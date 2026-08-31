from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_mlcf_pioc_readiness_manifest import (  # noqa: E402
    CASE_ID,
    FOLLOW_THROUGH_DOC_ID,
    FOLLOW_THROUGH_FACT_ID,
    MANIFEST_VERSION,
    MLCF,
    OUT,
    PIOC,
    PUBLIC_OFFER_DOC_ID,
    PUBLIC_OFFER_FACT_ID,
    build,
)
from ci_checker_helpers import assert_ci_slice_projection, without_root_meta  # noqa: E402
import build_ci_slice as ci_slice_builder  # noqa: E402
from psx_data import ROOT, STATE, load_json  # noqa: E402


HEX64 = re.compile(r"^[0-9a-f]{64}$", re.I)
FORBIDDEN_KEYS = {
    "forecast",
    "forecast_value",
    "valuation",
    "fair_value",
    "market_expectations",
    "price_target",
    "target_price",
    "recommendation",
    "probability",
    "consideration",
    "synergy",
    "synergies",
    "eps",
    "fcf",
    "free_cash_flow",
}
FORBIDDEN_TEXT = ("forecast", "valuation", "probability", "consideration", "synergy", "EPS", "FCF")


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _walk(value: object, path: str = ""):
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield child_path, key, item
            yield from _walk(item, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")


def _assert_no_forbidden_payload(manifest: dict[str, Any]) -> None:
    for path, key, value in _walk(manifest):
        lowered = str(key).lower()
        if lowered in FORBIDDEN_KEYS:
            raise AssertionError(f"forbidden manifest key emitted at {path}: {key}")
        if isinstance(value, str):
            for token in FORBIDDEN_TEXT:
                if token.lower() in value.lower():
                    raise AssertionError(f"forbidden manifest text emitted at {path}: {token}")


def _assert_ref(ref: dict[str, Any], expected_doc_id: str, expected_page: int) -> None:
    if ref.get("document_id") != expected_doc_id:
        raise AssertionError(f"document id mismatch: {ref.get('document_id')}")
    if ref.get("page") != expected_page:
        raise AssertionError(f"page mismatch for {expected_doc_id}: {ref.get('page')}")
    if not str(ref.get("source_url") or "").startswith("https://dps.psx.com.pk/download/document/"):
        raise AssertionError(f"non-PSX source URL emitted for {expected_doc_id}")
    if not HEX64.fullmatch(str(ref.get("content_sha256") or "")):
        raise AssertionError(f"missing content hash for {expected_doc_id}")
    if ref.get("source") != "PSX DPS":
        raise AssertionError(f"source mismatch for {expected_doc_id}: {ref.get('source')}")


def _assert_missing_inputs(manifest: dict[str, Any]) -> None:
    inputs = {row.get("input_id"): row for row in manifest.get("missing_inputs") or []}
    required = {
        "pioc_ci_pilot_membership",
        "pioc_retained_official_financial_documents",
        "pioc_financial_truth_row",
        "pioc_model_input_row",
        "mlcf_full_financial_truth_gate",
        "event_specific_incremental_financial_bridge",
        "mlcf_historical_adapter_scope",
    }
    if set(inputs) != required:
        raise AssertionError(f"missing-input checklist drifted: {sorted(inputs)}")
    if inputs["pioc_ci_pilot_membership"].get("present") is not False:
        raise AssertionError("PIOC pilot absence was not preserved")
    if inputs["pioc_retained_official_financial_documents"].get("present") != 0:
        raise AssertionError("PIOC document absence must be explicit")
    if inputs["pioc_financial_truth_row"].get("present") != 0:
        raise AssertionError("PIOC financial-truth absence must be explicit")
    if inputs["pioc_model_input_row"].get("present") != 0:
        raise AssertionError("PIOC model-input absence must be explicit")
    truth_gate = inputs["mlcf_full_financial_truth_gate"]
    present = truth_gate.get("present") or {}
    required_counts = truth_gate.get("required") or {}
    truth_row = ((load_json(STATE / "company_intel" / "financial_truth_qualification.json", {}).get("companies") or {}).get(MLCF) or {})
    expected_present = {
        "annual_income_triplets": int((truth_row.get("annual_income_triplets") or {}).get("present") or 0),
        "reported_quarter_fact_sets": int((truth_row.get("qualified_reported_quarter_fact_sets") or {}).get("present") or 0),
        "annual_operating_cash_flow": int((truth_row.get("annual_operating_cash_flow") or {}).get("present") or 0),
        "official_share_count_capital_note_tie_out": int((truth_row.get("share_count") or {}).get("status") == "official_share_count_capital_note_tied_out"),
    }
    if present != expected_present:
        raise AssertionError(f"MLCF financial-truth present counts drifted: {present}")
    if required_counts.get("official_share_count_capital_note_tie_out") != 1:
        raise AssertionError("share-capital tie-out requirement must stay exactly one official record")
    if truth_gate.get("status") != "missing":
        raise AssertionError("full financial-truth gate must stay missing while history gaps remain")
    if inputs["event_specific_incremental_financial_bridge"].get("present") != []:
        raise AssertionError("event-specific financial bridge must stay absent")
    approvals = load_json(STATE / "company_intel" / "official_share_capital_approvals.json", {})
    approved_tie_outs = [
        record
        for record in (approvals.get("records") or [])
        if record.get("symbol") == MLCF
        and record.get("approved") is True
        and record.get("record_type") == "official_share_count_capital_note_tie_out"
    ]
    if len(approved_tie_outs) != expected_present["official_share_count_capital_note_tie_out"]:
        raise AssertionError(
            "approved share-capital records and financial-truth tie-out presence disagree: "
            f"{len(approved_tie_outs)} approved vs {expected_present['official_share_count_capital_note_tie_out']} present"
        )
    if inputs["mlcf_historical_adapter_scope"].get("status") != "insufficient_for_event_model":
        raise AssertionError("MLCF historical adapter scope must not be treated as event-model ready")


def _synthetic_truth_with_share_count(status: str | None) -> dict[str, Any]:
    truth = load_json(STATE / "company_intel" / "financial_truth_qualification.json", {})
    row = dict(((truth.get("companies") or {}).get(MLCF) or {}))
    if status is None:
        row.pop("share_count", None)
    else:
        row["share_count"] = dict(row.get("share_count") or {}, status=status)
    companies = dict(truth.get("companies") or {})
    companies[MLCF] = row
    return dict(truth, companies=companies)


def _assert_tie_out_fail_closed() -> None:
    """Without an owner-approved tied-out share count the manifest must report zero."""
    intelligence_cases = load_json(STATE / "company_intel" / "intelligence_cases.json", {"companies": {}})
    model_inputs = load_json(STATE / "company_intel" / "financial_model_inputs.json", {"companies": {}})
    profiles = load_json(STATE / "company_profiles.json", {})
    pilot_symbols = list((profiles.get("pilot") or {}).get("symbols") or [])
    for label, synthetic in (
        ("share-count gate is not tied out", _synthetic_truth_with_share_count("pending_official_capital_note")),
        ("share-count row is absent", _synthetic_truth_with_share_count(None)),
    ):
        result = build(
            write=False,
            intelligence_cases=intelligence_cases,
            financial_truth=synthetic,
            model_inputs=model_inputs,
            pilot_symbols=pilot_symbols,
        )
        manifest = ((result.get("companies") or {}).get(MLCF) or {}).get("manifest") or {}
        inputs = {item.get("input_id"): item for item in manifest.get("missing_inputs") or []}
        gate = inputs.get("mlcf_full_financial_truth_gate") or {}
        tie_out = int((gate.get("present") or {}).get("official_share_count_capital_note_tie_out") or 0)
        if tie_out != 0:
            raise AssertionError(f"share-capital tie-out must fail closed when {label}")
        if gate.get("status") != "missing":
            raise AssertionError(f"financial-truth gate must stay missing when {label}")
        if (inputs.get("event_specific_incremental_financial_bridge") or {}).get("present") != []:
            raise AssertionError(f"event-specific financial bridge must stay absent when {label}")
        policy = manifest.get("formal_output_policy") or {}
        if policy.get("status") != "blocked" or policy.get("hard_block") is not True:
            raise AssertionError(f"formal outputs must stay hard-blocked when {label}")


def main() -> None:
    if not OUT.exists():
        raise AssertionError("mlcf_pioc_readiness_manifest.json is missing")
    profiles = load_json(STATE / "company_profiles.json", {})
    pilot_order = list((profiles.get("pilot") or {}).get("symbols") or [])
    pilot = set(pilot_order)
    if len(pilot_order) != 20 or len(pilot) != 20:
        raise AssertionError("pilot boundary must be exactly 20")
    if PIOC in pilot:
        raise AssertionError("PIOC must remain outside the current CI pilot")
    state = load_json(OUT, {})
    if state.get("schema_version") != 1 or state.get("manifest_version") != MANIFEST_VERSION:
        raise AssertionError("manifest schema/version mismatch")
    if state.get("source_policy") != "retained CI state only; no fetching, parsing, restaging, approvals, or source mutation":
        raise AssertionError("source policy drifted")
    if set(state.get("pilot_symbols") or []) != pilot or set(state.get("companies") or {}) != pilot:
        raise AssertionError("manifest must preserve the exact pilot boundary")
    summary = state.get("summary") or {}
    if summary.get("manifest_count") != 1 or summary.get("blocked_manifest_count") != 1 or summary.get("target_in_ci_pilot") is not False:
        raise AssertionError("manifest summary must report one blocked MLCF/PIOC manifest")
    row = (state.get("companies") or {}).get(MLCF) or {}
    manifest = row.get("manifest") or {}
    if row.get("status") != "blocked_missing_inputs" or not manifest:
        raise AssertionError("MLCF manifest row missing or not blocked")
    if manifest.get("case_id") != CASE_ID or manifest.get("case_status") != "Observed":
        raise AssertionError("case identity/status mismatch")
    if manifest.get("acquirer_symbol") != MLCF or manifest.get("target_symbol") != PIOC:
        raise AssertionError("issuer/target identity mismatch")
    known = manifest.get("known_fields") or {}
    expected_known = {
        "target": "Pioneer Cement Limited",
        "control": "reported control of Pioneer Cement Limited",
        "offer_shares": "up to 26,623,096 PIOC shares",
        "offer_percent": "11.72% shares",
        "spa_percent": "58.03% through Share Purchase Agreement(s)",
        "offer_price": "PKR 478.43 per share",
        "timing": "during February 2026",
        "follow_through": "Pioneer Cement Limited dispatches included in local-market total",
    }
    if known != expected_known:
        raise AssertionError(f"known retained fields drifted: {known}")
    pilot_status = manifest.get("pilot_status") or {}
    if pilot_status.get("in_current_ci_pilot") is not False or pilot_status.get("status") != "target_not_in_ci_pilot":
        raise AssertionError("PIOC not-in-pilot status missing")
    refs = manifest.get("evidence_refs") or []
    if len(refs) != 2:
        raise AssertionError("expected exactly two official evidence refs")
    _assert_ref(refs[0], PUBLIC_OFFER_DOC_ID, 3)
    _assert_ref(refs[1], FOLLOW_THROUGH_DOC_ID, 4)
    fact_ids = {
        fact.get("fact_id")
        for fact in ((load_json(STATE / "company_intel" / "intelligence_cases.json", {}).get("companies") or {}).get(MLCF) or {}).get("cases", [{}])[0].get("observed_facts") or []
    }
    if {PUBLIC_OFFER_FACT_ID, FOLLOW_THROUGH_FACT_ID} - fact_ids:
        raise AssertionError("source intelligence case no longer contains required facts")
    _assert_missing_inputs(manifest)
    _assert_tie_out_fail_closed()
    policy = manifest.get("formal_output_policy") or {}
    if policy.get("status") != "blocked" or policy.get("hard_block") is not True or policy.get("accepted_outputs") != []:
        raise AssertionError("formal output hard-block policy missing")
    _assert_no_forbidden_payload(manifest)
    if _dump(without_root_meta(state)) != _dump(without_root_meta(build(write=False))):
        raise AssertionError("MLCF/PIOC readiness manifest rebuild is not deterministic")

    assert_ci_slice_projection(
        ci_slice_builder,
        ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json",
        MLCF,
        "mlcf_pioc_readiness_manifest",
        row,
    )
    print("mlcf_pioc_readiness_manifest: PASS (MLCF/PIOC blocked checklist, 2 official citations)")


if __name__ == "__main__":
    main()
