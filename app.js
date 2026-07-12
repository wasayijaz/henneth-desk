/* PSX Trade Desk SPA — hash router, 4 themes, canvas charts.
   Routes: #/board · #/ticker/SYM · #/dividends · #/news
   All data from ../state/*.json (DPS-sourced). No external deps. */

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
const sgn = v => (v > 0 ? "+" : "") + v;
const cls = v => v > 0.05 ? "up" : v < -0.05 ? "dn" : "";
const fmt = (v, d = 2) => v == null ? "—" : Number(v).toLocaleString("en", { maximumFractionDigits: d });

// Data source: local dev reads ../state/ ; the deployed dashboard (GitHub Pages)
// reads state/ published alongside it by the GitHub Actions pipeline every 30 min.
const LOCAL = ["localhost", "127.0.0.1", ""].includes(location.hostname);
const DATA_BASE = LOCAL ? "../state/" : "state/";

const cache = {};
async function j(p, ttl = 25000) {
  const now = Date.now();
  if (cache[p] && now - cache[p].t < ttl) return cache[p].v;
  try {
    const r = await fetch(DATA_BASE + p + "?t=" + now);
    const v = r.ok ? await r.json() : null;
    cache[p] = { t: now, v };
    return v;
  } catch { return null; }
}

/* ---------- header chips ---------- */
function marketStatus() {
  const d = new Date(), day = d.getDay(), m = d.getHours() * 60 + d.getMinutes();
  const bt = (a, b) => m >= a && m <= b;
  if (day === 0 || day === 6) return ["WEEKEND", false];
  if (day === 5) return bt(557, 720) || bt(872, 990) ? ["LIVE", true] : ["CLOSED", false];
  return bt(572, 930) ? ["LIVE", true] : ["CLOSED", false];
}
async function renderHeader() {
  const [health, quant, live, macro, dash] = await Promise.all([j("health.json"), j("quant.json"), j("live.json"), j("macro.json"), j("dashboard.json")]);
  const [mt, mo] = marketStatus();
  $("mkt").textContent = "PSX " + mt; $("mkt").className = "pill " + (mo ? "ok" : "");
  if (health) { $("health").textContent = "HEALTH " + health.status.toUpperCase(); $("health").className = "pill " + (health.status === "ok" ? "ok" : "bad"); $("health").title = (health.problems || []).join("; "); }
  const reg = macro?.regime || "—";
  $("regime").textContent = "REGIME: " + reg.toUpperCase(); $("regime").className = "pill clickable " + (reg === "risk-off" ? "bad" : reg === "risk-on" ? "ok" : "");
  $("regime").onclick = () => location.hash = "#/macro";
  const geo = dash?.geo_risk;
  const gc = $("georisk");
  if (gc && geo?.score != null) {
    gc.style.display = "";
    gc.textContent = "RISK " + geo.score;
    gc.className = "pill clickable " + (geo.band === "elevated" ? "bad" : geo.band === "calm" ? "ok" : "");
    gc.title = `Geopolitical & market-stress radar: ${geo.score}/100 (${geo.band}). Click for the factors.`;
    gc.onclick = () => location.hash = "#/macro";
  } else if (gc) { gc.style.display = "none"; }
  $("regime").title = reg === "—" ? "Macro regime — run the desk to populate" :
    `Macro regime = the desk's risk posture (${reg}). ${reg === "risk-on" ? "Full setups allowed." : reg === "risk-off" ? "Max 2 setups, defensive only." : "Neutral — normal caution."} Click for the drivers.`;
  $("updated").textContent = "quant " + (quant?.updated || "—") + " · live " + (live?.updated || "—");
}

/* ---------- canvas chart ---------- */
function drawChart(canvas, tooltip, hist, days) {
  const rows = hist.slice(-days);
  const W = canvas.clientWidth, H = canvas.clientHeight || 320;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext("2d"); ctx.scale(dpr, dpr);
  const css = getComputedStyle(document.body);
  const up = css.getPropertyValue("--up").trim(), dn = css.getPropertyValue("--dn").trim();
  const accent = css.getPropertyValue("--accent").trim();
  const ink = css.color;
  const padL = 8, padR = 56, padT = 10, volH = 46, plotH = H - volH - 26;

  const closes = rows.map(r => r.close), vols = rows.map(r => r.volume);
  const lo = Math.min(...closes), hi = Math.max(...closes), span = (hi - lo) || 1;
  const vmax = Math.max(...vols) || 1;
  const X = i => padL + i / (rows.length - 1) * (W - padL - padR);
  const Y = v => padT + (1 - (v - lo) / span) * plotH;

  ctx.clearRect(0, 0, W, H);
  // gridlines + right axis labels
  ctx.globalAlpha = .35; ctx.strokeStyle = ink; ctx.lineWidth = .5;
  ctx.font = "10px sans-serif"; ctx.fillStyle = ink;
  for (let g = 0; g <= 3; g++) {
    const v = lo + span * g / 3, y = Y(v);
    ctx.globalAlpha = .12; ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
    ctx.globalAlpha = .55; ctx.fillText(fmt(v), W - padR + 6, y + 3);
  }
  ctx.globalAlpha = 1;
  // volume bars
  const pos = closes[closes.length - 1] >= closes[0];
  rows.forEach((r, i) => {
    ctx.fillStyle = (i > 0 && r.close >= rows[i - 1].close) ? up : dn;
    ctx.globalAlpha = .45;
    const bh = (r.volume / vmax) * volH;
    ctx.fillRect(X(i) - 1, H - 20 - bh, 2, bh);
  });
  ctx.globalAlpha = 1;
  // price line + soft area
  const lineC = pos ? up : dn;
  ctx.beginPath();
  rows.forEach((r, i) => i ? ctx.lineTo(X(i), Y(r.close)) : ctx.moveTo(X(i), Y(r.close)));
  ctx.strokeStyle = lineC; ctx.lineWidth = 2; ctx.stroke();
  ctx.lineTo(X(rows.length - 1), padT + plotH); ctx.lineTo(X(0), padT + plotH); ctx.closePath();
  ctx.globalAlpha = .08; ctx.fillStyle = lineC; ctx.fill(); ctx.globalAlpha = 1;
  // date ticks
  ctx.fillStyle = ink; ctx.globalAlpha = .55;
  [0, Math.floor(rows.length / 2), rows.length - 1].forEach(i => {
    ctx.fillText(rows[i].date, Math.min(X(i), W - padR - 58), H - 6);
  });
  ctx.globalAlpha = 1;

  canvas.onmousemove = e => {
    const rect = canvas.getBoundingClientRect();
    const i = Math.round((e.clientX - rect.left - padL) / (W - padL - padR) * (rows.length - 1));
    if (i < 0 || i >= rows.length) { tooltip.style.display = "none"; return; }
    const r = rows[i];
    tooltip.style.display = "block";
    tooltip.style.left = Math.min(e.clientX - rect.left + 12, W - 150) + "px";
    tooltip.style.top = "8px";
    const chg = i ? ((r.close / rows[i - 1].close - 1) * 100) : 0;
    tooltip.innerHTML = `<b>${r.date}</b><br>close ${fmt(r.close)} <span class="${cls(chg)}">${sgn(chg.toFixed(2))}%</span><br>vol ${fmt(r.volume, 0)}`;
  };
  canvas.onmouseleave = () => tooltip.style.display = "none";
}

function drawIntraday(canvas, tooltip, points, prevClose) {
  const W = canvas.clientWidth, H = canvas.clientHeight || 320, dpr = window.devicePixelRatio || 1;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext("2d"); ctx.scale(dpr, dpr);
  const css = getComputedStyle(document.body);
  const up = css.getPropertyValue("--up").trim(), dn = css.getPropertyValue("--dn").trim(), ink = css.color;
  const padL = 8, padR = 56, padT = 12, plotH = H - 40;
  const prices = points.map(p => p.p);
  const lo = Math.min(prevClose, ...prices), hi = Math.max(prevClose, ...prices), span = (hi - lo) || 1;
  const X = i => padL + i / (points.length - 1) * (W - padL - padR);
  const Y = v => padT + (1 - (v - lo) / span) * plotH;
  ctx.clearRect(0, 0, W, H);
  ctx.font = "10px sans-serif"; ctx.fillStyle = ink;
  for (let g = 0; g <= 3; g++) { const v = lo + span * g / 3, y = Y(v); ctx.globalAlpha = .1; ctx.strokeStyle = ink; ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke(); ctx.globalAlpha = .55; ctx.fillText(fmt(v), W - padR + 6, y + 3); }
  ctx.globalAlpha = .5; ctx.strokeStyle = ink; ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(padL, Y(prevClose)); ctx.lineTo(W - padR, Y(prevClose)); ctx.stroke(); ctx.setLineDash([]); ctx.globalAlpha = 1;
  const pos = prices[prices.length - 1] >= prevClose, lineC = pos ? up : dn;
  ctx.beginPath(); points.forEach((p, i) => i ? ctx.lineTo(X(i), Y(p.p)) : ctx.moveTo(X(i), Y(p.p)));
  ctx.strokeStyle = lineC; ctx.lineWidth = 1.8; ctx.stroke();
  ctx.lineTo(X(points.length - 1), padT + plotH); ctx.lineTo(X(0), padT + plotH); ctx.closePath();
  ctx.globalAlpha = .08; ctx.fillStyle = lineC; ctx.fill(); ctx.globalAlpha = 1;
  const tlabel = t => new Date(t * 1000).toLocaleTimeString("en", { hour: "2-digit", minute: "2-digit" });
  ctx.fillStyle = ink; ctx.globalAlpha = .55;
  [0, Math.floor(points.length / 2), points.length - 1].forEach(i => ctx.fillText(tlabel(points[i].t), Math.min(X(i), W - padR - 40), H - 6));
  ctx.globalAlpha = 1;
  canvas.onmousemove = e => {
    const rect = canvas.getBoundingClientRect();
    const i = Math.round((e.clientX - rect.left - padL) / (W - padL - padR) * (points.length - 1));
    if (i < 0 || i >= points.length) { tooltip.style.display = "none"; return; }
    const p = points[i], chg = (p.p / prevClose - 1) * 100;
    tooltip.style.display = "block"; tooltip.style.left = Math.min(e.clientX - rect.left + 12, W - 140) + "px"; tooltip.style.top = "8px";
    tooltip.innerHTML = `<b>${tlabel(p.t)}</b><br>${fmt(p.p)} <span class="${cls(chg)}">${sgn(chg.toFixed(2))}%</span>`;
  };
  canvas.onmouseleave = () => tooltip.style.display = "none";
}

/* ---------- pages ---------- */
function globalStrip(gl) {
  const inst = gl?.instruments || {};
  const order = ["BZ=F", "^GSPC", "^DJI", "^VIX", "GC=F", "BTC-USD", "ETH-USD", "PKR=X", "DX-Y.NYB"];
  const items = order.filter(s => inst[s]).map(s => {
    const v = inst[s];
    return `<div class="gitem" title="${esc(v.psx_read)}"><span>${esc(v.label)}</span>
      <b class="num">${fmt(v.price)}</b><i class="num ${cls(v.chg_1d_pct)}">${sgn(v.chg_1d_pct)}%</i></div>`;
  }).join("");
  return items ? `<div class="gstrip clickable" onclick="location.hash='#/macro'">${items}</div>` : "";
}

async function pageBoard() {
  const [quant, pred, dash, news, pos, smap, trig, live, gl] = await Promise.all([
    j("quant.json"), j("predictability.json"), j("dashboard.json"), j("newslog.json"),
    j("positions.json"), j("strategy_map.json"), j("live_triggers.json"), j("live.json"), j("global.json")]);
  const q = quant?.tickers || {};
  const lv = live?.tickers || {};

  const sigs = dash?.signals || [];
  const sigHtml = sigs.length ? sigs.map(s => `
    <div class="card clickable" onclick="location.hash='#/ticker/${esc(s.ticker)}'">
      <div class="tk-head"><span class="sym">${esc(s.ticker)}</span><span class="tag">${esc(s.template || "")}</span>
      ${s.audit === "PASS" ? '<span class="tag badge-ok up">audited ✓</span>' : ""}</div>
      <div class="statgrid num">
        <div class="stat"><span>entry</span><b>${s.entry}</b></div>
        <div class="stat"><span>stop</span><b class="dn">${s.stop}</b></div>
        <div class="stat"><span>target</span><b class="up">${s.target}</b></div>
        <div class="stat"><span>size</span><b>${s.size_shares ?? "—"} sh</b></div>
      </div><div class="sub" style="margin-top:8px">${esc(s.thesis || "")}</div></div>`).join("")
    : `<div class="card"><div class="empty">No active signals — desk is selective. Signals appear after an audited full cycle.</div></div>`;

  const tg = trig?.triggers || [];
  const trigHtml = tg.length ? `<div class="card"><h2>Live triggers</h2><div class="sub">proven patterns firing now · unvetted</div>
    <table><thead><tr><th>Ticker</th><th>Template</th><th class="r">Price</th><th class="r">Hist</th><th class="r">When</th></tr></thead><tbody>${
      tg.map(t => `<tr class="clickable" onclick="location.hash='#/ticker/${esc(t.ticker)}'"><td><b>${esc(t.ticker)}</b></td><td>${esc(t.template)}</td>
      <td class="r num">${t.price}</td><td class="r num">${Math.round(t.backtest.hit_rate * 100)}%·n${t.backtest.n}</td><td class="r num">${t.ts}</td></tr>`).join("")}</tbody></table></div>` : "";

  const heat = Object.entries(q).sort((a, b) => b[1].ret_1d - a[1].ret_1d).map(([s, v]) => {
    const a = Math.min(Math.abs(v.ret_1d) / 5, 1) * 0.5;
    const col = v.ret_1d > 0.05 ? "var(--up)" : v.ret_1d < -0.05 ? "var(--dn)" : null;
    const bg = col ? `style="background:color-mix(in srgb, ${col} ${Math.round(a * 100)}%, transparent)"` : "";
    return `<div class="cell clickable" ${bg} onclick="location.hash='#/ticker/${s}'" title="RSI ${v.rsi14} · 20d ${sgn(v.ret_20d)}%">
      <b>${s}</b><span class="px num">${fmt(lv[s]?.current ?? v.close)}</span><span class="num ${cls(v.ret_1d)}">${sgn(v.ret_1d)}%</span></div>`;
  }).join("");

  const sm = Object.entries(smap?.tickers || {}).flatMap(([s, l]) => l.map(t => ({ s, ...t })))
    .sort((a, b) => b.net_expectancy_pct - a.net_expectancy_pct).slice(0, 12);
  const pt = Object.entries(pred?.tickers || {}).sort((a, b) => b[1].score - a[1].score).slice(0, 10);
  const nn = (news || []).slice(-10).reverse();
  const aw = dash?.agent_wire || [];
  const op = pos?.open || [];

  $("view").innerHTML = `${globalStrip(gl)}<div class="grid-board">
    <div class="cards">
      ${sigHtml}${trigHtml}
      <div class="card"><h2>Positions</h2><div class="sub"></div>${op.length ? `<table><thead><tr><th>Ticker</th><th class="r">Entry</th><th class="r">Last</th><th class="r">P/L</th><th>Status</th></tr></thead><tbody>${
        op.map(p => `<tr class="clickable" onclick="location.hash='#/ticker/${esc(p.ticker)}'"><td><b>${esc(p.ticker)}</b></td><td class="r num">${p.entry}</td><td class="r num">${p.last_price ?? "—"}</td><td class="r num ${cls(p.unrealized_pct || 0)}">${p.unrealized_pct != null ? sgn(p.unrealized_pct) + "%" : "—"}</td><td>${esc(p.status || "HOLD")}</td></tr>`).join("")}</tbody></table>` : '<div class="empty">Flat — no open positions.</div>'}</div>
      <div class="card"><h2>Proven strategies</h2><div class="sub">cleared backtest + out-of-sample bars · click through</div>
        <table><thead><tr><th>Ticker</th><th>Template</th><th class="r">Hit</th><th class="r">Net</th><th class="r">n</th></tr></thead><tbody>${
        sm.map(t => `<tr class="clickable" onclick="location.hash='#/ticker/${t.s}'"><td><b>${t.s}</b></td><td><span class="tag">${esc(t.template)}</span></td><td class="r num">${Math.round(t.hit_rate * 100)}%</td><td class="r num up">${sgn(t.net_expectancy_pct)}%</td><td class="r num">${t.n}</td></tr>`).join("")}</tbody></table></div>
    </div>
    <div class="cards">
      <div class="card"><h2>Universe</h2><div class="sub">day move · click any name</div><div class="heat">${heat}</div></div>
      <div class="card"><h2>Predictability</h2><div class="sub"></div><table><thead><tr><th>Ticker</th><th class="r">Score</th><th class="r">RSI</th><th class="r">20d</th></tr></thead><tbody>${
        pt.map(([s, v]) => `<tr class="clickable" onclick="location.hash='#/ticker/${s}'"><td><b>${s}</b></td><td class="r num">${v.score}</td><td class="r num">${q[s]?.rsi14 ?? "—"}</td><td class="r num ${cls(q[s]?.ret_20d || 0)}">${q[s] ? sgn(q[s].ret_20d) + "%" : "—"}</td></tr>`).join("")}</tbody></table></div>
      <div class="card"><h2>News wire</h2><div class="sub"><a href="#/news">full wire →</a></div><div class="wire">${
        nn.length ? nn.map(n => `<p><span class="tag">${n.impact ?? ""}</span> <span class="t">${esc((n.ts || "").slice(5, 16))}</span><b>${(n.tickers || []).join(", ")}</b> ${esc(n.headline || n.summary || "")}</p>`).join("") : '<div class="empty">Wire silent.</div>'}</div></div>
      <div class="card"><h2>Agent wire</h2><div class="sub">this cycle</div><div class="wire">${
        aw.length ? aw.map(a => `<p><b style="color:var(--accent)">${esc(a.agent)}</b> ${esc(a.summary)}</p>`).join("") : '<div class="empty">No cycle run yet.</div>'}</div></div>
    </div>
  </div>`;
}

async function pageMacro() {
  const [gl, macro, geo] = await Promise.all([j("global.json"), j("macro.json"), j("georisk.json")]);
  const inst = gl?.instruments || {};
  const groups = {
    energy: "Energy — oil drives Pakistan's import bill, PKR & inflation",
    risk: "Global risk appetite — frontier flows follow",
    safe_haven: "Safe haven",
    crypto: "Crypto — global liquidity / retail risk barometer",
    fx: "Currency — the biggest macro lever for PSX",
  };
  const card = (gk, title) => {
    const rows = Object.entries(inst).filter(([, v]) => v.group === gk);
    if (!rows.length) return "";
    return `<div class="card"><h2>${esc(title)}</h2><table><thead><tr><th>Instrument</th><th class="r">Price</th><th class="r">1d</th><th class="r">1mo</th><th>PSX read-through</th></tr></thead><tbody>${
      rows.map(([s, v]) => `<tr><td><b>${esc(v.label)}</b></td><td class="r num">${fmt(v.price)}</td>
        <td class="r num ${cls(v.chg_1d_pct)}">${sgn(v.chg_1d_pct)}%</td>
        <td class="r num ${cls(v.chg_1mo_pct)}">${sgn(v.chg_1mo_pct)}%</td>
        <td class="sub" style="max-width:340px">${esc(v.psx_read)}${v.stale ? ' <span class="tag">stale</span>' : ""}</td></tr>`).join("")}</tbody></table></div>`;
  };

  const m = macro || {};
  const dom = m.domestic || {};
  const drivers = m.drivers || [];
  const macroCard = `<div class="card"><h2>Pakistan macro</h2>
    <div class="sub">regime <b>${esc((m.regime || "—").toUpperCase())}</b> · ${esc(m.global_read || "")} · updated ${esc(m.updated || "—")} ${m.updated ? "" : "(run macro-agent to populate)"}</div>
    <div class="facts">
      <div class="fact"><span>SBP policy rate</span><b>${esc(m.sbp_rate ?? "—")}</b></div>
      <div class="fact"><span>CPI YoY</span><b>${esc(m.cpi_yoy ?? "—")}</b></div>
      <div class="fact"><span>FX reserves</span><b>${esc(m.reserves_usd_bn ? "$" + m.reserves_usd_bn + "bn" : "—")}</b></div>
      <div class="fact"><span>6m T-bill</span><b>${esc(dom.tbill_6m ?? "—")}</b></div>
      <div class="fact"><span>10y PIB</span><b>${esc(dom.pib_10y ?? "—")}</b></div>
      <div class="fact"><span>Remittances</span><b>${esc(dom.remittances || "—")}</b></div>
    </div>
    ${dom.debt_note ? `<p class="sub" style="margin-top:10px"><b>Debt/borrowing:</b> ${esc(dom.debt_note)}</p>` : ""}
    ${drivers.length ? `<div class="sub" style="margin-top:10px"><b>Drivers:</b><ul style="margin:6px 0 0 16px">${drivers.map(d => `<li>${esc(d)}</li>`).join("")}</ul></div>` : ""}
    ${(m.next_events || []).length ? `<p class="sub" style="margin-top:8px"><b>Next:</b> ${m.next_events.map(e => `${esc(e.date)} ${esc(e.event)}`).join(" · ")}</p>` : ""}
    ${(m.sector_tilt) ? `<p class="sub" style="margin-top:8px"><b class="up">Favored:</b> ${(m.sector_tilt.favored || []).join(", ") || "—"} · <b class="dn">Avoid:</b> ${(m.sector_tilt.avoid || []).join(", ") || "—"}</p>` : ""}</div>`;

  // geo-risk radar (worldmonitor-style, from free signals)
  const geoCard = geo ? (() => {
    const band = geo.band, col = band === "elevated" ? "var(--dn)" : band === "calm" ? "var(--up)" : "var(--accent)";
    const bar = s => `<div style="height:6px;border-radius:3px;background:var(--line2);overflow:hidden"><div style="height:100%;width:${s}%;background:${s >= 65 ? "var(--dn)" : s <= 40 ? "var(--up)" : "var(--accent)"};transform-origin:left"></div></div>`;
    return `<div class="card"><div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:6px">
      <h2>Geopolitical & risk radar</h2>
      <span class="pill" style="background:color-mix(in srgb,${col} 15%,transparent);color:${col}">${geo.score}/100 · ${esc(band)}</span></div>
      <div class="sub" style="color:var(--ink2);margin-bottom:14px">${esc(geo.read)} <span style="opacity:.7">· ${esc(geo.source)}</span></div>
      <table><tbody>${geo.factors.map(f => `<tr>
        <td style="width:150px"><b>${esc(f.factor)}</b></td>
        <td class="num" style="width:150px">${esc(f.value)}</td>
        <td style="width:90px" class="r num">${f.stress}</td>
        <td style="min-width:110px">${bar(f.stress)}</td>
        <td class="sub" style="color:var(--ink2)">${esc(f.read)}</td></tr>`).join("")}</tbody></table>
      ${geo.sector_pressure?.length ? `<p class="sub" style="margin-top:12px"><b>Sector read-through:</b> ${geo.sector_pressure.map(esc).join(" · ")}</p>` : ""}
      ${geo.upgrade_note ? `<p class="sub" style="margin-top:8px;opacity:.7">${esc(geo.upgrade_note)}</p>` : ""}</div>`;
  })() : "";

  $("view").innerHTML = `
    <div class="seg" style="margin-top:4px"><h2>What moves PSX</h2><div class="ln"></div></div>
    <p class="sub" style="margin-bottom:14px">Global markets refreshed every cycle (Yahoo Finance). Pakistan-domestic numbers verified by the macro-agent from primary sources. Hover any read-through for why it matters.</p>
    ${geoCard}
    ${macroCard}
    ${card("fx", groups.fx)}
    ${card("energy", groups.energy)}
    ${card("risk", groups.risk)}
    ${card("crypto", groups.crypto)}
    ${card("safe_haven", groups.safe_haven)}`;
}

async function pageToday() {
  const [dr, gl] = await Promise.all([j("daily_read.json"), j("global.json")]);
  if (!dr) { $("view").innerHTML = `<div class="seg" style="margin-top:4px"><h2>Daily read</h2><div class="ln"></div></div><div class="card"><div class="empty">The daily read is written by the market-analyst agent in the pre-market cycle. Run a full cycle to generate today's note.</div></div>`; return; }
  const toneClass = { constructive: "ok", defensive: "bad", cautious: "bad" }[dr.tone] || "";
  const stanceTag = s => `<span class="pill ${s === "favoured" ? "ok" : s === "avoid" ? "bad" : ""}">${esc(s)}</span>`;
  $("view").innerHTML = `
  ${globalStrip(gl)}
  <div class="card">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px"><span class="pill ${toneClass}">${esc((dr.tone || "").toUpperCase())}</span><span class="sub">${esc(dr.date || "")}</span></div>
    <h2 style="font-size:22px;line-height:1.3;margin-bottom:12px">${esc(dr.headline || "")}</h2>
    <p style="font-size:14.5px;line-height:1.65;color:var(--ink2)">${esc(dr.summary || "")}</p>
  </div>
  <div class="two-col">
    <div class="card"><h2>Sectors to watch</h2><div class="sub"></div>
      <table><tbody>${(dr.sectors || []).map(s => `<tr><td><b>${esc(s.name)}</b></td><td>${stanceTag(s.stance)}</td><td class="sub" style="color:var(--ink2)">${esc(s.why)}</td></tr>`).join("") || '<tr><td class="empty">—</td></tr>'}</tbody></table></div>
    <div class="card"><h2>Key risks</h2><div class="sub">what would spoil the read</div>
      <ul style="margin:6px 0 0 16px;line-height:1.7">${(dr.risks || []).map(r => `<li>${esc(r)}</li>`).join("") || "<li class='sub'>none flagged</li>"}</ul>
      ${(dr.catalysts || []).length ? `<div class="sub" style="margin-top:12px"><b>Catalysts:</b> ${dr.catalysts.map(c => `${esc(c.date)} ${esc(c.event)}`).join(" · ")}</div>` : ""}</div>
  </div>
  <div class="seg"><h2>Names on the desk's radar</h2><div class="ln"></div></div>
  <div class="cards">${(dr.watchlist || []).map(w => `<div class="card clickable" onclick="location.hash='#/ticker/${esc(w.ticker)}'">
    <div class="tk-head" style="margin-bottom:8px"><span class="sym" style="font-size:20px">${esc(w.ticker)}</span></div>
    <p style="color:var(--ink2);line-height:1.6;margin-bottom:6px">${esc(w.angle)}</p>
    <div class="sub"><b class="dn">Risk:</b> ${esc(w.risk)}</div></div>`).join("") || '<div class="card"><div class="empty">Patient today — nothing stacks up strongly enough to flag.</div></div>'}</div>
  <p class="sub" style="margin-top:14px">${esc(dr.disclaimer || "Research, not advice.")}</p>`;
}

async function pageStrategies() {
  const [bt, smap] = await Promise.all([j("backtests.json"), j("strategy_map.json")]);
  const tpls = bt?.templates || {};
  let rows;
  if (Object.keys(tpls).length) {
    // full roll-up from backtests: proven count + tested count + stocks
    rows = Object.entries(tpls).map(([id, per]) => {
      const all = Object.values(per);
      const elig = all.filter(t => t.eligible);
      const avgNet = elig.length ? elig.reduce((a, t) => a + t.net_expectancy_pct, 0) / elig.length : null;
      return { id, name: all[0]?.name || id, cat: all[0]?.category || "", tested: all.length,
        proven: elig.length, avgNet, provenOn: Object.entries(per).filter(([, t]) => t.eligible).map(([s]) => s) };
    });
  } else {
    // bundled/snapshot fallback: derive from strategy_map (per-ticker proven lists)
    const agg = {};
    Object.entries(smap?.tickers || {}).forEach(([sym, list]) => list.forEach(p => {
      const a = agg[p.id] || (agg[p.id] = { id: p.id, name: p.name, cat: p.category, nets: [], provenOn: [] });
      a.nets.push(p.net_expectancy_pct); a.provenOn.push(sym);
    }));
    rows = Object.values(agg).map(a => ({ id: a.id, name: a.name, cat: a.cat, tested: null,
      proven: a.provenOn.length, avgNet: a.nets.reduce((x, y) => x + y, 0) / a.nets.length, provenOn: a.provenOn }));
  }
  rows.sort((a, b) => b.proven - a.proven);
  const byCat = {};
  rows.forEach(r => (byCat[r.cat] = byCat[r.cat] || []).push(r));

  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Strategy library</h2><div class="ln"></div><span class="pill">${rows.length} strategies</span></div>
  <p class="sub" style="margin-bottom:16px">Every strategy is a transparent rule set backtested on each stock's own ~19-year history. A strategy is only used on a stock where it cleared the bar (win rate ≥55%, positive expectancy after costs, and still profitable out-of-sample). Click any stock chip to see it in context.</p>
  ${Object.entries(byCat).map(([cat, list]) => `<div class="card"><h2 style="font-size:13px;text-transform:capitalize">${esc(cat.replace("_", " "))}</h2>
    <table><thead><tr><th>Strategy</th><th class="r">Proven on</th><th class="r">Avg net/trade</th><th>Stocks it works on</th></tr></thead><tbody>${
    list.map(r => `<tr><td><b>${esc(r.name)}</b></td><td class="r num">${r.proven}${r.tested ? "/" + r.tested : ""}</td>
      <td class="r num ${r.avgNet > 0 ? "up" : ""}">${r.avgNet != null ? sgn(r.avgNet.toFixed(2)) + "%" : "—"}</td>
      <td>${r.provenOn.slice(0, 10).map(s => `<a class="tag clickable" onclick="event.stopPropagation();location.hash='#/ticker/${s}'">${s}</a>`).join(" ") || '<span class="sub">none yet</span>'}</td></tr>`).join("")}</tbody></table></div>`).join("")}`;
}

function behaviorStats(hist) {
  const c = hist.map(h => h.close);
  const rets = c.slice(1).map((v, i) => v / c[i] - 1);
  let peak = c[0], mdd = 0;
  c.forEach(v => { peak = Math.max(peak, v); mdd = Math.min(mdd, v / peak - 1); });
  const upDays = rets.filter(r => r > 0).length;
  return {
    total: (c[c.length - 1] / c[0] - 1) * 100,
    mdd: mdd * 100,
    upPct: upDays / rets.length * 100,
    avgAbs: rets.reduce((a, r) => a + Math.abs(r), 0) / rets.length * 100,
    best: Math.max(...rets) * 100,
    worst: Math.min(...rets) * 100,
  };
}

async function pageTicker(sym) {
  sym = sym.toUpperCase();
  const [quant, bt, smap, uni, live, news, divs, fund, fscore, cal, hist, deep, intra] = await Promise.all([
    j("quant.json"), j("backtests.json"), j("strategy_map.json"), j("universe.json"),
    j("live.json"), j("newslog.json"), j("dividends.json"), j("fundamentals.json"),
    j("fundamental_scores.json"), j("earnings_calendar.json"), j("history/" + sym + ".json", 300000),
    j("history_deep/" + sym + ".json", 600000), j("intraday/" + sym + ".json", 20000)]);
  const q = quant?.tickers?.[sym], u = uni?.symbols?.[sym], lv = live?.tickers?.[sym];
  const proven = (smap?.tickers?.[sym]) || [];
  const fsc = fscore?.tickers?.[sym];
  // deep history (Yahoo, ~18y) preferred for chart + behavior; DPS as fallback
  const series = (deep && deep.length > (hist?.length || 0)) ? deep : hist;
  const yearsSpan = series ? ((new Date(series[series.length - 1].date) - new Date(series[0].date)) / 3.156e10) : 0;
  const f = fund?.tickers?.[sym] || {};
  const nextEarn = (cal?.events || []).find(e => e.ticker === sym && e.type === "results");
  const daysTo = d => d ? Math.ceil((new Date(d) - new Date()) / 86400000) : null;
  if (!series || !q) { $("view").innerHTML = `<div class="card"><div class="empty">No data for ${esc(sym)}.</div></div>`; return; }

  const px = lv?.current ?? q.close;
  const b = behaviorStats(series);
  const histYears = Math.max(1, Math.round(yearsSpan));
  const tickerNews = (news || []).filter(n => (n.tickers || []).includes(sym)).slice(-10).reverse();
  const dHist = (divs?.history || []).filter(d => d.symbol === sym);
  const dUp = (divs?.upcoming || []).filter(d => d.symbol === sym);
  const allTested = Object.entries(bt?.templates || {}).map(([id, per]) => ({ id, ...(per[sym] || {}) })).filter(t => t.n).sort((a, b) => (b.net_expectancy_pct ?? -99) - (a.net_expectancy_pct ?? -99));
  const provenIds = new Set(proven.map(p => p.id));
  const hasIntra = intra && intra.date === (live?.updated || "").slice(0, 10) && intra.points?.length > 3;

  $("view").innerHTML = `
  <a class="crumb" href="#/board">← board</a>
  <div class="card">
    <div class="tk-head">
      <span class="sym">${sym}</span>
      <span class="px num">${fmt(px)}</span>
      <span class="num ${cls(q.ret_1d)}" style="font-size:16px;font-weight:700">${sgn(q.ret_1d)}%</span>
      <span class="tag">${esc(u?.name || "")}</span>${lv?.sector && isNaN(lv.sector) ? `<span class="tag">${esc(lv.sector)}</span>` : ""}
      <span class="tag">${(u?.in || []).join(" · ")}</span>
      <a class="tag" target="_blank" href="https://www.tradingview.com/chart/?symbol=PSX%3A${sym}">TradingView ↗ (15m delayed)</a>
    </div>
    <div class="ranges" id="ranges">
      ${hasIntra ? '<button data-d="intra">1D</button>' : ""}<button data-d="63">3M</button><button data-d="126">6M</button><button class="on" data-d="252">1Y</button><button data-d="1260">5Y</button><button data-d="99999">Max${histYears >= 5 ? " (" + histYears + "y)" : ""}</button>
    </div>
    <div class="chartwrap"><canvas id="chart" style="height:340px"></canvas><div class="tooltip" id="tt"></div></div>
  </div>

  <div class="seg"><h2>Strategies proven on ${sym}</h2><div class="ln"></div><span class="pill ok">${proven.length} proven</span></div>
  <div class="card"><div class="sub">Of the desk's ${bt?.n_strategies ?? 52} tested strategies, these cleared the bar on ${sym}'s own ~19-year history — win rate ≥55%, positive expectancy after costs, AND still profitable in the unseen last third (out-of-sample). This is what actually worked here, not theory.</div>
    ${proven.length ? `<table><thead><tr><th>Strategy</th><th>Type</th><th class="r">Win rate</th><th class="r">Avg net/trade</th><th class="r">Trades</th><th class="r">Out-of-sample</th></tr></thead><tbody>${
      proven.map(t => `<tr><td><b>${esc(t.name)}</b></td><td><span class="tag">${esc(t.category.replace("_", " "))}</span></td>
        <td class="r num">${Math.round(t.hit_rate * 100)}%</td><td class="r num up">${sgn(t.net_expectancy_pct)}%</td>
        <td class="r num">${t.n}</td><td class="r num">${t.oos_hit != null ? Math.round(t.oos_hit * 100) + "% · n" + t.oos_n : "—"}</td></tr>`).join("")}</tbody></table>`
      : '<div class="empty">No strategy cleared the bar on this name — the desk would not signal it. That is a finding, not a gap: its history is too choppy for these rules.</div>'}</div>
  ${allTested.length > proven.length ? `<div class="card"><h2 style="font-size:13px">All ${allTested.length} strategies tested here</h2><div class="sub">full transparency — including the ones that failed. <span class="pill ok">proven</span> = made the cut.</div>
    <table><thead><tr><th>Strategy</th><th class="r">Win</th><th class="r">Net</th><th class="r">n</th><th class="r">Verdict</th></tr></thead><tbody>${
    allTested.slice(0, 20).map(t => `<tr><td>${esc(t.name || t.id)}</td><td class="r num">${t.hit_rate != null ? Math.round(t.hit_rate * 100) + "%" : "—"}</td>
      <td class="r num ${(t.net_expectancy_pct || 0) > 0 ? "up" : "dn"}">${sgn(t.net_expectancy_pct ?? 0)}%</td><td class="r num">${t.n}</td>
      <td class="r">${provenIds.has(t.id) ? '<span class="pill ok">proven</span>' : '<span style="opacity:.45">rejected</span>'}</td></tr>`).join("")}</tbody></table></div>` : ""}

  ${fsc ? `<div class="seg"><h2>Is it a good business?</h2><div class="ln"></div><span class="pill ${fsc.rating === "attractive" ? "ok" : fsc.rating === "caution" ? "bad" : ""}">${esc(fsc.rating)}</span></div>
  <div class="card"><div class="sub" style="font-size:13px;color:var(--ink2);margin-bottom:14px">${esc(fsc.overall)}</div>
    <div class="two-col" style="gap:12px">${fsc.cards.map(c => `<div style="border:1px solid var(--line);border-radius:10px;padding:12px 14px">
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px"><b>${esc(c[0])}</b><span class="tag">${esc(c[1])}</span></div>
      <div class="sub" style="color:var(--ink2)">${esc(c[2])}</div></div>`).join("")}</div></div>` : ""}

  <div class="card"><h2>Key facts</h2><div class="sub">fundamentals · stockanalysis.com${f.fetched ? " · " + f.fetched : ""}</div>
    <div class="facts">
      <div class="fact"><span>Market cap</span><b>${esc(f.market_cap || "—")}</b></div>
      <div class="fact"><span>P/E (TTM)</span><b>${esc(f.pe || "—")}</b></div>
      <div class="fact"><span>Forward P/E</span><b>${esc(f.forward_pe || "—")}</b></div>
      <div class="fact"><span>EPS (TTM)</span><b>${esc(f.eps || "—")}</b></div>
      <div class="fact"><span>Div yield</span><b>${esc(f.div_yield || "—")}</b></div>
      <div class="fact"><span>Payout ratio</span><b>${esc(f.payout_ratio || "—")}</b></div>
      <div class="fact"><span>Beta</span><b>${esc(f.beta || "—")}</b></div>
      <div class="fact"><span>Revenue</span><b>${esc(f.revenue || "—")}</b></div>
      <div class="fact"><span>Net income</span><b>${esc(f.net_income || "—")}</b></div>
      <div class="fact"><span>Shares out</span><b>${esc(f.shares_out || "—")}</b></div>
      <div class="fact"><span>Next results</span><b>${nextEarn ? esc(nextEarn.date) + ` <span class="cd ${daysTo(nextEarn.date) <= 7 ? "soon" : ""}">${daysTo(nextEarn.date)}d</span>` : esc(f.next_earnings || "—")}</b></div>
      <div class="fact"><span>Ex-dividend</span><b>${esc(f.ex_div_date || "—")}</b></div>
    </div></div>
  <div class="card"><h2>Quant snapshot</h2><div class="sub">as of ${q.date} close</div>
    <div class="statgrid num">
      <div class="stat"><span>RSI 14</span><b>${q.rsi14}</b></div>
      <div class="stat"><span>SMA 20</span><b class="${q.above_sma20 ? "up" : "dn"}">${q.sma20}</b></div>
      <div class="stat"><span>SMA 50</span><b class="${q.above_sma50 ? "up" : "dn"}">${q.sma50}</b></div>
      <div class="stat"><span>ATR proxy</span><b>${q.atr14_proxy}</b></div>
      <div class="stat"><span>5d / 20d</span><b><span class="${cls(q.ret_5d)}">${sgn(q.ret_5d)}%</span> / <span class="${cls(q.ret_20d)}">${sgn(q.ret_20d)}%</span></b></div>
      <div class="stat"><span>vol surge</span><b>${q.vol_surge ?? "—"}×</b></div>
      <div class="stat"><span>vola rank</span><b>${q.volatility_rank ?? "—"}</b></div>
      <div class="stat"><span>to 20d high</span><b>${sgn(q.dist_to_20d_high_pct)}%</b></div>
      <div class="stat"><span>avg traded/day</span><b>${fmt(q.avg_daily_traded_value / 1e6, 0)}M</b></div>
      <div class="stat"><span>index weight</span><b>${u?.weight_pct ?? "—"}%</b></div>
    </div></div>
  <div class="two-col">
    <div class="card"><h2>${histYears}-year behavior</h2><div class="sub">${series[0].date} → ${series[series.length - 1].date}${series === deep ? " · Yahoo history" : ""}</div>
      <div class="statgrid num">
        <div class="stat"><span>total return</span><b class="${cls(b.total)}">${sgn(b.total.toFixed(0))}%</b></div>
        <div class="stat"><span>max drawdown</span><b class="dn">${b.mdd.toFixed(0)}%</b></div>
        <div class="stat"><span>up days</span><b>${b.upPct.toFixed(0)}%</b></div>
        <div class="stat"><span>avg daily move</span><b>±${b.avgAbs.toFixed(2)}%</b></div>
        <div class="stat"><span>best day</span><b class="up">+${b.best.toFixed(1)}%</b></div>
        <div class="stat"><span>worst day</span><b class="dn">${b.worst.toFixed(1)}%</b></div>
      </div></div>
    <div class="card"><h2>Dividends</h2><div class="sub">face value Rs 10 assumed · buy BEFORE ex-date (~2 sessions pre-closure)</div>${
      dUp.length ? `<p style="margin-bottom:10px"><b class="up">UPCOMING:</b> ${dUp.map(d => `${esc(d.announcement)} — closure ${d.bc_start}, buy by <b>${d.buy_by}</b>`).join("; ")}</p>` : ""}
      <table><thead><tr><th>Announced</th><th>Payout</th><th class="r">Rs/sh</th><th class="r">Yield@now</th><th class="r">Closure</th></tr></thead><tbody>${
      dHist.length ? dHist.slice(0, 8).map(d => `<tr><td>${esc((d.announced || "").split(" ").slice(0, 3).join(" "))}</td><td>${esc(d.announcement)}</td>
        <td class="r num">${d.dividend_rs ?? "—"}</td><td class="r num">${d.yield_pct_at_close ? d.yield_pct_at_close + "%" : "—"}</td><td class="r num">${d.bc_start || "—"}</td></tr>`).join("") : '<tr><td colspan="5" class="empty">no payout records</td></tr>'}</tbody></table></div>
  </div>
  <div class="card"><h2>News & developments</h2><div class="sub">sentinel-tagged for ${sym}</div><div class="wire">${
    tickerNews.length ? tickerNews.map(n => `<p><span class="tag">${n.impact}</span> <span class="t">${esc((n.ts || "").slice(0, 16))}</span>${esc(n.headline || "")} ${n.url ? `<a href="${esc(n.url)}" target="_blank" style="color:var(--accent)">source ↗</a>` : ""}<br><span class="t">${esc(n.summary || "")}</span></p>`).join("") : '<div class="empty">Nothing tagged yet — sentinel populates this each cycle.</div>'}</div></div>`;

  const redraw = d => {
    if (d === "intra") drawIntraday($("chart"), $("tt"), intra.points, q.close);
    else drawChart($("chart"), $("tt"), series, +d);
  };
  $("ranges").addEventListener("click", e => {
    if (!e.target.dataset.d) return;
    $("ranges").querySelectorAll("button").forEach(x => x.classList.toggle("on", x === e.target));
    redraw(e.target.dataset.d);
  });
  redraw(252);
}

function daysFromNow(d) { return d ? Math.ceil((new Date(d) - new Date()) / 86400000) : null; }
function cdBadge(d) { const n = daysFromNow(d); return n == null ? "" : `<span class="cd ${n <= 3 ? "soon" : ""}">${n >= 0 ? n + "d" : "past"}</span>`; }

async function pageDividends() {
  const [cal, divs] = await Promise.all([j("earnings_calendar.json"), j("dividends.json")]);
  const ev = cal?.events || [];
  const divUp = ev.filter(e => e.type === "ex_dividend" || e.type === "book_closure");
  const past = (divs?.history || []).filter(d => d.bc_start && !d.upcoming)
    .sort((a, b) => b.bc_start.localeCompare(a.bc_start)).slice(0, 40);

  const divHtml = divUp.length ? divUp.map(d => `
    <tr class="clickable" onclick="location.hash='#/ticker/${d.ticker}'">
      <td><b>${d.ticker}</b></td>
      <td>${esc(d.announcement || d.type.replace("_", " "))}</td>
      <td class="r num">${d.dividend_rs ?? "—"}</td>
      <td class="r num">${d.yield_pct || (d.div_yield ? esc(d.div_yield) : "—")}</td>
      <td class="r num up"><b>${d.buy_by || "—"}</b> ${cdBadge(d.buy_by)}</td>
      <td class="r num">${d.sell_ok_from || d.date}</td>
    </tr>`).join("")
    : `<tr><td colspan="6" class="empty">No upcoming ex-dividend / book-closure dates in the universe right now. PSX dividends cluster right after results (Jul–Aug) — the fundamentals agent fills these the moment a company announces.</td></tr>`;

  $("view").innerHTML = `
  <div class="timing">
    <div><span>How to collect a dividend</span><b>Buy before → hold through → sell after</b></div>
    <div><span>① Buy by</span><b>the last session before the ex-date</b></div>
    <div><span>② Sell on / after</span><b>the ex-date — you keep the full payout</b></div>
  </div>

  <div class="seg"><h2>Upcoming dividends & book closures</h2><div class="ln"></div></div>
  <div class="card"><div class="sub">own the share BEFORE the ex-dividend date to receive the cash · updated ${esc(cal?.updated || "—")}</div>
    <table><thead><tr><th>Ticker</th><th>Payout</th><th class="r">Rs/sh</th><th class="r">Yield</th><th class="r">Buy by</th><th class="r">Ex / sell-after</th></tr></thead><tbody>${divHtml}</tbody></table></div>

  <div class="seg"><h2>Past payouts</h2><div class="ln"></div></div>
  <div class="card"><div class="sub">last ${past.length} closures · cash dividends (D) as % of Rs 10 face value</div>
    <table><thead><tr><th>Ticker</th><th>Payout</th><th class="r">Rs/sh</th><th class="r">Yield@now</th><th class="r">Announced</th><th class="r">Closure start</th></tr></thead><tbody>${
    past.map(d => `<tr class="clickable" onclick="location.hash='#/ticker/${d.symbol}'"><td><b>${d.symbol}</b></td><td>${esc(d.announcement)}</td>
      <td class="r num">${d.dividend_rs ?? "—"}</td><td class="r num">${d.yield_pct_at_close ? d.yield_pct_at_close + "%" : "—"}</td>
      <td class="r num">${esc((d.announced || "").split(" ").slice(0, 3).join(" "))}</td><td class="r num">${d.bc_start}</td></tr>`).join("")}</tbody></table></div>`;
}

async function pageCalendar() {
  const cal = await j("earnings_calendar.json");
  const earnings = (cal?.events || []).filter(e => e.type === "results");
  const byMonth = {};
  earnings.forEach(e => { const m = e.date.slice(0, 7); (byMonth[m] = byMonth[m] || []).push(e); });

  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Earnings calendar</h2><div class="ln"></div></div>
  <p class="sub" style="margin-bottom:16px">${earnings.length} upcoming results dates across the universe · <span class="pill ok">verified</span> = confirmed against a company/PSX board-meeting notice · <span class="tag">estimate</span> = scraped, pending verification. The desk won't open a swing into an unconfirmed results date inside its hold window (earnings gaps blow through stops).</p>
  ${Object.keys(byMonth).sort().map(m => {
    const label = new Date(m + "-01").toLocaleDateString("en", { month: "long", year: "numeric" });
    return `<div class="card"><h2 style="font-size:13px">${label}</h2>
      <table><thead><tr><th>Date</th><th class="r">In</th><th>Ticker</th><th>Event</th><th class="r">Status</th></tr></thead><tbody>${
      byMonth[m].map(e => `<tr class="clickable" onclick="location.hash='#/ticker/${e.ticker}'">
        <td class="num">${e.date}</td><td class="r">${cdBadge(e.date)}</td><td><b>${e.ticker}</b></td>
        <td class="sub">${esc(e.note || "results")}</td>
        <td class="r">${e.confirmed ? '<span class="pill ok">verified</span>' : '<span class="tag">estimate</span>'}</td></tr>`).join("")}</tbody></table></div>`;
  }).join("") || '<div class="card"><div class="empty">Calendar builds on the first full cycle.</div></div>'}`;
}

let newsFilter = { imp: 0, q: "" };
async function pageNews() {
  const news = (await j("newslog.json")) || [];
  const rows = news.filter(n => (n.impact || 0) >= newsFilter.imp
    && (!newsFilter.q || (n.tickers || []).join(" ").toUpperCase().includes(newsFilter.q) || (n.headline || "").toUpperCase().includes(newsFilter.q)))
    .slice(-80).reverse();
  $("view").innerHTML = `
  <div class="card"><h2>News wire</h2><div class="sub">${news.length} items logged · nothing is ever deleted — this is the desk's memory</div>
    <div class="ranges">
      ${[0, 3, 4, 5].map(i => `<button data-imp="${i}" class="${newsFilter.imp === i ? "on" : ""}">${i ? "impact ≥" + i : "all"}</button>`).join("")}
      <input id="nq" placeholder="filter ticker/text" value="${esc(newsFilter.q)}" style="font:inherit;padding:4px 10px;border:1px solid currentColor;opacity:.7;background:transparent;color:inherit;border-radius:6px">
    </div>
    <div class="wire">${rows.length ? rows.map(n => `<p><span class="tag">${n.impact}</span> <span class="t">${esc((n.ts || "").slice(0, 16))}</span>
      ${(n.tickers || []).map(t => `<a href="#/ticker/${esc(t)}" style="color:var(--accent);font-weight:700">${esc(t)}</a>`).join(" ")}
      <b>${esc(n.headline || "")}</b> ${n.url ? `<a href="${esc(n.url)}" target="_blank" style="color:var(--accent)">↗</a>` : ""}<br>
      <span class="t">${esc(n.summary || "")} · ${esc(n.source || "")}</span></p>`).join("") : '<div class="empty">Wire silent — sentinel runs every cycle during market hours.</div>'}</div></div>`;
  $("view").querySelector(".ranges").addEventListener("click", e => {
    if (e.target.dataset.imp != null) { newsFilter.imp = +e.target.dataset.imp; pageNews(); }
  });
  $("nq").addEventListener("change", e => { newsFilter.q = e.target.value.toUpperCase(); pageNews(); });
}

/* ---------- router ---------- */
const PAGES = { today: pageToday, board: pageBoard, strategies: pageStrategies, macro: pageMacro, dividends: pageDividends, calendar: pageCalendar, news: pageNews };
let lastPage = null;

function animateIn() {
  const v = $("view");
  v.classList.remove("enter"); void v.offsetWidth; v.classList.add("enter");
}

async function route(isPoll) {
  const h = location.hash || "#/today";
  const [, page, arg] = h.split("/");
  document.querySelectorAll("[data-nav]").forEach(a => a.classList.toggle("on", a.dataset.nav === (page || "today")));
  renderHeader();
  const key = page + (arg || "");
  if (page === "ticker" && arg) { await pageTicker(arg); }
  else { await (PAGES[page] || pageBoard)(); }
  // animate only on a real navigation (not the 30s silent refresh of the same page)
  if (!isPoll && key !== lastPage) { animateIn(); if (window.scrollTo) window.scrollTo(0, 0); }
  lastPage = key;
}
window.addEventListener("hashchange", () => route(false));
route(false);
setInterval(() => { Object.keys(cache).forEach(k => delete cache[k]); route(true); }, 30000);
