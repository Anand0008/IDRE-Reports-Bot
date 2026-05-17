"""Parametrized run of derived-ui tests.

Bot generates SQL via V10 pipeline; validator scrapes IDRE UI/API; compare.
Bot selection via env var BOT=v10 (default) or BOT=v8.
Skips if IDRE local server isn't reachable (handled by playwright_page fixture).
"""
import json
import os
import sys
from pathlib import Path

import pytest

from testing.v10_harness.runner import (
    TestRecord, run_derived_ui_test, TestResult,
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


def _ui_records() -> list[TestRecord]:
    return [r for r in _load_set() if r.category == "derived-ui"]


@pytest.fixture(scope="session")
def bot_runner_v10():
    """V10 bot pipeline. derived-ui tests always use V10 (not V8)."""
    which = os.environ.get("BOT", "v10")
    if which != "v10":
        pytest.skip(f"derived-ui tests require BOT=v10; got BOT={which}")
    sys.path.insert(0, "C:/Users/anand/Downloads/v10_reports_bot")
    from harness_entrypoint import run_query_v10

    def runner(prompt: str, now):
        return run_query_v10(prompt, now_anchor=now)
    return runner


_RECORDS = _ui_records()


@pytest.mark.parametrize("record", _RECORDS, ids=[r.id for r in _RECORDS])
def test_derived_ui(record, bot_runner_v10, playwright_page, now_anchor):
    result: TestResult = run_derived_ui_test(
        record, bot_runner_v10, playwright_page, now_anchor,
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
        f"{record.id}: bot={result.bot_payload} ui={result.expected_payload} "
        f"diffs={result.diffs}"
    )
