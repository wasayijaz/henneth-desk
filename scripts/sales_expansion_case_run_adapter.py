"""Read-only orchestrator for the sales-led case-run envelope.

No state is written and no network provider is called.  The retained route
loads fixed local state authorities in-process and fails closed if the exact
BOP/PSO/GAL no-go evidence changes.  The fixture route is explicit,
deterministic and non-authoritative.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any

import sales_expansion_engine as engine
import sales_expansion_case_run_contract as contract


def _identity() -> dict[str, str]:
    return {
        "schema_version": "sales_expansion_case_run_v1",
        "adapter_version": "sales_expansion_case_run_adapter_v1",
        "case_id": "case_sales_expansion_unselected_v1",
        "case_family": "sales_led_expansion",
    }


def _fixture_identity() -> dict[str, str]:
    return {
        "symbol": "SALES-FIXTURE",
        "event_ref": "fixture:sales-expansion-v1",
        "effective_date": "2025-12-31",
        "valuation_date": "2025-12-31",
        "cutoff_at": "2025-12-31T00:00:00+05:00",
    }


def _prov(value: Any, note: str = "synthetic fixture only; non-authoritative") -> dict[str, Any]:
    return {
        "value": value,
        "label_type": "analyst",
        "analyst_ref": {"note_id": "fixture:sales-expansion-case-run-v1", "note": note},
        "available_on": _fixture_identity()["valuation_date"],
    }


def _fixture_case(label: str) -> dict[str, Any]:
    fixture = _fixture_identity()
    scale = {"bear": 0.8, "base": 1.0, "bull": 1.2}[label]
    quarters = [
        "2026-03-31", "2026-06-30", "2026-09-30", "2026-12-31",
        "2027-03-31", "2027-06-30", "2027-09-30", "2027-12-31",
    ]
    return {
        "symbol": fixture["symbol"],
        "event_ref": fixture["event_ref"],
        "case_label": label,
        "effective_date": fixture["effective_date"],
        "valuation_date": fixture["valuation_date"],
        "inputs": {
            "quarter_ends": _prov(quarters),
            "sales_hires_schedule": _prov([2, 3, 4, 5, 6, 7, 8, 9]),
            "support_hires_schedule": _prov([1] * 8),
            "starting_revenue_pkr": _prov(100_000_000.0),
            "sales_compensation_usd_annual": _prov(12_000.0),
            "support_compensation_usd_annual": _prov(8_000.0),
            "fx_pkr_usd": _prov(280.0),
            "marketing_spend_pkr_schedule": _prov([1_000_000.0 * scale] * 8),
            "productivity_revenue_pkr_per_sales_hire_schedule": _prov([
                5_000_000.0 * scale, 6_000_000.0 * scale, 7_000_000.0 * scale, 8_000_000.0 * scale,
                9_000_000.0 * scale, 10_000_000.0 * scale, 11_000_000.0 * scale, 12_000_000.0 * scale,
            ]),
            "gross_margin_pct": _prov(50.0),
            "working_capital_pct_revenue": _prov(10.0),
            "initial_investment_pkr": _prov(20_000_000.0),
            "effective_tax_pct": _prov(30.0),
            "shares_out": _prov(100_000_000.0),
            "discount_rate_pct_annual": _prov(12.0),
        },
    }


def _mechanism() -> dict[str, str]:
    return {
        "mechanism_id": "sales_expansion.hires_channel_productivity.v1",
        "description": "Sales hires and support capacity may expand revenue; compensation, marketing and working capital are explicit costs.",
        "arithmetic_engine": engine.FORMULA_ID,
        "authority": "sales_expansion_engine.quarterly_metrics and evaluate_case",
    }


def _policy() -> dict[str, bool]:
    return {
        "research_only": True,
        "no_advice": True,
        "real_retained_path_zero_numeric_outputs": True,
        "fixture_non_authoritative": True,
    }


def _readiness(status: str, reasons: list[str]) -> dict[str, Any]:
    clean = sorted(set(reasons))
    return {"status": status, "blocked_reasons": clean, "hard_block": True, "reason": clean[0] if clean else None}


def _envelope_base(*, fixture: bool) -> dict[str, Any]:
    identity = _identity()
    fixture_id = _fixture_identity()
    return {
        "schema_version": identity["schema_version"],
        "adapter_version": identity["adapter_version"],
        "status": "computed_fixture" if fixture else "blocked",
        "fixture_only": fixture,
        "fixture_identity": {"symbol": fixture_id["symbol"], "event_ref": fixture_id["event_ref"]} if fixture else None,
        "case_id": identity["case_id"],
        "case_family": identity["case_family"],
        "mechanism": _mechanism(),
        "scenario_runs": [],
        "blocked_reasons": [],
        "input_lineage": [],
        "retained_projection": None,
        "analogue_readiness": _readiness("not_ready", ["no_case_specific_historical_analogue"]),
        "formal_output_readiness": _readiness("not_ready", ["synthetic_fixture_not_formal_output"]),
        "policy": _policy(),
        "run_receipt": {},
    }


def _load_fixed_authorities() -> dict[str, Any]:
    repo = Path(__file__).resolve().parents[1].resolve()
    paths = {
        "company_event_ledger": (repo / "state" / "company_event_ledger.json").resolve(),
        "company_documents": (repo / "state" / "company_documents.json").resolve(),
        "research_index": (repo / "state" / "research_index.json").resolve(),
        "source_registry": (repo / "state" / "company_intel" / "source_registry.json").resolve(),
    }
    out: dict[str, Any] = {}
    for name, path in paths.items():
        with path.open("r", encoding="utf-8") as handle:
            out[name] = json.load(handle)
    return out


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _closed(value: Any, keys: set[str], path: str, violations: list[str]) -> bool:
    if type(value) is not dict:
        violations.append(f"{path}: must be a plain object")
        return False
    extra = sorted(set(value) - keys)
    missing = sorted(keys - set(value))
    violations.extend(f"{path}.{key}: unknown field" for key in extra)
    violations.extend(f"{path}.{key}: missing field" for key in missing)
    return not extra and not missing


def _require(value: Any, expected: Any, path: str, violations: list[str]) -> None:
    if value != expected:
        violations.append(f"{path}: expected {expected!r}, got {value!r}")


def _one_event(ledger: dict[str, Any], symbol: str, event_id: str, path: str, violations: list[str]) -> dict[str, Any]:
    companies = ledger.get("companies") or {}
    company = companies.get(symbol)
    if type(company) is not dict:
        violations.append(f"{path}: company ledger missing")
        return {}
    events = company.get("events")
    if type(events) is not list:
        violations.append(f"{path}.events: must be a list")
        return {}
    matches = [row for row in events if type(row) is dict and row.get("event_id") == event_id]
    if len(matches) != 1:
        violations.append(f"{path}: expected exactly one event {event_id}, found {len(matches)}")
        return {}
    return matches[0]


def _one_doc(documents: dict[str, Any], doc_id: str, path: str, violations: list[str]) -> dict[str, Any]:
    docs = documents.get("documents") or {}
    doc = docs.get(doc_id)
    if type(doc) is not dict:
        violations.append(f"{path}: document {doc_id} missing")
        return {}
    return doc


def _one_evidence(event: dict[str, Any], page: int, text: str, path: str, violations: list[str]) -> dict[str, Any]:
    evidence = event.get("evidence")
    if type(evidence) is not list:
        violations.append(f"{path}.evidence: must be a list")
        return {}
    matches = [row for row in evidence if type(row) is dict and row.get("page") == page and row.get("text") == text]
    if len(matches) != 1:
        violations.append(f"{path}.evidence: expected exact page/text evidence once, found {len(matches)}")
        return {}
    return matches[0]


def _research_index_doc(research_index: dict[str, Any], doc_id: str, path: str, violations: list[str]) -> dict[str, Any]:
    docs = research_index.get("documents") or {}
    doc = docs.get(doc_id)
    if type(doc) is not dict:
        violations.append(f"{path}: research-index document {doc_id} missing")
        return {}
    return doc


def _source_registry_ticker(source_registry: dict[str, Any], symbol: str, path: str, violations: list[str]) -> dict[str, Any]:
    tickers = source_registry.get("tickers") or {}
    row = tickers.get(symbol)
    if type(row) is not dict:
        violations.append(f"{path}: source-registry ticker {symbol} missing")
        return {}
    return row


def _document_link(row: dict[str, Any], doc_id: str, path: str, violations: list[str]) -> dict[str, Any]:
    links = row.get("document_links")
    if type(links) is not list:
        violations.append(f"{path}.document_links: must be a list")
        return {}
    matches = [link for link in links if type(link) is dict and link.get("id") == doc_id]
    if len(matches) != 1:
        violations.append(f"{path}.document_links: expected document link {doc_id} once, found {len(matches)}")
        return {}
    return matches[0]


def _issuer_home(row: dict[str, Any], path: str, violations: list[str]) -> dict[str, Any]:
    pages = row.get("monitored_pages")
    if type(pages) is not list:
        violations.append(f"{path}.monitored_pages: must be a list")
        return {}
    matches = [page for page in pages if type(page) is dict and page.get("kind") == "issuer_home"]
    if len(matches) != 1:
        violations.append(f"{path}.monitored_pages: expected one issuer_home, found {len(matches)}")
        return {}
    return matches[0]


def _source_ref_hash(ref: dict[str, Any]) -> str:
    return _sha256_text(json.dumps(ref, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))


def _retained_source_effective_cutoff(lineage: list[dict[str, Any]], violations: list[str]) -> str | None:
    dated_candidates: list[tuple[str, datetime]] = []
    for index, row in enumerate(lineage):
        if type(row) is not dict:
            continue
        ref = row.get("source_ref")
        if type(ref) is not dict:
            continue
        for field in ("event_date", "published_at"):
            raw = ref.get(field)
            if raw is None:
                continue
            parsed = _parse_dt(raw)
            if parsed is None:
                violations.append(f"retained cutoff: input_lineage[{index}].source_ref.{field} is not parseable")
                continue
            dated_candidates.append((raw, parsed))
    if not dated_candidates:
        violations.append("retained cutoff: no retained source-effective date available")
        return None
    return max(dated_candidates, key=lambda item: item[1])[0]


def _bop_lineage(authorities: dict[str, Any], violations: list[str]) -> dict[str, Any]:
    event_text = "easingly leveraging digital platforms, data analytics, and automation to improve customer acquisition, streamline operations, and drive growth in low-cost deposits\u2014particularly current accounts\u2014thereby strengthening net interest margins an\u2026"
    event = _one_event(authorities["company_event_ledger"], "BOP", "evt_a51de635bed77b8329cc", "company_event_ledger.BOP", violations)
    doc = _one_doc(authorities["company_documents"], "psx:272102", "company_documents", violations)
    index_doc = _research_index_doc(authorities["research_index"], "psx:272102", "research_index", violations)
    evidence = _one_evidence(event, 25, event_text, "company_event_ledger.BOP.evt_a51de635bed77b8329cc", violations)
    if event:
        _closed(event, {"event_id", "event_type", "event_date", "tickers", "doc_id", "evidence", "priority_weight"}, "company_event_ledger.BOP.evt_a51de635bed77b8329cc", violations)
        _require(event.get("event_type"), "acquisition", "BOP event_type", violations)
        _require(event.get("event_date"), "2026-03-05T12:29:00+05:00", "BOP event_date", violations)
        _require(event.get("tickers"), ["BOP"], "BOP tickers", violations)
        _require(event.get("doc_id"), "psx:272102", "BOP doc_id", violations)
    if doc:
        _require(doc.get("content_sha256"), "b2ae42c6a0bc8032863d3df5a86b23b7d22c00f0581db6ec6bbed2ec64575617", "BOP document content_sha256", violations)
        _require(doc.get("local_sha256"), doc.get("content_sha256"), "BOP document local_sha256", violations)
        _require(doc.get("source_url"), "https://dps.psx.com.pk/download/document/272102.pdf", "BOP document source_url", violations)
        _require(doc.get("title"), "Transmission of Annual Report for the Year Ended 12/31/2025", "BOP document title", violations)
        _require(doc.get("published_at"), "2026-03-05T12:29:00+05:00", "BOP document published_at", violations)
        _require(doc.get("status"), "ready", "BOP document status", violations)
        _require(doc.get("stale"), False, "BOP document stale", violations)
    if index_doc:
        _require(index_doc.get("content_sha256"), doc.get("content_sha256"), "BOP index content_sha256", violations)
        _require(index_doc.get("url"), doc.get("source_url"), "BOP index url", violations)
        _require(index_doc.get("published_at"), doc.get("published_at"), "BOP index published_at", violations)
        _require(index_doc.get("title"), doc.get("title"), "BOP index title", violations)
        _require(index_doc.get("hash"), "psx:272102", "BOP index hash", violations)
    if evidence:
        _require(evidence.get("source_url"), doc.get("source_url"), "BOP evidence source_url", violations)
    ref = {
        "id": "psx:272102",
        "event_id": "evt_a51de635bed77b8329cc",
        "document_id": "psx:272102",
        "url": doc.get("source_url"),
        "title": doc.get("title"),
        "source": doc.get("source"),
        "source_origin": "research_index_and_company_documents",
        "event_type": event.get("event_type"),
        "event_date": event.get("event_date"),
        "published_at": doc.get("published_at"),
        "retrieved_at": doc.get("retrieved_at"),
        "page": evidence.get("page"),
        "content_sha256": doc.get("content_sha256"),
        "evidence_sha256": _source_ref_hash({"document_id": "psx:272102", "event_id": "evt_a51de635bed77b8329cc", "page": evidence.get("page"), "text": evidence.get("text")}),
        "text": evidence.get("text"),
    }
    return {
        "kind": "retained_source_evidence",
        "symbol": "BOP",
        "role": "generic_strategy_narrative",
        "qualifies_sales_event": False,
        "no_go_reason": "generic_strategy_narrative_without_dated_sales_event",
        "source_ref": ref,
    }


def _pso_lineage(authorities: dict[str, Any], doc_id: str, event_id: str, page: int, text: str, violations: list[str]) -> dict[str, Any]:
    event = _one_event(authorities["company_event_ledger"], "PSO", event_id, "company_event_ledger.PSO", violations)
    doc = _one_doc(authorities["company_documents"], doc_id, "company_documents", violations)
    registry = _source_registry_ticker(authorities["source_registry"], "PSO", "source_registry.PSO", violations)
    link = _document_link(registry, doc_id, "source_registry.PSO", violations)
    evidence = _one_evidence(event, page, text, f"company_event_ledger.PSO.{event_id}", violations)
    if event:
        _closed(event, {"event_id", "event_type", "event_date", "tickers", "doc_id", "evidence", "priority_weight"}, f"company_event_ledger.PSO.{event_id}", violations)
        _require(event.get("event_date"), None, f"PSO {event_id} event_date", violations)
        _require(event.get("tickers"), ["PSO"], f"PSO {event_id} tickers", violations)
        _require(event.get("doc_id"), doc_id, f"PSO {event_id} doc_id", violations)
    if doc:
        _require(doc.get("doc_id"), doc_id, f"PSO {doc_id} doc_id", violations)
        _require(doc.get("local_sha256"), doc.get("content_sha256"), f"PSO {doc_id} local_sha256", violations)
        _require(doc.get("published_at"), None, f"PSO {doc_id} published_at", violations)
        _require(doc.get("status"), "ready", f"PSO {doc_id} status", violations)
        _require(doc.get("stale"), False, f"PSO {doc_id} stale", violations)
        _require(doc.get("source"), "Issuer website", f"PSO {doc_id} source", violations)
    if link:
        _require(link.get("id"), doc_id, f"PSO {doc_id} source-registry id", violations)
        _require(link.get("url"), doc.get("source_url"), f"PSO {doc_id} source-registry url", violations)
        _require(link.get("label"), doc.get("title"), f"PSO {doc_id} source-registry label", violations)
        _require(link.get("status"), "discovered", f"PSO {doc_id} source-registry status", violations)
    if evidence:
        _require(evidence.get("source_url"), doc.get("source_url"), f"PSO {event_id} evidence source_url", violations)
    ref = {
        "id": doc_id,
        "event_id": event_id,
        "document_id": doc_id,
        "url": doc.get("source_url"),
        "title": doc.get("title"),
        "source": doc.get("source"),
        "source_origin": "source_registry_document_link_and_company_documents",
        "event_type": event.get("event_type"),
        "event_date": event.get("event_date"),
        "published_at": doc.get("published_at"),
        "retrieved_at": doc.get("retrieved_at"),
        "page": evidence.get("page"),
        "content_sha256": doc.get("content_sha256"),
        "evidence_sha256": _source_ref_hash({"document_id": doc_id, "event_id": event_id, "page": evidence.get("page"), "text": evidence.get("text")}),
        "text": evidence.get("text"),
    }
    return {
        "kind": "retained_source_evidence",
        "symbol": "PSO",
        "role": "same_issuer_undated_product_material",
        "qualifies_sales_event": False,
        "no_go_reason": "undated_same_issuer_product_material",
        "source_ref": ref,
    }


def _gal_lineage(authorities: dict[str, Any], violations: list[str]) -> dict[str, Any]:
    registry = _source_registry_ticker(authorities["source_registry"], "GAL", "source_registry.GAL", violations)
    company = (authorities["company_event_ledger"].get("companies") or {}).get("GAL")
    if company not in (None, {}):
        violations.append("company_event_ledger.GAL: expected no retained GAL events")
    page = _issuer_home(registry, "source_registry.GAL", violations)
    if registry:
        _require(registry.get("symbol"), "GAL", "GAL registry symbol", violations)
        _require(registry.get("issuer_url"), "https://www.ghandharanissan.com.pk/", "GAL issuer_url", violations)
        _require(registry.get("status"), "ok", "GAL registry status", violations)
        _require(registry.get("document_links"), [], "GAL document_links", violations)
    if page:
        _require(page.get("url"), "https://www.ghandharanissan.com.pk/", "GAL issuer_home url", violations)
        _require(page.get("content_sha256"), "9fed93ec98418218bc7449c51856fa3e79c8c9edccb0443189778495bc0200e7", "GAL issuer_home content_sha256", violations)
        _require(page.get("status"), "ok", "GAL issuer_home status", violations)
    text = "source_registry issuer_home retained; company_event_ledger has no GAL events"
    ref = {
        "id": "issuer_home:" + str(page.get("content_sha256")),
        "event_id": None,
        "document_id": None,
        "url": page.get("url"),
        "title": page.get("label"),
        "source": "Issuer website",
        "source_origin": "source_registry_issuer_home_and_empty_company_ledger",
        "event_type": None,
        "event_date": None,
        "published_at": page.get("last_modified"),
        "retrieved_at": page.get("first_seen_at"),
        "page": None,
        "content_sha256": page.get("content_sha256"),
        "evidence_sha256": _source_ref_hash({"symbol": "GAL", "issuer_home": page.get("url"), "content_sha256": page.get("content_sha256"), "text": text}),
        "text": text,
    }
    return {
        "kind": "retained_source_evidence",
        "symbol": "GAL",
        "role": "issuer_home_no_qualifying_sales_event",
        "qualifies_sales_event": False,
        "no_go_reason": "no_retained_sales_event",
        "source_ref": ref,
    }


def derive_retained_sales_no_go(authorities: dict[str, Any]) -> dict[str, Any]:
    """Build the exact retained evidence projection or fail closed."""
    violations: list[str] = []
    expected_top = {
        "company_event_ledger": {"schema_version", "companies", "_meta"},
        "company_documents": {"schema_version", "documents", "_meta"},
        "research_index": {"documents", "by_ticker", "_meta"},
        "source_registry": {"schema_version", "tickers", "updated", "source", "pilot_count", "degraded", "_meta"},
    }
    for name, keys in expected_top.items():
        _closed(authorities.get(name), keys, name, violations)
    if violations:
        raise ValueError("retained sales authority shape violation: " + "; ".join(sorted(set(violations))))

    pso1_text = "Y GROUND, LAHORE CANTT LAHORE LAHORE EMPRESS FILLING STATION OPPOSITE RAILWAY POLICE HEAD QUARTER, EMPRESS ROAD LAHORE LAHORE EXPO VIEW F/S & CNG PLOT NO.1 -1A, BLOCK R MUHAMMAD ALI JOHAR TOWN LAHORE FAISAL PETROLEUM STATION PSO STATION, P\u2026"
    pso2_text = "SMS alerts) Telecom Operator *Push SMS Billing SMS *Email Report *Email Frequency Daily (default) Sr. No. Card No. Name on Card Email Address (for Email alerts) Mobile No. (for SMS alerts) Telecom Operator *Push SMS *Pull SMS *Email Report\u2026"
    lineage = [
        _bop_lineage(authorities, violations),
        _pso_lineage(authorities, "issuer:61d85f4626413576b676aed8", "evt_2f3bfdf4a586999e66b6", 4, pso1_text, violations),
        _pso_lineage(authorities, "issuer:ca78a4beec7f30b38e790a5e", "evt_30027cd832df431a70a9", 1, pso2_text, violations),
        _gal_lineage(authorities, violations),
    ]
    reasons = [
        "BOP:generic_strategy_narrative_without_dated_sales_event",
        "GAL:no_retained_sales_event",
        "PSO:undated_same_issuer_product_material",
        "sales_lane:no_canonical_dated_event",
    ]
    cutoff = _retained_source_effective_cutoff(lineage, violations)
    projection = {
        "schema_version": "sales_expansion_retained_projection_v1",
        "authority_files": [
            "state/company_event_ledger.json",
            "state/company_documents.json",
            "state/research_index.json",
            "state/company_intel/source_registry.json",
        ],
        "cutoff_at": cutoff,
        "blocked_reasons": sorted(set(reasons)),
        "input_lineage": lineage,
        "derivation": {
            "BOP": "Exact retained event evt_a51de635bed77b8329cc is a broad digital/customer-acquisition strategy narrative from an annual report, not a discrete dated rollout.",
            "PSO": "Exact retained issuer product materials share the PSO issuer origin but carry null event and published dates, so they are not dated sales expansion events.",
            "GAL": "Source registry retains the issuer home hash, while company_event_ledger contains no GAL event rows.",
        },
    }
    expected_lineage = contract.expected_real_source_refs()
    expected_reasons = contract.expected_real_blocked_reasons()
    if lineage != expected_lineage:
        violations.append("retained projection: exact source lineage drifted from contract")
    if projection["blocked_reasons"] != expected_reasons:
        violations.append("retained projection: exact blocked reasons drifted from contract")
    projected, projection_violations = contract.safe_json_projection(projection)
    violations.extend(projection_violations)
    if violations:
        raise ValueError("retained sales no-go derivation failed closed: " + "; ".join(sorted(set(violations))))
    return projected


def _parse_dt(value: str) -> datetime | None:
    for candidate in (value, value.replace(" ", "T")):
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone(timedelta(hours=5)))
        return parsed
    return None


def build_real_case_run() -> dict[str, Any]:
    """Return the current retained path, blocked after local authority checks."""
    projection = derive_retained_sales_no_go(_load_fixed_authorities())
    envelope = _envelope_base(fixture=False)
    envelope["blocked_reasons"] = projection["blocked_reasons"]
    envelope["input_lineage"] = projection["input_lineage"]
    envelope["retained_projection"] = projection
    envelope["formal_output_readiness"] = _readiness("blocked", envelope["blocked_reasons"])
    envelope["run_receipt"] = {
        "cutoff_at": projection["cutoff_at"],
        "input_sha256": contract.sha256_json(contract.real_receipt_payload(envelope)),
        "output_sha256": contract.sha256_json([]),
        "retained_projection_sha256": contract.sha256_json(projection),
        "contract_version": _identity()["schema_version"],
    }
    violations = contract.validate_case_run(envelope)
    if violations:
        raise ValueError("sales expansion real case-run contract violation: " + "; ".join(violations))
    return envelope


def _build_real_case_run_for_test(authorities: dict[str, Any]) -> dict[str, Any]:
    projection = derive_retained_sales_no_go(authorities)
    envelope = _envelope_base(fixture=False)
    envelope["blocked_reasons"] = projection["blocked_reasons"]
    envelope["input_lineage"] = projection["input_lineage"]
    envelope["retained_projection"] = projection
    envelope["formal_output_readiness"] = _readiness("blocked", envelope["blocked_reasons"])
    envelope["run_receipt"] = {
        "cutoff_at": projection["cutoff_at"],
        "input_sha256": contract.sha256_json(contract.real_receipt_payload(envelope)),
        "output_sha256": contract.sha256_json([]),
        "retained_projection_sha256": contract.sha256_json(projection),
        "contract_version": _identity()["schema_version"],
    }
    violations = contract.validate_case_run(envelope)
    if violations:
        raise ValueError("sales expansion real case-run contract violation: " + "; ".join(violations))
    return envelope


def build_fixture_case_run() -> dict[str, Any]:
    """Compute deterministic bear/base/bull synthetic runs through the kernel."""
    runs: list[dict[str, Any]] = []
    for label in ("bear", "base", "bull"):
        case = _fixture_case(label)
        result = engine.evaluate_case(case)
        runs.append({"scenario": label, "status": "computed", "blocked_reasons": [], "case": case, "result": result})
    envelope = _envelope_base(fixture=True)
    envelope["scenario_runs"] = runs
    envelope["input_lineage"] = [
        dict(copy.deepcopy(record), field=field)
        for field, record in sorted(runs[0]["case"]["inputs"].items())
    ]
    envelope["run_receipt"] = {
        "cutoff_at": _fixture_identity()["cutoff_at"],
        "input_sha256": contract.sha256_json([r["case"] for r in runs]),
        "output_sha256": contract.sha256_json([r["result"] for r in runs]),
        "retained_projection_sha256": contract.sha256_json(None),
        "contract_version": _identity()["schema_version"],
    }
    violations = contract.validate_case_run(envelope)
    if violations:
        raise ValueError("sales expansion fixture case-run contract violation: " + "; ".join(violations))
    return envelope


def build_case_run(*, fixture: bool = False) -> dict[str, Any]:
    return build_fixture_case_run() if fixture else build_real_case_run()


__all__ = ["build_case_run", "build_real_case_run", "build_fixture_case_run"]
