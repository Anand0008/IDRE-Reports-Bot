"""Replace Gemini-hallucinated sql_equivalent with V8's hand-written bot_sql_equivalent.

V8's report_reference_cards.json has hand-written, presumably-tested SQL for all 13
reports. Map them into V10's business_logic.json, overwriting Gemini's output.
"""
from __future__ import annotations
import json
from pathlib import Path

V8_CARDS = Path("C:/Users/anand/Downloads/v8_reports_bot/knowledge/data/report_reference_cards.json")
V10_BL = Path("C:/Users/anand/Downloads/v10_reports_bot/knowledge/v10_pending/business_logic.json")

# V8 id -> V10 (staging) id, where they differ
ID_MAP = {
    "daily-funds": "auditing/daily-funds",
    "daily-transactions": "auditing/daily-transactions",
}

v8 = json.loads(V8_CARDS.read_text())
v8_sql = {}
for r in v8["reports"]:
    v8_id = r["id"]
    v10_id = ID_MAP.get(v8_id, v8_id)
    sql = (r.get("bot_sql_equivalent") or "").strip()
    if sql:
        v8_sql[v10_id] = {
            "sql_equivalent": sql,
            "where_logic": r.get("where_logic", ""),
            "critical_detail": r.get("critical_detail", ""),
            "joins": r.get("joins", ""),
            "notes": f"Hand-written SQL from V8 reference cards. {r.get('critical_detail','')[:150]}",
        }

v10 = json.loads(V10_BL.read_text())
imported, missing = 0, []
for r in v10["reports"]:
    rid = r["id"]
    if rid in v8_sql:
        r["sql_equivalent"] = v8_sql[rid]["sql_equivalent"]
        r["notes"] = v8_sql[rid]["notes"]
        r["needs_review"] = False
        r["source"] = "v8_hand_written"
        imported += 1
    else:
        missing.append(rid)

V10_BL.write_text(json.dumps(v10, indent=2, default=str))
print(f"Imported V8 SQL for {imported} of {len(v10['reports'])} V10 reports")
print(f"No V8 SQL for: {missing}")
print(f"V8 reports not in V10: {set(v8_sql.keys()) - set(r['id'] for r in v10['reports'])}")
