#!/usr/bin/env python3
"""
test_fingerprints.py - Tests for extract_change_fingerprints.py on all 5 fixture diffs.
"""

import json
import os
import sys
import unittest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPTS_DIR)

from extract_change_fingerprints import extract_fingerprints_from_diff


class TestChangeFingerprints(unittest.TestCase):
    def setUp(self):
        self.diffs_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "examples", "fixtures", "dev-diffs")
        )

    def _read_diff(self, filename: str) -> str:
        with open(os.path.join(self.diffs_dir, filename), "r", encoding="utf-8") as f:
            return f.read()

    def test_pr_101_strong_evidence(self):
        diff = self._read_diff("pr-101-payment-route.diff")
        fp = extract_fingerprints_from_diff(diff)
        self.assertIn("PAY-101", fp["jira_keys"])
        self.assertTrue(any("/api/v1/payments/process" in ep for ep in fp["endpoints"]))
        self.assertIn("/checkout/payment", fp["routes"])
        self.assertIn("Pay Now", fp["ui_labels"])
        self.assertIn("cardToken", fp["dto_fields"])
        self.assertEqual(len(fp["risk_signals"]), 0)

    def test_pr_102_jira_only(self):
        diff = self._read_diff("pr-102-jira-only.diff")
        fp = extract_fingerprints_from_diff(diff)
        self.assertIn("PAY-102", fp["jira_keys"])
        self.assertEqual(len(fp["endpoints"]), 0)
        self.assertEqual(len(fp["routes"]), 0)
        self.assertEqual(len(fp["ui_labels"]), 0)

    def test_pr_103_coverage_gap(self):
        diff = self._read_diff("pr-103-coverage-gap.diff")
        fp = extract_fingerprints_from_diff(diff)
        self.assertIn("PAY-309", fp["jira_keys"])
        self.assertIn("/refund/instant", fp["routes"])
        self.assertTrue(any("/instant" in ep or "/api/v1/refunds" in ep for ep in fp["endpoints"]))

    def test_pr_104_risk_widening(self):
        diff = self._read_diff("pr-104-auth-risk.diff")
        fp = extract_fingerprints_from_diff(diff)
        self.assertIn("AUTH-909", fp["jira_keys"])
        risk_categories = [r["category"] for r in fp["risk_signals"]]
        self.assertIn("auth_security", risk_categories)
        self.assertIn("dependencies", risk_categories)

    def test_pr_105_unlinked_edge_cases(self):
        diff = self._read_diff("pr-105-unlinked.diff")
        fp = extract_fingerprints_from_diff(diff)
        self.assertIn("PAY-8821", fp["jira_keys"])
        self.assertIn("ERR_CARD_EXPIRED", fp["error_codes"])
        self.assertIn("cardToken", fp["dto_fields"])


if __name__ == "__main__":
    unittest.main()
