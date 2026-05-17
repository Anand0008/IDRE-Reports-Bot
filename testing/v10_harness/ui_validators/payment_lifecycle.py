"""payment_lifecycle validator — counts cases by payment-lifecycle segment.

Maps Ashlee's P0/P1/P2 terminology onto IDRE CaseStatus enum values and
delegates to case_status_filter (same /dashboard/cases pagination read).

Segments:
- P0 = "no payments received" → status = PENDING_PAYMENTS
- P1 = "first received, second pending" → status = PENDING_SECOND_PAYMENT
- P2 = "both payments received" → status = FINAL_ELIGIBILITY_REVIEW
  (per Ashlee: once both arrive, the case moves into final-eligibility review)

If a future test entry needs a different segment-to-status mapping, add it
to SEGMENT_TO_STATUS rather than reimplementing the UI interaction.

Returns: {"count": int}
"""
from __future__ import annotations

from playwright.sync_api import Page

from . import REGISTRY
from .case_status_filter import CaseStatusFilterValidator

SEGMENT_TO_STATUS: dict[str, str] = {
    "P0": "PENDING_PAYMENTS",
    "P1": "PENDING_SECOND_PAYMENT",
    "P2": "FINAL_ELIGIBILITY_REVIEW",
}


class PaymentLifecycleValidator:
    name = "payment_lifecycle"

    def __init__(self) -> None:
        # Delegate to case_status_filter — same DOM read, different param shape.
        self._inner = CaseStatusFilterValidator()

    def extract(self, page: Page, params: dict) -> dict:
        segment = params["segment"]
        if segment not in SEGMENT_TO_STATUS:
            raise ValueError(
                f"unknown payment-lifecycle segment {segment!r}; "
                f"expected one of {sorted(SEGMENT_TO_STATUS)}"
            )
        status = SEGMENT_TO_STATUS[segment]
        return self._inner.extract(page, {"status": status})


REGISTRY["payment_lifecycle"] = PaymentLifecycleValidator
