"""Deterministic Intelligence Confidence v1 for retained CI signal clusters.

This module scores only retained signal clusters. It does not value,
recommend, or attach odds. Every component is a fixed mapping over
already-persisted state:

* source_reliability: best retained source_quality_level in the cluster.
* signal_independence: distinct originators only; PSX vs issuer distribution of
  the same official disclosure is not independent corroboration.
* historical_precedent: strict no-lookahead analogues from event_studies.
* financial_model_quality: financial-truth qualification, with model-input
  readiness retained as descriptive provenance only.
* peer_evidence: strict no-lookahead peer analogues from event_studies.
* data_completeness: retained evidence/proposition/financial coverage.
* recency: effective/detected date distance from signal_state.as_of.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any


SCHEMA_VERSION = 1
CONFIDENCE_VERSION = "intelligence_confidence_v2"
PKT = timezone(timedelta(hours=5))

COMPONENT_WEIGHTS = {
    "source_reliability": 20,
    "signal_independence": 20,
    "historical_precedent": 20,
    "financial_model_quality": 15,
    "peer_evidence": 10,
    "data_completeness": 10,
    "recency": 5,
}

BANDS = {
    "low": {"min": 0, "max": 49.9999},
    "medium": {"min": 50, "max": 74.9999},
    "high": {"min": 75, "max": 100},
}

MODEL_READINESS_SCORES = {
    "ready": 100,
    "complete": 100,
    "partial": 60,
    "unsupported_sector_model": 35,
    "blocked_missing_snapshot_inputs": 25,
    "unknown": 20,
}

FORBIDDEN_TEXT = (
    "buy",
    "sell",
    "recommend",
    "target price",
    "upside",
    "downside",
    "probability",
    "forecast",
    "guarantee",
    "should",
)


def _stable_id(prefix: str, *parts: Any) -> str:
    text = "\x1f".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:20]}"


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) == 10:
        text = f"{text}T00:00:00"
    elif len(text) == 16 and " " in text:
        text = text.replace(" ", "T") + ":00"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=PKT)
    return parsed.astimezone(PKT)


def _date_days_old(value: Any, as_of: Any) -> int | None:
    event_time = _parse_time(value)
    cutoff = _parse_time(as_of)
    if not event_time or not cutoff:
        return None
    return (cutoff.date() - event_time.date()).days


def _clamp_score(value: float | int | None) -> int:
    if value is None:
        return 0
    return int(round(max(0, min(100, float(value)))))


def _component(name: str, raw_facts: dict[str, Any], score: float | int, rationale: str) -> dict[str, Any]:
    weight = COMPONENT_WEIGHTS[name]
    normalized = _clamp_score(score)
    return {
        "weight": weight,
        "raw_facts": raw_facts,
        "normalized_score": normalized,
        "weighted_points": round(normalized * weight / 100, 2),
        "rationale": rationale,
    }


def _band(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def _source_reliability(cluster: dict[str, Any]) -> dict[str, Any]:
    levels = []
    evidence_rows = 0
    for obs in cluster.get("observations") or []:
        evidence = obs.get("evidence") or {}
        if isinstance(evidence.get("source_quality_level"), int):
            levels.append(evidence["source_quality_level"])
        if evidence.get("content_sha256") and evidence.get("evidence_sha256"):
            evidence_rows += 1
    best = min(levels) if levels else None
    score = {1: 100, 2: 70, 3: 45}.get(best, 0)
    return _component(
        "source_reliability",
        {"source_quality_levels": sorted(set(levels)), "evidence_rows": evidence_rows},
        score,
        "Mapped from retained official-source quality levels: 1=100, 2=70, 3=45, missing=0.",
    )


def _signal_independence(cluster: dict[str, Any]) -> dict[str, Any]:
    originators = sorted({o for o in cluster.get("originators") or [] if o})
    distributors = sorted({d for d in cluster.get("distributors") or [] if d})
    independent = len(originators)
    if independent >= 3:
        score = 100
    elif independent == 2:
        score = 75
    elif independent == 1:
        score = 25
    else:
        score = 0
    return _component(
        "signal_independence",
        {"distinct_originators": independent, "originators": originators, "distributors": distributors},
        score,
        "Only distinct originators count; distributor copies of one official source do not add corroboration.",
    )


def _event_study_for_cluster(cluster: dict[str, Any], studies_by_event: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for obs in cluster.get("observations") or []:
        event_id = obs.get("event_id")
        study = studies_by_event.get(event_id)
        if isinstance(study, dict):
            return study
    return None


def _mature_horizon_count(study: dict[str, Any]) -> int:
    return sum(1 for row in (study.get("horizons") or {}).values() if (row or {}).get("status") == "mature")


def _strict_analogues(study: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for analogue in study.get("analogues") or []:
        if not isinstance(analogue, dict):
            continue
        event_date = analogue.get("effective_date") or analogue.get("event_date")
        target_date = study.get("effective_date")
        if event_date and target_date and str(event_date) >= str(target_date):
            continue
        rows.append(analogue)
    return rows


def _historical_precedent(cluster: dict[str, Any], studies_by_event: dict[str, dict[str, Any]]) -> dict[str, Any]:
    study = _event_study_for_cluster(cluster, studies_by_event)
    analogues = _strict_analogues(study or {})
    mature = _mature_horizon_count(study or {})
    n = len(analogues)
    if n >= 5 and mature >= 2:
        score = 100
    elif n >= 3 and mature >= 1:
        score = 75
    elif n >= 1:
        score = 50
    elif mature >= 1:
        score = 25
    else:
        score = 0
    return _component(
        "historical_precedent",
        {"study_id": (study or {}).get("study_id"), "strict_analogue_count": n, "mature_horizon_count": mature},
        score,
        "Uses only event-study analogues dated before the assessed event; current-event horizons alone cap at 25.",
    )


def _financial_model_quality(model_row: dict[str, Any], financial_truth_row: dict[str, Any]) -> dict[str, Any]:
    model_status = model_row.get("status") or "unknown"
    financial_truth_status = financial_truth_row.get("status") or "not_qualified"
    observations = model_row.get("observations") or {}
    derived = model_row.get("derived") or {}
    observation_count = sum(len(v or []) for v in observations.values() if isinstance(v, list))
    derived_count = sum(len(v or []) for v in derived.values() if isinstance(v, list))
    if financial_truth_status == "qualified":
        score = MODEL_READINESS_SCORES.get(model_status, 20)
        if model_status == "partial" and observation_count >= 6 and derived_count >= 2:
            score = 75
        rationale = "Financial-truth qualification passed; score is then mapped from retained model-input readiness."
    else:
        score = 0
        rationale = "Financial-truth qualification has not passed, so legacy model-input readiness cannot contribute financial-model confidence."
    return _component(
        "financial_model_quality",
        {
            "status": financial_truth_status,
            "financial_truth_status": financial_truth_status,
            "financial_truth_downstream": financial_truth_row.get("downstream") or {},
            "model_input_readiness": {
                "status": model_status,
                "model_version": model_row.get("model_version"),
                "quality_flags": model_row.get("quality_flags") or [],
            },
            "model_version": model_row.get("model_version"),
            "observation_count": observation_count,
            "derived_count": derived_count,
            "quality_flags": (["financial_truth_not_qualified"] if financial_truth_status != "qualified" else []),
        },
        score,
        rationale,
    )


def _peer_evidence(cluster: dict[str, Any], study: dict[str, Any] | None) -> dict[str, Any]:
    symbol = cluster.get("symbol")
    peers = sorted({
        row.get("symbol")
        for row in _strict_analogues(study or {})
        if row.get("symbol") and row.get("symbol") != symbol
    })
    n = len(peers)
    score = 100 if n >= 5 else 75 if n >= 3 else 50 if n >= 1 else 0
    return _component(
        "peer_evidence",
        {"peer_symbol_count": n, "peer_symbols": peers, "study_id": (study or {}).get("study_id")},
        score,
        "Peer evidence is limited to strict no-lookahead analogues in event_studies.",
    )


def _data_completeness(cluster: dict[str, Any], model_row: dict[str, Any]) -> dict[str, Any]:
    observations = cluster.get("observations") or []
    evidence_complete = 0
    for obs in observations:
        evidence = obs.get("evidence") or {}
        required = ("document_id", "content_sha256", "evidence_sha256", "source_url", "page", "text")
        if all(evidence.get(key) for key in required):
            evidence_complete += 1
    prop = cluster.get("proposition") or {}
    prop_fields = [key for key in ("type", "stage", "target", "person", "role", "modality") if prop.get(key)]
    model_status = model_row.get("status") or "unknown"
    score = 0
    if observations:
        score += 35
    if evidence_complete == len(observations) and observations:
        score += 35
    if prop_fields:
        score += 15
    if model_status in {"ready", "complete", "partial"}:
        score += 15
    return _component(
        "data_completeness",
        {
            "observation_count": len(observations),
            "complete_evidence_rows": evidence_complete,
            "proposition_fields": prop_fields,
            "financial_model_status": model_status,
        },
        score,
        "Scores retained evidence, normalized proposition fields, and whether model inputs are at least partial.",
    )


def _recency(cluster: dict[str, Any], as_of: str | None) -> dict[str, Any]:
    dates = []
    for obs in cluster.get("observations") or []:
        dates.append(obs.get("effective_date") or obs.get("detected_at"))
    days = [d for d in (_date_days_old(value, as_of) for value in dates) if d is not None and d >= 0]
    age = min(days) if days else None
    if age is None:
        score = 0
    elif age <= 30:
        score = 100
    elif age <= 90:
        score = 80
    elif age <= 180:
        score = 60
    elif age <= 365:
        score = 40
    else:
        score = 20
    return _component(
        "recency",
        {"as_of": as_of, "age_days": age, "event_dates": sorted(str(d) for d in dates if d)},
        score,
        "Age is measured from retained effective/detected dates against signal_clusters.as_of.",
    )


def _provenance_refs(cluster: dict[str, Any], study: dict[str, Any] | None) -> list[dict[str, Any]]:
    refs = []
    seen = set()
    for obs in cluster.get("observations") or []:
        evidence = obs.get("evidence") or {}
        key = (evidence.get("document_id"), evidence.get("evidence_sha256"), evidence.get("page"))
        if key in seen:
            continue
        seen.add(key)
        refs.append({
            "source_product": "signal_clusters",
            "document_id": evidence.get("document_id"),
            "source_url": evidence.get("source_url"),
            "page": evidence.get("page"),
            "content_sha256": evidence.get("content_sha256"),
            "evidence_sha256": evidence.get("evidence_sha256"),
        })
    if study:
        refs.append({
            "source_product": "event_studies",
            "study_id": study.get("study_id"),
            "event_id": study.get("event_id"),
            "history_file": ((study.get("baseline") or {}).get("provenance") or {}).get("history_file"),
        })
    return refs


def _cluster_assessment(
    symbol: str,
    cluster: dict[str, Any],
    model_row: dict[str, Any],
    financial_truth_row: dict[str, Any],
    studies_by_event: dict[str, dict[str, Any]],
    as_of: str | None,
) -> dict[str, Any]:
    study = _event_study_for_cluster(cluster, studies_by_event)
    components = {
        "source_reliability": _source_reliability(cluster),
        "signal_independence": _signal_independence(cluster),
        "historical_precedent": _historical_precedent(cluster, studies_by_event),
        "financial_model_quality": _financial_model_quality(model_row, financial_truth_row),
        "peer_evidence": _peer_evidence(cluster, study),
        "data_completeness": _data_completeness(cluster, model_row),
        "recency": _recency(cluster, as_of),
    }
    score = round(sum(row["weighted_points"] for row in components.values()), 2)
    cluster_id = cluster.get("cluster_id")
    return {
        "confidence_id": _stable_id("confidence", symbol, cluster_id, as_of),
        "symbol": symbol,
        "source_cluster_id": cluster_id,
        "assertion_key": cluster.get("assertion_key"),
        "cluster_assessment": cluster.get("assessment"),
        "score": score,
        "band": _band(score),
        "band_thresholds": BANDS,
        "components": components,
        "provenance_refs": _provenance_refs(cluster, study),
        "policy_flags": ["research_only", "no_advice", "no_odds_claim", "no_forward_estimate", "no_price_claim"],
    }


def build_intelligence_confidence(
    signal_state: dict[str, Any],
    operating_events: dict[str, Any],
    event_studies: dict[str, Any],
    financial_model_inputs: dict[str, Any],
    financial_truth_qualification: dict[str, Any],
) -> dict[str, Any]:
    symbols = list(signal_state.get("pilot_symbols") or [])
    studies_by_event = {
        study.get("event_id"): study
        for study in (event_studies.get("studies") or {}).values()
        if isinstance(study, dict) and study.get("event_id")
    }
    as_of = signal_state.get("as_of") or "unknown"
    companies = {}
    for symbol in symbols:
        signal_row = (signal_state.get("companies") or {}).get(symbol) or {}
        model_row = (financial_model_inputs.get("companies") or {}).get(symbol) or {}
        financial_truth_row = (financial_truth_qualification.get("companies") or {}).get(symbol) or {}
        clusters = [cluster for cluster in signal_row.get("clusters") or [] if isinstance(cluster, dict)]
        assessments = [
            _cluster_assessment(symbol, cluster, model_row, financial_truth_row, studies_by_event, as_of)
            for cluster in clusters
        ]
        total = round(sum(row["score"] for row in assessments) / len(assessments), 2) if assessments else None
        companies[symbol] = {
            "symbol": symbol,
            "status": "assessed" if assessments else "no_assessments",
            "source_cluster_count": len(clusters),
            "assessment_count": len(assessments),
            "aggregate_score": total,
            "aggregate_band": _band(total) if total is not None else None,
            "aggregate_method": "mean_of_retained_cluster_assessments" if assessments else None,
            "assessments": assessments,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "confidence_version": CONFIDENCE_VERSION,
        "as_of": as_of,
        "pilot_symbols": symbols,
        "component_weights": COMPONENT_WEIGHTS,
        "band_thresholds": BANDS,
        "source": {
            "signal_clusters": "state/company_intel/signal_clusters.json",
            "operating_events": "state/company_intel/operating_events.json",
            "event_studies": "state/company_intel/event_studies.json",
            "financial_model_inputs": "state/company_intel/financial_model_inputs.json",
            "financial_truth_qualification": "state/company_intel/financial_truth_qualification.json",
        },
        "policy": {
            "research_only": True,
            "no_advice": True,
            "no_odds_claims": True,
            "no_forward_estimates": True,
            "no_price_claims": True,
        },
        "operating_event_company_count": len((operating_events.get("companies") or {})),
        "companies": companies,
    }
