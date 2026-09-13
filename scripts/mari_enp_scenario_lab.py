"""MARI E&P scenario lab and market-expectations gap kernel.

Builds on mari_enp_valuation_engine. Isolated bear/base/bull cases, two 3x3
sensitivity grids, and a reverse-solved discovery probability implied by an
explicit market premium. Research arithmetic only: no LLM, no advice, no
invented operands. Retained MARI state stays fail-closed until financial
truth is qualified and every assumption is present and approved.
"""
from __future__ import annotations

from typing import Any, Mapping
import copy
import hashlib
import json
import math
from pathlib import Path

from psx_data import ROOT, STATE, load_json, save_json
import mari_enp_valuation_engine as nav

ENGINE_VERSION = "mari_enp_scenario_lab_v1"
FORMULA_ID = "enp_exploration.scenario_lab.v1"
GAP_FORMULA_ID = "enp_exploration.expectations_gap.v1"
RESULT_SCHEMA = "mari_enp_scenario_lab_result_v1"
CASE_ID = nav.CASE_ID
SYMBOL = nav.SYMBOL
CASE_FAMILY = nav.CASE_FAMILY
OUT = STATE / "company_intel" / "mari_enp_scenario_lab.json"

STATUS_COMPUTED = "computed"
STATUS_TRUTH = "blocked_financial_truth_not_qualified"
STATUS_MISSING = "blocked_missing_inputs"

SCENARIO_LABELS = ("bear", "base", "bull")
RESERVE_LABELS = ("low", "base", "high")
SCENARIO_FIELDS = (
    "recoverable_scenario",
    "commodity_price_factor",
    "discount_rate",
    "geological_success_probability",
    "commercial_success_probability",
)
GRID_COMMODITY_KEYS = ("commodity_price_factors", "reserve_scenarios")
GRID_SUCCESS_KEYS = ("discount_rates", "success_probabilities")
SUMMARY_KEYS = (
    "p_disc",
    "dry_hole_cost_pkr",
    "unrisked_npv_pkr",
    "risked_npv_pkr",
    "per_share_risked_pkr",
    "per_share_unrisked_pkr",
)
ENVELOPE_KEYS = (
    "schema_version",
    "formula_id",
    "gap_formula_id",
    "engine_version",
    "valuation_engine_version",
    "case_id",
    "symbol",
    "case_family",
    "status",
    "blocked_reasons",
    "missing_inputs",
    "financial_truth_status",
    "assumptions_approved",
    "run_receipt",
    "scenarios",
    "grids",
    "expectations_gap",
    "confidence_limitations",
    "policy",
)


def _finite(value: Any) -> float | None:
    return nav._finite(value)


def _safe(value: Any) -> Any:
    return nav._safe(value)


def _premium_pkr_per_share(market: Mapping[str, Any]) -> tuple[float | None, list[str]]:
    if type(market) is not dict:
        return None, ["market"]
    if "market_premium_pkr_per_share" in market:
        premium = _finite(market["market_premium_pkr_per_share"])
        if premium is None:
            return None, ["market_premium_pkr_per_share"]
        return premium, []
    latest = _finite(market.get("latest_price_pkr"))
    undisturbed = _finite(market.get("undisturbed_price_pkr"))
    missing = []
    if latest is None or latest <= 0.0:
        missing.append("latest_price_pkr")
    if undisturbed is None or undisturbed <= 0.0:
        missing.append("undisturbed_price_pkr")
    if missing:
        return None, missing
    return _safe(latest - undisturbed), []


def validate_lab_case(case: Mapping[str, Any]) -> list[str]:
    if type(case) is not dict:
        return ["case: must be an exact mapping"]
    violations: list[str] = []
    assumptions = case.get("assumptions")
    if type(assumptions) is not dict:
        violations.append("assumptions: must be an exact mapping")
    else:
        violations.extend(nav.validate_assumptions(assumptions))
    scenarios = case.get("scenarios")
    if type(scenarios) is not dict:
        violations.append("scenarios: must be a mapping of bear/base/bull")
    else:
        if tuple(sorted(scenarios)) != tuple(sorted(SCENARIO_LABELS)):
            violations.append("scenarios: must contain exactly bear, base, bull")
        for label in SCENARIO_LABELS:
            row = scenarios.get(label)
            if type(row) is not dict:
                violations.append(f"scenarios.{label}: must be a mapping")
                continue
            extra = set(row) - set(SCENARIO_FIELDS)
            if extra:
                violations.append(f"scenarios.{label}: unknown field")
            for field in SCENARIO_FIELDS:
                if field not in row:
                    violations.append(f"scenarios.{label}.{field}: missing required input")
            if row.get("recoverable_scenario") not in RESERVE_LABELS:
                violations.append(f"scenarios.{label}.recoverable_scenario: must be low, base or high")
            factor = _finite(row.get("commodity_price_factor"))
            if factor is None or not (0.0 < factor <= 5.0):
                violations.append(f"scenarios.{label}.commodity_price_factor: must be in (0, 5]")
            rate = _finite(row.get("discount_rate"))
            if rate is None or not (0.0 < rate < 1.0):
                violations.append(f"scenarios.{label}.discount_rate: must be in (0, 1)")
            pg = _finite(row.get("geological_success_probability"))
            pc = _finite(row.get("commercial_success_probability"))
            if pg is None or not (0.0 < pg <= 1.0):
                violations.append(f"scenarios.{label}.geological_success_probability: must be in (0, 1]")
            if pc is None or not (0.0 < pc <= 1.0):
                violations.append(f"scenarios.{label}.commercial_success_probability: must be in (0, 1]")
    grids = case.get("grids")
    if type(grids) is not dict:
        violations.append("grids: must be a mapping")
    else:
        commodity = grids.get("commodity_vs_reserves")
        success = grids.get("discount_vs_success")
        violations.extend(_validate_commodity_grid(commodity))
        violations.extend(_validate_success_grid(success))
        extra = set(grids) - {"commodity_vs_reserves", "discount_vs_success"}
        if extra:
            violations.append("grids: unknown field")
    if "market" in case:
        premium, missing = _premium_pkr_per_share(case.get("market") or {})
        if missing:
            violations.extend(f"market.{name}: missing or invalid" for name in missing)
        elif premium is not None and abs(premium) > 1.0e9:
            violations.append("market: premium per share exceeds bound")
    return violations


def _validate_commodity_grid(grid: Any) -> list[str]:
    if type(grid) is not dict:
        return ["grids.commodity_vs_reserves: must be a mapping"]
    violations: list[str] = []
    if set(grid) - set(GRID_COMMODITY_KEYS):
        violations.append("grids.commodity_vs_reserves: unknown field")
    factors = grid.get("commodity_price_factors")
    reserves = grid.get("reserve_scenarios")
    if type(factors) is not list or len(factors) != 3:
        violations.append("grids.commodity_vs_reserves.commodity_price_factors: must be three factors")
    else:
        parsed = [_finite(item) for item in factors]
        if any(item is None or not (0.0 < item <= 5.0) for item in parsed):
            violations.append("grids.commodity_vs_reserves.commodity_price_factors: must be finite in (0, 5]")
    if type(reserves) is not list or len(reserves) != 3:
        violations.append("grids.commodity_vs_reserves.reserve_scenarios: must be three labels")
    elif any(item not in RESERVE_LABELS for item in reserves):
        violations.append("grids.commodity_vs_reserves.reserve_scenarios: must be low, base or high")
    return violations


def _validate_success_grid(grid: Any) -> list[str]:
    if type(grid) is not dict:
        return ["grids.discount_vs_success: must be a mapping"]
    violations: list[str] = []
    if set(grid) - set(GRID_SUCCESS_KEYS):
        violations.append("grids.discount_vs_success: unknown field")
    rates = grid.get("discount_rates")
    probs = grid.get("success_probabilities")
    if type(rates) is not list or len(rates) != 3:
        violations.append("grids.discount_vs_success.discount_rates: must be three rates")
    else:
        parsed = [_finite(item) for item in rates]
        if any(item is None or not (0.0 < item < 1.0) for item in parsed):
            violations.append("grids.discount_vs_success.discount_rates: must be finite in (0, 1)")
    if type(probs) is not list or len(probs) != 3:
        violations.append("grids.discount_vs_success.success_probabilities: must be three probabilities")
    else:
        parsed = [_finite(item) for item in probs]
        if any(item is None or not (0.0 < item <= 1.0) for item in parsed):
            violations.append("grids.discount_vs_success.success_probabilities: must be finite in (0, 1]")
    return violations


def apply_price_factor(assumptions: Mapping[str, Any], factor: float) -> dict[str, Any]:
    out = copy.deepcopy(dict(assumptions))
    out["oil_price_usd_bbl"] = _safe(float(assumptions["oil_price_usd_bbl"]) * factor)
    out["gas_price_usd_mmbtu"] = _safe(float(assumptions["gas_price_usd_mmbtu"]) * factor)
    out.pop("market_premium_pkr_per_share", None)
    return out


def apply_scenario_params(assumptions: Mapping[str, Any], params: Mapping[str, Any]) -> dict[str, Any]:
    out = apply_price_factor(assumptions, float(params["commodity_price_factor"]))
    out["scenario"] = params["recoverable_scenario"]
    out["discount_rate"] = float(params["discount_rate"])
    out["geological_success_probability"] = float(params["geological_success_probability"])
    out["commercial_success_probability"] = float(params["commercial_success_probability"])
    return out


def _summary(result: Mapping[str, Any]) -> dict[str, Any]:
    values = result["values"]
    per_share = result["per_share"]
    return _safe(
        {
            "p_disc": values["p_disc"],
            "dry_hole_cost_pkr": values["dry_hole_cost_pkr"],
            "unrisked_npv_pkr": values["unrisked_npv_pkr"],
            "risked_npv_pkr": values["risked_npv_pkr"],
            "per_share_risked_pkr": per_share["risked_pkr"],
            "per_share_unrisked_pkr": per_share["unrisked_pkr"],
        }
    )


def _cell_from_assumptions(assumptions: Mapping[str, Any]) -> dict[str, Any]:
    violations = nav.validate_assumptions(assumptions)
    if violations:
        return {
            "status": STATUS_MISSING,
            "blocked_reasons": violations,
            "values": None,
        }
    computed = nav.compute_valuation(assumptions)
    return {"status": STATUS_COMPUTED, "blocked_reasons": [], "values": _summary(computed)}


def run_scenarios(assumptions: Mapping[str, Any], scenarios: Mapping[str, Any]) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for label in SCENARIO_LABELS:
        params = scenarios[label]
        cell = _cell_from_assumptions(apply_scenario_params(assumptions, params))
        rows[label] = {
            "label": label,
            "parameters": {field: copy.deepcopy(params[field]) for field in SCENARIO_FIELDS},
            "p_disc": _safe(float(params["geological_success_probability"]) * float(params["commercial_success_probability"])),
            **cell,
        }
    return rows


def run_commodity_grid(assumptions: Mapping[str, Any], grid: Mapping[str, Any]) -> dict[str, Any]:
    factors = [float(item) for item in grid["commodity_price_factors"]]
    reserves = list(grid["reserve_scenarios"])
    cells = []
    for reserve in reserves:
        row = []
        for factor in factors:
            mutated = apply_price_factor(assumptions, factor)
            mutated["scenario"] = reserve
            cell = _cell_from_assumptions(mutated)
            row.append(
                {
                    "recoverable_scenario": reserve,
                    "commodity_price_factor": factor,
                    **cell,
                }
            )
        cells.append(row)
    return {
        "row_axis": {"name": "recoverable_reserves", "values": reserves},
        "col_axis": {"name": "commodity_price_factor", "values": factors},
        "cells": cells,
    }


def run_success_grid(assumptions: Mapping[str, Any], grid: Mapping[str, Any]) -> dict[str, Any]:
    rates = [float(item) for item in grid["discount_rates"]]
    probs = [float(item) for item in grid["success_probabilities"]]
    cells = []
    for p_disc in probs:
        row = []
        for rate in rates:
            mutated = copy.deepcopy(dict(assumptions))
            mutated.pop("market_premium_pkr_per_share", None)
            mutated["discount_rate"] = rate
            mutated["geological_success_probability"] = p_disc
            mutated["commercial_success_probability"] = 1.0
            cell = _cell_from_assumptions(mutated)
            row.append(
                {
                    "discount_rate": rate,
                    "success_probability": p_disc,
                    **cell,
                }
            )
        cells.append(row)
    return {
        "row_axis": {"name": "success_probability", "values": probs},
        "col_axis": {"name": "discount_rate", "values": rates},
        "cells": cells,
    }


def expectations_gap(base_values: Mapping[str, Any], p_base: float, market: Mapping[str, Any] | None, shares: float, fx: float) -> dict[str, Any]:
    if market is None:
        return {
            "status": STATUS_MISSING,
            "formula_id": GAP_FORMULA_ID,
            "p_base": p_base,
            "p_market": None,
            "delta": None,
            "market_premium_pkr_per_share": None,
            "blocked_reasons": ["market: missing"],
            "missing_inputs": ["market"],
        }
    premium_ps, missing = _premium_pkr_per_share(market)
    if missing or premium_ps is None:
        return {
            "status": STATUS_MISSING,
            "formula_id": GAP_FORMULA_ID,
            "p_base": p_base,
            "p_market": None,
            "delta": None,
            "market_premium_pkr_per_share": None,
            "blocked_reasons": [f"market.{name}: missing or invalid" for name in missing],
            "missing_inputs": missing,
        }
    unrisked_usd = float(base_values["unrisked_npv_pkr"]) / fx
    dry_usd = float(base_values["dry_hole_cost_pkr"]) / fx
    premium_usd = _safe(premium_ps * shares / fx)
    spread = _safe(unrisked_usd + dry_usd)
    if abs(spread) < 1e-12:
        return {
            "status": STATUS_MISSING,
            "formula_id": GAP_FORMULA_ID,
            "p_base": p_base,
            "p_market": None,
            "delta": None,
            "market_premium_pkr_per_share": premium_ps,
            "blocked_reasons": ["degenerate spread between unrisked NPV and dry-hole cost"],
            "missing_inputs": [],
        }
    p_market = _safe((premium_usd + dry_usd) / spread)
    if not 0.0 <= p_market <= 1.0:
        return {
            "status": STATUS_MISSING,
            "formula_id": GAP_FORMULA_ID,
            "p_base": p_base,
            "p_market": None,
            "delta": None,
            "market_premium_pkr_per_share": premium_ps,
            "blocked_reasons": ["market-implied discovery probability outside [0, 1]"],
            "missing_inputs": [],
        }
    return _safe(
        {
            "status": STATUS_COMPUTED,
            "formula_id": GAP_FORMULA_ID,
            "p_base": p_base,
            "p_market": p_market,
            "delta": _safe(p_market - p_base),
            "market_premium_pkr_per_share": premium_ps,
            "blocked_reasons": [],
            "missing_inputs": [],
        }
    )


def _limitations() -> dict[str, Any]:
    return {
        "research_only": True,
        "no_advice": True,
        "single_point_estimate": True,
        "simplifications": [
            "bear/base/bull are isolated cases; no probability weighting across the three labels",
            "commodity-price grid scales oil and gas prices by the same explicit factor",
            "success-probability grid applies P_disc directly as geological_success_probability with commercial_success_probability = 1",
            "P_market is reverse-solved from the base-case unrisked NPV, dry-hole cost and an explicit per-share premium",
            "grid and scenario outputs are summaries; full quarterly schedules remain in the valuation engine",
        ],
    }


def _policy() -> dict[str, Any]:
    return {
        "research_only": True,
        "no_advice": True,
        "no_order": True,
        "fail_closed_without_qualified_financial_truth": True,
        "fail_closed_without_approved_assumptions": True,
        "synthetic_numbers_not_written_to_retained_state": True,
    }


def _blank_envelope(
    status: str,
    reasons: list[str],
    missing: list[str],
    truth_status: str,
    approved: bool,
    identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    identity = identity or {}
    return {
        "schema_version": RESULT_SCHEMA,
        "formula_id": FORMULA_ID,
        "gap_formula_id": GAP_FORMULA_ID,
        "engine_version": ENGINE_VERSION,
        "valuation_engine_version": nav.ENGINE_VERSION,
        "case_id": identity.get("case_id") or CASE_ID,
        "symbol": identity.get("symbol") or SYMBOL,
        "case_family": CASE_FAMILY,
        "status": status,
        "blocked_reasons": sorted(set(str(reason) for reason in reasons if type(reason) is str and reason)),
        "missing_inputs": sorted(set(missing)),
        "financial_truth_status": truth_status,
        "assumptions_approved": approved,
        "run_receipt": {"inputs_sha256": None, "contract_version": ENGINE_VERSION},
        "scenarios": None,
        "grids": None,
        "expectations_gap": None,
        "confidence_limitations": _limitations(),
        "policy": _policy(),
    }


def evaluate_lab(case: Mapping[str, Any]) -> dict[str, Any]:
    """Gate, then emit isolated scenarios, 3x3 grids and the expectations gap."""
    if type(case) is not dict:
        return _blank_envelope(STATUS_MISSING, ["case: must be an exact mapping"], ["assumptions", "scenarios", "grids"], "unknown", False)
    truth_qualified = case.get("financial_truth_qualified") is True
    approved = case.get("assumptions_approved") is True
    identity = {"case_id": case.get("case_id") or CASE_ID, "symbol": case.get("symbol") or SYMBOL}
    assumptions = case.get("assumptions")
    if not truth_qualified or not approved:
        missing = []
        if type(assumptions) is not dict:
            missing.extend(nav.REQUIRED_FIELDS)
        else:
            missing.extend(field for field in nav.REQUIRED_FIELDS if field not in assumptions)
        if "scenarios" not in case:
            missing.append("scenarios")
        if "grids" not in case:
            missing.append("grids")
        reasons = []
        if not truth_qualified:
            reasons.append("financial_truth_not_qualified")
        if not approved:
            reasons.append("assumptions_unapproved")
        return _blank_envelope(
            STATUS_TRUTH,
            reasons,
            missing,
            "qualified" if truth_qualified else "not_qualified",
            approved,
            identity,
        )
    violations = validate_lab_case(case)
    if violations:
        missing = []
        if type(assumptions) is not dict:
            missing.extend(nav.REQUIRED_FIELDS)
        else:
            missing.extend(field for field in nav.REQUIRED_FIELDS if field not in assumptions)
        if type(case.get("scenarios")) is not dict:
            missing.append("scenarios")
        if type(case.get("grids")) is not dict:
            missing.append("grids")
        return _blank_envelope(STATUS_MISSING, violations, missing, "qualified", True, identity)

    scenarios = run_scenarios(assumptions, case["scenarios"])
    grids = {
        "commodity_vs_reserves": run_commodity_grid(assumptions, case["grids"]["commodity_vs_reserves"]),
        "discount_vs_success": run_success_grid(assumptions, case["grids"]["discount_vs_success"]),
    }
    base_row = scenarios["base"]
    if base_row["status"] != STATUS_COMPUTED or base_row["values"] is None:
        return _blank_envelope(STATUS_MISSING, base_row["blocked_reasons"], [], "qualified", True, identity)
    p_base = float(base_row["p_disc"])
    gap = expectations_gap(
        base_row["values"],
        p_base,
        case.get("market"),
        float(assumptions["fully_diluted_shares"]),
        float(assumptions["fx_pkr_usd"]),
    )
    canonical = json.dumps(
        {
            "assumptions": assumptions,
            "scenarios": case["scenarios"],
            "grids": case["grids"],
            "market": case.get("market"),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return _safe(
        {
            "schema_version": RESULT_SCHEMA,
            "formula_id": FORMULA_ID,
            "gap_formula_id": GAP_FORMULA_ID,
            "engine_version": ENGINE_VERSION,
            "valuation_engine_version": nav.ENGINE_VERSION,
            "case_id": identity["case_id"],
            "symbol": identity["symbol"],
            "case_family": CASE_FAMILY,
            "status": STATUS_COMPUTED,
            "blocked_reasons": [],
            "missing_inputs": [],
            "financial_truth_status": "qualified",
            "assumptions_approved": True,
            "run_receipt": {
                "inputs_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                "contract_version": ENGINE_VERSION,
            },
            "scenarios": scenarios,
            "grids": grids,
            "expectations_gap": gap,
            "confidence_limitations": _limitations(),
            "policy": _policy(),
        }
    )


def _mari_truth(root: Path | None = None) -> dict[str, Any]:
    payload = load_json((root or ROOT) / "state" / "company_intel" / "financial_truth_qualification.json", {})
    row = ((payload.get("companies") or {}).get(SYMBOL) or {})
    return row if type(row) is dict else {}


def _enp_assumptions_approved(root: Path | None = None) -> bool:
    payload = load_json((root or ROOT) / "state" / "company_intel" / "financial_engine_assumptions.json", {})
    records = payload.get("records") if type(payload) is dict else None
    if type(records) is not list:
        return False
    for record in records:
        if type(record) is not dict or record.get("symbol") != SYMBOL or record.get("approved") is not True:
            continue
        metric = str(record.get("metric") or record.get("assumption") or record.get("label") or "")
        if any(token in metric.lower() for token in ("enp", "peshawar", "working_interest", "risked_nav")):
            return True
    return False


def build_retained_lab(root: Path | None = None, *, write: bool = False) -> dict[str, Any]:
    """Fail-closed retained MARI envelope. Never invents grids or probabilities."""
    root = root or ROOT
    truth = _mari_truth(root)
    qualified = truth.get("status") == "qualified"
    approved = _enp_assumptions_approved(root)
    envelope = evaluate_lab(
        {
            "symbol": SYMBOL,
            "case_id": CASE_ID,
            "financial_truth_qualified": qualified,
            "assumptions_approved": approved,
            "assumptions": {},
        }
    )
    extra = ["no_model_ready_E_and_P_operands"]
    if not qualified:
        tie = truth.get("financial_tie_out") or {}
        extra.append("financial_truth_not_qualified: " + str(tie.get("reason") or "financial truth is not qualified"))
    if not approved:
        extra.append("assumptions_unapproved")
    envelope["blocked_reasons"] = sorted(set(list(envelope["blocked_reasons"]) + extra))
    envelope["missing_inputs"] = sorted(set(list(envelope["missing_inputs"]) + list(nav.REQUIRED_FIELDS) + ["scenarios", "grids", "market"]))
    if write:
        save_json(root / "state" / "company_intel" / "mari_enp_scenario_lab.json", envelope)
    return envelope


def build(*, write: bool = True) -> dict[str, Any]:
    return build_retained_lab(ROOT, write=write)


def main() -> None:
    envelope = build(write=True)
    print(f"mari_enp_scenario_lab: {envelope['status']} -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

