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
 * - Past Context: L12 Type Colonnade for the retained state categories, L11
 *   Trend Lineage for dated event windows, and G10 Diverging Bar for signed
 *   raw-price outcomes. L20 was rejected because the state map does not emit
 *   3–6 comparable continuous dimensions; F12 was rejected because it does
 *   not emit a valid then-versus-now numeric pair; F15 was rejected because
 *   thin samples do not provide a five-number distribution.
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
        const cell = el(s, "rect", { x: x0 + ci * cw + 1, y: y0 + ri * ch + 1, width: cw - 2, height: ch - 2, class: "ci-svg-heat", style: `--ci-strength:${shade}%` });
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
      const filledTicks = comparable ? Math.round(Math.abs(item.value) / max * 24) : 24;
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

  // G10 Diverging Bar: a shared zero makes signed historical returns honest.
  function diverging(host, payload = {}) {
    const items = list(payload.items).map(item => ({
      label: item?.label,
      value: number(item?.value),
      unit: item?.unit || "%",
      status: item?.status,
    })).filter(item => item.label && finite(item.value)).slice(0, 6);
    if (!items.length) return blocked(host, payload);
    const s = svg(host, payload.label || "Signed historical outcomes");
    const maxAbs = Math.max(...items.map(item => Math.abs(item.value)), 1);
    const zero = 206, half = 146;
    const rowGap = Math.min(34, 142 / Math.max(items.length, 1));
    const firstY = 42;
    el(s, "line", { x1: zero, y1: 25, x2: zero, y2: 185, class: "ci-svg-grid" });
    el(s, "text", { x: zero, y: 18, "text-anchor": "middle", class: "ci-svg-tiny" }, "0");
    items.forEach((item, index) => {
      const y = firstY + index * rowGap;
      const width = Math.abs(item.value) / maxAbs * half;
      const x = item.value < 0 ? zero - width : zero;
      const bar = el(s, "rect", {
        x, y: y - 8, width: Math.max(width, 1), height: 16,
        rx: 1.5,
        class: item.value < 0 ? "ci-svg-bar-negative" : "ci-svg-bar-positive",
      });
      title(bar, `${item.label}: ${item.value > 0 ? "+" : ""}${fmt(item.value, 1)}${item.unit}`);
      el(s, "text", { x: 18, y: y + 3, class: "ci-svg-small" }, text(item.label).slice(0, 14));
      el(s, "text", {
        x: item.value < 0 ? x - 7 : x + width + 7,
        y: y + 3,
        "text-anchor": item.value < 0 ? "end" : "start",
        class: item.value < 0 ? "ci-svg-value-negative" : "ci-svg-value-positive",
      }, `${item.value > 0 ? "+" : ""}${fmt(item.value, 1)}${item.unit}`);
    });
    el(s, "text", { x: 22, y: 208, class: "ci-svg-source" }, "DIVERGING BAR · SIGNED RAW-PRICE RETURN · HISTORICAL, NOT FORECAST");
  }

  /* Past Context / reusable editorial primitives — exact template audit:
   * state_colonnade: L12 Type Colonnade, templates/lupi-gallery.html,
   *   “Forty-four repos, ten owners”: actual input records converge into named
   *   categories. Preserve the record list, cubic threads and category termini.
   *   L4 Arc Matrix rejected: no category-by-category quantity; L20 Parallel
   *   Coordinates rejected: categorical qualification is not a numeric axis.
   * evidence_convergence: L5 Radial Convergence, same gallery,
   *   “48 requests pull toward five themes”: one perimeter mark per actual
   *   source reference, cubic paths into the observed case. Radius is fixed:
   *   source count is not confidence. L6 Cluster Field rejected: decorative
   *   spokes would invent records; F4 Tick Donut rejected: no part/whole trust.
   * dated_lineage: L11 Trend Lineage, same gallery,
   *   “Features rise, fall, come back”: discrete event marks on dated lanes,
   *   solid observed / hollow target marks, true calendar spacing and cutoff.
   *   F2 Hairline Line rejected: there is no continuous measurement; F12
   *   Dumbbell Queue rejected: dates are not paired numerical factor changes.
   * horizon_outcomes: G10 Diverging Bar, templates/glance-gallery.html,
   *   “Where we gained, where we bled”: shared zero, signed proportional bars,
   *   outside labels, 80ms row stagger. F9 Waterfall rejected: these windows
   *   are independent outcomes, not additive changes; F5 Tick Rows rejected:
   *   negative returns are not countable positive units. Dashboard use allows
   *   Glance. F15 Tick Box rejected: no qualified five-number distributions.
   * permission_tree: G7 Tree LR, templates/glance-gallery.html,
   *   “Everything the platform ships”: orthogonal root-to-leaf capability
   *   relationships, not a progress score. L13 Hourglass rejected: permission
   *   states are not shrinking counts; F11 Gauge rejected: no progress metric.
   *
   * All five share Henneth's established custom palette. Colour describes
   * availability/sign/category, never similarity or confidence. No new data
   * inference; the caller supplies facts, explicit permissions and dates.
   */
  function vizText(parent, x, y, value, className = "ci-viz-label", maxChars = 32, maxLines = 2, anchor = "start") {
    const node = el(parent, "text", { x, y, class: className, "text-anchor": anchor });
    const words = text(value).replaceAll("_", " ").split(/\s+/);
    const lines = [""];
    words.forEach(word => {
      const last = lines.length - 1;
      if (lines[last] && lines[last].length + word.length + 1 > maxChars) lines.push(word);
      else lines[last] += `${lines[last] ? " " : ""}${word}`;
    });
    lines.slice(0, maxLines).forEach((row, i) => el(node, "tspan", { x, dy: i ? "1.35em" : 0 }, i === maxLines - 1 && lines.length > maxLines ? `${row}…` : row));
    return node;
  }

  const vizWidth = host => Math.max(300, Math.min(1000, host.clientWidth || 600));
  const vizTone = status => statusBlocked(status) || /suppressed|prohibited|held/i.test(text(status)) ? "held" : /available|mature|qualified|allowed|observed/i.test(text(status)) ? "ready" : "unknown";
  let vizObserver;
  function vizFrame(host, label, width, height, hint) {
    const s = svg(host, label, `0 0 ${width} ${height}`);
    s.classList.add("ci-viz-svg");
    const inspector = document.createElement("div");
    inspector.className = "ci-viz-inspector";
    inspector.setAttribute("aria-live", "polite");
    inspector.textContent = hint;
    host.appendChild(inspector);
    const inspect = (node, detail, action = null) => {
      node.classList.add("ci-viz-record");
      node.setAttribute("tabindex", "0");
      node.setAttribute("role", action ? "button" : "img");
      node.setAttribute("aria-label", detail);
      title(node, detail);
      ["pointerenter", "focus", "click"].forEach(event => node.addEventListener(event, () => { inspector.textContent = detail; }));
      ["pointerleave", "blur"].forEach(event => node.addEventListener(event, () => { inspector.textContent = hint; }));
      node.addEventListener("keydown", event => {
        const records = [...s.querySelectorAll(".ci-viz-record")], index = records.indexOf(node);
        const target = event.key === "ArrowRight" || event.key === "ArrowDown" ? index + 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? index - 1 : event.key === "Home" ? 0 : event.key === "End" ? records.length - 1 : null;
        if (target != null) { event.preventDefault(); records[(target + records.length) % records.length]?.focus(); }
        if (action && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); node.dispatchEvent(new Event("click")); }
      });
      if (action) node.addEventListener("click", () => host.dispatchEvent(new CustomEvent("ci-chart-select", { bubbles: true, detail: action })));
    };
    if (typeof IntersectionObserver === "function") {
      vizObserver ||= new IntersectionObserver(entries => entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        vizObserver.unobserve(entry.target);
      }), { threshold: .12 });
      vizObserver.observe(s);
    } else s.classList.add("is-visible");
    return { s, inspect };
  }

  // Contract: {groups:[{label,status,items:[{label,value,detail}]}], label?}.
  // Value is display text. Neither thread width nor marker area encodes value.
  function state_colonnade(host, payload = {}) {
    const groups = list(payload.groups).filter(group => group?.label).slice(0, 6);
    if (!groups.length) return blocked(host, payload);
    const w = vizWidth(host), narrow = w < 540;
    const rowH = narrow ? 40 : 33;
    const groupH = group => Math.max(84, Math.max(list(group.items).length, 1) * rowH + 23);
    const h = groups.reduce((sum, group) => sum + groupH(group), 52);
    const { s, inspect } = vizFrame(host, payload.label || "Retained facts grouped by state category", w, h, "Follow a thread to see which retained fact belongs to each state category. Marks show availability, not confidence.");
    const xRecord = 16, xStart = w * .53, xHub = w * .7, xLabel = xHub + 14;
    vizText(s, 16, 19, "RETAINED FACT", "ci-viz-caption");
    vizText(s, xHub, 19, "STATE CATEGORY", "ci-viz-caption");
    let top = 35;
    groups.forEach((group, gi) => {
      const items = list(group.items).length ? group.items : [{ label: "No retained value", value: "Unknown" }];
      const gh = groupH(group), cy = top + (gh - 16) / 2;
      const tone = vizTone(group.status);
      const g = el(s, "g", { class: `ci-viz-group ci-viz-${tone}`, style: `--ci-viz-delay:${gi * 65}ms` });
      el(g, "line", { x1: 16, y1: top + gh - 9, x2: w - 16, y2: top + gh - 9, class: "ci-viz-grid" });
      items.forEach((item, ii) => {
        const yy = top + 14 + ii * rowH;
        const record = el(g, "g");
        el(record, "path", { d: `M${xStart} ${yy} C${w * .6} ${yy},${w * .62} ${cy},${xHub - 7} ${cy}`, class: "ci-viz-thread", pathLength: 1 });
        el(record, "rect", { x: xStart - 6, y: yy - 2, width: 4, height: 4, class: "ci-viz-mark" });
        vizText(record, xRecord, yy - 4, item.label, "ci-viz-label", narrow ? 24 : 44, 1);
        vizText(record, xRecord, yy + 11, item.value ?? "Unknown", "ci-viz-value", narrow ? 24 : 44, 1);
        inspect(record, `${group.label} · ${item.label}: ${item.value ?? "Unknown"}${item.detail ? ` · ${item.detail}` : ""}`, item.action);
      });
      el(g, "circle", { cx: xHub, cy, r: 5, class: "ci-viz-terminal" });
      vizText(g, xLabel, cy - 10, group.label, "ci-viz-label-strong", narrow ? 13 : 24, 2);
      vizText(g, xLabel, cy + 26, shortStatus(group.status), "ci-viz-status", narrow ? 13 : 24, 2);
      top += gh;
    });
  }

  // Contract: {sources:[{label,detail}], case_label, context_label?, context_detail?, trust_label?}.
  // Each source node is one actual reference supplied by the caller, never a proxy score.
  function evidence_convergence(host, payload = {}) {
    const sources = list(payload.sources).filter(item => item?.label);
    const w = vizWidth(host), narrow = w < 500, h = narrow ? 382 : 300;
    const cx = narrow ? w / 2 : w * .32, cy = narrow ? 144 : 142, radius = Math.min(94, w * .25);
    const { s, inspect } = vizFrame(host, payload.label || "Source references converge on the observed case", w, h, "Each perimeter mark is a retained source reference. Source trust and similarity remain separate questions.");
    el(s, "circle", { cx, cy, r: radius, class: "ci-viz-orbit" });
    // Rim ticks are calendar-free furniture, not extra records.
    for (let i = 0; i < 40; i++) {
      const a = i * Math.PI / 20;
      el(s, "line", { x1: cx + Math.cos(a) * (radius + 5), y1: cy + Math.sin(a) * (radius + 5), x2: cx + Math.cos(a) * (radius + 8), y2: cy + Math.sin(a) * (radius + 8), class: "ci-viz-grid" });
    }
    sources.slice(0, 16).forEach((item, i, rows) => {
      const a = rows.length === 1 ? -Math.PI / 2 : -Math.PI / 2 + i / rows.length * Math.PI * 2;
      const x = cx + Math.cos(a) * radius, y = cy + Math.sin(a) * radius;
      const group = el(s, "g", { class: "ci-viz-group ci-viz-ready", style: `--ci-viz-delay:${i * 60}ms` });
      el(group, "path", { d: `M${x} ${y} C${cx + (x - cx) * .42} ${cy + (y - cy) * .42},${cx} ${cy},${cx} ${cy}`, class: "ci-viz-thread", pathLength: 1 });
      el(group, "circle", { cx: x, cy: y, r: 5, class: "ci-viz-terminal" });
      const lx = cx + Math.cos(a) * (radius + 18), ly = cy + Math.sin(a) * (radius + 18);
      vizText(group, lx, ly + 4, String(i + 1).padStart(2, "0"), "ci-viz-caption", 4, 1, "middle");
      inspect(group, `${String(i + 1).padStart(2, "0")} · ${item.label}${item.detail ? ` · ${item.detail}` : ""}`, item.action);
    });
    el(s, "circle", { cx, cy, r: 25, class: "ci-viz-hub" });
    vizText(s, cx, cy + 5, "CASE", "ci-viz-hub-text", 12, 1, "middle");
    vizText(s, cx, cy + radius + 38, `${sources.length} source reference${sources.length === 1 ? "" : "s"}`, "ci-viz-label-strong", 32, 1, "middle");
    if (sources.length > 16) vizText(s, cx, cy + radius + 55, "First 16 shown; all retained below", "ci-viz-caption", 38, 1, "middle");
    const left = narrow ? 16 : w * .66, top = narrow ? 292 : 45;
    el(s, "line", { x1: narrow ? 16 : left - 18, y1: narrow ? top - 18 : 25, x2: narrow ? w - 16 : left - 18, y2: narrow ? top - 18 : h - 25, class: "ci-viz-grid" });
    vizText(s, left, top, "EVIDENCE TRUST", "ci-viz-caption");
    vizText(s, left, top + 22, payload.trust_label || "Source quality unknown", "ci-viz-label-strong", narrow ? 40 : Math.floor(w * .3 / 7), 2);
    vizText(s, left, top + (narrow ? 52 : 85), "SIMILARITY CONTEXT", "ci-viz-caption");
    vizText(s, left, top + (narrow ? 74 : 109), payload.context_label || "No similarity score emitted", "ci-viz-label-strong", narrow ? 40 : Math.floor(w * .3 / 7), 3);
    if (!narrow) vizText(s, left, top + 165, payload.context_detail || "No ranked analogue identity emitted", "ci-viz-label", Math.floor(w * .3 / 7), 3);
    inspect(s.querySelector(".ci-viz-hub"), `${payload.case_label || "Observed case"} · ${sources.length} retained source references. ${payload.context_detail || "Similarity is not a measure of evidence trust."}`);
  }

  // Contract: {items:[{date,label,kind:'event'|'source'|'outcome',observed:boolean,detail?}], cutoff?}.
  // True date spacing is retained. Adjacent marks may coincide; the keyed
  // record legend and focus inspector keep their identities accessible.
  function dated_lineage(host, payload = {}) {
    const rows = list(payload.items).map(item => ({ ...item, time: Date.parse(item?.date) })).filter(item => Number.isFinite(item.time)).sort((a, b) => a.time - b.time);
    if (!rows.length) return blocked(host, payload);
    const w = vizWidth(host), h = 340, cutoff = Date.parse(payload.cutoff);
    const times = rows.map(row => row.time).concat(Number.isFinite(cutoff) ? [cutoff] : []);
    const lo = Math.min(...times), hi = Math.max(...times), span = hi - lo || 86400000;
    const y = value => 44 + (value - lo) / span * 236;
    const lanes = ["event", "source", "outcome"], names = ["CASE", "SOURCES", "OUTCOMES"];
    const xs = [w * .44, w * .65, w * .86];
    const { s, inspect } = vizFrame(host, payload.label || "Dated case, source and outcome lineage", w, h, "Calendar position shows elapsed time. Solid marks are observed; hollow marks are target dates. Focus a mark to inspect its date.");
    for (let tick = 0; tick <= 4; tick++) {
      const time = lo + tick / 4 * span, yy = y(time);
      el(s, "line", { x1: 96, y1: yy, x2: w - 12, y2: yy, class: "ci-viz-grid" });
      vizText(s, 8, yy + 4, new Date(time).toISOString().slice(0, 10), "ci-viz-caption");
    }
    lanes.forEach((lane, i) => {
      const items = rows.filter(row => (lanes.includes(row.kind) ? row.kind : "event") === lane);
      vizText(s, xs[i], 21, names[i], "ci-viz-caption", 12, 1, "middle");
      if (!items.length) return;
      el(s, "line", { x1: xs[i], y1: y(items[0].time), x2: xs[i], y2: y(items[items.length - 1].time), class: "ci-viz-lineage-line" });
      items.forEach((item, ii) => {
        const yy = y(item.time), observed = item.observed !== false;
        const g = el(s, "g", { class: `ci-viz-group ci-viz-${observed ? "ready" : "unknown"}`, style: `--ci-viz-delay:${ii * 65}ms` });
        el(g, "circle", { cx: xs[i], cy: yy, r: 7, class: observed ? "ci-viz-terminal" : "ci-viz-target" });
        const recordNumber = rows.indexOf(item) + 1;
        // Outlying date labels stay in the record legend instead of colliding.
        vizText(g, xs[i] + 12, yy + 4, recordNumber, "ci-viz-caption", 4, 1);
        inspect(g, `${recordNumber}. ${item.label} · ${text(item.date).slice(0, 10)} · ${observed ? "Observed" : "Target date only"}${item.detail ? ` · ${item.detail}` : ""}`, item.action);
      });
    });
    if (Number.isFinite(cutoff)) {
      const yy = y(cutoff);
      el(s, "line", { x1: 98, y1: yy, x2: w - 12, y2: yy, class: "ci-viz-cutoff" });
      vizText(s, w - 12, 311, `Data cutoff ${text(payload.cutoff).slice(0, 10)}`, "ci-viz-label-strong", 38, 1, "end");
    }
    const legend = document.createElement("div");
    legend.className = "ci-viz-record-legend";
    rows.forEach((row, i) => {
      const entry = document.createElement("span");
      entry.textContent = `${i + 1}. ${row.label} · ${text(row.date).slice(0, 10)}`;
      legend.appendChild(entry);
    });
    host.appendChild(legend);
  }

  // Contract: {items:[{label,value:number|null,status,date?,detail?}], unit?:'%'}.
  // All windows remain visible; missing/immature values never become zero.
  function horizon_outcomes(host, payload = {}) {
    const rows = list(payload.items).filter(item => item?.label).slice(0, 8);
    if (!rows.length) return blocked(host, payload);
    const w = vizWidth(host), narrow = w < 530, rowH = narrow ? 76 : 64, h = 74 + rows.length * rowH;
    const numbers = rows.filter(row => row.status === "mature" && finite(row.value)).map(row => Math.abs(row.value));
    const max = Math.max(...numbers, 1), bound = max <= 5 ? Math.ceil(max) : Math.ceil(max / 5) * 5;
    const x0 = narrow ? 52 : 70, x1 = w - (narrow ? 20 : 28), zero = (x0 + x1) / 2, half = (x1 - x0) / 2;
    const { s, inspect } = vizFrame(host, payload.label || "Historical outcome windows", w, h, "Bars show signed raw-price returns from one observed event. A held window has no bar and contributes no zero to the chart.");
    [-1, -.5, 0, .5, 1].forEach(tick => {
      const xx = zero + half * tick;
      el(s, "line", { x1: xx, y1: 32, x2: xx, y2: h - 30, class: tick === 0 ? "ci-viz-zero" : "ci-viz-grid" });
      vizText(s, xx, 18, `${tick > 0 ? "+" : ""}${fmt(bound * tick)}${payload.unit || "%"}`, "ci-viz-caption", 16, 1, tick === -1 ? "start" : tick === 1 ? "end" : "middle");
    });
    rows.forEach((row, i) => {
      const top = 42 + i * rowH, yy = top + 21;
      const mature = row.status === "mature" && finite(row.value);
      const g = el(s, "g", { class: `ci-viz-group ${mature ? row.value < 0 ? "ci-viz-negative" : "ci-viz-ready" : "ci-viz-unknown"}`, style: `--ci-viz-delay:${i * 80}ms` });
      vizText(g, 10, yy + 4, row.label, "ci-viz-label-strong", 5, 1);
      if (mature) {
        const length = Math.abs(row.value) / bound * half, end = zero + row.value / bound * half;
        if (length > 0) el(g, "rect", { x: Math.min(zero, end), y: yy - 7, width: length, height: 14, rx: 7, class: "ci-viz-outcome-bar", style: `transform-origin:${zero}px ${yy}px` });
        else el(g, "circle", { cx: zero, cy: yy, r: 3, class: "ci-viz-mark" });
        vizText(g, end, top - 1, `${row.value > 0 ? "+" : ""}${fmt(row.value, 2)}${payload.unit || "%"}`, "ci-viz-value", 20, 1, row.value > 0 ? "end" : row.value < 0 ? "start" : "middle");
      } else {
        el(g, "line", { x1: x0, y1: yy, x2: x1, y2: yy, class: "ci-viz-unavailable-line" });
        vizText(g, zero, top - 1, shortStatus(row.status), "ci-viz-status", 26, 1, "middle");
      }
      vizText(g, x1, yy + 23, row.date || "Endpoint not retained", "ci-viz-caption", 36, 1, "end");
      inspect(g, `${row.label} · ${mature ? `${fmt(row.value, 2)}${payload.unit || "%"} raw-price return` : shortStatus(row.status)}${row.date ? ` · ${row.date}` : ""}${row.detail ? ` · ${row.detail}` : ""}`, row.action);
    });
  }

  // Contract: {root_label,items:[{label,allowed:boolean|null,detail?}]}.
  // There is deliberately no percent complete or ordered prerequisite chain.
  function permission_tree(host, payload = {}) {
    const rows = list(payload.items).filter(row => row?.label).slice(0, 6);
    if (!rows.length) return blocked(host, payload);
    const w = vizWidth(host), h = Math.max(190, rows.length * 82 + 32), rootX = 24, leafX = w < 500 ? 85 : w * .3;
    const mid = h / 2;
    const { s, inspect } = vizFrame(host, payload.label || "Research permissions retained in the answer contract", w, h, "Each branch is an explicit permission. A blocked branch cannot be activated by this visualization.");
    el(s, "circle", { cx: rootX, cy: mid, r: 6, class: "ci-viz-hub" });
    rows.forEach((row, i) => {
      const yy = 46 + i * 82, tone = row.allowed === true ? "ready" : row.allowed === false ? "held" : "unknown";
      const g = el(s, "g", { class: `ci-viz-group ci-viz-${tone}`, style: `--ci-viz-delay:${i * 80}ms` });
      el(g, "path", { d: `M${rootX + 6} ${mid} C${leafX * .7} ${mid},${leafX * .7} ${yy},${leafX} ${yy}`, class: "ci-viz-thread", pathLength: 1 });
      el(g, "circle", { cx: leafX, cy: yy, r: 5, class: row.allowed === true ? "ci-viz-terminal" : "ci-viz-target" });
      vizText(g, leafX + 18, yy - 5, row.label, "ci-viz-label-strong", Math.floor((w - leafX - 35) / 7), 2);
      vizText(g, leafX + 18, yy + 31, row.allowed === true ? "Allowed for descriptive research" : row.allowed === false ? "Held back" : "Permission unknown", "ci-viz-status", Math.floor((w - leafX - 35) / 7), 2);
      inspect(g, `${payload.root_label || "Historical context"} → ${row.label}: ${row.allowed === true ? "allowed" : row.allowed === false ? "held back" : "unknown"}${row.detail ? ` · ${row.detail}` : ""}`, row.action);
    });
  }

  const RENDERERS = { blocked, counter, timeline, mechanism, fan, waterfall, matrix, assumptions, expectations, diverging, state_colonnade, evidence_convergence, dated_lineage, horizon_outcomes, permission_tree };
  const EDITORIAL_TYPES = new Set(["state_colonnade", "evidence_convergence", "dated_lineage", "horizon_outcomes", "permission_tree"]);
  const vizWidths = new WeakMap();
  const vizResizeObserver = typeof ResizeObserver === "function" ? new ResizeObserver(entries => {
    entries.forEach(entry => {
      const width = entry.target.clientWidth;
      if (width > 0 && Math.abs(width - (vizWidths.get(entry.target) || 0)) >= 1) render(entry.target);
    });
  }) : null;

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
    if (EDITORIAL_TYPES.has(type)) {
      vizWidths.set(host, host.clientWidth);
      vizResizeObserver?.observe(host);
    }
  }

  function renderAll(root = document) {
    vizObserver?.disconnect();
    vizResizeObserver?.disconnect();
    root.querySelectorAll("[data-ci-chart]").forEach(render);
  }

  global.HennethCICharts = Object.freeze({ render, renderAll, RENDERERS: Object.freeze({ ...RENDERERS }) });
})(window);
