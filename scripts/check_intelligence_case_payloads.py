#!/usr/bin/env python3
"""Read-only contract checks for the two deterministic observed case payloads."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_ci_slice import build as build_slice
from build_intelligence_cases import (
    FOLLOW_THROUGH_DOC_ID,
    FOLLOW_THROUGH_EVENT_ID,
    MARI_CASE_ID,
    MARI_DOC_HASH,
    MARI_DOC_ID,
    MARI_EVENT_ID,
    MLCF_CASE_ID,
    PUBLIC_OFFER_DOC_ID,
    PUBLIC_OFFER_EVENT_ID,
    build as build_cases,
)
from psx_data import ROOT, STATE, load_json


OUT = STATE / "company_intel" / "intelligence_cases.json"
SLICE_OUT = ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json"
HEX64 = re.compile(r"^[0-9a-f]{64}$", re.I)
FORBIDDEN_KEYS = {"forecast", "valuation", "market_expectations", "price_target", "target_price", "recommendation", "probability", "expected_return"}
checks = 0


def check(condition: bool, message: str) -> None:
    global checks
    checks += 1
    if not condition:
        raise AssertionError(message)


def walk(value: object):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def snapshot(paths: list[Path]) -> dict[str, tuple[bool, str | None]]:
    result = {}
    for path in paths:
        if not path.exists():
            result[str(path)] = (False, None)
            continue
        result[str(path)] = (True, hashlib.sha256(path.read_bytes()).hexdigest())
    return result


def assert_evidence(ref: dict, event_id: str, document_id: str, page: int, content_hash: str) -> None:
    check(ref.get("event_id") == event_id, f"event mismatch: {ref.get('event_id')}")
    check(ref.get("document_id") == document_id, f"document mismatch: {ref.get('document_id')}")
    check(ref.get("page") == page, f"page mismatch for {document_id}")
    check(ref.get("content_sha256") == content_hash and HEX64.fullmatch(str(ref.get("content_sha256") or "")), f"hash mismatch for {document_id}")
    check(str(ref.get("source_url") or "").startswith("https://dps.psx.com.pk/download/document/"), f"non-PSX URL for {document_id}")
    check(bool(ref.get("text")) and ref.get("event_date") and ref.get("document_published_at"), f"incomplete evidence for {document_id}")


def main() -> None:
    watched = [OUT, SLICE_OUT]
    before = snapshot(watched)
    first = build_cases(write=False)
    second = build_cases(write=False)
    check(json.dumps(first, sort_keys=True, ensure_ascii=False, allow_nan=False) == json.dumps(second, sort_keys=True, ensure_ascii=False, allow_nan=False), "case builder is not deterministic")
    check(first["summary"] == {"company_count": 20, "observed_case_count": 2, "published_case_count": 0}, "case summary mismatch")
    check(set(first["companies"]) == set(first["pilot_symbols"]) and len(first["pilot_symbols"]) == 20, "pilot boundary mismatch")
    check(first["status_lifecycle"] == ["Observed", "Corroborated", "Modelled", "Validated", "Published"], "lifecycle vocabulary mismatch")

    mlcf = first["companies"]["MLCF"]["cases"][0]
    check(first["companies"]["MLCF"]["symbol"] == "MLCF" and mlcf["case_id"] == MLCF_CASE_ID, "MLCF identity mismatch")
    check(mlcf["status"] == "Observed" and mlcf["epistemic_type"] == "reported_fact", "MLCF lifecycle/epistemic mismatch")
    facts = {item["fact_id"]: item for item in mlcf["observed_facts"]}
    check(set(facts) == {"mlcf_pioc_public_offer_control", "mlcf_pioc_dispatch_inclusion"}, "MLCF fact set mismatch")
    values = {item["label"]: item["value"] for item in facts["mlcf_pioc_public_offer_control"]["reported_values"]}
    check(values == {"public_offer_shares": "up to 26,623,096 PIOC shares", "public_offer_percent": "11.72% shares", "spa_percent": "58.03% through Share Purchase Agreement(s)", "offer_price": "PKR 478.43 per share"}, "MLCF reported values mismatch")
    assert_evidence(facts["mlcf_pioc_public_offer_control"]["evidence"][0], PUBLIC_OFFER_EVENT_ID, PUBLIC_OFFER_DOC_ID, 3, "98cf83c9a286999c8006a7f73f490248f26694c9edbfc815b3dbd9188ee22a54")
    assert_evidence(facts["mlcf_pioc_dispatch_inclusion"]["evidence"][0], FOLLOW_THROUGH_EVENT_ID, FOLLOW_THROUGH_DOC_ID, 4, "744a0c710043d6e0a7de36bb99f21ca50f0f9346f6972b957f6733a47deae11f")

    mari = first["companies"]["MARI"]["cases"][0]
    check(first["companies"]["MARI"]["symbol"] == "MARI" and mari["case_id"] == MARI_CASE_ID, "MARI identity mismatch")
    check(mari["status"] == "Observed" and mari["epistemic_type"] == "reported_fact", "MARI lifecycle/epistemic mismatch")
    mari_fact = mari["observed_facts"][0]
    check(mari_fact["fact_id"] == "mari_peshawar_working_interest_acquisition", "MARI fact mismatch")
    assert_evidence(mari_fact["evidence"][0], MARI_EVENT_ID, MARI_DOC_ID, 1, MARI_DOC_HASH)
    check(MARI_DOC_ID != "psx:265594" and MARI_DOC_HASH == "c13ccb4de58ad005bca106942721490593fe219ff45906c68280ea7856192e42", "MARI strategy document substituted")

    for case in (mlcf, mari):
        check(case["promotion_blocks"].keys() >= {"Corroborated", "Modelled", "Published"}, f"promotion blocks missing for {case['case_id']}")
        check(all(case["policy"].get(key) is True for key in ("observed_only", "no_forecast", "no_valuation", "no_market_expectations", "no_recommendation", "reported_values_only")), f"policy missing for {case['case_id']}")
        cutoff = case["as_of"]
        for ref in case["source_lineage"]:
            check(ref["event_date"] <= cutoff and ref["document_published_at"] <= cutoff, f"evidence after case cutoff for {case['case_id']}")
        for key, _value in walk(case):
            check(str(key).lower() not in FORBIDDEN_KEYS, f"formal output key emitted: {key}")

    sliced = build_slice(write=False)
    rows = {row["symbol"]: row for row in sliced["tickers"]}
    check(rows["MLCF"]["intelligence_cases"] == first["companies"]["MLCF"], "MLCF case row not attached exactly")
    check(rows["MARI"]["intelligence_cases"] == first["companies"]["MARI"], "MARI case row not attached exactly")
    for symbol, row in rows.items():
        payload = row.get("intelligence_cases") or {}
        check(payload.get("symbol") == symbol, f"case payload crossed ticker boundary: {symbol}")
        if symbol not in {"MLCF", "MARI"}:
            check(payload.get("case_count") == 0 and payload.get("cases") == [], f"unexpected case on {symbol}")

    after = snapshot(watched)
    check(before == after, "payload checker wrote an artifact")
    if OUT.exists():
        check(load_json(OUT, {}) == first, "generated case state differs from deterministic builder output")
    print(f"intelligence_case_payloads: PASS ({checks} assertions)")


try:
    main()
except Exception as error:
    print(f"intelligence_case_payloads: FAIL — {error}")
    raise SystemExit(1)
