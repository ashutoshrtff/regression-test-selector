#!/usr/bin/env python3
"""
test_backtest.py - Unit tests for backtest.py evaluation pipeline and metric calculations.
"""

import os
import sys
import unittest

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, SCRIPTS_DIR)

from backtest import run_backtest, load_known_defects


class TestBacktest(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "examples", "fixtures"))
        self.diffs_dir = os.path.join(self.fixtures_dir, "dev-diffs")
        self.index_file = os.path.join(self.fixtures_dir, "playwright-index.json")
        self.defects_file = os.path.join(self.fixtures_dir, "known-defects.csv")

    def test_load_known_defects(self):
        defects = load_known_defects(self.defects_file)
        self.assertIn("pr-101", defects)
        self.assertEqual(defects["pr-101"], ["PAY-101"])
        self.assertIn("pr-104", defects)

    def test_run_backtest_pipeline(self):
        results = run_backtest(
            diffs_dir=self.diffs_dir,
            index_file=self.index_file,
            known_defects_file=self.defects_file,
            avg_duration_sec=45
        )
        summary = results["summary"]
        breakdown = results["per_pr_breakdown"]

        self.assertEqual(summary["total_prs_analyzed"], 5)
        self.assertEqual(summary["known_defects_tested"], 4)
        self.assertEqual(summary["known_defects_caught"], 4)
        self.assertEqual(summary["known_defects_missed"], 0)
        self.assertEqual(summary["recall_rate"], "100.0%")
        self.assertGreater(summary["total_engineering_time_saved_minutes"], 0)


if __name__ == "__main__":
    unittest.main()
