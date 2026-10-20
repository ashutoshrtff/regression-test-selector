# Matching and Ranking Reference Guide

This document defines the mathematical hierarchy, evidence tiers, confidence scoring model, and risk widening heuristics utilized by the `regression-test-selector` Copilot Agent Skill.

---

## 1. Core Philosophy: Recall Over Precision

In Enterprise Payments Platforms (PSP), the cost of escaping defects is orders of magnitude higher than the compute cost of running an extra test. Therefore, the selector strictly prioritizes **Recall over Precision**:
- **Goal**: Minimize regression cycle duration while maintaining near-100% defect capture recall.
- **Rule**: Never guess or hallucinate test names. A test can only be selected if it exists in the verified automation test catalog.
- **Rule**: Never use file path or filename similarity alone to justify test selection.

---

## 2. Evidence Tiers (Ordered by Weight)

| Tier | Category | Description | Primary Match Condition | Default Confidence |
| :---: | :--- | :--- | :--- | :---: |
| **Tier 1** | **Direct Technical Reference** | The test directly invokes or asserts against changed code artifacts. | Exact match on HTTP endpoint (`POST /api/...`), frontend route (`/checkout/...`), UI selector (`data-testid`), error code (`ERR_...`), or DTO field name. | **High** |
| **Tier 2** | **Jira Key Match** | Jira issue key linked in the change request is explicitly tied to the test. | Jira ticket key (`PAY-123`) appears in test title, test annotations, test comments, or automation repo commit history for that spec. | **Medium / High** (High if paired with Tier 3) |
| **Tier 3** | **Business Flow Match** | Agent judgment correlates the Plain-English behavior change with test intent. | Test scenario description directly exercises the business behavior, edge case, or conditional branch modified in the CR. | **Medium** |
| **Tier 4** | **Shared Page Object / Helper** | Test exercises changed behavior through an encapsulation layer. | Test instantiates or calls a Page Object (`PaymentPage`) or helper that contains the changed route, endpoint, or selector (1-level indirection). | **Medium** |
| **Tier 5** | **Semantic Domain Overlap** | Weakest match; based on module/keyword proximity. | Overlap on high-level domain terminology (e.g. `reporting`, `settlement`, `auth`) where technical evidence is sparse. | **Low** (Categorized under "Should Run" only) |

---

## 3. Confidence Determination Matrix

The confidence assigned to a selected test is computed systematically:

```
[Tier 1 Present?] ──Yes──> High Confidence (Must Run)
       │
      No
       │
[Tier 2 + Tier 3 or Tier 4?] ──Yes──> High Confidence (Must Run)
       │
      No
       │
[Single Tier 2 or Tier 4?] ──Yes──> Medium Confidence (Must Run if Tier 2, Should Run if Tier 4)
       │
      No
       │
[Tier 5 Semantic Match?] ──Yes──> Low Confidence (Should Run)
```

---

## 4. Value-Add: Unlinked Tests Outside Regression Suites

Automation repositories often accumulate hundreds of specific edge-case and regression tests that are:
1. Not included in the daily `@regression` smoke tag to keep runs under 30 minutes.
2. Missing formal Jira links due to ticketing tool migrations (e.g., Jira Xray to BrowserStack).

The selector indexes the **entire automation repository**. When a code change modifies a specific DTO field, error code, or secondary route, the selector discovers and flags relevant tests that are **Outside the standard regression suite**. This catches subtle regressions that standard scheduled suites miss.

---

## 5. Risk Widening Rules

When changes touch systemic infrastructure, selective testing can be dangerous. The selector evaluates the diff against the following **Risk Triggers**:

1. **Authentication & Session Management** (`auth_security`):
   - Changes to JWT validation, OAuth tokens, filter chains, security contexts, CORS policies, or permission annotations.
2. **Database Migrations** (`database_migrations`):
   - Changes in Flyway, Liquibase, Alembic, Prisma, or raw `.sql` migration files.
3. **Core Dependency Manifests** (`dependencies`):
   - Version bumps in `pom.xml`, `package.json`, `build.gradle`, `requirements.txt`.
4. **Feature Flag Defaults** (`feature_flag_defaults`):
   - Default boolean toggle inverted (`false` -> `true`).
5. **Shared Libraries & Base Classes** (`shared_core`):
   - Common utilities, base HTTP clients, or base entity classes touched.
6. **Payment-Critical Settlement Flows**:
   - Ledger reconciliation, transaction reversal, or currency conversion algorithms.

### Actions on Risk Trigger:
- **Single Trigger**: Automatically activate the **Smoke Test Suite** (`@smoke`) in addition to targeted tests.
- **Multiple Triggers (>= 3)** or **Database Migration + Auth change**: Recommend an unconditional **Full Suite Run** to ensure platform stability.
