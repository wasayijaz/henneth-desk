#!/usr/bin/env python3
"""Fail-closed checks for the three distinct published Alpha case lanes.

This is a selection-boundary check only. It does not build cases, promote facts,
or decide whether a company is financially qualified. The synthetic fixtures
exercise the lane contract without changing retained state.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from psx_data import STATE, load_json


ROOT = Path(__file__).resolve().parents[1]
INTELLIGENCE_CASES = STATE / "company_intel" / "intelligence_cases.json"
CNERGY_RECEIPT = STATE / "company_intel" / "cnergy_sales_event_intake_receipt.json"

LANES = ("e_and_p", "industrial_cement", "sales_led")
MARI_ENP_CASE_ID = "case_mari_working_interest_observed_v1"
MARI_SKY47_CASE_ID = "case_mari_sky47_karakoram1_launch_sales_observed_v1"


def _fail(message: str) -> None:
    raise AssertionError(message)


def _one_case(state: dict[str, Any], symbol: str, case_id: str) -> dict[str, Any]:
    cases = ((state.get("companies") or {}).get(symbol) or {}).get("cases") or []
    matches = [case for case in cases if isinstance(case, dict) and case.get("case_id") == case_id]
    if len(matches) != 1:
        _fail(f"{symbol} {case_id}: expected exactly one retained case, found {len(matches)}")
    return matches[0]


def _published_case(symbol: str, case_id: str, case_family: str, case_type: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "case_id": case_id,
        "case_family": case_family,
        "case_type": case_type,
        "status": "Published",
    }


def _lane_for_case(case: dict[str, Any]) -> str | None:
    family = case.get("case_family")
    case_type = str(case.get("case_type") or "")
    if family == "e_and_p":
        return "e_and_p"
    if family == "industrial_cement":
        return "industrial_cement"
    if family == "sales_led_expansion" or "sales_led" in case_type or case.get("sales_input_readiness") is not None:
        return "sales_led"
    return None


def validate_published_alpha_set(cases: list[dict[str, Any]]) -> list[str]:
    """Validate only the distinct published-lane boundary.

    The rule is intentionally symbol-agnostic: any future company may satisfy the
    sales-led lane if it is a Published case and does not reuse another lane's
    ticker or case id.
    """
    violations: list[str] = []
    if not isinstance(cases, list) or len(cases) != 3:
        return ["published alpha set must contain exactly three cases"]

    by_lane: dict[str, dict[str, Any]] = {}
    symbols: list[str] = []
    case_ids: list[str] = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            violations.append(f"cases[{index}]: must be an object")
            continue
        lane = _lane_for_case(case)
        if lane not in LANES:
            violations.append(f"cases[{index}]: unsupported or missing case lane")
            continue
        if lane in by_lane:
            violations.append(f"{lane}: duplicate lane")
        by_lane[lane] = case
        if case.get("status") != "Published":
            violations.append(f"{lane}: case must be Published for the Alpha published set")
        symbol = case.get("symbol")
        case_id = case.get("case_id")
        if not isinstance(symbol, str) or not symbol.strip():
            violations.append(f"{lane}: symbol is required")
        else:
            symbols.append(symbol)
        if not isinstance(case_id, str) or not case_id.strip():
            violations.append(f"{lane}: case_id is required")
        else:
            case_ids.append(case_id)

    for lane in LANES:
        if lane not in by_lane:
            violations.append(f"{lane}: required lane missing")
    if len(symbols) != len(set(symbols)):
        violations.append("published Alpha cases must use three distinct tickers")
    if len(case_ids) != len(set(case_ids)):
        violations.append("published Alpha cases must use three distinct case IDs")
    return sorted(set(violations))


def _assert_current_mari_sky47_cannot_count(state: dict[str, Any]) -> None:
    mari_enp = _one_case(state, "MARI", MARI_ENP_CASE_ID)
    mari_sky47 = _one_case(state, "MARI", MARI_SKY47_CASE_ID)
    if _lane_for_case(mari_enp) != "e_and_p":
        _fail("MARI Peshawar case must resolve to the E&P lane")
    if _lane_for_case(mari_sky47) != "sales_led":
        _fail("MARI Sky47 case must resolve to the sales-led lane")

    hypothetical = [
        {**copy.deepcopy(mari_enp), "status": "Published"},
        _published_case("MLCF", "case_mlcf_pioc_control_published_fixture", "industrial_cement", "acquisition_control"),
        {**copy.deepcopy(mari_sky47), "status": "Published"},
    ]
    violations = validate_published_alpha_set(hypothetical)
    if "published Alpha cases must use three distinct tickers" not in violations:
        _fail("MARI Sky47 was allowed to double-count as the separate sales-led golden company")


def _assert_current_cnergy_lead_non_promoted(state: dict[str, Any], receipt: dict[str, Any]) -> None:
    cnergy = (state.get("companies") or {}).get("CNERGY") or {}
    if cnergy.get("status") != "no_observed_case" or cnergy.get("case_count") != 0 or cnergy.get("cases") != []:
        _fail("CNERGY must remain outside selected IntelligenceCase seeds until a case seed is promoted")
    if "CNERGY" in (state.get("selected_symbols") or []):
        _fail("CNERGY must not be selected while its retained lead is evidence-only")

    if receipt.get("ticker") != "CNERGY" or receipt.get("status") != "observed_only_no_case_eligible_sales_expansion":
        _fail("CNERGY sales-event receipt identity/status drifted")
    primary = receipt.get("primary_event") or {}
    alternative = receipt.get("verified_alternative") or {}
    promotion = receipt.get("promotion") or {}
    if primary.get("event_status") != "observed_performance_record_not_sales_expansion" or not primary.get("content_sha256"):
        _fail("CNERGY primary sales-record source must be retained yet remain outside sales expansion")
    if (
        alternative.get("event_status") != "observed_only"
        or alternative.get("case_seed") is not None
        or alternative.get("event_type") != "sales_mix_expansion"
    ):
        _fail("CNERGY alternative lead must remain observed-only and unseeded")
    if promotion.get("case_seeds") != [] or promotion.get("facts") != []:
        _fail("CNERGY receipt must not promote cases or facts")
    if promotion.get("financial_truth_changed") is not False:
        _fail("CNERGY receipt must not alter financial truth")


def _assert_distinct_published_fixtures() -> None:
    positive = [
        _published_case("ENP-FIXTURE", "case_fixture_enp_published", "e_and_p", "development"),
        _published_case("CEMENT-FIXTURE", "case_fixture_cement_published", "industrial_cement", "capacity_expansion"),
        _published_case("SALES-FIXTURE", "case_fixture_sales_published", "sales_led_expansion", "branch_channel_sales_led"),
    ]
    if validate_published_alpha_set(positive) != []:
        _fail("symbol-agnostic distinct published fixture should pass")

    duplicate_ticker = copy.deepcopy(positive)
    duplicate_ticker[2]["symbol"] = duplicate_ticker[0]["symbol"]
    if "published Alpha cases must use three distinct tickers" not in validate_published_alpha_set(duplicate_ticker):
        _fail("duplicate ticker published fixture was accepted")

    duplicate_case_id = copy.deepcopy(positive)
    duplicate_case_id[2]["case_id"] = duplicate_case_id[1]["case_id"]
    if "published Alpha cases must use three distinct case IDs" not in validate_published_alpha_set(duplicate_case_id):
        _fail("duplicate case_id published fixture was accepted")

    observed_sales = copy.deepcopy(positive)
    observed_sales[2]["status"] = "Observed"
    if "sales_led: case must be Published for the Alpha published set" not in validate_published_alpha_set(observed_sales):
        _fail("Observed sales-led fixture was accepted as published")

    unknown_sales = copy.deepcopy(positive)
    unknown_sales[2]["case_family"] = "ai_data_centre"
    unknown_sales[2]["case_type"] = "campus_launch"
    if "sales_led: required lane missing" not in validate_published_alpha_set(unknown_sales):
        _fail("non-sales-labelled fixture was accepted into the sales-led lane")


def main() -> int:
    state = load_json(INTELLIGENCE_CASES, {})
    receipt = load_json(CNERGY_RECEIPT, {})
    if not state or state.get("schema_version") != 1:
        _fail("current intelligence-case state is missing or has an unexpected schema")
    if state.get("summary", {}).get("published_case_count") != 0:
        _fail("current retained state unexpectedly contains published IntelligenceCases")

    _assert_current_mari_sky47_cannot_count(state)
    _assert_current_cnergy_lead_non_promoted(state, receipt)
    _assert_distinct_published_fixtures()
    print("distinct golden case lanes: PASS (3 lanes require distinct published tickers/case IDs; CNERGY remains unpromoted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
