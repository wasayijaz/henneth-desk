#!/usr/bin/env python3
"""Small, deterministic financial-fact normalizer.

The document extractor intentionally stores only bounded evidence.  This module
therefore accepts the transient page text during a live extraction and returns
bounded, page-linked records.  The persisted series never contains document
text.  A later rebuild can consume the durable ``company_documents.json`` rows
when their evidence is sufficient, but it will not guess a period or unit that
is not explicitly present.
"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import date
from typing import Any, Iterable
from urllib.parse import urlparse

from financial_statement_facts import PARSER_VERSION, PARSER_REVISION


_DATE_PATTERNS = (
    re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?!\d)"),
    re.compile(r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b", re.I),
    re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b", re.I),
)
_MONTHS = {m.lower(): i for i, m in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1)}
_PERIOD_RE = re.compile(r"\b(period|quarter|year|half[- ]year|six[- ]month|nine[- ]month|month)\b.{0,30}\b(end(?:ed)?|ended)\b", re.I)
_PERIOD_WORDS = (
    ("annual", re.compile(r"\b(annual|year[- ]end|year ended|audited financial)\b", re.I)),
    ("half_year", re.compile(r"\b(half[- ]year|six[- ]month|six months|interim)\b", re.I)),
    ("quarter", re.compile(r"\b(quarter(?:ly)?|1st quarter|2nd quarter|3rd quarter|4th quarter)\b", re.I)),
)
_HEADER_SCALE_RE = re.compile(r"\(\s*(?:rupees?|rs\.?)\s+in\s+(thousand|million|billion|mn|bn)\s*\)", re.I)
_SUFFIX_SCALE = {"thousand": 1_000, "million": 1_000_000, "mn": 1_000_000, "billion": 1_000_000_000, "bn": 1_000_000_000}
_STRUCTURED_LINES = {
    "revenue", "gross_profit", "operating_profit", "finance_cost",
    "profit_before_tax", "tax_expense", "profit_after_tax_attributable", "basic_eps",
    "operating_cash_flow",
}
_STRUCTURED_STATEMENT_TYPES = {
    **{line: "income_statement" for line in _STRUCTURED_LINES if line != "operating_cash_flow"},
    "operating_cash_flow": "cash_flow_statement",
}
_OFFICIAL_PSX_DOCUMENT_RE = re.compile(r"^https://dps\.psx\.com\.pk/download/document/\d+\.pdf$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.I)


def _document_available_on(doc: dict[str, Any], fact: dict[str, Any]) -> str | None:
    """Return the authoritative date-level availability for a source receipt."""
    for value in (doc.get("available_on"), doc.get("published_at"), doc.get("retrieved_at"),
                  fact.get("available_on")):
        parsed = _iso_date_value(value)
        if parsed is not None:
            return parsed.isoformat()
    return None


def _same_domain(host: Any, root_domain: Any) -> bool:
    host_text = str(host or "").lower().rstrip(".")
    root_text = str(root_domain or "").lower().lstrip(".").rstrip(".")
    if host_text.startswith("www."):
        host_text = host_text[4:]
    if root_text.startswith("www."):
        root_text = root_text[4:]
    return bool(host_text and root_text and (host_text == root_text or host_text.endswith("." + root_text)))


def issuer_registry_binding(doc: dict[str, Any], fact: dict[str, Any],
                            registry: dict[str, Any] | None,
                            *, evidence_page: Any = None,
                            evidence_text: str = "") -> tuple[dict[str, Any] | None, list[str]]:
    """Validate an issuer PDF against the retained same-domain source registry.

    The registry is deliberately required as an explicit input.  A URL that is
    merely HTTPS (or happens to look like an issuer PDF) is not provenance.
    ``company_documents.json`` supplies the verified bytes/hash and page
    evidence; the registry supplies the retained issuer link and domain.
    """
    flags: list[str] = []
    doc_id = str(doc.get("doc_id") or "")
    source_url = str(fact.get("source_url") or doc.get("source_url") or "")
    if not doc_id.startswith("issuer:"):
        flags.append("issuer_document_id_required")
    if not source_url:
        flags.append("issuer_source_url_required")
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.path.lower().endswith(".pdf"):
        flags.append("issuer_pdf_url_required")
    doc_hash = str(doc.get("content_sha256") or "").lower()
    fact_hash = str(fact.get("content_sha256") or "").lower()
    if not _SHA256_RE.fullmatch(doc_hash) or not _SHA256_RE.fullmatch(fact_hash):
        flags.append("issuer_content_sha256_required")
    elif doc_hash != fact_hash:
        flags.append("issuer_content_hash_mismatch")
    if doc.get("status") != "ready":
        flags.append("issuer_document_not_verified")
    if str(doc.get("media_type") or doc.get("mime_type") or "").lower() not in {"application/pdf", "application/x-pdf"}:
        flags.append("issuer_pdf_media_type_required")
    local_hash = str(doc.get("local_sha256") or "").lower()
    if local_hash and local_hash != doc_hash:
        flags.append("issuer_local_content_hash_mismatch")
    if not isinstance(evidence_page, int) or isinstance(evidence_page, bool) or evidence_page < 1 or not evidence_text.strip():
        flags.append("issuer_page_evidence_required")
    tickers = {str(t).strip().upper() for t in (doc.get("tickers") or fact.get("tickers") or []) if str(t).strip()}
    ticker_rows = (registry or {}).get("tickers") if isinstance(registry, dict) else None
    if not isinstance(ticker_rows, dict) or not tickers:
        flags.append("issuer_registry_required")
        return None, sorted(set(flags))
    matches: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for ticker in sorted(tickers):
        row = ticker_rows.get(ticker)
        if not isinstance(row, dict):
            continue
        root_domain = row.get("root_domain")
        if not _same_domain(parsed.hostname, root_domain):
            continue
        for link in row.get("document_links") or []:
            if not isinstance(link, dict):
                continue
            if str(link.get("id") or "") == doc_id and str(link.get("url") or "") == source_url:
                link_page = urlparse(str(link.get("source_page") or row.get("issuer_url") or ""))
                if not _same_domain(link_page.hostname, root_domain):
                    continue
                matches.append((ticker, row, link))
    if len(matches) != 1:
        flags.append("issuer_registry_link_not_found")
        return None, sorted(set(flags))
    ticker, row, link = matches[0]
    if flags:
        return None, sorted(set(flags))
    return {
        "status": "qualified",
        "document_id": doc_id,
        "link_id": str(link.get("id")),
        "source_url": source_url,
        "source_page": str(link.get("source_page") or row.get("issuer_url") or ""),
        "root_domain": str(row.get("root_domain") or ""),
        "content_sha256": doc_hash,
        "evidence_page": evidence_page,
        "ticker": ticker,
        "registry_source": "state/company_intel/source_registry.json",
    }, []


def _iso_date(day: str, month: str, year: str) -> str | None:
    try:
        if month.isdigit():
            value = date(int(year), int(month), int(day))
        else:
            value = date(int(year), _MONTHS[month.lower()], int(day))
        return value.isoformat()
    except (KeyError, ValueError):
        return None


def explicit_period_end(title: str | None, pages: Iterable[str] = ()) -> tuple[str | None, str | None, list[str]]:
    """Find a reporting period only when an explicit ending phrase is present."""
    title_text = str(title or "")
    page_text = "\n".join(str(p or "") for p in pages)
    # Prefer title: a published timestamp must never become a reporting period.
    candidates: list[tuple[str, str]] = [(title_text, "title")]
    # Evidence pages may contain the header; limit the fallback to pages with a
    # period marker so ordinary dates in directors' biographies are ignored.
    candidates.extend((p, "page") for p in page_text.split("\n") if _PERIOD_RE.search(p))
    for material, origin in candidates:
        if not _PERIOD_RE.search(material) and origin == "title":
            # Common PSX title form: "Financial Results 31.12.2023".
            if not re.search(r"\b(results?|financial statements?)\b", material, re.I):
                continue
        for pattern in _DATE_PATTERNS:
            match = pattern.search(material)
            if not match:
                continue
            groups = match.groups()
            if len(groups) != 3:
                continue
            if groups[0].isdigit():
                iso = _iso_date(groups[0], groups[1], groups[2])
            else:
                iso = _iso_date(groups[1], groups[0], groups[2])
            if iso:
                return iso, period_type(material), []
    return None, None, ["missing_period_end"]


def period_type(material: str | None) -> str | None:
    value = str(material or "")
    for kind, pattern in _PERIOD_WORDS:
        if pattern.search(value):
            return kind
    return None


def consolidation_basis(material: str | None) -> tuple[str | None, list[str]]:
    text = str(material or "")
    consolidated = bool(re.search(r"\bconsolidated\b", text, re.I))
    unconsolidated = bool(re.search(r"\bunconsolidated\b|\bseparate financial", text, re.I))
    if consolidated and unconsolidated:
        return None, ["conflicting_consolidation_labels"]
    if consolidated:
        return "consolidated", []
    if unconsolidated:
        return "unconsolidated", []
    return None, ["missing_consolidation_basis"]


def currency_and_scale(fact: dict[str, Any], evidence_text: str) -> tuple[str | None, int | None, list[str]]:
    text = f"{fact.get('unit') or ''} {fact.get('raw_value') or ''} {evidence_text}"
    flags: list[str] = []
    currency = "PKR" if re.search(r"\b(?:rs\.?|rupees?)\b|PKR|pkr/share", text, re.I) else None
    if currency is None:
        flags.append("missing_currency")
    fact_type = str(fact.get("fact_type") or "").lower()
    per_share = fact_type in {"eps", "dividend", "target_price"}
    percent = fact_type in {"change_pct", "margin"}
    multiplier = 1 if per_share or percent else fact.get("scale_multiplier")
    if isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)) or multiplier <= 0:
        multiplier = None
    # Prefer an explicit *table header* over an extractor default.  Narrative
    # ``Rs 12 bn`` values must not scale a per-share or percentage metric.
    scale_match = _HEADER_SCALE_RE.search(evidence_text) if not per_share and not percent else None
    if scale_match:
        token = scale_match.group(1)
        if token:
            multiplier = _SUFFIX_SCALE[token.lower()]
    if multiplier is None and not per_share and not percent:
        flags.append("missing_unit_scale")
    return currency, int(multiplier) if multiplier is not None else None, flags


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _parse_structured_raw(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if text in {"", "-", "—", "–", "n/a", "na"}:
        return None
    negative = (text.startswith("(") and text.endswith(")")) or text.endswith("-")
    text = text.strip("()").rstrip("-").strip()
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        return None
    number = float(text)
    if not math.isfinite(number):
        return None
    return -number if negative else number


def _close_enough(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-6)


def _iso_date_value(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def normalize_fact(doc: dict[str, Any], fact: dict[str, Any], *, pages: Iterable[str] = (),
                   source_registry: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Return one bounded series row or ``None`` when no source identity exists."""
    doc_id = str(doc.get("doc_id") or "")
    ticker_values = doc.get("tickers") or fact.get("tickers") or []
    tickers = sorted({str(t).strip().upper() for t in ticker_values if str(t).strip()})
    evidence = next((e for e in fact.get("evidence") or [] if isinstance(e, dict)), {})
    source_url = evidence.get("source_url") or doc.get("source_url")
    evidence_page = evidence.get("page")
    evidence_text = str(evidence.get("text") or "")
    structured_v3 = fact.get("parser_version") == PARSER_VERSION and fact.get("parser_revision") == PARSER_REVISION
    if not doc_id or not source_url or not tickers or (not evidence_page and not structured_v3):
        return None
    cited_page = evidence.get("page")
    page_list = [str(p or "") for p in pages]
    page_count = doc.get("page_count")
    durable_page_count = (isinstance(page_count, int) and not isinstance(page_count, bool)
                          and page_count > 0)
    valid_evidence_page = (isinstance(cited_page, int) and not isinstance(cited_page, bool)
                           and cited_page > 0 and (
                               cited_page <= len(page_list)
                               or (durable_page_count and cited_page <= page_count)
                           ))
    # Durable document state retains only bounded excerpts, not one entry per
    # PDF page.  When page_count proves the cited page exists but that page is
    # outside the bounded excerpt list, keep using the exact fact evidence.
    cited_page_text = (page_list[cited_page - 1]
                       if valid_evidence_page and cited_page <= len(page_list)
                       else evidence_text)
    # A period may come from the title or the exact page cited by this fact;
    # never borrow a reporting header from a different page in the same PDF.
    if fact.get("parser_version") == "financial_statement_v2":
        period_end = fact.get("period_end")
        # Geometry-backed statement facts carry an exact duration.  Older
        # retained v2 rows predate the explicit period_type field, so preserve
        # the source fact and deterministically enrich the missing redundant
        # label rather than treating a verified 12-month statement as unknown.
        inferred_type = fact.get("period_type") or (
            "annual" if fact.get("duration_months") == 12 else "unknown"
        )
        period_flags = [] if period_end else ["missing_period_end"]
    else:
        period_end, inferred_type, period_flags = explicit_period_end(doc.get("title"), [cited_page_text])
    # All table-unit and consolidation decisions are made from the cited page,
    # never from an unrelated page's header.
    basis, basis_flags = (fact.get("consolidation"), []) if fact.get("parser_version") == "financial_statement_v2" else consolidation_basis(f"{doc.get('title') or ''} {cited_page_text}")
    currency, multiplier, unit_flags = currency_and_scale(fact, cited_page_text)
    issuer_binding = None
    if structured_v3:
        currency = fact.get("currency")
        multiplier = fact.get("unit_multiplier")
        unit_flags = []
        multiplier_number = _finite_number(multiplier)
        scale_number = _finite_number(fact.get("scale"))
        if currency is None:
            unit_flags.append("missing_structured_currency")
        if multiplier is None:
            unit_flags.append("missing_structured_unit_multiplier")
        if fact.get("scale") is None:
            unit_flags.append("missing_structured_scale")
        valid_scale = multiplier_number in {1.0, 1000.0, 1000000.0, 1000000000.0}
        if str(fact.get("fact_type") or "").lower() in {"basic_eps", "eps"}:
            valid_scale = multiplier_number == 1.0 and scale_number == 1.0
        if multiplier is not None and not valid_scale:
            unit_flags.append("invalid_structured_unit_multiplier")
        if fact.get("scale") is not None and (scale_number is None or multiplier_number is None or not _close_enough(scale_number, multiplier_number)):
            unit_flags.append("structured_scale_mismatch")
    metric = str(fact.get("fact_type") or "other")
    if not structured_v3:
        unit_flags.append("legacy_parser_revision_quarantine")
    if metric == "change_pct":
        currency = None
        multiplier = 1
        unit_flags = [flag for flag in unit_flags if flag not in {"missing_currency", "missing_unit_scale"}]
    flags = sorted(set((fact.get("quality_flags") or []) + period_flags + basis_flags + unit_flags))
    raw_value = fact.get("raw_value")
    normalized = fact.get("normalized_value")
    if multiplier and isinstance(raw_value, str) and not structured_v3:
        # Extractor normalized values are raw-value based.  Apply an explicit
        # table scale only when the raw value is a plain number (no suffix).
        if not re.search(r"\b(?:m|mn|million|bn|billion|thousand)\b", raw_value, re.I):
            try:
                number = float(raw_value.replace(",", ""))
                normalized = int(number * multiplier) if number.is_integer() else number * multiplier
            except ValueError:
                flags.append("unparseable_raw_value")
    if structured_v3:
        line = str(fact.get("line") or "")
        fact_document_id = str(fact.get("document_id") or "")
        doc_hash = doc.get("content_sha256")
        fact_hash = fact.get("content_sha256")
        fact_source = fact.get("source_url")
        evidence_source = evidence.get("source_url")
        if not fact.get("fact_id"): flags.append("missing_fact_id")
        if fact_document_id != doc_id: flags.append("document_id_mismatch")
        if not doc_hash or not fact_hash: flags.append("missing_content_sha256")
        elif fact_hash != doc_hash: flags.append("content_hash_mismatch")
        if not (source_url and fact_source and evidence_source):
            flags.append("missing_source_url")
        else:
            if not (source_url == fact_source == evidence_source == doc.get("source_url")):
                flags.append("source_url_mismatch")
        if str(doc_id).startswith("issuer:"):
            issuer_binding, issuer_flags = issuer_registry_binding(
                doc, fact, source_registry, evidence_page=evidence_page,
                evidence_text=evidence_text)
            flags.extend(issuer_flags)
        elif not _OFFICIAL_PSX_DOCUMENT_RE.fullmatch(str(source_url)):
            flags.append("non_official_source_url")
        if not valid_evidence_page: flags.append("invalid_evidence_page")
        if currency != "PKR": flags.append("invalid_structured_currency")
        if basis not in {"consolidated", "unconsolidated"}: flags.append("invalid_structured_consolidation")
        if fact.get("statement_type") != _STRUCTURED_STATEMENT_TYPES.get(line): flags.append("invalid_structured_statement_type")
        if line not in _STRUCTURED_LINES: flags.append("unsupported_structured_line")
        if metric != line: flags.append("line_fact_type_mismatch")
        if metric in {"basic_eps", "eps"} and (fact.get("unit") != "PKR/share" or multiplier != 1): flags.append("invalid_structured_eps_unit")
        if metric not in {"basic_eps", "eps"} and fact.get("unit") != "PKR": flags.append("invalid_structured_monetary_unit")
        if fact.get("duration_months") not in {3,6,9,12}: flags.append("invalid_structured_duration")
        if fact.get("column_role") not in {"current_period","comparative_prior_period"}: flags.append("invalid_structured_column_role")
        manifest = doc.get("manifest") if isinstance(doc.get("manifest"), dict) else {}
        authoritative_period = doc.get("period") or manifest.get("period") or doc.get("period_end")
        # Issuer report indexes may omit a publication-period field entirely.
        # A v2 fact's period is still authoritative when it comes from the
        # statement header/table geometry: current-period rows name that
        # period directly; comparative rows explicitly link back to it.
        if not authoritative_period:
            authoritative_period = (period_end if fact.get("column_role") == "current_period"
                                    else fact.get("comparative_to_period_end"))
        authoritative_date = _iso_date_value(authoritative_period)
        period_date = _iso_date_value(period_end)
        available_on = _document_available_on(doc, fact)
        available_date = _iso_date_value(available_on)
        linkage = fact.get("comparative_to_period_end")
        linkage_date = _iso_date_value(linkage) if linkage else None
        if period_date is None: flags.append("invalid_structured_period_end")
        if authoritative_date is None: flags.append("missing_authoritative_period")
        if available_date is None: flags.append("missing_or_invalid_publication_date")
        elif period_date and available_date <= period_date: flags.append("available_before_period_end")
        if fact.get("column_role") == "current_period" and linkage not in (None, ""):
            flags.append("current_period_has_comparative_linkage")
        if fact.get("column_role") == "comparative_prior_period":
            if linkage_date is None:
                flags.append("missing_comparative_linkage")
            elif authoritative_date is None or linkage_date != authoritative_date:
                flags.append("comparative_linkage_mismatch")
        if fact.get("readiness") == "model_loadable" and fact.get("quality_flags"):
            flags.append("preexisting_quality_flags_quarantine")
        raw_number = _parse_structured_raw(raw_value)
        multiplier_number = _finite_number(multiplier)
        normalized_number = _finite_number(fact.get("normalized_value"))
        value_number = _finite_number(fact.get("value"))
        if raw_number is None:
            flags.append("unparseable_raw_value")
        if multiplier_number is None or normalized_number is None or value_number is None:
            flags.append("nonfinite_structured_value")
        if raw_number is not None and multiplier_number is not None and normalized_number is not None and value_number is not None:
            expected_value = raw_number * multiplier_number
            if not (_close_enough(expected_value, normalized_number) and _close_enough(expected_value, value_number)):
                flags.append("structured_value_mismatch")
            normalized = fact.get("normalized_value")
    consolidation = basis or "unknown"
    period_type_value = inferred_type or "unknown"
    # The source fact identity is stable across a transient full-page pass and
    # a later durable-evidence rebuild.  Period/unit enrichment may improve on
    # the next run, so it must not create a second row for the same fact.
    series_seed = "|".join((tickers[0], metric, doc_id, str(fact.get("fact_id") or "")))
    series_id = "series_" + hashlib.sha256(series_seed.encode("utf-8")).hexdigest()[:24]
    blocking = {"missing_period_end", "missing_currency", "missing_unit_scale",
                "missing_consolidation_basis", "conflicting_consolidation_labels",
                "unparseable_raw_value", "conflict", "missing_or_invalid_publication_date",
                "legacy_parser_revision_quarantine", "invalid_structured_unit_multiplier",
                "invalid_structured_currency", "invalid_structured_eps_unit",
                "invalid_structured_monetary_unit", "invalid_structured_duration",
                "invalid_structured_column_role", "missing_comparative_linkage",
                "available_before_period_end", "missing_fact_id", "document_id_mismatch",
                "missing_content_sha256", "content_hash_mismatch", "missing_source_url",
                "source_url_mismatch", "non_official_source_url", "invalid_evidence_page",
                "invalid_structured_consolidation", "invalid_structured_statement_type",
                "unsupported_structured_line", "line_fact_type_mismatch",
                "nonfinite_structured_value", "structured_value_mismatch",
                "missing_structured_currency", "missing_structured_unit_multiplier",
                "missing_structured_scale", "structured_scale_mismatch",
                "invalid_structured_period_end", "missing_authoritative_period",
                "current_period_has_comparative_linkage", "comparative_linkage_mismatch",
                "preexisting_quality_flags_quarantine", "issuer_document_id_required",
                "issuer_source_url_required", "issuer_pdf_url_required", "issuer_content_sha256_required",
                "issuer_content_hash_mismatch", "issuer_document_not_verified", "issuer_pdf_media_type_required",
                "issuer_local_content_hash_mismatch", "issuer_page_evidence_required",
                "issuer_registry_required", "issuer_registry_link_not_found"}
    readiness = "model_loadable" if fact.get("readiness") == "model_loadable" and metric != "change_pct" and not blocking.intersection(flags) else "audit_only"
    available_on = _document_available_on(doc, fact)
    if fact.get("parser_version") == "financial_statement_v2" and not available_on:
        flags.append("missing_or_invalid_publication_date")
        readiness = "audit_only"
    return {
        "series_id": series_id, "ticker": tickers[0], "metric": metric,
        "parser_version": fact.get("parser_version"), "line": fact.get("line") or metric,
        "parser_revision": fact.get("parser_revision"),
        "available_on": available_on, "published_at": fact.get("published_at") or doc.get("published_at"), "retrieved_at": fact.get("retrieved_at") or doc.get("retrieved_at"),
        "statement_type": fact.get("statement_type"), "reported_label": fact.get("reported_label"),
        "duration_months": fact.get("duration_months"), "column_role": fact.get("column_role"),
        "comparative_to_period_end": fact.get("comparative_to_period_end"),
        "period_end": period_end, "period_type": period_type_value,
        "consolidation": consolidation, "currency": currency,
        "unit": fact.get("unit"), "unit_multiplier": multiplier,
        "raw_value": raw_value, "normalized_value": normalized,
        "document_id": doc_id, "fact_id": fact.get("fact_id"),
        "content_sha256": fact.get("content_sha256") or doc.get("content_sha256"),
        "source_url": source_url,
        "evidence": [{"page": evidence_page, "text": evidence_text, "source_url": source_url}],
        **({"issuer_registry_binding": issuer_binding} if issuer_binding else {}),
        "quality_flags": flags, "readiness": readiness,
    }
