"""Deterministic quarterly cash-flow engine for offshore E&P events.

Kernel scope (import-only): this module validates a case against
enp_event_contract, derives the merged quarterly cash-flow schedule and the
dry-hole / non-commercial / commercial outcome economics, and returns the
published result envelope.  It reads and writes no files, invents no inputs
and emits no timestamps, so identical cases produce byte-identical results.

Integration note for Terra's builder: map retained desk state into this
contract, call evaluate_case (or blocked_result when intake fails), emit the
envelope into generated state and wire desk gates around it.  Import this
kernel; never copy it.  Bear/base/bull arrive here as isolated cases -- any
weighting across them belongs to the existing impact engine, not here.

Outcome branches:

- dry_hole_npv        = -PV(exploration + appraisal spend)
                        - PV(consideration when non-recoverable)
- unrisked commercial = PV(entire spend schedule + non-recoverable
                        consideration + production net cash flows)
- risked_npv          = p * commercial + (1 - p) * dry, with
                        p = geological% * commercial% / 10,000

Non-recoverable consideration is a cost in both outcome branches; a
recoverable consideration is excluded from both (it returns in every state).

Discounting: end-of-quarter timing.  The quarterly factor is
(1 + r/100) ** 0.25 - 1 and each cash flow carries the exponent
n = 4 * (Q.year - V.year) + (Q.month // 3 - V.month // 3) where Q is the
cash-flow quarter-end and V the valuation date.  A negative n compounds a
pre-valuation cash flow forward to the valuation date.

Production: quarter k (0-based from first production) produces
initial * (1 - decline/100) ** k boe/d multiplied by the actual calendar
days of that quarter.  The value of one boe blends the oil share at the oil
price with the gas share at the gas price times the caller-supplied
boe-to-mmbtu conversion.  Working interest scales revenue and opex; spend
schedule amounts are already the company's working-interest share.

outcome_class is "commercial" when the unrisked commercial NPV is positive,
else "non_commercial".  The "dry_hole" outcome label is reserved for
builder-level pre-drill rows; this engine never emits it because within a
valued case the dry-hole branch is always computable.

Research arithmetic only.  Research outputs, no advice, no promises.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from typing import Any, Mapping

import enp_event_contract as contract

ENGINE_VERSION = "enp_event_engine_v1"
FORMULA_ID = "enp_exploration.risked_cashflow.v1"
RESULT_SCHEMA = "enp_event_model_result_v1"

_QUARTER_LAST_DAY = {3: 31, 6: 30, 9: 30, 12: 31}
_DRY_HOLE_PHASES = ("exploration", "appraisal", "consideration")


def _as_date(value: Any) -> date:
    return date.fromisoformat(str(value))


def _next_quarter_end(quarter_end: date) -> date:
    year, month = quarter_end.year, quarter_end.month + 3
    if month > 12:
        year += 1
        month -= 12
    return date(year, month, _QUARTER_LAST_DAY[month])


def _previous_quarter_end(quarter_end: date) -> date:
    if quarter_end.month == 3:
        return date(quarter_end.year - 1, 12, 31)
    return date(quarter_end.year, quarter_end.month - 3, _QUARTER_LAST_DAY[quarter_end.month - 3])


def _days_in_quarter(quarter_end: date) -> int:
    return (quarter_end - _previous_quarter_end(quarter_end)).days


def _discount_exponent(quarter_end: date, valuation: date) -> int:
    return 4 * (quarter_end.year - valuation.year) + (quarter_end.month // 3 - valuation.month // 3)


def _schedule(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    inputs = case["inputs"]
    valuation = _as_date(case["valuation_date"])
    annual_pct = float(inputs["discount_rate_pct_annual"]["value"])
    quarterly_rate = (1.0 + annual_pct / 100.0) ** 0.25 - 1.0

    def make_row(quarter_end: date, phase: str, production: float | None, gross: float,
                 royalty: float, opex: float, tax: float, net: float) -> dict[str, Any]:
        exponent = _discount_exponent(quarter_end, valuation)
        factor = (1.0 + quarterly_rate) ** (-exponent)
        return {
            "quarter_end": quarter_end.isoformat(),
            "phase": phase,
            "production_boe": production,
            "gross_revenue_pkr": gross,
            "royalty_pkr": royalty,
            "opex_pkr": opex,
            "tax_pkr": tax,
            "net_cash_flow_pkr": net,
            "discount_factor": factor,
            "discounted_cash_flow_pkr": net * factor,
        }

    rows: list[dict[str, Any]] = []
    for spend in inputs["spend_schedule"]["value"]:
        quarter_end = _as_date(spend["quarter_end"])
        amount = float(spend["amount_pkr"])
        rows.append(make_row(quarter_end, str(spend["phase"]), None, 0.0, 0.0, 0.0, 0.0, -amount))

    consideration = float(inputs["consideration_pkr"]["value"])
    non_recoverable = inputs.get("consideration_non_recoverable", {}).get("value") is True
    if consideration > 0.0 and non_recoverable:
        quarter_end = _as_date(inputs["consideration_quarter_end"]["value"])
        rows.append(make_row(quarter_end, "consideration", None, 0.0, 0.0, 0.0, 0.0, -consideration))

    working_interest = float(inputs["working_interest_pct"]["value"]) / 100.0
    initial_rate = float(inputs["initial_production_boe_pd"]["value"])
    decline = float(inputs["quarterly_decline_pct"]["value"]) / 100.0
    oil_share = float(inputs["oil_share_pct"]["value"]) / 100.0
    oil_price = float(inputs["oil_price_usd_bbl"]["value"])
    gas_price = float(inputs["gas_price_usd_mmbtu"]["value"])
    gas_per_boe = float(inputs["gas_mmbtu_per_boe"]["value"])
    fx = float(inputs["fx_pkr_usd"]["value"])
    opex_usd_boe = float(inputs["opex_usd_boe"]["value"])
    royalty_pct = float(inputs["royalty_pct"]["value"]) / 100.0
    tax_pct = float(inputs["effective_tax_pct"]["value"]) / 100.0
    value_per_boe_usd = oil_share * oil_price + (1.0 - oil_share) * gas_price * gas_per_boe

    quarter_end = _as_date(inputs["first_production_quarter_end"]["value"])
    horizon = int(inputs["production_horizon_quarters"]["value"])
    for k in range(horizon):
        rate_boe_pd = initial_rate * (1.0 - decline) ** k
        production_boe = rate_boe_pd * _days_in_quarter(quarter_end)
        gross = production_boe * working_interest * value_per_boe_usd * fx
        royalty = gross * royalty_pct
        opex = opex_usd_boe * production_boe * working_interest * fx
        operating_net = gross - royalty - opex
        tax = operating_net * tax_pct if operating_net > 0.0 else 0.0
        net = operating_net - tax
        rows.append(make_row(quarter_end, "production", production_boe, gross, royalty, opex, tax, net))
        quarter_end = _next_quarter_end(quarter_end)

    rows.sort(key=lambda row: (row["quarter_end"], row["phase"]))
    return rows


def _npvs(rows: list[dict[str, Any]]) -> tuple[float, float]:
    commercial = math.fsum(row["discounted_cash_flow_pkr"] for row in rows)
    dry_hole = math.fsum(
        row["discounted_cash_flow_pkr"] for row in rows if row["phase"] in _DRY_HOLE_PHASES
    )
    return commercial, dry_hole


def quarterly_cashflows(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Merged spend, consideration and production rows, end-of-quarter discounted."""
    violations = contract.validate_case(case)
    if violations:
        raise ValueError("; ".join(violations))
    return _schedule(case)


def break_even_success(commercial_npv: float, dry_hole_npv: float) -> tuple[float | None, str | None]:
    """Success probability at which the risked NPV is zero, as a percentage."""
    spread = commercial_npv - dry_hole_npv
    if abs(spread) < 1e-9:
        return None, "degenerate spread between commercial and dry-hole outcomes"
    probability = -dry_hole_npv / spread
    if not 0.0 < probability <= 1.0:
        return None, "break-even success probability outside (0, 1]"
    return probability * 100.0, None


def market_implied_success(commercial_npv: float, dry_hole_npv: float,
                           market_gap_pkr: float | None) -> tuple[float | None, str | None, list[str]]:
    """Success probability implied by a market gap, as a percentage."""
    if market_gap_pkr is None:
        return None, None, ["market_gap_pkr"]
    spread = commercial_npv - dry_hole_npv
    if abs(spread) < 1e-9:
        return None, "degenerate spread between commercial and dry-hole outcomes", []
    probability = (market_gap_pkr - dry_hole_npv) / spread
    note = None if 0.0 <= probability <= 1.0 else "market-implied success probability outside [0, 1]"
    return probability * 100.0, note, []


def risked_metrics(case: Mapping[str, Any]) -> dict[str, Any]:
    """Outcome classification, NPVs, probabilities and per-share values for a case."""
    violations = contract.validate_case(case)
    if violations:
        raise ValueError("; ".join(violations))
    return _metrics(case)


def _metrics(case: Mapping[str, Any]) -> dict[str, Any]:
    inputs = case["inputs"]
    commercial_npv, dry_hole_npv = _npvs(_schedule(case))
    geological = float(inputs["geological_success_pct"]["value"])
    commercial_chance = float(inputs["commercial_success_pct"]["value"])
    p_success = (geological / 100.0) * (commercial_chance / 100.0)
    risked = p_success * commercial_npv + (1.0 - p_success) * dry_hole_npv
    break_even_pct, break_even_note = break_even_success(commercial_npv, dry_hole_npv)
    gap_record = inputs.get("market_gap_pkr")
    gap = float(gap_record["value"]) if isinstance(gap_record, Mapping) else None
    implied_pct, implied_note, implied_missing = market_implied_success(commercial_npv, dry_hole_npv, gap)
    metrics: dict[str, Any] = {
        "outcome_class": "commercial" if commercial_npv > 0.0 else "non_commercial",
        "dry_hole_npv_pkr": dry_hole_npv,
        "unrisked_commercial_npv_pkr": commercial_npv,
        "risked_npv_pkr": risked,
        "p_success_pct": p_success * 100.0,
        "break_even_success_pct": break_even_pct,
        "break_even_note": break_even_note,
        "market_implied_success_pct": implied_pct,
        "market_implied_note": implied_note,
        "market_implied_missing": implied_missing,
    }
    shares_record = inputs.get("shares_out")
    if isinstance(shares_record, Mapping):
        shares = float(shares_record["value"])
        metrics["per_share"] = {
            "risked_pkr": risked / shares,
            "unrisked_pkr": commercial_npv / shares,
        }
    return metrics


def _confidence_limitations() -> dict[str, Any]:
    return {
        "research_only": True,
        "no_advice": True,
        "single_point_estimate": True,
        "simplifications": [
            "single analyst-labelled effective cash-tax rate on positive quarterly operating net revenue; no loss carryforward, no depreciation shield",
            "royalty charged on gross working-interest revenue; opex charged per working-interest boe",
            "end-of-quarter discounting at a caller-supplied annual effective rate; pre-valuation cash flows are compounded forward to the valuation date",
            "deterministic production decline; no price, cost or fx escalation over the horizon",
            "bear/base/bull are isolated cases; scenario weights belong to the impact engine, not this kernel",
            "spend schedule amounts are already the company working-interest share",
            "non-recoverable consideration is a cost in both dry-hole and commercial branches; recoverable consideration is excluded from both",
        ],
    }


def _inputs_lineage(inputs: Mapping[str, Any]) -> list[dict[str, Any]]:
    lineage: list[dict[str, Any]] = []
    for field in sorted(inputs):
        record = inputs[field]
        label_type = record.get("label_type")
        entry: dict[str, Any] = {
            "field": field,
            "value": record.get("value"),
            "label_type": label_type,
            "available_on": record.get("available_on"),
        }
        if label_type == "source":
            entry["source_ref"] = record.get("source_ref")
        else:
            entry["analyst_ref"] = record.get("analyst_ref")
        lineage.append(entry)
    return lineage


def _identity(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "symbol": case.get("symbol"),
        "event_ref": case.get("event_ref"),
        "case_label": case.get("case_label"),
        "effective_date": case.get("effective_date"),
        "valuation_date": case.get("valuation_date"),
    }


def evaluate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Full result envelope for a contract-valid case; raises ValueError otherwise."""
    violations = contract.validate_case(case)
    if violations:
        raise ValueError("; ".join(violations))
    canonical = json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    rows = _schedule(case)
    metrics = _metrics(case)
    probabilities: dict[str, Any] = {
        "break_even_success_pct": metrics["break_even_success_pct"],
        "market_implied_success_pct": metrics["market_implied_success_pct"],
        "market_implied_missing": metrics["market_implied_missing"],
    }
    if metrics["break_even_note"] is not None:
        probabilities["break_even_note"] = metrics["break_even_note"]
    if metrics["market_implied_note"] is not None:
        probabilities["market_implied_note"] = metrics["market_implied_note"]
    return {
        "schema_version": RESULT_SCHEMA,
        "formula_id": FORMULA_ID,
        "engine_version": ENGINE_VERSION,
        "run_receipt": {
            "inputs_sha256": digest,
            "contract_version": contract.CONTRACT_VERSION,
        },
        "status": "computed",
        "blocked_reasons": [],
        "scenario": _identity(case),
        "inputs_lineage": _inputs_lineage(case["inputs"]),
        "quarterly_schedule": rows,
        "outcome_class": metrics["outcome_class"],
        "values": {
            "dry_hole_npv_pkr": metrics["dry_hole_npv_pkr"],
            "unrisked_commercial_npv_pkr": metrics["unrisked_commercial_npv_pkr"],
            "risked_npv_pkr": metrics["risked_npv_pkr"],
            "p_success_pct": metrics["p_success_pct"],
        },
        "per_share": metrics.get("per_share"),
        "probabilities": probabilities,
        "confidence_limitations": _confidence_limitations(),
    }


def blocked_result(identity: Mapping[str, Any], reasons: list[str]) -> dict[str, Any]:
    """Envelope for a case that failed intake: identity and reasons, never partial numbers."""
    scenario = _identity(identity if isinstance(identity, Mapping) else {})
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
        "scenario": scenario,
        "inputs_lineage": [],
        "quarterly_schedule": [],
        "outcome_class": None,
        "values": None,
        "per_share": None,
        "probabilities": None,
        "confidence_limitations": _confidence_limitations(),
    }
