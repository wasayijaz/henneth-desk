"""Fail-closed, read-only DGKC PP-bag commissioning evidence seed.

The seed is intentionally an evidence object only.  It never writes state and
does not estimate capex, margins, utilization, earnings or valuation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVENT_LEDGER = ROOT / "state" / "company_event_ledger.json"
DOCUMENTS = ROOT / "state" / "company_documents.json"

CONTRACT_VERSION = "dgkc_commissioning_seed_contract_v1"
SEED_SCHEMA = "dgkc_commissioning_observed_seed_v1"

EXPECTED_CHAIN = [
    {
        "event_id": "evt_202508376c5508482555",
        "doc_id": "issuer:bdd12208b3af905c0658a716",
        "url": "https://www.dgcement.com/Briefing/CBS.pdf",
        "page": 8,
        "hash": "c09850be37901082eded263ce8f4963ca293a38e15b74d80c7bb9732aab6f242",
        "text": ", NPPCL produced 50.7 million paper bags. • DGKC holds 55% shares in NPPCL. • Revenue and Loss for the FY:2023 are Rs 3,091 Million and Rs 177 Million respectively. • L/C opened for new PP bag plant with capacity of 90 million bags per ann…",
        "transition": "lc_opened",
    },
    {
        "event_id": "evt_30b3d5aa155b5dffe676",
        "doc_id": "issuer:643aacd8ed6bc0d18deef78f",
        "url": "https://www.dgcement.com/Briefing/CBS Presentation 12112024.pdf",
        "page": 8,
        "hash": "2921f0b399ec6b4d41e678cf5de8f5914d45c3b29eb81b98dee796f73cbbe592",
        "text": ", NPPCL produced 43.3 million paper bags. • DGKC holds 55% shares in NPPCL. • Revenue and Loss for the FY 2024 are PKR 2,497 Million and PKR 285 Million respectively. • The PP Bag Plant, currently being installed at Quaid-e-Azam Business P…",
        "transition": "installation",
    },
    {
        "event_id": "evt_c66c444c35780cf5951e",
        "doc_id": "issuer:c7230a44854c74a77777465a",
        "url": "https://www.dgcement.com/Briefing/DGKC CBS Presentation 21112025.pdf",
        "page": 9,
        "hash": "df7976aec9b21f8316bfa8e4c0c436d6e359c6bd1f2a8e21d598ee28f664685c",
        "text": "e (90 million bags) at Quaid-e-Azam Business Park, Sheikhupura, commissioned in the third quarter of FY25. • In FY 2025, NPL produced 43.2 million (FY24: 43.3 million) paper bags and 29.7 million PP bags. • Profitability improved mainly du…",
        "transition": "commissioned_q3_fy25",
    },
]

BLOCKERS = [
    "event/effective date is not normalized; source publication and availability dates are absent",
    "plant capex, ramp/utilization, dispatch/cost and consolidated earnings attribution are absent",
    "qualified quarterly history and event-to-financial bridge are absent (0/8 quarters in the retained selection audit)",
    "load-bearing share-count assumptions are absent",
    "no minimum-sample historical analogue for commissioning (minimum three required)",
]


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}: expected JSON object")
    return value


def _ledger_events(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    companies = ledger.get("companies")
    if not isinstance(companies, dict) or not isinstance(companies.get("DGKC"), dict):
        raise ValueError("company_event_ledger.json: DGKC company missing")
    events = companies["DGKC"].get("events")
    if not isinstance(events, list):
        raise ValueError("company_event_ledger.json: DGKC events missing")
    return {event.get("event_id"): event for event in events if isinstance(event, dict)}


def _documents(documents: dict[str, Any]) -> dict[str, dict[str, Any]]:
    value = documents.get("documents")
    if not isinstance(value, dict):
        raise ValueError("company_documents.json: documents missing")
    return {key: item for key, item in value.items() if isinstance(item, dict)}


def validate_retained_chain(ledger: dict[str, Any] | None = None, documents: dict[str, Any] | None = None) -> list[str]:
    """Return violations; an empty list means the retained chain is exact."""
    ledger = _load(EVENT_LEDGER) if ledger is None else ledger
    documents = _load(DOCUMENTS) if documents is None else documents
    events = _ledger_events(ledger)
    docs = _documents(documents)
    violations: list[str] = []
    for expected in EXPECTED_CHAIN:
        event = events.get(expected["event_id"])
        if not event:
            violations.append(f"{expected['event_id']}: missing retained event")
            continue
        if event.get("doc_id") != expected["doc_id"]:
            violations.append(f"{expected['event_id']}: document id mismatch")
        if event.get("event_date") is not None:
            violations.append(f"{expected['event_id']}: event_date must remain null")
        evidence = event.get("evidence")
        if not isinstance(evidence, list) or len(evidence) != 1:
            violations.append(f"{expected['event_id']}: evidence cardinality mismatch")
        else:
            row = evidence[0]
            for key in ("source_url", "page", "text"):
                expected_value = expected["url"] if key == "source_url" else expected[key]
                if row.get(key) != expected_value:
                    violations.append(f"{expected['event_id']}: evidence {key} mismatch")
        doc = docs.get(expected["doc_id"])
        if not doc:
            violations.append(f"{expected['doc_id']}: retained document missing")
            continue
        checks = {
            "source_url": expected["url"],
            "content_sha256": expected["hash"],
            "local_sha256": expected["hash"],
            "status": "ready",
            "stale": False,
            "published_at": None,
            "available_on": None,
        }
        for key, value in checks.items():
            if doc.get(key) != value:
                violations.append(f"{expected['doc_id']}: {key} mismatch")
        evidence_rows = doc.get("evidence")
        if not isinstance(evidence_rows, list) or not any(
            row.get("source_url") == expected["url"]
            and row.get("page") == expected["page"]
            and row.get("text") == expected["text"]
            for row in evidence_rows if isinstance(row, dict)
        ):
            violations.append(f"{expected['doc_id']}: document evidence mismatch")
    return violations


def build_seed(ledger: dict[str, Any] | None = None, documents: dict[str, Any] | None = None) -> dict[str, Any]:
    violations = validate_retained_chain(ledger, documents)
    if violations:
        raise ValueError("DGKC retained commissioning chain rejected: " + "; ".join(violations))
    return {
        "schema_version": SEED_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "symbol": "DGKC",
        "status": "Observed",
        "corroboration_status": "Corroborated",
        "formal_status": "blocked",
        "event": {
            "event_id": EXPECTED_CHAIN[-1]["event_id"],
            "event_family": "industrial_expansion_commissioning",
            "issuer": "DGKC",
            "transition": [
                {"stage": row["transition"], "event_id": row["event_id"], "document_id": row["doc_id"], "page": row["page"], "url": row["url"], "content_sha256": row["hash"], "text": row["text"]}
                for row in EXPECTED_CHAIN
            ],
            "event_date": None,
            "availability_date": None,
            "event_evidence_hash": None,
        },
        "reported_operating_operands": {
            "capacity_bags": 90_000_000,
            "capacity_unit": "bags",
            "location": "Quaid-e-Azam Business Park, Sheikhupura",
            "commissioning_timing": "third quarter of FY25",
            "fy25_npl_paper_bags": 43_200_000,
            "fy24_npl_paper_bags": 43_300_000,
            "fy25_npl_pp_bags": 29_700_000,
            "capex": None,
            "ramp_or_utilization": None,
            "dispatch_or_cost": None,
        },
        "fact_boundary": {
            "facts": ["FY23 L/C opened and 90m capacity", "FY24 installation", "FY25 Q3 commissioning", "FY25 NPL output"],
            "inferences": ["incremental capacity may change bag volume/procurement or NPPCL economics; DGKC attribution is unproven"],
        },
        "blockers": BLOCKERS,
        "source_chain_validated": True,
        "model_or_publish_eligible": False,
    }


def validate_seed(seed: dict[str, Any]) -> list[str]:
    """Reject attempts to relabel this evidence-only object as a formal case."""
    violations: list[str] = []
    if seed.get("status") != "Observed":
        violations.append("status must be Observed")
    if seed.get("corroboration_status") != "Corroborated":
        violations.append("corroboration_status must be Corroborated")
    if seed.get("formal_status") != "blocked":
        violations.append("formal_status must remain blocked")
    if seed.get("model_or_publish_eligible") is not False:
        violations.append("model_or_publish_eligible must remain false")
    return violations


if __name__ == "__main__":
    print(json.dumps(build_seed(), indent=2, ensure_ascii=False, sort_keys=True))
