"""Build the deterministic Evidence Watchlist v1 state."""
from __future__ import annotations

import argparse
from pathlib import Path

from evidence_watchlist import build_evidence_watchlist
from psx_data import STATE, load_json, save_json


OUT = STATE / "company_intel" / "evidence_watchlist.json"


def _with_existing_root_meta(path: Path, result: dict) -> dict:
    existing = load_json(path, {})
    meta = existing.get("_meta") if isinstance(existing, dict) else None
    if not isinstance(meta, dict):
        return result
    return {**result, "_meta": meta}


def build(output_path: Path = OUT) -> dict:
    profiles = load_json(STATE / "company_profiles.json", {})
    pilot = (profiles.get("pilot") or {}).get("symbols") or []
    thesis_state = load_json(STATE / "company_intel" / "thesis_monitoring.json", {"companies": {}})
    management_delivery = load_json(STATE / "company_intel" / "management_delivery.json", {"companies": {}})
    confidence_state = load_json(STATE / "company_intel" / "intelligence_confidence.json", {"companies": {}})
    financial_model_inputs = load_json(STATE / "company_intel" / "financial_model_inputs.json", {"companies": {}})
    financial_truth = load_json(STATE / "company_intel" / "financial_truth_qualification.json", {"companies": {}})
    operating_events = load_json(STATE / "company_intel" / "operating_events.json", {"companies": {}})
    signal_clusters = load_json(STATE / "company_intel" / "signal_clusters.json", {"companies": {}})
    result = build_evidence_watchlist(
        thesis_state,
        management_delivery,
        confidence_state,
        financial_model_inputs,
        financial_truth,
        operating_events,
        signal_clusters,
        pilot_symbols=list(pilot),
    )
    save_json(output_path, _with_existing_root_meta(output_path, result))
    active = sum(1 for row in result.get("companies", {}).values() if row.get("items"))
    items = sum(len(row.get("items") or []) for row in result.get("companies", {}).values())
    print(f"evidence_watchlist: {len(result.get('companies', {}))} companies, {active} active, {items} items")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    build(args.out)


if __name__ == "__main__":
    main()
