# Phase A — Partial Progress v2 (handoff to next session)

**Date:** 2026-05-17 (afternoon slice)
**Continuation of:** `2026-05-17-day9-status.md`
**Latest commit:** TBD (after this file is committed)
**Branch state:** `Anand0008/IDRE-Reports-Bot` main

## Trajectory of `sql_executes` pass rate

| State | Pass | Note |
|---|---|---|
| Initial (Day 9 end) | 0/17 | All 17 fail validation |
| After validator wrap fix | 0/17 | Real errors exposed, none of them runtime errors |
| After backticked table-casing fix | 1/17 | `recent-activity` |
| After bare-identifier table-casing fix | 1/17 (no change in counts; different errors revealed) | |
| After stricter Gemini prompt + drop exports | **2/13** | `recent-activity`, `auditing/daily-transactions` |

## What got done this slice

1. **Validator wrap (`06_validate_pipeline.py`)**: now strips block comments `/*...*/`, line comments `--...`, and trailing `;`/whitespace before wrapping SQL in the validator subquery.

2. **`scripts/build_knowledge/fix_table_casing.py`** (extended): rewrites BOTH backticked PascalCase model refs AND bare PascalCase refs in `FROM/JOIN/UPDATE/INTO` position. 51 entries in the `model → table_name` map from `schema_catalog.json`.

3. **`05_extract_business_logic.py` SYSTEM_PROMPT rewritten** with hard constraints:
   - One single SELECT only — no `SET @var; SELECT`
   - Use MySQL table names (lowercase from `@@map`), NOT Prisma PascalCase model names
   - No `${var}` template literals, no `:param` placeholders, no `?` placeholders
   - If a table/column can't be confirmed, set `needs_review: true` rather than guess
   - Backtick `case` (reserved word)

4. **Dropped 5 export-infra entries** (`export`, `exports`, `exports/[exportId]`, `exports/[exportId]/download`, `exports/[exportId]/retry`) — these are export-management endpoints, not reports.

5. **Re-prompted Gemini** for the 12 failing reports with the stricter system prompt. All re-converted. Validation now shows 2 OK + 11 with REAL errors (no more cosmetic issues).

## What's actually broken in the remaining 11

All failures are now one of two classes — both fixable mechanically:

### Class 1: Wrong table names (5 reports)

Gemini invented tables that don't exist in `schema_catalog.json`. The real Prisma model uses a different name (often with a `case_` prefix or plural).

| Hallucinated name | Real name | Reports affected |
|---|---|---|
| `party` | `case_party` (model `CaseParty`) | `due-dates`, `auditing/daily-funds` |
| `dispute_line_item` | `dispute_line_items` (plural) | `idre-payouts`, `outstanding-payments` |
| `installment` | doesn't exist on staging — feature removed? | `due-dates/summary` |

### Class 2: Wrong column casing (6 reports)

**Critical finding:** Prisma column names are camelCase in MySQL too, not snake_case. Gemini's intuition was wrong. Examples of generated-wrong → actual:
- `dispute_reference_number` → `disputeReferenceNumber`
- `created_at` → `createdAt`
- `report_type` → `reportType`
- `type_of_dispute` → `typeOfDispute`
- `closedAt` → not in schema (may be `statusChangedAt` or similar)

This is a UNIVERSAL issue — every Gemini-generated SQL likely has at least one snake_case column ref that needs flipping.

## Verbatim prompt for next session

> Continuing V10 reports bot Phase A. We're at 2/13 sql_executes OK.
> Read `docs/superpowers/reports/2026-05-17-phase-a-partial.md` first.
>
> Concrete next steps (each ~15-30 min):
>
> **Step A1 — Extend `fix_table_casing.py` with an explicit alias map** for hallucinated tables:
> ```python
> TABLE_ALIASES = {
>     "party": "case_party",
>     "dispute_line_item": "dispute_line_items",
>     # add more as discovered
> }
> ```
> Apply in FROM/JOIN/INTO/UPDATE position only, with word-boundary regex. Re-validate.
>
> **Step A2 — Build a `fix_column_casing.py` script** that reads `schema_catalog.json`, builds a `snake_case_name → camelCaseName` map from every model's columns, and rewrites references in `<alias>.<column>` form in every `business_logic.json` `sql_equivalent`. Test by validating against staging.
>
> **Step A3 — For `due-dates/summary`** (`installment` table): inspect `app/api/reports/due-dates/summary/route.ts` on staging. If the feature was removed, drop the entry from `business_logic.json`. If renamed, update.
>
> **Step A4 — Validate**, target 13/13 OK (or `needs_review:true` with clear notes for any genuinely-untranslatable). Tag `knowledge-validated` on GitHub. Promote `v10_pending → v10` atomically (`scripts/build_knowledge/run_all.py` does this when validation passes, or do it manually with `mv`).
>
> **Then Phase B**: Day 10 derived-query test set (see `2026-05-15-v10-reports-bot-plan.md` Day 10).

## Known-report path is UNAFFECTED

15/15 byte-equal PASS still holds. `day9-complete` tag still valid. This whole investigation is about the *derived-query* path's knowledge layer, which fires only when the LLM falls through to SQL generation.

## Files changed this slice

- `scripts/build_knowledge/06_validate_pipeline.py` (wrap fix + import re)
- `scripts/build_knowledge/05_extract_business_logic.py` (stricter system prompt)
- `scripts/build_knowledge/fix_table_casing.py` (added bare-identifier rewrite in FROM/JOIN/UPDATE/INTO position)
- `v10_reports_bot/knowledge/v10_pending/business_logic.json` (12 reports re-generated under stricter prompt; 5 export entries dropped)
- `v10_reports_bot/knowledge/v10_pending/manifest.json` (validation: 2/13 OK)

## Session end notes

- IDRE local server: still running on `127.0.0.1:3000`. Don't kill until next session.
- Docker `idre-mysql`: still running.
- Working tree of IDRE clone: on `main` + dev tweaks intact (auto-login route preserved).
- V10 bot working tree (`v10_reports_bot/`): unchanged source; only `knowledge/v10_pending/` artifacts modified.
- Push credentials: PAT for `Anand0008/IDRE-Reports-Bot` was passed via shell history — rotate when convenient.
