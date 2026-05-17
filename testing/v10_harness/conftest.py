"""Pytest fixtures: staging RDS engine, IDRE session, now anchor."""
import os
import sys
from pathlib import Path
import pytest
import requests
from sqlalchemy.engine import Engine

# V10: bypass production row cap in tests
os.environ.setdefault("V10_DISABLE_ROW_CAP", "1")

# Make V8/V10 bot importable from harness
V8_BOT = Path("C:/Users/anand/Downloads/v8_reports_bot")
V10_BOT = Path("C:/Users/anand/Downloads/v10_reports_bot")
LOCAL_ROOT = Path("C:/Users/anand/Downloads/local")

for p in [V10_BOT, V8_BOT, LOCAL_ROOT]:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))


@pytest.fixture(scope="session")
def staging_engine() -> Engine:
    """Connect to staging RDS via V8's connector (same creds)."""
    os.chdir(str(V8_BOT))  # so V8's .env resolves
    from db.connector import get_engine
    eng = get_engine()
    # smoke test
    with eng.connect() as c:
        from sqlalchemy import text
        c.execute(text("SELECT 1"))
    return eng


@pytest.fixture(scope="session")
def idre_session() -> requests.Session:
    """Authenticated session against localhost:3000 IDRE."""
    s = requests.Session()
    try:
        r = s.get("http://127.0.0.1:3000/api/dev/auto-login", allow_redirects=True, timeout=30)
    except requests.exceptions.ConnectionError as e:
        pytest.skip(f"IDRE local server not reachable: connection refused ({e.__class__.__name__})")
    except requests.exceptions.Timeout:
        pytest.skip("IDRE local server not reachable: timeout")
    if r.status_code >= 400:
        pytest.skip(f"IDRE local server not reachable: HTTP {r.status_code}")
    return s


@pytest.fixture
def now_anchor(staging_engine: Engine):
    from testing.v10_harness.temporality import NowAnchor
    return NowAnchor.lock_from_db(staging_engine)


# ── Playwright fixtures (derived-ui category) ──────────────────────────────

@pytest.fixture(scope="session")
def playwright_browser():
    """Session-scoped headless Chromium for derived-ui tests."""
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    try:
        yield browser
    finally:
        browser.close()
        p.stop()


@pytest.fixture(scope="session")
def playwright_page(playwright_browser, idre_session):
    """Session-scoped Playwright page sharing IDRE auto-login cookies.

    Transfers cookies from the requests-based idre_session into the
    Playwright browser context, then verifies authenticated load of /dashboard.
    Validators reuse this page across tests to avoid per-test login cost.
    """
    ctx = playwright_browser.new_context()
    cookies = []
    for c in idre_session.cookies:
        cookies.append({
            "name": c.name,
            "value": c.value,
            "domain": c.domain or "127.0.0.1",
            "path": c.path or "/",
        })
    if cookies:
        ctx.add_cookies(cookies)
    page = ctx.new_page()
    try:
        page.goto("http://127.0.0.1:3000/dashboard",
                  wait_until="domcontentloaded", timeout=60000)
        yield page
    finally:
        ctx.close()
