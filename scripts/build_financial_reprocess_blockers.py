"""Build metadata-only blockers for the approved CI financial restage tranche.

This records why exact owner-reviewed official filings could not become
qualified financial facts under the current transport/parser gates. It never
downloads, parses, changes receipts, alters allowlists, or emits values.
"""
from __future__ import annotations

import hashlib
from typing import Any

from psx_data import ROOT, STATE, load_json, save_json


OUT = STATE / "company_intel" / "financial_reprocess_blockers.json"
MANIFEST_PATH = ROOT / "config" / "ci_reprocess_review_manifest.json"
ALLOWLIST_PATH = ROOT / "config" / "ci_reprocess_allowlist.json"
PARSER_VERSION = "financial_statement_v2"
PARSER_REVISION = "block_geometry_v5"

# These are the bounded exact-ID restage outcomes observed through
# reprocess_company_documents.py on the already owner-reviewed Wave 3 tranche.
# They are blockers, not receipts: no canonical state was committed for them.
APPROVED_BLOCKED_OUTCOMES: dict[str, dict[str, str]] = {
    "psx:260947": {
        "gate": "transport_network",
        "reason": "transport_error_connection",
        "next_required_evidence": "Successful exact-ID transport of the retained official DGKC FY2025 annual filing through the existing PSX path; no parser or cap change is authorized.",
    },
    "psx:264120": {
        "gate": "transport_network",
        "reason": "transport_error_connection",
        "next_required_evidence": "Successful exact-ID transport of the retained official DGKC Q1 FY2026 filing through the existing PSX path; no parser or cap change is authorized.",
    },
    "psx:275807": {
        "gate": "transport_network",
        "reason": "transport_error_connection",
        "next_required_evidence": "Successful exact-ID transport of the retained official DGKC Q3 FY2026 filing through the existing PSX path; no parser or cap change is authorized.",
    },
}


def _stable_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}_{hashlib.sha256(chr(31).join(str(part or '') for part in parts).encode('utf-8')).hexdigest()[:20]}"


def _manifest() -> dict[str, Any]:
    payload = load_json(MANIFEST_PATH, {})
    return payload if isinstance(payload, dict) else {}


def _allowlist_ids() -> list[str]:
    payload = load_json(ALLOWLIST_PATH, {})
    values = payload.get("document_ids") if isinstance(payload, dict) else []
    return [str(value) for value in values or []]


def _readiness_row(symbol: str, readiness: dict[str, Any], model_inputs: dict[str, Any]) -> dict[str, Any]:
    forecast = (readiness.get("companies") or {}).get(symbol) or {}
    model = (model_inputs.get("companies") or {}).get(symbol) or {}
    return {
        "forecast_readiness_status": forecast.get("status") or "unknown",
        "qualified_period_count": forecast.get("qualified_period_count", 0),
        "financial_model_inputs_status": model.get("status") or "unknown",
    }


def _next_status(symbol: str, readiness: dict[str, Any]) -> str:
    row = (readiness.get("companies") or {}).get(symbol) or {}
    if row.get("status") == "input_ready":
        return "not_required_for_current_input_readiness"
    return "required_for_input_readiness"


def build() -> dict[str, Any]:
    manifest = _manifest()
    manifest_ids = list(manifest.get("document_ids") or [])
    allowlist_ids = _allowlist_ids()
    if manifest_ids != allowlist_ids:
        raise ValueError("financial reprocess blockers require allowlist IDs to match the review manifest")
    missing = sorted(set(manifest_ids) - set(APPROVED_BLOCKED_OUTCOMES))
    extra = sorted(set(APPROVED_BLOCKED_OUTCOMES) - set(manifest_ids))
    if missing or extra:
        raise ValueError(f"blocked outcome map drift: missing={missing} extra={extra}")

    coverage = load_json(STATE / "company_intel" / "financial_coverage.json", {"companies": {}})
    readiness = load_json(STATE / "company_intel" / "forecast_readiness.json", {"companies": {}})
    model_inputs = load_json(STATE / "company_intel" / "financial_model_inputs.json", {"companies": {}})
    pilot = list(manifest.get("pilot_symbols") or [])
    if len(pilot) != 20 or len(set(pilot)) != 20:
        raise ValueError("financial reprocess blockers require exact 20-company pilot scope")

    docs = manifest.get("documents") or {}
    blocked = []
    companies: dict[str, dict[str, Any]] = {}
    for doc_id in manifest_ids:
        doc = docs.get(doc_id) or {}
        outcome = APPROVED_BLOCKED_OUTCOMES[doc_id]
        symbol = str(doc.get("symbol") or "")
        row = {
            "blocker_id": _stable_id("finreblock", doc_id, outcome["reason"], PARSER_REVISION),
            "document_id": doc_id,
            "symbol": symbol,
            "period": doc.get("period"),
            "classification": doc.get("classification"),
            "title": doc.get("title"),
            "source_url": doc.get("source_url"),
            "content_identity": doc.get("content_identity"),
            "safe_period": doc.get("safe_period"),
            "parser_version": PARSER_VERSION,
            "parser_revision": PARSER_REVISION,
            "status": "blocked_by_current_gate",
            "gate": outcome["gate"],
            "reason": outcome["reason"],
            "canonical_state_committed": False,
            "receipt_written": False,
            "facts_emitted": False,
            "next_status": _next_status(symbol, readiness),
            "next_required_evidence": outcome["next_required_evidence"],
        }
        blocked.append(row)
        company = companies.setdefault(symbol, {
            "symbol": symbol,
            "status": "blocked_tranche_reviewed",
            "readiness": _readiness_row(symbol, readiness, model_inputs),
            "coverage_status": ((coverage.get("companies") or {}).get(symbol) or {}).get("status") or "unknown",
            "blocked_document_count": 0,
            "required_blocked_document_count": 0,
            "blocked_documents": [],
        })
        company["blocked_document_count"] += 1
        if row["next_status"] == "required_for_input_readiness":
            company["required_blocked_document_count"] += 1
        company["blocked_documents"].append(row)

    result = {
        "schema_version": 1,
        "blocker_version": "financial_reprocess_blockers_v1",
        "source": {
            "review_manifest": "config/ci_reprocess_review_manifest.json",
            "execution_allowlist": "config/ci_reprocess_allowlist.json",
            "financial_coverage": "state/company_intel/financial_coverage.json",
            "forecast_readiness": "state/company_intel/forecast_readiness.json",
            "financial_model_inputs": "state/company_intel/financial_model_inputs.json",
        },
        "policy": {
            "metadata_only": True,
            "no_download": True,
            "no_pdf_parsing": True,
            "no_receipt_write": True,
            "no_allowlist_change": True,
            "no_numeric_facts": True,
            "no_forecast_or_valuation": True,
        },
        "limits": {
            "psx_file_bytes": 12 * 1024 * 1024,
            "psx_page_count": 120,
            "parser_requires_extractable_text_geometry": True,
        },
        "pilot_symbols": pilot,
        "summary": {
            "document_count": len(blocked),
            "company_count": len(companies),
            "required_for_input_readiness_count": sum(1 for row in blocked if row["next_status"] == "required_for_input_readiness"),
            "blocked_reasons": sorted({row["reason"] for row in blocked}),
        },
        "companies": companies,
        "blocked_documents": blocked,
    }
    save_json(OUT, result)
    print(f"financial_reprocess_blockers: {len(blocked)} blocked documents across {len(companies)} companies")
    return result


if __name__ == "__main__":
    build()
