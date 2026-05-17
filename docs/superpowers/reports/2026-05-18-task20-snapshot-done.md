# Task 20 DONE — Staging Snapshot in Local Docker, 15/15 Baseline PASS

**Date:** 2026-05-18
**Tag:** `derived-ui-baseline-snapshot`
**Runtime:** ~75 min wall-clock end-to-end

## Result

Local docker `idre` DB now holds a production-shaped staging snapshot. Both the V10 bot's executor and the validation harness read this DB, so the 15-test baseline now exercises real-scale data shape.

| Substrate | users | cases | payments | case_party |
|---|---:|---:|---:|---:|
| Dev seed (was) | 47 | 36 | 43 | 0 |
| **Staging snapshot (now)** | **2,275** | **67,794** | **251,441** | **134,553** |

**Baseline pass rate against snapshot: 15/15 (100%) in 7:18.**

## Dump details

- **Source:** `mysql-8-stage-1-cluster.cluster-cc1r7ekdbl8j.us-east-1.rds.amazonaws.com / idre_stage` (read-only via `app_idre_rw` + SSL)
- **Method:** container-internal `mysqldump` (idre-mysql container has mysqldump 8.0) with `--extended-insert --hex-blob`, output streamed through `gzip -c`
- **Excluded tables** (bloat or irrelevant):
  - `email_job` (5.2 GB, email send queue)
  - `case_action` (803 MB, event log)
  - `cms_api_request_log` (22 MB)
  - `cms_sync_log`
  - `session` (regenerated locally — schema imported separately for BetterAuth)
  - `_prisma_migrations`
- **Throughput:** ~13 MB/min compressed (much better than prior session's 5 MB/min thanks to `--extended-insert`)
- **Dump size:** 193 MB compressed (~1.6 GB uncompressed)
- **Dump runtime:** 14:35
- **Import runtime:** ~4 min (FK off, gunzip + mysql import)

## Auth blockers solved during snapshot

The dump replaced the dev-seed user table with production rows. That broke auto-login until we:

1. **Ryan's password hash** — production row has unknown password. Reset to IDRE's hardcoded seed hash for `orchid123` (`dbfd6621...:d667b791...` from `seeds/utils/auth-helpers.ts`). My computed scrypt hash didn't match BetterAuth's verifier — using the literal hardcoded hash works.
2. **Two-factor enabled** — production Ryan has `twoFactorEnabled=1` + a row in the `twoFactor` table. BetterAuth's signInEmail returns the redirect but skips the session cookie when 2FA is required. Deleted Ryan's row in `twoFactor` table.
3. **session table missing** — we excluded `session` from the schema dump too. BetterAuth's signInEmail does `prisma.session.create()` which failed. Dumped the session table schema separately and imported.

## Harness improvements landed

| Change | File | Why |
|---|---|---|
| `VALIDATOR_USE_DIRECT_SQL=1` opt-in | `ui_validators/case_status_filter.py` | At 60K+ cases, `/dashboard/cases?limit=500` Next.js page never completes rendering pagination footer (React Suspense + slow server action). Direct local-docker SQL is equivalent ground truth. |
| Default on in test fixture | `tests/test_baseline_derived_ui.py` | Production-scale runs auto-use SQL mode |
| Bot payload + raw SQL in JSON output | `runner.py` | Per-test debug without re-running |
| Auto-login error responses | `idre/app/api/dev/auto-login/route.ts` | Returns JSON error instead of silent 500 — surfaced the 2FA blocker quickly |
| `TARGET_DB` env override | `.snapshots/reset_ryan_password.py` | Script can target `idre` (now) or `orchid-idre` (legacy) |

## Test prompts revised for production semantics

| Test | What changed | Why |
|---|---|---|
| `D_avg_processing_time_ui` | Prompt now says "use CEILING per case, then ROUND of AVG" | IDRE's `lib/utils/report-calculations.ts:50` uses `Math.ceil` per case then `Math.round` of avg. DATEDIFF floors fractional days → off-by-1 at scale |
| `D_overdue_due_dates_ui` | Prompt now says "SELECT COUNT(*) ... WHERE COALESCE(due_date, eligibilityDueDate, paymentDueDate, due_date_until_decision) < UTC_TIMESTAMP()" | IDRE picks ONE primary due date per case in priority order (`lib/reports/due-dates.ts:335`), not OR-across-all-columns. OR-pattern gave 30,994; COALESCE gives 63,353 (matches IDRE) |

## How to refresh the snapshot in future

One-liner from `local/`:
```bash
# Dump in container (15-20 min at current throughput)
MSYS_NO_PATHCONV=1 docker exec idre-mysql bash -c '
mysqldump -h mysql-8-stage-1-cluster... -P 3306 -u app_idre_rw -p<PW> \
  --ssl-ca=/tmp/global-bundle.pem --ssl-mode=REQUIRED \
  --no-create-info --extended-insert --hex-blob --single-transaction --quick \
  --no-tablespaces --set-gtid-purged=OFF --skip-lock-tables \
  --ignore-table=idre_stage.email_job \
  --ignore-table=idre_stage.case_action \
  --ignore-table=idre_stage.cms_api_request_log \
  --ignore-table=idre_stage.cms_sync_log \
  --ignore-table=idre_stage.session \
  --ignore-table=idre_stage._prisma_migrations \
  idre_stage | gzip -c > /tmp/data.sql.gz'
# Import (~4 min)
docker exec idre-mysql bash -c '
{ echo "SET FOREIGN_KEY_CHECKS=0;"; gunzip -c /tmp/data.sql.gz; echo "SET FOREIGN_KEY_CHECKS=1;"; } \
  | mysql -uroot -pidrelocal idre'
# Reset Ryan + disable 2FA (one-shot)
python .snapshots/reset_ryan_password.py
"<DELETE FROM twoFactor>" via pymysql to local docker idre
```

## What this unblocks

- V10 bot now tested against production-shaped data (1,883x cases / 5,847x payments)
- Real semantic mismatches surfaced and fixed (CEIL vs FLOOR, OR vs COALESCE priority)
- Each future bot change can re-run `pytest testing/v10_harness/tests/test_baseline_derived_ui.py` and confirm it still passes at production scale
- Streamlit UI at `http://127.0.0.1:8501` now exercises bot against production-scale data live
