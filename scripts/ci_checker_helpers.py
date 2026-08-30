"""Shared normalization for checker comparisons of generated CI products."""
from __future__ import annotations

from typing import Any


def without_root_meta(value: Any) -> Any:
    """Return logical product content, excluding only the root integrity envelope."""
    if not isinstance(value, dict) or "_meta" not in value:
        return value
    logical = dict(value)
    logical.pop("_meta", None)
    return logical


def assert_ci_slice_projection(builder: Any, slice_path: Any, symbol: str, field: str, expected_row: dict[str, Any]) -> None:
    """Check a CI row through an in-memory builder capture, preserving the tracked slice."""
    before_exists = slice_path.exists()
    before_bytes = slice_path.read_bytes() if before_exists else None
    before_mtime = slice_path.stat().st_mtime_ns if before_exists else None
    original_save_json = builder.save_json
    writes: list[tuple[Any, Any]] = []

    def _capture_save(path: Any, payload: Any, *_args: Any, **_kwargs: Any) -> None:
        writes.append((path, payload))

    builder.save_json = _capture_save
    try:
        builder.build()
    finally:
        builder.save_json = original_save_json

    after_exists = slice_path.exists()
    after_bytes = slice_path.read_bytes() if after_exists else None
    after_mtime = slice_path.stat().st_mtime_ns if after_exists else None
    if (before_exists, before_bytes, before_mtime) != (after_exists, after_bytes, after_mtime):
        raise AssertionError("CI checker projection mutated company_intelligence.json")

    if len(writes) != 1:
        raise AssertionError(f"CI checker builder emitted {len(writes)} save_json calls; expected exactly one")
    written_path, projection = writes[0]
    if getattr(written_path, "resolve", lambda: written_path)() != slice_path.resolve():
        raise AssertionError(f"CI checker builder attempted to write unexpected path: {written_path}")
    if not isinstance(projection, dict):
        raise AssertionError("CI checker builder did not emit a mapping projection")

    tickers = projection.get("tickers")
    if not isinstance(tickers, list):
        raise AssertionError("CI checker projection tickers must be a list")
    matching_rows: list[dict[str, Any]] = []
    for row in tickers:
        if not isinstance(row, dict):
            raise AssertionError("CI checker projection ticker rows must be mappings")
        row_symbol = row.get("symbol")
        if not isinstance(row_symbol, str):
            raise AssertionError("CI checker projection ticker symbols must be plain strings")
        if row_symbol == symbol:
            matching_rows.append(row)
    if len(matching_rows) != 1:
        raise AssertionError(f"CI checker projection emitted {len(matching_rows)} rows for target symbol; expected exactly one")
    if matching_rows[0].get(field) != expected_row:
        raise AssertionError(f"CI slice does not expose the {symbol} {field} row exactly")
