/* Henneth CI editorial charts.
 *
 * Lieflat template audit (data contract first):
 * - 8-quarter scenarios: F3 Hairline Area is the closest honest foundation;
 *   L1 Launch Fan was rejected because it encodes entity birth dates + size.
 * - Revenue-to-EPS bridge: F9 Rung Waterfall; L2 Dot Cascade was rejected
 *   because it encodes ranked countable units, not a running financial bridge.
 * - Scenario sensitivity: L16 Matrix Heat; L8 Dotty Matrix was rejected because
 *   its isometric planes are decorative grouping, not a readable value matrix.
 * - Event history: L11 Trend Lineage. Assumptions: F5 Tick Rows. Expectations:
 *   F12 Dumbbell Queue. Fast headline values: G18 Draw-in + Counter grammar.
 *
 * The renderers below preserve those SVG geometries while using Henneth's
 * existing colour variables and JetBrains Mono type. No chart invents data:
 * missing or blocked payloads become a visible prerequisite path.
 */
(function (global) {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const QUARTERS = 8;
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const list = value => Array.isArray(value) ? value : [];
  const number = value => {
    if (value == null || (typeof value === "string" && !value.trim())) return null;
    const cleaned = typeof value === "string" ? value.replace(/[^0-9.+-]/g, "") : value;
    if (cleaned === "" || cleaned === "+" || cleaned === "-" || cleaned === ".") return null;
    const parsed = Number(cleaned);
    return Number.isFinite(parsed) ? parsed : null;
  };
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const text = value => String(value ?? "");
  const statusBlocked = value => /blocked|missing|unavailable|unknown|not[_ -]?qualified|not[_ -]?generated|not[_ -]?activated/i.test(text(value));
  const shortStatus = value => text(value || "Unavailable").replaceAll("_", " ").replace(/^blocked\s+/i, "");
  const fmt = (value, digits = 1) => finite(value) ? value.toLocaleString("en", { maximumFractionDigits: digits }) : "—";

  function svg(host, label, viewBox = "0 0 400 220") {
    const node = document.createElementNS(NS, "svg");
    node.setAttribute("viewBox", viewBox);
    node.setAttribute("role", "img");
    node.setAttribute("aria-label", label);
    node.setAttribute("preserveAspectRatio", "xMidYMid meet");
    host.replaceChildren(node);
    return node;
  }

  function el(parent, tag, attrs = {}, value = null) {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([key, item]) => node.setAttribute(key, String(item)));
    if (value != null) node.textContent = String(value);
    parent.appendChild(node);
    return node;
  }

  function title(node, value) {
    const tip = document.createElementNS(NS, "title");
    tip.textContent = value;
    node.appendChild(tip);
  }

  function linePath(values, x, y) {
    return values.map((value, index) => `${index ? "L" : "M"}${x(index).toFixed(2)} ${y(value).toFixed(2)}`).join(" ");
  }

  function blocked(host, payload = {}) {
    const label = payload.label || "This view is waiting for qualified evidence";
    const reason = shortStatus(payload.reason || payload.status || "Required input is not available");
    const requirements = list(payload.requirements).filter(Boolean).slice(0, 5);
    const stages = requirements.length ? requirements : ["Observed evidence", "Financial truth", "Model assumptions", "Deterministic output"];
    const available = clamp(Number(payload.available || 0), 0, stages.length);
    const s = svg(host, `${label}. ${reason}`);
    const x0 = 34, x1 = 366, y = 90;
    el(s, "line", { x1: x0, y1: y, x2: x1, y2: y, class: "ci-svg-grid" });
    stages.forEach((stage, index) => {
      const x = stages.length === 1 ? 200 : x0 + index * (x1 - x0) / (stages.length - 1);
      const ready = index < available;
      el(s, "circle", { cx: x, cy: y, r: ready ? 7 : 5, class: ready ? "ci-svg-ink" : "ci-svg-open" });
      el(s, "line", { x1: x, y1: y + 12, x2: x, y2: y + 24, class: "ci-svg-hair" });
      el(s, "text", { x, y: y + 39, "text-anchor": "middle", class: "ci-svg-tiny" }, text(stage).slice(0, 18));
    });
    el(s, "text", { x: 22, y: 24, class: "ci-svg-kicker" }, "OUTPUT HELD BACK");
    el(s, "text", { x: 22, y: 48, class: "ci-svg-title" }, text(label).slice(0, 46));
    el(s, "text", { x: 22, y: 180, class: "ci-svg-note" }, reason.slice(0, 72));
    el(s, "text", { x: 22, y: 201, class: "ci-svg-source" }, "NO ESTIMATE INFERRED · SOURCE GATE REMAINS AUTHORITATIVE");
  }

  // G18 Draw-in + Counter grammar, implemented as dependency-free SVG.
  function counter(host, payload = {}) {
    const value = number(payload.value);
    if (value == null) return blocked(host, payload);
    const s = svg(host, `${payload.label || "Metric"}: ${payload.display || value}`, "0 0 300 116");
    const history = list(payload.series).map(number).filter(finite);
    if (history.length > 1) {
      const min = Math.min(...history), max = Math.max(...history);
      const span = max - min || Math.abs(max) || 1;
      const x = i => 12 + i * 276 / Math.max(history.length - 1, 1);
      const y = v => 94 - (v - min) / span * 34;
      el(s, "path", { d: linePath(history, x, y), class: "ci-svg-line ci-svg-draw", "pathLength": 1 });
    }
    el(s, "text", { x: 12, y: 32, class: "ci-svg-value" }, payload.display || fmt(value, 2));
    el(s, "text", { x: 12, y: 49, class: "ci-svg-kicker" }, text(payload.unit || payload.label || "METRIC").toUpperCase().slice(0, 36));
    el(s, "text", { x: 288, y: 108, "text-anchor": "end", class: "ci-svg-source" }, "DRAW-IN COUNTER · RETAINED STATE");
  }

  // L11 Trend Lineage: each mark is a retained event.
  function timeline(host, payload = {}) {
    const items = list(payload.items).filter(item => item && item.date);
    if (!items.length) return blocked(host, payload);
    const s = svg(host, payload.label || "Dated event lineage");
    const x0 = 28, x1 = 372, y = 105;
    el(s, "line", { x1: x0, y1: y, x2: x1, y2: y, class: "ci-svg-grid" });
    items.slice(0, 8).forEach((item, index, rows) => {
      const x = rows.length === 1 ? 200 : x0 + index * (x1 - x0) / (rows.length - 1);
      const above = index % 2 === 0;
      const ty = above ? 50 : 158;
      el(s, "line", { x1: x, y1: y, x2: x, y2: above ? 68 : 140, class: "ci-svg-hair" });
      const dot = el(s, "circle", { cx: x, cy: y, r: index === rows.length - 1 ? 5 : 3, class: index === rows.length - 1 ? "ci-svg-hero" : "ci-svg-ink" });
      title(dot, `${item.date} · ${item.label || item.type || "event"}`);
      const anchor = index === 0 ? "start" : index === rows.length - 1 ? "end" : "middle";
      const labelX = index === 0 ? 20 : index === rows.length - 1 ? 380 : x;
      el(s, "text", { x: labelX, y: ty, "text-anchor": anchor, class: "ci-svg-small" }, text(item.label || item.type || "event").slice(0, 15));
      el(s, "text", { x: labelX, y: ty + (above ? 14 : -14), "text-anchor": anchor, class: "ci-svg-tiny" }, text(item.date).slice(0, 10));
    });
    el(s, "text", { x: 22, y: 206, class: "ci-svg-source" }, "TREND LINEAGE · ONE MARK = ONE RETAINED DATED EVENT");
  }

  // L12 Type Colonnade translated to event -> drivers -> statements.
  function mechanism(host, payload = {}) {
    const drivers = list(payload.drivers).filter(Boolean).slice(0, 6);
    if (!drivers.length) return blocked(host, payload);
    const s = svg(host, payload.label || "Event transmission mechanism");
    const left = 34, mid = 200, right = 366;
    const y0 = 42, gap = 25;
    el(s, "text", { x: left, y: 20, class: "ci-svg-kicker" }, "EVENT");
    el(s, "text", { x: mid, y: 20, "text-anchor": "middle", class: "ci-svg-kicker" }, "OPERATING DRIVER");
    el(s, "text", { x: right, y: 20, "text-anchor": "end", class: "ci-svg-kicker" }, "FINANCIAL LINE");
    drivers.forEach((driver, index) => {
      const y = y0 + index * gap;
      const target = text(payload.targets?.[index] || payload.target || "Financial output");
      el(s, "path", { d: `M${left + 22} ${y} C115 ${y},145 ${y},${mid - 12} ${y}`, class: "ci-svg-hair" });
      el(s, "path", { d: `M${mid + 12} ${y} C255 ${y},300 ${y},${right - 34} ${y}`, class: "ci-svg-hair" });
      el(s, "circle", { cx: left + 18, cy: y, r: 2.5, class: "ci-svg-ink" });
      el(s, "circle", { cx: mid, cy: y, r: 4, class: index === 0 ? "ci-svg-hero" : "ci-svg-open" });
      el(s, "circle", { cx: right - 30, cy: y, r: 2.5, class: "ci-svg-ink" });
      el(s, "text", { x: mid, y: y - 8, "text-anchor": "middle", class: "ci-svg-small" }, text(driver).replaceAll("_", " ").slice(0, 20));
      el(s, "text", { x: right, y: y + 3, "text-anchor": "end", class: "ci-svg-tiny" }, target.replaceAll("_", " ").slice(0, 18));
    });
    el(s, "text", { x: 22, y: 206, class: "ci-svg-source" }, "TYPE COLONNADE · LINES SHOW STATED LINKAGE, NOT CAUSAL PROOF");
  }

  // F3 Hairline Area extended with honest scenario bounds.
  function fan(host, payload = {}) {
    const bear = list(payload.bear).map(number), base = list(payload.base).map(number), bull = list(payload.bull).map(number);
    if (![bear, base, bull].every(series => series.length === QUARTERS && series.every(finite))) return blocked(host, payload);
    const s = svg(host, payload.label || "Eight-quarter forecast trajectory");
    const all = [...bear, ...base, ...bull], min = Math.min(...all), max = Math.max(...all), span = max - min || 1;
    const x = i => 30 + i * 338 / 7, y = v => 178 - (v - min) / span * 128;
    [0, .25, .5, .75, 1].forEach(t => el(s, "line", { x1: 30, y1: 178 - t * 128, x2: 368, y2: 178 - t * 128, class: "ci-svg-hair" }));
    const area = bull.map((v, i) => `${i ? "L" : "M"}${x(i)} ${y(v)}`).join(" ") + " " + bear.map((v, i) => `L${x(7 - i)} ${y(bear[7 - i])}`).join(" ") + " Z";
    el(s, "path", { d: area, class: "ci-svg-band" });
    el(s, "path", { d: linePath(bear, x, y), class: "ci-svg-bound" });
    el(s, "path", { d: linePath(bull, x, y), class: "ci-svg-bound" });
    el(s, "path", { d: linePath(base, x, y), class: "ci-svg-line ci-svg-draw", "pathLength": 1 });
    base.forEach((value, i) => {
      el(s, "line", { x1: x(i), y1: 178, x2: x(i), y2: y(value), class: "ci-svg-hair" });
      const dot = el(s, "circle", { cx: x(i), cy: y(value), r: 3, class: "ci-svg-ink" });
      title(dot, `Q${i + 1} · base ${fmt(value, 2)} ${payload.unit || ""}`);
      el(s, "text", { x: x(i), y: 195, "text-anchor": "middle", class: "ci-svg-tiny" }, `Q${i + 1}`);
    });
    el(s, "text", { x: 22, y: 214, class: "ci-svg-source" }, `HAIRLINE FORECAST BAND · ${text(payload.unit || "HONEST UNITS").toUpperCase()}`);
  }

  // F9 Rung Waterfall. Length and direction remain proportional to value.
  function waterfall(host, payload = {}) {
    const items = list(payload.items).map(item => ({ label: item?.label, value: number(item?.value), total: !!item?.total })).filter(item => item.label && finite(item.value)).slice(0, 6);
    if (items.length < 2) return blocked(host, payload);
    const running = []; let level = 0;
    items.forEach((item, index) => {
      const start = item.total ? 0 : level;
      const end = item.total ? item.value : level + item.value;
      running.push({ ...item, start, end });
      level = end;
      if (index === items.length - 1 && item.total) level = item.value;
    });
    const values = running.flatMap(item => [item.start, item.end, 0]), min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
    const s = svg(host, payload.label || "Event-to-earnings bridge");
    const x = i => 38 + i * 326 / Math.max(running.length - 1, 1), y = v => 178 - (v - min) / span * 126;
    running.forEach((item, index) => {
      const yy0 = y(item.start), yy1 = y(item.end), top = Math.min(yy0, yy1), bottom = Math.max(yy0, yy1);
      const steps = Math.max(1, Math.min(22, Math.round(Math.abs(item.value) / (span / 18 || 1))));
      for (let rung = 0; rung < steps; rung++) {
        const yy = top + (rung + .5) * (bottom - top) / steps;
        el(s, "line", { x1: x(index) - 13, y1: yy, x2: x(index) + 13, y2: yy, class: item.value < 0 ? "ci-svg-rung-negative" : "ci-svg-rung" });
      }
      if (index < running.length - 1) el(s, "line", { x1: x(index) + 16, y1: yy1, x2: x(index + 1) - 16, y2: yy1, class: "ci-svg-hair ci-svg-dashed" });
      el(s, "text", { x: x(index), y: top - 8, "text-anchor": "middle", class: "ci-svg-small" }, `${item.value > 0 && !item.total ? "+" : ""}${fmt(item.value, 1)}`);
      el(s, "text", { x: x(index), y: 197, "text-anchor": "middle", class: "ci-svg-tiny" }, text(item.label).slice(0, 11));
    });
    el(s, "text", { x: 22, y: 214, class: "ci-svg-source" }, `RUNG WATERFALL · ${text(payload.unit || "REPORTED MODEL UNIT").toUpperCase()}`);
  }

  // L16 Matrix Heat: cell lightness encodes the supplied numeric result.
  function matrix(host, payload = {}) {
    const values = list(payload.values);
    const rows = list(payload.rows), cols = list(payload.cols);
    if (!rows.length || !cols.length || values.length !== rows.length || values.some(row => !Array.isArray(row) || row.length !== cols.length || row.some(value => !finite(number(value))))) return blocked(host, payload);
    const flat = values.flat().map(number);
    if (flat.some(value => !finite(value))) return blocked(host, { ...payload, reason: "Sensitivity matrix contains a missing value" });
    const min = Math.min(...flat), max = Math.max(...flat), span = max - min || 1;
    const s = svg(host, payload.label || "Scenario sensitivity matrix");
    const x0 = 95, y0 = 38, width = 270, height = 135, cw = width / cols.length, ch = height / rows.length;
    cols.forEach((label, index) => el(s, "text", { x: x0 + (index + .5) * cw, y: 24, "text-anchor": "middle", class: "ci-svg-tiny" }, text(label).slice(0, 10)));
    rows.forEach((label, ri) => {
      el(s, "text", { x: x0 - 10, y: y0 + (ri + .5) * ch + 3, "text-anchor": "end", class: "ci-svg-tiny" }, text(label).slice(0, 12));
      values[ri].forEach((raw, ci) => {
        const value = number(raw), shade = Math.round(12 + (value - min) / span * 78);
        const cell = el(s, "rect", { x: x0 + ci * cw + 1, y: y0 + ri * ch + 1, width: cw - 2, height: ch - 2, class: "ci-svg-heat", style: `--ci-heat:${shade}%` });
        title(cell, `${rows[ri]} × ${cols[ci]}: ${fmt(value, 2)} ${payload.unit || ""}`);
        if (rows.length * cols.length <= 36) el(s, "text", { x: x0 + (ci + .5) * cw, y: y0 + (ri + .5) * ch + 3, "text-anchor": "middle", class: shade > 52 ? "ci-svg-cell-light" : "ci-svg-cell-dark" }, fmt(value, 1));
      });
    });
    el(s, "text", { x: 22, y: 208, class: "ci-svg-source" }, `MATRIX HEAT · SHADE = ${text(payload.unit || "MODEL OUTPUT").toUpperCase()}`);
  }

  // F5 Tick Rows: explicit assumptions, one scale per row.
  function assumptions(host, payload = {}) {
    const items = list(payload.items).map(item => ({ label: item?.label, value: number(item?.value), unit: item?.unit })).filter(item => item.label && finite(item.value)).slice(0, 6);
    if (!items.length) return blocked(host, payload);
    const s = svg(host, payload.label || "Key assumptions");
    const comparable = payload.comparable === true;
    const max = comparable ? Math.max(...items.map(item => Math.abs(item.value)), 1) : 1;
    items.forEach((item, index) => {
      const y = 32 + index * 27;
      const filledTicks = comparable ? Math.max(1, Math.round(Math.abs(item.value) / max * 24)) : 24;
      el(s, "text", { x: 20, y: y + 3, class: "ci-svg-tiny" }, text(item.label).slice(0, 18));
      for (let tick = 0; tick < 24; tick++) el(s, "line", { x1: 145 + tick * 7.4, y1: y - 4, x2: 145 + tick * 7.4, y2: y + 4, class: tick < filledTicks ? "ci-svg-rung" : "ci-svg-hair" });
      el(s, "text", { x: 376, y: y + 3, "text-anchor": "end", class: "ci-svg-small" }, `${fmt(item.value, 2)}${item.unit ? ` ${item.unit}` : ""}`);
    });
    el(s, "text", { x: 22, y: 208, class: "ci-svg-source" }, comparable ? "TICK ROWS · LENGTH = COMPARABLE RETAINED COUNT" : "TICK ROWS · VALUES LABELLED; MIXED UNITS NOT COMPARED");
  }

  // F12 Dumbbell Queue: current market requirement versus Henneth base.
  function expectations(host, payload = {}) {
    const market = number(payload.market), base = number(payload.base);
    if (market == null || base == null) return blocked(host, payload);
    const s = svg(host, payload.label || "Market expectations gap");
    const min = Math.min(market, base, 0), max = Math.max(market, base, 0), span = max - min || 1;
    const x = value => 48 + (value - min) / span * 304, y = 100;
    el(s, "line", { x1: 48, y1: y, x2: 352, y2: y, class: "ci-svg-grid" });
    const count = Math.min(40, Math.round(Math.abs(market - base) / span * 40));
    for (let i = 0; i < count; i++) el(s, "circle", { cx: x(base) + (i + .5) / count * (x(market) - x(base)), cy: y, r: 1.7, class: "ci-svg-muted" });
    el(s, "circle", { cx: x(market), cy: y, r: 6, class: "ci-svg-open" });
    el(s, "circle", { cx: x(base), cy: y, r: 6, class: "ci-svg-hero" });
    el(s, "text", { x: x(market), y: 76, "text-anchor": "middle", class: "ci-svg-small" }, `MARKET ${fmt(market, 2)}`);
    el(s, "text", { x: x(base), y: 132, "text-anchor": "middle", class: "ci-svg-small" }, `HENNETH ${fmt(base, 2)}`);
    el(s, "text", { x: 200, y: 166, "text-anchor": "middle", class: "ci-svg-value-small" }, `${market - base > 0 ? "+" : ""}${fmt(market - base, 2)} ${payload.unit || ""}`);
    el(s, "text", { x: 22, y: 208, class: "ci-svg-source" }, "DUMBBELL QUEUE · HOLLOW = MARKET REQUIREMENT · SOLID = BASE CASE");
  }

  const RENDERERS = { blocked, counter, timeline, mechanism, fan, waterfall, matrix, assumptions, expectations };

  function readPayload(host) {
    try { return JSON.parse(decodeURIComponent(host.dataset.ciChartPayload || "%7B%7D")); }
    catch (_) { return { status: "blocked_invalid_chart_payload", reason: "Chart payload could not be read" }; }
  }

  function render(host) {
    const payload = readPayload(host);
    const type = host.dataset.ciChart;
    const requested = RENDERERS[type] || blocked;
    const renderer = requested === blocked || statusBlocked(payload.status) || payload.blocked === true ? blocked : requested;
    host.classList.toggle("is-blocked", renderer === blocked);
    renderer(host, payload);
  }

  function renderAll(root = document) {
    root.querySelectorAll("[data-ci-chart]").forEach(render);
  }

  global.HennethCICharts = Object.freeze({ render, renderAll, RENDERERS: Object.freeze({ ...RENDERERS }) });
})(window);
