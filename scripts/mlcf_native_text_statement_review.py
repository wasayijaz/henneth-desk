#!/usr/bin/env python3
"""Audit-only native-text/geometry review for retained MLCF statements.

This lane binds local originals to the approved manifest and records statement
identity/page eligibility only. It intentionally emits no financial values/facts.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "mlcf_official_intake_manifest.json"
BASE = ROOT / ".cache" / "company_intel" / "mlcf_official_intake"
OUT = ROOT / "state" / "company_intel" / "mlcf_native_text_statement_review_receipt.json"

FILES = {
    "psx:194111": "194111.pdf",
    "issuer:mlcf:1q-2021-09": "q1_2021.pdf",
    "issuer:mlcf:hy-2021-12": "hy_2021.pdf",
    "issuer:mlcf:q3-2022-03": "q3_2022.pdf",
}

STATEMENT_RE = re.compile(r"statement of (?:financial position|profit or loss|comprehensive income|cash flows|changes in equity)", re.I)


def _page_meta(page: pymupdf.Page, number: int) -> dict[str, object]:
    text = " ".join(page.get_text().split())
    upper = text.upper()
    blocks = page.get_text("blocks")
    headers = [
        bool(re.search(r"(?:UNCONSOLIDATED|CONSOLIDATED)\s+STATEMENT OF FINANCIAL POSITION\s+AS AT", upper)),
        bool(re.search(r"(?:UNCONSOLIDATED|CONSOLIDATED)\s+STATEMENT OF PROFIT OR LOSS\s+FOR", upper)),
        bool(re.search(r"(?:UNCONSOLIDATED|CONSOLIDATED)\s+STATEMENT OF COMPREHENSIVE INCOME\s+FOR", upper)),
        bool(re.search(r"(?:UNCONSOLIDATED|CONSOLIDATED)?\s*CASH FLOWS FROM OPERATING ACTIVITIES", upper)),
    ]
    identity = "consolidated" if "CONSOLIDATED" in upper and "UNCONSOLIDATED" not in upper else (
        "standalone" if "UNCONSOLIDATED" in upper else "unknown"
    )
    units = bool(re.search(r"RUPEES?\s+IN\s+(?:THOUSAND|MILLION)", upper))
    period = bool(re.search(r"(?:YEAR|MONTHS|QUARTER|PERIOD)\s+ENDED|AS\s+AT", upper))
    return {
        "page": number,
        "statement_headers": [
            label for label, present in zip(
                ("financial_position", "profit_or_loss", "comprehensive_income", "cash_flows"), headers
            ) if present
        ],
        "identity": identity,
        "period_header_visible": period,
        "units_header_visible": units,
        "text_geometry_sufficient": bool(text and blocks and any(headers) and period and units),
        "text_block_count": len(blocks),
    }


def build() -> dict[str, object]:
    # This is receipt metadata only; release finalization overwrites it with the
    # shared build cutoff before the artifact can enter the integrity manifest.
    generated_at = "pending_ci_integrity_finalization"
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = {row["document_id"]: row for row in manifest["documents"]}
    docs: list[dict[str, object]] = []
    for doc_id, filename in FILES.items():
        row = rows[doc_id]
        path = BASE / filename
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != row["content_sha256"]:
            raise ValueError(f"{doc_id}: local hash does not match manifest")
        pdf = pymupdf.open(stream=raw, filetype="pdf")
        pages = [_page_meta(page, i + 1) for i, page in enumerate(pdf) if any(_page_meta(page, i + 1)["statement_headers"])]
        selected = [p for p in pages if p["text_geometry_sufficient"]]
        identities = sorted({p["identity"] for p in pages if p["identity"] != "unknown"})
        if not selected:
            raise ValueError(f"{doc_id}: no statement page has visible header/period/unit geometry")
        docs.append({
            "document_id": doc_id,
            "source": row["source"],
            "source_url": row["source_url"],
            "raw_path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "original_page": 1,
            "content_sha256": digest,
            "content_length": len(raw),
            "page_count": len(pdf),
            "statement_identity": identities,
            "period": {
                "period_end": row["period_end"],
                "period_type": row["period_type"],
                "duration": "twelve_months" if row["period_type"] == "annual" else (
                    "three_months" if doc_id.endswith("09") else "six_months" if doc_id.endswith("12") else "nine_months"
                ),
            },
            "selected_statement_pages": selected,
            "parser_entry_candidate": True,
            "parser_entry_basis": "native text with visible statement header, period header and units; identity remains explicit",
            "facts": [],
            "promotion_status": "audit_only",
        })
    return {
        "schema_version": 1,
        "receipt_version": "mlcf_native_text_statement_review_v1",
        "symbol": "MLCF",
        "manifest": "config/mlcf_official_intake_manifest.json",
        "policy": {
            "local_originals_only": True,
            "manifest_hash_required": True,
            "native_text_geometry_only": True,
            "no_network": True,
            "no_ocr": True,
            "audit_only": True,
            "financial_facts_emitted": False,
            "coverage_changed": False,
            "case_changed": False,
            "promotion_allowed": False,
        },
        "documents": docs,
        "summary": {
            "documents_reviewed": len(docs),
            "parser_entry_candidates": len(docs),
            "facts": [],
        },
        "generated_at": generated_at,
        "_meta": {
            "generator_version": "mlcf_native_text_statement_review_v1",
            "artifact_path": "state/company_intel/mlcf_native_text_statement_review_receipt.json",
            "generated_at": generated_at,
            "timestamp_semantics": {
                "generated_at": "receipt generation time only; not a source-effective or source-published time"
            }
        },
    }


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
