"""UIValidator protocol + shared helpers."""
from __future__ import annotations

import re
from typing import Any, Protocol

from playwright.sync_api import Page

_STRIP_RE = re.compile(r"[,\s$%]")


def parse_number(text: str) -> float:
    """Strip commas, $, %, whitespace; parse to float. Dash/em-dash → 0."""
    if text is None:
        raise ValueError("parse_number received None")
    cleaned = _STRIP_RE.sub("", text.strip())
    if cleaned in ("", "—", "-", "–"):
        return 0.0
    return float(cleaned)


class UIValidator(Protocol):
    name: str

    def extract(self, page: Page, params: dict) -> dict[str, Any]:
        """Drive `page` per `params`, return dict of extracted values."""
        ...
