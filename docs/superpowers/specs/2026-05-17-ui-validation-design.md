# V10 Derived-Query UI-Scraping Validation — Design Spec

**Date:** 2026-05-17
**Author:** Anand Wankhade (Telomere GS) with Claude
**Status:** Approved for implementation planning
**Builds on:** `2026-05-15-v10-reports-bot-design.md` (V10 main spec) and `2026-05-17-day9-status.md` (current state)

---

## 1. Context

V10's known-report path is shipped at 15/15 byte-equal PASS against IDRE's `/api/reports/*` endpoints (tagged `day9-complete`). The derived-query path — used when a prompt doesn't match a known report — currently has no measurement of correctness. The spec's existing validation classes for derived queries (`DERIVED_SQL_PARAMETERIZED`, `DERIVED_SQL_STATIC`) require hand-written canonical SQL that we'd have to verify ourselves first.

This spec adds a 4th validation class — `DERIVED_PLAYWRIGHT_UI` — that uses IDRE's own UI as the ground truth. Whatever number IDRE displays to a real human user IS the canonical answer the bot is expected to match. UI scraping eliminates the chicken-and-egg of canonical SQL ("how do we know OUR canonical SQL is right") for any query that has a UI representation.

## 2. Success Bar

For the ~12-15 derived prompts in the initial test set (mapped from your status-summary screenshot + Ashlee's daily emails), each test PASSES iff:
- Bot's scalar result (or breakdown dict) equals the value(s) extracted from IDRE local's UI at the same `:now` moment
- Equality is exact for integers, ±0.01 for floats, after stripping display formatting (`,`, `$`, `%`)
- Both sides read from the same database

## 3. Architecture Overview

```
test_set.jsonl entry (category: "derived-ui")
       │
       ▼
run_derived_ui_test(record, bot_runner, playwright_page, now_anchor)
   │                                │
   ▼                                ▼
Bot runs prompt              Playwright drives IDRE local UI
via V8 pipeline               per named template + params
+ V10 sql_writer              → extracts scalar/dict from DOM
+ 8 tools → number(s)
       │                                │
       └──────────► compare ◄───────────┘
                    (exact equality)
```

A new pytest file (`test_baseline_derived_ui.py`) parametrizes over entries with `category: "derived-ui"`. The other 3 derived test categories continue to work unchanged.

## 4. DB Alignment (load-bearing prerequisite)

For UI numbers to validate bot numbers, both must read from the same database.

**Decision:** Point IDRE local at staging RDS (the same DB the V10 bot's executor already reads).

**Implementation:** Modify `C:\Users\anand\Downloads\local\idre\.env`:
- `DATABASE_URL=mysql://app_idre_rw:<pwd>@mysql-8-stage-1-cluster.cluster-cc1r7ekdbl8j.us-east-1.rds.amazonaws.com:3306/idre_stage`
- Keep all existing dev-mode safeguards (`NEXT_PUBLIC_TEST_MODE=true`, `SMTP_HOST=mailpit-...`, test Stripe keys, dead-end SQS URLs)

**Risk mitigation gate** (MUST complete before authoring any tests):
1. Enable `general_log=ON` on staging RDS (or use Performance Insights / CloudWatch slow-query log)
2. Restart IDRE local with new `.env`
3. Hit `/api/dev/auto-login` from a browser
4. Grep general_log for INSERT/UPDATE/DELETE on staging during the request window
5. **If clean: proceed.** If any writes happen: abort this approach, fall back to seeding local orchid-idre Docker container with a sanitized staging snapshot instead

This gate is non-negotiable. We will not ship UI validation unless we've proven that running IDRE local against staging is read-only in practice.

## 5. Components

### 5.1 `testing/v10_harness/ui_validators/` (new module)

| File | Responsibility |
|---|---|
| `base.py` | `UIValidator` protocol: `extract(page, params) -> dict[str, Number] \| Number`. Shared helpers: `login(page)`, `parse_number(text)` (strip commas/$/%), `find_with_retry(page, selector, timeout=10s)`. |
| `dashboard_stats.py` | Reads scalar stat cards from `/dashboard`. Supports `params={"fields": ["totalCases", ...]}` → returns dict. |
| `case_status_filter.py` | Navigates `/disputes`, applies status filter via UI, reads count badge. Supports `params={"status": "PENDING_RFI"}` or `params={"statuses": [...]}` (multi-select). Also supports created-today / created-MTD filters. |
| `due_dates_filter.py` | Navigates due-dates report page, applies urgency filter, reads pagination total. Params: `{"urgency": "overdue"\|"warning"\|"approaching"\|"all"}`. |
| `payment_lifecycle.py` | Reads P=0/P=1/P=2 segment counts (the payment-pending breakdown specific to Ashlee's emails). Params: `{"segment": "P0"\|"P1"\|"P2"}`. |
| `__init__.py` | Registry mapping validator name → class. |
| `llm_fallback.py` | **Stub for V1.** Future: Gemini-driven Playwright agent that navigates autonomously when no template matches. Not implemented in this scope. |

### 5.2 `testing/v10_harness/runner.py` (extended)

Add `run_derived_ui_test(record, bot_runner, page, now_anchor) -> TestResult`:
- Bot runs prompt via existing `bot_runner` callable
- Bot result reduced to scalar or dict per `record.bot_must_return_keys`
- Validator looked up via name in registry; called with `page` + `validator_params`
- Comparison via existing `compare_aggregates` with `float_tolerance=0.01`
- Returns `TestResult` with verdict, diffs, measurements

### 5.3 `testing/v10_harness/conftest.py` (extended)

Add session-scoped fixture:
```python
@pytest.fixture(scope="session")
def playwright_page(idre_session):  # idre_session ensures auto-login cookies
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        # Transfer auto-login cookies from requests.Session to Playwright context
        for c in idre_session.cookies:
            context.add_cookies([{...}])
        page = context.new_page()
        yield page
        browser.close()
```

### 5.4 `testing/v10_harness/tests/test_baseline_derived_ui.py` (new)

Parametrizes over `category: "derived-ui"` entries. Uses `playwright_page` + `now_anchor` + `bot_runner` fixtures. Saves per-test JSON to `reports/` plus a screenshot on FAIL.

### 5.5 Test record schema

```json
{
  "id": "D_pending_rfi_ui",
  "category": "derived-ui",
  "prompt": "how many disputes are in pending RFI status",
  "validator": "case_status_filter",
  "validator_params": {"status": "PENDING_RFI"},
  "bot_must_return_keys": ["count"],
  "temporality": "variant"
}
```

For breakdown extraction:
```json
{
  "id": "D_dashboard_summary_ui",
  "category": "derived-ui",
  "prompt": "give me dashboard overview",
  "validator": "dashboard_stats",
  "validator_params": {"fields": ["totalCases", "activeArbitrators", "currentMonthCases"]},
  "bot_must_return_keys": ["totalCases", "activeArbitrators", "currentMonthCases"],
  "temporality": "variant"
}
```

## 6. Data Flow Per Test

1. Harness reads `:now = UTC_TIMESTAMP()` from staging RDS, locks it
2. Session-scoped Playwright browser already launched, auto-login cookies set
3. Bot runs prompt via `core/orchestrator.run_query` (V8 pipeline + V10 sql_writer + 8 tools)
4. Bot returns rows; harness reduces to scalar/dict by `bot_must_return_keys`
5. Validator looked up by name; `validator.extract(page, validator_params)` runs
6. Compare bot result vs validator result via `compare_aggregates`
7. Write `reports/<id>.json` with both values, diffs, latencies; screenshot on FAIL

## 7. Error Handling

| Failure mode | Behavior |
|---|---|
| IDRE local unreachable | SKIP (existing fixture skips on HTTP 4xx/5xx, ConnectionError, Timeout) |
| Playwright nav timeout | FAIL; save screenshot to `reports/<id>_failure.png`; record timeout in diffs |
| Validator selector miss | FAIL; save DOM snippet around expected element; record selector in diffs |
| Bot pipeline error | FAIL; include `agent_trace` in test result |
| Number-parse error | FAIL; record the raw extracted text in diffs |
| DB alignment violated (bot and UI return wildly different orders of magnitude) | FAIL but record a sentinel warning for human review |

## 8. Testing the Validators

Each validator gets two layers of tests:
- **Unit**: static HTML fixture loaded via `page.set_content(html_string)`, extraction logic verified without a live IDRE server
- **Integration**: 1 live run per validator against IDRE local at session start, confirms selectors still work

Run as part of `pytest testing/v10_harness/tests/` (unit) and gated to nightly (integration).

## 9. Initial Test Set (12-15 entries)

Mapped from the user's status-summary screenshot + recurring Ashlee email lines:

| ID | Prompt (NL) | Validator | Params |
|---|---|---|---|
| D_total_disputes_ui | "total disputes" | dashboard_stats | `{"fields": ["totalCases"]}` |
| D_mtd_disputes_ui | "month-to-date disputes" | dashboard_stats | `{"fields": ["currentMonthCases"]}` |
| D_new_today_ui | "new disputes today" | case_status_filter | `{"created": "today"}` |
| D_initial_elig_ui | "disputes in initial eligibility review" | case_status_filter | `{"status": "INITIAL_ELIGIBILITY_REVIEW"}` |
| D_pending_rfi_ui | "disputes in pending RFI" | case_status_filter | `{"status": "PENDING_RFI"}` |
| D_payment_pending_ui | "disputes in payment pending status" | payment_lifecycle | `{"segment": "P0"}` |
| D_pending_second_ui | "disputes pending second payment" | payment_lifecycle | `{"segment": "P1"}` |
| D_final_elig_both_paid_ui | "final eligibility review, both paid" | payment_lifecycle | `{"segment": "P2"}` |
| D_final_elig_completed_ui | "final eligibility completed" | case_status_filter | `{"status": "FINAL_ELIGIBILITY_COMPLETED"}` |
| D_final_det_pending_ui | "final determination pending" | case_status_filter | `{"status": "FINAL_DETERMINATION_PENDING"}` |
| D_ineligible_admin_ui | "ineligible pending admin fee" | case_status_filter | `{"status": "INELIGIBLE_PENDING_ADMIN_FEE"}` |
| D_pending_closure_pay_ui | "pending closure payments" | case_status_filter | `{"status": "PENDING_ADMINISTRATIVE_CLOSURE"}` |
| D_completed_ui | "completed disputes" | case_status_filter | `{"status": "COMPLETED"}` |
| D_mtd_final_det_ui | "MTD final determinations rendered" | case_status_filter | `{"status": "COMPLETED", "modified": "mtd"}` |
| D_mtd_defaults_ui | "MTD defaults rendered" | case_status_filter | `{"closureReason": "DEFAULT", "modified": "mtd"}` |

## 10. Out of Scope (V1)

- **LLM-driven Playwright agent** (`llm_fallback.py`) — stub only. Real implementation deferred until we know which test prompts can't be served by the 4 templates.
- **Row-set comparison** (extracting dispute IDs from UI tables) — V1 is scalars + dicts only. Adding row-set comparison is a follow-up if recurring "list me the cases" tests appear.
- **CI integration** — V1 runs locally on-demand. Wiring to GitHub Actions / nightly comes after the first measured pass-rate exists.
- **Replacing existing derived test classes** — `DERIVED_SQL_PARAMETERIZED` and `DERIVED_SQL_STATIC` keep working in parallel for queries with no UI representation.

## 11. Implementation Sequence

| Phase | Deliverable |
|---|---|
| 1 | Risk-gate: enable general_log on staging, point IDRE local at staging RDS, verify no writes |
| 2 | Validator base class + Playwright fixture in conftest |
| 3 | `dashboard_stats` validator + 2 tests; baseline run |
| 4 | `case_status_filter` validator + 8 tests; baseline run |
| 5 | `payment_lifecycle` validator + 3 tests; baseline run |
| 6 | `due_dates_filter` validator + 2 tests; baseline run |
| 7 | Full 15-test baseline; surface real derived-path PASS rate; iterate where bot fails |

## 12. Definition of Done

- All 15 derived-ui tests pass against the V10 bot
- Validator unit tests + 1 integration test per validator pass
- DB alignment safety gate verified clean (no writes from IDRE local)
- Screenshot capture on FAIL works end-to-end
- Test set committed to `testing/v10_harness/test_set.jsonl`
- Tag `derived-ui-validation` pushed to GitHub

## 13. Risks

| Risk | Mitigation |
|---|---|
| IDRE local writes to staging | DB alignment safety gate (section 4). Abort if any writes happen. |
| UI selectors brittle (break on IDRE refactor) | Use `data-testid` where present; document fallback XPath; integration test catches breakage early |
| Bot result format doesn't reduce cleanly to scalar | Each test entry's `bot_must_return_keys` is hand-curated; if the bot returns nested structure, the test reducer handles it; if still ambiguous, flag in test entry's `notes` |
| Playwright + Next.js dev-mode race conditions | Use `page.wait_for_load_state("networkidle")` after navigation; use `page.locator(selector).wait_for(state="visible")` before extract |
| Staging RDS data drifts between bot call and UI scrape | Both calls happen within ~5-30s; harness records `:now`; if values differ by orders of magnitude flag for human review |
| LLM fallback never gets built and 4 templates miss edge cases | The 15 initial tests are explicitly chosen to match the 4 templates. Expansion past these 15 will surface what the templates can't do, informing whether LLM fallback is needed. |
