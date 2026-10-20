#!/usr/bin/env python3
"""
itaf.adapters.browserstack - BrowserStack Test Management Adapter.

Supports upcoming enterprise migration to BrowserStack Test Management.
Connects via REST API v2 when credentials are configured, or uses fixture mode.
"""

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional

from itaf.adapters.base import BaseTestManagementAdapter
from itaf.core.models import DiscoveredTestCase, RequirementTestMapping, ExecutionStatus


class BrowserStackAdapter(BaseTestManagementAdapter):
    """BrowserStack Test Management REST / Fixture Adapter."""

    def __init__(self, fixture_evidence_path: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.fixture_evidence_path = fixture_evidence_path
        self.username = os.environ.get("BROWSERSTACK_USERNAME") or self.config.get("browserstack_username")
        self.access_key = os.environ.get("BROWSERSTACK_ACCESS_KEY") or self.config.get("browserstack_access_key")
        self.project_id = os.environ.get("BROWSERSTACK_PROJECT_ID") or self.config.get("browserstack_project_id")

    def get_adapter_name(self) -> str:
        return "browserstack"

    def is_live_connection(self) -> bool:
        return bool(self.username and self.access_key and self.project_id)

    def fetch_test_cases(self) -> List[DiscoveredTestCase]:
        return []

    def fetch_execution_evidence(self) -> Dict[str, Dict[str, Any]]:
        if self.is_live_connection():
            try:
                # BrowserStack Test Management REST API v2
                url = f"https://api-cloud.browserstack.com/test-management/v2/projects/{self.project_id}/test-runs"
                # Basic Auth
                import base64
                auth_str = f"{self.username}:{self.access_key}".encode()
                auth_b64 = base64.b64encode(auth_str).decode()
                req = urllib.request.Request(
                    url,
                    headers={"Authorization": f"Basic {auth_b64}", "Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw = json.loads(resp.read().decode())
                    results = {}
                    for item in raw.get("test_cases", []):
                        status = "EXECUTION_PASSED" if item.get("status") == "passed" else "EXECUTION_FAILED"
                        results[item["id"]] = {
                            "status": status,
                            "timestamp": item.get("updated_at"),
                            "duration": float(item.get("duration", 0.0)),
                            "source": "LIVE_BROWSERSTACK_API"
                        }
                    return results
            except Exception as e:
                import sys
                sys.stderr.write(f"[BrowserStackAdapter WARNING] Live API call failed ({e}). Reverting to fixture fallback.\n")

        if self.fixture_evidence_path and os.path.exists(self.fixture_evidence_path):
            with open(self.fixture_evidence_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    k: {
                        "status": v.get("status", "EXECUTION_PASSED"),
                        "timestamp": v.get("timestamp", "2026-10-20T10:00:00Z"),
                        "duration": float(v.get("duration", 3.1)),
                        "source": "FIXTURE_MOCK (Simulated BrowserStack Data)"
                    }
                    for k, v in data.items()
                }

        return {}

    def fetch_requirement_mappings(self) -> List[RequirementTestMapping]:
        return []
