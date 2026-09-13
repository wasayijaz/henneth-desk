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
    check("intake revision", receipt["intake_revision"] == builder.INTAKE_REVISION)
    check("identity", receipt["case_id"] == "case_pso_fy2025_distribution_network_expansion_gap_v1")
    check("candidate", receipt["ticker"] == "PSO" and receipt["event_ref"] == builder.EVENT_REF)
    check("source-bound status", receipt["status"] == "observed_seed_promoted")
    check("observed defensible", receipt["observed_seed_permitted"] is True)
    check("selected source-bound", receipt["selection_state"] == "canonical_observed_layer_promoted")
    check("event period", receipt["event_period_end"] == "2025-06-30")
    check("availability", receipt["available_on"] == "2025-10-02" and receipt["source_cutoff"] == builder.OFFICIAL_PUBLISHED_AT)
    check("audit authority", receipt["audit_authority"] == "docs/CASE_C_SALES_EXPANSION_CANDIDATE_AUDIT.md")

    retained = receipt["retained_authority_state"]
    psx = retained["research_index_psx_260771"]
    check("psx metadata present", psx["present"] is True and psx["document_id"] == "psx:260771")
    check("psx download failed", psx["download_status"] == "failed" and "PDF exceeds" in psx["download_error"])
    check("psx observed permitted", psx["qualifies_observed_seed"] is True)
    check("company document absent", retained["company_documents_psx_260771_present"] is False)
    check("one pso operating event", retained["operating_events_pso_distribution_candidates"] == 1)
    check("one pso observed case", retained["intelligence_cases_pso_observed_candidates"] == 1)

    decisive = retained["decisive_psx_260771"]
    check("decisive status", decisive["status"] == "hash_page_bound_observed_seed_defensible")
    check("decisive identity", decisive["document_id"] == "psx:260771" and decisive["title"] == builder.OFFICIAL_TITLE)
    check("decisive url", decisive["source_url"] == builder.OFFICIAL_URL)
    check("decisive published", decisive["published_at"] == builder.OFFICIAL_PUBLISHED_AT and decisive["available_on"] == "2025-10-02")
    check("decisive hash", HASH_RE.fullmatch(decisive["content_sha256"]) is not None)
    check("decisive size", 12 * 1024 * 1024 < decisive["content_length"] <= builder.MAX_DOCUMENT_SPECIFIC_BYTES)
    check("decisive pages", decisive["page_count"] == builder.EXPECTED_PAGE_COUNT)
    check("raw path", decisive["raw_path"] == ".cache/company_intel/pso_sales_expansion_intake/260771.pdf")
    check("oversized scoped", decisive["document_specific_oversized_handling"]["status"] == "accepted_for_this_document_only")
    check("event date basis", decisive["event_date"] == "2025-06-30" and "not a per-outlet opening date" in decisive["event_date_basis"])
    evidence = decisive["evidence"]
    check("evidence pages", {row["page"] for row in evidence} == {15, 310})
    for row in evidence:
        check("evidence hash-bound", row["source_url"] == builder.OFFICIAL_URL and row["content_sha256"] == decisive["content_sha256"])
        check("bounded text", 80 <= len(row["text"]) <= 1100)
    joined = " ".join(row["text"] for row in evidence).lower()
    for term in ("adding 107 new outlets in fy25", "network of 3,649", "3,580", "retail filling station"):
        check(f"evidence term {term}", term in joined)
    recon = decisive["network_reconciliation"]
    check("reconciliation", recon == {
        "fy2024_ending_network_outlets": 3580,
        "fy2025_gross_new_outlets": 107,
        "fy2025_ending_network_outlets": 3649,
        "derived_net_active_change_outlets": 69,
        "unknown_closures_or_reclassifications_outlets": 38,
        "inference_policy": "do_not_infer_the_38_outlet_difference",
    })
    check("promotion flags", decisive["case_seed_promoted"] is True and decisive["financial_facts_promoted"] is False)

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
    check("promoted to observed layer", facts["promotion_status"] == "promoted_to_canonical_observed_layer_reported_facts")

    boundaries = receipt["epistemic_boundaries"]
    check("gross not net", boundaries["gross_openings_are_not_net_additions"] is True)
    check("nested channels", boundaries["channel_layers_are_nested_not_additive"] is True)
    check("no causality backsolve", boundaries["reported_market_share_or_pat_must_not_be_backsolved_as_causal_expansion_impact"] is True)

    downstream = receipt["downstream_status"]
    check("case promoted", downstream["intelligence_case_seed"] == "observed")
    check("event written", downstream["operating_event"] == "observed")
    check("formal downstream blocked", downstream["financial_forecast"] == downstream["scenario_model"] == downstream["valuation"] == downstream["market_expectations"] == downstream["publication"] == "blocked")
    check("blocked reasons sorted", receipt["blocked_reasons"] == sorted(set(receipt["blocked_reasons"])))
    check("bounded block reason", "PSO:financial_truth_still_not_qualified" in receipt["blocked_reasons"])
    check("no numeric output hash", HASH_RE.fullmatch(receipt["run_receipt"]["output_sha256"]) is not None)
    check("empty output hash", receipt["run_receipt"]["output_sha256"] == builder._sha256([]))
    check("input receipt hash", receipt["run_receipt"]["input_sha256"] == builder._sha256({
        "research_index_psx_260771": psx,
        "decisive_psx_260771": decisive,
        "company_documents_psx_260771_present": retained["company_documents_psx_260771_present"],
        "same_issuer_hash_bound_nonqualifying_documents": nonqualifying,
        "reported_fact_candidates_unpromoted": facts,
    }))

    text = json.dumps(receipt, sort_keys=True).lower()
    for phrase in ("buy", "sell", "accumulate", "target price", "price target", "you should"):
        check(f"no advice {phrase}", re.search(r"\b" + re.escape(phrase) + r"\b", text) is None)

    for key, value in walk(receipt):
        if key in {"financial_forecast", "valuation", "scenario_model", "market_expectations", "publication"}:
            check(f"{key} blocked", value == "blocked")

    source = Path(builder.__file__).read_text(encoding="utf-8").lower()
    check("builder no network", not any(token in source for token in ("requests", "urllib", "httpx")))
    check("policy", receipt["policy"]["builder_no_network"] is True
          and receipt["policy"]["single_official_pdf_fetched_for_this_bounded_intake"] is True
          and receipt["policy"]["canonical_observed_layer_promotion_only"] is True
          and receipt["policy"]["no_financial_promotion"] is True)
    with patch.object(builder, "save_json", side_effect=AssertionError("write attempted")):
        no_write = builder.build(write=False)
    check("write false skips save", no_write["status"] == receipt["status"])
    check("deterministic", json.dumps(receipt, sort_keys=True) == json.dumps(builder.build(write=False), sort_keys=True))

    print(f"pso sales expansion evidence gap receipt: PASS ({PASSED} checks)")


if __name__ == "__main__":
    main()
