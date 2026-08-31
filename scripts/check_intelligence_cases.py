from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_intelligence_cases as cases_builder
import build_ci_slice as ci_slice_builder
from build_intelligence_cases import (
    CASE_PRODUCT_VERSION,
    FOLLOW_THROUGH_DOC_ID,
    FOLLOW_THROUGH_EVENT_ID,
    MARI_CASE_ID,
    MARI_DOC_ID,
    MARI_EVENT_ID,
    MLCF_CASE_ID,
    MLCF_CANONICAL_CONTROL_EVENT_ID,
    MLCF_FOLLOW_THROUGH_ALIAS_EVENT_ID,
    MLCF_INDEPENDENT_CANONICAL_EVENT_BINDING,
    MLCF_LEGACY_ALIAS_EVENT_BINDING,
    OUT,
    PUBLIC_OFFER_DOC_ID,
    PUBLIC_OFFER_EVENT_ID,
)
from ci_checker_helpers import assert_ci_slice_projection, without_root_meta
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
         "2025-12-18T12:52:00+05:00", "2025-12-18", "2025-12-18",
         MLCF_INDEPENDENT_CANONICAL_EVENT_BINDING),
        (follow, MLCF_FOLLOW_THROUGH_ALIAS_EVENT_ID, FOLLOW_THROUGH_EVENT_ID, FOLLOW_THROUGH_DOC_ID, 4,
         "744a0c710043d6e0a7de36bb99f21ca50f0f9346f6972b957f6733a47deae11f",
         "725f04c3c6d7f36bbffd6c205d574750f65b8c0546ae9f1b50683fe07b292b66",
         "2026-04-28T10:25:00+05:00", "2026-04-28", "2026-04-28",
         MLCF_LEGACY_ALIAS_EVENT_BINDING),
    ]
    for ref, canonical, legacy, doc_id, page, content_hash, evidence_hash, published, effective, available, binding in expected:
        if ref.get("canonical_event_id") != canonical or ref.get("legacy_event_id") != legacy:
            raise AssertionError("MLCF canonical/legacy event alias mismatch")
        if ref.get("canonical_event_id_binding") != binding:
            raise AssertionError("MLCF canonical event binding label mismatch")
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


def _builder_inputs() -> dict:
    return {
        "profiles": load_json(STATE / "company_profiles.json", {}),
        "ledger": load_json(STATE / "company_event_ledger.json", {"companies": {}}),
        "documents": load_json(STATE / "company_documents.json", {"documents": {}}),
        "operating_events": load_json(STATE / "company_intel" / "operating_events.json", {"companies": {}}),
        "financial_truth": load_json(STATE / "company_intel" / "financial_truth_qualification.json", {}),
        "event_studies": load_json(STATE / "company_intel" / "event_studies.json", {"studies": {}}),
        "mlcf_history": load_json(STATE / "history" / "MLCF.json", []),
        "mari_history": load_json(STATE / "history" / "MARI.json", []),
    }


def _build_with_inputs(inputs: dict) -> None:
    original_load_json = cases_builder.load_json
    sources = {
        STATE / "company_profiles.json": inputs["profiles"],
        STATE / "company_event_ledger.json": inputs["ledger"],
        STATE / "company_documents.json": inputs["documents"],
        STATE / "company_intel" / "operating_events.json": inputs["operating_events"],
        STATE / "company_intel" / "financial_truth_qualification.json": inputs["financial_truth"],
        STATE / "company_intel" / "event_studies.json": inputs["event_studies"],
        STATE / "history" / "MLCF.json": inputs["mlcf_history"],
        STATE / "history" / "MARI.json": inputs["mari_history"],
    }

    def fake_load_json(path: Path, default: object = None) -> object:
        for source_path, value in sources.items():
            if Path(path) == source_path:
                return copy.deepcopy(value)
        return original_load_json(path, default)

    cases_builder.load_json = fake_load_json
    try:
        cases_builder.build(write=False)
    finally:
        cases_builder.load_json = original_load_json


def _ledger_event(inputs: dict, event_id: str) -> dict:
    for event in inputs["ledger"]["companies"]["MLCF"]["events"]:
        if event.get("event_id") == event_id:
            return event
    raise AssertionError(f"fixture missing ledger event: {event_id}")


def _document(inputs: dict, doc_id: str) -> dict:
    doc = inputs["documents"]["documents"].get(doc_id)
    if not isinstance(doc, dict):
        raise AssertionError(f"fixture missing document: {doc_id}")
    return doc


def _operating_event(inputs: dict, event_id: str, symbol: str = "MLCF") -> dict:
    for event in inputs["operating_events"]["companies"][symbol]["events"]:
        if event.get("event_id") == event_id:
            return event
    raise AssertionError(f"fixture missing operating event: {event_id}")


def _counter_section(inputs: dict, section: str) -> dict:
    row = inputs["financial_truth"]["companies"]["MLCF"].get(section)
    if not isinstance(row, dict):
        raise AssertionError(f"fixture missing financial counter: {section}")
    return row


def _market_study(inputs: dict, event_id: str = MLCF_CANONICAL_CONTROL_EVENT_ID) -> dict:
    study = inputs["event_studies"].get("studies", {}).get(event_id)
    if not isinstance(study, dict):
        raise AssertionError("fixture missing MLCF canonical event study")
    return study


def _assert_mlcf_market_context(case: dict) -> None:
    context = (case.get("sections") or {}).get("analogues") or {}
    if context.get("status") != "available" or context.get("epistemic_type") != "derived_fact":
        raise AssertionError("MLCF market context must be an available derived fact")
    text = context.get("text") or ""
    for required in ("descriptive only", "not causal", "not adjusted or total return", "not an analogue benchmark", "not a forecast or valuation input"):
        if required not in text:
            raise AssertionError(f"MLCF market-context limitation missing: {required}")
    items = {item.get("id"): item for item in context.get("items") or []}
    for horizon, endpoint, expected_return in (
        ("1Q", "2026-03-18", -34.539447809329026),
        ("2Q", "2026-06-18", -19.397467159600414),
    ):
        item = items.get(horizon) or {}
        if f"{expected_return:.2f}%" not in str(item.get("text")) or endpoint not in str(item.get("text")):
            raise AssertionError(f"MLCF {horizon} raw-return context mismatch")
        if "descriptive and non-causal" not in str(item.get("reason")):
            raise AssertionError(f"MLCF {horizon} limitation missing")
    for horizon in ("4Q", "8Q"):
        item = items.get(horizon) or {}
        if item.get("text") != "Outcome not yet mature." or item.get("reason") != "target_after_last_bar":
            raise AssertionError(f"MLCF {horizon} maturity handling mismatch")
    aggregate = items.get("analogue_sample") or {}
    if "minimum threshold" not in str(aggregate.get("text")) or aggregate.get("reason") != "All retained aggregate horizons are suppressed because n < 3.":
        raise AssertionError("MLCF suppressed analogue status mismatch")
    formulas = context.get("formulas") or []
    if formulas != [{
        "formula_id": "event_study.raw_price_return.v1",
        "operands": ["baseline_close", "endpoint_close"],
        "source": "state/company_intel/event_studies.json; retained bars: state/history/MLCF.json",
    }]:
        raise AssertionError("MLCF market-context formula lineage mismatch")


def _assert_mari_market_context(case: dict) -> None:
    context = (case.get("sections") or {}).get("analogues") or {}
    if context.get("status") != "available" or context.get("epistemic_type") != "derived_fact":
        raise AssertionError("MARI market context must be an available derived fact")
    text = context.get("text") or ""
    for required in ("descriptive only", "not causal", "not adjusted or total return", "not an analogue benchmark", "not a forecast or valuation input"):
        if required not in text:
            raise AssertionError(f"MARI market-context limitation missing: {required}")
    items = {item.get("id"): item for item in context.get("items") or []}
    for horizon, endpoint, expected_return in (
        ("1Q", "2025-12-30", -2.708014258413405),
        ("2Q", "2026-03-30", -16.79971808460172),
    ):
        item = items.get(horizon) or {}
        if f"{expected_return:.2f}%" not in str(item.get("text")) or endpoint not in str(item.get("text")):
            raise AssertionError(f"MARI {horizon} raw-return context mismatch")
        if "retained MARI raw closing prices" not in str(item.get("reason")):
            raise AssertionError(f"MARI {horizon} source note missing")
    for horizon in ("4Q", "8Q"):
        item = items.get(horizon) or {}
        if item.get("text") != "Outcome not yet mature." or item.get("reason") != "target_after_last_bar":
            raise AssertionError(f"MARI {horizon} maturity handling mismatch")
    if (items.get("analogue_sample") or {}).get("reason") != "All retained aggregate horizons are suppressed because n < 3.":
        raise AssertionError("MARI suppressed analogue status mismatch")
    formulas = context.get("formulas") or []
    if formulas != [{
        "formula_id": "event_study.raw_price_return.v1",
        "operands": ["baseline_close", "endpoint_close"],
        "source": "state/company_intel/event_studies.json; retained bars: state/history/MARI.json",
    }]:
        raise AssertionError("MARI market-context formula lineage mismatch")


def _expect_builder_rejects(label: str, mutate) -> None:
    inputs = _builder_inputs()
    mutate(inputs)
    try:
        _build_with_inputs(inputs)
    except ValueError:
        return
    raise AssertionError(f"builder accepted bad MLCF source fixture: {label}")


def _assert_builder_source_mutation_tests() -> None:
    _expect_builder_rejects(
        "bad canonical event id",
        lambda inputs: _operating_event(inputs, MLCF_CANONICAL_CONTROL_EVENT_ID).__setitem__("event_id", "evt_bad"),
    )
    _expect_builder_rejects(
        "bad legacy event id",
        lambda inputs: _ledger_event(inputs, PUBLIC_OFFER_EVENT_ID).__setitem__("event_id", "evt_bad"),
    )
    _expect_builder_rejects(
        "bad control content hash",
        lambda inputs: _document(inputs, PUBLIC_OFFER_DOC_ID).__setitem__("content_sha256", "0" * 64),
    )
    _expect_builder_rejects(
        "bad canonical evidence hash",
        lambda inputs: _operating_event(inputs, MLCF_CANONICAL_CONTROL_EVENT_ID)["evidence"][0].__setitem__(
            "evidence_sha256", "0" * 64
        ),
    )
    _expect_builder_rejects(
        "bad follow-through evidence hash",
        lambda inputs: _ledger_event(inputs, FOLLOW_THROUGH_EVENT_ID)["evidence"][0].__setitem__("text", "changed"),
    )
    _expect_builder_rejects(
        "bad follow-through independent canonical event",
        lambda inputs: inputs["operating_events"]["companies"]["MLCF"]["events"].append(
            {
                **copy.deepcopy(_operating_event(inputs, MLCF_CANONICAL_CONTROL_EVENT_ID)),
                "event_id": MLCF_FOLLOW_THROUGH_ALIAS_EVENT_ID,
            }
        ),
    )
    _expect_builder_rejects(
        "bad follow-through document id",
        lambda inputs: _ledger_event(inputs, FOLLOW_THROUGH_EVENT_ID).__setitem__("doc_id", PUBLIC_OFFER_DOC_ID),
    )
    _expect_builder_rejects(
        "bad follow-through content hash",
        lambda inputs: _document(inputs, FOLLOW_THROUGH_DOC_ID).__setitem__("content_sha256", "0" * 64),
    )
    _expect_builder_rejects(
        "bad follow-through document hash",
        lambda inputs: _document(inputs, FOLLOW_THROUGH_DOC_ID).__setitem__("local_sha256", "0" * 64),
    )
    _expect_builder_rejects(
        "bad follow-through effective date",
        lambda inputs: _ledger_event(inputs, FOLLOW_THROUGH_EVENT_ID).__setitem__(
            "event_date", "2026-04-29T10:25:00+05:00"
        ),
    )
    _expect_builder_rejects(
        "bad follow-through published date",
        lambda inputs: _document(inputs, FOLLOW_THROUGH_DOC_ID).__setitem__(
            "published_at", "2026-04-29T10:25:00+05:00"
        ),
    )
    _expect_builder_rejects(
        "bad original page",
        lambda inputs: _ledger_event(inputs, FOLLOW_THROUGH_EVENT_ID)["evidence"][0].__setitem__("page", 5),
    )
    _expect_builder_rejects(
        "bad source URL",
        lambda inputs: _document(inputs, PUBLIC_OFFER_DOC_ID).__setitem__(
            "source_url", "https://example.invalid/document.pdf"
        ),
    )
    _expect_builder_rejects(
        "bad available date",
        lambda inputs: _document(inputs, FOLLOW_THROUGH_DOC_ID).__setitem__("available_on", "2026-04-29"),
    )
    _expect_builder_rejects(
        "missing evidence row",
        lambda inputs: _ledger_event(inputs, FOLLOW_THROUGH_EVENT_ID).__setitem__("evidence", []),
    )
    _expect_builder_rejects(
        "bad counter type",
        lambda inputs: _counter_section(inputs, "annual_income_triplets").__setitem__("required", "5"),
    )
    _expect_builder_rejects(
        "bad counter range",
        lambda inputs: _counter_section(inputs, "qualified_reported_quarter_fact_sets").__setitem__("present", 9),
    )
    _expect_builder_rejects(
        "bad counter keys",
        lambda inputs: _counter_section(inputs, "annual_operating_cash_flow").__setitem__("extra", "not allowed"),
    )
    _expect_builder_rejects(
        "bad counter period format",
        lambda inputs: _counter_section(inputs, "annual_income_triplets")["qualified_periods"].__setitem__(
            0, "2026/06/30"
        ),
    )
    _expect_builder_rejects(
        "bad counter semantics",
        lambda inputs: _counter_section(inputs, "annual_income_triplets").__setitem__("required", 6),
    )
    _expect_builder_rejects(
        "bad share-count source",
        lambda inputs: inputs["financial_truth"]["companies"]["MLCF"]["share_count"].__setitem__("source", "manual"),
    )
    _expect_builder_rejects(
        "bad share-count status",
        lambda inputs: inputs["financial_truth"]["companies"]["MLCF"]["share_count"].__setitem__("status", "ready"),
    )
    _expect_builder_rejects(
        "bad share-count shape",
        lambda inputs: inputs["financial_truth"]["companies"]["MLCF"].__setitem__("share_count", []),
    )
    _expect_builder_rejects(
        "bad market study event binding",
        lambda inputs: _market_study(inputs).__setitem__("event_id", "evt_bad"),
    )
    _expect_builder_rejects(
        "bad market study source history",
        lambda inputs: _market_study(inputs)["baseline"]["provenance"].__setitem__("history_file", "state/history/OTHER.json"),
    )
    _expect_builder_rejects(
        "bad mature market return",
        lambda inputs: _market_study(inputs)["horizons"]["1Q"].__setitem__("return_pct", float("nan")),
    )
    _expect_builder_rejects(
        "premature market horizon outcome",
        lambda inputs: _market_study(inputs)["horizons"]["4Q"].__setitem__("return_pct", 1.0),
    )
    _expect_builder_rejects(
        "unsuppressed small analogue sample",
        lambda inputs: _market_study(inputs)["analogue_aggregate"]["1Q"].__setitem__("status", "available"),
    )
    _expect_builder_rejects(
        "future market data cutoff",
        lambda inputs: _market_study(inputs).__setitem__("data_cutoff", "2099-01-01"),
    )
    _expect_builder_rejects(
        "market cutoff disconnected from retained history",
        lambda inputs: _market_study(inputs).__setitem__("data_cutoff", "2026-08-27"),
    )
    _expect_builder_rejects(
        "market mature endpoint beyond retained history",
        lambda inputs: _market_study(inputs)["horizons"]["1Q"].update({
            "selected_date": "2099-01-01",
            "provenance": {"history_file": "state/history/MLCF.json", "baseline_date": "2025-12-17", "endpoint_date": "2099-01-01"},
        }),
    )
    _expect_builder_rejects(
        "market giant baseline integer",
        lambda inputs: _market_study(inputs)["baseline"].__setitem__("selected_close", 10**1000),
    )
    _expect_builder_rejects(
        "market giant return integer",
        lambda inputs: _market_study(inputs)["horizons"]["1Q"].__setitem__("return_pct", 10**1000),
    )
    _expect_builder_rejects(
        "MARI market study event binding",
        lambda inputs: _market_study(inputs, "evt_b25decfc180474cbe066").__setitem__("event_id", "evt_bad"),
    )
    _expect_builder_rejects(
        "MARI market study history cutoff",
        lambda inputs: _market_study(inputs, "evt_b25decfc180474cbe066").__setitem__("data_cutoff", "2099-01-01"),
    )
    _expect_builder_rejects(
        "MARI canonical evidence hash",
        lambda inputs: _operating_event(inputs, "evt_b25decfc180474cbe066", "MARI")["evidence"][0].__setitem__("evidence_sha256", "0" * 64),
    )


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
    _assert_mlcf_market_context(case)
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
    if set(mari_facts) != {"mari_peshawar_working_interest_acquisition"}:
        raise AssertionError("MARI observed facts mismatch")
    mari_fact = mari_facts["mari_peshawar_working_interest_acquisition"]
    if {row.get("label"): row.get("value") for row in mari_fact.get("reported_values") or []} != {
        "block": "Peshawar Block",
        "operator_status": "as an Operator",
    }:
        raise AssertionError("MARI reported values mismatch")
    mari_ref = (mari_fact.get("evidence") or [{}])[0]
    _assert_evidence(mari_ref, MARI_EVENT_ID, MARI_DOC_ID, 1)
    if mari_ref.get("content_sha256") != "c13ccb4de58ad005bca106942721490593fe219ff45906c68280ea7856192e42":
        raise AssertionError("MARI source hash mismatch")
    _assert_mari_market_context(mari_case)
    for status in ("Corroborated", "Modelled", "Published"):
        if status not in (mari_case.get("promotion_blocks") or {}):
            raise AssertionError(f"MARI missing promotion block for {status}")
    if _dump(without_root_meta(state)) != _dump(without_root_meta(cases_builder.build(write=False))):
        raise AssertionError("intelligence case rebuild is not deterministic")
    _assert_builder_source_mutation_tests()

    confidence = load_json(STATE / "company_intel" / "intelligence_confidence.json", {"companies": {}})
    watchlist = load_json(STATE / "company_intel" / "evidence_watchlist.json", {"companies": {}})
    expected_slice_row = ci_slice_builder._intelligence_case_row(
        state,
        "MLCF",
        confidence_row=(confidence.get("companies") or {}).get("MLCF"),
        watchlist_row=(watchlist.get("companies") or {}).get("MLCF"),
    )
    if not isinstance(expected_slice_row, dict) or expected_slice_row.get("symbol") != "MLCF":
        raise AssertionError("MLCF CI slice case projection is missing")
    assert_ci_slice_projection(
        ci_slice_builder,
        ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json",
        "MLCF",
        "intelligence_cases",
        expected_slice_row,
    )
    print("intelligence_cases: PASS (MLCF and MARI Observed seeds, 3 official citations)")


if __name__ == "__main__":
    main()
