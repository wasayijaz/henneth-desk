"""Pure cement capacity-expansion operating-economics kernel.

The kernel consumes one provenance-validated bear/base/bull case and emits an
eight-quarter end-of-quarter schedule.  Incremental volume is zero until the
commissioning quarter, then equals capacity times the explicit utilization
ramp.  Existing revenue earns the explicit baseline gross margin; incremental
revenue earns selling price less the explicit fuel, power and freight costs.
Debt interest is a cash cost, while capex is a project cash outflow.  Cases are
isolated research scenarios: no orders, advice, network, files, or hidden
defaults are present.
"""
from __future__ import annotations

import copy
from datetime import date
import hashlib
import json
import math
from typing import Any, Mapping

import cement_expansion_contract as contract

ENGINE_VERSION = "cement_expansion_engine_v1"
FORMULA_ID = "cement_expansion.operating_economics.v1"
RESULT_SCHEMA = "cement_expansion_model_result_v1"


def _as_date(value: Any) -> date:
    return date.fromisoformat(str(value))


def _quarter_exponent(quarter_end: date, valuation_date: date) -> int:
    return 4 * (quarter_end.year - valuation_date.year) + (
        quarter_end.month // 3 - valuation_date.month // 3
    )


def _quarterly_rate(annual_pct: float) -> float:
    return (1.0 + annual_pct / 100.0) ** 0.25 - 1.0


def _finite_row(row: Mapping[str, Any], index: int) -> None:
    for key, value in row.items():
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"quarterly_schedule[{index}].{key}: non-finite output")


def quarterly_metrics(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Calculate eight deterministic quarterly operating rows after validation."""
    violations = contract.validate_case(case)
    if violations:
        raise ValueError("; ".join(violations))
    inputs = case["inputs"]
    quarter_ends = inputs["quarter_ends"]["value"]
    commissioning_quarter = int(inputs["commissioning_quarter_index"]["value"])
    capacity = float(inputs["incremental_capacity_units"]["value"])
    starting_utilization = float(inputs["starting_utilization_pct"]["value"])
    utilization_ramp = inputs["utilization_ramp_pct_schedule"]["value"]
    starting_revenue = float(inputs["starting_revenue_pkr"]["value"])
    selling_price = inputs["selling_price_pkr_per_unit_schedule"]["value"]
    fuel_cost = inputs["fuel_cost_pkr_per_unit_schedule"]["value"]
    power_cost = inputs["power_cost_pkr_per_unit_schedule"]["value"]
    freight_cost = inputs["freight_cost_pkr_per_unit_schedule"]["value"]
    fixed_cost = inputs["fixed_cost_pkr_schedule"]["value"]
    capex = inputs["capex_schedule_pkr"]["value"]
    depreciation = inputs["depreciation_pkr_schedule"]["value"]
    gross_margin = float(inputs["gross_margin_pct"]["value"]) / 100.0
    working_capital_rate = float(inputs["working_capital_pct_revenue"]["value"]) / 100.0
    debt = float(inputs["debt_financing_pkr"]["value"])
    equity = float(inputs["equity_financing_pkr"]["value"])
    annual_interest = float(inputs["annual_interest_rate_pct"]["value"]) / 100.0
    tax_rate = float(inputs["effective_tax_pct"]["value"]) / 100.0
    shares = float(inputs["shares_out"]["value"])
    valuation_date = _as_date(case["valuation_date"])
    discount_rate = _quarterly_rate(float(inputs["discount_rate_pct_annual"]["value"]))
    invested_capital = debt + equity
    if not math.isfinite(invested_capital):
        raise ValueError("invested_capital_pkr: non-finite output from financing aggregate")

    rows: list[dict[str, Any]] = []
    previous_working_capital = starting_revenue * working_capital_rate
    cumulative_fcf = 0.0
    for index in range(contract.QUARTER_COUNT):
        quarter_number = index + 1
        quarter_end = _as_date(quarter_ends[index])
        commissioned = quarter_number >= commissioning_quarter
        if commissioned:
            utilization_pct = float(utilization_ramp[index])
            volume = capacity * utilization_pct / 100.0
        else:
            utilization_pct = starting_utilization
            volume = 0.0
        variable_cost_per_unit = (
            float(fuel_cost[index]) + float(power_cost[index]) + float(freight_cost[index])
        )
        incremental_revenue = volume * float(selling_price[index])
        revenue = starting_revenue + incremental_revenue
        variable_cost = volume * variable_cost_per_unit
        gross_profit = starting_revenue * gross_margin + volume * (
            float(selling_price[index]) - variable_cost_per_unit
        )
        ebitda = gross_profit - float(fixed_cost[index])
        dep = float(depreciation[index])
        ebit = ebitda - dep
        finance_cost = debt * annual_interest / 4.0
        earnings_before_tax = ebit - finance_cost
        tax = max(earnings_before_tax, 0.0) * tax_rate
        net_income = earnings_before_tax - tax
        nopat = ebit - max(ebit, 0.0) * tax_rate
        working_capital = revenue * working_capital_rate
        delta_working_capital = working_capital - previous_working_capital
        fcf = ebitda - tax - finance_cost - delta_working_capital - float(capex[index])
        cumulative_fcf += fcf
        exponent = _quarter_exponent(quarter_end, valuation_date)
        discount_factor = (1.0 + discount_rate) ** (-exponent)
        row = {
            "quarter_index": quarter_number,
            "quarter_end": quarter_end.isoformat(),
            "commissioned": commissioned,
            "capacity_units": capacity,
            "utilization_pct": utilization_pct,
            "volume_units": volume,
            "selling_price_pkr_per_unit": float(selling_price[index]),
            "fuel_cost_pkr_per_unit": float(fuel_cost[index]),
            "power_cost_pkr_per_unit": float(power_cost[index]),
            "freight_cost_pkr_per_unit": float(freight_cost[index]),
            "revenue_pkr": revenue,
            "variable_cost_pkr": variable_cost,
            "gross_profit_pkr": gross_profit,
            "fixed_cost_pkr": float(fixed_cost[index]),
            "ebitda_pkr": ebitda,
            "depreciation_pkr": dep,
            "ebit_pkr": ebit,
            "finance_cost_pkr": finance_cost,
            "tax_pkr": tax,
            "net_income_pkr": net_income,
            "eps_pkr": net_income / shares,
            "working_capital_pkr": working_capital,
            "delta_working_capital_pkr": delta_working_capital,
            "capex_pkr": float(capex[index]),
            "fcf_pkr": fcf,
            "cumulative_fcf_pkr": cumulative_fcf,
            "roic_pct": nopat / invested_capital * 100.0,
            "discount_factor": discount_factor,
            "discounted_fcf_pkr": fcf * discount_factor,
        }
        _finite_row(row, quarter_number)
        rows.append(row)
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
        values = {
            "npv_pkr": math.fsum(row["discounted_fcf_pkr"] for row in rows),
            "total_revenue_pkr": math.fsum(row["revenue_pkr"] for row in rows),
            "total_gross_profit_pkr": math.fsum(row["gross_profit_pkr"] for row in rows),
            "total_ebitda_pkr": math.fsum(row["ebitda_pkr"] for row in rows),
            "total_capex_pkr": math.fsum(row["capex_pkr"] for row in rows),
            "total_fcf_pkr": math.fsum(row["fcf_pkr"] for row in rows),
        }
    except OverflowError as error:
        raise ValueError("values: non-finite output from aggregate overflow") from error
    for key, value in values.items():
        if not math.isfinite(value):
            raise ValueError(f"values.{key}: non-finite output")
    shares = float(case["inputs"]["shares_out"]["value"])
    per_share_npv = values["npv_pkr"] / shares
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
                "baseline gross margin applies to starting revenue; incremental costs are explicit fuel, power and freight per unit",
                "utilization is zero before commissioning and follows the supplied absolute quarterly ramp thereafter",
                "depreciation, capex, fixed costs and financing schedules are explicit; debt principal amortization is not modeled",
                "tax is an effective cash-tax rate on positive quarterly earnings before tax; no loss carryforward or tax shield detail",
                "working capital is a percentage of revenue; no terminal value or salvage value is modeled",
                "EPS is quarterly net income per explicit share count; no dilution or statutory adjustments",
                "ROIC is quarterly NOPAT divided by debt plus equity financing",
                "cases are isolated bear/base/bull scenarios; no scenario weighting is performed",
                "discounting uses end-of-quarter timing from valuation_date",
            ],
        },
    }


def _inputs_lineage(inputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for field in sorted(inputs, key=str):
        record = inputs[field]
        entry: dict[str, Any] = {
            "field": field,
            "value": copy.deepcopy(record.get("value")),
            "label_type": record.get("label_type"),
            "available_on": record.get("available_on"),
        }
        if record.get("label_type") == "source":
            entry["source_ref"] = copy.deepcopy(record.get("source_ref"))
        else:
            entry["analyst_ref"] = copy.deepcopy(record.get("analyst_ref"))
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
