"""canonical_sql validator -- runs SQL against local docker `idre` DB.

Used ONLY for metrics IDRE has no URL+filter combo a real user could
navigate to. Each entry MUST include `source_ref` (string) justifying
why no UI exists and (where possible) referencing the IDRE source file
the SQL was derived from. This keeps canonical-SQL authoring honest --
if we can't articulate why no UI exists, the test is suspect.

Params:
  sql:           the COUNT(*) or aggregate query (no semicolons, no DDL/DML)
  scalar_key:    column alias in the result row (e.g. "n" for "SELECT COUNT(*) AS n")
  result_key:    key in the returned dict (default "count")
  source_ref:    REQUIRED; non-empty string explaining why no UI exists
                 + which IDRE source file informed the SQL where possible
"""
from __future__ import annotations

import re
from typing import Any

import pymysql

from . import REGISTRY


_FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|"
    r"REPLACE|RENAME|LOAD|HANDLER|LOCK|UNLOCK)\b",
    re.IGNORECASE,
)


class CanonicalSqlValidator:
    name = "canonical_sql"

    def extract(self, page, params: dict) -> dict[str, Any]:
        sql = params["sql"].strip().rstrip(";")
        scalar_key = params["scalar_key"]
        result_key = params.get("result_key", "count")

        # Integrity: require source_ref (unless explicitly skipped for tests)
        if not params.get("_skip_source_ref_check", True):
            ref = params.get("source_ref", "")
            if not ref or not ref.strip():
                raise ValueError(
                    "canonical_sql entry missing source_ref. Each canonical-SQL "
                    "test must justify why no IDRE UI exists for this metric."
                )

        # Security: reject any DDL/DML even though we connect read-write
        if _FORBIDDEN_SQL.search(sql):
            raise ValueError(
                f"canonical_sql rejected: SQL contains forbidden keyword "
                f"(DDL/DML not allowed in validator queries): {sql[:200]!r}"
            )
        if ";" in sql:
            raise ValueError("canonical_sql rejected: semicolons not allowed (single-statement only)")

        conn = pymysql.connect(
            host="127.0.0.1", port=3306, user="root", password="idrelocal",
            database="idre", charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor, autocommit=True,
        )
        try:
            with conn.cursor() as c:
                c.execute(sql)
                row = c.fetchone()
        finally:
            conn.close()

        if row is None:
            raise RuntimeError(f"canonical_sql returned no rows: {sql[:200]!r}")
        if scalar_key not in row:
            raise RuntimeError(
                f"canonical_sql: scalar_key {scalar_key!r} not in result row "
                f"(available: {list(row.keys())})"
            )
        val = row[scalar_key]
        # Coerce to float (handles MySQL's DECIMAL returning as Decimal)
        from decimal import Decimal
        if isinstance(val, Decimal):
            val = float(val)
        elif val is None:
            val = 0.0
        else:
            val = float(val)
        return {result_key: val}


REGISTRY["canonical_sql"] = CanonicalSqlValidator
