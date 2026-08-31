"""Build compact observed IntelligenceCase seeds from retained official evidence.

This is intentionally not a generic case engine. The current product need is
one cement/industrial, one E&P, and one sales-led AI data-centre observed
seed. Later statuses or sector models must earn their own dedicated
builders/checks.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
import re
from typing import Any

from operating_events import evidence_hash, stable_id
from psx_data import STATE, load_json, save_json


OUT = STATE / "company_intel" / "intelligence_cases.json"
CASE_PRODUCT_VERSION = "observed_intelligence_case_seed_v5"
LIFECYCLE = ["Observed", "Corroborated", "Modelled", "Validated", "Published", "Monitoring", "Closed"]
PKT = timezone(timedelta(hours=5))

MLCF_CASE_ID = "case_mlcf_pioc_control_observed_v1"
PUBLIC_OFFER_EVENT_ID = "evt_cb44dc32c91b0c5712a5"
FOLLOW_THROUGH_EVENT_ID = "evt_25bfb52e721191c7b644"
PUBLIC_OFFER_DOC_ID = "psx:267429"
FOLLOW_THROUGH_DOC_ID = "psx:275425"
MLCF_CANONICAL_CONTROL_EVENT_ID = "evt_6e9b520a122b8f2d4a59"
MLCF_LEGACY_CONTROL_EVENT_ID = PUBLIC_OFFER_EVENT_ID
MLCF_FOLLOW_THROUGH_ALIAS_EVENT_ID = FOLLOW_THROUGH_EVENT_ID
MLCF_LEGACY_FOLLOW_THROUGH_EVENT_ID = FOLLOW_THROUGH_EVENT_ID
MLCF_INDEPENDENT_CANONICAL_EVENT_BINDING = "independent_operating_event"
MLCF_LEGACY_ALIAS_EVENT_BINDING = "legacy_alias_no_independent_operating_event"
MLCF_PRIMARY_CONTROL_EVIDENCE_SHA256 = "70a110272f96813a4d6693b596c99d9dbc4c4781d42a519543557a04ec4c581f"
MLCF_FOLLOW_THROUGH_EVIDENCE_SHA256 = "725f04c3c6d7f36bbffd6c205d574750f65b8c0546ae9f1b50683fe07b292b66"
MLCF_PRIMARY_CONTROL_CONTENT_SHA256 = "98cf83c9a286999c8006a7f73f490248f26694c9edbfc815b3dbd9188ee22a54"
MLCF_FOLLOW_THROUGH_CONTENT_SHA256 = "744a0c710043d6e0a7de36bb99f21ca50f0f9346f6972b957f6733a47deae11f"
MLCF_PRIMARY_CONTROL_URL = "https://dps.psx.com.pk/download/document/267429.pdf"
MLCF_FOLLOW_THROUGH_URL = "https://dps.psx.com.pk/download/document/275425.pdf"
MLCF_COUNTER_REQUIREMENTS = {
    "annual_income_triplets": 5,
    "qualified_reported_quarter_fact_sets": 8,
    "annual_operating_cash_flow": 5,
}
HEX64 = re.compile(r"^[0-9a-f]{64}$", re.I)

MARI_CASE_ID = "case_mari_working_interest_observed_v1"
MARI_EVENT_ID = "evt_eddfcc381018cb0dff43"
MARI_CANONICAL_CONTROL_EVENT_ID = "evt_b25decfc180474cbe066"
MARI_DOC_ID = "psx:260446"
MARI_DOC_HASH = "c13ccb4de58ad005bca106942721490593fe219ff45906c68280ea7856192e42"
MARI_EVIDENCE_SHA256 = "dd83c62cb781e2a57f5ae595a7184ea786a3e5890f7f7cc96cd93e23f958a177"
MARI_SOURCE_URL = "https://dps.psx.com.pk/download/document/260446.pdf"
MARI_FOLLOW_THROUGH_EVENT_ID = "evt_5cc9795abc3e4cfdda51"
MARI_FOLLOW_THROUGH_DOC_ID = "psx:271327"
MARI_FOLLOW_THROUGH_DOC_HASH = "e53fccd6eca58c685dbf9225140056303be704b1f389b876ba33d87aa4b687b3"
MARI_FOLLOW_THROUGH_SOURCE_URL = "https://dps.psx.com.pk/download/document/271327.pdf"

MARI_SALES_CASE_ID = "case_mari_sky47_karakoram1_launch_sales_observed_v1"
MARI_SALES_CANONICAL_EVENT_ID = "evt_e9068dbe4b6b8493a0cb"
MARI_SALES_DOC_ID = "psx:280337"
MARI_SALES_SOURCE_URL = "https://dps.psx.com.pk/download/document/280337.pdf"
MARI_SALES_TITLE = "Launch of Pakistan First and Largest Purpose-Built AI Ready Data Centre Campus"
MARI_SALES_PUBLISHED_AT = "2026-07-24T16:26:00+05:00"
MARI_SALES_EFFECTIVE_DATE = "2026-07-24"
MARI_SALES_EXACT_EVENT_ID_BINDING = "exact_canonical_operating_event"
MARI_SALES_RECOMPUTED_EVENT_ID_BINDING = "recomputed_from_accepted_source"
MARI_SALES_CAMPUS_RE = re.compile(r"\b(?:sky\s*47|data\s+cent(?:er|re)\s+campus)\b", re.I)
MARI_SALES_FACILITY_RE = re.compile(r"karakoram[-\s]0?1", re.I)
MARI_SALES_KERNEL_FIELDS = (
    "incremental_revenue_pkr",
    "contracted_capacity_mw",
    "utilisation_pct",
    "achieved_pricing",
    "capex_schedule_pkr",
    "commissioning_or_ramp_schedule",
    "incremental_margin_pct",
    "incremental_eps_pkr",
)


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        text = f"{text}T00:00:00"
    elif len(text) == 16 and text[10] == " ":
        text = text.replace(" ", "T") + ":00"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=PKT)
    return parsed.astimezone(PKT)


def _iso_time(value: Any) -> str | None:
    parsed = _parse_time(value)
    return parsed.isoformat() if parsed else None


def _date(value: Any) -> str | None:
    parsed = _parse_time(value)
    return parsed.date().isoformat() if parsed else None


def _event(ledger: dict[str, Any], symbol: str, event_id: str) -> dict[str, Any] | None:
    for event in (((ledger.get("companies") or {}).get(symbol) or {}).get("events") or []):
        if isinstance(event, dict) and event.get("event_id") == event_id:
            return event
    return None


def _operating_event(operating_events: dict[str, Any], symbol: str, event_id: str) -> dict[str, Any] | None:
    for event in (((operating_events.get("companies") or {}).get(symbol) or {}).get("events") or []):
        if isinstance(event, dict) and event.get("event_id") == event_id:
            return event
    return None


def _document(documents: dict[str, Any], doc_id: str) -> dict[str, Any] | None:
    doc = (documents.get("documents") or {}).get(doc_id)
    return doc if isinstance(doc, dict) else None


def _fail(message: str) -> None:
    raise ValueError(message)


def _require_equal(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        _fail(f"source mismatch for {label}: {actual!r}")


def _require_iso_time(label: str, value: Any, expected: str) -> None:
    _require_equal(label, _iso_time(value), expected)


def _require_date(label: str, value: Any, expected: str) -> None:
    _require_equal(label, _date(value), expected)


def _require_hex64(label: str, value: Any) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        _fail(f"invalid 64-character hash for {label}")
    return value.lower()


def _require_text(label: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"missing source text for {label}")
    return value


def _first_evidence(row: dict[str, Any], label: str) -> dict[str, Any]:
    evidence = row.get("evidence")
    if not isinstance(evidence, list) or not evidence or not isinstance(evidence[0], dict):
        _fail(f"missing evidence row for {label}")
    return evidence[0]


def _available_on(doc: dict[str, Any]) -> str | None:
    return _date(doc.get("available_on") or doc.get("published_at"))


def _validate_counter_section(
    row: dict[str, Any],
    section: str,
) -> dict[str, Any]:
    expected_required = MLCF_COUNTER_REQUIREMENTS[section]
    source = row.get(section)
    if not isinstance(source, dict):
        _fail(f"MLCF financial counter section missing: {section}")
    allowed = {"required", "present", "qualified_periods"}
    if set(source) != allowed:
        _fail(f"MLCF financial counter keys mismatch: {section}")
    required = source.get("required")
    present = source.get("present")
    periods = source.get("qualified_periods")
    if (
        not isinstance(required, int)
        or isinstance(required, bool)
        or not isinstance(present, int)
        or isinstance(present, bool)
        or required < 0
        or present < 0
        or present > required
    ):
        _fail(f"MLCF financial counter range/type mismatch: {section}")
    if not isinstance(periods, list) or len(periods) != present:
        _fail(f"MLCF financial counter period count mismatch: {section}")
    clean_periods = []
    for index, period in enumerate(periods):
        parsed = _date(period)
        if not isinstance(period, str) or parsed != period:
            _fail(f"MLCF financial counter invalid period: {section}[{index}]")
        clean_periods.append(period)
    if required != expected_required or clean_periods != sorted(set(clean_periods), reverse=True):
        _fail(f"MLCF financial counter source semantics mismatch: {section}")
    return {
        "required": required,
        "present": present,
        "qualified_periods": clean_periods,
    }


def _validate_share_count_counter(row: dict[str, Any]) -> dict[str, Any]:
    source = row.get("share_count")
    if not isinstance(source, dict):
        _fail("MLCF share-count counter section missing")
    allowed = {"status", "available_on", "source"}
    approved_allowed = allowed | {"limitation"}
    if set(source) != allowed and set(source) != approved_allowed:
        _fail("MLCF share-count counter keys mismatch")
    status = source.get("status")
    available_on = source.get("available_on")
    source_label = source.get("source")
    if not isinstance(status, str) or not status:
        _fail("MLCF share-count counter status mismatch")
    if available_on is not None and (_date(available_on) != available_on):
        _fail("MLCF share-count counter available_on mismatch")
    if status == "missing_official_share_count_capital_note_tie_out":
        if available_on is not None or source_label is not None:
            _fail("MLCF missing share-count counter carries unsupported evidence")
        return source
    if status != "official_share_count_capital_note_tied_out":
        _fail("MLCF share-count counter source semantics mismatch")
    if not isinstance(source_label, dict) or set(source_label) != {"id", "label", "path", "url"}:
        _fail("MLCF qualified share-count source shape mismatch")
    if not all(isinstance(source_label.get(key), str) and source_label.get(key) for key in ("id", "label", "url")):
        _fail("MLCF qualified share-count source binding mismatch")
    if source_label.get("path") is not None or available_on is None:
        _fail("MLCF qualified share-count source availability mismatch")
    return source


def _financial_truth_counters(qualification: dict[str, Any] | None = None) -> dict[str, Any]:
    if qualification is None:
        qualification = load_json(STATE / "company_intel" / "financial_truth_qualification.json", {})
    if not isinstance(qualification, dict):
        _fail("MLCF financial truth qualification source is not an object")
    if qualification.get("schema_version") != "financial_truth_qualification_v2":
        _fail("MLCF financial truth qualification schema mismatch")
    if qualification.get("source") != "retained_state_only":
        _fail("MLCF financial truth qualification source provenance mismatch")
    policy = qualification.get("policy")
    if not isinstance(policy, dict) or policy.get("does_not_activate_formal_engines") is not True:
        _fail("MLCF financial truth qualification formal-engine policy mismatch")
    row = (qualification.get("companies") or {}).get("MLCF") or {}
    if not isinstance(row, dict):
        _fail("MLCF financial truth qualification row is not an object")
    if row.get("symbol") != "MLCF" or row.get("status") not in {"not_qualified", "qualified"}:
        _fail("MLCF financial truth qualification state mismatch")
    downstream = row.get("downstream")
    if not isinstance(downstream, dict):
        _fail("MLCF financial truth downstream activation mismatch")
    financial_tie_out = row.get("financial_tie_out")
    if not isinstance(financial_tie_out, dict):
        _fail("MLCF financial truth tie-out state mismatch")
    if row["status"] == "not_qualified":
        if financial_tie_out.get("status") != "blocked" or any(
            downstream.get(key) != "blocked_financial_truth_not_qualified"
            for key in ("forecast", "valuation", "market_expectations")
        ):
            _fail("MLCF unqualified truth activated a formal output")
    elif financial_tie_out.get("status") != "qualified" or any(
        downstream.get(key) != "not_activated_owner_approved_forward_inputs_required"
        for key in ("forecast", "valuation", "market_expectations")
    ):
        _fail("MLCF qualified truth activation boundary mismatch")
    return {
        "annual_income_triplets": _validate_counter_section(row, "annual_income_triplets"),
        "qualified_reported_quarter_fact_sets": _validate_counter_section(row, "qualified_reported_quarter_fact_sets"),
        "annual_operating_cash_flow": _validate_counter_section(row, "annual_operating_cash_flow"),
        "share_count": _validate_share_count_counter(row),
    }


def _null_kernel_requirements() -> dict[str, dict[str, Any]]:
    return {
        field: {
            "value": None,
            "source_label": "retained_state_only:no_source_qualified_event_input",
            "status": "missing_source_bound_input",
        }
        for field in (
            "incremental_revenue_pkr",
            "incremental_margin_pct",
            "incremental_eps_pkr",
            "incremental_operating_cash_flow_pkr",
            "incremental_debt_pkr",
            "incremental_share_count",
            "cement_capacity_units",
            "commissioning_or_ramp_schedule",
            "capex_schedule_pkr",
            "fuel_power_freight_cost_schedule",
        )
    }


def _validate_mlcf_legacy_source(
    event: dict[str, Any],
    doc: dict[str, Any],
    *,
    legacy_event_id: str,
    canonical_event_id: str,
    canonical_event_id_binding: str,
    doc_id: str,
    source_url: str,
    page: int,
    content_sha256: str,
    evidence_sha256: str,
    published_at: str,
    effective_date: str,
    available_on: str,
) -> dict[str, Any]:
    _require_equal(f"{legacy_event_id}.event_id", event.get("event_id"), legacy_event_id)
    _require_equal(f"{legacy_event_id}.doc_id", event.get("doc_id"), doc_id)
    _require_equal(f"{legacy_event_id}.event_type", event.get("event_type"), "acquisition")
    _require_equal(f"{legacy_event_id}.priority_weight", event.get("priority_weight"), 4)
    _require_equal(f"{legacy_event_id}.tickers", event.get("tickers"), ["MLCF"])
    _require_iso_time(f"{legacy_event_id}.event_date", event.get("event_date"), published_at)
    evidence = _first_evidence(event, legacy_event_id)
    _require_equal(f"{legacy_event_id}.evidence.source_url", evidence.get("source_url"), source_url)
    _require_equal(f"{legacy_event_id}.evidence.page", evidence.get("page"), page)
    text = _require_text(f"{legacy_event_id}.evidence.text", evidence.get("text"))
    _require_equal(
        f"{legacy_event_id}.evidence_sha256",
        evidence_hash(doc_id, evidence.get("source_url"), evidence.get("page"), text),
        evidence_sha256,
    )
    _require_equal(f"{doc_id}.doc_id", doc.get("doc_id"), doc_id)
    _require_equal(f"{doc_id}.tickers", doc.get("tickers"), ["MLCF"])
    _require_equal(f"{doc_id}.source", doc.get("source"), "PSX DPS")
    _require_equal(f"{doc_id}.source_url", doc.get("source_url"), source_url)
    _require_equal(f"{doc_id}.content_sha256", _require_hex64(f"{doc_id}.content_sha256", doc.get("content_sha256")), content_sha256)
    _require_equal(f"{doc_id}.local_sha256", _require_hex64(f"{doc_id}.local_sha256", doc.get("local_sha256")), content_sha256)
    _require_iso_time(f"{doc_id}.published_at", doc.get("published_at"), published_at)
    _require_equal(f"{doc_id}.available_on", _available_on(doc), available_on)
    _require_date(f"{legacy_event_id}.effective_date", event.get("event_date"), effective_date)
    return {
        "canonical_event_id": canonical_event_id,
        "canonical_event_id_binding": canonical_event_id_binding,
        "legacy_event_id": legacy_event_id,
        "document_id": doc_id,
        "page": page,
        "content_sha256": content_sha256,
        "evidence_sha256": evidence_sha256,
        "published_at": published_at,
        "effective_date": effective_date,
        "available_on": available_on,
    }


def _validate_mlcf_canonical_control_source(event: dict[str, Any]) -> None:
    _require_equal("canonical_control.event_id", event.get("event_id"), MLCF_CANONICAL_CONTROL_EVENT_ID)
    _require_equal("canonical_control.company_id", event.get("company_id"), "MLCF")
    _require_equal("canonical_control.symbol", event.get("symbol"), "MLCF")
    _require_equal("canonical_control.event_type", event.get("event_type"), "acquisition_divestment")
    _require_equal("canonical_control.event_subtype", event.get("event_subtype"), "acquisition")
    _require_equal("canonical_control.intelligence_type", event.get("intelligence_type"), "reported_fact")
    _require_equal("canonical_control.priority_weight", event.get("priority_weight"), 4)
    _require_iso_time("canonical_control.detected_at", event.get("detected_at"), "2025-12-18T12:52:00+05:00")
    _require_equal("canonical_control.effective_date", event.get("effective_date"), "2025-12-18")
    _require_equal("canonical_control.source_url", event.get("source_url"), MLCF_PRIMARY_CONTROL_URL)
    evidence = _first_evidence(event, MLCF_CANONICAL_CONTROL_EVENT_ID)
    _require_equal("canonical_control.evidence.document_id", evidence.get("document_id"), PUBLIC_OFFER_DOC_ID)
    _require_equal("canonical_control.evidence.source", evidence.get("source"), "PSX DPS")
    _require_equal("canonical_control.evidence.source_url", evidence.get("source_url"), MLCF_PRIMARY_CONTROL_URL)
    _require_equal("canonical_control.evidence.page", evidence.get("page"), 3)
    _require_text("canonical_control.evidence.text", evidence.get("text"))
    _require_equal(
        "canonical_control.evidence.content_sha256",
        _require_hex64("canonical_control.evidence.content_sha256", evidence.get("content_sha256")),
        MLCF_PRIMARY_CONTROL_CONTENT_SHA256,
    )
    _require_equal(
        "canonical_control.evidence.evidence_sha256",
        _require_hex64("canonical_control.evidence.evidence_sha256", evidence.get("evidence_sha256")),
        MLCF_PRIMARY_CONTROL_EVIDENCE_SHA256,
    )


def _validate_mari_source(event: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    _require_equal("mari.event_id", event.get("event_id"), MARI_EVENT_ID)
    _require_equal("mari.doc_id", event.get("doc_id"), MARI_DOC_ID)
    _require_equal("mari.event_type", event.get("event_type"), "acquisition")
    _require_equal("mari.priority_weight", event.get("priority_weight"), 4)
    _require_equal("mari.tickers", event.get("tickers"), ["MARI"])
    _require_iso_time("mari.event_date", event.get("event_date"), "2025-09-30T10:46:00+05:00")
    evidence = _first_evidence(event, MARI_EVENT_ID)
    _require_equal("mari.evidence.source_url", evidence.get("source_url"), MARI_SOURCE_URL)
    _require_equal("mari.evidence.page", evidence.get("page"), 1)
    text = _require_text("mari.evidence.text", evidence.get("text"))
    _require_equal(
        "mari.evidence_sha256",
        evidence_hash(MARI_DOC_ID, evidence.get("source_url"), evidence.get("page"), text),
        MARI_EVIDENCE_SHA256,
    )
    _require_equal("mari.doc_id", doc.get("doc_id"), MARI_DOC_ID)
    _require_equal("mari.doc.tickers", doc.get("tickers"), ["MARI"])
    _require_equal("mari.doc.source", doc.get("source"), "PSX DPS")
    _require_equal("mari.doc.source_url", doc.get("source_url"), MARI_SOURCE_URL)
    _require_equal("mari.doc.content_sha256", _require_hex64("mari.doc.content_sha256", doc.get("content_sha256")), MARI_DOC_HASH)
    _require_equal("mari.doc.local_sha256", _require_hex64("mari.doc.local_sha256", doc.get("local_sha256")), MARI_DOC_HASH)
    _require_iso_time("mari.doc.published_at", doc.get("published_at"), "2025-09-30T10:46:00+05:00")
    _require_equal("mari.doc.available_on", _available_on(doc), "2025-09-30")
    return _evidence_ref(event, doc)


def _validate_mari_follow_through_source(
    event: dict[str, Any], doc: dict[str, Any], receipts: dict[str, Any],
) -> dict[str, Any]:
    """Accept the later filing only as source-bound mechanics, never corroboration."""
    _require_equal("mari_follow.event_id", event.get("event_id"), MARI_FOLLOW_THROUGH_EVENT_ID)
    _require_equal("mari_follow.doc_id", event.get("doc_id"), MARI_FOLLOW_THROUGH_DOC_ID)
    _require_equal("mari_follow.event_type", event.get("event_type"), "acquisition")
    _require_equal("mari_follow.priority_weight", event.get("priority_weight"), 4)
    _require_equal("mari_follow.tickers", event.get("tickers"), ["MARI"])
    _require_iso_time("mari_follow.event_date", event.get("event_date"), "2026-02-27T09:03:00+05:00")
    evidence = _first_evidence(event, MARI_FOLLOW_THROUGH_EVENT_ID)
    _require_equal("mari_follow.evidence.source_url", evidence.get("source_url"), MARI_FOLLOW_THROUGH_SOURCE_URL)
    _require_equal("mari_follow.evidence.page", evidence.get("page"), 6)
    text = _require_text("mari_follow.evidence.text", evidence.get("text"))
    if "65% working interest" not in text or "operatorship" not in text:
        _fail("MARI follow-through source does not state the exact working-interest/operator mechanics")
    _require_equal("mari_follow.doc.status", doc.get("status"), "ready")
    _require_equal("mari_follow.doc.source_url", doc.get("source_url"), MARI_FOLLOW_THROUGH_SOURCE_URL)
    _require_equal(
        "mari_follow.doc.content_sha256",
        _require_hex64("mari_follow.doc.content_sha256", doc.get("content_sha256")),
        MARI_FOLLOW_THROUGH_DOC_HASH,
    )
    rows = receipts.get("receipts") if isinstance(receipts, dict) else None
    if not any(
        isinstance(row, dict)
        and row.get("doc_id") == MARI_FOLLOW_THROUGH_DOC_ID
        and row.get("content_sha256") == MARI_FOLLOW_THROUGH_DOC_HASH
        and row.get("status") == "success"
        for row in (rows or [])
    ):
        _fail("MARI follow-through document lacks a matching successful exact-ID receipt")
    return _evidence_ref(event, doc)


def _validate_mari_canonical_control_source(event: dict[str, Any]) -> None:
    _require_equal("MARI canonical event_id", event.get("event_id"), MARI_CANONICAL_CONTROL_EVENT_ID)
    _require_equal("MARI canonical company_id", event.get("company_id"), "MARI")
    _require_equal("MARI canonical symbol", event.get("symbol"), "MARI")
    _require_equal("MARI canonical event_type", event.get("event_type"), "acquisition_divestment")
    _require_equal("MARI canonical event_subtype", event.get("event_subtype"), "acquisition")
    _require_equal("MARI canonical intelligence_type", event.get("intelligence_type"), "reported_fact")
    _require_iso_time("MARI canonical detected_at", event.get("detected_at"), "2025-09-30T10:46:00+05:00")
    _require_equal("MARI canonical effective_date", event.get("effective_date"), "2025-09-30")
    _require_equal("MARI canonical source_url", event.get("source_url"), MARI_SOURCE_URL)
    evidence = _first_evidence(event, MARI_CANONICAL_CONTROL_EVENT_ID)
    _require_equal("MARI canonical evidence.document_id", evidence.get("document_id"), MARI_DOC_ID)
    _require_equal("MARI canonical evidence.source", evidence.get("source"), "PSX DPS")
    _require_equal("MARI canonical evidence.source_url", evidence.get("source_url"), MARI_SOURCE_URL)
    _require_equal("MARI canonical evidence.page", evidence.get("page"), 1)
    _require_equal(
        "MARI canonical evidence.content_sha256",
        _require_hex64("MARI canonical evidence.content_sha256", evidence.get("content_sha256")),
        MARI_DOC_HASH,
    )
    _require_equal(
        "MARI canonical evidence.evidence_sha256",
        _require_hex64("MARI canonical evidence.evidence_sha256", evidence.get("evidence_sha256")),
        MARI_EVIDENCE_SHA256,
    )


def _mlcf_source_join(
    public_offer: dict[str, Any],
    follow_through: dict[str, Any],
    canonical_control: dict[str, Any],
    public_offer_doc: dict[str, Any],
    follow_through_doc: dict[str, Any],
) -> list[dict[str, Any]]:
    _validate_mlcf_canonical_control_source(canonical_control)
    primary = _validate_mlcf_legacy_source(
        public_offer,
        public_offer_doc,
        legacy_event_id=MLCF_LEGACY_CONTROL_EVENT_ID,
        canonical_event_id=MLCF_CANONICAL_CONTROL_EVENT_ID,
        canonical_event_id_binding=MLCF_INDEPENDENT_CANONICAL_EVENT_BINDING,
        doc_id=PUBLIC_OFFER_DOC_ID,
        source_url=MLCF_PRIMARY_CONTROL_URL,
        page=3,
        content_sha256=MLCF_PRIMARY_CONTROL_CONTENT_SHA256,
        evidence_sha256=MLCF_PRIMARY_CONTROL_EVIDENCE_SHA256,
        published_at="2025-12-18T12:52:00+05:00",
        effective_date="2025-12-18",
        available_on="2025-12-18",
    )
    follow = _validate_mlcf_legacy_source(
        follow_through,
        follow_through_doc,
        legacy_event_id=MLCF_LEGACY_FOLLOW_THROUGH_EVENT_ID,
        canonical_event_id=MLCF_FOLLOW_THROUGH_ALIAS_EVENT_ID,
        canonical_event_id_binding=MLCF_LEGACY_ALIAS_EVENT_BINDING,
        doc_id=FOLLOW_THROUGH_DOC_ID,
        source_url=MLCF_FOLLOW_THROUGH_URL,
        page=4,
        content_sha256=MLCF_FOLLOW_THROUGH_CONTENT_SHA256,
        evidence_sha256=MLCF_FOLLOW_THROUGH_EVIDENCE_SHA256,
        published_at="2026-04-28T10:25:00+05:00",
        effective_date="2026-04-28",
        available_on="2026-04-28",
    )
    return [
        {"role": "primary_control", **primary},
        {"role": "operating_follow_through", **follow},
    ]


def _cement_input_readiness(source_join: list[dict[str, Any]], counters: dict[str, Any]) -> dict[str, Any]:
    if len(source_join) != 2:
        raise ValueError("MLCF cement readiness source join mismatch")
    return {
        "status": "observed_only",
        "kernel_activation": "blocked",
        "attribution": {
            "acquirer": "MLCF",
            "target": "PIOC",
            "follow_through": "dispatch_inclusion",
        },
        "source_join": source_join,
        "financial_truth_counters": counters,
        "event_specific_kernel_requirements": _null_kernel_requirements(),
        "guardrails": {
            "dispatch_inclusion_not_standalone_pioc_earnings_or_capacity_impact": True,
            "no_numeric_model_output": True,
        },
    }


def _evidence_ref(event: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    evidence = (event.get("evidence") or [{}])[0]
    return {
        "event_id": event.get("event_id"),
        "document_id": event.get("doc_id"),
        "document_title": doc.get("title"),
        "document_published_at": _iso_time(doc.get("published_at") or event.get("event_date")),
        "document_retrieved_at": _iso_time(doc.get("retrieved_at")),
        "content_sha256": doc.get("content_sha256"),
        "source": doc.get("source") or "PSX DPS",
        "source_url": evidence.get("source_url") or doc.get("source_url"),
        "page": evidence.get("page"),
        "text": evidence.get("text"),
        "event_date": _iso_time(event.get("event_date")),
    }


def _source_cutoff(refs: list[dict[str, Any]]) -> str:
    parsed = [
        _parse_time(ref.get("document_retrieved_at") or ref.get("document_published_at"))
        for ref in refs
    ]
    parsed = [value for value in parsed if value is not None]
    return (max(parsed) if parsed else datetime.now(PKT).replace(microsecond=0)).isoformat()


def _policy(*, deterministic_derived_context: bool = False) -> dict[str, bool]:
    policy = {
        "observed_only": True,
        "no_forecast": True,
        "no_valuation": True,
        "no_market_expectations": True,
        "no_recommendation": True,
        "reported_values_only": not deterministic_derived_context,
    }
    if deterministic_derived_context:
        policy["deterministic_derived_context_only"] = True
    return policy


def _finite_positive(label: str, value: Any) -> float:
    if type(value) is int and abs(value) > 10**16:
        _fail(f"MLCF market context integer magnitude is invalid: {label}")
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        _fail(f"MLCF market context invalid positive numeric value: {label}")
    return float(value)


def _finite_number(label: str, value: Any) -> float:
    if type(value) is int and abs(value) > 10**16:
        _fail(f"MLCF market context integer magnitude is invalid: {label}")
    if type(value) not in (int, float) or not math.isfinite(value):
        _fail(f"MLCF market context invalid numeric value: {label}")
    return float(value)


def _history_cutoff(label: str, history: Any) -> datetime:
    if not isinstance(history, list) or not history:
        _fail(f"{label} market context history is missing")
    dates: list[datetime] = []
    for index, row in enumerate(history):
        if not isinstance(row, dict):
            _fail(f"{label} market context history row is invalid: {index}")
        date = _parse_time(row.get("date"))
        if date is None:
            _fail(f"{label} market context history date is invalid: {index}")
        dates.append(date)
    return max(dates)


def _market_context(
    event_studies: dict[str, Any],
    history: Any,
    *,
    label: str,
    symbol: str,
    event_id: str,
    effective_date: str,
    baseline_date: str,
) -> tuple[dict[str, Any], datetime]:
    """Return a source-bound historical outcome for one exact observed event.

    This deliberately publishes raw-price context only. It is not an analogue
    aggregate, causal attribution, financial output, forecast, or valuation input.
    """
    studies = event_studies.get("studies") if isinstance(event_studies, dict) else None
    if not isinstance(studies, dict):
        _fail(f"{label} market context study index is missing")
    study = studies.get(event_id)
    if not isinstance(study, dict):
        _fail(f"{label} market context study is missing")
    _require_equal(
        f"{label} market context.study_id",
        study.get("study_id"),
        f"study_{event_id.removeprefix('evt_')}",
    )
    _require_equal(f"{label} market context.event_id", study.get("event_id"), event_id)
    _require_equal(f"{label} market context.symbol", study.get("symbol"), symbol)
    _require_equal(f"{label} market context.event_type", study.get("event_type"), "acquisition_divestment")
    _require_equal(f"{label} market context.effective_date", study.get("effective_date"), effective_date)
    history_cutoff = _history_cutoff(label, history)
    data_cutoff = _parse_time(study.get("data_cutoff"))
    if data_cutoff is None or data_cutoff != history_cutoff:
        _fail(f"{label} market context cutoff does not match retained history")

    baseline = study.get("baseline")
    if not isinstance(baseline, dict):
        _fail(f"{label} market context baseline is missing")
    _require_equal(f"{label} market context.baseline.status", baseline.get("status"), "available")
    _require_equal(f"{label} market context.baseline.selected_date", baseline.get("selected_date"), baseline_date)
    _finite_positive("baseline.selected_close", baseline.get("selected_close"))
    baseline_provenance = baseline.get("provenance")
    if not isinstance(baseline_provenance, dict):
        _fail(f"{label} market context baseline provenance is missing")
    history_file = f"state/history/{symbol}.json"
    _require_equal(f"{label} market context.baseline.history_file", baseline_provenance.get("history_file"), history_file)
    _require_equal(f"{label} market context.baseline.provenance_date", baseline_provenance.get("selected_date"), baseline_date)

    horizons = study.get("horizons")
    if not isinstance(horizons, dict):
        _fail(f"{label} market context horizons are missing")
    items: list[dict[str, Any]] = []
    mature_endpoints: list[datetime] = []
    for horizon in ("1Q", "2Q", "4Q", "8Q"):
        row = horizons.get(horizon)
        if not isinstance(row, dict):
            _fail(f"{label} market context horizon is missing: {horizon}")
        provenance = row.get("provenance")
        if not isinstance(provenance, dict):
            _fail(f"{label} market context horizon provenance is missing: {horizon}")
        _require_equal(f"{label} market context.{horizon}.history_file", provenance.get("history_file"), history_file)
        _require_equal(f"{label} market context.{horizon}.baseline_date", provenance.get("baseline_date"), baseline_date)
        status = row.get("status")
        if status == "mature":
            endpoint = row.get("selected_date")
            if not isinstance(endpoint, str) or _date(endpoint) != endpoint:
                _fail(f"{label} market context mature endpoint is invalid: {horizon}")
            _require_equal(f"{label} market context.{horizon}.endpoint_date", provenance.get("endpoint_date"), endpoint)
            endpoint_date = _parse_time(endpoint)
            if endpoint_date is None or endpoint_date > history_cutoff:
                _fail(f"{label} market context mature endpoint exceeds retained history: {horizon}")
            _finite_positive(f"{horizon}.selected_close", row.get("selected_close"))
            result = _finite_number(f"{horizon}.return_pct", row.get("return_pct"))
            mature_endpoints.append(endpoint_date)
            items.append({
                "id": horizon,
                "text": f"Raw price return: {result:.2f}% ({baseline_date} to {endpoint}).",
                "reason": f"Derived from retained {symbol} raw closing prices; descriptive and non-causal.",
            })
        elif status in {"immature", "unavailable"}:
            if row.get("return_pct") is not None or row.get("selected_close") is not None or row.get("selected_date") is not None:
                _fail(f"MLCF market context non-mature horizon emits an outcome: {horizon}")
            if not isinstance(row.get("reason"), str) or not row.get("reason"):
                _fail(f"{label} market context non-mature horizon reason is missing: {horizon}")
            items.append({"id": horizon, "text": "Outcome not yet mature.", "reason": str(row["reason"])})
        else:
            _fail(f"{label} market context horizon status is invalid: {horizon}")

    aggregate = study.get("analogue_aggregate")
    if not isinstance(aggregate, dict):
        _fail(f"{label} market context analogue aggregate is missing")
    for horizon in ("1Q", "2Q", "4Q", "8Q"):
        row = aggregate.get(horizon)
        if not isinstance(row, dict) or row.get("status") != "suppressed" or row.get("reason") != "n_lt_3" or row.get("n") != 0:
            _fail(f"{label} market context analogue suppression mismatch: {horizon}")
        if row.get("mean_return_pct") is not None:
            _fail(f"{label} market context analogue average must remain suppressed: {horizon}")
    items.append({
        "id": "analogue_sample",
        "text": "No same-company or peer analogue sample meets the minimum threshold for a reliable benchmark.",
        "reason": "All retained aggregate horizons are suppressed because n < 3.",
    })
    if not mature_endpoints:
        _fail(f"{label} market context has no mature retained outcome")
    return {
        "status": "available",
        "epistemic_type": "derived_fact",
        "text": (
            f"Cutoff-safe raw-price context for this exact {label} observed event. It is descriptive only: "
            "not causal, not adjusted or total return, not an analogue benchmark, and not a forecast or valuation input."
        ),
        "items": items,
        "formulas": [{
            "formula_id": "event_study.raw_price_return.v1",
            "operands": ["baseline_close", "endpoint_close"],
            "source": f"state/company_intel/event_studies.json; retained bars: {history_file}",
        }],
    }, max(mature_endpoints)


def _mlcf_market_context(event_studies: dict[str, Any], history: Any) -> tuple[dict[str, Any], datetime]:
    return _market_context(
        event_studies, history, label="MLCF control", symbol="MLCF",
        event_id=MLCF_CANONICAL_CONTROL_EVENT_ID, effective_date="2025-12-18", baseline_date="2025-12-17",
    )


def _mari_market_context(event_studies: dict[str, Any], history: Any) -> tuple[dict[str, Any], datetime]:
    return _market_context(
        event_studies, history, label="MARI Peshawar", symbol="MARI",
        event_id=MARI_CANONICAL_CONTROL_EVENT_ID, effective_date="2025-09-30", baseline_date="2025-09-29",
    )


def _empty_company(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "status": "no_observed_case",
        "case_count": 0,
        "cases": [],
        "rejection_reasons": ["no_selected_observed_case_seed"],
    }


def _mlcf_case(
    ledger: dict[str, Any],
    documents: dict[str, Any],
    operating_events: dict[str, Any],
    event_studies: dict[str, Any] | None = None,
    history: Any = None,
) -> tuple[dict[str, Any] | None, list[str], list[dict[str, Any]]]:
    public_offer = _event(ledger, "MLCF", PUBLIC_OFFER_EVENT_ID)
    follow_through = _event(ledger, "MLCF", FOLLOW_THROUGH_EVENT_ID)
    canonical_control = _operating_event(operating_events, "MLCF", MLCF_CANONICAL_CONTROL_EVENT_ID)
    canonical_follow_through = _operating_event(operating_events, "MLCF", MLCF_FOLLOW_THROUGH_ALIAS_EVENT_ID)
    public_offer_doc = _document(documents, PUBLIC_OFFER_DOC_ID)
    follow_through_doc = _document(documents, FOLLOW_THROUGH_DOC_ID)
    missing = []
    for label, value in (
        ("missing_public_offer_event", public_offer),
        ("missing_follow_through_event", follow_through),
        ("missing_canonical_control_event", canonical_control),
        ("missing_public_offer_document", public_offer_doc),
        ("missing_follow_through_document", follow_through_doc),
    ):
        if value is None:
            missing.append(label)
    if missing:
        raise ValueError(f"MLCF source chain incomplete: {', '.join(missing)}")
    assert public_offer is not None and follow_through is not None
    assert public_offer_doc is not None and follow_through_doc is not None
    assert canonical_control is not None
    if canonical_follow_through is not None:
        raise ValueError("MLCF follow-through alias unexpectedly resolves to an independent operating event")
    source_join = _mlcf_source_join(public_offer, follow_through, canonical_control, public_offer_doc, follow_through_doc)
    financial_truth_counters = _financial_truth_counters()
    readiness = _cement_input_readiness(source_join, financial_truth_counters)
    refs = [_evidence_ref(public_offer, public_offer_doc), _evidence_ref(follow_through, follow_through_doc)]
    cutoff = _source_cutoff(refs)
    if event_studies is None:
        event_studies = load_json(STATE / "company_intel" / "event_studies.json", {})
    if history is None:
        history = load_json(STATE / "history" / "MLCF.json", [])
    market_context, market_cutoff = _mlcf_market_context(event_studies, history)
    source_cutoff = _parse_time(cutoff)
    if source_cutoff is None:
        _fail("MLCF source cutoff is invalid")
    cutoff = max(source_cutoff, market_cutoff).isoformat()
    case = {
        "case_id": MLCF_CASE_ID,
        "symbol": "MLCF",
        "target_symbol": "PIOC",
        "case_family": "industrial_cement",
        "case_type": "acquisition_control",
        "status": "Observed",
        "epistemic_type": "reported_fact",
        "as_of": cutoff,
        "summary": (
            "Observed official-source seed: MLCF reported a public offer/control transaction for "
            "Pioneer Cement, and a later MLCF quarterly filing reported Pioneer Cement dispatches "
            "included in local-market totals after the February 2026 acquisition."
        ),
        "observed_facts": [
            {
                "fact_id": "mlcf_pioc_public_offer_control",
                "source_event_id": PUBLIC_OFFER_EVENT_ID,
                "document_id": PUBLIC_OFFER_DOC_ID,
                "event_date": _iso_time(public_offer.get("event_date")),
                "statement": "MLCF reported a public offer to acquire PIOC shares and control of Pioneer Cement Limited.",
                "reported_values": [
                    {"label": "public_offer_shares", "value": "up to 26,623,096 PIOC shares"},
                    {"label": "public_offer_percent", "value": "11.72% shares"},
                    {"label": "spa_percent", "value": "58.03% through Share Purchase Agreement(s)"},
                    {"label": "offer_price", "value": "PKR 478.43 per share"},
                ],
                "evidence": [refs[0]],
            },
            {
                "fact_id": "mlcf_pioc_dispatch_inclusion",
                "source_event_id": FOLLOW_THROUGH_EVENT_ID,
                "document_id": FOLLOW_THROUGH_DOC_ID,
                "event_date": _iso_time(follow_through.get("event_date")),
                "statement": (
                    "MLCF reported inclusion of Pioneer Cement Limited dispatches in local-market "
                    "total due to its acquisition during February 2026."
                ),
                "reported_values": [
                    {"label": "acquisition_timing", "value": "during February 2026"},
                    {"label": "operating_follow_through", "value": "Pioneer Cement Limited dispatches included in local-market total"},
                ],
                "evidence": [refs[1]],
            },
        ],
        "alternative_readings": [
            {
                "alternative_id": "public_offer_not_full_model",
                "reading": "The December 2025 document is an official offer/control disclosure, not a quantified earnings model.",
                "status": "retained_as_observed_only",
                "rejection_condition": "Reject promotion if no later official source preserves acquisition/control or operating inclusion.",
            },
            {
                "alternative_id": "dispatch_inclusion_not_financial_impact",
                "reading": "The April 2026 filing shows operating inclusion after acquisition, but not a standalone PIOC financial impact.",
                "status": "retained_as_observed_only",
                "rejection_condition": "Reject modelling if source-qualified incremental revenue, margin, EPS, cash-flow, debt and share-count operands are absent.",
            },
        ],
        "promotion_blocks": {
            "Corroborated": "Blocked: retained evidence is an official MLCF/PSX chain, not independent-originator corroboration.",
            "Modelled": "Blocked: no source-qualified financial impact model or owner-approved assumptions are attached.",
            "Published": "Blocked: no forecast, valuation, reverse-expectations output, investor conclusion or release gate is complete.",
        },
        "cement_input_readiness": readiness,
        "sections": {"analogues": market_context},
        "policy": _policy(deterministic_derived_context=True),
        "source_lineage": refs,
    }
    return case, [], refs


def _mari_case(
    ledger: dict[str, Any],
    documents: dict[str, Any],
    operating_events: dict[str, Any] | None = None,
    event_studies: dict[str, Any] | None = None,
    history: Any = None,
    receipts: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, list[str], list[dict[str, Any]]]:
    event = _event(ledger, "MARI", MARI_EVENT_ID)
    follow_through = _event(ledger, "MARI", MARI_FOLLOW_THROUGH_EVENT_ID)
    document = _document(documents, MARI_DOC_ID)
    follow_through_document = _document(documents, MARI_FOLLOW_THROUGH_DOC_ID)
    if operating_events is None:
        operating_events = load_json(STATE / "company_intel" / "operating_events.json", {"companies": {}})
    canonical_event = _operating_event(operating_events, "MARI", MARI_CANONICAL_CONTROL_EVENT_ID)
    missing = []
    if event is None:
        missing.append("missing_mari_peshawar_working_interest_event")
    if document is None:
        missing.append("missing_mari_peshawar_working_interest_document")
    if canonical_event is None:
        missing.append("missing_mari_canonical_peshawar_event")
    if follow_through is None:
        missing.append("missing_mari_peshawar_follow_through_event")
    if follow_through_document is None:
        missing.append("missing_mari_peshawar_follow_through_document")
    if missing:
        return None, missing, []
    assert event is not None and document is not None and canonical_event is not None
    assert follow_through is not None and follow_through_document is not None
    ref = _validate_mari_source(event, document)
    follow_ref = _validate_mari_follow_through_source(
        follow_through, follow_through_document,
        receipts or load_json(STATE / "company_intel" / "reprocess_receipts.json", {"receipts": []}),
    )
    _validate_mari_canonical_control_source(canonical_event)
    cutoff = _source_cutoff([ref, follow_ref])
    if event_studies is None:
        event_studies = load_json(STATE / "company_intel" / "event_studies.json", {})
    if history is None:
        history = load_json(STATE / "history" / "MARI.json", [])
    market_context, market_cutoff = _mari_market_context(event_studies, history)
    source_cutoff = _parse_time(cutoff)
    if source_cutoff is None:
        _fail("MARI source cutoff is invalid")
    cutoff = max(source_cutoff, market_cutoff).isoformat()
    case = {
        "case_id": MARI_CASE_ID,
        "symbol": "MARI",
        "case_family": "e_and_p",
        "case_type": "working_interest_acquisition",
        "status": "Observed",
        "epistemic_type": "reported_fact",
        "as_of": cutoff,
        "summary": "Observed official-source seed: Mari Energies reported acquisition of a 65% working interest in Peshawar Block with operatorship.",
        "observed_facts": [
            {
                "fact_id": "mari_peshawar_working_interest_acquisition",
                "source_event_id": MARI_EVENT_ID,
                "document_id": MARI_DOC_ID,
                "event_date": _iso_time(event.get("event_date")),
                "statement": "Mari Energies reported acquisition of working interest in Peshawar Block as an operator.",
                "reported_values": [
                    {"label": "block", "value": "Peshawar Block"},
                    {"label": "operator_status", "value": "as an Operator"},
                ],
                "evidence": [ref],
            },
            {
                "fact_id": "mari_peshawar_follow_through_interest",
                "source_event_id": MARI_FOLLOW_THROUGH_EVENT_ID,
                "document_id": MARI_FOLLOW_THROUGH_DOC_ID,
                "event_date": _iso_time(follow_through.get("event_date")),
                "statement": "A later MARI quarterly filing reported a 65% Peshawar Block working interest together with operatorship.",
                "reported_values": [
                    {"label": "working_interest", "value": "65%"},
                    {"label": "operator_status", "value": "operatorship"},
                ],
                "evidence": [follow_ref],
            },
        ],
        "alternative_readings": [
            {
                "alternative_id": "working_interest_not_reserves",
                "reading": "Working-interest acquisition does not establish reserves, a commercial discovery, or future production.",
                "status": "retained_as_observed_only",
                "rejection_condition": "Reject promotion if no official source identifies technical results, resource potential, or a development path.",
            },
            {
                "alternative_id": "operator_status_not_economics",
                "reading": "The later filing confirms a 65% working interest and operatorship, but does not establish cost, timing, resource, production or project economics.",
                "status": "retained_as_observed_only",
                "rejection_condition": "Reject modelling if source-qualified project economics and qualified company financial inputs remain absent.",
            },
        ],
        "promotion_blocks": {
            "Corroborated": "Blocked: retained evidence is a MARI/PSX filing chain, not independent-originator corroboration.",
            "Modelled": "Blocked: no source-qualified financial model or owner-approved assumptions are attached.",
            "Published": "Blocked: no forecast, valuation, reverse-expectations output, investor conclusion or release gate is complete.",
        },
        "sections": {"analogues": market_context},
        "policy": _policy(deterministic_derived_context=True),
        "source_lineage": [ref, follow_ref],
    }
    return case, [], [ref, follow_ref]


def _sales_fail(message: str) -> None:
    raise ValueError(message)


def _sales_require_equal(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        _sales_fail(f"MARI sales-led source mismatch for {label}: {actual!r}")


def _sales_require_hex64(label: str, value: Any) -> str:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        _sales_fail(f"MARI sales-led invalid 64-character hash for {label}")
    return value.lower()


def _sales_require_text(label: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        _sales_fail(f"MARI sales-led missing source text for {label}")
    return value


def _mari_sales_candidates(operating_events: dict[str, Any]) -> list[dict[str, Any]]:
    events = (((operating_events.get("companies") or {}).get("MARI") or {}).get("events") or [])
    candidates = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("event_id") == MARI_SALES_CANONICAL_EVENT_ID:
            candidates.append(event)
            continue
        for row in event.get("evidence") or []:
            if isinstance(row, dict) and row.get("document_id") == MARI_SALES_DOC_ID:
                candidates.append(event)
                break
    return candidates


def _mari_sales_ledger_rows(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    rows = (((ledger.get("companies") or {}).get("MARI") or {}).get("events") or [])
    return [
        row for row in rows
        if isinstance(row, dict)
        and row.get("doc_id") == MARI_SALES_DOC_ID
        and _iso_time(row.get("event_date")) == MARI_SALES_PUBLISHED_AT
    ]


def _validate_mari_sales_source(
    event: dict[str, Any],
    doc: dict[str, Any],
    ledger: dict[str, Any],
) -> dict[str, Any]:
    _sales_require_equal("document.doc_id", doc.get("doc_id"), MARI_SALES_DOC_ID)
    _sales_require_equal("document.source", doc.get("source"), "PSX DPS")
    _sales_require_equal("document.source_url", doc.get("source_url"), MARI_SALES_SOURCE_URL)
    _sales_require_equal("document.title", doc.get("title"), MARI_SALES_TITLE)
    _sales_require_equal("document.classification", doc.get("classification"), "material_information")
    _sales_require_equal("document.published_at", _iso_time(doc.get("published_at")), MARI_SALES_PUBLISHED_AT)
    _sales_require_equal("document.available_on", _available_on(doc), MARI_SALES_EFFECTIVE_DATE)
    content_sha256 = _sales_require_hex64("document.content_sha256", doc.get("content_sha256"))
    _sales_require_equal(
        "document.local_sha256",
        _sales_require_hex64("document.local_sha256", doc.get("local_sha256")),
        content_sha256,
    )
    _sales_require_equal("event.company_id", event.get("company_id"), "MARI")
    _sales_require_equal("event.symbol", event.get("symbol"), "MARI")
    _sales_require_equal("event.event_type", event.get("event_type"), "product_launch")
    _sales_require_equal("event.event_subtype", event.get("event_subtype"), "product_launch")
    _sales_require_equal("event.intelligence_type", event.get("intelligence_type"), "reported_fact")
    _sales_require_equal("event.detected_at", _iso_time(event.get("detected_at")), MARI_SALES_PUBLISHED_AT)
    _sales_require_equal("event.effective_date", event.get("effective_date"), MARI_SALES_EFFECTIVE_DATE)
    _sales_require_equal("event.source_url", event.get("source_url"), MARI_SALES_SOURCE_URL)
    evidence = event.get("evidence")
    if not isinstance(evidence, list) or not evidence or not isinstance(evidence[0], dict):
        _sales_fail("MARI sales-led canonical event is missing its evidence row")
    row = evidence[0]
    _sales_require_equal("event.evidence.document_id", row.get("document_id"), MARI_SALES_DOC_ID)
    _sales_require_equal("event.evidence.source", row.get("source"), "PSX DPS")
    _sales_require_equal("event.evidence.source_url", row.get("source_url"), MARI_SALES_SOURCE_URL)
    page = row.get("page")
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        _sales_fail("MARI sales-led evidence page must be a one-based integer")
    text = _sales_require_text("event.evidence.text", row.get("text"))
    _sales_require_equal("event.evidence.content_sha256", row.get("content_sha256"), content_sha256)
    evidence_sha256 = _sales_require_hex64("event.evidence.evidence_sha256", row.get("evidence_sha256"))
    _sales_require_equal(
        "event.evidence.evidence_sha256",
        evidence_sha256,
        evidence_hash(MARI_SALES_DOC_ID, MARI_SALES_SOURCE_URL, page, text),
    )
    if not MARI_SALES_CAMPUS_RE.search(text) or not MARI_SALES_FACILITY_RE.search(text):
        _sales_fail("MARI sales-led evidence text does not name the data-centre campus and Karakoram-01 facility")
    event_id = event.get("event_id")
    if event_id == MARI_SALES_CANONICAL_EVENT_ID:
        event_id_binding = MARI_SALES_EXACT_EVENT_ID_BINDING
    else:
        recomputed = {
            stable_id("MARI", raw.get("event_id"), event.get("event_type"))
            for raw in _mari_sales_ledger_rows(ledger)
            if isinstance(raw.get("event_id"), str)
            and isinstance(raw.get("evidence"), list)
            and raw["evidence"]
            and isinstance(raw["evidence"][0], dict)
            and raw["evidence"][0].get("page") == page
            and raw["evidence"][0].get("text") == text
        }
        if event_id not in recomputed:
            _sales_fail(
                "MARI sales-led canonical event id is neither the accepted id nor a "
                "recomputation from the accepted PSX source"
            )
        event_id_binding = MARI_SALES_RECOMPUTED_EVENT_ID_BINDING
    return {
        "event_id": event_id,
        "event_id_binding": event_id_binding,
        "document_id": MARI_SALES_DOC_ID,
        "page": page,
        "content_sha256": content_sha256,
        "evidence_sha256": evidence_sha256,
        "published_at": MARI_SALES_PUBLISHED_AT,
        "effective_date": MARI_SALES_EFFECTIVE_DATE,
    }


def _canonical_evidence_ref(event: dict[str, Any], doc: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    row = (event.get("evidence") or [{}])[0]
    return {
        "canonical_event_id": event.get("event_id"),
        "canonical_event_id_binding": binding["event_id_binding"],
        "document_id": MARI_SALES_DOC_ID,
        "document_title": doc.get("title"),
        "document_published_at": _iso_time(doc.get("published_at")),
        "document_retrieved_at": _iso_time(doc.get("retrieved_at")),
        "content_sha256": doc.get("content_sha256"),
        "source": doc.get("source") or "PSX DPS",
        "source_url": row.get("source_url") or doc.get("source_url"),
        "page": row.get("page"),
        "text": row.get("text"),
        "evidence_sha256": row.get("evidence_sha256"),
    }


def _mari_financial_truth_gate() -> dict[str, Any]:
    qualification = load_json(STATE / "company_intel" / "financial_truth_qualification.json", {})
    row = (qualification.get("companies") or {}).get("MARI") if isinstance(qualification, dict) else None
    row = row if isinstance(row, dict) else {}
    status = row.get("status") if isinstance(row.get("status"), str) else ""
    downstream = row.get("downstream") if isinstance(row.get("downstream"), dict) else {}

    def blocked_value(key: str) -> str:
        value = downstream.get(key)
        if status == "qualified":
            return "blocked_missing_source_qualified_event_inputs"
        return value if isinstance(value, str) and value.startswith("blocked") else "blocked_financial_truth_not_qualified"

    return {
        "status": "qualified" if status == "qualified" else "not_qualified",
        "formal_output_statuses": {
            "financial_model_status": blocked_value("forecast"),
            "formal_valuation_status": blocked_value("valuation"),
            "reverse_expectations_status": blocked_value("market_expectations"),
        },
    }


def _sales_input_readiness(binding: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "observed_only",
        "kernel_activation": "blocked",
        "attribution": {"company": "MARI", "campus": "AI-ready data centre campus", "first_facility": "Karakoram-01"},
        "source_binding": binding,
        "financial_truth_gate": gate,
        "event_specific_kernel_requirements": {
            field: {
                "value": None,
                "source_label": "retained_state_only:no_source_qualified_event_input",
                "status": "missing_source_bound_input",
            }
            for field in MARI_SALES_KERNEL_FIELDS
        },
        "guardrails": {
            "launch_announcement_not_financial_qualification": True,
            "no_revenue_capacity_utilisation_pricing_or_timing_claims": True,
            "distinct_from_mari_e_and_p_case": True,
            "no_numeric_model_output": True,
        },
    }


def _mari_sales_case(
    ledger: dict[str, Any],
    documents: dict[str, Any],
    operating_events: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str], list[dict[str, Any]]]:
    candidates = _mari_sales_candidates(operating_events)
    document = _document(documents, MARI_SALES_DOC_ID)
    if not candidates and document is None:
        return None, ["missing_mari_sky47_launch_operating_event", "missing_mari_sky47_launch_document"], []
    if not candidates:
        _sales_fail("MARI sales-led source chain incomplete: launch document retained without its canonical operating event")
    if document is None:
        _sales_fail("MARI sales-led source chain incomplete: canonical launch event retained without its document")
    if len(candidates) > 1:
        _sales_fail("MARI sales-led source chain ambiguous: multiple canonical events bind to the launch document")
    assert candidates[0] is not None and document is not None
    binding = _validate_mari_sales_source(candidates[0], document, ledger)
    refs = [_canonical_evidence_ref(candidates[0], document, binding)]
    cutoff = _source_cutoff(refs)
    gate = _mari_financial_truth_gate()
    readiness = _sales_input_readiness(binding, gate)
    case = {
        "case_id": MARI_SALES_CASE_ID,
        "symbol": "MARI",
        "case_family": "ai_data_centre",
        "case_type": "campus_launch_sales_led",
        "status": "Observed",
        "epistemic_type": "reported_fact",
        "as_of": cutoff,
        "summary": (
            "Observed official-source seed: Mari Energies announced the launch of its "
            "Karakoram-01 purpose-built AI-ready data centre campus, described as "
            "Pakistan's first and largest."
        ),
        "observed_facts": [
            {
                "fact_id": "mari_sky47_karakoram1_campus_launch",
                "source_event_id": binding["event_id"],
                "document_id": MARI_SALES_DOC_ID,
                "event_date": MARI_SALES_PUBLISHED_AT,
                "statement": "Mari Energies reported the launch of the Karakoram-01 AI-ready data centre campus.",
                "reported_values": [
                    {"label": "first_facility", "value": "Karakoram-01"},
                    {"label": "described_as", "value": "Pakistan first and largest purpose-built AI ready data centre campus"},
                ],
                "evidence": refs,
            },
        ],
        "alternative_readings": [
            {
                "alternative_id": "launch_not_financial_qualification",
                "reading": "A launch announcement establishes the event, not any qualified revenue, capacity, utilisation, pricing or timing contribution.",
                "status": "unknown_unresolved",
                "rejection_condition": "Reject promotion while MARI financial truth is not qualified and no source-qualified operands exist.",
            },
            {
                "alternative_id": "announcement_not_contracted_demand",
                "reading": "The campus launch does not establish contracted customers, achieved pricing, utilisation, or a ramp schedule.",
                "status": "unknown_unresolved",
                "rejection_condition": "Reject modelling until official sources qualify contracted demand and operating terms.",
            },
            {
                "alternative_id": "sales_led_case_distinct_from_e_and_p",
                "reading": "The data-centre launch case is tracked separately from MARI's E&P case; the two value drivers are not merged.",
                "status": "retained_as_observed_only",
                "rejection_condition": f"Reject any conflation with {MARI_CASE_ID}.",
            },
        ],
        "monitoring": [
            "Watch for official customer contracts or service agreements tied to Karakoram-01.",
            "Watch for source-qualified capacity, utilisation, pricing, capex, margin, or ramp disclosures.",
            "Watch for MARI financial-truth qualification before any formal model, valuation, or expectations work.",
        ],
        "promotion_blocks": {
            "Corroborated": "Blocked: retained evidence is a single official Mari/PSX source and no independent-originator corroboration is attached.",
            "Modelled": "Blocked: financial-model, valuation and market-expectation outputs stay blocked until MARI financial truth is qualified and source-qualified revenue, capacity, utilisation, pricing and ramp inputs are attached.",
            "Published": "Blocked: no forecast, valuation, reverse-expectations output, investor conclusion or release gate is complete.",
        },
        "sales_input_readiness": readiness,
        "policy": {
            "observed_only": True,
            "no_forecast": True,
            "no_valuation": True,
            "no_market_expectations": True,
            "no_recommendation": True,
            "reported_values_only": True,
        },
        "source_lineage": refs,
    }
    return case, [], refs


def build(write: bool = True) -> dict[str, Any]:
    profiles = load_json(STATE / "company_profiles.json", {})
    ledger = load_json(STATE / "company_event_ledger.json", {"companies": {}})
    documents = load_json(STATE / "company_documents.json", {"documents": {}})
    operating_events = load_json(STATE / "company_intel" / "operating_events.json", {"companies": {}})
    event_studies = load_json(STATE / "company_intel" / "event_studies.json", {"studies": {}})
    mlcf_history = load_json(STATE / "history" / "MLCF.json", [])
    mari_history = load_json(STATE / "history" / "MARI.json", [])
    reprocess_receipts = load_json(STATE / "company_intel" / "reprocess_receipts.json", {"receipts": []})
    pilot = sorted((profiles.get("pilot") or {}).get("symbols") or [])
    companies = {symbol: _empty_company(symbol) for symbol in pilot}
    mlcf_case, mlcf_rejections, mlcf_refs = _mlcf_case(ledger, documents, operating_events, event_studies, mlcf_history)
    mari_case, mari_rejections, mari_refs = _mari_case(
        ledger, documents, operating_events, event_studies, mari_history, reprocess_receipts,
    )
    mari_sales_case, mari_sales_rejections, mari_sales_refs = _mari_sales_case(ledger, documents, operating_events)
    refs = [*mlcf_refs, *mari_refs, *mari_sales_refs]
    as_of = _source_cutoff(refs) if refs else datetime.now(PKT).replace(microsecond=0).isoformat()
    if "MLCF" not in companies:
        companies["MLCF"] = _empty_company("MLCF")
    if mlcf_case:
        companies["MLCF"] = {
            "symbol": "MLCF",
            "status": "observed_seed_available",
            "case_count": 1,
            "cases": [mlcf_case],
            "rejection_reasons": [],
        }
    else:
        companies["MLCF"]["rejection_reasons"] = mlcf_rejections
    if "MARI" not in companies:
        companies["MARI"] = _empty_company("MARI")
    mari_cases = [case for case in (mari_case, mari_sales_case) if case is not None]
    mari_rejections_all = [*(mari_rejections or []), *(mari_sales_rejections or [])]
    if mari_cases:
        companies["MARI"] = {
            "symbol": "MARI",
            "status": "observed_seed_available",
            "case_count": len(mari_cases),
            "cases": mari_cases,
            "rejection_reasons": mari_rejections_all,
        }
    else:
        companies["MARI"]["rejection_reasons"] = mari_rejections_all or ["no_selected_observed_case_seed"]
    result = {
        "schema_version": 1,
        "case_product_version": CASE_PRODUCT_VERSION,
        "as_of": as_of,
        "pilot_symbols": pilot,
        "selected_symbols": ["MARI", "MLCF"],
        "status_lifecycle": LIFECYCLE,
        "policy": {
            "dedicated_observed_seeds_only": True,
            "no_generic_case_engine": True,
            "reported_values_only": False,
            "deterministic_derived_context_only": True,
            "formal_engines_unchanged": True,
        },
        "summary": {
            "company_count": len(companies),
            "observed_case_count": sum(row.get("case_count", 0) for row in companies.values()),
            "published_case_count": 0,
        },
        "companies": companies,
    }
    if write:
        save_json(OUT, result)
        print(f"intelligence_cases: {result['summary']['observed_case_count']} observed seeds")
    return result


if __name__ == "__main__":
    build()
