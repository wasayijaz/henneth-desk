"""Focused checks for the MARI E&P case-run adapter."""
from __future__ import annotations

import copy
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import enp_event_engine
import mari_enp_case_run_adapter as adapter
import mari_enp_case_run_contract as contract


PASSED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"{name}: {detail}" if detail else name)
    PASSED += 1


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def assert_clean(data, label: str) -> None:
    text = json.dumps(data, sort_keys=True, allow_nan=False).lower()
    for phrase in ("buy", "sell", "accumulate", "target price", "price target", "you should"):
        check(f"{label} no advice phrase {phrase}", phrase not in text)
    for key, value in walk(data):
        if isinstance(value, float):
            check(f"{label} finite {key}", math.isfinite(value))


def main() -> None:
    root = Path(__file__).resolve().parents[1]

    real = adapter.build_retained_case_run(root)
    check("real envelope validates", contract.validate_envelope(real) == [])
    check("real identity",
          real["schema_version"] == contract.SCHEMA_VERSION
          and real["adapter_version"] == contract.ADAPTER_VERSION
          and real["case_id"] == "case_mari_offshore_exploration_blocks_observed_v1"
          and real["symbol"] == "MARI"
          and real["case_family"] == "e_and_p")
    check("real path blocked and not fixture", real["status"] == "blocked" and real["fixture_only"] is False)
    check("scenario labels exact",
          [row["case_label"] for row in real["scenario_runs"]] == ["bear", "base", "bull"])
    check("real scenario runs blocked with zero numeric outputs",
          all(
              row["status"] == "blocked"
              and row["fixture_only"] is False
              and row["input_sha256"] is None
              and row["input_fields"] == []
              and row["quarterly_schedule_rows"] == 0
              and row["values"] is None
              and row["per_share"] is None
              and row["probabilities"] is None
              for row in real["scenario_runs"]
          ))
    for reason in (
        "no_model_ready_E_and_P_operands",
        "annual_history_incomplete_or_audit_only",
        "quarterly_history_not_retained_as_model_ready",
        "share_count_is_metadata_lead_only",
    ):
        check(f"real blocked reason {reason}", reason in real["blocked_reasons"])
    check("real financial truth blocker exact",
          any(reason.startswith("financial_truth_not_qualified: requires five qualified annual income triplets")
              for reason in real["blocked_reasons"]))
    check("real formal products blocked",
          {row["product"]: row["blocked_reason"] for row in real["formal_output_readiness"]["products"]}
          == {
              "financial_forecasts": "missing_source_gated_inputs",
              "formal_valuations": "missing_source_gated_inputs",
              "market_expectations": "missing_source_gated_inputs",
          })
    check("real analogue readiness suppressed",
          real["analogue_readiness"]["target_event_id"] == adapter.EVENT_ID
          and real["analogue_readiness"]["readiness_status"] == "needs_more_mature_outcomes"
          and real["analogue_readiness"]["aggregate_ready_horizons"] == []
          and "3 additional mature strict prior exact analogue" in real["analogue_readiness"]["next_required_evidence"])
    source_rows = [row for row in real["input_lineage"] if row["label_type"] == "source"]
    missing_rows = [row for row in real["input_lineage"] if row["label_type"] == "missing"]
    check("real source lineage retained",
          {row["source_ref"]["id"] for row in source_rows if row["source_ref"]}
          == {"psx:260446", "psx:265594"})
    check("real missing operand lineage",
          "working_interest_pct" in {row["field"] for row in missing_rows}
          and "consideration_pkr" in {row["field"] for row in missing_rows}
          and all(row["value"] is None for row in missing_rows))
    check("real policy gates",
          all(real["policy"].values())
          and real["formal_output_readiness"]["financial_truth_status"] == "not_qualified")

    fixture = adapter.build_synthetic_fixture_case_run()
    check("fixture envelope validates", contract.validate_envelope(fixture) == [])
    check("fixture status unmistakable",
          fixture["status"] == "computed_fixture" and fixture["fixture_only"] is True
          and fixture["blocked_reasons"] == [])
    check("fixture scenario labels exact",
          [row["case_label"] for row in fixture["scenario_runs"]] == ["bear", "base", "bull"])
    check("fixture runs computed by existing engine",
          all(row["status"] == "computed"
              and row["fixture_only"] is True
              and row["engine_version"] == enp_event_engine.ENGINE_VERSION
              and row["formula_id"] == enp_event_engine.FORMULA_ID
              and isinstance(row["input_sha256"], str)
              and re.fullmatch(r"[0-9a-f]{64}", row["input_sha256"])
              for row in fixture["scenario_runs"]))
    check("fixture all runs have values and schedules",
          all(row["values"] and row["probabilities"] and row["quarterly_schedule_rows"] > 0
              for row in fixture["scenario_runs"]))
    check("fixture labels produce distinct receipts",
          len({row["input_sha256"] for row in fixture["scenario_runs"]}) == 3)
    check("fixture contains analyst provenance for every input",
          len(fixture["input_lineage"]) == 3 * 19
          and all(row["label_type"] == "analyst"
                  and row["status"] == "fixture_only"
                  and row["analyst_ref"]["note"].startswith("synthetic_fixture_only_")
                  for row in fixture["input_lineage"]))
    check("fixture does not activate formal outputs",
          fixture["formal_output_readiness"]["status"] == "blocked_fixture_only"
          and {row["blocked_reason"] for row in fixture["formal_output_readiness"]["products"]}
          == {"fixture_output_not_formal_output"})
    check("fixture analogue boundary",
          fixture["analogue_readiness"]["status"] == "fixture_not_real_analogue_evidence"
          and fixture["analogue_readiness"]["blocked_states"]["real_case"] == "not_activated_by_fixture")

    repeat_real = adapter.build_retained_case_run(root)
    repeat_fixture = adapter.build_synthetic_fixture_case_run()
    check("real deterministic", json.dumps(real, sort_keys=True) == json.dumps(repeat_real, sort_keys=True))
    check("fixture deterministic", json.dumps(fixture, sort_keys=True) == json.dumps(repeat_fixture, sort_keys=True))
    frozen = json.dumps(fixture, sort_keys=True)
    mutated = copy.deepcopy(fixture)
    mutated["scenario_runs"][0]["values"]["risked_npv_pkr"] += 1.0
    check("mutation changes copied fixture only", json.dumps(fixture, sort_keys=True) == frozen
          and json.dumps(mutated, sort_keys=True) != frozen)

    bad_envelope = copy.deepcopy(real)
    bad_envelope["extra"] = True
    check("contract rejects unknown envelope field",
          "envelope.extra: unknown field" in contract.validate_envelope(bad_envelope))
    bad_run = copy.deepcopy(fixture)
    bad_run["scenario_runs"][0]["extra"] = True
    check("contract rejects unknown run field",
          any("scenario_runs[0].extra: unknown field" == violation
              for violation in contract.validate_envelope(bad_run)))
    bad_lineage = copy.deepcopy(real)
    bad_lineage["input_lineage"][0]["extra"] = True
    check("contract rejects unknown lineage field",
          any("input_lineage[0].extra: unknown field" == violation
              for violation in contract.validate_envelope(bad_lineage)))
    bad_nan = copy.deepcopy(fixture)
    bad_nan["scenario_runs"][0]["values"]["risked_npv_pkr"] = float("nan")
    check("contract rejects nonfinite output",
          any("must be JSON-serializable and finite" in violation
              for violation in contract.validate_envelope(bad_nan)))
    bad_phrase = copy.deepcopy(real)
    bad_phrase["blocked_reasons"] = ["target price leak"]
    check("contract rejects target-price leakage",
          any("target-price phrase leaked" in violation
              for violation in contract.validate_envelope(bad_phrase)))
    bad_real = copy.deepcopy(real)
    bad_real["scenario_runs"][0]["values"] = {"risked_npv_pkr": 1.0}
    check("contract rejects real numeric activation",
          any("retained blocked run must carry zero numeric outputs" in violation
              for violation in contract.validate_envelope(bad_real)))
    bad_case = adapter._synthetic_case("base")
    bad_case["inputs"]["surprise_field"] = adapter._analyst(1.0, "synthetic_fixture_only_bad")
    check("strict engine-case wrapper rejects unknown input",
          "surprise_field: unknown E&P input field" in contract.validate_engine_case(bad_case))
    bad_case2 = adapter._synthetic_case("base")
    bad_case2["inputs"]["working_interest_pct"]["value"] = float("inf")
    check("strict engine-case wrapper rejects nonfinite input",
          any("working_interest_pct: must be a finite number" in violation
              for violation in contract.validate_engine_case(bad_case2)))
    bad_case3 = adapter._synthetic_case("base")
    bad_case3["inputs"]["working_interest_pct"]["available_on"] = "2026-01-01"
    check("strict engine-case wrapper rejects lookahead input",
          any("working_interest_pct: available_on must be on or before valuation_date" in violation
              for violation in contract.validate_engine_case(bad_case3)))

    assert_clean(real, "real")
    assert_clean(fixture, "fixture")
    print(f"MARI ENP case-run adapter: PASS ({PASSED} checks)")


if __name__ == "__main__":
    main()
