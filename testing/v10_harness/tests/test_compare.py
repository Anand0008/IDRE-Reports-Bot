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
