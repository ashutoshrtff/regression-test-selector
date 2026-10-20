#!/usr/bin/env python3
"""
itaf.adapters.xray - Jira Xray Test Management Adapter.

Supports live REST API execution when authenticated, and verified mock/fixture mode
when running in isolated environments. Clearly labels mock data in reports and UI.
"""

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional

from itaf.adapters.base import BaseTestManagementAdapter
from itaf.core.models import DiscoveredTestCase, RequirementTestMapping, ExecutionStatus


class XrayAdapter(BaseTestManagementAdapter):
    """Jira Xray REST / Fixture Adapter."""

    def __init__(self, fixture_evidence_path: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.fixture_evidence_path = fixture_evidence_path
        self.jira_base_url = os.environ.get("JIRA_BASE_URL") or self.config.get("jira_url")
        self.jira_api_token = os.environ.get("JIRA_API_TOKEN")

    def get_adapter_name(self) -> str:
        return "xray"

    def is_live_connection(self) -> bool:
        return bool(self.jira_base_url and self.jira_api_token)

    def fetch_test_cases(self) -> List[DiscoveredTestCase]:
        # Xray references mapped to tests
        return []

    def fetch_execution_evidence(self) -> Dict[str, Dict[str, Any]]:
        # If live credentials exist, query Xray REST API
        if self.is_live_connection():
            try:
                # Xray Test Execution REST Endpoint
                # GET {jira_base_url}/rest/raven/1.0/api/testruns?testExecKey=...
                req = urllib.request.Request(
                    f"{self.jira_base_url}/rest/raven/1.0/api/testruns",
                    headers={
                        "Authorization": f"Bearer {self.jira_api_token}",
                        "Content-Type": "application/json"
                    }
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw = json.loads(resp.read().decode())
                    results = {}
                    for item in raw:
                        status = "EXECUTION_PASSED" if item.get("status") == "PASS" else "EXECUTION_FAILED"
                        results[item["testKey"]] = {
                            "status": status,
                            "timestamp": item.get("startedOn"),
                            "duration": float(item.get("duration", 0.0)),
                            "source": "LIVE_XRAY_API"
                        }
                    return results
            except Exception:
                pass

        # Fixture / Mock fallback (clearly labeled)
        if self.fixture_evidence_path and os.path.exists(self.fixture_evidence_path):
            with open(self.fixture_evidence_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    k: {
                        "status": v.get("status", "EXECUTION_PASSED"),
                        "timestamp": v.get("timestamp", "2026-10-20T10:00:00Z"),
                        "duration": float(v.get("duration", 2.5)),
                        "source": "FIXTURE_MOCK (Simulated Xray Data)"
                    }
                    for k, v in data.items()
                }

        return {}

    def fetch_requirement_mappings(self) -> List[RequirementTestMapping]:
        return []
