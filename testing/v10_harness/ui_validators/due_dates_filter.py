"""due_dates_filter validator — counts cases by urgency bucket.

Hits /api/reports/due-dates/summary which IDRE's /dashboard/eligibility view
itself calls. Response shape:
    {success, data: {summary: {
        totalCases, overdueCases, urgentCases, warningCases, normalCases
    }}}

Same pattern as dashboard_stats: API value equals what the UI displays,
authenticated via Playwright context.

Accepted `urgency` params:
- "overdue"      → summary.overdueCases
- "urgent"       → summary.urgentCases
- "warning"      → summary.warningCases
- "normal"       → summary.normalCases
- "approaching"  → summary.urgentCases   (alias for plan-spec naming;
                    IDRE has no bucket called "approaching" — `urgent` is
                    the closest semantic match: due soon, not yet overdue)
- "all"          → summary.totalCases

Returns: {"count": int}
"""
from __future__ import annotations

from typing import Any

from playwright.sync_api import Page

from . import REGISTRY

ENDPOINT = "http://127.0.0.1:3000/api/reports/due-dates/summary"

_URGENCY_TO_FIELD: dict[str, str] = {
    "overdue": "overdueCases",
    "urgent": "urgentCases",
    "warning": "warningCases",
    "normal": "normalCases",
    "approaching": "urgentCases",  # plan-spec alias
    "all": "totalCases",
}


class DueDatesFilterValidator:
    name = "due_dates_filter"

    def extract(self, page: Page, params: dict) -> dict[str, Any]:
        urgency = params.get("urgency", "all")
        if urgency not in _URGENCY_TO_FIELD:
            raise ValueError(
                f"unknown urgency {urgency!r}; expected one of "
                f"{sorted(_URGENCY_TO_FIELD)}"
            )
        field = _URGENCY_TO_FIELD[urgency]

        # Call the summary endpoint unfiltered — it always returns counts for
        # ALL buckets, then we pick the one we want. This avoids re-hitting
        # the endpoint per urgency in higher-level test sweeps.
        resp = page.request.get(ENDPOINT, timeout=30000)
        if not resp.ok:
            raise RuntimeError(
                f"due-dates/summary returned HTTP {resp.status}: "
                f"{resp.text()[:300]}"
            )
        payload = resp.json()
        data = payload.get("data") or payload
        summary = data.get("summary") or data
        if field not in summary:
            raise KeyError(
                f"field {field!r} not in due-dates summary; "
                f"available: {sorted(summary.keys())}"
            )
        return {"count": int(summary[field])}


REGISTRY["due_dates_filter"] = DueDatesFilterValidator
