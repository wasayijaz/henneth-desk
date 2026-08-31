#!/usr/bin/env python3
"""Hash-bound, audit-only table extraction for MLCF FY2022 consolidated pages."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / ".cache/company_intel/mlcf_official_intake/194111.pdf"
MANIFEST = ROOT / "config/mlcf_official_intake_manifest.json"
OUT = ROOT / "state/company_intel/mlcf_fy22_table_audit.json"

HEADER_X = (403.88, 426.12)
HEADER_Y = (141.80, 153.98)
OCF_HEADER_X = (406.10, 423.90)
OCF_HEADER_Y = (99.60, 109.36)
MISSING_OFFICIAL_AVAILABILITY_REASON = "source_manifest_has_no_official_published_at_or_available_on"


def rect(w: tuple[float, ...]) -> dict[str, float]:
    return {k: round(float(v), 2) for k, v in zip(("x0", "y0", "x1", "y1"), w[:4])}


def in_range(value: float, bounds: tuple[float, float], tol: float = 0.25) -> bool:
    return bounds[0] - tol <= value <= bounds[1] + tol


def header_words(page: pymupdf.Page, expected_year: str, x_bounds: tuple[float, float], y_bounds: tuple[float, float]):
    matches = [w for w in page.get_text("words") if w[4] == expected_year and in_range(w[0], x_bounds) and in_range(w[1], y_bounds)]
    return matches[0] if len(matches) == 1 else None


def numeric_token(text: str) -> float | None:
    m = re.fullmatch(r"\(?-?[\d,]+(?:\.\d+)?\)?", text.strip())
    if not m:
        return None
    value = float(text.strip("()").replace(",", ""))
    return -value if text.startswith("(") else value


def find_row(page: pymupdf.Page, label_re: str, value_x: tuple[float, float], y_bounds: tuple[float, float]):
    # PyMuPDF keeps a whole statement in one text block.  Group words by
    # (block,line) so each row's left label and current-period cell are bound
    # to the same baseline rather than scraping the block as a whole.
    grouped: dict[float, list[tuple]] = {}
    for w in page.get_text("words"):
        if y_bounds[0] <= w[1] <= y_bounds[1]:
            grouped.setdefault(round(float(w[1]), 1), []).append(w)
    rows = []
    for words in grouped.values():
        words.sort(key=lambda w: w[0])
        labels = [w for w in words if w[0] < 330]
        label = " ".join(w[4] for w in labels).strip()
        if not re.search(label_re, label, re.I):
            continue
        cells = []
        for w in words:
            if in_range(w[0], value_x, 0.5):
                val = numeric_token(w[4])
                if val is not None:
                    cells.append((val, w))
        if len(cells) == 1:
            rows.append((label, cells[0]))
    return rows[0] if len(rows) == 1 else None


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    row = next(d for d in manifest["documents"] if d["document_id"] == "psx:194111")
    raw = PDF.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != row["content_sha256"]:
        raise ValueError("194111.pdf hash mismatch")
    doc = pymupdf.open(stream=raw, filetype="pdf")
    pages = {}
    candidates = []
    for number in (271, 273, 275):
        page = doc[number - 1]
        upper = " ".join(page.get_text().split()).upper()
        if "CONSOLIDATED" not in upper or "UNCONSOLIDATED" in upper:
            raise ValueError(f"page {number} is not consolidated")
        hw = header_words(page, "2022", OCF_HEADER_X if number == 275 else HEADER_X, OCF_HEADER_Y if number == 275 else HEADER_Y)
        if hw is None:
            raise ValueError(f"page {number}: deterministic current-period header missing")
        pages[str(number)] = {
            "page": number,
            "identity": "consolidated",
            "current_period": "2022",
            "period_end": "2022-06-30",
            "duration_months": 12,
            "unit": "PKR_thousand",
            "table_header_geometry": rect(hw),
        }
        if number == 273:
            specs = [
                ("sales_net", r"^Sales\s*-\s*net$", (389.96, 440.0), (185, 205), "PKR_thousand"),
                ("profit_after_taxation", r"^Profit\s+after\s+taxation$", (395.52, 440.0), (437, 458), "PKR_thousand"),
                ("eps_basic_diluted", r"^Earnings\s+per\s+share\s*-\s+basic\s+and\s+diluted$", (420.54, 440.0), (497, 518), "PKR/share"),
            ]
            for metric, pattern, xb, yb, unit in specs:
                hit = find_row(page, pattern, xb, yb)
                if hit is None:
                    continue
                label, (value, word) = hit
                candidates.append({"metric": metric, "label": label, "raw_value": value, "unit": unit, "cell_geometry": rect(word), "page": 273})
        elif number == 275:
            hit = find_row(page, r"^Net\s+cash\s+generated\s+from\s+operating\s+activities$", (404.416, 440.0), (519, 538))
            if hit is not None:
                label, (value, word) = hit
                candidates.append({"metric": "net_cash_generated_from_operating_activities", "label": label, "raw_value": value, "unit": "PKR_thousand", "cell_geometry": rect(word), "page": 275})
    availability = {
        "published_at": row.get("published_at"),
        "available_on": row.get("available_on"),
        "status": "missing",
        "reason": MISSING_OFFICIAL_AVAILABILITY_REASON,
        "binding_required_before_promotion": True,
        "no_date_inferred": True,
    }
    for c in candidates:
        c.update({"document_id": "psx:194111", "statement_identity": "consolidated", "period_end": "2022-06-30", "duration_months": 12, "content_sha256": digest, "status": "audit_only", "promotion_status": "blocked", "model_readiness": "not_ready", "model_readiness_reason": MISSING_OFFICIAL_AVAILABILITY_REASON})
    result = {
        "schema_version": 1,
        "receipt_version": "mlcf_fy22_table_audit_v1",
        "symbol": "MLCF",
        "source_pdf": ".cache/company_intel/mlcf_official_intake/194111.pdf",
        "source_url": row["source_url"],
        "content_sha256": digest,
        "official_availability": availability,
        "pages": pages,
        "candidates": candidates,
        "policy": {"local_original_only": True, "native_text_geometry_required": True, "hash_bound": True, "consolidated_only": True, "audit_only": True, "facts_promoted": False, "coverage_changed": False, "case_changed": False, "promotion_status": "blocked"},
        "summary": {"candidate_count": len(candidates), "facts": [], "promotion_status": "blocked", "reason": MISSING_OFFICIAL_AVAILABILITY_REASON},
        "required_before_promotion": [
            "official availability-date binding from source manifest published_at or available_on",
            "independent full-statement extraction",
            "annual period tie-out",
            "existing canonical fact conflict check",
            "financial-truth builder acceptance",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}; candidates={len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
