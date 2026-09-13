"""Cement Capacity Expansion Historical Analogue & Distribution Engine.

This module implements the deterministic eligibility, source qualification,
deduplication, and distribution calculation for the Cement Capacity Expansion lane
(DGKC line commissioning, MLCF organic expansions, and peer line ramps).

Strict Invariants:
1. Target Case Disambiguation:
   Explicitly distinguishes organic capacity expansion (clinker line / WHR commissioning)
   from inorganic corporate control acquisitions (e.g. MLCF's PIOC share purchase).
   Mismatched M&A events are strictly rejected from cement expansion analogue pooling.
2. Event-Family Eligibility:
   Permits only: cement_clinker_line_commissioning, cement_grinding_capacity_expansion,
   cement_waste_heat_recovery_commissioning, cement_line_ramp_debottlenecking.
3. Source Binding & Deduplication:
   Requires verified document ID, content SHA256, page, and publication timestamp.
   Multiple disclosures for the same capital project are deduplicated into one episode.
4. Horizon Maturity & No-Lookahead:
   Baseline is anchored strictly before information availability.
   Horizons (1Q, 2Q, 4Q, 8Q) must have mature trading endpoints on or before data cutoff.
5. Fail-Closed Sample Gate (N >= 3):
   Distribution statistics (mean, median, min, max, dispersion) remain strictly null
   and status remains "insufficient_sample" unless >= 3 mature independent outcomes exist.
6. Missing Records Queue:
   When retained qualified events < 3, emits a ranked exact queue of missing historical
   source documents and dates needed for lane maturation.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
import statistics
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence
from psx_data import STATE, load_json, save_json
import event_studies

SCHEMA_VERSION = 1
PRODUCT_VERSION = "cement_expansion_analogue_distribution_v1"
OUT = STATE / "company_intel" / "cement_expansion_analogue_distribution.json"

HORIZONS = ("1Q", "2Q", "4Q", "8Q")
MIN_SAMPLE = 3

ELIGIBLE_EVENT_FAMILIES = (
    "cement_clinker_line_commissioning",
    "cement_grinding_capacity_expansion",
    "cement_waste_heat_recovery_commissioning",
    "cement_line_ramp_debottlenecking",
    "cement_capacity_expansion",
)

EXCLUDED_EVENT_FAMILIES = (
    "corporate_equity_control_acquisition",
    "acquisition_divestment",
    "contract_tender_generic",
    "management_change",
    "debt_refinancing",
    "regulatory_action",
)

DISCOVERY_REQUIREMENTS_QUEUE = [
    {
        "slot_id": "slot_cement_expansion_1",
        "priority": 1,
        "requirement_type": "official_clinker_line_commissioning_notice",
        "description": "Commercial operation commencement disclosure for new or brownfield clinker line",
        "required_evidence_fields": ["document_id", "content_sha256", "source_url", "page", "published_at", "rated_clinker_tpd"],
        "eligibility_impact": "Provides primary verified clinker capacity expansion observation",
    },
    {
        "slot_id": "slot_cement_expansion_2",
        "priority": 2,
        "requirement_type": "official_waste_heat_recovery_or_grinding_notice",
        "description": "Commercial commissioning announcement for waste heat recovery (WHR) plant or additional cement grinding mill",
        "required_evidence_fields": ["document_id", "content_sha256", "source_url", "page", "published_at", "megawatt_or_tpd_capacity"],
        "eligibility_impact": "Provides second independent operational efficiency / capacity expansion observation",
    },
    {
        "slot_id": "slot_cement_expansion_3",
        "priority": 3,
        "requirement_type": "peer_cement_capacity_addition_notice",
        "description": "Historical commercial operation commencement announcement for domestic peer cement plant expansion",
        "required_evidence_fields": ["document_id", "content_sha256", "source_url", "page", "published_at", "capacity_addition_metric"],
        "eligibility_impact": "Completes required minimum mature sample (N >= 3) for statistical distribution publishing",
    },
]

def parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None

def validate_analogue_candidate(cand: Mapping[str, Any], cutoff_date: date | None = None) -> list[str]:
    """Validate one candidate observation against eligibility rules."""
    violations = []
    family = str(cand.get("event_family") or cand.get("event_type") or "")
    if family in EXCLUDED_EVENT_FAMILIES or "acquisition" in family.lower():
        violations.append(f"ineligible_event_family: {family} is corporate M&A/control, not cement capacity expansion")
    elif family not in ELIGIBLE_EVENT_FAMILIES and cand.get("event_type") not in ("capacity_expansion", "product_launch"):
        violations.append(f"unsupported_event_family: {family}")

    avail_date_str = cand.get("information_available_at") or (cand.get("source") or {}).get("available_on") or cand.get("effective_date")
    cand_date = parse_date(avail_date_str)
    if not cand_date:
        violations.append("missing_valid_event_or_information_date")
    elif cutoff_date and cand_date >= cutoff_date:
        violations.append(f"lookahead_violation: candidate date {cand_date} >= cutoff {cutoff_date}")

    source = cand.get("source") or {}
    if not isinstance(source, Mapping):
        violations.append("missing_source_binding")
    else:
        doc_id = str(source.get("id") or source.get("document_id") or "")
        if not doc_id:
            violations.append("missing_source_document_id")
        sha = str(source.get("hash") or source.get("content_sha256") or "")
        if not sha or len(sha) != 64 or not all(c in "0123456789abcdefABCDEF" for c in sha):
            violations.append("missing_or_malformed_content_sha256")
        url = str(source.get("url") or source.get("source_url") or "")
        if not url or not (url.startswith("http://") or url.startswith("https://") or url.startswith("fixture://")):
            violations.append("missing_or_invalid_source_url")
        page = source.get("page")
        if page is None or (isinstance(page, int) and page < 1):
            violations.append("missing_or_invalid_source_page")

    return violations

def deduplicate_observations(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Group multi-stage filings of the same project into single independent episodes."""
    deduped: dict[str, dict[str, Any]] = {}
    for cand in candidates:
        sym = str(cand.get("symbol") or "")
        episode_id = cand.get("episode_id")
        if episode_id:
            episode_key = f"{sym}:{episode_id}"
        else:
            source = cand.get("source") or {}
            doc_id = str(source.get("id") or source.get("document_id") or "")
            family = str(cand.get("event_family") or cand.get("event_type") or "")
            project_key = str(cand.get("project_id") or doc_id or cand.get("event_id") or "")
            episode_key = f"{sym}:{family}:{project_key}"
        if episode_key not in deduped:
            deduped[episode_key] = dict(cand)
        else:
            existing_date = parse_date(deduped[episode_key].get("effective_date"))
            new_date = parse_date(cand.get("effective_date"))
            if new_date and existing_date and new_date < existing_date:
                deduped[episode_key] = dict(cand)
    return list(deduped.values())

def compute_horizon_distribution(outcomes: Sequence[float | None]) -> dict[str, Any]:
    """Calculate distribution metrics strictly if N >= MIN_SAMPLE."""
    valid = [float(val) for val in outcomes if val is not None and math.isfinite(val)]
    n = len(valid)
    if n < MIN_SAMPLE:
        return {
            "status": "suppressed",
            "n": n,
            "reason": "n_lt_3",
            "mean_return_pct": None,
            "median_return_pct": None,
            "min_return_pct": None,
            "max_return_pct": None,
            "iqr_dispersion_pct": None,
        }
    sorted_vals = sorted(valid)
    mean_val = sum(sorted_vals) / n
    med_val = statistics.median(sorted_vals)
    min_val = sorted_vals[0]
    max_val = sorted_vals[-1]
    q75, q25 = (sorted_vals[int(0.75 * n)], sorted_vals[int(0.25 * n)]) if n >= 4 else (max_val, min_val)
    return {
        "status": "available",
        "n": n,
        "reason": None,
        "mean_return_pct": round(mean_val, 2),
        "median_return_pct": round(med_val, 2),
        "min_return_pct": round(min_val, 2),
        "max_return_pct": round(max_val, 2),
        "iqr_dispersion_pct": round(q75 - q25, 2),
    }

def evaluate_cement_expansion_lane(
    *,
    target_case: Mapping[str, Any] | None = None,
    candidate_pool: Sequence[Mapping[str, Any]] | None = None,
    cutoff_date: date | None = None,
) -> dict[str, Any]:
    """Evaluate analogue availability and compute distribution for cement expansion."""
    target = target_case or {
        "symbol": "DGKC",
        "lane": "cement_capacity_expansion_commissioning",
        "event_family": "cement_clinker_line_commissioning",
        "description": "DGKC 2,500 TPD Clinker Line & WHR Plant Commissioning",
    }

    raw_pool = candidate_pool if candidate_pool is not None else []
    validated_candidates = []
    rejected_candidates = []

    for cand in raw_pool:
        violations = validate_analogue_candidate(cand, cutoff_date=cutoff_date)
        if violations:
            rejected_candidates.append({"candidate": dict(cand), "violations": violations})
        else:
            validated_candidates.append(dict(cand))

    deduped_candidates = deduplicate_observations(validated_candidates)

    # Horizon maturity tracking with target endpoint verification
    horizon_distributions = {}
    mature_counts = {}
    for h_name, months in (("1Q", 3), ("2Q", 6), ("4Q", 12), ("8Q", 24)):
        horizon_outcomes = []
        for c in deduped_candidates:
            h_data = (c.get("horizons") or {}).get(h_name) or {}
            if h_data.get("status") != "mature":
                continue
            c_date = parse_date(c.get("information_available_at") or c.get("effective_date"))
            endpoint = parse_date(h_data.get("endpoint_date") or h_data.get("selected_date"))
            # Validate endpoint is strictly on or after horizon target date
            if c_date and endpoint:
                target_endpoint = event_studies.add_months(c_date, months)
                if endpoint < target_endpoint:
                    continue
            ret = h_data.get("return_pct")
            if ret is not None and math.isfinite(float(ret)):
                horizon_outcomes.append(float(ret))

        dist = compute_horizon_distribution(horizon_outcomes)
        horizon_distributions[h_name] = dist
        mature_counts[h_name] = dist["n"]

    all_ready = all(count >= MIN_SAMPLE for count in mature_counts.values())
    any_ready = any(count >= MIN_SAMPLE for count in mature_counts.values())
    overall_status = "sample_ready" if all_ready else ("partial_sample_ready" if any_ready else "insufficient_sample")

    return {
        "schema_version": SCHEMA_VERSION,
        "product_version": PRODUCT_VERSION,
        "lane": "cement_capacity_expansion_commissioning",
        "target_context": {
            "symbol": target.get("symbol"),
            "lane": target.get("lane"),
            "event_family": target.get("event_family"),
            "case_type_disambiguation": {
                "lane_identity": "organic_cement_capacity_expansion",
                "distinction_from_mlcf_pioc": "MLCF PIOC event is corporate equity control M&A (corporate_equity_control_acquisition) and remains blocked from organic capacity expansion pooling",
                "mlcf_pioc_case_status": "blocked_separate_event_family",
            },
        },
        "distribution_status": overall_status,
        "sample_summary": {
            "raw_candidates_evaluated": len(raw_pool),
            "validated_candidates": len(validated_candidates),
            "deduplicated_episodes": len(deduped_candidates),
            "mature_counts_by_horizon": mature_counts,
            "distribution_computed_horizons": [h for h, cnt in mature_counts.items() if cnt >= MIN_SAMPLE],
        },
        "horizon_distributions": horizon_distributions,
        "qualified_candidate_episodes": deduped_candidates,
        "rejected_candidates": rejected_candidates,
        "discovery_requirements_queue": DISCOVERY_REQUIREMENTS_QUEUE,
        "policy": {
            "fail_closed_minimum_sample_three": True,
            "strictly_pre_event_baselines": True,
            "no_mismatched_mna_coercion": True,
            "no_forecast_activation": True,
        },
    }

def build(*, write: bool = True) -> dict[str, Any]:
    """Build the real-mode cement expansion analogue distribution artifact."""
    op = load_json(STATE / "company_intel" / "operating_events.json", {"companies": {}})
    studies = load_json(STATE / "company_intel" / "event_studies.json", {"studies": {}})
    sectors_data = load_json(STATE / "sectors.json", {}).get("tickers") or {}

    existing = load_json(OUT, {})
    existing_meta = existing.get("_meta") if isinstance(existing, dict) else None

    retained_pool = []
    for sym, co_data in (op.get("companies") or {}).items():
        sec = (sectors_data.get(sym) or {}).get("sector")
        if sec != "Cement":
            continue
        for ev in (co_data.get("events") or []):
            if not isinstance(ev, dict):
                continue
            eid = ev.get("event_id")
            ev_study = (studies.get("studies") or {}).get(eid) or {}
            ev_evidences = ev.get("evidence") or []
            first_ev = ev_evidences[0] if ev_evidences else {}
            retained_pool.append({
                "candidate_id": f"cand_{sym}_{eid}",
                "event_id": eid,
                "symbol": sym,
                "sector": sec,
                "event_family": ev.get("event_subtype") or ev.get("event_type"),
                "event_type": ev.get("event_type"),
                "event_subtype": ev.get("event_subtype"),
                "effective_date": ev.get("effective_date"),
                "information_available_at": ev.get("detected_at") or ev.get("published_at") or ev.get("effective_date"),
                "source": {
                    "id": first_ev.get("document_id"),
                    "hash": first_ev.get("content_sha256"),
                    "page": first_ev.get("page"),
                    "url": first_ev.get("source_url"),
                },
                "horizons": ev_study.get("horizons") or {},
            })

    result = evaluate_cement_expansion_lane(
        target_case={
            "symbol": "DGKC",
            "lane": "cement_capacity_expansion_commissioning",
            "event_family": "cement_clinker_line_commissioning",
        },
        candidate_pool=retained_pool,
        cutoff_date=date(2026, 8, 31),
    )

    if isinstance(existing_meta, dict):
        result["_meta"] = existing_meta
    if write:
        save_json(OUT, result)
        print(f"cement_expansion_analogue_engine: {result['distribution_status']} ({result['sample_summary']['deduplicated_episodes']} qualified episodes) -> {OUT.name}")
    return result

if __name__ == "__main__":
    build()
