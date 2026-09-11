#!/usr/bin/env python3
"""Decide whether the local AI checkpoint has anything material to do.

The deterministic cloud pipeline already refreshes prices and health every 30
minutes for free. The token-spending local checkpoint should
therefore only wake up when something MATERIAL happened since it last ran.

This module owns that decision. It writes `state/checkpoint_trigger.json`:

    checkpoint_required  bool   - the only field the checkpoint task must read
    standing             list   - conditions that require a checkpoint every run
    pending              list   - material items first seen since the last ack
    tracked              dict   - id -> first_seen, so an item fires once, not forever
    degraded             list   - inputs that could not be read (fails LOUD: required)

Edge, not level: every trigger item carries a stable id and a sticky `first_seen`.
An item is pending only while `first_seen` is newer than the checkpoint's last ack,
so one impact-5 headline wakes the desk once instead of all day.

The checkpoint task acknowledges a run with:

    python scripts/build_checkpoint_trigger.py --ack checkpoint-am

which writes `state/checkpoint_ack.json`. Two files, one writer each: the cloud
owns the trigger, the checkpoint owns the ack.

Deliberately NOT here: stop/target band logic. The Monitor agent owns that rule
(see .claude/agents/monitor.md) and re-deriving it in Python would put one rule in
two places. An open position instead makes the checkpoint unconditional - monitoring
of live money is never skipped.

Also standing: the FIRST checkpoint of each trading day. The business press is only
read by the news-sentinel agent - the cloud pipeline indexes official filings and
issuer pages, not headlines - so a gate that could skip every checkpoint would starve
its own news input. One guaranteed scan per weekday keeps the news log alive; the
day's second checkpoint runs only if something material actually landed.

No network, no agents, idempotent, always exits 0.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from psx_data import STATE, load_json, save_json

PKT = timezone(timedelta(hours=5))
TRIGGER = STATE / "checkpoint_trigger.json"
ACK = STATE / "checkpoint_ack.json"

SCHEMA_VERSION = 1
NEWS_IMPACT_MIN = 4        # CLAUDE.md Rule 10 - the full pipeline re-triggers at >= 4
NEWS_LOOKBACK_DAYS = 10
MAX_PENDING = 40


def _now() -> str:
    return datetime.now(PKT).isoformat(timespec="seconds")


def _id(prefix: str, *parts: Any) -> str:
    seed = "|".join(str(p or "") for p in parts)
    return f"{prefix}_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _news_items(degraded: list[str]) -> list[dict[str, Any]]:
    log = load_json(STATE / "newslog.json", None)
    if not isinstance(log, list):
        degraded.append("newslog.json unreadable")
        return []
    cutoff = (datetime.now(PKT) - timedelta(days=NEWS_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    out = []
    for item in log:
        if not isinstance(item, dict):
            continue
        try:
            impact = int(item.get("impact") or 0)
        except (TypeError, ValueError):
            continue
        ts = str(item.get("ts") or "")[:10]
        if impact < NEWS_IMPACT_MIN or ts < cutoff:
            continue
        tickers = [t for t in (item.get("tickers") or []) if isinstance(t, str)]
        source = item.get("source") or "unknown source"
        out.append({
            "id": _id("news", ts, item.get("source"), item.get("headline")),
            "kind": "news",
            "symbol": ", ".join(tickers[:4]),
            "title": str(item.get("headline") or "")[:180],
            "detail": f"impact {impact} - {source}",
        })
    return out


def _health_item(degraded: list[str]) -> list[dict[str, Any]]:
    health = load_json(STATE / "health.json", None)
    if not isinstance(health, dict):
        degraded.append("health.json unreadable")
        return []
    status = str(health.get("status") or "unknown")
    if status == "ok":
        return []
    problems = [str(p) for p in (health.get("problems") or [])]
    return [{
        "id": _id("health", status, "|".join(sorted(problems))),
        "kind": "health",
        "symbol": "",
        "title": f"data health is {status}",
        "detail": "; ".join(problems)[:180] or "no problem detail recorded",
    }]


def _standing(degraded: list[str], acked_at: str) -> list[dict[str, Any]]:
    """Conditions that require a checkpoint on EVERY run, ack or not."""
    out: list[dict[str, Any]] = []

    # The day's first checkpoint always runs - it is the only thing that reads the
    # business press into state/newslog.json. Without it the gate would have no news
    # input to detect. The day's second checkpoint is the one this gate can skip.
    if str(acked_at)[:10] != datetime.now(PKT).strftime("%Y-%m-%d"):
        out.append({
            "kind": "first_of_day",
            "title": "no checkpoint has run yet today",
            "detail": "the day's first checkpoint always runs - it is the desk's only news scan",
        })

    positions = load_json(STATE / "positions.json", None)
    if not isinstance(positions, dict):
        degraded.append("positions.json unreadable")
        return out
    open_positions = [p for p in (positions.get("open") or []) if isinstance(p, dict)]
    if open_positions:
        tickers = ", ".join(str(p.get("ticker") or "?") for p in open_positions)
        out.append({
            "kind": "open_positions",
            "title": f"{len(open_positions)} open position(s): {tickers}",
            "detail": "live capital is at risk - the Monitor runs every cycle",
        })
    return out


def build() -> dict[str, Any]:
    degraded: list[str] = []

    acked_at = ""
    ack = load_json(ACK, None)
    if isinstance(ack, dict):
        acked_at = str(ack.get("acked_at") or "")

    observed = _news_items(degraded) + _health_item(degraded)
    standing = _standing(degraded, acked_at)

    previous = load_json(TRIGGER, None)
    seeding = not isinstance(previous, dict)
    known = (previous or {}).get("tracked") if isinstance(previous, dict) else {}
    known = known if isinstance(known, dict) else {}

    now = _now()
    tracked: dict[str, str] = {}
    pending: list[dict[str, Any]] = []
    for item in observed:
        item_id = item["id"]
        # First run seeds the ledger as pre-existing ("" = older than any ack), so
        # turning the gate on does not fire a checkpoint for the whole backlog.
        first_seen = known.get(item_id, "" if seeding else now)
        tracked[item_id] = first_seen
        if first_seen and first_seen > acked_at:
            pending.append({**item, "first_seen": first_seen})

    pending.sort(key=lambda i: i["first_seen"], reverse=True)
    dropped = max(0, len(pending) - MAX_PENDING)
    pending = pending[:MAX_PENDING]

    required = bool(pending or standing or degraded)
    if degraded:
        summary = f"inputs degraded ({len(degraded)}) - running the checkpoint rather than guessing"
    elif standing and pending:
        summary = f"{len(pending)} material item(s) and {len(standing)} standing condition(s)"
    elif standing:
        summary = "; ".join(s["title"] for s in standing)
    elif pending:
        summary = f"{len(pending)} material item(s) since the last checkpoint"
    elif seeding:
        summary = "gate seeded - existing items recorded as pre-existing, nothing pending"
    else:
        summary = "nothing material since the last checkpoint"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated": now,
        "checkpoint_required": required,
        "summary": summary,
        "acked_at": acked_at,
        "counts": {
            "pending": len(pending),
            "pending_dropped": dropped,
            "standing": len(standing),
            "tracked": len(tracked),
        },
        "standing": standing,
        "pending": pending,
        "tracked": tracked,
        "degraded": degraded,
        "note": "Deterministic checkpoint gate. Research infrastructure, not advice.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Checkpoint trigger gate")
    ap.add_argument("--ack", metavar="LABEL", help="record that a checkpoint just ran")
    ap.add_argument("--desk", action="store_true", help="accepted for desk pipeline compatibility")
    args = ap.parse_args()

    if args.ack:
        save_json(ACK, {"acked_at": _now(), "by": str(args.ack)[:60]})
        print(f"checkpoint gate: acked by {args.ack}")
        return 0

    payload = build()
    save_json(TRIGGER, payload)
    print(
        f"checkpoint gate: required={payload['checkpoint_required']} "
        f"pending={payload['counts']['pending']} standing={payload['counts']['standing']} "
        f"- {payload['summary']}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001 - never crash the cycle (AGENTS.md #17)
        print(f"checkpoint gate: failed ({e}) - leaving the previous trigger in place")
        sys.exit(0)
