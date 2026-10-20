#!/usr/bin/env python3
"""
itaf.engine.cross_repo_mapper - Cross-Repository Requirement-to-Test Mapping Engine.

Maps canonical requirements and expected outcomes to automated tests residing in separate
repositories using multi-signal evidence with explainable confidence and manual override support.
"""

from typing import Any, Dict, List, Optional, Set, Tuple
import re

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
        req_interface = requirement.interface.strip()
        req_endpoint = req_interface.split()[-1].lower() if " " in req_interface else req_interface.lower()
        req_method = req_interface.split()[0].upper() if " " in req_interface else "POST"

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

        # Extract Jira keys relevant to requirement
        req_jira_keys = set()
        for token in req_id.replace("_", "-").split("-"):
            if re.match(r'^[A-Z]{2,10}$', token):
                pass
        m = re.search(r'([A-Z]{2,10}-\d+)', req_id)
        if m:
            req_jira_keys.add(m.group(1).upper())
        if requirement.provenance and requirement.provenance.identifier:
            m_prov = re.search(r'([A-Z]{2,10}-\d+)', requirement.provenance.identifier)
            if m_prov:
                req_jira_keys.add(m_prov.group(1).upper())

        for outcome in requirement.expected_outcomes:
            outcome_mapped = False
            for test in available_tests.values():
                test_jira_set = {jk.upper() for jk in test.jira_keys}
                test_endpoints_set = {ep.lower() for ep in test.endpoints_visited}

                confidence = None
                evidence_reasons = []
                asserts_outcome = False

                # Signal 1: Jira Linkage
                has_jira_match = bool(req_jira_keys and (req_jira_keys & test_jira_set))
                if has_jira_match:
                    evidence_reasons.append(f"Linked to ticket key in test metadata: {', '.join(sorted(req_jira_keys & test_jira_set))}")

                # Signal 2: Interface match (endpoint & method)
                has_interface_match = any(
                    req_endpoint.rstrip("/") == ep.rstrip("/") or ep.endswith(req_endpoint) or req_endpoint.endswith(ep)
                    for ep in test_endpoints_set
                )
                if has_interface_match:
                    evidence_reasons.append(f"Exercises technical interface '{req_endpoint}'")

                # Signal 3: Assertion Depth Verification
                matching_assertions = []
                if outcome.outcome_type == RequirementType.IDEMPOTENCY:
                    for a in test.assertions:
                        if a.assertion_type == "IDEMPOTENCY_FLAG" or (
                            "idempotency" in a.target.lower() and a.is_deep_assertion
                        ):
                            matching_assertions.append(a)
                            asserts_outcome = True
                elif outcome.outcome_type == RequirementType.DUPLICATE_DETECTION:
                    for a in test.assertions:
                        if a.target == "409" or a.target == "DUPLICATE_PAYMENT":
                            matching_assertions.append(a)
                            asserts_outcome = True
                elif outcome.outcome_type == RequirementType.RESILIENCE_RETRY:
                    for a in test.assertions:
                        if a.assertion_type == "RETRY_COUNT" or (
                            outcome.expected_status_code and str(outcome.expected_status_code) == a.target
                            and any("retry" in (t.title.lower() + t.file_path.lower()) for t in [test])
                        ):
                            matching_assertions.append(a)
                            asserts_outcome = True
                elif outcome.outcome_type == RequirementType.SECURITY:
                    for a in test.assertions:
                        if outcome.expected_status_code and str(outcome.expected_status_code) == a.target:
                            matching_assertions.append(a)
                            asserts_outcome = True
                        elif not outcome.expected_status_code and a.target in ("401", "403"):
                            matching_assertions.append(a)
                            asserts_outcome = True
                elif outcome.outcome_type in (RequirementType.POSITIVE, RequirementType.API_CONTRACT):
                    for a in test.assertions:
                        if outcome.expected_status_code and str(outcome.expected_status_code) == a.target:
                            matching_assertions.append(a)
                            asserts_outcome = True
                elif outcome.outcome_type == RequirementType.DATA_INTEGRITY:
                    # Extract target field from outcome_id or description
                    field_match = re.search(r"OUT-MSG-([A-Z0-9_]+)-REQUIRED", outcome.outcome_id)
                    field_name = field_match.group(1).lower() if field_match else ""
                    for a in test.assertions:
                        if outcome.expected_status_code and str(outcome.expected_status_code) == a.target:
                            # Verify test is a negative test AND targets this specific field
                            test_text = (test.title + " " + test.file_path).lower()
                            if field_name and (field_name in test_text or field_name in a.raw_statement.lower()):
                                matching_assertions.append(a)
                                asserts_outcome = True
                            elif not field_name and any(neg in test_text for neg in ["reject", "invalid", "negative", "missing"]):
                                matching_assertions.append(a)
                                asserts_outcome = True

                elif outcome.outcome_type == RequirementType.NEGATIVE:
                    for a in test.assertions:
                        if outcome.expected_status_code and str(outcome.expected_status_code) == a.target:
                            if any(neg in test.title.lower() for neg in ["reject", "invalid", "negative", "missing", "error", "400", "422"]):
                                matching_assertions.append(a)
                                asserts_outcome = True

                if matching_assertions:
                    evidence_reasons.append(f"Asserts expected outcome condition ({len(matching_assertions)} assertion statement(s))")

                # Confidence Determination
                if asserts_outcome and has_interface_match and has_jira_match:
                    confidence = MappingConfidence.CONFIRMED
                elif asserts_outcome and has_interface_match:
                    confidence = MappingConfidence.HIGH
                elif asserts_outcome:
                    confidence = MappingConfidence.MEDIUM
                elif has_interface_match and has_jira_match:
                    # Test is explicitly linked to ticket and exercises endpoint, but doesn't deep assert this specific outcome
                    confidence = MappingConfidence.MEDIUM
                else:
                    # Merely visiting the interface without asserting this outcome or having a ticket link does not qualify
                    confidence = None

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
                    outcome_mapped = True

        return mappings
