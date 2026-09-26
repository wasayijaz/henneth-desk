/* ---- Screener: faceted filters over state/screener.json (583 tickers, 37 scored fields). ----
   Replaces the old plain-English pageScreener()/parseScreen()/saveScreen() (formerly app.js
   ~4853-4946, deleted in the same change — see "Screener: moved to dashboard/page-screener.js"
   marker left in app.js). The old design regex-parsed a free-text sentence into ad-hoc filters
   over a handful of quant/fairvalue fields assembled on the fly. This version reads the desk's
   own pre-built screener.json (scripts/build_screener.py, wired into run_cloud.py) and lets the
   reader pick real fields from six named families (move/risk/value/income/quality/context),
   each as a numeric range or a category checklist, combined with an explicit AND/OR toggle.

   Ported from docs/redesign-mockups/screener-mockup.html with a deliberately smaller surface —
   this repo's "simplest implementation that meets the requirement" rule. Dropped from the
   mockup: the SVG histogram + brush-drag range picker, the sector dot-cloud, sparkline detail
   panels, hover tooltips, and URL hash-sync. Kept: the family/variable metadata shape, the
   preset list, the operator vocabulary (at least / at most / is / is not), and the
   localStorage key for saved combinations (same key name the mockup used, so nothing to
   migrate). Conditions use plain number inputs and checkboxes instead of a drag interaction,
   and there is no separate event-delegation "wire" function — handlers are inline onclick/
   onchange calls back into the functions below, matching this file's own scrSetX naming and
   the codebase's existing convention (see page-strategies.js for the alternative delegated
   style; this page intentionally does not use it).

   No advice language: no "buy", "sell", "favored" — filters describe the data, never a
   recommendation. Missing values render as "—" in the table and "unknown" in prose, never 0. */

const FAMS = [
  ["move", "Move", "How the price has travelled."],
  ["risk", "Risk", "How bumpy, and how easy to trade."],
  ["value", "Value", "Price against earnings and the desk's model."],
  ["income", "Income", "Dividends paid and payout health."],
  ["quality", "Quality", "Business quality and the strategies that have worked on it."],
  ["context", "Context", "Sector, index membership, and recent news."],
];
const FAM = Object.fromEntries(FAMS.map(f => [f[0], { label: f[1], desc: f[2] }]));

/* Every field state/screener.json carries per ticker, except name/sector (name is shown
   directly; sector gets its own column and its own categorical filter). type "num" gets a
   min/max range condition; "cat" gets a checkbox-list condition. unit is appended after
   formatting; dec is decimal places; signed adds a "+" prefix via the global sgn() helper. */
const VARS = {
  chg_1w: { fam: "move", label: "1-week change", unit: "%", dec: 1, signed: true, desc: "Price change over the last 5 sessions." },
  chg_1m: { fam: "move", label: "1-month change", unit: "%", dec: 1, signed: true, desc: "Price change over the last ~21 sessions." },
  chg_3m: { fam: "move", label: "3-month change", unit: "%", dec: 1, signed: true, desc: "Price change over the last ~63 sessions." },
  chg_1y: { fam: "move", label: "1-year change", unit: "%", dec: 1, signed: true, desc: "Price change over the last ~252 sessions." },
  off_high: { fam: "move", label: "Off 52-week high", unit: "%", dec: 1, signed: true, desc: "Distance below the 52-week high (0 = at the high)." },
  off_low: { fam: "move", label: "Off 52-week low", unit: "%", dec: 1, signed: true, desc: "Distance above the 52-week low (0 = at the low)." },
  vs50: { fam: "move", label: "vs 50-day average", unit: "%", dec: 1, signed: true, desc: "Price versus its 50-session moving average." },
  vs200: { fam: "move", label: "vs 200-day average", unit: "%", dec: 1, signed: true, desc: "Price versus its 200-session moving average." },
  rsi: { fam: "move", label: "RSI (14)", unit: "", dec: 0, signed: false, desc: "14-session relative strength index, 0-100." },
  vol: { fam: "risk", label: "Volatility", unit: "%", dec: 1, signed: false, desc: "Recent realised daily volatility." },
  beta: { fam: "risk", label: "Beta", unit: "", dec: 2, signed: false, desc: "Sensitivity to the KSE-100's moves." },
  adtv: { fam: "risk", label: "Avg daily traded value", unit: " Rs m", dec: 1, signed: false, desc: "Average value traded per session, in Rs millions." },
  spread: { fam: "risk", label: "Bid/ask spread", unit: "%", dec: 2, signed: false, desc: "Typical quoted spread." },
  surge: { fam: "risk", label: "Volume surge", unit: "x", dec: 2, signed: false, desc: "Recent volume versus its own average." },
  liqb: { fam: "risk", label: "Liquidity band", type: "cat", opts: ["highly_liquid", "moderately_liquid", "illiquid"], desc: "The desk's own liquidity bucket." },
  price: { fam: "value", label: "Price", unit: " Rs", dec: 2, signed: false, desc: "Last close." },
  pe: { fam: "value", label: "P/E (trailing)", unit: "", dec: 1, signed: false, desc: "Price over trailing earnings." },
  fpe: { fam: "value", label: "P/E (forward)", unit: "", dec: 1, signed: false, desc: "Price over forward earnings." },
  gap: { fam: "value", label: "Gap to model value", unit: "%", dec: 1, signed: true, desc: "Distance between price and the desk's fair-value model (positive = below model value)." },
  verdict: { fam: "value", label: "Model verdict", type: "cat", opts: ["undervalued", "fair", "overvalued"], desc: "The fair-value model's read." },
  mcap: { fam: "value", label: "Market cap", unit: " Rs bn", dec: 1, signed: false, desc: "Market capitalisation, in Rs billions." },
  dy: { fam: "income", label: "Dividend yield", unit: "%", dec: 1, signed: false, desc: "Trailing dividend yield." },
  payout: { fam: "income", label: "Payout ratio", unit: "%", dec: 1, signed: false, desc: "Dividends paid as a share of earnings." },
  ndiv: { fam: "income", label: "Dividends paid", unit: "", dec: 0, signed: false, desc: "Number of dividend payouts on record." },
  bc: { fam: "income", label: "Book closure due", type: "cat", opts: ["yes", "no"], desc: "Whether a book closure is currently pending." },
  margin: { fam: "quality", label: "Net margin", unit: "%", dec: 1, signed: true, desc: "Net profit margin." },
  rating: { fam: "quality", label: "Desk rating", type: "cat", opts: ["attractive", "mixed", "caution"], desc: "The desk's own quality read." },
  pred: { fam: "quality", label: "Predictability score", unit: "", dec: 0, signed: false, desc: "How consistently this name's moves have followed its own history." },
  nprov: { fam: "quality", label: "Proven strategies", unit: "", dec: 0, signed: false, desc: "Number of backtested strategies with a live edge on this name." },
  besthit: { fam: "quality", label: "Best strategy hit rate", unit: "%", dec: 0, signed: false, desc: "Win rate of this name's best-performing backtested strategy." },
  bestnet: { fam: "quality", label: "Best strategy net return", unit: "%", dec: 1, signed: true, desc: "Net return of this name's best-performing backtested strategy." },
  sector: { fam: "context", label: "Sector", type: "cat", opts: null, desc: "PSX sector classification." },
  kse100: { fam: "context", label: "In the KSE-100", type: "cat", opts: ["yes", "no"], desc: "Index membership." },
  kmi: { fam: "context", label: "Shariah-compliant (KMI)", type: "cat", opts: ["yes", "no"], desc: "KMI-30 Shariah-compliance flag." },
  news30: { fam: "context", label: "News items (30d)", unit: "", dec: 0, signed: false, desc: "Tagged news items in the last 30 days." },
  impact: { fam: "context", label: "Highest news impact (30d)", unit: "", dec: 0, signed: false, desc: "Highest 1-5 impact score among recent news." },
  ins30: { fam: "context", label: "Insider filings (30d)", unit: "", dec: 0, signed: false, desc: "Insider/substantial-shareholder filings in the last 30 days." },
};

const PRESETS = [
  { title: "Near 52-week high, proven strategy", teaser: "Within 5% of the high, with at least one backtested strategy showing an edge.",
    conds: [{ field: "off_high", min: -5, max: null }, { field: "nprov", min: 1, max: null }] },
  { title: "Below model value, pays dividends", teaser: "At least 15% below the desk's model value, yielding 4% or more.",
    conds: [{ field: "gap", min: 15, max: null }, { field: "dy", min: 4, max: null }] },
  { title: "Low volatility, liquid", teaser: "Realised volatility at or below 5%, with healthy average daily value traded.",
    conds: [{ field: "vol", min: null, max: 5 }, { field: "adtv", min: 20, max: null }] },
  { title: "Low RSI inside the KSE-100", teaser: "RSI at or below 35, restricted to KSE-100 constituents.",
    conds: [{ field: "rsi", min: null, max: 35 }, { field: "kse100", vals: ["yes"] }] },
  { title: "Shariah-compliant, healthy margin", teaser: "KMI-30 names with a net margin of 10% or more and an attractive desk rating.",
    conds: [{ field: "kmi", vals: ["yes"] }, { field: "margin", min: 10, max: null }, { field: "rating", vals: ["attractive"] }] },
  { title: "In the news this month", teaser: "At least one news item in the last 30 days, with an impact score of 3 or higher.",
    conds: [{ field: "news30", min: 1, max: null }, { field: "impact", min: 3, max: null }] },
];

const SCR_LS = "henneth-screener-saved";
let SCR_DATA = null; // cached rows + metadata, built once per page load
let SCR_S = { conds: [], mode: "all", famOpen: "move", sort: "chg_1m", dir: -1, show: 40 };

function scrFmt(field, v) {
  if (v === null || v === undefined) return "—";
  const m = VARS[field];
  if (m.type === "cat") return String(v);
  const n = Number(v);
  if (!isFinite(n)) return "—";
  const s = n.toFixed(m.dec ?? 0);
  return (m.signed ? sgn(s) : s) + (m.unit || "");
}

async function scrLoad() {
  if (SCR_DATA) return SCR_DATA;
  const raw = await j("screener.json");
  const tickers = raw?.tickers || {};
  const rows = Object.entries(tickers).map(([s, v]) => ({ s, ...v }));
  const sectorOpts = [...new Set(rows.map(r => r.sector).filter(Boolean))].sort();
  VARS.sector.opts = sectorOpts;
  SCR_DATA = { rows, n: raw?.n ?? rows.length, asof: raw?.asof || raw?.updated || "" };
  return SCR_DATA;
}

function scrPass(row, c) {
  const m = VARS[c.field];
  const v = row[c.field];
  if (m.type === "cat") {
    if (!c.vals || !c.vals.length) return true;
    return v != null && c.vals.includes(v);
  }
  if (v == null) return false;
  if (c.min != null && v < c.min) return false;
  if (c.max != null && v > c.max) return false;
  return true;
}
function scrMatches(rows) {
  if (!SCR_S.conds.length) return rows;
  return rows.filter(r => (SCR_S.mode === "all" ? SCR_S.conds.every(c => scrPass(r, c)) : SCR_S.conds.some(c => scrPass(r, c))));
}
function scrCondLabel(c) {
  const m = VARS[c.field];
  if (m.type === "cat") return `${m.label}: ${(c.vals || []).map(esc).join(" or ") || "any"}`;
  if (c.min != null && c.max != null) return `${m.label}: between ${c.min} and ${c.max}${esc(m.unit || "")}`;
  if (c.min != null) return `${m.label}: at least ${c.min}${esc(m.unit || "")}`;
  if (c.max != null) return `${m.label}: at most ${c.max}${esc(m.unit || "")}`;
  return m.label;
}

function scrAddVar(field) {
  if (SCR_S.conds.some(c => c.field === field)) return;
  const m = VARS[field];
  SCR_S.conds.push(m.type === "cat" ? { field, vals: [] } : { field, min: null, max: null });
  pageScreener();
}
function scrRemoveCond(field) {
  SCR_S.conds = SCR_S.conds.filter(c => c.field !== field);
  pageScreener();
}
function scrSetNum(field, which, raw) {
  const c = SCR_S.conds.find(x => x.field === field);
  if (!c) return;
  c[which] = raw === "" ? null : Number(raw);
  pageScreener();
}
function scrToggleCat(field, val) {
  const c = SCR_S.conds.find(x => x.field === field);
  if (!c) return;
  c.vals = c.vals.includes(val) ? c.vals.filter(v => v !== val) : [...c.vals, val];
  pageScreener();
}
function scrSetMode(mode) { SCR_S.mode = mode; pageScreener(); }
function scrSetFam(fam) { SCR_S.famOpen = fam; pageScreener(); }
function scrApplyPreset(i) {
  const p = PRESETS[i];
  SCR_S.conds = p.conds.map(c => ({ ...c, vals: c.vals ? [...c.vals] : undefined }));
  SCR_S.mode = "all";
  SCR_S.show = 40;
  pageScreener();
}
function scrClear() { SCR_S.conds = []; SCR_S.show = 40; pageScreener(); }
function scrSort(field) {
  if (SCR_S.sort === field) SCR_S.dir = -SCR_S.dir;
  else { SCR_S.sort = field; SCR_S.dir = -1; }
  pageScreener();
}
function scrShowMore(all) { SCR_S.show = all ? 1e9 : SCR_S.show + 40; pageScreener(); }

function scrSavedList() {
  try { return JSON.parse(localStorage.getItem(SCR_LS) || "[]"); } catch { return []; }
}
function scrSaveCombo() {
  if (!SCR_S.conds.length) return;
  const name = prompt("Name this combination:", "");
  if (!name) return;
  const list = [...scrSavedList(), { name, mode: SCR_S.mode, conds: SCR_S.conds }].slice(-12);
  try { localStorage.setItem(SCR_LS, JSON.stringify(list)); } catch {}
  pageScreener();
}
function scrLoadCombo(i) {
  const c = scrSavedList()[i];
  if (!c) return;
  SCR_S.conds = c.conds;
  SCR_S.mode = c.mode || "all";
  SCR_S.show = 40;
  pageScreener();
}
function scrRemoveCombo(i) {
  const list = scrSavedList();
  list.splice(i, 1);
  try { localStorage.setItem(SCR_LS, JSON.stringify(list)); } catch {}
  pageScreener();
}

function scrPool() {
  return `<div class="wl-chips" role="tablist" aria-label="Variable family">
    ${FAMS.map(([id, label]) => `<button role="tab" aria-selected="${SCR_S.famOpen === id}" onclick="scrSetFam('${id}')">${esc(label)}</button>`).join("")}
  </div>
  <p class="sub" style="margin:8px 0">${esc(FAM[SCR_S.famOpen].desc)}</p>
  <div class="sc-pool">${Object.entries(VARS).filter(([, m]) => m.fam === SCR_S.famOpen).map(([field, m]) => {
    const active = SCR_S.conds.some(c => c.field === field);
    return `<button class="sc-chip${active ? " active" : ""}" title="${esc(m.desc)}" onclick="${active ? `scrRemoveCond('${field}')` : `scrAddVar('${field}')`}">${active ? "✓ " : "+ "}${esc(m.label)}</button>`;
  }).join("")}</div>`;
}

function scrCondRow(c) {
  const m = VARS[c.field];
  const body = m.type === "cat"
    ? `<div class="sc-cats">${(m.opts || []).map(opt => `<label class="sc-cat"><input type="checkbox" ${c.vals.includes(opt) ? "checked" : ""} onchange="scrToggleCat('${c.field}','${esc(opt)}')"> ${esc(opt)}</label>`).join("")}</div>`
    : `<div class="sc-range"><label>at least <input type="number" step="any" value="${c.min ?? ""}" onchange="scrSetNum('${c.field}','min',this.value)"></label>
       <label>at most <input type="number" step="any" value="${c.max ?? ""}" onchange="scrSetNum('${c.field}','max',this.value)"></label>
       <span class="sub">${esc(m.unit || "")}</span></div>`;
  return `<div class="sc-cond">
    <div class="sc-cond-head"><b>${esc(m.label)}</b><button class="sc-x" title="Remove" onclick="scrRemoveCond('${c.field}')">×</button></div>
    ${body}</div>`;
}

function scrRow(r) {
  return `<tr class="clickable" onclick="navigate('/ticker/${esc(r.s)}')">
    <td><b>${esc(r.s)}</b> <span class="sub">${esc((r.name || "").slice(0, 22))}</span></td>
    <td class="sub">${esc((r.sector || "—").slice(0, 18))}</td>
    <td class="r num">${scrFmt("price", r.price)}</td>
    <td class="r num ${r.chg_1m > 0 ? "up" : r.chg_1m < 0 ? "dn" : ""}">${scrFmt("chg_1m", r.chg_1m)}</td>
    <td class="r num">${scrFmt("rsi", r.rsi)}</td>
    <td class="r num">${scrFmt("dy", r.dy)}</td>
    <td class="r num ${r.gap > 0 ? "up" : r.gap < 0 ? "dn" : ""}">${scrFmt("gap", r.gap)}</td>
    <td class="r num">${scrFmt("pred", r.pred)}</td>
    <td class="r">${esc(r.rating ?? "—")}</td>
  </tr>`;
}

async function pageScreener() {
  const locked = !hasFeature("screener");
  const { rows, n, asof } = await scrLoad();
  const matched = scrMatches(rows);
  const sortField = SCR_S.sort;
  const sorted = [...matched].sort((a, b) => {
    const av = a[sortField], bv = b[sortField];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    const isNum = VARS[sortField]?.type !== "cat";
    const cmp = isNum ? av - bv : String(av).localeCompare(String(bv));
    return cmp * SCR_S.dir;
  });
  const visible = sorted.slice(0, SCR_S.show);
  const saved = scrSavedList();
  const sortArrow = f => (SCR_S.sort === f ? (SCR_S.dir === -1 ? " ▼" : " ▲") : "");

  $("view").innerHTML = `<div class="today-page sc-page">
  <div class="seg" style="margin-top:4px"><h2>Screener</h2><div class="ln"></div><span class="pill">${n} names</span></div>
  <p class="sub" style="margin-bottom:12px">Filter the desk's full universe on any of 37 scored fields, grouped into six families. A screen is a reading list, not a portfolio — every match still deserves the checklist on its own page.${asof ? ` As of ${esc(asof)}.` : ""}</p>
  ${locked ? planWall("The faceted screener",
    `Filter all ${n} names on move, risk, value, income, quality and news fields — the desk's own scored data, not a plain-text guess.`) : `
  <div class="sumstrip">
    <div class="sumtile"><b>${n}</b><span>tickers covered</span></div>
    <div class="sumtile"><b>${matched.length}</b><span>match${matched.length === 1 ? "" : "es"}</span></div>
    <div class="sumtile"><b>${SCR_S.conds.length}</b><span>active filter${SCR_S.conds.length === 1 ? "" : "s"}</span></div>
    <div class="sumtile"><b>6</b><span>variable families</span></div>
  </div>
  <div class="card">
    <div class="sc-presets-head"><b>Starting points</b><span class="sub">a preset replaces the current filters</span></div>
    <div class="sc-presets">${PRESETS.map((p, i) => `<button class="sc-preset" title="${esc(p.teaser)}" onclick="scrApplyPreset(${i})">${esc(p.title)}</button>`).join("")}</div>
  </div>
  <div class="card">
    <div class="sc-pool-head"><b>Add a filter</b></div>
    ${scrPool()}
  </div>
  ${SCR_S.conds.length ? `<div class="card">
    <div class="sc-cond-stack-head">
      <b>Active filters</b>
      <div class="wl-chips" role="group" aria-label="Combine filters">
        <button aria-pressed="${SCR_S.mode === "all"}" onclick="scrSetMode('all')">Match ALL</button>
        <button aria-pressed="${SCR_S.mode === "any"}" onclick="scrSetMode('any')">Match ANY</button>
      </div>
      <button class="note-save" onclick="scrClear()">Clear</button>
      ${me ? `<button class="note-save" onclick="scrSaveCombo()">Save combination</button>` : ""}
    </div>
    <div class="sc-cond-stack">${SCR_S.conds.map(scrCondRow).join("")}</div>
    <div class="sc-chips">${SCR_S.conds.map(c => `<span class="scr-chip">${scrCondLabel(c)}</span>`).join("")}</div>
  </div>` : ""}
  ${saved.length ? `<div class="card">
    <div class="sc-pool-head"><b>Saved combinations</b></div>
    <div class="sc-samples">${saved.map((s, i) => `<span class="scr-sample saved" style="display:inline-flex;align-items:center;gap:6px">
      <button class="scr-sample" style="border:none;padding:0" onclick="scrLoadCombo(${i})">★ ${esc(s.name)}</button>
      <button class="sc-x" title="Remove" onclick="scrRemoveCombo(${i})">×</button></span>`).join("")}</div>
  </div>` : ""}
  <div class="seg"><h2>${matched.length} match${matched.length === 1 ? "" : "es"}</h2><div class="ln"></div>${matched.length ? csvBtn("screen") : ""}</div>
  <div class="card" style="padding:0">${visible.length ? `<table><thead><tr>
    <th onclick="scrSort('s')" style="cursor:pointer">Stock${sortArrow("s")}</th>
    <th onclick="scrSort('sector')" style="cursor:pointer">Sector${sortArrow("sector")}</th>
    <th class="r" onclick="scrSort('price')" style="cursor:pointer">Price${sortArrow("price")}</th>
    <th class="r" onclick="scrSort('chg_1m')" style="cursor:pointer">1M chg${sortArrow("chg_1m")}</th>
    <th class="r" onclick="scrSort('rsi')" style="cursor:pointer">RSI${sortArrow("rsi")}</th>
    <th class="r" onclick="scrSort('dy')" style="cursor:pointer">Yield${sortArrow("dy")}</th>
    <th class="r" onclick="scrSort('gap')" style="cursor:pointer">vs fair${sortArrow("gap")}</th>
    <th class="r" onclick="scrSort('pred')" style="cursor:pointer">Predict.${sortArrow("pred")}</th>
    <th onclick="scrSort('rating')" style="cursor:pointer">Rating${sortArrow("rating")}</th>
  </tr></thead><tbody>${visible.map(scrRow).join("")}</tbody></table>`
    : '<div class="empty">Nothing clears every condition — loosen one and try again. An empty screen is information too.</div>'}</div>
  ${matched.length > visible.length ? `<div class="sc-more"><button class="note-save" onclick="scrShowMore(false)">Show 40 more</button>
    <button class="note-save" onclick="scrShowMore(true)">Show all ${matched.length}</button></div>` : ""}
  <details class="sc-glossary"><summary>Glossary — every field on this screen</summary>
    ${FAMS.map(([fid, flabel, fdesc]) => `<div class="sc-gloss-fam"><b>${esc(flabel)}</b> — ${esc(fdesc)}
      <ul>${Object.entries(VARS).filter(([, m]) => m.fam === fid).map(([, m]) => `<li><b>${esc(m.label)}</b> — ${esc(m.desc)}</li>`).join("")}</ul></div>`).join("")}
  </details>`}
  </div>`;
}
