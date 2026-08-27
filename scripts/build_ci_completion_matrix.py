#!/usr/bin/env python3
"""Build the Company Intelligence completion matrix.

This is a source-independent audit artifact: it reads only retained repo/state
files and records what the current Company Intelligence product can prove today.
It never fetches, reprocesses documents, calls a model, or marks a future feature
complete just because a placeholder surface exists.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Callable

from psx_data import ROOT, STATE, load_json, save_json

OUT = STATE / "company_intel" / "completion_matrix.json"
CI_SLICE = ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json"

STATUSES = ("complete", "partial", "blocked", "not_started", "unknown")

PRIMARY_TABS = (
    "overview", "intelligence", "financials", "earnings", "business",
    "operations", "scenarios", "valuation", "guidance", "catalysts",
    "risks", "events", "filings", "peers", "ownership", "quant", "research",
)

REQUIREMENT_IDS = (
    "pilot_boundary_20_companies",
    "profile_registry_source",
    "persistent_company_brain_state",
    "company_brain_domain_registry",
    "company_brain_source_products",
    "brain_object_provenance",
    "brain_timeline",
    "brain_contract_checkers",
    "canonical_intelligence_type_registry",
    "reported_fact_type",
    "derived_fact_type",
    "inference_type",
    "scenario_type",
    "forecast_type",
    "confidence_type_coverage",
    "operating_event_state",
    "operating_event_closed_registry",
    "operating_event_official_sources",
    "operating_event_checker",
    "signal_cluster_state",
    "signal_cluster_registry",
    "signal_cluster_checker",
    "driver_graph_state",
    "sector_driver_model_registry",
    "driver_edge_coverage",
    "driver_quality_flags",
    "impact_scenario_shells",
    "event_study_state",
    "event_study_strict_baselines",
    "event_study_horizons",
    "event_study_analogues",
    "event_study_checker",
    "conditional_benchmark_state",
    "conditional_benchmark_strict_candidates",
    "causal_foundation_state",
    "causal_foundation_policy",
    "causal_foundation_checker",
    "financial_model_input_state",
    "financial_parser_contract",
    "financial_coverage_queue",
    "financial_evidence_reconciliation",
    "forecast_readiness_contract",
    "forecast_readiness_live_inputs",
    "formal_forecast_engine_code",
    "formal_forecast_live_outputs",
    "formal_valuation_engine_code",
    "formal_valuation_live_outputs",
    "market_expectations_engine_code",
    "market_expectations_live_outputs",
    "scenario_lab_state",
    "scenario_lab_formula_controls",
    "scenario_lab_ui",
    "thesis_monitoring_state",
    "management_delivery_state",
    "private_thesis_storage_contract",
    "private_thesis_live_storage",
    "training_batch_handoff",
    "training_owner_receipts",
    "ask_henneth_backend",
    "ask_henneth_endpoint_security",
    "ask_henneth_ui",
    "company_navigation_tabs",
    "company_navigation_checker",
    "peer_registry_state",
    "ownership_source_review_manifest",
    "private_access_boundary",
    "root_state_publication_boundary",
    "ci_global_no_lookahead_gate",
    "completion_matrix_slice_summary",
)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _exists(rel_path: str) -> bool:
    return (ROOT / rel_path).exists()


def _text(rel_path: str) -> str:
    path = ROOT / rel_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _ok(label: str, rel_path: str, detail: str = "") -> dict[str, Any]:
    exists = _exists(rel_path)
    return {
        "label": label,
        "path": rel_path,
        "ok": exists,
        "detail": detail or ("present" if exists else "missing"),
    }


def _check(label: str, rel_path: str) -> dict[str, Any]:
    return _ok(label, rel_path, "focused checker path")


def _state(label: str, rel_path: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"label": label, "path": rel_path, "ok": bool(ok), "detail": detail}


def _contains(label: str, rel_path: str, needles: tuple[str, ...]) -> dict[str, Any]:
    haystack = _text(rel_path)
    missing = [needle for needle in needles if needle not in haystack]
    return {
        "label": label,
        "path": rel_path,
        "ok": not missing,
        "detail": "all expected markers present" if not missing else f"missing markers: {', '.join(missing[:5])}",
    }


def requirement_status(evidence: list[dict[str, Any]], blockers: list[str], hard_blocked: bool = False) -> str:
    ok_count = sum(1 for item in evidence if item.get("ok") is True)
    if hard_blocked:
        return "blocked"
    if not evidence or ok_count == 0:
        return "not_started"
    if blockers:
        return "partial"
    if ok_count != len(evidence):
        return "partial"
    return "complete"


def _row(
    requirement_id: str,
    title: str,
    evidence: list[dict[str, Any]],
    next_required_evidence: list[str],
    blockers: list[str] | None = None,
    hard_blocked: bool = False,
) -> dict[str, Any]:
    blockers = blockers or []
    status = requirement_status(evidence, blockers, hard_blocked)
    return {
        "id": requirement_id,
        "title": title,
        "status": status,
        "evidence": evidence,
        "blockers": blockers,
        "next_required_evidence": next_required_evidence,
    }


def _pilot_symbols(profiles: dict[str, Any]) -> list[str]:
    return list(((profiles.get("pilot") or {}).get("symbols") or []))


def _exact_pilot(data: dict[str, Any], pilot: list[str]) -> bool:
    companies = data.get("companies")
    return bool(len(pilot) == 20 and isinstance(companies, dict) and set(companies) == set(pilot))


def _pilot_order(data: dict[str, Any], pilot: list[str]) -> bool:
    symbols = data.get("pilot_symbols") or []
    return list(symbols) == list(pilot)


def _company_count(data: dict[str, Any]) -> int:
    companies = data.get("companies")
    return len(companies) if isinstance(companies, dict) else 0


def _sum_company_metric(data: dict[str, Any], key: str) -> int:
    total = 0
    for row in (data.get("companies") or {}).values():
        value = row.get(key)
        if isinstance(value, int):
            total += value
    return total


def _sum_nested_count(data: dict[str, Any], key: str) -> int:
    total = 0
    for row in (data.get("companies") or {}).values():
        value = row.get(key)
        if isinstance(value, list):
            total += len(value)
        elif isinstance(value, int):
            total += value
    return total


def _blocked_impact_scenario_count(data: dict[str, Any], pilot: list[str]) -> tuple[bool, int]:
    """Validate the retained, explicitly blocked numeric-impact scenario contract."""
    impact_keys = ("revenue_impact", "ebitda_impact", "eps_impact", "fcf_impact", "valuation_impact")
    blocked_statuses = {"insufficient_data", "unmodeled_driver"}
    if not _exact_pilot(data, pilot):
        return False, 0
    count = 0
    for row in (data.get("companies") or {}).values():
        for scenario in row.get("scenarios") or []:
            count += 1
            if (
                scenario.get("impact_status") not in blocked_statuses
                or not isinstance((scenario.get("assumptions") or {}).get("missing_inputs"), list)
                or any(key not in scenario or scenario[key] is not None for key in impact_keys)
            ):
                return False, count
    return count > 0, count


def _all_companies(data: dict[str, Any], pilot: list[str], predicate: Callable[[dict[str, Any]], bool]) -> bool:
    companies = data.get("companies") or {}
    return _exact_pilot(data, pilot) and all(predicate(companies.get(symbol) or {}) for symbol in pilot)


def _has_non_empty_graphs(driver_graphs: dict[str, Any], pilot: list[str]) -> bool:
    return _all_companies(
        driver_graphs,
        pilot,
        lambda row: bool(row.get("drivers")) and bool(row.get("edges")),
    )


def _parse_iso_day(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def is_strict_event_study(row: dict[str, Any]) -> bool:
    effective = _parse_iso_day(row.get("effective_date"))
    baseline = _parse_iso_day((row.get("baseline") or {}).get("selected_date"))
    return bool(
        effective
        and baseline
        and baseline < effective
        and (row.get("baseline") or {}).get("status") == "available"
    )


def strict_no_lookahead_count(event_studies: dict[str, Any]) -> tuple[int, int]:
    studies = event_studies.get("studies") or {}
    total = len(studies)
    strict = sum(1 for row in studies.values() if isinstance(row, dict) and is_strict_event_study(row))
    return strict, total


def strict_baseline_available_count(event_studies: dict[str, Any]) -> tuple[int, int, int]:
    studies = event_studies.get("studies") or {}
    total = len(studies)
    baseline_available = sum(
        1
        for row in studies.values()
        if isinstance(row, dict) and (row.get("baseline") or {}).get("status") == "available"
    )
    strict = sum(1 for row in studies.values() if isinstance(row, dict) and is_strict_event_study(row))
    return strict, baseline_available, total


def _study_count_with_horizons(event_studies: dict[str, Any]) -> tuple[int, int]:
    studies = event_studies.get("studies") or {}
    wanted = {"1Q", "2Q", "4Q", "8Q"}
    with_horizons = sum(1 for row in studies.values() if set((row.get("horizons") or {})) == wanted)
    return with_horizons, len(studies)


def _study_count_with_analogues(event_studies: dict[str, Any]) -> tuple[int, int]:
    studies = event_studies.get("studies") or {}
    with_contract = sum(
        1
        for row in studies.values()
        if isinstance(row.get("analogues"), list) and set(row.get("analogue_aggregate") or {}) == {"1Q", "2Q", "4Q", "8Q"}
    )
    return with_contract, len(studies)


def _blocked_summary_count(data: dict[str, Any]) -> int:
    return int((data.get("summary") or {}).get("blocked_company_count") or 0)


def _computed_summary_count(data: dict[str, Any]) -> int:
    return int((data.get("summary") or {}).get("computed_company_count") or 0)


def _completion_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {status: 0 for status in STATUSES}
    for row in rows:
        counts[row["status"]] += 1
    if counts["blocked"]:
        overall = "blocked"
    elif counts["partial"]:
        overall = "partial"
    elif counts["not_started"] or counts["unknown"]:
        overall = "partial"
    else:
        overall = "complete"
    return {
        "overall_status": overall,
        "requirement_count": len(rows),
        "counts": counts,
        "complete_requirement_ids": [row["id"] for row in rows if row["status"] == "complete"],
        "blocked_requirement_ids": [row["id"] for row in rows if row["status"] == "blocked"],
    }


def slice_summary(matrix: dict[str, Any]) -> dict[str, Any]:
    summary = matrix.get("summary") or {}
    counts = summary.get("counts") or {}
    return {
        "artifact": "state/company_intel/completion_matrix.json",
        "as_of": matrix.get("as_of") or "unknown",
        "overall_status": summary.get("overall_status") or "unknown",
        "requirement_count": summary.get("requirement_count") or 0,
        "complete": counts.get("complete", 0),
        "partial": counts.get("partial", 0),
        "blocked": counts.get("blocked", 0),
    }


def _sync_slice_summary(matrix: dict[str, Any]) -> None:
    ci_slice = load_json(CI_SLICE, {})
    if not isinstance(ci_slice, dict) or not ci_slice:
        return
    meta = ci_slice.setdefault("meta", {})
    if not isinstance(meta, dict):
        return
    meta["completion_matrix"] = slice_summary(matrix)
    save_json(CI_SLICE, ci_slice)


def build(write: bool = True) -> dict[str, Any]:
    profiles = load_json(STATE / "company_profiles.json", {})
    pilot = _pilot_symbols(profiles)
    brains = load_json(STATE / "company_intel" / "company_brains.json", {})
    operating_events = load_json(STATE / "company_intel" / "operating_events.json", {})
    driver_graphs = load_json(STATE / "company_intel" / "driver_graphs.json", {})
    impact_scenarios = load_json(STATE / "company_intel" / "impact_scenarios.json", {})
    event_studies = load_json(STATE / "company_intel" / "event_studies.json", {})
    conditional_benchmarks = load_json(STATE / "company_intel" / "conditional_benchmarks.json", {})
    causal_foundations = load_json(STATE / "company_intel" / "causal_foundations.json", {})
    financial_model_inputs = load_json(STATE / "company_intel" / "financial_model_inputs.json", {})
    financial_coverage = load_json(STATE / "company_intel" / "financial_coverage.json", {})
    financial_reconciliation = load_json(STATE / "company_intel" / "financial_evidence_reconciliation.json", {})
    forecast_readiness = load_json(STATE / "company_intel" / "forecast_readiness.json", {})
    financial_forecasts = load_json(STATE / "company_intel" / "financial_forecasts.json", {})
    formal_valuations = load_json(STATE / "company_intel" / "formal_valuations.json", {})
    market_expectations = load_json(STATE / "company_intel" / "market_expectations.json", {})
    scenario_lab = load_json(STATE / "company_intel" / "scenario_lab.json", {})
    private_thesis_receipt = load_json(STATE / "company_intel" / "private_thesis_storage_receipt.json", {})
    signal_clusters = load_json(STATE / "company_intel" / "signal_clusters.json", {})
    thesis_monitoring = load_json(STATE / "company_intel" / "thesis_monitoring.json", {})
    confidence = load_json(STATE / "company_intel" / "intelligence_confidence.json", {})
    management_delivery = load_json(STATE / "company_intel" / "management_delivery.json", {})
    evidence_watchlist = load_json(STATE / "company_intel" / "evidence_watchlist.json", {})
    monitoring = load_json(STATE / "company_intel" / "monitoring.json", {})
    guidance = load_json(STATE / "company_intel" / "guidance_contradictions.json", {})
    peer_registry = load_json(STATE / "company_intel" / "peer_registry.json", {})
    ownership_manifest = load_json(ROOT / "config" / "ownership_source_review_manifest.json", {})
    ci_slice = load_json(CI_SLICE, {})

    strict_studies, baseline_available_studies, study_total = strict_baseline_available_count(event_studies)
    horizon_studies, _ = _study_count_with_horizons(event_studies)
    analogue_studies, _ = _study_count_with_analogues(event_studies)
    ready_count = int((forecast_readiness.get("summary") or {}).get("ready_company_count") or 0)
    history_qualified_company_count = int((forecast_readiness.get("summary") or {}).get("history_qualified_company_count") or 0)
    adapter_unavailable_company_count = int((forecast_readiness.get("summary") or {}).get("adapter_unavailable_company_count") or 0)
    formal_output_blocked_count = sum(
        1 for row in (forecast_readiness.get("companies") or {}).values()
        if all(str((row.get("downstream_status") or {}).get(key) or "").startswith("blocked")
               for key in ("forecast", "valuation", "market_expectations", "numeric_impact"))
    )
    qualified_fact_company_count = int((forecast_readiness.get("summary") or {}).get("qualified_fact_company_count") or 0)
    event_count = sum(len(((operating_events.get("companies") or {}).get(symbol) or {}).get("events") or []) for symbol in pilot)
    dated_event_count = sum(1 for symbol in pilot for event in (((operating_events.get("companies") or {}).get(symbol) or {}).get("events") or []) if event.get("effective_date"))
    benchmark_count = sum(int(((conditional_benchmarks.get("companies") or {}).get(symbol) or {}).get("benchmark_count") or 0) for symbol in pilot)
    causal_row_count = sum(len(((causal_foundations.get("companies") or {}).get(symbol) or {}).get("causal_rows") or []) for symbol in pilot)
    guidance_object_count = sum(int(((guidance.get("companies") or {}).get(symbol) or {}).get("object_count") or 0) for symbol in pilot)
    active_thesis_count = int((management_delivery.get("summary") or {}).get("active_thesis_count") or 0)
    watch_count = int((evidence_watchlist.get("summary") or {}).get("active_watch_count") or 0)
    alert_count = int((monitoring.get("summary") or {}).get("alert_count") or 0)
    ownership_summary = ownership_manifest.get("summary") or {}
    ownership_candidate_count = int(ownership_summary.get("candidate_count") or 0)
    ownership_activated_count = int(ownership_summary.get("activated_company_count") or 0)
    blocked_impact_contract, blocked_impact_scenario_count = _blocked_impact_scenario_count(impact_scenarios, pilot)

    rows = [
        _row(
            "pilot_boundary_20_companies",
            "Pilot boundary is exactly 20 companies",
            [
                _state("profile pilot list", "state/company_profiles.json", len(pilot) == 20 and len(set(pilot)) == 20, f"{len(pilot)} unique pilot symbols"),
                _state("brain state pilot boundary", "state/company_intel/company_brains.json", _exact_pilot(brains, pilot), f"{_company_count(brains)} company rows"),
                _state("CI slice pilot boundary", "Henneth Desk 2.CI.0/data/company_intelligence.json", len(ci_slice.get("tickers") or []) == len(pilot), f"{len(ci_slice.get('tickers') or [])} slice rows"),
            ],
            ["Keep new Company Intelligence products keyed to company_profiles pilot.symbols."],
        ),
        _row(
            "profile_registry_source",
            "Profile registry is the company identity source",
            [
                _ok("profile state", "state/company_profiles.json"),
                _state("brain identity coverage", "state/company_intel/company_brains.json", _all_companies(brains, pilot, lambda row: isinstance(row.get("identity"), dict)), f"{_company_count(brains)} identity rows"),
            ],
            ["Any future company identity field must be emitted from retained profile/state sources."],
        ),
        _row(
            "persistent_company_brain_state",
            "Persistent Company Brain state exists for every pilot company",
            [
                _state("exact 20-company brain state", "state/company_intel/company_brains.json", _exact_pilot(brains, pilot), f"{_company_count(brains)} company rows"),
                _check("brain contract checker", "scripts/check_company_brains.py"),
                _check("brain UI contract checker", "scripts/check_company_brain_ui.mjs"),
            ],
            ["Keep Brain rows source-resolvable and byte-idempotent before adding new domains."],
        ),
        _row(
            "company_brain_domain_registry",
            "Company Brain domain registry covers the first-class domains",
            [
                _state("21-domain registry", "state/company_intel/company_brains.json", len(brains.get("domains") or []) == 21, f"{len(brains.get('domains') or [])} domains"),
                _state("domains attached to every brain", "state/company_intel/company_brains.json", _all_companies(brains, pilot, lambda row: isinstance(row.get("domains"), dict)), f"{_company_count(brains)} domain maps"),
            ],
            ["Add a domain only with a retained source product and UI/checker coverage."],
        ),
        _row(
            "company_brain_source_products",
            "Company Brain references retained source products",
            [
                _state("source product registry", "state/company_intel/company_brains.json", len(brains.get("source_products") or []) >= 10, f"{len(brains.get('source_products') or [])} source products"),
                _contains("event-study source refs", "state/company_intel/company_brains.json", ("state/company_intel/event_studies.json",)),
            ],
            ["New source products must be retained state files, not browser-only derivations."],
        ),
        _row(
            "brain_object_provenance",
            "Brain objects carry source provenance",
            [
                _contains("source_path markers", "state/company_intel/company_brains.json", ("source_path", "source_product")),
                _check("provenance lint", "scripts/provenance_lint.py"),
            ],
            ["Future Brain object producers need URL/path/page evidence before completion credit."],
        ),
        _row(
            "brain_timeline",
            "Brain timeline exists as a retained state surface",
            [
                _state("timeline per pilot company", "state/company_intel/company_brains.json", _all_companies(brains, pilot, lambda row: isinstance(row.get("timeline"), list)), f"{_company_count(brains)} timeline rows"),
                _contains("historical events domain", "state/company_intel/company_brains.json", ("historical_events",)),
            ],
            ["Expand timeline only from dated retained events and documents."],
        ),
        _row(
            "brain_contract_checkers",
            "Brain backend and UI contracts are checked",
            [
                _check("brain contract checker", "scripts/check_company_brains.py"),
                _check("brain UI checker", "scripts/check_company_brain_ui.mjs"),
                _ok("preflight gate includes CI products", "scripts/preflight.py"),
            ],
            ["Run full preflight before release sign-off."],
        ),
        _row(
            "canonical_intelligence_type_registry",
            "Canonical intelligence type registry is shared",
            [
                _ok("shared type registry", "scripts/intelligence_types.py"),
                _state("five canonical types emitted", "state/company_intel/company_brains.json", brains.get("intelligence_types") == ["reported_fact", "derived_fact", "inference", "scenario", "forecast"], "reported_fact, derived_fact, inference, scenario, forecast"),
            ],
            ["Extend the registry only when a producer emits source-resolvable objects of that type."],
        ),
        _row(
            "reported_fact_type",
            "Reported facts are represented as first-class intelligence",
            [
                _contains("reported fact objects", "state/company_intel/company_brains.json", ("reported_fact",)),
                _ok("type registry owner", "scripts/intelligence_types.py"),
            ],
            ["Keep reported facts tied to retained official or market-data source paths."],
        ),
        _row(
            "derived_fact_type",
            "Derived facts are represented as first-class intelligence",
            [
                _contains("derived fact objects", "state/company_intel/company_brains.json", ("derived_fact",)),
                _ok("financial model input derivations", "state/company_intel/financial_model_inputs.json"),
            ],
            ["Derived facts need formula IDs and operand provenance before new completion credit."],
        ),
        _row(
            "inference_type",
            "Inferences are represented as first-class intelligence",
            [
                _contains("inference objects", "state/company_intel/company_brains.json", ("inference",)),
                _state("confidence assessments", "state/company_intel/intelligence_confidence.json", _exact_pilot(confidence, pilot), f"{_company_count(confidence)} company rows"),
            ],
            ["Inferences must remain confidence-scored and separated from reported facts."],
        ),
        _row(
            "scenario_type",
            "Scenarios are represented as first-class intelligence",
            [
                _contains("scenario objects", "state/company_intel/company_brains.json", ("scenario",)),
                _state("scenario lab state", "state/company_intel/scenario_lab.json", _exact_pilot(scenario_lab, pilot), f"{_company_count(scenario_lab)} company rows"),
            ],
            ["Scenario arithmetic must remain caller-supplied and separate from formal forecasts."],
        ),
        _row(
            "forecast_type",
            "Forecast type exists but formal forecast objects are blocked until inputs qualify",
            [
                _contains("forecast type marker", "state/company_intel/company_brains.json", ("forecast",)),
                _state("forecast readiness contract", "state/company_intel/forecast_readiness.json", _exact_pilot(forecast_readiness, pilot), f"{ready_count} input-ready companies"),
            ],
            ["Three aligned annual consolidated PKR periods and approved assumptions before forecast objects can be computed."],
            [f"Real input-ready company count is {ready_count}; forecast objects remain non-computed."],
        ),
        _row(
            "confidence_type_coverage",
            "Intelligence confidence covers the pilot",
            [
                _state("typed confidence rows", "state/company_intel/intelligence_confidence.json", _exact_pilot(confidence, pilot), f"{_company_count(confidence)} company rows"),
                _check("confidence checker", "scripts/check_intelligence_confidence.py"),
                _check("confidence UI checker", "scripts/check_intelligence_confidence_ui.mjs"),
            ],
            ["Confidence scoring should continue to use retained signal clusters and strict analogues only."],
        ),
        _row(
            "operating_event_state",
            "Operating events exist for the pilot",
            [
                _state("operating event state", "state/company_intel/operating_events.json", _exact_pilot(operating_events, pilot), f"{_company_count(operating_events)} company rows"),
                _state("canonical event rows", "state/company_intel/operating_events.json", event_count > 0, f"{event_count} events"),
            ],
            ["Add event classes only through the closed event registry and retained evidence."],
        ),
        _row(
            "operating_event_closed_registry",
            "Operating event type registry is explicit",
            [
                _state("closed event type registry", "state/company_intel/operating_events.json", bool((operating_events.get("event_registry") or {}).get("status") == "closed" and (operating_events.get("event_registry") or {}).get("registry_version") and set(operating_events.get("event_types") or []) == {item.get("event_type") for item in ((operating_events.get("event_registry") or {}).get("event_types") or [])}), f"{len(operating_events.get('event_types') or [])} closed event types"),
                _contains("event support rules", "scripts/build_operating_events.py", ("strict_event_is_supported", "event_is_supported")),
            ],
            ["New event types need registry support and checker coverage."],
        ),
        _row(
            "operating_event_official_sources",
            "Operating events resolve to official retained sources",
            [
                _contains("official source URLs", "state/company_intel/operating_events.json", ("source_url", "dps.psx.com.pk")),
                _state("event source declaration", "state/company_intel/operating_events.json", "state/company_documents.json" in str(operating_events.get("source")), str(operating_events.get("source"))),
            ],
            ["Missing source URL or evidence rows must fail closed as unsupported events."],
        ),
        _row(
            "operating_event_checker",
            "Operating event contract is checked",
            [
                _check("operating intelligence checker", "scripts/check_operating_intelligence.py"),
                _ok("operating event builder", "scripts/build_operating_events.py"),
            ],
            ["Run focused checker and preflight after event registry changes."],
        ),
        _row(
            "signal_cluster_state",
            "Signal clusters exist for every pilot company",
            [
                _state("signal cluster state", "state/company_intel/signal_clusters.json", _exact_pilot(signal_clusters, pilot), f"{_company_count(signal_clusters)} company rows"),
                _state("clusterable signal count", "state/company_intel/signal_clusters.json", _sum_company_metric(signal_clusters, "clusterable_count") > 0, f"{_sum_company_metric(signal_clusters, 'clusterable_count')} clusterable records"),
            ],
            ["Broaden signals only through retained events and the cluster registry."],
        ),
        _row(
            "signal_cluster_registry",
            "Signal cluster registry version is retained",
            [
                _state("registry version", "state/company_intel/signal_clusters.json", bool(signal_clusters.get("registry_version")), str(signal_clusters.get("registry_version"))),
                _state("freshness metadata", "state/company_intel/signal_clusters.json", _all_companies(signal_clusters, pilot, lambda row: isinstance(row.get("freshness"), str) and bool(row.get("freshness")) and row.get("registry_version") == signal_clusters.get("registry_version")), f"{_company_count(signal_clusters)} versioned freshness rows"),
            ],
            ["Cluster registry changes need deterministic checker updates."],
        ),
        _row(
            "signal_cluster_checker",
            "Signal cluster contract is checked",
            [
                _check("signal cluster checker", "scripts/check_signal_clusters.py"),
                _ok("signal cluster builder", "scripts/build_signal_clusters.py"),
            ],
            ["Run the checker before completing new signal categories."],
        ),
        _row(
            "driver_graph_state",
            "Declarative driver graphs exist for every pilot company",
            [
                _state("full-pilot driver graphs", "state/company_intel/driver_graphs.json", _has_non_empty_graphs(driver_graphs, pilot), f"{_company_count(driver_graphs)} company rows"),
                _state("schema v2 driver graph", "state/company_intel/driver_graphs.json", driver_graphs.get("schema_version") == 2, f"schema {driver_graphs.get('schema_version')}"),
            ],
            ["Measured driver evidence can be layered later; current graphs are declarative routing only."],
        ),
        _row(
            "sector_driver_model_registry",
            "Sector driver model registry exists",
            [
                _ok("sector driver model registry", "scripts/sector_driver_models.py"),
                _state("supported sector list", "state/company_intel/driver_graphs.json", len(driver_graphs.get("supported_sectors") or []) > 0, f"{len(driver_graphs.get('supported_sectors') or [])} sectors"),
            ],
            ["New sector models must be added in the registry, not scattered in consumers."],
        ),
        _row(
            "driver_edge_coverage",
            "Driver graph edges are emitted for downstream consumers",
            [
                _state("edges per company", "state/company_intel/driver_graphs.json", _all_companies(driver_graphs, pilot, lambda row: bool(row.get("edges"))), f"{sum(len(((driver_graphs.get('companies') or {}).get(s) or {}).get('edges') or []) for s in pilot)} edges"),
                _check("driver/event routing checker", "scripts/check_operating_intelligence.py"),
            ],
            ["Edges become measured only after retained official events and period-aligned financial outcomes resolve."],
        ),
        _row(
            "driver_quality_flags",
            "Driver graph quality flags are explicit",
            [
                _state("quality flags per company", "state/company_intel/driver_graphs.json", _all_companies(driver_graphs, pilot, lambda row: isinstance(row.get("quality_flags"), list)), f"{_company_count(driver_graphs)} quality flag rows"),
            ],
            ["Keep unsupported or thin sector logic explicit in quality_flags."],
        ),
        _row(
            "impact_scenario_shells",
            "Impact scenario shells exist but numeric impacts are blocked",
            [
                _state("impact scenario shells", "state/company_intel/impact_scenarios.json", _exact_pilot(impact_scenarios, pilot), f"{_company_count(impact_scenarios)} company rows"),
                _state("explicit blocked numeric-impact contract", "state/company_intel/impact_scenarios.json", blocked_impact_contract, f"{blocked_impact_scenario_count} retained shells with null numeric impacts and explicit missing inputs"),
            ],
            ["Sourced operands for numeric impacts and enough mature analogue samples for published aggregates."],
            ["Numeric impact, probability, EBITDA, FCF, DCF and formal forecast outputs remain blocked or null."],
        ),
        _row(
            "event_study_state",
            "Historical event studies exist one-for-one with operating events",
            [
                _state("event-study state", "state/company_intel/event_studies.json", study_total == event_count and study_total > 0, f"{study_total} studies for {event_count} events"),
                _state("pilot boundary", "state/company_intel/event_studies.json", set(event_studies.get("pilot_symbols") or []) == set(pilot), f"{len(event_studies.get('pilot_symbols') or [])} symbols"),
            ],
            ["Keep one study per canonical operating event."],
        ),
        _row(
            "event_study_strict_baselines",
            "Event studies use strict no-lookahead baselines",
            [
                _state("strict baseline derivation", "state/company_intel/event_studies.json", strict_studies == baseline_available_studies and strict_studies > 0, f"{strict_studies}/{baseline_available_studies} baseline-available studies have baseline.selected_date before effective_date; {study_total} total studies"),
                _check("event study checker", "scripts/check_event_studies.py"),
            ],
            ["Future studies must preserve baseline.selected_date strictly before effective_date."],
        ),
        _row(
            "event_study_horizons",
            "Event studies carry fixed calendar horizons",
            [
                _state("1Q/2Q/4Q/8Q horizons", "state/company_intel/event_studies.json", horizon_studies == study_total and study_total > 0, f"{horizon_studies}/{study_total} studies"),
                _contains("raw return limitations", "state/company_intel/event_studies.json", ("raw_price_return_not_adjusted_or_total_return",)),
            ],
            ["Add new horizons only through the event_studies helper/checker contract."],
        ),
        _row(
            "event_study_analogues",
            "Event studies expose ex-ante analogue candidates and aggregate suppression",
            [
                _state("analogue contract", "state/company_intel/event_studies.json", analogue_studies == study_total and study_total > 0, f"{analogue_studies}/{study_total} studies"),
                _contains("thin sample suppression", "state/company_intel/event_studies.json", ("n_lt_3",)),
            ],
            ["Mature analogue aggregates need at least three ex-ante candidates."],
        ),
        _row(
            "event_study_checker",
            "Event study contract is checked",
            [
                _check("event study checker", "scripts/check_event_studies.py"),
                _ok("event study builder", "scripts/build_event_studies.py"),
                _ok("event study helpers", "scripts/event_studies.py"),
            ],
            ["Run focused checker after changing event-study schema or horizon logic."],
        ),
        _row(
            "conditional_benchmark_state",
            "Conditional benchmark state exists for every pilot company",
            [
                _state("conditional benchmarks", "state/company_intel/conditional_benchmarks.json", _exact_pilot(conditional_benchmarks, pilot), f"{_company_count(conditional_benchmarks)} company rows"),
                _state("dated benchmark count", "state/company_intel/conditional_benchmarks.json", benchmark_count == dated_event_count, f"{benchmark_count}/{dated_event_count} dated events; {event_count - dated_event_count} undated events excluded by no-lookahead"),
            ],
            ["Keep benchmark rows aligned one-for-one to dated retained operating events; undated evidence stays excluded."],
        ),
        _row(
            "conditional_benchmark_strict_candidates",
            "Conditional benchmarks use strict historical candidates but suppress thin samples",
            [
                _contains("candidate groups", "state/company_intel/conditional_benchmarks.json", ("same_company_exact", "same_sector_exact")),
                _contains("blocked states", "state/company_intel/conditional_benchmarks.json", ("descriptive_not_causal", "n_lt_3")),
                _check("conditional benchmark checker", "scripts/check_conditional_benchmarks.py"),
            ],
            ["Published aggregate statistics require mature ex-ante samples; thin samples stay suppressed."],
            ["Current benchmarks are descriptive and explicitly block causal, peer, financial, forecast and valuation states."],
        ),
        _row(
            "causal_foundation_state",
            "Causal foundation map exists for driver edges",
            [
                _state("causal foundations", "state/company_intel/causal_foundations.json", _exact_pilot(causal_foundations, pilot), f"{_company_count(causal_foundations)} company rows"),
                _state("edge-resolved causal rows", "state/company_intel/causal_foundations.json", causal_row_count > 0, f"{causal_row_count} causal rows"),
            ],
            ["Causal rows need period-aligned financial outcomes before any numeric impact can be claimed."],
        ),
        _row(
            "causal_foundation_policy",
            "Causal foundation policy blocks numeric impact and forecasts",
            [
                _state("categorical policy", "state/company_intel/causal_foundations.json", bool((causal_foundations.get("policy") or {}).get("categorical_status_only")), str(causal_foundations.get("policy") or {})),
                _contains("blocked numeric policy", "state/company_intel/causal_foundations.json", ("no_numeric_impact", "no_forecast_probability_valuation_or_price")),
            ],
            ["Any causal estimate requires new retained evidence and checker acceptance."],
        ),
        _row(
            "causal_foundation_checker",
            "Causal foundation contract is checked",
            [
                _check("causal foundations checker", "scripts/check_causal_foundations.py"),
                _check("causal foundations UI checker", "scripts/check_causal_foundations_ui.mjs"),
            ],
            ["Run checker before promoting new driver-edge evidence states."],
        ),
        _row(
            "financial_model_input_state",
            "Financial model input state exists for every pilot company",
            [
                _state("financial model inputs", "state/company_intel/financial_model_inputs.json", _exact_pilot(financial_model_inputs, pilot), f"{_company_count(financial_model_inputs)} company rows"),
                _state("downstream statuses retained", "state/company_intel/financial_model_inputs.json", _all_companies(financial_model_inputs, pilot, lambda row: isinstance(row.get("downstream_status"), dict)), f"{_company_count(financial_model_inputs)} downstream rows"),
            ],
            ["Promote inputs only after three aligned annual consolidated PKR periods resolve without conflicts."],
        ),
        _row(
            "financial_parser_contract",
            "Financial parser contract is fail-closed and fixture-backed",
            [
                _check("financial model input checker", "scripts/check_financial_model_inputs.py"),
                _ok("financial statement parser", "scripts/financial_statement_facts.py"),
                _contains("current parser revision", "scripts/check_financial_model_inputs.py", ("financial_statement_v2", "block_geometry_v5")),
            ],
            ["Add parser cases with adversarial fixtures before accepting new table shapes."],
        ),
        _row(
            "financial_coverage_queue",
            "Financial coverage queue is retained for all pilot companies",
            [
                _state("financial coverage", "state/company_intel/financial_coverage.json", _exact_pilot(financial_coverage, pilot), f"{_company_count(financial_coverage)} company rows"),
                _state(
                    "covered companies",
                    "state/company_intel/financial_coverage.json",
                    int((financial_coverage.get("summary") or {}).get("queued_company_count") or 0)
                    + sum(1 for row in (financial_coverage.get("companies") or {}).values() if isinstance(row, dict) and row.get("status") == "complete")
                    == len(pilot),
                    f"{(financial_coverage.get('summary') or {}).get('queued_company_count')} queued + "
                    f"{sum(1 for row in (financial_coverage.get('companies') or {}).values() if isinstance(row, dict) and row.get('status') == 'complete')} qualified",
                ),
                _check("financial coverage UI checker", "scripts/check_financial_coverage_ui.mjs"),
            ],
            ["Queue items must become qualified facts through official-document extraction, not manual estimates."],
        ),
        _row(
            "financial_evidence_reconciliation",
            "Financial evidence reconciliation records conflicts and missing slots",
            [
                _state("reconciliation state", "state/company_intel/financial_evidence_reconciliation.json", _exact_pilot(financial_reconciliation, pilot), f"{_company_count(financial_reconciliation)} company rows"),
                _state("conflict/missing-slot summary", "state/company_intel/financial_evidence_reconciliation.json", bool(financial_reconciliation.get("summary")), str(financial_reconciliation.get("summary") or {})),
                _check("reconciliation checker", "scripts/check_financial_evidence_reconciliation.py"),
            ],
            ["Resolve source conflicts and missing slots before numeric forecasts can leave blocked state."],
        ),
        _row(
            "forecast_readiness_contract",
            "Forecast readiness contract exists and blocks formal outputs without approved assumptions",
            [
                _state("readiness state", "state/company_intel/forecast_readiness.json", _exact_pilot(forecast_readiness, pilot), f"{_company_count(forecast_readiness)} company rows"),
                _state("blocked output policy", "state/company_intel/forecast_readiness.json", formal_output_blocked_count == len(pilot), f"{formal_output_blocked_count} companies with formal outputs blocked"),
                _check("forecast readiness checker", "scripts/check_forecast_contract.py"),
            ],
            ["Three qualified periods plus an executable adapter establish input readiness only; owner-approved assumptions remain required before numeric forecasts can compute."],
        ),
        _row(
            "forecast_readiness_live_inputs",
            "Live state has partially qualified financial history",
            [
                _state("history-qualified company count", "state/company_intel/forecast_readiness.json", history_qualified_company_count > 0, f"{history_qualified_company_count} companies with qualified history"),
                _state("input-ready or adapter-unavailable company count", "state/company_intel/forecast_readiness.json", (ready_count + adapter_unavailable_company_count) > 0, f"{ready_count} input-ready; {adapter_unavailable_company_count} adapter-unavailable"),
                _state("qualified fact company count", "state/company_intel/forecast_readiness.json", qualified_fact_company_count > 0, f"{qualified_fact_company_count} qualified-fact companies"),
            ],
            ["More pilot companies need three aligned annual consolidated PKR periods and sector adapters; all still need owner-approved assumptions before numeric outputs can become live."],
            [f"Real history-qualified company count is {history_qualified_company_count}; ready company count is {ready_count}; adapter-unavailable count is {adapter_unavailable_company_count}; formal numeric outputs remain blocked."],
        ),
        _row(
            "formal_forecast_engine_code",
            "Formal forecast engine has synthetic formula coverage",
            [
                _ok("formal financial engine builder", "scripts/build_formal_financial_engines.py"),
                _ok("formal financial engine module", "scripts/formal_financial_engines.py"),
                _check("formal engine checker", "scripts/check_formal_financial_engines.py"),
            ],
            ["Live computation still depends on qualified inputs and owner-approved assumptions."],
        ),
        _row(
            "formal_forecast_live_outputs",
            "Formal forecast live outputs remain blocked",
            [
                _state("forecast output state", "state/company_intel/financial_forecasts.json", _exact_pilot(financial_forecasts, pilot), f"{_company_count(financial_forecasts)} company rows"),
                _state("computed forecast count", "state/company_intel/financial_forecasts.json", _computed_summary_count(financial_forecasts) > 0, f"{_computed_summary_count(financial_forecasts)} computed companies"),
            ],
            ["Qualified financial inputs and approved assumptions are required before live forecast output can be complete."],
            [f"Live computed forecast count is {_computed_summary_count(financial_forecasts)}."],
            hard_blocked=True,
        ),
        _row(
            "formal_valuation_engine_code",
            "Formal valuation engine has synthetic formula coverage",
            [
                _ok("formal valuation state", "state/company_intel/formal_valuations.json"),
                _ok("formal financial engine module", "scripts/formal_financial_engines.py"),
                _check("formal engine checker", "scripts/check_formal_financial_engines.py"),
            ],
            ["Live valuation still depends on qualified inputs, approved assumptions and market operands."],
        ),
        _row(
            "formal_valuation_live_outputs",
            "Formal valuation live outputs remain blocked",
            [
                _state("valuation output state", "state/company_intel/formal_valuations.json", _exact_pilot(formal_valuations, pilot), f"{_company_count(formal_valuations)} company rows"),
                _state("computed valuation count", "state/company_intel/formal_valuations.json", _computed_summary_count(formal_valuations) > 0, f"{_computed_summary_count(formal_valuations)} computed companies"),
            ],
            ["Qualified inputs, approved assumptions and explicit valuation operands are required before completion."],
            [f"Live computed valuation count is {_computed_summary_count(formal_valuations)}."],
            hard_blocked=True,
        ),
        _row(
            "market_expectations_engine_code",
            "Market expectations engine has synthetic formula coverage",
            [
                _ok("market expectations state", "state/company_intel/market_expectations.json"),
                _ok("formal financial engine module", "scripts/formal_financial_engines.py"),
                _check("formal engine checker", "scripts/check_formal_financial_engines.py"),
            ],
            ["Live reverse-expectations output still depends on qualified inputs and approved market operands."],
        ),
        _row(
            "market_expectations_live_outputs",
            "Market expectations live outputs remain blocked",
            [
                _state("market expectations state", "state/company_intel/market_expectations.json", _exact_pilot(market_expectations, pilot), f"{_company_count(market_expectations)} company rows"),
                _state("computed expectations count", "state/company_intel/market_expectations.json", _computed_summary_count(market_expectations) > 0, f"{_computed_summary_count(market_expectations)} computed companies"),
            ],
            ["Qualified inputs plus approved price, share-count and balance-sheet operands are required before completion."],
            [f"Live computed market-expectations count is {_computed_summary_count(market_expectations)}."],
            hard_blocked=True,
        ),
        _row(
            "scenario_lab_state",
            "Scenario Lab state exists for every pilot company",
            [
                _state("scenario lab exact pilot", "state/company_intel/scenario_lab.json", _exact_pilot(scenario_lab, pilot), f"{_company_count(scenario_lab)} company rows"),
                _state("scenario operands", "state/company_intel/scenario_lab.json", bool(scenario_lab.get("formula_operands")), "formula_operands present"),
            ],
            ["Scenario Lab remains sensitivity arithmetic, not a formal valuation claim."],
        ),
        _row(
            "scenario_lab_formula_controls",
            "Scenario Lab formula controls are checked",
            [
                _check("scenario lab checker", "scripts/check_company_scenario_lab.py"),
                _contains("scenario formula IDs", "state/company_intel/scenario_lab.json", ("formula_ids",)),
            ],
            ["Add fixtures for any new scenario formula before exposing it."],
        ),
        _row(
            "scenario_lab_ui",
            "Scenario Lab UI contract is checked",
            [
                _check("scenario lab UI checker", "scripts/check_company_scenario_lab_ui.mjs"),
                _contains("scenario tab", "Henneth Desk 2.CI.0/app.js", ("scenarios",)),
            ],
            ["Keep UI display-only over emitted state."],
        ),
        _row(
            "thesis_monitoring_state",
            "Deterministic thesis monitoring state exists",
            [
                _state("thesis monitoring", "state/company_intel/thesis_monitoring.json", _exact_pilot(thesis_monitoring, pilot), f"{_company_count(thesis_monitoring)} company rows"),
                _check("thesis monitoring checker", "scripts/check_thesis_monitoring.py"),
                _check("thesis monitoring UI checker", "scripts/check_thesis_monitoring_ui.mjs"),
            ],
            ["Private owner-authored theses require live storage proof before storage completion."],
        ),
        _row(
            "management_delivery_state",
            "Management delivery and continuous monitoring state track thesis follow-through",
            [
                _state("management delivery", "state/company_intel/management_delivery.json", _exact_pilot(management_delivery, pilot), f"{_company_count(management_delivery)} company rows"),
                _state("delivery records", "state/company_intel/management_delivery.json", active_thesis_count > 0, f"{active_thesis_count} active theses"),
                _check("management delivery checker", "scripts/check_management_delivery.py"),
                _state("continuous monitoring", "state/company_intel/monitoring.json", _exact_pilot(monitoring, pilot), f"{_company_count(monitoring)} company rows; {alert_count} retained alerts"),
                _check("continuous monitoring checker", "scripts/check_ci_monitoring.py"),
                _check("continuous monitoring UI checker", "scripts/check_ci_monitoring_ui.mjs"),
            ],
            ["Delivery records stay categorical until later retained official evidence resolves."],
        ),
        _row(
            "private_thesis_storage_contract",
            "Private thesis storage contract is schema-configured and code-ready",
            [
                _ok("private thesis SQL contract", "docs/company_theses.sql"),
                _state(
                    "private thesis schema receipt",
                    "state/company_intel/private_thesis_storage_receipt.json",
                    private_thesis_receipt.get("schema_status") == "configured",
                    f"schema {private_thesis_receipt.get('schema_status') or 'unknown'}; live {private_thesis_receipt.get('live_verification_status') or 'unknown'}",
                ),
                _check("private thesis receipt checker", "scripts/check_private_thesis_storage_receipt.py"),
                _check("private thesis security checker", "scripts/check_company_theses_security.mjs"),
                _check("thesis UI checker", "scripts/check_company_theses_ui.mjs"),
            ],
            ["Live owner-token CRUD/RLS verification is still required before private thesis storage itself is complete."],
        ),
        _row(
            "private_thesis_live_storage",
            "Private thesis storage has not been live-verified",
            [
                _ok("private thesis SQL contract", "docs/company_theses.sql"),
                _state(
                    "private thesis live verification receipt",
                    "state/company_intel/private_thesis_storage_receipt.json",
                    private_thesis_receipt.get("live_verification_status") == "verified",
                    f"live verification {private_thesis_receipt.get('live_verification_status') or 'unknown'}",
                ),
            ],
            ["A live owner-token storage smoke test and receipt proving SQL/RLS is applied."],
            ["Repo evidence proves schema configuration only; it does not prove owner-token CRUD or cross-user RLS isolation."],
            hard_blocked=True,
        ),
        _row(
            "training_batch_handoff",
            "Training-mode synthesis handoff exists",
            [
                _ok("training batch handoff", "scripts/prepare_synthesis_batch.py"),
                _ok("training prompt", "prompts/company-intelligence-training.md"),
                _ok("approval gate", "scripts/company_brief_review.py"),
            ],
            ["Training mode remains owner-gated by design; do not automate prose approval."],
        ),
        _row(
            "training_owner_receipts",
            "Owner approval receipts are append-only and reconciled",
            [
                _ok("append-only approval receipts", "state/company_brief_receipts.json"),
                _check("receipt reconciliation checker", "scripts/check_training_receipt_reconciliation.py"),
            ],
            ["Owner-approved candidate receipts are required for future synthesized briefs."],
        ),
        _row(
            "ask_henneth_backend",
            "Ask Henneth backend contract exists",
            [
                _ok("owner-only Ask endpoint", "Henneth Desk 2.CI.0/api/ask.js"),
                _ok("server-owned Ask contract", "Henneth Desk 2.CI.0/api/ask_contract.js"),
                _check("Ask contract checker", "scripts/check_ask_henneth.mjs"),
            ],
            ["Release smoke test with provider env and owner JWT before deployed availability is complete."],
        ),
        _row(
            "ask_henneth_endpoint_security",
            "Ask Henneth endpoint security is checked",
            [
                _check("Ask endpoint checker", "scripts/check_ask_henneth_endpoint.mjs"),
                _check("root Ask hardening checker", "scripts/check_root_ask_hardening.mjs"),
                _ok("CI data middleware", "Henneth Desk 2.CI.0/middleware.js"),
            ],
            ["Live 401/403/200 owner-token smoke tests before release sign-off."],
        ),
        _row(
            "ask_henneth_ui",
            "Ask Henneth UI contract is checked",
            [
                _check("Ask UI checker", "scripts/check_ask_henneth_ui.mjs"),
                _contains("Ask UI markers", "Henneth Desk 2.CI.0/app.js", ("ask",)),
            ],
            ["Keep Ask UI display-only and owner-gated through the backend contract."],
        ),
        _row(
            "company_navigation_tabs",
            "Company navigation exposes the primary tab registry",
            [
                _contains("exact primary tab registry", "Henneth Desk 2.CI.0/app.js", PRIMARY_TABS),
                _state("slice rows for navigation", "Henneth Desk 2.CI.0/data/company_intelligence.json", len(ci_slice.get("tickers") or []) == len(pilot), f"{len(ci_slice.get('tickers') or [])} slice rows"),
            ],
            ["Future tabs must read emitted state and avoid browser-side business derivation."],
        ),
        _row(
            "company_navigation_checker",
            "Company navigation UI contract is checked",
            [
                _check("company navigation UI checker", "scripts/check_company_navigation_ui.mjs"),
                _contains("research tab marker", "Henneth Desk 2.CI.0/app.js", ("research",)),
            ],
            ["Run UI checker after tab or routing changes."],
        ),
        _row(
            "peer_registry_state",
            "Formal peer registry exists for every pilot company",
            [
                _state("peer registry", "state/company_intel/peer_registry.json", _exact_pilot(peer_registry, pilot), f"{_company_count(peer_registry)} company rows"),
                _check("peer registry checker", "scripts/check_peer_registry.py"),
            ],
            ["International peers remain non-authoritative unless sourced through a retained registry."],
        ),
        _row(
            "ownership_source_review_manifest",
            "Ownership source review manifest is retained and review-only",
            [
                _state(
                    "ownership manifest pilot boundary",
                    "config/ownership_source_review_manifest.json",
                    ownership_manifest.get("pilot_symbols") == pilot and set(ownership_manifest.get("companies") or {}) == set(pilot),
                    f"{len(ownership_manifest.get('companies') or {})} company rows",
                ),
                _state(
                    "review candidate manifest",
                    "config/ownership_source_review_manifest.json",
                    ownership_candidate_count > 0 and ownership_activated_count == 0,
                    f"{ownership_candidate_count} candidates; {ownership_activated_count} activated companies",
                ),
                _contains(
                    "review-only ownership policy",
                    "config/ownership_source_review_manifest.json",
                    ("no_ownership_activation", "no_inference_from_titles_toc_or_activity"),
                ),
                _check("ownership source manifest checker", "scripts/check_ownership_source_manifest.py"),
            ],
            ["Page-level extraction, required fields and owner approval before any ownership fact can be activated."],
        ),
        _row(
            "private_access_boundary",
            "Private access boundary protects CI data surfaces",
            [
                _ok("CI data middleware", "Henneth Desk 2.CI.0/middleware.js"),
                _ok("owner-only Ask endpoint", "Henneth Desk 2.CI.0/api/ask.js"),
                _check("generated URL safety checker", "scripts/check_generated_url_safety.py"),
            ],
            ["Live access smoke tests are still required before deployment sign-off."],
        ),
        _row(
            "root_state_publication_boundary",
            "Root publication boundary excludes CI artifacts and protected config",
            [
                _ok("root state publication boundary", "scripts/root_state_publication.py"),
                _check("root state publication checker", "scripts/check_root_state_publication.py"),
                _contains("root config serving guard", "scripts/serve.py", ("config/desk.json", "must never be served")),
            ],
            ["Never serve config/desk.json or secrets; keep publication scope checked."],
        ),
        _row(
            "ci_global_no_lookahead_gate",
            "Global CI no-lookahead gate exists",
            [
                _check("global CI no-lookahead checker", "scripts/check_ci_global_no_lookahead.py"),
                _contains("strict baseline check", "scripts/check_ci_global_no_lookahead.py", ("baseline.selected_date", "strictly before effective_date")),
            ],
            ["Run global no-lookahead lint before publishing new CI products."],
        ),
        _row(
            "completion_matrix_slice_summary",
            "Completion matrix summary is compact and embedded in the CI slice",
            [
                _ok("completion matrix builder", "scripts/build_ci_completion_matrix.py"),
                _check("completion matrix checker", "scripts/check_ci_completion_matrix.py"),
                _state("CI slice meta exists", "Henneth Desk 2.CI.0/data/company_intelligence.json", isinstance((ci_slice.get("meta") or {}).get("completion_matrix"), dict), "meta.completion_matrix present"),
            ],
            ["Builder/checker must be run whenever the completion registry changes."],
        ),
    ]

    if tuple(row["id"] for row in rows) != REQUIREMENT_IDS:
        raise AssertionError("completion matrix requirement registry drifted")

    payload = {
        "schema_version": 2,
        "as_of": (
            forecast_readiness.get("as_of")
            or profiles.get("updated")
            or "unknown"
        ),
        "scope": "Company Intelligence product completion audit",
        "source_policy": "retained repo/state evidence only; no fetching, model calls, SQL, publish, deploy, or source mutation",
        "pilot_symbols": pilot,
        "summary": _completion_summary(rows),
        "requirements": rows,
    }
    if write:
        save_json(OUT, payload)
        _sync_slice_summary(payload)
        print(f"ci_completion_matrix: {len(rows)} requirements -> {_rel(OUT)}")
    return payload


if __name__ == "__main__":
    build()
