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
