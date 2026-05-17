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
