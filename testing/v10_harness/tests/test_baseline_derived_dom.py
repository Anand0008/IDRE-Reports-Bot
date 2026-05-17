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
