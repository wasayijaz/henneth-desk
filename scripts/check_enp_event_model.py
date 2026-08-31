"""Golden, boundary, determinism and language checks for the E&P event model."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import enp_event_contract as contract
import enp_event_engine as engine

PASSED: list[str] = []

ENVELOPE_KEYS = [
    "schema_version",
    "formula_id",
    "engine_version",
    "run_receipt",
    "status",
    "blocked_reasons",
    "scenario",
    "inputs_lineage",
    "quarterly_schedule",
    "outcome_class",
    "values",
    "per_share",
    "probabilities",
    "confidence_limitations",
]
ROW_KEYS = [
    "quarter_end",
    "phase",
    "production_boe",
    "gross_revenue_pkr",
    "royalty_pkr",
    "opex_pkr",
    "tax_pkr",
    "net_cash_flow_pkr",
    "discount_factor",
    "discounted_cash_flow_pkr",
]


def fail(message: str) -> None:
    raise AssertionError(message)


def check(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        fail(f"{name}: {detail}" if detail else name)
    PASSED.append(name)


def close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def assert_clean_language(data, label: str) -> None:
    text = json.dumps(data, sort_keys=True).lower()
    for phrase in ("buy", "sell", "accumulate", "target price", "price target", "you should"):
        if phrase in text:
            fail(f"{label}: advice language leaked: {phrase}")


def assert_finite(data, label: str) -> None:
    for key, value in walk(data):
        if isinstance(value, float) and not math.isfinite(value):
            fail(f"{label}: non-finite number at {key}")


def analyst_record(value, note="golden fixture assumption"):
    return {
        "value": value,
        "label_type": "analyst",
        "analyst_ref": {"note_id": "note:enp:golden:0001", "note": note},
        "available_on": "2025-12-01",
    }


def golden_case() -> dict:
    return {
        "symbol": "MARI",
        "event_ref": "evt_3d1dae7553f73da60ba3",
        "case_label": "base",
        "effective_date": "2025-11-13",
        "valuation_date": "2025-12-31",
        "inputs": {
            "working_interest_pct": analyst_record(50.0),
            "consideration_pkr": analyst_record(1.0e8),
            "consideration_non_recoverable": analyst_record(True),
            "consideration_quarter_end": analyst_record("2025-12-31"),
            "spend_schedule": analyst_record([
                {"quarter_end": "2025-12-31", "phase": "exploration", "amount_pkr": 1.0e9},
                {"quarter_end": "2026-03-31", "phase": "appraisal", "amount_pkr": 5.0e8},
                {"quarter_end": "2026-06-30", "phase": "development", "amount_pkr": 3.0e9},
            ]),
            "first_production_quarter_end": analyst_record("2026-09-30"),
            "production_horizon_quarters": analyst_record(4),
            "initial_production_boe_pd": analyst_record(1000.0),
            "quarterly_decline_pct": analyst_record(0.0),
            "oil_share_pct": analyst_record(100.0),
            "oil_price_usd_bbl": analyst_record(70.0),
            "gas_price_usd_mmbtu": analyst_record(4.0),
            "gas_mmbtu_per_boe": analyst_record(5.8),
            "fx_pkr_usd": analyst_record(280.0),
            "opex_usd_boe": analyst_record(12.0),
            "royalty_pct": analyst_record(10.0),
            "effective_tax_pct": analyst_record(30.0),
            "discount_rate_pct_annual": analyst_record(12.0),
            "geological_success_pct": analyst_record(25.0),
            "commercial_success_pct": analyst_record(60.0),
            "operator_status": analyst_record("operator"),
            "shares_out": analyst_record(1000.0),
        },
    }


BOUNDARY_MUTATIONS = [
    ("missing working_interest_pct",
     lambda c: c["inputs"].pop("working_interest_pct"),
     "working_interest_pct: missing required input"),
    ("boolean as number",
     lambda c: c["inputs"]["working_interest_pct"].update(value=True),
     "must be a finite number"),
    ("NaN input",
     lambda c: c["inputs"]["working_interest_pct"].update(value=float("nan")),
     "must be a finite number"),
    ("infinite input",
     lambda c: c["inputs"]["working_interest_pct"].update(value=float("inf")),
     "must be a finite number"),
    ("working_interest_pct 0",
     lambda c: c["inputs"]["working_interest_pct"].update(value=0.0),
     "working_interest_pct: must be in (0, 100]"),
    ("working_interest_pct 101",
     lambda c: c["inputs"]["working_interest_pct"].update(value=101.0),
     "working_interest_pct: must be in (0, 100]"),
    ("geological_success_pct 0",
     lambda c: c["inputs"]["geological_success_pct"].update(value=0.0),
     "geological_success_pct: must be in (0, 100]"),
    ("commercial_success_pct 101",
     lambda c: c["inputs"]["commercial_success_pct"].update(value=101.0),
     "commercial_success_pct: must be in (0, 100]"),
    ("oil_share_pct 150",
     lambda c: c["inputs"]["oil_share_pct"].update(value=150.0),
     "oil_share_pct: must be in [0, 100]"),
    ("quarterly_decline_pct 100",
     lambda c: c["inputs"]["quarterly_decline_pct"].update(value=100.0),
     "quarterly_decline_pct: must be in [0, 100)"),
    ("discount rate 0",
     lambda c: c["inputs"]["discount_rate_pct_annual"].update(value=0.0),
     "discount_rate_pct_annual: must be in (0, 100)"),
    ("discount rate 101",
     lambda c: c["inputs"]["discount_rate_pct_annual"].update(value=101.0),
     "discount_rate_pct_annual: must be in (0, 100)"),
    ("royalty_pct 100",
     lambda c: c["inputs"]["royalty_pct"].update(value=100.0),
     "royalty_pct: must be in [0, 100)"),
    ("effective_tax_pct 100",
     lambda c: c["inputs"]["effective_tax_pct"].update(value=100.0),
     "effective_tax_pct: must be in [0, 100)"),
    ("malformed effective_date",
     lambda c: c.update(effective_date="2025-13-01"),
     "effective_date: must be an ISO date"),
    ("malformed valuation_date",
     lambda c: c.update(valuation_date="31-12-2025"),
     "valuation_date: must be an ISO date"),
    ("effective_date after valuation_date",
     lambda c: c.update(effective_date="2026-01-15"),
     "effective_date: must be on or before valuation_date"),
    ("production before effective_date",
     lambda c: c["inputs"]["first_production_quarter_end"].update(value="2025-09-30"),
     "first_production_quarter_end: must be after effective_date"),
    ("non-quarter-end production date",
     lambda c: c["inputs"]["first_production_quarter_end"].update(value="2026-09-15"),
     "first_production_quarter_end: must be a quarter-end"),
    ("negative spend amount",
     lambda c: c["inputs"]["spend_schedule"]["value"][0].update(amount_pkr=-1.0),
     "spend_schedule[0].amount_pkr: must be >= 0"),
    ("spend quarter before effective_date",
     lambda c: c["inputs"]["spend_schedule"]["value"][0].update(quarter_end="2025-09-30"),
     "spend_schedule[0].quarter_end: must be on or after effective_date"),
    ("invalid spend phase",
     lambda c: c["inputs"]["spend_schedule"]["value"][0].update(phase="gambit"),
     "spend_schedule[0].phase: must be one of exploration, appraisal, development"),
    ("empty spend schedule",
     lambda c: c["inputs"]["spend_schedule"].update(value=[]),
     "spend_schedule: must be a non-empty list of spend rows"),
    ("missing spend schedule",
     lambda c: c["inputs"].pop("spend_schedule"),
     "spend_schedule: missing required input"),
    ("consideration without quarter_end",
     lambda c: c["inputs"].pop("consideration_quarter_end"),
     "consideration_quarter_end: required when consideration_pkr > 0"),
    ("consideration without recoverable flag",
     lambda c: c["inputs"].pop("consideration_non_recoverable"),
     "consideration_non_recoverable: required when consideration_pkr > 0"),
    ("consideration quarter before effective_date",
     lambda c: c["inputs"]["consideration_quarter_end"].update(value="2025-09-30"),
     "consideration_quarter_end: must be on or after effective_date"),
    ("consideration flag not boolean",
     lambda c: c["inputs"]["consideration_non_recoverable"].update(value="yes"),
     "consideration_non_recoverable: must be a boolean"),
    ("shares_out zero",
     lambda c: c["inputs"]["shares_out"].update(value=0.0),
     "shares_out: must be > 0"),
    ("production horizon zero",
     lambda c: c["inputs"]["production_horizon_quarters"].update(value=0),
     "production_horizon_quarters: must be an integer >= 1"),
    ("production horizon fractional",
     lambda c: c["inputs"]["production_horizon_quarters"].update(value=2.5),
     "production_horizon_quarters: must be an integer >= 1"),
    ("production horizon boolean",
     lambda c: c["inputs"]["production_horizon_quarters"].update(value=True),
     "production_horizon_quarters: must be an integer >= 1"),
    ("unknown label_type",
     lambda c: c["inputs"]["working_interest_pct"].update(label_type="guess"),
     "provenance record must carry label_type"),
    ("source_ref without url or path",
     lambda c: c["inputs"]["working_interest_pct"].update(
         label_type="source",
         source_ref={"id": "psx:265594", "label": "Material Information"}),
     "provenance record must carry label_type"),
    ("analyst_ref without note",
     lambda c: c["inputs"]["working_interest_pct"].update(
         label_type="analyst",
         analyst_ref={"note_id": "note:enp:1"}),
     "provenance record must carry label_type"),
    ("available_on after valuation_date",
     lambda c: c["inputs"]["working_interest_pct"].update(available_on="2026-06-30"),
     "available_on must be on or before valuation_date"),
    ("market_gap_pkr NaN",
     lambda c: c["inputs"].update(market_gap_pkr=analyst_record(float("nan"))),
     "market_gap_pkr: must be a finite number"),
    ("non-JSON-serializable input",
     lambda c: c["inputs"].update(weird_field={"value": {1, 2}}),
     "JSON-serializable"),
    ("invalid case_label",
     lambda c: c.update(case_label="ultra"),
     "case_label: must be one of bear, base, bull"),
]


def main() -> None:
    check("contract version", contract.CONTRACT_VERSION == "enp_event_contract_v1")
    check("engine ids",
          engine.FORMULA_ID == "enp_exploration.risked_cashflow.v1"
          and engine.ENGINE_VERSION == "enp_event_engine_v1"
          and engine.RESULT_SCHEMA == "enp_event_model_result_v1")

    source_ok = {
        "label_type": "source",
        "source_ref": {
            "id": "psx:265594",
            "label": "Material Information",
            "path": "state/company_intel/operating_events.json",
        },
    }
    check("provenance accepts source with path", contract.provenance_ok(source_ok))
    check("provenance accepts analyst note",
          contract.provenance_ok(analyst_record(50.0)))
    check("provenance rejects unknown label",
          not contract.provenance_ok({"label_type": "guess"}))
    check("provenance rejects source without locator",
          not contract.provenance_ok({"label_type": "source",
                                      "source_ref": {"id": "x", "label": "y"}}))
    check("provenance rejects analyst without note",
          not contract.provenance_ok({"label_type": "analyst",
                                      "analyst_ref": {"note_id": "n"}}))

    case = golden_case()
    check("golden case validates", contract.validate_case(case) == [])
    result = engine.evaluate_case(case)
    check("envelope keys exact", sorted(result) == sorted(ENVELOPE_KEYS))
    check("envelope ids wired",
          result["schema_version"] == engine.RESULT_SCHEMA
          and result["formula_id"] == engine.FORMULA_ID
          and result["engine_version"] == engine.ENGINE_VERSION
          and result["run_receipt"]["contract_version"] == contract.CONTRACT_VERSION)
    canonical = json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    expected_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    check("inputs hash matches canonical sha256",
          result["run_receipt"]["inputs_sha256"] == expected_digest)

    lineage_fields = [entry["field"] for entry in result["inputs_lineage"]]
    check("lineage covers every input sorted", lineage_fields == sorted(case["inputs"]))
    check("lineage carries provenance and no lookahead",
          all(entry["label_type"] == "analyst" and "analyst_ref" in entry
              and entry["available_on"] <= case["valuation_date"]
              for entry in result["inputs_lineage"]))

    schedule = result["quarterly_schedule"]
    check("schedule shape",
          len(schedule) == 8 and all(sorted(row) == sorted(ROW_KEYS) for row in schedule))
    check("schedule sorted by quarter then phase",
          schedule == sorted(schedule, key=lambda row: (row["quarter_end"], row["phase"])))
    exploration = next(r for r in schedule if r["phase"] == "exploration")
    consideration = next(r for r in schedule if r["phase"] == "consideration")
    check("valuation-date row undiscounted",
          exploration["quarter_end"] == "2025-12-31" and exploration["discount_factor"] == 1.0)
    check("consideration row is a cost",
          consideration["net_cash_flow_pkr"] == -1.0e8
          and consideration["production_boe"] is None)

    production_rows = [r for r in schedule if r["phase"] == "production"]
    q3_2026 = production_rows[0]
    check("q3-2026 production boe", close(q3_2026["production_boe"], 92_000.0))
    check("q3-2026 gross revenue pkr", close(q3_2026["gross_revenue_pkr"], 901_600_000.0))
    check("q3-2026 royalty pkr", close(q3_2026["royalty_pkr"], 90_160_000.0))
    check("q3-2026 opex pkr", close(q3_2026["opex_pkr"], 154_560_000.0))
    check("q3-2026 tax pkr", close(q3_2026["tax_pkr"], 197_064_000.0))
    check("q3-2026 net cash flow pkr", close(q3_2026["net_cash_flow_pkr"], 459_816_000.0))
    check("q3-2026 discounted row",
          close(q3_2026["discounted_cash_flow_pkr"],
                q3_2026["net_cash_flow_pkr"] * q3_2026["discount_factor"]))
    check("calendar-day quarters",
          [r["production_boe"] for r in production_rows]
          == [92_000.0, 92_000.0, 90_000.0, 91_000.0])
    check("horizon production total",
          close(sum(r["production_boe"] for r in production_rows), 365_000.0))

    values = result["values"]
    p_success = values["p_success_pct"] / 100.0
    risked_recomputed = (p_success * values["unrisked_commercial_npv_pkr"]
                         + (1.0 - p_success) * values["dry_hole_npv_pkr"])
    check("p_success is geo times commercial", close(values["p_success_pct"], 15.0))
    check("risked identity from components",
          close(values["risked_npv_pkr"], risked_recomputed))
    commercial_total = math.fsum(r["discounted_cash_flow_pkr"] for r in schedule)
    dry_total = math.fsum(r["discounted_cash_flow_pkr"] for r in schedule
                          if r["phase"] in ("exploration", "appraisal", "consideration"))
    check("commercial npv is whole schedule",
          close(values["unrisked_commercial_npv_pkr"], commercial_total))
    check("dry hole npv is exploration appraisal consideration",
          close(values["dry_hole_npv_pkr"], dry_total))
    check("outcome class computed not dry_hole",
          result["outcome_class"] in ("commercial", "non_commercial"))
    check("per share derived from values",
          close(result["per_share"]["risked_pkr"], values["risked_npv_pkr"] / 1000.0)
          and close(result["per_share"]["unrisked_pkr"],
                    values["unrisked_commercial_npv_pkr"] / 1000.0))
    check("market gap missing reported",
          result["probabilities"]["market_implied_success_pct"] is None
          and result["probabilities"]["market_implied_missing"] == ["market_gap_pkr"])

    gap_case = copy.deepcopy(case)
    gap = (values["dry_hole_npv_pkr"]
           + 0.4 * (values["unrisked_commercial_npv_pkr"] - values["dry_hole_npv_pkr"]))
    gap_case["inputs"]["market_gap_pkr"] = analyst_record(gap)
    gap_result = engine.evaluate_case(gap_case)
    check("market-implied success 40 pct",
          close(gap_result["probabilities"]["market_implied_success_pct"], 40.0))
    check("market-implied in range has no note",
          "market_implied_note" not in gap_result["probabilities"])

    be_pct, be_note = engine.break_even_success(5.0e9, -2.0e9)
    be = be_pct / 100.0
    check("break-even round trip",
          be_pct is not None and be_note is None
          and abs(be * 5.0e9 + (1.0 - be) * -2.0e9) < 1.0)
    check("break-even degenerate spread",
          engine.break_even_success(1.0e9, 1.0e9)
          == (None, "degenerate spread between commercial and dry-hole outcomes"))
    check("golden break-even documented as unavailable",
          result["probabilities"]["break_even_success_pct"] is None
          and result["probabilities"]["break_even_note"] is not None)

    repeat = engine.evaluate_case(case)
    check("same object evaluates identically",
          json.dumps(repeat, sort_keys=True) == json.dumps(result, sort_keys=True))
    copy_result = engine.evaluate_case(copy.deepcopy(case))
    check("deepcopy evaluates identically",
          json.dumps(copy_result, sort_keys=True) == json.dumps(result, sort_keys=True))
    frozen_dump = json.dumps(result, sort_keys=True)
    case["inputs"]["fx_pkr_usd"]["value"] = 279.0
    check("earlier envelope unaffected by later mutation", json.dumps(result, sort_keys=True) == frozen_dump)
    mutated_result = engine.evaluate_case(case)
    fx_lineage = next(e for e in mutated_result["inputs_lineage"] if e["field"] == "fx_pkr_usd")
    check("mutation changes hash and lineage",
          mutated_result["run_receipt"]["inputs_sha256"] != result["run_receipt"]["inputs_sha256"]
          and fx_lineage["value"] == 279.0)

    for name, mutate, expected in BOUNDARY_MUTATIONS:
        boundary_case = golden_case()
        mutate(boundary_case)
        violations = contract.validate_case(boundary_case)
        check(f"boundary: {name}", any(expected in v for v in violations),
              f"expected fragment {expected!r} in {violations!r}")
    try:
        engine.evaluate_case({"symbol": "MARI"})
        fail("evaluate_case must raise on invalid input")
    except ValueError as error:
        check("evaluate joins violations with named fields",
              "; " in str(error) and "case_label" in str(error) and "effective_date" in str(error))
    try:
        engine.quarterly_cashflows(golden_case() | {"symbol": ""})
        fail("quarterly_cashflows must raise on invalid input")
    except ValueError:
        check("quarterly_cashflows validates first", True)

    blocked = engine.blocked_result(golden_case(), ["second reason", "first reason", "first reason"])
    check("blocked envelope keys", sorted(blocked) == sorted(ENVELOPE_KEYS))
    check("blocked carries no partial numbers",
          blocked["status"] == "blocked"
          and blocked["values"] is None
          and blocked["per_share"] is None
          and blocked["probabilities"] is None
          and blocked["quarterly_schedule"] == []
          and blocked["inputs_lineage"] == []
          and blocked["run_receipt"]["inputs_sha256"] is None)
    check("blocked reasons deduped and sorted",
          blocked["blocked_reasons"] == ["first reason", "second reason"])

    for module in (contract, engine):
        for symbol in ("open", "save_json", "load_json", "write"):
            check(f"no file-io symbol {module.__name__}.{symbol}",
                  not hasattr(module, symbol))

    for label, payload in (("computed", gap_result), ("blocked", blocked)):
        assert_clean_language(payload, label)
        assert_finite(payload, label)
    check("language and finite scans on envelopes", True)

    print(f"enp event model: PASS ({len(PASSED)} checks)")


if __name__ == "__main__":
    main()
