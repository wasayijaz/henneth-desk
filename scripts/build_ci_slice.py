#!/usr/bin/env python3
"""Build the private Company Intelligence app data slice.

Writes Henneth Desk 2.CI.0/data/company_intelligence.json from existing state files.
This is the only data file the CI app reads. It is a private research surface, but it still
keeps the same rule: every displayed fact traces to the state layer or is marked unknown.
"""
import time
from datetime import date
from pathlib import Path

from psx_data import ROOT, STATE, load_json, save_json
from document_events import event_is_supported
from build_ci_completion_matrix import slice_summary as _completion_matrix_summary

APP_DIR = ROOT / "Henneth Desk 2.CI.0"
OUT = APP_DIR / "data" / "company_intelligence.json"


def _num(value):
    try:
        return float(str(value).replace(",", "").replace("%", "").replace("Rs", "").strip())
    except (TypeError, ValueError):
        return None


def _round(value, places=2):
    n = _num(value)
    return round(n, places) if n is not None else None


def _url(value):
    value = str(value or "").strip()
    return value if value.startswith(("http://", "https://")) else None


def _iso_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _state_date(state):
    if not isinstance(state, dict):
        return None
    for key in ("as_of", "updated", "built", "fetched"):
        parsed = _iso_date(state.get(key))
        if parsed:
            return parsed
    for key in ("_meta", "meta"):
        meta = state.get(key)
        if isinstance(meta, dict) and meta:
            parsed = _state_date(meta)
            if parsed:
                return parsed
    return None


def _slice_source_cutoff(*states):
    dates = [_state_date(state) for state in states]
    dates = [value for value in dates if value]
    return max(dates) if dates else None


def _finite(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _source_ok(source, cutoff):
    if not isinstance(source, dict):
        return False
    available_on = _iso_date(source.get("available_on"))
    if not available_on or (cutoff and available_on > cutoff):
        return False
    return bool(source.get("id") and source.get("label") and (source.get("path") or _url(source.get("url"))))


def _reference_source_fact(fact, cutoff):
    if not isinstance(fact, dict):
        return None
    available_on = _iso_date(fact.get("available_on"))
    period_end = _iso_date(fact.get("period_end"))
    if not available_on or not period_end or (cutoff and available_on > cutoff):
        return None
    normalized_value = _finite(fact.get("normalized_value"))
    if normalized_value is None:
        return None
    if not fact.get("fact_id") or not fact.get("document_id") or not _url(fact.get("source_url")):
        return None
    return {
        "line": fact.get("line"),
        "fact_id": fact.get("fact_id"),
        "document_id": fact.get("document_id"),
        "content_sha256": fact.get("content_sha256"),
        "source_url": _url(fact.get("source_url")),
        "period_end": period_end,
        "available_on": available_on,
        "statement_type": fact.get("statement_type"),
        "period_type": fact.get("period_type"),
        "duration_months": fact.get("duration_months"),
        "consolidation": fact.get("consolidation"),
        "currency": fact.get("currency"),
        "unit": fact.get("unit"),
        "unit_multiplier": fact.get("unit_multiplier"),
        "normalized_value": normalized_value,
        "source_method": fact.get("source_method"),
        "source_revision": fact.get("source_revision"),
        "evidence_pages": fact.get("evidence_pages") or [],
    }


def _historical_reference_cases(assumptions_state, sym, cutoff):
    cases = []
    rejected = 0
    for record in assumptions_state.get("records") or []:
        if not isinstance(record, dict) or record.get("symbol") != sym:
            continue
        if record.get("record_type") != "derived_reference_case":
            continue
        source = record.get("source") or {}
        available_on = _iso_date(record.get("available_on") or source.get("available_on"))
        source_facts = [
            _reference_source_fact(fact, cutoff)
            for fact in (record.get("source_facts") or [])
        ]
        source_facts = [fact for fact in source_facts if fact]
        safe = (
            record.get("approved") is False
            and "value" not in record
            and available_on is not None
            and (not cutoff or available_on <= cutoff)
            and _source_ok(source, cutoff)
            and len(source_facts) == len(record.get("source_facts") or [])
            and bool(source_facts)
        )
        if not safe:
            rejected += 1
            continue
        cases.append({
            "metric": record.get("metric"),
            "derived_value": _round(record.get("derived_value"), 4),
            "unit": record.get("unit"),
            "status": "historical_reference_case_not_owner_approved",
            "record_type": record.get("record_type"),
            "epistemic_type": record.get("epistemic_type"),
            "case_type": record.get("case_type"),
            "assumption_status": record.get("assumption_status"),
            "approval_scope": record.get("approval_scope"),
            "approved": False,
            "available_on": available_on,
            "formula_version": record.get("formula_version"),
            "period_ends": [_iso_date(value) for value in (record.get("period_ends") or []) if _iso_date(value)],
            "source": {
                "id": source.get("id"),
                "label": source.get("label"),
                "path": source.get("path"),
                "url": _url(source.get("url")),
                "available_on": _iso_date(source.get("available_on")),
            },
            "formula": record.get("formula") or {},
            "source_facts": source_facts,
            "policy": {
                "historical_baseline_only": True,
                "not_owner_approved": True,
                "not_a_forecast": True,
                "not_a_valuation": True,
                "not_market_expectations": True,
                "not_accepted_by_formal_engine_approved_records": True,
            },
        })
    cases.sort(key=lambda row: (row.get("metric") or "", row.get("available_on") or "", row.get("source", {}).get("id") or ""))
    return {
        "status": "available" if cases else "none",
        "case_count": len(cases),
        "rejected_record_count": rejected,
        "source_cutoff": cutoff,
        "policy": {
            "historical_baselines_only": True,
            "not_owner_approved_assumptions": True,
            "not_forecasts_or_valuations_or_market_expectations": True,
            "formal_engine_eligibility_unchanged": True,
        },
        "cases": cases,
    }


def _reference_case_meta(assumptions_state, cutoff, rows):
    counts = [((row.get("historical_reference_cases") or {}).get("case_count") or 0) for row in rows]
    return {
        "schema_version": assumptions_state.get("schema_version"),
        "as_of": assumptions_state.get("as_of"),
        "source_cutoff": cutoff,
        "source": assumptions_state.get("source") or {},
        "policy": {
            "historical_baselines_only": True,
            "not_owner_approved_assumptions": True,
            "not_forecasts_or_valuations_or_market_expectations": True,
            "formal_engine_eligibility_unchanged": True,
        },
        "summary": {
            "company_count": len(rows),
            "company_with_reference_cases_count": sum(1 for count in counts if count),
            "reference_case_count": sum(counts),
        },
    }


def _private_thesis_storage_meta(receipt):
    if not isinstance(receipt, dict):
        receipt = {}
    receipts = receipt.get("live_verification_receipts") or []
    latest = receipts[-1] if receipts and isinstance(receipts[-1], dict) else {}
    return {
        "schema_status": receipt.get("schema_status") or "unknown",
        "live_verification_status": receipt.get("live_verification_status") or "unknown",
        "live_verification_receipt_count": len(receipts) if isinstance(receipts, list) else 0,
        "live_verification_latest_outcome": latest.get("outcome") or "none",
        "completion_boundary": receipt.get("completion_boundary"),
        "live_verification_required": receipt.get("live_verification_required") or [],
    }


def _assumption_gap_product(row):
    if not isinstance(row, dict):
        return {}
    return {
        "status": row.get("status"),
        "required_approved_records": [
            value for value in (row.get("required_approved_records") or [])
            if isinstance(value, str) and value
        ],
        "accepted_records": [
            {
                "metric": ref.get("metric"),
                "record_type": ref.get("record_type"),
                "approval_scope": ref.get("approval_scope"),
                "available_on": _iso_date(ref.get("available_on")),
                "source_id": ref.get("source_id"),
                "source_label": ref.get("source_label"),
                "source_path": ref.get("source_path"),
                "source_url": _url(ref.get("source_url")),
            }
            for ref in (row.get("accepted_records") or [])
            if isinstance(ref, dict)
        ],
        "missing_approved_records": [
            value for value in (row.get("missing_approved_records") or [])
            if isinstance(value, str) and value
        ],
        "missing_prerequisites": [
            value for value in (row.get("missing_prerequisites") or [])
            if isinstance(value, str) and value
        ],
        "policy": row.get("policy") or {},
    }


def _assumption_gap_review(assumptions_state, sym):
    gaps = assumptions_state.get("assumption_gaps") or {}
    companies = gaps.get("companies") or {}
    row = companies.get(sym)
    if not isinstance(row, dict):
        return {
            "symbol": sym,
            "status": "assumption_gap_manifest_not_emitted",
            "products": {},
            "historical_reference_cases": [],
            "reference_cases_can_satisfy_missing_records": False,
            "next_required_action": "financial_engine_assumption_gap_manifest_required",
            "policy": {
                "gap_manifest_only": True,
                "does_not_approve_assumptions": True,
                "does_not_compute_formal_outputs": True,
                "derived_reference_cases_are_not_approved_records": True,
            },
        }
    products = row.get("products") or {}
    return {
        "symbol": sym,
        "status": row.get("status"),
        "forecast_readiness_status": row.get("forecast_readiness_status"),
        "financial_model_inputs_status": row.get("financial_model_inputs_status"),
        "qualified_period_count": row.get("qualified_period_count"),
        "products": {
            key: _assumption_gap_product(products.get(key))
            for key in ("forecast", "valuation", "market_expectations")
        },
        "historical_reference_cases": [
            {
                "metric": ref.get("metric"),
                "assumption_status": ref.get("assumption_status"),
                "case_type": ref.get("case_type"),
                "formula_version": ref.get("formula_version"),
                "available_on": _iso_date(ref.get("available_on")),
                "source_id": ref.get("source_id"),
                "policy": ref.get("policy") or {},
            }
            for ref in (row.get("historical_reference_cases") or [])
            if isinstance(ref, dict)
        ],
        "reference_cases_can_satisfy_missing_records": row.get("reference_cases_can_satisfy_missing_records") is True,
        "next_required_action": row.get("next_required_action"),
        "source": gaps.get("source") or {},
        "policy": gaps.get("policy") or {},
    }


def _assumption_gap_meta(assumptions_state):
    gaps = assumptions_state.get("assumption_gaps") or {}
    return {
        "schema_version": gaps.get("schema_version"),
        "as_of": gaps.get("as_of"),
        "source": gaps.get("source") or {},
        "summary": gaps.get("summary") or {},
        "policy": gaps.get("policy") or {},
    }


def _latest_news(news, sym, limit=3):
    rows = [n for n in news if sym in (n.get("tickers") or [])]
    rows.sort(key=lambda n: n.get("ts") or "", reverse=True)
    return [
        {
            "date": (n.get("ts") or "")[:10],
            "impact": n.get("impact"),
            "headline": n.get("headline"),
            "url": _url(n.get("url")),
        }
        for n in rows[:limit]
        if n.get("headline")
    ]


def _research_docs(research, sym, limit=5):
    return [
        {
            "date": d.get("date"),
            "type": d.get("doc_type") or d.get("source"),
            "title": d.get("one_line") or d.get("digest"),
            "url": _url(d.get("url")),
        }
        for d in (research.get("by_ticker", {}) or {}).get(sym, [])[:limit]
    ]


def _receipt_document_id(row):
    return row.get("doc_id") or row.get("document_id")


def _brief_receipt_status(receipt_state):
    approved = {}
    for receipt in receipt_state.get("receipts") or []:
        if not isinstance(receipt, dict):
            continue
        for item in receipt.get("based_on") or []:
            if not isinstance(item, dict):
                continue
            doc_id = _receipt_document_id(item)
            content_sha256 = item.get("content_sha256")
            if not doc_id or not content_sha256:
                continue
            approved[(doc_id, content_sha256)] = {
                "approval_status": "approved",
                "synthesis_status": "complete",
                "training_mode": True,
                "receipt_id": receipt.get("receipt_id"),
                "brief_id": receipt.get("brief_id"),
                "approved_at": receipt.get("approved_at"),
            }
    return approved


def _document_queue_status(queue_state, receipt_state=None):
    approved = _brief_receipt_status(receipt_state or {})
    rows = queue_state.get("history") or queue_state.get("queue") or []
    status = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        doc_id = _receipt_document_id(row)
        if not doc_id:
            continue
        key = (doc_id, row.get("content_sha256"))
        status[key] = {
            "approval_status": row.get("approval_status"),
            "synthesis_status": row.get("synthesis_status"),
            "training_mode": bool(row.get("training_mode")),
        }
        if key in approved:
            status[key] = approved[key]
    return status


def _company_filings(document_state, queue_status, sym, limit=30):
    rows = []
    for doc in (document_state.get("documents") or {}).values():
        if sym not in (doc.get("tickers") or []):
            continue
        evidence = [
            {
                "page": item.get("page"),
                "text": item.get("text"),
                "source_url": _url(item.get("source_url") or doc.get("source_url")),
            }
            for item in (doc.get("evidence") or [])[:4]
            if isinstance(item, dict) and item.get("text")
        ]
        facts = [
            {
                "fact_id": fact.get("fact_id"),
                "type": fact.get("fact_type"),
                "raw_value": fact.get("raw_value"),
                "normalized_value": fact.get("normalized_value"),
                "unit": fact.get("unit"),
                "currency": fact.get("currency"),
                "scale_multiplier": fact.get("scale_multiplier"),
                "evidence": (fact.get("evidence") or [])[:1],
            }
            for fact in (doc.get("facts") or [])[:8]
            if isinstance(fact, dict)
        ]
        queue = queue_status.get((doc.get("doc_id"), doc.get("content_sha256")), {})
        rows.append({
            "doc_id": doc.get("doc_id"),
            "date": doc.get("published_at"),
            "type": doc.get("doc_type"),
            "title": doc.get("title"),
            "url": _url(doc.get("source_url")),
            "source": doc.get("source"),
            "status": doc.get("status"),
            "error": doc.get("error"),
            "content_sha256": doc.get("content_sha256"),
            "evidence": evidence,
            "facts": facts,
            "synthesis": queue,
        })
    rows.sort(key=lambda row: (row.get("date") or "", row.get("doc_id") or ""), reverse=True)
    return rows[:limit]


def _company_timeline(event_state, sym, limit=50):
    company = (event_state.get("companies") or {}).get(sym) or {}
    events = [
        {
            "event_id": event.get("event_id"),
            "doc_id": event.get("doc_id"),
            "date": event.get("event_date"),
            "type": event.get("event_type"),
            "priority_weight": event.get("priority_weight"),
            "evidence": (event.get("evidence") or [])[:2],
        }
        for event in (company.get("events") or [])
        if isinstance(event, dict) and event_is_supported(event)
    ]
    events.sort(key=lambda row: (row.get("date") or "", row.get("event_id") or ""), reverse=True)
    changes = [
        {
            "change_id": change.get("change_id"),
            "doc_id": change.get("doc_id"),
            "date": change.get("changed_at"),
            "type": change.get("change_type") or "document_revision",
            "previous_sha256": change.get("previous_sha256"),
            "content_sha256": change.get("content_sha256"),
            "fact_delta": change.get("fact_delta"),
        }
        for change in (company.get("changes") or [])
        if isinstance(change, dict)
    ]
    changes.sort(key=lambda row: (row.get("date") or "", row.get("change_id") or ""), reverse=True)
    return events[:limit], changes[:20]


def _company_sources(source_state, sym):
    row = ((source_state.get("tickers") or source_state.get("companies") or {}).get(sym) or {})
    sources = row.get("monitored_pages") if isinstance(row.get("monitored_pages"), list) else []
    document_links = row.get("document_links") if isinstance(row.get("document_links"), list) else []
    return {
        "status": row.get("status") or source_state.get("status") or "unknown",
        "error": row.get("error"),
        "issuer_url": _url(row.get("issuer_url") or row.get("website")),
        "sources": [
            {
                "kind": source.get("kind"),
                "url": _url(source.get("url")),
                "title": source.get("label"),
                "changed": bool(source.get("previous_sha256")),
                "last_changed": source.get("last_changed_at"),
                "first_seen": source.get("first_seen_at"),
                "status": source.get("status"),
            }
            for source in sources[:12]
            if isinstance(source, dict) and _url(source.get("url"))
        ],
        "documents": [
            {
                "id": document.get("id"),
                "type": document.get("document_type"),
                "title": document.get("label"),
                "url": _url(document.get("url")),
                "first_seen": document.get("first_seen_at"),
            }
            for document in document_links[:40]
            if isinstance(document, dict) and _url(document.get("url"))
        ],
    }


def _offmarket(offmarket, sym):
    shares = value = trades = days = 0
    for day_data in (offmarket.get("days") or {}).values():
        row = day_data.get(sym) if isinstance(day_data, dict) else None
        if not row:
            continue
        shares += row.get("shares") or 0
        value += row.get("value") or 0
        trades += row.get("trades") or 0
        days += 1
    return None if days == 0 else {
        "shares": shares,
        "value_pkr": value,
        "trades": trades,
        "days": days,
        "retention_days": offmarket.get("retention_days"),
    }


def _insider(insider, sym):
    rows = list((insider.get("symbols") or {}).get(sym) or [])
    rows.sort(key=lambda r: r.get("date") or "", reverse=True)
    return [
        {
            "date": r.get("date"),
            "title": r.get("title"),
            "pdf_url": r.get("pdf_url"),
            "parsed_transactions": len(r.get("transactions") or []),
        }
        for r in rows[:5]
    ]


def _financial_series(series_state, sym, limit=40):
    row = (series_state.get("tickers") or {}).get(sym) or {}
    facts = list(row.get("facts") or [])
    facts.sort(key=lambda f: (f.get("period_end") or "", f.get("metric") or "", f.get("series_id") or ""), reverse=True)
    return {
        "coverage": row.get("coverage") or {},
        "conflicts": (row.get("conflicts") or [])[:12],
        "facts": [
            {
                "series_id": fact.get("series_id"),
                "metric": fact.get("metric"),
                "period_end": fact.get("period_end"),
                "period_type": fact.get("period_type"),
                "consolidation": fact.get("consolidation"),
                "currency": fact.get("currency"),
                "unit": fact.get("unit"),
                "unit_multiplier": fact.get("unit_multiplier"),
                "raw_value": fact.get("raw_value"),
                "normalized_value": fact.get("normalized_value"),
                "document_id": fact.get("document_id"),
                "fact_id": fact.get("fact_id"),
                "source_url": _url(fact.get("source_url")),
                "evidence": (fact.get("evidence") or [])[:1],
                "quality_flags": fact.get("quality_flags") or [],
                "readiness": fact.get("readiness") or "audit_only",
            }
            for fact in facts[:limit]
            if isinstance(fact, dict)
        ],
    }


def _company_graph(graph_state, sym):
    row = (graph_state.get("companies") or {}).get(sym) or {}
    nodes_by_id = {node.get("id"): node for node in (graph_state.get("nodes") or []) if node.get("id")}
    allowed = set()
    if row.get("node_id"):
        allowed.add(row["node_id"])
    allowed.update(f"document:{doc_id}" for doc_id in (row.get("document_ids") or []))
    allowed.update(row.get("period_ids") or [])
    allowed.update(row.get("fact_ids") or [])
    allowed.update(f"event:{event_id}" for event_id in (row.get("event_ids") or []))
    allowed.update(f"change:{change_id}" for change_id in (row.get("change_ids") or []))
    allowed.update(f"source:{source_id}" for source_id in (row.get("source_ids") or []))
    caps = {"company": 1, "document": 12, "event": 12, "fact": 16,
            "period": 8, "source": 12, "change": 8}
    selected = []
    counts = {}
    type_order = {"company": 0, "document": 1, "event": 2, "fact": 3,
                  "period": 4, "source": 5, "change": 6}
    for node_id in sorted(allowed, key=lambda value: (
            type_order.get(nodes_by_id.get(value, {}).get("type"), 9),
            -(int(str(nodes_by_id.get(value, {}).get("published_at") or "0")[:4])
              if str(nodes_by_id.get(value, {}).get("published_at") or "")[:4].isdigit() else 0),
            value)):
        node = nodes_by_id.get(node_id)
        if not node:
            continue
        kind = node.get("type") or "other"
        if counts.get(kind, 0) >= caps.get(kind, 4):
            continue
        counts[kind] = counts.get(kind, 0) + 1
        selected.append(node)
    selected_ids = {node.get("id") for node in selected}
    edges = [
        edge for edge in (graph_state.get("edges") or [])
        if edge.get("from") in selected_ids and edge.get("to") in selected_ids
    ]
    return {
        "summary": row.get("counts") or {},
        "nodes": selected,
        "edges": edges[:120],
    }


def _change_intelligence(change_state, sym):
    row = (change_state.get("companies") or {}).get(sym) or {}
    items = []
    for item in (row.get("items") or [])[:18]:
        if not isinstance(item, dict):
            continue
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        source_url = _url(item.get("source_url") or evidence.get("source_url"))
        if not source_url:
            continue
        items.append({
            "id": item.get("id"),
            "kind": item.get("kind"),
            "severity": item.get("severity"),
            "date": item.get("date"),
            "title": item.get("title"),
            "summary": item.get("summary"),
            "document_id": item.get("document_id"),
            "source_url": source_url,
            "source_page": _url(item.get("source_page")),
            "evidence": {
                "source_url": source_url,
                "page": evidence.get("page"),
                "text": evidence.get("text"),
            },
            "metric": item.get("metric"),
            "delta": item.get("delta"),
            "delta_pct": item.get("delta_pct"),
            "period_end": item.get("period_end"),
            "previous_period_end": item.get("previous_period_end"),
            "consolidation": item.get("consolidation"),
            "priority_weight": item.get("priority_weight"),
        })
    return {
        "status": row.get("status") or "quiet",
        "latest_change_at": row.get("latest_change_at"),
        "counts": row.get("counts") or {},
        "items": items,
    }


def _source_quality(source_qa, sym):
    row = (source_qa.get("tickers") or {}).get(sym) or {}
    return {
        "status": row.get("registry_status") or "unknown",
        "monitored_page_count": row.get("monitored_page_count") or 0,
        "document_link_count": row.get("document_link_count") or 0,
        "quality_flags": row.get("quality_flags") or [],
        "missing_required_source": bool(row.get("missing_required_source")),
    }


def _formal_engine_product(engine_state, sym, kind):
    row = (engine_state.get("companies") or {}).get(sym)
    if isinstance(row, dict):
        return dict(row)
    return {
        "symbol": sym,
        "status": "blocked",
        "reason": f"{kind}_state_missing",
        "missing_requirements": [f"{kind}_state_missing"],
        "formula_id": engine_state.get("formula_id"),
        "result": None,
        "provenance": [],
        "policy": engine_state.get("policy") or {"research_only": True, "no_advice": True},
    }


def _formal_engine_meta(engine_state):
    return {
        "schema_version": engine_state.get("schema_version"),
        "engine_version": engine_state.get("engine_version"),
        "kind": engine_state.get("kind"),
        "as_of": engine_state.get("as_of"),
        "formula_id": engine_state.get("formula_id"),
        "source": engine_state.get("source") or {},
        "policy": engine_state.get("policy") or {},
        "summary": engine_state.get("summary") or {},
    }


def _empty_cement_operating_series(sym, sector):
    return {
        "symbol": sym,
        "status": "unknown",
        "activation_status": "not_applicable",
        "observation_count": 0,
        "annual_period_count": 0,
        "metrics": {},
        "downstream_status": {
            "financial_model_inputs": "not_activated",
            "forecast": "not_activated",
            "valuation": "not_activated",
            "market_expectations": "not_activated",
        },
        "quality_flags": [
            "not_in_cement_operating_series_scope" if str(sector or "").upper() != "CEMENT" else "cement_operating_series_state_missing",
        ],
    }


def _cement_operating_series(cement_state, sym, sector):
    row = (cement_state.get("companies") or {}).get(sym)
    return dict(row) if isinstance(row, dict) else _empty_cement_operating_series(sym, sector)


def _cement_historical_reconciliation(state, sym, sector):
    row = (state.get("companies") or {}).get(sym)
    if isinstance(row, dict):
        return dict(row)
    return {
        "symbol": sym,
        "status": "not_in_cement_reconciliation_scope" if str(sector or "").upper() != "CEMENT" else "state_missing",
        "reconciliation_kind": "historical_actuals_only",
        "qualified_financial_period_count": 0,
        "qualified_financial_periods": [],
        "driver_lanes": {},
        "missing_driver_lanes": [],
        "audit_operating_observation_count": 0,
        "adapter_status": "unavailable",
        "downstream_status": {"financial_model_inputs": "not_activated", "forecast": "not_activated", "valuation": "not_activated", "market_expectations": "not_activated"},
    }


def _company_brief(brief_state, document_state, sym):
    row = (brief_state.get("companies") or {}).get(sym) or {}
    current = row.get("current") or None
    if not current:
        return {"current": None, "history_count": len(row.get("history") or [])}
    documents = document_state.get("documents") or {}
    sections = {}
    for key, items in (current.get("sections") or {}).items():
        sections[key] = [
            {
                "text": item.get("text"),
                "evidence": [
                    {
                        "doc_id": ref.get("doc_id"), "page": ref.get("page"),
                        "source_url": _url((documents.get(ref.get("doc_id")) or {}).get("source_url")),
                    }
                    for ref in item.get("evidence") or [] if isinstance(ref, dict)
                ],
            }
            for item in items if isinstance(item, dict)
        ]
    return {
        "current": {
            "brief_id": current.get("brief_id"),
            "headline": current.get("headline"),
            "approved_at": current.get("approved_at"),
            "based_on": current.get("based_on") or [],
            "sections": sections,
            "limitations": current.get("limitations") or [],
        },
        "history_count": len(row.get("history") or []),
    }


def build(write: bool = True):
    universe = load_json(STATE / "universe.json", {"symbols": {}}).get("symbols", {})
    quant = load_json(STATE / "quant.json", {"tickers": {}}).get("tickers", {})
    live = load_json(STATE / "live.json", {"tickers": {}}).get("tickers", {})
    profiles_state = load_json(STATE / "company_profiles.json", {"tickers": {}})
    profiles = profiles_state.get("tickers", {})
    fundamentals = load_json(STATE / "fundamentals.json", {"tickers": {}}).get("tickers", {})
    score = load_json(STATE / "fundamental_scores.json", {"tickers": {}}).get("tickers", {})
    fairvalue = load_json(STATE / "fairvalue.json", {"tickers": {}}).get("tickers", {})
    liquidity = load_json(STATE / "liquidity.json", {"tickers": {}}).get("tickers", {})
    sectors = load_json(STATE / "sectors.json", {"tickers": {}}).get("tickers", {})
    news = load_json(STATE / "newslog.json", [])
    research = load_json(STATE / "research_index.json", {})
    company_documents = load_json(STATE / "company_documents.json", {"documents": {}})
    company_events = load_json(STATE / "company_event_ledger.json", {"companies": {}})
    synthesis_queue = load_json(STATE / "document_synthesis_queue.json", {"queue": [], "history": []})
    brief_receipts = load_json(STATE / "company_brief_receipts.json", {"receipts": []})
    source_registry = load_json(STATE / "company_intel" / "source_registry.json", {"tickers": {}})
    source_qa = load_json(STATE / "company_source_qa.json", {"tickers": {}})
    financial_series = load_json(STATE / "company_financial_series.json", {"tickers": {}})
    knowledge_graph = load_json(STATE / "company_intel" / "company_graph.json", {"companies": {}})
    change_intelligence = load_json(STATE / "company_intel" / "change_intelligence.json", {"companies": {}})
    company_briefs = load_json(STATE / "company_briefs.json", {"companies": {}})
    operating_events = load_json(STATE / "company_intel" / "operating_events.json", {"companies": {}})
    cement_operating_series = load_json(STATE / "company_intel" / "cement_operating_series.json", {"companies": {}})
    cement_historical_reconciliation = load_json(STATE / "company_intel" / "cement_historical_reconciliation.json", {"companies": {}})
    driver_graphs = load_json(STATE / "company_intel" / "driver_graphs.json", {"companies": {}})
    impact_scenarios = load_json(STATE / "company_intel" / "impact_scenarios.json", {"companies": {}})
    event_studies = load_json(STATE / "company_intel" / "event_studies.json", {"studies": {}})
    conditional_benchmarks = load_json(STATE / "company_intel" / "conditional_benchmarks.json", {"companies": {}})
    causal_foundations = load_json(STATE / "company_intel" / "causal_foundations.json", {"companies": {}})
    financial_model_inputs = load_json(STATE / "company_intel" / "financial_model_inputs.json", {"companies": {}})
    financial_coverage = load_json(STATE / "company_intel" / "financial_coverage.json", {"companies": {}})
    financial_truth_qualification = load_json(STATE / "company_intel" / "financial_truth_qualification.json", {"companies": {}})
    forecast_readiness = load_json(STATE / "company_intel" / "forecast_readiness.json", {"companies": {}})
    financial_evidence_reconciliation = load_json(STATE / "company_intel" / "financial_evidence_reconciliation.json", {"companies": {}})
    earnings_bridges = load_json(STATE / "company_intel" / "earnings_bridges.json", {"companies": {}})
    signal_clusters = load_json(STATE / "company_intel" / "signal_clusters.json", {"companies": {}})
    thesis_monitoring = load_json(STATE / "company_intel" / "thesis_monitoring.json", {"companies": {}})
    intelligence_confidence = load_json(STATE / "company_intel" / "intelligence_confidence.json", {"companies": {}})
    intelligence_cases = load_json(STATE / "company_intel" / "intelligence_cases.json", {"companies": {}})
    mlcf_pioc_readiness_manifest = load_json(STATE / "company_intel" / "mlcf_pioc_readiness_manifest.json", {"companies": {}})
    management_delivery = load_json(STATE / "company_intel" / "management_delivery.json", {"companies": {}})
    guidance_contradictions = load_json(STATE / "company_intel" / "guidance_contradictions.json", {"companies": {}})
    evidence_watchlist = load_json(STATE / "company_intel" / "evidence_watchlist.json", {"companies": {}})
    monitoring = load_json(STATE / "company_intel" / "monitoring.json", {"companies": {}})
    peer_registry = load_json(STATE / "company_intel" / "peer_registry.json", {"companies": {}})
    scenario_lab = load_json(STATE / "company_intel" / "scenario_lab.json", {"companies": {}})
    company_brains = load_json(STATE / "company_intel" / "company_brains.json", {"companies": {}})
    event_review_windows = load_json(STATE / "company_intel" / "event_review_windows.json", {"companies": {}})
    completion_matrix = load_json(STATE / "company_intel" / "completion_matrix.json", {})
    financial_forecasts = load_json(STATE / "company_intel" / "financial_forecasts.json", {"companies": {}})
    formal_valuations = load_json(STATE / "company_intel" / "formal_valuations.json", {"companies": {}})
    market_expectations = load_json(STATE / "company_intel" / "market_expectations.json", {"companies": {}})
    intelligence_cases = load_json(STATE / "company_intel" / "intelligence_cases.json", {"companies": {}})
    financial_engine_assumptions = load_json(STATE / "company_intel" / "financial_engine_assumptions.json", {"records": []})
    private_thesis_receipt = load_json(STATE / "company_intel" / "private_thesis_storage_receipt.json", {})
    insider = load_json(STATE / "insider_activity.json", {"symbols": {}})
    offmarket = load_json(STATE / "offmarket_activity.json", {"days": {}})
    queue_status = _document_queue_status(synthesis_queue, brief_receipts)
    source_cutoff = _slice_source_cutoff(
        profiles_state,
        financial_model_inputs,
        forecast_readiness,
        financial_engine_assumptions,
        financial_forecasts,
        formal_valuations,
        market_expectations,
    )

    # Keep the private app bounded to the declared CI pilot.  ``profiles`` may
    # retain stale public rows (for example a former pilot constituent), but
    # those rows must not silently expand the 20-company CI surface.
    pilot_symbols = (profiles_state.get("pilot") or {}).get("symbols") or list(profiles)
    symbols = [sym for sym in pilot_symbols if sym in profiles]
    rows = []
    for sym in symbols:
        q = quant.get(sym, {})
        lv = live.get(sym, {})
        f = fundamentals.get(sym, {})
        sc = score.get(sym, {})
        fv = fairvalue.get(sym, {})
        liq = liquidity.get(sym, {})
        sector = (sectors.get(sym) or {}).get("sector") or ""
        profile = profiles.get(sym, {})
        filings = _company_filings(company_documents, queue_status, sym)
        timeline, changes = _company_timeline(company_events, sym)
        sources = _company_sources(source_registry, sym)
        financial = _financial_series(financial_series, sym)
        graph = _company_graph(knowledge_graph, sym)
        change_digest = _change_intelligence(change_intelligence, sym)
        brief = _company_brief(company_briefs, company_documents, sym)
        op_events = (operating_events.get("companies", {}).get(sym) or {}).get("events") or []
        cement_operating_row = _cement_operating_series(cement_operating_series, sym, sector)
        cement_reconciliation_row = _cement_historical_reconciliation(cement_historical_reconciliation, sym, sector)
        dgraph = driver_graphs.get("companies", {}).get(sym) or {"sector": None, "drivers": [], "edges": [], "quality_flags": ["missing_driver_graph"]}
        scenarios = (impact_scenarios.get("companies", {}).get(sym) or {}).get("scenarios") or []
        studies = [v for v in (event_studies.get("studies") or {}).values() if v.get("symbol") == sym]
        conditional_benchmark_row = (conditional_benchmarks.get("companies") or {}).get(sym) or {"symbol": sym, "status": "state_missing", "benchmark_count": 0, "benchmarks": [], "policy": {}, "limitations": ["conditional_benchmarks_state_missing"]}
        causal_foundations_row = causal_foundations.get("companies", {}).get(sym) or {"symbol": sym, "sector": None, "causal_rows": [], "coverage": {"causal_row_count": 0}}
        model_inputs = financial_model_inputs.get("companies", {}).get(sym) or {"status": "unsupported_sector_model", "observations": {}, "derived": {}}
        financial_reconciliation_row = financial_evidence_reconciliation.get("companies", {}).get(sym) or {
            "symbol": sym,
            "status": "blocked",
            "eligible_fact_count": 0,
            "audit_only_fact_count": 0,
            "quarantined_fact_count": 0,
            "missing_slot_count": 0,
            "source_conflict_count": 0,
            "facts": [],
            "conflicts": [],
            "missing_slots": [],
            "qualified_periods": [],
            "readiness": {
                "forecast_readiness_status": "blocked",
                "forecast_qualified_period_count": 0,
                "financial_model_input_status": "unknown",
                "earnings_bridge_status": "blocked",
                "forecast": "blocked_insufficient_qualified_history",
                "valuation": "blocked_insufficient_qualified_history",
                "market_expectations": "blocked_insufficient_qualified_history",
                "reason": "financial_evidence_reconciliation_state_missing",
            },
        }
        earnings_bridge_row = (earnings_bridges.get("companies") or {}).get(sym) or {"symbol": sym, "status": "state_missing", "bridge_count": 0, "bridges": [], "formal_engine_status": {"forecast": "not_activated", "valuation": "not_activated", "market_expectations": "not_activated"}}
        financial_coverage_row = financial_coverage.get("companies", {}).get(sym) or {
            "symbol": sym,
            "status": "blocked_no_candidate_documents",
            "classification": "financial_results_coverage",
            "indexed_official_financial_doc_count": 0,
            "indexed_official_financial_docs": [],
            "required_annual_periods": [],
            "missing_revenue_pat_eps_by_annual_period": [],
            "qualification_queue": {
                "status": "blocked_no_candidate_documents",
                "candidate_documents": [],
            },
        }
        financial_truth_row = financial_truth_qualification.get("companies", {}).get(sym) or {
            "symbol": sym,
            "status": "not_generated",
            "downstream": {
                "forecast": "blocked_financial_truth_not_qualified",
                "valuation": "blocked_financial_truth_not_qualified",
                "market_expectations": "blocked_financial_truth_not_qualified",
            },
        }
        forecast_readiness_row = forecast_readiness.get("companies", {}).get(sym) or {
            "symbol": sym,
            "status": "blocked",
            "qualified_period_count": 0,
            "qualified_periods": [],
            "missing_requirements": ["forecast_readiness_state_missing"],
            "blocked_outputs": {
                "forecast": "blocked_insufficient_qualified_history",
                "valuation": "blocked_insufficient_qualified_history",
                "market_expectations": "blocked_insufficient_qualified_history",
            },
        }
        signal_cluster_row = signal_clusters.get("companies", {}).get(sym) or {"candidate_count": 0, "eligible_count": 0, "clusterable_count": 0, "rejection_reasons": {}, "clusters": []}
        thesis_row = (thesis_monitoring.get("companies") or {}).get(sym)
        confidence_row = (intelligence_confidence.get("companies") or {}).get(sym)
        intelligence_case_row = (intelligence_cases.get("companies") or {}).get(sym) or {
            "symbol": sym,
            "status": "no_observed_case",
            "case_count": 0,
            "cases": [],
            "rejection_reasons": ["intelligence_cases_state_missing"],
        }
        mlcf_pioc_readiness_row = (mlcf_pioc_readiness_manifest.get("companies") or {}).get(sym) or {
            "symbol": sym,
            "status": "not_selected",
            "manifest": None,
            "blockers": ["mlcf_pioc_readiness_manifest_state_missing"],
        }
        management_delivery_row = (management_delivery.get("companies") or {}).get(sym)
        guidance_contradictions_row = (guidance_contradictions.get("companies") or {}).get(sym)
        evidence_watchlist_row = (evidence_watchlist.get("companies") or {}).get(sym)
        monitoring_row = (monitoring.get("companies") or {}).get(sym)
        peer_registry_row = (peer_registry.get("companies") or {}).get(sym) or {
            "symbol": sym,
            "registry_status": "blocked_no_formal_peer_registry",
            "peer_set_kind": "pilot_sector_cohort",
            "method": peer_registry.get("method"),
            "sector": (sectors.get(sym) or {}).get("sector"),
            "sector_code": (sectors.get(sym) or {}).get("code"),
            "members": [],
            "formal_peers": [],
            "international_peers": {
                "status": "unavailable",
                "reason": "no_authoritative_international_peer_registry",
                "members": [],
            },
            "limitations": ["peer_registry_state_missing"],
        }
        scenario_lab_row = scenario_lab.get("companies", {}).get(sym) or {
            "symbol": sym,
            "status": {
                "scenario_lab": "blocked_missing_snapshot_inputs",
                "market_expectations": "blocked_missing_snapshot_inputs",
                "valuation": "blocked_missing_snapshot_inputs",
                "forecast": "blocked_insufficient_qualified_history",
            },
            "scenario": None,
            "reverse_expectations": None,
            "ebitda": None,
            "fcf": None,
            "dcf": None,
        }
        company_brain = company_brains.get("companies", {}).get(sym) or {
            "identity": {"symbol": sym}, "domains": {}, "intelligence_objects": [],
            "timeline": [], "coverage": {"object_count": 0},
        }
        event_review = event_review_windows.get("companies", {}).get(sym) or {
            "symbol": sym, "as_of": None, "known_events": [],
            "expected_reporting_window": {"status": "unknown", "reason": "event_review_windows_state_missing", "historical_dates": []},
            "review_windows": [],
        }
        financial_forecast_row = _formal_engine_product(financial_forecasts, sym, "financial_forecasts")
        formal_valuation_row = _formal_engine_product(formal_valuations, sym, "formal_valuations")
        market_expectation_row = _formal_engine_product(market_expectations, sym, "market_expectations")
        candidate_case_row = (intelligence_cases.get("companies") or {}).get(sym)
        intelligence_case_row = candidate_case_row if isinstance(candidate_case_row, dict) and candidate_case_row.get("symbol") == sym else {
            "symbol": sym,
            "status": "intelligence_cases_state_missing",
            "case_count": 0,
            "cases": [],
            "rejection_reasons": ["intelligence_cases_state_missing"],
        }
        historical_reference_cases = _historical_reference_cases(financial_engine_assumptions, sym, source_cutoff)
        assumption_gap_review = _assumption_gap_review(financial_engine_assumptions, sym)
        rows.append({
            "symbol": sym,
            "name": (universe.get(sym) or {}).get("name") or f.get("name") or "",
            "sector": sector,
            "indices": (universe.get(sym) or {}).get("in", []),
            "price": {
                "current": lv.get("current") or q.get("close"),
                "date": q.get("date"),
                "ret_1d": q.get("ret_1d"),
                "ret_20d": q.get("ret_20d"),
            },
            "profile": {
                "business_description": profile.get("business_description"),
                "incorporation": profile.get("incorporation"),
                "source_url": profile.get("source_url"),
                "fetched": profile.get("fetched"),
                "stale": bool(profile.get("stale")),
            },
            "fundamentals": {
                "market_cap": f.get("market_cap"),
                "eps": f.get("eps"),
                "pe": f.get("pe"),
                "forward_pe": f.get("forward_pe"),
                "div_yield": f.get("div_yield"),
                "payout_ratio": f.get("payout_ratio"),
                "beta": f.get("beta"),
                "rating": sc.get("rating"),
                "overall": sc.get("overall"),
            },
            "valuation": {
                "verdict": fv.get("verdict"),
                "composite_fair": fv.get("composite_fair"),
                "mispricing_pct": fv.get("mispricing_pct"),
            },
            "liquidity": {
                "research_eligible": bool(liq.get("research_eligible")),
                "signal_eligible": bool(liq.get("signal_eligible")),
                "adtv_pkr": liq.get("adtv_pkr"),
                "adtv_m": _round((liq.get("adtv_pkr") or 0) / 1_000_000, 1),
            },
            "documents": _research_docs(research, sym),
            "filings": filings,
            "financial_series": financial,
            "timeline": timeline,
            "changes": changes,
            "graph": graph,
            "change_intelligence": change_digest,
            "sources": sources,
            "source_quality": _source_quality(source_qa, sym),
            "brief": brief,
            "operating_events": op_events,
            "cement_operating_series": cement_operating_row,
            "cement_historical_reconciliation": cement_reconciliation_row,
            "driver_graph": dgraph,
            "impact_scenarios": scenarios,
            "event_studies": studies,
            "conditional_benchmarks": conditional_benchmark_row,
            "causal_foundations": causal_foundations_row,
            "financial_model_inputs": model_inputs,
            "financial_evidence_reconciliation": financial_reconciliation_row,
            "earnings_bridges": earnings_bridge_row,
            "financial_coverage": financial_coverage_row,
            "financial_truth_qualification": financial_truth_row,
            "forecast_readiness": forecast_readiness_row,
            "signal_clusters": signal_cluster_row,
            "thesis_monitoring": thesis_row,
            "intelligence_confidence": confidence_row,
            "intelligence_cases": intelligence_case_row,
            "mlcf_pioc_readiness_manifest": mlcf_pioc_readiness_row,
            "management_delivery": management_delivery_row,
            "guidance_contradictions": guidance_contradictions_row,
            "evidence_watchlist": evidence_watchlist_row,
            "monitoring": monitoring_row,
            "peer_registry": peer_registry_row,
            "scenario_lab": scenario_lab_row,
            "company_brain": company_brain,
            "event_review_windows": event_review,
            "financial_forecasts": financial_forecast_row,
            "formal_valuations": formal_valuation_row,
            "market_expectations": market_expectation_row,
            "intelligence_cases": intelligence_case_row,
            "historical_reference_cases": historical_reference_cases,
            "financial_engine_assumption_gaps": assumption_gap_review,
            "intelligence": {
                "document_count": len(filings),
                "event_count": len(timeline),
                "change_count": len(changes),
                "financial_fact_count": len(financial.get("facts") or []),
                "graph_node_count": len(graph.get("nodes") or []),
                "graph_edge_count": len(graph.get("edges") or []),
                "change_item_count": len(change_digest.get("items") or []),
                "brief_status": "approved" if brief.get("current") else "training_only",
                "pending_synthesis": sum(
                    1 for filing in filings
                    if (filing.get("synthesis") or {}).get("approval_status") == "pending"
                ),
                "last_event_at": timeline[0].get("date") if timeline else None,
                "source_status": sources.get("status"),
                "source_quality_flags": len((_source_quality(source_qa, sym).get("quality_flags") or [])),
                "operating_event_count": len(op_events),
                "cement_operating_observation_count": cement_operating_row.get("observation_count", 0),
                "cement_qualified_financial_period_count": cement_reconciliation_row.get("qualified_financial_period_count", 0),
                "impact_scenario_count": len(scenarios),
                "event_study_count": len(studies),
                "conditional_benchmark_count": conditional_benchmark_row.get("benchmark_count", 0),
                "causal_row_count": (causal_foundations_row.get("coverage") or {}).get("causal_row_count", 0),
                "financial_model_status": model_inputs.get("status"),
                "financial_reconciliation_status": financial_reconciliation_row.get("status"),
                "financial_reconciliation_eligible_facts": financial_reconciliation_row.get("eligible_fact_count", 0),
                "financial_reconciliation_missing_slots": financial_reconciliation_row.get("missing_slot_count", 0),
                "financial_reconciliation_conflicts": financial_reconciliation_row.get("source_conflict_count", 0),
                "financial_coverage_status": financial_coverage_row.get("status"),
                "financial_coverage_candidates": len(((financial_coverage_row.get("qualification_queue") or {}).get("candidate_documents")) or []),
                "forecast_readiness_status": forecast_readiness_row.get("status"),
                "forecast_qualified_period_count": forecast_readiness_row.get("qualified_period_count"),
                "scenario_lab_status": (scenario_lab_row.get("status") or {}).get("scenario_lab"),
                "market_expectations_status": (scenario_lab_row.get("status") or {}).get("market_expectations"),
                "brain_object_count": (company_brain.get("coverage") or {}).get("object_count", 0),
                "management_delivery_records": (management_delivery_row or {}).get("delivery_record_count", 0),
                "intelligence_case_count": (intelligence_case_row or {}).get("case_count", 0),
                "mlcf_pioc_readiness_manifest_status": (mlcf_pioc_readiness_row or {}).get("status"),
                "guidance_object_count": (guidance_contradictions_row or {}).get("object_count", 0),
                "guidance_contradiction_count": (guidance_contradictions_row or {}).get("contradiction_count", 0),
                "evidence_watchlist_status": (evidence_watchlist_row or {}).get("status"),
                "monitoring_status": (monitoring_row or {}).get("status"),
                "monitoring_alert_count": (monitoring_row or {}).get("alert_count", 0),
                "financial_forecast_status": financial_forecast_row.get("status"),
                "formal_valuation_status": formal_valuation_row.get("status"),
                "formal_market_expectations_status": market_expectation_row.get("status"),
                "historical_reference_case_count": historical_reference_cases.get("case_count", 0),
                "financial_engine_assumption_gap_status": assumption_gap_review.get("status"),
            },
            "news": _latest_news(news, sym),
            "insider_filings": _insider(insider, sym),
            "offmarket": _offmarket(offmarket, sym),
        })

    payload = {
        "meta": {
            "built": time.strftime("%Y-%m-%d %H:%M"),
            "source": "Henneth state layer",
            "profile_source": profiles_state.get("source"),
            "profile_updated": profiles_state.get("updated"),
            "count": len(rows),
            "financial_series": financial_series.get("_meta", {}),
            "graph": knowledge_graph.get("_meta", {}),
            "change_intelligence": change_intelligence.get("_meta", {}),
            "completion_matrix": _completion_matrix_summary(completion_matrix),
            "financial_forecasts": _formal_engine_meta(financial_forecasts),
            "formal_valuations": _formal_engine_meta(formal_valuations),
            "market_expectations": _formal_engine_meta(market_expectations),
            "historical_reference_cases": _reference_case_meta(financial_engine_assumptions, source_cutoff, rows),
            "event_review_windows": event_review_windows.get("meta") or {"count": len(rows), "status": "unknown"},
            "financial_engine_assumption_gaps": _assumption_gap_meta(financial_engine_assumptions),
            "private_thesis_storage": _private_thesis_storage_meta(private_thesis_receipt),
            "note": "Private company-intelligence slice. Research, not advice. No execution or order path.",
        },
        "tickers": rows,
    }
    if write:
        save_json(OUT, payload)
        print(f"ci_slice: {len(rows)} tickers -> {OUT.relative_to(ROOT)}")
    return payload


if __name__ == "__main__":
    build()
