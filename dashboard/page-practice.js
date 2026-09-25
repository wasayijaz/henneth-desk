/* ==========================================================================================
   PRACTICE PAGE — practice portfolio (redesign 2026-09, v2). Ported from
   docs/redesign-mockups/practice-mockup.html into four spaced chapters (01 how the book is
   doing, 02 the desk's own rules, 03 place an order, 04 journal).

   Business logic is NOT duplicated here — it lives in app.js and is reused as-is:
   PAPER_START, paperState/paperFee/paperPositions/paperCash/paperCreditDividends,
   paperTrade/paperReset (order entry + reset), DESK_RULES/loadDeskRules/deskSize/deskSizeRun/
   correlatedPairs (Rule 4 sizing + risk-limit checks). This file only shapes the data these
   already return into the page's markup. See CLAUDE.md Rule 4: "the ONLY formula" — the sizer
   here is app.js's deskSize/deskSizeRun, not a second copy.
   ========================================================================================== */

function ppRs(v, d) { return v == null || !isFinite(v) ? "unknown" : "Rs " + fmt(v, d == null ? 0 : d); }
function ppPct(v) { return v == null || !isFinite(v) ? "unknown" : sgn(+v.toFixed(2)) + "%"; }
function ppCls(v) { return v == null ? "" : v >= 0 ? "up" : "dn"; }

/* Day-by-day replay of cash + positions marked to real closes (state/history/<SYM>.json), so the
   equity curve is what actually happened to THIS book — not today's mix projected backward
   (that shortcut is what page-portfolio.js's history chart uses; it doesn't fit here because the
   practice book's mix changes trade to trade). KSE-100 overlay uses state/indices.json's
   `history`, which only carries a short trailing window — the chart is honestly clipped to it
   and says so, per CLAUDE.md Rule 2 (unknown, never guessed). */
async function ppEquitySeries(p, idx) {
  if (!p.trades.length) return null;
  const trades = p.trades.slice().sort((a, b) => a.ts.localeCompare(b.ts));
  const syms = [...new Set(trades.map(t => t.sym))];
  const hists = {};
  await Promise.all(syms.map(async s => { hists[s] = (await j(`history/${s}.json`)) || []; }));
  const d0 = trades[0].ts.slice(0, 10);
  const today = new Date().toISOString().slice(0, 10);
  const axisSet = new Set();
  for (const s of syms) for (const row of hists[s]) if (row.date >= d0 && row.date <= today) axisSet.add(row.date);
  if (!axisSet.size) return null;
  const axis = [...axisSet].sort();

  // per-symbol cursor into its (ascending) history — carries the last known close forward
  const cursors = {}; syms.forEach(s => { cursors[s] = { i: -1, hist: hists[s] }; });
  const closeAt = (s, d) => {
    const c = cursors[s];
    while (c.i + 1 < c.hist.length && c.hist[c.i + 1].date <= d) c.i++;
    return c.i >= 0 ? c.hist[c.i].close : null;
  };

  let ti = 0, cash = PAPER_START;
  const sh = {}; syms.forEach(s => { sh[s] = 0; });
  const equity = [];
  for (const d of axis) {
    while (ti < trades.length && trades[ti].ts.slice(0, 10) <= d) {
      const t = trades[ti];
      cash += t.side === "buy" ? -(t.sh * t.px + t.fee) : (t.sh * t.px - t.fee);
      sh[t.sym] = (sh[t.sym] || 0) + (t.side === "buy" ? t.sh : -t.sh);
      ti++;
    }
    let mv = 0, known = true;
    for (const s of syms) { if (!sh[s]) continue; const c = closeAt(s, d); if (c == null) { known = false; break; } mv += c * sh[s]; }
    equity.push(known ? cash + mv : null);
  }

  // KSE-100 overlay, scaled to the SAME Rs base as the equity line at the first date both cover
  let bench = null, benchFrom = null;
  if (idx?.history) {
    const idxDays = Object.keys(idx.history).sort();
    const overlapIdx = axis.findIndex((d, i) => equity[i] != null && idxDays.includes(d));
    if (overlapIdx >= 0) {
      const d0b = axis[overlapIdx], k0 = idx.history[d0b]?.KSE100, e0 = equity[overlapIdx];
      if (k0 && e0 != null) {
        bench = axis.map(d => { const k = idx.history[d]?.KSE100; return k ? e0 * (k / k0) : null; });
        benchFrom = d0b;
      }
    }
  }
  return { axis, equity, bench, benchFrom, d0 };
}

function ppEquityChart(series) {
  if (!series) return `<div class="today-chart-source">History unknown — no trades yet, or no price history on file for the symbols traded.</div>`;
  const { axis, equity, bench, benchFrom, d0 } = series;
  const have = axis.map((d, i) => ({ d, v: equity[i] })).filter(x => x.v != null);
  if (have.length < 2) return `<div class="today-chart-source">History unknown — not enough priced sessions yet to draw a curve.</div>`;
  const vals = have.map(x => x.v).concat(bench ? bench.filter(v => v != null) : []).concat([PAPER_START]);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const W = 560, H = 160, P = { l: 4, r: 4, t: 10, b: 20 };
  const n = axis.length;
  const sx = i => P.l + (i / Math.max(1, n - 1)) * (W - P.l - P.r);
  const sy = v => H - P.b - Math.max(0, Math.min(1, (v - lo) / ((hi - lo) || 1))) * (H - P.t - P.b);
  let ln = "";
  axis.forEach((d, i) => { if (equity[i] == null) return; ln += `${ln ? "L" : "M"}${sx(i).toFixed(1)},${sy(equity[i]).toFixed(1)} `; });
  let bl = "";
  if (bench) bench.forEach((v, i) => { if (v == null) return; bl += `${bl ? "L" : "M"}${sx(i).toFixed(1)},${sy(v).toFixed(1)} `; });
  const startY = sy(equity.find(v => v != null) ?? PAPER_START).toFixed(1);
  const note = bench
    ? (benchFrom > d0 ? `KSE-100 line starts ${esc(benchFrom)} — the index's own history on file doesn't reach back to your first trade (${esc(d0)}); the rest is unknown, not flat.` : `Both lines start ${esc(d0)}, your first trade.`)
    : `KSE-100 comparison unknown — no overlapping index history on file for this window.`;
  return `<svg class="px-eq" viewBox="0 0 ${W} ${H}" role="img" aria-label="Practice account equity vs KSE-100, same Rs base">
      <line class="start" x1="${P.l}" x2="${W - P.r}" y1="${startY}" y2="${startY}"/>
      ${bl ? `<path class="bench" d="${bl}"/>` : ""}
      <path class="eq" d="${ln}"/>
    </svg>
    <p class="today-chart-source">${note}</p>`;
}

function ppAllocBar(invested, total, limitPct) {
  const pct = total ? Math.max(0, Math.min(100, invested / total * 100)) : 0;
  const cashPct = 100 - pct;
  const tick = Math.max(0, Math.min(100, limitPct));
  return `<div class="px-alloc">
    <div class="px-alloc-bar">
      <span class="inv" style="width:${pct.toFixed(2)}%"></span>
      <span class="csh" style="width:${cashPct.toFixed(2)}%"></span>
      <i class="lim" style="left:${tick.toFixed(2)}%" title="${limitPct}% total-exposure limit"></i>
    </div>
    <div class="px-alloc-lab"><span>Invested ${pct.toFixed(1)}%</span><span class="mut">Cash ${cashPct.toFixed(1)}%</span><span class="mut">limit ${limitPct}%</span></div>
  </div>`;
}

function ppHoldings(rows, total, uni) {
  if (!rows.length) return `<div class="empty">No positions yet. Study a company first — then take your first position with money that can't hurt you.</div>`;
  return `<table><thead><tr><th>Stock</th><th class="r">Shares</th><th class="r">Avg cost</th><th class="r">Price</th><th class="r">Value</th><th class="r">P/L</th><th class="r">Weight</th></tr></thead><tbody>${
    rows.map(r => {
      const w = total ? (r.val || 0) / total * 100 : null;
      return `<tr class="clickable" onclick="navigate('/ticker/${r.s}')">
        <td><b>${r.s}</b> <span class="sub">${esc((uni?.symbols?.[r.s]?.name || "").slice(0, 20))}</span><br><small class="mut px-sec">${esc(r.sector || "unknown sector")}</small></td>
        <td class="r num">${r.sh}</td><td class="r num">${fmt(r.avg)}</td>
        <td class="r num">${r.px ? fmt(r.px) : "—"}</td><td class="r num">${r.val ? fmt(Math.round(r.val)) : "—"}</td>
        <td class="r num ${ppCls(r.pl)}">${r.pl != null ? `${sgn(+r.plp.toFixed(1))}% <span class="sub">(${r.pl >= 0 ? "+" : ""}Rs ${fmt(Math.round(r.pl))})</span>` : "—"}</td>
        <td class="r num">${w != null ? w.toFixed(1) + "%" : "—"}</td></tr>`;
    }).join("")}</tbody></table>`;
}

/* ---- 02: seven rule tiles, computed fresh (not deskRulePanel's HTML — that panel duplicates
   the chapter heading and only checks four of the seven). Copy follows the same PUBLICATION
   FRAME discipline as page-portfolio.js's pfXrayHtml(): `k`/`why` state the desk's own rule and
   its impersonal reason; `v`/`ok` are pure arithmetic over the reader's own book. No prose
   narrating what a specific breach "means" for the reader. */
function ppRule(ok, k, why, v, unknown) {
  return `<div class="pf-rule ${unknown ? "" : ok ? "ok" : "bad"}"><div class="pf-rule-h"><span class="mk">${unknown ? "?" : ok ? "✓" : "!"}</span>
    <div><b>${esc(k)}</b><p>${why}</p></div></div><span class="v">${v}</span></div>`;
}

function ppRules(rows, total, invested, p, corr) {
  const held = rows.filter(r => r.val);
  const secCount = {}; held.forEach(r => { if (r.sector) secCount[r.sector] = (secCount[r.sector] || 0) + 1; });
  const dupes = Object.entries(secCount).filter(([, n]) => n > DESK_RULES.max_same_sector_positions);
  const corrPairs = corr ? correlatedPairs(held, corr) : null;
  const expo = total ? invested / total * 100 : 0;
  const top = held.length ? held.reduce((a, b) => ((a.val || 0) > (b.val || 0) ? a : b)) : null;
  const topPct = top && total ? (top.val || 0) / total * 100 : 0;
  const bySec = {}; held.forEach(r => { if (r.sector) bySec[r.sector] = (bySec[r.sector] || 0) + (r.val || 0); });
  const secEntries = Object.entries(bySec);
  const topSec = secEntries.length ? secEntries.reduce((a, b) => (a[1] > b[1] ? a : b)) : null;
  const topSecPct = topSec && total ? topSec[1] / total * 100 : 0;

  // circuit breaker: real trade log has no stop/real flag, so a "stop-out" can only be
  // APPROXIMATED as any sell, grouped into 5-session windows — labelled as such, never
  // presented as the desk's actual circuit-breaker state (CLAUDE.md Rule 2: unknown, not guessed).
  const sells = (p.trades || []).filter(t => t.side === "sell");
  let breakerNote, breakerOk = true, breakerUnknown = !sells.length;
  if (sells.length) {
    const sorted = sells.slice().sort((a, b) => a.ts.localeCompare(b.ts));
    let worstCount = 0;
    for (let i = 0; i < sorted.length; i++) {
      const t0 = Date.parse(sorted[i].ts);
      let n = 1;
      for (let k = i + 1; k < sorted.length; k++) if ((Date.parse(sorted[k].ts) - t0) <= 5 * 86400000) n++;
      worstCount = Math.max(worstCount, n);
    }
    breakerOk = worstCount < 2;
    breakerNote = `${worstCount} sell${worstCount === 1 ? "" : "s"} within any 5-session window (approximated — the log doesn't flag which sells were stop-outs vs. deliberate exits)`;
  } else breakerNote = "no sells yet — unknown until this book has an exit to measure";

  const tiles = [
    ppRule(held.length <= DESK_RULES.max_positions, `Max ${DESK_RULES.max_positions} concurrent positions`,
      "The desk caps open positions so each one gets real attention.", `${held.length} held`),
    ppRule(expo <= DESK_RULES.max_total_exposure_pct, `Max ${DESK_RULES.max_total_exposure_pct}% total exposure`,
      "A concentrated, stop-loss-driven book holds most of its capital in reserve.", `${expo.toFixed(1)}%`),
    ppRule(!top || topPct <= DESK_RULES.max_pct_per_trade, `Max ${DESK_RULES.max_pct_per_trade}% per single name`,
      "Rule 4's position-value cap: no single stop can hurt the book much.", top ? `${topPct.toFixed(1)}% in ${esc(top.s)}` : "no positions"),
    ppRule(!dupes.length, "One position per sector",
      "Two names in the same sector aren't real diversification.", dupes.length ? `${dupes.map(([s, n]) => `${esc(s)} ×${n}`).join(", ")}` : `${Object.keys(secCount).length} sector${Object.keys(secCount).length === 1 ? "" : "s"}, no doubles`),
    corr
      ? ppRule(!corrPairs.length, "All pairs correlation r < 0.6",
          "Catches names in different sectors that still move together.", corrPairs.length ? corrPairs.map(x => `${esc(x.a)}~${esc(x.b)} r=${x.r}`).join(", ") : (held.length > 1 ? "no pair above 0.6" : "needs 2+ positions"))
      : ppRule(true, "All pairs correlation r < 0.6", "Catches names in different sectors that still move together.", "unknown — correlation.json unavailable", true),
    ppRule(!topSec || topSecPct <= 35, "Sector concentration ≤ 35%",
      "A cap on how much of the book one industry can drive.", topSec ? `${esc(topSec[0])} ${topSecPct.toFixed(1)}%` : "no positions"),
    ppRule(breakerOk, "Circuit breaker: 2 stop-outs / 5 sessions",
      "Two stop-outs inside five sessions moves the desk to signal-only.", breakerNote, breakerUnknown),
  ];
  return `<div class="pf-rules px-rules-grid">${tiles.join("")}</div>
  <details class="px-disclosure"><summary>How each rule is measured</summary>
    <ul class="px-disclosure-list">
      <li><b>Positions / exposure / per-name / sector</b> — computed directly from this book's open lots at current DPS prices, against <code>state/desk_rules.json</code>'s limits.</li>
      <li><b>Correlation</b> — <code>state/correlation.json</code>'s peer list for each held symbol, threshold ${corr ? (corr.high_corr_threshold ?? 0.6) : "0.6"}; unknown if that file didn't load.</li>
      <li><b>Circuit breaker</b> — the real trade log stores side/shares/price/fee/time but not a stop-out flag, so this tile approximates a stop-out as any sell, grouped into 5-session windows (no profit/loss check). It is a teaching approximation, not the desk's real signal-only trigger.</li>
    </ul>
  </details>`;
}

/* ---- 03: ticker price chart from real closes, for the symbol currently typed in #pp-sym ---- */
async function ppTickChart(sym) {
  if (!sym) return `<div class="today-chart-source">Type a ticker to see its recent price.</div>`;
  const hist = (await j(`history/${sym}.json`)) || [];
  if (!hist.length) return `<div class="today-chart-source">No price history on file for ${esc(sym)} — unknown.</div>`;
  const rows = hist.slice(-120);
  const vals = rows.map(r => r.close);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const W = 420, H = 120, P = { l: 4, r: 4, t: 8, b: 8 };
  const sx = i => P.l + (i / Math.max(1, rows.length - 1)) * (W - P.l - P.r);
  const sy = v => H - P.b - Math.max(0, Math.min(1, (v - lo) / ((hi - lo) || 1))) * (H - P.t - P.b);
  let ln = ""; rows.forEach((r, i) => { ln += `${ln ? "L" : "M"}${sx(i).toFixed(1)},${sy(r.close).toFixed(1)} `; });
  const last = rows[rows.length - 1], first = rows[0];
  const chg = first.close ? (last.close / first.close - 1) * 100 : null;
  return `<svg class="px-tick" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sym)} recent closes">
      <path class="ln ${ppCls(chg)}" d="${ln}"/>
    </svg>
    <p class="today-chart-source">${esc(sym)} · Rs ${fmt(last.close)} · ${rows.length} sessions on file · ${ppPct(chg)} over that window</p>`;
}

async function pagePractice() {
  await Promise.resolve();
  if (!me) {
    $("view").innerHTML = `<div class="today-page px-page">
      <div class="seg" style="margin-top:4px"><h2>Practice portfolio</h2><div class="ln"></div></div>
      <div class="disclaimer">Virtual money at real market prices — <b>education, not advice</b>, and never a forecast of real returns.</div>
      <div class="card mychart-cta">
        <h2>Learn with PKR 500,000 you can't lose</h2>
        <p class="sub">Real PSX prices, no real money: buy, size, sit through red days, collect dividends at book closure. Every mechanic of investing, none of the damage. Free with an account.</p>
        <button class="bw-go" style="max-width:260px" onclick="openAuth('signup')">Create a free account →</button></div>
    </div>`;
    return;
  }

  const [lv, q, uni, sectors, divs, idx, corr] = await Promise.all([
    j("live.json"), j("quant.json"), j("universe.json"), j("sectors.json"), j("dividends.json"), j("indices.json"), j("correlation.json"),
    loadDeskRules()]);   // Rule 4 limits from config, not the hardcoded fallback

  const p = { trades: [], credits: [], ...paperState() };
  if (paperCreditDividends(p, divs)) { myProfile = { ...(myProfile || {}), paper: p }; saveProfile({ paper: p }); }
  const pos = paperPositions(p), cash = paperCash(p);
  const pxOf = s => lv?.tickers?.[s]?.current ?? q?.tickers?.[s]?.close;
  const rows = Object.entries(pos).map(([s, x]) => {
    const px = pxOf(s), val = px ? px * x.sh : null, avg = x.cost / x.sh;
    return { s, sh: x.sh, avg, px, val, pl: val != null ? val - x.cost : null, plp: val != null ? (val / x.cost - 1) * 100 : null, sector: sectors?.tickers?.[s]?.sector || "" };
  }).sort((a, b) => (b.val || 0) - (a.val || 0));
  const invested = rows.reduce((a, r) => a + (r.val || 0), 0);
  const total = cash + invested, ret = (total / PAPER_START - 1) * 100;

  // benchmark: KSE100 since the first trade — same window, honest comparison (headline number;
  // the equity chart below shows the full curve, clipped to what indices.json actually covers)
  let bench = null;
  if (p.trades.length && idx?.history) {
    const d0 = p.trades[0].ts.slice(0, 10);
    const days = Object.keys(idx.history).sort();
    const k0 = idx.history[days.find(d => d >= d0) || days[days.length - 1]]?.KSE100;
    const k1 = idx.live?.KSE100 ?? idx.history[days[days.length - 1]]?.KSE100;
    if (k0 && k1) bench = (k1 / k0 - 1) * 100;
  }

  const equitySeries = await ppEquitySeries(p, idx);

  $("view").innerHTML = `<div class="today-page px-page">
  <div class="seg" style="margin-top:4px"><h2>Practice portfolio</h2><div class="ln"></div><span class="pill">virtual money · real prices</span></div>
  <div class="disclaimer">Virtual PKR ${fmt(PAPER_START)} at real market prices, for <b>education only</b>. Paper results overstate real ones — they can't simulate fear, and fills here ignore market depth. A teaching commission (0.15%, min Rs 25) is applied so costs are never invisible; real brokers' fees differ.</div>

  <div class="px-ch first">
    <div class="px-ch-n">01</div>
    <div class="px-ch-t">
      <h3>How the book is doing</h3>
      <div class="px-book">
        <section class="today-hero">
          <div class="today-stance">
            <p class="today-kicker">ACCOUNT VALUE <span>· virtual, at desk prices</span></p>
            <h1 class="pf-value">${ppRs(total, 0)}</h1>
            <div class="pf-duo">
              <span><small>SINCE START</small><b class="${ppCls(ret)}">${ppRs(total - PAPER_START, 0)}</b><em class="${ppCls(ret)}">${ppPct(ret)}</em></span>
              <span><small>KSE-100 SAME PERIOD</small><b class="${ppCls(bench)}">${bench != null ? ppPct(bench) : "unknown"}</b><em class="mut">${p.trades.length ? "since first trade" : "no trades yet"}</em></span>
            </div>
          </div>
          <div class="today-index">
            <p class="today-kicker">EQUITY CURVE <span>· real fills, real closes · dashed = start · grey = KSE-100</span></p>
            ${ppEquityChart(equitySeries)}
          </div>
        </section>

        ${ppAllocBar(invested, total, DESK_RULES.max_total_exposure_pct)}

        <div class="seg"><h2>Holdings</h2><div class="ln"></div><span class="pill">${rows.length}</span>${rows.length ? csvBtn("holdings") : ""}</div>
        <div class="card px-inset" style="padding:0">${ppHoldings(rows, total, uni)}</div>
      </div>
    </div>
  </div>

  <div class="px-ch">
    <div class="px-ch-n">02</div>
    <div class="px-ch-t">
      <h3>Against the desk's own rules</h3>
      <p class="sub" style="margin-bottom:10px">The desk holds itself to hard limits it cannot override. Your practice book is checked against the same ones — as <b>education about one specific discipline</b>, not a verdict on your portfolio.</p>
      ${ppRules(rows, total, invested, p, corr)}
    </div>
  </div>

  <div class="px-ch">
    <div class="px-ch-n">03</div>
    <div class="px-ch-t">
      <div style="display:flex;align-items:baseline;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:14px">
        <h3 style="margin:0">Try a trade</h3>
        <button class="note-save" onclick="paperReset()">Reset to Rs 500,000</button>
      </div>
      <div class="px-trade-grid">
        <div class="px-trade card">
          <div class="px-step"><span class="px-step-n">①</span><span class="px-step-lab">Ticker &amp; side</span>
            <input id="pp-sym" class="ph-in combo" type="search" enterkeyhint="next" aria-label="Ticker to trade" placeholder="Ticker (e.g. FFC)" autocomplete="off" style="flex:0 1 170px" oninput="ppSymChanged()">
            <span class="px-side"><button id="pp-buy" class="px-side-btn on" onclick="ppSide('buy')">Buy</button><button id="pp-sell" class="px-side-btn" onclick="ppSide('sell')">Sell</button></span></div>

          <div class="px-step"><span class="px-step-n">②</span><span class="px-step-lab">Size, by the desk formula</span></div>
          <div class="pp-form">
            <label class="dr-f">Capital (Rs)<input id="dz-cap" class="ph-in" type="text" inputmode="decimal" enterkeyhint="next" value="${Math.round(total) || PAPER_START}" oninput="deskSizeRun()"></label>
            <label class="dr-f">Entry (Rs)<input id="dz-entry" class="ph-in" type="text" inputmode="decimal" enterkeyhint="next" placeholder="e.g. 245.56" oninput="deskSizeRun()"></label>
            <label class="dr-f">Stop (Rs)<input id="dz-stop" class="ph-in" type="text" inputmode="decimal" enterkeyhint="done" placeholder="e.g. 233.28" oninput="deskSizeRun()"></label>
          </div>
          <div id="dz-out" class="sub" style="margin:8px 0">Enter an entry and a stop to size it.</div>
          <div class="px-step"><button class="note-save" onclick="ppUseSize()">Use this size</button>
            <span class="px-step-lab" style="margin-inline-start:10px">or shares, manually</span>
            <input id="pp-sh" class="ph-in" aria-label="Number of shares" type="text" inputmode="numeric" enterkeyhint="done" placeholder="Shares" style="flex:0 1 130px"></div>

          <div class="px-step"><span class="px-step-n">③</span><span class="px-step-lab">Why, in one sentence</span>
            <input id="pp-why" class="ph-in" type="text" placeholder="e.g. breakout above 20-day high on volume" style="flex:1 1 220px"></div>

          <div class="px-step"><button class="note-save" id="pp-go" onclick="paperTrade(ppSideVal)">Place order</button><span id="pp-msg" class="sub"></span></div>
          <p class="sub" style="margin-top:8px">Fills at the current DPS price — the same price the whole desk runs on. Writing the reason first, before the button, is the actual lesson.</p>
        </div>
        <div class="card px-inset" id="pp-tick-card">
          <p class="today-kicker">PRICE <span id="pp-tick-lab">· type a ticker</span></p>
          <div id="pp-tick-chart">${await ppTickChart("")}</div>
        </div>
      </div>
    </div>
  </div>

  <div class="px-ch">
    <div class="px-ch-n">04</div>
    <div class="px-ch-t">
      <h3>Journal</h3>
      <div class="px-jrn">
        ${(p.credits || []).length ? `<div class="seg"><h2>Dividends received</h2><div class="ln"></div></div>
        <div class="card px-inset" style="padding:0"><table><thead><tr><th>Stock</th><th class="r">Rs/sh</th><th class="r">Credited</th><th class="r">On closure</th></tr></thead><tbody>${
          p.credits.map(c => `<tr><td><b>${esc(c.sym)}</b></td><td class="r num">${c.rs}</td><td class="r num up">Rs ${fmt(c.amt)}</td><td class="r num">${esc(c.on)}</td></tr>`).join("")}</tbody></table>
        <div class="sub" style="padding:10px 15px">Simplified crediting: current shares × announced Rs/share once a book closure date passes, if the position predates it. Real settlements involve withholding tax and exact register timing.</div></div>` : ""}

        ${p.trades.length ? `<div class="seg"><h2>Trade log</h2><div class="ln"></div><span class="pill">${p.trades.length}</span></div>
        <div class="card px-inset" style="padding:0"><table><thead><tr><th>When</th><th>Side</th><th>Stock</th><th class="r">Shares</th><th class="r">Price</th><th class="r">Fee</th></tr></thead><tbody>${
          p.trades.slice().reverse().slice(0, 40).map(t => `<tr><td class="num sub">${esc(t.ts.slice(0, 16).replace("T", " "))}</td>
            <td><span class="pill ${t.side === "buy" ? "ok" : "bad"}">${t.side}</span></td><td><b>${esc(t.sym)}</b></td>
            <td class="r num">${t.sh}</td><td class="r num">${fmt(t.px)}</td><td class="r num">${t.fee}</td></tr>`).join("")}</tbody></table></div>
        <p class="sub" style="margin-top:10px">The log is the point — review it monthly and ask which trades had a written reason.</p>`
        : `<div class="empty">No trades logged yet.</div>`}
      </div>
    </div>
  </div>
  </div>`;

  deskSizeRun();
}

/* ---- ch03 small wiring, local to this page: buy/sell toggle, live ticker chart, "use this
   size" bridge into #pp-sh. paperTrade()/paperReset() themselves are app.js's, unchanged. ---- */
let ppSideVal = "buy";
function ppSide(side) {
  ppSideVal = side;
  const b = $("pp-buy"), s = $("pp-sell");
  if (b) b.classList.toggle("on", side === "buy");
  if (s) s.classList.toggle("on", side === "sell");
}
async function ppSymChanged() {
  const sym = ($("pp-sym")?.value || "").trim().toUpperCase();
  const lab = $("pp-tick-lab"), out = $("pp-tick-chart");
  if (lab) lab.textContent = sym ? "· " + sym : "· type a ticker";
  if (out) out.innerHTML = await ppTickChart(sym);
}
function ppUseSize() {
  const out = $("dz-out"); if (!out) return;
  const m = out.textContent.match(/^\s*([\d,]+)/);
  const cap = parseFloat(($("dz-cap")?.value || "").replace(/,/g, "")), entry = parseFloat($("dz-entry")?.value), stop = parseFloat($("dz-stop")?.value);
  const r = deskSize(cap, entry, stop);
  if (r && $("pp-sh")) $("pp-sh").value = r.shares;
}
