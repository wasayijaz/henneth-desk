"""MLCF cement-expansion scenario lab and market-expectations-gap engine
(Case B, Sections 12 & 14).

Builds directly on mlcf_cement_expansion_model: every scenario, sensitivity
cell, and expectations-gap computation is produced by calling that module's
own validate_case/evaluate_case -- this module never re-derives project
economics arithmetic. It only (a) transforms a single provenance-bound base
case into bear/bull variants and 3x3 sensitivity-grid variants via explicit,
bounded multipliers, and (b) reframes the base case's own price-implied
backsolve into a structured market-expectations-gap comparison against two
explicit reference utilization figures.

Fail-closed gate: evaluate_with_financial_truth_gate is the only entry point
a consumer should call. If the company's financial_truth_qualification.json
row is not qualified (per the shared
formal_financial_engines.financial_truth_is_qualified predicate), it returns
an identity-only envelope with status == "blocked_financial_truth_not_qualified"
and withholds every scenario, sensitivity, and expectations-gap number.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from datetime import date
from typing import Any, Mapping

import mlcf_cement_expansion_model as expansion_model
from formal_financial_engines import financial_truth_is_qualified
from psx_data import STATE, load_json, save_json

MODULE_VERSION = "mlcf_cement_scenario_lab_v1"
FORMULA_ID = "mlcf_cement_scenario_lab.scenario_sensitivity_and_expectations_gap.v1"
RESULT_SCHEMA = "mlcf_cement_scenario_lab_result_v1"
SCENARIO_LABELS = ("bear", "base", "bull")
GRID_STEPS = (-1, 0, 1)  # low, base, high -- applied as -step/0/+step around base

FINANCIAL_TRUTH_PATH = STATE / "company_intel" / "financial_truth_qualification.json"
OUTPUT_PATH = STATE / "company_intel" / "mlcf_cement_scenario_lab.json"

# ---------------------------------------------------------------------------
# Input contract
# ---------------------------------------------------------------------------

_SCENARIO_MULTIPLIER_FIELDS = {
    "ramp_scale_pct": (0.0, False, 300.0, True),
    "price_scale_pct": (0.0, False, 300.0, True),
    "fuel_cost_scale_pct": (0.0, False, 500.0, True),
    "power_cost_scale_pct": (0.0, False, 500.0, True),
    "raw_materials_cost_scale_pct": (0.0, False, 500.0, True),
}
_SCENARIO_MULTIPLIER_DELTA_FIELDS = {
    "wacc_delta_pct_points": (-20.0, True, 20.0, True),
}
_GRID_CONFIG_FIELDS = {
    "price_axis_step_pct": (0.0, False, 100.0, True),
    "coal_cost_axis_step_pct": (0.0, False, 100.0, True),
    "ramp_axis_step_pct": (0.0, False, 100.0, True),
    "wacc_axis_step_pct_points": (0.0, False, 20.0, True),
}
_GAP_INPUT_FIELDS = {
    "henneth_base_case_utilization_pct": (0.0, True, 100.0, True),
    "historical_comparable_median_utilization_pct": (0.0, True, 100.0, True),
}
_REQUIRED_SCENARIO_SCALARS = ("bear", "bull")


def _as_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


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


def _in_bounds(number: float, low: float, low_inc: bool, high: float, high_inc: bool) -> bool:
    return (number > low or (low_inc and number == low)) and (
        number < high or (high_inc and number == high)
    )


def _bounds_text(low: float, low_inc: bool, high: float, high_inc: bool) -> str:
    left = "[" if low_inc else "("
    right = "]" if high_inc else ")"
    fmt = lambda n: int(n) if float(n).is_integer() else n
    return f"{left}{fmt(low)}, {fmt(high)}{right}"


def _validate_bounded_record(prefix: str, field: str, record: Any, bounds: tuple,
                              valuation: date) -> list[str]:
    violations: list[str] = []
    label = f"{prefix}.{field}"
    if not isinstance(record, Mapping):
        return [f"{label}: input must be a provenance record mapping"]
    if not expansion_model.cement.provenance_ok(record):
        violations.append(f"{label}: provenance record must carry label_type and a complete reference")
    available_on = _as_date(record.get("available_on"))
    if available_on is None:
        violations.append(f"{label}: available_on must be an ISO date (YYYY-MM-DD)")
    elif available_on > valuation:
        violations.append(f"{label}: available_on must be on or before valuation_date")
    low, low_inc, high, high_inc = bounds
    number = _finite(record.get("value"))
    if number is None:
        violations.append(f"{label}: must be a finite number (booleans are not numbers)")
    elif not _in_bounds(number, low, low_inc, high, high_inc):
        violations.append(f"{label}: must be in {_bounds_text(low, low_inc, high, high_inc)}")
    return violations


def validate_case(case: Mapping[str, Any]) -> list[str]:
    """Return named violations; an empty list means the lab case is valid."""
    if not isinstance(case, Mapping):
        return ["case: must be a mapping"]
    violations: list[str] = []
    for field in ("symbol", "project_name", "event_ref"):
        if not _nonempty(case.get(field)):
            violations.append(f"{field}: must be a non-empty string")
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

    base_inputs = case.get("base_case_inputs")
    if not isinstance(base_inputs, Mapping):
        violations.append("base_case_inputs: must be a mapping of field to provenance record")
    else:
        base_wrapper = {
            "symbol": case.get("symbol"),
            "project_name": case.get("project_name"),
            "event_ref": f"{case.get('event_ref')}:base",
            "case_label": "base",
            "effective_date": case.get("effective_date"),
            "valuation_date": case.get("valuation_date"),
            "inputs": base_inputs,
        }
        for violation in expansion_model.validate_case(base_wrapper):
            violations.append(f"base_case_inputs.{violation}")

    multipliers = case.get("scenario_multipliers")
    if not isinstance(multipliers, Mapping):
        violations.append("scenario_multipliers: must be a mapping of bear/bull to multiplier records")
    else:
        for scenario in _REQUIRED_SCENARIO_SCALARS:
            block = multipliers.get(scenario)
            prefix = f"scenario_multipliers.{scenario}"
            if not isinstance(block, Mapping):
                violations.append(f"{prefix}: must be a mapping of multiplier field to provenance record")
                continue
            all_fields = dict(_SCENARIO_MULTIPLIER_FIELDS) | dict(_SCENARIO_MULTIPLIER_DELTA_FIELDS)
            for field in sorted(set(block) - set(all_fields), key=str):
                violations.append(f"{prefix}.{field}: unknown multiplier field")
            for field, bounds in all_fields.items():
                if field not in block:
                    violations.append(f"{prefix}.{field}: missing required multiplier")
                    continue
                violations.extend(_validate_bounded_record(prefix, field, block[field], bounds, valuation))

    grid_config = case.get("sensitivity_grid_config")
    if not isinstance(grid_config, Mapping):
        violations.append("sensitivity_grid_config: must be a mapping of axis-step field to provenance record")
    else:
        for field in sorted(set(grid_config) - set(_GRID_CONFIG_FIELDS), key=str):
            violations.append(f"sensitivity_grid_config.{field}: unknown grid-config field")
        for field, bounds in _GRID_CONFIG_FIELDS.items():
            if field not in grid_config:
                violations.append(f"sensitivity_grid_config.{field}: missing required grid-config input")
                continue
            violations.extend(_validate_bounded_record("sensitivity_grid_config", field, grid_config[field], bounds, valuation))

    gap_inputs = case.get("expectations_gap_inputs")
    if not isinstance(gap_inputs, Mapping):
        violations.append("expectations_gap_inputs: must be a mapping of reference-utilization field to provenance record")
    else:
        for field in sorted(set(gap_inputs) - set(_GAP_INPUT_FIELDS), key=str):
            violations.append(f"expectations_gap_inputs.{field}: unknown expectations-gap field")
        for field, bounds in _GAP_INPUT_FIELDS.items():
            if field not in gap_inputs:
                violations.append(f"expectations_gap_inputs.{field}: missing required expectations-gap input")
                continue
            violations.extend(_validate_bounded_record("expectations_gap_inputs", field, gap_inputs[field], bounds, valuation))

    return violations


# ---------------------------------------------------------------------------
# Deterministic transforms -- reuse expansion_model.evaluate_case for all math
# ---------------------------------------------------------------------------

def _record(value: Any, note: str, available_on: str) -> dict[str, Any]:
    return {
        "value": value,
        "label_type": "analyst",
        "analyst_ref": {"note_id": "note:mlcf-cement-scenario-lab:transform", "note": note},
        "available_on": available_on,
    }


def _transform_inputs(base_inputs: Mapping[str, Any], *, ramp_scale_pct: float = 100.0,
                       price_scale_pct: float = 100.0, fuel_cost_scale_pct: float = 100.0,
                       power_cost_scale_pct: float = 100.0, raw_materials_cost_scale_pct: float = 100.0,
                       wacc_delta_pct_points: float = 0.0, note: str) -> dict[str, Any]:
    """Return a deep-copied, scaled inputs mapping. Identity multipliers
    (100.0 / 0.0) leave the corresponding field byte-identical to the base."""
    inputs = copy.deepcopy(dict(base_inputs))

    def scale_schedule(field: str, factor: float, *, cap_pct: bool = False) -> None:
        record = inputs[field]
        scaled = [min(float(v) * factor, 100.0) if cap_pct else float(v) * factor for v in record["value"]]
        inputs[field] = _record(scaled, note, record["available_on"])

    scale_schedule("ramp_pct_schedule", ramp_scale_pct / 100.0, cap_pct=True)
    scale_schedule("selling_price_pkr_per_ton_schedule", price_scale_pct / 100.0)
    scale_schedule("fuel_cost_pkr_per_ton_schedule", fuel_cost_scale_pct / 100.0)
    scale_schedule("power_cost_pkr_per_ton_schedule", power_cost_scale_pct / 100.0)
    scale_schedule("raw_materials_cost_pkr_per_ton_schedule", raw_materials_cost_scale_pct / 100.0)

    wacc_record = inputs["valuation_discount_rate_pct_annual"]
    inputs["valuation_discount_rate_pct_annual"] = _record(
        float(wacc_record["value"]) + wacc_delta_pct_points, note, wacc_record["available_on"]
    )
    return inputs


def _full_case(identity: Mapping[str, Any], inputs: Mapping[str, Any], case_label: str,
                event_ref_suffix: str) -> dict[str, Any]:
    return {
        "symbol": identity["symbol"],
        "project_name": identity["project_name"],
        "event_ref": f"{identity['event_ref']}:{event_ref_suffix}",
        "case_label": case_label,
        "effective_date": identity["effective_date"],
        "valuation_date": identity["valuation_date"],
        "inputs": inputs,
    }


def _multiplier_values(block: Mapping[str, Any]) -> dict[str, float]:
    return {field: float(record["value"]) for field, record in block.items()}


def build_scenario_cases(case: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Build bear/base/bull full cases from the base case plus explicit
    bounded multipliers. Base always uses identity multipliers (100/0)."""
    identity = case
    base_inputs = case["base_case_inputs"]
    cases: dict[str, dict[str, Any]] = {
        "base": _full_case(identity, copy.deepcopy(dict(base_inputs)), "base", "base"),
    }
    for scenario in ("bear", "bull"):
        multipliers = _multiplier_values(case["scenario_multipliers"][scenario])
        transformed = _transform_inputs(
            base_inputs,
            ramp_scale_pct=multipliers["ramp_scale_pct"],
            price_scale_pct=multipliers["price_scale_pct"],
            fuel_cost_scale_pct=multipliers["fuel_cost_scale_pct"],
            power_cost_scale_pct=multipliers["power_cost_scale_pct"],
            raw_materials_cost_scale_pct=multipliers["raw_materials_cost_scale_pct"],
            wacc_delta_pct_points=multipliers["wacc_delta_pct_points"],
            note=f"{scenario} scenario multiplier applied to the source-bound base case",
        )
        cases[scenario] = _full_case(identity, transformed, scenario, scenario)
    return cases


def summarize_scenario(result: Mapping[str, Any]) -> dict[str, Any]:
    operating_rows = result["operating_schedule"]
    average_utilization_pct = math.fsum(row["utilization_pct"] for row in operating_rows) / len(operating_rows)
    return {
        "case_label": result["project"]["case_label"],
        "fair_value_impact_per_share_pkr": result["valuation"]["fair_value_impact_per_share_pkr"],
        "project_dcf_npv_pkr": result["valuation"]["project_dcf_npv_pkr"],
        "total_project_value_pkr": result["valuation"]["total_project_value_pkr"],
        "terminal_annualized_ebitda_pkr": result["valuation"]["terminal_annualized_ebitda_pkr"],
        "average_operating_utilization_pct": average_utilization_pct,
        "accounting_integrity_balanced": result["accounting_integrity"]["balanced"],
    }


def run_scenarios(case: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate bear/base/bull; raises ValueError if any variant is invalid."""
    scenario_cases = build_scenario_cases(case)
    results = {label: expansion_model.evaluate_case(scenario_cases[label]) for label in SCENARIO_LABELS}
    summaries = {label: summarize_scenario(results[label]) for label in SCENARIO_LABELS}
    return {"results": results, "summaries": summaries}


def _grid_cell_value(base_inputs: Mapping[str, Any], identity: Mapping[str, Any], *,
                      ramp_scale_pct: float = 100.0, price_scale_pct: float = 100.0,
                      fuel_cost_scale_pct: float = 100.0, power_cost_scale_pct: float = 100.0,
                      raw_materials_cost_scale_pct: float = 100.0, wacc_delta_pct_points: float = 0.0,
                      note: str, event_ref_suffix: str) -> float:
    inputs = _transform_inputs(
        base_inputs, ramp_scale_pct=ramp_scale_pct, price_scale_pct=price_scale_pct,
        fuel_cost_scale_pct=fuel_cost_scale_pct, power_cost_scale_pct=power_cost_scale_pct,
        raw_materials_cost_scale_pct=raw_materials_cost_scale_pct,
        wacc_delta_pct_points=wacc_delta_pct_points, note=note,
    )
    grid_case = _full_case(identity, inputs, "base", event_ref_suffix)
    return expansion_model.evaluate_case(grid_case)["valuation"]["fair_value_impact_per_share_pkr"]


def build_price_vs_variable_cost_grid(case: Mapping[str, Any]) -> dict[str, Any]:
    """Rows: selling price step. Columns: variable/coal cost step (applied
    uniformly to fuel, power and raw-materials cost per ton)."""
    base_inputs = case["base_case_inputs"]
    price_step = float(case["sensitivity_grid_config"]["price_axis_step_pct"]["value"])
    cost_step = float(case["sensitivity_grid_config"]["coal_cost_axis_step_pct"]["value"])
    row_values = [100.0 + price_step * step for step in GRID_STEPS]
    col_values = [100.0 + cost_step * step for step in GRID_STEPS]
    cells: list[list[float]] = []
    for r_index, price_scale in enumerate(row_values):
        row: list[float] = []
        for c_index, cost_scale in enumerate(col_values):
            value = _grid_cell_value(
                base_inputs, case, price_scale_pct=price_scale,
                fuel_cost_scale_pct=cost_scale, power_cost_scale_pct=cost_scale,
                raw_materials_cost_scale_pct=cost_scale,
                note="price-vs-variable-cost sensitivity grid cell",
                event_ref_suffix=f"grid1:{r_index}:{c_index}",
            )
            row.append(value)
        cells.append(row)
    return {
        "grid_id": "selling_price_vs_variable_cost",
        "row_axis": {"name": "selling_price_pct_of_base", "values": row_values},
        "column_axis": {"name": "variable_cost_pct_of_base", "values": col_values},
        "fair_value_impact_per_share_pkr": cells,
    }


def build_ramp_vs_wacc_grid(case: Mapping[str, Any]) -> dict[str, Any]:
    """Rows: utilization-ramp step. Columns: WACC discount-rate step
    (percentage points, additive)."""
    base_inputs = case["base_case_inputs"]
    ramp_step = float(case["sensitivity_grid_config"]["ramp_axis_step_pct"]["value"])
    wacc_step = float(case["sensitivity_grid_config"]["wacc_axis_step_pct_points"]["value"])
    row_values = [100.0 + ramp_step * step for step in GRID_STEPS]
    col_values = [wacc_step * step for step in GRID_STEPS]
    cells: list[list[float]] = []
    for r_index, ramp_scale in enumerate(row_values):
        row: list[float] = []
        for c_index, wacc_delta in enumerate(col_values):
            value = _grid_cell_value(
                base_inputs, case, ramp_scale_pct=ramp_scale, wacc_delta_pct_points=wacc_delta,
                note="utilization-ramp-vs-wacc sensitivity grid cell",
                event_ref_suffix=f"grid2:{r_index}:{c_index}",
            )
            row.append(value)
        cells.append(row)
    return {
        "grid_id": "utilization_ramp_vs_wacc",
        "row_axis": {"name": "utilization_ramp_pct_of_base", "values": row_values},
        "column_axis": {"name": "wacc_delta_pct_points", "values": col_values},
        "fair_value_impact_per_share_pkr": cells,
    }


# ---------------------------------------------------------------------------
# Market expectations gap
# ---------------------------------------------------------------------------

_GAP_TOLERANCE_PCT_POINTS = 0.5


def _interpretation(gap_pct_points: float) -> str:
    if gap_pct_points > _GAP_TOLERANCE_PCT_POINTS:
        return "market_implied_more_optimistic"
    if gap_pct_points < -_GAP_TOLERANCE_PCT_POINTS:
        return "market_implied_less_optimistic"
    return "market_implied_in_line"


def compute_market_expectations_gap(case: Mapping[str, Any]) -> dict[str, Any]:
    """Reverse-engineer plant utilization and commissioning timing implied by
    the base case's own current_market_price_pkr_per_share input, then
    compare against two explicit reference utilization figures."""
    base_case = _full_case(case, copy.deepcopy(dict(case["base_case_inputs"])), "base", "base")
    construction_rows = expansion_model.construction_schedule(base_case)
    utilization_backsolve = expansion_model.backsolve_utilization_scale(base_case)
    delay_backsolve = expansion_model.backsolve_commissioning_delay_quarters(base_case)

    henneth_base = float(case["expectations_gap_inputs"]["henneth_base_case_utilization_pct"]["value"])
    historical_median = float(case["expectations_gap_inputs"]["historical_comparable_median_utilization_pct"]["value"])

    if utilization_backsolve["reachable"]:
        scale = utilization_backsolve["implied_utilization_scale_pct"] / 100.0
        implied_operating_rows = expansion_model.operating_schedule(base_case, construction_rows, utilization_scale=scale)
        market_implied_utilization_pct = math.fsum(
            row["utilization_pct"] for row in implied_operating_rows
        ) / len(implied_operating_rows)
    else:
        market_implied_utilization_pct = None

    gap_vs_henneth = (
        market_implied_utilization_pct - henneth_base if market_implied_utilization_pct is not None else None
    )
    gap_vs_historical = (
        market_implied_utilization_pct - historical_median if market_implied_utilization_pct is not None else None
    )

    return {
        "current_market_price_pkr_per_share": float(
            case["base_case_inputs"]["current_market_price_pkr_per_share"]["value"]
        ),
        "pre_expansion_fair_value_pkr_per_share": float(
            case["base_case_inputs"]["pre_expansion_fair_value_pkr_per_share"]["value"]
        ),
        "market_implied_incremental_value_per_share_pkr": utilization_backsolve["target_value_per_share_pkr"],
        "utilization_backsolve_reachable": utilization_backsolve["reachable"],
        "market_implied_utilization_pct": market_implied_utilization_pct,
        "henneth_base_case_utilization_pct": henneth_base,
        "historical_comparable_median_utilization_pct": historical_median,
        "gap_vs_henneth_base_case_pct_points": gap_vs_henneth,
        "gap_vs_historical_comparable_median_pct_points": gap_vs_historical,
        "market_implied_commissioning_delay_quarters": delay_backsolve["implied_commissioning_delay_quarters"],
        "commissioning_delay_absolute_gap_pkr": delay_backsolve["absolute_gap_pkr"],
        "interpretation": {
            "vs_henneth_base_case": _interpretation(gap_vs_henneth) if gap_vs_henneth is not None else "not_reachable",
            "vs_historical_comparable_median": _interpretation(gap_vs_historical) if gap_vs_historical is not None else "not_reachable",
        },
    }


# ---------------------------------------------------------------------------
# Envelope builders
# ---------------------------------------------------------------------------

def evaluate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Pure deterministic kernel: raises ValueError for any invalid case.

    Has no knowledge of financial-truth qualification; callers that must
    respect the fail-closed gate use evaluate_with_financial_truth_gate.
    """
    violations = validate_case(case)
    if violations:
        raise ValueError("; ".join(violations))
    canonical = json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    scenarios = run_scenarios(case)
    price_vs_cost_grid = build_price_vs_variable_cost_grid(case)
    ramp_vs_wacc_grid = build_ramp_vs_wacc_grid(case)
    expectations_gap = compute_market_expectations_gap(case)
    return {
        "schema_version": RESULT_SCHEMA,
        "formula_id": FORMULA_ID,
        "module_version": MODULE_VERSION,
        "run_receipt": {
            "inputs_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "expansion_model_version": expansion_model.MODULE_VERSION,
        },
        "status": "computed",
        "blocked_reasons": [],
        "project": {
            "symbol": case["symbol"],
            "project_name": case["project_name"],
            "event_ref": case["event_ref"],
            "effective_date": case["effective_date"],
            "valuation_date": case["valuation_date"],
        },
        "scenario_lab": {
            "labels": list(SCENARIO_LABELS),
            "summaries": scenarios["summaries"],
            "full_results": scenarios["results"],
            "ordering_check": {
                "bear_le_base": scenarios["summaries"]["bear"]["fair_value_impact_per_share_pkr"]
                <= scenarios["summaries"]["base"]["fair_value_impact_per_share_pkr"],
                "base_le_bull": scenarios["summaries"]["base"]["fair_value_impact_per_share_pkr"]
                <= scenarios["summaries"]["bull"]["fair_value_impact_per_share_pkr"],
            },
        },
        "sensitivity_grids": {
            "selling_price_vs_variable_cost": price_vs_cost_grid,
            "utilization_ramp_vs_wacc": ramp_vs_wacc_grid,
        },
        "market_expectations_gap": expectations_gap,
        "confidence_limitations": {
            "research_only": True,
            "no_advice": True,
            "single_point_estimate": False,
            "simplifications": [
                "bear/bull scenarios and all sensitivity-grid cells are deterministic transforms of one source-bound base case via explicit, bounded multipliers; no independent evidence backs each scenario",
                "the variable-cost sensitivity axis scales fuel (coal proxy), power and raw-materials cost per ton uniformly by the same percentage",
                "the WACC sensitivity axis is an additive percentage-point shift on the base case's own discount rate",
                "the market-expectations gap treats (current_market_price - pre_expansion_fair_value) as the market-implied incremental equity value of this project only, then reframes the same utilization-scale backsolve as an average operating-quarter utilization percentage",
                "the two comparison references (Henneth base case, historical comparable median) are explicit caller-supplied inputs, not independently re-derived here",
                "cases are isolated bear/base/bull scenarios and grid cells; no probability weighting is performed",
            ],
        },
    }


def blocked_result(identity: Mapping[str, Any], reasons: list[str], *,
                    status: str = "blocked_invalid_inputs") -> dict[str, Any]:
    """Identity-only blocked envelope; no partial calculations leak."""
    return {
        "schema_version": RESULT_SCHEMA,
        "formula_id": FORMULA_ID,
        "module_version": MODULE_VERSION,
        "run_receipt": {"inputs_sha256": None, "expansion_model_version": expansion_model.MODULE_VERSION},
        "status": status,
        "blocked_reasons": sorted(set(str(reason) for reason in reasons)),
        "project": {
            "symbol": identity.get("symbol") if isinstance(identity, Mapping) else None,
            "project_name": identity.get("project_name") if isinstance(identity, Mapping) else None,
            "event_ref": identity.get("event_ref") if isinstance(identity, Mapping) else None,
            "effective_date": identity.get("effective_date") if isinstance(identity, Mapping) else None,
            "valuation_date": identity.get("valuation_date") if isinstance(identity, Mapping) else None,
        },
        "scenario_lab": None,
        "sensitivity_grids": None,
        "market_expectations_gap": None,
        "confidence_limitations": {
            "research_only": True,
            "no_advice": True,
            "single_point_estimate": False,
            "simplifications": ["blocked before calculation; missing, invalid, or unqualified inputs"],
        },
    }


def evaluate_with_financial_truth_gate(case: Mapping[str, Any],
                                        financial_truth_row: Mapping[str, Any]) -> dict[str, Any]:
    """The only entry point a consumer should call. Fails closed on both the
    financial-truth qualification gate and on invalid/malformed case inputs;
    never raises."""
    if not financial_truth_is_qualified(financial_truth_row):
        status = financial_truth_row.get("status") if isinstance(financial_truth_row, Mapping) else None
        return blocked_result(
            case if isinstance(case, Mapping) else {},
            [f"financial_truth_status:{status or 'missing'}"],
            status="blocked_financial_truth_not_qualified",
        )
    try:
        return evaluate_case(case)
    except ValueError as error:
        return blocked_result(
            case if isinstance(case, Mapping) else {},
            str(error).split("; "),
            status="blocked_invalid_inputs",
        )


# ---------------------------------------------------------------------------
# Build entry point
# ---------------------------------------------------------------------------

REAL_SYMBOL = expansion_model.REAL_SYMBOL
REAL_PROJECT_NAME = expansion_model.REAL_PROJECT_NAME
REAL_EVENT_REF = expansion_model.REAL_EVENT_REF
REAL_BASELINE_DATE = expansion_model.REAL_BASELINE_DATE


def _real_identity() -> dict[str, Any]:
    """Identity-only case shell for the real MLCF/PIOC lane. No project
    economics, scenario multipliers, grid config, or gap-reference inputs
    are populated: none are source-qualified for this case (see
    mlcf_pioc_case_run_adapter / build_mlcf_pioc_readiness_manifest), and the
    financial-truth gate below blocks live output before they would matter."""
    return {
        "symbol": REAL_SYMBOL,
        "project_name": REAL_PROJECT_NAME,
        "event_ref": REAL_EVENT_REF,
        "effective_date": REAL_BASELINE_DATE,
        "valuation_date": REAL_BASELINE_DATE,
    }


def build(*, write: bool = True, financial_truth: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build the real MLCF/PIOC scenario-lab state envelope. Blocks closed
    unless and until MLCF's financial_truth_qualification.json row is
    qualified."""
    truth_state = financial_truth if financial_truth is not None else load_json(
        FINANCIAL_TRUTH_PATH, {"companies": {}}
    )
    truth_row = (truth_state.get("companies") or {}).get(REAL_SYMBOL) or {}
    result = evaluate_with_financial_truth_gate(_real_identity(), truth_row)
    if write:
        save_json(OUTPUT_PATH, result)
    return result


def main() -> None:
    result = build(write=True)
    print(f"mlcf_cement_scenario_lab: status={result['status']}")


if __name__ == "__main__":
    main()
