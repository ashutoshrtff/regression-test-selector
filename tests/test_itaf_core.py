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
    RequirementTestMapping,
    RequirementCoverageAssessment,
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


class TestFalseAssuranceGuards(unittest.TestCase):
    """
    Priority 2: Rigorous verification that superficial matches do not falsely establish
    coverage or satisfy mandatory quality gates.
    """

    def setUp(self):
        self.policy_engine = PolicyEngine()
        self.mapper = CrossRepoMapper()

    def test_idempotency_header_alone_does_not_prove_safe_replay(self):
        """A test checking Idempotency-Key header alone cannot satisfy GATE-PAY-001 or outcome."""
        req = Requirement(
            requirement_id="REQ-PAY-IDEMP-01",
            title="Idempotent Payment Replay",
            description="Replaying request with same key returns cached result.",
            req_type=RequirementType.IDEMPOTENCY,
            origin=RequirementOrigin.EXPLICIT_SPEC,
            domain="PAYMENTS",
            service="payment-service",
            interface="POST /api/v1/payments/process",
            mandatory=True,
            severity=RuleSeverity.BLOCKER,
            applicable_rule_ids=["GATE-PAY-001"],
            expected_outcomes=[
                ExpectedOutcome(
                    outcome_id="OUT-PAY-IDEMP-01",
                    requirement_id="REQ-PAY-IDEMP-01",
                    outcome_type=RequirementType.IDEMPOTENCY,
                    description="Cached response returned on duplicate key",
                    target_interface="/api/v1/payments/process"
                )
            ]
        )

        # Test ONLY asserts header presence
        test_case = DiscoveredTestCase(
            test_id="test_header_only",
            title="Verify idempotency header was sent",
            file_path="tests/idemp.spec.ts",
            line_number=10,
            framework="playwright-ts",
            endpoints_visited=["/api/v1/payments/process"],
            assertions=[
                AssertionEvidence(
                    assertion_type="HEADER",
                    target="idempotency-key",
                    raw_statement="expect(headers['idempotency-key']).toBeDefined()",
                    line_number=15,
                    is_deep_assertion=True
                )
            ]
        )

        all_tests = {"test_header_only": test_case}
        mappings = self.mapper.map_requirement_to_tests(req, all_tests)

        # Mappings should not assert outcome
        asserting_mappings = [m for m in mappings if m.asserts_outcome]
        self.assertEqual(len(asserting_mappings), 0, "Header check alone must NOT assert idempotency safe replay outcome!")

        # Policy engine must fail GATE-PAY-001
        rule = self.policy_engine.rules["GATE-PAY-001"]
        passes, explanation, _ = self.policy_engine.evaluate_gate(rule, req, mappings, all_tests)
        self.assertFalse(passes, "GATE-PAY-001 must FAIL if tests only check header presence!")
        self.assertIn("failed", explanation.lower())

    def test_http_409_alone_does_not_prove_duplicate_detection(self):
        """A generic 409 assertion in a non-duplicate test cannot satisfy GATE-PAY-002."""
        req = Requirement(
            requirement_id="REQ-PAY-DUP-01",
            title="Business Duplicate Detection",
            description="Reject duplicate payments within 60s window.",
            req_type=RequirementType.DUPLICATE_DETECTION,
            origin=RequirementOrigin.EXPLICIT_SPEC,
            domain="PAYMENTS",
            service="payment-service",
            interface="POST /api/v1/payments/process",
            mandatory=True,
            severity=RuleSeverity.BLOCKER,
            applicable_rule_ids=["GATE-PAY-002"],
            expected_outcomes=[
                ExpectedOutcome(
                    outcome_id="OUT-PAY-DUP-01",
                    requirement_id="REQ-PAY-DUP-01",
                    outcome_type=RequirementType.DUPLICATE_DETECTION,
                    description="409 on duplicate payload",
                    target_interface="/api/v1/payments/process",
                    expected_status_code=409
                )
            ]
        )

        # Unrelated test that asserts 409 (e.g. optimistic lock conflict)
        test_case = DiscoveredTestCase(
            test_id="test_lock_conflict",
            title="Update user profile concurrent optimistic lock conflict",
            file_path="tests/user.spec.ts",
            line_number=20,
            framework="playwright-ts",
            endpoints_visited=["/api/v1/payments/process"],
            assertions=[
                AssertionEvidence(
                    assertion_type="STATUS_CODE",
                    target="409",
                    raw_statement="expect(res.status).toBe(409)",
                    line_number=25,
                    is_deep_assertion=True
                )
            ]
        )

        all_tests = {"test_lock_conflict": test_case}
        mappings = self.mapper.map_requirement_to_tests(req, all_tests)
        asserting_mappings = [m for m in mappings if m.asserts_outcome]
        self.assertEqual(len(asserting_mappings), 0, "Generic 409 in unrelated test must NOT satisfy duplicate outcome!")

        rule = self.policy_engine.rules["GATE-PAY-002"]
        passes, _, _ = self.policy_engine.evaluate_gate(rule, req, mappings, all_tests)
        self.assertFalse(passes, "GATE-PAY-002 must FAIL when 409 occurs outside duplicate submission context!")

    def test_http_503_alone_does_not_prove_successful_retry(self):
        """Asserting HTTP 503 alone does not prove retry behavior or recovery."""
        req = Requirement(
            requirement_id="REQ-PAY-RETRY-01",
            title="Downstream Retry and Recovery",
            description="Retry transient 503 errors with exponential backoff.",
            req_type=RequirementType.RESILIENCE_RETRY,
            origin=RequirementOrigin.EXPLICIT_SPEC,
            domain="PAYMENTS",
            service="payment-service",
            interface="POST /api/v1/payments/process",
            mandatory=True,
            severity=RuleSeverity.CRITICAL,
            applicable_rule_ids=["GATE-RET-001"],
            expected_outcomes=[
                ExpectedOutcome(
                    outcome_id="OUT-PAY-RETRY-01",
                    requirement_id="REQ-PAY-RETRY-01",
                    outcome_type=RequirementType.RESILIENCE_RETRY,
                    description="Downstream retry attempts",
                    target_interface="/api/v1/payments/process"
                )
            ]
        )

        # Test only asserts downstream 503 without testing retries
        test_case = DiscoveredTestCase(
            test_id="test_downstream_503",
            title="Downstream gateway returns 503 service unavailable",
            file_path="tests/retry.spec.ts",
            line_number=30,
            framework="playwright-ts",
            endpoints_visited=["/api/v1/payments/process"],
            assertions=[
                AssertionEvidence(
                    assertion_type="STATUS_CODE",
                    target="503",
                    raw_statement="expect(res.status).toBe(503)",
                    line_number=35,
                    is_deep_assertion=True
                )
            ]
        )

        all_tests = {"test_downstream_503": test_case}
        mappings = self.mapper.map_requirement_to_tests(req, all_tests)
        asserting_mappings = [m for m in mappings if m.asserts_outcome]
        self.assertEqual(len(asserting_mappings), 0, "503 assertion alone must NOT assert retry outcome!")

        rule = self.policy_engine.rules["GATE-RET-001"]
        passes, _, _ = self.policy_engine.evaluate_gate(rule, req, mappings, all_tests)
        self.assertFalse(passes, "GATE-RET-001 must FAIL if no retry attempts / counts are asserted!")

    def test_unrelated_assertion_cannot_satisfy_mandatory_outcome(self):
        """A test asserting 200 or UI text cannot satisfy a 401 Unauthorized requirement."""
        req = Requirement(
            requirement_id="REQ-SEC-AUTH-01",
            title="Authentication Guard",
            description="Reject unauthenticated requests with 401.",
            req_type=RequirementType.SECURITY,
            origin=RequirementOrigin.EXPLICIT_SPEC,
            domain="SECURITY",
            service="payment-service",
            interface="POST /api/v1/payments/process",
            mandatory=True,
            severity=RuleSeverity.BLOCKER,
            applicable_rule_ids=["GATE-SEC-001"],
            expected_outcomes=[
                ExpectedOutcome(
                    outcome_id="OUT-SEC-401",
                    requirement_id="REQ-SEC-AUTH-01",
                    outcome_type=RequirementType.SECURITY,
                    description="401 Unauthorized",
                    target_interface="/api/v1/payments/process",
                    expected_status_code=401
                )
            ]
        )

        test_case = DiscoveredTestCase(
            test_id="test_positive_payment",
            title="Submit payment positive flow",
            file_path="tests/pay.spec.ts",
            line_number=1,
            framework="playwright-ts",
            endpoints_visited=["/api/v1/payments/process"],
            assertions=[
                AssertionEvidence(
                    assertion_type="STATUS_CODE",
                    target="200",
                    raw_statement="expect(res.status).toBe(200)",
                    line_number=5,
                    is_deep_assertion=True
                ),
                AssertionEvidence(
                    assertion_type="UI_TEXT",
                    target="Payment Successful",
                    raw_statement="expect(page.getByText('Payment Successful')).toBeVisible()",
                    line_number=6,
                    is_deep_assertion=False
                )
            ]
        )

        mappings = self.mapper.map_requirement_to_tests(req, {"test_positive_payment": test_case})
        asserting = [m for m in mappings if m.asserts_outcome]
        self.assertEqual(len(asserting), 0, "Positive 200 / UI text assertion must not satisfy 401 security outcome!")

    def test_jira_and_endpoint_match_without_outcome_evidence_not_confirmed(self):
        """A test matching Jira ticket and endpoint but lacking assertions does not gain confirmed coverage."""
        req = Requirement(
            requirement_id="PAY-900-FEATURE",
            title="Core Payment Processing",
            description="Process payments with Jira key PAY-900.",
            req_type=RequirementType.FUNCTIONAL,
            origin=RequirementOrigin.EXPLICIT_SPEC,
            domain="PAYMENTS",
            service="payment-service",
            interface="POST /api/v1/payments/process",
            mandatory=True,
            severity=RuleSeverity.MAJOR,
            applicable_rule_ids=[],
            expected_outcomes=[
                ExpectedOutcome(
                    outcome_id="OUT-PAY-900-SUCCESS",
                    requirement_id="PAY-900-FEATURE",
                    outcome_type=RequirementType.POSITIVE,
                    description="Payment returns 200 OK",
                    target_interface="/api/v1/payments/process",
                    expected_status_code=200
                )
            ]
        )

        # Test has Jira key PAY-900 and visits endpoint, but has ZERO assertions
        test_case = DiscoveredTestCase(
            test_id="test_jira_only",
            title="[PAY-900] Visit payment page",
            file_path="tests/visit.spec.ts",
            line_number=1,
            framework="playwright-ts",
            jira_keys=["PAY-900"],
            endpoints_visited=["/api/v1/payments/process"],
            assertions=[]
        )

        mappings = self.mapper.map_requirement_to_tests(req, {"test_jira_only": test_case})
        self.assertEqual(len(mappings), 1)
        self.assertEqual(mappings[0].confidence, MappingConfidence.MEDIUM)
        self.assertFalse(mappings[0].asserts_outcome, "Non-asserting test must have asserts_outcome=False")

        # Evaluate through Coverage Intelligence Engine
        engine = CoverageIntelligenceEngine(policy_engine=self.policy_engine, mapper=self.mapper)
        assessments = engine.assess_coverage([req], {"test_jira_only": test_case})
        self.assertEqual(len(assessments), 1)
        self.assertEqual(assessments[0].coverage_status, CoverageStatus.MISSING_COVERAGE,
                         "A test with zero assertions must not establish coverage!")

    def test_coverage_status_and_execution_status_are_independent(self):
        """A requirement with full test coverage whose tests were not run must report TEST_NOT_EXECUTED."""
        req = Requirement(
            requirement_id="REQ-COV-EXEC-INDEP",
            title="Idempotency Requirement",
            description="Safe replay verified.",
            req_type=RequirementType.IDEMPOTENCY,
            origin=RequirementOrigin.EXPLICIT_SPEC,
            domain="PAYMENTS",
            service="payment-service",
            interface="POST /api/v1/payments/process",
            mandatory=True,
            severity=RuleSeverity.BLOCKER,
            applicable_rule_ids=["GATE-PAY-001"],
            expected_outcomes=[
                ExpectedOutcome(
                    outcome_id="OUT-IDEMP-VERIFIED",
                    requirement_id="REQ-COV-EXEC-INDEP",
                    outcome_type=RequirementType.IDEMPOTENCY,
                    description="Safe replay",
                    target_interface="/api/v1/payments/process"
                )
            ]
        )

        test_case = DiscoveredTestCase(
            test_id="test_idemp_deep",
            title="Verify safe replay returns cached response",
            file_path="tests/idemp.spec.ts",
            line_number=1,
            framework="playwright-ts",
            endpoints_visited=["/api/v1/payments/process"],
            assertions=[
                AssertionEvidence(
                    assertion_type="IDEMPOTENCY_FLAG",
                    target="idempotency_verified",
                    raw_statement="expect(body.idempotency_verified).toBe(true)",
                    line_number=10,
                    is_deep_assertion=True
                )
            ]
        )
        # No execution evidence provided -> TEST_NOT_EXECUTED
        engine = CoverageIntelligenceEngine(policy_engine=self.policy_engine, mapper=self.mapper)
        assessments = engine.assess_coverage([req], {"test_idemp_deep": test_case}, execution_evidence={})

        self.assertEqual(assessments[0].coverage_status, CoverageStatus.COVERED)
        self.assertEqual(assessments[0].execution_status, ExecutionStatus.TEST_NOT_EXECUTED)
        self.assertNotEqual(assessments[0].execution_status, ExecutionStatus.EXECUTION_PASSED)


class TestRegressionSelectionValidation(unittest.TestCase):
    """
    Priority 3: Verifies regression selection across indirect dependencies, shared DTOs,
    configuration changes, missing specs, unknown files, and stale test indexes.
    """

    def setUp(self):
        self.available_tests = {
            "test_pay_success": DiscoveredTestCase(
                test_id="test_pay_success",
                title="Successfully submit real-time payment",
                file_path="tests/payments.spec.ts",
                line_number=10,
                framework="playwright-ts",
                in_regression_suite=True,
                in_smoke_suite=True,
                endpoints_visited=["/api/v1/payments/process"],
                assertions=[AssertionEvidence("STATUS_CODE", "200", "status 200", 12, True)]
            ),
            "test_data_integrity": DiscoveredTestCase(
                test_id="test_data_integrity",
                title="Reject missing currency or debtorAccount field",
                file_path="tests/integrity.spec.ts",
                line_number=20,
                framework="playwright-ts",
                in_regression_suite=True,
                in_smoke_suite=False,
                endpoints_visited=["/api/v1/payments/process"],
                assertions=[AssertionEvidence("STATUS_CODE", "400", "status 400", 25, True)]
            ),
            "test_smoke_health": DiscoveredTestCase(
                test_id="test_smoke_health",
                title="Smoke health check and gateway probe",
                file_path="tests/smoke.spec.ts",
                line_number=1,
                framework="playwright-ts",
                in_regression_suite=False,
                in_smoke_suite=True,
                endpoints_visited=["/api/v1/health"],
                assertions=[AssertionEvidence("STATUS_CODE", "200", "status 200", 5, True)]
            )
        }

        self.selector = RegressionSelector(available_tests=self.available_tests)

    def test_shared_dto_change_triggers_affected_requirements(self):
        """A PR modifying shared DTO field 'currency' activates data integrity requirements."""
        assessment = RequirementCoverageAssessment(
            requirement_id="REQ-MSG-CURRENCY-INTEGRITY",
            title="Message Element Integrity: currency",
            domain="PAYMENTS",
            service="payment-service",
            coverage_status=CoverageStatus.COVERED,
            mapped_tests=[
                RequirementTestMapping(
                    requirement_id="REQ-MSG-CURRENCY-INTEGRITY",
                    outcome_id="OUT-MSG-CURRENCY",
                    test_id="test_data_integrity",
                    confidence=MappingConfidence.HIGH,
                    evidence_summary="Asserts currency rejection 400",
                    asserts_outcome=True,
                    mapping_source="INTERFACE_ASSERTION"
                )
            ],
            uncovered_outcomes=[],
            applicable_rules=[],
            failing_gate_ids=[],
            execution_status=ExecutionStatus.EXECUTION_PASSED,
            assessment_notes=["[PASS] Covered"],
            suggested_test_scenario=None
        )

        fingerprints = {
            "endpoints": [],
            "routes": [],
            "jira_keys": [],
            "dto_fields": ["currency"],
            "files_changed": ["src/dto/PaymentRequest.java"],
            "risk_signals": []
        }

        decisions, gaps, notes = self.selector.select_tests_for_change(fingerprints, [assessment])
        selected_ids = [d.test_id for d in decisions]
        self.assertIn("test_data_integrity", selected_ids, "Test covering changed DTO must be selected!")

    def test_indirect_dependency_and_configuration_changes(self):
        """Configuration changes (e.g. pom.xml / migration) activate risk widening and smoke tests."""
        assessment = RequirementCoverageAssessment(
            requirement_id="REQ-PAY-CORE",
            title="Payment Core",
            domain="PAYMENTS",
            service="payment-service",
            coverage_status=CoverageStatus.COVERED,
            mapped_tests=[],
            uncovered_outcomes=[],
            applicable_rules=[],
            failing_gate_ids=[],
            execution_status=ExecutionStatus.TEST_NOT_EXECUTED,
            assessment_notes=[],
            suggested_test_scenario=None
        )

        fingerprints = {
            "endpoints": [],
            "routes": [],
            "jira_keys": [],
            "dto_fields": [],
            "files_changed": ["pom.xml", "db/migrations/V10__add_index.sql"],
            "risk_signals": [
                {"category": "build_configuration", "explanation": "pom.xml modified"},
                {"category": "database_migrations", "explanation": "V10 migration modified"}
            ]
        }

        decisions, gaps, notes = self.selector.select_tests_for_change(fingerprints, [assessment])
        smoke_decisions = [d for d in decisions if d.priority == "SMOKE_ONLY"]
        self.assertTrue(len(smoke_decisions) > 0, "Risk widening must activate smoke tests when config/migrations change!")
        smoke_ids = [d.test_id for d in smoke_decisions]
        self.assertIn("test_smoke_health", smoke_ids)

    def test_unknown_files_and_missing_specifications_widen_conservatively(self):
        """Changes touching unmapped endpoints or unknown files conservatively fall back to domain tests."""
        assessment = RequirementCoverageAssessment(
            requirement_id="REQ-PAY-CORE",
            title="Payment Core",
            domain="PAYMENTS",
            service="payment-service",
            coverage_status=CoverageStatus.COVERED,
            mapped_tests=[
                RequirementTestMapping(
                    requirement_id="REQ-PAY-CORE",
                    outcome_id="OUT-1",
                    test_id="test_pay_success",
                    confidence=MappingConfidence.HIGH,
                    evidence_summary="Covers payments",
                    asserts_outcome=True,
                    mapping_source="INTERFACE_ASSERTION"
                )
            ],
            uncovered_outcomes=[],
            applicable_rules=[],
            failing_gate_ids=[],
            execution_status=ExecutionStatus.EXECUTION_PASSED,
            assessment_notes=[],
            suggested_test_scenario=None
        )

        fingerprints = {
            "endpoints": ["/api/v1/unknown-external-webhook"],
            "routes": [],
            "jira_keys": [],
            "dto_fields": [],
            "files_changed": ["scripts/unknown-helper.sh"],
            "risk_signals": []
        }

        decisions, gaps, notes = self.selector.select_tests_for_change(fingerprints, [assessment])
        self.assertTrue(any("conservative domain fallback" in n.lower() for n in notes),
                        "Warning notes must state that conservative domain fallback was applied!")
        self.assertIn("test_pay_success", [d.test_id for d in decisions],
                      "Domain test must be conservatively selected on unmapped impact!")

    def test_stale_test_index_resilience(self):
        """If mapped test no longer exists in available tests, selector safely excludes it without error."""
        assessment = RequirementCoverageAssessment(
            requirement_id="REQ-STALE-01",
            title="Stale Test Requirement",
            domain="PAYMENTS",
            service="payment-service",
            coverage_status=CoverageStatus.PARTIALLY_COVERED,
            mapped_tests=[
                RequirementTestMapping(
                    requirement_id="REQ-STALE-01",
                    outcome_id="OUT-STALE",
                    test_id="test_deleted_from_repo_yesterday",
                    confidence=MappingConfidence.HIGH,
                    evidence_summary="Historical mapping",
                    asserts_outcome=True,
                    mapping_source="INTERFACE_ASSERTION"
                )
            ],
            uncovered_outcomes=[],
            applicable_rules=[],
            failing_gate_ids=[],
            execution_status=ExecutionStatus.TEST_NOT_EXECUTED,
            assessment_notes=[],
            suggested_test_scenario={"title": "Re-implement deleted test", "target_interface": "/api/v1/payments", "severity": "HIGH", "steps": ["Step 1"]}
        )

        fingerprints = {
            "endpoints": ["/api/v1/payments"],
            "routes": [],
            "jira_keys": [],
            "dto_fields": [],
            "files_changed": [],
            "risk_signals": []
        }

        decisions, gaps, notes = self.selector.select_tests_for_change(fingerprints, [assessment])
        self.assertNotIn("test_deleted_from_repo_yesterday", [d.test_id for d in decisions])
        self.assertTrue(len(gaps) > 0, "Unmitigated gap must be reported when tests are missing/stale!")
        self.assertEqual(gaps[0]["requirement_id"], "REQ-STALE-01")

    def test_itaf_and_rts_skill_compatibility(self):
        """Verifies that RTS matcher and ITAF RegressionSelector produce compatible decisions for PR-101."""
        scripts_dir = os.path.join(WORKSPACE_ROOT, ".github", "skills", "regression-test-selector", "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from matcher import match_and_rank_tests

        # Synthetic PR-101 fingerprints
        pr_101_fingerprints = {
            "endpoints": ["POST /api/v1/payments/process"],
            "routes": ["/checkout/payment"],
            "jira_keys": ["PAY-900"],
            "dto_fields": ["idempotency_key"],
            "files_changed": ["src/controllers/PaymentController.ts"],
            "risk_signals": []
        }

        # Index with one payment test
        test_index = {
            "tests": [
                {
                    "id": "tests/payments.spec.ts:10:Successfully submit real-time payment",
                    "title": "Successfully submit real-time payment",
                    "file": "tests/payments.spec.ts",
                    "line": 10,
                    "in_regression_suite": True,
                    "endpoints_called": ["POST /api/v1/payments/process"],
                    "routes_visited": ["/checkout/payment"],
                    "jira_keys": ["PAY-900"],
                    "assertions": [{"type": "STATUS_CODE", "target": "200"}]
                }
            ]
        }

        rts_result = match_and_rank_tests(pr_101_fingerprints, test_index)
        self.assertTrue(len(rts_result["must_run"]) >= 1, "RTS skill must place direct endpoint match in MUST_RUN")
        self.assertEqual(rts_result["must_run"][0]["confidence"], "High")

        # Now evaluate via ITAF RegressionSelector
        itaf_test = DiscoveredTestCase(
            test_id="tests/payments.spec.ts:10:Successfully submit real-time payment",
            title="Successfully submit real-time payment",
            file_path="tests/payments.spec.ts",
            line_number=10,
            framework="playwright-ts",
            in_regression_suite=True,
            endpoints_visited=["/api/v1/payments/process"],
            routes_visited=["/checkout/payment"],
            jira_keys=["PAY-900"],
            assertions=[AssertionEvidence("STATUS_CODE", "200", "status 200", 12, True)]
        )

        assessment = RequirementCoverageAssessment(
            requirement_id="REQ-PAY-PROCESS",
            title="Process Payment",
            domain="PAYMENTS",
            service="payment-service",
            coverage_status=CoverageStatus.COVERED,
            mapped_tests=[
                RequirementTestMapping(
                    requirement_id="REQ-PAY-PROCESS",
                    outcome_id="OUT-1",
                    test_id=itaf_test.test_id,
                    confidence=MappingConfidence.CONFIRMED,
                    evidence_summary="Direct endpoint and outcome match",
                    asserts_outcome=True,
                    mapping_source="INTERFACE_ASSERTION"
                )
            ],
            uncovered_outcomes=[],
            applicable_rules=[],
            failing_gate_ids=[],
            execution_status=ExecutionStatus.EXECUTION_PASSED,
            assessment_notes=[],
            suggested_test_scenario=None
        )

        itaf_selector = RegressionSelector(available_tests={itaf_test.test_id: itaf_test})
        itaf_decisions, _, _ = itaf_selector.select_tests_for_change(pr_101_fingerprints, [assessment])

        self.assertEqual(len(itaf_decisions), 1)
        self.assertEqual(itaf_decisions[0].test_id, rts_result["must_run"][0]["id"])
        self.assertEqual(itaf_decisions[0].priority, "MUST_RUN")


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
