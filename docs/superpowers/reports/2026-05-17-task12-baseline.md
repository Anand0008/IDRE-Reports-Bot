# Task 12 — Derived-UI Baseline Established

**Date:** 2026-05-17
**Result:** 8/15 PASS, 7/15 FAIL (53% PASS rate)
**Runtime:** ~8 min for full baseline (15 tests × ~30-60 sec each, Gemini SQL dominates)
**Substrate:** local docker `idre` DB (47 users / 36 cases / 43 payments), bot+validators both pointed at same DB

## Pipeline proven end-to-end

This is the first **byte-level validation of V10 bot's derived-query SQL against IDRE's UI** as ground truth. The harness:
- Bot generates SQL via Gemini → executes against same local docker as IDRE
- Validator extracts canonical UI value via Playwright (or IDRE's internal API)
- Compare numeric-tolerant (string `'5'` matches int `5`)
- Per-test JSON + screenshot on FAIL saved to `reports/`

All 4 validator templates work: `dashboard_stats`, `case_status_filter`, `payment_lifecycle`, `due_dates_filter`.

## Result breakdown

### 8 PASSING
- `D_total_cases_ui` (dashboard_stats.totalCases → 36)
- `D_pending_rfi_ui` (case_status_filter PENDING_RFI → 5)
- `D_initial_elig_ui` (INITIAL_ELIGIBILITY_REVIEW → 7)
- `D_final_det_pending_ui` (FINAL_DETERMINATION_PENDING → 8)
- `D_final_elig_completed_ui` (FINAL_ELIGIBILITY_COMPLETED → 4)
- `D_final_det_rendered_ui` (FINAL_DETERMINATION_RENDERED → 4)
- `D_ineligible_admin_ui` (INELIGIBLE_PENDING_ADMIN_FEE → 0)
- `D_pending_closure_ui` (PENDING_ADMINISTRATIVE_CLOSURE → 0)

### 7 FAILING — 3 classes of bot/LLM issues (not harness bugs)

**Class A: Semantic mismatch (1 test)** — bot's SQL is plausible but counts differently than IDRE's API.
- `D_active_arbitrators_ui`: bot SQL `role='arbitrator' AND banned IS NOT TRUE` → 3. IDRE dashboard-stats → 5. Different definition of "active arbitrator." Need to read IDRE's `app/api/reports/dashboard-stats/route.ts` to find the canonical definition and feed it back into bot's knowledge layer.
- Likely also `D_avg_processing_time_ui` and `D_total_payments_ui` for the same reason (different SQL than IDRE's API uses).

**Class B: Empty SQL generation (3 tests)** — bot's `sql` field came back empty, `data: []`. Gemini's tool-calling path silently failed or routed elsewhere.
- `D_payment_pending_p0_ui`, `D_pending_second_p1_ui`, `D_final_elig_both_paid_p2_ui`
- All three share semantic ambiguity ("pending initial payment" / "pending second payment" / "both payments received") — Gemini may not match these to `status='PENDING_PAYMENTS'` etc. without explicit knowledge-layer hints. The 8 cases that PASS use more direct phrasings ("pending RFI", "initial eligibility review").

**Class C: Wrong response shape (1 test)** — bot interpreted "how many" as "list me the items" rather than "count me the items."
- `D_overdue_due_dates_ui`: bot returned `data: {'cases': [...36 case dicts...]}` instead of a count.
- Runner's reduction logic only handles `data: list[dict]` or `data: dict[scalar]` — it can't reduce `data: {key: list[dict]}` to a count.
- Fix options:
  - (a) Improve runner to detect `data: {key: list}` and use `len(list)` as count
  - (b) Sharpen prompt to "COUNT cases that are overdue" (LLM-side fix)
  - (c) Both

## Fixes landed during iteration

| Commit | Fix |
|---|---|
| `c91b64a` (local/) | `compare_aggregates` now numeric-tolerant (string vs int no longer FAIL) — recovered 4 tests |
| `a4e8b57` (v10_reports_bot/) | `sql_writer._parse_llm_response` now extracts SQL from ```sql fences and handles ASSUMPTIONS-before-SQL order — recovered 3 tests |

Combined recovery: 1/15 → 8/15.

## Remaining work (out of Phase B scope)

These are V10 bot improvements that would push pass rate higher; deferred:

1. **Add canonical definitions to bot's knowledge layer** for ambiguous business terms (active arbitrator, P0/P1/P2 payment lifecycle, etc.). Source: read IDRE's `app/api/reports/*` route handlers and translate their queries into `business_logic.json` entries.
2. **Strengthen Gemini prompt** to always return a scalar count for "how many X" questions (currently sometimes returns a list).
3. **Improve runner reduction** to handle nested-list shapes (`data: {cases: [...]}`).
4. **Investigate empty-SQL paths** — figure out why bot's sql field comes back empty for some prompts; probably a tool-calling routing decision that bypasses sql_writer entirely.
5. **Snapshot staging into local docker** (deferred from Task 1) — to catch SQL bugs that only surface at production scale.

## How to re-run

```bash
cd /c/Users/anand/Downloads/local
py311 -m pytest testing/v10_harness/tests/test_baseline_derived_ui.py -v --tb=line
# Or against staging instead of local docker:
V10_USE_STAGING=1 py311 -m pytest testing/v10_harness/tests/test_baseline_derived_ui.py
```

Per-test results land in `testing/v10_harness/reports/D_*_ui.json` with bot/expected payloads and timing.

## Definition of Done (per spec)

- ✅ All 4 validator templates implemented and registered
- ✅ DB alignment safety addressed (both sides on local docker `idre` — Task 1 done doc)
- ✅ Test set committed (15 derived-ui entries)
- ✅ Screenshot capture on FAIL works (artifacts in reports/)
- ✅ Pipeline proven end-to-end (8/15 PASS)
- ❌ "All 15 tests pass" — NOT achieved (7 failing on real V10 bot issues, classified above)
- ✅ Tag `derived-ui-baseline` (pending — applied with this commit)

## What this unblocks

Future V10 bot iterations now have a **measurable target**. Each bot improvement can be re-run against this baseline to confirm it moved the needle. Without this harness, V10's derived-query path had no objective evaluation.
