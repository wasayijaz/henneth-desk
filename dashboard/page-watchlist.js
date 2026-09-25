// watchlist page — redesign 2026-09 (mockup: docs/redesign-mockups/watchlist-mockup.html)
// Safe to call repeatedly: toggleWatch() in app.js re-calls pageWatchlist() after every save.
// Business logic stays in its owners: "what changed" is app.js watchIntel(), fair value is
// fairvalue.json, health is fundamental_scores.json. This file only lays those out.

const WL_STATE = { view: "cards", sort: "day", tok: 0, d: null, focus: null, toastT: 0, hooked: false };
const WL_STAR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9 6.8 19.6l1-5.8-4.3-4.1 5.9-.9z"/></svg>';
const WL_EVNAME = { results: "Results", ex_dividend: "Ex-dividend", book_closure: "Book closure" };
const WL_HEALTH = { attractive: ["stronger", "up"], caution: ["weaker", "dn"], mixed: ["mixed", "mut"] };
const WL_TOUCH = typeof matchMedia === "function" && matchMedia("(hover: none)").matches;

const wlNum = v => typeof v === "number" && isFinite(v);
const wlPct = (v, d = 2) => !wlNum(v) ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d) + "%";
const wlCls = v => !wlNum(v) ? "mut" : v > 0 ? "up" : v < 0 ? "dn" : "mut";
const wlPx = v => !wlNum(v) ? "—" : v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const wlToday = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Karachi" });   // PKT YYYY-MM-DD
const wlDays = (d, from) => Math.round((Date.parse(d + "T12:00:00Z") - Date.parse(from + "T12:00:00Z")) / 864e5);
const wlFmtD = (d, o = { day: "2-digit", month: "short" }) => d ? new Date(d + "T12:00:00Z").toLocaleDateString("en-GB", { ...o, timeZone: "UTC" }) : "—";
const wlDot = c => `<svg class="wl-dot ${c}" viewBox="0 0 8 8" aria-hidden="true"><rect x="0.6" y="0.6" width="6.8" height="6.8"/></svg>`;

async function pageWatchlist() {
  const tok = ++WL_STATE.tok;
  wlHook();
  const [quant, uni, sect, fvAll, fscore, live, newsAll, calAll, claimsAll, sigAll] = await Promise.all([
    j("quant.json"), j("universe.json"), j("sectors.json"), j("fairvalue.json"), j("fundamental_scores.json"), j("live.json"),
    j("newslog.json"), j("earnings_calendar.json"), j("claims.json"), j("signals.json")]);
  if (tok !== WL_STATE.tok || !routeHash().startsWith("#/watchlist")) return;
  if (!me) { wlSignedOut(); return; }
  const q = quant?.tickers || {}, list = watchlist();
  const syms = list.filter(s => q[s]);
  const hist = {};
  await Promise.all(syms.map(s => j("history/" + s + ".json", 300000).then(h => { hist[s] = Array.isArray(h) ? h : null; }, () => { hist[s] = null; })));
  if (tok !== WL_STATE.tok || !routeHash().startsWith("#/watchlist")) return;
  WL_STATE.d = { q, uni: uni?.symbols || {}, sect: sect?.tickers || {}, fv: fvAll?.tickers || {}, fs: fscore?.tickers || {},
    lv: live?.tickers || {}, cal: calAll, news: newsAll, claims: claimsAll, signals: sigAll, list, syms,
    missing: list.filter(s => !q[s]), hist, today: wlToday() };
  wlRender();
}

function wlSignedOut() {
  $("view").innerHTML = `<div class="today-page wl-page">
    <div class="today-date">Watchlist <span>· your names, one screen</span></div>
    <section class="wl-empty">
      <p class="today-kicker">YOUR WATCHLIST</p>
      <p>Sign in to build a watchlist — star any stock and it follows you here with its price, valuation and health at a glance.</p>
      <button class="auth-go wl-go" onclick="openAuth('signup')">Create a free account</button>
    </section></div>`;
}

/* ---------- derived views of state (no new business rules) ---------- */
function wlName(s) {
  const d = WL_STATE.d, q = d.q[s], fv = d.fv[s];
  const events = (d.cal?.events || []).filter(e => e.ticker === s && e.date);
  const sig = (d.signals?.active || []).find(x => (x.ticker || x.sym) === s);
  return { s, q, fv, fs: d.fs[s], events, sig,
    name: d.uni[s]?.name || "", sector: d.sect[s]?.sector || fv?.sector || "",
    px: d.lv[s]?.current ?? q?.close, gap: wlNum(fv?.mispricing_pct) ? fv.mispricing_pct : null };
}
function wlNext(n) {
  const t = WL_STATE.d.today;
  return n.events.filter(e => e.type !== "book_closure" && wlDays(e.date, t) >= 0).sort((a, b) => a.date.localeCompare(b.date))[0] || null;
}
function wlSorted(names) {
  const t = WL_STATE.d.today, big = 1e9;
  const key = {
    day: n => wlNum(n.q.ret_1d) ? -n.q.ret_1d : big,
    m20: n => wlNum(n.q.ret_20d) ? -n.q.ret_20d : big,
    fair: n => n.gap == null ? big : -n.gap,
    event: n => { const e = wlNext(n); return e ? wlDays(e.date, t) : big; },
    az: n => n.s
  }[WL_STATE.sort];
  return [...names].sort((a, b) => { const x = key(a), y = key(b); return typeof x === "string" ? x.localeCompare(y) : x - y; });
}
function wlChanges() {
  const d = WL_STATE.d;
  const ev = watchIntel(d.syms, { q: d.q, fvt: d.fv, news: d.news, cal: d.cal, claims: d.claims, signals: d.signals });
  const by = new Map();   // one row per message: market-wide stories tag many names
  for (const e of ev) { const k = e.tag + "|" + e.msg; if (by.has(k)) by.get(k).names.push(e.s); else by.set(k, { ...e, names: [e.s] }); }
  return [...by.values()];
}

/* ---------- pieces ---------- */
function wlSpark(n) {
  const all = (WL_STATE.d.hist[n.s] || []).filter(x => wlNum(x?.close));
  if (all.length < 2) return `<div class="wl-spark-none">No price history on file</div>`;
  const w = 240, h = 54, H = all.slice(-60), off = all.length - H.length;
  // Display overlay only: a 50-close average line for the picture. quant.json sma50 stays the desk's number.
  const ma = H.map((_, i) => { const k = off + i; if (k < 49) return null; let t = 0; for (let m = k - 49; m <= k; m++) t += all[m].close; return t / 50; });
  const vals = H.map(x => x.close).concat(ma.filter(v => v != null));
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const sy = v => h - 4 - (v - lo) / (hi - lo || 1) * (h - 8), sx = i => i / (H.length - 1) * w;
  const up = H.at(-1).close >= H[0].close;
  const line = H.map((x, i) => (i ? "L" : "M") + sx(i).toFixed(1) + " " + sy(x.close).toFixed(1)).join("");
  const mal = ma.map((v, i) => v == null ? "" : (ma[i - 1] == null ? "M" : "L") + sx(i).toFixed(1) + " " + sy(v).toFixed(1)).join("");
  return `<svg class="wl-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" data-s="${esc(n.s)}" aria-hidden="true">
    ${mal ? `<path class="ma" d="${mal}" vector-effect="non-scaling-stroke"/>` : ""}
    <path class="ln" d="${line}" style="stroke:var(${up ? "--up" : "--dn"})" vector-effect="non-scaling-stroke"/>
    <line class="cross" x1="0" x2="0" y1="0" y2="${h}" style="display:none" vector-effect="non-scaling-stroke"/>
    <rect x="0" y="0" width="${w}" height="${h}" fill="transparent"/></svg>`;
}
function wlEventLine(n) {
  const t = WL_STATE.d.today, e = wlNext(n);
  if (n.sig) return `${wlDot("sig")}${esc(n.sig.strategy_id || n.sig.strategy || "A proven strategy")} is firing — see the Board`;
  if (e) { const dd = wlDays(e.date, t);
    return `${wlDot(e.confirmed ? "" : "hollow")}${WL_EVNAME[e.type] || esc(e.type)} ${wlFmtD(e.date)} · ${dd === 0 ? "today" : "in " + dd + "d"}${e.confirmed ? "" : " · unconfirmed"}`; }
  return `<span class="mut">No dated event in the calendar</span>`;
}
function wlStarBtn(s) {
  return `<button class="wl-star" data-star="${esc(s)}" aria-label="Remove ${esc(s)} from watchlist" title="Remove from watchlist">${WL_STAR}</button>`;
}
function wlCard(n) {
  const q = n.q, hl = WL_HEALTH[n.fs?.rating] || ["—", "mut"], note = noteFor(n.s);
  return `<article class="today-radar-card" data-s="${esc(n.s)}" tabindex="0" aria-label="${esc(n.s)} ${esc(n.name)}">
    <div class="today-radar-card-head"><b>${esc(n.s)}</b><div class="wl-card-head-r"><span class="wl-sector" title="${esc(n.sector || "Sector unknown")}">${esc((n.sector || "—").toUpperCase())}</span>${wlStarBtn(n.s)}</div></div>
    <div class="wl-card-name">${esc(n.name || "—")}</div>
    <div class="wl-card-sub"><span class="px">${wlPx(n.px)}</span><span class="${wlCls(q.ret_1d)}">${wlPct(q.ret_1d)}</span></div>
    ${wlSpark(n)}
    <div class="today-radar-metrics">
      <span><small>20 DAYS</small><b class="${wlCls(q.ret_20d)}">${wlPct(q.ret_20d, 1)}</b></span>
      <span><small>FAIR VALUE</small><b>${n.gap == null ? "—" : wlPct(n.gap, 0) + (n.gap >= 0 ? " ↑" : " ↓")}</b></span>
      <span><small>HEALTH</small><b class="${hl[1]}">${hl[0]}</b></span>
    </div>
    <div class="wl-event">${wlEventLine(n)}</div>
    ${note ? `<p class="wl-note">✎ ${esc(note)}</p>` : ""}
  </article>`;
}
function wlTable(names) {
  return `<div class="today-table-wrap"><table class="today-table"><thead><tr><th>Ticker</th><th>Sector</th><th>Price</th><th>Day</th><th>20 days</th><th>RSI</th><th>Fair value gap</th><th>Health</th><th>Next event</th><th><span class="wl-sr">Remove</span></th></tr></thead><tbody>
  ${names.map(n => { const q = n.q, e = wlNext(n), hl = WL_HEALTH[n.fs?.rating] || ["—", "mut"];
    return `<tr class="clickable" data-s="${esc(n.s)}"><td><b>${esc(n.s)}</b></td><td class="mut">${esc(n.sector || "—")}</td><td>${wlPx(n.px)}</td><td class="${wlCls(q.ret_1d)}">${wlPct(q.ret_1d)}</td><td class="${wlCls(q.ret_20d)}">${wlPct(q.ret_20d, 1)}</td><td>${wlNum(q.rsi14) ? q.rsi14.toFixed(0) : "—"}</td><td>${n.gap == null ? "—" : wlPct(n.gap, 0)}</td><td class="${hl[1]}">${hl[0]}</td><td>${e ? (WL_EVNAME[e.type] || esc(e.type)) + " " + wlFmtD(e.date) : "—"}</td><td>${wlStarBtn(n.s)}</td></tr>`; }).join("")}
  </tbody></table></div>`;
}
function wlMap(names) {
  const pts = names.filter(n => n.gap != null && wlNum(n.q.ret_20d));
  const out = names.length - pts.length;
  if (!pts.length) return `<div class="wl-map wl-map-none">No name on your list has both a 20-day move and a fair value on file.</div>`;
  const W = 1080, H = 380, P = { l: 56, r: 24, t: 26, b: 34 };
  const xm = Math.max(12, ...pts.map(n => Math.abs(n.q.ret_20d))) * 1.1, ym = Math.max(40, ...pts.map(n => Math.abs(n.gap))) * 1.08;
  const sx = v => P.l + (v + xm) / (2 * xm) * (W - P.l - P.r), sy = v => P.t + (ym - v) / (2 * ym) * (H - P.t - P.b);
  const xs = xm > 40 ? 10 : 5, ys = ym > 80 ? 50 : 20;
  let g = "";
  for (let v = -Math.floor(xm / xs) * xs; v <= xm; v += xs) g += `<line class="grid" x1="${sx(v)}" x2="${sx(v)}" y1="${P.t}" y2="${H - P.b}"/><text x="${sx(v)}" y="${H - P.b + 14}" text-anchor="middle">${v > 0 ? "+" : ""}${v}%</text>`;
  for (let v = -Math.floor(ym / ys) * ys; v <= ym; v += ys) g += `<line class="grid" x1="${P.l}" x2="${W - P.r}" y1="${sy(v)}" y2="${sy(v)}"/><text x="${P.l - 8}" y="${sy(v) + 3}" text-anchor="end">${v > 0 ? "+" : ""}${v}%</text>`;
  const dots = pts.map(n => `<g class="pt" data-s="${esc(n.s)}" tabindex="0" transform="translate(${sx(n.q.ret_20d).toFixed(1)},${sy(n.gap).toFixed(1)})"><circle r="5" style="fill:var(${(n.q.ret_1d || 0) >= 0 ? "--up" : "--dn"})"/><text x="9" y="4">${esc(n.s)}</text></g>`).join("");
  return `<div class="wl-map"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Scatter of watchlist names: 20-day price change against gap to the desk's fair value">
    ${g}<line class="ax" x1="${sx(0)}" x2="${sx(0)}" y1="${P.t}" y2="${H - P.b}"/><line class="ax" x1="${P.l}" x2="${W - P.r}" y1="${sy(0)}" y2="${sy(0)}"/>
    <text class="q" x="${W - P.r - 6}" y="${P.t + 12}" text-anchor="end">RISING · FAIR VALUE ABOVE PRICE</text>
    <text class="q" x="${P.l + 6}" y="${P.t + 12}">FALLING · FAIR VALUE ABOVE PRICE</text>
    <text class="q" x="${W - P.r - 6}" y="${H - P.b - 8}" text-anchor="end">RISING · PRICE ABOVE FAIR VALUE</text>
    <text class="q" x="${P.l + 6}" y="${H - P.b - 8}">FALLING · PRICE ABOVE FAIR VALUE</text>
    <text x="${(W + P.l) / 2}" y="${H - 4}" text-anchor="middle">← 20-day price change →</text>
    <text transform="translate(12 ${H / 2}) rotate(-90)" text-anchor="middle">gap to fair value</text>
    ${dots}</svg></div>
    <p class="today-chart-source">Source: quant.json (ret_20d) and fairvalue.json (mispricing_pct) · dot colour = day move${out ? ` · ${out} name${out === 1 ? "" : "s"} not plotted (no fair value or 20-day move on file)` : ""}. Position is descriptive, not a call.</p>`;
}
function wlCalendar(names) {
  const t = WL_STATE.d.today, span = 35, W = 1080, L = 70, R = 14;
  const rows = names.filter(n => n.events.some(e => { const dd = wlDays(e.date, t); return dd >= -3 && dd <= span; }));
  if (!rows.length) return `<div class="wl-cal wl-cal-none">No results or dividend dates in the calendar for your names in the next five weeks.</div>
    <p class="today-chart-source">Source: earnings_calendar.json</p>`;
  const RH = 24, top = 26, H = top + rows.length * RH + 10;
  const sx = d => L + (d + 3) / (span + 3) * (W - L - R);
  const t0 = Date.parse(t + "T12:00:00Z");
  let g = "";
  for (let d = -3; d <= span; d++) { const dt = new Date(t0 + d * 864e5); if (dt.getUTCDay() === 1) g += `<line class="wk" x1="${sx(d)}" x2="${sx(d)}" y1="${top - 6}" y2="${H - 6}"/><text x="${sx(d) + 3}" y="${top - 10}">${wlFmtD(dt.toISOString().slice(0, 10))}</text>`; }
  g += `<line class="today" x1="${sx(0)}" x2="${sx(0)}" y1="${top - 14}" y2="${H - 6}"/><text x="${sx(0) + 3}" y="12" class="today-lbl">today ${wlFmtD(t)}</text>`;
  rows.forEach((n, i) => {
    const y = top + i * RH + RH / 2;
    g += `<text class="lbl" x="8" y="${y + 3}">${esc(n.s)}</text><line class="row" x1="${L}" x2="${W - R}" y1="${y}" y2="${y}"/>`;
    for (const e of n.events) {
      const d = wlDays(e.date, t); if (d < -3 || d > span) continue;
      if (e.buy_by && e.type !== "book_closure") { const b = Math.max(-3, wlDays(e.buy_by, t)); g += `<line class="bb" x1="${sx(b)}" x2="${sx(d)}" y1="${y}" y2="${y}"/>`; }
      const tip = `${n.s} · ${WL_EVNAME[e.type] || e.type} ${wlFmtD(e.date)}${e.buy_by ? " · buy-by " + wlFmtD(e.buy_by) : ""} · ${e.confirmed ? "confirmed" : "unconfirmed"}`;
      const shape = e.type === "results" ? `<rect x="-4.5" y="-4.5" width="9" height="9"` : e.type === "book_closure" ? `<rect x="-3" y="-6" width="6" height="12"` : `<circle r="4.5"`;
      g += `<g transform="translate(${sx(d)},${y})" data-tip="${esc(tip)}" class="${e.confirmed ? "ev" : "ev hollow"}">${shape}/></g>`;
    }
  });
  return `<div class="wl-cal"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Upcoming results and dividend dates for watched names">${g}</svg></div>
    <div class="wl-legend"><span><svg width="10" height="10"><circle cx="5" cy="5" r="4.5" fill="currentColor"/></svg>ex-dividend</span><span><svg width="10" height="10"><rect width="9" height="9" fill="currentColor"/></svg>results</span><span><svg width="8" height="12"><rect width="6" height="12" fill="currentColor"/></svg>book closure</span><span><svg width="10" height="10"><circle cx="5" cy="5" r="4" fill="none" stroke="currentColor"/></svg>hollow = unconfirmed</span><span><svg width="18" height="6"><line x1="0" x2="18" y1="3" y2="3" stroke="currentColor" stroke-width="2"/></svg>buy-by → date</span></div>
    <p class="today-chart-source">Source: earnings_calendar.json · ${rows.length} of ${names.length} names have a dated event from three days back to five weeks out · ${WL_TOUCH ? "tap" : "point at"} a marker for detail.</p>`;
}

/* ---------- page ---------- */
function wlRender() {
  const d = WL_STATE.d, view = $("view"); if (!d || !view) return;
  const names = d.syms.map(wlName), n = names.length;
  const moved = names.filter(x => wlNum(x.q.ret_1d));
  const up = moved.filter(x => x.q.ret_1d > 0).length, dn = moved.filter(x => x.q.ret_1d < 0).length, fl = n - up - dn;
  const avg = moved.length ? moved.reduce((a, x) => a + x.q.ret_1d, 0) / moved.length : null;
  const byDay = [...moved].sort((a, b) => b.q.ret_1d - a.q.ret_1d), best = byDay[0], worst = byDay.at(-1);
  const soon = names.filter(x => { const e = wlNext(x); return e && wlDays(e.date, d.today) <= 14; }).length;
  const dates = names.map(x => x.q.date).filter(Boolean).sort(), close = dates.at(-1);
  const closeTxt = close ? wlFmtD(close, { weekday: "short", day: "2-digit", month: "short", year: "numeric" }) : "unknown";
  const sorted = wlSorted(names), V = WL_STATE.view;

  let changes;
  if (!n) changes = "";
  else if (!hasFeature("watch_intel")) changes = `<div class="today-section-head"><p class="today-kicker">WHAT CHANGED</p><div><b>on a paid plan</b></div></div>` +
    planWall("Watchlist intelligence",
      "The desk watches your names between visits: strategies firing, 4%+ moves, volume surges, fair-value crossings, impact-4 news, results and buy-by dates inside a week, fresh broker calls — surfaced as 'what changed', not another table to scan.");
  else { const ch = wlChanges();
    changes = `<div class="today-section-head"><p class="today-kicker">WHAT CHANGED <span>· ${ch.length ? ch.length + " item" + (ch.length === 1 ? "" : "s") : "quiet"}</span></p><div><b>ranked by weight</b></div></div>
    <ul class="wl-changes">${ch.length ? ch.map(c => { const k = c.tag.startsWith("move") ? (c.tag.includes("↑") ? "up" : "dn") : c.w >= 5 ? "hot" : "";
      return `<li class="wl-change" data-nav="${esc(c.names[0])}" tabindex="0"><b>${c.names.map(esc).join(" · ")}</b><span class="wl-kind ${k}">${esc(c.tag)}</span><span>${esc(c.msg)}</span></li>`; }).join("")
      : `<li class="wl-change wl-quiet"><span class="mut">Nothing important changed on your names — a quiet watchlist is a feature, not a bug.</span></li>`}</ul>`; }

  const tape = byDay.concat(names.filter(x => !wlNum(x.q.ret_1d))).map(x => { const r = x.q.ret_1d, a = wlNum(r) ? Math.min(Math.abs(r) / 3, 1) * 34 + 6 : 0;
    return `<button data-go="${esc(x.s)}" style="background:color-mix(in srgb, var(${(r || 0) >= 0 ? "--up" : "--dn"}) ${a.toFixed(0)}%, var(--paper))" aria-label="${esc(x.s)} ${wlPct(r)}, jump to card"><b>${esc(x.s)}</b><span class="${wlCls(r)}">${wlPct(r, 1)}</span></button>`; }).join("");
  const inList = new Set(d.list);
  const opts = Object.keys(d.uni).filter(s => !inList.has(s)).sort().map(s => `<option value="${esc(s)}">${esc(d.uni[s]?.name || "")}</option>`).join("");
  const missing = d.missing.length ? `<p class="today-chart-source wl-missing">Not in today's price data, so not shown: ${d.missing.map(s => `<span>${esc(s)} ${wlStarBtn(s)}</span>`).join(" ")}</p>` : "";

  view.innerHTML = `<div class="today-page wl-page">
  <div class="today-date">Watchlist <span>· ${n} name${n === 1 ? "" : "s"} · close ${closeTxt}</span></div>
  ${n ? `<section class="today-hero">
    <div class="today-stance">
      <p class="today-kicker ${(avg ?? 0) >= 0 ? "up" : "dn"}">YOUR LIST TODAY <span>· average move ${wlPct(avg)}</span></p>
      <h1 class="${up >= dn ? "up" : "dn"}">${up} up · ${dn} down</h1>
      <p class="wl-hero-sub">${best ? `<b>${esc(best.s)}</b> led (${wlPct(best.q.ret_1d)})${worst !== best ? `, <b>${esc(worst.s)}</b> lagged (${wlPct(worst.q.ret_1d)})` : ""}. ` : ""}${soon} name${soon === 1 ? " has" : "s have"} a results or dividend date in the next two weeks. Research, not advice.</p>
      <div class="wl-breadth" aria-hidden="true">${up ? `<i style="flex:${up};background:var(--up)"></i>` : ""}${fl ? `<i style="flex:${fl};background:var(--rline)"></i>` : ""}${dn ? `<i style="flex:${dn};background:var(--dn)"></i>` : ""}</div>
    </div>
    <div class="today-index">
      <p class="today-kicker">SESSION TAPE <span>· one block per name, shade = size of move · tap to jump</span></p>
      <div class="wl-tape">${tape}</div>
    </div>
  </section>` : ""}
  ${changes}
  <div class="today-section-head"><p class="today-kicker">YOUR NAMES <span>· ${n}</span></p><div><b>${close ? "close " + wlFmtD(close) : "close unknown"}</b></div></div>
  <div class="wl-controls">
    <div class="wl-control-set">
      ${n ? `<div class="wl-control"><span class="wl-chips-label">VIEW</span><div class="wl-chips">${[["cards", "Cards"], ["table", "Table"], ["map", "Map"]].map(([k, l]) => `<button data-view="${k}" aria-pressed="${V === k}">${l}</button>`).join("")}</div></div>
      <div class="wl-control" ${V === "map" ? "hidden" : ""}><span class="wl-chips-label">SORT</span><div class="wl-chips">${[["day", "Day move"], ["m20", "20 days"], ["fair", "Fair value gap"], ["event", "Next event"], ["az", "A–Z"]].map(([k, l]) => `<button data-sort="${k}" aria-pressed="${WL_STATE.sort === k}">${l}</button>`).join("")}</div></div>` : ""}
    </div>
    <form class="wl-add"><input list="wl-uni" placeholder="Add a ticker…" aria-label="Add a ticker" autocomplete="off"><datalist id="wl-uni">${opts}</datalist><button type="submit">+ Add</button></form>
  </div>
  ${n ? `<div class="wl-view" ${V !== "cards" ? "hidden" : ""}><div class="today-radar-cards wl-cards">${sorted.map(wlCard).join("")}</div>
    <p class="today-chart-source">Line: last 60 closes (history/), dashed: 50-close average · fair value: fairvalue.json, ↑ means the desk's fair value sits above the close · health: fundamental_scores.json · ${WL_TOUCH ? "tap" : "click"} a card for the stock page, the star removes it.</p></div>
  <div class="wl-view" ${V !== "table" ? "hidden" : ""}>${wlTable(sorted)}</div>
  <div class="wl-view" ${V !== "map" ? "hidden" : ""}>${wlMap(names)}</div>`
  : `<div class="wl-empty"><p>No stocks yet. Open any stock and tap the ★ to add it — try <a href="/board">the Board</a> or search (top right). You can also type a ticker above.</p></div>`}
  ${missing}
  ${n ? `<div class="today-section-head"><p class="today-kicker">COMING UP <span>· results and dividend dates for your names</span></p><div><b>next 5 weeks</b></div></div>
  ${wlCalendar(names)}` : ""}
  </div>`;
  wlWire(view.querySelector(".wl-page"));
  if (WL_STATE.focus) { const s = WL_STATE.focus; WL_STATE.focus = null; wlGo(s); }
}

/* ---------- interactions ---------- */
function wlHook() {
  if (WL_STATE.hooked) return;
  WL_STATE.hooked = true;
  window.addEventListener("hashchange", () => { if (!routeHash().startsWith("#/watchlist")) { wlHideTip(); wlToastHide(); } });
}
function wlEl(id, cls, html) {
  let el = document.getElementById(id);
  if (!el) { el = document.createElement("div"); el.id = id; el.className = cls; if (html) el.innerHTML = html; document.body.appendChild(el); }
  return el;
}
function wlShowTip(e, html) {
  const tip = wlEl("wl-tip", "wl-tip");
  tip.innerHTML = html; tip.style.display = "block";
  const w = tip.offsetWidth, h = tip.offsetHeight;
  tip.style.left = Math.max(8, Math.min(e.clientX + 14, innerWidth - w - 8)) + "px";
  tip.style.top = Math.max(8, Math.min(e.clientY + 14, innerHeight - h - 8)) + "px";
}
function wlHideTip() { const t = document.getElementById("wl-tip"); if (t) t.style.display = "none"; }
function wlToast(msg, undo) {
  const t = wlEl("wl-toast", "wl-toast", '<span></span><button type="button">Undo</button>');
  t.querySelector("span").textContent = msg;
  const b = t.querySelector("button");
  b.style.display = undo ? "" : "none";
  b.onclick = undo ? () => { wlToastHide(); undo(); } : null;
  t.style.display = "flex";
  clearTimeout(WL_STATE.toastT);
  WL_STATE.toastT = setTimeout(wlToastHide, 6000);
}
function wlToastHide() { const t = document.getElementById("wl-toast"); if (t) t.style.display = "none"; }
function wlGo(s) {
  if (WL_STATE.view !== "cards") { WL_STATE.view = "cards"; WL_STATE.focus = s; wlRender(); return; }
  const el = [...document.querySelectorAll("#view .wl-cards .today-radar-card")].find(c => c.dataset.s === s);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
}
function wlRemove(s, btn) {
  btn.disabled = true;
  const row = btn.closest(".today-radar-card, tr");
  const done = async () => {
    await toggleWatch(s);   // persists to profiles.watchlist, tracks, re-renders this page
    wlToast(`${s} removed from your watchlist`, async () => { WL_STATE.focus = s; await toggleWatch(s); });
  };
  if (row && !matchMedia("(prefers-reduced-motion: reduce)").matches) { row.classList.add("wl-card-out"); setTimeout(done, 240); } else done();
}
async function wlAdd(input) {
  const d = WL_STATE.d, s = input.value.trim().toUpperCase();
  if (!s) { wlToast("Type a ticker"); return; }
  if (d.list.includes(s)) { wlGo(s); return; }
  if (!d.q[s] && !d.uni[s]) { wlToast(`${s} — not a ticker the desk covers`); return; }
  input.value = "";
  WL_STATE.focus = s;
  await toggleWatch(s);
  wlToast(`${s} added`);
}
function wlWire(root) {
  if (!root) return;
  const d = WL_STATE.d;
  root.addEventListener("click", e => {
    const st = e.target.closest("[data-star]");
    if (st) { e.stopPropagation(); wlRemove(st.dataset.star, st); return; }
    const v = e.target.closest("[data-view]"); if (v) { WL_STATE.view = v.dataset.view; wlRender(); return; }
    const so = e.target.closest("[data-sort]"); if (so) { WL_STATE.sort = so.dataset.sort; wlRender(); return; }
    const g = e.target.closest("[data-go]"); if (g) { wlGo(g.dataset.go); return; }
    const tp = e.target.closest("[data-tip]"); if (tp) { wlShowTip(e, esc(tp.dataset.tip)); return; }
    const nav = e.target.closest("[data-nav], .wl-cards .today-radar-card, tr[data-s], .wl-map .pt");
    if (nav) { wlHideTip(); navigate("/ticker/" + (nav.dataset.nav || nav.dataset.s)); }
  });
  root.addEventListener("keydown", e => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const nav = e.target.closest("[data-nav], .wl-cards .today-radar-card, .wl-map .pt");
    if (nav && e.target === nav) { e.preventDefault(); navigate("/ticker/" + (nav.dataset.nav || nav.dataset.s)); }
  });
  const form = root.querySelector(".wl-add");
  if (form) form.addEventListener("submit", e => { e.preventDefault(); wlAdd(form.querySelector("input")); });
  root.addEventListener("mouseleave", () => { wlHideTip(); root.querySelectorAll(".wl-spark .cross").forEach(l => l.style.display = "none"); });
  root.addEventListener("mousemove", e => {
    const sp = e.target.closest(".wl-spark");
    root.querySelectorAll(".wl-spark .cross").forEach(l => { if (l.parentNode !== sp) l.style.display = "none"; });
    if (sp) {
      const H = (d.hist[sp.dataset.s] || []).filter(x => wlNum(x?.close)).slice(-60), r = sp.getBoundingClientRect();
      const i = Math.max(0, Math.min(H.length - 1, Math.round((e.clientX - r.left) / r.width * (H.length - 1))));
      const l = sp.querySelector(".cross"), x = i / (H.length - 1) * 240;
      l.setAttribute("x1", x); l.setAttribute("x2", x); l.style.display = "";
      const last = H.at(-1).close;
      wlShowTip(e, `<b>${esc(sp.dataset.s)}</b> ${wlPx(H[i].close)}<br><span>${wlFmtD(H[i].date)} · last close ${wlPct((last / H[i].close - 1) * 100, 1)} from here</span>`);
      return;
    }
    const pt = e.target.closest(".wl-map .pt");
    if (pt) { const n = wlName(pt.dataset.s);
      wlShowTip(e, `<b>${esc(n.s)}</b> ${wlPx(n.px)} <span class="${wlCls(n.q.ret_1d)}">${wlPct(n.q.ret_1d)}</span><br><span>20 days ${wlPct(n.q.ret_20d, 1)} · fair ${wlPx(n.fv?.composite_fair)} (${esc(n.fv?.verdict || "unknown")})</span>`); return; }
    const t = e.target.closest("[data-tip]"); if (t) { wlShowTip(e, esc(t.dataset.tip)); return; }
    const tp = e.target.closest(".wl-tape button");
    if (tp) { const n = wlName(tp.dataset.go); wlShowTip(e, `<b>${esc(n.s)}</b> ${wlPx(n.px)}<br><span>${esc(n.sector || "sector unknown")}</span>`); return; }
    wlHideTip();
  });
}
