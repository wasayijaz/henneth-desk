#!/usr/bin/env python3
"""Focused checks for the provenance-preserving share-capital parser."""
from __future__ import annotations

from share_capital import extract_share_capital_evidence


def main() -> int:
    doc = {
        "doc_id": "psx:260947",
        "title": "DGKC Annual Report for the year ended June 30, 2025",
        "source_url": "https://dps.psx.com.pk/download/document/260947.pdf",
        "content_sha256": "1a10091295cf7a815f1910eb418215d501d42b52e39dcbd0b54a53fd1aceaa7d",
        "period_end": "2025-06-30",
        "symbol": "DGKC",
    }
    page = "2025 2024 Note (Rupees in thousand) Issued, subscribed and paid up share capital 438,119,118 ordinary shares of Rs 10 each 5 4,381,191 4,381,191 Other reserves"
    rows = extract_share_capital_evidence(doc, [page], [{"page": 234}])
    assert len(rows) == 1
    row = rows[0]
    assert row["value"] == 438_119_118
    assert row["paid_up_capital_value"] == 4_381_191
    assert row["source"]["id"] == "psx:260947"
    assert row["source"]["url"].endswith("260947.pdf")
    assert row["source"]["content_sha256"] == doc["content_sha256"]
    assert row["source"]["page"] == 234
    assert row["approved"] is False
    assert row["readiness"] == "candidate_only"

    # Authorised shares must not match: only the issued/paid-up row qualifies.
    authorised = "(Rupees in thousand) Authorised share capital 950,000,000 ordinary shares of Rs 10 each 9,500,000"
    assert extract_share_capital_evidence(doc, [authorised], [{"page": 234}]) == []

    # No source identity or broken arithmetic can produce a candidate.
    broken = {**doc, "content_sha256": "bad"}
    assert extract_share_capital_evidence(broken, [page]) == []
    mismatch = page.replace("4,381,191 4,381,191", "4,000,000 4,000,000")
    assert extract_share_capital_evidence(doc, [mismatch]) == []
    print("share capital self-check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
