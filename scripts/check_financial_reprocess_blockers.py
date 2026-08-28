"""Focused contract checks for metadata-only financial restage blockers."""
from __future__ import annotations

import json
import re
from typing import Any

from build_financial_reprocess_blockers import (
    APPROVED_BLOCKED_OUTCOMES,
    OUT,
    PARSER_REVISION,
    build,
)
from psx_data import load_json


FORBIDDEN_KEYS = {"normalized_value", "raw_value", "value", "amount", "eps", "revenue", "pat"}
ALLOWED_KEY_PATHS = {
    "psx_file_bytes",
    "psx_page_count",
    "document_count",
    "company_count",
    "blocked_document_count",
    "required_blocked_document_count",
    "required_for_input_readiness_count",
    "qualified_period_count",
}


def _fail(message: str) -> None:
    raise AssertionError(message)


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _walk(value: Any, path: tuple[str, ...] = ()):
    if isinstance(value, dict):
        for key, item in value.items():
            next_path = path + (str(key),)
            yield next_path, item
            yield from _walk(item, next_path)
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            yield from _walk(item, path + (str(idx),))


def _assert_metadata_only(payload: dict[str, Any]) -> None:
    policy = payload.get("policy") or {}
    for key in ("metadata_only", "no_download", "no_pdf_parsing", "no_receipt_write",
                "no_allowlist_change", "no_numeric_facts", "no_forecast_or_valuation"):
        if policy.get(key) is not True:
            _fail(f"missing policy {key}=true")
    for path, value in _walk(payload):
        key = path[-1]
        if key in FORBIDDEN_KEYS and key not in ALLOWED_KEY_PATHS:
            _fail(f"numeric fact-like key present at {'.'.join(path)}")
        if key in {"forecast_value", "valuation_value", "target_price", "fair_value"}:
            _fail(f"forecast/valuation output key present at {'.'.join(path)}")


def _assert_shape(payload: dict[str, Any]) -> None:
    pilot = payload.get("pilot_symbols") or []
    if len(pilot) != 20 or len(set(pilot)) != 20:
        _fail("pilot scope must be exactly 20 unique symbols")
    documents = payload.get("blocked_documents") or []
    if len(documents) != len(APPROVED_BLOCKED_OUTCOMES):
        _fail("blocked document count mismatch")
    ids = [row.get("document_id") for row in documents]
    if ids != list(APPROVED_BLOCKED_OUTCOMES):
        _fail("blocked documents must preserve manifest/allowlist order")
    companies = payload.get("companies") or {}
    if set(companies) != {"DGKC"}:
        _fail("unexpected blocker company boundary")
    required_count = 0
    for row in documents:
        doc_id = row.get("document_id")
        outcome = APPROVED_BLOCKED_OUTCOMES.get(str(doc_id)) or {}
        if not re.fullmatch(r"psx:\d+", str(doc_id or "")):
            _fail(f"{doc_id}: invalid document id")
        if row.get("parser_revision") != PARSER_REVISION:
            _fail(f"{doc_id}: parser revision mismatch")
        if row.get("status") != "blocked_by_current_gate":
            _fail(f"{doc_id}: not marked blocked")
        if row.get("gate") != outcome.get("gate") or row.get("reason") != outcome.get("reason"):
            _fail(f"{doc_id}: blocker reason drift")
        if row.get("canonical_state_committed") or row.get("receipt_written") or row.get("facts_emitted"):
            _fail(f"{doc_id}: blocker claims a side effect")
        if not str(row.get("source_url") or "").startswith("https://dps.psx.com.pk/download/document/"):
            _fail(f"{doc_id}: source URL is not official PSX DPS")
        if row.get("next_status") == "required_for_input_readiness":
            required_count += 1
    if (payload.get("summary") or {}).get("required_for_input_readiness_count") != required_count:
        _fail("required readiness summary mismatch")
    if required_count != 0:
        _fail("current tranche blockers are not required for legacy input-readiness status")


def main() -> int:
    expected = build()
    again = build()
    if _dump(expected) != _dump(again):
        _fail("financial reprocess blockers are not deterministic")
    _assert_metadata_only(expected)
    _assert_shape(expected)
    committed = load_json(OUT, {})
    if _dump(committed) != _dump(expected):
        _fail("committed financial_reprocess_blockers.json is stale")
    print(f"financial_reprocess_blockers: PASS ({len(expected.get('blocked_documents') or [])} blocked documents)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
