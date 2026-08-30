"""Read-only MARI E&P case-run adapter.

The retained-state path emits a deterministic blocked envelope for
``case_mari_offshore_exploration_blocks_observed_v1``. It intentionally
produces no numeric scenario output because the current retained state lacks
source-grounded E&P operands and model-ready financial truth.

The synthetic fixture path is separate and explicitly ``fixture_only``. It
proves that bear/base/bull cases can pass through the existing
``enp_event_engine`` when provenance-labelled operands are supplied.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping

import enp_event_engine
import build_mari_enp_evidence_readiness as readiness_builder
import mari_enp_case_run_contract as contract
import mari_enp_hypothesis_contract


EVENT_ID = "evt_3d1dae7553f73da60ba3"
EVENT_DOCUMENT_ID = "psx:265594"
EVENT_LEGACY_ID = "evt_ddf99590afb6dacddbde"


def build_retained_case_run(root: Path | None = None) -> dict[str, Any]:
    """Build the real retained MARI envelope without writing state."""
    root = root or Path(__file__).resolve().parents[1]
    # Rebuild the readiness seam in memory so a stale generated artifact can
    # never reintroduce cross-event provenance into the retained case-run.
    readiness = readiness_builder.build_manifest(root)
    cases = _load(root, "state/company_intel/intelligence_cases.json")
    analogues = _load(root, "state/company_intel/conditional_benchmarks.json")
    truth = _load(root, "state/company_intel/financial_truth_qualification.json")
    formal = {
        "financial_forecasts": _load(root, "state/company_intel/financial_forecasts.json"),
        "formal_valuations": _load(root, "state/company_intel/formal_valuations.json"),
        "market_expectations": _load(root, "state/company_intel/market_expectations.json"),
    }

    observed_case, case_reasons = _observed_case(cases)
    blocked_reasons = _blocked_reasons(readiness, truth, formal, case_reasons)
    valuation_date = _date_only((observed_case or {}).get("as_of"))
    if valuation_date is None:
        blocked_reasons.append("missing_retained_valuation_date")
        valuation_date = None
    effective_date = _date_only((readiness.get("event") or {}).get("effective_date"))
    if effective_date is None:
        blocked_reasons.append("missing_retained_effective_date")
        effective_date = None
    identity = {
        "symbol": contract.SYMBOL,
        "event_ref": EVENT_ID,
        "effective_date": effective_date,
        "valuation_date": valuation_date,
    }
    runs = []
    for label in contract.SCENARIO_LABELS:
        run_identity = dict(identity, case_label=label)
        runs.append(_summarise_engine_result(
            enp_event_engine.blocked_result(run_identity, blocked_reasons),
            fixture_only=False,
        ))

    envelope = _base_envelope(fixture_only=False)
    envelope.update({
        "status": "blocked",
        "scenario_runs": runs,
        "blocked_reasons": blocked_reasons,
        "input_lineage": _retained_lineage(readiness),
        "analogue_readiness": _analogue_readiness(analogues),
        "formal_output_readiness": _formal_output_readiness(truth, formal, fixture_only=False),
    })
    _assert_valid(envelope)
    return envelope


def build_synthetic_fixture_case_run() -> dict[str, Any]:
    """Build a fixture-only computed envelope for bear/base/bull wiring checks."""
    runs = []
    lineage = []
    for label in contract.SCENARIO_LABELS:
        case = _synthetic_case(label)
        violations = contract.validate_engine_case(case)
        if violations:
            raise ValueError("; ".join(violations))
        result = enp_event_engine.evaluate_case(case)
        runs.append(_summarise_engine_result(result, fixture_only=True))
        lineage.extend(_fixture_lineage(label, result["inputs_lineage"]))

    envelope = _base_envelope(fixture_only=True)
    envelope.update({
        "status": "computed_fixture",
        "scenario_runs": runs,
        "blocked_reasons": [],
        "input_lineage": lineage,
        "analogue_readiness": {
            "status": "fixture_not_real_analogue_evidence",
            "target_event_id": EVENT_ID,
            "readiness_status": "not_applicable_fixture_only",
            "aggregate_ready_horizons": [],
            "next_required_evidence": "Synthetic case-run fixture only; retained analogues remain governed by state/company_intel/conditional_benchmarks.json.",
            "blocked_states": {
                "real_case": {
                    "status": "blocked",
                    "reason": "not_activated_by_fixture",
                },
            },
        },
        "formal_output_readiness": _formal_output_readiness({}, {}, fixture_only=True),
    })
    _assert_valid(envelope)
    return envelope


def _base_envelope(fixture_only: bool) -> dict[str, Any]:
    return {
        "schema_version": contract.SCHEMA_VERSION,
        "adapter_version": contract.ADAPTER_VERSION,
        "status": "blocked",
        "fixture_only": fixture_only,
        "fixture_identity": {
            "id": contract._FIXTURE_ID,
            "spec_sha256": contract._FIXTURE_SPEC_SHA256,
        } if fixture_only else None,
        "case_id": contract.CASE_ID,
        "symbol": contract.SYMBOL,
        "case_family": contract.CASE_FAMILY,
        "hypothesis_linkage": {
            "status": "linked_observed_hypotheses",
            "source_contract": mari_enp_hypothesis_contract.CONTRACT_VERSION,
            "hypothesis_ids": list(mari_enp_hypothesis_contract.HYPOTHESIS_IDS),
            "exclusive_group": "mari-event-mechanism",
            "observed_event_status": mari_enp_hypothesis_contract.EVENT_STATUS,
        },
        "scenario_runs": [],
        "blocked_reasons": [],
        "input_lineage": [],
        "analogue_readiness": {
            "status": "unknown",
            "target_event_id": EVENT_ID,
            "readiness_status": "unknown",
            "aggregate_ready_horizons": [],
            "next_required_evidence": None,
            "blocked_states": {},
        },
        "formal_output_readiness": {
            "status": "blocked",
            "financial_truth_status": "not_qualified",
            "financial_truth_reason": None,
            "products": [],
        },
        "policy": {
            "research_only": True,
            "no_advice": True,
            "no_forecast_activation": True,
            "no_valuation_activation": True,
            "no_market_expectations_activation": True,
            "synthetic_numbers_fixture_only": True,
            "real_retained_path_zero_numeric_outputs": True,
        },
    }


def _observed_case(cases: Mapping[str, Any]) -> tuple[Mapping[str, Any] | None, list[str]]:
    company = ((cases.get("companies") or {}).get(contract.SYMBOL) or {})
    matches = [
        case for case in company.get("cases") or []
        if isinstance(case, Mapping) and case.get("case_id") == contract.CASE_ID
    ]
    if len(matches) != 1:
        return None, ["observed_mari_case_seed_missing_or_ambiguous"]
    case = matches[0]
    reasons: list[str] = []
    if case.get("status") != "Observed":
        reasons.append("observed_mari_case_seed_not_observed")
    if case.get("case_family") != contract.CASE_FAMILY:
        reasons.append("observed_mari_case_family_mismatch")
    return case, reasons


def _blocked_reasons(
    readiness: Mapping[str, Any],
    truth: Mapping[str, Any],
    formal: Mapping[str, Mapping[str, Any]],
    extra: list[str],
) -> list[str]:
    reasons = list(extra)
    reasons.extend(str(reason) for reason in ((readiness.get("activation") or {}).get("reasons") or []))
    truth_row = ((truth.get("companies") or {}).get(contract.SYMBOL) or {})
    if truth_row.get("status") != "qualified":
        tie_out = truth_row.get("financial_tie_out") or {}
        reason = tie_out.get("reason") or "financial truth is not qualified"
        reasons.append(f"financial_truth_not_qualified: {reason}")
    for product, state in formal.items():
        row = ((state.get("companies") or {}).get(contract.SYMBOL) or {})
        if row.get("status") != "computed":
            reasons.append(f"{product}_blocked: {row.get('blocked_reason') or row.get('reason') or row.get('status') or 'not_computed'}")
    return sorted(set(reasons))


def _retained_lineage(readiness: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for evidence in (readiness.get("event") or {}).get("evidence") or []:
        if evidence.get("document_id") != EVENT_DOCUMENT_ID or evidence.get("event_id") != EVENT_ID:
            continue
        available_on = _evidence_available_on(readiness, evidence)
        source_ok = bool(available_on and evidence.get("document_id"))
        rows.append({
            "scope": "retained_event_evidence",
            "case_label": None,
            "field": "observed_event_evidence",
            "status": str(evidence.get("evidence_class") or "observed"),
            "label_type": "source" if source_ok else "missing",
            "available_on": available_on,
            "value": None,
            "source_ref": {
                "id": evidence.get("document_id"),
                "label": "retained PSX event evidence",
                "url": evidence.get("source_url"),
                "page": evidence.get("page"),
                "content_sha256": evidence.get("content_sha256"),
                "evidence_sha256": evidence.get("evidence_sha256"),
                "event_id": evidence.get("event_id"),
                "date": available_on,
            } if source_ok else None,
            "analyst_ref": None,
        })
    for item in ((readiness.get("ep_operands") or {}).get("items") or []):
        operand = item.get("operand")
        label_type = "source" if item.get("status") == "observed_text_only" else "missing"
        refs = [
            ref for ref in (item.get("evidence_refs") or [])
            if ref.get("document_id") == EVENT_DOCUMENT_ID
            and ref.get("event_id") == EVENT_ID
        ]
        # Operator status is not stated in the target document.  Even if a
        # stale/mutated readiness object presents it as observed, do not emit
        # a target operand source row.
        if operand == "operator_status":
            label_type = "missing"
            refs = []
        if operand == "block_identity":
            refs = sorted(refs, key=lambda ref: 0 if ref.get("document_id") == EVENT_DOCUMENT_ID else 1)
        available_on = _evidence_available_on(readiness, refs[0]) if label_type == "source" and refs else None
        if not available_on:
            label_type = "missing"
        rows.append({
            "scope": "retained_ep_operand",
            "case_label": None,
            "field": operand,
            "status": item.get("status"),
            "label_type": label_type,
            "available_on": available_on,
            "value": item.get("value") if label_type == "source" else None,
            "source_ref": {
                "id": refs[0].get("document_id"),
                "label": "retained qualitative E&P operand lead",
                "url": refs[0].get("source_url"),
                "page": refs[0].get("page"),
                "content_sha256": refs[0].get("content_sha256"),
                "evidence_sha256": _evidence_sha256_for_document(readiness, refs[0].get("document_id")),
                "event_id": refs[0].get("event_id"),
                "date": available_on,
            } if label_type == "source" and refs else None,
            "analyst_ref": None,
        })
    return sorted(rows, key=lambda row: (str(row["scope"]), str(row["field"]), str(row["source_ref"])))


def _evidence_available_on(readiness: Mapping[str, Any], evidence: Mapping[str, Any]) -> str | None:
    """Use only a retained event date; never invent a provenance timestamp."""
    event = readiness.get("event") or {}
    event_date = _date_only(event.get("effective_date"))
    event_documents = {str(item.get("document_id")) for item in event.get("evidence") or []}
    if event_date and str(evidence.get("document_id")) in event_documents:
        return event_date
    return None


def _evidence_sha256_for_document(readiness: Mapping[str, Any], document_id: Any) -> str | None:
    for evidence in (readiness.get("event") or {}).get("evidence") or []:
        if evidence.get("document_id") == document_id:
            return evidence.get("evidence_sha256")
    return None


def _analogue_readiness(analogues: Mapping[str, Any]) -> dict[str, Any]:
    company = ((analogues.get("companies") or {}).get(contract.SYMBOL) or {})
    benchmark = next(
        (
            row for row in company.get("benchmarks") or []
            if ((row.get("target_event") or {}).get("event_id") == EVENT_ID)
        ),
        {},
    )
    readiness = benchmark.get("readiness_ledger") or {}
    return {
        "status": company.get("status") or "unknown",
        "target_event_id": EVENT_ID,
        "readiness_status": readiness.get("status") or benchmark.get("status") or "unknown",
        "aggregate_ready_horizons": list(readiness.get("aggregate_ready_horizons") or []),
        "next_required_evidence": readiness.get("next_required_evidence"),
        "blocked_states": benchmark.get("blocked_states") or company.get("blocked_states") or {},
    }


def _formal_output_readiness(
    truth: Mapping[str, Any],
    formal: Mapping[str, Mapping[str, Any]],
    fixture_only: bool,
) -> dict[str, Any]:
    if fixture_only:
        return {
            "status": "blocked_fixture_only",
            "financial_truth_status": "not_applicable_fixture_only",
            "financial_truth_reason": "Synthetic E&P scenario arithmetic does not activate retained formal outputs.",
            "products": [
                {"product": "financial_forecasts", "status": "blocked_fixture_only", "blocked_reason": "fixture_output_not_formal_output"},
                {"product": "formal_valuations", "status": "blocked_fixture_only", "blocked_reason": "fixture_output_not_formal_output"},
                {"product": "market_expectations", "status": "blocked_fixture_only", "blocked_reason": "fixture_output_not_formal_output"},
            ],
        }
    truth_row = ((truth.get("companies") or {}).get(contract.SYMBOL) or {})
    products = []
    for product in ("financial_forecasts", "formal_valuations", "market_expectations"):
        row = ((formal.get(product, {}).get("companies") or {}).get(contract.SYMBOL) or {})
        products.append({
            "product": product,
            "status": row.get("status") or "blocked",
            "blocked_reason": row.get("blocked_reason") or row.get("reason") or "not_computed",
        })
    return {
        "status": "blocked",
        "financial_truth_status": truth_row.get("status") or "not_qualified",
        "financial_truth_reason": (truth_row.get("financial_tie_out") or {}).get("reason"),
        "products": products,
    }


def _summarise_engine_result(result: Mapping[str, Any], fixture_only: bool) -> dict[str, Any]:
    schedule = result.get("quarterly_schedule") or []
    summary = {
        "case_label": (result.get("scenario") or {}).get("case_label"),
        "status": result.get("status"),
        "fixture_only": fixture_only,
        "engine_version": result.get("engine_version"),
        "formula_id": result.get("formula_id"),
        "contract_version": (result.get("run_receipt") or {}).get("contract_version"),
        "input_sha256": (result.get("run_receipt") or {}).get("inputs_sha256"),
        "fixture_hash": None,
        "input_fields": [entry.get("field") for entry in result.get("inputs_lineage") or []],
        "quarterly_schedule": schedule,
        "quarterly_schedule_rows": len(schedule),
        "values": result.get("values"),
        "per_share": result.get("per_share"),
        "probabilities": result.get("probabilities"),
        "blocked_reasons": sorted(set(str(reason) for reason in (result.get("blocked_reasons") or []))),
    }
    if fixture_only:
        summary["fixture_hash"] = contract.fixture_receipt_hash(summary)
    return summary


def _fixture_lineage(label: str, engine_lineage: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for entry in engine_lineage:
        rows.append({
            "scope": "synthetic_fixture_input",
            "case_label": label,
            "field": entry.get("field"),
            "status": "fixture_only",
            "label_type": entry.get("label_type"),
            "available_on": entry.get("available_on"),
            "value": entry.get("value"),
            "source_ref": entry.get("source_ref"),
            "analyst_ref": entry.get("analyst_ref"),
        })
    return rows


def _synthetic_case(label: str) -> dict[str, Any]:
    profile = {
        "bear": {
            "working_interest_pct": 20.0,
            "spend": [1.2e9, 0.7e9, 4.2e9],
            "initial_production_boe_pd": 750.0,
            "quarterly_decline_pct": 8.0,
            "oil_share_pct": 35.0,
            "opex_usd_boe": 18.0,
            "geological_success_pct": 18.0,
            "commercial_success_pct": 45.0,
        },
        "base": {
            "working_interest_pct": 35.0,
            "spend": [1.0e9, 0.6e9, 3.4e9],
            "initial_production_boe_pd": 1250.0,
            "quarterly_decline_pct": 5.0,
            "oil_share_pct": 45.0,
            "opex_usd_boe": 14.0,
            "geological_success_pct": 28.0,
            "commercial_success_pct": 58.0,
        },
        "bull": {
            "working_interest_pct": 50.0,
            "spend": [0.9e9, 0.5e9, 2.8e9],
            "initial_production_boe_pd": 1900.0,
            "quarterly_decline_pct": 3.0,
            "oil_share_pct": 55.0,
            "opex_usd_boe": 11.0,
            "geological_success_pct": 40.0,
            "commercial_success_pct": 70.0,
        },
    }[label]
    spend = profile["spend"]
    note = f"synthetic_fixture_only_{label}; not retained MARI truth"
    return {
        "symbol": contract.SYMBOL,
        "event_ref": EVENT_ID,
        "case_label": label,
        "effective_date": "2025-11-13",
        "valuation_date": "2025-12-31",
        "inputs": {
            "working_interest_pct": _analyst(profile["working_interest_pct"], note),
            "consideration_pkr": _analyst(0.0, note),
            "spend_schedule": _analyst([
                {"quarter_end": "2025-12-31", "phase": "exploration", "amount_pkr": spend[0]},
                {"quarter_end": "2026-03-31", "phase": "appraisal", "amount_pkr": spend[1]},
            ], note),
            "first_production_quarter_end": _analyst("2026-09-30", note),
            "production_horizon_quarters": _analyst(6, note),
            "initial_production_boe_pd": _analyst(profile["initial_production_boe_pd"], note),
            "quarterly_decline_pct": _analyst(profile["quarterly_decline_pct"], note),
            "oil_share_pct": _analyst(profile["oil_share_pct"], note),
            "oil_price_usd_bbl": _analyst(70.0, note),
            "gas_price_usd_mmbtu": _analyst(4.0, note),
            "gas_mmbtu_per_boe": _analyst(5.8, note),
            "fx_pkr_usd": _analyst(280.0, note),
            "opex_usd_boe": _analyst(profile["opex_usd_boe"], note),
            "royalty_pct": _analyst(12.5, note),
            "effective_tax_pct": _analyst(35.0, note),
            "discount_rate_pct_annual": _analyst(16.0, note),
            "geological_success_pct": _analyst(profile["geological_success_pct"], note),
            "commercial_success_pct": _analyst(profile["commercial_success_pct"], note),
            "shares_out": _analyst(1_000_000_000.0, note),
        },
    }


def _analyst(value: Any, note: str) -> dict[str, Any]:
    return {
        "value": value,
        "label_type": "analyst",
        "analyst_ref": {
            "note_id": "note:mari-enp-case-run:fixture",
            "note": note,
        },
        "available_on": "2025-12-01",
    }


def _load(root: Path, relative: str) -> Any:
    with (root / relative).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _date_only(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    if len(text) >= 10:
        try:
            return datetime.fromisoformat(text[:10]).date().isoformat()
        except ValueError:
            return None
    return None


def _assert_valid(envelope: Mapping[str, Any]) -> None:
    violations = contract.validate_envelope(envelope)
    if violations:
        raise ValueError("; ".join(violations))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--fixture", action="store_true", help="emit the synthetic fixture-only computed envelope")
    args = parser.parse_args()
    envelope = build_synthetic_fixture_case_run() if args.fixture else build_retained_case_run(args.root)
    print(json.dumps(envelope, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False))


if __name__ == "__main__":
    main()
