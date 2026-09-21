"""PSX DPS portal client. Single source of truth for market data.

Endpoints (unofficial, verified live 2026-07-12):
  /timeseries/eod/{SYM}  -> {"data": [[unix_ts, close, volume, open], ...]} newest first
  /timeseries/int/{SYM}  -> {"data": [[unix_ts, price, volume], ...]} intraday ticks, newest first
  /indices/{INDEX}       -> HTML constituents table (symbol, name, ldcp, current, ..., idx wtg %)
  /market-watch          -> HTML table of all symbols with LDCP/open/high/low/current/volume
"""
import json
import re
from html import unescape
from html.parser import HTMLParser
import threading
import time
from pathlib import Path

import requests

BASE = "https://dps.psx.com.pk"
ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) psx-trade-desk/1.0"}

# One requests.Session PER THREAD. fetch_history.py now refreshes the whole universe in one run
# with a ThreadPoolExecutor, and a single shared Session is not safe under concurrent use (its
# connection pool and cookie jar are mutated without locking). threading.local() gives each worker
# its own Session — connection reuse within a thread, no sharing across threads.
_local = threading.local()

# GLOBAL request-rate gate, shared across every worker thread. DPS rate-limits by AGGREGATE
# request rate, not by connection count: a full-universe sweep at 6 workers with no gate burst
# past its limit and got HTTP 429 on 372 of 491 symbols in one cloud run (fetch marks 429 a
# fail and does NOT overwrite the file, so 258 symbols silently froze at their last good bar).
# This gate spaces ALL DPS requests >= _MIN_INTERVAL apart regardless of worker count, so the
# thread pool only hides network latency and never sets the request rate. ~1.25 req/s is inside
# the rate DPS tolerates across a whole sweep: at 0.35s a stable ~24-symbol cluster (the stalest
# tickers, which lead the queue) still 429'd on every run absorbing the provider's cold-start
# burst penalty; 0.8s clears it. A 491-symbol sweep still finishes in ~7 min, well under the
# job's DEADLINE_S (1200s) and the workflow cap. Slot reservation is done under the lock; the
# sleep is not, so threads don't queue on a held lock.
_MIN_INTERVAL = 0.8
_EMPTY_DATA_RETRIES = 3
_rate_lock = threading.Lock()
_next_slot = [0.0]


class DeadlineExceeded(RuntimeError):
    """A deadline-aware provider call could not complete within its caller's budget."""


def _remaining(deadline):
    if deadline is None:
        return None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise DeadlineExceeded("provider deadline exceeded")
    return remaining


def _sleep_until(deadline, seconds):
    if deadline is None:
        time.sleep(seconds)
        return
    remaining = _remaining(deadline)
    if seconds >= remaining:
        time.sleep(remaining)
        raise DeadlineExceeded("provider deadline reached during backoff")
    time.sleep(seconds)


def _throttle(deadline=None) -> None:
    with _rate_lock:
        now = time.monotonic()
        slot = max(now, _next_slot[0])
        wait = slot - now
        if deadline is not None and wait >= deadline - now:
            raise DeadlineExceeded("provider deadline reached before DPS request")
        _next_slot[0] = slot + _MIN_INTERVAL
    if wait > 0:
        _sleep_until(deadline, wait)


def _sess() -> requests.Session:
    s = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update(HEADERS)
        _local.session = s
    return s


def _get(path: str, retries: int = 6, timeout: int = 20, deadline=None) -> requests.Response:
    last = None
    for i in range(retries):
        _throttle(deadline)  # global rate gate — keeps the aggregate DPS request rate under its 429 limit
        request_timeout = timeout if deadline is None else min(timeout, _remaining(deadline))
        try:
            r = _sess().get(f"{BASE}{path}", timeout=request_timeout)
            if r.status_code == 200:
                return r
            if r.status_code == 429:
                # Rate-limited despite the gate: honour Retry-After when DPS sends it, else back
                # off exponentially. Distinct from other errors so a transient 429 doesn't strand
                # a symbol at its last good bar (the freeze this whole path exists to prevent).
                last = RuntimeError(f"HTTP 429 on {path}")
                ra = r.headers.get("Retry-After", "")
                delay = float(ra) if ra.isdigit() else 2.0 * (2 ** i)
                _sleep_until(deadline, min(delay, 60.0))
                continue
            last = RuntimeError(f"HTTP {r.status_code} on {path}")
        except requests.RequestException as e:
            last = e
        _sleep_until(deadline, 1.5 * (i + 1))
    raise last


def eod_history(symbol: str, deadline=None) -> list[dict]:
    """Daily history, oldest first: [{date, close, volume, open}]. No high/low in this feed."""
    rows = []
    for attempt in range(_EMPTY_DATA_RETRIES):
        payload = _get(f"/timeseries/eod/{symbol}", deadline=deadline).json()
        rows = payload.get("data") or []
        if rows:
            break
    if not rows:
        raise RuntimeError(f"empty history data after {_EMPTY_DATA_RETRIES} attempts")
    out = []
    for row in reversed(rows):  # API is newest-first
        ts, close, volume, opn = row[0], row[1], row[2], row[3]
        out.append({
            "date": time.strftime("%Y-%m-%d", time.gmtime(ts)),
            "close": float(close),
            "volume": int(volume),
            "open": float(opn),
        })
    return out


def intraday_last(symbol: str) -> dict | None:
    """Most recent tick: {ts, price, volume} or None."""
    payload = _get(f"/timeseries/int/{symbol}").json()
    rows = payload.get("data") or []
    if not rows:
        return None
    ts, price, vol = rows[0][0], rows[0][1], rows[0][2]
    return {"ts": int(ts), "price": float(price), "volume": int(vol)}


_ROW_RE = re.compile(r"<tr.*?</tr>", re.S)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _parse_table_rows(html: str) -> list[list[str]]:
    rows = []
    for tr in _ROW_RE.findall(html):
        cells = [_TAG_RE.sub("", c).replace("&amp;", "&").strip() for c in _CELL_RE.findall(tr)]
        if cells:
            rows.append(cells)
    return rows


class _SecurityCell(HTMLParser):
    """Read security identity from DPS attributes, never concatenated display text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.order = None
        self.symbols = set()
        self.badges = []
        self._badge = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "td":
            self.order = attrs.get("data-order")
        if tag == "a":
            match = re.fullmatch(r"/(?:company|etf)/([A-Za-z0-9][A-Za-z0-9.-]*)/?", attrs.get("href", ""))
            if match:
                self.symbols.add(match[1].upper())
        if tag == "div" and "tag" in attrs.get("class", "").split():
            self._badge = True

    def handle_endtag(self, tag):
        if tag == "div":
            self._badge = False

    def handle_data(self, data):
        if self._badge and data.strip():
            self.badges.append(data.strip())


def _security_table_rows(html: str):
    """Yield (plain cells, declared ticker, badges); ambiguous identity fails closed."""
    for tr in _ROW_RE.findall(html):
        full_cells = re.findall(r"<td\b[^>]*>.*?</td>", tr, re.S | re.I)
        if len(full_cells) < 7:
            continue
        first = _SecurityCell()
        first.feed(full_cells[0])
        if len(first.symbols) != 1:
            raise ValueError("DPS security row lacks one unambiguous company/ETF link")
        symbol = next(iter(first.symbols))
        if first.order and first.order.strip().upper() != symbol:
            raise ValueError(f"DPS security identity attributes disagree for {symbol}")
        cells = [unescape(_TAG_RE.sub(" ", c)).strip() for c in full_cells]
        cells[0] = symbol
        yield cells, symbol, sorted(set(first.badges))


def index_constituents(index: str) -> list[dict]:
    """Constituents of KSE100 / KMI30 etc: [{symbol, name, weight_pct}] sorted by weight desc."""
    html = _get(f"/indices/{index}").text
    out = []
    seen = set()
    for cells, symbol, badges in _security_table_rows(html):
        # data rows: SYMBOL, NAME, LDCP, CURRENT, CHANGE, CHANGE%, IDX WTG%, ...
        if len(cells) < 7 or cells[0] in ("SYMBOL", ""):
            continue
        try:
            weight = float(cells[6].replace(",", "").replace("%", ""))
        except ValueError:
            weight = 0.0
        if symbol in seen:
            raise ValueError(f"duplicate DPS index identity: {symbol}")
        seen.add(symbol)
        record = {"symbol": symbol, "name": cells[1], "weight_pct": weight}
        if badges:
            record["source_badges"] = badges
        out.append(record)
    out.sort(key=lambda x: -x["weight_pct"])
    return out


# Temporary Ready-market board suffixes. PSX appends these to the ordinary ticker while a
# corporate action is open (ex-dividend / ex-bonus / ex-right). They are the SAME listed
# ordinary share, not a new company. DPS timeseries still answers the unsuffixed ticker
# (verified 2026-08-17: FFC has 1238 bars, FFCXD has 0).
#
# Never strip NC text or preference/security suffixes by guess. Compliance badges are separate
# HTML metadata, extracted by _security_table_rows; genuine source ticker suffixes remain intact.
_BOARD_STATE_SUFFIXES = ("XD", "XB", "XR")


def split_board_state(symbol: str) -> tuple[str, str | None]:
    """Return (canonical_symbol, temporary_board_state_or_None).

    Only strips a known two-letter Ready-market state suffix when the remainder looks like a
    real ticker (letters, at least 2 characters). Unknown tails are left alone — HASCOLNC
    stays HASCOLNC, EPCLPS stays EPCLPS, US500 stays US500.
    """
    if not isinstance(symbol, str) or not symbol:
        return symbol, None
    raw = symbol.strip().upper()
    for suf in _BOARD_STATE_SUFFIXES:
        if raw.endswith(suf) and len(raw) > len(suf) + 1:
            base = raw[:-len(suf)]
            if base.isalpha():
                return base, suf
            return raw, None
    return raw, None


def canonical_symbol(symbol: str) -> str:
    """Henneth identity for a source ticker. Temporary XD/XB/XR notation collapses to the
    ordinary share. Everything else is returned unchanged (uppercased)."""
    canon, _state = split_board_state(symbol)
    return canon


def market_watch() -> dict[str, dict]:
    """Live snapshot of all symbols: {SYM: {ldcp, open, high, low, current, volume}}."""
    html = _get("/market-watch").text
    # header names come from data-name attributes on th
    header = re.findall(r'<th[^>]*data-name="([^"]+)"', html)
    snap = {}
    for cells, sym, badges in _security_table_rows(html):
        if len(cells) < len(header) or cells[0] == "SYMBOL" or not cells[0]:
            continue
        row = dict(zip(header, cells))

        def num(key):
            v = row.get(key, "").replace(",", "")
            try:
                return float(v)
            except ValueError:
                return None

        record = {
            "ldcp": num("ldcp"), "open": num("open"), "high": num("high"),
            "low": num("low"), "current": num("close"),
            "volume": num("volume"), "sector": row.get("sector", ""),
        }
        if badges:
            record["source_badges"] = badges
        if sym in snap and snap[sym] != record:
            raise ValueError(f"conflicting DPS market-watch rows for {sym}")
        snap[sym] = record
    return snap


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def _clean(o):
    """Recursively replace NaN/Infinity with None so output is valid JSON
    (browsers reject the Infinity/NaN literals Python emits by default)."""
    import math
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(_clean(obj), indent=1, ensure_ascii=False, allow_nan=False),
                   encoding="utf-8")
    for attempt in range(8):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.15 * (attempt + 1))


def price_staleness_pct(price_then, price_now) -> float | None:
    """How far a price captured earlier (e.g. a Desk Room session's price_at_session) has
    drifted from a current price, as an absolute percentage. None if either input is
    missing/non-numeric or price_then <= 0 — never a guessed number (desk hard-rule #2).

    Shared by scripts/provenance_lint.py (gates publish on gross staleness) and
    scripts/room_verify.py (persists the same figure per ticker into state/verify.json) so
    the two checks can never silently disagree on the formula."""
    if not isinstance(price_then, (int, float)) or not isinstance(price_now, (int, float)):
        return None
    if price_then <= 0:
        return None
    return abs(price_now / price_then - 1) * 100


def load_config() -> dict:
    return json.loads((ROOT / "config" / "desk.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------------
# MARKETS. PSX is the home market and everything here defaults to it, so a universe entry with no
# `market` field behaves exactly as it did before config/markets.json existed. See
# docs/PUBLICATION_RESTRUCTURE.md section 7.

_DEFAULT_MARKET = "PSX"


def load_markets() -> dict:
    """Per-market config. Missing file degrades to a PSX-only desk rather than crashing —
    a US layer that fails to load must never take the home market down with it."""
    try:
        return json.loads((ROOT / "config" / "markets.json").read_text(encoding="utf-8"))["markets"]
    except (OSError, ValueError, KeyError):
        return {}


def market_of(symbol: str, universe: dict | None = None) -> str:
    """Which market a symbol belongs to. Defaults to PSX for every pre-existing entry."""
    if universe is None:
        universe = load_json(STATE / "universe.json", {"symbols": {}})
    return ((universe.get("symbols", {}).get(symbol) or {}).get("market") or _DEFAULT_MARKET)


def yahoo_symbol(symbol: str, universe: dict | None = None) -> str:
    """The ticker as Yahoo spells it.

    This one function is the entire data-layer cost of adding a market. PSX names carry the
    Karachi suffix (`FFC` -> `FFC.KA`); a US ticker is itself.

    An EXPLICIT `yahoo` field on the universe entry wins, and index symbols rely on it. Yahoo
    spells the S&P 500 `^GSPC`, but the desk's own symbol has to survive being a FILENAME
    (state/history/{SYM}.json) and then a URL PATH the browser fetches — and `^` is unsafe in a
    URL, so it would arrive percent-encoded or not at all. So the desk calls it `US500` and maps
    it here. Never let an upstream vendor's punctuation become a filename."""
    if universe is None:
        universe = load_json(STATE / "universe.json", {"symbols": {}})
    meta = universe.get("symbols", {}).get(symbol) or {}
    if meta.get("yahoo"):
        return meta["yahoo"]
    mkt = meta.get("market") or _DEFAULT_MARKET
    suffix = (load_markets().get(mkt) or {}).get("yahoo_suffix", ".KA")
    if symbol.startswith("^") or symbol.endswith(suffix or "\0"):
        return symbol
    return f"{symbol}{suffix}"


def market_symbols(market: str = _DEFAULT_MARKET, symbols: list[str] | None = None) -> list[str]:
    """Filter to one market. Defaults to PSX.

    WHY THIS EXISTS. Adding a second market to universe.json silently widened the input of every
    script that iterates it — including the ones whose SOURCE is PSX-specific. `fetch_intraday.py`
    would ask DPS for XLE, `fetch_dividends_deep.py` would ask Yahoo for `US500.KA`, and
    `fetch_fundamentals.py` would look for a Karachi filing for an American sector ETF. None of
    those crash; they just fail 23 times a cycle and, worse, spend a bounded per-run fetch budget
    on symbols that can never succeed — which STARVES the real PSX names those budgets exist for.

    So: anything whose data SOURCE is PSX wraps its symbol list in this. Anything that is pure
    maths over state/history/{SYM}.json (quant, backtest, predictability, correlation, fair value)
    deliberately does NOT — those are market-agnostic and US coverage is the point."""
    universe = load_json(STATE / "universe.json", {"symbols": {}})
    syms = universe.get("symbols", {})
    pool = symbols if symbols is not None else list(syms)
    return [s for s in pool if ((syms.get(s) or {}).get("market") or _DEFAULT_MARKET) == market]


def research_symbols() -> list[str]:
    """The names the expensive pipeline (backtests, fundamentals, predictability, fair value)
    is allowed to run on: tier=core plus any listed name that cleared the liquidity RESEARCH
    gate in state/liquidity.json.

    One helper, one definition. These scripts previously each carried their own
    `tier == "core"` filter, so a change to the rule meant editing every copy and any missed
    copy would silently analyse a different set than the others.

    Fails CLOSED to core-only: if liquidity.json is missing or unreadable (first run, or a
    failed cycle), we analyse the smaller known-good set rather than fanning out over the
    whole market on a gate we cannot verify."""
    universe = load_json(STATE / "universe.json", {"symbols": {}})
    core = [s for s, m in universe.get("symbols", {}).items()
            if (m or {}).get("tier", "core") == "core"]
    liq = load_json(STATE / "liquidity.json", None)
    if not liq or not liq.get("tickers"):
        return core
    promoted = [s for s, m in liq["tickers"].items()
                if m.get("research_eligible") and s in universe.get("symbols", {})]
    return sorted(set(core) | set(promoted))
