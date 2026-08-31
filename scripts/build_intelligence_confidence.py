"""Thin writer for deterministic Intelligence Confidence v1."""
from psx_data import STATE, load_json, save_json
from intelligence_confidence import build_intelligence_confidence


OUT = STATE / "company_intel" / "intelligence_confidence.json"


def build():
    signal_state = load_json(STATE / "company_intel" / "signal_clusters.json", {"companies": {}})
    operating_events = load_json(STATE / "company_intel" / "operating_events.json", {"companies": {}})
    event_studies = load_json(STATE / "company_intel" / "event_studies.json", {"studies": {}})
    financial_model_inputs = load_json(STATE / "company_intel" / "financial_model_inputs.json", {"companies": {}})
    financial_truth_qualification = load_json(STATE / "company_intel" / "financial_truth_qualification.json", {"companies": {}})
    result = build_intelligence_confidence(
        signal_state,
        operating_events,
        event_studies,
        financial_model_inputs,
        financial_truth_qualification,
    )
    save_json(OUT, result)
    total = sum((row.get("assessment_count") or 0) for row in result.get("companies", {}).values())
    print(f"intelligence_confidence: {len(result.get('companies', {}))} companies, {total} assessments")
    return result


if __name__ == "__main__":
    build()
