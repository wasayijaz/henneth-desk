"""Strict envelope contract for the MARI E&P case-run adapter.

The adapter is allowed to prove wiring into ``enp_event_engine``. It is not a
forecast, valuation, recommendation, or publication activator. The retained
MARI path remains blocked until source-grounded E&P operands and financial
truth are present. Computed scenario runs are permitted only when the envelope
is marked as a synthetic fixture.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any, Mapping

import enp_event_contract
import enp_event_engine
import mari_enp_hypothesis_contract


SCHEMA_VERSION = "mari_enp_case_run_envelope_v1"
ADAPTER_VERSION = "mari_enp_case_run_adapter_v1"
CASE_ID = "case_mari_offshore_exploration_blocks_observed_v1"
SYMBOL = "MARI"
CASE_FAMILY = "e_and_p"
SCENARIO_LABELS = ("bear", "base", "bull")

ALLOWED_ENGINE_INPUTS = frozenset({
    "working_interest_pct",
    "consideration_pkr",
    "consideration_non_recoverable",
    "consideration_quarter_end",
    "spend_schedule",
    "first_production_quarter_end",
    "production_horizon_quarters",
    "initial_production_boe_pd",
    "quarterly_decline_pct",
    "oil_share_pct",
    "oil_price_usd_bbl",
    "gas_price_usd_mmbtu",
    "gas_mmbtu_per_boe",
    "fx_pkr_usd",
    "opex_usd_boe",
    "royalty_pct",
    "effective_tax_pct",
    "discount_rate_pct_annual",
    "geological_success_pct",
    "commercial_success_pct",
    "shares_out",
    "market_gap_pkr",
})

_ENVELOPE_KEYS = frozenset({
    "schema_version",
    "adapter_version",
    "status",
    "fixture_only",
    "case_id",
    "symbol",
    "case_family",
    "hypothesis_linkage",
    "scenario_runs",
    "blocked_reasons",
    "input_lineage",
    "analogue_readiness",
    "formal_output_readiness",
    "policy",
})
_HYPOTHESIS_KEYS = frozenset({
    "status",
    "source_contract",
    "hypothesis_ids",
    "exclusive_group",
    "observed_event_status",
})
_RUN_KEYS = frozenset({
    "case_label",
    "status",
    "fixture_only",
    "engine_version",
    "formula_id",
    "contract_version",
    "input_sha256",
    "input_fields",
    "quarterly_schedule_rows",
    "values",
    "per_share",
    "probabilities",
    "blocked_reasons",
})
_LINEAGE_KEYS = frozenset({
    "scope",
    "case_label",
    "field",
    "status",
    "label_type",
    "available_on",
    "value",
    "source_ref",
    "analyst_ref",
})
_ANALOGUE_KEYS = frozenset({
    "status",
    "target_event_id",
    "readiness_status",
    "aggregate_ready_horizons",
    "next_required_evidence",
    "blocked_states",
})
_FORMAL_KEYS = frozenset({
    "status",
    "financial_truth_status",
    "financial_truth_reason",
    "products",
})
_FORMAL_PRODUCT_KEYS = frozenset({"product", "status", "blocked_reason"})
_POLICY_KEYS = frozenset({
    "research_only",
    "no_advice",
    "no_forecast_activation",
    "no_valuation_activation",
    "no_market_expectations_activation",
    "synthetic_numbers_fixture_only",
    "real_retained_path_zero_numeric_outputs",
})
_FORBIDDEN_PHRASES = (
    "buy",
    "sell",
    "accumulate",
    "target price",
    "price target",
    "you should",
)
_FORBIDDEN_KEY_FRAGMENTS = (
    "target_price",
    "price_target",
    "recommendation",
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_engine_case(case: Mapping[str, Any]) -> list[str]:
    """Strict wrapper around the generic E&P engine contract."""
    violations: list[str] = []
    if not isinstance(case, Mapping):
        return ["case: must be a mapping"]
    inputs = case.get("inputs")
    if not isinstance(inputs, Mapping):
        violations.append("inputs: must be a mapping")
    else:
        for field in sorted(set(inputs) - ALLOWED_ENGINE_INPUTS):
            violations.append(f"{field}: unknown E&P input field")
    violations.extend(enp_event_contract.validate_case(case))
    return violations


def validate_envelope(envelope: Mapping[str, Any]) -> list[str]:
    """Return named violations for the narrow adapter output envelope."""
    if not isinstance(envelope, Mapping):
        return ["envelope: must be a mapping"]
    violations: list[str] = []
    violations.extend(_keys(envelope, _ENVELOPE_KEYS, "envelope"))
    violations.extend(_json_finite(envelope, "envelope"))
    violations.extend(_forbidden_language(envelope, "envelope"))

    if envelope.get("schema_version") != SCHEMA_VERSION:
        violations.append(f"schema_version: must equal {SCHEMA_VERSION}")
    if envelope.get("adapter_version") != ADAPTER_VERSION:
        violations.append(f"adapter_version: must equal {ADAPTER_VERSION}")
    if envelope.get("case_id") != CASE_ID:
        violations.append(f"case_id: must equal {CASE_ID}")
    if envelope.get("symbol") != SYMBOL:
        violations.append(f"symbol: must equal {SYMBOL}")
    if envelope.get("case_family") != CASE_FAMILY:
        violations.append(f"case_family: must equal {CASE_FAMILY}")
    if envelope.get("status") not in {"blocked", "computed_fixture"}:
        violations.append("status: must be blocked or computed_fixture")
    fixture_only = envelope.get("fixture_only")
    if not isinstance(fixture_only, bool):
        violations.append("fixture_only: must be a boolean")
    elif envelope.get("status") == "computed_fixture" and fixture_only is not True:
        violations.append("fixture_only: computed_fixture envelopes must be fixture-only")
    elif envelope.get("status") == "blocked" and fixture_only is not False:
        violations.append("fixture_only: retained blocked envelopes must not be fixtures")

    hypothesis = envelope.get("hypothesis_linkage")
    if isinstance(hypothesis, Mapping):
        violations.extend(_keys(hypothesis, _HYPOTHESIS_KEYS, "hypothesis_linkage"))
        if tuple(hypothesis.get("hypothesis_ids") or ()) != mari_enp_hypothesis_contract.HYPOTHESIS_IDS:
            violations.append("hypothesis_linkage.hypothesis_ids: must match MARI hypothesis contract order")
        if hypothesis.get("source_contract") != mari_enp_hypothesis_contract.CONTRACT_VERSION:
            violations.append("hypothesis_linkage.source_contract: must match hypothesis contract")
        if hypothesis.get("observed_event_status") != mari_enp_hypothesis_contract.EVENT_STATUS:
            violations.append("hypothesis_linkage.observed_event_status: must equal observed")
    else:
        violations.append("hypothesis_linkage: must be a mapping")

    runs = envelope.get("scenario_runs")
    if not isinstance(runs, list):
        violations.append("scenario_runs: must be a list")
        runs = []
    if [run.get("case_label") for run in runs if isinstance(run, Mapping)] != list(SCENARIO_LABELS):
        violations.append("scenario_runs: must contain exactly bear, base, bull in order")
    for index, run in enumerate(runs):
        if not isinstance(run, Mapping):
            violations.append(f"scenario_runs[{index}]: must be a mapping")
            continue
        violations.extend(_validate_run(run, f"scenario_runs[{index}]", bool(fixture_only)))

    blocked_reasons = envelope.get("blocked_reasons")
    if not isinstance(blocked_reasons, list) or any(not _nonempty(item) for item in blocked_reasons):
        violations.append("blocked_reasons: must be a list of non-empty strings")
    elif blocked_reasons != sorted(set(blocked_reasons)):
        violations.append("blocked_reasons: must be sorted and deduplicated")
    if envelope.get("status") == "blocked" and not blocked_reasons:
        violations.append("blocked_reasons: retained blocked envelope requires reasons")

    lineage = envelope.get("input_lineage")
    if not isinstance(lineage, list):
        violations.append("input_lineage: must be a list")
        lineage = []
    for index, entry in enumerate(lineage):
        if not isinstance(entry, Mapping):
            violations.append(f"input_lineage[{index}]: must be a mapping")
            continue
        violations.extend(_validate_lineage(entry, f"input_lineage[{index}]"))

    analogue = envelope.get("analogue_readiness")
    if isinstance(analogue, Mapping):
        violations.extend(_keys(analogue, _ANALOGUE_KEYS, "analogue_readiness"))
        horizons = analogue.get("aggregate_ready_horizons")
        if not isinstance(horizons, list) or any(not isinstance(item, str) for item in horizons):
            violations.append("analogue_readiness.aggregate_ready_horizons: must be a list of strings")
    else:
        violations.append("analogue_readiness: must be a mapping")

    formal = envelope.get("formal_output_readiness")
    if isinstance(formal, Mapping):
        violations.extend(_keys(formal, _FORMAL_KEYS, "formal_output_readiness"))
        products = formal.get("products")
        if not isinstance(products, list):
            violations.append("formal_output_readiness.products: must be a list")
            products = []
        for index, product in enumerate(products):
            if not isinstance(product, Mapping):
                violations.append(f"formal_output_readiness.products[{index}]: must be a mapping")
                continue
            violations.extend(_keys(product, _FORMAL_PRODUCT_KEYS, f"formal_output_readiness.products[{index}]"))
    else:
        violations.append("formal_output_readiness: must be a mapping")

    policy = envelope.get("policy")
    if isinstance(policy, Mapping):
        violations.extend(_keys(policy, _POLICY_KEYS, "policy"))
        for key in _POLICY_KEYS:
            if policy.get(key) is not True:
                violations.append(f"policy.{key}: must be true")
    else:
        violations.append("policy: must be a mapping")

    if envelope.get("status") == "blocked":
        for index, run in enumerate(runs):
            if isinstance(run, Mapping) and _has_numeric_outputs(run):
                violations.append(f"scenario_runs[{index}]: retained blocked run must carry zero numeric outputs")
    return sorted(set(violations))


def _validate_run(run: Mapping[str, Any], prefix: str, fixture_only: bool) -> list[str]:
    violations = _keys(run, _RUN_KEYS, prefix)
    if run.get("case_label") not in SCENARIO_LABELS:
        violations.append(f"{prefix}.case_label: must be bear, base or bull")
    status = run.get("status")
    if status not in {"blocked", "computed"}:
        violations.append(f"{prefix}.status: must be blocked or computed")
    if run.get("fixture_only") is not fixture_only:
        violations.append(f"{prefix}.fixture_only: must match envelope fixture_only")
    if run.get("engine_version") != enp_event_engine.ENGINE_VERSION:
        violations.append(f"{prefix}.engine_version: must match E&P engine")
    if run.get("formula_id") != enp_event_engine.FORMULA_ID:
        violations.append(f"{prefix}.formula_id: must match E&P formula")
    if run.get("contract_version") != enp_event_contract.CONTRACT_VERSION:
        violations.append(f"{prefix}.contract_version: must match E&P contract")
    input_sha = run.get("input_sha256")
    if status == "computed":
        if not fixture_only:
            violations.append(f"{prefix}: retained real path cannot be computed by this adapter")
        if not (isinstance(input_sha, str) and re.fullmatch(r"[0-9a-f]{64}", input_sha)):
            violations.append(f"{prefix}.input_sha256: computed run requires a sha256")
        if not isinstance(run.get("values"), Mapping):
            violations.append(f"{prefix}.values: computed run requires engine values")
        if not isinstance(run.get("probabilities"), Mapping):
            violations.append(f"{prefix}.probabilities: computed run requires engine probabilities")
        rows = run.get("quarterly_schedule_rows")
        if isinstance(rows, bool) or not isinstance(rows, int) or rows < 1:
            violations.append(f"{prefix}.quarterly_schedule_rows: computed run requires a positive integer")
    elif status == "blocked":
        if input_sha is not None:
            violations.append(f"{prefix}.input_sha256: blocked run must be null")
        if run.get("values") is not None or run.get("per_share") is not None or run.get("probabilities") is not None:
            violations.append(f"{prefix}: blocked run must not carry numeric sections")
        if run.get("quarterly_schedule_rows") != 0:
            violations.append(f"{prefix}.quarterly_schedule_rows: blocked run must be 0")
    input_fields = run.get("input_fields")
    if not isinstance(input_fields, list) or any(not isinstance(item, str) for item in input_fields):
        violations.append(f"{prefix}.input_fields: must be a list of strings")
    blocked = run.get("blocked_reasons")
    if not isinstance(blocked, list) or any(not _nonempty(item) for item in blocked):
        violations.append(f"{prefix}.blocked_reasons: must be a list of non-empty strings")
    elif blocked != sorted(set(blocked)):
        violations.append(f"{prefix}.blocked_reasons: must be sorted and deduplicated")
    return violations


def _validate_lineage(entry: Mapping[str, Any], prefix: str) -> list[str]:
    violations = _keys(entry, _LINEAGE_KEYS, prefix)
    if entry.get("case_label") is not None and entry.get("case_label") not in SCENARIO_LABELS:
        violations.append(f"{prefix}.case_label: must be null, bear, base or bull")
    if not _nonempty(entry.get("scope")):
        violations.append(f"{prefix}.scope: must be a non-empty string")
    if not _nonempty(entry.get("field")):
        violations.append(f"{prefix}.field: must be a non-empty string")
    if not _nonempty(entry.get("status")):
        violations.append(f"{prefix}.status: must be a non-empty string")
    label_type = entry.get("label_type")
    if label_type not in {"source", "analyst", "missing"}:
        violations.append(f"{prefix}.label_type: must be source, analyst or missing")
    available_on = entry.get("available_on")
    if available_on is not None and not (isinstance(available_on, str) and _DATE_RE.fullmatch(available_on)):
        violations.append(f"{prefix}.available_on: must be null or an ISO date")
    if label_type == "source":
        ref = entry.get("source_ref")
        if not isinstance(ref, Mapping) or not _nonempty(ref.get("id")) or not _nonempty(ref.get("label")):
            violations.append(f"{prefix}.source_ref: source lineage requires id and label")
    if label_type == "analyst":
        ref = entry.get("analyst_ref")
        if not isinstance(ref, Mapping) or not _nonempty(ref.get("note_id")) or not _nonempty(ref.get("note")):
            violations.append(f"{prefix}.analyst_ref: analyst lineage requires note_id and note")
    if label_type == "missing" and (entry.get("source_ref") is not None or entry.get("analyst_ref") is not None):
        violations.append(f"{prefix}: missing lineage must not carry a provenance ref")
    return violations


def _keys(mapping: Mapping[str, Any], expected: frozenset[str], prefix: str) -> list[str]:
    violations: list[str] = []
    for key in sorted(set(mapping) - expected):
        violations.append(f"{prefix}.{key}: unknown field")
    for key in sorted(expected - set(mapping)):
        violations.append(f"{prefix}.{key}: missing required field")
    return violations


def _json_finite(value: Any, prefix: str) -> list[str]:
    violations: list[str] = []
    try:
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError):
        violations.append(f"{prefix}: must be JSON-serializable and finite")
    for path, item in _walk(value, prefix):
        if isinstance(item, float) and not math.isfinite(item):
            violations.append(f"{path}: non-finite number")
    return violations


def _forbidden_language(value: Any, prefix: str) -> list[str]:
    violations: list[str] = []
    text = json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).lower()
    for phrase in _FORBIDDEN_PHRASES:
        if phrase in text:
            violations.append(f"{prefix}: advice or target-price phrase leaked: {phrase}")
    for path, key, _item in _walk_items(value, prefix):
        lowered = str(key).lower()
        if any(fragment in lowered for fragment in _FORBIDDEN_KEY_FRAGMENTS):
            violations.append(f"{path}.{key}: advice or target-price key leaked")
    return violations


def _has_numeric_outputs(run: Mapping[str, Any]) -> bool:
    return any(run.get(field) is not None for field in ("values", "per_share", "probabilities")) or run.get("quarterly_schedule_rows") != 0


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _walk(value: Any, path: str):
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}.{key}"
            yield child, item
            yield from _walk(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child = f"{path}[{index}]"
            yield child, item
            yield from _walk(item, child)


def _walk_items(value: Any, path: str):
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield path, key, item
            yield from _walk_items(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_items(item, f"{path}[{index}]")
