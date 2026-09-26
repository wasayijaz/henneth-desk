// macro page — redesign 2026-09, rebuild 2 (owner rejected first port: sections didn't match the
// approved mockup). Ported to the mockup's actual 4 chapters (docs/redesign-mockups/macro-mockup.html):
// "01 The regime at a glance" (~589), "02 The drivers board" (~621), "03 How the regime shifted"
// (~639), "04 What moves each sector" (~667). FACTOR_LABEL / FACTOR_PLAIN / sectorDriverLine stay
// in app.js — other pages (ticker detail, screener drill-in) still call them, so they are not
// page-local; not redeclared here.
//
// Real data only, from state/ via j(): global.json, macro.json, georisk.json, sector_macro.json,
// macro_history.json (factor series for sparklines / us10y / em_equity). Chapter 03 needs a
// regime-history series, a geo-risk-history series and a KSE-100 price history to draw the
// mockup's flip log / interactive timeline — none of those state/ files exist (no regime_hist.json,
// no geo_hist.json, no daily KSE-100 series), so chapter 03 says exactly that instead of inventing
// a flip log; it still renders what real data supports, the sheet's own forward-looking event list.
// Display fixes kept: US 10y is macro_history.json's `us10y` series as-is (already a plain
// percentage, no re-scaling); next_events filtered to future-only and de-duped by date+event;
// sector_tilt labelled "Macro tailwind" / "Macro headwind" (never "Favored"/"Avoid"); every mockup
// `mc-` class renamed `mac-` (the bare `mc-` prefix is load-bearing sitewide for an unrelated
// paywall/tease widget — themes.css ~866-1133, pages-workspace.css). No advice language: "the
// setup"/"the desk's read", never "you should buy". Missing/unavailable data renders as "unknown",
// with the reason named.

function macPct(v, d = 1) { return v == null || !isFinite(v) ? "unknown" : Number(v).toFixed(d) + "%"; }
function macNum(v, d = 2) { return v == null || !isFinite(v) ? "unknown" : Number(v).toFixed(d); }

// same driver-string convention as macro.json: prose, optionally ending "Source: <url> ...".
function macDrivers(list) {
  return (list || []).map(s => {
    const i = String(s).search(/Sources?:/);
    const urls = (String(s).match(/https?:\/\/[^\s]+/g) || []).map(u => u.replace(/[.,;)]+$/, ""));
    return { text: i >= 0 ? String(s).slice(0, i).trim() : String(s), urls };
  });
}
function macSrcLinks(d) {
  return d.urls.map(u => { let h = u; try { h = new URL(u).hostname.replace(/^www\./, ""); } catch (e) {} return `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(h)}</a>`; }).join(" ");
}

// filter past next_events and de-dupe same date+text pairs (today is a real wall-clock date, not
// state — read from the browser, PKT-ish is close enough for a date-only compare).
function macFutureEvents(list) {
  const today = new Date().toISOString().slice(0, 10);
  const seen = new Set(), out = [];
  for (const e of list || []) {
    const key = `${e.date}|${e.event}`;
    if (e.date < today || seen.has(key)) continue;
    seen.add(key); out.push(e);
  }
  return out.sort((a, b) => a.date.localeCompare(b.date));
}

// simple static sparkline — no pointer/crosshair interaction (the mockup's lineChart() is
// interactive SVG driven by pointer/keyboard events; too heavy to port blind, and a plain trend
// line carries the same information for this page's purpose).
function macSpark(vs) {
  if (!vs || vs.length < 2) return "";
  const lo = Math.min(...vs), hi = Math.max(...vs), span = hi - lo || 1;
  const pts = vs.map((v, i) => `${(i / (vs.length - 1) * 100).toFixed(2)},${(23 - (v - lo) / span * 23).toFixed(2)}`).join(" ");
  const up = vs[vs.length - 1] >= vs[0];
  return `<svg class="mac-spark ${up ? "up" : "dn"}" viewBox="0 0 100 26" preserveAspectRatio="none" aria-hidden="true"><polyline points="${pts}"></polyline></svg>`;
}

// chapter header — numbered, titled, with a one-line "why" and an as-of tag naming the source.
function macChapterHead(n, title, why, tag) {
  return `<div class="mac-chh"><span class="mac-chn">${esc(n)}</span><div><h2 class="mac-cht">${esc(title)}</h2><p class="mac-chw">${esc(why)}</p></div><span class="mac-chtag">${esc(tag)}</span></div>`;
}

const MAC_SYM2FACTOR = { "CL=F": "oil", "BZ=F": "oil", "GC=F": "gold", "PKR=X": "usdpkr", "^GSPC": "sp500", "DX-Y.NYB": "dollar" };
const MAC_TIER1 = [["fx", "Currency", "the biggest macro lever for PSX"], ["energy", "Energy", "the import bill, PKR and inflation"]];
const MAC_TIER3 = [
  ["risk", "Global risk appetite", "frontier flows follow"],
  ["crypto", "Crypto", "global liquidity / retail risk barometer"],
  ["safe_haven", "Safe haven", "the hedge bid"],
];
const MAC_CHIPS = [["all", "All"], ["fx", "Currency"], ["energy", "Energy"], ["geo", "Geo"], ["home", "Pakistan"], ["risk", "Risk"], ["crypto", "Crypto"], ["safe_haven", "Safe haven"], ["test", "Test only"]];

async function pageMacro() {
  const [gl, macro, geo, sm, hist] = await Promise.all([
    j("global.json"), j("macro.json"), j("georisk.json"), j("sector_macro.json"), j("macro_history.json"),
  ]);
  const inst = gl?.instruments || {};
  const m = macro || {};
  const dom = m.domestic || {};
  const regime = (m.regime || "").toLowerCase().replace(/[^a-z]/g, "");
  const regimeTone = regime === "riskon" ? "up" : regime === "riskoff" ? "dn" : "mut";
  const RL = { riskon: "RISK-ON", neutral: "NEUTRAL", riskoff: "RISK-OFF" };

  const factorSeries = (() => {
    const out = {};
    for (const [k, rec] of Object.entries(hist?.factors || {})) {
      const dates = Object.keys(rec.series || {}).sort();
      out[k] = dates.map(d => rec.series[d]);
    }
    return out;
  })();
  const us10ySeries = factorSeries.us10y || [];
  const us10yLast = us10ySeries.length ? us10ySeries[us10ySeries.length - 1] : null;
  const emEqSeries = factorSeries.em_equity || [];
  const emEqLast = emEqSeries.length ? emEqSeries[emEqSeries.length - 1] : null;

  const drivers = macDrivers(m.drivers);
  const events = macFutureEvents(m.next_events);
  const tilt = m.sector_tilt || {};
  const usd = inst["PKR=X"], brent = inst["BZ=F"];
  const mpc = events.find(e => /mpc|monetary policy|policy rate/i.test(e.event));

  /* ================= 01 — The regime at a glance ================= */
  const scale = `<div class="mac-scale" role="img" aria-label="Regime scale: ${esc(RL[regime] || m.regime || "unknown")}">${["riskon", "neutral", "riskoff"].map(r => `<span class="${r === regime ? "on " + (r === "riskon" ? "up" : r === "riskoff" ? "dn" : "mut") : ""}">${RL[r]}</span>`).join("")}</div>`;

  const ch01 = `<section class="mac-ch">
    ${macChapterHead("01", "The regime at a glance", "Whether the macro backdrop is a tailwind or a headwind for PSX right now, and the four numbers carrying it.", `regime sheet ${esc(m.updated || "unknown")}`)}
    <div class="mac-verdict ${regimeTone}">
      <div class="mac-vh"><span class="mac-badge ${regimeTone}">${esc(RL[regime] || (m.regime || "unknown").toUpperCase())}</span><b>Macro regime</b></div>
      ${scale}
      <p class="mac-vp">${esc(m.global_read || "unknown")}</p>
      <div class="mac-vmeta">written ${esc(m.updated || "unknown")}${geo ? ` · geo-risk ${esc(String(geo.score))}/100 (${esc(geo.band || "unknown")})` : ""}</div>
    </div>
    <div class="mac-strip">
      <div><small>USD/PKR · the biggest lever</small><b>${usd ? esc(fmt(usd.price)) : "unknown"}</b><span>${usd ? `<em class="${cls(usd.chg_1d_pct)}">${sgn(usd.chg_1d_pct)}%</em> 1d · <em class="${cls(usd.chg_1mo_pct)}">${sgn(usd.chg_1mo_pct)}%</em> 1mo` : "unknown"}</span></div>
      <div><small>BRENT · the import bill</small><b>${brent ? "$" + esc(fmt(brent.price)) : "unknown"}</b><span>${brent ? `<em class="${cls(brent.chg_1d_pct)}">${sgn(brent.chg_1d_pct)}%</em> 1d · <em class="${cls(brent.chg_1mo_pct)}">${sgn(brent.chg_1mo_pct)}%</em> 1mo` : "unknown"}</span></div>
      <div><small>GEO RISK · desk composite</small><b class="${geo ? (geo.band === "elevated" ? "dn" : geo.band === "calm" ? "up" : "mut") : ""}">${geo ? esc(String(geo.score)) : "unknown"}${geo ? '<span class="mac-mut">/100</span>' : ""}</b><span>${geo ? `${esc(geo.band || "unknown")} · ${esc(geo.updated || "unknown")}` : "unknown"}</span></div>
      <div><small>SBP POLICY RATE</small><b>${m.sbp_rate != null ? macPct(m.sbp_rate) : "unknown"}</b><span>${mpc ? `next MPC ${esc(mpc.date)}` : "next MPC unknown"}</span></div>
    </div>
    <div class="mac-quiet">
      <details class="mac-more"><summary>What moved the last flip</summary>
        <div class="mac-flip"><p class="mac-unk">unknown — no regime-history file (state/regime_hist.json does not exist)</p><p class="mut">The sheet keeps the current regime, not a change log. The drivers below are the current reasoning.</p></div>
      </details>
      <details class="mac-more"><summary>The ${drivers.length} drivers behind the read, with sources</summary>
        <ol class="mac-drv-list">${drivers.map(d => `<li>${esc(d.text)}${d.urls.length ? `<br>${macSrcLinks(d)}` : ""}</li>`).join("")}</ol>
      </details>
    </div>
  </section>`;

  /* ================= 02 — The drivers board ================= */
  const tile = ([sym, v]) => {
    const fk = MAC_SYM2FACTOR[sym];
    const spark = fk && factorSeries[fk] ? macSpark(factorSeries[fk].slice(-30)) : "";
    return `<div class="mac-tile">
      <div class="mac-t-top"><span class="mac-t-k">${esc(v.label)}${v.stale ? ' <span class="mac-tag">stale</span>' : ""}</span></div>
      <b class="mac-t-p">${esc(fmt(v.price))}</b>
      <span class="mac-t-ch"><em class="${cls(v.chg_1d_pct)}">${sgn(v.chg_1d_pct)}%<i>1d</i></em><em class="${cls(v.chg_1mo_pct)}">${sgn(v.chg_1mo_pct)}%<i>1mo</i></em></span>
      ${spark}
      <span class="mac-t-why" title="${esc(v.psx_read || "")}">${esc(v.psx_read || "")}</span>
    </div>`;
  };
  const group = ([gk, title, why]) => {
    const rows = Object.entries(inst).filter(([, v]) => v.group === gk);
    if (!rows.length) return "";
    return `<div class="mac-grp" data-grp="${esc(gk)}"><div class="mac-grp-h"><b>${esc(title)}</b><i>${esc(why)}</i></div>
      <div class="mac-tiles">${rows.map(tile).join("")}</div></div>`;
  };
  const geoGroup = geo ? `<div class="mac-grp" data-grp="geo"><div class="mac-grp-h"><b>Geo risk</b><i>the desk's composite, not a market tile</i></div>
    <div class="mac-tiles"><div class="mac-tile"><div class="mac-t-top"><span class="mac-t-k">Geo-risk score</span></div>
      <b class="mac-t-p">${esc(String(geo.score))}/100</b>
      <span class="mac-t-why">${esc(geo.band || "unknown")} · ${esc(geo.read || "unknown")}</span></div></div></div>` : "";
  const homeFacts = [
    ["SBP policy rate", m.sbp_rate != null ? macPct(m.sbp_rate) : null],
    ["CPI YoY", m.cpi_yoy != null ? macPct(m.cpi_yoy) : null],
    ["FX reserves", m.reserves_usd_bn != null ? "US$" + macNum(m.reserves_usd_bn) + "bn" : null],
    ["6m T-bill", dom.tbill_6m != null ? macPct(dom.tbill_6m) : null],
    ["10y PIB", dom.pib_10y != null ? macPct(dom.pib_10y) : null],
  ];
  const homeGroup = `<div class="mac-grp" data-grp="home"><div class="mac-grp-h"><b>Pakistan's own numbers</b><i>synthesized from the macro sheet — no live tile</i></div>
    <div class="mac-facts">${homeFacts.map(([k, v]) => `<div class="mac-fact"><span>${esc(k)}</span><b>${v == null ? "unknown" : esc(v)}</b></div>`).join("")}</div>
    ${dom.remittances ? `<p class="mac-sub" style="margin-top:6px"><b>Remittances</b> ${esc(dom.remittances)}</p>` : ""}
    ${dom.debt_note ? `<p class="mac-sub"><b>Debt / borrowing</b> ${esc(dom.debt_note)}</p>` : ""}
  </div>`;
  const testGroup = (us10yLast != null || emEqLast != null) ? `<div class="mac-grp" data-grp="test"><div class="mac-grp-h"><b>Also in the sector test</b><i>no live tile — history only (macro_history.json)</i></div>
    <div class="mac-tiles">
      ${us10yLast != null ? `<div class="mac-tile"><div class="mac-t-top"><span class="mac-t-k">US 10y yield</span></div><b class="mac-t-p">${macPct(us10yLast)}</b>${macSpark(us10ySeries.slice(-30))}<span class="mac-t-why">the US cost of money — a lagged driver in the sector test below</span></div>` : ""}
      ${emEqLast != null ? `<div class="mac-tile"><div class="mac-t-top"><span class="mac-t-k">EM equity flows</span></div><b class="mac-t-p">${macNum(emEqLast)}</b>${macSpark(emEqSeries.slice(-30))}<span class="mac-t-why">an index level, not a price — money moving into emerging markets, lagged a day</span></div>` : ""}
    </div></div>` : "";

  const ch02 = `<section class="mac-ch">
    ${macChapterHead("02", "The drivers board", "Which outside prices are moving and why each matters to Karachi.", `tape ${esc(gl?.updated || "unknown")}`)}
    <div class="mac-chips" role="group" aria-label="Filter driver groups">${MAC_CHIPS.map(([k, l], i) => `<button type="button" data-mac-g="${esc(k)}" aria-pressed="${i === 0}">${esc(l)}</button>`).join("")}</div>
    <p class="mac-src">Global markets refresh every cycle${gl?.source ? ` (${esc(gl.source)})` : ""}; Pakistan numbers are verified from primary sources.</p>
    <div class="mac-tier">
      <p class="mac-lvl"><b>Tier 1</b> · the levers the read names</p>
      <div class="mac-pair">${MAC_TIER1.map(group).join("")}${geoGroup}</div>
    </div>
    <div class="mac-tier">
      <p class="mac-lvl"><b>Tier 2</b> · Pakistan's own numbers</p>
      ${homeGroup}
    </div>
    <div class="mac-tier">
      <p class="mac-lvl"><b>Tier 3</b> · the wider tape</p>
      <div class="mac-fams">${MAC_TIER3.map(group).join("")}${testGroup}</div>
    </div>
  </section>`;

  /* ================= 03 — How the regime shifted ================= */
  const ch03 = `<section class="mac-ch">
    ${macChapterHead("03", "How the regime shifted", "How long the current regime has held, and what the geo score and the index did around each flip.", "history unavailable")}
    <div class="mac-card">
      <p class="mac-unk"><b>Unknown — this desk has no regime-history file.</b> state/regime_hist.json,
      state/geo_hist.json and a KSE-100 daily-close history do not exist yet, so held-since duration,
      the flip count, the flip log and the regime timeline chart cannot be built from real data.
      This section shows only what the macro sheet states today (chapter 01) and what it lists as
      coming up (below) — nothing here is fabricated.</p>
    </div>
    <div class="mac-coming">
      <p class="mac-lvl"><b>Coming up</b> · from the sheet's event list, future only</p>
      <ul class="mac-ev">${events.length ? events.map(e => `<li><b>${esc(e.date)}</b><span>${esc(e.event)}</span></li>`).join("") : `<li><span class="mac-unk">no upcoming events on the sheet</span></li>`}</ul>
    </div>
  </section>`;

  /* ================= 04 — What moves each sector ================= */
  const ch04 = (() => {
    if (!sm?.by_sector) {
      return `<section class="mac-ch">${macChapterHead("04", "What moves each sector", "Which global factors have tended to move each PSX sector the next day — and how little they explain.", "unavailable")}<div class="mac-card"><p class="mac-unk">unknown — sector_macro.json missing</p></div></section>`;
    }
    const h = sm.headline || {};
    const bonf = sm.method?.bonferroni_bar, fdr = sm.method?.fdr_cutoff;
    const MKT = "THE MARKET (KSE100 proxy)";
    const entries = Object.entries(sm.by_sector);
    const mktEntry = entries.find(([sec]) => sec === MKT);
    const rest = entries.filter(([sec]) => sec !== MKT).sort((a, b) => (b[1].joint_r2_pct ?? 0) - (a[1].joint_r2_pct ?? 0));
    const factorsUsed = [...new Set(entries.flatMap(([, rec]) => (rec.drivers || []).map(d => d.factor)))];
    const factorChips = [["all", "All"], ...factorsUsed.map(f => [f, FACTOR_LABEL[f] || f])];

    const srow = ([sec, rec], isMkt) => {
      const demo = (rec.drivers || []).filter(d => d.demonstrated);
      const chips = demo.length
        ? demo.slice(0, 3).map(d => `<span class="mac-chip ${d.corr > 0 ? "up" : "dn"}" data-mac-f="${esc(d.factor)}" title="correlation ${d.corr}, p=${d.p_value}">${esc(FACTOR_LABEL[d.factor] || d.factor)} ${d.corr > 0 ? "↑" : "↓"}</span>`).join("")
        : `<span class="mac-mut">nothing beat chance</span>`;
      return `<tr class="${isMkt ? "mac-mkt-row" : ""}"><td><b>${esc(sec)}</b></td><td>${chips}</td><td class="mac-num">${rec.joint_r2_pct != null ? rec.joint_r2_pct + "%" : "unknown"}</td></tr>`;
    };

    return `<section class="mac-ch">
      ${macChapterHead("04", "What moves each sector", "Which global factors have tended to move each PSX sector the next day — and how little they explain.", `window ${esc(sm.window?.from || "unknown")} → ${esc(sm.window?.to || "unknown")}`)}
      <div class="mac-card">
        <p class="mac-vmeta">THE TEST'S ANSWER · global tape against PSX sectors, lagged a day</p>
        <p class="mac-vp"><b>${esc(String(h.survivors_bonferroni ?? "?"))}</b> of ${esc(String(h.hypotheses_tested ?? "?"))} links pass the strict bar${bonf != null ? ` · Bonferroni p ≤ ${bonf}` : ""}</p>
        <div class="mac-strip c3">
          <div><small>LINKS TESTED</small><b>${esc(String(h.hypotheses_tested ?? "unknown"))}</b><span>${entries.length} sector series</span></div>
          <div><small>PASS THE LOOSER BAR</small><b>${esc(String(h.survivors_fdr ?? "unknown"))}</b><span>${fdr != null ? `Benjamini-Hochberg, p ≤ ${fdr}` : "unknown"}</span></div>
          <div><small>WINDOW</small><b class="mac-num" style="text-align:left">${esc(sm.window?.from || "unknown")} → ${esc(sm.window?.to || "unknown")}</b><span>${sm.window?.psx_days != null ? `${sm.window.psx_days} PSX days` : "unknown"}</span></div>
        </div>
      </div>
      <div class="mac-tilt">
        <p class="mac-vmeta">THE DESK'S READ · sector tilt, written ${esc(m.updated || "unknown")} with the regime</p>
        <p class="mac-sub"><b class="up">Macro tailwind:</b> ${esc((tilt.favored || []).join(" · ") || "unknown")}</p>
        <p class="mac-sub"><b class="dn">Macro headwind:</b> ${esc((tilt.avoid || []).join(" · ") || "unknown")}</p>
        <p class="mac-mut">A read of the macro backdrop, not a recommendation. Losses are expected and documented.</p>
      </div>
      <div class="mac-quiet">
        <details class="mac-more"><summary>The ${esc(String(h.hypotheses_tested ?? "?"))}-link sector table — which factor moved which sector</summary>
          <div class="mac-chips" role="group" aria-label="Highlight sectors by factor">${factorChips.map(([k, l], i) => `<button type="button" data-mac-f="${esc(k)}" aria-pressed="${i === 0}">${esc(l)}</button>`).join("")}</div>
          <table class="mac-tbl"><thead><tr><th>Sector</th><th>Demonstrated drivers</th><th>Global tape explains</th></tr></thead>
            <tbody>${mktEntry ? srow(mktEntry, true) : ""}${rest.map(r => srow(r, false)).join("")}</tbody></table>
          <p class="mac-mut" style="margin-top:8px">↑ moved with the factor · ↓ moved against it.</p>
        </details>
      </div>
      <p class="mac-mut">${esc(sm.method?.lag || "")} ${esc(sm.method?.test || "")} Sector returns: ${esc(sm.method?.sector_returns || "")}. US 10y: ${esc(sm.method?.us10y_units || "")}. ${esc(sm.note || "")}</p>
    </section>`;
  })();

  $("view").innerHTML = `<div class="mac-page today-page">${ch01}${ch02}${ch03}${ch04}</div>`;

  /* click delegation on the fresh page root — never on #view itself (persists across nav) */
  const root = $("view").querySelector(".mac-page");
  root.addEventListener("click", (e) => {
    const gBtn = e.target.closest("[data-mac-g]");
    if (gBtn) {
      const g = gBtn.getAttribute("data-mac-g");
      gBtn.parentElement.querySelectorAll("[data-mac-g]").forEach(b => b.setAttribute("aria-pressed", String(b === gBtn)));
      root.querySelectorAll(".mac-grp").forEach(el => { el.style.display = (g === "all" || el.getAttribute("data-grp") === g) ? "" : "none"; });
      return;
    }
    const fBtn = e.target.closest("[data-mac-f]");
    if (fBtn && fBtn.tagName === "BUTTON") {
      const f = fBtn.getAttribute("data-mac-f");
      fBtn.parentElement.querySelectorAll("[data-mac-f]").forEach(b => b.setAttribute("aria-pressed", String(b === fBtn)));
      root.querySelectorAll(".mac-tbl tbody tr").forEach(tr => {
        if (f === "all") { tr.style.opacity = ""; return; }
        tr.style.opacity = tr.querySelector(`.mac-chip[data-mac-f="${f}"]`) ? "" : "0.35";
      });
    }
  });
}
