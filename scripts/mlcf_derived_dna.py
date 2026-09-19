"""Strict, audit-only derived financial facts for MLCF ``psx:260032``.

This is deliberately a bounded lane, not a universal formula engine.  The
retained annual report exposes the three depreciation/amortisation operands in
note 43.1 but does not report a single D&A or EBITDA line.  We therefore keep
the inputs as reported-note evidence and expose only deterministic derived
facts with explicit epistemic type, formula version and source geometry.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

DERIVED_LINEAGE_VERSION = "mlcf_derived_lineage_v2"
DERIVED_SCHEMA_VERSION = 2
FORMULA_ID = "mlcf_derived_dna_sum_v2"
EBITDA_FORMULA_ID = "mlcf_derived_ebitda_v2"
PBT_BASIS_FORMULA_ID = "mlcf_pbt_basis_discrepancy_v1"
NOTE_PAGE = 361
NOTE_HEADING_TOKEN = "43.1"
NOTE_HEADING_TEXT = "CASH FLOW INFORMATION"
UNIT_EVIDENCE = "Rupees in thousand"
SCALE = 1000
UNIT = "PKR"
CURRENT_PERIOD_END = "2025-06-30"
COMPARATIVE_PERIOD_END = "2024-06-30"
YEAR_HEADERS = ("2025", "2024")
SOURCE_PAGE_SCOPE = (291, 292, 293, 295, NOTE_PAGE)
STATEMENT_PAGE_SCOPE = (291, 292, 293, 295)
HEADER_TOLERANCE = 24.0
EXPECTED_DOCUMENT_ID = "psx:260032"
EXPECTED_SOURCE_URL = "https://dps.psx.com.pk/download/document/260032.pdf"
EXPECTED_CONTENT_SHA256 = "4fdfb4cbd2eee65576cbb89b43334ce0c09a7e5ffd573d5bf93b414029eba6d1"

# These commitments are the sealed parser output used by the retained receipt.
# Keeping them here makes validation deterministic in clean CI, where the
# ignored source PDF is intentionally unavailable.  A changed value, period,
# metric, identity, source binding, or geometry therefore cannot be promoted by
# merely changing the receipt and recomputing the result.
EXPECTED_DERIVED_FACTS = {
    ("depreciation_amortization", "2025-06-30"): "derived_4e2292e0574bb4b8ba93291f",
    ("ebitda", "2025-06-30"): "derived_dc4ea4a1c449a2c7ef4ba809",
    ("depreciation_amortization", "2024-06-30"): "derived_85d5ff640065d1d7002ae5ee",
    ("ebitda", "2024-06-30"): "derived_2b7c0d6ef9cea45e537740f1",
}

EXPECTED_INPUT_COMMITMENTS = {
    "reported_note:psx:260032:2025-06-30:amortisation_intangible_assets:20.1": "afa1a7450686cdc78730292df864409f5992ee725538a3468d364a2192c207d3",
    "reported_note:psx:260032:2025-06-30:depreciation_operating_fixed_assets:19.1.1": "ab8f3dfa7e9506dbf8a90da459af639eb86e5f50a006b358ca8b12605a1ff215",
    "reported_note:psx:260032:2025-06-30:depreciation_right_of_use:19.4.1": "06738c6f81773b6a2ac4d84771b179c16de91b2b8679cbd506deaf5203eb7ba9",
    "fact_341ff235d9fa10701669239a": "c6bb056e11552ba9fc3102fa4058d5169d972b5a4c56e8a91c1a3e521fba13d3",
    "reported_note:psx:260032:2024-06-30:amortisation_intangible_assets:20.1": "3b2d66e2a10c63887b4d12c8833c1321eb6144a10212d2eb539c60d1972fd465",
    "reported_note:psx:260032:2024-06-30:depreciation_operating_fixed_assets:19.1.1": "c4c3c8cafe4fe3231b96381c89877d5d5594840b6222985cbe5bd4e7e3f51777",
    "reported_note:psx:260032:2024-06-30:depreciation_right_of_use:19.4.1": "c5a265dcaad5ff566080b3b007c32259e1a166bcc237e3f5c07c20534e927572",
    "fact_9758bc41bc81a3c081f5d9be": "110ad3d9b010162327d15ac0edded5913d683816d7f6a8ce03026530a2f35eed",
}

# (operand key, row-label regex, expected note reference)
OPERANDS: tuple[tuple[str, str, str], ...] = (
    ("depreciation_operating_fixed_assets", r"depreciation\s+on\s+operating\s+fixed\s+assets", "19.1.1"),
    ("depreciation_right_of_use", r"depreciation\s+on\s+right[- ]of[- ]use\s+asset", "19.4.1"),
    ("amortisation_intangible_assets", r"amorti[sz]ation\s+on\s+intangible\s+assets", "20.1"),
)


class DerivedDnaError(ValueError):
    """Raised when retained note geometry or a derived fact is not provable."""


def _rows_from_words(words: list[tuple]) -> list[tuple[float, list[tuple[float, float, str]]]]:
    by_y: dict[float, list[tuple[float, float, str]]] = {}
    for word in words:
        if len(word) < 5:
            continue
        x0, y0, x1, _y1, text = word[0], word[1], word[2], word[3], word[4]
        by_y.setdefault(round(float(y0), 1), []).append((float(x0), float(x1), str(text)))
    return [(y, sorted(tokens)) for y, tokens in sorted(by_y.items())]


def _normal(text: str) -> str:
    return " ".join(str(text or "").split())


def _is_number(token: str) -> bool:
    return bool(re.fullmatch(r"\(?\d[\d,]*\)?", token))


def _parse_number(token: str) -> float:
    negative = token.startswith("(") and token.endswith(")")
    digits = token.strip("()").replace(",", "")
    value = float(digits)
    return -value if negative else value


def validate_source_page_scope(page_scope: list[int] | tuple[int, ...]) -> tuple[int, ...]:
    """Require the exact statement-plus-note page scope for this lane."""
    normalized = tuple(int(page) for page in page_scope)
    if normalized != SOURCE_PAGE_SCOPE:
        raise DerivedDnaError(f"source_page_scope_mismatch:{list(normalized)}")
    return normalized


def _note_header_columns(rows: list[tuple[float, list[tuple[float, float, str]]]]) -> dict[str, dict[str, float]]:
    note_rows = [
        (y, tokens) for y, tokens in rows
        if any(token == NOTE_HEADING_TOKEN for _x0, _x1, token in tokens)
    ]
    if len(note_rows) != 1:
        raise DerivedDnaError("note_token_missing" if not note_rows else "ambiguous_note_token")
    note_y = note_rows[0][0]
    all_tokens = {token for _y, tokens in rows for _x0, _x1, token in tokens}
    for year in YEAR_HEADERS:
        if year not in all_tokens:
            raise DerivedDnaError(f"year_header_missing:{year}")
    header_candidates: list[tuple[float, list[tuple[float, float, str]]]] = []
    for y, tokens in rows:
        if y >= note_y:
            continue
        years = {token for _x0, _x1, token in tokens if token in YEAR_HEADERS}
        if years == set(YEAR_HEADERS):
            header_candidates.append((y, tokens))
    if not header_candidates:
        for year in YEAR_HEADERS:
            raise DerivedDnaError(f"year_header_missing:{year}")
    _header_y, tokens = max(header_candidates, key=lambda item: item[0])
    columns: dict[str, dict[str, float]] = {}
    for year in YEAR_HEADERS:
        matches = [(x0, x1) for x0, x1, token in tokens if token == year]
        if not matches:
            raise DerivedDnaError(f"year_header_missing:{year}")
        if len(matches) != 1:
            raise DerivedDnaError(f"ambiguous_year_header:{year}")
        x0, x1 = matches[0]
        columns[year] = {"x0": x0, "x1": x1, "center_x": (x0 + x1) / 2.0, "row_y": _header_y}
    if columns["2025"]["center_x"] >= columns["2024"]["center_x"]:
        raise DerivedDnaError("year_header_order_invalid")
    return columns


def _bind_value_columns(
    value_cells: list[tuple[float, float, str]],
    columns: dict[str, dict[str, float]],
    key: str,
) -> dict[str, tuple[float, float, str]]:
    if len(value_cells) != 2:
        raise DerivedDnaError(f"operand_value_cell_count:{key}:{len(value_cells)}")
    bound: dict[str, tuple[float, float, str]] = {}
    for cell in value_cells:
        x0, x1, token = cell
        center = (x0 + x1) / 2.0
        distances = sorted((abs(center - info["center_x"]), year) for year, info in columns.items())
        distance, year = distances[0]
        if distance > HEADER_TOLERANCE or (len(distances) > 1 and distance == distances[1][0]):
            raise DerivedDnaError(f"value_column_geometry_mismatch:{key}")
        if year in bound:
            raise DerivedDnaError(f"duplicate_value_column:{key}:{year}")
        bound[year] = cell
    if set(bound) != set(YEAR_HEADERS):
        raise DerivedDnaError(f"value_column_binding_incomplete:{key}")
    return bound


def _row_geometry(tokens: list[tuple[float, float, str]], value_cells: list[tuple[float, float, str]]) -> dict[str, Any]:
    x0 = min(token[0] for token in tokens)
    x1 = max(token[1] for token in tokens)
    return {"x0": x0, "x1": x1, "token_count": len(tokens), "value_cell_count": len(value_cells)}


def extract_operands(words: list[tuple], page_text: str) -> dict[str, Any]:
    """Validate note 43.1 and return geometry-bound operand lineage."""
    text = _normal(page_text)
    if NOTE_HEADING_TEXT not in text.upper():
        raise DerivedDnaError("note_heading_missing")
    if UNIT_EVIDENCE.lower() not in text.lower():
        raise DerivedDnaError("unit_evidence_missing")
    rows = _rows_from_words(words)
    columns = _note_header_columns(rows)
    periods = {
        CURRENT_PERIOD_END: {"column_role": "current_period", "operands": [], "header": columns["2025"]},
        COMPARATIVE_PERIOD_END: {"column_role": "comparative_prior_period", "operands": [], "header": columns["2024"]},
    }
    for key, label_pattern, note_ref in OPERANDS:
        matches = [
            (y, tokens) for y, tokens in rows
            if re.search(label_pattern, " ".join(token for _x0, _x1, token in tokens), re.I)
        ]
        if not matches:
            raise DerivedDnaError(f"operand_row_missing:{key}")
        if len(matches) > 1:
            raise DerivedDnaError(f"ambiguous_operand_rows:{key}")
        row_y, tokens = matches[0]
        refs = [(x0, x1) for x0, x1, token in tokens if token == note_ref]
        if len(refs) != 1:
            raise DerivedDnaError(f"note_reference_{'missing' if not refs else 'ambiguous'}:{key}")
        ref_x = refs[0][0]
        value_cells = [(x0, x1, token) for x0, x1, token in tokens if x0 > ref_x and _is_number(token)]
        bound = _bind_value_columns(value_cells, columns, key)
        # The reported label stops before the note reference.  It must never
        # contain the note number, which is a separate provenance field.
        label_tokens = [token for x0, _x1, token in tokens if x0 < ref_x and token != "-"]
        reported_label = _normal(" ".join(label_tokens))
        if not reported_label:
            raise DerivedDnaError(f"reported_label_missing:{key}")
        base = {
            "operand_key": key,
            "reported_label": reported_label,
            "note_reference": note_ref,
            "epistemic_type": "reported_fact",
            "unit": UNIT,
            "scale": SCALE,
            "page": NOTE_PAGE,
            "row_y": row_y,
            "row_geometry": _row_geometry(tokens, value_cells),
            "header_geometry": {year: dict(columns[year]) for year in YEAR_HEADERS},
        }
        for year, period_end in (("2025", CURRENT_PERIOD_END), ("2024", COMPARATIVE_PERIOD_END)):
            x0, x1, raw_value = bound[year]
            value = _parse_number(raw_value)
            if value <= 0:
                raise DerivedDnaError(f"operand_value_invalid:{key}")
            periods[period_end]["operands"].append({
                **base,
                "period_end": period_end,
                "column_role": periods[period_end]["column_role"],
                "raw_value": raw_value,
                "normalized_value": value * SCALE,
                "value_x": x0,
                "value_geometry": {"x0": x0, "x1": x1, "center_x": (x0 + x1) / 2.0, "row_y": row_y},
            })
    return periods


def derive_dna(periods: dict[str, Any]) -> dict[str, Any]:
    """Sum the three reported operands; the sum is never labelled reported."""
    derived_periods = {}
    for period_end, node in periods.items():
        operands = sorted(node["operands"], key=lambda row: row["operand_key"])
        if len(operands) != len(OPERANDS):
            raise DerivedDnaError(f"operand_count_invalid:{period_end}:{len(operands)}")
        total = sum(row["normalized_value"] for row in operands)
        derived_periods[period_end] = {
            "column_role": node["column_role"],
            "header_geometry": node["header"],
            "operands": operands,
            "operand_count": len(operands),
            "sum_normalized_value": total,
            "sum_raw_value_thousand": f"{int(total / SCALE):,}",
        }
    return {
        "formula": {
            "id": FORMULA_ID,
            "calculation_version": DERIVED_LINEAGE_VERSION,
            "expression": " + ".join(key for key, _pattern, _ref in OPERANDS),
            "semantics": "sum_of_three_reported_note_rows",
            "reported_as_single_line": False,
            "rou_included": True,
            "rou_definition": "depreciation on right-of-use asset is an explicit operand; no separate ROU adjustment is applied",
        },
        "periods": derived_periods,
    }


def derive_ebitda(operating_profit_normalized: float, dna_normalized: float) -> float:
    """Derived EBITDA lineage only: operating profit plus derived D&A."""
    if not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in (operating_profit_normalized, dna_normalized)):
        raise DerivedDnaError("ebitda_operand_not_numeric")
    return float(operating_profit_normalized) + float(dna_normalized)


def _stable_fact_id(document_id: str, metric: str, period_end: str, formula_id: str) -> str:
    digest = hashlib.sha256("\x1f".join((document_id, metric, period_end, formula_id)).encode()).hexdigest()[:24]
    return f"derived_{digest}"


def _source_binding(document_id: str, content_sha256: str, page: int, source_url: str = EXPECTED_SOURCE_URL) -> dict[str, Any]:
    return {"document_id": document_id, "source_url": source_url, "content_sha256": content_sha256, "page": page}


def _commitment(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _validate_sealed_input(input_fact: dict[str, Any], receipt_source: dict[str, Any]) -> None:
    fact_id = input_fact.get("fact_id") if isinstance(input_fact, dict) else None
    expected = EXPECTED_INPUT_COMMITMENTS.get(fact_id)
    if expected is None or _commitment(input_fact) != expected:
        raise DerivedDnaError("derived_fact_input_commitment_invalid")
    if input_fact.get("source") != _source_binding(EXPECTED_DOCUMENT_ID, EXPECTED_CONTENT_SHA256, input_fact["source"]["page"]):
        raise DerivedDnaError("derived_fact_input_source_invalid")
    if input_fact["source"]["document_id"] != receipt_source["document_id"] or input_fact["source"]["content_sha256"] != receipt_source["content_sha256"]:
        raise DerivedDnaError("derived_fact_input_receipt_source_mismatch")


def _note_input(row: dict[str, Any], document_id: str, content_sha256: str) -> dict[str, Any]:
    return {
        "fact_id": f"reported_note:{document_id}:{row['period_end']}:{row['operand_key']}:{row['note_reference']}",
        "epistemic_type": "reported_fact",
        "metric": row["operand_key"],
        "period_end": row["period_end"],
        "normalized_value": row["normalized_value"],
        "raw_value": row["raw_value"],
        "reported_label": row["reported_label"],
        "note_reference": row["note_reference"],
        "source": _source_binding(document_id, content_sha256, NOTE_PAGE),
        "geometry": {"row_y": row["row_y"], "row": row["row_geometry"], "value": row["value_geometry"], "headers": row["header_geometry"]},
    }


def _parser_input(fact: dict[str, Any], page_words: list[tuple] | None) -> dict[str, Any]:
    if not isinstance(fact, dict) or not fact.get("fact_id") or fact.get("epistemic_type", "reported_fact") != "reported_fact":
        raise DerivedDnaError("input_fact_missing_or_not_reported")
    page = fact.get("page")
    if not isinstance(page, int) or page < 1 or not fact.get("content_sha256") or not fact.get("source_url"):
        raise DerivedDnaError("input_fact_source_binding_missing")
    geometry: dict[str, Any] = {"page": page, "reported_label": fact.get("reported_label")}
    if isinstance(fact.get("statement_heading"), dict):
        geometry["statement_heading"] = fact["statement_heading"]
    if page_words:
        rows = _rows_from_words(page_words)
        label = _normal(str(fact.get("reported_label") or "")).lower()
        matches = [(y, tokens) for y, tokens in rows if label and label in _normal(" ".join(token for _x0, _x1, token in tokens)).lower()]
        if matches:
            row_y, tokens = matches[0]
            numerics = [(x0, x1, token) for x0, x1, token in tokens if _is_number(token)]
            geometry.update({"row_y": row_y, "row_geometry": _row_geometry(tokens, numerics)})
    if "row_y" not in geometry:
        raise DerivedDnaError("input_fact_geometry_missing")
    return {
        "fact_id": fact["fact_id"],
        "epistemic_type": "reported_fact",
        "metric": fact.get("line") or fact.get("canonical_line") or fact.get("metric"),
        "period_end": fact.get("period_end"),
        "normalized_value": fact.get("normalized_value"),
        "raw_value": fact.get("raw_value"),
        "source": _source_binding(fact.get("document_id") or EXPECTED_DOCUMENT_ID, fact["content_sha256"], page, fact["source_url"]),
        "geometry": geometry,
    }


def _pbt_note_row(words: list[tuple], page_text: str) -> dict[str, Any]:
    text = _normal(page_text)
    if NOTE_HEADING_TEXT not in text.upper() or UNIT_EVIDENCE.lower() not in text.lower():
        raise DerivedDnaError("pbt_note_scope_missing")
    rows = _rows_from_words(words)
    columns = _note_header_columns(rows)
    matches = [(y, tokens) for y, tokens in rows if re.search(r"profit\s+before\s+final\s+taxes\s+and\s+income\s+tax", " ".join(token for _x0, _x1, token in tokens), re.I)]
    if len(matches) != 1:
        raise DerivedDnaError("pbt_note_row_missing_or_ambiguous")
    row_y, tokens = matches[0]
    label_end = max(x1 for _x0, x1, token in tokens if token.lower() == "tax")
    value_cells = [(x0, x1, token) for x0, x1, token in tokens if x0 > label_end and _is_number(token)]
    bound = _bind_value_columns(value_cells, columns, "pbt_basis")
    values = {}
    for year, period_end in (("2025", CURRENT_PERIOD_END), ("2024", COMPARATIVE_PERIOD_END)):
        x0, x1, raw = bound[year]
        values[period_end] = {
            "epistemic_type": "reported_fact",
            "reported_label": "Profit before final taxes and income tax",
            "period_end": period_end,
            "raw_value": raw,
            "normalized_value": _parse_number(raw) * SCALE,
            "source": _source_binding(EXPECTED_DOCUMENT_ID, EXPECTED_CONTENT_SHA256, NOTE_PAGE),
            "geometry": {"row_y": row_y, "value": {"x0": x0, "x1": x1, "center_x": (x0 + x1) / 2.0, "row_y": row_y}, "headers": columns},
        }
    return values


def _pbt_discrepancy(
    note_values: dict[str, Any],
    pbt_facts: dict[str, dict[str, Any]],
    document_id: str,
    content_sha256: str,
    page_words: dict[int, list[tuple]] | None,
) -> dict[str, Any]:
    periods: dict[str, Any] = {}
    for period_end, note in note_values.items():
        statement = pbt_facts.get(period_end)
        if not isinstance(statement, dict):
            raise DerivedDnaError(f"pbt_input_fact_missing:{period_end}")
        statement_input = _parser_input(statement, (page_words or {}).get(int(statement.get("page") or 0)))
        difference = float(note["normalized_value"]) - float(statement_input["normalized_value"])
        periods[period_end] = {
            "epistemic_type": "derived_fact",
            "normalized_value": difference,
            "reported_label": "PBT basis discrepancy",
            "status": "basis_discrepancy_retained" if difference else "basis_matches",
            "formula": {"id": PBT_BASIS_FORMULA_ID, "calculation_version": DERIVED_LINEAGE_VERSION, "expression": "cash_flow_note_pbt - income_statement_pbt"},
            "inputs": [statement_input, note],
            "source": _source_binding(document_id, content_sha256, NOTE_PAGE),
        }
    return {"formula": {"id": PBT_BASIS_FORMULA_ID, "calculation_version": DERIVED_LINEAGE_VERSION, "expression": "cash_flow_note_pbt - income_statement_pbt"}, "periods": periods}


def build_receipt_block(
    document_id: str,
    content_sha256: str,
    note_words: list[tuple],
    note_text: str,
    primary_period_end: str,
    operating_profit_facts: dict[str, dict[str, Any]],
    operating_profit_page: int | None = None,
    *,
    pbt_facts: dict[str, dict[str, Any]] | None = None,
    statement_page_words: dict[int, list[tuple]] | None = None,
) -> dict[str, Any]:
    """Build the audit-only derived fact block and strict source lineage."""
    if document_id != EXPECTED_DOCUMENT_ID or content_sha256 != EXPECTED_CONTENT_SHA256:
        raise DerivedDnaError("derived_source_identity_mismatch")
    periods = extract_operands(note_words, note_text)
    dna = derive_dna(periods)
    if not isinstance(operating_profit_facts, dict) or any(not isinstance(value, dict) for value in operating_profit_facts.values()):
        raise DerivedDnaError("operating_profit_input_fact_missing")
    derived_facts: list[dict[str, Any]] = []
    ebitda_periods: dict[str, Any] = {}
    for period_end, node in dna["periods"].items():
        operands = [_note_input(row, document_id, content_sha256) for row in node["operands"]]
        dna_id = _stable_fact_id(document_id, "depreciation_amortization", period_end, FORMULA_ID)
        dna_fact = {
            "fact_id": dna_id, "symbol": "MLCF", "metric": "depreciation_amortization", "line": "depreciation_amortization",
            "period_end": period_end, "period_type": "annual", "duration_months": 12, "statement_type": "cash_flow_statement",
            "consolidation": "consolidated", "currency": UNIT, "unit": UNIT, "unit_multiplier": 1,
            "normalized_value": node["sum_normalized_value"], "epistemic_type": "derived_fact", "reported": False,
            "source_method": "deterministic_derived", "readiness": "model_loadable", "formula": dna["formula"],
            "calculation_version": DERIVED_LINEAGE_VERSION, "lineage": {"inputs": operands, "source_scope": list(SOURCE_PAGE_SCOPE)},
            "source": _source_binding(document_id, content_sha256, NOTE_PAGE),
            "evidence": [{"page": NOTE_PAGE, "source_url": EXPECTED_SOURCE_URL, "text": NOTE_HEADING_TOKEN}],
        }
        derived_facts.append(dna_fact)
        op_fact = operating_profit_facts.get(period_end)
        if not isinstance(op_fact, dict):
            raise DerivedDnaError(f"operating_profit_input_fact_missing:{period_end}")
        op_input = _parser_input(op_fact, (statement_page_words or {}).get(int(op_fact.get("page") or 0)))
        ebitda_value = derive_ebitda(float(op_input["normalized_value"]), float(dna_fact["normalized_value"]))
        ebitda_id = _stable_fact_id(document_id, "ebitda", period_end, EBITDA_FORMULA_ID)
        ebitda_formula = {"id": EBITDA_FORMULA_ID, "calculation_version": DERIVED_LINEAGE_VERSION, "expression": "operating_profit + derived_depreciation_amortization", "rou_included": True, "rou_definition": "derived D&A includes depreciation on right-of-use asset exactly once"}
        ebitda_fact = {
            "fact_id": ebitda_id, "symbol": "MLCF", "metric": "ebitda", "line": "ebitda", "period_end": period_end,
            "period_type": "annual", "duration_months": 12, "statement_type": "income_statement", "consolidation": "consolidated",
            "currency": UNIT, "unit": UNIT, "unit_multiplier": 1, "normalized_value": ebitda_value,
            "epistemic_type": "derived_fact", "reported": False, "source_method": "deterministic_derived", "readiness": "model_loadable",
            "formula": ebitda_formula, "calculation_version": DERIVED_LINEAGE_VERSION,
            "lineage": {"inputs": [op_input, dna_fact], "source_scope": list(SOURCE_PAGE_SCOPE)},
            "source": _source_binding(document_id, content_sha256, NOTE_PAGE),
            "evidence": [{"page": NOTE_PAGE, "source_url": EXPECTED_SOURCE_URL, "text": NOTE_HEADING_TOKEN}],
        }
        derived_facts.append(ebitda_fact)
        ebitda_periods[period_end] = {
            "operating_profit_normalized_value": op_input["normalized_value"], "operating_profit_page": op_fact.get("page"),
            "operating_profit_fact_id": op_fact.get("fact_id"), "derived_depreciation_amortization_normalized_value": dna_fact["normalized_value"],
            "derived_depreciation_amortization_fact_id": dna_id, "normalized_value": ebitda_value,
            "epistemic_type": "derived_fact", "formula": ebitda_formula,
        }
    pbt_basis = _pbt_discrepancy(_pbt_note_row(note_words, note_text), pbt_facts or {}, document_id, content_sha256, statement_page_words)
    return {
        "schema_version": DERIVED_SCHEMA_VERSION, "derived_lineage_version": DERIVED_LINEAGE_VERSION,
        "depreciation_amortization": {
            "reported": False, "epistemic_type": "derived_fact", "formula": dna["formula"],
            "source": {**_source_binding(document_id, content_sha256, NOTE_PAGE), "note": NOTE_HEADING_TOKEN, "note_heading": NOTE_HEADING_TEXT, "unit": UNIT, "scale": SCALE, "unit_evidence": UNIT_EVIDENCE, "page_scope": list(SOURCE_PAGE_SCOPE)},
            "periods": dna["periods"],
        },
        "ebitda": {
            "reported": False, "epistemic_type": "derived_fact", "formula": {"id": EBITDA_FORMULA_ID, "calculation_version": DERIVED_LINEAGE_VERSION, "expression": "operating_profit + derived_depreciation_amortization", "rou_included": True, "rou_definition": "derived D&A includes depreciation on right-of-use asset exactly once"},
            "periods": ebitda_periods,
        },
        "pbt_basis_discrepancy": pbt_basis, "facts": derived_facts,
        "policy": {"derived_only_not_reported": True, "no_manual_source_method": True, "canonical_promotion": "blocked", "financial_truth_gate_effect": "derived_ebitda_lineage_only"},
    }


def read_note_page(raw: bytes) -> tuple[str, list[tuple]]:
    """Read only verified PDF page 361; caller validates source hash/scope."""
    import pymupdf

    pdf = pymupdf.open(stream=raw, filetype="pdf")
    try:
        if NOTE_PAGE > len(pdf):
            raise DerivedDnaError("note_page_out_of_range")
        page = pdf[NOTE_PAGE - 1]
        return page.get_text("text") or "", list(page.get_text("words") or [])
    finally:
        pdf.close()


def _validate_source(source: dict[str, Any]) -> None:
    if not isinstance(source, dict) or source.get("document_id") != EXPECTED_DOCUMENT_ID or source.get("content_sha256") != EXPECTED_CONTENT_SHA256 or source.get("source_url") != EXPECTED_SOURCE_URL or source.get("page") != NOTE_PAGE:
        raise DerivedDnaError("derived_source_binding_invalid")
    validate_source_page_scope(source.get("page_scope") or ())


def validate_derived_fact(fact: dict[str, Any], *, receipt_source: dict[str, Any]) -> None:
    """Reject forged, incomplete or masquerading derived facts."""
    if not isinstance(fact, dict) or fact.get("epistemic_type") != "derived_fact" or fact.get("reported") is not False or fact.get("source_method") == "manual":
        raise DerivedDnaError("derived_fact_epistemic_type_invalid")
    if fact.get("calculation_version") != DERIVED_LINEAGE_VERSION:
        raise DerivedDnaError("derived_fact_calculation_version_invalid")
    if not isinstance(fact.get("normalized_value"), (int, float)) or not math.isfinite(float(fact["normalized_value"])):
        raise DerivedDnaError("derived_fact_normalized_value_invalid")
    _validate_source(receipt_source)
    source = fact.get("source")
    if source != {key: receipt_source.get(key) for key in ("document_id", "source_url", "content_sha256", "page")}:
        raise DerivedDnaError("derived_fact_source_mismatch")
    formula = fact.get("formula")
    lineage = fact.get("lineage")
    if not isinstance(formula, dict) or not formula.get("id") or formula.get("calculation_version") != DERIVED_LINEAGE_VERSION or not isinstance(lineage, dict) or not isinstance(lineage.get("inputs"), list) or not lineage.get("inputs"):
        raise DerivedDnaError("derived_fact_formula_or_lineage_missing")
    if lineage.get("source_scope") != list(SOURCE_PAGE_SCOPE):
        raise DerivedDnaError("derived_fact_source_scope_invalid")
    for input_fact in lineage["inputs"]:
        if not isinstance(input_fact, dict) or not input_fact.get("fact_id") or not isinstance(input_fact.get("normalized_value"), (int, float)):
            raise DerivedDnaError("derived_fact_input_invalid")
        if input_fact.get("epistemic_type") == "derived_fact":
            if input_fact.get("metric") != "depreciation_amortization":
                raise DerivedDnaError("derived_fact_nested_metric_invalid")
            validate_derived_fact(input_fact, receipt_source=receipt_source)
            continue
        if input_fact.get("epistemic_type") != "reported_fact":
            raise DerivedDnaError("derived_fact_input_invalid")
        _validate_sealed_input(input_fact, receipt_source)
        input_source = input_fact.get("source") or {}
        if input_source.get("document_id") != EXPECTED_DOCUMENT_ID or input_source.get("content_sha256") != EXPECTED_CONTENT_SHA256 or input_source.get("page") not in SOURCE_PAGE_SCOPE:
            raise DerivedDnaError("derived_fact_input_source_invalid")
        expected_input_pages = {
            "operating_profit": {293},
            "depreciation_operating_fixed_assets": {NOTE_PAGE},
            "depreciation_right_of_use": {NOTE_PAGE},
            "amortisation_intangible_assets": {NOTE_PAGE},
        }
        metric = input_fact.get("metric")
        if metric in expected_input_pages and input_source.get("page") not in expected_input_pages[metric]:
            raise DerivedDnaError("derived_fact_input_page_invalid")
        if not isinstance(input_fact.get("geometry"), dict) or not input_fact["geometry"]:
            raise DerivedDnaError("derived_fact_input_geometry_missing")
    if fact.get("metric") == "depreciation_amortization":
        if formula.get("id") != FORMULA_ID or len(lineage["inputs"]) != 3:
            raise DerivedDnaError("derived_dna_formula_invalid")
        expected = sum(float(row["normalized_value"]) for row in lineage["inputs"])
        if float(fact["normalized_value"]) != expected:
            raise DerivedDnaError("derived_dna_value_mismatch")
    elif fact.get("metric") == "ebitda":
        if formula.get("id") != EBITDA_FORMULA_ID or len(lineage["inputs"]) != 2:
            raise DerivedDnaError("derived_ebitda_formula_invalid")
        op, dna = lineage["inputs"]
        if op.get("metric") != "operating_profit" or dna.get("metric") != "depreciation_amortization":
            raise DerivedDnaError("derived_ebitda_input_metric_invalid")
        if float(fact["normalized_value"]) != derive_ebitda(float(op["normalized_value"]), float(dna["normalized_value"])):
            raise DerivedDnaError("derived_ebitda_value_mismatch")
    else:
        raise DerivedDnaError("derived_fact_metric_out_of_scope")


def validate_derived_receipt(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(receipt, dict) or receipt.get("schema_version") != DERIVED_SCHEMA_VERSION or receipt.get("derived_lineage_version") != DERIVED_LINEAGE_VERSION:
        raise DerivedDnaError("derived_receipt_schema_invalid")
    source = receipt.get("source")
    _validate_source(source)
    facts = receipt.get("derived", {}).get("facts") if isinstance(receipt.get("derived"), dict) else None
    if not isinstance(facts, list) or len(facts) != len(EXPECTED_DERIVED_FACTS):
        raise DerivedDnaError("derived_receipt_facts_cardinality_invalid")
    expected_ids = set(EXPECTED_DERIVED_FACTS.values())
    actual_ids = [fact.get("fact_id") for fact in facts if isinstance(fact, dict)]
    if len(actual_ids) != len(set(actual_ids)):
        raise DerivedDnaError("derived_receipt_duplicate_fact_id")
    if set(actual_ids) != expected_ids:
        raise DerivedDnaError("derived_receipt_fact_set_invalid")
    for fact in facts:
        if not isinstance(fact, dict):
            raise DerivedDnaError("derived_receipt_fact_invalid")
        expected_id = EXPECTED_DERIVED_FACTS.get((fact.get("metric"), fact.get("period_end")))
        if expected_id != fact.get("fact_id"):
            raise DerivedDnaError("derived_receipt_fact_identity_invalid")
        validate_derived_fact(fact, receipt_source=source)
    return facts
