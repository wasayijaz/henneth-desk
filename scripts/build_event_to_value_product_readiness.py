"""Build the Event-to-Value Alpha product-readiness audit.

Read-only over retained CI artifacts. It does not fetch, qualify financials,
compute forecasts/valuations, or invent a passing production gate.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any

from psx_data import ROOT, STATE, load_json, save_json
from build_ci_artifact_integrity import artifact_paths, canonical_hash, rel

OUT = STATE / "company_intel" / "event_to_value_product_readiness.json"
PRODUCT_VERSION = "event_to_value_product_readiness_v1"
REQUIRED_GOLDEN_COUNT = 3
READINESS_REL = "state/company_intel/event_to_value_product_readiness.json"
REQUIRED_METRIC_IDS = (
    "model_ready_companies",
    "published_cases",
    "financially_computed_scenarios",
    "live_forecast_outputs",
    "live_valuation_outputs",
    "live_market_expectation_outputs",
    "ask_henneth_test_status",
    "active_thesis_monitoring_cases",
    "required_output_nulls",
    "provenance_coverage",
    "no_lookahead_status",
    "production_gate_status",
)
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
SOURCE_SCHEMA_VERSIONS = {
    "intelligence_cases": 1,
    # v2 is the current retained financial-truth contract; v1 remains
    # readable for deterministic historical fixtures.
    "financial_truth_qualification": ("financial_truth_qualification_v1", "financial_truth_qualification_v2"),
    "forecast_readiness": 1,
    "impact_scenarios": 1,
    "financial_forecasts": 1,
    "formal_valuations": 1,
    "market_expectations": 1,
    "thesis_monitoring": 1,
    "artifact_integrity": 1,
    "release_integrity_receipt": 1,
}
SOURCE_KINDS = {
    "intelligence_cases": None,
    "financial_truth_qualification": None,
    "forecast_readiness": None,
    "impact_scenarios": None,
    "financial_forecasts": "financial_forecasts",
    "formal_valuations": "formal_valuations",
    "market_expectations": "market_expectations",
    "thesis_monitoring": None,
    "artifact_integrity": "ci_artifact_integrity_manifest",
    "release_integrity_receipt": "ci_release_integrity_receipt",
}
SOURCE_REQUIRED_KEYS = {
    "intelligence_cases": ("case_product_version", "as_of", "pilot_symbols", "selected_symbols", "status_lifecycle", "policy", "summary", "companies"),
    "financial_truth_qualification": ("pilot_symbols", "source", "policy", "selection", "companies", "summary"),
    "forecast_readiness": ("contract_version", "as_of", "pilot_symbols", "registry_versions", "adapter_versions", "adapter_source_owners", "policies", "source", "summary", "companies"),
    "impact_scenarios": ("pilot_symbols", "companies", "scenario_probabilities", "_meta"),
    "financial_forecasts": ("engine_version", "kind", "as_of", "pilot_symbols", "formula_id", "source", "policy", "summary", "companies"),
    "formal_valuations": ("engine_version", "kind", "as_of", "pilot_symbols", "formula_id", "source", "policy", "summary", "companies"),
    "market_expectations": ("engine_version", "kind", "as_of", "pilot_symbols", "formula_id", "source", "policy", "summary", "companies"),
    "thesis_monitoring": ("as_of", "pilot_symbols", "source", "policy", "companies"),
    "artifact_integrity": ("kind", "source_commit_sha", "build_cutoff_at", "generated_at", "artifact_count", "artifacts", "policy"),
    "release_integrity_receipt": ("kind", "release_commit_sha", "release_status", "recorded_at", "required_evidence"),
}
COMPUTED_SCENARIO_STATUSES = {"computed", "modelled", "modeled"}
COMPUTED_ENGINE_STATUSES = {"computed"}
PROJECTED_STATUSES = {"available", "blocked", "unknown", "not_generated"}
SOURCE_HEALTHY_STATUSES = {
    "available",
    "healthy",
    "ok",
}
ENGINE_OUTPUT_KEYS = {
    "financial_forecasts": {
        "forecast_revenue",
        "forecast_profit_after_tax_attributable",
        "forecast_basic_eps",
    },
    "formal_valuations": {
        "formula_value_per_share",
        "formula_equity_value",
        "formula_enterprise_value",
        "net_debt",
    },
    "market_expectations": {
        "required_revenue",
        "required_profit_after_tax_attributable",
        "required_basic_eps",
        "required_revenue_growth_pct",
        "assumed_revenue_growth_pct",
        "expectations_gap_pct",
    },
}
IMPACT_OUTPUT_KEYS = ("revenue_impact", "ebitda_impact", "eps_impact", "fcf_impact", "valuation_impact")
SOURCE_BOUND_LINEAGE_KEYS = {
    "source_path",
    "artifact_path",
}
RUN_RECEIPT_LINEAGE_KEYS = {
    "run_id",
    "run_at",
    "generated_at",
    "build_cutoff_at",
    "source_commit_sha",
    "formula_id",
    "formula_version",
    "receipt_id",
    "provenance_id",
}
COUNT_VALUE_METRIC_IDS = set(ALPHA_DENOMINATORS) | {"active_thesis_monitoring_cases", "required_output_nulls"}
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
ISO_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?)?$"
)


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


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if not ISO_TIMESTAMP_RE.fullmatch(text):
        return None
    try:
        if text.endswith("Z"):
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        else:
            parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=5)))
    return parsed.astimezone(timezone.utc)


def _after_cutoff(value: Any, cutoff: Any) -> bool:
    parsed_value = _parse_time(value)
    parsed_cutoff = _parse_time(cutoff)
    return bool(parsed_value and parsed_cutoff and parsed_value > parsed_cutoff)


def _timestamp_reason(label: str, value: Any, *, required: bool = False) -> str | None:
    if value is None:
        return f"{label}_missing" if required else None
    if not isinstance(value, str) or not value.strip():
        return f"{label}_invalid"
    if _parse_time(value) is None:
        return f"{label}_invalid"
    return None


def _dict_required(value: Any) -> bool:
    return isinstance(value, dict)


def _list_required(value: Any) -> bool:
    return isinstance(value, list)


def _source_contract_reason(name: str, payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return f"{name}_not_generated"
    expected_schema = SOURCE_SCHEMA_VERSIONS.get(name)
    if payload.get("schema_version") != expected_schema and not (
        isinstance(expected_schema, tuple) and payload.get("schema_version") in expected_schema
    ):
        return f"{name}_schema_version_invalid"
    for key in SOURCE_REQUIRED_KEYS.get(name, ()):
        if key not in payload:
            return f"{name}_{key}_missing"
    expected_kind = SOURCE_KINDS.get(name)
    if expected_kind is not None:
        if not isinstance(payload.get("kind"), str) or not payload.get("kind"):
            return f"{name}_kind_missing"
        if payload.get("kind") != expected_kind:
            return f"{name}_kind_invalid:{payload.get('kind')}"
    elif "kind" in payload and payload.get("kind") not in (None, "", name):
        return f"{name}_kind_invalid:{payload.get('kind')}"
    if "status" in payload:
        if not isinstance(payload.get("status"), str) or not payload.get("status").strip():
            return f"{name}_status_invalid:{payload.get('status')!r}"
        status = _status_text(payload.get("status"))
        if status not in SOURCE_HEALTHY_STATUSES:
            return f"{name}_status_not_healthy:{status or 'missing'}"
    freshness = _as_of(payload)
    freshness_reason = _timestamp_reason(f"{name}_as_of", freshness, required=True)
    if freshness_reason:
        return freshness_reason
    if name in {"intelligence_cases", "forecast_readiness", "impact_scenarios", "financial_forecasts", "formal_valuations", "market_expectations", "thesis_monitoring"}:
        if not _list_required(payload.get("pilot_symbols")):
            return f"{name}_pilot_symbols_invalid"
    if name in {"intelligence_cases", "financial_truth_qualification", "forecast_readiness", "impact_scenarios", "financial_forecasts", "formal_valuations", "market_expectations", "thesis_monitoring"}:
        if not _dict_required(payload.get("companies")):
            return f"{name}_companies_invalid"
    if name in {"intelligence_cases", "financial_truth_qualification", "forecast_readiness", "financial_forecasts", "formal_valuations", "market_expectations"}:
        if not _dict_required(payload.get("summary")):
            return f"{name}_summary_invalid"
    if name in {"financial_forecasts", "formal_valuations", "market_expectations"} and not isinstance(payload.get("formula_id"), str):
        return f"{name}_formula_id_invalid"
    if name == "release_integrity_receipt":
        if payload.get("release_status") != "verified":
            return f"{name}_release_status_not_verified:{payload.get('release_status') or 'missing'}"
        evidence = payload.get("required_evidence")
        if not isinstance(evidence, dict) or any(not isinstance(row, dict) or row.get("status") != "pass" for row in evidence.values()):
            return f"{name}_required_evidence_not_pass"
    return None


def _source_reason_for_load(name: str, payload: dict[str, Any] | None, load_status: str) -> str | None:
    if load_status != "available":
        return f"{name}_not_generated" if load_status == "not_generated" else f"{name}_blocked"
    return _source_contract_reason(name, payload)


def _source_status(reason: str | None) -> str:
    return "available" if reason is None else "blocked"


def _source_maps_from(
    *,
    cases: dict[str, Any] | None,
    cases_status: str,
    truth: dict[str, Any] | None,
    truth_status: str,
    forecast_readiness: dict[str, Any] | None,
    forecast_ready_status: str,
    scenarios: dict[str, Any] | None,
    scenarios_status: str,
    forecasts: dict[str, Any] | None,
    forecasts_status: str,
    valuations: dict[str, Any] | None,
    valuations_status: str,
    expectations: dict[str, Any] | None,
    expectations_status: str,
    theses: dict[str, Any] | None,
    theses_status: str,
    integrity: dict[str, Any] | None,
    integrity_status: str,
    receipt: dict[str, Any] | None,
    receipt_status: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str], dict[str, str | None], dict[str, str | None]]:
    selection = derive_selected_symbols(cases, cases_status)
    contract_sources = {
        "financial_truth_qualification": (truth, truth_status),
        "forecast_readiness": (forecast_readiness, forecast_ready_status),
        "impact_scenarios": (scenarios, scenarios_status),
        "financial_forecasts": (forecasts, forecasts_status),
        "formal_valuations": (valuations, valuations_status),
        "market_expectations": (expectations, expectations_status),
        "thesis_monitoring": (theses, theses_status),
        "release_integrity_receipt": (receipt, receipt_status),
    }
    source_reasons = {
        name: _source_reason_for_load(name, payload, status)
        for name, (payload, status) in contract_sources.items()
    }
    if integrity_status == "available" and integrity is not None:
        _, provenance_status, provenance_reason, _, _ = _integrity_status(integrity)
    else:
        provenance_status = "not_generated" if integrity_status == "not_generated" else "blocked"
        provenance_reason = "artifact_integrity_not_generated" if integrity_status == "not_generated" else "artifact_integrity_blocked"
    payloads = {
        "intelligence_cases": cases,
        "financial_truth_qualification": truth,
        "forecast_readiness": forecast_readiness,
        "impact_scenarios": scenarios,
        "financial_forecasts": forecasts,
        "formal_valuations": valuations,
        "market_expectations": expectations,
        "thesis_monitoring": theses,
        "artifact_integrity": integrity,
        "release_integrity_receipt": receipt,
    }
    load_statuses = {
        "intelligence_cases": cases_status,
        "financial_truth_qualification": truth_status,
        "forecast_readiness": forecast_ready_status,
        "impact_scenarios": scenarios_status,
        "financial_forecasts": forecasts_status,
        "formal_valuations": valuations_status,
        "market_expectations": expectations_status,
        "thesis_monitoring": theses_status,
        "artifact_integrity": integrity_status,
        "release_integrity_receipt": receipt_status,
    }
    source_as_of = {name: _as_of(payloads[name]) for name in SOURCE_PATHS}
    source_schema_version = {
        name: (payloads[name] or {}).get("schema_version") if load_statuses[name] == "available" else None
        for name in SOURCE_PATHS
    }
    source_kind = {
        name: (payloads[name] or {}).get("kind") if load_statuses[name] == "available" else None
        for name in SOURCE_PATHS
    }
    source_status = {
        "intelligence_cases": selection["status"],
        "financial_truth_qualification": _source_status(source_reasons["financial_truth_qualification"]),
        "forecast_readiness": _source_status(source_reasons["forecast_readiness"]),
        "impact_scenarios": _source_status(source_reasons["impact_scenarios"]),
        "financial_forecasts": _source_status(source_reasons["financial_forecasts"]),
        "formal_valuations": _source_status(source_reasons["formal_valuations"]),
        "market_expectations": _source_status(source_reasons["market_expectations"]),
        "thesis_monitoring": _source_status(source_reasons["thesis_monitoring"]),
        "artifact_integrity": provenance_status,
        "release_integrity_receipt": _source_status(source_reasons["release_integrity_receipt"]),
    }
    source_reason = {
        "intelligence_cases": selection["reason"],
        "financial_truth_qualification": source_reasons["financial_truth_qualification"],
        "forecast_readiness": source_reasons["forecast_readiness"],
        "impact_scenarios": source_reasons["impact_scenarios"],
        "financial_forecasts": source_reasons["financial_forecasts"],
        "formal_valuations": source_reasons["formal_valuations"],
        "market_expectations": source_reasons["market_expectations"],
        "thesis_monitoring": source_reasons["thesis_monitoring"],
        "artifact_integrity": provenance_reason,
        "release_integrity_receipt": source_reasons["release_integrity_receipt"],
    }
    return source_as_of, source_schema_version, source_kind, source_status, source_reason


def _current_source_maps() -> tuple[dict[str, Any], dict[str, Any], dict[str, str], dict[str, str | None], dict[str, str | None]]:
    loaded = {name: _load(path) for name, path in SOURCE_PATHS.items()}
    return _source_maps_from(
        cases=loaded["intelligence_cases"][0],
        cases_status=loaded["intelligence_cases"][1],
        truth=loaded["financial_truth_qualification"][0],
        truth_status=loaded["financial_truth_qualification"][1],
        forecast_readiness=loaded["forecast_readiness"][0],
        forecast_ready_status=loaded["forecast_readiness"][1],
        scenarios=loaded["impact_scenarios"][0],
        scenarios_status=loaded["impact_scenarios"][1],
        forecasts=loaded["financial_forecasts"][0],
        forecasts_status=loaded["financial_forecasts"][1],
        valuations=loaded["formal_valuations"][0],
        valuations_status=loaded["formal_valuations"][1],
        expectations=loaded["market_expectations"][0],
        expectations_status=loaded["market_expectations"][1],
        theses=loaded["thesis_monitoring"][0],
        theses_status=loaded["thesis_monitoring"][1],
        integrity=loaded["artifact_integrity"][0],
        integrity_status=loaded["artifact_integrity"][1],
        receipt=loaded["release_integrity_receipt"][0],
        receipt_status=loaded["release_integrity_receipt"][1],
    )


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
        "lineage": {
            "source_path": source_path,
            "as_of": as_of,
            "status": status,
            "reason": reason,
        },
    }


def derive_selected_symbols(cases: dict[str, Any] | None, cases_status: str) -> dict[str, Any]:
    source_path = SOURCE_PATHS["intelligence_cases"]
    if cases_status != "available" or cases is None:
        reason = "intelligence_cases_not_generated" if cases_status == "not_generated" else "intelligence_cases_blocked"
        return {"status": "not_generated" if cases_status == "not_generated" else "blocked", "symbols": [], "source_path": source_path, "reason": reason}
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


def _lineage_flags(value: Any, expected_source_path: str) -> tuple[bool, bool]:
    if value in (None, "", [], {}):
        return False, False
    if isinstance(value, str):
        return False, False
    if isinstance(value, list):
        source_bound = False
        run_bound = False
        for item in value:
            item_source_bound, item_run_bound = _lineage_flags(item, expected_source_path)
            source_bound = source_bound or item_source_bound
            run_bound = run_bound or item_run_bound
        return source_bound, run_bound
    if not isinstance(value, dict):
        return False, False
    source = _status_text(value.get("source"))
    if source in {"inferred", "unknown", "model_guess", "estimated"}:
        return False, False
    source_bound = any(value.get(key) == expected_source_path for key in SOURCE_BOUND_LINEAGE_KEYS)
    run_bound = any(value.get(key) for key in RUN_RECEIPT_LINEAGE_KEYS)
    for key in ("run", "receipt", "provenance", "lineage", "sources", "source_facts"):
        nested_source_bound, nested_run_bound = _lineage_flags(value.get(key), expected_source_path)
        source_bound = source_bound or nested_source_bound
        run_bound = run_bound or nested_run_bound
    return source_bound, run_bound


def _has_source_bound_lineage(value: Any, expected_source_path: str) -> bool:
    source_bound, run_bound = _lineage_flags(value, expected_source_path)
    return source_bound and run_bound


def _has_finite_impact_output(row: dict[str, Any]) -> bool:
    return all(_finite_number(row.get(key)) for key in IMPACT_OUTPUT_KEYS)


def _has_complete_impact_contract(row: dict[str, Any]) -> bool:
    return (
        isinstance(row.get("scenario_id"), str)
        and bool(row.get("scenario_id"))
        and isinstance(row.get("event_id"), str)
        and bool(row.get("event_id"))
        and isinstance(row.get("company_id"), str)
        and bool(row.get("company_id"))
        and _has_finite_impact_output(row)
    )


def _has_finite_engine_output(row: dict[str, Any], engine_name: str) -> bool:
    result = row.get("result")
    if not isinstance(result, dict):
        return False
    allowed = ENGINE_OUTPUT_KEYS.get(engine_name)
    if not allowed:
        return False
    if set(result) != allowed:
        return False
    return all(_finite_number(result.get(key)) for key in allowed)


def _integrity_status(integrity: dict[str, Any] | None) -> tuple[str | None, str, str | None, list[str], dict[str, Any]]:
    if not isinstance(integrity, dict):
        return None, "not_generated", "artifact_integrity_not_generated", [], {}
    for key in ("schema_version", "kind", "source_commit_sha", "build_cutoff_at", "generated_at", "artifact_count", "artifacts"):
        if key not in integrity:
            return None, "blocked", f"artifact_integrity_{key}_missing", [], {}
    if integrity.get("schema_version") != SOURCE_SCHEMA_VERSIONS["artifact_integrity"]:
        return None, "blocked", "artifact_integrity_schema_version_invalid", [], {}
    if integrity.get("kind") != SOURCE_KINDS["artifact_integrity"]:
        return None, "blocked", "artifact_integrity_kind_invalid", [], {}
    for key in ("build_cutoff_at", "generated_at"):
        timestamp_reason = _timestamp_reason(f"artifact_integrity_{key}", integrity.get(key), required=True)
        if timestamp_reason:
            return None, "blocked", timestamp_reason, [], {}
    artifacts_list = integrity.get("artifacts")
    if not isinstance(artifacts_list, list):
        return None, "blocked", "artifact_integrity_artifacts_invalid", [], {}
    if integrity.get("artifact_count") != len(artifacts_list):
        return None, "blocked", "artifact_integrity_artifact_count_invalid", [], {}
    hashed = [row for row in artifacts_list if isinstance(row, dict) and row.get("sha256") and row.get("path")]
    value = f"{len(hashed)}/{len(artifacts_list)}"
    try:
        expected_paths = [rel(path) for path in artifact_paths()]
        # The readiness artifact is self-referential: include its canonical
        # path in the expected envelope even on the first build (before the
        # file exists), keeping integrity status deterministic and fail-closed.
        if READINESS_REL not in expected_paths:
            expected_paths.append(READINESS_REL)
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
    mismatched: list[str] = []
    rows_by_path = {str(row.get("path")): row for row in hashed}
    for path in artifact_paths():
        rel_path = rel(path)
        if rel_path == READINESS_REL:
            # Readiness consumes the manifest; its own hash is verified by
            # the focused checker, not fed back into this status calculation.
            continue
        raw = load_json(path, None)
        row = rows_by_path.get(rel_path)
        if not isinstance(raw, dict) or not row or row.get("sha256") != canonical_hash(raw):
            mismatched.append(rel_path)
    if mismatched:
        details["hash_mismatch_paths"] = mismatched
        notes.append("hash_mismatch=" + ",".join(mismatched[:5]))
        return value, "blocked", "artifact_integrity_manifest_hashes_stale", notes, details
    if not details["covered"]:
        return value, "blocked", "event_to_value_product_readiness_not_in_artifact_integrity_manifest", notes, details
    if not integrity.get("source_commit_sha") or not integrity.get("build_cutoff_at") or not integrity.get("generated_at"):
        return value, "blocked", "artifact_integrity_lineage_missing", notes, details
    # The readiness hash is checked by the focused checker; feeding it back
    # here would make the readiness status self-referential.
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
    if not _has_source_bound_lineage(lineage, SOURCE_PATHS["impact_scenarios"]):
        return False
    return _has_complete_impact_contract(scenario)


def _engine_live_count(payload: dict[str, Any] | None, load_status: str, selected: list[str], engine_name: str) -> tuple[int | None, str, str | None, list[str]]:
    if load_status != "available" or payload is None:
        return None, load_status, "source_artifact_not_generated" if load_status == "not_generated" else "source_artifact_blocked", []
    source_reason = _source_contract_reason(engine_name, payload)
    if source_reason:
        return None, "blocked", source_reason, []
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
            and _has_finite_engine_output(row, engine_name)
            and _has_source_bound_lineage(row.get("provenance") or row.get("lineage") or row.get("run") or row.get("receipt") or row.get("_meta"), SOURCE_PATHS[engine_name])
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


def _project_block(payload: dict[str, Any], reason: str, metrics: list[Any] | None = None, summary: dict[str, Any] | None = None, lineage: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason": reason,
        "metrics": metrics or [],
        "summary": summary or {},
        "lineage": lineage or {},
        "policy": payload.get("policy") or {},
        "product_version": payload.get("product_version"),
        "as_of": payload.get("as_of"),
    }


def _valid_source_paths(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == set(SOURCE_PATHS)
        and all(isinstance(key, str) and isinstance(path, str) and path == SOURCE_PATHS[key] for key, path in value.items())
    )


def _whole_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _metric_contract_reason(row: Any, build_cutoff_at: Any) -> str | None:
    if not isinstance(row, dict):
        return "event_to_value_product_readiness_metric_invalid"
    for key in ("id", "label", "status", "definition", "source_path"):
        if not isinstance(row.get(key), str) or not row.get(key):
            return f"event_to_value_product_readiness_metric_{key}_invalid"
    if row.get("id") not in REQUIRED_METRIC_IDS:
        return f"event_to_value_product_readiness_metric_id_unknown:{row.get('id')}"
    if row.get("status") not in PROJECTED_STATUSES:
        return f"event_to_value_product_readiness_metric_status_invalid:{row.get('id')}"
    if row.get("status") != "available" and not isinstance(row.get("reason"), str):
        return f"event_to_value_product_readiness_metric_reason_missing:{row.get('id')}"
    if row.get("source_path") not in set(SOURCE_PATHS.values()) | {"scripts/check_ask_henneth.mjs", "scripts/check_ci_global_no_lookahead.py"}:
        return f"event_to_value_product_readiness_metric_source_path_invalid:{row.get('id')}"
    timestamp_reason = _timestamp_reason("event_to_value_product_readiness_metric_as_of", row.get("as_of"))
    if timestamp_reason:
        return f"{timestamp_reason}:{row.get('id')}"
    if _after_cutoff(row.get("as_of"), build_cutoff_at):
        return f"event_to_value_product_readiness_metric_as_of_after_build_cutoff:{row.get('id')}"
    notes = row.get("notes")
    if notes is not None and (not isinstance(notes, list) or any(not isinstance(note, str) for note in notes)):
        return f"event_to_value_product_readiness_metric_notes_invalid:{row.get('id')}"
    value = row.get("value")
    if row.get("id") in COUNT_VALUE_METRIC_IDS:
        if value is not None and not _whole_count(value):
            return f"event_to_value_product_readiness_metric_value_invalid:{row.get('id')}"
        if row.get("status") == "available" and not _whole_count(value):
            return f"event_to_value_product_readiness_metric_value_missing:{row.get('id')}"
    elif row.get("id") == "provenance_coverage":
        if value is not None and (not isinstance(value, str) or "/" not in value):
            return "event_to_value_product_readiness_metric_value_invalid:provenance_coverage"
    elif row.get("id") in {"ask_henneth_test_status", "no_lookahead_status"} and value is not None:
        return f"event_to_value_product_readiness_metric_value_invalid:{row.get('id')}"
    elif row.get("id") == "production_gate_status" and value is not None and not isinstance(value, str):
        return "event_to_value_product_readiness_metric_value_invalid:production_gate_status"
    denominator = row.get("denominator")
    if row.get("id") in ALPHA_DENOMINATORS:
        if denominator != ALPHA_DENOMINATORS[row.get("id")]:
            return f"event_to_value_product_readiness_metric_denominator_invalid:{row.get('id')}"
    elif denominator is not None:
        return f"event_to_value_product_readiness_metric_denominator_invalid:{row.get('id')}"
    metric_lineage = row.get("lineage")
    if not isinstance(metric_lineage, dict):
        return f"event_to_value_product_readiness_metric_lineage_invalid:{row.get('id')}"
    if metric_lineage.get("source_path") != row.get("source_path"):
        return f"event_to_value_product_readiness_metric_lineage_source_path_invalid:{row.get('id')}"
    if metric_lineage.get("as_of") != row.get("as_of"):
        return f"event_to_value_product_readiness_metric_lineage_as_of_invalid:{row.get('id')}"
    if metric_lineage.get("status") != row.get("status"):
        return f"event_to_value_product_readiness_metric_lineage_status_invalid:{row.get('id')}"
    if metric_lineage.get("reason") != row.get("reason"):
        return f"event_to_value_product_readiness_metric_lineage_reason_invalid:{row.get('id')}"
    return None


def project_readiness(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("kind") != "event_to_value_product_readiness":
        return {"status": "not_generated", "reason": "event_to_value_product_readiness_not_generated", "metrics": [], "summary": {}, "lineage": {}, "policy": {}, "product_version": None, "as_of": None}
    if payload.get("schema_version") != 1 or payload.get("product_version") != PRODUCT_VERSION:
        return _project_block(payload, "event_to_value_product_readiness_schema_invalid")
    payload_status = payload.get("status")
    if payload_status not in PROJECTED_STATUSES:
        return _project_block(payload, f"event_to_value_product_readiness_status_invalid:{payload_status}")
    if not _valid_source_paths(payload.get("source_paths")):
        return _project_block(payload, "event_to_value_product_readiness_source_paths_invalid")
    metrics = payload.get("metrics")
    lineage = payload.get("lineage") if isinstance(payload.get("lineage"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    for key in ("selected_symbols", "selected_symbols_status", "selected_symbols_reason", "selected_symbols_source_path"):
        if key in summary and key in lineage and summary.get(key) != lineage.get(key):
            return _project_block(payload, f"event_to_value_product_readiness_{key}_mismatch", metrics if isinstance(metrics, list) else [], summary, lineage)
    selected = lineage.get("selected_symbols")
    selected_status = lineage.get("selected_symbols_status")
    if not isinstance(metrics, list) or len(metrics) != 12:
        return _project_block(payload, "event_to_value_product_readiness_metrics_invalid", summary=summary, lineage=lineage)
    metric_ids = [row.get("id") for row in metrics if isinstance(row, dict)]
    if tuple(metric_ids) != REQUIRED_METRIC_IDS:
        return _project_block(payload, "event_to_value_product_readiness_metric_ids_invalid", summary=summary, lineage=lineage)
    for row in metrics:
        reason = _metric_contract_reason(row, lineage.get("build_cutoff_at"))
        if reason:
            return _project_block(payload, reason, summary=summary, lineage=lineage)
    actual_available_count = sum(1 for row in metrics if isinstance(row, dict) and row.get("status") == "available")
    actual_blocked_ids = [row["id"] for row in metrics if isinstance(row, dict) and row.get("status") != "available"]
    if summary.get("metric_count") != len(metrics):
        return _project_block(payload, "event_to_value_product_readiness_metric_count_invalid", metrics, summary, lineage)
    if not isinstance(summary.get("available_metric_count"), int) or isinstance(summary.get("available_metric_count"), bool):
        return _project_block(payload, "event_to_value_product_readiness_available_metric_count_invalid", metrics, summary, lineage)
    if summary.get("available_metric_count") != actual_available_count:
        return _project_block(payload, "event_to_value_product_readiness_available_metric_count_mismatch", metrics, summary, lineage)
    if summary.get("blocked_metric_count") != len(actual_blocked_ids):
        return _project_block(payload, "event_to_value_product_readiness_blocked_metric_count_mismatch", metrics, summary, lineage)
    if summary.get("blocked_metric_ids") != actual_blocked_ids:
        return _project_block(payload, "event_to_value_product_readiness_blocked_metric_ids_mismatch", metrics, summary, lineage)
    if not isinstance(lineage.get("source_commit_sha"), str) or not isinstance(lineage.get("build_cutoff_at"), str) or not isinstance(lineage.get("generated_at"), str):
        return _project_block(payload, "event_to_value_product_readiness_lineage_missing", metrics, summary, lineage)
    for key in ("generated_at", "build_cutoff_at"):
        timestamp_reason = _timestamp_reason(f"event_to_value_product_readiness_lineage_{key}", lineage.get(key), required=True)
        if timestamp_reason:
            return _project_block(payload, timestamp_reason, metrics, summary, lineage)
    if _after_cutoff(lineage.get("generated_at"), lineage.get("build_cutoff_at")):
        return _project_block(payload, "event_to_value_product_readiness_generated_after_build_cutoff", metrics, summary, lineage)
    source_as_of = lineage.get("source_as_of")
    if not isinstance(source_as_of, dict) or set(source_as_of) != set(SOURCE_PATHS):
        return _project_block(payload, "event_to_value_product_readiness_source_as_of_invalid", metrics, summary, lineage)
    for name, as_of in source_as_of.items():
        timestamp_reason = _timestamp_reason("event_to_value_product_readiness_source_as_of", as_of)
        if timestamp_reason:
            return _project_block(payload, f"{timestamp_reason}:{name}", metrics, summary, lineage)
        if _after_cutoff(as_of, lineage.get("build_cutoff_at")):
            return _project_block(payload, f"event_to_value_product_readiness_source_as_of_after_build_cutoff:{name}", metrics, summary, lineage)
    source_schema_version = lineage.get("source_schema_version")
    source_kind = lineage.get("source_kind")
    source_status = lineage.get("source_status")
    source_reason = lineage.get("source_reason")
    if not isinstance(source_schema_version, dict) or set(source_schema_version) != set(SOURCE_PATHS):
        return _project_block(payload, "event_to_value_product_readiness_source_schema_version_invalid", metrics, summary, lineage)
    if not isinstance(source_kind, dict) or set(source_kind) != set(SOURCE_PATHS):
        return _project_block(payload, "event_to_value_product_readiness_source_kind_invalid", metrics, summary, lineage)
    if not isinstance(source_status, dict) or set(source_status) != set(SOURCE_PATHS):
        return _project_block(payload, "event_to_value_product_readiness_source_status_invalid", metrics, summary, lineage)
    if not isinstance(source_reason, dict) or set(source_reason) != set(SOURCE_PATHS):
        return _project_block(payload, "event_to_value_product_readiness_source_reason_invalid", metrics, summary, lineage)
    actual_source_as_of, actual_source_schema_version, actual_source_kind, actual_source_status, actual_source_reason = _current_source_maps()
    if source_as_of != actual_source_as_of:
        return _project_block(payload, "event_to_value_product_readiness_source_as_of_mismatch", metrics, summary, lineage)
    if source_schema_version != actual_source_schema_version:
        return _project_block(payload, "event_to_value_product_readiness_source_schema_version_mismatch", metrics, summary, lineage)
    if source_kind != actual_source_kind:
        return _project_block(payload, "event_to_value_product_readiness_source_kind_mismatch", metrics, summary, lineage)
    if source_status != actual_source_status:
        return _project_block(payload, "event_to_value_product_readiness_source_status_mismatch", metrics, summary, lineage)
    if source_reason != actual_source_reason:
        return _project_block(payload, "event_to_value_product_readiness_source_reason_mismatch", metrics, summary, lineage)
    for name, status in source_status.items():
        if status not in PROJECTED_STATUSES:
            return _project_block(payload, f"event_to_value_product_readiness_source_status_value_invalid:{name}", metrics, summary, lineage)
        if status != "available" and not isinstance(source_reason.get(name), str):
            return _project_block(payload, f"event_to_value_product_readiness_source_reason_missing:{name}", metrics, summary, lineage)
        if status == "available" and source_as_of.get(name) is None:
            return _project_block(payload, f"event_to_value_product_readiness_source_as_of_missing:{name}", metrics, summary, lineage)
        if status == "available":
            if source_schema_version.get(name) != SOURCE_SCHEMA_VERSIONS[name]:
                return _project_block(payload, f"event_to_value_product_readiness_source_schema_version_value_invalid:{name}", metrics, summary, lineage)
            if source_kind.get(name) != SOURCE_KINDS[name]:
                return _project_block(payload, f"event_to_value_product_readiness_source_kind_value_invalid:{name}", metrics, summary, lineage)
        else:
            if source_schema_version.get(name) not in (None, SOURCE_SCHEMA_VERSIONS[name]):
                return _project_block(payload, f"event_to_value_product_readiness_source_schema_version_value_invalid:{name}", metrics, summary, lineage)
            if source_kind.get(name) not in (None, SOURCE_KINDS[name]):
                return _project_block(payload, f"event_to_value_product_readiness_source_kind_value_invalid:{name}", metrics, summary, lineage)
    if (
        selected_status != "available"
        or not isinstance(selected, list)
        or len(selected) != REQUIRED_GOLDEN_COUNT
        or any(not isinstance(symbol, str) or not symbol.strip() or symbol != symbol.strip().upper() for symbol in selected)
        or len(set(selected)) != REQUIRED_GOLDEN_COUNT
    ):
        return _project_block(payload, lineage.get("selected_symbols_reason") or summary.get("selected_symbols_reason") or "selected_symbols_not_exactly_three", metrics, summary, lineage)
    if actual_available_count == 0:
        return _project_block(payload, "event_to_value_product_readiness_all_metrics_blocked", metrics, summary, lineage)
    for key in ("artifact_integrity_status", "artifact_integrity_reason", "artifact_integrity"):
        if key not in lineage:
            return _project_block(payload, f"event_to_value_product_readiness_{key}_missing", metrics, summary, lineage)
    if lineage.get("artifact_integrity_status") not in PROJECTED_STATUSES:
        return _project_block(payload, "event_to_value_product_readiness_artifact_integrity_status_invalid", metrics, summary, lineage)
    if lineage.get("artifact_integrity_status") != "available" and not isinstance(lineage.get("artifact_integrity_reason"), str):
        return _project_block(payload, "event_to_value_product_readiness_artifact_integrity_reason_missing", metrics, summary, lineage)
    if not isinstance(lineage.get("artifact_integrity"), dict):
        return _project_block(payload, "event_to_value_product_readiness_artifact_integrity_shape_invalid", metrics, summary, lineage)
    provenance = next((row for row in metrics if isinstance(row, dict) and row.get("id") == "provenance_coverage"), {})
    if provenance.get("status") != "available":
        return _project_block(payload, provenance.get("reason") or "event_to_value_product_readiness_integrity_unsealed", metrics, summary, lineage)
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
    source_as_of, source_schema_version, source_kind, source_status, source_reasons = _source_maps_from(
        cases=cases,
        cases_status=cases_status,
        truth=truth,
        truth_status=truth_status,
        forecast_readiness=forecast_readiness,
        forecast_ready_status=forecast_ready_status,
        scenarios=scenarios,
        scenarios_status=scenarios_status,
        forecasts=forecasts,
        forecasts_status=forecasts_status,
        valuations=valuations,
        valuations_status=valuations_status,
        expectations=expectations,
        expectations_status=expectations_status,
        theses=theses,
        theses_status=theses_status,
        integrity=integrity,
        integrity_status=integrity_status,
        receipt=receipt,
        receipt_status=receipt_status,
    )

    def blocked_selection() -> tuple[None, str, str, list[str]]:
        return None, "blocked", selection["reason"], [f"selected_symbols={selection['symbols']}"]

    if selected_ready and truth_status == "available" and truth is not None and source_reasons["financial_truth_qualification"] is None:
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
            "not_generated" if truth_status == "not_generated" else "blocked",
            source_reasons["financial_truth_qualification"] or "financial_truth_qualification_blocked",
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

    if selected_ready and scenarios_status == "available" and scenarios is not None and source_reasons["impact_scenarios"] is None:
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
            "not_generated" if scenarios_status == "not_generated" else "blocked",
            source_reasons["impact_scenarios"] or "impact_scenarios_blocked",
            [],
        )
    else:
        scenario_value, scenario_status, scenario_reason, scenario_notes = blocked_selection()

    if selected_ready:
        forecast_count, forecast_status, forecast_reason, forecast_notes = _engine_live_count(forecasts, forecasts_status, selected, "financial_forecasts")
        valuation_count, valuation_status, valuation_reason, valuation_notes = _engine_live_count(valuations, valuations_status, selected, "formal_valuations")
        expectation_count, expectation_status, expectation_reason, expectation_notes = _engine_live_count(expectations, expectations_status, selected, "market_expectations")
    else:
        forecast_count, forecast_status, forecast_reason, forecast_notes = blocked_selection()
        valuation_count, valuation_status, valuation_reason, valuation_notes = blocked_selection()
        expectation_count, expectation_status, expectation_reason, expectation_notes = blocked_selection()

    ask_status = "blocked"
    ask_reason = "ask_henneth_live_runtime_not_recorded_in_authoritative_ci_state"
    ask_notes = ["Focused contract checkers exist at scripts/check_ask_henneth.mjs, but they are not a live production Ask receipt."]

    if selected_ready and theses_status == "available" and theses is not None and source_reasons["thesis_monitoring"] is None:
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
            "not_generated" if theses_status == "not_generated" else "blocked",
            source_reasons["thesis_monitoring"] or "thesis_monitoring_blocked",
            [],
        )
    else:
        thesis_value, thesis_status, thesis_reason, thesis_notes = blocked_selection()

    if (
        selected_ready
        and forecasts_status == "available"
        and valuations_status == "available"
        and expectations_status == "available"
        and source_reasons["financial_forecasts"] is None
        and source_reasons["formal_valuations"] is None
        and source_reasons["market_expectations"] is None
    ):
        nulls_value, nulls_notes = _null_required_outputs(forecasts, valuations, expectations, selected)
        nulls_status, nulls_reason = "available", None
    elif selected_ready:
        nulls_value, nulls_status, nulls_reason, nulls_notes = None, "blocked", (
            source_reasons["financial_forecasts"]
            or source_reasons["formal_valuations"]
            or source_reasons["market_expectations"]
            or "required_output_artifacts_not_all_available"
        ), []
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

    if receipt_status != "available" or receipt is None or source_reasons["release_integrity_receipt"] is not None:
        production_status = "not_generated" if receipt_status == "not_generated" else "blocked"
        production_reason = source_reasons["release_integrity_receipt"] or ("release_integrity_receipt_not_generated" if receipt_status == "not_generated" else "release_integrity_receipt_blocked")
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
        "source_as_of": source_as_of,
        "source_schema_version": source_schema_version,
        "source_kind": source_kind,
        "source_status": source_status,
        "source_reason": source_reasons,
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
