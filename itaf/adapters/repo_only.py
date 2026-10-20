#!/usr/bin/env python3
"""
itaf.adapters.repo_only - Default Git and Source Repository Test Management Adapter.

Operates purely on local and cloned automation repository files, parsing comments,
titles, and commit logs with zero external network dependencies.
"""

from typing import Any, Dict, List, Optional

from itaf.adapters.base import BaseTestManagementAdapter
from itaf.core.models import DiscoveredTestCase, RequirementTestMapping
from itaf.engine.test_discovery import TestDiscoveryEngine


class RepoOnlyAdapter(BaseTestManagementAdapter):
    """Zero-dependency source repository adapter."""

    def __init__(self, automation_repo_path: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.automation_repo_path = automation_repo_path
        self.discovery_engine = TestDiscoveryEngine(automation_repo_path)

    def get_adapter_name(self) -> str:
        return "repo-only"

    def is_live_connection(self) -> bool:
        return True # Local files are live real evidence

    def fetch_test_cases(self) -> List[DiscoveredTestCase]:
        tests_map = self.discovery_engine.discover_all_tests()
        return list(tests_map.values())

    def fetch_execution_evidence(self) -> Dict[str, Dict[str, Any]]:
        # In repo-only mode without CI exports, execution results default to TEST_NOT_EXECUTED
        return {}

    def fetch_requirement_mappings(self) -> List[RequirementTestMapping]:
        # CrossRepoMapper derives mappings automatically from code
        return []
