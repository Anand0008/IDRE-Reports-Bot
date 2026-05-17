"""Live smoke test for due_dates_filter validator.

Confirms each urgency bucket returns a count, and at least one is non-zero.

Run:
    py311 -m testing.v10_harness.ui_validators._smoke_due_dates_filter
"""
from __future__ import annotations

import sys
import requests
from playwright.sync_api import sync_playwright


def main() -> int:
    s = requests.Session()
    s.get("http://127.0.0.1:3000/api/dev/auto-login",
          allow_redirects=True, timeout=30)

    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            ctx = b.new_context()
            ctx.add_cookies([{
                "name": c.name, "value": c.value,
                "domain": "127.0.0.1", "path": "/",
            } for c in s.cookies])
            page = ctx.new_page()

            sys.path.insert(0, "C:/Users/anand/Downloads/local")
            from testing.v10_harness.ui_validators import get
            v = get("due_dates_filter")

            results: dict[str, int] = {}
            for urgency in ["overdue", "urgent", "warning", "normal",
                            "approaching", "all"]:
                got = v.extract(page, {"urgency": urgency})
                count = got.get("count")
                results[urgency] = count
                print(f"  urgency={urgency}: {got}", flush=True)

            # Sanity: overdue+urgent+warning+normal == all (totalCases)
            sum_buckets = (
                results["overdue"] + results["urgent"]
                + results["warning"] + results["normal"]
            )
            sum_ok = sum_buckets == results["all"]
            print(f"  sum(overdue+urgent+warning+normal)={sum_buckets} "
                  f"vs all={results['all']} "
                  f"{'OK' if sum_ok else 'FAIL'}", flush=True)

            # Plan-spec alias: approaching == urgent
            alias_ok = results["approaching"] == results["urgent"]
            print(f"  approaching == urgent: {alias_ok} "
                  f"{'OK' if alias_ok else 'FAIL'}", flush=True)

            # At least one bucket non-zero (against dev data of 36 cases)
            any_nonzero = any(v > 0 for v in [
                results["overdue"], results["urgent"],
                results["warning"], results["normal"],
            ])
            print(f"  any bucket non-zero: {any_nonzero} "
                  f"{'OK' if any_nonzero else 'FAIL'}", flush=True)

            if not (sum_ok and alias_ok and any_nonzero):
                print("\nFAIL", flush=True)
                return 1
            print("\nPASS", flush=True)
            return 0
        finally:
            b.close()


if __name__ == "__main__":
    sys.exit(main())
