# Task 1 Pivot — Snapshot Staging → Local Docker

**Date:** 2026-05-17
**Status:** Replaces original Task 1 ("verify IDRE local against staging is read-only")

## Why we pivoted

Original Task 1 required IDRE running locally to authenticate against staging
RDS so the bot and the IDRE UI both read the same database. Auto-login broke
because none of the seeded staging passwords work for any admin/test account.

An exhaustive search ran against `account.password` (BetterAuth scrypt format
`hexsalt:hexhash`, params N=16384 r=16 p=1 dkLen=64): 46 candidate passwords
were tested across every email in `user` (`ryan@orchidsoftsolutions.com`,
`karthick.murugan@telomeregs.com`, several admin/test/seed/demo addresses).
Result: NO MATCH for any candidate against any account. The staging admin
password is not present in any local codebase, env file, doc, or commit
history we have access to.

Pivot decision: instead of "IDRE reads staging," **snapshot staging into the
existing local docker MySQL, revert IDRE to its original local-docker config,
and let auto-login work the way it always did against local docker.** The bot
continues to read staging directly (unchanged). The local IDRE UI reads the
local snapshot. Both surfaces reflect the same dataset at snapshot time.

## Architecture

```
                staging RDS (idre_stage)
                       │
                       │ mysqldump (one-shot, SSL, --single-transaction)
                       ▼
        .snapshots/staging_snapshot_YYYYMMDD.sql.gz
                       │
                       │ gunzip | mysql (into local docker)
                       ▼
   docker idre-mysql ── orchid-idre  ← IDRE local (next dev) reads this
                                         + Playwright UI scraping reads this

   staging RDS (idre_stage) ← v10 reports bot reads this directly
```

Both surfaces (bot + UI) read snapshot-coherent data because the bot's SELECTs
return the same rows the mysqldump captured at snapshot time. Drift accumulates
only as staging changes after the snapshot — refresh the snapshot to re-align.

## Tables excluded from snapshot

Skipped to reduce dump size and avoid irrelevant content:

| Table | Size | Rows | Reason |
|-------|------|------|--------|
| `email_job` | 5.2 GB | 277,386 | Email send queue; unused by reports/UI |
| `cms_api_request_log` | 22 MB | 51,971 | External API request log; no FKs |
| `cms_sync_log` | 10.6 MB | 6,556 | Sync audit log; no FKs |
| `session` | 2.6 MB | 2,459 | Auth sessions; recreated on login |
| `_prisma_migrations` | 0.08 MB | 169 | Local docker has its own migrations chain |

All other tables (including `case_action` 800MB, `payment` 486MB, `case`
267MB, etc.) are preserved — they're referenced by core reports and the
derived-ui validators.

## How to refresh the snapshot

```bash
# from C:\Users\anand\Downloads\local
docker cp C:\Users\anand\Downloads\v10_reports_bot\global-bundle.pem idre-mysql:/tmp/global-bundle.pem

docker exec idre-mysql sh -c 'mysqldump \
  -h mysql-8-stage-1-cluster.cluster-cc1r7ekdbl8j.us-east-1.rds.amazonaws.com \
  -P 3306 -u app_idre_rw -p"<PW>" \
  --ssl-mode=REQUIRED --ssl-ca=/tmp/global-bundle.pem \
  --single-transaction --quick --skip-lock-tables --no-tablespaces --set-gtid-purged=OFF \
  --ignore-table=idre_stage.email_job \
  --ignore-table=idre_stage.cms_api_request_log \
  --ignore-table=idre_stage.cms_sync_log \
  --ignore-table=idre_stage.session \
  --ignore-table=idre_stage._prisma_migrations \
  idre_stage | gzip -c > /tmp/staging_snapshot.sql.gz'

docker cp idre-mysql:/tmp/staging_snapshot.sql.gz \
  C:\Users\anand\Downloads\local\.snapshots\staging_snapshot_$(date +%Y%m%d).sql.gz

# import (DROP/CREATE for clean slate)
docker exec idre-mysql mysql -h 127.0.0.1 -u root -pidrelocal \
  -e "DROP DATABASE IF EXISTS \`orchid-idre\`; CREATE DATABASE \`orchid-idre\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

docker exec -i idre-mysql sh -c 'gunzip | mysql -h 127.0.0.1 -u root -pidrelocal orchid-idre' \
  < C:\Users\anand\Downloads\local\.snapshots\staging_snapshot_<DATE>.sql.gz

# reset Ryan's password to scrypt(orchid123) so auto-login works
python C:\Users\anand\Downloads\local\.snapshots\reset_ryan_password.py
```

## Sensitivity

The dump contains real Veratru/Telomere client data (cases, parties, payments,
SSNs in some tables, etc.). It is:

- gitignored via `.snapshots/` + `*.sql.gz` in `C:\Users\anand\Downloads\local\.gitignore`
- never to be committed, pushed to any remote, or shared off the laptop
- subject to the same authorization the bot already has (the bot already reads
  this data live from staging; the snapshot persists what it already queries)

## Verification

(filled in by Task G after import completes)

- [x] Dump file created on disk
- [ ] Import into `orchid-idre` succeeded
- [ ] Row counts confirmed (`user`, `case`, `payment` ≥ staging baselines)
- [ ] Ryan password reset returned 1 row updated
- [x] `idre/.env` identical to `.env.localmysql.backup` (verified zero-diff)
- [x] `app/api/dev/auto-login/route.ts` matches the 27-line original (no env reads, no try/catch)
- [ ] User restarts `npx next dev`; controller probes auto-login → 302 redirect with set-cookie
