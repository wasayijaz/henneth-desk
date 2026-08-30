"""Fail-closed, read-only DGKC PP-bag commissioning evidence seed.

The seed is intentionally an evidence object only.  It never writes state and
does not estimate capex, margins, utilization, earnings or valuation.
"""
from __future__ import annotations

import json
from pathlib import Path
import math
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVENT_LEDGER = ROOT / "state" / "company_event_ledger.json"
DOCUMENTS = ROOT / "state" / "company_documents.json"

CONTRACT_VERSION = "dgkc_commissioning_seed_contract_v2"
SEED_SCHEMA = "dgkc_commissioning_evidence_seed_v2"

# This seed is deliberately not an IntelligenceCase.  These labels are kept
# outside that lifecycle so an undated clue cannot be promoted by accident.
EVIDENCE_STATUS = "evidence_only"
CORROBORATION_STATUS = "uncorroborated"
SELECTION_STATUS = "unselected"
GO_NO_GO = "no_go"

FORBIDDEN_KEYS = {
    "forecast", "forecast_value", "valuation", "fair_value", "market_expectations",
    "price_target", "target_price", "recommendation", "advice", "probability",
    "expected_return", "scenario", "model", "modelled", "modeled", "eps", "ebitda",
    "fcf", "free_cash_flow", "npv", "roic", "margin", "share_price", "price",
}
MAX_NUMERIC = 10**15

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


def _ledger_events(ledger: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Return DGKC events and structural violations without trusting input keys."""
    violations: list[str] = []
    if type(ledger) is not dict:
        return [], ["company_event_ledger.json: root must be an object"]
    companies = ledger.get("companies")
    if type(companies) is not dict:
        return [], ["company_event_ledger.json: companies must be an object"]
    dgkc = companies.get("DGKC")
    if type(dgkc) is not dict:
        return [], ["company_event_ledger.json: DGKC company missing"]
    events = dgkc.get("events")
    if type(events) is not list:
        return [], ["company_event_ledger.json: DGKC events missing"]
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, event in enumerate(events):
        if type(event) is not dict:
            violations.append(f"DGKC events[{index}]: object required")
            continue
        event_id = event.get("event_id")
        if type(event_id) is not str:
            # Do not interpolate attacker-controlled repr/str values.
            violations.append(f"DGKC events[{index}]: event_id must be a string")
            continue
        if event_id in seen:
            violations.append(f"{event_id}: duplicate retained event")
        seen.add(event_id)
        rows.append(event)
    return rows, violations


def _documents(documents: Any) -> tuple[list[tuple[str, dict[str, Any]]], list[str]]:
    """Return retained documents and structural violations safely."""
    violations: list[str] = []
    if type(documents) is not dict:
        return [], ["company_documents.json: root must be an object"]
    value = documents.get("documents")
    if type(value) is not dict:
        return [], ["company_documents.json: documents missing"]
    rows: list[tuple[str, dict[str, Any]]] = []
    for index, (key, item) in enumerate(value.items()):
        if type(key) is not str:
            violations.append(f"documents[{index}]: document id must be a string")
            continue
        if type(item) is not dict:
            violations.append(f"documents[{index}]: document must be an object")
            continue
        rows.append((key, item))
    return rows, violations


def _find_event(events: list[dict[str, Any]], event_id: str) -> dict[str, Any] | None:
    matches = [event for event in events if event.get("event_id") == event_id]
    return matches[0] if matches else None


def _find_document(documents: list[tuple[str, dict[str, Any]]], doc_id: str) -> dict[str, Any] | None:
    for key, item in documents:
        if key == doc_id:
            return item
    return None


def validate_retained_chain(ledger: dict[str, Any] | None = None, documents: dict[str, Any] | None = None) -> list[str]:
    """Return violations; an empty list means the retained chain is exact."""
    violations: list[str] = []
    try:
        ledger = _load(EVENT_LEDGER) if ledger is None else ledger
    except Exception:
        return ["company_event_ledger.json: unreadable root"]
    try:
        documents = _load(DOCUMENTS) if documents is None else documents
    except Exception:
        return ["company_documents.json: unreadable root"]
    events, event_violations = _ledger_events(ledger)
    docs, document_violations = _documents(documents)
    violations.extend(event_violations)
    violations.extend(document_violations)
    for expected in EXPECTED_CHAIN:
        event = _find_event(events, expected["event_id"])
        if not event:
            violations.append(f"{expected['event_id']}: missing retained event")
            continue
        if event.get("doc_id") != expected["doc_id"]:
            violations.append(f"{expected['event_id']}: document id mismatch")
        for date_key in ("event_date", "availability_date", "effective_date"):
            if event.get(date_key) is not None:
                violations.append(f"{expected['event_id']}: {date_key} must remain null")
        if event.get("tickers") != ["DGKC"]:
            violations.append(f"{expected['event_id']}: issuer attribution mismatch")
        evidence = event.get("evidence")
        if not isinstance(evidence, list) or len(evidence) != 1:
            violations.append(f"{expected['event_id']}: evidence cardinality mismatch")
        else:
            row = evidence[0]
            if type(row) is not dict:
                violations.append(f"{expected['event_id']}: evidence row must be an object")
                row = {}
            for key in ("source_url", "page", "text"):
                expected_value = expected["url"] if key == "source_url" else expected[key]
                if row.get(key) != expected_value:
                    violations.append(f"{expected['event_id']}: evidence {key} mismatch")
            for forbidden_date in ("event_date", "published_at", "available_on", "availability_date"):
                if row.get(forbidden_date) is not None:
                    violations.append(f"{expected['event_id']}: evidence date must remain absent")
        doc = _find_document(docs, expected["doc_id"])
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
        if isinstance(evidence_rows, list):
            matching = [
                row for row in evidence_rows
                if isinstance(row, dict)
                and row.get("source_url") == expected["url"]
                and row.get("page") == expected["page"]
                and row.get("text") == expected["text"]
            ]
            if len(matching) != 1:
                violations.append(f"{expected['doc_id']}: exact source evidence cardinality mismatch")
    return violations


def build_seed(ledger: dict[str, Any] | None = None, documents: dict[str, Any] | None = None) -> dict[str, Any]:
    violations = validate_retained_chain(ledger, documents)
    if violations:
        raise ValueError("DGKC retained commissioning chain rejected: " + "; ".join(violations))
    return {
        "schema_version": SEED_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "symbol": "DGKC",
        "status": EVIDENCE_STATUS,
        "corroboration_status": CORROBORATION_STATUS,
        "selection_status": SELECTION_STATUS,
        "go_no_go": GO_NO_GO,
        "intelligence_case_eligible": False,
        "selected_industrial_case": "MLCF",
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
            "scope": "reported_historical_source_bound_only",
        },
        "forward_model_operands": {
            "status": "not_available",
            "values": {},
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
    """Validate the closed, evidence-only shape without trusting caller objects."""
    violations: list[str] = []
    if type(seed) is not dict:
        return ["seed root must be an object"]

    allowed = {
        "schema_version", "contract_version", "symbol", "status", "corroboration_status",
        "selection_status", "go_no_go", "intelligence_case_eligible", "selected_industrial_case",
        "formal_status", "event", "reported_operating_operands", "forward_model_operands",
        "fact_boundary", "blockers", "source_chain_validated", "model_or_publish_eligible",
    }
    nested_allowed = {
        "event": {"event_id", "event_family", "issuer", "transition", "event_date", "availability_date", "event_evidence_hash"},
        "transition": {"stage", "event_id", "document_id", "page", "url", "content_sha256", "text"},
        "reported_operating_operands": {"capacity_bags", "capacity_unit", "location", "commissioning_timing", "fy25_npl_paper_bags", "fy24_npl_paper_bags", "fy25_npl_pp_bags", "capex", "ramp_or_utilization", "dispatch_or_cost", "scope"},
        "forward_model_operands": {"status", "values"},
        "fact_boundary": {"facts", "inferences"},
    }

    seen: set[int] = set()

    def walk(value: Any, path: str, parent: str | None = None, depth: int = 0) -> None:
        if depth > 32:
            violations.append(f"{path or 'seed'}: nesting depth exceeds bound")
            return
        if type(value) is dict:
            identity = id(value)
            if identity in seen:
                violations.append(f"{path or 'seed'}: cyclic object is not valid JSON")
                return
            seen.add(identity)
            allowed_here = allowed if not path else nested_allowed.get(parent or "")
            for key, child in value.items():
                if type(key) is not str:
                    violations.append(f"{path or 'seed'}: key must be a string")
                    continue
                lowered = key.lower()
                if lowered in FORBIDDEN_KEYS:
                    violations.append(f"{path or 'seed'}: forbidden key {key}")
                if allowed_here is not None and key not in allowed_here:
                    violations.append(f"{path or 'seed'}: unknown key {key}")
                child_path = f"{path}.{key}" if path else key
                walk(child, child_path, key if key in nested_allowed else parent, depth + 1)
            seen.remove(identity)
        elif type(value) is list:
            identity = id(value)
            if identity in seen:
                violations.append(f"{path or 'seed'}: cyclic object is not valid JSON")
                return
            seen.add(identity)
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]", parent, depth + 1)
            seen.remove(identity)
        elif type(value) in (int, float):
            if not math.isfinite(float(value)):
                violations.append(f"{path}: numeric value must be finite")
            elif abs(float(value)) > MAX_NUMERIC:
                violations.append(f"{path}: numeric value exceeds bound")
        elif value is None or type(value) in (str, bool):
            return
        else:
            violations.append(f"{path or 'seed'}: unsupported value type")

    walk(seed, "")
    checks = (
        ("schema_version", SEED_SCHEMA), ("contract_version", CONTRACT_VERSION), ("symbol", "DGKC"),
        ("status", EVIDENCE_STATUS), ("corroboration_status", CORROBORATION_STATUS),
        ("selection_status", SELECTION_STATUS), ("go_no_go", GO_NO_GO),
        ("intelligence_case_eligible", False), ("selected_industrial_case", "MLCF"),
        ("formal_status", "blocked"), ("source_chain_validated", True),
        ("model_or_publish_eligible", False),
    )
    for key, expected in checks:
        if seed.get(key) != expected:
            violations.append(f"{key} must remain {expected!r}")
    event = seed.get("event")
    if type(event) is not dict:
        violations.append("event must be an object")
    else:
        if event.get("event_date") is not None or event.get("availability_date") is not None or event.get("event_evidence_hash") is not None:
            violations.append("event dates and evidence hash must remain null")
        if event.get("issuer") != "DGKC":
            violations.append("event issuer must remain DGKC")
        transition = event.get("transition")
        if type(transition) is not list or len(transition) != len(EXPECTED_CHAIN):
            violations.append("event transition must retain the exact three-source chain")
        elif type(transition) is list:
            for index, (row, expected) in enumerate(zip(transition, EXPECTED_CHAIN)):
                if type(row) is not dict:
                    violations.append(f"event transition[{index}] must be an object")
                    continue
                expected_row = {
                    "stage": expected["transition"], "event_id": expected["event_id"],
                    "document_id": expected["doc_id"], "page": expected["page"],
                    "url": expected["url"], "content_sha256": expected["hash"],
                    "text": expected["text"],
                }
                for key, expected_value in expected_row.items():
                    if row.get(key) != expected_value:
                        violations.append(f"event transition[{index}] {key} mismatch")
    operands = seed.get("reported_operating_operands")
    if type(operands) is not dict or operands.get("capex") is not None or operands.get("ramp_or_utilization") is not None or operands.get("dispatch_or_cost") is not None:
        violations.append("forward economics operands must remain unavailable")
    forward = seed.get("forward_model_operands")
    if type(forward) is not dict or forward.get("status") != "not_available" or forward.get("values") != {}:
        violations.append("forward model operands must remain unavailable")
    boundary = seed.get("fact_boundary")
    if type(boundary) is not dict:
        violations.append("fact_boundary must be an object")
    else:
        for key in ("facts", "inferences"):
            values = boundary.get(key)
            if type(values) is not list or any(type(item) is not str for item in values):
                violations.append(f"fact_boundary.{key} must contain text only")
    blockers = seed.get("blockers")
    if type(blockers) is not list or any(type(item) is not str for item in blockers):
        violations.append("blockers must contain text only")
    return violations


if __name__ == "__main__":
    print(json.dumps(build_seed(), indent=2, ensure_ascii=False, sort_keys=True))
