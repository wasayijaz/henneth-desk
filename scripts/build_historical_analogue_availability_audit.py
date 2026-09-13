"""Build Historical Analogue Availability Audit for Alpha Cases.

This module performs a bounded, deterministic audit of retained official state
to evaluate historical analogue availability for the four Event-to-Value Alpha
case envelopes (MLCF control acquisition, MARI working-interest acquisition,
MARI data-centre launch, PSO retail network expansion).

Strict Guardrails:
- Reads only retained state files (operating_events, event_studies, conditional_benchmarks,
  intelligence_cases, historical_state_map, sectors, company_profiles).
- Classifies candidates into:
  * Tier 1: exact event type/subtype (strictly same-company or same-sector before cutoff).
  * Tier 2: same economic mechanism with explicit comparability dimensions.
  * Tier 3: regime/context only (never scenario-calibrating).
- Enforces strict point-in-time no-lookahead (candidates must have effective_date < target case date).
- Preserves thin-sample suppression (N < 3).
- Does not invent candidates, double-count events, alter canonical state, or activate forecasts.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from psx_data import STATE, load_json, save_json


PRODUCT_VERSION = "historical_analogue_availability_audit_v1"
OUT = STATE / "company_intel" / "historical_analogue_availability_audit.json"

ALPHA_CASE_IDS = (
    "case_mari_working_interest_observed_v1",
    "case_mari_sky47_karakoram1_launch_sales_observed_v1",
    "case_mlcf_pioc_control_observed_v1",
    "case_pso_fy2025_distribution_network_expansion_observed_v1",
)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _audit_case(
    context: Mapping[str, Any],
    *,
    all_operating_events: Mapping[str, Any],
    event_studies: Mapping[str, Any],
    sectors_map: Mapping[str, Any],
) -> dict[str, Any]:
    case = context.get("case") or {}
    binding = context.get("event_binding") or {}
    symbol = str(case.get("symbol") or "")
    case_id = str(case.get("case_id") or "")
    target_event_id = binding.get("matched_operating_event_id")
    target_effective_date_str = binding.get("effective_date")
    target_date = _parse_date(target_effective_date_str)
    target_type = binding.get("event_type")
    target_subtype = binding.get("event_subtype")
    target_sector = (sectors_map.get(symbol) or {}).get("sector")

    tier1_candidates = []
    tier2_candidates = []
    tier3_candidates = []
    excluded_candidates = []

    # Scan all 20 pilot companies' operating events
    for sym, co_data in (all_operating_events.get("companies") or {}).items():
        co_sector = (sectors_map.get(sym) or {}).get("sector")
        for ev in (co_data.get("events") or []):
            if not isinstance(ev, dict):
                continue
            cand_id = ev.get("event_id")
            cand_date_str = ev.get("effective_date")
            cand_date = _parse_date(cand_date_str)
            cand_type = ev.get("event_type")
            cand_subtype = ev.get("event_subtype")
            cand_study = (event_studies.get("studies") or {}).get(cand_id)

            # Self-exclusion or post-target lookahead
            if cand_id == target_event_id:
                continue

            # Evidence / source extraction
            first_ev = next((item for item in (ev.get("evidence") or []) if isinstance(item, dict)), {})
            cand_doc_id = first_ev.get("document_id")
            cand_sha = first_ev.get("content_sha256")
            cand_page = first_ev.get("page")
            cand_url = first_ev.get("source_url")

            # Horizon maturity evaluation
            horizons_eval = {}
            if cand_study:
                for h_name in ("1Q", "2Q", "4Q", "8Q"):
                    h_row = (cand_study.get("horizons") or {}).get(h_name) or {}
                    horizons_eval[h_name] = {
                        "status": h_row.get("status"),
                        "return_pct": h_row.get("return_pct"),
                        "selected_date": h_row.get("selected_date"),
                        "reason": h_row.get("reason"),
                    }

            cand_record = {
                "event_id": cand_id,
                "symbol": sym,
                "sector": co_sector,
                "event_type": cand_type,
                "event_subtype": cand_subtype,
                "effective_date": cand_date_str,
                "source_document_id": cand_doc_id,
                "content_sha256": cand_sha,
                "page": cand_page,
                "source_url": cand_url,
                "has_event_study": cand_study is not None,
                "horizons": horizons_eval,
                "scale_fields": {
                    "available": bool(ev.get("estimated_scale")),
                    "detail": ev.get("estimated_scale"),
                },
                "independence_status": "independent_issuer" if sym != symbol else "same_issuer_prior_episode",
            }

            # Check lookahead: candidate must be strictly before target date
            if not cand_date or not target_date or cand_date >= target_date:
                excluded_candidates.append({
                    "event_id": cand_id,
                    "symbol": sym,
                    "effective_date": cand_date_str,
                    "reason": "lookahead_or_undated" if (cand_date and cand_date >= target_date) else "undated_event",
                })
                continue

            # Classification rules:
            # Tier 1: exact event_type and event_subtype match, in same company or same sector
            if cand_type == target_type and cand_subtype == target_subtype and (sym == symbol or co_sector == target_sector):
                tier1_candidates.append({
                    **cand_record,
                    "tier": "tier_1_exact_analogue",
                    "mechanism": f"Exact {target_type}/{target_subtype} in {'same_company' if sym == symbol else 'same_sector'}",
                    "scenario_calibrating": False,  # remains false while sample N < 3
                })
            # Tier 2: same economic mechanism across sectors (e.g. corporate M&A / asset expansion)
            elif cand_type == target_type and cand_subtype == target_subtype:
                tier2_candidates.append({
                    **cand_record,
                    "tier": "tier_2_economic_mechanism_analogue",
                    "mechanism": f"Cross-sector {target_type}/{target_subtype} mechanism ({co_sector} vs {target_sector})",
                    "comparability_fields": {
                        "target_sector": target_sector,
                        "candidate_sector": co_sector,
                        "cross_sector_structural_differences": "Sector drivers and margin structures differ",
                    },
                    "scenario_calibrating": False,
                })
            elif cand_type == "acquisition_divestment" and target_type == "acquisition_divestment":
                tier2_candidates.append({
                    **cand_record,
                    "tier": "tier_2_economic_mechanism_analogue",
                    "mechanism": "Inorganic corporate transaction",
                    "comparability_fields": {"target_subtype": target_subtype, "candidate_subtype": cand_subtype},
                    "scenario_calibrating": False,
                })
            else:
                tier3_candidates.append({
                    "event_id": cand_id,
                    "symbol": sym,
                    "sector": co_sector,
                    "event_type": cand_type,
                    "effective_date": cand_date_str,
                    "tier": "tier_3_regime_context_only",
                    "mechanism": "Broad market/corporate regime context only",
                    "scenario_calibrating": False,
                })

    # Audit conclusions
    t1_count = len(tier1_candidates)
    t2_count = len(tier2_candidates)
    t1_mature_1q = sum(1 for c in tier1_candidates if (c.get("horizons") or {}).get("1Q", {}).get("status") == "mature")

    evidence_gap = []
    if t1_count < 3:
        evidence_gap.append({
            "gap_type": "thin_sample_threshold_unmet",
            "current_tier1_count": t1_count,
            "required_count": 3,
            "deficit": 3 - t1_count,
            "rule": "Statistics and scenario calibration remain suppressed below N=3 mature exact analogues",
        })
    if t1_count == 0:
        evidence_gap.append({
            "gap_type": "zero_exact_prior_analogues",
            "detail": f"No prior {target_type}/{target_subtype} events exist in {target_sector} or {symbol} prior to {target_effective_date_str}",
        })

    return {
        "case_id": case_id,
        "symbol": symbol,
        "sector": target_sector,
        "case_family": case.get("case_family"),
        "case_type": case.get("case_type"),
        "target_event": {
            "event_id": target_event_id,
            "event_type": target_type,
            "event_subtype": target_subtype,
            "effective_date": target_effective_date_str,
            "match_policy": binding.get("match_policy"),
        },
        "analogue_availability": {
            "tier_1_exact_count": t1_count,
            "tier_1_mature_1q_count": t1_mature_1q,
            "tier_2_mechanism_count": t2_count,
            "tier_3_regime_count": len(tier3_candidates),
            "sample_sufficient_for_stats": t1_count >= 3,
            "status": "sample_ready" if t1_count >= 3 else ("thin_history_present" if (t1_count + t2_count) > 0 else "zero_candidates"),
        },
        "tier_1_candidates": tier1_candidates,
        "tier_2_candidates": tier2_candidates,
        "evidence_gaps": evidence_gap,
        "policy": {
            "strictly_pre_target": True,
            "no_forecast_activation": True,
            "no_synthetic_matching": True,
        },
    }


def build(*, write: bool = True) -> dict[str, Any]:
    hstate = load_json(STATE / "company_intel" / "historical_state_map.json", {"contexts": []})
    op = load_json(STATE / "company_intel" / "operating_events.json", {"companies": {}})
    studies = load_json(STATE / "company_intel" / "event_studies.json", {"studies": {}})
    sectors_data = load_json(STATE / "sectors.json", {}).get("tickers") or {}

    existing = load_json(OUT, {})
    existing_meta = existing.get("_meta") if isinstance(existing, dict) else None

    contexts = hstate.get("contexts") or []
    case_audits = []
    for ctx in contexts:
        case_id = (ctx.get("case") or {}).get("case_id")
        if case_id in ALPHA_CASE_IDS:
            case_audits.append(_audit_case(
                ctx,
                all_operating_events=op,
                event_studies=studies,
                sectors_map=sectors_data,
            ))

    summary = {
        "audited_case_count": len(case_audits),
        "cases_with_tier1_analogues": sum(1 for a in case_audits if (a.get("analogue_availability") or {}).get("tier_1_exact_count", 0) > 0),
        "cases_with_sufficient_sample_for_stats": sum(1 for a in case_audits if (a.get("analogue_availability") or {}).get("sample_sufficient_for_stats") is True),
        "total_tier1_candidates_identified": sum((a.get("analogue_availability") or {}).get("tier_1_exact_count", 0) for a in case_audits),
        "total_tier2_mechanism_candidates_identified": sum((a.get("analogue_availability") or {}).get("tier_2_mechanism_count", 0) for a in case_audits),
        "suppression_policy_enforced": True,
    }

    result = {
        "schema_version": 1,
        "product_version": PRODUCT_VERSION,
        "kind": "historical_analogue_availability_audit",
        "scope": "Event-to-Value Alpha Case Envelopes",
        "summary": summary,
        "cases": case_audits,
        "policy": {
            "strict_no_lookahead": True,
            "retained_state_only": True,
            "minimum_sample_three": True,
            "no_forecast_activation": True,
            "descriptive_past_context_only": True,
        },
    }
    if isinstance(existing_meta, dict):
        result["_meta"] = existing_meta
    if write:
        save_json(OUT, result)
        print(f"historical_analogue_availability_audit: {len(case_audits)} cases audited -> {OUT.name}")
    return result


if __name__ == "__main__":
    build()
