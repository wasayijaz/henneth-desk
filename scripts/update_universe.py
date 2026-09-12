"""Refresh the trading universe.

TWO TIERS, one universe. The desk previously covered only the KSE100 + KMI30 (~103 names), which
meant a real listed company like BBFL simply did not exist in the product — search found nothing,
and there was no page to land on. For a product users expect to be complete, an unsearchable
listed company is a bug, not a scope decision.

  core   — KSE-100 (top-N by weight) + full KMI-30.
           Gets the FULL pipeline: deep history, backtests, fundamentals, fair value, Desk Room
           debates, signals. These are the names the desk actually researches.
  listed — every remaining constituent of the KSE All Share index (ALLSHR), i.e. the rest of the
           market. Gets prices, quant basics, sector, dividends and a real page — so every listed
           company is searchable and readable — but NOT the expensive per-ticker analysis.

The tier is written onto each symbol so every downstream script can decide honestly what it can
say about a name, instead of silently implying full coverage everywhere. Scripts that are cheap
per ticker (prices, quant, dividends) should process ALL; scripts that are expensive per ticker
(deep history, backtests, Room) should filter to core.

Writes state/universe.json. Run weekly (run_cycle.py handles cadence).
"""
import sys
import time

from psx_data import STATE, index_constituents, load_config, load_markets, save_json
from psx_data import split_board_state


def _intake(row: dict, indices: list[str], tier: str) -> dict:
    """One PSX index row -> one Henneth universe record.

    Temporary Ready-market suffixes (XD/XB/XR) collapse to the ordinary ticker so FFCXD
    does not replace FFC as a second company. The source spelling is kept on the record.
    NC / preference suffixes are not rewritten here.
    """
    raw = (row.get("symbol") or "").strip()
    canon, state = split_board_state(raw)
    rec = {
        "symbol": canon,
        "name": row.get("name"),
        "weight_pct": row.get("weight_pct"),
        "in": list(indices),
        "tier": tier,
    }
    if state:
        rec["source_symbol"] = raw.upper()
        rec["board_state"] = state
    if row.get("source_badges"):
        rec["source_badges"] = list(row["source_badges"])
    return rec


def _merge_source(existing: dict, incoming: dict) -> None:
    """When the same company appears on a second index, keep any board-state metadata."""
    if incoming.get("source_symbol") and not existing.get("source_symbol"):
        existing["source_symbol"] = incoming["source_symbol"]
        existing["board_state"] = incoming.get("board_state")
    badges = set(existing.get("source_badges", [])) | set(incoming.get("source_badges", []))
    if badges:
        existing["source_badges"] = sorted(badges)


def main():
    cfg = load_config()
    uni_cfg = cfg["universe"]
    top_n = uni_cfg["kse100_top_n"]
    cover_all = uni_cfg.get("cover_all_listed", True)

    kse = index_constituents("KSE100")
    if len(kse) < 50:
        print(f"FATAL: KSE100 constituents parse returned only {len(kse)} rows", file=sys.stderr)
        sys.exit(1)
    kmi = index_constituents("KMI30") if uni_cfg["include_kmi30"] else []

    members = {}
    for c in kse[:top_n]:
        rec = _intake(c, ["KSE100"], "core")
        members[rec["symbol"]] = rec
    for c in kmi:
        rec = _intake(c, ["KMI30"], "core")
        s = rec["symbol"]
        if s in members:
            if "KMI30" not in members[s]["in"]:
                members[s]["in"].append("KMI30")
            _merge_source(members[s], rec)
        else:
            members[s] = rec
    n_core = len(members)

    # the rest of the market, from the All Share index (every listed company)
    n_all = 0
    if cover_all:
        allshr = index_constituents("ALLSHR")
        n_all = len(allshr)
        if n_all < 200:
            # a parse failure here must not silently shrink the universe
            print(f"FATAL: ALLSHR returned only {n_all} rows — preserving prior universe", file=sys.stderr)
            return
        else:
            for c in allshr:
                rec = _intake(c, ["ALLSHR"], "listed")
                s = rec["symbol"]
                if s in members:
                    if "ALLSHR" not in members[s]["in"]:
                        members[s]["in"].append("ALLSHR")
                    _merge_source(members[s], rec)
                else:
                    members[s] = rec

    kmi_all = index_constituents("KMIALLSHR") if cover_all else []
    for c in kmi_all:
        rec = _intake(c, ["KMIALLSHR"], "listed")
        s = rec["symbol"]
        if s in members and "KMIALLSHR" not in members[s]["in"]:
            members[s]["in"].append("KMIALLSHR")
        if s in members:
            _merge_source(members[s], rec)

    # ---- non-PSX markets, merged in from config/markets.json --------------------------------
    # This file REGENERATES universe.json from the PSX indices every cycle, so anything not
    # re-derived here disappears. Without this merge the US symbols would be written once by hand
    # and silently vanish on the next run — the classic "it worked yesterday" data bug.
    # Symbols are declared in config, not scraped, because a fixed index-and-sector list is the
    # whole point (see markets.json _why_us): there is no upstream membership feed to follow.
    n_foreign = 0
    for mkt, mcfg in (load_markets() or {}).items():
        if mkt == "PSX":
            continue
        for group, entries in (mcfg.get("symbols") or {}).items():
            if group.startswith("_") or not isinstance(entries, dict):
                continue
            for sym, spec in entries.items():
                if sym.startswith("_"):
                    continue
                # A plain string is just the name; a dict may also carry `yahoo` for symbols whose
                # vendor spelling is not filename/URL-safe (see markets.json _symbol_note).
                name = spec if isinstance(spec, str) else spec.get("name", sym)
                rec = {
                    "symbol": sym, "name": name, "market": mkt,
                    # core so the full analysis stack runs (quant, backtests, predictability);
                    # `in` records the group so the UI can section them without a second file.
                    "tier": "core", "in": [f"{mkt}:{group.upper()}"],
                }
                if isinstance(spec, dict) and spec.get("yahoo"):
                    rec["yahoo"] = spec["yahoo"]
                members[sym] = rec
                n_foreign += 1

    n_listed = sum(1 for m in members.values() if m["tier"] == "listed")
    save_json(STATE / "universe.json", {
        "updated": time.strftime("%Y-%m-%d %H:%M"),
        "kse100_total": len(kse),
        "kmi30_total": len(kmi),
        "allshr_total": n_all,
        "tiers": {
            "core": n_core,
            "listed": n_listed,
            "_note": ("core = KSE100 + KMI30, full research pipeline. listed = the rest of the "
                      "KSE All Share, covered with prices/quant/sector/dividends and a real page, "
                      "but no deep backtests or Desk Room debates. Any script that is expensive "
                      "per ticker must filter to tier == 'core'."),
        },
        "symbols": members,
    })
    print(f"universe: {len(members)} symbols ({n_core} core [{top_n} KSE100 + {len(kmi)} KMI30], "
          f"{n_listed} listed from ALLSHR, {n_foreign} non-PSX)")


if __name__ == "__main__":
    main()
