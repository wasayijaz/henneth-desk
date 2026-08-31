"""Evidence Watchlist v1 for the exact Company Intelligence pilot.

The watchlist is a thin deterministic index over already-retained CI products.
It does not read private user theses, prices, valuations, forecasts, or broad
text stores. Every item is keyed by exact source IDs from the same company.
"""
from __future__ import annotations

import hashlib
from typing import Any


SCHEMA_VERSION = 1
WATCHLIST_VERSION = "evidence_watchlist_v1"
ITEM_STATUSES = {"watching", "confirmed", "contradicted", "blocked"}
FORBIDDEN_TEXT = (
    "buy",
    "sell",
    "recommend",
    "target price",
    "fair value",
    "upside",
    "downside",
    "probability",
    "odds",
    "forecast",
    "valuation",
    "price",
    "should",
    "supabase",
    "company_theses",
)


def _stable_id(prefix: str, *parts: Any) -> str:
    text = "\x1f".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(text.encode('utf-8')).hexdigest()[:20]}"


def _source_as_of(*states: dict[str, Any]) -> dict[str, str]:
    names = (
        "thesis_monitoring",
        "management_delivery",
        "intelligence_confidence",
        "financial_model_inputs",
        "financial_truth_qualification",
        "operating_events",
        "signal_clusters",
    )
    return {
        name: str(state.get("as_of") or "unknown")
        for name, state in zip(names, states)
    }


def _derived_as_of(source_as_of: dict[str, str]) -> str:
    values = sorted(v for v in source_as_of.values() if v and v != "unknown")
    return values[-1] if values else "unknown"


def _delivery_item_status(delivery_status: str | None) -> str:
    if delivery_status == "confirmed":
        return "confirmed"
    if delivery_status == "contradicted":
        return "contradicted"
    if delivery_status == "blocked_no_guidance_objects":
        return "blocked"
    return "watching"


def _assessment_by_cluster(confidence_row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row.get("source_cluster_id"): row
        for row in confidence_row.get("assessments") or []
        if isinstance(row, dict) and row.get("source_cluster_id")
    }


def _cluster_by_id(signal_row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row.get("cluster_id"): row
        for row in signal_row.get("clusters") or []
        if isinstance(row, dict) and row.get("cluster_id")
    }


def _record_by_thesis(delivery_row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row.get("thesis_id"): row
        for row in delivery_row.get("records") or []
        if isinstance(row, dict) and row.get("thesis_id")
    }


def _event_ids(cluster: dict[str, Any]) -> list[str]:
    ids = []
    for obs in cluster.get("observations") or []:
        event_id = obs.get("event_id")
        if event_id and event_id not in ids:
            ids.append(event_id)
    return ids


def _evidence_refs(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs = []
    seen = set()
    for group in groups:
        for evidence in group or []:
            if not isinstance(evidence, dict):
                continue
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
                "content_sha256": evidence.get("content_sha256"),
                "evidence_sha256": evidence.get("evidence_sha256"),
                "source_url": evidence.get("source_url"),
                "source": evidence.get("source"),
                "page": evidence.get("page"),
            })
    return refs


def _watch_item(
    symbol: str,
    thesis: dict[str, Any],
    cluster: dict[str, Any],
    delivery: dict[str, Any],
    assessment: dict[str, Any] | None,
    model_row: dict[str, Any],
    truth_row: dict[str, Any],
) -> dict[str, Any]:
    matched = delivery.get("matched_event") if isinstance(delivery.get("matched_event"), dict) else None
    confidence_link = delivery.get("confidence_link") if isinstance(delivery.get("confidence_link"), dict) else None
    reasons = delivery.get("reasons") or []
    source_evidence = _evidence_refs(thesis.get("evidence") or [], (delivery.get("source_assertion") or {}).get("evidence") or [])
    matched_evidence = _evidence_refs(matched.get("evidence") or []) if matched else []
    prove_checks = thesis.get("prove_checks") or []
    kill_checks = thesis.get("kill_checks") or []
    watch_items = thesis.get("watch_items") or []
    confidence_id = (confidence_link or {}).get("confidence_id") or (assessment or {}).get("confidence_id")
    confidence_band = (confidence_link or {}).get("band") or (assessment or {}).get("band")
    truth_qualified = truth_row.get("status") == "qualified"
    model_status = model_row.get("status") or "unknown"
    model_flags = list(model_row.get("quality_flags") or [])
    readiness_flags = list(model_flags)
    if not truth_qualified and "financial_truth_not_qualified" not in readiness_flags:
        readiness_flags.append("financial_truth_not_qualified")
    readiness = {
        "status": "qualified" if truth_qualified else "not_qualified",
        "downstream_status": truth_row.get("downstream") or {},
        "quality_flags": readiness_flags,
        "model_input_readiness": {"status": model_status, "quality_flags": model_flags},
    }
    return {
        "watch_id": _stable_id(
            "evidence_watch",
            symbol,
            thesis.get("thesis_id"),
            thesis.get("source_cluster_id"),
            delivery.get("delivery_id"),
        ),
        "symbol": symbol,
        "status": _delivery_item_status(delivery.get("status")),
        "thesis_status": thesis.get("status"),
        "monitoring_state": thesis.get("monitoring_state"),
        "thesis_type": thesis.get("thesis_type"),
        "monitored_assertion": thesis.get("monitored_assertion"),
        "delivery_status": delivery.get("status"),
        "confidence_band": confidence_band,
        "financial_readiness_status": readiness["status"],
        "status_reason": reasons[0] if reasons else "exact official-source monitoring remains active",
        "confirmation_check": prove_checks,
        "break_check": kill_checks,
        "next_evidence": watch_items,
        "confidence": {"confidence_id": confidence_id, "band": confidence_band},
        "financial_readiness": readiness,
        "source_evidence": source_evidence,
        "matched_evidence": matched_evidence,
        "policy_flags": ["research_only", "no_advice", "no_odds_claims", "no_forward_estimates", "no_price_claims", "no_valuation_claims"],
        "ids": {
            "thesis_id": thesis.get("thesis_id"),
            "source_cluster_id": thesis.get("source_cluster_id"),
            "delivery_id": delivery.get("delivery_id"),
            "confidence_id": confidence_id,
            "assertion_key": thesis.get("assertion_key"),
            "conflict_key": thesis.get("conflict_key"),
            "source_event_ids": thesis.get("linked_event_ids") or _event_ids(cluster),
            "matched_event_id": (matched or {}).get("event_id"),
        },
        "source_assertion": {
            "available_at": (delivery.get("source_assertion") or {}).get("available_at"),
            "evidence": source_evidence,
        },
        "matched_event": None if not matched else {
            "event_id": matched.get("event_id"),
            "status": delivery.get("status"),
            "match_rule": matched.get("match_rule"),
            "available_at": matched.get("available_at"),
            "evidence": matched_evidence,
        },
        "checks": {
            "prove": prove_checks,
            "kill": kill_checks,
            "watch": watch_items,
        },
        "reasons": reasons,
        "limitations": delivery.get("limitations") or [],
    }


def build_evidence_watchlist(
    thesis_state: dict[str, Any],
    management_delivery_state: dict[str, Any],
    confidence_state: dict[str, Any],
    financial_model_state: dict[str, Any],
    financial_truth_state: dict[str, Any],
    operating_events_state: dict[str, Any],
    signal_state: dict[str, Any],
    *,
    pilot_symbols: list[str] | None = None,
) -> dict[str, Any]:
    symbols = list(pilot_symbols or thesis_state.get("pilot_symbols") or signal_state.get("pilot_symbols") or [])
    source_as_of = _source_as_of(
        thesis_state,
        management_delivery_state,
        confidence_state,
        financial_model_state,
        financial_truth_state,
        operating_events_state,
        signal_state,
    )
    companies = {}
    active_symbols = []
    for symbol in symbols:
        thesis_row = (thesis_state.get("companies") or {}).get(symbol) or {}
        delivery_row = (management_delivery_state.get("companies") or {}).get(symbol) or {}
        confidence_row = (confidence_state.get("companies") or {}).get(symbol) or {}
        model_row = (financial_model_state.get("companies") or {}).get(symbol) or {}
        truth_row = (financial_truth_state.get("companies") or {}).get(symbol) or {}
        signal_row = (signal_state.get("companies") or {}).get(symbol) or {}
        clusters = _cluster_by_id(signal_row)
        delivery_records = _record_by_thesis(delivery_row)
        assessments = _assessment_by_cluster(confidence_row)
        items = []
        for thesis in thesis_row.get("theses") or []:
            if not isinstance(thesis, dict):
                continue
            cluster_id = thesis.get("source_cluster_id")
            delivery = delivery_records.get(thesis.get("thesis_id"))
            cluster = clusters.get(cluster_id)
            if not delivery or not cluster:
                continue
            items.append(_watch_item(
                symbol,
                thesis,
                cluster,
                delivery,
                assessments.get(cluster_id),
                model_row,
                truth_row,
            ))
        if items:
            active_symbols.append(symbol)
        status_counts = {status: sum(1 for item in items if item.get("status") == status) for status in sorted(ITEM_STATUSES)}
        companies[symbol] = {
            "symbol": symbol,
            "status": "active_watch" if items else "no_active_watch",
            "status_reason": "active deterministic thesis monitoring" if items else "no active deterministic thesis emitted",
            "active_watch_count": len(items),
            "status_counts": status_counts,
            "financial_readiness": {
                "status": "qualified" if truth_row.get("status") == "qualified" else "not_qualified",
                "downstream_status": truth_row.get("downstream") or {},
                "quality_flags": list(model_row.get("quality_flags") or []) + ([] if truth_row.get("status") == "qualified" else ["financial_truth_not_qualified"]),
                "model_input_readiness": {"status": model_row.get("status") or "unknown", "quality_flags": model_row.get("quality_flags") or []},
            },
            "items": items,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "watchlist_version": WATCHLIST_VERSION,
        "as_of": _derived_as_of(source_as_of),
        "source_as_of": source_as_of,
        "pilot_symbols": symbols,
        "source": {
            "thesis_monitoring": "state/company_intel/thesis_monitoring.json",
            "management_delivery": "state/company_intel/management_delivery.json",
            "intelligence_confidence": "state/company_intel/intelligence_confidence.json",
            "financial_model_inputs": "state/company_intel/financial_model_inputs.json",
            "financial_truth_qualification": "state/company_intel/financial_truth_qualification.json",
            "operating_events": "state/company_intel/operating_events.json",
            "signal_clusters": "state/company_intel/signal_clusters.json",
        },
        "policy": {
            "research_only": True,
            "no_advice": True,
            "categorical_only": True,
            "no_odds_claims": True,
            "no_forward_estimates": True,
            "no_price_claims": True,
            "no_valuation_claims": True,
            "official_source_provenance_required": True,
            "same_company_exact_id_links_required": True,
            "private_user_theses_excluded": True,
        },
        "status_vocabulary": sorted(ITEM_STATUSES),
        "summary": {
            "coverage": "active_watch_present" if active_symbols else "no_active_watch",
            "active_symbols": active_symbols,
            "company_count": len(symbols),
            "active_company_count": len(active_symbols),
            "active_watch_count": sum(len((companies.get(symbol) or {}).get("items") or []) for symbol in symbols),
        },
        "companies": companies,
    }
