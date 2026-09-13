"""Project the MARI E&P thesis monitor into CI slice/readiness shapes.

Authoritative input is state/company_intel/mari_enp_thesis_monitor.json plus
financial-truth status. Numeric/active counts stay zero whenever financial
truth is red or the monitor is not active_monitoring. This module does not
parse statements, fetch, or invent economics.
"""
from __future__ import annotations

from typing import Any, Mapping

SOURCE_PATH = "state/company_intel/mari_enp_thesis_monitor.json"
SYMBOL = "MARI"
STATUS_ACTIVE = "active_monitoring"


def _truth_row(truth: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(truth, dict):
        return {}
    companies = truth.get("companies")
    if isinstance(companies, dict) and isinstance(companies.get(SYMBOL), dict):
        return companies[SYMBOL]
    if truth.get("symbol") == SYMBOL:
        return dict(truth)
    return {}


def _compact_indicators(rows: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "indicator_id": row.get("indicator_id"),
                "role": row.get("role"),
                "status": row.get("status"),
                "text": row.get("text"),
                "available_on": row.get("available_on"),
            }
        )
    return out


def is_active(monitor: Mapping[str, Any] | None, truth: Mapping[str, Any] | None) -> bool:
    truth_row = _truth_row(truth)
    if truth_row.get("status") != "qualified":
        return False
    if not isinstance(monitor, dict):
        return False
    thesis = monitor.get("thesis") if isinstance(monitor.get("thesis"), dict) else {}
    return monitor.get("status") == STATUS_ACTIVE and thesis.get("activation") == "active"


def active_count(monitor: Mapping[str, Any] | None, truth: Mapping[str, Any] | None) -> int:
    return 1 if is_active(monitor, truth) else 0


def selected_active_count(
    symbol: str,
    generic_row: Mapping[str, Any] | None,
    monitor: Mapping[str, Any] | None,
    truth: Mapping[str, Any] | None,
) -> int:
    """MARI uses the E&P monitor; other selected symbols keep generic counts."""
    if symbol == SYMBOL:
        return active_count(monitor, truth)
    count = (generic_row or {}).get("active_thesis_count")
    return count if isinstance(count, int) and not isinstance(count, bool) else 0


def readiness_projection(monitor: Mapping[str, Any] | None, truth: Mapping[str, Any] | None) -> dict[str, Any]:
    """Slice/readiness view: confirmation, rejection, stale, next-trigger."""
    monitor = monitor if isinstance(monitor, dict) else {}
    active = is_active(monitor, truth)
    truth_row = _truth_row(truth)
    blocked_reason = None
    if truth_row.get("status") != "qualified":
        blocked_reason = "blocked_financial_truth_not_qualified"
    elif not monitor:
        blocked_reason = "mari_enp_thesis_monitor_missing"
    elif monitor.get("status") != STATUS_ACTIVE:
        blocked_reason = str(monitor.get("status") or "blocked")
    next_monitor = monitor.get("next_monitor") if isinstance(monitor.get("next_monitor"), dict) else {}
    return {
        "source_path": SOURCE_PATH,
        "symbol": SYMBOL,
        "status": "available" if active else "blocked",
        "monitor_status": monitor.get("status"),
        "active_thesis_count": 1 if active else 0,
        "blocked_reason": blocked_reason,
        "confirming_indicators": _compact_indicators(monitor.get("confirming_indicators")),
        "disconfirming_indicators": _compact_indicators(monitor.get("disconfirming_indicators")),
        "stale_input_warnings": list(monitor.get("stale_input_warnings") or []),
        "next_monitor_date": next_monitor.get("next_monitor_date"),
        "next_triggers": list(next_monitor.get("triggers") or []),
        "evidence_cutoff": monitor.get("evidence_cutoff"),
        "suppressed": monitor.get("suppressed") if isinstance(monitor.get("suppressed"), dict) else {
            "valuation": True,
            "scenario": True,
            "expectations": True,
            "numeric_indicators": True,
        },
    }


def overlay_slice_row(
    symbol: str,
    generic_row: Mapping[str, Any] | None,
    monitor: Mapping[str, Any] | None,
    truth: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if symbol != SYMBOL:
        return dict(generic_row) if isinstance(generic_row, dict) else generic_row
    row = dict(generic_row) if isinstance(generic_row, dict) else {
        "symbol": SYMBOL,
        "status": "no_active_thesis",
        "active_thesis_count": 0,
        "theses": [],
    }
    projection = readiness_projection(monitor, truth)
    row["active_thesis_count"] = projection["active_thesis_count"]
    if projection["active_thesis_count"]:
        row["status"] = "active_monitoring"
    else:
        row["status"] = "no_active_thesis"
    row["mari_enp_thesis_monitor"] = projection
    return row
