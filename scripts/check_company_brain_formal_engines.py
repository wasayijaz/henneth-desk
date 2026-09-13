"""Validate Company Brain references to formal financial engine products."""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_company_brains import FORMAL_ENGINE_PRODUCTS, OUT, build
from psx_data import STATE, load_json
from ci_checker_helpers import without_root_meta


PRODUCTS = tuple(FORMAL_ENGINE_PRODUCTS)
ADVICE_PHRASES = ("buy", "sell", "accumulate", "target price", "price target", "you should")
BLOCKED_STATUSES = frozenset(("blocked", "blocked_financial_truth_not_qualified"))


def equivalent_status(left: object, right: object) -> bool:
    return left == right or (left in BLOCKED_STATUSES and right in BLOCKED_STATUSES)


def fail(message: str) -> None:
    raise AssertionError(message)


def dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def iso_day(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value[:10]
    try:
        date.fromisoformat(text)
    except ValueError:
        return None
    return text


def assert_clean(value: object, label: str) -> None:
    text = dump(value).lower()
    for phrase in ADVICE_PHRASES:
        if phrase in text:
            fail(f"{label}: advice language leaked: {phrase}")
    for key, item in walk(value):
        if isinstance(item, float) and not math.isfinite(item):
            fail(f"{label}: non-finite value at {key}")


def load_engines() -> dict:
    engines = {}
    for product, meta in FORMAL_ENGINE_PRODUCTS.items():
        state = load_json(meta["path"], {})
        if state.get("kind") != product:
            fail(f"{product}: kind mismatch")
        engines[product] = state
    return engines


def assert_engine_shape(product: str, state: dict, pilot: set[str]) -> None:
    symbols = state.get("pilot_symbols") or []
    if len(symbols) != 20 or set(symbols) != pilot:
        fail(f"{product}: exact 20 pilot mismatch")
    companies = state.get("companies") or {}
    if set(companies) != pilot:
        fail(f"{product}: company rows do not match pilot")
    if (state.get("policy") or {}).get("no_advice") is not True:
        fail(f"{product}: no-advice policy missing")
    if (state.get("policy") or {}).get("no_output_without_approved_source_labelled_assumptions") is not True:
        fail(f"{product}: source-truth policy missing")
    summary = state.get("summary") or {}
    computed = sum(1 for row in companies.values() if row.get("status") == "computed")
    if summary.get("computed_company_count") != computed:
        fail(f"{product}: computed summary mismatch")
    if summary.get("blocked_company_count") != 20 - computed:
        fail(f"{product}: blocked summary mismatch")
    cutoff = iso_day(state.get("as_of"))
    for symbol, row in companies.items():
        if row.get("symbol") != symbol:
            fail(f"{product}:{symbol}: symbol mismatch")
        if row.get("formula_id") != state.get("formula_id"):
            fail(f"{product}:{symbol}: formula mismatch")
        if (row.get("policy") or {}).get("research_only") is not True or (row.get("policy") or {}).get("no_advice") is not True:
            fail(f"{product}:{symbol}: row policy mismatch")
        if row.get("status") in BLOCKED_STATUSES:
            if row.get("result") is not None:
                fail(f"{product}:{symbol}: blocked row carried result")
            if row.get("provenance") not in ([], None):
                fail(f"{product}:{symbol}: blocked row carried provenance")
            if not row.get("missing_requirements"):
                fail(f"{product}:{symbol}: blocked row missing requirements")
        elif row.get("status") == "computed":
            if not isinstance(row.get("result"), dict) or not row.get("provenance"):
                fail(f"{product}:{symbol}: computed row lacks result/provenance")
            for ref in row.get("provenance") or []:
                available_on = iso_day(ref.get("available_on"))
                if not available_on:
                    fail(f"{product}:{symbol}: provenance missing available_on")
                if cutoff and available_on > cutoff:
                    fail(f"{product}:{symbol}: provenance after product cutoff")
                if ref.get("record_type") == "qualified_actual":
                    if not ref.get("fact_id") or not ref.get("document_id") or not ref.get("source_url"):
                        fail(f"{product}:{symbol}: qualified actual provenance is not source-resolvable")
                elif not (ref.get("source_id") and ref.get("source_label") and (ref.get("source_url") or ref.get("source_path"))):
                    fail(f"{product}:{symbol}: assumption provenance is not source-resolvable")
        else:
            fail(f"{product}:{symbol}: invalid status {row.get('status')}")
    assert_clean(state, product)


def expected_ref(product: str, state: dict, symbol: str) -> dict:
    row = (state.get("companies") or {}).get(symbol) or {}
    meta = FORMAL_ENGINE_PRODUCTS[product]
    ref = {
        "type": "formal_engine_product",
        "source_product": product,
        "source_path": f"{meta['state_path']}#/companies/{symbol}",
        "symbol": row.get("symbol") or symbol,
        "kind": state.get("kind") or product,
        "engine_version": state.get("engine_version"),
        "formula_id": row.get("formula_id") or state.get("formula_id"),
        "status": row.get("status") or "blocked",
        "reason": row.get("reason"),
        "result": row.get("result"),
        "provenance": row.get("provenance") or [],
        "policy": row.get("policy") or {},
        "as_of": iso_day(state.get("as_of")),
        "brain_path": f"companies/{symbol}/domains/{meta['brain_path']}",
    }
    if row.get("missing_requirements") is not None:
        ref["missing_requirements"] = row["missing_requirements"]
    return ref


def assert_brain_links(brain: dict, engines: dict, pilot: set[str]) -> None:
    if len(brain.get("pilot_symbols") or []) != 20 or set(brain.get("pilot_symbols") or []) != pilot:
        fail("company_brains: exact 20 pilot mismatch")
    companies = brain.get("companies") or {}
    if set(companies) != pilot:
        fail("company_brains: company rows do not match pilot")
    for symbol, company in companies.items():
        refs = company.get("formal_engine_refs")
        if set(refs or {}) != set(PRODUCTS):
            fail(f"{symbol}: formal engine reference coverage mismatch")
        domains = company.get("domains") or {}
        for product, state in engines.items():
            ref = refs[product]
            expected = expected_ref(product, state, symbol)
            comparable_ref = dict(ref)
            comparable_expected = dict(expected)
            if equivalent_status(comparable_ref.get("status"), comparable_expected.get("status")):
                comparable_ref["status"] = comparable_expected["status"] = "blocked"
            if comparable_ref != comparable_expected:
                fail(f"{symbol}: {product} Brain ref does not match authoritative state")
            if ref["source_path"] != f"{FORMAL_ENGINE_PRODUCTS[product]['state_path']}#/companies/{symbol}":
                fail(f"{symbol}: {product} source path is not resolvable")
            source_row = (state.get("companies") or {}).get(symbol) or {}
            if not equivalent_status(ref["status"], source_row.get("status")):
                fail(f"{symbol}: {product} status not preserved")
            if ref["result"] != source_row.get("result"):
                fail(f"{symbol}: {product} result not preserved")
            if ref["provenance"] != (source_row.get("provenance") or []):
                fail(f"{symbol}: {product} provenance not preserved")
            if ref["status"] in BLOCKED_STATUSES and (ref["result"] is not None or ref["provenance"]):
                fail(f"{symbol}: {product} blocked ref claims computed output")
            domain_name = FORMAL_ENGINE_PRODUCTS[product]["brain_path"]
            if (domains.get(domain_name) or {}).get("status") != "blocked":
                fail(f"{symbol}: {product} changed blocked domain status")
        if (domains.get("forecasts") or {}).get("object_refs") or (domains.get("valuation") or {}).get("object_refs"):
            fail(f"{symbol}: formal domains gained intelligence objects")
    assert_clean(brain, "company_brains")


def main() -> None:
    if not OUT.exists():
        fail("company_brains.json is missing")
    profiles = load_json(STATE / "company_profiles.json", {})
    pilot_order = list((profiles.get("pilot") or {}).get("symbols") or [])
    pilot = set(pilot_order)
    if len(pilot_order) != 20 or len(pilot) != 20:
        fail("profile pilot boundary must be exactly 20")
    engines = load_engines()
    for product, state in engines.items():
        assert_engine_shape(product, state, pilot)
        negative = json.loads(json.dumps(state))
        negative_symbol = next(iter(pilot))
        negative["companies"][negative_symbol]["status"] = "blocked_unknown_status"
        try:
            assert_engine_shape(product, negative, pilot)
        except AssertionError:
            pass
        else:
            fail(f"{product}: unknown status was accepted")
    brain = load_json(OUT, {})
    assert_brain_links(brain, engines, pilot)
    if dump(without_root_meta(brain)) != dump(without_root_meta(build(write=False))):
        fail("company_brains rebuild is not deterministic with formal engine links")
    print("company_brain_formal_engines: PASS (20 companies, 3 formal refs each)")


if __name__ == "__main__":
    main()
