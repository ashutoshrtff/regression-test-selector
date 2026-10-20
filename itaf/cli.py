#!/usr/bin/env python3
"""
itaf.cli - Unified Command-Line Interface for the Intelligent Test Assurance Framework.

Usage:
  itaf assess  [--feature-dir PATH] [--json]
  itaf select  --diff-file PATH [--feature-dir PATH]
  itaf gates   [--gates-dir PATH]
  itaf report  [--output PATH] [--json]
  itaf serve   [--port PORT]
"""

import argparse
import json
import os
import sys

# Ensure root workspace and skill directory are in sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)
SKILL_DIR = os.path.join(WORKSPACE_ROOT, ".github", "skills", "regression-test-selector")
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from itaf.ui.server import run_itaf_analysis, start_server
from itaf.engine.policy_engine import PolicyEngine
from itaf.engine.regression_selector import RegressionSelector
from itaf.reports.generator import generate_markdown_report
from itaf.core.models import CoverageStatus


def cmd_assess(args):
    """Executes requirement and coverage assessment."""
    data = run_itaf_analysis(sample_feature_dir=args.feature_dir)
    assessments = data["assessments"]

    total = len(assessments)
    covered = sum(1 for a in assessments if a.coverage_status == CoverageStatus.COVERED)
    partial = sum(1 for a in assessments if a.coverage_status == CoverageStatus.PARTIALLY_COVERED)
    missing = sum(1 for a in assessments if a.coverage_status == CoverageStatus.MISSING_COVERAGE)
    failing_gates = sum(len(a.failing_gate_ids) for a in assessments)

    if args.json:
        print(json.dumps({
            "summary": {
                "total_requirements": total,
                "covered": covered,
                "partially_covered": partial,
                "missing": missing,
                "failing_gates": failing_gates
            },
            "assessments": [
                {
                    "requirement_id": a.requirement_id,
                    "title": a.title,
                    "coverage_status": a.coverage_status.value,
                    "failing_gate_ids": a.failing_gate_ids,
                    "execution_status": a.execution_status.value,
                    "mapped_test_count": len(a.mapped_tests),
                    "suggested_scenario": a.suggested_test_scenario
                }
                for a in assessments
            ]
        }, indent=2))
        return

    sys.stdout.write("\n====================================================================\n")
    sys.stdout.write("       ITAF: Intelligent Test Assurance Framework Summary\n")
    sys.stdout.write("====================================================================\n")
    sys.stdout.write(f"Total Applicable Requirements: {total}\n")
    sys.stdout.write(f"Fully Covered Requirements:    {covered} ({round(covered/total*100, 1) if total else 0}%)\n")
    sys.stdout.write(f"Partially Covered:             {partial}\n")
    sys.stdout.write(f"Missing Test Coverage:         {missing}\n")
    sys.stdout.write(f"Failing Mandatory Gates:       {failing_gates}\n")
    sys.stdout.write("--------------------------------------------------------------------\n")

    for a in assessments:
        status_tag = "[PASS]" if a.coverage_status == CoverageStatus.COVERED else ("[WARN]" if a.coverage_status == CoverageStatus.PARTIALLY_COVERED else "[FAIL]")
        sys.stdout.write(f"{status_tag} [{a.coverage_status.value}] {a.requirement_id}: {a.title}\n")
        if a.failing_gate_ids:
            sys.stdout.write(f"    FAILING GATES: {', '.join(a.failing_gate_ids)}\n")
        if a.suggested_test_scenario:
            sys.stdout.write(f"    ACTIONABLE GAP REMEDIATION: {a.suggested_test_scenario['title']}\n")
    sys.stdout.write("====================================================================\n\n")


def cmd_select(args):
    """Executes requirement-driven regression selection."""
    if not os.path.exists(args.diff_file):
        sys.stderr.write(f"Error: diff file not found: {args.diff_file}\n")
        sys.exit(1)

    # Read diff and extract fingerprints
    from scripts.extract_change_fingerprints import extract_fingerprints_from_diff
    with open(args.diff_file, "r", encoding="utf-8", errors="replace") as f:
        diff_text = f.read()
    fingerprints = extract_fingerprints_from_diff(diff_text)

    data = run_itaf_analysis(sample_feature_dir=args.feature_dir)
    selector = RegressionSelector(data["tests"])
    decisions, unmitigated_gaps, warnings = selector.select_tests_for_change(
        change_fingerprints=fingerprints,
        assessments=data["assessments"]
    )

    if args.json:
        print(json.dumps({
            "selected_tests": [
                {
                    "priority": d.priority,
                    "confidence": d.confidence,
                    "test_id": d.test_id,
                    "title": d.title,
                    "in_regression_suite": d.in_regression_suite,
                    "reasons": d.selection_reasons,
                    "affected_requirements": d.affected_requirement_ids
                }
                for d in decisions
            ],
            "unmitigated_gaps": unmitigated_gaps,
            "warning_notes": warnings
        }, indent=2))
        return

    sys.stdout.write("\n====================================================================\n")
    sys.stdout.write("      ITAF: Requirement-Driven Regression Selection\n")
    sys.stdout.write("====================================================================\n")
    if warnings:
        sys.stdout.write("⚠️  WARNING: Unmitigated requirement impact detected:\n")
        for w in warnings:
            sys.stdout.write(f"   • {w}\n")
        sys.stdout.write("--------------------------------------------------------------------\n")

    sys.stdout.write(f"Total Selected Tests: {len(decisions)}\n")
    for d in decisions:
        in_reg = "Yes" if d.in_regression_suite else "NO (Outside Suite)"
        sys.stdout.write(f"[{d.priority}] ({d.confidence} Confidence) {d.title} (In Reg Suite: {in_reg})\n")
        sys.stdout.write(f"    Reasons: {'; '.join(d.selection_reasons)}\n")
    sys.stdout.write("====================================================================\n\n")


def cmd_gates(args):
    """Inspects and validates quality gate rules."""
    engine = PolicyEngine(gates_dir=args.gates_dir)
    sys.stdout.write(f"Loaded {len(engine.rules)} quality gate rules from {engine.gates_dir}:\n")
    for rule_id, rule in sorted(engine.rules.items()):
        mandatory_str = "MANDATORY" if rule.mandatory else "RECOMMENDED"
        sys.stdout.write(f"• [{rule.severity.value}] {rule_id}: {rule.name} ({mandatory_str}, Category: {rule.category})\n")
    if engine.validation_errors:
        sys.stderr.write(f"\nRule validation errors ({len(engine.validation_errors)}):\n")
        for err in engine.validation_errors:
            sys.stderr.write(f"  - {err}\n")


def cmd_report(args):
    """Generates an audit report."""
    data = run_itaf_analysis()
    report_md = generate_markdown_report(data["assessments"])
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report_md)
        sys.stderr.write(f"Report exported to {args.output}\n")
    else:
        print(report_md)


def cmd_serve(args):
    """Starts interactive UI server."""
    start_server(port=args.port)


def main():
    parser = argparse.ArgumentParser(description="ITAF - Intelligent Test Assurance Framework CLI")
    subparsers = parser.add_subparsers(dest="command", help="ITAF command to execute")

    # assess
    p_assess = subparsers.add_parser("assess", help="Assess requirement and quality gate coverage")
    p_assess.add_argument("--feature-dir", type=str, help="Path to feature directory containing specifications")
    p_assess.add_argument("--json", action="store_true", help="Output JSON format")

    # select
    p_select = subparsers.add_parser("select", help="Select regression tests based on change and requirements")
    p_select.add_argument("--diff-file", type=str, required=True, help="Unified diff file representing code change")
    p_select.add_argument("--feature-dir", type=str, help="Path to feature directory")
    p_select.add_argument("--json", action="store_true", help="Output JSON format")

    # gates
    p_gates = subparsers.add_parser("gates", help="Validate and list quality gate rules")
    p_gates.add_argument("--gates-dir", type=str, help="Custom path to gates directory")

    # report
    p_report = subparsers.add_parser("report", help="Generate audit-ready test assurance report")
    p_report.add_argument("--output", type=str, help="Output file path (default stdout)")

    # serve
    p_serve = subparsers.add_parser("serve", help="Launch interactive web dashboard")
    p_serve.add_argument("--port", type=int, default=8080, help="Web server port (default: 8080)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "assess":
        cmd_assess(args)
    elif args.command == "select":
        cmd_select(args)
    elif args.command == "gates":
        cmd_gates(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "serve":
        cmd_serve(args)


if __name__ == "__main__":
    main()
