"""Per-report: read route.ts + lib dep; ask Gemini to extract Prisma + JS + SQL triple.

Cost note: makes one Gemini 2.5 Pro call per discovered report (~18 calls × 30-60s).
Run via the orchestrator or call directly with --only <report_id> for one-off conversion.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import google.generativeai as genai
from common import IDRE_REPO, ensure_pending, write_json, git_sha


SYSTEM_PROMPT = """You are converting an IDRE platform report from TypeScript+Prisma source code into an equivalent raw MySQL query.

You will receive the contents of:
  (a) app/api/reports/<name>/route.ts — the Next.js route handler
  (b) (optional) lib/reports/<name>.ts — supporting library code

Output a JSON object with these keys:
  - "prisma_query": the Prisma call(s) the route makes (verbatim, as a single TypeScript string)
  - "js_postprocessing": any JS that runs AFTER the Prisma call (filter, map, reduce, .some(), .every(), aggregations). Empty string if none.
  - "sql_equivalent": a MySQL SELECT that produces the same final result as the route after JS post-processing. Use backticks for `case` (reserved word). Inline the JS logic as SQL subqueries (NOT EXISTS, CASE WHEN, etc.) where applicable.
  - "result_shape": the JSON shape the route returns (top-level keys)
  - "notes": one-sentence rationale; flag any logic you couldn't translate.

Output ONLY the JSON object. No markdown, no commentary."""


def read_with_deps(report: dict) -> str:
    parts = []
    route = IDRE_REPO / report["route_file"]
    parts.append(f"// FILE: {report['route_file']}\n" + route.read_text(encoding="utf-8"))
    if report.get("lib_file"):
        lib = IDRE_REPO / report["lib_file"]
        if lib.exists():
            parts.append(f"\n// FILE: {report['lib_file']}\n" + lib.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def call_gemini(source: str, api_key: str) -> dict:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        "gemini-2.5-pro-preview",
        system_instruction=SYSTEM_PROMPT,
    )
    resp = model.generate_content(source, generation_config={"temperature": 0.1, "max_output_tokens": 8000})
    text = resp.text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def main(only: str | None) -> int:
    sys.path.insert(0, "C:/Users/anand/Downloads/v8_reports_bot")
    import os
    os.chdir("C:/Users/anand/Downloads/v8_reports_bot")
    from config.settings import get_settings
    api_key = get_settings().gemini_api_key
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set in v8/.env", file=sys.stderr)
        return 1

    pending = ensure_pending()
    cards_path = pending / "report_reference_cards.json"
    if not cards_path.exists():
        print(f"ERROR: run 02_extract_reference_cards.py first", file=sys.stderr)
        return 1
    cards_doc = json.loads(cards_path.read_text())
    cards = cards_doc["reports"]
    if only:
        cards = [c for c in cards if c["id"] == only]
        if not cards:
            print(f"ERROR: no card with id={only}", file=sys.stderr)
            return 1

    # Resume support: skip already-converted cards if business_logic.json exists
    existing: dict = {}
    out_path = pending / "business_logic.json"
    if out_path.exists() and not only:
        existing_doc = json.loads(out_path.read_text())
        existing = {r["id"]: r for r in existing_doc.get("reports", [])}

    business_logic = list(existing.values())
    for c in cards:
        if c["id"] in existing and not existing[c["id"]].get("needs_review"):
            print(f"SKIP {c['id']} (already converted, no needs_review flag)")
            continue
        print(f"Converting {c['id']}...", flush=True)
        try:
            source = read_with_deps(c)
        except OSError as e:
            print(f"  SKIP: {e}", file=sys.stderr)
            continue
        try:
            triple = call_gemini(source, api_key)
        except Exception as e:
            print(f"  FAIL: {e}", file=sys.stderr)
            business_logic.append({"id": c["id"], "needs_review": True, "error": str(e)})
            continue
        triple["id"] = c["id"]
        triple["route_file"] = c["route_file"]
        triple["needs_review"] = False
        # replace existing entry if present
        business_logic = [b for b in business_logic if b.get("id") != c["id"]]
        business_logic.append(triple)
        # persist progressively in case of mid-run failure
        write_json(out_path, {"idre_git_sha": git_sha(), "reports": business_logic})

    write_json(out_path, {"idre_git_sha": git_sha(), "reports": business_logic})
    print(f"Wrote {len(business_logic)} business-logic entries -> {out_path}")
    needs_review = [b for b in business_logic if b.get("needs_review")]
    if needs_review:
        print(f"WARNING: {len(needs_review)} entries need human review:")
        for b in needs_review:
            print(f"  - {b['id']}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--only", help="Convert just this report id (for one-off retries)")
    args = p.parse_args()
    sys.exit(main(args.only))
