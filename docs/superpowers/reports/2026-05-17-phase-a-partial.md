# Phase A — Partial Progress v3 (handoff to next session)

**Date:** 2026-05-17 (final slice)
**Continuation of:** `2026-05-17-day9-status.md` (Phase A in that doc's plan)
**Branch state:** `Anand0008/IDRE-Reports-Bot` main

## Trajectory of `sql_executes` pass rate

| State | Pass | Note |
|---|---|---|
| Day 9 end | 0/17 | All fail validation |
| Validator wrap fix | 0/17 | Real errors exposed |
| Backticked table-casing | 1/17 (later 1/13 after dropping exports) | `recent-activity` |
| Bare-identifier table-casing | 1/13 | uncovered new errors but same pass count |
| Stricter Gemini prompt + drop exports | **2/13** | + `auditing/daily-transactions` |
| Hand-curated table aliases | **3/13** | + `due-dates` |
| Snake→camel column rewrite | **4/13** | + `unpaid-disputes`, `cms-payments`; but `due-dates` regressed |

Net delta this session: **0/17 → 4/13 valid SQL** (+ 5 export-infra entries correctly dropped). Real but partial.

## The remaining 9 failures

After the snake→camel column fix, residual errors:

| Report | Error | Cause |
|---|---|---|
| `due-dates` | `Unknown column 'c.dueDate'` | **Regression from my fix.** Schema column IS `due_date` (snake_case). My rule wrongly camelCased it. Need per-column-name check against schema, not blind regex. |
| `dashboard-stats` | `Unknown column 'closedAt'` | Column doesn't exist (schema has `statusChangedAt`). My EXTRA mapping `closed_at→statusChangedAt` only fires for snake_case input; here Gemini wrote camelCase `closedAt` directly. |
| `due-dates/summary` | Table `installment` doesn't exist | Gemini hallucination. Likely a feature that exists only in a newer staging revision, or Gemini guessed wrong. **Hand-fix or drop.** |
| `auditing/daily-funds` | Table `nachaBatch` doesn't exist | Schema has `nacha_batch`. The bare-identifier fix only triggers in `FROM/JOIN/UPDATE/INTO` position — this reference is elsewhere (CTE or subquery). Widen the rewrite scope. |
| `exports`, `exports/[exportId]`, `exports/[exportId]/download` | Various `file_url`, `filePath`, etc. | Schema doesn't have `file_url` or `filePath`. **These 3 should be DROPPED — they're export-infra, not reports.** v2 of fix_table_casing.py needs the drop logic too (it ran AFTER the drop step). |
| `idre-payouts`, `outstanding-payments` | Table `DisputeLineItems` (plural Pascal) doesn't exist | `HAND_ALIASES` has `DisputeLineItem` (singular). Gemini emitted plural Pascal. Add `"DisputeLineItems": "dispute_line_items"` to aliases. |

## Key insights for next session

1. **Schema-aware column rewriter:** instead of blind `snake_to_camel`, look up each column reference in the schema_catalog for the table that owns that alias. The schema has the ground-truth case. Build a `(table, snake_form) → real_case` map.

2. **Drop step needs to be re-run** after each Gemini re-prompt. Otherwise exports/* re-appear.

3. **Some columns genuinely ARE snake_case** (`due_date`, `due_date_until_decision`). Don't assume Prisma columns are uniformly camelCase. Check schema_catalog per column.

4. **`installment` table** truly doesn't exist on this staging revision. Either staging dropped the table, or Gemini hallucinated. Need a human to look at `app/api/reports/due-dates/summary/route.ts` and decide.

## Verbatim next-session prompt

> Continuing V10 reports bot Phase A. At 4/13 sql_executes OK. Read `docs/superpowers/reports/2026-05-17-phase-a-partial.md` first.
>
> Step A4 — Rewrite `fix_column_casing.py` to be schema-aware:
>   - Parse SQL to find `<alias>.<col>` references.
>   - For each `<alias>`, find its table (from `FROM <table> AS <alias>` or `FROM <table> <alias>`).
>   - Look up `<col>` in `schema_catalog.json[models][<table>][columns]`.
>   - If a column matching `<col>` exists with different case (snake vs camel), replace with the actual schema name.
>   - NEVER guess; only replace when schema confirms.
>
> Step A5 — Add `"DisputeLineItems": "dispute_line_items"` and any other plural Pascal forms to HAND_ALIASES.
>
> Step A6 — Re-run the export-drop step (the 3-line filter in business_logic.json) BEFORE validating.
>
> Step A7 — Hand-investigate `due-dates/summary` (`installment` table). Read the actual route.ts; either fix or mark `needs_review:true` with explanation.
>
> Step A8 — Hand-fix `dashboard-stats` (`closedAt` doesn't exist; choose `statusChangedAt` or remove the column from the SELECT).
>
> Target: 9/9 actually-derivable OK + 4 explicitly `needs_review` (`due-dates/summary` installment + the 3 export-infra that should never have been generated). Tag `knowledge-validated`. Promote `v10_pending → v10`.
>
> Then Phase B: Day 10 derived-query test set per `2026-05-15-v10-reports-bot-plan.md`.

## What's safe (known-report path)

15/15 PASS still holds. Tag `day9-complete` is the ground truth for what's shipped. The knowledge-layer SQL problems above only affect the derived-query path — which still works (V8 pipeline produces SQL from schema/glossary tools even when `get_idre_business_logic` returns broken text).

## Files changed across all 3 Phase A slices

- `scripts/build_knowledge/06_validate_pipeline.py` — wrap fix + strip `;`, `--`, `/*...*/`
- `scripts/build_knowledge/05_extract_business_logic.py` — stricter SYSTEM_PROMPT (one SELECT, no SET, MySQL table names, no template literals)
- `scripts/build_knowledge/fix_table_casing.py` — model→table map + bare-id rewrite in FROM/JOIN/UPDATE/INTO + 6 hand aliases
- `scripts/build_knowledge/fix_column_casing.py` (new) — snake→camel column rewrite (overaggressive, needs schema-aware version)
- `v10_reports_bot/knowledge/v10_pending/business_logic.json` — 12 reports re-generated; 5 export entries dropped; 12 table-casing rewrites; 8 column-casing rewrites
- `v10_reports_bot/knowledge/v10_pending/manifest.json` — validation 4/13 OK

## Cost note

This session made 12 Gemini 2.5 Pro calls for re-conversion (~30s each, ~6 min total wall, ~$1-2 inference). Next session's Step A4 should NOT need any Gemini calls — it's all mechanical fixes on existing `business_logic.json`. The hand-investigation in A7/A8 may need ~10 min of human SQL reading.

## Session end state

- IDRE local server: assumed running on 127.0.0.1:3000 (didn't kill it).
- Docker `idre-mysql`: assumed running.
- IDRE clone working tree: on `main` + dev tweaks (auto-login route preserved).
- V10 bot working tree: unchanged source; `knowledge/v10_pending/` has the latest 4/13 state.
