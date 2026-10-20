#!/usr/bin/env python3
"""
itaf.adapters.base - Pluggable Test Management Adapter Interface.

Defines vendor-neutral interfaces for Xray, BrowserStack, and Repo-Only test discovery
and execution evidence retrieval without vendor lock-in.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from itaf.core.models import DiscoveredTestCase, RequirementTestMapping, ExecutionStatus


class BaseTestManagementAdapter(ABC):
    """Abstract interface for test management platforms."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    @abstractmethod
    def get_adapter_name(self) -> str:
        """Returns the identifier name of the adapter."""
        pass

    @abstractmethod
    def is_live_connection(self) -> bool:
        """Returns True if connected to real live API, False if operating on local fixtures/mocks."""
        pass

    @abstractmethod
    def fetch_test_cases(self) -> List[DiscoveredTestCase]:
        """Discovers test cases registered in the test management system."""
        pass

    @abstractmethod
    def fetch_execution_evidence(self) -> Dict[str, Dict[str, Any]]:
        """
        Retrieves recent test execution results.
        Returns: { test_id: { "status": "EXECUTION_PASSED"|"EXECUTION_FAILED", "timestamp": "...", "duration": float } }
        """
        pass

    @abstractmethod
    def fetch_requirement_mappings(self) -> List[RequirementTestMapping]:
        """Retrieves existing issue-to-test links from the test management platform."""
        pass
