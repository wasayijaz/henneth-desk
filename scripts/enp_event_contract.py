"""Provenance-labelled input contract for offshore E&P event economics.

Every input a caller supplies must arrive as an explicit record carrying its
own provenance: either a document source reference or an analyst note.  The
contract is fail-closed.  Malformed records, unknown label types, booleans
posed as numbers, non-finite values, out-of-bounds operands, non-quarter-end
dates and lookahead ("available_on" after "valuation_date") are all rejected
with named fields.  There are no invented defaults anywhere in this module:
absent means blocked, never guessed.

Case shape (all dates ISO YYYY-MM-DD):

    {
        "symbol": str,
        "event_ref": str,
        "case_label": "bear" | "base" | "bull",
        "effective_date": date,
        "valuation_date": date,
        "inputs": {
            field: {
                "value": ...,
                "label_type": "source" | "analyst",
                "source_ref": {"id", "label", "url" | "path"},   # if source
                "analyst_ref": {"note_id", "note"},              # if analyst
                "available_on": date,
            },
        },
    }

Spend schedule rows are {"quarter_end", "phase", "amount_pkr"} with "phase"
one of exploration / appraisal / development; the schedule record carries one
provenance reference for the whole plan.  A valid quarter-end is the last day
of March, June, September or December.
"""
from __future__ import annotations

from datetime import date
import json
import math
from typing import Any, Mapping

CONTRACT_VERSION = "enp_event_contract_v1"
LABEL_TYPES = ("source", "analyst")
CASE_LABELS = ("bear", "base", "bull")
PHASES = ("exploration", "appraisal", "development")

_QUARTER_LAST_DAY = {3: 31, 6: 30, 9: 30, 12: 31}

# field -> (low, low_inclusive, high, high_inclusive)
_BOUNDED_FIELDS = {
    "working_interest_pct": (0.0, False, 100.0, True),
    "quarterly_decline_pct": (0.0, True, 100.0, False),
    "oil_share_pct": (0.0, True, 100.0, True),
    "royalty_pct": (0.0, True, 100.0, False),
    "effective_tax_pct": (0.0, True, 100.0, False),
    "discount_rate_pct_annual": (0.0, False, 100.0, False),
    "geological_success_pct": (0.0, False, 100.0, True),
    "commercial_success_pct": (0.0, False, 100.0, True),
}
_POSITIVE_FIELDS = (
    "initial_production_boe_pd",
    "oil_price_usd_bbl",
    "gas_price_usd_mmbtu",
    "gas_mmbtu_per_boe",
    "fx_pkr_usd",
    "shares_out",
)
_NON_NEGATIVE_FIELDS = ("consideration_pkr", "opex_usd_boe")
_REQUIRED_INPUTS = (
    "working_interest_pct",
    "consideration_pkr",
    "spend_schedule",
    "first_production_quarter_end",
    "production_horizon_quarters",
    "initial_production_boe_pd",
    "quarterly_decline_pct",
    "oil_share_pct",
    "oil_price_usd_bbl",
    "gas_price_usd_mmbtu",
    "gas_mmbtu_per_boe",
    "fx_pkr_usd",
    "opex_usd_boe",
    "royalty_pct",
    "effective_tax_pct",
    "discount_rate_pct_annual",
    "geological_success_pct",
    "commercial_success_pct",
)


def _as_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def is_quarter_end(value: Any) -> bool:
    """True when value is the last day of Mar/Jun/Sep/Dec."""
    parsed = _as_date(value)
    return parsed is not None and (parsed.month, parsed.day) in ((3, 31), (6, 30), (9, 30), (12, 31))


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _bounds_text(low: float, low_inclusive: bool, high: float, high_inclusive: bool) -> str:
    def fmt(bound: float) -> str:
        return str(int(bound)) if float(bound).is_integer() else repr(bound)

    return (
        ("[" if low_inclusive else "(")
        + fmt(low)
        + ", "
        + fmt(high)
        + ("]" if high_inclusive else ")")
    )


def _in_bounds(number: float, low: float, low_inclusive: bool, high: float, high_inclusive: bool) -> bool:
    above_low = number > low or (low_inclusive and number == low)
    below_high = number < high or (high_inclusive and number == high)
    return above_low and below_high


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def provenance_ok(record: Mapping[str, Any]) -> bool:
    """True when the record carries a complete source or analyst reference."""
    if not isinstance(record, Mapping):
        return False
    label_type = record.get("label_type")
    if label_type not in LABEL_TYPES:
        return False
    if label_type == "source":
        ref = record.get("source_ref")
        if not isinstance(ref, Mapping):
            return False
        has_locator = _nonempty(ref.get("url")) or _nonempty(ref.get("path"))
        return _nonempty(ref.get("id")) and _nonempty(ref.get("label")) and bool(has_locator)
    ref = record.get("analyst_ref")
    if not isinstance(ref, Mapping):
        return False
    return _nonempty(ref.get("note_id")) and _nonempty(ref.get("note"))


def validate_case(case: Mapping[str, Any]) -> list[str]:
    """Return named violations for a case; an empty list means the case is valid."""
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
    for field in _REQUIRED_INPUTS:
        if field not in inputs:
            violations.append(f"{field}: missing required input")

    for field in sorted(inputs):
        record = inputs[field]
        if not isinstance(record, Mapping):
            violations.append(f"{field}: input must be a provenance record mapping")
            continue
        if not provenance_ok(record):
            violations.append(
                f"{field}: provenance record must carry label_type and a matching complete reference"
            )
        available_on = _as_date(record.get("available_on"))
        if available_on is None:
            violations.append(f"{field}: available_on must be an ISO date (YYYY-MM-DD)")
        elif available_on > valuation:
            violations.append(f"{field}: available_on must be on or before valuation_date")

        value = record.get("value")
        if field in _BOUNDED_FIELDS:
            low, low_inclusive, high, high_inclusive = _BOUNDED_FIELDS[field]
            number = _finite(value)
            if number is None:
                violations.append(f"{field}: must be a finite number (booleans are not numbers)")
            elif not _in_bounds(number, low, low_inclusive, high, high_inclusive):
                violations.append(
                    f"{field}: must be in {_bounds_text(low, low_inclusive, high, high_inclusive)}"
                )
        elif field in _POSITIVE_FIELDS:
            number = _finite(value)
            if number is None:
                violations.append(f"{field}: must be a finite number (booleans are not numbers)")
            elif number <= 0.0:
                violations.append(f"{field}: must be > 0")
        elif field in _NON_NEGATIVE_FIELDS:
            number = _finite(value)
            if number is None:
                violations.append(f"{field}: must be a finite number (booleans are not numbers)")
            elif number < 0.0:
                violations.append(f"{field}: must be >= 0")
        elif field == "market_gap_pkr":
            if _finite(value) is None:
                violations.append(f"{field}: must be a finite number (booleans are not numbers)")
        elif field == "production_horizon_quarters":
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                violations.append("production_horizon_quarters: must be an integer >= 1")
        elif field == "consideration_non_recoverable":
            if not isinstance(value, bool):
                violations.append("consideration_non_recoverable: must be a boolean")
        elif field == "consideration_quarter_end":
            if not is_quarter_end(value):
                violations.append(
                    "consideration_quarter_end: must be a quarter-end (last day of Mar/Jun/Sep/Dec)"
                )
            elif _as_date(value) < effective:
                violations.append("consideration_quarter_end: must be on or after effective_date")
        elif field == "first_production_quarter_end":
            if not is_quarter_end(value):
                violations.append(
                    "first_production_quarter_end: must be a quarter-end (last day of Mar/Jun/Sep/Dec)"
                )
            elif _as_date(value) <= effective:
                violations.append("first_production_quarter_end: must be after effective_date")
        elif field == "spend_schedule":
            rows = value if isinstance(value, list) else None
            if not rows:
                violations.append("spend_schedule: must be a non-empty list of spend rows")
            else:
                violations.extend(_validate_spend_rows(rows, effective))
        # Unknown extra fields are hashed with the case but never interpreted.

    consideration_record = inputs.get("consideration_pkr")
    consideration = (
        _finite(consideration_record.get("value"))
        if isinstance(consideration_record, Mapping)
        else None
    )
    if consideration is not None and consideration > 0.0:
        for field in ("consideration_non_recoverable", "consideration_quarter_end"):
            if field not in inputs:
                violations.append(f"{field}: required when consideration_pkr > 0")
    return violations


def _validate_spend_rows(rows: list[Any], effective: date) -> list[str]:
    violations: list[str] = []
    for index, row in enumerate(rows):
        prefix = f"spend_schedule[{index}]"
        if not isinstance(row, Mapping):
            violations.append(f"{prefix}: must be a mapping")
            continue
        quarter_end = row.get("quarter_end")
        if not is_quarter_end(quarter_end):
            violations.append(f"{prefix}.quarter_end: must be a quarter-end (last day of Mar/Jun/Sep/Dec)")
        elif _as_date(quarter_end) < effective:
            violations.append(f"{prefix}.quarter_end: must be on or after effective_date")
        if row.get("phase") not in PHASES:
            violations.append(f"{prefix}.phase: must be one of exploration, appraisal, development")
        amount = _finite(row.get("amount_pkr"))
        if amount is None:
            violations.append(f"{prefix}.amount_pkr: must be a finite number (booleans are not numbers)")
        elif amount < 0.0:
            violations.append(f"{prefix}.amount_pkr: must be >= 0")
    return violations
