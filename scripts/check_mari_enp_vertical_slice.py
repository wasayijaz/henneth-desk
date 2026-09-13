#!/usr/bin/env python3
"""Fail-closed checks for the MARI E&P vertical slice.

Real retained state must report the exact expected stages; identity mutations
must be rejected; synthetic fixtures prove the truth/operand/formal gates are
independent; structural tampering must be caught. Run after the builder.
"""
from __future__ import annotations

import copy
import json
import math
from typing import Any

from build_mari_enp_vertical_slice import (
    CANONICAL_BINDING,
    CANONICAL_EVENT_ID,
    CASES_PATH,
    CORROBORATING_BINDING,
    CORROBORATING_EVENT_ID,
    HYPOTHESIS_IDS,
    LEGACY_PESHAWAR_EVENT_ID,
    MARI_ENP_CASE_ID,
    MARI_SKY47_CASE_ID,
    OFFSHORE_EVENT_ID,
    OUT,
    RETIRED_ALIAS_IDS,
    SALES_LED_CASE_ID,
    STAGE_ORDER,
    _assemble,
    _mari_rows,
    build,
    derive_stages,
    identity_violations,
    validate_slice,
)
from psx_data import ROOT, load_json

PASSED = 0
BANNED_PHRASES = ("buy", "sell", "accumulate", "target price", "price target", "you should")
EXPECTED_BLOCKERS = [
    "ep_driver_inputs",
    "financial_truth",
    "scenario",
    "model",
    "valuation",
    "market_expectations",
    "monitoring",
    "ask",
    "public_ui",
]


def check(name: str, cond: Any, detail: str = "") -> None:
    global PASSED
    if not cond:
        raise AssertionError(name + ": " + (detail or "check failed"))
    PASSED += 1


def _assert_clean(value: Any, label: str) -> None:
    text = json.dumps(value, default=str).lower()
    for phrase in BANNED_PHRASES:
        check(label + "_no_advice_language_" + phrase.replace(" ", "_"), phrase not in text, phrase)

    def walk(node: Any) -> None:
        if isinstance(node, float):
            check(label + "_finite_float", math.isfinite(node), str(node))
        elif isinstance(node, dict):
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)


def check_real_state() -> dict[str, Any]:
    row = build(write=False)
    if OUT.exists():
        disk_row = dict(load_json(OUT, {})); disk_row.pop("_meta", None); check("slice_matches_disk", disk_row == row)
    _assert_clean(row, "real_slice")
    cases = load_json(ROOT / CASES_PATH, {})
    real_violations = identity_violations(cases)
    check("identity_no_violations", real_violations == [], str(real_violations))
    check("stage_order_exact", list(row["stages"]) == list(STAGE_ORDER))
    check("overall_blocked", row["status"] == "blocked", row["status"])
    check("blockers_exact", row["blockers"] == EXPECTED_BLOCKERS, str(row["blockers"]))
    expected_status = {
        "event_evidence": "available",
        "competing_hypotheses": "available",
        "ep_driver_inputs": "blocked",
        "analogue_cutoff": "available",
        "financial_truth": "blocked",
        "scenario": "blocked",
        "model": "blocked",
        "valuation": "blocked",
        "market_expectations": "blocked",
        "monitoring": "blocked",
        "ask": "not_generated",
        "public_ui": "not_generated",
    }
    expected_reasons = {
        "ep_driver_inputs": "blocked_missing_numeric_operands",
        "financial_truth": "financial_truth_not_qualified",
        "scenario": "financial_truth_not_qualified",
        "model": "financial_truth_not_qualified",
        "valuation": "financial_truth_not_qualified",
        "market_expectations": "financial_truth_not_qualified",
        "monitoring": "no_active_thesis",
        "ask": "ask_endpoint_not_generated",
        "public_ui": "no_mari_enp_slice_surface",
    }
    for name, status in expected_status.items():
        stage = row["stages"][name]
        check("stage_status_" + name, stage["status"] == status, str(stage["status"]))
        if status == "available":
            check("stage_reason_" + name, stage["reason"] is None, str(stage["reason"]))
        else:
            check("stage_reason_" + name, stage["reason"] == expected_reasons[name], str(stage["reason"]))
        check("stage_source_" + name, bool(stage.get("source")))
    event_stage = row["stages"]["event_evidence"]
    check(
        "canonical_binding_exact",
        event_stage["canonical"] == {"event_id": CANONICAL_EVENT_ID, **CANONICAL_BINDING},
        str(event_stage["canonical"]),
    )
    check(
        "corroborating_binding_exact",
        event_stage["corroborating"] == {"event_id": CORROBORATING_EVENT_ID, **CORROBORATING_BINDING},
        str(event_stage["corroborating"]),
    )
    hypothesis_stage = row["stages"]["competing_hypotheses"]
    check("hypothesis_ids_exact", hypothesis_stage["hypothesis_ids"] == list(HYPOTHESIS_IDS), str(hypothesis_stage["hypothesis_ids"]))
    for reading in hypothesis_stage["alternative_readings"]:
        check("alternative_reading_retained", reading.get("status") == "retained_as_observed_only", str(reading.get("alternative_id")))
    ep = row["stages"]["ep_driver_inputs"]
    check("ep_operator_status_text_only", ep["operand_statuses"].get("operator_status") == "observed_text_only", str(ep["operand_statuses"]))
    check("ep_working_interest_unavailable", ep["operand_statuses"].get("working_interest_pct") == "unavailable", str(ep["operand_statuses"]))
    check("ep_kernel_not_activated", ep["kernel_activated"] is False, str(ep["kernel_activated"]))
    check("ep_share_count_metadata_lead", ep["share_count_status"] == "metadata_lead", str(ep["share_count_status"]))
    check("ep_next_evidence_needs_owner", ep["next_evidence_status"] == "needs_owner_approval", str(ep["next_evidence_status"]))
    analogue = row["stages"]["analogue_cutoff"]
    check("analogue_horizon_ids", set(analogue["horizon_ids"]) == {"1Q", "2Q", "4Q", "8Q", "analogue_sample"}, str(analogue["horizon_ids"]))
    check("analogue_derived_fact", analogue["epistemic_type"] == "derived_fact", str(analogue["epistemic_type"]))
    truth = row["stages"]["financial_truth"]
    check("truth_not_qualified", truth["truth_status"] == "not_qualified", str(truth["truth_status"]))
    check("truth_annual_0_of_5", truth["annual_coverage"] == {"present": 0, "required": 5}, str(truth["annual_coverage"]))
    check("truth_quarters_0_of_8", truth["quarter_coverage"] == {"present": 0, "required": 8}, str(truth["quarter_coverage"]))
    check("truth_ocf_0_of_5", truth["annual_ocf_coverage"] == {"present": 0, "required": 5}, str(truth["annual_ocf_coverage"]))
    check("truth_share_count_status", truth["share_count_status"] == "missing_official_share_count_capital_note_tie_out", str(truth["share_count_status"]))
    for name in ("model", "valuation", "market_expectations"):
        stage = row["stages"][name]
        check("formal_fail_closed_" + name, stage["status"] == "blocked" and stage["reason"] == "financial_truth_not_qualified", str(stage["reason"]))
        check("formal_product_blocked_" + name, stage["product_status"] in {"blocked", "blocked_financial_truth_not_qualified"}, str(stage["product_status"]))
    check("formal_policy_flag", row["formal_output_policy"]["synthetic_fixture_outputs_never_count_as_formal"] is True)
    monitoring = row["stages"]["monitoring"]
    check("monitoring_no_active_thesis", monitoring["reason"] == "no_active_thesis", str(monitoring["reason"]))
    check("watchlist_no_active_watch", monitoring["watchlist_status"] == "no_active_watch", str(monitoring["watchlist_status"]))
    ask_stage = row["stages"]["ask"]
    check("ask_not_generated", ask_stage["status"] == "not_generated", ask_stage["status"])
    ui = row["stages"]["public_ui"]
    check("public_ui_not_generated", ui["status"] == "not_generated", ui["status"])
    check("ci_data_has_case_true", ui["ci_data_has_case"] is True, str(ui["ci_data_has_case"]))
    check("public_tickers_has_mari_false", ui["public_tickers_has_mari"] is False, str(ui["public_tickers_has_mari"]))
    ledger_ids = {str(entry["id"]) for entry in row["alias_rejection_ledger"]}
    check("ledger_ids_exact", ledger_ids == set(RETIRED_ALIAS_IDS) | {SALES_LED_CASE_ID}, str(ledger_ids))
    check("ledger_all_ineligible", all(entry["active_case_eligible"] is False for entry in row["alias_rejection_ledger"]))
    exclusion = row["sales_led_exclusion"]
    check("lanes_distinct", exclusion["distinct_lanes"] is True and exclusion["sales_led_case_id"] != exclusion["target_case_id"])
    check("sky47_family_ai_data_centre", exclusion["sales_led_family"] == "ai_data_centre", str(exclusion["sales_led_family"]))
    return row


def _mutated_cases(cases: dict[str, Any], event_id: str, field: str, value: Any) -> dict[str, Any]:
    mutated = copy.deepcopy(cases)
    case = next(row for row in _mari_rows(mutated) if row.get("case_id") == MARI_ENP_CASE_ID)
    lineage_row = next(row for row in case["source_lineage"] if row.get("event_id") == event_id)
    lineage_row[field] = value
    return mutated


def check_identity_mutations() -> None:
    cases = load_json(ROOT / CASES_PATH, {})
    for label, event_id, field, value in (
        ("wrong_event_id", CANONICAL_EVENT_ID, "event_id", "evt_mutation_wrong_id"),
        ("wrong_document_id", CANONICAL_EVENT_ID, "document_id", "psx:000000"),
        ("wrong_hash", CANONICAL_EVENT_ID, "content_sha256", "0" * 64),
        ("wrong_page", CANONICAL_EVENT_ID, "page", 99),
        ("wrong_canonical_published_at", CANONICAL_EVENT_ID, "document_published_at", "2000-01-01T00:00:00+05:00"),
        ("wrong_corroborating_published_at", CORROBORATING_EVENT_ID, "document_published_at", "2000-01-01T00:00:00+05:00"),
    ):
        violations = identity_violations(_mutated_cases(cases, event_id, field, value))
        check("mutation_rejected_" + label, len(violations) > 0, str(violations))
    for label, alias in (("legacy_peshawar", LEGACY_PESHAWAR_EVENT_ID), ("offshore_event", OFFSHORE_EVENT_ID)):
        violations = identity_violations(_mutated_cases(cases, CANONICAL_EVENT_ID, "event_id", alias))
        check("retired_alias_rejected_" + label, any(item.startswith("retired_alias_bound") for item in violations), str(violations))
    family = copy.deepcopy(cases)
    family_case = next(row for row in _mari_rows(family) if row.get("case_id") == MARI_ENP_CASE_ID)
    family_case["case_family"] = "ai_data_centre"
    check("case_family_mutation_rejected", identity_violations(family))
    renamed = copy.deepcopy(cases)
    renamed_case = next(row for row in _mari_rows(renamed) if row.get("case_id") == MARI_ENP_CASE_ID)
    renamed_case["case_id"] = SALES_LED_CASE_ID
    check("case_id_mutation_rejected", identity_violations(renamed))


def _analogue_block() -> dict[str, Any]:
    return {
        "status": "available",
        "epistemic_type": "derived_fact",
        "items": [{"id": horizon} for horizon in ("1Q", "2Q", "4Q", "8Q", "analogue_sample")],
    }


def _synthetic_case() -> dict[str, Any]:
    return {
        "case_id": MARI_ENP_CASE_ID,
        "case_family": "e_and_p",
        "case_type": "working_interest_acquisition",
        "status": "Observed",
        "as_of": "2026-01-01T00:00:00+05:00",
        "source_lineage": [
            {"event_id": CANONICAL_EVENT_ID, **CANONICAL_BINDING},
            {"event_id": CORROBORATING_EVENT_ID, **CORROBORATING_BINDING},
        ],
        "observed_facts": [
            {"source_event_id": CANONICAL_EVENT_ID},
            {"source_event_id": CORROBORATING_EVENT_ID},
        ],
        "alternative_readings": [
            {"alternative_id": "working_interest_not_reserves", "status": "retained_as_observed_only"},
            {"alternative_id": "operator_status_not_economics", "status": "retained_as_observed_only"},
        ],
        "promotion_blocks": {
            "Corroborated": "Blocked: synthetic fixture",
            "Modelled": "Blocked: synthetic fixture",
            "Published": "Blocked: synthetic fixture",
        },
        "sections": {"analogues": _analogue_block()},
    }


def _synthetic_cases() -> dict[str, Any]:
    return {"companies": {"MARI": {"cases": [_synthetic_case(), {"case_id": MARI_SKY47_CASE_ID, "case_family": "ai_data_centre"}]}}}


def _truth(qualified: bool) -> dict[str, Any]:
    present = 5 if qualified else 0
    quarters = 8 if qualified else 0
    return {
        "status": "qualified" if qualified else "not_qualified",
        "model_ready_financial_statement_coverage": {
            "annual": {"present": present, "required": 5},
            "reported_quarter": {"present": quarters, "required": 8},
        },
        "annual_operating_cash_flow": {"present": present, "required": 5},
        "annual_income_triplets": {"present": present, "required": 5},
        "share_count": {"status": "qualified_share_count_capital_note_tie_out" if qualified else "missing_official_share_count_capital_note_tie_out"},
    }


def _readiness(activated: bool) -> dict[str, Any]:
    items = [
        {"operand": "operator_status", "status": "observed_text_only"},
        {"operand": "working_interest_pct", "status": 0.65 if activated else "unavailable"},
    ]
    return {
        "ep_operands": {"status": "available_numeric_operands" if activated else "blocked_missing_numeric_operands", "items": items},
        "activation": {"kernel_activated": activated},
        "share_count": {"status": "metadata_lead"},
    }


def _formal(computed: bool) -> dict[str, dict[str, Any]]:
    row = {"status": "computed" if computed else "blocked", "reason": None if computed else "missing_source_gated_inputs"}
    return {"forecast": dict(row), "valuation": dict(row), "market_expectations": dict(row)}


def _thesis(active: bool) -> dict[str, Any]:
    return {"active_thesis_count": 1 if active else 0}


def _watchlist(active: bool) -> dict[str, Any]:
    return {"status": "active_watch" if active else "no_active_watch", "active_watch_count": 1 if active else 0}


def _surfaces(present: bool) -> dict[str, bool]:
    return {"ask_endpoint_present": present, "public_tickers_has_mari": present, "ci_data_has_case": True}


def _stages(truth_qualified: bool, operands_ready: bool, formal_computed: bool, thesis_active: bool, surfaces_present: bool) -> dict[str, dict[str, Any]]:
    return derive_stages(
        _synthetic_case(),
        _truth(truth_qualified),
        _readiness(operands_ready),
        _thesis(thesis_active),
        _watchlist(thesis_active),
        _formal(formal_computed),
        _surfaces(surfaces_present),
    )


def check_synthetic_fixtures() -> None:
    synthetic_violations = identity_violations(_synthetic_cases())
    check("synthetic_identity_clean", synthetic_violations == [], str(synthetic_violations))
    red_truth = _stages(False, True, True, True, True)
    check("red_truth_keeps_ep_available", red_truth["ep_driver_inputs"]["status"] == "available", red_truth["ep_driver_inputs"]["status"])
    for name in ("scenario", "model", "valuation", "market_expectations"):
        stage = red_truth[name]
        check("red_truth_blocks_" + name, stage["status"] == "blocked" and stage["reason"] == "financial_truth_not_qualified", str(stage["reason"]))
    green = _stages(True, True, True, True, True)
    for name in ("scenario", "model", "valuation", "market_expectations", "monitoring", "ask", "public_ui"):
        check("green_allows_" + name, green[name]["status"] == "available", green[name]["status"])
    missing_operands = _stages(True, False, True, True, True)
    check("operands_gate_scenario", missing_operands["scenario"]["status"] == "blocked" and missing_operands["scenario"]["reason"] == "no_source_qualified_ep_operands", str(missing_operands["scenario"]["reason"]))
    missing_formal = _stages(True, True, False, True, True)
    check("scenario_ok_without_formal_products", missing_formal["scenario"]["status"] == "available", missing_formal["scenario"]["status"])
    for name in ("model", "valuation", "market_expectations"):
        check("formal_gate_" + name, missing_formal[name]["status"] == "blocked", missing_formal[name]["status"])
    green_row = _assemble(_synthetic_case(), green, "ai_data_centre")
    green_problems = validate_slice(green_row)
    check("green_row_valid", green_problems == [], str(green_problems))
    _assert_clean(green_row, "green_row")


def check_structural_tamper() -> None:
    red_row = _assemble(_synthetic_case(), _stages(False, True, True, True, True), "ai_data_centre")
    promoted = copy.deepcopy(red_row)
    promoted["stages"]["scenario"]["status"] = "available"
    promoted["stages"]["scenario"]["reason"] = None
    check("tamper_promoted_scenario_rejected", validate_slice(promoted))
    cleared = copy.deepcopy(red_row)
    cleared["blockers"] = []
    check("tamper_cleared_blockers_rejected", validate_slice(cleared))
    green_row = _assemble(_synthetic_case(), _stages(True, True, True, True, True), "ai_data_centre")
    merged = copy.deepcopy(green_row)
    merged["sales_led_exclusion"]["distinct_lanes"] = False
    check("tamper_merged_lanes_rejected", validate_slice(merged))
    eligible = copy.deepcopy(green_row)
    eligible["alias_rejection_ledger"][0]["active_case_eligible"] = True
    check("tamper_eligible_alias_rejected", validate_slice(eligible))


def main() -> None:
    check_real_state()
    check_identity_mutations()
    check_synthetic_fixtures()
    check_structural_tamper()
    print("mari_enp_vertical_slice: PASS (" + str(PASSED) + " checks)")


if __name__ == "__main__":
    main()
