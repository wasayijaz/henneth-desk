"""Build the compact, reference-only Company Brain index for the CI pilot."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from intelligence_types import BRAIN_DOMAINS, INTELLIGENCE_TYPES, SOURCE_INDEX_PRODUCTS, SOURCE_PRODUCTS
from psx_data import STATE, load_json, save_json
from ci_checker_helpers import without_root_meta

OUT = STATE / "company_intel" / "company_brains.json"
SOURCE_INDEX_PRODUCT_META = {
    "operating_events": {
        "path": STATE / "company_intel" / "operating_events.json",
        "state_path": "state/company_intel/operating_events.json",
    },
    "financial_model_inputs": {
        "path": STATE / "company_intel" / "financial_model_inputs.json",
        "state_path": "state/company_intel/financial_model_inputs.json",
    },
    "financial_evidence_reconciliation": {
        "path": STATE / "company_intel" / "financial_evidence_reconciliation.json",
        "state_path": "state/company_intel/financial_evidence_reconciliation.json",
    },
    "financial_coverage": {
        "path": STATE / "company_intel" / "financial_coverage.json",
        "state_path": "state/company_intel/financial_coverage.json",
    },
    "forecast_readiness": {
        "path": STATE / "company_intel" / "forecast_readiness.json",
        "state_path": "state/company_intel/forecast_readiness.json",
    },
    "financial_forecasts": {
        "path": STATE / "company_intel" / "financial_forecasts.json",
        "state_path": "state/company_intel/financial_forecasts.json",
    },
    "formal_valuations": {
        "path": STATE / "company_intel" / "formal_valuations.json",
        "state_path": "state/company_intel/formal_valuations.json",
    },
    "market_expectations": {
        "path": STATE / "company_intel" / "market_expectations.json",
        "state_path": "state/company_intel/market_expectations.json",
    },
    "signal_clusters": {
        "path": STATE / "company_intel" / "signal_clusters.json",
        "state_path": "state/company_intel/signal_clusters.json",
    },
    "thesis_monitoring": {
        "path": STATE / "company_intel" / "thesis_monitoring.json",
        "state_path": "state/company_intel/thesis_monitoring.json",
    },
    "guidance_contradictions": {
        "path": STATE / "company_intel" / "guidance_contradictions.json",
        "state_path": "state/company_intel/guidance_contradictions.json",
    },
    "management_delivery": {
        "path": STATE / "company_intel" / "management_delivery.json",
        "state_path": "state/company_intel/management_delivery.json",
    },
    "intelligence_confidence": {
        "path": STATE / "company_intel" / "intelligence_confidence.json",
        "state_path": "state/company_intel/intelligence_confidence.json",
    },
    "scenario_lab": {
        "path": STATE / "company_intel" / "scenario_lab.json",
        "state_path": "state/company_intel/scenario_lab.json",
    },
    "impact_scenarios": {
        "path": STATE / "company_intel" / "impact_scenarios.json",
        "state_path": "state/company_intel/impact_scenarios.json",
    },
    "driver_graphs": {
        "path": STATE / "company_intel" / "driver_graphs.json",
        "state_path": "state/company_intel/driver_graphs.json",
    },
}
ROW_METADATA_KEYS = (
    "symbol",
    "status",
    "activation_status",
    "coverage_status",
    "freshness",
    "guidance_status",
    "reason",
    "missing_requirements",
    "result",
    "provenance",
    "policy",
    "formula_id",
    "model_version",
    "contract_version",
    "classification",
    "downstream_status",
    "quality_flags",
    "limitations",
    "candidate_count",
    "eligible_count",
    "clusterable_count",
    "source_cluster_count",
    "active_thesis_count",
    "assessment_count",
    "aggregate_score",
    "aggregate_band",
    "guidance_count",
    "risk_count",
    "object_count",
    "contradiction_count",
    "delivery_record_count",
    "guidance_object_count",
    "guidance_record_count",
)
STATE_METADATA_KEYS = (
    "schema_version",
    "as_of",
    "source",
    "policy",
    "kind",
    "engine_version",
    "formula_id",
    "contract_version",
    "coverage_version",
    "reconciliation_version",
    "guidance_version",
    "delivery_version",
    "confidence_version",
    "registry_version",
)
FORMAL_ENGINE_PRODUCTS = {
    "financial_forecasts": {
        "path": STATE / "company_intel" / "financial_forecasts.json",
        "state_path": "state/company_intel/financial_forecasts.json",
        "brain_path": "forecasts",
    },
    "formal_valuations": {
        "path": STATE / "company_intel" / "formal_valuations.json",
        "state_path": "state/company_intel/formal_valuations.json",
        "brain_path": "valuation",
    },
    "market_expectations": {
        "path": STATE / "company_intel" / "market_expectations.json",
        "state_path": "state/company_intel/market_expectations.json",
        "brain_path": "forecasts",
    },
}

BRIEF_DOMAIN_MAP = {
    "what_changed": ("projects", "catalysts", "historical_events"),
    "financial_read": ("financial_statements", "operating_kpis"),
    "management_and_capital": ("management", "capital_allocation"),
}
EVENT_DOMAIN_MAP = {
    "hiring_expansion": ("employees", "capacity"),
    "capacity_plant_expansion": ("capacity", "facilities", "projects"),
    "exploration_well_discovery": ("capacity", "projects", "catalysts"),
    "contract_tender": ("customers", "projects", "catalysts"),
    "management_change": ("management",),
    "debt_refinancing": ("capital_allocation", "risks"),
    "product_launch": ("products", "catalysts"),
    "supplier_change": ("suppliers", "risks"),
    "maintenance_shutdown": ("facilities", "capacity", "risks"),
    "regulatory_change": ("risks", "catalysts"),
    "acquisition_divestment": ("subsidiaries", "capital_allocation", "catalysts"),
}


def _stable_id(symbol: str, product: str, source_id: str) -> str:
    raw = f"{symbol}|{product}|{source_id}".encode("utf-8")
    return "bio_" + hashlib.sha256(raw).hexdigest()[:20]


def _date(value: object) -> str | None:
    return value[:10] if isinstance(value, str) and len(value) >= 10 else None


def _metadata_dates(value: object) -> list[str]:
    if isinstance(value, str):
        day = _date(value)
        return [day] if day else []
    if isinstance(value, dict):
        dates: list[str] = []
        for item in value.values():
            dates.extend(_metadata_dates(item))
        return dates
    if isinstance(value, list):
        dates: list[str] = []
        for item in value:
            dates.extend(_metadata_dates(item))
        return dates
    return []


def _input_as_of(states: list[dict], companies: dict) -> str:
    dates: list[str] = []
    for state in states:
        if not isinstance(state, dict):
            continue
        for key in ("as_of", "updated"):
            dates.extend(_metadata_dates(state.get(key)))
        if isinstance(state.get("_meta"), dict):
            for key in ("as_of", "updated", "built"):
                dates.extend(_metadata_dates(state["_meta"].get(key)))
    for company in companies.values():
        for obj in company.get("intelligence_objects") or []:
            day = _date(obj.get("available_on"))
            if day:
                dates.append(day)
    return max(dates) if dates else "unknown"


def _evidence_refs(evidence: object) -> list[dict]:
    rows = evidence if isinstance(evidence, list) else [evidence] if isinstance(evidence, dict) else []
    refs = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ref = {key: row[key] for key in (
            "document_id", "doc_id", "page", "content_sha256", "evidence_sha256", "source_url"
        ) if row.get(key) is not None}
        if ref:
            refs.append(ref)
    return refs[:3]


def _domains() -> dict:
    rows = {domain: {"status": "unknown", "object_refs": []} for domain in BRAIN_DOMAINS}
    rows["forecasts"] = {"status": "blocked", "object_refs": [], "reason": "forecast_objects_not_permitted"}
    rows["valuation"] = {"status": "blocked", "object_refs": [], "reason": "valuation_objects_not_permitted"}
    return rows


def _add_object(objects: list[dict], domains: dict, symbol: str, product: str, source_id: str,
                typ: str, domain_names: tuple[str, ...], available_on: str,
                evidence_refs: list[dict], confidence: int | None,
                input_refs: list[str] | None = None) -> None:
    obj = {
        "id": _stable_id(symbol, product, source_id),
        "type": typ,
        "source_product": product,
        "source_id": source_id,
        "available_on": available_on,
        "evidence_refs": evidence_refs,
        "confidence": confidence,
        "brain_paths": [f"companies/{symbol}/domains/{name}" for name in domain_names],
    }
    if input_refs:
        obj["input_refs"] = input_refs
    objects.append(obj)
    for name in domain_names:
        domains[name]["object_refs"].append(obj["id"])


def _brief_objects(symbol: str, briefs: dict, domains: dict, objects: list[dict]) -> None:
    history = (((briefs.get("companies") or {}).get(symbol) or {}).get("history") or [])
    for brief in history:
        approved_on = _date(brief.get("approved_at"))
        brief_id = brief.get("brief_id")
        if brief.get("status") != "owner_approved" or not approved_on or not brief_id:
            continue
        for section, domain_names in BRIEF_DOMAIN_MAP.items():
            for index, row in enumerate(((brief.get("sections") or {}).get(section) or [])):
                if not isinstance(row, dict):
                    continue
                evidence = _evidence_refs(row.get("evidence"))
                if evidence:
                    _add_object(objects, domains, symbol, "company_briefs", f"{brief_id}:{section}:{index}",
                                "reported_fact", domain_names, approved_on, evidence, 90)


def _event_objects(symbol: str, operating: dict, domains: dict, objects: list[dict]) -> None:
    events = (((operating.get("companies") or {}).get(symbol) or {}).get("events") or [])
    for event in events:
        event_id = event.get("event_id")
        available_on = _date(event.get("detected_at") or event.get("effective_date"))
        evidence = _evidence_refs(event.get("evidence"))
        if not event_id or not available_on or not evidence:
            continue
        domain_names = tuple(dict.fromkeys(EVENT_DOMAIN_MAP.get(event.get("event_type"), ()) + ("historical_events",)))
        typ = event.get("intelligence_type") or "reported_fact"
        if typ not in {"reported_fact", "derived_fact", "inference"}:
            typ = "reported_fact"
        _add_object(objects, domains, symbol, "operating_events", event_id, typ, domain_names,
                    available_on, evidence, event.get("confidence"))


def _study_objects(symbol: str, studies: dict, domains: dict, objects: list[dict]) -> None:
    for study_id, study in sorted((studies.get("studies") or {}).items()):
        available_on = _date(study.get("data_cutoff") or study.get("effective_date"))
        if study.get("symbol") != symbol or not available_on:
            continue
        _add_object(objects, domains, symbol, "event_studies", study_id, "derived_fact",
                    ("historical_events",), available_on,
                    [{"source_path": f"state/company_intel/event_studies.json#/studies/{study_id}"}],
                    None, [study["event_id"]] if study.get("event_id") else None)


def _load_formal_engines() -> dict:
    return {
        product: load_json(meta["path"], {"companies": {}})
        for product, meta in FORMAL_ENGINE_PRODUCTS.items()
    }


def _load_source_index_products() -> dict:
    return {
        product: load_json(SOURCE_INDEX_PRODUCT_META[product]["path"], {"companies": {}})
        for product in SOURCE_INDEX_PRODUCTS
    }


def _picked(mapping: dict, keys: tuple[str, ...]) -> dict:
    return {key: mapping[key] for key in keys if key in mapping}


def _state_metadata(state: dict) -> dict:
    """Return source product metadata, excluding the generated integrity envelope."""
    logical = without_root_meta(state)
    return _picked(logical, STATE_METADATA_KEYS) if isinstance(logical, dict) else {}


def _source_index(symbol: str, source_products: dict) -> dict:
    refs = {}
    for product in SOURCE_INDEX_PRODUCTS:
        state = source_products[product]
        row = ((state.get("companies") or {}).get(symbol) or {})
        meta = SOURCE_INDEX_PRODUCT_META[product]
        refs[product] = {
            "source_product": product,
            "state_path": meta["state_path"],
            "source_path": f"{meta['state_path']}#/companies/{symbol}",
            "pointer": f"/companies/{symbol}",
            "symbol": row.get("symbol") or symbol,
            "state_metadata": _state_metadata(state),
            "row_metadata": _picked(row, ROW_METADATA_KEYS),
        }
    return refs


def _formal_engine_refs(symbol: str, formal_engines: dict) -> dict:
    refs = {}
    for product, state in formal_engines.items():
        meta = FORMAL_ENGINE_PRODUCTS[product]
        row = ((state.get("companies") or {}).get(symbol) or {})
        ref = {
            "type": "formal_engine_product",
            "source_product": product,
            "source_path": f"{meta['state_path']}#/companies/{symbol}",
            "symbol": row.get("symbol") or symbol,
            "kind": state.get("kind") or product,
            "engine_version": state.get("engine_version"),
            "formula_id": row.get("formula_id") or state.get("formula_id"),
            "status": row.get("status") or "blocked",
            "reason": row.get("reason"),
            "result": row.get("result"),
            "provenance": row.get("provenance") or [],
            "policy": row.get("policy") or {},
            "as_of": _date(state.get("as_of")),
            "brain_path": f"companies/{symbol}/domains/{meta['brain_path']}",
        }
        if row.get("missing_requirements") is not None:
            ref["missing_requirements"] = row["missing_requirements"]
        refs[product] = ref
    return refs


def _with_existing_root_meta(path: Path, result: dict) -> dict:
    existing = load_json(path, {})
    meta = existing.get("_meta") if isinstance(existing, dict) else None
    if not isinstance(meta, dict):
        return result
    return {**result, "_meta": meta}


def _finalize(domains: dict) -> None:
    for row in domains.values():
        row["object_refs"] = sorted(set(row["object_refs"]))
        if row["object_refs"]:
            row["status"] = "available"


def build(write: bool = True) -> dict:
    profiles = load_json(STATE / "company_profiles.json", {})
    briefs = load_json(STATE / "company_briefs.json", {})
    operating = load_json(STATE / "company_intel" / "operating_events.json", {})
    studies = load_json(STATE / "company_intel" / "event_studies.json", {})
    formal_engines = _load_formal_engines()
    source_index_products = _load_source_index_products()
    pilot = sorted((profiles.get("pilot") or {}).get("symbols") or [])
    companies = {}
    for symbol in pilot:
        domains = _domains()
        objects: list[dict] = []
        profile = (profiles.get("tickers") or {}).get(symbol) or {}
        identity = {"symbol": symbol, "label": symbol, "source_product": "company_profiles", "source_id": symbol}
        if profile.get("source_url"):
            identity["source_url"] = profile["source_url"]
        _brief_objects(symbol, briefs, domains, objects)
        _event_objects(symbol, operating, domains, objects)
        _study_objects(symbol, studies, domains, objects)
        objects.sort(key=lambda obj: (obj["available_on"], obj["id"]))
        _finalize(domains)
        timeline = [{"date": obj["available_on"], "object_ref": obj["id"], "type": obj["type"],
                     "source_product": obj["source_product"]} for obj in objects]
        companies[symbol] = {
            "identity": identity,
            "domains": domains,
            "intelligence_objects": objects,
            "source_index": _source_index(symbol, source_index_products),
            "formal_engine_refs": _formal_engine_refs(symbol, formal_engines),
            "timeline": timeline,
            "coverage": {
                "available_domains": sum(row["status"] == "available" for row in domains.values()),
                "partial_domains": sum(row["status"] == "partial" for row in domains.values()),
                "unknown_domains": sum(row["status"] == "unknown" for row in domains.values()),
                "blocked_domains": sum(row["status"] == "blocked" for row in domains.values()),
                "object_count": len(objects),
            },
        }
    as_of = _input_as_of([profiles, briefs, operating, studies, *formal_engines.values(), *source_index_products.values()], companies)
    result = {
        "schema_version": 1,
        "as_of": as_of,
        "pilot_symbols": pilot,
        "intelligence_types": list(INTELLIGENCE_TYPES),
        "domains": list(BRAIN_DOMAINS),
        "source_products": list(SOURCE_PRODUCTS),
        "source_index_products": list(SOURCE_INDEX_PRODUCTS),
        "companies": companies,
    }
    if write:
        save_json(OUT, _with_existing_root_meta(OUT, result))
        total = sum(company["coverage"]["object_count"] for company in companies.values())
        print(f"company_brains: wrote {len(companies)} companies, {total} reference objects")
    return result


if __name__ == "__main__":
    build()
