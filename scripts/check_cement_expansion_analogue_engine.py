"""Focused unit and adversarial checks for Cement Expansion Analogue Engine."""
from __future__ import annotations
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cement_expansion_analogue_engine as engine
from ci_checker_helpers import without_root_meta
from psx_data import STATE, load_json

def _fail(message: str) -> None:
    raise AssertionError(message)

def _fixture_candidate(i: int, sym: str = "DGKC", mature_1q: bool = True) -> dict:
    return {
        "candidate_id": f"cand_test_{sym}_{i}",
        "project_id": f"proj_{sym}_{i}",
        "symbol": sym,
        "sector": "Cement",
        "event_family": "cement_clinker_line_commissioning",
        "event_type": "capacity_expansion",
        "event_subtype": "cement_clinker_line_commissioning",
        "effective_date": f"2024-0{i}-15",
        "information_available_at": f"2024-0{i}-15",
        "source": {
            "id": f"psx:20000{i}",
            "hash": "a" * 64,
            "page": 1,
            "url": f"https://dps.psx.com.pk/download/document/20000{i}.pdf",
        },
        "horizons": {
            "1Q": {"status": "mature" if mature_1q else "unavailable", "return_pct": 5.0 * i if mature_1q else None, "endpoint_date": f"2024-0{i+3}-15"},
            "2Q": {"status": "mature" if mature_1q else "unavailable", "return_pct": 8.0 * i if mature_1q else None, "endpoint_date": f"2024-0{i+6}-15"},
            "4Q": {"status": "unavailable", "return_pct": None},
            "8Q": {"status": "unavailable", "return_pct": None},
        },
    }

def _test_positive_distribution_n3() -> None:
    pool = [_fixture_candidate(1, "DGKC"), _fixture_candidate(2, "LUCK"), _fixture_candidate(3, "MLCF")]
    res = engine.evaluate_cement_expansion_lane(candidate_pool=pool, cutoff_date=date(2026, 1, 1))
    if res["distribution_status"] != "partial_sample_ready":
        _fail("N=3 mature in 1Q/2Q but 0 in 4Q/8Q must yield partial_sample_ready status")
    dist_1q = res["horizon_distributions"]["1Q"]
    if dist_1q["status"] != "available" or dist_1q["n"] != 3:
        _fail(f"1Q distribution must be available with n=3: {dist_1q}")
    if dist_1q["mean_return_pct"] != 10.0 or dist_1q["median_return_pct"] != 10.0:
        _fail(f"1Q mean/median return calculation mismatch: {dist_1q}")

def _test_fail_closed_thin_sample_n2() -> None:
    pool = [_fixture_candidate(1, "DGKC"), _fixture_candidate(2, "LUCK")]
    res = engine.evaluate_cement_expansion_lane(candidate_pool=pool, cutoff_date=date(2026, 1, 1))
    if res["distribution_status"] != "insufficient_sample":
        _fail("N=2 candidates must fail closed with insufficient_sample status")
    dist_1q = res["horizon_distributions"]["1Q"]
    if dist_1q["status"] != "suppressed" or dist_1q["mean_return_pct"] is not None:
        _fail(f"1Q stats must be suppressed when N < 3: {dist_1q}")

def _test_premature_endpoint_suppression() -> None:
    cand = _fixture_candidate(1, "DGKC")
    # 1Q target date is 2024-04-15 (3 months after 2024-01-15). Set endpoint before target date:
    cand["horizons"]["1Q"]["endpoint_date"] = "2024-03-01"
    pool = [cand, _fixture_candidate(2, "LUCK"), _fixture_candidate(3, "MLCF")]
    res = engine.evaluate_cement_expansion_lane(candidate_pool=pool, cutoff_date=date(2026, 1, 1))
    dist_1q = res["horizon_distributions"]["1Q"]
    if dist_1q["n"] != 2 or dist_1q["status"] != "suppressed":
        _fail(f"Premature endpoint must be excluded from mature sample: {dist_1q}")

def _test_source_qualification_violations() -> None:
    bad_page = _fixture_candidate(1, "DGKC")
    bad_page["source"]["page"] = 0
    if not any("missing_or_invalid_source_page" in v for v in engine.validate_analogue_candidate(bad_page)):
        _fail("page < 1 must be rejected")

    bad_url = _fixture_candidate(1, "DGKC")
    bad_url["source"]["url"] = "invalid_url"
    if not any("missing_or_invalid_source_url" in v for v in engine.validate_analogue_candidate(bad_url)):
        _fail("invalid URL must be rejected")

    bad_hash = _fixture_candidate(1, "DGKC")
    bad_hash["source"]["hash"] = "short_hash"
    if not any("missing_or_malformed_content_sha256" in v for v in engine.validate_analogue_candidate(bad_hash)):
        _fail("non-64 hex hash must be rejected")

def _test_duplicate_source_deduplication() -> None:
    # Simulated repeated MLCF disclosures from psx:263397
    cand1 = _fixture_candidate(1, "MLCF")
    cand1["source"]["id"] = "psx:263397"
    cand2 = _fixture_candidate(1, "MLCF")
    cand2["source"]["id"] = "psx:263397"
    cand2["candidate_id"] = "cand_test_MLCF_duplicate_row"
    deduped = engine.deduplicate_observations([cand1, cand2])
    if len(deduped) != 1:
        _fail(f"Repeated disclosures from same source/project must deduplicate to 1, got {len(deduped)}")

def _test_mismatched_mna_rejection() -> None:
    mna_cand = {
        "candidate_id": "cand_mlcf_pioc",
        "symbol": "MLCF",
        "event_family": "corporate_equity_control_acquisition",
        "event_type": "acquisition_divestment",
        "event_subtype": "acquisition",
        "effective_date": "2025-12-18",
        "source": {"id": "psx:267429", "hash": "c" * 64},
    }
    violations = engine.validate_analogue_candidate(mna_cand, cutoff_date=date(2026, 1, 1))
    if not any("is corporate M&A/control" in v for v in violations):
        _fail("M&A corporate control event must be explicitly rejected from cement expansion")

def _test_deduplication() -> None:
    cand1 = _fixture_candidate(1, "DGKC")
    cand2 = _fixture_candidate(1, "DGKC")
    cand2["effective_date"] = "2024-02-15"
    deduped = engine.deduplicate_observations([cand1, cand2])
    if len(deduped) != 1:
        _fail(f"Duplicate project disclosures must deduplicate into 1 episode, got {len(deduped)}")

def _test_no_advice_leak(data: dict) -> None:
    text = json.dumps(data).lower()
    for phrase in ("you should buy", "you should sell", "price target", "target price"):
        if re.search(r"\b" + re.escape(phrase) + r"\b", text):
            _fail(f"Disallowed advice phrase leaked: {phrase}")

def main() -> None:
    _test_positive_distribution_n3()
    _test_fail_closed_thin_sample_n2()
    _test_premature_endpoint_suppression()
    _test_source_qualification_violations()
    _test_duplicate_source_deduplication()
    _test_mismatched_mna_rejection()
    _test_deduplication()

    # Real-mode build and contract test
    rebuilt = engine.build(write=False)
    _test_no_advice_leak(rebuilt)
    if rebuilt.get("schema_version") != 1 or rebuilt.get("product_version") != engine.PRODUCT_VERSION:
        _fail("Schema version or product version mismatch")
    if rebuilt.get("distribution_status") != "insufficient_sample":
        _fail("Real retained state must report insufficient_sample while mature exact events < 3")
    queue = rebuilt.get("discovery_requirements_queue") or []
    if len(queue) != 3:
        _fail(f"Discovery requirements queue must contain exactly 3 prioritized slots, got {len(queue)}")

    path = engine.OUT
    if path.exists():
        saved = load_json(path, {})
        if json.dumps(without_root_meta(saved), sort_keys=True) != json.dumps(without_root_meta(rebuilt), sort_keys=True):
            _fail("Saved cement expansion analogue distribution is not deterministic with builder")

    print("check_cement_expansion_analogue_engine: PASS (all unit, adversarial and real-state checks passed)")

if __name__ == "__main__":
    main()
