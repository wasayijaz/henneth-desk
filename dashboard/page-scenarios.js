// scenarios page — redesign 2026-09
// Behaviour parity source: old pageScenarios (app.js, removed here, kept in git history).
// New visual structure ported from docs/redesign-mockups/scenarios-mockup.html.
//
// IMPORTANT — this page does NOT use the mockup's sample data. The mockup's 22-factor pool
// (docs/redesign-mockups/wl/scenarios-data.js, window.SCN) was measured OFFLINE and is not in
// state/ — Rule 2 forbids quoting a number the data layer doesn't have. Every factor, spot
// value, beta, correlation, p-value, sector name and date below comes from state/sector_macro.json
// and state/macro_history.json via j(). The factor pool is DERIVED from macro_history.json's
// keys, not hardcoded — SC_META below is presentation-only metadata (label/unit/group) for the
// factors the desk currently measures; a future factor state doesn't know about yet still renders,
// using its raw key as the label and no unit, until someone adds a metadata entry for it.
//
// Units fix: state stores the us10y beta as "per PERCENTAGE-POINT change in the US 10y yield"
// (state/sector_macro.json method.us10y_units, confirmed against scripts/sector_macro.py line 13
// — no extra scaling factor). The other six factors are relative-% movers. us10y therefore gets
// its own pp-native move control (additive target, "+0.25 pp" display) instead of reusing the
// relative-% control the other factors use — mixing the two was the live bug this port fixes.
//
// STRONG/WEAK/NO LINK badges are derived only because state carries p_value per driver — compared
// against state/sector_macro.json's own method.bonferroni_bar / method.fdr_cutoff. No badge is
// invented where state has no p-value.
//
// No advice language: output reads "the setup"/"the desk's read", never "you should buy".
// Missing/unavailable data renders as the literal string "unknown".

const MARKET_SECTOR_KEY = "THE MARKET (KSE100 proxy)";
const SC_CAP = 6;

// Presentation-only metadata for the factors the desk currently measures. Keyed by the same
// names state/macro_history.json's `factors` object and state/sector_macro.json's driver
// `factor` field use. Any key state carries that isn't listed here still renders (see scMeta).
const SC_META = {
  oil: { label: "Oil (WTI)", short: "Oil", unit: "$", group: "Commodities" },
  gold: { label: "Gold", short: "Gold", unit: "$", group: "Commodities" },
  usdpkr: { label: "USD/PKR", short: "Rupee", unit: "Rs", group: "Currency" },
  dollar: { label: "Dollar index", short: "DXY", unit: "", group: "Currency" },
  sp500: { label: "S&P 500", short: "S&P", unit: "", group: "Global markets" },
  em_equity: { label: "EM equity flows", short: "EM eq.", unit: "", group: "Global markets" },
  us10y: { label: "US 10-year yield", short: "US 10y", unit: "pp", group: "Rates" },
};

// A small set of named move-presets ("combos"), in the mockup's spirit — but every one here is
// built only from the 7 factor names the desk actually measures today, and is filtered again at
// render time against whatever keys state currently carries, so a factor state drops silently
// drops its combos too rather than fabricating a piece.
const SC_COMBOS = [
  { id: "oil_spike", label: "Oil spike", set: { oil: 15 } },
  { id: "rupee_slide", label: "Rupee slide", set: { usdpkr: 8 } },
  { id: "global_selloff", label: "Global sell-off", set: { sp500: -4, em_equity: -5 } },
  { id: "dollar_surge", label: "Dollar surge", set: { dollar: 5 } },
  { id: "yields_jump", label: "US yields jump", set: { us10y: 0.5 } },
];

// Only overlap the desk can actually demonstrate with 7 factors: sp500 and em_equity are both
// global-risk-appetite factors and tend to move together — staging both double-counts one signal.
const SC_OVERLAP_PAIRS = [["sp500", "em_equity"]];

// One colour per staged piece (sections 04/05), built only from tokens already on the page —
// no new hex colours. Assigned by stage order so a piece keeps its colour as others are added/removed.
const SC_PALETTE = ["var(--ink1)", "var(--up)", "var(--dn)", "var(--ink3)",
  "color-mix(in srgb, var(--up) 50%, var(--ink1))", "color-mix(in srgb, var(--dn) 50%, var(--ink1))"];
function scColor(f) { const i = SC_S.stage.indexOf(f); return SC_PALETTE[i < 0 ? 0 : i % SC_PALETTE.length]; }

let SC_S = { stage: [], mv: {}, grp: "all", q: "" };

/* ---------- formatting (missing data always renders "unknown") ---------- */
function scMeta(f) { return SC_META[f] || { label: f, short: f, unit: "", group: "Other" }; }
function scNum(v, d = 2) { return v == null || !isFinite(v) ? "unknown" : fmt(v, d); }
function scDate(v) { return v ? String(v).slice(0, 10) : "unknown"; }
function scDefaultMove(f) { return f === "us10y" ? 0.25 : 10; }
function scMoveOf(f) { return SC_S.mv[f] ?? scDefaultMove(f); }
function scMoveTxt(f, mv) { return scMeta(f).unit === "pp" ? sgn(+mv.toFixed(2)) + " pp" : sgn(+mv.toFixed(1)) + "%"; }

/* ---------- data ---------- */
async function scLoadState() {
  const [sm, mh, quant, live, sect, scn] = await Promise.all([
    j("sector_macro.json"), j("macro_history.json"), j("quant.json"), j("live.json"), j("sectors.json"),
    j("scenario_stocks.json"),
  ]);
  return { sm, mh, quant, live, sect, scn };
}

// ---- per-stock "KSE effect" (v2) — driven only by state/scenario_stocks.json's by_factor rows.
// Named stocks appear ONLY as measured past co-movement (beta/corr), never as a forecast — every
// render path below carries the mandatory caption. survives_fdr/survives_bonferroni are shown
// honestly (a row that fails FDR renders "weaker"/striped, never silently promoted).
const SC_STK_LOOSE = 0.05;   // p <= this => "rose with" / "fell with" grouping
const SC_STK_NOLINK = 0.3;   // p >  this => "little measured link" grouping
const SC_STK_STEPS = [0.1, 0.25, 0.5, 1, 2]; // intensity thresholds, in % estimated move

function scStkScale(f, mv) { return scMeta(f).unit === "pp" ? 10 * mv : mv; }

function scStkHalf95(t) {
  const r = t?.corr, n = t?.days;
  if (r == null || !isFinite(r) || n == null || n < 4 || Math.abs(r) >= 1) return null;
  return 1.96 * Math.abs(t.beta) / (Math.abs(r) * Math.sqrt((n - 2) / (1 - r * r)));
}

function scStkEst(t, f) {
  if (t?.beta == null || !isFinite(t.beta)) return null;
  return t.beta * scStkScale(f, scMoveOf(f));
}

function scStkIntensity(est) {
  if (est == null || !isFinite(est)) return 0;
  return SC_STK_STEPS.filter(x => Math.abs(est) >= x).length;
}

function scStkGroups(D, f) {
  const rows = D.scn?.by_factor?.[f] || [];
  const up = rows.filter(t => t.beta > 0 && t.p_value != null && t.p_value <= SC_STK_LOOSE)
    .sort((a, b) => a.p_value - b.p_value || Math.abs(b.corr) - Math.abs(a.corr)).slice(0, 5);
  const dn = rows.filter(t => t.beta < 0 && t.p_value != null && t.p_value <= SC_STK_LOOSE)
    .sort((a, b) => a.p_value - b.p_value || Math.abs(b.corr) - Math.abs(a.corr)).slice(0, 5);
  const nil = rows.filter(t => t.p_value != null && t.p_value > SC_STK_NOLINK)
    .sort((a, b) => (D.scn?.stocks?.[b.stock]?.weight_pct || 0) - (D.scn?.stocks?.[a.stock]?.weight_pct || 0)).slice(0, 4);
  return { up, dn, nil, total: rows.length };
}

function scStkRow(D, f, t) {
  const meta = D.scn?.stocks?.[t.stock] || {};
  const est = scStkEst(t, f);
  const half = scStkHalf95(t);
  const n = scStkIntensity(est);
  const dir = est == null ? "mut" : est > 0 ? "up" : est < 0 ? "dn" : "mut";
  const weak = !t.survives_fdr;
  const cells = Array.from({ length: 5 }, (_, i) => `<i class="${i < n ? "on" : ""}"></i>`).join("");
  const estTxt = est == null ? "unknown" : `${sgn(+est.toFixed(2))}%`;
  const rangeTxt = half == null ? "" : ` <small>(${sgn(+(est - half).toFixed(2))}% to ${sgn(+(est + half).toFixed(2))}%)</small>`;
  return `<div class="sc-st ${weak ? "weak" : ""}">
    <div class="sc-st-sym"><b>${esc(t.stock)}</b><span class="sub">${esc(meta.name || "unknown")}</span></div>
    <div class="sc-int" data-c="${dir}">${cells}</div>
    <div class="sc-st-est num ${dir}">${estTxt}${rangeTxt}</div>
    <div class="sc-st-fit sub">r ${scNum(t.corr)} · n ${t.days ?? "unknown"}</div>
  </div>`;
}

function scStkGroupBlock(D, f, title, rows, note) {
  if (!rows.length) return `<div class="sc-grp"><h4>${esc(title)}</h4><div class="sc-empty">unknown — nothing measured in this group.</div></div>`;
  return `<div class="sc-grp"><h4>${esc(title)} <span class="sub">(${rows.length} of ${scStkGroups(D, f).total} tested)</span></h4>
    ${rows.map(t => scStkRow(D, f, t)).join("")}
  </div>`;
}

// The per-factor stock-intensity panel — the mandatory non-advice caption is always rendered
// alongside named stocks, and the file's own `note` is surfaced once per panel.
function scDialStocks(D, f) {
  if (!D.scn) return `<div class="sc-stk-empty sub">unknown — state/scenario_stocks.json unavailable this cycle.</div>`;
  const g = scStkGroups(D, f);
  const m = scMeta(f);
  return `<div class="sc-dq">
    <div class="sc-dq-h sub">This dial alone · per-stock measured co-movement, ${esc(m.short)}</div>
    ${scStkGroupBlock(D, f, "Rose with it", g.up)}
    ${scStkGroupBlock(D, f, "Fell with it", g.dn)}
    ${scStkGroupBlock(D, f, "Little measured link", g.nil)}
    <p class="sc-stk-cap">Measured past co-movement, not a forecast or a recommendation.</p>
    <div class="sc-intkey">
      <span>Bars = how many of ${SC_STK_STEPS.map(x => x + "%").join("/")} estimated-move thresholds are met.</span>
      <span>Striped = fails the FDR significance test (shown as "weaker").</span>
    </div>
  </div>`;
}

// The live factor pool — derived from state, not hardcoded, so a future pipeline change that
// adds factors to macro_history.json shows up here automatically.
function scFactorKeys(D) {
  return Object.keys(D.mh?.factors || {}).filter(f => Object.keys(D.mh.factors[f]?.series || {}).length);
}

function scSpot(D, f) {
  const ser = D.mh?.factors?.[f]?.series || {};
  const days = Object.keys(ser).sort();
  return days.length ? { v: ser[days[days.length - 1]], d: days[days.length - 1] } : null;
}

function scSpark(D, f) {
  const ser = D.mh?.factors?.[f]?.series || {};
  const days = Object.keys(ser).sort().slice(-30);
  if (days.length < 2) return "";
  const vals = days.map(d => ser[d]);
  const lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1) * 100).toFixed(1)},${(20 - (v - lo) / span * 20).toFixed(1)}`).join(" ");
  const up = vals[vals.length - 1] >= vals[0];
  return `<svg class="sc-spark" viewBox="0 0 100 20" preserveAspectRatio="none"><polyline points="${pts}" class="${up ? "up" : "dn"}"/></svg>`;
}

function scDriver(D, sec, f) { return (D.sm?.by_sector?.[sec]?.drivers || []).find(x => x.factor === f); }

// per-factor STRONG/WEAK/NO LINK tier — strongest tier the factor reaches across any sector,
// gated on state's own p_value + significance bars (method.bonferroni_bar / method.fdr_cutoff).
function scFactorTier(D, f) {
  const bon = D.sm?.method?.bonferroni_bar, fdr = D.sm?.method?.fdr_cutoff;
  if (bon == null || fdr == null) return null;
  let best = "none";
  for (const sec of Object.keys(D.sm?.by_sector || {})) {
    const d = scDriver(D, sec, f);
    if (!d || d.p_value == null) continue;
    if (d.p_value <= bon) return "strong";
    if (d.p_value <= fdr) best = "weak";
  }
  return best;
}
const SC_BADGE_TXT = { strong: "STRONG", weak: "WEAK", none: "NO LINK" };

function scReach(D, f) {
  return Object.keys(D.sm?.by_sector || {}).filter(s => s !== MARKET_SECTOR_KEY && scDriver(D, s, f)?.demonstrated).length;
}

// contribution of one staged factor's move to one sector's estimated return, in the sector's own
// units the driver beta was fit in (percentage points of return) — us10y's move is itself pp, the
// other six are relative %, but the formula shape (beta × move) is identical either way; only the
// move's own units differ per factor, per state/sector_macro.json's method.us10y_units.
function scContribution(D, sec, f) {
  const d = scDriver(D, sec, f);
  if (!d || !d.demonstrated) return null;
  return d.beta * scMoveOf(f);
}

function scSectorTotal(D, sec) {
  let total = 0, any = false;
  const hits = [];
  for (const f of SC_S.stage) {
    const c = scContribution(D, sec, f);
    if (c != null) { total += c; any = true; hits.push({ f, est: c }); }
  }
  return { total, any, hits };
}

function scOverlapWarning() {
  const on = new Set(SC_S.stage);
  const hit = SC_OVERLAP_PAIRS.find(([a, b]) => on.has(a) && on.has(b));
  if (!hit) return "";
  return `<p class="sc-warn">${esc(scMeta(hit[0]).short)} and ${esc(scMeta(hit[1]).short)} are both global risk-appetite factors that tend to move together historically — staging both may double-count one signal rather than two independent ones.</p>`;
}

/* ---------- render pieces ---------- */
function scBadgeChip(tier) {
  if (tier == null) return "";
  return `<i class="sc-badge sc-badge-${tier}">${SC_BADGE_TXT[tier]}</i>`;
}

function scPieceCard(D, f) {
  const m = scMeta(f), spot = scSpot(D, f), tier = scFactorTier(D, f), reach = scReach(D, f);
  const staged = SC_S.stage.includes(f);
  const spotTxt = spot ? `${m.unit}${scNum(spot.v)}${m.unit === "pp" ? "" : ""} <span class="sub">(${scDate(spot.d)})</span>` : "unknown";
  return `<div class="sc-piece ${staged ? "on" : ""}" data-f="${esc(f)}" role="button">
    <div class="sc-piece-h"><b>${esc(m.label)}</b>${scBadgeChip(tier)}</div>
    ${scSpark(D, f)}
    <div class="sc-piece-spot">${spotTxt}</div>
    <div class="sc-piece-reach">${reach ? `moved <b>${reach}</b> sector${reach === 1 ? "" : "s"} measurably` : "no sector shows a demonstrated link"}</div>
    <div class="sc-piece-cta">${staged ? "on the stage — tap to remove" : "tap to stage"}</div>
  </div>`;
}

function scStageCard(D, f) {
  const m = scMeta(f), spot = scSpot(D, f), mv = scMoveOf(f), pp = m.unit === "pp";
  const target = spot ? (pp ? spot.v + mv : spot.v * (1 + mv / 100)) : null;
  const range = pp ? { min: -1, max: 1, step: 0.05 } : { min: -30, max: 30, step: 0.5 };
  return `<div class="sc-stc" data-f="${esc(f)}">
    <div class="sc-stc-h"><b>${esc(m.label)}</b><button class="sc-x" data-remove="${esc(f)}" aria-label="Remove">×</button></div>
    <div class="sc-stc-move">${scMoveTxt(f, mv)}${spot ? `<span class="sub"> → ${m.unit && !pp ? m.unit : ""}${scNum(target)}${pp ? " pp" : ""}</span>` : ""}</div>
    <input type="range" class="sc-slider" data-dial="${esc(f)}" min="${range.min}" max="${range.max}" step="${range.step}" value="${mv}">
    <input type="text" inputmode="decimal" class="ph-in sc-num" data-dial-n="${esc(f)}" value="${mv}">
    ${scDialStocks(D, f)}
  </div>`;
}

function scComboChip(D, combo, live) {
  const keys = Object.keys(combo.set).filter(k => live.includes(k));
  if (!keys.length) return "";
  const parts = keys.map(k => `${scMeta(k).short} ${sgn(combo.set[k])}${scMeta(k).unit === "pp" ? "pp" : "%"}`).join(", ");
  return `<button class="sc-combo" data-combo="${esc(combo.id)}" title="${esc(parts)}">${esc(combo.label)}</button>`;
}

function scGauge(D) {
  const hasMarket = !!D.sm?.by_sector?.[MARKET_SECTOR_KEY];
  if (!hasMarket) return `<div class="sc-gauge-empty">unknown — no market-wide row in the data layer</div>`;
  const { total, any } = scSectorTotal(D, MARKET_SECTOR_KEY);
  if (!SC_S.stage.length) return `<div class="sc-gauge-empty">Stage a factor to see the desk's read on the KSE-100 proxy.</div>`;
  if (!any) return `<div class="sc-gauge-empty">No demonstrated link from the staged factor(s) to the market as a whole.</div>`;
  // semicircular needle: -3%..+3% mapped to -90deg..+90deg, clamped
  const clamped = Math.max(-3, Math.min(3, total));
  const ang = (clamped / 3) * 90;
  const rad = (ang - 90) * Math.PI / 180;
  const cx = 60, cy = 60, r = 46;
  const x = cx + r * Math.cos(rad), y = cy + r * Math.sin(rad);
  return `<svg class="sc-gauge" viewBox="0 0 120 66">
    <path d="M 14 60 A 46 46 0 0 1 106 60" class="sc-gauge-arc"/>
    <line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" class="sc-gauge-needle"/>
    <circle cx="${cx}" cy="${cy}" r="3" class="sc-gauge-hub"/>
  </svg>
  <div class="sc-gauge-val ${total > 0.05 ? "up" : total < -0.05 ? "dn" : ""}">${sgn(+total.toFixed(2))}%</div>
  <div class="sub">the desk's read on the KSE-100 proxy under the staged move(s)</div>`;
}

function scBoardTiles(D) {
  const secs = Object.keys(D.sm?.by_sector || {}).filter(s => s !== MARKET_SECTOR_KEY);
  if (!SC_S.stage.length) return `<div class="sc-empty">Stage a factor above to populate the board.</div>`;
  const rows = secs.map(sec => ({ sec, ...scSectorTotal(D, sec) }));
  rows.sort((a, b) => b.total - a.total);
  return `<div class="sc-board">${rows.map(r => `
    <div class="sc-tile ${!r.any ? "quiet" : r.total > 0 ? "up" : r.total < 0 ? "dn" : ""} clickable" onclick="navigate('/sectors')">
      <b>${esc(r.sec)}</b>
      <span class="num">${r.any ? sgn(+r.total.toFixed(2)) + "%" : "no link"}</span>
    </div>`).join("")}</div>`;
}

function scNotMeasured() {
  return `<p class="sub sc-footnote">Domestic SBP-rate scenarios aren't offered because the desk has only measured <b>global</b> factors against sectors — US yields are the closest measured cousin, and pretending otherwise would be a guess dressed as data. As the data layer measures more factors, they appear in the pool above automatically.</p>`;
}

/* ---------- section head (numbered, matches mockup's head('01', title, sub, right)) ---------- */
function scHead(n, title, sub, right) {
  return `<div class="today-section-head"><p class="today-kicker">${esc(n)} · ${esc(title)}<span> · ${esc(sub)}</span></p><div><b>${right || ""}</b></div></div>`;
}

function scSectors(D) { return Object.keys(D.sm?.by_sector || {}).filter(s => s !== MARKET_SECTOR_KEY); }

/* ---------- 04 — what pushes each sector (stacked tornado bars, real betas only) ---------- */
function scTornadoRows(D) {
  const secs = [MARKET_SECTOR_KEY, ...scSectors(D)];
  return secs.map(sec => {
    const hits = SC_S.stage.map(f => ({ f, c: scContribution(D, sec, f) })).filter(x => x.c != null);
    return { sec, hits, total: hits.reduce((a, x) => a + x.c, 0) };
  });
}

function scTornado(D) {
  if (!SC_S.stage.length) return `<div class="sc-empty">Stage a factor above to see what pushes each sector.</div>`;
  const rows = scTornadoRows(D);
  const maxAbs = Math.max(1e-6, ...rows.map(r => {
    let pos = 0, neg = 0;
    r.hits.forEach(h => { if (h.c > 0) pos += h.c; else neg += -h.c; });
    return Math.max(pos, neg);
  }));
  const seg = h => `<span class="sc-torn-seg" style="width:${(Math.abs(h.c) / maxAbs * 100).toFixed(1)}%;background:${scColor(h.f)}" title="${esc(scMeta(h.f).short)} ${sgn(+h.c.toFixed(2))}%"></span>`;
  const bar = r => {
    if (!r.hits.length) return `<div class="sc-torn-bar"><span class="sc-torn-none">no demonstrated link</span></div>`;
    const pos = r.hits.filter(h => h.c > 0), neg = r.hits.filter(h => h.c < 0);
    return `<div class="sc-torn-bar"><div class="sc-torn-neg">${neg.map(seg).join("")}</div><div class="sc-torn-mid"></div><div class="sc-torn-pos">${pos.map(seg).join("")}</div></div>`;
  };
  const body = rows.map(r => `<div class="sc-torn-row"><span class="sc-torn-label">${esc(r.sec === MARKET_SECTOR_KEY ? "KSE-100 proxy" : r.sec)}</span>${bar(r)}<span class="sc-torn-val ${!r.hits.length ? "mut" : r.total > 0 ? "up" : r.total < 0 ? "dn" : ""}">${r.hits.length ? sgn(+r.total.toFixed(2)) + "%" : "no link"}</span></div>`).join("");
  const legend = SC_S.stage.map(f => `<span class="sc-legend-i"><i style="background:${scColor(f)}"></i>${esc(scMeta(f).short)}</span>`).join("");
  return `<div class="sc-torn">${body}</div><div class="sc-legend">${legend}</div>
  <p class="sub sc-footnote">Each colour is one staged piece; segment width is its estimated push on that sector's next-session return. A piece with no demonstrated link to a sector adds no segment there.</p>`;
}

/* ---------- 05 — sector x shock grid (same betas, one column per staged piece) ---------- */
function scCell(D, sec, f) {
  const d = scDriver(D, sec, f);
  if (!d) return { txt: "unknown", cls: "mut" };
  if (!d.demonstrated) return { txt: "no link", cls: "mut" };
  const c = d.beta * scMoveOf(f);
  return { txt: sgn(+c.toFixed(2)) + "%", cls: c > 0 ? "up" : c < 0 ? "dn" : "" };
}

function scGrid(D) {
  if (!SC_S.stage.length) return `<div class="sc-empty">Stage a factor above to see the sector × shock grid.</div>`;
  const secs = scSectors(D), cols = SC_S.stage;
  const cssCols = `130px repeat(${cols.length},1fr)`;
  const head = `<div class="sc-grid-row sc-grid-head" style="grid-template-columns:${cssCols}"><span></span>${cols.map(f => `<button class="sc-grid-col" data-colrm="${esc(f)}" style="color:${scColor(f)}" title="Remove ${esc(scMeta(f).short)} from the stage">${esc(scMeta(f).short)}</button>`).join("")}</div>`;
  const rows = secs.map(sec => `<div class="sc-grid-row" style="grid-template-columns:${cssCols}"><span class="sc-grid-lbl">${esc(sec)}</span>${cols.map(f => { const c = scCell(D, sec, f); return `<span class="sc-grid-cell ${c.cls}">${esc(c.txt)}</span>`; }).join("")}</div>`).join("");
  return `<div class="sc-grid">${head}${rows}</div>
  <p class="sub sc-footnote">Filled = the piece's estimated push on that sector. "no link" = tested, nothing survived. "unknown" = not yet measured for this pair. Click a column head to remove that piece from the stage.</p>`;
}

/* ---------- 06 — watchlist through the scenario (real watchlist, real last close) ---------- */
function scWatchRows(D) {
  const list = typeof watchlist === "function" ? watchlist() : [];
  const q = D.quant?.tickers || {}, lv = D.live?.tickers || {}, sect = D.sect?.tickers || {};
  return list.map(s => {
    const qq = q[s];
    const px = lv[s]?.current ?? qq?.close;
    const sector = sect[s]?.sector || null;
    const known = sector && D.sm?.by_sector?.[sector];
    const { total, any } = known ? scSectorTotal(D, sector) : { total: 0, any: false };
    const est = SC_S.stage.length && any ? total : null;
    const proj = px != null && est != null ? px * (1 + est / 100) : null;
    return { s, px, sector, known: !!known, est, proj, priced: qq != null };
  });
}

function scWatch(D) {
  if (typeof me !== "undefined" && !me) return `<div class="sc-empty">Sign in to see your watchlist under this scenario — star any stock and it appears here.</div>`;
  const rows = scWatchRows(D);
  if (!rows.length) return `<div class="sc-empty">No stocks on your watchlist yet.</div>`;
  const priced = rows.filter(r => r.priced);
  if (!priced.length) return `<div class="sc-empty">None of your watchlist names are in today's price data.</div>`;
  const cellTxt = r => !SC_S.stage.length ? "stage a piece" : !r.known ? "sector unmeasured" : r.est == null ? "no link" : sgn(+r.est.toFixed(2)) + "%";
  const cellCls = r => !SC_S.stage.length || !r.known || r.est == null ? "mut" : r.est > 0 ? "up" : r.est < 0 ? "dn" : "";
  const body = priced.map(r => `<div class="sc-wl-row"><b>${esc(r.s)}</b><span class="sc-wl-sec">${esc(r.sector || "sector unknown")}</span><span class="sc-wl-px">${r.px != null ? fmt(r.px, 2) : "unknown"}</span><span class="sc-wl-est ${cellCls(r)}">${cellTxt(r)}</span><span class="sc-wl-proj">${r.proj != null ? fmt(r.proj, 2) : "unknown"}</span></div>`).join("");
  const missing = rows.length - priced.length;
  return `<div class="sc-wl"><div class="sc-wl-row sc-wl-head"><b>Ticker</b><span>Sector</span><span>Last close</span><span>Est. move</span><span>Projected</span></div>${body}</div>
  ${missing ? `<p class="sub sc-footnote">${missing} name${missing === 1 ? "" : "s"} not in today's price data, not shown.</p>` : ""}
  <p class="sub sc-footnote">A name moves with its sector here only on average; single stocks carry their own news. Last close is quant.json/live.json, the same source the Watchlist page uses.</p>`;
}

/* ---------- 07 — how the estimate is made (static prose + real computed figures) ---------- */
function scStats(D) {
  const secs = Object.keys(D.sm?.by_sector || {});
  const bon = D.sm?.method?.bonferroni_bar, fdr = D.sm?.method?.fdr_cutoff;
  let tested = 0, sB = 0, sF = 0;
  const r2 = [];
  for (const sec of secs) {
    const row = D.sm.by_sector[sec];
    if (row?.joint_r2_pct != null && isFinite(row.joint_r2_pct)) r2.push(row.joint_r2_pct);
    for (const d of row?.drivers || []) {
      if (d.p_value == null) continue;
      tested++;
      if (bon != null && d.p_value <= bon) sB++;
      else if (fdr != null && d.p_value <= fdr) sF++;
    }
  }
  return { tested, sB, sF, r2min: r2.length ? Math.min(...r2) : null, r2max: r2.length ? Math.max(...r2) : null };
}

function scWorked(D) {
  const f = SC_S.stage[0];
  if (!f) return "Stage a piece above to see a worked example.";
  const d = scDriver(D, MARKET_SECTOR_KEY, f);
  if (!d || !d.demonstrated) return `No demonstrated link from ${esc(scMeta(f).short)} to the KSE-100 proxy — the sum below would be zero for that pair, so it isn't shown as one.`;
  const mv = scMoveOf(f), c = d.beta * mv;
  return `${esc(scMeta(f).short)} dialed to ${scMoveTxt(f, mv)}. Measured beta <b>${scNum(d.beta, 3)}</b> × move = <b>${sgn(+c.toFixed(2))}%</b> on the KSE-100 proxy. Every sector total on the board above is this same sum, one factor at a time, across whatever's staged.`;
}

function scMethodBlock(D) {
  const st = scStats(D), bon = D.sm?.method?.bonferroni_bar, fdr = D.sm?.method?.fdr_cutoff;
  return `<div class="sc-steps">
    <div class="sc-inset"><h3>1 · THE MEASURE</h3><p>Each sector's daily return was regressed on each factor's previous-session move. US 10-year yield is measured in percentage-point moves, not percent — a 4.20% → 4.45% move is a <b>0.25pp</b> move, not a 6% one; the other six factors move in relative %.</p></div>
    <div class="sc-inset"><h3>2 · THE FILTER</h3><p>${st.tested ? `<b>${st.tested}</b> sector-piece links tested. <b>${st.sB}</b> pass the strict bar (Bonferroni, p ≤ ${scNum(bon, 5)}); <b>${st.sF}</b> more pass the false-discovery bar only (p ≤ ${scNum(fdr, 5)}). Only those move an estimate.` : "Link counts unknown — sector_macro.json does not carry p-values for these pieces yet."}</p></div>
    <div class="sc-inset"><h3>3 · THE SUM</h3><p>${scWorked(D)}</p></div>
  </div>
  <div class="sc-steps" style="margin-top:10px">
    <div class="sc-inset"><h3>STACKING</h3><p>Each beta was fit one piece at a time. Stacking several pieces on the stage adds their single-piece estimates — pieces that tend to move together (global equities with each other, US yields with each other) can double-count part of the same move. The stage flags it above when it happens.</p></div>
    <div class="sc-inset"><h3>HOW MUCH IT EXPLAINS</h3><p>${st.r2min != null ? `The measured pieces together explain only <b>${scNum(st.r2min, 1)}–${scNum(st.r2max, 1)}%</b> of a sector's daily moves (R²).` : "How much of a sector's daily move these pieces explain is unknown — sector_macro.json does not carry an R² figure yet."} The rest is local news, flows and noise — a sector with no link is no evidence, not a forecast of no move.</p></div>
    <div class="sc-inset"><h3>WHAT IT IS NOT</h3><p>Descriptive research on the desk's own data — not a trading signal and not advice. The estimate is for one session after a one-day move; it says how a sector has tended to react historically, not what it will do.</p></div>
  </div>`;
}

/* ---------- main ---------- */
async function pageScenarios() {
  const locked = !hasFeature("scenarios");
  const D = locked ? { sm: null, mh: null } : await scLoadState();
  const FKEYS = locked ? [] : scFactorKeys(D);
  SC_S.stage = SC_S.stage.filter(f => FKEYS.includes(f));

  const groups = ["all", ...Array.from(new Set(FKEYS.map(f => scMeta(f).group)))];
  const q = SC_S.q.trim().toLowerCase();
  const visible = FKEYS.filter(f => (SC_S.grp === "all" || scMeta(f).group === SC_S.grp)
    && (!q || scMeta(f).label.toLowerCase().includes(q) || f.includes(q)));

  $("view").innerHTML = `
  <div class="today-page sc-page">
  <div class="seg" style="margin-top:4px"><h2>Scenarios</h2><div class="ln"></div><span class="pill">measured, not imagined</span></div>
  <p class="sub" style="margin-bottom:12px">"What if oil hits $95?" — answered from what the desk has actually measured, not from a story. Stage up to ${SC_CAP} factors and dial their moves.</p>
  ${locked ? planWall("The scenario simulator",
      "Oil, the rupee, Wall Street, US yields — which PSX sectors historically leaned up or down, from measured sector betas, with the honest link strength attached.") : `

  <div class="card sc-pool-card">
    ${scHead("01", "THE POOL", "every factor the desk has measured")}
    <div class="seg-tabs">${groups.map(g => `<button class="seg-opt ${SC_S.grp === g ? "on" : ""}" data-grp="${esc(g)}">${esc(g === "all" ? "All" : g)}</button>`).join("")}</div>
    <input type="text" class="ph-in sc-search" placeholder="Search factors…" value="${esc(SC_S.q)}" data-search>
    <div class="sc-pool">${visible.length ? visible.map(f => scPieceCard(D, f)).join("") : '<div class="sc-empty">No factors match.</div>'}</div>
    ${SC_COMBOS.map(c => scComboChip(D, c, FKEYS)).join("") ? `<div class="sc-combos"><span class="sub">Combos: </span>${SC_COMBOS.map(c => scComboChip(D, c, FKEYS)).join("")}</div>` : ""}
    ${scNotMeasured()}
  </div>

  <div class="card sc-stage-card">
    ${scHead("02", "THE STAGE", "dial each piece's move", `${SC_S.stage.length}/${SC_CAP} staged`)}
    ${SC_S.stage.length ? `<div class="sc-stage-h">${SC_S.stage.length ? `<button class="sc-reset" data-reset>reset</button>` : ""}</div><div class="sc-stage">${SC_S.stage.map(f => scStageCard(D, f)).join("")}</div>` : `<div class="sc-empty">Tap a piece in the pool to stage it.</div>`}
    ${scOverlapWarning()}
    <div class="sc-gauge-wrap">${scGauge(D)}</div>
    ${D.scn?.note ? `<p class="sc-scn-note sub">${esc(D.scn.note)}</p>` : ""}
  </div>

  <div class="card sc-board-card">
    ${scHead("03", "THE BOARD", "every sector, this stage combined")}
    ${scBoardTiles(D)}
    <div class="tnote">Each estimate = the sector's measured daily beta to a staged factor (correction-survived) × the dialed move — the typical <i>co-movement</i>, not a forecast. Even the strongest links explain only a few percent of a sector's daily variance, and a real shock arrives tangled with everything else. History, not prophecy — and never advice.</div>
  </div>

  <div class="card sc-torn-card">
    ${scHead("04", "WHAT PUSHES EACH SECTOR", "same betas, one bar per sector")}
    ${scTornado(D)}
  </div>

  <div class="card sc-grid-card">
    ${scHead("05", "SECTOR × SHOCK", "one column per staged piece")}
    ${scGrid(D)}
  </div>

  <div class="card sc-wl-card">
    ${scHead("06", "WATCHLIST THROUGH THE SCENARIO", "the stage applied to your names")}
    ${scWatch(D)}
  </div>

  <div class="card sc-method-card">
    ${scHead("07", "HOW THE ESTIMATE IS MADE", "method, filter, and what it isn't")}
    ${scMethodBlock(D)}
  </div>
  `}
  </div>`;

  if (!locked) scWire($("view").querySelector(".sc-page"));
}

function scWire(root) {
  root.addEventListener("click", e => {
    const piece = e.target.closest("[data-f]");
    if (piece && !e.target.closest("[data-remove]")) {
      const f = piece.dataset.f;
      const i = SC_S.stage.indexOf(f);
      if (i >= 0) SC_S.stage.splice(i, 1);
      else if (SC_S.stage.length < SC_CAP) SC_S.stage.push(f);
      pageScenarios();
      return;
    }
    const rm = e.target.closest("[data-remove]");
    if (rm) { SC_S.stage = SC_S.stage.filter(f => f !== rm.dataset.remove); pageScenarios(); return; }
    const grp = e.target.closest("[data-grp]");
    if (grp) { SC_S.grp = grp.dataset.grp; pageScenarios(); return; }
    const combo = e.target.closest("[data-combo]");
    if (combo) {
      const c = SC_COMBOS.find(x => x.id === combo.dataset.combo);
      if (c) { SC_S.stage = Object.keys(c.set).slice(0, SC_CAP); SC_S.mv = { ...SC_S.mv, ...c.set }; pageScenarios(); }
      return;
    }
    if (e.target.closest("[data-reset]")) { SC_S.stage = []; pageScenarios(); return; }
    const colrm = e.target.closest("[data-colrm]");
    if (colrm) { SC_S.stage = SC_S.stage.filter(f => f !== colrm.dataset.colrm); pageScenarios(); return; }
  });
  root.addEventListener("input", e => {
    const dial = e.target.closest("[data-dial]");
    if (dial) { SC_S.mv[dial.dataset.dial] = +dial.value || 0; const n = root.querySelector(`[data-dial-n="${dial.dataset.dial}"]`); if (n) n.value = dial.value; }
  });
  root.addEventListener("change", e => {
    const dial = e.target.closest("[data-dial]");
    if (dial) { pageScenarios(); return; }
    const n = e.target.closest("[data-dial-n]");
    if (n) { SC_S.mv[n.dataset.dialN] = +n.value || 0; pageScenarios(); return; }
    if (e.target.closest("[data-search]")) { SC_S.q = e.target.value; pageScenarios(); }
  });
}
