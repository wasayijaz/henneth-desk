"""MARI E&P historical analogue and event-study engine.

Deterministic, read-only research arithmetic over retained desk state. No LLM,
no network, no advice. Identical inputs produce identical outputs; a number is
emitted only where retained evidence permits it, never null-as-zero.

Point-in-time contract (every comparison is strict):

- A candidate event's effective date must precede the target event's date.
- A price endpoint must land strictly before the target event's date; the
  pre-event price baseline must land strictly before the candidate's date.
- A financial outcome period must END strictly before the target event's date
  and its fact must be AVAILABLE strictly before that date. A pre-event
  financial baseline must end and be available strictly before the candidate
  event's own date.
- Only model-loadable financial facts produce outcomes; audit-only facts fail
  closed with an explicit reason.

Horizons are 1Q/2Q/4Q/8Q: calendar-month targets (3/6/12/24) for raw stock
returns and post-event fiscal-quarter ordinals (1st/2nd/4th/8th distinct
period end strictly after the candidate event) for revenue, net margin and
EPS outcomes, each measured against the candidate's own pre-event baseline.

Aggregates report n, median, range and interquartile range, and are suppressed
with an explicit display whenever n < MIN_SAMPLE. Everything here is
descriptive history: no causal claim, no forecast, no valuation input, no
advice.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))

from psx_data import ROOT, STATE, load_json, save_json
from event_studies import add_months, first_on_or_after, last_before, parse_date, raw_return

ENGINE_VERSION = "mari_enp_analogue_engine_v1"
RESULT_SCHEMA = "mari_enp_analogue_engine_result_v1"
SYMBOL = "MARI"
PEERS = ("OGDC", "PPL")
UNIVERSE = (SYMBOL,) + PEERS
CASE_FAMILY = "e_and_p_exploration"
OUT = STATE / "company_intel" / "mari_enp_analogue_engine.json"

# The retained registry has no dedicated discovery/exploration/working-interest
# event type; acquisition_divestment carries MARI's working-interest,
# exploration-block and farm-out events. The remaining types are accepted
# defensively so a future registry addition cannot silently miss the family.
FAMILY_EVENT_TYPES = ("acquisition_divestment", "discovery", "exploration", "working_interest")
HORIZON_ORDER = ("1Q", "2Q", "4Q", "8Q")
HORIZON_MONTHS = {"1Q": 3, "2Q": 6, "4Q": 12, "8Q": 24}
HORIZON_QUARTERS = {"1Q": 1, "2Q": 2, "4Q": 4, "8Q": 8}
MIN_SAMPLE = 3
INSUFFICIENT_EVIDENCE = "Insufficient evidence for a reliable benchmark"
MODEL_ELIGIBLE = "model_loadable"
FINANCIAL_METRICS = ("revenue", "profit", "eps")
OUTCOME_METRICS = ("stock_return_pct", "revenue_delta_pct", "margin_delta_pct", "eps_delta_pct")
AGG_CLASSES = ("same_company", "peer", "combined")
MAX_ABS_NUMBER = 1.0e15
LOOKAHEAD_REASONS = frozenset(
    {
        "period_end_not_strictly_before_target_cutoff",
        "revenue_available_on_not_strictly_before_target_cutoff",
        "profit_available_on_not_strictly_before_target_cutoff",
        "eps_available_on_not_strictly_before_target_cutoff",
    }
)
LOOKAHEAD_SLOT_REASONS = frozenset(
    LOOKAHEAD_REASONS
    | {
        "endpoint_not_available_strictly_before_target_cutoff",
    }
)

ROOT_KEYS = (
    "schema_version",
    "engine_version",
    "symbol",
    "peer_symbols",
    "event_family",
    "minimum_sample",
    "data_cutoffs",
    "policy",
    "symbol_coverage",
    "target_count",
    "targets",
    "limitations",
    "source",
)
FAMILY_KEYS = ("event_types", "universe", "rationale", "matching_policy")
COVERAGE_KEYS = (
    "family_event_count",
    "dated_family_event_count",
    "excluded_event_count",
    "excluded_events",
    "financial_series",
)
FIN_SERIES_KEYS = ("fact_count", "model_eligible_fact_count", "metrics_present", "status", "reason")
TARGET_KEYS = ("target_event", "excluded_candidates", "candidate_count", "candidates", "aggregates", "insufficient_evidence")
TARGET_EVENT_KEYS = ("event_id", "symbol", "event_type", "event_subtype", "effective_date", "cutoff", "source_document_ids")
EXCLUDED_CANDIDATE_KEYS = ("event_id", "symbol", "reason")
CANDIDATE_KEYS = ("event_id", "symbol", "classification", "event_type", "event_subtype", "effective_date", "outcomes")
STOCK_SLOT_KEYS = (
    "status",
    "reason",
    "value",
    "target_date",
    "baseline_date",
    "baseline_close",
    "endpoint_date",
    "endpoint_close",
)
FIN_SLOT_KEYS = (
    "status",
    "reason",
    "period_end",
    "available_on",
    "level_value",
    "baseline_period_end",
    "baseline_level_value",
    "value",
    "delta_semantics",
)
SLOT_NAMES = ("stock_return_pct", "revenue", "margin", "eps")
AGG_KEYS = ("n", "status", "reason", "display", "stats")
STATS_KEYS = ("median", "min", "max", "range", "q1", "q3", "iqr")
STATUS_ENUM = ("mature", "unavailable", "excluded_lookahead")
PCT_DELTA = "pct_change_vs_pre_event_baseline_period"
PP_DELTA = "percentage_point_change_vs_pre_event_baseline_period"
BANNED = ("you should", "buy", "sell", "accumulate", "target price", "price target", "recommendation", "caused", "will lead")


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or abs(number) > MAX_ABS_NUMBER:
        return None
    return number


def _walk_text(value: Any) -> str:
    if isinstance(value, str):
        return value.casefold()
    if isinstance(value, Mapping):
        return " ".join(_walk_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_walk_text(item) for item in value)
    return ""


def select_family_events(events_by_symbol: Mapping[str, Iterable[Mapping[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split universe events into dated family events and excluded rows."""
    dated: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for symbol in UNIVERSE:
        for event in events_by_symbol.get(symbol) or []:
            if not isinstance(event, Mapping) or event.get("event_type") not in FAMILY_EVENT_TYPES:
                continue
            row = {"symbol": symbol, "event": dict(event)}
            if parse_date(event.get("effective_date")) is None:
                excluded.append(
                    {
                        "symbol": symbol,
                        "event_id": event.get("event_id"),
                        "event_type": event.get("event_type"),
                        "reason": "missing_or_invalid_effective_date",
                    }
                )
            else:
                dated.append(row)
    dated.sort(key=lambda row: (row["event"].get("effective_date") or "", row["event"].get("event_id") or ""))
    excluded.sort(key=lambda row: (row.get("symbol") or "", row.get("event_id") or ""))
    return dated, excluded


def stock_return_outcome(
    rows: list[dict[str, Any]], candidate_day: date, horizon_months: int, target_cutoff: date
) -> dict[str, Any]:
    """Raw close-to-close return for one candidate horizon, cutoff-capped."""
    target_day = add_months(candidate_day, horizon_months)
    out: dict[str, Any] = {
        "status": "unavailable",
        "reason": None,
        "value": None,
        "target_date": target_day.isoformat(),
        "baseline_date": None,
        "baseline_close": None,
        "endpoint_date": None,
        "endpoint_close": None,
    }
    baseline = last_before(rows, candidate_day)
    if baseline is None or _finite(baseline.get("close")) is None or float(baseline["close"]) == 0.0:
        out["reason"] = "no_valid_baseline_close_before_event"
        return out
    out["baseline_date"] = baseline.get("date")
    out["baseline_close"] = _finite(baseline.get("close"))
    endpoint = first_on_or_after(rows, target_day)
    if endpoint is None or _finite(endpoint.get("close")) is None:
        out["reason"] = "no_endpoint_close_on_or_after_target_date"
        return out
    endpoint_day = parse_date(endpoint.get("date"))
    if endpoint_day is None or endpoint_day >= target_cutoff:
        out["status"] = "excluded_lookahead"
        out["reason"] = "endpoint_not_available_strictly_before_target_cutoff"
        return out
    value = raw_return(baseline, endpoint)
    if value is None or not math.isfinite(value):
        out["reason"] = "invalid_return_arithmetic"
        return out
    out.update(
        {
            "status": "mature",
            "reason": None,
            "value": float(value),
            "endpoint_date": endpoint.get("date"),
            "endpoint_close": _finite(endpoint.get("close")),
        }
    )
    return out


def _fact_view(fact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "metric": fact.get("metric"),
        "period_end": parse_date(fact.get("period_end")),
        "available_on": parse_date(fact.get("available_on")),
        "value": _finite(fact.get("normalized_value")),
        "readiness": fact.get("readiness"),
    }


def _period_level(
    views: list[dict[str, Any]], metric: str, period: date, target_cutoff: date
) -> tuple[str, str | None, float | None, date | None]:
    """Eligible level for one (metric, period) under the target cutoff."""
    rows = [view for view in views if view["metric"] == metric and view["period_end"] == period]
    if not rows:
        return "unavailable", f"no_dated_{metric}_fact_for_period", None, None
    with_avail = [view for view in rows if view["available_on"] is not None]
    if not with_avail:
        return "unavailable", f"{metric}_missing_available_on", None, None
    prior = [view for view in with_avail if view["available_on"] < target_cutoff]
    if not prior:
        return "excluded_lookahead", f"{metric}_available_on_not_strictly_before_target_cutoff", None, None
    eligible = [view for view in prior if view["readiness"] == MODEL_ELIGIBLE and view["value"] is not None]
    if not eligible:
        return "unavailable", f"{metric}_facts_not_model_eligible", None, None
    if len({view["value"] for view in eligible}) > 1:
        return "unavailable", f"conflicting_eligible_{metric}_facts", None, None
    return "mature", None, eligible[0]["value"], eligible[0]["available_on"]


def _baseline_level(
    views: list[dict[str, Any]], metric: str, candidate_day: date
) -> tuple[date | None, float | None, str]:
    """Latest eligible pre-event baseline level, published before the event."""
    eligible = [
        view
        for view in views
        if view["metric"] == metric
        and view["readiness"] == MODEL_ELIGIBLE
        and view["value"] is not None
        and view["period_end"] is not None
        and view["period_end"] < candidate_day
        and view["available_on"] is not None
        and view["available_on"] < candidate_day
    ]
    if not eligible:
        return None, None, f"no_pre_event_eligible_{metric}_baseline"
    latest = max(view["period_end"] for view in eligible)
    rows = [view for view in eligible if view["period_end"] == latest]
    if len({view["value"] for view in rows}) > 1:
        return latest, None, f"conflicting_eligible_{metric}_baseline"
    return latest, rows[0]["value"], ""


def _fin_slot(
    status: str,
    reason: str | None,
    *,
    period_end: date | None = None,
    available_on: date | None = None,
    level_value: float | None = None,
    baseline_period_end: date | None = None,
    baseline_level_value: float | None = None,
    value: float | None = None,
    delta_semantics: str | None = None,
) -> dict[str, Any]:
    mature = status == "mature"
    return {
        "status": status,
        "reason": reason,
        "period_end": period_end.isoformat() if period_end else None,
        "available_on": available_on.isoformat() if available_on else None,
        "level_value": level_value if mature else None,
        "baseline_period_end": baseline_period_end.isoformat() if baseline_period_end else None,
        "baseline_level_value": baseline_level_value if mature else None,
        "value": value if mature else None,
        "delta_semantics": delta_semantics if mature else None,
    }


def _level_delta_slot(
    metric: str,
    views: list[dict[str, Any]],
    period: date,
    candidate_day: date,
    target_cutoff: date,
) -> dict[str, Any]:
    status, reason, level, available_on = _period_level(views, metric, period, target_cutoff)
    if status != "mature":
        return _fin_slot(status, reason, period_end=period)
    baseline_end, baseline_level, baseline_reason = _baseline_level(views, metric, candidate_day)
    if baseline_level is None or baseline_level <= 0.0:
        return _fin_slot("unavailable", baseline_reason or f"nonpositive_{metric}_baseline", period_end=period)
    if level is None or level <= 0.0:
        return _fin_slot("unavailable", f"nonpositive_{metric}_outcome", period_end=period)
    delta = (level / baseline_level - 1.0) * 100.0
    if not math.isfinite(delta):
        return _fin_slot("unavailable", "invalid_delta_arithmetic", period_end=period)
    return _fin_slot(
        "mature",
        None,
        period_end=period,
        available_on=available_on,
        level_value=level,
        baseline_period_end=baseline_end,
        baseline_level_value=baseline_level,
        value=delta,
        delta_semantics=PCT_DELTA,
    )


def _margin_slot(
    views: list[dict[str, Any]],
    period: date,
    candidate_day: date,
    target_cutoff: date,
    metrics_present: frozenset[str],
) -> dict[str, Any]:
    if not {"revenue", "profit"} <= metrics_present:
        return _fin_slot("unavailable", "margin_requires_revenue_and_profit_series")
    rev_status, rev_reason, rev_level, _ = _period_level(views, "revenue", period, target_cutoff)
    prof_status, prof_reason, prof_level, available_on = _period_level(views, "profit", period, target_cutoff)
    if rev_status != "mature":
        return _fin_slot(rev_status, rev_reason, period_end=period)
    if prof_status != "mature":
        return _fin_slot(prof_status, prof_reason, period_end=period)
    if rev_level is None or rev_level <= 0.0:
        return _fin_slot("unavailable", "nonpositive_revenue_for_margin", period_end=period)
    margin = prof_level / rev_level * 100.0
    rev_end, rev_base, rev_reason = _baseline_level(views, "revenue", candidate_day)
    prof_end, prof_base, prof_reason = _baseline_level(views, "profit", candidate_day)
    if rev_base is None or rev_base <= 0.0:
        return _fin_slot("unavailable", rev_reason or "nonpositive_revenue_baseline", period_end=period)
    if prof_base is None:
        return _fin_slot("unavailable", prof_reason, period_end=period)
    if rev_end != prof_end:
        return _fin_slot("unavailable", "no_common_pre_event_margin_baseline_period", period_end=period)
    base_margin = prof_base / rev_base * 100.0
    delta = margin - base_margin
    if not math.isfinite(margin) or not math.isfinite(delta):
        return _fin_slot("unavailable", "invalid_margin_arithmetic", period_end=period)
    return _fin_slot(
        "mature",
        None,
        period_end=period,
        available_on=available_on,
        level_value=margin,
        baseline_period_end=rev_end,
        baseline_level_value=base_margin,
        value=delta,
        delta_semantics=PP_DELTA,
    )


def financial_outcomes(
    facts: Iterable[Mapping[str, Any]],
    metrics_present: Iterable[str],
    candidate_day: date,
    quarter_index: int,
    target_cutoff: date,
) -> dict[str, dict[str, Any]]:
    """Revenue/margin/EPS outcome slots for the quarter_index-th post-event fiscal period."""
    metrics = frozenset(metrics_present)
    views = [_fact_view(fact) for fact in facts if isinstance(fact, Mapping) and fact.get("metric") in FINANCIAL_METRICS]
    dated_ends = sorted({view["period_end"] for view in views if view["period_end"] is not None})
    post_ends = [end for end in dated_ends if end > candidate_day]

    def blocked(reason: str, status: str = "unavailable", period: date | None = None) -> dict[str, dict[str, Any]]:
        return {
            "revenue": _fin_slot(status, reason, period_end=period),
            "margin": _fin_slot(status, reason, period_end=period),
            "eps": _fin_slot(status, reason, period_end=period),
        }

    if quarter_index > len(post_ends):
        return blocked("insufficient_dated_periods_after_event")
    period = post_ends[quarter_index - 1]
    if period >= target_cutoff:
        return blocked("period_end_not_strictly_before_target_cutoff", status="excluded_lookahead", period=period)

    revenue = (
        _level_delta_slot("revenue", views, period, candidate_day, target_cutoff)
        if "revenue" in metrics
        else _fin_slot("unavailable", "revenue_not_in_retained_financial_series", period_end=period)
    )
    margin = _margin_slot(views, period, candidate_day, target_cutoff, metrics)
    eps = (
        _level_delta_slot("eps", views, period, candidate_day, target_cutoff)
        if "eps" in metrics
        else _fin_slot("unavailable", "eps_not_in_retained_financial_series", period_end=period)
    )
    return {"revenue": revenue, "margin": margin, "eps": eps}


def aggregate_statistics(values: Iterable[Any]) -> dict[str, Any]:
    """n, median, range and IQR for mature outcomes; suppressed below MIN_SAMPLE."""
    finite = sorted(float(value) for value in values if _finite(value) is not None)
    count = len(finite)
    stats = {key: None for key in STATS_KEYS}
    out: dict[str, Any] = {"n": count, "status": None, "reason": None, "display": None, "stats": stats}
    if count < MIN_SAMPLE:
        out["status"] = "suppressed"
        out["reason"] = f"n_lt_{MIN_SAMPLE}"
        out["display"] = INSUFFICIENT_EVIDENCE
        return out
    q1, median, q3 = statistics.quantiles(finite, n=4, method="inclusive")
    low, high = finite[0], finite[-1]
    stats.update(
        {
            "median": median,
            "min": low,
            "max": high,
            "range": high - low,
            "q1": q1,
            "q3": q3,
            "iqr": q3 - q1,
        }
    )
    out["status"] = "available"
    return out


def _candidate_outcome_value(outcome: Mapping[str, Any], metric: str) -> float | None:
    if metric == "stock_return_pct":
        slot = outcome["stock_return_pct"]
    elif metric == "revenue_delta_pct":
        slot = outcome["revenue"]
    elif metric == "margin_delta_pct":
        slot = outcome["margin"]
    else:
        slot = outcome["eps"]
    if slot.get("status") != "mature":
        return None
    value = _finite(slot.get("value"))
    return value


def _aggregates_for(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    aggregates: dict[str, Any] = {}
    for horizon in HORIZON_ORDER:
        metric_map: dict[str, Any] = {}
        for metric in OUTCOME_METRICS:
            class_map: dict[str, Any] = {}
            for label in AGG_CLASSES:
                if label == "combined":
                    pool = candidates
                else:
                    pool = [row for row in candidates if row["classification"] == label]
                values = [
                    value
                    for row in pool
                    if (value := _candidate_outcome_value(row["outcomes"][horizon], metric)) is not None
                ]
                class_map[label] = aggregate_statistics(values)
            metric_map[metric] = class_map
        aggregates[horizon] = metric_map
    return aggregates


def _validate_fin_slot(slot: Any, path: str, errors: list[str]) -> None:
    if not isinstance(slot, Mapping) or tuple(slot) != FIN_SLOT_KEYS:
        errors.append(f"{path}: exact fin slot keys required")
        return
    status = slot.get("status")
    if status not in STATUS_ENUM:
        errors.append(f"{path}.status: invalid status")
        return
    if status == "mature":
        if _finite(slot.get("value")) is None or _finite(slot.get("level_value")) is None:
            errors.append(f"{path}: mature slot requires finite value and level")
        if parse_date(slot.get("period_end")) is None or parse_date(slot.get("available_on")) is None:
            errors.append(f"{path}: mature slot requires period_end and available_on")
        if slot.get("delta_semantics") not in (PCT_DELTA, PP_DELTA):
            errors.append(f"{path}.delta_semantics: unknown semantics")
    else:
        if any(slot.get(key) is not None for key in ("value", "level_value", "baseline_level_value", "delta_semantics")):
            errors.append(f"{path}: non-mature slot must not carry numbers")
        if not isinstance(slot.get("reason"), str) or not slot["reason"].strip():
            errors.append(f"{path}.reason: required for non-mature slot")
        if status == "excluded_lookahead" and slot.get("reason") not in LOOKAHEAD_SLOT_REASONS:
            errors.append(f"{path}.reason: unknown lookahead reason")
    if slot.get("period_end") is not None and parse_date(slot.get("period_end")) is None:
        errors.append(f"{path}.period_end: unparseable")


def validate_output(payload: Any) -> list[str]:
    """Fail-closed structural and point-in-time validation of the full artifact."""
    errors: list[str] = []
    if not isinstance(payload, Mapping):
        return ["payload: must be a mapping"]
    if tuple(payload) != ROOT_KEYS:
        errors.append("payload: exact root keys required")
    if payload.get("schema_version") != RESULT_SCHEMA or payload.get("engine_version") != ENGINE_VERSION:
        errors.append("payload: schema/engine version mismatch")
    if payload.get("symbol") != SYMBOL or tuple(payload.get("peer_symbols") or ()) != PEERS:
        errors.append("payload: symbol/peer identity mismatch")
    if payload.get("minimum_sample") != MIN_SAMPLE:
        errors.append("payload: minimum_sample mismatch")
    family = payload.get("event_family")
    if not isinstance(family, Mapping) or tuple(family) != FAMILY_KEYS:
        errors.append("event_family: exact keys required")
    else:
        if tuple(family.get("event_types") or ()) != FAMILY_EVENT_TYPES:
            errors.append("event_family.event_types: mismatch")
        if tuple(family.get("universe") or ()) != UNIVERSE:
            errors.append("event_family.universe: mismatch")
    policy = payload.get("policy")
    if not isinstance(policy, Mapping):
        errors.append("policy: mapping required")
    else:
        for flag in ("descriptive_only", "no_causal_claim", "no_forecast_or_valuation", "no_advice", "raw_price_return_not_adjusted_or_total_return"):
            if policy.get(flag) is not True:
                errors.append(f"policy.{flag}: must be true")
        if policy.get("minimum_aggregate_sample") != MIN_SAMPLE:
            errors.append("policy.minimum_aggregate_sample: mismatch")
        if policy.get("insufficient_evidence_display") != INSUFFICIENT_EVIDENCE:
            errors.append("policy.insufficient_evidence_display: mismatch")
    if not isinstance(payload.get("data_cutoffs"), Mapping):
        errors.append("data_cutoffs: mapping required")
    coverage = payload.get("symbol_coverage")
    if not isinstance(coverage, Mapping) or tuple(coverage) != UNIVERSE:
        errors.append("symbol_coverage: exact universe keys required")
    else:
        for symbol, row in coverage.items():
            if not isinstance(row, Mapping) or tuple(row) != COVERAGE_KEYS:
                errors.append(f"symbol_coverage.{symbol}: exact keys required")
                continue
            series = row.get("financial_series")
            if not isinstance(series, Mapping) or tuple(series) != FIN_SERIES_KEYS:
                errors.append(f"symbol_coverage.{symbol}.financial_series: exact keys required")
    targets = payload.get("targets")
    if not isinstance(targets, list):
        errors.append("targets: list required")
        targets = []
    if payload.get("target_count") != len(targets):
        errors.append("target_count: must equal targets length")
    ordered = [(row.get("target_event", {}).get("effective_date") or "", row.get("target_event", {}).get("event_id") or "") for row in targets if isinstance(row, Mapping)]
    if ordered != sorted(ordered):
        errors.append("targets: must be sorted by effective_date then event_id")
    for index, target in enumerate(targets):
        prefix = f"targets[{index}]"
        if not isinstance(target, Mapping) or tuple(target) != TARGET_KEYS:
            errors.append(f"{prefix}: exact target keys required")
            continue
        event = target.get("target_event")
        if not isinstance(event, Mapping) or tuple(event) != TARGET_EVENT_KEYS:
            errors.append(f"{prefix}.target_event: exact keys required")
            continue
        target_day = parse_date(event.get("effective_date"))
        if target_day is None or event.get("cutoff") != event.get("effective_date"):
            errors.append(f"{prefix}.target_event: effective_date/cutoff invalid")
            continue
        if event.get("symbol") != SYMBOL:
            errors.append(f"{prefix}.target_event.symbol: must be MARI")
        if not isinstance(event.get("source_document_ids"), list):
            errors.append(f"{prefix}.target_event.source_document_ids: list required")
        excluded = target.get("excluded_candidates")
        if not isinstance(excluded, list):
            errors.append(f"{prefix}.excluded_candidates: list required")
        else:
            for row in excluded:
                if not isinstance(row, Mapping) or tuple(row) != EXCLUDED_CANDIDATE_KEYS or row.get("reason") != "effective_date_not_strictly_before_target":
                    errors.append(f"{prefix}.excluded_candidates: malformed row")
        counts = target.get("candidate_count")
        candidates = target.get("candidates")
        if not isinstance(counts, Mapping) or tuple(counts) != AGG_CLASSES:
            errors.append(f"{prefix}.candidate_count: exact class keys required")
            counts = {}
        if not isinstance(candidates, list):
            errors.append(f"{prefix}.candidates: list required")
            candidates = []
        recount = {"same_company": 0, "peer": 0, "combined": 0}
        for position, candidate in enumerate(candidates):
            cpath = f"{prefix}.candidates[{position}]"
            if not isinstance(candidate, Mapping) or tuple(candidate) != CANDIDATE_KEYS:
                errors.append(f"{cpath}: exact candidate keys required")
                continue
            candidate_day = parse_date(candidate.get("effective_date"))
            if candidate_day is None:
                errors.append(f"{cpath}.effective_date: unparseable")
                continue
            if candidate_day >= target_day:
                errors.append(f"{cpath}.effective_date: must be strictly before target")
                continue
            symbol = candidate.get("symbol")
            classification = candidate.get("classification")
            if classification == "same_company":
                if symbol != SYMBOL:
                    errors.append(f"{cpath}: same_company requires MARI")
            elif classification == "peer":
                if symbol not in PEERS:
                    errors.append(f"{cpath}: peer requires OGDC or PPL")
            else:
                errors.append(f"{cpath}.classification: invalid")
                continue
            recount[classification] += 1
            recount["combined"] += 1
            outcomes = candidate.get("outcomes")
            if not isinstance(outcomes, Mapping) or tuple(outcomes) != HORIZON_ORDER:
                errors.append(f"{cpath}.outcomes: exact horizon keys required")
                continue
            for horizon, outcome in outcomes.items():
                opath = f"{cpath}.outcomes.{horizon}"
                if not isinstance(outcome, Mapping) or tuple(outcome) != SLOT_NAMES:
                    errors.append(f"{opath}: exact slot keys required")
                    continue
                stock = outcome["stock_return_pct"]
                if not isinstance(stock, Mapping) or tuple(stock) != STOCK_SLOT_KEYS:
                    errors.append(f"{opath}.stock_return_pct: exact keys required")
                else:
                    status = stock.get("status")
                    if status not in STATUS_ENUM:
                        errors.append(f"{opath}.stock_return_pct.status: invalid")
                    elif status == "mature":
                        if _finite(stock.get("value")) is None:
                            errors.append(f"{opath}.stock_return_pct: mature requires finite value")
                        baseline_day = parse_date(stock.get("baseline_date"))
                        endpoint_day = parse_date(stock.get("endpoint_date"))
                        if baseline_day is None or baseline_day >= candidate_day:
                            errors.append(f"{opath}.stock_return_pct.baseline_date: must precede candidate")
                        if endpoint_day is None or endpoint_day < parse_date(stock.get("target_date") or "") or endpoint_day >= target_day:
                            errors.append(f"{opath}.stock_return_pct.endpoint_date: must be on/after target and before cutoff")
                    else:
                        if stock.get("value") is not None or stock.get("endpoint_close") is not None or stock.get("endpoint_date") is not None:
                            errors.append(f"{opath}.stock_return_pct: non-mature slot must not carry endpoint numbers")
                        if not isinstance(stock.get("reason"), str) or not stock["reason"].strip():
                            errors.append(f"{opath}.stock_return_pct.reason: required")
                        elif status == "excluded_lookahead" and stock["reason"] not in LOOKAHEAD_SLOT_REASONS:
                            errors.append(f"{opath}.stock_return_pct.reason: unknown lookahead reason")
                    if parse_date(stock.get("target_date") or "x") is None:
                        errors.append(f"{opath}.stock_return_pct.target_date: unparseable")
                for slot_name in ("revenue", "margin", "eps"):
                    _validate_fin_slot(outcome[slot_name], f"{opath}.{slot_name}", errors)
                    slot = outcome[slot_name]
                    if isinstance(slot, Mapping) and slot.get("status") == "mature":
                        period_end = parse_date(slot.get("period_end"))
                        available_on = parse_date(slot.get("available_on"))
                        baseline_end = parse_date(slot.get("baseline_period_end") or "2000-01-01")
                        if period_end is None or period_end <= candidate_day:
                            errors.append(f"{opath}.{slot_name}.period_end: must follow candidate")
                        if available_on is None or available_on >= target_day:
                            errors.append(f"{opath}.{slot_name}.available_on: must strictly precede target")
                        if baseline_end is not None and baseline_end >= candidate_day:
                            errors.append(f"{opath}.{slot_name}.baseline_period_end: must precede candidate")
        for label, count in recount.items():
            if counts.get(label) != count:
                errors.append(f"{prefix}.candidate_count.{label}: must equal recomputed candidate count")
        aggregates = target.get("aggregates")
        if not isinstance(aggregates, Mapping) or tuple(aggregates) != HORIZON_ORDER:
            errors.append(f"{prefix}.aggregates: exact horizon keys required")
            continue
        any_available = False
        for horizon, metric_map in aggregates.items():
            if not isinstance(metric_map, Mapping) or tuple(metric_map) != OUTCOME_METRICS:
                errors.append(f"{prefix}.aggregates.{horizon}: exact metric keys required")
                continue
            for metric, class_map in metric_map.items():
                apath = f"{prefix}.aggregates.{horizon}.{metric}"
                if not isinstance(class_map, Mapping) or tuple(class_map) != AGG_CLASSES:
                    errors.append(f"{apath}: exact class keys required")
                    continue
                for label, agg in class_map.items():
                    if not isinstance(agg, Mapping) or tuple(agg) != AGG_KEYS:
                        errors.append(f"{apath}.{label}: exact aggregate keys required")
                        continue
                    count = agg.get("n")
                    expected = sum(
                        1
                        for row in candidates
                        if (label == "combined" or row.get("classification") == label)
                        and _candidate_outcome_value(row.get("outcomes", {}).get(horizon) or {}, metric) is not None
                    )
                    if count != expected:
                        errors.append(f"{apath}.{label}.n: must equal mature outcome count")
                    stats = agg.get("stats")
                    if not isinstance(stats, Mapping) or tuple(stats) != STATS_KEYS:
                        errors.append(f"{apath}.{label}.stats: exact keys required")
                        continue
                    if isinstance(count, int) and count < MIN_SAMPLE:
                        if agg.get("status") != "suppressed" or agg.get("reason") != f"n_lt_{MIN_SAMPLE}":
                            errors.append(f"{apath}.{label}: thin sample must be suppressed")
                        if agg.get("display") != INSUFFICIENT_EVIDENCE:
                            errors.append(f"{apath}.{label}.display: exact insufficient-evidence text required")
                        if any(stats.get(key) is not None for key in STATS_KEYS):
                            errors.append(f"{apath}.{label}.stats: must be null while suppressed")
                    else:
                        if agg.get("status") != "available" or agg.get("reason") is not None or agg.get("display") is not None:
                            errors.append(f"{apath}.{label}: available aggregate fields mismatch")
                        values = [v for v in (stats.get(key) for key in STATS_KEYS) if v is not None]
                        if len(values) != len(STATS_KEYS) or any(_finite(v) is None for v in values):
                            errors.append(f"{apath}.{label}.stats: finite values required")
                        else:
                            low, q1, median, q3, high = stats["min"], stats["q1"], stats["median"], stats["q3"], stats["max"]
                            if not (low <= q1 <= median <= q3 <= high):
                                errors.append(f"{apath}.{label}.stats: quartile ordering violated")
                            if abs(stats["range"] - (high - low)) > 1e-9 or abs(stats["iqr"] - (q3 - q1)) > 1e-9:
                                errors.append(f"{apath}.{label}.stats: range/iqr identities violated")
                        any_available = True
        if target.get("insufficient_evidence") != (not any_available):
            errors.append(f"{prefix}.insufficient_evidence: must equal absence of any available aggregate")
    limitations = payload.get("limitations")
    source = payload.get("source")
    if not isinstance(limitations, list) or not limitations or any(not isinstance(row, str) or not row.strip() for row in limitations):
        errors.append("limitations: non-empty string list required")
    if not isinstance(source, list) or not source or any(not isinstance(row, str) for row in source):
        errors.append("source: non-empty string list required")
    lowered = _walk_text(payload)
    for phrase in BANNED:
        if phrase in lowered:
            errors.append(f"payload: banned advice/causal language ({phrase})")
            break
    try:
        json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError):
        errors.append("payload: must be finite JSON-serializable data")
    return sorted(set(errors))


def _load_history(root: Path, symbol: str) -> list[dict[str, Any]]:
    rows = load_json(root / "state" / "history" / f"{symbol}.json", [])
    if not isinstance(rows, list):
        return []
    keep = [
        row
        for row in rows
        if isinstance(row, dict) and parse_date(row.get("date")) is not None and _finite(row.get("close")) is not None
    ]
    return sorted(keep, key=lambda row: row.get("date") or "")


def _series_views(root: Path, symbol: str) -> tuple[list[Mapping[str, Any]], list[str], int, int]:
    series = load_json(root / "state" / "company_financial_series.json", {})
    tickers = series.get("tickers") if isinstance(series, dict) else {}
    ticker = (tickers or {}).get(symbol) or {}
    facts = [fact for fact in (ticker.get("facts") or []) if isinstance(fact, Mapping)]
    metrics = sorted((ticker.get("metrics") or {}).keys()) if isinstance(ticker.get("metrics"), dict) else []
    eligible = sum(1 for fact in facts if fact.get("readiness") == MODEL_ELIGIBLE)
    return facts, metrics, len(facts), eligible


def _coverage_row(symbol: str, dated: list[dict[str, Any]], excluded: list[dict[str, Any]], root: Path) -> dict[str, Any]:
    family = [row for row in dated if row["symbol"] == symbol]
    family_excluded = [row for row in excluded if row["symbol"] == symbol]
    facts, metrics, fact_count, eligible_count = _series_views(root, symbol)
    if fact_count == 0:
        status, reason = "no_facts", "no_retained_financial_series_facts"
    elif eligible_count == 0:
        status, reason = "no_model_eligible_facts", "all_retained_facts_audit_only"
    else:
        status, reason = "available", ""
    return {
        "family_event_count": len(family) + len(family_excluded),
        "dated_family_event_count": len(family),
        "excluded_event_count": len(family_excluded),
        "excluded_events": family_excluded,
        "financial_series": {
            "fact_count": fact_count,
            "model_eligible_fact_count": eligible_count,
            "metrics_present": metrics,
            "status": status,
            "reason": reason,
        },
    }


def _candidate_study(
    event: Mapping[str, Any],
    symbol: str,
    target_day: date,
    histories: Mapping[str, list[dict[str, Any]]],
    facts_by_symbol: Mapping[str, list[Mapping[str, Any]]],
    metrics_by_symbol: Mapping[str, list[str]],
) -> dict[str, Any]:
    candidate_day = parse_date(event.get("effective_date"))
    classification = "same_company" if symbol == SYMBOL else "peer"
    outcomes: dict[str, Any] = {}
    for horizon in HORIZON_ORDER:
        stock = stock_return_outcome(histories[symbol], candidate_day, HORIZON_MONTHS[horizon], target_day)
        financial = financial_outcomes(
            facts_by_symbol[symbol],
            metrics_by_symbol[symbol],
            candidate_day,
            HORIZON_QUARTERS[horizon],
            target_day,
        )
        outcomes[horizon] = {"stock_return_pct": stock, "revenue": financial["revenue"], "margin": financial["margin"], "eps": financial["eps"]}
    return {
        "event_id": event.get("event_id"),
        "symbol": symbol,
        "classification": classification,
        "event_type": event.get("event_type"),
        "event_subtype": event.get("event_subtype"),
        "effective_date": event.get("effective_date"),
        "outcomes": outcomes,
    }


def _target_study(
    row: Mapping[str, Any],
    dated: list[dict[str, Any]],
    histories: Mapping[str, list[dict[str, Any]]],
    facts_by_symbol: Mapping[str, list[Mapping[str, Any]]],
    metrics_by_symbol: Mapping[str, list[str]],
) -> dict[str, Any]:
    event = row["event"]
    target_day = parse_date(event.get("effective_date"))
    candidates: list[dict[str, Any]] = []
    excluded_candidates: list[dict[str, Any]] = []
    for other in dated:
        other_day = parse_date(other["event"].get("effective_date"))
        if other["event"].get("event_id") == event.get("event_id"):
            continue
        if other_day is not None and other_day < target_day:
            candidates.append(
                _candidate_study(other["event"], other["symbol"], target_day, histories, facts_by_symbol, metrics_by_symbol)
            )
        else:
            excluded_candidates.append(
                {"event_id": other["event"].get("event_id"), "symbol": other["symbol"], "reason": "effective_date_not_strictly_before_target"}
            )
    candidates.sort(key=lambda item: (item["effective_date"] or "", item["event_id"] or ""))
    excluded_candidates.sort(key=lambda item: (item["symbol"] or "", item["event_id"] or ""))
    aggregates = _aggregates_for(candidates)
    any_available = any(
        class_map[label]["status"] == "available"
        for metric_map in aggregates.values()
        for class_map in metric_map.values()
        for label in AGG_CLASSES
    )
    document_ids = sorted(
        {
            item.get("document_id")
            for item in (event.get("evidence") or [])
            if isinstance(item, Mapping) and isinstance(item.get("document_id"), str)
        }
    )
    return {
        "target_event": {
            "event_id": event.get("event_id"),
            "symbol": SYMBOL,
            "event_type": event.get("event_type"),
            "event_subtype": event.get("event_subtype"),
            "effective_date": event.get("effective_date"),
            "cutoff": event.get("effective_date"),
            "source_document_ids": document_ids,
        },
        "excluded_candidates": excluded_candidates,
        "candidate_count": {
            "same_company": sum(1 for item in candidates if item["classification"] == "same_company"),
            "peer": sum(1 for item in candidates if item["classification"] == "peer"),
            "combined": len(candidates),
        },
        "candidates": candidates,
        "aggregates": aggregates,
        "insufficient_evidence": not any_available,
    }


def build(root: Path | None = None, *, write: bool = True) -> dict[str, Any]:
    """Build the retained MARI E&P analogue envelope from desk state."""
    root = Path(root) if root is not None else ROOT
    events_state = load_json(root / "state" / "company_intel" / "operating_events.json", {})
    companies = events_state.get("companies") if isinstance(events_state, dict) else {}
    events_by_symbol = {symbol: ((companies or {}).get(symbol) or {}).get("events") or [] for symbol in UNIVERSE}
    dated, excluded = select_family_events(events_by_symbol)
    histories = {symbol: _load_history(root, symbol) for symbol in UNIVERSE}
    facts_by_symbol: dict[str, list[Mapping[str, Any]]] = {}
    metrics_by_symbol: dict[str, list[str]] = {}
    for symbol in UNIVERSE:
        facts, metrics, _, _ = _series_views(root, symbol)
        facts_by_symbol[symbol] = facts
        metrics_by_symbol[symbol] = metrics
    targets = [
        _target_study(row, dated, histories, facts_by_symbol, metrics_by_symbol)
        for row in dated
        if row["symbol"] == SYMBOL
    ]
    price_cutoffs = {
        symbol: (histories[symbol][-1].get("date") if histories[symbol] else None) for symbol in UNIVERSE
    }
    series_meta = load_json(root / "state" / "company_financial_series.json", {})
    payload = {
        "schema_version": RESULT_SCHEMA,
        "engine_version": ENGINE_VERSION,
        "symbol": SYMBOL,
        "peer_symbols": list(PEERS),
        "event_family": {
            "event_types": list(FAMILY_EVENT_TYPES),
            "universe": list(UNIVERSE),
            "rationale": "Registry family for E&P exploration/working-interest/discovery events. The retained registry carries MARI's working-interest, exploration-block and farm-out events under acquisition_divestment; discovery/exploration/working_interest types are accepted defensively if the registry ever adds them. Peer coverage is exactly OGDC and PPL.",
            "matching_policy": {
                "candidate_date": "strictly_before_target",
                "price_endpoint": "first_close_on_or_after_calendar_target_and_strictly_before_target_cutoff",
                "price_baseline": "last_close_strictly_before_candidate_event",
                "financial_period": "nth_distinct_period_end_strictly_after_candidate_event",
                "financial_availability": "period_end_and_available_on_strictly_before_target_cutoff",
                "financial_baseline": "period_end_and_available_on_strictly_before_candidate_event",
                "financial_readiness": "model_loadable_facts_only",
                "minimum_aggregate_sample": MIN_SAMPLE,
                "aggregate_method": "median_range_iqr_inclusive_quartiles",
            },
        },
        "minimum_sample": MIN_SAMPLE,
        "data_cutoffs": {
            "price_history_last_date": price_cutoffs,
            "financial_series_updated": (series_meta.get("_meta") or {}).get("updated") if isinstance(series_meta, dict) else None,
        },
        "policy": {
            "descriptive_only": True,
            "no_causal_claim": True,
            "no_forecast_or_valuation": True,
            "no_advice": True,
            "raw_price_return_not_adjusted_or_total_return": True,
            "minimum_aggregate_sample": MIN_SAMPLE,
            "insufficient_evidence_display": INSUFFICIENT_EVIDENCE,
        },
        "symbol_coverage": {symbol: _coverage_row(symbol, dated, excluded, root) for symbol in UNIVERSE},
        "target_count": len(targets),
        "targets": targets,
        "limitations": [
            "Raw close-to-close price returns; not adjusted for dividends, splits or index effects, and not total returns.",
            "Descriptive historical association only; outcomes are labels, never causal attribution.",
            "Aggregates are suppressed below the minimum sample and never average thin samples into a benchmark.",
            "Financial outcomes require model-loadable facts; audit-only retained facts fail closed.",
            "Peer coverage depends on retained registry events; OGDC and PPL currently retain no family events, so peer evidence is empty rather than assumed.",
            "Historical selection is limited to the retained registry and price window; survivorship and coverage bias are not corrected.",
        ],
        "source": [
            "state/company_intel/operating_events.json",
            "state/history/MARI.json",
            "state/history/OGDC.json",
            "state/history/PPL.json",
            "state/company_financial_series.json",
        ],
    }
    violations = validate_output(payload)
    if violations:
        raise ValueError("mari_enp_analogue_engine: invalid output: " + "; ".join(violations[:6]))
    if write:
        existing = load_json(OUT, {})
        if isinstance(existing, dict) and isinstance(existing.get("_meta"), dict):
            payload["_meta"] = existing["_meta"]
        save_json(OUT, payload)
    suppressed = sum(
        1
        for target in targets
        for metric_map in target["aggregates"].values()
        for class_map in metric_map.values()
        for label in AGG_CLASSES
        if class_map[label]["status"] == "suppressed"
    )
    total = len(targets) * len(HORIZON_ORDER) * len(OUTCOME_METRICS) * len(AGG_CLASSES)
    print(
        f"mari_enp_analogue_engine: {len(targets)} targets, {suppressed}/{total} aggregates suppressed (n < {MIN_SAMPLE})"
        + (f" -> {OUT.relative_to(ROOT)}" if write else "")
    )
    return payload


def fingerprint(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    ).hexdigest()


def main() -> None:
    build(write=True)


if __name__ == "__main__":
    main()
