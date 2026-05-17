"""dashboard_stats validator — reads /api/reports/dashboard-stats via Playwright.

Design note: this validator hits the API endpoint that IDRE's /dashboard page
itself calls. The dashboard renders these stats verbatim from the API response
(no UI-side computation), so the API value equals what a human user sees.
This avoids Next.js dev-mode networkidle flakiness while still using the
authenticated Playwright context (cookies match what a real browser would
send). If a future stat card adds UI-side calculation, switch this validator
to DOM scraping instead.

Supported params:
- `fields`: list of dot-paths into the response data, e.g.
  ["totalCases", "activeArbitrators"] → returns {totalCases: 36, activeArbitrators: 5}
  Each field reads `data[field].value` from the response payload.
"""
from __future__ import annotations

from typing import Any

from playwright.sync_api import Page

from . import REGISTRY
from .base import parse_number

ENDPOINT = "http://127.0.0.1:3000/api/reports/dashboard-stats"


class DashboardStatsValidator:
    name = "dashboard_stats"

    def extract(self, page: Page, params: dict) -> dict[str, Any]:
        fields = params["fields"]
        resp = page.request.get(ENDPOINT, timeout=30000)
        if not resp.ok:
            raise RuntimeError(
                f"dashboard-stats API returned HTTP {resp.status}: "
                f"{resp.text()[:300]}"
            )
        payload = resp.json()
        data = payload.get("data") or payload
        out: dict[str, Any] = {}
        for field in fields:
            if field not in data:
                raise KeyError(
                    f"field {field!r} not in dashboard-stats response; "
                    f"available: {sorted(data.keys())}"
                )
            entry = data[field]
            raw = entry["value"] if isinstance(entry, dict) and "value" in entry else entry
            out[field] = parse_number(str(raw))
        return out


REGISTRY["dashboard_stats"] = DashboardStatsValidator
