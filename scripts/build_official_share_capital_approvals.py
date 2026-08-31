#!/usr/bin/env python3
"""Promote only explicitly owner-approved, receipt-bound share-capital candidates."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from psx_data import ROOT, STATE, load_json, save_json


MANIFEST = ROOT / "config" / "ci_share_capital_approval_manifest.json"
CANDIDATES = STATE / "company_intel" / "official_share_capital_candidates.json"
RECEIPTS = STATE / "company_intel" / "reprocess_receipts.json"
OUT = STATE / "company_intel" / "official_share_capital_approvals.json"
VERSION = "official_share_capital_approvals_v1"


def _iso_date(value: Any) -> str | None:
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _approved_ids(manifest: dict[str, Any]) -> dict[str, str]:
    policy = manifest.get("policy") or {}
    expected = {
        "owner_approval_required": True,
        "source_bound_candidates_only": True,
        "no_numeric_values_in_manifest": True,
        "no_engine_activation_by_manifest": True,
    }
    if manifest.get("schema_version") != 1 or manifest.get("approval_version") != "ci_share_capital_approval_v1" or policy != expected:
        raise ValueError("share-capital approval manifest policy mismatch")
    approved: dict[str, str] = {}
    for row in manifest.get("approvals") or []:
        if not isinstance(row, dict) or set(row) != {"candidate_fact_id", "approved_at"}:
            raise ValueError("share-capital approval entries must contain only candidate_fact_id and approved_at")
        candidate_id = str(row.get("candidate_fact_id") or "")
        approved_at = _iso_date(row.get("approved_at"))
        if not candidate_id or not approved_at or candidate_id in approved:
            raise ValueError("invalid or duplicate share-capital approval entry")
        approved[candidate_id] = approved_at
    return approved


def _receipt_bound(candidate: dict[str, Any], receipts: list[dict[str, Any]]) -> bool:
    source = candidate.get("source") if isinstance(candidate.get("source"), dict) else {}
    doc_id = source.get("id")
    content_sha256 = source.get("content_sha256")
    return any(
        row.get("doc_id") == doc_id
        and row.get("content_sha256") == content_sha256
        and row.get("status") == "success"
        and row.get("canonical_state_committed") is True
        for row in receipts if isinstance(row, dict)
    )


def build(*, manifest_path: Path = MANIFEST, candidates_path: Path = CANDIDATES,
          receipts_path: Path = RECEIPTS, out: Path = OUT) -> dict[str, Any]:
    approved = _approved_ids(load_json(manifest_path, {}))
    candidates = load_json(candidates_path, {}).get("candidates") or []
    receipts = load_json(receipts_path, {}).get("receipts") or []
    records = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("fact_id") not in approved:
            continue
        source = candidate.get("source") if isinstance(candidate.get("source"), dict) else {}
        available_on = _iso_date(candidate.get("available_on")) or _iso_date(candidate.get("published_at"))
        if (
            candidate.get("record_type") != "official_share_count_capital_note_tie_out_candidate"
            or candidate.get("approved") is not False
            or candidate.get("readiness") != "candidate_only"
            or candidate.get("metric") != "shares_out"
            or not candidate.get("symbol")
            or not available_on
            or not source.get("id") or not source.get("url") or not source.get("content_sha256")
            or not _receipt_bound(candidate, receipts)
            or (candidate.get("tie_out") or {}).get("status") != "tied_out"
        ):
            raise ValueError(f"{candidate.get('fact_id')}: approval candidate no longer meets source-bound gate")
        records.append({
            **candidate,
            "record_type": "official_share_count_capital_note_tie_out",
            "approved": True,
            "approved_at": approved[candidate["fact_id"]],
            "available_on": available_on,
            "readiness": "financial_truth_eligible",
            "quality_flags": [],
            "approval_provenance": "config/ci_share_capital_approval_manifest.json",
        })
    result = {
        "schema_version": 1,
        "approval_output_version": VERSION,
        "source": {"candidates": "state/company_intel/official_share_capital_candidates.json", "receipts": "state/company_intel/reprocess_receipts.json", "manifest": "config/ci_share_capital_approval_manifest.json"},
        "policy": {"owner_approval_required": True, "receipt_bound": True, "does_not_fetch": True, "does_not_parse": True, "does_not_emit_forecasts": True},
        "records": records,
        "summary": {"approved_record_count": len(records)},
    }
    save_json(out, result)
    print(f"official_share_capital_approvals: {len(records)} approved records")
    return result


if __name__ == "__main__":
    build()
