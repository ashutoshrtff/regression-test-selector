"""
ITAF Adapters - Test management adapters for repo-only, Jira Xray, and BrowserStack.
"""

from itaf.adapters.base import BaseTestManagementAdapter
from itaf.adapters.repo_only import RepoOnlyAdapter
from itaf.adapters.xray import XrayAdapter
from itaf.adapters.browserstack import BrowserStackAdapter

__all__ = [
    "BaseTestManagementAdapter",
    "RepoOnlyAdapter",
    "XrayAdapter",
    "BrowserStackAdapter"
]
