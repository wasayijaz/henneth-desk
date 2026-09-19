"""Derived depreciation & amortisation lane for MLCF psx:260032 note 43.1.

The filing reports depreciation and amortisation only as three separate note
rows; no combined statement line exists anywhere in the document.  This module
extracts those three reported operands with exact geometry and derives their
sum strictly for audit-receipt EBITDA lineage.  The sum is a derived value and
is never claimed to be reported; nothing here writes canonical facts.
"""
from __future__ import annotations

import re
from typing import Any

FORMULA_ID = "mlcf_derived_dna_sum_v1"
EBITDA_FORMULA_ID = "mlcf_derived_ebitda_v1"
NOTE_PAGE = 361
NOTE_HEADING_TOKEN = "43.1"
NOTE_HEADING_TEXT = "CASH FLOW INFORMATION"
UNIT_EVIDENCE = "Rupees in thousand"
SCALE = 1000
UNIT = "PKR"
CURRENT_PERIOD_END = "2025-06-30"
COMPARATIVE_PERIOD_END = "2024-06-30"
YEAR_HEADERS = ("2025", "2024")

# (operand key, row-label regex, expected note reference)
OPERANDS: tuple[tuple[str, str, str], ...] = (
    ("depreciation_operating_fixed_assets", r"depreciation\s+on\s+operating\s+fixed\s+assets", "19.1.1"),
    ("depreciation_right_of_use", r"depreciation\s+on\s+right[- ]of[- ]use\s+asset", "19.4.1"),
    ("amortisation_intangible_assets", r"amorti[sz]ation\s+on\s+intangible\s+assets", "20.1"),
)


class DerivedDnaError(ValueError):
    """Raised when the note-43.1 operand geometry fails strict validation."""


def _rows_from_words(words: list[tuple]) -> list[tuple[float, list[tuple[float, str]]]]:
    by_y: dict[float, list[tuple[float, str]]] = {}
    for word in words:
        x0, y0, _x1, _y1, text = word[0], word[1], word[2], word[3], word[4]
        by_y.setdefault(round(float(y0), 1), []).append((float(x0), str(text)))
    return [(y, sorted(tokens)) for y, tokens in sorted(by_y.items())]


def _is_number(token: str) -> bool:
    return bool(re.fullmatch(r"\(?\d[\d,]*\)?", token))


def _parse_number(token: str) -> float:
    negative = token.startswith("(") and token.endswith(")")
    digits = token.strip("()").replace(",", "")
    value = float(digits)
    return -value if negative else value


def extract_operands(words: list[tuple], page_text: str) -> dict[str, Any]:
    """Validate note 43.1 geometry and return per-period operand lineage.

    Fails closed (DerivedDnaError) on: wrong page (no note heading), missing
    unit evidence, missing year header, missing operand row, ambiguous
    duplicate rows, missing note reference, wrong value-cell count, or a
    non-positive operand value.
    """
    text = " ".join((page_text or "").split())
    if NOTE_HEADING_TEXT not in text.upper().replace("  ", " "):
        raise DerivedDnaError("note_heading_missing")
    if UNIT_EVIDENCE not in text:
        raise DerivedDnaError("unit_evidence_missing")
    flat_tokens = [token for _y, tokens in _rows_from_words(words) for _x, token in tokens]
    for year in YEAR_HEADERS:
        if year not in flat_tokens:
            raise DerivedDnaError(f"year_header_missing:{year}")

    rows = _rows_from_words(words)
    periods = {
        CURRENT_PERIOD_END: {"column_role": "current_period", "operands": []},
        COMPARATIVE_PERIOD_END: {"column_role": "comparative_prior_period", "operands": []},
    }
    for key, label_pattern, note_ref in OPERANDS:
        matches = [
            (y, tokens) for y, tokens in rows
            if re.search(label_pattern, " ".join(token for _x, token in tokens), re.I)
        ]
        if not matches:
            raise DerivedDnaError(f"operand_row_missing:{key}")
        if len(matches) > 1:
            raise DerivedDnaError(f"ambiguous_operand_rows:{key}")
        y, tokens = matches[0]
        refs = [x for x, token in tokens if token == note_ref]
        if not refs:
            raise DerivedDnaError(f"note_reference_missing:{key}")
        ref_x = refs[0]
        value_cells = [(x, token) for x, token in tokens if x > ref_x and _is_number(token)]
        if len(value_cells) != 2:
            raise DerivedDnaError(f"operand_value_cell_count:{key}:{len(value_cells)}")
        (x_current, raw_current), (x_comparative, raw_comparative) = sorted(value_cells)
        value_current = _parse_number(raw_current)
        value_comparative = _parse_number(raw_comparative)
        if value_current <= 0 or value_comparative <= 0:
            raise DerivedDnaError(f"operand_value_invalid:{key}")
        base = {
            "operand_key": key,
            "reported_label": " ".join(token for _x, token in tokens if not _is_number(token)),
            "note_reference": note_ref,
            "unit": UNIT,
            "scale": SCALE,
            "page": NOTE_PAGE,
            "row_y": y,
        }
        periods[CURRENT_PERIOD_END]["operands"].append({
            **base,
            "period_end": CURRENT_PERIOD_END,
            "column_role": "current_period",
            "raw_value": raw_current,
            "normalized_value": value_current * SCALE,
            "value_x": x_current,
        })
        periods[COMPARATIVE_PERIOD_END]["operands"].append({
            **base,
            "period_end": COMPARATIVE_PERIOD_END,
            "column_role": "comparative_prior_period",
            "raw_value": raw_comparative,
            "normalized_value": value_comparative * SCALE,
            "value_x": x_comparative,
        })
    return periods


def derive_dna(periods: dict[str, Any]) -> dict[str, Any]:
    """Sum the three reported operands per period. The sum is derived, not reported."""
    derived_periods = {}
    for period_end, node in periods.items():
        operands = sorted(node["operands"], key=lambda row: row["operand_key"])
        if len(operands) != len(OPERANDS):
            raise DerivedDnaError(f"operand_count_invalid:{period_end}:{len(operands)}")
        total = sum(row["normalized_value"] for row in operands)
        derived_periods[period_end] = {
            "column_role": node["column_role"],
            "operands": operands,
            "operand_count": len(operands),
            "sum_normalized_value": total,
            "sum_raw_value_thousand": f"{int(total / SCALE):,}",
        }
    return {
        "formula": {
            "id": FORMULA_ID,
            "expression": " + ".join(key for key, _pattern, _ref in OPERANDS),
            "semantics": "sum_of_three_reported_note_rows",
            "reported_as_single_line": False,
        },
        "periods": derived_periods,
    }


def derive_ebitda(operating_profit_normalized: float, dna_normalized: float) -> float:
    """Derived EBITDA lineage only: operating profit plus the derived D&A sum."""
    return float(operating_profit_normalized) + float(dna_normalized)


def read_note_page(raw: bytes) -> tuple[str, list[tuple]]:
    """Read the note-43.1 page text and word geometry from verified PDF bytes."""
    import pymupdf

    pdf = pymupdf.open(stream=raw, filetype="pdf")
    try:
        if NOTE_PAGE > len(pdf):
            raise DerivedDnaError("note_page_out_of_range")
        page = pdf[NOTE_PAGE - 1]
        return page.get_text("text") or "", list(page.get_text("words") or [])
    finally:
        pdf.close()


def build_receipt_block(
    document_id: str,
    content_sha256: str,
    note_words: list[tuple],
    note_text: str,
    primary_period_end: str,
    operating_profit_normalized: float,
    operating_profit_page: int,
) -> dict[str, Any]:
    """Build the audit-only derived D&A / derived EBITDA lineage block."""
    periods = extract_operands(note_words, note_text)
    dna = derive_dna(periods)
    primary = dna["periods"][primary_period_end]
    ebitda_value = derive_ebitda(operating_profit_normalized, primary["sum_normalized_value"])
    return {
        "depreciation_amortization": {
            "reported": False,
            "formula": dna["formula"],
            "source": {
                "document_id": document_id,
                "content_sha256": content_sha256,
                "page": NOTE_PAGE,
                "note": NOTE_HEADING_TOKEN,
                "note_heading": NOTE_HEADING_TEXT,
                "unit": UNIT,
                "scale": SCALE,
                "unit_evidence": UNIT_EVIDENCE,
            },
            "periods": dna["periods"],
        },
        "ebitda": {
            "reported": False,
            "formula": {
                "id": EBITDA_FORMULA_ID,
                "expression": "operating_profit + derived_depreciation_amortization",
            },
            "periods": {
                primary_period_end: {
                    "operating_profit_normalized_value": float(operating_profit_normalized),
                    "operating_profit_page": operating_profit_page,
                    "derived_depreciation_amortization_normalized_value": primary["sum_normalized_value"],
                    "normalized_value": ebitda_value,
                },
            },
        },
        "policy": {
            "derived_only_not_reported": True,
            "canonical_promotion": "blocked",
            "financial_truth_gate_effect": "none",
        },
    }
