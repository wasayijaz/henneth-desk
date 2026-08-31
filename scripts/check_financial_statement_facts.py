#!/usr/bin/env python3
"""Offline regression checks for the conservative financial statement parser."""
from __future__ import annotations

import sys

from financial_statement_facts import detect_scale_info, extract_facts


def _w(x0: float, y0: float, text: str, block: int, line: int, word: int = 0):
    width = max(8.0, float(len(text) * 5.0))
    return (x0, y0, x0 + width, y0 + 10.0, text, block, line, word)


def main() -> int:
    assert detect_scale_info("(PKR in �000�)") == (1_000, [])
    words = [
        _w(50, 40, "Consolidated", 0, 0), _w(120, 40, "Statement", 0, 0, 1),
        _w(190, 40, "of", 0, 0, 2), _w(210, 40, "Profit", 0, 0, 3),
        _w(260, 40, "or", 0, 0, 4), _w(280, 40, "Loss", 0, 0, 5),
        _w(50, 70, "For", 0, 1), _w(75, 70, "the", 0, 1, 1),
        _w(105, 70, "year", 0, 1, 2), _w(140, 70, "ended", 0, 1, 3),
        _w(180, 70, "June", 0, 1, 4), _w(220, 70, "30,", 0, 1, 5),
        _w(245, 70, "2024", 0, 1, 6),
        _w(410, 110, "2024", 1, 0), _w(500, 110, "2023", 1, 1),
        _w(350, 130, "Note", 1, 2), _w(420, 130, "(PKR", 1, 2, 1), _w(450, 130, "in", 1, 2, 2),
        _w(465, 130, "�000�)", 1, 2, 2),
        _w(50, 160, "Revenue", 2, 0), _w(350, 160, "31.1", 3, 0),
        _w(410, 160, "100", 4, 0), _w(500, 160, "90", 5, 0),
        _w(50, 180, "Cost", 6, 0), _w(80, 180, "of", 6, 0, 1),
        _w(100, 180, "sales", 6, 0, 2), _w(410, 180, "60", 7, 0),
        _w(500, 180, "55", 8, 0),
        _w(50, 200, "Gross", 9, 0), _w(85, 200, "profit", 9, 0, 1),
        _w(410, 200, "40", 10, 0), _w(500, 200, "35", 11, 0),
    ]
    page = "Consolidated Statement of Profit or Loss For the year ended June 30, 2024"
    facts = extract_facts(
        {"doc_id": "fixture", "title": "Annual Report 2024", "source_url": "https://example.test/a.pdf",
         "content_sha256": "fixture", "published_at": "2024-08-01"},
        [page], [words], [{"page": 1, "text": page, "words": words}],
    )
    assert facts, "geometry fixture emitted no facts"
    actual = {(f["line"], f["period_end"], f["consolidation"], f["scale"], f["duration_months"])
            for f in facts}
    assert actual == {
                ("revenue", "2024-06-30", "consolidated", 1_000, 12),
                ("revenue", "2023-06-30", "consolidated", 1_000, 12),
                ("gross_profit", "2024-06-30", "consolidated", 1_000, 12),
                ("gross_profit", "2023-06-30", "consolidated", 1_000, 12),
            }
    assert all(f["readiness"] == "model_loadable" and f["currency"] == "PKR" for f in facts)
    assert all("cost of sales" not in f["reported_label"].lower() for f in facts)

    # Consolidated cash-flow statements often place the OCF total well below
    # the header and label it ``Net cash inflow from operating activities``.
    # This must resolve to the total row (not the section heading) with the
    # same geometry/provenance requirements as income facts.
    cash_words = [
        _w(50, 40, "Consolidated", 0, 0), _w(120, 40, "Statement", 0, 0, 1),
        _w(190, 40, "of", 0, 0, 2), _w(210, 40, "Cash", 0, 0, 3),
        _w(260, 40, "Flows", 0, 0, 4),
        _w(50, 70, "For", 0, 1), _w(75, 70, "the", 0, 1, 1),
        _w(105, 70, "year", 0, 1, 2), _w(140, 70, "ended", 0, 1, 3),
        _w(180, 70, "June", 0, 1, 4), _w(220, 70, "30,", 0, 1, 5),
        _w(245, 70, "2024", 0, 1, 6),
        _w(410, 110, "2024", 1, 0), _w(500, 110, "2023", 1, 1),
        _w(350, 130, "Note", 1, 2), _w(420, 130, "(PKR", 1, 2, 1),
        _w(450, 130, "in", 1, 2, 2), _w(465, 130, "�000�)", 1, 2, 3),
        _w(50, 160, "Cash", 2, 0), _w(85, 160, "flows", 2, 0, 1),
        _w(120, 160, "from", 2, 0, 2), _w(160, 160, "operating", 2, 0, 3),
        _w(230, 160, "activities", 2, 0, 4),
        _w(50, 280, "Net", 3, 0), _w(75, 280, "cash", 3, 0, 1),
        _w(110, 280, "inflow", 3, 0, 2), _w(155, 280, "from", 3, 0, 3),
        _w(200, 280, "operating", 3, 0, 4), _w(270, 280, "activities", 3, 0, 5),
        _w(410, 280, "100", 4, 0), _w(500, 280, "90", 5, 0),
    ]
    cash_page = "Consolidated Statement of Cash Flows For the year ended June 30, 2024"
    cash_facts = extract_facts(
        {"doc_id": "cash-fixture", "title": "Annual Report 2024", "source_url": "https://example.test/c.pdf",
         "content_sha256": "cash-fixture", "published_at": "2024-08-01"},
        [cash_page], [cash_words], [{"page": 1, "text": cash_page, "words": cash_words}],
    )
    ocf = [fact for fact in cash_facts if fact["line"] == "operating_cash_flow"]
    assert {(fact["period_end"], fact["value"], fact["readiness"], fact["consolidation"])
            for fact in ocf} == {
                ("2024-06-30", 100_000, "model_loadable", "consolidated"),
                ("2023-06-30", 90_000, "model_loadable", "consolidated"),
            }

    # Later-page MLCF consolidated interim statements use wrapped duration
    # headers ("Half/Nine month ended" + "Quarter ended") and an explicit
    # equity-holder PAT row.  These are direct three-month columns, not
    # derived values; retain the original source page and availability date.
    def mlcf_page(period_title, period_end, page_no, revenue_q, pat_q, eps_q):
        words = [
            _w(50, 40, "CONSOLIDATED", 0, 0), _w(130, 40, "CONDENSED", 0, 0, 1),
            _w(220, 40, "INTERIM", 0, 0, 2), _w(300, 40, "STATEMENT", 0, 0, 3),
            _w(400, 40, "OF", 0, 0, 4), _w(430, 40, "PROFIT", 0, 0, 5),
            _w(490, 40, "OR", 0, 0, 6), _w(515, 40, "LOSS", 0, 0, 7),
            _w(60, 70, "six", 0, 1), _w(90, 70, "months", 0, 1, 1),
            _w(130, 70, "ended", 0, 1, 2), _w(360, 70, "quarter", 0, 1, 3),
            _w(410, 70, "ended", 0, 1, 4),
            _w(260, 100, str(period_end[:4]), 1, 0), _w(330, 100, str(int(period_end[:4])-1), 1, 0, 1),
            _w(460, 100, str(period_end[:4]), 1, 0, 2), _w(530, 100, str(int(period_end[:4])-1), 1, 0, 3),
            _w(180, 120, "(Rupees", 1, 4), _w(230, 120, "in", 1, 4, 1), _w(250, 120, "thousand)", 1, 4, 2),
            _w(50, 150, "Revenue", 2, 0), _w(260, 150, "500", 2, 1), _w(330, 150, "450", 2, 2), _w(460, 150, str(revenue_q), 2, 3), _w(530, 150, "400", 2, 4),
            _w(50, 180, "Equity", 3, 0), _w(95, 180, "holders", 3, 0, 1), _w(150, 180, "of", 3, 0, 2), _w(170, 180, "the", 3, 0, 3), _w(195, 180, "Holding", 3, 0, 4), _w(210, 180, "Company", 3, 0, 5), _w(260, 180, "1000", 3, 1), _w(330, 180, "900", 3, 2), _w(460, 180, str(pat_q), 3, 3), _w(530, 180, "800", 3, 4),
            _w(50, 210, "Earnings", 4, 0), _w(105, 210, "per", 4, 0, 1), _w(130, 210, "share", 4, 0, 2), _w(260, 210, "5.0", 4, 1), _w(330, 210, "4.5", 4, 2), _w(460, 210, str(eps_q), 4, 3), _w(530, 210, "4.0", 4, 4),
        ]
        text = f"Consolidated statement of profit or loss {period_title}"
        return extract_facts(
            {"doc_id": f"psx:{page_no}", "title": "MLCF Quarterly Financial Statements", "source_url": f"https://dps.psx.com.pk/download/document/{page_no}.pdf", "content_sha256": "a"*64, "period_end": period_end, "published_at": f"{period_end[:4]}-04-28"},
            [text], [words], [{"page": page_no, "text": text, "words": words}],
        )

    q2 = mlcf_page("for the six-month period and quarter ended December 31, 2025", "2025-12-31", 33, 18935494, 3118059, 2.98)
    q3 = mlcf_page("for nine months period and quarter ended March 31, 2026", "2026-03-31", 29, 21545015, 1770955, 1.86)
    for facts, page, rev, pat, eps in ((q2, 33, 18935494, 3118059, 2.98), (q3, 29, 21545015, 1770955, 1.86)):
        assert facts and any(f.get("duration_months") == 3 for f in facts), "wrapped-quarter fixture emitted no direct three-month facts"
        current = [f for f in facts if f["column_role"] == "current_period" and f["duration_months"] == 3]
        by_line = {f["line"]: f for f in current}
        required = {"revenue", "profit_after_tax_attributable", "basic_eps"}
        assert required.issubset(by_line), f"missing direct-quarter triplet: {required - set(by_line)}"
        actual_triplet = {line: by_line[line]["value"] for line in required}
        expected_triplet = {"revenue": rev * 1000, "profit_after_tax_attributable": pat * 1000, "basic_eps": eps}
        assert actual_triplet == expected_triplet, f"unexpected direct-quarter triplet: {actual_triplet}"
        assert all(by_line[line]["page"] == page and by_line[line]["consolidation"] == "consolidated" and by_line[line]["readiness"] == "model_loadable" for line in required)

    # Owner-approved MLCF Q1 FY26 page 29 geometry.  The statement's Note
    # column sits immediately left of the first value column (note ``12`` at
    # x294, values at x324/x384), while the EPS row uses the singular
    # ``Earning per share`` issuer label.  The parser must retain only the
    # direct current three-month consolidated Revenue/PAT/EPS triplet.
    q1_words = [
        _w(72, 40, "CONDENSED", 0, 0), _w(150, 40, "INTERIM", 0, 0, 1),
        _w(220, 40, "CONSOLIDATED", 0, 0, 2), _w(320, 40, "STATEMENT", 0, 0, 3),
        _w(400, 40, "OF", 0, 0, 4), _w(425, 40, "PROFIT", 0, 0, 5),
        _w(470, 40, "OR", 0, 0, 6), _w(490, 40, "LOSS", 0, 0, 7),
        _w(317, 70, "Three", 1, 0), _w(343, 70, "Months", 1, 0, 1),
        _w(376, 70, "Period", 1, 0, 2), _w(405, 70, "Ended", 1, 0, 3),
        _w(334, 100, "2025", 2, 0), _w(396, 100, "2024", 2, 1),
        _w(292, 120, "Note", 2, 2), _w(334, 120, "(Rupees", 2, 3),
        _w(369, 120, "in", 2, 3, 1), _w(379, 120, "thousand)", 2, 3, 2),
        _w(72, 150, "Revenue", 3, 0), _w(110, 150, "from", 3, 0, 1),
        _w(140, 150, "contracts", 3, 0, 2), _w(190, 150, "with", 3, 0, 3),
        _w(220, 150, "customers", 3, 0, 4), _w(294, 150, "12", 3, 1),
        _w(324, 150, "16,483,361", 3, 2), _w(384, 150, "15,719,838", 3, 3),
        _w(72, 410, "Profit", 5, 0), _w(110, 410, "is", 5, 0, 1),
        _w(130, 410, "attributable", 5, 0, 2), _w(190, 410, "to:", 5, 0, 3),
        _w(72, 422, "Equity", 5, 1), _w(110, 422, "holders", 5, 1, 1),
        _w(160, 422, "of", 5, 1, 2), _w(180, 422, "the", 5, 1, 3),
        _w(205, 422, "Holding", 5, 1, 4), _w(250, 422, "Company", 5, 1, 5),
        _w(329, 422, "2,728,256", 5, 2), _w(389, 422, "1,342,743", 5, 3),
        _w(72, 500, "Earning", 6, 0), _w(110, 500, "per", 6, 0, 1),
        _w(130, 500, "share", 6, 0, 2), _w(294, 500, "15", 6, 1),
        _w(350, 500, "2.60", 6, 2), _w(410, 500, "1.28", 6, 3),
    ]
    q1_text = "Consolidated statement of profit or loss for the three months period ended September 30, 2025"
    q1_facts = extract_facts(
        {"doc_id": "psx:263397", "title": "MLCF Quarterly Financial Statements",
         "source_url": "https://dps.psx.com.pk/download/document/263397.pdf",
         "content_sha256": "a05eeee23485edd71c6c096a606a3b6fd76d6687e13bdaf032f97b59b9cdcc7e",
         "period_end": "2025-09-30", "published_at": "2025-10-27"},
        [q1_text], [q1_words], [{"page": 29, "text": q1_text, "words": q1_words}],
    )
    q1_current = [f for f in q1_facts if f["column_role"] == "current_period" and f["duration_months"] == 3]
    q1_by_line = {f["line"]: f for f in q1_current}
    assert set(q1_by_line) == {"revenue", "profit_after_tax_attributable", "basic_eps"}, "MLCF Q1 page-29 emitted non-triplet facts"
    assert {line: q1_by_line[line]["value"] for line in ("revenue", "profit_after_tax_attributable", "basic_eps")} == {
        "revenue": 16_483_361_000, "profit_after_tax_attributable": 2_728_256_000, "basic_eps": 2.60,
    }
    assert all(f["page"] == 29 and f["content_sha256"] == "a05eeee23485edd71c6c096a606a3b6fd76d6687e13bdaf032f97b59b9cdcc7e"
               and f["duration_months"] == 3 and f["consolidation"] == "consolidated" and f["currency"] == "PKR"
               and f["unit"] in {"PKR", "PKR/share"} and f["readiness"] == "model_loadable" for f in q1_by_line.values())

    # MARI Q2 geometry: the filing is published in 2026, while the local
    # statement period is explicitly 31.12.2025 and its wrapped year headers
    # are 2025/2024.  The strict shifted-year rule may bind the direct 3M
    # current column, retaining consolidated basis, scale and source identity.
    mari_words = [
        _w(50, 50, "Consolidated", 0, 0), _w(125, 50, "statement", 0, 0, 1),
        _w(205, 50, "of", 0, 0, 2), _w(230, 50, "profit", 0, 0, 3),
        _w(275, 50, "or", 0, 0, 4), _w(300, 50, "loss", 0, 0, 5),
        _w(80, 75, "For", 0, 1), _w(110, 75, "the", 0, 1, 1),
        _w(140, 75, "period", 0, 1, 2), _w(185, 75, "ended", 0, 1, 3),
        _w(240, 75, "31.12.2025", 0, 1, 4),
        _w(268, 105, "Quarter", 1, 0), _w(305, 105, "ended", 1, 0, 1),
        _w(428, 105, "Six", 1, 1), _w(450, 105, "months", 1, 1, 1), _w(495, 105, "ended", 1, 1, 2),
        _w(280, 130, "2025", 2, 0), _w(355, 130, "2024", 2, 1),
        _w(435, 130, "2025", 2, 2), _w(510, 130, "2024", 2, 3),
        _w(180, 150, "(Rupees", 2, 4), _w(230, 150, "in", 2, 4, 1), _w(245, 150, "thousand)", 2, 4, 2),
        _w(50, 180, "Revenue", 3, 0), _w(280, 180, "300", 3, 1), _w(355, 180, "250", 3, 2), _w(435, 180, "700", 3, 3), _w(510, 180, "650", 3, 4),
        _w(50, 205, "Profit", 4, 0), _w(90, 205, "after", 4, 0, 1), _w(125, 205, "taxation", 4, 0, 2), _w(180, 205, "attributable", 4, 0, 3), _w(245, 205, "to", 4, 0, 4), _w(265, 205, "owners", 4, 0, 5), _w(280, 205, "of", 4, 0, 6), _w(300, 205, "the", 4, 0, 7), _w(325, 205, "parent", 4, 0, 8),
        _w(280, 205, "30", 4, 1), _w(355, 205, "20", 4, 2), _w(435, 205, "80", 4, 3), _w(510, 205, "70", 4, 4),
        _w(50, 230, "Earnings", 5, 0), _w(105, 230, "per", 5, 0, 1), _w(130, 230, "share", 5, 0, 2),
        _w(280, 230, "3.0", 5, 1), _w(355, 230, "2.0", 5, 2), _w(435, 230, "7.0", 5, 3), _w(510, 230, "6.0", 5, 4),
    ]
    mari_doc = {"doc_id": "psx:271327", "title": "Transmission of Quarterly Financial Statements",
                "source_url": "https://dps.psx.com.pk/download/document/271327.pdf",
                "content_sha256": "e53fccd6eca58c685dbf9225140056303be704b1f389b876ba33d87aa4b687b3",
                "period_end": "2026-12-31", "published_at": "2026-02-27T09:03:00+05:00"}
    mari_facts = extract_facts(mari_doc, ["Consolidated statement of profit or loss for the period ended 31.12.2025"],
                                [mari_words], [{"page": 38, "text": "Consolidated statement of profit or loss for the period ended 31.12.2025", "words": mari_words}])
    mari_current = {f["line"]: f for f in mari_facts if f["column_role"] == "current_period" and f["duration_months"] == 3}
    assert set(mari_current) == {"revenue", "profit_after_tax_attributable", "basic_eps"}
    assert {line: mari_current[line]["value"] for line in mari_current} == {"revenue": 300_000, "profit_after_tax_attributable": 30_000, "basic_eps": 3.0}
    assert all(f["period_end"] == "2025-12-31" and f["consolidation"] == "consolidated" and f["readiness"] == "model_loadable" and f["page"] == 38 and f["content_sha256"] == mari_doc["content_sha256"] for f in mari_current.values())

    # The same geometry without a local consolidated basis is audit-only; it
    # must never become a model-loadable direct-quarter triplet.
    mari_no_basis = [tuple(list(w[:4]) + [w[4].replace("Consolidated", "Statement")] + list(w[5:])) if w[4] == "Consolidated" else w for w in mari_words]
    no_basis_facts = extract_facts({**mari_doc, "doc_id": "mari-no-basis"}, ["Statement of profit or loss for the period ended 31.12.2025"], [mari_no_basis], [{"page": 38, "text": "Statement of profit or loss for the period ended 31.12.2025", "words": mari_no_basis}])
    assert no_basis_facts and all(f["readiness"] == "audit_only" and f["consolidation"] is None for f in no_basis_facts)

    # A shifted year without an exact independently bound period must fail
    # closed rather than relabelling an unrelated table as the current quarter.
    mismatched = extract_facts({**mari_doc, "doc_id": "mari-mismatched-period", "period_end": "2026-11-30"}, ["Consolidated statement of profit or loss for the period ended 31.12.2025"], [mari_words], [{"page": 38, "text": "Consolidated statement of profit or loss for the period ended 31.12.2025", "words": mari_words}])
    assert not [f for f in mismatched if f["column_role"] == "current_period" and f["duration_months"] == 3]

    # A matching date elsewhere on the page cannot authorize a different
    # wrapped table.  The proof must sit immediately above its duration band.
    remote_date_words = [
        (word[0], 5.0, word[2], 15.0, *word[4:]) if word[1] == 75 else word
        for word in mari_words
    ]
    remote_date = extract_facts(
        mari_doc,
        ["Consolidated statement of profit or loss for the period ended 31.12.2025"],
        [remote_date_words],
        [{"page": 38, "text": "Consolidated statement of profit or loss for the period ended 31.12.2025", "words": remote_date_words}],
    )
    assert not [f for f in remote_date if f["column_role"] == "current_period" and f["duration_months"] == 3]

    # Wrong basis must not be promoted as consolidated evidence.
    bad_words = [tuple(list(w[:4]) + [w[4].replace("CONSOLIDATED", "UNCONSOLIDATED")] + list(w[5:])) if w[4] == "CONSOLIDATED" else w for w in ([
        _w(50, 40, "CONSOLIDATED", 0, 0), _w(130, 40, "Statement", 0, 0, 1), _w(220, 40, "of", 0, 0, 2), _w(250, 40, "Profit", 0, 0, 3), _w(300, 40, "or", 0, 0, 4), _w(325, 40, "Loss", 0, 0, 5)])]
    assert not extract_facts({"doc_id": "bad", "title": "Quarterly Financial Statements", "published_at": "2025-04-01"}, ["bad"], [bad_words], [{"page": 1, "text": "bad", "words": bad_words}])
    print("financial statement facts self-check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
