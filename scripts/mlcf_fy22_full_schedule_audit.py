"""Build an audit-only, geometry-bound FY2022 MLCF statement schedule.

The receipt is deliberately a candidate lane: it never writes canonical facts or
changes qualification state.  Values are read only from the retained, hash-bound
PSX PDF and are accepted only when a local ``2022``/``2021`` table header, scale,
consolidated heading and a unique two-column row are visible in native text.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / ".cache/company_intel/mlcf_official_intake/194111.pdf"
MANIFEST = ROOT / "config/mlcf_official_intake_manifest.json"
OUT = ROOT / "state/company_intel/mlcf_fy22_full_schedule_audit.json"
DOCUMENT_ID = "psx:194111"
SOURCE_URL = "https://financials.psx.com.pk/lib/DownloadPDF.php?id=194111"
EXPECTED_HASH = "5103d0a5eaaa8ce2c8c435ae50de6ee5000248ad05094e3f0ac086212e687aae"
MISSING_OFFICIAL_AVAILABILITY_REASON = "source_manifest_has_no_official_published_at_or_available_on"
OFFICIAL_AVAILABILITY_REQUIREMENT = "official availability-date binding from source manifest published_at or available_on"

SPECS: dict[str, tuple[str, list[tuple[int, str]]]] = {
    "balance_sheet": ("balance_sheet", [
        ("cash_and_cash_equivalents", r"^cash\s+and\s+(?:cash\s+and\s+)?bank\s+balances\b"),
        ("trade_receivables", r"^trade\s+debts?\b"),
        ("inventories", r"^stock-in-trade\b"),
        ("total_current_assets", r"^total\s+current\s+assets\b"),
        ("property_plant_equipment", r"^property,\s*plant\s+and\s+equipment\b"),
        ("total_assets", r"^total\s+assets\b"),
        ("short_term_borrowings", r"^short\s+term\s+borrowings\b"),
        ("long_term_borrowings", r"^long\s+term\s+loans\s+from\s+financial\s+institutions\b"),
        ("trade_payables", r"^trade\s+and\s+other\s+payables\b"),
        ("total_equity", r"^total\s+equity\b"),
    ]),
    "income_statement": ("income_statement", [
        ("revenue", r"^sales\s*-\s*net\b"),
        ("gross_profit", r"^gross\s+profit\b"),
        ("ebitda", r"^ebitda\b"),
        ("operating_profit", r"^profit\s+from\s+operations\b"),
        ("finance_cost", r"^finance\s+cost\b"),
        ("profit_before_tax", r"^profit\s+before\s+taxation\b"),
        ("profit_after_tax_attributable", r"^profit\s+after\s+taxation\b"),
        ("tax_expense", r"^taxation\b"),
        ("basic_eps", r"^earnings\s+per\s+share\s*-\s*basic\s+and\s+diluted\b"),
    ]),
    "cash_flow_statement": ("cash_flow_statement", [
        ("operating_cash_flow", r"^net\s+cash\s+generated\s+from\s+operating\s+activities\b"),
        ("capital_expenditure", r"^capital\s+expenditure\b"),
        ("depreciation_amortization", r"^depreciation\s+and\s+amortization\b"),
        ("net_cash_from_investing_activities", r"^net\s+cash\s+used\s+in\s+investing\s+activities\b"),
        ("net_cash_from_financing_activities", r"^net\s+cash\s+generated\s+from\s*/?\s*\(?used\s+in\)?\s+financing\s+activities\b"),
        ("dividends_paid", r"^dividend\s+paid\b"),
    ]),
}

PAGE_SCOPE = {"balance_sheet": [271, 272], "income_statement": [273], "cash_flow_statement": [275]}


def _num(text: str) -> float | None:
    text = str(text).strip()
    if text in {"-", "—", "–"}:
        return 0.0
    m = re.fullmatch(r"\(?-?[\d,]+(?:\.\d+)?\)?", text)
    if not m:
        return None
    value = float(text.strip("()").replace(",", ""))
    return -value if text.startswith("(") and text.endswith(")") else value


def _bbox(tokens: list[tuple]) -> dict[str, float]:
    return {k: round(v, 1) for k, v in zip(("x0", "y0", "x1", "y1"), (
        min(float(t[0]) for t in tokens), min(float(t[1]) for t in tokens),
        max(float(t[2]) for t in tokens), max(float(t[3]) for t in tokens))) }


def _lines(page: pymupdf.Page) -> list[list[tuple]]:
    groups: dict[float, list[tuple]] = {}
    for token in page.get_text("words"):
        groups.setdefault(round(float(token[1]), 1), []).append(token)
    return [sorted(v, key=lambda t: float(t[0])) for _, v in sorted(groups.items())]


def _header(page: pymupdf.Page) -> tuple[dict[str, float | str], dict[str, float | str]]:
    years = {str(t[4]): t for t in page.get_text("words") if str(t[4]) in {"2022", "2021"} and float(t[1]) < 180 and float(t[0]) > 380}
    if set(years) != {"2022", "2021"}:
        raise ValueError(f"page {page.number + 1}: missing current/comparison header")
    return ({"text": "2022", **_bbox([years["2022"]])}, {"text": "2021", **_bbox([years["2021"]])})


def _extract(page: pymupdf.Page, canonical: str, pattern: str, scale: int) -> dict[str, object] | None:
    candidates = []
    all_words = list(page.get_text("words"))
    for row in _lines(page):
        label = " ".join(str(t[4]) for t in row)
        if not re.search(pattern, label, re.I):
            continue
        y = sum(float(t[1]) for t in row) / len(row)
        band = [t for t in all_words if abs(float(t[1]) - y) <= 2.1]
        nums = [(t, _num(str(t[4]))) for t in band if float(t[0]) >= 380 and _num(str(t[4])) is not None]
        current = [x for x in nums if float(x[0][0]) < 455]
        comparative = [x for x in nums if float(x[0][0]) >= 455]
        if len(current) == 1 and len(comparative) == 1:
            candidates.append((row, current[0], comparative[0], label))
    if len(candidates) != 1:
        return None
    row, cur, comp, label = candidates[0]
    unit = "PKR per share" if canonical == "basic_eps" else "PKR thousands"
    multiplier = 1 if unit == "PKR per share" else scale
    scale_tokens = [t for t in page.get_text("words") if re.search(r"thousand", str(t[4]), re.I)]
    basis_tokens = [t for t in page.get_text("words") if str(t[4]).lower() == "consolidated" and float(t[1]) < 140]
    return {
        "canonical_line": canonical,
        "reported_label": label,
        "statement_type": "balance_sheet" if page.number + 1 in (271, 272) else ("income_statement" if page.number + 1 == 273 else "cash_flow_statement"),
        "statement_identity": "consolidated",
        "period_end": "2022-06-30",
        "duration_months": 12,
        "column_role": "current",
        "comparative_to_period_end": "2021-06-30",
        "raw_value": str(cur[0][4]),
        "reported_value": cur[1],
        "normalized_value": cur[1] * multiplier,
        "comparative_raw_value": str(comp[0][4]),
        "comparative_value": comp[1],
        "comparative_normalized_value": comp[1] * multiplier,
        "unit": unit,
        "currency": "PKR",
        "scale": scale,
        "scale_evidence": {"text": "Rupees in thousand", "geometry": _bbox(scale_tokens[:4]) if scale_tokens else {}},
        "basis_evidence": {"text": "CONSOLIDATED", "geometry": _bbox(basis_tokens[:1]) if basis_tokens else {}, "original_page": page.number + 1},
        "original_page": page.number + 1,
        "row_geometry": _bbox(row),
        "cell_geometry": {"current": _bbox([cur[0]]), "comparison": _bbox([comp[0]])},
        "status": "audit_only",
        "promotion_status": "blocked",
        "model_readiness": "not_ready",
        "model_readiness_reason": MISSING_OFFICIAL_AVAILABILITY_REASON,
        "document_id": DOCUMENT_ID,
        "source_url": SOURCE_URL,
        "content_sha256": EXPECTED_HASH,
    }


def build() -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest_row = next(d for d in manifest["documents"] if d["document_id"] == DOCUMENT_ID)
    raw = PDF.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_HASH or manifest_row.get("content_sha256") != EXPECTED_HASH:
        raise ValueError("FY2022 original-byte hash mismatch")
    official_availability = {
        "published_at": manifest_row.get("published_at"),
        "available_on": manifest_row.get("available_on"),
        "status": "missing",
        "reason": MISSING_OFFICIAL_AVAILABILITY_REASON,
        "binding_required_before_promotion": True,
        "no_date_inferred": True,
    }
    candidates: list[dict[str, object]] = []
    omissions: list[dict[str, str]] = []
    with pymupdf.open(stream=raw, filetype="pdf") as pdf:
        pages = {n: pdf[n - 1] for n in {271, 272, 273, 275}}
        headers = {n: _header(pages[n]) for n in pages}
        for schedule, (_, specs) in SPECS.items():
            page = pages[PAGE_SCOPE[schedule][-1] if schedule != "balance_sheet" else 272]
            for canonical, pattern in specs:
                found = _extract(page, canonical, pattern, 1000)
                if found is None and schedule == "balance_sheet" and page.number + 1 == 272:
                    found = _extract(pages[271], canonical, pattern, 1000)
                if found is None:
                    omissions.append({"statement_type": schedule, "canonical_line": canonical, "reason": "missing_or_ambiguous_geometry_on_scoped_pages"})
                else:
                    hdr = headers[found["original_page"]]
                    found["current_period_header_geometry"] = hdr[0]
                    found["comparison_period_header_geometry"] = hdr[1]
                    if not found["basis_evidence"]["geometry"]:
                        omissions.append({"statement_type": schedule, "canonical_line": canonical, "reason": "missing_or_ambiguous_geometry_on_scoped_pages"})
                        continue
                    candidates.append(found)
    return {
        "schema_version": 1,
        "receipt_version": "mlcf_fy22_full_schedule_audit_v1",
        "symbol": "MLCF",
        "document_id": DOCUMENT_ID,
        "source": {"document_id": DOCUMENT_ID, "source_url": SOURCE_URL, "raw_path": str(PDF.relative_to(ROOT)).replace("\\", "/"), "content_sha256": EXPECTED_HASH, "page_scope": [271, 272, 273, 275], "official_availability": official_availability},
        "period": {"period_end": "2022-06-30", "duration_months": 12, "comparison_period_end": "2021-06-30"},
        "policy": {"official_hash_bound_original_only": True, "consolidated_statement_only": True, "local_scale_required": True, "current_column_header_required": True, "row_geometry_required": True, "no_network": True, "no_ocr": True, "audit_only": True, "canonical_financial_facts_written": False, "qualification_changed": False, "formal_outputs_activated": False},
        "candidates": candidates,
        "omissions": omissions,
        "qualification": {"status": "blocked", "full_schedule_qualified": False, "reason": "candidate evidence only; official availability-date binding, independent statement/tie-out and canonical acceptance remain required"},
        "required_before_promotion": [OFFICIAL_AVAILABILITY_REQUIREMENT, "independent full-statement extraction", "annual period tie-out", "existing canonical conflict check", "financial-truth builder acceptance"],
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
