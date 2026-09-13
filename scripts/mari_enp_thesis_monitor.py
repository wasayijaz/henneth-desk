"""Bounded MARI E&P thesis monitor.

Consumes retained event, valuation/scenario/expectations envelopes, and
source-bound filings. It does not parse financial statements, fetch providers,
or invent economics. Source-effective dates after the cutoff are lookahead.
Required artifacts dated more than STALE_DAYS before the cutoff are rejected.
Red financial truth or missing source facts suppress numeric activation.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Mapping
import hashlib
import json
import re
from pathlib import Path

from psx_data import ROOT, STATE, load_json, save_json

ENGINE_VERSION = "mari_enp_thesis_monitor_v1"
FORMULA_ID = "enp_exploration.thesis_monitor.v1"
RESULT_SCHEMA = "mari_enp_thesis_monitor_result_v1"
CASE_ID = "case_mari_working_interest_observed_v1"
SYMBOL = "MARI"
CASE_FAMILY = "e_and_p"
OUT = STATE / "company_intel" / "mari_enp_thesis_monitor.json"
STALE_DAYS = 365
STATUS_ACTIVE = "active_monitoring"
STATUS_TRUTH = "blocked_financial_truth_not_qualified"
STATUS_SOURCE = "blocked_missing_source_facts"
STATUS_LOOKAHEAD = "blocked_lookahead"
STATUS_STALE = "blocked_stale_inputs"
_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ADVICE_RE = re.compile(r"\b(?:buy|sell|accumulate|target\s+price|price\s+target|you\s+should)\b", re.I)
_QUARTER_ENDS = ((3, 31), (6, 30), (9, 30), (12, 31))
TRIGGERS = (
    "official_well_result_disclosure",
    "working_interest_or_operatorship_restatement",
    "financial_truth_qualification_change",
    "source_qualified_reserves_or_cost_filing",
)
ENVELOPE_KEYS = (
    "schema_version",
    "formula_id",
    "engine_version",
    "case_id",
    "symbol",
    "case_family",
    "status",
    "blocked_reasons",
    "thesis",
    "confirming_indicators",
    "disconfirming_indicators",
    "evidence_cutoff",
    "next_monitor",
    "stale_input_warnings",
    "suppressed",
    "source_facts",
    "consumed_artifacts",
    "run_receipt",
    "policy",
)


def as_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, type(date.min)):
        return value
    if type(value) is not str:
        return None
    match = _DATE_RE.match(value.strip())
    if match is None:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def next_quarter_end(cutoff: date) -> date:
    for month, day in _QUARTER_ENDS:
        candidate = date(cutoff.year, month, day)
        if candidate > cutoff:
            return candidate
    return date(cutoff.year + 1, 3, 31)


def _https(url: Any) -> bool:
    return type(url) is str and url.startswith("https://")


def _source_ok(evidence: Mapping[str, Any]) -> bool:
    page = evidence.get("page")
    return (
        type(evidence.get("document_id")) is str
        and bool(evidence.get("document_id"))
        and type(evidence.get("content_sha256")) is str
        and _HASH_RE.fullmatch(evidence["content_sha256"]) is not None
        and type(page) is int
        and page >= 1
        and _https(evidence.get("source_url"))
    )


def _indicator(indicator_id: str, role: str, status: str, text: str, source: Mapping[str, Any] | None = None, available_on: str | None = None) -> dict[str, Any]:
    if _ADVICE_RE.search(text):
        raise ValueError("advice language is forbidden")
    return {
        "indicator_id": indicator_id,
        "role": role,
        "status": status,
        "text": text,
        "available_on": available_on,
        "source": {
            "document_id": (source or {}).get("document_id"),
            "page": (source or {}).get("page"),
            "content_sha256": (source or {}).get("content_sha256"),
            "source_url": (source or {}).get("source_url"),
        } if source else None,
    }


def _extract_case(cases: Mapping[str, Any]) -> dict[str, Any] | None:
    company = ((cases.get("companies") or {}).get(SYMBOL) or {})
    matches = [row for row in (company.get("cases") or []) if type(row) is dict and row.get("case_id") == CASE_ID]
    return matches[0] if len(matches) == 1 else None


def _collect_evidence(case: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for fact in case.get("observed_facts") or []:
        if type(fact) is not dict:
            continue
        for evidence in fact.get("evidence") or []:
            if type(evidence) is not dict or not _source_ok(evidence):
                continue
            key = (evidence.get("document_id"), evidence.get("content_sha256"), evidence.get("page"))
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "fact_id": fact.get("fact_id"),
                    "statement": fact.get("statement"),
                    "document_id": evidence.get("document_id"),
                    "page": evidence.get("page"),
                    "content_sha256": evidence.get("content_sha256"),
                    "source_url": evidence.get("source_url"),
                    "event_date": evidence.get("event_date") or fact.get("event_date"),
                    "published_at": evidence.get("document_published_at"),
                }
            )
    return rows


def _effective_date(row: Mapping[str, Any]) -> date | None:
    return as_date(row.get("available_on")) or as_date(row.get("published_at")) or as_date(row.get("event_date"))


def _artifact_as_of(blob: Mapping[str, Any]) -> date | None:
    if type(blob) is not dict:
        return None
    return as_date(blob.get("as_of")) or as_date(blob.get("artifact_as_of")) or as_date((blob.get("evidence_cutoff") or {}).get("as_of_date"))


def evaluate_monitor(
    *,
    cutoff_date: str,
    cases: Mapping[str, Any],
    truth: Mapping[str, Any],
    valuation: Mapping[str, Any],
    scenario_lab: Mapping[str, Any],
    expectations: Mapping[str, Any],
    extra_artifacts: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pure monitor. Identical inputs produce identical envelopes."""
    cutoff = as_date(cutoff_date)
    if cutoff is None:
        raise ValueError("cutoff_date: must be an ISO date")

    reasons: list[str] = []
    stale_warnings: list[str] = []
    confirming: list[dict[str, Any]] = []
    disconfirming: list[dict[str, Any]] = []
    lookahead = False
    stale_block = False

    case = _extract_case(cases)
    if case is None:
        reasons.append("observed_mari_case_seed_missing")
    evidence_rows = _collect_evidence(case) if case else []
    in_cutoff: list[dict[str, Any]] = []
    for row in evidence_rows:
        effective = _effective_date(row)
        if effective is None:
            reasons.append(f"untimestamped_source:{row['document_id']}")
            continue
        if effective > cutoff:
            lookahead = True
            reasons.append(f"lookahead_source:{row['document_id']}:{effective.isoformat()}")
            continue
        in_cutoff.append({**row, "available_on": effective.isoformat()})

    if not in_cutoff:
        reasons.append("no_cutoff_safe_source_facts")

    truth_row = ((truth.get("companies") or {}).get(SYMBOL) or {}) if type(truth) is dict else {}
    truth_qualified = truth_row.get("status") == "qualified"
    if not truth_qualified:
        reasons.append("financial_truth_not_qualified")

    artifacts = {
        "valuation": valuation if type(valuation) is dict else {},
        "scenario_lab": scenario_lab if type(scenario_lab) is dict else {},
        "expectations": expectations if type(expectations) is dict else {},
    }
    for extra in extra_artifacts or []:
        if type(extra) is dict and type(extra.get("name")) is str:
            artifacts[str(extra["name"])] = extra

    consumed = []
    for name, blob in artifacts.items():
        artifact_date = _artifact_as_of(blob)
        status = blob.get("status") if type(blob) is dict else None
        entry = {
            "name": name,
            "status": status,
            "as_of": artifact_date.isoformat() if artifact_date else None,
            "used_for_activation": False,
        }
        if artifact_date is not None and artifact_date > cutoff:
            lookahead = True
            reasons.append(f"lookahead_artifact:{name}:{artifact_date.isoformat()}")
            entry["rejection"] = "lookahead"
        elif artifact_date is not None and (cutoff - artifact_date).days > STALE_DAYS:
            stale_block = True
            stale_warnings.append(f"{name}: as_of {artifact_date.isoformat()} is more than {STALE_DAYS} days before cutoff")
            reasons.append(f"stale_artifact:{name}:{artifact_date.isoformat()}")
            entry["rejection"] = "stale"
        consumed.append(entry)

    for row in in_cutoff:
        role = "confirming"
        text = str(row.get("statement") or "Retained official Peshawar Block working-interest evidence.")
        confirming.append(
            _indicator(
                f"source:{row['document_id']}:p{row['page']}",
                role,
                "observed",
                text,
                row,
                row["available_on"],
            )
        )

    valuation_status = artifacts["valuation"].get("status") if type(artifacts["valuation"]) is dict else None
    scenario_status = artifacts["scenario_lab"].get("status") if type(artifacts["scenario_lab"]) is dict else None
    expectations_status = artifacts["expectations"].get("status") if type(artifacts["expectations"]) is dict else None
    numeric_live = (
        truth_qualified
        and not lookahead
        and not stale_block
        and bool(in_cutoff)
        and valuation_status == "computed"
        and scenario_status == "computed"
    )
    if numeric_live:
        confirming.append(
            _indicator(
                "kernel:valuation_computed",
                "confirming",
                "computed",
                "Valuation envelope status is computed at cutoff.",
                None,
                cutoff.isoformat(),
            )
        )
        confirming.append(
            _indicator(
                "kernel:scenario_lab_computed",
                "confirming",
                "computed",
                "Scenario-lab envelope status is computed at cutoff.",
                None,
                cutoff.isoformat(),
            )
        )
        if expectations_status == "computed":
            confirming.append(
                _indicator(
                    "kernel:expectations_computed",
                    "confirming",
                    "computed",
                    "Expectations envelope status is computed at cutoff.",
                    None,
                    cutoff.isoformat(),
                )
            )
        for item in consumed:
            if item["name"] in {"valuation", "scenario_lab", "expectations"}:
                item["used_for_activation"] = True

    if case:
        for alt in case.get("alternative_readings") or []:
            if type(alt) is not dict:
                continue
            reading = alt.get("reading")
            if type(reading) is str and reading:
                disconfirming.append(
                    _indicator(
                        f"alternative:{alt.get('alternative_id')}",
                        "disconfirming",
                        "open_alternative",
                        reading,
                        None,
                        cutoff.isoformat(),
                    )
                )

    if lookahead:
        status = STATUS_LOOKAHEAD
    elif stale_block:
        status = STATUS_STALE
    elif not in_cutoff:
        status = STATUS_SOURCE
    elif not truth_qualified:
        status = STATUS_TRUTH
    else:
        status = STATUS_ACTIVE

    thesis_status = "suppressed" if status != STATUS_ACTIVE else ("Strengthening" if numeric_live else "Stable")
    suppressed = {
        "valuation": not numeric_live,
        "scenario": not numeric_live,
        "expectations": not numeric_live,
        "numeric_indicators": not numeric_live,
    }
    if status != STATUS_ACTIVE:
        confirming = [row for row in confirming if row["status"] == "observed"]
        for item in consumed:
            item["used_for_activation"] = False

    latest_evidence = max((row["available_on"] for row in in_cutoff), default=None)
    canonical = json.dumps(
        {
            "cutoff": cutoff.isoformat(),
            "case_id": CASE_ID,
            "evidence": [row["content_sha256"] for row in in_cutoff],
            "status": status,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    envelope = {
        "schema_version": RESULT_SCHEMA,
        "formula_id": FORMULA_ID,
        "engine_version": ENGINE_VERSION,
        "case_id": CASE_ID,
        "symbol": SYMBOL,
        "case_family": CASE_FAMILY,
        "status": status,
        "blocked_reasons": sorted(set(reasons)),
        "thesis": {
            "thesis_id": "thesis_mari_peshawar_working_interest_observed",
            "assertion": "Mari Energies reported acquisition of working interest in Peshawar Block as operator.",
            "status": thesis_status,
            "activation": "active" if status == STATUS_ACTIVE else "suppressed",
        },
        "confirming_indicators": confirming,
        "disconfirming_indicators": disconfirming if status in {STATUS_ACTIVE, STATUS_TRUTH} else [],
        "evidence_cutoff": {
            "as_of_date": cutoff.isoformat(),
            "latest_allowed_evidence_date": cutoff.isoformat(),
            "latest_retained_evidence_date": latest_evidence,
            "stale_days": STALE_DAYS,
        },
        "next_monitor": {
            "next_monitor_date": next_quarter_end(cutoff).isoformat(),
            "triggers": list(TRIGGERS),
        },
        "stale_input_warnings": sorted(set(stale_warnings)),
        "suppressed": suppressed,
        "source_facts": [
            {
                "document_id": row["document_id"],
                "page": row["page"],
                "content_sha256": row["content_sha256"],
                "available_on": row["available_on"],
            }
            for row in in_cutoff
        ],
        "consumed_artifacts": consumed,
        "run_receipt": {
            "inputs_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "contract_version": ENGINE_VERSION,
        },
        "policy": {
            "research_only": True,
            "no_advice": True,
            "no_fetch": True,
            "no_invented_values": True,
            "fail_closed_on_red_financial_truth": True,
            "fail_closed_on_lookahead": True,
            "fail_closed_on_stale_required_artifacts": True,
        },
    }
    dumped = json.dumps(envelope)
    if _ADVICE_RE.search(dumped):
        raise ValueError("advice language is forbidden")
    return envelope


def build_retained_monitor(root: Path | None = None, *, cutoff_date: str | None = None, write: bool = False) -> dict[str, Any]:
    root = root or ROOT
    cases = load_json(root / "state" / "company_intel" / "intelligence_cases.json", {})
    truth = load_json(root / "state" / "company_intel" / "financial_truth_qualification.json", {})
    valuation = load_json(root / "state" / "company_intel" / "mari_enp_valuation_engine.json", {})
    scenario_lab = load_json(root / "state" / "company_intel" / "mari_enp_scenario_lab.json", {})
    expectations = load_json(root / "state" / "company_intel" / "market_expectations.json", {})
    case = _extract_case(cases)
    cutoff = cutoff_date or (as_date((case or {}).get("as_of")) or as_date(cases.get("as_of")))
    if cutoff is None:
        raise ValueError("retained cutoff_date could not be read from the observed case")
    envelope = evaluate_monitor(
        cutoff_date=cutoff.isoformat(),
        cases=cases,
        truth=truth,
        valuation=valuation,
        scenario_lab=scenario_lab,
        expectations=expectations,
    )
    if write:
        save_json(root / "state" / "company_intel" / "mari_enp_thesis_monitor.json", envelope)
    return envelope


def build(*, write: bool = True) -> dict[str, Any]:
    return build_retained_monitor(ROOT, write=write)


def main() -> None:
    envelope = build(write=True)
    print(f"mari_enp_thesis_monitor: {envelope['status']} -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

