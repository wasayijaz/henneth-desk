#!/usr/bin/env python3
"""Build a review-only ownership-source manifest from retained CI metadata.

This never fetches, reads a document body, or emits ownership facts.  It makes
the next owner-approved source batch reviewable without converting a document
title, TOC, insider activity, or issuer relationship into a shareholding claim.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from psx_data import ROOT, STATE, load_json, save_json

OUT = ROOT / "config" / "ownership_source_review_manifest.json"
KEYWORDS = ("pattern of shareholding", "shareholding", "substantial shareholder", "free float", "free-float")
REQUIRED_REVIEW_FIELDS = [
    "statement_as_of", "availability_date", "holder_or_category", "shares_or_percentage",
    "denominator_or_issued_shares", "document_id", "source_url", "page",
]


def safe_official_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    return value


def _date(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value[:10]


def _candidate(symbol: str, source: dict, *, source_owner: str, source_type: str) -> dict | None:
    url = safe_official_url(source.get("url") or source.get("source_url"))
    if not url:
        return None
    label = str(source.get("label") or source.get("title") or source.get("digest") or "official document")
    document_type = str(source.get("document_type") or source.get("doc_type") or "issuer_document")
    haystack = f"{label} {document_type}".lower()
    if document_type != "annual_report" and not any(term in haystack for term in KEYWORDS):
        return None
    identifier = source.get("id") or source.get("hash") or source.get("document_id") or url
    return {
        "candidate_id": f"{symbol}:{identifier}",
        "symbol": symbol,
        "source_owner": source_owner,
        "source_type": source_type,
        "document_id": str(identifier),
        "source_url": url,
        "label": label,
        "document_type": document_type,
        "published_at": _date(source.get("date") or source.get("published_at")),
        "retained_at": _date(source.get("first_seen_at") or source.get("retrieved_at")),
        "review_required": True,
        "usable_ownership_facts": False,
        "reason": "metadata candidate only; document/page extraction and owner review required before any ownership fact can exist",
    }


def _dedupe(candidates: list[dict]) -> list[dict]:
    by_url: dict[str, dict] = {}
    for candidate in candidates:
        previous = by_url.get(candidate["source_url"])
        if previous is None or candidate["source_type"] < previous["source_type"]:
            by_url[candidate["source_url"]] = candidate
    return sorted(by_url.values(), key=lambda row: (row["source_type"], row["label"].lower(), row["source_url"]))


def build(write: bool = True) -> dict:
    profiles = load_json(STATE / "company_profiles.json", {})
    pilot = list((profiles.get("pilot") or {}).get("symbols") or [])
    registry = load_json(STATE / "company_intel" / "source_registry.json", {})
    research = load_json(STATE / "research_index.json", {})
    documents = research.get("documents") or {}
    companies = {}
    for symbol in pilot:
        candidates = []
        issuer = (registry.get("tickers") or {}).get(symbol) or {}
        for item in issuer.get("document_links") or []:
            candidate = _candidate(symbol, item, source_owner="issuer", source_type="issuer_registry")
            if candidate:
                candidates.append(candidate)
        for item in documents.values():
            if symbol not in (item.get("tickers") or []):
                continue
            candidate = _candidate(symbol, item, source_owner="psx", source_type="research_index")
            if candidate:
                candidates.append(candidate)
        candidates = _dedupe(candidates)
        companies[symbol] = {
            "symbol": symbol,
            "status": "review_required" if candidates else "no_retained_candidate",
            "ownership_facts": [],
            "candidates": candidates,
            "required_fields_before_activation": REQUIRED_REVIEW_FIELDS,
            "reason": (
                "candidate official documents require owner approval plus page-level extraction"
                if candidates else "no retained official ownership candidate; discover an issuer annual-report schedule, PSX float record, or official substantial-holder filing"
            ),
        }
    output = {
        "schema_version": 1,
        "kind": "ownership_source_review_manifest",
        "pilot_symbols": pilot,
        "policy": {
            "review_only": True,
            "no_fetch": True,
            "no_document_extraction": True,
            "no_ownership_activation": True,
            "no_inference_from_titles_toc_or_activity": True,
            "official_source_owners": ["issuer", "psx", "secp"],
        },
        "required_fields_before_activation": REQUIRED_REVIEW_FIELDS,
        "companies": companies,
        "summary": {
            "company_count": len(companies),
            "review_required_company_count": sum(row["status"] == "review_required" for row in companies.values()),
            "no_retained_candidate_company_count": sum(row["status"] == "no_retained_candidate" for row in companies.values()),
            "candidate_count": sum(len(row["candidates"]) for row in companies.values()),
            "activated_company_count": 0,
        },
    }
    if write:
        save_json(OUT, output)
        print(f"ownership_source_manifest: {output['summary']['candidate_count']} candidates across {len(companies)} pilot companies")
    return output


if __name__ == "__main__":
    build()
