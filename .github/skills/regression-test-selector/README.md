# Regression Test Selector (RTS) Skill Package

This directory contains the complete, reusable **GitHub Copilot Agent Skill** `regression-test-selector`.

Please refer to the main [README.md](../../../README.md) in the repository root for full details on installation, architecture, benchmarks, and demo instructions.

## Directory Contents

- `SKILL.md`: The GitHub Copilot Agent Skill definition and procedural instructions.
- `config/`: Example configuration templates (`rts.config.example.yml`, `service-map.example.yml`).
- `scripts/`: Zero-dependency Python 3.9+ automation scripts:
  - `fetch_automation_repo.py`: Clones/syncs automation repos (supports local, github.com, `*.ghe.com`, GHES).
  - `build_test_index.py`: Indexes Playwright TS and Selenium Java tests with 1-level Page Object resolution.
  - `extract_change_fingerprints.py`: Extracts endpoints, routes, UI labels, DTOs, flags, error codes, and risk signals from diffs.
  - `matcher.py`: Core rule-based evidence ranking engine, gap detector, and report formatter.
  - `init_config.py`: Interactive / flag-driven configuration generator.
  - `backtest.py`: Historical benchmarking and defect recall evaluation tool.
- `references/`: Architectural guides for matching/ranking, framework adapters, and test source integrations.
- `templates/`: Markdown report template (`report.md`).
- `examples/`: Sample report (`sample-report.md`) and fixtures (`fake-automation-repo` and `dev-diffs`).
- `tests/`: Automated unit and integration test suite (`run_all_tests.py`).

## Quick Test Execution
```bash
python tests/run_all_tests.py
```
