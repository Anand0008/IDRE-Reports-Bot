# V10 OTEL Tracing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** 100% per-query traceability for V10 bot via OpenTelemetry → local Jaeger.

**Architecture:** Single `tracing.py` helper module + one decorator per agent + tool-call wrapping in SQL Writer. Async OTLP HTTP export to Jaeger all-in-one container.

**Tech Stack:** `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, Jaeger 1.61 (Docker).

**Spec:** `docs/superpowers/specs/2026-05-19-v10-otel-tracing-design.md`

**Working dir:** `C:\Users\anand\Downloads\v10_reports_bot` for bot edits; `C:\Users\anand\Downloads\local` for harness + scripts + docs.

**Python:** `/c/Users/anand/AppData/Local/Programs/Python/Python311/python.exe` (alias `py311`)

---

## File Structure

```
v10_reports_bot/
  tracing.py                          # NEW core helper
  requirements.txt                    # MODIFY add OTEL deps
  harness_entrypoint.py               # MODIFY wrap run_query_v10 in root span
  agents/
    router.py                         # MODIFY add @trace_agent
    idre_api_client.py                # MODIFY add span around HTTP call + cache
    response_normalizer.py            # MODIFY add @trace_agent
    context_loader.py                 # MODIFY add @trace_agent
    ambiguity_scorer.py               # MODIFY add @trace_agent + custom attrs
    clarification_agent.py            # MODIFY add @trace_agent + custom attrs
    schema_mapper.py                  # MODIFY add @trace_agent + tables/scores
    platform_context_agent.py         # MODIFY add @trace_agent
    schema_verifier.py                # MODIFY add @trace_agent
    sql_writer.py                     # MODIFY add @trace_agent + tool wrapping
    sql_validator.py                  # MODIFY add @trace_agent
    executor.py                       # MODIFY add @trace_agent + db.query child span
    debugger_agent.py                 # MODIFY add @trace_agent
    post_processor.py                 # MODIFY add @trace_agent
    output_formatter.py               # MODIFY add @trace_agent
    response_formatter.py             # MODIFY add @trace_agent
    feedback_injector.py              # MODIFY add @trace_agent

local/
  scripts/snapshot/start_jaeger.sh    # NEW Jaeger launcher
  docs/superpowers/reports/
    2026-05-19-otel-screenshot.md     # NEW final smoke-trace evidence
```

---

## Task 1: Install OTEL dependencies + start Jaeger

**Files:** `v10_reports_bot/requirements.txt`, `local/scripts/snapshot/start_jaeger.sh`

- [ ] **Step 1: Add OTEL deps to bot requirements**

Read `v10_reports_bot/requirements.txt`, then append:
```
opentelemetry-sdk>=1.27.0,<2
opentelemetry-exporter-otlp-proto-http>=1.27.0,<2
opentelemetry-api>=1.27.0,<2
```

- [ ] **Step 2: Install**

```bash
py311 -m pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http opentelemetry-api 2>&1 | tail -3
```

- [ ] **Step 3: Create Jaeger launcher script**

Create `C:\Users\anand\Downloads\local\scripts\snapshot\start_jaeger.sh`:
```bash
#!/usr/bin/env bash
set -e
# Idempotent: skip if container exists
if docker ps -a --format '{{.Names}}' | grep -q '^v10-jaeger$'; then
  docker start v10-jaeger >/dev/null
  echo "v10-jaeger already exists; started."
else
  docker run -d --name v10-jaeger --restart unless-stopped \
    -p 16686:16686 -p 4317:4317 -p 4318:4318 \
    jaegertracing/all-in-one:1.61
fi
echo "Jaeger UI: http://localhost:16686"
echo "OTLP HTTP endpoint: http://localhost:4318/v1/traces"
```

- [ ] **Step 4: Run launcher**

```bash
bash /c/Users/anand/Downloads/local/scripts/snapshot/start_jaeger.sh
sleep 3
curl -s http://localhost:16686/ -o /dev/null -w "Jaeger UI HTTP: %{http_code}\n"
curl -s -X POST http://localhost:4318/v1/traces -H 'content-type: application/json' -d '{}' -o /dev/null -w "OTLP endpoint HTTP: %{http_code}\n"
```

Expected: UI returns 200; OTLP endpoint returns 200 or 400 (valid endpoint, empty payload).

- [ ] **Step 5: Commit**

```bash
cd /c/Users/anand/Downloads/v10_reports_bot
git add requirements.txt
git commit -m "feat(deps): OTEL SDK + OTLP HTTP exporter for tracing"
cd /c/Users/anand/Downloads/local
git add scripts/snapshot/start_jaeger.sh
git commit -m "feat(snapshot): start_jaeger.sh launcher"
```

---

## Task 2: Create `tracing.py` helper module

**Files:** `v10_reports_bot/tracing.py`, `v10_reports_bot/tests/test_tracing.py`

- [ ] **Step 1: Write the failing test first**

Create `v10_reports_bot/tests/test_tracing.py` (mkdir `tests/` if needed):
```python
"""Unit tests for tracing helper module."""
import os
import pytest


def test_redact_email():
    from tracing import redact
    assert redact("contact ryan@orchidsoftsolutions.com today") == "contact <email> today"


def test_redact_phone():
    from tracing import redact
    assert redact("call 5551234567 now") == "call <phone> now"


def test_redact_ssn():
    from tracing import redact
    assert redact("ssn 123-45-6789") == "ssn <ssn>"


def test_redact_keeps_other_text():
    from tracing import redact
    assert redact("hello world") == "hello world"


def test_redact_handles_non_string():
    from tracing import redact
    assert redact(None) is None
    assert redact(42) == 42


def test_trace_agent_no_op_when_disabled(monkeypatch):
    """When V10_OTEL_ENABLED=0, decorator must be identity (zero overhead)."""
    monkeypatch.setenv("V10_OTEL_ENABLED", "0")
    # Re-import to pick up env (this is tricky with cached imports; using a fresh module path)
    import importlib, sys
    if "tracing" in sys.modules:
        del sys.modules["tracing"]
    import tracing
    @tracing.trace_agent("v10.test.noop")
    def my_fn(state):
        return {**state, "ran": True}
    result = my_fn({"x": 1})
    assert result == {"x": 1, "ran": True}


def test_trace_agent_runs_when_enabled(monkeypatch):
    """When enabled, decorator runs the function and sets span attributes without raising."""
    monkeypatch.setenv("V10_OTEL_ENABLED", "1")
    import importlib, sys
    if "tracing" in sys.modules:
        del sys.modules["tracing"]
    import tracing
    @tracing.trace_agent("v10.test.enabled")
    def my_fn(state):
        return {**state, "ran": True, "agent_trace": [{"agent": "test", "status": "ok", "summary": "did the thing"}]}
    result = my_fn({"x": 1})
    assert result["ran"] is True


def test_traced_tool_call_no_op_when_disabled(monkeypatch):
    monkeypatch.setenv("V10_OTEL_ENABLED", "0")
    import importlib, sys
    if "tracing" in sys.modules:
        del sys.modules["tracing"]
    import tracing
    with tracing.traced_tool_call("test_tool"):
        pass  # just must not raise
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd /c/Users/anand/Downloads/v10_reports_bot
py311 -m pytest tests/test_tracing.py -v 2>&1 | tail -15
```

Expected: ImportError on `tracing`.

- [ ] **Step 3: Implement `tracing.py`**

Create `v10_reports_bot/tracing.py` with exact content from spec §5.1 (incorporated verbatim — see spec).

- [ ] **Step 4: Run tests to verify passing**

```bash
py311 -m pytest tests/test_tracing.py -v 2>&1 | tail -15
```

Expected: 8 passed.

- [ ] **Step 5: Verify a span actually reaches Jaeger**

```bash
py311 -c "
import os; os.environ['V10_OTEL_ENABLED'] = '1'
import sys; sys.path.insert(0, '.')
import tracing
@tracing.trace_agent('v10.test.smoke')
def go(state): return {**state, 'done': True}
result = go({'in': 'data'})
print('result:', result)
import time; time.sleep(2)  # allow batch exporter to flush
print('Check Jaeger UI: http://localhost:16686  service=v10-bot operation=v10.test.smoke')
"
```

- [ ] **Step 6: Visit Jaeger UI** (`http://localhost:16686`) — service `v10-bot` should appear in dropdown; one trace with operation `v10.test.smoke`. Capture screenshot (manual; save to `local/docs/superpowers/reports/2026-05-19-otel-screenshot.md` later).

- [ ] **Step 7: Commit**

```bash
cd /c/Users/anand/Downloads/v10_reports_bot
git add tracing.py tests/test_tracing.py
git commit -m "feat(tracing): OTEL helper module — @trace_agent, traced_tool_call, redact (Risk R4+R5+R6 mitigations)"
```

---

## Task 3: Instrument router + harness_entrypoint (root span + path branching)

**Files:** `v10_reports_bot/harness_entrypoint.py`, `v10_reports_bot/agents/router.py`

- [ ] **Step 1: Wrap `run_query_v10` in root span**

Read `harness_entrypoint.py`. At the top of `run_query_v10`, replace the body with:

```python
def run_query_v10(prompt: str, now_anchor=None, user_role: str = "MA") -> dict:
    from tracing import get_tracer, redact
    tracer = get_tracer()
    with tracer.start_as_current_span("v10.query") as span:
        span.set_attribute("query.prompt", redact(prompt)[:500])
        span.set_attribute("query.user_role", user_role)
        rd = route(prompt)
        span.set_attribute("query.path", rd.path)
        span.set_attribute("router.report", rd.report or "")
        span.set_attribute("router.confidence", float(rd.confidence))

        if rd.path == "known":
            with tracer.start_as_current_span("v10.known.api_call") as known_span:
                try:
                    client = IdreApiClient()
                    resp = client.call(rd.report, rd.parameters)
                except Exception as e:
                    known_span.set_attribute("known.error", str(e)[:200])
                    return _run_derived(prompt, rd, user_role, error=str(e))
                body = resp.get("body") if isinstance(resp.get("body"), dict) else {}
                known_span.set_attribute("known.idre_status", resp.get("status_code", 0))
                return {
                    **body,
                    "_v10_router_decision": {
                        "path": rd.path, "report": rd.report,
                        "parameters": rd.parameters, "confidence": rd.confidence,
                    },
                    "_v10_normalized": normalize(body),
                    "_v10_idre_status": resp["status_code"],
                }
        elif rd.path == "clarify":
            return {
                "router_decision": {"path": "clarify", "confidence": rd.confidence},
                "data": None,
                "error": "clarification_required",
            }
        else:
            return _run_derived(prompt, rd, user_role)
```

- [ ] **Step 2: Wrap router's `route` function**

In `agents/router.py`, find `def route(...)`. Wrap return with span using existing pattern:

```python
def route(prompt: str):
    from tracing import get_tracer
    tracer = get_tracer()
    with tracer.start_as_current_span("v10.router.route") as span:
        # ... existing logic stays here ...
        result = _existing_route_logic(prompt)
        span.set_attribute("router.matched_signature", result.report or "<none>")
        span.set_attribute("router.path", result.path)
        return result
```

(If existing `route` is short, inline it.)

- [ ] **Step 3: Smoke run with known + derived prompts**

```bash
py311 -c "
import os; os.environ['V10_OTEL_ENABLED'] = '1'
from harness_entrypoint import run_query_v10
# Known
print(run_query_v10('show me the dashboard overview').get('_v10_router_decision'))
import time; time.sleep(2)
# Derived
r = run_query_v10('how many cases are pending RFI?')
print('derived path:', r.get('router_decision'))
time.sleep(2)
" 2>&1 | tail -10
```

Both should appear in Jaeger UI under service `v10-bot`.

- [ ] **Step 4: Commit**

```bash
cd /c/Users/anand/Downloads/v10_reports_bot
git add harness_entrypoint.py agents/router.py
git commit -m "feat(tracing): root span in harness_entrypoint + router span (Task 3)"
```

---

## Task 4: Instrument all derived-path agents with @trace_agent

**Files:** all 14 files in `v10_reports_bot/agents/`

- [ ] **Step 1: For each agent file, add the import + decorator**

For each of these files, locate the `*_node` function and add `@trace_agent(...)` decorator above:

| File | Function | Decorator name |
|---|---|---|
| `agents/context_loader.py` | `context_loader_node` | `v10.agent.context_loader` |
| `agents/ambiguity_scorer.py` | `ambiguity_scorer_node` | `v10.agent.ambiguity_scorer` |
| `agents/clarification_agent.py` | `clarification_agent_node` | `v10.agent.clarification_agent` |
| `agents/schema_mapper.py` | `schema_mapper_node` | `v10.agent.schema_mapper` |
| `agents/platform_context_agent.py` | (the node fn) | `v10.agent.platform_context` |
| `agents/schema_verifier.py` | (the node fn) | `v10.agent.schema_verifier` |
| `agents/sql_writer.py` | `sql_writer_node` | `v10.agent.sql_writer` |
| `agents/sql_validator.py` | (the node fn) | `v10.agent.sql_validator` |
| `agents/executor.py` | (the node fn) | `v10.agent.executor` |
| `agents/debugger_agent.py` | (the node fn) | `v10.agent.debugger` |
| `agents/post_processor.py` | (the node fn) | `v10.agent.post_processor` |
| `agents/output_formatter.py` | (the node fn) | `v10.agent.output_formatter` |
| `agents/response_formatter.py` | (the node fn) | `v10.agent.response_formatter` |
| `agents/feedback_injector.py` | (the node fn) | `v10.agent.feedback_injector` |

Pattern per file (top of file):
```python
from tracing import trace_agent
```

Pattern per node function:
```python
@trace_agent("v10.agent.NAME")
def NAME_node(state):
    # existing implementation unchanged
    ...
```

Use Read + Edit on each file (one decorator line + one import).

- [ ] **Step 2: Smoke test — run a single derived query**

```bash
py311 -c "
import os; os.environ['V10_OTEL_ENABLED'] = '1'
from harness_entrypoint import run_query_v10
r = run_query_v10('how many cases are pending RFI?')
print('agent_trace steps:', len(r.get('agent_trace', [])))
import time; time.sleep(3)
" 2>&1 | tail -5
```

Open Jaeger UI → service `v10-bot` → most recent trace. Expand `v10.derived.orchestrator` (will appear after Task 5; for now you'll see flat `v10.agent.*` siblings). Each agent span should be visible with `agent.status`, `agent.summary`, `agent.input_keys`, `agent.output_keys` attributes.

- [ ] **Step 3: Commit**

```bash
git add agents/
git commit -m "feat(tracing): @trace_agent decorator on all 14 derived-path agents (Task 4)"
```

---

## Task 5: Wrap derived path in orchestrator span

**Files:** `v10_reports_bot/harness_entrypoint.py`

- [ ] **Step 1: Wrap `_run_derived`**

In `harness_entrypoint.py`, modify `_run_derived`:

```python
def _run_derived(prompt, rd, user_role, error=None):
    from tracing import get_tracer
    tracer = get_tracer()
    with tracer.start_as_current_span("v10.derived.orchestrator") as span:
        from core.orchestrator import run_query
        state = run_query(
            user_query=prompt,
            session_id="harness",
            user_role=user_role,
        )
        span.set_attribute("derived.row_count", state.get("row_count", 0))
        span.set_attribute("derived.has_sql", bool(state.get("validated_sql") or state.get("generated_sql")))
        return {
            "router_decision": {
                "path": "derived", "report": rd.report,
                "parameters": rd.parameters, "confidence": rd.confidence,
            },
            "data": state.get("query_result") or [],
            "sql": state.get("validated_sql") or state.get("generated_sql") or "",
            "row_count": state.get("row_count", 0),
            "agent_trace": state.get("agent_trace", []),
            "fallback_reason": error,
        }
```

- [ ] **Step 2: Smoke run + verify orchestrator span has agent children**

```bash
py311 -c "
import os; os.environ['V10_OTEL_ENABLED'] = '1'
from harness_entrypoint import run_query_v10
r = run_query_v10('how many cases are pending RFI?')
import time; time.sleep(3)
" 2>&1 | tail -3
```

Jaeger UI → most recent trace → should show:
```
v10.query
├── v10.router.route
└── v10.derived.orchestrator
    ├── v10.agent.context_loader
    ├── v10.agent.ambiguity_scorer
    └── ... (rest of agents)
```

- [ ] **Step 3: Commit**

```bash
git add harness_entrypoint.py
git commit -m "feat(tracing): wrap derived path in orchestrator span (Task 5)"
```

---

## Task 6: Wrap SQL Writer's 8 tool calls (R3 mitigation)

**Files:** `v10_reports_bot/agents/sql_writer.py`

R3 (Risk): Wrapping must NOT break Gemini's `genai.protos.Tool` registration. Mitigation: use `functools.wraps` and verify all 8 tools still register.

- [ ] **Step 1: Find tool dispatch code**

In `sql_writer.py`, locate where Gemini tool calls are dispatched (look for the tool-loop or the function-call handler). Likely a dict/map of tool name → function.

- [ ] **Step 2: Add traced wrapper at dispatch site**

If there's a central dispatch like:
```python
TOOL_FUNCTIONS = {
    "get_idre_business_logic": get_idre_business_logic,
    "get_table_schema": get_table_schema,
    # ... 6 more
}

def dispatch_tool(name, args):
    return TOOL_FUNCTIONS[name](**args)
```

Wrap dispatch (NOT the individual functions — keeps Gemini's function declarations intact):
```python
from tracing import traced_tool_call

def dispatch_tool(name, args):
    with traced_tool_call(name) as span:
        if span is not None:
            span.set_attribute("tool.args_keys", list(args.keys())[:20])
        result = TOOL_FUNCTIONS[name](**args)
        if span is not None:
            span.set_attribute("tool.result_size", len(str(result)[:10000]))
        return result
```

- [ ] **Step 3: Pre-flight — verify all 8 tools still register with Gemini**

```bash
py311 -c "
from agents.sql_writer import _build_gemini_tools
tools = _build_gemini_tools()
print(f'tools registered: {len(tools)}')
for t in tools[:3]:
    print(' ', t)
"
```

Expected: 8 (or however many `_build_gemini_tools` returns; matches pre-instrumentation count).

If count is wrong: REVERT the wrapping pattern and report. Try the alternative — wrap individual call sites instead of dispatch.

- [ ] **Step 4: Smoke run a derived prompt + verify tool spans appear**

```bash
py311 -c "
import os; os.environ['V10_OTEL_ENABLED'] = '1'
from harness_entrypoint import run_query_v10
r = run_query_v10('how many cases are pending RFI?')
import time; time.sleep(3)
" 2>&1
```

Jaeger UI → trace → expand `v10.agent.sql_writer` → expect 1+ child spans named `v10.tool.<name>`.

- [ ] **Step 5: Commit**

```bash
git add agents/sql_writer.py
git commit -m "feat(tracing): wrap 8 SQL Writer tool calls (Task 6 + Risk R3 mitigation — functools.wraps preserves Gemini registration; verified 8/8 tools register)"
```

---

## Task 7: Add custom attributes for schema_mapper + executor (R2 mitigation)

**Files:** `v10_reports_bot/agents/schema_mapper.py`, `v10_reports_bot/agents/executor.py`

R2 (Risk): top-K scores from vector retrieval may not be exposable. Mitigation: try-extract, fall back gracefully.

- [ ] **Step 1: schema_mapper — extract tables + scores if available**

Inside the `@trace_agent`-wrapped `schema_mapper_node`, after the matching step:

```python
from opentelemetry import trace
span = trace.get_current_span()
try:
    matched_tables = state.get("matched_tables", [])  # adjust to actual state key
    span.set_attribute("schema.tables_matched", [t for t in matched_tables][:10])
    span.set_attribute("schema.k", len(matched_tables))
    # Try to extract scores (best-effort)
    scores = state.get("table_scores")  # adjust to actual key, or None
    if scores and isinstance(scores, list):
        span.set_attribute("schema.scores", [round(float(s), 4) for s in scores[:10]])
        span.set_attribute("schema.scores_available", True)
    else:
        span.set_attribute("schema.scores_available", False)
except Exception as e:
    span.set_attribute("schema.attr_error", str(e)[:200])
```

If the actual state keys differ, adjust based on reading the file.

- [ ] **Step 2: executor — record row_count + elapsed_ms + cache hit**

Inside `executor_node`, after execution:

```python
from opentelemetry import trace
span = trace.get_current_span()
span.set_attribute("executor.row_count", state.get("row_count", 0))
# elapsed_ms might already be in state; otherwise wrap timing
if "execution_elapsed_ms" in state:
    span.set_attribute("executor.elapsed_ms", state["execution_elapsed_ms"])
if "materialized_hit" in state:
    span.set_attribute("executor.was_cached", bool(state["materialized_hit"]))
```

Also add a child span for the actual SQL execution:
```python
with tracer.start_as_current_span("v10.db.query") as db_span:
    db_span.set_attribute("db.system", "mysql")
    # Avoid logging entire SQL again (already in parent); just length
    db_span.set_attribute("db.statement_length", len(sql))
    # ... execute ...
```

- [ ] **Step 3: Smoke + verify attributes appear**

Run a derived query, check Jaeger UI for `schema.tables_matched` and `executor.row_count` attrs on the relevant spans.

- [ ] **Step 4: Commit**

```bash
git add agents/schema_mapper.py agents/executor.py
git commit -m "feat(tracing): schema_mapper top-K + executor metrics (Task 7 + Risk R2 mitigation — best-effort score extraction with scores_available flag)"
```

---

## Task 8: Verify IDRE service-name distinction (R1 mitigation)

**Files:** None modified; verification only.

R1 (Risk): V10 and IDRE both export to same Jaeger. Verify no collision.

- [ ] **Step 1: Trigger IDRE traffic + V10 traffic**

```bash
# IDRE: trigger by loading a page
curl -s -c /tmp/cj.txt "http://127.0.0.1:3000/api/dev/auto-login" -L -o /dev/null
curl -s -b /tmp/cj.txt "http://127.0.0.1:3000/dashboard" -o /dev/null

# V10: trigger via bot
py311 -c "
import os; os.environ['V10_OTEL_ENABLED'] = '1'
from harness_entrypoint import run_query_v10
run_query_v10('how many cases are pending RFI?')
" 2>&1 | tail -2
sleep 5
```

- [ ] **Step 2: Query Jaeger services API**

```bash
curl -s "http://localhost:16686/api/services" | py311 -c "import json,sys; print(json.dumps(json.load(sys.stdin), indent=2))"
```

Expected output includes BOTH:
- `v10-bot` (our service)
- IDRE's service (likely named `idre` or similar)

If only one appears → IDRE has no OTEL exporter actually firing (acceptable — V10 traces still work). If both appear → R1 mitigation verified.

- [ ] **Step 3: Document the outcome inline** in the next task's commit message.

---

## Task 9: Overhead measurement (R4 mitigation)

**Files:** None modified; measurement only.

R4 (Risk): `V10_OTEL_ENABLED=0` must result in <2% overhead. Verify.

- [ ] **Step 1: Run pytest baseline WITH tracing OFF**

```bash
cd /c/Users/anand/Downloads/local
V10_OTEL_ENABLED=0 py311 -m pytest testing/v10_harness/tests/test_baseline_derived_dom.py -v -k "DD_pending_rfi or DD_total_cases or DD_initial_elig" --tb=no 2>&1 | tail -3
```

Note total time T_off.

- [ ] **Step 2: Run same subset WITH tracing ON**

```bash
V10_OTEL_ENABLED=1 py311 -m pytest testing/v10_harness/tests/test_baseline_derived_dom.py -v -k "DD_pending_rfi or DD_total_cases or DD_initial_elig" --tb=no 2>&1 | tail -3
```

Note total time T_on.

- [ ] **Step 3: Compute delta**

If `(T_on - T_off) / T_off > 0.05` (5%): investigate. The `redact()` regex passes or per-attribute calls may be hot spots. Document.

If <2%: success.

- [ ] **Step 4: Document inline** in commit message at end of next task.

---

## Task 10: Smoke trace screenshot + done doc

**Files:** `local/docs/superpowers/reports/2026-05-19-otel-screenshot.md`

- [ ] **Step 1: Capture a representative trace**

In Jaeger UI:
1. Search service=`v10-bot`, operation=`v10.query`, last 1h
2. Pick a derived-path trace
3. Expand all spans
4. Take a screenshot showing the hierarchy + at least 3 spans with attributes visible

- [ ] **Step 2: Write the done doc**

Create `local/docs/superpowers/reports/2026-05-19-otel-screenshot.md`:

```markdown
# V10 OTEL Tracing — Done

**Date:** 2026-05-19
**Tag:** v10-otel-tracing

## What works
- Jaeger UI: http://localhost:16686 (in-memory)
- Service: `v10-bot`
- Trace hierarchy verified for both known + derived paths
- SQL Writer tool spans visible (8 tools instrumented)
- Schema Mapper attributes: tables_matched + (scores when available)
- IDRE OTEL coexistence: <document outcome from Task 8>
- Overhead delta (OTEL off vs on): <result from Task 9>

## Trace screenshot
(embed or describe; if image, save to docs/superpowers/reports/2026-05-19-otel.png and link)

## How to use
1. `bash scripts/snapshot/start_jaeger.sh` (idempotent)
2. Run any V10 query (CLI, Streamlit, pytest)
3. Browse http://localhost:16686

## How to disable
`export V10_OTEL_ENABLED=0` — decorators become identity (zero overhead verified).

## Risk mitigations verified
- R1 (IDRE service collision): <pass/fail>
- R2 (schema-mapper score extraction): scores_available=<true/false>
- R3 (Gemini tool registration): 8/8 tools register post-wrapping
- R4 (overhead disabled): <X%>
- R5 (Jaeger down tolerance): tested by stopping container — bot continues, exports fail silently
- R6 (PII redaction): email/phone/SSN redactor unit-tested
- R7 (Jaeger storage limit): documented; restart container clears
```

- [ ] **Step 3: Commit + tag**

```bash
cd /c/Users/anand/Downloads/local
git add docs/superpowers/reports/2026-05-19-otel-screenshot.md
git commit -m "docs: V10 OTEL tracing done — all 7 risks verified"
git tag -a v10-otel-tracing -m "V10 OTEL tracing complete — Jaeger + per-agent spans + tool spans"
git push origin main --tags
```

---

## Self-Review

**Spec coverage:** Walked spec section by section:
- §3.1 components (8 components instrumented) → Tasks 2-7
- §3.2 hierarchy → Tasks 3+4+5+6 produce it
- §3.3 attributes → Tasks 4 (standard) + 7 (custom)
- §3.4 redaction → Task 2 (in tracing.py with unit tests)
- §3.5 infrastructure → Task 1
- §4 risk mitigations → R1=Task 8, R2=Task 7, R3=Task 6, R4=Task 9, R5=Task 2 (BatchSpanProcessor async), R6=Task 2 (redact + unit tests), R7=Task 10 (documented)
- §7 DoD → Task 10

**Placeholder scan:** No TBD/TODO. The `<adjust to actual state key>` notes in Task 7 are acknowledged — engineer must read schema_mapper/executor state to find right key names. Fallback documented.

**Type consistency:** `@trace_agent`, `traced_tool_call`, `redact`, `get_tracer` consistent throughout. Span attribute names follow `<area>.<metric>` convention.

Self-review pass.

---

## Execution

Per session preference: subagent-driven. Plan ready to dispatch.
