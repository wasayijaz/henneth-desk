"""Exact source contract for the owner-approved MARI sales-event intake."""
from __future__ import annotations

MARI_SALES_EVENT_DOCUMENTS: dict[str, dict[str, str]] = {
    "psx:280337": {
        "symbol": "MARI",
        "company_name": "Mari Energies Limited",
        "title": "Launch of Pakistan First and Largest Purpose-Built AI Ready Data Centre Campus",
        "published_at": "2026-07-24T16:26:00+05:00",
        "source_url": "https://dps.psx.com.pk/download/document/280337.pdf",
        "observed_transport_sha256": "acdfaac317a7f2650a9ac11f2e98b69ebf37ce30a3134b51b61c084531286996",
        "event_type": "product_launch",
        "evidence_pattern": r"\bofficially\s+launched\s+Karakoram-01\b",
    },
    "psx:280161": {
        "symbol": "MARI",
        "company_name": "Mari Energies Limited",
        "title": "Clarification of News Item",
        "published_at": "2026-07-21T14:07:00+05:00",
        "source_url": "https://dps.psx.com.pk/download/document/280161.pdf",
    },
}

MARI_SALES_EVENT_INTAKE_IDS = frozenset(MARI_SALES_EVENT_DOCUMENTS)
