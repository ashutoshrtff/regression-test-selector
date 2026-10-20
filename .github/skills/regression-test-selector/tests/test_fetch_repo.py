#!/usr/bin/env python3
"""
test_fetch_repo.py - Unit tests for fetch_automation_repo.py host parsing and local repo handling.
"""

import os
import sys
import unittest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPTS_DIR)

from fetch_automation_repo import extract_host_from_repo, is_local_path, fetch_or_clone_repo


class TestFetchRepo(unittest.TestCase):
    def test_extract_host_standard_github(self):
        url = "https://github.com/my-org/payments-automation.git"
        self.assertEqual(extract_host_from_repo(url), "github.com")

    def test_extract_host_ghe_eu_residency(self):
        url = "https://emea-payments.ghe.com/psp-team/e2e-suite"
        self.assertEqual(extract_host_from_repo(url), "emea-payments.ghe.com")

    def test_extract_host_ssh_format(self):
        url = "git@github-enterprise.internal.net:payments/automation.git"
        self.assertEqual(extract_host_from_repo(url), "github-enterprise.internal.net")

    def test_is_local_path(self):
        self.assertTrue(is_local_path("."))
        self.assertTrue(is_local_path("./my-folder"))
        self.assertTrue(is_local_path("../sibling-repo"))
        self.assertFalse(is_local_path("https://github.com/org/repo"))

    def test_fetch_local_fixture_repo(self):
        fixture_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "examples", "fixtures", "fake-automation-repo", "playwright")
        )
        meta = fetch_or_clone_repo(fixture_path)
        self.assertEqual(meta["host"], "local")
        self.assertTrue(os.path.exists(meta["path"]))
        self.assertIn("fetched_at", meta)


if __name__ == "__main__":
    unittest.main()
