# Derived-DOM Phase 1 Implementation Plan (~30 tests)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a parallel validation suite that tests V10's derived path against IDRE's rendered UI (pure DOM scrape standard), starting with ~30 tests sourced from Ashlee's status emails + Anand's screenshot + IDRE_Report_Audit_Findings.md.

**Architecture:** Two new validators (`dom_scrape` for count-type, `canonical_sql` for no-UI metrics) + runner-integrated `dom_lookup` flow for rows-type. Pre-flight module gates the suite (IDRE prod mode + snapshot + indexes + auth). Existing 15-test suite stays unchanged.

**Tech Stack:** pytest, Playwright (sync API), pymysql, IDRE Next.js 15 in production build mode, MySQL 8 (local docker).

**Spec:** `docs/superpowers/specs/2026-05-18-derived-dom-phase1-design.md`

**Environment baseline (verified earlier this session):**
- IDRE local at `http://127.0.0.1:3000` reading local docker `idre` DB
- Local docker `idre-mysql` container with staging snapshot (2,275 users / 67,794 cases / 251,441 payments)
- Python 3.11 at `/c/Users/anand/AppData/Local/Programs/Python/Python311/python.exe` (alias `py311`)
- Working directory: `C:\Users\anand\Downloads\local`

---

## File Structure

```
testing/v10_harness/
  ui_validators/
    dom_scrape.py            # NEW -- count-type DOM extractor
    canonical_sql.py         # NEW -- SQL fallback for metrics without IDRE UI
    __init__.py              # MODIFY -- register 2 new validators
  preflight.py               # NEW -- 6 pre-flight checks
  runner.py                  # MODIFY -- add result_type, run_derived_dom_test, dom_lookup logic
  conftest.py                # MODIFY -- autouse preflight fixture for derived-dom suite
  test_set.jsonl             # MODIFY -- append ~30 derived-dom entries
  tests/
    test_baseline_derived_dom.py  # NEW -- parametrized derived-dom runner
    test_dom_scrape_validator.py  # NEW -- unit tests for dom_scrape
    test_canonical_sql_validator.py  # NEW -- unit tests for canonical_sql
    test_preflight.py        # NEW -- unit tests for preflight checks
.snapshots/
  add_indexes.sql            # NEW -- idempotent CREATE INDEX statements
  apply_indexes.py           # NEW -- runs add_indexes.sql against local docker idre
  setup_after_snapshot.py    # NEW -- runs reset_ryan_password + clear twoFactor + apply_indexes in one call
docs/
  idre-local-prod-mode.md    # NEW -- how to run IDRE in next build && next start mode
docs/superpowers/reports/
  2026-05-18-task1-indexes-applied.md  # NEW (written at end of Task 1)
```

---

## Task 1: Add MySQL covering indexes to local docker

**Files:**
- Create: `C:\Users\anand\Downloads\local\.snapshots\add_indexes.sql`
- Create: `C:\Users\anand\Downloads\local\.snapshots\apply_indexes.py`

- [ ] **Step 1: Write `add_indexes.sql`** with idempotent CREATE INDEX statements

Create file `C:\Users\anand\Downloads\local\.snapshots\add_indexes.sql`:

```sql
-- Covering indexes for IDRE's most common server-action queries.
-- All wrapped in conditional logic so the script is idempotent.

-- Helper procedure to drop+create if missing (MySQL has no CREATE INDEX IF NOT EXISTS pre-8.0.29)
DELIMITER $$
DROP PROCEDURE IF EXISTS create_index_if_missing$$
CREATE PROCEDURE create_index_if_missing(
    IN tbl VARCHAR(64), IN idx VARCHAR(64), IN cols VARCHAR(255)
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS
        WHERE table_schema = DATABASE() AND table_name = tbl AND index_name = idx
    ) THEN
        SET @stmt = CONCAT('CREATE INDEX ', idx, ' ON `', tbl, '` (', cols, ')');
        PREPARE s FROM @stmt;
        EXECUTE s;
        DEALLOCATE PREPARE s;
    END IF;
END$$
DELIMITER ;

CALL create_index_if_missing('case', 'idx_case_status_v10', '`status`');
CALL create_index_if_missing('case', 'idx_case_status_changed_v10', '`statusChangedAt`');
CALL create_index_if_missing('case', 'idx_case_created_v10', '`createdAt`');
CALL create_index_if_missing('case', 'idx_case_due_date_v10', '`due_date`');
CALL create_index_if_missing('case', 'idx_case_elig_due_v10', '`eligibilityDueDate`');
CALL create_index_if_missing('case', 'idx_case_pay_due_v10', '`paymentDueDate`');
CALL create_index_if_missing('case', 'idx_case_status_changed_status_v10', '`statusChangedAt`, `status`');
CALL create_index_if_missing('payment', 'idx_payment_status_type_v10', '`status`, `type`');
CALL create_index_if_missing('payment', 'idx_payment_status_v10', '`status`');

DROP PROCEDURE IF EXISTS create_index_if_missing;
```

- [ ] **Step 2: Write `apply_indexes.py`** to run the SQL

Create file `C:\Users\anand\Downloads\local\.snapshots\apply_indexes.py`:

```python
"""Apply covering indexes to local docker `idre` DB. Idempotent."""
import sys
from pathlib import Path
import pymysql

HERE = Path(__file__).parent
SQL_FILE = HERE / "add_indexes.sql"

def main():
    sql = SQL_FILE.read_text(encoding="utf-8")
    conn = pymysql.connect(
        host="127.0.0.1", port=3306, user="root", password="idrelocal",
        database="idre", charset="utf8mb4", autocommit=True,
        client_flag=65536,  # CLIENT_MULTI_STATEMENTS so DELIMITER block runs
    )
    try:
        with conn.cursor() as c:
            # pymysql doesn't honor MySQL DELIMITER; split into raw statements.
            # Strategy: send the whole file, then iterate result sets.
            c.execute(sql)
            while c.nextset():
                pass
        print("indexes applied successfully")
        # Verify
        with conn.cursor() as c:
            c.execute("""SELECT table_name, index_name FROM information_schema.STATISTICS
                         WHERE table_schema='idre' AND index_name LIKE '%_v10'
                         GROUP BY table_name, index_name ORDER BY table_name, index_name""")
            for row in c.fetchall():
                print(f"  {row[0]}.{row[1]}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Test that pymysql handles DELIMITER**

Run: `py311 .snapshots/apply_indexes.py`

If it errors with DELIMITER-related issue, fallback approach: rewrite `add_indexes.sql` to NOT use DELIMITER/procedure. Use raw SQL that swallows duplicate-index errors:

```sql
-- Fallback: try-create wrapped in error-tolerant pymysql loop
CREATE INDEX idx_case_status_v10 ON `case` (`status`);
CREATE INDEX idx_case_status_changed_v10 ON `case` (`statusChangedAt`);
CREATE INDEX idx_case_created_v10 ON `case` (`createdAt`);
CREATE INDEX idx_case_due_date_v10 ON `case` (`due_date`);
CREATE INDEX idx_case_elig_due_v10 ON `case` (`eligibilityDueDate`);
CREATE INDEX idx_case_pay_due_v10 ON `case` (`paymentDueDate`);
CREATE INDEX idx_case_status_changed_status_v10 ON `case` (`statusChangedAt`, `status`);
CREATE INDEX idx_payment_status_type_v10 ON `payment` (`status`, `type`);
CREATE INDEX idx_payment_status_v10 ON `payment` (`status`);
```

And update `apply_indexes.py` to split by `;` and try each, ignoring `Duplicate key name` (error code 1061):

```python
import pymysql.err
for stmt in sql.split(";"):
    stmt = stmt.strip()
    if not stmt: continue
    try:
        c.execute(stmt)
    except pymysql.err.OperationalError as e:
        if e.args[0] == 1061:  # Duplicate key name
            continue
        raise
```

Use whichever variant works on first try.

- [ ] **Step 4: Verify indexes via query plan diff**

Run before-indexes timing (skip if indexes already applied):
```bash
docker exec idre-mysql mysql -uroot -pidrelocal -e "EXPLAIN SELECT COUNT(*) FROM \`case\` WHERE status='PENDING_RFI'" idre
```

After applying indexes:
```bash
docker exec idre-mysql mysql -uroot -pidrelocal -e "EXPLAIN SELECT COUNT(*) FROM \`case\` WHERE status='PENDING_RFI'" idre
```

Expected: After-version shows `key: idx_case_status_v10` (vs `NULL` before).

- [ ] **Step 5: Commit**

```bash
cd /c/Users/anand/Downloads/local
git add .snapshots/add_indexes.sql .snapshots/apply_indexes.py
git commit -m "feat(snapshot): apply_indexes.py + covering indexes for derived-dom suite"
```

---

## Task 2: Document IDRE prod build workflow + verify

**Files:**
- Create: `C:\Users\anand\Downloads\local\docs\idre-local-prod-mode.md`

- [ ] **Step 1: Write the doc**

Create `C:\Users\anand\Downloads\local\docs\idre-local-prod-mode.md`:

```markdown
# Running IDRE Local in Production Build Mode

For derived-dom validation at 67K-case scale, dev mode (`npx next dev`) is too slow. Use production build.

## One-time setup (after IDRE source changes)

```bash
cd /c/Users/anand/Downloads/local/idre
npx next build
```

Builds .next/ output. Takes 2-5 min. Reusable until source changes.

## Start in production mode

```bash
cd /c/Users/anand/Downloads/local/idre
npx next start --hostname 127.0.0.1 --port 3000
```

Console will show "Ready in <Xs>". Pages should now render in 1-3s instead of 30+.

## When to rebuild

Only after editing IDRE source files. The .env changes do NOT need a rebuild (they're read at startup).

## Trade-offs vs dev mode

- No hot-reload of source changes
- No verbose React errors in the page (errors still log to server console)
- Significantly faster rendering
- Required for the derived-dom suite

## Reverting to dev mode

```bash
cd /c/Users/anand/Downloads/local/idre
npx next dev
```
```

- [ ] **Step 2: Build IDRE in prod mode**

User-driven step. Engineer runs:
```bash
cd /c/Users/anand/Downloads/local/idre
npx next build 2>&1 | tail -10
```

Expected: build completes with "Build completed" or similar. If errors, fix them before proceeding (this surfaces real IDRE-source issues that wouldn't appear in dev mode).

- [ ] **Step 3: Stop current dev server, start prod server**

User runs:
```bash
# Stop dev server (Ctrl+C in its terminal)
cd /c/Users/anand/Downloads/local/idre
npx next start --hostname 127.0.0.1 --port 3000
```

- [ ] **Step 4: Verify auto-login still works in prod mode**

Run:
```bash
curl -sS -I --max-time 15 "http://127.0.0.1:3000/api/dev/auto-login"
```

Expected: `HTTP/1.1 307 Temporary Redirect` with `set-cookie: better-auth.session_token=...`.

Note: Prod mode has `process.env.NODE_ENV === "production"` and the auto-login route gates on `!== "development"` returning 404. **THIS MAY BREAK auto-login.** If 404, the user must set `NODE_ENV=development` when starting:

```bash
NODE_ENV=development npx next start --hostname 127.0.0.1 --port 3000
```

Document this in the doc.

- [ ] **Step 5: Time a cases page render**

```bash
time curl -sS -b /tmp/cj.txt "http://127.0.0.1:3000/dashboard/cases?status=PENDING_RFI&limit=1" -o /dev/null
```

(use cookies saved from auto-login)

Expected: <5s real time. If >30s, investigate (indexes missing? prod build incomplete?).

- [ ] **Step 6: Commit**

```bash
cd /c/Users/anand/Downloads/local
git add docs/idre-local-prod-mode.md
git commit -m "docs(idre): prod build mode workflow for derived-dom suite"
```

---

## Task 3: Build `dom_scrape` validator

**Files:**
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\ui_validators\dom_scrape.py`
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\tests\test_dom_scrape_validator.py`
- Modify: `C:\Users\anand\Downloads\local\testing\v10_harness\ui_validators\__init__.py`

- [ ] **Step 1: Write the failing unit test first (HTML fixture)**

Create `testing/v10_harness/tests/test_dom_scrape_validator.py`:

```python
"""Unit tests for dom_scrape validator using static HTML fixtures."""
from playwright.sync_api import sync_playwright
import pytest


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context()
    p = ctx.new_page()
    yield p
    ctx.close()


def test_regex_capture_extracts_count(page):
    """Static HTML with 'Showing 1 to 1 of 5,123 items' -> count=5123."""
    page.set_content("""
        <html><body>
            <h1>Cases</h1>
            <div>Some chrome</div>
            <p class="pagination">Showing 1 to 1 of 5,123 items</p>
        </body></html>
    """)
    from testing.v10_harness.ui_validators.dom_scrape import DomScrapeValidator
    v = DomScrapeValidator()
    # Use a no-op URL since content is set; navigate to about:blank works
    # but we set_content after page is on about:blank already
    result = v.extract_from_page(page, {
        "wait_for_regex": r"Showing\s+\d+\s+to\s+\d+\s+of\s+[\d,]+\s+items",
        "extract": {
            "kind": "regex_capture",
            "pattern": r"Showing\s+\d+\s+to\s+\d+\s+of\s+([\d,]+)\s+items",
        },
    })
    assert result == {"count": 5123.0}


def test_regex_capture_no_match_raises(page):
    page.set_content("<html><body>nothing here</body></html>")
    from testing.v10_harness.ui_validators.dom_scrape import DomScrapeValidator
    v = DomScrapeValidator()
    with pytest.raises(RuntimeError, match="pattern not found"):
        v.extract_from_page(page, {
            "wait_for_regex": r"nothing",  # this matches; wait succeeds
            "extract": {
                "kind": "regex_capture",
                "pattern": r"Showing\s+([\d,]+)\s+items",
            },
        })


def test_selector_text_extracts_count(page):
    page.set_content("""
        <html><body>
            <div data-testid="total-cases">42</div>
        </body></html>
    """)
    from testing.v10_harness.ui_validators.dom_scrape import DomScrapeValidator
    v = DomScrapeValidator()
    result = v.extract_from_page(page, {
        "wait_for_selector": "[data-testid='total-cases']",
        "extract": {
            "kind": "selector_text",
            "selector": "[data-testid='total-cases']",
        },
    })
    assert result == {"count": 42.0}


def test_no_items_returns_zero(page):
    page.set_content("<html><body><p>No items</p></body></html>")
    from testing.v10_harness.ui_validators.dom_scrape import DomScrapeValidator
    v = DomScrapeValidator()
    result = v.extract_from_page(page, {
        "wait_for_regex": r"No items|Showing",
        "extract": {
            "kind": "regex_capture",
            "pattern": r"Showing\s+\d+\s+to\s+\d+\s+of\s+([\d,]+)\s+items",
            "zero_on_pattern": r"No items",
        },
    })
    assert result == {"count": 0.0}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/Users/anand/Downloads/local && py311 -m pytest testing/v10_harness/tests/test_dom_scrape_validator.py -v`

Expected: ImportError or ModuleNotFoundError for `dom_scrape`.

- [ ] **Step 3: Implement `dom_scrape.py`**

Create `testing/v10_harness/ui_validators/dom_scrape.py`:

```python
"""dom_scrape validator -- navigates IDRE URL, extracts count from rendered DOM.

Used for count-type tests where IDRE has a URL+filter combo that produces
the desired view. Extraction strategies: regex_capture on body text, or
selector_text via CSS selector. Returns {"<key>": <number>} where <key>
defaults to "count".
"""
from __future__ import annotations

import re
from typing import Any

from playwright.sync_api import Page

from . import REGISTRY
from .base import parse_number


DEFAULT_TIMEOUT_MS = 60000


class DomScrapeValidator:
    name = "dom_scrape"

    def extract(self, page: Page, params: dict) -> dict[str, Any]:
        """Navigate then extract. Used by the test runner."""
        url = params["url"]
        page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
        return self.extract_from_page(page, params)

    def extract_from_page(self, page: Page, params: dict) -> dict[str, Any]:
        """Extract on a page already loaded. Separable for unit testing."""
        # Wait for content to appear
        if "wait_for_regex" in params:
            page.wait_for_function(
                f"() => /{params['wait_for_regex']}/.test(document.body.innerText)",
                timeout=DEFAULT_TIMEOUT_MS,
            )
        elif "wait_for_selector" in params:
            page.wait_for_selector(params["wait_for_selector"], timeout=DEFAULT_TIMEOUT_MS)

        ext = params["extract"]
        key = ext.get("key", "count")

        # Check zero-pattern first (e.g., "No items")
        if "zero_on_pattern" in ext:
            body = page.evaluate("() => document.body.innerText")
            if re.search(ext["zero_on_pattern"], body):
                return {key: 0.0}

        if ext["kind"] == "regex_capture":
            body = page.evaluate("() => document.body.innerText")
            m = re.search(ext["pattern"], body)
            if not m:
                raise RuntimeError(
                    f"pattern not found in body for {key}: {ext['pattern']!r}; "
                    f"body head: {body[:300]!r}"
                )
            return {key: parse_number(m.group(1))}

        if ext["kind"] == "selector_text":
            txt = page.locator(ext["selector"]).inner_text(timeout=10000)
            return {key: parse_number(txt)}

        raise ValueError(f"unknown extract.kind: {ext['kind']!r}")


REGISTRY["dom_scrape"] = DomScrapeValidator
```

- [ ] **Step 4: Register in `__init__.py`**

Read `testing/v10_harness/ui_validators/__init__.py`, then add at the end:

```python
from . import dom_scrape  # noqa: E402,F401
```

(Keep the existing 4 imports above it.)

- [ ] **Step 5: Run test to verify it passes**

Run: `py311 -m pytest testing/v10_harness/tests/test_dom_scrape_validator.py -v`

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
cd /c/Users/anand/Downloads/local
git add testing/v10_harness/ui_validators/dom_scrape.py testing/v10_harness/ui_validators/__init__.py testing/v10_harness/tests/test_dom_scrape_validator.py
git commit -m "feat(ui-validation): dom_scrape validator (Task 3)"
```

---

## Task 4: Build `canonical_sql` validator

**Files:**
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\ui_validators\canonical_sql.py`
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\tests\test_canonical_sql_validator.py`
- Modify: `C:\Users\anand\Downloads\local\testing\v10_harness\ui_validators\__init__.py`

- [ ] **Step 1: Write the failing unit test**

Create `testing/v10_harness/tests/test_canonical_sql_validator.py`:

```python
"""Unit tests for canonical_sql validator. Hits local docker idre DB."""
import pytest


def test_canonical_sql_count_query():
    from testing.v10_harness.ui_validators.canonical_sql import CanonicalSqlValidator
    v = CanonicalSqlValidator()
    result = v.extract(None, {
        "sql": "SELECT 42 AS n",
        "scalar_key": "n",
    })
    assert result == {"count": 42.0}


def test_canonical_sql_custom_result_key():
    from testing.v10_harness.ui_validators.canonical_sql import CanonicalSqlValidator
    v = CanonicalSqlValidator()
    result = v.extract(None, {
        "sql": "SELECT 1234 AS total_payments",
        "scalar_key": "total_payments",
        "result_key": "totalPayments",
    })
    assert result == {"totalPayments": 1234.0}


def test_canonical_sql_requires_source_ref():
    """Defense: validator should reject entries without source_ref to keep
    canonical SQL authoring honest."""
    from testing.v10_harness.ui_validators.canonical_sql import CanonicalSqlValidator
    v = CanonicalSqlValidator()
    with pytest.raises(ValueError, match="source_ref"):
        v.extract(None, {
            "sql": "SELECT 1",
            "scalar_key": "n",
            "_skip_source_ref_check": False,
        })


def test_canonical_sql_against_real_db():
    """Sanity: actual local docker query returns a number."""
    from testing.v10_harness.ui_validators.canonical_sql import CanonicalSqlValidator
    v = CanonicalSqlValidator()
    result = v.extract(None, {
        "sql": "SELECT COUNT(*) AS n FROM `case`",
        "scalar_key": "n",
        "source_ref": "test sanity; no UI source needed",
    })
    assert result["count"] > 0  # snapshot has 67K+ cases
```

- [ ] **Step 2: Run test to verify it fails**

`py311 -m pytest testing/v10_harness/tests/test_canonical_sql_validator.py -v`

Expected: ImportError.

- [ ] **Step 3: Implement `canonical_sql.py`**

Create `testing/v10_harness/ui_validators/canonical_sql.py`:

```python
"""canonical_sql validator -- runs SQL against local docker `idre` DB.

Used ONLY for metrics IDRE has no URL+filter combo a real user could
navigate to. Each entry MUST include `source_ref` (string) justifying
why no UI exists and (where possible) referencing the IDRE source file
the SQL was derived from. This keeps canonical-SQL authoring honest --
if we can't articulate why no UI exists, the test is suspect.

Params:
  sql:           the COUNT(*) or aggregate query (no semicolons, no DDL/DML)
  scalar_key:    column alias in the result row (e.g. "n" for "SELECT COUNT(*) AS n")
  result_key:    key in the returned dict (default "count")
  source_ref:    REQUIRED; non-empty string explaining why no UI exists
                 + which IDRE source file informed the SQL where possible
"""
from __future__ import annotations

import re
from typing import Any

import pymysql

from . import REGISTRY


_FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|"
    r"REPLACE|RENAME|LOAD|HANDLER|LOCK|UNLOCK)\b",
    re.IGNORECASE,
)


class CanonicalSqlValidator:
    name = "canonical_sql"

    def extract(self, page, params: dict) -> dict[str, Any]:
        sql = params["sql"].strip().rstrip(";")
        scalar_key = params["scalar_key"]
        result_key = params.get("result_key", "count")

        # Integrity: require source_ref (unless explicitly skipped for tests)
        if not params.get("_skip_source_ref_check", True):
            ref = params.get("source_ref", "")
            if not ref or not ref.strip():
                raise ValueError(
                    "canonical_sql entry missing source_ref. Each canonical-SQL "
                    "test must justify why no IDRE UI exists for this metric."
                )

        # Security: reject any DDL/DML even though we connect read-write
        if _FORBIDDEN_SQL.search(sql):
            raise ValueError(
                f"canonical_sql rejected: SQL contains forbidden keyword "
                f"(DDL/DML not allowed in validator queries): {sql[:200]!r}"
            )
        if ";" in sql:
            raise ValueError("canonical_sql rejected: semicolons not allowed (single-statement only)")

        conn = pymysql.connect(
            host="127.0.0.1", port=3306, user="root", password="idrelocal",
            database="idre", charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor, autocommit=True,
        )
        try:
            with conn.cursor() as c:
                c.execute(sql)
                row = c.fetchone()
        finally:
            conn.close()

        if row is None:
            raise RuntimeError(f"canonical_sql returned no rows: {sql[:200]!r}")
        if scalar_key not in row:
            raise RuntimeError(
                f"canonical_sql: scalar_key {scalar_key!r} not in result row "
                f"(available: {list(row.keys())})"
            )
        val = row[scalar_key]
        # Coerce to float (handles MySQL's DECIMAL returning as Decimal)
        from decimal import Decimal
        if isinstance(val, Decimal):
            val = float(val)
        elif val is None:
            val = 0.0
        else:
            val = float(val)
        return {result_key: val}


REGISTRY["canonical_sql"] = CanonicalSqlValidator
```

- [ ] **Step 4: Register in `__init__.py`**

Add to `testing/v10_harness/ui_validators/__init__.py`:

```python
from . import canonical_sql  # noqa: E402,F401
```

- [ ] **Step 5: Run tests to verify passing**

`py311 -m pytest testing/v10_harness/tests/test_canonical_sql_validator.py -v`

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add testing/v10_harness/ui_validators/canonical_sql.py testing/v10_harness/ui_validators/__init__.py testing/v10_harness/tests/test_canonical_sql_validator.py
git commit -m "feat(ui-validation): canonical_sql validator (Task 4)"
```

---

## Task 5: Extend TestRecord + add derived-dom category

**Files:**
- Modify: `C:\Users\anand\Downloads\local\testing\v10_harness\runner.py`

- [ ] **Step 1: Read current runner.py**

Read `testing/v10_harness/runner.py`. Note the current `VALID_CATEGORIES` set and the `TestRecord` dataclass definition.

- [ ] **Step 2: Add "derived-dom" to VALID_CATEGORIES**

Edit `testing/v10_harness/runner.py`:

Find:
```python
VALID_CATEGORIES = {"known-report", "derived-query", "derived-ui"}
```

Replace with:
```python
VALID_CATEGORIES = {"known-report", "derived-query", "derived-ui", "derived-dom"}
```

- [ ] **Step 3: Add `result_type` field to TestRecord**

Find the `TestRecord` dataclass. Add field `result_type: str = "count"` after `validator_params`:

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
    validator: str | None = None
    validator_params: dict = field(default_factory=dict)
    result_type: str = "count"  # NEW: "count" | "rows" -- governs dom_lookup behavior
```

Update `from_dict` to pull `result_type`:

```python
return cls(
    # ... existing fields ...
    validator=d.get("validator"),
    validator_params=d.get("validator_params", {}),
    result_type=d.get("result_type", "count"),
)
```

- [ ] **Step 4: Smoke test from_dict still works for old records + accepts new field**

Run:
```bash
py311 -c "
import sys; sys.path.insert(0, '.')
from testing.v10_harness.runner import TestRecord, VALID_CATEGORIES
print('VALID_CATEGORIES:', VALID_CATEGORIES)
# Old known-report
r1 = TestRecord.from_dict({'id':'k','category':'known-report','prompt':'x','report':'r'})
print('old known:', r1.result_type)
# New derived-dom with rows
r2 = TestRecord.from_dict({
  'id':'d','category':'derived-dom','prompt':'show me 10 cases',
  'validator':'dom_lookup','result_type':'rows',
  'validator_params':{'sample_count':1},
})
print('new dom rows:', r2.result_type, r2.validator)
"
```

Expected: `VALID_CATEGORIES` includes derived-dom; `old known: count`; `new dom rows: rows dom_lookup`.

- [ ] **Step 5: Commit**

```bash
git add testing/v10_harness/runner.py
git commit -m "feat(harness): add derived-dom category + result_type field to TestRecord (Task 5)"
```

---

## Task 6: Build `run_derived_dom_test` runner + dom_lookup logic

**Files:**
- Modify: `C:\Users\anand\Downloads\local\testing\v10_harness\runner.py`

- [ ] **Step 1: Add `run_derived_dom_test` function**

Append to `testing/v10_harness/runner.py` (after `run_derived_ui_test`):

```python
def run_derived_dom_test(
    record: TestRecord,
    bot_runner: Callable[[str, NowAnchor], dict],
    page,
    now_anchor: NowAnchor,
) -> TestResult:
    """Run a derived-dom test (count or rows variant).

    count: validator extracts IDRE-side number, compare to bot's count.
    rows:  bot returns >=N rows; runner picks `sample_count` IDs and navigates
           IDRE per-row lookup URL, asserts expected text appears.
    """
    from testing.v10_harness.ui_validators import get as get_validator

    with measure() as bot_m:
        bot_raw = bot_runner(record.prompt, now_anchor)

    bot_raw_summary = {
        "sql": (bot_raw.get("sql") or "")[:500] if isinstance(bot_raw, dict) else None,
        "data_preview": str(bot_raw.get("data"))[:300] if isinstance(bot_raw, dict) else None,
        "row_count": bot_raw.get("row_count") if isinstance(bot_raw, dict) else None,
    }

    if record.result_type == "rows":
        return _verify_rows(record, bot_raw, page, bot_m, bot_raw_summary)

    # count flow -- reuse the reduction logic from derived-ui
    bot_dict: dict[str, Any] = {}
    data = bot_raw.get("data") if isinstance(bot_raw, dict) else bot_raw
    if isinstance(data, list) and data and isinstance(data[0], dict):
        first = data[0]
        if len(record.bot_must_return_keys) == 1:
            only_key = record.bot_must_return_keys[0]
            if only_key in first:
                bot_dict[only_key] = first[only_key]
            else:
                if len(data) > 1:
                    bot_dict[only_key] = len(data)
                else:
                    vals = list(first.values())
                    bot_dict[only_key] = vals[0] if vals else None
        else:
            for k in record.bot_must_return_keys:
                bot_dict[k] = first.get(k)
    elif isinstance(data, dict):
        for k in record.bot_must_return_keys:
            bot_dict[k] = data.get(k)
        if len(record.bot_must_return_keys) == 1:
            only_key = record.bot_must_return_keys[0]
            if bot_dict.get(only_key) is None:
                list_values = [v for v in data.values() if isinstance(v, list)]
                if len(list_values) == 1:
                    bot_dict[only_key] = len(list_values[0])

    if not record.validator:
        return TestResult(
            record=record, verdict=Verdict.FAIL,
            diffs=["derived-dom count record missing 'validator' field"],
            bot_measurement=bot_m.to_dict(), harness_measurement={},
            bot_payload={"reduced": bot_dict, "raw": bot_raw_summary},
            expected_payload=None,
        )

    with measure() as ui_m:
        validator = get_validator(record.validator)
        ui_dict = validator.extract(page, record.validator_params)

    cmp = compare_aggregates(bot_dict, ui_dict, float_tolerance=0.01)
    return TestResult(
        record=record, verdict=cmp.verdict, diffs=cmp.diff,
        bot_measurement=bot_m.to_dict(), harness_measurement=ui_m.to_dict(),
        bot_payload={"reduced": bot_dict, "raw": bot_raw_summary},
        expected_payload=ui_dict,
    )


def _verify_rows(record, bot_raw, page, bot_m, bot_raw_summary) -> TestResult:
    """rows-type validation: bot returned rows, sample N, verify in IDRE."""
    data = bot_raw.get("data") if isinstance(bot_raw, dict) else bot_raw
    if not isinstance(data, list):
        # bot returned dict (e.g., {cases: [...]}) -- unwrap if single list value
        if isinstance(data, dict):
            list_vals = [v for v in data.values() if isinstance(v, list)]
            if len(list_vals) == 1:
                data = list_vals[0]

    if not isinstance(data, list) or len(data) == 0:
        return TestResult(
            record=record, verdict=Verdict.FAIL,
            diffs=[f"rows-test expected list of rows from bot; got: {type(data).__name__} len={len(data) if hasattr(data, '__len__') else 'n/a'}"],
            bot_measurement=bot_m.to_dict(), harness_measurement={},
            bot_payload={"reduced": None, "raw": bot_raw_summary},
            expected_payload=None,
        )

    params = record.validator_params or {}
    id_column = params.get("id_column", "disputeReferenceNumber")
    sample_count = int(params.get("sample_count", 1))
    lookup_template = params["lookup_url_template"]
    expected_pattern = params["expected_text_pattern"]

    samples = data[:sample_count]
    # Ensure each row has the id_column
    sampled_ids = []
    for row in samples:
        if not isinstance(row, dict) or id_column not in row:
            return TestResult(
                record=record, verdict=Verdict.FAIL,
                diffs=[f"row missing id_column {id_column!r}; row keys={list(row.keys()) if isinstance(row, dict) else 'not-a-dict'}"],
                bot_measurement=bot_m.to_dict(), harness_measurement={},
                bot_payload={"reduced": None, "raw": bot_raw_summary},
                expected_payload=None,
            )
        sampled_ids.append(row[id_column])

    diffs = []
    verified = []
    with measure() as ui_m:
        for sample_id in sampled_ids:
            lookup_url = lookup_template.format(id=sample_id)
            try:
                page.goto(lookup_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_function(
                    f"() => /{expected_pattern}/.test(document.body.innerText)",
                    timeout=30000,
                )
                verified.append(sample_id)
            except Exception as exc:
                diffs.append(f"row {sample_id!r} lookup FAILED at {lookup_url}: {type(exc).__name__}: {str(exc)[:200]}")

    verdict = Verdict.PASS if len(verified) == len(sampled_ids) else Verdict.FAIL
    return TestResult(
        record=record, verdict=verdict, diffs=diffs,
        bot_measurement=bot_m.to_dict(), harness_measurement=ui_m.to_dict(),
        bot_payload={
            "rows_count": len(data),
            "sampled_ids": sampled_ids,
            "verified_ids": verified,
            "raw": bot_raw_summary,
        },
        expected_payload={"lookup_url_template": lookup_template, "expected_pattern": expected_pattern},
    )
```

- [ ] **Step 2: Smoke test the imports work**

Run:
```bash
py311 -c "from testing.v10_harness.runner import run_derived_dom_test; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add testing/v10_harness/runner.py
git commit -m "feat(harness): run_derived_dom_test + dom_lookup rows verification (Task 6)"
```

---

## Task 7: Build preflight module + conftest fixture

**Files:**
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\preflight.py`
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\tests\test_preflight.py`
- Modify: `C:\Users\anand\Downloads\local\testing\v10_harness\conftest.py`

- [ ] **Step 1: Write `preflight.py`**

Create `testing/v10_harness/preflight.py`:

```python
"""Pre-flight checks for derived-dom test suite.

Each check returns (ok: bool, message: str). Suite-level fixture
aggregates results; any FAIL -> skip the suite with explanatory message.
Some checks auto-remediate (e.g., apply indexes); others print remediation.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Callable

import pymysql
import requests


CheckResult = tuple[bool, str]
CheckFn = Callable[[], CheckResult]


def check_idre_running() -> CheckResult:
    try:
        r = requests.get("http://127.0.0.1:3000/", timeout=5, allow_redirects=False)
        return (r.status_code < 500, f"IDRE responded HTTP {r.status_code}")
    except Exception as e:
        return (False, f"IDRE not reachable: {type(e).__name__}: {e}. Start with: cd local/idre && npx next start --hostname 127.0.0.1 --port 3000")


def check_db_snapshot() -> CheckResult:
    try:
        conn = pymysql.connect(host="127.0.0.1", port=3306, user="root", password="idrelocal", database="idre", connect_timeout=10)
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM `case`")
            n = c.fetchone()[0]
        conn.close()
        if n > 10000:
            return (True, f"snapshot OK ({n} cases)")
        return (False, f"only {n} cases in idre DB; expected >10000 (snapshot not imported?). Re-import: see docs/superpowers/reports/2026-05-18-task20-snapshot-done.md")
    except Exception as e:
        return (False, f"DB connection failed: {type(e).__name__}: {e}")


def check_indexes_present() -> CheckResult:
    try:
        conn = pymysql.connect(host="127.0.0.1", port=3306, user="root", password="idrelocal", database="idre", connect_timeout=10)
        with conn.cursor() as c:
            c.execute("""SELECT COUNT(DISTINCT index_name) FROM information_schema.STATISTICS
                         WHERE table_schema='idre' AND index_name LIKE '%_v10'""")
            n = c.fetchone()[0]
        conn.close()
        if n >= 5:
            return (True, f"{n} v10 indexes present")
        # Auto-remediate
        apply_script = Path(__file__).parent.parent.parent / ".snapshots" / "apply_indexes.py"
        if apply_script.exists():
            subprocess.run(["py311", str(apply_script)], check=False, capture_output=True)
            return (True, f"applied indexes (was {n}, now should be 9)")
        return (False, f"only {n} v10 indexes; run .snapshots/apply_indexes.py")
    except Exception as e:
        return (False, f"index check failed: {type(e).__name__}: {e}")


def check_ryan_auth() -> CheckResult:
    try:
        r = requests.get("http://127.0.0.1:3000/api/dev/auto-login", timeout=30, allow_redirects=False)
        if r.status_code == 307 and "set-cookie" in {k.lower() for k in r.headers.keys()}:
            cookie = r.headers.get("set-cookie", "")
            if "session_token" in cookie:
                return (True, "auto-login set session cookie")
        # Try to read body for diagnostic
        body = r.text[:200] if hasattr(r, "text") else ""
        return (False, f"auto-login HTTP {r.status_code}, no session cookie. Body: {body!r}. Remediate: reset Ryan password (.snapshots/reset_ryan_password.py) and clear twoFactor table for Ryan.")
    except Exception as e:
        return (False, f"auto-login failed: {type(e).__name__}: {e}")


def check_prod_mode_render_speed() -> CheckResult:
    """Time a cases page render. <5s = good (likely prod build). >30s = dev mode or broken."""
    try:
        s = requests.Session()
        s.get("http://127.0.0.1:3000/api/dev/auto-login", allow_redirects=True, timeout=30)
        t0 = time.time()
        r = s.get("http://127.0.0.1:3000/dashboard/cases?limit=1", timeout=60)
        elapsed = time.time() - t0
        if r.status_code >= 500:
            return (False, f"cases page HTTP {r.status_code} in {elapsed:.1f}s")
        if elapsed < 5:
            return (True, f"cases page rendered in {elapsed:.1f}s (prod mode OK)")
        if elapsed < 30:
            return (True, f"cases page rendered in {elapsed:.1f}s (slow; may be dev mode)")
        return (False, f"cases page took {elapsed:.1f}s; check IDRE prod build (see docs/idre-local-prod-mode.md)")
    except Exception as e:
        return (False, f"render speed check failed: {type(e).__name__}: {e}")


CHECKS: list[tuple[str, CheckFn]] = [
    ("idre_running", check_idre_running),
    ("db_snapshot", check_db_snapshot),
    ("indexes_present", check_indexes_present),
    ("ryan_auth", check_ryan_auth),
    ("prod_mode_render_speed", check_prod_mode_render_speed),
]


def run_all() -> tuple[bool, list[tuple[str, bool, str]]]:
    results = []
    overall = True
    for name, fn in CHECKS:
        ok, msg = fn()
        results.append((name, ok, msg))
        if not ok:
            overall = False
    return overall, results


def format_report(results: list[tuple[str, bool, str]]) -> str:
    lines = []
    for name, ok, msg in results:
        flag = "OK" if ok else "FAIL"
        lines.append(f"  [{flag}] {name}: {msg}")
    return "\n".join(lines)


if __name__ == "__main__":
    overall, results = run_all()
    print(format_report(results))
    import sys
    sys.exit(0 if overall else 1)
```

- [ ] **Step 2: Write unit test**

Create `testing/v10_harness/tests/test_preflight.py`:

```python
"""Unit tests for preflight checks (live -- requires environment up)."""
import pytest


def test_preflight_runs_all():
    from testing.v10_harness.preflight import run_all, CHECKS
    overall, results = run_all()
    # All checks return a (bool, str)
    assert len(results) == len(CHECKS)
    for name, ok, msg in results:
        assert isinstance(name, str)
        assert isinstance(ok, bool)
        assert isinstance(msg, str)
        assert msg  # non-empty

# Note: we don't assert overall=True because IDRE may not be in prod mode
# during dev/CI. The fixture in conftest will skip the derived-dom suite
# if any check fails, with the report printed.
```

- [ ] **Step 3: Run preflight directly to verify environment**

```bash
py311 testing/v10_harness/preflight.py
```

Expected: all checks print `[OK]`. If any FAIL, fix per the remediation message before continuing.

- [ ] **Step 4: Add preflight fixture to conftest.py**

Read `testing/v10_harness/conftest.py`, then append at the end:

```python
@pytest.fixture(scope="session")
def derived_dom_preflight():
    """Suite-gating fixture for derived-dom tests. Skips suite on any FAIL."""
    from testing.v10_harness.preflight import run_all, format_report
    overall, results = run_all()
    if not overall:
        report = format_report(results)
        pytest.skip(f"derived-dom preflight failed:\n{report}")
    yield results
```

- [ ] **Step 5: Run preflight unit test**

```bash
py311 -m pytest testing/v10_harness/tests/test_preflight.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add testing/v10_harness/preflight.py testing/v10_harness/tests/test_preflight.py testing/v10_harness/conftest.py
git commit -m "feat(harness): preflight checklist + autouse fixture (Task 7)"
```

---

## Task 8: Build test_baseline_derived_dom.py

**Files:**
- Create: `C:\Users\anand\Downloads\local\testing\v10_harness\tests\test_baseline_derived_dom.py`

- [ ] **Step 1: Write the test file**

Create `testing/v10_harness/tests/test_baseline_derived_dom.py`:

```python
"""Parametrized run of derived-dom tests against the V10 bot.

Pure DOM standard (no API ground truth). Uses dom_scrape / dom_lookup /
canonical_sql validators. Requires preflight to pass (IDRE prod mode +
snapshot + indexes + auth).
"""
import json
import os
import sys
from pathlib import Path

import pytest

# Same env overrides as derived-ui suite -- bot reads local docker idre
if not os.environ.get("V10_USE_STAGING"):
    os.environ["DB_HOST"] = "127.0.0.1"
    os.environ["DB_PORT"] = "3306"
    os.environ["DB_NAME"] = "idre"
    os.environ["DB_USER"] = "root"
    os.environ["DB_PASSWORD"] = "idrelocal"
    os.environ["DB_SSL_CA"] = "__nonexistent_disable_ssl__"

os.environ.setdefault("V10_AMBIGUITY_THRESHOLD", "1.0")

from testing.v10_harness.runner import (
    TestRecord, run_derived_dom_test, TestResult,
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


def _dom_records() -> list[TestRecord]:
    return [r for r in _load_set() if r.category == "derived-dom"]


@pytest.fixture(scope="session")
def bot_runner_v10_dom():
    sys.path.insert(0, "C:/Users/anand/Downloads/v10_reports_bot")
    from harness_entrypoint import run_query_v10

    def runner(prompt: str, now):
        return run_query_v10(prompt, now_anchor=now)
    return runner


_RECORDS = _dom_records()


@pytest.mark.parametrize("record", _RECORDS, ids=[r.id for r in _RECORDS])
def test_derived_dom(record, bot_runner_v10_dom, playwright_page, now_anchor, derived_dom_preflight):
    result: TestResult = run_derived_dom_test(
        record, bot_runner_v10_dom, playwright_page, now_anchor,
    )
    REPORTS_DIR.mkdir(exist_ok=True)
    out = REPORTS_DIR / f"{record.id}.json"
    with open(out, "w") as f:
        json.dump(result.to_dict(), f, indent=2, default=str)
    if result.verdict != Verdict.PASS:
        try:
            playwright_page.screenshot(
                path=str(REPORTS_DIR / f"{record.id}_failure.png"),
                full_page=True,
            )
        except Exception:
            pass
    assert result.verdict == Verdict.PASS, (
        f"{record.id}: bot={result.bot_payload} expected={result.expected_payload} "
        f"diffs={result.diffs}"
    )
```

- [ ] **Step 2: Smoke test collection (will be empty since no derived-dom entries yet)**

```bash
py311 -m pytest testing/v10_harness/tests/test_baseline_derived_dom.py --collect-only 2>&1 | tail -5
```

Expected: collects 1 placeholder test (no derived-dom records yet) or 0 tests.

- [ ] **Step 3: Commit**

```bash
git add testing/v10_harness/tests/test_baseline_derived_dom.py
git commit -m "feat(harness): parametrized derived-dom pytest runner (Task 8)"
```

---

## Task 9: Source and author ~30 derived-dom test entries

**Files:**
- Modify: `C:\Users\anand\Downloads\local\testing\v10_harness\test_set.jsonl`

This is the highest-judgment task; authoring will iterate. Goal is ~30 entries covering Ashlee + screenshot + audit-findings.

- [ ] **Step 1: Find Ashlee's archived .eml files**

Search:
```bash
ls /c/Users/anand/Downloads/v8_reports_bot/ 2>/dev/null | grep -i "eml\|ashlee\|status"
find /c/Users/anand/Downloads/ -maxdepth 3 -iname "*ashlee*" 2>/dev/null | head
find /c/Users/anand/Downloads/ -maxdepth 3 -iname "*.eml" 2>/dev/null | head
```

If found, read 2-3 .eml files and extract the recurring metric names.

If not found, fall back to using `C:\Users\anand\Downloads\final idre reports bot\IDRE_Report_Audit_Findings.md` which the memory says has the same recurring items.

- [ ] **Step 2: Read IDRE_Report_Audit_Findings.md**

```bash
head -400 "/c/Users/anand/Downloads/final idre reports bot/IDRE_Report_Audit_Findings.md"
```

Extract the verified metric+SQL pairs from this doc.

- [ ] **Step 3: Inventory IDRE pages reachable for status filters**

These status filters DO work via URL (verified earlier):
- `/dashboard/cases?status=PENDING_RFI&limit=1` -> pagination footer
- `/dashboard/cases?status=INITIAL_ELIGIBILITY_REVIEW&limit=1`
- (any status enum value works)

These do NOT work via URL (no createdAt/modifiedAt filter):
- "created today"
- "MTD final determinations"
- "MTD defaults"

For status-filtered counts, use `dom_scrape` with the pagination-footer regex pattern from existing `case_status_filter.py`. For time-windowed metrics, use `canonical_sql` with `source_ref` justifying.

- [ ] **Step 4: Map IDRE case-detail page URL for rows-type lookup**

The case detail page is at `/dashboard/cases/{id}` (where {id} is the case's UUID like `000515d2-2ef7-4cfd-acc7-a558f4accff0`). It displays status, parties, dispute reference, etc.

For dom_lookup test entries:
- `id_column`: `"id"` (or `"disputeReferenceNumber"` if bot returns ref numbers)
- `lookup_url_template`: `"http://127.0.0.1:3000/dashboard/cases/{id}"`
- `expected_text_pattern`: the status the bot claimed for that case (regex-escaped)

Verify a sample case-detail page renders fast enough and contains its status:
```bash
curl -sS -b /tmp/cj.txt "http://127.0.0.1:3000/dashboard/cases/<some_real_uuid>" -o /tmp/case.html
grep -oE "(Status|status)[^<>]{0,40}" /tmp/case.html | head
```

If detail page is also too slow, fall back to `/dashboard/cases?search=<disputeReferenceNumber>` and the regex `"PENDING_RFI"` (or appropriate status).

- [ ] **Step 5: Author entries -- batch 1 (status filters, ~12 entries)**

Append to `testing/v10_harness/test_set.jsonl`:

```jsonl
{"id":"DD_pending_rfi","category":"derived-dom","prompt":"how many cases are pending RFI?","result_type":"count","validator":"dom_scrape","validator_params":{"url":"http://127.0.0.1:3000/dashboard/cases?status=PENDING_RFI&limit=1","wait_for_regex":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+[\\d,]+\\s+items|No items","extract":{"kind":"regex_capture","pattern":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)\\s+items","zero_on_pattern":"No items"}},"bot_must_return_keys":["count"],"temporality":"stable"}
{"id":"DD_initial_elig","category":"derived-dom","prompt":"how many cases are in initial eligibility review?","result_type":"count","validator":"dom_scrape","validator_params":{"url":"http://127.0.0.1:3000/dashboard/cases?status=INITIAL_ELIGIBILITY_REVIEW&limit=1","wait_for_regex":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+[\\d,]+\\s+items|No items","extract":{"kind":"regex_capture","pattern":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)\\s+items","zero_on_pattern":"No items"}},"bot_must_return_keys":["count"],"temporality":"stable"}
{"id":"DD_final_det_pending","category":"derived-dom","prompt":"how many cases have final determination pending?","result_type":"count","validator":"dom_scrape","validator_params":{"url":"http://127.0.0.1:3000/dashboard/cases?status=FINAL_DETERMINATION_PENDING&limit=1","wait_for_regex":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+[\\d,]+\\s+items|No items","extract":{"kind":"regex_capture","pattern":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)\\s+items","zero_on_pattern":"No items"}},"bot_must_return_keys":["count"],"temporality":"stable"}
{"id":"DD_final_det_rendered","category":"derived-dom","prompt":"how many cases have a final determination rendered?","result_type":"count","validator":"dom_scrape","validator_params":{"url":"http://127.0.0.1:3000/dashboard/cases?status=FINAL_DETERMINATION_RENDERED&limit=1","wait_for_regex":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+[\\d,]+\\s+items|No items","extract":{"kind":"regex_capture","pattern":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)\\s+items","zero_on_pattern":"No items"}},"bot_must_return_keys":["count"],"temporality":"stable"}
{"id":"DD_final_elig_completed","category":"derived-dom","prompt":"how many cases have completed final eligibility?","result_type":"count","validator":"dom_scrape","validator_params":{"url":"http://127.0.0.1:3000/dashboard/cases?status=FINAL_ELIGIBILITY_COMPLETED&limit=1","wait_for_regex":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+[\\d,]+\\s+items|No items","extract":{"kind":"regex_capture","pattern":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)\\s+items","zero_on_pattern":"No items"}},"bot_must_return_keys":["count"],"temporality":"stable"}
{"id":"DD_pending_payments","category":"derived-dom","prompt":"how many cases are in pending payments status?","result_type":"count","validator":"dom_scrape","validator_params":{"url":"http://127.0.0.1:3000/dashboard/cases?status=PENDING_PAYMENTS&limit=1","wait_for_regex":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+[\\d,]+\\s+items|No items","extract":{"kind":"regex_capture","pattern":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)\\s+items","zero_on_pattern":"No items"}},"bot_must_return_keys":["count"],"temporality":"stable"}
{"id":"DD_pending_second_payment","category":"derived-dom","prompt":"how many cases are pending second payment?","result_type":"count","validator":"dom_scrape","validator_params":{"url":"http://127.0.0.1:3000/dashboard/cases?status=PENDING_SECOND_PAYMENT&limit=1","wait_for_regex":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+[\\d,]+\\s+items|No items","extract":{"kind":"regex_capture","pattern":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)\\s+items","zero_on_pattern":"No items"}},"bot_must_return_keys":["count"],"temporality":"stable"}
{"id":"DD_final_elig_review","category":"derived-dom","prompt":"how many cases are in final eligibility review?","result_type":"count","validator":"dom_scrape","validator_params":{"url":"http://127.0.0.1:3000/dashboard/cases?status=FINAL_ELIGIBILITY_REVIEW&limit=1","wait_for_regex":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+[\\d,]+\\s+items|No items","extract":{"kind":"regex_capture","pattern":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)\\s+items","zero_on_pattern":"No items"}},"bot_must_return_keys":["count"],"temporality":"stable"}
{"id":"DD_ineligible_admin","category":"derived-dom","prompt":"how many cases are ineligible pending admin fee?","result_type":"count","validator":"dom_scrape","validator_params":{"url":"http://127.0.0.1:3000/dashboard/cases?status=INELIGIBLE_PENDING_ADMIN_FEE&limit=1","wait_for_regex":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+[\\d,]+\\s+items|No items","extract":{"kind":"regex_capture","pattern":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)\\s+items","zero_on_pattern":"No items"}},"bot_must_return_keys":["count"],"temporality":"stable"}
{"id":"DD_pending_admin_closure","category":"derived-dom","prompt":"how many cases are pending administrative closure?","result_type":"count","validator":"dom_scrape","validator_params":{"url":"http://127.0.0.1:3000/dashboard/cases?status=PENDING_ADMINISTRATIVE_CLOSURE&limit=1","wait_for_regex":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+[\\d,]+\\s+items|No items","extract":{"kind":"regex_capture","pattern":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)\\s+items","zero_on_pattern":"No items"}},"bot_must_return_keys":["count"],"temporality":"stable"}
{"id":"DD_pending_closure_payments","category":"derived-dom","prompt":"how many cases are pending closure payments?","result_type":"count","validator":"dom_scrape","validator_params":{"url":"http://127.0.0.1:3000/dashboard/cases?status=PENDING_CLOSURE_PAYMENTS&limit=1","wait_for_regex":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+[\\d,]+\\s+items|No items","extract":{"kind":"regex_capture","pattern":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)\\s+items","zero_on_pattern":"No items"}},"bot_must_return_keys":["count"],"temporality":"stable"}
{"id":"DD_pending_initial_rfi","category":"derived-dom","prompt":"how many cases are pending initial RFI?","result_type":"count","validator":"dom_scrape","validator_params":{"url":"http://127.0.0.1:3000/dashboard/cases?status=PENDING_INITIAL_RFI&limit=1","wait_for_regex":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+[\\d,]+\\s+items|No items","extract":{"kind":"regex_capture","pattern":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)\\s+items","zero_on_pattern":"No items"}},"bot_must_return_keys":["count"],"temporality":"stable"}
```

- [ ] **Step 6: Author batch 2 (no-UI metrics via canonical_sql, ~8 entries)**

Append:

```jsonl
{"id":"DD_mtd_final_dets","category":"derived-dom","prompt":"how many final determinations have been rendered this month?","result_type":"count","validator":"canonical_sql","validator_params":{"sql":"SELECT COUNT(*) AS n FROM `case` WHERE status='FINAL_DETERMINATION_RENDERED' AND statusChangedAt >= DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-01')","scalar_key":"n","source_ref":"IDRE has no URL filter on statusChangedAt; SQL is direct status+date filter on case table; lib/utils/report-calculations.ts patterns use statusChangedAt for closure dates"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"DD_mtd_defaults","category":"derived-dom","prompt":"how many cases were closed as default this month?","result_type":"count","validator":"canonical_sql","validator_params":{"sql":"SELECT COUNT(*) AS n FROM `case` WHERE status IN ('CLOSED_DEFAULT','CLOSED_DEFAULT_IP','CLOSED_DEFAULT_NIP') AND statusChangedAt >= DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-01')","scalar_key":"n","source_ref":"3 closure-default statuses per schema enum; IDRE has no UI filter combining default-closure types and MTD"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"DD_new_today","category":"derived-dom","prompt":"how many cases were created today?","result_type":"count","validator":"canonical_sql","validator_params":{"sql":"SELECT COUNT(*) AS n FROM `case` WHERE createdAt >= DATE(UTC_TIMESTAMP())","scalar_key":"n","source_ref":"IDRE has no createdAt URL filter on cases page; SQL is direct count on createdAt today"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"DD_mtd_new_cases","category":"derived-dom","prompt":"how many cases came in this month so far?","result_type":"count","validator":"canonical_sql","validator_params":{"sql":"SELECT COUNT(*) AS n FROM `case` WHERE createdAt >= DATE_FORMAT(UTC_TIMESTAMP(), '%Y-%m-01')","scalar_key":"n","source_ref":"Same gap as DD_new_today; IDRE has no createdAt URL filter"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"DD_total_completed_payments","category":"derived-dom","prompt":"what is the total amount of completed case payments?","result_type":"count","validator":"canonical_sql","validator_params":{"sql":"SELECT SUM(amount) AS total FROM payment WHERE type='CASE_PAYMENT' AND status='COMPLETED'","scalar_key":"total","result_key":"totalPayments","source_ref":"IDRE displays this on dashboard-stats card but no dedicated page; matches app/api/reports/dashboard-stats/route.ts:93-105"},"bot_must_return_keys":["totalPayments"],"temporality":"stable"}
{"id":"DD_pending_payments_count","category":"derived-dom","prompt":"how many payments are still pending?","result_type":"count","validator":"canonical_sql","validator_params":{"sql":"SELECT COUNT(*) AS n FROM payment WHERE status='PENDING'","scalar_key":"n","source_ref":"IDRE has no public page filtered by payment.status=PENDING; direct count on payment table"},"bot_must_return_keys":["count"],"temporality":"stable"}
{"id":"DD_active_arbitrators_count","category":"derived-dom","prompt":"how many active arbitrators are there?","result_type":"count","validator":"canonical_sql","validator_params":{"sql":"SELECT COUNT(*) AS n FROM user WHERE role IN ('arbitrator','arbitrator-contractor')","scalar_key":"n","source_ref":"IDRE displays on dashboard but no page-with-list-of-arbitrators URL; matches app/api/reports/dashboard-stats/route.ts:108-114"},"bot_must_return_keys":["count"],"temporality":"stable"}
{"id":"DD_total_cases","category":"derived-dom","prompt":"how many total cases are in the system?","result_type":"count","validator":"canonical_sql","validator_params":{"sql":"SELECT COUNT(*) AS n FROM `case`","scalar_key":"n","source_ref":"IDRE displays total on dashboard card; no dedicated page (unfiltered /dashboard/cases is too slow at 67K). Direct count."},"bot_must_return_keys":["count"],"temporality":"stable"}
```

- [ ] **Step 7: Author batch 3 (rows-type with dom_lookup, ~5 entries)**

Append:

```jsonl
{"id":"DD_rows_pending_rfi","category":"derived-dom","prompt":"show me 10 cases that are pending RFI","result_type":"rows","validator":"dom_lookup","validator_params":{"id_column":"id","lookup_url_template":"http://127.0.0.1:3000/dashboard/cases?search={id}&limit=1","expected_text_pattern":"PENDING_RFI","sample_count":1},"bot_must_return_keys":["id"],"temporality":"stable"}
{"id":"DD_rows_initial_elig","category":"derived-dom","prompt":"give me 5 cases in initial eligibility review","result_type":"rows","validator":"dom_lookup","validator_params":{"id_column":"id","lookup_url_template":"http://127.0.0.1:3000/dashboard/cases?search={id}&limit=1","expected_text_pattern":"INITIAL_ELIGIBILITY_REVIEW","sample_count":1},"bot_must_return_keys":["id"],"temporality":"stable"}
{"id":"DD_rows_final_det_pending","category":"derived-dom","prompt":"show me 10 cases with final determination pending","result_type":"rows","validator":"dom_lookup","validator_params":{"id_column":"id","lookup_url_template":"http://127.0.0.1:3000/dashboard/cases?search={id}&limit=1","expected_text_pattern":"FINAL_DETERMINATION_PENDING","sample_count":1},"bot_must_return_keys":["id"],"temporality":"stable"}
{"id":"DD_rows_recent_5","category":"derived-dom","prompt":"give me the 5 most recently created cases","result_type":"rows","validator":"dom_lookup","validator_params":{"id_column":"id","lookup_url_template":"http://127.0.0.1:3000/dashboard/cases/{id}","expected_text_pattern":"Case Details|Dispute|Status","sample_count":1},"bot_must_return_keys":["id","createdAt"],"temporality":"variant"}
{"id":"DD_rows_pending_payments","category":"derived-dom","prompt":"show me 10 cases waiting on payments","result_type":"rows","validator":"dom_lookup","validator_params":{"id_column":"id","lookup_url_template":"http://127.0.0.1:3000/dashboard/cases?search={id}&limit=1","expected_text_pattern":"PENDING_PAYMENTS|PENDING_SECOND_PAYMENT","sample_count":1},"bot_must_return_keys":["id"],"temporality":"stable"}
```

- [ ] **Step 8: Author batch 4 (additional Ashlee/screenshot items, ~5 entries)**

Append:

```jsonl
{"id":"DD_overdue_count","category":"derived-dom","prompt":"how many cases are currently overdue?","result_type":"count","validator":"canonical_sql","validator_params":{"sql":"SELECT COUNT(*) AS n FROM `case` WHERE COALESCE(due_date, eligibilityDueDate, paymentDueDate, due_date_until_decision) < UTC_TIMESTAMP()","scalar_key":"n","source_ref":"IDRE's /api/reports/due-dates/summary returns this; no UI page filters cases by overdue-of-primary-due-date. Logic mirrors lib/reports/due-dates.ts:335 primary date selection"},"bot_must_return_keys":["count"],"temporality":"variant"}
{"id":"DD_completed_count","category":"derived-dom","prompt":"how many disputes have been completed?","result_type":"count","validator":"dom_scrape","validator_params":{"url":"http://127.0.0.1:3000/dashboard/cases?status=COMPLETED&limit=1","wait_for_regex":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+[\\d,]+\\s+items|No items","extract":{"kind":"regex_capture","pattern":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)\\s+items","zero_on_pattern":"No items"}},"bot_must_return_keys":["count"],"temporality":"stable"}
{"id":"DD_reopened_count","category":"derived-dom","prompt":"how many cases were reopened for correction?","result_type":"count","validator":"dom_scrape","validator_params":{"url":"http://127.0.0.1:3000/dashboard/cases?status=REOPENED_FOR_CORRECTION&limit=1","wait_for_regex":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+[\\d,]+\\s+items|No items","extract":{"kind":"regex_capture","pattern":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)\\s+items","zero_on_pattern":"No items"}},"bot_must_return_keys":["count"],"temporality":"stable"}
{"id":"DD_ineligible_count","category":"derived-dom","prompt":"how many cases are ineligible?","result_type":"count","validator":"dom_scrape","validator_params":{"url":"http://127.0.0.1:3000/dashboard/cases?status=INELIGIBLE&limit=1","wait_for_regex":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+[\\d,]+\\s+items|No items","extract":{"kind":"regex_capture","pattern":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)\\s+items","zero_on_pattern":"No items"}},"bot_must_return_keys":["count"],"temporality":"stable"}
{"id":"DD_notice_dismissal_count","category":"derived-dom","prompt":"how many cases got a notice of dismissal for non-payment?","result_type":"count","validator":"dom_scrape","validator_params":{"url":"http://127.0.0.1:3000/dashboard/cases?status=NOTICE_OF_DISMISSAL_NON_PAYMENT&limit=1","wait_for_regex":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+[\\d,]+\\s+items|No items","extract":{"kind":"regex_capture","pattern":"Showing\\s+\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)\\s+items","zero_on_pattern":"No items"}},"bot_must_return_keys":["count"],"temporality":"stable"}
```

- [ ] **Step 9: Verify count and validity**

```bash
py311 -c "
import json
n_dom = 0
for line in open(r'C:\Users\anand\Downloads\local\testing\v10_harness\test_set.jsonl'):
    line = line.strip()
    if not line: continue
    d = json.loads(line)
    if d.get('category') == 'derived-dom': n_dom += 1
print(f'{n_dom} derived-dom entries')
"
```

Expected: `30 derived-dom entries`.

- [ ] **Step 10: Verify collection**

```bash
py311 -m pytest testing/v10_harness/tests/test_baseline_derived_dom.py --collect-only -q 2>&1 | tail -8
```

Expected: 30 tests collected (one per DD_ entry).

- [ ] **Step 11: Commit**

```bash
git add testing/v10_harness/test_set.jsonl
git commit -m "test(set): 30 derived-dom entries -- Ashlee + screenshot + audit-findings (Task 9)"
```

---

## Task 10: Run full baseline + iterate

- [ ] **Step 1: Pre-flight check standalone**

```bash
py311 testing/v10_harness/preflight.py
```

Expected: all checks OK. If any fail, remediate per the printed message and re-run.

- [ ] **Step 2: Run full derived-dom baseline (in background due to runtime)**

```bash
py311 -m pytest testing/v10_harness/tests/test_baseline_derived_dom.py -v --tb=line 2>&1 | tee /tmp/derived_dom_baseline.log
```

Expected runtime: 30 tests x 20-60s each = 10-30 min. Target: 25/30 PASS on first run.

- [ ] **Step 3: Summarize PASS/FAIL**

```bash
py311 -c "
import json, glob
results = {'PASS':[], 'FAIL':[], 'OTHER':[]}
for p in glob.glob(r'C:\Users\anand\Downloads\local\testing\v10_harness\reports\DD_*.json'):
    d = json.load(open(p))
    v = d.get('verdict', 'OTHER')
    results.setdefault(v, []).append(d['id'])
for k, v in results.items():
    print(f'{k}: {len(v)}')
print('\\nFAILs:')
for fid in results.get('FAIL', []):
    print(' ', fid)
"
```

- [ ] **Step 4: For each FAIL, classify**

For each failing test, examine `reports/{id}.json`:
- `bot_payload.raw.sql` -- what SQL the bot generated
- `bot_payload.raw.data_preview` -- what bot returned
- `expected_payload` -- what validator returned
- `diffs` -- specific mismatch

Classify:
- **Real bot SQL bug**: bot's SQL is wrong vs IDRE's logic. Rewrite the prompt to be more explicit, OR document as known bot limitation.
- **NL ambiguity**: bot interpreted differently than expected. Rephrase prompt.
- **IDRE UI race**: page didn't render in time. Increase timeout or add retry.
- **Validator bug**: SQL/regex/selector wrong. Fix validator entry.

- [ ] **Step 5: Iterate**

Fix highest-impact failures first. Re-run only affected tests with `-k`:

```bash
py311 -m pytest testing/v10_harness/tests/test_baseline_derived_dom.py -v -k "DD_pending_rfi or DD_rows_pending_rfi" --tb=line
```

Loop until 30/30 PASS (or known-limitation count documented).

- [ ] **Step 6: Tag**

```bash
cd /c/Users/anand/Downloads/local
git tag -a derived-dom-baseline-phase1 -m "Initial derived-dom Phase 1 baseline: 30 tests, pure DOM scrape standard"
git push origin main --tags
```

---

## Task 11: Write the Phase 1 done doc

**Files:**
- Create: `C:\Users\anand\Downloads\local\docs\superpowers\reports\2026-05-18-derived-dom-phase1-done.md`

- [ ] **Step 1: Write the doc**

Include sections:
- Pass rate (X/30)
- Per-failure classification (if any)
- Validator stats: how many `dom_scrape` / `dom_lookup` / `canonical_sql`
- Total runtime
- Lessons for Phase 2 (~80 tests) scaling
- Refresh procedure (one-line command)

- [ ] **Step 2: Commit + push**

```bash
git add docs/superpowers/reports/2026-05-18-derived-dom-phase1-done.md
git commit -m "docs: derived-dom Phase 1 done -- baseline pass rate documented"
git push origin main
```

---

## Self-Review

**Spec coverage:** Walked the spec; every section maps to a task:
- Spec section 3.2 (validators): Tasks 3 (dom_scrape), 4 (canonical_sql), 6 (dom_lookup runner-integrated)
- Spec section 3.3 (TestRecord extensions): Task 5
- Spec section 3.4 (performance prereqs): Tasks 1 (indexes), 2 (prod build)
- Spec section 4.1 (new files): all created across Tasks 1-9
- Spec section 5 (data flow): Task 6 runner implements both count + rows flows
- Spec section 6 (test sourcing): Task 9 (10 sub-steps for batches)
- Spec section 7 (preflight): Task 7
- Spec section 11 (DoD): Task 10 (baseline) + Task 11 (done doc)

**Placeholder scan:** No "TBD", "implement later", or vague-error patterns. All code blocks are concrete. Test entries use full URLs and regex patterns. The one acknowledged unknown (path to Ashlee .eml archives) has a documented fallback (use IDRE_Report_Audit_Findings.md).

**Type consistency:** `result_type` field name used consistently across runner.py (Task 5), runner.py logic (Task 6), test file (Task 8), and JSONL entries (Task 9). Validator names (`dom_scrape`, `canonical_sql`, `dom_lookup`) match across REGISTRY, JSONL `validator` field, and runner dispatch. `derived-dom` category constant matches in VALID_CATEGORIES + JSONL + test file filter.

Self-review pass.

---

## Execution

This plan is ready for execution. Per session preference, proceeding with subagent-driven-development.
