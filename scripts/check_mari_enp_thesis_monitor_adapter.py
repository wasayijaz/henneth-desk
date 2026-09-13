"""Focused checks for the MARI E&P thesis-monitor slice/readiness adapter."""
from __future__ import annotations

import copy
import json
from datetime import date

import mari_enp_thesis_monitor as monitor
import mari_enp_thesis_monitor_adapter as adapter

PASSED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if not condition:
        raise AssertionError(name + (": " + detail if detail else ""))
    PASSED += 1


def main() -> None:
    retained = monitor.build(write=False)
    red_truth = {"companies": {"MARI": {"status": "not_qualified"}}}
    projection = adapter.readiness_projection(retained, red_truth)
    check("red-truth projection blocked", projection["status"] == "blocked")
    check("red-truth count is zero", projection["active_thesis_count"] == 0)
    check("red-truth reason", projection["blocked_reason"] == "blocked_financial_truth_not_qualified")
    check("red-truth numeric suppressed", projection["suppressed"]["numeric_indicators"] is True)
    check("red-truth still exposes observed confirmation", any(row.get("status") == "observed" for row in projection["confirming_indicators"]))
    check("red-truth exposes next trigger date", isinstance(projection["next_monitor_date"], str) and projection["next_monitor_date"] > "2026-01-01")
    check("red-truth exposes trigger list", "official_well_result_disclosure" in projection["next_triggers"])
    overlay = adapter.overlay_slice_row("MARI", {"symbol": "MARI", "status": "no_active_thesis", "active_thesis_count": 0, "theses": []}, retained, red_truth)
    check("red-truth slice count zero", overlay["active_thesis_count"] == 0 and overlay["status"] == "no_active_thesis")
    check("red-truth slice nested projection", overlay["mari_enp_thesis_monitor"]["active_thesis_count"] == 0)
    other = adapter.overlay_slice_row("MLCF", {"symbol": "MLCF", "active_thesis_count": 2}, retained, red_truth)
    check("non-MARI overlay unchanged", other["active_thesis_count"] == 2 and "mari_enp_thesis_monitor" not in other)

    cutoff = "2026-08-31"
    cases = {
        "companies": {
            "MARI": {
                "cases": [{
                    "case_id": monitor.CASE_ID,
                    "symbol": "MARI",
                    "as_of": cutoff,
                    "observed_facts": [{
                        "fact_id": "mari_peshawar_working_interest_acquisition",
                        "event_date": "2025-09-30T10:46:00+05:00",
                        "statement": "Mari Energies reported acquisition of working interest in Peshawar Block as an operator.",
                        "evidence": [{
                            "document_id": "psx:260446",
                            "document_published_at": "2025-09-30T10:46:00+05:00",
                            "event_date": "2025-09-30T10:46:00+05:00",
                            "content_sha256": "c13ccb4de58ad005bca106942721490593fe219ff45906c68280ea7856192e42",
                            "source_url": "https://dps.psx.com.pk/download/document/260446.pdf",
                            "page": 1,
                        }],
                    }],
                    "alternative_readings": [{
                        "alternative_id": "working_interest_not_reserves",
                        "reading": "Working-interest acquisition does not establish reserves.",
                    }],
                }]
            }
        }
    }
    qualified = {"companies": {"MARI": {"status": "qualified"}}}
    positive_monitor = monitor.evaluate_monitor(
        cutoff_date=cutoff,
        cases=cases,
        truth=qualified,
        valuation={"status": "computed", "as_of": cutoff},
        scenario_lab={"status": "computed", "as_of": cutoff},
        expectations={"status": "computed", "as_of": cutoff},
    )
    live = adapter.readiness_projection(positive_monitor, qualified)
    check("synthetic qualified is available", live["status"] == "available" and live["active_thesis_count"] == 1)
    check("synthetic confirmation present", any(str(row.get("indicator_id")).startswith("kernel:") for row in live["confirming_indicators"]))
    check("synthetic rejection/alternative present", any(row.get("role") == "disconfirming" for row in live["disconfirming_indicators"]))
    check("synthetic stale list exposed", isinstance(live["stale_input_warnings"], list))
    check("synthetic next trigger exposed", live["next_monitor_date"] == monitor.next_quarter_end(date(2026, 8, 31)).isoformat())
    live_row = adapter.overlay_slice_row("MARI", {"symbol": "MARI", "status": "no_active_thesis", "active_thesis_count": 0, "theses": []}, positive_monitor, qualified)
    check("synthetic slice becomes active", live_row["status"] == "active_monitoring" and live_row["active_thesis_count"] == 1)

    stale_monitor = monitor.evaluate_monitor(
        cutoff_date=cutoff,
        cases=cases,
        truth=qualified,
        valuation={"status": "computed", "as_of": "2024-01-01"},
        scenario_lab={"status": "computed", "as_of": cutoff},
        expectations={"status": "computed", "as_of": cutoff},
    )
    stale = adapter.readiness_projection(stale_monitor, qualified)
    check("stale path stays blocked", stale["status"] == "blocked" and stale["active_thesis_count"] == 0)
    check("stale warnings surface", any("valuation" in item for item in stale["stale_input_warnings"]))
    check("selected count uses generic for MLCF", adapter.selected_active_count("MLCF", {"active_thesis_count": 3}, positive_monitor, qualified) == 3)
    check("selected count uses monitor for MARI", adapter.selected_active_count("MARI", {"active_thesis_count": 9}, positive_monitor, qualified) == 1)
    check("selected count red MARI stays zero", adapter.selected_active_count("MARI", {"active_thesis_count": 9}, retained, red_truth) == 0)
    check("adapter projection deterministic", json.dumps(adapter.readiness_projection(retained, red_truth), sort_keys=True) == json.dumps(copy.deepcopy(projection), sort_keys=True))
    print(f"{PASSED} checks passed")


if __name__ == "__main__":
    main()
