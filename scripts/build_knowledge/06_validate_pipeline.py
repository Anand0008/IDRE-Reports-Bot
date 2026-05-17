"""Validate pending knowledge artifacts: required files present, SQL is parseable,
and (optionally) sql_equivalent executes without error against staging RDS.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
from common import PENDING_DIR, write_json, git_sha, utc_iso, file_sha256

REQUIRED = [
    "report_reference_cards.json",
    "schema_catalog.json",
    "enum_catalog.json",
    "business_logic.json",
]


def main(execute_sql: bool) -> int:
    summary = {"checks": [], "ok": True}

    # Check 1: all required files exist
    for fname in REQUIRED:
        f = PENDING_DIR / fname
        if not f.exists():
            summary["checks"].append({"name": f"file_exists:{fname}", "ok": False})
            summary["ok"] = False
        else:
            summary["checks"].append({"name": f"file_exists:{fname}", "ok": True, "sha": file_sha256(f)})

    # Check 2: business_logic.json well-formed
    bl_path = PENDING_DIR / "business_logic.json"
    if bl_path.exists():
        bl = json.loads(bl_path.read_text())
        for r in bl["reports"]:
            ok = bool(r.get("sql_equivalent")) and not r.get("needs_review", False)
            summary["checks"].append({
                "name": f"sql_present:{r['id']}",
                "ok": ok,
            })
            if not ok:
                summary["ok"] = False

    # Check 3 (optional): execute every sql_equivalent
    if execute_sql:
        sys.path.insert(0, "C:/Users/anand/Downloads/v8_reports_bot")
        import os
        os.chdir("C:/Users/anand/Downloads/v8_reports_bot")
        from db.connector import get_engine
        from sqlalchemy import text
        eng = get_engine()
        bl = json.loads((PENDING_DIR / "business_logic.json").read_text())
        with eng.connect() as conn:
            for r in bl["reports"]:
                sql = r.get("sql_equivalent", "")
                if not sql:
                    continue
                # Strip block comments, trailing line comments, then trailing semicolons/whitespace
                # so the wrapper SELECT * FROM (<sql>) AS _v LIMIT 1 doesn't break on /* */ or -- or ;
                cleaned = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
                cleaned = re.sub(r"--[^\n]*", "", cleaned)
                cleaned = cleaned.strip().rstrip(";").strip()
                if not cleaned:
                    summary["checks"].append({"name": f"sql_executes:{r['id']}", "ok": False, "err": "empty after strip"})
                    summary["ok"] = False
                    continue
                try:
                    # Wrap in LIMIT-bounded subquery to keep validation fast
                    conn.execute(text(f"SELECT * FROM ({cleaned}) AS _v LIMIT 1"))
                    summary["checks"].append({"name": f"sql_executes:{r['id']}", "ok": True})
                except Exception as e:
                    summary["checks"].append({"name": f"sql_executes:{r['id']}", "ok": False, "err": str(e)[:300]})
                    summary["ok"] = False

    # Write manifest
    manifest = {
        "idre_git_sha": git_sha(),
        "generated_at": utc_iso(),
        "files": {f: file_sha256(PENDING_DIR / f) for f in REQUIRED if (PENDING_DIR / f).exists()},
        "validation": summary,
    }
    write_json(PENDING_DIR / "manifest.json", manifest)
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--execute-sql", action="store_true",
                   help="Also execute each sql_equivalent against staging (slower)")
    args = p.parse_args()
    sys.exit(main(args.execute_sql))
