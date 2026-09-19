#!/usr/bin/env python3
"""Verify the owner financial-assumption handoff is review-only and current."""
from __future__ import annotations

import argparse
from datetime import date
import json
import math
from pathlib import Path
import sys
from typing import Any
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_owner_financial_assumption_handoff import KIND, OUT, TARGET_SYMBOLS, build
from import_owner_financial_assumptions import ALLOWED_METRICS, STRICT_MINIMUM_METRICS
from psx_data import load_json


EXPECTED_PRODUCTS = {
    "MLCF": {
        "forecast": ["revenue_growth_pct", "net_margin_pct"],
        "valuation": ["revenue_growth_pct", "net_margin_pct", "exit_pe", "net_debt"],
        "market_expectations": ["exit_pe", "net_margin_pct", "revenue_growth_pct"],
    },
    "DGKC": {
        "forecast": ["revenue_growth_pct", "net_margin_pct"],
        "valuation": ["revenue_growth_pct", "net_margin_pct", "exit_pe", "net_debt"],
        "market_expectations": ["exit_pe", "net_margin_pct", "revenue_growth_pct"],
    },
}


def expected_missing_prerequisites(row: dict[str, Any]) -> list[str]:
    missing_prerequisites = []
    if row.get("financial_model_inputs_status") != "ready":
        missing_prerequisites.append("financial_model_inputs_ready")
    if row.get("forecast_readiness_status") != "input_ready":
        missing_prerequisites.append("forecast_readiness_input_ready")
    if row.get("financial_truth_status") != "qualified":
        missing_prerequisites.append("financial_truth_qualified")
    return missing_prerequisites


def expected_company_status(row: dict[str, Any]) -> str:
    if expected_missing_prerequisites(row):
        return "not_ready_for_assumption_handoff"
    return "input_ready_pending_owner_drafts"


def expected_product_status(row: dict[str, Any]) -> str:
    if expected_missing_prerequisites(row):
        return "not_evaluated_until_input_ready"
    return "blocked_missing_approved_records"


def assert_prerequisite_boundary_checks() -> None:
    green = {
        "financial_model_inputs_status": "ready",
        "forecast_readiness_status": "input_ready",
        "financial_truth_status": "qualified",
    }
    if expected_missing_prerequisites(green):
        fail("positive boundary: green prerequisites reported missing")
    if expected_company_status(green) != "input_ready_pending_owner_drafts":
        fail("positive boundary: green prerequisites did not open handoff")
    if expected_product_status(green) != "blocked_missing_approved_records":
        fail("positive boundary: green prerequisites did not evaluate products")

    red_cases = (
        ("model inputs", "financial_model_inputs_status", "partial", ["financial_model_inputs_ready"]),
        ("forecast readiness", "forecast_readiness_status", "blocked", ["forecast_readiness_input_ready"]),
        ("financial truth", "financial_truth_status", "not_qualified", ["financial_truth_qualified"]),
    )
    for label, field, value, expected in red_cases:
        row = dict(green)
        row[field] = value
        if expected_missing_prerequisites(row) != expected:
            fail(f"negative boundary: {label} prerequisite mismatch")
        if expected_company_status(row) != "not_ready_for_assumption_handoff":
            fail(f"negative boundary: {label} did not close company handoff")
        if expected_product_status(row) != "not_evaluated_until_input_ready":
            fail(f"negative boundary: {label} did not close product evaluation")


def fail(message: str) -> None:
    raise AssertionError(message)


def dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def iso_date(value: Any) -> str | None:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def _has_control_chars(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def assert_manifest_current() -> dict[str, Any]:
    assert_prerequisite_boundary_checks()
    if not OUT.exists():
        fail("owner financial-assumption handoff manifest is missing")
    manifest = load_json(OUT, {})
    rebuilt = build(write=False)
    if dump(manifest) != dump(rebuilt):
        fail("owner financial-assumption handoff manifest is stale or non-deterministic")
    if manifest.get("kind") != KIND or manifest.get("target_symbols") != list(TARGET_SYMBOLS):
        fail("handoff manifest kind or target boundary drifted")
    policy = manifest.get("policy") or {}
    for key in (
        "review_only",
        "secret_free",
        "no_assumption_values_in_manifest",
        "no_supabase_read_or_write",
        "does_not_approve_rows",
        "does_not_activate_formal_engines",
        "append_copy_approval_remains_manual",
    ):
        if policy.get(key) is not True:
            fail(f"handoff policy missing {key}")
    text = dump(manifest).lower()
    for forbidden in ("service_key", "apikey", "authorization", "bearer ", "password"):
        if forbidden in text:
            fail(f"secret-bearing marker leaked into manifest: {forbidden}")
    companies = manifest.get("companies") or {}
    if set(companies) != set(TARGET_SYMBOLS):
        fail("handoff company boundary mismatch")
    source = manifest.get("source") or {}
    if source.get("financial_truth_qualification") != "state/company_intel/financial_truth_qualification.json":
        fail("handoff manifest does not declare financial truth source gate")
    for symbol in TARGET_SYMBOLS:
        row = companies.get(symbol) or {}
        missing_prerequisites = expected_missing_prerequisites(row)
        if row.get("status") != expected_company_status(row):
            fail(f"{symbol}: handoff status does not match source prerequisites")
        if row.get("reference_cases_can_satisfy_missing_records") is not False:
            fail(f"{symbol}: reference cases can satisfy missing records")
        refs = row.get("historical_reference_cases") or []
        if {ref.get("metric") for ref in refs} != {"revenue_growth_pct", "net_margin_pct"}:
            fail(f"{symbol}: expected historical reference-case context only")
        if any(ref.get("can_satisfy_approved_record") is not False for ref in refs):
            fail(f"{symbol}: reference case marked eligible for approval gap")
        products = row.get("products") or {}
        for product, missing in EXPECTED_PRODUCTS[symbol].items():
            product_row = products.get(product) or {}
            if product_row.get("status") != expected_product_status(row):
                fail(f"{symbol}: {product} status does not match source prerequisites")
            expected_missing = [] if missing_prerequisites else missing
            if product_row.get("missing_approved_records") != expected_missing:
                fail(f"{symbol}: {product} missing records drifted: {product_row.get('missing_approved_records')}")
            if product_row.get("missing_prerequisites") != missing_prerequisites:
                fail(f"{symbol}: {product} prerequisite list drifted")
            accepted = [record.get("metric") for record in product_row.get("accepted_records") or []]
            expected_accepted = ["shares_out"] if product != "market_expectations" else ["current_price", "shares_out"]
            if accepted != expected_accepted:
                fail(f"{symbol}: {product} accepted deterministic operands drifted: {accepted}")
            for record in product_row.get("accepted_records") or []:
                if record.get("record_type") != "approved_market_operand" or record.get("value_present") is not True:
                    fail(f"{symbol}: {product} accepted a non-market operand")
        missing_metrics = [record.get("metric") for record in row.get("handoff_records") or []]
        if missing_prerequisites and missing_metrics:
            fail(f"{symbol}: blocked prerequisite company must have no handoff records")
        if missing_metrics != sorted(set(missing_metrics)):
            fail(f"{symbol}: unique handoff metrics are not deterministic: {missing_metrics}")
        for record in row.get("handoff_records") or []:
            if "value" in record or "row_id" in record or "approved_at" in record:
                fail(f"{symbol}: handoff record contains activating row/value fields")
            metric = record.get("metric")
            contract = record.get("contract") or {}
            if metric not in ALLOWED_METRICS:
                fail(f"{symbol}: unsupported handoff metric {metric}")
            unit, minimum, maximum = ALLOWED_METRICS[metric]
            if contract.get("unit") != unit or contract.get("minimum") != minimum or contract.get("maximum") != maximum:
                fail(f"{symbol}: metric contract drifted for {metric}")
    summary = manifest.get("summary") or {}
    expected_missing_count = sum(
        len((companies.get(symbol) or {}).get("handoff_records") or [])
        for symbol in TARGET_SYMBOLS
    )
    expected_product_gap_count = sum(
        len((product or {}).get("missing_approved_records") or [])
        for company in companies.values()
        for product in ((company or {}).get("products") or {}).values()
    )
    if summary.get("unique_missing_company_metric_count") != expected_missing_count:
        fail("handoff summary missing-record count is not derived from company rows")
    if summary.get("product_missing_entry_count") != expected_product_gap_count or summary.get("formal_products_ready_count") != 0:
        fail("handoff summary claims missing or ready count incorrectly")
    return manifest


def validate_draft(row: dict[str, Any], manifest: dict[str, Any]) -> str | None:
    row_id = str(row.get("id") or "").strip()
    try:
        uuid.UUID(row_id)
    except ValueError:
        return "invalid_row_id"
    symbol = str(row.get("symbol") or "").strip().upper()
    metric = str(row.get("metric") or "").strip()
    companies = manifest.get("companies") or {}
    company = companies.get(symbol) or {}
    required_metrics = {item.get("metric") for item in company.get("handoff_records") or []}
    if symbol not in TARGET_SYMBOLS or metric not in required_metrics:
        return "not_required_by_current_handoff"
    if row.get("approved") is not False or row.get("approved_at") is not None:
        return "draft_not_inert"
    if metric not in ALLOWED_METRICS:
        return "unsupported_metric"
    value = finite(row.get("value"))
    if value is None:
        return "non_finite_value"
    unit, minimum, maximum = ALLOWED_METRICS[metric]
    if metric in STRICT_MINIMUM_METRICS:
        in_range = minimum < value <= maximum
    else:
        in_range = minimum <= value <= maximum
    if not in_range or row.get("unit") != unit:
        return "value_or_unit_out_of_contract"
    available_on = iso_date(row.get("available_on"))
    manifest_as_of = iso_date(manifest.get("as_of"))
    if not available_on:
        return "missing_available_on"
    if manifest_as_of and available_on > manifest_as_of:
        return "available_on_after_manifest_as_of"
    source_label = str(row.get("source_label") or "").strip()
    source_url = str(row.get("source_url") or "").strip()
    rationale = str(row.get("rationale") or "").strip()
    if not source_label or len(source_label) > 500 or _has_control_chars(source_label):
        return "invalid_source_label"
    if source_url and (not source_url.startswith("https://") or len(source_url) > 2000 or _has_control_chars(source_url)):
        return "unsafe_source_url"
    if not rationale or len(rationale) > 2000 or _has_control_chars(rationale):
        return "invalid_rationale"
    return None


def assert_draft_export(path: Path, manifest: dict[str, Any]) -> None:
    rows = load_json(path, [])
    if isinstance(rows, dict):
        rows = rows.get("rows") or rows.get("drafts") or []
    if not isinstance(rows, list):
        fail("draft export must be a list or an object with rows/drafts")
    rejected: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            rejected["row_not_object"] = rejected.get("row_not_object", 0) + 1
            continue
        reason = validate_draft(row, manifest)
        if reason:
            rejected[reason] = rejected.get(reason, 0) + 1
            continue
        seen.add((str(row["symbol"]).upper(), str(row["metric"])))
    expected = {
        (symbol, record.get("metric"))
        for symbol in TARGET_SYMBOLS
        for record in ((manifest.get("companies") or {}).get(symbol) or {}).get("handoff_records") or []
        if isinstance(record, dict) and record.get("metric")
    }
    missing = sorted(f"{symbol}:{metric}" for symbol, metric in expected - seen)
    extra = sorted(f"{symbol}:{metric}" for symbol, metric in seen - expected)
    if rejected or missing or extra:
        detail = {"rejected": rejected, "missing": missing, "extra": extra}
        fail("draft export is not a complete valid handoff set: " + json.dumps(detail, sort_keys=True))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft-export", type=Path, help="Optional local JSON export of inert draft rows to validate.")
    args = parser.parse_args(argv)
    manifest = assert_manifest_current()
    if args.draft_export:
        assert_draft_export(args.draft_export, manifest)
        print("owner_financial_assumption_handoff: PASS (manifest current; draft export complete and inert)")
    else:
        summary = manifest.get("summary") or {}
        draft_count = summary.get("unique_missing_company_metric_count")
        print(
            "owner_financial_assumption_handoff: "
            f"PASS (manifest current; review-only, {draft_count} company-metric drafts required)"
        )


if __name__ == "__main__":
    main()
