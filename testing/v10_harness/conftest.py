"""Pytest fixtures: staging RDS engine, IDRE session, now anchor."""
import os
import sys
from pathlib import Path
import pytest
import requests
from sqlalchemy.engine import Engine

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
        r = s.get("http://localhost:3000/api/dev/auto-login", allow_redirects=True, timeout=30)
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
