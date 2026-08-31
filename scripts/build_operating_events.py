"""Build evidence-backed operating events for the declared CI pilot."""
from __future__ import annotations
from datetime import date
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from psx_data import STATE, load_json, save_json
from operating_events import (
    TYPE_MAP, bounded_text, evidence_hash, stable_id, source_quality,
    confidence, quality_flags, iso_date, strict_event_is_supported,
)
from document_events import event_is_supported

OUT = STATE / "company_intel" / "operating_events.json"
SOURCE_PATHS = (
    "state/company_documents.json",
    "state/company_event_ledger.json",
)
SOURCE_SYSTEMS = {
    "psx": {
        "source": "PSX DPS",
        "document_id_prefix": "psx:",
        "quality_level": 1,
        "required_fields": ["document_id", "source_url", "page", "text", "content_sha256"],
    },
    "issuer": {
        "source": "Issuer website",
        "document_id_prefix": "issuer:",
        "quality_level": 6,
        "required_fields": ["document_id", "source_url", "page", "text", "content_sha256"],
    },
}
OPERATING_EVENT_REGISTRY = {
    "registry_version": "operating_event_registry_v1",
    "status": "closed",
    "intelligence_type": "reported_fact",
    "source_paths": list(SOURCE_PATHS),
    "source_systems": SOURCE_SYSTEMS,
    "eligibility_rules": [
        "company must be in state/company_profiles.json pilot.symbols",
        "raw event must come from state/company_event_ledger.json",
        "raw doc_id must resolve in state/company_documents.json",
        "raw event_type must map to a supported canonical event type",
        "document_events.event_is_supported(raw) must pass",
        "operating_events.strict_event_is_supported(canonical_type, evidence) must pass",
        "evidence rows must include text, source_url, one-based page, source, content_sha256, and evidence_sha256",
        "detected_at is raw event_date when available, otherwise document retrieved_at",
        "effective_date is the ISO date prefix of raw event_date only",
        "effective_date must not be later than detected_at or the retained source cutoff",
    ],
    "event_types": [
        {
            "event_type": "acquisition_divestment",
            "raw_event_types": ["acquisition"],
            "allowed_priority_weights": [4],
            "strict_pattern_key": "acquisition_divestment",
        },
        {
            "event_type": "contract_tender",
            "raw_event_types": ["contract"],
            "allowed_priority_weights": [3],
            "strict_pattern_key": "contract_tender",
        },
        {
            "event_type": "debt_refinancing",
            "raw_event_types": ["credit_event"],
            "allowed_priority_weights": [5],
            "strict_pattern_key": "debt_refinancing",
        },
        {
            "event_type": "management_change",
            "raw_event_types": ["management_change"],
            "allowed_priority_weights": [3],
            "strict_pattern_key": "management_change",
        },
        {
            "event_type": "regulatory_change",
            "raw_event_types": ["regulatory_action"],
            "allowed_priority_weights": [4],
            "strict_pattern_key": "regulatory_change",
        },
        {
            "event_type": "product_launch",
            "raw_event_types": ["product_launch"],
            "allowed_priority_weights": [3],
            "strict_pattern_key": "product_launch",
        },
    ],
}


def _date_prefix(value: object) -> str | None:
    return iso_date(value)


def _parse_date(value: object) -> date | None:
    prefix = _date_prefix(value)
    if not prefix:
        return None
    try:
        return date.fromisoformat(prefix)
    except ValueError:
        return None


def _source_cutoff(pilot: list[str], ledger: dict, docs: dict) -> date | None:
    dates: list[date] = []
    for sym in pilot:
        for raw in (ledger.get(sym, {}).get("events") or []):
            for value in (raw.get("event_date"), docs.get(raw.get("doc_id"), {}).get("retrieved_at")):
                parsed = _parse_date(value)
                if parsed:
                    dates.append(parsed)
    return max(dates) if dates else None


def _json_date(value: date | None) -> str | None:
    return value.isoformat() if value else None

def build() -> dict:
    profiles = load_json(STATE / "company_profiles.json", {})
    pilot = (profiles.get("pilot") or {}).get("symbols") or []
    docs = (load_json(STATE / "company_documents.json", {}).get("documents") or {})
    ledger = load_json(STATE / "company_event_ledger.json", {}).get("companies") or {}
    source_cutoff = _source_cutoff(sorted(pilot), ledger, docs)
    companies = {}
    for sym in sorted(pilot):
        out = []
        for raw in (ledger.get(sym, {}).get("events") or []):
            event_type = TYPE_MAP.get(raw.get("event_type"))
            evidence = [e for e in (raw.get("evidence") or []) if isinstance(e, dict) and e.get("text") and e.get("source_url")]
            doc = docs.get(raw.get("doc_id"), {})
            if not event_type or not evidence or not event_is_supported(raw) or not strict_event_is_supported(event_type, evidence):
                continue
            url = evidence[0].get("source_url") or doc.get("source_url")
            excerpt = bounded_text(evidence[0].get("text"))
            event = {
                "event_id": stable_id(sym, raw.get("event_id") or raw.get("doc_id"), event_type),
                "company_id": sym, "symbol": sym, "event_type": event_type,
                "event_subtype": raw.get("event_type"), "intelligence_type": "reported_fact",
                "priority_weight": raw.get("priority_weight"),
                "detected_at": raw.get("event_date") or doc.get("retrieved_at"),
                "effective_date": iso_date(raw.get("event_date")), "expected_completion": None,
                "business_segment": None, "location": None,
                "description": excerpt, "source_url": url,
                "source_quality_level": source_quality(url, doc.get("source")),
                "confidence": 0, "estimated_scale": None, "expected_cost": None,
                "affected_drivers": [], "expected_lag": None, "historical_analogues": [],
                "peer_analogues": [], "scenario_ids": [], "financial_model_version": None,
                "evidence": [
                    {
                        "document_id": raw.get("doc_id"),
                        "source": doc.get("source"),
                        "source_url": e.get("source_url"),
                        "page": e.get("page"),
                        "text": bounded_text(e.get("text")),
                        "content_sha256": doc.get("content_sha256"),
                        "evidence_sha256": evidence_hash(raw.get("doc_id"), e.get("source_url"), e.get("page"), e.get("text")),
                    }
                    for e in evidence[:3]
                ],
                "quality_flags": [],
            }
            recency_days = None
            effective = iso_date(raw.get("event_date"))
            effective_date = _parse_date(effective)
            if effective_date and source_cutoff:
                recency_days = max(0, (source_cutoff - effective_date).days)
            event["confidence"] = confidence(event["source_quality_level"], len(event["evidence"]), recency_days=recency_days)
            event["quality_flags"] = quality_flags(event)
            out.append(event)
        out.sort(key=lambda e: (e.get("effective_date") or "", e["event_id"]), reverse=True)
        companies[sym] = {"events": out}
    result = {
        "schema_version": 2,
        "registry_version": OPERATING_EVENT_REGISTRY["registry_version"],
        "as_of": _json_date(source_cutoff),
        "pilot_symbols": sorted(pilot),
        "companies": companies,
        "event_types": sorted(TYPE_MAP.values()),
        "event_registry": OPERATING_EVENT_REGISTRY,
        "source": " + ".join(SOURCE_PATHS),
    }
    save_json(OUT, result)
    print(f"operating_events: {sum(len(v['events']) for v in companies.values())} events across {len(companies)} pilot companies")
    return result

if __name__ == "__main__": build()
