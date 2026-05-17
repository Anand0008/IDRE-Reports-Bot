"""Test record schema + per-prompt execution orchestration."""
from dataclasses import dataclass, field
from typing import Any, Callable
from sqlalchemy.engine import Engine
from sqlalchemy import text
import requests

from testing.v10_harness.temporality import NowAnchor
from testing.v10_harness.compare import (
    Verdict, CompareResult,
    compare_json_at_paths, compare_aggregates,
)
from testing.v10_harness.measurements import Measurement, measure


VALID_CATEGORIES = {"known-report", "derived-query", "derived-ui"}


@dataclass
class TestRecord:
    __test__ = False  # not a pytest test class
    id: str
    category: str
    prompt: str
    report: str | None = None
    expected_idre_call: dict | None = None
    compare_fields: list[str] = field(default_factory=list)
    ground_truth_sql: list[dict] = field(default_factory=list)
    bot_must_return_keys: list[str] = field(default_factory=list)
    temporality: str = "variant"  # "variant" | "stable"
    notes: str = ""
    validator: str | None = None  # derived-ui: name of UI validator to invoke
    validator_params: dict = field(default_factory=dict)  # derived-ui params

    @classmethod
    def from_dict(cls, d: dict) -> "TestRecord":
        if d.get("category") not in VALID_CATEGORIES:
            raise ValueError(f"unknown category: {d.get('category')}")
        return cls(
            id=d["id"],
            category=d["category"],
            prompt=d["prompt"],
            report=d.get("report"),
            expected_idre_call=d.get("expected_idre_call"),
            compare_fields=d.get("compare_fields", []),
            ground_truth_sql=d.get("ground_truth_sql", []),
            bot_must_return_keys=d.get("bot_must_return_keys", []),
            temporality=d.get("temporality", "variant"),
            notes=d.get("notes", ""),
            validator=d.get("validator"),
            validator_params=d.get("validator_params", {}),
        )


@dataclass
class TestResult:
    __test__ = False  # not a pytest test class
    record: TestRecord
    verdict: Verdict
    diffs: list[str]
    bot_measurement: dict
    harness_measurement: dict
    bot_payload: Any = None
    expected_payload: Any = None

    def to_dict(self) -> dict:
        return {
            "id": self.record.id,
            "category": self.record.category,
            "verdict": self.verdict.value,
            "diffs": self.diffs,
            "bot_measurement": self.bot_measurement,
            "harness_measurement": self.harness_measurement,
        }


def run_known_report_test(
    record: TestRecord,
    bot_runner: Callable[[str, NowAnchor], dict],
    idre_session: requests.Session,
    now_anchor: NowAnchor,
    idre_base_url: str = "http://127.0.0.1:3000",
) -> TestResult:
    """Run a known-report test. Calls bot AND IDRE in parallel-equivalent fashion."""
    # Bot path
    with measure() as bot_m:
        bot_response = bot_runner(record.prompt, now_anchor)

    # Ground-truth path
    call = record.expected_idre_call or {}
    with measure() as harness_m:
        resp = idre_session.request(
            method=call.get("method", "GET"),
            url=f"{idre_base_url}{call.get('path', '')}",
            params=call.get("query", {}),
            timeout=300,
        )
        expected = resp.json() if resp.status_code == 200 else {"_http_status": resp.status_code}

    cmp = compare_json_at_paths(bot_response, expected, record.compare_fields)
    return TestResult(
        record=record,
        verdict=cmp.verdict,
        diffs=cmp.diff,
        bot_measurement=bot_m.to_dict(),
        harness_measurement=harness_m.to_dict(),
        bot_payload=bot_response,
        expected_payload=expected,
    )


def run_derived_query_test(
    record: TestRecord,
    bot_runner: Callable[[str, NowAnchor], dict],
    staging_engine: Engine,
    now_anchor: NowAnchor,
) -> TestResult:
    """Run a derived-query test. Compares bot's dict result to harness-computed truth."""
    # Bot path
    with measure() as bot_m:
        bot_result = bot_runner(record.prompt, now_anchor)
    # Bot result is expected to be a dict keyed by names in bot_must_return_keys

    # Ground-truth path
    expected: dict[str, Any] = {}
    with measure() as harness_m:
        with staging_engine.connect() as conn:
            for entry in record.ground_truth_sql:
                bound = now_anchor.bind_sql(entry["sql"])
                row = conn.execute(text(bound["sql"]), bound["params"]).mappings().first()
                if row is None:
                    expected[entry["name"]] = None
                else:
                    # Convention: single-column ground-truth SQL aliased AS v, else first column
                    if "v" in row:
                        expected[entry["name"]] = row["v"]
                    else:
                        expected[entry["name"]] = list(row.values())[0]

    # Check required keys present
    missing_keys = [k for k in record.bot_must_return_keys if k not in bot_result]
    if missing_keys:
        return TestResult(
            record=record,
            verdict=Verdict.FAIL,
            diffs=[f"Bot result missing keys: {missing_keys}"],
            bot_measurement=bot_m.to_dict(),
            harness_measurement=harness_m.to_dict(),
            bot_payload=bot_result,
            expected_payload=expected,
        )

    cmp = compare_aggregates(bot_result, expected, float_tolerance=0.01)
    return TestResult(
        record=record,
        verdict=cmp.verdict,
        diffs=cmp.diff,
        bot_measurement=bot_m.to_dict(),
        harness_measurement=harness_m.to_dict(),
        bot_payload=bot_result,
        expected_payload=expected,
    )


def run_derived_ui_test(
    record: TestRecord,
    bot_runner: Callable[[str, NowAnchor], dict],
    page,
    now_anchor: NowAnchor,
) -> TestResult:
    """Run a derived-ui test.

    Bot generates SQL & executes via its own pipeline → returns rows.
    Validator drives IDRE's UI/API via Playwright → returns scalar/dict.
    Compare exact (float tolerance 0.01).
    """
    from testing.v10_harness.ui_validators import get as get_validator

    with measure() as bot_m:
        bot_raw = bot_runner(record.prompt, now_anchor)

    # Reduce bot result to {key: number} dict, matching validator's shape
    bot_dict: dict[str, Any] = {}
    data = bot_raw.get("data") if isinstance(bot_raw, dict) else bot_raw
    if isinstance(data, list) and data and isinstance(data[0], dict):
        first = data[0]
        if len(record.bot_must_return_keys) == 1:
            # Single-key case: take first scalar value from the first row
            only_key = record.bot_must_return_keys[0]
            if only_key in first:
                bot_dict[only_key] = first[only_key]
            else:
                vals = list(first.values())
                bot_dict[only_key] = vals[0] if vals else None
        else:
            for k in record.bot_must_return_keys:
                bot_dict[k] = first.get(k)
    elif isinstance(data, dict):
        for k in record.bot_must_return_keys:
            bot_dict[k] = data.get(k)

    if not record.validator:
        return TestResult(
            record=record,
            verdict=Verdict.FAIL,
            diffs=["derived-ui record missing 'validator' field"],
            bot_measurement=bot_m.to_dict(),
            harness_measurement={},
            bot_payload=bot_dict,
            expected_payload=None,
        )

    with measure() as ui_m:
        validator = get_validator(record.validator)
        ui_dict = validator.extract(page, record.validator_params)

    cmp = compare_aggregates(bot_dict, ui_dict, float_tolerance=0.01)
    return TestResult(
        record=record,
        verdict=cmp.verdict,
        diffs=cmp.diff,
        bot_measurement=bot_m.to_dict(),
        harness_measurement=ui_m.to_dict(),
        bot_payload=bot_dict,
        expected_payload=ui_dict,
    )
