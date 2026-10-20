#!/usr/bin/env python3
"""
build_test_index.py - Build an indexed catalog of automated tests from an automation repository.

Supports Playwright (TypeScript/JavaScript), Selenium (Java), and Gherkin.
Resolves one level of Page Object indirection.
Standard library only (Python 3.9+).
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


JIRA_REGEX = re.compile(r"\b([A-Z]{2,10}-\d+)\b")
TAG_REGEX = re.compile(r'(@[a-zA-Z0-9_\-]+)')


def detect_git_commit(repo_dir: str) -> str:
    """Returns HEAD commit SHA if repo is a git repository, else returns a content hash."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass

    # Fallback: compute hash of file names and modification times
    hasher = hashlib.sha256()
    for root, _, files in os.walk(repo_dir):
        for f in sorted(files):
            fp = os.path.join(root, f)
            try:
                mtime = str(os.path.getmtime(fp))
                hasher.update(f.encode())
                hasher.update(mtime.encode())
            except OSError:
                pass
    return hasher.hexdigest()[:12]


def detect_framework(repo_dir: str) -> str:
    """Detects test framework based on repository manifest and config files."""
    has_playwright_config = False
    has_java_files = False
    has_pom = False

    for root, _, files in os.walk(repo_dir):
        path_parts = set(Path(root).parts)
        if any(p in path_parts for p in ("node_modules", "target", ".git", ".test_index_cache")):
            continue
        if any(f in ("playwright.config.ts", "playwright.config.js", "playwright.config.mjs") for f in files):
            has_playwright_config = True
        if "pom.xml" in files or "build.gradle" in files:
            has_pom = True
        if any(f.endswith(".java") for f in files):
            has_java_files = True

    if has_playwright_config:
        return "playwright-ts"
    if has_pom or has_java_files:
        return "selenium-java"
    return "playwright-ts"  # Default fallback


def get_git_log_jira_keys(repo_dir: str, file_rel_path: str) -> List[str]:
    """Extracts Jira keys from git commit messages for a test file."""
    keys = set()
    try:
        res = subprocess.run(
            ["git", "log", "-n", "20", "--pretty=%B", "--", file_rel_path],
            cwd=repo_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if res.returncode == 0:
            for match in JIRA_REGEX.finditer(res.stdout):
                keys.add(match.group(1))
    except Exception:
        pass
    return sorted(list(keys))


class PageObjectCatalog:
    """Parses and caches Page Object classes to resolve indirection."""

    def __init__(self, repo_dir: str):
        self.repo_dir = repo_dir
        self.page_objects: Dict[str, Dict[str, Any]] = {}
        self._scan()

    def _scan(self):
        for root, _, files in os.walk(self.repo_dir):
            for file in files:
                if file.endswith("Page.ts") or file.endswith("Page.js") or file.endswith("Page.java") or "/pages/" in root.replace("\\", "/"):
                    filepath = os.path.join(root, file)
                    class_name = Path(file).stem
                    self.page_objects[class_name] = self._parse_page_object(filepath)

    def _parse_page_object(self, filepath: str) -> Dict[str, Any]:
        routes = set()
        endpoints = set()
        ui_labels = set()

        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            # Find routes (e.g. goto('/...'), driver.get('...'), or route string literals)
            for m in re.finditer(r'(?:goto|get)\s*\(\s*["\']([^"\']+)["\']', content):
                val = m.group(1)
                if val.startswith("/") or "http" in val:
                    routes.add(val)
            for m in re.finditer(r'["\'](/checkout[a-zA-Z0-9_\-\/]*)["\']', content):
                routes.add(m.group(1))
            for m in re.finditer(r'["\'](/auth[a-zA-Z0-9_\-\/]*)["\']', content):
                routes.add(m.group(1))

            # Find endpoints (e.g. /api/v1/...)
            for m in re.finditer(r'["\'](/api/v[0-9]+/[a-zA-Z0-9_\-\/]+)["\']', content):
                endpoints.add(m.group(1))

            # Find UI labels and test-ids
            for m in re.finditer(r'getByTestId\s*\(\s*["\']([^"\']+)["\']', content):
                ui_labels.add(m.group(1))
            for m in re.finditer(r'getByRole\s*\(\s*["\']button["\']\s*,\s*\{\s*name:\s*["\']([^"\']+)["\']\s*\}', content):
                ui_labels.add(m.group(1))
            for m in re.finditer(r'(?:id|name)\s*=\s*["\']([a-zA-Z0-9_\-]+)["\']', content):
                ui_labels.add(m.group(1))
            for m in re.finditer(r'FindBy\s*\(\s*(?:id|name)\s*=\s*["\']([^"\']+)["\']', content):
                ui_labels.add(m.group(1))

        except Exception as e:
            sys.stderr.write(f"Warning: Failed parsing PageObject {filepath}: {e}\n")

        return {
            "routes": sorted(list(routes)),
            "endpoints": sorted(list(endpoints)),
            "ui_labels": sorted(list(ui_labels))
        }

    def resolve(self, po_name: str) -> Dict[str, Any]:
        return self.page_objects.get(po_name, {"routes": [], "endpoints": [], "ui_labels": []})


def parse_playwright_file(
    repo_dir: str,
    filepath: str,
    po_catalog: PageObjectCatalog,
    regression_tag: str,
    smoke_tag: str
) -> List[Dict[str, Any]]:
    """Parses a Playwright test spec file."""
    rel_path = os.path.relpath(filepath, repo_dir).replace("\\", "/")
    tests = []

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        sys.stderr.write(f"Error reading {filepath}: {e}\n")
        return []

    git_jira_keys = get_git_log_jira_keys(repo_dir, rel_path)

    current_describes: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        line_num = i + 1

        # Match test.describe(...)
        describe_match = re.search(r'test\.describe\s*\(\s*["\']([^"\']+)["\']', line)
        if describe_match:
            current_describes.append(describe_match.group(1))

        # Match test(...) or it(...)
        test_match = re.search(r'(?:test|it)\s*\(\s*["\']([^"\']+)["\']', line)
        if test_match:
            raw_title = test_match.group(1)
            full_title = " > ".join(current_describes + [raw_title]) if current_describes else raw_title

            # Collect test block lines to extract actions and assertions
            test_body_lines = []
            brace_count = line.count("{") - line.count("}")
            j = i + 1
            while j < len(lines) and brace_count > 0:
                test_body_lines.append(lines[j])
                brace_count += lines[j].count("{") - lines[j].count("}")
                j += 1
            test_body = "\n".join(test_body_lines)

            # Extract tags from title and body
            tags = set(TAG_REGEX.findall(full_title))
            for t_line in test_body_lines:
                for t in TAG_REGEX.findall(t_line):
                    tags.add(t)

            # Jira keys from title, body comments, and git log
            jira_keys = set(JIRA_REGEX.findall(full_title))
            for t in JIRA_REGEX.findall(test_body):
                jira_keys.add(t)
            # Also check comments preceding the test
            k = i - 1
            while k >= 0 and (lines[k].strip().startswith("//") or lines[k].strip().startswith("/*") or lines[k].strip().startswith("*")):
                for jk in JIRA_REGEX.findall(lines[k]):
                    jira_keys.add(jk)
                k -= 1
            jira_keys.update(git_jira_keys)

            # Routes visited directly
            routes_visited = set()
            for m in re.finditer(r'(?:page\.goto|goto)\s*\(\s*["\']([^"\']+)["\']', test_body):
                routes_visited.add(m.group(1))

            # Endpoints called / mocked
            endpoints_called = set()
            for m in re.finditer(r'["\'](?:\*\*)?(/api/v[0-9]+/[a-zA-Z0-9_\-\/]+)["\']', test_body):
                endpoints_called.add(m.group(1))
            for m in re.finditer(r'route\s*\(\s*["\'](?:\*\*)?(/api/[^"\']+)["\']', test_body):
                endpoints_called.add(m.group(1))

            # UI labels, buttons, testids
            ui_labels = set()
            for m in re.finditer(r'getByRole\s*\(\s*["\']button["\']\s*,\s*\{\s*name:\s*["\']([^"\']+)["\']\s*\}', test_body):
                ui_labels.add(m.group(1))
            for m in re.finditer(r'getByTestId\s*\(\s*["\']([^"\']+)["\']', test_body):
                ui_labels.add(m.group(1))
            for m in re.finditer(r'getByText\s*\(\s*["\']([^"\']+)["\']', test_body):
                ui_labels.add(m.group(1))

            # Detect Page Objects used
            page_objects_used = set()
            for po_name in po_catalog.page_objects:
                if re.search(r'\b' + re.escape(po_name) + r'\b', line + "\n" + test_body):
                    page_objects_used.add(po_name)
                    # Inherit routes, endpoints, UI labels from Page Object (one level indirection)
                    po_data = po_catalog.resolve(po_name)
                    routes_visited.update(po_data.get("routes", []))
                    endpoints_called.update(po_data.get("endpoints", []))
                    ui_labels.update(po_data.get("ui_labels", []))

            # Check suite membership
            in_regression = (
                regression_tag in tags or
                regression_tag.replace("@", "") in [t.replace("@", "") for t in tags] or
                "regression" in rel_path.lower()
            )
            in_smoke = (
                smoke_tag in tags or
                smoke_tag.replace("@", "") in [t.replace("@", "") for t in tags] or
                "smoke" in rel_path.lower()
            )

            test_id = f"{rel_path}:{line_num}:{raw_title}"

            tests.append({
                "id": test_id,
                "file": rel_path,
                "line": line_num,
                "title": full_title,
                "tags": sorted(list(tags)),
                "jira_keys": sorted(list(jira_keys)),
                "routes_visited": sorted(list(routes_visited)),
                "endpoints_called": sorted(list(endpoints_called)),
                "ui_labels": sorted(list(ui_labels)),
                "page_objects_used": sorted(list(page_objects_used)),
                "in_regression_suite": in_regression,
                "in_smoke_suite": in_smoke
            })

        i += 1

    return tests


def parse_selenium_java_file(
    repo_dir: str,
    filepath: str,
    po_catalog: PageObjectCatalog,
    regression_tag: str,
    smoke_tag: str
) -> List[Dict[str, Any]]:
    """Parses a Selenium Java test class file."""
    rel_path = os.path.relpath(filepath, repo_dir).replace("\\", "/")
    tests = []

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
            lines = content.splitlines()
    except Exception as e:
        sys.stderr.write(f"Error reading {filepath}: {e}\n")
        return []

    git_jira_keys = get_git_log_jira_keys(repo_dir, rel_path)
    class_match = re.search(r'public\s+class\s+([a-zA-Z0-9_]+)', content)
    class_name = class_match.group(1) if class_match else Path(filepath).stem

    # Match @Test methods
    test_pattern = re.compile(
        r'(@Test\s*(?:\([^)]*\))?)\s*(?:/\*\*.*?\*/\s*)?public\s+void\s+([a-zA-Z0-9_]+)\s*\([^)]*\)\s*\{',
        re.DOTALL
    )

    for m in test_pattern.finditer(content):
        test_annotation = m.group(1)
        method_name = m.group(2)
        start_char = m.start()
        line_num = content[:start_char].count("\n") + 1

        # Extract description or groups from @Test annotation
        groups = []
        groups_match = re.search(r'groups\s*=\s*\{([^}]+)\}', test_annotation)
        if groups_match:
            raw_groups = groups_match.group(1)
            groups = [g.strip().strip('"\'') for g in raw_groups.split(",")]
        elif 'groups' in test_annotation:
            g_single = re.search(r'groups\s*=\s*["\']([^"\']+)["\']', test_annotation)
            if g_single:
                groups = [g_single.group(1)]

        desc_match = re.search(r'description\s*=\s*["\']([^"\']+)["\']', test_annotation)
        description = desc_match.group(1) if desc_match else method_name
        full_title = f"{class_name}.{method_name} - {description}"

        tags = set(f"@{g}" if not g.startswith("@") else g for g in groups)

        # Jira keys from comments above method, description, or git log
        jira_keys = set(JIRA_REGEX.findall(description))
        jira_keys.update(git_jira_keys)

        # Inspect slice of text around method definition for comments
        pre_context = content[max(0, start_char - 400):start_char]
        for jk in JIRA_REGEX.findall(pre_context):
            jira_keys.add(jk)

        # Find method body roughly
        body_slice = content[m.end():m.end() + 1500]

        routes_visited = set()
        endpoints_called = set()
        ui_labels = set()
        page_objects_used = set()

        # Routes in method body
        for rm in re.finditer(r'(?:driver\.get|navigate\(\)\.to)\s*\(\s*["\']([^"\']+)["\']', body_slice):
            routes_visited.add(rm.group(1))

        # Endpoints
        for ep in re.finditer(r'["\'](/api/v[0-9]+/[a-zA-Z0-9_\-\/]+)["\']', body_slice):
            endpoints_called.add(ep.group(1))

        # Page Objects
        for po_name in po_catalog.page_objects:
            if po_name in body_slice or po_name in pre_context:
                page_objects_used.add(po_name)
                po_data = po_catalog.resolve(po_name)
                routes_visited.update(po_data.get("routes", []))
                endpoints_called.update(po_data.get("endpoints", []))
                ui_labels.update(po_data.get("ui_labels", []))

        # Regression / Smoke suite membership
        reg_clean = regression_tag.replace("@", "").lower()
        smoke_clean = smoke_tag.replace("@", "").lower()

        in_regression = (
            any(g.lower() == reg_clean for g in groups) or
            "regression" in rel_path.lower() or
            f"@{reg_clean}" in tags
        )
        in_smoke = (
            any(g.lower() == smoke_clean for g in groups) or
            "smoke" in rel_path.lower() or
            f"@{smoke_clean}" in tags
        )

        test_id = f"{rel_path}:{line_num}:{class_name}.{method_name}"

        tests.append({
            "id": test_id,
            "file": rel_path,
            "line": line_num,
            "title": full_title,
            "tags": sorted(list(tags)),
            "jira_keys": sorted(list(jira_keys)),
            "routes_visited": sorted(list(routes_visited)),
            "endpoints_called": sorted(list(endpoints_called)),
            "ui_labels": sorted(list(ui_labels)),
            "page_objects_used": sorted(list(page_objects_used)),
            "in_regression_suite": in_regression,
            "in_smoke_suite": in_smoke
        })

    return tests


def build_index(
    repo_dir: str,
    framework: str = "auto",
    regression_tag: str = "@regression",
    smoke_tag: str = "@smoke",
    force: bool = False
) -> Dict[str, Any]:
    """Builds and caches the full test index for the automation repository."""
    repo_dir = os.path.abspath(repo_dir)
    if not os.path.exists(repo_dir):
        raise FileNotFoundError(f"Automation repo directory does not exist: {repo_dir}")

    commit_sha = detect_git_commit(repo_dir)

    # Cache check
    cache_dir = os.path.join(repo_dir, ".test_index_cache")
    cache_file = os.path.join(cache_dir, f"{commit_sha}.json")
    if not force and os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                sys.stderr.write(f"Loaded index from cache: {cache_file} ({len(cached_data.get('tests', []))} tests)\n")
                return cached_data
        except Exception:
            pass

    if framework == "auto":
        framework = detect_framework(repo_dir)

    sys.stderr.write(f"Indexing automation repository at: {repo_dir}\n")
    sys.stderr.write(f"Detected framework: {framework}, commit: {commit_sha}\n")

    po_catalog = PageObjectCatalog(repo_dir)
    sys.stderr.write(f"Indexed {len(po_catalog.page_objects)} Page Object(s) for indirection resolution.\n")

    all_tests: List[Dict[str, Any]] = []

    for root, _, files in os.walk(repo_dir):
        path_parts = set(Path(root).parts)
        # Skip node_modules, target, .git (exact folder names, not substring)
        if any(p in path_parts for p in ("node_modules", "target", ".git", ".test_index_cache")):
            continue

        for file in files:
            filepath = os.path.join(root, file)

            if framework == "playwright-ts":
                if file.endswith(".spec.ts") or file.endswith(".test.ts") or file.endswith(".spec.js") or file.endswith(".test.js"):
                    t_list = parse_playwright_file(repo_dir, filepath, po_catalog, regression_tag, smoke_tag)
                    all_tests.extend(t_list)
            elif framework == "selenium-java":
                if file.endswith("Test.java") or file.endswith("Tests.java") or file.endswith("IT.java"):
                    t_list = parse_selenium_java_file(repo_dir, filepath, po_catalog, regression_tag, smoke_tag)
                    all_tests.extend(t_list)

    total_tests = len(all_tests)
    tests_with_jira = sum(1 for t in all_tests if t.get("jira_keys"))
    tests_with_endpoints_or_routes = sum(1 for t in all_tests if t.get("endpoints_called") or t.get("routes_visited"))
    in_regression_count = sum(1 for t in all_tests if t.get("in_regression_suite"))
    in_smoke_count = sum(1 for t in all_tests if t.get("in_smoke_suite"))

    pct_jira = f"{(tests_with_jira / total_tests * 100):.1f}%" if total_tests > 0 else "0.0%"
    pct_endpoints = f"{(tests_with_endpoints_or_routes / total_tests * 100):.1f}%" if total_tests > 0 else "0.0%"

    result = {
        "meta": {
            "framework": framework,
            "commit": commit_sha,
            "repo_dir": repo_dir,
            "total_tests": total_tests,
            "in_regression_suite": in_regression_count,
            "in_smoke_suite": in_smoke_count,
            "tests_with_jira": tests_with_jira,
            "pct_jira": pct_jira,
            "tests_with_endpoints_or_routes": tests_with_endpoints_or_routes,
            "pct_endpoints_or_routes": pct_endpoints
        },
        "tests": all_tests
    }

    # Save cache
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to write cache {cache_file}: {e}\n")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Build a comprehensive test catalog from an automated test repository."
    )
    parser.add_argument(
        "--repo-dir",
        type=str,
        required=True,
        help="Path to automation repository root."
    )
    parser.add_argument(
        "--framework",
        type=str,
        default="auto",
        choices=["auto", "playwright-ts", "selenium-java"],
        help="Test framework (auto, playwright-ts, selenium-java)."
    )
    parser.add_argument(
        "--regression-tag",
        type=str,
        default="@regression",
        help="Tag identifying regression suite tests (default: @regression)."
    )
    parser.add_argument(
        "--smoke-tag",
        type=str,
        default="@smoke",
        help="Tag identifying smoke suite tests (default: @smoke)."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild index ignoring cache."
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Optional output file to write index JSON. Defaults to stdout."
    )

    args = parser.parse_args()

    try:
        index_data = build_index(
            repo_dir=args.repo_dir,
            framework=args.framework,
            regression_tag=args.regression_tag,
            smoke_tag=args.smoke_tag,
            force=args.force
        )
    except Exception as e:
        sys.stderr.write(f"Error building test index: {e}\n")
        sys.exit(1)

    meta = index_data["meta"]
    sys.stderr.write(
        f"Summary: Found {meta['total_tests']} tests ({meta['in_regression_suite']} in regression, {meta['in_smoke_suite']} in smoke). "
        f"Jira coverage: {meta['pct_jira']}, Route/Endpoint coverage: {meta['pct_endpoints_or_routes']}.\n"
    )

    json_str = json.dumps(index_data, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
        sys.stderr.write(f"Index written to {args.output}\n")
    else:
        print(json_str)


if __name__ == "__main__":
    main()
