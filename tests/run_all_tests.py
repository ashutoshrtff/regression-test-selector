#!/usr/bin/env python3
"""
Root test runner: executes both ITAF core tests and RTS skill tests.
"""

import os
import sys
import unittest

WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

def main():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Discover tests in tests/
    tests_dir = os.path.join(WORKSPACE_ROOT, "tests")
    suite.addTests(loader.discover(tests_dir, pattern="test_*.py"))

    # Discover tests in .github/skills/regression-test-selector/tests/
    rts_tests_dir = os.path.join(WORKSPACE_ROOT, ".github", "skills", "regression-test-selector", "tests")
    if os.path.exists(rts_tests_dir):
        suite.addTests(loader.discover(rts_tests_dir, pattern="test_*.py", top_level_dir=rts_tests_dir))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

if __name__ == "__main__":
    main()
