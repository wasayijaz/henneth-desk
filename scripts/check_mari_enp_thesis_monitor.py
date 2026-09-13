"""Focused checks for the bounded MARI E&P thesis monitor."""
from __future__ import annotations

import copy
import json
from datetime import date

import mari_enp_thesis_monitor as monitor

PASSED = 0
BANNED = ("buy", "sell", "accumulate", "target price", "price target", "you should")


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if not condition:
        raise AssertionError(name + (": " + detail if detail else ""))
    PASSED += 1


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def source_evidence(available_on: str, document_id: str = "psx:260446") -> dict:
    return {
        "document_id": document_id,
        "document_published_at": available_on + "T10:00:00+05:00",
        "event_date": available_on + "T10:00:00+05:00",
        "content_sha256": "c13ccb4de58ad005bca106942721490593fe219ff45906c68280ea7856192e42",
        "source_url": "https://dps.psx.com.pk/download/document/260446.pdf",
        "page": 1,
    }


def observed_case(available_on: str = "2025-09-30") -> dict:
    return {
        "case_id": monitor.CASE_ID,
        "symbol": "MARI",
        "as_of": available_on + "T16:43:41+05:00",
        "observed_facts": [
            {
                "fact_id": "mari_peshawar_working_interest_acquisition",
                "event_date": available_on + "T10:46:00+05:00",
                "statement": "Mari Energies reported acquisition of working interest in Peshawar Block as an operator.",
                "evidence": [source_evidence(available_on)],
            }
        ],
        "alternative_readings": [
            {
                "alternative_id": "working_interest_not_reserves",
                "reading": "Working-interest acquisition does not establish reserves, a commercial discovery, or future production.",
            }
        ],
    }


def cases_payload(case: dict | None = None) -> dict:
    row = case if case is not None else observed_case()
    return {"companies": {"MARI": {"cases": [row]}}}


def truth_payload(status: str) -> dict:
    return {"companies": {"MARI": {"status": status, "financial_tie_out": {"status": "blocked" if status != "qualified" else "ok"}}}}


def main() -> None:
    check("ids", monitor.FORMULA_ID == "enp_exploration.thesis_monitor.v1")
    check("next quarter after 2026-08-31", monitor.next_quarter_end(date(2026, 8, 31)).isoformat() == "2026-09-30")
    check("next quarter after quarter-end", monitor.next_quarter_end(date(2026, 9, 30)).isoformat() == "2026-12-31")

    retained = monitor.build(write=True)
    check("envelope keys", tuple(retained) == monitor.ENVELOPE_KEYS)
    check("retained red-truth fail-closed", retained["status"] == monitor.STATUS_TRUTH)
    check("retained thesis suppressed", retained["thesis"]["activation"] == "suppressed" and retained["thesis"]["status"] == "suppressed")
    check("retained numeric kernels suppressed", all(retained["suppressed"].values()))
    check("retained has cutoff-safe source facts", any(row["document_id"] == "psx:260446" for row in retained["source_facts"]))
    check("retained confirming indicators are observed only", all(row["status"] == "observed" for row in retained["confirming_indicators"]))
    check("retained copied no invented NPV", "npv" not in json.dumps(retained).lower() or all("npv" not in str(row.get("text", "")).lower() for row in retained["confirming_indicators"]))
    check("retained next monitor is after cutoff", retained["next_monitor"]["next_monitor_date"] > retained["evidence_cutoff"]["as_of_date"])
    check("retained triggers explicit", retained["next_monitor"]["triggers"] == list(monitor.TRIGGERS))
    latest = retained["evidence_cutoff"]["latest_retained_evidence_date"]
    check("no-lookahead retained evidence", latest is None or latest <= retained["evidence_cutoff"]["as_of_date"])
    for row in retained["source_facts"]:
        check("source fact in cutoff", row["available_on"] <= retained["evidence_cutoff"]["as_of_date"])
        check("source fact hashed", len(row["content_sha256"]) == 64)
    check("repeat retained identical", json.dumps(monitor.build(write=False), sort_keys=True) == json.dumps(retained, sort_keys=True))

    cutoff = "2026-08-31"
    future_case = observed_case("2026-09-15")
    lookahead = monitor.evaluate_monitor(
        cutoff_date=cutoff,
        cases=cases_payload(future_case),
        truth=truth_payload("qualified"),
        valuation={"status": "computed", "as_of": cutoff},
        scenario_lab={"status": "computed", "as_of": cutoff},
        expectations={"status": "computed", "as_of": cutoff},
    )
    check("lookahead status", lookahead["status"] == monitor.STATUS_LOOKAHEAD)
    check("lookahead evidence excluded", lookahead["source_facts"] == [])
    check("lookahead does not activate", lookahead["thesis"]["activation"] == "suppressed")
    check("lookahead reason names future date", any("2026-09-15" in reason for reason in lookahead["blocked_reasons"]))

    stale = monitor.evaluate_monitor(
        cutoff_date=cutoff,
        cases=cases_payload(),
        truth=truth_payload("qualified"),
        valuation={"status": "computed", "as_of": "2024-01-01"},
        scenario_lab={"status": "computed", "as_of": cutoff},
        expectations={"status": "computed", "as_of": cutoff},
    )
    check("stale artifact rejected", stale["status"] == monitor.STATUS_STALE)
    check("stale warning present", any("valuation" in item for item in stale["stale_input_warnings"]))
    check("stale does not activate numeric kernels", stale["suppressed"]["numeric_indicators"] is True)

    missing = monitor.evaluate_monitor(
        cutoff_date=cutoff,
        cases={"companies": {"MARI": {"cases": []}}},
        truth=truth_payload("qualified"),
        valuation={"status": "computed", "as_of": cutoff},
        scenario_lab={"status": "computed", "as_of": cutoff},
        expectations={"status": "computed", "as_of": cutoff},
    )
    check("missing source facts fail-closed", missing["status"] == monitor.STATUS_SOURCE)

    red = monitor.evaluate_monitor(
        cutoff_date=cutoff,
        cases=cases_payload(),
        truth=truth_payload("not_qualified"),
        valuation={"status": "computed", "as_of": cutoff},
        scenario_lab={"status": "computed", "as_of": cutoff},
        expectations={"status": "computed", "as_of": cutoff},
    )
    check("red truth remains blocked even with computed kernels", red["status"] == monitor.STATUS_TRUTH)
    check("red truth suppresses computed kernel indicators", all(row["status"] == "observed" for row in red["confirming_indicators"]))
    check("red truth keeps observed confirming evidence", any(row["source"] and row["source"]["document_id"] == "psx:260446" for row in red["confirming_indicators"]))

    positive = monitor.evaluate_monitor(
        cutoff_date=cutoff,
        cases=cases_payload(),
        truth=truth_payload("qualified"),
        valuation={"status": "computed", "as_of": cutoff},
        scenario_lab={"status": "computed", "as_of": cutoff},
        expectations={"status": "computed", "as_of": cutoff},
    )
    check("synthetic qualified path activates", positive["status"] == monitor.STATUS_ACTIVE)
    check("synthetic qualified thesis live", positive["thesis"]["activation"] == "active" and positive["thesis"]["status"] == "Strengthening")
    check("synthetic kernels not suppressed", positive["suppressed"]["valuation"] is False and positive["suppressed"]["scenario"] is False)
    check("synthetic confirming includes computed kernels", {row["indicator_id"] for row in positive["confirming_indicators"]} >= {"kernel:valuation_computed", "kernel:scenario_lab_computed", "kernel:expectations_computed"})
    check("synthetic still carries observed source", any(row["indicator_id"].startswith("source:psx:260446") for row in positive["confirming_indicators"]))
    check("synthetic copies no invented prices", all("price" not in row["text"].lower() for row in positive["confirming_indicators"]))

    mutated = copy.deepcopy(positive)
    mutated["confirming_indicators"][0]["text"] += " extra"
    check("caller mutation does not change next evaluate", json.dumps(monitor.evaluate_monitor(
        cutoff_date=cutoff,
        cases=cases_payload(),
        truth=truth_payload("qualified"),
        valuation={"status": "computed", "as_of": cutoff},
        scenario_lab={"status": "computed", "as_of": cutoff},
        expectations={"status": "computed", "as_of": cutoff},
    ), sort_keys=True) != json.dumps(mutated, sort_keys=True))

    for _, item in walk(retained):
        if isinstance(item, str):
            check("no advice language", not any(phrase in item.lower() for phrase in BANNED))

    print(f"{PASSED} checks passed")


if __name__ == "__main__":
    main()

