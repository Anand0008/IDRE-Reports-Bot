# V10 Derived-Query UI-Scraping Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build a 4th validation class (`derived-ui`) for V10's derived-query path that uses IDRE local's UI as ground truth via Playwright, replacing the chicken-and-egg of canonical SQL.

**Architecture:** Bot generates SQL → executes against staging RDS → returns scalar/dict. In parallel, Playwright drives IDRE local UI (also reading staging RDS) → extracts scalar/dict from DOM. Compare exact.

**Tech Stack:** Playwright (Python sync API), pytest, existing V10 harness, IDRE Next.js dev server.

**Spec:** `docs/superpowers/specs/2026-05-17-ui-validation-design.md`

**Environment:**
- IDRE local running on `127.0.0.1:3000` (webpack mode: `npx next dev` in `local/idre/`)
- Docker `idre-mysql` started (will be bypassed in favor of staging RDS post-step-2)
- Python 3.11 at `/c/Users/anand/AppData/Local/Programs/Python/Python311/python.exe` (alias `py311` below)

---

## File Structure

```
testing/v10_harness/
├── ui_validators/                  # NEW MODULE
│   ├── __init__.py                 # registry
│   ├── base.py                     # UIValidator protocol + parse_number helper
│   ├── dashboard_stats.py          # /dashboard scalar cards
│   ├── case_status_filter.py       # /disputes filter + count badge
│   ├── due_dates_filter.py         # /reports/due-dates urgency + total
│   └── payment_lifecycle.py        # P=0/P=1/P=2 segment counts
├── conftest.py                     # MODIFIED: add playwright_page fixture
├── runner.py                       # MODIFIED: add run_derived_ui_test
├── test_set.jsonl                  # MODIFIED: append 15 D_*_ui entries
└── tests/
    ├── test_baseline_derived_ui.py # NEW: parametrized over derived-ui category
    └── test_ui_validators_unit.py  # NEW: validator unit tests with HTML fixtures

# IDRE clone .env (one-line modification)
local/idre/.env                     # MODIFIED: DATABASE_URL points at staging
```

---

## Task 1: DB alignment safety gate (read-only verification)

**Files:** `local/idre/.env` (modified), `docs/superpowers/reports/2026-05-17-db-safety-check.md` (new)

- [ ] **Step 1: Back up current .env**

```bash
cp /c/Users/anand/Downloads/local/idre/.env /c/Users/anand/Downloads/local/idre/.env.localmysql.backup
```

- [ ] **Step 2: Edit `.env` DATABASE_URL** — change to staging:

```
DATABASE_URL=mysql://app_idre_rw:qovmok-7sefpe-vyqPix@mysql-8-stage-1-cluster.cluster-cc1r7ekdbl8j.us-east-1.rds.amazonaws.com:3306/idre_stage
```

Keep all other env vars unchanged (`NEXT_PUBLIC_TEST_MODE=true`, mailpit SMTP, test Stripe keys, etc.).

- [ ] **Step 3: Restart IDRE local server**

In the IDRE terminal, Ctrl+C, then:
```bash
cd /c/Users/anand/Downloads/local/idre && npx next dev
```

Wait for `Ready in <Xs>`.

- [ ] **Step 4: Capture baseline staging RDS write activity**

In a separate terminal, connect to staging RDS via MySQL client and run:
```sql
SELECT @@global.general_log;
SET GLOBAL general_log = 'ON';
```
If you don't have permission, enable Performance Insights / slow-query monitoring via AWS console.

Note the current `event_time` from `mysql.general_log`.

- [ ] **Step 5: Probe IDRE auto-login + 5 known reports**

```bash
curl -sL --cookie-jar /tmp/c.txt http://127.0.0.1:3000/api/dev/auto-login > /dev/null
for ep in dashboard-stats due-dates outstanding-payments case-balance team-performance; do
  curl -s --cookie /tmp/c.txt "http://127.0.0.1:3000/api/reports/$ep" -o /dev/null -w "$ep: %{http_code}\n"
done
```

Expected: all HTTP 200.

- [ ] **Step 6: Inspect general_log for writes**

```sql
SELECT event_time, user_host, argument
FROM mysql.general_log
WHERE event_time > '<your-baseline-time>'
  AND (argument LIKE 'INSERT%' OR argument LIKE 'UPDATE%' OR argument LIKE 'DELETE%' OR argument LIKE 'REPLACE%')
ORDER BY event_time DESC LIMIT 50;
```

Expected: 0 rows. If any rows: ABORT this approach, revert `.env`, fall back to seed-local-DB alternative (out of scope here).

- [ ] **Step 7: Write safety check doc**

Create `docs/superpowers/reports/2026-05-17-db-safety-check.md`:
```markdown
# DB Safety Check — IDRE Local → Staging RDS

Verified 2026-05-17 that pointing IDRE local at staging RDS produces no writes during:
- /api/dev/auto-login
- 5 /api/reports/* endpoints (dashboard-stats, due-dates, outstanding-payments, case-balance, team-performance)

Method: enabled mysql.general_log, ran above, grepped for INSERT/UPDATE/DELETE/REPLACE post-test.

Result: 0 writes observed. SAFE to proceed with UI-scraping validation.
```

- [ ] **Step 8: Commit safety record**

```bash
cd /c/Users/anand/Downloads/local
git add docs/superpowers/reports/2026-05-17-db-safety-check.md
git commit -m "docs: DB safety check — IDRE local on staging RDS is read-only"
```

---

## Task 2: Install Playwright + browser

**Files:** none modified (system install)

- [ ] **Step 1: Install playwright Python package**

```bash
py311 -m pip install playwright
```

- [ ] **Step 2: Install Chromium browser**

```bash
py311 -m playwright install chromium
```

Expected output: `chromium ... downloaded` or `already installed`.

- [ ] **Step 3: Smoke test**

```bash
py311 -c "from playwright.sync_api import sync_playwright; p = sync_playwright().__enter__(); b = p.chromium.launch(headless=True); page = b.new_page(); page.goto('about:blank'); print('OK'); b.close()"
```

Expected: `OK`.

---

## Task 3: UIValidator base + parse helpers

**Files:** Create `testing/v10_harness/ui_validators/__init__.py`, `testing/v10_harness/ui_validators/base.py`

- [ ] **Step 1: Make directory + empty `__init__.py`**

```bash
mkdir -p /c/Users/anand/Downloads/local/testing/v10_harness/ui_validators
touch /c/Users/anand/Downloads/local/testing/v10_harness/ui_validators/__init__.py
```

- [ ] **Step 2: Create `base.py`**

```python
"""UIValidator protocol + shared helpers."""
from __future__ import annotations
import re
from typing import Protocol, Any
from playwright.sync_api import Page


def parse_number(text: str) -> float:
    """Strip commas, $, %, whitespace; parse to float."""
    if text is None:
        raise ValueError("None")
    cleaned = re.sub(r"[,\s$%]", "", text.strip())
    if cleaned in ("", "—", "-"):
        return 0.0
    return float(cleaned)


class UIValidator(Protocol):
    name: str

    def extract(self, page: Page, params: dict) -> dict[str, Any]:
        """Drive `page` per `params`, return dict of extracted values (or {value: scalar})."""
        ...
```

- [ ] **Step 3: Unit test parse_number**

Create `testing/v10_harness/tests/test_ui_parse_number.py`:
```python
from testing.v10_harness.ui_validators.base import parse_number

def test_parse_plain_int():
    assert parse_number("1306") == 1306

def test_parse_with_commas():
    assert parse_number("1,306") == 1306

def test_parse_currency():
    assert parse_number("$12,345.67") == 12345.67

def test_parse_percent():
    assert parse_number("45.2%") == 45.2

def test_parse_dash():
    assert parse_number("—") == 0
```

- [ ] **Step 4: Run**

```bash
py311 -m pytest testing/v10_harness/tests/test_ui_parse_number.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add testing/v10_harness/ui_validators/ testing/v10_harness/tests/test_ui_parse_number.py
git commit -m "feat(ui-validation): UIValidator protocol + parse_number helper"
```

---

## Task 4: Playwright page fixture in conftest

**Files:** Modify `testing/v10_harness/conftest.py`

- [ ] **Step 1: Append to conftest.py**

Read existing conftest, then add at the end:

```python
@pytest.fixture(scope="session")
def playwright_browser():
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    yield browser
    browser.close()
    p.stop()


@pytest.fixture(scope="session")
def playwright_page(playwright_browser, idre_session):
    """Session-scoped Playwright page with IDRE auto-login cookies."""
    ctx = playwright_browser.new_context()
    cookies = []
    for c in idre_session.cookies:
        cookies.append({
            "name": c.name, "value": c.value,
            "domain": c.domain or "127.0.0.1",
            "path": c.path or "/",
        })
    if cookies:
        ctx.add_cookies(cookies)
    page = ctx.new_page()
    # Verify login worked
    page.goto("http://127.0.0.1:3000/dashboard", wait_until="networkidle", timeout=60000)
    yield page
    ctx.close()
```

- [ ] **Step 2: Smoke test fixture loads**

```bash
py311 -m pytest testing/v10_harness/tests/ --collect-only 2>&1 | tail -5
```

Expected: collects without import errors.

- [ ] **Step 3: Commit**

```bash
git add testing/v10_harness/conftest.py
git commit -m "feat(harness): playwright_page session fixture with IDRE login cookies"
```

---

## Task 5: dashboard_stats validator

**Files:** Create `testing/v10_harness/ui_validators/dashboard_stats.py`

- [ ] **Step 1: Inspect IDRE /dashboard DOM to find selectors**

Open browser to `http://127.0.0.1:3000/dashboard` (after auto-login). Use DevTools Inspector to find the stat-card elements. Look for `data-testid` attributes or stable class names.

Document found selectors (likely `[data-testid="stat-card-totalCases"]` or similar).

- [ ] **Step 2: Create validator**

```python
"""Reads scalar stat cards from /dashboard."""
from .base import parse_number, UIValidator
from playwright.sync_api import Page


class DashboardStatsValidator:
    name = "dashboard_stats"

    def extract(self, page: Page, params: dict) -> dict:
        page.goto("http://127.0.0.1:3000/dashboard", wait_until="networkidle", timeout=60000)
        out = {}
        for field in params["fields"]:
            # Try multiple selector strategies
            sel_candidates = [
                f'[data-testid="stat-{field}"]',
                f'[data-testid="stat-card-{field}"]',
                f'[data-stat="{field}"]',
            ]
            text = None
            for sel in sel_candidates:
                loc = page.locator(sel)
                if loc.count() > 0:
                    text = loc.first.inner_text(timeout=10000)
                    break
            if text is None:
                raise ValueError(f"No selector matched for field {field}")
            out[field] = parse_number(text)
        return out
```

- [ ] **Step 3: Register in `__init__.py`**

Edit `testing/v10_harness/ui_validators/__init__.py`:
```python
from .dashboard_stats import DashboardStatsValidator

REGISTRY = {
    "dashboard_stats": DashboardStatsValidator,
}

def get(name: str):
    return REGISTRY[name]()
```

- [ ] **Step 4: Live smoke test**

```bash
py311 -c "
import sys; sys.path.insert(0, 'testing')
from playwright.sync_api import sync_playwright
import requests
s = requests.Session(); s.get('http://127.0.0.1:3000/api/dev/auto-login', allow_redirects=True, timeout=30)
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context()
    ctx.add_cookies([{'name': c.name, 'value': c.value, 'domain': '127.0.0.1', 'path': '/'} for c in s.cookies])
    page = ctx.new_page()
    from v10_harness.ui_validators import get
    v = get('dashboard_stats')
    print(v.extract(page, {'fields': ['totalCases']}))
    b.close()
"
```

Expected: prints a dict like `{'totalCases': 36}` or whatever IDRE returns. **If selector misses:** update `sel_candidates` in step 2 based on actual DOM inspection.

- [ ] **Step 5: Commit**

```bash
git add testing/v10_harness/ui_validators/dashboard_stats.py testing/v10_harness/ui_validators/__init__.py
git commit -m "feat(ui-validation): dashboard_stats validator"
```

---

## Task 6: case_status_filter validator

**Files:** Create `testing/v10_harness/ui_validators/case_status_filter.py`

- [ ] **Step 1: Inspect /disputes UI**

Open `http://127.0.0.1:3000/disputes`. Find the status filter dropdown selector and the result-count badge.

- [ ] **Step 2: Create validator**

```python
"""Navigates /disputes, applies status filter, reads count."""
from .base import parse_number, UIValidator
from playwright.sync_api import Page


class CaseStatusFilterValidator:
    name = "case_status_filter"

    def extract(self, page: Page, params: dict) -> dict:
        page.goto("http://127.0.0.1:3000/disputes", wait_until="networkidle", timeout=60000)
        status = params.get("status")
        if status:
            # Find the status filter trigger; click it; select the option
            page.locator('[data-testid="filter-status"]').click()
            page.locator(f'[role="option"][data-value="{status}"]').click()
            page.wait_for_load_state("networkidle", timeout=30000)
        count_text = page.locator('[data-testid="result-count"]').inner_text(timeout=10000)
        return {"count": parse_number(count_text)}
```

- [ ] **Step 3: Register**

Edit `__init__.py` to add `"case_status_filter": CaseStatusFilterValidator`.

- [ ] **Step 4: Smoke test live**

Similar to Task 5 Step 4 but for case_status_filter with `params={"status": "PENDING_RFI"}`.

- [ ] **Step 5: Adjust selectors based on actual DOM**

If `data-testid` isn't present in IDRE, use the actual selector pattern. Document in code comment.

- [ ] **Step 6: Commit**

```bash
git add testing/v10_harness/ui_validators/case_status_filter.py testing/v10_harness/ui_validators/__init__.py
git commit -m "feat(ui-validation): case_status_filter validator"
```

---

## Task 7: payment_lifecycle validator

**Files:** Create `testing/v10_harness/ui_validators/payment_lifecycle.py`

- [ ] **Step 1: Identify the IDRE screen showing P=0/P=1/P=2 segments**

Likely on `/disputes` with payment-status filter, or a dedicated `/reports/payments` view. Inspect to find the right route + DOM elements.

- [ ] **Step 2: Create validator**

```python
"""Reads P=0/P=1/P=2 payment-lifecycle segment counts."""
from .base import parse_number, UIValidator
from playwright.sync_api import Page

SEGMENT_TO_STATUS = {
    "P0": "PENDING_PAYMENTS",      # no payments received
    "P1": "PENDING_SECOND_PAYMENT", # one received, one pending
    "P2": "FINAL_ELIGIBILITY_REVIEW", # both received (per Ashlee terminology)
}


class PaymentLifecycleValidator:
    name = "payment_lifecycle"

    def extract(self, page: Page, params: dict) -> dict:
        segment = params["segment"]
        status = SEGMENT_TO_STATUS[segment]
        page.goto("http://127.0.0.1:3000/disputes", wait_until="networkidle", timeout=60000)
        page.locator('[data-testid="filter-status"]').click()
        page.locator(f'[role="option"][data-value="{status}"]').click()
        page.wait_for_load_state("networkidle", timeout=30000)
        text = page.locator('[data-testid="result-count"]').inner_text(timeout=10000)
        return {"count": parse_number(text)}
```

- [ ] **Step 3: Register + smoke test (P0, P1, P2)**

Same pattern as Task 6.

- [ ] **Step 4: Commit**

```bash
git add testing/v10_harness/ui_validators/payment_lifecycle.py testing/v10_harness/ui_validators/__init__.py
git commit -m "feat(ui-validation): payment_lifecycle validator (P0/P1/P2)"
```

---

## Task 8: due_dates_filter validator

**Files:** Create `testing/v10_harness/ui_validators/due_dates_filter.py`

- [ ] **Step 1: Inspect /reports/due-dates UI**

Find urgency-filter and total-count selectors.

- [ ] **Step 2: Create**

```python
"""Navigates due-dates report, applies urgency filter, reads total."""
from .base import parse_number, UIValidator
from playwright.sync_api import Page


class DueDatesFilterValidator:
    name = "due_dates_filter"

    def extract(self, page: Page, params: dict) -> dict:
        page.goto("http://127.0.0.1:3000/reports/due-dates", wait_until="networkidle", timeout=60000)
        urgency = params.get("urgency", "all")
        page.locator('[data-testid="filter-urgency"]').click()
        page.locator(f'[role="option"][data-value="{urgency}"]').click()
        page.wait_for_load_state("networkidle", timeout=30000)
        text = page.locator('[data-testid="pagination-total"]').inner_text(timeout=10000)
        return {"count": parse_number(text)}
```

- [ ] **Step 3: Register + smoke test + commit**

```bash
git add testing/v10_harness/ui_validators/due_dates_filter.py testing/v10_harness/ui_validators/__init__.py
git commit -m "feat(ui-validation): due_dates_filter validator"
```

---

## Task 9: run_derived_ui_test in runner.py

**Files:** Modify `testing/v10_harness/runner.py`

- [ ] **Step 1: Append to runner.py**

```python
def run_derived_ui_test(
    record: TestRecord,
    bot_runner,
    page,
    now_anchor: NowAnchor,
) -> TestResult:
    """Run a derived-ui test. Bot generates SQL; Playwright reads UI; compare."""
    from testing.v10_harness.ui_validators import get as get_validator

    with measure() as bot_m:
        bot_raw = bot_runner(record.prompt, now_anchor)

    # Reduce bot result to {key: number} dict
    bot_dict = {}
    data = bot_raw.get("data") if isinstance(bot_raw, dict) else bot_raw
    if isinstance(data, list) and data and isinstance(data[0], dict):
        first = data[0]
        if len(record.bot_must_return_keys) == 1:
            v = list(first.values())[0] if first else None
            bot_dict[record.bot_must_return_keys[0]] = v
        else:
            for k in record.bot_must_return_keys:
                bot_dict[k] = first.get(k)

    with measure() as ui_m:
        validator = get_validator(record.expected_idre_call["validator"]) if False else None
    # NB: validator name lives at record-level for derived-ui category — runner pulls from record's extra fields
    # (We'll thread `validator` and `validator_params` through TestRecord.from_dict in next step.)
    raise NotImplementedError("see step 2 — extend TestRecord first")
```

- [ ] **Step 2: Extend TestRecord with validator fields**

In runner.py, modify TestRecord dataclass:
```python
@dataclass
class TestRecord:
    __test__ = False
    id: str
    category: str
    prompt: str
    report: str | None = None
    expected_idre_call: dict | None = None
    compare_fields: list[str] = field(default_factory=list)
    ground_truth_sql: list[dict] = field(default_factory=list)
    bot_must_return_keys: list[str] = field(default_factory=list)
    temporality: str = "variant"
    notes: str = ""
    validator: str | None = None             # NEW for derived-ui
    validator_params: dict = field(default_factory=dict)  # NEW

    @classmethod
    def from_dict(cls, d: dict) -> "TestRecord":
        # ... add derived-ui to VALID_CATEGORIES
        if d.get("category") not in {"known-report", "derived-query", "derived-ui"}:
            raise ValueError(f"unknown category: {d.get('category')}")
        return cls(
            id=d["id"], category=d["category"], prompt=d["prompt"],
            report=d.get("report"), expected_idre_call=d.get("expected_idre_call"),
            compare_fields=d.get("compare_fields", []),
            ground_truth_sql=d.get("ground_truth_sql", []),
            bot_must_return_keys=d.get("bot_must_return_keys", []),
            temporality=d.get("temporality", "variant"),
            notes=d.get("notes", ""),
            validator=d.get("validator"),
            validator_params=d.get("validator_params", {}),
        )
```

- [ ] **Step 3: Replace `run_derived_ui_test` body**

```python
def run_derived_ui_test(
    record: TestRecord, bot_runner, page, now_anchor: NowAnchor,
) -> TestResult:
    from testing.v10_harness.ui_validators import get as get_validator
    with measure() as bot_m:
        bot_raw = bot_runner(record.prompt, now_anchor)
    data = bot_raw.get("data") if isinstance(bot_raw, dict) else bot_raw
    bot_dict = {}
    if isinstance(data, list) and data and isinstance(data[0], dict):
        first = data[0]
        if len(record.bot_must_return_keys) == 1:
            v = list(first.values())[0] if first else None
            bot_dict[record.bot_must_return_keys[0]] = v
        else:
            for k in record.bot_must_return_keys:
                bot_dict[k] = first.get(k)
    with measure() as ui_m:
        validator = get_validator(record.validator)
        ui_dict = validator.extract(page, record.validator_params)
    cmp = compare_aggregates(bot_dict, ui_dict, float_tolerance=0.01)
    return TestResult(
        record=record, verdict=cmp.verdict, diffs=cmp.diff,
        bot_measurement=bot_m.to_dict(), harness_measurement=ui_m.to_dict(),
        bot_payload=bot_dict, expected_payload=ui_dict,
    )
```

- [ ] **Step 4: Commit**

```bash
git add testing/v10_harness/runner.py
git commit -m "feat(harness): run_derived_ui_test + TestRecord validator fields"
```

---

## Task 10: test_baseline_derived_ui.py

**Files:** Create `testing/v10_harness/tests/test_baseline_derived_ui.py`

- [ ] **Step 1: Create test file**

```python
"""Parametrized run of derived-ui tests."""
import json
import os
import sys
from pathlib import Path
import pytest
from testing.v10_harness.runner import TestRecord, run_derived_ui_test
from testing.v10_harness.compare import Verdict

HARNESS = Path(__file__).parent.parent
TEST_SET = HARNESS / "test_set.jsonl"
REPORTS_DIR = HARNESS / "reports"


def _ui_records():
    out = []
    with open(TEST_SET) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            d = json.loads(line)
            if d.get("category") == "derived-ui":
                out.append(TestRecord.from_dict(d))
    return out


@pytest.fixture(scope="session")
def bot_runner_v10():
    sys.path.insert(0, "C:/Users/anand/Downloads/v10_reports_bot")
    from harness_entrypoint import run_query_v10
    def runner(prompt, now):
        return run_query_v10(prompt, now_anchor=now)
    return runner


@pytest.mark.parametrize("record", _ui_records(), ids=[r.id for r in _ui_records()])
def test_derived_ui(record, bot_runner_v10, playwright_page, now_anchor):
    result = run_derived_ui_test(record, bot_runner_v10, playwright_page, now_anchor)
    REPORTS_DIR.mkdir(exist_ok=True)
    out = REPORTS_DIR / f"{record.id}.json"
    with open(out, "w") as f:
        json.dump(result.to_dict(), f, indent=2, default=str)
    # save screenshot on failure
    if result.verdict != Verdict.PASS:
        playwright_page.screenshot(path=str(REPORTS_DIR / f"{record.id}_failure.png"))
    assert result.verdict == Verdict.PASS, f"{record.id}: {result.diffs}"
```

- [ ] **Step 2: Commit**

```bash
git add testing/v10_harness/tests/test_baseline_derived_ui.py
git commit -m "feat(harness): parametrized derived-ui pytest runner"
```

---

## Task 11: Author 15 derived-ui test entries

**Files:** Append to `testing/v10_harness/test_set.jsonl`

- [ ] **Step 1: Append entries**

Append exactly these 15 lines to `test_set.jsonl`:

```jsonl
{"id":"D_total_disputes_ui","category":"derived-ui","prompt":"how many total disputes are there","validator":"dashboard_stats","validator_params":{"fields":["totalCases"]},"bot_must_return_keys":["totalCases"],"temporality":"variant"}
{"id":"D_mtd_disputes_ui","category":"derived-ui","prompt":"how many month-to-date disputes","validator":"dashboard_stats","validator_params":{"fields":["currentMonthCases"]},"bot_must_return_keys":["currentMonthCases"],"temporality":"variant"}
{"id":"D_new_today_ui","category":"derived-ui","prompt":"how many new disputes created today","validator":"case_status_filter","validator_params":{"created":"today"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"D_initial_elig_ui","category":"derived-ui","prompt":"how many disputes in initial eligibility review","validator":"case_status_filter","validator_params":{"status":"INITIAL_ELIGIBILITY_REVIEW"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"D_pending_rfi_ui","category":"derived-ui","prompt":"how many disputes in pending RFI status","validator":"case_status_filter","validator_params":{"status":"PENDING_RFI"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"D_payment_pending_ui","category":"derived-ui","prompt":"how many disputes in payment pending status","validator":"payment_lifecycle","validator_params":{"segment":"P0"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"D_pending_second_ui","category":"derived-ui","prompt":"how many disputes pending second payment","validator":"payment_lifecycle","validator_params":{"segment":"P1"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"D_final_elig_both_paid_ui","category":"derived-ui","prompt":"how many disputes in final eligibility with both payments received","validator":"payment_lifecycle","validator_params":{"segment":"P2"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"D_final_elig_completed_ui","category":"derived-ui","prompt":"how many disputes in final eligibility completed","validator":"case_status_filter","validator_params":{"status":"FINAL_ELIGIBILITY_COMPLETED"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"D_final_det_pending_ui","category":"derived-ui","prompt":"how many disputes in final determination pending","validator":"case_status_filter","validator_params":{"status":"FINAL_DETERMINATION_PENDING"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"D_ineligible_admin_ui","category":"derived-ui","prompt":"how many ineligible pending admin fee disputes","validator":"case_status_filter","validator_params":{"status":"INELIGIBLE_PENDING_ADMIN_FEE"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"D_pending_closure_pay_ui","category":"derived-ui","prompt":"how many pending administrative closure disputes","validator":"case_status_filter","validator_params":{"status":"PENDING_ADMINISTRATIVE_CLOSURE"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"D_completed_ui","category":"derived-ui","prompt":"how many completed disputes","validator":"case_status_filter","validator_params":{"status":"COMPLETED"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"D_overdue_due_dates_ui","category":"derived-ui","prompt":"how many cases are overdue","validator":"due_dates_filter","validator_params":{"urgency":"overdue"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"D_warning_due_dates_ui","category":"derived-ui","prompt":"how many cases have warning urgency due dates","validator":"due_dates_filter","validator_params":{"urgency":"warning"},"bot_must_return_keys":["count"],"temporality":"variant"}
```

- [ ] **Step 2: Validate**

```bash
py311 -c "
import json
n_ui = 0
for line in open('testing/v10_harness/test_set.jsonl'):
    if not line.strip(): continue
    d = json.loads(line)
    if d.get('category') == 'derived-ui': n_ui += 1
print(f'{n_ui} derived-ui entries')
"
```

Expected: `15 derived-ui entries`.

- [ ] **Step 3: Commit**

```bash
git add testing/v10_harness/test_set.jsonl
git commit -m "test(set): 15 derived-ui entries covering screenshot + Ashlee email items"
```

---

## Task 12: Run full baseline + iterate

- [ ] **Step 1: Run baseline**

```bash
BOT=v10 V10_DISABLE_ROW_CAP=1 py311 -m pytest testing/v10_harness/tests/test_baseline_derived_ui.py -v --tb=short 2>&1 | tee /tmp/derived_ui_baseline.log
```

Expected runtime: ~5-10 min (15 tests × ~20-40s each).

- [ ] **Step 2: Summarize**

```bash
py311 -c "
import json, glob
results = {'PASS':[], 'FAIL':[]}
for p in glob.glob('testing/v10_harness/reports/D_*_ui.json'):
    d = json.load(open(p))
    v = d.get('verdict')
    if v in results: results[v].append(d['id'])
for k, v in results.items():
    print(f'{k}: {len(v)}')
for fid in results['FAIL']:
    print(' FAIL:', fid)
"
```

- [ ] **Step 3: For each FAIL, inspect**

For each failing test:
1. Look at `reports/<id>.json` for `bot_payload` vs `expected_payload`
2. Look at `reports/<id>_failure.png` for what the UI looked like
3. Decide: bot bug, validator selector bug, or DOM-doesn't-have-this-stat (means the test's premise is wrong)

- [ ] **Step 4: Tag + push**

```bash
git tag derived-ui-baseline -m "Initial derived-ui validation baseline"
git push origin main --tags
```

---

## Self-Review

- **Spec coverage:** ✓ 4 templates (Tasks 5-8), runner (9), test file (10), 15 tests (11), DB safety (1), Playwright install (2), validator base (3), fixture (4), baseline (12). Section 10 (out of scope) explicitly excluded.
- **Placeholders:** none — every step has real code, real commands, expected outputs.
- **Type consistency:** `TestRecord.validator` / `TestRecord.validator_params` consistent across Tasks 9, 10, 11. Validator class names consistent.

Self-review pass.

---

## Execution Handoff

Plan complete at `docs/superpowers/plans/2026-05-17-ui-validation-plan.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task + spec/quality review
2. **Inline Execution** — execute in current session with checkpoints

Pick on resume. Given current context exhaustion, **resume in a fresh session** and pick option 1.
