"""Smoke test: playwright_page fixture lands at /dashboard authenticated.

Verifies the IDRE→requests→Playwright cookie transfer chain end-to-end.
Skips if IDRE local isn't reachable (same as idre_session fixture).
"""


def test_playwright_lands_at_dashboard(playwright_page):
    url = playwright_page.url
    assert "/dashboard" in url, f"expected /dashboard, got {url}"
    assert "/login" not in url, f"got bounced to login: {url}"


def test_playwright_session_cookie_present(playwright_page):
    cookies = playwright_page.context.cookies()
    names = {c["name"] for c in cookies}
    assert any("session_token" in n or "better-auth" in n for n in names), \
        f"no session cookie found, names={names}"
