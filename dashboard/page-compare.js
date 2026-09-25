// compare page — redesign 2026-09
// Behaviour parity source: old pageCompare (removed from app.js, kept for reference in git history).
// New visual structure ported from docs/redesign-mockups/compare-mockup.html.
// Real data only — every number below comes from state/ via j(); nothing is invented.
// The mockup's sample numbers (its hardcoded `const D` blob) were placeholders only and are
// not used here — this file re-derives everything from the same state files the old
// pageCompare read (quant, fairvalue, fundamentals, fundamental_scores, predictability,
// sectors, universe, backtests), plus per-symbol history/<SYM>.json for the price path.

const CMP_TOUCH = matchMedia("(hover: none)").matches;
const CMP_MAX = 4;
const CMP_RANGES = { "3M": 63, "6M": 126, "1Y": 252, "3Y": 756 };
// series mark: colour (--s0..--s3, set in page-compare.css) + dash class, same scheme for
// swatches, name-card top border and chart lines — mirrors compare-mockup.html's DASH/ser/sw.
const CMP_DASH = ["", "", "d2", "d3"];

let CMP = { syms: [], pin: null, range: "1Y", off: new Set(), open: new Set(), ts: { k: null, d: -1 }, rs: 0, topen: false, xi: null };

function cmpPct(v, d = 1) { return v == null || !isFinite(v) ? "unknown" : sgn(+v.toFixed(d)) + "%"; }
function cmpX(v) { return v == null || !isFinite(v) ? "unknown" : (v > 0 ? "+" : "") + v.toFixed(1) + "%"; }
function cmpRs(v, d = 2) { return v == null || !isFinite(v) ? "unknown" : "Rs " + fmt(v, d); }
function cmpNum(v, d = 1) { return v == null || !isFinite(v) ? "unknown" : fmt(v, d); }
function cmpDate(s) {
  if (!s) return "unknown";
  const d = new Date(String(s).slice(0, 10) + "T12:00:00Z");
  if (isNaN(d)) return "unknown";
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}
const cmpVerd = { under: "reads undervalued", fair: "reads fair", over: "reads overvalued" };

/* ---------- data ---------- */
async function cmpLoadState() {
  const [q, fv, fu, fs, pr, sec, uni, bt] = await Promise.all([
    j("quant.json"), j("fairvalue.json"), j("fundamentals.json"), j("fundamental_scores.json"),
    j("predictability.json"), j("sectors.json"), j("universe.json"), j("backtests.json"),
  ]);
  return { q, fv, fu, fs, pr, sec, uni, bt };
}

function cmpParsePct(s) { const v = parseFloat(s); return isFinite(v) ? v : null; }

function cmpBuildT(D, s) {
  const q = D.q?.tickers?.[s] || {};
  const fv = D.fv?.tickers?.[s] || null;
  const fuRaw = D.fu?.tickers?.[s] || null;
  const fsRow = D.fs?.tickers?.[s] || null;
  const prRow = D.pr?.tickers?.[s] || null;
  const provenCount = Object.values(D.bt?.templates || {}).reduce((n, per) => n + (per?.[s]?.eligible ? 1 : 0), 0);
  return {
    name: D.uni?.symbols?.[s]?.name || "",
    sector: D.sec?.tickers?.[s]?.sector || null,
    q: { close: q.close ?? null, ret_1d: q.ret_1d ?? null, ret_5d: q.ret_5d ?? null, ret_20d: q.ret_20d ?? null, rsi14: q.rsi14 ?? null, sma50: q.sma50 ?? null },
    fv: fv ? { fair: fv.composite_fair ?? null, gap: fv.mispricing_pct ?? null, verdict: fv.verdict ?? null, methods: fv.methods || null, pe: fv.pe ?? null } : null,
    fu: fuRaw,
    dy: fuRaw ? cmpParsePct(fuRaw.div_yield) : null,
    payout: fuRaw ? cmpParsePct(fuRaw.payout_ratio) : null,
    fs: fsRow ? { rating: fsRow.rating || null, pe: fsRow.metrics?.pe ?? null, fpe: fsRow.metrics?.forward_pe ?? null } : null,
    pr: prRow ? { score: prRow.score ?? null, n: prRow.total_signals ?? null } : null,
    proven: provenCount,
  };
}

/* ---------- picker / selection ---------- */
function cmpAdd2(raw) {
  const sym = (raw || "").trim().toUpperCase();
  if (!sym) return;
  if (CMP.syms.includes(sym)) return;
  if (CMP.syms.length >= CMP_MAX) return;
  CMP.syms.push(sym);
  pageCompare();
}
function cmpDrop2(sym) { CMP.syms = CMP.syms.filter(x => x !== sym); CMP.off.delete(sym); if (CMP.pin === sym) CMP.pin = null; pageCompare(); }
function cmpMove(sym, by) {
  const i = CMP.syms.indexOf(sym); if (i < 0) return;
  const j2 = i + by; if (j2 < 0 || j2 >= CMP.syms.length) return;
  [CMP.syms[i], CMP.syms[j2]] = [CMP.syms[j2], CMP.syms[i]];
  pageCompare();
}

/* ---------- main entry ---------- */
async function pageCompare() {
  const D = await cmpLoadState();
  const known = CMP.syms.filter(s => D.q?.tickers?.[s]);
  const missing = CMP.syms.filter(s => !D.q?.tickers?.[s]);
  CMP.syms = known;
  const T = {}; CMP.syms.forEach(s => { T[s] = cmpBuildT(D, s); });

  const hist = {};
  await Promise.all(CMP.syms.map(s => j("history/" + s + ".json", 300000).then(
    h => { hist[s] = Array.isArray(h) ? h : []; },
    () => { hist[s] = []; }
  )));

  const nstrat = D.bt?.n_strategies ?? Object.keys(D.bt?.templates || {}).length;
  const asof = {
    quant: D.q?.updated || "unknown", fairvalue: D.fv?.updated || "unknown", fundamentals: D.fu?.updated || "unknown",
    fundamental_scores: D.fs?.updated || "unknown", predictability: D.pr?.updated || "unknown", backtests: D.bt?.updated || "unknown",
  };

  const view = $("view");
  view.innerHTML = `<div class="today-page cmp-page">
    <div class="today-date">Compare <span>· ${CMP.syms.length} of ${CMP_MAX} names${CMP.syms.length ? " · data as of " + esc(asof.quant) + " PKT" : ""}</span></div>
    <div class="cx-tip" id="cmp-tip"></div>
    <section class="cx-ch first">${cmpPicker(missing)}</section>
    ${cmpBody(T, hist, nstrat, asof)}
  </div>`;

  cmpCharts(hist);
  cmpWire(view.querySelector(".cmp-page"), T, hist, nstrat);
}

function cmpBody(T, hist, nstrat, asof) {
  const n = CMP.syms.length;
  if (n < 2) return `<div class="cx-ch"><div class="cx-card cx-empty">Pick at least two names. Up to four fit side by side.</div></div>`;
  const head = (no, k, sub, right = "") => `<div class="today-section-head"><p class="today-kicker">${no} · ${k} <span>· ${sub}</span></p><div>${right}</div></div>`;
  return `
  <section class="cx-ch">
    ${head("01", "SIDE BY SIDE", "where each name stands today")}
    ${cmpNames(T)}
  </section>
  <section class="cx-ch">
    ${head("02", "THE PRICE PATH", "rebased to 100", `<div class="wl-chips" role="group" aria-label="Range">${Object.keys(CMP_RANGES).map(k => `<button data-range="${k}" aria-pressed="${k === CMP.range}">${esc(k)}</button>`).join("")}</div>`)}
    <div class="cx-card" style="margin-top:20px">
      <div class="cx-ctrl"><div class="cx-legend" role="group" aria-label="Lines on the chart">${CMP.syms.map((s, i) => `<button class="cx-lg" data-lg="${esc(s)}" data-sym="${esc(s)}" aria-pressed="${!CMP.off.has(s)}" aria-label="${esc(s)} line">${cmpSw(i)}<b>${esc(s)}</b></button>`).join("")}<span><i class="sw d3" style="--sc:var(--ink3)"></i>100 = start of range</span></div></div>
      <div id="cmp-pathchart"></div>
      <p class="cx-cap">Daily closes from <code>state/history/&lt;symbol&gt;.json</code>, rebased so every line starts at 100. ${CMP_TOUCH ? "Tap the chart" : "Hover the chart"} for the exact day; tap a name above to hide or show its line.</p>
    </div>
  </section>
  <section class="cx-ch">
    ${head("03", "MEASURE BY MEASURE", "valuation, quality, momentum, dividends")}
    ${cmpSets(T)}
  </section>
  <section class="cx-ch">
    ${head("04", "THE DESK'S READ", "plain words, no call")}
    ${cmpRead(T, nstrat)}
  </section>
  <section class="cx-ch">
    ${head("05", "EVERY NUMBER", "the full grid, for export")}
    <div id="cmp-tblwrap">${cmpTable(T, nstrat)}</div>
  </section>
  <p class="pf-foot">Model fair value is an estimate from four methods that often disagree; it is not a price target. "Strategies proven here" counts are not comparable across names with different amounts of history (here: ${CMP.syms.map(s => `${esc(s)} ${(hist[s] || []).length} sessions`).join(", ")}). Research only — the desk never places orders and nothing here is a recommendation. Terms: <a href="/glossary">glossary</a>.
  Sources: quant ${esc(asof.quant)} · fair value ${esc(asof.fairvalue)} · fundamentals ${esc(asof.fundamentals)} · scores ${esc(asof.fundamental_scores)} · predictability ${esc(asof.predictability)} · backtests ${esc(asof.backtests)} PKT.</p>`;
}

function cmpSw(i) { return `<i class="sw ${CMP_DASH[i]}" style="--sc:var(--s${i})" aria-hidden="true"></i>`; }

/* ---------- 01 picker ---------- */
function cmpPicker(missing) {
  const n = CMP.syms.length;
  return `<div class="cx-card cx-pick">
    <div>
      <form id="cmp-form" class="cx-form">
        <input id="cmp-in" class="ph-in combo" aria-label="Add a company to compare" placeholder="Add a company — type a symbol" ${n >= CMP_MAX ? "disabled" : ""}>
        <button type="submit" class="cx-btn" ${n >= CMP_MAX ? "disabled" : ""}>Add</button>
      </form>
      <div class="cx-chips">${CMP.syms.map((s, i) => `<span class="cx-chip" data-sym="${esc(s)}" data-pin="${esc(s)}">${cmpSw(i)}<span>${esc(s)}</span><button data-drop="${esc(s)}" aria-label="Remove ${esc(s)}" title="Remove ${esc(s)}">✕</button></span>`).join("")}</div>
      ${missing.length ? `<div class="cx-warn">No data for ${missing.map(esc).join(", ")} — check the symbol, or it may be a PSX board counter rather than a tradeable company.</div>` : (n === 0 ? `<div class="cx-warn">Add two or more names to compare them.</div>` : "")}
    </div>
    <div class="cx-count">NAMES<b>${n}/${CMP_MAX}</b><div class="cx-slots">${Array.from({ length: CMP_MAX }, (_, i) => `<i class="${i < n ? "on" : ""}"></i>`).join("")}</div></div>
  </div>`;
}

/* ---------- 02 name cards ---------- */
function cmpNames(T) {
  return `<div class="cx-names" style="--n:${CMP.syms.length}">${CMP.syms.map((s, i) => {
    const t = T[s];
    const last = i === CMP.syms.length - 1;
    return `<div class="cx-card cx-name ${CMP_DASH[i]}" data-sym="${esc(s)}" data-pin="${esc(s)}" style="--sc:var(--s${i})">
      <header><a href="/ticker/${esc(s)}">${esc(s)}</a><small>${t.sector ? esc(t.sector) : "unknown"}</small></header>
      <p class="full" title="${esc(t.name || "unknown")}">${esc(t.name || "unknown")}</p>
      <p class="px">${cmpRs(t.q.close)}</p>
      <div class="mv"><span class="${cls(t.q.ret_1d || 0)}">${cmpPct(t.q.ret_1d)}<small> 1D</small></span><span class="${cls(t.q.ret_20d || 0)}">${cmpPct(t.q.ret_20d)}<small> 20D</small></span></div>
      <div class="cx-tags">
        <span><small>VS MODEL</small>${t.fv && t.fv.gap != null ? cmpX(t.fv.gap) + " · " + (cmpVerd[t.fv.verdict] || t.fv.verdict || "unknown") : "unknown"}</span>
        <span><small>FUNDAMENTALS</small>${t.fs?.rating ? esc(t.fs.rating) : "unknown"}</span>
        <span><small>INDEX WEIGHT</small>unknown</span>
        <span><small>PROVEN HERE</small>${t.proven} strategies</span>
      </div>
      <div class="cx-nfoot">
        <div class="cx-idx"></div>
        <div class="cx-nctl">
          <button data-move="${esc(s)}" data-by="-1" ${i === 0 ? "disabled" : ""} aria-label="Move ${esc(s)} earlier">◂</button>
          <button data-move="${esc(s)}" data-by="1" ${last ? "disabled" : ""} aria-label="Move ${esc(s)} later">▸</button>
          <button data-drop="${esc(s)}" aria-label="Remove ${esc(s)}" title="Remove ${esc(s)}">✕</button>
        </div>
      </div>
    </div>`;
  }).join("")}</div>`;
}

/* ---------- 02 price path chart ---------- */
function cmpWindow(hist) {
  const n = CMP_RANGES[CMP.range] || 252;
  const dateSet = new Set();
  CMP.syms.forEach(s => (hist[s] || []).slice(-n).forEach(r => dateSet.add(r.date)));
  const dates = [...dateSet].sort();
  const series = CMP.syms.map(s => {
    const rows = hist[s] || [];
    const byDate = new Map(rows.map(r => [r.date, r.close]));
    let base = null;
    return dates.map(d => {
      const c = byDate.get(d);
      if (c == null) return null;
      if (base == null) base = c;
      return base ? (c / base) * 100 : null;
    });
  });
  return { dates, series };
}

function cmpPathChart(width) {
  const hist = cmpPathChart._hist || {};
  const { dates, series } = cmpWindow(hist);
  const W = Math.max(280, width || 600), H = 260, P = { l: 34, r: 10, t: 10, b: 22 };
  if (!dates.length) return `<p class="cx-cap">No overlapping history for the selected range.</p>`;
  const vis = series.filter((_, i) => !CMP.off.has(CMP.syms[i]));
  const all = vis.flat().filter(v => v != null);
  const lo = Math.min(100, ...all), hi = Math.max(100, ...all);
  const pad = (hi - lo) * 0.08 || 5;
  const y0 = lo - pad, y1 = hi + pad;
  const sx = i => P.l + (dates.length <= 1 ? 0 : (i / (dates.length - 1)) * (W - P.l - P.r));
  const sy = v => H - P.b - ((v - y0) / (y1 - y0 || 1)) * (H - P.t - P.b);
  const path = arr => {
    let d = "", started = false;
    arr.forEach((v, i) => { if (v == null) { started = false; return; } d += (started ? "L" : "M") + sx(i).toFixed(1) + "," + sy(v).toFixed(1) + " "; started = true; });
    return d.trim();
  };
  const base100 = sy(100);
  let lines = `<line class="base" x1="${P.l}" x2="${W - P.r}" y1="${base100.toFixed(1)}" y2="${base100.toFixed(1)}"/>`;
  series.forEach((arr, i) => {
    const s = CMP.syms[i];
    if (CMP.off.has(s)) return;
    lines += `<path class="ln ${CMP_DASH[i]}" data-sym="${esc(s)}" d="${path(arr)}" style="stroke:var(--s${i})"/>`;
  });
  return `<svg id="cmp-pathsvg" class="cx-svg" viewBox="0 0 ${W} ${H}" data-l="${P.l}" data-r="${P.r}" data-n="${dates.length}" role="img" aria-label="Rebased price path" tabindex="0">
    <text x="${P.l - 6}" y="${(base100 + 3).toFixed(1)}" text-anchor="end">100</text>
    ${lines}
    <line id="cmp-xhair" class="xh" x1="0" x2="0" y1="${P.t}" y2="${H - P.b}" style="display:none"/>
  </svg>`;
}

function cmpCharts(hist) {
  const c = document.getElementById("cmp-pathchart");
  if (!c) return;
  cmpPathChart._hist = hist;
  c.innerHTML = cmpPathChart(c.clientWidth);
}

/* ---------- 03 measure sets ---------- */
const CMP_SETS = [
  { k: "VALUATION", sub: "price against earnings and the model", rows: [
    { l: "P/E (trailing)", h: "lower reads cheaper", dir: -1, g: T => T.fs?.pe ?? T.fv?.pe ?? null, f: v => cmpNum(v, 2), src: ["fundamental_scores", "metrics.pe"] },
    { l: "P/E (forward)", h: "lower reads cheaper on expected earnings", dir: -1, g: T => T.fs?.fpe ?? null, f: v => cmpNum(v, 2), src: ["fundamental_scores", "metrics.forward_pe"] },
    { l: "Model fair value (Rs)", h: "the desk's four-method estimate, not a price target", dir: 0, g: T => T.fv?.fair ?? null, f: v => cmpRs(v), src: ["fairvalue", "composite_fair"] },
    { l: "vs fair value", h: "distance between price and the model estimate", dir: 0, g: T => T.fv?.gap ?? null, f: v => cmpX(v), src: ["fairvalue", "mispricing_pct"] },
  ] },
  { k: "QUALITY", sub: "predictability and strategy fit on each name's own history", dir: 1, rows: [
    { l: "Predictability", h: "higher means signals on this name held up better historically", dir: 1, g: T => T.pr?.score ?? null, f: v => cmpNum(v, 1), src: ["predictability", "score"] },
    { l: "Strategies proven here", h: "how many of the desk's templates cleared the bar on this name's own history", dir: 1, g: T => T.proven, f: v => cmpNum(v, 0), src: ["backtests", "templates.*.<SYM>.eligible"] },
  ] },
  { k: "MOMENTUM", sub: "recent price behaviour, descriptive only", rows: [
    { l: "20-day move", h: "change over the last 20 sessions", dir: 0, g: T => T.q.ret_20d ?? null, f: v => cmpPct(v, 1), sg: true, src: ["quant", "ret_20d"] },
    { l: "RSI (14)", h: "momentum oscillator; neither high nor low is inherently better", dir: 0, g: T => T.q.rsi14 ?? null, f: v => cmpNum(v, 1), src: ["quant", "rsi14"] },
  ] },
  { k: "DIVIDENDS", sub: "yield and how much of profit it costs", rows: [
    { l: "Dividend yield", h: "higher pays more per rupee invested, before payout quality", dir: 1, g: T => T.dy, f: v => cmpPct(v, 2), src: ["fundamentals", "div_yield"] },
    { l: "Payout ratio", h: "share of profit paid out; very high can mean it is not well covered", dir: 0, g: T => T.payout, f: v => cmpPct(v, 2), src: ["fundamentals", "payout_ratio"] },
  ] },
];

function cmpLeader(T, r) {
  if (!r.dir) return null;
  const vals = CMP.syms.map(s => [s, r.g(T[s])]).filter(x => x[1] != null && isFinite(x[1]));
  if (vals.length < 2) return null;
  vals.sort((a, b) => r.dir * (b[1] - a[1]));
  if (vals[1] && vals[1][1] === vals[0][1]) return null;
  return vals[0][0];
}
function cmpRule(T, r) {
  if (!r.dir) return `Context only; no name leads on this row. ${r.h}.`;
  const lead = cmpLeader(T, r);
  return `${r.dir < 0 ? "Lower" : "Higher"} ${r.l} reads stronger (${r.h}). ${lead ? "Stronger here: " + lead + "." : "No single name is stronger: values tie, or fewer than two are known."}`;
}
function cmpInset(T, r, id, asofFile) {
  const [file, field] = r.src || ["unknown", "unknown"];
  return `<div class="cx-mx" id="${esc(id)}" ${CMP.open.has(id) ? "" : "hidden"}>
    <p class="rule"><small>RULE</small>${esc(cmpRule(T, r))}</p>
    <dl>${CMP.syms.map((s, i) => `<dt>${cmpSw(i)}${esc(s)}</dt><dd>${esc(r.f(r.g(T[s])))}</dd>`).join("")}</dl>
    <p class="src">Source: <code>state/${esc(file)}.json</code> · ${esc(field)}</p>
  </div>`;
}
function cmpSets(T) {
  const n = CMP.syms.length;
  return `<div class="cx-sets">${CMP_SETS.map((st, a) => {
    const leads = Object.fromEntries(CMP.syms.map(s => [s, 0]));
    st.rows.forEach(r => { const l = cmpLeader(T, r); if (l) leads[l]++; });
    const rows = st.rows.map((r, b) => {
      const lead = cmpLeader(T, r), id = `cmp-mx-${a}-${b}`, open = CMP.open.has(id);
      const head = `<div class="cx-mrow" role="button" tabindex="0" aria-expanded="${open}" aria-controls="${id}" data-row="${id}"><div class="lb"><i class="cx-chev" aria-hidden="true">+</i>${esc(r.l)}<small>${esc(r.h)}</small></div>`;
      const vals = CMP.syms.map(s => r.g(T[s])), good = vals.filter(v => v != null && isFinite(v));
      const lo = good.length ? Math.min(...good) : 0, hi = good.length ? Math.max(...good) : 0;
      const cells = CMP.syms.map((s, i) => {
        const v = vals[i], w = (v == null || !isFinite(v)) ? 0 : hi === lo ? 60 : 12 + (v - lo) / (hi - lo) * 88;
        return `<div class="cx-cell ${s === lead ? "lead" : ""} ${v == null ? "na" : ""}" data-sym="${esc(s)}" title="${esc(r.l)}: ${esc(r.f(v))}"><div class="v"><span class="${r.sg && v != null ? cls(v) : ""}">${esc(r.f(v))}</span>${s === lead ? "<em>◆</em>" : ""}</div><div class="cx-trk"><i style="width:${w}%"></i></div></div>`;
      }).join("");
      return head + cells + "</div>" + cmpInset(T, r, id);
    }).join("");
    const lt = Object.entries(leads).filter(x => x[1]).map(([s, k]) => `<b>${esc(s)}</b> ${k}`).join(" · ") || "no leader";
    return `<section class="cx-set" style="--n:${n}"><h3>${esc(st.k)} <span>${esc(st.sub)} · leads: ${lt}</span></h3>
      <div class="cx-mhd"><span></span>${CMP.syms.map((s, i) => `<span data-sym="${esc(s)}">${cmpSw(i)}${esc(s)}</span>`).join("")}</div>${rows}</section>`;
  }).join("")}</div>
  <p class="cx-cap">◆ marks the name that leads on a measure, by the rule under its label. Bars run from the lowest value (short) to the highest (full) in this set. Rows marked context have no leader. ${CMP_TOUCH ? "Tap a row" : "Hover a row for the values; click it"} to open the raw numbers and the state file they come from.</p>`;
}

/* ---------- 04 the desk's read ---------- */
function cmpTally(T) {
  const c = Object.fromEntries(CMP.syms.map(s => [s, 0])); let tot = 0;
  CMP_SETS.forEach(st => st.rows.forEach(r => { const l = cmpLeader(T, r); if (l) { c[l]++; tot++; } }));
  return { c, tot };
}
function cmpReadLines(T, nstrat) {
  const ss = CMP.syms, L = [];
  const best = (g, dir) => { const v = ss.map(s => [s, g(s)]).filter(x => x[1] != null && isFinite(x[1])); return v.length ? v.sort((a, b) => dir * (b[1] - a[1]))[0] : null; };
  const pe = best(s => T[s].fs?.pe ?? null, -1); if (pe) L.push(`Lowest trailing P/E: <b>${esc(pe[0])}</b> at ${esc(cmpNum(pe[1], 2))}.`);
  const dy = best(s => T[s].dy, 1); if (dy) L.push(`Highest dividend yield: <b>${esc(dy[0])}</b> at ${esc(cmpPct(dy[1], 2))}, paying out ${esc(cmpPct(T[dy[0]].payout, 0))} of profit.`);
  const below = ss.filter(s => T[s].q.close != null && T[s].q.sma50 != null && T[s].q.close < T[s].q.sma50);
  const down = ss.filter(s => T[s].q.ret_20d != null && T[s].q.ret_20d < 0);
  if (below.length && down.length) {
    L.push(below.length === ss.length && down.length === ss.length
      ? `${ss.length === 2 ? "Both" : "All " + ss.length} trade below their 50-day average and are down over 20 sessions — the chart side is soft across the bench.`
      : `${below.length ? below.join(", ") : "None"} below the 50-day average; ${down.length ? down.join(", ") : "none"} down over 20 sessions.`);
  }
  const pv = best(s => T[s].proven, 1); if (pv && pv[1] > 0) L.push(`Most strategies proven on its own history: <b>${esc(pv[0])}</b>, ${pv[1]} of ${nstrat}.`);
  return L;
}
function cmpRead(T, nstrat) {
  const { c, tot } = cmpTally(T), order = [...CMP.syms].sort((a, b) => c[b] - c[a]);
  const top = order[0], tie = order.length > 1 && c[order[1]] === c[top];
  const lede = !tot ? "No measure in this set has a clear leader on the data available." : tie
    ? `No single name leads the bench: ${order.map(s => `${esc(s)} ${c[s]}`).join(", ")} of ${tot} measures. Each one is stronger on a different side.`
    : `<b>${esc(top)}</b> leads on ${c[top]} of the ${tot} measures that have a leader; ${order.slice(1).map(s => `${esc(s)} on ${c[s]}`).join(", ")}. Leading on more measures is a description of the numbers, not a ranking to act on.`;
  return `<div class="cx-read">
    <div class="cx-card">
      <p class="today-kicker">THE DESK'S READ <span>· from the numbers above, nothing added</span></p>
      <p class="cx-lede">${lede}</p>
      <ul class="cx-lines">${cmpReadLines(T, nstrat).map(l => `<li>${l}</li>`).join("") || "<li>Not enough overlapping data to add a line here.</li>"}</ul>
    </div>
    <div class="cx-card cx-tally">
      <h3>LEADS <span>· ${tot} measures with a direction</span></h3>
      ${CMP.syms.map((s, i) => `<div class="cx-trow" data-sym="${esc(s)}" data-pin="${esc(s)}"><span>${cmpSw(i)}${esc(s)}</span><div class="bar">${Array.from({ length: tot || 1 }, (_, k) => `<i class="${k < c[s] ? "on" : ""}"></i>`).join("")}</div><span class="r">${c[s]}</span></div>`).join("")}
      <p class="cx-cap">Every measure counts the same here. A name can lead on many small things and still carry the bigger risk. Losses happen on every kind of name.</p>
    </div>
  </div>`;
}

/* ---------- 05 full table ---------- */
const CMP_TROWS = [
  ["Sector", T => T.sector ? esc(T.sector) : "unknown"],
  ["Price (Rs)", T => T.q.close != null ? T.q.close.toFixed(2) : "unknown"],
  ["20-day move", T => cmpPct(T.q.ret_20d, 2)],
  ["RSI (14)", T => T.q.rsi14 != null ? T.q.rsi14.toFixed(1) : "unknown"],
  ["P/E (trailing)", T => cmpNum(T.fs?.pe ?? T.fv?.pe ?? null, 2)],
  ["P/E (forward)", T => cmpNum(T.fs?.fpe ?? null, 2)],
  ["Dividend yield", T => cmpPct(T.dy, 2)],
  ["Payout ratio", T => cmpPct(T.payout, 2)],
  ["Model fair value (Rs)", T => T.fv?.fair != null ? T.fv.fair.toFixed(2) : "unknown"],
  ["vs fair value", T => T.fv?.gap != null ? cmpX(T.fv.gap) + " · " + (cmpVerd[T.fv.verdict] || T.fv.verdict || "unknown") : "unknown"],
  ["Predictability", T => T.pr?.score != null ? T.pr.score.toFixed(1) : "unknown"],
  ["Strategies proven here", T => `${T.proven}`],
];
const cmpNumOf = t => { const m = String(t).replace(/,/g, "").match(/-?\d+(?:\.\d+)?/); return m ? +m[0] : null; };
function cmpCmpBy(a, b, d) {
  const ua = a === "unknown", ub = b === "unknown"; if (ua || ub) return (ua ? 1 : 0) - (ub ? 1 : 0);
  const na = cmpNumOf(a), nb = cmpNumOf(b);
  return (na != null && nb != null ? na - nb : String(a).localeCompare(String(b))) * d;
}
function cmpCols(T) { if (CMP.ts.k == null) return CMP.syms; const g = s => CMP_TROWS[CMP.ts.k][1](T[s]); return [...CMP.syms].sort((a, b) => cmpCmpBy(g(a), g(b), CMP.ts.d)); }
function cmpRows() { const r = CMP_TROWS.map((x, i) => [i, ...x]); return CMP.rs ? r.sort((a, b) => a[1].localeCompare(b[1]) * CMP.rs) : r; }
function cmpTable(T, nstrat) {
  const cs = cmpCols(T), ci = s => CMP.syms.indexOf(s);
  const arrow = (on, d) => on ? (d < 0 ? "▼" : "▲") : "↕";
  const rsLbl = CMP.rs === 1 ? "ascending" : CMP.rs === -1 ? "descending" : "none";
  return `<details class="cx-more" ${CMP.topen ? "open" : ""}><summary>Every number in one table · ${CMP_TROWS.length} rows</summary>
    <div class="cx-ctrl"><span class="cx-cap" style="margin:0">${CMP_TOUCH ? "Tap" : "Click"} a measure to order the names by it; ${(CMP_TOUCH ? "tap" : "click")} "Measure" to order the rows.</span><button class="cx-btn" id="cmp-csv">Export CSV</button></div>
    <div class="cx-tbl today-table-wrap"><table class="today-table"><thead><tr><th aria-sort="${rsLbl}"><button class="cx-sort ${CMP.rs ? "on" : ""}" data-sort="m" aria-label="Order rows by measure name">Measure<i>${CMP.rs === 1 ? "▲" : CMP.rs === -1 ? "▼" : "↕"}</i></button></th>${cs.map(s => `<th data-sym="${esc(s)}">${cmpSw(ci(s))}<a href="/ticker/${esc(s)}">${esc(s)}</a></th>`).join("")}</tr></thead>
    <tbody>${cmpRows().map(([i, l, g]) => { const on = CMP.ts.k === i;
      const vals = cs.map(s => g(T[s]));
      const nums = cs.map((s, idx) => [s, cmpNumOf(vals[idx])]).filter(x => x[1] != null);
      const best = on && nums.length > 1 ? cs[0] : null;
      return `<tr><td><button class="cx-sort ${on ? "on" : ""}" data-sort="${i}" aria-pressed="${on}">${esc(l)}<i>${arrow(on, CMP.ts.d)}</i></button></td>${cs.map((s, idx) => `<td data-sym="${esc(s)}" data-pin="${esc(s)}" class="${s === best ? "best" : ""}">${esc(vals[idx])}</td>`).join("")}</tr>`;
    }).join("")}</tbody></table></div>
  </details>`;
}
function cmpCsv(T) {
  const q = v => /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v, cs = cmpCols(T);
  const lines = [["Measure", ...cs], ...cmpRows().map(([, l, g]) => [l, ...cs.map(s => g(T[s]))])].map(r => r.map(q).join(","));
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
  a.download = `henneth-compare-${cs.join("-")}.csv`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/* ---------- linked highlight ---------- */
function cmpApplyHl(root) {
  const cur = CMP._hover || CMP.pin;
  root.classList.toggle("has-hl", !!cur);
  root.querySelectorAll("[data-sym]").forEach(el => el.classList.toggle("is-hl", el.getAttribute("data-sym") === cur));
  root.querySelectorAll(".cx-chip, .cx-name").forEach(el => el.classList.toggle("is-pin", el.getAttribute("data-sym") === CMP.pin));
}

/* ---------- interactivity ---------- */
function cmpWire(root, T, hist, nstrat) {
  if (!root) return;
  const tip = root.querySelector("#cmp-tip");
  function showTip(x, y, html) { if (!tip) return; tip.innerHTML = html; tip.style.display = "block"; tip.style.left = Math.max(8, Math.min(x + 14, innerWidth - 290)) + "px"; tip.style.top = (y + 14) + "px"; }
  function hideTip() { if (tip) tip.style.display = "none"; }

  root.querySelector("#cmp-form")?.addEventListener("submit", e => { e.preventDefault(); const i = $("cmp-in"); cmpAdd2(i.value); if (i) i.value = ""; });

  root.addEventListener("click", e => {
    const t = e.target;
    const d = t.closest("[data-drop]"); if (d) { cmpDrop2(d.getAttribute("data-drop")); return; }
    const mv = t.closest("[data-move]"); if (mv) { cmpMove(mv.getAttribute("data-move"), +mv.getAttribute("data-by")); return; }
    const r = t.closest("[data-range]"); if (r) { if (CMP.range !== r.getAttribute("data-range")) { CMP.range = r.getAttribute("data-range"); cmpCharts(hist); root.querySelectorAll("[data-range]").forEach(b => b.setAttribute("aria-pressed", b === r)); } return; }
    const lg = t.closest("[data-lg]"); if (lg) {
      const s = lg.getAttribute("data-lg");
      if (CMP.off.has(s)) CMP.off.delete(s);
      else if (CMP.syms.filter(x => !CMP.off.has(x)).length > 1) CMP.off.add(s);
      else { showTip(e.clientX || 0, e.clientY || 0, "At least one line stays on."); return; }
      lg.setAttribute("aria-pressed", !CMP.off.has(s)); hideTip(); cmpCharts(hist); return;
    }
    const so = t.closest("[data-sort]"); if (so) {
      const k = so.getAttribute("data-sort");
      if (k === "m") CMP.rs = CMP.rs === 0 ? 1 : CMP.rs === 1 ? -1 : 0;
      else { const i = +k; CMP.ts = CMP.ts.k !== i ? { k: i, d: -1 } : CMP.ts.d === -1 ? { k: i, d: 1 } : { k: null, d: -1 }; }
      const wrap = root.querySelector("#cmp-tblwrap"); if (wrap) wrap.innerHTML = cmpTable(T, nstrat);
      cmpApplyHl(root); return;
    }
    if (t.closest("#cmp-csv")) { cmpCsv(T); return; }
    const row = t.closest("[data-row]"); if (row) {
      const id = row.getAttribute("data-row"), open = !CMP.open.has(id);
      if (open) CMP.open.add(id); else CMP.open.delete(id);
      row.setAttribute("aria-expanded", open);
      const ins = document.getElementById(id); if (ins) ins.hidden = !open;
      hideTip(); return;
    }
    const p = t.closest("[data-pin]"); if (p && !t.closest("a, button, svg")) { CMP.pin = CMP.pin === p.getAttribute("data-pin") ? null : p.getAttribute("data-pin"); cmpApplyHl(root); }
  });

  root.addEventListener("keydown", e => {
    const t = e.target;
    if ((e.key === "Enter" || e.key === " ") && t.matches("[role=button][tabindex]")) { e.preventDefault(); t.click(); }
    if (e.key === "Escape") { CMP.pin = null; CMP._hover = null; hideTip(); cmpApplyHl(root); }
  });

  if (!CMP_TOUCH) {
    root.addEventListener("pointerover", e => { const t = e.target.closest("[data-sym]"); const s = t ? t.getAttribute("data-sym") : null; if (s === CMP._hover) return; CMP._hover = s; cmpApplyHl(root); });
    root.addEventListener("pointerleave", () => { CMP._hover = null; cmpApplyHl(root); hideTip(); });
    root.addEventListener("pointermove", e => {
      const svg = e.target.closest("#cmp-pathsvg");
      if (svg) { cmpPathTip(svg, e, hist, showTip); return; }
      const tEl = e.target.closest("[title]");
      if (tEl) { showTip(e.clientX, e.clientY, esc(tEl.getAttribute("title"))); return; }
      hideTip();
    });
  } else {
    root.addEventListener("pointerdown", e => {
      const svg = e.target.closest("#cmp-pathsvg");
      if (svg) { cmpPathTip(svg, e, hist, showTip); return; }
      const tEl = e.target.closest("[title]");
      if (tEl && !e.target.closest(".cx-mrow")) showTip(e.clientX, e.clientY, esc(tEl.getAttribute("title")));
      else hideTip();
    });
  }

  cmpApplyHl(root);
  let rz; addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => cmpCharts(hist), 150); });
}

function cmpPathTip(svg, e, hist, showTip) {
  const { dates, series } = cmpWindow(hist);
  if (!dates.length) return;
  const b = svg.getBoundingClientRect(), k = svg.viewBox.baseVal.width / b.width;
  const L = +svg.dataset.l, R = +svg.dataset.r, W = svg.viewBox.baseVal.width, n = dates.length;
  const x = (e.clientX - b.left) * k;
  if (x < L - 4 || x > W - R + 4) return;
  const i = Math.max(0, Math.min(n - 1, Math.round((x - L) / (W - L - R || 1) * (n - 1))));
  const html = `<b>${esc(cmpDate(dates[i]))}</b><br>` + CMP.syms.filter(s => !CMP.off.has(s)).map((s, idx) => {
    const si = CMP.syms.indexOf(s), v = series[si][i];
    return `${esc(s)} <b class="${v != null ? cls(v - 100) : ""}">${v != null ? v.toFixed(1) : "unknown"}</b>`;
  }).join("<br>");
  showTip(e.clientX, e.clientY, html);
}
