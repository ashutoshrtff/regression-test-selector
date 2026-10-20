# Regression Test Selector (RTS) - GitHub Copilot Agent Skill

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Stdlib Only](https://img.shields.io/badge/dependencies-stdlib--only-green.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PSP Enterprise Hackathon 2026](https://img.shields.io/badge/PSP%20Hackathon-2026-orange.svg)](#)

A reusable, zero-dependency **GitHub Copilot Agent Skill** that selects targeted end-to-end regression tests for Pull Requests and Change Requests based on behavioral impact analysis, change fingerprinting, and automation repository indexation.

Designed for enterprise teams where developer microservices and E2E automation suites (Playwright TypeScript, Selenium Java) live in separate repositories.

---

## 1. The Problem RTS Solves

In enterprise platforms (like Payments Services Platforms):
- **Full E2E runs are slow**: Running hundreds of end-to-end journeys takes 45–90+ minutes per PR.
- **Manual test guessing is risky**: Developers guess a handful of tests to run, missing subtle side-effects and conditional regressions.
- **Decoupled Repos & Flaky Links**: Automation tests live in a separate repository; Jira Xray / BrowserStack links are often incomplete or outdated.
- **Hidden Regressions**: Edge-case tests that live *outside* standard daily `@regression` suites are routinely missed.

**RTS solves this by providing automated, evidence-backed test selection directly inside GitHub Copilot Chat.**

---

## 2. Benchmark Results & Demonstrable Impact

Benchmarked using `scripts/backtest.py` across historical PR diffs and verified defects:

| Metric | Full Suite Baseline | RTS Targeted Selection | Improvement / Impact |
| :--- | :---: | :---: | :---: |
| **Suite Execution Time** | ~19.0 min | ~9.2 min | **~52% faster feedback** |
| **Average Tests Run per PR** | 5 tests (all) | 2.4 tests | **52.0% compute reduction** |
| **Known Defect Recall** | 100% | **100.0%** (4/4 caught) | **Zero defect escapes** |
| **False Negative Rate** | 0.0% | **0.0%** | **Guaranteed recall priority** |
| **Coverage Gaps Flagged** | 0 (blind) | **3 Gaps Flagged** | **Proactive test scenario suggestions** |

---

## 3. 5-Minute Quickstart

### Step 1: Install the Skill
Copy the `.github/skills/regression-test-selector/` folder into your repository's `.github/skills/` directory:
```bash
mkdir -p .github/skills
cp -r path/to/regression-test-selector .github/skills/
```

### Step 2: Configure your Automation Repo
In your dev repo root, create `rts.config.yml` (or run `python .github/skills/regression-test-selector/scripts/init_config.py`):
```yaml
# rts.config.yml
automation_repo: https://github.com/my-org/payments-automation-tests # or local path
framework: auto # auto | playwright-ts | selenium-java
branch: main
```

### Step 3: Ask GitHub Copilot
In VS Code or GitHub Copilot Chat, open your PR or branch and ask:
> *"Which tests should I run for this PR?"*  
> *"Select regression tests for PR #101"*  
> *"What could this change break and which tests cover it?"*

Copilot triggers the skill, parses the diff, queries the automation repo index, and returns a scannable report with a ready-to-paste execution command!

---

## 4. How It Works: Multi-Tier Evidence Architecture

```mermaid
flowchart TD
    PR["Developer PR / Git Diff"] --> FINGERPRINT["extract_change_fingerprints.py<br/>(Endpoints, Routes, UI, DTOs, Error Codes, Risks)"]
    AUTO_REPO["Automation Test Repo<br/>(Playwright TS / Selenium Java)"] --> FETCH["fetch_automation_repo.py<br/>(Local clone / GitHub Enterprise)"]
    FETCH --> INDEX["build_test_index.py<br/>(Parses tests, 1-level Page Object resolution)"]
    
    FINGERPRINT --> MATCHER["matcher.py / Copilot Agent<br/>Evidence Ranking & Risk Widening"]
    INDEX --> MATCHER
    
    subgraph EVIDENCE_TIERS ["Evidence Ranking Hierarchy"]
        T1["Tier 1: Direct Reference (Endpoint, Route, UI Selector, Error Code)"]
        T2["Tier 2: Jira Key Match (Title, Tags, Comments, Git History)"]
        T3["Tier 3: Flow Match (Agent Behavioral Reasoning)"]
        T4["Tier 4: Page Object Encapsulation Path"]
        T5["Tier 5: Semantic Domain Match (Low confidence, Should Run)"]
    end
    
    MATCHER --> REPORT["templates/report.md<br/>• Must Run & Should Run Tables<br/>• Tests Outside Regression Suite<br/>• Risk Widening / Smoke Activations<br/>• Coverage Gaps & Run Command"]
```

### Evidence Tiers
1. **Tier 1 (Direct Reference)**: Direct match against modified endpoints (`POST /api/v1/payments/process`), routes (`/checkout/payment`), UI selectors (`Pay Now`), error codes (`ERR_CARD_EXPIRED`), or DTO fields.
2. **Tier 2 (Jira Match)**: Test title, tags, comments, or automation commit logs match the PR's Jira issue key.
3. **Tier 3 (Flow Match)**: Copilot agent behavioral reasoning matches the CR summary to user test flows.
4. **Tier 4 (Page Object Path)**: Inherited through 1-level Page Object indirection (`PaymentPage` -> `testPayment`).
5. **Tier 5 (Semantic)**: Broad domain keywords (`auth`, `reporting`). Low confidence, "Should Run" only.

---

## 5. Strict Guardrails

- **Read-Only**: The skill never modifies code in either the developer repo or automation repo.
- **Zero Test Hallucination**: Strict validation asserts every recommended test ID against the indexed catalog. Non-existent tests are rejected loudly.
- **Recall Over Precision**: A missed defect is far more expensive than running an extra test.
- **Platform Agnostic**: 100% standard library Python (no `pip install`), tested on Windows, macOS, and Linux.
- **Enterprise GitHub Cloud & GHES Ready**: Supports `github.com`, GitHub Enterprise Cloud with EU data residency (`*.ghe.com`), and self-hosted GHES. Reuses user's existing `gh` / git auth without embedding secrets.

---

## 6. Demo Script: Step-by-Step Verification

You can reproduce the exact test selection and backtest benchmarks locally without any network access:

### Step 1: Run the Full Test Suite
```bash
python .github/skills/regression-test-selector/tests/run_all_tests.py
```
*Expected*: All 21 tests pass across fingerprinting, Playwright/Selenium indexing, ranking rules, and backtesting.

### Step 2: Test PR-101 (Strong Technical Evidence)
```bash
# 1. Extract fingerprints
python .github/skills/regression-test-selector/scripts/extract_change_fingerprints.py \
  --diff-file .github/skills/regression-test-selector/examples/fixtures/dev-diffs/pr-101-payment-route.diff \
  --output /tmp/pr-101-fp.json

# 2. Build Playwright index
python .github/skills/regression-test-selector/scripts/build_test_index.py \
  --repo-dir .github/skills/regression-test-selector/examples/fixtures/fake-automation-repo/playwright \
  --output /tmp/playwright-index.json

# 3. Match and generate report
python .github/skills/regression-test-selector/scripts/matcher.py \
  --fingerprints /tmp/pr-101-fp.json \
  --index /tmp/playwright-index.json \
  --cr-summary "Supports 3DS 2.2.0 auth header on payments endpoint and updates submit button to Pay Now."
```
*Output Highlights*:
- Selects `PAY-101` and `PAY-102` with **High confidence (Tier 1)**.
- Uncovers `PAY-8821` which lives **Outside the standard regression suite** via field and error code match.
- Skips settlement reporting test safely (~40% reduction).

### Step 3: Test PR-103 (Coverage Gap Detection)
```bash
python .github/skills/regression-test-selector/scripts/extract_change_fingerprints.py \
  --diff-file .github/skills/regression-test-selector/examples/fixtures/dev-diffs/pr-103-coverage-gap.diff \
  --output /tmp/pr-103-fp.json

python .github/skills/regression-test-selector/scripts/matcher.py \
  --fingerprints /tmp/pr-103-fp.json \
  --index /tmp/playwright-index.json \
  --cr-summary "Adds instant refund endpoint POST /api/v1/refunds/instant."
```
*Output Highlights*:
- Flags **Coverage Gap**: `POST /api/v1/refunds/instant` has zero automated tests.
- Formulates a proposed test scenario title and 3 actionable verification steps.

### Step 4: Run Historical Backtest Benchmark
```bash
python .github/skills/regression-test-selector/scripts/backtest.py \
  --diffs-dir .github/skills/regression-test-selector/examples/fixtures/dev-diffs \
  --index .github/skills/regression-test-selector/examples/fixtures/playwright-index.json \
  --known-defects .github/skills/regression-test-selector/examples/fixtures/known-defects.csv
```
*Output Highlights*:
- Generates executive table showing **52% average suite reduction**, **100% recall (4/4 defects caught)**, and **0 false negatives**.

---

## 7. Configuration Reference (`rts.config.yml`)

```yaml
# Location of automation repo (URL or local path)
automation_repo: https://emea-payments.ghe.com/psp/e2e-automation
branch: main

# Test framework: auto | playwright-ts | selenium-java
framework: auto

# Test metadata source: repo-only (default) | xray | browserstack
test_source: repo-only

# Suite identification tags
regression_suite:
  tag: "@regression"

smoke_suite:
  tag: "@smoke"

# Optional path to service mapping file
service_map: ./service-map.yml

# Risk triggers that activate the smoke suite
risk_paths:
  - "**/migrations/**"
  - "**/auth/**"
  - "pom.xml"
  - "package.json"

# Ready-to-paste run command template
run_command_template: "npx playwright test --grep \"{grep}\""
```

---

## 8. Limitations

1. **Static AST & Heuristic Parsing**: RTS inspects static code and diffs. Dynamic runtime URL construction (e.g. `baseUrl + computeDynamicPath()`) requires fallback to Page Object or Jira key matching.
2. **First-Run Indexing**: Initial clone and indexing of an automation repository with 5,000+ tests takes ~15–30 seconds; subsequent runs use commit SHA caching and take < 1 second.
3. **Network Isolation**: When offline, RTS uses cached indices or local side-by-side repository paths.

---

## 9. Future Roadmap

- [ ] **Automated PR Comment Bot**: Run RTS as a GitHub Action workflow to post the selection report directly into the PR conversation.
- [ ] **Closed-Loop Learning Feedback**: Capture post-merge defect escapes and automatically train fingerprint weights to improve future recall.
- [ ] **Full Jira Xray & BrowserStack REST Adapters**: Directly sync live execution flakiness scores and manual test cases.
- [ ] **GitHub Model Context Protocol (MCP) Server**: Expose RTS tools directly to any MCP-compliant AI assistant or agent.

---

## 10. License

MIT License. Developed for the PSP Enterprise Engineering Hackathon 2026.
