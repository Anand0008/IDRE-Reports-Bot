"""Locks a single :now timestamp for the duration of one test."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.engine import Engine
from sqlalchemy import text


@dataclass(frozen=True)
class NowAnchor:
    _now: datetime

    @classmethod
    def lock_from_value(cls, value: datetime) -> "NowAnchor":
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return cls(_now=value)

    @classmethod
    def lock_from_db(cls, engine: Engine) -> "NowAnchor":
        with engine.connect() as conn:
            row = conn.execute(text("SELECT UTC_TIMESTAMP() AS n")).mappings().one()
        n = row["n"]
        if n.tzinfo is None:
            n = n.replace(tzinfo=timezone.utc)
        return cls(_now=n)

    def now(self) -> datetime:
        return self._now

    def bind_sql(self, sql: str) -> dict[str, Any]:
        """Convert :now markers into mysql-connector named params."""
        if ":now" not in sql:
            return {"sql": sql, "params": {}}
        bound_sql = sql.replace(":now", "%(now)s")
        return {"sql": bound_sql, "params": {"now": self._now}}
