"""Validate Company Brain source-index rows against retained CI products."""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_company_brains import (
    OUT,
    ROW_METADATA_KEYS,
    SOURCE_INDEX_PRODUCT_META,
    STATE_METADATA_KEYS,
    build,
    _state_metadata,
)
from intelligence_types import SOURCE_INDEX_PRODUCTS
from psx_data import STATE, load_json
from ci_checker_helpers import without_root_meta


ADVICE_PHRASES = ("you should", "target price", "price target", "buy recommendation", "sell recommendation")


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _picked(mapping: dict, keys: tuple[str, ...]) -> dict:
    return {key: mapping[key] for key in keys if key in mapping}


def _iso_day(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value[:10]
    try:
        date.fromisoformat(text)
    except ValueError:
        return None
    return text


def _walk(value: object):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _resolve_pointer(state: dict, pointer: str) -> object:
    if not pointer.startswith("/"):
        raise AssertionError(f"invalid JSON pointer {pointer!r}")
    current: object = state
    for raw_part in pointer.split("/")[1:]:
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise AssertionError(f"unresolved JSON pointer {pointer!r}")
    return current


def _assert_no_advice(value: object, label: str) -> None:
    text = _dump(value).lower()
    for phrase in ADVICE_PHRASES:
        if phrase in text:
            raise AssertionError(f"{label}: advice language leaked: {phrase}")


def _assert_no_lookahead(ref: dict, row: dict, state: dict, label: str) -> None:
    cutoff = _iso_day(state.get("as_of"))
    if not cutoff:
        return
    for key, item in _walk(ref):
        if key in {"available_on", "available_at", "published_at", "detected_at", "effective_date"}:
            day = _iso_day(item)
            if day and day > cutoff:
                raise AssertionError(f"{label}: {key} is after product cutoff")
    for provenance in row.get("provenance") or []:
        day = _iso_day((provenance or {}).get("available_on"))
        if day and day > cutoff:
            raise AssertionError(f"{label}: source provenance is after product cutoff")


def _assert_blocked_preserved(ref: dict, row: dict, label: str) -> None:
    if row.get("status") != "blocked":
        return
    metadata = ref.get("row_metadata") or {}
    if "result" in row and metadata.get("result") is not row.get("result"):
        raise AssertionError(f"{label}: blocked result was not preserved as null")
    if "provenance" in row and metadata.get("provenance") != row.get("provenance"):
        raise AssertionError(f"{label}: blocked provenance was not preserved")


def _assert_ref(symbol: str, product: str, ref: dict, state: dict) -> None:
    meta = SOURCE_INDEX_PRODUCT_META[product]
    label = f"{symbol}:{product}"
    expected_path = f"{meta['state_path']}#/companies/{symbol}"
    if ref.get("source_product") != product:
        raise AssertionError(f"{label}: source product mismatch")
    if ref.get("state_path") != meta["state_path"] or ref.get("source_path") != expected_path:
        raise AssertionError(f"{label}: source path mismatch")
    if ref.get("pointer") != f"/companies/{symbol}":
        raise AssertionError(f"{label}: pointer mismatch")
    row = _resolve_pointer(state, ref["pointer"])
    if not isinstance(row, dict) or not row:
        raise AssertionError(f"{label}: pointer did not resolve to a source row")
    if ref.get("symbol") != (row.get("symbol") or symbol):
        raise AssertionError(f"{label}: symbol mismatch")
    state_metadata = ref.get("state_metadata") or {}
    if "_meta" in state_metadata:
        raise AssertionError(f"{label}: generated integrity metadata leaked into source index")
    if ref.get("state_metadata") != _state_metadata(state):
        raise AssertionError(f"{label}: state metadata was not preserved exactly")
    if ref.get("row_metadata") != _picked(row, ROW_METADATA_KEYS):
        raise AssertionError(f"{label}: row metadata was not preserved exactly")
    if "status" in row and (ref.get("row_metadata") or {}).get("status") != row.get("status"):
        raise AssertionError(f"{label}: status was not preserved exactly")
    if "result" in row and (ref.get("row_metadata") or {}).get("result") != row.get("result"):
        raise AssertionError(f"{label}: result was not preserved exactly")
    if "provenance" in row and (ref.get("row_metadata") or {}).get("provenance") != row.get("provenance"):
        raise AssertionError(f"{label}: provenance was not preserved exactly")
    if "source_url" in ref:
        raise AssertionError(f"{label}: invented top-level source_url")
    _assert_blocked_preserved(ref, row, label)
    _assert_no_lookahead(ref, row, state, label)
    _assert_no_advice(ref, label)


def main() -> None:
    if not OUT.exists():
        raise AssertionError("company_brains.json is missing")
    profiles = load_json(STATE / "company_profiles.json", {})
    pilot_order = list((profiles.get("pilot") or {}).get("symbols") or [])
    pilot = set(pilot_order)
    if len(pilot_order) != 20 or len(pilot) != 20:
        raise AssertionError("profile pilot boundary must be exactly 20")
    brain = load_json(OUT, {})
    if set(brain.get("pilot_symbols") or []) != pilot or set(brain.get("companies") or {}) != pilot:
        raise AssertionError("company_brains: exact 20-company pilot mismatch")
    if brain.get("source_index_products") != list(SOURCE_INDEX_PRODUCTS):
        raise AssertionError("source index product registry mismatch")
    states = {product: load_json(meta["path"], {}) for product, meta in SOURCE_INDEX_PRODUCT_META.items()}
    for product, state in states.items():
        if set((state.get("companies") or {})) != pilot:
            raise AssertionError(f"{product}: source companies do not match exact pilot")
    for symbol, company in (brain.get("companies") or {}).items():
        index = company.get("source_index") or {}
        if set(index) != set(SOURCE_INDEX_PRODUCTS):
            raise AssertionError(f"{symbol}: source index coverage mismatch")
        for product in SOURCE_INDEX_PRODUCTS:
            _assert_ref(symbol, product, index[product], states[product])
    if _dump(without_root_meta(brain)) != _dump(without_root_meta(build(write=False))):
        raise AssertionError("company_brains rebuild is not deterministic with source index")
    print(f"company_brain_source_index: PASS ({len(pilot)} companies, {len(SOURCE_INDEX_PRODUCTS)} source rows each)")


if __name__ == "__main__":
    main()
