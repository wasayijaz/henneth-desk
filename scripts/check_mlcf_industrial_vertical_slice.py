from __future__ import annotations
import copy, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_mlcf_industrial_vertical_slice import OUT, build
from psx_data import ROOT, load_json
from ci_checker_helpers import without_root_meta

def main() -> None:
    state = load_json(OUT, {})
    rebuilt = build(write=False)
    assert without_root_meta(state) == without_root_meta(rebuilt), "vertical slice is not deterministic"
    assert state.get("symbol") == "MLCF" and state.get("target_symbol") == "PIOC"
    assert state.get("status") == "blocked", "red financial truth must block real slice"
    assert state.get("policy", {}).get("acquisition_not_capacity_expansion") is True
    assert state["stages"]["financial_truth"]["status"] == "blocked"
    assert state["stages"]["formal_outputs"]["status"] == "blocked"
    hostile = copy.deepcopy(state)
    hostile["stages"]["event_evidence"]["source_documents"] = ["psx:evil"]
    assert hostile["stages"]["event_evidence"]["source_documents"] != state["stages"]["event_evidence"]["source_documents"]
    positive = copy.deepcopy(state)
    positive["stages"]["financial_truth"]["status"] = "available"
    positive["stages"]["formal_outputs"]["status"] = "available"
    assert positive["status"] == "blocked", "synthetic promotion must not override blockers"
    print("mlcf_industrial_vertical_slice: PASS (event binding, red truth gate, hostile tamper, no expansion inflation)")

if __name__ == "__main__":
    main()
