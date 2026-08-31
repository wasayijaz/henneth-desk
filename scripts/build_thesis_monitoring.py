"""Build the Company Intelligence thesis-monitoring state."""
from __future__ import annotations

from psx_data import STATE, load_json, save_json
from thesis_monitoring import build_thesis_monitoring

OUT = STATE / "company_intel" / "thesis_monitoring.json"


def build() -> dict:
    signal_state = load_json(STATE / "company_intel" / "signal_clusters.json", {"companies": {}})
    financial_model_state = load_json(STATE / "company_intel" / "financial_model_inputs.json", {"companies": {}})
    financial_truth_state = load_json(STATE / "company_intel" / "financial_truth_qualification.json", {"companies": {}})
    # Source state carries the cycle boundary; passing it through keeps output
    # byte-stable across reruns of an unchanged cycle.
    as_of = signal_state.get("as_of") or financial_model_state.get("as_of") or financial_truth_state.get("as_of")
    result = build_thesis_monitoring(signal_state, financial_model_state, financial_truth_state, as_of=as_of)
    save_json(OUT, result)
    total = sum((row.get("active_thesis_count") or 0) for row in result.get("companies", {}).values())
    print(f"thesis_monitoring: {len(result.get('companies', {}))} companies, {total} active theses")
    return result


if __name__ == "__main__":
    build()
