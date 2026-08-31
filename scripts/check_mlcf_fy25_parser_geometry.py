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

    standalone = _facts(_words(basis="Standalone"))
    assert standalone and {f["consolidation"] for f in standalone} == {"unconsolidated"}
    assert not any(f["consolidation"] == "consolidated" for f in standalone)

    print("MLCF FY25 parser geometry check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
