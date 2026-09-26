// dividends page — redesign 2026-09. Ported from docs/redesign-mockups/dividends-mockup.html
// (+ wl/dividends-data.js static snapshot) in the sibling PSX repo, per the owner-approved mockup.
// Fidelity: markup, class names, chapter order, charts (scatter() yield/payout map, annualChart()
// per-company bars), legends and copy are kept as close to the mockup as a live data source allows.
// Deliberate deviations from the literal mockup script, and why:
//   1. mc-* class rename -> dv-*: mc-lvl, mc-strip(+.c3), mc-flag, mc-unk, mc-cap. The bare mc-
//      prefix is load-bearing sitewide for an unrelated paywall/tease widget (themes.css ~866-1133,
//      pages-workspace.css; planWall() emits .mc-lock-kick) — same reason page-macro.js renames
//      mc-* to mac-*. mc-card is dropped: the mockup declares it but never uses it.
//   2. The mockup's fake local `let plan = 'full'` demo toggle (with its own planChips UI) is
//      replaced by the real hasFeature("dividends_full")/planWall() gating the rest of the paid
//      desk uses. Free accounts see the first 3 lanes in Upcoming (matching the mockup's own
//      free-preview slice) and a planWall() card in place of the yield/payout map, company
//      history and past-payouts chapters — the old live pageDividends() gated that same set with
//      isSubscribed(), and the mockup's own wall-teaser text ("the yield and payout map... every
//      company's payout history... is part of the paid plan") claims that broader scope too.
//   3. D.today / D.asof.calendar / precomputed e.past in the mockup all come from a frozen
//      snapshot file. The live port computes "today" with app.js's existing todayPKT() helper
//      (PKT calendar date, correcting the UTC/PKT 5-hour offset) at render time, and derives every
//      upcoming/past split from that real date — never from a stale field. This fixes the README's
//      documented "stale upcoming dates" bug at the source instead of reproducing it.
//   4. D.deep[sym].a rows are [year, totalRs, count] triples (annualChart()'s tooltip needs the
//      count), built here by grouping dividends_deep.json's flat per-ticker [{ex,rs},...] list by
//      ex-date year.
//   5. D.meta[sym] = [name, sector] is built by joining universe.json (name) and sectors.json
//      (sector); D.mism (payout-ratio recompute mismatches, foot() method note only) is computed
//      live by comparing fundamentals.json's stored payout_ratio against DPS/EPS*100.
//   6. The mockup wires its tooltip (mousemove/focusin/focusout/keydown) on `document`. Scoped
//      here to the page root and torn down on navigation so listeners don't accumulate across
//      repeated visits to #view (a global document listener would leak in this SPA).
//
// Real data only, from state/ via j(): dividends.json (DPS filings — upcoming, history,
// face_value_assumed/calibrated), earnings_calendar.json (ex-dates — vendor; book closures — DPS),
// fundamentals.json (trailing yield, EPS/DPS/PE — vendor, string fields with unit suffixes),
// dividends_deep.json (split-adjusted annual payout series — vendor), universe.json (names),
// sectors.json (sector labels). Missing data renders as "unknown" (dv-unk), never guessed.
// No advice language: "the setup"/"the desk's read", never "you should buy"/"sell". No desk
// calls or targets on named securities.

const MON_DV = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const MONL_DV = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const DOW_DV = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
const dvNum = (v, d = 2) => v == null || !isFinite(v) ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const dvUnk = '<span class="dv-unk">unknown</span>';
const dvFD = s => `${s.slice(8, 10)} ${MON_DV[+s.slice(5, 7) - 1]}`;
const dvFDY = s => `${dvFD(s)} ${s.slice(0, 4)}`;
const dvFT = s => s && s.length > 10 ? `${dvFD(s)} ${s.slice(11, 16)}` : (s ? dvFD(s) : "unknown");
const dvMs = s => Date.parse(s.slice(0, 10) + "T12:00:00Z");
const dvIso = t => new Date(t).toISOString().slice(0, 10);
const dvAddD = (s, n) => dvIso(dvMs(s) + n * 864e5);
const dvWd = s => new Date(dvMs(s)).getUTCDay();
const dvIsWk = s => !!s && (dvWd(s) === 0 || dvWd(s) === 6);
const dvDayW = s => s ? `${DOW_DV[dvWd(s)]} ${dvFD(s)}` : "unknown";
const DV_PER = { F: "final", I: "interim I", II: "interim II", III: "interim III", IV: "interim IV", V: "interim V" };
const DV_KIND = { D: "cash", B: "bonus shares", R: "right shares" };
const dvAnnPlain = r => [r.pct != null ? `${dvNum(r.pct, r.pct % 1 ? 2 : 0)}% of face` : null, DV_PER[r.per], DV_KIND[r.kind]].filter(Boolean).join(" · ");
const dvAnnDate = s => { const m = /^(\w+) (\d+), (\d{4})/.exec(s || ""); if (!m) return null; const i = MONL_DV.indexOf(m[1]); return i < 0 ? null : `${m[3]}-${String(i + 1).padStart(2, "0")}-${m[2].padStart(2, "0")}`; };
const dvBizDayBefore = s => { let d = dvAddD(s, -1); while (dvIsWk(d)) d = dvAddD(d, -1); return d; };

// dividends_deep.json ticker -> {a:[[year,totalRs,count],...], p:[[ex,rs],...], n}
function dvAggDeep(list) {
  if (!list || !list.length) return null;
  const p = list.map(r => [r.ex, r.rs]).sort((a, b) => a[0] < b[0] ? -1 : 1);
  const byYear = new Map();
  for (const [ex, rs] of p) {
    const y = +ex.slice(0, 4);
    const row = byYear.get(y) || [y, 0, 0];
    row[1] += rs; row[2] += 1;
    byYear.set(y, row);
  }
  const a = [...byYear.values()].sort((x, y) => x[0] - y[0]);
  return { a, p, n: p.length };
}

async function pageDividends() {
  $("view").innerHTML = `<div class="today-page dv-page"><p class="sub">Loading dividends…</p></div>`;
  const [divs, cal, fund, deep, uni, sect] = await Promise.all([
    j("dividends.json"), j("earnings_calendar.json"), j("fundamentals.json"),
    j("dividends_deep.json"), j("universe.json"), j("sectors.json"),
  ]);
  if (!divs || !cal) { $("view").innerHTML = `<div class="today-page dv-page"><p class="sub">Dividend data is unavailable right now.</p></div>`; return; }

  const TODAY = todayPKT();
  const SNAP = (cal.updated || "").slice(0, 10) || TODAY;
  const staleDays = SNAP ? Math.max(0, Math.round((dvMs(TODAY) - dvMs(SNAP)) / 864e5)) : null;
  const curYear = +TODAY.slice(0, 4);

  const nm = t => (uni?.symbols?.[t]?.name) || null;
  const sec = t => (sect?.tickers?.[t]?.sector) || null;
  const meta = {}; // t -> [name, sector], built lazily via nm()/sec()

  const face = divs.face_value_assumed ?? null;
  const faceCal = divs.face_value_calibrated || {};

  // ---- reshape upcoming/history rows ----
  const upcoming = (divs.upcoming || []).map(r => ({
    t: r.symbol, bc: r.bc_start, end_: r.bc_end, ann: r.announcement, rs: r.dividend_rs,
    yld: r.yield_pct_at_close, per: r.period, kind: r.kind, announced: r.announced, pct: r.pct_of_face,
  }));
  const history = (divs.history || []).map(r => ({
    t: r.symbol, ann: r.announcement, rs: r.dividend_rs, yld: r.yield_pct_at_close, kind: r.kind,
    per: r.period, announced: r.announced, bc: r.bc_start, end: r.bc_end, pct: r.pct_of_face,
  }));
  const annBy = Object.fromEntries(upcoming.map(r => [r.t + "|" + r.bc, r]));

  // ---- fundamentals: parse vendor strings, recompute payout ratio ----
  const F = {}; const mism = [];
  for (const [t, row] of Object.entries(fund?.tickers || fund || {})) {
    if (!row || typeof row !== "object") continue;
    const pf = v => { if (v == null) return null; const n = parseFloat(String(v).replace(/[%,]/g, "")); return isFinite(n) ? n : null; };
    const y = pf(row.div_yield);
    const dps = pf(row.dps ?? row.dividend_per_share);
    const eps = pf(row.eps);
    const pe = pf(row.pe ?? row.pe_ratio);
    const po = (eps != null && eps > 0 && dps != null) ? (dps / eps * 100) : null;
    const storedPO = pf(row.payout_ratio);
    if (storedPO != null && po != null && Math.abs(storedPO - po) > 0.5) mism.push(t);
    F[t] = { y, po, dps, eps, pe };
  }

  // ---- dividends_deep: aggregate per ticker into {a,p,n} ----
  const deepTickers = deep?.tickers || {};
  const D_deep = {};
  for (const t of Object.keys(deepTickers)) { const agg = dvAggDeep(deepTickers[t]); if (agg) D_deep[t] = agg; }
  const deepSyms = Object.keys(D_deep).sort();

  // ---- events: one per ex_dividend / book_closure calendar entry, "cum" derived live ----
  const events = [];
  for (const e of (cal.events || [])) {
    if (e.type !== "ex_dividend" && e.type !== "book_closure") continue;
    const t = e.symbol || e.ticker;
    if (e.type === "book_closure") {
      const date = e.bc_start || e.start, end = e.bc_end || e.end;
      if (!date) continue;
      const cum = dvAddD(date, -3);
      const match = annBy[t + "|" + date];
      events.push({ t, type: "bc", date, end, cum, rs: match?.rs, ann: match?.ann, yld: match?.yld, pct: match?.pct, past: (end || date) < TODAY });
    } else {
      const date = e.date || e.ex_date;
      if (!date) continue;
      const cum = dvBizDayBefore(date);
      const trail = F[t]?.y ?? null;
      events.push({ t, type: "ex", date, cum, trail, past: date < TODAY });
    }
  }
  const ahead = events.filter(e => !e.past);
  const passed = events.filter(e => e.past);
  const byT = {};
  ahead.forEach(e => { (byT[e.t] ||= { t: e.t, ex: null, bc: null })[e.type] = e; });
  const lanes = Object.values(byT).map(g => ({
    ...g, first: [g.ex?.date, g.bc?.date].filter(Boolean).sort()[0], dps: g.bc ? annBy[g.t + "|" + g.bc.date] : null,
  })).sort((a, b) => a.first.localeCompare(b.first) || a.t.localeCompare(b.t));
  if (!lanes.length) { $("view").innerHTML = `<div class="today-page dv-page"><p class="sub">No dividend dates ahead in the calendar right now.</p></div>`; return; }

  const nBC = lanes.filter(l => l.bc).length, nEX = lanes.filter(l => l.ex).length, nExOnly = lanes.filter(l => l.ex && !l.bc).length;
  const wkCum = lanes.filter(l => l.bc && dvIsWk(l.bc.cum));
  const first = lanes[0];
  const firstSame = lanes.filter(l => l.first === first.first).map(l => l.t);
  const inWindow = passed.filter(e => e.date >= SNAP);
  const aheadSet = new Set(lanes.map(l => l.t));
  const PAST = history.filter(h => !h.bc || h.bc < TODAY);

  const gated = !hasFeature("dividends_full");

  // ================= hero (gantt timeline) =================
  const cumOf = l => l.ex?.cum || l.bc?.cum;
  const allDates = lanes.flatMap(l => [l.ex?.date, l.bc?.date, l.bc?.end, l.ex?.cum, l.bc?.cum]).filter(Boolean);
  const T0 = [TODAY, ...allDates].sort()[0], T1 = dvAddD(allDates.sort().at(-1) || TODAY, 2);
  const span = (dvMs(T1) - dvMs(T0)) / 864e5 + 1;
  const P = s => ((dvMs(s) - dvMs(T0)) / 864e5 / span * 100);
  const days = Array.from({ length: span }, (_, i) => dvAddD(T0, i));
  const wkBands = days.filter(dvIsWk).map(s => `<i class="dv-wk" style="left:${P(s).toFixed(3)}%;width:${(100 / span).toFixed(3)}%"></i>`).join("");
  const nowL = `<i class="dv-now" style="left:${P(TODAY).toFixed(3)}%"></i>`;
  const laneTip = l => {
    const x = [`<b>${esc(l.t)}</b>${nm(l.t) ? " · " + esc(nm(l.t)) : ""}`];
    if (l.bc) x.push(`Book closure <b>${dvFD(l.bc.date)} → ${dvFD(l.bc.end)}</b> (DPS)`, `${esc(l.bc.ann || "")}${l.dps ? " · " + esc(dvAnnPlain(l.dps)) : ""}${l.bc.rs != null ? " · Rs <b>" + dvNum(l.bc.rs) + "</b>/share" : ""}${l.bc.yld != null ? " · " + dvNum(l.bc.yld) + "% of last close" : ""}`, `Last cum session, DPS rule: <b>${dvDayW(l.bc.cum)}</b>${dvIsWk(l.bc.cum) ? " ⚑ weekend" : ""}`);
    if (l.ex) x.push(`Ex-date <b>${dvDayW(l.ex.date)}</b> (vendor, unconfirmed)`, `Last cum session, vendor: <b>${dvDayW(l.ex.cum)}</b>`);
    if (!l.bc) x.push("Amount and closure: unknown until DPS files them");
    x.push('<span class="mut">Click to open its dividend history</span>');
    return esc(x.join("<br>"));
  };
  const lane = l => {
    const parts = [wkBands, nowL];
    const c = [l.ex?.cum, l.bc?.cum].filter(Boolean);
    [...new Set(c)].forEach(s => { if (s >= T0) parts.push(`<i class="dv-cum${dvIsWk(s) ? " wk" : ""}" style="left:${P(s).toFixed(3)}%"></i>`); });
    if (l.bc) {
      const a = P(l.bc.date), b = P(dvAddD(l.bc.end, 1));
      parts.push(`<i class="dv-bc" style="left:${a.toFixed(3)}%;width:${(b - a).toFixed(3)}%"></i><span class="dv-rs" style="left:${b.toFixed(3)}%">${l.bc.rs != null ? "Rs " + dvNum(l.bc.rs) : "unknown"}</span>`);
    }
    if (l.ex) parts.push(`<i class="dv-ex" style="left:${(P(l.ex.date) + 50 / span).toFixed(3)}%"></i>`);
    return `<div class="dv-gr"><span class="dv-gl">${dvLink(l.t)}<small>${esc(nm(l.t) || "")}</small></span><button class="dv-trk" type="button" data-sym="${esc(l.t)}" data-tip="${laneTip(l)}" aria-label="${esc(l.t)}: ${l.bc ? `closure ${dvFD(l.bc.date)} to ${dvFD(l.bc.end)}` : ""}${l.ex ? ` ex-date ${dvFD(l.ex.date)}` : ""}. Open dividend history">${parts.join("")}</button></div>`;
  };
  const axis = () => {
    const ticks = days.filter(s => dvWd(s) === 1).map(s => `<span class="dv-tk" style="left:${P(s).toFixed(3)}%">${dvFD(s)}</span>`).join("");
    return `<div class="dv-gr dv-gax"><span class="dv-gl">MON</span><div class="dv-trk">${ticks}<span class="dv-tk now" style="left:${P(TODAY).toFixed(3)}%;top:19px">today</span></div></div>`;
  };
  const dvSHead = (id, kick, title, what, right = "") => `<header class="sx-hd"><div><p class="sx-k">${esc(kick)}</p><h2 id="${id}">${esc(title)}</h2>${what ? `<p class="sx-ld">${esc(what)}</p>` : ""}</div>${right ? `<div class="sx-hr">${right}</div>` : ""}</header>`;

  const hero = () => `<section class="px-ch first sx-hero dv-hero" aria-labelledby="h-hero">
    ${dvSHead("h-hero", "Dividends · book closures and ex-dates", `${nBC} book closures and ${nEX} ex-dates ahead, the first on ${dvFD(first.first)}`,
      `Each lane is one company. The solid bar is the register closure DPS has filed; the diamond is the ex-date a vendor lists; the thin tick is the last session a trade carries the entitlement, as the data layer derives it. Weekends are shaded.`,
      `state ${esc(dvFT(cal.updated))} PKT<br>today ${dvFD(TODAY)}`)}
    ${staleDays != null ? `<p class="dv-stale"><span class="dv-flag">SNAPSHOT ${staleDays} DAY${staleDays === 1 ? "" : "S"} OLD</span> The calendar was last refreshed ${dvFD(SNAP)}. ${passed.length} date${passed.length === 1 ? "" : "s"} in it ha${passed.length === 1 ? "s" : "ve"} already passed and sit in the fold under the table, not on this timeline.</p>` : ""}
    <div class="dv-gt" id="gantt">${axis()}${lanes.map(lane).join("")}</div>
    <div class="dv-lg"><span><i class="bc"></i>book closure · DPS, confirmed</span><span><i class="ex"></i>ex-date · vendor, unconfirmed</span><span><i class="cum"></i>last cum session</span><span><i class="cum wk"></i>last cum falls on a weekend</span><span><i class="wkb"></i>weekend</span></div>
    <div class="sx-kp">
      <div><small>NEXT DATE</small><b>${dvFD(first.first)}</b><span>${firstSame.map(esc).join(", ")} · ${first.ex && first.ex.date === first.first ? "ex-date (vendor)" : "closure start"}</span></div>
      <div><small>CLOSURES FILED</small><b>${nBC}</b><span>DPS, amount known</span></div>
      <div><small>EX-DATE ONLY</small><b>${nExOnly}</b><span>vendor date; amount unknown</span></div>
      <div data-tip="${esc(wkCum.map(l => `${l.t} ${dvDayW(l.bc.cum)}`).join("<br>"))}"><small>WEEKEND CUM DATES</small><b class="${wkCum.length ? "dn" : ""}">${wkCum.length}</b><span>closure − 3 calendar days lands on Sat/Sun</span></div>
    </div>
    <div class="dv-strip c3 dv-tm" aria-label="How the three dates relate">
      <div><small>1 · LAST CUM SESSION</small><b>entitlement travels with the trade</b><span>The last session whose trades are on the register when it closes. DPS rows: closure start − 3 calendar days. Vendor rows: the business day before its ex-date.</span></div>
      <div><small>2 · EX-DATE</small><b>entitlement stays behind</b><span>Trades from this session settle after the register closes, so they carry no entitlement for this payout.</span></div>
      <div><small>3 · BOOK CLOSURE</small><b>register shut, entitlement fixed</b><span>Start → end as filed on DPS. The amount is the announced % of face value${face != null ? ` (Rs ${dvNum(face, 0)}` : ""}${Object.keys(faceCal).length ? `, or the calibrated face for ${Object.keys(faceCal).length} names)` : face != null ? ")" : ""}.</span></div>
    </div>
  </section>`;

  // ================= upcoming table =================
  const upRow = l => {
    const b = l.bc, x = l.ex, f = F[l.t];
    const cumV = x ? dvDayW(x.cum) : b ? dvDayW(b.cum) : dvUnk;
    const cum2 = b && (!x || x.cum !== b.cum) ? `<span class="dv-2">${x ? "DPS rule " + dvDayW(b.cum) : "DPS rule"} ${dvIsWk(b.cum) ? '<span class="dv-flag">weekend</span>' : ""}</span>` : "";
    return `<tr><td>${dvLink(l.t)}<span class="dv-ann">${esc(nm(l.t) || "")}</span></td>
      <td class="l">${esc(sec(l.t) || "") || dvUnk}</td>
      <td class="l">${b ? esc(b.ann || "") + `<span class="dv-ann">${esc(dvAnnPlain(l.dps || {}))}</span>` : dvUnk}</td>
      <td>${b && b.rs != null ? dvNum(b.rs) : dvUnk}</td>
      <td>${b && b.yld != null ? dvNum(b.yld) + "%" : dvUnk}</td>
      <td>${x?.trail != null ? dvNum(x.trail) + "%" : f?.y != null ? dvNum(f.y) + "%" : dvUnk}</td>
      <td>${cumV}${cum2}</td>
      <td>${x ? dvDayW(x.date) : dvUnk}</td>
      <td>${b ? `${dvFD(b.date)} → ${dvFD(b.end)}` : dvUnk}${l.dps?.announced ? `<span class="dv-2">filed ${dvFD(dvAnnDate(l.dps.announced) || l.dps.announced)}</span>` : ""}</td></tr>`;
  };
  const passedRows = () => passed.map(e => `<tr class="dv-past"><td>${dvLink(e.t)}</td><td class="l">${e.type === "bc" ? "book closure · DPS" : "ex-date · vendor"}</td><td>${dvDayW(e.date)}${e.end ? " → " + dvFD(e.end) : ""}</td><td>${e.rs != null ? "Rs " + dvNum(e.rs) : e.trail != null ? dvNum(e.trail) + "% trailing" : dvUnk}</td><td>${e.date >= SNAP ? "after snapshot" : "on snapshot day"}</td></tr>`).join("");
  const upTable = () => {
    const rows = gated ? lanes.slice(0, 3) : lanes;
    const wall = gated ? `<tr class="dv-wall"><td colspan="9">The full dividend desk — ${Math.max(0, lanes.length - 3)} more compan${lanes.length - 3 === 1 ? "y" : "ies"}, the yield and payout map, and every company's payout history — is part of the paid plan.<small>Free preview shows the first three dates. Same data, same sources.</small></td></tr>` : "";
    return `<table class="sx-tbl"><thead><tr><th>Company</th><th class="l">Sector</th><th class="l">Announcement</th><th>Rs / share</th><th data-tip="This one payout ÷ last close in the snapshot (DPS)">This payout<br>÷ last close</th><th data-tip="Vendor trailing-12-month dividend ÷ price. A different base from the column to its left.">Trailing yield<br>(vendor)</th><th>Last cum<br>session</th><th>Ex-date<br>(vendor)</th><th>Book closure<br>(DPS)</th></tr></thead><tbody>${rows.map(upRow).join("")}${wall}</tbody></table>`;
  };
  const upcomingSection = () => `<section class="px-ch" aria-labelledby="h-up">
    ${dvSHead("h-up", "Upcoming", "Every date ahead, one row per company", "Amounts and closures come from DPS filings. Ex-dates come from a vendor and are unconfirmed until DPS files the closure. The two yields use different bases, so they sit in separate columns.", `${lanes.length} companies · ${dvFD(TODAY)} → ${dvFD(T1)}`)}
    <div class="sx-scroll" id="upT" style="margin-top:10px">${upTable()}</div>
    <details class="px-more"><summary><b>${passed.length} date${passed.length === 1 ? "" : "s"} already passed</b> since the snapshot was taken
      <p class="dv-cap" style="margin-top:0">The data layer still lists these as upcoming because it has not refreshed since ${dvFD(SNAP)}.</p>
      <div class="sx-scroll"><table class="sx-tbl"><thead><tr><th>Company</th><th class="l">Date type</th><th>Date</th><th>Amount</th><th>Status</th></tr></thead><tbody>${passedRows()}</tbody></table></div></details>
  </section>`;

  // ================= yield & payout map =================
  let ypView = "map";
  const FS = Object.entries(F).map(([t, f]) => ({ t, ...f })).filter(f => f.y != null);
  const POS = FS.filter(f => f.po != null), NOPO = FS.filter(f => f.po == null);
  const OVER = POS.filter(f => f.po > 100).sort((a, b) => b.po - a.po);
  const XMAX = 200;
  const fTip = f => esc([`<b>${esc(f.t)}</b>${nm(f.t) ? " · " + esc(nm(f.t)) : ""}`, `Trailing yield <b>${dvNum(f.y)}%</b>`, `Payout <b>${f.po == null ? "unknown" : dvNum(f.po, 1) + "%"}</b> = DPS ${dvNum(f.dps)} ÷ EPS ${dvNum(f.eps)}`, f.pe != null ? `P/E ${dvNum(f.pe)}` : "", aheadSet.has(f.t) ? `<b>Has a date ahead</b>` : "", '<span class="mut">Click to open its dividend history</span>'].filter(Boolean).join("<br>"));

  let current = (lanes.find(l => l.bc && D_deep[l.t] && D_deep[l.t].n >= 20) || lanes[0]).t;

  function dvScatter(host) {
    const draw = () => {
      if (!POS.length) { host.innerHTML = `<p class="dv-cap">No companies with both a trailing yield and a defined payout ratio right now.</p>`; return; }
      const W = Math.max(260, host.clientWidth), H = W < 420 ? 240 : 300, L = 36, R = 14, T = 10, Bm = 30;
      const ymax = Math.ceil(Math.max(...POS.map(f => f.y)) / 5) * 5 || 5;
      const X = v => L + Math.min(v, XMAX) / XMAX * (W - L - R), Y = v => T + (ymax - v) / ymax * (H - T - Bm);
      const pts = POS.slice().sort((a, b) => a.po - b.po);
      const yt = Array.from({ length: ymax / 5 + 1 }, (_, i) => i * 5).filter(v => ymax <= 20 || v % 10 === 0).map(v => `<line class="grid" x1="${L}" x2="${W - R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}"/><text x="${L - 6}" y="${(Y(v) + 3).toFixed(1)}" text-anchor="end">${v}%</text>`).join("");
      const xt = [0, 50, 100, 150, 200].map(v => `<text x="${X(v).toFixed(1)}" y="${H - 16}" text-anchor="${v === 0 ? "start" : v === 200 ? "end" : "middle"}">${v}${v === 200 ? "%+" : "%"}</text>`).join("");
      const ref = `<line x1="${X(100)}" x2="${X(100)}" y1="${T}" y2="${H - Bm}" style="stroke:var(--ink3);stroke-dasharray:3 3"/><text x="${X(100) + 5}" y="${T + 9}">payout = earnings</text>`;
      const dots = pts.map((f, i) => {
        const on = aheadSet.has(f.t), cx = X(f.po), cy = Y(f.y);
        const shape = f.po > XMAX ? `<path d="M${cx - 4},${cy - 4}L${cx + 3},${cy}L${cx - 4},${cy + 4}Z" style="fill:var(--dn)"/>` : `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${on ? 3.8 : 2.6}" style="fill:${on ? "var(--ink1)" : "none"};stroke:${on ? "var(--ink1)" : f.po > 100 ? "var(--dn)" : "var(--ink3)"};stroke-width:1.2"/>`;
        return `<g class="dv-pt" data-i="${i}">${shape}${f.t === current ? `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="7" style="fill:none;stroke:var(--ink1);stroke-width:1"/>` : ""}</g>`;
      }).join("");
      const lab = `<text x="${W - R}" y="${H - 3}" text-anchor="end">payout ratio (DPS ÷ EPS) →</text><text x="${L}" y="${H - 3}">↑ trailing yield</text>`;
      host.innerHTML = `<svg class="pf-hist" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" tabindex="0" role="img" aria-label="Trailing yield against payout ratio for ${POS.length} companies — arrow keys step through them, Enter opens history">${yt}${ref}${xt}${dots}${lab}<circle class="hl" r="6" style="fill:none;stroke:var(--today-focus);stroke-width:1.5;display:none"/></svg>`;
      const svg = host.firstChild, hl = svg.querySelector(".hl");
      let idx = -1;
      const show = (i, cx, cy) => {
        idx = Math.max(0, Math.min(pts.length - 1, i)); const f = pts[idx];
        hl.setAttribute("cx", X(f.po)); hl.setAttribute("cy", Y(f.y)); hl.style.display = "";
        const r = svg.getBoundingClientRect(), k = r.width / W;
        dvTipAt(cx ?? r.left + X(f.po) * k, cy ?? r.top + Y(f.y) * k, fTip(f).replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&amp;/g, "&"));
      };
      const near = e => { const r = svg.getBoundingClientRect(), x = (e.clientX - r.left) * W / r.width, y = (e.clientY - r.top) * W / r.width; let b = -1, bd = 196; pts.forEach((f, i) => { const d = (X(f.po) - x) ** 2 + (Y(f.y) - y) ** 2; if (d < bd) { bd = d; b = i; } }); return b; };
      svg.addEventListener("pointermove", e => { const b = near(e); if (b < 0) { hl.style.display = "none"; dvHideTip(); svg.style.cursor = ""; return; } svg.style.cursor = "pointer"; show(b, e.clientX, e.clientY); });
      svg.addEventListener("pointerleave", () => { hl.style.display = "none"; dvHideTip(); });
      svg.addEventListener("click", e => { const b = near(e); if (b >= 0) dvPick(pts[b].t, true); });
      svg.addEventListener("blur", () => { hl.style.display = "none"; dvHideTip(); });
      svg.addEventListener("keydown", e => {
        if (e.key === "ArrowRight" || e.key === "ArrowUp") show(idx + 1); else if (e.key === "ArrowLeft" || e.key === "ArrowDown") show(idx - 1);
        else if (e.key === "Enter" && idx >= 0) dvPick(pts[idx].t, true); else return;
        e.preventDefault();
      });
    };
    draw(); dvCharts.push({ host, draw });
  }
  const rankHTML = key => {
    const arr = (key === "y" ? FS.slice().sort((a, b) => b.y - a.y) : POS.slice().sort((a, b) => b.po - a.po));
    if (!arr.length) return `<p class="dv-cap">No companies with that figure right now.</p>`;
    const max = key === "y" ? arr[0].y : XMAX;
    const row = f => { const v = key === "y" ? f.y : f.po; return `<button type="button" class="dv-rr${aheadSet.has(f.t) ? " on" : ""}${key === "po" && f.po > 100 ? " over" : ""}" data-sym="${esc(f.t)}" data-tip="${fTip(f)}"><b>${esc(f.t)}</b><span class="pf-meter"><i style="width:${(Math.min(v, max) / max * 100).toFixed(1)}%"></i></span><em>${dvNum(v, key === "y" ? 2 : 1)}%</em><small>${key === "y" ? (f.po == null ? "payout unknown" : "payout " + dvNum(f.po, 0) + "%") : "yield " + dvNum(f.y) + "%"}</small></button>`; };
    return `<div class="dv-rk">${arr.slice(0, 15).map(row).join("")}</div>${arr.length > 15 ? `<details class="px-more"><summary><b>All ${arr.length}</b> by ${key === "y" ? "trailing yield" : "payout ratio"}</summary><div class="dv-rk">${arr.slice(15).map(row).join("")}</div></details>` : ""}`;
  };
  const ypBody = () => ypView === "map" ? '<div id="scat"></div>' : rankHTML(ypView);
  const yieldPayout = () => gated ? `<section class="px-ch" aria-labelledby="h-yp">
      ${dvSHead("h-yp", "Yield and payout", "How much each company pays against what it earns", "", `${FS.length} companies`)}
      ${planWall("The yield and payout map", "Trailing yield against payout ratio for every covered company, and the full ranked lists by yield and by payout — part of the paid plan.")}
    </section>` : `<section class="px-ch" aria-labelledby="h-yp">
    ${dvSHead("h-yp", "Yield and payout", "How much each company pays against what it earns", `Trailing yield is the vendor's 12-month dividend ÷ price. Payout ratio is dividend per share ÷ earnings per share × 100 — the same definition the desk's Rule 4 check uses — and is unknown when EPS is zero, negative or missing. Filled dots have a date ahead.`, `${FS.length} companies · fundamentals ${esc(dvFT(fund?.updated))}`)}
    <div class="sx-top"><p class="dv-lvl"><b>View</b></p><div class="wl-chips" id="ypChips" role="group" aria-label="Yield and payout view"><button type="button" data-v="map" aria-pressed="true">Map</button><button type="button" data-v="y" aria-pressed="false">By yield</button><button type="button" data-v="po" aria-pressed="false">By payout</button></div></div>
    <div class="dv-yp" id="ypBody">${ypBody()}</div>
    <div class="dv-notes">
      <div><small>PAID MORE THAN REPORTED EPS · ${OVER.length}</small>${OVER.map(f => `${dvLink(f.t)}<span class="mut">${dvNum(f.po, 0)}%</span>`).join(" ")}<br><span class="mut">Payout above 100% means the dividend exceeded trailing earnings in the vendor's window. It can come from one-off gains, reserves, or a timing gap between the two figures.</span></div>
      <div><small>PAYOUT UNKNOWN · ${NOPO.length}</small>${NOPO.map(f => dvLink(f.t)).join(" ")}<br><span class="mut">EPS is zero, negative or missing, so the ratio is not defined. They are not on the map.</span></div>
    </div>
  </section>`;

  // ================= company history =================
  function dvAnnualChart(host, sym) {
    const d = D_deep[sym];
    const draw = () => {
      const W = Math.max(260, host.clientWidth), H = W < 420 ? 190 : 220, L = 40, R = 8, T = 16, Bm = 22;
      if (!d) { host.innerHTML = `<p class="dv-cap">No payout history on record for ${esc(sym)} — ${dvUnk}.</p>`; return; }
      const y0 = d.a[0][0], y1 = Math.max(d.a.at(-1)[0], curYear), yrs = Array.from({ length: y1 - y0 + 1 }, (_, i) => y0 + i);
      const A = Object.fromEntries(d.a.map(r => [r[0], r]));
      const max = Math.max(...d.a.map(r => r[1])) * 1.1 || 1;
      const bw = (W - L - R) / yrs.length, X = i => L + i * bw, Y = v => T + (max - v) / max * (H - T - Bm);
      const g = [0, max / 2 / 1.1, max / 1.1].map(v => `<line class="grid" x1="${L}" x2="${W - R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}"/><text x="${L - 6}" y="${(Y(v) + 3).toFixed(1)}" text-anchor="end">${dvNum(v, v < 10 ? 1 : 0)}</text>`).join("");
      const step = yrs.length > 14 ? (W < 420 ? 5 : 3) : W < 420 ? 2 : 1;
      const bars = yrs.map((y, i) => {
        const r = A[y], part = y === curYear, h = r ? H - Bm - Y(r[1]) : 0;
        return `${r ? `<rect x="${(X(i) + bw * .18).toFixed(1)}" y="${Y(r[1]).toFixed(1)}" width="${(bw * .64).toFixed(1)}" height="${Math.max(1, h).toFixed(1)}" style="fill:${part ? "url(#dvHatch)" : "var(--ink2)"};stroke:${part ? "var(--ink2)" : "none"};stroke-width:1"/>` : `<line x1="${(X(i) + bw * .25).toFixed(1)}" x2="${(X(i) + bw * .75).toFixed(1)}" y1="${H - Bm}" y2="${H - Bm}" style="stroke:var(--ink3)"/>`}${(y - y0) % step === 0 || y === y1 ? `<text x="${(X(i) + bw / 2).toFixed(1)}" y="${H - 7}" text-anchor="middle">${W < 420 ? "'" + String(y).slice(2) : y}</text>` : ""}`;
      }).join("");
      host.innerHTML = `<svg class="pf-hist" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" tabindex="0" role="img" aria-label="${esc(sym)} cash dividends per share by calendar year, ${y0} to ${y1} — arrow keys step through years"><defs><pattern id="dvHatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="4" height="4" style="fill:var(--px-card)"/><line x1="0" y1="0" x2="0" y2="4" style="stroke:var(--ink3);stroke-width:1.5"/></pattern></defs><text x="${L}" y="9">Rs / share, by ex-date year</text>${g}${bars}<rect class="cross" y="${T}" height="${H - T - Bm}" width="${bw.toFixed(1)}" style="fill:var(--today-hover);stroke:none;display:none"/></svg>`;
      const svg = host.firstChild, cr = svg.querySelector(".cross");
      svg.insertBefore(cr, svg.querySelector("rect:not(pattern rect), line.grid"));
      let idx = yrs.length - 1;
      const show = (i, cx, cy) => {
        idx = Math.max(0, Math.min(yrs.length - 1, i)); const y = yrs[idx], r = A[y];
        cr.setAttribute("x", X(idx)); cr.style.display = "";
        const list = d.p.filter(pp => +pp[0].slice(0, 4) === y).map(pp => `${dvFD(pp[0])} · Rs ${dvNum(pp[1], 2)}`).join("<br>");
        const rb = svg.getBoundingClientRect(), k = rb.width / W;
        dvTipAt(cx ?? rb.left + (X(idx) + bw / 2) * k, cy ?? rb.top + T * k, `<b>${y}${y === curYear ? " · to date" : ""}</b><br>${r ? `Rs <b>${dvNum(r[1], 2)}</b> across ${r[2]} payout${r[2] > 1 ? "s" : ""}<br>${list}` : "No payout on record"}`);
      };
      const off = () => { cr.style.display = "none"; dvHideTip(); };
      svg.addEventListener("pointermove", e => { const rb = svg.getBoundingClientRect(), x = (e.clientX - rb.left) * W / rb.width; show(Math.floor((x - L) / bw), e.clientX, e.clientY); });
      svg.addEventListener("pointerleave", off); svg.addEventListener("blur", off);
      svg.addEventListener("keydown", e => { if (e.key === "ArrowLeft") show(idx - 1); else if (e.key === "ArrowRight") show(idx + 1); else if (e.key === "Home") show(0); else if (e.key === "End") show(yrs.length - 1); else return; e.preventDefault(); });
    };
    draw(); dvCharts.push({ host, draw });
  }
  const pickOpts = () => {
    const up = lanes.map(l => l.t).filter(t => D_deep[t] || F[t]);
    const rest = deepSyms.filter(t => !up.includes(t));
    const o = t => `<option value="${esc(t)}"${t === current ? " selected" : ""}>${esc(t)}${nm(t) ? " — " + esc(nm(t)).slice(0, 34) : ""}</option>`;
    return `<optgroup label="Date ahead">${up.map(o).join("")}</optgroup><optgroup label="All with payout history">${rest.map(o).join("")}</optgroup>`;
  };
  const histBody = sym => {
    const d = D_deep[sym], f = F[sym], l = byT[sym];
    const last = d?.p.at(-1);
    const full = d ? d.a.filter(r => r[0] < curYear) : [];
    const spanY = d ? curYear - d.a[0][0] : 0;
    const dps = history.filter(h => h.t === sym);
    const title = d ? `${d.n} cash payouts on record since ${d.a[0][0]}` : "no payout series on record";
    return `<div class="dv-chh"><b>${dvLink(sym)} <span style="font-weight:400;font-size:11px;color:var(--ink2)">${esc(nm(sym) || "")}</span></b><span>${esc(sec(sym) || "")}${l ? ` · date ahead: ${l.bc ? "closure " + dvFD(l.bc.date) : "ex " + dvFD(l.ex.date)}` : ""}</span></div>
      <p class="dv-cap" style="margin:0 0 10px">${title}. Split-adjusted Rs per share, grouped by ex-date year; the hatched bar is ${curYear} so far.</p>
      <div id="annual"></div>
      <div class="sx-kp">
        <div><small>LAST PAYOUT</small><b>${last ? "Rs " + dvNum(last[1]) : dvUnk}</b><span>${last ? "ex " + dvFDY(last[0]) : ""}</span></div>
        <div><small>YEARS WITH A PAYOUT</small><b>${d ? `${full.length}/${spanY}` : dvUnk}</b><span>${d ? `full years ${d.a[0][0]}–${curYear - 1}` : ""}</span></div>
        <div><small>TRAILING YIELD</small><b>${f?.y != null ? dvNum(f.y) + "%" : dvUnk}</b><span>vendor, 12 months</span></div>
        <div><small>PAYOUT RATIO</small><b class="${f?.po > 100 ? "dn" : ""}">${f?.po != null ? dvNum(f.po, 1) + "%" : dvUnk}</b><span>${f ? `DPS ${dvNum(f.dps)} ÷ EPS ${dvNum(f.eps)}` : "no fundamentals row"}</span></div>
      </div>
      <p class="sx-sub">Filings on DPS for ${esc(sym)} · ${dps.length}</p>
      ${dps.length ? `<div class="sx-scroll"><table class="sx-tbl"><thead><tr><th>Filed</th><th class="l">Announcement</th><th>Rs / share</th><th>Payout ÷ close</th><th>Book closure</th></tr></thead><tbody>${dps.map(h => `<tr><td>${dvAnnDate(h.announced) ? dvFDY(dvAnnDate(h.announced)) : dvUnk}</td><td class="l">${esc(h.ann || "")}<span class="dv-ann">${esc(dvAnnPlain(h))}</span></td><td>${h.rs != null ? dvNum(h.rs) : DV_KIND[h.kind] && h.kind !== "D" ? '<span class="mut">' + DV_KIND[h.kind] + "</span>" : dvUnk}</td><td>${h.yld != null ? dvNum(h.yld) + "%" : dvUnk}</td><td>${h.bc ? `${dvFD(h.bc)} → ${dvFD(h.end)}` : dvUnk}</td></tr>`).join("")}</tbody></table></div>` : `<p class="dv-cap" style="margin:0">None in the DPS window the data layer keeps.</p>`}
      ${d ? `<details class="px-more"><summary><b>Every payout on record</b> · ${d.n}</summary><div class="dv-pay">${d.p.slice().reverse().map(pp => `<span>${dvFDY(pp[0])} <b>${dvNum(pp[1])}</b></span>`).join("")}</div></details>` : ""}`;
  };
  const history_ = () => gated ? `<section class="px-ch" aria-labelledby="h-hist" id="histSec">
      ${dvSHead("h-hist", "Company history", "One company's payouts, year by year", "", `${deepSyms.length} companies`)}
      ${planWall("Every company's payout history", "Pick any covered company and see its cash dividends per share, year by year, back through the record — part of the paid plan.")}
    </section>` : `<section class="px-ch" aria-labelledby="h-hist" id="histSec">
    ${dvSHead("h-hist", "Company history", "One company's payouts, year by year", "Pick a company, or click one on the timeline or the yield map. Bars sum every cash payout by ex-date year; filings are the DPS book-closure announcements the desk has kept.", `${deep?.coverage_from ? "series from " + dvFD(deep.coverage_from.slice(0, 10)) : ""} · ${deepSyms.length} companies`)}
    <div class="sx-top"><p class="dv-lvl"><b>Company</b></p><select class="sx-pick" id="pick" aria-label="Company">${pickOpts()}</select></div>
    <div class="dv-ch" id="histBody">${histBody(current)}</div>
  </section>`;

  // ================= past payouts =================
  let pastKind = "all";
  const pastRow = h => `<tr><td>${dvLink(h.t)}</td><td class="l">${esc(h.ann || "")}<span class="dv-ann">${esc(dvAnnPlain(h))}</span></td><td>${h.rs != null ? dvNum(h.rs) : h.kind !== "D" ? '<span class="mut">' + (DV_KIND[h.kind] || "") + "</span>" : dvUnk}</td><td>${h.yld != null ? dvNum(h.yld) + "%" : dvUnk}</td><td>${dvAnnDate(h.announced) ? dvFDY(dvAnnDate(h.announced)) : dvUnk}</td><td>${h.bc ? `${dvFD(h.bc)} → ${dvFD(h.end)}` : dvUnk}</td></tr>`;
  const pastTable = () => {
    const rows = PAST.filter(h => pastKind === "all" || (pastKind === "F" ? h.per === "F" : pastKind === "I" ? /^I|V/.test(h.per || "") : h.kind !== "D"));
    const th = `<thead><tr><th>Company</th><th class="l">Announcement</th><th>Rs / share</th><th data-tip="This one payout ÷ the close in the latest snapshot — not the price at the time">Payout ÷<br>close now</th><th>Filed</th><th>Book closure</th></tr></thead>`;
    return `<div class="sx-scroll"><table class="sx-tbl">${th}<tbody>${rows.slice(0, 40).map(pastRow).join("")}</tbody></table></div>${rows.length > 40 ? `<details class="px-more"><summary><b>${rows.length - 40} more</b> filings</summary><div class="sx-scroll"><table class="sx-tbl">${th}<tbody>${rows.slice(40).map(pastRow).join("")}</tbody></table></div></details>` : ""}`;
  };
  const past_ = () => gated ? `<section class="px-ch" aria-labelledby="h-past">
      ${dvSHead("h-past", "Past payouts", "Closures already done, newest first", "", `${PAST.length} filings`)}
      ${planWall("Every past payout", "Every book closure the DPS scrape has kept, filterable by final, interim, or bonus/right — part of the paid plan.")}
    </section>` : `<section class="px-ch" aria-labelledby="h-past">
    ${dvSHead("h-past", "Past payouts", "Closures already done, newest first", "Every book closure the DPS scrape has kept. The yield column divides one payout by today's snapshot close, so it describes the payout against the current price, not the price when it was paid.", `${PAST.length} filings`)}
    <div class="sx-top"><p class="dv-lvl"><b>Show</b></p><div class="wl-chips" id="pastChips" role="group" aria-label="Filing type"><button type="button" data-k="all" aria-pressed="true">All</button><button type="button" data-k="F" aria-pressed="false">Final</button><button type="button" data-k="I" aria-pressed="false">Interim</button><button type="button" data-k="X" aria-pressed="false">Bonus / right</button></div></div>
    <div id="pastT" style="margin-top:10px">${pastTable()}</div>
  </section>`;

  // ================= method / sources footer =================
  const foot = () => `<div class="pf-foot">
    <p><b>Method.</b> Amounts are the announced percentage of face value${face != null ? ` (Rs ${dvNum(face, 0)}` : ""}${Object.keys(faceCal).length ? `; calibrated face for ${Object.keys(faceCal).join(", ")}` : ""}${face != null ? ")" : ""}. "Last cum session" is the data layer's own derivation: closure start − 3 calendar days for DPS rows, the business day before the ex-date for vendor rows; where the two differ both are shown and a weekend value is flagged. Payout ratio = DPS ÷ EPS × 100, undefined when EPS ≤ 0 — the definition scripts/check_rule4.py uses; ${mism.length} stored ratio${mism.length === 1 ? "" : "s"} in the snapshot didn't match a recomputation. Annual history sums split-adjusted cash events by ex-date year.</p>
    <p><b>Sources.</b> state/earnings_calendar.json (ex-dates · vendor; closures · DPS) · state/dividends.json (DPS filings, ${history.length} rows) · state/dividends_deep.json${deep?.source ? ` (${esc(deep.source)})` : ""} · state/fundamentals.json · state/universe.json · state/sectors.json.</p>
    <p><b>As of.</b> Calendar ${esc(dvFT(cal.updated))} · filings ${esc(dvFT(divs.updated))} · fundamentals ${esc(dvFT(fund?.updated))} · payout series ${deep?.updated ? dvFD(deep.updated.slice(0, 10)) : "unknown"}. Today ${dvFD(TODAY)}${staleDays != null ? ` — the snapshot is ${staleDays} day${staleDays === 1 ? "" : "s"} old` : ""}. A date or amount missing from the data layer is shown as unknown. Research, not advice. Past payouts say nothing certain about future ones; no income promises.</p>
  </div>`;

  // ================= wire up =================
  $("view").innerHTML = `<div class="today-page dv-page" id="dvPage">${hero()}${upcomingSection()}${yieldPayout()}${history_()}${past_()}${foot()}<div class="wl-tip" id="dvTip" role="tooltip"></div></div>`;
  const page = $("view").querySelector("#dvPage");
  const dvCharts = [];
  const tipEl = page.querySelector("#dvTip");
  function dvTipAt(x, y, html) { tipEl.innerHTML = html; tipEl.style.display = "block"; tipEl.style.left = Math.max(4, Math.min(x + 14, innerWidth - 290)) + "px"; tipEl.style.top = Math.min(y + 14, innerHeight - 60) + "px"; }
  function dvHideTip() { tipEl.style.display = "none"; }
  function dvLink(s) { return `<a href="#/ticker/${encodeURIComponent(s)}">${esc(s)}</a>`; }
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const onMove = e => { const el = e.target.closest?.("[data-tip]"); if (el && page.contains(el)) dvTipAt(e.clientX, e.clientY, el.dataset.tip); else if (!e.target.closest?.(".pf-hist")) dvHideTip(); };
  const onFocusIn = e => { const el = e.target.closest?.("[data-tip]"); if (el && page.contains(el)) { const r = el.getBoundingClientRect(); dvTipAt(r.left, r.bottom, el.dataset.tip); } };
  const onFocusOut = () => dvHideTip();
  const onKeydown = e => { if (e.key === "Escape") dvHideTip(); };
  const onScroll = () => dvHideTip();
  document.addEventListener("mousemove", onMove);
  document.addEventListener("focusin", onFocusIn);
  document.addEventListener("focusout", onFocusOut);
  document.addEventListener("keydown", onKeydown);
  addEventListener("scroll", onScroll, { passive: true });
  const cleanup = () => {
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("focusin", onFocusIn);
    document.removeEventListener("focusout", onFocusOut);
    document.removeEventListener("keydown", onKeydown);
    removeEventListener("scroll", onScroll);
    removeEventListener("resize", onResize);
  };
  new MutationObserver((_, obs) => { if (!document.body.contains(page)) { cleanup(); obs.disconnect(); } }).observe($("view").parentNode || document.body, { childList: true, subtree: true });

  function dvSetPressed(wrap, b) { wrap.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x === b)); }
  function dvSyncLanes() { page.querySelectorAll("button.dv-trk").forEach(b => b.setAttribute("aria-pressed", b.dataset.sym === current)); }
  function dvDrawYP() {
    for (let i = dvCharts.length - 1; i >= 0; i--) if (!dvCharts[i].host.isConnected) dvCharts.splice(i, 1);
    const ypBodyEl = page.querySelector("#ypBody");
    if (!ypBodyEl) return;
    ypBodyEl.innerHTML = ypBody();
    if (ypView === "map") dvScatter(page.querySelector("#scat"));
  }
  function dvPick(sym, scroll) {
    current = sym; dvHideTip();
    const sel = page.querySelector("#pick");
    if (sel) {
      if (![...sel.options].some(o => o.value === sym)) sel.insertAdjacentHTML("afterbegin", `<option value="${esc(sym)}">${esc(sym)}</option>`);
      sel.value = sym;
    }
    for (let i = dvCharts.length - 1; i >= 0; i--) if (!dvCharts[i].host.isConnected || dvCharts[i].host.id === "annual") dvCharts.splice(i, 1);
    const histBodyEl = page.querySelector("#histBody");
    if (histBodyEl) { histBodyEl.innerHTML = histBody(sym); dvAnnualChart(page.querySelector("#annual"), sym); }
    if (ypView === "map" && !gated) dvDrawYP();
    dvSyncLanes();
    if (scroll) page.querySelector("#histSec")?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  }
  page.addEventListener("click", e => {
    const t = e.target.closest("button.dv-trk, .dv-rr"); if (t) { dvPick(t.dataset.sym, true); return; }
    const yc = e.target.closest("#ypChips button"); if (yc) { ypView = yc.dataset.v; dvSetPressed(yc.parentNode, yc); dvDrawYP(); return; }
    const kc = e.target.closest("#pastChips button"); if (kc) { pastKind = kc.dataset.k; dvSetPressed(kc.parentNode, kc); page.querySelector("#pastT").innerHTML = pastTable(); }
  });
  page.addEventListener("change", e => { if (e.target.id === "pick") dvPick(e.target.value, false); });
  if (!gated) dvPick(current, false); else dvSyncLanes();

  let rt; const onResize = () => { clearTimeout(rt); rt = setTimeout(() => dvCharts.forEach(c => c.host.isConnected && c.draw()), 120); };
  addEventListener("resize", onResize);
}
