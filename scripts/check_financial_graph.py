#!/usr/bin/env python3
"""Offline guard for period/unit/provenance and no-churn financial transforms."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from build_financial_series import _sanitize_row, build, merge_rows
from build_company_graph import build as build_graph
from financial_series import normalize_fact
from financial_statement_facts import PARSER_REVISION


def _fixture(title: str, page: str, raw: str = "12,345") -> tuple[dict, dict, list[str]]:
    doc = {"doc_id": "psx:check", "tickers": ["ABC"], "title": title,
           "source_url": "https://dps.psx.com.pk/download/document/1.pdf", "status": "ready",
           "content_sha256": "a" * 64, "period": "2025-09-30"}
    fact = {"fact_id": "fact_fixture", "fact_type": "revenue", "line": "revenue",
            "parser_version": "financial_statement_v2", "parser_revision": PARSER_REVISION,
            "readiness": "model_loadable", "period_end": "2025-09-30", "period_type":"quarter",
            "duration_months":3, "column_role":"current_period", "consolidation": "consolidated",
            "currency": "PKR", "statement_type": "income_statement", "available_on": "2025-10-02",
            "published_at": "2025-10-02", "document_id": doc["doc_id"], "source_url": doc["source_url"],
            "content_sha256": doc["content_sha256"], "raw_value": raw,
            "normalized_value": 12_345_000_000, "value": 12_345_000_000,
            "unit": "PKR", "scale_multiplier": 1,
            "evidence": [{"source_url": doc["source_url"], "page": 1, "text": "Revenue " + raw + " (Rupees in million)"}]}
    fact["unit_multiplier"] = 1_000_000
    fact["scale"] = 1_000_000
    return doc, fact, [page]


def run() -> None:
    doc, fact, pages = _fixture("ABC Quarterly Results for the period ended 30.09.2025",
                                "CONDENSED CONSOLIDATED STATEMENT (Rupees in million) Revenue 12,345")
    row = normalize_fact(doc, fact, pages=pages)
    assert row and row["period_end"] == "2025-09-30", row
    assert row["period_type"] == "quarter", row
    assert row["consolidation"] == "consolidated", row
    assert row["currency"] == "PKR" and row["unit_multiplier"] == 1_000_000, row
    assert row["normalized_value"] == 12_345_000_000, row
    assert row["readiness"] == "model_loadable", row
    assert not {"missing_period_end", "missing_currency", "missing_unit_scale", "missing_consolidation_basis"}.intersection(row["quality_flags"]), row
    bounded_doc = {**doc, "doc_id": "psx:bounded-page", "page_count": 200}
    bounded_fact = {**fact, "fact_id": "fact_bounded_page", "document_id": bounded_doc["doc_id"]}
    bounded_fact["evidence"] = [{"source_url": doc["source_url"], "page": 155,
                                  "text": "Revenue 12,345 (Rupees in million)"}]
    bounded = normalize_fact(bounded_doc, bounded_fact, pages=["cover excerpt"])
    assert bounded and "invalid_evidence_page" not in bounded["quality_flags"], bounded
    eps_doc = {**doc, "doc_id": "psx:eps-fixture", "title": "ABC Results"}
    eps_fact = {"fact_id": "fact_eps", "fact_type": "eps", "raw_value": "12.5", "normalized_value": 12.5,
                "unit": "PKR/share", "scale_multiplier": 1,
                "evidence": [{"source_url": doc["source_url"], "page": 1, "text": "EPS Rs 12.5. Revenue Rs 12 bn."}]}
    eps = normalize_fact(eps_doc, eps_fact, pages=["EPS Rs 12.5. Revenue Rs 12 bn."])
    assert eps and eps["unit_multiplier"] == 1 and eps["normalized_value"] == 12.5, eps
    unclaimed_fact = {"fact_id": "fact_div", "fact_type": "dividend", "raw_value": "26",
                      "normalized_value": 26, "unit": "PKR/share", "scale_multiplier": 1_000_000,
                      "evidence": [{"source_url": doc["source_url"], "page": 1,
                                    "text": "Unclaimed dividend 26,721 (Rupees in million)"}]}
    unclaimed = normalize_fact(eps_doc | {"doc_id": "psx:div-fixture"}, unclaimed_fact,
                               pages=["Unclaimed dividend 26,721 (Rupees in million)"])
    assert unclaimed and unclaimed["unit_multiplier"] == 1 and unclaimed["normalized_value"] == 26, unclaimed

    doc2, fact2, pages2 = _fixture("ABC Annual Results for year ended 31.12.2024",
                                  "SEPARATE FINANCIAL STATEMENTS (Rupees in thousand) Revenue 12,345")
    row2 = normalize_fact(doc2 | {"doc_id": "psx:fixture2", "period": "2024-12-31"}, fact2 | {
        "fact_id": "fact_fixture2", "document_id": "psx:fixture2", "period_end":"2024-12-31",
        "period_type":"annual", "consolidation":"unconsolidated", "unit_multiplier":1000,
        "scale": 1000, "normalized_value": 12_345_000, "value": 12_345_000,
    }, pages=pages2)
    assert row2 and row2["period_end"] == "2024-12-31" and row2["consolidation"] == "unconsolidated", row2
    assert row2["unit_multiplier"] == 1_000 and row2["normalized_value"] == 12_345_000, row2

    cash_doc, cash_fact, cash_pages = _fixture(
        "ABC Annual Results for year ended 31.12.2025",
        "CONSOLIDATED STATEMENT OF CASH FLOWS (Rupees in million) Net cash generated from operating activities 12,345",
    )
    cash_fact.update({
        "fact_id": "fact_cash_flow", "fact_type": "operating_cash_flow", "line": "operating_cash_flow",
        "statement_type": "cash_flow_statement", "period_end": "2025-12-31", "period_type": "annual",
        "duration_months": 12, "normalized_value": 12_345_000_000, "value": 12_345_000_000,
        "available_on": "2026-02-02", "published_at": "2026-02-02",
        "evidence": [{"source_url": cash_doc["source_url"], "page": 1,
                      "text": "Net cash generated from operating activities 12,345 (Rupees in million)"}],
    })
    cash = normalize_fact(cash_doc | {"period": "2025-12-31"}, cash_fact, pages=cash_pages)
    assert cash and cash["readiness"] == "model_loadable" and cash["statement_type"] == "cash_flow_statement", cash
    cash_wrong_statement = normalize_fact(cash_doc | {"period": "2025-12-31"},
                                          {**cash_fact, "statement_type": "income_statement"}, pages=cash_pages)
    assert cash_wrong_statement and cash_wrong_statement["readiness"] == "audit_only" and "invalid_structured_statement_type" in cash_wrong_statement["quality_flags"], cash_wrong_statement

    missing_doc, missing_fact, missing_pages = _fixture("ABC Results", "Revenue 12,345")
    missing_fact = {**missing_fact, "period_end": None, "period_type": "unknown", "readiness": "audit_only"}
    missing = normalize_fact(missing_doc, missing_fact, pages=missing_pages)
    assert missing and missing["period_end"] is None and "missing_period_end" in missing["quality_flags"], missing
    misleading_doc, misleading_fact, _ = _fixture("ABC Results", "Revenue 12,345")
    misleading_fact = {**misleading_fact, "period_end": None, "period_type": "unknown", "readiness": "audit_only"}
    misleading_fact["evidence"][0]["page"] = 1
    misleading = normalize_fact(misleading_doc, misleading_fact,
                                 pages=["Revenue 12,345", "Financial period ended 31.12.2024"])
    assert misleading and misleading["period_end"] is None, "borrowed a period from a different page"
    bad_page = normalize_fact(missing_doc, missing_fact | {"evidence": [{"source_url": missing_doc["source_url"], "page": 0, "text": "Revenue 12,345"}]}, pages=missing_pages)
    assert bad_page and bad_page["readiness"] == "audit_only" and "invalid_evidence_page" in bad_page["quality_flags"], bad_page
    valid_doc, valid_fact, valid_pages = _fixture("ABC Quarterly Results for the period ended 30.09.2025",
                                                  "CONDENSED CONSOLIDATED STATEMENT (Rupees in million) Revenue 12,345")
    current_v3_cases = [
        ("missing_fact_id", {"fact_id": None}),
        ("document_id_mismatch", {"document_id": "psx:other"}),
        ("missing_content_sha256", {"content_sha256": None}),
        ("content_hash_mismatch", {"content_sha256": "b" * 64}),
        ("missing_source_url", {"source_url": None}),
        ("source_url_mismatch", {"source_url": "https://dps.psx.com.pk/download/document/2.pdf"}),
        ("missing_structured_currency", {"currency": None}),
        ("missing_structured_unit_multiplier", {"unit_multiplier": None}),
        ("missing_structured_scale", {"scale": None}),
        ("structured_scale_mismatch", {"scale": 1000}),
        ("invalid_structured_period_end", {"period_end": "2025/09/30"}),
        ("missing_or_invalid_publication_date", {"available_on": "2025-10-02T09:00:00"}),
        ("available_before_period_end", {"available_on": "2025-09-30"}),
        ("current_period_has_comparative_linkage", {"comparative_to_period_end": "2025-09-30"}),
        ("comparative_linkage_mismatch", {"column_role": "comparative_prior_period",
                                           "period_end": "2024-09-30",
                                           "comparative_to_period_end": "2025-06-30"}),
        ("missing_comparative_linkage", {"column_role": "comparative_prior_period",
                                          "period_end": "2024-09-30",
                                          "comparative_to_period_end": None}),
        ("preexisting_quality_flags_quarantine", {"quality_flags": ["reviewer_fixture_flag"]}),
        ("non_official_source_url", {"source_url": "https://example.com/report.pdf",
                                      "evidence": [{"source_url": "https://example.com/report.pdf", "page": 1, "text": "Revenue 12,345 (Rupees in million)"}]}),
        ("invalid_evidence_page", {"evidence": [{"source_url": valid_doc["source_url"], "page": 0, "text": "Revenue 12,345 (Rupees in million)"}]}),
        ("invalid_structured_consolidation", {"consolidation": "unknown"}),
        ("invalid_structured_statement_type", {"statement_type": "balance_sheet"}),
        ("unsupported_structured_line", {"line": "assets", "fact_type": "assets"}),
        ("line_fact_type_mismatch", {"line": "revenue", "fact_type": "gross_profit"}),
        ("unparseable_raw_value", {"raw_value": "lOO", "normalized_value": 100_000_000, "value": 100_000_000}),
        ("structured_value_mismatch", {"normalized_value": 999, "value": 999}),
        ("structured_value_mismatch", {"normalized_value": 12_345_000_000, "value": 999}),
        ("nonfinite_structured_value", {"normalized_value": float("nan")}),
        ("nonfinite_structured_value", {"value": float("inf")}),
        ("nonfinite_structured_value", {"unit_multiplier": True}),
        ("legacy_parser_revision_quarantine", {"parser_revision": "block_geometry_v2"}),
    ]
    for expected_flag, patch in current_v3_cases:
        candidate = dict(valid_fact)
        candidate["evidence"] = [dict(item) for item in valid_fact["evidence"]]
        candidate.update(patch)
        row_bad = normalize_fact(valid_doc, candidate, pages=valid_pages)
        assert row_bad and row_bad["readiness"] == "audit_only" and expected_flag in row_bad["quality_flags"], (expected_flag, row_bad)

    # Issuer PDFs are eligible only through the retained same-domain source
    # registry link. A direct URL, hash mismatch, or missing page evidence
    # remains audit-only even when the parser emitted a v2 fact.
    issuer_url = "https://issuer.example/investors/annual-2025.pdf"
    issuer_hash = "c" * 64
    issuer_doc = {**valid_doc, "doc_id": "issuer:fixture", "source_url": issuer_url,
                  "content_sha256": issuer_hash, "local_sha256": issuer_hash,
                  "media_type": "application/pdf", "status": "ready", "tickers": ["ABC"]}
    issuer_fact = {**valid_fact, "document_id": "issuer:fixture", "source_url": issuer_url,
                   "content_sha256": issuer_hash,
                   "evidence": [{"source_url": issuer_url, "page": 1,
                                 "text": "Revenue 12,345 (Rupees in million)"}]}
    issuer_registry = {"tickers": {"ABC": {
        "root_domain": "issuer.example", "issuer_url": "https://issuer.example/",
        "document_links": [{"id": "issuer:fixture", "url": issuer_url,
                            "source_page": "https://issuer.example/investors/",
                            "status": "discovered"}],
    }}}
    issuer_row = normalize_fact(issuer_doc, issuer_fact, pages=valid_pages,
                                source_registry=issuer_registry)
    assert issuer_row and issuer_row["readiness"] == "model_loadable", issuer_row
    assert issuer_row.get("issuer_registry_binding", {}).get("link_id") == "issuer:fixture", issuer_row
    assert normalize_fact(issuer_doc, issuer_fact, pages=valid_pages)["readiness"] == "audit_only"
    for patch in (
        {"source_url": "https://evil.example/annual-2025.pdf"},
        {"content_sha256": "d" * 64},
        {"evidence": [{"source_url": issuer_url, "page": 0, "text": "Revenue"}]},
    ):
        candidate = dict(issuer_fact)
        candidate["evidence"] = [dict(item) for item in issuer_fact["evidence"]]
        candidate.update(patch)
        bad = normalize_fact(issuer_doc, candidate, pages=valid_pages,
                             source_registry=issuer_registry)
        assert bad and bad["readiness"] == "audit_only", (patch, bad)
    repaired = _sanitize_row({"unit": "PKR/share", "unit_multiplier": 1_000_000,
                              "raw_value": "12.5", "normalized_value": 12_500_000,
                              "metric": "eps", "quality_flags": ["missing_period_end"]})
    assert repaired["unit_multiplier"] == 1 and repaired["normalized_value"] == 12.5
    assert repaired["readiness"] == "audit_only"
    repaired_ocf = _sanitize_row({
        "parser_version": "financial_statement_v2", "parser_revision": PARSER_REVISION,
        "metric": "operating_cash_flow", "line": "operating_cash_flow",
        "statement_type": "cash_flow_statement", "quality_flags": [
            "invalid_structured_statement_type", "unsupported_structured_line",
        ],
    })
    assert repaired_ocf["quality_flags"] == [] and repaired_ocf["readiness"] == "model_loadable", repaired_ocf

    with tempfile.TemporaryDirectory(prefix="henneth-financial-check-") as temp:
        root = Path(temp)
        input_path = root / "company_documents.json"
        output_path = root / "company_financial_series.json"
        input_path.write_text(json.dumps({"documents": {"psx:fixture": {**doc, "facts": [fact]}}}), encoding="utf-8")
        first = build(input_path, output_path)
        bytes_first = output_path.read_bytes()
        second = build(input_path, output_path)
        assert first["tickers"]["ABC"]["facts"], first
        assert output_path.read_bytes() == bytes_first, "no-op build rewrote durable series"
        merge_rows([row], output_path)
        merged = json.loads(output_path.read_text(encoding="utf-8"))
        assert len(merged["tickers"]["ABC"]["facts"]) == 1, "merge duplicated a stable row"
        poorer = dict(row)
        poorer["period_end"] = None
        poorer["period_type"] = "unknown"
        poorer["consolidation"] = "unknown"
        merge_rows([poorer], output_path)
        merged = json.loads(output_path.read_text(encoding="utf-8"))
        assert merged["tickers"]["ABC"]["facts"][0]["period_end"] == row["period_end"], "poorer rebuild replaced richer row"
        sources_path = root / "company_source_qa.json"
        graph_path = root / "company_graph.json"
        source_url = doc["source_url"]
        docs_payload = {"documents": {doc["doc_id"]: {**doc, "events": [{"event_id": "evt_fixture", "event_type": "earnings", "event_date": "2025-10-01", "evidence": [{"source_url": source_url, "page": 1, "text": "Results"}]}], "facts": [fact]}}}
        input_path.write_text(json.dumps(docs_payload), encoding="utf-8")
        sources_path.write_text(json.dumps({"tickers": {}, "sources": {}}), encoding="utf-8")
        graph = build_graph(input_path, output_path, sources_path, graph_path)
        factual = {"SUPPORTS_FACT", "REPORTS_PERIOD", "HAS_EVENT", "EVIDENCED_BY", "REVISION_OF"}
        assert all(e.get("evidence", {}).get("source_url") for e in graph["edges"] if e.get("type") in factual), graph
        graph_bytes = graph_path.read_bytes()
        build_graph(input_path, output_path, sources_path, graph_path)
        assert graph_path.read_bytes() == graph_bytes, "no-op graph rewrote durable state"
    print("financial graph self-check: ok")


if __name__ == "__main__":
    try:
        run()
    except (AssertionError, KeyError, TypeError) as exc:
        print(f"financial graph self-check: FAIL: {exc}")
        sys.exit(1)
