#!/usr/bin/env python3
"""
itaf.engine.policy_engine - Deterministic Hard-Gate and Policy Evaluation Engine.

Loads machine-readable policy rules from gates/, validates them against JSON schema,
and evaluates whether requirements and tests satisfy mandatory quality gates.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from itaf.core.models import (
    PolicyRule,
    RuleSeverity,
    Requirement,
    DiscoveredTestCase,
    RequirementTestMapping,
    CoverageStatus
)
from itaf.core.schemas import load_schema, validate_dict

GATES_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "gates"))


def _parse_yaml_file(filepath: str) -> Dict[str, Any]:
    """Parses YAML file with PyYAML if installed, otherwise lightweight standard library parser."""
    try:
        import yaml
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except ImportError:
        pass

    # Built-in lightweight YAML parser for rules
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    rules = []
    current_rule: Dict[str, Any] = {}
    current_list_key = ""

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- rule_id:"):
            if current_rule:
                rules.append(current_rule)
            current_rule = {"rule_id": stripped.split(":", 1)[1].strip().strip('"\'')}
            current_list_key = ""
        elif current_rule:
            if stripped.startswith("name:"):
                current_rule["name"] = stripped.split(":", 1)[1].strip().strip('"\'')
            elif stripped.startswith("category:"):
                current_rule["category"] = stripped.split(":", 1)[1].strip().strip('"\'')
            elif stripped.startswith("severity:"):
                current_rule["severity"] = stripped.split(":", 1)[1].strip().strip('"\'')
            elif stripped.startswith("mandatory:"):
                current_rule["mandatory"] = stripped.split(":", 1)[1].strip().lower() == "true"
            elif stripped.startswith("description:"):
                current_rule["description"] = stripped.split(":", 1)[1].strip().strip('"\'')
            elif stripped.startswith("failure_criteria:"):
                current_rule["failure_criteria"] = stripped.split(":", 1)[1].strip().strip('"\'')
            elif stripped.startswith("source_standard:"):
                current_rule["source_standard"] = stripped.split(":", 1)[1].strip().strip('"\'')
            elif stripped.startswith("version:"):
                current_rule["version"] = stripped.split(":", 1)[1].strip().strip('"\'')
            elif stripped.startswith("applies_to:"):
                current_rule["applies_to"] = {}
                current_list_key = "applies_to"
            elif stripped.startswith("domains:") and current_list_key == "applies_to":
                current_rule["applies_to"]["domains"] = []
                current_list_key = "domains"
            elif stripped.startswith("methods:") and "applies_to" in current_rule:
                current_rule["applies_to"]["methods"] = []
                current_list_key = "methods"
            elif stripped.startswith("required_outcomes:"):
                current_rule["required_outcomes"] = []
                current_list_key = "required_outcomes"
            elif stripped.startswith("- ") and current_list_key:
                val = stripped[2:].strip().strip('"\'')
                if current_list_key == "domains":
                    current_rule["applies_to"]["domains"].append(val)
                elif current_list_key == "methods":
                    current_rule["applies_to"]["methods"].append(val)
                elif current_list_key == "required_outcomes":
                    current_rule["required_outcomes"].append(val)

    if current_rule:
        rules.append(current_rule)

    return {"rules": rules}


class PolicyEngine:
    """Loads, validates, and deterministically evaluates quality gates."""

    def __init__(self, gates_dir: Optional[str] = None):
        self.gates_dir = gates_dir or GATES_DIR
        self.rules: Dict[str, PolicyRule] = {}
        self.rule_schema = load_schema("policy-rule.schema.json")
        self.validation_errors: List[str] = []
        self._load_rules()

    def _load_rules(self):
        """Recursively loads all YAML policy rule definitions from the gates directory."""
        if not os.path.exists(self.gates_dir):
            return

        for root, _, files in os.walk(self.gates_dir):
            for file in files:
                if file.endswith(".yaml") or file.endswith(".yml"):
                    file_path = os.path.join(root, file)
                    doc = _parse_yaml_file(file_path)
                    raw_rules = doc.get("rules", [])
                    for raw in raw_rules:
                        # Validate against schema
                        is_valid, errors = validate_dict(raw, self.rule_schema)
                        if not is_valid:
                            self.validation_errors.append(f"Invalid rule in {file}: {', '.join(errors)}")
                            continue

                        rule = PolicyRule(
                            rule_id=raw["rule_id"],
                            name=raw["name"],
                            category=raw["category"],
                            description=raw["description"],
                            severity=RuleSeverity(raw["severity"]),
                            mandatory=raw["mandatory"],
                            applies_to=raw.get("applies_to", {}),
                            required_outcomes=raw.get("required_outcomes", []),
                            failure_criteria=raw["failure_criteria"],
                            source_standard=raw.get("source_standard", "Internal"),
                            version=raw.get("version", "1.0.0")
                        )
                        self.rules[rule.rule_id] = rule

    def get_applicable_rules(self, requirement: Requirement) -> List[PolicyRule]:
        """Determines which policy rules apply to a given requirement."""
        applicable = []
        req_domain = requirement.domain.upper()
        req_interface = requirement.interface.upper()
        req_method = req_interface.split()[0] if " " in req_interface else "POST"

        for rule in self.rules.values():
            applies = rule.applies_to
            domain_match = not applies.get("domains") or any(d.upper() == req_domain for d in applies["domains"])
            method_match = not applies.get("methods") or any(m.upper() == req_method for m in applies["methods"])

            if domain_match and method_match:
                applicable.append(rule)

        return applicable

    def evaluate_gate(
        self,
        rule: PolicyRule,
        requirement: Requirement,
        mapped_tests: List[RequirementTestMapping],
        all_tests: Dict[str, DiscoveredTestCase]
    ) -> Tuple[bool, str, RuleSeverity]:
        """
        Evaluates whether a specific quality gate passes for a requirement.
        Returns: (passes: bool, explanation: str, severity: RuleSeverity)
        """
        if not mapped_tests:
            return (
                False,
                f"Gate '{rule.name}' ({rule.rule_id}) failed: No tests are mapped to requirement '{requirement.requirement_id}'. {rule.failure_criteria}",
                rule.severity
            )

        # Inspect if any mapped test genuinely asserts the required outcomes
        asserting_tests = [m for m in mapped_tests if m.asserts_outcome]

        # Specific gate checks
        if rule.rule_id == "GATE-PAY-001":  # Idempotency
            # Must assert idempotency header and replay safety
            has_idempotency_assertion = False
            for m in mapped_tests:
                test = all_tests.get(m.test_id)
                if test:
                    for a in test.assertions:
                        if "idempotency" in a.target.lower() or "idempotency" in a.raw_statement.lower():
                            has_idempotency_assertion = True
                            break
            if not has_idempotency_assertion:
                return (
                    False,
                    f"Gate '{rule.name}' ({rule.rule_id}) failed: Mapped tests do not assert that repeating requests with the same Idempotency-Key returns cached response without duplicate side-effects.",
                    rule.severity
                )

        elif rule.rule_id == "GATE-PAY-002":  # Business Duplicate Detection
            # Must assert HTTP 409 or DUPLICATE_PAYMENT code
            has_dup_assertion = False
            for m in mapped_tests:
                test = all_tests.get(m.test_id)
                if test:
                    for a in test.assertions:
                        if a.target == "409" or "duplicate" in a.target.lower() or "conflict" in a.raw_statement.lower():
                            has_dup_assertion = True
                            break
            if not has_dup_assertion:
                return (
                    False,
                    f"Gate '{rule.name}' ({rule.rule_id}) failed: No automated test asserts HTTP 409 Conflict rejection when separate submissions contain duplicate business fields.",
                    rule.severity
                )

        elif rule.rule_id == "GATE-RET-001":  # Transient Retry Backoff
            # Must assert retry count, 503 recovery, or backoff
            has_retry_assertion = False
            for m in mapped_tests:
                test = all_tests.get(m.test_id)
                if test:
                    for a in test.assertions:
                        if "retry" in a.target.lower() or a.assertion_type == "RETRY_COUNT" or "503" in a.target:
                            has_retry_assertion = True
                            break
            if not has_retry_assertion:
                return (
                    False,
                    f"Gate '{rule.name}' ({rule.rule_id}) failed: No test case asserts retry count, exponential backoff, or downstream recovery on HTTP 503 / socket timeout.",
                    rule.severity
                )

        elif rule.rule_id == "GATE-SEC-001":  # Authentication Token
            has_auth_assertion = False
            for m in mapped_tests:
                test = all_tests.get(m.test_id)
                if test:
                    for a in test.assertions:
                        if a.target in ("401", "403") or "auth" in a.target.lower() or "unauthorized" in a.raw_statement.lower():
                            has_auth_assertion = True
                            break
            if not has_auth_assertion:
                return (
                    False,
                    f"Gate '{rule.name}' ({rule.rule_id}) failed: Missing test asserting HTTP 401 Unauthorized rejection on missing or expired token.",
                    rule.severity
                )

        if not asserting_tests:
            return (
                False,
                f"Gate '{rule.name}' ({rule.rule_id}) failed: Discovered tests merely visit interface but do not deeply assert expected outcome.",
                rule.severity
            )

        return (
            True,
            f"Gate '{rule.name}' ({rule.rule_id}) PASSED: Demonstrated by test(s): {', '.join(m.test_id for m in asserting_tests)}.",
            rule.severity
        )
