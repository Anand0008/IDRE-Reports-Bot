"""Narrated headed-mode demo of the derived-ui validation flow.

Runs 3 validators end-to-end so you can WATCH Chromium navigate IDRE,
extract numbers, and prove they match a manual SQL probe of local docker.
Forces window to a visible position + bumps slow_mo to 1500ms per action.

Run:
  py311 testing/v10_harness/watch_demo.py
"""
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


def banner(msg: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {msg}")
    print("=" * 72)


def pause(secs: float, label: str = "watching") -> None:
    print(f"  [pause {secs}s -- {label}]")
    time.sleep(secs)


def main() -> None:
    banner("1) AUTHENTICATING via /api/dev/auto-login (background, no browser)")
    s = requests.Session()
    s.get("http://127.0.0.1:3000/api/dev/auto-login", allow_redirects=True, timeout=30)
    print(f"  cookies acquired: {[c.name for c in s.cookies]}")

    banner("2) LAUNCHING headed Chromium -- window forced visible at top-left")
    from playwright.sync_api import sync_playwright

    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=False,
        slow_mo=1500,  # 1.5 sec per action so you can FOLLOW each step
        args=[
            "--window-position=20,20",
            "--window-size=1400,900",
            "--disable-blink-features=AutomationControlled",  # less aggressive about hiding
        ],
    )
    ctx = browser.new_context(viewport={"width": 1380, "height": 850})
    for c in s.cookies:
        ctx.add_cookies([{
            "name": c.name, "value": c.value,
            "domain": c.domain or "127.0.0.1",
            "path": c.path or "/",
        }])
    page = ctx.new_page()
    print("  [OK] browser open. Look for a Chromium window in the top-left of your screen.")
    pause(3, "spot the browser window")

    banner("3) NAVIGATING to /dashboard -- verifies login worked")
    page.goto("http://127.0.0.1:3000/dashboard", wait_until="domcontentloaded", timeout=60000)
    print(f"  [OK] on {page.url}")
    pause(3, "see the IDRE dashboard render")

    # -- Validator demo 1: case_status_filter (PENDING_RFI) -----------------
    banner("4) DEMO 1: case_status_filter -- count PENDING_RFI cases")
    from testing.v10_harness.ui_validators import get as get_validator
    v = get_validator("case_status_filter")
    print("  Bot's SQL would be:")
    print("    SELECT COUNT(*) FROM `case` WHERE status = 'PENDING_RFI'")
    print("  Validator navigates: /dashboard/cases?status=PENDING_RFI&limit=500")
    print("  then reads pagination footer to extract count")
    pause(2, "browser navigates now")
    result = v.extract(page, {"status": "PENDING_RFI"})
    print(f"  [OK] Validator extracted: {result}")
    pause(4, "see the filtered cases list + the 'Showing N items' footer")

    # -- Validator demo 2: dashboard_stats ---------------------------------
    banner("5) DEMO 2: dashboard_stats -- totalCases via API")
    print("  This validator uses page.request.get() -- Playwright's authenticated")
    print("  HTTP client. No DOM scraping; same cookies as the browser.")
    v = get_validator("dashboard_stats")
    result = v.extract(page, {"fields": ["totalCases", "activeArbitrators", "avgProcessingTime"]})
    print(f"  [OK] {result}")
    pause(3, "API-style validator runs without visible navigation")

    # -- Validator demo 3: due_dates_filter --------------------------------
    banner("6) DEMO 3: due_dates_filter -- overdue count")
    v = get_validator("due_dates_filter")
    result = v.extract(page, {"urgency": "overdue"})
    print(f"  [OK] {result}")
    pause(3, "due-dates summary API extracted")

    # -- Manual cross-check against local docker MySQL ---------------------
    banner("7) CROSS-CHECK: run the same query directly against the DB")
    import pymysql
    conn = pymysql.connect(
        host="127.0.0.1", port=3306, user="root", password="idrelocal",
        database="idre", charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    with conn.cursor() as c:
        c.execute("SELECT COUNT(*) AS n FROM `case` WHERE status='PENDING_RFI'")
        print(f"  Direct SQL: SELECT COUNT(*) FROM case WHERE status='PENDING_RFI' -> {c.fetchone()}")
        c.execute("SELECT COUNT(*) AS n FROM `case`")
        print(f"  Direct SQL: SELECT COUNT(*) FROM case -> {c.fetchone()}")
        c.execute("SELECT COUNT(*) AS n FROM user WHERE role IN ('arbitrator','arbitrator-contractor')")
        print(f"  Direct SQL: SELECT COUNT(*) FROM user WHERE role IN ('arbitrator','arbitrator-contractor') -> {c.fetchone()}")
    conn.close()

    banner("8) DONE -- browser stays open 15 sec so you can interact / inspect")
    pause(15, "feel free to click around the browser window before it closes")

    browser.close()
    p.stop()
    print("\n[OK] demo complete")


if __name__ == "__main__":
    main()
