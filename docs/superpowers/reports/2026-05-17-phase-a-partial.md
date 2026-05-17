# Phase A — Partial Progress (handoff to next session)

**Date:** 2026-05-17
**Continuation of:** `2026-05-17-day9-status.md` (Phase A in that doc's plan)
**Branch state:** committed to `main` on `Anand0008/IDRE-Reports-Bot`

## What got done this slice

1. **Fixed the validator wrap bug** in `scripts/build_knowledge/06_validate_pipeline.py`:
   - Strips `/* ... */` block comments, `-- line` comments, and trailing `;`/whitespace before wrapping SQL in `SELECT * FROM (<sql>) AS _v LIMIT 1`.
   - Re-running validation exposed the *real* errors (previously hidden by wrap failures).

2. **Created `scripts/build_knowledge/fix_table_casing.py`** — a one-shot script that reads `schema_catalog.json`, builds a `PascalCaseModel → mysql_table_name` map (51 entries), and rewrites *backticked* references in every `business_logic.json` `sql_equivalent`. Updated 15 reports.

## Current state of `business_logic.json` (after both fixes)

**1 of 17 reports executes** against staging RDS: `recent-activity`. The other 16 fail.

## Remaining failure breakdown

| Failure pattern | Reports | Fix |
|---|---|---|
| Bare (non-backticked) PascalCase identifier | `idre-payouts` (`Payment`), `dashboard-stats` (`Payment`), `due-dates` (`Party`), `unpaid-disputes` (`PaymentAllocation`) | Extend `fix_table_casing.py` to handle bare identifiers — but **carefully**: it must NOT rewrite column names that happen to share the PascalCase. Use word-boundary regex matched against tokens that appear in FROM/JOIN/UPDATE position only. ~30 min careful work. |
| Multi-statement `SET @var; SELECT ...` | `team-performance`, `case-analytics`, `cms-payments` | Re-prompt Gemini with stricter `05_extract_business_logic.py` SYSTEM_PROMPT: "ONE SELECT only. NO SET @var. NO `${var}` template-literal placeholders. NO `?` placeholders. If you cannot translate a helper function, set `needs_review: true` and explain." Run with `--only <id>` for each. |
| Schema reference doesn't exist on staging | `due-dates/summary` (`form_response`), `exports` (`mfe.fileUrl` column), `exports/[exportId]*` (`:exportId` SQLAlchemy bind param) | Hand-investigate: `due-dates/summary` and `exports/*` may be NEW staging routes that reference tables/columns this script's schema catalog didn't pick up (or that don't exist yet on staging RDS). Either fix manually or mark `needs_review: true`. |
| Generic 1064 syntax (unclassified) | `auditing/daily-transactions`, `case-balance`, `outstanding-payments`, `auditing/daily-funds`, `exports/[exportId]/retry` | Read each SQL, identify root cause. Likely a mix of JSON-function misuse and unmatched parens. |

## Verbatim next-session prompt

> Continuing V10 reports bot Phase A. Last session got 1/17 executing.
> Read `docs/superpowers/reports/2026-05-17-phase-a-partial.md` first, then:
>
> 1. Extend `scripts/build_knowledge/fix_table_casing.py` to safely rewrite bare PascalCase identifiers in FROM/JOIN clauses only. Test by running it then `06_validate_pipeline.py --execute-sql`. Should recover ~4 reports.
> 2. Update `05_extract_business_logic.py` SYSTEM_PROMPT with the stricter constraints above; re-prompt the 3 multi-statement reports with `--only`.
> 3. Hand-fix the remaining failures by reading the actual `route.ts` side-by-side with the generated SQL.
> 4. Target: 17/17 OK. Tag `knowledge-validated` on GitHub when done. Promote `v10_pending` → `v10` atomically.
>
> Then Phase B: Day 10 derived-query test set (see `2026-05-15-v10-reports-bot-plan.md` Day 10).

## Files changed in this slice

- `scripts/build_knowledge/06_validate_pipeline.py` (validator wrap fix)
- `scripts/build_knowledge/fix_table_casing.py` (new — backticked-only)
- `v10_reports_bot/knowledge/v10_pending/business_logic.json` (15 entries rewritten)
- `v10_reports_bot/knowledge/v10_pending/manifest.json` (new validation result: 1/17 OK)

## What is NOT broken

The 15/15 known-report baseline still holds — known path doesn't depend on `business_logic.json`. Day 9 `day9-complete` tag is still valid.
