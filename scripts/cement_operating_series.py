"""Audit-only retained cement operating observations.

This module deliberately does not feed forecasts, valuations, or
financial_model_inputs.  It turns a tiny allowlisted set of retained official
issuer/PSX evidence snippets into source-linked observations for review.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any

from psx_data import STATE, load_json, save_json

OUT = STATE / "company_intel" / "cement_operating_series.json"
PRODUCT_VERSION = "cement_operating_series_v1"
SERIES_VERSION = "audit_only_dgkc_seed_v1"
CEMENT_PILOT_SYMBOLS = ("MLCF", "DGKC", "LUCK")


@dataclass(frozen=True)
class ObservationSpec:
    symbol: str
    metric: str
    period_end: str
    value: int | float
    raw_value: str
    unit: str
    document_id: str
    page: int
    anchors: tuple[str, ...]
    source_fact_ids: tuple[str, ...] = ()


DGKC_SPECS: tuple[ObservationSpec, ...] = (
    ObservationSpec("DGKC", "clinker_production", "2013-06-30", 3924090, "3,924,090", "tonnes", "issuer:26f095b5a39a5c2fce8ae3f7", 29, ("FY14 FY13 Clinker production 3,585,103 3,924,090",)),
    ObservationSpec("DGKC", "cement_production", "2013-06-30", 4031801, "4,031,801", "tonnes", "issuer:26f095b5a39a5c2fce8ae3f7", 29, ("Cement production 3,988,512 4,031,801",)),
    ObservationSpec("DGKC", "cement_sales_local", "2013-06-30", 2892266, "2,892,266", "tonnes", "issuer:26f095b5a39a5c2fce8ae3f7", 29, ("Local Sales 2,954,943 2,892,266",), ("fact_d143e8e6542e70ca40f5",)),
    ObservationSpec("DGKC", "cement_sales_export", "2013-06-30", 1126174, "1,126,174", "tonnes", "issuer:26f095b5a39a5c2fce8ae3f7", 29, ("Export Sales 1,021,329 1,126,174",), ("fact_9a8fa67e8d4554d92d7c",)),
    ObservationSpec("DGKC", "cement_sales_total", "2013-06-30", 4018440, "4,018,440", "tonnes", "issuer:26f095b5a39a5c2fce8ae3f7", 29, ("Total Sales 3,976,272 4,018,440",), ("fact_1abc967777d2dbed79a1",)),
    ObservationSpec("DGKC", "clinker_production", "2014-06-30", 3585103, "3,585,103", "tonnes", "issuer:26f095b5a39a5c2fce8ae3f7", 29, ("FY14 FY13 Clinker production 3,585,103 3,924,090",)),
    ObservationSpec("DGKC", "cement_production", "2014-06-30", 3988512, "3,988,512", "tonnes", "issuer:26f095b5a39a5c2fce8ae3f7", 29, ("Cement production 3,988,512 4,031,801",)),
    ObservationSpec("DGKC", "cement_sales_local", "2014-06-30", 2954943, "2,954,943", "tonnes", "issuer:26f095b5a39a5c2fce8ae3f7", 29, ("Local Sales 2,954,943 2,892,266",), ("fact_d143e8e6542e70ca40f5",)),
    ObservationSpec("DGKC", "cement_sales_export", "2014-06-30", 1021329, "1,021,329", "tonnes", "issuer:26f095b5a39a5c2fce8ae3f7", 29, ("Export Sales 1,021,329 1,126,174",), ("fact_9a8fa67e8d4554d92d7c",)),
    ObservationSpec("DGKC", "cement_sales_total", "2014-06-30", 3976272, "3,976,272", "tonnes", "issuer:26f095b5a39a5c2fce8ae3f7", 29, ("Total Sales 3,976,272 4,018,440",), ("fact_1abc967777d2dbed79a1",)),
    ObservationSpec("DGKC", "clinker_production", "2015-06-30", 3507230, "3,507,230", "tonnes", "issuer:773167b57f3bc15094fdf721", 63, ("FY15 FY14 Clinker Production 3,507,230 3,585,103",)),
    ObservationSpec("DGKC", "cement_production", "2015-06-30", 3849672, "3,849,672", "tonnes", "issuer:773167b57f3bc15094fdf721", 63, ("Cement Production 3,849,672 3,988,511",)),
    ObservationSpec("DGKC", "cement_sales_local", "2015-06-30", 3196103, "3,196,103", "tonnes", "issuer:773167b57f3bc15094fdf721", 63, ("Local Sales 3,196,103 2,954,943",), ("fact_2dea404e3e5f24334412",)),
    ObservationSpec("DGKC", "cement_sales_export", "2015-06-30", 661967, "661,967", "tonnes", "issuer:773167b57f3bc15094fdf721", 63, ("Export Sales 661,967 1,021,328",)),
    ObservationSpec("DGKC", "cement_sales_total", "2015-06-30", 3858070, "3,858,070", "tonnes", "issuer:773167b57f3bc15094fdf721", 63, ("Total Sales 3,858,070 3,976,271",), ("fact_1d05dfaec989a013d010",)),
    ObservationSpec("DGKC", "cement_production", "2016-06-30", 4426631, "4,426,631", "tonnes", "issuer:c38ef8e6e11d33c8261e262d", 82, ("Cement 4,426,631 3,849,672",)),
    ObservationSpec("DGKC", "cement_sales_local", "2016-06-30", 3710393, "3,710,393", "tonnes", "issuer:c38ef8e6e11d33c8261e262d", 82, ("Local 3,710,393 3,196,103",), ("fact_70a2642d9e1ea41de549",)),
    ObservationSpec("DGKC", "cement_sales_export", "2016-06-30", 712298, "712,298", "tonnes", "issuer:c38ef8e6e11d33c8261e262d", 82, ("Export 712,298",), ("fact_70a2642d9e1ea41de549",)),
    ObservationSpec("DGKC", "cement_sales_total", "2016-06-30", 4422691, "4,422,691", "tonnes", "issuer:c38ef8e6e11d33c8261e262d", 82, ("Cement sales: 4,422,691 3,858,070",), ("fact_70a2642d9e1ea41de549",)),
    ObservationSpec("DGKC", "cement_sales_local", "2017-06-30", 3895042, "3,895,042", "tonnes", "issuer:6644afdd89fc5384830867e7", 61, ("Local 3,895,042 3,710,393",), ("fact_698119070066e332ee58",)),
    ObservationSpec("DGKC", "cement_sales_total", "2017-06-30", 4478065, "4,478,065", "tonnes", "issuer:6644afdd89fc5384830867e7", 61, ("Cement sales: 4,478,065 4,422,691",), ("fact_698119070066e332ee58",)),
    ObservationSpec("DGKC", "clinker_production", "2019-06-30", 6380898, "6,380,898", "tonnes", "issuer:5943c09923394ef40e90cc78", 74, ("linker 6,841,964 6,380,898",), ("fact_a9e8d8a145154fa49e1f",)),
    ObservationSpec("DGKC", "cement_production", "2019-06-30", 5613650, "5,613,650", "tonnes", "issuer:5943c09923394ef40e90cc78", 74, ("Cement 5,510,426 5,613,650",), ("fact_a9e8d8a145154fa49e1f",)),
    ObservationSpec("DGKC", "cement_sales_local", "2019-06-30", 5327410, "5,327,410", "tonnes", "issuer:5943c09923394ef40e90cc78", 74, ("Local 5,336,680 5,327,410",), ("fact_a9e8d8a145154fa49e1f",)),
    ObservationSpec("DGKC", "cement_sales_export", "2019-06-30", 270232, "270,232", "tonnes", "issuer:5943c09923394ef40e90cc78", 74, ("Export 158,143 270,232",), ("fact_a9e8d8a145154fa49e1f",)),
    ObservationSpec("DGKC", "cement_sales_total", "2019-06-30", 5597642, "5,597,642", "tonnes", "issuer:5943c09923394ef40e90cc78", 74, ("Cement sales: 5,494,823 5,597,642",), ("fact_a9e8d8a145154fa49e1f",)),
    ObservationSpec("DGKC", "clinker_production", "2020-06-30", 6841964, "6,841,964", "tonnes", "issuer:5943c09923394ef40e90cc78", 74, ("linker 6,841,964 6,380,898",), ("fact_a9e8d8a145154fa49e1f",)),
    ObservationSpec("DGKC", "cement_production", "2020-06-30", 5510426, "5,510,426", "tonnes", "issuer:5943c09923394ef40e90cc78", 74, ("Cement 5,510,426 5,613,650",), ("fact_a9e8d8a145154fa49e1f",)),
    ObservationSpec("DGKC", "cement_sales_local", "2020-06-30", 5336680, "5,336,680", "tonnes", "issuer:5943c09923394ef40e90cc78", 74, ("Local 5,336,680 5,327,410",), ("fact_a9e8d8a145154fa49e1f",)),
    ObservationSpec("DGKC", "cement_sales_export", "2020-06-30", 158143, "158,143", "tonnes", "issuer:5943c09923394ef40e90cc78", 74, ("Export 158,143 270,232",), ("fact_a9e8d8a145154fa49e1f",)),
    ObservationSpec("DGKC", "cement_sales_total", "2020-06-30", 5494823, "5,494,823", "tonnes", "issuer:5943c09923394ef40e90cc78", 74, ("Cement sales: 5,494,823 5,597,642",), ("fact_a9e8d8a145154fa49e1f",)),
    # The page is a FY2025/FY2024 comparison table.  The first annual value in
    # each labelled row is FY2025; later values are comparatives and must not
    # be attached to the FY2025 period.
    ObservationSpec("DGKC", "cement_production", "2025-06-30", 3762813, "3,762,813", "tonnes", "psx:260947", 119, ("Cement production 3,762,813",)),
    ObservationSpec("DGKC", "cement_sales_total", "2025-06-30", 3770701, "3,770,701", "tonnes", "psx:260947", 119, ("Total Cement sales 3,770,701",)),
    ObservationSpec("DGKC", "cement_sales_local", "2025-06-30", 3611075, "3,611,075", "tonnes", "psx:260947", 119, ("Local Cement sales 3,611,075",)),
    ObservationSpec("DGKC", "cement_sales_export", "2025-06-30", 159626, "159,626", "tonnes", "psx:260947", 119, ("Export cement sales 159,626",)),
    ObservationSpec("DGKC", "clinker_sales", "2025-06-30", 1070871, "1,070,871", "tonnes", "psx:260947", 119, ("Clinker sales 1,070,871",)),
)


def _stable_id(*parts: object) -> str:
    raw = "|".join(str(p) for p in parts)
    return "cops_" + sha256(raw.encode("utf-8")).hexdigest()[:24]


def _source_links_by_id(source_registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for ticker, row in (source_registry.get("tickers") or {}).items():
        for link in row.get("document_links") or []:
            doc_id = link.get("id")
            if doc_id:
                out[doc_id] = {**link, "symbol": ticker}
    return out


def _fact_ids(doc: dict[str, Any], spec: ObservationSpec) -> list[str]:
    available = {f.get("fact_id") for f in doc.get("facts") or [] if f.get("fact_id")}
    return [fact_id for fact_id in spec.source_fact_ids if fact_id in available]


def _retained_financial_evidence(
    financial_series: dict[str, Any],
    spec: ObservationSpec,
    source_url: str | None,
) -> list[str]:
    candidates: list[str] = []
    if not source_url:
        return candidates
    facts = ((financial_series.get("tickers") or {}).get(spec.symbol) or {}).get("facts") or []
    for fact in facts:
        fact_source_url = fact.get("source_url")
        for evidence in fact.get("evidence") or []:
            if evidence.get("page") != spec.page or not evidence.get("text"):
                continue
            evidence_source_url = evidence.get("source_url")
            if source_url in {fact_source_url, evidence_source_url}:
                candidates.append(str(evidence["text"]))
    return candidates


def _evidence_text(
    doc: dict[str, Any],
    spec: ObservationSpec,
    financial_series: dict[str, Any],
) -> tuple[str, str]:
    doc_candidates: list[str] = []
    for evidence in doc.get("evidence") or []:
        if evidence.get("page") == spec.page and evidence.get("text"):
            doc_candidates.append(str(evidence["text"]))
    for fact in doc.get("facts") or []:
        for evidence in fact.get("evidence") or []:
            if evidence.get("page") == spec.page and evidence.get("text"):
                doc_candidates.append(str(evidence["text"]))
    financial_candidates = _retained_financial_evidence(financial_series, spec, doc.get("source_url"))
    candidates = [
        ("state/company_documents.json", text)
        for text in doc_candidates
    ] + [
        ("state/company_financial_series.json", text)
        for text in financial_candidates
    ]
    for source_state, text in candidates:
        if all(anchor in text for anchor in spec.anchors):
            return text, source_state
    # Some retained issuer excerpts begin mid-row.  The fallback remains exact:
    # the requested raw value and its declared row label must occur together on
    # the pinned document page.  It does not search other pages or documents.
    labels = {
        "clinker_production": "Clinker",
        "cement_production": "Cement",
        "cement_sales_local": "Local",
        "cement_sales_export": "Export",
        "cement_sales_total": "Cement sales",
        "clinker_sales": "Clinker sales",
    }
    label = labels.get(spec.metric)
    for source_state, text in candidates:
        if label and label in text and spec.raw_value in text:
            return text, source_state
    raise ValueError(f"{spec.document_id} page {spec.page} missing retained anchors for {spec.metric} {spec.period_end}")


def _availability(doc: dict[str, Any]) -> dict[str, str | None]:
    """Never pass a discovery/retrieval time off as issuer publication time."""
    published_at = doc.get("published_at")
    return {
        "available_on": published_at,
        "retained_on": doc.get("retrieved_at"),
        "status": "official_publication_date" if published_at else "publication_date_not_retained_audit_only",
    }


def observation_from_spec(
    spec: ObservationSpec,
    documents: dict[str, Any],
    source_links: dict[str, dict[str, Any]],
    financial_series: dict[str, Any],
) -> dict[str, Any]:
    doc = documents.get(spec.document_id)
    if not isinstance(doc, dict):
        raise ValueError(f"missing retained document {spec.document_id}")
    if spec.symbol not in (doc.get("tickers") or []):
        raise ValueError(f"{spec.document_id} is not retained for {spec.symbol}")
    source_link = source_links.get(spec.document_id)
    evidence_text, anchor_source_state = _evidence_text(doc, spec, financial_series)
    fact_ids = _fact_ids(doc, spec)
    # A filing's metadata alone does not prove availability of an excerpt held
    # only in the financial-series seam.  Keep those snippets audit-only until
    # the document evidence owner retains the matching page text directly.
    availability = (
        _availability(doc)
        if anchor_source_state == "state/company_documents.json"
        else {
            "available_on": None,
            "retained_on": doc.get("retrieved_at"),
            "status": "publication_date_not_retained_audit_only",
        }
    )
    return {
        "observation_id": _stable_id(spec.symbol, spec.metric, spec.period_end, spec.raw_value, spec.document_id, spec.page),
        "symbol": spec.symbol,
        "metric": spec.metric,
        "period_end": spec.period_end,
        "period_type": "annual",
        "value": spec.value,
        "raw_value": spec.raw_value,
        "unit": spec.unit,
        "unit_multiplier": 1,
        "readiness": "audit_only",
        "approval_status": "not_owner_approved_forecast_input",
        "model_eligibility": "not_model_loadable",
        "source": {
            "document_id": spec.document_id,
            "source": doc.get("source"),
            "source_url": doc.get("source_url"),
            "source_page": (source_link or {}).get("source_page"),
            "source_registry_status": (source_link or {}).get("status"),
            "page": spec.page,
            "text": evidence_text,
            "anchor_source_state": anchor_source_state,
            "content_sha256": doc.get("content_sha256"),
            "local_sha256": doc.get("local_sha256"),
            "published_at": doc.get("published_at"),
            "retrieved_at": doc.get("retrieved_at"),
            **availability,
            "source_fact_ids": fact_ids,
        },
        "quality_flags": [
            "audit_only_not_forecast_input",
            "retained_official_evidence_seed",
            *([] if fact_ids else ["value_from_retained_evidence_snippet"]),
        ],
    }


def _company_row(symbol: str, observations: list[dict[str, Any]]) -> dict[str, Any]:
    if symbol == "DGKC":
        metrics: dict[str, list[dict[str, Any]]] = {}
        for obs in sorted(observations, key=lambda x: (x["metric"], x["period_end"], x["observation_id"])):
            metrics.setdefault(obs["metric"], []).append(obs)
        periods = sorted({obs["period_end"] for obs in observations})
        return {
            "symbol": symbol,
            "status": "audit_only_series_available",
            "activation_status": "blocked_audit_only_no_model_adapter",
            "observation_count": len(observations),
            "annual_period_count": len(periods),
            "metrics": metrics,
            "downstream_status": {
                "financial_model_inputs": "not_activated",
                "forecast": "not_activated",
                "valuation": "not_activated",
                "market_expectations": "not_activated",
            },
            "lane_assessment": {
                "same_company_reference_case": "possible_audit_only",
                "pilot_peer_operating_lane": "blocked_insufficient_aligned_peer_history",
            },
            "quality_flags": ["audit_only_not_model_loadable"],
        }
    if symbol == "MLCF":
        qualification_requirements = [
            {
                "requirement": "aligned_annual_cement_operating_rows",
                "required_periods": 5,
                "current_periods": 0,
                "required_metrics": [
                    "cement_sales_total",
                    "cement_sales_local",
                    "cement_sales_export",
                    "cement_production",
                    "clinker_production_or_sales",
                ],
                "status": "missing",
                "evidence_needed": (
                    "official MLCF annual pages with source-bound period, unit, "
                    "page-local row labels, and current/comparative column geometry"
                ),
            },
            {
                "requirement": "event_specific_operating_bridge",
                "required_periods": 2,
                "current_periods": 0,
                "required_metrics": [
                    "pre_pioc_mlcf_dispatches",
                    "post_pioc_combined_dispatches",
                    "pio_cement_dispatch_inclusion_basis",
                ],
                "status": "missing",
                "evidence_needed": (
                    "official bridge that separates MLCF standalone dispatches "
                    "from PIOC-acquired dispatches after the February 2026 acquisition"
                ),
            },
        ]
        return {
            "symbol": symbol,
            "status": "insufficient_aligned_annual_operating_history",
            "activation_status": "blocked_insufficient_aligned_annual_operating_history",
            "observation_count": 0,
            "annual_period_count": 0,
            "metrics": {},
            "blocked_reason": (
                "MLCF has partial cement operating context, but no retained source currently "
                "supplies a five-year aligned annual MLCF operating series or a PIOC bridge "
                "that can feed a model without mixing acquisition effects."
            ),
            "qualification_requirements": qualification_requirements,
            "next_evidence_actions": [
                {
                    "action": "find_or_retain_annual_operating_table",
                    "target": "five official MLCF annual periods",
                    "acceptance": (
                        "current-year and comparative columns must bind to the correct period, "
                        "unit, page, source URL, document hash, and row labels"
                    ),
                },
                {
                    "action": "separate_pioc_acquisition_effect",
                    "target": "FY2026 bridge between MLCF standalone and PIOC-included dispatches",
                    "acceptance": (
                        "do not use the post-acquisition combined dispatch figure as an MLCF "
                        "standalone annual operating-history row"
                    ),
                },
            ],
            "retained_evidence_summary": [
                {
                    "document_id": "issuer:0041077dadc52bdcd3baaa54",
                    "source_url": "https://www.kmlg.com/mlcfl/wp-content/uploads/2023/08/MLCF-Road-Show-08-05-2023.pdf",
                    "pages": [15, 19],
                    "status": "partial_context_only",
                    "reason": "retained snippets contain one retention/quantity comment and industry FY22/FY21 dispatch context, not aligned MLCF annual operating rows",
                },
                {
                    "document_id": "psx:275425",
                    "source_url": "https://dps.psx.com.pk/download/document/275425.pdf",
                    "pages": [4, 20],
                    "status": "partial_period_context_only",
                    "reason": "retained 3Q FY26 export-volume comment is interim and post-PIOC acquisition, not aligned annual history",
                },
            ],
            "downstream_status": {
                "financial_model_inputs": "not_activated",
                "forecast": "not_activated",
                "valuation": "not_activated",
                "market_expectations": "not_activated",
            },
            "quality_flags": ["insufficient_aligned_annual_operating_history"],
        }
    return {
        "symbol": symbol,
        "status": "missing_retained_cement_operating_history",
        "activation_status": "blocked_missing_retained_cement_operating_history",
        "observation_count": 0,
        "annual_period_count": 0,
        "metrics": {},
        "downstream_status": {
            "financial_model_inputs": "not_activated",
            "forecast": "not_activated",
            "valuation": "not_activated",
            "market_expectations": "not_activated",
        },
        "quality_flags": ["missing_retained_cement_operating_history"],
    }


def build_state(
    company_documents: dict[str, Any],
    source_registry: dict[str, Any],
    financial_series: dict[str, Any] | None = None,
    specs: tuple[ObservationSpec, ...] = DGKC_SPECS,
    as_of: str | None = None,
) -> dict[str, Any]:
    documents = company_documents.get("documents") or {}
    source_links = _source_links_by_id(source_registry)
    retained_financial_series = financial_series or {}
    observations = [
        observation_from_spec(spec, documents, source_links, retained_financial_series)
        for spec in specs
    ]
    companies = {
        symbol: _company_row(symbol, [obs for obs in observations if obs["symbol"] == symbol])
        for symbol in CEMENT_PILOT_SYMBOLS
    }
    return {
        "schema_version": 1,
        "product_version": PRODUCT_VERSION,
        "series_version": SERIES_VERSION,
        "as_of": as_of or date.today().isoformat(),
        "pilot_symbols": list(CEMENT_PILOT_SYMBOLS),
        "scope": "exact_ci_pilot_cement_cohort",
        "source": {
            "company_documents": "state/company_documents.json",
            "source_registry": "state/company_intel/source_registry.json",
            "retained_financial_series": "state/company_financial_series.json",
        },
        "policy": {
            "audit_only": True,
            "formal_engine_eligibility_unchanged": True,
            "not_financial_model_input": True,
            "not_forecast_input": True,
            "not_valuation_input": True,
            "no_peer_lane_until_all_pilot_cement_names_have_aligned_annual_history": True,
        },
        "companies": companies,
    }


def build() -> dict[str, Any]:
    existing_state = load_json(OUT, {})
    result = build_state(
        load_json(STATE / "company_documents.json", {"documents": {}}),
        load_json(STATE / "company_intel" / "source_registry.json", {"tickers": {}}),
        load_json(STATE / "company_financial_series.json", {"tickers": {}}),
    )
    if isinstance(existing_state, dict) and isinstance(existing_state.get("_meta"), dict):
        result["_meta"] = existing_state["_meta"]
    save_json(OUT, result)
    print(
        "cement_operating_series: "
        f"{sum(row.get('observation_count', 0) for row in result['companies'].values())} audit-only observations"
    )
    return result


if __name__ == "__main__":
    build()
