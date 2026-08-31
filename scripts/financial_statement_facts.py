"""Conservative financial-statement v2 parser and model-input contract.

Geometry-backed facts are emitted only from local block/line table evidence.
Text fallback is retained for audit/quarantine only and is never model-loadable.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from typing import Any

PARSER_VERSION = "financial_statement_v2"
PARSER_REVISION = "block_geometry_v6"

INCOME_STATEMENT_LINE_PATTERNS = {
    # ``sales`` by itself also occurs in ``cost of sales``.  Keep revenue
    # matching broad enough for issuer wording, but do not classify a cost row
    # as revenue while scanning adjacent geometry lines.
    "revenue": r"(?:revenue|net sales|(?<!cost of )sales|turnover)",
    "gross_profit": r"gross profit",
    "ebitda": r"(?:ebitda|earnings\s+before\s+interest,?\s+tax(?:es)?,?\s+depreciation\s+(?:and|&)\s+amorti[sz]ation)",
    "operating_profit": r"(?:operating profit|profit from operations)",
    "finance_cost": r"(?:finance cost|finance costs|financial charges)",
    "profit_before_tax": r"(?:profit before tax|profit before taxation)",
    # Keep PAT before tax: issuer tables commonly label the total as
    # ``Profit after taxation`` and would otherwise be misclassified by the
    # broad ``taxation`` expression below.  The owner row is the attributable
    # value needed by the forecast gate; retain the existing PAT wording too.
    "profit_after_tax_attributable": r"(?:owners of (?:the )?(?:parent|holding)(?: company)?|equity holders of (?:the )?(?:parent|holding)(?: company)?|profit after tax(?:ation)? attributable|profit attributable to owners|profit after tax(?:ation)?|profit for the period)",
    "tax_expense": r"(?:taxation|income tax expense|tax expense)",
    # Issuers alternate between ``Earnings per share`` and the singular
    # ``Earning per share`` label; both denote the same basic EPS row.
    "basic_eps": r"(?:basic )?eps(?:\s|$)|earnings? per share",
}

BALANCE_SHEET_LINE_PATTERNS = {
    "cash_and_cash_equivalents": r"\bcash\s+and\s+(?:cash\s+equivalents|bank\s+balances)\b",
    "trade_receivables": r"\b(?:trade|accounts?)\s+receivables?\b",
    "inventories": r"\binventor(?:y|ies)\b",
    "total_current_assets": r"\btotal\s+current\s+assets\b",
    "property_plant_equipment": r"\b(?:property,?\s+plant\s+(?:and|&)\s+equipment|fixed\s+assets?)\b",
    "total_assets": r"\btotal\s+assets\b",
    "short_term_borrowings": r"\bshort[-\s]?term\s+(?:borrowings|financ(?:e|ing)|loans?)\b",
    "long_term_borrowings": r"\blong[-\s]?term\s+(?:borrowings|financ(?:e|ing)|loans?)\b",
    "trade_payables": r"\b(?:trade|accounts?)\s+payables?\b",
    "total_equity": r"\b(?:total\s+)?equity\b",
}

CASH_FLOW_LINE_PATTERNS = {
    # Issuers label the load-bearing total in several equivalent ways.  In
    # particular, consolidated cash-flow statements commonly use
    # ``Net cash inflow from operating activities``; the prior expression
    # only recognised ``cash flows from``/``cash generated from`` and thus
    # missed the actual total row despite valid statement geometry.
    "operating_cash_flow": r"\b(?:net\s+)?cash\s+(?:generated\s+from|provided\s+by|used\s+in|flows?\s+from|(?:in|out)flow\s+from)\s+operating\s+activities\b",
    "capital_expenditure": r"\b(?:capital\s+expenditure|fixed\s+capital\s+expenditure|(?:purchase|acquisition|additions?)\s+of\s+property,\s+plant\s+and\s+equipment)\b",
    "depreciation_amortization": r"\bdepreciation\s+(?:and|/)\s+amorti[sz]ation\b",
    "net_cash_from_investing_activities": r"\bnet\s+cash\s+(?:used\s+in|generated\s+from|flows?\s+from|(?:in|out)flow\s+from)\s+investing\s+activities\b",
    "net_cash_from_financing_activities": r"\bnet\s+cash\s+(?:used\s+in|generated\s+from|flows?\s+from|(?:in|out)flow\s+from)\s+financing\s+activities\b",
    "dividends_paid": r"\bdividends?\s+(?:paid|distributed)\b",
}

LINE_PATTERNS = {
    **INCOME_STATEMENT_LINE_PATTERNS,
    **BALANCE_SHEET_LINE_PATTERNS,
    **CASH_FLOW_LINE_PATTERNS,
}
STATEMENT_LINE_PATTERNS = {
    "income_statement": INCOME_STATEMENT_LINE_PATTERNS,
    "balance_sheet": BALANCE_SHEET_LINE_PATTERNS,
    "cash_flow_statement": CASH_FLOW_LINE_PATTERNS,
}
SCALE_MAP = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000, "mn": 1_000_000, "bn": 1_000_000_000}


def stable_id(*parts: Any, prefix: str = "fact") -> str:
    return f"{prefix}_{hashlib.sha256('|'.join(str(x or '') for x in parts).encode()).hexdigest()[:24]}"


def parse_number(value: str) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if text in {"", "-", "—", "–", "n/a", "na"}:
        return None
    negative = text.startswith("(") and text.endswith(")") or text.endswith("-")
    text = text.strip("()").rstrip("-").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    n = float(m.group(0))
    return -n if negative else n


def detect_scale_info(text: str) -> tuple[int | None, list[str]]:
    m = re.search(r"(?:rupees?|rs\.?|pkr)\s+in\s+(thousand|million|billion|bn|mn)", text or "", re.I)
    if m:
        return SCALE_MAP[m.group(1).lower()], []
    # Annual reports frequently abbreviate thousands as ``PKR in '000`` (or
    # use typographic quotes).  This is still explicit table-scale evidence,
    # unlike an unqualified number elsewhere on the page.
    if re.search(r"(?:rupees?|rs\.?|pkr)\s+in\s*[^0-9A-Za-z]?0{3}[^0-9A-Za-z]?", text or "", re.I):
        return 1_000, []
    return None, ["missing_table_scale"]


def detect_scale(text: str) -> int:
    return detect_scale_info(text)[0] or 1


def _token(raw: tuple) -> dict[str, Any] | None:
    if len(raw) < 5:
        return None
    x0, y0, x1, y1, text, *rest = raw
    block = int(rest[0]) if len(rest) >= 1 and isinstance(rest[0], int) else 0
    line = int(rest[1]) if len(rest) >= 2 and isinstance(rest[1], int) else int(round(float(y0)))
    word = int(rest[2]) if len(rest) >= 3 and isinstance(rest[2], int) else 0
    return {
        "x0": float(x0), "y0": float(y0), "x1": float(x1), "y1": float(y1),
        "cx": (float(x0) + float(x1)) / 2, "cy": (float(y0) + float(y1)) / 2,
        "text": str(text), "block": block, "line": line, "word": word,
    }


def build_lines(page_words: list[tuple]) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for raw in page_words or []:
        tok = _token(raw)
        if tok:
            grouped.setdefault((tok["block"], tok["line"]), []).append(tok)
    lines = []
    for (block, line_no), tokens in grouped.items():
        ordered = sorted(tokens, key=lambda t: (t["x0"], t["word"]))
        lines.append({
            "block": block,
            "line": line_no,
            "tokens": ordered,
            "text": " ".join(t["text"] for t in ordered),
            "x0": min(t["x0"] for t in ordered),
            "x1": max(t["x1"] for t in ordered),
            "y0": min(t["y0"] for t in ordered),
            "y1": max(t["y1"] for t in ordered),
            "cy": sum(t["cy"] for t in ordered) / len(ordered),
        })
    return sorted(lines, key=lambda l: (l["y0"], l["x0"]))


def _normalized_words(tokens: list[dict[str, Any]]) -> list[str]:
    return [re.sub(r"[^a-z0-9]", "", t["text"].lower()) for t in tokens]


def _duration_occurrences(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    phrase_specs = [
        (("nine", "months"), 9), (("nine", "month"), 9), (("9", "months"), 9), (("9", "month"), 9),
        (("three", "months"), 3), (("3", "months"), 3), (("quarter",), 3),
        (("six", "months"), 6), (("six", "month"), 6), (("6", "months"), 6), (("6", "month"), 6), (("half", "year"), 6),
        (("year", "ended"), 12), (("annual",), 12),
    ]
    out = []
    for line in lines:
        words = _normalized_words(line["tokens"])
        for start in range(len(words)):
            for phrase, months in phrase_specs:
                size = len(phrase)
                if tuple(words[start:start + size]) != phrase:
                    continue
                seq = line["tokens"][start:start + size]
                out.append({
                    "months": months,
                    "line": line,
                    "x0": min(t["x0"] for t in seq),
                    "x1": max(t["x1"] for t in seq),
                    "cx": sum(t["cx"] for t in seq) / len(seq),
                    "y0": min(t["y0"] for t in seq),
                    "y1": max(t["y1"] for t in seq),
                })
    # PyMuPDF can split a wrapped ``Half year ended`` header into adjacent
    # logical lines.  The generic ``year ended`` phrase is then the same
    # six-month header, not a second annual duration group.
    filtered = []
    for item in out:
        if item["months"] == 12 and any(
            other["months"] in {6, 9}
            and abs(float(other["y0"]) - float(item["y0"])) <= 3
            and float(other["x0"]) < float(item["x1"])
            and float(item["x0"]) < float(other["x1"])
            for other in out
        ):
            continue
        filtered.append(item)
    return sorted(filtered, key=lambda o: (o["y0"], o["cx"]))


def _round_bbox(row: dict[str, Any]) -> list[float]:
    return [round(float(row[key]), 1) for key in ("x0", "y0", "x1", "y1")]


def _line_identity(line: dict[str, Any]) -> dict[str, int]:
    return {"block": int(line.get("block") or 0), "line": int(line.get("line") or 0)}


def _parse_year_token(text: str) -> int | None:
    if re.fullmatch(r"20\d{2}", str(text)):
        return int(text)
    m = re.fullmatch(r"\d{1,2}[./-]\d{1,2}[./-](20\d{2})", str(text))
    return int(m.group(1)) if m else None


def _header_tokens(line: dict[str, Any]) -> list[dict[str, Any]]:
    found = []
    for tok in line["tokens"]:
        year = _parse_year_token(tok["text"])
        if year is not None:
            found.append({**tok, "year": year})
    return found


def _assign_by_voronoi(headers: list[dict[str, Any]], occurrences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(occurrences, key=lambda o: o["cx"])
    if not ordered:
        return []
    boundaries = [(ordered[i]["cx"] + ordered[i + 1]["cx"]) / 2 for i in range(len(ordered) - 1)]
    assigned = []
    for header in sorted(headers, key=lambda h: h["cx"]):
        idx = 0
        while idx < len(boundaries) and header["cx"] > boundaries[idx]:
            idx += 1
        group = ordered[idx]
        assigned.append({**header, "duration_months": group["months"], "group_cx": group["cx"]})
    return assigned


def _same_visual_band(items: list[dict[str, Any]], *, key: str = "cy", tolerance: float = 3) -> list[list[dict[str, Any]]]:
    bands: list[list[dict[str, Any]]] = []
    for item in sorted(items, key=lambda x: (x[key], x.get("cx", x.get("x0", 0)))):
        for band in bands:
            center = sum(float(x[key]) for x in band) / len(band)
            if abs(float(item[key]) - center) <= tolerance:
                band.append(item)
                break
        else:
            bands.append([item])
    return bands


def _synthetic_header_line(headers: list[dict[str, Any]], durations: list[dict[str, Any]]) -> dict[str, Any]:
    source_lines = [h.get("line") for h in headers if h.get("line")] + [d.get("line") for d in durations if d.get("line")]
    tokens = [tok for line in source_lines for tok in (line.get("tokens") or [])]
    if not tokens:
        tokens = headers
    return {
        "block": int((headers[0].get("line") or {}).get("block") or headers[0].get("block") or 0),
        "line": int((headers[0].get("line") or {}).get("line") or 0),
        "tokens": sorted(tokens, key=lambda t: (t["x0"], t.get("word", 0))),
        "text": " ".join(t["text"] for t in sorted(tokens, key=lambda t: (t["x0"], t.get("word", 0)))),
        "x0": min(float(t["x0"]) for t in tokens),
        "x1": max(float(t["x1"]) for t in tokens),
        "y0": min(float(t["y0"]) for t in tokens),
        "y1": max(float(t["y1"]) for t in tokens),
        "cy": sum(float(t["cy"]) for t in tokens) / len(tokens),
    }


def _line_basis_marker(line: dict[str, Any]) -> str | None:
    text = line["text"]
    if re.search(r"\b(?:standalone|unconsolidated|separate financial)\b", text, re.I):
        return "unconsolidated"
    if re.search(r"\bconsolidated\b", text, re.I):
        return "consolidated"
    return None


def _has_header_noise(lines: list[dict[str, Any]], duration_band: list[dict[str, Any]],
                      year_band: list[dict[str, Any]]) -> bool:
    duration_y0 = min(float(d["y0"]) for d in duration_band)
    duration_y1 = max(float(d["y1"]) for d in duration_band)
    year_y0 = min(float(h["y0"]) for h in year_band)
    window_floor = max(0, duration_y0 - 90)
    basis_seen: set[str] = set()
    scale_seen: set[int] = set()
    for line in lines:
        if window_floor <= line["y0"] <= year_y0:
            basis = _line_basis_marker(line)
            if basis:
                basis_seen.add(basis)
            scale, _ = detect_scale_info(line["text"])
            if scale:
                scale_seen.add(scale)
        if duration_y1 < line["y0"] < year_y0:
            if detect_scale_info(line["text"])[0] or _line_basis_marker(line):
                return True
            if _duration_occurrences([line]):
                return True
    return len(basis_seen) > 1 or len(scale_seen) > 1


def _wrapped_header_descriptors(lines: list[dict[str, Any]], occurrences: list[dict[str, Any]],
                                manifest_date: date) -> list[dict[str, Any]]:
    current_year = manifest_date.year
    prior_year = current_year - 1
    duration_bands = _same_visual_band(occurrences, key="y0", tolerance=3)
    year_items = []
    for line in lines:
        if re.search(r"\bnotes?\b", line["text"], re.I):
            continue
        for header in _header_tokens(line):
            year_items.append({**header, "line": line})
    year_bands = _same_visual_band(year_items, key="cy", tolerance=3)
    candidates = []
    for duration_band in duration_bands:
        durations = sorted(duration_band, key=lambda d: d["cx"])
        if len(durations) < 1:
            continue
        # Distinct cumulative/current groups must occupy distinct visual
        # ranges.  Overlapping labels are ambiguous synthetic/fragmented
        # geometry and cannot safely be mapped to year columns.
        if any(float(left["x1"]) > float(right["x0"])
               for left, right in zip(durations, durations[1:])):
            continue
        months = [int(d["months"]) for d in durations]
        if len(set(months)) != len(months):
            continue
        expected_years = [year for _ in durations for year in (current_year, prior_year)]
        eligible = []
        duration_y1 = max(float(d["y1"]) for d in durations)
        for year_band in year_bands:
            headers = sorted(year_band, key=lambda h: h["cx"])
            if len(headers) != 2 * len(durations):
                continue
            if any(h["year"] > current_year for h in headers):
                continue
            year_gap = min(float(h["y0"]) for h in headers) - duration_y1
            if not (0 <= year_gap <= 60):
                continue
            header_min_x = min(float(h["x0"]) for h in headers)
            header_max_x = max(float(h["x1"]) for h in headers)
            # A normal statement table has a ``Note`` column immediately to
            # the left of the year columns.  Only reject a same-band notes
            # label when it sits to the right of all year headers, where it is
            # evidence of an unrelated notes table rather than a statement
            # header.  This preserves the geometry safety gate while accepting
            # wrapped annual-report headers such as Lucky's.
            if any(abs(float(line["cy"]) - sum(float(h["cy"]) for h in headers) / len(headers)) <= 3
                   and re.search(r"\bnotes?\b", line["text"], re.I)
                   and min((float(tok["x0"]) for tok in line["tokens"]
                            if re.fullmatch(r"notes?", tok["text"], re.I)), default=header_min_x)
                   > header_max_x for line in lines):
                continue
            if [h["year"] for h in headers] != expected_years:
                continue
            if _has_header_noise(lines, durations, headers):
                continue
            assigned = []
            for idx, duration in enumerate(durations):
                for header in headers[idx * 2:idx * 2 + 2]:
                    assigned.append({**header, "duration_months": duration["months"], "group_cx": duration["cx"]})
            eligible.append({"line": _synthetic_header_line(headers, durations), "headers": assigned})
        if len(eligible) == 1:
            candidates.extend(eligible)
    return candidates


def _header_descriptors(lines: list[dict[str, Any]], manifest_date: date, title: str) -> list[dict[str, Any]]:
    occurrences = _duration_occurrences(lines)
    candidates = []
    for line in lines:
        headers = _header_tokens(line)
        if len(headers) < 2:
            continue
        preceding = [o for o in occurrences if 0 <= line["y0"] - o["y1"] <= 65]
        if preceding:
            band_y = max(o["y0"] for o in preceding)
            assigned = _assign_by_voronoi(headers, [o for o in preceding if abs(o["y0"] - band_y) <= 12])
        else:
            months = 12 if re.search(r"\b(?:annual|year ended)\b", title, re.I) else None
            assigned = [{**h, "duration_months": months, "group_cx": None} for h in headers] if months else []
        if not assigned:
            continue
        groups: dict[float | None, list[dict[str, Any]]] = {}
        for desc in assigned:
            groups.setdefault(desc["group_cx"], []).append(desc)
        valid = True
        for group in groups.values():
            if sum(1 for h in group if h["year"] == manifest_date.year) != 1:
                valid = False
                break
            if any(h["year"] > manifest_date.year for h in group):
                valid = False
                break
        if valid:
            candidates.append({"line": line, "headers": assigned})
    candidates.extend(_wrapped_header_descriptors(lines, occurrences, manifest_date))
    deduped = []
    seen: set[tuple] = set()
    for candidate in candidates:
        key = tuple((round(float(h["cx"]), 1), h["year"], h["duration_months"]) for h in candidate["headers"])
        if key not in seen:
            seen.add(key)
            deduped.append(candidate)
    return deduped


def _nearest_headers_for_row(header_sets: list[dict[str, Any]], row: dict[str, Any],
                             *, max_distance: float = 120) -> dict[str, Any] | None:
    prior = [h for h in header_sets if h["line"]["y1"] < row["y0"]
             and row["y0"] - h["line"]["y1"] <= max_distance]
    # A wrapped multi-duration table can yield both a partial direct header
    # candidate and the complete geometry candidate on the same visual band.
    # Prefer the complete band on a tie; otherwise a 9-month row can silently
    # displace the matching 3-month columns.
    return max(prior, key=lambda h: (h["line"]["y1"], len(h.get("headers") or []))) if prior else None


def _line_match(row: dict[str, Any], statement_type: str | None = None) -> tuple[str, re.Match[str]] | None:
    patterns = STATEMENT_LINE_PATTERNS.get(statement_type) if statement_type else LINE_PATTERNS
    for line, pattern in patterns.items():
        m = re.search(pattern, row["text"], re.I)
        if m:
            if line == "revenue":
                text = row["text"]
                # Gross-sales and sales-tax deduction rows are not the
                # canonical revenue line and would otherwise create duplicate
                # revenue facts from the same statement.
                if re.search(r"\bgross\s+sales\b", text, re.I) or re.search(
                        r"\bless\s*:\s*sales\s+tax\b", text, re.I):
                    continue
            if line == "long_term_borrowings" and re.search(r"\bcurrent\s+portion\s+of\b", row["text"], re.I):
                continue
            return line, m
    return None


def _nearest_basis(lines: list[dict[str, Any]], row: dict[str, Any], floor_y: float) -> tuple[str | None, float]:
    prior = [l for l in lines if floor_y <= l["y1"] < row["y0"]]
    for line in reversed(prior):
        text = line["text"]
        if re.search(r"\b(?:standalone|unconsolidated|separate financial)\b", text, re.I):
            return "unconsolidated", line["y0"]
        if re.search(r"\bconsolidated\b", text, re.I):
            return "consolidated", line["y0"]
    return None, floor_y


def _nearest_scale(lines: list[dict[str, Any]], row: dict[str, Any], floor_y: float) -> tuple[int | None, list[str], bool]:
    # The scale line can overlap the first statement row by a few points in
    # tightly typeset annual reports; retain the local evidence band without
    # reaching into the row below.
    prior = [l for l in lines if floor_y <= l["y0"] < row["y0"] + 3]
    for line in reversed(prior):
        scale, flags = detect_scale_info(line["text"])
        if scale:
            return scale, flags, True
    return None, ["missing_table_scale"], False


def _note_bands(lines: list[dict[str, Any]], header_line: dict[str, Any], row: dict[str, Any]) -> list[tuple[float, float]]:
    bands = []
    for line in lines:
        if not (header_line["y0"] - 25 <= line["y0"] <= row["y0"]):
            continue
        # A restatement annotation such as ``Restated - note 2.2`` is not a
        # table note column.  Treat only a standalone header label as a note
        # band, otherwise valid comparative/current cells can be suppressed.
        if not re.match(r"\s*notes?\b", line["text"], re.I):
            continue
        for tok in line["tokens"]:
            if re.fullmatch(r"notes?", tok["text"], re.I):
                # Keep the exclusion local to the note label/cell.  A broad
                # +/-35pt band can swallow the first value column when the
                # issuer places the note number immediately left of it (as in
                # MLCF's page-29 interim statement).  The table's numeric
                # columns are already aligned independently, so a tight band
                # is sufficient to suppress note references without masking
                # adjacent facts.
                bands.append((tok["x0"] - 10, tok["x1"] + 10))
    return bands


def _numeric_cells(row: dict[str, Any], label_end_x: float, note_bands: list[tuple[float, float]]) -> list[dict[str, Any]]:
    cells = []
    for tok in row["tokens"]:
        value = parse_number(tok["text"])
        if value is None or tok["cx"] <= label_end_x + 2:
            continue
        if any(lo <= tok["cx"] <= hi for lo, hi in note_bands):
            continue
        cells.append({**tok, "number": value})
    return sorted(cells, key=lambda c: c["cx"])


def _numeric_only_continuation(line: dict[str, Any], label_end_x: float,
                               note_bands: list[tuple[float, float]]) -> list[dict[str, Any]]:
    if _line_match(line):
        return []
    cells = []
    for tok in line["tokens"]:
        in_note_band = any(lo <= tok["cx"] <= hi for lo, hi in note_bands)
        if in_note_band:
            continue
        value = parse_number(tok["text"])
        if value is None:
            if re.search(r"[A-Za-z]", tok["text"]):
                return []
            if str(tok["text"]).strip():
                return []
            continue
        if tok["cx"] <= label_end_x + 2:
            return []
        cells.append({**tok, "number": value})
    return sorted(cells, key=lambda c: c["cx"])


def _single_separated_numeric_band(lines: list[dict[str, Any]], row: dict[str, Any],
                                   headers: list[dict[str, Any]], label_end_x: float,
                                   note_bands: list[tuple[float, float]]) -> list[dict[str, Any]]:
    # PyMuPDF can expose one physical values row as one block per column.  Keep
    # the group local to the label (same baseline or no more than 8pt below),
    # and require the whole group to align exactly to the active headers.
    # This is deliberately not a general continuation mechanism: a second
    # eligible numeric band makes the row ambiguous and therefore unusable.
    visual_bands: list[dict[str, Any]] = []
    for line in lines:
        if line is row:
            continue
        same_baseline = abs(float(line["cy"]) - float(row["cy"])) <= 3
        adjacent_baseline = 0 <= float(line["y0"]) - float(row["y1"]) <= 8
        if not (same_baseline or adjacent_baseline):
            continue
        nums = _numeric_only_continuation(line, label_end_x, note_bands)
        if not nums or len(nums) > len(headers):
            continue
        for band in visual_bands:
            if abs(float(band["cy"]) - float(line["cy"])) <= 3:
                band["cells"].extend(nums)
                break
        else:
            visual_bands.append({"cy": float(line["cy"]), "cells": list(nums)})

    candidates = []
    for band in visual_bands:
        nums = sorted(band["cells"], key=lambda c: c["cx"])
        if len(nums) == len(headers) and _aligned_cells(headers, nums) is not None:
            candidates.append(nums)
    return candidates[0] if len(candidates) == 1 else []


def _continuation_cells_or_invalid(line: dict[str, Any], label_end_x: float,
                                   note_bands: list[tuple[float, float]]) -> tuple[list[dict[str, Any]], bool]:
    if _line_match(line):
        return [], True
    cells = []
    for tok in line["tokens"]:
        if any(lo <= tok["cx"] <= hi for lo, hi in note_bands):
            continue
        value = parse_number(tok["text"])
        if value is None:
            return [], bool(str(tok["text"]).strip())
        if tok["cx"] <= label_end_x + 2:
            return [], True
        cells.append({**tok, "number": value})
    return sorted(cells, key=lambda c: c["cx"]), False


def _nearby_numeric_bands(lines: list[dict[str, Any]], row: dict[str, Any], label_end_x: float,
                          note_bands: list[tuple[float, float]]) -> list[dict[str, Any]]:
    bands = []
    for line in lines:
        y_delta = float(line["y0"] - row["y1"])
        if line is not row and not (-4 <= y_delta <= 40):
            continue
        numeric = []
        non_numeric = False
        for tok in line["tokens"]:
            if any(lo <= tok["cx"] <= hi for lo, hi in note_bands):
                continue
            value = parse_number(tok["text"])
            if value is not None and tok["cx"] > label_end_x + 2:
                numeric.append(tok)
                continue
            if tok["cx"] > label_end_x + 2 and str(tok["text"]).strip():
                non_numeric = True
        if numeric or line is row:
            bands.append({
                **_line_identity(line),
                "y_delta": round(y_delta, 1),
                "numeric_count": len(numeric),
                "numeric_x": [round(float(tok["cx"]), 1) for tok in numeric[:12]],
                "numeric_only": bool(numeric) and not non_numeric,
            })
    return bands[:4]


def _label_end_x(row: dict[str, Any], line_name: str) -> float:
    text = " ".join(t["text"] for t in row["tokens"])
    match = re.search(LINE_PATTERNS[line_name], text, re.I)
    if not match:
        return row["x0"]
    consumed = len(text[:match.end()].split())
    tokens = row["tokens"][:max(consumed, 1)]
    return max(t["x1"] for t in tokens)


def _aligned_cells(headers: list[dict[str, Any]], nums: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]] | None:
    if len(headers) != len(nums):
        return None
    aligned = []
    used: set[int] = set()
    for header in sorted(headers, key=lambda h: h["cx"]):
        candidates = [(abs(num["cx"] - header["cx"]), idx, num) for idx, num in enumerate(nums)
                      if idx not in used and abs(num["cx"] - header["cx"]) <= 50]
        if not candidates:
            return None
        _, idx, num = min(candidates, key=lambda c: c[0])
        used.add(idx)
        aligned.append((header, num))
    return aligned if len(used) == len(nums) else None


def _fallback_facts(doc: dict[str, Any], page_no: int, page_text: str, period: str, available_on: str | None) -> list[dict[str, Any]]:
    out = []
    for line, pattern in INCOME_STATEMENT_LINE_PATTERNS.items():
        m = re.search(rf"(?im)^\s*({pattern})[^\n]*?\s+([\(\-]?\d[\d,]*(?:\.\d+)?\)?-?)\s*$", page_text)
        if not m:
            continue
        value = parse_number(m.group(2))
        if value is None:
            continue
        flags = ["geometry_not_proven", "missing_consolidation_basis", "missing_currency_evidence", "missing_table_scale"]
        out.append({
            "fact_id": stable_id(doc.get("doc_id"), doc.get("content_sha256"), page_no, line, period, "fallback", m.group(2)),
            "parser_version": PARSER_VERSION,
            "parser_revision": PARSER_REVISION,
            "document_id": doc.get("doc_id"),
            "source_url": doc.get("source_url"),
            "content_sha256": doc.get("content_sha256"),
            "page": page_no,
            "evidence": [{"page": page_no, "text": m.group(0)[:240], "source_url": doc.get("source_url")}],
            "statement_type": "income_statement",
            "line": line,
            "fact_type": line,
            "reported_label": m.group(1),
            "period_end": period,
            "duration_months": None,
            "column_role": "current",
            "comparative_to_period_end": None,
            "consolidation": None,
            "currency": None,
            "scale": 1,
            "unit": "PKR/share" if line == "basic_eps" else "PKR",
            "unit_multiplier": 1,
            "value": value,
            "normalized_value": value,
            "raw_value": m.group(2),
            "quality_flags": flags,
            "readiness": "audit_only",
            "available_on": available_on,
            "published_at": doc.get("published_at"),
            "retrieved_at": doc.get("retrieved_at"),
        })
    return out


def _structured_page_facts(doc: dict[str, Any], page_no: int, page_words: list[tuple],
                           page_text: str, period: str, available_on: str | None) -> list[dict[str, Any]]:
    lines = build_lines(page_words)
    if not lines:
        return []
    # Notes and management-review tables often reuse labels (for example
    # ``Revenue``) with the same year columns.  They are page-evidenced but are
    # not primary income statements; require a local statement heading before
    # accepting any row.
    heading = _statement_heading(lines)
    if not heading:
        return []
    try:
        manifest_date = date.fromisoformat(str(period)[:10])
    except (TypeError, ValueError):
        return []
    header_sets = _header_descriptors(lines, manifest_date, str(doc.get("title") or ""))
    if not header_sets:
        return []
    out: list[dict[str, Any]] = []
    for row in lines:
        statement_type = str(heading.get("type") or "")
        matched = _line_match(row, statement_type)
        if not matched:
            continue
        line_name, label_match = matched
        if line_name == "profit_after_tax_attributable" and _is_non_attributable_pat_row(lines, row):
            continue
        # Cash-flow totals can sit well below the header (after the opening
        # section label and several component rows).  Permit a wider bounded
        # search only for the canonical OCF row; other rows retain the strict
        # proximity gate so notes/tables cannot borrow a header.
        long_row = line_name in {"profit_after_tax_attributable", "basic_eps", "operating_cash_flow"}
        headers = _nearest_headers_for_row(header_sets, row, max_distance=500 if long_row else 120)
        if not headers:
            continue
        floor_y = max(0, headers["line"]["y0"] - 90)
        basis, basis_y = _nearest_basis(lines, row, floor_y)
        scale, scale_flags, currency_seen = _nearest_scale(lines, row, basis_y)
        label_end = _label_end_x(row, line_name)
        note_bands = _note_bands(lines, headers["line"], row)
        nums = _numeric_cells(row, label_end, note_bands)
        needed = len(headers["headers"])
        # A note reference can be the only numeric token on a label line while
        # the actual statement values sit in a separately extracted but
        # visually adjacent numeric band.  Only replace an incomplete label
        # row when that band is unique and fully column-aligned; never merge
        # the two, because doing so could treat the note number as a value.
        if len(nums) != needed:
            separated = _single_separated_numeric_band(
                lines, row, headers["headers"], label_end, note_bands)
            if separated:
                nums = separated
        # Some PDFs split a wrapped EPS value into one text block per column
        # (``21.09`` and ``1.42`` are separate lines at the same y).  Gather
        # those cells as one geometry band, but only when the neighbouring
        # text explicitly identifies the EPS units/qualifier.
        if not nums and line_name == "basic_eps":
            continuations = [l for l in lines if l is not row and
                             -4 <= l["y0"] - row["y1"] <= 35]
            # Lucky's consolidated statement puts continuing/discontinued EPS
            # on labelled rows and the full-year basic EPS on a following
            # numeric-only row.  Prefer that explicit total row; accepting the
            # first labelled continuation would silently publish continuing
            # EPS as the annual metric.
            eps_nums = []
            eps_row = None
            for continuation in continuations:
                part = _numeric_only_continuation(continuation, label_end, note_bands)
                if len(part) == needed:
                    eps_nums = part
                    eps_row = continuation
                    break
            if eps_nums:
                nums = sorted(eps_nums, key=lambda c: c["cx"])
                row = {**row, "text": row["text"] + " " + eps_row["text"],
                       "y1": max(row["y1"], eps_row["y1"]),
                       "x1": max(row["x1"], eps_row["x1"])}
            elif any(re.search(r"\b(?:share|diluted|rupees?)\b", l["text"], re.I) for l in continuations):
                for continuation in continuations:
                    eps_nums.extend(_numeric_cells(continuation, label_end, note_bands))
                if len(eps_nums) == needed:
                    nums = sorted(eps_nums, key=lambda c: c["cx"])
        if not nums:
            continuation_row = row
            invalid_continuation = False
            continuations=[l for l in lines if l is not row and
                           ((line_name == "basic_eps" and -4 <= l["y0"] - row["y1"] <= 35) or
                            (line_name != "basic_eps" and 3 < l["y0"] - row["y1"] <= 35))]
            for continuation in continuations:
                if len(nums) == needed and _line_match(continuation):
                    break
                # EPS labels are often wrapped as ``... basic`` followed by
                # ``and diluted in Rupees`` while the values remain on that
                # second visual line.  Accept only an explicit EPS qualifier
                # and the same-column numeric cells; ordinary continuation
                # rows retain the stricter all-numeric gate below.
                if line_name == "basic_eps" and re.search(r"\b(?:share|diluted|rupees?)\b", continuation["text"], re.I):
                    part = _numeric_cells(continuation, label_end, note_bands)
                    if len(part) == needed:
                        nums.extend(part)
                        continuation_row = {**continuation_row, "text": continuation_row["text"] + " " + continuation["text"], "y1": max(continuation_row["y1"], continuation["y1"]), "x1": max(continuation_row["x1"], continuation["x1"])}
                        break
                # A new statement row marks the end of a wrapped numeric
                # continuation; never consume values from the following row.
                if _line_match(continuation):
                    break
                part, invalid = _continuation_cells_or_invalid(continuation, label_end, note_bands)
                if invalid:
                    invalid_continuation = True
                    break
                if part:
                    if len(nums) + len(part) > needed:
                        invalid_continuation = True
                        break
                    nums.extend(part)
                    continuation_row = {**continuation_row, "text": continuation_row["text"] + " " + continuation["text"], "y1": max(continuation_row["y1"],continuation["y1"]), "x1": max(continuation_row["x1"], continuation["x1"])}
            if invalid_continuation:
                continue
            row = continuation_row
        aligned = _aligned_cells(headers["headers"], nums)
        if not aligned:
            continue
        for header, num in aligned:
            try:
                period_end = date(header["year"], manifest_date.month, manifest_date.day).isoformat()
            except ValueError:
                continue
            role = "current_period" if header["year"] == manifest_date.year else "comparative_prior_period"
            flags: list[str] = []
            if not basis:
                flags.append("missing_consolidation_basis")
            if line_name != "basic_eps":
                flags.extend(scale_flags)
            if not currency_seen:
                flags.append("missing_currency_evidence")
            multiplier = 1 if line_name == "basic_eps" else (scale or 1)
            value = num["number"] * multiplier
            out.append({
                "fact_id": stable_id(doc.get("doc_id"), doc.get("content_sha256"), page_no, line_name, period_end, role, basis, num["text"], header["duration_months"]),
                "parser_version": PARSER_VERSION,
                "parser_revision": PARSER_REVISION,
                "document_id": doc.get("doc_id"),
                "source_url": doc.get("source_url"),
                "content_sha256": doc.get("content_sha256"),
                "page": page_no,
                "evidence": [{"page": page_no, "text": row["text"][:240], "source_url": doc.get("source_url")}],
                "statement_type": statement_type,
                "statement_heading": heading,
                "line": line_name,
                "fact_type": line_name,
                "reported_label": label_match.group(0),
                "period_end": period_end,
                "duration_months": header["duration_months"],
                "period_type": "annual" if header["duration_months"] == 12 else "interim",
                "column_role": role,
                "comparative_to_period_end": period if role == "comparative_prior_period" else None,
                "consolidation": basis,
                "currency": "PKR" if currency_seen else None,
                "scale": multiplier,
                "unit": "PKR/share" if line_name == "basic_eps" else "PKR",
                "unit_multiplier": multiplier,
                "value": value,
                "normalized_value": value,
                "raw_value": num["text"],
                "quality_flags": sorted(set(flags)),
                "readiness": "model_loadable" if not flags else "audit_only",
                "available_on": available_on,
                "published_at": doc.get("published_at"),
                "retrieved_at": doc.get("retrieved_at"),
            })
    # A wrapped PDF row can be visited more than once when PyMuPDF exposes
    # duplicate visual blocks.  Keep one fact per page/line/period/column;
    # retaining duplicates would look like multiple revenue observations.
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for fact in out:
        key = (fact.get("page"), fact.get("line"), fact.get("period_end"),
               fact.get("duration_months"), fact.get("column_role"), fact.get("consolidation"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fact)
    return deduped


def _statement_heading(lines: list[dict[str, Any]]) -> dict[str, Any] | None:
    # Issuer PDFs vary between a single heading line and wrapped headings such
    # as ``Consolidated Statement of`` / ``Profit or Loss``.  Search individual
    # lines first, then a bounded top-of-page join so unrelated body text is
    # never used as a statement descriptor.
    for line in lines[:12]:
        text = line["text"]
        # A comprehensive-income statement repeats the PAT/attribution labels,
        # but is not the primary income statement used by the model.  Accept a
        # combined ``profit or loss and ... comprehensive income`` heading,
        # while rejecting a standalone comprehensive statement.
        if re.search(r"\bstatement\b.*\bcomprehensive\s+income\b", text, re.I) \
                and not re.search(r"\bprofit\s+or\s+loss\b", text, re.I):
            continue
        if re.search(r"\bstatement\b.*\b(?:profit|loss|income|comprehensive|operations)\b", text, re.I):
            return {"type": "income_statement", "basis": _basis_from_text(text), "bbox": _round_bbox(line)}
        if re.search(r"\b(?:profit|loss|income)\b.*\bstatement\b", text, re.I):
            return {"type": "income_statement", "basis": _basis_from_text(text), "bbox": _round_bbox(line)}
        if re.search(r"\bstatement\b.*\bfinancial\s+position\b|\bbalance\s+sheet\b", text, re.I):
            return {"type": "balance_sheet", "basis": _basis_from_text(text), "bbox": _round_bbox(line)}
        if re.search(r"\bstatement\b.*\bcash\s+flows?\b|\bcash\s+flows?\b.*\bstatement\b", text, re.I):
            return {"type": "cash_flow_statement", "basis": _basis_from_text(text), "bbox": _round_bbox(line)}
    top = " ".join(line["text"] for line in lines[:6])
    if re.search(r"\bstatement\b.*\bcomprehensive\s+income\b", top, re.I) \
            and not re.search(r"\bprofit\s+or\s+loss\b", top, re.I):
        return None
    if re.search(r"\bstatement\b.*\b(?:profit|loss|income|comprehensive|operations)\b", top, re.I) \
            or re.search(r"\b(?:profit|loss|income)\b.*\bstatement\b", top, re.I):
        first = lines[0]
        return {"type": "income_statement", "basis": _basis_from_text(top), "bbox": _round_bbox(first)}
    if re.search(r"\bstatement\b.*\bfinancial\s+position\b|\bbalance\s+sheet\b", top, re.I):
        first = lines[0]
        return {"type": "balance_sheet", "basis": _basis_from_text(top), "bbox": _round_bbox(first)}
    if re.search(r"\bstatement\b.*\bcash\s+flows?\b|\bcash\s+flows?\b.*\bstatement\b", top, re.I):
        first = lines[0]
        return {"type": "cash_flow_statement", "basis": _basis_from_text(top), "bbox": _round_bbox(first)}
    return None


def _is_non_attributable_pat_row(lines: list[dict[str, Any]], row: dict[str, Any]) -> bool:
    """Reject PAT subtotals/totals when the statement exposes an owner row.

    Consolidated statements commonly show continuing PAT, discontinued PAT,
    total PAT, then an ``Attributable to: Owners ...`` split row.  The model
    metric is the owner-attributable amount, not any of those subtotals.  A
    standalone ``Profit after taxation`` line remains valid for statements
    that do not present an attribution section (for example unconsolidated
    statements).
    """
    text = row["text"]
    if re.search(r"\bowners?\s+of\s+(?:the\s+)?(?:parent|holding)(?:\s+company)?\b|\bequity\s+holders?\s+of\s+(?:the\s+)?(?:parent|holding)(?:\s+company)?\b|\battributable\s+to\s+owners?\b|\bprofit\s+attributable\s+to\s+owners?\b", text, re.I):
        return False
    if re.search(r"\bprofit\s+after\s+tax(?:ation)?\s+from\s+(?:continuing|discontinued)\s+operations\b", text, re.I):
        return True
    if not re.search(r"\bprofit\s+after\s+tax(?:ation)?\b|\bprofit\s+for\s+the\s+period\b", text, re.I):
        return False
    nearby = []
    for candidate in lines:
        if candidate is row or not (0 < candidate["y0"] - row["y0"] <= 70):
            continue
        nearby.append(candidate["text"])
    nearby_text = " ".join(nearby)
    if re.search(r"\b(?:owners?|equity\s+holders?)\s+of\s+(?:the\s+)?(?:parent|holding)(?:\s+company)?\b|\battributable\s+to\s+(?:owners?|equity\s+holders?)\b", nearby_text, re.I):
        return True
    return False


def _basis_from_text(text: str) -> str | None:
    if re.search(r"\b(?:standalone|unconsolidated|separate financial)\b", text, re.I):
        return "unconsolidated"
    if re.search(r"\bconsolidated\b", text, re.I):
        return "consolidated"
    return None


def _evidence_category(lines: list[dict[str, Any]], floor_y: float, row_y: float) -> dict[str, Any]:
    scoped = [line for line in lines if floor_y <= line["y1"] < row_y]
    scale = None
    currency = False
    for line in reversed(scoped):
        if not currency and re.search(r"\b(?:rupees?|rs\.?|pkr)\b", line["text"], re.I):
            currency = True
        if scale is None:
            scale, _ = detect_scale_info(line["text"])
        if currency and scale:
            break
    label = next((name for name, value in SCALE_MAP.items() if value == scale), None)
    return {"currency": "present" if currency else "missing", "scale": label or "missing"}


def diagnose_page_records(doc: dict[str, Any], page_records: list[dict[str, Any]], *, max_pages: int = 25) -> dict[str, Any]:
    """Return bounded parser diagnostics using the same geometry helpers as extraction."""

    period = _extract_period(doc, [str((row or {}).get("text") or "") for row in page_records])
    pages = []
    for idx, record in enumerate(page_records[:max_pages]):
        page_no = int((record or {}).get("page") or idx + 1)
        words = list((record or {}).get("words") or [])
        lines = build_lines(words)
        page_diag: dict[str, Any] = {
            "page": page_no,
            "line_count": min(len(lines), 250),
            "candidate_statement": _statement_heading(lines),
            "duration_groups": [],
            "year_token_candidates": [],
            "year_headers": [],
            "rows": [],
            "note_bands_detected": False,
            "parser_decision": "no_fact",
            "reason_codes": [],
        }
        if not lines:
            page_diag["reason_codes"].append("no_geometry_words")
            pages.append(page_diag)
            continue
        durations = _duration_occurrences(lines)
        page_diag["duration_groups"] = [
            {"months": item["months"], "bbox": _round_bbox(item), "center_x": round(float(item["cx"]), 1),
             **_line_identity(item["line"])}
            for item in durations[:16]
        ]
        year_candidates = []
        for line in lines:
            for tok in _header_tokens(line):
                year_candidates.append({
                    "year": tok["year"],
                    "x": round(float(tok["cx"]), 1),
                    "y": round(float(tok["cy"]), 1),
                    **_line_identity(line),
                })
        page_diag["year_token_candidates"] = year_candidates[:16]
        try:
            manifest_date = date.fromisoformat(str(period)[:10])
        except (TypeError, ValueError):
            manifest_date = None
        header_sets = _header_descriptors(lines, manifest_date, str(doc.get("title") or "")) if manifest_date else []
        for header_set in header_sets[:8]:
            page_diag["year_headers"].append({
                "y": round(float(header_set["line"]["y0"]), 1),
                "headers": [
                    {"year": h["year"], "x": round(float(h["cx"]), 1), "duration_months": h.get("duration_months")}
                    for h in header_set["headers"][:12]
                ],
            })
        page_reasons: set[str] = set()
        statement_type = (page_diag["candidate_statement"] or {}).get("type")
        if not page_diag["candidate_statement"]:
            page_reasons.add("no_candidate_heading")
        if not period:
            page_reasons.add("missing_manifest_period")
        if not durations and not re.search(r"\b(?:annual|year ended)\b", str(doc.get("title") or ""), re.I):
            page_reasons.add("no_duration_groups")
        if not header_sets:
            page_reasons.add("no_current_header")
        facts_on_page = _structured_page_facts(doc, page_no, words, str((record or {}).get("text") or ""), str(period or ""), _available_on(doc)) if period else []
        if facts_on_page:
            page_diag["parser_decision"] = "emitted_model_loadable" if any(f.get("readiness") == "model_loadable" for f in facts_on_page) else "emitted_audit_only"
        for row in lines:
            matched = _line_match(row, statement_type)
            if not matched:
                continue
            line_name, _ = matched
            headers = _nearest_headers_for_row(header_sets, row) if header_sets else None
            floor_y = max(0, headers["line"]["y0"] - 90) if headers else 0
            basis, basis_y = _nearest_basis(lines, row, floor_y)
            scale, scale_flags, currency_seen = _nearest_scale(lines, row, basis_y)
            note_bands = _note_bands(lines, headers["line"], row) if headers else []
            nums = _numeric_cells(row, _label_end_x(row, line_name), note_bands)
            if headers and len(nums) != len(headers["headers"]):
                separated = _single_separated_numeric_band(
                    lines, row, headers["headers"], _label_end_x(row, line_name), note_bands)
                if separated:
                    nums = separated
            aligned = _aligned_cells(headers["headers"], nums) if headers else None
            row_reasons = []
            if not headers:
                row_reasons.append("no_current_header")
            if not basis:
                row_reasons.append("no_local_basis")
            if not scale or scale_flags or not currency_seen:
                row_reasons.append("no_local_scale")
            if headers and aligned is None:
                row_reasons.append("row_cell_mismatch")
            if note_bands:
                page_diag["note_bands_detected"] = True
            page_reasons.update(row_reasons)
            page_diag["rows"].append({
                "label": line_name,
                "y": round(float(row["y0"]), 1),
                "numeric_cell_count": len(nums),
                "numeric_x": [round(float(num["cx"]), 1) for num in nums[:12]],
                "nearby_numeric_bands": _nearby_numeric_bands(lines, row, _label_end_x(row, line_name), note_bands),
                "note_band_count": len(note_bands),
                "scale_currency": _evidence_category(lines, basis_y if basis else floor_y, row["y0"]),
                "decision": "aligned" if aligned else "rejected",
                "reason_codes": row_reasons[:8],
            })
        if not page_diag["rows"] and lines:
            page_reasons.add("descriptor_ambiguity")
        page_diag["reason_codes"] = sorted(page_reasons)[:12]
        pages.append(page_diag)
    return {
        "schema_version": 1,
        "parser_version": PARSER_VERSION,
        "parser_revision": PARSER_REVISION,
        "doc_id": doc.get("doc_id"),
        "page_count_diagnosed": len(pages),
        "pages": pages,
        "truncated": len(page_records) > max_pages,
    }


def _extract_period(doc: dict[str, Any], pages: list[str]) -> str | None:
    if doc.get("period_end"):
        return str(doc["period_end"])[:10]
    title = str(doc.get("title") or "")
    preferred_years = {int(y) for y in re.findall(r"20\d{2}", title)}

    def from_text(text: str) -> str | None:
        m = re.search(r"(?:ended|ending)\s+(\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{4}-\d{2}-\d{2})", text, re.I)
        if m:
            raw = m.group(1).replace("/", "-").replace(".", "-")
            parts = raw.split("-")
            candidate = "-".join(reversed(parts)) if len(parts[0]) <= 2 else raw
            if not preferred_years or int(candidate[:4]) in preferred_years:
                return candidate
            return None
        month_names = ("January|February|March|April|May|June|July|August|September|October|"
                       "November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec")
        named = re.search(
            rf"(?:ended|ending)\s+(?:the\s+)?({month_names})\s+(\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+(20\d{{2}})",
            text, re.I)
        if not named or (preferred_years and int(named.group(3)) not in preferred_years):
            return None
        try:
            month_number = next(i for i, name in enumerate(
                ("january", "february", "march", "april", "may", "june", "july", "august",
                 "september", "october", "november", "december"), 1)
                if name.startswith(named.group(1).lower().rstrip(".")))
            return date(int(named.group(3)), month_number, int(named.group(2))).isoformat()
        except (StopIteration, TypeError, ValueError):
            return None

    # Search each page so long annual reports cannot hide the reporting date
    # after an arbitrary text prefix.  Prefer a date on a page whose local text
    # identifies a primary financial statement; narrative pages often mention
    # prior/future year dates as context.
    candidates: list[tuple[int, int, str]] = []
    for index, page in enumerate(pages):
        page_text = str(page or "")
        candidate = from_text(page_text)
        if not candidate:
            continue
        score = 2 if re.search(r"statement\s+of\s+(?:profit|income)|profit\s+or\s+loss|financial\s+statements", page_text, re.I) else 0
        candidates.append((score, -index, candidate))
    if candidates:
        return max(candidates)[2]
    candidate = from_text(title)
    if candidate:
        return candidate
    return None


def _available_on(doc: dict[str, Any]) -> str | None:
    published = doc.get("published_at") or doc.get("retrieved_at")
    try:
        # Daily CI state is available on the recorded official publication or
        # verified retrieval date.  Do not manufacture a next-day delay: that
        # would make already-retained source evidence look like future data.
        return date.fromisoformat(str(published)[:10]).isoformat() if published else None
    except ValueError:
        return None


def extract_facts(doc: dict[str, Any], pages: list[str], words: list[list[tuple]] | None = None,
                  page_records: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if words is None and page_records:
        words = [list((r or {}).get("words") or []) for r in page_records]
    title = str(doc.get("title") or "")
    full = "\n".join(pages)
    if not re.search(r"financial results|financial statements|annual report|quarterly results", title + " " + full[:2000], re.I):
        return []
    period = _extract_period(doc, pages)
    if not period:
        return []
    available_on = _available_on(doc)
    page_numbers = [int((r or {}).get("page") or i + 1) for i, r in enumerate(page_records or [])] or list(range(1, len(pages) + 1))
    geometry_present = bool(words and any(words))
    out: list[dict[str, Any]] = []
    for page_index, page in enumerate(pages):
        page_no = page_numbers[page_index] if page_index < len(page_numbers) else page_index + 1
        page_words = words[page_index] if words and page_index < len(words) else []
        if page_words:
            out.extend(_structured_page_facts(doc, page_no, page_words, page, period, available_on))
        elif not geometry_present:
            out.extend(_fallback_facts(doc, page_no, page, period, available_on))
    if not available_on:
        for fact in out:
            fact.setdefault("quality_flags", []).append("missing_or_invalid_publication_date")
            fact["quality_flags"] = sorted(set(fact["quality_flags"]))
            fact["readiness"] = "audit_only"
    return out
