"""Closed contract for the sales-led Event-to-Value case-run envelope.

The retained lane is deliberately categorical, but the category is not an
assertion: the adapter must re-derive it from exact retained BOP, PSO and GAL
evidence.  Numeric outputs are legal only in the explicitly synthetic fixture
lane, where the existing sales economics kernel remains the arithmetic owner.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
import re
from typing import Any

import sales_expansion_contract as sales

SCHEMA_VERSION = "sales_expansion_case_run_v1"
ADAPTER_VERSION = "sales_expansion_case_run_adapter_v1"
CASE_ID = "case_sales_expansion_unselected_v1"
CASE_FAMILY = "sales_led_expansion"
SCENARIOS = ("bear", "base", "bull")
REAL_CANDIDATES = ("BOP", "PSO", "GAL")
FIXTURE_SYMBOL = "SALES-FIXTURE"
FIXTURE_EVENT_REF = "fixture:sales-expansion-v1"
FIXTURE_EFFECTIVE_DATE = "2025-12-31"
FIXTURE_VALUATION_DATE = "2025-12-31"
FIXTURE_CUTOFF_AT = "2025-12-31T00:00:00+05:00"
REAL_CUTOFF_AT = "2026-03-05T12:29:00+05:00"

HASH_RE = re.compile(r"^[0-9a-f]{64}$")
ADVICE_RE = re.compile(
    r"\b(?:buy|sell|accumulate|recommend(?:ation)?|you\s+should)\b|\btarget\s+price\b|\bprice\s+target\b",
    re.I,
)
MAX_JSON_DEPTH = 48
MAX_JSON_NODES = 20_000
MAX_STRING_LENGTH = 20_000


def canonical_json(value: Any) -> str:
    projected, violations = safe_json_projection(value)
    if violations:
        raise ValueError("; ".join(violations))
    return json.dumps(projected, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def safe_json_projection(value: Any) -> tuple[Any, list[str]]:
    """Return a plain JSON projection or deterministic shape violations."""
    seen: set[int] = set()
    count = 0

    def walk(item: Any, path: str, depth: int) -> tuple[Any, list[str]]:
        nonlocal count
        count += 1
        if count > MAX_JSON_NODES:
            return None, [f"{path}: JSON payload exceeds {MAX_JSON_NODES} nodes"]
        if depth > MAX_JSON_DEPTH:
            return None, [f"{path}: JSON payload exceeds depth {MAX_JSON_DEPTH}"]
        if type(item) is dict:
            marker = id(item)
            if marker in seen:
                return None, [f"{path}: cyclic JSON object is forbidden"]
            seen.add(marker)
            out: dict[str, Any] = {}
            violations: list[str] = []
            for key, child in item.items():
                if type(key) is not str:
                    violations.append(f"{path}: mapping keys must be plain strings")
                    continue
                projected, child_violations = walk(child, f"{path}.{key}", depth + 1)
                violations.extend(child_violations)
                out[key] = projected
            seen.remove(marker)
            return out, violations
        if type(item) is list:
            marker = id(item)
            if marker in seen:
                return None, [f"{path}: cyclic JSON array is forbidden"]
            seen.add(marker)
            out = []
            violations = []
            for index, child in enumerate(item):
                projected, child_violations = walk(child, f"{path}[{index}]", depth + 1)
                violations.extend(child_violations)
                out.append(projected)
            seen.remove(marker)
            return out, violations
        if type(item) is str:
            if len(item) > MAX_STRING_LENGTH:
                return None, [f"{path}: string exceeds {MAX_STRING_LENGTH} characters"]
            return item, []
        if item is None or type(item) is bool or type(item) is int:
            return item, []
        if type(item) is float:
            if not math.isfinite(item):
                return None, [f"{path}: value must be finite"]
            return item, []
        return None, [f"{path}: value must be plain JSON, not {type(item).__name__}"]

    return walk(value, "$", 0)


def expected_fixture_identity() -> dict[str, Any]:
    return {
        "symbol": "SALES-FIXTURE",
        "event_ref": "fixture:sales-expansion-v1",
        "effective_date": "2025-12-31",
        "valuation_date": "2025-12-31",
    }


def expected_real_identity() -> dict[str, str]:
    return {
        "schema_version": "sales_expansion_case_run_v1",
        "adapter_version": "sales_expansion_case_run_adapter_v1",
        "case_id": "case_sales_expansion_unselected_v1",
        "case_family": "sales_led_expansion",
    }


def expected_real_source_refs() -> list[dict[str, Any]]:
    return [
        {
            "kind": "retained_source_evidence",
            "symbol": "BOP",
            "role": "generic_strategy_narrative",
            "qualifies_sales_event": False,
            "no_go_reason": "generic_strategy_narrative_without_dated_sales_event",
            "source_ref": {
                "id": "psx:272102",
                "event_id": "evt_a51de635bed77b8329cc",
                "document_id": "psx:272102",
                "url": "https://dps.psx.com.pk/download/document/272102.pdf",
                "title": "Transmission of Annual Report for the Year Ended 12/31/2025",
                "source": "PSX DPS",
                "source_origin": "research_index_and_company_documents",
                "event_type": "acquisition",
                "event_date": "2026-03-05T12:29:00+05:00",
                "published_at": "2026-03-05T12:29:00+05:00",
                "retrieved_at": "2026-08-22 16:10",
                "page": 25,
                "content_sha256": "b2ae42c6a0bc8032863d3df5a86b23b7d22c00f0581db6ec6bbed2ec64575617",
                "evidence_sha256": "16739c8885cf2433454971a90b1f9878017bd04ecf1edd66055443241fcffc84",
                "text": "easingly leveraging digital platforms, data analytics, and automation to improve customer acquisition, streamline operations, and drive growth in low-cost deposits\u2014particularly current accounts\u2014thereby strengthening net interest margins an\u2026",
            },
        },
        {
            "kind": "retained_source_evidence",
            "symbol": "PSO",
            "role": "same_issuer_undated_product_material",
            "qualifies_sales_event": False,
            "no_go_reason": "undated_same_issuer_product_material",
            "source_ref": {
                "id": "issuer:61d85f4626413576b676aed8",
                "event_id": "evt_2f3bfdf4a586999e66b6",
                "document_id": "issuer:61d85f4626413576b676aed8",
                "url": "https://psopk.com/source/fuelcards/list_of_enabled_outlets.pdf",
                "title": "Stations Accepting Corporate Cards (PDF)",
                "source": "Issuer website",
                "source_origin": "source_registry_document_link_and_company_documents",
                "event_type": "earnings",
                "event_date": None,
                "published_at": None,
                "retrieved_at": "2026-08-18 03:22",
                "page": 4,
                "content_sha256": "2bd076fae2202d45aac45bdd142e28f004a4254fff96cf02bac82caa0d892662",
                "evidence_sha256": "77509d702cdd05fe35677d7d47fc7d7cbb132dc37de110cf71022b1f7261bd0f",
                "text": "Y GROUND, LAHORE CANTT LAHORE LAHORE EMPRESS FILLING STATION OPPOSITE RAILWAY POLICE HEAD QUARTER, EMPRESS ROAD LAHORE LAHORE EXPO VIEW F/S & CNG PLOT NO.1 -1A, BLOCK R MUHAMMAD ALI JOHAR TOWN LAHORE FAISAL PETROLEUM STATION PSO STATION, P\u2026",
            },
        },
        {
            "kind": "retained_source_evidence",
            "symbol": "PSO",
            "role": "same_issuer_undated_product_material",
            "qualifies_sales_event": False,
            "no_go_reason": "undated_same_issuer_product_material",
            "source_ref": {
                "id": "issuer:ca78a4beec7f30b38e790a5e",
                "event_id": "evt_30027cd832df431a70a9",
                "document_id": "issuer:ca78a4beec7f30b38e790a5e",
                "url": "https://psopk.com/source/fuelcards/corporate-cards/02.pdf",
                "title": "PSO Cards SMS & Email Alerts Service",
                "source": "Issuer website",
                "source_origin": "source_registry_document_link_and_company_documents",
                "event_type": "credit_event",
                "event_date": None,
                "published_at": None,
                "retrieved_at": "2026-08-18 03:22",
                "page": 1,
                "content_sha256": "0b66c3bbd717ed36b51c91918c5e85dbc86c26b67c438c2c1796d4f97ce18604",
                "evidence_sha256": "6ac8d318df97b49a5fb44064bf81e722d35d10d8d9abd293c9f1eb7ee80cb03e",
                "text": "SMS alerts) Telecom Operator *Push SMS Billing SMS *Email Report *Email Frequency Daily (default) Sr. No. Card No. Name on Card Email Address (for Email alerts) Mobile No. (for SMS alerts) Telecom Operator *Push SMS *Pull SMS *Email Report\u2026",
            },
        },
        {
            "kind": "retained_source_evidence",
            "symbol": "GAL",
            "role": "issuer_home_no_qualifying_sales_event",
            "qualifies_sales_event": False,
            "no_go_reason": "no_retained_sales_event",
            "source_ref": {
                "id": "issuer_home:9fed93ec98418218bc7449c51856fa3e79c8c9edccb0443189778495bc0200e7",
                "event_id": None,
                "document_id": None,
                "url": "https://www.ghandharanissan.com.pk/",
                "title": "Issuer website",
                "source": "Issuer website",
                "source_origin": "source_registry_issuer_home_and_empty_company_ledger",
                "event_type": None,
                "event_date": None,
                "published_at": None,
                "retrieved_at": "2026-08-18T02:03:36+05:00",
                "page": None,
                "content_sha256": "9fed93ec98418218bc7449c51856fa3e79c8c9edccb0443189778495bc0200e7",
                "evidence_sha256": "5a5e8ae86deca18ceaa96f18f918626e6461ee71836bac81d4797063737fd098",
                "text": "source_registry issuer_home retained; company_event_ledger has no GAL events",
            },
        },
    ]


def expected_real_blocked_reasons() -> list[str]:
    return [
        "BOP:generic_strategy_narrative_without_dated_sales_event",
        "GAL:no_retained_sales_event",
        "PSO:undated_same_issuer_product_material",
        "sales_lane:no_canonical_dated_event",
    ]


def expected_real_retained_projection(
    cutoff_at: str = REAL_CUTOFF_AT,
    _real_sources: list[dict[str, Any]] = expected_real_source_refs(),
    _real_blocked: list[str] = expected_real_blocked_reasons(),
) -> dict[str, Any]:
    return {
        "schema_version": "sales_expansion_retained_projection_v1",
        "authority_files": [
            "state/company_event_ledger.json",
            "state/company_documents.json",
            "state/research_index.json",
            "state/company_intel/source_registry.json",
        ],
        "cutoff_at": cutoff_at,
        "blocked_reasons": _real_blocked,
        "input_lineage": _real_sources,
        "derivation": {
            "BOP": "Exact retained event evt_a51de635bed77b8329cc is a broad digital/customer-acquisition strategy narrative from an annual report, not a discrete dated rollout.",
            "PSO": "Exact retained issuer product materials share the PSO issuer origin but carry null event and published dates, so they are not dated sales expansion events.",
            "GAL": "Source registry retains the issuer home hash, while company_event_ledger contains no GAL event rows.",
        },
    }


def real_receipt_payload(envelope: dict[str, Any]) -> dict[str, Any]:
    return {
        "blocked_reasons": envelope.get("blocked_reasons"),
        "input_lineage": envelope.get("input_lineage"),
        "retained_projection": envelope.get("retained_projection"),
    }


def _datetime(value: Any) -> datetime | None:
    if type(value) is not str:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _scan(value: Any, path: str = "$") -> list[str]:
    violations: list[str] = []
    if type(value) is dict:
        for key, item in value.items():
            if key in {"target_price", "price_target", "targetPrice", "priceTarget"} or ADVICE_RE.search(key):
                violations.append(f"{path}.{key}: advice or target-price field is forbidden")
            violations.extend(_scan(item, f"{path}.{key}"))
    elif type(value) is list:
        for index, item in enumerate(value):
            violations.extend(_scan(item, f"{path}[{index}]"))
    elif type(value) is str and ADVICE_RE.search(value):
        violations.append(f"{path}: advice language is forbidden")
    return violations


def _unknown(value: dict[str, Any], allowed: set[str], path: str) -> list[str]:
    return [f"{path}.{key}: unknown field" for key in sorted(set(value) - allowed)]


def _readiness(value: Any, path: str, expected: str) -> list[str]:
    if type(value) is not dict:
        return [f"{path}: must be a plain object"]
    allowed = {"status", "blocked_reasons", "hard_block", "reason"}
    out = _unknown(value, allowed, path)
    if value.get("status") != expected:
        out.append(f"{path}.status: must equal {expected}")
    reasons = value.get("blocked_reasons")
    if type(reasons) is not list or any(type(x) is not str or not x.strip() for x in reasons):
        out.append(f"{path}.blocked_reasons: must be non-empty strings")
    elif reasons != sorted(set(reasons)):
        out.append(f"{path}.blocked_reasons: must be sorted and deduplicated")
    if value.get("hard_block") is not True:
        out.append(f"{path}.hard_block: must be true")
    if reasons and value.get("reason") != reasons[0]:
        out.append(f"{path}.reason: must equal first blocked reason")
    return out


def _validate_real_lineage(lineage: Any, _expected: list[dict[str, Any]] = expected_real_source_refs()) -> list[str]:
    if type(lineage) is not list:
        return ["input_lineage: must be a list"]
    expected = _expected
    violations: list[str] = []
    if lineage != expected:
        violations.append("input_lineage: must equal exact retained BOP/PSO/GAL source projection")
    seen = set()
    for index, row in enumerate(lineage):
        if type(row) is not dict:
            violations.append(f"input_lineage[{index}]: must be a plain object")
            continue
        violations.extend(_unknown(row, {"kind", "symbol", "role", "qualifies_sales_event", "no_go_reason", "source_ref"}, f"input_lineage[{index}]"))
        ref = row.get("source_ref")
        if type(ref) is not dict:
            violations.append(f"input_lineage[{index}].source_ref: must be a plain object")
            continue
        ref_keys = {
            "id", "event_id", "document_id", "url", "title", "source", "source_origin",
            "event_type", "event_date", "published_at", "retrieved_at", "page",
            "content_sha256", "evidence_sha256", "text",
        }
        violations.extend(_unknown(ref, ref_keys, f"input_lineage[{index}].source_ref"))
        if type(ref.get("content_sha256")) is not str or not HASH_RE.fullmatch(ref.get("content_sha256", "")):
            violations.append(f"input_lineage[{index}].source_ref.content_sha256: must be sha256")
        if type(ref.get("evidence_sha256")) is not str or not HASH_RE.fullmatch(ref.get("evidence_sha256", "")):
            violations.append(f"input_lineage[{index}].source_ref.evidence_sha256: must be sha256")
        key = (row.get("symbol"), ref.get("id"), ref.get("event_id"), ref.get("page"))
        if key in seen:
            violations.append(f"input_lineage[{index}]: duplicate retained source row")
        seen.add(key)
    return violations


def _validate_exact_tree(value: Any, expected: Any, path: str) -> list[str]:
    violations: list[str] = []
    if type(expected) is dict:
        if type(value) is not dict:
            return [f"{path}: must be a plain object"]
        actual_keys = set(value)
        expected_keys = set(expected)
        violations.extend(f"{path}.{key}: unknown field" for key in sorted(actual_keys - expected_keys))
        violations.extend(f"{path}.{key}: missing field" for key in sorted(expected_keys - actual_keys))
        for key in sorted(actual_keys & expected_keys):
            violations.extend(_validate_exact_tree(value[key], expected[key], f"{path}.{key}"))
        return violations
    if type(expected) is list:
        if type(value) is not list:
            return [f"{path}: must be a list"]
        if len(value) != len(expected):
            violations.append(f"{path}: expected {len(expected)} items, got {len(value)}")
        for index, (item, expected_item) in enumerate(zip(value, expected)):
            violations.extend(_validate_exact_tree(item, expected_item, f"{path}[{index}]"))
        return violations
    if value != expected:
        violations.append(f"{path}: exact retained value mismatch")
    return violations


def _validate_retained_projection(
    projection: Any,
    cutoff_at: str,
    _real_sources: list[dict[str, Any]] = expected_real_source_refs(),
    _real_blocked: list[str] = expected_real_blocked_reasons(),
) -> list[str]:
    expected = expected_real_retained_projection(cutoff_at, _real_sources, _real_blocked)
    violations = _validate_exact_tree(projection, expected, "retained_projection")
    if type(projection) is dict:
        if projection.get("input_lineage") != _real_sources:
            violations.append("retained_projection.input_lineage: must equal exact retained source projection")
        if projection.get("blocked_reasons") != _real_blocked:
            violations.append("retained_projection.blocked_reasons: must equal exact retained sales no-go reasons")
        if projection.get("cutoff_at") != cutoff_at:
            violations.append("retained_projection.cutoff_at: must equal retained source-effective cutoff")
    return violations


def _numeric_payload(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if type(value) is dict:
        for key, item in value.items():
            if key in {"values", "per_share", "quarterly_schedule", "break_even"} and item not in (None, [], {}):
                found.append(f"{path}.{key}")
            found.extend(_numeric_payload(item, f"{path}.{key}"))
    elif type(value) is list:
        for index, item in enumerate(value):
            found.extend(_numeric_payload(item, f"{path}[{index}]"))
    return found


def _validate_fixture_run(
    run: dict[str, Any],
    path: str,
    _fixture_identity: dict[str, Any] = expected_fixture_identity(),
) -> list[str]:
    run_keys = {"scenario", "status", "blocked_reasons", "case", "result"}
    violations: list[str] = []
    if set(run) != run_keys:
        violations.extend(f"{path}.{key}: closed run fields required" for key in sorted(run_keys - set(run)))
        violations.extend(f"{path}.{key}: unknown field" for key in sorted(set(run) - run_keys))
        return violations
    label = run.get("scenario")
    if label not in ("bear", "base", "bull"):
        violations.append(f"{path}.scenario: must be bear, base or bull")
    if run.get("status") != "computed" or run.get("blocked_reasons") != []:
        violations.append(f"{path}: fixture run must be computed with no blocked reasons")
    case = run.get("case")
    if type(case) is not dict:
        violations.append(f"{path}.case: fixture case required")
    else:
        violations.extend(sales.validate_case(case))
        identity = _fixture_identity
        expected = {
            "symbol": identity["symbol"],
            "event_ref": identity["event_ref"],
            "case_label": label,
            "effective_date": identity["effective_date"],
            "valuation_date": identity["valuation_date"],
        }
        for key, value in expected.items():
            if case.get(key) != value:
                violations.append(f"{path}.case.{key}: fixture identity mismatch")
    result = run.get("result")
    if type(result) is not dict:
        violations.append(f"{path}.result: computed result required")
    else:
        try:
            import sales_expansion_engine as engine
            expected_result = engine.evaluate_case(case)
        except Exception as error:
            violations.append(f"{path}.result: independent re-evaluation failed: {error}")
        else:
            if result != expected_result:
                violations.append(f"{path}.result: does not match independently re-evaluated fixture")
    return violations


def validate_case_run(
    envelope: Any,
    _identity: dict[str, str] = expected_real_identity(),
    _fixture_identity: dict[str, Any] = expected_fixture_identity(),
    _real_sources: list[dict[str, Any]] = expected_real_source_refs(),
    _real_blocked: list[str] = expected_real_blocked_reasons(),
    _fixture_cutoff_at: str = "2025-12-31T00:00:00+05:00",
    _real_cutoff_at: str = REAL_CUTOFF_AT,
    _real_receipt_payload=real_receipt_payload,
) -> list[str]:
    """Return deterministic violations; an empty list means the envelope is valid."""
    projected, projection_violations = safe_json_projection(envelope)
    if projection_violations:
        return sorted(set(projection_violations))
    if type(projected) is not dict:
        return ["envelope: must be a plain object"]
    envelope = projected
    envelope_keys = {
        "schema_version", "adapter_version", "status", "fixture_only", "fixture_identity",
        "case_id", "case_family", "mechanism", "scenario_runs", "blocked_reasons",
        "input_lineage", "retained_projection", "analogue_readiness", "formal_output_readiness",
        "policy", "run_receipt",
    }
    receipt_keys = {"cutoff_at", "input_sha256", "output_sha256", "retained_projection_sha256", "contract_version"}
    mechanism_keys = {"mechanism_id", "description", "arithmetic_engine", "authority"}
    policy_keys = {"research_only", "no_advice", "real_retained_path_zero_numeric_outputs", "fixture_non_authoritative"}

    identity = _identity
    violations = _scan(envelope)
    violations.extend(_unknown(envelope, envelope_keys, "envelope"))
    if envelope.get("schema_version") != identity["schema_version"] or envelope.get("adapter_version") != identity["adapter_version"]:
        violations.append("envelope: schema or adapter version mismatch")
    if envelope.get("case_id") != identity["case_id"] or envelope.get("case_family") != identity["case_family"]:
        violations.append("envelope: case identity mismatch")
    status = envelope.get("status")
    fixture = envelope.get("fixture_only")
    if status not in {"blocked", "computed_fixture"}:
        violations.append("status: must be blocked or computed_fixture")
    if type(fixture) is not bool or fixture != (status == "computed_fixture"):
        violations.append("fixture_only: must agree with status")
    fixture_identity = _fixture_identity
    if fixture:
        expected_fixture = {"symbol": fixture_identity["symbol"], "event_ref": fixture_identity["event_ref"]}
        if type(envelope.get("fixture_identity")) is not dict or envelope["fixture_identity"] != expected_fixture:
            violations.append("fixture_identity: exact fixture identity required")
        if envelope.get("retained_projection") is not None:
            violations.append("retained_projection: fixture path must be null")
    elif envelope.get("fixture_identity") is not None:
        violations.append("fixture_identity: real path must be null")
    if type(envelope.get("mechanism")) is not dict or set(envelope["mechanism"]) != mechanism_keys:
        violations.append("mechanism: closed business-mechanism description required")
    policy = envelope.get("policy")
    if (
        type(policy) is not dict
        or set(policy) != policy_keys
        or policy.get("research_only") is not True
        or policy.get("no_advice") is not True
        or policy.get("real_retained_path_zero_numeric_outputs") is not True
        or policy.get("fixture_non_authoritative") is not True
    ):
        violations.append("policy: closed research-only policy required")
    reasons = envelope.get("blocked_reasons")
    if type(reasons) is not list or any(type(x) is not str or not x.strip() for x in reasons):
        violations.append("blocked_reasons: must be non-empty strings")
    elif reasons != sorted(set(reasons)):
        violations.append("blocked_reasons: must be sorted and deduplicated")
    runs = envelope.get("scenario_runs")
    if type(runs) is not list:
        violations.append("scenario_runs: must be a list")
        runs = []
    if status == "blocked":
        if runs:
            violations.append("scenario_runs: blocked envelope cannot carry scenarios")
        if _numeric_payload(envelope):
            violations.append("real retained path must contain zero numeric output payloads")
        if reasons != _real_blocked:
            violations.append("blocked_reasons: must equal exact retained sales no-go reasons")
        violations.extend(_validate_real_lineage(envelope.get("input_lineage"), _real_sources))
        projection = envelope.get("retained_projection")
        violations.extend(_validate_retained_projection(projection, _real_cutoff_at, _real_sources, _real_blocked))
    else:
        if reasons != [] or len(runs) != 3 or [r.get("scenario") for r in runs if type(r) is dict] != ["bear", "base", "bull"]:
            violations.append("computed_fixture: requires ordered bear/base/bull runs and no blocked reasons")
        lineage = envelope.get("input_lineage")
        if type(lineage) is not list or not lineage:
            violations.append("input_lineage: non-empty provenance list required")
        for index, run in enumerate(runs):
            if type(run) is dict:
                violations.extend(_validate_fixture_run(run, f"scenario_runs[{index}]", _fixture_identity))
            else:
                violations.append(f"scenario_runs[{index}]: must be a plain object")
    violations.extend(_readiness(envelope.get("analogue_readiness"), "analogue_readiness", "not_ready"))
    violations.extend(_readiness(envelope.get("formal_output_readiness"), "formal_output_readiness", "blocked" if status == "blocked" else "not_ready"))
    receipt = envelope.get("run_receipt")
    if (
        type(receipt) is not dict
        or set(receipt) != receipt_keys
        or _datetime(receipt.get("cutoff_at")) is None
        or receipt.get("contract_version") != identity["schema_version"]
        or type(receipt.get("input_sha256")) is not str
        or not HASH_RE.fullmatch(receipt.get("input_sha256", ""))
        or type(receipt.get("output_sha256")) is not str
        or not HASH_RE.fullmatch(receipt.get("output_sha256", ""))
        or type(receipt.get("retained_projection_sha256")) is not str
        or not HASH_RE.fullmatch(receipt.get("retained_projection_sha256", ""))
    ):
        violations.append("run_receipt: closed hash-bound receipt required")
    elif status == "computed_fixture":
        cases = [run.get("case") for run in runs]
        results = [run.get("result") for run in runs]
        if receipt.get("cutoff_at") != _fixture_cutoff_at:
            violations.append("run_receipt.cutoff_at: fixture cutoff mismatch")
        if receipt.get("input_sha256") != sha256_json(cases):
            violations.append("run_receipt.input_sha256: fixture input hash mismatch")
        if receipt.get("output_sha256") != sha256_json(results):
            violations.append("run_receipt.output_sha256: fixture output hash mismatch")
        if receipt.get("retained_projection_sha256") != sha256_json(None):
            violations.append("run_receipt.retained_projection_sha256: fixture retained projection hash mismatch")
    elif status == "blocked":
        projection = envelope.get("retained_projection")
        if type(projection) is dict:
            if receipt.get("cutoff_at") != projection.get("cutoff_at"):
                violations.append("run_receipt.cutoff_at: retained cutoff mismatch")
            if receipt.get("input_sha256") != sha256_json(_real_receipt_payload(envelope)):
                violations.append("run_receipt.input_sha256: retained input hash mismatch")
            if receipt.get("retained_projection_sha256") != sha256_json(projection):
                violations.append("run_receipt.retained_projection_sha256: retained projection hash mismatch")
        if receipt.get("output_sha256") != sha256_json([]):
            violations.append("run_receipt.output_sha256: retained output hash mismatch")
    return sorted(set(violations))


def numeric_output_keys(value: Any) -> list[str]:
    projected, violations = safe_json_projection(value)
    if violations:
        return ["<invalid-json-projection>"]
    return _numeric_payload(projected)


__all__ = [
    "CASE_ID",
    "SCENARIOS",
    "validate_case_run",
    "numeric_output_keys",
    "sha256_json",
    "canonical_json",
    "expected_real_source_refs",
    "expected_real_blocked_reasons",
    "expected_real_retained_projection",
    "real_receipt_payload",
    "safe_json_projection",
]
