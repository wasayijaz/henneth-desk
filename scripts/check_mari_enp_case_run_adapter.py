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
              and row["quarterly_schedule"] == []
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
          == {"psx:265594"}
          and all(row["source_ref"]["event_id"] == adapter.EVENT_ID for row in source_rows))
    check("real missing operand lineage",
          "working_interest_pct" in {row["field"] for row in missing_rows}
          and "consideration_pkr" in {row["field"] for row in missing_rows}
          and "operator_status" in {row["field"] for row in missing_rows}
          and all(row["value"] is None and row["source_ref"] is None for row in missing_rows))
    check("real target operand lineage",
          [row["field"] for row in real["input_lineage"]
           if row["scope"] == "retained_ep_operand" and row["label_type"] == "source"] == ["block_identity"]
          and next(row for row in real["input_lineage"] if row["field"] == "block_identity")["source_ref"]["id"] == "psx:265594")
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
    check("fixture schedule rows exact",
          all(row["quarterly_schedule_rows"] == 8 and len(row["quarterly_schedule"]) == 8
              for row in fixture["scenario_runs"]))
    check("fixture schedule identities",
          all([item["phase"] for item in row["quarterly_schedule"]]
              == ["exploration", "appraisal", "production", "production", "production", "production", "production", "production"]
              for row in fixture["scenario_runs"]))
    check("fixture schedule row shape",
          all(set(item) == {
              "quarter_end", "phase", "production_boe", "gross_revenue_pkr", "royalty_pkr",
              "opex_pkr", "tax_pkr", "net_cash_flow_pkr", "discount_factor",
              "discounted_cash_flow_pkr",
          }
              for row in fixture["scenario_runs"]
              for item in row["quarterly_schedule"]))
    check("fixture labels produce distinct receipts",
          len({row["input_sha256"] for row in fixture["scenario_runs"]}) == 3)
    check("fixture input fields include hardened kernel requirements",
          all("operator_status" in row["input_fields"] and "shares_out" in row["input_fields"]
              for row in fixture["scenario_runs"]))
    check("fixture contains analyst provenance for every input",
          len(fixture["input_lineage"]) == 3 * 20
          and all(row["label_type"] == "analyst"
                  and row["status"] == "fixture_only"
                  and row["analyst_ref"]["note"].startswith("synthetic_fixture_only_")
                  for row in fixture["input_lineage"]))
    fixture_operator_statuses = {
        row["case_label"]: row["value"]
        for row in fixture["input_lineage"]
        if row["field"] == "operator_status"
    }
    check("fixture operator statuses are explicit descriptive inputs",
          fixture_operator_statuses == {"bear": "operator", "base": "operator", "bull": "non_operator"})
    check("fixture receipt hashes pinned",
          {row["case_label"]: row["input_sha256"] for row in fixture["scenario_runs"]}
          == {
              "bear": "f1ec3bd18471b876bbc440123dde09bedc50e3d4d88b578886bbde1f48bf3652",
              "base": "cd44aad48e26b7dfb3069f836545da52c87f551d2af5c7b2cbe67b5b40990d9f",
              "bull": "705cc0095cbeb64133b16087e5b887fb80aab5c5a29d9ccdab5cb0b4061ae780",
          }
          and {row["case_label"]: row["fixture_hash"] for row in fixture["scenario_runs"]}
          == {
              "bear": "0a7d4787d77bb7fbaac12230d8c381e2fc27a352467e4a70c9f67947bfd23a2f",
              "base": "0a824a4d9f484c9c9144b2e981afa9ce44e92fcbe5e2587e25cd41af46911194",
              "bull": "46b93352efa4e21ab53e114645db09b620b11bf72701fde015e3f57151876a6a",
          })
    check("fixture does not activate formal outputs",
          fixture["formal_output_readiness"]["status"] == "blocked_fixture_only"
          and {row["blocked_reason"] for row in fixture["formal_output_readiness"]["products"]}
          == {"fixture_output_not_formal_output"})
    check("fixture analogue boundary",
          fixture["analogue_readiness"]["status"] == "fixture_not_real_analogue_evidence"
          and fixture["analogue_readiness"]["blocked_states"]["real_case"]["reason"] == "not_activated_by_fixture")

    repeat_real = adapter.build_retained_case_run(root)
    repeat_fixture = adapter.build_synthetic_fixture_case_run()
    check("real deterministic", json.dumps(real, sort_keys=True) == json.dumps(repeat_real, sort_keys=True))
    check("fixture deterministic", json.dumps(fixture, sort_keys=True) == json.dumps(repeat_fixture, sort_keys=True))
    frozen = json.dumps(fixture, sort_keys=True)
    mutated = copy.deepcopy(fixture)
    mutated["scenario_runs"][0]["values"]["risked_npv_pkr"] += 1.0
    check("mutation changes copied fixture only", json.dumps(fixture, sort_keys=True) == frozen
          and json.dumps(mutated, sort_keys=True) != frozen)
    operator_case = adapter._synthetic_case("base")
    operator_result = enp_event_engine.evaluate_case(operator_case)
    non_operator_case = copy.deepcopy(operator_case)
    non_operator_case["inputs"]["operator_status"]["value"] = "non_operator"
    non_operator_result = enp_event_engine.evaluate_case(non_operator_case)
    check("operator status changes receipt but not arithmetic",
          operator_result["run_receipt"]["inputs_sha256"] != non_operator_result["run_receipt"]["inputs_sha256"]
          and operator_result["values"] == non_operator_result["values"]
          and operator_result["per_share"] == non_operator_result["per_share"]
          and operator_result["probabilities"] == non_operator_result["probabilities"]
          and operator_result["quarterly_schedule"] == non_operator_result["quarterly_schedule"])

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

    missing_date = copy.deepcopy(real)
    missing_date["input_lineage"][0]["available_on"] = None
    check("contract rejects missing retained source date",
          any("source lineage requires a retained date" in violation
              for violation in contract.validate_envelope(missing_date)))
    arbitrary_source = copy.deepcopy(real)
    src = next(row for row in arbitrary_source["input_lineage"] if row["source_ref"])["source_ref"]
    src["id"] = "arbitrary-id"
    check("contract rejects arbitrary source ID",
          any("authoritative retained source receipt" in violation for violation in contract.validate_envelope(arbitrary_source)))
    correlated_unknown = copy.deepcopy(real)
    correlated_ref = next(row for row in correlated_unknown["input_lineage"] if row["source_ref"])["source_ref"]
    correlated_ref.update(id="psx:999999", url="https://dps.psx.com.pk/download/document/999999.pdf", page=7,
                          content_sha256="0" * 64, evidence_sha256="1" * 64)
    check("contract rejects fully correlated unknown source ID",
          any("authoritative retained source receipt" in violation
              for violation in contract.validate_envelope(correlated_unknown)))
    unknown_issuer = copy.deepcopy(real)
    unknown_ref = next(row for row in unknown_issuer["input_lineage"] if row["source_ref"])["source_ref"]
    unknown_ref["id"] = "issuer:" + "a" * 24
    check("contract rejects unknown issuer source ID",
          any("authoritative retained source receipt" in violation
              for violation in contract.validate_envelope(unknown_issuer)))
    for field, value in (("url", "https://evil.invalid/doc.pdf"), ("path", "forged/path.pdf"), ("page", 99), ("content_sha256", "0" * 64), ("evidence_sha256", "1" * 64), ("date", "2024-01-01")):
        forged = copy.deepcopy(real)
        source = next(row for row in forged["input_lineage"] if row["source_ref"])["source_ref"]
        source[field] = value
        check(f"contract rejects forged source {field}",
              contract.validate_envelope(forged) != [])
    swapped_operands = copy.deepcopy(real)
    block_row = next(row for row in swapped_operands["input_lineage"] if row["field"] == "block_identity")
    operator_row = next(row for row in swapped_operands["input_lineage"] if row["field"] == "operator_status")
    operator_row["label_type"] = "source"
    operator_row["value"] = "Peshawar Block as an Operator"
    operator_row["source_ref"] = copy.deepcopy(block_row["source_ref"])
    operator_row["available_on"] = block_row["available_on"]
    check("contract rejects operator source promotion",
          contract.validate_envelope(swapped_operands) != [])
    peshawar_operator = copy.deepcopy(real)
    peshawar_operator_row = next(row for row in peshawar_operator["input_lineage"] if row["field"] == "operator_status")
    peshawar_operator_row.update({
        "label_type": "source",
        "value": "Peshawar Block as an Operator",
        "available_on": "2025-11-13",
        "source_ref": {
            "id": "psx:260446",
            "label": "prior PSX event evidence",
            "url": "https://dps.psx.com.pk/download/document/260446.pdf",
            "page": 1,
            "content_sha256": "c13ccb4de58ad005bca106942721490593fe219ff45906c68280ea7856192e42",
            "evidence_sha256": "dd83c62cb781e2a57f5ae595a7184ea786a3e5890f7f7cc96cd93e23f958a177",
            "event_id": "evt_b25decfc180474cbe066",
            "date": "2025-11-13",
        },
    })
    check("contract rejects Peshawar operator injection",
          contract.validate_envelope(peshawar_operator) != [])
    peshawar_block = copy.deepcopy(real)
    peshawar_block_row = next(row for row in peshawar_block["input_lineage"] if row["field"] == "block_identity")
    peshawar_block_row["source_ref"]["id"] = "psx:260446"
    check("contract rejects Peshawar target-operand injection",
          contract.validate_envelope(peshawar_block) != [])
    peshawar_any_operand = copy.deepcopy(real)
    peshawar_any_row = next(row for row in peshawar_any_operand["input_lineage"] if row["field"] == "working_interest_pct")
    peshawar_any_row.update({
        "label_type": "source",
        "value": 25.0,
        "available_on": "2025-11-13",
        "source_ref": {
            "id": "psx:260446",
            "label": "prior PSX event evidence",
            "url": "https://dps.psx.com.pk/download/document/260446.pdf",
            "page": 1,
            "content_sha256": "c13ccb4de58ad005bca106942721490593fe219ff45906c68280ea7856192e42",
            "evidence_sha256": "dd83c62cb781e2a57f5ae595a7184ea786a3e5890f7f7cc96cd93e23f958a177",
            "event_id": "evt_b25decfc180474cbe066",
            "date": "2025-11-13",
        },
    })
    check("contract rejects Peshawar injection into any target operand",
          contract.validate_envelope(peshawar_any_operand) != [])
    cross_event = copy.deepcopy(real)
    cross_block = next(row for row in cross_event["input_lineage"] if row["field"] == "block_identity")
    cross_block["source_ref"]["event_id"] = "evt_b25decfc180474cbe066"
    check("contract rejects cross-event source binding",
          any("canonical MARI offshore target event" in violation
              for violation in contract.validate_envelope(cross_event)))
    duplicate_lineage = copy.deepcopy(real)
    duplicate_lineage["input_lineage"].append(copy.deepcopy(duplicate_lineage["input_lineage"][0]))
    check("contract rejects duplicate lineage row",
          any("duplicate lineage row" in violation
              for violation in contract.validate_envelope(duplicate_lineage)))
    duplicate_operand = copy.deepcopy(real)
    operand = next(row for row in duplicate_operand["input_lineage"] if row["scope"] == "retained_ep_operand")
    duplicate_operand["input_lineage"].append(copy.deepcopy(operand))
    check("contract rejects duplicate retained operand field",
          any("duplicate retained operand field" in violation
              for violation in contract.validate_envelope(duplicate_operand)))
    converted = copy.deepcopy(real)
    converted["status"] = "computed_fixture"
    converted["fixture_only"] = True
    converted["fixture_identity"] = {"id": contract._FIXTURE_ID, "spec_sha256": contract._FIXTURE_SPEC_SHA256}
    converted["scenario_runs"] = copy.deepcopy(fixture["scenario_runs"])
    check("contract rejects blocked-to-fixture conversion",
          contract.validate_envelope(converted) != [])

    adversarial = [
        ("invented values",
         lambda c: c["scenario_runs"][0].update(values={"invented": 123}),
         "values.invented: unknown field"),
        ("empty values",
         lambda c: c["scenario_runs"][0].update(values={}),
         "values.dry_hole_npv_pkr: missing required field"),
        ("made-up probabilities",
         lambda c: c["scenario_runs"][0].update(probabilities={"made_up": 999}),
         "probabilities.made_up: unknown field"),
        ("wrong row count",
         lambda c: c["scenario_runs"][0].update(quarterly_schedule_rows=1),
         "quarterly_schedule_rows: computed fixture must equal 8"),
        ("computed blocked reason",
         lambda c: c["scenario_runs"][0].update(blocked_reasons=["should_not_exist"]),
         "blocked_reasons: computed run must not carry blocked reasons"),
        ("empty input fields",
         lambda c: c["scenario_runs"][0].update(input_fields=[]),
         "input_fields: computed run must list the complete E&P fixture input fields"),
    ]
    for name, mutate, expected in adversarial:
        candidate = copy.deepcopy(fixture)
        mutate(candidate)
        violations = contract.validate_envelope(candidate)
        check(f"adversarial rejects {name}",
              any(expected in violation for violation in violations), repr(violations))

    fixture_nested_unknowns = [
        ("values nested unknown", lambda c: c["scenario_runs"][0]["values"].update(extra=1), "values.extra: unknown field"),
        ("per share nested unknown", lambda c: c["scenario_runs"][0]["per_share"].update(extra=1), "per_share.extra: unknown field"),
        ("probability nested unknown", lambda c: c["scenario_runs"][0]["probabilities"].update(extra=1), "probabilities.extra: unknown field"),
        ("schedule row nested unknown", lambda c: c["scenario_runs"][0]["quarterly_schedule"][0].update(extra=1), "quarterly_schedule[0].extra: unknown field"),
        ("analyst ref nested unknown", lambda c: c["input_lineage"][-1]["analyst_ref"].update(extra=1), "analyst_ref.extra: unknown field"),
        ("formal product nested unknown", lambda c: c["formal_output_readiness"]["products"][0].update(extra=1), "formal_output_readiness.products[0].extra: unknown field"),
        ("readiness blocked-state nested unknown", lambda c: c["analogue_readiness"]["blocked_states"]["real_case"].update(extra=1), "blocked_states.real_case.extra: unknown field"),
    ]
    for name, mutate, expected in fixture_nested_unknowns:
        candidate = copy.deepcopy(fixture)
        mutate(candidate)
        violations = contract.validate_envelope(candidate)
        check(f"nested rejects {name}",
              any(expected in violation for violation in violations), repr(violations))
    real_nested_unknown = copy.deepcopy(real)
    first_source = next(row for row in real_nested_unknown["input_lineage"] if row["source_ref"])
    first_source["source_ref"].update(extra=1)
    check("nested rejects source ref nested unknown",
          any("source_ref.extra: unknown field" in violation
              for violation in contract.validate_envelope(real_nested_unknown)))

    bad_blocked_reasons = copy.deepcopy(real)
    bad_blocked_reasons["scenario_runs"][0]["blocked_reasons"] = []
    check("contract rejects blocked run without reasons",
          any("blocked_reasons: blocked run requires reasons" in violation
              for violation in contract.validate_envelope(bad_blocked_reasons)))
    bad_schedule = copy.deepcopy(fixture)
    bad_schedule["scenario_runs"][0]["quarterly_schedule"][0]["discounted_cash_flow_pkr"] = 123.0
    check("contract rejects inconsistent schedule arithmetic",
          any("discounted_cash_flow_pkr: must equal net_cash_flow_pkr * discount_factor" in violation
              for violation in contract.validate_envelope(bad_schedule)))
    bad_lineage_align = copy.deepcopy(fixture)
    bad_lineage_align["input_lineage"].pop()
    check("contract rejects missing fixture lineage",
          any("computed fixture lineage must exactly cover every scenario/input field" in violation
              for violation in contract.validate_envelope(bad_lineage_align)))
    bad_case = adapter._synthetic_case("base")
    bad_case["inputs"]["surprise_field"] = adapter._analyst(1.0, "synthetic_fixture_only_bad")
    check("strict engine-case wrapper rejects unknown input",
          "surprise_field: unknown E&P input field" in contract.validate_engine_case(bad_case))
    non_operator_case = adapter._synthetic_case("bull")
    check("strict engine-case wrapper accepts synthetic non-operator",
          contract.validate_engine_case(non_operator_case) == [])
    missing_operator = adapter._synthetic_case("base")
    missing_operator["inputs"].pop("operator_status")
    check("strict engine-case wrapper rejects missing operator status",
          "operator_status: missing required input" in contract.validate_engine_case(missing_operator))
    invalid_operator = adapter._synthetic_case("base")
    invalid_operator["inputs"]["operator_status"]["value"] = "operator_from_text"
    check("strict engine-case wrapper rejects invalid operator status",
          "operator_status: must be operator or non_operator" in contract.validate_engine_case(invalid_operator))
    bool_operator = adapter._synthetic_case("base")
    bool_operator["inputs"]["operator_status"]["value"] = True
    check("strict engine-case wrapper rejects boolean operator status",
          "operator_status: must be operator or non_operator" in contract.validate_engine_case(bool_operator))
    missing_shares = adapter._synthetic_case("base")
    missing_shares["inputs"].pop("shares_out")
    check("strict engine-case wrapper rejects missing shares_out",
          "shares_out: missing required input" in contract.validate_engine_case(missing_shares))
    bad_case2 = adapter._synthetic_case("base")
    bad_case2["inputs"]["working_interest_pct"]["value"] = float("inf")
    check("strict engine-case wrapper rejects nonfinite input",
          any("working_interest_pct: must be a finite number" in violation
              for violation in contract.validate_engine_case(bad_case2)))
    oversized_case = adapter._synthetic_case("base")
    oversized_case["inputs"]["fx_pkr_usd"]["value"] = 1.0e101
    check("strict engine-case wrapper rejects oversized finite input",
          any("fx_pkr_usd: must be a finite number" in violation
              for violation in contract.validate_engine_case(oversized_case)))
    bad_case3 = adapter._synthetic_case("base")
    bad_case3["inputs"]["working_interest_pct"]["available_on"] = "2026-01-01"
    check("strict engine-case wrapper rejects lookahead input",
          any("working_interest_pct: available_on must be on or before valuation_date" in violation
              for violation in contract.validate_engine_case(bad_case3)))
    bad_case4 = adapter._synthetic_case("base")
    bad_case4["valuation_date"] = "2025-12-XX"
    check("strict engine-case wrapper rejects malformed valuation date",
          any("valuation_date: must be an ISO date" in violation
              for violation in contract.validate_engine_case(bad_case4)))
    duplicate_spend = adapter._synthetic_case("base")
    duplicate_spend["inputs"]["spend_schedule"]["value"].append(
        copy.deepcopy(duplicate_spend["inputs"]["spend_schedule"]["value"][0])
    )
    check("strict engine-case wrapper rejects duplicate spend row",
          any("duplicate spend row" in violation
              for violation in contract.validate_engine_case(duplicate_spend)))
    class DictAlias(dict):
        pass
    alias_case = DictAlias(adapter._synthetic_case("base"))
    check("strict engine-case wrapper rejects dict aliases",
          any("case: must be an exact mapping" in violation
              for violation in contract.validate_engine_case(alias_case)))

    huge_output = copy.deepcopy(fixture)
    huge_output["scenario_runs"][0]["values"]["risked_npv_pkr"] = 10 ** 1000
    check("hostile huge integer output is rejected without raising",
          any("number exceeds magnitude limit" in violation
              for violation in contract.validate_envelope(huge_output)))
    class ListAlias(list):
        pass
    nested_alias = copy.deepcopy(fixture)
    nested_alias["scenario_runs"] = ListAlias(nested_alias["scenario_runs"])
    check("exact scenario list boundary rejects subclasses",
          any("scenario_runs: must be a list" in violation
              for violation in contract.validate_envelope(nested_alias)))

    assert_clean(real, "real")
    assert_clean(fixture, "fixture")
    print(f"MARI ENP case-run adapter: PASS ({PASSED} checks)")


if __name__ == "__main__":
    main()
