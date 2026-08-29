#!/usr/bin/env python3
"""Independent offline checks for exact-ID company document restaging."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import reprocess_company_documents as r


class FakeResponse:
    def __init__(self, status_code: int, body: bytes = b"", headers: dict[str, str] | None = None,
                 url: str | None = None) -> None:
        self.status_code = status_code
        self.body = body
        self.content = body
        self.headers = headers or {}
        self.url = url

    def iter_content(self, chunk_size: int = 65536):
        for i in range(0, len(self.body), chunk_size):
            yield self.body[i:i + chunk_size]


class FakeTransport:
    def __init__(self, responses: dict[str, list[FakeResponse] | FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def get(self, url: str, **_: Any) -> FakeResponse:
        self.calls.append(url)
        found = self.responses[url]
        if isinstance(found, list):
            if not found:
                raise AssertionError(f"no fake response left for {url}")
            return found.pop(0)
        return found


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")


def _seed_canonical_state(root: Path, doc_ids: list[str]) -> None:
    state = root / "state"
    pilot = [
        "FFC", "UBL", "MLCF", "DGKC", "FCCL", "LUCK", "HBL", "MCB", "MEBL", "NBP",
        "OGDC", "PPL", "PSO", "ENGROH", "EFERT", "BAHL", "SYS", "TRG", "NML", "PRL",
    ]
    profiles = {"pilot": {"symbols": pilot}, "tickers": {
        sym: {"symbol": sym, "source_url": f"https://dps.psx.com.pk/company/{sym}",
              "business_description": f"{sym} fixture"} for sym in pilot
    }}
    _write_json(state / "company_profiles.json", profiles)
    _write_json(state / "company_documents.json", {"schema_version": 1, "documents": {
        "existing": {"status": "ready", "content_sha256": "abc", "tickers": ["FFC"], "facts": []}
    }})
    _write_json(state / "company_financial_series.json", {"schema_version": 1, "tickers": {
        sym: {"ticker": sym, "facts": [{"series_id": f"series_{sym.lower()}_fixture",
                                        "ticker": sym, "metric": "revenue", "line": "revenue",
                                        "period_end": "2025-12-31", "period_type": "annual",
                                        "document_id": "existing", "content_sha256": "abc",
                                        "source_url": "https://dps.psx.com.pk/download/document/1.pdf",
                                        "evidence": [{"page": 1, "text": "fixture"}],
                                        "parser_version": r.PARSER_VERSION, "readiness": "model_loadable"}]}
        for sym in pilot[:12]
    }})
    _write_json(state / "company_intel" / "financial_model_inputs.json", {
        "schema_version": 1, "pilot_symbols": pilot, "companies": {sym: {"status": "fixture"} for sym in pilot}
    })
    _write_json(state / "company_intel" / "financial_evidence_reconciliation.json", {
        "schema_version": 1, "pilot_symbols": pilot, "companies": {sym: {"status": "fixture"} for sym in pilot}
    })
    _write_json(state / "company_intel" / "financial_truth_qualification.json", {
        "schema_version": 1, "pilot_symbols": pilot, "companies": {sym: {"status": "red"} for sym in pilot}
    })
    for name in ("financial_forecasts", "formal_valuations", "market_expectations"):
        _write_json(state / "company_intel" / f"{name}.json", {
            "schema_version": 1, "pilot_symbols": pilot, "companies": {sym: {"status": "stale"} for sym in pilot}
        })
    _write_json(root / "ci_slice.json", {"meta": {"count": 20}, "tickers": [{"symbol": sym} for sym in pilot]})
    _write_json(state / "company_event_ledger.json", {"companies": {}})
    _write_json(state / "company_intel" / "source_registry.json", {"tickers": {sym: {"status": "ok"} for sym in pilot}})
    _write_json(state / "document_synthesis_queue.json", {"queue": [], "history": []})


def _pdf(text: str, pages: int = 1, encrypt: bool = False) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for idx in range(pages):
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), f"{text} page {idx + 1}")
    if encrypt:
        data = doc.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="owner",
            user_pw="user",
            permissions=0,
        )
    else:
        data = doc.tobytes()
    doc.close()
    return data


def _statement_pdf() -> bytes:
    """Real one-page positioned PDF for the scoped restage integration seam."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    rows = [
        (50, 70, "Consolidated statement of profit or loss"),
        (50, 90, "PKR in million"),
        (170, 115, "Year ended"),
        (140, 140, "2025                    2024"),
        (50, 165, "Revenue                 300                    250     PKR in million"),
        (50, 190, "Profit after tax attributable     45                     40     PKR in million"),
        (50, 215, "Earnings per share          3.0                    2.5     PKR in million"),
    ]
    for x, y, text in rows:
        page.insert_text((x, y), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def _series_fact(doc_id: str, content_sha: str, line: str, period_end: str, raw: str,
                 normalized: float, *, revision: str | None = None,
                 readiness: str = "model_loadable") -> dict[str, Any]:
    unit = "PKR/share" if line == "basic_eps" else "PKR"
    multiplier = 1 if line == "basic_eps" else 1_000_000
    return {
        "series_id": f"fixture_{doc_id.replace(':', '_')}_{line}_{period_end}_{revision or 'none'}",
        "ticker": "MLCF",
        "metric": line,
        "line": line,
        "parser_version": r.PARSER_VERSION,
        "parser_revision": revision,
        "readiness": readiness,
        "period_end": period_end,
        "period_type": "annual",
        "duration_months": 12,
        "consolidation": "consolidated",
        "currency": "PKR",
        "statement_type": "income_statement",
        "unit": unit,
        "unit_multiplier": multiplier,
        "raw_value": raw,
        "normalized_value": normalized,
        "available_on": "2024-02-01" if period_end.startswith("2023") else "2026-01-01",
        "published_at": "2026-01-01T09:00:00+05:00",
        "document_id": doc_id,
        "fact_id": f"fact_{doc_id.replace(':', '_')}_{line}_{period_end}",
        "content_sha256": content_sha,
        "source_url": "https://dps.psx.com.pk/download/document/111.pdf",
        "evidence": [{"page": 1, "text": f"{line} {raw}", "source_url": "https://dps.psx.com.pk/download/document/111.pdf"}],
        "quality_flags": [],
    }


def _fixture(root: Path, doc_ids: list[str], *, hashes: dict[str, str] | None = None,
             bad_row: dict[str, Any] | None = None, full_canonical: bool = False) -> Path:
    state = root / "state"
    if full_canonical:
        _seed_canonical_state(root, doc_ids)
    else:
        pilot = ["FFC", "UBL", "MLCF"]
        _write_json(state / "company_profiles.json", {"pilot": {"symbols": pilot}})
    docs = {}
    for doc_id in doc_ids:
        numeric = doc_id.split(":", 1)[1]
        row = {
            "id": doc_id,
            "hash": doc_id,
            "source": "PSX DPS",
            "source_type": "filing",
            "doc_type": "financial_results",
            "date": "2026-08-01",
            "published_at": "2026-08-01T09:00:00+05:00",
            "tickers": ["FFC"],
            "company_name": "Fauji Fertilizer Company Limited",
            "title": "FFC Financial Results for the quarter ended June 30 2026",
            "digest": "FFC Financial Results for the quarter ended June 30 2026",
            "url": f"https://dps.psx.com.pk/download/document/{numeric}.pdf",
            "official_document_id": numeric,
        }
        if hashes and doc_id in hashes:
            row["content_sha256"] = hashes[doc_id]
        if bad_row and doc_id == doc_ids[0]:
            row.update(bad_row)
        docs[doc_id] = row
    _write_json(state / "research_index.json", {"schema_version": 1, "documents": docs})
    _write_json(state / "document_synthesis_queue.json", {"do_not": "touch"})
    _write_json(state / "company_intel" / "cursors.json", {"do_not": "touch"})
    manifest = root / "allow.json"
    _write_json(manifest, {"document_ids": doc_ids, "documents": {
        doc_id: {
            "symbol": "FFC",
            "company_name": "Fauji Fertilizer Company Limited",
            "expected_title_pattern": "Financial Results.*June 30 2026",
            "period": "2026-06-30",
        }
        for doc_id in doc_ids
    }})
    return manifest


def _run(root: Path, doc_ids: list[str], bodies: dict[str, bytes], *, manifest: Path,
         consume: bool = False, _consumer=None, cache_root: Path | None = None,
         _model_builder=None, _reconciliation_builder=None, _truth_builder=None,
         _formal_builder=None, _completion_matrix_builder=None,
         _ci_builder=None, _checker=None) -> tuple[dict[str, Any], FakeTransport]:
    responses = {}
    for doc_id, body in bodies.items():
        numeric = doc_id.split(":", 1)[1]
        url = f"https://dps.psx.com.pk/download/document/{numeric}.pdf"
        responses[url] = FakeResponse(200, body, {
            "Content-Type": "application/pdf",
            "Content-Length": str(len(body)),
        }, url)
    transport = FakeTransport(responses)
    result = r.run_reprocess(
        doc_ids,
        root=cache_root or root,
        state_root=root / "state",
        allowlist_manifest=manifest,
        transport=transport,
        consume=consume,
        _consumer=_consumer,
        receipts_path=root / "state" / "company_intel" / "reprocess_receipts.json",
        expected_allowlist=frozenset(doc_ids),
        ci_slice_path=root / "ci_slice.json",
        _model_builder=_model_builder,
        _reconciliation_builder=_reconciliation_builder,
        _truth_builder=_truth_builder,
        _formal_builder=_formal_builder,
        _completion_matrix_builder=_completion_matrix_builder,
        _ci_builder=_ci_builder,
        _checker=_checker,
    )
    return result, transport


def _receipt_text(root: Path) -> str:
    path = root / "state" / "company_intel" / "reprocess_receipts.json"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _assert_diagnostic_metadata_only(value: Any) -> None:
    forbidden_keys = {"text", "raw_text", "raw_value", "value", "path", "local_path", "words", "secret"}
    forbidden_fragments = ("Financial statements revenue", "%PDF", ".cache")
    if isinstance(value, dict):
        for key, item in value.items():
            assert key not in forbidden_keys, f"diagnostic leaked forbidden key: {key}"
            _assert_diagnostic_metadata_only(item)
    elif isinstance(value, list):
        for item in value:
            _assert_diagnostic_metadata_only(item)
    elif isinstance(value, str):
        assert not any(fragment in value for fragment in forbidden_fragments), value


def _good_builders(root: Path):
    def model_builder() -> None:
        pilot = json.loads((root / "state" / "company_profiles.json").read_text(encoding="utf-8"))["pilot"]["symbols"]
        _write_json(root / "state" / "company_intel" / "financial_model_inputs.json", {
            "schema_version": 1,
            "pilot_symbols": pilot,
            "companies": {sym: {"status": "fixture"} for sym in pilot},
        })

    def reconciliation_builder() -> None:
        pilot = json.loads((root / "state" / "company_profiles.json").read_text(encoding="utf-8"))["pilot"]["symbols"]
        model = json.loads((root / "state" / "company_intel" / "financial_model_inputs.json").read_text(encoding="utf-8"))
        _write_json(root / "state" / "company_intel" / "financial_evidence_reconciliation.json", {
            "schema_version": 1,
            "pilot_symbols": pilot,
            "companies": {sym: {"status": "reconciled", "model_status": (model.get("companies") or {}).get(sym, {}).get("status")} for sym in pilot},
        })

    def truth_builder() -> None:
        pilot = json.loads((root / "state" / "company_profiles.json").read_text(encoding="utf-8"))["pilot"]["symbols"]
        reconciliation = json.loads((root / "state" / "company_intel" / "financial_evidence_reconciliation.json").read_text(encoding="utf-8"))
        _write_json(root / "state" / "company_intel" / "financial_truth_qualification.json", {
            "schema_version": 1,
            "pilot_symbols": pilot,
            "companies": {sym: {"status": "qualified", "from_reconciliation": (reconciliation.get("companies") or {}).get(sym, {}).get("status")} for sym in pilot},
        })

    def formal_builder() -> None:
        pilot = json.loads((root / "state" / "company_profiles.json").read_text(encoding="utf-8"))["pilot"]["symbols"]
        truth = json.loads((root / "state" / "company_intel" / "financial_truth_qualification.json").read_text(encoding="utf-8"))
        for name in ("financial_forecasts", "formal_valuations", "market_expectations"):
            _write_json(root / "state" / "company_intel" / f"{name}.json", {
                "schema_version": 1,
                "pilot_symbols": pilot,
                "companies": {sym: {"status": "blocked_pending_owner_approved_assumptions", "truth_status": (truth.get("companies") or {}).get(sym, {}).get("status")} for sym in pilot},
            })

    def completion_matrix_builder() -> None:
        pilot = json.loads((root / "state" / "company_profiles.json").read_text(encoding="utf-8"))["pilot"]["symbols"]
        truth = json.loads((root / "state" / "company_intel" / "financial_truth_qualification.json").read_text(encoding="utf-8"))
        _write_json(root / "state" / "company_intel" / "completion_matrix.json", {
            "schema_version": 2,
            "pilot_symbols": pilot,
            "companies": {sym: {"truth_status": (truth.get("companies") or {}).get(sym, {}).get("status")} for sym in pilot},
        })

    def ci_builder() -> None:
        pilot = json.loads((root / "state" / "company_profiles.json").read_text(encoding="utf-8"))["pilot"]["symbols"]
        truth = json.loads((root / "state" / "company_intel" / "financial_truth_qualification.json").read_text(encoding="utf-8"))
        valuations = json.loads((root / "state" / "company_intel" / "formal_valuations.json").read_text(encoding="utf-8"))
        completion = json.loads((root / "state" / "company_intel" / "completion_matrix.json").read_text(encoding="utf-8"))
        _write_json(root / "ci_slice.json", {"meta": {"count": len(pilot)}, "tickers": [
            {"symbol": sym,
             "financial_truth_qualification": (truth.get("companies") or {}).get(sym),
             "formal_valuations": (valuations.get("companies") or {}).get(sym),
             "completion_matrix": (completion.get("companies") or {}).get(sym)}
            for sym in pilot
        ]})

    return model_builder, reconciliation_builder, truth_builder, formal_builder, completion_matrix_builder, ci_builder, lambda _name: None


def _bad_zero_model_builder(root: Path):
    def model_builder() -> None:
        pilot = json.loads((root / "state" / "company_profiles.json").read_text(encoding="utf-8"))["pilot"]["symbols"]
        _write_json(root / "state" / "company_intel" / "financial_model_inputs.json", {
            "schema_version": 1,
            "pilot_symbols": pilot,
            "companies": {},
        })

    return model_builder


def _assert_unsafe(root: Path, doc_ids: list[str], *, bad_row: dict[str, Any] | None = None) -> None:
    manifest = _fixture(root, ["psx:111"], bad_row=bad_row)
    try:
        r.run_reprocess(doc_ids, root=root, state_root=root / "state", allowlist_manifest=manifest,
                        transport=FakeTransport({}), expected_allowlist=frozenset(["psx:111"]))
    except r.UnsafeInput:
        return
    raise AssertionError(f"unsafe input accepted: {doc_ids} {bad_row}")


def _verified_fixture(root: Path, revision: str | None) -> list[dict[str, str]]:
    fact = {
        "ticker": "FFC",
        "document_id": "psx:111",
        "content_sha256": "f" * 64,
        "parser_version": r.PARSER_VERSION,
        "metric": "revenue",
    }
    if revision is not None:
        fact["parser_revision"] = revision
    return _verified_facts(root, [fact])


def _verified_facts(root: Path, facts: list[dict[str, Any]]) -> list[dict[str, str]]:
    state = root / "state"
    _write_json(state / "company_documents.json", {"schema_version": 1, "documents": {
        "psx:111": {"status": "ready", "content_sha256": "f" * 64, "tickers": ["FFC"]}
    }})
    _write_json(state / "company_financial_series.json", {"schema_version": 1, "tickers": {
        "FFC": {"ticker": "FFC", "facts": facts}
    }})
    doc = r.VerifiedDocument(
        doc_id="psx:111",
        numeric_id="111",
        row={},
        url="https://dps.psx.com.pk/download/document/111.pdf",
        tickers=["FFC"],
    )
    fetched = r.FetchResult(
        body=b"%PDF-fixture",
        content_sha256="f" * 64,
        content_length=12,
        final_url="https://dps.psx.com.pk/download/document/111.pdf",
        content_type="application/pdf",
        page_count=1,
        normalized_chars=100,
    )
    return r._verified_commits(state, [(doc, fetched)])


def main() -> int:
    # Exact MLCF annual exception: four parser-sized ranges preserving source pages.
    mlcf_policy = r.OVERSIZED_CHUNK_POLICIES["psx:260032"]
    assert mlcf_policy["ranges"] == ((1, 120), (121, 240), (241, 360), (361, 401))
    assert sum(end - start + 1 for start, end in mlcf_policy["ranges"]) == 401
    assert mlcf_policy["content_sha256"] == "4fdfb4cbd2eee65576cbb89b43334ce0c09a7e5ffd573d5bf93b414029eba6d1"
    good_pdf = _pdf(
        "Consolidated financial statements for the period ended 2026-06-30\n"
        "Rupees in million\n"
        "Revenue 120\n"
        "Profit for the period 30\n"
        "Earnings per share 2\n"
        "Financial statements revenue profit assets cash flow equity notes",
        pages=2,
    )
    second_pdf = _pdf("Financial results deposits advances profit before tax earning per share", pages=2)
    good_sha = hashlib.sha256(good_pdf).hexdigest()

    with tempfile.TemporaryDirectory(prefix="henneth-reprocess-") as tmp:
        root = Path(tmp)
        repo_root = Path(__file__).resolve().parents[1]

        # The committed production manifest is exact: approved IDs only, no duplicates/invalid extras.
        prod_manifest = repo_root / "config" / "ci_reprocess_allowlist.json"
        approved = r.load_allowlist(prod_manifest)
        assert set(approved) == set(r.APPROVED_WAVE3_ALLOWLIST)
        resolved = r.resolve_documents(sorted(r.APPROVED_WAVE3_ALLOWLIST), repo_root / "state", approved)
        assert len(resolved) == len(r.APPROVED_WAVE3_ALLOWLIST)
        assert {doc.doc_id for doc in resolved} == set(r.APPROVED_WAVE3_ALLOWLIST)
        approved_example = sorted(r.APPROVED_WAVE3_ALLOWLIST)[0]
        for name, ids in {
            "extra": sorted(r.APPROVED_WAVE3_ALLOWLIST | {"psx:999999"}),
            "missing": sorted(set(r.APPROVED_WAVE3_ALLOWLIST) - {approved_example}),
            "duplicate": sorted(r.APPROVED_WAVE3_ALLOWLIST) + [approved_example],
            "invalid": sorted(r.APPROVED_WAVE3_ALLOWLIST)[:-1] + ["bad"],
        }.items():
            manifest = root / f"manifest_{name}.json"
            _write_json(manifest, {"schema_version": 1, "document_ids": ids, "documents": {}})
            try:
                r.load_allowlist(manifest)
            except r.UnsafeInput:
                pass
            else:
                raise AssertionError(f"invalid manifest accepted: {name}")

        # Each invocation remains capped at five exact IDs.
        try:
            r.validate_operator_ids([f"psx:{900000 + index}" for index in range(r.MAX_DOCUMENT_IDS + 1)])
        except r.UnsafeInput:
            pass
        else:
            raise AssertionError("six document IDs accepted in one invocation")

        # Unsafe operator forms are rejected before transport can exist.
        for bad in ([], ["psx:1"] * 6, ["psx:1", "psx:1"], ["*"], ["all"], ["psx:1-9"], ["FFC"],
                    ["https://dps.psx.com.pk/download/document/111.pdf"], ["fixture.pdf"], ["-"], [">out"]):
            _assert_unsafe(root / ("bad_" + str(abs(hash(str(bad))))), bad)

        # Retained index contract: exact allowlist, exact pilot, PSX DPS source, safe URL, financial type/title.
        cases = [
            {"tickers": ["NONPILOT"]},
            {"source": "Broker"},
            {"source_type": "broker"},
            {"doc_type": "board_meeting"},
            {"title": "Notice of Board Meeting"},
            {"title": "Financial Results REVOKED"},
            {"url": "http://dps.psx.com.pk/download/document/111.pdf"},
            {"url": "https://evil.test/download/document/111.pdf"},
            {"url": "https://dps.psx.com.pk/download/document/222.pdf"},
            {"url": "https://dps.psx.com.pk/download/document/111.pdf?x=1"},
        ]
        for i, bad_row in enumerate(cases):
            _assert_unsafe(root / f"bad_row_{i}", ["psx:111"], bad_row=bad_row)
        not_allowed = root / "not_allowed"
        _fixture(not_allowed, ["psx:111"])
        _write_json(not_allowed / "allow.json", {"document_ids": ["psx:222"], "documents": {
            "psx:222": {
                "symbol": "FFC", "company_name": "Fauji Fertilizer Company Limited",
                "expected_title_pattern": "Financial Results.*June 30 2026", "period": "2026-06-30",
            }
        }})
        try:
            r.run_reprocess(["psx:111"], root=not_allowed, state_root=not_allowed / "state",
                            allowlist_manifest=not_allowed / "allow.json", transport=FakeTransport({}),
                            expected_allowlist=frozenset(["psx:222"]))
        except r.UnsafeInput:
            pass
        else:
            raise AssertionError("non-allowlisted ID accepted")

        # Validation/stage-only writes no success receipt; only fixed durable consume can receipt.
        ok = root / "ok"
        manifest = _fixture(ok, ["psx:111", "psx:222"], full_canonical=True)
        good_model, good_reconcile, good_truth, good_formal, good_completion, good_ci, good_checker = _good_builders(ok)
        shared_before = {
            p: p.read_bytes()
            for p in [ok / "state" / "research_index.json", ok / "state" / "document_synthesis_queue.json",
                      ok / "state" / "company_intel" / "cursors.json"]
        }
        captured: dict[str, Any] = {}
        result, transport = _run(ok, ["psx:111", "psx:222"], {"psx:111": good_pdf, "psx:222": second_pdf},
                                 manifest=manifest)
        assert result["status"] == "staged"
        assert [row["status"] for row in result["results"]] == ["staged_validated", "staged_validated"]
        assert _receipt_text(ok) == ""
        capture_root = root / "registry_capture"
        capture_manifest = _fixture(capture_root, ["psx:111"], full_canonical=True)
        registry_seen: dict[str, Any] = {}
        try:
            _run(capture_root, ["psx:111"], {"psx:111": good_pdf}, manifest=capture_manifest,
                 _consumer=lambda registry, queue, _stage, _docs: (
                     registry_seen.update({
                         "registry": json.loads(registry.read_text(encoding="utf-8")),
                         "queue": json.loads(queue.read_text(encoding="utf-8")),
                     }) or {"status": "staged", "committed": []}
                 ))
        except RuntimeError:
            pass
        else:
            raise AssertionError("uncommitted registry capture was accepted")
        scoped_row = registry_seen["registry"]["documents"]["psx:111"]
        scoped_queue = registry_seen["queue"]["documents"][0]
        assert scoped_row["parser_version"] == r.PARSER_VERSION
        assert scoped_row["parser_revision"] == r.PARSER_REVISION
        assert scoped_queue["parser_version"] == r.PARSER_VERSION
        assert scoped_queue["parser_revision"] == r.PARSER_REVISION
        before_hash = hashlib.sha256((ok / "state" / "research_index.json").read_bytes()).hexdigest()
        repo_raw_reprocess = repo_root / ".cache" / "company_intel" / "raw" / "reprocess"
        repo_stage_reprocess = repo_root / ".cache" / "company_intel" / "reprocess"
        before_repo_raw = sorted(str(path) for path in repo_raw_reprocess.glob("*")) if repo_raw_reprocess.exists() else []
        before_repo_stage = sorted(str(path) for path in repo_stage_reprocess.glob("*")) if repo_stage_reprocess.exists() else []
        result, transport = _run(ok, ["psx:111", "psx:222"], {"psx:111": good_pdf, "psx:222": second_pdf},
                                 manifest=manifest, consume=True, cache_root=repo_root,
                                 _model_builder=good_model, _reconciliation_builder=good_reconcile,
                                 _truth_builder=good_truth, _formal_builder=good_formal,
                                 _completion_matrix_builder=good_completion,
                                 _ci_builder=good_ci, _checker=good_checker)
        assert result["status"] == "ok"
        assert set(row["status"] for row in result["results"]).issubset({"committed", "processed_unsupported"})
        assert not any((ok / ".cache" / "company_intel" / "raw" / "reprocess").glob("*"))
        assert not any((ok / ".cache" / "company_intel" / "reprocess").glob("*"))
        after_repo_raw = sorted(str(path) for path in repo_raw_reprocess.glob("*")) if repo_raw_reprocess.exists() else []
        after_repo_stage = sorted(str(path) for path in repo_stage_reprocess.glob("*")) if repo_stage_reprocess.exists() else []
        assert after_repo_raw == before_repo_raw
        assert after_repo_stage == before_repo_stage
        docs_payload = json.loads((ok / "state" / "company_documents.json").read_text(encoding="utf-8"))
        for doc_id in ["psx:111", "psx:222"]:
            assert docs_payload["documents"][doc_id]["content_sha256"]
        assert (ok / "state" / "company_financial_series.json").exists(), "canonical durable output was cleaned"
        assert (ok / "state" / "company_intel" / "financial_model_inputs.json").exists()
        assert hashlib.sha256((ok / "state" / "research_index.json").read_bytes()).hexdigest() == before_hash
        for p, before in shared_before.items():
            if p.name == "research_index.json":
                assert p.read_bytes() == before, f"shared registry changed: {p}"
        receipt = json.loads(_receipt_text(ok))
        assert len(receipt["receipts"]) == 2
        assert set(row["status"] for row in receipt["receipts"]).issubset({"success", "processed_unsupported"})
        assert {row.get("parser_revision") for row in receipt["receipts"]} == {r.PARSER_REVISION}
        receipt_blob = json.dumps(receipt)
        assert ".cache" not in receipt_blob and str(ok) not in receipt_blob
        assert "Financial statements revenue" not in receipt_blob and "%PDF" not in receipt_blob

        # Genuine temp-root integration: scoped inputs feed the real document-intelligence
        # owner, verified commits inspect its durable temp outputs, and model inputs are
        # built by the real builder redirected to the temp state only.
        import build_financial_model_inputs as bfmi
        import document_intelligence as di
        import document_queue as dq

        real = root / "real_temp_root"
        _seed_canonical_state(real, ["psx:111"])
        temp_state = real / "state"
        _write_json(temp_state / "sectors.json", {"tickers": {"MLCF": {"sector": "Cement"}}})
        sentinel = b'{"schema_version":1,"receipts":[{"sentinel":true}]}'
        _write_json(temp_state / "company_brief_receipts.json", {"schema_version": 1, "receipts": [{"sentinel": True}]})
        sentinel = (temp_state / "company_brief_receipts.json").read_bytes()
        statement_pdf = _statement_pdf()
        statement_sha = hashlib.sha256(statement_pdf).hexdigest()
        seed_facts = [
            _series_fact("psx:seed2023", "3" * 64, "revenue", "2023-12-31", "200", 200_000_000.0,
                         revision=r.PARSER_REVISION),
            _series_fact("psx:seed2023", "3" * 64, "profit_after_tax_attributable", "2023-12-31", "30",
                         30_000_000.0, revision=r.PARSER_REVISION),
            _series_fact("psx:seed2023", "3" * 64, "basic_eps", "2023-12-31", "2.0", 2.0,
                         revision=r.PARSER_REVISION),
            _series_fact("psx:oldrev", "2" * 64, "revenue", "2025-12-31", "999", 999_000_000.0,
                         revision="block_geometry_v2"),
            _series_fact("psx:legacy", "1" * 64, "revenue", "2025-12-31", "888", 888_000_000.0,
                         revision="block_geometry_v2"),
        ]
        seed_facts[-1]["parser_version"] = "legacy_extractor_v1"
        _write_json(temp_state / "company_financial_series.json", {"schema_version": 1, "tickers": {
            "MLCF": {"ticker": "MLCF", "facts": seed_facts}
        }})
        doc_row = {
            "title": "MLCF Annual Financial Results for year ended 31.12.2025",
            "digest": "MLCF Annual Financial Results for year ended 31.12.2025",
            "source": "PSX DPS",
            "source_type": "filing",
            "doc_type": "financial_results",
            "published_at": "2026-01-01T09:00:00+05:00",
            "date": "2026-01-01",
            "company_name": "Maple Leaf Cement Factory Limited",
            "tickers": ["MLCF"],
        }
        verified_doc = r.VerifiedDocument(
            doc_id="psx:111",
            numeric_id="111",
            row=doc_row,
            url="https://dps.psx.com.pk/download/document/111.pdf",
            tickers=["MLCF"],
            content_sha256=statement_sha,
            manifest={
                "symbol": "MLCF",
                "company_name": "Maple Leaf Cement Factory Limited",
                "expected_title_pattern": "Annual Financial Results.*31.12.2025",
                "period": "2025-12-31",
            },
        )
        verified_fetch = r.FetchResult(
            body=statement_pdf,
            content_sha256=statement_sha,
            content_length=len(statement_pdf),
            final_url="https://dps.psx.com.pk/download/document/111.pdf",
            content_type="application/pdf",
            page_count=1,
            normalized_chars=200,
        )
        stage_dir = real / ".cache" / "company_intel" / "reprocess" / "fixture"
        raw_dir = real / ".cache" / "company_intel" / "raw" / "reprocess" / "fixture"
        stage_dir.mkdir(parents=True)
        raw_dir.mkdir(parents=True)
        registry_path, queue_path = r._write_scoped_inputs(stage_dir, raw_dir, [(verified_doc, verified_fetch)])
        scoped_registry = json.loads(registry_path.read_text(encoding="utf-8"))
        scoped_queue = json.loads(queue_path.read_text(encoding="utf-8"))
        assert list(scoped_registry["documents"]) == ["psx:111"]
        assert scoped_registry["documents"]["psx:111"]["period_end"] == "2025-12-31"
        assert scoped_registry["documents"]["psx:111"]["expected_symbol"] == "MLCF"
        assert scoped_queue["documents"] == [{
            "doc_id": "psx:111",
            "path": scoped_queue["documents"][0]["path"],
            "content_sha256": statement_sha,
            "parser_version": r.PARSER_VERSION,
            "parser_revision": r.PARSER_REVISION,
        }]

        original_di_root = di.ROOT
        original_di_build_queue = di.build_queue
        original_bfmi_state = bfmi.STATE
        original_bfmi_out = bfmi.OUT
        try:
            di.ROOT = real
            di.build_queue = lambda documents, path: dq.build_queue(
                documents, path=path, receipts_path=temp_state / "company_brief_receipts.json"
            )
            rc = di.run(
                index_path=registry_path,
                output_path=temp_state / "company_documents.json",
                extraction_queue_path=queue_path,
                ledger_path=temp_state / "company_event_ledger.json",
                queue_path=temp_state / "document_synthesis_queue.json",
                series_path=temp_state / "company_financial_series.json",
            )
            assert rc == 0
            committed = r._verified_commits(temp_state, [(verified_doc, verified_fetch)])
            assert committed == [{"doc_id": "psx:111", "content_sha256": statement_sha, "status": "success"}], committed
            bfmi.STATE = temp_state
            bfmi.OUT = temp_state / "company_intel" / "financial_model_inputs.json"
            model_payload = bfmi.build()
        finally:
            di.ROOT = original_di_root
            di.build_queue = original_di_build_queue
            bfmi.STATE = original_bfmi_state
            bfmi.OUT = original_bfmi_out

        assert (temp_state / "company_brief_receipts.json").read_bytes() == sentinel
        real_docs = json.loads((temp_state / "company_documents.json").read_text(encoding="utf-8"))
        real_doc = real_docs["documents"]["psx:111"]
        assert real_doc["status"] == "ready" and real_doc["content_sha256"] == statement_sha
        current_doc_facts = [f for f in real_doc["facts"] if f.get("parser_revision") == r.PARSER_REVISION]
        assert {f.get("line") for f in current_doc_facts} >= {
            "revenue", "profit_after_tax_attributable", "basic_eps"
        }
        assert all(f.get("readiness") == "model_loadable" and f.get("page") == 1
                   and f.get("source_url") == "https://dps.psx.com.pk/download/document/111.pdf"
                   and f.get("content_sha256") == statement_sha for f in current_doc_facts)
        queue_payload = json.loads((temp_state / "document_synthesis_queue.json").read_text(encoding="utf-8"))
        assert queue_payload["queue"][0]["approval_status"] == "pending"
        assert queue_payload["queue"][0]["training_mode"] is True
        series_payload = json.loads((temp_state / "company_financial_series.json").read_text(encoding="utf-8"))
        mlcf_facts = series_payload["tickers"]["MLCF"]["facts"]
        exact_current = {
            (f.get("line"), f.get("period_end"), f.get("raw_value"), f.get("normalized_value"),
             f.get("readiness"), f.get("parser_revision"), f.get("document_id"), f.get("content_sha256"),
             f.get("source_url"), (f.get("evidence") or [{}])[0].get("page"))
            for f in mlcf_facts
            if f.get("document_id") == "psx:111" and f.get("parser_revision") == r.PARSER_REVISION
        }
        assert {
            ("revenue", "2025-12-31", "300", 300_000_000.0, "model_loadable", r.PARSER_REVISION,
             "psx:111", statement_sha, "https://dps.psx.com.pk/download/document/111.pdf", 1),
            ("revenue", "2024-12-31", "250", 250_000_000.0, "model_loadable", r.PARSER_REVISION,
             "psx:111", statement_sha, "https://dps.psx.com.pk/download/document/111.pdf", 1),
            ("profit_after_tax_attributable", "2025-12-31", "45", 45_000_000.0, "model_loadable",
             r.PARSER_REVISION, "psx:111", statement_sha, "https://dps.psx.com.pk/download/document/111.pdf", 1),
            ("profit_after_tax_attributable", "2024-12-31", "40", 40_000_000.0, "model_loadable",
             r.PARSER_REVISION, "psx:111", statement_sha, "https://dps.psx.com.pk/download/document/111.pdf", 1),
            ("basic_eps", "2025-12-31", "3.0", 3.0, "model_loadable", r.PARSER_REVISION,
             "psx:111", statement_sha, "https://dps.psx.com.pk/download/document/111.pdf", 1),
            ("basic_eps", "2024-12-31", "2.5", 2.5, "model_loadable", r.PARSER_REVISION,
             "psx:111", statement_sha, "https://dps.psx.com.pk/download/document/111.pdf", 1),
        }.issubset(exact_current)
        stale_revision_rows = [f for f in mlcf_facts if f.get("document_id") == "psx:oldrev"]
        assert stale_revision_rows and all(f.get("parser_revision") == "block_geometry_v2" for f in stale_revision_rows)
        legacy_rows = [f for f in mlcf_facts if f.get("document_id") == "psx:legacy"]
        assert legacy_rows and all(f.get("readiness") == "audit_only"
                                   and "legacy_extractor_not_model_eligible" in (f.get("quality_flags") or [])
                                   for f in legacy_rows)
        mlcf_model = model_payload["companies"]["MLCF"]
        assert mlcf_model["status"] == "ready"
        assert (mlcf_model.get("model_registry") or {}).get("status") == "covered"
        assert (mlcf_model.get("model_adapter") or {}).get("status") == "available"
        assert (mlcf_model.get("model_adapter") or {}).get("selected_sector") == "CEMENT"
        assert (mlcf_model.get("downstream_status") or {}).get("forecast") == "blocked_pending_owner_approved_assumptions"
        assert (mlcf_model.get("downstream_status") or {}).get("valuation") == "blocked_pending_owner_approved_assumptions"
        assert {len(mlcf_model["observations"][line]) for line in
                ("revenue", "profit_after_tax_attributable", "basic_eps")} == {3}
        assert mlcf_model["derived"]["revenue_growth_pct"]
        observed_ids = json.dumps(mlcf_model["observations"])
        assert "psx:oldrev" not in observed_ids and "psx:legacy" not in observed_ids

        # Revision provenance: restage must never relabel legacy/no-revision facts as current success.
        legacy_fact = root / "legacy_fact_verify"
        assert _verified_fixture(legacy_fact, None) == [{
            "doc_id": "psx:111", "content_sha256": "f" * 64, "status": "processed_unsupported"
        }]
        current_fact = root / "current_fact_verify"
        assert _verified_fixture(current_fact, r.PARSER_REVISION) == [{
            "doc_id": "psx:111", "content_sha256": "f" * 64, "status": "success"
        }]
        mixed = root / "mixed_fact_verify"
        assert _verified_facts(mixed, [
            {"ticker": "FFC", "document_id": "psx:111", "content_sha256": "f" * 64,
             "parser_version": r.PARSER_VERSION, "metric": "revenue"},
            {"ticker": "FFC", "document_id": "psx:111", "content_sha256": "f" * 64,
             "parser_version": r.PARSER_VERSION, "parser_revision": r.PARSER_REVISION,
             "metric": "gross_profit"},
        ])[0]["status"] == "success"

        no_stamp = root / "no_stamp_consume"
        _fixture(no_stamp, ["psx:111"], full_canonical=True)
        no_stamp_model, no_stamp_reconcile, no_stamp_truth, no_stamp_formal, no_stamp_completion, no_stamp_ci, no_stamp_checker = _good_builders(no_stamp)
        expected_doc = r.VerifiedDocument(
            doc_id="psx:111",
            numeric_id="111",
            row={},
            url="https://dps.psx.com.pk/download/document/111.pdf",
            tickers=["FFC"],
        )
        expected_fetch = r.FetchResult(
            body=good_pdf,
            content_sha256=good_sha,
            content_length=len(good_pdf),
            final_url="https://dps.psx.com.pk/download/document/111.pdf",
            content_type="application/pdf",
            page_count=1,
            normalized_chars=100,
        )
        import document_intelligence
        original_run = document_intelligence.run

        def legacy_writer(*, output_path: Path, ledger_path: Path, queue_path: Path, series_path: Path, **_: Any) -> int:
            docs_payload = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {"documents": {}}
            docs_payload.setdefault("documents", {})["psx:111"] = {
                "status": "ready", "content_sha256": good_sha, "tickers": ["FFC"], "facts": [
                    {"parser_version": r.PARSER_VERSION, "document_id": "psx:111",
                     "content_sha256": good_sha, "metric": "revenue"}
                ]
            }
            _write_json(output_path, docs_payload)
            _write_json(ledger_path, {"companies": {}})
            _write_json(queue_path, {"queue": []})
            series_payload = json.loads(series_path.read_text(encoding="utf-8")) if series_path.exists() else {"tickers": {}}
            tickers = series_payload.setdefault("tickers", {})
            tickers.setdefault("FFC", {"ticker": "FFC", "facts": []}).setdefault("facts", []).append(
                {"parser_version": r.PARSER_VERSION, "document_id": "psx:111",
                 "content_sha256": good_sha, "metric": "revenue"}
            )
            _write_json(series_path, series_payload)
            return 0

        document_intelligence.run = legacy_writer
        try:
            committed = r.consume_canonical(no_stamp / "registry.json", no_stamp / "queue.json",
                                            no_stamp / "stage", [(expected_doc, expected_fetch)],
                                            state_root=no_stamp / "state", ci_slice_path=no_stamp / "ci_slice.json",
                                            model_builder=no_stamp_model, reconciliation_builder=no_stamp_reconcile,
                                            truth_builder=no_stamp_truth, formal_builder=no_stamp_formal,
                                            completion_matrix_builder=no_stamp_completion, ci_builder=no_stamp_ci,
                                            checker=no_stamp_checker)
        finally:
            document_intelligence.run = original_run
        assert committed["processed"][0]["status"] == "processed_unsupported"
        retained_fact = json.loads((no_stamp / "state" / "company_financial_series.json").read_text(encoding="utf-8"))["tickers"]["FFC"]["facts"][0]
        assert retained_fact.get("parser_revision") is None, "canonical consumer relabeled a legacy fact"

        # Active canonical transactions run full preflight without recursively invoking this self-check.
        tx = root / "transaction_preflight_isolation"
        _fixture(tx, ["psx:111"], full_canonical=True)
        tx_model, tx_reconcile, tx_truth, tx_formal, tx_completion, tx_ci, _ = _good_builders(tx)

        def current_writer(*, output_path: Path, ledger_path: Path, queue_path: Path, series_path: Path, **_: Any) -> int:
            docs_payload = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {"documents": {}}
            docs_payload.setdefault("documents", {})["psx:111"] = {
                "status": "ready", "content_sha256": good_sha, "tickers": ["FFC"], "facts": [
                    {"parser_version": r.PARSER_VERSION, "parser_revision": r.PARSER_REVISION,
                     "document_id": "psx:111", "content_sha256": good_sha, "metric": "revenue"}
                ]
            }
            _write_json(output_path, docs_payload)
            _write_json(ledger_path, {"companies": {}})
            _write_json(queue_path, {"queue": []})
            series_payload = json.loads(series_path.read_text(encoding="utf-8")) if series_path.exists() else {"tickers": {}}
            facts = series_payload.setdefault("tickers", {}).setdefault("FFC", {"ticker": "FFC", "facts": []}).setdefault("facts", [])
            facts.append({"parser_version": r.PARSER_VERSION, "parser_revision": r.PARSER_REVISION,
                          "document_id": "psx:111", "content_sha256": good_sha, "metric": "revenue"})
            _write_json(series_path, series_payload)
            return 0

        class Completed:
            def __init__(self, returncode: int = 0, stdout: str = "ok") -> None:
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = ""

        checker_calls: list[tuple[str, str | None]] = []
        original_run = document_intelligence.run
        original_subprocess_run = r.subprocess.run

        def fake_checker_run(cmd, **kwargs):
            name = Path(str(cmd[-1])).name
            env = kwargs.get("env") or {}
            checker_calls.append((
                name,
                env.get("HENNETH_REPROCESS_TRANSACTION")
                or env.get("HENNETH_CI_PRODUCT_CONTRACTS_VERIFIED_BY_PREFLIGHT"),
            ))
            return Completed()

        document_intelligence.run = current_writer
        r.subprocess.run = fake_checker_run
        try:
            r.consume_canonical(tx / "registry.json", tx / "queue.json", tx / "stage",
                                [(expected_doc, expected_fetch)], state_root=tx / "state",
                                ci_slice_path=tx / "ci_slice.json",
                                model_builder=tx_model, reconciliation_builder=tx_reconcile,
                                truth_builder=tx_truth, formal_builder=tx_formal,
                                completion_matrix_builder=tx_completion, ci_builder=tx_ci)
        finally:
            document_intelligence.run = original_run
            r.subprocess.run = original_subprocess_run
        assert ("preflight.py", "1") in checker_calls, checker_calls
        assert ("check_ci_completion_matrix.py", "1") in checker_calls, checker_calls
        assert all(flag is None for name, flag in checker_calls if name not in {"check_ci_completion_matrix.py", "preflight.py"}), checker_calls
        assert [name for name, _ in checker_calls] == [
            "check_financial_model_inputs.py",
            "check_financial_evidence_reconciliation.py",
            "check_financial_truth_qualification.py",
            "check_formal_financial_engines.py",
            "check_ci_completion_matrix.py",
            "check_event_studies.py",
            "check_operating_intelligence.py",
            "preflight.py",
        ], checker_calls
        tx_slice = json.loads((tx / "ci_slice.json").read_text(encoding="utf-8"))
        assert {row["financial_truth_qualification"]["status"] for row in tx_slice["tickers"]} == {"qualified"}
        assert {row["formal_valuations"]["truth_status"] for row in tx_slice["tickers"]} == {"qualified"}

        # The default transaction finalizer must rebuild source products before the
        # Company Brain indexes their row metadata. This catches stale Brain refs
        # such as thesis_monitoring being rebuilt after company_brains.
        order_tx = root / "transaction_builder_order"
        _fixture(order_tx, ["psx:111"], full_canonical=True)
        order_model, order_reconcile, order_truth, order_formal, order_completion, _, _ = _good_builders(order_tx)
        builder_order: list[str] = []

        def record_builder(name: str, payload: dict[str, Any] | None = None):
            def build() -> dict[str, Any]:
                builder_order.append(name)
                if payload is not None:
                    _write_json(order_tx / "state" / "company_intel" / f"{name}.json", payload)
                return payload or {}
            return build

        def order_ci_builder() -> dict[str, Any]:
            builder_order.append("build_ci_slice")
            pilot = json.loads((order_tx / "state" / "company_profiles.json").read_text(encoding="utf-8"))["pilot"]["symbols"]
            _write_json(order_tx / "ci_slice.json", {"tickers": [{"symbol": sym} for sym in pilot]})
            return {}

        import build_ci_artifact_integrity
        import build_ci_monitoring
        import build_ci_slice
        import build_ci_work_routing_policy
        import build_company_brains
        import build_evidence_watchlist
        import build_guidance_contradictions
        import build_intelligence_confidence
        import build_management_delivery
        import build_signal_clusters
        import build_thesis_monitoring

        patch_targets = [
            (build_signal_clusters, "build", record_builder("build_signal_clusters")),
            (build_thesis_monitoring, "build", record_builder("build_thesis_monitoring")),
            (build_intelligence_confidence, "build", record_builder("build_intelligence_confidence")),
            (build_guidance_contradictions, "build", record_builder("build_guidance_contradictions")),
            (build_management_delivery, "build", record_builder("build_management_delivery")),
            (build_company_brains, "build", record_builder("build_company_brains")),
            (build_evidence_watchlist, "build", record_builder("build_evidence_watchlist")),
            (build_ci_monitoring, "build", record_builder("build_ci_monitoring")),
            (build_ci_work_routing_policy, "build", record_builder("build_ci_work_routing_policy")),
            (build_ci_slice, "build", order_ci_builder),
            (build_ci_artifact_integrity, "build", record_builder("build_ci_artifact_integrity")),
        ]
        originals = [(module, name, getattr(module, name)) for module, name, _ in patch_targets]
        document_intelligence.run = current_writer
        try:
            for module, name, replacement in patch_targets:
                setattr(module, name, replacement)
            r.consume_canonical(order_tx / "registry.json", order_tx / "queue.json", order_tx / "stage",
                                [(expected_doc, expected_fetch)], state_root=order_tx / "state",
                                ci_slice_path=order_tx / "ci_slice.json",
                                model_builder=order_model, reconciliation_builder=order_reconcile,
                                truth_builder=order_truth, formal_builder=order_formal,
                                completion_matrix_builder=order_completion, checker=lambda _name: None)
        finally:
            document_intelligence.run = original_run
            for module, name, original in originals:
                setattr(module, name, original)
        expected_order = [
            "build_signal_clusters",
            "build_thesis_monitoring",
            "build_intelligence_confidence",
            "build_guidance_contradictions",
            "build_management_delivery",
            "build_company_brains",
            "build_evidence_watchlist",
            "build_ci_monitoring",
            "build_ci_work_routing_policy",
            "build_ci_slice",
            "build_ci_artifact_integrity",
            "build_signal_clusters",
            "build_thesis_monitoring",
            "build_intelligence_confidence",
            "build_guidance_contradictions",
            "build_management_delivery",
            "build_company_brains",
            "build_evidence_watchlist",
            "build_ci_monitoring",
            "build_ci_work_routing_policy",
            "build_ci_slice",
            "build_ci_artifact_integrity",
        ]
        assert builder_order == expected_order, builder_order

        # Normal preflight still invokes the reprocess self-check; only the transaction-local flag skips it.
        import os
        import preflight
        old_env = os.environ.pop("HENNETH_REPROCESS_TRANSACTION", None)
        original_preflight_run = preflight.subprocess.run
        normal_calls: list[str] = []

        def fake_preflight_run(cmd, **_kwargs):
            normal_calls.append(Path(str(cmd[-1])).name)
            return Completed()

        preflight.subprocess.run = fake_preflight_run
        try:
            preflight.check_reprocess_documents()
            assert normal_calls == ["check_reprocess_company_documents.py"]
            os.environ["HENNETH_REPROCESS_TRANSACTION"] = "1"
            normal_calls.clear()
            preflight.check_reprocess_documents()
            assert normal_calls == []
        finally:
            preflight.subprocess.run = original_preflight_run
            if old_env is None:
                os.environ.pop("HENNETH_REPROCESS_TRANSACTION", None)
            else:
                os.environ["HENNETH_REPROCESS_TRANSACTION"] = old_env

        # A non-reprocess preflight failure still rolls back every canonical snapshot byte-for-byte.
        fail_tx = root / "transaction_preflight_failure"
        _fixture(fail_tx, ["psx:111"], full_canonical=True)
        fail_model, fail_reconcile, fail_truth, fail_formal, fail_completion, fail_ci, _ = _good_builders(fail_tx)
        before_docs = (fail_tx / "state" / "company_documents.json").read_bytes()
        before_model = (fail_tx / "state" / "company_intel" / "financial_model_inputs.json").read_bytes()
        before_slice = (fail_tx / "ci_slice.json").read_bytes()

        def failing_preflight_run(cmd, **kwargs):
            name = Path(str(cmd[-1])).name
            if name == "preflight.py":
                assert (kwargs.get("env") or {}).get("HENNETH_REPROCESS_TRANSACTION") == "1"
                return Completed(1, "forced non-reprocess preflight failure")
            return Completed()

        document_intelligence.run = current_writer
        r.subprocess.run = failing_preflight_run
        try:
            try:
                r.consume_canonical(fail_tx / "registry.json", fail_tx / "queue.json", fail_tx / "stage",
                                    [(expected_doc, expected_fetch)], state_root=fail_tx / "state",
                                    ci_slice_path=fail_tx / "ci_slice.json",
                                    model_builder=fail_model, reconciliation_builder=fail_reconcile,
                                    truth_builder=fail_truth, formal_builder=fail_formal,
                                    completion_matrix_builder=fail_completion, ci_builder=fail_ci)
            except r.ReprocessTransactionError as exc:
                assert exc.stage == "checker:preflight.py"
                assert exc.rolled_back is True
                diagnostic = exc.to_result("fixture-run")
                assert diagnostic["status"] == "transaction_failed"
                assert diagnostic["failure_stage"] == "checker:preflight.py"
                assert diagnostic["canonical_state_committed"] is False
                assert diagnostic["receipt_written"] is False
                assert "forced non-reprocess preflight failure" in str(exc)
            else:
                raise AssertionError("preflight failure did not abort transaction")
        finally:
            document_intelligence.run = original_run
            r.subprocess.run = original_subprocess_run
        assert (fail_tx / "state" / "company_documents.json").read_bytes() == before_docs
        assert (fail_tx / "state" / "company_intel" / "financial_model_inputs.json").read_bytes() == before_model
        assert (fail_tx / "ci_slice.json").read_bytes() == before_slice

        # Revision-aware idempotency: same hash+same revision skips; legacy no-revision receipt does not.
        idem = root / "idem"
        idem_manifest = _fixture(idem, ["psx:111"], hashes={"psx:111": good_sha}, full_canonical=True)
        idem_model, idem_reconcile, idem_truth, idem_formal, idem_completion, idem_ci, idem_checker = _good_builders(idem)
        _run(idem, ["psx:111"], {"psx:111": good_pdf}, manifest=idem_manifest, consume=True, cache_root=repo_root,
             _model_builder=idem_model, _reconciliation_builder=idem_reconcile,
             _truth_builder=idem_truth, _formal_builder=idem_formal,
             _completion_matrix_builder=idem_completion,
             _ci_builder=idem_ci, _checker=idem_checker)
        first_receipts = _receipt_text(idem)
        result, transport = _run(idem, ["psx:111"], {"psx:111": good_pdf}, manifest=idem_manifest)
        assert result["results"][0]["status"] == "skipped_idempotent"
        assert transport.calls == []
        assert _receipt_text(idem) == first_receipts
        current_receipts = json.loads(first_receipts)["receipts"]
        assert len(current_receipts) == 1 and current_receipts[0]["parser_revision"] == r.PARSER_REVISION

        legacy = root / "legacy_revision"
        legacy_manifest = _fixture(legacy, ["psx:111"], hashes={"psx:111": good_sha}, full_canonical=True)
        _write_json(legacy / "state" / "company_intel" / "reprocess_receipts.json", {
            "schema_version": 1,
            "receipts": [{
                "doc_id": "psx:111",
                "content_sha256": good_sha,
                "parser_version": r.PARSER_VERSION,
                "parser_revision": "block_geometry_v3",
                "status": "processed_unsupported",
            }],
        })
        legacy_model, legacy_reconcile, legacy_truth, legacy_formal, legacy_completion, legacy_ci, legacy_checker = _good_builders(legacy)
        result, transport = _run(legacy, ["psx:111"], {"psx:111": good_pdf}, manifest=legacy_manifest,
                                 consume=True, cache_root=repo_root,
                                 _model_builder=legacy_model, _reconciliation_builder=legacy_reconcile,
                                 _truth_builder=legacy_truth, _formal_builder=legacy_formal,
                                 _completion_matrix_builder=legacy_completion,
                                 _ci_builder=legacy_ci, _checker=legacy_checker)
        assert transport.calls, "legacy no-revision receipt incorrectly blocked new parser revision"
        receipts = json.loads(_receipt_text(legacy))["receipts"]
        assert len(receipts) == 2
        assert receipts[0].get("parser_revision") == "block_geometry_v3"
        assert receipts[1].get("parser_revision") == r.PARSER_REVISION
        result, transport = _run(legacy, ["psx:111"], {"psx:111": good_pdf}, manifest=legacy_manifest)
        assert result["results"][0]["status"] == "skipped_idempotent"
        assert transport.calls == []
        unknown = root / "unknown_hash"
        unknown_manifest = _fixture(unknown, ["psx:111"], full_canonical=True)
        unknown_model, unknown_reconcile, unknown_truth, unknown_formal, unknown_completion, unknown_ci, unknown_checker = _good_builders(unknown)
        _run(unknown, ["psx:111"], {"psx:111": good_pdf}, manifest=unknown_manifest, consume=True, cache_root=repo_root,
             _model_builder=unknown_model, _reconciliation_builder=unknown_reconcile,
             _truth_builder=unknown_truth, _formal_builder=unknown_formal,
             _completion_matrix_builder=unknown_completion,
             _ci_builder=unknown_ci, _checker=unknown_checker)
        result, transport = _run(unknown, ["psx:111"], {"psx:111": good_pdf}, manifest=unknown_manifest)
        assert result["results"][0]["status"] == "skipped_idempotent"
        assert transport.calls == [], "prior receipt hash did not short-circuit future network"
        assert _receipt_text(unknown)

        # Diagnostic mode deliberately bypasses same-revision receipts, writes no receipt/state,
        # emits bounded summaries only, and still uses exact manifest/transport gates.
        diag = root / "diagnose"
        diag_manifest = _fixture(diag, ["psx:111"], hashes={"psx:111": good_sha}, full_canonical=True)
        _write_json(diag / "state" / "company_intel" / "reprocess_receipts.json", {
            "schema_version": 1,
            "receipts": [{
                "doc_id": "psx:111",
                "content_sha256": good_sha,
                "parser_version": r.PARSER_VERSION,
                "parser_revision": r.PARSER_REVISION,
                "status": "processed_unsupported",
            }],
        })
        before_diag = {
            path: path.read_bytes()
            for path in [
                diag / "state" / "company_documents.json",
                diag / "state" / "company_financial_series.json",
                diag / "state" / "company_intel" / "financial_model_inputs.json",
                diag / "ci_slice.json",
                diag / "state" / "company_intel" / "reprocess_receipts.json",
            ]
        }
        result, transport = _run(diag, ["psx:111"], {"psx:111": good_pdf}, manifest=diag_manifest, consume=False)
        assert result["results"][0]["status"] == "skipped_idempotent" and transport.calls == []
        responses = {"https://dps.psx.com.pk/download/document/111.pdf": FakeResponse(
            200, good_pdf, {"Content-Type": "application/pdf", "Content-Length": str(len(good_pdf))},
            "https://dps.psx.com.pk/download/document/111.pdf")}
        transport = FakeTransport(responses)
        diag_result = r.run_reprocess(["psx:111"], root=diag, state_root=diag / "state",
                                      allowlist_manifest=diag_manifest, transport=transport,
                                      expected_allowlist=frozenset(["psx:111"]), diagnose=True,
                                      receipts_path=diag / "state" / "company_intel" / "reprocess_receipts.json")
        assert diag_result["mode"] == "diagnose" and diag_result["status"] == "ok"
        assert transport.calls, "diagnose mode incorrectly honored same-revision idempotency skip"
        for path, before in before_diag.items():
            assert path.read_bytes() == before, f"diagnose changed canonical/receipt file: {path}"
        assert not any((diag / ".cache" / "company_intel" / "raw" / "reprocess").glob("*"))
        assert not any((diag / ".cache" / "company_intel" / "reprocess").glob("*"))
        blob = json.dumps(diag_result)
        assert "Financial statements revenue" not in blob and "%PDF" not in blob and str(diag) not in blob
        assert '"words"' not in blob and '"path"' not in blob and ".cache" not in blob
        _assert_diagnostic_metadata_only(diag_result["results"][0]["diagnostic"])
        page_diag = diag_result["results"][0]["diagnostic"]["pages"][0]
        assert {"page", "duration_groups", "year_token_candidates", "year_headers", "rows",
                "reason_codes", "parser_decision"}.issubset(page_diag)
        for duration in page_diag["duration_groups"]:
            assert {"block", "line", "months", "bbox", "center_x"}.issubset(duration)
        assert len(page_diag["year_token_candidates"]) <= 16
        for candidate in page_diag["year_token_candidates"]:
            assert {"year", "x", "y", "block", "line"} == set(candidate)
        for row in page_diag["rows"]:
            assert len(row.get("nearby_numeric_bands") or []) <= 4
            for band in row.get("nearby_numeric_bands") or []:
                assert {"y_delta", "numeric_count", "numeric_x", "block", "line", "numeric_only"} == set(band)
                assert isinstance(band["numeric_only"], bool)
        try:
            r.run_reprocess(["psx:111"], root=diag, state_root=diag / "state",
                            allowlist_manifest=diag_manifest, transport=FakeTransport({}),
                            expected_allowlist=frozenset(["psx:111"]), consume=True, diagnose=True)
        except r.UnsafeInput:
            pass
        else:
            raise AssertionError("diagnose+consume accepted")
        diag_bad = root / "diagnose_bad"
        diag_bad_manifest = _fixture(diag_bad, ["psx:111"])
        out = r.run_reprocess(["psx:111"], root=diag_bad, state_root=diag_bad / "state",
                              allowlist_manifest=diag_bad_manifest,
                              transport=FakeTransport({"https://dps.psx.com.pk/download/document/111.pdf":
                                                      FakeResponse(503, b"", {"Content-Type": "application/pdf"})}),
                              expected_allowlist=frozenset(["psx:111"]), diagnose=True)
        assert out["status"] == "degraded" and out["results"][0]["reason"] == "http_status_503"
        diag_not_allowed = root / "diagnose_not_allowed"
        _fixture(diag_not_allowed, ["psx:111"])
        _write_json(diag_not_allowed / "allow.json", {"document_ids": ["psx:222"], "documents": {
            "psx:222": {"symbol": "FFC", "company_name": "Fauji Fertilizer Company Limited",
                         "expected_title_pattern": "Financial Results.*June 30 2026", "period": "2026-06-30"}
        }})
        try:
            r.run_reprocess(["psx:111"], root=diag_not_allowed, state_root=diag_not_allowed / "state",
                            allowlist_manifest=diag_not_allowed / "allow.json", transport=FakeTransport({}),
                            expected_allowlist=frozenset(["psx:222"]), diagnose=True)
        except r.UnsafeInput:
            pass
        else:
            raise AssertionError("diagnose accepted non-manifest ID")

        # Crash/retry: failed consumer leaves no receipt; retry appends once.
        crash = root / "crash"
        crash_manifest = _fixture(crash, ["psx:111"], full_canonical=True)

        def bad_consumer(_: Path, __: Path, ___: Path, ____: list) -> dict[str, Any]:
            raise RuntimeError("boom")

        try:
            _run(crash, ["psx:111"], {"psx:111": good_pdf}, manifest=crash_manifest, _consumer=bad_consumer)
        except RuntimeError:
            pass
        else:
            raise AssertionError("consumer failure was swallowed")
        assert _receipt_text(crash) == ""
        try:
            _run(crash, ["psx:111"], {"psx:111": good_pdf}, manifest=crash_manifest,
                 _consumer=lambda _a, _b, _c, _d: {"status": "staged", "committed": []})
        except RuntimeError:
            pass
        else:
            raise AssertionError("uncommitted consumer result was accepted")
        assert _receipt_text(crash) == ""
        crash_model, crash_reconcile, crash_truth, crash_formal, crash_completion, crash_ci, crash_checker = _good_builders(crash)
        _run(crash, ["psx:111"], {"psx:111": good_pdf}, manifest=crash_manifest, consume=True, cache_root=repo_root,
             _model_builder=crash_model, _reconciliation_builder=crash_reconcile,
             _truth_builder=crash_truth, _formal_builder=crash_formal,
             _completion_matrix_builder=crash_completion,
             _ci_builder=crash_ci, _checker=crash_checker)
        assert len(json.loads(_receipt_text(crash))["receipts"]) == 1

        zero_model = root / "zero_model"
        zero_manifest = _fixture(zero_model, ["psx:111"], full_canonical=True)
        before_model = (zero_model / "state" / "company_intel" / "financial_model_inputs.json").read_bytes()
        before_slice = (zero_model / "ci_slice.json").read_bytes()
        _, zero_reconcile, zero_truth, zero_formal, zero_completion, zero_ci, zero_checker = _good_builders(zero_model)
        try:
            _run(zero_model, ["psx:111"], {"psx:111": good_pdf}, manifest=zero_manifest,
                 consume=True, cache_root=repo_root,
                 _model_builder=_bad_zero_model_builder(zero_model),
                 _reconciliation_builder=zero_reconcile, _truth_builder=zero_truth,
                 _formal_builder=zero_formal, _completion_matrix_builder=zero_completion,
                 _ci_builder=zero_ci, _checker=zero_checker)
        except r.ReprocessTransactionError as exc:
            assert exc.stage == "validate_canonical_boundaries"
            assert exc.rolled_back is True
            assert exc.documents == [{
                "doc_id": "psx:111",
                "content_sha256": good_sha,
                "page_count": 2,
                "source_url": "https://dps.psx.com.pk/download/document/111.pdf",
                "receipt": "not_written_transaction_failed",
            }]
            diagnostic = exc.to_result()
            assert diagnostic["documents"][0]["receipt"] == "not_written_transaction_failed"
            assert diagnostic["receipt_written"] is False
        else:
            raise AssertionError("zero-company model output was committed")
        assert (zero_model / "state" / "company_intel" / "financial_model_inputs.json").read_bytes() == before_model
        assert (zero_model / "ci_slice.json").read_bytes() == before_slice
        assert _receipt_text(zero_model) == ""

        rollback = root / "rollback"
        rollback_manifest = _fixture(rollback, ["psx:111"], full_canonical=True)
        _write_json(rollback / "state" / "company_documents.json", {"schema_version": 1, "documents": {
            "sentinel": {"status": "ready", "content_sha256": "abc"}
        }})
        before_docs = (rollback / "state" / "company_documents.json").read_bytes()
        bad_registry = rollback / "registry.json"
        bad_queue = rollback / "queue.json"
        _write_json(bad_registry, {"documents": {"psx:111": {
            "doc_id": "psx:111", "id": "psx:111", "source": "PSX DPS", "source_type": "filing",
            "tickers": ["FFC"], "title": "FFC Financial Results", "source_url": "https://dps.psx.com.pk/download/document/111.pdf"
        }}})
        _write_json(bad_queue, {"documents": [{"doc_id": "psx:111", "path": str(rollback / "missing.pdf"),
                                              "content_sha256": good_sha}]})
        expected_doc = r.VerifiedDocument(
            doc_id="psx:111",
            numeric_id="111",
            row={},
            url="https://dps.psx.com.pk/download/document/111.pdf",
            tickers=["FFC"],
        )
        expected_fetch = r.FetchResult(
            body=good_pdf,
            content_sha256=good_sha,
            content_length=len(good_pdf),
            final_url="https://dps.psx.com.pk/download/document/111.pdf",
            content_type="application/pdf",
            page_count=1,
            normalized_chars=100,
        )
        try:
            r.consume_canonical(bad_registry, bad_queue, rollback / "stage",
                                [(expected_doc, expected_fetch)], state_root=rollback / "state")
        except RuntimeError:
            pass
        else:
            raise AssertionError("bad canonical consume did not fail")
        assert (rollback / "state" / "company_documents.json").read_bytes() == before_docs

        publish_fail = root / "publish_fail"
        publish_manifest = _fixture(publish_fail, ["psx:111"], full_canonical=True)
        _write_json(publish_fail / "state" / "company_documents.json", {"schema_version": 1, "documents": {
            "sentinel": {"status": "ready", "content_sha256": "abc"}
        }})
        _write_json(publish_fail / "state" / "company_event_ledger.json", {"sentinel": True})
        before_docs = (publish_fail / "state" / "company_documents.json").read_bytes()
        before_ledger = (publish_fail / "state" / "company_event_ledger.json").read_bytes()
        publish_model, publish_reconcile, publish_truth, publish_formal, publish_completion, publish_ci, publish_checker = _good_builders(publish_fail)
        original_replace = r._atomic_replace_file
        replace_count = {"n": 0}

        def fail_second(src: Path, dest: Path) -> None:
            replace_count["n"] += 1
            if replace_count["n"] == 2:
                raise RuntimeError("forced replace failure")
            original_replace(src, dest)

        r._atomic_replace_file = fail_second
        try:
            try:
                _run(publish_fail, ["psx:111"], {"psx:111": good_pdf},
                     manifest=publish_manifest, consume=True, cache_root=repo_root,
                     _model_builder=publish_model, _reconciliation_builder=publish_reconcile,
                     _truth_builder=publish_truth, _formal_builder=publish_formal,
                     _completion_matrix_builder=publish_completion,
                     _ci_builder=publish_ci, _checker=publish_checker)
            except RuntimeError:
                pass
            else:
                raise AssertionError("forced publish failure was swallowed")
        finally:
            r._atomic_replace_file = original_replace
        assert (publish_fail / "state" / "company_documents.json").read_bytes() == before_docs
        assert (publish_fail / "state" / "company_event_ledger.json").read_bytes() == before_ledger
        assert _receipt_text(publish_fail) == ""

        # Transport/content failures are per-ID degraded and still exit through a result object.
        degraded = root / "degraded"
        degraded_manifest = _fixture(degraded, ["psx:111", "psx:222"])
        responses = {
            "https://dps.psx.com.pk/download/document/111.pdf": FakeResponse(503, b"", {"Content-Type": "application/pdf"}),
            "https://dps.psx.com.pk/download/document/222.pdf": FakeResponse(200, second_pdf, {
                "Content-Type": "application/pdf", "Content-Length": str(len(second_pdf)),
            }, "https://dps.psx.com.pk/download/document/222.pdf"),
        }
        result = r.run_reprocess(["psx:111", "psx:222"], root=degraded, state_root=degraded / "state",
                                 allowlist_manifest=degraded_manifest, transport=FakeTransport(responses),
                                 expected_allowlist=frozenset(["psx:111", "psx:222"]))
        assert result["status"] == "degraded"
        assert [row["status"] for row in result["results"]] == ["degraded", "staged_validated"]
        assert _receipt_text(degraded) == ""

        # Redirect and URL identity enforcement.
        redirect = root / "redirect"
        redirect_manifest = _fixture(redirect, ["psx:111"])
        redirect_url = "https://dps.psx.com.pk/download/document/111.pdf"
        transport = FakeTransport({
            redirect_url: [
                FakeResponse(302, b"", {"Location": "/download/document/111.pdf"}),
                FakeResponse(200, good_pdf, {"Content-Type": "application/pdf",
                                             "Content-Length": str(len(good_pdf))}, redirect_url),
            ],
        })
        out = r.run_reprocess(["psx:111"], root=redirect, state_root=redirect / "state",
                              allowlist_manifest=redirect_manifest, transport=transport,
                              expected_allowlist=frozenset(["psx:111"]))
        assert out["results"][0]["status"] == "staged_validated"
        final_bad = root / "final_bad"
        final_bad_manifest = _fixture(final_bad, ["psx:111"])
        transport = FakeTransport({
            redirect_url: FakeResponse(200, good_pdf, {"Content-Type": "application/pdf",
                                                       "Content-Length": str(len(good_pdf))},
                                       "https://evil.test/download/document/111.pdf"),
        })
        out = r.run_reprocess(["psx:111"], root=final_bad, state_root=final_bad / "state",
                              allowlist_manifest=final_bad_manifest, transport=transport,
                              expected_allowlist=frozenset(["psx:111"]))
        assert out["status"] == "degraded"
        assert out["results"][0]["reason"] == "final_url_mismatch"
        redirect_loop = root / "redirect_loop"
        redirect_loop_manifest = _fixture(redirect_loop, ["psx:111"])
        transport = FakeTransport({
            redirect_url: FakeResponse(302, b"", {"Location": "/download/document/111.pdf"}),
        })
        out = r.run_reprocess(["psx:111"], root=redirect_loop, state_root=redirect_loop / "state",
                              allowlist_manifest=redirect_loop_manifest, transport=transport,
                              expected_allowlist=frozenset(["psx:111"]))
        assert out["results"][0]["reason"] == "redirect_cap_exceeded"
        for location in ("https://evil.test/download/document/111.pdf", "/download/document/222.pdf"):
            rr = root / ("redirect_bad_" + str(abs(hash(location))))
            rr_manifest = _fixture(rr, ["psx:111"])
            transport = FakeTransport({redirect_url: FakeResponse(302, b"", {"Location": location})})
            out = r.run_reprocess(["psx:111"], root=rr, state_root=rr / "state",
                                  allowlist_manifest=rr_manifest, transport=transport,
                                  expected_allowlist=frozenset(["psx:111"]))
            assert out["results"][0]["reason"] == "redirect_target_mismatch"

        # Caps, content type, magic, hash, encryption, pages, image-only.
        checks = [
            ("type", FakeResponse(200, good_pdf, {"Content-Type": "text/plain"}), "content_type_not_allowed"),
            ("declared", FakeResponse(200, b"", {"Content-Type": "application/pdf",
                                                 "Content-Length": str(r.MAX_FILE_BYTES + 1)}),
             "declared_file_cap_exceeded"),
            ("magic", FakeResponse(200, b"not a pdf", {"Content-Type": "application/pdf"}), "pdf_magic_mismatch"),
            ("encrypt", FakeResponse(200, _pdf("secret words " * 20, encrypt=True),
                                     {"Content-Type": "application/pdf"}), "encrypted_pdf"),
            ("pages", FakeResponse(200, _pdf("many words " * 20, pages=r.MAX_FILE_PAGES + 1),
                                   {"Content-Type": "application/pdf"}), "file_page_cap_exceeded"),
            ("image", FakeResponse(200, _pdf("", pages=1), {"Content-Type": "application/pdf"}),
             "unsupported_image_only"),
        ]
        for name, response, reason in checks:
            case = root / f"content_{name}"
            case_manifest = _fixture(case, ["psx:111"])
            transport = FakeTransport({"https://dps.psx.com.pk/download/document/111.pdf": response})
            out = r.run_reprocess(["psx:111"], root=case, state_root=case / "state",
                                  allowlist_manifest=case_manifest, transport=transport,
                                  expected_allowlist=frozenset(["psx:111"]))
            assert out["results"][0]["reason"] == reason, (name, out)
        stream = root / "stream_cap"
        stream_manifest = _fixture(stream, ["psx:111"])
        too_large_stream = b"%PDF-" + (b"x" * r.MAX_FILE_BYTES)
        out = r.run_reprocess(["psx:111"], root=stream, state_root=stream / "state",
                              allowlist_manifest=stream_manifest,
                              transport=FakeTransport({"https://dps.psx.com.pk/download/document/111.pdf":
                                                      FakeResponse(200, too_large_stream,
                                                                   {"Content-Type": "application/pdf"})}),
                              expected_allowlist=frozenset(["psx:111"]))
        assert out["results"][0]["reason"] == "stream_file_cap_exceeded"
        run_bytes = root / "run_bytes"
        run_bytes_manifest = _fixture(run_bytes, ["psx:111", "psx:222", "psx:333"])
        under_file_over_run = b"%PDF-" + (b"x" * (11 * 1024 * 1024))
        out = r.run_reprocess(["psx:111", "psx:222", "psx:333"], root=run_bytes, state_root=run_bytes / "state",
                              allowlist_manifest=run_bytes_manifest,
                              transport=FakeTransport({
                                  "https://dps.psx.com.pk/download/document/111.pdf": FakeResponse(200, under_file_over_run, {"Content-Type": "application/pdf"}),
                                  "https://dps.psx.com.pk/download/document/222.pdf": FakeResponse(200, under_file_over_run, {"Content-Type": "application/pdf"}),
                                  "https://dps.psx.com.pk/download/document/333.pdf": FakeResponse(200, under_file_over_run, {"Content-Type": "application/pdf"}),
                              }),
                              expected_allowlist=frozenset(["psx:111", "psx:222", "psx:333"]))
        assert out["results"][2]["reason"] == "run_byte_cap_exceeded"
        run_pages = root / "run_pages"
        run_pages_manifest = _fixture(run_pages, ["psx:111", "psx:222", "psx:333"])
        page_heavy = _pdf("Financial statements page text with sufficient extracted characters", pages=101)
        out = r.run_reprocess(["psx:111", "psx:222", "psx:333"], root=run_pages, state_root=run_pages / "state",
                              allowlist_manifest=run_pages_manifest,
                              transport=FakeTransport({
                                  "https://dps.psx.com.pk/download/document/111.pdf": FakeResponse(200, page_heavy, {"Content-Type": "application/pdf"}),
                                  "https://dps.psx.com.pk/download/document/222.pdf": FakeResponse(200, page_heavy, {"Content-Type": "application/pdf"}),
                                  "https://dps.psx.com.pk/download/document/333.pdf": FakeResponse(200, page_heavy, {"Content-Type": "application/pdf"}),
                              }),
                              expected_allowlist=frozenset(["psx:111", "psx:222", "psx:333"]))
        assert out["results"][2]["reason"] == "run_page_cap_exceeded"
        mismatch = root / "hash_mismatch"
        mismatch_manifest = _fixture(mismatch, ["psx:111"], hashes={"psx:111": "0" * 64})
        out = _run(mismatch, ["psx:111"], {"psx:111": good_pdf}, manifest=mismatch_manifest)[0]
        assert out["results"][0]["reason"] == "known_receipt_hash_mismatch"

        # Offline transport fallback is bounded to the exact owner-retained annual report.
        retained_doc = next(
            doc for doc in resolved if doc.doc_id == "psx:260947"
        )
        original_spec = dict(r.RETAINED_ORIGINALS["psx:260947"])
        assert original_spec["source_url"] == "https://dps.psx.com.pk/download/document/260947.pdf"
        assert original_spec["content_sha256"] == "1a10091295cf7a815f1910eb418215d501d42b52e39dcbd0b54a53fd1aceaa7d"
        assert original_spec["page_count"] == 333
        retained_fixture = root / "retained_fixture.pdf"
        retained_fixture.write_bytes(good_pdf)
        r.RETAINED_ORIGINALS["psx:260947"] = {
            **original_spec,
            "relative_path": retained_fixture,
            "content_sha256": good_sha,
            "page_count": 2,
        }
        retained_doc = r.VerifiedDocument(
            doc_id=retained_doc.doc_id, numeric_id=retained_doc.numeric_id,
            row=retained_doc.row, url=retained_doc.url, tickers=retained_doc.tickers,
            content_sha256=good_sha, manifest=retained_doc.manifest,
        )

        class NoResponseTransport:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def get(self, url: str, **_: Any) -> Any:
                self.calls.append(url)
                raise ConnectionError("offline fixture")

        offline_transport = NoResponseTransport()
        retained_budget = r.RunBudget()
        retained = r.fetch_with_retained_fallback(
            retained_doc, offline_transport, retained_budget, repo_root,
        )
        assert retained.content_sha256 == good_sha
        assert retained.page_count == 2
        assert offline_transport.calls == [retained_doc.url]

        # A modified retained file is rejected by its pinned manifest hash.
        bad_retained = root / "bad_retained.pdf"
        bad_retained.write_bytes(b"%PDF-not-the-approved-original")
        r.RETAINED_ORIGINALS["psx:260947"] = {
            **r.RETAINED_ORIGINALS["psx:260947"],
            "relative_path": bad_retained,
        }
        try:
            try:
                r.fetch_retained_original(retained_doc, repo_root, r.RunBudget(),
                                          allow_oversized_chunk=True)
            except r.DegradedDocument as exc:
                assert str(exc) == "retained_hash_mismatch"
            else:
                raise AssertionError("modified retained original was accepted")
        finally:
            r.RETAINED_ORIGINALS["psx:260947"] = original_spec

        # Non-approved IDs never perform a filesystem lookup or use the retained path.
        nonapproved = r.VerifiedDocument(
            doc_id="psx:264230", numeric_id="264230", row={},
            url="https://dps.psx.com.pk/download/document/264230.pdf", tickers=["DGKC"],
            content_sha256="0" * 64,
        )
        try:
            r.fetch_retained_original(nonapproved, root, r.RunBudget())
        except r.DegradedDocument as exc:
            assert str(exc) == "retained_original_not_approved"
        else:
            raise AssertionError("non-approved document used retained fallback")

        # Cleanup boundary/path escape.
        try:
            r.safe_cleanup(root, root)
        except r.UnsafeInput:
            pass
        else:
            raise AssertionError("cleanup accepted parent path")
        try:
            r.safe_cleanup(root / "outside", root / "inside")
        except r.UnsafeInput:
            pass
        else:
            raise AssertionError("cleanup accepted path escape")

    print("reprocess_company_documents self-check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
