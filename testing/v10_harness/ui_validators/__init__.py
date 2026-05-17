"""UI validators for derived-ui test category.

Each validator drives IDRE's UI via Playwright and extracts a scalar (or dict
of scalars) from the DOM. The harness compares the validator's extraction to
the V10 bot's SQL result.

Register validators here; the runner looks them up by name.
"""
from __future__ import annotations

REGISTRY: dict = {}


def get(name: str):
    """Look up a validator by name. Raises KeyError if not registered."""
    cls = REGISTRY[name]
    return cls()


# Import side-effects register each validator in REGISTRY
from . import dashboard_stats  # noqa: E402,F401
from . import case_status_filter  # noqa: E402,F401
from . import payment_lifecycle  # noqa: E402,F401
from . import due_dates_filter  # noqa: E402,F401
from . import dom_scrape  # noqa: E402,F401
from . import canonical_sql  # noqa: E402,F401
