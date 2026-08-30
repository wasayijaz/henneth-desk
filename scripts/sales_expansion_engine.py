"""Pure sales-led expansion economics kernel.

The engine consumes one provenance-validated bear, base or bull case and emits
eight end-of-quarter operating rows: revenue, SG&A, gross profit, EBITDA,
operating EPS (NOPAT per share), free cash flow and ROIC, plus discounted
cash flow. Compensation is annual USD converted with the explicit FX input;
marketing is already PKR. Revenue equals the explicit starting revenue plus
sales hires times the explicit quarterly productivity ramp. Support hires are
an SG&A cost. Working capital is a percentage of revenue and its quarter-over-
quarter change reduces FCF. Initial investment is a Q1 cash outflow and the
ROIC denominator.

This is a sector-specific research calculator, not a universal formula engine.
CAC/retention are intentionally not modeled in v1; no values are invented for
them. Cases are isolated and never weighted. The module is stateless,
stdlib-only and importable without file or network I/O.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from typing import Any, Mapping

import sales_expansion_contract as contract

ENGINE_VERSION = "sales_expansion_engine_v1"
FORMULA_ID = "sales_expansion.operating_economics.v1"
RESULT_SCHEMA = "sales_expansion_model_result_v1"


def _as_date(value: Any) -> date:
    return date.fromisoformat(str(value))


def _quarter_exponent(quarter_end: date, valuation_date: date) -> int:
    return 4 * (quarter_end.year - valuation_date.year) + (
        quarter_end.month // 3 - valuation_date.month // 3
    )


def _quarterly_rate(annual_pct: float) -> float:
    return (1.0 + annual_pct / 100.0) ** 0.25 - 1.0


def quarterly_metrics(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Calculate eight deterministic quarterly operating rows after validation."""
    violations = contract.validate_case(case)
    if violations:
        raise ValueError("; ".join(violations))
    inputs = case["inputs"]
    quarter_ends = inputs["quarter_ends"]["value"]
    sales_hires = inputs["sales_hires_schedule"]["value"]
    support_hires = inputs["support_hires_schedule"]["value"]
    marketing = inputs["marketing_spend_pkr_schedule"]["value"]
    productivity = inputs["productivity_revenue_pkr_per_sales_hire_schedule"]["value"]
    starting_revenue = float(inputs["starting_revenue_pkr"]["value"])
    sales_comp = float(inputs["sales_compensation_usd_annual"]["value"]) / 4.0
    support_comp = float(inputs["support_compensation_usd_annual"]["value"]) / 4.0
    fx = float(inputs["fx_pkr_usd"]["value"])
    gross_margin = float(inputs["gross_margin_pct"]["value"]) / 100.0
    working_capital_rate = float(inputs["working_capital_pct_revenue"]["value"]) / 100.0
    investment = float(inputs["initial_investment_pkr"]["value"])
    tax_rate = float(inputs["effective_tax_pct"]["value"]) / 100.0
    shares = float(inputs["shares_out"]["value"])
    valuation_date = _as_date(case["valuation_date"])
    discount_rate = _quarterly_rate(float(inputs["discount_rate_pct_annual"]["value"]))

    rows: list[dict[str, Any]] = []
    previous_working_capital = starting_revenue * working_capital_rate
    cumulative_fcf = 0.0
    for index in range(contract.QUARTER_COUNT):
        quarter_end = _as_date(quarter_ends[index])
        revenue = starting_revenue + float(sales_hires[index]) * float(productivity[index])
        sga = (
            float(sales_hires[index]) * sales_comp * fx
            + float(support_hires[index]) * support_comp * fx
            + float(marketing[index])
        )
        gross_profit = revenue * gross_margin
        ebitda = gross_profit - sga
        tax = ebitda * tax_rate if ebitda > 0.0 else 0.0
        nopat = ebitda - tax
        working_capital = revenue * working_capital_rate
        delta_working_capital = working_capital - previous_working_capital
        initial_investment = investment if index == 0 else 0.0
        fcf = nopat - delta_working_capital - initial_investment
        cumulative_fcf += fcf
        exponent = _quarter_exponent(quarter_end, valuation_date)
        discount_factor = (1.0 + discount_rate) ** (-exponent)
        rows.append(
            {
                "quarter_index": index + 1,
                "quarter_end": quarter_end.isoformat(),
                "sales_hires": sales_hires[index],
                "support_hires": support_hires[index],
                "revenue_pkr": revenue,
                "sga_pkr": sga,
                "gross_profit_pkr": gross_profit,
                "ebitda_pkr": ebitda,
                "tax_pkr": tax,
                "eps_pkr": nopat / shares,
                "working_capital_pkr": working_capital,
                "delta_working_capital_pkr": delta_working_capital,
                "fcf_pkr": fcf,
                "cumulative_fcf_pkr": cumulative_fcf,
                "roic_pct": nopat / investment * 100.0,
                "discount_factor": discount_factor,
                "discounted_fcf_pkr": fcf * discount_factor,
            }
        )
        for key, value in rows[-1].items():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"quarterly_schedule[{index + 1}].{key}: non-finite output")
        previous_working_capital = working_capital
    return rows


def break_even_metrics(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Return first EBITDA and cumulative-cash break-even quarters, if reached."""
    ebitda_row = next((row for row in rows if row["ebitda_pkr"] >= 0.0), None)
    cash_row = next((row for row in rows if row["cumulative_fcf_pkr"] >= 0.0), None)
    notes: list[str] = []
    if ebitda_row is None:
        notes.append("EBITDA break-even is not reached within the eight-quarter horizon")
    if cash_row is None:
        notes.append("cumulative cash break-even is not reached within the eight-quarter horizon")
    return {
        "ebitda_break_even_quarter": ebitda_row["quarter_index"] if ebitda_row else None,
        "ebitda_break_even_quarter_end": ebitda_row["quarter_end"] if ebitda_row else None,
        "cash_break_even_quarter": cash_row["quarter_index"] if cash_row else None,
        "cash_break_even_quarter_end": cash_row["quarter_end"] if cash_row else None,
        "note": "; ".join(notes) if notes else None,
    }


def evaluate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Return a computed envelope or raise ValueError for invalid input."""
    violations = contract.validate_case(case)
    if violations:
        raise ValueError("; ".join(violations))
    canonical = json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    rows = quarterly_metrics(case)
    try:
        npv = math.fsum(row["discounted_fcf_pkr"] for row in rows)
        values = {
            "npv_pkr": npv,
            "total_revenue_pkr": math.fsum(row["revenue_pkr"] for row in rows),
            "total_gross_profit_pkr": math.fsum(row["gross_profit_pkr"] for row in rows),
            "total_ebitda_pkr": math.fsum(row["ebitda_pkr"] for row in rows),
            "total_fcf_pkr": math.fsum(row["fcf_pkr"] for row in rows),
        }
    except OverflowError as error:
        raise ValueError("values: non-finite output from aggregate overflow") from error
    for key, value in values.items():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"values.{key}: non-finite output")
    shares = float(case["inputs"]["shares_out"]["value"])
    per_share_npv = npv / shares
    if not math.isfinite(per_share_npv):
        raise ValueError("per_share.npv_pkr: non-finite output")
    return {
        "schema_version": RESULT_SCHEMA,
        "formula_id": FORMULA_ID,
        "engine_version": ENGINE_VERSION,
        "run_receipt": {
            "inputs_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "contract_version": contract.CONTRACT_VERSION,
        },
        "status": "computed",
        "blocked_reasons": [],
        "scenario": {
            "symbol": case["symbol"],
            "event_ref": case["event_ref"],
            "case_label": case["case_label"],
            "effective_date": case["effective_date"],
            "valuation_date": case["valuation_date"],
        },
        "inputs_lineage": _inputs_lineage(case["inputs"]),
        "quarterly_schedule": rows,
        "values": values,
        "per_share": {"npv_pkr": per_share_npv},
        "break_even": break_even_metrics(rows),
        "confidence_limitations": {
            "research_only": True,
            "no_advice": True,
            "single_point_estimate": True,
            "simplifications": [
                "CAC and customer retention are not modeled in v1",
                "sales-led revenue is starting revenue plus explicit sales-hire productivity; no account expansion or churn",
                "compensation is a fixed annual USD rate converted with explicit FX and divided by four",
                "tax is an effective cash-tax rate on positive quarterly EBITDA; no loss carryforward or depreciation shield",
                "working capital is a percentage of revenue; no capex or terminal value is modeled",
                "EPS is operating NOPAT per share, not a full statutory earnings measure",
                "cases are isolated bear/base/bull scenarios; no scenario weighting is performed",
                "discounting uses end-of-quarter timing and compounds pre-valuation quarters forward",
            ],
        },
    }


def _inputs_lineage(inputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for field in sorted(inputs):
        record = inputs[field]
        entry: dict[str, Any] = {
            "field": field,
            "value": record.get("value"),
            "label_type": record.get("label_type"),
            "available_on": record.get("available_on"),
        }
        if record.get("label_type") == "source":
            entry["source_ref"] = record.get("source_ref")
        else:
            entry["analyst_ref"] = record.get("analyst_ref")
        entries.append(entry)
    return entries


def blocked_result(identity: Mapping[str, Any], reasons: list[str]) -> dict[str, Any]:
    """Create an identity-only blocked envelope with no partial calculations."""
    return {
        "schema_version": RESULT_SCHEMA,
        "formula_id": FORMULA_ID,
        "engine_version": ENGINE_VERSION,
        "run_receipt": {
            "inputs_sha256": None,
            "contract_version": contract.CONTRACT_VERSION,
        },
        "status": "blocked",
        "blocked_reasons": sorted(set(str(reason) for reason in reasons)),
        "scenario": {
            "symbol": identity.get("symbol"),
            "event_ref": identity.get("event_ref"),
            "case_label": identity.get("case_label"),
            "effective_date": identity.get("effective_date"),
            "valuation_date": identity.get("valuation_date"),
        },
        "inputs_lineage": [],
        "quarterly_schedule": [],
        "values": None,
        "per_share": None,
        "break_even": None,
        "confidence_limitations": {
            "research_only": True,
            "no_advice": True,
            "single_point_estimate": True,
            "simplifications": ["blocked before calculation; missing or invalid inputs"],
        },
    }
