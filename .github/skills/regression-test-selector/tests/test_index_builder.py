#!/usr/bin/env python3
"""
test_index_builder.py - Unit tests for build_test_index.py for Playwright TS and Selenium Java.
"""

import os
import sys
import unittest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPTS_DIR)

from build_test_index import build_index, PageObjectCatalog, parse_playwright_file, parse_selenium_java_file


class TestIndexBuilder(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "examples", "fixtures", "fake-automation-repo")
        )
        self.playwright_dir = os.path.join(self.base_dir, "playwright")
        self.selenium_dir = os.path.join(self.base_dir, "selenium")

    def test_page_object_catalog(self):
        catalog = PageObjectCatalog(self.playwright_dir)
        self.assertIn("PaymentPage", catalog.page_objects)
        po = catalog.resolve("PaymentPage")
        self.assertIn("/checkout/payment", po["routes"])
        self.assertIn("/api/v1/payments/process", po["endpoints"])
        self.assertIn("card-number-input", po["ui_labels"])

    def test_build_playwright_index(self):
        index = build_index(self.playwright_dir, framework="playwright-ts", force=True)
        meta = index["meta"]
        tests = index["tests"]

        self.assertEqual(meta["total_tests"], 5)
        self.assertEqual(meta["in_regression_suite"], 3)
        self.assertEqual(meta["in_smoke_suite"], 2)

        # Check page object resolution on payment.spec.ts
        pay_test = next(t for t in tests if "[PAY-101]" in t["id"])
        self.assertIn("/checkout/payment", pay_test["routes_visited"])
        self.assertIn("Pay Now", pay_test["ui_labels"])
        self.assertIn("PaymentPage", pay_test["page_objects_used"])

        # Check test outside regression suite
        unlinked = next(t for t in tests if "[PAY-8821]" in t["id"])
        self.assertFalse(unlinked["in_regression_suite"])
        self.assertIn("PAY-8821", unlinked["jira_keys"])

    def test_build_selenium_index(self):
        index = build_index(self.selenium_dir, framework="selenium-java", force=True)
        meta = index["meta"]
        tests = index["tests"]

        self.assertEqual(meta["total_tests"], 3)
        self.assertEqual(meta["in_regression_suite"], 2)
        self.assertEqual(meta["in_smoke_suite"], 1)

        pay_test = next(t for t in tests if "PAY-101" in t["title"])
        self.assertIn("/checkout/payment", pay_test["routes_visited"])
        self.assertIn("btn-submit-order", pay_test["ui_labels"])
        self.assertTrue(pay_test["in_regression_suite"])


if __name__ == "__main__":
    unittest.main()
