# V10 OTEL Tracing — Design Spec

**Date:** 2026-05-19
**Status:** Approved for implementation planning
**Goal:** 100% per-query traceability for V10 bot via OpenTelemetry + local Jaeger.

## 1. Context

V10 currently emits a coarse `agent_trace` array in each response (agent name + status + summary) but lacks:
- Per-step timestamps (only total durations)
- GraphState snapshots at agent boundaries
- Tool-call traces inside SQL Writer (which of 8 tools, args, results)
- Decision rationale (e.g., schema_mapper picked 3 of 32 tables — which and why)
- A unified viewer

This spec adds OTEL-based tracing exporting to a local Jaeger instance, giving a full query timeline with drill-down per agent + per tool call.

Persistent user requirement (memory: `feedback_observability.md`): "100% traceability at micro level for all flows — source, destination, timestamps, every stage."

## 2. Success Bar

For any single bot query (known or derived path, via pytest/Streamlit/CLI):
- Jaeger UI shows a trace tree with root + child spans matching the hierarchy in §4
- Each agent span has start/end timestamps to millisecond precision
- Schema Mapper span lists selected tables (top-K) with retrieval scores
- SQL Writer span has one child span per Gemini tool invocation, with tool name + args + result-size
- Setting `V10_OTEL_ENABLED=0` (or unset) results in **zero added latency** (decorators no-op)
- IDRE's existing OTEL config is unaffected (no service-name collision; no exporter conflict)

## 3. Architecture

### 3.1 Components

| Component | Responsibility |
|---|---|
| `jaeger` Docker container | Receives OTLP/HTTP spans on :4318; serves UI on :16686; in-memory storage |
| `v10_reports_bot/tracing.py` | Initializes TracerProvider on import; exposes `@trace_agent` decorator + `traced_tool_call` context manager + `redact` helper |
| Each `agents/*.py` | One `@trace_agent("agent.name")` decorator on its `*_node` function |
| `agents/sql_writer.py` | Wraps each Gemini tool function with `traced_tool_call` |
| `harness_entrypoint.run_query_v10` | Creates root `v10.query` span with prompt + path |
| `agents/router.py` | Creates `v10.router.route` span with decision attributes |
| `agents/idre_api_client.py` | Creates `v10.known.api_call` span with cache hit/miss + IDRE HTTP status |
| `agents/executor.py` | Adds `v10.db.query` child span around SQL execution |

### 3.2 Span hierarchy

```
v10.query (root)
├── v10.router.route
├── v10.known.api_call                 (when path=known)
│   └── v10.known.idre_http_get
└── v10.derived.orchestrator           (when path=derived)
    ├── v10.agent.context_loader
    ├── v10.agent.ambiguity_scorer
    ├── v10.agent.clarification_agent
    ├── v10.agent.schema_mapper
    │   └── v10.retrieval.vector_bm25
    ├── v10.agent.platform_context
    ├── v10.agent.schema_verifier
    ├── v10.agent.sql_writer
    │   ├── v10.gemini.call (N for tool loop)
    │   ├── v10.tool.<name> (per tool invocation)
    │   └── v10.tool.<name>
    ├── v10.agent.sql_validator
    ├── v10.agent.executor
    │   └── v10.db.query
    ├── v10.agent.debugger (on retry)
    ├── v10.agent.post_processor
    └── v10.agent.response_formatter
```

### 3.3 Span attributes (per agent)

Standard attributes for every agent span:
- `agent.name` (str): canonical agent name
- `agent.status` (str): ok / warn / fail
- `agent.input_keys` (str[]): GraphState keys read (NOT full values)
- `agent.output_keys` (str[]): GraphState keys written or modified
- `agent.summary` (str): same one-line summary as in `agent_trace`

Custom attributes by agent:
- `ambiguity_scorer`: `ambiguity.score`, `ambiguity.flags` (str[]), `ambiguity.threshold`
- `clarification_agent`: `clarification.needed` (bool), `clarification.auto_answered` (bool)
- `schema_mapper`: `schema.tables_matched` (str[]), `schema.k`, `schema.scores` (float[] if exposable)
- `sql_writer`: `sql_writer.tools_called` (str[]), `sql_writer.tool_call_count`, `sql_writer.final_sql_length`
- `sql_validator`: `validation.errors` (str[]) if any
- `executor`: `executor.row_count`, `executor.elapsed_ms`, `executor.was_cached` (bool)
- `debugger`: `debugger.retry_count`, `debugger.error_class`

### 3.4 Sensitive data redaction

`v10_reports_bot/tracing.py:redact(text)` strips:
- Email addresses → `<email>`
- Phone numbers (10+ consecutive digits) → `<phone>`
- SSN-like patterns (3-2-4 digits) → `<ssn>`

Applied to: any free-text attribute that might contain user data (prompt, summary, SQL parameters if logged). NOT applied to: SQL text (we WANT to see it for diagnostics), table/column names, status enum values.

Result rows are never logged into spans — only `row_count` recorded.

### 3.5 Infrastructure

- Jaeger all-in-one: `docker run -d --name jaeger -p 16686:16686 -p 4317:4317 -p 4318:4318 jaegertracing/all-in-one:1.61`
- OTLP HTTP exporter to `http://localhost:4318/v1/traces`
- Service name: `v10-bot` (distinct from IDRE's `idre`)
- In-memory storage (Jaeger default); restart container to clear

## 4. Risk Mitigations (designed-in)

| Risk | Mitigation (will be implementation step) |
|---|---|
| **R1: IDRE OTEL conflict** — both V10 bot and IDRE export to same Jaeger endpoint; risk of overlapping service-name = "default" | Set `service.name=v10-bot` on V10's TracerProvider via Resource attributes; verify IDRE keeps its existing service name (likely `idre`). After install, check Jaeger UI — both services should appear in dropdown. Plan task explicitly verifies this. |
| **R2: Schema Mapper top-K scores not exposable** — if the embedding library doesn't expose scores cleanly, span attributes become empty | Implementation pattern: try-import-and-extract; fall back to recording table names only (without scores). Span attribute `schema.scores_available: bool` documents which case occurred. No crash. |
| **R3: Gemini tool decorators must not break function-declarations** — wrapping tool fns must preserve signature/docstring/annotations so Gemini's `genai.protos.Tool` registration still parses correctly | Use `functools.wraps` on the traced_tool_call wrapper. Plan task includes a pre-flight smoke test: after wrapping, call `_build_gemini_tools()` and assert all 8 tools register without error. If any fail, revert that tool's wrapping and document. |
| **R4: Performance overhead when `V10_OTEL_ENABLED=False`** — decorators must be true no-ops | Implementation: decorator factory checks env var ONCE on import; if disabled, returns identity decorator. Plan includes a timing test comparing pytest baseline with OTEL on vs off (target: <2% delta). |
| **R5: Jaeger not running** — bot must not crash | OTLP exporter has its own timeout/retry config; bot must catch any export error and continue. Implementation uses `BatchSpanProcessor` (async export) — failed exports are dropped silently. |
| **R6: PII leakage into spans** — staging snapshot has real client data | `redact()` helper applied at all free-text attribute set sites. Code review explicitly checks any place a span attribute is set from user data. SQL strings exempted (necessary for diagnostics). |
| **R7: Trace volume blowing out memory** — Jaeger in-memory storage default ~50K traces | Document the limit; restart Jaeger container clears it. If running long-baseline (150+ tests), restart between runs. Future: switch to Tempo + S3 if needed (out of scope). |

## 5. Components Detail

### 5.1 `v10_reports_bot/tracing.py`
```python
import os
from contextlib import contextmanager
from functools import wraps
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME

_OTEL_ENABLED = os.environ.get("V10_OTEL_ENABLED", "1").lower() in ("1", "true", "yes")

if _OTEL_ENABLED:
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: "v10-bot"}))
    exporter = OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

_tracer = trace.get_tracer("v10.bot")


def trace_agent(name: str):
    """Decorator for agent_node functions. Wraps in OTEL span."""
    if not _OTEL_ENABLED:
        return lambda fn: fn  # zero-cost no-op
    def deco(fn):
        @wraps(fn)
        def wrapped(state):
            with _tracer.start_as_current_span(name) as span:
                if isinstance(state, dict):
                    span.set_attribute("agent.input_keys", list(state.keys())[:50])
                result = fn(state)
                # Compute output_keys diff (only keys that changed/added)
                if isinstance(result, dict) and isinstance(state, dict):
                    changed = [k for k in result if k not in state or result[k] != state.get(k)]
                    span.set_attribute("agent.output_keys", changed[:50])
                # If agent_trace was appended, pull the last entry's summary
                if isinstance(result, dict) and "agent_trace" in result:
                    trace_list = result["agent_trace"]
                    if trace_list and isinstance(trace_list[-1], dict):
                        last = trace_list[-1]
                        if "status" in last: span.set_attribute("agent.status", last["status"])
                        if "summary" in last: span.set_attribute("agent.summary", redact(last["summary"][:500]))
                return result
        return wrapped
    return deco


@contextmanager
def traced_tool_call(tool_name: str):
    """Context manager for SQL Writer's tool calls."""
    if not _OTEL_ENABLED:
        yield
        return
    with _tracer.start_as_current_span(f"v10.tool.{tool_name}") as span:
        span.set_attribute("tool.name", tool_name)
        yield span


def redact(text: str) -> str:
    """Strip emails, phones, SSNs from free-text span attributes."""
    import re
    if not isinstance(text, str): return text
    text = re.sub(r'[\w.+-]+@[\w-]+\.[\w.-]+', '<email>', text)
    text = re.sub(r'\b\d{10,}\b', '<phone>', text)
    text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '<ssn>', text)
    return text


def get_tracer():
    return _tracer
```

### 5.2 Agent instrumentation pattern

Each agent file gets one decorator line:
```python
# agents/ambiguity_scorer.py
from tracing import trace_agent

@trace_agent("v10.agent.ambiguity_scorer")
def ambiguity_scorer_node(state):
    # existing implementation unchanged
    ...
```

### 5.3 SQL Writer tool tracing

```python
# agents/sql_writer.py
from tracing import traced_tool_call

# When dispatching a Gemini tool call:
def _dispatch_tool(name, args):
    with traced_tool_call(name) as span:
        span.set_attribute("tool.args_keys", list(args.keys()))
        result = ACTUAL_TOOL_FUNCTIONS[name](**args)
        span.set_attribute("tool.result_size", len(str(result)))
        return result
```

### 5.4 Jaeger setup

One-shot launcher script: `scripts/snapshot/start_jaeger.sh`
```bash
#!/bin/bash
docker run -d --name v10-jaeger --restart unless-stopped \
  -p 16686:16686 -p 4317:4317 -p 4318:4318 \
  jaegertracing/all-in-one:1.61
echo "Jaeger UI: http://localhost:16686"
```

## 6. Out of Scope

- Metrics export (request rate, error rate, p99)
- Production-grade trace storage (Tempo + S3)
- Sampling — always-on at 100%
- Cross-process correlation with IDRE's OTEL (both export to same Jaeger but with different service names; correlation would require trace propagation through HTTP headers, which IDRE doesn't currently support inbound)
- Custom Jaeger UI panels / dashboards
- Alerting / SLO tracking

## 7. Definition of Done

- Jaeger container running, reachable at `http://localhost:16686`
- `v10_reports_bot/tracing.py` exists with `@trace_agent`, `traced_tool_call`, `redact`
- All 10+ agent `*_node` functions decorated
- SQL Writer's tool dispatch wrapped
- Router + IDRE API client + Executor have spans
- Running `pytest testing/v10_harness/tests/test_baseline_derived_dom.py -v -k DD_pending_rfi` produces a trace visible in Jaeger UI with full hierarchy
- Schema Mapper span lists tables_matched (and scores if exposable; else `schema.scores_available=False`)
- All 8 SQL Writer tools register cleanly with Gemini after wrapping (verification step in plan)
- `V10_OTEL_ENABLED=0` produces baseline runtime within 2% of pre-instrumentation
- Smoke trace screenshot saved to `docs/superpowers/reports/2026-05-19-otel-screenshot.md`
- Tag `v10-otel-tracing` applied
