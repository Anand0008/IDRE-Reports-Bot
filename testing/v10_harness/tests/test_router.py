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
