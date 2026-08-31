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
REAL_SYMBOL = "MLCF"
REAL_TARGET_SYMBOL = "PIOC"
REAL_CASE_FAMILY = "industrial_cement"
REAL_CASE_TYPE = "acquisition_control"
REAL_MANIFEST_ID = "mlcf_pioc_event_model_readiness_v1"
# Includes the producer's source event timestamp.  This is immutable evidence
# lineage, not a generated/build timestamp.
REAL_SOURCE_CHAIN_SHA256 = "9497a1d7b6ba23c1e3983a164a807437042ca3ec139224c40f885289feccc4be"
REAL_SOURCE_CHAIN_IDS = (
    ("mlcf_pioc_public_offer_control", "evt_cb44dc32c91b0c5712a5", "psx:267429"),
    ("mlcf_pioc_dispatch_inclusion", "evt_25bfb52e721191c7b644", "psx:275425"),
)
READINESS_TOP_KEYS = {
    "status", "kernel_activation", "attribution", "source_join",
    "financial_truth_counters", "event_specific_kernel_requirements", "guardrails",
}
READINESS_ATTRIBUTION = {
    "acquirer": REAL_SYMBOL,
    "target": REAL_TARGET_SYMBOL,
    "follow_through": "dispatch_inclusion",
}
READINESS_SOURCE_JOIN_KEYS = {
    "role", "canonical_event_id", "canonical_event_id_binding", "legacy_event_id",
    "document_id", "page", "content_sha256", "evidence_sha256", "published_at",
    "effective_date", "available_on",
}
READINESS_SOURCE_JOIN = (
    {
        "role": "primary_control",
        "canonical_event_id": "evt_6e9b520a122b8f2d4a59",
        "canonical_event_id_binding": "independent_operating_event",
        "legacy_event_id": "evt_cb44dc32c91b0c5712a5",
        "document_id": "psx:267429", "page": 3,
        "content_sha256": "98cf83c9a286999c8006a7f73f490248f26694c9edbfc815b3dbd9188ee22a54",
        "evidence_sha256": "70a110272f96813a4d6693b596c99d9dbc4c4781d42a519543557a04ec4c581f",
        "published_at": "2025-12-18T12:52:00+05:00", "effective_date": "2025-12-18", "available_on": "2025-12-18",
    },
    {
        "role": "operating_follow_through",
        "canonical_event_id": "evt_25bfb52e721191c7b644",
        "canonical_event_id_binding": "legacy_alias_no_independent_operating_event",
        "legacy_event_id": "evt_25bfb52e721191c7b644",
        "document_id": "psx:275425", "page": 4,
        "content_sha256": "744a0c710043d6e0a7de36bb99f21ca50f0f9346f6972b957f6733a47deae11f",
        "evidence_sha256": "725f04c3c6d7f36bbffd6c205d574750f65b8c0546ae9f1b50683fe07b292b66",
        "published_at": "2026-04-28T10:25:00+05:00", "effective_date": "2026-04-28", "available_on": "2026-04-28",
    },
)
READINESS_COUNTERS = {
    "annual_income_triplets": {"required": 5, "present": 3, "qualified_periods": ["2026-06-30", "2025-06-30", "2024-06-30"]},
    "qualified_reported_quarter_fact_sets": {"required": 8, "present": 3, "qualified_periods": ["2026-03-31", "2025-12-31", "2025-09-30"]},
    "annual_operating_cash_flow": {"required": 5, "present": 2, "qualified_periods": ["2025-06-30", "2024-06-30"]},
    "share_count": {"status": "missing_official_share_count_capital_note_tie_out", "available_on": None, "source": None},
}
READINESS_REQUIREMENTS = (
    "incremental_revenue_pkr", "incremental_margin_pct", "incremental_eps_pkr",
    "incremental_operating_cash_flow_pkr", "incremental_debt_pkr", "incremental_share_count",
    "cement_capacity_units", "commissioning_or_ramp_schedule", "capex_schedule_pkr",
    "fuel_power_freight_cost_schedule",
)
READINESS_REQUIREMENT_RECORD = {
    "value": None,
    "source_label": "retained_state_only:no_source_qualified_event_input",
    "status": "missing_source_bound_input",
}
READINESS_GUARDRAILS = {
    "dispatch_inclusion_not_standalone_pioc_earnings_or_capacity_impact": True,
    "no_numeric_model_output": True,
}
REAL_KNOWN_FIELDS = {
    "target": "Pioneer Cement Limited",
    "control": "reported control of Pioneer Cement Limited",
    "offer_shares": "up to 26,623,096 PIOC shares",
    "offer_percent": "11.72% shares",
    "spa_percent": "58.03% through Share Purchase Agreement(s)",
    "offer_price": "PKR 478.43 per share",
    "timing": "during February 2026",
    "follow_through": "Pioneer Cement Limited dispatches included in local-market total",
}
REAL_MISSING_INPUT_STATUSES = {
    "pioc_ci_pilot_membership": "missing",
    "pioc_retained_official_financial_documents": "missing",
    "pioc_financial_truth_row": "missing",
    "pioc_model_input_row": "missing",
    "mlcf_full_financial_truth_gate": "missing",
    "event_specific_incremental_financial_bridge": "missing",
    "mlcf_historical_adapter_scope": "insufficient_for_event_model",
}
REAL_MISSING_INPUTS = (
    {
        "input_id": "pioc_ci_pilot_membership", "status": "missing",
        "required": "target company inside current CI pilot", "present": False,
        "source_path": "state/company_profiles.json",
    },
    {
        "input_id": "pioc_retained_official_financial_documents", "status": "missing",
        "required": "retained official target-company financial documents under the CI document source", "present": 0,
        "source_path": "state/company_documents.json",
    },
    {
        "input_id": "pioc_financial_truth_row", "status": "missing",
        "required": "target-company financial truth row under the CI pilot boundary", "present": 0,
        "source_path": "state/company_intel/financial_truth_qualification.json",
    },
    {
        "input_id": "pioc_model_input_row", "status": "missing",
        "required": "target-company model-input row under the CI pilot boundary", "present": 0,
        "source_path": "state/company_intel/financial_model_inputs.json",
    },
    {
        "input_id": "mlcf_full_financial_truth_gate", "status": "missing",
        "required": {"annual_income_triplets": 5, "reported_quarter_fact_sets": 8,
                     "annual_operating_cash_flow": 5, "official_share_count_capital_note_tie_out": 1},
        "present": {"annual_income_triplets": 3, "reported_quarter_fact_sets": 3,
                    "annual_operating_cash_flow": 2, "official_share_count_capital_note_tie_out": 0},
        "source_path": "state/company_intel/financial_truth_qualification.json",
    },
    {
        "input_id": "event_specific_incremental_financial_bridge", "status": "missing",
        "required": ["source-qualified target-company contribution by retained period",
                     "source-qualified acquirer consolidation bridge by retained period",
                     "source-qualified debt and cash position tied to the transaction chain",
                     "official share-capital tie-out after the transaction chain"],
        "present": [],
        "source_paths": ["state/company_intel/intelligence_cases.json",
                         "state/company_intel/financial_evidence_reconciliation.json",
                         "state/company_intel/financial_model_inputs.json"],
    },
    {
        "input_id": "mlcf_historical_adapter_scope", "status": "insufficient_for_event_model",
        "required": "event-specific MLCF/PIOC acquisition-control model inputs",
        "present": {"mlcf_company_model_input_status": "ready",
                    "adapter_version": "cement_actuals_to_formal_engine_inputs_v1",
                    "scope_limitation": "MLCF historical actuals only; not a target-company or transaction-chain model"},
        "source_path": "state/company_intel/financial_model_inputs.json",
    },
)
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
    "page", "text", "event_date",
}
# The readiness manifest is a compact projection of source evidence.  It does
# not duplicate the full text or the event timestamp held by the case facts.
_MANIFEST_EVIDENCE_REF_KEYS = _EVIDENCE_REF_KEYS - {"text", "event_date"}
_REAL_CASE_KEYS = {
    "case_id", "symbol", "target_symbol", "case_family", "case_type", "status",
    "epistemic_type", "as_of", "summary", "observed_facts", "alternative_readings",
    "promotion_blocks", "policy", "source_lineage", "cement_input_readiness",
}
_REAL_OBSERVED_FACT_KEYS = {
    "fact_id", "source_event_id", "document_id", "event_date", "statement",
    "reported_values", "evidence",
}
_REAL_REPORTED_VALUE_KEYS = {"label", "value"}
_REAL_MANIFEST_KEYS = {
    "manifest_id", "case_id", "case_status", "acquirer_symbol", "target_symbol",
    "status", "as_of", "known_fields", "pilot_status", "evidence_refs",
    "missing_inputs", "formal_output_policy",
}
_REAL_KNOWN_FIELDS_KEYS = set(REAL_KNOWN_FIELDS)
_REAL_PILOT_STATUS_KEYS = {
    "target_symbol", "in_current_ci_pilot", "pilot_symbols_source", "status",
}
_REAL_MISSING_INPUT_KEYS = {"input_id", "status", "required", "present"}
_REAL_FORMAL_OUTPUT_POLICY_KEYS = {
    "status", "hard_block", "accepted_outputs", "block_reason",
    "no_generic_economic_engine", "reported_fields_only",
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


def _exact_keys(mapping: Mapping[str, Any], allowed: set[str], path: str) -> list[str]:
    violations = _closed(mapping, allowed, path)
    violations.extend(f"{path}.{key}: missing field" for key in sorted(allowed - set(mapping), key=str))
    return violations


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
        and _datetime(ref.get("event_date")) is not None
        and isinstance(ref.get("content_sha256"), str)
        and _HASH_RE.fullmatch(ref.get("content_sha256", "")) is not None
        and _nonempty(ref.get("source"))
        and _nonempty(ref.get("source_url"))
        and isinstance(ref.get("page"), int)
        and not isinstance(ref.get("page"), bool)
        and ref.get("page") > 0
        and _nonempty(ref.get("text"))
    )


def _canonical_hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _strict_evidence_ref(ref: Any, path: str, *, require_text: bool) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(ref, Mapping):
        return None, [f"{path}: must be a mapping"]
    allowed = _EVIDENCE_REF_KEYS if require_text else _MANIFEST_EVIDENCE_REF_KEYS
    violations = _exact_keys(ref, allowed, path)
    if _datetime(ref.get("document_published_at")) is None:
        violations.append(f"{path}.document_published_at: must be an ISO datetime")
    if _datetime(ref.get("document_retrieved_at")) is None:
        violations.append(f"{path}.document_retrieved_at: must be an ISO datetime")
    if require_text and _datetime(ref.get("event_date")) is None:
        violations.append(f"{path}.event_date: must be an ISO datetime")
    for key in ("event_id", "document_id", "document_title", "source", "source_url"):
        if not _nonempty(ref.get(key)):
            violations.append(f"{path}.{key}: must be a non-empty string")
    if not isinstance(ref.get("content_sha256"), str) or _HASH_RE.fullmatch(ref.get("content_sha256", "")) is None:
        violations.append(f"{path}.content_sha256: must be a 64-character hex hash")
    if not isinstance(ref.get("page"), int) or isinstance(ref.get("page"), bool) or ref.get("page") <= 0:
        violations.append(f"{path}.page: must be a positive integer")
    if require_text and not _nonempty(ref.get("text")):
        violations.append(f"{path}.text: must be a non-empty string")
    return {str(key): copy.deepcopy(value) for key, value in ref.items()}, violations


def _manifest_ref(ref: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(ref.get(key)) for key in sorted(_MANIFEST_EVIDENCE_REF_KEYS)}


def _raw_source_refs(value: Any, path: str, *, require_text: bool) -> tuple[list[dict[str, Any]], list[str]]:
    refs: list[dict[str, Any]] = []
    violations: list[str] = []
    if not isinstance(value, list):
        return refs, [f"{path}: must be a list"]
    if len(value) != len(REAL_SOURCE_CHAIN_IDS):
        violations.append(f"{path}: must contain exactly {len(REAL_SOURCE_CHAIN_IDS)} retained evidence rows")
    for index, ref_value in enumerate(value):
        ref, ref_violations = _strict_evidence_ref(
            ref_value, f"{path}[{index}]", require_text=require_text
        )
        violations.extend(ref_violations)
        if ref is not None:
            refs.append(ref)
    return refs, violations


def _wrapped_lineage_source_refs(value: Any, path: str) -> tuple[list[dict[str, Any]], list[str]]:
    refs: list[dict[str, Any]] = []
    violations: list[str] = []
    if not isinstance(value, list):
        return refs, [f"{path}: must be a list"]
    if len(value) != len(REAL_SOURCE_CHAIN_IDS):
        violations.append(f"{path}: must contain exactly {len(REAL_SOURCE_CHAIN_IDS)} retained evidence rows")
    for index, row in enumerate(value):
        row_path = f"{path}[{index}]"
        if not isinstance(row, Mapping):
            violations.append(f"{row_path}: must be a mapping")
            continue
        violations.extend(_exact_keys(row, {"kind", "document_id", "source_ref"}, row_path))
        if row.get("kind") != "evidence":
            violations.append(f"{row_path}.kind: must be evidence")
        ref, ref_violations = _strict_evidence_ref(row.get("source_ref"), f"{row_path}.source_ref", require_text=True)
        violations.extend(ref_violations)
        if row.get("document_id") != (ref or {}).get("document_id"):
            violations.append(f"{row_path}.document_id: must match source_ref.document_id")
        if ref is not None:
            refs.append(ref)
    return refs, violations


def _real_lineage_violations(value: Any, path: str) -> list[str]:
    refs, violations = _wrapped_lineage_source_refs(value, path)
    if len(refs) == len(REAL_SOURCE_CHAIN_IDS):
        for index, ((_, expected_event_id, expected_doc_id), ref) in enumerate(zip(REAL_SOURCE_CHAIN_IDS, refs)):
            ref_path = f"{path}[{index}].source_ref"
            if ref.get("event_id") != expected_event_id:
                violations.append(f"{ref_path}.event_id: retained MLCF/PIOC event mismatch")
            if ref.get("document_id") != expected_doc_id:
                violations.append(f"{ref_path}.document_id: retained MLCF/PIOC document mismatch")
        if _canonical_hash(refs) != REAL_SOURCE_CHAIN_SHA256:
            violations.append(f"{path}: retained MLCF/PIOC source chain hash mismatch")
    return violations


def _observed_fact_refs(case: Mapping[str, Any], path: str) -> tuple[list[dict[str, Any]], list[str]]:
    refs_by_fact: dict[str, dict[str, Any]] = {}
    violations: list[str] = []
    facts = case.get("observed_facts")
    if not isinstance(facts, list):
        return [], [f"{path}.observed_facts: must be a list"]
    if len(facts) != len(REAL_SOURCE_CHAIN_IDS):
        violations.append(f"{path}.observed_facts: must contain exactly the retained MLCF/PIOC facts")
    for index, fact in enumerate(facts):
        fact_path = f"{path}.observed_facts[{index}]"
        if not isinstance(fact, Mapping):
            violations.append(f"{fact_path}: must be a mapping")
            continue
        violations.extend(_exact_keys(fact, _REAL_OBSERVED_FACT_KEYS, fact_path))
        fact_id = fact.get("fact_id")
        if not _nonempty(fact_id):
            violations.append(f"{fact_path}.fact_id: must be a non-empty string")
            continue
        if fact_id in refs_by_fact:
            violations.append(f"{fact_path}.fact_id: duplicate retained fact")
        values = fact.get("reported_values")
        if not isinstance(values, list):
            violations.append(f"{fact_path}.reported_values: must be a list")
        else:
            for value_index, value in enumerate(values):
                value_path = f"{fact_path}.reported_values[{value_index}]"
                if not isinstance(value, Mapping):
                    violations.append(f"{value_path}: must be a mapping")
                    continue
                violations.extend(_exact_keys(value, _REAL_REPORTED_VALUE_KEYS, value_path))
                if not _nonempty(value.get("label")) or not _nonempty(value.get("value")):
                    violations.append(f"{value_path}: label and value must be non-empty strings")
        evidence = fact.get("evidence")
        if not isinstance(evidence, list) or len(evidence) != 1:
            violations.append(f"{fact_path}.evidence: must contain exactly one evidence reference")
            continue
        ref, ref_violations = _strict_evidence_ref(evidence[0], f"{fact_path}.evidence[0]", require_text=True)
        violations.extend(ref_violations)
        if ref is None:
            continue
        if fact.get("source_event_id") != ref.get("event_id"):
            violations.append(f"{fact_path}.source_event_id: must match evidence event_id")
        if fact.get("document_id") != ref.get("document_id"):
            violations.append(f"{fact_path}.document_id: must match evidence document_id")
        if fact.get("event_date") != ref.get("document_published_at"):
            violations.append(f"{fact_path}.event_date: must equal evidence document_published_at")
        refs_by_fact[str(fact_id)] = ref
    expected_facts = {fact_id for fact_id, _, _ in REAL_SOURCE_CHAIN_IDS}
    if set(refs_by_fact) != expected_facts:
        violations.append(f"{path}.observed_facts: retained fact identity mismatch")
    refs: list[dict[str, Any]] = []
    for fact_id, expected_event_id, expected_doc_id in REAL_SOURCE_CHAIN_IDS:
        ref = refs_by_fact.get(fact_id)
        if ref is None:
            continue
        if ref.get("event_id") != expected_event_id:
            violations.append(f"{path}.observed_facts.{fact_id}.event_id: retained event mismatch")
        if ref.get("document_id") != expected_doc_id:
            violations.append(f"{path}.observed_facts.{fact_id}.document_id: retained document mismatch")
        refs.append(ref)
    return refs, violations


def _manifest_refs(manifest: Mapping[str, Any], path: str) -> tuple[list[dict[str, Any]], list[str]]:
    refs: list[dict[str, Any]] = []
    violations: list[str] = []
    violations.extend(_exact_keys(manifest, _REAL_MANIFEST_KEYS, path))
    expected = {
        "manifest_id": REAL_MANIFEST_ID,
        "case_id": CASE_ID,
        "case_status": "Observed",
        "acquirer_symbol": REAL_SYMBOL,
        "target_symbol": REAL_TARGET_SYMBOL,
        "status": "blocked_missing_inputs",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            violations.append(f"{path}.{key}: retained manifest identity mismatch")
    if _datetime(manifest.get("as_of")) is None:
        violations.append(f"{path}.as_of: must be an ISO datetime")
    known_fields = manifest.get("known_fields")
    if not isinstance(known_fields, Mapping):
        violations.append(f"{path}.known_fields: must be a mapping")
    else:
        violations.extend(_exact_keys(known_fields, _REAL_KNOWN_FIELDS_KEYS, f"{path}.known_fields"))
        if dict(known_fields) != REAL_KNOWN_FIELDS:
            violations.append(f"{path}.known_fields: retained known-field snapshot mismatch")
    pilot_status = manifest.get("pilot_status")
    if not isinstance(pilot_status, Mapping):
        violations.append(f"{path}.pilot_status: must be a mapping")
    else:
        violations.extend(_exact_keys(pilot_status, _REAL_PILOT_STATUS_KEYS, f"{path}.pilot_status"))
        if (
            pilot_status.get("target_symbol") != REAL_TARGET_SYMBOL
            or pilot_status.get("in_current_ci_pilot") is not False
            or pilot_status.get("pilot_symbols_source") != "state/company_profiles.json"
            or pilot_status.get("status") != "target_not_in_ci_pilot"
        ):
            violations.append(f"{path}.pilot_status: retained PIOC pilot boundary mismatch")
    missing_inputs = manifest.get("missing_inputs")
    if not isinstance(missing_inputs, list) or not missing_inputs:
        violations.append(f"{path}.missing_inputs: must be a non-empty list")
    else:
        missing_statuses: dict[str, str] = {}
        input_ids: list[str] = []
        for index, row in enumerate(missing_inputs):
            row_path = f"{path}.missing_inputs[{index}]"
            if not isinstance(row, Mapping):
                violations.append(f"{row_path}: must be a mapping")
                continue
            source_key = "source_paths" if "source_paths" in row else "source_path"
            allowed = set(_REAL_MISSING_INPUT_KEYS) | {source_key}
            violations.extend(_exact_keys(row, allowed, row_path))
            if ("source_path" in row) == ("source_paths" in row):
                violations.append(f"{row_path}: must carry exactly one source_path/source_paths field")
            if not _nonempty(row.get("input_id")) or not _nonempty(row.get("status")):
                violations.append(f"{row_path}: input_id and status must be non-empty strings")
            else:
                missing_statuses[str(row.get("input_id"))] = str(row.get("status"))
                input_ids.append(str(row.get("input_id")))
            if "required" not in row or row.get("required") in (None, "", [], {}):
                violations.append(f"{row_path}.required: exact producer requirement is required")
            if "present" not in row:
                violations.append(f"{row_path}.present: exact producer presence value is required")
            source_value = row.get(source_key)
            if source_key == "source_path" and not _nonempty(source_value):
                violations.append(f"{row_path}.source_path: must be a non-empty producer path")
            if source_key == "source_paths" and (
                not isinstance(source_value, list) or not source_value or any(not _nonempty(item) for item in source_value)
            ):
                violations.append(f"{row_path}.source_paths: must be a non-empty list of producer paths")
            if index < len(REAL_MISSING_INPUTS) and dict(row) != REAL_MISSING_INPUTS[index]:
                violations.append(f"{row_path}: exact producer-derived missing-input row mismatch")
        if input_ids != [row["input_id"] for row in REAL_MISSING_INPUTS] or missing_statuses != REAL_MISSING_INPUT_STATUSES:
            violations.append(f"{path}.missing_inputs: retained missing-input checklist mismatch")
    policy = manifest.get("formal_output_policy")
    if not isinstance(policy, Mapping):
        violations.append(f"{path}.formal_output_policy: must be a mapping")
    else:
        violations.extend(_exact_keys(policy, _REAL_FORMAL_OUTPUT_POLICY_KEYS, f"{path}.formal_output_policy"))
        if (
            policy.get("status") != "blocked"
            or policy.get("hard_block") is not True
            or policy.get("accepted_outputs") != []
            or policy.get("no_generic_economic_engine") is not True
            or policy.get("reported_fields_only") is not True
            or policy.get("block_reason") != "formal output remains blocked until every missing input is source-qualified and owner-reviewed through existing gates"
        ):
            violations.append(f"{path}.formal_output_policy: retained hard-block policy mismatch")
    evidence_refs = manifest.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        violations.append(f"{path}.evidence_refs: must be a list")
    else:
        if len(evidence_refs) != len(REAL_SOURCE_CHAIN_IDS):
            violations.append(f"{path}.evidence_refs: must contain exactly two retained references")
        for index, ref_value in enumerate(evidence_refs):
            ref, ref_violations = _strict_evidence_ref(
                ref_value, f"{path}.evidence_refs[{index}]", require_text=False
            )
            violations.extend(ref_violations)
            if ref is not None:
                refs.append(ref)
    return refs, violations


def validate_cement_input_readiness(value: Any, path: str = "cement_input_readiness") -> list[str]:
    """Validate the producer-owned MLCF readiness object as an exact closed contract."""
    violations: list[str] = []
    if not isinstance(value, Mapping):
        return [f"{path}: must be a mapping"]
    violations.extend(_exact_keys(value, READINESS_TOP_KEYS, path))
    if value.get("status") != "observed_only":
        violations.append(f"{path}.status: must equal observed_only")
    if value.get("kernel_activation") != "blocked":
        violations.append(f"{path}.kernel_activation: must equal blocked")
    attribution = value.get("attribution")
    if not isinstance(attribution, Mapping):
        violations.append(f"{path}.attribution: must be a mapping")
    else:
        violations.extend(_exact_keys(attribution, set(READINESS_ATTRIBUTION), f"{path}.attribution"))
        if dict(attribution) != READINESS_ATTRIBUTION:
            violations.append(f"{path}.attribution: exact MLCF/PIOC attribution required")
    joins = value.get("source_join")
    if not isinstance(joins, list) or len(joins) != len(READINESS_SOURCE_JOIN):
        violations.append(f"{path}.source_join: must contain exactly two ordered rows")
    else:
        for index, row in enumerate(joins):
            row_path = f"{path}.source_join[{index}]"
            if not isinstance(row, Mapping):
                violations.append(f"{row_path}: must be a mapping")
                continue
            violations.extend(_exact_keys(row, READINESS_SOURCE_JOIN_KEYS, row_path))
            expected = READINESS_SOURCE_JOIN[index]
            if dict(row) != expected:
                violations.append(f"{row_path}: exact retained source join mismatch")
            if not isinstance(row.get("page"), int) or isinstance(row.get("page"), bool) or row.get("page") <= 0:
                violations.append(f"{row_path}.page: must be a positive integer")
            for key in ("content_sha256", "evidence_sha256"):
                if not isinstance(row.get(key), str) or _HASH_RE.fullmatch(row.get(key, "")) is None:
                    violations.append(f"{row_path}.{key}: must be a 64-character hex hash")
            for key in ("effective_date", "available_on"):
                if _date(row.get(key)) is None:
                    violations.append(f"{row_path}.{key}: must be an ISO date")
            if _datetime(row.get("published_at")) is None:
                violations.append(f"{row_path}.published_at: must be an ISO datetime")
    counters = value.get("financial_truth_counters")
    if not isinstance(counters, Mapping):
        violations.append(f"{path}.financial_truth_counters: must be a mapping")
    else:
        violations.extend(_exact_keys(counters, set(READINESS_COUNTERS), f"{path}.financial_truth_counters"))
        for section, expected in READINESS_COUNTERS.items():
            row_path = f"{path}.financial_truth_counters.{section}"
            row = counters.get(section)
            if not isinstance(row, Mapping):
                violations.append(f"{row_path}: must be a mapping")
                continue
            violations.extend(_exact_keys(row, set(expected), row_path))
            if dict(row) != expected:
                violations.append(f"{row_path}: exact producer counter required")
            if section != "share_count":
                if not isinstance(row.get("required"), int) or isinstance(row.get("required"), bool):
                    violations.append(f"{row_path}.required: must be an integer")
                if not isinstance(row.get("present"), int) or isinstance(row.get("present"), bool):
                    violations.append(f"{row_path}.present: must be an integer")
                periods = row.get("qualified_periods")
                if not isinstance(periods, list) or any(not isinstance(x, str) or _date(x) is None for x in (periods or [])):
                    violations.append(f"{row_path}.qualified_periods: must be an ordered ISO-date list")
            else:
                if row.get("available_on") is not None and _date(row.get("available_on")) is None:
                    violations.append(f"{row_path}.available_on: must be null or ISO date")
                if row.get("source") is not None and not isinstance(row.get("source"), str):
                    violations.append(f"{row_path}.source: must be null or string")
    requirements = value.get("event_specific_kernel_requirements")
    if not isinstance(requirements, Mapping):
        violations.append(f"{path}.event_specific_kernel_requirements: must be a mapping")
    else:
        violations.extend(_exact_keys(requirements, set(READINESS_REQUIREMENTS), f"{path}.event_specific_kernel_requirements"))
        for key in READINESS_REQUIREMENTS:
            row_path = f"{path}.event_specific_kernel_requirements.{key}"
            row = requirements.get(key)
            if not isinstance(row, Mapping):
                violations.append(f"{row_path}: must be a mapping")
                continue
            violations.extend(_exact_keys(row, set(READINESS_REQUIREMENT_RECORD), row_path))
            if dict(row) != READINESS_REQUIREMENT_RECORD:
                violations.append(f"{row_path}: exact null source-labelled requirement required")
    guardrails = value.get("guardrails")
    if not isinstance(guardrails, Mapping):
        violations.append(f"{path}.guardrails: must be a mapping")
    else:
        violations.extend(_exact_keys(guardrails, set(READINESS_GUARDRAILS), f"{path}.guardrails"))
        if dict(guardrails) != READINESS_GUARDRAILS:
            violations.append(f"{path}.guardrails: exact guardrails required")
    return sorted(set(violations))


def retained_real_source_lineage(
    intelligence_case: Mapping[str, Any],
    readiness_manifest: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return exact retained MLCF/PIOC lineage rows, or named violations."""
    if not isinstance(intelligence_case, Mapping):
        return [], ["intelligence_case: must be a mapping"]
    if not isinstance(readiness_manifest, Mapping):
        return [], ["readiness_manifest: must be a mapping"]
    violations: list[str] = []
    case = intelligence_case
    manifest = readiness_manifest
    violations.extend(_exact_keys(case, _REAL_CASE_KEYS, "intelligence_case"))
    violations.extend(validate_cement_input_readiness(case.get("cement_input_readiness")))
    if isinstance(case.get("cement_input_readiness"), Mapping):
        if case.get("cement_input_readiness") != {
            "status": "observed_only", "kernel_activation": "blocked",
            "attribution": READINESS_ATTRIBUTION,
            "source_join": list(READINESS_SOURCE_JOIN),
            "financial_truth_counters": READINESS_COUNTERS,
            "event_specific_kernel_requirements": {
                key: dict(READINESS_REQUIREMENT_RECORD) for key in READINESS_REQUIREMENTS
            },
            "guardrails": READINESS_GUARDRAILS,
        }:
            violations.append("intelligence_case.cement_input_readiness: must equal producer-derived readiness")
    case_expected = {
        "case_id": CASE_ID,
        "symbol": REAL_SYMBOL,
        "target_symbol": REAL_TARGET_SYMBOL,
        "case_family": REAL_CASE_FAMILY,
        "case_type": REAL_CASE_TYPE,
        "status": "Observed",
        "epistemic_type": "reported_fact",
    }
    for key, value in case_expected.items():
        if case.get(key) != value:
            violations.append(f"intelligence_case.{key}: retained case identity mismatch")
    if _datetime(case.get("as_of")) is None:
        violations.append("intelligence_case.as_of: must be an ISO datetime")
    fact_refs, fact_violations = _observed_fact_refs(case, "intelligence_case")
    lineage_refs, lineage_violations = _raw_source_refs(
        case.get("source_lineage"), "intelligence_case.source_lineage", require_text=True
    )
    manifest_refs, manifest_violations = _manifest_refs(manifest, "readiness_manifest")
    violations.extend(fact_violations)
    violations.extend(lineage_violations)
    violations.extend(manifest_violations)
    if fact_refs and lineage_refs and lineage_refs != fact_refs:
        violations.append("intelligence_case.source_lineage: must exactly match observed_facts evidence")
    if fact_refs and manifest_refs and manifest_refs != [_manifest_ref(ref) for ref in fact_refs]:
        violations.append("readiness_manifest.evidence_refs: must exactly match retained observed evidence")
    if fact_refs and _canonical_hash(fact_refs) != REAL_SOURCE_CHAIN_SHA256:
        violations.append("intelligence_case.observed_facts: retained source chain hash mismatch")
    if violations:
        return [], sorted(set(violations))
    return [
        {"kind": "evidence", "document_id": ref["document_id"], "source_ref": copy.deepcopy(ref)}
        for ref in fact_refs
    ], []


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
    elif status == "blocked":
        violations.extend(_real_lineage_violations(envelope.get("input_lineage"), "input_lineage"))

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
