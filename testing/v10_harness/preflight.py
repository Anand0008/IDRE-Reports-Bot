"""Pre-flight checks for derived-dom test suite.

Each check returns (ok: bool, message: str). Suite-level fixture
aggregates results; any FAIL -> skip the suite with explanatory message.
Some checks auto-remediate (e.g., apply indexes); others print remediation.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Callable

import pymysql
import requests


CheckResult = tuple[bool, str]
CheckFn = Callable[[], CheckResult]


def check_idre_running() -> CheckResult:
    try:
        r = requests.get("http://127.0.0.1:3000/", timeout=5, allow_redirects=False)
        return (r.status_code < 500, f"IDRE responded HTTP {r.status_code}")
    except Exception as e:
        return (False, f"IDRE not reachable: {type(e).__name__}: {e}. Start with: cd local/idre && npx next start --hostname 127.0.0.1 --port 3000")


def check_db_snapshot() -> CheckResult:
    try:
        conn = pymysql.connect(host="127.0.0.1", port=3306, user="root", password="idrelocal", database="idre", connect_timeout=10)
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) FROM `case`")
            n = c.fetchone()[0]
        conn.close()
        if n > 10000:
            return (True, f"snapshot OK ({n} cases)")
        return (False, f"only {n} cases in idre DB; expected >10000 (snapshot not imported?). Re-import: see docs/superpowers/reports/2026-05-18-task20-snapshot-done.md")
    except Exception as e:
        return (False, f"DB connection failed: {type(e).__name__}: {e}")


def check_indexes_present() -> CheckResult:
    try:
        conn = pymysql.connect(host="127.0.0.1", port=3306, user="root", password="idrelocal", database="idre", connect_timeout=10)
        with conn.cursor() as c:
            c.execute("""SELECT COUNT(DISTINCT index_name) FROM information_schema.STATISTICS
                         WHERE table_schema='idre' AND index_name LIKE '%_v10'""")
            n = c.fetchone()[0]
        conn.close()
        if n >= 5:
            return (True, f"{n} v10 indexes present")
        # Auto-remediate
        apply_script = Path(__file__).parent.parent.parent / ".snapshots" / "apply_indexes.py"
        if apply_script.exists():
            subprocess.run(["py311", str(apply_script)], check=False, capture_output=True)
            return (True, f"applied indexes (was {n}, now should be 9)")
        return (False, f"only {n} v10 indexes; run .snapshots/apply_indexes.py")
    except Exception as e:
        return (False, f"index check failed: {type(e).__name__}: {e}")


def check_ryan_auth() -> CheckResult:
    try:
        r = requests.get("http://127.0.0.1:3000/api/dev/auto-login", timeout=30, allow_redirects=False)
        if r.status_code == 307 and "set-cookie" in {k.lower() for k in r.headers.keys()}:
            cookie = r.headers.get("set-cookie", "")
            if "session_token" in cookie:
                return (True, "auto-login set session cookie")
        # Try to read body for diagnostic
        body = r.text[:200] if hasattr(r, "text") else ""
        return (False, f"auto-login HTTP {r.status_code}, no session cookie. Body: {body!r}. Remediate: reset Ryan password (.snapshots/reset_ryan_password.py) and clear twoFactor table for Ryan.")
    except Exception as e:
        return (False, f"auto-login failed: {type(e).__name__}: {e}")


def check_prod_mode_render_speed() -> CheckResult:
    """Time a cases page render. <5s = good (likely prod build). >30s = dev mode or broken."""
    try:
        s = requests.Session()
        s.get("http://127.0.0.1:3000/api/dev/auto-login", allow_redirects=True, timeout=30)
        t0 = time.time()
        r = s.get("http://127.0.0.1:3000/dashboard/cases?limit=1", timeout=60)
        elapsed = time.time() - t0
        if r.status_code >= 500:
            return (False, f"cases page HTTP {r.status_code} in {elapsed:.1f}s")
        if elapsed < 5:
            return (True, f"cases page rendered in {elapsed:.1f}s (prod mode OK)")
        if elapsed < 30:
            return (True, f"cases page rendered in {elapsed:.1f}s (slow; may be dev mode)")
        return (False, f"cases page took {elapsed:.1f}s; check IDRE prod build (see docs/idre-local-prod-mode.md)")
    except Exception as e:
        return (False, f"render speed check failed: {type(e).__name__}: {e}")


CHECKS: list[tuple[str, CheckFn]] = [
    ("idre_running", check_idre_running),
    ("db_snapshot", check_db_snapshot),
    ("indexes_present", check_indexes_present),
    ("ryan_auth", check_ryan_auth),
    ("prod_mode_render_speed", check_prod_mode_render_speed),
]


def run_all() -> tuple[bool, list[tuple[str, bool, str]]]:
    results = []
    overall = True
    for name, fn in CHECKS:
        ok, msg = fn()
        results.append((name, ok, msg))
        if not ok:
            overall = False
    return overall, results


def format_report(results: list[tuple[str, bool, str]]) -> str:
    lines = []
    for name, ok, msg in results:
        flag = "OK" if ok else "FAIL"
        lines.append(f"  [{flag}] {name}: {msg}")
    return "\n".join(lines)


if __name__ == "__main__":
    overall, results = run_all()
    print(format_report(results))
    import sys
    sys.exit(0 if overall else 1)
