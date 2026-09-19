"""Focused checks for deterministic financial engine assumptions."""
from __future__ import annotations

import shutil
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_financial_engine_assumptions as builder
from formal_financial_engines import approved_records


def fail(message: str) -> None:
    raise AssertionError(message)


def write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def seed_state(root: Path, *, future_dates: bool = False, existing_records: list[dict] | None = None) -> Path:
    write_json(root / "company_profiles.json", {
        "updated": "2024-03-03 09:00",
        "pilot": {"symbols": ["MLCF"]},
    })
    write_json(root / "history_meta.json", {"updated": "2024-03-03 17:00"})
    history_rows = [
        {"date": "2024-03-01", "close": 10.5, "volume": 100, "open": 10.0},
        {"date": "2024-03-02", "close": 11.0, "volume": 110, "open": 10.6},
    ]
    if future_dates:
        history_rows.append({"date": "2024-03-04", "close": 12.0, "volume": 120, "open": 11.5})
    write_json(root / "history" / "MLCF.json", history_rows)
    fetched = "2024-03-04" if future_dates else "2024-03-02"
    write_json(root / "fundamentals.json", {
        "updated": "2024-03-03 18:00",
        "source": "stockanalysis.com",
        "tickers": {
            "MLCF": {
                "shares_out": "100.00M",
                "source_url": "https://stockanalysis.com/quote/psx/MLCF/",
                "fetched": fetched,
            },
        },
    })
    write_json(root / "company_intel" / "forecast_readiness.json", {
        "as_of": "2024-03-03 18:00",
        "companies": {
            "MLCF": {
                "status": "input_ready",
                "qualified_periods": [
                    {
                        "period_end": "2021-06-30",
                        "available_on": "2021-09-30",
                        "consolidation": "consolidated",
                        "source_fact_ids": {
                            "revenue": "fact_revenue_2021",
                            "profit_after_tax_attributable": "fact_pat_2021",
                            "basic_eps": "fact_eps_2021",
                        },
                    },
                    {
                        "period_end": "2022-06-30",
                        "available_on": "2022-09-30",
                        "consolidation": "consolidated",
                        "source_fact_ids": {
                            "revenue": "fact_revenue_2022",
                            "profit_after_tax_attributable": "fact_pat_2022",
                            "basic_eps": "fact_eps_2022",
                        },
                    },
                    {
                        "period_end": "2023-06-30",
                        "available_on": "2023-09-30",
                        "consolidation": "consolidated",
                        "source_fact_ids": {
                            "revenue": "fact_revenue_2023",
                            "profit_after_tax_attributable": "fact_pat_2023",
                            "basic_eps": "fact_eps_2023",
                        },
                    },
                ],
            },
        },
    })
    observations = {"revenue": [], "profit_after_tax_attributable": [], "basic_eps": []}
    for period_end, revenue, pat, eps in (
        ("2021-06-30", 1000.0, 100.0, 1.0),
        ("2022-06-30", 1100.0, 165.0, 1.5),
        ("2023-06-30", 1210.0, 181.5, 1.65),
    ):
        year = period_end[:4]
        document_id = f"psx:{year}"
        source_url = f"https://dps.psx.com.pk/download/document/{year}.pdf"
        for line, value in (
            ("revenue", revenue),
            ("profit_after_tax_attributable", pat),
            ("basic_eps", eps),
        ):
            observations[line].append({
                "ticker": "MLCF",
                "metric": line,
                "line": line,
                "fact_id": f"fact_{line if line != 'profit_after_tax_attributable' else 'pat'}_{year}",
                "available_on": f"{year}-09-30",
                "statement_type": "income_statement",
                "period_end": period_end,
                "period_type": "annual",
                "duration_months": 12,
                "consolidation": "consolidated",
                "currency": "PKR",
                "unit": "PKR/share" if line == "basic_eps" else "PKR",
                "unit_multiplier": 1,
                "normalized_value": value,
                "document_id": document_id,
                "content_sha256": f"sha-{line}-{year}",
                "source_url": source_url,
                "evidence": [{"page": 1, "text": f"{line} {year}", "source_url": source_url}],
                "readiness": "model_loadable",
            })
    write_json(root / "company_intel" / "financial_model_inputs.json", {
        "companies": {
            "MLCF": {
                "symbol": "MLCF",
                "status": "ready",
                "observations": observations,
                "derived": {},
            },
        },
    })
    out = root / "company_intel" / "financial_engine_assumptions.json"
    if existing_records is not None:
        write_json(out, {"records": existing_records})
    return out


def owner_record(metric: str = "exit_pe") -> dict:
    return {
        "symbol": "MLCF",
        "metric": metric,
        "value": 5.0,
        "approved": True,
        "available_on": "2024-03-02",
        "record_type": "approved_assumption",
        "source": {
            "id": f"owner:{metric}:2024-03-02",
            "label": f"owner approved {metric}",
            "path": "state/company_intel/financial_engine_assumptions.json",
            "available_on": "2024-03-02",
        },
    }


def assert_emits_market_operands_and_reference_cases() -> None:
    with tempfile.TemporaryDirectory(prefix="henneth-engine-assumptions-") as td:
        root = Path(td)
        out = seed_state(root, existing_records=[owner_record("exit_pe"), owner_record("revenue_growth_pct")])
        state = builder.build(root, out)
        generated = [record for record in state["records"] if record.get("generated_by") == builder.BUILDER_ID]
        generated_metrics = {record["metric"] for record in generated}
        if generated_metrics != {"current_price", "shares_out", "revenue_growth_pct", "net_margin_pct"}:
            fail(f"generated metrics mismatch: {sorted(generated_metrics)}")
        for metric in builder.FORBIDDEN_GENERATED_MODEL_METRICS:
            if any(record.get("generated_by") == builder.BUILDER_ID and record.get("metric") == metric for record in state["records"]):
                fail(f"generated forbidden metric {metric}")
        reference_cases = [
            record for record in generated
            if record.get("record_type") == "derived_reference_case"
        ]
        if len(reference_cases) != 2:
            fail(f"reference case count mismatch: {len(reference_cases)}")
        for record in reference_cases:
            if record.get("case_type") != "reference_case" or record.get("epistemic_type") != "derived":
                fail("reference case missing derived/reference_case typing")
            if record.get("approved") is not False or "value" in record:
                fail("reference case can enter formal engine approved value path")
            if record.get("assumption_status") != "not_owner_approved_forecast_input":
                fail("reference case does not clearly reject owner-approved forecast status")
            if not record.get("derived_value") or not record.get("source_facts"):
                fail("reference case missing derived value or source fact provenance")
            for fact in record["source_facts"]:
                for field in ("fact_id", "document_id", "source_url", "period_end", "available_on", "normalized_value"):
                    if not fact.get(field):
                        fail(f"reference source fact missing {field}")
        records = approved_records(state, "MLCF", "2024-03-03")
        if records.get("current_price", {}).get("value") != 11.0:
            fail("current_price not accepted by formal-engine source gate")
        if records.get("shares_out", {}).get("value") != 100_000_000.0:
            fail("shares_out not accepted by formal-engine source gate")
        if records.get("exit_pe", {}).get("source", {}).get("id") != "owner:exit_pe:2024-03-02":
            fail("owner-approved record was not preserved")
        if records.get("net_margin_pct"):
            fail("derived reference-case margin was accepted as an approved model input")
        if records.get("revenue_growth_pct", {}).get("source", {}).get("id") != "owner:revenue_growth_pct:2024-03-02":
            fail("owner-approved growth input was not kept distinct from generated reference case")
        gaps = ((state.get("assumption_gaps") or {}).get("companies") or {}).get("MLCF") or {}
        products = gaps.get("products") or {}
        if gaps.get("status") != "input_ready_pending_approved_records":
            fail("input-ready assumption gap row missing")
        if gaps.get("reference_cases_can_satisfy_missing_records") is not False:
            fail("reference cases can satisfy missing approved records")
        if products.get("forecast", {}).get("missing_approved_records") != ["net_margin_pct"]:
            fail("forecast assumption gap did not account for owner-approved growth and generated shares")
        if products.get("valuation", {}).get("missing_approved_records") != ["net_margin_pct", "net_debt"]:
            fail("valuation assumption gap mismatch")
        if products.get("market_expectations", {}).get("missing_approved_records") != ["net_margin_pct"]:
            fail("market expectations assumption gap mismatch")
        if not gaps.get("historical_reference_cases"):
            fail("gap manifest missing historical reference case refs")


def assert_idempotent_and_replaces_generated() -> None:
    with tempfile.TemporaryDirectory(prefix="henneth-engine-assumptions-") as td:
        root = Path(td)
        stale_generated = {
            "symbol": "MLCF",
            "metric": "current_price",
            "value": 9.0,
            "approved": True,
            "available_on": "2024-02-29",
            "generated_by": builder.BUILDER_ID,
            "record_type": "approved_market_operand",
            "source": {
                "id": "henneth_state:history:MLCF:2024-02-29:close",
                "label": "stale generated close",
                "path": "state/history/MLCF.json",
                "available_on": "2024-02-29",
            },
        }
        out = seed_state(root, existing_records=[owner_record(), stale_generated])
        builder.build(root, out)
        first = out.read_bytes()
        state = builder.build(root, out)
        second = out.read_bytes()
        if first != second:
            fail("builder is not byte-idempotent")
        if any(record.get("value") == 9.0 for record in state["records"]):
            fail("stale generated record was not replaced")


def assert_no_lookahead() -> None:
    with tempfile.TemporaryDirectory(prefix="henneth-engine-assumptions-") as td:
        root = Path(td)
        out = seed_state(root, future_dates=True, existing_records=[])
        state = builder.build(root, out)
        generated_metrics = {record["metric"] for record in state["records"] if record.get("generated_by") == builder.BUILDER_ID}
        if {"current_price", "shares_out"} & generated_metrics:
            fail(f"future-dated market source generated records: {sorted(generated_metrics)}")
        reasons = {(row["metric"], row["reason"]) for row in state["blocked"]}
        if ("current_price", "history_date_after_source_state") not in reasons:
            fail("future price row was not blocked")
        if ("shares_out", "fundamentals_date_after_source_state") not in reasons:
            fail("future shares-out row was not blocked")


def assert_real_state_builds() -> None:
    with tempfile.TemporaryDirectory(prefix="henneth-engine-assumptions-real-state-") as td:
        root = Path(td)
        for rel in (
            "company_profiles.json",
            "fundamentals.json",
            "history_meta.json",
            "company_intel/financial_model_inputs.json",
            "company_intel/forecast_readiness.json",
        ):
            src = ROOT / "state" / rel
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        shutil.copytree(ROOT / "state" / "history", root / "history")
        out = root / "company_intel" / "financial_engine_assumptions.json"
        builder.build(root, out)
        state = json.loads(out.read_text(encoding="utf-8"))
        generated = [record for record in state.get("records", []) if record.get("generated_by") == builder.BUILDER_ID]
        for record in generated:
            if record.get("metric") not in builder.GENERATED_METRICS:
                fail(f"real-state generated forbidden metric {record.get('metric')}")
            source = record.get("source") or {}
            if not source.get("id") or not source.get("label") or not record.get("available_on") or not source.get("path"):
                fail("real-state generated record missing source gate fields")
            if record.get("record_type") == "derived_reference_case" and (record.get("approved") is not False or "value" in record):
                fail("real-state reference case can enter approved value path")
        gaps = state.get("assumption_gaps") or {}
        companies = gaps.get("companies") or {}
        mlcf = companies.get("MLCF") or {}
        if mlcf.get("status") != "input_ready_pending_approved_records":
            fail("MLCF: real-state assumption gap did not mark input-ready pending records")
        if mlcf.get("reference_cases_can_satisfy_missing_records") is not False:
            fail("MLCF: reference cases can satisfy missing records")
        expected = {
            "forecast": ["revenue_growth_pct", "net_margin_pct"],
            "valuation": ["revenue_growth_pct", "net_margin_pct", "exit_pe", "net_debt"],
            "market_expectations": ["exit_pe", "net_margin_pct", "revenue_growth_pct"],
        }
        for product, missing in expected.items():
            row = (mlcf.get("products") or {}).get(product) or {}
            if row.get("missing_approved_records") != missing:
                fail(f"MLCF: {product} gap mismatch {row.get('missing_approved_records')}")
            accepted = [record.get("metric") for record in row.get("accepted_records") or []]
            required_market = ["shares_out"] if product != "market_expectations" else ["current_price", "shares_out"]
            if accepted != required_market:
                fail(f"MLCF: {product} accepted deterministic operands mismatch {accepted}")

        dgkc = companies.get("DGKC") or {}
        if dgkc.get("status") != "not_evaluated_until_input_ready" or dgkc.get("financial_model_inputs_status") != "partial":
            fail("DGKC: partial model inputs did not keep assumption review fail-closed")
        for product, row in (dgkc.get("products") or {}).items():
            if row.get("status") != "not_evaluated_until_input_ready":
                fail(f"DGKC: {product} activated before model inputs were ready")
            if row.get("missing_approved_records") != [] or row.get("missing_prerequisites") != ["financial_model_inputs_ready"]:
                fail(f"DGKC: {product} prerequisite boundary mismatch")
        summary = gaps.get("summary") or {}
        if summary.get("input_ready_company_count") != 1 or summary.get("ready_product_count") != 0:
            fail("real-state assumption gap summary mismatch")


def assert_cli_runs_against_temp_fixture() -> None:
    with tempfile.TemporaryDirectory(prefix="henneth-engine-assumptions-cli-") as td:
        root = Path(td)
        out = seed_state(root, existing_records=[])
        script = (
            "import build_financial_engine_assumptions as b;"
            f"b.build(r'{root}', r'{out}')"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=ROOT / "scripts",
        )
        if result.returncode != 0:
            fail("temp-fixture builder failed - " + ((result.stdout or result.stderr or "")[-500:].strip()))


def assert_real_state_cli_does_not_run_in_check() -> None:
    """The focused check must not mutate repo state while proving real inputs work."""
    before = (ROOT / "state" / "company_intel" / "financial_engine_assumptions.json").read_bytes()
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_financial_engine_assumptions.py"), "--self-noop"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        fail("self-noop check failed - " + ((result.stdout or result.stderr or "")[-500:].strip()))
    after = (ROOT / "state" / "company_intel" / "financial_engine_assumptions.json").read_bytes()
    if before != after:
        fail("focused check mutated real state")


def main() -> None:
    if sys.argv[1:] == ["--self-noop"]:
        return
    assert_emits_market_operands_and_reference_cases()
    assert_idempotent_and_replaces_generated()
    assert_no_lookahead()
    assert_real_state_builds()
    assert_cli_runs_against_temp_fixture()
    assert_real_state_cli_does_not_run_in_check()
    print("financial engine assumptions: PASS")


if __name__ == "__main__":
    main()
