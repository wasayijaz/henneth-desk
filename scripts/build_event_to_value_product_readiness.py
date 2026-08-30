"""Build the Event-to-Value Alpha product-readiness audit.

Read-only over retained CI artifacts. It does not fetch, qualify financials,
compute forecasts/valuations, or invent a passing production gate.
"""
from __future__ import annotations

from math import isfinite
from typing import Any

from psx_data import ROOT, STATE, load_json, save_json
from build_ci_artifact_integrity import artifact_paths, canonical_hash, rel

OUT = STATE / "company_intel" / "event_to_value_product_readiness.json"
PRODUCT_VERSION = "event_to_value_product_readiness_v1"
REQUIRED_GOLDEN_COUNT = 3
READINESS_REL = "state/company_intel/event_to_value_product_readiness.json"
ALPHA_DENOMINATORS = {
    "model_ready_companies": 3,
    "published_cases": 3,
    "financially_computed_scenarios": 9,
    "live_forecast_outputs": 3,
    "live_valuation_outputs": 3,
    "live_market_expectation_outputs": 3,
}
SOURCE_PATHS = {
    "intelligence_cases": "state/company_intel/intelligence_cases.json",
    "financial_truth_qualification": "state/company_intel/financial_truth_qualification.json",
    "forecast_readiness": "state/company_intel/forecast_readiness.json",
    "impact_scenarios": "state/company_intel/impact_scenarios.json",
    "financial_forecasts": "state/company_intel/financial_forecasts.json",
    "formal_valuations": "state/company_intel/formal_valuations.json",
    "market_expectations": "state/company_intel/market_expectations.json",
    "thesis_monitoring": "state/company_intel/thesis_monitoring.json",
    "artifact_integrity": "state/company_intel/artifact_integrity.json",
    "release_integrity_receipt": "state/company_intel/release_integrity_receipt.json",
}
COMPUTED_SCENARIO_STATUSES = {"computed", "modelled", "modeled"}
COMPUTED_ENGINE_STATUSES = {"computed"}
PROJECTED_STATUSES = {"available", "blocked", "unknown", "not_generated"}
SOURCE_TOP_LEVEL_STATUSES = {
    "available",
    "blocked",
    "degraded",
    "healthy",
    "ok",
    "partial",
    "unknown",
    "not_generated",
}
FORMAL_OUTPUT_KEYS = (
    "forecast",
    "valuation",
    "market_expectation",
    "market_expectations",
    "revenue",
    "revenue_cagr",
    "revenue_growth",
    "ebitda",
    "eps",
    "pat",
    "fcf",
    "fair_value",
    "fair_value_per_share",
    "target_price",
    "implied_price",
    "implied_pe",
    "current_price",
    "upside_pct",
    "downside_pct",
    "gap_pct",
)
RUN_LINEAGE_KEYS = {
    "run_id",
    "run_at",
    "generated_at",
    "build_cutoff_at",
    "source_commit_sha",
    "source_path",
    "artifact_path",
    "formula_id",
    "formula_version",
    "receipt_id",
    "provenance_id",
    "source_id",
    "source_url",
    "document_id",
    "fact_id",
    "content_sha256",
}
BLOCKED_SCENARIO_MARKERS = {
    "unmodeled_driver",
    "unmodelled_driver",
    "no_modeled_driver",
    "insufficient_data",
    "blocked",
    "not_generated",
    "unknown",
    "inferred",
}


def _load(rel: str, default: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
    path = ROOT / rel
    if not path.exists():
        return None, "not_generated"
    payload = load_json(path, default if default is not None else {})
    if not isinstance(payload, dict):
        return None, "blocked"
    return payload, "available"


def _as_of(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    meta = payload.get("_meta") if isinstance(payload.get("_meta"), dict) else {}
    for key in ("as_of", "generated_at", "build_cutoff_at", "recorded_at"):
        value = payload.get(key) or meta.get(key)
        if value:
            return str(value)
    return None


def _status_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _top_level_status(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return "not_generated"
    return _status_text(payload.get("status") or payload.get("schema_status") or "available")


def _source_status_ok(payload: dict[str, Any] | None) -> bool:
    status = _top_level_status(payload)
    return status in SOURCE_TOP_LEVEL_STATUSES and status not in {"blocked", "not_generated", "unknown"}


def _metric(
    metric_id: str,
    label: str,
    *,
    status: str,
    value: Any,
    denominator: Any,
    definition: str,
    source_path: str,
    as_of: str | None,
    reason: str | None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": metric_id,
        "label": label,
        "status": status,
        "value": value,
        "denominator": denominator,
        "display": None if value is None or denominator is None else f"{value}/{denominator}",
        "definition": definition,
        "source_path": source_path,
        "as_of": as_of,
        "reason": reason,
        "notes": notes or [],
    }


def derive_selected_symbols(cases: dict[str, Any] | None, cases_status: str) -> dict[str, Any]:
    source_path = SOURCE_PATHS["intelligence_cases"]
    if cases_status != "available" or cases is None:
        reason = "intelligence_cases_not_generated" if cases_status == "not_generated" else "intelligence_cases_blocked"
        return {"status": "not_generated" if cases_status == "not_generated" else "blocked", "symbols": [], "source_path": source_path, "reason": reason}
    if not _source_status_ok(cases):
        return {"status": "blocked", "symbols": [], "source_path": source_path, "reason": f"intelligence_cases_status_invalid:{_top_level_status(cases)}"}
    raw = cases.get("selected_symbols")
    if not isinstance(raw, list):
        return {"status": "blocked", "symbols": [], "source_path": source_path, "reason": "selected_symbols_missing"}
    companies = cases.get("companies")
    if not isinstance(companies, dict):
        return {"status": "blocked", "symbols": [], "source_path": source_path, "reason": "intelligence_cases_companies_invalid"}
    symbols: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            return {"status": "blocked", "symbols": [], "source_path": source_path, "reason": "selected_symbols_invalid"}
        symbol = item.strip().upper()
        if symbol in symbols:
            return {"status": "blocked", "symbols": [], "source_path": source_path, "reason": "selected_symbols_duplicate"}
        if symbol not in companies:
            return {"status": "blocked", "symbols": [], "source_path": source_path, "reason": f"selected_symbol_unknown:{symbol}"}
        symbols.append(symbol)
    if len(symbols) != REQUIRED_GOLDEN_COUNT:
        return {
            "status": "blocked",
            "symbols": symbols,
            "source_path": source_path,
            "reason": f"selected_symbols_not_exactly_three:count={len(symbols)}",
        }
    return {"status": "available", "symbols": symbols, "source_path": source_path, "reason": None}


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or value in (None, "", {}, []):
        return False
    if isinstance(value, dict):
        return _finite_number(value.get("value"))
    if isinstance(value, str):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return isfinite(number)


def _has_source_bound_lineage(value: Any) -> bool:
    if value in (None, "", [], {}):
        return False
    if isinstance(value, str):
        return False
    if isinstance(value, list):
        return any(_has_source_bound_lineage(item) for item in value)
    if not isinstance(value, dict):
        return False
    source = _status_text(value.get("source"))
    if source in {"inferred", "unknown", "model_guess", "estimated"}:
        return False
    if any(value.get(key) for key in RUN_LINEAGE_KEYS):
        return True
    return any(_has_source_bound_lineage(value.get(key)) for key in ("run", "receipt", "provenance", "lineage", "sources", "source_facts"))


def _has_any_finite_output(row: dict[str, Any]) -> bool:
    if any(_finite_number(row.get(key)) for key in ("revenue_impact", "ebitda_impact", "eps_impact", "fcf_impact", "valuation_impact")):
        return True
    result = row.get("result")
    if isinstance(result, dict):
        return any(_finite_number(result.get(key)) for key in FORMAL_OUTPUT_KEYS) or any(
            _finite_number(value) for value in result.values()
        )
    return False


def _integrity_status(integrity: dict[str, Any] | None) -> tuple[str | None, str, str | None, list[str], dict[str, Any]]:
    if not isinstance(integrity, dict):
        return None, "not_generated", "artifact_integrity_not_generated", [], {}
    artifacts_list = integrity.get("artifacts")
    if not isinstance(artifacts_list, list):
        return None, "blocked", "artifact_integrity_artifacts_invalid", [], {}
    hashed = [row for row in artifacts_list if isinstance(row, dict) and row.get("sha256") and row.get("path")]
    try:
        expected_paths = [rel(path) for path in artifact_paths()]
    except OSError as exc:
        return value, "blocked", f"artifact_integrity_expected_paths_unavailable:{exc.__class__.__name__}", [], {}
    manifest_paths = [str(row.get("path")) for row in hashed]
    missing = sorted(set(expected_paths) - set(manifest_paths))
    extra = sorted(set(manifest_paths) - set(expected_paths))
    notes = [f"artifact_count={len(artifacts_list)}", f"expected_artifact_count={len(expected_paths)}"]
    if missing:
        notes.append("missing=" + ",".join(missing[:5]))
    if extra:
        notes.append("extra=" + ",".join(extra[:5]))
    value = f"{len(hashed)}/{len(artifacts_list)}"
    details = {
        "expected_artifact_count": len(expected_paths),
        "manifest_artifact_count": len(artifacts_list),
        "missing_paths": missing,
        "extra_paths": extra,
        "covered": READINESS_REL in manifest_paths,
    }
    if len(artifacts_list) != len(expected_paths) or missing or extra:
        return value, "blocked", "artifact_integrity_manifest_paths_drifted", notes, details
    if len(hashed) != len(artifacts_list):
        return value, "blocked", "artifact_integrity_incomplete", notes, details
    if not details["covered"]:
        return value, "blocked", "event_to_value_product_readiness_not_in_artifact_integrity_manifest", notes, details
    if not integrity.get("source_commit_sha") or not integrity.get("build_cutoff_at") or not integrity.get("generated_at"):
        return value, "blocked", "artifact_integrity_lineage_missing", notes, details
    entry = next((row for row in hashed if row.get("path") == READINESS_REL), None)
    readiness_path = ROOT / READINESS_REL
    readiness = load_json(readiness_path, None) if readiness_path.exists() else None
    if not isinstance(readiness, dict):
        return value, "blocked", "event_to_value_product_readiness_not_generated", notes, details
    if entry.get("sha256") != canonical_hash(readiness):
        return value, "blocked", "event_to_value_product_readiness_hash_mismatch", notes, details
    notes = [str(integrity.get("source_commit_sha")), *notes, READINESS_REL]
    return value, "available", None, notes, details


def financial_impact_computed(scenario: dict[str, Any]) -> bool:
    if not isinstance(scenario, dict):
        return False
    status = str(scenario.get("impact_status") or scenario.get("status") or "").strip().lower()
    flags = {str(flag).strip().lower() for flag in (scenario.get("quality_flags") or []) if flag not in (None, "")}
    if status in BLOCKED_SCENARIO_MARKERS or flags.intersection(BLOCKED_SCENARIO_MARKERS):
        return False
    if status not in COMPUTED_SCENARIO_STATUSES:
        return False
    lineage = scenario.get("lineage") or scenario.get("provenance") or scenario.get("run") or scenario.get("receipt") or scenario.get("source")
    if not _has_source_bound_lineage(lineage):
        return False
    return _has_any_finite_output(scenario)


def _engine_live_count(payload: dict[str, Any] | None, load_status: str, selected: list[str]) -> tuple[int | None, str, str | None, list[str]]:
    if load_status != "available" or payload is None:
        return None, load_status, "source_artifact_not_generated" if load_status == "not_generated" else "source_artifact_blocked", []
    if not _source_status_ok(payload):
        return None, "blocked", f"source_artifact_status_invalid:{_top_level_status(payload)}", []
    computed = 0
    notes: list[str] = []
    companies = payload.get("companies") or {}
    if not isinstance(companies, dict):
        return None, "blocked", "source_artifact_companies_invalid", []
    for symbol in selected:
        row = companies.get(symbol)
        if (
            isinstance(row, dict)
            and _status_text(row.get("status")) in COMPUTED_ENGINE_STATUSES
            and isinstance(row.get("result"), dict)
            and row.get("result")
            and _has_any_finite_output(row)
            and _has_source_bound_lineage(row.get("provenance") or row.get("lineage") or row.get("run") or row.get("receipt") or row.get("_meta"))
        ):
            computed += 1
            notes.append(symbol)
    return computed, ("available" if computed else "blocked"), (None if computed else "no_live_computed_result_for_selected_symbols"), notes


def _null_required_outputs(
    forecasts: dict[str, Any] | None,
    valuations: dict[str, Any] | None,
    expectations: dict[str, Any] | None,
    selected: list[str],
) -> tuple[int, list[str]]:
    nulls = 0
    notes: list[str] = []
    for label, payload in (
        ("financial_forecasts", forecasts),
        ("formal_valuations", valuations),
        ("market_expectations", expectations),
    ):
        companies = (payload or {}).get("companies") or {}
        for symbol in selected:
            row = companies.get(symbol) if isinstance(companies, dict) else None
            if not isinstance(row, dict) or row.get("result") in (None, {}, []) or row.get("status") != "computed":
                nulls += 1
                notes.append(f"{label}:{symbol}:{(row or {}).get('reason') or (row or {}).get('status') or 'result_null'}")
    return nulls, notes


def project_readiness(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("kind") != "event_to_value_product_readiness":
        return {"status": "not_generated", "reason": "event_to_value_product_readiness_not_generated", "metrics": [], "summary": {}, "lineage": {}, "policy": {}, "product_version": None, "as_of": None}
    if payload.get("schema_version") != 1 or payload.get("product_version") != PRODUCT_VERSION:
        return {"status": "blocked", "reason": "event_to_value_product_readiness_schema_invalid", "metrics": [], "summary": {}, "lineage": {}, "policy": {}, "product_version": payload.get("product_version"), "as_of": payload.get("as_of")}
    payload_status = payload.get("status")
    if payload_status not in PROJECTED_STATUSES:
        return {"status": "blocked", "reason": f"event_to_value_product_readiness_status_invalid:{payload_status}", "metrics": [], "summary": {}, "lineage": {}, "policy": payload.get("policy") or {}, "product_version": payload.get("product_version"), "as_of": payload.get("as_of")}
    metrics = payload.get("metrics")
    lineage = payload.get("lineage") if isinstance(payload.get("lineage"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    selected = lineage.get("selected_symbols") or summary.get("selected_symbols")
    selected_status = lineage.get("selected_symbols_status") or summary.get("selected_symbols_status")
    if not isinstance(metrics, list) or len(metrics) != 12:
        return {"status": "blocked", "reason": "event_to_value_product_readiness_metrics_invalid", "metrics": [], "summary": summary, "lineage": lineage, "policy": payload.get("policy") or {}, "product_version": payload.get("product_version"), "as_of": payload.get("as_of")}
    metric_ids = [row.get("id") for row in metrics if isinstance(row, dict)]
    if len(metric_ids) != len(metrics) or len(set(metric_ids)) != len(metrics):
        return {"status": "blocked", "reason": "event_to_value_product_readiness_metric_ids_invalid", "metrics": [], "summary": summary, "lineage": lineage, "policy": payload.get("policy") or {}, "product_version": payload.get("product_version"), "as_of": payload.get("as_of")}
    for row in metrics:
        if row.get("status") not in PROJECTED_STATUSES:
            return {"status": "blocked", "reason": f"event_to_value_product_readiness_metric_status_invalid:{row.get('id')}", "metrics": [], "summary": summary, "lineage": lineage, "policy": payload.get("policy") or {}, "product_version": payload.get("product_version"), "as_of": payload.get("as_of")}
        if row.get("status") != "available" and not row.get("reason"):
            return {"status": "blocked", "reason": f"event_to_value_product_readiness_metric_reason_missing:{row.get('id')}", "metrics": [], "summary": summary, "lineage": lineage, "policy": payload.get("policy") or {}, "product_version": payload.get("product_version"), "as_of": payload.get("as_of")}
    if (
        selected_status != "available"
        or not isinstance(selected, list)
        or len(selected) != REQUIRED_GOLDEN_COUNT
        or any(not isinstance(symbol, str) or not symbol.strip() or symbol != symbol.strip().upper() for symbol in selected)
        or len(set(selected)) != REQUIRED_GOLDEN_COUNT
    ):
        return {
            "status": "blocked",
            "reason": lineage.get("selected_symbols_reason") or summary.get("selected_symbols_reason") or "selected_symbols_not_exactly_three",
            "metrics": metrics,
            "summary": summary,
            "lineage": lineage,
            "policy": payload.get("policy") or {},
            "product_version": payload.get("product_version"),
            "as_of": payload.get("as_of"),
        }
    if not lineage.get("source_commit_sha") or not lineage.get("build_cutoff_at") or not lineage.get("generated_at"):
        return {
            "status": "blocked",
            "reason": "event_to_value_product_readiness_lineage_missing",
            "metrics": metrics,
            "summary": summary,
            "lineage": lineage,
            "policy": payload.get("policy") or {},
            "product_version": payload.get("product_version"),
            "as_of": payload.get("as_of"),
        }
    provenance = next((row for row in metrics if isinstance(row, dict) and row.get("id") == "provenance_coverage"), {})
    if provenance.get("status") != "available":
        return {
            "status": "blocked",
            "reason": provenance.get("reason") or "event_to_value_product_readiness_integrity_unsealed",
            "metrics": metrics,
            "summary": summary,
            "lineage": lineage,
            "policy": payload.get("policy") or {},
            "product_version": payload.get("product_version"),
            "as_of": payload.get("as_of"),
        }
    available_count = summary.get("available_metric_count")
    if available_count == 0 and payload_status == "available":
        return {
            "status": "blocked",
            "reason": "event_to_value_product_readiness_all_metrics_blocked",
            "metrics": metrics,
            "summary": summary,
            "lineage": lineage,
            "policy": payload.get("policy") or {},
            "product_version": payload.get("product_version"),
            "as_of": payload.get("as_of"),
        }
    return {
        "status": payload_status,
        "reason": payload.get("reason"),
        "metrics": metrics,
        "summary": summary,
        "lineage": lineage,
        "policy": payload.get("policy") or {},
        "product_version": payload.get("product_version"),
        "as_of": payload.get("as_of"),
    }


def build(write: bool = True, artifacts: dict[str, tuple[dict[str, Any] | None, str]] | None = None) -> dict[str, Any]:
    loaded = artifacts or {}

    def take(name: str) -> tuple[dict[str, Any] | None, str]:
        if name in loaded:
            return loaded[name]
        return _load(SOURCE_PATHS[name])

    truth, truth_status = take("financial_truth_qualification")
    forecast_readiness, forecast_ready_status = take("forecast_readiness")
    cases, cases_status = take("intelligence_cases")
    scenarios, scenarios_status = take("impact_scenarios")
    forecasts, forecasts_status = take("financial_forecasts")
    valuations, valuations_status = take("formal_valuations")
    expectations, expectations_status = take("market_expectations")
    theses, theses_status = take("thesis_monitoring")
    integrity, integrity_status = take("artifact_integrity")
    receipt, receipt_status = take("release_integrity_receipt")

    selection = derive_selected_symbols(cases, cases_status)
    selected = selection["symbols"] if selection["status"] == "available" else []
    selected_ready = selection["status"] == "available"

    def blocked_selection() -> tuple[None, str, str, list[str]]:
        return None, "blocked", selection["reason"], [f"selected_symbols={selection['symbols']}"]

    if selected_ready and truth_status == "available" and truth is not None:
        qualified = [
            symbol
            for symbol in selected
            if isinstance((truth.get("companies") or {}).get(symbol), dict)
            and (truth.get("companies") or {}).get(symbol, {}).get("status") == "qualified"
        ]
        model_ready_value, model_ready_notes = len(qualified), qualified
        model_ready_status = "available" if qualified else "blocked"
        model_ready_reason = None if qualified else "no_selected_company_has_qualified_financial_truth"
    elif selected_ready:
        model_ready_value, model_ready_status, model_ready_reason, model_ready_notes = (
            None,
            truth_status,
            "financial_truth_qualification_not_generated" if truth_status == "not_generated" else "financial_truth_qualification_blocked",
            [],
        )
    else:
        model_ready_value, model_ready_status, model_ready_reason, model_ready_notes = blocked_selection()

    if selected_ready and cases_status == "available" and cases is not None:
        published: list[str] = []
        observed: list[str] = []
        for symbol in selected:
            row = (cases.get("companies") or {}).get(symbol) or {}
            for case in row.get("cases") or []:
                if not isinstance(case, dict):
                    continue
                identity = f"{case.get('symbol')}:{case.get('case_id')}:{case.get('status')}"
                if case.get("status") == "Published":
                    published.append(identity)
                elif case.get("status"):
                    observed.append(identity)
        published_value = len(published)
        published_notes = published or observed
        published_status = "available" if published else "blocked"
        published_reason = None if published else ("observed_cases_exist_but_none_are_published" if observed else "no_published_intelligence_case")
    elif selected_ready:
        published_value, published_status, published_reason, published_notes = (
            None,
            cases_status,
            "intelligence_cases_not_generated" if cases_status == "not_generated" else "intelligence_cases_blocked",
            [],
        )
    else:
        published_value, published_status, published_reason, published_notes = blocked_selection()

    if selected_ready and scenarios_status == "available" and scenarios is not None:
        computed_scenarios = 0
        scenario_notes: list[str] = []
        for symbol in selected:
            row = (scenarios.get("companies") or {}).get(symbol) or {}
            for scenario in row.get("scenarios") or []:
                if financial_impact_computed(scenario):
                    computed_scenarios += 1
                    scenario_notes.append(str(scenario.get("scenario_id") or scenario.get("event_id")))
        scenario_value = computed_scenarios
        scenario_status = "available" if computed_scenarios else "blocked"
        scenario_reason = None if computed_scenarios else "no_financially_computed_scenario_impacts_for_selected_symbols"
    elif selected_ready:
        scenario_value, scenario_status, scenario_reason, scenario_notes = (
            None,
            scenarios_status,
            "impact_scenarios_not_generated" if scenarios_status == "not_generated" else "impact_scenarios_blocked",
            [],
        )
    else:
        scenario_value, scenario_status, scenario_reason, scenario_notes = blocked_selection()

    if selected_ready:
        forecast_count, forecast_status, forecast_reason, forecast_notes = _engine_live_count(forecasts, forecasts_status, selected)
        valuation_count, valuation_status, valuation_reason, valuation_notes = _engine_live_count(valuations, valuations_status, selected)
        expectation_count, expectation_status, expectation_reason, expectation_notes = _engine_live_count(expectations, expectations_status, selected)
    else:
        forecast_count, forecast_status, forecast_reason, forecast_notes = blocked_selection()
        valuation_count, valuation_status, valuation_reason, valuation_notes = blocked_selection()
        expectation_count, expectation_status, expectation_reason, expectation_notes = blocked_selection()

    ask_status = "blocked"
    ask_reason = "ask_henneth_live_runtime_not_recorded_in_authoritative_ci_state"
    ask_notes = ["Focused contract checkers exist at scripts/check_ask_henneth.mjs, but they are not a live production Ask receipt."]

    if selected_ready and theses_status == "available" and theses is not None:
        active_cases = 0
        thesis_notes: list[str] = []
        for symbol in selected:
            row = (theses.get("companies") or {}).get(symbol) or {}
            count = row.get("active_thesis_count")
            if isinstance(count, int):
                active_cases += count
            if row.get("status") == "active_monitoring":
                thesis_notes.append(f"{symbol}:{count}")
        thesis_value = active_cases
        thesis_status = "available"
        thesis_reason = None if active_cases else "no_active_thesis_monitoring_cases_for_selected_symbols"
    elif selected_ready:
        thesis_value, thesis_status, thesis_reason, thesis_notes = (
            None,
            theses_status,
            "thesis_monitoring_not_generated" if theses_status == "not_generated" else "thesis_monitoring_blocked",
            [],
        )
    else:
        thesis_value, thesis_status, thesis_reason, thesis_notes = blocked_selection()

    if selected_ready and forecasts_status == "available" and valuations_status == "available" and expectations_status == "available":
        nulls_value, nulls_notes = _null_required_outputs(forecasts, valuations, expectations, selected)
        nulls_status, nulls_reason = "available", None
    elif selected_ready:
        nulls_value, nulls_status, nulls_reason, nulls_notes = None, "blocked", "required_output_artifacts_not_all_available", []
    else:
        nulls_value, nulls_status, nulls_reason, nulls_notes = blocked_selection()

    if integrity_status == "available" and integrity is not None:
        provenance_value, provenance_status, provenance_reason, provenance_notes, integrity_details = _integrity_status(integrity)
    else:
        integrity_details = {}
        provenance_value, provenance_status, provenance_reason = (
            None,
            integrity_status,
            "artifact_integrity_not_generated" if integrity_status == "not_generated" else "artifact_integrity_blocked",
        )

    lookahead_status = "blocked"
    lookahead_reason = "no_lookahead_pass_is_not_stored_as_authoritative_state; scripts/check_ci_global_no_lookahead.py must be run to prove the current tree"
    lookahead_notes = ["Checker exists. This audit does not treat a missing stored receipt as a pass."]

    if receipt_status != "available" or receipt is None:
        production_status = receipt_status
        production_reason = "release_integrity_receipt_not_generated" if receipt_status == "not_generated" else "release_integrity_receipt_blocked"
        production_notes: list[str] = []
        production_value = None
    else:
        evidence = receipt.get("required_evidence") or {}
        missing = [key for key, row in evidence.items() if not isinstance(row, dict) or row.get("status") != "pass"]
        production_notes = [f"{key}:{(evidence.get(key) or {}).get('status')}" for key in evidence]
        production_value = receipt.get("release_status")
        if receipt.get("release_status") == "verified" and not missing:
            production_status, production_reason = "available", None
        else:
            production_status = "blocked"
            production_reason = str(receipt.get("release_status") or "not_verified")
            if missing:
                production_reason = f"{production_reason}:missing_evidence={','.join(missing)}"

    lineage = {
        "product_version": PRODUCT_VERSION,
        "generated_at": (integrity or {}).get("generated_at") if integrity_status == "available" else _as_of(receipt) or _as_of(cases) or _as_of(truth),
        "source_as_of": {
            "intelligence_cases": _as_of(cases),
            "financial_truth_qualification": _as_of(truth),
            "forecast_readiness": _as_of(forecast_readiness),
            "impact_scenarios": _as_of(scenarios),
            "financial_forecasts": _as_of(forecasts),
            "formal_valuations": _as_of(valuations),
            "market_expectations": _as_of(expectations),
            "thesis_monitoring": _as_of(theses),
            "artifact_integrity": _as_of(integrity),
            "release_integrity_receipt": _as_of(receipt),
        },
        "source_commit_sha": (integrity or {}).get("source_commit_sha") if integrity_status == "available" else None,
        "build_cutoff_at": (integrity or {}).get("build_cutoff_at") if integrity_status == "available" else None,
        "artifact_integrity_status": provenance_status,
        "artifact_integrity_reason": provenance_reason,
        "artifact_integrity": integrity_details,
        "selected_symbols": selected,
        "selected_symbols_source_path": selection["source_path"],
        "selected_symbols_status": selection["status"],
        "selected_symbols_reason": selection["reason"],
    }

    metrics = [
        _metric("model_ready_companies", "Model-ready companies", status=model_ready_status, value=model_ready_value, denominator=ALPHA_DENOMINATORS["model_ready_companies"], definition="Count of selected golden-case companies whose financial_truth_qualification.status is qualified. Unselected companies and forecast-readiness input_ready do not count.", source_path=SOURCE_PATHS["financial_truth_qualification"], as_of=_as_of(truth), reason=model_ready_reason, notes=model_ready_notes),
        _metric("published_cases", "Published Intelligence Cases", status=published_status, value=published_value, denominator=ALPHA_DENOMINATORS["published_cases"], definition="Count of Published intelligence_cases on the selected golden-case symbols only.", source_path=SOURCE_PATHS["intelligence_cases"], as_of=_as_of(cases), reason=published_reason, notes=published_notes),
        _metric("financially_computed_scenarios", "Financially computed scenarios", status=scenario_status, value=scenario_value, denominator=ALPHA_DENOMINATORS["financially_computed_scenarios"], definition="Count of selected-symbol impact_scenarios with explicit computed/modelled status, a finite numeric impact, and source/lineage. unmodeled_driver and blocked/not_generated/inferred rows do not count even if a number is present.", source_path=SOURCE_PATHS["impact_scenarios"], as_of=_as_of(scenarios), reason=scenario_reason, notes=scenario_notes),
        _metric("live_forecast_outputs", "Live forecast outputs", status=forecast_status, value=forecast_count, denominator=ALPHA_DENOMINATORS["live_forecast_outputs"], definition="Count of selected-symbol financial_forecasts rows with status computed and a non-null result.", source_path=SOURCE_PATHS["financial_forecasts"], as_of=_as_of(forecasts), reason=forecast_reason, notes=forecast_notes),
        _metric("live_valuation_outputs", "Live valuation outputs", status=valuation_status, value=valuation_count, denominator=ALPHA_DENOMINATORS["live_valuation_outputs"], definition="Count of selected-symbol formal_valuations rows with status computed and a non-null result.", source_path=SOURCE_PATHS["formal_valuations"], as_of=_as_of(valuations), reason=valuation_reason, notes=valuation_notes),
        _metric("live_market_expectation_outputs", "Live market-expectation outputs", status=expectation_status, value=expectation_count, denominator=ALPHA_DENOMINATORS["live_market_expectation_outputs"], definition="Count of selected-symbol market_expectations rows with status computed and a non-null result.", source_path=SOURCE_PATHS["market_expectations"], as_of=_as_of(expectations), reason=expectation_reason, notes=expectation_notes),
        _metric("ask_henneth_test_status", "Ask Henneth test status", status=ask_status, value=None, denominator=None, definition="Live Ask runtime proof must be a stored receipt. Local contract checkers are not treated as a production pass.", source_path="scripts/check_ask_henneth.mjs", as_of=None, reason=ask_reason, notes=ask_notes),
        _metric("active_thesis_monitoring_cases", "Active thesis-monitoring cases", status=thesis_status, value=thesis_value, denominator=None, definition="Sum of thesis_monitoring.active_thesis_count across the selected golden-case symbols only.", source_path=SOURCE_PATHS["thesis_monitoring"], as_of=_as_of(theses), reason=thesis_reason, notes=thesis_notes),
        _metric("required_output_nulls", "Required-output nulls", status=nulls_status, value=nulls_value, denominator=None, definition="Count of selected-symbol forecast, valuation, and market-expectation rows whose result is null or not computed.", source_path="state/company_intel/financial_forecasts.json", as_of=_as_of(forecasts), reason=nulls_reason, notes=nulls_notes),
        _metric("provenance_coverage", "Provenance coverage", status=provenance_status, value=provenance_value, denominator=None, definition="Hashed artifact_integrity rows versus artifact_count. The generated readiness artifact itself must be covered by the sealed manifest.", source_path=SOURCE_PATHS["artifact_integrity"], as_of=_as_of(integrity), reason=provenance_reason, notes=provenance_notes),
        _metric("no_lookahead_status", "No-lookahead status", status=lookahead_status, value=None, denominator=None, definition="No stored no-lookahead receipt exists. A pass requires scripts/check_ci_global_no_lookahead.py against the current tree.", source_path="scripts/check_ci_global_no_lookahead.py", as_of=None, reason=lookahead_reason, notes=lookahead_notes),
        _metric("production_gate_status", "Production gate status", status=production_status, value=production_value, denominator=None, definition="Release is verified only when release_integrity_receipt.release_status is verified and every required_evidence row is pass for one commit.", source_path=SOURCE_PATHS["release_integrity_receipt"], as_of=_as_of(receipt), reason=production_reason, notes=production_notes),
    ]

    blocked = [row["id"] for row in metrics if row["status"] != "available"]
    available_count = len(metrics) - len(blocked)
    top_status = "blocked" if not selected_ready or available_count == 0 or provenance_status != "available" else "available"
    top_reason = (
        selection["reason"]
        if not selected_ready
        else provenance_reason
        if provenance_status != "available"
        else "event_to_value_product_readiness_all_metrics_blocked"
        if available_count == 0
        else None
    )
    result = {
        "schema_version": 1,
        "product_version": PRODUCT_VERSION,
        "kind": "event_to_value_product_readiness",
        "as_of": lineage["generated_at"],
        "status": top_status,
        "reason": top_reason,
        "policy": {
            "research_only": True,
            "read_only_audit": True,
            "no_inferred_success": True,
            "no_advice": True,
            "distinct_from_intelligence_case_ui": True,
            "selected_golden_cases_only": True,
        },
        "source_paths": SOURCE_PATHS,
        "lineage": lineage,
        "summary": {
            "metric_count": len(metrics),
            "available_metric_count": available_count,
            "blocked_metric_count": len(blocked),
            "blocked_metric_ids": blocked,
            "alpha_denominators": ALPHA_DENOMINATORS,
            "selected_symbols": selected,
            "selected_symbols_status": selection["status"],
            "selected_symbols_reason": selection["reason"],
            "selected_symbols_source_path": selection["source_path"],
            "forecast_readiness_input_ready_count": ((forecast_readiness or {}).get("summary") or {}).get("ready_company_count") if forecast_ready_status == "available" else None,
            "forecast_readiness_is_not_model_ready": True,
        },
        "metrics": metrics,
    }
    if write:
        save_json(OUT, result)
        print(
            "event_to_value_product_readiness: "
            f"{result['summary']['available_metric_count']}/{result['summary']['metric_count']} available "
            f"selected={selected or selection['reason']}"
        )
    return result


if __name__ == "__main__":
    build()
