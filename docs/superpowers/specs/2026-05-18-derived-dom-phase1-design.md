# V10 Derived-DOM Validation — Phase 1 Design (~30 tests)

**Date:** 2026-05-18
**Status:** Approved for implementation planning
**Author:** Anand Wankhade with Claude
**Builds on:**
- `2026-05-17-ui-validation-design.md` (original UI validation spec)
- `2026-05-18-task20-snapshot-done.md` (production-shaped local docker)
- `derived-ui-baseline-snapshot` tag (existing 15/15 baseline)

## 1. Context and Motivation

The existing `derived-ui-baseline-snapshot` suite (15 tests, 100% PASS against staging snapshot in local docker) validates V10's derived path but uses a mix of validation sources: 4 tests hit IDRE's `/api/reports/dashboard-stats` directly, 1 hits `/api/reports/due-dates/summary`, and 10 use a SQL fallback against local docker. None scrape IDRE's actual rendered UI at production scale.

For the derived path specifically, we want validation that mirrors what a human user would see in IDRE's interface — not an API the user never touches. This Phase 1 spec adds a parallel test suite targeting ~30 tests sourced from the metrics that matter most for status reporting: Ashlee Bell's daily status emails and Anand's status-summary screenshot.

Existing 15 tests stay unchanged (regression-locked under their tag). New suite is additive.

## 2. Success Bar

**Phase 1 target: 25/30 PASS (~83%) on first full run, 30/30 within one iteration cycle.**

Each test passes iff:
- **For `count` tests:** bot's reduced count equals the number IDRE's UI displays on the relevant filtered page, within tolerance 0.01.
- **For `rows` tests:** bot returns >=5 rows containing the requested unique identifier (case id or disputeReferenceNumber), and the first sampled identifier is found on IDRE's case-detail page with the expected attribute (status, urgency, etc.) matching what bot claimed.

Both bot and validator read the same DB (local docker `idre` with staging snapshot). Mismatches are real semantic gaps, not data drift.

## 3. Architecture

### 3.1 Two parallel test suites

| Suite | File | Validators | Status |
|---|---|---|---|
| Legacy (15 tests) | `tests/test_baseline_derived_ui.py` | dashboard_stats, case_status_filter, payment_lifecycle, due_dates_filter | Unchanged. Locked under tag `derived-ui-baseline-snapshot`. |
| New Phase 1 (~30 tests) | `tests/test_baseline_derived_dom.py` | dom_scrape, dom_lookup, canonical_sql | This spec. |

### 3.2 Three new validators

**`dom_scrape`** — count-type. Navigates IDRE URL, waits for content, reads a number via selector or regex.

```python
class DomScrapeValidator:
    name = "dom_scrape"
    def extract(self, page, params):
        page.goto(params["url"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_function(
            f"() => /{params['wait_for_regex']}/.test(document.body.innerText)",
            timeout=60000,
        )
        body = page.evaluate("() => document.body.innerText")
        ext = params["extract"]
        if ext["kind"] == "regex_capture":
            m = re.search(ext["pattern"], body)
            if not m:
                raise RuntimeError(f"pattern not found in body: {ext['pattern']}")
            return {ext.get("key", "count"): parse_number(m.group(1))}
        if ext["kind"] == "selector_text":
            txt = page.locator(ext["selector"]).inner_text(timeout=10000)
            return {ext.get("key", "count"): parse_number(txt)}
        raise ValueError(f"unknown extract kind: {ext['kind']}")
```

**`dom_lookup`** — rows-type. Run by runner (not the validator interface) because it needs bot's output. Picks `sample_count` rows from bot's response, navigates IDRE's case-detail page for each sampled ID, asserts an expected text pattern appears (e.g., the expected status). All sampled rows must match for PASS.

**`canonical_sql`** — count-type, fallback for metrics IDRE has no URL-filter combo for. Executes hand-authored SQL on local docker `idre`. Each entry must include `source_ref` justifying why no UI exists and (where possible) which IDRE source file informed the SQL.

### 3.3 Test record schema extensions

`TestRecord` gains:
- `result_type: "count" | "rows"` (default `"count"`)
- `validator_params` extended with `dom_scrape`/`dom_lookup`/`canonical_sql` shapes per validator (existing union pattern)

`category` for new suite: `"derived-dom"` (distinct from existing `"derived-ui"`).

### 3.4 Performance prerequisites

DOM scrape at 67K-row scale requires IDRE pages to render in <30s. Two changes:

1. **MySQL covering indexes on local docker `idre`** (added once, persist with container):
   - `case (status)`, `case (statusChangedAt)`, `case (createdAt)`, `case (due_date)`, `case (eligibilityDueDate)`, `case (paymentDueDate)`
   - `payment (status, type)`, `payment (amount)`
   - Whatever else profiling shows IDRE needs

2. **IDRE in production build mode** instead of `next dev`:
   - `cd local/idre && npx next build && npx next start`
   - 5-10x faster server-render than dev mode
   - Trade-off: no hot-reload for IDRE source edits; manual rebuild on changes

If after both changes a page still takes >30s, that metric is flagged "DOM-impractical" and moves to `canonical_sql`.

## 4. Components

### 4.1 New files

```
testing/v10_harness/
  ui_validators/
    dom_scrape.py          # NEW
    dom_lookup.py          # NEW (peer of validators, but runner-driven)
    canonical_sql.py       # NEW
  tests/
    test_baseline_derived_dom.py  # NEW (parallel to existing)
  preflight.py             # NEW (pre-flight checklist module)
.snapshots/
  add_indexes.sql          # NEW (idempotent CREATE INDEX statements)
  apply_indexes.py         # NEW (run add_indexes.sql against local docker idre)
docs/superpowers/specs/
  2026-05-18-derived-dom-phase1-design.md  # THIS FILE
docs/idre-local-prod-mode.md   # NEW (how to run IDRE in prod build)
```

### 4.2 Modified files

```
testing/v10_harness/runner.py        # add result_type handling + dom_lookup integration
testing/v10_harness/ui_validators/__init__.py  # register 3 new validators
testing/v10_harness/conftest.py      # preflight fixture (autouse for derived-dom tests)
testing/v10_harness/test_set.jsonl   # append ~30 derived-dom entries
```

### 4.3 IDRE-side changes (local working tree only, NOT pushed to main)

```
local/idre/                       # run `next build` produces .next/ output
                                  # documented; not committed
```

No IDRE source code edits required for Phase 1.

## 5. Data Flow Per Test

### count-type
1. Pre-flight (once per session): asserts IDRE prod mode + DB snapshot + indexes + 2FA cleared
2. Bot runs prompt via `run_query_v10` -> returns dict with `data`, `sql`, etc.
3. Runner reduces bot response to `{key: number}` per `bot_must_return_keys`
4. `dom_scrape` validator (or `canonical_sql` for no-UI metrics) extracts the IDRE-side count
5. `compare_aggregates` checks numeric equality (tolerance 0.01)
6. Result + screenshot (on FAIL) written to `reports/{id}.json`

### rows-type
1. Pre-flight
2. Bot runs prompt -> returns `data: [row, row, ...]`
3. Runner pulls `sample_count` rows from bot's data using `id_column`
4. For each sampled ID:
   - Navigate `lookup_url_template.format(id=...)` (typically `/dashboard/cases?search={id}` or `/dashboard/cases/{id}`)
   - Wait for page to load
   - Search page body for `expected_text_pattern`
5. PASS iff all sampled rows verified; FAIL otherwise (with which sample failed in the diff)

## 6. Test Sourcing (Phase 1, ~30 entries)

### Source A: Ashlee's daily status emails (~15 prompts)
Source: V8 history's 7 archived .eml files (path to confirm during implementation). Each email reports:
- Total disputes today (count-type)
- New disputes today (count-type)
- Disputes by status (count-type per status)
- Cases in initial eligibility (count-type)
- Cases pending RFI (count-type)
- Cases pending payment (count-type)
- Cases pending second payment (count-type)
- Cases in final eligibility (count-type)
- Final determinations rendered today/MTD (count-type, may be no-UI -> canonical_sql)
- Defaults rendered today/MTD (count-type, likely no-UI -> canonical_sql)
- Recent disputes (rows-type, "show me X")

### Source B: Anand's status-summary screenshot (~10 prompts)
Items from the screenshot; specific entries derived during implementation from the actual screenshot content.

### Source C: IDRE_Report_Audit_Findings.md (~5 prompts)
Hand-verified canonical SQL from `C:\Users\anand\Downloads\final idre reports bot\IDRE_Report_Audit_Findings.md`. Used for spot-check on hardest cases (joins, multi-status filters, payment-status combos).

### Authoring rule
- Phrase each prompt as a real user would speak to V10 (not SQL-shaped). Examples in this spec's earlier sections.
- Classify count vs rows based on natural phrasing ("how many" -> count, "show me X" / "give me latest X" -> rows).
- For each, identify whether IDRE has a URL+filter combo a real human user could actually navigate to that produces the requested view. The URL must be reachable through normal IDRE navigation (links/filters in the existing UI), not a synthesized URL nobody would discover. If no such URL combo exists -> `canonical_sql` with `source_ref`.

## 7. Pre-flight Checklist

Implemented as `testing/v10_harness/preflight.py`, invoked via autouse session fixture for the new suite.

| Check | Pass criterion | Failure action |
|---|---|---|
| IDRE running | HTTP 200 on `http://127.0.0.1:3000` within 5s | Skip all derived-dom tests with explanatory message |
| IDRE in prod mode | Response header check (Next.js prod vs dev differs); fallback: time a known page render and assert <2s | Print warning; allow tests but expect slower runs / higher fail rate |
| DB snapshot loaded | `SELECT COUNT(*) FROM case > 10000` | Skip all derived-dom tests; instruct user to re-import snapshot |
| Indexes present | `SHOW INDEX FROM case WHERE Column_name='status'` returns >=1 | Auto-apply `apply_indexes.py` (idempotent) |
| Ryan auth working | `GET /api/dev/auto-login` returns `set-cookie: better-auth.session_token=...` | Skip all derived-dom tests; instruct user to reset password / clear twoFactor |
| Env vars | `V10_AMBIGUITY_THRESHOLD=1.0` set, DB_* overrides set | Auto-set defaults |

Pre-flight failure prints exactly which check failed and the remediation command. No mystery aborts.

## 8. Validation Rigor Summary

- **count-type tests:** bot's count must match IDRE's displayed count. Cheap, scales. Catches off-by-N, wrong table, wrong WHERE.
- **rows-type tests:** bot returns >=5 rows; runner verifies 1 sampled row exists in IDRE with expected attributes. Catches wrong-filter-but-coincidentally-same-count bugs that pure counts miss. ~5s extra per rows-test (one navigation).

Per user direction (2026-05-18 brainstorm): for rows-type, sampling 1 row from bot's output and verifying it in IDRE is "fine and doable" -- not exhaustive cross-check but sufficient given combinatoric improbability of wrong-filter producing valid-looking sampled rows.

## 9. Out of Scope (Phase 1)

- Phase 2 (scale to ~80 deterministic tests) -- separate spec
- Phase 3 (~70 Tier 2 NL stretch tests) -- separate spec
- Replacing the existing 15-test suite -- stays unchanged
- Time-window filters (createdAfter/createdBefore) in IDRE -- if Phase 1 needs them, use canonical_sql; future IDRE work could add URL filters
- CI integration -- runs locally on demand
- Test refresh automation -- snapshot refresh procedure documented but manual

## 10. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Prod build of IDRE introduces issues not present in dev | Document explicit `next build` then `next start` command; pre-flight check times a page render; tester can revert to `next dev` for IDRE source debugging |
| Indexes change query plans in ways that surface different bugs | Indexes are speed-only; results should be identical. Spot-check first 5 tests with and without indexes to confirm. |
| Gemini stochasticity causes test flakiness | Tier 1 prompts deliberately phrased to minimize alternate SQL interpretations (e.g., explicit status enum naming). Re-run flaky tests once before marking FAIL. |
| Some metrics have no URL combo to view (time-window filters etc.) | `canonical_sql` fallback. Each such entry documented with `source_ref` justifying why no UI exists. |
| User auth blockers reappear after snapshot refresh | Pre-flight check catches it; `reset_ryan_password.py` and twoFactor clear script remain runnable. |
| Bot router shortcuts "how many overdue" to known-path | Already known issue. Phrase such prompts to bias toward derived (e.g., "show me overdue cases" -> rows-type) or use canonical_sql. |
| 30 tests x 30-60s = 15-30 min per run, slow for iteration | Per-test JSON saved for debug without re-running. Cherry-pick failing tests with `-k` pattern. |

## 11. Definition of Done (Phase 1)

- New suite file `test_baseline_derived_dom.py` exists and runs
- 3 new validators implemented and registered: `dom_scrape`, `dom_lookup`, `canonical_sql`
- `preflight.py` module gates the suite
- `apply_indexes.py` script idempotent; documented
- `docs/idre-local-prod-mode.md` explains the `next build && next start` workflow
- ~30 derived-dom entries in `test_set.jsonl` covering Ashlee emails + screenshot + audit-findings sample
- Initial baseline run: 25/30 PASS minimum
- After one iteration: 30/30 PASS
- Tag `derived-dom-baseline-phase1` applied to the green commit
- Failures (if any persist) classified as: real bot bug / NL ambiguity / IDRE UI race / known limitation

## 12. Future Phases (referenced, not designed here)

- **Phase 2:** Expand to ~80 Tier 1 deterministic tests. Spec when Phase 1 lands.
- **Phase 3:** Add ~70 Tier 2 NL stretch tests with relaxed pass-rate goals. Surfaces real-world NL gaps.
- **Phase 4 (maybe):** Wire baseline runs into CI on bot changes (auto-snapshot refresh + run on push).
