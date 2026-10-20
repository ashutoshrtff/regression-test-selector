#!/usr/bin/env python3
"""
backtest.py - Backtest test selection pipeline against past PR diffs and known defects.

Computes precision/recall, suite reduction, and estimated engineering time saved.
Standard library only (Python 3.9+).
"""

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Import internal modules
sys.path.insert(0, os.path.dirname(__file__))
from extract_change_fingerprints import extract_fingerprints_from_diff
from matcher import match_and_rank_tests


def load_known_defects(filepath: str) -> Dict[str, List[str]]:
    """Loads known defect mapping from CSV or JSON (PR ID -> List of Test IDs/Patterns)."""
    mapping: Dict[str, List[str]] = {}

    if filepath.endswith(".json"):
        with open(filepath, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
            # Expecting {"pr_id": ["test_id1", ...]} or list of dicts
            if isinstance(raw, dict):
                return raw
            elif isinstance(raw, list):
                for item in raw:
                    pr = str(item.get("pr_id") or item.get("pr"))
                    test = item.get("test_id") or item.get("test")
                    mapping.setdefault(pr, []).append(test)
    else:
        # CSV parsing
        with open(filepath, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pr = row.get("pr_id") or row.get("pr") or row.get("PR")
                test = row.get("test_id") or row.get("test") or row.get("TEST")
                if pr and test:
                    mapping.setdefault(pr.strip(), []).append(test.strip())

    return mapping


def run_backtest(
    diffs_dir: str,
    index_file: str,
    known_defects_file: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    avg_duration_sec: int = 45
) -> Dict[str, Any]:
    """Runs the selector across all diffs in diffs_dir and benchmarks performance."""
    # Load test index
    with open(index_file, "r", encoding="utf-8-sig") as f:
        test_index = json.load(f)

    total_tests_in_suite = len(test_index.get("tests", []))
    known_defects = load_known_defects(known_defects_file) if known_defects_file else {}

    diff_files = [
        f for f in sorted(os.listdir(diffs_dir))
        if f.endswith(".diff") or f.endswith(".patch")
    ]

    if not diff_files:
        raise FileNotFoundError(f"No .diff or .patch files found in {diffs_dir}")

    pr_results: List[Dict[str, Any]] = []
    total_selected_count = 0
    total_known_defects = 0
    caught_defects = 0
    missed_defects = 0

    for df in diff_files:
        possible_keys = [df, Path(df).stem]
        m = re.search(r'pr[-_]?(\d+)', df, re.IGNORECASE)
        if m:
            num = m.group(1)
            possible_keys.extend([num, f"pr-{num}", f"pr_{num}", f"PR-{num}"])
            pr_id = f"pr-{num}"
        else:
            pr_id = df

        diff_path = os.path.join(diffs_dir, df)
        with open(diff_path, "r", encoding="utf-8", errors="replace") as f:
            diff_text = f.read()

        fingerprints = extract_fingerprints_from_diff(diff_text)
        analysis = match_and_rank_tests(fingerprints, test_index, config=config)

        selected = analysis["must_run"] + analysis["should_run"]
        selected_ids = {t["id"] for t in selected}
        selected_titles = {t["title"] for t in selected}

        # Check known defects for this PR
        expected_tests = []
        for k in possible_keys:
            if k in known_defects:
                expected_tests.extend(known_defects[k])
                break

        pr_defects_total = len(expected_tests)
        pr_defects_caught = 0

        for exp in expected_tests:
            total_known_defects += 1
            # Check if exp matches any selected ID or title substring
            matched = any(exp in sid or exp in stitle for sid, stitle in zip(selected_ids, selected_titles))
            if matched:
                caught_defects += 1
                pr_defects_caught += 1
            else:
                missed_defects += 1

        selected_count = len(selected)
        total_selected_count += selected_count
        reduction_pct = (
            ((total_tests_in_suite - selected_count) / total_tests_in_suite * 100)
            if total_tests_in_suite > 0 else 0
        )
        time_saved_min = round((total_tests_in_suite - selected_count) * avg_duration_sec / 60, 1)

        # Compute per-PR confusion matrix metrics
        tp = pr_defects_caught
        fn = pr_defects_total - pr_defects_caught
        fp = max(0, selected_count - tp)
        non_defect_tests = max(0, total_tests_in_suite - pr_defects_total)
        tn = max(0, non_defect_tests - fp)

        pr_precision = (tp / (tp + fp) * 100) if (tp + fp) > 0 else 0.0
        pr_recall = (tp / (tp + fn) * 100) if (tp + fn) > 0 else 100.0

        pr_results.append({
            "diff_file": df,
            "pr_id": pr_id,
            "selected_tests_count": selected_count,
            "suite_reduction_pct": f"{reduction_pct:.1f}%",
            "time_saved_minutes": time_saved_min,
            "known_defects_total": pr_defects_total,
            "known_defects_caught": pr_defects_caught,
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "true_negatives": tn,
            "precision_pct": f"{pr_precision:.1f}%",
            "recall_pct": f"{pr_recall:.1f}%",
            "coverage_gaps_count": len(analysis.get("coverage_gaps", [])),
            "smoke_triggered": analysis.get("smoke_triggered", False)
        })

    num_prs = len(diff_files)
    mean_selected = round(total_selected_count / num_prs, 1) if num_prs > 0 else 0
    mean_reduction_pct = (
        ((total_tests_in_suite - mean_selected) / total_tests_in_suite * 100)
        if total_tests_in_suite > 0 else 0
    )
    total_time_saved_min = round(
        sum(r["time_saved_minutes"] for r in pr_results), 1
    )
    recall_rate_pct = (
        (caught_defects / total_known_defects * 100)
        if total_known_defects > 0 else 100.0
    )
    total_tp = sum(r["true_positives"] for r in pr_results)
    total_fp = sum(r["false_positives"] for r in pr_results)
    total_fn = sum(r["false_negatives"] for r in pr_results)
    total_tn = sum(r["true_negatives"] for r in pr_results)
    overall_precision_pct = (
        (total_tp / (total_tp + total_fp) * 100)
        if (total_tp + total_fp) > 0 else 0.0
    )

    return {
        "summary": {
            "dataset_type": "SYNTHETIC_FIXTURE_DATASET",
            "total_prs_analyzed": num_prs,
            "full_suite_tests": total_tests_in_suite,
            "mean_selected_tests": mean_selected,
            "mean_suite_reduction": f"{mean_reduction_pct:.1f}%",
            "total_engineering_time_saved_minutes": total_time_saved_min,
            "known_defects_tested": total_known_defects,
            "known_defects_caught": caught_defects,
            "known_defects_missed": missed_defects,
            "true_positives": total_tp,
            "false_positives": total_fp,
            "false_negatives": total_fn,
            "true_negatives": total_tn,
            "recall_rate": f"{recall_rate_pct:.1f}%",
            "precision_rate": f"{overall_precision_pct:.1f}%",
            "assumptions": f"Assumes average test duration of {avg_duration_sec}s per test across single-threaded run.",
            "limitations": [
                "Small synthetic fixture dataset (5 diffs, 5 fake tests)",
                "Historical recall measured against configured known defects CSV",
                "Does not reflect multi-tenant production CI execution variability"
            ]
        },
        "per_pr_breakdown": pr_results
    }


def format_backtest_table(results: Dict[str, Any]) -> str:
    """Formats backtest benchmark results into Markdown table."""
    summary = results["summary"]
    breakdown = results["per_pr_breakdown"]

    lines = []
    lines.append("# Regression Test Selector: Historical Backtest Benchmark\n")
    lines.append("> [!NOTE] **Dataset Notice: Synthetic Fixtures**")
    lines.append(f"> Dataset: `{summary.get('dataset_type', 'FIXTURE')}` | {summary.get('assumptions', '')}\n")
    lines.append("## Executive Benchmark Summary\n")
    lines.append(f"- **Pull Requests Evaluated**: {summary['total_prs_analyzed']}")
    lines.append(f"- **Full Suite Size**: {summary['full_suite_tests']} tests")
    lines.append(f"- **Average Selected Tests per PR**: {summary['mean_selected_tests']} tests")
    lines.append(f"- **Average Test Suite Reduction**: **{summary['mean_suite_reduction']}**")
    lines.append(f"- **Total Time Saved Across Run**: ~{summary['total_engineering_time_saved_minutes']} minutes")
    lines.append(f"- **Defect Recall Rate**: **{summary['recall_rate']}** ({summary['known_defects_caught']}/{summary['known_defects_tested']} defects caught)")
    lines.append(f"- **Selection Precision**: **{summary.get('precision_rate', 'N/A')}** ({summary.get('true_positives', 0)} TP, {summary.get('false_positives', 0)} FP)")
    lines.append(f"- **False Negative Defect Escapes**: **{summary['known_defects_missed']}**\n")

    lines.append("## Per-Pull-Request Breakdown\n")
    lines.append("| PR / Diff | Selected | Suite Reduction | Time Saved | TP | FP | FN | Precision | Recall | Gaps Flagged |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")

    for pr in breakdown:
        lines.append(
            f"| `{pr['diff_file']}` | {pr['selected_tests_count']} | {pr['suite_reduction_pct']} | "
            f"~{pr['time_saved_minutes']} min | {pr.get('true_positives', 0)} | {pr.get('false_positives', 0)} | "
            f"{pr.get('false_negatives', 0)} | {pr.get('precision_pct', 'N/A')} | {pr.get('recall_pct', 'N/A')} | {pr['coverage_gaps_count']} |"
        )

    lines.append("\n## Methodological Limitations")
    for lim in summary.get("limitations", []):
        lines.append(f"- {lim}")

    return "\n".join(lines)
    lines.append(f"- **Full Suite Size**: {summary['full_suite_tests']} tests")
    lines.append(f"- **Average Selected Tests per PR**: {summary['mean_selected_tests']} tests")
    lines.append(f"- **Average Test Suite Reduction**: **{summary['mean_suite_reduction']}**")
    lines.append(f"- **Total Time Saved Across Run**: ~{summary['total_engineering_time_saved_minutes']} minutes")
    lines.append(f"- **Defect Recall Rate**: **{summary['recall_rate']}** ({summary['known_defects_caught']}/{summary['known_defects_tested']} defects caught)")
    lines.append(f"- **False Negative Defect Escapes**: **{summary['known_defects_missed']}**\n")

    lines.append("## Per-Pull-Request Breakdown\n")
    lines.append("| PR / Diff | Selected | Suite Reduction | Time Saved | Defects Caught | Smoke Triggered | Gaps Flagged |")
    lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")

    for pr in breakdown:
        defects_str = f"{pr['known_defects_caught']}/{pr['known_defects_total']}" if pr['known_defects_total'] > 0 else "N/A"
        smoke_str = "Yes" if pr["smoke_triggered"] else "No"
        lines.append(
            f"| `{pr['diff_file']}` | {pr['selected_tests_count']} | {pr['suite_reduction_pct']} | "
            f"~{pr['time_saved_minutes']} min | {defects_str} | {smoke_str} | {pr['coverage_gaps_count']} |"
        )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run backtest evaluation of regression-test-selector against PR diffs.")
    parser.add_argument("--diffs-dir", type=str, required=True, help="Directory containing .diff or .patch files.")
    parser.add_argument("--index", type=str, required=True, help="Path to test index JSON file.")
    parser.add_argument("--known-defects", type=str, help="Path to known defects CSV or JSON mapping.")
    parser.add_argument("--avg-duration-sec", type=int, default=45, help="Average test duration in seconds (default: 45).")
    parser.add_argument("--output", type=str, help="Output file path (default: stdout).")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of Markdown.")

    args = parser.parse_args()

    try:
        results = run_backtest(
            diffs_dir=args.diffs_dir,
            index_file=args.index,
            known_defects_file=args.known_defects,
            avg_duration_sec=args.avg_duration_sec
        )
    except Exception as e:
        sys.stderr.write(f"Error during backtest: {e}\n")
        sys.exit(1)

    if args.json:
        out_content = json.dumps(results, indent=2)
    else:
        out_content = format_backtest_table(results)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out_content)
        sys.stderr.write(f"Backtest report written to {args.output}\n")
    else:
        print(out_content)


if __name__ == "__main__":
    main()
