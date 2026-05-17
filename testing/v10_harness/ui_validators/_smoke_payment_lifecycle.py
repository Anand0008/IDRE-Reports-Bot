"""Live smoke test for payment_lifecycle validator.

Confirms P0, P1, P2 return non-zero counts on the dev dataset.

Run:
    py311 -m testing.v10_harness.ui_validators._smoke_payment_lifecycle
"""
from __future__ import annotations

import sys
import requests
from playwright.sync_api import sync_playwright


def main() -> int:
    s = requests.Session()
    s.get("http://127.0.0.1:3000/api/dev/auto-login",
          allow_redirects=True, timeout=30)

    # Dev-data ground truth
    expected = {
        "P0": 2,  # PENDING_PAYMENTS
        "P1": 3,  # PENDING_SECOND_PAYMENT
        "P2": 3,  # FINAL_ELIGIBILITY_REVIEW
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
            v = get("payment_lifecycle")

            failures = []
            for seg, exp in expected.items():
                got = v.extract(page, {"segment": seg})
                ok = got.get("count") == exp
                print(f"  {seg}: got {got}, expected {exp} "
                      f"{'OK' if ok else 'FAIL'}", flush=True)
                if not ok:
                    failures.append((seg, exp, got))

            if failures:
                print(f"\nFAIL: {failures}", flush=True)
                return 1
            print("\nPASS: P0/P1/P2 all match dev-data ground truth",
                  flush=True)
            return 0
        finally:
            b.close()


if __name__ == "__main__":
    sys.exit(main())
