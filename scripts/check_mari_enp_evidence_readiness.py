"""Focused checks for the retained MARI E&P evidence-readiness audit."""
from __future__ import annotations

import json
import math
from pathlib import Path

import build_mari_enp_evidence_readiness as builder


def fail(message: str) -> None:
    raise AssertionError(message)


def check(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        fail(f"{name}: {detail}" if detail else name)


def walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = builder.build_manifest(root)
    check("schema version", manifest["schema_version"] == "mari_enp_evidence_readiness_v1")
    check("symbol and event identity",
          manifest["symbol"] == "MARI"
          and manifest["event"]["event_id"] == builder.EVENT_ID
          and manifest["event"]["document_id"] == "psx:265594")
    event_evidence = manifest["event"]["evidence"]
    check("target event excerpt is exact hash/page backed",
          len(event_evidence) == 1
          and manifest["event"]["exact_hash_page_backed_evidence_count"] == 1
          and all(row["evidence_class"] == "exact_hash_page_backed"
                  and row["content_sha256"]
                  and row["page"] is not None
                  for row in event_evidence))
    check("event remains observed only",
          manifest["event"]["status"] == "observed_only"
          and manifest["event"]["numeric_facts_retained"] is False)
    check("event source ids",
          {row["document_id"] for row in event_evidence} == {"psx:265594"}
          and all(row["event_id"] == builder.EVENT_ID for row in event_evidence))

    annual = manifest["financial_history"]["annual"]
    check("five annual slots", len(annual["periods"]) == 5 and annual["required_count"] == 5)
    check("annual slots are latest five fiscal ends",
          [row["period_end"] for row in annual["periods"]] == builder.ANNUAL_PERIODS)
    check("annual financial gate blocked",
          annual["status"] == "blocked" and annual["model_ready_count"] == 0)
    annual_status = {row["period_end"]: row["status"] for row in annual["periods"]}
    check("annual status distinctions",
          annual_status == {
              "2026-06-30": "metadata_lead",
              "2025-06-30": "metadata_lead",
              "2024-06-30": "audit_only_or_quarantined",
              "2023-06-30": "audit_only_or_quarantined",
              "2022-06-30": "unavailable",
          })
    check("annual facts carry retained hashes/pages",
          all(
              all(fact["content_sha256"] and fact["page"] is not None
                  and fact["evidence_class"] == "exact_hash_page_backed"
                  for fact in row["facts"])
              for row in annual["periods"]
              if row["facts"]
          ))
    check("annual values are never model-ready",
          all(row["model_ready_metrics"] == [] for row in annual["periods"]))

    quarterly = manifest["financial_history"]["quarterly"]
    check("eight quarter slots", len(quarterly["periods"]) == 8 and quarterly["required_count"] == 8)
    check("quarter slots are deterministic",
          [row["period_end"] for row in quarterly["periods"]] == builder.QUARTER_PERIODS)
    check("quarterly financial gate blocked",
          quarterly["status"] == "blocked" and quarterly["model_ready_count"] == 0)
    quarter_status = {row["period_end"]: row["status"] for row in quarterly["periods"]}
    check("quarter status distinguishes metadata from unavailable",
          quarter_status == {
              "2024-09-30": "unavailable",
              "2024-12-31": "unavailable",
              "2025-03-31": "unavailable",
              "2025-06-30": "unavailable",
              "2025-09-30": "metadata_lead",
              "2025-12-31": "metadata_lead",
              "2026-03-31": "metadata_lead",
              "2026-06-30": "unavailable",
          })
    check("quarter rows contain no numeric facts",
          all(row["facts"] == [] for row in quarterly["periods"]))

    shares = manifest["share_count"]
    check("share count metadata lead only",
          shares["status"] == "metadata_lead"
          and shares["value"] == 1200000000.0
          and shares["source"]["page"] is None
          and shares["source"]["content_sha256"] is None)
    check("share count source retained",
          shares["source"]["path"] == "state/fundamentals.json"
          and shares["source"]["url"] == "https://stockanalysis.com/quote/psx/MARI/")

    operands = manifest["ep_operands"]
    check("E&P operands blocked", operands["status"] == "blocked_missing_numeric_operands")
    operand_status = {item["operand"]: item["status"] for item in operands["items"]}
    operator = next(item for item in operands["items"] if item["operand"] == "operator_status")
    check("only target qualitative block lead observed; operator remains missing",
          operand_status["block_identity"] == "observed_text_only"
          and operand_status["operator_status"] == "unavailable"
          and operator["value"] is None
          and operator["evidence_refs"] == []
          and all(
              status == "unavailable"
              for operand, status in operand_status.items()
              if operand not in {"block_identity"}
          ))
    block = next(item for item in operands["items"] if item["operand"] == "block_identity")
    check("block identity binds target document only",
          {ref["document_id"] for ref in block["evidence_refs"]} == {"psx:265594"}
          and all(ref["event_id"] == builder.EVENT_ID for ref in block["evidence_refs"]))
    check("no numeric E&P values retained",
          all(item["value"] is None or item["status"] == "observed_text_only"
              for item in operands["items"]))

    activation = manifest["activation"]
    check("all downstream activation gates blocked",
          activation["status"] == "blocked"
          and activation["kernel_activated"] is False
          and activation["forecast_activated"] is False
          and activation["valuation_activated"] is False
          and activation["market_expectations_activated"] is False)
    check("highest leverage next action",
          manifest["next_evidence_action"]["priority"] == "highest_leverage"
          and manifest["next_evidence_action"]["status"] == "needs_owner_approval"
          and "265594" in manifest["next_evidence_action"]["action"]
          and "260446" not in manifest["next_evidence_action"]["action"]
          and "operator status" in manifest["next_evidence_action"]["why"].lower())

    repeat = builder.build_manifest(root)
    check("deterministic rebuild",
          json.dumps(manifest, sort_keys=True) == json.dumps(repeat, sort_keys=True))
    for key, value in walk(manifest):
        if isinstance(value, float) and not math.isfinite(value):
            fail(f"non-finite value at {key}")
    text = json.dumps(manifest, sort_keys=True).lower()
    for phrase in ("buy", "sell", "accumulate", "target price", "price target", "you should"):
        check(f"no advice phrase {phrase}", phrase not in text)
    print("mari enp evidence readiness: PASS (34 checks)")


if __name__ == "__main__":
    main()
