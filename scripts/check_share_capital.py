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

    # MLCF FY2025's retained official PSX annual is a deterministic fixture
    # for the capital-note path.  The parser must preserve the original
    # document identity/hash and original one-based page citation while
    # keeping the result candidate-only until verified restage and owner
    # approval occur.
    mlcf_doc = {
        "doc_id": "psx:260032",
        "title": "MLCF Transmission of Annual Financial Statements for the Year Ended 30.06.2025",
        "source_url": "https://dps.psx.com.pk/download/document/260032.pdf",
        "content_sha256": "4fdfb4cbd2eee65576cbb89b43334ce0c09a7e5ffd573d5bf93b414029eba6d1",
        "period_end": "2025-06-30",
        "symbol": "MLCF",
    }
    mlcf_page = (
        "Consolidated Statement of Financial Position 2025 2024 Note "
        "(Rupees in thousand) Issued, subscribed and paid up share capital "
        "1,047,562,608 ordinary shares of Rs 10 each 5 10,475,626 10,475,626"
    )
    mlcf_rows = extract_share_capital_evidence(mlcf_doc, [mlcf_page], [{"page": 317}])
    assert len(mlcf_rows) == 1
    mlcf_row = mlcf_rows[0]
    assert mlcf_row["symbol"] == "MLCF"
    assert mlcf_row["value"] == 1_047_562_608
    assert mlcf_row["paid_up_capital_value"] == 10_475_626
    assert mlcf_row["paid_up_capital_unit"] == "PKR thousand"
    assert mlcf_row["source"]["id"] == "psx:260032"
    assert mlcf_row["source"]["url"] == mlcf_doc["source_url"]
    assert mlcf_row["source"]["content_sha256"] == mlcf_doc["content_sha256"]
    assert mlcf_row["source"]["page"] == 317
    assert "1,047,562,608" in mlcf_row["source"]["text"]
    assert "10,475,626" in mlcf_row["source"]["text"]
    assert mlcf_row["approved"] is False
    assert mlcf_row["readiness"] == "candidate_only"
    assert mlcf_row["tie_out"]["status"] == "tied_out"

    # A capital note with non-matching nominal arithmetic must fail closed;
    # it must never become a candidate merely because the share count parses.
    mlcf_broken = mlcf_page.replace("10,475,626 10,475,626", "10,000,000 10,000,000")
    assert extract_share_capital_evidence(mlcf_doc, [mlcf_broken], [{"page": 317}]) == []

    # Authorised shares must not match: only the issued/paid-up row qualifies.
    authorised = "(Rupees in thousand) Authorised share capital 950,000,000 ordinary shares of Rs 10 each 9,500,000"
    assert extract_share_capital_evidence(doc, [authorised], [{"page": 234}]) == []

    # No source identity or broken arithmetic can produce a candidate.
    broken = {**doc, "content_sha256": "bad"}
    assert extract_share_capital_evidence(broken, [page]) == []
    mismatch = page.replace("4,381,191 4,381,191", "4,000,000 4,000,000")
    assert extract_share_capital_evidence(doc, [mismatch]) == []

    # The canonical issuer annual is the only permitted FY25 source path.  Its
    # candidate keeps issuer identity and the original one-based page citation;
    # the PSX distributor duplicate is intentionally not used as a second row.
    issuer_doc = {
        "doc_id": "issuer:39fe974f6ef82bbeadf83938",
        "title": "DGKC Annual Report 2025",
        "source_url": "https://www.dgcement.com/financial-reports/DGAnnual2025.pdf",
        "content_sha256": "96ca1120b238541d4916fb1c777614ee6045f30ab130d2f18e8a1fd5c62bdf73",
        "period_end": "2025-06-30",
        "symbol": "DGKC",
    }
    issuer_page = (
        "Consolidated Statement of Financial Position 2025 2024 Note "
        "(Rupees in thousand) Issued, subscribed and paid up share capital "
        "438,119,118 ordinary shares of Rs 10 each 5 4,381,191 4,381,191"
    )
    issuer_rows = extract_share_capital_evidence(issuer_doc, [issuer_page], [{"page": 254}])
    assert len(issuer_rows) == 1
    issuer_row = issuer_rows[0]
    assert issuer_row["value"] == 438_119_118
    assert issuer_row["source"]["id"] == issuer_doc["doc_id"]
    assert issuer_row["source"]["label"] == issuer_doc["title"]
    assert issuer_row["source"]["url"] == issuer_doc["source_url"]
    assert issuer_row["source"]["content_sha256"] == issuer_doc["content_sha256"]
    assert "issued, subscribed and paid up share capital" in issuer_row["source"]["text"].lower()
    assert issuer_row["source"]["page"] == 254, "consolidated note must beat unconsolidated duplicate"
    assert issuer_row["approved"] is False and issuer_row["readiness"] == "candidate_only"
    assert extract_share_capital_evidence(
        {**issuer_doc, "content_sha256": "0" * 64}, [issuer_page], [{"page": 254}]
    ) == []
    assert extract_share_capital_evidence(
        {**issuer_doc, "page_count": 331}, [issuer_page], [{"page": 254}]
    ) == []
    assert extract_share_capital_evidence(
        {**issuer_doc, "source_url": "https://dps.psx.com.pk/download/document/260947.pdf"},
        [issuer_page], [{"page": 254}],
    ) == []
    print("share capital self-check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
