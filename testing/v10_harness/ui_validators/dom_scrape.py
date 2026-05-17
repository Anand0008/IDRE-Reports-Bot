"""dom_scrape validator -- navigates IDRE URL, extracts count from rendered DOM.

Used for count-type tests where IDRE has a URL+filter combo that produces
the desired view. Extraction strategies: regex_capture on body text, or
selector_text via CSS selector. Returns {"<key>": <number>} where <key>
defaults to "count".
"""
from __future__ import annotations

import re
from typing import Any

from playwright.sync_api import Page

from . import REGISTRY
from .base import parse_number


DEFAULT_TIMEOUT_MS = 60000


class DomScrapeValidator:
    name = "dom_scrape"

    def extract(self, page: Page, params: dict) -> dict[str, Any]:
        """Navigate then extract. Used by the test runner."""
        url = params["url"]
        page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
        return self.extract_from_page(page, params)

    def extract_from_page(self, page: Page, params: dict) -> dict[str, Any]:
        """Extract on a page already loaded. Separable for unit testing."""
        # Wait for content to appear
        if "wait_for_regex" in params:
            page.wait_for_function(
                f"() => /{params['wait_for_regex']}/.test(document.body.innerText)",
                timeout=DEFAULT_TIMEOUT_MS,
            )
        elif "wait_for_selector" in params:
            page.wait_for_selector(params["wait_for_selector"], timeout=DEFAULT_TIMEOUT_MS)

        ext = params["extract"]
        key = ext.get("key", "count")

        # Check zero-pattern first (e.g., "No items")
        if "zero_on_pattern" in ext:
            body = page.evaluate("() => document.body.innerText")
            if re.search(ext["zero_on_pattern"], body):
                return {key: 0.0}

        if ext["kind"] == "regex_capture":
            body = page.evaluate("() => document.body.innerText")
            m = re.search(ext["pattern"], body)
            if not m:
                raise RuntimeError(
                    f"pattern not found in body for {key}: {ext['pattern']!r}; "
                    f"body head: {body[:300]!r}"
                )
            return {key: parse_number(m.group(1))}

        if ext["kind"] == "selector_text":
            txt = page.locator(ext["selector"]).inner_text(timeout=10000)
            return {key: parse_number(txt)}

        raise ValueError(f"unknown extract.kind: {ext['kind']!r}")


REGISTRY["dom_scrape"] = DomScrapeValidator
