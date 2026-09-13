from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from build_evidence_watchlist import OUT
from evidence_watchlist import FORBIDDEN_TEXT, ITEM_STATUSES, build_evidence_watchlist
from psx_data import ROOT, STATE, load_json
from ci_checker_helpers import assert_ci_slice_projection, without_root_meta
import build_ci_slice as ci_slice_builder


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
    allowed = {
        "no_advice",
        "no_odds_claims",
        "no_forward_estimates",
        "no_price_claims",
        "no_valuation_claims",
    }
    for value in _walk_strings(data):
        lowered = value.lower()
        if lowered in allowed or lowered.startswith("blocked_"):
            continue
        for term in FORBIDDEN_TEXT:
            if term in lowered:
                _fail(f"forbidden evidence-watchlist term present: {term}")


def _event_ids(row: dict) -> set[str]:
    return {event.get("event_id") for event in row.get("events") or [] if isinstance(event, dict) and event.get("event_id")}


def _assert_evidence(symbol: str, item: dict, documents: dict) -> None:
    for evidence in ((item.get("source_assertion") or {}).get("evidence") or []):
        doc = documents.get(evidence.get("document_id")) or {}
        if doc.get("status") != "ready":
            _fail(f"{symbol}: watch evidence document is not ready")
        if doc.get("content_sha256") != evidence.get("content_sha256"):
            _fail(f"{symbol}: watch evidence content hash mismatch")
        if doc.get("source_url") != evidence.get("source_url"):
            _fail(f"{symbol}: watch evidence source URL mismatch")
        if not isinstance(evidence.get("page"), int) or evidence["page"] < 1:
            _fail(f"{symbol}: watch evidence page invalid")
        if not evidence.get("evidence_sha256"):
            _fail(f"{symbol}: watch evidence hash missing")
    matched = item.get("matched_event") or {}
    for evidence in matched.get("evidence") or []:
        doc = documents.get(evidence.get("document_id")) or {}
        if doc.get("status") != "ready":
            _fail(f"{symbol}: matched evidence document is not ready")
        if doc.get("content_sha256") != evidence.get("content_sha256"):
            _fail(f"{symbol}: matched evidence content hash mismatch")


def _assert_shape(
    data: dict,
    thesis_state: dict,
    delivery_state: dict,
    confidence_state: dict,
    model_state: dict,
    truth_state: dict,
    operating_events: dict,
    signal_state: dict,
    pilot: list[str],
) -> int:
    if data.get("pilot_symbols") != pilot:
        _fail("pilot order mismatch")
    policy = data.get("policy") or {}
    for key in ("research_only", "no_advice", "categorical_only", "official_source_provenance_required", "same_company_exact_id_links_required", "private_user_theses_excluded"):
        if policy.get(key) is not True:
            _fail(f"policy flag missing: {key}")
    if set(data.get("status_vocabulary") or []) != ITEM_STATUSES:
        _fail("status vocabulary mismatch")
    for source_name, source_data in (
        ("thesis_monitoring", thesis_state),
        ("management_delivery", delivery_state),
        ("intelligence_confidence", confidence_state),
        ("operating_events", operating_events),
        ("signal_clusters", signal_state),
    ):
        if set(source_data.get("companies") or {}) != set(pilot):
            _fail(f"{source_name}: company boundary mismatch")
    if list((model_state.get("companies") or {}).keys()) and set(model_state.get("companies") or {}) != set(pilot):
        _fail("financial_model_inputs: company boundary mismatch")
    companies = data.get("companies") or {}
    if list(companies) != pilot:
        _fail("company order/boundary mismatch")
    documents = load_json(STATE / "company_documents.json", {"documents": {}}).get("documents") or {}
    total = 0
    seen_ids = set()
    for symbol in pilot:
        row = companies.get(symbol) or {}
        theses = (thesis_state.get("companies") or {}).get(symbol, {}).get("theses") or []
        records = (delivery_state.get("companies") or {}).get(symbol, {}).get("records") or []
        clusters = (signal_state.get("companies") or {}).get(symbol, {}).get("clusters") or []
        assessments = (confidence_state.get("companies") or {}).get(symbol, {}).get("assessments") or []
        model_row = (model_state.get("companies") or {}).get(symbol) or {}
        truth_row = (truth_state.get("companies") or {}).get(symbol) or {}
        events = _event_ids((operating_events.get("companies") or {}).get(symbol) or {})
        thesis_by_id = {thesis.get("thesis_id"): thesis for thesis in theses}
        record_by_id = {record.get("delivery_id"): record for record in records}
        cluster_by_id = {cluster.get("cluster_id"): cluster for cluster in clusters}
        confidence_by_id = {assessment.get("confidence_id"): assessment for assessment in assessments}
        if row.get("symbol") != symbol:
            _fail(f"{symbol}: row symbol mismatch")
        items = row.get("items") or []
        if row.get("status") != ("active_watch" if items else "no_active_watch"):
            _fail(f"{symbol}: row status mismatch")
        if len(items) != len(theses):
            _fail(f"{symbol}: watch item count does not match active theses")
        for item in items:
            total += 1
            watch_id = item.get("watch_id")
            if not watch_id or watch_id in seen_ids:
                _fail(f"{symbol}: duplicate/missing watch id")
            seen_ids.add(watch_id)
            if item.get("symbol") != symbol:
                _fail(f"{symbol}: item symbol mismatch")
            if item.get("status") not in ITEM_STATUSES:
                _fail(f"{symbol}: invalid item status")
            ids = item.get("ids") or {}
            thesis = thesis_by_id.get(ids.get("thesis_id"))
            record = record_by_id.get(ids.get("delivery_id"))
            cluster = cluster_by_id.get(ids.get("source_cluster_id"))
            if not thesis or not record or not cluster:
                _fail(f"{symbol}: unresolved thesis/delivery/cluster id")
            if record.get("thesis_id") != thesis.get("thesis_id"):
                _fail(f"{symbol}: delivery record linked to different thesis")
            if thesis.get("source_cluster_id") != cluster.get("cluster_id") or record.get("source_cluster_id") != cluster.get("cluster_id"):
                _fail(f"{symbol}: source cluster id mismatch")
            for key in ("assertion_key", "conflict_key"):
                if ids.get(key) != thesis.get(key) or ids.get(key) != record.get(key) or ids.get(key) != cluster.get(key):
                    _fail(f"{symbol}: {key} exact-link mismatch")
            confidence_id = ids.get("confidence_id")
            if confidence_id and confidence_id not in confidence_by_id:
                _fail(f"{symbol}: unresolved confidence id")
            expected_readiness = "qualified" if truth_row.get("status") == "qualified" else "not_qualified"
            if item.get("financial_readiness_status") != expected_readiness:
                _fail(f"{symbol}: financial truth readiness status mismatch")
            if (item.get("financial_readiness") or {}).get("downstream_status") != (truth_row.get("downstream") or {}):
                _fail(f"{symbol}: financial truth downstream mismatch")
            if ((item.get("financial_readiness") or {}).get("model_input_readiness") or {}).get("status") != (model_row.get("status") or "unknown"):
                _fail(f"{symbol}: model-input readiness mismatch")
            if ids.get("matched_event_id") and ids.get("matched_event_id") not in events:
                _fail(f"{symbol}: matched event crosses company boundary")
            source_event_ids = ids.get("source_event_ids") or []
            if set(source_event_ids) != set(thesis.get("linked_event_ids") or []):
                _fail(f"{symbol}: source event id mismatch")
            if not set(source_event_ids).issubset(events):
                _fail(f"{symbol}: source event crosses company boundary")
            if "score" in item or "aggregate_score" in item:
                _fail(f"{symbol}: numeric confidence score leaked into watchlist")
            _assert_evidence(symbol, item, documents)
    if (data.get("summary") or {}).get("active_symbols") != [s for s in pilot if (companies.get(s) or {}).get("items")]:
        _fail("summary active symbol order mismatch")
    return total


def _load_sources() -> tuple[dict, dict, dict, dict, dict, dict, dict, list[str]]:
    profiles = load_json(STATE / "company_profiles.json", {})
    pilot = (profiles.get("pilot") or {}).get("symbols") or []
    return (
        load_json(STATE / "company_intel" / "thesis_monitoring.json", {"companies": {}}),
        load_json(STATE / "company_intel" / "management_delivery.json", {"companies": {}}),
        load_json(STATE / "company_intel" / "intelligence_confidence.json", {"companies": {}}),
        load_json(STATE / "company_intel" / "financial_model_inputs.json", {"companies": {}}),
        load_json(STATE / "company_intel" / "financial_truth_qualification.json", {"companies": {}}),
        load_json(STATE / "company_intel" / "operating_events.json", {"companies": {}}),
        load_json(STATE / "company_intel" / "signal_clusters.json", {"companies": {}}),
        list(pilot),
    )


def main() -> None:
    thesis_state, delivery_state, confidence_state, model_state, truth_state, operating_events, signal_state, pilot = _load_sources()
    if len(pilot) != 20 or len(set(pilot)) != 20:
        _fail("pilot boundary must be exactly 20")
    expected = build_evidence_watchlist(
        thesis_state,
        delivery_state,
        confidence_state,
        model_state,
        truth_state,
        operating_events,
        signal_state,
        pilot_symbols=pilot,
    )
    if _dump(expected) != _dump(build_evidence_watchlist(thesis_state, delivery_state, confidence_state, model_state, truth_state, operating_events, signal_state, pilot_symbols=pilot)):
        _fail("pure builder is not deterministic")
    _assert_safe_language(expected)
    total = _assert_shape(expected, thesis_state, delivery_state, confidence_state, model_state, truth_state, operating_events, signal_state, pilot)
    if not OUT.exists():
        _fail("state/company_intel/evidence_watchlist.json missing")
    real = load_json(OUT, {})
    if _dump(without_root_meta(real)) != _dump(without_root_meta(expected)):
        _fail("authoritative watchlist differs from pure builder")
    with tempfile.TemporaryDirectory() as tmpdir:
        first = Path(tmpdir) / "first.json"
        second = Path(tmpdir) / "second.json"
        for path in (first, second):
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "build_evidence_watchlist.py"), "--out", str(path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                _fail((result.stdout or "") + (result.stderr or ""))
        if first.read_bytes() != second.read_bytes():
            _fail("builder output is not byte-idempotent")
    slice_path = ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json"
    for symbol, state_row in real.get("companies", {}).items():
        assert_ci_slice_projection(ci_slice_builder, slice_path, symbol, "evidence_watchlist", state_row)
    print(f"evidence_watchlist: PASS ({len(pilot)} companies, {total} items)")


if __name__ == "__main__":
    main()
