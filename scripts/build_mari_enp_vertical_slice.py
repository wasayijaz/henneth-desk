#!/usr/bin/env python3
"""Retained-state-only MARI E&P vertical-slice audit (fail-closed).

Owned files: this builder, check_mari_enp_vertical_slice.py, and the generated
state/company_intel/mari_enp_vertical_slice.json. Reads retained state only:
no fetching, no financial extraction, no OCR, no providers, no advice language.
Formal numeric outputs stay blocked unless financial truth is qualified AND the
separate E&P evidence contracts are valid. Synthetic fixtures never count as formal.
"""
from __future__ import annotations

from typing import Any

from check_distinct_golden_case_lanes import MARI_ENP_CASE_ID, MARI_SKY47_CASE_ID
from mari_enp_hypothesis_contract import CONTRACT_VERSION, EVENT_STATUS, HYPOTHESIS_IDS
from psx_data import ROOT, STATE, load_json, save_json

OUT = STATE / "company_intel" / "mari_enp_vertical_slice.json"

CASES_PATH = "state/company_intel/intelligence_cases.json"
TRUTH_PATH = "state/company_intel/financial_truth_qualification.json"
READINESS_PATH = "state/company_intel/mari_enp_evidence_readiness.json"
THESIS_PATH = "state/company_intel/thesis_monitoring.json"
WATCHLIST_PATH = "state/company_intel/evidence_watchlist.json"
FORMAL_PATHS = {
    "forecast": "state/company_intel/financial_forecasts.json",
    "valuation": "state/company_intel/formal_valuations.json",
    "market_expectations": "state/company_intel/market_expectations.json",
}
PRODUCT_STAGES = {"model": "forecast", "valuation": "valuation", "market_expectations": "market_expectations"}

CANONICAL_EVENT_ID = "evt_eddfcc381018cb0dff43"
CANONICAL_BINDING = {
    "document_id": "psx:260446",
    "page": 1,
    "content_sha256": "c13ccb4de58ad005bca106942721490593fe219ff45906c68280ea7856192e42",
    "document_published_at": "2025-09-30T10:46:00+05:00",
    "source_url": "https://dps.psx.com.pk/download/document/260446.pdf",
}
CORROBORATING_EVENT_ID = "evt_5cc9795abc3e4cfdda51"
CORROBORATING_BINDING = {
    "document_id": "psx:271327",
    "page": 6,
    "content_sha256": "e53fccd6eca58c685dbf9225140056303be704b1f389b876ba33d87aa4b687b3",
    "document_published_at": "2026-02-27T09:03:00+05:00",
    "source_url": "https://dps.psx.com.pk/download/document/271327.pdf",
}

LEGACY_PESHAWAR_EVENT_ID = "evt_b25decfc180474cbe066"
LEGACY_OFFSHORE_EVENT_ID = "evt_ddf99590afb6dacddbde"
OFFSHORE_EVENT_ID = "evt_3d1dae7553f73da60ba3"
OFFSHORE_CASE_ID = "case_mari_offshore_exploration_blocks_observed_v1"
SALES_LED_CASE_ID = MARI_SKY47_CASE_ID
RETIRED_ALIAS_IDS = (LEGACY_PESHAWAR_EVENT_ID, LEGACY_OFFSHORE_EVENT_ID, OFFSHORE_EVENT_ID, OFFSHORE_CASE_ID)

CASE_FAMILY = "e_and_p"
CASE_TYPE = "working_interest_acquisition"
ALTERNATIVE_READING_IDS = ("working_interest_not_reserves", "operator_status_not_economics")
ANALOGUE_HORIZON_IDS = ("1Q", "2Q", "4Q", "8Q", "analogue_sample")

STAGE_ORDER = (
    "event_evidence",
    "competing_hypotheses",
    "ep_driver_inputs",
    "analogue_cutoff",
    "financial_truth",
    "scenario",
    "model",
    "valuation",
    "market_expectations",
    "monitoring",
    "ask",
    "public_ui",
)
STATUS_VOCAB = ("available", "blocked", "not_generated")
TOP_LEVEL_KEYS = {
    "schema_version",
    "kind",
    "as_of",
    "symbol",
    "case_id",
    "case_family",
    "status",
    "reason",
    "stages",
    "alias_rejection_ledger",
    "sales_led_exclusion",
    "formal_output_policy",
    "policy",
    "blockers",
}


def _obj(path: str, default: dict[str, Any]) -> dict[str, Any]:
    value = load_json(ROOT / path, default)
    return value if isinstance(value, dict) else default


def _mari_rows(cases: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in (((cases.get("companies") or {}).get("MARI") or {}).get("cases") or []) if isinstance(row, dict)]


def _stage(status: str, reason: str | None, source: str, **details: Any) -> dict[str, Any]:
    return {"status": status, "reason": reason, "source": source, **details}


def _analogue_block(case: dict[str, Any]) -> dict[str, Any]:
    return (case.get("sections") or {}).get("analogues") or {}


def identity_violations(cases: dict[str, Any]) -> list[str]:
    """Fail-closed binding audit for the active MARI E&P observed case."""
    out: list[str] = []
    rows = _mari_rows(cases)
    targets = [row for row in rows if row.get("case_id") == MARI_ENP_CASE_ID]
    if len(targets) != 1:
        return ["target_case_count_" + str(len(targets))]
    case = targets[0]
    if case.get("case_family") != CASE_FAMILY:
        out.append("case_family_mismatch")
    if case.get("case_type") != CASE_TYPE:
        out.append("case_type_mismatch")
    if case.get("status") != "Observed":
        out.append("case_status_not_observed")
    lineage = [row for row in case.get("source_lineage") or [] if isinstance(row, dict)]
    for label, event_id, binding in (
        ("canonical", CANONICAL_EVENT_ID, CANONICAL_BINDING),
        ("corroborating", CORROBORATING_EVENT_ID, CORROBORATING_BINDING),
    ):
        row = next((item for item in lineage if item.get("event_id") == event_id), None)
        if row is None:
            out.append(label + "_lineage_row_missing")
            continue
        for key, want in binding.items():
            if row.get(key) != want:
                out.append(label + "_" + key + "_mismatch")
    retired = set(RETIRED_ALIAS_IDS)
    bound_ids = {str(row.get("event_id")) for row in lineage} | {str(row.get("document_id")) for row in lineage}
    retired_bound = sorted(bound_ids & retired)
    if retired_bound:
        out.append("retired_alias_bound:" + ",".join(retired_bound))
    facts = [fact for fact in case.get("observed_facts") or [] if isinstance(fact, dict)]
    lead = [str(fact.get("source_event_id")) for fact in facts[:2]]
    if lead != [CANONICAL_EVENT_ID, CORROBORATING_EVENT_ID]:
        out.append("observed_fact_lead_events_mismatch")
    readings = {
        str(reading.get("alternative_id")): reading
        for reading in case.get("alternative_readings") or []
        if isinstance(reading, dict)
    }
    for reading_id in ALTERNATIVE_READING_IDS:
        if (readings.get(reading_id) or {}).get("status") != "retained_as_observed_only":
            out.append("alternative_reading_not_retained:" + reading_id)
    gates = case.get("promotion_blocks") or {}
    for gate in ("Corroborated", "Modelled", "Published"):
        if not str(gates.get(gate, "")).startswith("Blocked"):
            out.append("promotion_gate_not_blocked:" + gate)
    analogue = _analogue_block(case)
    if analogue.get("status") != "available":
        out.append("analogue_cutoff_not_available")
    else:
        if analogue.get("epistemic_type") != "derived_fact":
            out.append("analogue_not_derived_fact")
        horizon_ids = {str(item.get("id")) for item in analogue.get("items") or [] if isinstance(item, dict)}
        if horizon_ids != set(ANALOGUE_HORIZON_IDS):
            out.append("analogue_horizon_ids_mismatch")
    sky = next((row for row in rows if row.get("case_id") == MARI_SKY47_CASE_ID), None)
    if sky is None or sky.get("case_family") != "ai_data_centre":
        out.append("sky47_sales_led_case_missing")
    return out


def _probe_surfaces() -> dict[str, bool]:
    ask = ROOT / "site" / "api" / "ask.js"
    tickers = ROOT / "site" / "src" / "data" / "public" / "tickers.json"
    ci = ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json"
    return {
        "ask_endpoint_present": ask.exists(),
        "public_tickers_has_mari": tickers.exists() and "MARI" in tickers.read_text(encoding="utf-8"),
        "ci_data_has_case": ci.exists() and MARI_ENP_CASE_ID in ci.read_text(encoding="utf-8"),
    }


def derive_stages(
    case: dict[str, Any],
    truth: dict[str, Any],
    readiness: dict[str, Any],
    thesis: dict[str, Any],
    watchlist: dict[str, Any],
    formal: dict[str, dict[str, Any]],
    surfaces: dict[str, bool],
) -> dict[str, dict[str, Any]]:
    """Pure stage derivation; the checker exercises this with synthetic fixtures."""
    truth_ok = truth.get("status") == "qualified"
    operands = readiness.get("ep_operands") or {}
    activation = readiness.get("activation") or {}
    operands_ok = activation.get("kernel_activated") is True and not str(operands.get("status") or "").startswith("blocked")
    scenario_ok = truth_ok and operands_ok
    coverage = truth.get("model_ready_financial_statement_coverage") or {}

    def counter(block: dict[str, Any]) -> dict[str, Any]:
        return {"present": block.get("present"), "required": block.get("required")}

    truth_share = truth.get("share_count")
    truth_share_status = truth_share.get("status") if isinstance(truth_share, dict) else truth_share
    readiness_share = readiness.get("share_count")
    readiness_share_status = readiness_share.get("status") if isinstance(readiness_share, dict) else readiness_share
    operand_statuses = {
        str(item.get("operand")): item.get("status")
        for item in operands.get("items") or []
        if isinstance(item, dict)
    }
    next_action = readiness.get("next_evidence_action") or {}
    analogue = _analogue_block(case)
    active_thesis_count = int(thesis.get("active_thesis_count") or 0)

    stages: dict[str, dict[str, Any]] = {}
    stages["event_evidence"] = _stage(
        "available",
        None,
        CASES_PATH,
        case_id=case.get("case_id"),
        case_family=case.get("case_family"),
        case_type=case.get("case_type"),
        lifecycle=case.get("status"),
        canonical={"event_id": CANONICAL_EVENT_ID, **CANONICAL_BINDING},
        corroborating={"event_id": CORROBORATING_EVENT_ID, **CORROBORATING_BINDING},
    )
    stages["competing_hypotheses"] = _stage(
        "available",
        None,
        "scripts/mari_enp_hypothesis_contract.py",
        hypothesis_ids=list(HYPOTHESIS_IDS),
        contract_version=CONTRACT_VERSION,
        event_status=EVENT_STATUS,
        alternative_readings=case.get("alternative_readings") or [],
    )
    stages["ep_driver_inputs"] = _stage(
        "available" if operands_ok else "blocked",
        None if operands_ok else operands.get("status"),
        READINESS_PATH,
        operand_statuses=operand_statuses,
        kernel_activated=activation.get("kernel_activated"),
        share_count_status=readiness_share_status,
        next_evidence_status=next_action.get("status"),
        next_evidence_action=next_action.get("action"),
    )
    stages["analogue_cutoff"] = _stage(
        "available",
        None,
        CASES_PATH,
        epistemic_type=analogue.get("epistemic_type"),
        horizon_ids=[str(item.get("id")) for item in analogue.get("items") or [] if isinstance(item, dict)],
    )
    stages["financial_truth"] = _stage(
        "available" if truth_ok else "blocked",
        None if truth_ok else "financial_truth_not_qualified",
        TRUTH_PATH,
        truth_status=truth.get("status"),
        annual_coverage=counter(coverage.get("annual") or {}),
        quarter_coverage=counter(coverage.get("reported_quarter") or {}),
        annual_ocf_coverage=counter(truth.get("annual_operating_cash_flow") or {}),
        income_triplet_coverage=counter(truth.get("annual_income_triplets") or {}),
        share_count_status=truth_share_status,
    )
    if scenario_ok:
        stages["scenario"] = _stage("available", None, TRUTH_PATH + "; " + READINESS_PATH)
    elif not truth_ok:
        stages["scenario"] = _stage("blocked", "financial_truth_not_qualified", TRUTH_PATH + "; " + READINESS_PATH)
    else:
        stages["scenario"] = _stage("blocked", "no_source_qualified_ep_operands", TRUTH_PATH + "; " + READINESS_PATH)
    for stage_name in ("model", "valuation", "market_expectations"):
        product = formal.get(PRODUCT_STAGES[stage_name]) or {}
        product_ok = truth_ok and product.get("status") == "computed"
        stages[stage_name] = _stage(
            "available" if product_ok else "blocked",
            None if product_ok else ("financial_truth_not_qualified" if not truth_ok else "missing_source_gated_inputs"),
            FORMAL_PATHS[PRODUCT_STAGES[stage_name]],
            product_status=product.get("status"),
            product_reason=product.get("reason"),
        )
    stages["monitoring"] = _stage(
        "available" if active_thesis_count > 0 else "blocked",
        None if active_thesis_count > 0 else "no_active_thesis",
        THESIS_PATH + "; " + WATCHLIST_PATH,
        active_thesis_count=active_thesis_count,
        watchlist_status=watchlist.get("status"),
        active_watch_count=watchlist.get("active_watch_count"),
    )
    stages["ask"] = _stage(
        "available" if surfaces.get("ask_endpoint_present") else "not_generated",
        None if surfaces.get("ask_endpoint_present") else "ask_endpoint_not_generated",
        "site/api/ask.js",
    )
    ui_ok = bool(surfaces.get("public_tickers_has_mari")) and bool(surfaces.get("ci_data_has_case"))
    stages["public_ui"] = _stage(
        "available" if ui_ok else "not_generated",
        None if ui_ok else "no_mari_enp_slice_surface",
        "site/src/data/public/tickers.json; Henneth Desk 2.CI.0/data/company_intelligence.json",
        public_tickers_has_mari=surfaces.get("public_tickers_has_mari"),
        ci_data_has_case=surfaces.get("ci_data_has_case"),
    )
    return stages


def _alias_ledger(sky47_family: Any) -> list[dict[str, Any]]:
    return [
        {
            "id": LEGACY_PESHAWAR_EVENT_ID,
            "kind": "legacy_event_id",
            "note": "Legacy Peshawar event id retained only as superseded evidence lineage; never the active case binding.",
            "active_case_eligible": False,
        },
        {
            "id": LEGACY_OFFSHORE_EVENT_ID,
            "kind": "legacy_event_id",
            "note": "Superseded legacy offshore event id; not bound as the active E&P case.",
            "active_case_eligible": False,
        },
        {
            "id": OFFSHORE_EVENT_ID,
            "kind": "superseded_event_id",
            "note": "Offshore event id drives a separate evidence-readiness record; never the Peshawar working-interest case.",
            "active_case_eligible": False,
        },
        {
            "id": OFFSHORE_CASE_ID,
            "kind": "retired_case_id",
            "note": "Retired offshore observed-case alias; excluded from active-case eligibility.",
            "active_case_eligible": False,
        },
        {
            "id": SALES_LED_CASE_ID,
            "kind": "sales_led_case_id",
            "note": "Distinct AI-data-centre sales-led lane; MARI is never counted as a sales-led case.",
            "case_family": sky47_family,
            "active_case_eligible": False,
        },
    ]


def _assemble(case: dict[str, Any], stages: dict[str, dict[str, Any]], sky47_family: Any) -> dict[str, Any]:
    blockers = [name for name in STAGE_ORDER if stages.get(name, {}).get("status") != "available"]
    return {
        "schema_version": 1,
        "kind": "mari_enp_vertical_slice",
        "as_of": case.get("as_of"),
        "symbol": "MARI",
        "case_id": case.get("case_id"),
        "case_family": case.get("case_family"),
        "status": "blocked" if blockers else "available",
        "reason": None if not blockers else blockers[0] + ":" + str(stages[blockers[0]].get("reason")),
        "stages": stages,
        "alias_rejection_ledger": _alias_ledger(sky47_family),
        "sales_led_exclusion": {
            "sales_led_case_id": SALES_LED_CASE_ID,
            "sales_led_family": sky47_family,
            "target_case_id": MARI_ENP_CASE_ID,
            "distinct_lanes": True,
            "mari_never_counted_as_sales_led": True,
        },
        "formal_output_policy": {
            "rule": "Formal numeric outputs stay blocked unless financial truth is qualified AND the separate E&P evidence contracts are valid.",
            "synthetic_fixture_outputs_never_count_as_formal": True,
        },
        "policy": {
            "retained_state_only": True,
            "research_only": True,
            "never_places_orders": True,
            "rejects_stale_and_retired_aliases": True,
            "formal_engines_require_financial_truth": True,
        },
        "blockers": blockers,
    }


def validate_slice(row: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if set(row) != TOP_LEVEL_KEYS:
        out.append("top_level_keys_mismatch")
    stages = row.get("stages") or {}
    if list(stages) != list(STAGE_ORDER):
        out.append("stage_set_or_order_mismatch")
    for name, stage in stages.items():
        if not isinstance(stage, dict):
            out.append("stage_not_object:" + name)
            continue
        if stage.get("status") not in STATUS_VOCAB:
            out.append("stage_status_invalid:" + name)
        if stage.get("status") == "available" and stage.get("reason") is not None:
            out.append("available_stage_has_reason:" + name)
        if stage.get("status") != "available" and not stage.get("reason"):
            out.append("non_available_stage_missing_reason:" + name)
        if not stage.get("source"):
            out.append("stage_missing_source:" + name)
    blockers = [name for name in STAGE_ORDER if (stages.get(name) or {}).get("status") != "available"]
    if row.get("blockers") != blockers:
        out.append("blockers_mismatch")
    if row.get("status") not in ("available", "blocked"):
        out.append("overall_status_invalid")
    if (row.get("status") == "blocked") != bool(blockers):
        out.append("overall_status_blockers_mismatch")
    if row.get("status") == "blocked" and not row.get("reason"):
        out.append("overall_reason_missing")
    ledger = row.get("alias_rejection_ledger") or []
    ledger_ids = {str(entry.get("id")) for entry in ledger if isinstance(entry, dict)}
    if ledger_ids != set(RETIRED_ALIAS_IDS) | {SALES_LED_CASE_ID}:
        out.append("alias_ledger_ids_mismatch")
    if any(entry.get("active_case_eligible") is not False for entry in ledger if isinstance(entry, dict)):
        out.append("alias_eligible_not_false")
    exclusion = row.get("sales_led_exclusion") or {}
    if exclusion.get("distinct_lanes") is not True:
        out.append("sales_led_lanes_not_distinct")
    if exclusion.get("sales_led_case_id") == exclusion.get("target_case_id"):
        out.append("sales_led_ids_not_distinct")
    if exclusion.get("mari_never_counted_as_sales_led") is not True:
        out.append("sales_led_exclusion_flag_missing")
    policy = row.get("formal_output_policy") or {}
    if policy.get("synthetic_fixture_outputs_never_count_as_formal") is not True:
        out.append("formal_policy_flag_missing")
    return out


def build(*, write: bool = True) -> dict[str, Any]:
    cases = _obj(CASES_PATH, {})
    violations = identity_violations(cases)
    if violations:
        raise ValueError("mari_identity_drift: " + "; ".join(violations))
    rows = _mari_rows(cases)
    case = next(row for row in rows if row.get("case_id") == MARI_ENP_CASE_ID)
    sky = next(row for row in rows if row.get("case_id") == MARI_SKY47_CASE_ID)
    truth = (_obj(TRUTH_PATH, {}).get("companies") or {}).get("MARI") or {}
    readiness = _obj(READINESS_PATH, {})
    thesis = (_obj(THESIS_PATH, {}).get("companies") or {}).get("MARI") or {}
    watchlist = (_obj(WATCHLIST_PATH, {}).get("companies") or {}).get("MARI") or {}
    formal = {
        name: (_obj(path, {}).get("companies") or {}).get("MARI") or {}
        for name, path in FORMAL_PATHS.items()
    }
    stages = derive_stages(case, truth, readiness, thesis, watchlist, formal, _probe_surfaces())
    row = _assemble(case, stages, sky.get("case_family"))
    problems = validate_slice(row)
    if problems:
        raise ValueError("mari_slice_invalid: " + "; ".join(problems))
    if write:
        save_json(OUT, row)
    return row


if __name__ == "__main__":
    result = build()
    print("mari_enp_vertical_slice: " + result["status"] + " -> " + str(OUT.relative_to(ROOT)))
