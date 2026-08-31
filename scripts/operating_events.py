"""Authoritative operating-event contract and deterministic helpers."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

EVENT_TYPES = {
    "hiring_expansion", "capacity_plant_expansion", "exploration_well_discovery",
    "contract_tender", "management_change", "debt_refinancing", "product_launch",
    "supplier_change", "maintenance_shutdown", "regulatory_change", "acquisition_divestment",
}
INTELLIGENCE_TYPES = {"reported_fact", "derived_fact", "inference", "scenario", "forecast"}
SOURCE_LEVELS = {1, 2, 3, 4, 5, 6}
TYPE_MAP = {
    "contract": "contract_tender", "management_change": "management_change",
    "credit_event": "debt_refinancing", "acquisition": "acquisition_divestment",
    "regulatory_action": "regulatory_change", "product_launch": "product_launch",
}
STRICT_EVENT_PATTERNS = {
    "contract_tender": r"\b(contract\s+(?:awarded|signed|secured)|awarded\s+(?:a\s+)?contract|order\s+worth|entered\s+into\s+(?:an?\s+)?agreement|memorandum\s+of\s+understanding|mou\s+(?:signed|with))\b",
    "management_change": r"\b(?:appointed(?:\s+as)?|appointment\s+of|resigned|resignation\s+of)\b.{0,80}\b(?:chief\s+executive|ceo|chief\s+financial|cfo|director|chairman|company\s+secretary)\b|\b(?:chief\s+executive|ceo|chief\s+financial|cfo|director|chairman|company\s+secretary)\b.{0,80}\b(?:appointed|resigned|appointment|resignation)\b",
    "debt_refinancing": r"\b(default\s+in\s+payment\s+of\s+debts|strategy\s+for\s+liquidity\s+problems|debt\s+restructur(?:e|ing)|refinanc(?:e|ing)|going\s+concern|insolvency|trading\s+halt)\b",
    "acquisition_divestment": r"\b(public\s+announcement\s+of\s+(?:intention|offer)|offer\s+to\s+acquire|acquisition\s+of\s+(?:ordinary\s+)?shares|paid-up\s+share\s+capital|takeover|divest(?:ment|ed)|disposal\s+of\s+(?:subsidiary|shares|business)|acquired\s+(?:control|stake|shareholding)|acquisition\s+of\s+.+(?:plant|business|company|subsidiary|blocks?))\b",
    "regulatory_change": r"\b(regulatory\s+action|show[- ]cause|competition\s+ordinance|secp|regulator)\b",
    "product_launch": r"\bofficially\s+launched\s+Karakoram-01\b.{0,180}\b(?:data\s+cent(?:er|re)|campus)\b",
}
STRICT_EXCLUSIONS = {
    "management_change": r"\b(external\s+auditors?|auditors?|kpmg|remuneration)\b",
    "debt_refinancing": r"\b(customer\s+debts?|credit\s+limit|when\s+a\s+customer|delinquency)\b",
    "acquisition_divestment": r"\b(computer\s+software|power\s+acquisition\s+program)\b",
    "product_launch": r"\b(?:plan(?:s|ned)?|intend(?:s|ed)?|strategy|proposal|media\s+report)\b",
}

def stable_id(*parts: Any, prefix: str = "evt") -> str:
    raw = "|".join(str(p or "") for p in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]}"

def bounded_text(value: Any, limit: int = 280) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "..."

def evidence_hash(*parts: Any) -> str:
    raw = "|".join(str(p or "") for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def strict_event_is_supported(event_type: str | None, evidence_rows: list[dict[str, Any]]) -> bool:
    text = " ".join(str(row.get("text") or "") for row in evidence_rows if isinstance(row, dict))
    if not text:
        return False
    pattern = STRICT_EVENT_PATTERNS.get(event_type or "")
    if not pattern or not re.search(pattern, text, re.I | re.S):
        return False
    exclusion = STRICT_EXCLUSIONS.get(event_type or "")
    return not bool(exclusion and re.search(exclusion, text, re.I | re.S))

def source_quality(url: str | None, source: str | None = None) -> int:
    text = f"{url or ''} {source or ''}".lower()
    if any(x in text for x in ("dps.psx.com.pk", "psx", "secp", "sbp", "regulatory")):
        return 1
    if any(x in text for x in ("investor", "presentation", "earnings", "annual report", "company")):
        return 2
    if any(x in text for x in ("gov", "credit", "industry")):
        return 3
    if any(x in text for x in ("reuters", "bloomberg", "dawn", "business recorder")):
        return 4
    if any(x in text for x in ("job", "supplier", "linkedin")):
        return 5
    return 6

def confidence(level: int, evidence_count: int, corroboration: int = 0, recency_days: int | None = None) -> int:
    score = {1: 82, 2: 74, 3: 64, 4: 54, 5: 40, 6: 20}.get(level, 20)
    score += min(10, max(0, evidence_count - 1) * 5)
    score += min(8, max(0, corroboration) * 4)
    if recency_days is not None and recency_days > 365:
        score -= min(20, (recency_days - 365) // 90 * 5)
    return max(0, min(100, int(score)))

def quality_flags(event: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if not event.get("source_url"): flags.append("missing_source_url")
    if not event.get("evidence"): flags.append("missing_evidence")
    if event.get("confidence", 0) < 50: flags.append("low_confidence")
    if not event.get("effective_date"): flags.append("unknown_effective_date")
    return flags

def iso_date(value: Any) -> str | None:
    text = str(value or "").strip()
    return text[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", text) else None
