#!/usr/bin/env python3
"""Focused contract checks for the owner-gated share-capital approval boundary."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from build_official_share_capital_approvals import build


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _candidate() -> dict:
    return {
        "fact_id": "share_candidate_fixture",
        "symbol": "MLCF",
        "metric": "shares_out",
        "record_type": "official_share_count_capital_note_tie_out_candidate",
        "approved": False,
        "readiness": "candidate_only",
        "published_at": "2025-09-25T12:43:00+05:00",
        "available_on": None,
        "tie_out": {"status": "tied_out"},
        "source": {"id": "psx:260032", "url": "https://dps.psx.com.pk/download/document/260032.pdf", "content_sha256": "a" * 64},
    }


def _manifest(approvals: list[dict]) -> dict:
    return {"schema_version": 1, "approval_version": "ci_share_capital_approval_v1", "policy": {"owner_approval_required": True, "source_bound_candidates_only": True, "no_numeric_values_in_manifest": True, "no_engine_activation_by_manifest": True}, "approvals": approvals}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="henneth-share-capital-") as raw:
        root = Path(raw)
        manifest, candidates, receipts, out = (root / name for name in ("manifest.json", "candidates.json", "receipts.json", "out.json"))
        _write(candidates, {"candidates": [_candidate()]})
        _write(receipts, {"receipts": [{"doc_id": "psx:260032", "content_sha256": "a" * 64, "status": "success", "canonical_state_committed": True}]})
        _write(manifest, _manifest([]))
        empty = build(manifest_path=manifest, candidates_path=candidates, receipts_path=receipts, out=out)
        assert empty["records"] == []
        _write(manifest, _manifest([{"candidate_fact_id": "share_candidate_fixture", "approved_at": "2026-08-31"}]))
        approved = build(manifest_path=manifest, candidates_path=candidates, receipts_path=receipts, out=out)
        record = approved["records"][0]
        assert record["record_type"] == "official_share_count_capital_note_tie_out"
        assert record["approved"] is True and record["available_on"] == "2025-09-25"
        _write(receipts, {"receipts": []})
        try:
            build(manifest_path=manifest, candidates_path=candidates, receipts_path=receipts, out=out)
        except ValueError:
            pass
        else:
            raise AssertionError("unreceipted candidate was accepted")
    print("official_share_capital_approvals: PASS")


if __name__ == "__main__":
    main()
