"""Focused checks for Historical Analogue Availability Audit."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_historical_analogue_availability_audit as builder
from ci_checker_helpers import without_root_meta
from psx_data import STATE, load_json


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _fail(message: str) -> None:
    raise AssertionError(message)


def _check_no_advice_or_forecast_leak(payload: dict) -> None:
    text = _dump(payload).lower()
    banned = (
        "you should buy",
        "you should sell",
        "price target",
        "target price",
        "forecasted return",
        "predicted return",
        "caused the return",
    )
    for phrase in banned:
        if re.search(r"\b" + re.escape(phrase) + r"\b", text):
            _fail(f"disallowed advice/forecast phrase leaked: {phrase}")


def _assert_no_lookahead(audit: dict) -> None:
    for case_audit in audit.get("cases") or []:
        target_info = (case_audit.get("target_event") or {}).get("information_available_at") or (case_audit.get("target_event") or {}).get("effective_date")
        target_date = builder._parse_date(target_info)
        if not target_date:
            _fail(f"{case_audit.get('case_id')}: target cutoff date missing")
        for cand in (case_audit.get("tier_1_candidates") or []) + (case_audit.get("tier_2_candidates") or []):
            cand_date = builder._parse_date(cand.get("effective_date"))
            if not cand_date:
                _fail(f"{case_audit.get('case_id')}: candidate {cand.get('event_id')} has no valid date")
            if cand_date >= target_date:
                _fail(f"{case_audit.get('case_id')}: lookahead violation - candidate date {cand_date} >= target date {target_date}")


def _assert_sample_suppression_and_integrity(audit: dict) -> None:
    summary = audit.get("summary") or {}
    if summary.get("audited_case_count") != 4:
        _fail("must audit exactly 4 Alpha cases")
    if summary.get("cases_with_sufficient_sample_for_stats") != 0:
        _fail("all 4 cases currently have thin sample N < 3; stats must remain suppressed")

    for case_audit in audit.get("cases") or []:
        avail = case_audit.get("analogue_availability") or {}
        t1_count = avail.get("tier_1_exact_count", 0)
        if t1_count < 3 and avail.get("sample_sufficient_for_stats") is not False:
            _fail(f"{case_audit.get('case_id')}: sample_sufficient_for_stats must be False when N < 3")
        for cand in case_audit.get("tier_1_candidates") or []:
            if cand.get("scenario_calibrating") is not False:
                _fail(f"{case_audit.get('case_id')}: candidate {cand.get('event_id')} cannot calibrate scenarios without N >= 3")
            if not cand.get("source_document_id"):
                _fail(f"{case_audit.get('case_id')}: candidate {cand.get('event_id')} missing source document ID")


def _assert_pso_information_cutoff_integrity(audit: dict) -> None:
    pso_case = next((c for c in (audit.get("cases") or []) if c.get("symbol") == "PSO"), None)
    if not pso_case:
        _fail("PSO case missing in audit")
    target = pso_case.get("target_event") or {}
    if target.get("effective_date") != "2025-06-30":
        _fail("PSO effective_date must be 2025-06-30 (FY25 period end)")
    if target.get("information_available_at") != "2025-10-02":
        _fail("PSO information_available_at must be 2025-10-02 (annual report publication)")


def _fixture_banned_phrases_regression() -> None:
    for banned_phrase in ("price target", "you should buy", "forecasted return", "target price"):
        caught = False
        try:
            _check_no_advice_or_forecast_leak({"leak": f"Here is the {banned_phrase} for this stock"})
        except AssertionError:
            caught = True
        if not caught:
            _fail(f"Banned phrase checker failed to catch: {banned_phrase}")


def main() -> None:
    path = builder.OUT
    if not path.exists():
        _fail("historical_analogue_availability_audit.json is missing")
    state = load_json(path, {})
    rebuilt = builder.build(write=False)
    if _dump(without_root_meta(state)) != _dump(without_root_meta(rebuilt)):
        _fail("historical analogue availability audit rebuild is not deterministic")
    if state.get("schema_version") != 1 or state.get("product_version") != builder.PRODUCT_VERSION:
        _fail("schema/version mismatch")
    if state.get("kind") != "historical_analogue_availability_audit":
        _fail("kind mismatch")

    _check_no_advice_or_forecast_leak(state)
    _fixture_banned_phrases_regression()
    _assert_no_lookahead(state)
    _assert_sample_suppression_and_integrity(state)
    _assert_pso_information_cutoff_integrity(state)

    print(f"historical_analogue_availability: PASS ({len(state.get('cases', []))} Alpha cases audited)")


if __name__ == "__main__":
    main()
