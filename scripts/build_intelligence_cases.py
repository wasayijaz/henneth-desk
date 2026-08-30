"""Build compact observed IntelligenceCase seeds from retained official evidence.

This is intentionally not a generic case engine.  The current product need is
one cement/industrial and one E&P observed seed. Later statuses or sector
models must earn their own dedicated builders/checks.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from psx_data import STATE, load_json, save_json


OUT = STATE / "company_intel" / "intelligence_cases.json"
CASE_PRODUCT_VERSION = "observed_intelligence_case_seed_v2"
PKT = timezone(timedelta(hours=5))

MLCF_CASE_ID = "case_mlcf_pioc_control_observed_v1"
PUBLIC_OFFER_EVENT_ID = "evt_cb44dc32c91b0c5712a5"
FOLLOW_THROUGH_EVENT_ID = "evt_25bfb52e721191c7b644"
PUBLIC_OFFER_DOC_ID = "psx:267429"
FOLLOW_THROUGH_DOC_ID = "psx:275425"
MLCF_CANONICAL_CONTROL_EVENT_ID = "evt_6e9b520a122b8f2d4a59"
MLCF_LEGACY_CONTROL_EVENT_ID = PUBLIC_OFFER_EVENT_ID
MLCF_CANONICAL_FOLLOW_THROUGH_EVENT_ID = FOLLOW_THROUGH_EVENT_ID
MLCF_LEGACY_FOLLOW_THROUGH_EVENT_ID = FOLLOW_THROUGH_EVENT_ID

MARI_CASE_ID = "case_mari_offshore_exploration_blocks_observed_v1"
MARI_EVENT_ID = "evt_ddf99590afb6dacddbde"
MARI_DOC_ID = "psx:265594"


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        text = f"{text}T00:00:00"
    elif len(text) == 16 and text[10] == " ":
        text = text.replace(" ", "T") + ":00"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=PKT)
    return parsed.astimezone(PKT)


def _iso_time(value: Any) -> str | None:
    parsed = _parse_time(value)
    return parsed.isoformat() if parsed else None


def _date(value: Any) -> str | None:
    parsed = _parse_time(value)
    return parsed.date().isoformat() if parsed else None


def _event(ledger: dict[str, Any], symbol: str, event_id: str) -> dict[str, Any] | None:
    for event in (((ledger.get("companies") or {}).get(symbol) or {}).get("events") or []):
        if isinstance(event, dict) and event.get("event_id") == event_id:
            return event
    return None


def _operating_event(operating_events: dict[str, Any], symbol: str, event_id: str) -> dict[str, Any] | None:
    for event in (((operating_events.get("companies") or {}).get(symbol) or {}).get("events") or []):
        if isinstance(event, dict) and event.get("event_id") == event_id:
            return event
    return None


def _document(documents: dict[str, Any], doc_id: str) -> dict[str, Any] | None:
    doc = (documents.get("documents") or {}).get(doc_id)
    return doc if isinstance(doc, dict) else None


def _financial_truth_counters() -> dict[str, Any]:
    qualification = load_json(STATE / "company_intel" / "financial_truth_qualification.json", {})
    row = (qualification.get("companies") or {}).get("MLCF") or {}
    annual = row.get("annual_income_triplets") or {}
    quarters = row.get("qualified_reported_quarter_fact_sets") or {}
    ocf = row.get("annual_operating_cash_flow") or {}
    share_count = row.get("share_count") or {}
    return {
        "annual_income_triplets": {
            "required": annual.get("required"),
            "present": annual.get("present"),
            "qualified_periods": list(annual.get("qualified_periods") or []),
        },
        "qualified_reported_quarter_fact_sets": {
            "required": quarters.get("required"),
            "present": quarters.get("present"),
            "qualified_periods": list(quarters.get("qualified_periods") or []),
        },
        "annual_operating_cash_flow": {
            "required": ocf.get("required"),
            "present": ocf.get("present"),
            "qualified_periods": list(ocf.get("qualified_periods") or []),
        },
        "share_count": {
            "status": share_count.get("status"),
            "available_on": share_count.get("available_on"),
            "source": share_count.get("source"),
        },
    }


def _null_kernel_requirements() -> dict[str, dict[str, Any]]:
    return {
        field: {
            "value": None,
            "source_label": "retained_state_only:no_source_qualified_event_input",
            "status": "missing_source_bound_input",
        }
        for field in (
            "incremental_revenue_pkr",
            "incremental_margin_pct",
            "incremental_eps_pkr",
            "incremental_operating_cash_flow_pkr",
            "incremental_debt_pkr",
            "incremental_share_count",
            "cement_capacity_units",
            "commissioning_or_ramp_schedule",
            "capex_schedule_pkr",
            "fuel_power_freight_cost_schedule",
        )
    }


def _cement_input_readiness(refs: list[dict[str, Any]]) -> dict[str, Any]:
    primary, follow_through = refs
    if primary.get("event_id") != PUBLIC_OFFER_EVENT_ID or primary.get("document_id") != PUBLIC_OFFER_DOC_ID:
        raise ValueError("MLCF primary source join mismatch")
    if follow_through.get("event_id") != FOLLOW_THROUGH_EVENT_ID or follow_through.get("document_id") != FOLLOW_THROUGH_DOC_ID:
        raise ValueError("MLCF follow-through source join mismatch")
    return {
        "status": "observed_only",
        "kernel_activation": "blocked",
        "attribution": {
            "acquirer": "MLCF",
            "target": "PIOC",
            "follow_through": "dispatch_inclusion",
        },
        "source_join": [
            {
                "role": "primary_control",
                "canonical_event_id": MLCF_CANONICAL_CONTROL_EVENT_ID,
                "legacy_event_id": MLCF_LEGACY_CONTROL_EVENT_ID,
                "document_id": primary.get("document_id"),
                "page": primary.get("page"),
                "content_sha256": primary.get("content_sha256"),
                "evidence_sha256": "70a110272f96813a4d6693b596c99d9dbc4c4781d42a519543557a04ec4c581f",
                "published_at": "2025-12-18T12:52:00+05:00",
                "effective_date": "2025-12-18",
                "available_on": "2025-12-18",
            },
            {
                "role": "operating_follow_through",
                "canonical_event_id": MLCF_CANONICAL_FOLLOW_THROUGH_EVENT_ID,
                "legacy_event_id": MLCF_LEGACY_FOLLOW_THROUGH_EVENT_ID,
                "document_id": follow_through.get("document_id"),
                "page": follow_through.get("page"),
                "content_sha256": follow_through.get("content_sha256"),
                "evidence_sha256": "137a01f15530276a63688c01bc7eff20dd4b27154314786149fa9d8b22c21b2f",
                "published_at": "2026-04-28T10:25:00+05:00",
                "effective_date": "2026-04-28",
                "available_on": "2026-04-28",
            },
        ],
        "financial_truth_counters": _financial_truth_counters(),
        "event_specific_kernel_requirements": _null_kernel_requirements(),
        "guardrails": {
            "dispatch_inclusion_not_standalone_pioc_earnings_or_capacity_impact": True,
            "no_numeric_model_output": True,
        },
    }


def _evidence_ref(event: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    evidence = (event.get("evidence") or [{}])[0]
    return {
        "event_id": event.get("event_id"),
        "document_id": event.get("doc_id"),
        "document_title": doc.get("title"),
        "document_published_at": _iso_time(doc.get("published_at") or event.get("event_date")),
        "document_retrieved_at": _iso_time(doc.get("retrieved_at")),
        "content_sha256": doc.get("content_sha256"),
        "source": doc.get("source") or "PSX DPS",
        "source_url": evidence.get("source_url") or doc.get("source_url"),
        "page": evidence.get("page"),
        "text": evidence.get("text"),
    }


def _source_cutoff(refs: list[dict[str, Any]]) -> str:
    parsed = [
        _parse_time(ref.get("document_retrieved_at") or ref.get("document_published_at"))
        for ref in refs
    ]
    parsed = [value for value in parsed if value is not None]
    return (max(parsed) if parsed else datetime.now(PKT).replace(microsecond=0)).isoformat()


def _empty_company(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "status": "no_observed_case",
        "case_count": 0,
        "cases": [],
        "rejection_reasons": ["no_selected_observed_case_seed"],
    }


def _mlcf_case(
    ledger: dict[str, Any],
    documents: dict[str, Any],
    operating_events: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str], list[dict[str, Any]]]:
    public_offer = _event(ledger, "MLCF", PUBLIC_OFFER_EVENT_ID)
    follow_through = _event(ledger, "MLCF", FOLLOW_THROUGH_EVENT_ID)
    canonical_control = _operating_event(operating_events, "MLCF", MLCF_CANONICAL_CONTROL_EVENT_ID)
    public_offer_doc = _document(documents, PUBLIC_OFFER_DOC_ID)
    follow_through_doc = _document(documents, FOLLOW_THROUGH_DOC_ID)
    missing = []
    for label, value in (
        ("missing_public_offer_event", public_offer),
        ("missing_follow_through_event", follow_through),
        ("missing_canonical_control_event", canonical_control),
        ("missing_public_offer_document", public_offer_doc),
        ("missing_follow_through_document", follow_through_doc),
    ):
        if value is None:
            missing.append(label)
    if missing:
        return None, missing, []
    assert public_offer is not None and follow_through is not None
    assert public_offer_doc is not None and follow_through_doc is not None
    assert canonical_control is not None
    canonical_evidence = (canonical_control.get("evidence") or [{}])[0]
    if (
        canonical_evidence.get("document_id") != PUBLIC_OFFER_DOC_ID
        or canonical_evidence.get("page") != 3
        or canonical_evidence.get("content_sha256") != public_offer_doc.get("content_sha256")
        or canonical_control.get("effective_date") != "2025-12-18"
    ):
        raise ValueError("MLCF canonical control source join/hash/page/date mismatch")
    refs = [_evidence_ref(public_offer, public_offer_doc), _evidence_ref(follow_through, follow_through_doc)]
    cutoff = _source_cutoff(refs)
    case = {
        "case_id": MLCF_CASE_ID,
        "symbol": "MLCF",
        "target_symbol": "PIOC",
        "case_family": "industrial_cement",
        "case_type": "acquisition_control",
        "status": "Observed",
        "epistemic_type": "reported_fact",
        "as_of": cutoff,
        "summary": (
            "Observed official-source seed: MLCF reported a public offer/control transaction for "
            "Pioneer Cement, and a later MLCF quarterly filing reported Pioneer Cement dispatches "
            "included in local-market totals after the February 2026 acquisition."
        ),
        "observed_facts": [
            {
                "fact_id": "mlcf_pioc_public_offer_control",
                "source_event_id": PUBLIC_OFFER_EVENT_ID,
                "document_id": PUBLIC_OFFER_DOC_ID,
                "event_date": _iso_time(public_offer.get("event_date")),
                "statement": "MLCF reported a public offer to acquire PIOC shares and control of Pioneer Cement Limited.",
                "reported_values": [
                    {"label": "public_offer_shares", "value": "up to 26,623,096 PIOC shares"},
                    {"label": "public_offer_percent", "value": "11.72% shares"},
                    {"label": "spa_percent", "value": "58.03% through Share Purchase Agreement(s)"},
                    {"label": "offer_price", "value": "PKR 478.43 per share"},
                ],
                "evidence": [refs[0]],
            },
            {
                "fact_id": "mlcf_pioc_dispatch_inclusion",
                "source_event_id": FOLLOW_THROUGH_EVENT_ID,
                "document_id": FOLLOW_THROUGH_DOC_ID,
                "event_date": _iso_time(follow_through.get("event_date")),
                "statement": (
                    "MLCF reported inclusion of Pioneer Cement Limited dispatches in local-market "
                    "total due to its acquisition during February 2026."
                ),
                "reported_values": [
                    {"label": "acquisition_timing", "value": "during February 2026"},
                    {"label": "operating_follow_through", "value": "Pioneer Cement Limited dispatches included in local-market total"},
                ],
                "evidence": [refs[1]],
            },
        ],
        "alternative_readings": [
            {
                "alternative_id": "public_offer_not_full_model",
                "reading": "The December 2025 document is an official offer/control disclosure, not a quantified earnings model.",
                "status": "retained_as_observed_only",
                "rejection_condition": "Reject promotion if no later official source preserves acquisition/control or operating inclusion.",
            },
            {
                "alternative_id": "dispatch_inclusion_not_financial_impact",
                "reading": "The April 2026 filing shows operating inclusion after acquisition, but not a standalone PIOC financial impact.",
                "status": "retained_as_observed_only",
                "rejection_condition": "Reject modelling if source-qualified incremental revenue, margin, EPS, cash-flow, debt and share-count operands are absent.",
            },
        ],
        "promotion_blocks": {
            "Corroborated": "Blocked: retained evidence is an official MLCF/PSX chain, not independent-originator corroboration.",
            "Modelled": "Blocked: no source-qualified financial impact model or owner-approved assumptions are attached.",
            "Published": "Blocked: no forecast, valuation, reverse-expectations output, investor conclusion or release gate is complete.",
        },
        "cement_input_readiness": _cement_input_readiness(refs),
        "policy": {
            "observed_only": True,
            "no_forecast": True,
            "no_valuation": True,
            "no_market_expectations": True,
            "no_recommendation": True,
            "reported_values_only": True,
        },
        "source_lineage": refs,
    }
    return case, [], refs


def _mari_case(ledger: dict[str, Any], documents: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], list[dict[str, Any]]]:
    event = _event(ledger, "MARI", MARI_EVENT_ID)
    document = _document(documents, MARI_DOC_ID)
    missing = []
    if event is None:
        missing.append("missing_mari_offshore_blocks_event")
    if document is None:
        missing.append("missing_mari_offshore_blocks_document")
    if missing:
        return None, missing, []
    assert event is not None and document is not None
    refs = [_evidence_ref(event, document)]
    cutoff = _source_cutoff(refs)
    case = {
        "case_id": MARI_CASE_ID,
        "symbol": "MARI",
        "case_family": "e_and_p",
        "case_type": "offshore_exploration_block_acquisition",
        "status": "Observed",
        "epistemic_type": "reported_fact",
        "as_of": cutoff,
        "summary": (
            "Observed official-source seed: Mari Energies reported its acquisition of offshore "
            "exploration blocks as part of its long-term strategy to find new hydrocarbon resources."
        ),
        "observed_facts": [
            {
                "fact_id": "mari_offshore_exploration_blocks_acquisition",
                "source_event_id": MARI_EVENT_ID,
                "document_id": MARI_DOC_ID,
                "event_date": _iso_time(event.get("event_date")),
                "statement": "Mari Energies reported the acquisition of offshore exploration blocks.",
                "reported_values": [
                    {"label": "stated_purpose", "value": "find new hydrocarbon resources"},
                ],
                "evidence": refs,
            },
        ],
        "alternative_readings": [
            {
                "alternative_id": "blocks_not_proved_reserves",
                "reading": "The reported block acquisition does not establish reserves, a commercial discovery, or future production.",
                "status": "retained_as_observed_only",
                "rejection_condition": "Reject promotion if no official source identifies technical results, resource potential, or a development path.",
            },
            {
                "alternative_id": "strategy_not_execution_schedule",
                "reading": "The stated long-term exploration strategy does not establish working interest, operator status, cost, timing, or economic terms.",
                "status": "retained_as_observed_only",
                "rejection_condition": "Reject modelling if source-qualified project economics and a qualified company financial history remain absent.",
            },
        ],
        "promotion_blocks": {
            "Corroborated": "Blocked: retained evidence is a single official Mari/PSX source and no independent-originator corroboration is attached.",
            "Modelled": "Blocked: no source-qualified working interest, operator status, cost, timing, resource, production or financial-model inputs are attached.",
            "Published": "Blocked: no forecast, valuation, reverse-expectations output, investor conclusion or release gate is complete.",
        },
        "policy": {
            "observed_only": True,
            "no_forecast": True,
            "no_valuation": True,
            "no_market_expectations": True,
            "no_recommendation": True,
            "reported_values_only": True,
        },
        "source_lineage": refs,
    }
    return case, [], refs


def build(write: bool = True) -> dict[str, Any]:
    profiles = load_json(STATE / "company_profiles.json", {})
    ledger = load_json(STATE / "company_event_ledger.json", {"companies": {}})
    documents = load_json(STATE / "company_documents.json", {"documents": {}})
    operating_events = load_json(STATE / "company_intel" / "operating_events.json", {"companies": {}})
    pilot = sorted((profiles.get("pilot") or {}).get("symbols") or [])
    companies = {symbol: _empty_company(symbol) for symbol in pilot}
    mlcf_case, mlcf_rejections, mlcf_refs = _mlcf_case(ledger, documents, operating_events)
    mari_case, mari_rejections, mari_refs = _mari_case(ledger, documents)
    refs = [*mlcf_refs, *mari_refs]
    as_of = _source_cutoff(refs) if refs else datetime.now(PKT).replace(microsecond=0).isoformat()
    if "MLCF" not in companies:
        companies["MLCF"] = _empty_company("MLCF")
    if mlcf_case:
        companies["MLCF"] = {
            "symbol": "MLCF",
            "status": "observed_seed_available",
            "case_count": 1,
            "cases": [mlcf_case],
            "rejection_reasons": [],
        }
    else:
        companies["MLCF"]["rejection_reasons"] = mlcf_rejections
    if "MARI" not in companies:
        companies["MARI"] = _empty_company("MARI")
    if mari_case:
        companies["MARI"] = {
            "symbol": "MARI",
            "status": "observed_seed_available",
            "case_count": 1,
            "cases": [mari_case],
            "rejection_reasons": [],
        }
    else:
        companies["MARI"]["rejection_reasons"] = mari_rejections
    result = {
        "schema_version": 1,
        "case_product_version": CASE_PRODUCT_VERSION,
        "as_of": as_of,
        "pilot_symbols": pilot,
        "selected_symbols": ["MARI", "MLCF"],
        "status_lifecycle": ["Observed", "Corroborated", "Modelled", "Validated", "Published"],
        "policy": {
            "dedicated_observed_seeds_only": True,
            "no_generic_case_engine": True,
            "reported_values_only": True,
            "formal_engines_unchanged": True,
        },
        "summary": {
            "company_count": len(companies),
            "observed_case_count": sum(row.get("case_count", 0) for row in companies.values()),
            "published_case_count": 0,
        },
        "companies": companies,
    }
    if write:
        existing = load_json(OUT, {}) if OUT.exists() else {}
        if isinstance(existing.get("_meta"), dict):
            result["_meta"] = existing["_meta"]
        save_json(OUT, result)
        print(f"intelligence_cases: {result['summary']['observed_case_count']} observed seeds")
    return result


if __name__ == "__main__":
    build()
