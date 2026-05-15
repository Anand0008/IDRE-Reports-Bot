# V10 IDRE Reports Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace V7/V8/V9 with V10 — a two-path bot (IDRE-API for known reports, MCP-tool SQL for derived queries) that achieves byte-equal output to IDRE on known reports and exact-match results on derived queries, validated by a result-comparison test harness anchored to staging.

**Architecture:** Test harness built first (no other change is measurable without it). Then a staging-anchored knowledge pipeline. Then a router that dispatches to either an IDRE API wrapper layer or a rewritten MCP-tool SQL writer. All deterministically connected; no embeddings, no RAG, no heuristic SQL scoring.

**Tech Stack:** Python 3.11, LangGraph, Google Gemini 2.5 Pro, SQLAlchemy + mysql-connector-python, pytest, Streamlit (existing). Bot lives in `C:\Users\anand\Downloads\v10_reports_bot\`; harness in `C:\Users\anand\Downloads\local\testing\v10_harness\`; knowledge pipeline in `C:\Users\anand\Downloads\local\scripts\build_knowledge\`.

**Spec:** `docs/superpowers/specs/2026-05-15-v10-reports-bot-design.md`

**Environment reminders:**
- IDRE local dev server runs on `localhost:3000` via **webpack** (`npx next dev` — NOT `pnpm dev` / Turbopack; Node v25.3.0 crashes Turbopack)
- `tsx` scripts in `testing/` need `NODE_PATH=C:\Users\anand\Downloads\local\idre\node_modules` prefix
- Use Python 3.11 (`C:/Users/anand/AppData/Local/Programs/Python/Python311/python.exe`) — it has python-docx and openpyxl
- Staging RDS credentials live in V8's `.env` (copy into V10's `.env` at Day 5)

---

## File Structure

**V10 bot directory** (`C:\Users\anand\Downloads\v10_reports_bot\`):

| Path | Status | Responsibility |
|---|---|---|
| `agents/router.py` | NEW | Component 1: routes queries to known or derived path |
| `agents/idre_api_client.py` | NEW | Component 2: typed wrappers for 14 IDRE report endpoints |
| `agents/parameter_extractor.py` | NEW | Component 2: NL params → IDRE API query params |
| `agents/response_normalizer.py` | NEW | Component 2: flatten IDRE responses to canonical row format |
| `agents/sql_writer.py` | MODIFIED from V8 | Rewritten system prompt; removed metric_cards/sql_templates; uses new tools |
| `agents/schema_verifier.py` | MODIFIED from V8 | Remove `_COMMONLY_HALLUCINATED` dict |
| `agents/executor.py` | MODIFIED from V8 | Row cap 50K → 100K production; bypass cap in tests |
| `agents/ambiguity_scorer.py` | COPIED from V8 | unchanged |
| `agents/clarification_agent.py` | COPIED from V8 | unchanged |
| `agents/context_loader.py` | COPIED from V8 | unchanged |
| `agents/debugger_agent.py` | COPIED from V8 | unchanged |
| `agents/feedback_injector.py` | COPIED from V8 | unchanged |
| `agents/output_formatter.py` | COPIED from V8 | unchanged |
| `agents/platform_context_agent.py` | COPIED from V8 | unchanged |
| `agents/post_processor.py` | COPIED from V8 | unchanged |
| `agents/response_formatter.py` | COPIED from V8 | unchanged |
| `agents/schema_mapper.py` | COPIED from V8 | unchanged |
| `agents/sql_validator.py` | COPIED from V8 | unchanged |
| `tools/idre_tools.py` | MODIFIED from V8 | 8-tool catalog (5 kept, 3 new); reads from `knowledge/v10/` |
| `knowledge/v10/` | NEW DIR | Filled by Component 4 pipeline |
| `config/route_signatures.json` | NEW | Component 1's 14 RouteSignature entries |
| `config/settings.py` | COPIED from V8 | unchanged |
| `config/business_glossary.json` | COPIED from V8 | manual for V10 |
| `state/context.py` | MODIFIED from V8 | Add `now_anchor`, `router_decision`, `idre_api_response` fields |
| `app.py` | MODIFIED from V8 | LangGraph wiring with Router as first node after context_loader |
| `.env` | NEW | Copy V8's credentials |

**Knowledge pipeline** (`C:\Users\anand\Downloads\local\scripts\build_knowledge\`):

| Path | Status |
|---|---|
| `01_sync_staging.py` | NEW |
| `02_extract_reference_cards.py` | NEW |
| `03_extract_schema.py` | NEW |
| `04_extract_enums.py` | NEW |
| `05_extract_business_logic.py` | NEW |
| `06_validate_pipeline.py` | NEW |
| `run_all.py` | NEW |

**Test harness** (`C:\Users\anand\Downloads\local\testing\v10_harness\`):

| Path | Status |
|---|---|
| `conftest.py` | NEW |
| `temporality.py` | NEW |
| `compare.py` | NEW |
| `measurements.py` | NEW |
| `runner.py` | NEW |
| `run_tests.py` | NEW |
| `test_set.jsonl` | NEW |
| `tests/test_known_reports.py` | NEW |
| `tests/test_derived_queries.py` | NEW |

---

## Day 0: Preliminaries (do once before Day 1)

### Task 0.1: Initialize git repo for planning artifacts

**Files:**
- Create: `C:\Users\anand\Downloads\local\.gitignore`

- [ ] **Step 1: Initialize repo and configure**

```bash
cd /c/Users/anand/Downloads/local
git init
git config user.email "anand.wankhade@telomeregs.com"
git config user.name "Anand Wankhade"
```

- [ ] **Step 2: Write .gitignore**

Create `C:\Users\anand\Downloads\local\.gitignore`:

```gitignore
# Bot version directories live separately, not in this repo
idre/
testing/sql-compare/chrome-cdp-profile/
testing/sql-compare/sql-captures/
testing/sql-compare/__pycache__/

# Generated test artifacts
testing/v10_harness/reports/
testing/ultimate_v2/
testing/ultimate_comparison/

# Knowledge pipeline outputs (versioned separately if needed)
scripts/build_knowledge/__pycache__/

# Python
__pycache__/
*.pyc
.venv/

# Secrets
*.env
!.env.example

# IDE
.vscode/
.idea/
```

- [ ] **Step 3: Initial commit of spec + plan**

```bash
git add docs/superpowers/specs/2026-05-15-v10-reports-bot-design.md
git add docs/superpowers/plans/2026-05-15-v10-reports-bot-plan.md
git add .gitignore
git commit -m "chore: initialize V10 planning artifacts"
```

### Task 0.2: Verify Python 3.11 environment

- [ ] **Step 1: Verify Python and required packages**

Run:
```bash
/c/Users/anand/AppData/Local/Programs/Python/Python311/python.exe -c "import docx, openpyxl, sqlalchemy, mysql.connector, pydantic, pydantic_settings, requests, pytest, google.generativeai; print('all imports OK')"
```

Expected: `all imports OK`

If anything is missing:
```bash
/c/Users/anand/AppData/Local/Programs/Python/Python311/python.exe -m pip install python-docx openpyxl sqlalchemy mysql-connector-python pydantic pydantic-settings requests pytest google-generativeai
```

- [ ] **Step 2: Create a `py311` alias** in your shell rc (`~/.bashrc`) so the rest of the plan is shorter:

```bash
echo "alias py311='/c/Users/anand/AppData/Local/Programs/Python/Python311/python.exe'" >> ~/.bashrc
source ~/.bashrc
py311 --version
```

Expected: `Python 3.11.x`

### Task 0.3: Verify staging RDS reachability

- [ ] **Step 1: Test connection**

```bash
py311 -c "
import os
os.chdir('/c/Users/anand/Downloads/v8_reports_bot')
from db.connector import test_connection
print('OK' if test_connection() else 'FAIL')
"
```

Expected: `OK`

If FAIL: check that V8's `.env` exists and `global-bundle.pem` is present.

### Task 0.4: Verify IDRE local dev server runs

- [ ] **Step 1: Start IDRE locally (webpack mode)**

In a separate terminal:
```bash
cd /c/Users/anand/Downloads/local/idre
npx next dev
```

Expected: `Ready in <time> ms` on `http://localhost:3000`. Leave this running for the rest of the plan.

- [ ] **Step 2: Verify dev auto-login works**

```bash
curl -i -L http://localhost:3000/api/dev/auto-login
```

Expected: HTTP 200 or 302 redirect to `/`. Cookie `session=...` should be set.

- [ ] **Step 3: Verify one report endpoint responds**

```bash
curl -s --cookie-jar /tmp/idre_cookies.txt http://localhost:3000/api/dev/auto-login -o /dev/null
curl -s --cookie /tmp/idre_cookies.txt "http://localhost:3000/api/reports/dashboard-stats" | head -c 500
```

Expected: JSON response starting with `{` (not an HTML login page).

---

## Day 1: Test Harness Skeleton + 10 Known-Report Tests

The harness MUST exist before any bot change. Without it we cannot tell if any change helps.

### Task 1.1: Create test harness directory and `__init__` files

**Files:**
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\__init__.py`
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\tests\__init__.py`
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\reports\.gitkeep`

- [ ] **Step 1: Create directories**

```bash
mkdir -p /c/Users/anand/Downloads/local/testing/v10_harness/tests
mkdir -p /c/Users/anand/Downloads/local/testing/v10_harness/reports
touch /c/Users/anand/Downloads/local/testing/v10_harness/__init__.py
touch /c/Users/anand/Downloads/local/testing/v10_harness/tests/__init__.py
touch /c/Users/anand/Downloads/local/testing/v10_harness/reports/.gitkeep
```

- [ ] **Step 2: Verify**

```bash
ls /c/Users/anand/Downloads/local/testing/v10_harness/
```

Expected: `__init__.py  reports  tests`

- [ ] **Step 3: Commit**

```bash
cd /c/Users/anand/Downloads/local
git add testing/v10_harness/
git commit -m "feat(harness): create v10 test harness directory skeleton"
```

### Task 1.2: Write `temporality.py` — :now anchoring

**Files:**
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\temporality.py`
- Test: `C:\Users\anand\Downloads\local\testing\v10_harness\tests\test_temporality.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_temporality.py`:

```python
from datetime import datetime, timezone
from testing.v10_harness.temporality import NowAnchor


def test_now_anchor_freezes_a_single_timestamp():
    anchor = NowAnchor.lock_from_value(datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc))
    assert anchor.now() == datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
    # Repeated calls return the same value
    assert anchor.now() == anchor.now()


def test_now_anchor_parameterizes_sql_with_now_marker():
    anchor = NowAnchor.lock_from_value(datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc))
    sql = "SELECT COUNT(*) FROM `case` WHERE createdAt >= :now"
    bound = anchor.bind_sql(sql)
    assert bound["sql"] == "SELECT COUNT(*) FROM `case` WHERE createdAt >= %(now)s"
    assert bound["params"] == {"now": datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)}


def test_now_anchor_handles_no_now_marker():
    anchor = NowAnchor.lock_from_value(datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc))
    sql = "SELECT COUNT(*) FROM `case`"
    bound = anchor.bind_sql(sql)
    assert bound["sql"] == "SELECT COUNT(*) FROM `case`"
    assert bound["params"] == {}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /c/Users/anand/Downloads/local
py311 -m pytest testing/v10_harness/tests/test_temporality.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'testing.v10_harness.temporality'`

- [ ] **Step 3: Write minimal implementation**

Create `testing/v10_harness/temporality.py`:

```python
"""Locks a single :now timestamp for the duration of one test."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.engine import Engine
from sqlalchemy import text


@dataclass(frozen=True)
class NowAnchor:
    _now: datetime

    @classmethod
    def lock_from_value(cls, value: datetime) -> "NowAnchor":
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return cls(_now=value)

    @classmethod
    def lock_from_db(cls, engine: Engine) -> "NowAnchor":
        with engine.connect() as conn:
            row = conn.execute(text("SELECT UTC_TIMESTAMP() AS n")).mappings().one()
        n = row["n"]
        if n.tzinfo is None:
            n = n.replace(tzinfo=timezone.utc)
        return cls(_now=n)

    def now(self) -> datetime:
        return self._now

    def bind_sql(self, sql: str) -> dict[str, Any]:
        """Convert :now markers into mysql-connector named params."""
        if ":now" not in sql:
            return {"sql": sql, "params": {}}
        bound_sql = sql.replace(":now", "%(now)s")
        return {"sql": bound_sql, "params": {"now": self._now}}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
py311 -m pytest testing/v10_harness/tests/test_temporality.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add testing/v10_harness/temporality.py testing/v10_harness/tests/test_temporality.py
git commit -m "feat(harness): add NowAnchor for :now-parameterized SQL"
```

### Task 1.3: Write `compare.py` — result comparison

**Files:**
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\compare.py`
- Test: `C:\Users\anand\Downloads\local\testing\v10_harness\tests\test_compare.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_compare.py`:

```python
from testing.v10_harness.compare import (
    compare_row_sets,
    compare_aggregates,
    compare_json_at_paths,
    Verdict,
)


def test_compare_row_sets_exact_match():
    bot = [{"caseId": 1, "status": "OPEN"}, {"caseId": 2, "status": "CLOSED"}]
    expected = [{"caseId": 2, "status": "CLOSED"}, {"caseId": 1, "status": "OPEN"}]
    result = compare_row_sets(bot, expected)
    assert result.verdict == Verdict.PASS
    assert result.diff == []


def test_compare_row_sets_missing_row():
    bot = [{"caseId": 1}]
    expected = [{"caseId": 1}, {"caseId": 2}]
    result = compare_row_sets(bot, expected)
    assert result.verdict == Verdict.FAIL
    assert any("missing" in d.lower() for d in result.diff)


def test_compare_row_sets_extra_row():
    bot = [{"caseId": 1}, {"caseId": 99}]
    expected = [{"caseId": 1}]
    result = compare_row_sets(bot, expected)
    assert result.verdict == Verdict.FAIL
    assert any("extra" in d.lower() for d in result.diff)


def test_compare_aggregates_exact():
    result = compare_aggregates({"total": 100, "sum": 250.50}, {"total": 100, "sum": 250.50})
    assert result.verdict == Verdict.PASS


def test_compare_aggregates_float_tolerance():
    result = compare_aggregates({"sum": 100.001}, {"sum": 100.005}, float_tolerance=0.01)
    assert result.verdict == Verdict.PASS


def test_compare_aggregates_float_outside_tolerance():
    result = compare_aggregates({"sum": 100.0}, {"sum": 101.0}, float_tolerance=0.01)
    assert result.verdict == Verdict.FAIL


def test_compare_aggregates_int_mismatch_no_tolerance():
    result = compare_aggregates({"total": 100}, {"total": 101})
    assert result.verdict == Verdict.FAIL


def test_compare_json_at_paths_basic():
    bot = {"data": {"cases": [{"id": "a"}, {"id": "b"}], "totalCount": 2}}
    expected = {"data": {"cases": [{"id": "b"}, {"id": "a"}], "totalCount": 2}}
    result = compare_json_at_paths(
        bot, expected,
        ["data.totalCount", "data.cases[*].id"],
    )
    assert result.verdict == Verdict.PASS


def test_compare_json_at_paths_mismatch():
    bot = {"data": {"totalCount": 5}}
    expected = {"data": {"totalCount": 10}}
    result = compare_json_at_paths(bot, expected, ["data.totalCount"])
    assert result.verdict == Verdict.FAIL
```

- [ ] **Step 2: Run test to verify it fails**

```bash
py311 -m pytest testing/v10_harness/tests/test_compare.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write implementation**

Create `testing/v10_harness/compare.py`:

```python
"""Result comparison primitives. NO keyword scoring — only result equality."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"


@dataclass
class CompareResult:
    verdict: Verdict
    diff: list[str] = field(default_factory=list)


def _row_signature(row: dict) -> tuple:
    return tuple(sorted((k, _hash_value(v)) for k, v in row.items()))


def _hash_value(v: Any) -> Any:
    if isinstance(v, list):
        return tuple(_hash_value(x) for x in v)
    if isinstance(v, dict):
        return tuple(sorted((k, _hash_value(val)) for k, val in v.items()))
    return v


def compare_row_sets(bot: list[dict], expected: list[dict]) -> CompareResult:
    """Set-equality between two lists of dict rows. Order ignored."""
    if len(bot) != len(expected):
        return CompareResult(
            Verdict.FAIL,
            [f"Row count mismatch: bot={len(bot)} expected={len(expected)}"],
        )
    bot_sigs = sorted(_row_signature(r) for r in bot)
    exp_sigs = sorted(_row_signature(r) for r in expected)
    if bot_sigs == exp_sigs:
        return CompareResult(Verdict.PASS)
    bot_set = set(bot_sigs)
    exp_set = set(exp_sigs)
    diff = []
    missing = exp_set - bot_set
    extra = bot_set - exp_set
    if missing:
        diff.append(f"Bot missing {len(missing)} expected row(s); first: {list(missing)[0]}")
    if extra:
        diff.append(f"Bot has {len(extra)} extra row(s); first: {list(extra)[0]}")
    return CompareResult(Verdict.FAIL, diff)


def compare_aggregates(
    bot: dict[str, Any],
    expected: dict[str, Any],
    float_tolerance: float = 0.0,
) -> CompareResult:
    """Compare aggregate dicts. Ints exact; floats within tolerance."""
    diff = []
    for key, exp_val in expected.items():
        if key not in bot:
            diff.append(f"Missing key: {key}")
            continue
        bot_val = bot[key]
        if isinstance(exp_val, float) or isinstance(bot_val, float):
            if abs(float(bot_val) - float(exp_val)) > float_tolerance:
                diff.append(f"{key}: bot={bot_val} expected={exp_val} (tol={float_tolerance})")
        else:
            if bot_val != exp_val:
                diff.append(f"{key}: bot={bot_val!r} expected={exp_val!r}")
    return CompareResult(Verdict.FAIL if diff else Verdict.PASS, diff)


def _extract_path(obj: Any, path: str) -> list:
    """Extract values from `obj` using a dotted path with `[*]` for array fanout."""
    parts = path.split(".")
    current = [obj]
    for part in parts:
        next_level = []
        for item in current:
            if part.endswith("[*]"):
                key = part[:-3]
                arr = item.get(key, []) if isinstance(item, dict) else []
                next_level.extend(arr if isinstance(arr, list) else [])
            else:
                if isinstance(item, dict):
                    next_level.append(item.get(part))
        current = next_level
    return current


def compare_json_at_paths(
    bot: dict, expected: dict, paths: list[str]
) -> CompareResult:
    """Compare two JSON responses at a list of dotted paths."""
    diff = []
    for path in paths:
        bot_vals = _extract_path(bot, path)
        exp_vals = _extract_path(expected, path)
        # Order-independent for array fanouts
        if "[*]" in path:
            if sorted(map(repr, bot_vals)) != sorted(map(repr, exp_vals)):
                diff.append(
                    f"Path {path}: bot has {len(bot_vals)} values, "
                    f"expected {len(exp_vals)} values; sets differ"
                )
        else:
            if bot_vals != exp_vals:
                diff.append(f"Path {path}: bot={bot_vals} expected={exp_vals}")
    return CompareResult(Verdict.FAIL if diff else Verdict.PASS, diff)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
py311 -m pytest testing/v10_harness/tests/test_compare.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add testing/v10_harness/compare.py testing/v10_harness/tests/test_compare.py
git commit -m "feat(harness): add result comparison primitives (no keyword scoring)"
```

### Task 1.4: Write `measurements.py` — informational only

**Files:**
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\measurements.py`
- Test: `C:\Users\anand\Downloads\local\testing\v10_harness\tests\test_measurements.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_measurements.py`:

```python
import time
from testing.v10_harness.measurements import Measurement, measure


def test_measurement_records_latency():
    with measure() as m:
        time.sleep(0.01)
    assert m.latency_ms >= 10
    assert m.latency_ms < 100  # not absurdly slow


def test_measurement_records_tokens():
    with measure() as m:
        m.record_tokens(prompt=100, completion=50)
    assert m.tokens.prompt == 100
    assert m.tokens.completion == 50
    assert m.tokens.total == 150


def test_measurement_serializes_to_dict():
    with measure() as m:
        m.record_tokens(prompt=10, completion=5)
    d = m.to_dict()
    assert "latency_ms" in d
    assert d["tokens"]["total"] == 15
```

- [ ] **Step 2: Run test, verify fail**

```bash
py311 -m pytest testing/v10_harness/tests/test_measurements.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implementation**

Create `testing/v10_harness/measurements.py`:

```python
"""Records latency and token usage. INFORMATIONAL ONLY — no budget enforcement in V10."""
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class TokenUsage:
    prompt: int = 0
    completion: int = 0

    @property
    def total(self) -> int:
        return self.prompt + self.completion


@dataclass
class Measurement:
    latency_ms: float = 0.0
    tokens: TokenUsage = field(default_factory=TokenUsage)
    llm_calls: int = 0

    def record_tokens(self, prompt: int = 0, completion: int = 0) -> None:
        self.tokens.prompt += prompt
        self.tokens.completion += completion

    def record_llm_call(self) -> None:
        self.llm_calls += 1

    def to_dict(self) -> dict:
        return {
            "latency_ms": round(self.latency_ms, 1),
            "tokens": {
                "prompt": self.tokens.prompt,
                "completion": self.tokens.completion,
                "total": self.tokens.total,
            },
            "llm_calls": self.llm_calls,
        }


@contextmanager
def measure() -> Iterator[Measurement]:
    m = Measurement()
    start = time.monotonic()
    try:
        yield m
    finally:
        m.latency_ms = (time.monotonic() - start) * 1000
```

- [ ] **Step 4: Run test, verify pass**

```bash
py311 -m pytest testing/v10_harness/tests/test_measurements.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add testing/v10_harness/measurements.py testing/v10_harness/tests/test_measurements.py
git commit -m "feat(harness): add Measurement context manager (informational)"
```

### Task 1.5: Write `conftest.py` — shared fixtures

**Files:**
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\conftest.py`

- [ ] **Step 1: Create fixtures**

```python
"""Pytest fixtures: staging RDS engine, IDRE session, now anchor."""
import os
import sys
from pathlib import Path
import pytest
import requests
from sqlalchemy.engine import Engine

# Make V8/V10 bot importable from harness
V8_BOT = Path("C:/Users/anand/Downloads/v8_reports_bot")
V10_BOT = Path("C:/Users/anand/Downloads/v10_reports_bot")
LOCAL_ROOT = Path("C:/Users/anand/Downloads/local")

for p in [V10_BOT, V8_BOT, LOCAL_ROOT]:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))


@pytest.fixture(scope="session")
def staging_engine() -> Engine:
    """Connect to staging RDS via V8's connector (same creds)."""
    os.chdir(str(V8_BOT))  # so V8's .env resolves
    from db.connector import get_engine
    eng = get_engine()
    # smoke test
    with eng.connect() as c:
        from sqlalchemy import text
        c.execute(text("SELECT 1"))
    return eng


@pytest.fixture(scope="session")
def idre_session() -> requests.Session:
    """Authenticated session against localhost:3000 IDRE."""
    s = requests.Session()
    r = s.get("http://localhost:3000/api/dev/auto-login", allow_redirects=True, timeout=30)
    if r.status_code >= 400:
        pytest.skip(f"IDRE local server not reachable: HTTP {r.status_code}")
    return s


@pytest.fixture
def now_anchor(staging_engine: Engine):
    from testing.v10_harness.temporality import NowAnchor
    return NowAnchor.lock_from_db(staging_engine)
```

- [ ] **Step 2: Run a smoke pytest to verify conftest loads**

```bash
cd /c/Users/anand/Downloads/local
py311 -m pytest testing/v10_harness/tests/ -v --collect-only
```

Expected: tests collect successfully (existing temporality/compare/measurements tests still listed).

- [ ] **Step 3: Commit**

```bash
git add testing/v10_harness/conftest.py
git commit -m "feat(harness): add pytest fixtures for staging RDS + IDRE session"
```

### Task 1.6: Write `runner.py` — per-prompt execution

**Files:**
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\runner.py`
- Test: `C:\Users\anand\Downloads\local\testing\v10_harness\tests\test_runner.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_runner.py`:

```python
import pytest
from testing.v10_harness.runner import TestRecord, run_known_report_test, run_derived_query_test


def test_test_record_parses_known_report_entry():
    entry = {
        "id": "K_due_001",
        "category": "known-report",
        "report": "due-dates",
        "prompt": "list overdue cases",
        "expected_idre_call": {"method": "GET", "path": "/api/reports/due-dates", "query": {"urgency": "overdue"}},
        "compare_fields": ["data.totalCount"],
        "temporality": "variant",
    }
    rec = TestRecord.from_dict(entry)
    assert rec.id == "K_due_001"
    assert rec.category == "known-report"
    assert rec.report == "due-dates"


def test_test_record_parses_derived_entry():
    entry = {
        "id": "D_total_001",
        "category": "derived-query",
        "prompt": "how many cases are there",
        "ground_truth_sql": [{"name": "total", "sql": "SELECT COUNT(*) AS v FROM `case`"}],
        "bot_must_return_keys": ["total"],
        "temporality": "stable",
    }
    rec = TestRecord.from_dict(entry)
    assert rec.id == "D_total_001"
    assert rec.category == "derived-query"
    assert rec.ground_truth_sql[0]["name"] == "total"


def test_test_record_rejects_unknown_category():
    with pytest.raises(ValueError, match="unknown category"):
        TestRecord.from_dict({"id": "X", "category": "bogus", "prompt": "x"})
```

- [ ] **Step 2: Run, verify fail**

```bash
py311 -m pytest testing/v10_harness/tests/test_runner.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implementation**

Create `testing/v10_harness/runner.py`:

```python
"""Test record schema + per-prompt execution orchestration."""
from dataclasses import dataclass, field
from typing import Any, Callable
from sqlalchemy.engine import Engine
from sqlalchemy import text
import requests

from testing.v10_harness.temporality import NowAnchor
from testing.v10_harness.compare import (
    Verdict, CompareResult,
    compare_json_at_paths, compare_aggregates,
)
from testing.v10_harness.measurements import Measurement, measure


VALID_CATEGORIES = {"known-report", "derived-query"}


@dataclass
class TestRecord:
    id: str
    category: str
    prompt: str
    report: str | None = None
    expected_idre_call: dict | None = None
    compare_fields: list[str] = field(default_factory=list)
    ground_truth_sql: list[dict] = field(default_factory=list)
    bot_must_return_keys: list[str] = field(default_factory=list)
    temporality: str = "variant"  # "variant" | "stable"
    notes: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "TestRecord":
        if d.get("category") not in VALID_CATEGORIES:
            raise ValueError(f"unknown category: {d.get('category')}")
        return cls(
            id=d["id"],
            category=d["category"],
            prompt=d["prompt"],
            report=d.get("report"),
            expected_idre_call=d.get("expected_idre_call"),
            compare_fields=d.get("compare_fields", []),
            ground_truth_sql=d.get("ground_truth_sql", []),
            bot_must_return_keys=d.get("bot_must_return_keys", []),
            temporality=d.get("temporality", "variant"),
            notes=d.get("notes", ""),
        )


@dataclass
class TestResult:
    record: TestRecord
    verdict: Verdict
    diffs: list[str]
    bot_measurement: dict
    harness_measurement: dict
    bot_payload: Any = None
    expected_payload: Any = None

    def to_dict(self) -> dict:
        return {
            "id": self.record.id,
            "category": self.record.category,
            "verdict": self.verdict.value,
            "diffs": self.diffs,
            "bot_measurement": self.bot_measurement,
            "harness_measurement": self.harness_measurement,
        }


def run_known_report_test(
    record: TestRecord,
    bot_runner: Callable[[str, NowAnchor], dict],
    idre_session: requests.Session,
    now_anchor: NowAnchor,
    idre_base_url: str = "http://localhost:3000",
) -> TestResult:
    """Run a known-report test. Calls bot AND IDRE in parallel-equivalent fashion."""
    # Bot path
    with measure() as bot_m:
        bot_response = bot_runner(record.prompt, now_anchor)

    # Ground-truth path
    call = record.expected_idre_call or {}
    with measure() as harness_m:
        resp = idre_session.request(
            method=call.get("method", "GET"),
            url=f"{idre_base_url}{call.get('path', '')}",
            params=call.get("query", {}),
            timeout=300,
        )
        expected = resp.json() if resp.status_code == 200 else {"_http_status": resp.status_code}

    cmp = compare_json_at_paths(bot_response, expected, record.compare_fields)
    return TestResult(
        record=record,
        verdict=cmp.verdict,
        diffs=cmp.diff,
        bot_measurement=bot_m.to_dict(),
        harness_measurement=harness_m.to_dict(),
        bot_payload=bot_response,
        expected_payload=expected,
    )


def run_derived_query_test(
    record: TestRecord,
    bot_runner: Callable[[str, NowAnchor], dict],
    staging_engine: Engine,
    now_anchor: NowAnchor,
) -> TestResult:
    """Run a derived-query test. Compares bot's dict result to harness-computed truth."""
    # Bot path
    with measure() as bot_m:
        bot_result = bot_runner(record.prompt, now_anchor)
    # Bot result is expected to be a dict keyed by names in bot_must_return_keys

    # Ground-truth path
    expected: dict[str, Any] = {}
    with measure() as harness_m:
        with staging_engine.connect() as conn:
            for entry in record.ground_truth_sql:
                bound = now_anchor.bind_sql(entry["sql"])
                row = conn.execute(text(bound["sql"]), bound["params"]).mappings().first()
                if row is None:
                    expected[entry["name"]] = None
                else:
                    # Convention: single-column ground-truth SQL aliased AS v, else first column
                    if "v" in row:
                        expected[entry["name"]] = row["v"]
                    else:
                        expected[entry["name"]] = list(row.values())[0]

    # Check required keys present
    missing_keys = [k for k in record.bot_must_return_keys if k not in bot_result]
    if missing_keys:
        return TestResult(
            record=record,
            verdict=Verdict.FAIL,
            diffs=[f"Bot result missing keys: {missing_keys}"],
            bot_measurement=bot_m.to_dict(),
            harness_measurement=harness_m.to_dict(),
            bot_payload=bot_result,
            expected_payload=expected,
        )

    cmp = compare_aggregates(bot_result, expected, float_tolerance=0.01)
    return TestResult(
        record=record,
        verdict=cmp.verdict,
        diffs=cmp.diff,
        bot_measurement=bot_m.to_dict(),
        harness_measurement=harness_m.to_dict(),
        bot_payload=bot_result,
        expected_payload=expected,
    )
```

- [ ] **Step 4: Run, verify pass**

```bash
py311 -m pytest testing/v10_harness/tests/test_runner.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add testing/v10_harness/runner.py testing/v10_harness/tests/test_runner.py
git commit -m "feat(harness): add TestRecord schema + known/derived runners"
```

### Task 1.7: Write the initial `test_set.jsonl` with 10 known-report tests

**Files:**
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\test_set.jsonl`

- [ ] **Step 1: Author the 10 entries**

Create `testing/v10_harness/test_set.jsonl` (one JSON object per line):

```jsonl
{"id":"K_dash_001","category":"known-report","report":"dashboard-stats","prompt":"give me the dashboard overview stats","expected_idre_call":{"method":"GET","path":"/api/reports/dashboard-stats","query":{}},"compare_fields":["data.totalCases","data.activeArbitrators","data.totalPayments","data.totalPaymentAmount"],"temporality":"variant"}
{"id":"K_due_001","category":"known-report","report":"due-dates","prompt":"list all overdue cases as of today across all 4 due date columns","expected_idre_call":{"method":"GET","path":"/api/reports/due-dates","query":{"urgency":"overdue","limit":"10000"}},"compare_fields":["data.totalCount","data.cases[*].caseId","data.cases[*].status"],"temporality":"variant"}
{"id":"K_due_002","category":"known-report","report":"due-dates","prompt":"cases with upcoming due dates in the next 7 days","expected_idre_call":{"method":"GET","path":"/api/reports/due-dates","query":{"urgency":"warning","limit":"10000"}},"compare_fields":["data.totalCount","data.cases[*].caseId"],"temporality":"variant"}
{"id":"K_out_001","category":"known-report","report":"outstanding-payments","prompt":"show all cases with outstanding payments","expected_idre_call":{"method":"GET","path":"/api/reports/outstanding-payments","query":{"limit":"10000"}},"compare_fields":["data.totalCount","data.cases[*].caseId","data.cases[*].status"],"temporality":"variant"}
{"id":"K_bal_001","category":"known-report","report":"case-balance","prompt":"show the case balance report","expected_idre_call":{"method":"GET","path":"/api/reports/case-balance","query":{"limit":"10000"}},"compare_fields":["data.totalCount","data.cases[*].caseId","data.totalBalance"],"temporality":"variant"}
{"id":"K_cms_001","category":"known-report","report":"cms-payments","prompt":"show CMS payments breakdown","expected_idre_call":{"method":"GET","path":"/api/reports/cms-payments","query":{}},"compare_fields":["data.totalAmount","data.byStatus"],"temporality":"variant"}
{"id":"K_team_001","category":"known-report","report":"team-performance","prompt":"show team performance metrics","expected_idre_call":{"method":"GET","path":"/api/reports/team-performance","query":{}},"compare_fields":["data.members[*].userId","data.members[*].caseCount"],"temporality":"variant"}
{"id":"K_unpaid_001","category":"known-report","report":"unpaid-disputes","prompt":"list all unpaid disputes","expected_idre_call":{"method":"GET","path":"/api/reports/unpaid-disputes","query":{"limit":"10000"}},"compare_fields":["data.totalCount","data.disputes[*].caseId"],"temporality":"variant"}
{"id":"K_payouts_001","category":"known-report","report":"idre-payouts","prompt":"show all IDRE payouts","expected_idre_call":{"method":"GET","path":"/api/reports/idre-payouts","query":{"limit":"10000"}},"compare_fields":["data.totalCount","data.payouts[*].paymentId","data.totalAmount"],"temporality":"variant"}
{"id":"K_activity_001","category":"known-report","report":"recent-activity","prompt":"show recent activity from the last 7 days","expected_idre_call":{"method":"GET","path":"/api/reports/recent-activity","query":{"limit":"10000"}},"compare_fields":["data.activities[*].caseId","data.totalCount"],"temporality":"variant"}
```

- [ ] **Step 2: Verify well-formed JSONL**

```bash
py311 -c "
import json
with open('testing/v10_harness/test_set.jsonl') as f:
    for i, line in enumerate(f, 1):
        json.loads(line)
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add testing/v10_harness/test_set.jsonl
git commit -m "feat(harness): add 10 known-report tests for Day 1 baseline"
```

### Task 1.8: Write `run_tests.py` — pytest entry point

**Files:**
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\tests\test_baseline_known.py`

- [ ] **Step 1: Author the pytest file**

Create `testing/v10_harness/tests/test_baseline_known.py`:

```python
"""Parametrized run of known-report tests against a bot under test.

Bot selection via env var BOT=v8 or BOT=v10 (default v8 for baseline).
"""
import json
import os
import sys
from pathlib import Path
import pytest

from testing.v10_harness.runner import (
    TestRecord, run_known_report_test, TestResult,
)
from testing.v10_harness.compare import Verdict


HARNESS = Path(__file__).parent.parent
TEST_SET = HARNESS / "test_set.jsonl"
REPORTS_DIR = HARNESS / "reports"


def _load_set() -> list[TestRecord]:
    records = []
    with open(TEST_SET) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(TestRecord.from_dict(json.loads(line)))
    return records


def _known_records() -> list[TestRecord]:
    return [r for r in _load_set() if r.category == "known-report"]


@pytest.fixture(scope="session")
def bot_runner():
    """Return a callable (prompt, now_anchor) -> dict response."""
    which = os.environ.get("BOT", "v8")
    if which == "v8":
        from db.connector import get_engine  # ensure V8 env active
        # For V8 baseline, we route every "known-report" prompt to the SQL bot
        # and wrap its dict-result back into a JSON-like shape.
        import importlib
        sys.path.insert(0, "C:/Users/anand/Downloads/v8_reports_bot")
        app = importlib.import_module("app")

        def runner(prompt: str, now):
            # V8 doesn't accept :now; we just call its top-level NL handler.
            result = app.run_query(prompt) if hasattr(app, "run_query") else {"data": {}}
            return result if isinstance(result, dict) else {"data": result}
        return runner
    elif which == "v10":
        sys.path.insert(0, "C:/Users/anand/Downloads/v10_reports_bot")
        import app as v10_app
        return lambda prompt, now: v10_app.run_query_v10(prompt, now)
    else:
        raise RuntimeError(f"Unknown BOT={which}")


@pytest.mark.parametrize("record", _known_records(), ids=[r.id for r in _known_records()])
def test_known_report(record, bot_runner, idre_session, now_anchor):
    result: TestResult = run_known_report_test(
        record, bot_runner, idre_session, now_anchor,
    )
    REPORTS_DIR.mkdir(exist_ok=True)
    out = REPORTS_DIR / f"{record.id}.json"
    with open(out, "w") as f:
        json.dump(result.to_dict(), f, indent=2, default=str)
    assert result.verdict == Verdict.PASS, f"{record.id}: {result.diffs}"
```

- [ ] **Step 2: Collect-only sanity check**

```bash
cd /c/Users/anand/Downloads/local
py311 -m pytest testing/v10_harness/tests/test_baseline_known.py --collect-only
```

Expected: 10 test items, one per K_* record.

- [ ] **Step 3: Commit**

```bash
git add testing/v10_harness/tests/test_baseline_known.py
git commit -m "feat(harness): add parametrized known-report baseline runner"
```

### Task 1.9: Day-1 sanity run

- [ ] **Step 1: Run the harness unit tests**

```bash
cd /c/Users/anand/Downloads/local
py311 -m pytest testing/v10_harness/tests/test_temporality.py testing/v10_harness/tests/test_compare.py testing/v10_harness/tests/test_measurements.py testing/v10_harness/tests/test_runner.py -v
```

Expected: 18 passed.

- [ ] **Step 2: Commit a Day-1 marker**

```bash
git tag day1-complete -m "Day 1: test harness skeleton + 10 known-report tests"
```

---

## Day 2: V8 Baseline Run

The first time we will have honest result-comparison numbers for any version. **Expect most tests to FAIL** — V8 generates SQL via tools, not parallel IDRE calls, so byte-equality is unlikely. The point is to capture WHERE V8 diverges.

### Task 2.1: Make V8 callable in-process

V8's `app.py` is Streamlit-driven; we need a callable function for the harness.

**Files:**
- Create: `C:\Users\anand\Downloads\v8_reports_bot\harness_entrypoint.py`

- [ ] **Step 1: Inspect V8 graph entry**

```bash
grep -n "def\|workflow\|graph\|compile" /c/Users/anand/Downloads/v8_reports_bot/app.py | head -30
```

Look for the function that builds the LangGraph and an existing top-level runner (likely `run_query` or `process_query`).

- [ ] **Step 2: Write the entrypoint**

Create `C:\Users\anand\Downloads\v8_reports_bot\harness_entrypoint.py`:

```python
"""Single-call entrypoint for harness use. Wraps V8's LangGraph.

Usage:
    from harness_entrypoint import run
    result = run("how many total cases are there")
    # → {"data": {...}, "sql": "...", "agent_trace": [...]}
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent.resolve()
os.chdir(str(HERE))  # so config/settings.py finds .env
sys.path.insert(0, str(HERE))

from state.context import GraphState
from agents.context_loader import context_loader_node
from agents.ambiguity_scorer import ambiguity_scorer_node
from agents.schema_mapper import schema_mapper_node
from agents.sql_writer import sql_writer_node
from agents.sql_validator import sql_validator_node
from agents.executor import executor_node
from agents.output_formatter import output_formatter_node


def run(prompt: str, user_role: str = "MA") -> dict:
    """Run V8 pipeline once and return a dict result."""
    state: GraphState = {
        "user_query": prompt,
        "session_id": "harness",
        "user_role": user_role,
        "permitted_tables": [],
        "conversation_history": [],
        "resolved_query": prompt,
        "entity_registry": {},
    }
    # Sequential — bypass LangGraph orchestration to keep it deterministic for tests
    state = context_loader_node(state)
    state = ambiguity_scorer_node(state)
    state = schema_mapper_node(state)
    state = sql_writer_node(state)
    state = sql_validator_node(state)
    state = executor_node(state)
    state = output_formatter_node(state)
    return {
        "data": state.get("query_result", []),
        "sql": state.get("generated_sql", ""),
        "row_count": state.get("row_count", 0),
        "agent_trace": state.get("agent_trace", []),
        "execution_error": state.get("execution_error"),
    }
```

- [ ] **Step 3: Smoke-test the entrypoint**

```bash
cd /c/Users/anand/Downloads/v8_reports_bot
py311 harness_entrypoint.py 2>&1 | head -5
```

(Nothing should error on import. Empty stdout is fine.)

Run an inline call:

```bash
py311 -c "
import sys; sys.path.insert(0, '/c/Users/anand/Downloads/v8_reports_bot')
from harness_entrypoint import run
r = run('how many total cases are there')
print('row_count:', r['row_count'])
print('sql:', r['sql'][:100])
"
```

Expected: prints a row count and the first 100 chars of generated SQL. If errors, fix and rerun.

- [ ] **Step 4: Update harness conftest to use it**

Edit `testing/v10_harness/tests/test_baseline_known.py`, replace the V8 branch in `bot_runner`:

```python
    if which == "v8":
        sys.path.insert(0, "C:/Users/anand/Downloads/v8_reports_bot")
        from harness_entrypoint import run as v8_run

        def runner(prompt: str, now):
            r = v8_run(prompt)
            # Wrap rows as IDRE-API-like shape for compare.py paths
            return {"data": {"rows": r.get("data", []), "totalCount": r.get("row_count", 0)}}
        return runner
```

- [ ] **Step 5: Commit**

```bash
cd /c/Users/anand/Downloads/local
git add ../v8_reports_bot/harness_entrypoint.py testing/v10_harness/tests/test_baseline_known.py
# If the v8 dir is outside this git repo, just commit the harness side:
git add testing/v10_harness/tests/test_baseline_known.py
git commit -m "feat(harness): wire V8 entrypoint for baseline runs"
```

### Task 2.2: Execute Day-2 baseline

- [ ] **Step 1: Run the 10 known-report tests against V8**

```bash
cd /c/Users/anand/Downloads/local
BOT=v8 py311 -m pytest testing/v10_harness/tests/test_baseline_known.py -v --tb=short -o log_cli=true
```

Expected: all 10 tests run to completion. Most will FAIL (V8 generates SQL ≠ IDRE response shape). Capture the output.

- [ ] **Step 2: Inspect the per-test JSON reports**

```bash
ls testing/v10_harness/reports/
py311 -c "
import json, glob
results = {}
for p in glob.glob('testing/v10_harness/reports/K_*.json'):
    d = json.load(open(p))
    results[d['id']] = d['verdict']
for k, v in sorted(results.items()):
    print(f'{k}: {v}')
print('PASS rate:', sum(1 for v in results.values() if v=='PASS'), '/', len(results))
"
```

- [ ] **Step 3: Save the baseline summary**

```bash
mkdir -p testing/v10_harness/reports/baseline
cp testing/v10_harness/reports/K_*.json testing/v10_harness/reports/baseline/
py311 -c "
import json, glob
out = []
for p in glob.glob('testing/v10_harness/reports/baseline/K_*.json'):
    out.append(json.load(open(p)))
with open('testing/v10_harness/reports/baseline/SUMMARY.json', 'w') as f:
    json.dump({'bot': 'v8', 'date': '2026-05-15', 'results': out}, f, indent=2, default=str)
"
```

- [ ] **Step 4: Commit the baseline**

```bash
git add testing/v10_harness/reports/baseline/
git commit -m "test: V8 baseline against 10 known-report tests (Day 2)"
git tag day2-baseline -m "V8 baseline numbers captured"
```

---

## Day 3: Knowledge Pipeline (Scripts 01–06)

Each script is independent and idempotent. We build them in dependency order.

### Task 3.1: Create pipeline directory + shared helpers

**Files:**
- Create: `C:\Users\anand\Downloads\local\scripts\build_knowledge\__init__.py`
- Create: `C:\Users\anand\Downloads\local\scripts\build_knowledge\common.py`

- [ ] **Step 1: Make the directory**

```bash
mkdir -p /c/Users/anand/Downloads/local/scripts/build_knowledge
touch /c/Users/anand/Downloads/local/scripts/build_knowledge/__init__.py
```

- [ ] **Step 2: Write `common.py`**

```python
"""Shared paths + helpers for the knowledge-build pipeline."""
from __future__ import annotations
import json
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timezone

IDRE_REPO = Path("C:/Users/anand/Downloads/local/idre")
KNOWLEDGE_ROOT = Path("C:/Users/anand/Downloads/v10_reports_bot/knowledge")
PENDING_DIR = KNOWLEDGE_ROOT / "v10_pending"
LIVE_DIR = KNOWLEDGE_ROOT / "v10"


def ensure_pending() -> Path:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    return PENDING_DIR


def write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def git_sha(branch: str = "staging") -> str:
    out = subprocess.check_output(
        ["git", "rev-parse", f"origin/{branch}"],
        cwd=str(IDRE_REPO),
        text=True,
    )
    return out.strip()[:12]


def utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
```

- [ ] **Step 3: Commit**

```bash
cd /c/Users/anand/Downloads/local
git add scripts/build_knowledge/__init__.py scripts/build_knowledge/common.py
git commit -m "feat(pipeline): scaffold knowledge-build pipeline + common helpers"
```

### Task 3.2: Script `01_sync_staging.py`

**Files:**
- Create: `C:\Users\anand\Downloads\local\scripts\build_knowledge\01_sync_staging.py`

- [ ] **Step 1: Write the script**

```python
"""Sync local IDRE clone to origin/staging. Idempotent."""
from __future__ import annotations
import argparse
import subprocess
import sys
from pathlib import Path
from common import IDRE_REPO, git_sha


def run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=str(IDRE_REPO), text=True).strip()


def main(branch: str) -> int:
    if not (IDRE_REPO / ".git").exists():
        print(f"ERROR: {IDRE_REPO} is not a git repo", file=sys.stderr)
        return 1
    print(f"Fetching origin/{branch}...")
    run(["git", "fetch", "origin", branch])
    sha = git_sha(branch)
    print(f"origin/{branch} is at {sha}")

    # Check for local uncommitted changes — refuse to clobber
    dirty = run(["git", "status", "--porcelain"])
    if dirty:
        print("WARNING: local repo has uncommitted changes:")
        print(dirty)
        print("Pipeline will checkout origin/staging in detached HEAD.")

    run(["git", "checkout", "--detach", f"origin/{branch}"])
    print(f"Checked out origin/{branch} ({sha}) in detached HEAD")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--branch", default="staging")
    args = p.parse_args()
    sys.exit(main(args.branch))
```

- [ ] **Step 2: Verify it runs**

```bash
cd /c/Users/anand/Downloads/local/scripts/build_knowledge
py311 01_sync_staging.py --branch staging
```

Expected: `Fetching origin/staging...` then `origin/staging is at <sha>` then `Checked out origin/staging (<sha>) in detached HEAD`.

- [ ] **Step 3: Commit**

```bash
cd /c/Users/anand/Downloads/local
git add scripts/build_knowledge/01_sync_staging.py
git commit -m "feat(pipeline): step 01 — sync IDRE clone to origin/staging"
```

### Task 3.3: Script `02_extract_reference_cards.py`

**Files:**
- Create: `C:\Users\anand\Downloads\local\scripts\build_knowledge\02_extract_reference_cards.py`

- [ ] **Step 1: Write the script**

```python
"""Discover all report endpoints under idre/app/api/reports/**.
Emit a minimal card per report. (Detailed extraction lives in 05.)
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from common import IDRE_REPO, ensure_pending, write_json, git_sha


REPORTS_DIR = IDRE_REPO / "app" / "api" / "reports"


def discover_reports() -> list[dict]:
    cards = []
    if not REPORTS_DIR.exists():
        return cards
    for route_ts in REPORTS_DIR.rglob("route.ts"):
        rel = route_ts.relative_to(IDRE_REPO).as_posix()
        # The report id is the directory containing route.ts, relative to api/reports
        rel_dir = route_ts.parent.relative_to(REPORTS_DIR).as_posix()
        report_id = rel_dir or "root"
        # Look for a sibling lib dependency
        lib_candidate = IDRE_REPO / "lib" / "reports" / f"{report_id.split('/')[-1]}.ts"
        cards.append({
            "id": report_id,
            "route_file": rel,
            "lib_file": lib_candidate.relative_to(IDRE_REPO).as_posix() if lib_candidate.exists() else None,
            "endpoint": f"/api/reports/{report_id}",
        })
    cards.sort(key=lambda c: c["id"])
    return cards


def main() -> int:
    cards = discover_reports()
    if not cards:
        print(f"ERROR: no route.ts files found under {REPORTS_DIR}", file=sys.stderr)
        return 1
    out = ensure_pending() / "report_reference_cards.json"
    write_json(out, {
        "idre_git_sha": git_sha(),
        "reports": cards,
        "count": len(cards),
    })
    print(f"Wrote {len(cards)} report cards → {out}")
    for c in cards:
        print(f"  {c['id']:30} → {c['route_file']}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.parse_args()
    sys.exit(main())
```

- [ ] **Step 2: Run it**

```bash
cd /c/Users/anand/Downloads/local/scripts/build_knowledge
py311 02_extract_reference_cards.py
```

Expected: prints each report id and the relative path of its `route.ts`. Should match the 14 we expect (dashboard-stats, due-dates, etc.), plus possibly new ones from staging.

- [ ] **Step 3: Inspect the output**

```bash
cat /c/Users/anand/Downloads/v10_reports_bot/knowledge/v10_pending/report_reference_cards.json | head -40
```

- [ ] **Step 4: Commit**

```bash
cd /c/Users/anand/Downloads/local
git add scripts/build_knowledge/02_extract_reference_cards.py
git commit -m "feat(pipeline): step 02 — discover all report endpoints"
```

### Task 3.4: Script `03_extract_schema.py`

**Files:**
- Create: `C:\Users\anand\Downloads\local\scripts\build_knowledge\03_extract_schema.py`

- [ ] **Step 1: Write the script**

```python
"""Parse idre/prisma/schema.prisma into a schema_catalog.json.
Each table gets: name, columns (name, type, optional, attributes), relations.
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path
from common import IDRE_REPO, ensure_pending, write_json, git_sha

SCHEMA_FILE = IDRE_REPO / "prisma" / "schema.prisma"

MODEL_BLOCK = re.compile(r"^model\s+(\w+)\s*\{([^}]*)\}", re.MULTILINE | re.DOTALL)
ENUM_BLOCK = re.compile(r"^enum\s+(\w+)\s*\{([^}]*)\}", re.MULTILINE | re.DOTALL)
FIELD_LINE = re.compile(
    r"^\s*(\w+)\s+(\w+)(\?)?(\s*\[\])?\s*(.*)$"
)


def parse_models(text: str) -> list[dict]:
    models = []
    for name, body in MODEL_BLOCK.findall(text):
        columns = []
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("@@"):
                continue
            m = FIELD_LINE.match(line)
            if not m:
                continue
            col_name, col_type, opt, is_list, attrs = m.groups()
            columns.append({
                "name": col_name,
                "type": col_type,
                "optional": opt == "?",
                "is_list": bool(is_list),
                "attributes": attrs.strip(),
            })
        # Convention: table_name matches @@map() if present, else lowercased model name
        table_map = re.search(r"@@map\(\"([^\"]+)\"\)", body)
        models.append({
            "model": name,
            "table_name": table_map.group(1) if table_map else _camel_to_snake(name),
            "columns": columns,
        })
    return models


def parse_enums(text: str) -> list[dict]:
    enums = []
    for name, body in ENUM_BLOCK.findall(text):
        values = [line.strip() for line in body.splitlines() if line.strip() and not line.strip().startswith("//")]
        enums.append({"name": name, "values": values})
    return enums


def _camel_to_snake(name: str) -> str:
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return s


def main() -> int:
    if not SCHEMA_FILE.exists():
        print(f"ERROR: {SCHEMA_FILE} not found (did 01_sync_staging.py run?)", file=sys.stderr)
        return 1
    text = SCHEMA_FILE.read_text(encoding="utf-8")
    models = parse_models(text)
    enums = parse_enums(text)
    out = ensure_pending() / "schema_catalog.json"
    write_json(out, {
        "idre_git_sha": git_sha(),
        "models": models,
        "enums_inline": enums,
        "model_count": len(models),
        "enum_count": len(enums),
    })
    print(f"Wrote {len(models)} models + {len(enums)} enums → {out}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.parse_args()
    sys.exit(main())
```

- [ ] **Step 2: Run it**

```bash
cd /c/Users/anand/Downloads/local/scripts/build_knowledge
py311 03_extract_schema.py
```

Expected: `Wrote NN models + NN enums → .../schema_catalog.json`.

- [ ] **Step 3: Spot-check models include `case` and `payment`**

```bash
py311 -c "
import json
d = json.load(open('/c/Users/anand/Downloads/v10_reports_bot/knowledge/v10_pending/schema_catalog.json'))
names = [m['table_name'] for m in d['models']]
for needed in ['case','payment','case_payment_allocation','case_refunds','user','organization']:
    print(needed, 'OK' if needed in names else 'MISSING')
"
```

Expected: all OK. If MISSING, the @@map convention may be different on staging — adjust the regex.

- [ ] **Step 4: Commit**

```bash
cd /c/Users/anand/Downloads/local
git add scripts/build_knowledge/03_extract_schema.py
git commit -m "feat(pipeline): step 03 — extract schema from staging schema.prisma"
```

### Task 3.5: Script `04_extract_enums.py`

**Files:**
- Create: `C:\Users\anand\Downloads\local\scripts\build_knowledge\04_extract_enums.py`

- [ ] **Step 1: Write the script**

```python
"""Combine Prisma inline enums + TypeScript enum decls + RDS distinct-value sampling."""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
from common import IDRE_REPO, ensure_pending, write_json, git_sha

ENUM_TS_REGEX = re.compile(
    r"export\s+(?:const\s+|enum\s+)(\w+)\s*=?\s*\{([^}]*)\}\s*(?:as\s+const)?",
    re.DOTALL,
)


def scan_ts_enums() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    candidates = list(IDRE_REPO.rglob("*.ts"))
    for f in candidates:
        if "node_modules" in f.parts:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "enum " not in text and "as const" not in text:
            continue
        for name, body in ENUM_TS_REGEX.findall(text):
            values = re.findall(r"['\"]([A-Z_][A-Z0-9_]+)['\"]", body)
            values += re.findall(r"\b([A-Z_][A-Z0-9_]+)\s*[:=]", body)
            values = sorted(set(values))
            if values:
                found.setdefault(name, []).extend(values)
    return {k: sorted(set(v)) for k, v in found.items()}


def sample_rds_columns(engine) -> dict[str, list[str]]:
    """Sample distinct values for known enum-like columns from staging RDS."""
    from sqlalchemy import text
    cols = [
        ("case", "status"),
        ("payment", "type"),
        ("payment", "status"),
        ("payment", "direction"),
        ("case_payment_allocation", "partyType"),
    ]
    out: dict[str, list[str]] = {}
    with engine.connect() as conn:
        for table, col in cols:
            try:
                rows = conn.execute(
                    text(f"SELECT DISTINCT `{col}` AS v FROM `{table}` WHERE `{col}` IS NOT NULL")
                ).mappings().all()
                out[f"{table}.{col}"] = sorted(set(str(r["v"]) for r in rows))
            except Exception as e:
                out[f"{table}.{col}"] = []
                print(f"WARN: failed to sample {table}.{col}: {e}", file=sys.stderr)
    return out


def main() -> int:
    sys.path.insert(0, "/c/Users/anand/Downloads/v8_reports_bot")
    import os
    os.chdir("/c/Users/anand/Downloads/v8_reports_bot")
    from db.connector import get_engine
    eng = get_engine()

    ts_enums = scan_ts_enums()
    rds = sample_rds_columns(eng)
    out = ensure_pending() / "enum_catalog.json"
    write_json(out, {
        "idre_git_sha": git_sha(),
        "typescript_enums": ts_enums,
        "rds_sampled": rds,
    })
    print(f"Wrote {len(ts_enums)} TS enums + {len(rds)} RDS column samples → {out}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.parse_args()
    sys.exit(main())
```

- [ ] **Step 2: Run it**

```bash
cd /c/Users/anand/Downloads/local/scripts/build_knowledge
py311 04_extract_enums.py
```

Expected: writes `enum_catalog.json`. WARN lines for any column that doesn't exist on current staging — that's information, not failure.

- [ ] **Step 3: Spot-check `case.status` and `payment.type`**

```bash
py311 -c "
import json
d = json.load(open('/c/Users/anand/Downloads/v10_reports_bot/knowledge/v10_pending/enum_catalog.json'))
print('case.status:', d['rds_sampled'].get('case.status'))
print('payment.type:', d['rds_sampled'].get('payment.type'))
"
```

Expected: lists of actual status / type strings (e.g., `PENDING_PAYMENTS`, `CASE_PAYMENT`).

- [ ] **Step 4: Commit**

```bash
cd /c/Users/anand/Downloads/local
git add scripts/build_knowledge/04_extract_enums.py
git commit -m "feat(pipeline): step 04 — extract enums (TS + RDS-sampled)"
```

### Task 3.6: Script `05_extract_business_logic.py` — frontier-model conversion

This is the hardest script. It reads each report's `route.ts` (and any `lib/reports/*.ts` dependency) and uses Gemini 2.5 Pro to produce a `{prisma_query, js_postprocessing, sql_equivalent}` triple per report.

**Files:**
- Create: `C:\Users\anand\Downloads\local\scripts\build_knowledge\05_extract_business_logic.py`

- [ ] **Step 1: Write the script**

```python
"""Per-report: read route.ts + lib dep; ask Gemini to extract Prisma + JS + SQL triple."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import google.generativeai as genai
from common import IDRE_REPO, ensure_pending, write_json, git_sha


SYSTEM_PROMPT = """You are converting an IDRE platform report from TypeScript+Prisma source code into an equivalent raw MySQL query.

You will receive the contents of:
  (a) app/api/reports/<name>/route.ts — the Next.js route handler
  (b) (optional) lib/reports/<name>.ts — supporting library code

Output a JSON object with these keys:
  - "prisma_query": the Prisma call(s) the route makes (verbatim, as a single TypeScript string)
  - "js_postprocessing": any JS that runs AFTER the Prisma call (filter, map, reduce, .some(), .every(), aggregations). Empty string if none.
  - "sql_equivalent": a MySQL SELECT that produces the same final result as the route after JS post-processing. Use backticks for `case` (reserved word). Inline the JS logic as SQL subqueries (NOT EXISTS, CASE WHEN, etc.) where applicable.
  - "result_shape": the JSON shape the route returns (top-level keys)
  - "notes": one-sentence rationale; flag any logic you couldn't translate.

Output ONLY the JSON object. No markdown, no commentary."""


def read_with_deps(report: dict) -> str:
    parts = []
    route = IDRE_REPO / report["route_file"]
    parts.append(f"// FILE: {report['route_file']}\n" + route.read_text(encoding="utf-8"))
    if report.get("lib_file"):
        lib = IDRE_REPO / report["lib_file"]
        if lib.exists():
            parts.append(f"\n// FILE: {report['lib_file']}\n" + lib.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def call_gemini(source: str, api_key: str) -> dict:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        "gemini-2.5-pro-preview",
        system_instruction=SYSTEM_PROMPT,
    )
    resp = model.generate_content(source, generation_config={"temperature": 0.1, "max_output_tokens": 8000})
    text = resp.text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def main() -> int:
    sys.path.insert(0, "/c/Users/anand/Downloads/v8_reports_bot")
    import os
    os.chdir("/c/Users/anand/Downloads/v8_reports_bot")
    from config.settings import get_settings
    api_key = get_settings().gemini_api_key
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set in v8/.env", file=sys.stderr)
        return 1

    pending = ensure_pending()
    cards_path = pending / "report_reference_cards.json"
    if not cards_path.exists():
        print(f"ERROR: run 02_extract_reference_cards.py first", file=sys.stderr)
        return 1
    cards_doc = json.loads(cards_path.read_text())
    cards = cards_doc["reports"]

    business_logic = []
    for c in cards:
        print(f"Converting {c['id']}...", flush=True)
        try:
            source = read_with_deps(c)
        except OSError as e:
            print(f"  SKIP: {e}", file=sys.stderr)
            continue
        try:
            triple = call_gemini(source, api_key)
        except Exception as e:
            print(f"  FAIL: {e}", file=sys.stderr)
            business_logic.append({"id": c["id"], "needs_review": True, "error": str(e)})
            continue
        triple["id"] = c["id"]
        triple["route_file"] = c["route_file"]
        triple["needs_review"] = False
        business_logic.append(triple)

    out = pending / "business_logic.json"
    write_json(out, {
        "idre_git_sha": git_sha(),
        "reports": business_logic,
    })
    print(f"Wrote {len(business_logic)} business-logic entries → {out}")
    needs_review = [b for b in business_logic if b.get("needs_review")]
    if needs_review:
        print(f"WARNING: {len(needs_review)} entries need human review:")
        for b in needs_review:
            print(f"  - {b['id']}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.parse_args()
    sys.exit(main())
```

- [ ] **Step 2: Run it**

```bash
cd /c/Users/anand/Downloads/local/scripts/build_knowledge
py311 05_extract_business_logic.py
```

Expected: ~14 reports converted, one Gemini call each (~30-60s per call), total ~10-15 min. Any FAIL line means that report needs human review.

- [ ] **Step 3: Spot-check one card**

```bash
py311 -c "
import json
d = json.load(open('/c/Users/anand/Downloads/v10_reports_bot/knowledge/v10_pending/business_logic.json'))
due = next((r for r in d['reports'] if r['id']=='due-dates'), None)
if due:
    print('sql_equivalent:')
    print(due.get('sql_equivalent', '')[:500])
"
```

Expected: a SQL SELECT statement that references 4 due-date columns. If only 1 column referenced, that report needs review.

- [ ] **Step 4: Commit**

```bash
cd /c/Users/anand/Downloads/local
git add scripts/build_knowledge/05_extract_business_logic.py
git commit -m "feat(pipeline): step 05 — Gemini conversion Prisma+JS → SQL"
```

### Task 3.7: Script `06_validate_pipeline.py`

**Files:**
- Create: `C:\Users\anand\Downloads\local\scripts\build_knowledge\06_validate_pipeline.py`

- [ ] **Step 1: Write the script**

```python
"""Validate pending knowledge artifacts: required files present, SQL is parseable,
and (optionally) sql_equivalent executes without error against staging RDS.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from common import PENDING_DIR, write_json, git_sha, utc_iso, file_sha256

REQUIRED = [
    "report_reference_cards.json",
    "schema_catalog.json",
    "enum_catalog.json",
    "business_logic.json",
]


def main(execute_sql: bool) -> int:
    summary = {"checks": [], "ok": True}

    # Check 1: all required files exist
    for fname in REQUIRED:
        f = PENDING_DIR / fname
        if not f.exists():
            summary["checks"].append({"name": f"file_exists:{fname}", "ok": False})
            summary["ok"] = False
        else:
            summary["checks"].append({"name": f"file_exists:{fname}", "ok": True, "sha": file_sha256(f)})

    # Check 2: business_logic.json well-formed
    bl_path = PENDING_DIR / "business_logic.json"
    if bl_path.exists():
        bl = json.loads(bl_path.read_text())
        for r in bl["reports"]:
            ok = bool(r.get("sql_equivalent")) and not r.get("needs_review", False)
            summary["checks"].append({
                "name": f"sql_present:{r['id']}",
                "ok": ok,
            })
            if not ok:
                summary["ok"] = False

    # Check 3 (optional): execute every sql_equivalent
    if execute_sql:
        sys.path.insert(0, "/c/Users/anand/Downloads/v8_reports_bot")
        import os
        os.chdir("/c/Users/anand/Downloads/v8_reports_bot")
        from db.connector import get_engine
        from sqlalchemy import text
        eng = get_engine()
        bl = json.loads((PENDING_DIR / "business_logic.json").read_text())
        with eng.connect() as conn:
            for r in bl["reports"]:
                sql = r.get("sql_equivalent", "")
                if not sql:
                    continue
                try:
                    conn.execute(text(sql + " LIMIT 1"))
                    summary["checks"].append({"name": f"sql_executes:{r['id']}", "ok": True})
                except Exception as e:
                    summary["checks"].append({"name": f"sql_executes:{r['id']}", "ok": False, "err": str(e)[:300]})
                    summary["ok"] = False

    # Write manifest
    manifest = {
        "idre_git_sha": git_sha(),
        "generated_at": utc_iso(),
        "files": {f: file_sha256(PENDING_DIR / f) for f in REQUIRED if (PENDING_DIR / f).exists()},
        "validation": summary,
    }
    write_json(PENDING_DIR / "manifest.json", manifest)
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--execute-sql", action="store_true",
                   help="Also execute each sql_equivalent against staging (slower)")
    args = p.parse_args()
    sys.exit(main(args.execute_sql))
```

- [ ] **Step 2: Run validation without SQL execution first**

```bash
cd /c/Users/anand/Downloads/local/scripts/build_knowledge
py311 06_validate_pipeline.py
```

Expected: prints summary with all checks `"ok": true`. Exit 0.

- [ ] **Step 3: Run validation with SQL execution**

```bash
py311 06_validate_pipeline.py --execute-sql
```

Expected: most reports' sql_equivalent executes against staging. Any FAIL with `sql_executes:X` means the Gemini-generated SQL has an error — flag those reports for review.

- [ ] **Step 4: Commit**

```bash
cd /c/Users/anand/Downloads/local
git add scripts/build_knowledge/06_validate_pipeline.py
git commit -m "feat(pipeline): step 06 — validation + manifest emission"
```

### Task 3.8: Orchestrator `run_all.py` + atomic swap

**Files:**
- Create: `C:\Users\anand\Downloads\local\scripts\build_knowledge\run_all.py`

- [ ] **Step 1: Write the orchestrator**

```python
"""Run all pipeline steps, then atomically swap v10_pending/ → v10/."""
from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from common import PENDING_DIR, LIVE_DIR


STEPS = [
    "01_sync_staging.py",
    "02_extract_reference_cards.py",
    "03_extract_schema.py",
    "04_extract_enums.py",
    "05_extract_business_logic.py",
]
HERE = Path(__file__).parent


def run_step(name: str, branch: str) -> int:
    cmd = ["py311", str(HERE / name)]
    if name == "01_sync_staging.py":
        cmd += ["--branch", branch]
    print(f"\n=== {name} ===")
    return subprocess.call(cmd, cwd=str(HERE))


def main(branch: str, execute_sql: bool) -> int:
    # Clear pending
    if PENDING_DIR.exists():
        shutil.rmtree(PENDING_DIR)
    PENDING_DIR.mkdir(parents=True)

    for step in STEPS:
        code = run_step(step, branch)
        if code != 0:
            print(f"\nABORT: {step} returned {code}", file=sys.stderr)
            return code

    # Validation
    val_cmd = ["py311", str(HERE / "06_validate_pipeline.py")]
    if execute_sql:
        val_cmd.append("--execute-sql")
    print("\n=== 06_validate_pipeline.py ===")
    code = subprocess.call(val_cmd, cwd=str(HERE))
    if code != 0:
        print("VALIDATION FAILED — leaving v10_pending/ in place for inspection.", file=sys.stderr)
        return code

    # Atomic swap
    backup = LIVE_DIR.with_suffix(".prev")
    if backup.exists():
        shutil.rmtree(backup)
    if LIVE_DIR.exists():
        LIVE_DIR.rename(backup)
    PENDING_DIR.rename(LIVE_DIR)
    print(f"\nKnowledge live at {LIVE_DIR}")
    print(f"Previous version archived at {backup}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--branch", default="staging")
    p.add_argument("--execute-sql", action="store_true")
    args = p.parse_args()
    sys.exit(main(args.branch, args.execute_sql))
```

- [ ] **Step 2: Smoke-run the orchestrator**

```bash
cd /c/Users/anand/Downloads/local/scripts/build_knowledge
py311 run_all.py --branch staging
```

Expected: 6 stages run sequentially. On success, `Knowledge live at .../knowledge/v10`. On failure, pending dir kept and exit non-zero.

- [ ] **Step 3: Inspect the live directory**

```bash
ls /c/Users/anand/Downloads/v10_reports_bot/knowledge/v10/
cat /c/Users/anand/Downloads/v10_reports_bot/knowledge/v10/manifest.json | head -30
```

Expected: 5 JSON files + manifest.

- [ ] **Step 4: Commit**

```bash
cd /c/Users/anand/Downloads/local
git add scripts/build_knowledge/run_all.py
git commit -m "feat(pipeline): orchestrator with atomic swap"
git tag day3-complete -m "Day 3: knowledge pipeline scripts written"
```

---

## Day 4: Run Pipeline + Triage Needs-Review Reports

### Task 4.1: Production pipeline run with SQL execution

- [ ] **Step 1: Full validated run**

```bash
cd /c/Users/anand/Downloads/local/scripts/build_knowledge
py311 run_all.py --branch staging --execute-sql 2>&1 | tee /tmp/pipeline_day4.log
```

Expected: all 6 steps pass, atomic swap to `knowledge/v10/` succeeds. If validation fails, the next step triages.

- [ ] **Step 2: Identify reports needing review**

```bash
py311 -c "
import json
m = json.load(open('/c/Users/anand/Downloads/v10_reports_bot/knowledge/v10/manifest.json'))
failed = [c for c in m['validation']['checks'] if not c['ok']]
print(f'{len(failed)} failed checks:')
for c in failed:
    print(' -', c.get('name'), c.get('err','')[:120])
"
```

- [ ] **Step 3: For each failed report — open route.ts side-by-side with the generated sql_equivalent**

```bash
py311 -c "
import json
bl = json.load(open('/c/Users/anand/Downloads/v10_reports_bot/knowledge/v10/business_logic.json'))
for r in bl['reports']:
    if r.get('needs_review'):
        print('---', r['id'], '---')
        print('route:', r.get('route_file'))
        print('SQL:', r.get('sql_equivalent','')[:600])
"
```

### Task 4.2: Manual repair for needs-review reports

For each report flagged:

- [ ] **Step 1: Read the actual route.ts**

```bash
cat /c/Users/anand/Downloads/local/idre/app/api/reports/<report_id>/route.ts
```

- [ ] **Step 2: Hand-fix the `sql_equivalent` directly in `business_logic.json`**

Open `C:\Users\anand\Downloads\v10_reports_bot\knowledge\v10\business_logic.json` and update the failing report's `sql_equivalent`. Set `needs_review: false`.

- [ ] **Step 3: Re-validate just that report**

```bash
py311 -c "
import json, os, sys
sys.path.insert(0, '/c/Users/anand/Downloads/v8_reports_bot'); os.chdir('/c/Users/anand/Downloads/v8_reports_bot')
from db.connector import get_engine
from sqlalchemy import text
bl = json.load(open('/c/Users/anand/Downloads/v10_reports_bot/knowledge/v10/business_logic.json'))
report_id = 'PUT_REPORT_ID_HERE'
r = next(x for x in bl['reports'] if x['id']==report_id)
with get_engine().connect() as c:
    c.execute(text(r['sql_equivalent'] + ' LIMIT 1'))
print(f'{report_id} SQL OK')
"
```

Expected: `<report_id> SQL OK`.

- [ ] **Step 4: Commit the repaired knowledge**

```bash
cd /c/Users/anand/Downloads/local
# v10_reports_bot is outside this repo by default — if you want this versioned,
# either git init in v10_reports_bot or copy v10/ knowledge into a tracked location.
# For now, just record the change:
echo "Knowledge repair $(date -u +%F) — fixed reports: <list>" >> docs/superpowers/knowledge-repair-log.md
git add docs/superpowers/knowledge-repair-log.md
git commit -m "docs: log knowledge-pipeline repairs for $(date -u +%F)"
git tag day4-complete -m "Day 4: pipeline run + manual repairs complete"
```

---

## Day 5: V10 Bootstrap + Router + 5 Known-Report Wrappers

### Task 5.1: Bootstrap V10 directory from V8

**Files:**
- Create: `C:\Users\anand\Downloads\v10_reports_bot\` (whole tree)

- [ ] **Step 1: Copy V8 → V10**

```bash
cp -a /c/Users/anand/Downloads/v8_reports_bot/ /c/Users/anand/Downloads/v10_reports_bot/
```

- [ ] **Step 2: Remove things V10 won't use**

```bash
cd /c/Users/anand/Downloads/v10_reports_bot
rm -f knowledge/data/file_summaries.json
rm -f knowledge/data/repo_map.txt
rm -f knowledge/data/module_keywords.json
rm -f knowledge/data/platform_rules.json
rm -f config/sql_templates.json
rm -f config/metric_cards.json
rm -rf data/__pycache__ agents/__pycache__ tools/__pycache__ config/__pycache__
# Knowledge v10/ already exists from Day 3-4 pipeline; leave it
```

- [ ] **Step 3: Verify v10/ knowledge is in place**

```bash
ls /c/Users/anand/Downloads/v10_reports_bot/knowledge/v10/
```

Expected: `business_logic.json  enum_catalog.json  manifest.json  report_reference_cards.json  schema_catalog.json`.

- [ ] **Step 4: Init git for V10 bot**

```bash
cd /c/Users/anand/Downloads/v10_reports_bot
git init
git config user.email "anand.wankhade@telomeregs.com"
git config user.name "Anand Wankhade"
cat > .gitignore << 'EOF'
__pycache__/
*.pyc
.env
data/__pycache__
agents/__pycache__
tools/__pycache__
config/__pycache__
chrome-cdp-profile/
materialized_results/
*.log
EOF
git add .
git commit -m "feat: bootstrap V10 from V8, strip RAG/legacy artifacts"
git tag v10-bootstrap
```

### Task 5.2: Extend `state/context.py` with V10 fields

**Files:**
- Modify: `C:\Users\anand\Downloads\v10_reports_bot\state\context.py`

- [ ] **Step 1: Read current**

```bash
head -100 /c/Users/anand/Downloads/v10_reports_bot/state/context.py
```

- [ ] **Step 2: Add fields**

Open `state/context.py` and add these fields to the `GraphState` TypedDict (find the `class GraphState` block and append before the closing of the TypedDict):

```python
    # ─── V10 additions ───
    now_anchor_iso: str          # ISO 8601 timestamp locked at request start
    router_decision: dict        # {path, report?, parameters?, confidence, reasoning}
    idre_api_response: dict      # Raw response when known-report path used
    knowledge_git_sha: str       # SHA of the knowledge/v10 in use
```

- [ ] **Step 3: Commit**

```bash
cd /c/Users/anand/Downloads/v10_reports_bot
git add state/context.py
git commit -m "feat(state): add V10 fields for router_decision, now_anchor, idre_api_response"
```

### Task 5.3: Author `config/route_signatures.json`

**Files:**
- Create: `C:\Users\anand\Downloads\v10_reports_bot\config\route_signatures.json`

- [ ] **Step 1: Write signatures for the 5 Day-5 reports**

(We do 14 reports across Day 5 + Day 9. Day 5 covers the 5 highest-failure-category reports.)

Create `config/route_signatures.json`:

```json
{
  "version": "v10-day5",
  "signatures": [
    {
      "id": "due-dates",
      "trigger_phrases": ["due date", "overdue", "deadline", "past due", "approaching", "urgent", "due today", "due this week"],
      "required_entities": ["case"],
      "parameter_extractors": [
        {"name": "urgency", "regex": "\\b(overdue|urgent|warning|approaching|normal|all)\\b", "default": "all"},
        {"name": "limit", "from_phrases": [{"match": "top\\s+(\\d+)", "extract_int": true}], "default": 10000}
      ],
      "idre_endpoint": "/api/reports/due-dates",
      "method": "GET"
    },
    {
      "id": "outstanding-payments",
      "trigger_phrases": ["outstanding payment", "outstanding payments", "unpaid", "owed amount", "payment outstanding"],
      "required_entities": ["case", "payment"],
      "parameter_extractors": [
        {"name": "limit", "from_phrases": [{"match": "top\\s+(\\d+)", "extract_int": true}], "default": 10000}
      ],
      "idre_endpoint": "/api/reports/outstanding-payments",
      "method": "GET"
    },
    {
      "id": "case-balance",
      "trigger_phrases": ["case balance", "balance report", "negative balance", "allocated", "refunded"],
      "required_entities": ["case"],
      "parameter_extractors": [
        {"name": "limit", "from_phrases": [{"match": "top\\s+(\\d+)", "extract_int": true}], "default": 10000}
      ],
      "idre_endpoint": "/api/reports/case-balance",
      "method": "GET"
    },
    {
      "id": "dashboard-stats",
      "trigger_phrases": ["dashboard", "quick stats", "overview", "kpi", "summary"],
      "required_entities": [],
      "parameter_extractors": [],
      "idre_endpoint": "/api/reports/dashboard-stats",
      "method": "GET"
    },
    {
      "id": "cms-payments",
      "trigger_phrases": ["cms payment", "cms payments", "cms admin fee", "cms fee", "medicare"],
      "required_entities": ["payment"],
      "parameter_extractors": [
        {"name": "limit", "from_phrases": [{"match": "top\\s+(\\d+)", "extract_int": true}], "default": 10000}
      ],
      "idre_endpoint": "/api/reports/cms-payments",
      "method": "GET"
    }
  ]
}
```

- [ ] **Step 2: Commit**

```bash
cd /c/Users/anand/Downloads/v10_reports_bot
git add config/route_signatures.json
git commit -m "feat(router): add route signatures for 5 Day-5 reports"
```

### Task 5.4: Write `agents/router.py`

**Files:**
- Create: `C:\Users\anand\Downloads\v10_reports_bot\agents\router.py`
- Test: `C:\Users\anand\Downloads\local\testing\v10_harness\tests\test_router.py`

- [ ] **Step 1: Write the failing test**

Create `testing/v10_harness/tests/test_router.py`:

```python
import sys
sys.path.insert(0, "C:/Users/anand/Downloads/v10_reports_bot")
from agents.router import route, RouterDecision


def test_route_matches_due_dates_overdue():
    d = route("show me all overdue cases right now")
    assert d.path == "known"
    assert d.report == "due-dates"
    assert d.parameters.get("urgency") == "overdue"
    assert d.confidence >= 0.85


def test_route_matches_dashboard_stats():
    d = route("give me the dashboard overview")
    assert d.path == "known"
    assert d.report == "dashboard-stats"


def test_route_to_derived_for_novel_query():
    d = route("which arbitrators have worked more than 50 cases this quarter and what is their average resolution time")
    # Should not strongly match any single report; fall to derived
    assert d.path in ("derived", "clarify")
    if d.path == "derived":
        assert d.report is None


def test_route_extracts_top_n_limit():
    d = route("show me top 25 outstanding payments")
    assert d.path == "known"
    assert d.report == "outstanding-payments"
    assert d.parameters.get("limit") == 25
```

- [ ] **Step 2: Run, verify fail**

```bash
cd /c/Users/anand/Downloads/local
py311 -m pytest testing/v10_harness/tests/test_router.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the router**

Create `C:\Users\anand\Downloads\v10_reports_bot\agents\router.py`:

```python
"""V10 Router — deterministic signature match + LLM fallback.

Stage 1: deterministic keyword match against config/route_signatures.json.
Stage 2: Gemini fallback when stage 1 confidence < 0.85.
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SIG_PATH = Path(__file__).parent.parent / "config" / "route_signatures.json"


@dataclass
class RouterDecision:
    path: str                     # "known" | "derived" | "clarify"
    report: str | None = None
    parameters: dict = field(default_factory=dict)
    confidence: float = 0.0
    reasoning: str = ""


_SIGS_CACHE: list[dict] | None = None


def _load_signatures() -> list[dict]:
    global _SIGS_CACHE
    if _SIGS_CACHE is None:
        _SIGS_CACHE = json.loads(SIG_PATH.read_text(encoding="utf-8"))["signatures"]
    return _SIGS_CACHE


def _extract_params(query: str, sig: dict) -> dict:
    out: dict[str, Any] = {}
    q = query.lower()
    for spec in sig.get("parameter_extractors", []):
        name = spec["name"]
        # Regex-based extraction
        if "regex" in spec:
            m = re.search(spec["regex"], q, re.IGNORECASE)
            if m:
                out[name] = m.group(1) if m.lastindex else m.group(0)
                continue
        # Phrase-extractor with int
        for phrase in spec.get("from_phrases", []):
            m = re.search(phrase["match"], q, re.IGNORECASE)
            if m:
                v = m.group(1)
                if phrase.get("extract_int"):
                    out[name] = int(v)
                else:
                    out[name] = v
                break
        # Default
        if name not in out and "default" in spec:
            out[name] = spec["default"]
    return out


def _score(query: str, sig: dict) -> float:
    """Confidence = matched-trigger-phrases / total-trigger-phrases, capped at 1.0,
    plus a small bump if any required entity word appears."""
    q = query.lower()
    triggers = sig.get("trigger_phrases", [])
    if not triggers:
        return 0.0
    matched = sum(1 for t in triggers if t in q)
    base = matched / len(triggers) if triggers else 0.0
    # Bigger bump when at least one trigger phrase hits — heuristic
    if matched >= 1:
        base = max(base, 0.85 + 0.05 * min(matched - 1, 3))
    return min(base, 1.0)


def route(query: str) -> RouterDecision:
    sigs = _load_signatures()
    best: tuple[float, dict | None] = (0.0, None)
    for sig in sigs:
        s = _score(query, sig)
        if s > best[0]:
            best = (s, sig)
    score, sig = best
    if sig and score >= 0.85:
        return RouterDecision(
            path="known",
            report=sig["id"],
            parameters=_extract_params(query, sig),
            confidence=score,
            reasoning=f"signature match: {sig['id']}",
        )
    # Stage 2 (LLM fallback) — leave as a TODO hook; for Day 5 we go straight to derived
    return RouterDecision(
        path="derived",
        report=None,
        parameters={},
        confidence=max(score, 0.0),
        reasoning="no signature matched ≥ 0.85; routing to derived path",
    )


def router_node(state: dict) -> dict:
    """LangGraph node wrapper."""
    decision = route(state.get("resolved_query") or state.get("user_query", ""))
    return {**state, "router_decision": {
        "path": decision.path,
        "report": decision.report,
        "parameters": decision.parameters,
        "confidence": decision.confidence,
        "reasoning": decision.reasoning,
    }}
```

- [ ] **Step 4: Run, verify pass**

```bash
cd /c/Users/anand/Downloads/local
py311 -m pytest testing/v10_harness/tests/test_router.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd /c/Users/anand/Downloads/v10_reports_bot
git add agents/router.py
git commit -m "feat(router): deterministic signature router (5 Day-5 reports)"
cd /c/Users/anand/Downloads/local
git add testing/v10_harness/tests/test_router.py
git commit -m "test(router): cover deterministic match, derived fallback, param extraction"
```

### Task 5.5: Write `agents/idre_api_client.py`

**Files:**
- Create: `C:\Users\anand\Downloads\v10_reports_bot\agents\idre_api_client.py`
- Test: `C:\Users\anand\Downloads\local\testing\v10_harness\tests\test_idre_api_client.py`

- [ ] **Step 1: Write the failing test**

Create `testing/v10_harness/tests/test_idre_api_client.py`:

```python
import sys
import pytest
sys.path.insert(0, "C:/Users/anand/Downloads/v10_reports_bot")
from agents.idre_api_client import IdreApiClient, KNOWN_ENDPOINTS


def test_known_endpoints_for_day5_reports():
    for rid in ["due-dates", "outstanding-payments", "case-balance", "dashboard-stats", "cms-payments"]:
        assert rid in KNOWN_ENDPOINTS


def test_client_call_dashboard_stats(idre_session):
    c = IdreApiClient(session=idre_session)
    resp = c.call("dashboard-stats", {})
    assert resp["status_code"] == 200
    assert "data" in resp["body"]
```

- [ ] **Step 2: Run, verify fail**

```bash
py311 -m pytest testing/v10_harness/tests/test_idre_api_client.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the client**

Create `C:\Users\anand\Downloads\v10_reports_bot\agents\idre_api_client.py`:

```python
"""Typed wrappers around IDRE's report endpoints."""
from __future__ import annotations
import os
import time
from dataclasses import dataclass
from typing import Any
import requests

IDRE_BASE_URL = os.environ.get("IDRE_BASE_URL", "http://localhost:3000")
DEFAULT_TIMEOUT_S = 300

KNOWN_ENDPOINTS = {
    "due-dates": "/api/reports/due-dates",
    "outstanding-payments": "/api/reports/outstanding-payments",
    "case-balance": "/api/reports/case-balance",
    "dashboard-stats": "/api/reports/dashboard-stats",
    "cms-payments": "/api/reports/cms-payments",
    # Day 9 adds the remaining 9.
}


@dataclass
class IdreApiResponse:
    status_code: int
    body: Any
    latency_ms: float
    headers: dict

    def to_dict(self) -> dict:
        return {"status_code": self.status_code, "body": self.body, "latency_ms": self.latency_ms}


class IdreApiClient:
    def __init__(self, session: requests.Session | None = None, base_url: str = IDRE_BASE_URL):
        self.base_url = base_url
        self.session = session or self._auto_session()
        self._cache: dict[tuple, IdreApiResponse] = {}
        self._cache_ttl_s = 60.0
        self._cache_stamps: dict[tuple, float] = {}

    def _auto_session(self) -> requests.Session:
        s = requests.Session()
        r = s.get(f"{self.base_url}/api/dev/auto-login", allow_redirects=True, timeout=30)
        r.raise_for_status()
        return s

    def call(self, report_id: str, params: dict) -> dict:
        if report_id not in KNOWN_ENDPOINTS:
            raise KeyError(f"unknown report_id: {report_id}")
        key = (report_id, tuple(sorted((k, str(v)) for k, v in params.items())))
        now = time.monotonic()
        if key in self._cache and (now - self._cache_stamps[key]) < self._cache_ttl_s:
            return self._cache[key].to_dict()
        path = KNOWN_ENDPOINTS[report_id]
        url = self.base_url + path
        start = time.monotonic()
        r = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT_S)
        latency = (time.monotonic() - start) * 1000
        try:
            body = r.json()
        except Exception:
            body = {"_raw": r.text[:2000]}
        resp = IdreApiResponse(r.status_code, body, latency, dict(r.headers))
        self._cache[key] = resp
        self._cache_stamps[key] = now
        return resp.to_dict()


def idre_api_client_node(state: dict) -> dict:
    """LangGraph node: only runs when router_decision.path == 'known'."""
    rd = state.get("router_decision", {})
    if rd.get("path") != "known":
        return state
    client = IdreApiClient()
    resp = client.call(rd["report"], rd.get("parameters", {}))
    return {**state, "idre_api_response": resp}
```

- [ ] **Step 4: Run, verify pass**

```bash
py311 -m pytest testing/v10_harness/tests/test_idre_api_client.py -v
```

Expected: 2 passed (idre_session fixture needs IDRE local server running).

- [ ] **Step 5: Commit**

```bash
cd /c/Users/anand/Downloads/v10_reports_bot
git add agents/idre_api_client.py
git commit -m "feat(known-path): IdreApiClient with 5 Day-5 endpoints + 60s cache"
cd /c/Users/anand/Downloads/local
git add testing/v10_harness/tests/test_idre_api_client.py
git commit -m "test(known-path): coverage for endpoint catalog + live call"
```

### Task 5.6: Write `agents/parameter_extractor.py` and `agents/response_normalizer.py`

**Files:**
- Create: `C:\Users\anand\Downloads\v10_reports_bot\agents\parameter_extractor.py`
- Create: `C:\Users\anand\Downloads\v10_reports_bot\agents\response_normalizer.py`
- Test: `C:\Users\anand\Downloads\local\testing\v10_harness\tests\test_param_extractor.py`

- [ ] **Step 1: Write the failing test for parameter_extractor**

Create `tests/test_param_extractor.py`:

```python
import sys
from datetime import datetime, timezone
sys.path.insert(0, "C:/Users/anand/Downloads/v10_reports_bot")
from agents.parameter_extractor import resolve_date_phrase, extract_search_term


def test_resolve_date_today():
    now = datetime(2026, 5, 15, 14, 0, 0, tzinfo=timezone.utc)
    d = resolve_date_phrase("today", now)
    assert d["startDate"].startswith("2026-05-15")
    assert d["endDate"].startswith("2026-05-15")


def test_resolve_date_mtd():
    now = datetime(2026, 5, 15, 14, 0, 0, tzinfo=timezone.utc)
    d = resolve_date_phrase("month-to-date", now)
    assert d["startDate"].startswith("2026-05-01")


def test_resolve_date_last_7_days():
    now = datetime(2026, 5, 15, 14, 0, 0, tzinfo=timezone.utc)
    d = resolve_date_phrase("last 7 days", now)
    assert d["startDate"].startswith("2026-05-08") or d["startDate"].startswith("2026-05-09")


def test_extract_search_term_capitol_bridge():
    assert extract_search_term("show payouts to Capitol Bridge").lower() == "capitol bridge"


def test_extract_search_term_none():
    assert extract_search_term("show all cases") is None
```

- [ ] **Step 2: Implement**

Create `C:\Users\anand\Downloads\v10_reports_bot\agents\parameter_extractor.py`:

```python
"""NL → IDRE API query parameters. EST-aware date math."""
from __future__ import annotations
import re
from datetime import datetime, timedelta, timezone

ENTITY_PATTERNS = [
    r"capitol bridge", r"halo", r"veratru", r"halomd",
    r"unitedhealthcare", r"uhc", r"pacifichealth",
]


def resolve_date_phrase(phrase: str, now: datetime) -> dict:
    """Return {startDate, endDate} ISO strings for a NL date phrase."""
    p = phrase.lower().strip()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if p in ("today",):
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    elif p in ("yesterday",):
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    elif p in ("this week",):
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif p in ("last 7 days", "past 7 days", "previous 7 days"):
        start = now - timedelta(days=7)
        end = now
    elif p in ("month-to-date", "mtd", "this month"):
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif p in ("last month",):
        first_of_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_end = first_of_this - timedelta(seconds=1)
        start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = first_of_this
    else:
        return {}
    return {
        "startDate": start.isoformat().replace("+00:00", "Z"),
        "endDate": end.isoformat().replace("+00:00", "Z"),
    }


def extract_search_term(query: str) -> str | None:
    q = query.lower()
    for pat in ENTITY_PATTERNS:
        m = re.search(pat, q, re.IGNORECASE)
        if m:
            return m.group(0)
    return None
```

Create `C:\Users\anand\Downloads\v10_reports_bot\agents\response_normalizer.py`:

```python
"""Normalize IDRE API response shapes into {rows, meta}."""


def normalize(response_body: dict) -> dict:
    """Best-effort flattening. Returns {"rows": [...], "meta": {...}}."""
    data = response_body.get("data", response_body)
    rows: list = []
    meta: dict = {}
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        # Find the obvious row array
        for key in ("cases", "payments", "payouts", "disputes", "activities", "rows", "items"):
            if key in data and isinstance(data[key], list):
                rows = data[key]
                meta = {k: v for k, v in data.items() if k != key}
                break
        else:
            # No row array; treat the whole dict as a single-row aggregate
            rows = [data]
            meta = {}
    return {"rows": rows, "meta": meta}
```

- [ ] **Step 3: Run param-extractor tests**

```bash
py311 -m pytest testing/v10_harness/tests/test_param_extractor.py -v
```

Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
cd /c/Users/anand/Downloads/v10_reports_bot
git add agents/parameter_extractor.py agents/response_normalizer.py
git commit -m "feat(known-path): parameter extractor + response normalizer"
cd /c/Users/anand/Downloads/local
git add testing/v10_harness/tests/test_param_extractor.py
git commit -m "test(known-path): parameter extractor coverage"
```

### Task 5.7: Wire V10 into a `harness_entrypoint.py`

**Files:**
- Create: `C:\Users\anand\Downloads\v10_reports_bot\harness_entrypoint.py`

- [ ] **Step 1: Write the entrypoint**

```python
"""V10 single-call entrypoint, harness-friendly.

Flow:
  1. Router decides path
  2. If known: idre_api_client → normalizer → return {data: body}
  3. If derived: V8-style SQL flow (will be replaced Days 7-8)
  4. If clarify: return immediate clarification error
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent.resolve()
os.chdir(str(HERE))
sys.path.insert(0, str(HERE))

from agents.router import route
from agents.idre_api_client import IdreApiClient
from agents.response_normalizer import normalize


def run_query_v10(prompt: str, now_anchor=None, user_role: str = "MA") -> dict:
    """Single-call run. If now_anchor is provided (testing), use its now()."""
    rd = route(prompt)
    if rd.path == "known":
        client = IdreApiClient()
        resp = client.call(rd.report, rd.parameters)
        return {
            "router_decision": {
                "path": rd.path, "report": rd.report,
                "parameters": rd.parameters, "confidence": rd.confidence,
            },
            "data": resp["body"].get("data", resp["body"]),
            "normalized": normalize(resp["body"]),
            "idre_status": resp["status_code"],
        }
    elif rd.path == "clarify":
        return {
            "router_decision": {"path": "clarify", "confidence": rd.confidence},
            "data": None,
            "error": "clarification_required",
        }
    else:
        # Derived — defer to V8 path for Day 5; will be replaced Days 7-8
        sys.path.insert(0, "/c/Users/anand/Downloads/v8_reports_bot")
        from harness_entrypoint import run as v8_run
        r = v8_run(prompt)
        return {
            "router_decision": {"path": "derived", "confidence": rd.confidence},
            "data": r.get("data", []),
            "sql": r.get("sql", ""),
            "row_count": r.get("row_count", 0),
        }
```

- [ ] **Step 2: Smoke test**

```bash
py311 -c "
import sys; sys.path.insert(0, '/c/Users/anand/Downloads/v10_reports_bot')
from harness_entrypoint import run_query_v10
r = run_query_v10('show me the dashboard overview')
print('router:', r['router_decision'])
print('idre_status:', r.get('idre_status'))
"
```

Expected: router path=known, report=dashboard-stats, status 200.

- [ ] **Step 3: Commit**

```bash
cd /c/Users/anand/Downloads/v10_reports_bot
git add harness_entrypoint.py
git commit -m "feat: V10 harness entrypoint with router + known/derived dispatch"
git tag day5-bootstrap
```

### Task 5.8: Run the Day-5 baseline (V10 vs V8 on 10 known-report tests)

- [ ] **Step 1: Run both bots**

```bash
cd /c/Users/anand/Downloads/local
BOT=v10 py311 -m pytest testing/v10_harness/tests/test_baseline_known.py -v --tb=short -o log_cli=true 2>&1 | tee /tmp/v10_day5.log
```

- [ ] **Step 2: Compare baselines**

```bash
py311 -c "
import json, glob
v8_summary = json.load(open('testing/v10_harness/reports/baseline/SUMMARY.json'))
v10_results = [json.load(open(p)) for p in glob.glob('testing/v10_harness/reports/K_*.json')]
def by_id(rs): return {r['id']: r for r in rs}
v8 = by_id(v8_summary['results'])
v10 = by_id(v10_results)
print(f'{\"ID\":<22} {\"V8\":<8} {\"V10\":<8}')
for k in sorted(set(v8) | set(v10)):
    print(f'{k:<22} {v8.get(k,{}).get(\"verdict\",\"-\"):<8} {v10.get(k,{}).get(\"verdict\",\"-\"):<8}')
"
```

Expected: V10 should PASS on all 5 Day-5 reports (and possibly more). V8 will FAIL most.

- [ ] **Step 3: Save Day-5 results**

```bash
mkdir -p testing/v10_harness/reports/day5
cp testing/v10_harness/reports/K_*.json testing/v10_harness/reports/day5/
git add testing/v10_harness/reports/day5/
git commit -m "test: V10 Day-5 baseline (5 known-report wrappers)"
git tag day5-complete
```

---

## Day 6: Expand Test Set + Run Combined V8/V10

### Task 6.1: Add 30 more known-report tests (3 more per Day-5 report + smoke tests for the other 9)

**Files:**
- Modify: `C:\Users\anand\Downloads\local\testing\v10_harness\test_set.jsonl`

- [ ] **Step 1: Append additional entries**

Append these lines to `test_set.jsonl`:

```jsonl
{"id":"K_due_003","category":"known-report","report":"due-dates","prompt":"cases overdue in eligibility review","expected_idre_call":{"method":"GET","path":"/api/reports/due-dates","query":{"urgency":"overdue","limit":"10000"}},"compare_fields":["data.cases[*].eligibilityDueDate"],"temporality":"variant"}
{"id":"K_due_004","category":"known-report","report":"due-dates","prompt":"show top 25 most urgent due dates","expected_idre_call":{"method":"GET","path":"/api/reports/due-dates","query":{"urgency":"urgent","limit":"25"}},"compare_fields":["data.totalCount","data.cases[*].caseId"],"temporality":"variant"}
{"id":"K_due_005","category":"known-report","report":"due-dates","prompt":"all cases regardless of urgency","expected_idre_call":{"method":"GET","path":"/api/reports/due-dates","query":{"urgency":"all","limit":"10000"}},"compare_fields":["data.totalCount"],"temporality":"variant"}
{"id":"K_out_002","category":"known-report","report":"outstanding-payments","prompt":"outstanding payments where IP has not paid","expected_idre_call":{"method":"GET","path":"/api/reports/outstanding-payments","query":{"limit":"10000"}},"compare_fields":["data.totalCount","data.cases[*].caseId"],"temporality":"variant"}
{"id":"K_out_003","category":"known-report","report":"outstanding-payments","prompt":"top 50 outstanding payments by amount","expected_idre_call":{"method":"GET","path":"/api/reports/outstanding-payments","query":{"limit":"50"}},"compare_fields":["data.cases[*].caseId"],"temporality":"variant"}
{"id":"K_bal_002","category":"known-report","report":"case-balance","prompt":"which cases have a negative balance","expected_idre_call":{"method":"GET","path":"/api/reports/case-balance","query":{"limit":"10000"}},"compare_fields":["data.cases[*].caseId","data.cases[*].balanceCents"],"temporality":"variant"}
{"id":"K_bal_003","category":"known-report","report":"case-balance","prompt":"show total balance across active cases","expected_idre_call":{"method":"GET","path":"/api/reports/case-balance","query":{"limit":"10000"}},"compare_fields":["data.totalBalance"],"temporality":"variant"}
{"id":"K_dash_002","category":"known-report","report":"dashboard-stats","prompt":"how many active arbitrators","expected_idre_call":{"method":"GET","path":"/api/reports/dashboard-stats","query":{}},"compare_fields":["data.activeArbitrators"],"temporality":"variant"}
{"id":"K_dash_003","category":"known-report","report":"dashboard-stats","prompt":"total payment volume this month vs last","expected_idre_call":{"method":"GET","path":"/api/reports/dashboard-stats","query":{}},"compare_fields":["data.currentMonthPayments","data.previousMonthPayments"],"temporality":"variant"}
{"id":"K_cms_002","category":"known-report","report":"cms-payments","prompt":"CMS payments pending vs completed","expected_idre_call":{"method":"GET","path":"/api/reports/cms-payments","query":{}},"compare_fields":["data.byStatus"],"temporality":"variant"}
{"id":"K_cms_003","category":"known-report","report":"cms-payments","prompt":"total CMS admin fee collected","expected_idre_call":{"method":"GET","path":"/api/reports/cms-payments","query":{}},"compare_fields":["data.totalAmount"],"temporality":"variant"}
```

(That's 11 more known-report tests, bringing total to 21 known.)

Now add 9 derived-query tests (the first batch — more come Day 10):

```jsonl
{"id":"D_total_001","category":"derived-query","prompt":"how many total cases are there","ground_truth_sql":[{"name":"total","sql":"SELECT COUNT(*) AS v FROM `case`"}],"bot_must_return_keys":["total"],"temporality":"stable"}
{"id":"D_mtd_001","category":"derived-query","prompt":"how many cases were created this month so far","ground_truth_sql":[{"name":"mtd","sql":"SELECT COUNT(*) AS v FROM `case` WHERE createdAt >= DATE_FORMAT(:now, '%Y-%m-01 00:00:00')"}],"bot_must_return_keys":["mtd"],"temporality":"variant"}
{"id":"D_today_001","category":"derived-query","prompt":"how many new disputes today","ground_truth_sql":[{"name":"today","sql":"SELECT COUNT(*) AS v FROM `case` WHERE DATE(createdAt) = DATE(:now)"}],"bot_must_return_keys":["today"],"temporality":"variant"}
{"id":"D_pending_rfi_001","category":"derived-query","prompt":"disputes in pending RFI status","ground_truth_sql":[{"name":"pending_rfi","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='PENDING_RFI'"}],"bot_must_return_keys":["pending_rfi"],"temporality":"stable"}
{"id":"D_pending_pay_001","category":"derived-query","prompt":"disputes in payment pending status","ground_truth_sql":[{"name":"payment_pending","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='PENDING_PAYMENTS'"}],"bot_must_return_keys":["payment_pending"],"temporality":"stable"}
{"id":"D_pending_second_001","category":"derived-query","prompt":"disputes pending second payments","ground_truth_sql":[{"name":"pending_second","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='PENDING_SECOND_PAYMENT'"}],"bot_must_return_keys":["pending_second"],"temporality":"stable"}
{"id":"D_initial_elig_001","category":"derived-query","prompt":"cases in initial eligibility review","ground_truth_sql":[{"name":"initial_eligibility_review","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='INITIAL_ELIGIBILITY_REVIEW'"}],"bot_must_return_keys":["initial_eligibility_review"],"temporality":"stable"}
{"id":"D_ineligible_admin_001","category":"derived-query","prompt":"how many cases are ineligible pending admin fee","ground_truth_sql":[{"name":"ineligible_admin","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='INELIGIBLE_PENDING_ADMIN_FEE'"}],"bot_must_return_keys":["ineligible_admin"],"temporality":"stable"}
{"id":"D_closed_001","category":"derived-query","prompt":"how many disputes are closed","ground_truth_sql":[{"name":"closed","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status IN ('CLOSED','INELIGIBLE_PENDING_ADMIN_FEE','PENDING_ADMINISTRATIVE_CLOSURE','COMPLETED')"}],"bot_must_return_keys":["closed"],"temporality":"stable"}
```

(9 derived = 30 total prompts in the test set now.)

- [ ] **Step 2: Validate JSONL**

```bash
py311 -c "
import json
n = 0
with open('testing/v10_harness/test_set.jsonl') as f:
    for line in f:
        if line.strip():
            json.loads(line); n += 1
print(f'{n} valid entries')
"
```

Expected: `30 valid entries`.

- [ ] **Step 3: Commit**

```bash
git add testing/v10_harness/test_set.jsonl
git commit -m "test(set): expand to 30 prompts (21 known + 9 derived)"
```

### Task 6.2: Add `tests/test_baseline_derived.py`

**Files:**
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\tests\test_baseline_derived.py`

- [ ] **Step 1: Write the parametrized test**

```python
"""Parametrized run of derived-query tests."""
import json
import os
import sys
from pathlib import Path
import pytest

from testing.v10_harness.runner import (
    TestRecord, run_derived_query_test, TestResult,
)
from testing.v10_harness.compare import Verdict


HARNESS = Path(__file__).parent.parent
TEST_SET = HARNESS / "test_set.jsonl"
REPORTS_DIR = HARNESS / "reports"


def _derived_records() -> list[TestRecord]:
    out = []
    with open(TEST_SET) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("category") == "derived-query":
                out.append(TestRecord.from_dict(d))
    return out


@pytest.fixture(scope="session")
def bot_derived_runner():
    """Return a callable that returns a dict keyed by required names.

    The derived path returns rows from SQL execution. For our test set, each
    prompt asks a single aggregate, so we wrap the bot's row_count or first
    column value into a dict under the bot_must_return_keys name(s)."""
    which = os.environ.get("BOT", "v10")
    if which == "v8":
        sys.path.insert(0, "C:/Users/anand/Downloads/v8_reports_bot")
        from harness_entrypoint import run as bot_run
    else:
        sys.path.insert(0, "C:/Users/anand/Downloads/v10_reports_bot")
        from harness_entrypoint import run_query_v10 as bot_run_v10
        bot_run = lambda p: bot_run_v10(p)

    def runner(prompt: str, now):
        r = bot_run(prompt)
        data = r.get("data", [])
        # Single-aggregate convention: first column of first row
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict) and first:
                val = list(first.values())[0]
                return {"v": val}
        return {}
    return runner


@pytest.mark.parametrize("record", _derived_records(), ids=[r.id for r in _derived_records()])
def test_derived(record, bot_derived_runner, staging_engine, now_anchor):
    # The bot returns {"v": <number>}; we remap to the expected key
    bot_raw = bot_derived_runner(record.prompt, now_anchor)
    bot_dict = {k: bot_raw.get("v") for k in record.bot_must_return_keys}

    # Reuse the runner's compute path manually
    from sqlalchemy import text
    expected = {}
    with staging_engine.connect() as c:
        for entry in record.ground_truth_sql:
            bound = now_anchor.bind_sql(entry["sql"])
            row = c.execute(text(bound["sql"]), bound["params"]).mappings().first()
            expected[entry["name"]] = row["v"] if row and "v" in row else None

    from testing.v10_harness.compare import compare_aggregates
    result = compare_aggregates(bot_dict, expected)

    REPORTS_DIR.mkdir(exist_ok=True)
    out = REPORTS_DIR / f"{record.id}.json"
    with open(out, "w") as f:
        json.dump({
            "id": record.id,
            "verdict": result.verdict.value,
            "diffs": result.diff,
            "bot": bot_dict,
            "expected": expected,
        }, f, indent=2, default=str)
    assert result.verdict == Verdict.PASS, f"{record.id}: {result.diff}"
```

- [ ] **Step 2: Collect-only**

```bash
py311 -m pytest testing/v10_harness/tests/test_baseline_derived.py --collect-only
```

Expected: 9 derived test items collected.

- [ ] **Step 3: Run derived against V8**

```bash
BOT=v8 py311 -m pytest testing/v10_harness/tests/test_baseline_derived.py -v --tb=short
```

Expected: many failures — V8 SQL won't match exact counts because of stale knowledge.

- [ ] **Step 4: Run derived against V10 (still using V8 derived path under the hood at this stage)**

```bash
BOT=v10 py311 -m pytest testing/v10_harness/tests/test_baseline_derived.py -v --tb=short
```

Expected: similar to V8 for derived path (Days 7-8 fix it).

- [ ] **Step 5: Commit**

```bash
git add testing/v10_harness/tests/test_baseline_derived.py
git commit -m "test: add parametrized derived-query test runner"
git tag day6-complete
```

---

## Day 7–8: SQL Writer Rewrite + 3 New Tools

This is where the derived path gets its real V10 upgrade.

### Task 7.1: Rewrite `tools/idre_tools.py` to read from `knowledge/v10/`

**Files:**
- Modify: `C:\Users\anand\Downloads\v10_reports_bot\tools\idre_tools.py`

- [ ] **Step 1: Replace the file wholesale**

Open `tools/idre_tools.py` and replace its contents with:

```python
"""V10 MCP tools — read from knowledge/v10/, no static legacy artifacts."""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
from typing import Any

import google.generativeai as genai
from sqlalchemy import text

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge" / "v10"


_business_logic_cache: dict | None = None
_schema_catalog_cache: dict | None = None
_enum_catalog_cache: dict | None = None
_filter_patterns_cache: dict | None = None
_glossary_cache: list | None = None


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _bl() -> dict:
    global _business_logic_cache
    if _business_logic_cache is None:
        _business_logic_cache = _load(KNOWLEDGE_DIR / "business_logic.json")
    return _business_logic_cache


def _schema() -> dict:
    global _schema_catalog_cache
    if _schema_catalog_cache is None:
        _schema_catalog_cache = _load(KNOWLEDGE_DIR / "schema_catalog.json")
    return _schema_catalog_cache


def _enums() -> dict:
    global _enum_catalog_cache
    if _enum_catalog_cache is None:
        _enum_catalog_cache = _load(KNOWLEDGE_DIR / "enum_catalog.json")
    return _enum_catalog_cache


def _glossary() -> list:
    global _glossary_cache
    if _glossary_cache is None:
        cfg = Path(__file__).parent.parent / "config" / "business_glossary.json"
        if cfg.exists():
            data = _load(cfg)
            _glossary_cache = data.get("terms", [])
        else:
            _glossary_cache = []
    return _glossary_cache


def _filter_patterns() -> dict:
    """Inline patterns (Day 7); could be a separate file later."""
    return {
        "today":            "DATE(:col) = DATE(:now)",
        "yesterday":        "DATE(:col) = DATE_SUB(DATE(:now), INTERVAL 1 DAY)",
        "this week":        ":col >= DATE_SUB(:now, INTERVAL WEEKDAY(:now) DAY)",
        "last 7 days":      ":col >= DATE_SUB(:now, INTERVAL 7 DAY)",
        "month-to-date":    ":col >= DATE_FORMAT(:now, '%Y-%m-01 00:00:00')",
        "mtd":              ":col >= DATE_FORMAT(:now, '%Y-%m-01 00:00:00')",
        "this month":       ":col >= DATE_FORMAT(:now, '%Y-%m-01 00:00:00')",
        "last month":       ":col >= DATE_FORMAT(:now - INTERVAL 1 MONTH, '%Y-%m-01') AND :col < DATE_FORMAT(:now, '%Y-%m-01')",
        "this quarter":     ":col >= DATE_FORMAT(DATE_SUB(:now, INTERVAL ((MONTH(:now)-1) MOD 3) MONTH), '%Y-%m-01')",
    }


# ─── Tool 1: get_idre_business_logic ────────────────────────────────

def get_idre_business_logic(report_name: str) -> str:
    rid = report_name.lower().strip()
    for r in _bl().get("reports", []):
        if r.get("id", "").lower() == rid:
            return json.dumps({
                "id": r["id"],
                "prisma_query": r.get("prisma_query", ""),
                "js_postprocessing": r.get("js_postprocessing", ""),
                "sql_equivalent": r.get("sql_equivalent", ""),
                "notes": r.get("notes", ""),
            }, indent=2)
    available = [r["id"] for r in _bl().get("reports", [])]
    return f"Report '{report_name}' not found. Available: {', '.join(available)}"


# ─── Tool 2: get_report_reference (alias, returns reference card metadata) ───

def get_report_reference(report_name: str) -> str:
    return get_idre_business_logic(report_name)


# ─── Tool 3: get_table_schema ────────────────────────────────────────

def get_table_schema(table_name: str) -> str:
    name = table_name.lower().strip()
    for m in _schema().get("models", []):
        if m.get("table_name", "").lower() == name:
            return json.dumps(m, indent=2)
    available = sorted({m.get("table_name", "") for m in _schema().get("models", [])})
    return f"Table '{table_name}' not found. Available: {', '.join(available)}"


# ─── Tool 4: get_enum_values ─────────────────────────────────────────

def get_enum_values(column_path: str) -> str:
    p = column_path.lower().strip().replace("`", "")
    rds = _enums().get("rds_sampled", {})
    if p in rds:
        return json.dumps({"source": "rds_sampled", "values": rds[p]}, indent=2)
    # fallback to TS enums
    ts = _enums().get("typescript_enums", {})
    for name, vals in ts.items():
        if name.lower() == p or p.endswith(name.lower()):
            return json.dumps({"source": "ts_enum", "name": name, "values": vals}, indent=2)
    return f"No enum mapping for '{column_path}'. Available rds-sampled: {', '.join(sorted(rds.keys()))}"


# ─── Tool 5: lookup_business_term ────────────────────────────────────

def lookup_business_term(term: str) -> str:
    t = term.lower().strip()
    for e in _glossary():
        syns = [s.lower() for s in e.get("synonyms", [])]
        if e.get("term", "").lower() == t or t in syns:
            return json.dumps(e, indent=2)
    return f"Term '{term}' not found in glossary."


# ─── Tool 6: list_available_reports ──────────────────────────────────

def list_available_reports() -> str:
    out = []
    for r in _bl().get("reports", []):
        out.append({"id": r.get("id"), "endpoint": f"/api/reports/{r.get('id')}"})
    return json.dumps(out, indent=2)


# ─── Tool 7: find_filter_pattern ─────────────────────────────────────

def find_filter_pattern(intent: str) -> str:
    intent_norm = intent.lower().strip()
    pats = _filter_patterns()
    if intent_norm in pats:
        return json.dumps({
            "intent": intent_norm,
            "sql_template": pats[intent_norm],
            "notes": "Replace :col with the actual datetime column; :now is supplied at execution time as the request anchor.",
        }, indent=2)
    return f"No pattern for '{intent}'. Known: {', '.join(pats.keys())}"


# ─── Tool 8: verify_sql_executes ─────────────────────────────────────

def verify_sql_executes(sql: str) -> str:
    """EXPLAIN first, then dry-run with LIMIT 5 on read replica."""
    import os, sys
    sys.path.insert(0, "C:/Users/anand/Downloads/v10_reports_bot")
    os.chdir("C:/Users/anand/Downloads/v10_reports_bot")
    from db.connector import get_engine
    eng = get_engine()
    out: dict[str, Any] = {"sql": sql[:300], "ok": False}
    try:
        with eng.connect() as conn:
            t0 = time.monotonic()
            conn.execute(text(f"EXPLAIN {sql}"))
            test_sql = sql.rstrip(";\n ") + " LIMIT 5"
            rows = conn.execute(text(test_sql)).mappings().all()
            out["ok"] = True
            out["sample_row_count"] = len(rows)
            out["columns"] = list(rows[0].keys()) if rows else []
            out["exec_ms"] = round((time.monotonic() - t0) * 1000, 1)
    except Exception as e:
        out["error"] = str(e)[:500]
    return json.dumps(out, indent=2)


# ─── Tool Definitions for Gemini Function Calling ────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "get_idre_business_logic",
        "description": "Get the full Prisma + JS post-processing + SQL equivalent for a known IDRE report. Call this FIRST if the user's question maps to any IDRE report.",
        "parameters": {"type": "object", "properties": {
            "report_name": {"type": "string", "description": "Report id, e.g. 'due-dates', 'outstanding-payments'."}
        }, "required": ["report_name"]},
    },
    {
        "name": "get_table_schema",
        "description": "Get the schema for a single MySQL table — column names, types, optional flags.",
        "parameters": {"type": "object", "properties": {
            "table_name": {"type": "string", "description": "Table name e.g. 'case' or 'payment'."}
        }, "required": ["table_name"]},
    },
    {
        "name": "get_enum_values",
        "description": "Get the valid enum values for a database column. Always prefer the rds_sampled source.",
        "parameters": {"type": "object", "properties": {
            "column_path": {"type": "string", "description": "Dot-notation e.g. 'case.status' or 'payment.type'."}
        }, "required": ["column_path"]},
    },
    {
        "name": "lookup_business_term",
        "description": "Look up a domain term in the IDRE glossary.",
        "parameters": {"type": "object", "properties": {
            "term": {"type": "string", "description": "Term e.g. 'CMS payment', 'outstanding'."}
        }, "required": ["term"]},
    },
    {
        "name": "list_available_reports",
        "description": "List all known IDRE reports with their endpoints.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "find_filter_pattern",
        "description": "Get the SQL date expression for a NL date phrase (today, mtd, last 7 days, etc.).",
        "parameters": {"type": "object", "properties": {
            "intent": {"type": "string", "description": "Date phrase e.g. 'month-to-date'."}
        }, "required": ["intent"]},
    },
    {
        "name": "verify_sql_executes",
        "description": "Run EXPLAIN then a LIMIT-5 dry run of the SQL on the read replica. Returns columns + sample row count or the error message. Call BEFORE returning the SQL as final.",
        "parameters": {"type": "object", "properties": {
            "sql": {"type": "string", "description": "MySQL SELECT statement to validate."}
        }, "required": ["sql"]},
    },
    {
        "name": "get_report_reference",
        "description": "Alias for get_idre_business_logic. Retained for backward compatibility within V10.",
        "parameters": {"type": "object", "properties": {
            "report_name": {"type": "string"}
        }, "required": ["report_name"]},
    },
]

TOOL_DISPATCH = {
    "get_idre_business_logic": get_idre_business_logic,
    "get_report_reference": get_report_reference,
    "get_table_schema": get_table_schema,
    "get_enum_values": get_enum_values,
    "lookup_business_term": lookup_business_term,
    "list_available_reports": list_available_reports,
    "find_filter_pattern": find_filter_pattern,
    "verify_sql_executes": verify_sql_executes,
}
```

- [ ] **Step 2: Smoke-test each tool**

```bash
cd /c/Users/anand/Downloads/v10_reports_bot
py311 -c "
from tools.idre_tools import (
    get_idre_business_logic, get_table_schema, get_enum_values,
    find_filter_pattern, verify_sql_executes, list_available_reports,
)
print('--- business_logic(due-dates) ---'); print(get_idre_business_logic('due-dates')[:400])
print('--- schema(case) ---'); print(get_table_schema('case')[:300])
print('--- enum(case.status) ---'); print(get_enum_values('case.status')[:300])
print('--- filter(month-to-date) ---'); print(find_filter_pattern('month-to-date'))
print('--- verify(SELECT 1) ---'); print(verify_sql_executes('SELECT 1'))
print('--- list_reports ---'); print(list_available_reports()[:200])
"
```

Expected: each tool returns sensible output. `verify_sql_executes('SELECT 1')` returns `"ok": true`.

- [ ] **Step 3: Commit**

```bash
git add tools/idre_tools.py
git commit -m "feat(tools): V10 8-tool catalog reading from knowledge/v10/"
```

### Task 7.2: Rewrite `agents/sql_writer.py` system prompt + drop legacy paths

**Files:**
- Modify: `C:\Users\anand\Downloads\v10_reports_bot\agents\sql_writer.py`

- [ ] **Step 1: Replace the system prompt and gut the legacy methods**

Open `agents/sql_writer.py`. Replace the existing `SYSTEM_PROMPT` constant with:

```python
SYSTEM_PROMPT = """You are a MySQL expert writing SELECT queries for the IDRE healthcare dispute resolution platform.

HARD RULES
- SELECT-only. No INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE.
- Always backtick `case` (MySQL reserved word).
- Do NOT add LIMIT unless the user asks for a top-N.

MANDATORY PROTOCOL
1. If the user's intent matches a known IDRE report, call `get_idre_business_logic` first and use its `sql_equivalent` as your starting point.
2. Use `get_table_schema` to confirm column names before writing SQL.
3. Use `get_enum_values` for any status/type column you reference.
4. Use `find_filter_pattern` for date phrases ("today", "month-to-date", "last 7 days").
5. Before declaring SQL final, call `verify_sql_executes`. If it returns an error, fix and re-verify. Max 3 verification rounds.

OUTPUT
<final SQL>

ASSUMPTIONS:
- <one line per assumption>
"""
```

- [ ] **Step 2: Remove `_check_metric_cards` and `_check_sql_templates` calls**

In `sql_writer.py`, find the section that calls `_check_metric_cards(query)` and `_check_sql_templates(query)`. Delete those calls and their function definitions. Also delete:

- `METRIC_CARDS_PATH` and `SQL_TEMPLATES_PATH` module-level constants
- The `save_successful_query` function
- Any reference to `SUCCESSFUL_QUERIES_PATH`

- [ ] **Step 3: Update Gemini model name**

Change `model_name="gemini-3.1-pro-preview"` to `model_name="gemini-2.5-pro-preview"` in `_generate_sql_with_tools`.

- [ ] **Step 4: Smoke test by running a simple prompt through V10's harness**

```bash
cd /c/Users/anand/Downloads/v10_reports_bot
py311 -c "
import os, sys; sys.path.insert(0, '.'); os.chdir('.')
from harness_entrypoint import run_query_v10
r = run_query_v10('how many cases are pending RFI')
print('router_path:', r['router_decision']['path'])
print('sql:', r.get('sql', 'no sql')[:200])
print('row_count:', r.get('row_count'))
"
```

Expected: router routes to "derived"; SQL produced uses `status='PENDING_RFI'`; row count is non-zero.

- [ ] **Step 5: Commit**

```bash
git add agents/sql_writer.py
git commit -m "feat(sql-writer): V10 system prompt; remove metric_cards/sql_templates/successful_queries"
```

### Task 7.3: Remove `_COMMONLY_HALLUCINATED` and update `schema_verifier.py`

**Files:**
- Modify: `C:\Users\anand\Downloads\v10_reports_bot\agents\schema_verifier.py`

- [ ] **Step 1: Find and delete**

```bash
grep -n "_COMMONLY_HALLUCINATED" /c/Users/anand/Downloads/v10_reports_bot/agents/schema_verifier.py
```

Open `agents/schema_verifier.py`. Delete:
- The `_COMMONLY_HALLUCINATED` dict
- Any code that consults it
- Replace its use with a call to `verify_sql_executes` (delegated to the SQL writer's own protocol now)

- [ ] **Step 2: Verify imports still resolve**

```bash
py311 -c "from agents.schema_verifier import schema_verifier_node; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add agents/schema_verifier.py
git commit -m "refactor(schema-verifier): drop _COMMONLY_HALLUCINATED dict (replaced by verify_sql_executes tool)"
```

### Task 7.4: Modify `agents/executor.py` for the row-cap rules

**Files:**
- Modify: `C:\Users\anand\Downloads\v10_reports_bot\agents\executor.py`

- [ ] **Step 1: Find the cap constant**

```bash
grep -n "50000\|50_000\|MAX_ROWS\|ROW_LIMIT\|row.cap\|cap" /c/Users/anand/Downloads/v10_reports_bot/agents/executor.py
```

- [ ] **Step 2: Update**

Set the production cap to 100,000 and make it bypassable via env var:

```python
import os
DEFAULT_ROW_CAP = 100_000
ROW_CAP = int(os.environ.get("V10_ROW_CAP", DEFAULT_ROW_CAP))
DISABLE_ROW_CAP = os.environ.get("V10_DISABLE_ROW_CAP", "").lower() in ("1", "true", "yes")
```

Find the place that truncates results and update to:

```python
if not DISABLE_ROW_CAP and len(rows) >= ROW_CAP:
    state["was_capped"] = True
    rows = rows[:ROW_CAP]
else:
    state["was_capped"] = False
```

- [ ] **Step 3: Update GraphState** to include `was_capped: bool`

Edit `state/context.py` and add `was_capped: bool` to the V10 additions block.

- [ ] **Step 4: Update the harness to set DISABLE_ROW_CAP**

Edit `testing/v10_harness/conftest.py` — add at top:

```python
os.environ["V10_DISABLE_ROW_CAP"] = "1"
```

- [ ] **Step 5: Commit**

```bash
cd /c/Users/anand/Downloads/v10_reports_bot
git add agents/executor.py state/context.py
git commit -m "feat(executor): production cap 50K→100K; tests bypass cap; was_capped flag in state"
cd /c/Users/anand/Downloads/local
git add testing/v10_harness/conftest.py
git commit -m "test(harness): disable row cap for all test runs"
```

### Task 7.5: Wire V10 LangGraph (or sequential) flow in `harness_entrypoint.py`

**Files:**
- Modify: `C:\Users\anand\Downloads\v10_reports_bot\harness_entrypoint.py`

- [ ] **Step 1: Replace the V8-fallback in the derived branch**

Open `harness_entrypoint.py` and replace the derived branch with V10's own pipeline:

```python
    else:
        # V10 derived path
        from state.context import GraphState
        from agents.context_loader import context_loader_node
        from agents.ambiguity_scorer import ambiguity_scorer_node
        from agents.schema_mapper import schema_mapper_node
        from agents.sql_writer import sql_writer_node
        from agents.sql_validator import sql_validator_node
        from agents.executor import executor_node
        from agents.output_formatter import output_formatter_node

        state: GraphState = {
            "user_query": prompt, "session_id": "harness", "user_role": user_role,
            "permitted_tables": [], "conversation_history": [],
            "resolved_query": prompt, "entity_registry": {},
            "router_decision": {"path": "derived"},
        }
        if now_anchor is not None:
            state["now_anchor_iso"] = now_anchor.now().isoformat()
        state = context_loader_node(state)
        state = ambiguity_scorer_node(state)
        state = schema_mapper_node(state)
        state = sql_writer_node(state)
        state = sql_validator_node(state)
        state = executor_node(state)
        state = output_formatter_node(state)
        return {
            "router_decision": {"path": "derived"},
            "data": state.get("query_result", []),
            "sql": state.get("generated_sql", ""),
            "row_count": state.get("row_count", 0),
            "was_capped": state.get("was_capped", False),
            "agent_trace": state.get("agent_trace", []),
        }
```

- [ ] **Step 2: Run the full Day-6 test set**

```bash
cd /c/Users/anand/Downloads/local
BOT=v10 py311 -m pytest testing/v10_harness/tests/test_baseline_known.py testing/v10_harness/tests/test_baseline_derived.py -v --tb=short 2>&1 | tee /tmp/v10_day8.log
```

Expected: known-report tests still pass (5 reports covered); derived tests should show significant improvement vs Day 6.

- [ ] **Step 3: Save Day-8 results**

```bash
mkdir -p testing/v10_harness/reports/day8
cp testing/v10_harness/reports/K_*.json testing/v10_harness/reports/D_*.json testing/v10_harness/reports/day8/
git add testing/v10_harness/reports/day8/
git commit -m "test: V10 Day-8 results (SQL writer rewrite + 3 new tools)"
git tag day8-complete
```

---

## Day 9: Expand Known-Report Wrappers to All 14 Reports

### Task 9.1: Append 9 more route signatures

**Files:**
- Modify: `C:\Users\anand\Downloads\v10_reports_bot\config\route_signatures.json`

- [ ] **Step 1: Append signatures**

Open `config/route_signatures.json`. Add these 9 signatures inside the `"signatures"` array:

```json
    {
      "id": "case-analytics",
      "trigger_phrases": ["case analytics", "case volume", "case trend", "case breakdown", "outcomes", "resolution time"],
      "required_entities": ["case"],
      "parameter_extractors": [],
      "idre_endpoint": "/api/reports/case-analytics",
      "method": "GET"
    },
    {
      "id": "team-performance",
      "trigger_phrases": ["team performance", "arbitrator performance", "caseload", "workload", "productivity", "cases per arbitrator"],
      "required_entities": ["user"],
      "parameter_extractors": [],
      "idre_endpoint": "/api/reports/team-performance",
      "method": "GET"
    },
    {
      "id": "unpaid-disputes",
      "trigger_phrases": ["unpaid dispute", "unpaid disputes", "dispute payment", "p=0", "neither party paid"],
      "required_entities": ["case", "payment"],
      "parameter_extractors": [
        {"name": "limit", "from_phrases": [{"match": "top\\s+(\\d+)", "extract_int": true}], "default": 10000}
      ],
      "idre_endpoint": "/api/reports/unpaid-disputes",
      "method": "GET"
    },
    {
      "id": "idre-payouts",
      "trigger_phrases": ["payout", "payouts", "halo", "veratru", "capitol bridge", "third-party payment"],
      "required_entities": ["payment"],
      "parameter_extractors": [
        {"name": "search", "regex": "(capitol bridge|halo|veratru|halomd|unitedhealthcare|uhc|pacifichealth)"},
        {"name": "limit", "from_phrases": [{"match": "top\\s+(\\d+)", "extract_int": true}], "default": 10000}
      ],
      "idre_endpoint": "/api/reports/idre-payouts",
      "method": "GET"
    },
    {
      "id": "auditing/daily-funds",
      "trigger_phrases": ["daily funds", "incoming funds", "outgoing funds", "net cash position", "cash position"],
      "required_entities": ["payment"],
      "parameter_extractors": [],
      "idre_endpoint": "/api/reports/auditing/daily-funds",
      "method": "GET"
    },
    {
      "id": "auditing/daily-transactions",
      "trigger_phrases": ["daily transaction", "daily transactions", "transactions today", "quickbooks", "7-digit"],
      "required_entities": ["payment"],
      "parameter_extractors": [],
      "idre_endpoint": "/api/reports/auditing/daily-transactions",
      "method": "GET"
    },
    {
      "id": "recent-activity",
      "trigger_phrases": ["recent activity", "recent activities", "activity feed", "latest activity", "latest changes"],
      "required_entities": ["case"],
      "parameter_extractors": [
        {"name": "limit", "from_phrases": [{"match": "top\\s+(\\d+)", "extract_int": true}], "default": 10000}
      ],
      "idre_endpoint": "/api/reports/recent-activity",
      "method": "GET"
    },
    {
      "id": "payment-variance",
      "trigger_phrases": ["payment variance", "variance", "reconcile", "reconciliation"],
      "required_entities": ["payment"],
      "parameter_extractors": [],
      "idre_endpoint": "/api/reports/payment-variance",
      "method": "GET"
    },
    {
      "id": "case-search",
      "trigger_phrases": ["search case", "find case", "look up dispute", "DISP-"],
      "required_entities": ["case"],
      "parameter_extractors": [
        {"name": "shortId", "regex": "DISP-([A-Z0-9]+)"}
      ],
      "idre_endpoint": "/api/reports/case-search",
      "method": "GET"
    }
```

(The 14th — case-search — is a defensive addition. Adjust if staging doesn't expose it; remove from this file if so.)

- [ ] **Step 2: Verify JSON parses**

```bash
py311 -c "import json; d = json.load(open('/c/Users/anand/Downloads/v10_reports_bot/config/route_signatures.json')); print(len(d['signatures']), 'signatures')"
```

Expected: `14 signatures` (or 13 if you removed case-search).

- [ ] **Step 3: Commit**

```bash
cd /c/Users/anand/Downloads/v10_reports_bot
git add config/route_signatures.json
git commit -m "feat(router): add 9 more route signatures (all 14 reports covered)"
```

### Task 9.2: Extend `KNOWN_ENDPOINTS` in `idre_api_client.py`

- [ ] **Step 1: Open `agents/idre_api_client.py` and update**

Replace the `KNOWN_ENDPOINTS` dict:

```python
KNOWN_ENDPOINTS = {
    "due-dates": "/api/reports/due-dates",
    "outstanding-payments": "/api/reports/outstanding-payments",
    "case-balance": "/api/reports/case-balance",
    "dashboard-stats": "/api/reports/dashboard-stats",
    "cms-payments": "/api/reports/cms-payments",
    "case-analytics": "/api/reports/case-analytics",
    "team-performance": "/api/reports/team-performance",
    "unpaid-disputes": "/api/reports/unpaid-disputes",
    "idre-payouts": "/api/reports/idre-payouts",
    "auditing/daily-funds": "/api/reports/auditing/daily-funds",
    "auditing/daily-transactions": "/api/reports/auditing/daily-transactions",
    "recent-activity": "/api/reports/recent-activity",
    "payment-variance": "/api/reports/payment-variance",
    "case-search": "/api/reports/case-search",
}
```

- [ ] **Step 2: Smoke test each endpoint reachability**

```bash
py311 -c "
import sys; sys.path.insert(0, '/c/Users/anand/Downloads/v10_reports_bot')
from agents.idre_api_client import IdreApiClient, KNOWN_ENDPOINTS
c = IdreApiClient()
for rid in KNOWN_ENDPOINTS:
    try:
        r = c.call(rid, {})
        print(f'{rid:35} HTTP {r[\"status_code\"]}')
    except Exception as e:
        print(f'{rid:35} ERR {str(e)[:80]}')
"
```

Expected: HTTP 200 for the 13 known endpoints; some 4xx/5xx is possible (parameters required) but no Python exceptions.

- [ ] **Step 3: Commit**

```bash
git add agents/idre_api_client.py
git commit -m "feat(known-path): extend endpoint catalog to all 14 reports"
```

### Task 9.3: Add 12 more known-report tests to test_set (2 per new report)

**Files:**
- Modify: `C:\Users\anand\Downloads\local\testing\v10_harness\test_set.jsonl`

- [ ] **Step 1: Append entries**

Append these to `test_set.jsonl`:

```jsonl
{"id":"K_analytics_001","category":"known-report","report":"case-analytics","prompt":"show case volume trends by month","expected_idre_call":{"method":"GET","path":"/api/reports/case-analytics","query":{}},"compare_fields":["data.caseVolumeTrends"],"temporality":"variant"}
{"id":"K_analytics_002","category":"known-report","report":"case-analytics","prompt":"breakdown of case outcomes IP vs NIP","expected_idre_call":{"method":"GET","path":"/api/reports/case-analytics","query":{}},"compare_fields":["data.outcomeAnalysis"],"temporality":"variant"}
{"id":"K_team_002","category":"known-report","report":"team-performance","prompt":"top 5 arbitrators by cases closed","expected_idre_call":{"method":"GET","path":"/api/reports/team-performance","query":{}},"compare_fields":["data.members[*].userId","data.members[*].caseCount"],"temporality":"variant"}
{"id":"K_unpaid_002","category":"known-report","report":"unpaid-disputes","prompt":"unpaid disputes by dispute type","expected_idre_call":{"method":"GET","path":"/api/reports/unpaid-disputes","query":{"limit":"10000"}},"compare_fields":["data.byDisputeType"],"temporality":"variant"}
{"id":"K_payouts_002","category":"known-report","report":"idre-payouts","prompt":"all payouts to Capitol Bridge","expected_idre_call":{"method":"GET","path":"/api/reports/idre-payouts","query":{"search":"capitol bridge","limit":"10000"}},"compare_fields":["data.payouts[*].paymentId","data.totalAmount"],"temporality":"variant"}
{"id":"K_payouts_003","category":"known-report","report":"idre-payouts","prompt":"total payouts to Halo and VeraTru","expected_idre_call":{"method":"GET","path":"/api/reports/idre-payouts","query":{"limit":"10000"}},"compare_fields":["data.totalAmount"],"temporality":"variant"}
{"id":"K_dfunds_001","category":"known-report","report":"auditing/daily-funds","prompt":"net cash position today","expected_idre_call":{"method":"GET","path":"/api/reports/auditing/daily-funds","query":{}},"compare_fields":["data.netPosition","data.incoming","data.outgoing"],"temporality":"variant"}
{"id":"K_dtxn_001","category":"known-report","report":"auditing/daily-transactions","prompt":"all transactions for today","expected_idre_call":{"method":"GET","path":"/api/reports/auditing/daily-transactions","query":{}},"compare_fields":["data.transactions[*].paymentId","data.totalCount"],"temporality":"variant"}
{"id":"K_activity_002","category":"known-report","report":"recent-activity","prompt":"recent status changes across all cases","expected_idre_call":{"method":"GET","path":"/api/reports/recent-activity","query":{"limit":"10000"}},"compare_fields":["data.activities[*].caseId","data.activities[*].action"],"temporality":"variant"}
{"id":"K_variance_001","category":"known-report","report":"payment-variance","prompt":"show payment variance report","expected_idre_call":{"method":"GET","path":"/api/reports/payment-variance","query":{}},"compare_fields":["data.totalVariance","data.cases[*].caseId"],"temporality":"variant"}
{"id":"K_variance_002","category":"known-report","report":"payment-variance","prompt":"cases with payment variance over $100","expected_idre_call":{"method":"GET","path":"/api/reports/payment-variance","query":{}},"compare_fields":["data.cases[*].caseId","data.cases[*].varianceAmount"],"temporality":"variant"}
{"id":"K_dash_004","category":"known-report","report":"dashboard-stats","prompt":"how many cases were created this month","expected_idre_call":{"method":"GET","path":"/api/reports/dashboard-stats","query":{}},"compare_fields":["data.currentMonthCases"],"temporality":"variant"}
```

- [ ] **Step 2: Validate JSONL**

```bash
cd /c/Users/anand/Downloads/local
py311 -c "
import json
counts = {'known-report': 0, 'derived-query': 0}
with open('testing/v10_harness/test_set.jsonl') as f:
    for line in f:
        if line.strip():
            d = json.loads(line)
            counts[d['category']] += 1
print(counts)
"
```

Expected: `{'known-report': 33, 'derived-query': 9}` (so 42 total at this point).

- [ ] **Step 3: Run**

```bash
BOT=v10 py311 -m pytest testing/v10_harness/tests/test_baseline_known.py -v --tb=short 2>&1 | tee /tmp/v10_day9.log
```

Expected: most pass. Any failure should be inspected — likely either `compare_fields` paths don't match staging's actual JSON shape (fix the test entry) or a report's wrapper isn't extracting parameters right (fix the signature).

- [ ] **Step 4: Commit**

```bash
git add testing/v10_harness/test_set.jsonl
git commit -m "test: 12 more known-report tests covering all 14 reports"
git tag day9-complete
```

---

## Day 10: Full Test Set + Triage + V10 Release

### Task 10.1: Add the remaining derived-query tests

**Files:**
- Modify: `C:\Users\anand\Downloads\local\testing\v10_harness\test_set.jsonl`

- [ ] **Step 1: Add 6 Ashlee-email-derived tests**

(Each Ashlee email status line becomes one prompt; the ground-truth SQL is what produces that line.)

Append:

```jsonl
{"id":"D_ashlee_001","category":"derived-query","prompt":"final eligibility review where both payments received","ground_truth_sql":[{"name":"final_elig_review_both_paid","sql":"SELECT COUNT(*) AS v FROM `case` c WHERE c.status='FINAL_ELIGIBILITY_REVIEW' AND EXISTS (SELECT 1 FROM case_payment_allocation cpa JOIN payment p ON cpa.paymentId=p.id WHERE cpa.caseId=c.id AND cpa.partyType='INITIATING' AND p.direction='INCOMING' AND p.status IN ('PENDING','APPROVED','COMPLETED')) AND EXISTS (SELECT 1 FROM case_payment_allocation cpa JOIN payment p ON cpa.paymentId=p.id WHERE cpa.caseId=c.id AND cpa.partyType='NON_INITIATING' AND p.direction='INCOMING' AND p.status IN ('PENDING','APPROVED','COMPLETED'))"}],"bot_must_return_keys":["final_elig_review_both_paid"],"temporality":"variant"}
{"id":"D_ashlee_002","category":"derived-query","prompt":"final eligibility completed where both payments and notice of offers received","ground_truth_sql":[{"name":"final_elig_completed","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='FINAL_ELIGIBILITY_COMPLETED'"}],"bot_must_return_keys":["final_elig_completed"],"temporality":"stable"}
{"id":"D_ashlee_003","category":"derived-query","prompt":"final determination pending where arbiter is reviewing dispute","ground_truth_sql":[{"name":"final_determination_pending","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='FINAL_DETERMINATION_PENDING'"}],"bot_must_return_keys":["final_determination_pending"],"temporality":"stable"}
{"id":"D_ashlee_004","category":"derived-query","prompt":"completed disputes with final payment determination rendered","ground_truth_sql":[{"name":"completed","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='COMPLETED'"}],"bot_must_return_keys":["completed"],"temporality":"stable"}
{"id":"D_ashlee_005","category":"derived-query","prompt":"month-to-date final determinations rendered","ground_truth_sql":[{"name":"mtd_final_determinations","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='COMPLETED' AND statusChangedAt >= DATE_FORMAT(:now, '%Y-%m-01 00:00:00')"}],"bot_must_return_keys":["mtd_final_determinations"],"temporality":"variant"}
{"id":"D_ashlee_006","category":"derived-query","prompt":"month-to-date defaults rendered","ground_truth_sql":[{"name":"mtd_defaults","sql":"SELECT COUNT(*) AS v FROM `case` WHERE closureReason='DEFAULT' AND statusChangedAt >= DATE_FORMAT(:now, '%Y-%m-01 00:00:00')"}],"bot_must_return_keys":["mtd_defaults"],"temporality":"variant"}
```

- [ ] **Step 2: Add 7 user-image-derived tests** (each numbered item in your status-summary screenshot):

```jsonl
{"id":"D_image_001","category":"derived-query","prompt":"give me total disputes","ground_truth_sql":[{"name":"total_disputes","sql":"SELECT COUNT(*) AS v FROM `case`"}],"bot_must_return_keys":["total_disputes"],"temporality":"stable"}
{"id":"D_image_002","category":"derived-query","prompt":"month-to-date disputes","ground_truth_sql":[{"name":"mtd_disputes","sql":"SELECT COUNT(*) AS v FROM `case` WHERE createdAt >= DATE_FORMAT(:now, '%Y-%m-01 00:00:00')"}],"bot_must_return_keys":["mtd_disputes"],"temporality":"variant"}
{"id":"D_image_003","category":"derived-query","prompt":"new disputes today","ground_truth_sql":[{"name":"new_today","sql":"SELECT COUNT(*) AS v FROM `case` WHERE DATE(createdAt) = DATE(:now)"}],"bot_must_return_keys":["new_today"],"temporality":"variant"}
{"id":"D_image_004","category":"derived-query","prompt":"disputes in payment pending status with breakdown of pending second payments","ground_truth_sql":[{"name":"payment_pending","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='PENDING_PAYMENTS'"},{"name":"pending_second","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='PENDING_SECOND_PAYMENT'"}],"bot_must_return_keys":["payment_pending","pending_second"],"temporality":"stable"}
{"id":"D_image_005","category":"derived-query","prompt":"disputes in final eligibility process with sub-status breakdown","ground_truth_sql":[{"name":"final_elig_process","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status IN ('FINAL_ELIGIBILITY_REVIEW','FINAL_ELIGIBILITY_COMPLETED','FINAL_DETERMINATION_PENDING')"},{"name":"final_elig_review","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='FINAL_ELIGIBILITY_REVIEW'"},{"name":"final_elig_completed","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='FINAL_ELIGIBILITY_COMPLETED'"},{"name":"final_determination_pending","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='FINAL_DETERMINATION_PENDING'"}],"bot_must_return_keys":["final_elig_process","final_elig_review","final_elig_completed","final_determination_pending"],"temporality":"stable"}
{"id":"D_image_006","category":"derived-query","prompt":"disputes closed with breakdown of ineligible pending admin fee and pending closure payments","ground_truth_sql":[{"name":"closed","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status IN ('INELIGIBLE_PENDING_ADMIN_FEE','PENDING_ADMINISTRATIVE_CLOSURE','CLOSED')"},{"name":"ineligible_admin","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='INELIGIBLE_PENDING_ADMIN_FEE'"},{"name":"pending_closure_payments","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='PENDING_ADMINISTRATIVE_CLOSURE'"}],"bot_must_return_keys":["closed","ineligible_admin","pending_closure_payments"],"temporality":"stable"}
{"id":"D_image_007","category":"derived-query","prompt":"completed disputes with month-to-date sub-stats","ground_truth_sql":[{"name":"completed","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='COMPLETED'"},{"name":"mtd_final_determinations","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status='COMPLETED' AND statusChangedAt >= DATE_FORMAT(:now, '%Y-%m-01 00:00:00')"},{"name":"mtd_defaults","sql":"SELECT COUNT(*) AS v FROM `case` WHERE closureReason='DEFAULT' AND statusChangedAt >= DATE_FORMAT(:now, '%Y-%m-01 00:00:00')"}],"bot_must_return_keys":["completed","mtd_final_determinations","mtd_defaults"],"temporality":"variant"}
```

- [ ] **Step 3: Add 10 ad-hoc derived tests + 6 adversarial tests**

```jsonl
{"id":"D_adhoc_001","category":"derived-query","prompt":"how many cases were closed last quarter","ground_truth_sql":[{"name":"closed_last_q","sql":"SELECT COUNT(*) AS v FROM `case` WHERE status IN ('CLOSED','COMPLETED','INELIGIBLE_PENDING_ADMIN_FEE') AND statusChangedAt >= DATE_SUB(DATE_FORMAT(DATE_SUB(:now, INTERVAL ((MONTH(:now)-1) MOD 3) MONTH), '%Y-%m-01'), INTERVAL 3 MONTH) AND statusChangedAt < DATE_FORMAT(DATE_SUB(:now, INTERVAL ((MONTH(:now)-1) MOD 3) MONTH), '%Y-%m-01')"}],"bot_must_return_keys":["closed_last_q"],"temporality":"variant"}
{"id":"D_adhoc_002","category":"derived-query","prompt":"average days to close a case","ground_truth_sql":[{"name":"avg_days_to_close","sql":"SELECT AVG(DATEDIFF(statusChangedAt, createdAt)) AS v FROM `case` WHERE status IN ('CLOSED','COMPLETED')"}],"bot_must_return_keys":["avg_days_to_close"],"temporality":"variant"}
{"id":"D_adhoc_003","category":"derived-query","prompt":"how many cases per status","ground_truth_sql":[{"name":"distinct_statuses","sql":"SELECT COUNT(DISTINCT status) AS v FROM `case`"}],"bot_must_return_keys":["distinct_statuses"],"temporality":"stable"}
{"id":"D_adhoc_004","category":"derived-query","prompt":"total incoming payments completed today","ground_truth_sql":[{"name":"incoming_today","sql":"SELECT COALESCE(SUM(amount),0) AS v FROM payment WHERE direction='INCOMING' AND status='COMPLETED' AND DATE(updatedAt)=DATE(:now)"}],"bot_must_return_keys":["incoming_today"],"temporality":"variant"}
{"id":"D_adhoc_005","category":"derived-query","prompt":"total outgoing payments completed today","ground_truth_sql":[{"name":"outgoing_today","sql":"SELECT COALESCE(SUM(amount),0) AS v FROM payment WHERE direction='OUTGOING' AND status='COMPLETED' AND DATE(updatedAt)=DATE(:now)"}],"bot_must_return_keys":["outgoing_today"],"temporality":"variant"}
{"id":"D_adhoc_006","category":"derived-query","prompt":"number of distinct organizations involved as initiating parties","ground_truth_sql":[{"name":"distinct_ip_orgs","sql":"SELECT COUNT(DISTINCT initiatingPartyOrganizationId) AS v FROM `case` WHERE initiatingPartyOrganizationId IS NOT NULL"}],"bot_must_return_keys":["distinct_ip_orgs"],"temporality":"stable"}
{"id":"D_adhoc_007","category":"derived-query","prompt":"how many cases have multiple line items","ground_truth_sql":[{"name":"multi_line_cases","sql":"SELECT COUNT(*) AS v FROM (SELECT caseId FROM dispute_line_item WHERE status='ACTIVE' GROUP BY caseId HAVING COUNT(*) > 1) t"}],"bot_must_return_keys":["multi_line_cases"],"temporality":"stable"}
{"id":"D_adhoc_008","category":"derived-query","prompt":"total CMS admin fee collected this year","ground_truth_sql":[{"name":"cms_admin_fee_ytd","sql":"SELECT COALESCE(SUM(amount),0) AS v FROM payment WHERE type='CASE_PAYMENT' AND status='COMPLETED' AND YEAR(updatedAt) = YEAR(:now)"}],"bot_must_return_keys":["cms_admin_fee_ytd"],"temporality":"variant"}
{"id":"D_adhoc_009","category":"derived-query","prompt":"how many active arbitrators","ground_truth_sql":[{"name":"active_arbs","sql":"SELECT COUNT(*) AS v FROM user WHERE role IN ('arbitrator','arbitrator-contractor')"}],"bot_must_return_keys":["active_arbs"],"temporality":"stable"}
{"id":"D_adhoc_010","category":"derived-query","prompt":"cases assigned but not yet started","ground_truth_sql":[{"name":"assigned_not_started","sql":"SELECT COUNT(*) AS v FROM `case` WHERE assignedToId IS NOT NULL AND status='INITIAL_ELIGIBILITY_REVIEW'"}],"bot_must_return_keys":["assigned_not_started"],"temporality":"stable"}
{"id":"D_adversarial_001","category":"derived-query","prompt":"outstanding payments where IP has not made any incoming payment","ground_truth_sql":[{"name":"ip_unpaid","sql":"SELECT COUNT(*) AS v FROM `case` c WHERE c.status IN ('PENDING_PAYMENTS','PENDING_SECOND_PAYMENT','PENDING_ADMINISTRATIVE_CLOSURE','INELIGIBLE','INELIGIBLE_PENDING_ADMIN_FEE') AND NOT EXISTS (SELECT 1 FROM case_payment_allocation cpa JOIN payment p ON cpa.paymentId=p.id WHERE cpa.caseId=c.id AND cpa.partyType='INITIATING' AND p.direction='INCOMING' AND p.status IN ('PENDING','APPROVED','COMPLETED'))"}],"bot_must_return_keys":["ip_unpaid"],"temporality":"stable"}
{"id":"D_adversarial_002","category":"derived-query","prompt":"total case balance across all cases using allocations minus refunds","ground_truth_sql":[{"name":"total_balance","sql":"SELECT COALESCE((SELECT SUM(cpa.allocatedAmountCents) FROM case_payment_allocation cpa JOIN payment p ON cpa.paymentId=p.id WHERE p.direction='INCOMING' AND p.status IN ('APPROVED','COMPLETED')),0) - COALESCE((SELECT SUM(refundAmountCents) FROM case_refunds WHERE status='COMPLETED'),0) AS v"}],"bot_must_return_keys":["total_balance"],"temporality":"stable"}
{"id":"D_adversarial_003","category":"derived-query","prompt":"CMS payments total amount (should be type CASE_PAYMENT not CMS_INVOICE_PAYMENT)","ground_truth_sql":[{"name":"cms_total","sql":"SELECT COALESCE(SUM(amount),0) AS v FROM payment WHERE type='CASE_PAYMENT' AND status='COMPLETED'"}],"bot_must_return_keys":["cms_total"],"temporality":"stable"}
{"id":"D_adversarial_004","category":"derived-query","prompt":"cases overdue checking all 4 due date columns","ground_truth_sql":[{"name":"overdue_all_4","sql":"SELECT COUNT(*) AS v FROM `case` WHERE (due_date < :now OR due_date_until_decision < :now OR eligibilityDueDate < :now OR paymentDueDate < :now)"}],"bot_must_return_keys":["overdue_all_4"],"temporality":"variant"}
{"id":"D_adversarial_005","category":"derived-query","prompt":"total outgoing completed payouts to Halo across all time","ground_truth_sql":[{"name":"halo_total","sql":"SELECT COALESCE(SUM(amount),0) AS v FROM payment WHERE direction='OUTGOING' AND status='COMPLETED' AND (LOWER(JSON_UNQUOTE(JSON_EXTRACT(bankingSnapshot, '$.accountHolderName'))) LIKE '%halo%' OR LOWER(recipientName) LIKE '%halo%')"}],"bot_must_return_keys":["halo_total"],"temporality":"stable"}
{"id":"D_adversarial_006","category":"derived-query","prompt":"recent case activity in the last 7 days","ground_truth_sql":[{"name":"recent_actions","sql":"SELECT COUNT(*) AS v FROM case_action WHERE createdAt >= DATE_SUB(:now, INTERVAL 7 DAY)"}],"bot_must_return_keys":["recent_actions"],"temporality":"variant"}
```

(That's 6+7+10+6 = 29 new derived + 9 from Day 6 = 38 derived total + 33 known = 71. Plus 9 from Day 1 brings to 80? Let me recount: known: 10 (Day1) + 11 (Day6) + 12 (Day9) = 33. Derived: 9 (Day6) + 6 ashlee + 7 image + 10 adhoc + 6 adversarial = 38. Total: 71. To reach 80 add 9 more.)

- [ ] **Step 4: Add 9 more derived prompts from ops team**

These come from real ops-team questions you collect during Week 1. Placeholder template (replace with actual prompts):

```jsonl
{"id":"D_ops_001","category":"derived-query","prompt":"<ops question 1>","ground_truth_sql":[{"name":"k","sql":"<verified SQL>"}],"bot_must_return_keys":["k"],"temporality":"stable"}
```

Repeat 9 times with real prompts gathered from ops. If you can't gather them in time, mark Task 10.1 step 4 as deferred and proceed with 71 — note this in the day-10 results.

- [ ] **Step 5: Commit**

```bash
git add testing/v10_harness/test_set.jsonl
git commit -m "test: add 28 derived prompts (ashlee + image + adversarial + adhoc)"
```

### Task 10.2: Full V10 test run

- [ ] **Step 1: Run everything**

```bash
cd /c/Users/anand/Downloads/local
BOT=v10 py311 -m pytest testing/v10_harness/tests/test_baseline_known.py testing/v10_harness/tests/test_baseline_derived.py -v --tb=short 2>&1 | tee /tmp/v10_final.log
```

Expected: complete run. Known: ≥ 30/33 PASS (some may need test-entry fixes). Derived: target ≥ 35/38 PASS first-try.

- [ ] **Step 2: Summarize**

```bash
py311 -c "
import json, glob
results = {'PASS':[], 'PARTIAL':[], 'FAIL':[]}
for p in glob.glob('testing/v10_harness/reports/*.json'):
    d = json.load(open(p))
    v = d.get('verdict')
    if v in results:
        results[v].append(d.get('id'))
total = sum(len(v) for v in results.values())
for k, v in results.items():
    print(f'{k}: {len(v)}/{total} ({len(v)/total*100:.1f}%)')
print('\\nFAIL list:')
for fid in results['FAIL']:
    print(' -', fid)
"
```

- [ ] **Step 3: Triage**

For each FAIL:
  - Read the per-prompt JSON in `testing/v10_harness/reports/`
  - Inspect `diffs`, `bot`, `expected`
  - Decide: bot bug? test-entry bug? knowledge-pipeline gap?
  - Fix the smallest-blame thing first
  - Re-run that one test: `BOT=v10 py311 -m pytest testing/v10_harness/tests/ -k <prompt_id> -v`

- [ ] **Step 4: Final commit**

```bash
mkdir -p testing/v10_harness/reports/day10
cp testing/v10_harness/reports/*.json testing/v10_harness/reports/day10/
git add testing/v10_harness/reports/day10/
git commit -m "test: V10 Day-10 full-suite run (80-prompt test set)"
git tag day10-complete -m "V10 implementation complete"
```

### Task 10.3: Write a release note

**Files:**
- Create: `C:\Users\anand\Downloads\local\docs\superpowers\reports\2026-05-15-v10-day10-results.md`

- [ ] **Step 1: Author it**

```markdown
# V10 Reports Bot — Day 10 Results

**Date:** <fill at completion>
**Tag:** day10-complete
**Test set:** N prompts (X known + Y derived)
**Bot under test:** V10 (git SHA <fill>)
**Knowledge git SHA:** <from manifest>

## Headline

- Known-report pass rate: <N>/<total> = <%>
- Derived-query pass rate: <N>/<total> = <%>
- Combined: <N>/<total> = <%>

## Vs the April 30 V9 baseline

- April 30: 17 PASS / 14 PARTIAL / 3 FAIL on ~34 scored prompts (70.6% weighted heuristic score)
- Today: <fill> exact result-match PASS on <total> prompts

(Note: not directly comparable — old scoring was heuristic SQL keyword presence; this one is byte-equal result comparison.)

## What's now broken that used to "pass"

<List any prompt categories where V10 fails despite V9 "passing" on the heuristic. Most likely none, but call out any.>

## Remaining failures

<For each FAIL: prompt id, prompt text, bot result, expected result, hypothesized cause, owner.>

## Next phase candidates

- Phase B (Approach B): SQL-only path with result-match testing for everything (defer)
- Phase C (Approach C): Fine-tune on the verified prompt→SQL pairs this test set produced
- Automated glossary extraction from Confluence + staging
- Latency/token budgets — enabled now that correctness is solid
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/reports/2026-05-15-v10-day10-results.md
git commit -m "docs: V10 Day-10 results writeup"
```

---

## Plan Self-Review

I read the spec sections against the plan tasks:

- **Spec Component 1 (Router):** covered by Tasks 5.3, 5.4, 9.1. LLM fallback (stage 2) is stubbed in `route()` — production deployment may want to wire Gemini fallback when `score < 0.85`. Recorded as TODO comment in router.py; tests cover the deterministic path only.
- **Spec Component 2 (Known-report path):** covered by Tasks 5.5 (client), 5.6 (param extractor + normalizer), 9.2 (extend endpoints).
- **Spec Component 3 (Derived-query path):** covered by Tasks 7.1 (tools rewrite), 7.2 (sql_writer rewrite), 7.3 (schema_verifier cleanup), 7.4 (executor row cap), 7.5 (wire harness).
- **Spec Component 4 (Knowledge pipeline):** covered by Tasks 3.1 through 3.8, with manual triage in Task 4.2.
- **Spec Component 5 (Test harness):** covered by Tasks 1.1 through 1.9 (harness skeleton), 6.2 (derived runner), 10.2 (full run).
- **Temporal variance handling:** covered by `temporality.py` (Task 1.2) + ground_truth_sql with `:now` parameter (used throughout).
- **Result comparison (no keyword scoring):** covered by `compare.py` (Task 1.3) and per-record test runners.
- **80-prompt test set composition:** covered by Tasks 1.7 (10), 6.1 (20), 9.3 (12), 10.1 (28+9 ops) — total reaches 71 + ops prompts.

**Internal-consistency check:** `RouterDecision.report` typed as `str | None` consistently. `TestRecord.bot_must_return_keys` referenced same way in runner.py, test_baseline_derived.py, and test entries. `KNOWN_ENDPOINTS` covers exactly the 14 reports listed in spec section 4 (modulo the `case-search` defensive addition flagged in Task 9.1).

**Placeholder scan:** one explicit placeholder block — Task 10.1 Step 4 has 9 "<ops question>" entries that must be filled with real ops-team prompts during Week 1. Flagged as such, not a hidden TBD.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-15-v10-reports-bot-plan.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for a 10-day plan where each day has 5-10 atomic tasks.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Best when you want to watch the work happen and answer ambiguities as they come up.

Which approach?





