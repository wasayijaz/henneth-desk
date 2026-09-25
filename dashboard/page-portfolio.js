// portfolio page — redesign 2026-09
// Behaviour parity source: old-pagePortfolio.js (removed from app.js, kept for reference).
// New visual structure ported from docs/redesign-mockups/portfolio-mockup.html.
// Real data only — every number below comes from state/ via j(); nothing is invented.

let PF_SORT = { key: "w", dir: -1 };
let PF_TREE_MODE = "hold";
const PF_TOUCH = matchMedia("(hover: none)").matches;

function pfRs(v, d) { return v == null ? "—" : "Rs " + fmt(v, d == null ? 0 : d); }
function pfCls(v) { return v == null ? "" : v >= 0 ? "up" : "dn"; }
function pfPct(v) { return v == null || !isFinite(v) ? "—" : sgn(+v.toFixed(2)) + "%"; }
function pfFmtD(s) {
  if (!s) return "unknown";
  const d = new Date(s + "T12:00:00Z");
  if (isNaN(d)) return "unknown";
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}
function pfDays(s, today) { return Math.round((Date.parse(s + "T00:00:00Z") - Date.parse(today + "T00:00:00Z")) / 86400000); }

async function pagePortfolio() {
  if (!me) {
    $("view").innerHTML = `<div class="today-page pf-page">
      <div class="today-date">Portfolio</div>
      <div class="card"><div class="empty">Sign in to track your holdings — live value, profit/loss, weights and estimated dividend income. Private to you, read-only: the desk never trades. Research, not advice.<br><br>
      <button class="auth-go" style="max-width:220px" onclick="openAuth('signup')">Create a free account</button></div></div>
    </div>`;
    return;
  }

  const [quant, uni, live, divs, sectAll, fvAll, fsAll, deepDiv, calendar] = await Promise.all([
    j("quant.json"), j("universe.json"), j("live.json"), j("dividends.json"), j("sectors.json"),
    j("fairvalue.json"), j("fundamental_scores.json"), j("dividends_deep.json"), j("earnings_calendar.json")
  ]);

  const holdings = portfolio();
  const syms = holdings.map(h => h.ticker);
  const hist = {};
  await Promise.all(syms.map(s => j("history/" + s + ".json", 300000).then(
    h => { hist[s] = Array.isArray(h) ? h : null; },
    () => { hist[s] = null; }
  )));

  const q = quant?.tickers || {}, lv = live?.tickers || {}, names = uni?.symbols || {};
  const dHist = divs?.history || [];
  const events = calendar?.events || [];
  const today = new Date().toISOString().slice(0, 10);

  const rows = holdings.map(h => {
    const qq = q[h.ticker];
    const px = lv[h.ticker]?.current ?? qq?.close ?? null;
    const mv = px != null ? px * h.shares : null;
    const cost = h.avg_cost * h.shares;
    const pl = mv != null ? mv - cost : null;
    const plPct = (mv != null && cost > 0) ? (mv / cost - 1) * 100 : null;
    // Today's move: live price vs live prior close (ldcp); off-hours, quant's last 1-day return.
    const l = lv[h.ticker];
    const day = (l?.current != null && l?.ldcp) ? (l.current - l.ldcp) * h.shares
      : (px != null && qq?.ret_1d != null) ? (px - px / (1 + qq.ret_1d / 100)) * h.shares : null;
    const lastDiv = dHist.filter(d => d.symbol === h.ticker).sort((a, b) => (b.bc_start || "").localeCompare(a.bc_start || ""))[0];
    const annualDiv = lastDiv?.dividend_rs ? lastDiv.dividend_rs * h.shares : null;
    const h2 = hist[h.ticker];
    return {
      ...h, px, mv, cost, pl, plPct, annualDiv, day, hist: h2,
      name: names[h.ticker]?.name || "", known: !!qq,
      sector: (sectAll?.tickers?.[h.ticker] || {}).sector || null
    };
  });

  const totMv = rows.reduce((a, r) => a + (r.mv || 0), 0);
  const totCost = rows.reduce((a, r) => a + r.cost, 0);
  const totPl = totMv - totCost;
  const totPlPct = totCost > 0 ? (totMv / totCost - 1) * 100 : null;
  const totDiv = rows.reduce((a, r) => a + (r.annualDiv || 0), 0);
  const totDay = rows.reduce((a, r) => a + (r.day || 0), 0);
  const withW = rows.map(r => ({ ...r, w: totMv > 0 ? (r.mv || 0) / totMv * 100 : 0 })).sort((a, b) => b.w - a.w);
  const top = withW[0], top3 = withW.slice(0, 3).reduce((a, r) => a + r.w, 0);
  const concFlag = !withW.length ? "" :
    top.w >= 40 ? `Your largest position, <b>${esc(top.ticker)}</b>, is <b>${top.w.toFixed(0)}%</b> of the portfolio.`
      : top3 >= 65 && withW.length >= 3 ? `Your top 3 positions make up <b>${top3.toFixed(0)}%</b> of the portfolio.`
        : `Your largest position is <b>${top.w.toFixed(0)}%</b> — reasonably spread across ${withW.length} name${withW.length === 1 ? "" : "s"}.`;

  const secW = {};
  withW.forEach(r => { const k = r.sector || "Unclassified"; secW[k] = (secW[k] || 0) + r.w; });
  const secRows = Object.entries(secW).sort((a, b) => b[1] - a[1]);
  const topSec = secRows[0];
  const secFlag = !secRows.length ? "" :
    secRows.length === 1 ? `Every rupee you hold is in <b>${esc(topSec[0])}</b>. One sector shock moves your whole portfolio at once.`
      : topSec[1] >= 50 ? `<b>${topSec[1].toFixed(0)}%</b> of your portfolio sits in <b>${esc(topSec[0])}</b> — those names tend to rise and fall together, whatever their tickers say.`
        : `Your biggest sector is <b>${esc(topSec[0])}</b> at <b>${topSec[1].toFixed(0)}%</b>, spread across ${secRows.length} sectors.`;
  const dupSecSet = new Set(Object.entries(secW).filter(([k]) => k !== "Unclassified" && withW.filter(r => r.sector === k).length > 1).map(([k]) => k));

  const asof = withW.map(r => r.hist && r.hist.length ? r.hist[r.hist.length - 1].date : null).filter(Boolean).sort().pop();
  const ev = withW.flatMap(r => events.filter(e => e.ticker === r.ticker && pfDays(e.date, today) >= 0).map(e => ({ ...e })))
    .sort((a, b) => a.date.localeCompare(b.date))[0];
  const EV = { results: "results", ex_dividend: "ex-dividend", book_closure: "book closure" };

  const above = withW.filter(r => r.pl != null && r.pl > 0).length;

  const header = `<div class="today-date">Portfolio <span>· ${withW.length} holding${withW.length === 1 ? "" : "s"}${asof ? ` · close ${pfFmtD(asof)}` : ""}</span></div>`;

  const heroSub = withW.length
    ? `<p class="pf-hero-sub"><b>${above} of ${withW.length}</b> holding${withW.length === 1 ? "" : "s"} ${above === 1 ? "is" : "are"} above your average cost. Largest is <b>${esc(top.ticker)}</b> at ${top.w.toFixed(0)}% of value.${ev ? ` Next dated event: <b>${esc(ev.ticker)}</b> ${EV[ev.type] || ev.type} ${pfFmtD(ev.date)}${ev.confirmed ? "" : " (unconfirmed)"}.` : ""}</p>`
    : `<p class="pf-hero-sub">No holdings yet. Add one below to start tracking live value, profit/loss and position weights.</p>`;

  const hero = `<section class="today-hero">
    <div class="today-stance">
      <p class="today-kicker">YOUR PORTFOLIO <span>· at desk prices · private, read-only</span></p>
      <h1 class="pf-value">${withW.length ? pfRs(totMv, 0) : pfRs(0, 0)}</h1>
      <div class="pf-duo">
        <span><small>TODAY</small><b class="${pfCls(totDay)}">${withW.length ? pfRs(totDay, 0) : "—"}</b><em class="${pfCls(totDay)}">${withW.length && (totMv - totDay) ? pfPct(totDay / (totMv - totDay) * 100) : "—"}</em></span>
        <span><small>SINCE YOUR COST</small><b class="${pfCls(totPl)}">${withW.length ? pfRs(totPl, 0) : "—"}</b><em class="${pfCls(totPl)}">${pfPct(totPlPct)}</em></span>
      </div>
      ${heroSub}
    </div>
    <div class="today-index">
      <p class="today-kicker">VALUE OF TODAY'S HOLDINGS <span>· recent sessions · dashed = your cost</span></p>
      ${pfHistoryChart(withW, totCost)}
      <p class="today-chart-source">Today's share counts applied to past closes (state/history/&lt;ticker&gt;.json) — shows how this mix has moved, not your actual account history.</p>
    </div>
  </section>`;

  const addForm = `<form class="card pf-add" id="pf-add" onsubmit="event.preventDefault();submitHolding()" autocomplete="off">
    <label><small>TICKER</small><input id="ph-tkr" type="text" list="pf-tkrs" enterkeyhint="next" placeholder="e.g. FFC" autocapitalize="characters" spellcheck="false" required></label>
    <label><small>SHARES</small><input id="ph-sh" type="text" inputmode="numeric" enterkeyhint="next" placeholder="e.g. 500" required></label>
    <label><small>AVG COST / SHARE</small><span class="pf-rs"><i>Rs</i><input id="ph-cost" type="text" inputmode="decimal" enterkeyhint="done" placeholder="312.50" required></span></label>
    <button type="submit">+ Add holding</button>
    <p id="ph-msg" class="sub" aria-live="polite">Adding a ticker you already hold replaces that row. Stored privately on your account.</p>
    <datalist id="pf-tkrs">${Object.keys(names).sort().map(t => `<option value="${esc(t)}">${esc(names[t]?.name || "")}</option>`).join("")}</datalist>
  </form>`;

  if (!withW.length) {
    $("view").innerHTML = `<div class="today-page pf-page">
      ${header}${hero}
      <div class="today-section-head"><p class="today-kicker">ADD A HOLDING</p></div>
      ${addForm}
      <div class="card"><div class="empty">No holdings yet. Add one above — enter a ticker, how many shares, and your average cost, and the desk tracks your live value, profit/loss and position weights here.</div></div>
    </div>`;
    return;
  }

  const treeSection = `<div class="today-section-head"><p class="today-kicker">WHERE YOUR MONEY SITS <span>· box size = share of value · shade = today's move · ${PF_TOUCH ? "tap" : "point at"} to find the row</span></p>
    <div class="pf-chips" role="group" aria-label="Treemap grouping">
      <button data-mode="hold" aria-pressed="${PF_TREE_MODE === "hold"}">By holding</button>
      <button data-mode="sec" aria-pressed="${PF_TREE_MODE === "sec"}">By sector</button>
    </div></div>
  <div class="pf-tree" id="pf-tree">${pfTreeHtml(withW, dupSecSet)}</div>
  ${PF_TREE_MODE === "sec" ? '<p class="today-chart-source">Red outline = a sector holding more than one of your names.</p>' : ""}`;

  const fallSection = `<div class="today-section-head"><p class="today-kicker">FROM COST TO VALUE <span>· what each holding added or took away · net <b class="${pfCls(totPl)}">${pfRs(totPl, 0)}</b></span></p></div>
  ${pfWaterfallHtml(withW, totCost, totMv)}`;

  const tableSection = `<div class="today-section-head"><p class="today-kicker">HOLDINGS <span>· ${withW.length} · ${PF_TOUCH ? "tap" : "click"} a column to sort</span></p><div><b>close ${asof ? pfFmtD(asof) : "unknown"}</b></div></div>
  <div class="pf-controls"></div>
  <div class="card pf-hold" id="pf-holdwrap">${pfTableHtml(withW, totMv, totPl, totPlPct)}</div>
  <div class="pf-legend"><span><svg width="18" height="4"><line x1="0" x2="18" y1="2" y2="2" stroke="currentColor" stroke-width="2"/></svg>90-session range</span><span><svg width="10" height="10"><circle cx="5" cy="5" r="3.6" fill="currentColor"/></svg>price today</span><span><svg width="4" height="10"><line x1="2" x2="2" y1="0" y2="10" stroke="currentColor" stroke-width="1.5"/></svg>your cost</span></div>`;

  let xraySection = "";
  if (!hasFeature("xray")) {
    xraySection = `<div class="today-section-head"><p class="today-kicker">PORTFOLIO X-RAY <span>· facts about these holdings</span></p></div>${planWall("Portfolio X-ray",
      "Your holdings measured against the desk's own published risk rules: weighted beta, blended valuation, expected dividend income from real payout history, and how your concentration reads against the limits the desk imposes on itself.")}`;
  } else {
    xraySection = pfXrayHtml(withW, secW, fsAll, fvAll, deepDiv, top, dupSecSet);
  }

  const divSection = `<div class="today-section-head"><p class="today-kicker">DIVIDEND INCOME <span>· by month · last 12 months paid, next 2 declared</span></p></div>
  ${pfDividendsHtml(withW, deepDiv, dHist, today)}`;

  $("view").innerHTML = `<div class="today-page pf-page">
    ${header}${hero}
    <div class="today-section-head"><p class="today-kicker">ADD A HOLDING</p></div>
    ${addForm}
    ${treeSection}
    ${fallSection}
    ${tableSection}
    ${xraySection}
    ${divSection}
    <div class="today-section-head"><p class="today-kicker">CONCENTRATION <span>· fact, not advice</span></p></div>
    <div class="card">
      <p class="sub" style="line-height:1.6;margin-bottom:12px">${concFlag} Concentration means your portfolio rises and falls with fewer bets; diversification spreads that risk across more names. Whether that's right for you depends on your own goals and risk tolerance — the desk states the fact and the general principle, and never tells you to buy or sell.</p>
      <div class="ph-bars">${withW.map(r => `<div class="ph-bar-row"><span class="ph-bar-lbl">${esc(r.ticker)}</span><span class="ph-bar-track"><span class="ph-bar-fill" style="width:${Math.max(2, r.w).toFixed(0)}%"></span></span><span class="ph-bar-val num">${r.w.toFixed(0)}%</span></div>`).join("")}</div>
    </div>
    <div class="today-section-head"><p class="today-kicker">SECTOR CONCENTRATION <span>· ${secRows.length} sector${secRows.length === 1 ? "" : "s"}</span></p></div>
    <div class="card">
      <p class="sub" style="line-height:1.6;margin-bottom:12px">${secFlag} This is the exposure position weights hide: two banks are one bet on interest rates, and two cement names are one bet on construction — however different the tickers look. Sectors are PSX's own classification. Stated as a fact about your holdings, not as advice.</p>
      <div class="ph-bars">${secRows.map(([s, p]) => `<div class="ph-bar-row"><span class="ph-bar-lbl" title="${esc(s)}">${esc(s.length > 22 ? s.slice(0, 21) + "…" : s)}</span><span class="ph-bar-track"><span class="ph-bar-fill" style="width:${Math.max(2, p).toFixed(0)}%"></span></span><span class="ph-bar-val num">${p.toFixed(0)}%</span></div>`).join("")}</div>
    </div>
    <p class="pf-foot">A private, read-only tracker of what you own — the desk never places orders and holds no money. Every figure is arithmetic over your holdings at desk prices; none of it is advice or a recommendation to buy or sell. Estimated dividend income is each holding's most recent declared dividend applied to your shares — an estimate from past payouts, not a promise; companies can cut or skip dividends. Prices are desk end-of-day/live figures and may differ from your broker.</p>
    <div class="pf-tip" id="pf-tip"></div>
  </div>`;

  pfWire(document.getElementById("view").querySelector(".pf-page"), withW, totMv, totPl, totPlPct, dupSecSet, secW, fsAll, fvAll, deepDiv, top, dHist, today);
}

/* ---------- value-over-time history chart ---------- */
function pfHistoryChart(rows, totCost) {
  const withHist = rows.filter(r => r.hist && r.hist.length);
  if (!withHist.length) return `<div class="today-chart-source">History unknown — no price history on file for these holdings.</div>`;
  // union of dates from the holding with the longest history, capped to last 90 sessions
  const base = withHist.reduce((a, b) => (b.hist.length > a.hist.length ? b : a));
  const dates = base.hist.slice(-90).map(x => x.date);
  const series = dates.map(d => {
    let v = 0, known = 0;
    rows.forEach(r => {
      if (!r.hist) return;
      const pt = r.hist.find(x => x.date === d);
      if (pt) { v += pt.close * r.shares; known++; }
    });
    return known ? v : null;
  });
  const valid = series.filter(v => v != null);
  if (!valid.length) return `<div class="today-chart-source">History unknown.</div>`;
  const lo = Math.min(...valid, totCost), hi = Math.max(...valid, totCost);
  const W = 560, H = 140, P = { l: 4, r: 4, t: 8, b: 18 };
  const sx = i => P.l + (i / Math.max(1, dates.length - 1)) * (W - P.l - P.r);
  const sy = v => H - P.b - Math.max(0, Math.min(1, (v - lo) / ((hi - lo) || 1))) * (H - P.t - P.b);
  let ln = "", ar = `M${sx(0)},${H - P.b} `;
  series.forEach((v, i) => { if (v == null) return; const cmd = ln ? "L" : "M"; ln += `${cmd}${sx(i).toFixed(1)},${sy(v).toFixed(1)} `; ar += `L${sx(i).toFixed(1)},${sy(v).toFixed(1)} `; });
  ar += `L${sx(dates.length - 1).toFixed(1)},${H - P.b} Z`;
  const costY = sy(totCost).toFixed(1);
  return `<svg class="pf-hist" viewBox="0 0 ${W} ${H}" role="img" aria-label="Value of today's holdings applied to past closes">
    <path class="ar" d="${ar}" style="fill:var(--up)"/>
    <line class="cost" x1="${P.l}" x2="${W - P.r}" y1="${costY}" y2="${costY}"/>
    <path class="ln" d="${ln}" style="stroke:var(--up)"/>
  </svg>`;
}

/* ---------- squarified treemap ---------- */
function pfSquarify(items, x, y, w, h) {
  items = items.filter(i => i.v > 0);
  const total = items.reduce((a, i) => a + i.v, 0);
  if (!total || !items.length) return [];
  const scale = (w * h) / total;
  const out = [];
  function worst(row, len) {
    const s = row.reduce((a, i) => a + i.v * scale, 0);
    let mx = 0;
    row.forEach(i => { const r = Math.max((len * len * i.v * scale) / (s * s), (s * s) / (len * len * i.v * scale)); if (r > mx) mx = r; });
    return mx;
  }
  let rest = [...items].sort((a, b) => b.v - a.v);
  let cx = x, cy = y, cw = w, ch = h;
  while (rest.length) {
    const len = Math.min(cw, ch);
    let row = [rest[0]], i = 1;
    while (i < rest.length && worst(row.concat(rest[i]), len) <= worst(row, len)) { row.push(rest[i]); i++; }
    rest = rest.slice(row.length);
    const rowArea = row.reduce((a, it) => a + it.v * scale, 0);
    if (cw >= ch) {
      const rw = rowArea / ch;
      let ry = cy;
      row.forEach(it => { const rh = (it.v * scale) / rw; out.push({ ...it, x: cx, y: ry, w: rw, h: rh }); ry += rh; });
      cx += rw; cw -= rw;
    } else {
      const rh = rowArea / cw;
      let rx = cx;
      row.forEach(it => { const rw = (it.v * scale) / rh; out.push({ ...it, x: rx, y: cy, w: rw, h: rh }); rx += rw; });
      cy += rh; ch -= rh;
    }
  }
  return out;
}
function pfTreeHtml(rows, dupSecSet) {
  const W = 1080, H = 300;
  let items;
  if (PF_TREE_MODE === "sec") {
    const bySec = {};
    rows.forEach(r => { const k = r.sector || "Unclassified"; (bySec[k] = bySec[k] || []).push(r); });
    items = Object.entries(bySec).map(([k, rs]) => ({
      k, v: rs.reduce((a, r) => a + (r.mv || 0), 0),
      day: rs.reduce((a, r) => a + (r.day || 0), 0),
      pct: rs.reduce((a, r) => a + r.w, 0),
      dbl: dupSecSet.has(k), tick: rs.map(r => r.ticker).join(", ")
    }));
  } else {
    items = rows.map(r => ({ k: r.ticker, v: r.mv || 0, day: r.day, pct: r.w, dbl: r.sector && dupSecSet.has(r.sector), tick: r.ticker }));
  }
  const placed = pfSquarify(items, 0, 0, W, H);
  return `<div style="position:relative;width:100%;height:100%">${placed.map(it => {
    const small = it.w * it.h < 5200;
    return `<button style="left:${(it.x / W * 100).toFixed(3)}%;top:${(it.y / H * 100).toFixed(3)}%;width:${(it.w / W * 100).toFixed(3)}%;height:${(it.h / H * 100).toFixed(3)}%" class="${it.dbl ? "dbl" : ""}${small ? " small" : ""}" data-tip="${esc(`${it.k} · ${it.pct.toFixed(1)}% of value · ${pfRs(it.v, 0)}${it.day != null ? " · today " + pfPct(it.v ? it.day / (it.v - it.day) * 100 : 0) : ""}`)}" data-go="${esc(it.tick.split(",")[0].trim())}">
      <b>${esc(it.k)}</b><em class="${pfCls(it.day)}">${it.pct.toFixed(0)}%</em><span class="sub">${it.day != null ? pfRs(it.day, 0) : ""}</span>
    </button>`;
  }).join("")}</div>`;
}

/* ---------- waterfall: cost -> value ---------- */
function pfWaterfallHtml(rows, totCost, totMv) {
  const W = 900, H = 200, P = { l: 60, r: 20, t: 16, b: 40 };
  const steps = [{ k: "COST", v: totCost }, ...rows.map(r => ({ k: r.ticker, v: r.pl || 0, tick: r.ticker })), { k: "VALUE", v: totMv }];
  const hi = Math.max(totCost, totMv, ...rows.map(r => r.mv || 0)) * 1.05;
  const bw = (W - P.l - P.r) / steps.length;
  const sy = v => H - P.b - Math.max(0, Math.min(1, v / (hi || 1))) * (H - P.t - P.b);
  let cum = 0, g = "";
  steps.forEach((s, i) => {
    const x = P.l + i * bw + bw * 0.15, w = bw * 0.7;
    let y0, y1, isEnd = s.k === "COST" || s.k === "VALUE";
    if (isEnd) { y0 = sy(0); y1 = sy(s.v); cum = s.v; }
    else { const from = cum; cum += s.v; y0 = sy(Math.min(from, cum)); y1 = sy(Math.max(from, cum)); }
    const cls = isEnd ? "up" : s.v >= 0 ? "up" : "dn";
    g += `<g${s.tick ? ` data-go="${esc(s.tick)}"` : ""} data-tip="${esc(s.k + " · " + pfRs(s.v, 0))}">
      <rect x="${x.toFixed(1)}" y="${Math.min(y0, y1).toFixed(1)}" width="${w.toFixed(1)}" height="${Math.max(1, Math.abs(y1 - y0)).toFixed(1)}" style="fill:var(--${cls})" opacity="${isEnd ? 1 : 0.75}"/>
      <text class="lbl" x="${(x + w / 2).toFixed(1)}" y="${H - P.b + 14}" text-anchor="middle">${esc(s.k.length > 6 ? s.k.slice(0, 6) : s.k)}</text>
    </g>`;
  });
  return `<div class="pf-fall"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Waterfall from total cost to current value, one step per holding">${g}</svg></div>`;
}

/* ---------- per-holding 90-session range sparkline ---------- */
function pfRangeSpark(r) {
  if (!r.hist || !r.hist.length || r.px == null) return `<span class="sub mut">—</span>`;
  const h = r.hist.slice(-90).map(x => x.close);
  const lo = Math.min(...h), hi = Math.max(...h), W = 120;
  const sx = v => 4 + Math.max(0, Math.min(1, (v - lo) / ((hi - lo) || 1))) * (W - 8);
  const out = r.avg_cost < lo ? "◂" : r.avg_cost > hi ? "▸" : "";
  return `<svg class="pf-range" viewBox="0 0 ${W} 18" data-tip="${esc(`${r.ticker} · 90-session range ${fmt(lo)}–${fmt(hi)} · your cost ${fmt(r.avg_cost)}${out ? " (outside range)" : ""} · price ${fmt(r.px)}`)}">
    <line class="tr" x1="4" x2="${W - 4}" y1="9" y2="9"/>
    <line class="ck" x1="${sx(r.avg_cost).toFixed(1)}" x2="${sx(r.avg_cost).toFixed(1)}" y1="3" y2="15"/>${out ? `<text x="${out === "◂" ? 0 : W - 6}" y="6">${out}</text>` : ""}
    <circle cx="${sx(r.px).toFixed(1)}" cy="9" r="3.6" style="fill:var(${r.px >= r.avg_cost ? "--up" : "--dn"})"/></svg>`;
}

/* ---------- holdings table ---------- */
function pfTableHtml(rows, totMv, totPl, totPlPct) {
  const cols = [
    ["t", "Holding"], ["sh", "Shares"], ["ac", "Avg cost"], ["px", "Price"], ["day", "Today"],
    ["mv", "Value"], ["pl", "Profit·loss"], ["w", "Weight"], ["rg", "Cost vs range"]
  ];
  const key = PF_SORT.key, dir = PF_SORT.dir;
  const sorted = [...rows].sort((a, b) => {
    const va = key === "t" ? a.ticker : key === "sh" ? a.shares : key === "ac" ? a.avg_cost : key === "px" ? a.px : key === "day" ? a.day : key === "mv" ? a.mv : key === "pl" ? a.pl : a.w;
    const vb = key === "t" ? b.ticker : key === "sh" ? b.shares : key === "ac" ? b.avg_cost : key === "px" ? b.px : key === "day" ? b.day : key === "mv" ? b.mv : key === "pl" ? b.pl : b.w;
    if (va == null) return 1; if (vb == null) return -1;
    return va < vb ? -1 * dir : va > vb ? 1 * dir : 0;
  });
  return `<table class="today-table"><thead><tr>${cols.map(([k, l]) => `<th${k === "rg" ? "" : ` data-sort="${k}"`}${k === key ? ` aria-sort="${dir === 1 ? "ascending" : "descending"}"` : ""}>${l}</th>`).join("")}<th></th></tr></thead><tbody>${
    sorted.map(r => `<tr data-t="${esc(r.ticker)}">
      <td class="clickable" onclick="navigate('/ticker/${esc(r.ticker)}')"><b>${esc(r.ticker)}</b> <span class="sub">${esc((r.name || "").slice(0, 16))}</span>${r.known ? "" : ' <span class="sub dn">not in universe</span>'}</td>
      <td class="r num">${fmt(r.shares)}</td>
      <td class="r num">${fmt(r.avg_cost)}</td>
      <td class="r num">${r.px != null ? fmt(r.px) : "—"}</td>
      <td class="r num ${pfCls(r.day)}">${r.day != null ? pfRs(r.day, 0) : "—"}</td>
      <td class="r num">${r.mv != null ? fmt(r.mv, 0) : "—"}</td>
      <td class="r num ${pfCls(r.pl)}">${pfPct(r.plPct)}${r.pl != null ? `<div class="sub">${(r.pl >= 0 ? "+" : "") + fmt(r.pl, 0)}</div>` : ""}</td>
      <td class="r"><span class="pf-w"><i style="width:${Math.max(2, r.w * 0.5).toFixed(0)}px"></i>${r.w.toFixed(0)}%</span></td>
      <td class="r">${pfRangeSpark(r)}</td>
      <td class="r"><button class="pf-del" data-del="${esc(r.ticker)}" aria-label="Remove ${esc(r.ticker)}" title="Remove holding">✕</button></td></tr>`).join("")
  }</tbody><tfoot><tr><td><b>Total</b></td><td></td><td></td><td></td><td></td><td class="r num"><b>${fmt(totMv, 0)}</b></td>
    <td class="r num ${pfCls(totPl)}"><b>${pfPct(totPlPct)}</b></td><td></td><td></td><td></td></tr></tfoot></table>`;
}

/* ---------- X-ray: the desk's own rules, run over the user's actual mix ---------- */
function pfMeter(v, max, lim, ok, l) {
  const pv = Math.max(0, Math.min(1, v / max)) * 100, pl = Math.max(0, Math.min(1, lim / max)) * 100;
  return `<div class="pf-meter"><i style="width:${pv.toFixed(1)}%;background:var(${ok ? "--up" : "--dn"})"></i><s style="left:${pl.toFixed(1)}%" data-l="${l}"></s></div>`;
}
function pfRule(ok, k, why, viz, v) {
  return `<div class="pf-rule"><span class="mk" style="color:var(${ok ? "--up" : "--dn"});border-color:var(${ok ? "--up" : "--dn"})">${ok ? "✓" : "!"}</span>
    <div><b>${esc(k)}</b><p>${why}</p></div>${viz}<span class="v">${v}</span></div>`;
}
function pfXrayHtml(withW, secW, fsAll, fvAll, deepDiv, top, dupSecSet) {
  const FS = fsAll?.tickers || {}, FV = fvAll?.tickers || {};
  const wsum = withW.reduce((a, r) => a + (r.mv || 0), 0) || 1;
  let bW = 0, bCov = 0, yW = 0, yCov = 0, gapW = 0, gapCov = 0;
  withW.forEach(r => {
    const m = FS[r.ticker]?.metrics || {}, fv = FV[r.ticker] || {};
    if (m.beta != null) { bW += m.beta * (r.mv || 0); bCov += (r.mv || 0); }
    if (m.div_yield != null) { yW += m.div_yield * (r.mv || 0); yCov += (r.mv || 0); }
    if (fv.mispricing_pct != null) { gapW += fv.mispricing_pct * (r.mv || 0); gapCov += (r.mv || 0); }
  });
  const beta = bCov ? bW / bCov : null, yld = yCov ? yW / yCov : null, gap = gapCov ? gapW / gapCov : null;
  const cutoff = new Date(Date.now() - 365 * 86400000).toISOString().slice(0, 10);
  let expDiv = 0, divCov = 0;
  withW.forEach(r => {
    const pays = (deepDiv?.tickers?.[r.ticker] || []).filter(p => p.ex >= cutoff);
    if (pays.length) { expDiv += pays.reduce((a, p) => a + p.rs, 0) * r.shares; divCov += (r.mv || 0); }
  });
  const dupList = [...dupSecSet];
  /* PUBLICATION FRAME (docs/PUBLICATION_RESTRUCTURE.md §2a) — preserved verbatim from
     old-pagePortfolio.js: `k`/`why` state the desk's OWN rule and its impersonal reason
     (identical for every reader, already-published methodology); `v`/`ok` are pure arithmetic
     over the reader's own holdings (tracking, explicitly allowed). Never add prose narrating
     what the reader's specific mix *means* — stating a rule and showing a number is reference;
     narrating the conclusion is advisory and crosses the line. */
  const checks = [
    { ok: withW.length <= 4, k: "Max 4 concurrent positions", v: `${withW.length} holding${withW.length === 1 ? "" : "s"}`,
      why: "The desk caps itself at 4 open positions so each one gets real attention.",
      viz: pfMeter(withW.length, Math.max(withW.length, 4) + 1, 4, withW.length <= 4, "4") },
    { ok: !dupList.length, k: "No two positions in one sector", v: dupList.length ? `${dupList.map(k => esc(k)).join(", ")} doubled` : "none doubled",
      why: "The desk allows itself one position per sector — two names in one sector is one bet wearing two tickers.",
      viz: `<div class="pf-secchips">${Object.keys(secW).map(k => `<span class="${dupSecSet.has(k) ? "x" : ""}">${esc(k)}</span>`).join("")}</div>` },
    { ok: top ? top.w <= 20 : true, k: "Position ≤ 20% of capital", v: top ? `largest ${esc(top.ticker)} ${top.w.toFixed(0)}%` : "—",
      why: "The desk caps any single position at 20% of capital, so one company's bad quarter cannot set the whole result.",
      viz: top ? pfMeter(top.w, 100, 20, top.w <= 20, "20%") : "" },
  ];
  const nPass = checks.filter(c => c.ok).length;
  return `<div class="today-section-head"><p class="today-kicker">PORTFOLIO X-RAY <span>· facts about these holdings</span></p><div><b>${nPass}/${checks.length} desk rules met</b></div></div>
  <p class="sub" style="margin-bottom:12px">The desk's own risk rules, run over your actual holdings — the constraints the desk imposes on itself, shown so you can see how your mix reads against them. Not instructions, and not a suggestion to trade.</p>
  <div class="today-radar-cards">
    <div class="today-radar-card"><span class="today-kicker">WEIGHTED BETA</span><b>${beta != null ? beta.toFixed(2) : "unknown"}</b>
      ${beta != null ? `<svg class="pf-gauge" viewBox="0 0 200 22"><line x1="4" x2="196" y1="11" y2="11" stroke="var(--rline)"/><line x1="100" x2="100" y1="4" y2="18" stroke="var(--ink3)"/><circle cx="${Math.max(4, Math.min(196, beta / 2 * 200)).toFixed(1)}" cy="11" r="4" style="fill:var(--ink1)"/><text x="100" y="21" text-anchor="middle">market = 1.0</text></svg>` : ""}
      <span class="sub">${(bCov / wsum * 100).toFixed(0)}% of value covered</span></div>
    <div class="today-radar-card"><span class="today-kicker">BLENDED YIELD</span><b>${yld != null ? yld.toFixed(2) + "%" : "unknown"}</b><span class="sub">${(yCov / wsum * 100).toFixed(0)}% of value covered</span></div>
    <div class="today-radar-card"><span class="today-kicker">DIVIDENDS · LAST 12 MONTHS</span><b class="${divCov ? "up" : ""}">${divCov ? pfRs(expDiv, 0) : "unknown"}</b><span class="sub">from real trailing payouts, not a forecast</span></div>
    <div class="today-radar-card"><span class="today-kicker">VS MODEL FAIR VALUE</span><b class="${gap > 0 ? "up" : gap < 0 ? "dn" : ""}">${gap != null ? sgn(+gap.toFixed(1)) + "%" : "unknown"}</b><span class="sub">value-weighted across holdings</span></div>
  </div>
  <div class="pf-rules">${checks.map(c => pfRule(c.ok, c.k, c.why, c.viz, esc(c.v))).join("")}</div>
  <p class="sub xr-foot" style="margin-top:6px">Beta and yield are value-weighted over the holdings the desk has data for; coverage is stated so a partial figure is never mistaken for a complete one.</p>`;
}

/* ---------- dividend income by month ---------- */
function pfDividendsHtml(rows, deepDiv, dHist, today) {
  const cutoff = new Date(Date.now() - 365 * 86400000).toISOString().slice(0, 10);
  const months = [];
  for (let i = -11; i <= 2; i++) { const d = new Date(); d.setUTCDate(1); d.setUTCMonth(d.getUTCMonth() + i); months.push(d.toISOString().slice(0, 7)); }
  const paid = {}, declared = {};
  rows.forEach(r => {
    (deepDiv?.tickers?.[r.ticker] || []).filter(p => p.ex >= cutoff).forEach(p => {
      const m = p.ex.slice(0, 7); if (months.includes(m)) paid[m] = (paid[m] || 0) + p.rs * r.shares;
    });
    dHist.filter(d => d.symbol === r.ticker && d.bc_start >= today).forEach(d => {
      const m = d.bc_start.slice(0, 7); if (months.includes(m)) declared[m] = (declared[m] || 0) + (d.dividend_rs || 0) * r.shares;
    });
  });
  const vals = months.map(m => (paid[m] || 0) + (declared[m] || 0));
  const hi = Math.max(1, ...vals);
  if (!vals.some(v => v > 0)) return `<div class="today-chart-source">No dividend history or declared dividends on file for these holdings.</div>`;
  const W = 720, H = 180, P = { l: 44, r: 10, t: 10, b: 26 }, bw = (W - P.l - P.r) / months.length;
  const sy = v => H - P.b - Math.max(0, Math.min(1, v / hi)) * (H - P.t - P.b);
  let g = "", ys = hi > 4000 ? 1000 : 200;
  for (let v = 0; v <= hi; v += ys) g += `<line class="grid" x1="${P.l}" x2="${W - P.r}" y1="${sy(v).toFixed(1)}" y2="${sy(v).toFixed(1)}"/><text x="${P.l - 6}" y="${(sy(v) + 3).toFixed(1)}" text-anchor="end">${(v / 1000).toFixed(0)}k</text>`;
  const nowX = P.l + 12 * bw;
  months.forEach((m, i) => {
    const x = P.l + i * bw + bw * 0.15, w = bw * 0.7;
    const isPaid = (paid[m] || 0) > 0, isDecl = (declared[m] || 0) > 0;
    const v = (paid[m] || 0) + (declared[m] || 0);
    if (v > 0) {
      const y = sy(v);
      g += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${(H - P.b - y).toFixed(1)}" style="fill:var(--up)" opacity="${isPaid ? 0.85 : 0.35}" stroke="${isDecl && !isPaid ? "var(--up)" : "none"}" stroke-dasharray="${isDecl && !isPaid ? "3 2" : "none"}"/>`;
    }
    g += `<text x="${(x + w / 2).toFixed(1)}" y="${H - P.b + 14}" text-anchor="middle">${m.slice(5)}</text>`;
  });
  g += `<line class="now" x1="${nowX.toFixed(1)}" x2="${nowX.toFixed(1)}" y1="${P.t}" y2="${H - P.b}"/>`;
  return `<div class="pf-divs"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Dividend income by month, last 12 months paid and next 2 declared">${g}</svg></div>
  <div class="pf-legend"><span><svg width="10" height="10"><rect width="9" height="9" fill="currentColor" opacity=".85"/></svg>paid</span><span><svg width="10" height="10"><rect width="9" height="9" fill="none" stroke="currentColor" stroke-dasharray="3 2"/></svg>declared, not yet paid</span></div>
  <p class="today-chart-source">Source: dividends_deep.json (paid, by ex-date) and dividends.json (declared) × your share counts. History, not a forecast — companies cut and skip dividends.</p>`;
}

/* ---------- interactivity: treemap toggle, sort, tooltips ---------- */
function pfWire(root, withW, totMv, totPl, totPlPct, dupSecSet, secW, fsAll, fvAll, deepDiv, top, dHist, today) {
  if (!root) return;
  const tip = root.querySelector("#pf-tip");
  function showTip(el, x, y) {
    const t = el.getAttribute("data-tip"); if (!t || !tip) return;
    tip.textContent = t; tip.style.display = "block";
    tip.style.left = Math.min(x + 12, window.innerWidth - 300) + "px";
    tip.style.top = Math.min(y + 12, window.innerHeight - 60) + "px";
  }
  function hideTip() { if (tip) tip.style.display = "none"; }
  root.addEventListener("pointermove", e => {
    if (PF_TOUCH) return;
    const el = e.target.closest("[data-tip]");
    if (el) showTip(el, e.clientX, e.clientY); else hideTip();
  });
  root.addEventListener("pointerleave", hideTip);

  root.addEventListener("click", e => {
    const del = e.target.closest("[data-del]");
    if (del) { removeHolding(del.getAttribute("data-del")); return; }

    const go = e.target.closest("[data-go]");
    if (go && PF_TOUCH) { const t = go.getAttribute("data-tip"); if (t) { showTip(go, e.clientX, e.clientY); e.stopPropagation(); return; } }
    if (go) { const tkr = go.getAttribute("data-go"); if (tkr) navigate("/ticker/" + tkr); return; }

    const mode = e.target.closest("[data-mode]");
    if (mode) {
      PF_TREE_MODE = mode.getAttribute("data-mode");
      root.querySelectorAll("[data-mode]").forEach(b => b.setAttribute("aria-pressed", b === mode));
      const treeEl = root.querySelector("#pf-tree");
      if (treeEl) treeEl.innerHTML = pfTreeHtml(withW, dupSecSet);
      return;
    }

    const sortTh = e.target.closest("th[data-sort]");
    if (sortTh) {
      const k = sortTh.getAttribute("data-sort");
      PF_SORT = { key: k, dir: PF_SORT.key === k ? -PF_SORT.dir : -1 };
      const wrap = root.querySelector("#pf-holdwrap");
      if (wrap) wrap.innerHTML = pfTableHtml(withW, totMv, totPl, totPlPct);
      return;
    }
  });
}
