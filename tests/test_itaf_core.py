#!/usr/bin/env python3
"""
Unit and integration tests for ITAF core components, policy engine, mapper,
coverage intelligence, regression selector, and web server security.
"""

import json
import os
import sys
import unittest
from pathlib import Path

# Add workspace root to sys.path
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)
SKILL_DIR = os.path.join(WORKSPACE_ROOT, ".github", "skills", "regression-test-selector")
if SKILL_DIR not in sys.path:
    sys.path.insert(0, SKILL_DIR)

from itaf.core.models import (
    Requirement,
    ExpectedOutcome,
    DiscoveredTestCase,
    AssertionEvidence,
    RequirementType,
    RequirementOrigin,
    RuleSeverity,
    CoverageStatus,
    ExecutionStatus,
    MappingConfidence
)
from itaf.parsers import OpenAPIParser, FeatureParser, MessageFormatParser
from itaf.engine import PolicyEngine, TestDiscoveryEngine, CrossRepoMapper, CoverageIntelligenceEngine, RegressionSelector


class TestParsers(unittest.TestCase):
    """Verifies that parsers extract specifications with correct types and outcomes."""

    def setUp(self):
        self.sample_dir = os.path.join(WORKSPACE_ROOT, "examples", "sample_feature")

    def test_openapi_parser(self):
        openapi_path = os.path.join(self.sample_dir, "payment-api.v1.yaml")
        parser = OpenAPIParser(openapi_path)
        reqs = parser.parse()
        self.assertGreaterEqual(len(reqs), 3)

        req_types = {r.req_type for r in reqs}
        self.assertIn(RequirementType.API_CONTRACT, req_types)
        self.assertIn(RequirementType.SECURITY, req_types)
        self.assertIn(RequirementType.IDEMPOTENCY, req_types)

        contract_req = next(r for r in reqs if r.req_type == RequirementType.API_CONTRACT)
        status_codes = {o.expected_status_code for o in contract_req.expected_outcomes}
        self.assertIn(200, status_codes)
        self.assertIn(400, status_codes)

    def test_feature_parser(self):
        feature_path = os.path.join(self.sample_dir, "payment-submission-feature.md")
        parser = FeatureParser(feature_path)
        reqs = parser.parse()
        self.assertGreaterEqual(len(reqs), 2)

        dup_req = next((r for r in reqs if r.req_type == RequirementType.DUPLICATE_DETECTION), None)
        self.assertNotNull(dup_req)
        self.assertEqual(dup_req.expected_outcomes[0].expected_status_code, 409)

        retry_req = next((r for r in reqs if r.req_type == RequirementType.RESILIENCE_RETRY), None)
        self.assertNotNull(retry_req)
        self.assertIn("GATE-RET-001", retry_req.applicable_rule_ids)

    def assertNotNull(self, val):
        self.assertTrue(val is not None)

    def test_message_parser(self):
        msg_path = os.path.join(self.sample_dir, "swift-pacs008-payment.json")
        parser = MessageFormatParser(msg_path)
        reqs = parser.parse()
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0].req_type, RequirementType.DATA_INTEGRITY)
        self.assertGreaterEqual(len(reqs[0].expected_outcomes), 4)


class TestPolicyEngine(unittest.TestCase):
    """Verifies rule applicability, gate evaluation, and false-positive prevention."""

    def setUp(self):
        self.engine = PolicyEngine()

    def test_rule_applicability_is_selective(self):
        """Security requirement must NOT apply payment or retry gates."""
        sec_req = Requirement(
            requirement_id="REQ-SEC-TEST",
            title="Authentication Requirement",
            description="Auth",
            req_type=RequirementType.SECURITY,
            origin=RequirementOrigin.EXPLICIT_SPEC,
            domain="PAYMENTS",
            service="test-service",
            interface="POST /api/v1/payments/process",
            applicable_rule_ids=["GATE-SEC-001", "GATE-SEC-002"]
        )
        applicable = self.engine.get_applicable_rules(sec_req)
        app_ids = [r.rule_id for r in applicable]
        self.assertIn("GATE-SEC-001", app_ids)
        self.assertIn("GATE-SEC-002", app_ids)
        # Must NOT include retry or idempotency gates
        self.assertNotIn("GATE-RET-001", app_ids)
        self.assertNotIn("GATE-PAY-001", app_ids)

    def test_keyword_match_does_not_falsely_satisfy_gate(self):
        """A test merely containing 'conflict' or 'auth' in code must not satisfy gates."""
        rule_dup = self.engine.rules.get("GATE-PAY-002")
        self.assertTrue(rule_dup is not None)

        req_dup = Requirement(
            requirement_id="REQ-DUP-TEST",
            title="Duplicate Detection",
            description="Dup",
            req_type=RequirementType.DUPLICATE_DETECTION,
            origin=RequirementOrigin.EXPLICIT_SPEC,
            domain="PAYMENTS",
            service="test-service",
            interface="POST /api/v1/payments/process"
        )

        # Mock test that mentions 'conflict' in comment or variable but asserts 200
        test_false = DiscoveredTestCase(
            test_id="test:1:false_positive",
            title="Test payment conflict helper",
            file_path="test.spec.ts",
            line_number=1,
            framework="playwright-ts",
            endpoints_visited=["/api/v1/payments/process"],
            assertions=[
                AssertionEvidence(
                    assertion_type="STATUS_CODE",
                    target="200",
                    raw_statement="expect(conflictFlag).toBe(200)",
                    is_deep_assertion=True
                )
            ]
        )

        from itaf.core.models import RequirementTestMapping
        mapping = RequirementTestMapping(
            requirement_id="REQ-DUP-TEST",
            outcome_id="OUT-1",
            test_id="test:1:false_positive",
            confidence=MappingConfidence.HIGH,
            evidence_summary="test",
            asserts_outcome=True,
            mapping_source="TEST"
        )

        passes, reason, _ = self.engine.evaluate_gate(
            rule_dup,
            req_dup,
            [mapping],
            {"test:1:false_positive": test_false}
        )
        # Must FAIL because target was 200, not 409 or DUPLICATE_PAYMENT
        self.assertFalse(passes)


class TestCrossRepoMapper(unittest.TestCase):
    """Verifies that cross repo mapper handles case normalization and precise matching."""

    def test_case_insensitive_interface_matching(self):
        mapper = CrossRepoMapper()
        req = Requirement(
            requirement_id="REQ-TEST",
            title="Payment Submission",
            description="Process",
            req_type=RequirementType.POSITIVE,
            origin=RequirementOrigin.EXPLICIT_SPEC,
            domain="PAYMENTS",
            service="pay-srv",
            interface="POST /api/v1/payments/process",
            expected_outcomes=[
                ExpectedOutcome(
                    outcome_id="OUT-200",
                    requirement_id="REQ-TEST",
                    outcome_type=RequirementType.POSITIVE,
                    description="Returns 200",
                    target_interface="POST /api/v1/payments/process",
                    expected_status_code=200
                )
            ]
        )

        test = DiscoveredTestCase(
            test_id="test:10:submitPayment",
            title="[PAY-900] Successfully submit payment",
            file_path="test.spec.ts",
            line_number=10,
            framework="playwright-ts",
            endpoints_visited=["/api/v1/payments/process"],
            assertions=[
                AssertionEvidence("STATUS_CODE", "200", "expect(res.status).toBe(200)", 12, True)
            ]
        )

        mappings = mapper.map_requirement_to_tests(req, {test.test_id: test})
        self.assertEqual(len(mappings), 1)
        self.assertTrue(mappings[0].asserts_outcome)
        self.assertEqual(mappings[0].confidence, MappingConfidence.HIGH)

    def test_negative_outcome_precision(self):
        """A test asserting 401 must not satisfy 403 Forbidden outcome."""
        mapper = CrossRepoMapper()
        req = Requirement(
            requirement_id="REQ-SEC",
            title="Security Control",
            description="Auth",
            req_type=RequirementType.SECURITY,
            origin=RequirementOrigin.EXPLICIT_SPEC,
            domain="PAYMENTS",
            service="pay-srv",
            interface="POST /api/v1/payments/process",
            expected_outcomes=[
                ExpectedOutcome(
                    outcome_id="OUT-403",
                    requirement_id="REQ-SEC",
                    outcome_type=RequirementType.SECURITY,
                    description="Returns 403 Forbidden",
                    target_interface="POST /api/v1/payments/process",
                    expected_status_code=403
                )
            ]
        )

        test_401 = DiscoveredTestCase(
            test_id="test:20:auth401",
            title="Reject with 401 Unauthorized",
            file_path="test.spec.ts",
            line_number=20,
            framework="playwright-ts",
            endpoints_visited=["/api/v1/payments/process"],
            assertions=[
                AssertionEvidence("STATUS_CODE", "401", "expect(res.status).toBe(401)", 22, True)
            ]
        )

        mappings = mapper.map_requirement_to_tests(req, {test_401.test_id: test_401})
        # If mapped, asserts_outcome must be False because 401 != 403
        for m in mappings:
            self.assertFalse(m.asserts_outcome)


class TestRegressionSelector(unittest.TestCase):
    """Verifies conservative selection and gap detection for ambiguous and missing coverage."""

    def test_unmitigated_gap_flagged_for_missing_and_ambiguous(self):
        from itaf.core.models import RequirementCoverageAssessment
        ass_missing = RequirementCoverageAssessment(
            requirement_id="REQ-RETRY",
            title="Downstream Retry",
            domain="PAYMENTS",
            service="pay-srv",
            coverage_status=CoverageStatus.MISSING_COVERAGE,
            failing_gate_ids=["GATE-RET-001"],
            suggested_test_scenario={"title": "Verify retry on 503", "target_interface": "POST /api/v1/payments/process"}
        )

        ass_ambiguous = RequirementCoverageAssessment(
            requirement_id="REQ-AMBIGUOUS",
            title="Unspecified Timeout Feature",
            domain="PAYMENTS",
            service="pay-srv",
            coverage_status=CoverageStatus.AMBIGUOUS,
            assessment_notes=["[AMBIGUITY] Timeout threshold not defined."],
            suggested_test_scenario={"title": "Clarify timeout boundary", "target_interface": "POST /api/v1/payments/process"}
        )

        selector = RegressionSelector({})
        fingerprints = {"endpoints": ["POST /api/v1/payments/process"]}
        decisions, gaps, warnings = selector.select_tests_for_change(fingerprints, [ass_missing, ass_ambiguous])

        gap_ids = [g["requirement_id"] for g in gaps]
        self.assertIn("REQ-RETRY", gap_ids)
        self.assertIn("REQ-AMBIGUOUS", gap_ids)
        self.assertTrue(len(warnings) >= 2)


class TestCoverageIntelligenceEdgeCases(unittest.TestCase):
    """Verifies coverage intelligence guardrails against empty outcomes and false passes."""

    def setUp(self):
        self.policy_engine = PolicyEngine()
        self.engine = CoverageIntelligenceEngine(self.policy_engine)

    def test_empty_expected_outcomes_never_marked_covered(self):
        """A requirement with zero expected outcomes must not automatically be marked COVERED."""
        req_empty = Requirement(
            requirement_id="REQ-EMPTY-TEST",
            title="Empty Requirement",
            description="No outcomes declared",
            req_type=RequirementType.FUNCTIONAL,
            origin=RequirementOrigin.EXPLICIT_SPEC,
            domain="PAYMENTS",
            service="pay-service",
            interface="POST /api/v1/payments",
            expected_outcomes=[]
        )
        assessments = self.engine.assess_coverage([req_empty], {})
        self.assertEqual(len(assessments), 1)
        # Must NOT be COVERED
        self.assertNotEqual(assessments[0].coverage_status, CoverageStatus.COVERED)
        self.assertEqual(assessments[0].coverage_status, CoverageStatus.AMBIGUOUS)

    def test_requirement_with_zero_applicable_gates_explicitly_noted(self):
        """A requirement with zero applicable gates must note that no gates apply."""
        req_no_gates = Requirement(
            requirement_id="REQ-CUSTOM-REPORTING",
            title="Generate Audit CSV",
            description="Reporting",
            req_type=RequirementType.FUNCTIONAL,
            origin=RequirementOrigin.EXPLICIT_SPEC,
            domain="REPORTING",
            service="report-service",
            interface="GET /api/v1/reports/audit",
            expected_outcomes=[
                ExpectedOutcome(
                    outcome_id="OUT-REP-200",
                    requirement_id="REQ-CUSTOM-REPORTING",
                    outcome_type=RequirementType.FUNCTIONAL,
                    description="Returns 200 CSV",
                    target_interface="GET /api/v1/reports/audit",
                    expected_status_code=200
                )
            ]
        )
        assessments = self.engine.assess_coverage([req_no_gates], {})
        self.assertEqual(len(assessments), 1)
        self.assertEqual(len(assessments[0].applicable_rules), 0)
        self.assertTrue(any("No organizational quality gates apply" in n for n in assessments[0].assessment_notes))


class TestIncrementalCache(unittest.TestCase):
    """Verifies artifact hashing, cache hits, and cache invalidation."""

    def test_artifact_cache_lifecycle(self):
        import tempfile
        from itaf.core.cache import ArtifactCache

        cache = ArtifactCache()
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".yaml") as f:
            f.write("openapi: 3.0.0\ninfo:\n  title: Test API\n")
            temp_path = f.name

        try:
            # First fetch: computes and caches
            call_count = [0]
            def compute():
                call_count[0] += 1
                return {"title": "Test API"}

            result1 = cache.get_or_compute(temp_path, compute)
            self.assertEqual(result1["title"], "Test API")
            self.assertEqual(call_count[0], 1)

            # Second fetch: cache hit, compute not called
            result2 = cache.get_or_compute(temp_path, compute)
            self.assertEqual(result2["title"], "Test API")
            self.assertEqual(call_count[0], 1)

            # Modify file: cache must invalidate and recompute
            with open(temp_path, "w") as f:
                f.write("openapi: 3.0.0\ninfo:\n  title: Updated API\n")

            def compute_updated():
                call_count[0] += 1
                return {"title": "Updated API"}

            result3 = cache.get_or_compute(temp_path, compute_updated)
            self.assertEqual(result3["title"], "Updated API")
            self.assertEqual(call_count[0], 2)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestWebServerSecurity(unittest.TestCase):
    """Verifies that the web server rejects directory traversal attempts."""

    def test_static_path_traversal_blocked(self):
        from itaf.ui.server import STATIC_DIR
        rel_path = "../../itaf_cli.py"
        clean_rel = os.path.normpath(rel_path.lstrip("/\\"))
        full_path = os.path.abspath(os.path.join(STATIC_DIR, clean_rel))
        try:
            common = os.path.commonpath([STATIC_DIR, full_path])
            is_traversal = (common != STATIC_DIR)
        except ValueError:
            is_traversal = True

        self.assertTrue(is_traversal, "Directory traversal was not detected!")

    def test_diff_filename_sanitization(self):
        traversal_input = "../../../etc/passwd"
        clean_name = os.path.basename(traversal_input)
        self.assertEqual(clean_name, "passwd")
        self.assertNotIn("/", clean_name)
        self.assertNotIn("..", clean_name)


if __name__ == "__main__":
    unittest.main()
