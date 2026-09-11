# Full desk cycle (pre-market / escalation)

You are the Orchestrator of Henneth. Read CLAUDE.md. Run this exact sequence; each stage's failure degrades gracefully (log and continue where safe, but stages marked GATE stop new-signal generation).

1. **Deterministic data stage** (Bash, in order):
   - `python scripts/update_universe.py` — only if `state/universe.json` older than 7 days
   - `python scripts/fetch_history.py`
   - `python scripts/fetch_dividends.py`
   - `python scripts/fetch_fundamentals.py` — only if `state/fundamentals.json` older than 7 days (weekly; slow-moving reference data)
   - `python scripts/score_fundamentals.py` — plain-English financial scorecards
   - `python scripts/build_calendar.py` — normalizes earnings + ex-div dates into state/earnings_calendar.json
   - `python scripts/quant.py`
   - `python scripts/predictability.py`
   - `python scripts/backtest.py` — all 50+ strategies (strategies/library.json) x universe on deep history → strategy_map.json
   - `python scripts/snapshot.py`
   - `python scripts/fetch_intraday.py` — today's tick series for the 1D charts
   - `python scripts/fetch_global.py` — global markets that drive PSX (crude, S&P, Dow, VIX, gold, BTC, ETH, USD/PKR, DXY)
   - `python scripts/fetch_georisk.py` — geopolitical & market-stress radar (must run AFTER fetch_global + news-sentinel's newslog)
   - `python scripts/tv_crosscheck.py` — independent TradingView verification of quant numbers; non-zero exit counts as a health problem.
   - `python scripts/data_health.py` — GATE: if health status != ok OR crosscheck reported FAILs, skip stages 3-5, still run 2 and 6-7.
   - `python scripts/compute_fairvalue.py`
   - `python scripts/build_signals.py` — the published non-directive signal records
2. **news-sentinel** agent, then **macro-agent** agent (parallel is fine).
   Also run **fundamentals-agent** if today is Monday OR any `state/earnings_calendar.json`
   event is within 21 days and unconfirmed — it verifies earnings/dividend dates vs primary
   sources and flips `confirmed:true`. Skip otherwise (it's weekly-cadence reference work).
2b. **Translate (cheap path).** Run
    `python scripts/translate_extract.py state/macro.json global_read dom.debt_note "drivers[]" "next_events[].event" "sector_tilt.favored[]" "sector_tilt.avoid[]"` (Bash).
    If it prints "0 fields", skip the translator (no LLM call). Otherwise run the
    **state-translator** agent (reads `state/translate_batch.json`, writes
    `state/translate_batch_ur.json` — nothing else), then `python scripts/translate_merge.py`.
    Non-blocking: if any step fails, log and continue — English content is already durably written.
3. **strategist** agent.
4. **risk-officer** agent (only if proposed.json has setups).
5. **auditor** agent (only if vetted.json has approved setups). Setups that PASS audit become published signals: append them to `state/signals.json` with status "active_signal".
   **Do NOT copy `size_shares` or `size_pkr` into `signals.json`** — per docs/PUBLICATION_RESTRUCTURE.md §3 no subscriber-facing surface carries a share count derived from the desk's own capital. They stay in `vetted.json`, where the Auditor's Rule 4/7 re-derivation still needs them, and readers size against their own capital at `/tools/position-size-calculator/`.
   **Do NOT copy `entry`, `stop`, `target`, `rr` or `risk_per_share` into `signals.json` either** — per docs/PUBLICATION_RESTRUCTURE_V2.md §4a a price target or stop-loss on a named security is a "research service" under SECP Reg 2(ha) (S.R.O.7(I)/2026); without the Reg 3 licence the published surface must stay inside the 2(h) general-commentary exemption. The published `active_signal` record carries only non-directive fields (ticker, strategy, template, category, sector, hold_sessions, backtest, confidence, basis, thesis — matching `scripts/build_signals.py`). The levels stay in `vetted.json` for the Auditor's re-derivation; readers derive their own at `/tools/strategy-level-calculator/`.
   Then for each run `python scripts/alert.py "NEW SIGNAL" "<ticker> entry <e> stop <s> target <t> risk/share <r> — <template>"`. (The alert is the owner's PRIVATE Telegram, not a published surface, so it may still cite the level; it is not subject to the 2(h) publication constraint.)
6. **monitor** agent (if any open positions in state/positions.json).
6b. **market-analyst** agent — writes `state/daily_read.json` (the day's plain-English read: tone, sectors, watchlist, risks). Once per day, in the pre-market full run only.
6c. **Translate (cheap path).** Run
    `python scripts/translate_extract.py state/daily_read.json headline summary "sectors[].why" "risks[]" "catalysts[].event" "watchlist[].angle" "watchlist[].risk"` (Bash).
    If it prints "0 fields", skip the translator (no LLM call). Otherwise run the
    **state-translator** agent (reads `state/translate_batch.json`, writes
    `state/translate_batch_ur.json` — nothing else), then `python scripts/translate_merge.py`.
    Non-blocking: if any step fails, log and continue.
7. **Report**: run `python scripts/build_dashboard.py` (Bash) — it assembles the core of
   `state/dashboard.json` deterministically (regime, geo-risk, movers, news, signals, positions).
   Then PATCH in the `agent_wire` array: one line per agent that ran this cycle
   (`[{agent, summary}]`) so the board's Agent Wire reflects the run. Append one line to
   `state/runlog.json`: `{ts, mode:"full", health, setups_proposed, approved, audited_pass, alerts_sent}`.

Rules: never invent data; every number in dashboard.json must come from a state file. If any agent fails, note it in agent_wire and continue. Keep total output terse.
