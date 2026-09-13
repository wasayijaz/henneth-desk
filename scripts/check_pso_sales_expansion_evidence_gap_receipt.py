"""Focused checks for the PSO Case C evidence-gap receipt."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_pso_sales_expansion_evidence_gap_receipt as builder

PASSED = 0
HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED
    if not condition:
        raise AssertionError(f"{name}: {detail}" if detail else name)
    PASSED += 1


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def main() -> None:
    receipt = builder.build(write=True)
    check("schema", receipt["schema_version"] == builder.SCHEMA_VERSION)
    check("identity", receipt["case_id"] == "case_pso_fy2025_distribution_network_expansion_gap_v1")
    check("candidate", receipt["ticker"] == "PSO" and receipt["event_ref"] == builder.EVENT_REF)
    check("blocked status", receipt["status"] == "evidence_gap_no_observed_seed")
    check("not observed", receipt["observed_seed_permitted"] is False)
    check("selected pending", receipt["selection_state"] == "selected_candidate_pending_evidence_ingestion")
    check("event period", receipt["event_period_end"] == "2025-06-30")
    check("no availability", receipt["available_on"] is None and receipt["source_cutoff"] is None)
    check("audit authority", receipt["audit_authority"] == "docs/CASE_C_SALES_EXPANSION_CANDIDATE_AUDIT.md")

    retained = receipt["retained_authority_state"]
    psx = retained["research_index_psx_260771"]
    check("psx metadata present", psx["present"] is True and psx["document_id"] == "psx:260771")
    check("psx download failed", psx["download_status"] == "failed" and "PDF exceeds" in psx["download_error"])
    check("psx not hash bound", psx["content_sha256"] is None)
    check("psx no go", psx["qualifies_observed_seed"] is False)
    check("company document absent", retained["company_documents_psx_260771_present"] is False)
    check("no pso operating event", retained["operating_events_pso_distribution_candidates"] == 0)

    nonqualifying = retained["same_issuer_hash_bound_nonqualifying_documents"]
    check("same issuer bindings", len(nonqualifying) >= 3)
    for row in nonqualifying:
        check("same issuer no promotion", row["qualifies_observed_seed"] is False)
        check("same issuer reason", row["no_go_reason"] == "same_issuer_corporate_card_material_not_dated_fy2025_network_expansion")
        check("same issuer hash", HASH_RE.fullmatch(row["content_sha256"] or "") is not None)
        check("same issuer local hash", row["local_sha256"] == row["content_sha256"])
        check("same issuer no date", row["published_at"] is None)
        if "corporate" in str(row["title"]).lower() or "card" in str(row["title"]).lower():
            check("undated footprint doc cannot satisfy FY2025 expansion event",
                  row["published_at"] is None
                  and row["qualifies_observed_seed"] is False
                  and receipt["event_period_end"] == "2025-06-30")

    facts = receipt["reported_fact_candidates_unpromoted"]
    check("gross openings retained as unpromoted", facts["fy2025_gross_new_outlets"] == 107)
    check("net change derived", facts["derived_net_active_change_outlets"] == 69)
    check("unknown delta", facts["unknown_closures_or_reclassifications_outlets"] == 38)
    check("not promoted", facts["promotion_status"] == "not_promoted_to_reported_facts")

    boundaries = receipt["epistemic_boundaries"]
    check("gross not net", boundaries["gross_openings_are_not_net_additions"] is True)
    check("nested channels", boundaries["channel_layers_are_nested_not_additive"] is True)
    check("no causality backsolve", boundaries["reported_market_share_or_pat_must_not_be_backsolved_as_causal_expansion_impact"] is True)

    downstream = receipt["downstream_status"]
    check("downstream all blocked", all(value == "blocked" for value in downstream.values()))
    check("blocked reasons sorted", receipt["blocked_reasons"] == sorted(set(receipt["blocked_reasons"])))
    check("decisive block reason", "PSO:fy2025_decisive_source_not_retained_hash_page_bound" in receipt["blocked_reasons"])
    check("no numeric output hash", HASH_RE.fullmatch(receipt["run_receipt"]["output_sha256"]) is not None)
    check("empty output hash", receipt["run_receipt"]["output_sha256"] == builder._sha256([]))
    check("input receipt hash", receipt["run_receipt"]["input_sha256"] == builder._sha256({
        "research_index_psx_260771": psx,
        "company_documents_psx_260771_present": retained["company_documents_psx_260771_present"],
        "same_issuer_hash_bound_nonqualifying_documents": nonqualifying,
        "reported_fact_candidates_unpromoted": facts,
    }))

    text = json.dumps(receipt, sort_keys=True).lower()
    for phrase in ("buy", "sell", "accumulate", "target price", "price target", "you should"):
        check(f"no advice {phrase}", re.search(r"\b" + re.escape(phrase) + r"\b", text) is None)

    for key, value in walk(receipt):
        if key in {"valuation", "scenario_model", "publication", "operating_event", "intelligence_case_seed"}:
            check(f"{key} blocked", value == "blocked")

    source = Path(builder.__file__).read_text(encoding="utf-8").lower()
    check("builder no network", not any(token in source for token in ("requests", "urllib", "httpx")))
    with patch.object(builder, "save_json", side_effect=AssertionError("write attempted")):
        no_write = builder.build(write=False)
    check("write false skips save", no_write["status"] == receipt["status"])
    check("deterministic", json.dumps(receipt, sort_keys=True) == json.dumps(builder.build(write=False), sort_keys=True))

    print(f"pso sales expansion evidence gap receipt: PASS ({PASSED} checks)")


if __name__ == "__main__":
    main()
