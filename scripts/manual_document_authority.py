"""Fail-closed authority for approved image-only document page citations.

This ledger deliberately records geometry and provenance only.  It never
contains financial values, parser output, or a synthetic parser receipt.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any

from psx_data import STATE, load_json


AUTHORITY_PATH = STATE / "company_intel" / "manual_document_authority.json"
OFFICIAL_URL_RE = re.compile(r"^https://dps\.psx\.com\.pk/download/document/(\d+)\.pdf$")
PSX_DOC_RE = re.compile(r"^psx:(\d+)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ROOT_KEYS = {"schema_version", "append_only", "authority_revision", "approval", "documents", "_meta"}
DOCUMENT_KEYS = {
    "document_id", "symbol", "source", "source_url", "content_sha256",
    "text_extractable", "parser_status", "page_count", "verified_pages",
    "page_evidence", "published_at", "research_index_date", "provenance",
    "authority_scope", "facts",
}
PAGE_KEYS = {"page", "render_sha256", "width", "height"}
PROVENANCE_KEYS = {"vision_review_run_id", "vision_review_manifest_sha256"}


def _iso_with_zone(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def _approval_ok(approval: Any) -> bool:
    return (
        isinstance(approval, dict)
        and approval.get("owner_confirmed") is True
        and isinstance(approval.get("reviewers"), list)
        and len({str(item) for item in approval["reviewers"] if item}) >= 2
    )


def load_authority(path: Path = AUTHORITY_PATH) -> dict[str, Any]:
    payload = load_json(path, {}) if path.exists() else {}
    return payload if isinstance(payload, dict) else {}


def validate_authority(payload: dict[str, Any], *, state_root: Path = STATE) -> tuple[dict[str, dict[str, Any]], list[str]]:
    flags: list[str] = []
    if set(payload) != ROOT_KEYS:
        flags.append("authority_root_keys_invalid")
    if payload.get("schema_version") != 1 or payload.get("append_only") is not True or payload.get("authority_revision") != "manual_document_authority_v1":
        flags.append("authority_schema_invalid")
    if not _approval_ok(payload.get("approval")):
        flags.append("authority_owner_or_dual_review_missing")
    documents = payload.get("documents")
    if not isinstance(documents, dict) or not documents:
        return {}, sorted(set(flags + ["authority_documents_missing"]))
    registry = load_json(state_root / "company_documents.json", {})
    registry_documents = registry.get("documents") if isinstance(registry, dict) else {}
    research = load_json(state_root / "research_index.json", {})
    research_documents = research.get("documents") if isinstance(research, dict) else {}
    valid: dict[str, dict[str, Any]] = {}
    for key, record in documents.items():
        record_flags: list[str] = []
        if not isinstance(record, dict) or set(record) != DOCUMENT_KEYS:
            record_flags.append(f"{key}: authority_document_keys_invalid")
            flags.extend(record_flags)
            continue
        document_id = record.get("document_id")
        source_url = record.get("source_url")
        doc_match = PSX_DOC_RE.fullmatch(str(document_id or ""))
        url_match = OFFICIAL_URL_RE.fullmatch(str(source_url or ""))
        if key != document_id or not (doc_match and url_match and doc_match.group(1) == url_match.group(1)):
            record_flags.append(f"{key}: authority_document_url_mismatch")
        if record.get("symbol") != "MLCF" or record.get("source") != "PSX DPS":
            record_flags.append(f"{key}: authority_issuer_or_source_invalid")
        if not SHA256_RE.fullmatch(str(record.get("content_sha256") or "")):
            record_flags.append(f"{key}: authority_hash_invalid")
        if record.get("text_extractable") is not False or record.get("parser_status") != "image_only_under_financial_statement_v2_policy":
            record_flags.append(f"{key}: authority_image_only_policy_invalid")
        if record.get("authority_scope") != "manual_page_citation_only" or record.get("facts") != []:
            record_flags.append(f"{key}: authority_must_not_contain_facts")
        if not _iso_with_zone(record.get("published_at")) or not isinstance(record.get("research_index_date"), str):
            record_flags.append(f"{key}: authority_date_invalid")
        page_count = record.get("page_count")
        pages = record.get("page_evidence")
        verified_pages = record.get("verified_pages")
        if not isinstance(page_count, int) or isinstance(page_count, bool) or page_count < 1:
            record_flags.append(f"{key}: authority_page_count_invalid")
        if not isinstance(pages, list) or len(pages) != page_count:
            record_flags.append(f"{key}: authority_page_evidence_count_invalid")
        seen_pages: set[int] = set()
        for page in pages if isinstance(pages, list) else []:
            if not isinstance(page, dict) or set(page) != PAGE_KEYS:
                record_flags.append(f"{key}: authority_page_evidence_shape_invalid")
                continue
            number = page.get("page")
            if not isinstance(number, int) or isinstance(number, bool) or number < 1 or number > page_count or number in seen_pages:
                record_flags.append(f"{key}: authority_page_evidence_page_invalid")
            seen_pages.add(number) if isinstance(number, int) else None
            if not SHA256_RE.fullmatch(str(page.get("render_sha256") or "")) or not all(isinstance(page.get(field), int) and not isinstance(page.get(field), bool) and page[field] > 0 for field in ("width", "height")):
                record_flags.append(f"{key}: authority_page_evidence_integrity_invalid")
        if seen_pages != set(range(1, page_count + 1)):
            record_flags.append(f"{key}: authority_page_evidence_incomplete")
        if not isinstance(verified_pages, list) or not verified_pages or any(not isinstance(page, int) or isinstance(page, bool) or page < 1 or page > page_count for page in verified_pages) or len(set(verified_pages)) != len(verified_pages):
            record_flags.append(f"{key}: authority_verified_pages_invalid")
        provenance = record.get("provenance")
        if not isinstance(provenance, dict) or set(provenance) != PROVENANCE_KEYS or not provenance.get("vision_review_run_id") or not SHA256_RE.fullmatch(str(provenance.get("vision_review_manifest_sha256") or "")):
            record_flags.append(f"{key}: authority_provenance_invalid")
        registry_row = registry_documents.get(document_id) if isinstance(registry_documents, dict) else None
        research_row = research_documents.get(document_id) if isinstance(research_documents, dict) else None
        if not isinstance(registry_row, dict) or not isinstance(research_row, dict):
            record_flags.append(f"{key}: authority_retained_registry_missing")
        else:
            if any(registry_row.get(field) != record.get(field) for field in ("source_url", "content_sha256", "published_at")) or registry_row.get("local_sha256") != record.get("content_sha256"):
                record_flags.append(f"{key}: authority_registry_binding_mismatch")
            if research_row.get("url") != source_url or research_row.get("published_at") != record.get("published_at") or research_row.get("date") != record.get("research_index_date"):
                record_flags.append(f"{key}: authority_research_index_binding_mismatch")
        if record_flags:
            flags.extend(record_flags)
        else:
            valid[key] = record
    return valid, sorted(set(flags))


def claim_has_authority(claim: dict[str, Any], *, authority_path: Path = AUTHORITY_PATH, state_root: Path = STATE) -> bool:
    if not isinstance(claim, dict):
        return False
    valid, flags = validate_authority(load_authority(authority_path), state_root=state_root)
    record = valid.get(str(claim.get("document_id") or ""))
    return not flags and isinstance(record, dict) and record.get("content_sha256") == claim.get("content_sha256") and claim.get("source_url") == record.get("source_url") and claim.get("page") in (record.get("verified_pages") or [])
