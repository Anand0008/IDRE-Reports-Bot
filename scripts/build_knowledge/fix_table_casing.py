"""Replace `PrismaModelName` with `actual_mysql_table_name` in business_logic.json."""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

PENDING = Path("C:/Users/anand/Downloads/v10_reports_bot/knowledge/v10_pending")

schema = json.loads((PENDING / "schema_catalog.json").read_text())
# Build mapping: model name (PascalCase) -> table_name (actual MySQL name)
mapping = {}
for m in schema.get("models", []):
    model = m.get("model")
    table = m.get("table_name")
    if model and table and model != table:
        mapping[model] = table

print(f"Building mapping for {len(mapping)} model->table renames")
for k, v in sorted(mapping.items())[:5]:
    print(f"  `{k}` -> `{v}`")
if len(mapping) > 5:
    print(f"  ... and {len(mapping)-5} more")

bl_path = PENDING / "business_logic.json"
bl = json.loads(bl_path.read_text())

changes = 0
for r in bl["reports"]:
    sql = r.get("sql_equivalent", "")
    if not sql:
        continue
    new_sql = sql
    for model, table in mapping.items():
        # Replace backticked PascalCase model with backticked table_name
        new_sql = re.sub(rf"`{re.escape(model)}`", f"`{table}`", new_sql)
        # Also replace unbacked: word boundaries around bare model name (used as table ref)
        # only when followed by whitespace, dot, or end (so we don't rewrite column names that happen to match)
        # Skip this — too risky. Stick to backticked.
    if new_sql != sql:
        changes += 1
        r["sql_equivalent"] = new_sql
        print(f"  fixed: {r['id']}")

bl_path.write_text(json.dumps(bl, indent=2, default=str))
print(f"\n{changes} reports updated; wrote {bl_path}")
