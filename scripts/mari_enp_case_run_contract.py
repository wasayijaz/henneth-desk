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
import hashlib
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
    "operator_status",
    "shares_out",
    "market_gap_pkr",
})

_ENVELOPE_KEYS = frozenset({
    "schema_version",
    "adapter_version",
    "status",
    "fixture_only",
    "fixture_identity",
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
_FIXTURE_IDENTITY_KEYS = frozenset({"id", "spec_sha256"})
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
    "fixture_hash",
    "input_fields",
    "quarterly_schedule",
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
_FIXTURE_ID = "mari_enp_synthetic_fixture_v1"
_FIXTURE_SPEC_SHA256 = hashlib.sha256(_FIXTURE_ID.encode("ascii")).hexdigest()
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
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_COMPUTED_QUARTERLY_ROWS = 8
_COMPUTED_INPUT_FIELDS = tuple(sorted(
    field for field in ALLOWED_ENGINE_INPUTS
    if field not in {"consideration_non_recoverable", "consideration_quarter_end", "market_gap_pkr"}
))
_VALUE_KEYS = frozenset({
    "dry_hole_npv_pkr",
    "unrisked_commercial_npv_pkr",
    "risked_npv_pkr",
    "p_success_pct",
})
_PER_SHARE_KEYS = frozenset({"risked_pkr", "unrisked_pkr"})
_PROBABILITY_KEYS = frozenset({
    "break_even_success_pct",
    "market_implied_success_pct",
    "market_implied_missing",
})
_PROBABILITY_OPTIONAL_KEYS = frozenset({"break_even_note", "market_implied_note"})
_SCHEDULE_ROW_KEYS = frozenset({
    "quarter_end",
    "phase",
    "production_boe",
    "gross_revenue_pkr",
    "royalty_pkr",
    "opex_pkr",
    "tax_pkr",
    "net_cash_flow_pkr",
    "discount_factor",
    "discounted_cash_flow_pkr",
})
_SOURCE_REF_KEYS = frozenset({
    "id",
    "label",
    "url",
    "path",
    "page",
    "content_sha256",
    "evidence_sha256",
    "event_id",
    "date",
})
_SOURCE_REF_REQUIRED = frozenset({"id", "label"})
_RETAINED_SOURCE_RECEIPTS = {
    "psx:265594": {
        "url": "https://dps.psx.com.pk/download/document/265594.pdf",
        "path": None,
        "page": 3,
        "content_sha256": "cdc3f69157f5e5803238ba347ecb4e96f7297479df87d345739896913de8aae4",
        "evidence_sha256": "56c298f041bd756cd184e75d122f5a95cc6879f4b5fa037786007948b76d3d83",
        "date": "2025-11-13",
        "event_id": "evt_3d1dae7553f73da60ba3",
    },
}
_RETAINED_OPERAND_SOURCE_IDS = {
    "block_identity": "psx:265594",
}
_ANALYST_REF_KEYS = frozenset({"note_id", "note"})
_BLOCKED_STATE_KEYS = frozenset({"status", "reason"})
_FORMAL_PRODUCT_ORDER = ("financial_forecasts", "formal_valuations", "market_expectations")


def validate_engine_case(case: Mapping[str, Any]) -> list[str]:
    """Strict wrapper around the generic E&P engine contract."""
    violations: list[str] = []
    if type(case) is not dict:
        return ["case: must be an exact mapping"]
    inputs = case.get("inputs")
    if type(inputs) is not dict:
        violations.append("inputs: must be an exact mapping")
    else:
        for field in sorted(set(inputs) - ALLOWED_ENGINE_INPUTS):
            violations.append(f"{field}: unknown E&P input field")
    violations.extend(enp_event_contract.validate_case(case))
    return violations


def validate_envelope(envelope: Mapping[str, Any]) -> list[str]:
    """Return named violations for the narrow adapter output envelope."""
    if not type(envelope) is dict:
        return ["envelope: must be a mapping"]
    violations: list[str] = []
    violations.extend(_keys(envelope, _ENVELOPE_KEYS, "envelope"))
    violations.extend(_json_finite(envelope, "envelope"))
    violations.extend(_forbidden_language(envelope, "envelope"))

    fixture_identity = envelope.get("fixture_identity")
    if envelope.get("status") == "computed_fixture":
        if not type(fixture_identity) is dict:
            violations.append("fixture_identity: computed fixture requires identity")
        else:
            violations.extend(_keys(fixture_identity, _FIXTURE_IDENTITY_KEYS, "fixture_identity"))
            if fixture_identity.get("id") != _FIXTURE_ID:
                violations.append("fixture_identity.id: must match deterministic fixture")
            if fixture_identity.get("spec_sha256") != _FIXTURE_SPEC_SHA256:
                violations.append("fixture_identity.spec_sha256: must match deterministic fixture")
    elif fixture_identity is not None:
        violations.append("fixture_identity: retained blocked envelope must be null")

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
    if type(hypothesis) is dict:
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
    if not type(runs) is list:
        violations.append("scenario_runs: must be a list")
        runs = []
    if [run.get("case_label") for run in runs if type(run) is dict] != list(SCENARIO_LABELS):
        violations.append("scenario_runs: must contain exactly bear, base, bull in order")
    for index, run in enumerate(runs):
        if not type(run) is dict:
            violations.append(f"scenario_runs[{index}]: must be a mapping")
            continue
        violations.extend(_validate_run(run, f"scenario_runs[{index}]", bool(fixture_only)))

    blocked_reasons = envelope.get("blocked_reasons")
    if not type(blocked_reasons) is list or any(not _nonempty(item) for item in blocked_reasons):
        violations.append("blocked_reasons: must be a list of non-empty strings")
    elif blocked_reasons != sorted(set(blocked_reasons)):
        violations.append("blocked_reasons: must be sorted and deduplicated")
    if envelope.get("status") == "blocked" and not blocked_reasons:
        violations.append("blocked_reasons: retained blocked envelope requires reasons")

    lineage = envelope.get("input_lineage")
    if not type(lineage) is list:
        violations.append("input_lineage: must be a list")
        lineage = []
    for index, entry in enumerate(lineage):
        if not type(entry) is dict:
            violations.append(f"input_lineage[{index}]: must be a mapping")
            continue
        violations.extend(_validate_lineage(entry, f"input_lineage[{index}]"))
    # Lineage is an evidence ledger, not a bag of attestations.  Reject exact
    # duplicate rows and duplicate retained operand fields so callers cannot
    # inflate provenance coverage or create ambiguous field-to-receipt binds.
    seen_rows: set[str] = set()
    seen_operands: set[str] = set()
    for index, entry in enumerate(lineage):
        if not type(entry) is dict:
            continue
        try:
            row_key = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        except (TypeError, ValueError):
            continue
        if row_key in seen_rows:
            violations.append(f"input_lineage[{index}]: duplicate lineage row")
        seen_rows.add(row_key)
        if entry.get("scope") == "retained_ep_operand":
            operand_key = str(entry.get("field"))
            if operand_key in seen_operands:
                violations.append(f"input_lineage[{index}]: duplicate retained operand field")
            seen_operands.add(operand_key)
    violations.extend(_validate_lineage_alignment(runs, lineage, bool(fixture_only), envelope.get("status")))

    analogue = envelope.get("analogue_readiness")
    if type(analogue) is dict:
        violations.extend(_keys(analogue, _ANALOGUE_KEYS, "analogue_readiness"))
        if analogue.get("target_event_id") != "evt_3d1dae7553f73da60ba3":
            violations.append("analogue_readiness.target_event_id: must match MARI offshore event")
        if analogue.get("status") not in {"benchmarks_available", "fixture_not_real_analogue_evidence"}:
            violations.append("analogue_readiness.status: unexpected readiness status")
        if not _nonempty(analogue.get("readiness_status")):
            violations.append("analogue_readiness.readiness_status: must be a non-empty string")
        horizons = analogue.get("aggregate_ready_horizons")
        if not type(horizons) is list or any(not isinstance(item, str) for item in horizons):
            violations.append("analogue_readiness.aggregate_ready_horizons: must be a list of strings")
        violations.extend(_validate_blocked_states(analogue.get("blocked_states"), "analogue_readiness.blocked_states"))
    else:
        violations.append("analogue_readiness: must be a mapping")

    formal = envelope.get("formal_output_readiness")
    if type(formal) is dict:
        violations.extend(_keys(formal, _FORMAL_KEYS, "formal_output_readiness"))
        if formal.get("status") not in {"blocked", "blocked_fixture_only"}:
            violations.append("formal_output_readiness.status: must be blocked or blocked_fixture_only")
        if not _nonempty(formal.get("financial_truth_status")):
            violations.append("formal_output_readiness.financial_truth_status: must be a non-empty string")
        if formal.get("financial_truth_reason") is not None and not _nonempty(formal.get("financial_truth_reason")):
            violations.append("formal_output_readiness.financial_truth_reason: must be null or a non-empty string")
        products = formal.get("products")
        if not type(products) is list:
            violations.append("formal_output_readiness.products: must be a list")
            products = []
        if [product.get("product") for product in products if type(product) is dict] != list(_FORMAL_PRODUCT_ORDER):
            violations.append("formal_output_readiness.products: must contain the three formal products in order")
        for index, product in enumerate(products):
            if not type(product) is dict:
                violations.append(f"formal_output_readiness.products[{index}]: must be a mapping")
                continue
            violations.extend(_keys(product, _FORMAL_PRODUCT_KEYS, f"formal_output_readiness.products[{index}]"))
            if product.get("status") not in {"blocked", "blocked_fixture_only"}:
                violations.append(f"formal_output_readiness.products[{index}].status: must be blocked or blocked_fixture_only")
            if not _nonempty(product.get("blocked_reason")):
                violations.append(f"formal_output_readiness.products[{index}].blocked_reason: must be a non-empty string")
    else:
        violations.append("formal_output_readiness: must be a mapping")

    policy = envelope.get("policy")
    if type(policy) is dict:
        violations.extend(_keys(policy, _POLICY_KEYS, "policy"))
        for key in _POLICY_KEYS:
            if policy.get(key) is not True:
                violations.append(f"policy.{key}: must be true")
    else:
        violations.append("policy: must be a mapping")

    if envelope.get("status") == "blocked":
        for index, run in enumerate(runs):
            if type(run) is dict and _has_numeric_outputs(run):
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
        fixture_hash = run.get("fixture_hash")
        expected_fixture_hash = fixture_receipt_hash(run)
        if fixture_hash != expected_fixture_hash:
            violations.append(f"{prefix}.fixture_hash: must bind deterministic fixture inputs")
        values = run.get("values")
        if type(values) is dict:
            violations.extend(_validate_values(values, f"{prefix}.values"))
        else:
            violations.append(f"{prefix}.values: computed run requires engine values")
        per_share = run.get("per_share")
        if type(per_share) is dict:
            violations.extend(_validate_per_share(per_share, f"{prefix}.per_share"))
        else:
            violations.append(f"{prefix}.per_share: computed run requires per-share engine values")
        probabilities = run.get("probabilities")
        if type(probabilities) is dict:
            violations.extend(_validate_probabilities(probabilities, f"{prefix}.probabilities"))
        else:
            violations.append(f"{prefix}.probabilities: computed run requires engine probabilities")
        rows = run.get("quarterly_schedule_rows")
        if rows != _COMPUTED_QUARTERLY_ROWS:
            violations.append(f"{prefix}.quarterly_schedule_rows: computed fixture must equal {_COMPUTED_QUARTERLY_ROWS}")
        schedule = run.get("quarterly_schedule")
        if type(schedule) is list:
            violations.extend(_validate_schedule(schedule, f"{prefix}.quarterly_schedule"))
        else:
            violations.append(f"{prefix}.quarterly_schedule: computed run requires engine schedule rows")
    elif status == "blocked":
        if input_sha is not None:
            violations.append(f"{prefix}.input_sha256: blocked run must be null")
        if run.get("fixture_hash") is not None:
            violations.append(f"{prefix}.fixture_hash: blocked run must be null")
        if run.get("values") is not None or run.get("per_share") is not None or run.get("probabilities") is not None:
            violations.append(f"{prefix}: blocked run must not carry numeric sections")
        if run.get("quarterly_schedule_rows") != 0:
            violations.append(f"{prefix}.quarterly_schedule_rows: blocked run must be 0")
        if run.get("quarterly_schedule") != []:
            violations.append(f"{prefix}.quarterly_schedule: blocked run must be empty")
    input_fields = run.get("input_fields")
    if not type(input_fields) is list or any(not isinstance(item, str) for item in input_fields):
        violations.append(f"{prefix}.input_fields: must be a list of strings")
    elif status == "computed" and tuple(input_fields) != _COMPUTED_INPUT_FIELDS:
        violations.append(f"{prefix}.input_fields: computed run must list the complete E&P fixture input fields")
    elif status == "blocked" and input_fields != []:
        violations.append(f"{prefix}.input_fields: blocked run must have no input fields")
    blocked = run.get("blocked_reasons")
    if not type(blocked) is list or any(not _nonempty(item) for item in blocked):
        violations.append(f"{prefix}.blocked_reasons: must be a list of non-empty strings")
    elif blocked != sorted(set(blocked)):
        violations.append(f"{prefix}.blocked_reasons: must be sorted and deduplicated")
    elif status == "computed" and blocked:
        violations.append(f"{prefix}.blocked_reasons: computed run must not carry blocked reasons")
    elif status == "blocked" and not blocked:
        violations.append(f"{prefix}.blocked_reasons: blocked run requires reasons")
    return violations


def fixture_receipt_hash(run: Mapping[str, Any]) -> str:
    """Hash all computed fixture receipts so output edits cannot hide behind a flag swap."""
    payload = {key: run.get(key) for key in sorted(_RUN_KEYS - {"fixture_hash"})}
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(encoded).hexdigest()


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
        if available_on is None:
            violations.append(f"{prefix}.available_on: source lineage requires a retained date")
        ref = entry.get("source_ref")
        if type(ref) is dict:
            violations.extend(_validate_source_ref(ref, f"{prefix}.source_ref", available_on))
            if entry.get("scope") == "retained_ep_operand":
                expected_id = _RETAINED_OPERAND_SOURCE_IDS.get(entry.get("field"))
                if expected_id is None:
                    violations.append(
                        f"{prefix}.source_ref.id: no retained source is permitted for this operand"
                    )
                elif ref.get("id") != expected_id:
                    violations.append(
                        f"{prefix}.source_ref.id: does not match authoritative source for retained operand"
                    )
            if entry.get("scope") in {"retained_event_evidence", "retained_ep_operand"}:
                if ref.get("event_id") != "evt_3d1dae7553f73da60ba3":
                    violations.append(
                        f"{prefix}.source_ref.event_id: must bind canonical MARI offshore target event"
                    )
        else:
            violations.append(f"{prefix}.source_ref: source lineage requires id and label")
        if entry.get("analyst_ref") is not None:
            violations.append(f"{prefix}.analyst_ref: source lineage must not carry analyst_ref")
    if label_type == "analyst":
        ref = entry.get("analyst_ref")
        if type(ref) is dict:
            violations.extend(_validate_analyst_ref(ref, f"{prefix}.analyst_ref"))
        else:
            violations.append(f"{prefix}.analyst_ref: analyst lineage requires note_id and note")
        if entry.get("source_ref") is not None:
            violations.append(f"{prefix}.source_ref: analyst lineage must not carry source_ref")
    if label_type == "missing":
        if entry.get("value") is not None:
            violations.append(f"{prefix}.value: missing lineage must carry null value")
        if entry.get("source_ref") is not None or entry.get("analyst_ref") is not None:
            violations.append(f"{prefix}: missing lineage must not carry a provenance ref")
    return violations


def _validate_values(values: Mapping[str, Any], prefix: str) -> list[str]:
    violations = _keys(values, _VALUE_KEYS, prefix)
    for key in _VALUE_KEYS:
        if _finite(values.get(key)) is None:
            violations.append(f"{prefix}.{key}: must be a finite number")
    p_success = _finite(values.get("p_success_pct"))
    if p_success is not None and not 0.0 < p_success <= 100.0:
        violations.append(f"{prefix}.p_success_pct: must be in (0, 100]")
    return violations


def _validate_per_share(per_share: Mapping[str, Any], prefix: str) -> list[str]:
    violations = _keys(per_share, _PER_SHARE_KEYS, prefix)
    for key in _PER_SHARE_KEYS:
        if _finite(per_share.get(key)) is None:
            violations.append(f"{prefix}.{key}: must be a finite number")
    return violations


def _validate_probabilities(probabilities: Mapping[str, Any], prefix: str) -> list[str]:
    violations = _keys(
        probabilities,
        _PROBABILITY_KEYS,
        prefix,
        optional=_PROBABILITY_OPTIONAL_KEYS,
    )
    for key in ("break_even_success_pct", "market_implied_success_pct"):
        value = probabilities.get(key)
        if value is not None:
            number = _finite(value)
            if number is None:
                violations.append(f"{prefix}.{key}: must be null or a finite number")
            elif not 0.0 <= number <= 100.0:
                violations.append(f"{prefix}.{key}: must be in [0, 100]")
    missing = probabilities.get("market_implied_missing")
    if missing != ["market_gap_pkr"]:
        violations.append(f"{prefix}.market_implied_missing: must equal ['market_gap_pkr']")
    for key in _PROBABILITY_OPTIONAL_KEYS:
        if key in probabilities and not _nonempty(probabilities.get(key)):
            violations.append(f"{prefix}.{key}: must be a non-empty string when present")
    return violations


def _validate_schedule(schedule: list[Any], prefix: str) -> list[str]:
    violations: list[str] = []
    if len(schedule) != _COMPUTED_QUARTERLY_ROWS:
        violations.append(f"{prefix}: computed fixture must contain {_COMPUTED_QUARTERLY_ROWS} rows")
    previous_key: tuple[str, str] | None = None
    for index, row in enumerate(schedule):
        row_prefix = f"{prefix}[{index}]"
        if not type(row) is dict:
            violations.append(f"{row_prefix}: must be a mapping")
            continue
        violations.extend(_keys(row, _SCHEDULE_ROW_KEYS, row_prefix))
        quarter_end = row.get("quarter_end")
        if not enp_event_contract.is_quarter_end(quarter_end):
            violations.append(f"{row_prefix}.quarter_end: must be a quarter-end")
        phase = row.get("phase")
        if phase not in enp_event_contract.PHASES and phase != "production":
            violations.append(f"{row_prefix}.phase: must be exploration, appraisal, development or production")
        sort_key = (str(quarter_end), str(phase))
        if previous_key is not None and sort_key < previous_key:
            violations.append(f"{prefix}: rows must be sorted by quarter_end then phase")
        previous_key = sort_key
        production = row.get("production_boe")
        if phase == "production":
            if _finite(production) is None or float(production) <= 0.0:
                violations.append(f"{row_prefix}.production_boe: production rows require positive finite production")
        elif production is not None:
            violations.append(f"{row_prefix}.production_boe: non-production rows must be null")
        for key in (
            "gross_revenue_pkr",
            "royalty_pkr",
            "opex_pkr",
            "tax_pkr",
            "net_cash_flow_pkr",
            "discount_factor",
            "discounted_cash_flow_pkr",
        ):
            if _finite(row.get(key)) is None:
                violations.append(f"{row_prefix}.{key}: must be a finite number")
        factor = _finite(row.get("discount_factor"))
        net = _finite(row.get("net_cash_flow_pkr"))
        discounted = _finite(row.get("discounted_cash_flow_pkr"))
        if factor is not None and factor <= 0.0:
            violations.append(f"{row_prefix}.discount_factor: must be > 0")
        if factor is not None and net is not None and discounted is not None:
            if not math.isclose(discounted, net * factor, rel_tol=1e-9, abs_tol=1e-4):
                violations.append(f"{row_prefix}.discounted_cash_flow_pkr: must equal net_cash_flow_pkr * discount_factor")
    return violations


def _validate_source_ref(ref: Mapping[str, Any], prefix: str, available_on: Any = None) -> list[str]:
    violations = _keys(ref, _SOURCE_REF_REQUIRED, prefix, optional=_SOURCE_REF_KEYS - _SOURCE_REF_REQUIRED)
    for key in _SOURCE_REF_REQUIRED:
        if not _nonempty(ref.get(key)):
            violations.append(f"{prefix}.{key}: must be a non-empty string")
    source_id = ref.get("id")
    receipt = _RETAINED_SOURCE_RECEIPTS.get(source_id) if isinstance(source_id, str) else None
    if receipt is None:
        violations.append(f"{prefix}.id: must match an authoritative retained source receipt")
    if "url" in ref and ref.get("url") is not None and not _nonempty(ref.get("url")):
        violations.append(f"{prefix}.url: must be null or a non-empty string")
    if "path" in ref and ref.get("path") is not None and not _nonempty(ref.get("path")):
        violations.append(f"{prefix}.path: must be null or a non-empty string")
    if not (_nonempty(ref.get("url")) or _nonempty(ref.get("path"))):
        violations.append(f"{prefix}: authoritative source requires a URL or path")
    for key in ("content_sha256", "evidence_sha256"):
        value = ref.get(key)
        if value is not None and not (isinstance(value, str) and _SHA_RE.fullmatch(value)):
            violations.append(f"{prefix}.{key}: must be null or a sha256")
    if not (isinstance(ref.get("content_sha256"), str) and _SHA_RE.fullmatch(ref["content_sha256"])):
        violations.append(f"{prefix}.content_sha256: authoritative source requires a sha256")
    source_date = ref.get("date")
    if not (isinstance(source_date, str) and _DATE_RE.fullmatch(source_date)):
        violations.append(f"{prefix}.date: authoritative source requires an ISO date")
    elif available_on != source_date:
        violations.append(f"{prefix}.date: must match lineage available_on")
    page = ref.get("page")
    if page is not None and (isinstance(page, bool) or not isinstance(page, int) or page < 1):
        violations.append(f"{prefix}.page: must be null or an integer >= 1")
    if page is None:
        violations.append(f"{prefix}.page: authoritative source requires a document page")
    if receipt is not None:
        for key in ("url", "path", "page", "content_sha256", "evidence_sha256", "date", "event_id"):
            if ref.get(key) != receipt[key]:
                violations.append(f"{prefix}.{key}: does not match authoritative retained source receipt")
    elif "event_id" in ref and ref.get("event_id") is not None and not _nonempty(ref.get("event_id")):
        violations.append(f"{prefix}.event_id: must be null or a non-empty string")
    return violations


def _validate_analyst_ref(ref: Mapping[str, Any], prefix: str) -> list[str]:
    violations = _keys(ref, _ANALYST_REF_KEYS, prefix)
    for key in _ANALYST_REF_KEYS:
        if not _nonempty(ref.get(key)):
            violations.append(f"{prefix}.{key}: must be a non-empty string")
    return violations


def _validate_blocked_states(value: Any, prefix: str) -> list[str]:
    if not type(value) is dict:
        return [f"{prefix}: must be a mapping"]
    violations: list[str] = []
    for key, item in value.items():
        if not _nonempty(key):
            violations.append(f"{prefix}: keys must be non-empty strings")
        if not type(item) is dict:
            violations.append(f"{prefix}.{key}: must be a mapping")
            continue
        violations.extend(_keys(item, _BLOCKED_STATE_KEYS, f"{prefix}.{key}"))
        if item.get("status") != "blocked":
            violations.append(f"{prefix}.{key}.status: must equal blocked")
        if not _nonempty(item.get("reason")):
            violations.append(f"{prefix}.{key}.reason: must be a non-empty string")
    return violations


def _validate_lineage_alignment(
    runs: list[Any],
    lineage: list[Any],
    fixture_only: bool,
    status: Any,
) -> list[str]:
    violations: list[str] = []
    valid_runs = [run for run in runs if type(run) is dict]
    valid_lineage = [entry for entry in lineage if type(entry) is dict]
    if status == "computed_fixture":
        expected = {(label, field) for label in SCENARIO_LABELS for field in _COMPUTED_INPUT_FIELDS}
        observed = {
            (entry.get("case_label"), entry.get("field"))
            for entry in valid_lineage
            if entry.get("scope") == "synthetic_fixture_input"
        }
        if observed != expected:
            violations.append("input_lineage: computed fixture lineage must exactly cover every scenario/input field")
        for run in valid_runs:
            label = run.get("case_label")
            if tuple(run.get("input_fields") or ()) != _COMPUTED_INPUT_FIELDS:
                violations.append(f"scenario_runs[{label}].input_fields: must align with computed fixture lineage")
        if not fixture_only:
            violations.append("input_lineage: computed fixture status requires fixture_only")
    elif status == "blocked":
        for entry in valid_lineage:
            if entry.get("case_label") is not None:
                violations.append("input_lineage: retained blocked lineage must not be scenario-specific")
        if not any(entry.get("label_type") == "missing" for entry in valid_lineage):
            violations.append("input_lineage: retained blocked path must identify missing inputs")
    return violations


def _keys(mapping: Mapping[str, Any], expected: frozenset[str], prefix: str,
          optional: frozenset[str] = frozenset()) -> list[str]:
    violations: list[str] = []
    for key in sorted(set(mapping) - expected - optional):
        violations.append(f"{prefix}.{key}: unknown field")
    for key in sorted(expected - set(mapping)):
        violations.append(f"{prefix}.{key}: missing required field")
    return violations


def _json_finite(value: Any, prefix: str) -> list[str]:
    violations: list[str] = []
    violations.extend(_exact_containers(value, prefix))
    try:
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        violations.append(f"{prefix}: must be JSON-serializable and finite")
    for path, item in _walk(value, prefix):
        if type(item) is float and (not math.isfinite(item) or abs(item) > enp_event_contract.MAX_ABS_NUMBER):
            violations.append(f"{path}: non-finite number")
        elif type(item) is int and abs(item) > enp_event_contract.MAX_ABS_NUMBER:
            violations.append(f"{path}: number exceeds magnitude limit")
    return violations


def _exact_containers(value: Any, path: str) -> list[str]:
    """Reject dict/list subclasses before any serializer can invoke overrides."""
    violations: list[str] = []
    if type(value) is dict:
        for key, item in value.items():
            violations.extend(_exact_containers(item, f"{path}.{key}"))
    elif type(value) is list:
        for index, item in enumerate(value):
            violations.extend(_exact_containers(item, f"{path}[{index}]"))
    elif isinstance(value, (dict, list)):
        violations.append(f"{path}: must use exact builtin dict/list")
    return violations


def _forbidden_language(value: Any, prefix: str) -> list[str]:
    violations: list[str] = []
    try:
        text = json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).lower()
    except (TypeError, ValueError, OverflowError):
        return [f"{prefix}: cannot serialize for language scan"]
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


def _finite(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return number if math.isfinite(number) and abs(number) <= enp_event_contract.MAX_ABS_NUMBER else None


def _walk(value: Any, path: str):
    if type(value) is dict:
        for key, item in value.items():
            child = f"{path}.{key}"
            yield child, item
            yield from _walk(item, child)
    elif type(value) is list:
        for index, item in enumerate(value):
            child = f"{path}[{index}]"
            yield child, item
            yield from _walk(item, child)


def _walk_items(value: Any, path: str):
    if type(value) is dict:
        for key, item in value.items():
            yield path, key, item
            yield from _walk_items(item, f"{path}.{key}")
    elif type(value) is list:
        for index, item in enumerate(value):
            yield from _walk_items(item, f"{path}[{index}]")
