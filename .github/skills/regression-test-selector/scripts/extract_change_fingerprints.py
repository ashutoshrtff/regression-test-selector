#!/usr/bin/env python3
"""
extract_change_fingerprints.py - Extract behavioral fingerprints and risk signals from a diff.

Part of the GitHub Copilot Agent Skill: regression-test-selector
Standard library only (Python 3.9+).
"""

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set, Tuple


# Regex patterns for change extraction
JIRA_KEY_REGEX = re.compile(r"\b([A-Z]{2,10}-\d+)\b")

# Endpoints (Spring, Express, Nest, FastAPI, Flask, .NET, Controller annotations)
ENDPOINT_PATTERNS = [
    # Spring / Java
    re.compile(r'@(Get|Post|Put|Delete|Patch|Request)Mapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'@RequestMapping\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE),
    # Express / Node / Fastify
    re.compile(r'(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE),
    # Python FastAPI / Flask
    re.compile(r'@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE),
    # .NET / C#
    re.compile(r'\[Http(Get|Post|Put|Delete|Patch)\s*(?:\(\s*["\']([^"\']+)["\']\s*\))?\]', re.IGNORECASE),
    re.compile(r'\[Route\s*\(\s*["\']([^"\']+)["\']\s*\)\]', re.IGNORECASE),
    # Generic REST path literals (e.g. "/api/v1/...")
    re.compile(r'["\'](/api/v[0-9]+/[a-zA-Z0-9_\-\/\{\}]+)["\']')
]

# UI routes (e.g., /checkout, /login, /payment/...)
ROUTE_PATTERNS = [
    re.compile(r'action\s*=\s*["\'](/[^"\']+)["\']', re.IGNORECASE),
    re.compile(r'path:\s*["\'](/[^"\']+)["\']', re.IGNORECASE),
    re.compile(r'router\.push\s*\(\s*["\'](/[^"\']+)["\']', re.IGNORECASE),
    re.compile(r'navigate\s*\(\s*["\'](/[^"\']+)["\']', re.IGNORECASE),
    re.compile(r'["\'](/checkout[a-zA-Z0-9_\-\/]*)["\']', re.IGNORECASE),
    re.compile(r'["\'](/auth[a-zA-Z0-9_\-\/]*)["\']', re.IGNORECASE),
    re.compile(r'["\'](/refund[a-zA-Z0-9_\-\/]*)["\']', re.IGNORECASE),
    re.compile(r'["\'](/report[a-zA-Z0-9_\-\/]*)["\']', re.IGNORECASE)
]

# UI labels, test-ids, button names
UI_PATTERNS = [
    re.compile(r'data-testid\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'id\s*=\s*["\'](btn-[^"\']+|pay-[^"\']+|input-[^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<button[^>]*>([^<]+)</button>', re.IGNORECASE),
    re.compile(r'aria-label\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'getByRole\s*\(\s*["\']button["\']\s*,\s*\{\s*name:\s*["\']([^"\']+)["\']\s*\}', re.IGNORECASE),
    re.compile(r'getByTestId\s*\(\s*["\']([^"\']+)["\']\s*\)', re.IGNORECASE),
]

# DTO fields, model properties
FIELD_PATTERNS = [
    re.compile(r'(?:private|public|protected)?\s+(?:String|int|long|boolean|BigDecimal|Double|List<[^>]+>)\s+([a-zA-Z0-9_]+)\s*;'),
    re.compile(r'get([A-Z][a-zA-Z0-9_]+)\s*\(\s*\)'),
    re.compile(r'set([A-Z][a-zA-Z0-9_]+)\s*\('),
    re.compile(r'(?:cardToken|cardNumber|expiryDate|securityCode|threeDsVersion|cvv|amount|currency|transactionId|refundAmount)\b', re.IGNORECASE)
]

# Feature flags
FEATURE_FLAG_PATTERNS = [
    re.compile(r'(?:ff_[a-zA-Z0-9_]+|feature_flags?\.[a-zA-Z0-9_\.]+)', re.IGNORECASE),
    re.compile(r'(?:isFeatureEnabled|isEnabled|useFlag)\s*\(\s*["\']([a-zA-Z0-9_\-\.]+)["\']', re.IGNORECASE),
    re.compile(r'LaunchDarkly|Unleash|Flipper', re.IGNORECASE)
]

# Config keys / environment variables
CONFIG_KEY_PATTERNS = [
    re.compile(r'@Value\s*\(\s*["\']\$\{([^:\}]+)(?::[^}]*)?\}["\']\s*\)'),
    re.compile(r'System\.(?:getenv|getProperty)\s*\(\s*["\']([^"\']+)["\']\s*\)'),
    re.compile(r'process\.env\.([A-Z0-9_]+)'),
    re.compile(r'([A-Z0-9_]{4,}_(?:TIMEOUT|URL|HOST|SECRET|KEY|ENABLED))\b')
]

# Error codes and messages
ERROR_CODE_PATTERNS = [
    re.compile(r'\b(ERR_[A-Z0-9_]+)\b'),
    re.compile(r'\b(INSUFFICIENT_FUNDS|CARD_DECLINED|EXPIRED_CARD|UNAUTHORIZED|INVALID_TOKEN|DUPLICATE_TXN)\b'),
    re.compile(r'errorCode\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'HttpStatus\.(UNAUTHORIZED|FORBIDDEN|BAD_REQUEST|NOT_FOUND|INTERNAL_SERVER_ERROR)'),
    re.compile(r'ResponseEntity\.status\(([0-9]{3})\)')
]

# Risk indicators based on path patterns
RISK_PATH_RULES = [
    ("auth_security", re.compile(r'(?:/auth/|/security/|Jwt|OAuth|SecurityConfig|TokenValidator|Permission)', re.IGNORECASE),
     "Changes touch security/authentication filters or token handling logic."),
    ("database_migrations", re.compile(r'(?:/migrations?/|/flyway/|/liquibase/|\.sql$|alembic|prisma)', re.IGNORECASE),
     "Database schema migration scripts detected."),
    ("dependencies", re.compile(r'(?:pom\.xml|package\.json|package-lock\.json|build\.gradle|requirements\.txt|go\.mod)', re.IGNORECASE),
     "Build manifest or external dependency versions altered."),
    ("build_pipeline", re.compile(r'(?:\.github/workflows/|Jenkinsfile|Dockerfile|\.gitlab-ci\.yml)', re.IGNORECASE),
     "CI/CD workflow or container definition touched."),
    ("shared_core", re.compile(r'(?:/common/|/core/|/shared/|/util/|BaseController|BaseService)', re.IGNORECASE),
     "Shared/core components modified; potential wide ripple effect across services.")
]


def parse_unified_diff(diff_text: str) -> List[Dict[str, Any]]:
    """
    Parses unified diff into files and hunks with line numbers.
    """
    files: List[Dict[str, Any]] = []
    current_file: Optional[Dict[str, Any]] = None
    current_hunk: Optional[Dict[str, Any]] = None
    old_line = 0
    new_line = 0

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            parts = raw_line.split()
            old_path = parts[2][2:] if len(parts) > 2 else ""
            new_path = parts[3][2:] if len(parts) > 3 else ""
            current_file = {
                "old_path": old_path,
                "new_path": new_path,
                "is_new": False,
                "is_deleted": False,
                "hunks": []
            }
            files.append(current_file)
            current_hunk = None
        elif current_file and raw_line.startswith("new file mode"):
            current_file["is_new"] = True
        elif current_file and raw_line.startswith("deleted file mode"):
            current_file["is_deleted"] = True
        elif current_file and raw_line.startswith("@@ "):
            # @@ -start,count +start,count @@
            hunk_match = re.match(r'^@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@', raw_line)
            if hunk_match:
                new_line = int(hunk_match.group(2))
                current_hunk = {
                    "header": raw_line,
                    "new_start": new_line,
                    "added_lines": [],
                    "removed_lines": [],
                    "context_lines": []
                }
                current_file["hunks"].append(current_hunk)
        elif current_hunk is not None:
            if raw_line.startswith("+") and not raw_line.startswith("+++"):
                current_hunk["added_lines"].append({"line_num": new_line, "content": raw_line[1:]})
                new_line += 1
            elif raw_line.startswith("-") and not raw_line.startswith("---"):
                current_hunk["removed_lines"].append({"content": raw_line[1:]})
            else:
                current_hunk["context_lines"].append(raw_line)
                new_line += 1

    return files


def extract_fingerprints_from_diff(diff_text: str) -> Dict[str, Any]:
    """
    Extracts structured fingerprints and risk signals from a diff.
    """
    files = parse_unified_diff(diff_text)

    endpoints: Set[str] = set()
    routes: Set[str] = set()
    ui_labels: Set[str] = set()
    dto_fields: Set[str] = set()
    feature_flags: Set[str] = set()
    config_keys: Set[str] = set()
    error_codes: Set[str] = set()
    shared_modules: Set[str] = set()
    jira_keys: Set[str] = set()
    risk_signals: List[Dict[str, str]] = []

    # Also search entire diff text for Jira keys
    for match in JIRA_KEY_REGEX.finditer(diff_text):
        jira_keys.add(match.group(1))

    for file_obj in files:
        filepath = file_obj["new_path"] or file_obj["old_path"]

        # Check risk paths
        for category, pattern, explanation in RISK_PATH_RULES:
            if pattern.search(filepath):
                # Avoid duplicate risk entries for same category
                if not any(r["category"] == category and r["file"] == filepath for r in risk_signals):
                    risk_signals.append({
                        "category": category,
                        "file": filepath,
                        "trigger": "file_path_match",
                        "explanation": explanation
                    })

        if "common" in filepath.lower() or "shared" in filepath.lower() or "util" in filepath.lower():
            shared_modules.add(filepath)

        # Inspect modified lines (added + removed) and context
        class_mapping = ""
        for hunk in file_obj["hunks"]:
            # Check context lines for class-level RequestMapping
            for cline in hunk["context_lines"]:
                crm = re.search(r'@RequestMapping\s*\(\s*["\']([^"\']+)["\']', cline, re.IGNORECASE)
                if crm:
                    class_mapping = crm.group(1).rstrip("/")

            lines_to_inspect = [line["content"] for line in hunk["added_lines"]]
            context_to_inspect = hunk["context_lines"]

            # Check if feature flag default toggled in diff
            for line in lines_to_inspect:
                if re.search(r'(?:enabled|flag|default)\s*[:=]\s*true\b', line, re.IGNORECASE):
                    # Check removed lines for false
                    for r_line in hunk["removed_lines"]:
                        if re.search(r'(?:enabled|flag|default)\s*[:=]\s*false\b', r_line["content"], re.IGNORECASE):
                            risk_signals.append({
                                "category": "feature_flag_defaults",
                                "file": filepath,
                                "trigger": "default_value_toggled",
                                "explanation": f"Feature flag or default toggled from false to true in {filepath}"
                            })
                            break

            for line in lines_to_inspect:
                # Endpoints
                for pat in ENDPOINT_PATTERNS:
                    for m in pat.finditer(line):
                        groups = [g for g in m.groups() if g]
                        if len(groups) == 2:
                            method, path = groups
                            full_path = f"{class_mapping}/{path.lstrip('/')}" if class_mapping and not path.startswith(class_mapping) else path
                            endpoints.add(f"{method.upper()} {full_path}")
                        elif len(groups) == 1:
                            val = groups[0]
                            if val.startswith("/"):
                                full_path = f"{class_mapping}/{val.lstrip('/')}" if class_mapping and not val.startswith(class_mapping) else val
                                endpoints.add(f"ANY {full_path}")

                # Routes
                for pat in ROUTE_PATTERNS:
                    for m in pat.finditer(line):
                        val = m.group(1) if m.groups() else m.group(0)
                        if val.startswith("/"):
                            routes.add(val)

                # UI Labels / selectors
                for pat in UI_PATTERNS:
                    for m in pat.finditer(line):
                        label = m.group(1).strip()
                        if label and len(label) < 60:
                            ui_labels.add(label)

                # DTO Fields
                for pat in FIELD_PATTERNS:
                    for m in pat.finditer(line):
                        field = m.group(1) if m.groups() else m.group(0)
                        if field.startswith("get") or field.startswith("set"):
                            field = field[3:]
                        if field:
                            field_name = field[0].lower() + field[1:]
                            dto_fields.add(field_name)

                # Feature flags
                for pat in FEATURE_FLAG_PATTERNS:
                    for m in pat.finditer(line):
                        flag = m.group(1) if m.groups() else m.group(0)
                        feature_flags.add(flag)

                # Config keys
                for pat in CONFIG_KEY_PATTERNS:
                    for m in pat.finditer(line):
                        key = m.group(1) if m.groups() else m.group(0)
                        config_keys.add(key)

                # Error codes
                for pat in ERROR_CODE_PATTERNS:
                    for m in pat.finditer(line):
                        err = m.group(1) if m.groups() else m.group(0)
                        error_codes.add(err)

            # Also scan context lines for relevant DTO fields and routes in immediate vicinity
            for cline in context_to_inspect:
                for pat in ROUTE_PATTERNS:
                    for m in pat.finditer(cline):
                        val = m.group(1) if m.groups() else m.group(0)
                        if val.startswith("/"):
                            routes.add(val)
                for pat in FIELD_PATTERNS:
                    for m in pat.finditer(cline):
                        field = m.group(1) if m.groups() else m.group(0)
                        if field.startswith("get") or field.startswith("set"):
                            field = field[3:]
                        if field and len(field) > 2:
                            field_name = field[0].lower() + field[1:]
                            dto_fields.add(field_name)

    # Normalize endpoints: remove ANY /path if METHOD /path exists
    specific_paths = {ep.split(" ", 1)[1] for ep in endpoints if not ep.startswith("ANY ")}
    normalized_endpoints = {ep for ep in endpoints if not (ep.startswith("ANY ") and ep.split(" ", 1)[1] in specific_paths)}

    # Contract changes risk
    for file_obj in files:
        fp = file_obj["new_path"] or file_obj["old_path"]
        if fp.endswith(".proto") or "openapi" in fp.lower() or "swagger" in fp.lower() or fp.endswith(".graphql"):
            risk_signals.append({
                "category": "contract_changes",
                "file": fp,
                "trigger": "contract_file_modified",
                "explanation": f"API Contract specification changed in {fp}"
            })

    return {
        "files_changed_count": len(files),
        "files_changed": [f["new_path"] or f["old_path"] for f in files],
        "jira_keys": sorted(list(jira_keys)),
        "endpoints": sorted(list(normalized_endpoints)),
        "routes": sorted(list(routes)),
        "ui_labels": sorted(list(ui_labels)),
        "dto_fields": sorted(list(dto_fields)),
        "feature_flags": sorted(list(feature_flags)),
        "config_keys": sorted(list(config_keys)),
        "error_codes": sorted(list(error_codes)),
        "shared_modules": sorted(list(shared_modules)),
        "risk_signals": risk_signals
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract behavioral fingerprints and risk signals from a unified diff."
    )
    parser.add_argument(
        "--diff-file",
        type=str,
        help="Path to unified diff file. If omitted and no base/head provided, reads from stdin."
    )
    parser.add_argument(
        "--base",
        type=str,
        help="Base git reference (e.g. main or commit hash) for git diff."
    )
    parser.add_argument(
        "--head",
        type=str,
        help="Head git reference (e.g. feature-branch or PR head) for git diff."
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Format output JSON with indentation."
    )

    parser.add_argument(
        "--output",
        type=str,
        help="Optional file path to write output JSON."
    )

    args = parser.parse_args()

    diff_content = ""
    if args.base and args.head:
        cmd = ["git", "diff", f"{args.base}...{args.head}"]
        sys.stderr.write(f"Executing: {' '.join(cmd)}\n")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            sys.stderr.write(f"Error running git diff: {res.stderr}\n")
            sys.exit(1)
        diff_content = res.stdout
    elif args.diff_file:
        if not os.path.exists(args.diff_file):
            sys.stderr.write(f"Error: diff file '{args.diff_file}' does not exist.\n")
            sys.exit(1)
        with open(args.diff_file, "r", encoding="utf-8", errors="replace") as f:
            diff_content = f.read()
    else:
        # Check if stdin has content
        if sys.stdin.isatty():
            sys.stderr.write("Error: No diff input provided. Pipe a diff into stdin or use --diff-file / --base / --head.\n")
            parser.print_help(sys.stderr)
            sys.exit(1)
        diff_content = sys.stdin.read()

    if not diff_content.strip():
        sys.stderr.write("Warning: Empty diff provided.\n")
        output = {
            "files_changed_count": 0,
            "files_changed": [],
            "jira_keys": [],
            "endpoints": [],
            "routes": [],
            "ui_labels": [],
            "dto_fields": [],
            "feature_flags": [],
            "config_keys": [],
            "error_codes": [],
            "shared_modules": [],
            "risk_signals": []
        }
    else:
        output = extract_fingerprints_from_diff(diff_content)

    sys.stderr.write(
        f"Extracted {len(output['endpoints'])} endpoints, {len(output['routes'])} routes, "
        f"{len(output['ui_labels'])} UI labels, {len(output['jira_keys'])} Jira keys, "
        f"{len(output['risk_signals'])} risk signals.\n"
    )

    indent = 2 if args.pretty else None
    json_str = json.dumps(output, indent=indent)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
        sys.stderr.write(f"Fingerprints written to {args.output}\n")
    else:
        print(json_str)


if __name__ == "__main__":
    main()
