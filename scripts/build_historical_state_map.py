"""Build CI Historical State Map.

This is the CI-native version of "find past setups like this one": it links an
observed Intelligence Case to the event study, conditional benchmark, and
pre-event market setup already retained in state.  It does not search the web,
invent peer examples, compute forecasts, or make causal claims.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import date
from typing import Any, Mapping

import event_studies
from psx_data import STATE, load_json, save_json


PRODUCT_VERSION = "historical_state_map_v1"
OUT = STATE / "company_intel" / "historical_state_map.json"
SOURCE_PATHS = {
    "intelligence_cases": "state/company_intel/intelligence_cases.json",
    "operating_events": "state/company_intel/operating_events.json",
    "event_studies": "state/company_intel/event_studies.json",
    "conditional_benchmarks": "state/company_intel/conditional_benchmarks.json",
    "financial_truth_qualification": "state/company_intel/financial_truth_qualification.json",
    "history": "state/history/{symbol}.json",
    "indices": "state/indices.json",
}
TRADING_WINDOWS = (5, 15, 60)
HORIZONS = ("1Q", "2Q", "4Q", "8Q")
MIN_SAMPLE = 3
ALPHA_CASES = {
    "MARI": "A_e_and_p",
    "MLCF": "B_industrial_cement",
    "PSO": "C_sales_led",
}


def _as_date(value: Any) -> date | None:
    if isinstance(value, str) and len(value) >= 10:
        return event_studies.parse_date(value[:10])
    return None


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _stable_id(*parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return "hstate_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _load_history(symbol: str) -> list[dict[str, Any]]:
    rows = load_json(STATE / "history" / f"{symbol}.json", [])
    if not isinstance(rows, list):
        return []
    return sorted([row for row in rows if isinstance(row, dict)], key=lambda row: str(row.get("date") or ""))


def _case_event_id(case: Mapping[str, Any]) -> str | None:
    for fact in case.get("observed_facts") or []:
        if isinstance(fact, Mapping) and fact.get("source_event_id"):
            return str(fact["source_event_id"])
    for row in case.get("source_lineage") or []:
        if not isinstance(row, Mapping):
            continue
        for key in ("canonical_event_id", "event_id"):
            if row.get(key):
                return str(row[key])
    return None


def _operating_event_by_id(operating_events: Mapping[str, Any], symbol: str, event_id: str | None) -> dict[str, Any] | None:
    if not event_id:
        return None
    for event in (((operating_events.get("companies") or {}).get(symbol) or {}).get("events") or []):
        if isinstance(event, dict) and event.get("event_id") == event_id:
            return event
    return None


def _best_event_match(
    *,
    case: Mapping[str, Any],
    event_id: str | None,
    operating_events: Mapping[str, Any],
    event_study_state: Mapping[str, Any],
) -> tuple[str | None, dict[str, Any] | None, str]:
    symbol = str(case.get("symbol") or "")
    direct = _operating_event_by_id(operating_events, symbol, event_id)
    if direct:
        return event_id, direct, "direct_case_event_id"
    legacy = (case.get("legacy_event_binding") or {}).get("canonical_event_id")
    if legacy:
        event = _operating_event_by_id(operating_events, symbol, str(legacy))
        if event:
            return str(legacy), event, "legacy_canonical_event_id"
    case_date = _as_date(case.get("as_of"))
    if case.get("source_lineage"):
        first = next((row for row in case.get("source_lineage") or [] if isinstance(row, Mapping)), {})
        case_date = _as_date(first.get("event_date") or first.get("document_published_at")) or case_date
    family = str(case.get("case_family") or "")
    type_text = str(case.get("case_type") or "")
    candidates = []
    for event in (((operating_events.get("companies") or {}).get(symbol) or {}).get("events") or []):
        if not isinstance(event, dict):
            continue
        study = (event_study_state.get("studies") or {}).get(event.get("event_id"))
        if not study:
            continue
        event_date = _as_date(event.get("effective_date"))
        if case_date and event_date and abs((case_date - event_date).days) > 370:
            continue
        text = " ".join(str(event.get(key) or "") for key in ("event_type", "event_subtype", "description")).lower()
        score = 0
        for token in (family, type_text):
            for part in token.replace("_", " ").split():
                if len(part) > 3 and part.lower() in text:
                    score += 1
        if score:
            candidates.append((score, str(event.get("event_id")), event))
    candidates.sort(key=lambda row: (-row[0], row[1]))
    if candidates:
        return candidates[0][1], candidates[0][2], "nearest_event_type_text_match"
    return event_id, None, "no_operating_event_match"


def _pre_event_market_setup(symbol: str, effective_date: Any, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    event_day = _as_date(effective_date)
    history = rows if rows is not None else _load_history(symbol)
    eligible = [row for row in history if (d := _as_date(row.get("date"))) and (event_day is None or d < event_day)]
    baseline = eligible[-1] if eligible else None
    windows: dict[str, Any] = {}
    for sessions in TRADING_WINDOWS:
        key = f"{sessions}d"
        if not baseline or len(eligible) <= sessions:
            windows[key] = {
                "status": "unavailable",
                "return_pct": None,
                "start_date": None,
                "end_date": baseline.get("date") if baseline else None,
                "reason": "insufficient_pre_event_history",
            }
            continue
        start = eligible[-(sessions + 1)]
        start_close = _finite(start.get("close"))
        end_close = _finite(baseline.get("close"))
        value = ((end_close / start_close) - 1.0) * 100.0 if start_close and end_close else None
        windows[key] = {
            "status": "available" if value is not None else "unavailable",
            "return_pct": value,
            "start_date": start.get("date"),
            "end_date": baseline.get("date"),
            "reason": None if value is not None else "missing_pre_event_close",
        }
    recent_volumes = [_finite(row.get("volume")) for row in eligible[-5:]]
    long_volumes = [_finite(row.get("volume")) for row in eligible[-60:]]
    recent = [value for value in recent_volumes if value is not None]
    long = [value for value in long_volumes if value is not None]
    volume_ratio = None
    if recent and long and statistics.median(long) not in (0, None):
        volume_ratio = statistics.median(recent) / statistics.median(long)
    return {
        "status": "available" if baseline else "unavailable",
        "event_date": event_day.isoformat() if event_day else None,
        "baseline": {
            "date": baseline.get("date") if baseline else None,
            "close": baseline.get("close") if baseline else None,
            "provenance": {"history_file": f"state/history/{symbol}.json"},
        },
        "pre_event_returns": windows,
        "pre_event_volume": {
            "status": "available" if volume_ratio is not None else "unavailable",
            "median_5_session_to_60_session_ratio": volume_ratio,
            "reason": None if volume_ratio is not None else "insufficient_or_missing_volume_history",
        },
        "policy": {
            "strictly_pre_event": True,
            "raw_price_not_adjusted_or_total_return": True,
        },
    }


def _benchmark_for_event(benchmarks: Mapping[str, Any], symbol: str, event_id: str | None) -> dict[str, Any] | None:
    if not event_id:
        return None
    row = (benchmarks.get("companies") or {}).get(symbol) or {}
    for benchmark in row.get("benchmarks") or []:
        target = benchmark.get("target_event") or {}
        if isinstance(benchmark, dict) and target.get("event_id") == event_id:
            return benchmark
    return None


def _benchmark_projection(benchmark: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(benchmark, Mapping):
        return {
            "status": "no_benchmark_row",
            "strict_candidate_count": 0,
            "aggregate_ready_horizons": [],
            "horizon_aggregates": {horizon: {"status": "suppressed", "n": 0, "reason": "no_benchmark_row"} for horizon in HORIZONS},
        }
    ledger = benchmark.get("readiness_ledger") or {}
    aggregates = {}
    for horizon in HORIZONS:
        row = (benchmark.get("horizon_aggregates") or {}).get(horizon) or {}
        n = int(row.get("n") or 0)
        status = row.get("status")
        aggregates[horizon] = {
            "status": "available" if status == "available" and n >= MIN_SAMPLE else "suppressed",
            "n": n,
            "reason": None if status == "available" and n >= MIN_SAMPLE else (row.get("reason") or "n_lt_3"),
            "stats": row.get("stats") if status == "available" and n >= MIN_SAMPLE else {
                "mean_return_pct": None,
                "median_return_pct": None,
                "min_return_pct": None,
                "max_return_pct": None,
            },
        }
    return {
        "status": benchmark.get("status") or "unknown",
        "strict_candidate_count": int(ledger.get("strict_candidate_count") or 0),
        "aggregate_ready_horizons": list(ledger.get("aggregate_ready_horizons") or []),
        "candidate_evidence_summary": benchmark.get("candidate_evidence_summary") or {},
        "horizon_aggregates": aggregates,
        "policy": benchmark.get("matching_policy") or {},
    }


def _event_study_projection(study: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(study, Mapping):
        return {"status": "no_event_study", "baseline": None, "horizons": {}, "kse100_relative": None}
    horizons = {}
    for horizon in HORIZONS:
        row = (study.get("horizons") or {}).get(horizon) or {}
        horizons[horizon] = {
            "status": row.get("status"),
            "return_pct": row.get("return_pct") if row.get("status") == "mature" else None,
            "target_date": row.get("target_date"),
            "selected_date": row.get("selected_date"),
            "reason": row.get("reason"),
            "provenance": row.get("provenance"),
        }
    return {
        "status": "available",
        "study_id": study.get("study_id"),
        "data_cutoff": study.get("data_cutoff"),
        "baseline": study.get("baseline"),
        "horizons": horizons,
        "kse100_relative": study.get("kse100_relative"),
        "limitations": study.get("limitations") or [],
    }


def _financial_truth_projection(truth: Mapping[str, Any], symbol: str) -> dict[str, Any]:
    row = (truth.get("companies") or {}).get(symbol) or {}
    return {
        "status": row.get("status") or "not_generated",
        "blocks_formal_outputs": row.get("status") != "qualified",
        "reason": row.get("reason") or row.get("status_reason"),
        "annual": ((row.get("model_ready_financial_statement_coverage") or {}).get("annual") or {}),
        "reported_quarter": ((row.get("model_ready_financial_statement_coverage") or {}).get("reported_quarter") or {}),
    }


def _context_for_case(
    case: Mapping[str, Any],
    *,
    operating_events: Mapping[str, Any],
    event_study_state: Mapping[str, Any],
    benchmarks: Mapping[str, Any],
    truth: Mapping[str, Any],
) -> dict[str, Any]:
    symbol = str(case.get("symbol") or "")
    case_event_id = _case_event_id(case)
    event_id, event, match_policy = _best_event_match(
        case=case,
        event_id=case_event_id,
        operating_events=operating_events,
        event_study_state=event_study_state,
    )
    study = (event_study_state.get("studies") or {}).get(event_id) if event_id else None
    benchmark = _benchmark_for_event(benchmarks, symbol, event_id)
    effective_date = (event or {}).get("effective_date") or case.get("effective_date") or case.get("as_of")
    analogue = _benchmark_projection(benchmark)
    market = _pre_event_market_setup(symbol, effective_date)
    financial_truth = _financial_truth_projection(truth, symbol)
    ready_horizons = analogue.get("aggregate_ready_horizons") or []
    return {
        "map_id": _stable_id(symbol, case.get("case_id"), event_id),
        "case": {
            "case_id": case.get("case_id"),
            "symbol": symbol,
            "case_family": case.get("case_family"),
            "case_type": case.get("case_type"),
            "status": case.get("status"),
            "epistemic_type": case.get("epistemic_type"),
            "as_of": case.get("as_of"),
            "alpha_lane": ALPHA_CASES.get(symbol),
        },
        "event_binding": {
            "case_event_id": case_event_id,
            "matched_operating_event_id": event_id,
            "match_policy": match_policy,
            "effective_date": effective_date,
            "event_type": (event or {}).get("event_type"),
            "event_subtype": (event or {}).get("event_subtype"),
            "source_quality_level": (event or {}).get("source_quality_level"),
            "source_lineage": case.get("source_lineage") or [],
        },
        "current_state_vector": {
            "market_setup": market,
            "operating_event": {
                "status": "available" if event else "blocked",
                "affected_drivers": (event or {}).get("affected_drivers") or [],
                "estimated_scale": (event or {}).get("estimated_scale"),
                "evidence_count": len((event or {}).get("evidence") or []),
            },
            "financial_truth": financial_truth,
            "policy_regime": {
                "status": "unavailable",
                "reason": "macro_policy_regime_model_not_qualified",
                "load_bearing_gap": True,
            },
        },
        "past_context": {
            "semantics": "historical_context/not_forecast",
            "evidence_trust_separation": "Similarity is descriptive past context and strictly separate from evidence trust or forward valuation.",
            "event_study": _event_study_projection(study),
            "strict_analogue_benchmark": analogue,
            "usable_for_scenario_calibration": bool(ready_horizons) and financial_truth["status"] == "qualified",
            "calibration_blockers": [
                reason for reason, blocked in (
                    ("financial_truth_not_qualified", financial_truth["status"] != "qualified"),
                    ("no_minimum_strict_analogue_sample", not ready_horizons),
                ) if blocked
            ],
        },
        "answer_contract": {
            "can_answer_then_vs_now": bool(event and market.get("status") == "available"),
            "can_publish_benchmark_stats": bool(ready_horizons),
            "can_feed_forecast_or_valuation": False,
            "why": "Historical state context is descriptive until financial truth, sector-model inputs, and analogue sample gates pass.",
        },
    }


def build(*, write: bool = True) -> dict[str, Any]:
    cases = load_json(STATE / "company_intel" / "intelligence_cases.json", {"companies": {}, "selected_symbols": []})
    operating_events = load_json(STATE / "company_intel" / "operating_events.json", {"companies": {}})
    studies = load_json(STATE / "company_intel" / "event_studies.json", {"studies": {}})
    benchmarks = load_json(STATE / "company_intel" / "conditional_benchmarks.json", {"companies": {}})
    truth = load_json(STATE / "company_intel" / "financial_truth_qualification.json", {"companies": {}})
    selected = [str(symbol) for symbol in cases.get("selected_symbols") or []]
    contexts = []
    for symbol in selected:
        for case in (((cases.get("companies") or {}).get(symbol) or {}).get("cases") or []):
            if isinstance(case, Mapping):
                contexts.append(_context_for_case(
                    case,
                    operating_events=operating_events,
                    event_study_state=studies,
                    benchmarks=benchmarks,
                    truth=truth,
                ))
    summary = {
        "selected_symbols": selected,
        "context_count": len(contexts),
        "observed_context_count": sum(1 for row in contexts if (row.get("case") or {}).get("status") == "Observed"),
        "with_pre_event_market_setup": sum(1 for row in contexts if (((row.get("current_state_vector") or {}).get("market_setup") or {}).get("status") == "available")),
        "with_event_study": sum(
            1
            for row in contexts
            if (((row.get("past_context") or {}).get("event_study") or {}).get("status") == "available")
        ),
        "with_publishable_benchmark_stats": sum(1 for row in contexts if ((row.get("answer_contract") or {}).get("can_publish_benchmark_stats") is True)),
        "usable_for_scenario_calibration": sum(
            1
            for row in contexts
            if ((row.get("past_context") or {}).get("usable_for_scenario_calibration") is True)
        ),
    }
    result = {
        "schema_version": 1,
        "product_version": PRODUCT_VERSION,
        "kind": "historical_state_map",
        "status": "available" if contexts else "blocked",
        "reason": None if contexts else "no_selected_intelligence_cases",
        "source_paths": SOURCE_PATHS,
        "summary": summary,
        "contexts": contexts,
        "policy": {
            "retained_state_only": True,
            "strict_no_lookahead": True,
            "descriptive_not_causal": True,
            "no_forecast_or_valuation_activation": True,
            "minimum_sample_three_for_benchmark_stats": True,
        },
        "inspired_by": {
            "concept": "historical setup matching",
            "implementation_boundary": "CI uses its own retained filings, price history, event studies, and financial-truth gates; no proprietary matching method is copied.",
        },
    }
    if write:
        save_json(OUT, result)
        print(f"historical_state_map: {summary['context_count']} contexts, {summary['with_publishable_benchmark_stats']} publishable benchmark rows")
    return result


if __name__ == "__main__":
    build()
