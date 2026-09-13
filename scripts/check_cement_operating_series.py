"""Focused checks for the audit-only cement operating series."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
sys.path.insert(0, str(ROOT / "scripts"))

from cement_operating_series import CEMENT_PILOT_SYMBOLS, ObservationSpec, build_state


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def walk(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise AssertionError("non-finite value")
    if isinstance(value, dict):
        for child in value.values():
            walk(child)
    elif isinstance(value, list):
        for child in value:
            walk(child)


def fixture_documents() -> dict:
    return {
        "documents": {
            "issuer:fixture": {
                "doc_id": "issuer:fixture",
                "tickers": ["DGKC"],
                "source": "Issuer registry",
                "source_url": "https://example.com/dgkc.pdf",
                "content_sha256": "fixturehash",
                "local_sha256": "fixturehash",
                "published_at": "2026-08-27T03:00:00+05:00",
                "retrieved_at": "2026-08-27 00:00",
                "facts": [{"fact_id": "fact_fixture", "evidence": [{"page": 7, "text": "FY24 FY23 Cement sales 100 90"}]}],
                "evidence": [{"page": 7, "text": "FY24 FY23 Cement sales 100 90"}],
            }
        }
    }


def fixture_registry() -> dict:
    return {
        "tickers": {
            "DGKC": {
                "document_links": [
                    {
                        "id": "issuer:fixture",
                        "status": "discovered",
                        "source_page": "https://example.com/ir",
                        "first_seen_at": "2026-08-27T03:00:00+05:00",
                    }
                ]
            }
        }
    }


def fixture_financial_series() -> dict:
    return {
        "tickers": {
            "DGKC": {
                "facts": [
                    {
                        "source_url": "https://example.com/dgkc.pdf",
                        "evidence": [
                            {
                                "page": 8,
                                "text": "FY25 FY24 Cement production 120 100 Total Cement sales 118 99",
                            }
                        ],
                    }
                ]
            }
        }
    }


def assert_fixture_contract() -> None:
    spec = ObservationSpec(
        "DGKC",
        "cement_sales_total",
        "2024-06-30",
        100,
        "100",
        "tonnes",
        "issuer:fixture",
        7,
        ("FY24 FY23 Cement sales 100 90",),
        ("fact_fixture",),
    )
    state = build_state(fixture_documents(), fixture_registry(), specs=(spec,), as_of="2026-08-27")
    row = state["companies"]["DGKC"]
    obs = row["metrics"]["cement_sales_total"][0]
    assert obs["readiness"] == "audit_only"
    assert obs["approval_status"] == "not_owner_approved_forecast_input"
    assert obs["model_eligibility"] == "not_model_loadable"
    assert obs["source"]["available_on"] == "2026-08-27T03:00:00+05:00"
    assert obs["source"]["status"] == "official_publication_date"
    assert obs["source"]["source_fact_ids"] == ["fact_fixture"]
    assert obs["source"]["anchor_source_state"] == "state/company_documents.json"
    assert state["companies"]["MLCF"]["status"] == "insufficient_aligned_annual_operating_history"
    assert state["companies"]["LUCK"]["status"] == "missing_retained_cement_operating_history"
    retained_spec = ObservationSpec(
        "DGKC",
        "cement_production",
        "2025-06-30",
        120,
        "120",
        "tonnes",
        "issuer:fixture",
        8,
        ("Cement production 120",),
    )
    retained_state = build_state(
        fixture_documents(),
        fixture_registry(),
        fixture_financial_series(),
        specs=(retained_spec,),
        as_of="2026-08-27",
    )
    retained_obs = retained_state["companies"]["DGKC"]["metrics"]["cement_production"][0]
    assert retained_obs["source"]["anchor_source_state"] == "state/company_financial_series.json"
    assert retained_obs["source"]["text"] == "FY25 FY24 Cement production 120 100 Total Cement sales 118 99"
    bad_spec = ObservationSpec("DGKC", "cement_sales_total", "2024-06-30", 101, "101", "tonnes", "issuer:fixture", 7, ("missing anchor",))
    try:
        build_state(fixture_documents(), fixture_registry(), specs=(bad_spec,), as_of="2026-08-27")
    except ValueError:
        pass
    else:
        raise AssertionError("missing retained anchor did not fail closed")


def assert_real_state() -> None:
    state = load(STATE / "company_intel" / "cement_operating_series.json")
    walk(state)
    assert state.get("schema_version") == 1
    assert state.get("policy", {}).get("audit_only") is True
    assert state.get("policy", {}).get("formal_engine_eligibility_unchanged") is True
    assert set(state.get("pilot_symbols") or []) == set(CEMENT_PILOT_SYMBOLS)
    assert set(state.get("companies") or {}) == set(CEMENT_PILOT_SYMBOLS)
    dgkc = state["companies"]["DGKC"]
    assert dgkc["status"] == "audit_only_series_available"
    assert dgkc["activation_status"] == "blocked_audit_only_no_model_adapter"
    assert dgkc["observation_count"] >= 36
    assert dgkc["annual_period_count"] >= 8
    assert dgkc["lane_assessment"]["pilot_peer_operating_lane"] == "blocked_insufficient_aligned_peer_history"
    required_metrics = {"clinker_production", "cement_production", "cement_sales_local", "cement_sales_export", "cement_sales_total", "clinker_sales"}
    assert required_metrics <= set(dgkc["metrics"])
    expected_fy25 = {
        "cement_production": ("3,762,813", 3762813, "Cement production 3,762,813"),
        "cement_sales_total": ("3,770,701", 3770701, "Total Cement sales 3,770,701"),
        "cement_sales_local": ("3,611,075", 3611075, "Local Cement sales 3,611,075"),
        "cement_sales_export": ("159,626", 159626, "Export cement sales 159,626"),
        "clinker_sales": ("1,070,871", 1070871, "Clinker sales 1,070,871"),
    }
    seen_ids = set()
    for metric, observations in dgkc["metrics"].items():
        periods = [obs["period_end"] for obs in observations]
        assert periods == sorted(periods), f"{metric} not sorted"
        for obs in observations:
            assert obs["observation_id"] not in seen_ids
            seen_ids.add(obs["observation_id"])
            assert obs["readiness"] == "audit_only"
            assert obs["approval_status"] == "not_owner_approved_forecast_input"
            assert obs["model_eligibility"] == "not_model_loadable"
            source = obs["source"]
            for field in ("document_id", "source_url", "page", "text", "content_sha256", "retained_on", "status"):
                assert source.get(field) not in (None, ""), f"{obs['observation_id']} missing {field}"
            assert str(source["source_url"]).startswith("https://")
            assert isinstance(source["page"], int) and source["page"] > 0
            assert source["anchor_source_state"] in {"state/company_documents.json", "state/company_financial_series.json"}
            assert obs["raw_value"] in source["text"]
            if source["status"] == "official_publication_date":
                assert source.get("available_on") not in (None, "")
            else:
                assert source["status"] == "publication_date_not_retained_audit_only"
                assert source.get("available_on") is None
    for metric, (raw_value, value, anchor) in expected_fy25.items():
        matches = [obs for obs in dgkc["metrics"][metric] if obs["period_end"] == "2025-06-30"]
        assert len(matches) == 1, f"{metric} FY2025 observation missing/duplicated"
        obs = matches[0]
        source = obs["source"]
        assert obs["raw_value"] == raw_value
        assert obs["value"] == value
        assert obs["readiness"] == "audit_only"
        assert obs["model_eligibility"] == "not_model_loadable"
        assert obs["approval_status"] == "not_owner_approved_forecast_input"
        assert source["document_id"] == "psx:260947"
        assert source["source_url"] == "https://dps.psx.com.pk/download/document/260947.pdf"
        assert source["page"] == 119
        assert source["published_at"] == "2025-10-03T11:05:00+05:00"
        assert source["available_on"] is None
        assert source["status"] == "publication_date_not_retained_audit_only"
        assert source["anchor_source_state"] == "state/company_financial_series.json"
        assert anchor in source["text"]
        assert raw_value in source["text"]
    assert state["companies"]["MLCF"]["status"] == "insufficient_aligned_annual_operating_history"
    assert state["companies"]["MLCF"]["observation_count"] == 0
    mlcf_requirements = state["companies"]["MLCF"].get("qualification_requirements") or []
    assert {row.get("requirement") for row in mlcf_requirements} == {
        "aligned_annual_cement_operating_rows",
        "event_specific_operating_bridge",
    }
    annual_req = next(row for row in mlcf_requirements if row["requirement"] == "aligned_annual_cement_operating_rows")
    assert annual_req["required_periods"] == 5
    assert annual_req["current_periods"] == 0
    assert annual_req["status"] == "missing"
    assert "cement_sales_total" in annual_req["required_metrics"]
    assert "source-bound period" in annual_req["evidence_needed"]
    bridge_req = next(row for row in mlcf_requirements if row["requirement"] == "event_specific_operating_bridge")
    assert bridge_req["required_periods"] == 2
    assert bridge_req["current_periods"] == 0
    assert "PIOC-acquired dispatches" in bridge_req["evidence_needed"]
    next_actions = state["companies"]["MLCF"].get("next_evidence_actions") or []
    assert [row.get("action") for row in next_actions] == [
        "find_or_retain_annual_operating_table",
        "separate_pioc_acquisition_effect",
    ]
    assert "post-acquisition combined dispatch" in next_actions[1]["acceptance"]
    assert state["companies"]["LUCK"]["status"] == "missing_retained_cement_operating_history"
    assert state["companies"]["LUCK"]["observation_count"] == 0
    for row in state["companies"].values():
        assert set(row["downstream_status"].values()) == {"not_activated"}
    model_inputs = load(STATE / "company_intel" / "financial_model_inputs.json")
    assert model_inputs.get("source") == "state/company_financial_series.json"
    assert model_inputs.get("model_adapter_source") is None
    assert "cement_operating_series" not in json.dumps(model_inputs)
    for path in ("forecast_readiness.json", "financial_forecasts.json", "formal_valuations.json", "market_expectations.json"):
        payload = load(STATE / "company_intel" / path)
        assert "cement_operating_series" not in json.dumps(payload), f"{path} consumed audit-only operating series"


def main() -> None:
    assert_fixture_contract()
    assert_real_state()
    print("cement_operating_series: PASS")


if __name__ == "__main__":
    main()
