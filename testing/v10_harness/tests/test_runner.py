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
