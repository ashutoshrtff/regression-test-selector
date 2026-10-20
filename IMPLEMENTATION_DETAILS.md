# IMPLEMENTATION DETAILS — Intelligent Test Assurance Framework (ITAF) & Regression Test Selector (RTS)

> **Last Updated**: 2026-10-20  
> **Project**: Regression Test Selector — PSP Enterprise Engineering Hackathon 2026  
> **Language**: Python 3.9+ (100% stdlib, zero external dependencies)  
> **License**: MIT  

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Problem Statement](#2-problem-statement)
3. [Architecture Overview](#3-architecture-overview)
4. [Directory Structure](#4-directory-structure)
5. [Core Data Models (`itaf/core/`)](#5-core-data-models-itafcore)
6. [Parsers (`itaf/parsers/`)](#6-parsers-itafparsers)
7. [Engine (`itaf/engine/`)](#7-engine-itafengine)
8. [Adapters (`itaf/adapters/`)](#8-adapters-itafadapters)
9. [Reports (`itaf/reports/`)](#9-reports-itafreports)
10. [Web UI (`itaf/ui/`)](#10-web-ui-itafui)
11. [CLI (`itaf/cli.py` & `itaf_cli.py`)](#11-cli-itafclipy--itaf_clipy)
12. [Quality Gate Policy Rules (`gates/`)](#12-quality-gate-policy-rules-gates)
13. [JSON Schemas (`schemas/`)](#13-json-schemas-schemas)
14. [Examples & Fixtures (`examples/`)](#14-examples--fixtures-examples)
15. [GitHub Copilot Skill (`.github/skills/`)](#15-github-copilot-skill-githubskills)
16. [Configuration Reference](#16-configuration-reference)
17. [Data Flow & Pipeline](#17-data-flow--pipeline)
18. [Evidence Tier Ranking System](#18-evidence-tier-ranking-system)
19. [Guardrails & Safety](#19-guardrails--safety)
20. [Benchmark Results](#20-benchmark-results)
21. [API Endpoints (Web Server)](#21-api-endpoints-web-server)
22. [Class & Module Reference](#22-class--module-reference)
23. [Enum Reference](#23-enum-reference)
24. [File Inventory](#24-file-inventory)
25. [Future Roadmap](#25-future-roadmap)
26. [Changelog](#26-changelog)

---

## 1. Project Overview

The **Intelligent Test Assurance Framework (ITAF)** is a comprehensive, zero-dependency Python framework that combines two major capabilities:

- **Capability A — Requirement-Driven Coverage Intelligence**: Parses engineering specifications (OpenAPI, Feature Documents, ISO 20022 Message Specs), extracts canonical requirements and expected outcomes, discovers automated tests from cross-repository automation suites (Playwright TypeScript, Selenium Java), evaluates assertion depth, and produces auditable coverage assessments with mandatory quality gate outcomes.

- **Capability B — Smart Regression Test Selection (RTS)**: Given a code change (git diff), extracts behavioral fingerprints (endpoints, routes, UI selectors, error codes, DTO fields, risk signals), maps them to affected requirements and expected outcomes, and produces a ranked test selection with priority (`MUST_RUN`, `SHOULD_RUN`, `SMOKE_ONLY`), confidence levels, and coverage gap warnings.

The project is designed for **enterprise Payments Services Platforms (PSP)** where developer microservices and end-to-end automation suites live in **separate repositories**.

### Key Design Principles

| Principle | Description |
|:---|:---|
| **Zero Dependencies** | 100% Python standard library — no `pip install` needed |
| **Read-Only** | Never modifies code in developer or automation repos |
| **Zero Test Hallucination** | Every recommended test ID is validated against the indexed catalog |
| **Recall Over Precision** | A missed defect is far more expensive than running an extra test |
| **Platform Agnostic** | Works on Windows, macOS, and Linux |
| **Enterprise Ready** | Supports `github.com`, GitHub Enterprise Cloud (EU `*.ghe.com`), and self-hosted GHES |
| **Provenance Tracking** | Every requirement, outcome, and mapping is traceable to its source artifact, section, and line number |

---

## 2. Problem Statement

In enterprise payment platforms:

1. **Full E2E runs are slow**: Running hundreds of end-to-end journeys takes 45–90+ minutes per PR.
2. **Manual test guessing is risky**: Developers guess a handful of tests, missing subtle side-effects and conditional regressions.
3. **Decoupled Repos & Flaky Links**: Automation tests live in a separate repository; Jira Xray / BrowserStack links are often incomplete or outdated.
4. **Hidden Regressions**: Edge-case tests outside standard daily `@regression` suites are routinely missed.
5. **No Quality Gate Enforcement**: Mandatory compliance controls (PCI-DSS, ISO 20022, retry resilience) have no automated validation mechanism.

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         INPUT ARTIFACTS                                │
│  ┌─────────────┐  ┌─────────────────┐  ┌─────────────────┐           │
│  │  OpenAPI     │  │ Feature Spec    │  │ Message Spec    │           │
│  │  (.yaml)     │  │ (.md)           │  │ (.json)         │           │
│  └──────┬───────┘  └───────┬─────────┘  └───────┬─────────┘           │
│         │                  │                     │                     │
│         ▼                  ▼                     ▼                     │
│  ┌──────────────────────────────────────────────────────────┐         │
│  │              PARSERS (itaf/parsers/)                      │         │
│  │  OpenAPIParser  FeatureParser  MessageFormatParser         │         │
│  └──────────────────────┬────────────────────────────────────┘         │
│                         │ List[Requirement]                            │
│                         ▼                                              │
│  ┌──────────────────────────────────────────────────────────┐         │
│  │              ENGINE (itaf/engine/)                         │         │
│  │                                                           │         │
│  │  PolicyEngine ──────► Quality Gate Evaluation             │         │
│  │  TestDiscoveryEngine ► Discovers tests + assertion depth  │         │
│  │  CrossRepoMapper ───► Requirement ↔ Test mapping          │         │
│  │  CoverageIntelligenceEngine ► Coverage assessments        │         │
│  │  RegressionSelector ► Change-driven test selection        │         │
│  └──────────────────────┬────────────────────────────────────┘         │
│                         │                                              │
│         ┌───────────────┼───────────────┐                             │
│         ▼               ▼               ▼                             │
│  ┌────────────┐  ┌────────────┐  ┌────────────────┐                  │
│  │ CLI Output │  │ Markdown   │  │ Web Dashboard  │                  │
│  │ (Terminal) │  │ Report     │  │ (5-screen UI)  │                  │
│  └────────────┘  └────────────┘  └────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Directory Structure

```
Regression test selector/
├── .github/
│   └── skills/
│       └── regression-test-selector/        # GitHub Copilot Agent Skill
│           ├── SKILL.md                     # Skill definition for Copilot
│           ├── README.md                    # Skill documentation
│           ├── config/                      # Example configuration files
│           │   ├── rts.config.example.yml
│           │   └── service-map.example.yml
│           ├── examples/
│           │   ├── sample-report.md
│           │   └── fixtures/               # Test fixtures for backtesting
│           │       ├── dev-diffs/           # Sample PR diffs (5 files)
│           │       ├── fake-automation-repo/ # Mock Playwright & Selenium repos
│           │       ├── known-defects.csv
│           │       ├── playwright-index.json
│           │       └── selenium-index.json
│           ├── references/                  # Reference documentation
│           ├── scripts/                     # Standalone RTS scripts
│           │   ├── backtest.py
│           │   ├── build_test_index.py
│           │   ├── extract_change_fingerprints.py
│           │   ├── fetch_automation_repo.py
│           │   ├── init_config.py
│           │   └── matcher.py
│           ├── templates/                   # Report templates
│           └── tests/                       # 21 RTS unit/integration tests
│               ├── run_all_tests.py
│               ├── test_backtest.py
│               ├── test_fetch_repo.py
│               ├── test_fingerprints.py
│               ├── test_index_builder.py
│               └── test_ranking.py
├── examples/
│   └── sample_feature/                     # ITAF sample feature directory
│       ├── ADR-004-idempotency-and-resilience.md
│       ├── execution-evidence.json         # Labeled fixture execution evidence
│       ├── payment-api.v1.yaml             # Sample OpenAPI spec
│       ├── payment-submission-feature.md   # Sample feature spec
│       ├── pr-payment-retry-change.diff    # Sample code diff
│       ├── swift-pacs008-payment.json      # Sample ISO 20022 message spec
│       └── tests/payments/
│           └── payment-submission.spec.ts  # Sample Playwright test suite
├── gates/                                  # Quality gate policy rule packs
│   ├── common/
│   │   ├── api.yaml                        # API contract & schema gates (2 rules)
│   │   └── security.yaml                   # Authentication & authorization gates (2 rules)
│   ├── domains/
│   │   └── payments.yaml                   # Payment-specific gates (idempotency, dedup, amounts - 3 rules)
│   └── resilience/
│       ├── circuit-breaker.yaml            # Circuit breaker gates (1 rule)
│       └── retry.yaml                      # Retry & backoff gates (2 rules)
├── itaf/                                   # Main Python package (Zero pip dependencies)
│   ├── __init__.py
│   ├── cli.py                              # Unified CLI (5 subcommands, 225 lines)
│   ├── adapters/                           # Test management platform adapters
│   │   ├── __init__.py
│   │   ├── base.py                         # Abstract adapter interface (47 lines)
│   │   ├── browserstack.py                 # BrowserStack REST adapter (82 lines)
│   │   ├── repo_only.py                    # Local git repository adapter (40 lines)
│   │   └── xray.py                         # Jira Xray REST adapter (83 lines)
│   ├── core/                               # Data models, schema validation & cache
│   │   ├── __init__.py
│   │   ├── cache.py                        # SHA-256 artifact hashing cache (71 lines)
│   │   ├── models.py                       # 14 dataclasses + 7 enums (211 lines)
│   │   └── schemas.py                      # JSON Schema loader & validator (79 lines)
│   ├── engine/                             # Core deterministic processing engines
│   │   ├── __init__.py
│   │   ├── coverage_intelligence.py        # Coverage assessment engine (201 lines)
│   │   ├── cross_repo_mapper.py            # Requirement-to-test mapping (180 lines)
│   │   ├── policy_engine.py                # Quality gate evaluation (376 lines)
│   │   ├── regression_selector.py          # Smart regression selector (189 lines)
│   │   └── test_discovery.py               # Test discovery & assertion inspector (240 lines)
│   ├── parsers/                            # Specification parsers
│   │   ├── __init__.py
│   │   ├── feature_parser.py               # Markdown feature/story parser (230 lines)
│   │   ├── message_parser.py               # ISO 20022 / JSON message parser (90 lines)
│   │   └── openapi_parser.py               # OpenAPI 3.0+ / Swagger 2.0 parser (339 lines)
│   ├── reports/
│   │   ├── __init__.py
│   │   └── generator.py                    # Markdown audit report generator (133 lines)
│   └── ui/                                 # Interactive web dashboard
│       ├── __init__.py
│       ├── server.py                       # Hardened HTTP server (stdlib http.server, 296 lines)
│       └── static/
│           ├── app.js                      # Frontend JavaScript (vanilla, 240 lines)
│           ├── index.html                  # 5-screen SPA layout (313 lines)
│           └── styles.css                  # Enterprise-grade CSS (398 lines)
├── schemas/                                # JSON Schema definitions
│   ├── coverage-result.schema.json
│   ├── policy-rule.schema.json
│   ├── regression-decision.schema.json
│   ├── requirement.schema.json
│   └── test-case.schema.json
├── tests/                                  # ITAF Core Unit & Integration Test Suite
│   ├── run_all_tests.py                    # Unified test runner (45 tests, stdlib unittest)
│   └── test_itaf_core.py                   # 24 core ITAF tests (parsers, gates, mapping, false-assurance, cache, security)
├── .gitignore
├── itaf_cli.py                             # Root CLI entrypoint (8 lines)
├── README.md                               # Project README
└── IMPLEMENTATION_DETAILS.md               # ← This file
```

**Project Statistics**: 83 source files, 45 automated tests (100% passing in ~2s), zero pip dependencies (100% Python 3.9+ standard library).

---

## 5. Core Data Models (`itaf/core/`)

### File: `itaf/core/models.py` (211 lines)

Contains **6 enumerations** and **9 dataclasses** that form the canonical, technology-neutral data model for the entire framework. All models use Python's `dataclasses` module and are fully serializable.

#### Enumerations (6)

| Enum | Values | Purpose |
|:---|:---|:---|
| `RequirementType` | `FUNCTIONAL`, `POSITIVE`, `NEGATIVE`, `SECURITY`, `IDEMPOTENCY`, `DUPLICATE_DETECTION`, `RESILIENCE_RETRY`, `CIRCUIT_BREAKER`, `API_CONTRACT`, `DATA_INTEGRITY`, `OBSERVABILITY` | Classifies the type of requirement |
| `RequirementOrigin` | `EXPLICIT_SPEC`, `POLICY_GATE`, `INFERRED` | Tracks where the requirement came from |
| `RuleSeverity` | `BLOCKER`, `CRITICAL`, `MAJOR`, `MINOR` | Severity level for quality gates |
| `MappingConfidence` | `CONFIRMED`, `HIGH`, `MEDIUM`, `LOW`, `AMBIGUOUS`, `MISSING` | Confidence level of requirement→test mapping |
| `CoverageStatus` | `COVERED`, `PARTIALLY_COVERED`, `MISSING_COVERAGE`, `BLOCKED`, `AMBIGUOUS`, `NOT_APPLICABLE` | Coverage state of a requirement |
| `ExecutionStatus` | `EXECUTION_PASSED`, `EXECUTION_FAILED`, `TEST_NOT_EXECUTED`, `EVIDENCE_MISSING` | Last execution result |

#### Dataclasses (9)

| Dataclass | Key Fields | Purpose |
|:---|:---|:---|
| `Provenance` | `artifact_path`, `artifact_type`, `section`, `line_number`, `identifier`, `extracted_at` | Tracks origin of every extracted data item |
| `ExpectedOutcome` | `outcome_id`, `requirement_id`, `outcome_type`, `description`, `target_interface`, `expected_status_code`, `expected_headers`, `expected_error_code`, `required_assertions` | A discrete verifiable behavior that must be demonstrated |
| `Requirement` | `requirement_id`, `title`, `description`, `req_type`, `origin`, `domain`, `service`, `interface`, `mandatory`, `severity`, `applicable_rule_ids`, `expected_outcomes`, `acceptance_criteria`, `ambiguity_notes` | Canonical engineering/business requirement |
| `AssertionEvidence` | `assertion_type`, `target`, `raw_statement`, `line_number`, `is_deep_assertion` | Assertion extracted from test body via AST inspection |
| `DiscoveredTestCase` | `test_id`, `title`, `file_path`, `line_number`, `framework`, `in_regression_suite`, `in_smoke_suite`, `tags`, `jira_keys`, `endpoints_visited`, `routes_visited`, `http_methods`, `headers_sent`, `assertions`, `page_objects_used`, `execution_status` | A cataloged automated test |
| `RequirementTestMapping` | `requirement_id`, `outcome_id`, `test_id`, `confidence`, `evidence_summary`, `asserts_outcome`, `mapping_source`, `is_override`, `override_reason` | Explicit mapping from requirement to test with explainable confidence |
| `PolicyRule` | `rule_id`, `name`, `category`, `description`, `severity`, `mandatory`, `applies_to`, `required_outcomes`, `failure_criteria`, `source_standard`, `version` | A deterministic organizational quality gate |
| `RequirementCoverageAssessment` | `requirement_id`, `title`, `domain`, `service`, `coverage_status`, `mapped_tests`, `uncovered_outcomes`, `applicable_rules`, `failing_gate_ids`, `execution_status`, `assessment_notes`, `suggested_test_scenario` | Full coverage evaluation for a single requirement |
| `RegressionSelectionDecision` | `test_id`, `title`, `file_path`, `framework`, `in_regression_suite`, `priority`, `confidence`, `selection_reasons`, `affected_requirement_ids`, `affected_outcomes`, `triggered_by_gates` | A ranked test selection recommendation |

### File: `itaf/core/cache.py` (71 lines)

- **`ArtifactCache`**: In-memory artifact cache keyed by SHA-256 digests. Eliminates redundant file I/O, regex AST scans, and YAML parsing during iterative CLI assessments and web UI interactions.
- **`compute_file_sha256(file_path)`**: Computes deterministic SHA-256 hex digest of file contents on disk.
- **`GLOBAL_ARTIFACT_CACHE`**: Process-wide cache singleton shared across CLI operations, the web server, and pipeline runs.

### File: `itaf/core/schemas.py` (79 lines)

- **`load_schema(schema_name)`**: Loads JSON Schema files from the `schemas/` directory by name.
- **`validate_dict(instance, schema)`**: Validates a dict against a JSON Schema. Uses `jsonschema` library if available; otherwise falls back to a thorough built-in validator that checks required fields, type constraints, enum constraints, and regex patterns — all using standard library only.

---

## 6. Parsers (`itaf/parsers/`)

Three deterministic parsers extract canonical `Requirement` objects with full provenance tracking.

### `OpenAPIParser` — `openapi_parser.py` (339 lines)

**Purpose**: Parses OpenAPI 3.0+ and Swagger 2.0 specifications into canonical `Requirement` and `ExpectedOutcome` objects with full provenance tracking.

**Input**: YAML or JSON OpenAPI spec file (validates spec presence; raises `ValueError` if file is empty or whitespace).

**Extraction Logic**:
- Iterates over all `paths` → `operations` (GET, POST, PUT, DELETE, PATCH).
- For each operation, generates:
  1. **API Contract Requirement** (`RequirementType.API_CONTRACT`): Expects success responses (200/201) and client error (400) linked to `GATE-API-001` and `GATE-API-002`.
  2. **Security Requirement** (`RequirementType.SECURITY`): Expects HTTP 401 Unauthorized for missing auth and HTTP 403 Forbidden for insufficient role/permissions. Generated when `security` schemes are detected or for mutating HTTP methods (`POST`, `PUT`, `DELETE`), linked to `GATE-SEC-001` and `GATE-SEC-002`.
  3. **Idempotency Requirement** (`RequirementType.IDEMPOTENCY`): Generated when `Idempotency-Key` header parameter is detected or for mutating `POST` operations in the PAYMENTS domain, linked to `GATE-PAY-001`.

**YAML Fallback**: Includes an enhanced lightweight built-in YAML parser (`_parse_yaml_or_json`) that works without PyYAML by regex-parsing paths, methods, parameters (including header parameters like `Idempotency-Key`), security schemes, operationIds, summaries, and response status codes.

### `FeatureParser` — `feature_parser.py` (230 lines)

**Purpose**: Parses Markdown feature specifications, user stories, and MVDs (Minimum Viable Documents).

**Extraction Logic**:
- **Generic Markdown Requirements**: Scans for `### Requirement ...` sections and extracts bulleted acceptance criteria (`- ` / `* `).
- **Business Duplicate Detection**: Scans for `duplicate detection`, `velocity window`, `409 Conflict` → generates `RequirementType.DUPLICATE_DETECTION` requirement with `GATE-PAY-002`.
- **Resilience & Retry**: Scans for `retry behaviour`, `transient failure`, `503`, `backoff`, `downstream timeout` → generates `RequirementType.RESILIENCE_RETRY` requirement with `GATE-RET-001`, `GATE-RET-002`.
- **Ambiguity Detection**: Flags requirements lacking concrete operational parameters (e.g., retry mandated but max retry count or backoff duration unspecified) in `ambiguity_notes`.
- **Jira Key Extraction**: Extracts Jira keys dynamically from document text using regex `[A-Z]{2,10}-\d+`.
- **Target Interface**: Identifies target interface via regex for HTTP methods and paths (`POST /api/v1/...`).

### `MessageFormatParser` — `message_parser.py` (90 lines)

**Purpose**: Parses ISO 20022 (pacs.008) and JSON payment message specifications.

**Input**: JSON file with `message_type`, `mandatory_fields`, and `interface`.

**Extraction Logic**:
- For each mandatory field (e.g., `amount`, `currency`, `debtorAccount`, `creditorAccount`), generates an `ExpectedOutcome` of type `DATA_INTEGRITY` expecting HTTP 400 when the field is missing.
- Links to `GATE-PAY-003` (Payment Amount and Currency Integrity).

---

## 7. Engine (`itaf/engine/`)

Five deterministic engines that form the core processing pipeline.

### `PolicyEngine` — `policy_engine.py` (376 lines)

**Purpose**: Loads, validates, and deterministically evaluates quality gates without relying on heuristic guesses.

**Key Methods**:

| Method | Signature | Description |
|:---|:---|:---|
| `__init__` | `(gates_dir=None)` | Loads all YAML rule files from `gates/`, validates each against `policy-rule.schema.json` |
| `_load_rules` | `()` | Recursively walks `gates/` directory, parses YAML (with PyYAML or built-in parser), validates, and stores `PolicyRule` objects |
| `get_applicable_rules` | `(requirement) → List[PolicyRule]` | Matches rules based on `requirement.applicable_rule_ids` or requirement domain/type alignment |
| `evaluate_gate` | `(rule, requirement, mapped_tests, all_tests) → (passes, explanation, severity)` | Evaluates specific gate against structured assertion evidence |

**Decoupled Rule Applicability**:
Rule applicability is cleanly separated from gate compliance. Rules are only evaluated against requirements they explicitly govern (via `applicable_rule_ids` or matching domain/type). Irrelevant rules are excluded rather than evaluated as passing or failing.

**Structured Assertion Verification for All 10 Gates**:
- **GATE-SEC-001 (Authentication)**: Verifies mapped tests contain `STATUS_CODE` assertions targeting `401` or auth-specific error codes.
- **GATE-SEC-002 (Authorization RBAC)**: Verifies mapped tests contain `STATUS_CODE` assertions targeting `403` or role-denial error codes.
- **GATE-API-001 (API Contract Compliance)**: Verifies assertions checking HTTP `200`/`201` success status and schema response fields.
- **GATE-API-002 (Input Validation)**: Verifies assertions checking HTTP `400` status code for invalid or malformed payloads.
- **GATE-PAY-001 (Idempotency)**: Verifies assertions targeting `IDEMPOTENCY_FLAG` or `Idempotency-Key` headers.
- **GATE-PAY-002 (Duplicate Detection)**: Verifies assertions targeting HTTP `409` or `DUPLICATE_PAYMENT` error codes.
- **GATE-PAY-003 (Amount/Currency Integrity)**: Verifies assertions for amount/currency constraints and rejection of invalid monetary values.
- **GATE-RET-001 (Retry Policy)**: Verifies assertions on `RETRY_COUNT` or HTTP `503` transient failure recovery.
- **GATE-RET-002 (Backoff and Jitter)**: Verifies assertions checking retry delays or exponential backoff parameters.
- **GATE-CB-001 (Circuit Breaker)**: Verifies assertions checking circuit breaker trip and open-state behavior.

**Anti-False-Positive Guardrails**:
Tests with generic assertions or empty test bodies cannot satisfy domain gates. Raw keyword substring matching (e.g. tests mentioning `"auth"` or `"conflict"` in variables or comments) is rejected.

### `TestDiscoveryEngine` — `test_discovery.py` (240 lines)

**Purpose**: Discovers and catalogs automated tests from cross-repository automation suites, with deep assertion structure inspection.

**Supported Frameworks**:
- **Playwright TypeScript** (`.spec.ts`, `.test.ts`)
- **Selenium Java** (`*Test.java`, `*Tests.java`, `*IT.java`)

**Discovery Process**:

1. Walks the automation repository path, skipping `node_modules`, `target`, `.git`.
2. For **Playwright** files:
   - Regex-matches `test('...', async (...) => {` blocks.
   - Extracts test title, line number, Jira keys, tags, endpoints (`/api/v1/...`), routes (`goto('...')`), HTTP methods.
   - Matches braces to extract full test body.
   - Runs `inspect_assertions_in_body()` on the body.
3. For **Selenium Java** files:
   - Regex-matches `@Test` annotated `public void` methods.
   - Extracts description from annotation, Jira keys from comments preceding the method.
   - Same assertion inspection.

**Assertion Pattern Recognition** (`inspect_assertions_in_body`):

| Pattern | Assertion Type | Example Match |
|:---|:---|:---|
| `status().toBe(200)` | `STATUS_CODE` | `expect(response.status).toBe(200)` |
| `errorCode == 'DUPLICATE_PAYMENT'` | `ERROR_CODE` | `expect(body.errorCode).toBe('...')` |
| `headers['idempotency-key']` | `HEADER` | `getHeader("Idempotency-Key")` |
| `idempotency_verified == true` | `IDEMPOTENCY_FLAG` | `expect(body.idempotency_verified).toBe(true)` |
| `retryCount >= 1` | `RETRY_COUNT` | `expect(attempts).toBe(3)` |
| `getByText('Pay Now')` | `UI_TEXT` | `page.getByText('Pay Now')` |
| `expect(...).toBeVisible()` | `GENERIC_ASSERTION` | `expect(element).toBeVisible()` |
| `Assert.assertTrue(...)` | `GENERIC_ASSERTION` | Java-style assertions |

**Deep vs Shallow**: `STATUS_CODE`, `ERROR_CODE`, `RETRY_COUNT`, and `HEADER` assertions are flagged as `is_deep_assertion=True`, distinguishing tests that genuinely verify outcomes from tests that merely visit endpoints.

### `CrossRepoMapper` — `cross_repo_mapper.py` (180 lines)

**Purpose**: Maps canonical requirements to automated tests using multi-signal evidence, producing explainable confidence scores.

**Key Correctness Improvements**:
- **Case-Insensitive Interface Matching**: Lowercases both requirement interfaces and test endpoints/routes to eliminate false-negative mapping misses.
- **Dynamic Jira Extraction**: Extracts Jira keys from requirement descriptions and titles using regex `[A-Z]{2,10}-\d+` rather than relying on hardcoded lists.
- **Multi-Outcome Mapping**: Maps every discrete `ExpectedOutcome` within a requirement independently; removed premature loop break.
- **Strict Negative & Data Integrity Matching**: Ensures tests asserting HTTP 401 cannot satisfy HTTP 403 outcomes; negative amount tests cannot satisfy missing currency or debtor account outcomes.

**Mapping Signals**:

| Signal | Weight | Logic |
|:---|:---|:---|
| **Jira Key Match** | Medium | Test's Jira keys match requirement identifier |
| **Interface Match** | High | Test's `endpoints_visited` matches requirement's `interface` endpoint |
| **Assertion Depth** | Highest | Test has assertions matching the outcome type (idempotency, duplicate detection, retry, security, status code) |

**Confidence Determination**:

| Condition | Confidence Level |
|:---|:---|
| asserts_outcome + interface_match + jira_match | `CONFIRMED` |
| asserts_outcome + interface_match | `HIGH` |
| interface_match + jira_match | `HIGH` |
| interface_match only | `MEDIUM` |
| jira_match only | `MEDIUM` |
| Semantic keyword overlap only | `LOW` (excluded from mappings) |

**Override Support**: Allows explicit `{ requirement_id: [test_ids] }` overrides that produce `CONFIRMED` confidence mappings with `MANUAL_OVERRIDE` source.

### `CoverageIntelligenceEngine` — `coverage_intelligence.py` (201 lines)

**Purpose**: Evaluates requirements against discovered tests and execution evidence, producing comprehensive `RequirementCoverageAssessment` objects.

**Key Correctness Improvements**:
- **Multi-Index Execution Lookup**: Indexes execution evidence by both raw `test_id` (`file:line:title`) and composite key `(file_path, title)`. Prevents line number shifts from invalidating execution evidence.
- **Empty Outcomes Guardrail**: Explicitly guards against false coverage: if `len(expected_outcomes) == 0`, requirement is classified as `CoverageStatus.AMBIGUOUS` with explanatory notes rather than incorrectly defaulting to `COVERED`.
- **Zero Applicable Gates Notation**: Explicitly records an audit note when zero quality gates apply to a requirement, ensuring transparency in compliance audits.

**Assessment Pipeline** (for each requirement):

1. **Map Requirements to Tests**: Uses `CrossRepoMapper.map_requirement_to_tests()`.
2. **Evaluate Quality Gates**: Uses `PolicyEngine.get_applicable_rules()` + `evaluate_gate()`.
3. **Determine Uncovered Outcomes**: Compares covered outcome IDs from mapped tests against required outcomes.
4. **Determine Coverage Status**:
   - `AMBIGUOUS` if requirement has zero outcomes or `ambiguity_notes`
   - `MISSING_COVERAGE` if no mapped tests
   - `COVERED` if all outcomes covered and all gates passed
   - `PARTIALLY_COVERED` if some outcomes covered or some tests assert outcomes
   - `MISSING_COVERAGE` otherwise
5. **Determine Execution Status**: Aggregates from mapped tests' execution evidence via multi-index lookup.
6. **Generate Suggested Scenario**: If coverage is missing/partial, generates concrete test title + verification steps.

### `RegressionSelector` — `regression_selector.py` (189 lines)

**Purpose**: Selects and prioritizes tests based on code change fingerprints and requirement impact.

**Selection Pipeline**:

1. **Identify Affected Requirements**: Compares changed endpoints, routes, Jira keys, mapped tests, and suggested scenario interfaces against assessment data.
2. **Select Tests Mapped to Affected Requirements**: 
   - Tests with `asserts_outcome=True` → `MUST_RUN`
   - Tests without deep assertions → `SHOULD_RUN`
   - Tests are deduplicated; if same test covers multiple requirements, reasons are aggregated and priority is promoted.
3. **Detect Coverage Gaps**: Affected requirements with `MISSING_COVERAGE`, `PARTIALLY_COVERED`, `AMBIGUOUS`, or `BLOCKED` generate `unmitigated_gaps` and `warning_notes` with recommended new test scenarios.
4. **Conservative Domain Fallback**: When technical change impact cannot be precisely resolved to an endpoint, all tests within the affected domain are selected with `SHOULD_RUN` priority to prevent defect escapes.
5. **Risk Widening**: If `risk_signals` are present (e.g., dependency bumps, auth changes, migration files), all `@smoke` suite tests are activated with `SMOKE_ONLY` priority.
6. **Strict Validation Guardrail**: Verifies every selected test ID exists in `available_tests` — raises `ValueError` if a non-existent test is selected (anti-hallucination).
7. **Ranking**: `MUST_RUN` → `SHOULD_RUN` → `SMOKE_ONLY`, then alphabetical by title.

---

## 8. Adapters (`itaf/adapters/`)

Pluggable test management adapters implement a vendor-neutral interface for test discovery and execution evidence retrieval.

### `BaseTestManagementAdapter` — `base.py` (47 lines)

Abstract base class with four abstract methods:

| Method | Returns | Purpose |
|:---|:---|:---|
| `get_adapter_name()` | `str` | Adapter identifier |
| `is_live_connection()` | `bool` | `True` if connected to real API |
| `fetch_test_cases()` | `List[DiscoveredTestCase]` | Discovers test cases from the platform |
| `fetch_execution_evidence()` | `Dict[str, Dict]` | Retrieves execution results |
| `fetch_requirement_mappings()` | `List[RequirementTestMapping]` | Retrieves existing issue-to-test links |

### `RepoOnlyAdapter` — `repo_only.py` (40 lines)

- **Mode**: Local git repository (zero network dependency)
- Uses `TestDiscoveryEngine` directly to scan automation repo files.
- `is_live_connection()` returns `True` (local files are real evidence).
- Execution evidence defaults to `TEST_NOT_EXECUTED` (no CI export available).

### `XrayAdapter` — `xray.py` (83 lines)

- **Mode**: Jira Xray REST API or fixture fallback
- **Live**: Queries `{jira_base_url}/rest/raven/1.0/api/testruns` with Bearer JWT token. Logs connection warnings to `sys.stderr` if requests fail.
- **Fixture**: Loads mock execution evidence from JSON file, clearly labeled as `FIXTURE_MOCK (Simulated Xray Data)`.
- Auth via `JIRA_BASE_URL` and `JIRA_API_TOKEN` environment variables.

### `BrowserStackAdapter` — `browserstack.py` (82 lines)

- **Mode**: BrowserStack Test Management REST API v2 or fixture fallback
- **Live**: Queries `https://api-cloud.browserstack.com/test-management/v2/projects/{project_id}/test-runs` with Basic Auth. Logs connection warnings to `sys.stderr` if requests fail.
- **Fixture**: Loads mock data from JSON file, labeled as `FIXTURE_MOCK (Simulated BrowserStack Data)`.
- Auth via `BROWSERSTACK_USERNAME`, `BROWSERSTACK_ACCESS_KEY`, `BROWSERSTACK_PROJECT_ID` environment variables.

---

## 9. Reports (`itaf/reports/`)

### `generator.py` (133 lines)

**Function**: `generate_markdown_report(assessments, regression_decisions, change_summary, project_name, is_live_evidence) → str`

Generates audit-ready Markdown reports with 6 sections:

1. **Executive Quality Assurance Summary**: Total/covered/partial/missing requirements, failing gates count, coverage percentage.
2. **Mandatory Quality Gate Outcomes**: Table with Gate ID (exact ID extracted from findings), Requirement, Status (PASS/FAIL), Severity, and Finding detail.
3. **Requirement Traceability Matrix**: Table with Requirement ID, Domain/Service, Expected Outcome, Coverage Status, Mapped Test Count, Execution Evidence.
4. **Unmitigated Coverage Gaps & Actionable Remediation**: For each gap: target interface, severity, suggested test scenario title, and recommended verification steps.
5. **Requirement-Driven Regression Test Selection** (if decisions provided): Priority, Confidence, Test Name, In Regression Suite, Selection Rationale, Covered Requirements.
6. **Audit Provenance & Operational Notes**: Explains evaluation methodology (deterministic gates, assertion depth, execution data source).

---

## 10. Web UI (`itaf/ui/`)

### `server.py` (296 lines)

**Class**: `ITAFRequestHandler` (extends `http.server.BaseHTTPRequestHandler`)

Hardened, zero-dependency HTTP server using Python's `http.server` standard library module.

**Security Hardening**:
- **Path Traversal Protection**: Uses `os.path.commonpath` to ensure all `/static/*` requests remain strictly within the `itaf/ui/static` directory.
- **Filename Sanitization**: Sanitizes incoming diff filenames with `os.path.basename` on `/api/select-regression` to prevent directory traversal.
- **Payload Size Limits**: Enforces a strict 2MB request body limit on all POST endpoints to mitigate denial-of-service attempts.
- **Security Headers**: Injects `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY` on all responses.
- **Safe Binding**: Defaults to loopback address `127.0.0.1` rather than public interfaces.
- **Cache Integration**: Leverages `GLOBAL_ARTIFACT_CACHE` for fast in-memory response generation.

**Endpoints**:

| Method | Path | Handler | Description |
|:---|:---|:---|:---|
| GET | `/` or `/index.html` | `_serve_file` | Serves the SPA HTML |
| GET | `/static/*` | `_serve_file` | Serves CSS and JS static assets with path sanitization |
| GET | `/api/status` | Direct JSON | Returns `{"status": "ONLINE", "version": "2.0.0", "framework": "ITAF"}` |
| GET | `/api/assessments` | `_handle_get_assessments` | Runs full analysis pipeline, returns summary + assessment list |
| GET | `/api/report` | `_handle_get_report` | Returns Markdown report as JSON |
| POST | `/api/select-regression` | `_handle_select_regression` | Accepts `{"diff_file": "..."}`, runs regression selection |

**Orchestration Function**: `run_itaf_analysis(sample_feature_dir)` executes the end-to-end pipeline:
1. Parse requirements from OpenAPI, Feature, and Message specs in the feature directory.
2. Discover tests from the feature directory or fallback to the skill's fake automation repo.
3. Load execution evidence JSON if available.
4. Run PolicyEngine → CrossRepoMapper → CoverageIntelligenceEngine.
5. Return `{requirements, tests, assessments, evidence}`.

### Frontend — `static/index.html` (313 lines)

5-screen Single Page Application:

| Screen | Tab Name | Description |
|:---|:---|:---|
| **B** (default) | Coverage Assessment | Metrics cards, alert banner for failing gates, filterable requirements table |
| **C** | Requirement Detail | Inspector with provenance, gate outcomes, mapped tests with assertion detail, remediation suggestions |
| **D** | Regression Selection | Diff selector dropdown, run button, warning banner, decision matrix table |
| **A** | Configuration | Discovered artifacts list, active gate rule packs |
| **E** | Audit Report | Markdown report viewer with copy/download buttons |

### Frontend — `static/app.js` (240 lines)

Vanilla JavaScript client with functions:

| Function | Purpose |
|:---|:---|
| `runAnalysis()` | Fetches `/api/assessments`, renders metrics and table |
| `renderSummaryMetrics(summary)` | Updates stat cards and gate alert banner |
| `renderRequirementsTable(items)` | Builds HTML table rows with status badges |
| `applyFilters()` | Filters by coverage status, domain, and search text |
| `inspectRequirement(reqId)` | Populates detail view with gates, tests, remediation |
| `executeRegressionSelection()` | POSTs to `/api/select-regression`, renders decision table |
| `loadReport()` | Fetches Markdown report for screen E |
| `copyReport()` | Copies report to clipboard |
| `downloadReport()` | Downloads report as `.md` file |

### Frontend — `static/styles.css` (398 lines)

Enterprise-grade CSS using:
- CSS Custom Properties (design tokens for colors)
- `Inter` font family (body) + `JetBrains Mono` (code)
- Responsive grid layouts (`stats-grid`, `detail-grid`, `config-grid`)
- Status badges (`.badge-success`, `.badge-warning`, `.badge-danger`, `.badge-neutral`)
- Alert banners with icon + content layout
- Data table with hover states and toolbar filters
- Gate outcome items with pass/fail left-border indicators
- Dark header with tab navigation

---

## 11. CLI (`itaf/cli.py` & `itaf_cli.py`)

### Root Entrypoint — `itaf_cli.py` (8 lines)

Simply imports and calls `main()` from `itaf.cli`.

### CLI Module — `itaf/cli.py` (222 lines)

**Usage**: `python itaf_cli.py <command> [options]`

| Command | Description | Key Arguments |
|:---|:---|:---|
| `assess` | Assess requirement and quality gate coverage | `--feature-dir PATH`, `--json` |
| `select` | Select regression tests based on change and requirements | `--diff-file PATH` (required), `--feature-dir PATH`, `--json` |
| `gates` | Validate and list quality gate rules | `--gates-dir PATH` |
| `report` | Generate audit-ready test assurance report | `--output PATH` |
| `serve` | Launch interactive web dashboard | `--port PORT` (default: 8080) |

**`cmd_assess`**: Runs `run_itaf_analysis()`, computes summary statistics (total/covered/partial/missing/failing gates), outputs formatted terminal table or JSON.

**`cmd_select`**: Reads diff file, extracts fingerprints, runs analysis, creates `RegressionSelector`, calls `select_tests_for_change()`, outputs decisions with priority, confidence, and reasons.

**`cmd_gates`**: Creates `PolicyEngine`, prints all loaded rules with severity and category.

**`cmd_report`**: Runs analysis, generates Markdown report, prints to stdout or writes to file.

**`cmd_serve`**: Starts the HTTP server on specified port.

**Windows UTF-8 Fix**: Reconfigures `sys.stdout` and `sys.stderr` to UTF-8 encoding on Windows to prevent emoji/Unicode encoding errors.

---

## 12. Quality Gate Policy Rules (`gates/`)

Machine-readable YAML policy rule packs organized by category. Each rule is validated against `policy-rule.schema.json` at load time.

### `common/security.yaml` — 2 rules

| Rule ID | Name | Severity | Standard |
|:---|:---|:---|:---|
| `GATE-SEC-001` | Mandatory Authentication Token Validation | BLOCKER | PCI-DSS 4.0 Req 8.2 & OAuth2 Security BCP |
| `GATE-SEC-002` | Role-Based Access Control and Authorization Enforcement | CRITICAL | OWASP API Security Top 10 - API1:2023 |

### `common/api.yaml` — 2 rules

| Rule ID | Name | Severity | Standard |
|:---|:---|:---|:---|
| `GATE-API-001` | API Contract and Status Code Conformity | CRITICAL | OpenAPI Specification 3.0 & Bank API Guidelines |
| `GATE-API-002` | Standardized Error Response Structure | MAJOR | RFC 7807 Problem Details |

### `domains/payments.yaml` — 3 rules

| Rule ID | Name | Severity | Standard |
|:---|:---|:---|:---|
| `GATE-PAY-001` | Request Idempotency Control | BLOCKER | PSP Platform Standards - Section 5.1 |
| `GATE-PAY-002` | Business Duplicate Detection | BLOCKER | SWIFT / ISO 20022 Duplicate Payment Prevention |
| `GATE-PAY-003` | Payment Amount and Currency Integrity | BLOCKER | ISO 4217 Currency Standards |

### `resilience/retry.yaml` — 2 rules

| Rule ID | Name | Severity | Standard |
|:---|:---|:---|:---|
| `GATE-RET-001` | Transient Downstream Failure Retry with Backoff | BLOCKER | Bank Resilience Architecture Standard 4.1 |
| `GATE-RET-002` | Idempotent Safe-Retry Boundary | CRITICAL | PSP Engineering Gate 2.4 |

### `resilience/circuit-breaker.yaml` — 1 rule

| Rule ID | Name | Severity | Standard |
|:---|:---|:---|:---|
| `GATE-CB-001` | Downstream Circuit Breaker Failure Isolation | MAJOR | Bank Resilience Architecture Standard 4.3 |

**Total**: 10 quality gate rules across 5 YAML files.

---

## 13. JSON Schemas (`schemas/`)

Five JSON Schema (draft-07) definitions validating all serializable data structures:

| Schema File | Title | Required Fields |
|:---|:---|:---|
| `policy-rule.schema.json` | PolicyRule | `rule_id`, `name`, `category`, `severity`, `mandatory`, `applies_to`, `required_outcomes`, `failure_criteria` |
| `requirement.schema.json` | Requirement | `requirement_id`, `title`, `description`, `req_type`, `origin`, `domain`, `service`, `interface` |
| `test-case.schema.json` | DiscoveredTestCase | `test_id`, `title`, `file_path`, `line_number`, `framework` |
| `coverage-result.schema.json` | RequirementCoverageAssessment | `requirement_id`, `title`, `domain`, `service`, `coverage_status` |
| `regression-decision.schema.json` | RegressionSelectionDecision | `test_id`, `title`, `file_path`, `framework`, `priority`, `confidence` |

---

## 14. Examples & Fixtures (`examples/`)

### `examples/sample_feature/` — ITAF Sample Feature Directory

| File | Size | Description |
|:---|:---|:---|
| `payment-api.v1.yaml` | 2.2 KB | OpenAPI 3.0 spec for `POST /api/v1/payments/process` with Idempotency-Key, security, responses |
| `payment-submission-feature.md` | 2.6 KB | Feature spec for PAY-900 with 5 business requirements (auth, idempotency, dedup, retry, amounts) |
| `ADR-004-idempotency-and-resilience.md` | 1.6 KB | Architecture Decision Record for idempotency and resilience patterns |
| `swift-pacs008-payment.json` | 363 B | ISO 20022 pacs.008 message spec with mandatory fields |
| `execution-evidence.json` | 1.3 KB | Mock test execution results |
| `pr-payment-retry-change.diff` | 1.1 KB | Sample diff for downstream retry logic change |
| `tests/payments/payment-submission.spec.ts` | 3.6 KB | Playwright test suite with 5 tests covering auth, idempotency, dedup, negative amounts |

### `.github/skills/regression-test-selector/examples/fixtures/` — RTS Backtesting Fixtures

- **`dev-diffs/`**: 5 sample PR diffs (PR-101, PR-102, PR-103, PR-104, PR-105)
- **`fake-automation-repo/`**: Mock Playwright and Selenium test repos with realistic test files
- **`known-defects.csv`**: Historical defects for recall validation
- **`playwright-index.json`** / **`selenium-index.json`**: Pre-built test indexes

---

## 15. GitHub Copilot Skill (`.github/skills/`)

The `regression-test-selector` skill is a reusable GitHub Copilot Agent Skill consisting of:

### Scripts (`scripts/`)

| Script | Purpose |
|:---|:---|
| `extract_change_fingerprints.py` | Extracts endpoints, routes, UI selectors, error codes, DTO fields, risk signals from git diffs |
| `build_test_index.py` | Builds JSON index of all tests with assertion depth from an automation repo |
| `fetch_automation_repo.py` | Clones/pulls automation repo (GitHub Cloud, Enterprise, or local path) |
| `matcher.py` | Matches fingerprints against test index using evidence tiers, produces selection report |
| `backtest.py` | Runs historical backtest across diffs and known defects to measure recall/precision |
| `init_config.py` | Initializes `rts.config.yml` configuration file |

### Tests (`tests/`)

The framework is verified by a **45-test automated test suite** executed with standard library `unittest` via `python tests/run_all_tests.py`:

- **21 RTS Skill Tests** (`.github/skills/regression-test-selector/tests/`):
  - Change fingerprint extraction accuracy (`test_fingerprints.py`)
  - Playwright and Selenium test indexing and Page Object resolution (`test_index_builder.py`)
  - Evidence tier ranking and strict validation guardrails (`test_ranking.py`)
  - Backtesting recall and precision calculations (`test_backtest.py`)
  - Remote and local repo fetching and host detection (`test_fetch_repo.py`)
- **24 ITAF Core Tests** (`tests/test_itaf_core.py`, 1030 lines):
  - **Specification Parsing**: OpenAPI parameter/security extraction, Feature Markdown parsing with ambiguity notes, ISO 20022 message parsing.
  - **Policy Engine**: Rule applicability isolation and structured assertion checks across all 10 gates; anti-false-positive checks against keyword-only matches.
  - **Cross-Repo Mapper**: Case-insensitive interface normalization, regex Jira key extraction, discrete outcome mapping, strict negative outcome matching (e.g. 401 != 403).
  - **Coverage Intelligence**: Multi-index execution lookup `(file_path, title)`, empty outcomes guardrail (`AMBIGUOUS` never `COVERED`), zero-gate transparency notes.
  - **False Assurance Prevention Guardrails** (`TestFalseAssuranceGuards`):
    - An idempotency header assertion alone does NOT prove safe replay (`test_idempotency_header_alone_does_not_prove_safe_replay`).
    - An HTTP 409 assertion alone does NOT prove business duplicate detection (`test_http_409_alone_does_not_prove_duplicate_detection`).
    - An HTTP 503 assertion alone does NOT prove successful retry behavior (`test_http_503_alone_does_not_prove_successful_retry`).
    - A test containing an unrelated assertion cannot satisfy a mandatory outcome (`test_unrelated_assertion_cannot_satisfy_mandatory_outcome`).
    - A Jira-key or endpoint match without relevant outcome evidence does not establish confirmed coverage (`test_jira_and_endpoint_match_without_outcome_evidence_not_confirmed`).
    - Coverage status and execution status are evaluated and reported independently (`test_coverage_status_and_execution_status_are_independent`).
  - **Regression Selection Validation** (`TestRegressionSelectionValidation`):
    - Shared DTO field modifications trigger affected requirements (`test_shared_dto_change_triggers_affected_requirements`).
    - Indirect dependency and build configuration changes (`pom.xml`, migrations) trigger risk widening and smoke tests (`test_indirect_dependency_and_configuration_changes`).
    - Unmapped endpoints or unknown files trigger conservative domain fallback with audit warnings (`test_unknown_files_and_missing_specifications_widen_conservatively`).
    - Stale test index resilience safely excludes deleted tests and flags unmitigated coverage gaps (`test_stale_test_index_resilience`).
    - ITAF engine and standalone RTS skill produce compatible decisions for equivalent change inputs (`test_itaf_and_rts_skill_compatibility`).
  - **Incremental Cache**: SHA-256 artifact hashing and lifecycle invalidation.
  - **Web Server Security**: Static path traversal protection via `os.path.commonpath`, diff input sanitization via `os.path.basename`.

---

## 16. Configuration Reference

### `rts.config.yml` — RTS Configuration

```yaml
automation_repo: https://github.com/my-org/payments-automation-tests  # or local path
framework: auto                # auto | playwright-ts | selenium-java
branch: main
test_source: repo-only         # repo-only (default) | xray | browserstack
regression_suite:
  tag: "@regression"
smoke_suite:
  tag: "@smoke"
service_map: ./service-map.yml
risk_paths:
  - "**/migrations/**"
  - "**/auth/**"
  - "pom.xml"
  - "package.json"
run_command_template: 'npx playwright test --grep "{grep}"'
```

### Environment Variables

| Variable | Adapter | Purpose |
|:---|:---|:---|
| `JIRA_BASE_URL` | Xray | Jira instance URL |
| `JIRA_API_TOKEN` | Xray | API authentication token |
| `BROWSERSTACK_USERNAME` | BrowserStack | Account username |
| `BROWSERSTACK_ACCESS_KEY` | BrowserStack | API access key |
| `BROWSERSTACK_PROJECT_ID` | BrowserStack | Project identifier |

---

## 17. Data Flow & Pipeline

```
                    ┌──────────────────┐
                    │   Input Phase    │
                    └──────┬───────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   OpenAPI Spec      Feature Spec      Message Spec
        │                  │                  │
        ▼                  ▼                  ▼
   OpenAPIParser     FeatureParser    MessageFormatParser
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                     List[Requirement]
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   PolicyEngine    TestDiscoveryEngine   CrossRepoMapper
   (loads gates)   (scans auto repo)    (maps req→test)
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                           ▼
                CoverageIntelligenceEngine
                           │
              List[RequirementCoverageAssessment]
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   CLI Output         Web UI API        Markdown Report
   (terminal)         (JSON REST)       (audit-ready)
                           │
                           ▼ (if diff provided)
                   RegressionSelector
                           │
              List[RegressionSelectionDecision]
              + unmitigated_gaps
              + warning_notes
```

---

## 18. Evidence Tier Ranking System

Used by the RTS skill's `matcher.py` and by the ITAF engine's `CrossRepoMapper`:

| Tier | Name | Example | Priority |
|:---|:---|:---|:---|
| **Tier 1** | Direct Reference | Endpoint `POST /api/v1/payments/process`, Route `/checkout/payment`, UI selector `Pay Now`, Error code `ERR_CARD_EXPIRED`, DTO field | `MUST_RUN` (High Confidence) |
| **Tier 2** | Jira Key Match | Test title/tags/comments contain PR's Jira issue key | `MUST_RUN` (High Confidence if joint; Medium if alone) |
| **Tier 3** | Flow Match | Behavioral reasoning matches CR summary to test flows | `SHOULD_RUN` (Medium Confidence) |
| **Tier 4** | Page Object Path | Inherited through 1-level Page Object indirection (e.g., `PaymentPage` → `testPayment`) | `SHOULD_RUN` (Medium Confidence) |
| **Tier 5** | Semantic Domain Match | Broad domain keywords (`payment`, `checkout`, `refund`). Advisory fallback; outcome assertions unverified. | `SHOULD_RUN` (Low Confidence) |

---

## 19. Guardrails & Safety

| Guardrail | Implementation |
|:---|:---|
| **Read-Only** | The framework never modifies code in developer or automation repos |
| **Zero Test Hallucination** | `RegressionSelector` validates every selected test ID against `available_tests`; raises `ValueError` on non-existent test |
| **Recall Over Precision** | Design prioritizes catching all relevant tests over minimizing false positives |
| **Schema Validation** | All policy rules validated against JSON Schema at load time |
| **Provenance Tracking** | Every `Requirement`, `ExpectedOutcome`, and `AssertionEvidence` tracks source artifact, section, and line number |
| **Ambiguity Detection** | `FeatureParser` flags requirements with unspecified parameters (e.g., missing retry limits) |
| **Evidence Labeling** | Adapters clearly distinguish between `LIVE_*_API` and `FIXTURE_MOCK (Simulated ... Data)` sources |
| **Assertion Depth** | Tests are classified as deep-asserting vs. endpoint-visiting based on assertion type analysis |

---

## 20. Benchmark Results

The RTS selection pipeline was validated across 5 synthetic pull request fixture scenarios (`dev-diffs/pr-101.diff` to `pr-105.diff`) against the mock payments automation test suite (`fake-automation-repo/`, 25 total candidate test evaluations across 5 PR diffs):

| Metric | Without RTS (Full Regression Baseline) | With RTS Targeted Selection | Improvement / Impact |
|:---|:---:|:---:|:---|
| **Average Tests Run per PR** | 5.0 tests (all) | 2.4 tests | **52.0% execution reduction** |
| **Suite Execution Time** | ~19.0 min | ~9.2 min | **~52% CI time saved** |
| **True Positives (TP)** | — | **4** | Correctly selected tests catching known defects |
| **False Positives (FP)** | — | **8** | Proactively selected via risk-widening/smoke or domain coverage |
| **False Negatives (FN)** | — | **0** | Zero defect escapes |
| **True Negatives (TN)** | — | **13** | Safely omitted irrelevant tests |
| **Defect Recall Rate** | 100.0% | **100.0%** (4/4 caught) | **Zero defect escapes** |
| **Selection Precision** | 20.0% (4/20) | **33.3%** (4/12 selected) | **66.5% precision improvement** |
| **Coverage Gaps Flagged** | 0 (blind) | **3 Gaps Flagged** | **Proactive test scenario generation** |

> [!NOTE]
> **Dataset Disclosure**: These benchmark results reflect backtesting simulations executed via `scripts/backtest.py` across synthetic PR diffs and known defects fixture dataset (`known-defects.csv`, `dev-diffs/pr-*.diff`, `fake-automation-repo/`). Zero-denominator safety is enforced in all statistical calculations. These results characterize backtesting algorithm performance on synthetic fixtures rather than multi-tenant production CI execution telemetry.

---

## 21. API Endpoints (Web Server)

| Method | Path | Request Body | Response |
|:---|:---|:---|:---|
| `GET` | `/api/status` | — | `{"status":"ONLINE","version":"2.0.0","framework":"ITAF"}` |
| `GET` | `/api/assessments` | — | `{"summary":{...},"assessments":[{requirement_id, title, coverage_status, failing_gate_ids, mapped_tests, ...}]}` |
| `GET` | `/api/report` | — | `{"markdown":"# Intelligent Test Assurance Report..."}` |
| `POST` | `/api/select-regression` | `{"diff_file":"pr-payment-retry-change.diff"}` | `{"diff_file":"...","decisions":[{test_id, priority, confidence, selection_reasons, ...}],"unmitigated_gaps":[...],"warning_notes":[...]}` |

---

## 22. Class & Module Reference

| Module Path | Class/Function | Lines | Purpose |
|:---|:---|:---:|:---|
| `itaf/core/models.py` | 6 Enums + 9 Dataclasses | 211 | Canonical data models |
| `itaf/core/cache.py` | `ArtifactCache`, `GLOBAL_ARTIFACT_CACHE` | 71 | SHA-256 artifact caching |
| `itaf/core/schemas.py` | `load_schema()`, `validate_dict()` | 79 | Schema loading & validation |
| `itaf/parsers/openapi_parser.py` | `OpenAPIParser` | 339 | OpenAPI 3.0/Swagger parser |
| `itaf/parsers/feature_parser.py` | `FeatureParser` | 230 | Feature/story document parser |
| `itaf/parsers/message_parser.py` | `MessageFormatParser` | 90 | ISO 20022 message parser |
| `itaf/engine/policy_engine.py` | `PolicyEngine` | 376 | Quality gate loader & evaluator |
| `itaf/engine/test_discovery.py` | `TestDiscoveryEngine`, `inspect_assertions_in_body()` | 240 | Test discovery & lexical assertion inspection |
| `itaf/engine/cross_repo_mapper.py` | `CrossRepoMapper` | 180 | Requirement→test mapping |
| `itaf/engine/coverage_intelligence.py` | `CoverageIntelligenceEngine` | 201 | Coverage assessment engine |
| `itaf/engine/regression_selector.py` | `RegressionSelector` | 189 | Change-driven test selection |
| `itaf/adapters/base.py` | `BaseTestManagementAdapter` | 47 | Abstract adapter interface |
| `itaf/adapters/repo_only.py` | `RepoOnlyAdapter` | 40 | Local git repository adapter |
| `itaf/adapters/xray.py` | `XrayAdapter` | 83 | Jira Xray REST adapter |
| `itaf/adapters/browserstack.py` | `BrowserStackAdapter` | 82 | BrowserStack REST adapter |
| `itaf/reports/generator.py` | `generate_markdown_report()` | 133 | Markdown audit report generator |
| `itaf/ui/server.py` | `ITAFRequestHandler`, `run_itaf_analysis()`, `start_server()` | 296 | Hardened web server & orchestrator |
| `itaf/cli.py` | `cmd_assess`, `cmd_select`, `cmd_gates`, `cmd_report`, `cmd_serve`, `main()` | 225 | Unified CLI interface |
| `tests/run_all_tests.py` | Unified test runner | 32 | Runs all 45 core & skill tests |
| `tests/test_itaf_core.py` | `TestParsers`, `TestPolicyEngine`, `TestCrossRepoMapper`, `TestCoverageIntelligenceEdgeCases`, `TestFalseAssuranceGuards`, `TestRegressionSelectionValidation`, `TestRegressionSelector`, `TestIncrementalCache`, `TestWebServerSecurity` | 1030 | Core ITAF unit & integration tests (24 tests) |

---

## 23. Enum Reference

### `RequirementType` — 11 values
`FUNCTIONAL` · `POSITIVE` · `NEGATIVE` · `SECURITY` · `IDEMPOTENCY` · `DUPLICATE_DETECTION` · `RESILIENCE_RETRY` · `CIRCUIT_BREAKER` · `API_CONTRACT` · `DATA_INTEGRITY` · `OBSERVABILITY`

### `RequirementOrigin` — 3 values
`EXPLICIT_SPEC` (from OpenAPI/Feature/MVD) · `POLICY_GATE` (mandated by org gate) · `INFERRED` (deduced from context)

### `RuleSeverity` — 4 values
`BLOCKER` (deployment blocked) · `CRITICAL` (requires approval) · `MAJOR` (address in sprint) · `MINOR` (best practice)

### `MappingConfidence` — 6 values
`CONFIRMED` · `HIGH` · `MEDIUM` · `LOW` · `AMBIGUOUS` · `MISSING`

### `CoverageStatus` — 6 values
`COVERED` · `PARTIALLY_COVERED` · `MISSING_COVERAGE` · `BLOCKED` · `AMBIGUOUS` · `NOT_APPLICABLE`

### `ExecutionStatus` — 4 values
`EXECUTION_PASSED` · `EXECUTION_FAILED` · `TEST_NOT_EXECUTED` · `EVIDENCE_MISSING`

---

## 24. File Inventory

### Python Source Files (`.py`)

| # | File | Lines | Description |
|:---|:---|:---:|:---|
| 1 | `itaf_cli.py` | 8 | Root CLI entrypoint |
| 2 | `itaf/cli.py` | 225 | Unified CLI with 5 subcommands |
| 3 | `itaf/core/__init__.py` | 48 | Core package exports |
| 4 | `itaf/core/cache.py` | 71 | Artifact SHA-256 caching |
| 5 | `itaf/core/models.py` | 211 | Data models (6 enums + 9 dataclasses) |
| 6 | `itaf/core/schemas.py` | 79 | JSON Schema validation |
| 7 | `itaf/parsers/__init__.py` | 9 | Parsers package exports |
| 8 | `itaf/parsers/openapi_parser.py` | 339 | OpenAPI 3.0/Swagger parser |
| 9 | `itaf/parsers/feature_parser.py` | 230 | Feature/story parser |
| 10 | `itaf/parsers/message_parser.py` | 90 | ISO 20022 message parser |
| 11 | `itaf/engine/__init__.py` | 17 | Engine package exports |
| 12 | `itaf/engine/policy_engine.py` | 376 | Quality gate evaluation |
| 13 | `itaf/engine/test_discovery.py` | 240 | Test discovery + assertion inspection |
| 14 | `itaf/engine/cross_repo_mapper.py` | 180 | Cross-repo requirement→test mapping |
| 15 | `itaf/engine/coverage_intelligence.py` | 201 | Coverage assessment engine |
| 16 | `itaf/engine/regression_selector.py` | 189 | Smart regression selector |
| 17 | `itaf/adapters/__init__.py` | 15 | Adapters package exports |
| 18 | `itaf/adapters/base.py` | 47 | Abstract adapter interface |
| 19 | `itaf/adapters/repo_only.py` | 40 | Local repository adapter |
| 20 | `itaf/adapters/xray.py` | 83 | Jira Xray adapter |
| 21 | `itaf/adapters/browserstack.py` | 82 | BrowserStack adapter |
| 22 | `itaf/reports/__init__.py` | 0 | Reports package init |
| 23 | `itaf/reports/generator.py` | 133 | Markdown report generator |
| 24 | `itaf/ui/__init__.py` | 0 | UI package init |
| 25 | `itaf/ui/server.py` | 296 | Web server + orchestration |
| 26 | `tests/run_all_tests.py` | 32 | Unified test runner |
| 27 | `tests/test_itaf_core.py` | 1030 | Core ITAF unit & integration tests |
| 28 | `.github/skills/regression-test-selector/scripts/backtest.py` | 301 | RTS backtesting script |
| 29 | `.github/skills/regression-test-selector/scripts/build_test_index.py` | 572 | RTS test indexing script |
| 30 | `.github/skills/regression-test-selector/scripts/extract_change_fingerprints.py` | 421 | RTS diff fingerprinting script |
| 31 | `.github/skills/regression-test-selector/scripts/fetch_automation_repo.py` | 179 | RTS repo fetch script |
| 32 | `.github/skills/regression-test-selector/scripts/init_config.py` | 178 | RTS config init script |
| 33 | `.github/skills/regression-test-selector/scripts/matcher.py` | 468 | RTS test matching script |
| 34 | `.github/skills/regression-test-selector/tests/run_all_tests.py` | 19 | RTS skill test runner |
| 35 | `.github/skills/regression-test-selector/tests/test_backtest.py` | 48 | RTS backtest unit tests |
| 36 | `.github/skills/regression-test-selector/tests/test_fetch_repo.py` | 46 | RTS fetch repo unit tests |
| 37 | `.github/skills/regression-test-selector/tests/test_fingerprints.py` | 69 | RTS fingerprinting unit tests |
| 38 | `.github/skills/regression-test-selector/tests/test_index_builder.py` | 68 | RTS index builder unit tests |
| 39 | `.github/skills/regression-test-selector/tests/test_ranking.py` | 134 | RTS ranking unit tests |

### Frontend Files

| File | Lines | Description |
|:---|:---:|:---|
| `itaf/ui/static/index.html` | 313 | 5-screen SPA layout |
| `itaf/ui/static/app.js` | 240 | Vanilla JS client |
| `itaf/ui/static/styles.css` | 398 | Enterprise CSS design system |

### Configuration & Schema Files

| File | Lines | Description |
|:---|:---:|:---|
| `schemas/policy-rule.schema.json` | 28 | Policy rule JSON Schema |
| `schemas/requirement.schema.json` | 47 | Requirement JSON Schema |
| `schemas/test-case.schema.json` | 43 | Test case JSON Schema |
| `schemas/coverage-result.schema.json` | 39 | Coverage result JSON Schema |
| `schemas/regression-decision.schema.json` | 20 | Regression decision JSON Schema |
| `gates/common/security.yaml` | 34 | Security gates (2 rules) |
| `gates/common/api.yaml` | 33 | API contract gates (2 rules) |
| `gates/domains/payments.yaml` | 54 | Payment domain gates (3 rules) |
| `gates/resilience/retry.yaml` | 35 | Retry resilience gates (2 rules) |
| `gates/resilience/circuit-breaker.yaml` | 19 | Circuit breaker gate (1 rule) |
| `.gitignore` | 10 | Git ignore rules |

---

## 25. Future Roadmap

- [ ] **Automated PR Comment Bot**: Run RTS as a GitHub Action workflow to post selection reports directly into PR conversations.
- [ ] **Closed-Loop Learning Feedback**: Capture post-merge defect escapes and automatically train fingerprint weights to improve future recall.
- [ ] **Full Jira Xray & BrowserStack REST Adapters**: Directly sync live execution flakiness scores and manual test cases.
- [ ] **GitHub Model Context Protocol (MCP) Server**: Expose RTS tools directly to any MCP-compliant AI assistant or agent.

---

## 26. Changelog

| Date | Change |
|:---|:---|
| 2026-10-20 | **Focused Correctness Review & Final Validation Complete (45/45 Tests Passing)**:<br>• **False Assurance Prevention**: Added rigorous guardrails preventing `HEADER` assertions alone from satisfying idempotency safe replay, generic `409` from satisfying business duplicate detection, and `503` alone from satisfying retry behavior. Enforced independent reporting for coverage status vs. execution status.<br>• **Model & Documentation Reconciliation**: Reconciled model counts to 6 enums and 9 dataclasses in `itaf/core/models.py`; clarified lexical regex pattern inspection over test source code (avoiding compiler AST dependencies); explicitly designated benchmark results as synthetic fixture backtesting.<br>• **Regression Selection Hardening**: Added shared DTO matching to `RegressionSelector`; validated risk widening across build configuration changes (`pom.xml`, migrations); added conservative domain fallback and stale test index tolerance.<br>• **Validation**: Expanded test suite to 45 automated tests (21 RTS skill tests + 24 ITAF core tests in `tests/test_itaf_core.py`), all passing standard-library-only execution in ~2s. |
| 2026-10-20 | Implementation Audit & Remediation: Decoupled rule applicability from gate compliance; fixed case-insensitive interface matching and Jira key extraction in `cross_repo_mapper.py`; removed fragile line numbers in execution evidence indexing; resolved static file directory traversal and sanitized diff file inputs in `server.py`; implemented conservative regression fallback and unmitigated gap reporting for ambiguous/missing specifications; added comprehensive core tests and unified runner. |
| 2026-10-20 | Initial `IMPLEMENTATION_DETAILS.md` created with full project documentation covering architecture, all modules, data models, engines, parsers, adapters, UI, CLI, gates, schemas, examples, benchmarks, APIs, and file inventory. |

---

> **Note**: This file should be kept up-to-date whenever significant changes are made to the project. Update the relevant sections and add an entry to the Changelog.
