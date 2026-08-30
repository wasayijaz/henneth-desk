from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_intelligence_cases import (
    CASE_PRODUCT_VERSION,
    FOLLOW_THROUGH_DOC_ID,
    FOLLOW_THROUGH_EVENT_ID,
    MARI_CASE_ID,
    MARI_DOC_ID,
    MARI_EVENT_ID,
    MLCF_CASE_ID,
    MLCF_CANONICAL_CONTROL_EVENT_ID,
    MLCF_CANONICAL_FOLLOW_THROUGH_EVENT_ID,
    OUT,
    PUBLIC_OFFER_DOC_ID,
    PUBLIC_OFFER_EVENT_ID,
    build,
)
from ci_checker_helpers import without_root_meta
from psx_data import ROOT, STATE, load_json


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
    "expected_return",
}
FORBIDDEN_STATUSES = {"Corroborated", "Modelled", "Validated", "Published"}


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _walk(value: object, path: str = ""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield path, key, item
            yield from _walk(item, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")


def _assert_no_forbidden_payload(case: dict) -> None:
    for _path, key, value in _walk(case):
        lowered = str(key).lower()
        if lowered in FORBIDDEN_KEYS:
            raise AssertionError(f"forbidden case key emitted: {key}")
        if lowered == "status" and value in FORBIDDEN_STATUSES:
            raise AssertionError(f"case was promoted beyond Observed: {value}")


def _assert_evidence(ref: dict, expected_event_id: str, expected_doc_id: str, expected_page: int) -> None:
    if ref.get("event_id") != expected_event_id:
        raise AssertionError(f"event id mismatch: {ref.get('event_id')}")
    if ref.get("document_id") != expected_doc_id:
        raise AssertionError(f"document id mismatch: {ref.get('document_id')}")
    if ref.get("page") != expected_page:
        raise AssertionError(f"page mismatch for {expected_doc_id}: {ref.get('page')}")
    if not str(ref.get("source_url") or "").startswith("https://dps.psx.com.pk/download/document/"):
        raise AssertionError(f"non-PSX source URL emitted for {expected_doc_id}")
    if not HEX64.fullmatch(str(ref.get("content_sha256") or "")):
        raise AssertionError(f"missing content hash for {expected_doc_id}")
    if not ref.get("text"):
        raise AssertionError(f"missing evidence text for {expected_doc_id}")


def _assert_mlcf_cement_readiness(case: dict) -> None:
    readiness = case.get("cement_input_readiness") or {}
    if readiness.get("status") != "observed_only" or readiness.get("kernel_activation") != "blocked":
        raise AssertionError("MLCF cement readiness must remain observed-only and blocked")
    if readiness.get("attribution") != {
        "acquirer": "MLCF",
        "target": "PIOC",
        "follow_through": "dispatch_inclusion",
    }:
        raise AssertionError("MLCF cement attribution mismatch")
    joins = readiness.get("source_join") or []
    if len(joins) != 2:
        raise AssertionError("MLCF cement readiness requires two source joins")
    primary, follow = joins
    expected = [
        (primary, MLCF_CANONICAL_CONTROL_EVENT_ID, PUBLIC_OFFER_EVENT_ID, PUBLIC_OFFER_DOC_ID, 3,
         "98cf83c9a286999c8006a7f73f490248f26694c9edbfc815b3dbd9188ee22a54",
         "70a110272f96813a4d6693b596c99d9dbc4c4781d42a519543557a04ec4c581f",
         "2025-12-18T12:52:00+05:00", "2025-12-18", "2025-12-18"),
        (follow, MLCF_CANONICAL_FOLLOW_THROUGH_EVENT_ID, FOLLOW_THROUGH_EVENT_ID, FOLLOW_THROUGH_DOC_ID, 4,
         "744a0c710043d6e0a7de36bb99f21ca50f0f9346f6972b957f6733a47deae11f",
         "137a01f15530276a63688c01bc7eff20dd4b27154314786149fa9d8b22c21b2f",
         "2026-04-28T10:25:00+05:00", "2026-04-28", "2026-04-28"),
    ]
    for ref, canonical, legacy, doc_id, page, content_hash, evidence_hash, published, effective, available in expected:
        if ref.get("canonical_event_id") != canonical or ref.get("legacy_event_id") != legacy:
            raise AssertionError("MLCF canonical/legacy event alias mismatch")
        if ref.get("document_id") != doc_id or ref.get("page") != page:
            raise AssertionError("MLCF cement readiness document/page mismatch")
        if ref.get("content_sha256") != content_hash or ref.get("evidence_sha256") != evidence_hash:
            raise AssertionError("MLCF cement readiness hash mismatch")
        if ref.get("published_at") != published or ref.get("effective_date") != effective or ref.get("available_on") != available:
            raise AssertionError("MLCF cement readiness date mismatch")
    counters = readiness.get("financial_truth_counters") or {}
    for section, required, present, periods in (
        ("annual_income_triplets", 5, 3, ["2026-06-30", "2025-06-30", "2024-06-30"]),
        ("qualified_reported_quarter_fact_sets", 8, 3, ["2026-03-31", "2025-12-31", "2025-09-30"]),
        ("annual_operating_cash_flow", 5, 2, ["2025-06-30", "2024-06-30"]),
    ):
        row = counters.get(section) or {}
        if row.get("required") != required or row.get("present") != present or row.get("qualified_periods") != periods:
            raise AssertionError(f"MLCF financial counter mismatch: {section}")
    share = counters.get("share_count") or {}
    if share.get("status") != "missing_official_share_count_capital_note_tie_out" or share.get("available_on") is not None or share.get("source") is not None:
        raise AssertionError("MLCF share-count tie-out must remain missing")
    requirements = readiness.get("event_specific_kernel_requirements") or {}
    if not requirements or any(
        not isinstance(record, dict)
        or record.get("value") is not None
        or record.get("source_label") != "retained_state_only:no_source_qualified_event_input"
        or record.get("status") != "missing_source_bound_input"
        for record in requirements.values()
    ):
        raise AssertionError("MLCF event-specific kernel inputs must be source-labelled nulls")
    if readiness.get("guardrails") != {
        "dispatch_inclusion_not_standalone_pioc_earnings_or_capacity_impact": True,
        "no_numeric_model_output": True,
    }:
        raise AssertionError("MLCF cement readiness guardrails mismatch")


def main() -> None:
    if not OUT.exists():
        raise AssertionError("intelligence_cases.json is missing")
    profiles = load_json(STATE / "company_profiles.json", {})
    pilot_order = list((profiles.get("pilot") or {}).get("symbols") or [])
    pilot = set(pilot_order)
    if len(pilot_order) != 20 or len(pilot) != 20:
        raise AssertionError("pilot boundary must be exactly 20")
    state = load_json(OUT, {})
    if state.get("schema_version") != 1 or state.get("case_product_version") != CASE_PRODUCT_VERSION:
        raise AssertionError("intelligence case schema/version mismatch")
    if set(state.get("pilot_symbols") or []) != pilot or set(state.get("companies") or {}) != pilot:
        raise AssertionError("intelligence case state must preserve the exact pilot boundary")
    if state.get("summary", {}).get("observed_case_count") != 2 or state.get("summary", {}).get("published_case_count") != 0:
        raise AssertionError("expected exactly two observed cases and zero published cases")
    row = (state.get("companies") or {}).get("MLCF") or {}
    cases = row.get("cases") or []
    if row.get("status") != "observed_seed_available" or len(cases) != 1:
        raise AssertionError("MLCF observed seed missing")
    case = cases[0]
    if case.get("case_id") != MLCF_CASE_ID or case.get("status") != "Observed":
        raise AssertionError("MLCF case identity/status mismatch")
    if case.get("epistemic_type") != "reported_fact" or case.get("symbol") != "MLCF" or case.get("target_symbol") != "PIOC":
        raise AssertionError("MLCF case epistemic or issuer identity mismatch")
    _assert_no_forbidden_payload(case)
    facts = {fact.get("fact_id"): fact for fact in case.get("observed_facts") or []}
    required_facts = {"mlcf_pioc_public_offer_control", "mlcf_pioc_dispatch_inclusion"}
    if set(facts) != required_facts:
        raise AssertionError(f"observed facts mismatch: {sorted(facts)}")
    public_values = {row.get("label"): row.get("value") for row in facts["mlcf_pioc_public_offer_control"].get("reported_values") or []}
    for label, expected in {
        "public_offer_shares": "up to 26,623,096 PIOC shares",
        "public_offer_percent": "11.72% shares",
        "spa_percent": "58.03% through Share Purchase Agreement(s)",
        "offer_price": "PKR 478.43 per share",
    }.items():
        if public_values.get(label) != expected:
            raise AssertionError(f"public-offer value mismatch for {label}: {public_values.get(label)}")
    follow_values = {row.get("label"): row.get("value") for row in facts["mlcf_pioc_dispatch_inclusion"].get("reported_values") or []}
    if follow_values.get("acquisition_timing") != "during February 2026":
        raise AssertionError("February 2026 acquisition timing was not preserved")
    _assert_evidence(facts["mlcf_pioc_public_offer_control"]["evidence"][0], PUBLIC_OFFER_EVENT_ID, PUBLIC_OFFER_DOC_ID, 3)
    _assert_evidence(facts["mlcf_pioc_dispatch_inclusion"]["evidence"][0], FOLLOW_THROUGH_EVENT_ID, FOLLOW_THROUGH_DOC_ID, 4)
    _assert_mlcf_cement_readiness(case)
    blocks = case.get("promotion_blocks") or {}
    for status in ("Corroborated", "Modelled", "Published"):
        if status not in blocks:
            raise AssertionError(f"missing promotion block for {status}")

    mari_row = (state.get("companies") or {}).get("MARI") or {}
    mari_cases = mari_row.get("cases") or []
    if mari_row.get("status") != "observed_seed_available" or len(mari_cases) != 1:
        raise AssertionError("MARI observed seed missing")
    mari_case = mari_cases[0]
    if mari_case.get("case_id") != MARI_CASE_ID or mari_case.get("status") != "Observed":
        raise AssertionError("MARI case identity/status mismatch")
    if mari_case.get("epistemic_type") != "reported_fact" or mari_case.get("symbol") != "MARI":
        raise AssertionError("MARI case epistemic or issuer identity mismatch")
    _assert_no_forbidden_payload(mari_case)
    mari_facts = {fact.get("fact_id"): fact for fact in mari_case.get("observed_facts") or []}
    if set(mari_facts) != {"mari_offshore_exploration_blocks_acquisition"}:
        raise AssertionError("MARI observed facts mismatch")
    mari_fact = mari_facts["mari_offshore_exploration_blocks_acquisition"]
    if {row.get("label"): row.get("value") for row in mari_fact.get("reported_values") or []} != {"stated_purpose": "find new hydrocarbon resources"}:
        raise AssertionError("MARI stated purpose mismatch")
    mari_ref = (mari_fact.get("evidence") or [{}])[0]
    _assert_evidence(mari_ref, MARI_EVENT_ID, MARI_DOC_ID, 3)
    if mari_ref.get("content_sha256") != "cdc3f69157f5e5803238ba347ecb4e96f7297479df87d345739896913de8aae4":
        raise AssertionError("MARI source hash mismatch")
    for status in ("Corroborated", "Modelled", "Published"):
        if status not in (mari_case.get("promotion_blocks") or {}):
            raise AssertionError(f"MARI missing promotion block for {status}")
    if _dump(without_root_meta(state)) != _dump(without_root_meta(build(write=False))):
        raise AssertionError("intelligence case rebuild is not deterministic")

    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_ci_slice.py")], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    slice_state = load_json(ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json", {"tickers": []})
    rows = {row.get("symbol"): row for row in slice_state.get("tickers") or []}
    if rows.get("MLCF", {}).get("intelligence_cases") != row:
        raise AssertionError("CI slice does not expose the MLCF intelligence case row exactly")
    print("intelligence_cases: PASS (MLCF and MARI Observed seeds, 3 official citations)")


if __name__ == "__main__":
    main()
