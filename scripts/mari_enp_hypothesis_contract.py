"""Fail-closed contract for a MARI observed-event hypothesis register.

This is an evidence-lifecycle contract, not an E&P forecast or valuation model.
The caller injects one dated observed event, mutually exclusive hypotheses and
source-bound corroboration/refutation records. Every source is hash-, page-
and document-bound and must be raw-available at the case cutoff. Missing,
untimestamped or lookahead evidence blocks the case; no defaults are invented.
"""
from __future__ import annotations

from datetime import date
import json
import math
import re
from typing import Any, Mapping

CONTRACT_VERSION = "mari_enp_hypothesis_contract_v1"
CASE_SCHEMA = "mari_enp_hypothesis_case_v1"
EVENT_STATUS = "observed"
EVIDENCE_STATUSES = ("available", "missing", "raw_unavailable", "untimestamped", "superseded")
RELATIONS = ("corroborates", "refutes")
HYPOTHESIS_IDS = ("blocks_not_proved_reserves", "strategy_not_execution_schedule")
HYPOTHESIS_TYPE = "observed_text_only"

_CASE_KEYS = {"schema_version", "symbol", "case_id", "as_of_date", "event", "hypotheses", "evidence"}
_EVENT_KEYS = {"event_id", "canonical_event_id", "legacy_event_id", "event_statement", "event_date", "published_date", "available_on", "event_status", "source"}
_HYPOTHESIS_KEYS = {"hypothesis_id", "hypothesis_type", "label", "statement", "exclusive_group", "excludes", "base_confidence"}
_EVIDENCE_KEYS = {"evidence_id", "event_id", "hypothesis_id", "relation", "status", "summary", "event_date", "published_date", "available_on", "weight", "source"}
_SOURCE_KEYS = {"canonical_event_id", "legacy_event_id", "document_id", "content_sha256", "page", "join_key", "source_label", "source_url", "source_path", "raw_available"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_KEY_FRAGMENTS = (
    "price", "revenue", "eps", "npv", "valuation", "forecast", "cash",
    "pkr", "usd", "shares", "fcf", "ebitda", "debt", "cost", "margin", "target",
)


def _as_date(value: Any) -> date | None:
    if not isinstance(value, str) or _DATE_RE.fullmatch(value) is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _keys(mapping: Mapping[str, Any], expected: set[str], prefix: str,
          optional: set[str] | None = None) -> list[str]:
    violations: list[str] = []
    optional = optional or set()
    for key in sorted((set(mapping) - expected - optional), key=str):
        violations.append(f"{prefix}.{key}: unknown field")
    for key in sorted((expected - set(mapping)), key=str):
        violations.append(f"{prefix}.{key}: missing required field")
    return violations


def _forbidden_keys(value: Any, path: str = "case") -> list[str]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            text = str(key).lower()
            if any(fragment in text for fragment in _FORBIDDEN_KEY_FRAGMENTS):
                violations.append(f"{path}.{key}: financial output fields are forbidden")
            violations.extend(_forbidden_keys(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_forbidden_keys(child, f"{path}[{index}]"))
    return violations


def _validate_date_chain(prefix: str, event_date: Any, published_date: Any,
                         available_on: Any, as_of: date) -> list[str]:
    violations: list[str] = []
    parsed = []
    for name, value in (("event_date", event_date), ("published_date", published_date), ("available_on", available_on)):
        item = _as_date(value)
        if item is None:
            violations.append(f"{prefix}.{name}: must be an exact ISO date (YYYY-MM-DD)")
        parsed.append(item)
    if all(item is not None for item in parsed):
        event, published, available = parsed
        if event > published:
            violations.append(f"{prefix}: event_date must be on or before published_date")
        if published > available:
            violations.append(f"{prefix}: published_date must be on or before available_on")
        if available > as_of:
            violations.append(f"{prefix}.available_on: must be on or before as_of_date")
    return violations


def _validate_source(source: Any, prefix: str) -> list[str]:
    if not isinstance(source, Mapping):
        return [f"{prefix}: must be a mapping"]
    required_source_keys = _SOURCE_KEYS - {"source_url", "source_path"}
    violations = _keys(source, required_source_keys, prefix,
                       optional=_SOURCE_KEYS - required_source_keys)
    document_id = source.get("document_id")
    if not _nonempty(document_id):
        violations.append(f"{prefix}.document_id: must be a non-empty string")
    for field in ("canonical_event_id", "legacy_event_id"):
        if not _nonempty(source.get(field)):
            violations.append(f"{prefix}.{field}: must be a non-empty string")
    content_hash = source.get("content_sha256")
    if not isinstance(content_hash, str) or _HASH_RE.fullmatch(content_hash) is None:
        violations.append(f"{prefix}.content_sha256: must be 64 lowercase hex characters")
    page = source.get("page")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        violations.append(f"{prefix}.page: must be an integer >= 1")
    expected_join = f"{document_id}|{page}|{content_hash}" if _nonempty(document_id) and isinstance(page, int) and not isinstance(page, bool) and isinstance(content_hash, str) else None
    if not isinstance(source.get("join_key"), str) or source.get("join_key") != expected_join:
        violations.append(f"{prefix}.join_key: must equal document_id|page|content_sha256")
    if not _nonempty(source.get("source_label")):
        violations.append(f"{prefix}.source_label: must be a non-empty string")
    if not (_nonempty(source.get("source_url")) or _nonempty(source.get("source_path"))):
        violations.append(f"{prefix}: source_url or source_path is required")
    if not isinstance(source.get("raw_available"), bool):
        violations.append(f"{prefix}.raw_available: must be a boolean")
    elif source.get("raw_available") is not True:
        violations.append(f"{prefix}.raw_available: raw-unavailable evidence is blocked")
    return violations


def validate_case(case: Mapping[str, Any]) -> list[str]:
    """Return named violations; an empty list means the observed case is valid."""
    if not isinstance(case, Mapping):
        return ["case: must be a mapping"]
    violations = _keys(case, _CASE_KEYS, "case")
    violations.extend(_forbidden_keys(case))
    try:
        json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError):
        violations.append("case: must be JSON-serializable and finite")
    if case.get("schema_version") != CASE_SCHEMA:
        violations.append(f"schema_version: must equal {CASE_SCHEMA}")
    if case.get("symbol") != "MARI":
        violations.append("symbol: must equal MARI for this MARI-specific contract")
    if not _nonempty(case.get("case_id")):
        violations.append("case_id: must be a non-empty string")
    as_of = _as_date(case.get("as_of_date"))
    if as_of is None:
        violations.append("as_of_date: must be an exact ISO date (YYYY-MM-DD)")

    event = case.get("event")
    if isinstance(event, Mapping):
        violations.extend(_keys(event, _EVENT_KEYS, "event"))
        if not _nonempty(event.get("event_id")):
            violations.append("event.event_id: must be a non-empty string")
        for field in ("canonical_event_id", "legacy_event_id"):
            if not _nonempty(event.get(field)):
                violations.append(f"event.{field}: must be a non-empty string")
        if _nonempty(event.get("event_id")) and _nonempty(event.get("canonical_event_id")) and event.get("event_id") != event.get("canonical_event_id"):
            violations.append("event.event_id: must equal event.canonical_event_id")
        if not _nonempty(event.get("event_statement")):
            violations.append("event.event_statement: must be a non-empty string")
        if event.get("event_status") != EVENT_STATUS:
            violations.append("event.event_status: must equal observed")
        if as_of is not None:
            violations.extend(_validate_date_chain("event", event.get("event_date"), event.get("published_date"), event.get("available_on"), as_of))
        violations.extend(_validate_source(event.get("source"), "event.source"))
        event_source = event.get("source")
        if isinstance(event_source, Mapping):
            for field in ("canonical_event_id", "legacy_event_id"):
                if _nonempty(event.get(field)) and event.get(field) != event_source.get(field):
                    violations.append(f"event.{field}: must reconcile with event.source.{field}")
    else:
        violations.append("event: must be a mapping")

    hypotheses = case.get("hypotheses")
    hypothesis_ids: list[str] = []
    if not isinstance(hypotheses, list) or len(hypotheses) < 2:
        violations.append("hypotheses: must contain at least two mutually exclusive hypotheses")
        hypotheses = []
    labels: set[str] = set()
    statements: set[str] = set()
    groups: set[str] = set()
    for index, hypothesis in enumerate(hypotheses):
        prefix = f"hypotheses[{index}]"
        if not isinstance(hypothesis, Mapping):
            violations.append(f"{prefix}: must be a mapping")
            continue
        violations.extend(_keys(hypothesis, _HYPOTHESIS_KEYS, prefix))
        hypothesis_id = hypothesis.get("hypothesis_id")
        if not _nonempty(hypothesis_id):
            violations.append(f"{prefix}.hypothesis_id: must be a non-empty string")
        else:
            hypothesis_ids.append(hypothesis_id)
        if hypothesis.get("hypothesis_type") != HYPOTHESIS_TYPE:
            violations.append(f"{prefix}.hypothesis_type: must equal {HYPOTHESIS_TYPE}")
        label = hypothesis.get("label")
        statement = hypothesis.get("statement")
        if not _nonempty(label):
            violations.append(f"{prefix}.label: must be a non-empty string")
        elif label.casefold() in labels:
            violations.append(f"{prefix}.label: duplicate hypothesis")
        else:
            labels.add(label.casefold())
        if not _nonempty(statement):
            violations.append(f"{prefix}.statement: must be a non-empty string")
        elif statement.casefold() in statements:
            violations.append(f"{prefix}.statement: duplicate hypothesis")
        else:
            statements.add(statement.casefold())
        group = hypothesis.get("exclusive_group")
        if not _nonempty(group):
            violations.append(f"{prefix}.exclusive_group: must be a non-empty string")
        else:
            groups.add(group)
        excludes = hypothesis.get("excludes")
        if not isinstance(excludes, list) or any(not _nonempty(item) for item in excludes):
            violations.append(f"{prefix}.excludes: must be a list of hypothesis IDs")
        confidence = _finite(hypothesis.get("base_confidence"))
        if confidence is None:
            violations.append(f"{prefix}.base_confidence: must be a finite number")
        elif not 0.0 <= confidence <= 1.0:
            violations.append(f"{prefix}.base_confidence: must be in [0, 1]")
    if len(hypothesis_ids) != len(set(hypothesis_ids)):
        violations.append("hypotheses: duplicate hypothesis_id")
    if set(hypothesis_ids) != set(HYPOTHESIS_IDS):
        violations.append(f"hypotheses: must contain exactly {', '.join(HYPOTHESIS_IDS)}")
    if len(groups) > 1:
        violations.append("hypotheses: all hypotheses must share one exclusive_group")
    if len(hypothesis_ids) >= 2:
        expected_excludes = set(hypothesis_ids)
        for index, hypothesis in enumerate(hypotheses):
            if isinstance(hypothesis, Mapping):
                excludes = hypothesis.get("excludes")
                if isinstance(excludes, list) and set(excludes) != expected_excludes - {hypothesis.get("hypothesis_id")}:
                    violations.append(f"hypotheses[{index}].excludes: must name every other hypothesis exactly once")

    evidence = case.get("evidence")
    evidence_ids: list[str] = []
    evidence_by_hypothesis: dict[str, int] = {}
    relation_seen: set[str] = set()
    event_id = event.get("event_id") if isinstance(event, Mapping) else None
    event_source_id = ((event.get("source") or {}).get("document_id") if isinstance(event, Mapping) and isinstance(event.get("source"), Mapping) else None)
    event_source_seen = False
    if not isinstance(evidence, list) or len(evidence) < 2:
        violations.append("evidence: must contain at least two corroboration/refutation records")
        evidence = []
    for index, record in enumerate(evidence):
        prefix = f"evidence[{index}]"
        if not isinstance(record, Mapping):
            violations.append(f"{prefix}: must be a mapping")
            continue
        violations.extend(_keys(record, _EVIDENCE_KEYS, prefix))
        evidence_id = record.get("evidence_id")
        if not _nonempty(evidence_id):
            violations.append(f"{prefix}.evidence_id: must be a non-empty string")
        else:
            evidence_ids.append(evidence_id)
        if record.get("event_id") != event_id:
            violations.append(f"{prefix}.event_id: must match event.event_id")
        hypothesis_id = record.get("hypothesis_id")
        if hypothesis_id not in hypothesis_ids:
            violations.append(f"{prefix}.hypothesis_id: must reference a declared hypothesis")
        else:
            evidence_by_hypothesis[hypothesis_id] = evidence_by_hypothesis.get(hypothesis_id, 0) + 1
        relation = record.get("relation")
        if relation not in RELATIONS:
            violations.append(f"{prefix}.relation: must be corroborates or refutes")
        else:
            relation_seen.add(relation)
        if record.get("status") != "available":
            status = record.get("status")
            if status not in EVIDENCE_STATUSES:
                violations.append(f"{prefix}.status: must be one of {', '.join(EVIDENCE_STATUSES)}")
            else:
                violations.append(f"{prefix}.status: {status} evidence is blocked; only available is calculable")
        if not _nonempty(record.get("summary")):
            violations.append(f"{prefix}.summary: must be a non-empty string")
        if as_of is not None:
            violations.extend(_validate_date_chain(prefix, record.get("event_date"), record.get("published_date"), record.get("available_on"), as_of))
        weight = _finite(record.get("weight"))
        if weight is None:
            violations.append(f"{prefix}.weight: must be a finite number")
        elif not 0.0 < weight <= 1.0:
            violations.append(f"{prefix}.weight: must be in (0, 1]")
        violations.extend(_validate_source(record.get("source"), f"{prefix}.source"))
        source = record.get("source")
        if isinstance(source, Mapping) and source.get("document_id") == event_source_id:
            event_source_seen = True
    if len(evidence_ids) != len(set(evidence_ids)):
        violations.append("evidence: duplicate evidence_id")
    if "corroborates" not in relation_seen or "refutes" not in relation_seen:
        violations.append("evidence: at least one corroborates and one refutes record is required")
    for hypothesis_id in hypothesis_ids:
        if evidence_by_hypothesis.get(hypothesis_id, 0) == 0:
            violations.append(f"evidence: hypothesis {hypothesis_id} has no corroboration/refutation evidence")
    if event_source_id and not event_source_seen:
        violations.append("evidence: at least one record must retain the observed event source document")
    return violations
