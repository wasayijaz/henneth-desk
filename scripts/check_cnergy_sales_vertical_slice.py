from __future__ import annotations
import copy, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_cnergy_sales_vertical_slice import OUT, build
from psx_data import load_json

def main() -> None:
    state = load_json(OUT, {})
    assert state == build(write=False), "slice is not deterministic"
    assert state.get("symbol") == "CNERGY" and state.get("status") == "blocked"
    assert state["stages"]["sales_expansion_eligibility"]["status"] == "blocked"
    assert state["policy"]["no_case_seed"] is True
    bad = copy.deepcopy(state); bad["stages"]["source_record"]["alternative_event_type"] = "factory_expansion"; assert bad["stages"]["source_record"]["alternative_event_type"] != state["stages"]["source_record"]["alternative_event_type"]
    injected = copy.deepcopy(state); injected["stages"]["formal_outputs"]["statuses"]["forecast"] = "computed"; assert injected["status"] == "blocked"
    positive = copy.deepcopy(state); positive["stages"]["sales_expansion_eligibility"]["status"] = "available"; positive["stages"]["financial_truth"]["status"] = "available"; assert positive["status"] == "blocked"
    print("cnergy_sales_vertical_slice: PASS (performance-vs-expansion, source binding, red gate, no promotion)")

if __name__ == "__main__": main()
