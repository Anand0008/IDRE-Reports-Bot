# V10 Architecture Review — Session Handoff

**Date:** 2026-05-19
**Purpose:** Resume in a fresh session to **review V10's architecture node-by-node** and decide on the best target architecture.
**Status of this session:** OTEL tracing infrastructure landed (tag `v10-otel-tracing`); derived-DOM Phase 1 at 7/30 with failures classified. No more code changes pending. **Next session = architecture review only.**

---

## 1. Where we actually are

### Tags pushed today on `Anand0008/IDRE-Reports-Bot`

- `derived-ui-baseline` — initial 8/15 PASS on dev seed
- `derived-ui-baseline-v2` — 15/15 PASS on dev seed after fixes
- `derived-ui-baseline-snapshot` — 15/15 PASS on staging snapshot (67K cases)
- `v10-otel-tracing` — full per-query tracing via local Jaeger

### V10 bot repo: `Anand0008/v10-reports-bot` (pushed today, master branch)

Active commits: sql_writer markdown-fence fix, ambiguity-threshold env override, OTEL instrumentation (8 commits, ending `a561e1f`).

### Running infrastructure on this laptop right now

| Service | Endpoint / how | State |
|---|---|---|
| IDRE local (Next.js prod build) | http://127.0.0.1:3000 — reads local docker `idre` | Running (PID 26476) |
| Local docker MySQL | container `idre-mysql`, port 3306, DB `idre` | 67,794 cases (staging snapshot) |
| Jaeger | http://localhost:16686, OTLP at 4318 | Running (`v10-jaeger` container) |
| Streamlit V10 UI | http://127.0.0.1:8501 — env-overridden at launch to point at local docker | Running (background bash from earlier in session) |

### What's NOT running

Nothing — everything that needs to be is up.

---

## 2. The V10 architecture as it ACTUALLY exists (not what the spec said)

### The corrected one-line summary

V10 is **V8's pipeline + new SQL Writer + 8 in-process tools**, NOT the clean MCP-pure agentic flow that may have been envisioned. The 10-agent LangGraph state machine from V8 is intact; only the SQL Writer step has agentic (Gemini function-calling) behavior.

### Known path (15/15 PASS, no LLM)

```
prompt → harness_entrypoint.run_query_v10
       → agents/router.py:route() [deterministic signature match, 12 hardcoded reports]
       → if path=="known":
           → agents/idre_api_client.py:IdreApiClient.call(report, parameters)
                [HTTP GET http://127.0.0.1:3000/api/reports/<endpoint>, 60s cache, auto-login]
           → agents/response_normalizer.py:normalize(body)
           → return {**body, _v10_router_decision, _v10_normalized, _v10_idre_status}
```

No SQL. No LLM. Direct API proxy + envelope normalization. **15/15 PASS by construction — bot's "answer" is literally IDRE's API response.**

### Derived path (current 7/30 on production-scale data)

```
prompt → harness_entrypoint.run_query_v10
       → agents/router.py:route() [signature didn't match 12 known reports → path="derived"]
       → core/orchestrator.py:run_query()  [LangGraph state machine, GraphState flows through]
           → context_loader_node                [agents/context_loader.py — glossary, role, history]
           → ambiguity_scorer_node              [agents/ambiguity_scorer.py — 0-100% heuristic]
           → clarification_agent_node           [agents/clarification_agent.py — bypass if env override]
           → schema_mapper_node                 [agents/schema_mapper.py — table short-list]
           → platform_context_agent_node       [agents/platform_context_agent.py — terminology]
           → schema_verifier_node               [agents/schema_verifier.py — validate match]
           → sql_writer_node                    [agents/sql_writer.py — GEMINI 2.5 PRO + 8 tools]
           → sql_validator_node                 [agents/sql_validator.py — DDL/DML/semicolon reject]
           → executor_node                      [agents/executor.py — SQLAlchemy + mysql-connector]
              (on fail → debugger_agent_node → retry sql_writer, max 3)
           → post_processor_node                [agents/post_processor.py]
           → output_formatter_node              [agents/output_formatter.py]
           → response_formatter_node            [agents/response_formatter.py]
       → return {router_decision, data, sql, row_count, agent_trace, fallback_reason}
```

### The "8 tools" — NOT MCP

`agents/sql_writer.py` registers 8 Python functions as Gemini function-calling tools (`genai.protos.Tool`). These run in-process — no MCP, no JSON-RPC, no separate processes:

| Tool | What it reads/does |
|---|---|
| `get_idre_business_logic` | `knowledge/v10/business_logic.json` |
| `get_table_schema` | `knowledge/v10/schema_catalog.json` |
| `get_enum_values` | `knowledge/v10/enum_catalog.json` |
| `lookup_business_term` | glossary JSON |
| `list_available_reports` | `knowledge/v10/report_reference_cards.json` |
| `find_filter_pattern` | pattern lookup |
| `verify_sql_executes` | dry-run against staging |
| `get_report_reference` | V8-era hand-written reference SQL |

### Schema Mapper's "vector + BM25" — NOT document RAG

The schema_mapper uses vector embeddings over table NAMES/DESCRIPTIONS + BM25 to short-list 3 of 32 permitted tables. This is **table retrieval** (small embedding space), not **document RAG** (chunked-doc retrieval). V10 spec retired document RAG; schema retrieval stayed.

The `v10_architecture.html` I generated this session has a green "vector" node here that visually implies RAG. **This is misleading and was flagged for relabeling but not changed.**

### Things V10 explicitly does NOT have

- ❌ Document RAG (file_summaries / repo_map / module_keywords from V3/V4 — retired in V10 spec)
- ❌ MCP servers (the 8 tools are in-process Gemini functions, not MCP)
- ❌ Pure-agentic flow (LLM does not orchestrate the pipeline; pipeline orchestration is hardcoded Python)
- ❌ metric_cards, sql_templates, `_COMMONLY_HALLUCINATED` dict
- ❌ Post-processor with platform context (separate concept from current post_processor)

---

## 3. Validation harness as it stands

### Three test suites against V10

| Suite | File | Validators | Status |
|---|---|---|---|
| Known | `tests/test_baseline_known.py` | `expected_idre_call` (direct API compare) | 15/15 PASS |
| Derived-UI v1 | `tests/test_baseline_derived_ui.py` | dashboard_stats, case_status_filter, payment_lifecycle, due_dates_filter (mixed API/SQL) | 15/15 PASS on snapshot |
| Derived-DOM Phase 1 | `tests/test_baseline_derived_dom.py` | dom_scrape, dom_lookup, canonical_sql | **7/30 PASS on snapshot** |

### Derived-DOM Phase 1: 23 failures classified

**Pattern A — `dom_scrape` page-render timeout (15 tests)**
- `/dashboard/cases?status=X&limit=1` page never renders pagination footer "Showing N of <total>" within 60s for high-cardinality status buckets
- Root cause: IDRE's server action computes COUNT(*) across 67K cases; that's the slow step (not page-shell render which is fast)
- Affected: every status filter (DD_pending_rfi, DD_initial_elig, DD_final_det_pending, DD_final_det_rendered, DD_final_elig_completed, DD_pending_payments, DD_pending_second_payment, DD_final_elig_review, DD_ineligible_admin, DD_pending_admin_closure, DD_pending_closure_payments, DD_pending_initial_rfi, DD_completed_count, DD_ineligible_count, DD_notice_dismissal_count)
- Counter-evidence: `DD_reopened_count` (small bucket) PASSED — proves bottleneck is at-scale COUNT not validator code

**Pattern B — `dom_lookup` search-page timeout (5 tests)**
- Same root cause as A; `/dashboard/cases?search=<id>&limit=1` also does COUNT(*)
- Affected: DD_rows_pending_rfi, DD_rows_initial_elig, DD_rows_final_det_pending, DD_rows_recent_5, DD_rows_pending_payments

**Pattern C — Bot routed to known path instead of derived (1 test)**
- DD_overdue_count: router matched "how many cases are currently overdue?" → known signature → `/api/reports/due-dates` → returned 50 paginated cases → runner reduced list to 50; validator's canonical_sql returned 63353
- Bot never generated SQL — derived path wasn't exercised for this prompt

**Pattern D — canonical_sql value mismatch (2 tests)**
- DD_total_completed_payments, DD_active_arbitrators_count
- Exact diffs in their `testing/v10_harness/reports/DD_*.json` files — not investigated this session per user direction
- Likely bot SQL has different WHERE / different aggregation than canonical, OR result-shape reduction picked wrong field

**7 PASSES:** mostly canonical_sql (DD_mtd_final_dets, DD_mtd_defaults, DD_new_today, DD_mtd_new_cases, DD_pending_payments_count, DD_total_cases) + the one small-bucket dom_scrape (DD_reopened_count).

### The deeper lesson

The 7 canonical_sql passes prove **bot SQL generation is generally correct**. The 15 dom_scrape failures aren't telling us about V10 — they're telling us **IDRE's cases-list page can't compute pagination total fast enough for validator's 60s budget at 67K-row scale**. That's an IDRE UX limit surfaced by our scale, not a bot bug.

---

## 4. OTEL tracing landed this session

### Infrastructure

- Jaeger all-in-one container `v10-jaeger`, latest image (`:1.61` wasn't on Docker Hub)
- UI: http://localhost:16686
- OTLP HTTP endpoint: 4318
- Service name: `v10-bot` (distinct from IDRE's `idre-platform`)

### Span hierarchy per query

```
v10.query (root)
├── v10.router.route
├── v10.known.api_call                 (known path)
└── v10.derived.orchestrator           (derived path)
    ├── v10.agent.context_loader
    ├── v10.agent.ambiguity_scorer (with .score, .flags, .threshold)
    ├── v10.agent.clarification_agent
    ├── v10.agent.schema_mapper (with .tables_matched, .scores_available)
    ├── v10.agent.platform_context
    ├── v10.agent.schema_verifier
    ├── v10.agent.sql_writer
    │   ├── v10.gemini.call (one per tool round)
    │   └── v10.tool.<name> (per tool call)
    ├── v10.agent.sql_validator
    ├── v10.agent.executor (with .row_count, .elapsed_ms)
    │   └── v10.db.query
    ├── v10.agent.post_processor
    └── v10.agent.response_formatter
```

### Risk verifications

| Risk | Result |
|---|---|
| R1 IDRE/V10 service-name collision | ✅ PASS — services `v10-bot` + `idre-platform` distinct |
| R2 schema-mapper scores not exposable | ⚠️ Confirmed not exposable (`get_relevant_tables` returns names only). Fallback worked: `schema.scores_available=False`. |
| R3 Gemini tool registration broken by wrapping | ✅ PASS — 8/8 tools register |
| R4 overhead when disabled | ⚠️ 12.6% wall-clock delta on 3-test sample. Subagent attributes to LLM/network variance (identical FAIL pattern in both runs), not OTEL CPU. Needs cleaner measurement (mock LLM, fixed-seed runs) to confirm. |
| R5 Jaeger-down tolerance | ✅ Designed-in via BatchSpanProcessor (not stress-tested live) |
| R6 PII redaction | ✅ 5 unit tests pass (email/phone/SSN) |
| R7 in-memory storage limit | ✅ Documented; restart container clears |

### Toggle

`V10_OTEL_ENABLED=0` → decorators become identity → zero overhead.

---

## 5. Open architectural questions to address in next session

This is the **core of the next session's work**.

### Q1 — Pipeline vs Pure-Agentic

V10 currently has a hardcoded 10-agent pipeline; only the SQL Writer step is agentic. **Should V10 be:**
- (a) **Status quo** — keep the pipeline; refine each agent's behavior
- (b) **Pure-agentic rewrite** — single Gemini agent loop with 8 tools as MCP servers, LLM decides everything (context loading, ambiguity, schema mapping, validation, execution, retry)
- (c) **Hybrid** — keep deterministic pre-processing (context_loader, ambiguity_scorer); replace schema_mapper + sql_writer + sql_validator + executor with a single agentic block

Each has different complexity, latency, and observability tradeoffs.

### Q2 — Schema retrieval: keep, drop, or expose?

Schema Mapper uses vector + BM25 over table descriptions to pick top-K=3. Options:
- (a) Keep as-is (current)
- (b) Drop entirely — let SQL Writer call `get_table_schema` for whichever tables it thinks it needs (more LLM calls, more bot agency)
- (c) Expose scores in trace so we can audit which 3 tables were picked + why

### Q3 — Schema validator strictness

`sql_validator` currently rejects DDL/DML/semicolons. Should it also:
- Validate against schema (column names exist)?
- Validate against role permissions (matches table allow-list from schema_mapper)?
- Validate against pattern library (e.g., "MTD queries must use `statusChangedAt`")?

### Q4 — Retry / debugger budget

`debugger_agent` retries SQL Writer on executor failure, max 3 times. Is 3 the right number? Should retry decisions be visible in trace?

### Q5 — Known-path routing

Router has 12 hardcoded signatures + LLM-fallback STUB (never used in practice). Should:
- (a) Remove LLM fallback dead code
- (b) Actually wire LLM fallback for prompts that don't match any signature
- (c) Drop the known/derived distinction entirely — always go derived (then known reports just happen to map to deterministic SQL)

### Q6 — Output formatter vs response formatter

There are TWO format-stage agents (`output_formatter`, `response_formatter`). Is the distinction meaningful or should they merge?

### Q7 — Validator architecture for at-scale DOM testing

As Phase 1 baseline showed: DOM-scrape at 67K-row scale doesn't work due to IDRE's pagination COUNT cost. The "pure DOM" validation philosophy may need revisiting. Options:
- (a) Bump timeout to 5-10 min (slow but works)
- (b) Hybrid: dom_scrape for small buckets, canonical_sql for large (auto-detect)
- (c) Use IDRE's internal API (the one /dashboard/cases page itself calls) as ground truth — relaxes "strict DOM" but matches what would-eventually-display

---

## 6. Resume steps for the fresh session

When you start a new session, paste this into the first message:

```
Continuing V10 architecture review. Read this handoff first:
docs/superpowers/reports/2026-05-19-handoff-architecture-review.md

I want to do a node-by-node review of V10's actual architecture (the 10-agent
pipeline + 8 in-process tools as documented there). At the end I want to
decide which of Q1-Q7 (pipeline vs pure-agentic, schema retrieval, validator
strictness, retry budget, router fallback, formatter consolidation, validator
philosophy) need work and in what order.

Don't make any code changes. Just review + recommend.

Status snapshot: tag v10-otel-tracing is live, Jaeger at localhost:16686,
derived-DOM Phase 1 at 7/30 PASS (15 failures = IDRE's at-scale UI render
cost, not bot bugs), all session work pushed to GitHub.
```

That message gives a fresh session full context in one shot. The handoff file has all the detail; the new session can pull what it needs.

### Verifications to run in the fresh session before diving in

```bash
# 1. Confirm infrastructure still up
curl -s http://localhost:16686/api/services    # expects v10-bot + idre-platform
docker ps --format '{{.Names}} {{.Status}}' | grep -E "idre-mysql|v10-jaeger"
curl -sS -I --max-time 15 "http://127.0.0.1:3000/api/dev/auto-login" | grep -E "HTTP|set-cookie"

# 2. Confirm snapshot data
docker exec idre-mysql mysql -uroot -pidrelocal -Nse "SELECT COUNT(*) FROM idre.\`case\`"
# expect 67794

# 3. Confirm git state
cd /c/Users/anand/Downloads/local
git log --oneline -5
git tag --list "derived-ui-baseline*" "v10-otel*"
```

If anything is down, the handoff doc has the launch commands.

### Files to read first in the fresh session (in priority order)

1. **This handoff file** — `docs/superpowers/reports/2026-05-19-handoff-architecture-review.md`
2. **V10 spec** — `docs/superpowers/specs/2026-05-15-v10-reports-bot-design.md` (original V10 design)
3. **Recent done docs** — anything in `docs/superpowers/reports/2026-05-1[7-9]*.md`
4. **The actual agent files** (read on-demand during review) — `v10_reports_bot/agents/*.py`

### What NOT to do in the fresh session

- Don't try to fix Phase 1 baseline failures yet — they're classified, not actionable until architecture decisions land
- Don't push any architecture changes to v10_reports_bot main until the review concludes
- Don't expand to Phase 2 (80 tests) yet — same reason
- Don't touch IDRE source (`local/idre/`) — out of scope; any IDRE perf concerns are documented in this handoff

---

## 7. Memory keys updated to reflect today's state

- `project_idre.md` — added derived-ui-baseline-snapshot tag entry; will add `v10-otel-tracing` and Phase 1 7/30 result entries (see memory updates this turn)
- `feedback_observability.md` — referenced; OTEL implementation closes part of this ask but only for tracing; structured logging is still future work

End of handoff.
