---
name: regression-test-selector
description: Selects targeted regression tests for a Pull Request or Change Request based on behavioral impact analysis, change fingerprinting, and automation repository index. Triggers on "which tests should I run for this PR/CR", "select regression tests", "test impact analysis", "what could this change break".
---

# Regression Test Selector (RTS) Skill

Select targeted automated regression tests for a PR/CR to maximize defect recall while drastically shortening CI test feedback loops.

## Guardrails
- **Read-Only**: Never modify the developer repo or automation repo.
- **No Hallucinated Tests**: ONLY recommend tests that exist in the indexed automation test catalog.
- **Recall Over Precision**: A missed defect is worse than running an extra test. If in doubt, select it.
- **Human Guidance**: If evidence is thin or conditional, state what a human engineer must verify.

---

## Procedural Workflow

When the user asks to select tests for a PR or change:

### Step 1: Load Configuration
Look for `rts.config.yml` in the dev repo root.
- If missing, run:
  ```bash
  python .github/skills/regression-test-selector/scripts/init_config.py
  ```
- Or ask the user for:
  1. Automation repository URL or local path
  2. Test framework (`playwright-ts` or `selenium-java`)

### Step 2: Fetch Change Diff & Context
Obtain the unified diff and metadata:
- For a GitHub PR:
  ```bash
  gh pr view <PR_NUMBER_OR_URL> --json number,title,headRefName,body
  gh pr diff <PR_NUMBER_OR_URL> > /tmp/pr_change.diff
  ```
- For a local branch or commit range:
  ```bash
  git diff origin/main...HEAD > /tmp/pr_change.diff
  ```
Extract Jira issue key (e.g., `PAY-101`) from branch name, commit logs, or PR title.

### Step 3: Extract Fingerprints & Analyze Behavioral Impact
Run the fingerprint extractor:
```bash
python .github/skills/regression-test-selector/scripts/extract_change_fingerprints.py --diff-file /tmp/pr_change.diff --output /tmp/fingerprints.json
```
**Agent Judgment Step**:
Scripts extract facts; **you provide engineering judgment**.
Read the key diff hunks from `/tmp/pr_change.diff`. Write a concise summary (max 10 lines) covering:
- What user journeys or API contracts changed.
- New conditional branches, altered validations, and edge condition handling.

### Step 4: Trace Systemic Impact Beyond Diff
When contracts or shared models change, trace outward:
- Identify callers of modified public methods or changed endpoints.
- Check database schema changes and configuration properties.
- State clearly in the report what impact was traced.

### Step 5: Fetch & Index Automation Repo
Sync the automation repository and build/read the incremental test catalog:
```bash
python .github/skills/regression-test-selector/scripts/fetch_automation_repo.py --repo "<automation_repo_from_config>"
python .github/skills/regression-test-selector/scripts/build_test_index.py --repo-dir "<path_from_fetch>" --output /tmp/test_index.json
```
*Note: Page Object indirection is resolved automatically by the indexer.*

### Step 6: Match, Rank, and Detect Gaps
Run the matcher engine or evaluate against the evidence tiers:
```bash
python .github/skills/regression-test-selector/scripts/matcher.py \
  --fingerprints /tmp/fingerprints.json \
  --index /tmp/test_index.json \
  --cr-summary "<your_behavioral_summary>" \
  --output /tmp/rts_report.md
```

#### Evidence Tiers:
1. **Tier 1 (Direct Reference)**: Changed endpoint, route, UI selector, error code, or DTO field.
2. **Tier 2 (Jira Match)**: Test title, comment, or git log matches the change request Jira key.
3. **Tier 3 (Flow Match)**: Agent judgment matches described business flow to test intent.
4. **Tier 4 (Page Object Path)**: Test reaches changed behavior via an imported Page Object.
5. **Tier 5 (Semantic)**: High-level domain overlap (low confidence, "Should Run" only).

### Step 7: Risk Widening Heuristics
Check if any of these risk signals fired in `/tmp/fingerprints.json`:
- `auth_security`: Auth filters, JWT validation, security config touched.
- `database_migrations`: SQL, Flyway, Liquibase migration scripts changed.
- `dependencies`: `pom.xml`, `package.json`, or lockfiles altered.
- `feature_flag_defaults`: Default toggled from false to true.
- `shared_core`: Shared utility libraries or base classes modified.

**Rule**:
- If any trigger fires: Add the **Smoke Test Suite** (`@smoke`) to the recommendation.
- If >= 3 triggers fire: Recommend an unconditional **Full Suite Run**.

### Step 8: Generate Report & Execution Command
Present the report using the format defined in `templates/report.md`:
1. CR Summary (plain-English behavior changes & edge conditions).
2. Must Run tests table (with In-Regression-Suite flag, tier, confidence, reason).
3. Should Run tests table.
4. Risk Widening / Smoke alerts.
5. Coverage gaps (untested endpoints/routes with suggested scenario & steps).
6. Insufficient evidence / items for human verification.
7. Statistics (% suite reduction, estimated minutes saved).
8. Ready-to-paste run command (e.g. `npx playwright test --grep "..."` or `mvn test -Dtest=...`).
*Never automatically trigger test execution; present the command for the engineer to run.*

---

## When Evidence Is Insufficient (Playbook)

1. **No Jira Key Found**: Rely strictly on technical fingerprints (endpoints, routes, selectors).
2. **Zero Automated Tests Matched**: Explicitly state that no automated tests cover the changed paths. Detail exact manual exploratory testing steps.
3. **Ambiguous Feature Flag**: If a flag controls the change, warn the developer to verify test execution with the flag both ON and OFF.
4. **Third-Party Integrations**: Flag webhook or PSP gateway contract changes for sandbox verification.
