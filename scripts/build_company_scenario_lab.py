"""Build the deterministic company scenario lab state snapshot."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from company_scenario_lab import parse_scaled
from formal_financial_engines import financial_truth_is_qualified

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "state" / "company_profiles.json"
FUND = ROOT / "state" / "fundamentals.json"
QUANT = ROOT / "state" / "quant.json"
FINANCIAL_TRUTH = ROOT / "state" / "company_intel" / "financial_truth_qualification.json"
OUT = ROOT / "state" / "company_intel" / "scenario_lab.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build(profile_path: Path = PILOT, fundamentals_path: Path = FUND,
          quant_path: Path = QUANT, financial_truth_path: Path = FINANCIAL_TRUTH) -> dict:
    profile, fundamentals, quant, financial_truth = (
        load(profile_path), load(fundamentals_path), load(quant_path), load(financial_truth_path)
    )
    symbols = list(profile["pilot"]["symbols"])
    companies = {}
    fundamentals_dates = []
    price_dates = []
    for symbol in symbols:
        f = fundamentals.get("tickers", {}).get(symbol) or {}
        q = quant.get("tickers", {}).get(symbol) or {}
        revenue = parse_scaled(f["revenue"])
        net_income = parse_scaled(f["net_income"])
        shares = parse_scaled(f["shares_out"])
        # baseline eps is DERIVED (net_income / shares_out), matching this file's own
        # published formula_operands.baseline_eps contract and the eps definition
        # scenario.v1/reverse.v1 use downstream. The vendor's own separately-scraped
        # eps field (state/fundamentals.json) is not trusted here for the same reason
        # payout_ratio is recomputed in fetch_fundamentals.py: independently-scraped
        # vendor fields on the same page are not guaranteed mutually consistent.
        eps = net_income / shares
        price = float(q["close"])
        if min(revenue, net_income, shares, eps, price) <= 0:
            raise ValueError(f"non-positive baseline for {symbol}")
        truth_row = (financial_truth.get("companies") or {}).get(symbol) or {}
        truth_qualified = financial_truth_is_qualified(truth_row)
        activation_status = (
            "ready_snapshot_sensitivity"
            if truth_qualified else "blocked_financial_truth_not_qualified"
        )
        fundamentals_dates.append(f.get("fetched"))
        price_dates.append(q.get("date"))
        companies[symbol] = {
            "symbol": symbol,
            "baseline": {
                "revenue": revenue, "net_income": net_income,
                "shares_out": shares, "eps": eps, "latest_price": price,
            },
            "provenance": {
                "fundamentals_source_url": f.get("source_url"),
                "fundamentals_as_of": f.get("fetched"),
                "price_source_url": f"https://dps.psx.com.pk/company/{symbol}",
                "price_as_of": q.get("date"),
            },
            "baseline_sources": {
                metric: {"source_url": f.get("source_url"), "as_of": f.get("fetched")}
                for metric in ("revenue", "net_income", "shares_out", "eps")
            } | {"latest_price": {"source_url": f"https://dps.psx.com.pk/company/{symbol}", "as_of": q.get("date")}},
            "formula_ids": ["baseline.net_income_per_share", "scenario.v1", "reverse.v1", "expectations_gap.v1"],
            "scenario": None,
            "reverse_expectations": None,
            "market_expectations_gap": None,
            "status": {
                "scenario_lab": activation_status,
                "market_expectations": activation_status,
                "valuation": activation_status,
                "forecast": activation_status,
            },
            "financial_truth_status": truth_row.get("status") or "missing",
            "ebitda": None, "fcf": None, "dcf": None,
        }
    return {
        "schema_version": 1,
        "as_of": {"fundamentals": max(fundamentals_dates), "price": max(price_dates)},
        "pilot_symbols": symbols,
        "assumptions": {"caller_supplied_only": True,
                        "fields": ["revenue_growth_pct", "net_margin_pct", "exit_pe"]},
        "status": _summary_status(companies),
        "companies": companies,
        "formula_operands": {
            "baseline_eps": "net_income / shares_out",
            "scenario": "revenue*(1+growth/100); net_income=revenue*margin/100; eps=net_income/shares_out; price=eps*exit_pe",
            "reverse": "required_eps=latest_price/exit_pe; required_net_income=required_eps*shares_out; required_revenue=required_net_income/(margin/100)",
            "expectations_gap": "required_revenue_growth_pct - revenue_growth_pct",
        },
    }


def _summary_status(companies: dict) -> dict:
    statuses = {
        (row.get("status") or {}).get("scenario_lab")
        for row in companies.values()
    }
    if statuses == {"ready_snapshot_sensitivity"}:
        scenario_status = "ready_snapshot_sensitivity"
    elif statuses == {"blocked_financial_truth_not_qualified"}:
        scenario_status = "blocked_financial_truth_not_qualified"
    else:
        scenario_status = "mixed_financial_truth_qualification"
    return {
        "scenario_lab": scenario_status,
        "market_expectations": scenario_status,
        "valuation": scenario_status,
        "forecast": scenario_status,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=OUT)
    args = ap.parse_args()
    data = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
