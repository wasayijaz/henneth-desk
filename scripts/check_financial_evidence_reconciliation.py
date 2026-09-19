"""Stable checks for Financial Evidence Reconciliation v1."""
from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
sys.path.insert(0, str(ROOT / "scripts"))

import build_financial_evidence_reconciliation as builder
from financial_evidence_reconciliation import (
    BLOCKED_OUTPUT_STATUS,
    EARNINGS_BRIDGE_VERSION,
    RECONCILIATION_VERSION,
    build_reconciliation,
    company_reconciliation,
    eligibility_scope,
    fact_status,
    stable_id,
)
from financial_statement_facts import PARSER_REVISION, PARSER_VERSION
from forecast_contract import official_financial_fact_provenance
from manual_financial_claims import qualified_manual_rows
from psx_data import load_json


FORBIDDEN_KEYS = {
    "forecast_value",
    "valuation_value",
    "target_price",
    "fair_value",
    "expected_return",
    "market_implied_growth",
}
READINESS_STATUSES = {
    "blocked_model_adapter_unavailable",
    "blocked_insufficient_qualified_history",
    "blocked_unsupported_sector_model",
    "input_ready",
}


def _fail(message: str) -> None:
    raise AssertionError(message)


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _walk(value, path=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield path + (str(key),), item
            yield from _walk(item, path + (str(key),))
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            yield from _walk(item, path + (str(idx),))


def _assert_no_numeric_outputs(data: dict) -> None:
    for path, value in _walk(data):
        key = path[-1] if path else ""
        if isinstance(value, float) and not math.isfinite(value):
            _fail(f"nonfinite value at {'.'.join(path)}")
        if key in FORBIDDEN_KEYS:
            _fail(f"forbidden forecast/valuation key at {'.'.join(path)}")
        if len(path) >= 2 and path[-2] in {"readiness", "policy"} and key in {"forecast", "valuation", "market_expectations"}:
            if value not in set(BLOCKED_OUTPUT_STATUS.values()):
                _fail(f"{'.'.join(path)} is not blocked")


def _assert_forecast_readiness(row: dict, symbol: str) -> None:
    readiness = row.get("readiness") or {}
    status = readiness.get("forecast_readiness_status")
    qualified_count = readiness.get("forecast_qualified_period_count")
    if status not in READINESS_STATUSES:
        _fail(f"{symbol}: invalid forecast readiness status {status!r}")
    if not isinstance(qualified_count, int) or qualified_count < 0:
        _fail(f"{symbol}: invalid legacy forecast-readiness qualified count")
    if status == "input_ready" and qualified_count < 3:
        _fail(f"{symbol}: input-ready reconciliation lacks three qualified periods")
    if status == "blocked_model_adapter_unavailable" and qualified_count < 3:
        _fail(f"{symbol}: adapter-unavailable readiness lacks three qualified periods")
    if status == "blocked_insufficient_qualified_history" and qualified_count >= 3:
        _fail(f"{symbol}: sufficient history mislabeled insufficient")


def _fact(line: str = "revenue", year: int = 2025, value: float = 100.0, **overrides) -> dict:
    source_url = overrides.pop("source_url", "https://dps.psx.com.pk/download/document/1.pdf")
    row = {
        "fact_id": f"{line}-{year}-{stable_id('case', line, year, value)[-6:]}",
        "document_id": f"psx:{year}",
        "content_sha256": f"hash-{year}",
        "source_url": source_url,
        "line": line,
        "metric": line,
        "parser_version": PARSER_VERSION,
        "parser_revision": PARSER_REVISION,
        "readiness": "model_loadable",
        "period_end": f"{year}-12-31",
        "period_type": "annual",
        "duration_months": 12,
        "consolidation": "consolidated",
        "currency": "PKR",
        "statement_type": "income_statement",
        "unit": "PKR/share" if line == "basic_eps" else "PKR",
        "unit_multiplier": 1 if line == "basic_eps" else 1_000_000,
        "raw_value": str(value),
        "normalized_value": value if line == "basic_eps" else value * 1_000_000,
        "available_on": f"{year + 1}-02-01",
        "published_at": f"{year + 1}-02-01T09:00:00+05:00",
        "retrieved_at": "2026-08-26 00:00",
        "quality_flags": [],
        "evidence": [{"page": 1, "text": f"{line} {year}", "source_url": source_url}],
    }
    row.update(overrides)
    return row


def _quarter_fact(line: str = "revenue", period: str = "2025-09-30", value: float = 100.0, **overrides) -> dict:
    year = int(period[:4])
    row = _fact(
        line,
        year,
        value,
        period_end=period,
        period_type="quarter",
        duration_months=3,
        column_role="current_period",
        available_on="2025-10-27",
        published_at="2025-10-27T10:09:00+05:00",
        fact_id=f"{line}-{period}-quarter-{stable_id('case', line, period, value)[-6:]}",
    )
    row.update(overrides)
    return row


def _ready_facts() -> list[dict]:
    rows = []
    for year in (2023, 2024, 2025):
        rows.extend([
            _fact("revenue", year, 100 + year),
            _fact("profit_after_tax_attributable", year, 20 + year),
            _fact("basic_eps", year, 2 + year / 1000),
        ])
    return rows


def _issuer_fact(line: str = "revenue", year: int = 2025, value: float = 100.0, **overrides) -> dict:
    source_url = f"https://issuer.example/investors/annual-{year}.pdf"
    source_page = "https://issuer.example/investors/"
    document_id = f"issuer:{year}"
    content_hash = ("abcdef0123456789" * 4)[:63] + str(year % 10)
    row = _fact(line, year, value, source_url=source_url)
    row.update({
        "document_id": document_id,
        "content_sha256": content_hash,
        "evidence": [{"page": 1, "text": f"{line} {year}", "source_url": source_url}],
        "issuer_registry_binding": {
            "status": "qualified",
            "document_id": document_id,
            "link_id": document_id,
            "source_url": source_url,
            "source_page": source_page,
            "root_domain": "issuer.example",
            "content_sha256": content_hash,
            "evidence_page": 1,
        },
    })
    row.update(overrides)
    return row


def _coverage() -> dict:
    return {
        "required_annual_periods": [
            {"slot": "annual_period_1", "period_end": "2025-12-31", "period_type": "annual", "document_id": "psx:2025", "matched_text": "year ended 2025"},
            {"slot": "annual_period_2", "period_end": "2024-12-31", "period_type": "annual", "document_id": "psx:2024", "matched_text": "year ended 2024"},
            {"slot": "annual_period_3", "period_end": "2023-12-31", "period_type": "annual", "document_id": "psx:2023", "matched_text": "year ended 2023"},
        ]
    }


def _assert_shape(data: dict, pilot: list[str]) -> None:
    _assert_no_numeric_outputs(data)
    if data.get("reconciliation_version") != RECONCILIATION_VERSION:
        _fail("reconciliation version mismatch")
    if data.get("earnings_bridge_version") != EARNINGS_BRIDGE_VERSION:
        _fail("earnings bridge version mismatch")
    if data.get("pilot_symbols") != pilot or len(pilot) != 20 or len(set(pilot)) != 20:
        _fail("pilot order/boundary mismatch")
    companies = data.get("companies") or {}
    if set(companies) != set(pilot):
        _fail("company boundary mismatch")
    summary = data.get("summary") or {}
    expected_ready = sum(1 for row in companies.values()
                         if (row.get("readiness") or {}).get("forecast_readiness_status") == "input_ready")
    expected_eligible = sum(1 for row in companies.values() for fact in row.get("facts") or []
                            if fact.get("status") == "eligible")
    if (summary.get("forecast_ready_company_count") != expected_ready
            or summary.get("eligible_fact_count") != expected_eligible):
        _fail("real-state reconciliation summary does not match its fact rows")
    for symbol in pilot:
        row = companies.get(symbol) or {}
        if row.get("symbol") != symbol:
            _fail(f"{symbol}: symbol mismatch")
        _assert_forecast_readiness(row, symbol)
        for key, blocked in BLOCKED_OUTPUT_STATUS.items():
            if row.get("readiness", {}).get(key) != blocked:
                _fail(f"{symbol}: {key} not blocked")
        for record in row.get("facts") or []:
            if record.get("status") not in {"eligible", "audit_only", "quarantined"}:
                _fail(f"{symbol}: invalid fact status")
            if not record.get("reconciliation_id") or not record.get("evidence_id"):
                _fail(f"{symbol}: missing stable ids")
            source = record.get("source") or {}
            if record.get("status") == "eligible":
                if not (
                    str(source.get("document_id") or "").startswith("psx:")
                    or str(source.get("document_id") or "").startswith("issuer:")
                ):
                    _fail(f"{symbol}: eligible fact missing official document")
                if source.get("source") not in {"PSX DPS", "Issuer registry"}:
                    _fail(f"{symbol}: eligible fact missing official source label")
                if not isinstance(source.get("page"), int) or source.get("available_on") <= record.get("period_end"):
                    _fail(f"{symbol}: eligible fact violates provenance/no-lookahead")
            if record.get("status") == "audit_only" and not record.get("reasons"):
                _fail(f"{symbol}: audit-only fact missing reason")
        for missing in row.get("missing_slots") or []:
            if missing.get("status") != "missing" or not missing.get("reason"):
                _fail(f"{symbol}: missing slot lacks explicit status")
        for conflict in row.get("conflicts") or []:
            if conflict.get("status") != "quarantined" or conflict.get("reason") != "conflicting_values_retained_no_silent_selection":
                _fail(f"{symbol}: conflict not quarantined")
            values = {item.get("normalized_value") for item in conflict.get("values") or []}
            if len(values) < 2:
                _fail(f"{symbol}: conflict lacks conflicting values")


def _synthetic_assertions() -> None:
    cases = {
        "missing_provenance": [_fact(evidence=[])],
        "source_url_mismatch": [_fact(evidence=[{"page": 1, "text": "x", "source_url": "https://dps.psx.com.pk/download/document/other.pdf"}])],
        "unofficial_source": [_fact(source_url="https://example.com/1.pdf", evidence=[{"page": 1, "text": "x", "source_url": "https://example.com/1.pdf"}])],
        "unavailable_before_cutoff": [_fact(available_on="2025-12-31")],
        "unavailable_after_cutoff_missing": [_fact(available_on=None)],
        "audit_only_promotion": [_fact(readiness="audit_only", quality_flags=["legacy_extractor_not_model_eligible"])],
    }
    for name, facts in cases.items():
        row = company_reconciliation("MLCF", facts, _coverage(), {}, {"status": "blocked_insufficient_qualified_history", "qualified_period_count": 0}, "2026-08-26")
        statuses = {record.get("status") for record in row.get("facts") or []}
        if "eligible" in statuses:
            _fail(f"{name}: invalid fact became eligible")
        if name == "audit_only_promotion" and "audit_only" not in statuses:
            _fail("audit-only fact did not retain audit-only status")
    conflict_facts = [_fact(value=100), _fact(value=101, fact_id="revenue-2025-conflict")]
    conflict_row = company_reconciliation("MLCF", conflict_facts, _coverage(), {}, {"status": "blocked_insufficient_qualified_history", "qualified_period_count": 0}, "2026-08-26")
    if conflict_row.get("source_conflict_count") != 1 or not conflict_row.get("conflicts"):
        _fail("conflicting values were not retained/quarantined")
    if any(record.get("status") != "quarantined" for record in conflict_row.get("facts") or []):
        _fail("conflicting fact rows were not quarantined")
    noisy_conflict_row = company_reconciliation("MLCF", [
        _fact(value=100),
        _fact(value=101, fact_id="revenue-2025-noisy", quality_flags=["taxonomy_noise"]),
    ], _coverage(), {}, {"status": "blocked_insufficient_qualified_history", "qualified_period_count": 0}, "2026-08-26")
    if noisy_conflict_row.get("source_conflict_count") != 0 or noisy_conflict_row.get("conflicts"):
        _fail("quarantined parser noise counted as a blocking source conflict")
    noisy_statuses = {record.get("source", {}).get("fact_id"): record.get("status") for record in noisy_conflict_row.get("facts") or []}
    if noisy_statuses.get("revenue-2025-noisy") != "quarantined":
        _fail("quarantined parser-noise fact disappeared or became eligible")
    unit_noise_row = company_reconciliation("MLCF", [
        _fact(value=100),
        _fact(value=101, fact_id="revenue-2025-unit-noise", currency="USD"),
    ], _coverage(), {}, {"status": "blocked_insufficient_qualified_history", "qualified_period_count": 0}, "2026-08-26")
    if unit_noise_row.get("source_conflict_count") != 0 or unit_noise_row.get("conflicts"):
        _fail("unit/taxonomy noise counted as a blocking source conflict")
    unit_record = next((record for record in unit_noise_row.get("facts") or [] if record.get("source", {}).get("fact_id") == "revenue-2025-unit-noise"), None)
    if not unit_record or unit_record.get("status") != "quarantined" or "missing_or_non_pkr_currency" not in (unit_record.get("reasons") or []):
        _fail("unit-noise fact was not visibly quarantined")
    # A reported line can reach the ledger from two qualified lanes at different
    # source scales - a thousands-scaled parser fact and a unit-scaled
    # owner-verified claim. The slot key must compare the normalized quantity,
    # so a disagreement blocks and an agreement stays clean.
    cross_scale_conflict_row = company_reconciliation("MLCF", [
        _fact(value=100),
        _fact(value=101, fact_id="revenue-2025-cross-scale",
              unit_multiplier=1, normalized_value=101 * 1_000_000),
    ], _coverage(), {}, {"status": "blocked_insufficient_qualified_history", "qualified_period_count": 0}, "2026-08-26")
    if cross_scale_conflict_row.get("source_conflict_count") != 1:
        _fail("cross-scale disagreement on one reported line escaped the conflict gate")
    if any(record.get("status") != "quarantined" for record in cross_scale_conflict_row.get("facts") or []):
        _fail("cross-scale conflicting fact rows were not quarantined")
    cross_scale_conflict = (cross_scale_conflict_row.get("conflicts") or [{}])[0]
    if {entry.get("unit_multiplier") for entry in cross_scale_conflict.get("values") or []} != {1, 1_000_000}:
        _fail("cross-scale conflict did not retain each value's source scale")
    cross_scale_agreement_row = company_reconciliation("MLCF", [
        _fact(value=100),
        _fact(value=100, fact_id="revenue-2025-cross-scale-agreed",
              unit_multiplier=1, normalized_value=100 * 1_000_000),
    ], _coverage(), {}, {"status": "blocked_insufficient_qualified_history", "qualified_period_count": 0}, "2026-08-26")
    if cross_scale_agreement_row.get("source_conflict_count") != 0 or cross_scale_agreement_row.get("conflicts"):
        _fail("agreeing cross-scale restatements of one reported line were treated as a conflict")
    if any(record.get("status") != "eligible" for record in cross_scale_agreement_row.get("facts") or []):
        _fail("agreeing cross-scale facts lost eligibility")
    eps_scale_row = company_reconciliation("MLCF", [
        _fact(value=100),
        _fact("basic_eps", value=10.0, fact_id="eps-2025-scale-guard"),
    ], _coverage(), {}, {"status": "blocked_insufficient_qualified_history", "qualified_period_count": 0}, "2026-08-26")
    if eps_scale_row.get("source_conflict_count") != 0 or eps_scale_row.get("conflicts"):
        _fail("distinct reported quantities collided in the conflict slot key")
    future_row = company_reconciliation("MLCF", [_fact(available_on="2027-02-01")], _coverage(), {}, {"status": "blocked_insufficient_qualified_history", "qualified_period_count": 0}, "2026-08-26")
    if any(record.get("status") == "eligible" for record in future_row.get("facts") or []):
        _fail("future available_on became eligible")
    ready_row = company_reconciliation("MLCF", _ready_facts(), _coverage(), {"status": "ready"}, {"status": "input_ready", "qualified_period_count": 3}, "2026-08-26")
    if ready_row.get("eligible_fact_count") != 9 or ready_row.get("missing_slot_count") != 0:
        _fail("ready fixture did not reconcile eligible facts")
    if ready_row.get("readiness", {}).get("forecast") != BLOCKED_OUTPUT_STATUS["forecast"]:
        _fail("ready fixture activated forecast output")
    for fact in _ready_facts():
        if fact_status(fact, "2026-08-26") != "eligible":
            _fail("clean official fact did not classify eligible")
    qualified_ocf = _fact(
        "operating_cash_flow",
        statement_type="cash_flow_statement",
        unit="PKR",
        unit_multiplier=1_000_000,
    )
    if fact_status(qualified_ocf, "2026-08-26") != "eligible":
        _fail("clean consolidated annual operating cash flow did not classify eligible")
    wrong_ocf_statement = _fact("operating_cash_flow")
    if fact_status(wrong_ocf_statement, "2026-08-26") == "eligible":
        _fail("operating cash flow with an income-statement identity became eligible")
    clean_quarter = _quarter_fact()
    if fact_status(clean_quarter, "2026-08-26") != "eligible":
        _fail("direct consolidated three-month reported quarter fact did not classify eligible")
    clean_quarter_record = company_reconciliation(
        "MLCF",
        [clean_quarter],
        _coverage(),
        {},
        {"status": "blocked_insufficient_qualified_history", "qualified_period_count": 0},
        "2026-08-26",
    )["facts"][0]
    if clean_quarter_record.get("eligibility_scope") != "reported_quarter_financial_truth_gate":
        _fail("direct reported quarter fact did not expose quarter-only eligibility scope")
    quarter_only_row = company_reconciliation(
        "MLCF",
        [clean_quarter],
        _coverage(),
        {},
        {"status": "blocked_insufficient_qualified_history", "qualified_period_count": 0},
        "2026-08-26",
    )
    if not any(
        missing.get("period_end") == "2025-12-31" and missing.get("metric") == "revenue"
        for missing in quarter_only_row.get("missing_slots") or []
    ):
        _fail("quarter-only fact incorrectly satisfied an annual income slot")
    for name, fact in {
        "comparative_quarter": _quarter_fact(column_role="comparative_prior_period"),
        "six_month_interim": _quarter_fact(period_type="interim", duration_months=6),
    }.items():
        if eligibility_scope(fact) != "not_eligible_financial_truth_gate":
            _fail(f"{name}: invalid quarter fixture exposed eligible scope")
        if fact_status(fact, "2026-08-26") == "eligible":
            _fail(f"{name}: invalid quarter fixture became eligible")
    clean_cashflow_quarter = _quarter_fact("operating_cash_flow", statement_type="cash_flow_statement", unit="PKR", unit_multiplier=1_000_000)
    if fact_status(clean_cashflow_quarter, "2026-08-26") != "eligible" or eligibility_scope(clean_cashflow_quarter) != "reported_quarter_financial_truth_gate":
        _fail("direct consolidated three-month cash-flow fact did not become quarterly eligible")
    issuer_fact = _issuer_fact()
    if not official_financial_fact_provenance(issuer_fact):
        _fail("qualified issuer fixture did not satisfy shared official provenance")
    issuer_row = company_reconciliation("MLCF", [issuer_fact], _coverage(), {}, {"status": "blocked_insufficient_qualified_history", "qualified_period_count": 0}, "2026-08-26")
    issuer_records = issuer_row.get("facts") or []
    if len(issuer_records) != 1 or issuer_records[0].get("status") != "eligible":
        _fail("qualified issuer fact did not reconcile eligible")
    issuer_source = issuer_records[0].get("source") or {}
    if issuer_source.get("issuer_registry_binding") != issuer_fact.get("issuer_registry_binding"):
        _fail("qualified issuer binding was not preserved in reconciliation source")
    tampered = _issuer_fact(issuer_registry_binding={**issuer_fact["issuer_registry_binding"], "content_sha256": "tampered"})
    if official_financial_fact_provenance(tampered):
        _fail("tampered issuer binding satisfied shared official provenance")
    if fact_status(tampered, "2026-08-26") == "eligible":
        _fail("tampered issuer binding became eligible")

    current_fact = _fact(retrieved_at="2026-08-29T11:15:16Z")
    current_snapshot = build_reconciliation(
        ["MLCF"],
        {"tickers": {"MLCF": {"facts": [current_fact, _fact(available_on="2027-02-01", retrieved_at="2026-08-27T00:00:00Z")]}}},
        {"companies": {"MLCF": _coverage()}},
        {"companies": {"MLCF": {"status": "ready"}}},
        {"as_of": "2026-08-28 15:26", "companies": {"MLCF": {"status": "blocked_insufficient_qualified_history", "qualified_period_count": 0}}},
    )
    if current_snapshot.get("as_of") != "2026-08-29T11:15:16Z":
        _fail("newly retrieved fact did not advance reconciliation availability cutoff")
    current_records = current_snapshot["companies"]["MLCF"]["facts"]
    if any(record.get("source", {}).get("available_on") == "2027-02-01" for record in current_records):
        _fail("future available_on fact advanced reconciliation snapshot")
    manual_rows, manual_meta = qualified_manual_rows()
    if manual_meta.get("qualified_count") != 9 or any(fact_status(row, "2026-08-31") != "eligible" for row in manual_rows):
        _fail("approved manual claims did not require or satisfy document authority")
    uncovered_manual = {**manual_rows[0], "evidence": [{"page": 2, "source_url": manual_rows[0]["source_url"]}]}
    if fact_status(uncovered_manual, "2026-08-31") == "eligible":
        _fail("manual fact outside its approved document-authority page became eligible")


def main() -> None:
    expected = builder.build()
    expected_again = builder.build()
    if _dump(expected) != _dump(expected_again):
        _fail("builder output is not deterministic")
    pilot = expected.get("pilot_symbols") or []
    _assert_shape(expected, pilot)
    for symbol, row in (expected.get("companies") or {}).items():
        _assert_forecast_readiness(row, symbol)
    _synthetic_assertions()
    before = builder.OUT.read_bytes()
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_financial_evidence_reconciliation.py")], capture_output=True, text=True, timeout=30)
    if result.returncode != 0 or builder.OUT.read_bytes() != before:
        _fail("builder output is not byte-idempotent")
    with tempfile.TemporaryDirectory(prefix="henneth-finrec-") as td:
        root = Path(td)
        payload = build_reconciliation(
            ["MLCF"],
            {"tickers": {"MLCF": {"facts": _ready_facts()}}},
            {"companies": {"MLCF": _coverage()}},
            {"companies": {"MLCF": {"status": "ready"}}},
            {"companies": {"MLCF": {"status": "input_ready", "qualified_period_count": 3}}},
        )
        (root / "out.json").write_text(_dump(payload), encoding="utf-8")
        loaded = json.loads((root / "out.json").read_text(encoding="utf-8"))
        if loaded["companies"]["MLCF"]["eligible_fact_count"] != 9:
            _fail("temp fixture round trip failed")
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_ci_slice.py")], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        _fail(result.stdout + result.stderr)
    slice_data = load_json(ROOT / "Henneth Desk 2.CI.0" / "data" / "company_intelligence.json", {"tickers": []})
    by_symbol = {row.get("symbol"): row for row in slice_data.get("tickers") or []}
    for symbol, state_row in expected.get("companies", {}).items():
        if (by_symbol.get(symbol) or {}).get("financial_evidence_reconciliation") != state_row:
            _fail(f"{symbol}: CI slice financial_evidence_reconciliation mismatch")
    print(
        "financial_evidence_reconciliation: "
        f"PASS ({len(pilot)} companies, "
        f"{(expected.get('summary') or {}).get('forecast_ready_company_count')} forecast-ready)"
    )


if __name__ == "__main__":
    main()
