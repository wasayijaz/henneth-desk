"""Focused deterministic checks for the MARI observed-event hypothesis kernel."""
from __future__ import annotations

import copy
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import mari_enp_hypothesis_contract as contract
import mari_enp_hypothesis_engine as engine

PASSED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"{name}: {detail}" if detail else name)
    PASSED += 1


def close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def source(canonical_event_id: str, legacy_event_id: str, document_id: str,
           content_sha256: str, evidence_sha256: str, page: int) -> dict:
    return {
        "canonical_event_id": canonical_event_id,
        "legacy_event_id": legacy_event_id,
        "document_id": document_id,
        "content_sha256": content_sha256,
        "evidence_sha256": evidence_sha256,
        "page": page,
        "join_key": f"{document_id}|{page}|{content_sha256}",
        "source_label": "Synthetic retained document fixture",
        "source_url": f"https://dps.psx.com.pk/download/document/{document_id.split(':')[-1]}.pdf",
        "raw_available": True,
        "retained": True,
    }


def golden_case() -> dict:
    event_id = "evt_3d1dae7553f73da60ba3"
    event_source = source(
        "evt_3d1dae7553f73da60ba3", "evt_ddf99590afb6dacddbde",
        "psx:265594", "cdc3f69157f5e5803238ba347ecb4e96f7297479df87d345739896913de8aae4",
        "56c298f041bd756cd184e75d122f5a95cc6879f4b5fa037786007948b76d3d83", 3,
    )
    peshawar_source = source(
        "evt_b25decfc180474cbe066", "evt_eddfcc381018cb0dff43",
        "psx:260446", "c13ccb4de58ad005bca106942721490593fe219ff45906c68280ea7856192e42",
        "dd83c62cb781e2a57f5ae595a7184ea786a3e5890f7f7cc96cd93e23f958a177", 1,
    )
    return {
        "schema_version": "mari_enp_hypothesis_case_v1",
        "symbol": "MARI",
        "case_id": "mari-hypothesis-fixture",
        "as_of_date": "2025-11-30",
        "event": {
            "event_id": event_id,
            "canonical_event_id": "evt_3d1dae7553f73da60ba3",
            "legacy_event_id": "evt_ddf99590afb6dacddbde",
            "event_statement": "Synthetic observed-text-only event fixture; no issuer fact is asserted.",
            "event_date": "2025-11-13",
            "published_date": "2025-11-13",
            "available_on": "2025-11-13",
            "event_status": "observed",
            "source": event_source,
        },
        "hypotheses": [
            {
                "hypothesis_id": "blocks_not_proved_reserves",
                "hypothesis_type": "observed_text_only",
                "label": "Blocks reserves are not proved",
                "statement": "Observed text does not prove reserves.",
                "exclusive_group": "mari-event-mechanism",
                "excludes": ["strategy_not_execution_schedule"],
                "base_confidence": 0.60,
            },
            {
                "hypothesis_id": "strategy_not_execution_schedule",
                "hypothesis_type": "observed_text_only",
                "label": "Strategy is not an execution schedule",
                "statement": "Observed strategy text is not an execution schedule.",
                "exclusive_group": "mari-event-mechanism",
                "excludes": ["blocks_not_proved_reserves"],
                "base_confidence": 0.40,
            },
        ],
        "evidence": [
            {
                "evidence_id": "ev-event-corroboration",
                "event_id": event_id,
                "hypothesis_id": "blocks_not_proved_reserves",
                "relation": "corroborates",
                "status": "available",
                "summary": "Synthetic source-bound corroboration fixture.",
                "event_date": "2025-11-13",
                "published_date": "2025-11-13",
                "available_on": "2025-11-13",
                "weight": 0.80,
                "source": event_source,
            },
            {
                "evidence_id": "ev-alt-refutation",
                "event_id": event_id,
                "hypothesis_id": "blocks_not_proved_reserves",
                "relation": "refutes",
                "status": "available",
                "summary": "Synthetic source-bound refutation fixture.",
                "event_date": "2025-09-30",
                "published_date": "2025-09-30",
                "available_on": "2025-09-30",
                "weight": 0.10,
                "source": peshawar_source,
            },
            {
                "evidence_id": "ev-no-expansion-refutation",
                "event_id": event_id,
                "hypothesis_id": "strategy_not_execution_schedule",
                "relation": "refutes",
                "status": "available",
                "summary": "Synthetic source-bound refutation fixture.",
                "event_date": "2025-09-30",
                "published_date": "2025-09-30",
                "available_on": "2025-09-30",
                "weight": 0.90,
                "source": peshawar_source,
            },
        ],
    }


def expect_reject(name: str, candidate: dict, expected: str) -> None:
    violations = contract.validate_case(candidate)
    check(f"boundary {name}", any(expected in violation for violation in violations), repr(violations))


def main() -> None:
    case = golden_case()
    check("contract id", contract.CONTRACT_VERSION == "mari_enp_hypothesis_contract_v1")
    check("case schema", contract.CASE_SCHEMA == "mari_enp_hypothesis_case_v1")
    check("golden validates", contract.validate_case(case) == [])
    check("source fixture accepted", contract.validate_case(case) == [])

    result = engine.evaluate_case(case)
    expected_keys = {"schema_version", "formula_id", "engine_version", "run_receipt", "status",
                     "scenario", "event_lifecycle", "evidence_lifecycle", "hypothesis_lifecycle",
                     "unresolved_reasons", "confidence", "policy"}
    check("envelope shape", set(result) == expected_keys)
    check("envelope ids", result["schema_version"] == engine.RESULT_SCHEMA
          and result["formula_id"] == engine.FORMULA_ID
          and result["engine_version"] == engine.ENGINE_VERSION)
    check("resolved lifecycle", result["status"] == "resolved" and result["unresolved_reasons"] == [])
    check("scenario identity", result["scenario"] == {
        "symbol": "MARI", "case_id": "mari-hypothesis-fixture", "as_of_date": "2025-11-30",
        "event_id": "evt_3d1dae7553f73da60ba3", "event_status": "observed",
    })
    check("event lifecycle", result["event_lifecycle"]["event_status"] == "observed"
          and result["event_lifecycle"]["canonical_event_id"] == "evt_3d1dae7553f73da60ba3"
          and result["event_lifecycle"]["legacy_event_id"] == "evt_ddf99590afb6dacddbde"
          and result["event_lifecycle"]["source"]["document_id"] == "psx:265594")
    check("evidence lifecycle count", len(result["evidence_lifecycle"]) == 3)
    check("allowlisted documents", {row["source"]["document_id"] for row in result["evidence_lifecycle"]}
          == {"psx:265594", "psx:260446"})
    check("evidence source receipts", all(len(row["source"]["content_sha256"]) == 64
                                           and len(row["source"]["evidence_sha256"]) == 64
                                           and row["source"]["page"] >= 1
                                           and row["source"]["join_key"].count("|") == 2
                                           and row["source"]["raw_available"] is True
                                           and row["source"]["retained"] is True
                                           and row["status"] == "available"
                                           for row in result["evidence_lifecycle"]))
    h1, h2 = result["hypothesis_lifecycle"]
    check("hypothesis lifecycle ids", [row["hypothesis_id"] for row in result["hypothesis_lifecycle"]]
          == ["blocks_not_proved_reserves", "strategy_not_execution_schedule"])
    check("hypothesis statuses", h1["lifecycle"] == "supported" and h2["lifecycle"] == "refuted")
    check("confidence arithmetic", close(h1["confidence"], round((0.60 + 0.80) / (1.0 + 0.80 + 0.10), 6))
          and close(h2["confidence"], round((0.40 + 0.00) / (1.0 + 0.90), 6)))
    check("confidence aggregate", close(result["confidence"]["overall"], h1["confidence"]))
    check("policy gates", result["policy"] == {"research_only": True, "no_advice": True, "no_financial_outputs": True})
    check("receipt present", isinstance(result["run_receipt"]["inputs_sha256"], str)
          and len(result["run_receipt"]["inputs_sha256"]) == 64)

    repeat = engine.evaluate_case(case)
    copied = engine.evaluate_case(copy.deepcopy(case))
    dump = json.dumps(result, sort_keys=True)
    check("same object deterministic", json.dumps(repeat, sort_keys=True) == dump)
    check("deepcopy deterministic", json.dumps(copied, sort_keys=True) == dump)
    frozen = json.dumps(result, sort_keys=True)
    case["evidence"][0]["source"]["source_label"] = "mutated-source"
    check("result detached from input mutation", json.dumps(result, sort_keys=True) == frozen)
    changed = engine.evaluate_case(case)
    check("input mutation changes hash", changed["run_receipt"]["inputs_sha256"] != result["run_receipt"]["inputs_sha256"])

    mutations = [
        ("missing event", lambda c: c.pop("event"), "case.event: missing required field"),
        ("wrong symbol", lambda c: c.update(symbol="OGDC"), "symbol: must equal MARI"),
        ("event status", lambda c: c["event"].update(event_status="planned"), "event.event_status: must equal observed"),
        ("hypothesis type", lambda c: c["hypotheses"][0].update(hypothesis_type="forecast"), "hypotheses[0].hypothesis_type: must equal observed_text_only"),
        ("bad hash", lambda c: c["event"]["source"].update(content_sha256="x"), "event.source.content_sha256: must be 64 lowercase hex characters"),
        ("fabricated content hash", lambda c: (c["event"]["source"].update(content_sha256="d" * 64), c["event"]["source"].update(join_key=f"psx:265594|3|{'d' * 64}")), "event.source: source is not in the exact retained MARI allowlist"),
        ("bad evidence hash", lambda c: c["event"]["source"].update(evidence_sha256="d" * 64), "event.source: source is not in the exact retained MARI allowlist"),
        ("bad join", lambda c: c["event"]["source"].update(join_key="wrong"), "event.source.join_key: must equal document_id|page|content_sha256"),
        ("alias mismatch", lambda c: c["event"].update(legacy_event_id="evt-other"), "event.legacy_event_id: must reconcile with event.source.legacy_event_id"),
        ("fabricated document", lambda c: (c["event"]["source"].update(document_id="psx:999999"), c["event"]["source"].update(join_key=f"psx:999999|3|{c['event']['source']['content_sha256']}")), "event.source: source is not in the exact retained MARI allowlist"),
        ("fabricated page", lambda c: (c["event"]["source"].update(page=4), c["event"]["source"].update(join_key=f"psx:265594|4|{c['event']['source']['content_sha256']}")), "event.source: source is not in the exact retained MARI allowlist"),
        ("fabricated alias", lambda c: c["event"]["source"].update(canonical_event_id="evt-fabricated"), "event.source: source is not in the exact retained MARI allowlist"),
        ("fabricated legacy alias", lambda c: c["event"]["source"].update(legacy_event_id="evt-fabricated"), "event.source: source is not in the exact retained MARI allowlist"),
        ("page bool", lambda c: c["event"]["source"].update(page=True), "event.source.page: must be an integer >= 1"),
        ("raw unavailable", lambda c: c["event"]["source"].update(raw_available=False), "event.source.raw_available: raw-unavailable evidence is blocked"),
        ("not retained", lambda c: c["event"]["source"].update(retained=False), "event.source.retained: source is not retained"),
        ("availability binding", lambda c: c["event"].update(available_on="2025-11-14"), "event.source: available_on does not match retained source binding"),
        ("event untimestamped", lambda c: c["event"].update(event_date="unknown"), "event.event_date: must be an exact ISO date"),
        ("event lookahead", lambda c: c["event"].update(available_on="2025-12-01"), "event.available_on: must be on or before as_of_date"),
        ("published ordering", lambda c: c["event"].update(published_date="2025-11-10"), "event: event_date must be on or before published_date"),
        ("duplicate hypothesis id", lambda c: c["hypotheses"][1].update(hypothesis_id="blocks_not_proved_reserves"), "hypotheses: duplicate hypothesis_id"),
        ("duplicate label", lambda c: c["hypotheses"][1].update(label=c["hypotheses"][0]["label"]), "hypotheses[1].label: duplicate hypothesis"),
        ("duplicate statement", lambda c: c["hypotheses"][1].update(statement=c["hypotheses"][0]["statement"]), "hypotheses[1].statement: duplicate hypothesis"),
        ("non-exclusive excludes", lambda c: c["hypotheses"][0].update(excludes=[]), "hypotheses[0].excludes: must name every other hypothesis exactly once"),
        ("duplicate exclusion", lambda c: c["hypotheses"][0].update(excludes=["strategy_not_execution_schedule", "strategy_not_execution_schedule"]), "hypotheses[0].excludes: duplicate alternative exclusion entry"),
        ("one hypothesis", lambda c: c.update(hypotheses=c["hypotheses"][:1]), "hypotheses: must contain at least two"),
        ("duplicate evidence id", lambda c: c["evidence"][1].update(evidence_id=c["evidence"][0]["evidence_id"]), "evidence: duplicate evidence_id"),
        ("missing evidence", lambda c: c.update(evidence=c["evidence"][:1]), "evidence: must contain at least two"),
        ("bad relation", lambda c: c["evidence"][0].update(relation="supports"), "evidence[0].relation: must be corroborates or refutes"),
        ("missing relation class", lambda c: c["evidence"].__setitem__(0, {**c["evidence"][0], "relation": "refutes"}), "evidence: at least one corroborates and one refutes"),
        ("missing evidence for hypothesis", lambda c: c.update(evidence=c["evidence"][:2]), "evidence: hypothesis strategy_not_execution_schedule has no corroboration/refutation evidence"),
        ("evidence event mismatch", lambda c: c["evidence"][0].update(event_id="other-event"), "evidence[0].event_id: must match event.event_id"),
        ("evidence lookahead", lambda c: c["evidence"][0].update(available_on="2025-12-01"), "evidence[0].available_on: must be on or before as_of_date"),
        ("evidence status missing", lambda c: c["evidence"][0].update(status="missing"), "evidence[0].status: missing evidence is blocked"),
        ("evidence raw unavailable", lambda c: c["evidence"][0]["source"].update(raw_available=False), "evidence[0].source.raw_available: raw-unavailable evidence is blocked"),
        ("confidence nan", lambda c: c["hypotheses"][0].update(base_confidence=float("nan")), "hypotheses[0].base_confidence: must be a finite number"),
        ("confidence inf", lambda c: c["hypotheses"][0].update(base_confidence=float("inf")), "hypotheses[0].base_confidence: must be a finite number"),
        ("confidence overbound", lambda c: c["hypotheses"][0].update(base_confidence=1.01), "hypotheses[0].base_confidence: must be in [0, 1]"),
        ("weight nan", lambda c: c["evidence"][0].update(weight=float("nan")), "evidence[0].weight: must be a finite number"),
        ("weight zero", lambda c: c["evidence"][0].update(weight=0.0), "evidence[0].weight: must be in (0, 1]"),
        ("unknown top-level", lambda c: c.update(extra_field=True), "case.extra_field: unknown field"),
        ("unknown nested", lambda c: c["event"].update(extra_field=True), "event.extra_field: unknown field"),
        ("financial output attempt", lambda c: c.update(financial_outputs={"npv": 1}), "financial output fields are forbidden"),
        ("non-json", lambda c: c["event"].update(event_statement={1, 2}), "case: must be JSON-serializable and finite"),
    ]
    for name, mutate, expected in mutations:
        candidate = golden_case()
        mutate(candidate)
        expect_reject(name, candidate, expected)

    try:
        engine.evaluate_case({"symbol": "MARI"})
    except ValueError as error:
        check("evaluate raises named violations", "; " in str(error) and "case_id" in str(error))
    else:
        raise AssertionError("evaluate should reject invalid case")

    blocked = engine.blocked_result({"symbol": "MARI", "case_id": "blocked-fixture"}, ["zeta", "alpha", "alpha"])
    check("blocked envelope", blocked["status"] == "blocked" and blocked["event_lifecycle"] is None
          and blocked["evidence_lifecycle"] == [] and blocked["hypothesis_lifecycle"] == []
          and blocked["confidence"] is None and blocked["unresolved_reasons"] == ["alpha", "zeta"])

    for label, payload in (("computed", result), ("blocked", blocked)):
        text = json.dumps(payload, sort_keys=True).lower()
        for phrase in ("buy", "sell", "accumulate", "target price", "price target", "you should",
                       "npv", "revenue", "eps", "valuation", "forecast", "pkr", "usd"):
            check(f"{label} no financial/advice output {phrase}", re.search(r"\b" + re.escape(phrase) + r"\b", text) is None)
        for key, value in walk(payload):
            if isinstance(value, float):
                check(f"{label} finite {key}", math.isfinite(value))

    for module in (contract, engine):
        for symbol in ("open", "save_json", "load_json", "write", "requests"):
            check(f"no io/network symbol {module.__name__}.{symbol}", not hasattr(module, symbol))
    print(f"MARI ENP hypothesis model: PASS ({PASSED} checks)")


if __name__ == "__main__":
    main()
