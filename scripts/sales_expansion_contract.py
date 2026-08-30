"""Fail-closed provenance contract for a sales-led expansion case.

A case is an isolated bear/base/bull scenario. Every input is an explicit
record with label_type source|analyst, a complete matching reference and an
available_on date no later than valuation_date. Schedules are eight-quarter
lists carried inside one provenance-labelled record. No defaults are chosen:
missing data blocks the engine.
"""
from __future__ import annotations

from datetime import date
import json
import math
from typing import Any, Mapping

CONTRACT_VERSION = "sales_expansion_contract_v1"
LABEL_TYPES = ("source", "analyst")
CASE_LABELS = ("bear", "base", "bull")
QUARTER_COUNT = 8

_BOUNDED = {
    "gross_margin_pct": (0.0, True, 100.0, True),
    "working_capital_pct_revenue": (0.0, True, 100.0, False),
    "effective_tax_pct": (0.0, True, 100.0, False),
}
_POSITIVE = (
    "sales_compensation_usd_annual",
    "support_compensation_usd_annual",
    "fx_pkr_usd",
    "initial_investment_pkr",
    "shares_out",
    "discount_rate_pct_annual",
)
_NON_NEGATIVE = ("starting_revenue_pkr", "sales_hires_schedule", "support_hires_schedule",
                 "marketing_spend_pkr_schedule", "productivity_revenue_pkr_per_sales_hire_schedule")
_REQUIRED = (
    "quarter_ends",
    "sales_hires_schedule",
    "support_hires_schedule",
    "starting_revenue_pkr",
    "sales_compensation_usd_annual",
    "support_compensation_usd_annual",
    "fx_pkr_usd",
    "marketing_spend_pkr_schedule",
    "productivity_revenue_pkr_per_sales_hire_schedule",
    "gross_margin_pct",
    "working_capital_pct_revenue",
    "initial_investment_pkr",
    "effective_tax_pct",
    "shares_out",
    "discount_rate_pct_annual",
)


def _as_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def is_quarter_end(value: Any) -> bool:
    parsed = _as_date(value)
    return parsed is not None and (parsed.month, parsed.day) in {
        (3, 31), (6, 30), (9, 30), (12, 31)
    }


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def provenance_ok(record: Mapping[str, Any]) -> bool:
    if not isinstance(record, Mapping):
        return False
    label_type = record.get("label_type")
    if label_type not in LABEL_TYPES:
        return False
    if label_type == "source":
        ref = record.get("source_ref")
        return (
            isinstance(ref, Mapping)
            and _nonempty(ref.get("id"))
            and _nonempty(ref.get("label"))
            and (_nonempty(ref.get("url")) or _nonempty(ref.get("path")))
        )
    ref = record.get("analyst_ref")
    return isinstance(ref, Mapping) and _nonempty(ref.get("note_id")) and _nonempty(ref.get("note"))


def _bounds_text(low: float, low_inc: bool, high: float, high_inc: bool) -> str:
    left = "[" if low_inc else "("
    right = "]" if high_inc else ")"
    return f"{left}{int(low) if low.is_integer() else low}, {int(high) if high.is_integer() else high}{right}"


def _in_bounds(number: float, low: float, low_inc: bool, high: float, high_inc: bool) -> bool:
    return (number > low or (low_inc and number == low)) and (
        number < high or (high_inc and number == high)
    )


def _validate_schedule_length(field: str, value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) != QUARTER_COUNT:
        return [f"{field}: must be a list of exactly {QUARTER_COUNT} values"]
    return []


def _validate_int_schedule(field: str, value: Any) -> list[str]:
    violations = _validate_schedule_length(field, value)
    if violations:
        return violations
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            violations.append(f"{field}[{index}]: must be an integer >= 0")
    return violations


def _validate_number_schedule(field: str, value: Any) -> list[str]:
    violations = _validate_schedule_length(field, value)
    if violations:
        return violations
    for index, item in enumerate(value):
        number = _finite(item)
        if number is None:
            violations.append(f"{field}[{index}]: must be a finite number (booleans are not numbers)")
        elif number < 0.0:
            violations.append(f"{field}[{index}]: must be >= 0")
    return violations


def validate_case(case: Mapping[str, Any]) -> list[str]:
    """Return named violations; an empty list means the case is valid."""
    if not isinstance(case, Mapping):
        return ["case: must be a mapping"]
    violations: list[str] = []
    for field in ("symbol", "event_ref"):
        if not _nonempty(case.get(field)):
            violations.append(f"{field}: must be a non-empty string")
    if case.get("case_label") not in CASE_LABELS:
        violations.append("case_label: must be one of bear, base, bull")
    effective = _as_date(case.get("effective_date"))
    valuation = _as_date(case.get("valuation_date"))
    if effective is None:
        violations.append("effective_date: must be an ISO date (YYYY-MM-DD)")
    if valuation is None:
        violations.append("valuation_date: must be an ISO date (YYYY-MM-DD)")
    if effective is not None and valuation is not None and effective > valuation:
        violations.append("effective_date: must be on or before valuation_date")
    try:
        json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except (TypeError, ValueError):
        violations.append("case: must be JSON-serializable")
    if effective is None or valuation is None:
        return violations
    inputs = case.get("inputs")
    if not isinstance(inputs, Mapping):
        violations.append("inputs: must be a mapping of field to provenance record")
        return violations
    for field in _REQUIRED:
        if field not in inputs:
            violations.append(f"{field}: missing required input")
    for field, record in sorted(inputs.items()):
        if not isinstance(record, Mapping):
            violations.append(f"{field}: input must be a provenance record mapping")
            continue
        if not provenance_ok(record):
            violations.append(f"{field}: provenance record must carry label_type and a complete reference")
        available_on = _as_date(record.get("available_on"))
        if available_on is None:
            violations.append(f"{field}: available_on must be an ISO date (YYYY-MM-DD)")
        elif available_on > valuation:
            violations.append(f"{field}: available_on must be on or before valuation_date")
        value = record.get("value")
        if field in _BOUNDED:
            low, low_inc, high, high_inc = _BOUNDED[field]
            number = _finite(value)
            if number is None:
                violations.append(f"{field}: must be a finite number (booleans are not numbers)")
            elif not _in_bounds(number, low, low_inc, high, high_inc):
                violations.append(f"{field}: must be in {_bounds_text(low, low_inc, high, high_inc)}")
        elif field in _POSITIVE:
            number = _finite(value)
            if number is None:
                violations.append(f"{field}: must be a finite number (booleans are not numbers)")
            elif number <= 0.0:
                violations.append(f"{field}: must be > 0")
        elif field == "starting_revenue_pkr":
            number = _finite(value)
            if number is None:
                violations.append(f"{field}: must be a finite number (booleans are not numbers)")
            elif number < 0.0:
                violations.append(f"{field}: must be >= 0")
        elif field in {"sales_hires_schedule", "support_hires_schedule"}:
            violations.extend(_validate_int_schedule(field, value))
        elif field in {"marketing_spend_pkr_schedule", "productivity_revenue_pkr_per_sales_hire_schedule"}:
            violations.extend(_validate_number_schedule(field, value))
        elif field == "quarter_ends":
            length_errors = _validate_schedule_length(field, value)
            violations.extend(length_errors)
            if not length_errors:
                previous: date | None = None
                for index, quarter_end in enumerate(value):
                    parsed = _as_date(quarter_end)
                    if not is_quarter_end(quarter_end):
                        violations.append(f"{field}[{index}]: must be a quarter-end (last day of Mar/Jun/Sep/Dec)")
                    elif parsed < effective:
                        violations.append(f"{field}[{index}]: must be on or after effective_date")
                    if previous is not None and parsed is not None and parsed <= previous:
                        violations.append(f"{field}[{index}]: quarter ends must be strictly increasing")
                    if parsed is not None:
                        previous = parsed
    return violations

