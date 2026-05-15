# V10 IDRE Reports Bot — Design Spec

**Date:** 2026-05-15
**Author:** Anand Wankhade (Telomere GS) with Claude
**Status:** Approved for implementation planning
**Supersedes:** V7, V8, V9 (all three retired by this spec)
**Codename:** V10

---

## 1. Context

The IDRE Reports Bot translates natural-language questions about the IDRE
platform's case, payment, and arbitration data into accurate answers. Six
prior versions (V1–V6 shipped, V7/V8/V9 evaluated) have failed to reach
production-acceptable accuracy.

Most recent evaluation (April 30, 2026) reported weighted scores of 48.5%
(V7), 69.1% (V8), 70.6% (V9) across 218 prompts. Diagnostic work has
established that those numbers overstate quality because:

- Scoring was heuristic SQL-keyword presence, not result correctness
- Only ~34 of 218 prompts contributed to the score
- Bot results were silently truncated at 50,000 rows
- Ground truth was derived from IDRE `main` branch while the platform's
  production code lives on `staging` (80+ commits ahead)
- The V9 "verification" agent only compared response shape, not values,
  and called IDRE with `limit=25` against bot results of up to 200K rows
- V7's RAG measurably hurt accuracy (-20.6% vs V8)
- V9's runtime verifier added only +1.5% vs V8

V10 starts from these findings and redesigns the bot around two principles:
(a) for known IDRE reports, achieve 1:1 result match by calling IDRE's own
API; (b) for everything else, use deterministic tool-based SQL generation
with no embeddings, no RAG, and a result-comparison test harness anchored
to staging.

## 2. Success Bar

Two modes, both required:

| Mode | Bar |
|---|---|
| **Known-report queries** (any query that maps to an IDRE report endpoint) | Byte-equal to IDRE platform output on `compare_fields`; zero clarification rounds; no fallback to derived path |
| **Derived queries** (any query that requires composition of IDRE data beyond a single report endpoint — e.g., status-summary breakdowns like Ashlee Bell's daily emails, sub-aggregations like "MTD disputes" or "1558 in final eligibility with both payments received") | Result equals canonical-SQL result at the same `:now`; row sets equal as ordered tuples after canonical sort; aggregates exact; row counts exact |

Latency and token cost are **measured but not enforced** in V10. They will
become enforced budgets in a later phase once correctness is solid.

## 3. Architecture Overview

```
                       ┌──────────────────────────────┐
                       │  Input: user NL query        │
                       └──────────────┬───────────────┘
                                      ▼
              ┌─────────────────────────────────────────────┐
              │  Router Agent  (deterministic + LLM fallback)│
              │  Output: {path, report?, parameters?, conf} │
              └────────┬───────────────────────────┬────────┘
                       │                           │
              known-report path             derived-query path
                       │                           │
                       ▼                           ▼
              ┌────────────────┐         ┌────────────────────┐
              │ IDRE API Client│         │ MCP-tool SQL Writer│
              │ + Parameter    │         │ (Gemini function   │
              │   Extractor    │         │  calling, no RAG)  │
              │ + Response     │         │ + Executor (read   │
              │   Normalizer   │         │  replica, no cap)  │
              └────────┬───────┘         └─────────┬──────────┘
                       │                           │
                       └─────────┬─────────────────┘
                                 ▼
                       ┌────────────────────────┐
                       │ Response Formatter     │
                       └────────────────────────┘
```

Existing V8 agents that remain in V10 with minor changes:
`ambiguity_scorer`, `clarification_agent`, `context_loader`,
`response_formatter`, `output_formatter`, `post_processor`, `executor`
(with row-cap changes), `feedback_injector`, `debugger_agent`.

Existing V7/V8/V9 components **removed** in V10:
- ChromaDB and any embedding-model code (V7 RAG)
- `idre_verifier.py` (V9 runtime verifier) — its core idea moves into the
  test harness
- `metric_cards.json` triggering inside `sql_writer.py`
- `sql_templates.json` triggering inside `sql_writer.py`
- `successful_queries.json` (V6 rolling few-shot window)
- `_COMMONLY_HALLUCINATED` dictionary in `schema_verifier.py`
- `file_summaries.json`, `module_keywords.json`, `repo_map.txt` in the
  knowledge folder (these were inputs to RAG retrieval)

## 4. Component 1 — Router Agent

**File:** `agents/router.py` (new)

**Input:** `user_query: str` from `GraphState`

**Output:** `RouterDecision`:

```python
class RouterDecision(TypedDict):
    path: Literal["known", "derived", "clarify"]
    report: str | None        # e.g. "due-dates", "outstanding-payments"
    parameters: dict | None   # e.g. {"urgency": "overdue", "limit": 10000}
    confidence: float          # 0.0..1.0
    reasoning: str             # for the trace
```

**Two-stage decision:**

1. **Deterministic signature match.** Each known report has a
   `RouteSignature` entry in `config/route_signatures.json`:

   ```json
   {
     "id": "due-dates",
     "trigger_phrases": ["due date", "overdue", "deadline", "past due", "approaching", "urgent"],
     "required_entities": ["case", "date"],
     "parameter_extractors": [
       {"name": "urgency", "regex": "(overdue|urgent|warning|approaching)", "default": "all"},
       {"name": "limit", "from_phrases": [{"match": "top \\d+", "extract_int": true}], "default": 10000}
     ],
     "idre_endpoint": "/api/reports/due-dates",
     "method": "GET"
   }
   ```

   Computes a confidence by counting trigger-phrase matches against the
   query. Confidence ≥ 0.85 → returns `path="known"` with extracted
   parameters and skips stage 2.

2. **LLM fallback.** Only invoked when stage 1 confidence < 0.85.
   Single Gemini call with the 14 `RouteSignature` entries packaged as
   function declarations. Gemini either picks one (and the function-call
   args become `parameters`) or returns "none of these" → `path="derived"`.
   Confidence is taken from a structured-output field.

3. **Clarify trigger.** If LLM fallback returns confidence < 0.6 OR the
   query has unresolved entity references (e.g., "their cases" with no
   prior context), router returns `path="clarify"` and the existing
   `clarification_agent` runs.

**Signatures cover 14 IDRE reports** (extracted from staging):
`dashboard-stats`, `due-dates`, `case-analytics`, `team-performance`,
`outstanding-payments`, `unpaid-disputes`, `idre-payouts`, `cms-payments`,
`case-balance`, `auditing/daily-funds`, `auditing/daily-transactions`,
`recent-activity`, `payment-variance`, and one open slot for new reports
shipping on staging.

**Adding a new known report:** add one entry to
`config/route_signatures.json` and one entry to `idre_api_client.py`. No
agent code changes.

## 5. Component 2 — Known-Report Path

Three sub-components, all new:

### 5.1 `agents/idre_api_client.py`

Typed wrappers for each of the 14 IDRE report endpoints. Each wrapper:

- Accepts the parameter dict from the router
- Authenticates via dev auto-login (`/api/dev/auto-login`) locally; via
  service token in production
- Calls the IDRE endpoint with a 300-second timeout (configurable; will be tuned in a later phase along with latency budgets)
- Returns the raw response JSON plus metadata (status code, latency,
  IDRE response headers including any `X-Git-Sha` if available)
- Caches successful responses for 60 seconds keyed by
  `(endpoint, sorted-query-params)`

Failure modes:
- HTTP 4xx → return with `error: "client_error"` so the bot can apologize
- HTTP 5xx or timeout → fall back to derived path with the same intent;
  the trace records "known path failed, falling back"
- Auth failure → fail loudly; do not silently fall back

### 5.2 `agents/parameter_extractor.py`

Converts NL parameters into IDRE API query parameters. Built around the
`parameter_extractors` entries in each `RouteSignature`. Handles:

- **Date ranges:** "today", "yesterday", "this week", "last 7 days",
  "month-to-date", "Q1", explicit dates. All resolved against the
  `:now` timestamp locked at the start of the request. EST is the
  reporting timezone — converted from server-local time.
- **Entity names:** "Halo", "Capitol Bridge", etc. → `search` parameter
- **Status filters:** "overdue", "urgent", "pending" → endpoint-specific
  enum values
- **Pagination:** "top 50", "first 10" → `limit` parameter. Default
  limit is **10000** (the IDRE API's own default), not 25 (V9's broken
  default).

### 5.3 `agents/response_normalizer.py`

IDRE API responses have inconsistent shapes — sometimes
`{data: [...]}`, sometimes `{data: {cases: [...], totalCount: n}}`,
sometimes a bare array. Normalizer flattens these into the canonical
`{rows: [...], meta: {totalCount, ...}}` shape that the formatter expects.
This is a pure transformation — no logic, no LLM.

## 6. Component 3 — Derived-Query Path

Inherits V8's MCP-tool architecture with the changes below.

### 6.1 Tool Catalog (V10)

Replacing the V8 6-tool set with this 8-tool set (V8 had `get_pricing_info` which V10 folds into `lookup_business_term`; V10 adds 3 new tools). **Bold = new in V10.**

| Tool | Status from V8 | V10 behavior |
|---|---|---|
| `get_report_reference` | rewritten | Returns Prisma source + auto-generated SQL translation + `js_postprocessing` block. NO hand-written `bot_sql_equivalent`. Pulled from `knowledge/v10/business_logic.json`. |
| `get_table_schema` | rewritten | Reads from `knowledge/v10/schema_catalog.json` (built from staging `schema.prisma`). Augmented with `INFORMATION_SCHEMA` lookups against staging RDS at build time. |
| `get_enum_values` | rewritten | Reads from `knowledge/v10/enum_catalog.json` (built from staging TypeScript enums + RDS-sampled distinct values). |
| `lookup_business_term` | kept | Same behavior. Glossary stays in `config/business_glossary.json` for now; automated extraction is deferred to a later phase. |
| `list_available_reports` | kept | Same behavior. |
| **`find_filter_pattern`** | **new** | `(intent: str) -> {sql_expression, explanation}`. Maps "month-to-date" / "today" / "last 7 days" / "this quarter" to SQL date expressions with EST timezone handling. |
| **`verify_sql_executes`** | **new** | `(sql: str) -> {ok, row_count, columns, error?, exec_ms}`. Dry-runs the SQL on the read replica with `EXPLAIN` first. LLM gets ground-truth execution feedback before claiming SQL is done. |
| **`get_idre_business_logic`** | **new** | `(report_name: str) -> {prisma_query, js_postprocessing, sql_equivalent, notes}`. Returns the **full Level-3 logic** from staging route handlers — Prisma fetch + the JavaScript post-processing that runs after. The LLM needs to see the JS post-processing to translate `.filter()`/`.some()` patterns into `NOT EXISTS` subqueries. |

Removed from V8: `get_pricing_info` (moved into `business_glossary.json`
under category="pricing" — accessible via `lookup_business_term`).

### 6.2 System Prompt (rewritten)

The V8 system prompt is ~65 lines mixing display rules, payment knowledge,
SQL rules, and reservation about table names. Most of it duplicates what
tools return — and Gemini ignored it (V6 evidence: prompt said
`CASE_PAYMENT` for CMS but Gemini still generated `CMS_INVOICE_PAYMENT`).

V10 system prompt: ≤ 20 lines, contains only:

1. Role statement
2. Hard rules: SELECT-only; backtick `case`; no `LIMIT` unless asked
3. **Mandatory protocol:**
   - Call `get_idre_business_logic` if the user's intent matches any known IDRE report. Use its `sql_equivalent` as the starting point.
   - Call `verify_sql_executes` before claiming SQL is final.
   - If `verify_sql_executes` returns an error, fix and re-verify. Max 3 rounds.
4. Output format

Everything else (display rules, payment knowledge, "always include
shortId", etc.) moves to either the tool responses or the `post_processor`
agent.

### 6.3 Executor changes

`agents/executor.py`:

- **Production execution** keeps a configurable row cap (default raised
  from 50,000 to **100,000**) to prevent runaway queries.
- **Test execution** disables the row cap entirely. A test that produces
  >100K rows is acceptable if the expected result also has >100K rows.
- Logs `was_capped: bool` on every execution. If a test result was
  capped at any point, the test record's verdict is `FAIL` regardless
  of comparison outcome.
- Continues to use read replica for SELECT; continues to block all DML.

## 7. Component 4 — Knowledge & Ground-Truth Pipeline

**Today: zero pipeline exists.** All V7/V8/V9 knowledge files are frozen
April 29, 2026 manual snapshots.

### 7.1 Pipeline scripts

```
scripts/build_knowledge/
├── 01_sync_staging.py            # git fetch + checkout origin/staging in idre/
├── 02_extract_reference_cards.py # Parse app/api/reports/**/route.ts + lib/reports/*.ts → cards
├── 03_extract_schema.py          # Parse prisma/schema.prisma → schema_catalog.json
├── 04_extract_enums.py           # Parse all .ts enum decls + sample staging RDS → enum_catalog.json
├── 05_extract_business_logic.py  # Frontier-model conversion: Prisma + JS → SQL equivalent
├── 06_validate_pipeline.py       # Self-validate all generated artifacts
└── run_all.py                    # Orchestrator: runs 01→06, atomic swap
```

### 7.2 Outputs

```
knowledge/v10/
├── manifest.json                 # {idre_git_sha, idre_branch, generated_at, file_hashes, validation_summary}
├── report_reference_cards.json   # 14 cards, auto-extracted
├── schema_catalog.json           # From staging schema.prisma + INFORMATION_SCHEMA
├── enum_catalog.json             # TS enums × RDS-sampled distinct values
├── business_logic.json           # Full per-report Prisma+JS+SQL triple
└── filter_patterns.json          # Date/time expressions, EST-aware
```

### 7.3 Atomic swap discipline

Pipeline writes to `knowledge/v10_pending/`, runs validation, then renames
`v10_pending/` → `v10/` (replacing previous `v10/` in one filesystem op).
If validation fails, `v10_pending/` is preserved for inspection and last-good
`v10/` stays live. Bot reads `v10/manifest.json` at startup and logs the
`idre_git_sha` it's running against.

### 7.4 Frequency and triggering

- **Nightly cron:** runs `run_all.py --branch staging` at 02:00 EST
- **On-demand:** developer runs `python scripts/build_knowledge/run_all.py --branch <branch>` for fast iteration
- **Drift detection:** post-run, compare today's manifest file hashes
  against yesterday's. If changed reports overlap with the last 7 days'
  test failures, fire a Slack alert "report X changed, expect failures"

### 7.5 Level-3 conversion (the hard part)

Past V7/V8 attempts hand-translated `route.ts` files into reference cards.
Hand translation is the root cause of CMS_INVOICE_PAYMENT-style
hallucinations: bots see stale wrong SQL and copy it.

V10 uses a frontier-model conversion step inside
`02_extract_reference_cards.py` and `05_extract_business_logic.py`:

1. Read `app/api/reports/<name>/route.ts` + its `lib/reports/<name>.ts` dependencies
2. Send to Gemini 2.5 Pro with a strict prompt: "Here is the Prisma query
   and the JavaScript post-processing. Output: (a) raw SQL equivalent,
   (b) any logic that must run in code after SQL"
3. Run the generated SQL against staging RDS, call the original IDRE API
   endpoint, compare results
4. Cards that match within ±1% on row count + ±0.01 on key aggregates
   are persisted as-is; cards that don't match get a `needs_review: true`
   flag and a human reviews before they go live

This conversion runs **once at build time per report change**, not per
query. The cost is bounded and acceptable.

### 7.6 What we throw out from V7/V8/V9 knowledge folder

- `file_summaries.json` (851KB) — bled in from the Artoo SDLC bot; never used by reports bot
- `repo_map.txt` (89KB) — was an input to RAG retrieval
- `module_keywords.json` (17KB) — was an input to RAG retrieval
- `platform_rules.json` (15KB) — replaced by auto-generated `enum_catalog.json` and `business_logic.json`
- `metric_cards.json` — replaced by router signatures and tool responses
- `sql_templates.json` — replaced by `get_idre_business_logic` returning fresh-from-staging SQL

`business_glossary.json` (47KB) is **kept manually** for V10. Automated
extraction from Confluence + staging is parked for a later phase.

## 8. Component 5 — Test Harness

The most important component. Without this we cannot know if anything is
working.

### 8.1 Layout

```
testing/v10_harness/
├── run_tests.py                  # pytest entry point
├── test_set.jsonl                # The 80-prompt test set
├── conftest.py                   # Staging RDS, IDRE local server fixtures
├── runner.py                     # Per-prompt execution
├── compare.py                    # Row-set equality, aggregate diff, IDRE JSON diff
├── measurements.py               # Latency + token recording (informational only)
├── temporality.py                # :now anchoring, parameterized SQL execution
└── reports/
    └── latest.html               # Per-run report with diffs
```

### 8.2 Test record schema

Two schemas, one per category.

**Known-report test:**

```json
{
  "id": "K_due_001",
  "category": "known-report",
  "report": "due-dates",
  "prompt": "list all overdue cases as of today across all 4 due date columns",
  "expected_idre_call": {
    "method": "GET",
    "path": "/api/reports/due-dates",
    "query": {"urgency": "overdue", "limit": "10000"}
  },
  "compare_fields": [
    "data.totalCount",
    "data.cases[*].caseId",
    "data.cases[*].due_date",
    "data.cases[*].due_date_until_decision",
    "data.cases[*].eligibilityDueDate",
    "data.cases[*].paymentDueDate",
    "data.cases[*].status"
  ],
  "temporality": "variant"
}
```

**Derived-query test:**

```json
{
  "id": "D_daily_status_001",
  "category": "derived-query",
  "prompt": "give me today's IDRE daily status summary numbers — total disputes, MTD, new today, then breakdown by status with all sub-items",
  "ground_truth_sql": [
    {"name": "total_disputes", "sql": "SELECT COUNT(*) AS v FROM `case`"},
    {"name": "mtd_disputes", "sql": "SELECT COUNT(*) AS v FROM `case` WHERE createdAt >= DATE_FORMAT(:now, '%Y-%m-01 00:00:00')"},
    {"name": "new_today", "sql": "SELECT COUNT(*) AS v FROM `case` WHERE DATE(createdAt) = DATE(:now)"},
    {"name": "pending_rfi", "sql": "SELECT COUNT(*) AS v FROM `case` WHERE status='PENDING_RFI'"},
    {"name": "final_eligibility_review_both_paid", "sql": "SELECT COUNT(*) FROM `case` c WHERE c.status='FINAL_ELIGIBILITY_REVIEW' AND EXISTS (SELECT 1 FROM case_payment_allocation cpa JOIN payment p ON cpa.paymentId=p.id WHERE cpa.caseId=c.id AND cpa.partyType='INITIATING' AND p.direction='INCOMING' AND p.status IN ('PENDING','APPROVED','COMPLETED')) AND EXISTS (SELECT 1 FROM case_payment_allocation cpa JOIN payment p ON cpa.paymentId=p.id WHERE cpa.caseId=c.id AND cpa.partyType='NON_INITIATING' AND p.direction='INCOMING' AND p.status IN ('PENDING','APPROVED','COMPLETED'))"}
  ],
  "bot_must_return_keys": ["total_disputes", "mtd_disputes", "new_today", "pending_rfi", "final_eligibility_review_both_paid"],
  "temporality": "variant"
}
```

### 8.3 Temporality handling

Three classes:

| Class | Ground truth storage | When evaluated |
|---|---|---|
| `KNOWN_REPORT_PARALLEL_CALL` | IDRE API path + params | Test time, parallel call against same DB state |
| `DERIVED_SQL_PARAMETERIZED` | Canonical SQL with `:now` parameter | Test time, both bot and harness anchored to same `:now` |
| `DERIVED_SQL_STATIC` | Canonical SQL, no parameters | Test time, plain execution (e.g., "cases closed in 2024" — closed dates don't change) |

The `temporality` field on each test record (`variant` or `stable`) tells
the harness which class to use.

**Anchoring discipline:**

1. Harness locks `now = NOW()` from staging RDS at the moment the bot's
   request begins
2. Bot runs its full pipeline (which may include router → IDRE API call OR
   router → SQL writer → executor)
3. Harness runs the ground-truth call (parallel IDRE API call OR
   parameterized SQL) using the same `:now`
4. Both bot's and harness's views of the DB are at the same logical
   instant — temporal drift is impossible

**The Ashlee Bell emails and the user's status-summary image are test-set
seeds, not ground truth.** From each we extract:
- The intent ("daily status summary by sub-status")
- The structural breakdown (which numbers correspond to which sub-categories)
- We write the canonical SQL ourselves, validate it against staging
- The numbers in the email/image are used only to sanity-check that the
  canonical SQL produces results in the right ballpark on the date of
  the email

### 8.4 PASS criteria

For **known-report tests**:
- Bot's response JSON must be byte-equal to IDRE's response JSON on
  `compare_fields` (after stripping volatile fields like timestamps)
- Network errors, timeouts, fallback-to-derived: **FAIL**
- Any clarification round: **FAIL**

For **derived-query tests**:
- Set of returned rows must equal expected rows (order-agnostic,
  tuple-level equality after canonical sort)
- Tolerance for floating-point columns: ±0.01
- Tolerance for `row_count`: zero — must match exactly
- Tolerance for aggregates: zero — must match exactly
- Any execution capped at 100K rows: **FAIL** with "result too large for test"
- Bot must return all keys listed in `bot_must_return_keys`

PARTIAL exists for known-report tests only and is reserved for cases
where IDRE itself returns randomized internal pagination — column set
matches, row count within ±1%, aggregates within ±1%.

A test that produces wrong rows but valid SQL is **FAIL**, no partial credit.

### 8.5 Two-tier test runner

| Tier | Set size | Runs on | Purpose |
|---|---|---|---|
| Fast | 30 prompts (subset) | Every push to staging-tracking branches | Catch regressions quickly |
| Slow | Full 80 prompts | Nightly + on demand | Comprehensive correctness |

No time budget enforced — tests run to completion. Concurrency is capped
at 3 to avoid hammering staging RDS.

### 8.6 Initial test set composition

| Bucket | Count | Source |
|---|---|---|
| Known-report basic queries | 28 | 2 per × 14 reports (smoke + a filter) |
| Known-report filtered queries | 14 | 1 per report — `?status=X`, `?date=Y`, etc. |
| Derived from Ashlee's emails | 15 | Daily status summary breakdowns (V1 history archived 7 .eml files) |
| Derived from user's image example | 7 | Each numbered item in the screenshot — total/MTD/new today, status breakdowns, sub-aggregations |
| Derived ad-hoc | 10 | Real questions ops staff asks today, gathered week 1 |
| Adversarial / known-hard | 6 | Outstanding-payments NOT EXISTS; case-balance refunds; CMS_PAYMENT type confusion; 4-due-date COALESCE; payout entity matching; 7-day recency |
| **Total** | **80** | |

### 8.7 Prior testing mistakes — explicit V10 fix table

| # | Past mistake | V10 fix |
|---|---|---|
| 1 | 50K row cap silently masked failures | Test executor uses no cap; production cap raised to 100K; any cap-trigger fails the test |
| 2 | Heuristic SQL keyword scoring (25%+25%+25%+25%) | Result-set comparison only; no keyword scoring anywhere |
| 3 | 218 prompts but only ~34 scored | Every prompt has concrete ground truth; if we can't write it, the prompt doesn't enter the set |
| 4 | Clarification auto-answered with heuristic dict | Test prompts pre-parameterized; ambiguity scorer should return zero; any clarification = FAIL |
| 5 | Ground truth from `main`, platform on `staging` | All ground truth regenerated from staging on each pipeline run |
| 6 | "Execution OK" credit just for `row_count > 0` | Row count alone never gives points; row content must match |
| 7 | 6h 37m test runtime, no incremental signal | Two-tier runner: 30-prompt fast tier on every push, 80-prompt slow tier nightly |
| 8 | Auto-retries silently hid problems | Track `retry_count` per test; PASS-on-first-try and PASS-after-retry tracked separately |
| 9 | No cost / latency tracking | Captured per record; reported but **not enforced** in V10 |
| 10 | One scorer used for both modes — apples to oranges | Separate criteria per category (known vs derived) |
| 11 | Static expected numbers grew stale | All ground truth computed at test time with `:now` anchoring |
| 12 | V9 verifier called IDRE with `limit=25` against bot results of 200K | V10 known-report tests call IDRE with the same params the bot used |

## 9. What V10 is NOT (Out of Scope)

Listed so we don't get scope-crept in implementation:

- **Approach B** (SQL-only path with result-match testing): not in V10.
  Will be reconsidered after V10's test harness reveals where the derived
  path actually plateaus.
- **Approach C** (fine-tuning on curated pairs): not in V10. Saved for
  after V10 produces verified prompt → SQL pairs as a side effect of the
  test harness.
- **Automated Confluence + staging glossary extraction.** V10 keeps the
  manual `business_glossary.json`.
- **Latency budgets / token-cost enforcement.** Measured, not enforced.
- **Production EC2 deployment changes.** V10 runs the same EC2 +
  Streamlit deployment as V5+. Deployment pipeline changes are out of scope.
- **Multi-tenant access control rewrites.** V10 keeps V5+'s 9-role access
  control as-is.
- **New report types beyond the 14 currently on staging.** V10 stays in
  sync with whatever staging has; new reports get added via signature +
  client wrapper, not architecture changes.
- **Conversational follow-ups / multi-turn context.** Each query is
  treated as standalone in V10.

## 10. Implementation Milestones

Two weeks of focused work. The order is non-negotiable — the test harness
exists before any other change ships, because we cannot otherwise tell if
changes help.

| Day | Deliverable | Owner |
|---|---|---|
| 1 | Test harness skeleton (`runner.py`, `compare.py`, `temporality.py`, `measurements.py`) + 10 hand-coded known-report tests | Engineering |
| 2 | Run baseline: V8 unchanged against the 10 tests → first real correctness numbers we'll have ever seen | Engineering |
| 3 | Build Component 4 pipeline scripts 01–06 | Engineering |
| 4 | Generate first `knowledge/v10/` artifacts from staging | Engineering |
| 5 | Build Router (Component 1) + 5 known-report wrappers (due-dates, outstanding-payments, case-balance, dashboard-stats, cms-payments) | Engineering |
| 6 | Expand test set to 40 prompts; run V8 + new known-path | Engineering |
| 7-8 | Rewrite SQL writer system prompt; add 3 new tools to Component 3; remove `metric_cards`/`sql_templates`/`successful_queries` paths | Engineering |
| 9 | Expand known-report wrappers to all 14 reports | Engineering |
| 10 | Full 80-prompt test set complete; full V10 test run; triage and fix failures | Engineering |

After Day 10 we have a result-comparison-validated V10. The number we
report will be real, not a heuristic.

## 11. Definition of Done for V10

- All 14 IDRE reports route through Component 2 with 1:1 result match on
  the test harness
- Derived-query path passes ≥ 90% of the 38 derived-query tests on first
  try (no retries)
- Knowledge pipeline runs successfully on staging every night for 5
  consecutive nights with validation passing
- Bot is connected to staging RDS read replica for derived execution
- Production deployment remains on EC2 with the existing CDK stack
  (no infrastructure changes)
- `business_glossary.json` reviewed and confirmed accurate for the 14
  known reports

## 12. Risks and Open Questions

| Risk | Mitigation |
|---|---|
| Staging RDS lag / replication delay creates ground-truth flakiness | Test harness reads `now` from staging RDS, not local clock; both bot and harness see same logical instant |
| Frontier-model Level-3 conversion produces wrong SQL for edge cases | Validation gate in `05_extract_business_logic.py` rejects cards that don't match within tolerance; `needs_review` flag for human review |
| IDRE staging branch ships breaking changes mid-week | Drift detection compares manifest SHAs; Slack alert on report-source changes; rebuild can be re-run on demand |
| Test set of 80 is too small to catch all failure modes | Acknowledged. We grow it as we discover failures. Better than the 218-prompt set with no real scoring. |
| `:now` anchoring across bot vs harness has timing skew | Harness locks `:now` once and passes the same value to both; the bot's API client reads `:now` from a request header rather than `NOW()` calls |
| 14 reports underestimate staging's true count | Component 4's `02_extract_reference_cards.py` enumerates all routes under `app/api/reports/`; any unexpected ones are flagged |

---

**End of spec.** Next step: implementation planning via the `writing-plans` skill.
