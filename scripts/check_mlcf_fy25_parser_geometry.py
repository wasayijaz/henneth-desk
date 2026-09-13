#!/usr/bin/env python3
"""Focused checks for MLCF FY25 separated label/value geometry."""
from __future__ import annotations

from financial_statement_facts import extract_facts


def _w(x0: float, y0: float, text: str, block: int, line: int, word: int = 0):
    width = max(8.0, float(len(text) * 5.0))
    return (x0, y0, x0 + width, y0 + 10.0, text, block, line, word)


def _doc(name: str) -> dict[str, str]:
    return {
        "doc_id": f"psx:{name}",
        "title": "MLCF Annual Report 2025 Financial Statements",
        "period_end": "2025-06-30",
        "published_at": "2025-09-25",
        "source_url": f"https://dps.psx.com.pk/download/document/{name}.pdf",
        "content_sha256": f"{name}hash",
    }


def _words(*, basis: str = "Consolidated", headers: tuple[str, ...] = ("2025", "2024"),
           bands: tuple[tuple[str, str], ...] = (("123,456", "98,765"),)):
    words = [
        _w(50, 20, basis, 0, 0),
        _w(125, 20, "Statement", 0, 0, 1),
        _w(195, 20, "of", 0, 0, 2),
        _w(215, 20, "Profit", 0, 0, 3),
        _w(260, 20, "or", 0, 0, 4),
        _w(280, 20, "Loss", 0, 0, 5),
        _w(50, 45, "(Rupees", 1, 0),
        _w(92, 45, "in", 1, 0, 1),
        _w(108, 45, "thousand)", 1, 0, 2),
    ]
    for idx, header in enumerate(headers):
        words.append(_w(410 + idx * 90, 70, header, 2, 0, idx))
    words.extend([
        _w(50, 100, "Revenue", 3, 0),
        _w(95, 100, "from", 3, 0, 1),
        _w(130, 100, "contracts", 3, 0, 2),
        _w(180, 100, "with", 3, 0, 3),
        _w(215, 100, "customers", 3, 0, 4),
        # This is the target geometry: the label's note reference is a number
        # but the values are a separately extracted, same-baseline band.
        _w(350, 100, "13", 3, 0, 5),
    ])
    for band_idx, band in enumerate(bands):
        y = 100.0 + band_idx * 3.0
        # The actual filing exposes one numeric PDF block per value column.
        words.append(_w(410, y, band[0], 4 + band_idx * 2, 0))
        words.append(_w(500, y, band[1], 5 + band_idx * 2, 0))
    return words


def _facts(words):
    text = "Consolidated statement of profit or loss for the year ended June 30, 2025"
    return extract_facts(_doc("260032"), [text], [words], [{"page": 291, "text": text, "words": words}])


def _words_with_competing_adjacent_band():
    words = _words()
    # Keep the following row's label and values on a nearby baseline.  The
    # parser must not borrow that aligned band for the current row.
    words.extend([
        _w(50, 116, "Cost", 10, 0),
        _w(82, 116, "of", 10, 0, 1),
        _w(98, 116, "sales", 10, 0, 2),
        _w(410, 116, "999,999", 11, 0),
        _w(500, 116, "888,888", 12, 0),
    ])
    return words


def _balance_doc(name="260032"):
    doc = _doc(name)
    doc["title"] = "MLCF Annual Report 2025 Consolidated Financial Statements"
    if name == "260032":
        doc["content_sha256"] = "4fdfb4cbd2eee65576cbb89b43334ce0c09a7e5ffd573d5bf93b414029eba6d1"
    return doc


def _balance_words(*, as_at="June 30, 2025", duplicate_year_band=False):
    words = [
        _w(50, 20, "Consolidated", 0, 0),
        _w(125, 20, "Statement", 0, 0, 1),
        _w(195, 20, "of", 0, 0, 2),
        _w(215, 20, "Financial", 0, 0, 3),
        _w(285, 20, "Position", 0, 0, 4),
        _w(50, 45, "AS", 1, 0),
        _w(70, 45, "AT", 1, 0, 1),
        _w(95, 45, "JUNE", 1, 0, 2),
        _w(140, 45, as_at.split()[-3].rstrip(","), 1, 0, 3),
        _w(175, 45, as_at.split()[-2], 1, 0, 4),
        _w(215, 45, as_at.split()[-1], 1, 0, 5),
        # The year labels are separate geometry lines, but share one baseline.
        _w(410, 70, "2025", 2, 0),
        _w(500, 70, "2024", 3, 0),
        _w(50, 85, "(Rupees", 4, 0),
        _w(92, 85, "in", 4, 0, 1),
        _w(108, 85, "thousand)", 4, 0, 2),
        _w(50, 110, "Total", 5, 0),
        _w(82, 110, "assets", 5, 0, 1),
        _w(410, 110, "123,456", 6, 0),
        _w(500, 110, "98,765", 7, 0),
    ]
    if duplicate_year_band:
        words.extend([_w(410, 160, "2025", 8, 0), _w(500, 160, "2024", 9, 0)])
        words.extend([_w(50, 205, "Total", 10, 0), _w(82, 205, "assets", 10, 0, 1),
                      _w(410, 205, "999,999", 11, 0), _w(500, 205, "888,888", 12, 0)])
    return words


def _balance_facts(words, *, as_at="June 30, 2025"):
    text = f"Consolidated statement of financial position AS AT {as_at}"
    doc = _balance_doc()
    return extract_facts(doc, [text], [words], [{"page": 291, "text": text, "words": words}])


def _continuation_page_one_words(*, heading="Financial Position", total=("118,731,599", "100,343,986")):
    words = [
        _w(50, 20, "Consolidated", 0, 0),
        _w(125, 20, "Statement", 0, 0, 1),
        _w(195, 20, "of", 0, 0, 2),
        _w(215, 20, heading.split()[0], 0, 0, 3),
        _w(285, 20, heading.split()[-1], 0, 0, 4),
        _w(50, 45, "AS", 1, 0),
        _w(70, 45, "AT", 1, 0, 1),
        _w(95, 45, "JUNE", 1, 0, 2),
        _w(140, 45, "30,", 1, 0, 3),
        _w(175, 45, "2025", 1, 0, 4),
        _w(410, 70, "2025", 2, 0),
        _w(500, 70, "2024", 3, 0),
        _w(340, 85, "Note", 4, 0),
        _w(400, 85, "(Rupees", 4, 1),
        _w(445, 85, "in", 4, 1, 1),
        _w(462, 85, "thousand)", 4, 1, 2),
        _w(50, 110, "EQUITY", 5, 0),
        _w(100, 110, "AND", 5, 0, 1),
        _w(130, 110, "LIABILITIES", 5, 0, 2),
        _w(50, 150, "Total", 6, 0),
        _w(82, 150, "equity", 6, 0, 1),
        _w(410, 150, "70,959,286", 7, 0),
        _w(500, 150, "57,643,643", 8, 0),
        _w(50, 200, "Long", 9, 0),
        _w(85, 200, "term", 9, 0, 1),
        _w(120, 200, "loans", 9, 0, 2),
        _w(155, 200, "from", 9, 0, 3),
        _w(190, 200, "financial", 9, 0, 4),
        _w(250, 200, "institutions", 9, 0, 5),
        _w(410, 200, "9,781,639", 10, 0),
        _w(500, 200, "9,785,786", 11, 0),
        _w(50, 520, "CURRENT", 12, 0),
        _w(115, 520, "LIABILITIES", 12, 0, 1),
        _w(50, 560, "Trade", 13, 0),
        _w(90, 560, "and", 13, 0, 1),
        _w(120, 560, "other", 13, 0, 2),
        _w(160, 560, "payables", 13, 0, 3),
        _w(410, 560, "17,698,228", 14, 0),
        _w(500, 560, "13,083,068", 15, 0),
        _w(50, 600, "Short", 16, 0),
        _w(90, 600, "term", 16, 0, 1),
        _w(125, 600, "borrowings", 16, 0, 2),
        _w(410, 600, "822,285", 17, 0),
        _w(500, 600, "1,645,316", 18, 0),
        _w(410, 660, total[0], 19, 0),
        _w(500, 660, total[1], 20, 0),
    ]
    return words


def _continuation_page_two_words(*, headers=("2025", "2024"), total=("118,731,599", "100,343,986"),
                                 duplicate_cash=False, statement_boundary=False):
    words = [
        _w(410, 70, headers[0], 1, 0),
        _w(500, 70, headers[1], 2, 0),
        _w(340, 85, "Note", 3, 0),
        _w(400, 85, "(Rupees", 3, 1),
        _w(445, 85, "in", 3, 1, 1),
        _w(462, 85, "thousand)", 3, 1, 2),
        _w(50, 110, "ASSETS", 4, 0),
        _w(50, 150, "NON", 5, 0),
        _w(80, 150, "-", 5, 0, 1),
        _w(95, 150, "CURRENT", 5, 0, 2),
        _w(160, 150, "ASSETS", 5, 0, 3),
        _w(50, 190, "Property,", 6, 0),
        _w(110, 190, "plant", 6, 0, 1),
        _w(155, 190, "and", 6, 0, 2),
        _w(185, 190, "equipment", 6, 0, 3),
        _w(410, 190, "72,403,474", 7, 0),
        _w(500, 190, "72,786,438", 8, 0),
        _w(50, 360, "CURRENT", 9, 0),
        _w(115, 360, "ASSETS", 9, 0, 1),
        _w(50, 400, "Stock-in-trade", 10, 0),
        _w(410, 400, "4,278,247", 11, 0),
        _w(500, 400, "3,176,688", 12, 0),
        _w(50, 420, "Trade", 13, 0),
        _w(90, 420, "debts", 13, 0, 1),
        _w(410, 420, "4,610,182", 14, 0),
        _w(500, 420, "4,188,745", 15, 0),
        _w(50, 500, "Cash", 16, 0),
        _w(90, 500, "and", 16, 0, 1),
        _w(120, 500, "bank", 16, 0, 2),
        _w(155, 500, "balances", 16, 0, 3),
        _w(410, 500, "1,861,551", 17, 0),
        _w(500, 500, "1,279,424", 18, 0),
        _w(410, 525, "36,654,982", 19, 0),
        _w(500, 525, "27,374,875", 20, 0),
        _w(410, 660, total[0], 21, 0),
        _w(500, 660, total[1], 22, 0),
    ]
    if duplicate_cash:
        words.extend([
            _w(50, 540, "Cash", 23, 0),
            _w(90, 540, "and", 23, 0, 1),
            _w(120, 540, "bank", 23, 0, 2),
            _w(155, 540, "balances", 23, 0, 3),
            _w(410, 540, "9,999", 24, 0),
            _w(500, 540, "8,888", 25, 0),
        ])
    if statement_boundary:
        words.extend([
            _w(50, 125, "Consolidated", 26, 0),
            _w(125, 125, "Statement", 26, 0, 1),
            _w(195, 125, "of", 26, 0, 2),
            _w(215, 125, "Cash", 26, 0, 3),
            _w(250, 125, "Flows", 26, 0, 4),
        ])
    return words


def _continuation_facts(*, doc=None, page_one=None, page_two=None, page_two_no=292):
    doc = doc or _balance_doc()
    text1 = "Consolidated statement of financial position AS AT JUNE 30, 2025"
    text2 = "Assets continuation"
    page_one = page_one or _continuation_page_one_words()
    page_two = page_two or _continuation_page_two_words()
    return extract_facts(
        doc,
        [text1, text2],
        [page_one, page_two],
        [
            {"page": 291, "text": text1, "words": page_one},
            {"page": page_two_no, "text": text2, "words": page_two},
        ],
    )


def _words_with_distant_row(*, duplicate_year_band=False):
    words = _words()
    if duplicate_year_band:
        words.extend([_w(410, 160, "2025", 10, 0), _w(500, 160, "2024", 10, 0, 1)])
    words.extend([
        _w(50, 250, "Operating", 12, 0), _w(110, 250, "profit", 12, 0, 1),
        _w(410, 250, "777,777", 13, 0), _w(500, 250, "666,666", 14, 0),
    ])
    return words


def _eps_words(*, duplicate_values=False):
    words = _words()
    # MLCF's annual EPS label wraps onto a second geometry line while the two
    # EPS cells are emitted as numeric-only lines that overlap that qualifier
    # band by a few points.  The parser may accept only the explicitly
    # qualified, uniquely aligned pair.
    words.extend([
        _w(50, 130, "Earnings", 20, 0),
        _w(105, 130, "per", 20, 0, 1),
        _w(125, 130, "share", 20, 0, 2),
        _w(50, 134, "basic", 21, 0),
        _w(80, 134, "and", 21, 0, 1),
        _w(100, 134, "diluted", 21, 0, 2),
        _w(410, 135, "10.98", 22, 0),
        _w(500, 135, "6.51", 23, 0),
    ])
    if duplicate_values:
        words.extend([
            _w(410, 138, "9.99", 24, 0),
            _w(500, 138, "5.55", 25, 0),
        ])
    return words


def main() -> int:
    positive = _facts(_words())
    assert [(f["line"], f["period_end"], f["raw_value"], f["consolidation"], f["readiness"])
            for f in positive] == [
                ("revenue", "2025-06-30", "123,456", "consolidated", "model_loadable"),
                ("revenue", "2024-06-30", "98,765", "consolidated", "model_loadable"),
            ]
    assert [f["value"] for f in positive] == [123_456_000.0, 98_765_000.0]

    assert _facts(_words(headers=("2025",))) == []
    assert _facts(_words(bands=(("123,456", "98,765"), ("222,222", "111,111")))) == []

    adjacent = _facts(_words_with_competing_adjacent_band())
    assert [(f["line"], f["raw_value"]) for f in adjacent] == [
        ("revenue", "123,456"), ("revenue", "98,765"),
    ]
    assert not any(f["raw_value"] in {"999,999", "888,888"} for f in adjacent)

    standalone = _facts(_words(basis="Standalone"))
    assert standalone and {f["consolidation"] for f in standalone} == {"unconsolidated"}
    assert not any(f["consolidation"] == "consolidated" for f in standalone)

    balance = _balance_facts(_balance_words())
    assert [(f["line"], f["period_end"], f["raw_value"], f["consolidation"], f["readiness"])
            for f in balance] == [
                ("total_assets", "2025-06-30", "123,456", "consolidated", "model_loadable"),
                ("total_assets", "2024-06-30", "98,765", "consolidated", "model_loadable"),
            ]
    assert _balance_facts(_balance_words(as_at="June 30, 2024")) == []
    ambiguous_balance = _balance_facts(_balance_words(duplicate_year_band=True))
    assert {(f["line"], f["raw_value"]) for f in ambiguous_balance} == {
        ("total_assets", "123,456"), ("total_assets", "98,765"),
    }
    assert not any(f["raw_value"] in {"999,999", "888,888"} for f in ambiguous_balance)

    continuation = _continuation_facts()
    continuation_pairs = {(f["page"], f["line"], f["period_end"], f["raw_value"], f["consolidation"], f["readiness"])
                          for f in continuation}
    assert (292, "property_plant_equipment", "2025-06-30", "72,403,474", "consolidated", "model_loadable") in continuation_pairs
    assert (292, "inventories", "2025-06-30", "4,278,247", "consolidated", "model_loadable") in continuation_pairs
    assert (292, "trade_receivables", "2025-06-30", "4,610,182", "consolidated", "model_loadable") in continuation_pairs
    assert (292, "cash_and_cash_equivalents", "2025-06-30", "1,861,551", "consolidated", "model_loadable") in continuation_pairs
    assert (292, "total_current_assets", "2025-06-30", "36,654,982", "consolidated", "model_loadable") in continuation_pairs
    assert (292, "total_assets", "2025-06-30", "118,731,599", "consolidated", "model_loadable") in continuation_pairs
    assert (291, "short_term_borrowings", "2025-06-30", "822,285", "consolidated", "model_loadable") in continuation_pairs
    assert (291, "trade_payables", "2025-06-30", "17,698,228", "consolidated", "model_loadable") in continuation_pairs
    assert not any(f["page"] == 292 and f["line"] == "cash_and_cash_equivalents" and f["raw_value"] == "36,654,982"
                   for f in continuation)

    bad_hash = _continuation_facts(doc={**_balance_doc(), "content_sha256": "wrong"})
    assert not any(f["page"] == 292 for f in bad_hash)
    wrong_prior = _continuation_facts(page_one=_continuation_page_one_words(heading="Profit Loss"))
    assert not any(f["page"] == 292 for f in wrong_prior)
    noncontiguous = _continuation_facts(page_two_no=293)
    assert not any(f["page"] == 293 for f in noncontiguous)
    period_mismatch = _continuation_facts(doc={**_balance_doc(), "period_end": "2024-06-30"})
    assert not any(f["page"] == 292 for f in period_mismatch)
    header_mismatch = _continuation_facts(page_two=_continuation_page_two_words(headers=("2025", "2023")))
    assert not any(f["page"] == 292 for f in header_mismatch)
    duplicate_label = _continuation_facts(page_two=_continuation_page_two_words(duplicate_cash=True))
    assert not any(f["page"] == 292 for f in duplicate_label)
    boundary = _continuation_facts(page_two=_continuation_page_two_words(statement_boundary=True))
    assert not any(f["page"] == 292 and f["statement_type"] == "balance_sheet" for f in boundary)

    distant = _facts(_words_with_distant_row())
    assert {(f["line"], f["raw_value"]) for f in distant} == {
        ("revenue", "123,456"), ("revenue", "98,765"),
        ("operating_profit", "777,777"), ("operating_profit", "666,666"),
    }
    competing = _facts(_words_with_distant_row(duplicate_year_band=True))
    assert {(f["line"], f["raw_value"]) for f in competing} == {
        ("revenue", "123,456"), ("revenue", "98,765"),
    }

    eps = _facts(_eps_words())
    assert [(f["line"], f["raw_value"], f["unit"]) for f in eps if f["line"] == "basic_eps"] == [
        ("basic_eps", "10.98", "PKR/share"),
        ("basic_eps", "6.51", "PKR/share"),
    ]
    duplicate_eps = _facts(_eps_words(duplicate_values=True))
    assert not any(f["line"] == "basic_eps" for f in duplicate_eps)

    print("MLCF FY25 parser geometry check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
