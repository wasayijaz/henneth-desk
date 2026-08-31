#!/usr/bin/env python3
"""Check approved image-only document geometry without accepting numeric facts."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manual_document_authority import claim_has_authority, load_authority, validate_authority


def _fail(message: str) -> None:
    raise AssertionError(message)


def _assert_rejects(name: str, payload: dict, flag: str) -> None:
    _, flags = validate_authority(payload)
    if flag not in flags:
        _fail(f"{name}: expected {flag}, got {flags}")


def main() -> None:
    payload = load_authority()
    valid, flags = validate_authority(payload)
    if flags or set(valid) != {"psx:236626", "psx:280589"}:
        _fail(f"approved manual document authority invalid: {flags}")
    if valid["psx:236626"]["verified_pages"] != [1] or valid["psx:280589"]["verified_pages"] != [3]:
        _fail("approved citation pages changed")
    if any(record.get("facts") for record in valid.values()):
        _fail("document authority contains numeric facts")
    if not claim_has_authority({"document_id": "psx:236626", "content_sha256": valid["psx:236626"]["content_sha256"], "source_url": valid["psx:236626"]["source_url"], "page": 1}):
        _fail("approved FY24 page citation not accepted")
    if claim_has_authority({"document_id": "psx:236626", "content_sha256": valid["psx:236626"]["content_sha256"], "source_url": valid["psx:236626"]["source_url"], "page": 2}):
        _fail("unverified page citation was accepted")

    drift = copy.deepcopy(payload)
    drift["documents"]["psx:280589"]["page_count"] = 9
    _assert_rejects("page count drift", drift, "psx:280589: authority_page_evidence_count_invalid")
    forged = copy.deepcopy(payload)
    forged["documents"]["psx:236626"]["content_sha256"] = "0" * 64
    _assert_rejects("hash mismatch", forged, "psx:236626: authority_registry_binding_mismatch")
    parser_like = copy.deepcopy(payload)
    parser_like["documents"]["psx:236626"]["text_extractable"] = True
    _assert_rejects("parser-like authority", parser_like, "psx:236626: authority_image_only_policy_invalid")
    numeric = copy.deepcopy(payload)
    numeric["documents"]["psx:236626"]["facts"] = [{"value": 1}]
    _assert_rejects("numeric authority", numeric, "psx:236626: authority_must_not_contain_facts")
    one_reviewer = copy.deepcopy(payload)
    one_reviewer["approval"]["reviewers"] = ["primary_visual_review"]
    _assert_rejects("single reviewer", one_reviewer, "authority_owner_or_dual_review_missing")
    print("manual_document_authority: PASS (approved image-only geometry; zero numeric facts)")


if __name__ == "__main__":
    main()
