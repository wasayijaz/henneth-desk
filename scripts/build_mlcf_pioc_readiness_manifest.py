"""Build the MLCF/PIOC acquisition-control readiness manifest.

This is a read-only checklist over existing retained CI state. It does not
parse, fetch, restage, approve inputs, or compute formal outputs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from psx_data import STATE, load_json, save_json


OUT = STATE / "company_intel" / "mlcf_pioc_readiness_manifest.json"
MANIFEST_VERSION = "mlcf_pioc_readiness_manifest_v1"
CASE_ID = "case_mlcf_pioc_control_observed_v1"
PUBLIC_OFFER_FACT_ID = "mlcf_pioc_public_offer_control"
FOLLOW_THROUGH_FACT_ID = "mlcf_pioc_dispatch_inclusion"
PUBLIC_OFFER_DOC_ID = "psx:267429"
FOLLOW_THROUGH_DOC_ID = "psx:275425"
PIOC = "PIOC"
MLCF = "MLCF"
PKT = timezone(timedelta(hours=5))


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        text = f"{text}T00:00:00"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=PKT)
    return parsed.astimezone(PKT)


def _source_cutoff(*values: Any) -> str:
    parsed = [_parse_time(value) for value in values]
    parsed = [value for value in parsed if value is not None]
    return max(parsed).isoformat() if parsed else "unknown"


def _case(intelligence_cases: dict[str, Any]) -> dict[str, Any] | None:
    row = ((intelligence_cases.get("companies") or {}).get(MLCF) or {})
    for case in row.get("cases") or []:
        if isinstance(case, dict) and case.get("case_id") == CASE_ID:
            return case
    return None


def _fact(case: dict[str, Any], fact_id: str) -> dict[str, Any] | None:
    for fact in case.get("observed_facts") or []:
        if isinstance(fact, dict) and fact.get("fact_id") == fact_id:
            return fact
    return None


def _reported_values(fact: dict[str, Any] | None) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for row in (fact or {}).get("reported_values") or []:
        if isinstance(row, dict) and row.get("label"):
            values[str(row.get("label"))] = row.get("value")
    return values


def _evidence_ref(fact: dict[str, Any] | None) -> dict[str, Any] | None:
    evidence = ((fact or {}).get("evidence") or [None])[0]
    if not isinstance(evidence, dict):
        return None
    return {
        "event_id": evidence.get("event_id"),
        "document_id": evidence.get("document_id"),
        "document_title": evidence.get("document_title"),
        "document_published_at": evidence.get("document_published_at"),
        "document_retrieved_at": evidence.get("document_retrieved_at"),
        "content_sha256": evidence.get("content_sha256"),
        "source": evidence.get("source"),
        "source_url": evidence.get("source_url"),
        "page": evidence.get("page"),
    }


def _empty_company(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "status": "not_selected",
        "manifest": None,
        "blockers": ["not_selected_for_mlcf_pioc_manifest"],
    }


def _with_existing_root_meta(path: Path, result: dict[str, Any]) -> dict[str, Any]:
    existing = load_json(path, {})
    meta = existing.get("_meta") if isinstance(existing, dict) else None
    if not isinstance(meta, dict):
        return result
    return {**result, "_meta": meta}


def _missing_inputs(
    financial_truth: dict[str, Any],
    model_inputs: dict[str, Any],
    pilot_symbols: list[str],
) -> list[dict[str, Any]]:
    truth = ((financial_truth.get("companies") or {}).get(MLCF) or {})
    model = ((model_inputs.get("companies") or {}).get(MLCF) or {})
    return [
        {
            "input_id": "pioc_ci_pilot_membership",
            "status": "missing",
            "required": "target company inside current CI pilot",
            "present": PIOC in pilot_symbols,
            "source_path": "state/company_profiles.json",
        },
        {
            "input_id": "pioc_retained_official_financial_documents",
            "status": "missing",
            "required": "retained official target-company financial documents under the CI document source",
            "present": 0,
            "source_path": "state/company_documents.json",
        },
        {
            "input_id": "pioc_financial_truth_row",
            "status": "missing",
            "required": "target-company financial truth row under the CI pilot boundary",
            "present": 0,
            "source_path": "state/company_intel/financial_truth_qualification.json",
        },
        {
            "input_id": "pioc_model_input_row",
            "status": "missing",
            "required": "target-company model-input row under the CI pilot boundary",
            "present": 0,
            "source_path": "state/company_intel/financial_model_inputs.json",
        },
        {
            "input_id": "mlcf_full_financial_truth_gate",
            "status": "missing",
            "required": {
                "annual_income_triplets": (truth.get("annual_income_triplets") or {}).get("required"),
                "reported_quarter_fact_sets": (truth.get("qualified_reported_quarter_fact_sets") or {}).get("required"),
                "annual_operating_cash_flow": (truth.get("annual_operating_cash_flow") or {}).get("required"),
                "official_share_count_capital_note_tie_out": 1,
            },
            "present": {
                "annual_income_triplets": (truth.get("annual_income_triplets") or {}).get("present"),
                "reported_quarter_fact_sets": (truth.get("qualified_reported_quarter_fact_sets") or {}).get("present"),
                "annual_operating_cash_flow": (truth.get("annual_operating_cash_flow") or {}).get("present"),
                "official_share_count_capital_note_tie_out": int(
                    (truth.get("share_count") or {}).get("status") == "official_share_count_capital_note_tied_out"
                ),
            },
            "source_path": "state/company_intel/financial_truth_qualification.json",
        },
        {
            "input_id": "event_specific_incremental_financial_bridge",
            "status": "missing",
            "required": [
                "source-qualified target-company contribution by retained period",
                "source-qualified acquirer consolidation bridge by retained period",
                "source-qualified debt and cash position tied to the transaction chain",
                "official share-capital tie-out after the transaction chain",
            ],
            "present": [],
            "source_paths": [
                "state/company_intel/intelligence_cases.json",
                "state/company_intel/financial_evidence_reconciliation.json",
                "state/company_intel/financial_model_inputs.json",
            ],
        },
        {
            "input_id": "mlcf_historical_adapter_scope",
            "status": "insufficient_for_event_model",
            "required": "event-specific MLCF/PIOC acquisition-control model inputs",
            "present": {
                "mlcf_company_model_input_status": model.get("status"),
                "adapter_version": model.get("adapter_version"),
                "scope_limitation": "MLCF historical actuals only; not a target-company or transaction-chain model",
            },
            "source_path": "state/company_intel/financial_model_inputs.json",
        },
    ]


def _mlcf_manifest(
    intelligence_cases: dict[str, Any],
    financial_truth: dict[str, Any],
    model_inputs: dict[str, Any],
    pilot_symbols: list[str],
) -> tuple[dict[str, Any] | None, list[str], list[dict[str, Any]]]:
    case = _case(intelligence_cases)
    if case is None:
        return None, ["missing_mlcf_pioc_observed_case"], []
    public_offer = _fact(case, PUBLIC_OFFER_FACT_ID)
    follow_through = _fact(case, FOLLOW_THROUGH_FACT_ID)
    missing = []
    for label, value in (
        ("missing_public_offer_fact", public_offer),
        ("missing_follow_through_fact", follow_through),
    ):
        if value is None:
            missing.append(label)
    refs = [ref for ref in (_evidence_ref(public_offer), _evidence_ref(follow_through)) if ref]
    if missing:
        return None, missing, refs
    values = _reported_values(public_offer)
    follow_values = _reported_values(follow_through)
    as_of = _source_cutoff(*(ref.get("document_retrieved_at") or ref.get("document_published_at") for ref in refs))
    return {
        "manifest_id": "mlcf_pioc_event_model_readiness_v1",
        "case_id": case.get("case_id"),
        "case_status": case.get("status"),
        "acquirer_symbol": MLCF,
        "target_symbol": PIOC,
        "status": "blocked_missing_inputs",
        "as_of": as_of,
        "known_fields": {
            "target": "Pioneer Cement Limited",
            "control": "reported control of Pioneer Cement Limited",
            "offer_shares": values.get("public_offer_shares"),
            "offer_percent": values.get("public_offer_percent"),
            "spa_percent": values.get("spa_percent"),
            "offer_price": values.get("offer_price"),
            "timing": follow_values.get("acquisition_timing"),
            "follow_through": follow_values.get("operating_follow_through"),
        },
        "pilot_status": {
            "target_symbol": PIOC,
            "in_current_ci_pilot": PIOC in pilot_symbols,
            "pilot_symbols_source": "state/company_profiles.json",
            "status": "target_not_in_ci_pilot",
        },
        "evidence_refs": refs,
        "missing_inputs": _missing_inputs(financial_truth, model_inputs, pilot_symbols),
        "formal_output_policy": {
            "status": "blocked",
            "hard_block": True,
            "accepted_outputs": [],
            "block_reason": "formal output remains blocked until every missing input is source-qualified and owner-reviewed through existing gates",
            "no_generic_economic_engine": True,
            "reported_fields_only": True,
        },
    }, [], refs


def build(
    write: bool = True,
    *,
    intelligence_cases: dict[str, Any] | None = None,
    financial_truth: dict[str, Any] | None = None,
    model_inputs: dict[str, Any] | None = None,
    pilot_symbols: list[str] | None = None,
) -> dict[str, Any]:
    """Build the manifest from current producer authorities.

    Callers that already rebuilt the IntelligenceCase can pass that object so
    readiness is derived from the same in-memory producer result.  Omitted
    inputs retain the standalone script behaviour for the scheduled builder.
    """
    if pilot_symbols is None:
        profiles = load_json(STATE / "company_profiles.json", {})
        pilot_symbols = list((profiles.get("pilot") or {}).get("symbols") or [])
    if intelligence_cases is None:
        intelligence_cases = load_json(STATE / "company_intel" / "intelligence_cases.json", {"companies": {}})
    if financial_truth is None:
        financial_truth = load_json(STATE / "company_intel" / "financial_truth_qualification.json", {"companies": {}})
    if model_inputs is None:
        model_inputs = load_json(STATE / "company_intel" / "financial_model_inputs.json", {"companies": {}})
    companies = {symbol: _empty_company(symbol) for symbol in pilot_symbols}
    manifest, blockers, refs = _mlcf_manifest(intelligence_cases, financial_truth, model_inputs, pilot_symbols)
    if MLCF not in companies:
        companies[MLCF] = _empty_company(MLCF)
    companies[MLCF] = {
        "symbol": MLCF,
        "status": "blocked_missing_inputs" if manifest else "blocked_missing_case",
        "manifest": manifest,
        "blockers": blockers,
    }
    result = {
        "schema_version": 1,
        "manifest_version": MANIFEST_VERSION,
        "as_of": _source_cutoff(*(ref.get("document_retrieved_at") or ref.get("document_published_at") for ref in refs)),
        "pilot_symbols": pilot_symbols,
        "selected_symbols": [MLCF],
        "source_policy": "retained CI state only; no fetching, parsing, restaging, approvals, or source mutation",
        "policy": {
            "read_only_checklist": True,
            "explicit_blockers_only": True,
            "formal_outputs_blocked": True,
            "no_generic_economic_engine": True,
            "reported_fields_only": True,
        },
        "summary": {
            "company_count": len(companies),
            "manifest_count": 1 if manifest else 0,
            "blocked_manifest_count": 1,
            "target_in_ci_pilot": PIOC in pilot_symbols,
        },
        "companies": companies,
    }
    if write:
        save_json(OUT, _with_existing_root_meta(OUT, result))
        print(f"mlcf_pioc_readiness_manifest: {result['summary']['manifest_count']} manifest, formal outputs blocked")
    return result


if __name__ == "__main__":
    build()
