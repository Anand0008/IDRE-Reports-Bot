"""Live smoke test for case_status_filter validator.

Hits IDRE local /dashboard/cases with each known status and confirms
the validator returns the count we expect from the dev dataset.

Run:
    py311 -m testing.v10_harness.ui_validators._smoke_case_status_filter
"""
from __future__ import annotations

import sys
import requests
from playwright.sync_api import sync_playwright


def main() -> int:
    s = requests.Session()
    s.get("http://127.0.0.1:3000/api/dev/auto-login",
          allow_redirects=True, timeout=30)

    # Dev-data ground truth (from the task brief)
    expected = {
        "FINAL_DETERMINATION_PENDING": 8,
        "INITIAL_ELIGIBILITY_REVIEW": 7,
        "PENDING_RFI": 5,
        "FINAL_ELIGIBILITY_COMPLETED": 4,
        "FINAL_DETERMINATION_RENDERED": 4,
        "PENDING_SECOND_PAYMENT": 3,
        "FINAL_ELIGIBILITY_REVIEW": 3,
        "PENDING_PAYMENTS": 2,
        # Zero-count statuses
        "INELIGIBLE_PENDING_ADMIN_FEE": 0,
        "PENDING_ADMINISTRATIVE_CLOSURE": 0,
    }

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
            v = get("case_status_filter")

            failures = []
            for status, exp in expected.items():
                got = v.extract(page, {"status": status})
                ok = got.get("count") == exp
                print(f"  {status}: got {got}, expected {exp} {'OK' if ok else 'FAIL'}",
                      flush=True)
                if not ok:
                    failures.append((status, exp, got))

            # Multi-status: pick PENDING_RFI + PENDING_PAYMENTS = 5 + 2 = 7
            got_multi = v.extract(page, {"statuses": ["PENDING_RFI", "PENDING_PAYMENTS"]})
            print(f"  [PENDING_RFI, PENDING_PAYMENTS]: got {got_multi}, expected 7 "
                  f"{'OK' if got_multi.get('count') == 7 else 'FAIL'}", flush=True)
            if got_multi.get("count") != 7:
                failures.append(("multi", 7, got_multi))

            if failures:
                print(f"\nFAIL: {len(failures)} mismatch(es)", flush=True)
                for f in failures:
                    print(f"  {f}", flush=True)
                return 1
            print("\nPASS: all status counts match dev-data ground truth", flush=True)
            return 0
        finally:
            b.close()


if __name__ == "__main__":
    sys.exit(main())
