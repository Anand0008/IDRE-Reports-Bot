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

# Hand-curated aliases for tables Gemini hallucinated (not Prisma model names).
# These are NOT in schema_catalog as models — they're guesses Gemini made
# from English nouns or incomplete schema knowledge.
HAND_ALIASES = {
    "party": "case_party",
    "Party": "case_party",
    "dispute_line_item": "dispute_line_items",   # actual table is plural
    "DisputeLineItem": "dispute_line_items",
    "PaymentAllocation": "case_payment_allocation",
    "CaseAllocation": "case_payment_allocation",
    # installment: feature doesn't exist on staging — Gemini hallucinated it.
    # Leaving unmapped so validation fails loudly for due-dates/summary.
}
for k, v in HAND_ALIASES.items():
    mapping[k] = v

print(f"Building mapping for {len(mapping)} model->table renames ({len(HAND_ALIASES)} hand aliases)")
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
        # Bare (non-backticked) identifier — only rewrite in table position
        # (after FROM/JOIN/UPDATE/INTO), with a word boundary, to avoid
        # rewriting column names that happen to match a model name.
        new_sql = re.sub(
            rf"(\b(?:FROM|JOIN|UPDATE|INTO)\s+){re.escape(model)}\b",
            rf"\1`{table}`",
            new_sql,
            flags=re.IGNORECASE,
        )
    if new_sql != sql:
        changes += 1
        r["sql_equivalent"] = new_sql
        print(f"  fixed: {r['id']}")

bl_path.write_text(json.dumps(bl, indent=2, default=str))
print(f"\n{changes} reports updated; wrote {bl_path}")
