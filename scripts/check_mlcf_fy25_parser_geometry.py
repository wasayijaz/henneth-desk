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


def _words_with_distant_row(*, duplicate_year_band=False):
    words = _words()
    if duplicate_year_band:
        words.extend([_w(410, 160, "2025", 10, 0), _w(500, 160, "2024", 10, 0, 1)])
    words.extend([
        _w(50, 250, "Operating", 12, 0), _w(110, 250, "profit", 12, 0, 1),
        _w(410, 250, "777,777", 13, 0), _w(500, 250, "666,666", 14, 0),
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

    distant = _facts(_words_with_distant_row())
    assert {(f["line"], f["raw_value"]) for f in distant} == {
        ("revenue", "123,456"), ("revenue", "98,765"),
        ("operating_profit", "777,777"), ("operating_profit", "666,666"),
    }
    competing = _facts(_words_with_distant_row(duplicate_year_band=True))
    assert {(f["line"], f["raw_value"]) for f in competing} == {
        ("revenue", "123,456"), ("revenue", "98,765"),
    }

    print("MLCF FY25 parser geometry check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
