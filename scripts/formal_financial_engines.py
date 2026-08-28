"""Source-gated formal forecast, valuation, and expectations formulas.

The formulas here are intentionally small.  They activate only after the
forecast-readiness contract has accepted the historical financial inputs and
every forward/market operand is present as an approved, source-labelled record.
"""
from __future__ import annotations

from datetime import date
import math
from typing import Any, Mapping


ENGINE_VERSION = "formal_financial_engines_v1"
FORECAST_FORMULA_ID = "formal_forecast.revenue_margin_eps.v1"
VALUATION_FORMULA_ID = "formal_valuation.pe_equity_ev.v1"
EXPECTATIONS_FORMULA_ID = "formal_market_expectations.reverse_growth.v1"

FORECAST_ASSUMPTIONS = ("revenue_growth_pct", "net_margin_pct")
VALUATION_ASSUMPTIONS = ("exit_pe",)
MARKET_OPERANDS = ("shares_out", "net_debt", "current_price")


def finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def iso_date(value: Any) -> str | None:
    text = str(value or "")
    try:
        date.fromisoformat(text[:10])
    except ValueError:
        return None
    return text[:10]


def source_ok(record: Mapping[str, Any], cutoff: str | None) -> bool:
    source = record.get("source") or {}
    available_on = iso_date(record.get("available_on") or source.get("available_on"))
    if not available_on:
        return False
    if cutoff and available_on > cutoff:
        return False
    return bool(
        source.get("id")
        and source.get("label")
        and (source.get("url") or source.get("path"))
    )


def approved_records(assumptions: Mapping[str, Any], symbol: str, cutoff: str | None) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for record in assumptions.get("records") or []:
        if not isinstance(record, dict) or record.get("symbol") != symbol:
            continue
        metric = str(record.get("metric") or "")
        value = finite(record.get("value"))
        if (
            metric
            and value is not None
            and record.get("approved") is True
            and source_ok(record, cutoff)
        ):
            records[metric] = dict(record)
    return records


def _latest(observations: Mapping[str, Any], line: str, cutoff: str | None) -> dict[str, Any] | None:
    rows = []
    for row in observations.get(line) or []:
        if not isinstance(row, dict):
            continue
        value = finite(row.get("normalized_value"))
        available_on = iso_date(row.get("available_on") or row.get("availability"))
        period_end = iso_date(row.get("period_end"))
        if value is None or not available_on or not period_end:
            continue
        if cutoff and available_on > cutoff:
            continue
        if row.get("readiness") not in (None, "model_loadable"):
            continue
        if not row.get("fact_id") or not row.get("source_url"):
            continue
        rows.append(row)
    return sorted(rows, key=lambda row: (str(row.get("period_end") or ""), str(row.get("fact_id") or "")))[-1] if rows else None


def actuals_from_model_inputs(
    model_row: Mapping[str, Any],
    readiness_row: Mapping[str, Any],
    financial_truth_row: Mapping[str, Any],
    cutoff: str | None,
) -> tuple[dict[str, Any], list[str]]:
    missing = []
    # Forecast readiness describes legacy three-period input coverage.  Strict
    # financial truth is the authoritative, fail-closed activation gate.
    if financial_truth_row.get("status") != "qualified":
        missing.append("financial_truth_qualified")
    if readiness_row.get("status") != "input_ready":
        missing.append("forecast_readiness_input_ready")
    if model_row.get("status") != "ready":
        missing.append("financial_model_inputs_ready")
    observations = model_row.get("observations") or {}
    actuals = {
        line: _latest(observations, line, cutoff)
        for line in ("revenue", "profit_after_tax_attributable", "basic_eps")
    }
    for line, row in actuals.items():
        if row is None:
            missing.append(f"actual_{line}")
    periods = {row.get("period_end") for row in actuals.values() if row}
    if len(periods) > 1:
        missing.append("same_period_actuals")
    return actuals, sorted(set(missing))


def _blocked(symbol: str, kind: str, missing: list[str], formula_id: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "status": "blocked",
        "reason": "missing_source_gated_inputs",
        "missing_requirements": sorted(set(missing)),
        "formula_id": formula_id,
        "result": None,
        "provenance": [],
        "policy": {"research_only": True, "no_advice": True},
    }


def _source_ref(metric: str, record: Mapping[str, Any]) -> dict[str, Any]:
    source = record.get("source") or {}
    return {
        "metric": metric,
        "source_id": source.get("id"),
        "source_label": source.get("label"),
        "source_url": source.get("url"),
        "source_path": source.get("path"),
        "available_on": record.get("available_on") or source.get("available_on"),
        "record_type": record.get("record_type") or "approved_assumption",
    }


def _actual_ref(metric: str, row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "metric": metric,
        "fact_id": row.get("fact_id"),
        "document_id": row.get("document_id"),
        "source_url": row.get("source_url"),
        "period_end": row.get("period_end"),
        "available_on": row.get("available_on") or row.get("availability"),
        "record_type": "qualified_actual",
    }


def build_company_engines(
    symbol: str,
    model_row: Mapping[str, Any],
    readiness_row: Mapping[str, Any],
    financial_truth_row: Mapping[str, Any],
    assumptions: Mapping[str, Any],
    cutoff: str | None = None,
) -> dict[str, dict[str, Any]]:
    cutoff = iso_date(cutoff) or None
    actuals, missing = actuals_from_model_inputs(model_row, readiness_row, financial_truth_row, cutoff)
    records = approved_records(assumptions, symbol, cutoff)
    forecast_required = set(FORECAST_ASSUMPTIONS + ("shares_out",))
    valuation_required = forecast_required | set(VALUATION_ASSUMPTIONS + ("net_debt",))
    expectations_required = set(("current_price", "exit_pe", "net_margin_pct", "revenue_growth_pct", "shares_out"))

    def missing_for(required: set[str]) -> list[str]:
        return sorted(set(missing) | {f"approved_{metric}" for metric in sorted(required - set(records))})

    outputs: dict[str, dict[str, Any]] = {}
    forecast_missing = missing_for(forecast_required)
    valuation_missing = missing_for(valuation_required)
    expectations_missing = missing_for(expectations_required)

    def record_value(metric: str) -> float | None:
        return finite((records.get(metric) or {}).get("value"))

    def actual_value(line: str) -> float | None:
        return finite((actuals.get(line) or {}).get("normalized_value"))

    revenue = actual_value("revenue")
    growth = record_value("revenue_growth_pct")
    margin = record_value("net_margin_pct")
    shares = record_value("shares_out")
    if forecast_missing:
        outputs["forecast"] = _blocked(symbol, "forecast", forecast_missing, FORECAST_FORMULA_ID)
        forecast_revenue = forecast_pat = forecast_eps = None
        source_refs = []
    elif revenue is None or growth is None or margin is None or shares is None:
        raise ValueError(f"{symbol}: non-finite forecast operand")
    elif revenue <= 0 or shares <= 0 or margin <= 0:
        raise ValueError(f"{symbol}: non-positive gated operand")
    else:
        forecast_revenue = revenue * (1.0 + growth / 100.0)
        forecast_pat = forecast_revenue * margin / 100.0
        forecast_eps = forecast_pat / shares
        source_refs = [_actual_ref(metric, actuals[metric]) for metric in ("revenue", "profit_after_tax_attributable", "basic_eps")]
        source_refs.extend(_source_ref(metric, records[metric]) for metric in sorted(forecast_required))
        outputs["forecast"] = {
            "symbol": symbol,
            "status": "computed",
            "formula_id": FORECAST_FORMULA_ID,
            "result": {
                "forecast_revenue": forecast_revenue,
                "forecast_profit_after_tax_attributable": forecast_pat,
                "forecast_basic_eps": forecast_eps,
            },
            "provenance": source_refs,
            "policy": {"research_only": True, "no_advice": True},
        }

    if valuation_missing or forecast_eps is None:
        outputs["valuation"] = _blocked(symbol, "valuation", valuation_missing, VALUATION_FORMULA_ID)
    else:
        exit_pe = record_value("exit_pe")
        net_debt = record_value("net_debt")
        if exit_pe is None or net_debt is None:
            raise ValueError(f"{symbol}: non-finite valuation operand")
        if exit_pe <= 0:
            raise ValueError(f"{symbol}: non-positive valuation operand")
        formula_value_per_share = forecast_eps * exit_pe
        equity_value = formula_value_per_share * shares
        enterprise_value = equity_value + net_debt
        valuation_refs = list(source_refs)
        valuation_refs.extend(_source_ref(metric, records[metric]) for metric in sorted(set(VALUATION_ASSUMPTIONS + ("net_debt",))))
        outputs["valuation"] = {
            "symbol": symbol,
            "status": "computed",
            "formula_id": VALUATION_FORMULA_ID,
            "result": {
                "formula_value_per_share": formula_value_per_share,
                "formula_equity_value": equity_value,
                "formula_enterprise_value": enterprise_value,
                "net_debt": net_debt,
            },
            "provenance": valuation_refs,
            "policy": {"research_only": True, "no_advice": True},
        }

    if expectations_missing:
        outputs["market_expectations"] = _blocked(symbol, "market_expectations", expectations_missing, EXPECTATIONS_FORMULA_ID)
    else:
        exit_pe = record_value("exit_pe")
        price = record_value("current_price")
        if revenue is None or margin is None or shares is None or growth is None or exit_pe is None or price is None:
            raise ValueError(f"{symbol}: non-finite market expectations operand")
        if revenue <= 0 or margin <= 0 or shares <= 0 or exit_pe <= 0 or price <= 0:
            raise ValueError(f"{symbol}: non-positive market expectations operand")
        required_eps = price / exit_pe
        required_pat = required_eps * shares
        required_revenue = required_pat / (margin / 100.0)
        required_growth = (required_revenue / revenue - 1.0) * 100.0
        expectation_refs = [_actual_ref(metric, actuals[metric]) for metric in ("revenue", "profit_after_tax_attributable", "basic_eps")]
        expectation_refs.extend(_source_ref(metric, records[metric]) for metric in sorted(expectations_required))
        outputs["market_expectations"] = {
            "symbol": symbol,
            "status": "computed",
            "formula_id": EXPECTATIONS_FORMULA_ID,
            "result": {
                "required_revenue": required_revenue,
                "required_profit_after_tax_attributable": required_pat,
                "required_basic_eps": required_eps,
                "required_revenue_growth_pct": required_growth,
                "assumed_revenue_growth_pct": growth,
                "expectations_gap_pct": required_growth - growth,
            },
            "provenance": expectation_refs,
            "policy": {"research_only": True, "no_advice": True},
        }
    return outputs
