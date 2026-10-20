#!/usr/bin/env python3
"""
itaf.reports.generator - Audit-Ready Test Assurance & Regression Report Generator.

Formats comprehensive coverage intelligence, mandatory quality gate outcomes,
evidence traceability, and ranked regression decisions into Markdown and JSON.
"""

import json
from typing import Any, Dict, List, Optional

from itaf.core.models import (
    RequirementCoverageAssessment,
    RegressionSelectionDecision,
    CoverageStatus,
    ExecutionStatus,
    RuleSeverity
)


def generate_markdown_report(
    assessments: List[RequirementCoverageAssessment],
    regression_decisions: Optional[List[RegressionSelectionDecision]] = None,
    change_summary: Optional[str] = None,
    project_name: str = "Payment Services Platform",
    is_live_evidence: bool = False
) -> str:
    """Generates an audit-ready Markdown report."""
    regression_decisions = regression_decisions or []
    lines: List[str] = []

    lines.append(f"# Intelligent Test Assurance Report: {project_name}\n")
    lines.append(f"**Generated**: {assessments[0].domain if assessments else 'Enterprise'} | "
                 f"**Evidence Source**: {'Live Infrastructure' if is_live_evidence else 'Verified Test Fixture / Local Environment'}\n")

    # 1. Executive Summary
    total_reqs = len(assessments)
    covered_reqs = sum(1 for a in assessments if a.coverage_status == CoverageStatus.COVERED)
    partial_reqs = sum(1 for a in assessments if a.coverage_status == CoverageStatus.PARTIALLY_COVERED)
    missing_reqs = sum(1 for a in assessments if a.coverage_status == CoverageStatus.MISSING_COVERAGE)
    failing_gates_total = sum(len(a.failing_gate_ids) for a in assessments)

    coverage_pct = (covered_reqs / total_reqs * 100) if total_reqs > 0 else 0

    lines.append("## 1. Executive Quality Assurance Summary\n")
    lines.append(f"- **Total Applicable Requirements**: {total_reqs}")
    lines.append(f"- **Fully Covered Requirements**: {covered_reqs} ({coverage_pct:.1f}%)")
    lines.append(f"- **Partially Covered Requirements**: {partial_reqs}")
    lines.append(f"- **Requirements Missing Test Coverage**: {missing_reqs}")
    lines.append(f"- **Mandatory Quality Gate Failures**: **{failing_gates_total}**\n")

    if failing_gates_total > 0:
        lines.append("> [!CAUTION] **Mandatory Quality Gates Failing**")
        lines.append("> One or more mandatory technical or compliance policies have zero verifying test assertions.\n")
    else:
        lines.append("> [!NOTE] **All Mandatory Quality Gates Passed**\n")

    # 2. Mandatory Quality Gate Outcomes
    lines.append("## 2. Mandatory Quality Gate Outcomes\n")
    lines.append("| Gate ID | Requirement | Status | Severity | Finding & Policy Detail |")
    lines.append("| :--- | :--- | :---: | :---: | :--- |")

    for a in assessments:
        for note in a.assessment_notes:
            if note.startswith("[BLOCKER]") or note.startswith("[CRITICAL]") or note.startswith("[MAJOR]"):
                parts = note.split(" ", 1)
                sev = parts[0].strip("[]")
                # Extract specific gate ID if present in message
                import re
                m_gate = re.search(r'\((GATE-[A-Z0-9\-]+)\)', parts[1])
                gate_label = m_gate.group(1) if m_gate else (a.failing_gate_ids[0] if a.failing_gate_ids else 'GATE-RULE')
                lines.append(f"| `{gate_label}` | `{a.requirement_id}` | ❌ **FAIL** | {sev} | {parts[1]} |")
            elif note.startswith("[PASS]"):
                import re
                m_gate = re.search(r'\((GATE-[A-Z0-9\-]+)\)', note)
                gate_label = m_gate.group(1) if m_gate else 'PASSED'
                lines.append(f"| `{gate_label}` | `{a.requirement_id}` | ✅ **PASS** | MINOR | {note[7:]} |")

    lines.append("")

    # 3. Requirement Traceability & Coverage Matrix
    lines.append("## 3. Requirement Traceability Matrix\n")
    lines.append("| Requirement ID | Domain / Service | Expected Outcome | Coverage Status | Mapped Test Count | Execution Evidence |")
    lines.append("| :--- | :--- | :--- | :---: | :---: | :---: |")

    for a in assessments:
        status_badge = "✅ COVERED" if a.coverage_status == CoverageStatus.COVERED else ("⚠️ PARTIAL" if a.coverage_status == CoverageStatus.PARTIALLY_COVERED else "❌ MISSING")
        exec_badge = a.execution_status.value
        lines.append(f"| `{a.requirement_id}` | {a.domain} / {a.service} | {a.title} | {status_badge} | {len(a.mapped_tests)} | `{exec_badge}` |")

    lines.append("")

    # 4. Coverage Gaps & Remediation Scenarios
    lines.append("## 4. Unmitigated Coverage Gaps & Actionable Remediation\n")
    gaps_found = False
    for a in assessments:
        if a.suggested_test_scenario:
            gaps_found = True
            sc = a.suggested_test_scenario
            lines.append(f"### Gap: `{a.requirement_id}` - {a.title}")
            lines.append(f"**Target Interface**: `{sc['target_interface']}` | **Severity**: `{sc['severity']}`")
            lines.append(f"\n**Suggested Test Scenario**: *{sc['title']}*\n")
            lines.append("**Recommended Verification Steps**:")
            for s in sc["steps"]:
                lines.append(f"- {s}")
            lines.append("")

    if not gaps_found:
        lines.append("*Zero coverage gaps. All required outcomes have corresponding test assertions.*\n")

    # 5. Smart Regression Selection (Capability B)
    if regression_decisions:
        lines.append("## 5. Requirement-Driven Regression Test Selection\n")
        if change_summary:
            lines.append(f"**Evaluated Change Context**: {change_summary}\n")

        lines.append("| Priority | Confidence | Test Name | In Regression Suite | Selection Rationale | Covered Requirements |")
        lines.append("| :---: | :---: | :--- | :---: | :--- | :--- |")

        for d in regression_decisions:
            in_reg = "Yes" if d.in_regression_suite else "**No (Outside)**"
            reqs = ", ".join(d.affected_requirement_ids)
            lines.append(f"| **{d.priority}** | {d.confidence} | `{d.title}` | {in_reg} | {'; '.join(d.selection_reasons)} | `{reqs}` |")

        lines.append("")

    # 6. Verification and Execution Notes
    lines.append("## 6. Audit Provenance & Operational Notes\n")
    lines.append("- **Deterministic Hard Gates**: Evaluated deterministically using machine-readable YAML policy rules in `gates/`.")
    lines.append("- **Assertion Depth**: Evaluated using AST structure to distinguish tests that genuinely assert outcomes from tests that merely visit endpoints.")
    lines.append(f"- **Execution Data**: {'Real test execution data queried from live infrastructure' if is_live_evidence else 'Test execution results loaded from verified fixture records'}.")

    return "\n".join(lines)
