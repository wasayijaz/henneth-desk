"""Fail-closed provenance contract for a cement capacity-expansion case.

Each numeric input is an explicit source- or analyst-labelled record with an
availability date no later than valuation_date. The contract is closed:
unknown input fields, missing references, booleans, non-finite values, malformed
dates, schedule length/order errors and out-of-bounds values are rejected.
Schedules carry exactly eight quarter values; no defaults are invented.
"""
from __future__ import annotations

from datetime import date
import json
import math
from typing import Any, Mapping

CONTRACT_VERSION = "cement_expansion_contract_v1"
LABEL_TYPES = ("source", "analyst")
CASE_LABELS = ("bear", "base", "bull")
QUARTER_COUNT = 8

_BOUNDED = {
    "gross_margin_pct": (0.0, True, 100.0, True),
    "working_capital_pct_revenue": (0.0, True, 100.0, False),
    "effective_tax_pct": (0.0, True, 100.0, False),
    "annual_interest_rate_pct": (0.0, True, 100.0, False),
    "discount_rate_pct_annual": (0.0, False, 100.0, False),
}
_POSITIVE = (
    "incremental_capacity_units",
    "selling_price_pkr_per_unit",
    "shares_out",
    "equity_financing_pkr",
)
_NON_NEGATIVE = (
    "starting_utilization_pct",
    "starting_revenue_pkr",
    "debt_financing_pkr",
    "capex_schedule_pkr",
    "utilization_ramp_pct_schedule",
    "selling_price_pkr_per_unit_schedule",
    "fuel_cost_pkr_per_unit_schedule",
    "power_cost_pkr_per_unit_schedule",
    "freight_cost_pkr_per_unit_schedule",
    "fixed_cost_pkr_schedule",
    "depreciation_pkr_schedule",
)
_REQUIRED = (
    "quarter_ends",
    "commissioning_quarter_index",
    "incremental_capacity_units",
    "starting_utilization_pct",
    "utilization_ramp_pct_schedule",
    "starting_revenue_pkr",
    "selling_price_pkr_per_unit_schedule",
    "fuel_cost_pkr_per_unit_schedule",
    "power_cost_pkr_per_unit_schedule",
    "freight_cost_pkr_per_unit_schedule",
    "fixed_cost_pkr_schedule",
    "capex_schedule_pkr",
    "depreciation_pkr_schedule",
    "gross_margin_pct",
    "working_capital_pct_revenue",
    "debt_financing_pkr",
    "equity_financing_pkr",
    "annual_interest_rate_pct",
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
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
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


def _validate_number_schedule(field: str, value: Any, *, positive: bool = False) -> list[str]:
    violations = _validate_schedule_length(field, value)
    if violations:
        return violations
    for index, item in enumerate(value):
        number = _finite(item)
        if number is None:
            violations.append(f"{field}[{index}]: must be a finite number (booleans are not numbers)")
        elif positive and number <= 0.0:
            violations.append(f"{field}[{index}]: must be > 0")
        elif not positive and number < 0.0:
            violations.append(f"{field}[{index}]: must be >= 0")
    return violations


def _validate_pct_schedule(field: str, value: Any) -> list[str]:
    violations = _validate_number_schedule(field, value)
    if violations:
        return violations
    for index, item in enumerate(value):
        number = _finite(item)
        if number is not None and not _in_bounds(number, 0.0, True, 100.0, True):
            violations.append(f"{field}[{index}]: must be in [0, 100]")
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
        json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError):
        violations.append("case: must be JSON-serializable and finite")
    if effective is None or valuation is None:
        return violations
    inputs = case.get("inputs")
    if not isinstance(inputs, Mapping):
        violations.append("inputs: must be a mapping of field to provenance record")
        return violations
    for field in sorted((set(inputs) - set(_REQUIRED)), key=str):
        violations.append(f"{field}: unknown input field")
    for field in _REQUIRED:
        if field not in inputs:
            violations.append(f"{field}: missing required input")
    for field, record in sorted(inputs.items(), key=lambda item: str(item[0])):
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
        elif field in {"starting_utilization_pct"}:
            number = _finite(value)
            if number is None:
                violations.append(f"{field}: must be a finite number (booleans are not numbers)")
            elif not _in_bounds(number, 0.0, True, 100.0, True):
                violations.append(f"{field}: must be in [0, 100]")
        elif field in {"starting_revenue_pkr", "debt_financing_pkr"}:
            number = _finite(value)
            if number is None:
                violations.append(f"{field}: must be a finite number (booleans are not numbers)")
            elif number < 0.0:
                violations.append(f"{field}: must be >= 0")
        elif field in {"capex_schedule_pkr",
                       "fuel_cost_pkr_per_unit_schedule", "power_cost_pkr_per_unit_schedule",
                       "freight_cost_pkr_per_unit_schedule", "fixed_cost_pkr_schedule",
                       "depreciation_pkr_schedule"}:
            violations.extend(_validate_number_schedule(field, value))
        elif field == "utilization_ramp_pct_schedule":
            violations.extend(_validate_pct_schedule(field, value))
        elif field == "selling_price_pkr_per_unit_schedule":
            violations.extend(_validate_number_schedule(field, value, positive=True))
        elif field == "commissioning_quarter_index":
            if isinstance(value, bool) or not isinstance(value, int):
                violations.append("commissioning_quarter_index: must be an integer from 1 to 8")
            elif not 1 <= value <= QUARTER_COUNT:
                violations.append("commissioning_quarter_index: must be an integer from 1 to 8")
        elif field == "quarter_ends":
            length_errors = _validate_schedule_length(field, value)
            violations.extend(length_errors)
            if not length_errors:
                previous: date | None = None
                for index, quarter_end in enumerate(value):
                    parsed = _as_date(quarter_end)
                    if not is_quarter_end(quarter_end):
                        violations.append(f"{field}[{index}]: must be a quarter-end (last day of Mar/Jun/Sep/Dec)")
                    elif parsed < valuation:
                        violations.append(f"{field}[{index}]: must be on or after valuation_date")
                    if previous is not None and parsed is not None and parsed <= previous:
                        violations.append(f"{field}[{index}]: quarter ends must be strictly increasing")
                    if parsed is not None:
                        previous = parsed
    return violations
