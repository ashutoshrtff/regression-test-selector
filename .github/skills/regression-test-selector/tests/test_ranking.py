#!/usr/bin/env python3
"""
test_ranking.py - Unit tests for matching and ranking rules, confidence tiers, and guardrails.
"""

import json
import os
import sys
import unittest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPTS_DIR)

from matcher import match_and_rank_tests, format_markdown_report


class TestRankingRules(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "examples", "fixtures"))
        with open(os.path.join(self.fixtures_dir, "playwright-index.json"), "r", encoding="utf-8") as f:
            self.playwright_index = json.load(f)
        with open(os.path.join(self.fixtures_dir, "selenium-index.json"), "r", encoding="utf-8") as f:
            self.selenium_index = json.load(f)

    def test_tier_1_direct_match(self):
        fingerprints = {
            "endpoints": ["POST /api/v1/payments/process"],
            "routes": ["/checkout/payment"],
            "ui_labels": ["Pay Now"],
            "jira_keys": ["PAY-101"],
            "dto_fields": ["cardToken"],
            "error_codes": [],
            "risk_signals": []
        }
        res = match_and_rank_tests(fingerprints, self.playwright_index)
        must_run_ids = [t["id"] for t in res["must_run"]]
        # Expect payment.spec.ts:6:[PAY-101] to be selected with High confidence
        self.assertTrue(any("PAY-101" in tid for tid in must_run_ids))
        pay101 = next(t for t in res["must_run"] if "PAY-101" in t["id"])
        self.assertEqual(pay101["confidence"], "High")
        self.assertTrue(pay101["in_regression_suite"])

    def test_jira_only_match(self):
        fingerprints = {
            "endpoints": [],
            "routes": [],
            "ui_labels": [],
            "jira_keys": ["PAY-102"],
            "dto_fields": [],
            "error_codes": [],
            "risk_signals": []
        }
        res = match_and_rank_tests(fingerprints, self.playwright_index)
        all_selected = res["must_run"] + res["should_run"]
        selected_ids = [t["id"] for t in all_selected]
        self.assertTrue(any("PAY-102" in tid for tid in selected_ids))

    def test_coverage_gap_detection(self):
        fingerprints = {
            "endpoints": ["POST /api/v1/refunds/instant"],
            "routes": ["/refund/instant"],
            "ui_labels": [],
            "jira_keys": ["PAY-309"],
            "dto_fields": [],
            "error_codes": [],
            "risk_signals": []
        }
        res = match_and_rank_tests(fingerprints, self.playwright_index)
        self.assertEqual(len(res["must_run"]), 0)
        self.assertGreater(len(res["coverage_gaps"]), 0)
        gap_targets = [g["target"] for g in res["coverage_gaps"]]
        self.assertIn("/api/v1/refunds/instant", gap_targets)
        self.assertIn("/refund/instant", gap_targets)

    def test_risk_widening_activates_smoke(self):
        fingerprints = {
            "endpoints": [],
            "routes": [],
            "ui_labels": [],
            "jira_keys": [],
            "dto_fields": [],
            "error_codes": [],
            "risk_signals": [
                {
                    "category": "auth_security",
                    "file": "src/auth/JwtValidator.java",
                    "trigger": "path",
                    "explanation": "Security module altered"
                }
            ]
        }
        res = match_and_rank_tests(fingerprints, self.playwright_index)
        self.assertTrue(res["smoke_triggered"])
        # Should include smoke tests
        all_selected = res["must_run"] + res["should_run"]
        self.assertTrue(any("AUTH-401" in t["id"] or "@smoke" in t["title"] for t in all_selected))

    def test_strict_validation_guardrail_prevents_hallucinations(self):
        """Ensures non-existent tests trigger a loud failure and can never be returned."""
        fingerprints = {
            "endpoints": ["POST /api/v1/payments/process"],
            "routes": [],
            "ui_labels": [],
            "jira_keys": [],
            "dto_fields": [],
            "error_codes": [],
            "risk_signals": []
        }
        # Fake index missing the test
        corrupted_index = {"meta": {}, "tests": []}
        # match_and_rank_tests only selects tests present in index
        res = match_and_rank_tests(fingerprints, corrupted_index)
        self.assertEqual(len(res["must_run"]), 0)
        self.assertEqual(len(res["should_run"]), 0)

    def test_outside_regression_suite_flagged(self):
        """Tests that tests outside the regression suite are clearly flagged."""
        fingerprints = {
            "endpoints": ["POST /api/v1/payments/process"],
            "routes": [],
            "ui_labels": [],
            "jira_keys": ["PAY-8821"],
            "dto_fields": ["cardToken"],
            "error_codes": ["ERR_CARD_EXPIRED"],
            "risk_signals": []
        }
        res = match_and_rank_tests(fingerprints, self.playwright_index)
        unlinked = next((t for t in res["must_run"] + res["should_run"] if "PAY-8821" in t["id"]), None)
        self.assertIsNotNone(unlinked)
        self.assertFalse(unlinked["in_regression_suite"])


if __name__ == "__main__":
    unittest.main()
