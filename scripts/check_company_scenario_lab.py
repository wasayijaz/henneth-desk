"""Focused checker for the company scenario lab snapshot and formulas."""
from __future__ import annotations
import json, math, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from company_scenario_lab import forward_scenario, market_expectations_gap, reverse_expectations, parse_scaled
from build_company_scenario_lab import build
from ci_checker_helpers import without_root_meta

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state" / "company_intel" / "scenario_lab.json"
PILOT = ROOT / "state" / "company_profiles.json"

def fail(msg):
    raise AssertionError(msg)

def main():
    d = json.loads(STATE.read_text(encoding="utf-8")); p = json.loads(PILOT.read_text(encoding="utf-8"))
    expected = p["pilot"]["symbols"]
    if d["pilot_symbols"] != expected or len(d["companies"]) != 20: fail("exact pilot mismatch")
    for s in expected:
        c = d["companies"][s]; b = c["baseline"]
        if c["financial_truth_status"] != "not_qualified": fail(f"financial truth binding {s}")
        if set(c["status"].values()) != {"blocked_financial_truth_not_qualified"}: fail(f"financial truth gate {s}")
        if abs(b["eps"] - b["net_income"] / b["shares_out"]) / b["eps"] > .01: fail(f"eps mismatch {s}")
        if any(not math.isfinite(float(b[k])) or b[k] <= 0 for k in b): fail(f"bad baseline {s}")
        if not c["provenance"]["fundamentals_source_url"] or not c["provenance"]["price_source_url"]: fail(f"source {s}")
        if not c["provenance"]["fundamentals_as_of"] or not c["provenance"]["price_as_of"]: fail(f"date {s}")
        if c["scenario"] is not None or c["reverse_expectations"] is not None or c["market_expectations_gap"] is not None: fail("chosen assumptions present")
        if "expectations_gap.v1" not in c["formula_ids"]: fail(f"gap formula missing {s}")
        if c["ebitda"] is not None or c["fcf"] is not None or c["dcf"] is not None: fail("blocked null missing")
    if set(d["status"].values()) != {"blocked_financial_truth_not_qualified"}: fail("summary financial truth gate")
    b = {"revenue": 1000.0, "shares_out": 100.0, "latest_price": 11.0}
    s = forward_scenario(b, 10, 20, 5)
    if not math.isclose(s["scenario_revenue"], 1100) or not math.isclose(s["scenario_eps"], 2.2) or not math.isclose(s["multiple_implied_price"], 11): fail("golden formula")
    r = reverse_expectations(b, 5, 20)
    if not math.isclose(r["required_eps"], 2.2) or not math.isclose(r["required_revenue"], 1100): fail("reverse formula")
    if not math.isclose(reverse_expectations(b, s["exit_pe"], s["net_margin_pct"])["required_revenue_growth_pct"], 10): fail("roundtrip")
    gap = market_expectations_gap(b, 5, 20, 5)
    if not math.isclose(gap["expectations_gap_pct"], 5): fail("expectations gap formula")
    for args in [(b, -100, 20, 5), (b, 1, 101, 5), (b, 1, 20, 0)]:
        try: forward_scenario(*args); fail("invalid accepted")
        except ValueError: pass
    # The required blocked status contains the literal word forecast; reject
    # forbidden labels/prose everywhere else while allowing that status key.
    scrub = json.loads(json.dumps(d))
    scrub.get("status", {}).pop("forecast", None)
    for company in scrub.get("companies", {}).values():
        company.get("status", {}).pop("forecast", None)
    if any(x in json.dumps(scrub).lower() for x in ("forecast", "fair value", "target", "advice", "probability")): fail("forbidden language")
    with tempfile.TemporaryDirectory() as td:
        rebuilt = build(); old = json.dumps(without_root_meta(d), sort_keys=True); new = json.dumps(without_root_meta(rebuilt), sort_keys=True)
        if old != new: fail("non-deterministic rebuild")
        truth = json.loads((ROOT / "state" / "company_intel" / "financial_truth_qualification.json").read_text(encoding="utf-8"))
        truth["companies"][expected[0]]["status"] = "qualified"
        truth_path = Path(td) / "financial_truth_qualification.json"
        truth_path.write_text(json.dumps(truth), encoding="utf-8")
        positive = build(financial_truth_path=truth_path)
        first = positive["companies"][expected[0]]
        if first["status"]["scenario_lab"] != "ready_snapshot_sensitivity": fail("qualified positive activation")
        if first["financial_truth_status"] != "qualified": fail("qualified positive binding")
        if positive["companies"][expected[1]]["status"]["scenario_lab"] != "blocked_financial_truth_not_qualified": fail("mixed truth isolation")
    print("company scenario lab: PASS (20 rows, formulas, reverse, bounds, provenance, deterministic)")

if __name__ == "__main__": main()
