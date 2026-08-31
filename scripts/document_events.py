#!/usr/bin/env python3
"""Deterministic document type, event, and fact extraction.

This is intentionally conservative: a fact is emitted only when a labelled value
is present in source text.  Every fact/event carries an exact bounded excerpt and
one-based page reference.  It is evidence for the Room, never a recommendation.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from document_extract import evidence_for
from mari_sales_event_contract import MARI_SALES_EVENT_DOCUMENTS


DOC_TYPES = ("results", "board_meeting", "agm", "corporate_briefing", "dividend",
             "acquisition", "regulatory", "rating", "appointment", "company_note", "other")
EVENT_TYPES = ("earnings", "board_meeting", "agm", "briefing", "dividend", "acquisition",
               "regulatory_action", "management_change", "rating_change", "contract",
               "credit_event", "product_launch", "other")

_DOC_RULES = (
    ("results", r"\b(results?|profit|loss|eps|financial statements?|quarter|half[- ]year)\b"),
    ("board_meeting", r"\bboard\s+(meeting|of directors)|meeting of the board\b"),
    ("agm", r"\b(agm|annual general meeting)\b"),
    ("corporate_briefing", r"\b(corporate briefing|briefing session|investor presentation)\b"),
    ("dividend", r"\b(dividend|interim dividend|final dividend|bonus share)\b"),
    ("acquisition", r"\b(acqui(sition|re)|merger|amalgamation|takeover)\b"),
    ("regulatory", r"\b(secp|regulator|regulatory action|show[- ]cause|penalty|sanction)\b"),
    ("rating", r"\b(credit rating|rating action|downgraded?|upgraded?)\b"),
    ("appointment", r"\b(appointed|appointment|resigned|resignation|chief executive|ceo)\b"),
    ("company_note", r"\b(target price|overweight|underweight|buy|sell|morning note)\b"),
)

_EVENT_RULES = (
    ("earnings", r"\b(results?|profit|loss|eps|financial statements?|quarter|half[- ]year)\b", 3),
    ("board_meeting", r"\b(board meeting|meeting of the board)\b", 3),
    ("agm", r"\b(agm|annual general meeting)\b", 3),
    ("briefing", r"\b(corporate briefing|briefing session|investor presentation)\b", 3),
    ("dividend", r"\b(interim dividend|final dividend|cash dividend|dividend\s+(?:of|at|@)|bonus shares?)\b", 2),
    ("acquisition", r"\b(acqui(sition|re)|merger|amalgamation|takeover)\b", 4),
    ("regulatory_action", r"\b(regulatory action|show[- ]cause|penalty|sanction(?:ed)?)\b", 4),
    ("management_change", r"\b(appointed(?:\s+as)?|appointment\s+of|resigned|resignation\s+of)\b", 3),
    ("rating_change", r"\b(credit rating|rating action|downgraded?|upgraded?)\b", 3),
    ("contract", r"\b(contract\s+(?:awarded|signed|secured)|awarded\s+(?:a\s+)?contract|order worth|entered into (?:an?\s+)?agreement|memorandum of understanding|mou\s+(?:signed|with))\b", 3),
    ("credit_event", r"\b(default|trading halt|insolvency|going concern)\b", 5),
)
_EVENT_PATTERNS = {event_type: pattern for event_type, pattern, _ in _EVENT_RULES}
_EVENT_PATTERNS["product_launch"] = r"\bofficially\s+launched\s+Karakoram-01\b"

# Labelled values only; this avoids mistaking page numbers for financial facts.
_FACT_RULES = (
    ("eps", r"\beps\s*(?:of|:|=)?\s*(?:rs\.?\s*)?(-?\d+(?:\.\d+)?)", "PKR/share"),
    ("dividend", r"(?<!unclaimed\s)\b(?:cash\s+)?dividend\s*(?:of|:|=)?\s*(?:rs\.?\s*)?(\d+(?:\.\d+)?)", "PKR/share"),
    ("revenue", r"\b(?:revenue|sales|turnover)\s*(?:of|:|=)?\s*(?:rs\.?\s*)?([\d,.]+(?:\s*(?:m|mn|bn|billion|million))?)", "reported"),
    ("profit", r"\b(?:profit|net income|profit after tax|pat)\s*(?:of|:|=)?\s*(?:rs\.?\s*)?([\d,.]+(?:\s*(?:m|mn|bn|billion|million))?)", "reported"),
    ("target_price", r"\btarget\s+price\s*(?:of|:|=)?\s*(?:rs\.?\s*)?(\d+(?:\.\d+)?)", "PKR/share"),
    ("change_pct", r"\b(?:increased?|decreased?|growth|decline|margin)\s*(?:by|of|:|=)?\s*(\d+(?:\.\d+)?)\s*%", "percent"),
)


def _number(value: str) -> float | int | None:
    match = re.search(r"-?(?:\d[\d,]*\.?\d*|\.\d+)", value)
    if not match:
        return None
    token = match.group(0).replace(",", "")
    try:
        n = float(token)
    except ValueError:
        return None
    return int(n) if n.is_integer() else n


def classify_document(title: str | None, text: str) -> str:
    hay = f"{title or ''} {text[:10000]}"
    for kind, pattern in _DOC_RULES:
        if re.search(pattern, hay, re.I):
            return kind
    return "other"


def event_is_supported(event: dict[str, Any]) -> bool:
    """Apply current conservative rules to retained events from older runs."""
    pattern = _EVENT_PATTERNS.get(event.get("event_type"))
    if not pattern:
        return False
    evidence_text = " ".join(
        str(row.get("text") or "") for row in (event.get("evidence") or []) if isinstance(row, dict)
    )
    return bool(evidence_text and re.search(pattern, evidence_text, re.I))


def extract_events(doc_id: str, title: str | None, text: str, pages: list[str],
                   tickers: list[str], source_url: str | None = None,
                   published_at: str | None = None,
                   content_sha256: str | None = None,
                   material_information: bool = False) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``doc_type, events, facts`` with stable IDs and bounded evidence.

    ``priority_weight`` is a deterministic extraction-routing weight (1 routine
    to 5 severe language), not the desk's governed news-impact score.
    """
    doc_type = classify_document(title, text)
    evidence_base = {"source_url": source_url}
    events: list[dict[str, Any]] = []
    for event_type, pattern, weight in _EVENT_RULES:
        ev = evidence_for(pattern, pages)
        if not ev:
            continue
        evidence = {**evidence_base, **ev}
        seed = f"{doc_id}|{content_sha256 or ''}|{event_type}|{published_at or ''}|{json.dumps(evidence, sort_keys=True)}"
        event_id = "evt_" + hashlib.sha256(seed.encode()).hexdigest()[:20]
        events.append({"event_id": event_id, "doc_id": doc_id, "event_type": event_type,
                       "priority_weight": weight, "tickers": sorted(set(tickers)),
                       "event_date": published_at, "evidence": [evidence]})

    # Material-information documents normally remain excluded from event
    # intake.  The sole exception is the exact owner-approved, transport-hash-
    # bound MARI launch source; its event is evidence-led, not title-led.
    policy = MARI_SALES_EVENT_DOCUMENTS.get(doc_id) if material_information else None
    if policy and (content_sha256 == policy.get("observed_transport_sha256")
                   and title == policy.get("title")
                   and published_at == policy.get("published_at")
                   and sorted(set(tickers)) == [policy.get("symbol")]):
        pattern = policy.get("evidence_pattern")
        event_type = policy.get("event_type")
        evidence_match = evidence_for(pattern, pages) if pattern and event_type else None
        if evidence_match:
            evidence = {**evidence_base, **evidence_match}
            seed = f"{doc_id}|{content_sha256}|{event_type}|{published_at}|{json.dumps(evidence, sort_keys=True)}"
            events.append({
                "event_id": "evt_" + hashlib.sha256(seed.encode()).hexdigest()[:20],
                "doc_id": doc_id, "event_type": event_type, "priority_weight": 3,
                "tickers": sorted(set(tickers)), "event_date": published_at,
                "content_sha256": content_sha256, "evidence": [evidence],
            })

    facts: list[dict[str, Any]] = []
    for fact_type, pattern, unit in _FACT_RULES:
        for match in re.finditer(pattern, text, re.I):
            raw_value = match.group(1).strip()
            value = _number(raw_value)
            if value is None:
                continue
            suffix_match = re.search(r"\b(m|mn|million|bn|billion)\b", raw_value, re.I)
            scales = {"m": 1_000_000, "mn": 1_000_000, "million": 1_000_000,
                      "bn": 1_000_000_000, "billion": 1_000_000_000}
            multiplier = scales.get(suffix_match.group(1).lower()) if suffix_match else 1
            normalized = value * multiplier if multiplier else None
            ev = evidence_for(re.escape(match.group(0)), pages)
            if not ev:
                continue
            evidence = {**evidence_base, **ev}
            seed = f"{doc_id}|{content_sha256 or ''}|{fact_type}|{raw_value}|{json.dumps(evidence, sort_keys=True)}"
            facts.append({"fact_id": "fact_" + hashlib.sha256(seed.encode()).hexdigest()[:20],
                          "doc_id": doc_id, "fact_type": fact_type, "raw_value": raw_value,
                          "normalized_value": normalized,
                          "unit": unit, "currency": None,
                          "scale_multiplier": multiplier, "tickers": sorted(set(tickers)),
                          "evidence": [evidence]})
    return doc_type, events, facts
