"""Unit tests for parse_number helper."""
import pytest

from testing.v10_harness.ui_validators.base import parse_number


def test_parse_plain_int():
    assert parse_number("1306") == 1306


def test_parse_with_commas():
    assert parse_number("1,306") == 1306


def test_parse_currency():
    assert parse_number("$12,345.67") == 12345.67


def test_parse_percent():
    assert parse_number("45.2%") == 45.2


def test_parse_dash():
    assert parse_number("—") == 0


def test_parse_em_dash():
    assert parse_number("–") == 0


def test_parse_empty_string():
    assert parse_number("   ") == 0


def test_parse_none_raises():
    with pytest.raises(ValueError):
        parse_number(None)  # type: ignore[arg-type]


def test_parse_leading_trailing_space():
    assert parse_number("  42  ") == 42
