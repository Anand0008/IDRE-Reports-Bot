"""Unit tests for dom_scrape validator using static HTML fixtures."""
from playwright.sync_api import sync_playwright
import pytest


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context()
    p = ctx.new_page()
    yield p
    ctx.close()


def test_regex_capture_extracts_count(page):
    """Static HTML with 'Showing 1 to 1 of 5,123 items' -> count=5123."""
    page.set_content("""
        <html><body>
            <h1>Cases</h1>
            <div>Some chrome</div>
            <p class="pagination">Showing 1 to 1 of 5,123 items</p>
        </body></html>
    """)
    from testing.v10_harness.ui_validators.dom_scrape import DomScrapeValidator
    v = DomScrapeValidator()
    result = v.extract_from_page(page, {
        "wait_for_regex": r"Showing\s+\d+\s+to\s+\d+\s+of\s+[\d,]+\s+items",
        "extract": {
            "kind": "regex_capture",
            "pattern": r"Showing\s+\d+\s+to\s+\d+\s+of\s+([\d,]+)\s+items",
        },
    })
    assert result == {"count": 5123.0}


def test_regex_capture_no_match_raises(page):
    page.set_content("<html><body>nothing here</body></html>")
    from testing.v10_harness.ui_validators.dom_scrape import DomScrapeValidator
    v = DomScrapeValidator()
    with pytest.raises(RuntimeError, match="pattern not found"):
        v.extract_from_page(page, {
            "wait_for_regex": r"nothing",  # this matches; wait succeeds
            "extract": {
                "kind": "regex_capture",
                "pattern": r"Showing\s+([\d,]+)\s+items",
            },
        })


def test_selector_text_extracts_count(page):
    page.set_content("""
        <html><body>
            <div data-testid="total-cases">42</div>
        </body></html>
    """)
    from testing.v10_harness.ui_validators.dom_scrape import DomScrapeValidator
    v = DomScrapeValidator()
    result = v.extract_from_page(page, {
        "wait_for_selector": "[data-testid='total-cases']",
        "extract": {
            "kind": "selector_text",
            "selector": "[data-testid='total-cases']",
        },
    })
    assert result == {"count": 42.0}


def test_no_items_returns_zero(page):
    page.set_content("<html><body><p>No items</p></body></html>")
    from testing.v10_harness.ui_validators.dom_scrape import DomScrapeValidator
    v = DomScrapeValidator()
    result = v.extract_from_page(page, {
        "wait_for_regex": r"No items|Showing",
        "extract": {
            "kind": "regex_capture",
            "pattern": r"Showing\s+\d+\s+to\s+\d+\s+of\s+([\d,]+)\s+items",
            "zero_on_pattern": r"No items",
        },
    })
    assert result == {"count": 0.0}
