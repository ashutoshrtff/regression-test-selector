#!/usr/bin/env python3
"""
itaf.engine.coverage_intelligence - Core Coverage Intelligence Assessment Engine.

Evaluates required expected outcomes against discovered tests and execution evidence.
Produces explainable coverage states: COVERED, PARTIALLY_COVERED, MISSING_COVERAGE, BLOCKED.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

from itaf.core.models import (
    Requirement,
    ExpectedOutcome,
    DiscoveredTestCase,
    RequirementTestMapping,
    RequirementCoverageAssessment,
    CoverageStatus,
    ExecutionStatus,
    PolicyRule,
    RuleSeverity
)
from itaf.engine.policy_engine import PolicyEngine
from itaf.engine.cross_repo_mapper import CrossRepoMapper


class CoverageIntelligenceEngine:
    """Evaluates expected outcomes against tests and policies, calculating rigorous metrics."""

    def __init__(self, policy_engine: PolicyEngine, mapper: Optional[CrossRepoMapper] = None):
        self.policy_engine = policy_engine
        self.mapper = mapper or CrossRepoMapper()

    def assess_coverage(
        self,
        requirements: List[Requirement],
        available_tests: Dict[str, DiscoveredTestCase],
        execution_evidence: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[RequirementCoverageAssessment]:
        """
        Performs deep coverage intelligence analysis across all requirements.
        execution_evidence format: { "test_id": { "status": "EXECUTION_PASSED", "timestamp": "...", "duration": 4.2 } }
        """
        execution_evidence = execution_evidence or {}
        assessments: List[RequirementCoverageAssessment] = []

        # Build flexible lookup index for execution evidence
        evidence_by_title: Dict[Any, Dict[str, Any]] = {}
        for ev_key, ev_val in execution_evidence.items():
            evidence_by_title[ev_key] = ev_val
            parts = ev_key.split(":", 2)
            if len(parts) >= 3:
                evidence_by_title[parts[2].strip()] = ev_val
                evidence_by_title[(parts[0].replace("\\", "/"), parts[2].strip())] = ev_val
            else:
                evidence_by_title[ev_key.strip()] = ev_val

        # Update test execution statuses if real evidence provided
        for test_id, test in available_tests.items():
            ev = None
            if test_id in execution_evidence:
                ev = execution_evidence[test_id]
            elif (test.file_path, test.title) in evidence_by_title:
                ev = evidence_by_title[(test.file_path, test.title)]
            elif test.title in evidence_by_title:
                ev = evidence_by_title[test.title]

            if ev:
                stat_str = ev.get("status", "TEST_NOT_EXECUTED")
                try:
                    test.execution_status = ExecutionStatus(stat_str)
                except ValueError:
                    test.execution_status = ExecutionStatus.TEST_NOT_EXECUTED
                test.last_execution_timestamp = ev.get("timestamp")
                test.execution_duration_sec = float(ev.get("duration", 0.0))

        for req in requirements:
            # 1. Map requirements to tests
            mapped_tests = self.mapper.map_requirement_to_tests(req, available_tests)

            # 2. Evaluate applicable quality gates
            applicable_rules = self.policy_engine.get_applicable_rules(req)
            failing_gates = []
            assessment_notes = []

            for rule in applicable_rules:
                passes, reason, severity = self.policy_engine.evaluate_gate(
                    rule=rule,
                    requirement=req,
                    mapped_tests=mapped_tests,
                    all_tests=available_tests
                )
                if not passes:
                    failing_gates.append(rule.rule_id)
                    assessment_notes.append(f"[{severity.value}] {reason}")
                else:
                    assessment_notes.append(f"[PASS] {reason}")

            if not applicable_rules:
                assessment_notes.append("[INFO] No organizational quality gates apply to this requirement.")

            # 3. Determine uncovered expected outcomes
            covered_outcome_ids = {m.outcome_id for m in mapped_tests if m.asserts_outcome}
            uncovered_outcomes = [
                out for out in req.expected_outcomes
                if out.outcome_id not in covered_outcome_ids
            ]

            # 4. Determine overall CoverageStatus
            if req.ambiguity_notes:
                coverage_status = CoverageStatus.AMBIGUOUS
                assessment_notes.extend([f"[AMBIGUITY] {n}" for n in req.ambiguity_notes])
            elif not req.mandatory and not req.expected_outcomes:
                coverage_status = CoverageStatus.NOT_APPLICABLE
                assessment_notes.append("[NOT_APPLICABLE] Requirement is non-mandatory and defines no expected outcomes.")
            elif len(req.expected_outcomes) == 0:
                # Critical guardrail: A requirement with zero expected outcomes cannot be marked COVERED
                coverage_status = CoverageStatus.AMBIGUOUS
                assessment_notes.append("[AMBIGUITY] Requirement specifies zero expected outcomes; testable behavior missing.")
            elif not mapped_tests:
                coverage_status = CoverageStatus.MISSING_COVERAGE
            elif len(uncovered_outcomes) == 0 and len(failing_gates) == 0:
                coverage_status = CoverageStatus.COVERED
            elif len(uncovered_outcomes) < len(req.expected_outcomes) or any(m.asserts_outcome for m in mapped_tests):
                coverage_status = CoverageStatus.PARTIALLY_COVERED
            else:
                coverage_status = CoverageStatus.MISSING_COVERAGE

            # 5. Determine combined ExecutionStatus of mapped tests (independently from coverage status)
            asserting_mapped = [m for m in mapped_tests if m.asserts_outcome]
            relevant_tests = [available_tests[m.test_id] for m in asserting_mapped if m.test_id in available_tests]

            if not relevant_tests:
                if mapped_tests and any(m.test_id in available_tests for m in mapped_tests):
                    # Tests visit interface/Jira but do NOT assert this requirement's expected outcome
                    exec_status = ExecutionStatus.TEST_NOT_EXECUTED
                else:
                    exec_status = ExecutionStatus.EVIDENCE_MISSING
            elif any(t.execution_status == ExecutionStatus.EXECUTION_FAILED for t in relevant_tests):
                exec_status = ExecutionStatus.EXECUTION_FAILED
            elif all(t.execution_status == ExecutionStatus.EXECUTION_PASSED for t in relevant_tests):
                exec_status = ExecutionStatus.EXECUTION_PASSED
            else:
                exec_status = ExecutionStatus.TEST_NOT_EXECUTED

            # 6. Formulate suggested test scenario if coverage is missing, partial, or ambiguous
            suggested_scenario = None
            if coverage_status in (CoverageStatus.MISSING_COVERAGE, CoverageStatus.PARTIALLY_COVERED, CoverageStatus.AMBIGUOUS):
                suggested_scenario = self._generate_suggested_scenario(req, uncovered_outcomes)

            assessments.append(RequirementCoverageAssessment(
                requirement_id=req.requirement_id,
                title=req.title,
                domain=req.domain,
                service=req.service,
                coverage_status=coverage_status,
                mapped_tests=mapped_tests,
                uncovered_outcomes=uncovered_outcomes,
                applicable_rules=[r.rule_id for r in applicable_rules],
                failing_gate_ids=failing_gates,
                execution_status=exec_status,
                assessment_notes=assessment_notes,
                suggested_test_scenario=suggested_scenario
            ))

        return assessments

    def _generate_suggested_scenario(
        self,
        req: Requirement,
        uncovered_outcomes: List[ExpectedOutcome]
    ) -> Dict[str, Any]:
        """Proposes concrete test title and verification steps for missing coverage."""
        steps = []
        if req.req_type.value == "RESILIENCE_RETRY":
            title = f"Verify transient downstream 503 retry and recovery for {req.interface}"
            steps = [
                f"1. Mock downstream payment provider to return HTTP 503 on initial invocation.",
                f"2. Invoke {req.interface} and observe that an automated retry attempt is dispatched with exponential backoff.",
                f"3. Configure downstream mock to return HTTP 200 on second invocation.",
                f"4. Assert that payment succeeds with HTTP 200 and total retry counter equals 1."
            ]
        elif req.req_type.value == "DUPLICATE_DETECTION":
            title = f"Verify business duplicate transaction rejection (409 Conflict) on {req.interface}"
            steps = [
                f"1. Submit valid payment with unique transaction payload.",
                f"2. Within 60 seconds, submit a separate payment request with identical recipient, amount, and reference.",
                f"3. Assert HTTP response status is 409 Conflict.",
                f"4. Assert response body contains errorCode 'DUPLICATE_PAYMENT' and ledger contains only 1 debit."
            ]
        elif req.req_type.value == "IDEMPOTENCY":
            title = f"Verify replay safety using Idempotency-Key on {req.interface}"
            steps = [
                f"1. Generate unique Idempotency-Key header and submit request to {req.interface}.",
                f"2. Re-send identical request with the exact same Idempotency-Key header.",
                f"3. Assert HTTP status and response payload are identical to the first execution.",
                f"4. Assert downstream payment processor receives exactly one financial authorization."
            ]
        else:
            title = f"Verify expected outcomes for requirement {req.requirement_id} on {req.interface}"
            steps = [f"Step {i+1}: Assert {out.description}" for i, out in enumerate(uncovered_outcomes)] or ["Verify outcome."]

        return {
            "title": title,
            "target_interface": req.interface,
            "steps": steps,
            "mandatory": req.mandatory,
            "severity": req.severity.value
        }
