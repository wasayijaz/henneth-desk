/* Henneth Today — visual desk read (classic-script renderer).
   The router may call window.HennethTodayRenderer() when this file is loaded. It deliberately
   reads the same state seam/helpers as app.js and never writes state or derives trade rules. */
(function () {
  "use strict";

  const esc0 = v => typeof esc === "function" ? esc(v) : String(v ?? "").replace(/[&<>\"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt0 = v => typeof fmt === "function" ? fmt(v) : (v == null ? "—" : Number(v).toLocaleString("en", { maximumFractionDigits: 2 }));
  const pct = v => v == null || Number.isNaN(Number(v)) ? "—" : `${Number(v) > 0 ? "+" : ""}${Number(v).toFixed(2)}%`;
  const signClass = v => Number(v) > 0.05 ? "up" : Number(v) < -0.05 ? "dn" : "";
  const text = (obj, key) => typeof tp === "function" ? tp(obj, key) : (obj?.[key] ?? "");
  const positiveNumber = value => {
    if (typeof value !== "number" && !(typeof value === "string" && value.trim())) return null;
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? number : null;
  };
  const sourceDate = value => typeof value === "string" && value.trim() ? value.trim() : "date unknown";
  const indexRoundingTolerance = 0.011;
  function readIndexDailyChange(indices, key) {
    if (typeof window.HennethIndexDailyChange === "function") return window.HennethIndexDailyChange(indices, key);
    const entry = indices?.daily_change?.[key], finite = value => typeof value === "number" && Number.isFinite(value);
    const source = typeof indices?.source_at === "string" && indices.source_at.trim() ? indices.source_at : "";
    const session = typeof indices?.live_session_date === "string" && indices.live_session_date.trim() ? indices.live_session_date : "";
    const sourceSession = /^(\d{4}-\d{2}-\d{2})/.exec(source)?.[1] || "";
    if (!entry || typeof entry !== "object" || !source || !session || sourceSession !== session) return null;
    if (!["current", "change", "percent", "derived_previous_close"].every(field => finite(entry[field]))) return null;
    if (entry.current <= 0 || entry.derived_previous_close <= 0 || entry.source_at !== source || entry.session_date !== session) return null;
    const live = indices?.live?.[key];
    if (!finite(live) || live <= 0 || Math.abs(entry.current - live) > indexRoundingTolerance) return null;
    if (Math.abs(entry.derived_previous_close - (entry.current - entry.change)) > indexRoundingTolerance) return null;
    if (Math.abs(entry.percent - (entry.change / entry.derived_previous_close * 100)) > indexRoundingTolerance) return null;
    return entry;
  }

  // The external wire is the canonical article source for the desk (same data rail.js reads).
  // Keep malformed dates behind dated stories and never turn an untrusted URL into a link.
  function articleHref(value) {
    const raw = String(value || "").trim();
    try {
      const parsed = new URL(raw);
      return /^https?:$/i.test(parsed.protocol) && parsed.hostname ? raw : "";
    } catch { return ""; }
  }
  function latestArticle(items) {
    if (!Array.isArray(items)) return null;
    return items.map((item, index) => {
      const headline = typeof item?.headline === "string" ? item.headline.trim() : "";
      const rawDate = String(item?.ts || "").trim();
      return { item, index, headline, stamp: rawDate, ms: rawDate ? Date.parse(rawDate) : NaN };
    }).filter(row => row.headline).sort((a, b) => {
      const av = Number.isFinite(a.ms), bv = Number.isFinite(b.ms);
      if (av !== bv) return av ? -1 : 1;
      if (av && b.ms !== a.ms) return b.ms - a.ms;
      // newslog_append.py is append-only and timestamps are date-only; the final item
      // for a day is the freshest article when several share the same date.
      return b.index - a.index;
    }).map(row => row.item)[0] || null;
  }
  function articleCard(items) {
    const item = latestArticle(items);
    if (!item) return "";
    const title = typeof item.headline === "string" ? item.headline.trim() : "";
    const source = typeof item.source === "string" && item.source.trim() ? item.source.trim() : "Unknown source";
    const rawDate = String(item.ts || "").trim();
    const date = rawDate && Number.isFinite(Date.parse(rawDate)) ? rawDate.slice(0, 10) : "date unknown";
    const excerpt = typeof item.summary === "string" ? item.summary.trim() : "";
    const href = articleHref(item.url);
    return `<article class="today-article" aria-label="Latest external article"><div class="today-article-meta"><span class="today-article-kicker">ARTICLE</span><span>${esc0(source)} · ${esc0(date)}</span></div><h2 class="today-article-title">${esc0(title)}</h2>${excerpt ? `<p class="today-article-excerpt">${esc0(excerpt)}</p>` : ""}${href ? `<a class="today-article-link" href="${esc0(href)}" target="_blank" rel="noopener noreferrer">Read article →</a>` : ""}</article>`;
  }

  function indexRead(indices) {
    const hist = indices?.history || {};
    const dates = Object.keys(hist).sort();
    const latestDate = dates[dates.length - 1];
    const daily = readIndexDailyChange(indices, "KSE100");
    const liveVal = Number(indices?.live?.KSE100);
    const haveLive = Number.isFinite(liveVal);
    const latest = daily ? daily.current : haveLive ? liveVal : Number(hist[latestDate]?.KSE100);
    const date = daily ? daily.source_at : haveLive ? (indices?.source_at || "") : (latestDate || "");
    return { latest, prior: daily ? daily.derived_previous_close : NaN,
      change: daily ? daily.change : NaN, changePct: daily ? daily.percent : NaN, date,
      sessionDate: daily ? daily.session_date : "", priorDate: "",
      values: dates.slice(-30).map(d => hist[d]?.KSE100) };
  }

  function sectorSummary(dr) {
    const fav = (dr?.sectors || []).filter(s => s.stance === "favoured");
    const avoid = (dr?.sectors || []).filter(s => s.stance === "avoid");
    const names = xs => xs.map(s => s.name).slice(0, 3);
    return { fav, avoid, favNames: names(fav), avoidNames: names(avoid) };
  }

  function tickerRows(dr, quant, live, universe) {
    const seen = new Set(), rows = [];
    const add = ticker => {
      const sym = String(ticker || "").toUpperCase();
      if (!sym || seen.has(sym) || !quant?.tickers?.[sym]) return;
      seen.add(sym); rows.push(sym);
    };
    // Keep the personal watchlist distinct from the desk's research radar. The old order
    // repeated the same four live signals twice on Today and made both sections less useful.
    if (typeof watchlist === "function") watchlist().forEach(add);
    (window.HennethTodayWatchlist || []).forEach(add);
    return rows.slice(0, 5).map(sym => {
      const q = quant.tickers[sym] || {}, l = live?.tickers?.[sym] || {};
      const livePrice = positiveNumber(l.current);
      const quantClose = positiveNumber(q.close);
      const hasLivePrice = livePrice !== null;
      const px = hasLivePrice ? livePrice : quantClose;
      return {
        sym,
        name: universe?.symbols?.[sym]?.name || "",
        px,
        q,
        priceAsOf: hasLivePrice ? sourceDate(live?.source_at) : quantClose !== null ? sourceDate(q.date) : "date unknown",
        priceSource: hasLivePrice ? "DPS snapshot" : quantClose !== null ? "Last available close" : "Unknown",
        returnAsOf: sourceDate(q.date),
      };
    });
  }

  function fallbackPriceCell(row) {
    const value = row.px == null ? "—" : fmt0(row.px);
    return `<td class="num"><span>${esc0(value)}</span><small class="today-table-source">${esc0(row.priceSource)} · ${esc0(row.priceAsOf)}</small></td>`;
  }

  function fallbackReturnCell(value, row) {
    return `<td class="num ${signClass(value)}"><span>${pct(value)}</span><small class="today-table-source">${esc0(row.returnAsOf)}</small></td>`;
  }

  function radarRows(dr, dash, snapshot) {
    if (snapshot?.date && Array.isArray(snapshot.rows) && snapshot.rows.length) {
      return snapshot.rows.slice(0, 8).map(row => ({
        ticker: String(row.ticker || "").toUpperCase(),
        strategy: row.strategy || "—",
        hitRate: row.hit_rate,
        winRate: row.hit_rate,
        netExpectancyPct: row.net_expectancy_pct,
        tradeCount: row.n,
        oosHit: row.oos_hit,
        oosStatus: row.oos_hit == null ? "" : `${Math.round(Number(row.oos_hit) * 100)}% hit`,
        confidence: row.confidence || "—",
        angle: row.angle || "",
        risk: row.risk || ""
      })).filter(row => row.ticker);
    }
    const signals = {};
    (dash?.signals || []).forEach(s => { if (s?.ticker && !signals[s.ticker]) signals[s.ticker] = s; });
    return (dr?.watchlist || []).slice(0, 8).map(w => {
      const signal = signals[w.ticker] || {};
      const bt = signal.backtest || {};
      return {
        ticker: String(w.ticker || "").toUpperCase(),
        strategy: signal.template || signal.strategy || "—",
        hitRate: bt.hit_rate,
        winRate: bt.hit_rate,
        netExpectancyPct: bt.net_expectancy_pct,
        tradeCount: bt.n,
        oosHit: bt.oos_hit,
        oosStatus: bt.oos_hit == null ? "" : `${Math.round(Number(bt.oos_hit) * 100)}% hit`,
        confidence: signal.confidence || "—",
        angle: text(w, "angle") || w.angle || "",
        risk: text(w, "risk") || w.risk || ""
      };
    }).filter(r => r.ticker);
  }

  function radarFallback(rows) {
    if (!rows.length) return `<div class="today-empty">No radar names in this snapshot.</div>`;
    return rows.map(r => `<details class="today-radar-row"><summary><b>${esc0(r.ticker)}</b><span>${esc0(r.strategy)}</span><i>${r.hitRate == null ? "—" : `${Math.round(Number(r.hitRate) * 100)}% win`} · ${r.netExpectancyPct == null ? "—" : `${Number(r.netExpectancyPct).toFixed(1)}% net`} · n=${r.tradeCount == null ? "—" : esc0(r.tradeCount)}</i></summary><div class="today-radar-detail"><span>OOS ${r.oosHit == null ? "—" : `${Math.round(Number(r.oosHit) * 100)}%`} · ${esc0(r.confidence)}</span>${r.angle ? `<p>${esc0(r.angle)}</p>` : ""}${r.risk ? `<p><b class="dn">Risk:</b> ${esc0(r.risk)}</p>` : ""}</div></details>`).join("");
  }

  function radarCards(rows) {
    if (!rows.length) return `<div class="today-empty">No radar names in this snapshot.</div>`;
    return rows.map(r => {
      const hit = r.hitRate == null ? null : Number(r.hitRate) * 100;
      const oos = r.oosHit == null ? null : Number(r.oosHit) * 100;
      return `<article class="today-radar-card">
        <div class="today-radar-card-head"><b>${esc0(r.ticker)}</b><span>${esc0(String(r.confidence).toUpperCase())} CONF.</span></div>
        <p>${esc0(r.strategy)}</p>
        <div class="today-radar-metrics">
          <span><small>EXPECTANCY</small><b class="${signClass(r.netExpectancyPct)}">${r.netExpectancyPct == null ? "—" : pct(r.netExpectancyPct)}</b></span>
          <span><small>HIT RATE</small><b>${hit == null ? "—" : `${hit.toFixed(1)}%`}</b></span>
          <span><small>SAMPLE</small><b>${r.tradeCount == null ? "—" : esc0(r.tradeCount)}</b></span>
        </div>
        <div class="today-radar-oos"><span>OUT OF SAMPLE</span><b>${oos == null ? "—" : `${Math.round(oos)}%`}</b><progress max="100" value="${oos == null ? 0 : Math.max(0, Math.min(100, oos))}" aria-label="${esc0(r.ticker)} out-of-sample hit rate"></progress></div>
        <details><summary>Desk angle + key risk</summary><div>${r.angle ? `<p>${esc0(r.angle)}</p>` : ""}${r.risk ? `<p><b class="dn">Risk:</b> ${esc0(r.risk)}</p>` : ""}</div></details>
      </article>`;
    }).join("");
  }

  function renderTimeline(catalysts) {
    if (!catalysts?.length) return `<div class="today-empty">No dated catalyst in the calendar.</div>`;
    return catalysts.slice(0, 5).map((c, i) => `<div class="today-event"><span class="today-event-dot ${i === 0 ? "is-next" : ""}"></span><div><b>${esc0(c.date || "—")}</b><span>${esc0(text(c, "event") || c.event || "Event")}</span>${c.which_tickers?.length ? `<small>${esc0(c.which_tickers.join(" · "))}</small>` : ""}</div></div>`).join("");
  }

  async function renderer() {
    const root = typeof $ === "function" ? $("view") : document.getElementById("view");
    if (!root || typeof j !== "function") return;
    const [dr, quant, live, uni, indices, sectors, cur, dash, news, radarSnapshot] = await Promise.all([
      j("daily_read.json"), j("quant.json"), j("live.json"), j("universe.json"), j("indices.json"), j("sectors.json"), j("curriculum.json"), j("dashboard.json"), j("newslog.json"), j("research_radar.json")
    ]);
    if (!dr) {
      root.innerHTML = `<section class="today-empty-state"><p class="today-kicker">TODAY'S READ</p><h1>Daily read unavailable</h1><p>The market-analyst note has not been published for this cycle.</p></section>`;
      return;
    }
    const ix = indexRead(indices), tone = String(dr.tone || "cautious"), toneClass = tone === "constructive" ? "up" : tone === "defensive" || tone === "cautious" ? "dn" : "";
    const ss = sectorSummary(dr), rows = tickerRows(dr, quant, live, uni), radar = radarRows(dr, dash, radarSnapshot);
    const radarDate = radarSnapshot?.date || dr.date || "date unknown";
    const radarIsPrevious = Boolean(dr.date && radarDate && radarDate !== dr.date);
    const watchHistories = await Promise.all(rows.map(async row => {
      try { return await j(`history/${encodeURIComponent(row.sym)}.json`); }
      catch { return null; }
    }));
    rows.forEach((row, i) => {
      if (Array.isArray(watchHistories[i])) row.sparkline = watchHistories[i].slice(-32).map(point => point?.close).filter(Number.isFinite);
    });
    const lessons = (cur?.levels || []).flatMap(v => (v.lessons || []).map(l => ({ lv: v.id, l }))); let lesson = lessons[0];
    try { const done = typeof learnProgress === "function" ? learnProgress() : {}; lesson = lessons.find(x => !done[x.lv + "/" + x.l.id]) || lesson; } catch { /* optional */ }
    const lessonHtml = lesson ? `<button class="today-disclosure today-lesson" type="button" onclick="openLesson('${esc0(lesson.lv)}','${esc0(lesson.l.id)}')"><span><small>TODAY'S LESSON · ${esc0(lesson.l.mins)} MIN</small><b>${esc0(lesson.l.title)}</b></span><span aria-hidden="true">→</span></button>` : "";
    const setupHtml = `<button class="today-disclosure" type="button" onclick="navigate('/settings')"><span><small>DESK SETUP</small><b>Research workspace, ready.</b></span><span aria-hidden="true">↗</span></button>`;
    const summarySource = String(text(dr, "headline") || dr.headline || text(dr, "summary") || dr.summary || "").replace(/\s+/g, " ").trim();
    const summaryLine = summarySource.replace(/[.!?]\s*$/, "");
    const articleHtml = articleCard(news);
    const changeStrip = Number.isFinite(ix.change) && Number.isFinite(ix.changePct) && ix.date && ix.sessionDate
      ? `<div class="today-change-strip"><b>WHAT CHANGED</b><span>KSE-100 ${pct(ix.changePct)} · ${ix.change > 0 ? "+" : ""}${fmt0(ix.change)} points · session ${esc0(ix.sessionDate)}</span><span class="today-chart-source">PSX board daily change · source as of ${esc0(ix.date)}. Briefing and price snapshot are separate sources.</span></div>`
      : `<div class="today-change-strip"><b>CURRENT SNAPSHOT</b><span>KSE-100 ${fmt0(ix.latest)} · ${esc0(ix.date || "date unknown")}</span><span class="today-chart-source">Briefing and price snapshot are separate sources.</span></div>`;
    root.innerHTML = `<div class="today-page">
      <div class="today-date">${esc0(dr.date || ix.date || "")} <span>· research desk</span></div>
      <section class="today-hero" aria-labelledby="today-heading">
        <div class="today-stance"><p class="today-kicker">TODAY'S STANCE</p><small class="today-chart-source">Analyst briefing · ${esc0(dr.date || "date unknown")}</small><h1 id="today-heading" class="${toneClass}">${esc0(tone.toUpperCase())}</h1><p>${esc0(summaryLine)}${summaryLine ? "." : ""}</p></div>
        <div class="today-index"><p class="today-kicker" data-icon="indices">KSE-100</p><small class="today-chart-source">Index snapshot · ${esc0(ix.date || "date unknown")}</small><div class="today-index-value">${fmt0(ix.latest)}</div><div class="today-index-change ${signClass(ix.changePct)}">${pct(ix.changePct)} <span>${Number.isFinite(ix.change) ? `${ix.change > 0 ? "+" : ""}${fmt0(ix.change)}` : ""}</span></div><div class="today-chart-host" data-hn-today-index aria-label="KSE-100 trend"></div></div>
      </section>
      ${changeStrip}
      <section class="today-priorities" aria-label="Desk priorities">
        <div class="today-priority"><p class="today-kicker up" data-icon="sectors">FAVOURED</p><b>${ss.favNames.length ? esc0(ss.favNames.join(", ")) : "None flagged"}</b><small>${ss.fav.length} sector${ss.fav.length === 1 ? "" : "s"}</small></div>
        <div class="today-priority"><p class="today-kicker dn" data-icon="risk">AVOIDING</p><b>${ss.avoidNames.length ? esc0(ss.avoidNames.join(", ")) : "None flagged"}</b><small>${ss.avoid.length} sector${ss.avoid.length === 1 ? "" : "s"}</small></div>
        <div class="today-priority"><p class="today-kicker" data-icon="calendar">NEXT CATALYST</p><b>${esc0(dr.catalysts?.[0]?.date || "—")}</b><small>${esc0(text(dr.catalysts?.[0] || {}, "event") || dr.catalysts?.[0]?.event || "No dated event")}</small></div>
      </section>
      <section class="today-radar" id="research-radar"><div class="today-section-head"><p class="today-kicker" data-icon="radar">RESEARCH RADAR <span>· ${radarIsPrevious ? "PREVIOUS COMPLETE SNAPSHOT" : "LATEST COMPLETE SNAPSHOT"} · AS OF ${esc0(radarDate)} · NOT RECOMMENDATIONS</span></p></div><div class="today-radar-host" data-hn-desk-radar>${radarFallback(radar)}</div><div class="today-radar-cards" id="radar-evidence">${radarCards(radar)}</div></section>
      <section class="today-breadth" id="sector-breadth"><div class="today-section-head"><p class="today-kicker" data-icon="sectors">SECTOR BREADTH <span>(ADV / DEC)</span></p></div><div class="today-breadth-list" data-hn-sector-breadth><div class="today-empty">Loading breadth view…</div></div></section>
      <section class="today-grid"><div class="today-panel"><div class="today-section-head"><p class="today-kicker" data-icon="watchlist">WATCHLIST (${rows.length})</p><a href="/watchlist">View full →</a></div><div class="today-table-wrap" data-hn-today-watch><table class="today-table"><thead><tr><th>Symbol</th><th>Name</th><th>Price</th><th>1D</th><th>5D</th><th>20D</th></tr></thead><tbody>${rows.map(r => `<tr class="clickable" onclick="navigate('/ticker/${esc0(r.sym)}')"><td><b>${esc0(r.sym)}</b></td><td>${esc0(String(r.name).slice(0, 27))}</td>${fallbackPriceCell(r)}${fallbackReturnCell(r.q.ret_1d, r)}${fallbackReturnCell(r.q.ret_5d, r)}${fallbackReturnCell(r.q.ret_20d, r)}</tr>`).join("") || `<tr><td colspan="6" class="today-empty">No watchlist names in this snapshot.</td></tr>`}</tbody></table></div></div><div class="today-panel"><div class="today-section-head"><p class="today-kicker" data-icon="calendar">CATALYST TIMELINE</p><a href="/calendar">View full →</a></div><div class="today-events" data-hn-catalysts>${renderTimeline(dr.catalysts)}</div></div></section>
      ${articleHtml}
      <section class="today-disclosures">${lessonHtml}${setupHtml}</section>
      <p class="today-disclaimer">${esc0(dr.disclaimer || "Research, not advice. The desk generates signals; it does not place orders.")}</p>
    </div>`;
    try {
      if (typeof window.HennethTodayCharts?.enhance === "function") {
        window.HennethTodayCharts.enhance(root, { index: { ...ix, history: indices?.history || {}, updated: indices?.source_at }, quant, live, sectors, watchlist: rows, catalysts: dr.catalysts || [], dailyRead: dr, dashboard: dash, radar, deskRadar: radar }, { compact: true, radar: { compactHeader: true, source: radarDate } });
      } else {
        const host = root.querySelector("[data-hn-sector-breadth]");
        if (host) host.innerHTML = `<div class="today-empty">Breadth view unavailable in this snapshot.</div>`;
      }
    } catch (e) { console.warn("[henneth] Today charts unavailable", e); }
    try { window.HennethTodayInfo?.enhance?.(root); } catch (e) { console.warn("[henneth] Today info unavailable", e); }
  }

  window.HennethTodayRenderer = renderer;
  window.HennethTodayArticle = { latest: latestArticle, href: articleHref, card: articleCard };
  window.pageTodayRedesigned = renderer;
})();
