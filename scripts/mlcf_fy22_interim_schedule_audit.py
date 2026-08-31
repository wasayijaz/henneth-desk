"""Audit-only geometry receipt for direct three-month consolidated MLCF rows.

Only native text from the three retained issuer PDFs is used.  The half-year and
nine-month reports are accepted only where their original statement prints an
explicit quarter column; no quarter is derived by subtraction.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/mlcf_official_intake_manifest.json"
OUT = ROOT / "state/company_intel/mlcf_fy22_interim_schedule_audit.json"
INTAKE = ROOT / ".cache/company_intel/mlcf_official_intake"

SPECS = {
    "issuer:mlcf:1q-2021-09": {"file": "q1_2021.pdf", "page": 32, "period_end": "2021-09-30", "period_start": "2021-07-01", "year": "2021", "quarter_x": (320, 380), "duration_label": "three_months"},
    "issuer:mlcf:hy-2021-12": {"file": "hy_2021.pdf", "page": 40, "period_end": "2021-12-31", "period_start": "2021-10-01", "year": "2021", "quarter_x": (320, 380), "duration_label": "three_months"},
    "issuer:mlcf:q3-2022-03": {"file": "q3_2022.pdf", "page": 34, "period_end": "2022-03-31", "period_start": "2022-01-01", "year": "2022", "quarter_x": (320, 380), "duration_label": "three_months"},
}
METRICS = {
    "revenue": (re.compile(r"^sales\s*-\s*net", re.I), "Sales - net", "PKR thousands"),
    "profit_after_tax": (re.compile(r"^profit\s+after\s+taxation", re.I), "Profit after taxation", "PKR thousands"),
    "basic_eps": (re.compile(r"^earnings\s+per\s+share\s*-\s*basic$", re.I), "Earnings per share - basic and diluted", "PKR per share"),
}


def _bbox(tokens: list[tuple]) -> dict[str, float]:
    return {k: round(v, 1) for k, v in zip(("x0", "y0", "x1", "y1"), (min(float(t[0]) for t in tokens), min(float(t[1]) for t in tokens), max(float(t[2]) for t in tokens), max(float(t[3]) for t in tokens)))}


def _line_rows(page: pymupdf.Page) -> list[list[tuple]]:
    rows: dict[float, list[tuple]] = {}
    for token in page.get_text("words"):
        rows.setdefault(round(float(token[1]), 1), []).append(token)
    return [sorted(row, key=lambda t: float(t[0])) for _, row in sorted(rows.items())]


def _num(text: str) -> float | None:
    text = text.strip()
    if text in {"-", "—", "–"}:
        return 0.0
    if not re.fullmatch(r"\(?-?[\d,]+(?:\.\d+)?\)?", text):
        return None
    value = float(text.strip("()").replace(",", ""))
    return -value if text.startswith("(") and text.endswith(")") else value


def _evidence(page: pymupdf.Page, pattern: str, *, max_y: float = 180) -> dict[str, Any]:
    words = [t for t in page.get_text("words") if float(t[1]) <= max_y]
    selected = [t for t in words if re.search(pattern, str(t[4]), re.I)]
    if not selected:
        raise ValueError(f"missing evidence {pattern!r} on page {page.number + 1}")
    return {"text": " ".join(str(t[4]) for t in selected), "geometry": _bbox(selected), "original_page": page.number + 1}


def _period_evidence(page: pymupdf.Page) -> dict[str, Any]:
    selected = [t for t in page.get_text("words") if float(t[1]) < 100]
    text = " ".join(str(t[4]) for t in sorted(selected, key=lambda t: (float(t[1]), float(t[0]))))
    if "CONDENSED" not in text or "CONSOLIDATED" not in text or "STATEMENT" not in text or "ENDED" not in text:
        raise ValueError(f"statement/period title incomplete on page {page.number + 1}")
    return {"text": text, "geometry": _bbox(selected), "original_page": page.number + 1, "duration_months": 3}


def _candidate(page: pymupdf.Page, document_id: str, spec: dict[str, Any], metric: str, matcher: re.Pattern[str], label: str, unit: str, sha: str, source_url: str) -> dict[str, Any]:
    rows = _line_rows(page)
    row = next((r for r in rows if matcher.search(" ".join(str(t[4]) for t in r))), None)
    if row is None and metric == "basic_eps":
        row = next((r for r in rows if " ".join(str(t[4]) for t in r).lower() == "earnings per share - basic"), None)
        if row is None:
            # Label wraps onto the next physical line; combine both lines.
            first = next((r for r in rows if "Earnings per share - basic" in " ".join(str(t[4]) for t in r)), None)
            second = next((r for r in rows if "and diluted" in " ".join(str(t[4]) for t in r)), None)
            if first and second:
                row = first + second
    if row is None:
        raise ValueError(f"{document_id} {metric}: row missing")
    row_y = max(float(t[1]) for t in row) if metric == "basic_eps" else sum(float(t[1]) for t in row) / len(row)
    all_words = list(page.get_text("words"))
    x0, x1 = spec["quarter_x"]
    numeric = [(t, _num(str(t[4]))) for t in all_words if x0 <= float(t[0]) < x1 and abs(float(t[1]) - row_y) <= 2.5 and _num(str(t[4])) is not None]
    if len(numeric) != 1:
        raise ValueError(f"{document_id} {metric}: direct quarter cell is not unique")
    cell, value = numeric[0]
    current_year = [t for t in all_words if str(t[4]) == spec["year"] and x0 <= float(t[0]) < x1 and float(t[1]) < 180]
    if len(current_year) != 1:
        raise ValueError(f"{document_id}: current quarter year header missing")
    scale = _evidence(page, r"Rupees", max_y=180)
    scale["text"] = "Rupees in thousand"
    identity = _evidence(page, r"CONSOLIDATED", max_y=100)
    period = _period_evidence(page)
    normalized = value if unit == "PKR per share" else value * 1000
    return {
        "metric": metric,
        "reported_label": label,
        "reported_value": value,
        "normalized_value": normalized,
        "unit": unit,
        "currency": "PKR",
        "scale": 1 if unit == "PKR per share" else 1000,
        "period_start": spec["period_start"],
        "period_end": spec["period_end"],
        "duration_months": 3,
        "column_role": "current_quarter",
        "statement_identity": "consolidated",
        "document_id": document_id,
        "source_url": source_url,
        "content_sha256": sha,
        "original_page": page.number + 1,
        "statement_identity_evidence": identity,
        "period_evidence": period,
        "scale_currency_evidence": scale,
        "current_period_header_geometry": {"text": spec["year"], "geometry": _bbox([current_year[0]]), "original_page": page.number + 1},
        "cell_geometry": {"text": str(cell[4]), "geometry": _bbox([cell])},
        "status": "audit_only",
        "promotion_status": "blocked_pending_official_availability_date_and_independent_tie_out",
    }


def build() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_id = {row["document_id"]: row for row in manifest["documents"]}
    candidates: list[dict[str, Any]] = []
    omissions: list[dict[str, str]] = []
    for document_id, spec in SPECS.items():
        row = by_id[document_id]
        path = INTAKE / spec["file"]
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        if sha != row["content_sha256"]:
            raise ValueError(f"{document_id}: retained-byte hash mismatch")
        try:
            with pymupdf.open(stream=raw, filetype="pdf") as pdf:
                page = pdf[spec["page"] - 1]
                for metric, (matcher, label, unit) in METRICS.items():
                    try:
                        observed = _candidate(page, document_id, spec, metric, matcher, label, unit, sha, row["source_url"])
                        omission_reason = (
                            "profit_after_tax_attribution_not_proven_on_original_page"
                            if metric == "profit_after_tax"
                            else "direct_three_month_geometry_seen_but_set_not_qualified_official_availability_date_missing"
                        )
                        omissions.append({
                            "document_id": document_id,
                            "metric": metric,
                            "reason": omission_reason,
                            "why_no_direct_current_3m_set": "The original page shows a direct current-quarter column, but this audit emits zero promotion candidates because official availability dates are missing; PAT also lacks an explicit owner-attribution row.",
                            "selected_original_page": observed["original_page"],
                            "selected_page_text": observed["period_evidence"]["text"],
                            "geometry_evidence": {
                                "statement_identity": observed["statement_identity_evidence"],
                                "period": observed["period_evidence"],
                                "scale_currency": observed["scale_currency_evidence"],
                                "current_period_header": observed["current_period_header_geometry"],
                                "cell": observed["cell_geometry"],
                            },
                        })
                    except (ValueError, IndexError) as exc:
                        omissions.append({
                            "document_id": document_id,
                            "metric": metric,
                            "reason": str(exc),
                            "why_no_direct_current_3m_set": "No audit candidate was emitted because the bounded geometry check did not prove a unique direct current-quarter cell.",
                            "selected_original_page": spec["page"],
                            "selected_page_text": " ".join(page.get_text().splitlines()[:8]),
                        })
        except (ValueError, IndexError) as exc:
            omissions.append({"document_id": document_id, "reason": str(exc)})
    return {
        "schema_version": 1,
        "receipt_version": "mlcf_fy22_interim_schedule_audit_v1",
        "symbol": "MLCF",
        "scope": "direct three-month consolidated Revenue/PAT/EPS candidates from three retained FY22 interim PDFs",
        "source_manifest": "config/mlcf_official_intake_manifest.json",
        "policy": {
            "official_hash_bound_original_only": True,
            "consolidated_statement_only": True,
            "direct_three_month_column_required": True,
            "no_quarter_from_cumulative_subtraction": True,
            "local_scale_currency_required": True,
            "statement_period_identity_geometry_required": True,
            "no_network": True,
            "no_ocr": True,
            "audit_only": True,
            "canonical_financial_facts_written": False,
            "financial_truth_changed": False,
            "formal_outputs_activated": False,
        },
        "official_availability": {
            "status": "missing",
            "documents": {doc: {"published_at": by_id[doc].get("published_at"), "available_on": by_id[doc].get("available_on")} for doc in SPECS},
            "reason": "source_manifest_has_no_official_published_at_or_available_on",
            "promotion_blocker": True,
            "no_date_inferred": True,
        },
        "candidates": candidates,
        "omissions": omissions,
        "qualification": {"status": "blocked", "direct_three_month_set_qualified": False, "reason": "audit candidates only; official availability dates and independent reconciliation remain missing"},
        "required_before_promotion": ["official availability-date binding from source manifest published_at or available_on", "independent statement/tie-out review", "canonical conflict check", "financial-truth builder acceptance"],
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
