"""Fail-closed contract for MLCF/PIOC cement analogue eligibility.

This is deliberately a small, injected-observation contract.  It does not
search for peers, read state, calculate returns, or make an economic claim.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
import re
from typing import Any, Mapping

CONTRACT_VERSION = "mlcf_pioc_analogue_eligibility_v1"
STATUSES = ("eligible", "insufficient", "blocked")
TIERS = ("same_company", "same_official_sector")
HORIZONS = ("1Q", "2Q", "4Q", "8Q")
MIN_SAMPLE = 3

_HASH = re.compile(r"^[0-9a-fA-F]{64}$")
_DATE_KEYS = {"effective_date", "available_on", "cutoff", "endpoint_date"}
_BANNED = (
    "you should", "buy", "sell", "causal", "caused", "will lead", "forecast",
    "valuation", "target price",
)

_TARGET_KEYS = {
    "event_id", "symbol", "target_symbol", "event_type", "event_subtype",
    "effective_date", "mechanism", "scale", "official_sector", "source",
}
_SOURCE_KEYS = {"id", "hash", "page", "available_on", "cutoff"}
_CANDIDATE_KEYS = {
    "candidate_id", "event_id", "symbol", "event_type", "event_subtype",
    "effective_date", "tier", "official_sector", "mechanism", "scale",
    "horizon", "source", "endpoint_date", "endpoint_available_on",
    "endpoint_status", "outcome_return_pct",
}
_ROOT_KEYS = {
    "contract_version", "mode", "cutoff", "target_event", "candidate_observations",
    "existing_mlcf_analogues_insufficient",
}

REAL_TARGET = {
    "event_id": "evt_6e9b520a122b8f2d4a59",
    "symbol": "MLCF",
    "target_symbol": "PIOC",
    "event_type": "acquisition_divestment",
    "event_subtype": "acquisition",
    "effective_date": "2025-12-18",
    "mechanism": "cement_acquisition_control",
    "scale": "dispatch_inclusion",
    "official_sector": "Cement",
    "source": {"id": "psx:267429", "hash": "98cf83c9a286999c8006a7f73f490248f26694c9edbfc815b3dbd9188ee22a54", "page": 3, "available_on": "2025-12-18", "cutoff": "2025-12-18"},
}


def _day(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _text_has_banned(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.casefold()
        return any(token in lowered for token in _BANNED)
    if isinstance(value, Mapping):
        return any(_text_has_banned(v) for v in value.values())
    if isinstance(value, list):
        return any(_text_has_banned(v) for v in value)
    return False


def _closed(mapping: Mapping[str, Any], allowed: set[str], path: str, errors: list[str]) -> None:
    for key in mapping:
        if key not in allowed:
            errors.append(f"{path}.{key}: unknown key")


def _source_errors(source: Any, *, cutoff: date | None, mode: str, path: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(source, Mapping):
        return [f"{path}: must be a mapping"]
    _closed(source, _SOURCE_KEYS, path, errors)
    if not _nonempty(source.get("id")):
        errors.append(f"{path}.id: required")
    source_hash = source.get("hash")
    if not isinstance(source_hash, str) or not _HASH.fullmatch(source_hash):
        errors.append(f"{path}.hash: must be a 64-character hexadecimal hash")
    page = source.get("page")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        errors.append(f"{path}.page: must be a positive integer")
    available = _day(source.get("available_on"))
    if available is None:
        errors.append(f"{path}.available_on: must be YYYY-MM-DD")
    source_cutoff = _day(source.get("cutoff"))
    if source_cutoff is None:
        errors.append(f"{path}.cutoff: must be YYYY-MM-DD")
    if available and source_cutoff and available > source_cutoff:
        errors.append(f"{path}: available_on must not be after cutoff")
    if cutoff and source_cutoff and source_cutoff > cutoff:
        errors.append(f"{path}.cutoff: after product cutoff")
    if mode == "fixture" and not str(source.get("id") or "").startswith("fixture:"):
        errors.append(f"{path}.id: fixture mode requires fixture: source id")
    if mode == "real" and str(source.get("id") or "").startswith("fixture:"):
        errors.append(f"{path}.id: real mode rejects fixture source")
    return errors


def _target_errors(target: Any, *, cutoff: date | None, mode: str) -> list[str]:
    errors: list[str] = []
    path = "target_event"
    if not isinstance(target, Mapping):
        return [f"{path}: must be a mapping"]
    _closed(target, _TARGET_KEYS, path, errors)
    for key in ("event_id", "symbol", "target_symbol", "event_type", "event_subtype", "mechanism", "scale", "official_sector"):
        if not _nonempty(target.get(key)):
            errors.append(f"{path}.{key}: required non-empty string")
    if target.get("symbol") != "MLCF" or target.get("target_symbol") != "PIOC":
        errors.append(f"{path}: must identify MLCF to PIOC")
    effective = _day(target.get("effective_date"))
    if effective is None:
        errors.append(f"{path}.effective_date: must be YYYY-MM-DD")
    elif cutoff and effective > cutoff:
        errors.append(f"{path}.effective_date: after product cutoff")
    errors.extend(_source_errors(target.get("source"), cutoff=cutoff, mode=mode, path=f"{path}.source"))
    if mode == "real":
        for key, expected in REAL_TARGET.items():
            if key == "source":
                continue
            if target.get(key) != expected:
                errors.append(f"{path}.{key}: does not match canonical MLCF/PIOC target")
        source = target.get("source") or {}
        for key, expected in REAL_TARGET["source"].items():
            if source.get(key) != expected:
                errors.append(f"{path}.source.{key}: does not match canonical MLCF source binding")
    return errors


def _candidate_errors(candidate: Any, *, target: Mapping[str, Any], cutoff: date | None, mode: str, index: int) -> list[str]:
    path = f"candidate_observations[{index}]"
    errors: list[str] = []
    if not isinstance(candidate, Mapping):
        return [f"{path}: must be a mapping"]
    _closed(candidate, _CANDIDATE_KEYS, path, errors)
    for key in ("candidate_id", "event_id", "symbol", "event_type", "event_subtype", "mechanism", "scale"):
        if not _nonempty(candidate.get(key)):
            errors.append(f"{path}.{key}: required non-empty string")
    if candidate.get("tier") not in TIERS:
        errors.append(f"{path}.tier: must be one of {TIERS}")
    if candidate.get("horizon") not in HORIZONS:
        errors.append(f"{path}.horizon: must be one of {HORIZONS}")
    if candidate.get("event_type") != target.get("event_type") or candidate.get("event_subtype") != target.get("event_subtype"):
        errors.append(f"{path}: event type/subtype must exactly match target")
    if candidate.get("mechanism") != target.get("mechanism"):
        errors.append(f"{path}.mechanism: incompatible cement mechanism")
    if candidate.get("scale") != target.get("scale"):
        errors.append(f"{path}.scale: incompatible acquisition/commissioning/dispatch scale")
    effective = _day(candidate.get("effective_date")); target_day = _day(target.get("effective_date"))
    if effective is None:
        errors.append(f"{path}.effective_date: must be YYYY-MM-DD")
    elif target_day and effective >= target_day:
        errors.append(f"{path}.effective_date: candidate must be strictly ex ante")
    if candidate.get("tier") == "same_company" and candidate.get("symbol") != target.get("symbol"):
        errors.append(f"{path}.symbol: same_company tier requires target symbol")
    if candidate.get("tier") == "same_official_sector":
        if candidate.get("symbol") == target.get("symbol"):
            errors.append(f"{path}.symbol: sector tier must be another symbol")
        if not _nonempty(candidate.get("official_sector")):
            errors.append(f"{path}.official_sector: required for sector tier")
        elif _nonempty(target.get("official_sector")) and candidate.get("official_sector") != target.get("official_sector"):
            errors.append(f"{path}.official_sector: must exactly match target official sector")
    endpoint = _day(candidate.get("endpoint_date")); endpoint_available = _day(candidate.get("endpoint_available_on"))
    if endpoint is None:
        errors.append(f"{path}.endpoint_date: required YYYY-MM-DD")
    if endpoint_available is None:
        errors.append(f"{path}.endpoint_available_on: required YYYY-MM-DD")
    if cutoff and endpoint and endpoint > cutoff:
        errors.append(f"{path}.endpoint_date: after cutoff")
    if cutoff and endpoint_available and endpoint_available > cutoff:
        errors.append(f"{path}.endpoint_available_on: after cutoff")
    if endpoint_available and target_day and endpoint_available > target_day:
        errors.append(f"{path}.endpoint_available_on: endpoint evidence was not available ex ante to target")
    if endpoint and endpoint_available and endpoint_available < endpoint:
        errors.append(f"{path}.endpoint_available_on: must be on or after endpoint_date")
    if endpoint and effective and endpoint <= effective:
        errors.append(f"{path}.endpoint_date: must be after event date")
    if endpoint and target_day and endpoint >= target_day:
        errors.append(f"{path}.endpoint_date: endpoint must be before target event")
    endpoint_status = candidate.get("endpoint_status")
    if endpoint_status not in {"mature", "immature", "unavailable"}:
        errors.append(f"{path}.endpoint_status: invalid status")
    if endpoint_status == "mature" and (not endpoint or (cutoff and endpoint > cutoff)):
        errors.append(f"{path}: mature endpoint must be available ex ante by cutoff")
    value = candidate.get("outcome_return_pct")
    if endpoint_status == "mature" and not _finite(value):
        errors.append(f"{path}.outcome_return_pct: mature outcome requires finite number")
    if endpoint_status != "mature" and value is not None:
        errors.append(f"{path}.outcome_return_pct: non-mature outcome must be absent")
    errors.extend(_source_errors(candidate.get("source"), cutoff=cutoff, mode=mode, path=f"{path}.source"))
    source = candidate.get("source")
    source_available = _day(source.get("available_on")) if isinstance(source, Mapping) else None
    if source_available and effective and source_available > effective:
        errors.append(f"{path}.source.available_on: candidate evidence must be available by candidate event date")
    if source_available and target_day and source_available > target_day:
        errors.append(f"{path}.source.available_on: candidate evidence was not available ex ante to target")
    return errors


def validate_payload(payload: Mapping[str, Any]) -> list[str]:
    """Return deterministic violations; an empty list means contract-valid input."""
    errors: list[str] = []
    if not isinstance(payload, Mapping):
        return ["payload: must be a mapping"]
    _closed(payload, _ROOT_KEYS, "payload", errors)
    if payload.get("contract_version") != CONTRACT_VERSION:
        errors.append("contract_version: mismatch")
    mode = payload.get("mode")
    if mode not in {"fixture", "real"}:
        errors.append("mode: must be fixture or real")
    cutoff = _day(payload.get("cutoff"))
    if cutoff is None:
        errors.append("cutoff: must be YYYY-MM-DD")
    errors.extend(_target_errors(payload.get("target_event"), cutoff=cutoff, mode=str(mode),))
    reasons = payload.get("existing_mlcf_analogues_insufficient")
    if not isinstance(reasons, list) or not reasons or any(not _nonempty(item) for item in reasons):
        errors.append("existing_mlcf_analogues_insufficient: non-empty list of reasons required")
    candidates = payload.get("candidate_observations")
    if not isinstance(candidates, list):
        errors.append("candidate_observations: must be a list")
        candidates = []
    target = payload.get("target_event") if isinstance(payload.get("target_event"), Mapping) else {}
    for index, candidate in enumerate(candidates):
        errors.extend(_candidate_errors(candidate, target=target, cutoff=cutoff, mode=str(mode), index=index))
    seen: set[tuple[str, str, str, str]] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            continue
        source = candidate.get("source") if isinstance(candidate.get("source"), Mapping) else {}
        key = (str(candidate.get("candidate_id")), str(candidate.get("event_id")), str(source.get("id")), str(candidate.get("horizon")))
        if key in seen:
            errors.append(f"candidate_observations[{index}]: duplicate candidate/event/source/horizon observation")
        seen.add(key)
    if _text_has_banned(payload):
        errors.append("payload: unknown/advice/causal language is forbidden")
    try:
        json.dumps(payload, sort_keys=True, ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError):
        errors.append("payload: JSON must be finite and serializable")
    return errors


def observation_fingerprint(candidate: Mapping[str, Any]) -> str:
    """Stable id for an already validated observation; no evidence is created."""
    raw = json.dumps(candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = [
    "CONTRACT_VERSION", "STATUSES", "TIERS", "HORIZONS", "MIN_SAMPLE",
    "validate_payload", "observation_fingerprint",
]
