#!/usr/bin/env python3
"""Check the owner-verified manual financial claim gate."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
sys.path.insert(0, str(ROOT / "scripts"))

from forecast_contract import qualified_periods
from manual_financial_claims import MANUAL_SOURCE_METHOD, is_qualified_manual_fact, qualified_manual_rows
from manual_document_authority import AUTHORITY_PATH


def _fail(message: str) -> None:
    raise AssertionError(message)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_ledger(root: Path, payload: dict) -> Path:
    path = root / "verified_manual_financial_claims.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _base_ledger() -> dict:
    return _load(STATE / "company_intel" / "verified_manual_financial_claims.json")


def _first_claim_mutation(**updates) -> dict:
    payload = _base_ledger()
    payload["claims"][0] = {**payload["claims"][0], **updates}
    return payload


def _qualify(payload: dict, existing_facts: list[dict] | None = None) -> tuple[list[dict], dict]:
    with tempfile.TemporaryDirectory(prefix="henneth-manual-claims-") as td:
        return qualified_manual_rows(_write_ledger(Path(td), payload), existing_facts=existing_facts or [])


def _assert_rejects(name: str, payload: dict, expected_flag: str) -> None:
    rows, meta = _qualify(payload)
    flags = [flag for item in meta.get("rejected_claims") or [] for flag in item.get("flags") or []]
    rejected_ids = {item.get("claim_id") for item in meta.get("rejected_claims") or []}
    expected_rejections = len(rejected_ids)
    if expected_flag not in flags or len(rows) != max(0, len(payload.get("claims") or []) - expected_rejections):
        _fail(f"{name} did not reject with {expected_flag}: {flags}")


def main() -> None:
    ledger = _base_ledger()
    rows, meta = _qualify(ledger)
    if len(rows) != 9 or meta.get("qualified_count") != 9 or meta.get("rejected_count") != 0:
        _fail(f"approved ledger did not qualify exactly nine claims: {meta}")
    if {row.get("source_method") for row in rows} != {MANUAL_SOURCE_METHOD}:
        _fail("manual rows did not retain distinct source_method")
    if any(row.get("parser_version") or row.get("parser_revision") for row in rows):
        _fail("manual rows impersonate parser output")
    fy25 = [row for row in rows if row.get("period_end") == "2025-06-30"]
    if len(fy25) != 3 or any(row.get("column_role") != "comparative_prior_period" or row.get("comparative_to_period_end") != "2026-06-30" for row in fy25):
        _fail("FY2025 manual rows did not retain comparative linkage")
    if any(row.get("readiness") != "model_loadable" or row.get("quality_flags") for row in rows):
        _fail("qualified manual rows are not clean model_loadable facts")
    periods = qualified_periods(rows)
    if [row.get("period_end") for row in periods] != ["2024-06-30", "2025-06-30", "2026-06-30"]:
        _fail(f"manual rows did not satisfy three aligned periods: {periods}")

    no_owner = _base_ledger()
    no_owner["approval"]["owner_confirmed"] = False
    _assert_rejects("no owner approval", no_owner, "missing_owner_or_dual_review_approval")

    one_reviewer = _base_ledger()
    one_reviewer["approval"]["reviewers"] = ["primary_visual_review"]
    _assert_rejects("one reviewer", one_reviewer, "missing_owner_or_dual_review_approval")

    _assert_rejects("bad url", _first_claim_mutation(source_url="https://example.com/document.pdf"), "non_official_manual_source_url")
    _assert_rejects("bad hash", _first_claim_mutation(content_sha256="abc"), "invalid_manual_content_sha256")
    _assert_rejects("bad page", _first_claim_mutation(page=0), "invalid_manual_page")
    _assert_rejects("uncovered page", _first_claim_mutation(page=2), "manual_document_authority_missing_or_mismatch")
    _assert_rejects("bad availability", _first_claim_mutation(available_on="2024-06-30T00:00:00+05:00"), "manual_available_before_period_end")
    bad_comparative = _base_ledger()
    bad_comparative["claims"][3]["comparative_to_period_end"] = "2025-06-30"
    _assert_rejects("bad comparative linkage", bad_comparative, "invalid_manual_comparative_linkage")

    duplicate_conflict = _base_ledger()
    duplicate_conflict["claims"].append({**duplicate_conflict["claims"][0], "claim_id": "manual_mlc_2024_revenue_conflict", "value": 1})
    _assert_rejects("duplicate conflict", duplicate_conflict, "duplicate_manual_claim_key")

    duplicate_same = _base_ledger()
    duplicate_same["claims"].append({**duplicate_same["claims"][0], "claim_id": "manual_mlc_2024_revenue_same"})
    _assert_rejects("duplicate same semantic key", duplicate_same, "duplicate_manual_claim_key")

    forged_claim = _first_claim_mutation(source_method=MANUAL_SOURCE_METHOD)
    _assert_rejects("forged claim identity", forged_claim, "manual_claim_must_not_supply_source_identity")

    wrong_status = _first_claim_mutation(review_status="approved")
    _assert_rejects("wrong review status", wrong_status, "invalid_manual_review_status")

    not_append_only = _base_ledger()
    not_append_only["append_only"] = False
    _assert_rejects("not append only", not_append_only, "manual_ledger_not_append_only")

    nonfinite = _first_claim_mutation(value=float("nan"))
    _assert_rejects("nonfinite value", nonfinite, "nonfinite_manual_value")

    existing_conflict = [{
        "ticker": "MLCF",
        "line": "revenue",
        "period_end": "2024-06-30",
        "consolidation": "consolidated",
        "currency": "PKR",
        "statement_type": "income_statement",
        "unit": "PKR",
        "unit_multiplier": 1,
        "normalized_value": 1,
        "readiness": "model_loadable",
    }]
    rows, meta = _qualify(_base_ledger(), existing_conflict)
    flags = [flag for item in meta.get("rejected_claims") or [] for flag in item.get("flags") or []]
    if len(rows) != 8 or "manual_claim_conflicts_with_existing_model_fact" not in flags:
        _fail("existing model fact conflict did not reject only the conflicting claim")

    good = _qualify(_base_ledger())[0][0]
    forged = {**good, "source_url": "https://dps.psx.com.pk/download/document/280589.pdf"}
    orphan = {**good}
    orphan.pop("manual_claim_id", None)
    parser_like = {**good, "parser_version": "financial_statement_v2"}
    wrong_revision = {**good, "source_revision": "manual_vision_v2"}
    uncovered_fact = {**good, "evidence": [{"page": 2, "source_url": good["source_url"]}]}
    if not is_qualified_manual_fact(good):
        _fail("valid manual series fact was not accepted by source predicate")
    if any(is_qualified_manual_fact(row) for row in (forged, orphan, parser_like, wrong_revision, uncovered_fact)):
        _fail("forged/orphan manual fact passed source predicate")

    print("manual_financial_claims: PASS (approved ledger + approval/provenance/conflict gates)")


if __name__ == "__main__":
    main()
