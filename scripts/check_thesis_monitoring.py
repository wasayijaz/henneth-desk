from __future__ import annotations

import json
import subprocess
import sys

from build_thesis_monitoring import OUT, build
from psx_data import ROOT, STATE, load_json
from thesis_monitoring import FORBIDDEN_TEXT, build_thesis_monitoring


def _fail(message: str) -> None:
    raise AssertionError(message)


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
    allowed_paths = {"no_forecasts"}
    text = json.dumps(data, sort_keys=True).lower()
    for term in FORBIDDEN_TEXT:
        if term in text:
            _fail(f"forbidden thesis-monitoring term present: {term}")
    for value in _walk_strings(data):
        lowered = value.lower()
        if "forecast" in lowered and value not in allowed_paths and not value.startswith("blocked_"):
            _fail(f"unsafe forecast wording: {value}")
        if "probability" in lowered:
            _fail(f"unsafe probability wording: {value}")


def _assert_shape(data: dict, signal_state: dict, financial_state: dict, truth_state: dict) -> int:
    symbols = list((signal_state.get("pilot_symbols") or []))
    if len(symbols) != 20:
        _fail("expected 20 pilot symbols")
    if data.get("pilot_symbols") != symbols:
        _fail("pilot symbol order mismatch")
    companies = data.get("companies") or {}
    if set(companies) != set(symbols):
        _fail("company boundary mismatch")
    total = 0
    seen_ids = set()
    for symbol in symbols:
        row = companies.get(symbol) or {}
        signal_row = (signal_state.get("companies") or {}).get(symbol) or {}
        model_row = (financial_state.get("companies") or {}).get(symbol) or {}
        truth_row = (truth_state.get("companies") or {}).get(symbol) or {}
        theses = row.get("theses") or []
        clusters = signal_row.get("clusters") or []
        if row.get("source_cluster_count") != len(clusters):
            _fail(f"{symbol} source cluster count mismatch")
        if row.get("active_thesis_count") != len(theses):
            _fail(f"{symbol} active thesis count mismatch")
        if len(theses) != len(clusters):
            _fail(f"{symbol} thesis count does not match retained clusters")
        readiness = row.get("financial_readiness") or {}
        expected_status = "qualified" if truth_row.get("status") == "qualified" else "not_qualified"
        if readiness.get("status") != expected_status:
            _fail(f"{symbol} financial truth readiness mismatch")
        if readiness.get("downstream_status") != (truth_row.get("downstream") or {}):
            _fail(f"{symbol} financial truth downstream mismatch")
        if (readiness.get("model_input_readiness") or {}).get("status") != (model_row.get("status") or "unknown"):
            _fail(f"{symbol} model-input readiness mismatch")
        cluster_ids = {cluster.get("cluster_id") for cluster in clusters}
        for thesis in theses:
            total += 1
            thesis_id = thesis.get("thesis_id")
            if not thesis_id or thesis_id in seen_ids:
                _fail(f"{symbol} duplicate/missing thesis id")
            seen_ids.add(thesis_id)
            if thesis.get("symbol") != symbol:
                _fail(f"{symbol} thesis symbol mismatch")
            if thesis.get("source_cluster_id") not in cluster_ids:
                _fail(f"{symbol} thesis references unknown cluster")
            if thesis.get("status") not in {"Strengthening", "Stable", "Weakening", "Broken"}:
                _fail(f"{symbol} invalid canonical thesis status")
            expected_status = {
                "inconsistent": "Broken",
                "supersession": "Weakening",
                "convergent": "Strengthening",
                "corroborated": "Strengthening",
            }.get(str(thesis.get("assessment") or "").lower(), "Stable")
            if thesis.get("status") != expected_status:
                _fail(f"{symbol} canonical thesis status mismatch")
            if thesis.get("monitoring_state") not in {"active_monitoring", "superseded_monitoring", "contradicted_or_inconsistent"}:
                _fail(f"{symbol} invalid monitoring state")
            if thesis.get("intelligence_type") != "inference":
                _fail(f"{symbol} invalid thesis intelligence type")
            if not thesis.get("prove_checks") or not thesis.get("kill_checks") or not thesis.get("watch_items"):
                _fail(f"{symbol} missing monitoring checks")
            for evidence in thesis.get("evidence") or []:
                if not str(evidence.get("source_url") or "").startswith("https://"):
                    _fail(f"{symbol} evidence missing safe source url")
                if not evidence.get("content_sha256") or len(evidence.get("content_sha256")) != 64:
                    _fail(f"{symbol} evidence missing content hash")
                if not isinstance(evidence.get("page"), int) or evidence.get("page") < 1:
                    _fail(f"{symbol} evidence page invalid")
    return total


def main() -> None:
    checks = 0
    signal_state = load_json(STATE / "company_intel" / "signal_clusters.json", {"companies": {}})
    financial_state = load_json(STATE / "company_intel" / "financial_model_inputs.json", {"companies": {}})
    truth_state = load_json(STATE / "company_intel" / "financial_truth_qualification.json", {"companies": {}})
    expected = build_thesis_monitoring(signal_state, financial_state, truth_state, as_of="2026-01-01T00:00:00Z")
    expected_again = build_thesis_monitoring(signal_state, financial_state, truth_state, as_of="2026-01-01T00:00:00Z")
    if json.dumps(expected, sort_keys=True) != json.dumps(expected_again, sort_keys=True):
        _fail("pure builder is not deterministic")
    checks += 1
    _assert_safe_language(expected); checks += 1
    total = _assert_shape(expected, signal_state, financial_state, truth_state); checks += 1
    real = build()
    _assert_safe_language(real); checks += 1
    total = _assert_shape(real, signal_state, financial_state, truth_state); checks += 1
    before = OUT.read_bytes()
    build()
    if before != OUT.read_bytes():
        _fail("builder output is not idempotent")
    checks += 1
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_ci_slice.py")], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        _fail(result.stdout + result.stderr)
    print(f"thesis_monitoring: PASS ({checks} assertions, {total} active theses)")


if __name__ == "__main__":
    main()
