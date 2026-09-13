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
    if isinstance(value, date):
        return value
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
    operating_events: Mapping[str, Any],
    event_study_state: Mapping[str, Any],
) -> tuple[str | None, dict[str, Any] | None, str, dict[str, Any] | None]:
    symbol = str(case.get("symbol") or "")
    events = ((operating_events.get("companies") or {}).get(symbol) or {}).get("events") or []

    # 1. Direct canonical event ID in case lineage or observed facts
    for row in case.get("source_lineage") or []:
        if isinstance(row, Mapping):
            for key in ("canonical_event_id", "event_id"):
                cid = row.get(key)
                if cid:
                    ev = _operating_event_by_id(operating_events, symbol, str(cid))
                    if ev:
                        return str(cid), ev, "direct_canonical_event_id", dict(row)
    for fact in case.get("observed_facts") or []:
        if isinstance(fact, Mapping):
            for key in ("source_event_id", "canonical_event_id", "event_id"):
                cid = fact.get(key)
                if cid:
                    ev = _operating_event_by_id(operating_events, symbol, str(cid))
                    if ev:
                        return str(cid), ev, "direct_canonical_event_id", dict(fact)

    # 2. Exact source document provenance (document_id + content_sha256)
    for row in case.get("source_lineage") or []:
        if not isinstance(row, Mapping):
            continue
        doc_id = row.get("document_id")
        doc_sha = row.get("content_sha256")
        if doc_id:
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                for ev_item in ev.get("evidence") or []:
                    if isinstance(ev_item, dict) and ev_item.get("document_id") == doc_id:
                        sha_match = bool(doc_sha and ev_item.get("content_sha256") == doc_sha)
                        policy = "exact_source_document_and_hash" if sha_match else "exact_source_document_id"
                        return ev.get("event_id"), ev, policy, dict(row)

    return None, None, "unbound_no_defensible_operating_event_match", None


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
    event_id, event, match_policy, matched_lineage = _best_event_match(
        case=case,
        operating_events=operating_events,
        event_study_state=event_study_state,
    )
    is_bound = bool(event and event_id and match_policy in ("direct_canonical_event_id", "exact_source_document_and_hash", "exact_source_document_id"))
    effective_date = event.get("effective_date") if (is_bound and event) else None
    detected_at = (event.get("detected_at") or event.get("published_at") or (matched_lineage or {}).get("document_published_at")) if (is_bound and event) else None
    detected_day = _as_date(detected_at[:10]) if isinstance(detected_at, str) and len(detected_at) >= 10 else None
    effective_day = _as_date(effective_date) if effective_date else None
    if detected_day:
        cutoff_date = detected_day
        info_avail = detected_at[:10] if isinstance(detected_at, str) else detected_day.isoformat()
    else:
        cutoff_date = effective_day
        info_avail = effective_date

    study = (event_study_state.get("studies") or {}).get(event_id) if is_bound else None
    benchmark = _benchmark_for_event(benchmarks, symbol, event_id) if is_bound else None
    analogue = _benchmark_projection(benchmark)
    market = _pre_event_market_setup(symbol, cutoff_date) if is_bound and cutoff_date else {
        "status": "unavailable",
        "event_date": None,
        "baseline": {"date": None, "close": None, "provenance": {}},
        "pre_event_returns": {},
        "pre_event_volume": {
            "status": "unavailable",
            "median_5_session_to_60_session_ratio": None,
            "reason": "unbound_operating_event" if not is_bound else "missing_effective_date",
        },
        "policy": {
            "strictly_pre_event": True,
            "raw_price_not_adjusted_or_total_return": True,
        },
    }
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
            "matched_operating_event_id": event_id if is_bound else None,
            "match_policy": match_policy,
            "effective_date": effective_date,
            "information_available_at": info_avail,
            "event_type": (event or {}).get("event_type") if is_bound else None,
            "event_subtype": (event or {}).get("event_subtype") if is_bound else None,
            "source_quality_level": (event or {}).get("source_quality_level") if is_bound else None,
            "matched_source_document_id": (matched_lineage or {}).get("document_id") if matched_lineage else None,
            "matched_content_sha256": (matched_lineage or {}).get("content_sha256") if matched_lineage else None,
            "matched_page": (matched_lineage or {}).get("page") if matched_lineage else None,
            "source_lineage": case.get("source_lineage") or [],
        },
        "current_state_vector": {
            "market_setup": market,
            "operating_event": {
                "status": "available" if is_bound else "blocked",
                "affected_drivers": (event or {}).get("affected_drivers") or [] if is_bound else [],
                "estimated_scale": (event or {}).get("estimated_scale") if is_bound else None,
                "evidence_count": len((event or {}).get("evidence") or []) if is_bound else 0,
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
            "usable_for_scenario_calibration": bool(ready_horizons) and financial_truth["status"] == "qualified" and is_bound,
            "calibration_blockers": [
                reason for reason, blocked in (
                    ("unbound_operating_event", not is_bound),
                    ("financial_truth_not_qualified", financial_truth["status"] != "qualified"),
                    ("no_minimum_strict_analogue_sample", not ready_horizons),
                ) if blocked
            ],
        },
        "answer_contract": {
            "can_answer_then_vs_now": bool(is_bound and event and market.get("status") == "available"),
            "can_publish_benchmark_stats": bool(ready_horizons),
            "can_feed_forecast_or_valuation": False,
            "why": "Historical state context is descriptive until financial truth, sector-model inputs, and analogue sample gates pass.",
        },
    }


def build(*, write: bool = True) -> dict[str, Any]:
    existing = load_json(OUT, {})
    existing_meta = existing.get("_meta") if isinstance(existing, dict) else None
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
    if isinstance(existing_meta, dict):
        result["_meta"] = existing_meta
    if write:
        save_json(OUT, result)
        print(f"historical_state_map: {summary['context_count']} contexts, {summary['with_publishable_benchmark_stats']} publishable benchmark rows")
    return result


if __name__ == "__main__":
    build()
