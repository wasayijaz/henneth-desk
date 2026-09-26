// news page — redesign 2026-09
// Behaviour parity source: old pageNews (app.js, removed here, kept in git history) — a flat
// impact-threshold + search wire. New visual structure ported FAITHFULLY from
// docs/redesign-mockups/news-mockup.html: same 5 sections, same SVG flow chart, same legend,
// same impact-scale reference list, same filter/feed/coverage layout, same class names (nw-*)
// under the codebase's own page-scoping convention.
//
// Real data only. docs/redesign-mockups/wl/news-data.js (window.NEWS) is a mockup-only sample
// shim and is NOT read — every derivation below is computed straight from state/newslog.json,
// state/sectors.json and state/universe.json via j(), the same way every other ported page does.
//
// Known data issue (desk rule): newslog.json is NOT stored in chronological order. Items are
// sorted descending by date+time below; bare-date items (no time component) sort by date only,
// they never inherit a fabricated time.
//
// The 1–5 impact scale is fixed by CLAUDE.md Rule 10 — hardcoded in NW_SCALE below because no
// state file carries the criteria text.
//
// MACRO is a pseudo-ticker, not a security: excluded from clickable ticker links everywhere,
// shown instead as a non-clickable "market-wide" badge (.nw-mac), exactly as the mockup does.
//
// Disclosed deviations from the mockup (behaviour-equivalent, not content changes):
//  1. Ticker links use the codebase's path router (navigate('/ticker/SYM')) instead of the
//     mockup's `href="#/ticker/SYM"` hash links — this app is path-routed, not hash-routed.
//  2. The tooltip is wired page-root-scoped (root-level mousemove/mouseleave on [data-tip],
//     a .wl-tip node inside the page root) instead of the mockup's document-level listeners —
//     matches every other ported page's tooltip convention; same visual tooltip either way.
//  3. Per-item source has one real field (n.source) — the mockup's srcN/src "raw source differs
//     from normalised name" tooltip case does not exist in state, so it never fires here.
//  4. Filters reset on every page visit (matches the mockup, which is a single-load page); the
//     OLD pageNews kept its filter in a module-level variable across navigations — that
//     persistence is not reproduced.
//  5. The hero right-label is a static "data health · see Today" pointer, not a live read of
//     state/health.json — Rule 6 health gating is already surfaced on the Today page; this page
//     does not duplicate that fetch/derivation, it just signposts where to check it.
//
// No advice language. No desk calls or targets on named securities.

const NW_MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const NW_NAME = { 1: "Routine", 2: "Minor", 3: "Notable", 4: "Material", 5: "Severe" };
const NW_SCALE = {
  1: "Routine or administrative — no market read.",
  2: "Minor company item.",
  3: "Notable — results date, management change, or sector news.",
  4: "Material — earnings surprise, regulatory action, major contract, index reconstitution, or a sharp commodity/FX move.",
  5: "Severe — default, trading halt, fraud, war, or macro shock.",
};
const NW_UNK = '<span class="nw-unk">unknown</span>';
const NW_CLAMP = 260;
const NW_LEVELS = [1, 2, 3, 4, 5];

function nwFD(d) {
  if (!d) return "unknown";
  const t = new Date(d + "T00:00:00");
  if (isNaN(t)) return String(d);
  return `${String(t.getDate()).padStart(2, "0")} ${NW_MON[t.getMonth()]}`;
}
function nwDaysBetween(a, b) { return Math.round((new Date(b + "T00:00:00") - new Date(a + "T00:00:00")) / 86400000); }
function nwCut(dateStr, days) { const t = new Date(dateStr + "T00:00:00"); t.setDate(t.getDate() - days); return t.toISOString().slice(0, 10); }
function nwClamp(s) {
  s = s || "";
  if (s.length <= NW_CLAMP) return { short: s, clamped: false };
  let cut = s.slice(0, NW_CLAMP);
  const sp = cut.lastIndexOf(" ");
  if (sp > 40) cut = cut.slice(0, sp);
  return { short: cut + "…", clamped: true };
}
function nwHost(u) {
  if (!u) return null;
  try { const h = new URL(u).hostname.replace(/^www\./, ""); return h || null; } catch { return null; }
}
function nwChip(l) {
  const name = NW_NAME[l] || "unknown";
  const crit = NW_SCALE[l] || "";
  return `<span class="nw-imp l${l}" data-tip="${esc(`Impact ${l} · ${name} — ${crit}`)}">${l}</span>`;
}
function nwTlink(sym) {
  return `<span class="clickable" style="cursor:pointer" onclick="navigate('/ticker/${encodeURIComponent(sym)}')">${esc(sym)}</span>`;
}
function nwPct(a, b) { return b ? Math.round((a / b) * 100) + "%" : "—"; }

function nwSectionHead(kick, title, what, right) {
  return `<div class="sx-hd">
    <div><span class="sx-k">${esc(kick)}</span><h2>${title}</h2>${what ? `<p class="sx-ld">${what}</p>` : ""}</div>
    ${right ? `<div class="sx-hr">${right}</div>` : ""}
  </div>`;
}

// stacked-bar SVG flow chart — one bar per calendar day from FIRST to LAST, segments coloured
// by impact level, 3 horizontal grid lines (0 / half-max / max), day labels on the 1st/15th.
function nwDrawFlow(host, days, dayCounts) {
  function draw() {
    if (!host.isConnected) { window.removeEventListener("resize", draw); return; }
    const w = Math.max(240, host.clientWidth || 600);
    const h = 120, padL = 28, padB = 16, padT = 6;
    const plotW = w - padL - 6, plotH = h - padT - padB;
    const n = days.length || 1;
    const bw = Math.max(1, plotW / n);
    const max = Math.max(1, ...days.map(d => NW_LEVELS.reduce((s, l) => s + (dayCounts[d][l] || 0), 0)));
    const y = v => padT + plotH - (v / max) * plotH;
    let bars = "";
    days.forEach((d, i) => {
      const x = padL + i * bw;
      let acc = 0, rects = "";
      for (const l of NW_LEVELS) {
        const v = dayCounts[d][l] || 0;
        if (!v) continue;
        const y0 = y(acc), y1 = y(acc + v);
        rects += `<rect class="s l${l}" x="${x}" y="${y1}" width="${Math.max(0.6, bw - 0.6)}" height="${Math.max(0, y0 - y1)}"></rect>`;
        acc += v;
      }
      const total = acc;
      bars += `<g data-tip="${esc(`${nwFD(d)}: ${total} item${total === 1 ? "" : "s"}`)}">
        <rect class="hit" x="${x}" y="${padT}" width="${Math.max(1, bw)}" height="${plotH}"></rect>
        ${rects}
      </g>`;
    });
    let dayLabels = "";
    days.forEach((d, i) => {
      const dom = +d.slice(8, 10);
      if (dom === 1 || dom === 15) dayLabels += `<text x="${padL + i * bw}" y="${h - 3}">${nwFD(d)}</text>`;
    });
    const grid = [0, 0.5, 1].map(f => {
      const yy = padT + plotH - f * plotH;
      return `<line class="grid" x1="${padL}" x2="${w - 6}" y1="${yy}" y2="${yy}"></line><text x="2" y="${yy + 3}">${Math.round(max * f)}</text>`;
    }).join("");
    host.innerHTML = `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">${grid}${bars}${dayLabels}</svg>`;
  }
  draw();
  window.addEventListener("resize", draw);
}

async function pageNews() {
  const view = $("view");
  const [rawNews, sectors, universe] = await Promise.all([j("newslog.json"), j("sectors.json"), j("universe.json")]);
  const raw = Array.isArray(rawNews) ? rawNews : [];

  if (!raw.length) {
    view.innerHTML = `<div class="today-page nw-page">
      <div class="sx-hd"><div><span class="sx-k">News wire</span><h2>No items logged yet</h2></div></div>
      <div class="nw-empty">Wire silent — sentinel runs every cycle during market hours.</div>
    </div>`;
    return;
  }

  const sectorOf = {}; const sectorName = {};
  for (const [sym, v] of Object.entries(sectors?.tickers || {})) sectorOf[sym] = v?.sector || null;
  for (const [code, nm] of Object.entries(sectors?.codes || {})) sectorName[code] = nm;
  const nameOf = {};
  for (const [sym, v] of Object.entries(universe?.symbols || {})) nameOf[sym] = v?.name || "";

  // out-of-order count in the RAW log, before our own sort — cited in the footer
  let inversions = 0;
  for (let i = 1; i < raw.length; i++) if ((raw[i].ts || "") < (raw[i - 1].ts || "")) inversions++;

  const items = raw.map((it, i) => {
    const ts = String(it.ts || "");
    const hasTime = ts.length > 10;
    return {
      i,
      d: hasTime ? ts.slice(0, 10) : ts,
      t: hasTime ? ts.slice(11, 16) : null,
      tk: Array.isArray(it.tickers) ? it.tickers : [],
      imp: it.impact || 0,
      h: it.headline || "", h_ur: it.headline_ur || "",
      s: it.summary || "", s_ur: it.summary_ur || "",
      src: it.source || "", url: it.url || "",
    };
  }).sort((a, b) => {
    if (a.d !== b.d) return a.d < b.d ? 1 : -1;
    const at = a.t || "", bt = b.t || "";
    if (at !== bt) return at < bt ? 1 : -1;
    return 0;
  });

  const n = items.length;
  const LAST = items[0].d, FIRST = items[n - 1].d;
  const nTimed = items.filter(it => it.t).length;

  const counts = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
  for (const it of items) if (counts[it.imp] != null) counts[it.imp]++;
  const maxCount = Math.max(1, ...NW_LEVELS.map(l => counts[l]));

  const c30 = nwCut(LAST, 30);
  const in30 = items.filter(it => it.d > c30 && it.d <= LAST);
  const hi30 = in30.filter(it => it.imp >= 4).length;
  const sev30 = in30.filter(it => it.imp === 5).length;

  const w0 = nwCut(LAST, 7), w1 = nwCut(LAST, 14);
  const thisWeek = items.filter(it => it.d > w0 && it.d <= LAST).length;
  const prevWeek = items.filter(it => it.d > w1 && it.d <= w0).length;
  const wowTxt = prevWeek ? `${thisWeek >= prevWeek ? "+" : ""}${thisWeek - prevWeek} vs prior 7d` : "no prior-week baseline";

  const hiAll = items.filter(it => it.imp >= 4).length;

  const tkCount = {}, tkImp = {};
  let macroCount = 0;
  for (const it of items) {
    for (const t of it.tk) {
      if (t === "MACRO") { macroCount++; continue; }
      tkCount[t] = (tkCount[t] || 0) + 1;
      (tkImp[t] = tkImp[t] || { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 })[it.imp]++;
    }
  }
  const topTk = Object.entries(tkCount).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 15);

  const secCount = {}, secImp = {};
  for (const it of items) {
    const secs = new Set();
    for (const t of it.tk) { if (t === "MACRO") continue; const s = sectorOf[t]; if (s) secs.add(s); }
    for (const s of secs) {
      secCount[s] = (secCount[s] || 0) + 1;
      (secImp[s] = secImp[s] || { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 })[it.imp]++;
    }
  }
  const secRows = Object.entries(secCount).sort((a, b) => b[1] - a[1]);
  const topTkAll = Math.max(1, ...topTk.map(([, c]) => c));
  const topSecAll = Math.max(1, macroCount, ...secRows.map(([, c]) => c));

  const isTk = q => q === "MACRO" || nameOf[q] !== undefined || tkCount[q] != null;

  // day-by-day stacked counts, FIRST..LAST inclusive, for the flow chart
  const days = []; const dayCounts = {};
  { let d = FIRST; let guard = 0; while (d <= LAST && guard++ < 5000) { days.push(d); dayCounts[d] = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 }; d = new Date(new Date(d + "T00:00:00Z").getTime() + 86400000).toISOString().slice(0, 10); } }
  for (const it of items) if (dayCounts[it.d]) dayCounts[it.d][it.imp]++;

  const row = (it, withDate) => {
    const tks = it.tk.filter(t => t !== "MACRO");
    const isMacro = it.tk.includes("MACRO");
    const { short, clamped } = nwClamp(it.s);
    const host = nwHost(it.url);
    return `<div class="nw-it l${it.imp}${it.imp >= 4 ? " hi" : ""}">
      <div class="tm">${withDate ? esc(nwFD(it.d)) + " " : ""}${it.t ? esc(it.t) + " PKT" : NW_UNK}</div>
      ${nwChip(it.imp)}
      <div>
        <h3>${esc(it.h)}</h3>
        ${it.h_ur ? `<h3 class="nw-ur" dir="rtl">${esc(it.h_ur)}</h3>` : ""}
        <p data-i="${it.i}">${esc(short)}${clamped ? ` <button type="button" class="nw-rd" data-i="${it.i}">read all</button>` : ""}</p>
        ${it.s_ur ? `<p class="nw-ur" dir="rtl">${esc(it.s_ur)}</p>` : ""}
        <div class="nw-meta">
          <span>${it.src ? esc(it.src) : "source unknown"}</span>
          ${host ? `${externalLink(it.url, esc(host), 'style="color:var(--accent)"')}` : ""}
          <span class="nw-tk">${tks.map(nwTlink).join(" ")}</span>
          ${isMacro ? '<span class="nw-mac">market-wide</span>' : ""}
        </div>
      </div>
    </div>`;
  };

  const latestSevere = items.filter(it => it.imp >= 4).slice(0, 6);

  const scaleList = NW_LEVELS.map(l => `<li class="l${l}">
    ${nwChip(l)}
    <b>${NW_NAME[l]}</b>
    <span>${NW_SCALE[l]}</span>
    <span class="bar"><i style="width:${nwPct(counts[l], maxCount).replace("—", "0%")}"><s></s></i></span>
  </li>`).join("");

  view.innerHTML = `<div class="today-page nw-page">
    <section class="nw-sec nw-hero">
      ${nwSectionHead("News wire · " + nwFD(FIRST) + " → " + nwFD(LAST) + " · " + n + " items",
        `${hi30} material/severe item${hi30 === 1 ? "" : "s"} in the last 30 sessions' calendar window`,
        `The desk's fixed 1–5 impact scale. Any item tagged ≥4 re-triggers the full research pipeline the same cycle.`,
        `<span class="nw-lvl">data health · see Today</span>`)}
      <div class="nw-flow" id="nwFlow"></div>
      <div class="nw-key">${NW_LEVELS.map(l => `<span class="l${l}"><i></i>${l} ${NW_NAME[l]}</span>`).join("")}</div>
      <div class="sx-kp">
        <div data-tip="total items in the permanent log"><b>${n}</b><span>Logged</span></div>
        <div data-tip="impact 4 or 5, all-time"><b>${hiAll}</b><span>Material + severe</span><i>${sev30} severe in 30d</i></div>
        <div data-tip="${esc(wowTxt)}"><b>${thisWeek}</b><span>Last 7 days</span></div>
        <div data-tip="most tagged ticker in the log"><b>${topTk[0] ? esc(topTk[0][0]) : "—"}</b><span>Most tagged</span><i>${topTk[0] ? topTk[0][1] + " items" : ""}</i></div>
      </div>
      <div class="nw-top"><span class="nw-sub">Latest material &amp; severe</span></div>
      <div class="nw-list">${latestSevere.length ? latestSevere.map(it => row(it, true)).join("") : '<div class="nw-empty">Nothing tagged ≥4 yet.</div>'}</div>
    </section>

    <section class="nw-sec">
      ${nwSectionHead("Reference", "The impact scale", "Fixed by desk rule — Sentinel applies these criteria on every item; drift here silently changes how often the full pipeline re-triggers.")}
      <ol class="nw-scale">${scaleList}</ol>
    </section>

    <section class="nw-sec" id="wire">
      ${nwSectionHead("The wire", "Every item, newest first", "Sorted by the desk, not by the source — the raw log is not chronological.")}
      <div class="nw-fil">
        <div class="wl-chips" id="nwImp">
          ${[[1, "all"], [2, "≥2"], [3, "≥3"], [4, "≥4"], [5, "5"]].map(([v, lbl]) => `<button type="button" data-imp="${v}" aria-pressed="${v === 1 ? "true" : "false"}">${lbl}</button>`).join("")}
        </div>
        <label>Sector <select id="nwSec">
          <option value="">All sectors</option>
          <option value="__MACRO">Market-wide (${macroCount})</option>
          ${secRows.map(([code, c]) => `<option value="${esc(code)}">${esc(sectorName[code] || code)} (${c})</option>`).join("")}
        </select></label>
        <input id="nwQ" type="search" inputmode="search" enterkeyhint="search" placeholder="filter ticker or text">
      </div>
      <div class="nw-count" id="nwCount"></div>
      <div id="feed"></div>
    </section>

    <section class="nw-sec">
      ${nwSectionHead("Coverage", "Where the wire has been looking", "Counts across the full log, not just the current filter.")}
      <div class="nw-two">
        <div>
          <h3>Top tickers</h3>
          <ul class="nw-rank">${topTk.map(([sym, c]) => `<li>
            <span class="nm">${esc(sym)}<span class="sub">${esc(nameOf[sym] || "unknown")}</span></span>
            <span class="bar">${NW_LEVELS.filter(l => tkImp[sym]?.[l]).map(l => `<i class="l${l}" style="flex:${tkImp[sym][l]}"></i>`).join("")}</span>
            <button type="button" data-tk="${esc(sym)}"><b>${c}</b></button>
          </li>`).join("") || '<div class="nw-empty">No tickers tagged yet.</div>'}</ul>
        </div>
        <div>
          <h3>Sectors</h3>
          <ul class="nw-rank">
            ${macroCount ? `<li><span class="nm">Market-wide<span class="sub">MACRO-tagged items</span></span><span class="bar"><i class="l3" style="flex:1"></i></span><button type="button" data-sec="__MACRO"><b>${macroCount}</b></button></li>` : ""}
            ${secRows.map(([code, c]) => `<li>
              <span class="nm">${esc(sectorName[code] || code)}<span class="sub">${esc(code)}</span></span>
              <span class="bar">${NW_LEVELS.filter(l => secImp[code]?.[l]).map(l => `<i class="l${l}" style="flex:${secImp[code][l]}"></i>`).join("")}</span>
              <button type="button" data-sec="${esc(code)}"><b>${c}</b></button>
            </li>`).join("")}
          </ul>
        </div>
      </div>
    </section>

    <footer class="pf-foot">
      <p>Nothing is ever deleted from this wire — it is the desk's permanent memory, not a live feed. This is research, not advice: no item here is a recommendation to buy or sell anything.</p>
      <p>Source: state/newslog.json (${n} items, ${nwFD(FIRST)} → ${nwFD(LAST)}), state/sectors.json (updated ${esc(sectors?.updated || "unknown")}), state/universe.json (updated ${esc(universe?.updated || "unknown")}). ${inversions} out-of-order entr${inversions === 1 ? "y" : "ies"} in the raw log, resolved by sorting here. ${nTimed} of ${n} items carry a logged time; the rest show as ${NW_UNK} and sort by date only.</p>
      <p>Summaries are clamped at ${NW_CLAMP} characters with a "read all" toggle. Urdu text renders only where state carries a <code>_ur</code> sibling field for that item — none does in the current snapshot.</p>
    </footer>
    <div class="wl-tip" aria-hidden="true"></div>
  </div>`;

  const root = view.firstElementChild;
  nwDrawFlow(root.querySelector("#nwFlow"), days, dayCounts);

  // tooltip — page-root-scoped, matches every other ported page's convention
  const tip = () => root.querySelector(".wl-tip");
  const showTip = (e, html) => { const t = tip(); if (!t) return; t.innerHTML = html; t.style.display = "block"; t.style.left = Math.max(8, Math.min(e.clientX + 14, innerWidth - 290)) + "px"; t.style.top = (e.clientY + 14) + "px"; };
  const hideTip = () => { const t = tip(); if (t) t.style.display = "none"; };
  root.addEventListener("mousemove", e => { const t = e.target.closest("[data-tip]"); if (t) { showTip(e, esc(t.dataset.tip)); return; } hideTip(); });
  root.addEventListener("mouseleave", hideTip);

  // filter/feed — partial swap of #feed/#nwCount only, matching the mockup's own renderFeed()
  const F = { imp: 1, sec: "", q: "" };
  let limit = 80;
  const expanded = new Set();
  const feedEl = root.querySelector("#feed");
  const countEl = root.querySelector("#nwCount");

  function match(it) {
    if (it.imp < F.imp) return false;
    if (F.sec === "__MACRO") { if (!it.tk.includes("MACRO")) return false; }
    else if (F.sec) { if (!it.tk.some(t => sectorOf[t] === F.sec)) return false; }
    if (F.q) {
      if (isTk(F.q)) { if (!it.tk.includes(F.q)) return false; }
      else {
        const hay = (it.h + " " + it.s).toUpperCase();
        if (!hay.includes(F.q) && !it.tk.some(t => t.startsWith(F.q))) return false;
      }
    }
    return true;
  }

  function renderFeed() {
    const filtered = items.filter(match);
    const active = F.imp !== 1 || F.sec || F.q;
    countEl.innerHTML = `<span>${filtered.length} item${filtered.length === 1 ? "" : "s"}</span>${active ? ' <button type="button" id="nwClr">clear filters</button>' : ""}`;
    const slice = filtered.slice(0, limit);
    let html = "";
    let curDay = null;
    for (const it of slice) {
      if (it.d !== curDay) { curDay = it.d; html += `<div class="nw-day">${esc(nwFD(it.d))} · ${it.d === LAST ? "latest session" : ""}</div>`; }
      html += row(it, false).replace('<p data-i="', expanded.has(it.i) ? `<p data-i="` : '<p data-i="');
      if (expanded.has(it.i)) html = html.replace(`data-i="${it.i}">${esc(nwClamp(it.s).short)}`, `data-i="${it.i}">${esc(it.s)}`).replace(`read all</button>`, `less</button>`);
    }
    feedEl.innerHTML = html || '<div class="nw-empty">No items match the current filter.</div>';
    if (filtered.length > limit) feedEl.insertAdjacentHTML("beforeend", `<button type="button" class="nw-more">Show more (${filtered.length - limit} left)</button>`);
  }
  renderFeed();

  root.querySelector("#nwImp").addEventListener("click", e => {
    const b = e.target.closest("button[data-imp]"); if (!b) return;
    F.imp = +b.dataset.imp;
    root.querySelectorAll("#nwImp button").forEach(x => x.setAttribute("aria-pressed", x === b ? "true" : "false"));
    limit = 80; renderFeed();
  });
  root.querySelector("#nwSec").addEventListener("change", e => { F.sec = e.target.value; limit = 80; renderFeed(); });
  let qDebounce;
  root.querySelector("#nwQ").addEventListener("input", e => {
    clearTimeout(qDebounce);
    const v = e.target.value.trim().toUpperCase();
    qDebounce = setTimeout(() => { F.q = v; limit = 80; renderFeed(); }, 120);
  });

  root.addEventListener("click", e => {
    if (e.target.id === "nwClr") {
      F.imp = 1; F.sec = ""; F.q = "";
      root.querySelector("#nwSec").value = ""; root.querySelector("#nwQ").value = "";
      root.querySelectorAll("#nwImp button").forEach(x => x.setAttribute("aria-pressed", x.dataset.imp === "1" ? "true" : "false"));
      limit = 80; renderFeed(); return;
    }
    if (e.target.classList.contains("nw-more")) { limit += 80; renderFeed(); return; }
    if (e.target.classList.contains("nw-rd")) {
      const i = +e.target.dataset.i;
      if (expanded.has(i)) expanded.delete(i); else expanded.add(i);
      renderFeed(); return;
    }
    const tkBtn = e.target.closest("button[data-tk]");
    if (tkBtn) {
      F.imp = 1; F.q = tkBtn.dataset.tk;
      root.querySelectorAll("#nwImp button").forEach(x => x.setAttribute("aria-pressed", x.dataset.imp === "1" ? "true" : "false"));
      root.querySelector("#nwQ").value = tkBtn.dataset.tk;
      limit = 80; renderFeed();
      root.querySelector("#wire")?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    const secBtn = e.target.closest("button[data-sec]");
    if (secBtn) {
      F.imp = 1; F.sec = secBtn.dataset.sec;
      root.querySelectorAll("#nwImp button").forEach(x => x.setAttribute("aria-pressed", x.dataset.imp === "1" ? "true" : "false"));
      root.querySelector("#nwSec").value = secBtn.dataset.sec;
      limit = 80; renderFeed();
      root.querySelector("#wire")?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
  });
}
