"""MLCF cement historical analogue and event-study benchmark engine
(Case B, Section 11).

Consumes a caller-supplied, provenance-bound pool of historical cement
capacity-expansion / line-commissioning events (MLCF itself, and its direct
domestic peers LUCK, DGKC, PIOC, FCCL) and produces deterministic per-horizon
benchmark statistics (1Q/2Q/4Q/8Q). This module never fetches, parses, or
searches for evidence itself -- every event record is an explicit
source-labelled provenance record the caller supplies, matching this desk's
existing retained-state-only architecture (see fetch_company_documents.py /
stage_issuer_documents.py for the actual sourcing pipeline). Horizon-date
arithmetic reuses event_studies.add_months rather than re-deriving it.

Point-in-time cutoff discipline: every event's effective_date, and every
outcome's endpoint_date/endpoint_available_on, must be on or before the
case's single cutoff_date. A "mature" outcome additionally requires its
horizon target date (event_date + horizon months) to already have passed as
of the cutoff; an "immature" outcome is only valid when the target date is
still in the future relative to cutoff. No outcome may carry numeric metrics
unless its status is "mature" -- this is the no-lookahead guardrail.

Sample-size handling: each per-horizon, per-metric benchmark aggregates only
"mature" observations. Aggregates with fewer than MIN_SAMPLE (3) mature
observations report status "insufficient_evidence" and a fixed message
instead of a median/IQR/range computed on too few points.

Fail-closed gate: evaluate_with_financial_truth_gate is the only entry point
a consumer should call. If the company's financial_truth_qualification.json
row is not qualified (per the shared
formal_financial_engines.financial_truth_is_qualified predicate), it returns
an identity-only envelope with status == "blocked_financial_truth_not_qualified"
and withholds every benchmark number.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import statistics
from datetime import date
from typing import Any, Mapping

import event_studies
from formal_financial_engines import financial_truth_is_qualified
from psx_data import STATE, load_json, save_json

MODULE_VERSION = "mlcf_cement_analogue_engine_v1"
FORMULA_ID = "mlcf_cement_analogue_engine.historical_benchmark.v1"
RESULT_SCHEMA = "mlcf_cement_analogue_engine_result_v1"

HORIZON_MONTHS = {"1Q": 3, "2Q": 6, "4Q": 12, "8Q": 24}
HORIZONS = tuple(HORIZON_MONTHS)
MIN_SAMPLE = 3
INSUFFICIENT_EVIDENCE_MESSAGE = "Insufficient evidence for a reliable benchmark"

OUTCOME_METRICS = (
    "utilization_change_pct_points",
    "revenue_change_pct",
    "ebitda_margin_change_pct_points",
    "eps_change_pct",
    "absolute_stock_return_pct",
    "sector_relative_return_pct",
)
EVENT_TYPES = ("capacity_expansion", "line_commissioning")
ALLOWED_SYMBOLS = ("MLCF", "LUCK", "DGKC", "PIOC", "FCCL")
VALUATION_METRICS = ("trailing_pe", "ev_ebitda")
ECONOMIC_CONDITIONS = (
    "favorable_demand_low_input_cost",
    "favorable_demand_high_input_cost",
    "weak_demand_low_input_cost",
    "weak_demand_high_input_cost",
    "neutral",
)
OUTCOME_STATUSES = ("mature", "immature", "unavailable")

FINANCIAL_TRUTH_PATH = STATE / "company_intel" / "financial_truth_qualification.json"
OUTPUT_PATH = STATE / "company_intel" / "mlcf_cement_analogue_engine.json"


def _as_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    return event_studies.parse_date(value)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def provenance_ok(record: Any) -> bool:
    """Source-only provenance: historical analogue facts must be sourced,
    never analyst-estimated (unlike scenario/sensitivity assumptions)."""
    if not isinstance(record, Mapping):
        return False
    if record.get("label_type") != "source":
        return False
    ref = record.get("source_ref")
    return (
        isinstance(ref, Mapping)
        and _nonempty(ref.get("id"))
        and _nonempty(ref.get("label"))
        and (_nonempty(ref.get("url")) or _nonempty(ref.get("path")))
    )


def _validate_source_record(prefix: str, record: Any, cutoff: date) -> list[str]:
    violations: list[str] = []
    if not provenance_ok(record):
        violations.append(f"{prefix}: provenance record must carry label_type=source and a complete source_ref")
        return violations
    available_on = _as_date(record.get("available_on"))
    if available_on is None:
        violations.append(f"{prefix}.available_on: must be an ISO date (YYYY-MM-DD)")
    elif available_on > cutoff:
        violations.append(f"{prefix}.available_on: must be on or before cutoff_date")
    return violations


def _validate_outcome(prefix: str, effective_date: date, cutoff: date, horizon: str,
                       record: Any) -> list[str]:
    violations: list[str] = []
    if not isinstance(record, Mapping):
        return [f"{prefix}: must be a mapping"]
    for field in set(record) - ({"status", "endpoint_date", "endpoint_available_on"} | set(OUTCOME_METRICS)):
        violations.append(f"{prefix}.{field}: unknown outcome field")
    status = record.get("status")
    if status not in OUTCOME_STATUSES:
        violations.append(f"{prefix}.status: must be one of {OUTCOME_STATUSES}")
        return violations

    target_date = event_studies.add_months(effective_date, HORIZON_MONTHS[horizon])
    endpoint_date = record.get("endpoint_date")
    available_on = record.get("endpoint_available_on")
    parsed_endpoint = _as_date(endpoint_date) if endpoint_date is not None else None
    parsed_available = _as_date(available_on) if available_on is not None else None

    if status == "mature":
        if target_date > cutoff:
            violations.append(f"{prefix}: status=mature but horizon target date {target_date.isoformat()} is after cutoff_date")
        if endpoint_date is None or parsed_endpoint is None:
            violations.append(f"{prefix}.endpoint_date: mature outcome requires an ISO date")
        elif parsed_endpoint < target_date:
            violations.append(f"{prefix}.endpoint_date: must be on or after the horizon target date {target_date.isoformat()}")
        elif parsed_endpoint > cutoff:
            violations.append(f"{prefix}.endpoint_date: after cutoff_date (lookahead)")
        if available_on is None or parsed_available is None:
            violations.append(f"{prefix}.endpoint_available_on: mature outcome requires an ISO date")
        elif parsed_endpoint is not None and parsed_available < parsed_endpoint:
            violations.append(f"{prefix}.endpoint_available_on: must be on or after endpoint_date")
        elif parsed_available > cutoff:
            violations.append(f"{prefix}.endpoint_available_on: after cutoff_date (lookahead)")
        for metric in OUTCOME_METRICS:
            number = _finite(record.get(metric))
            if number is None:
                violations.append(f"{prefix}.{metric}: mature outcome requires a finite number (booleans are not numbers)")
    else:
        if endpoint_date is not None or available_on is not None:
            violations.append(f"{prefix}: only a mature outcome may carry endpoint_date/endpoint_available_on")
        for metric in OUTCOME_METRICS:
            if record.get(metric) is not None:
                violations.append(f"{prefix}.{metric}: only a mature outcome may carry a numeric value")
        if status == "immature" and target_date <= cutoff:
            violations.append(f"{prefix}: status=immature but horizon target date {target_date.isoformat()} is already on or before cutoff_date")
    return violations


def _validate_analogue_event(index: int, cutoff: date, record: Any) -> list[str]:
    prefix = f"analogue_events[{index}]"
    violations: list[str] = []
    if not isinstance(record, Mapping):
        return [f"{prefix}: must be a mapping"]

    required_scalar_fields = {
        "event_id", "symbol", "event_type", "effective_date", "scale_tpd",
        "pre_event_valuation_metric", "pre_event_valuation_multiple",
        "pre_event_baseline_as_of_date", "economic_conditions", "source", "outcomes",
    }
    for field in set(record) - required_scalar_fields:
        violations.append(f"{prefix}.{field}: unknown field")
    for field in required_scalar_fields:
        if field not in record:
            violations.append(f"{prefix}.{field}: missing required field")

    if not _nonempty(record.get("event_id")):
        violations.append(f"{prefix}.event_id: must be a non-empty string")
    symbol = record.get("symbol")
    if symbol not in ALLOWED_SYMBOLS:
        violations.append(f"{prefix}.symbol: must be one of {ALLOWED_SYMBOLS}")
    event_type = record.get("event_type")
    if event_type not in EVENT_TYPES:
        violations.append(f"{prefix}.event_type: must be one of {EVENT_TYPES}")

    effective_date = _as_date(record.get("effective_date"))
    if effective_date is None:
        violations.append(f"{prefix}.effective_date: must be an ISO date (YYYY-MM-DD)")
    elif effective_date > cutoff:
        violations.append(f"{prefix}.effective_date: must be on or before cutoff_date (lookahead)")

    scale_tpd = _finite(record.get("scale_tpd"))
    if scale_tpd is None:
        violations.append(f"{prefix}.scale_tpd: must be a finite number (booleans are not numbers)")
    elif scale_tpd <= 0.0:
        violations.append(f"{prefix}.scale_tpd: must be > 0")

    if record.get("pre_event_valuation_metric") not in VALUATION_METRICS:
        violations.append(f"{prefix}.pre_event_valuation_metric: must be one of {VALUATION_METRICS}")
    multiple = _finite(record.get("pre_event_valuation_multiple"))
    if multiple is None:
        violations.append(f"{prefix}.pre_event_valuation_multiple: must be a finite number (booleans are not numbers)")
    elif multiple <= 0.0:
        violations.append(f"{prefix}.pre_event_valuation_multiple: must be > 0")

    baseline_as_of = _as_date(record.get("pre_event_baseline_as_of_date"))
    if baseline_as_of is None:
        violations.append(f"{prefix}.pre_event_baseline_as_of_date: must be an ISO date (YYYY-MM-DD)")
    elif effective_date is not None and baseline_as_of > effective_date:
        violations.append(f"{prefix}.pre_event_baseline_as_of_date: must be on or before effective_date")

    if record.get("economic_conditions") not in ECONOMIC_CONDITIONS:
        violations.append(f"{prefix}.economic_conditions: must be one of {ECONOMIC_CONDITIONS}")

    violations.extend(_validate_source_record(f"{prefix}.source", record.get("source"), cutoff))

    outcomes = record.get("outcomes")
    if not isinstance(outcomes, Mapping):
        violations.append(f"{prefix}.outcomes: must be a mapping of horizon to outcome record")
    else:
        for field in set(outcomes) - set(HORIZONS):
            violations.append(f"{prefix}.outcomes.{field}: unknown horizon")
        for horizon in HORIZONS:
            if horizon not in outcomes:
                violations.append(f"{prefix}.outcomes.{horizon}: missing required horizon")
                continue
            if effective_date is not None:
                violations.extend(_validate_outcome(f"{prefix}.outcomes.{horizon}", effective_date, cutoff, horizon, outcomes[horizon]))
    return violations


def validate_case(case: Mapping[str, Any]) -> list[str]:
    """Return named violations; an empty list means the case is valid."""
    if not isinstance(case, Mapping):
        return ["case: must be a mapping"]
    violations: list[str] = []
    for field in ("symbol", "project_name", "event_ref"):
        if not _nonempty(case.get(field)):
            violations.append(f"{field}: must be a non-empty string")
    cutoff = _as_date(case.get("cutoff_date"))
    if cutoff is None:
        violations.append("cutoff_date: must be an ISO date (YYYY-MM-DD)")
    try:
        json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError):
        violations.append("case: must be JSON-serializable and finite")
    if cutoff is None:
        return violations

    target = case.get("target_event")
    if not isinstance(target, Mapping):
        violations.append("target_event: must be a mapping")
    else:
        for field in set(target) - {"symbol", "event_type", "effective_date", "scale_tpd", "source"}:
            violations.append(f"target_event.{field}: unknown field")
        if target.get("symbol") not in ALLOWED_SYMBOLS:
            violations.append(f"target_event.symbol: must be one of {ALLOWED_SYMBOLS}")
        if target.get("event_type") not in EVENT_TYPES:
            violations.append(f"target_event.event_type: must be one of {EVENT_TYPES}")
        target_effective = _as_date(target.get("effective_date"))
        if target_effective is None:
            violations.append("target_event.effective_date: must be an ISO date (YYYY-MM-DD)")
        scale = _finite(target.get("scale_tpd"))
        if scale is None:
            violations.append("target_event.scale_tpd: must be a finite number (booleans are not numbers)")
        elif scale <= 0.0:
            violations.append("target_event.scale_tpd: must be > 0")
        violations.extend(_validate_source_record("target_event.source", target.get("source"), cutoff))

    events = case.get("analogue_events")
    if not isinstance(events, list):
        violations.append("analogue_events: must be a list of analogue event records")
    else:
        seen_ids: set[str] = set()
        for index, record in enumerate(events):
            violations.extend(_validate_analogue_event(index, cutoff, record))
            if isinstance(record, Mapping) and _nonempty(record.get("event_id")):
                event_id = record["event_id"]
                if event_id in seen_ids:
                    violations.append(f"analogue_events[{index}].event_id: duplicate event_id '{event_id}'")
                seen_ids.add(event_id)
    return violations


# ---------------------------------------------------------------------------
# Deterministic aggregation kernel
# ---------------------------------------------------------------------------

def _quantiles(values: list[float]) -> tuple[float, float]:
    """Q1/Q3 via the stdlib inclusive method (matches common quartile
    convention); requires at least 2 points, only called at n >= MIN_SAMPLE."""
    q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return q1, q3


def _metric_benchmark(values: list[float]) -> dict[str, Any]:
    n = len(values)
    if n < MIN_SAMPLE:
        return {
            "sample_size": n,
            "status": "insufficient_evidence",
            "message": INSUFFICIENT_EVIDENCE_MESSAGE,
            "median": None, "q1": None, "q3": None, "iqr": None, "min": None, "max": None,
        }
    ordered = sorted(values)
    q1, q3 = _quantiles(ordered)
    return {
        "sample_size": n,
        "status": "sufficient",
        "message": None,
        "median": statistics.median(ordered),
        "q1": q1,
        "q3": q3,
        "iqr": q3 - q1,
        "min": ordered[0],
        "max": ordered[-1],
    }


def compute_benchmarks(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    benchmarks: dict[str, Any] = {}
    for horizon in HORIZONS:
        horizon_benchmarks: dict[str, Any] = {}
        mature_count = 0
        for metric in OUTCOME_METRICS:
            values: list[float] = []
            for event in events:
                outcome = event["outcomes"][horizon]
                if outcome["status"] == "mature":
                    values.append(float(outcome[metric]))
            if metric == OUTCOME_METRICS[0]:
                mature_count = len(values)
            horizon_benchmarks[metric] = _metric_benchmark(values)
        benchmarks[horizon] = {
            "mature_sample_size": mature_count,
            "metrics": horizon_benchmarks,
        }
    return benchmarks


def _event_lineage(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "event_id": record["event_id"],
        "symbol": record["symbol"],
        "event_type": record["event_type"],
        "effective_date": record["effective_date"],
        "scale_tpd": record["scale_tpd"],
        "pre_event_valuation_metric": record["pre_event_valuation_metric"],
        "pre_event_valuation_multiple": record["pre_event_valuation_multiple"],
        "pre_event_baseline_as_of_date": record["pre_event_baseline_as_of_date"],
        "economic_conditions": record["economic_conditions"],
        "source": copy.deepcopy(record["source"]),
        "outcomes": copy.deepcopy(record["outcomes"]),
    }


# ---------------------------------------------------------------------------
# Envelope builders
# ---------------------------------------------------------------------------

def evaluate_case(case: Mapping[str, Any]) -> dict[str, Any]:
    """Pure deterministic kernel: raises ValueError for any invalid case.

    Has no knowledge of financial-truth qualification; callers that must
    respect the fail-closed gate use evaluate_with_financial_truth_gate.
    """
    violations = validate_case(case)
    if violations:
        raise ValueError("; ".join(violations))
    canonical = json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    events = case["analogue_events"]
    benchmarks = compute_benchmarks(events)
    return {
        "schema_version": RESULT_SCHEMA,
        "formula_id": FORMULA_ID,
        "module_version": MODULE_VERSION,
        "run_receipt": {
            "inputs_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        },
        "status": "computed",
        "blocked_reasons": [],
        "project": {
            "symbol": case["symbol"],
            "project_name": case["project_name"],
            "event_ref": case["event_ref"],
            "cutoff_date": case["cutoff_date"],
        },
        "target_event": {
            "symbol": case["target_event"]["symbol"],
            "event_type": case["target_event"]["event_type"],
            "effective_date": case["target_event"]["effective_date"],
            "scale_tpd": case["target_event"]["scale_tpd"],
            "source": copy.deepcopy(case["target_event"]["source"]),
        },
        "analogue_pool": {
            "total_events": len(events),
            "events": [_event_lineage(record) for record in sorted(events, key=lambda r: (r["effective_date"], r["event_id"]))],
        },
        "benchmarks": benchmarks,
        "confidence_limitations": {
            "research_only": True,
            "no_advice": True,
            "single_point_estimate": False,
            "simplifications": [
                "every analogue event and outcome is an explicit, source-labelled caller input; this module performs no search, fetch, or document parsing of its own",
                "point-in-time cutoff discipline: no event, outcome endpoint, or evidence-availability date may fall after cutoff_date",
                "a mature outcome requires its horizon target date (event date + horizon months) to have already passed as of cutoff_date; otherwise it must be marked immature with no numeric metrics",
                f"per-horizon, per-metric benchmarks require at least {MIN_SAMPLE} mature observations; below that, the benchmark reports '{INSUFFICIENT_EVIDENCE_MESSAGE}' instead of a median/IQR/range",
                "median, Q1, Q3 use the stdlib inclusive-quartile method; IQR = Q3 - Q1",
                "this is a descriptive historical benchmark only, not a forecast, valuation input, or causal attribution of the target event's own outcome",
            ],
        },
    }


def blocked_result(identity: Mapping[str, Any], reasons: list[str], *,
                    status: str = "blocked_invalid_inputs") -> dict[str, Any]:
    """Identity-only blocked envelope; no partial calculations leak."""
    return {
        "schema_version": RESULT_SCHEMA,
        "formula_id": FORMULA_ID,
        "module_version": MODULE_VERSION,
        "run_receipt": {"inputs_sha256": None},
        "status": status,
        "blocked_reasons": sorted(set(str(reason) for reason in reasons)),
        "project": {
            "symbol": identity.get("symbol") if isinstance(identity, Mapping) else None,
            "project_name": identity.get("project_name") if isinstance(identity, Mapping) else None,
            "event_ref": identity.get("event_ref") if isinstance(identity, Mapping) else None,
            "cutoff_date": identity.get("cutoff_date") if isinstance(identity, Mapping) else None,
        },
        "target_event": None,
        "analogue_pool": None,
        "benchmarks": None,
        "confidence_limitations": {
            "research_only": True,
            "no_advice": True,
            "single_point_estimate": False,
            "simplifications": ["blocked before calculation; missing, invalid, or unqualified inputs"],
        },
    }


def evaluate_with_financial_truth_gate(case: Mapping[str, Any],
                                        financial_truth_row: Mapping[str, Any]) -> dict[str, Any]:
    """The only entry point a consumer should call. Fails closed on both the
    financial-truth qualification gate and on invalid/malformed case inputs;
    never raises."""
    if not financial_truth_is_qualified(financial_truth_row):
        status = financial_truth_row.get("status") if isinstance(financial_truth_row, Mapping) else None
        return blocked_result(
            case if isinstance(case, Mapping) else {},
            [f"financial_truth_status:{status or 'missing'}"],
            status="blocked_financial_truth_not_qualified",
        )
    try:
        return evaluate_case(case)
    except ValueError as error:
        return blocked_result(
            case if isinstance(case, Mapping) else {},
            str(error).split("; "),
            status="blocked_invalid_inputs",
        )


# ---------------------------------------------------------------------------
# Build entry point
# ---------------------------------------------------------------------------

REAL_SYMBOL = "MLCF"
REAL_PROJECT_NAME = "MLCF Cement Historical Analogue & Event Study Benchmark"
REAL_EVENT_REF = "case_mlcf_pioc_control_observed_v1"
REAL_BASELINE_DATE = "2026-08-31"


def _real_identity() -> dict[str, Any]:
    """Identity-only case shell for the real MLCF lane. No target event, no
    analogue pool: neither is source-qualified/retained yet for capacity-
    expansion or line-commissioning events across MLCF/LUCK/DGKC/PIOC/FCCL
    (that sourcing runs through fetch_company_documents.py /
    stage_issuer_documents.py, not this pure kernel). The financial-truth
    gate below blocks live output before an analogue pool would matter."""
    return {
        "symbol": REAL_SYMBOL,
        "project_name": REAL_PROJECT_NAME,
        "event_ref": REAL_EVENT_REF,
        "cutoff_date": REAL_BASELINE_DATE,
    }


def build(*, write: bool = True, financial_truth: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build the real MLCF cement analogue-engine state envelope. Blocks
    closed unless and until MLCF's financial_truth_qualification.json row is
    qualified."""
    truth_state = financial_truth if financial_truth is not None else load_json(
        FINANCIAL_TRUTH_PATH, {"companies": {}}
    )
    truth_row = (truth_state.get("companies") or {}).get(REAL_SYMBOL) or {}
    result = evaluate_with_financial_truth_gate(_real_identity(), truth_row)
    if write:
        save_json(OUTPUT_PATH, result)
    return result


def main() -> None:
    result = build(write=True)
    print(f"mlcf_cement_analogue_engine: status={result['status']}")


if __name__ == "__main__":
    main()
