"""Contract checks for the scheduled-routine predecessor gate."""

from __future__ import annotations

from datetime import date

from wait_for_routine_receipt import ReceiptError, validate_evidence


DAY = date(2026, 9, 14)
SHA = "a" * 40


def _receipt(routine: str) -> dict:
    entry = {
        "routine": routine,
        "started": "2026-09-14T17:45:00+05:00",
        "research_sha": SHA,
        "mode": "light" if routine == "pm" else "full",
        "outcome": "verified research",
        "ended": "2026-09-14T18:00:00+05:00",
    }
    if routine == "pm":
        entry["ack_proof"] = {
            "acked_at": entry["ended"],
            "by": "checkpoint-pm",
            "routine": "pm",
            "started": entry["started"],
            "research_sha": SHA,
        }
    return entry


def _must_fail(receipts: object, logs: object, ack: object, routine: str) -> None:
    try:
        validate_evidence(receipts, logs, ack, routine, DAY, lambda _sha: True)
    except ReceiptError:
        return
    raise AssertionError("invalid predecessor evidence was accepted")


def main() -> int:
    pm = _receipt("pm")
    daily = _receipt("daily")
    assert validate_evidence([pm], [pm.copy()], pm["ack_proof"], "pm", DAY, lambda _sha: True) == pm
    assert validate_evidence([daily], [daily.copy()], None, "daily", DAY, lambda _sha: True) == daily
    _must_fail([], [], None, "pm")
    _must_fail([pm], [], pm["ack_proof"], "pm")
    _must_fail([pm], [pm.copy()], {"acked_at": pm["ended"], "by": "checkpoint-pm"}, "pm")
    try:
        validate_evidence([daily], [daily.copy()], None, "daily", DAY, lambda _sha: False)
    except ReceiptError:
        pass
    else:
        raise AssertionError("unreachable research SHA was accepted")
    print("routine predecessor receipt checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
