#!/usr/bin/env python3
"""Hard publication-content checks for subscriber-facing Desk state.

This is an internal publication-policy guard, not a legal-compliance test. It
checks only the two seams covered by docs/PUBLICATION_RESTRUCTURE_V2.md:
restricted execution/sizing keys in signals.active records, and Chair/house-
view fields at the top level of named-ticker rooms sessions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


RESTRICTED_SIGNAL_FIELDS = frozenset(
    {"entry", "stop", "target", "rr", "risk_per_share", "size_shares", "size_pkr"}
)

# Only direct fields on a named-ticker room session are checked. Nested memo
# content is deliberately left alone: technical prose may discuss direction
# or levels without becoming a Chair verdict.
ROOM_SESSION_FIELDS = frozenset(
    {"chair", "house_view", "conviction", "direction", "target"}
)

# One-way cleanup allowlist for the legacy state that existed when this guard
# was introduced. The cleanup may remove only this direct field for these
# tickers; it may not rewrite any memo, debate, metadata, price, or other row.
LEGACY_ROOM_CLEANUP_TICKERS = (
    "BAHL",
    "DCR",
    "DGKC",
    "FABL",
    "FFL",
    "GAL",
    "GHNI",
    "JSML",
    "KEL",
    "LOTCHEM",
    "MLCF",
    "MTL",
    "PAEL",
    "PIOC",
    "PSX",
    "SAZEW",
    "TBL",
)
LEGACY_ROOM_REMOVED_FIELDS = {ticker: frozenset({"house_view"}) for ticker in LEGACY_ROOM_CLEANUP_TICKERS}


def _mapping_key_paths(value: Any, path: str):
    """Yield (key, path) for every mapping key below value."""
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield key, child_path
            yield from _mapping_key_paths(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _mapping_key_paths(child, f"{path}[{index}]")


def validate_signals(signals: Any) -> list[str]:
    """Return publication-policy violations in signals.json."""
    if not isinstance(signals, dict):
        return ["signals.json: expected an object"]
    active = signals.get("active")
    if not isinstance(active, list):
        return ["signals.json: active must be a list"]

    errors: list[str] = []
    for index, record in enumerate(active):
        path = f"signals.json.active[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{path}: expected an object")
            continue
        for key, key_path in _mapping_key_paths(record, path):
            if key in RESTRICTED_SIGNAL_FIELDS:
                errors.append(f"{key_path}: restricted published signal field '{key}'")
    return errors


def validate_rooms(rooms: Any) -> list[str]:
    """Return publication-policy violations in named-ticker rooms.json."""
    if not isinstance(rooms, dict):
        return ["rooms.json: expected an object"]

    errors: list[str] = []
    for symbol, session in rooms.items():
        if symbol == "_meta":
            continue
        path = f"rooms.json[{symbol!r}]"
        if not isinstance(session, dict):
            errors.append(f"{path}: expected a room session object")
            continue
        for field in ROOM_SESSION_FIELDS:
            if field in session:
                errors.append(
                    f"{path}.{field}: prohibited named-ticker room session field '{field}'"
                )
    return errors


def validate_publication(signals: Any, rooms: Any) -> list[str]:
    """Validate both publication seams and return all violations."""
    return [*validate_signals(signals), *validate_rooms(rooms)]


def validate_room_cleanup(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Assert that the approved legacy cleanup changed only its allowlist."""
    errors: list[str] = []
    if set(before) != set(after):
        errors.append("rooms cleanup: ticker/meta key set changed")
    for symbol in sorted(set(before) | set(after)):
        before_row = before.get(symbol)
        after_row = after.get(symbol)
        if not isinstance(before_row, dict) or not isinstance(after_row, dict):
            if before_row != after_row:
                errors.append(f"rooms cleanup: non-object row changed at {symbol!r}")
            continue
        removed = set(before_row) - set(after_row)
        added = set(after_row) - set(before_row)
        allowed = set(LEGACY_ROOM_REMOVED_FIELDS.get(symbol, ()))
        if removed != allowed:
            errors.append(f"rooms cleanup: removed fields at {symbol!r}: {sorted(removed)}")
        if added:
            errors.append(f"rooms cleanup: added fields at {symbol!r}: {sorted(added)}")
        for field in set(before_row) & set(after_row):
            if before_row[field] != after_row[field]:
                errors.append(f"rooms cleanup: changed field at {symbol!r}.{field}")
    return errors


def _self_test() -> None:
    """Exercise negative injections and accepted existing-style content."""
    injected_signals = {
        "active": [
            {
                "ticker": "FFC",
                "payload": {field: 1 for field in sorted(RESTRICTED_SIGNAL_FIELDS)},
            }
        ]
    }
    signal_errors = validate_signals(injected_signals)
    assert len(signal_errors) == len(RESTRICTED_SIGNAL_FIELDS), signal_errors
    assert all("restricted published signal field" in error for error in signal_errors)

    injected_rooms = {
        "FFC": {
            "chair": {},
            "house_view": {},
            "conviction": "high",
            "direction": "up",
            "target": 410,
            "price_at_session": 385.0,
        }
    }
    room_errors = validate_rooms(injected_rooms)
    found = {field for field in ROOM_SESSION_FIELDS if any(f".{field}:" in error for error in room_errors)}
    assert found == ROOM_SESSION_FIELDS, room_errors

    accepted_signals = {
        "active": [
            {
                "ticker": "FFC",
                "strategy": "macd_bull_zero",
                "backtest": {"hit_rate": 0.59},
                "thesis": "Technical history describes a possible entry pattern; the reader decides.",
            }
        ]
    }
    accepted_rooms = {
        "FFC": {
            "price_at_session": 385.0,
            "ta_memo": {
                "levels": {"support": 370.0, "resistance": 400.0},
                "technical_stance": "cautious",
                "read": "The memo describes direction and target levels as technical context.",
            },
            "fa_memo": {"broker_view": "Historical broker attribution is retained as attribution."},
            "bull_case": {"thesis": "One side of the debate."},
            "bear_case": {"thesis": "The other side of the debate."},
        },
        "_meta": {"sessions": 1},
    }
    assert not validate_publication(accepted_signals, accepted_rooms)

    cleanup_before = {
        "DCR": {"house_view": {"summary": "legacy"}, "bull_case": {"thesis": "kept"}},
        "FFC": {"bull_case": {"thesis": "kept"}},
        "_meta": {"sessions": 2},
    }
    cleanup_after = {
        "DCR": {"bull_case": {"thesis": "kept"}},
        "FFC": {"bull_case": {"thesis": "kept"}},
        "_meta": {"sessions": 2},
    }
    assert not validate_room_cleanup(cleanup_before, cleanup_after)
    cleanup_bad = {
        "DCR": {"house_view": {"summary": "legacy"}},
        "FFC": {"bull_case": {"thesis": "changed"}},
        "_meta": {"sessions": 2},
    }
    assert validate_room_cleanup(cleanup_before, cleanup_bad)
    print("check_research_publication: self-test passed")


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run negative and positive fixtures")
    parser.add_argument("--state-dir", type=Path, default=Path(__file__).resolve().parents[1] / "state")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return 0

    errors: list[str] = []
    for name in ("signals.json", "rooms.json"):
        try:
            value = _load(args.state_dir / name)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: could not load — {exc}")
            continue
        errors.extend(validate_signals(value) if name == "signals.json" else validate_rooms(value))

    if errors:
        print("check_research_publication: FAIL")
        for error in errors:
            print(f"  x {error}")
        return 1
    print("check_research_publication: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
