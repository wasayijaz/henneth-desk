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
    """Check a CI row through the read-only builder projection, preserving the tracked slice."""
    before_exists = slice_path.exists()
    before_bytes = slice_path.read_bytes() if before_exists else None
    before_mtime = slice_path.stat().st_mtime_ns if before_exists else None
    original_save_json = builder.save_json

    def _unexpected_save(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("CI checker projection attempted to call save_json")

    builder.save_json = _unexpected_save
    try:
        projection = builder.build(write=False)
    finally:
        builder.save_json = original_save_json

    after_exists = slice_path.exists()
    after_bytes = slice_path.read_bytes() if after_exists else None
    after_mtime = slice_path.stat().st_mtime_ns if after_exists else None
    if (before_exists, before_bytes, before_mtime) != (after_exists, after_bytes, after_mtime):
        raise AssertionError("CI checker projection mutated company_intelligence.json")

    rows = {row.get("symbol"): row for row in projection.get("tickers") or []}
    if rows.get(symbol, {}).get(field) != expected_row:
        raise AssertionError(f"CI slice does not expose the {symbol} {field} row exactly")
