import sys
from datetime import datetime, timezone
sys.path.insert(0, "C:/Users/anand/Downloads/v10_reports_bot")
from agents.parameter_extractor import resolve_date_phrase, extract_search_term


def test_resolve_date_today():
    now = datetime(2026, 5, 15, 14, 0, 0, tzinfo=timezone.utc)
    d = resolve_date_phrase("today", now)
    assert d["startDate"].startswith("2026-05-15")
    assert d["endDate"].startswith("2026-05-16")


def test_resolve_date_mtd():
    now = datetime(2026, 5, 15, 14, 0, 0, tzinfo=timezone.utc)
    d = resolve_date_phrase("month-to-date", now)
    assert d["startDate"].startswith("2026-05-01")


def test_resolve_date_last_7_days():
    now = datetime(2026, 5, 15, 14, 0, 0, tzinfo=timezone.utc)
    d = resolve_date_phrase("last 7 days", now)
    assert d["startDate"].startswith("2026-05-08")


def test_extract_search_term_capitol_bridge():
    assert extract_search_term("show payouts to Capitol Bridge").lower() == "capitol bridge"


def test_extract_search_term_none():
    assert extract_search_term("show all cases") is None
