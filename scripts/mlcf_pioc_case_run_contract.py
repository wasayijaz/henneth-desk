"""Strict contract for the MLCF/PIOC acquisition-control case-run envelope.

This module deliberately owns no state I/O.  It validates the narrow envelope
emitted by :mod:`mlcf_pioc_case_run_adapter` and delegates economic scenario
validation to the existing cement expansion contract.  A blocked run carries
identity and provenance only; no partial economic values are accepted.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import date, datetime
from typing import Any, Mapping

import cement_expansion_contract as cement

CASE_ID = "case_mlcf_pioc_control_observed_v1"
SCENARIOS = ("bear", "base", "bull")
FIXTURE_SYMBOL = "MLCF-FIXTURE"
FIXTURE_EVENT_REF = "fixture:mlcf-pioc-cement-expansion-v1"
FIXTURE_EFFECTIVE_DATE = "2025-12-31"
FIXTURE_VALUATION_DATE = "2025-12-31"
FIXTURE_QUARTER_ENDS = (
    "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30",
    "2026-12-31", "2027-03-31", "2027-06-30", "2027-09-30",
)
ENVELOPE_KEYS = {
    "status",
    "case_id",
    "scenario_runs",
    "blocked_reasons",
    "input_lineage",
    "analogue_readiness",
    "formal_output_readiness",
}
RUN_KEYS = {"scenario", "status", "blocked_reasons", "result"}
READINESS_KEYS = {"status", "blocked_reasons", "hard_block", "reason"}
_ENGINE_RESULT_KEYS = {
    "schema_version", "formula_id", "engine_version", "run_receipt", "status",
    "blocked_reasons", "scenario", "inputs_lineage", "quarterly_schedule",
    "values", "per_share", "break_even", "confidence_limitations",
}
_ENGINE_RESULT_SCHEMA = "cement_expansion_model_result_v1"
_ADAPTER_RESULT_KEYS = _ENGINE_RESULT_KEYS | {"case_id"}
_SCENARIO_KEYS = {"symbol", "event_ref", "case_label", "effective_date", "valuation_date"}
_RECEIPT_KEYS = {"inputs_sha256", "contract_version"}
_EXPECTED_FORMULA_ID = "cement_expansion.operating_economics.v1"
_EXPECTED_ENGINE_VERSION = "cement_expansion_engine_v1"
_VALUE_KEYS = {"npv_pkr", "total_revenue_pkr", "total_gross_profit_pkr", "total_ebitda_pkr", "total_capex_pkr", "total_fcf_pkr"}
_PER_SHARE_KEYS = {"npv_pkr"}
_BREAK_EVEN_KEYS = {"ebitda_break_even_quarter", "ebitda_break_even_quarter_end", "cash_break_even_quarter", "cash_break_even_quarter_end", "note"}
_LIMITATION_KEYS = {"research_only", "no_advice", "single_point_estimate", "simplifications"}
_ANALYST_REF_KEYS = {"note_id", "note"}
_SOURCE_REF_BASE_KEYS = {"id", "label"}
_EVIDENCE_REF_KEYS = {
    "event_id", "document_id", "document_title", "document_published_at",
    "document_retrieved_at", "content_sha256", "source", "source_url",
    "page", "text",
}
_QUARTER_KEYS = {
    "quarter_index", "quarter_end", "commissioned", "capacity_units", "utilization_pct", "volume_units",
    "selling_price_pkr_per_unit", "fuel_cost_pkr_per_unit", "power_cost_pkr_per_unit", "freight_cost_pkr_per_unit",
    "revenue_pkr", "variable_cost_pkr", "gross_profit_pkr", "fixed_cost_pkr", "ebitda_pkr", "depreciation_pkr",
    "ebit_pkr", "finance_cost_pkr", "tax_pkr", "net_income_pkr", "eps_pkr", "working_capital_pkr",
    "delta_working_capital_pkr", "capex_pkr", "fcf_pkr", "cumulative_fcf_pkr", "roic_pct", "discount_factor",
    "discounted_fcf_pkr",
}
_HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")

_ADVICE_RE = re.compile(
    r"\b(?:buy|sell|accumulate|recommend(?:ation)?|you\s+should)\b|"
    r"\btarget\s+price\b|\bprice\s+target\b",
    flags=re.IGNORECASE,
)
_LEAK_KEYS = {"target_price", "price_target", "targetPrice", "priceTarget"}


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _scan_leaks(value: Any, path: str = "$") -> list[str]:
    """Return advice/target-price/non-finite violations in arbitrary JSON."""
    violations: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text in _LEAK_KEYS or _ADVICE_RE.search(key_text):
                violations.append(f"{path}.{key_text}: advice or target-price field is forbidden")
            violations.extend(_scan_leaks(item, f"{path}.{key_text}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            violations.extend(_scan_leaks(item, f"{path}[{index}]"))
    elif isinstance(value, str) and _ADVICE_RE.search(value):
        violations.append(f"{path}: advice or target-price language is forbidden")
    elif isinstance(value, float) and not math.isfinite(value):
        violations.append(f"{path}: value must be finite")
    return violations


def _date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _closed(mapping: Mapping[str, Any], allowed: set[str], path: str) -> list[str]:
    return [f"{path}.{key}: unknown field" for key in sorted(set(mapping) - allowed, key=str)]


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _source_ref_valid(ref: Any) -> bool:
    if not isinstance(ref, Mapping):
        return False
    keys = set(ref)
    if keys not in (_SOURCE_REF_BASE_KEYS | {"url"}, _SOURCE_REF_BASE_KEYS | {"path"}):
        return False
    return (
        _nonempty(ref.get("id"))
        and _nonempty(ref.get("label"))
        and (_nonempty(ref.get("url")) or _nonempty(ref.get("path")))
    )


def _analyst_ref_valid(ref: Any) -> bool:
    return (
        isinstance(ref, Mapping)
        and set(ref) == _ANALYST_REF_KEYS
        and _nonempty(ref.get("note_id"))
        and _nonempty(ref.get("note"))
    )


def _evidence_ref_valid(row: Mapping[str, Any]) -> bool:
    if set(row) != {"kind", "document_id", "source_ref"} or row.get("kind") != "evidence":
        return False
    ref = row.get("source_ref")
    if not isinstance(ref, Mapping) or set(ref) != _EVIDENCE_REF_KEYS:
        return False
    return (
        row.get("document_id") == ref.get("document_id")
        and _nonempty(ref.get("event_id"))
        and _nonempty(ref.get("document_id"))
        and _nonempty(ref.get("document_title"))
        and _datetime(ref.get("document_published_at")) is not None
        and _datetime(ref.get("document_retrieved_at")) is not None
        and isinstance(ref.get("content_sha256"), str)
        and _HASH_RE.fullmatch(ref.get("content_sha256", "")) is not None
        and _nonempty(ref.get("source"))
        and _nonempty(ref.get("source_url"))
        and isinstance(ref.get("page"), int)
        and not isinstance(ref.get("page"), bool)
        and ref.get("page") > 0
        and _nonempty(ref.get("text"))
    )


def _canonical_case_from_result(result: Mapping[str, Any]) -> dict[str, Any] | None:
    scenario = result.get("scenario")
    lineage = result.get("inputs_lineage")
    if not isinstance(scenario, Mapping) or not isinstance(lineage, list):
        return None
    inputs: dict[str, Any] = {}
    for row in lineage:
        if not isinstance(row, Mapping):
            return None
        label = row.get("label_type")
        record = {
            "value": copy.deepcopy(row.get("value")),
            "label_type": label,
            "available_on": row.get("available_on"),
        }
        if label == "source":
            record["source_ref"] = copy.deepcopy(row.get("source_ref"))
        elif label == "analyst":
            record["analyst_ref"] = copy.deepcopy(row.get("analyst_ref"))
        else:
            return None
        inputs[str(row.get("field"))] = record
    return {
        "case_id": CASE_ID,
        "symbol": scenario.get("symbol"),
        "event_ref": scenario.get("event_ref"),
        "case_label": scenario.get("case_label"),
        "effective_date": scenario.get("effective_date"),
        "valuation_date": scenario.get("valuation_date"),
        "inputs": inputs,
    }


def _fixture_identity_violations(result: Mapping[str, Any], run: Mapping[str, Any], path: str) -> list[str]:
    scenario = result.get("scenario")
    if not isinstance(scenario, Mapping) or set(scenario) != _SCENARIO_KEYS:
        return [f"{path}.scenario: closed fixture identity required"]
    expected = {
        "symbol": FIXTURE_SYMBOL,
        "event_ref": FIXTURE_EVENT_REF,
        "case_label": run.get("scenario"),
        "effective_date": FIXTURE_EFFECTIVE_DATE,
        "valuation_date": FIXTURE_VALUATION_DATE,
    }
    if dict(scenario) != expected:
        return [f"{path}.scenario: fixture identity mismatch"]
    return []


def _verify_fixture_result(result: Mapping[str, Any], path: str) -> list[str]:
    case = _canonical_case_from_result(result)
    if case is None:
        return [f"{path}: cannot reconstruct canonical fixture case"]
    if case.get("symbol") != FIXTURE_SYMBOL or case.get("event_ref") != FIXTURE_EVENT_REF:
        return [f"{path}: fixture case identity mismatch"]
    if case.get("effective_date") != FIXTURE_EFFECTIVE_DATE or case.get("valuation_date") != FIXTURE_VALUATION_DATE:
        return [f"{path}: fixture case date mismatch"]
    quarter_record = ((case.get("inputs") or {}).get("quarter_ends") or {})
    if quarter_record.get("value") != list(FIXTURE_QUARTER_ENDS):
        return [f"{path}.inputs_lineage: fixture quarter ends mismatch"]
    canonical = json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    receipt = result.get("run_receipt")
    if not isinstance(receipt, Mapping) or receipt.get("inputs_sha256") != hashlib.sha256(canonical.encode("utf-8")).hexdigest():
        return [f"{path}.run_receipt: inputs hash does not match canonical fixture case"]
    try:
        import cement_expansion_engine as engine

        expected = engine.evaluate_case(case)
    except Exception as error:
        return [f"{path}: canonical fixture re-evaluation failed: {error}"]
    expected["case_id"] = CASE_ID
    if result != expected:
        return [f"{path}: result does not match independently re-evaluated fixture result"]
    return []


def _result_shape(result: Mapping[str, Any], run: Mapping[str, Any], path: str) -> list[str]:
    violations: list[str] = []
    violations.extend(_closed(result, _ADAPTER_RESULT_KEYS, path))
    if set(result) != _ADAPTER_RESULT_KEYS:
        violations.extend(f"{path}.{key}: missing field" for key in sorted(_ADAPTER_RESULT_KEYS - set(result), key=str))
    if (
        result.get("case_id") != CASE_ID
        or result.get("schema_version") != _ENGINE_RESULT_SCHEMA
        or result.get("formula_id") != _EXPECTED_FORMULA_ID
        or result.get("engine_version") != _EXPECTED_ENGINE_VERSION
        or result.get("status") != "computed"
    ):
        violations.append(f"{path}: canonical computed identity mismatch")
    if result.get("blocked_reasons") != []:
        violations.append(f"{path}.blocked_reasons: computed result must be empty")
    receipt = result.get("run_receipt")
    if not isinstance(receipt, Mapping) or set(receipt) != _RECEIPT_KEYS or not isinstance(receipt.get("inputs_sha256"), str) or not _HASH_RE.fullmatch(receipt.get("inputs_sha256", "")) or receipt.get("contract_version") != cement.CONTRACT_VERSION:
        violations.append(f"{path}.run_receipt: closed canonical receipt required")
    violations.extend(_fixture_identity_violations(result, run, path))
    values = result.get("values")
    if not isinstance(values, Mapping) or set(values) != _VALUE_KEYS or any(not _finite(value) for value in values.values()):
        violations.append(f"{path}.values: exact finite canonical summary required")
    per_share = result.get("per_share")
    if not isinstance(per_share, Mapping) or set(per_share) != _PER_SHARE_KEYS or not _finite(per_share.get("npv_pkr")):
        violations.append(f"{path}.per_share: exact finite canonical summary required")
    break_even = result.get("break_even")
    if not isinstance(break_even, Mapping) or set(break_even) != _BREAK_EVEN_KEYS:
        violations.append(f"{path}.break_even: exact canonical fields required")
    elif any(value is not None and not isinstance(value, (str, int)) for value in break_even.values()):
        violations.append(f"{path}.break_even: invalid field types")
    limits = result.get("confidence_limitations")
    if not isinstance(limits, Mapping) or set(limits) != _LIMITATION_KEYS or limits.get("research_only") is not True or limits.get("no_advice") is not True or limits.get("single_point_estimate") is not True or not isinstance(limits.get("simplifications"), list) or not limits.get("simplifications"):
        violations.append(f"{path}.confidence_limitations: exact non-empty canonical limitations required")
    schedule = result.get("quarterly_schedule")
    if not isinstance(schedule, list) or len(schedule) != cement.QUARTER_COUNT:
        violations.append(f"{path}.quarterly_schedule: must contain exactly 8 rows")
    else:
        for index, row in enumerate(schedule):
            row_path = f"{path}.quarterly_schedule[{index}]"
            if not isinstance(row, Mapping) or set(row) != _QUARTER_KEYS:
                violations.append(f"{row_path}: exact canonical quarter keys required")
                continue
            if row.get("quarter_index") != index + 1 or not isinstance(row.get("quarter_end"), str) or _date(row.get("quarter_end")) is None:
                violations.append(f"{row_path}: quarter identity mismatch")
            elif row.get("quarter_end") != FIXTURE_QUARTER_ENDS[index]:
                violations.append(f"{row_path}: fixture quarter end mismatch")
            if not isinstance(row.get("commissioned"), bool):
                violations.append(f"{row_path}.commissioned: must be boolean")
            for key, value in row.items():
                if key not in {"quarter_index", "quarter_end", "commissioned"} and not _finite(value):
                    violations.append(f"{row_path}.{key}: must be finite numeric")
    lineage = result.get("inputs_lineage")
    if not isinstance(lineage, list) or len(lineage) != len(cement._REQUIRED):
        violations.append(f"{path}.inputs_lineage: must contain every canonical input exactly once")
    else:
        fields = []
        for index, row in enumerate(lineage):
            row_path = f"{path}.inputs_lineage[{index}]"
            if not isinstance(row, Mapping):
                violations.append(f"{row_path}: must be a mapping"); continue
            fields.append(row.get("field"))
            label = row.get("label_type")
            allowed = {"field", "value", "label_type", "available_on", "source_ref" if label == "source" else "analyst_ref"}
            violations.extend(_closed(row, allowed, row_path))
            if label not in {"source", "analyst"} or not isinstance(row.get("available_on"), str) or _date(row.get("available_on")) is None:
                violations.append(f"{row_path}: closed provenance fields required")
            ref = row.get("source_ref") if label == "source" else row.get("analyst_ref")
            if not isinstance(ref, Mapping) or not ref:
                violations.append(f"{row_path}: provenance reference required")
            elif label == "source" and not _source_ref_valid(ref):
                violations.append(f"{row_path}.source_ref: exact source reference required")
            elif label == "analyst" and not _analyst_ref_valid(ref):
                violations.append(f"{row_path}.analyst_ref: exact analyst reference required")
            if row.get("value") is None:
                violations.append(f"{row_path}.value: empty lineage value")
        if fields != sorted(cement._REQUIRED) or len(set(fields)) != len(fields):
            violations.append(f"{path}.inputs_lineage: canonical input field coverage mismatch")
    if not violations:
        violations.extend(_verify_fixture_result(result, path))
    return violations


def validate_scenario_case(case: Mapping[str, Any]) -> list[str]:
    """Validate one economic scenario, including exact case identity."""
    if not isinstance(case, Mapping):
        return ["scenario case: must be a mapping"]
    violations: list[str] = []
    if case.get("case_id") != CASE_ID:
        violations.append(f"case_id: must equal {CASE_ID}")
    if case.get("case_label") not in SCENARIOS:
        violations.append("case_label: must be one of bear, base, bull")
    violations.extend(cement.validate_case(case))
    violations.extend(_scan_leaks(case))
    return sorted(set(violations))


def _lineage_valid(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for item in value:
        if not isinstance(item, Mapping):
            return False
        # Every lineage item must identify a retained source or an explicit
        # analyst note.  Numeric economic values are intentionally optional.
        label = item.get("label_type")
        if label == "source":
            if set(item) != {"field", "value", "label_type", "available_on", "source_ref"}:
                return False
            if not isinstance(item.get("available_on"), str) or _date(item.get("available_on")) is None:
                return False
            if not _source_ref_valid(item.get("source_ref")):
                return False
        elif label == "analyst":
            if set(item) != {"field", "value", "label_type", "available_on", "analyst_ref"}:
                return False
            if not isinstance(item.get("available_on"), str) or _date(item.get("available_on")) is None:
                return False
            if not _analyst_ref_valid(item.get("analyst_ref")):
                return False
        elif item.get("kind") == "evidence":
            if not _evidence_ref_valid(item):
                return False
        else:
            return False
    return True


def validate_case_run(envelope: Mapping[str, Any]) -> list[str]:
    """Return deterministic named violations; an empty list means valid."""
    if not isinstance(envelope, Mapping):
        return ["envelope: must be a mapping"]
    violations: list[str] = []
    unknown = set(envelope) - ENVELOPE_KEYS
    violations.extend(f"{key}: unknown envelope field" for key in sorted(unknown, key=str))
    if envelope.get("case_id") != CASE_ID:
        violations.append(f"case_id: must equal {CASE_ID}")
    status = envelope.get("status")
    if status not in {"blocked", "computed"}:
        violations.append("status: must be blocked or computed")
    reasons = envelope.get("blocked_reasons")
    if not isinstance(reasons, list) or any(not isinstance(row, str) or not row.strip() for row in reasons):
        violations.append("blocked_reasons: must be a list of non-empty strings")
    elif reasons != sorted(set(reasons)):
        violations.append("blocked_reasons: must be sorted and deduplicated")
    if not _lineage_valid(envelope.get("input_lineage")):
        violations.append("input_lineage: must contain source/analyst/evidence lineage")

    runs = envelope.get("scenario_runs")
    if not isinstance(runs, list):
        violations.append("scenario_runs: must be a list")
        runs = []
    elif status == "computed" and len(runs) != 3:
        violations.append("scenario_runs: computed envelope must contain exactly bear, base and bull")
    elif status == "blocked" and runs:
        violations.append("scenario_runs: blocked envelope must contain no scenario objects")
    labels: list[str] = []
    for index, run in enumerate(runs):
        path = f"scenario_runs[{index}]"
        if not isinstance(run, Mapping):
            violations.append(f"{path}: must be a mapping")
            continue
        labels.append(str(run.get("scenario")))
        violations.extend(f"{path}.{key}: unknown field" for key in sorted(set(run) - RUN_KEYS, key=str))
        if run.get("scenario") not in SCENARIOS:
            violations.append(f"{path}.scenario: must be one of bear, base, bull")
        run_status = run.get("status")
        if run_status not in {"blocked", "computed"}:
            violations.append(f"{path}.status: must be blocked or computed")
        run_reasons = run.get("blocked_reasons")
        if not isinstance(run_reasons, list) or any(not isinstance(row, str) or not row.strip() for row in run_reasons):
            violations.append(f"{path}.blocked_reasons: must be a list of non-empty strings")
        elif run_reasons != sorted(set(run_reasons)):
            violations.append(f"{path}.blocked_reasons: must be sorted and deduplicated")
        if run_status == "blocked":
            if "result" in run:
                violations.append(f"{path}: blocked run cannot carry result values")
            if not run_reasons:
                violations.append(f"{path}: blocked run requires a reason")
        elif not isinstance(run.get("result"), Mapping):
            violations.append(f"{path}.result: computed run requires an engine result")
        elif run_reasons:
            violations.append(f"{path}: computed run cannot carry blocked reasons")
        else:
            result = run["result"]
            violations.extend(_result_shape(result, run, f"{path}.result"))

    if status == "computed" and labels != list(SCENARIOS):
        violations.append("scenario_runs: labels must be exactly bear, base, bull")
    if status == "blocked" and any(isinstance(run, Mapping) and run.get("status") == "computed" for run in runs):
        violations.append("status: blocked envelope cannot contain computed scenarios")
    if status == "computed" and any(isinstance(run, Mapping) and run.get("status") != "computed" for run in runs):
        violations.append("status: computed envelope requires three computed scenarios")
    for field in ("analogue_readiness", "formal_output_readiness"):
        value = envelope.get(field)
        if not isinstance(value, Mapping):
            violations.append(f"{field}: must be a mapping")
        else:
            violations.extend(f"{field}.{key}: unknown field" for key in sorted(set(value) - READINESS_KEYS, key=str))
            expected_status = "blocked" if field == "formal_output_readiness" and status == "blocked" else "not_ready"
            if value.get("status") != expected_status:
                violations.append(f"{field}.status: must equal {expected_status}")
            readiness_reasons = value.get("blocked_reasons")
            if not isinstance(readiness_reasons, list) or any(not isinstance(x, str) or not x.strip() for x in readiness_reasons):
                violations.append(f"{field}.blocked_reasons: must be a list of strings")
            elif readiness_reasons != sorted(set(readiness_reasons)):
                violations.append(f"{field}.blocked_reasons: must be sorted and deduplicated")
            elif field == "formal_output_readiness" and status == "blocked" and readiness_reasons != reasons:
                violations.append(f"{field}.blocked_reasons: must match authoritative blocked reasons")
            if value.get("hard_block") is not True:
                violations.append(f"{field}.hard_block: must be true")
            if readiness_reasons and value.get("reason") != readiness_reasons[0]:
                violations.append(f"{field}.reason: must equal the first blocked reason")
    violations.extend(_scan_leaks(envelope))
    return sorted(set(violations))


def numeric_output_keys(value: Any, path: str = "$") -> list[str]:
    """Find numeric economic payloads; blocked runs use this as a safety check."""
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"values", "per_share", "quarterly_schedule", "break_even"} and item not in (None, [], {}):
                found.append(f"{path}.{key}")
            found.extend(numeric_output_keys(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(numeric_output_keys(item, f"{path}[{index}]"))
    return found
