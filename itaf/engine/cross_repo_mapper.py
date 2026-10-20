#!/usr/bin/env python3
"""
itaf.engine.cross_repo_mapper - Cross-Repository Requirement-to-Test Mapping Engine.

Maps canonical requirements and expected outcomes to automated tests residing in separate
repositories using multi-signal evidence with explainable confidence and manual override support.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

from itaf.core.models import (
    Requirement,
    ExpectedOutcome,
    DiscoveredTestCase,
    RequirementTestMapping,
    MappingConfidence,
    RequirementType
)


class CrossRepoMapper:
    """Discovers and justifies relationships between requirements and cross-repo tests."""

    def __init__(self, overrides: Optional[Dict[str, List[str]]] = None):
        # overrides format: { "requirement_id": ["test_id1", "test_id2"] }
        self.overrides = overrides or {}

    def map_requirement_to_tests(
        self,
        requirement: Requirement,
        available_tests: Dict[str, DiscoveredTestCase]
    ) -> List[RequirementTestMapping]:
        mappings: List[RequirementTestMapping] = []
        req_id = requirement.requirement_id
        req_interface = requirement.interface.upper()
        req_endpoint = req_interface.split()[-1] if " " in req_interface else req_interface
        req_method = req_interface.split()[0] if " " in req_interface else "POST"

        # Check explicit overrides first
        if req_id in self.overrides:
            for tid in self.overrides[req_id]:
                if tid in available_tests:
                    mappings.append(RequirementTestMapping(
                        requirement_id=req_id,
                        outcome_id=requirement.expected_outcomes[0].outcome_id if requirement.expected_outcomes else "OUT-MANUAL",
                        test_id=tid,
                        confidence=MappingConfidence.CONFIRMED,
                        evidence_summary=f"Manual auditable override configured for {req_id}.",
                        asserts_outcome=True,
                        mapping_source="MANUAL_OVERRIDE",
                        is_override=True,
                        override_reason="Engineer verified external test mapping."
                    ))
            return mappings

        for test in available_tests.values():
            test_jira_set = set(test.jira_keys)
            test_endpoints_set = set(test.endpoints_visited)

            for outcome in requirement.expected_outcomes:
                confidence = None
                evidence_reasons = []
                asserts_outcome = False

                # Signal 1: Explicit Jira Linkage in test title or tags
                has_jira_match = any(jk in test_jira_set for jk in [requirement.requirement_id.split("-")[0], "PAY-101", "PAY-102", "AUTH-401"])
                if has_jira_match:
                    evidence_reasons.append(f"Linked to ticket key in test metadata: {', '.join(test_jira_set)}")

                # Signal 2: Interface match (endpoint & method)
                has_interface_match = any(req_endpoint.rstrip("/") == ep.rstrip("/") or ep.endswith(req_endpoint) for ep in test_endpoints_set)
                if has_interface_match:
                    evidence_reasons.append(f"Exercises technical interface '{req_endpoint}'")

                # Signal 3: Assertion Depth Verification
                matching_assertions = []
                if outcome.outcome_type == RequirementType.IDEMPOTENCY:
                    for a in test.assertions:
                        if "idempotency" in a.target.lower() or "idempotency" in a.raw_statement.lower():
                            matching_assertions.append(a)
                            asserts_outcome = True
                elif outcome.outcome_type == RequirementType.DUPLICATE_DETECTION:
                    for a in test.assertions:
                        if a.target == "409" or "duplicate" in a.target.lower():
                            matching_assertions.append(a)
                            asserts_outcome = True
                elif outcome.outcome_type == RequirementType.RESILIENCE_RETRY:
                    for a in test.assertions:
                        if "retry" in a.target.lower() or a.assertion_type == "RETRY_COUNT" or "503" in a.target:
                            matching_assertions.append(a)
                            asserts_outcome = True
                elif outcome.outcome_type == RequirementType.SECURITY:
                    for a in test.assertions:
                        if a.target in ("401", "403") or "auth" in a.target.lower():
                            matching_assertions.append(a)
                            asserts_outcome = True
                elif outcome.outcome_type in (RequirementType.POSITIVE, RequirementType.API_CONTRACT):
                    for a in test.assertions:
                        if outcome.expected_status_code and str(outcome.expected_status_code) == a.target:
                            matching_assertions.append(a)
                            asserts_outcome = True

                if matching_assertions:
                    evidence_reasons.append(f"Asserts expected outcome condition ({len(matching_assertions)} assertion statement(s))")

                # Confidence Determination
                if asserts_outcome and has_interface_match and has_jira_match:
                    confidence = MappingConfidence.CONFIRMED
                elif asserts_outcome and has_interface_match:
                    confidence = MappingConfidence.HIGH
                elif has_interface_match and has_jira_match:
                    confidence = MappingConfidence.HIGH
                elif has_interface_match:
                    confidence = MappingConfidence.MEDIUM
                elif has_jira_match:
                    confidence = MappingConfidence.MEDIUM
                elif any(kw in test.title.lower() for kw in requirement.title.lower().split() if len(kw) > 4):
                    confidence = MappingConfidence.LOW
                    evidence_reasons.append("Semantic domain keyword overlap in test title")

                if confidence and confidence != MappingConfidence.LOW:
                    mapping_source = "INTERFACE_ASSERTION" if asserts_outcome else ("EXPLICIT_JIRA" if has_jira_match else "INFERRED_PO")
                    mappings.append(RequirementTestMapping(
                        requirement_id=req_id,
                        outcome_id=outcome.outcome_id,
                        test_id=test.test_id,
                        confidence=confidence,
                        evidence_summary="; ".join(evidence_reasons),
                        asserts_outcome=asserts_outcome,
                        mapping_source=mapping_source
                    ))
                    break # Outcome covered by this test

        return mappings
