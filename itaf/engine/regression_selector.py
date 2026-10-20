#!/usr/bin/env python3
"""
itaf.engine.regression_selector - Requirement-Driven Smart Regression Test Selector.

Evolves impact analysis by connecting changed code fingerprints -> affected requirements
and expected outcomes -> ranked regression tests, highlighting unmitigated coverage gaps.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

from itaf.core.models import (
    Requirement,
    DiscoveredTestCase,
    RequirementCoverageAssessment,
    RegressionSelectionDecision,
    CoverageStatus,
    RuleSeverity
)


class RegressionSelector:
    """Selects and prioritizes automated tests based on code change and requirement impact."""

    def __init__(self, available_tests: Dict[str, DiscoveredTestCase]):
        self.available_tests = available_tests

    def select_tests_for_change(
        self,
        change_fingerprints: Dict[str, Any],
        assessments: List[RequirementCoverageAssessment],
        risk_widening_active: bool = False
    ) -> Tuple[List[RegressionSelectionDecision], List[Dict[str, Any]], List[str]]:
        """
        Returns:
        (selected_decisions, unmitigated_gaps, warning_notes)
        """
        change_endpoints = {ep.split(" ", 1)[-1] for ep in change_fingerprints.get("endpoints", [])}
        change_routes = set(change_fingerprints.get("routes", []))
        change_jira = set(change_fingerprints.get("jira_keys", []))
        risk_signals = change_fingerprints.get("risk_signals", [])

        # Determine if risk widening should be triggered
        if risk_signals or risk_widening_active:
            risk_widening_active = True

        selected_map: Dict[str, RegressionSelectionDecision] = {}
        unmitigated_gaps: List[Dict[str, Any]] = []
        warning_notes: List[str] = []

        # 1. Identify which requirements are affected by this change
        affected_assessments = []
        for ass in assessments:
            is_affected = False

            # Check interface via mapped tests, suggested scenario, title, or ID
            target_interfaces = []
            if ass.suggested_test_scenario and "target_interface" in ass.suggested_test_scenario:
                target_interfaces.append(ass.suggested_test_scenario["target_interface"].lower())
            for m in ass.mapped_tests:
                test = self.available_tests.get(m.test_id)
                if test:
                    target_interfaces.extend([ep.lower() for ep in test.endpoints_visited])
                    target_interfaces.extend([r.lower() for r in test.routes_visited])

            for ep in change_endpoints:
                ep_clean = ep.lower().strip()
                if (
                    ep_clean in ass.title.lower()
                    or ep_clean in ass.requirement_id.lower()
                    or any(ep_clean in iface for iface in target_interfaces)
                    or any(ep_clean in m.evidence_summary.lower() for m in ass.mapped_tests)
                ):
                    is_affected = True
                    break

            for rt in change_routes:
                rt_clean = rt.lower().strip()
                if any(rt_clean in iface for iface in target_interfaces):
                    is_affected = True
                    break

            for jk in change_jira:
                jk_clean = jk.upper().strip()
                if jk_clean in ass.requirement_id.upper() or any(
                    jk_clean in m.evidence_summary.upper() for m in ass.mapped_tests
                ):
                    is_affected = True
                    break

            # If no technical endpoints were resolved from diff, fall back conservatively to all requirements in domain
            if is_affected or (len(change_endpoints) == 0 and len(change_routes) == 0 and len(change_jira) == 0):
                affected_assessments.append(ass)

        # Conservative selection fallback: if diff has evidence but no requirement matched
        if not affected_assessments and (change_endpoints or change_routes or change_jira):
            warning_notes.append(
                "Change impact evidence did not conclusively link to known specifications. "
                "Applying conservative domain fallback to prevent regression escapes."
            )
            affected_assessments = assessments

        # 2. Select tests mapped to affected requirements
        for ass in affected_assessments:
            # Check if this affected requirement has missing, partial, or ambiguous coverage
            if ass.coverage_status in (
                CoverageStatus.MISSING_COVERAGE,
                CoverageStatus.PARTIALLY_COVERED,
                CoverageStatus.AMBIGUOUS,
                CoverageStatus.BLOCKED
            ):
                if ass.suggested_test_scenario:
                    unmitigated_gaps.append({
                        "requirement_id": ass.requirement_id,
                        "title": ass.title,
                        "status": ass.coverage_status.value,
                        "scenario": ass.suggested_test_scenario,
                        "failing_gates": ass.failing_gate_ids
                    })
                    status_desc = "ambiguous/unspecified criteria" if ass.coverage_status == CoverageStatus.AMBIGUOUS else "inadequate test coverage"
                    warning_notes.append(
                        f"Change impacts requirement '{ass.requirement_id}' with {status_desc}! "
                        f"Failing gates: {', '.join(ass.failing_gate_ids) if ass.failing_gate_ids else 'None'}. "
                        f"Recommended new test: '{ass.suggested_test_scenario['title']}'."
                    )

            for m in ass.mapped_tests:
                test = self.available_tests.get(m.test_id)
                if not test:
                    continue

                priority = "MUST_RUN" if m.asserts_outcome else "SHOULD_RUN"
                confidence = m.confidence.value

                if m.test_id not in selected_map:
                    selected_map[m.test_id] = RegressionSelectionDecision(
                        test_id=test.test_id,
                        title=test.title,
                        file_path=test.file_path,
                        framework=test.framework,
                        in_regression_suite=test.in_regression_suite,
                        priority=priority,
                        confidence=confidence,
                        selection_reasons=[f"Covers affected requirement '{ass.requirement_id}' ({m.evidence_summary})"],
                        affected_requirement_ids=[ass.requirement_id],
                        affected_outcomes=[m.outcome_id],
                        triggered_by_gates=ass.failing_gate_ids
                    )
                else:
                    dec = selected_map[m.test_id]
                    if ass.requirement_id not in dec.affected_requirement_ids:
                        dec.affected_requirement_ids.append(ass.requirement_id)
                        dec.selection_reasons.append(f"Also covers requirement '{ass.requirement_id}'")
                    if priority == "MUST_RUN":
                        dec.priority = "MUST_RUN"

        # 3. Apply Risk Widening (Smoke Suite Activation)
        if risk_widening_active:
            for test in self.available_tests.values():
                if test.in_smoke_suite and test.test_id not in selected_map:
                    selected_map[test.test_id] = RegressionSelectionDecision(
                        test_id=test.test_id,
                        title=test.title,
                        file_path=test.file_path,
                        framework=test.framework,
                        in_regression_suite=test.in_regression_suite,
                        priority="SMOKE_ONLY",
                        confidence="HIGH",
                        selection_reasons=[
                            f"Activated by risk widening trigger: {', '.join(s.get('category','') for s in risk_signals)}"
                            if risk_signals else "Activated by risk widening policy"
                        ],
                        affected_requirement_ids=["SYS-RISK-WIDENING"],
                        affected_outcomes=[],
                        triggered_by_gates=["GATE-RISK-SMOKE"]
                    )

        # 4. Strict Validation Guardrail: Ensure every selected test ID actually exists
        for tid in selected_map.keys():
            if tid not in self.available_tests:
                raise ValueError(f"[CRITICAL ERROR] Hallucinated or non-existent test selected: {tid}")

        # Order decisions: MUST_RUN first, then SHOULD_RUN, then SMOKE_ONLY
        order_weights = {"MUST_RUN": 1, "SHOULD_RUN": 2, "SMOKE_ONLY": 3}
        ranked_decisions = sorted(
            selected_map.values(),
            key=lambda d: (order_weights.get(d.priority, 9), d.title)
        )

        return ranked_decisions, unmitigated_gaps, warning_notes
