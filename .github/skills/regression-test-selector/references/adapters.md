# RTS Adapter Architecture & Extension Guide

This guide documents the pluggable adapter architecture in `regression-test-selector`. Adding a new test management platform or automation test framework requires a single interface implementation and a configuration mapping.

---

## 1. Test Source Adapters

A Test Source Adapter discovers tests, retrieves execution historical stats, and maps external tickets (e.g. Jira / Xray / BrowserStack Test Management) to test cases.

### Base Interface Definition (Python)

```python
class BaseTestSourceAdapter:
    """Base interface for test source management adapters."""

    def __init__(self, config: dict):
        self.config = config

    def get_tests_for_jira_key(self, jira_key: str) -> list[dict]:
        """
        Retrieves tests associated with a Jira ticket key.
        Returns a list of dicts: [{'test_id': str, 'title': str, 'status': str}]
        """
        raise NotImplementedError

    def get_test_run_metrics(self, test_id: str) -> dict:
        """
        Returns execution runtime metrics (e.g. {'avg_duration_seconds': 45.0, 'flakiness_score': 0.05}).
        """
        return {"avg_duration_seconds": 45.0, "flakiness_score": 0.0}
```

---

## 2. Available Adapters

### `repo-only` (Default, Implemented)
- **Status**: Production Ready.
- **Mechanism**: Inspects repository code directly, extracting Jira keys from test titles, code comments, annotations, and automation repository git log commit messages (`git log -n 20 --pretty=%B <file>`).
- **Dependencies**: None. Requires zero external network calls or secrets.

### `xray` (Jira Xray REST Adapter - Stub)
- **Status**: Integration Stub available.
- **Environment Variables**:
  - `JIRA_BASE_URL` (e.g. `https://jira.internal.example.com`)
  - `JIRA_API_TOKEN` or `XRAY_CLIENT_SECRET`
- **Implementation Outline**:
```python
import os, urllib.request, json

class XrayAdapter(BaseTestSourceAdapter):
    def get_tests_for_jira_key(self, jira_key: str) -> list[dict]:
        token = os.environ.get("JIRA_API_TOKEN")
        base_url = os.environ.get("JIRA_BASE_URL", self.config.get("jira_url"))
        if not token or not base_url:
            return []
        
        # GET /rest/raven/1.0/api/test?issueKey={jira_key}
        req = urllib.request.Request(
            f"{base_url}/rest/raven/1.0/api/test?issueKey={jira_key}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
                return [{"test_id": t["key"], "title": t["summary"]} for t in data]
        except Exception:
            return []
```

### `browserstack` (BrowserStack Test Management Adapter - Stub)
- **Status**: Future Migration Stub.
- **Environment Variables**:
  - `BROWSERSTACK_USERNAME`
  - `BROWSERSTACK_ACCESS_KEY`
  - `BROWSERSTACK_PROJECT_ID`
- **Interface Target**:
```python
class BrowserStackAdapter(BaseTestSourceAdapter):
    def get_tests_for_jira_key(self, jira_key: str) -> list[dict]:
        # BrowserStack Test Management REST API v2
        # GET https://api-cloud.browserstack.com/test-management/v2/projects/{project_id}/test-cases?jira_issue={jira_key}
        return []
```

---

## 3. Framework Adapters

Framework adapters parse specific file extensions into normalized test definitions.

### Base Interface Definition

```python
class BaseFrameworkAdapter:
    """Base interface for test framework parsers."""

    def detect(self, repo_dir: str) -> bool:
        """Returns True if repo uses this test framework."""
        raise NotImplementedError

    def parse_test_file(self, repo_dir: str, filepath: str) -> list[dict]:
        """Parses test definitions and metadata from a file."""
        raise NotImplementedError

    def format_run_command(self, selected_tests: list[dict], config: dict) -> str:
        """Formats framework-specific CLI execution command."""
        raise NotImplementedError
```

### Adding a New Framework Adapter (e.g. Cypress or PyTest)
1. Create `scripts/adapters/cypress.py` implementing `BaseFrameworkAdapter`.
2. Register the adapter in `build_test_index.py` `detect_framework()` and `build_index()`.
3. Set `framework: cypress` in `rts.config.yml`.
