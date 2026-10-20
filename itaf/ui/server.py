#!/usr/bin/env python3
"""
itaf.ui.server - Lightweight, Zero-Dependency Bank-Grade Quality Engineering Web Server.

Serves the 5-screen interactive ITAF UI and provides REST APIs for coverage intelligence,
hard gate outcomes, and requirement-driven regression selection using standard library http.server.
"""

import json
import mimetypes
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

# Ensure root workspace and skill scripts are in sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)
SKILL_DIR = os.path.join(WORKSPACE_ROOT, ".github", "skills", "regression-test-selector")
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)

from itaf.parsers import OpenAPIParser, FeatureParser, MessageFormatParser
from itaf.engine import PolicyEngine, TestDiscoveryEngine, CrossRepoMapper, CoverageIntelligenceEngine, RegressionSelector
from itaf.reports.generator import generate_markdown_report
from itaf.core.models import CoverageStatus

from itaf.core.cache import GLOBAL_ARTIFACT_CACHE

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def run_itaf_analysis(sample_feature_dir: Optional[str] = None):
    """Executes the end-to-end assurance pipeline against sample or configured feature files."""
    feature_dir = sample_feature_dir or os.path.join(WORKSPACE_ROOT, "examples", "sample_feature")
    openapi_file = os.path.join(feature_dir, "payment-api.v1.yaml")
    feature_file = os.path.join(feature_dir, "payment-submission-feature.md")
    message_file = os.path.join(feature_dir, "swift-pacs008-payment.json")
    evidence_file = os.path.join(feature_dir, "execution-evidence.json")
    test_repo_dir = feature_dir # Contains tests/payments/payment-submission.spec.ts

    # 1. Parse requirements with incremental artifact hashing cache
    requirements = []
    if os.path.exists(openapi_file):
        requirements.extend(GLOBAL_ARTIFACT_CACHE.get_or_compute(
            openapi_file, lambda: OpenAPIParser(openapi_file).parse()
        ))
    if os.path.exists(feature_file):
        requirements.extend(GLOBAL_ARTIFACT_CACHE.get_or_compute(
            feature_file, lambda: FeatureParser(feature_file).parse()
        ))
    if os.path.exists(message_file):
        requirements.extend(GLOBAL_ARTIFACT_CACHE.get_or_compute(
            message_file, lambda: MessageFormatParser(message_file).parse()
        ))

    # 2. Discover tests
    tests = {}
    if os.path.exists(test_repo_dir):
        tests = TestDiscoveryEngine(test_repo_dir).discover_all_tests()

    # Fallback to playwright fixture repo if sample_feature has no tests
    if not tests:
        pw_dir = os.path.join(WORKSPACE_ROOT, ".github", "skills", "regression-test-selector", "examples", "fixtures", "fake-automation-repo", "playwright")
        if os.path.exists(pw_dir):
            tests = TestDiscoveryEngine(pw_dir).discover_all_tests()

    # 3. Load execution evidence
    evidence = {}
    if os.path.exists(evidence_file):
        with open(evidence_file, "r", encoding="utf-8") as f:
            evidence = json.load(f)

    # 4. Run Policy & Coverage Engines
    policy_engine = PolicyEngine()
    mapper = CrossRepoMapper()
    coverage_engine = CoverageIntelligenceEngine(policy_engine, mapper)
    assessments = coverage_engine.assess_coverage(requirements, tests, evidence)

    return {
        "requirements": requirements,
        "tests": tests,
        "assessments": assessments,
        "evidence": evidence
    }


class ITAFRequestHandler(BaseHTTPRequestHandler):
    """Handles static assets and API requests for the quality engineering workspace."""

    def log_message(self, format, *args):
        # Human-friendly logging to stderr
        sys.stderr.write(f"[ITAF Server] {args[0]} {args[1]}\n")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self._serve_file(os.path.join(STATIC_DIR, "index.html"), "text/html")
        elif path.startswith("/static/"):
            rel_path = path[8:].lstrip("/\\")
            # Enforce path traversal protection
            clean_rel = os.path.normpath(rel_path)
            full_path = os.path.abspath(os.path.join(STATIC_DIR, clean_rel))
            try:
                common = os.path.commonpath([STATIC_DIR, full_path])
                if common != STATIC_DIR:
                    self.send_error(403, "Access forbidden: Path traversal detected")
                    return
            except ValueError:
                self.send_error(403, "Access forbidden")
                return

            mime_type, _ = mimetypes.guess_type(full_path)
            self._serve_file(full_path, mime_type or "application/octet-stream")
        elif path == "/api/status":
            self._json_response({"status": "ONLINE", "version": "2.0.0", "framework": "ITAF"})
        elif path == "/api/assessments":
            self._handle_get_assessments()
        elif path == "/api/report":
            self._handle_get_report()
        else:
            self.send_error(404, "Endpoint not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/select-regression":
            self._handle_select_regression()
        else:
            self.send_error(404, "Endpoint not found")

    def _serve_file(self, filepath: str, content_type: str):
        if not os.path.exists(filepath):
            self.send_error(404, f"File not found: {filepath}")
            return
        with open(filepath, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(content)

    def _json_response(self, data: Any, status: int = 200):
        body = json.dumps(data, default=lambda o: getattr(o, '__dict__', str(o))).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def _handle_get_assessments(self):
        data = run_itaf_analysis()
        assessments = data["assessments"]

        total = len(assessments)
        covered = sum(1 for a in assessments if a.coverage_status == CoverageStatus.COVERED)
        partial = sum(1 for a in assessments if a.coverage_status == CoverageStatus.PARTIALLY_COVERED)
        missing = sum(1 for a in assessments if a.coverage_status == CoverageStatus.MISSING_COVERAGE)
        failing_gates = sum(len(a.failing_gate_ids) for a in assessments)

        summary = {
            "total_requirements": total,
            "covered_requirements": covered,
            "partially_covered": partial,
            "missing_coverage": missing,
            "failing_gates_count": failing_gates,
            "coverage_percentage": round((covered / total * 100), 1) if total > 0 else 0,
            "evidence_source": "FIXTURE_MOCK (Simulated/Local Test Data)"
        }

        # Convert assessments to serializable dicts
        serializable = []
        for a in assessments:
            serializable.append({
                "requirement_id": a.requirement_id,
                "title": a.title,
                "domain": a.domain,
                "service": a.service,
                "coverage_status": a.coverage_status.value,
                "failing_gate_ids": a.failing_gate_ids,
                "execution_status": a.execution_status.value,
                "assessment_notes": a.assessment_notes,
                "suggested_test_scenario": a.suggested_test_scenario,
                "mapped_tests": [
                    {
                        "requirement_id": m.requirement_id,
                        "test_id": m.test_id,
                        "confidence": m.confidence.value,
                        "evidence_summary": m.evidence_summary,
                        "asserts_outcome": m.asserts_outcome,
                        "mapping_source": m.mapping_source
                    }
                    for m in a.mapped_tests
                ]
            })

        self._json_response({"summary": summary, "assessments": serializable})

    def _handle_select_regression(self):
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > 2 * 1024 * 1024:
            self.send_error(413, "Payload Too Large: Maximum request body is 2MB")
            return
        raw_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            payload = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            self._json_response({"error": "Invalid JSON request body"}, status=400)
            return

        diff_file_raw = payload.get("diff_file", "pr-payment-retry-change.diff")
        # Sanitize filename against directory traversal
        diff_file_name = os.path.basename(str(diff_file_raw))

        # Resolve diff path safely within known allowed directories
        allowed_dirs = [
            os.path.join(WORKSPACE_ROOT, "examples", "sample_feature"),
            os.path.join(WORKSPACE_ROOT, ".github", "skills", "regression-test-selector", "examples", "fixtures", "dev-diffs")
        ]
        diff_path = None
        for adir in allowed_dirs:
            candidate = os.path.join(adir, diff_file_name)
            if os.path.exists(candidate):
                diff_path = candidate
                break

        from itaf.engine.regression_selector import RegressionSelector
        # Extract change fingerprints
        from scripts.extract_change_fingerprints import extract_fingerprints_from_diff
        fingerprints = {}
        if diff_path and os.path.exists(diff_path):
            with open(diff_path, "r", encoding="utf-8", errors="replace") as f:
                fingerprints = extract_fingerprints_from_diff(f.read())
        else:
            fingerprints = {"risk_signals": [{"category": "unknown_diff", "explanation": f"Diff file '{diff_file_name}' could not be located in allowed directories."}]}

        data = run_itaf_analysis()
        selector = RegressionSelector(data["tests"])
        decisions, unmitigated_gaps, warnings = selector.select_tests_for_change(
            change_fingerprints=fingerprints,
            assessments=data["assessments"]
        )

        serializable_decisions = [
            {
                "test_id": d.test_id,
                "title": d.title,
                "file_path": d.file_path,
                "framework": d.framework,
                "in_regression_suite": d.in_regression_suite,
                "priority": d.priority,
                "confidence": d.confidence,
                "selection_reasons": d.selection_reasons,
                "affected_requirement_ids": d.affected_requirement_ids
            }
            for d in decisions
        ]

        self._json_response({
            "diff_file": diff_file_name,
            "evidence_source": "FIXTURE_MOCK (Simulated/Local Test Data)",
            "decisions": serializable_decisions,
            "unmitigated_gaps": unmitigated_gaps,
            "warning_notes": warnings
        })

    def _handle_get_report(self):
        data = run_itaf_analysis()
        report_md = generate_markdown_report(data["assessments"])
        self._json_response({"markdown": report_md})


def start_server(port: int = 8080):
    """Starts the ITAF web server."""
    server = HTTPServer(("127.0.0.1", port), ITAFRequestHandler)
    sys.stderr.write(f"\n====================================================================\n")
    sys.stderr.write(f"  ITAF Quality Engineering Workspace running at: http://127.0.0.1:{port}\n")
    sys.stderr.write(f"  Press Ctrl+C to stop.\n")
    sys.stderr.write(f"====================================================================\n\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    start_server(port)
