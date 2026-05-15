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
        sys.path.insert(0, "C:/Users/anand/Downloads/v8_reports_bot")
        from harness_entrypoint import run as v8_run

        def runner(prompt: str, now):
            r = v8_run(prompt)
            # Wrap rows as IDRE-API-like shape for compare.py paths
            return {"data": {"rows": r.get("data", []), "totalCount": r.get("row_count", 0)}}
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
