"""Discover all report endpoints under idre/app/api/reports/**.
Emit a minimal card per report. (Detailed extraction lives in 05.)
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from common import IDRE_REPO, ensure_pending, write_json, git_sha


REPORTS_DIR = IDRE_REPO / "app" / "api" / "reports"


def discover_reports() -> list[dict]:
    cards = []
    if not REPORTS_DIR.exists():
        return cards
    for route_ts in REPORTS_DIR.rglob("route.ts"):
        rel = route_ts.relative_to(IDRE_REPO).as_posix()
        # The report id is the directory containing route.ts, relative to api/reports
        rel_dir = route_ts.parent.relative_to(REPORTS_DIR).as_posix()
        report_id = rel_dir or "root"
        # Look for a sibling lib dependency
        lib_candidate = IDRE_REPO / "lib" / "reports" / f"{report_id.split('/')[-1]}.ts"
        cards.append({
            "id": report_id,
            "route_file": rel,
            "lib_file": lib_candidate.relative_to(IDRE_REPO).as_posix() if lib_candidate.exists() else None,
            "endpoint": f"/api/reports/{report_id}",
        })
    cards.sort(key=lambda c: c["id"])
    return cards


def main() -> int:
    cards = discover_reports()
    if not cards:
        print(f"ERROR: no route.ts files found under {REPORTS_DIR}", file=sys.stderr)
        return 1
    out = ensure_pending() / "report_reference_cards.json"
    write_json(out, {
        "idre_git_sha": git_sha(),
        "reports": cards,
        "count": len(cards),
    })
    print(f"Wrote {len(cards)} report cards -> {out}")
    for c in cards:
        print(f"  {c['id']:30} -> {c['route_file']}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.parse_args()
    sys.exit(main())
