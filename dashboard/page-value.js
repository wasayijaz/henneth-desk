// value page — redesign 2026-09
// Model fair value: four chapters (at a glance · gap map · one name, four models · by sector).
// Every number is read from state/fairvalue.json. Verdict thresholds (±15%) and the model maths
// live ONLY in scripts/compute_fairvalue.py; this file only counts, sorts and takes medians of the
// rows it displays (presentation). The 40% "models agree" line is a display rule of this page.

const VX_METHODS = { relative_pe: "Peer P/E", earnings_power: "Earnings power", graham: "Graham (revised)", ddm: "Dividend discount" };
const VX_VERD = { undervalued: "below fair", fair: "near fair", overvalued: "above fair" };
const VX_VCLS = { undervalued: "up", fair: "mut", overvalued: "dn" };
const VX_LO = -100, VX_HI = 200; // gap-map axis; names past +200% are drawn clipped with a caret
// view state survives the router's silent re-renders (polls, auth events)
const VX_S = { filt: "all", sec: "", focus: null, tSort: "x", tDir: -1, secSort: "gap", secAll: false, open: {} };

const vxPct = (v, d = 1) => v == null || !isFinite(v) ? "unknown" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d) + "%";
const vxRs = v => v == null || !isFinite(v) ? "unknown" : "Rs " + v.toLocaleString("en-US", { minimumFractionDigits: v < 100 ? 2 : 0, maximumFractionDigits: v < 100 ? 2 : 0 });
const vxCls = v => v > 0 ? "up" : v < 0 ? "dn" : "mut";
const vxMedian = a => { const s = a.filter(v => v != null && isFinite(v)).sort((x, y) => x - y), m = s.length >> 1; return s.length ? (s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2) : null; };
const vxSec = s => (s || "unknown").replace(/ Companies$/, "").replace("Inv. Banks / Inv. Cos. / Securities Cos.", "Investment cos.").replace("Power Generation & Distribution", "Power").replace("Technology & Communication", "Technology").replace("Food & Personal Care Products", "Food & personal care").replace("Automobile Parts & Accessories", "Auto parts").replace("Automobile Assembler", "Auto assemblers").replace("Real Estate Investment Trust", "REITs").replace("Paper, Board & Packaging", "Paper & packaging").replace("Oil & Gas Exploration", "Oil & gas E&P").replace("Oil & Gas Marketing", "Oil marketing").replace("Sugar & Allied Industries", "Sugar");
function vxTicks(a, b, n) {
  const raw = (b - a) / n; if (!(raw > 0)) return [];
  const mag = 10 ** Math.floor(Math.log10(raw)), st = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
  const out = []; for (let t = Math.ceil(a / st) * st; t <= b; t += st) out.push(+t.toFixed(6)); return out;
}

async function pageValue() {
  const [fv, uni] = await Promise.all([j("fairvalue.json"), j("universe.json")]);
  const view = $("view");
  const tickers = fv?.tickers || {};
  if (!Object.keys(tickers).length) {
    view.innerHTML = `<div class="today-page vx-page"><div class="today-date">Value <span>· model fair value</span></div>
      <div class="vx-card vx-empty"><p class="vx-lede">The fair-value file is unavailable right now, so no model values are shown. Nothing is estimated in its place.</p></div></div>`;
    return;
  }
  const I = fv.inputs || {}, SPE = I.sector_median_pe || {}, MINP = I.min_peers_for_sector_median;
  const ROWS = Object.entries(tickers).map(([sym, t]) => {
    const m = Object.fromEntries(Object.entries(t.methods || {}).filter(([, v]) => v != null && isFinite(v)));
    const vals = Object.values(m), c = t.composite_fair, bb = t.relative_pe_basis || {};
    const lo = vals.length ? Math.min(...vals) : null, hi = vals.length ? Math.max(...vals) : null;
    return {
      sym, n: uni?.symbols?.[sym]?.name || null, p: t.price, e: t.eps, eb: t.eps_basis, pe: t.pe, g: t.growth_est_pct,
      m, b: bb.basis, bn: bb.n_peers, bpe: bb.median_pe, s: t.sector || "unknown", c, x: t.mispricing_pct, v: t.verdict,
      nm: vals.length, lo, hi, spread: c > 0 && vals.length ? (hi - lo) / c * 100 : null,
    };
  }).filter(r => r.x != null && isFinite(r.x)).sort((a, b) => b.x - a.x);
  const BY = Object.fromEntries(ROWS.map(r => [r.sym, r]));
  const SECTORS = [...new Set(ROWS.map(r => r.s))].sort();
  const under = ROWS.filter(r => r.v === "undervalued"), over = ROWS.filter(r => r.v === "overvalued").reverse();
  const paid = isSubscribed();
  // free visitors see the three widest below-fair names only (old page gating)
  const PICK = paid ? ROWS : under.slice(0, 3);
  const S = VX_S;
  if (!S.focus || !PICK.some(r => r.sym === S.focus)) S.focus = (PICK.find(r => r.sym === "FFC") || PICK[0] || ROWS[0]).sym;
  if (S.sec && !SECTORS.includes(S.sec)) S.sec = "";
  const asofTxt = fv.updated ? String(fv.updated) : "unknown";
  const passes = r => (S.filt === "all" || r.v === S.filt) && (!S.sec || r.s === S.sec);
  const num = (v, suf = "") => v == null || !isFinite(v) ? "unknown" : v + suf;

  view.innerHTML = `<div class="today-page vx-page"></div>`;
  const root = view.firstElementChild;

  /* ---------- 01 · at a glance ---------- */
  function hero() {
    const n = ROWS.length, c = { undervalued: 0, fair: 0, overvalued: 0 };
    ROWS.forEach(r => { if (r.v in c) c[r.v]++; });
    const med = vxMedian(ROWS.map(r => r.x)), peerSecs = SECTORS.filter(s => s in SPE).length;
    const seg = k => `<i style="width:${c[k] / n * 100}%;background:${k === "fair" ? "var(--ink3)" : `var(--${VX_VCLS[k]})`}" data-tip="${c[k]} of ${n} names: price ${VX_VERD[k]}"></i>`;
    const inp = (tip, lab, val, em) => `<div data-tip="${esc(tip)}"><small>${lab}</small><b>${val}</b><em>${em}</em></div>`;
    return `<div class="today-hero">
      <div class="today-stance vx-panel">
        <p class="today-kicker">MEDIAN GAP <span>· model value vs price, all ${n} names</span></p>
        <h1 class="vx-big ${vxCls(med)}">${vxPct(med)}</h1>
        <p class="vx-lede">${med == null ? "The middle gap is unknown." : `For the typical name, the models' middle estimate sits ${Math.abs(med).toFixed(1)}% ${med < 0 ? "below" : "above"} today's price.`} That is a model's estimate with a range, not a price target.</p>
        <div class="vx-split">${seg("undervalued")}${seg("fair")}${seg("overvalued")}</div>
        <div class="vx-splitkey"><span><b class="up">${c.undervalued}</b> price below fair</span><span><b>${c.fair}</b> near fair</span><span><b class="dn">${c.overvalued}</b> above fair</span></div>
      </div>
      <div class="today-index vx-panel">
        <p class="today-kicker">WHAT FEEDS THE MODELS <span>· same for every name</span></p>
        <div class="vx-inputs">
          ${inp("The yield the earnings-power and Graham models use as the hurdle a stock has to beat.", "BOND YIELD", num(I.bond_yield_pct, "%"), "the safe-return hurdle")}
          ${inp(`Middle P/E of every name in the file. Used for peer P/E when a sector has fewer than ${num(MINP)} usable peers.`, "MARKET P/E", num(I.market_median_pe, "×"), "middle of all names")}
          ${inp("The return the dividend-discount model asks for. Only used for names that pay a dividend.", "REQUIRED RETURN", num(I.required_return_pct, "%"), "dividend model only")}
          ${inp(`Sectors with ${num(MINP)}+ names that have a usable P/E get their own peer P/E; the rest fall back to the market P/E.`, "PEER GROUPS", `${peerSecs} of ${SECTORS.length}`, `sectors with ${num(MINP)}+ peers`)}
        </div>
        <p class="vx-cap">Model run ${esc(asofTxt)} PKT · from public fundamentals · no discounted-cash-flow model is run.</p>
      </div>
    </div>`;
  }

  /* ---------- 02 · gap map ---------- */
  function gapChart(W) {
    const mob = W < 520, H = mob ? 190 : 240, L = 34, R = 6, T = 10, B = 22, iw = W - L - R, ih = H - T - B;
    const y = v => T + (VX_HI - Math.max(VX_LO, Math.min(VX_HI, v))) / (VX_HI - VX_LO) * ih, bw = iw / ROWS.length, y0 = y(0);
    let g = `<rect class="band" x="${L}" y="${y(15)}" width="${iw}" height="${y(-15) - y(15)}"/>`;
    [-100, -50, 50, 100, 150, 200].forEach(t => g += `<line class="ax" x1="${L}" x2="${W - R}" y1="${y(t)}" y2="${y(t)}"/><text x="${L - 5}" y="${y(t) + 3}" text-anchor="end">${t > 0 ? "+" : "−"}${Math.abs(t)}%</text>`);
    g += `<text x="${L - 5}" y="${y0 + 3}" text-anchor="end" class="ink2">0</text>`;
    ROWS.forEach((r, i) => {
      const x = L + i * bw, yv = y(r.x), c = r.v === "undervalued" ? "b-up" : r.v === "overvalued" ? "b-dn" : "b-mid";
      g += `<rect class="${c}${passes(r) ? "" : " dim"}" x="${x + (bw > 3 ? .5 : 0)}" y="${Math.min(yv, y0)}" width="${Math.max(bw - (bw > 3 ? 1 : 0), .8)}" height="${Math.max(Math.abs(yv - y0), 1)}"/>`;
      if (r.x > VX_HI) g += `<path class="${c}" d="M${x + bw / 2 - 3} ${T - 1}l3 -5l3 5z"/>`;
    });
    const fi = ROWS.findIndex(r => r.sym === S.focus);
    if (fi >= 0) {
      const fr = ROWS[fi], fx = L + (fi + .5) * bw, left = fi < ROWS.length * .7;
      g += `<line class="focus" x1="${fx}" x2="${fx}" y1="${T}" y2="${H - B + 4}"/><text class="lbl" x="${fx + (left ? 4 : -4)}" y="${H - 6}" text-anchor="${left ? "start" : "end"}">${esc(fr.sym)} ${vxPct(fr.x)}</text>`;
    }
    g += `<line class="zero" x1="${L}" x2="${W - R}" y1="${y0}" y2="${y0}"/>`;
    return `<svg class="vx-svg vx-gapsvg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" data-l="${L}" data-bw="${bw}" role="img" aria-label="Gap between model value and price for ${ROWS.length} names, sorted">${g}</svg>`;
  }
  const endRow = r => `<button class="vx-row" type="button" data-sym="${esc(r.sym)}" aria-current="${r.sym === S.focus}"><span class="nm"><b>${esc(r.sym)}</b><small>${esc(r.n || vxSec(r.s))}</small></span><span class="${VX_VCLS[r.v] || "mut"}">${vxPct(r.x)}</span></button>`;

  function gapMap() {
    const vis = ROWS.filter(passes), pos = vis.filter(r => r.x > 0), neg = vis.filter(r => r.x < 0);
    const chip = (k, l) => `<button type="button" data-filt="${k}" aria-pressed="${S.filt === k}">${l}</button>`;
    return `<div class="vx-card">
        <div class="vx-ctrl">
          <div class="wl-chips">${chip("all", "All")}${chip("undervalued", "Below fair")}${chip("fair", "Near fair")}${chip("overvalued", "Above fair")}</div>
          <select class="vx-sel" data-ctl="sec" aria-label="Filter by sector"><option value="">Every sector</option>${SECTORS.map(s => `<option value="${esc(s)}"${S.sec === s ? " selected" : ""}>${esc(vxSec(s))}</option>`).join("")}</select>
        </div>
        <div class="vx-chart" data-chart="gap"></div>
        <div class="vx-legend"><span><i style="background:var(--up)"></i>price below fair</span><span><i style="background:var(--ink3)"></i>within ±15%</span><span><i style="background:var(--dn)"></i>price above fair</span><span><i class="bd"></i>near-fair band</span></div>
        <p class="vx-cap">Each bar is one name: how far the models' middle value sits from price. Tap a bar to open it below. Colour marks the gap, not a signal.</p>
      </div>
      <div class="vx-ends">
        <div class="vx-card"><h3>WIDEST BELOW FAIR <span>· ${pos.length} shown</span></h3>${pos.slice(0, 5).map(endRow).join("") || '<p class="vx-cap">None in this filter.</p>'}</div>
        <div class="vx-card"><h3>WIDEST ABOVE FAIR <span>· ${neg.length} shown</span></h3>${neg.slice(-5).reverse().map(endRow).join("") || '<p class="vx-cap">None in this filter.</p>'}</div>
      </div>
      <details class="vx-more" data-k="tbl"${S.open.tbl ? " open" : ""}><summary>Every name in this filter (${vis.length}) · sortable</summary>${vis.length ? table(vis) : '<p class="vx-cap">None in this filter.</p>'}</details>`;
  }

  function table(vis) {
    const k = S.tSort, str = k === "sym" || k === "s";
    const val = r => str ? String(r[k] ?? "") : (r[k] ?? -Infinity);
    const rows = [...vis].sort((a, b) => (str ? val(a).localeCompare(val(b)) : val(a) - val(b)) * S.tDir);
    const th = (key, l) => `<th data-sort="${key}">${l}${S.tSort === key ? (S.tDir > 0 ? " ↑" : " ↓") : ""}</th>`;
    return `<div class="today-table-wrap vx-tbl"><table class="today-table"><thead><tr>${th("sym", "Name")}${th("s", "Sector")}${th("p", "Price")}${th("c", "Model value")}${th("x", "Gap")}${th("nm", "Models")}</tr></thead><tbody>
      ${rows.map(r => `<tr class="clickable" data-sym="${esc(r.sym)}" aria-current="${r.sym === S.focus}"><td><b>${esc(r.sym)}</b></td><td>${esc(vxSec(r.s))}</td><td>${vxRs(r.p)}</td><td>${vxRs(r.c)}</td><td class="${VX_VCLS[r.v] || "mut"}">${vxPct(r.x)}</td><td>${r.nm}/4</td></tr>`).join("")}
    </tbody></table></div>`;
  }

  /* ---------- 03 · one name, the models ---------- */
  function field(W) {
    const r = BY[S.focus], mob = W < 460, LW = mob ? 86 : 124, R = 10, T = 26, RH = mob ? 34 : 38, keys = Object.keys(VX_METHODS);
    const H = T + RH * (keys.length + 1) + 22, pts = [...Object.values(r.m), r.p, r.c].filter(v => v != null && isFinite(v));
    if (!pts.length) return '<p class="vx-cap">No model values for this name.</p>';
    const lo = Math.min(...pts), hi = Math.max(...pts), pad = (hi - lo) * .12 || hi * .1 || 1, a = Math.max(0, lo - pad), b = hi + pad;
    const x = v => LW + (v - a) / (b - a) * (W - LW - R), hasP = r.p != null && isFinite(r.p), px = hasP ? x(r.p) : null;
    let g = r.lo != null ? `<rect class="band" x="${x(r.lo)}" y="${T - 4}" width="${Math.max(x(r.hi) - x(r.lo), 1)}" height="${RH * keys.length + 4}"/>` : "";
    vxTicks(a, b, mob ? 4 : 6).forEach(t => g += `<line class="ax" x1="${x(t)}" x2="${x(t)}" y1="${T - 4}" y2="${H - 20}"/><text x="${x(t)}" y="${H - 6}" text-anchor="middle">${t.toLocaleString("en-US")}</text>`);
    keys.forEach((k, i) => {
      const cy = T + RH * i + RH / 2 - 2, v = r.m[k], lab = mob ? VX_METHODS[k].replace(" (revised)", "").replace("Dividend discount", "Dividend") : VX_METHODS[k];
      g += `<text class="lbl" x="0" y="${cy + 3}">${lab}</text>`;
      if (v == null) { g += `<text x="${LW}" y="${cy + 3}">${k === "ddm" ? (mob ? "not used · no dividend data" : "not used · no dividend yield in the data") : "not used · inputs missing"}</text>`; return; }
      const vx = x(v), d = hasP ? (v / r.p - 1) * 100 : null, right = vx < W - 90, c = d == null ? "b-mid" : d >= 0 ? "b-up" : "b-dn";
      if (hasP) g += `<line class="conn" x1="${px}" x2="${vx}" y1="${cy}" y2="${cy}"/>`;
      g += `<rect class="mk ${c}" x="${vx - 5}" y="${cy - 5}" width="10" height="10" data-tip="${esc(VX_METHODS[k])}: ${vxRs(v)} · ${vxPct(d)} vs price"/>`;
      g += `<text class="${d == null ? "" : d >= 0 ? "up" : "dn"}" x="${vx + (right ? 9 : -9)}" y="${cy + 3}" text-anchor="${right ? "start" : "end"}">${vxRs(v)} ${vxPct(d, 0)}</text>`;
    });
    const my = T + RH * keys.length + RH / 2 - 2;
    g += `<text class="lbl" x="0" y="${my + 3}" style="font-weight:700">${mob ? "Median" : "Median of models"}</text>`;
    if (r.c != null && isFinite(r.c)) {
      const mx = x(r.c), mr = mx < W - 110;
      g += `<line class="med" x1="${mx}" x2="${mx}" y1="${my - 8}" y2="${my + 8}"/><text class="lbl" x="${mx + (mr ? 7 : -7)}" y="${my + 3}" text-anchor="${mr ? "start" : "end"}">${vxRs(r.c)} ${vxPct(r.x)}</text>`;
    } else g += `<text x="${LW}" y="${my + 3}">unknown</text>`;
    if (hasP) g += `<line class="price" x1="${px}" x2="${px}" y1="${T - 12}" y2="${H - 20}"/><text class="lbl" x="${px}" y="${T - 15}" text-anchor="${px > W - 80 ? "end" : px < LW + 40 ? "start" : "middle"}">price ${vxRs(r.p)}</text>`;
    return `<svg class="vx-svg vx-ffsvg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(r.sym)}: model values against price">${g}</svg>`;
  }

  function confidence(r) {
    const peer = r.b === "sector", close = r.spread != null && r.spread <= 40, all4 = r.nm === 4, epsKnown = !!r.eb && r.eb !== "unknown";
    const firm = [all4, close, peer, epsKnown].filter(Boolean).length;
    const chk = (ok, t, v, why, extra = "") => `<div class="vx-chk"><p><b>${t}</b><i class="${ok ? "up" : "dn"}">${v}</i></p>${extra}<em>${why}</em></div>`;
    const missing = Object.keys(VX_METHODS).filter(k => r.m[k] == null).map(k => VX_METHODS[k]);
    return `<div class="vx-card">
      <h3>HOW FIRM IS THIS ESTIMATE <span>· ${firm} of 4 checks hold</span></h3>
      <div class="vx-score">${[0, 1, 2, 3].map(i => `<i class="${i < firm ? "on" : ""}"></i>`).join("")}</div>
      ${chk(all4, "Models used", r.nm + " of 4", all4 ? "Every model had the inputs it needs." : `Not run: ${esc(missing.join(", "))}${missing.includes("Dividend discount") ? " (no dividend yield in the data)" : ""}.`)}
      ${chk(close, "Models agree", r.spread == null ? "unknown" : close ? "close" : "split", r.spread == null ? "The spread between models is unknown." : `Lowest to highest spans ${vxRs(r.lo)}–${vxRs(r.hi)}, ${r.spread.toFixed(0)}% of the middle value. Under 40% reads as close (a display rule of this page).`, r.spread == null ? "" : `<div class="vx-meter"><i style="width:${Math.min(r.spread, 150) / 150 * 100}%"></i><s style="left:${40 / 150 * 100}%"></s></div>`)}
      ${chk(peer, "Peer group", peer ? num(r.bn) + " peers" : "market used", peer ? `Compared with ${num(r.bn)} names in ${esc(vxSec(r.s))} (middle P/E ${num(r.bpe, "×")}).` : `Fewer than ${num(MINP)} usable peers in ${esc(vxSec(r.s))}, so the market P/E of ${num(r.bpe, "×")} stands in.`)}
      ${chk(epsKnown, "Earnings figure", epsKnown ? esc(r.eb) : "basis unknown", "The data does not say whether EPS is trailing twelve months or annualised, so every model inherits that doubt.")}
    </div>`;
  }

  function focusPanel() {
    const r = BY[S.focus];
    return `<div class="vx-focus">
      <div class="vx-card">
        <div class="vx-id"><div><b>${esc(r.sym)}</b><p>${esc(r.n || "name unknown")} · ${esc(vxSec(r.s))}</p></div>
          <div class="gap"><b class="${VX_VCLS[r.v] || "mut"}">${vxPct(r.x)}</b>middle value vs price · ${VX_VERD[r.v] || "unknown"}</div></div>
        <div class="vx-chart" data-chart="ff"></div>
        <div class="vx-legend"><span><i class="ln"></i>price</span><span><i class="md"></i>median of models</span><span><i class="bd"></i>range the models span</span></div>
        <div class="vx-facts">
          <span data-tip="Earnings per share the models start from. Basis: ${esc(r.eb || "unknown")}."><small>EPS</small>${r.e == null ? "unknown" : "Rs " + r.e}</span>
          <span data-tip="Price ÷ EPS today."><small>P/E NOW</small>${num(r.pe, "×")}</span>
          <span data-tip="Read from forward vs trailing P/E, kept between 0% and 30%. Defaults to 5% when there is no forward figure."><small>GROWTH EST</small>${num(r.g, "%")}</span>
          <span data-tip="${r.b === "sector" ? "Middle P/E of the sector peers." : "Market P/E, used because the sector is thin."}"><small>${r.b === "sector" ? "PEER P/E" : "MARKET P/E"}</small>${num(r.bpe, "×")}</span>
        </div>
        <p class="vx-cap"><a href="/ticker/${esc(r.sym)}">${esc(r.sym)} full page →</a></p>
      </div>
      <div class="vx-conf">${confidence(r)}</div>
    </div>
    <details class="vx-more" data-k="how"${S.open.how ? " open" : ""}><summary>What each model means, in plain words</summary>
      <div class="vx-how">
        <div><b>Peer P/E</b><p>What the stock would be worth if the market paid the same price-for-earnings as for its sector peers.</p><code>sector middle P/E × EPS</code></div>
        <div><b>Earnings power</b><p>Values earnings against the bond yield: the higher safe returns are, the less each rupee of profit is worth.</p><code>100 ÷ (${num(I.bond_yield_pct)} + 4) × EPS</code></div>
        <div><b>Graham (revised)</b><p>Benjamin Graham's rule of thumb: a base multiple, lifted by expected growth, scaled by the bond yield.</p><code>EPS × (8.5 + 2 × growth) × 4.4 ÷ ${num(I.bond_yield_pct)}</code></div>
        <div><b>Dividend discount</b><p>Today's value of the dividend stream, growing slowly, at a ${num(I.required_return_pct, "%")} required return. Payers only.</p><code>next dividend ÷ (${num(I.required_return_pct, "%")} − growth)</code></div>
        <div><b>Discounted cash flow</b><p>Not run. The desk's model has no cash-flow forecast, so this view is unknown for every name.</p><code>unknown</code></div>
      </div>
      <p class="vx-cap">Model value = the middle of the models that ran. Rough models on limited public data; the spread between them is part of the answer.</p>
    </details>`;
  }

  /* ---------- 04 · sectors ---------- */
  function sectors() {
    const list = SECTORS.map(s => { const rr = ROWS.filter(r => r.s === s); return { s, n: rr.length, med: vxMedian(rr.map(r => r.x)), pe: SPE[s] ?? null }; });
    const sortBy = { gap: (a, b) => b.med - a.med, size: (a, b) => b.n - a.n || b.med - a.med, name: (a, b) => vxSec(a.s).localeCompare(vxSec(b.s)) }[S.secSort];
    list.sort(sortBy);
    const all = list.length, shown = S.secAll ? list : list.slice(0, 12);
    const bar = v => { const c = Math.max(-100, Math.min(100, v)), w = Math.abs(c) / 2; return `<span class="vx-div"><span class="bnd"></span><i style="left:${c >= 0 ? 50 : 50 - w}%;width:${w}%;background:var(--${v > 15 ? "up" : v < -15 ? "dn" : "ink3"})"></i></span>`; };
    return `<div class="vx-card vx-secwrap">
      <div class="vx-sechd"><span>Sector</span><span>Middle gap (±100% shown)</span><span class="r">Gap</span><span class="r">Names</span><span class="r">Peer P/E</span></div>
      ${shown.map(x => `<button type="button" class="vx-sec${x.n < MINP ? " thin" : ""}" data-sec="${esc(x.s)}" data-tip="${esc(vxSec(x.s))}: ${x.n} names, middle gap ${vxPct(x.med)}. ${x.pe == null ? `Fewer than ${num(MINP)} usable peers, so names here use the market P/E.` : `Sector P/E ${x.pe}×.`} Tap to filter the gap map.">
        <span class="n">${esc(vxSec(x.s))}</span>${bar(x.med)}<span class="r ${x.med > 15 ? "up" : x.med < -15 ? "dn" : ""}">${vxPct(x.med, 0)}</span><span class="r">${x.n}</span><span class="r">${x.pe == null ? "market" : x.pe + "×"}</span></button>`).join("")}
      ${all > 12 ? `<button class="vx-btn vx-secall" type="button" data-ctl="secall">${S.secAll ? "Show 12" : `Show all ${all}`}</button>` : ""}
      <p class="vx-cap">A thin sector (under ${num(MINP)} names) is grey: its middle gap rests on one or two companies.</p>
    </div>`;
  }

  /* ---------- page ---------- */
  const head = (no, k, sub, right = "") => `<div class="today-section-head"><p class="today-kicker">${no} · ${k} <span>· ${sub}</span></p><div>${right}</div></div>`;
  const disclaimer = `<p class="pf-foot">The desk's read, not advice. Fair value here is the middle of up to four rough models run on public fundamentals: a model's estimate with a range, not a price target. A price below the model's value is not a reason on its own to own a stock; models miss debt, one-offs and cycles. The desk never places orders.</p>
    <p class="pf-foot">Model estimates on public fundamentals for research and education — not price targets, not advice, not a signal to buy or sell. A price below model fair value is not a recommendation, and a low share price never means a company is cheap. Past performance does not guarantee future results.</p>`;
  const picker = `<select class="vx-sel" data-ctl="pick" aria-label="Choose a name">${[...PICK].sort((a, b) => a.sym.localeCompare(b.sym)).map(x => `<option value="${esc(x.sym)}"${x.sym === S.focus ? " selected" : ""}>${esc(x.sym)}</option>`).join("")}</select>`;

  function render() {
    const one = `<section class="vx-ch" data-ch="one">
        ${head("03", "ONE NAME, FOUR MODELS", "the range matters more than the point", picker)}
        ${focusPanel()}
      </section>`;
    const body = paid ? `
      <section class="vx-ch" data-ch="map">
        ${head("02", "THE GAP MAP", "every name, widest gap first", `<b>${ROWS.filter(passes).length} of ${ROWS.length}</b>`)}
        <div class="vx-gap">${gapMap()}</div>
      </section>
      ${one}
      <section class="vx-ch" data-ch="sec">
        ${head("04", "BY SECTOR", "where the gaps cluster", `<div class="wl-chips">${[["gap", "Gap"], ["size", "Size"], ["name", "A–Z"]].map(([k, l]) => `<button type="button" data-ssort="${k}" aria-pressed="${S.secSort === k}">${l}</button>`).join("")}</div>`)}
        <div class="vx-gap">${sectors()}</div>
      </section>` : `
      <section class="vx-ch" data-ch="map">
        ${head("02", "WIDEST BELOW FAIR", "a preview of three")}
        <div class="vx-gap"><div class="vx-card">${under.slice(0, 3).map(endRow).join("") || '<p class="vx-cap">None below model fair value right now.</p>'}</div></div>
      </section>
      ${PICK.length ? one : ""}
      <div class="vx-ch">${planWall("The full value screen", `${ROWS.length} names valued four independent ways — all ${under.length} priced below model fair value, the ${over.length} priced above it, and every stock's full four-model working.`)}</div>`;
    root.innerHTML = `
      <div class="today-date">Value <span>· model fair value · run ${esc(asofTxt)} PKT</span></div>
      <section class="vx-ch first">
        ${head("01", "THE SCREEN AT A GLANCE", "an estimate with a range")}
        ${hero()}
      </section>
      ${body}
      ${disclaimer}
      <div class="wl-tip" aria-hidden="true"></div>`;
    charts();
  }
  function charts() {
    const g = root.querySelector('[data-chart="gap"]'), f = root.querySelector('[data-chart="ff"]');
    if (g) g.innerHTML = gapChart(g.clientWidth || 600);
    if (f) f.innerHTML = field(f.clientWidth || 500);
  }

  /* ---------- interactions (bound to this page root only) ---------- */
  const tip = () => root.querySelector(".wl-tip");
  const showTip = (e, html) => { const t = tip(); if (!t) return; t.innerHTML = html; t.style.display = "block"; t.style.left = Math.max(8, Math.min(e.clientX + 14, innerWidth - 290)) + "px"; t.style.top = (e.clientY + 14) + "px"; };
  const hideTip = () => { const t = tip(); if (t) t.style.display = "none"; };
  const barAt = e => { const s = root.querySelector(".vx-gapsvg"); if (!s) return null; const b = s.getBoundingClientRect(), k = s.viewBox.baseVal.width / b.width, i = Math.floor(((e.clientX - b.left) * k - +s.dataset.l) / +s.dataset.bw); return ROWS[i] || null; };
  const scrollTo = ch => root.querySelector(`[data-ch="${ch}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  const focus = (sym, scroll) => { if (!BY[sym] || !PICK.includes(BY[sym])) return; S.focus = sym; render(); if (scroll) scrollTo("one"); };

  root.addEventListener("click", e => {
    const t = e.target;
    if (t.closest("a[href]")) return;
    if (t.closest(".vx-gapsvg")) { const r = barAt(e); if (r) focus(r.sym, true); return; }
    const f = t.closest("[data-filt]"); if (f) { S.filt = f.dataset.filt; render(); return; }
    const so = t.closest("th[data-sort]"); if (so) { const k = so.dataset.sort; S.tDir = S.tSort === k ? -S.tDir : (k === "sym" || k === "s" ? 1 : -1); S.tSort = k; render(); return; }
    const ss = t.closest("[data-ssort]"); if (ss) { S.secSort = ss.dataset.ssort; render(); return; }
    if (t.closest('[data-ctl="secall"]')) { S.secAll = !S.secAll; render(); return; }
    const sc = t.closest("[data-sec]"); if (sc) { S.sec = sc.dataset.sec; S.filt = "all"; render(); scrollTo("map"); return; }
    const sy = t.closest("[data-sym]"); if (sy) focus(sy.dataset.sym, true);
  });
  root.addEventListener("change", e => {
    const c = e.target.dataset?.ctl;
    if (c === "sec") { S.sec = e.target.value; render(); }
    if (c === "pick") focus(e.target.value, false);
  });
  root.addEventListener("toggle", e => { const k = e.target.dataset?.k; if (k) S.open[k] = e.target.open; }, true);
  root.addEventListener("mousemove", e => {
    if (e.target.closest(".vx-gapsvg")) { const r = barAt(e); if (r) { showTip(e, `<b>${esc(r.sym)}</b> <span>${esc(r.n || "")}</span><br>price ${vxRs(r.p)} · model ${vxRs(r.c)}<br><b class="${VX_VCLS[r.v] || "mut"}">${vxPct(r.x)}</b> <span>· ${VX_VERD[r.v] || "unknown"} · ${r.nm}/4 models · tap to open</span>`); return; } }
    const t = e.target.closest("[data-tip]"); if (t) { showTip(e, esc(t.dataset.tip)); return; }
    hideTip();
  });
  root.addEventListener("mouseleave", hideTip);
  let rz;
  const onResize = () => { if (!document.body.contains(root)) { removeEventListener("resize", onResize); return; } clearTimeout(rz); rz = setTimeout(charts, 150); };
  addEventListener("resize", onResize);

  render();
}
