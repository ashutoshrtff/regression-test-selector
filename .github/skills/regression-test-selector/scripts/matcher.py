#!/usr/bin/env python3
"""
matcher.py - Rule-based matching and ranking engine for regression test selection.

Applies evidence tiers (Tier 1 to Tier 5), risk widening rules, coverage gap detection,
and strict index validation. Standard library only (Python 3.9+).
"""

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple


def match_and_rank_tests(
    fingerprints: Dict[str, Any],
    test_index: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
    cr_summary: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ranks tests against change fingerprints using multi-tier evidence.
    Enforces strict index presence validation (never hallucinating test names).
    """
    config = config or {}
    all_tests = test_index.get("tests", [])
    valid_test_ids = {t["id"]: t for t in all_tests}

    change_endpoints = {ep.split(" ", 1)[-1] for ep in fingerprints.get("endpoints", [])}
    change_routes = set(fingerprints.get("routes", []))
    change_ui_labels = {lbl.lower() for lbl in fingerprints.get("ui_labels", [])}
    change_jira_keys = set(fingerprints.get("jira_keys", []))
    change_dto_fields = {f.lower() for f in fingerprints.get("dto_fields", [])}
    change_error_codes = set(fingerprints.get("error_codes", []))
    risk_signals = fingerprints.get("risk_signals", [])

    must_run: List[Dict[str, Any]] = []
    should_run: List[Dict[str, Any]] = []
    covered_endpoints: Set[str] = set()
    covered_routes: Set[str] = set()
    covered_ui_labels: Set[str] = set()

    # Track already selected IDs to prevent duplicates
    selected_ids: Set[str] = set()

    for test in all_tests:
        test_id = test["id"]
        test_title = test.get("title", "")
        test_jira = set(test.get("jira_keys", []))
        test_endpoints = {ep.split(" ", 1)[-1] for ep in test.get("endpoints_called", [])}
        test_routes = set(test.get("routes_visited", []))
        test_labels = {lbl.lower() for lbl in test.get("ui_labels", [])}
        page_objects = set(test.get("page_objects_used", []))

        evidence_tiers: List[str] = []
        reasons: List[str] = []

        # 1. Tier 1: Direct Reference (Endpoint, Route, UI Label, or Error Code)
        endpoint_intersection = change_endpoints.intersection(test_endpoints)
        if endpoint_intersection:
            evidence_tiers.append("Tier 1 (Direct Endpoint)")
            reasons.append(f"Exercises modified endpoint(s): {', '.join(sorted(endpoint_intersection))}")
            covered_endpoints.update(endpoint_intersection)

        route_intersection = change_routes.intersection(test_routes)
        if route_intersection:
            evidence_tiers.append("Tier 1 (Direct Route)")
            reasons.append(f"Visits modified route(s): {', '.join(sorted(route_intersection))}")
            covered_routes.update(route_intersection)

        label_intersection = change_ui_labels.intersection(test_labels)
        if label_intersection:
            evidence_tiers.append("Tier 1 (UI Selector)")
            reasons.append(f"Targets modified UI element(s): {', '.join(sorted(label_intersection))}")
            covered_ui_labels.update(label_intersection)

        # Direct Error Code / DTO field in title
        for err in change_error_codes:
            if err in test_title:
                evidence_tiers.append("Tier 1 (Error Code)")
                reasons.append(f"Verifies error condition: {err}")

        for dto in change_dto_fields:
            if dto in test_title.lower():
                evidence_tiers.append("Tier 1 (DTO Field)")
                reasons.append(f"Exercises changed field: {dto}")

        # 2. Tier 2: Jira Key Match
        jira_intersection = change_jira_keys.intersection(test_jira)
        if jira_intersection:
            evidence_tiers.append("Tier 2 (Jira Match)")
            reasons.append(f"Linked to Jira ticket(s): {', '.join(sorted(jira_intersection))}")

        # 3. Tier 4: Page Object / Shared Helper Path
        # If test uses a page object that covers changed routes/endpoints
        if not (endpoint_intersection or route_intersection) and page_objects:
            # Check if any change route/endpoint is in page object
            for po in page_objects:
                for cr in change_routes:
                    if cr in test_routes:
                        evidence_tiers.append("Tier 4 (Page Object Path)")
                        reasons.append(f"Indirectly exercises route {cr} via Page Object {po}")
                        break

        # 4. Tier 5: Semantic / Keyword similarity (fallback)
        if not evidence_tiers:
            # Check for payment / auth / refund keyword overlap
            for kw in ["payment", "checkout", "auth", "login", "refund", "report"]:
                if any(kw in f.lower() for f in fingerprints.get("files_changed", [])) and kw in test_title.lower():
                    evidence_tiers.append("Tier 5 (Semantic)")
                    reasons.append(f"Semantic match on domain keyword '{kw}' (Advisory fallback; direct interface and outcome unverified)")
                    break

        if not evidence_tiers:
            continue

        # Determine Confidence and Category
        is_tier_1 = any(t.startswith("Tier 1") for t in evidence_tiers)
        is_tier_2 = any(t.startswith("Tier 2") for t in evidence_tiers)
        is_tier_4 = any(t.startswith("Tier 4") for t in evidence_tiers)
        is_tier_5 = any(t.startswith("Tier 5") for t in evidence_tiers)

        if is_tier_1 or (is_tier_2 and len(evidence_tiers) > 1):
            confidence = "High"
            category = "must_run"
        elif is_tier_2 or is_tier_4:
            confidence = "Medium"
            category = "must_run" if is_tier_2 else "should_run"
        else:
            confidence = "Low"
            category = "should_run"

        entry = {
            "id": test_id,
            "title": test_title,
            "file": test.get("file", ""),
            "line": test.get("line", 0),
            "in_regression_suite": test.get("in_regression_suite", False),
            "evidence_tier": evidence_tiers[0],
            "all_evidence": evidence_tiers,
            "confidence": confidence,
            "reason": "; ".join(reasons)
        }

        if category == "must_run":
            must_run.append(entry)
        else:
            should_run.append(entry)
        selected_ids.add(test_id)

    # 5. Risk Widening: check risk signals
    smoke_triggered = False
    smoke_reasons: List[str] = []
    full_run_recommended = False

    if risk_signals:
        smoke_triggered = True
        for sig in risk_signals:
            smoke_reasons.append(f"{sig.get('category')}: {sig.get('explanation')}")

        if len(risk_signals) >= 3 or any(s.get("category") == "database_migrations" for s in risk_signals):
            full_run_recommended = True

    smoke_tests_added: List[Dict[str, Any]] = []
    if smoke_triggered:
        for test in all_tests:
            if test.get("in_smoke_suite") and test["id"] not in selected_ids:
                entry = {
                    "id": test["id"],
                    "title": test.get("title", ""),
                    "file": test.get("file", ""),
                    "line": test.get("line", 0),
                    "in_regression_suite": test.get("in_regression_suite", False),
                    "evidence_tier": "Risk Widening (Smoke)",
                    "all_evidence": ["Risk Widening (Smoke)"],
                    "confidence": "Medium",
                    "reason": f"Activated by risk widening trigger: {', '.join([s.get('category','') for s in risk_signals])}"
                }
                should_run.append(entry)
                smoke_tests_added.append(entry)
                selected_ids.add(test["id"])

    # 6. Strict Validation Guardrail: Ensure every recommended test exists in valid_test_ids
    all_recommended = must_run + should_run
    for t in all_recommended:
        if t["id"] not in valid_test_ids:
            raise ValueError(f"[CRITICAL ERROR] Hallucinated or non-existent test recommended: {t['id']}")

    # 7. Coverage Gaps Identification
    coverage_gaps: List[Dict[str, Any]] = []
    uncovered_endpoints = change_endpoints - covered_endpoints
    for ep in sorted(uncovered_endpoints):
        coverage_gaps.append({
            "target": ep,
            "type": "endpoint",
            "suggested_title": f"Verify behavior of modified endpoint: {ep}",
            "suggested_steps": [
                f"1. Send valid request payload to {ep} and verify HTTP 200 response.",
                f"2. Send invalid or expired parameters to {ep} and verify appropriate error response.",
                f"3. Verify database persistence and audit log entry."
            ]
        })

    uncovered_routes = change_routes - covered_routes
    for rt in sorted(uncovered_routes):
        coverage_gaps.append({
            "target": rt,
            "type": "route",
            "suggested_title": f"End-to-end journey for view route: {rt}",
            "suggested_steps": [
                f"1. Navigate to {rt} in supported browser viewports.",
                f"2. Complete primary user workflow submission.",
                f"3. Verify redirection and confirmation UI elements."
            ]
        })

    # 8. Time Savings and Stats
    total_suite_count = len(all_tests)
    selected_count = len(selected_ids)
    tests_skipped = max(0, total_suite_count - selected_count)
    avg_test_duration_sec = config.get("avg_test_duration_seconds", 45)
    total_suite_time_sec = total_suite_count * avg_test_duration_sec
    selected_suite_time_sec = selected_count * avg_test_duration_sec
    time_saved_sec = max(0, total_suite_time_sec - selected_suite_time_sec)
    time_saved_min = round(time_saved_sec / 60, 1)

    # 9. Generate Run Command
    framework = test_index.get("meta", {}).get("framework", "playwright-ts")
    run_cmd = generate_run_command(all_recommended, framework, config)

    # Build report sections
    return {
        "cr_summary": cr_summary or "Behavioral change analysis across modified components.",
        "must_run": must_run,
        "should_run": should_run,
        "smoke_triggered": smoke_triggered,
        "smoke_reasons": smoke_reasons,
        "full_run_recommended": full_run_recommended,
        "coverage_gaps": coverage_gaps,
        "insufficient_evidence": get_insufficient_evidence_notes(fingerprints, all_recommended),
        "stats": {
            "total_suite_count": total_suite_count,
            "selected_count": selected_count,
            "tests_skipped": tests_skipped,
            "reduction_pct": f"{(tests_skipped / total_suite_count * 100):.1f}%" if total_suite_count > 0 else "0%",
            "estimated_time_saved_minutes": time_saved_min,
            "estimated_run_time_minutes": round(selected_suite_time_sec / 60, 1)
        },
        "run_command": run_cmd
    }


def get_insufficient_evidence_notes(fingerprints: Dict[str, Any], selected_tests: List[Dict[str, Any]]) -> List[str]:
    """Identifies ambiguous areas requiring manual engineer verification."""
    notes = []
    if fingerprints.get("feature_flags"):
        notes.append(
            f"Feature flag(s) touched: {', '.join(fingerprints['feature_flags'])}. "
            "Automated test suite may run with static flag config; verify behavior with both flag ON and OFF."
        )
    if fingerprints.get("config_keys"):
        notes.append(
            f"Configuration key(s) modified: {', '.join(fingerprints['config_keys'])}. "
            "Ensure staging deployment environment variables match production secrets."
        )
    if not fingerprints.get("jira_keys"):
        notes.append(
            "No Jira ticket keys detected in commits or diff. Matching relied solely on technical fingerprints."
        )
    if not selected_tests:
        notes.append(
            "Zero matching automated tests found for this change. Thorough manual regression exploration recommended."
        )
    return notes


def generate_run_command(selected_tests: List[Dict[str, Any]], framework: str, config: Dict[str, Any]) -> str:
    """Generates ready-to-run terminal command for selected tests."""
    if not selected_tests:
        return "# No matching automated tests selected. Manual exploratory testing or writing a new test recommended."

    custom_tmpl = config.get("run_command_template")

    if framework == "playwright-ts":
        titles = [t["title"].split(" > ")[-1] for t in selected_tests]
        # Clean regex special chars for grep
        clean_grep = "|".join([re.escape(re.sub(r'@[a-zA-Z0-9_\-]+', '', t).strip()) for t in titles])
        if len(clean_grep) > 500:
            # Fallback to files if grep string becomes too long
            files = sorted(list({t["file"] for t in selected_tests}))
            return f"npx playwright test {' '.join(files)}"
        if custom_tmpl:
            return custom_tmpl.replace("{grep}", clean_grep)
        return f'npx playwright test --grep "{clean_grep}"'

    elif framework == "selenium-java":
        # Group by class or method for maven surefire
        methods = []
        for t in selected_tests:
            # ID format: path:line:ClassName.methodName
            parts = t["id"].split(":")
            if len(parts) >= 3 and "." in parts[2]:
                methods.append(parts[2])
        if methods:
            joined = ",".join(methods)
            if custom_tmpl:
                return custom_tmpl.replace("{test_names}", joined)
            return f"mvn test -Dtest={joined}"
        return "mvn test -Dgroups=regression,smoke"

    return "npx playwright test"


def format_markdown_report(analysis: Dict[str, Any]) -> str:
    """Formats analysis dictionary into Markdown report conforming to templates/report.md."""
    lines: List[str] = []
    lines.append("# Regression Test Selector Report\n")

    # 1. CR Summary
    lines.append("## 1. Change Request Summary\n")
    lines.append(f"{analysis.get('cr_summary')}\n")

    # 2. Must Run
    must_run = analysis.get("must_run", [])
    lines.append("## 2. Must Run Tests\n")
    if must_run:
        lines.append("| Test Name | In Regression Suite | Evidence Tier | Confidence | Reason |")
        lines.append("| :--- | :---: | :---: | :---: | :--- |")
        for t in must_run[:25]:
            in_reg = "Yes" if t.get("in_regression_suite") else "**No (Outside)**"
            title = t.get("title", "").replace("|", "-")
            lines.append(f"| `{title}` | {in_reg} | {t.get('evidence_tier')} | {t.get('confidence')} | {t.get('reason')} |")
        if len(must_run) > 25:
            lines.append(f"\n*... and {len(must_run) - 25} more test(s) selected.*")
    else:
        lines.append("*No tests categorized as Must Run.*\n")
    lines.append("")

    # 3. Should Run
    should_run = analysis.get("should_run", [])
    lines.append("## 3. Should Run Tests\n")
    if should_run:
        lines.append("| Test Name | In Regression Suite | Evidence Tier | Confidence | Reason |")
        lines.append("| :--- | :---: | :---: | :---: | :--- |")
        for t in should_run[:25]:
            in_reg = "Yes" if t.get("in_regression_suite") else "**No (Outside)**"
            title = t.get("title", "").replace("|", "-")
            lines.append(f"| `{title}` | {in_reg} | {t.get('evidence_tier')} | {t.get('confidence')} | {t.get('reason')} |")
        if len(should_run) > 25:
            lines.append(f"\n*... and {len(should_run) - 25} more test(s) selected.*")
    else:
        lines.append("*No tests categorized as Should Run.*\n")
    lines.append("")

    # 4. Smoke / Full-Run Trigger
    lines.append("## 4. Risk Widening & Smoke Triggers\n")
    if analysis.get("smoke_triggered"):
        lines.append("> [!WARNING] **Risk Widening Activated**")
        for r in analysis.get("smoke_reasons", []):
            lines.append(f"> - {r}")
        if analysis.get("full_run_recommended"):
            lines.append("\n> [!CAUTION] **Full Suite Run Recommended**: Multiple critical risk triggers fired.")
    else:
        lines.append("No risk widening rules triggered. Standard selective regression applies.\n")
    lines.append("")

    # 5. Coverage Gaps
    gaps = analysis.get("coverage_gaps", [])
    lines.append("## 5. Coverage Gaps\n")
    if gaps:
        for g in gaps:
            lines.append(f"### Gap: `{g.get('target')}` ({g.get('type')})")
            lines.append(f"**Suggested Test Scenario**: {g.get('suggested_title')}\n")
            lines.append("**Recommended Steps**:")
            for s in g.get("suggested_steps", []):
                lines.append(f"- {s}")
            lines.append("")
    else:
        lines.append("No coverage gaps detected. All touched endpoints/routes have corresponding automated tests.\n")

    # 6. Insufficient Evidence
    notes = analysis.get("insufficient_evidence", [])
    lines.append("## 6. Insufficient Evidence & Human Verification Items\n")
    if notes:
        for n in notes:
            lines.append(f"- {n}")
    else:
        lines.append("- All required technical evidence was conclusively resolved from the repository diff.\n")
    lines.append("")

    # 7. Stats
    stats = analysis.get("stats", {})
    lines.append("## 7. Execution Statistics & Estimated Impact\n")
    lines.append(f"- **Total Automation Suite Size**: {stats.get('total_suite_count')} tests")
    lines.append(f"- **Selected Tests**: {stats.get('selected_count')} tests")
    lines.append(f"- **Tests Skipped Safely**: {stats.get('tests_skipped')} tests ({stats.get('reduction_pct')} reduction)")
    lines.append(f"- **Estimated Time Saved**: ~{stats.get('estimated_time_saved_minutes')} minutes")
    lines.append(f"- **Estimated Run Duration**: ~{stats.get('estimated_run_time_minutes')} minutes\n")

    # 8. Ready-to-paste run command
    lines.append("## 8. Ready-to-paste Execution Command\n")
    lines.append("```bash")
    lines.append(analysis.get("run_command", ""))
    lines.append("```\n")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Match change fingerprints to test index and generate ranking report.")
    parser.add_argument("--fingerprints", type=str, required=True, help="Path to fingerprints JSON file.")
    parser.add_argument("--index", type=str, required=True, help="Path to test index JSON file.")
    parser.add_argument("--config", type=str, help="Path to rts.config.yml or JSON.")
    parser.add_argument("--cr-summary", type=str, help="Plain English CR summary string.")
    parser.add_argument("--output", type=str, help="Output markdown or JSON file. Defaults to stdout.")
    parser.add_argument("--json", action="store_true", help="Output raw JSON analysis instead of Markdown.")

    args = parser.parse_args()

    def read_json_file(path: str) -> Any:
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except UnicodeDecodeError:
            with open(path, "r", encoding="utf-16") as f:
                return json.load(f)

    fingerprints = read_json_file(args.fingerprints)
    test_index = read_json_file(args.index)

    config = {}
    if args.config and os.path.exists(args.config):
        # Light yaml/json parse
        with open(args.config, "r", encoding="utf-8") as f:
            raw = f.read()
            try:
                config = json.loads(raw)
            except Exception:
                # simple key-value parser for basic yml
                for line in raw.splitlines():
                    if ":" in line and not line.strip().startswith("#"):
                        k, v = line.split(":", 1)
                        config[k.strip()] = v.strip().strip('"\'')

    analysis = match_and_rank_tests(
        fingerprints=fingerprints,
        test_index=test_index,
        config=config,
        cr_summary=args.cr_summary
    )

    if args.json:
        output_content = json.dumps(analysis, indent=2)
    else:
        output_content = format_markdown_report(analysis)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_content)
        sys.stderr.write(f"Report written to {args.output}\n")
    else:
        print(output_content)


if __name__ == "__main__":
    main()
