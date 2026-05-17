"""Unit tests for canonical_sql validator. Hits local docker idre DB."""
import pytest


def test_canonical_sql_count_query():
    from testing.v10_harness.ui_validators.canonical_sql import CanonicalSqlValidator
    v = CanonicalSqlValidator()
    result = v.extract(None, {
        "sql": "SELECT 42 AS n",
        "scalar_key": "n",
    })
    assert result == {"count": 42.0}


def test_canonical_sql_custom_result_key():
    from testing.v10_harness.ui_validators.canonical_sql import CanonicalSqlValidator
    v = CanonicalSqlValidator()
    result = v.extract(None, {
        "sql": "SELECT 1234 AS total_payments",
        "scalar_key": "total_payments",
        "result_key": "totalPayments",
    })
    assert result == {"totalPayments": 1234.0}


def test_canonical_sql_requires_source_ref():
    """Defense: validator should reject entries without source_ref to keep
    canonical SQL authoring honest."""
    from testing.v10_harness.ui_validators.canonical_sql import CanonicalSqlValidator
    v = CanonicalSqlValidator()
    with pytest.raises(ValueError, match="source_ref"):
        v.extract(None, {
            "sql": "SELECT 1",
            "scalar_key": "n",
            "_skip_source_ref_check": False,
        })


def test_canonical_sql_against_real_db():
    """Sanity: actual local docker query returns a number."""
    from testing.v10_harness.ui_validators.canonical_sql import CanonicalSqlValidator
    v = CanonicalSqlValidator()
    result = v.extract(None, {
        "sql": "SELECT COUNT(*) AS n FROM `case`",
        "scalar_key": "n",
        "source_ref": "test sanity; no UI source needed",
    })
    assert result["count"] > 0  # snapshot has 67K+ cases
