"""Extract an official share-capital/share-count tie-out candidate.

This is a pure, provenance-preserving parser.  It never writes state and never
marks a record as approved: callers may retain the candidate only after the
source PDF has passed the normal verified-restage transaction.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any


OFFICIAL_URL = re.compile(r"^https://dps\.psx\.com\.pk/download/document/(\d+)\.pdf$")
DOC_ID = re.compile(r"^psx:(\d+)$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

# The FY25 DGKC issuer report is the canonical source for the share-count
# tie-out.  Keep this pair explicit: the retained PSX distributor copy is not
# independent evidence and must never be accepted or double-counted here.
CANONICAL_ISSUER_DOC_ID = "issuer:39fe974f6ef82bbeadf83938"
CANONICAL_ISSUER_URL = "https://www.dgcement.com/financial-reports/DGAnnual2025.pdf"
CANONICAL_ISSUER_SHA256 = "96ca1120b238541d4916fb1c777614ee6045f30ab130d2f18e8a1fd5c62bdf73"
CANONICAL_ISSUER_PAGE_COUNT = 332

# Keep the match local to the issued/subscribed/paid-up row.  This prevents
# authorised capital (which commonly appears immediately above it) from being
# mistaken for issued shares.
PAID_UP_ROW = re.compile(
    r"issued\s*,?\s*subscribed\s+and\s+paid[-\s]+up\s+share\s+capital"
    r"(?P<body>.{0,260}?\d[\d,]*\s+(?:\([^)]{0,40}\)\s+)?ordinary\s+shares\s+of\s+rs\.?\s*10\s+each"
    r".{0,100})",
    re.I,
)
TABLE_TOTAL = re.compile(
    r"(?P<shares>\d{1,3}(?:,\d{3}){2,})\s+"
    r"(?P<paid_up>\d{1,3}(?:,\d{3})+)\s+"
    r"\d{1,3}(?:,\d{3})+"
)
SHARES_PHRASE = re.compile(
    r"(?P<shares>\d[\d,]*)\s+(?:\([^)]{0,40}\)\s+)?ordinary\s+shares\s+of\s+rs\.?\s*10\s+each",
    re.I,
)
SCALE = re.compile(r"\(\s*(?:rupees?|rs\.?|pkr)\s+in\s+(?:thousand|000)\s*\)", re.I)
YEAR = re.compile(r"\b(20\d{2})\b")


def _number(value: str) -> int | None:
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _period_end(doc: dict[str, Any], page_text: str) -> str | None:
    value = str(doc.get("period_end") or "").strip()
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        pass
    # A year alone is deliberately not converted into a date.  Fiscal year-end
    # is issuer-specific, so callers must supply period_end in the verified
    # registry before promoting the candidate.
    return None


def _paid_up_pair(match: re.Match[str]) -> tuple[int, int] | None:
    """Read one explicitly denominated capital row without guessing a value."""
    phrase = SHARES_PHRASE.search(match.group("body"))
    if not phrase:
        return None
    shares = _number(phrase.group("shares"))
    tail = match.group("body")[phrase.end():]
    nominal_thousands = (shares * 10) / 1_000 if shares else 0
    paid_up_thousands = next(
        (_number(token) for token in re.findall(r"\d[\d,]*", tail)
         if (_number(token) or 0) >= nominal_thousands * 0.99),
        None,
    )
    if not shares or not paid_up_thousands:
        return None
    return shares, paid_up_thousands


def _capital_note_total(text: str, match: re.Match[str]) -> tuple[int, int] | None:
    """Read a capital-note total row when its denomination is in the header.

    Some official PDFs render each issued-share component with the denomination
    but render the total line as only ``shares | capital | comparative``.  It is
    still a safe capital-note tie-out only when the same page has the explicit
    paid-up heading, stated PKR-thousand scale, and the total arithmetic ties.
    """
    body = text[match.end(): match.end() + 2_000]
    pairs = [
        (_number(item.group("shares")), _number(item.group("paid_up")))
        for item in TABLE_TOTAL.finditer(body)
    ]
    pairs = [item for item in pairs if item[0] and item[1]]
    if not pairs:
        return None
    # Component rows can also tie individually.  The total must be the largest
    # explicit share-count row in the same capital-note table.
    shares, paid_up_thousands = max(pairs, key=lambda item: item[0])
    return shares, paid_up_thousands


def extract_share_capital_evidence(
    doc: dict[str, Any],
    pages: list[str],
    page_records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return at most one unapproved capital-note candidate from verified pages.

    The candidate carries the original PSX document identity, hash, URL and
    one-based page number.  Missing identity, scale, period, or arithmetic
    tie-out evidence produces no candidate rather than a guessed value.
    """
    doc_id = str(doc.get("doc_id") or doc.get("document_id") or "").strip()
    source_url = str(doc.get("source_url") or doc.get("url") or "").strip()
    content_sha256 = str(doc.get("content_sha256") or "").strip().lower()
    doc_match = DOC_ID.fullmatch(doc_id)
    url_match = OFFICIAL_URL.fullmatch(source_url)
    issuer_pair = doc_id == CANONICAL_ISSUER_DOC_ID and source_url == CANONICAL_ISSUER_URL
    if (not issuer_pair and (not doc_match or not url_match or doc_match.group(1) != url_match.group(1))):
        return []
    if not SHA256.fullmatch(content_sha256):
        return []
    if issuer_pair:
        if content_sha256 != CANONICAL_ISSUER_SHA256:
            return []
        declared_pages = doc.get("page_count")
        if declared_pages is not None and declared_pages != CANONICAL_ISSUER_PAGE_COUNT:
            return []
    period_end = _period_end(doc, "")

    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for index, raw_page in enumerate(pages or []):
        text = " ".join(str(raw_page or "").split())
        match = PAID_UP_ROW.search(text)
        if not match:
            continue
        if not SCALE.search(text):
            continue
        # A one-line fact may be available first, but a capital-note total is
        # the safer result whenever the one-line layout is ambiguous.  Test
        # each independently; never let a malformed component suppress a
        # later, arithmetically tied total row.
        selected_pair: tuple[int, int] | None = None
        for pair in (_paid_up_pair(match), _capital_note_total(text, match)):
            if not pair:
                continue
            candidate_shares, candidate_paid_up = pair
            if abs(candidate_shares * 10 - candidate_paid_up * 1_000) <= 1_000:
                selected_pair = pair
                break
        if not selected_pair:
            continue
        shares, paid_up_thousands = selected_pair
        nominal_pkr = shares * 10
        paid_up_pkr = paid_up_thousands * 1_000
        page = index + 1
        if page_records and index < len(page_records):
            page = int((page_records[index] or {}).get("page") or page)
        if page < 1:
            continue
        # Citation text must contain the selected total when the page uses a
        # multi-row capital-note table; the heading alone is not reviewable
        # evidence for the emitted share count.
        selected_text = f"{shares:,} {paid_up_thousands:,}"
        selected_offset = text.find(selected_text, match.end())
        excerpt_start = max(0, (selected_offset if selected_offset >= 0 else match.start()) - 100)
        excerpt_end = min(len(text), (selected_offset + len(selected_text) if selected_offset >= 0 else match.end()) + 180)
        excerpt = text[excerpt_start:excerpt_end]
        row = {
            "symbol": str(doc.get("symbol") or (doc.get("tickers") or [None])[0] or "").upper() or None,
            "metric": "shares_out",
            "record_type": "official_share_count_capital_note_tie_out_candidate",
            "approved": False,
            "approval_scope": "verified_restage_required",
            "value": shares,
            "unit": "shares",
            "paid_up_capital_value": paid_up_thousands,
            "paid_up_capital_unit": "PKR thousand",
            "denomination_pkr_per_share": 10,
            "period_end": period_end,
            "available_on": doc.get("available_on"),
            "published_at": doc.get("published_at"),
            "source": {
                "id": doc_id,
                "label": str(doc.get("title") or "Official PSX annual report capital note"),
                "url": source_url,
                "content_sha256": content_sha256,
                "page": page,
                "text": excerpt[:320],
            },
            "tie_out": {
                "nominal_pkr": nominal_pkr,
                "reported_paid_up_pkr": paid_up_pkr,
                "rounding_tolerance_pkr": 1_000,
                "status": "tied_out",
            },
            "readiness": "candidate_only",
            "quality_flags": ["requires_verified_restage_and_owner_approval"],
            "fact_id": "share_candidate_" + hashlib.sha256(
                f"{doc_id}|{content_sha256}|{page}|{shares}|{paid_up_thousands}".encode("utf-8")
            ).hexdigest()[:24],
        }
        # Prefer the canonical consolidated statement of financial position
        # over an older/duplicated share-capital note.  Both remain visible in
        # transient extraction, but only the canonical page is a tie-out
        # candidate for qualification.
        # Use word boundaries so ``unconsolidated statement ...`` cannot win
        # merely because it contains the word ``consolidated`` as a suffix.
        canonical_score = int(bool(re.search(
            r"\bconsolidated\s+statement\s+of\s+financial\s+position\b", text, re.I)
        )) * 4
        canonical_score += int("capital and reserves" in text.lower()) * 2
        # The numbered issued/paid-up capital note is the strongest tie-out
        # evidence: unlike the balance-sheet summary it explicitly identifies
        # the capital-note schedule and share-count columns.
        canonical_score += int(bool(re.search(
            r"(?:^|\s)\d{1,2}\.\s+issued\s*,?\s*subscribed\s+and\s+paid\s+up\s+share\s+capital\b",
            text, re.I,
        ))) * 20
        candidates.append((canonical_score, page, row))
    if not candidates:
        return []
    _, _, selected = max(candidates, key=lambda item: (item[0], item[1]))
    return [selected]
