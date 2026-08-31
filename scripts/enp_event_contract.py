"""Closed, finite and provenance-labelled contract for E&P event cases."""
from __future__ import annotations

from datetime import date
import json
import math
import re
from typing import Any, Mapping

CONTRACT_VERSION = "enp_event_contract_v1"
LABEL_TYPES = ("source", "analyst")
CASE_LABELS = ("bear", "base", "bull")
PHASES = ("exploration", "appraisal", "development")
OPERATOR_STATUSES = ("operator", "non_operator")

# Conservative domain bounds keep products finite while rejecting inputs that
# are economically impossible for a PSX-listed E&P project case.
# The largest permitted scalar/output. Per-field bounds below are tighter; this
# ceiling is a final arithmetic and serialization guard (all valid combinations
# remain below 1e15 PKR, so 1e16 leaves a small safety margin).
MAX_ABS_NUMBER = 1.0e16
MAX_CASH_PKR = 1.0e12
MAX_MARKET_GAP_PKR = 1.0e13
MAX_VALUATION_LAG_DAYS = 731
MAX_PRODUCTION_START_LAG_DAYS = 3653
MAX_INPUT_FIELDS = 64
MAX_SPEND_ROWS = 256
MAX_HORIZON_QUARTERS = 80
MAX_NESTING_DEPTH = 12
MAX_SERIALIZED_BYTES = 1_000_000
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ADVICE_RE = re.compile(r"\b(?:buy|sell|accumulate|target\s+price|price\s+target|you\s+should)\b", re.I)
_QUARTER_DAYS = ((3, 31), (6, 30), (9, 30), (12, 31))

_BOUNDED_FIELDS = {
    "working_interest_pct": (0.0, False, 100.0, True),
    "quarterly_decline_pct": (0.0, True, 100.0, False),
    "oil_share_pct": (0.0, True, 100.0, True),
    "royalty_pct": (0.0, True, 100.0, False),
    "effective_tax_pct": (0.0, True, 100.0, False),
    "discount_rate_pct_annual": (0.0, False, 100.0, False),
    "geological_success_pct": (0.0, False, 100.0, True),
    "commercial_success_pct": (0.0, False, 100.0, True),
    "initial_production_boe_pd": (0.0, False, 100_000.0, True),
    "oil_price_usd_bbl": (0.0, False, 300.0, True),
    "gas_price_usd_mmbtu": (0.0, False, 50.0, True),
    "gas_mmbtu_per_boe": (0.0, False, 10.0, True),
    "fx_pkr_usd": (0.0, False, 1_000.0, True),
    "shares_out": (0.0, False, 50_000_000_000.0, True),
    "consideration_pkr": (0.0, True, MAX_CASH_PKR, True),
    "opex_usd_boe": (0.0, True, 300.0, True),
    "market_gap_pkr": (-MAX_MARKET_GAP_PKR, True, MAX_MARKET_GAP_PKR, True),
}
_REQUIRED_INPUTS = (
    "working_interest_pct", "consideration_pkr", "spend_schedule", "first_production_quarter_end",
    "production_horizon_quarters", "initial_production_boe_pd", "quarterly_decline_pct", "oil_share_pct",
    "oil_price_usd_bbl", "gas_price_usd_mmbtu", "gas_mmbtu_per_boe", "fx_pkr_usd", "opex_usd_boe",
    "royalty_pct", "effective_tax_pct", "discount_rate_pct_annual", "geological_success_pct",
    "commercial_success_pct", "shares_out", "operator_status",
)
_OPTIONAL_INPUTS = ("market_gap_pkr", "consideration_non_recoverable", "consideration_quarter_end")
ALLOWED_INPUTS = frozenset(_REQUIRED_INPUTS + _OPTIONAL_INPUTS)


def _as_date(value: Any) -> date | None:
    if type(value) is not str or not _DATE_RE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError, OverflowError):
        return None


def is_quarter_end(value: Any) -> bool:
    parsed = _as_date(value)
    return parsed is not None and (parsed.month, parsed.day) in _QUARTER_DAYS


def _finite(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return number if math.isfinite(number) and abs(number) <= MAX_ABS_NUMBER else None


def _bounds_text(low: float, low_inclusive: bool, high: float, high_inclusive: bool) -> str:
    def fmt(bound: float) -> str:
        return str(int(bound)) if bound.is_integer() else repr(bound)
    return ("[" if low_inclusive else "(") + fmt(low) + ", " + fmt(high) + ("]" if high_inclusive else ")")


def _in_bounds(number: float, low: float, low_inclusive: bool, high: float, high_inclusive: bool) -> bool:
    return (number > low or (low_inclusive and number == low)) and (number < high or (high_inclusive and number == high))


def _days_between(start: date, end: date) -> int:
    return (end - start).days


def _nonempty(value: Any) -> bool:
    return type(value) is str and bool(value.strip()) and len(value) <= 4096 and not _ADVICE_RE.search(value)


def _walk_json(value: Any, depth: int = 0, seen: set[int] | None = None) -> str | None:
    """Validate exact JSON containers without invoking hostile subclass methods."""
    if seen is None:
        seen = set()
    if depth > MAX_NESTING_DEPTH:
        return "case: nesting depth exceeds limit"
    if type(value) is dict:
        ident = id(value)
        if ident in seen:
            return "case: cyclic input is not allowed"
        seen.add(ident)
        for key, item in value.items():
            if type(key) is not str:
                return "case: object keys must be strings"
            if len(key) > 4096:
                return "case: string exceeds length limit"
            violation = _walk_json(item, depth + 1, seen)
            if violation:
                return violation
        seen.remove(ident)
    elif type(value) is list:
        ident = id(value)
        if ident in seen:
            return "case: cyclic input is not allowed"
        seen.add(ident)
        for item in value:
            violation = _walk_json(item, depth + 1, seen)
            if violation:
                return violation
        seen.remove(ident)
    elif type(value) is str:
        if len(value) > 4096 or _ADVICE_RE.search(value):
            return "case: unsupported or advice text"
    elif type(value) is bool or value is None:
        pass
    elif type(value) in (int, float):
        if _finite(value) is None:
            return "case: numbers must be finite and within magnitude limit"
    else:
        return "case: only exact JSON types are supported"
    return None


def provenance_ok(record: Mapping[str, Any]) -> bool:
    if type(record) is not dict:
        return False
    label_type = record.get("label_type")
    if type(label_type) is not str or label_type not in LABEL_TYPES:
        return False
    if label_type == "source":
        ref = record.get("source_ref")
        if type(ref) is not dict:
            return False
        return _nonempty(ref.get("id")) and _nonempty(ref.get("label")) and (_nonempty(ref.get("url")) or _nonempty(ref.get("path")))
    ref = record.get("analyst_ref")
    return type(ref) is dict and _nonempty(ref.get("note_id")) and _nonempty(ref.get("note"))


def validate_case(case: Mapping[str, Any]) -> list[str]:
    if type(case) is not dict:
        return ["case: must be an exact mapping"]
    violations: list[str] = []
    structural = _walk_json(case)
    if structural:
        violations.append(structural)
    try:
        encoded = json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_SERIALIZED_BYTES:
            violations.append("case: serialized size exceeds limit")
    except (TypeError, ValueError, OverflowError):
        violations.append("case: must be JSON-serializable")
    for field in ("symbol", "event_ref"):
        if not _nonempty(case.get(field)):
            violations.append(f"{field}: must be a non-empty string")
    case_label = case.get("case_label")
    if type(case_label) is not str or case_label not in CASE_LABELS:
        violations.append("case_label: must be one of bear, base, bull")
    effective, valuation = _as_date(case.get("effective_date")), _as_date(case.get("valuation_date"))
    if effective is None:
        violations.append("effective_date: must be an ISO date (YYYY-MM-DD)")
    if valuation is None:
        violations.append("valuation_date: must be an ISO date (YYYY-MM-DD)")
    if effective and valuation and effective > valuation:
        violations.append("effective_date: must be on or before valuation_date")
    if effective and valuation and _days_between(effective, valuation) > MAX_VALUATION_LAG_DAYS:
        violations.append(f"valuation_date: must be within {MAX_VALUATION_LAG_DAYS} days of effective_date")
    inputs = case.get("inputs")
    if type(inputs) is not dict:
        violations.append("inputs: must be an exact mapping of field to provenance record")
        return violations
    if len(inputs) > MAX_INPUT_FIELDS:
        violations.append(f"inputs: exceeds maximum field count ({MAX_INPUT_FIELDS})")
    for key in inputs:
        if type(key) is not str:
            violations.append("inputs: field keys must be strings")
        elif key not in ALLOWED_INPUTS:
            violations.append(f"{key}: unknown E&P input field")
    for field in _REQUIRED_INPUTS:
        if field not in inputs:
            violations.append(f"{field}: missing required input")
    if effective is None or valuation is None:
        return violations
    for field in sorted(inputs):
        record = inputs[field]
        if type(record) is not dict:
            violations.append(f"{field}: input must be a provenance record mapping")
            continue
        if not provenance_ok(record):
            violations.append(f"{field}: provenance record must carry label_type and a matching complete reference")
        available_on = _as_date(record.get("available_on"))
        if available_on is None:
            violations.append(f"{field}: available_on must be an ISO date (YYYY-MM-DD)")
        elif available_on > valuation:
            violations.append(f"{field}: available_on must be on or before valuation_date")
        value = record.get("value")
        if field in _BOUNDED_FIELDS:
            number = _finite(value)
            if number is None:
                violations.append(f"{field}: must be a finite number (booleans are not numbers)")
            elif not _in_bounds(number, *_BOUNDED_FIELDS[field]):
                if field == "shares_out" and number <= 0:
                    violations.append("shares_out: must be > 0")
                else:
                    violations.append(f"{field}: must be in {_bounds_text(*_BOUNDED_FIELDS[field])}")
        elif field == "production_horizon_quarters":
            if type(value) is not int or value < 1 or value > MAX_HORIZON_QUARTERS:
                violations.append(f"production_horizon_quarters: must be an integer >= 1 and <= {MAX_HORIZON_QUARTERS}")
        elif field == "operator_status":
            if type(value) is not str or value not in OPERATOR_STATUSES:
                violations.append("operator_status: must be operator or non_operator")
        elif field == "consideration_non_recoverable":
            if type(value) is not bool:
                violations.append("consideration_non_recoverable: must be a boolean")
        elif field == "consideration_quarter_end":
            if not is_quarter_end(value):
                violations.append("consideration_quarter_end: must be a quarter-end (last day of Mar/Jun/Sep/Dec)")
            elif _as_date(value) < effective:
                violations.append("consideration_quarter_end: must be on or after effective_date")
        elif field == "first_production_quarter_end":
            if not is_quarter_end(value):
                violations.append("first_production_quarter_end: must be a quarter-end (last day of Mar/Jun/Sep/Dec)")
            elif _as_date(value) <= effective:
                violations.append("first_production_quarter_end: must be after effective_date")
            elif _days_between(effective, _as_date(value)) > MAX_PRODUCTION_START_LAG_DAYS:
                violations.append(f"first_production_quarter_end: must be within {MAX_PRODUCTION_START_LAG_DAYS} days of effective_date")
        elif field == "spend_schedule":
            rows = value if type(value) is list else None
            if not rows:
                violations.append("spend_schedule: must be a non-empty list of spend rows")
            elif len(rows) > MAX_SPEND_ROWS:
                violations.append(f"spend_schedule: exceeds maximum row count ({MAX_SPEND_ROWS})")
            else:
                violations.extend(_validate_spend_rows(rows, effective))
    consideration_record = inputs.get("consideration_pkr")
    consideration = _finite(consideration_record.get("value")) if type(consideration_record) is dict else None
    if consideration is not None and consideration > 0:
        for field in ("consideration_non_recoverable", "consideration_quarter_end"):
            if field not in inputs:
                violations.append(f"{field}: required when consideration_pkr > 0")
    return violations


def _validate_spend_rows(rows: list[Any], effective: date) -> list[str]:
    violations: list[str] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        prefix = f"spend_schedule[{index}]"
        if type(row) is not dict:
            violations.append(f"{prefix}: must be a mapping")
            continue
        quarter_end, phase = row.get("quarter_end"), row.get("phase")
        if not is_quarter_end(quarter_end):
            violations.append(f"{prefix}.quarter_end: must be a quarter-end (last day of Mar/Jun/Sep/Dec)")
        elif _as_date(quarter_end) < effective:
            violations.append(f"{prefix}.quarter_end: must be on or after effective_date")
        if type(phase) is not str or phase not in PHASES:
            violations.append(f"{prefix}.phase: must be one of exploration, appraisal, development")
        elif type(quarter_end) is str and is_quarter_end(quarter_end):
            key = (quarter_end, phase)
            if key in seen:
                violations.append(f"{prefix}: duplicate spend row for quarter_end and phase")
            seen.add(key)
        amount = _finite(row.get("amount_pkr"))
        if amount is None:
            violations.append(f"{prefix}.amount_pkr: must be a finite number (booleans are not numbers)")
        elif amount < 0:
            violations.append(f"{prefix}.amount_pkr: must be >= 0")
        elif amount > MAX_CASH_PKR:
            violations.append(f"{prefix}.amount_pkr: must be <= {MAX_CASH_PKR:.0f}")
    return violations
