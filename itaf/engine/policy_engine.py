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
    RequirementType,
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
        explicit_rule_ids = set(requirement.applicable_rule_ids)

        for rule in self.rules.values():
            # If the requirement explicitly specifies applicable rules, honor that explicit contract
            if explicit_rule_ids:
                if rule.rule_id in explicit_rule_ids:
                    applicable.append(rule)
                continue

            # Otherwise, evaluate scope based on requirement type, domain, and interface method
            applies = rule.applies_to
            domain_match = not applies.get("domains") or any(d.upper() == req_domain for d in applies["domains"])
            method_match = not applies.get("methods") or any(m.upper() == req_method for m in applies["methods"])

            if not (domain_match and method_match):
                continue

            category = rule.category.upper()
            rtype = requirement.req_type
            type_match = False
            if category == "SECURITY" and rtype == RequirementType.SECURITY:
                type_match = True
            elif category == "PAYMENT_CORRECTNESS":
                if rule.rule_id == "GATE-PAY-001" and rtype == RequirementType.IDEMPOTENCY:
                    type_match = True
                elif rule.rule_id == "GATE-PAY-002" and rtype == RequirementType.DUPLICATE_DETECTION:
                    type_match = True
                elif rule.rule_id == "GATE-PAY-003" and rtype in (RequirementType.DATA_INTEGRITY, RequirementType.NEGATIVE):
                    type_match = True
            elif category == "RESILIENCE":
                if rule.rule_id.startswith("GATE-RET") and rtype == RequirementType.RESILIENCE_RETRY:
                    type_match = True
                elif rule.rule_id == "GATE-CB-001" and rtype == RequirementType.CIRCUIT_BREAKER:
                    type_match = True
            elif category == "API_STANDARDS" and rtype == RequirementType.API_CONTRACT:
                type_match = True

            if type_match:
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
        if not asserting_tests:
            return (
                False,
                f"Gate '{rule.name}' ({rule.rule_id}) failed: Discovered tests merely visit interface but do not deeply assert expected outcome.",
                rule.severity
            )

        # Gate-specific validation based on evidence
        if rule.rule_id == "GATE-PAY-001":  # Idempotency
            has_idempotency_assertion = False
            for m in asserting_tests:
                test = all_tests.get(m.test_id)
                if test:
                    for a in test.assertions:
                        if a.assertion_type == "IDEMPOTENCY_FLAG":
                            has_idempotency_assertion = True
                            break
                        if a.assertion_type == "HEADER" and "idempotency" in a.target.lower():
                            has_idempotency_assertion = True
                            break
            if not has_idempotency_assertion:
                return (
                    False,
                    f"Gate '{rule.name}' ({rule.rule_id}) failed: Mapped tests do not assert that repeating requests with the same Idempotency-Key returns cached response without duplicate side-effects.",
                    rule.severity
                )

        elif rule.rule_id == "GATE-PAY-002":  # Business Duplicate Detection
            has_dup_assertion = False
            for m in asserting_tests:
                test = all_tests.get(m.test_id)
                if test:
                    for a in test.assertions:
                        if a.target == "409" or a.target == "DUPLICATE_PAYMENT":
                            has_dup_assertion = True
                            break
            if not has_dup_assertion:
                return (
                    False,
                    f"Gate '{rule.name}' ({rule.rule_id}) failed: No automated test asserts HTTP 409 Conflict rejection or DUPLICATE_PAYMENT code when separate submissions contain duplicate business fields.",
                    rule.severity
                )

        elif rule.rule_id == "GATE-PAY-003":  # Payment Amount and Currency Integrity
            has_integrity_assertion = False
            for m in asserting_tests:
                test = all_tests.get(m.test_id)
                if test:
                    for a in test.assertions:
                        if a.target == "400":
                            has_integrity_assertion = True
                            break
            if not has_integrity_assertion:
                return (
                    False,
                    f"Gate '{rule.name}' ({rule.rule_id}) failed: No automated test asserts rejection (HTTP 400 Bad Request) on negative, zero, or malformed payment amounts.",
                    rule.severity
                )

        elif rule.rule_id == "GATE-RET-001":  # Transient Retry Backoff
            has_retry_assertion = False
            for m in asserting_tests:
                test = all_tests.get(m.test_id)
                if test:
                    for a in test.assertions:
                        if a.assertion_type == "RETRY_COUNT":
                            has_retry_assertion = True
                            break
            if not has_retry_assertion:
                return (
                    False,
                    f"Gate '{rule.name}' ({rule.rule_id}) failed: No test case asserts retry count, exponential backoff, or downstream recovery on HTTP 503 / socket timeout.",
                    rule.severity
                )

        elif rule.rule_id == "GATE-RET-002":  # Idempotent Safe-Retry Boundary
            has_safe_retry = False
            for m in asserting_tests:
                test = all_tests.get(m.test_id)
                if test and ("safe" in test.title.lower() or "idempotent" in test.title.lower() or any(a.assertion_type == "RETRY_COUNT" for a in test.assertions)):
                    has_safe_retry = True
                    break
            if not has_safe_retry:
                return (
                    False,
                    f"Gate '{rule.name}' ({rule.rule_id}) failed: No test asserts that retries preserve idempotent execution boundary without ledger over-debits.",
                    rule.severity
                )

        elif rule.rule_id == "GATE-SEC-001":  # Authentication Token
            has_auth_assertion = False
            for m in asserting_tests:
                test = all_tests.get(m.test_id)
                if test:
                    for a in test.assertions:
                        if a.target == "401":
                            has_auth_assertion = True
                            break
            if not has_auth_assertion:
                return (
                    False,
                    f"Gate '{rule.name}' ({rule.rule_id}) failed: Missing test asserting HTTP 401 Unauthorized rejection on missing or expired token.",
                    rule.severity
                )

        elif rule.rule_id == "GATE-SEC-002":  # RBAC Authorization
            has_rbac_assertion = False
            for m in asserting_tests:
                test = all_tests.get(m.test_id)
                if test:
                    for a in test.assertions:
                        if a.target == "403":
                            has_rbac_assertion = True
                            break
            if not has_rbac_assertion:
                return (
                    False,
                    f"Gate '{rule.name}' ({rule.rule_id}) failed: Missing test asserting HTTP 403 Forbidden rejection when role lacks disbursement rights.",
                    rule.severity
                )

        elif rule.rule_id == "GATE-API-001":  # API Contract Conformity
            has_200 = any(a.target in ("200", "201") for m in asserting_tests for a in all_tests.get(m.test_id, DiscoveredTestCase("", "", "", 0, "")).assertions)
            has_400 = any(a.target == "400" for m in asserting_tests for a in all_tests.get(m.test_id, DiscoveredTestCase("", "", "", 0, "")).assertions)
            if not (has_200 and has_400):
                missing_parts = []
                if not has_200: missing_parts.append("positive HTTP 200/201")
                if not has_400: missing_parts.append("negative HTTP 400 Bad Request")
                return (
                    False,
                    f"Gate '{rule.name}' ({rule.rule_id}) failed: Missing contract validation for: {', '.join(missing_parts)}.",
                    rule.severity
                )

        elif rule.rule_id == "GATE-API-002":  # Standardized Error Structure
            has_err_body = any(
                a.assertion_type == "ERROR_CODE"
                for m in asserting_tests
                for a in all_tests.get(m.test_id, DiscoveredTestCase("", "", "", 0, "")).assertions
            )
            if not has_err_body:
                return (
                    False,
                    f"Gate '{rule.name}' ({rule.rule_id}) failed: No test asserts standardized problem details or error code in error response body.",
                    rule.severity
                )

        elif rule.rule_id == "GATE-CB-001":  # Circuit Breaker
            has_cb = any(
                "circuit" in test.title.lower() or "breaker" in test.title.lower()
                for m in asserting_tests
                for test in [all_tests.get(m.test_id)]
                if test
            )
            if not has_cb:
                return (
                    False,
                    f"Gate '{rule.name}' ({rule.rule_id}) failed: No automated test asserts circuit breaker trip/isolation under consecutive downstream failures.",
                    rule.severity
                )

        return (
            True,
            f"Gate '{rule.name}' ({rule.rule_id}) PASSED: Demonstrated by test(s): {', '.join(m.test_id for m in asserting_tests)}.",
            rule.severity
        )
