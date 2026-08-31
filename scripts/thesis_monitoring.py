"""Deterministic thesis-monitoring state for Company Intelligence.

The monitor turns retained signal clusters into source-linked watch items.
It does not forecast, value, recommend, or choose an investment action.
"""
from __future__ import annotations

import hashlib
from typing import Any


FORBIDDEN_TEXT = (
    "buy",
    "sell",
    "recommend",
    "target price",
    "fair value",
    "upside",
    "downside",
    "guarantee",
    "should",
)

PROVE_BY_TYPE = {
    "acquisition": "subsequent official disclosure confirms stage progression or completion",
    "divestment": "subsequent official disclosure confirms stage progression or completion",
    "management_change": "subsequent official disclosure confirms the named person and role are effective",
    "exploration_well_discovery": "subsequent official disclosure reports appraisal, reserve, production, or commercial status",
    "capacity_plant_expansion": "subsequent official disclosure reports commissioning, operating status, or production contribution",
    "debt_refinancing": "subsequent official disclosure reports revised financing terms or repayment progress",
    "contract_tender": "subsequent official disclosure reports award, execution, cancellation, or material scope change",
}

KILL_BY_TYPE = {
    "acquisition": "official disclosure cancels, terminates, rejects, or materially contradicts the same target assertion",
    "divestment": "official disclosure cancels, terminates, rejects, or materially contradicts the same asset assertion",
    "management_change": "official disclosure reverses the named appointment or reports a different effective role",
    "exploration_well_discovery": "official disclosure reports non-commercial, dry, abandoned, or materially adverse appraisal status",
    "capacity_plant_expansion": "official disclosure reports cancellation, indefinite delay, shutdown, or material under-delivery",
    "debt_refinancing": "official disclosure reports default, failed refinancing, or worse terms than the monitored assertion",
    "contract_tender": "official disclosure reports cancellation, loss, non-award, termination, or material scope reduction",
}


def _stable_id(prefix: str, *parts: Any) -> str:
    text = "\x1f".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:20]}"


def _clean_text(value: Any, limit: int = 220) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text[:limit] if text else None


def _prop_text(prop: dict[str, Any]) -> str:
    bits = []
    for key in ("type", "stage", "target", "person", "role", "modality"):
        value = _clean_text(prop.get(key), 120)
        if value:
            bits.append(f"{key}={value}")
    return "; ".join(bits) if bits else "official-source signal"


def _event_ids(cluster: dict[str, Any]) -> list[str]:
    ids = []
    for obs in cluster.get("observations") or []:
        event_id = obs.get("event_id")
        if isinstance(event_id, str) and event_id and event_id not in ids:
            ids.append(event_id)
    return ids


def _evidence_refs(cluster: dict[str, Any]) -> list[dict[str, Any]]:
    refs = []
    seen = set()
    for obs in cluster.get("observations") or []:
        evidence = obs.get("evidence") or {}
        key = (
            evidence.get("document_id"),
            evidence.get("content_sha256"),
            evidence.get("evidence_sha256"),
            evidence.get("page"),
        )
        if key in seen:
            continue
        seen.add(key)
        refs.append({
            "document_id": evidence.get("document_id"),
            "source_url": evidence.get("source_url"),
            "page": evidence.get("page"),
            "content_sha256": evidence.get("content_sha256"),
            "evidence_sha256": evidence.get("evidence_sha256"),
            "source": evidence.get("source"),
        })
    return refs


def _canonical_status(assessment: Any) -> str:
    """Map the retained cluster assessment to the public monitoring vocabulary."""
    value = str(assessment or "").strip().lower()
    if value == "inconsistent":
        return "Broken"
    if value in {"supersession", "superseded"}:
        return "Weakening"
    if value in {"convergent", "corroborated"}:
        return "Strengthening"
    # A single-source or otherwise unclassified retained cluster is not evidence
    # of direction. Keep it explicitly stable rather than inventing momentum.
    return "Stable"


def _cluster_thesis(symbol: str, cluster: dict[str, Any]) -> dict[str, Any]:
    prop = cluster.get("proposition") or {}
    thesis_type = _clean_text(prop.get("type"), 80) or "official_signal"
    cluster_id = cluster.get("cluster_id")
    thesis_id = _stable_id("thesis", symbol, cluster_id, cluster.get("assertion_key"))
    assessment = _clean_text(cluster.get("assessment"), 80) or "unknown_assessment"
    monitoring_state = {
        "inconsistent": "contradicted_or_inconsistent",
        "supersession": "superseded_monitoring",
    }.get(assessment, "active_monitoring")
    return {
        "thesis_id": thesis_id,
        "symbol": symbol,
        "status": _canonical_status(assessment),
        "monitoring_state": monitoring_state,
        "intelligence_type": "inference",
        "source_cluster_id": cluster_id,
        "assessment": assessment,
        "confidence_band": (cluster.get("confidence") or {}).get("band"),
        "assertion_key": cluster.get("assertion_key"),
        "conflict_key": cluster.get("conflict_key"),
        "thesis_type": thesis_type,
        "monitored_assertion": _prop_text(prop),
        "linked_event_ids": _event_ids(cluster),
        "evidence": _evidence_refs(cluster),
        "prove_checks": [
            {
                "check_id": _stable_id("prove", thesis_id, "progression"),
                "source_required": "official_company_or_psx_disclosure",
                "condition": PROVE_BY_TYPE.get(thesis_type, "subsequent official disclosure directly confirms the monitored assertion"),
                "current_status": "not_observed",
            }
        ],
        "kill_checks": [
            {
                "check_id": _stable_id("kill", thesis_id, "contradiction"),
                "source_required": "official_company_or_psx_disclosure",
                "condition": KILL_BY_TYPE.get(thesis_type, "subsequent official disclosure directly contradicts the monitored assertion"),
                "current_status": "not_observed",
            }
        ],
        "watch_items": [
            {
                "watch_id": _stable_id("watch", thesis_id, "same_conflict_key"),
                "watch_type": "official_disclosure_refresh",
                "description": "Monitor future retained operating events with the same conflict key.",
                "source_required": "state/company_intel/operating_events.json",
            },
            {
                "watch_id": _stable_id("watch", thesis_id, "financial_readiness"),
                "watch_type": "model_readiness",
                "description": "Monitor financial model input readiness before any quantified impact can be calculated.",
                "source_required": "state/company_intel/financial_model_inputs.json",
            },
        ],
    }


def _financial_readiness(model_row: dict[str, Any], truth_row: dict[str, Any]) -> dict[str, Any]:
    """Expose the authoritative qualification gate without losing input detail."""
    model_status = model_row.get("status") or "unknown"
    model_downstream = model_row.get("downstream_status") or {}
    model_flags = list(model_row.get("quality_flags") or [])
    truth_status = truth_row.get("status") or "not_qualified"
    truth_downstream = truth_row.get("downstream") or {}
    qualified = truth_status == "qualified"
    flags = list(model_flags)
    if not qualified and "financial_truth_not_qualified" not in flags:
        flags.append("financial_truth_not_qualified")
    return {
        "status": "qualified" if qualified else "not_qualified",
        "downstream_status": truth_downstream,
        "quality_flags": flags,
        "model_input_readiness": {
            "status": model_status,
            "downstream_status": model_downstream,
            "quality_flags": model_flags,
        },
    }


def build_thesis_monitoring(
    signal_state: dict[str, Any],
    financial_model_state: dict[str, Any],
    financial_truth_state: dict[str, Any],
    *,
    as_of: str | None = None,
) -> dict[str, Any]:
    symbols = list(signal_state.get("pilot_symbols") or [])
    companies = {}
    for symbol in symbols:
        signal_row = (signal_state.get("companies") or {}).get(symbol) or {}
        model_row = (financial_model_state.get("companies") or {}).get(symbol) or {}
        truth_row = (financial_truth_state.get("companies") or {}).get(symbol) or {}
        theses = [
            _cluster_thesis(symbol, cluster)
            for cluster in (signal_row.get("clusters") or [])
            if isinstance(cluster, dict)
        ]
        companies[symbol] = {
            "symbol": symbol,
            "status": "active_monitoring" if theses else "no_active_thesis",
            "source_cluster_count": len(signal_row.get("clusters") or []),
            "active_thesis_count": len(theses),
            "financial_readiness": _financial_readiness(model_row, truth_row),
            "theses": theses,
        }
    # ``as_of`` is inherited from the deterministic source products. Never use
    # wall-clock time here: repeated runs over unchanged state must be byte-stable.
    stable_as_of = as_of or signal_state.get("as_of") or financial_model_state.get("as_of") or financial_truth_state.get("as_of") or "unknown"
    return {
        "schema_version": 1,
        "as_of": stable_as_of,
        "pilot_symbols": symbols,
        "source": {
            "signal_clusters": "state/company_intel/signal_clusters.json",
            "financial_model_inputs": "state/company_intel/financial_model_inputs.json",
            "financial_truth_qualification": "state/company_intel/financial_truth_qualification.json",
        },
        "policy": {
            "research_only": True,
            "no_advice": True,
            "no_price_targets": True,
            "no_forecasts": True,
            "source_required": "official_company_or_psx_disclosure",
        },
        "companies": companies,
    }
