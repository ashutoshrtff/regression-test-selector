#!/usr/bin/env python3
"""
run_all_tests.py - Test suite runner for regression-test-selector.
Runs all unit and integration tests via standard library unittest.
"""

import os
import sys
import unittest

def main():
    test_dir = os.path.dirname(__file__)
    suite = unittest.defaultTestLoader.discover(test_dir, pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

if __name__ == "__main__":
    main()
