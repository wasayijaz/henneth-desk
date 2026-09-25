// strategies page — redesign 2026-09
// Behaviour parity source: old pageStrategies (app.js lines 1108-1235, removed here, kept in
// git history). New visual structure ported from docs/redesign-mockups/strategies-mockup.html.
// Real data only — every number below comes from state/ via j(); nothing is invented. The
// mockup's sample data (docs/redesign-mockups/wl/strategies-data.js, window.ST) is a hardcoded
// placeholder blob and is NOT used here — every chapter (family bars, funnel, heatmap, scatter
// bins, per-strategy detail) is re-derived client-side from the same real state files the old
// page read (backtests, strategy_map, strategy_library, universe), plus sectors.json for the
// family x sector matrix (sectors.json is already fetched the same way by page-compare.js).
// No advice language: output reads "the setup"/"the desk's read", never "you should buy".
// Missing/unavailable data renders as the literal string "unknown".

let STR_S = { fam: null, lens: "heat", openId: null };

function strPct(v, d = 0) { return v == null || !isFinite(v) ? "unknown" : Math.round(v * 100 * Math.pow(10, d)) / Math.pow(10, d) + "%"; }
function strNum(v) { return v == null || !isFinite(v) ? "unknown" : v; }
function strDate(v) { return v ? String(v).slice(0, 10) : "unknown"; }

/* ---------- data ---------- */
async function strLoadState() {
  const [bt, smap, lib, uni, sec] = await Promise.all([
    j("backtests.json"), j("strategy_map.json"), j("strategy_library.json"), j("universe.json"), j("sectors.json"),
  ]);
  return { bt, smap, lib, uni, sec };
}

// per-strategy roll-up rows — same fallback logic as the old page: prefer the full backtests
// roll-up, fall back to the bundled per-ticker strategy_map snapshot if backtests are empty.
function strRows(D) {
  const tpls = D.bt?.templates || {};
  if (Object.keys(tpls).length) {
    return Object.entries(tpls).map(([id, per]) => {
      const all = Object.values(per);
      const elig = all.filter(t => t.eligible);
      const avgNet = elig.length ? elig.reduce((a, t) => a + t.net_expectancy_pct, 0) / elig.length : null;
      return {
        id, name: all[0]?.name || id, cat: all[0]?.category || "", tested: all.length,
        proven: elig.length, avgNet, provenOn: Object.entries(per).filter(([, t]) => t.eligible).map(([s]) => s),
        pairs: Object.entries(per).map(([s, t]) => ({ s, net: t.net_expectancy_pct, hit: t.hit_rate, n: t.n, oos: t.oos?.hit_rate, ok: !!t.eligible })),
      };
    });
  }
  const agg = {};
  Object.entries(D.smap?.tickers || {}).forEach(([sym, list]) => list.forEach(p => {
    const a = agg[p.id] || (agg[p.id] = { id: p.id, name: p.name, cat: p.category, nets: [], provenOn: [], pairs: [] });
    a.nets.push(p.net_expectancy_pct); a.provenOn.push(sym);
    a.pairs.push({ s: sym, net: p.net_expectancy_pct, hit: p.hit_rate, n: p.n, oos: p.oos?.hit_rate, ok: true });
  }));
  return Object.values(agg).map(a => ({
    id: a.id, name: a.name, cat: a.cat, tested: null,
    proven: a.provenOn.length, avgNet: a.nets.reduce((x, y) => x + y, 0) / a.nets.length, provenOn: a.provenOn, pairs: a.pairs,
  }));
}

// real 5-stage funnel, computed from the raw stock x strategy pairs and the SAME bars.json
// thresholds backtest.py applies — no stage is invented, each is a literal filter on real fields.
function strFunnel(D) {
  const tpls = D.bt?.templates || {};
  const bars = D.bt?.bars || {};
  const pairs = [];
  Object.values(tpls).forEach(per => Object.values(per).forEach(t => pairs.push(t)));
  if (!pairs.length) return null;
  const s1 = pairs.length;
  const s2 = pairs.filter(t => (t.n ?? 0) >= (bars.min_trades ?? 0));
  const s3 = s2.filter(t => (t.hit_rate ?? 0) >= (bars.min_hit_rate ?? 0));
  const s4 = s3.filter(t => (t.net_expectancy_pct ?? -Infinity) >= (bars.min_net_expectancy_pct ?? 0));
  const s5 = pairs.filter(t => t.eligible);
  return [
    { label: "stock x strategy pairs", n: s1 },
    { label: `at least ${bars.min_trades ?? "?"} trades`, n: s2.length },
    { label: `hit rate ≥ ${Math.round((bars.min_hit_rate ?? 0) * 100)}%`, n: s3.length },
    { label: "net expectancy after costs > 0", n: s4.length },
    { label: "holds out-of-sample — proven", n: s5.length },
  ];
}

// real family (strategy category) x sector matrix of PROVEN pairs — sectors.json is the
// authoritative PSX sector classification, already used the same way by page-compare.js.
function strFamSector(D) {
  const tpls = D.bt?.templates || {};
  const secOf = sym => D.sec?.tickers?.[sym]?.sector || null;
  const cell = {};
  const cats = new Set(); const sectors = new Set();
  Object.entries(tpls).forEach(([id, per]) => {
    const cat = Object.values(per)[0]?.category || "other";
    cats.add(cat);
    Object.entries(per).forEach(([sym, t]) => {
      if (!t.eligible) return;
      const sec = secOf(sym); if (!sec) return;
      sectors.add(sec);
      const k = cat + "|" + sec;
      cell[k] = (cell[k] || 0) + 1;
    });
  });
  return { cats: [...cats].sort(), sectors: [...sectors].sort(), cell };
}

// real win-rate x net-expectancy 2D bin histogram over every tested pair (not just proven) —
// shows where the whole library actually lands, not a cherry-picked slice.
function strScatterBins(D) {
  const tpls = D.bt?.templates || {};
  const pairs = [];
  Object.values(tpls).forEach(per => Object.values(per).forEach(t => pairs.push(t)));
  if (!pairs.length) return null;
  const hitEdges = [0, .3, .4, .45, .5, .55, .6, .65, .7, .8, 1.01];
  const netEdges = [-5, -1, -.5, 0, .5, 1, 2, 4, 8, 100];
  const binOf = (v, edges) => { for (let i = 0; i < edges.length - 1; i++) if (v >= edges[i] && v < edges[i + 1]) return i; return edges.length - 2; };
  const cells = {};
  pairs.forEach(t => {
    if (t.hit_rate == null || t.net_expectancy_pct == null) return;
    const hb = binOf(t.hit_rate, hitEdges), nb = binOf(t.net_expectancy_pct, netEdges);
    const k = hb + "," + nb;
    cells[k] = (cells[k] || { hb, nb, n: 0, proven: 0 });
    cells[k].n++; if (t.eligible) cells[k].proven++;
  });
  return { hitEdges, netEdges, cells: Object.values(cells) };
}

/* ---------- render pieces ---------- */
function strFamBars(rows, funnelTotal) {
  const byCat = {};
  rows.forEach(r => { const a = byCat[r.cat] || (byCat[r.cat] = { cat: r.cat, tested: 0, proven: 0 }); a.tested += r.tested || 0; a.proven += r.proven; });
  const list = Object.values(byCat).sort((a, b) => b.proven - a.proven);
  const max = Math.max(1, ...list.map(a => a.proven));
  return `<div class="st-fams" role="group" aria-label="Filter by family">
    <button class="st-fam ${STR_S.fam === null ? "on" : ""}" data-fam="">
      <span class="st-fam-h"><b>All families</b><i>${funnelTotal != null ? funnelTotal + " proven pairs" : "unknown"}</i></span>
      <span class="st-fam-bar"><i style="width:100%"></i></span>
    </button>
    ${list.map(a => `<button class="st-fam ${STR_S.fam === a.cat ? "on" : ""}" data-fam="${esc(a.cat)}">
      <span class="st-fam-h"><b>${esc((a.cat || "other").replace(/_/g, " "))}</b><i>${a.proven} of ${a.tested || "?"} proven</i></span>
      <span class="st-fam-bar"><i style="width:${Math.max(3, Math.round(a.proven / max * 100))}%"></i></span>
    </button>`).join("")}
  </div>`;
}

function strFunnelBlock(funnel) {
  if (!funnel) return `<div class="card st-empty">Funnel needs the full backtests roll-up — not present in this data snapshot. unknown.</div>`;
  const max = funnel[0].n || 1;
  return `<div class="st-funnel">${funnel.map((s, i) => `<div class="st-step">
    <span class="st-step-n">${i + 1}</span>
    <span class="st-step-lab">${esc(s.label)}</span>
    <span class="st-step-bar"><i style="width:${Math.max(2, Math.round(s.n / max * 100))}%"></i></span>
    <b class="st-step-v">${s.n.toLocaleString()}</b>
  </div>`).join("")}</div>`;
}

function strHeat(fs) {
  if (!fs.cats.length || !fs.sectors.length) return `<div class="card st-empty">No proven pair carries a matched sector yet. unknown.</div>`;
  const max = Math.max(1, ...Object.values(fs.cell));
  return `<div class="st-heat-wrap"><table class="st-heat"><thead><tr><th></th>${fs.sectors.map(s => `<th>${esc(s)}</th>`).join("")}</tr></thead>
    <tbody>${fs.cats.map(c => `<tr><th>${esc((c || "other").replace(/_/g, " "))}</th>${fs.sectors.map(s => {
      const n = fs.cell[c + "|" + s] || 0;
      const t = n ? Math.max(.12, n / max) : 0;
      return `<td style="${n ? `--t:${t}` : ""}" class="${n ? "on" : ""}">${n || ""}</td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div>
  <p class="st-cap">Each cell: proven strategy x sector pairs, after costs, holding out-of-sample. Darker = more.</p>`;
}

function strScatter(bins) {
  if (!bins) return `<div class="card st-empty">Scatter needs the full backtests roll-up — not present in this data snapshot. unknown.</div>`;
  const W = 640, H = 360, pad = 34;
  const maxN = Math.max(1, ...bins.cells.map(c => c.n));
  const cw = (W - pad * 2) / (bins.hitEdges.length - 1), ch = (H - pad * 2) / (bins.netEdges.length - 1);
  const dots = bins.cells.map(c => {
    const cx = pad + (c.hb + .5) * cw, cy = H - pad - (c.nb + .5) * ch;
    const r = 3 + 13 * Math.sqrt(c.n / maxN);
    const provenShare = c.n ? c.proven / c.n : 0;
    return `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${r.toFixed(1)}" style="--p:${provenShare.toFixed(2)}"><title>${Math.round(bins.hitEdges[c.hb] * 100)}-${Math.round(bins.hitEdges[c.hb + 1] * 100)}% hit rate, ${bins.netEdges[c.nb]}-${bins.netEdges[c.nb + 1]}% net · ${c.n} pairs, ${c.proven} proven</title></circle>`;
  }).join("");
  return `<svg class="st-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Win rate against net expectancy, every tested pair">
    <line x1="${pad}" y1="${H - pad}" x2="${W - pad}" y2="${H - pad}" class="ax"/>
    <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${H - pad}" class="ax"/>
    <text x="${W / 2}" y="${H - 6}" class="lab" text-anchor="middle">win rate →</text>
    <text x="12" y="${H / 2}" class="lab" text-anchor="middle" transform="rotate(-90 12 ${H / 2})">net expectancy / trade →</text>
    ${dots}
  </svg><p class="st-cap">Every tested stock x strategy pair, binned. Bubble size = how many pairs land there; fill = share that proved out. Hover a bubble for the exact range.</p>`;
}

// Where one rule lands across every stock it was tested on: net expectancy per trade, binned
// in 0.5% steps (clamped to ±6%), the proven share of each bin drawn on top.
function strDist(pairs, bar) {
  const lo = -6, hi = 6, step = .5, nb = (hi - lo) / step;
  const bins = Array.from({ length: nb }, () => ({ n: 0, ok: 0 }));
  pairs.forEach(p => {
    if (p.net == null || !isFinite(p.net)) return;
    const b = bins[Math.min(nb - 1, Math.max(0, Math.floor((p.net - lo) / step)))];
    b.n++; if (p.ok) b.ok++;
  });
  const max = Math.max(1, ...bins.map(b => b.n));
  const W = 240, H = 44, bw = W / nb, x = v => (v - lo) / (hi - lo) * W;
  return `<svg class="st-dist" viewBox="0 0 ${W} ${H + 12}" preserveAspectRatio="none" aria-hidden="true">
    ${bins.map((b, i) => { if (!b.n) return ""; const h = Math.max(2, b.n / max * H), ho = b.ok / max * H;
      return `<rect class="all" x="${(i * bw + .5).toFixed(1)}" y="${(H - h).toFixed(1)}" width="${(bw - 1).toFixed(1)}" height="${h.toFixed(1)}"/>${b.ok
        ? `<rect class="ok" x="${(i * bw + .5).toFixed(1)}" y="${(H - ho).toFixed(1)}" width="${(bw - 1).toFixed(1)}" height="${ho.toFixed(1)}"/>` : ""}`; }).join("")}
    <line class="zero" x1="${x(0)}" y1="0" x2="${x(0)}" y2="${H}"/>
    ${bar != null ? `<line class="bar" x1="${x(bar)}" y1="0" x2="${x(bar)}" y2="${H}"/>` : ""}
    <line class="ax" x1="0" y1="${H}" x2="${W}" y2="${H}"/>
    <text x="0" y="${H + 10}">−6%</text><text x="${x(0)}" y="${H + 10}" text-anchor="middle">0</text><text x="${W}" y="${H + 10}" text-anchor="end">+6%</text>
  </svg>`;
}

// The rule's exit geometry: target above the entry line, stop below, drawn to the same scale.
function strPayoff(d) {
  if (d.target_pct == null || d.stop_pct == null) return "";
  const H = 40, mid = H * d.target_pct / (d.target_pct + d.stop_pct);
  const rr = d.stop_pct ? (d.target_pct / d.stop_pct).toFixed(1) : "unknown";
  return `<div class="st-pay">
    <svg viewBox="0 0 14 ${H}" aria-hidden="true"><rect class="tg" x="0" y="0" width="14" height="${mid.toFixed(1)}"/><rect class="sp" x="0" y="${mid.toFixed(1)}" width="14" height="${(H - mid).toFixed(1)}"/><line x1="0" y1="${mid.toFixed(1)}" x2="14" y2="${mid.toFixed(1)}"/></svg>
    <span class="st-pay-t"><b class="up">+${d.target_pct}%</b> target<br><b class="dn">−${d.stop_pct}%</b> stop<br><i>${d.hold ?? "unknown"} sessions max · ${rr} : 1</i></span>
  </div>`;
}

function strCards(rows, descs, bars) {
  const filtered = STR_S.fam === null ? rows : rows.filter(r => r.cat === STR_S.fam);
  if (!filtered.length) return `<div class="card st-empty">No strategy in this family yet. unknown.</div>`;
  const netBar = bars?.min_net_expectancy_pct ?? null;
  return `<div class="st-cards">${filtered.map(r => {
    const d = descs[r.id] || {};
    const open = STR_S.openId === r.id;
    const pairs = r.pairs || [];
    const proven = pairs.filter(p => p.ok).sort((a, b) => b.net - a.net);
    const share = r.tested ? r.proven / r.tested : null;
    return `<div class="st-card ${open ? "open" : ""} ${r.proven ? "" : "none"}" data-strcard="${esc(r.id)}">
      <div class="st-card-h"><b>${esc(r.name)}</b><span class="tag">${esc((r.cat || "other").replace(/_/g, " "))}</span></div>
      <p class="st-card-p">${esc(d.description || "")}</p>
      <div class="st-hero">
        <span><b class="${r.avgNet > 0 ? "up" : ""}">${r.avgNet != null ? sgn(+r.avgNet.toFixed(2)) + "%" : "unknown"}</b><i>avg net / trade where proven</i></span>
        <span class="r"><b>${r.proven}<small> / ${r.tested ?? "unknown"}</small></b><i>stocks proven</i></span>
      </div>
      <span class="st-share" title="${share != null ? Math.round(share * 100) + "% of tested stocks cleared the bar" : "unknown"}"><i style="width:${share != null ? Math.max(r.proven ? 2 : 0, Math.round(share * 100)) : 0}%"></i></span>
      ${pairs.length && r.tested ? `<div class="st-dist-w"><span class="st-lab">Net / trade on each of ${pairs.length} stocks tested<em><i class="k-ok"></i>proven</em></span>${strDist(pairs, netBar)}</div>` : ""}
      <div class="st-foot">
        ${strPayoff(d)}
        ${proven.length ? `<div class="st-best"><span class="st-lab">Strongest record</span>${proven.slice(0, 3).map(p =>
          `<span class="st-chip clickable" onclick="navigate('/ticker/${esc(p.s)}')"><b>${esc(p.s)}</b><i class="up">${sgn(+p.net.toFixed(2))}%</i></span>`).join("")}</div>`
        : `<div class="st-best"><span class="st-lab">Strongest record</span><span class="st-none">Hasn't cleared the bar on any stock yet.</span></div>`}
      </div>
      ${open ? `<div class="st-detail">${proven.length
        ? `<table class="st-tbl"><thead><tr><th>Stock</th><th class="r">Trades</th><th class="r">Win</th><th class="r">Win OOS</th><th class="r">Net/trade</th></tr></thead><tbody>${
            proven.slice(0, 15).map(p => `<tr><td class="clickable" onclick="navigate('/ticker/${esc(p.s)}')">${esc(p.s)}</td><td class="r num">${strNum(p.n)}</td><td class="r num">${strPct(p.hit)}</td><td class="r num">${strPct(p.oos)}</td><td class="r num up">${sgn(+p.net.toFixed(2))}%</td></tr>`).join("")}</tbody></table>${proven.length > 15 ? `<p class="st-cap">+ ${proven.length - 15} more.</p>` : ""}`
        : `<p class="st-cap">Hasn't cleared the bar on any stock in the universe yet.</p>`}</div>`
        : `<span class="st-more">${proven.length ? `All ${proven.length} proven stocks ›` : ""}</span>`}
    </div>`;
  }).join("")}</div>`;
}

/* ---------- board (unchanged from the old page — same functions, same behaviour) ---------- */
function strBoardBlock(D, rows) {
  const names = D.uni?.symbols || {};
  const nStrat = D.bt?.n_strategies || rows.length || 52;
  const board = stratBoard();
  const pending = board.filter(s => !stratRunOn(s));
  const anyRan = board.some(stratRunOn);
  const provenCount = s => (D.smap?.tickers?.[s] || []).length;
  const tiles = board.map(s => { const ranS = stratRunOn(s);
    return `<div class="sb-tile clickable" onclick="if(!event.target.closest('.sb-x'))navigate('/ticker/${esc(s)}')">
      <button class="sb-x" data-sbdel="${esc(s)}" title="Remove ${esc(s)} from the board" aria-label="remove ${esc(s)}">✕</button>
      <b>${esc(s)}</b><span class="sb-nm">${esc((names[s]?.name || "").slice(0, 24))}</span>
      <span class="pill ${ranS && provenCount(s) ? "ok" : ranS ? "" : "wait"}">${ranS ? provenCount(s) + " of " + nStrat + " proven" : "waiting for a run"}</span>
    </div>`; }).join("");
  const addTile = `<div class="sb-tile sb-add">
      <span class="sk">Add a stock</span>
      <input id="sb-tkr" class="ph-in combo" type="search" enterkeyhint="search" placeholder="e.g. FFC" autocomplete="off" onkeydown="if(event.key==='Enter'&&!document.querySelector('.combo-opt.on'))addBoardTicker()">
      <button class="note-save" onclick="addBoardTicker()">Add to board</button>
    </div>`;

  const runBar = pending.length ? `<button class="run-desk run-strat" onclick="playBoardRun()">
    <span class="run-ico">▶</span>
    <span class="run-txt"><b>The strategy library on ${anyRan ? `your ${pending.length} new stock${pending.length > 1 ? "s" : ""}` : `your ${board.length} stock${board.length > 1 ? "s" : ""}`}</b><i>All ${nStrat} of the desk's strategies, backtested across ${pending.length === 1 ? "its" : "each stock's"} ~19-year history — costs included, out-of-sample checked — with every stock-strategy pair that survived, ranked.</i></span>
    <span class="run-meta">${D.bt?.updated ? `<span class="run-last">Library updated · ${esc(strDate(D.bt.updated))}</span>` : ""}<span class="run-go">Read ›</span></span>
  </button>` : board.length ? `<button class="run-desk run-strat ran" onclick="playBoardRun()">
    <span class="run-ico">▶</span>
    <span class="run-txt"><b>The strategy library on your ${board.length} stock${board.length > 1 ? "s" : ""}</b><i>All ${nStrat} strategies across every stock on your board, re-ranked by what survives. Worth revisiting as the library and the price history move on.</i></span>
    <span class="run-meta">${D.bt?.updated ? `<span class="run-last">Library updated · ${esc(strDate(D.bt.updated))}</span>` : ""}<span class="run-go">Replay ›</span></span>
  </button>` : "";

  const results = !board.length ? "" : board.map(s => {
    const list = D.smap?.tickers?.[s] || [];
    const head = `<div class="sb-res-head clickable" onclick="navigate('/ticker/${esc(s)}')"><b>${esc(s)}</b><span class="sub">${esc((names[s]?.name || "").slice(0, 30))}</span><span class="pill ${stratRunOn(s) ? (list.length ? "ok" : "") : "wait"}">${stratRunOn(s) ? list.length + " proven" : "not run yet"}</span></div>`;
    if (!stratRunOn(s)) return `<div class="card" style="padding:0">${head}
      <div class="empty" style="padding:14px 17px">The library's results for <b>${esc(s)}</b> aren't open yet — hit <b>Read ›</b> above for all ${nStrat} strategies backtested across ${esc(s)}'s own ~19 years of price history, and what actually held up.</div></div>`;
    return `<div class="card" style="padding:0">${head}
      ${list.length ? `<table><thead><tr><th>Strategy</th><th class="r">Win rate</th><th class="r">Avg net/trade</th><th class="r">Trades</th><th class="r">Out-of-sample</th></tr></thead><tbody>${
        list.map(t => `<tr><td><b>${esc(t.name)}</b> <span class="tag">${esc((t.category || "").replace(/_/g, " "))}</span></td>
          <td class="r num">${Math.round(t.hit_rate * 100)}%</td><td class="r num up">${sgn(t.net_expectancy_pct)}%</td>
          <td class="r num">${t.n}</td><td class="r num">${t.oos_hit != null ? Math.round(t.oos_hit * 100) + "% · n" + t.oos_n : "unknown"}</td></tr>`).join("")}</tbody></table>`
        : `<div class="empty" style="padding:14px 17px">No strategy cleared the bar on ${esc(s)} — none held win rate ≥55%, positive expectancy after costs, AND out-of-sample. The desk wouldn't signal it. That's a finding, not a gap.</div>`}</div>`;
  }).join("");

  return { board, tiles, addTile, runBar, results };
}

/* ---------- main entry ---------- */
async function pageStrategies() {
  const D = await strLoadState();
  const rows = strRows(D);
  rows.sort((a, b) => b.proven - a.proven);
  const descs = {}; (D.lib?.strategies || []).forEach(s => { descs[s.id] = s; });

  const nStrat = D.bt?.n_strategies || rows.length || 52;
  const provenPairs = Object.values(D.smap?.tickers || {}).reduce((a, l) => a + l.length, 0);
  const nCovered = Object.keys(D.smap?.tickers || {}).length;
  const sTile = (label, val, sub, k) => `<div class="sumtile"><span class="sk">${label}</span><b class="${k || ""}">${val}</b>${sub ? `<i>${sub}</i>` : ""}</div>`;

  const funnel = strFunnel(D);
  const famSector = strFamSector(D);
  const scatterBins = strScatterBins(D);
  const { board, tiles, addTile, runBar, results } = strBoardBlock(D, rows);

  const dict = `<details class="dict"><summary><b>What's in the library, plain English</b><span class="sub">every strategy the desk runs, in one line each</span><span class="dict-arrow">▾</span></summary>
    ${Object.entries(rows.reduce((a, r) => ((a[r.cat] = a[r.cat] || []).push(r), a), {})).map(([cat, list]) => `<div class="dict-cat">${esc((cat || "other").replace(/_/g, " "))}</div>
      ${list.map(r => { const d = descs[r.id] || {};
        return `<div class="dict-row"><div><b>${esc(r.name)}</b>${d.target_pct != null ? `<span class="dict-meta">target +${d.target_pct}% · stop −${d.stop_pct}% · max ${d.hold} sessions</span>` : ""}</div>
        <p>${esc(d.description || "")}</p>
        <span class="dict-proven ${r.proven ? "" : "none"}">${r.proven ? `proven on ${r.proven} stock${r.proven === 1 ? "" : "s"}` : "hasn't cleared the bar anywhere yet"}</span></div>`; }).join("")}`).join("")}
  </details>`;

  const reqForm = `<div class="seg"><h2>Request a strategy</h2><div class="ln"></div><span class="pill">the desk tests it</span></div>
  <div class="card">
    <p class="sub" style="margin-bottom:12px">Trade by a rule that isn't in the library? Explain it below. The desk codes it, backtests it on ~19 years, and if it clears the bar it joins the library.</p>
    ${me ? `<div class="rq-form">
      <div class="ph-row"><input id="rq-title" class="ph-in" inputmode="text" enterkeyhint="next" aria-label="Strategy name" placeholder="Name it (e.g. Monday gap fade)" maxlength="80">
      <input id="rq-tkr" class="ph-in combo" type="search" enterkeyhint="search" aria-label="Ticker (optional)" style="flex:0 1 150px" placeholder="Ticker (optional)" autocomplete="off"></div>
      <textarea id="rq-desc" class="tknote" style="min-height:88px" placeholder="Explain the rules in plain English: when it buys, when it exits, any filters (volume, trend, day of week…)."></textarea>
      <div class="tknote-bar"><button class="note-save" onclick="submitStratRequest()">Send to the desk</button><span id="rq-msg" class="sub"></span></div></div>`
    : `<div class="empty">Sign in to send the desk a strategy to test.<br><br><button class="auth-go" style="max-width:220px" onclick="openAuth('signup')">Create a free account</button></div>`}
  </div>`;

  const view = $("view");
  view.innerHTML = `<div class="today-page st-page">
    <div class="seg" style="margin-top:4px"><h2>Strategies</h2><div class="ln"></div><span class="pill">${nStrat} strategies</span></div>
    <p class="sub" style="margin-bottom:14px">An open rule set, backtested on each stock's own ~19 years. It counts only where it cleared the bar — win rate ≥55%, positive expectancy after costs, profitable out-of-sample. Research, not advice.</p>
    <div class="sumstrip s4">
      ${sTile("Strategies", nStrat, "transparent rule sets", "")}
      ${sTile("Proven pairs", provenPairs, "strategy x stock, after costs + OOS", provenPairs ? "up" : "")}
      ${sTile("Stocks with a proven edge", nCovered, "across the universe", "")}
      ${sTile("Library updated", strDate(D.bt?.updated), "full re-backtest", "")}
    </div>

    <div class="seg"><h2>By family</h2><div class="ln"></div></div>
    ${strFamBars(rows, funnel ? funnel[4].n : null)}

    <div class="seg"><h2>The funnel</h2><div class="ln"></div><span class="pill">every pair the library has ever tried</span></div>
    <div class="card">${strFunnelBlock(funnel)}</div>

    <div class="seg"><h2>Where it holds up</h2><div class="ln"></div>
      <div class="wl-chips" role="group" aria-label="View"><button data-lens="heat" aria-pressed="${STR_S.lens === "heat"}">By sector</button><button data-lens="scatter" aria-pressed="${STR_S.lens === "scatter"}">Win rate vs net</button></div>
    </div>
    <div class="card">${STR_S.lens === "heat" ? strHeat(famSector) : strScatter(scatterBins)}</div>

    <div class="seg"><h2>Your board</h2><div class="ln"></div><span class="pill">${board.length ? board.length + " stock" + (board.length > 1 ? "s" : "") : "empty"}</span></div>
    <div class="card">
      <div class="sb-grid">${tiles}${addTile}</div>
      <span id="sb-msg" class="sub" style="display:block;margin-top:8px"></span>
      ${!me && board.length ? `<span class="sub" style="display:block;margin-top:4px">Your board lives in this session only — <a style="color:var(--accent);cursor:pointer" onclick="openAuth('signup')">sign in</a> to keep it.</span>` : ""}
    </div>
    ${isSubscribed() ? runBar + results
      : planWall("The strategy library on your board",
        "Pick your stocks above to read every strategy's results on each — ~19 years of that stock's own history per rule, with win rate, expectancy after costs and out-of-sample honesty.")}

    <div class="seg"><h2>The library</h2><div class="ln"></div></div>
    ${strCards(rows, descs, D.bt?.bars)}
    ${dict}
    ${reqForm}
  </div>`;

  strWire(view.querySelector(".st-page"));
}

function strWire(root) {
  if (!root) return;
  root.addEventListener("click", e => {
    const fam = e.target.closest("[data-fam]");
    if (fam) { STR_S.fam = fam.dataset.fam || null; pageStrategies(); return; }
    const lens = e.target.closest("[data-lens]");
    if (lens) { STR_S.lens = lens.dataset.lens; pageStrategies(); return; }
    const card = e.target.closest("[data-strcard]");
    if (card && !e.target.closest("a,button,.clickable")) {
      const id = card.dataset.strcard;
      STR_S.openId = STR_S.openId === id ? null : id;
      pageStrategies();
    }
  });
}
