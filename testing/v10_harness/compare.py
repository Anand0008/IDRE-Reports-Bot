"""Result comparison primitives. NO keyword scoring — only result equality."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"


@dataclass
class CompareResult:
    verdict: Verdict
    diff: list[str] = field(default_factory=list)


def _row_signature(row: dict) -> tuple:
    return tuple(sorted((k, _hash_value(v)) for k, v in row.items()))


def _hash_value(v: Any) -> Any:
    if isinstance(v, list):
        return tuple(_hash_value(x) for x in v)
    if isinstance(v, dict):
        return tuple(sorted((k, _hash_value(val)) for k, val in v.items()))
    return v


def compare_row_sets(bot: list[dict], expected: list[dict]) -> CompareResult:
    """Set-equality between two lists of dict rows. Order ignored."""
    bot_sigs = sorted(_row_signature(r) for r in bot)
    exp_sigs = sorted(_row_signature(r) for r in expected)
    if bot_sigs == exp_sigs:
        return CompareResult(Verdict.PASS)
    bot_set = set(bot_sigs)
    exp_set = set(exp_sigs)
    diff = []
    missing = exp_set - bot_set
    extra = bot_set - exp_set
    if missing:
        diff.append(f"Bot missing {len(missing)} expected row(s); first: {list(missing)[0]}")
    if extra:
        diff.append(f"Bot has {len(extra)} extra row(s); first: {list(extra)[0]}")
    return CompareResult(Verdict.FAIL, diff)


def _try_numeric(v: Any) -> tuple[bool, float | None]:
    """Best-effort numeric coercion. Returns (succeeded, value)."""
    if v is None:
        return False, None
    if isinstance(v, bool):
        return False, None  # don't treat True/False as 1/0 for aggregate comparison
    if isinstance(v, (int, float)):
        return True, float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if s == "":
            return False, None
        try:
            return True, float(s)
        except ValueError:
            return False, None
    return False, None


def compare_aggregates(
    bot: dict[str, Any],
    expected: dict[str, Any],
    float_tolerance: float = 0.0,
) -> CompareResult:
    """Compare aggregate dicts. Numeric values (incl numeric strings) compared
    with tolerance; non-numeric values compared strictly."""
    diff = []
    for key, exp_val in expected.items():
        if key not in bot:
            diff.append(f"Missing key: {key}")
            continue
        bot_val = bot[key]
        bot_ok, bot_num = _try_numeric(bot_val)
        exp_ok, exp_num = _try_numeric(exp_val)
        if bot_ok and exp_ok:
            if abs(bot_num - exp_num) > float_tolerance:
                diff.append(f"{key}: bot={bot_val!r} expected={exp_val!r} (tol={float_tolerance})")
        else:
            if bot_val != exp_val:
                diff.append(f"{key}: bot={bot_val!r} expected={exp_val!r}")
    return CompareResult(Verdict.FAIL if diff else Verdict.PASS, diff)


def _extract_path(obj: Any, path: str) -> list:
    """Extract values from `obj` using a dotted path with `[*]` for array fanout."""
    parts = path.split(".")
    current = [obj]
    for part in parts:
        next_level = []
        for item in current:
            if part.endswith("[*]"):
                key = part[:-3]
                arr = item.get(key, []) if isinstance(item, dict) else []
                next_level.extend(arr if isinstance(arr, list) else [])
            else:
                if isinstance(item, dict):
                    next_level.append(item.get(part))
        current = next_level
    return current


def compare_json_at_paths(
    bot: dict, expected: dict, paths: list[str]
) -> CompareResult:
    """Compare two JSON responses at a list of dotted paths."""
    diff = []
    for path in paths:
        bot_vals = _extract_path(bot, path)
        exp_vals = _extract_path(expected, path)
        # Order-independent for array fanouts
        if "[*]" in path:
            if sorted(map(repr, bot_vals)) != sorted(map(repr, exp_vals)):
                diff.append(
                    f"Path {path}: bot has {len(bot_vals)} values, "
                    f"expected {len(exp_vals)} values; sets differ"
                )
        else:
            if bot_vals != exp_vals:
                diff.append(f"Path {path}: bot={bot_vals} expected={exp_vals}")
    return CompareResult(Verdict.FAIL if diff else Verdict.PASS, diff)
