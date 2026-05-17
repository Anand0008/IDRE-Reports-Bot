# Phase A — Strategic Pivot (final handoff)

**Date:** 2026-05-17 (end of session)
**Continuation of:** `2026-05-17-day9-status.md`
**Branch state:** `Anand0008/IDRE-Reports-Bot` main

## TL;DR — the strategic reframe

After multiple iterations on `business_logic.json`, two things became clear:

1. **The 15/15 known-report PASS doesn't depend on `business_logic.json` at all.** Known path calls IDRE's `/api/reports/*` directly. The `sql_equivalent` field is reference material for the LLM's *derived-query* path only.

2. **We don't have derived-query tests yet.** So optimizing `business_logic.json` is optimizing an input to an untested output. Wrong order.

The right move is to skip further `business_logic.json` polish and use `final idre reports bot/IDRE_Report_Audit_Findings.md` (a March 2026 audit doc) as the source of truth for Day 10's derived-query tests. It has hand-verified SQL for the exact prompts in Ashlee's status-summary emails + the user's screenshot (total disputes, MTD, new-today, P=0/P=1/P=2 payment lifecycle, final eligibility breakdowns).

## Knowledge-layer progress this session (informational)

Even though it's now lower priority, this session moved `business_logic.json` forward:

| State | sql_executes OK |
|---|---|
| Day 9 end | 0/17 |
| After validator wrap fix | 0/17 (real errors exposed) |
| After table-casing + stricter Gemini prompt | 2/13 |
| After hand-curated table aliases (`party→case_party`, etc.) | 3/13 |
| After snake→camel column rewrite | 4/13 |
| After importing V8 hand-written `bot_sql_equivalent` | **7/16** (case-balance, cms-payments, due-dates, outstanding-payments, recent-activity, team-performance, unpaid-disputes) |

The 9 remaining failures: 1064 syntax errors in V8's hand-written multi-statement queries (auditing/daily-funds, auditing/daily-transactions, case-analytics, dashboard-stats, idre-payouts) + the export/installment hallucinations. These can wait.

## Strategically more valuable: use `IDRE_Report_Audit_Findings.md`

**Path:** `C:\Users\anand\Downloads\final idre reports bot\IDRE_Report_Audit_Findings.md`

This document was created 2026-03-24, comparing canonical (verified) SQL against Gemini's generation, against the live staging DB. Verified SQL for at least the following derived queries (each with NL prompt + verified SQL):

- Report 1: total disputes; 1a: MTD; 1b: new-today
- Report 2: initial eligibility review
- Report 3: pending RFI status
- Report 4: payment pending P=0; 4a: pending second P=1
- Report 5: final eligibility process; 5a: review with both paid P=2; 5b: completed
- (and more — index continues past line 287 of the file)

These EXACTLY map to:
- The user's status-summary screenshot's 7 numbered items + sub-items
- Ashlee Bell's status-update .eml emails (V1 history archives 7 of them)

## Verbatim next-session prompt

> Continuing V10 reports bot. Known-report path is 15/15 PASS (`day9-complete` tag). Now starting Phase B (Day 10 derived-query tests). Skip further knowledge-layer polish.
>
> Read `docs/superpowers/reports/2026-05-17-phase-a-partial.md` first.
>
> **Step B1** — Read `C:\Users\anand\Downloads\final idre reports bot\IDRE_Report_Audit_Findings.md` end-to-end. It has hand-verified SQL for ~15-20 derived queries matching Ashlee's status emails + user's screenshot.
>
> **Step B2** — Build `testing/v10_harness/test_set.jsonl` derived entries (`D_*` ids) from each verified report:
> - `prompt` = the NL Query string from the audit doc
> - `ground_truth_sql` = `[{name: "v", sql: <verified SQL with :now param>}]`
> - `bot_must_return_keys` = `["v"]`
> - `temporality` = "stable" if no date in SQL, "variant" if `:now` is used
>
> Target ~20-25 derived tests.
>
> **Step B3** — Run derived baseline: `BOT=v10 pytest testing/v10_harness/tests/test_baseline_derived.py -v`. The bot uses `core/orchestrator.run_query` (V8 pipeline + V10 sql_writer + 8 tools) to generate SQL. Compare bot's count to ground-truth count.
>
> **Step B4** — Surface real derived-path pass rate. THIS is the number that tells us if Day 7-8 SQL writer rewrite + the knowledge layer (broken as it is) are actually delivering. If pass rate is poor, revisit knowledge layer with measurements driving the priorities.
>
> Then Day 6 (expand known-report test set) and Phase C (production readiness) per plan.

## Older bot folders — what's where

User pointed at these multiple times:

| Path | What it is | Useful for now? |
|---|---|---|
| `Downloads\update4_reports_bot\` | V3/V4 (March 2026) — platform context + post-processor era. 13 agents. Has `knowledge/data/` with file_summaries, repo_map, module_keywords. | Not directly. Old retrieval inputs we don't need (V10 has no RAG). |
| `Downloads\update5_reports_bot_update.zip` | V5+ deploy update bundle. | Probably has older `schema_catalog.json`, glossary updates. Skip. |
| `Downloads\final idre reports bot\` | V5+ at the consolidated path. **HAS THE AUDIT FINDINGS DOC.** | **YES — for Phase B (Day 10 test set).** |
| `Downloads\update4_reports_bot_update.zip` | Older V3/V4 update bundle. | Skip. |
| `Downloads\v6_reports_bot\` | V6 — has `sql_templates.json` (10 templates) + `business_rules.json` (pricing eras). | Marginally useful — sql_templates may have a few more verified examples. Skip for now. |
| `Downloads\v8_reports_bot\` | V8 — already used (its `report_reference_cards.json` was just imported into V10's `business_logic.json`). | Done — net +3 sql_executes from that import. |

## Known-report path is STILL the deliverable

`day9-complete` tag = 15/15 byte-equal PASS, 12 IDRE reports, ~3:24 runtime. Everything in this doc is about the DERIVED-QUERY path which is a fallback. The known path is what makes V10 ship-able.

## Files changed this session

- `scripts/build_knowledge/06_validate_pipeline.py` (validator wrap fix)
- `scripts/build_knowledge/05_extract_business_logic.py` (stricter system prompt; max_output_tokens=32000)
- `scripts/build_knowledge/fix_table_casing.py` (model→table map + bare-id rewrite in FROM/JOIN + hand aliases)
- `scripts/build_knowledge/fix_column_casing.py` (snake→camel column rewrite — needs schema-aware v2 next session)
- `scripts/build_knowledge/import_v8_sql.py` (imports V8 hand-written SQL — got us to 7/16)
- `v10_reports_bot/knowledge/v10_pending/business_logic.json` (4 mechanical passes + V8 import)
- `v10_reports_bot/knowledge/v10_pending/manifest.json` (latest: 7/16)
- `docs/superpowers/reports/2026-05-17-phase-a-partial.md` (this file, evolved across 3 versions)

## Session-end environment state

- IDRE local server: running on 127.0.0.1:3000.
- Docker `idre-mysql`: running.
- IDRE clone working tree: on `main` + dev tweaks (auto-login route preserved).
- V10 bot working tree: source unchanged; only `knowledge/v10_pending/` artifacts modified (`v10/` was promoted earlier; still has earlier 1/17 state — `v10_pending` has the 7/16 state).
