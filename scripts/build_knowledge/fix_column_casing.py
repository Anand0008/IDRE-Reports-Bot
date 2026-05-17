"""Replace snake_case column refs with the actual camelCase column name from schema.

Prisma stores columns with the same case as the Prisma model defines them (camelCase
by convention), but Gemini's translation often emits snake_case. This rewrites references
of the form `<alias>.<snake>` or bare `<snake>` in `<col list>, <where clauses>, ...` to
the actual camelCase column name when there's a unique camelCase mapping in the schema.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

PENDING = Path("C:/Users/anand/Downloads/v10_reports_bot/knowledge/v10_pending")


def snake_of(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


schema = json.loads((PENDING / "schema_catalog.json").read_text())

# Build snake -> set-of-camel mapping (across all models)
snake_to_camel: dict[str, set[str]] = {}
for m in schema.get("models", []):
    for c in m.get("columns", []):
        cn = c.get("name", "")
        if not cn:
            continue
        s = snake_of(cn)
        if s == cn:
            continue  # already snake_case in source, no rewrite needed
        snake_to_camel.setdefault(s, set()).add(cn)

# Hand additions for common patterns that don't appear in the schema parse
# (e.g., columns Gemini invents that map to known camelCase forms)
EXTRA = {
    "closed_at": "statusChangedAt",  # IDRE doesn't have closedAt; uses statusChangedAt
}
for s, c in EXTRA.items():
    snake_to_camel.setdefault(s, set()).add(c)

# Only rewrite when the mapping is unambiguous (1 camelCase target)
unambiguous = {s: list(cs)[0] for s, cs in snake_to_camel.items() if len(cs) == 1}
ambiguous = {s: list(cs) for s, cs in snake_to_camel.items() if len(cs) > 1}

print(f"unambiguous mappings: {len(unambiguous)}")
print(f"ambiguous (skipped): {len(ambiguous)}")
for s, opts in list(ambiguous.items())[:5]:
    print(f"  ambig: {s} -> {opts}")

bl_path = PENDING / "business_logic.json"
bl = json.loads(bl_path.read_text())

changes = 0
total_rewrites = 0
for r in bl["reports"]:
    sql = r.get("sql_equivalent", "")
    if not sql:
        continue
    new_sql = sql
    report_rewrites = 0
    for snake, camel in unambiguous.items():
        # alias.snake -> alias.camel  (alias is any word: \w+)
        before = new_sql
        new_sql = re.sub(rf"(\w+)\.{re.escape(snake)}\b", rf"\1.{camel}", new_sql)
        # bare snake_case in SELECT/ORDER BY positions (riskier — limit to columns surrounded by
        # word boundaries and NOT preceded by `.` or alphanumeric)
        new_sql = re.sub(rf"(?<![\w.])\b{re.escape(snake)}\b(?!\s*\()", camel, new_sql)
        if new_sql != before:
            report_rewrites += 1
    if new_sql != sql:
        changes += 1
        total_rewrites += report_rewrites
        r["sql_equivalent"] = new_sql
        print(f"  fixed {r['id']} ({report_rewrites} column patterns)")

bl_path.write_text(json.dumps(bl, indent=2, default=str))
print(f"\n{changes} reports updated, {total_rewrites} total column rewrites")
