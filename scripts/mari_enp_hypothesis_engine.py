"""Pure deterministic evaluator for a MARI observed-event hypothesis register.

This module deliberately stops at evidence and hypothesis lifecycle. It does
not forecast production, estimate value, calculate prices, or emit financial
outputs. All records are injected by the caller and are validated by
``mari_enp_hypothesis_contract`` before any confidence arithmetic occurs.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

import mari_enp_hypothesis_contract as contract

ENGINE_VERSION = "mari_enp_hypothesis_engine_v1"
FORMULA_ID = "mari_observed_event.competing_hypotheses.v1"
RESULT_SCHEMA = "mari_enp_hypothesis_result_v1"


def _confidence(base: float, corroboration: float, refutation: float) -> float:
    denominator = 1.0 + corroboration + refutation
    score = (base + corroboration) / denominator
    if not math.isfinite(score):
        raise ValueError("confidence: non-finite output")
    return round(score, 6)


def _lifecycle(score: float) -> str:
    if score >= 0.6:
        return "supported"
    if score <= 0.4:
        return "refuted"
    return "unresolved"


def evaluate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate evidence balance without producing a forecast or financial output."""
    violations = contract.validate_case(case)
    if violations:
        raise ValueError("; ".join(violations))
    canonical = json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    event = case["event"]
    evidence_rows = case["evidence"]
    evidence_by_hypothesis: dict[str, list[Mapping[str, Any]]] = {
        hypothesis["hypothesis_id"]: [] for hypothesis in case["hypotheses"]
    }
    for evidence in evidence_rows:
        evidence_by_hypothesis[evidence["hypothesis_id"]].append(evidence)

    hypothesis_lifecycle: list[dict[str, Any]] = []
    for hypothesis in case["hypotheses"]:
        rows = evidence_by_hypothesis[hypothesis["hypothesis_id"]]
        corroboration = sum(float(row["weight"]) for row in rows if row["relation"] == "corroborates")
        refutation = sum(float(row["weight"]) for row in rows if row["relation"] == "refutes")
        score = _confidence(float(hypothesis["base_confidence"]), corroboration, refutation)
        hypothesis_lifecycle.append({
            "hypothesis_id": hypothesis["hypothesis_id"],
            "hypothesis_type": hypothesis["hypothesis_type"],
            "label": hypothesis["label"],
            "exclusive_group": hypothesis["exclusive_group"],
            "lifecycle": _lifecycle(score),
            "confidence": score,
            "corroboration_weight": round(corroboration, 6),
            "refutation_weight": round(refutation, 6),
            "evidence_ids": [row["evidence_id"] for row in rows],
        })

    supported = [row for row in hypothesis_lifecycle if row["lifecycle"] == "supported"]
    unresolved_reasons: list[str] = []
    if len(supported) == 0:
        unresolved_reasons.append("no uniquely supported hypothesis")
    elif len(supported) > 1:
        unresolved_reasons.append("multiple hypotheses remain supported")
    unresolved_reasons.extend(
        f"hypothesis {row['hypothesis_id']} has unresolved evidence balance"
        for row in hypothesis_lifecycle if row["lifecycle"] == "unresolved"
    )
    status = "resolved" if len(supported) == 1 and not any(
        row["lifecycle"] == "unresolved" for row in hypothesis_lifecycle
    ) else "unresolved"
    overall_confidence = round(max(row["confidence"] for row in hypothesis_lifecycle), 6)
    if not math.isfinite(overall_confidence):
        raise ValueError("confidence.overall: non-finite output")

    return {
        "schema_version": RESULT_SCHEMA,
        "formula_id": FORMULA_ID,
        "engine_version": ENGINE_VERSION,
        "run_receipt": {
            "inputs_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "contract_version": contract.CONTRACT_VERSION,
        },
        "status": status,
        "scenario": {
            "symbol": case["symbol"],
            "case_id": case["case_id"],
            "as_of_date": case["as_of_date"],
            "event_id": event["event_id"],
            "event_status": event["event_status"],
        },
        "event_lifecycle": {
            "event_id": event["event_id"],
            "canonical_event_id": event["canonical_event_id"],
            "legacy_event_id": event["legacy_event_id"],
            "event_status": event["event_status"],
            "event_date": event["event_date"],
            "published_date": event["published_date"],
            "available_on": event["available_on"],
            "source": _source_projection(event["source"]),
        },
        "evidence_lifecycle": [_evidence_projection(row) for row in evidence_rows],
        "hypothesis_lifecycle": hypothesis_lifecycle,
        "unresolved_reasons": sorted(set(unresolved_reasons)),
        "confidence": {
            "overall": overall_confidence,
            "basis": "base confidence adjusted by weighted corroboration and refutation evidence",
        },
        "policy": {
            "research_only": True,
            "no_advice": True,
            "no_financial_outputs": True,
        },
    }


def _source_projection(source: Mapping[str, Any]) -> dict[str, Any]:
    projection = {
        "canonical_event_id": source["canonical_event_id"],
        "legacy_event_id": source["legacy_event_id"],
        "document_id": source["document_id"],
        "content_sha256": source["content_sha256"],
        "evidence_sha256": source["evidence_sha256"],
        "page": source["page"],
        "join_key": source["join_key"],
        "source_label": source["source_label"],
        "raw_available": source["raw_available"],
        "retained": source["retained"],
    }
    if "source_url" in source:
        projection["source_url"] = source["source_url"]
    if "source_path" in source:
        projection["source_path"] = source["source_path"]
    return projection


def _evidence_projection(evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "evidence_id": evidence["evidence_id"],
        "event_id": evidence["event_id"],
        "hypothesis_id": evidence["hypothesis_id"],
        "relation": evidence["relation"],
        "status": evidence["status"],
        "summary": evidence["summary"],
        "event_date": evidence["event_date"],
        "published_date": evidence["published_date"],
        "available_on": evidence["available_on"],
        "weight": float(evidence["weight"]),
        "source": _source_projection(evidence["source"]),
    }


def blocked_result(identity: Mapping[str, Any], reasons: list[str]) -> dict[str, Any]:
    """Return identity and lifecycle blockers without partial evidence output."""
    return {
        "schema_version": RESULT_SCHEMA,
        "formula_id": FORMULA_ID,
        "engine_version": ENGINE_VERSION,
        "run_receipt": {
            "inputs_sha256": None,
            "contract_version": contract.CONTRACT_VERSION,
        },
        "status": "blocked",
        "scenario": {
            "symbol": identity.get("symbol"),
            "case_id": identity.get("case_id"),
            "as_of_date": identity.get("as_of_date"),
            "event_id": identity.get("event_id"),
            "event_status": identity.get("event_status"),
        },
        "event_lifecycle": None,
        "evidence_lifecycle": [],
        "hypothesis_lifecycle": [],
        "unresolved_reasons": sorted(set(str(reason) for reason in reasons)),
        "confidence": None,
        "policy": {
            "research_only": True,
            "no_advice": True,
            "no_financial_outputs": True,
        },
    }
