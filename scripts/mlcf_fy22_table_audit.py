"""Audit-only extraction of four geometry-bound FY2022 MLCF statement cells.

This is deliberately not a financial-fact writer.  It records the current-year
column, row label, units and source geometry needed for a later independent
statement/tie-out review.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / ".cache/company_intel/mlcf_official_intake/194111.pdf"
MANIFEST = ROOT / "config/mlcf_official_intake_manifest.json"
OUT = ROOT / "state/company_intel/mlcf_fy22_table_audit.json"
DOCUMENT_ID = "psx:194111"
SOURCE_URL = "https://financials.psx.com.pk/lib/DownloadPDF.php?id=194111"
EXPECTED_HASH = "5103d0a5eaaa8ce2c8c435ae50de6ee5000248ad05094e3f0ac086212e687aae"


def words_by_line(page: pymupdf.Page) -> dict[float, list[tuple[float, float, float, float, str]]]:
    lines: dict[float, list[tuple[float, float, float, float, str]]] = {}
    # PyMuPDF's line indexes restart inside blocks.  Physical baseline is the
    # stable statement-table row key for an immutable, hash-bound page.
    for x0, y0, x1, y1, text, _block, _line, _word in page.get_text("words"):
        lines.setdefault(round(y0, 1), []).append((x0, y0, x1, y1, text))
    return lines


def phrase(words: list[tuple[float, float, float, float, str]]) -> str:
    return " ".join(word[4] for word in sorted(words, key=lambda item: item[0])).replace(" - ", "-")


def value_at_current_column(
    page: pymupdf.Page, *, label: str, value: str, header_y_max: float
) -> tuple[dict[str, float | str], dict[str, float | str]]:
    lines = words_by_line(page)
    header = next(
        (word for row in lines.values() for word in row if word[4] == "2022" and word[1] <= header_y_max),
        None,
    )
    if header is None:
        raise ValueError(f"current-period 2022 header missing on page {page.number + 1}")
    for row in lines.values():
        text = phrase(row)
        if label not in text:
            continue
        row_y = sum(word[1] for word in row) / len(row)
        # Number cells are positioned on a slightly different PDF baseline
        # from their row labels, so resolve within a tight physical tolerance.
        current = [
            word
            for candidate_row in lines.values()
            for word in candidate_row
            if word[4] == value and 380 <= word[0] <= 445 and abs(word[1] - row_y) <= 2
        ]
        if len(current) != 1:
            raise ValueError(f"{label}: current-period cell not unique on page {page.number + 1}")
        cell = current[0]
        return (
            {"text": "2022", "x0": round(header[0], 1), "y0": round(header[1], 1), "x1": round(header[2], 1), "y1": round(header[3], 1)},
            {"text": value, "x0": round(cell[0], 1), "y0": round(cell[1], 1), "x1": round(cell[2], 1), "y1": round(cell[3], 1)},
        )
    raise ValueError(f"{label}: statement row missing on page {page.number + 1}")


def candidate(
    *, metric: str, reported_label: str, reported_value: float, normalized_value: float,
    unit: str, page: int, header: dict[str, float | str], cell: dict[str, float | str]
) -> dict[str, object]:
    return {
        "metric": metric,
        "reported_label": reported_label,
        "reported_value": reported_value,
        "normalized_value": normalized_value,
        "unit": unit,
        "currency": "PKR",
        "period_start": "2021-07-01",
        "period_end": "2022-06-30",
        "duration_months": 12,
        "statement_identity": "consolidated",
        "document_id": DOCUMENT_ID,
        "source_url": SOURCE_URL,
        "content_sha256": EXPECTED_HASH,
        "original_page": page,
        "current_period_header_geometry": header,
        "cell_geometry": cell,
        "status": "audit_only",
        "promotion_status": "blocked_pending_independent_statement_and_period_tie_out",
    }


def build() -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest_row = next(row for row in manifest["documents"] if row["document_id"] == DOCUMENT_ID)
    raw = PDF.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_HASH or manifest_row["content_sha256"] != EXPECTED_HASH:
        raise ValueError("FY2022 original-byte hash mismatch")
    with pymupdf.open(stream=raw, filetype="pdf") as pdf:
        profit_loss = pdf[272]
        cash_flow = pdf[274]
        h_sales, c_sales = value_at_current_column(profit_loss, label="Sales-net", value="48,519,622", header_y_max=170)
        h_pat, c_pat = value_at_current_column(profit_loss, label="Profit after taxation", value="4,553,125", header_y_max=170)
        h_eps, c_eps = value_at_current_column(profit_loss, label="Earnings per share-basic and diluted", value="4.15", header_y_max=170)
        h_ocf, c_ocf = value_at_current_column(cash_flow, label="Net cash generated from operating activities", value="9,389,176", header_y_max=130)
    candidates = [
        candidate(metric="revenue", reported_label="Sales - net", reported_value=48_519_622, normalized_value=48_519_622_000, unit="PKR thousands", page=273, header=h_sales, cell=c_sales),
        candidate(metric="profit_after_tax", reported_label="Profit after taxation", reported_value=4_553_125, normalized_value=4_553_125_000, unit="PKR thousands", page=273, header=h_pat, cell=c_pat),
        candidate(metric="basic_eps", reported_label="Earnings per share - basic and diluted", reported_value=4.15, normalized_value=4.15, unit="PKR per share", page=273, header=h_eps, cell=c_eps),
        candidate(metric="operating_cash_flow", reported_label="Net cash generated from operating activities", reported_value=9_389_176, normalized_value=9_389_176_000, unit="PKR thousands", page=275, header=h_ocf, cell=c_ocf),
    ]
    return {
        "schema_version": 1,
        "receipt_version": "mlcf_fy22_table_audit_v1",
        "symbol": "MLCF",
        "scope": "one official FY2022 annual report, four audit-only current-period table cells",
        "policy": {
            "official_hash_bound_original_only": True,
            "consolidated_statement_only": True,
            "current_period_header_geometry_required": True,
            "no_network": True,
            "no_ocr": True,
            "audit_only": True,
            "canonical_financial_facts_written": False,
            "financial_truth_changed": False,
            "formal_outputs_activated": False,
        },
        "candidates": candidates,
        "required_before_promotion": [
            "independent full-statement extraction",
            "annual period tie-out",
            "existing canonical fact conflict check",
            "financial-truth builder acceptance",
        ],
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
