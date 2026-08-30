"""Build a read-only MARI E&P evidence-readiness manifest from retained state.

This builder never fetches or parses documents and never promotes audit-only
facts. It records the distinction between hash/page-bound excerpts,
metadata-only document leads and unavailable inputs. The output is a
readiness audit only: no forecast, valuation, expectations or E&P cash-flow
kernel is activated.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "mari_enp_evidence_readiness_v1"
SYMBOL = "MARI"
EVENT_ID = "evt_3d1dae7553f73da60ba3"
EVENT_DOCUMENT_ID = "psx:265594"

ANNUAL_PERIODS = [
    "2026-06-30",
    "2025-06-30",
    "2024-06-30",
    "2023-06-30",
    "2022-06-30",
]
QUARTER_PERIODS = [
    "2024-09-30",
    "2024-12-31",
    "2025-03-31",
    "2025-06-30",
    "2025-09-30",
    "2025-12-31",
    "2026-03-31",
    "2026-06-30",
]
REQUIRED_FINANCIAL_METRICS = ("revenue", "profit_after_tax_attributable", "basic_eps")
EP_OPERANDS = (
    "working_interest_pct",
    "operator_status",
    "consideration_pkr",
    "block_identity",
    "exploration_timing",
    "development_timing",
    "production_boe",
    "reserves",
    "opex_usd_boe",
    "royalty_pct",
    "effective_tax_pct",
    "oil_price_usd_bbl",
    "gas_price_usd_mmbtu",
    "gas_mmbtu_per_boe",
    "fx_pkr_usd",
)


def _load(root: Path, relative: str) -> Any:
    with (root / relative).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _event_evidence(operating_events: Mapping[str, Any]) -> list[dict[str, Any]]:
    events = (
        (operating_events.get("companies") or {}).get(SYMBOL)
        or operating_events.get(SYMBOL)
        or {}
    ).get("events") or []
    # The readiness manifest is for the offshore target only.  Prior-event
    # material (including the Peshawar acquisition) belongs to the analogue
    # product and must never be promoted into this target event's evidence.
    selected = [event for event in events if event.get("event_id") == EVENT_ID]
    rows: list[dict[str, Any]] = []
    for event in selected:
        for evidence in event.get("evidence") or []:
            # Bind the retained excerpt to both canonical identities.  A
            # malformed target event carrying another document is not target
            # evidence and is therefore omitted rather than relabelled.
            if evidence.get("document_id") != EVENT_DOCUMENT_ID:
                continue
            rows.append(
                {
                    "event_id": event.get("event_id"),
                    "event_subtype": event.get("event_subtype"),
                    "document_id": evidence.get("document_id"),
                    "source_url": evidence.get("source_url"),
                    "page": evidence.get("page"),
                    "content_sha256": evidence.get("content_sha256"),
                    "evidence_sha256": evidence.get("evidence_sha256"),
                    "text": evidence.get("text"),
                    "evidence_class": (
                        "exact_hash_page_backed"
                        if evidence.get("document_id")
                        and evidence.get("page") is not None
                        and evidence.get("content_sha256")
                        else "metadata_lead"
                    ),
                }
            )
    return sorted(rows, key=lambda row: (str(row.get("document_id")), int(row.get("page") or 0)))


def _annual_rows(reconciliation: Mapping[str, Any], coverage: Mapping[str, Any]) -> list[dict[str, Any]]:
    facts = ((reconciliation.get("companies") or {}).get(SYMBOL) or {}).get("facts") or []
    docs = (
        ((coverage.get("companies") or {}).get(SYMBOL) or coverage.get(SYMBOL) or {})
        .get("indexed_official_financial_docs")
        or []
    )
    rows: list[dict[str, Any]] = []
    for slot, period_end in enumerate(ANNUAL_PERIODS, start=1):
        period_facts = [
            fact
            for fact in facts
            if fact.get("period_end") == period_end and fact.get("period_type") == "annual"
        ]
        fact_rows = []
        for fact in period_facts:
            source = fact.get("source") or {}
            fact_rows.append(
                {
                    "metric": fact.get("metric"),
                    "value": fact.get("normalized_value"),
                    "unit": fact.get("unit"),
                    "status": fact.get("status"),
                    "document_id": source.get("document_id"),
                    "page": source.get("page"),
                    "content_sha256": source.get("content_sha256"),
                    "source_url": source.get("source_url"),
                    "fact_id": source.get("fact_id") or fact.get("evidence_id"),
                    "evidence_class": (
                        "exact_hash_page_backed"
                        if source.get("document_id")
                        and source.get("page") is not None
                        and source.get("content_sha256")
                        else "metadata_lead"
                    ),
                }
            )
        period_docs = [
            {
                "document_id": document.get("document_id"),
                "title": document.get("title"),
                "source_url": document.get("source_url"),
                "published_at": document.get("published_at"),
                "content_sha256": document.get("content_sha256"),
                "safe_period": document.get("safe_period"),
                "evidence_class": "metadata_lead",
            }
            for document in docs
            if (document.get("safe_period") or {}).get("period_end") == period_end
        ]
        model_ready_metrics = sorted(
            {
                fact.get("metric")
                for fact in period_facts
                if fact.get("status") == "eligible"
                and fact.get("metric") in REQUIRED_FINANCIAL_METRICS
            }
        )
        hash_page_facts = sum(
            fact.get("evidence_class") == "exact_hash_page_backed" for fact in fact_rows
        )
        if model_ready_metrics == list(REQUIRED_FINANCIAL_METRICS):
            status = "model_ready"
            reason = "all required annual metrics are eligible"
        elif fact_rows:
            status = "audit_only_or_quarantined"
            reason = "retained facts have page/hash evidence but are not model-eligible"
        elif period_docs:
            status = "metadata_lead"
            reason = "official document is indexed by title/date, but PDF values were not parsed"
        else:
            status = "unavailable"
            reason = "no retained annual-period evidence"
        rows.append(
            {
                "slot": f"annual_period_{slot}",
                "period_end": period_end,
                "required_metrics": list(REQUIRED_FINANCIAL_METRICS),
                "model_ready_metrics": model_ready_metrics,
                "status": status,
                "reason": reason,
                "hash_page_fact_count": hash_page_facts,
                "facts": sorted(fact_rows, key=lambda fact: (str(fact.get("metric")), str(fact.get("fact_id")))),
                "document_leads": sorted(period_docs, key=lambda document: str(document.get("document_id"))),
            }
        )
    return rows


def _quarter_rows(reconciliation: Mapping[str, Any], coverage: Mapping[str, Any]) -> list[dict[str, Any]]:
    facts = ((reconciliation.get("companies") or {}).get(SYMBOL) or {}).get("facts") or []
    docs = (
        ((coverage.get("companies") or {}).get(SYMBOL) or coverage.get(SYMBOL) or {})
        .get("indexed_official_financial_docs")
        or []
    )
    rows: list[dict[str, Any]] = []
    for slot, period_end in enumerate(QUARTER_PERIODS, start=1):
        period_facts = [
            fact
            for fact in facts
            if fact.get("period_end") == period_end
            and fact.get("period_type") in {"interim", "quarterly"}
        ]
        period_docs = [
            {
                "document_id": document.get("document_id"),
                "title": document.get("title"),
                "source_url": document.get("source_url"),
                "published_at": document.get("published_at"),
                "safe_period": document.get("safe_period"),
                "evidence_class": "metadata_lead",
            }
            for document in docs
            if (document.get("safe_period") or {}).get("period_end") == period_end
            and (document.get("safe_period") or {}).get("period_type") in {"interim", "quarterly"}
        ]
        if period_facts:
            status = "audit_only_or_quarantined"
            reason = "retained quarterly facts are not model-eligible"
        elif period_docs:
            status = "metadata_lead"
            reason = "official interim document is indexed, but quarterly values were not parsed"
        else:
            status = "unavailable"
            reason = "no retained quarterly-period evidence"
        rows.append(
            {
                "slot": f"quarter_period_{slot}",
                "period_end": period_end,
                "required_metrics": list(REQUIRED_FINANCIAL_METRICS),
                "status": status,
                "reason": reason,
                "facts": period_facts,
                "document_leads": sorted(period_docs, key=lambda document: str(document.get("document_id"))),
            }
        )
    return rows


def _share_count(assumptions: Mapping[str, Any]) -> dict[str, Any]:
    records = assumptions.get("records") or []
    match = next(
        (
            record
            for record in records
            if record.get("symbol") == SYMBOL and record.get("metric") == "shares_out"
        ),
        None,
    )
    if not match:
        return {
            "status": "unavailable",
            "reason": "no retained shares_out record",
            "value": None,
            "unit": "shares",
            "source": None,
        }
    source = match.get("source") or {}
    return {
        "status": "metadata_lead",
        "reason": "retained market-operand record has no official filing page/content hash",
        "value": match.get("value"),
        "unit": match.get("unit") or "shares",
        "available_on": match.get("available_on"),
        "approved_scope": match.get("approval_scope"),
        "source": {
            "id": source.get("id"),
            "label": source.get("label"),
            "path": source.get("path"),
            "url": source.get("url"),
            "page": None,
            "content_sha256": None,
            "evidence_class": "metadata_lead",
        },
    }


def _ep_operands(event_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    exact_refs = [
        {
            "document_id": row.get("document_id"),
            "page": row.get("page"),
            "content_sha256": row.get("content_sha256"),
            "source_url": row.get("source_url"),
            "event_id": row.get("event_id"),
        }
        for row in event_evidence
        if row.get("evidence_class") == "exact_hash_page_backed"
    ]
    observed_text_operands = {
        "block_identity": "offshore exploration blocks (event excerpt; block names not retained)",
    }
    items = []
    for operand in EP_OPERANDS:
        if operand in observed_text_operands:
            items.append(
                {
                    "operand": operand,
                    "status": "observed_text_only",
                    "value": observed_text_operands[operand],
                    "reason": "page/hash-backed event excerpt is retained, but no numeric model input is present",
                    "evidence_refs": exact_refs,
                }
            )
        else:
            items.append(
                {
                    "operand": operand,
                    "status": "unavailable",
                    "value": None,
                    "reason": "no retained source-grounded value; do not infer from event metadata",
                    "evidence_refs": [],
                }
            )
    return {
        "status": "blocked_missing_numeric_operands",
        "reason": "event evidence contains qualitative excerpts only; no numeric E&P inputs are retained",
        "items": items,
    }


def build_manifest(root: Path) -> dict[str, Any]:
    operating_events = _load(root, "state/company_intel/operating_events.json")
    reconciliation = _load(root, "state/company_intel/financial_evidence_reconciliation.json")
    coverage = _load(root, "state/company_intel/financial_coverage.json")
    assumptions = _load(root, "state/company_intel/financial_engine_assumptions.json")
    event_evidence = _event_evidence(operating_events)
    annual = _annual_rows(reconciliation, coverage)
    quarterly = _quarter_rows(reconciliation, coverage)
    share_count = _share_count(assumptions)
    ep_operands = _ep_operands(event_evidence)
    exact_event_count = sum(row["evidence_class"] == "exact_hash_page_backed" for row in event_evidence)
    annual_model_ready = sum(row["status"] == "model_ready" for row in annual)
    quarter_model_ready = sum(row["status"] == "model_ready" for row in quarterly)
    return {
        "schema_version": SCHEMA_VERSION,
        "symbol": SYMBOL,
        "event": {
            "event_id": EVENT_ID,
            "document_id": EVENT_DOCUMENT_ID,
            "effective_date": "2025-11-13",
            "status": "observed_only",
            "evidence": event_evidence,
            "exact_hash_page_backed_evidence_count": exact_event_count,
            "numeric_facts_retained": False,
        },
        "financial_history": {
            "annual": {
                "required_count": 5,
                "model_ready_count": annual_model_ready,
                "status": "blocked" if annual_model_ready < 5 else "ready",
                "reason": "five aligned annual revenue/PAT/EPS periods are not model-ready",
                "periods": annual,
            },
            "quarterly": {
                "required_count": 8,
                "model_ready_count": quarter_model_ready,
                "status": "blocked" if quarter_model_ready < 8 else "ready",
                "reason": "eight quarterly revenue/PAT/EPS periods are not retained as model-ready facts",
                "periods": quarterly,
            },
        },
        "share_count": share_count,
        "ep_operands": ep_operands,
        "activation": {
            "status": "blocked",
            "kernel_activated": False,
            "forecast_activated": False,
            "valuation_activated": False,
            "market_expectations_activated": False,
            "reasons": [
                "no_model_ready_E_and_P_operands",
                "annual_history_incomplete_or_audit_only",
                "quarterly_history_not_retained_as_model_ready",
                "share_count_is_metadata_lead_only",
            ],
        },
        "next_evidence_action": {
            "priority": "highest_leverage",
            "status": "needs_owner_approval",
            "action": "Parse PSX:265594 with page-level text and content hashes retained",
            "expected_unlocks": [
                "offshore block identity",
                "working interest and operator status from the target document",
                "consideration terms",
                "exploration/development timing",
            ],
            "why": "The target official event document currently contains only a truncated qualitative excerpt; operator status and working interest remain missing until the target document is parsed.",
        },
        "provenance_policy": {
            "official_event_evidence": "exact_hash_page_backed excerpts are recorded as observed facts only",
            "financial_facts": "audit_only or quarantined facts remain non-modelable",
            "metadata_leads": "document/title and shares_out leads are not promoted to source-grounded operands",
            "unavailable": "missing values are null and must not be inferred",
        },
        "source_state": {
            "operating_events": "state/company_intel/operating_events.json",
            "financial_evidence_reconciliation": "state/company_intel/financial_evidence_reconciliation.json",
            "financial_coverage": "state/company_intel/financial_coverage.json",
            "financial_engine_assumptions": "state/company_intel/financial_engine_assumptions.json",
            "as_of": reconciliation.get("as_of") or assumptions.get("as_of") or operating_events.get("as_of"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "state/company_intel/mari_enp_evidence_readiness.json",
    )
    args = parser.parse_args()
    manifest = build_manifest(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"mari enp evidence readiness: wrote {args.output}")


if __name__ == "__main__":
    main()
