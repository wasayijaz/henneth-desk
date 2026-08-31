from __future__ import annotations

import json
import copy
import subprocess
import sys

from build_intelligence_confidence import OUT, build
from intelligence_confidence import COMPONENT_WEIGHTS, FORBIDDEN_TEXT, build_intelligence_confidence
from psx_data import ROOT, STATE, load_json


def _fail(message: str) -> None:
    raise AssertionError(message)


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def _assert_safe_language(data: dict) -> None:
    for value in _walk_strings(data):
        lowered = value.lower()
        if lowered in {"no_advice", "no_probability", "no_forecast", "no_price_claim", "no_price_claims"}:
            continue
        for term in FORBIDDEN_TEXT:
            if term in lowered:
                _fail(f"forbidden confidence term present: {term}")


def _assert_shape(data: dict, signal_state: dict, event_studies: dict, model_inputs: dict, financial_truth: dict) -> int:
    symbols = list(signal_state.get("pilot_symbols") or [])
    if len(symbols) != 20 or len(set(symbols)) != 20:
        _fail("pilot boundary must be exactly 20")
    if data.get("pilot_symbols") != symbols:
        _fail("pilot symbol order mismatch")
    if data.get("component_weights") != COMPONENT_WEIGHTS or sum(COMPONENT_WEIGHTS.values()) != 100:
        _fail("component weights mismatch")
    companies = data.get("companies") or {}
    if set(companies) != set(symbols):
        _fail("company boundary mismatch")
    studies_by_event = {
        study.get("event_id"): study
        for study in (event_studies.get("studies") or {}).values()
        if isinstance(study, dict) and study.get("event_id")
    }
    total = 0
    seen_ids = set()
    for symbol in symbols:
        row = companies.get(symbol) or {}
        signal_row = (signal_state.get("companies") or {}).get(symbol) or {}
        model_row = (model_inputs.get("companies") or {}).get(symbol) or {}
        truth_row = (financial_truth.get("companies") or {}).get(symbol) or {}
        clusters = signal_row.get("clusters") or []
        assessments = row.get("assessments") or []
        if row.get("source_cluster_count") != len(clusters):
            _fail(f"{symbol}: source cluster count mismatch")
        if row.get("assessment_count") != len(assessments) or len(assessments) != len(clusters):
            _fail(f"{symbol}: assessment count mismatch")
        if assessments and row.get("aggregate_score") is None:
            _fail(f"{symbol}: missing aggregate for assessed company")
        if not assessments and row.get("aggregate_score") is not None:
            _fail(f"{symbol}: aggregate present without assessments")
        cluster_ids = {cluster.get("cluster_id") for cluster in clusters}
        for assessment in assessments:
            total += 1
            aid = assessment.get("confidence_id")
            if not aid or aid in seen_ids:
                _fail(f"{symbol}: duplicate/missing assessment id")
            seen_ids.add(aid)
            if assessment.get("source_cluster_id") not in cluster_ids:
                _fail(f"{symbol}: assessment references unknown cluster")
            if assessment.get("band") not in {"low", "medium", "high"}:
                _fail(f"{symbol}: invalid confidence band")
            components = assessment.get("components") or {}
            if tuple(components) != tuple(COMPONENT_WEIGHTS):
                _fail(f"{symbol}: component order/name mismatch")
            point_sum = 0.0
            for name, component in components.items():
                if component.get("weight") != COMPONENT_WEIGHTS[name]:
                    _fail(f"{symbol}: {name} weight mismatch")
                score = component.get("normalized_score")
                if not isinstance(score, int) or score < 0 or score > 100:
                    _fail(f"{symbol}: {name} normalized score invalid")
                if "raw_facts" not in component or not isinstance(component.get("raw_facts"), dict):
                    _fail(f"{symbol}: {name} raw facts missing")
                if not component.get("rationale"):
                    _fail(f"{symbol}: {name} rationale missing")
                expected_points = round(score * COMPONENT_WEIGHTS[name] / 100, 2)
                if component.get("weighted_points") != expected_points:
                    _fail(f"{symbol}: {name} weighted points mismatch")
                point_sum += expected_points
            if assessment.get("score") != round(point_sum, 2):
                _fail(f"{symbol}: confidence score mismatch")
            refs = assessment.get("provenance_refs") or []
            if not refs:
                _fail(f"{symbol}: missing provenance refs")
            for ref in refs:
                if ref.get("source_product") == "event_studies":
                    event_id = ref.get("event_id")
                    if event_id not in studies_by_event:
                        _fail(f"{symbol}: unresolved event study ref")
                elif ref.get("source_product") == "signal_clusters":
                    if not ref.get("document_id") or not ref.get("evidence_sha256"):
                        _fail(f"{symbol}: incomplete signal provenance ref")
                else:
                    _fail(f"{symbol}: invalid provenance source product")
            financial_component = components["financial_model_quality"]
            raw_facts = financial_component["raw_facts"]
            expected_truth_status = truth_row.get("status") or "not_qualified"
            if raw_facts.get("status") != expected_truth_status or raw_facts.get("financial_truth_status") != expected_truth_status:
                _fail(f"{symbol}: financial-truth raw fact mismatch")
            if (raw_facts.get("model_input_readiness") or {}).get("status") != (model_row.get("status") or "unknown"):
                _fail(f"{symbol}: model-input readiness provenance mismatch")
            if expected_truth_status != "qualified" and financial_component.get("normalized_score") != 0:
                _fail(f"{symbol}: unqualified financial truth contributed model confidence")
            independence = components["signal_independence"]["raw_facts"]
            if len(independence.get("originators") or []) == 1 and components["signal_independence"]["normalized_score"] > 25:
                _fail(f"{symbol}: single originator over-scored for independence")
    return total


def main() -> None:
    signal_state = load_json(STATE / "company_intel" / "signal_clusters.json", {"companies": {}})
    operating_events = load_json(STATE / "company_intel" / "operating_events.json", {"companies": {}})
    event_studies = load_json(STATE / "company_intel" / "event_studies.json", {"studies": {}})
    model_inputs = load_json(STATE / "company_intel" / "financial_model_inputs.json", {"companies": {}})
    financial_truth = load_json(STATE / "company_intel" / "financial_truth_qualification.json", {"companies": {}})
    expected = build_intelligence_confidence(signal_state, operating_events, event_studies, model_inputs, financial_truth)
    expected_again = build_intelligence_confidence(signal_state, operating_events, event_studies, model_inputs, financial_truth)
    if _dump(expected) != _dump(expected_again):
        _fail("pure builder is not deterministic")
    _assert_safe_language(expected)
    total = _assert_shape(expected, signal_state, event_studies, model_inputs, financial_truth)
    mlcf_model = (model_inputs.get("companies") or {}).get("MLCF") or {}
    mlcf_truth = (financial_truth.get("companies") or {}).get("MLCF") or {}
    if mlcf_model.get("status") == "ready" and mlcf_truth.get("status") != "qualified":
        live_component = ((expected.get("companies", {}).get("MLCF", {}).get("assessments") or [{}])[0].get("components") or {}).get("financial_model_quality") or {}
        if live_component.get("normalized_score") != 0:
            _fail("MLCF: legacy ready inputs must not bypass red financial truth")
    qualified_truth = copy.deepcopy(financial_truth)
    qualified_truth.setdefault("companies", {}).setdefault("MLCF", {})["status"] = "qualified"
    qualified_component = ((build_intelligence_confidence(signal_state, operating_events, event_studies, model_inputs, qualified_truth)
                            .get("companies", {}).get("MLCF", {}).get("assessments") or [{}])[0].get("components") or {}).get("financial_model_quality") or {}
    if mlcf_model.get("status") == "ready" and qualified_component.get("normalized_score") != 100:
        _fail("MLCF: qualified financial truth must permit model-quality scoring")
    real = build()
    if _dump(expected) != _dump(real):
        _fail("writer output differs from pure builder")
    before = OUT.read_bytes()
    build()
    if before != OUT.read_bytes():
        _fail("builder output is not idempotent")
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_ci_slice.py")], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        _fail(result.stdout + result.stderr)
    slice_data = load_json(ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json", {"tickers": []})
    by_symbol = {row.get("symbol"): row for row in slice_data.get("tickers") or []}
    pilot = list(signal_state.get("pilot_symbols") or [])
    if set(by_symbol) != set(pilot):
        _fail("CI slice does not contain exact pilot")
    for symbol, state_row in real.get("companies", {}).items():
        if (by_symbol.get(symbol) or {}).get("intelligence_confidence") != state_row:
            _fail(f"{symbol}: CI slice confidence mismatch")
    print(f"intelligence_confidence: PASS ({len(pilot)} companies, {total} assessments)")


if __name__ == "__main__":
    main()
