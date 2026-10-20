#!/usr/bin/env python3
"""
itaf.engine.test_discovery - Deep Test Discovery and Assertion Structure Inspector.

Extracts test cases across separate automation repositories and deeply inspects
their assertions to distinguish tests that genuinely verify outcomes from tests that merely visit endpoints.
"""

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from itaf.core.models import (
    DiscoveredTestCase,
    AssertionEvidence,
    ExecutionStatus
)

JIRA_KEY_REGEX = re.compile(r'\b([A-Z]{2,10}-\d+)\b')
TAG_REGEX = re.compile(r'(@[a-zA-Z0-9_\-]+)')

# Assertion regex patterns
ASSERTION_PATTERNS = [
    # Status codes: expect(response.status()).toBe(200), expect(res.status).toBe(409), Assert.assertEquals(response.getStatusCode(), 200)
    (re.compile(r'status(?:Code)?\s*\)?\s*(?:==|\.toBe\(|\.toEqual\(|,)\s*([1-5][0-9]{2})', re.IGNORECASE), "STATUS_CODE"),
    # Error codes: errorCode == 'DUPLICATE_PAYMENT', expect(body.errorCode).toBe('...')
    (re.compile(r'(?:errorCode|error_code|code)\s*(?:==|\.toBe\(|\.toEqual\(|,\s*["\'])\s*["\']([A-Z0-9_]{3,30})["\']', re.IGNORECASE), "ERROR_CODE"),
    # Headers: expect(headers['idempotency-key']), getHeader("Idempotency-Key")
    (re.compile(r'(?:header|headers|getHeader)\s*(?:\[|\()\s*["\']([a-zA-Z0-9_\-]+)["\']', re.IGNORECASE), "HEADER"),
    # Retries: retry_count, attempts, retryAttempts
    (re.compile(r'(?:retry(?:Count|Attempts|_count)?|attempts)\s*(?:==|>=|\.toBe\()\s*([0-9]+)', re.IGNORECASE), "RETRY_COUNT"),
    # UI Text / messages: expect(page.getByText('...'))
    (re.compile(r'getByText\s*\(\s*["\']([^"\']+)["\']\s*\)', re.IGNORECASE), "UI_TEXT"),
    # Generic assertions: expect(...).toBeVisible(), Assert.assertTrue(...)
    (re.compile(r'expect\s*\(\s*([^)]+)\)\.(toBeVisible|toBeTruthy|toBeDefined|toContain)', re.IGNORECASE), "GENERIC_ASSERTION"),
    (re.compile(r'Assert\.(assertTrue|assertEquals|assertNotNull)\s*\(\s*([^,\)]+)', re.IGNORECASE), "GENERIC_ASSERTION")
]


def inspect_assertions_in_body(body_text: str, start_line: int = 1) -> List[AssertionEvidence]:
    """Inspects method/test block body for structural assertion evidence."""
    assertions: List[AssertionEvidence] = []
    lines = body_text.splitlines()

    for idx, line in enumerate(lines):
        line_num = start_line + idx
        for pat, a_type in ASSERTION_PATTERNS:
            for match in pat.finditer(line):
                target = match.group(1).strip().strip('"\'')
                assertions.append(AssertionEvidence(
                    assertion_type=a_type,
                    target=target,
                    raw_statement=line.strip(),
                    line_number=line_num,
                    is_deep_assertion=(a_type in ("STATUS_CODE", "ERROR_CODE", "RETRY_COUNT", "HEADER"))
                ))

    return assertions


class TestDiscoveryEngine:
    """Discovers and catalogs tests from the automation repository with assertion depth analysis."""

    def __init__(self, automation_repo_path: str):
        self.repo_path = os.path.abspath(automation_repo_path)
        if not os.path.exists(self.repo_path):
            raise FileNotFoundError(f"Automation repository path not found: {self.repo_path}")

    def discover_all_tests(self) -> Dict[str, DiscoveredTestCase]:
        """Scans the automation repository and returns a map of test_id -> DiscoveredTestCase."""
        tests: Dict[str, DiscoveredTestCase] = {}

        for root, _, files in os.walk(self.repo_path):
            # Skip node_modules, .git, target
            path_parts = set(Path(root).parts)
            if any(p in path_parts for p in ("node_modules", "target", ".git", ".test_index_cache")):
                continue

            for file in files:
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, self.repo_path).replace("\\", "/")

                if file.endswith(".spec.ts") or file.endswith(".test.ts"):
                    spec_tests = self._parse_playwright_spec(filepath, rel_path)
                    for t in spec_tests:
                        tests[t.test_id] = t
                elif file.endswith("Test.java") or file.endswith("Tests.java") or file.endswith("IT.java"):
                    java_tests = self._parse_selenium_java_spec(filepath, rel_path)
                    for t in java_tests:
                        tests[t.test_id] = t

        return tests

    def _parse_playwright_spec(self, filepath: str, rel_path: str) -> List[DiscoveredTestCase]:
        tests: List[DiscoveredTestCase] = []
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                lines = content.splitlines()
        except Exception:
            return []

        # Find test(...) blocks
        test_block_pat = re.compile(r'(?:test|it)\s*\(\s*["\']([^"\']+)["\']\s*,\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{')
        for match in test_block_pat.finditer(content):
            title = match.group(1)
            start_char = match.start()
            line_no = content[:start_char].count("\n") + 1

            # Approximate test body
            end_char = content.find("});", start_char)
            body = content[start_char:end_char if end_char != -1 else start_char + 1500]

            assertions = inspect_assertions_in_body(body, line_no)

            # Metadata
            tags = set(TAG_REGEX.findall(title))
            jira_keys = set(JIRA_KEY_REGEX.findall(title))

            # Endpoints
            endpoints = set()
            for ep_m in re.finditer(r'["\'](/api/v[0-9]+/[a-zA-Z0-9_\-\/]+)["\']', body):
                endpoints.add(ep_m.group(1))

            # Routes
            routes = set()
            for r_m in re.finditer(r'goto\s*\(\s*["\']([^"\']+)["\']', body):
                routes.add(r_m.group(1))

            # Methods & Headers
            methods = []
            if "POST" in body or ".post(" in body: methods.append("POST")
            if "GET" in body or ".get(" in body: methods.append("GET")

            test_id = f"{rel_path}:{line_no}:{title}"
            tests.append(DiscoveredTestCase(
                test_id=test_id,
                title=title,
                file_path=rel_path,
                line_number=line_no,
                framework="playwright-ts",
                in_regression_suite="@regression" in tags or "regression" in rel_path.lower(),
                in_smoke_suite="@smoke" in tags or "smoke" in rel_path.lower(),
                tags=sorted(list(tags)),
                jira_keys=sorted(list(jira_keys)),
                endpoints_visited=sorted(list(endpoints)),
                routes_visited=sorted(list(routes)),
                http_methods=methods,
                assertions=assertions,
                execution_status=ExecutionStatus.TEST_NOT_EXECUTED
            ))

        return tests

    def _parse_selenium_java_spec(self, filepath: str, rel_path: str) -> List[DiscoveredTestCase]:
        tests: List[DiscoveredTestCase] = []
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            return []

        class_name = Path(filepath).stem
        test_method_pat = re.compile(
            r'(@Test\s*(?:\([^)]*\))?)\s*(?:/\*\*.*?\*/\s*)?public\s+void\s+([a-zA-Z0-9_]+)\s*\([^)]*\)\s*\{'
        )

        for match in test_method_pat.finditer(content):
            annotation = match.group(1)
            method_name = match.group(2)
            start_char = match.start()
            line_no = content[:start_char].count("\n") + 1

            desc_m = re.search(r'description\s*=\s*["\']([^"\']+)["\']', annotation)
            description = desc_m.group(1) if desc_m else method_name
            full_title = f"{class_name}.{method_name} - {description}"

            end_char = content.find("\n    }", start_char)
            body = content[start_char:end_char if end_char != -1 else start_char + 1500]

            assertions = inspect_assertions_in_body(body, line_no)

            tags = set()
            if "groups" in annotation:
                for g in re.findall(r'["\']([^"\']+)["\']', annotation):
                    tags.add(f"@{g}")

            jira_keys = set(JIRA_KEY_REGEX.findall(description))
            # Also check comments directly preceding the method
            pre_chunk = content[max(0, start_char - 300):start_char]
            for jk in JIRA_KEY_REGEX.findall(pre_chunk):
                jira_keys.add(jk)

            endpoints = set()
            for ep_m in re.finditer(r'["\'](/api/v[0-9]+/[a-zA-Z0-9_\-\/]+)["\']', body + pre_chunk):
                endpoints.add(ep_m.group(1))

            test_id = f"{rel_path}:{line_no}:{class_name}.{method_name}"
            tests.append(DiscoveredTestCase(
                test_id=test_id,
                title=full_title,
                file_path=rel_path,
                line_number=line_no,
                framework="selenium-java",
                in_regression_suite="@regression" in tags or "regression" in rel_path.lower(),
                in_smoke_suite="@smoke" in tags or "smoke" in rel_path.lower(),
                tags=sorted(list(tags)),
                jira_keys=sorted(list(jira_keys)),
                endpoints_visited=sorted(list(endpoints)),
                assertions=assertions,
                execution_status=ExecutionStatus.TEST_NOT_EXECUTED
            ))

        return tests
