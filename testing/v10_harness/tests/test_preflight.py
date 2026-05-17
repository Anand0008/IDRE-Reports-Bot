"""Unit tests for preflight checks (live -- requires environment up)."""
import pytest


def test_preflight_runs_all():
    from testing.v10_harness.preflight import run_all, CHECKS
    overall, results = run_all()
    # All checks return a (bool, str)
    assert len(results) == len(CHECKS)
    for name, ok, msg in results:
        assert isinstance(name, str)
        assert isinstance(ok, bool)
        assert isinstance(msg, str)
        assert msg  # non-empty

# Note: we don't assert overall=True because IDRE may not be in prod mode
# during dev/CI. The fixture in conftest will skip the derived-dom suite
# if any check fails, with the report printed.
