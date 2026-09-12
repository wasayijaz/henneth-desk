(function () {
  "use strict";

  const API_VERSION = "2026.09.05";
  const NS = "HennethTodayCharts";
  const STYLE_ID = "hn-today-charts-style";
  const DEFAULT_SPARK_POINTS = 32;
  const FLAT_BAND = 0.05;
  const MONO_STACK = '\"JetBrains Mono\", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
  const monoFont = size => `${size}px ${MONO_STACK}`;

  const isFiniteNumber = v => typeof v === "number" && Number.isFinite(v);
  const toNumber = v => {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
  const escAttr = s => esc(s).replace(/`/g, "&#96;");
  const pct = (v, digits = 1) => {
    const n = toNumber(v);
    if (n == null) return "-";
    return (n > 0 ? "+" : "") + n.toFixed(digits) + "%";
  };
  const fmtInt = v => {
    const n = toNumber(v);
    return n == null ? "0" : Math.round(n).toLocaleString("en");
  };
  const toneClass = v => {
    const n = toNumber(v);
    return n == null ? "" : n > FLAT_BAND ? "up" : n < -FLAT_BAND ? "dn" : "";
  };
  const seriesCsv = values => values.map(v => {
    const n = toNumber(v);
    return n == null ? "" : String(+n.toFixed(4));
  }).join(",");
  function sourceStamp(value) {
    const raw = typeof value === "string" ? value : value?.updated || value?.as_of || value?.date || "";
    return raw ? `Source ${String(raw).replace(/\s+/g, " ")}` : "Source UNKNOWN";
  }

  function redrawAfterFontLoad(canvas, redraw) {
    if (!canvas || canvas._hnFontsReadyBound || typeof document === "undefined" || !document.fonts?.ready?.then) return;
    canvas._hnFontsReadyBound = true;
    document.fonts.ready.then(() => {
      if (canvas.isConnected !== false) redraw(canvas);
    }, () => {});
  }

  function ensureStyles() {
    if (typeof document === "undefined" || document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
.hn-today-visual{box-sizing:border-box}
.hn-today-watch,.hn-catalyst-timeline{display:grid;gap:1px;background:var(--hair,var(--line));border:1.5px solid var(--line)}
.hn-index-trend{border:1.5px solid var(--line);background:var(--panel);padding:12px}
.hn-index-compact{position:relative}.hn-chart-heading{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px;border-bottom:1px solid var(--line);padding:0 0 7px;margin-bottom:4px}.hn-chart-heading .sub{font-size:9px;color:var(--ink2)}.hn-chart-source{display:block;color:var(--ink2);font-size:8px;letter-spacing:.03em}.hn-index-compact .hn-chart-source{margin-top:2px}
.hn-index-top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:8px}
.hn-index-title{min-width:0}
.hn-index-title b{display:block}
.hn-index-value{text-align:end;white-space:nowrap}
.hn-index-canvas{width:100%;height:118px;display:block}
.hn-index-canvas.is-compact{height:92px}
.hn-today-watch-row{display:grid;grid-template-columns:minmax(88px,1fr) 82px 106px 58px;gap:10px;align-items:center;background:var(--panel);padding:10px 12px;color:inherit;text-decoration:none}
.hn-today-watch-name{min-width:0}
.hn-today-spark{width:106px;height:30px;display:block}
.hn-sector-breadth{border:1.5px solid var(--line);background:var(--panel);padding:10px}
.hn-sector-matrix-canvas{width:100%;display:block}
.hn-desk-radar{position:relative;border:1.5px solid var(--line);background:var(--panel);padding:12px}
.hn-desk-radar-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:8px}
.hn-desk-radar-head b{display:block}
.hn-desk-radar-canvas{width:100%;display:block;cursor:crosshair}
.hn-desk-radar-tip{position:absolute;z-index:4;width:min(310px,calc(100% - 24px));padding:11px 12px;border:1px solid var(--ink2);background:var(--panel);box-shadow:3px 3px 0 color-mix(in srgb,var(--ink2) 22%,transparent);pointer-events:none;transform:translate(10px,10px);font-family:${MONO_STACK}}
.hn-desk-radar-tip[hidden]{display:none}
.hn-desk-radar-tip-head{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:7px}
.hn-desk-radar-tip-head b{font-size:14px}
.hn-desk-radar-tip-head span,.hn-desk-radar-tip-meta{color:var(--ink2);font-size:9px}
.hn-desk-radar-tip p{margin:6px 0 0;font-size:9px;line-height:1.45}
.hn-desk-radar-tip-risk{color:var(--dn)}
.hn-desk-radar-canvas:focus,.hn-sector-matrix-canvas:focus{outline:1px solid var(--ink2);outline-offset:3px}.hn-sector-tip{position:absolute;z-index:4;max-width:min(360px,calc(100% - 24px));max-height:220px;overflow:auto;padding:8px 10px;border:1px solid var(--ink2);background:var(--panel);box-shadow:3px 3px 0 color-mix(in srgb,var(--ink2) 20%,transparent);pointer-events:auto;font-size:9px;line-height:1.45;font-family:${MONO_STACK}}.hn-sector-tip[hidden]{display:none}.hn-sector-tip b,.hn-sector-tip>span{display:block}.hn-sector-tip>span{color:var(--ink2)}.hn-sector-members{display:grid;grid-template-columns:repeat(2,minmax(90px,1fr));gap:2px 10px;margin-top:7px;border-top:1px solid var(--line);padding-top:6px}.hn-sector-member{display:flex;justify-content:space-between;gap:8px;color:var(--ink1);text-decoration:none;padding:2px 0}.hn-sector-member:hover,.hn-sector-member:focus-visible{outline:1px solid var(--ink2);outline-offset:1px}.hn-sector-member.up span{color:var(--up)}.hn-sector-member.dn span{color:var(--dn)}.hn-sector-member.flat span{color:var(--ink2)}
.hn-sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.hn-catalyst-row{display:grid;grid-template-columns:102px 1fr auto;gap:10px;align-items:start;background:var(--panel);padding:10px 12px}
.hn-catalyst-date{text-align:center}
.hn-catalyst-copy{min-width:0}
@media(max-width:640px){
  .hn-today-watch-row{grid-template-columns:minmax(0,1fr) 62px}
  .hn-index-top{display:grid;grid-template-columns:1fr}
  .hn-index-value{text-align:start}
  .hn-today-spark{grid-column:1/-1;width:100%;height:34px}
  .hn-sector-row,.hn-catalyst-row{grid-template-columns:1fr}
  .hn-desk-radar-head{display:grid;grid-template-columns:1fr}
  .hn-catalyst-date{text-align:start;width:max-content}
}`;
    document.head.appendChild(style);
  }

  let _palette = null;
  function palette() {
    if (_palette) return _palette;
    if (typeof document === "undefined") {
      _palette = { up: "#287a3e", dn: "#a33a34", ink: "#1f211d", ink2: "#55584e", line: "#d8d3c7", panel: "#f7f4ea" };
      return _palette;
    }
    const target = document.body || document.documentElement;
    const css = getComputedStyle(target);
    const cssVar = name => css.getPropertyValue(name).trim();
    _palette = {
      up: cssVar("--up") || "#287a3e",
      dn: cssVar("--dn") || "#a33a34",
      ink: cssVar("--ink1") || css.color || "#1f211d",
      ink2: cssVar("--ink2") || "#55584e",
      line: cssVar("--line") || "#d8d3c7",
      panel: cssVar("--panel") || "#f7f4ea",
    };
    return _palette;
  }
  function invalidatePalette() { _palette = null; }

  function closeSeriesFromHistory(history, limit = DEFAULT_SPARK_POINTS) {
    const rows = Array.isArray(history) ? history : [];
    return rows
      .map(r => toNumber(r && (r.close ?? r.c ?? r.price ?? r.current)))
      .filter(isFiniteNumber)
      .slice(-limit);
  }

  function sparkStats(values) {
    const points = values.map(toNumber).filter(isFiniteNumber);
    if (points.length < 2) return { points, changePct: null, direction: "flat" };
    const first = points[0], last = points[points.length - 1];
    const changePct = first ? (last / first - 1) * 100 : null;
    const direction = changePct == null ? "flat" : changePct > FLAT_BAND ? "up" : changePct < -FLAT_BAND ? "down" : "flat";
    return { points, changePct, direction };
  }

  function symbolOf(raw) {
    if (raw && typeof raw === "object") return String(raw.sym || raw.ticker || raw.s || "").trim().toUpperCase();
    return String(raw || "").trim().toUpperCase();
  }

  function prepareWatchlistRows(symbols, data = {}, options = {}) {
    const tickers = Array.isArray(symbols) ? symbols : [];
    const quant = data.quant?.tickers || data.quant || {};
    const live = data.live?.tickers || data.live || {};
    const universe = data.universe?.symbols || data.universe || {};
    const histories = data.histories || data.history || {};
    const limit = Math.max(4, Math.min(96, toNumber(options.points) || DEFAULT_SPARK_POINTS));

    return tickers.map(symbolOf).filter(Boolean).map((ticker, i) => {
      const raw = tickers[i] && typeof tickers[i] === "object" ? tickers[i] : {};
      const q = quant[ticker] || {};
      const l = live[ticker] || {};
      const u = universe[ticker] || {};
      const hasSnapshot = typeof l.current === "number" && Number.isFinite(l.current) && l.current > 0;
      const hasClose = typeof q.close === "number" && Number.isFinite(q.close) && q.close > 0;
      const price = hasSnapshot ? l.current : hasClose ? q.close : toNumber(raw.price ?? raw.px ?? raw.current);
      const priceAsOf = hasSnapshot ? data.live?.source_at : hasClose ? q.date : raw.priceAsOf;
      const priceSource = hasSnapshot ? "DPS snapshot" : hasClose ? "Last available close" : "Provided price";
      const returnAsOf = hasSnapshot && l.ldcp > 0 ? data.live?.source_at : q.date;
      const dayPct = hasSnapshot && l.ldcp > 0 ? (l.current / l.ldcp - 1) * 100 : toNumber(q.ret_1d ?? raw.dayPct ?? raw.ret_1d ?? raw.changePct);
      const spark = Array.isArray(raw.sparkline || raw.history)
        ? (raw.sparkline || raw.history).map(r => toNumber(r?.close ?? r?.value ?? r)).filter(isFiniteNumber).slice(-limit)
        : Array.isArray(data.sparkline?.[ticker])
        ? data.sparkline[ticker].map(toNumber).filter(isFiniteNumber).slice(-limit)
        : closeSeriesFromHistory(histories[ticker], limit);
      const stats = sparkStats(spark);
      return {
        ticker,
        name: String(raw.name || u.name || ""),
        price,
        dayPct,
        priceAsOf: priceAsOf || "unknown",
        priceSource,
        returnAsOf: returnAsOf || "unknown",
        sparkline: stats.points,
        sparkChangePct: stats.changePct,
        direction: dayPct == null ? stats.direction : dayPct > FLAT_BAND ? "up" : dayPct < -FLAT_BAND ? "down" : "flat",
      };
    });
  }

  function indexValueOf(row) {
    if (row == null) return null;
    if (typeof row !== "object") return toNumber(row);
    return toNumber(row.close ?? row.value ?? row.current ?? row.price ?? row.index ?? row.level);
  }

  function indexDateOf(row) {
    if (!row || typeof row !== "object") return "";
    return String(row.date || row.t || row.time || "");
  }

  function prepareIndexTrend(index = {}, options = {}) {
    index = index || {};
    const limit = Math.max(8, Math.min(160, toNumber(options.points) || 48));
    const rows = Array.isArray(index) ? index
      : Array.isArray(index.history) ? index.history
      : Array.isArray(index.values) ? index.values
      : Array.isArray(index.points) ? index.points
      : [];
    const points = rows.map(row => ({ value: indexValueOf(row), date: indexDateOf(row) }))
      .filter(row => row.value != null)
      .slice(-limit);
    const values = points.map(p => p.value);
    const stats = sparkStats(values);
    const last = values.length ? values[values.length - 1] : toNumber(index.current ?? index.close ?? index.value);
    const label = String(index.label || index.name || "KSE-100");
    const date = String(index.date || points[points.length - 1]?.date || "");
    return {
      label,
      date,
      points,
      values,
      value: last,
      changePct: stats.changePct,
      direction: stats.direction,
    };
  }

  function indexTrendHtml(model, options = {}) {
    ensureStyles();
    const m = model || prepareIndexTrend(null, options);
    const values = Array.isArray(m.values) ? m.values : [];
    const label = m.label || "KSE-100";
    const sparkLabel = values.length >= 2
      ? `${label} ${pct(m.changePct)} over the provided index history`
      : `${label} has no provided index history`;
    if (options.compact || options.indexCard === false) {
      return `<div class="hn-index-compact"><canvas class="hn-index-canvas is-compact" width="520" height="92" role="img" aria-label="${escAttr(sparkLabel)}" title="${escAttr(sparkLabel)}" data-values="${escAttr(seriesCsv(values))}" data-tone="${escAttr(m.direction)}"></canvas><span class="hn-chart-source">${esc(sourceStamp(options.source || m.date))}</span></div>`;
    }
    return `<div class="hn-today-visual hn-index-trend" aria-label="${escAttr(label + " trend")}">
      <div class="hn-index-top">
        <span class="hn-index-title"><b>${esc(label)}</b><span class="sub">${esc(m.date || "provided history")}</span></span>
        <span class="hn-index-value"><b class="num ${toneClass(m.changePct)}">${m.value == null ? "-" : esc(m.value.toLocaleString("en", { maximumFractionDigits: 2 }))}</b><span class="sub">${pct(m.changePct)}</span></span>
      </div>
      <canvas class="hn-index-canvas" width="520" height="118" role="img" aria-label="${escAttr(sparkLabel)}" title="${escAttr(sparkLabel)}" data-values="${escAttr(seriesCsv(values))}" data-tone="${escAttr(m.direction)}"></canvas><span class="hn-chart-source">${esc(sourceStamp(options.source || m.date))}</span>
    </div>`;
  }

  function drawIndexTrend(canvas, values, options = {}) {
    if (!canvas || typeof canvas.getContext !== "function") return false;
    const points = (Array.isArray(values) ? values : []).map(toNumber).filter(isFiniteNumber);
    const w = Math.max(160, Math.floor(canvas.clientWidth || canvas.width || 520));
    const h = Math.max(80, Math.floor(canvas.clientHeight || canvas.height || 118));
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return false;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const c = palette();
    const pad = { l: 6, r: 8, t: 8, b: 18 };
    const mid = Math.floor((h - pad.b + pad.t) / 2) + 0.5;
    ctx.strokeStyle = c.line;
    ctx.lineWidth = 1;
    ctx.globalAlpha = 0.9;
    ctx.beginPath();
    ctx.moveTo(pad.l, mid);
    ctx.lineTo(w - pad.r, mid);
    ctx.stroke();
    if (points.length < 2) {
      ctx.globalAlpha = 0.75;
      ctx.fillStyle = c.ink2;
      ctx.font = monoFont(11);
      ctx.fillText("no provided index line", pad.l, mid - 8);
      ctx.globalAlpha = 1;
      return false;
    }
    const lo = Math.min(...points), hi = Math.max(...points), span = hi - lo || Math.max(Math.abs(hi), 1) * 0.01;
    const x = i => pad.l + i / (points.length - 1) * (w - pad.l - pad.r);
    const y = v => pad.t + (1 - (v - lo) / span) * (h - pad.t - pad.b);
    const tone = options.tone || canvas.getAttribute("data-tone") || "";
    const line = tone === "down" ? c.dn : tone === "up" ? c.up : c.ink2;
    ctx.globalAlpha = 0.15;
    ctx.fillStyle = line;
    ctx.beginPath();
    points.forEach((v, i) => i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v)));
    ctx.lineTo(x(points.length - 1), h - pad.b);
    ctx.lineTo(x(0), h - pad.b);
    ctx.closePath();
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.strokeStyle = line;
    ctx.lineWidth = 2;
    ctx.beginPath();
    points.forEach((v, i) => i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v)));
    ctx.stroke();
    ctx.fillStyle = line;
    ctx.fillRect(Math.round(x(points.length - 1)) - 2, Math.round(y(points[points.length - 1])) - 2, 4, 4);
    ctx.fillStyle = c.ink2;
    ctx.globalAlpha = 0.65;
    ctx.font = monoFont(10);
    ctx.fillText(String(Math.round(hi).toLocaleString("en")), pad.l, 10);
    ctx.fillText(String(Math.round(lo).toLocaleString("en")), pad.l, h - 4);
    ctx.globalAlpha = 1;
    return true;
  }

  function mountIndexTrend(root) {
    const host = root && root.querySelectorAll ? root : document;
    host.querySelectorAll("canvas.hn-index-canvas").forEach(canvas => {
      const values = String(canvas.getAttribute("data-values") || "")
        .split(",")
        .map(toNumber)
        .filter(isFiniteNumber);
      drawIndexTrend(canvas, values);
      redrawAfterFontLoad(canvas, current => drawIndexTrend(current, values));
    });
  }

  function radarPct(raw) {
    const n = toNumber(raw);
    if (n == null) return null;
    return Math.abs(n) <= 1 ? n * 100 : n;
  }

  function oosStatusOf(row) {
    if (!row || typeof row !== "object") return "";
    const raw = row.oosStatus ?? row.oos_status ?? row.oos ?? row.oosPass ?? row.oos_pass ?? row.outOfSample ?? row.out_of_sample;
    if (raw === true) return "pass";
    if (raw === false) return "fail";
    const s = String(raw || "").trim().toLowerCase();
    if (!s) return "";
    if (/pass|work|profitable|positive|ok/.test(s)) return "pass";
    if (/fail|loss|negative|weak|miss/.test(s)) return "fail";
    return s.slice(0, 18);
  }

  function prepareDeskRadar(items = [], options = {}) {
    const rows = Array.isArray(items) ? items
      : Array.isArray(items?.rows) ? items.rows
      : Array.isArray(items?.watchlist) ? items.watchlist
      : [];
    const limit = Math.max(1, Math.min(16, toNumber(options.limit) || 8));
    return rows.map(row => {
      const ticker = symbolOf(row);
      // Expectancy fields are explicitly percentage points (`*_pct`); unlike hit/OOS
      // rates they must not turn 0.8% into an invented 80%.
      const expectancy = toNumber(row?.expectancyPct ?? row?.netExpectancyPct ?? row?.net_expectancy_pct ?? row?.netPct ?? row?.net_pct ?? row?.expectancy);
      const explicitWinPct = row?.winRatePct ?? row?.win_rate_pct ?? row?.hitRatePct ?? row?.hit_rate_pct;
      const winRate = explicitWinPct == null ? radarPct(row?.winRate ?? row?.win_rate) : toNumber(explicitWinPct);
      const trades = toNumber(row?.tradeCount ?? row?.trade_count ?? row?.trades ?? row?.n ?? row?.sample ?? row?.sampleSize ?? row?.sample_size);
      const explicitOosPct = row?.oosHitPct ?? row?.oos_hit_pct ?? row?.oosPercent ?? row?.oos_percent;
      const oosHit = explicitOosPct == null ? radarPct(row?.oosHit ?? row?.oos_hit) : toNumber(explicitOosPct);
      const suppliedStatus = oosStatusOf(row);
      const status = oosHit == null ? suppliedStatus : oosHit >= 50 ? "pass" : "fail";
      return {
        ticker,
        expectancy,
        winRate,
        trades: trades == null ? null : Math.max(0, trades),
        // Keep the normalized percent on the row: deskRadarHtml() prepares rows
        // again, and dropping this value there used to erase OOS labels.
        oosHit,
        oosHitPct: oosHit,
        winRatePct: winRate,
        oosStatus: status,
        oosLabel: oosHit == null ? suppliedStatus : `${Math.round(oosHit)}% hit`,
        strategy: String(row?.strategy ?? row?.template ?? row?.trigger ?? "").trim(),
        confidence: String(row?.confidence ?? "").trim(),
        angle: String(row?.angle ?? row?.deskAngle ?? row?.desk_angle ?? "").trim(),
        risk: String(row?.risk ?? row?.keyRisk ?? row?.key_risk ?? "").trim(),
      };
    }).filter(row => row.ticker && row.expectancy != null && row.winRate != null && row.trades != null)
      .slice(0, limit);
  }

  function deskRadarHtml(rows, options = {}) {
    ensureStyles();
    const list = prepareDeskRadar(rows, options);
    if (!list.length) return "";
    const title = options.title || "Desk Radar";
    const subtitle = options.subtitle || "Historical tested evidence only: net expectancy, win rate and sample size. Not a recommendation or forecast.";
    const heading = options.compactHeader ? "" : `<div class="hn-desk-radar-head"><span><b>${esc(title)}</b><span class="sub">${esc(subtitle)}</span></span></div>`;
    const payload = escAttr(JSON.stringify(list));
    const summary = list.map(row => `${row.ticker}: ${pct(row.expectancy)} expectancy, ${pct(row.winRate)} win rate, ${fmtInt(row.trades)} trades${row.oosLabel ? ", OOS " + row.oosLabel : ""}`).join("; ");
    return `<div class="hn-today-visual hn-desk-radar" aria-label="${escAttr(title)}">
      ${heading}
      <canvas class="hn-desk-radar-canvas" tabindex="0" width="620" height="260" role="img" aria-label="${escAttr(summary)}" title="${escAttr(title)}" data-rows="${payload}"></canvas><span class="hn-chart-source">${esc(sourceStamp(options.source))}</span>
      <div class="hn-desk-radar-tip" role="status" aria-live="polite" hidden></div>
      <table class="hn-sr-only">
        <caption>${esc(title)} - historical tested evidence, not a recommendation or forecast</caption>
        <thead><tr><th>Ticker</th><th>Net expectancy %</th><th>Win rate %</th><th>Trades</th><th>OOS status</th></tr></thead>
        <tbody>${list.map(row => `<tr><th>${esc(row.ticker)}</th><td>${pct(row.expectancy)}</td><td>${pct(row.winRate)}</td><td>${fmtInt(row.trades)}</td><td>${esc(row.oosLabel || "not provided")}</td></tr>`).join("")}</tbody>
      </table>
    </div>`;
  }

  function drawDeskRadar(canvas, rows, options = {}) {
    if (!canvas || typeof canvas.getContext !== "function") return false;
    const list = prepareDeskRadar(rows || canvas._hnRadarRows || [], options);
    const w = Math.max(280, Math.floor(canvas.clientWidth || canvas.width || 620));
    const h = Math.max(220, Math.floor(canvas.clientHeight || canvas.height || 260));
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    canvas.style.height = h + "px";
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return false;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const c = palette();
    const pad = { l: w < 440 ? 34 : 42, r: 18, t: 18, b: 34 };
    const xs = list.map(row => row.expectancy);
    const ys = list.map(row => row.winRate);
    const xMin = Math.min(-1, ...xs), xMax = Math.max(1, ...xs);
    const xPad = Math.max(0.5, (xMax - xMin) * 0.12);
    const loX = xMin - xPad, hiX = xMax + xPad;
    const loY = Math.max(0, Math.min(50, ...ys) - 5);
    const hiY = Math.min(100, Math.max(60, ...ys) + 5);
    const maxTrades = Math.max(1, ...list.map(row => row.trades || 0));
    const x = v => pad.l + (v - loX) / ((hiX - loX) || 1) * (w - pad.l - pad.r);
    const y = v => pad.t + (1 - (v - loY) / ((hiY - loY) || 1)) * (h - pad.t - pad.b);
    const zeroX = x(0);

    ctx.strokeStyle = c.line;
    ctx.lineWidth = 1;
    ctx.globalAlpha = 0.9;
    ctx.strokeRect(pad.l + 0.5, pad.t + 0.5, w - pad.l - pad.r, h - pad.t - pad.b);
    ctx.globalAlpha = 0.45;
    ctx.beginPath();
    ctx.moveTo(zeroX, pad.t);
    ctx.lineTo(zeroX, h - pad.b);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(pad.l, y(50));
    ctx.lineTo(w - pad.r, y(50));
    ctx.stroke();

    ctx.globalAlpha = 1;
    ctx.fillStyle = c.ink2;
    ctx.font = monoFont(10);
    ctx.fillText("net expectancy %", pad.l, h - 9);
    ctx.save();
    ctx.translate(10, h - pad.b);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("win rate %", 0, 0);
    ctx.restore();
    ctx.fillText(pct(loX, 0), pad.l, h - 22);
    ctx.fillText(pct(hiX, 0), w - pad.r - 34, h - 22);
    ctx.fillText("50%", pad.l + 4, y(50) - 6);

    const hasOos = list.some(row => row.oosLabel);
    canvas._hnRadarPoints = [];
    list.forEach(row => {
      const cx = x(row.expectancy), cy = y(row.winRate);
      const size = 5 + Math.sqrt((row.trades || 1) / maxTrades) * 13;
      const goodX = row.expectancy > FLAT_BAND;
      const goodY = row.winRate >= 50;
      ctx.globalAlpha = 0.18;
      ctx.fillStyle = goodX && goodY ? c.up : !goodX && !goodY ? c.dn : c.ink2;
      ctx.fillRect(cx - size / 2, cy - size / 2, size, size);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = row.oosStatus === "pass" ? c.up : row.oosStatus === "fail" ? c.dn : c.ink2;
      ctx.setLineDash(row.oosStatus && row.oosStatus !== "pass" ? [3, 3] : []);
      ctx.strokeRect(cx - size / 2 + 0.5, cy - size / 2 + 0.5, size, size);
      ctx.setLineDash([]);
      if (canvas._hnRadarActive === row.ticker) {
        ctx.strokeStyle = c.ink;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(cx - size / 2 - 3.5, cy - size / 2 - 3.5, size + 7, size + 7);
      }
      ctx.fillStyle = c.ink;
      ctx.font = monoFont(11);
      const labelWidth = ctx.measureText(row.ticker).width;
      const gap = 5, plotLeft = pad.l + 2, plotRight = w - pad.r - 2;
      const rightX = cx + size / 2 + gap, leftX = cx - size / 2 - gap - labelWidth;
      const maxLabelX = Math.max(plotLeft, plotRight - labelWidth);
      // Prefer the natural right side; flip left when a long ticker would run past the
      // plot edge. If neither side fits, clamp to the side with more room (without
      // changing the marker or its hit target).
      let labelX;
      if (rightX + labelWidth <= plotRight) labelX = rightX;
      else if (leftX >= plotLeft) labelX = leftX;
      else {
        const rightRoom = Math.max(0, plotRight - rightX), leftRoom = Math.max(0, leftX - plotLeft);
        labelX = rightRoom >= leftRoom ? Math.min(Math.max(rightX, plotLeft), maxLabelX) : Math.min(Math.max(leftX, plotLeft), maxLabelX);
      }
      canvas._hnRadarPoints.push({ x: cx, y: cy, radius: Math.max(10, size / 2 + 7),
        label: { x: labelX - 4, y: cy - 10, w: labelWidth + 8, h: 20 }, row });
      ctx.fillText(row.ticker, labelX, cy + 3);
    });

    if (hasOos) {
      ctx.fillStyle = c.ink2;
      ctx.font = monoFont(10);
      ctx.fillText("OOS outline: solid ≥50%, dashed <50%", pad.l, 10);
    }
    ctx.globalAlpha = 1;
    return true;
  }

  function mountDeskRadar(root) {
    const host = root && root.querySelectorAll ? root : document;
    host.querySelectorAll("canvas.hn-desk-radar-canvas").forEach(canvas => {
      let rows = [];
      try { rows = JSON.parse(canvas.getAttribute("data-rows") || "[]"); } catch { rows = []; }
      canvas._hnRadarRows = rows;
      drawDeskRadar(canvas, rows);
      if (!canvas._hnHoverBound) {
        const tip = canvas.parentElement?.querySelector(".hn-desk-radar-tip");
        const hideTip = () => { canvas._hnRadarActive = null; drawDeskRadar(canvas); if (tip) tip.hidden = true; };
        const showPoint = (point, px, py) => {
          if (!point || !tip) return;
          canvas._hnRadarActive = point.row.ticker;
          drawDeskRadar(canvas);
          const row = point.row;
          const angle = row.angle ? row.angle.slice(0, 210) + (row.angle.length > 210 ? "…" : "") : "Included because its current technical trigger cleared the desk's historical evidence screen.";
          const risk = row.risk ? row.risk.slice(0, 145) + (row.risk.length > 145 ? "…" : "") : "No additional key risk note is available in this snapshot.";
          tip.innerHTML = `<div class="hn-desk-radar-tip-head"><b>${esc(row.ticker)}</b><span>${esc(row.confidence ? row.confidence.toUpperCase() + " CONFIDENCE" : "RESEARCH RADAR")}</span></div>${row.strategy ? `<div class="hn-desk-radar-tip-meta">${esc(row.strategy)}</div>` : ""}<div class="hn-desk-radar-tip-meta">${pct(row.expectancy)} expectancy · ${pct(row.winRate)} hit rate · ${fmtInt(row.trades)} trades${row.oosLabel ? ` · OOS ${esc(row.oosLabel)}` : ""}</div><p>${esc(angle)}</p><p class="hn-desk-radar-tip-risk"><b>Key risk:</b> ${esc(risk)}</p>`;
          const maxLeft = Math.max(8, canvas.clientWidth - Math.min(310, canvas.clientWidth - 24) - 16);
          tip.style.left = clamp(px, 8, maxLeft) + "px";
          tip.style.top = clamp(py, 8, Math.max(8, canvas.clientHeight - 150)) + "px";
          tip.hidden = false;
        };
        canvas.addEventListener("pointermove", event => {
          if (!tip) return;
          const rect = canvas.getBoundingClientRect();
          const px = event.clientX - rect.left;
          const py = event.clientY - rect.top;
          const point = (canvas._hnRadarPoints || []).find(p => {
            const label = p.label;
            const inLabel = label && px >= label.x && px <= label.x + label.w && py >= label.y && py <= label.y + label.h;
            return Math.hypot(px - p.x, py - p.y) <= p.radius || inLabel;
          });
          if (!point) { hideTip(); return; }
          showPoint(point, px, py);
        });
        canvas.addEventListener("pointerdown", event => { const rect = canvas.getBoundingClientRect(); const point = (canvas._hnRadarPoints || []).find(p => Math.hypot(event.clientX - rect.left - p.x, event.clientY - rect.top - p.y) <= p.radius || (p.label && event.clientX - rect.left >= p.label.x && event.clientX - rect.left <= p.label.x + p.label.w && event.clientY - rect.top >= p.label.y && event.clientY - rect.top <= p.label.y + p.label.h)); if (point) { event.preventDefault(); showPoint(point, point.x, point.y); } });
        canvas.addEventListener("focus", () => showPoint(canvas._hnRadarPoints?.[0], canvas._hnRadarPoints?.[0]?.x || 8, canvas._hnRadarPoints?.[0]?.y || 8));
        canvas.addEventListener("keydown", event => { const points = canvas._hnRadarPoints || []; if (!points.length) return; const index = Math.max(0, points.findIndex(p => p.row.ticker === canvas._hnRadarActive)); const next = event.key === "ArrowRight" || event.key === "ArrowDown" ? (index + 1) % points.length : event.key === "ArrowLeft" || event.key === "ArrowUp" ? (index - 1 + points.length) % points.length : index; if (event.key.startsWith("Arrow") || event.key === "Enter" || event.key === " ") { event.preventDefault(); showPoint(points[next], points[next].x, points[next].y); } });
        canvas.addEventListener("pointerleave", hideTip);
        canvas.addEventListener("blur", hideTip);
        canvas.addEventListener("keydown", event => { if (event.key === "Escape") { event.preventDefault(); hideTip(); } });
        canvas._hnHoverBound = true;
      }
      if (typeof ResizeObserver !== "undefined" && !canvas._hnResize) {
        canvas._hnResize = new ResizeObserver(() => drawDeskRadar(canvas));
        canvas._hnResize.observe(canvas);
      }
      redrawAfterFontLoad(canvas, current => drawDeskRadar(current));
    });
  }

  function watchlistMicroHtml(rows, options = {}) {
    ensureStyles();
    const list = Array.isArray(rows) ? rows : [];
    const limit = Math.max(1, Math.min(12, toNumber(options.limit) || list.length || 6));
    const visible = list.slice(0, limit);
    if (!visible.length) return "";
    return `<div class="hn-today-visual hn-today-watch" aria-label="Watchlist price snapshots"><div class="hn-chart-source">Prices and returns use the dates shown per name.</div>
      ${visible.map(row => {
        const name = row.name ? ` <span class="sub">${esc(row.name.slice(0, 22))}</span>` : "";
        const values = Array.isArray(row.sparkline) ? row.sparkline : [];
        const sparkLabel = values.length >= 2
          ? `${row.ticker} ${pct(row.sparkChangePct)} over the provided history window`
          : `${row.ticker} has no provided history window`;
        return `<a class="hn-today-watch-row clickable" href="/ticker/${encodeURIComponent(row.ticker)}">
          <span class="hn-today-watch-name"><b>${esc(row.ticker)}</b>${name}<span class="hn-chart-source">${esc(row.priceSource || "Price")} · ${esc(row.priceAsOf || "unknown")}</span></span>
          <span class="r num">${row.price == null ? "-" : esc(row.price.toLocaleString("en", { maximumFractionDigits: 2 }))}</span>
          <canvas class="hn-today-spark" width="106" height="30" role="img" aria-label="${escAttr(sparkLabel)}" title="${escAttr(sparkLabel)}" data-values="${escAttr(seriesCsv(values))}" data-tone="${escAttr(row.direction)}"></canvas>
          <span class="r num ${toneClass(row.dayPct)}">${pct(row.dayPct)}<span class="hn-chart-source">1-session · ${esc(row.returnAsOf || "unknown")}</span></span>
        </a>`;
      }).join("")}
    </div>`;
  }

  function drawSparkline(canvas, values, options = {}) {
    if (!canvas || typeof canvas.getContext !== "function") return false;
    const points = (Array.isArray(values) ? values : []).map(toNumber).filter(isFiniteNumber);
    const w = Math.max(40, Math.floor(canvas.clientWidth || canvas.width || 106));
    const h = Math.max(18, Math.floor(canvas.clientHeight || canvas.height || 30));
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return false;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const c = palette();
    const tone = options.tone || canvas.getAttribute("data-tone") || "";
    const line = tone === "down" || tone === "dn" ? c.dn : tone === "up" ? c.up : c.ink2;
    ctx.lineCap = "square";
    ctx.lineJoin = "miter";
    ctx.strokeStyle = c.line;
    ctx.lineWidth = 1;
    ctx.globalAlpha = 0.9;
    ctx.beginPath();
    ctx.moveTo(0, Math.floor(h / 2) + 0.5);
    ctx.lineTo(w, Math.floor(h / 2) + 0.5);
    ctx.stroke();
    if (points.length < 2) {
      ctx.globalAlpha = 0.75;
      ctx.fillStyle = c.ink2;
      ctx.font = monoFont(10);
      ctx.fillText("no line", 2, h - 7);
      ctx.globalAlpha = 1;
      return false;
    }
    const lo = Math.min(...points), hi = Math.max(...points), span = hi - lo || Math.max(Math.abs(hi), 1) * 0.01;
    const x = i => points.length === 1 ? w / 2 : i / (points.length - 1) * (w - 2) + 1;
    const y = v => 2 + (1 - (v - lo) / span) * (h - 5);
    ctx.globalAlpha = 1;
    ctx.strokeStyle = line;
    ctx.lineWidth = options.lineWidth || 1.6;
    ctx.beginPath();
    points.forEach((v, i) => i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v)));
    ctx.stroke();
    ctx.fillStyle = line;
    ctx.fillRect(Math.round(x(points.length - 1)) - 1, Math.round(y(points[points.length - 1])) - 1, 3, 3);
    return true;
  }

  function mountSparklines(root) {
    const host = root && root.querySelectorAll ? root : document;
    host.querySelectorAll("canvas.hn-today-spark").forEach(canvas => {
      const values = String(canvas.getAttribute("data-values") || "")
        .split(",")
        .map(toNumber)
        .filter(isFiniteNumber);
      drawSparkline(canvas, values);
      redrawAfterFontLoad(canvas, current => drawSparkline(current, values));
    });
  }

  function sectorNameFor(code, sectorState) {
    const codes = sectorState?.codes || {};
    return codes[String(code)] || String(code || "");
  }

  function prepareSectorBreadth(data = {}, options = {}) {
    const quant = data.quant?.tickers || data.quant || {};
    const live = data.live?.tickers || data.live || {};
    const sectorState = data.sectors || {};
    const byTicker = sectorState.tickers || {};
    const readSectors = Array.isArray(data.dailyRead?.sectors) ? data.dailyRead.sectors : [];
    const stanceByName = new Map(readSectors.map(s => [String(s.name || "").toLowerCase(), s.stance || ""]));
    const buckets = new Map();

    Object.keys(quant).forEach(ticker => {
      const q = quant[ticker] || {};
      const l = live[ticker] || {};
      const sector = byTicker[ticker]?.sector || sectorNameFor(l.sector, sectorState);
      const rawRet = q.ret_1d;
      const ret = rawRet == null || rawRet === "" ? null : toNumber(rawRet);
      if (!sector || ret == null) return;
      if (!buckets.has(sector)) buckets.set(sector, { name: sector, up: 0, down: 0, flat: 0, sum: 0, count: 0, leaders: [], members: [] });
      const b = buckets.get(sector);
      if (ret > FLAT_BAND) b.up += 1;
      else if (ret < -FLAT_BAND) b.down += 1;
      else b.flat += 1;
      b.sum += ret;
      b.count += 1;
      b.leaders.push({ ticker, ret });
      b.members.push({ ticker, ret });
    });

    const minCount = Math.max(1, toNumber(options.minCount) || 3);
    return [...buckets.values()]
      .filter(b => b.count >= minCount)
      .map(b => {
        const positive = b.up / b.count * 100;
        const negative = b.down / b.count * 100;
        const flat = Math.max(0, 100 - positive - negative);
        const stance = stanceByName.get(b.name.toLowerCase()) || "";
        b.avgRet = b.count ? b.sum / b.count : null;
        b.positivePct = positive;
        b.negativePct = negative;
        b.flatPct = flat;
        b.net = b.up - b.down;
        b.netPct = b.count ? b.net / b.count * 100 : 0;
        b.stance = stance;
        b.leaders = b.leaders
          .sort((a, z) => Math.abs(z.ret) - Math.abs(a.ret))
          .slice(0, 3);
        b.members = b.members.sort((a, z) => z.ret - a.ret);
        return b;
      })
      .sort((a, b) => (b.netPct || 0) - (a.netPct || 0) || (b.avgRet || 0) - (a.avgRet || 0))
      .slice(0, Math.max(1, Math.min(12, toNumber(options.limit) || 8)));
  }

  function sectorMatrixRows(rows) {
    return (Array.isArray(rows) ? rows : []).map(row => ({
      name: String(row.name || ""),
      up: Math.max(0, Math.round(toNumber(row.up) || 0)),
      flat: Math.max(0, Math.round(toNumber(row.flat) || 0)),
      down: Math.max(0, Math.round(toNumber(row.down) || 0)),
      count: Math.max(0, Math.round(toNumber(row.count) || 0)),
      avgRet: toNumber(row.avgRet),
      netPct: toNumber(row.netPct) || 0,
      members: Array.isArray(row.members) ? row.members.map(member => ({ ticker: String(member.ticker || ""), ret: toNumber(member.ret) })).filter(member => member.ticker && member.ret != null) : [],
    })).filter(row => row.name && row.count);
  }

  function sectorBreadthHtml(rows, options = {}) {
    ensureStyles();
    const list = sectorMatrixRows(rows);
    if (!list.length) return "";
    const title = options.title || "Sector breadth";
    const payload = escAttr(JSON.stringify(list));
    const summary = list.map(row => `${row.name}: ${row.up} advancing (${Math.round(row.up / row.count * 100)}%), ${row.flat} flat (${Math.round(row.flat / row.count * 100)}%), ${row.down} declining (${Math.round(row.down / row.count * 100)}%), n=${row.count}, average ${pct(row.avgRet)}`).join("; ");
    return `<div class="hn-today-visual hn-sector-breadth" aria-label="${escAttr(title)}">
      <div class="hn-chart-heading"><b>${esc(title)}</b><span class="sub">Top ${list.length} by net breadth · min 3 names · flat ±0.05%</span><span class="hn-chart-source">${esc(sourceStamp(options.source))}</span></div><canvas class="hn-sector-matrix-canvas" tabindex="0" width="620" height="${Math.max(150, 34 + list.length * 30)}" role="img" aria-label="${escAttr(summary)}" title="${escAttr(title)}" data-rows="${payload}"></canvas><div class="hn-sector-tip" role="status" aria-live="polite" hidden></div>
      <table class="hn-sr-only">
        <caption>${esc(title)}</caption>
        <thead><tr><th>Sector</th><th>Advancing</th><th>Flat</th><th>Declining</th><th>Average 1D move</th></tr></thead>
        <tbody>${list.map(row => `<tr><th>${esc(row.name)}</th><td>${fmtInt(row.up)}</td><td>${fmtInt(row.flat)}</td><td>${fmtInt(row.down)}</td><td>${pct(row.avgRet)}</td></tr>`).join("")}</tbody>
      </table>
    </div>`;
  }

  function drawSectorBreadthMatrix(canvas, rows, options = {}) {
    if (!canvas || typeof canvas.getContext !== "function") return false;
    const list = sectorMatrixRows(rows || canvas._hnSectorRows || []);
    const w = Math.max(260, Math.floor(canvas.clientWidth || canvas.width || 620));
    const rowH = w < 460 ? 34 : 30;
    const top = 28;
    const h = Math.max(124, top + list.length * rowH + 8);
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    canvas.style.height = h + "px";
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return false;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const c = palette();
    const compact = w < 460;
    const sectorW = compact ? Math.max(92, Math.floor(w * 0.34)) : Math.max(150, Math.floor(w * 0.36));
    const avgW = compact ? 48 : 70;
    const gap = 4;
    const cellW = Math.max(34, Math.floor((w - sectorW - avgW - gap * 5) / 3));
    const cols = [
      { key: "up", label: "ADV", color: c.up },
      { key: "flat", label: "FLAT", color: c.ink2 },
      { key: "down", label: "DEC", color: c.dn },
    ];
    const maxCount = Math.max(1, ...list.flatMap(row => cols.map(col => row[col.key] || 0)));
    const maxAvg = Math.max(0.2, ...list.map(row => Math.abs(row.avgRet || 0)));
    canvas._hnSectorHits = [];

    ctx.fillStyle = c.ink2;
    ctx.font = monoFont(10);
    ctx.textBaseline = "middle";
    ctx.fillText("SECTOR", 0, 12);
    cols.forEach((col, i) => ctx.fillText(col.label, sectorW + gap + i * (cellW + gap), 12));
    ctx.fillText("AVG", w - avgW + 4, 12);
    ctx.strokeStyle = c.line;
    ctx.globalAlpha = 0.9;
    ctx.beginPath();
    ctx.moveTo(0, top - 8.5);
    ctx.lineTo(w, top - 8.5);
    ctx.stroke();

    list.forEach((row, r) => {
      const y = top + r * rowH;
      canvas._hnSectorHits.push({ y, h: rowH, row });
      ctx.globalAlpha = 1;
      ctx.fillStyle = c.ink;
      ctx.font = compact ? monoFont(10) : monoFont(11);
      const label = row.name.length > (compact ? 14 : 24) ? row.name.slice(0, compact ? 13 : 23) + "." : row.name;
      ctx.fillText(label, 0, y + rowH / 2);

      cols.forEach((col, i) => {
        const n = row[col.key] || 0;
        const x = sectorW + gap + i * (cellW + gap);
        const intensity = clamp(n / maxCount, 0, 1);
        ctx.globalAlpha = col.key === "flat" ? 0.08 + intensity * 0.16 : 0.10 + intensity * 0.58;
        ctx.fillStyle = col.color;
        ctx.fillRect(x, y + 3, cellW, rowH - 6);
        ctx.globalAlpha = 1;
        ctx.strokeStyle = c.line;
        ctx.lineWidth = 1;
        ctx.strokeRect(x + 0.5, y + 3.5, cellW - 1, rowH - 7);
        ctx.fillStyle = col.key === "flat" ? c.ink : col.color;
        ctx.font = monoFont(12);
        ctx.textAlign = "center";
        ctx.fillText(String(n), x + cellW / 2, y + rowH / 2);
        ctx.textAlign = "start";
      });

      const avg = row.avgRet || 0;
      const avgX = w - avgW + 4;
      const markerW = Math.max(6, Math.round((Math.abs(avg) / maxAvg) * (avgW - 18)));
      ctx.globalAlpha = 1;
      ctx.fillStyle = avg > FLAT_BAND ? c.up : avg < -FLAT_BAND ? c.dn : c.ink2;
      ctx.fillRect(avgX, y + rowH - 9, markerW, 3);
      ctx.font = monoFont(11);
      ctx.fillText(pct(row.avgRet), avgX, y + rowH / 2 - 2);
      if (canvas._hnSectorActive === row.name) {
        ctx.strokeStyle = c.ink;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(0.5, y + 1.5, w - 1, rowH - 3);
      }
    });
    ctx.globalAlpha = 1;
    return true;
  }

  function mountSectorBreadthMatrix(root) {
    const host = root && root.querySelectorAll ? root : document;
    host.querySelectorAll("canvas.hn-sector-matrix-canvas").forEach(canvas => {
      let rows = [];
      try { rows = JSON.parse(canvas.getAttribute("data-rows") || "[]"); } catch { rows = []; }
      canvas._hnSectorRows = rows;
      drawSectorBreadthMatrix(canvas, rows);
      if (!canvas._hnSectorHoverBound) {
        const tip = canvas.parentElement?.querySelector(".hn-sector-tip");
        let activeHit = null, pinned = false, tipHover = false, focusWithin = false, canvasFocused = false, hideTimer = null;
        const scheduleHide = () => { clearTimeout(hideTimer); hideTimer = setTimeout(() => { if (!pinned && !tipHover && !focusWithin && !canvasFocused) hide(); }, 120); };
        const show = (hit, y = 8) => {
          if (!tip || !hit) return;
          clearTimeout(hideTimer);
          const row = hit.row, share = key => Math.round((row[key] / row.count) * 100);
          if (!activeHit || activeHit.row.name !== row.name) {
            const members = (row.members || []).slice().sort((a, b) => b.ret - a.ret);
            const names = members.map(member => `<a href="/ticker/${encodeURIComponent(member.ticker)}" class="hn-sector-member ${member.ret > FLAT_BAND ? "up" : member.ret < -FLAT_BAND ? "dn" : "flat"}">${esc(member.ticker)} <span>${esc(pct(member.ret))}</span></a>`).join("");
            tip.innerHTML = `<b>${esc(row.name)}</b><span>n=${row.count} · ${row.up} advancing (${share("up")}%) · ${row.flat} flat (${share("flat")}%) · ${row.down} declining (${share("down")}%)</span><span>Average 1D ${esc(pct(row.avgRet))}</span>${names ? `<div class="hn-sector-members">${names}</div>` : ""}`;
            activeHit = hit;
            canvas._hnSectorActive = row.name;
            drawSectorBreadthMatrix(canvas);
          }
          tip.style.top = clamp(y + 8, 8, Math.max(8, canvas.clientHeight - 72)) + "px";
          tip.hidden = false;
        };
        const hide = () => { clearTimeout(hideTimer); activeHit = null; pinned = false; canvas._hnSectorActive = null; drawSectorBreadthMatrix(canvas); if (tip) tip.hidden = true; };
        const hitAt = event => {
          const rect = canvas.getBoundingClientRect(), py = event.clientY - rect.top;
          return (canvas._hnSectorHits || []).find(hit => py >= hit.y && py <= hit.y + hit.h);
        };
        canvas.addEventListener("pointermove", event => { const hit = hitAt(event); if (hit) show(hit, hit.y); else if (!pinned) scheduleHide(); });
        canvas.addEventListener("pointerdown", event => { const hit = hitAt(event); if (hit) { event.preventDefault(); pinned = true; show(hit, hit.y); } });
        canvas.addEventListener("pointerleave", scheduleHide);
        tip?.addEventListener("pointerenter", () => { tipHover = true; clearTimeout(hideTimer); });
        tip?.addEventListener("pointerleave", () => { tipHover = false; scheduleHide(); });
        canvas.addEventListener("focus", () => { canvasFocused = true; show(canvas._hnSectorHits?.[0], 8); });
        canvas.addEventListener("blur", event => { canvasFocused = false; if (event.relatedTarget && tip?.contains?.(event.relatedTarget)) return; if (!pinned) scheduleHide(); });
        tip?.addEventListener("focusin", () => { focusWithin = true; clearTimeout(hideTimer); });
        tip?.addEventListener("focusout", event => { if (event.relatedTarget === canvas || tip?.contains?.(event.relatedTarget)) return; focusWithin = false; if (!pinned) scheduleHide(); });
        if (!canvas._hnSectorDocBound && typeof document !== "undefined") {
          document.addEventListener("pointerdown", event => { if (event.target !== canvas && !tip?.contains?.(event.target)) hide(); });
          canvas._hnSectorDocBound = true;
        }
        canvas.addEventListener("keydown", event => {
          const hits = canvas._hnSectorHits || []; if (!hits.length) return;
          const current = Number(canvas.dataset.hnSectorFocus || 0);
          if (event.key === "ArrowDown" || event.key === "ArrowRight") { event.preventDefault(); canvas.dataset.hnSectorFocus = String((current + 1) % hits.length); show(hits[(current + 1) % hits.length], hits[(current + 1) % hits.length].y); }
          else if (event.key === "ArrowUp" || event.key === "ArrowLeft") { event.preventDefault(); const next = (current - 1 + hits.length) % hits.length; canvas.dataset.hnSectorFocus = String(next); show(hits[next], hits[next].y); }
          else if (event.key === "Enter" || event.key === " ") { event.preventDefault(); pinned = true; show(hits[current], hits[current].y); }
          else if (event.key === "Escape") { event.preventDefault(); hide(); }
        });
        canvas._hnSectorHoverBound = true;
      }
      if (typeof ResizeObserver !== "undefined" && !canvas._hnResize) {
        canvas._hnResize = new ResizeObserver(() => drawSectorBreadthMatrix(canvas));
        canvas._hnResize.observe(canvas);
      }
      redrawAfterFontLoad(canvas, current => drawSectorBreadthMatrix(current));
    });
  }

  function renderSectorBreadth(host, rows, options) {
    if (!host) return false;
    host.innerHTML = sectorBreadthHtml(rows, options);
    mountSectorBreadthMatrix(host);
    return true;
  }

  function prepareCatalysts(dailyRead = {}, options = {}) {
    dailyRead = dailyRead || {};
    const today = String(options.today || dailyRead.date || "").slice(0, 10);
    const items = Array.isArray(dailyRead) ? dailyRead : Array.isArray(dailyRead.catalysts) ? dailyRead.catalysts : [];
    return items.map((item, i) => {
      const date = String(item?.date || "").slice(0, 10);
      const tickers = Array.isArray(item?.which_tickers) ? item.which_tickers.filter(Boolean).map(String) : [];
      const status = today && date ? (date < today ? "past" : date === today ? "today" : "upcoming") : "unknown";
      return {
        date,
        event: String(item?.event || ""),
        tickers,
        status,
        order: i,
      };
    }).filter(item => item.date || item.event)
      .sort((a, b) => (a.date || "9999").localeCompare(b.date || "9999") || a.order - b.order);
  }

  function catalystTimelineHtml(items, options = {}) {
    ensureStyles();
    const list = (Array.isArray(items) ? items : []).slice(0, Math.max(1, Math.min(10, toNumber(options.limit) || 6)));
    if (!list.length) return "";
    return `<div class="hn-today-visual hn-catalyst-timeline" aria-label="Catalyst timeline">
      ${list.map(item => {
        const cls = item.status === "today" ? "ok" : item.status === "past" ? "bad" : "";
        const tickers = item.tickers.length ? `<span class="sub">${esc(item.tickers.slice(0, 4).join(", "))}</span>` : "";
        return `<div class="hn-catalyst-row">
          <span class="pill hn-catalyst-date ${cls}">${esc(item.date || "-")}</span>
          <span class="hn-catalyst-copy"><b>${esc(item.event || "Catalyst")}</b>${tickers ? "<br>" + tickers : ""}</span>
          <span class="tag">${esc(item.status)}</span>
        </div>`;
      }).join("")}
    </div>`;
  }

  function enhance(root, data = {}, options = {}) {
    const host = root && root.querySelector ? root : document;
    const out = {};
    const indexHost = host.querySelector("[data-hn-today-index]");
    if (indexHost) {
      const indexOptions = { ...(options.index || {}) };
      if (options.compact != null && indexOptions.compact == null) indexOptions.compact = options.compact;
      if (!indexOptions.source) indexOptions.source = data.index?.updated || data.index?.date;
      const model = prepareIndexTrend(data.index || {}, indexOptions);
      indexHost.innerHTML = indexTrendHtml(model, indexOptions);
      mountIndexTrend(indexHost);
      out.index = model.values.length;
    }
    const watchHost = host.querySelector("[data-hn-today-watch]");
    if (watchHost) {
      const watchSymbols = data.watchlistSymbols || data.watchlist || [];
      const rows = prepareWatchlistRows(watchSymbols, data, options.watchlist || {});
      watchHost.innerHTML = watchlistMicroHtml(rows, { ...(options.watchlist || {}), source: data.live?.source_at || "unknown" });
      mountSparklines(watchHost);
      out.watchlist = rows.length;
    }
    const sectorHost = host.querySelector("[data-hn-sector-breadth]");
    if (sectorHost) {
      const rows = prepareSectorBreadth(data, options.sectors || {});
      renderSectorBreadth(sectorHost, rows, { ...(options.sectors || {}), source: data.quant?.updated });
      out.sectors = rows.length;
    }
    const radarHost = host.querySelector("[data-hn-desk-radar]");
    if (radarHost) {
      const radarRows = data.deskRadar || data.radar || data.dailyRead?.watchlist || data.daily_read?.watchlist || [];
      const rows = prepareDeskRadar(radarRows, options.radar || {});
      radarHost.innerHTML = deskRadarHtml(rows, { ...(options.radar || {}), source: data.dashboard?.updated || data.dailyRead?.date });
      mountDeskRadar(radarHost);
      out.radar = rows.length;
    }
    const catalystHost = host.querySelector("[data-hn-catalysts]");
    if (catalystHost) {
      const catalystSource = data.dailyRead || data.daily_read || data.catalysts || {};
      const catalystOptions = { ...(options.catalysts || {}) };
      if (!catalystOptions.today && (data.dailyRead?.date || data.daily_read?.date)) catalystOptions.today = data.dailyRead?.date || data.daily_read?.date;
      const rows = prepareCatalysts(catalystSource, catalystOptions);
      catalystHost.innerHTML = catalystTimelineHtml(rows, options.catalysts || {});
      out.catalysts = rows.length;
    }
    return out;
  }

  window[NS] = {
    version: API_VERSION,
    prepareWatchlistRows,
    prepareIndexTrend,
    indexTrendHtml,
    drawIndexTrend,
    mountIndexTrend,
    watchlistMicroHtml,
    drawSparkline,
    mountSparklines,
    prepareDeskRadar,
    deskRadarHtml,
    drawDeskRadar,
    mountDeskRadar,
    prepareSectorBreadth,
    sectorBreadthHtml,
    drawSectorBreadthMatrix,
    mountSectorBreadthMatrix,
    renderSectorBreadth,
    prepareCatalysts,
    catalystTimelineHtml,
    enhance,
    invalidatePalette,
  };
})();
