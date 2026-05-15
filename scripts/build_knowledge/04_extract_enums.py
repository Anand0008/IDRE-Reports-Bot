"""Combine Prisma inline enums + TypeScript enum decls + RDS distinct-value sampling."""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
from common import IDRE_REPO, ensure_pending, write_json, git_sha

ENUM_TS_REGEX = re.compile(
    r"export\s+(?:const\s+|enum\s+)(\w+)\s*=?\s*\{([^}]*)\}\s*(?:as\s+const)?",
    re.DOTALL,
)


def scan_ts_enums() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    candidates = list(IDRE_REPO.rglob("*.ts"))
    for f in candidates:
        if "node_modules" in f.parts:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "enum " not in text and "as const" not in text:
            continue
        for name, body in ENUM_TS_REGEX.findall(text):
            values = re.findall(r"['\"]([A-Z_][A-Z0-9_]+)['\"]", body)
            values += re.findall(r"\b([A-Z_][A-Z0-9_]+)\s*[:=]", body)
            values = sorted(set(values))
            if values:
                found.setdefault(name, []).extend(values)
    return {k: sorted(set(v)) for k, v in found.items()}


def sample_rds_columns(engine) -> dict[str, list[str]]:
    """Sample distinct values for known enum-like columns from staging RDS."""
    from sqlalchemy import text
    cols = [
        ("case", "status"),
        ("payment", "type"),
        ("payment", "status"),
        ("payment", "direction"),
        ("case_payment_allocation", "partyType"),
    ]
    out: dict[str, list[str]] = {}
    with engine.connect() as conn:
        for table, col in cols:
            try:
                rows = conn.execute(
                    text(f"SELECT DISTINCT `{col}` AS v FROM `{table}` WHERE `{col}` IS NOT NULL")
                ).mappings().all()
                out[f"{table}.{col}"] = sorted(set(str(r["v"]) for r in rows))
            except Exception as e:
                out[f"{table}.{col}"] = []
                print(f"WARN: failed to sample {table}.{col}: {e}", file=sys.stderr)
    return out


def main() -> int:
    sys.path.insert(0, "C:/Users/anand/Downloads/v8_reports_bot")
    import os
    os.chdir("C:/Users/anand/Downloads/v8_reports_bot")
    from db.connector import get_engine
    eng = get_engine()

    ts_enums = scan_ts_enums()
    rds = sample_rds_columns(eng)
    out = ensure_pending() / "enum_catalog.json"
    write_json(out, {
        "idre_git_sha": git_sha(),
        "typescript_enums": ts_enums,
        "rds_sampled": rds,
    })
    print(f"Wrote {len(ts_enums)} TS enums + {len(rds)} RDS column samples -> {out}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.parse_args()
    sys.exit(main())
