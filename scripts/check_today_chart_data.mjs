/* Pure Today chart data/interaction checks; no browser, network, or provider calls. */
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync("dashboard/today-charts.js", "utf8");
assert.match(source, /JetBrains Mono/, "chart font stack names JetBrains Mono");
assert.doesNotMatch(source, /ctx\.font\s*=\s*[^;]*sans-serif/, "canvas assignments do not fall back to generic sans-serif");
assert.match(source, /document\.fonts\?\.ready/, "charts redraw after the webfont becomes ready");
const documentHandlers = {};
const context = { window: { devicePixelRatio: 1 }, document: { addEventListener(name, fn) { documentHandlers[name] = fn; }, getElementById() { return null; }, createElement() { return { id: "", textContent: "" }; }, head: { appendChild() {} }, body: {}, fonts: { ready: Promise.resolve() } }, getComputedStyle() { return { color: "#1f211d", getPropertyValue() { return ""; } }; }, console, Math, JSON, String, Number, Object, Array, Set, setTimeout, clearTimeout };
vm.runInNewContext(source, context);
const charts = context.window.HennethTodayCharts;
assert(charts, "Today chart API is exposed");

const datedRows = charts.prepareWatchlistRows(["OLD", "LIVE"], {
  quant: { tickers: { OLD: { close: 50.4, date: "2025-01-20", ret_1d: 3.79 }, LIVE: { close: 99, date: "2026-09-10", ret_1d: -1 } } },
  live: { source_at: "2026-09-11T16:50:00+05:00", tickers: { LIVE: { current: 110, ldcp: 100 } } },
});
assert.equal(datedRows[0].priceAsOf, "2025-01-20");
assert.equal(datedRows[0].returnAsOf, "2025-01-20");
assert.equal(datedRows[1].price, 110);
assert.ok(Math.abs(datedRows[1].dayPct - 10) < 1e-8);
const oldPriceHtml = charts.watchlistMicroHtml([datedRows[0]], { source: "2026-09-11T16:50:00+05:00" });
assert.match(oldPriceHtml, /Last available close.*2025-01-20/);
assert.doesNotMatch(oldPriceHtml, /2026-09-11/);

const sourceRow = { ticker: "MLCF", netExpectancyPct: 0.8, winRate: 0.6, tradeCount: 10, oos_hit: 0.8 };
const first = charts.prepareDeskRadar([sourceRow]);
const second = charts.prepareDeskRadar(first);
assert.equal(first[0].expectancy, 0.8, "expectancy remains percentage points");
assert.equal(first[0].oosHit, 80, "ratio OOS hit normalizes to percent once");
assert.equal(second[0].oosHit, 80, "re-preparing a row preserves normalized OOS hit");
assert.equal(second[0].oosLabel, "80% hit", "re-preparing preserves the exact OOS label");
const tiny = charts.prepareDeskRadar([{ ticker: "TINY", netExpectancyPct: 0.8, winRate: 0.5, tradeCount: 4, oos_hit: 0.005 }]);
const tinyAgain = charts.prepareDeskRadar(tiny);
assert.equal(tiny[0].oosHit, 0.5, "tiny ratio normalizes to 0.5 percent");
assert.equal(tinyAgain[0].oosHit, 0.5, "tiny normalized OOS remains idempotent");
const explicit = charts.prepareDeskRadar([{ ticker: "PCT", netExpectancyPct: 0.8, winRatePct: 0.5, tradeCount: 4, oosHitPct: 0.5 }]);
assert.equal(explicit[0].winRate, 0.5, "explicit win-rate percent is not treated as a ratio");
assert.equal(explicit[0].oosHit, 0.5, "explicit OOS percent is not treated as a ratio");
const missing = charts.prepareDeskRadar([{ ticker: "XYZ", netExpectancyPct: 1.2, winRate: 0.5, tradeCount: 4 }]);
assert.equal(missing[0].oosHit, null, "missing OOS stays unknown, not zero");
assert.equal(missing[0].oosLabel, "", "missing OOS has no fabricated label");

const catalysts = charts.prepareCatalysts({ date: "2026-09-04", catalysts: [
  { date: "2026-09-04", event: "Today" }, { date: "2026-09-10", event: "Upcoming" }, { event: "Undated" },
] });
assert.deepEqual(catalysts.map(row => row.status), ["today", "upcoming", "unknown"]);
assert.match(charts.catalystTimelineHtml(catalysts), /2026-09-04/);
const sectorRows = [{ name: "Banks", up: 3, flat: 1, down: 1, count: 5, avgRet: 0.2, members: [{ ticker: "MCB", ret: 0.4 }, { ticker: "ABL", ret: -0.2 }] }];
const sectorHtml = charts.sectorBreadthHtml(sectorRows, { source: "2026-09-04 08:04" });
assert.match(sectorHtml, /Top 1 by net breadth/);
assert.match(sectorHtml, /tabindex="0"/);
assert.match(sectorHtml, /Source 2026-09-04 08:04/);
assert.match(sectorHtml, /MCB/);
assert.match(charts.deskRadarHtml(first, { source: "2026-09-04 18:17" }), /Source 2026-09-04 18:17/);
const breadth = charts.prepareSectorBreadth({
  quant: { tickers: { NULL: { ret_1d: null }, UP: { ret_1d: 0.2 }, FLAT: { ret_1d: 0 } } },
  live: { tickers: {} }, sectors: { tickers: { NULL: { sector: "Banks" }, UP: { sector: "Banks" }, FLAT: { sector: "Banks" } } },
}, { minCount: 1, limit: 8 });
assert.equal(breadth[0].count, 2, "missing daily return is excluded instead of counted as flat");
assert.equal(Array.from(breadth[0].members, member => member.ticker).sort().join(","), "FLAT,UP", "sector members exclude missing returns");

function makeCanvas() {
  const handlers = {};
  const ctx = { setTransform() {}, clearRect() {}, strokeRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {},
    fillRect() {}, fillText() {}, setLineDash() {}, save() {}, translate() {}, rotate() {}, restore() {}, measureText(value) { return { width: String(value).length * 7 }; } };
  const tip = { hidden: true, style: {}, parentElement: null };
  const canvas = { clientWidth: 620, clientHeight: 260, width: 620, height: 260, style: {}, _tip: tip,
    getContext() { return ctx; }, getBoundingClientRect() { return { left: 0, top: 0 }; }, getAttribute(name) { return name === "data-rows" ? this._rowsAttr || "[]" : null; },
    addEventListener(name, fn) { handlers[name] = fn; }, parentElement: { querySelector() { return tip; } } };
  tip.parentElement = canvas.parentElement;
  canvas.handlers = handlers;
  return canvas;
}
const canvas = makeCanvas();
charts.drawDeskRadar(canvas, first);
assert(canvas._hnRadarPoints[0].label, "radar point carries a ticker label hit rectangle");
const label = canvas._hnRadarPoints[0].label;
assert(label.w > 0 && label.h > 0, "ticker label hit rectangle has dimensions");

const narrowRadar = makeCanvas();
narrowRadar.clientWidth = 280;
narrowRadar.width = 280;
const crowdedRows = [
  { ticker: "SHORT", netExpectancyPct: -0.8, winRate: 0.55, tradeCount: 10, oos_hit: 0.5 },
  { ticker: "VERY-LONG-TICKER", netExpectancyPct: 0.8, winRate: 0.6, tradeCount: 10, oos_hit: 0.5 },
];
charts.drawDeskRadar(narrowRadar, crowdedRows);
const longPoint = narrowRadar._hnRadarPoints.find(point => point.row.ticker === "VERY-LONG-TICKER");
assert(longPoint, "narrow radar retains long ticker point");
assert(longPoint.label.x + longPoint.label.w <= 280 - 18 + 4, "long right-edge ticker label stays within canvas bounds");
assert(longPoint.label.x + longPoint.label.w <= longPoint.x - 1, "flipped long ticker label does not cover its marker");
const interactiveRadar = makeCanvas();
interactiveRadar.clientWidth = 280;
interactiveRadar.width = 280;
interactiveRadar._rowsAttr = JSON.stringify(crowdedRows);
charts.mountDeskRadar({ querySelectorAll(selector) { return selector === "canvas.hn-desk-radar-canvas" ? [interactiveRadar] : []; } });
assert.equal(interactiveRadar._hnFontsReadyBound, true, "radar redraw waits for the initial JetBrains Mono font readiness");
const interactiveLong = interactiveRadar._hnRadarPoints.find(point => point.row.ticker === "VERY-LONG-TICKER");
interactiveRadar.handlers.pointermove({ clientX: interactiveLong.label.x + interactiveLong.label.w / 2, clientY: interactiveLong.label.y + interactiveLong.label.h / 2 });
assert.equal(interactiveRadar._tip.hidden, false, "pointer over flipped label opens radar tooltip");
assert.match(interactiveRadar._tip.innerHTML, /VERY-LONG-TICKER/, "flipped label hit targets its own ticker");

function makeSectorCanvas() {
  const handlers = {};
  const ctx = { setTransform() {}, clearRect() {}, strokeRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {},
    fillRect() {}, fillText() {}, setLineDash() {}, save() {}, translate() {}, rotate() {}, restore() {}, measureText(value) { return { width: String(value).length * 7 }; } };
  let tipHtml = "", tipWrites = 0;
  const tipHandlers = {};
  const link = {};
  const tip = { hidden: true, style: {}, parentElement: null,
    addEventListener(name, fn) { tipHandlers[name] = fn; },
    contains(node) { return node === link; },
    get innerHTML() { return tipHtml; },
    set innerHTML(value) { tipWrites += 1; tipHtml = value; },
  };
  const canvas = { clientWidth: 620, clientHeight: 260, width: 620, height: 260, style: {}, dataset: {},
    getContext() { return ctx; }, getBoundingClientRect() { return { left: 0, top: 0 }; }, getAttribute() { return "[]"; },
    addEventListener(name, fn) { (handlers[name] ||= []).push(fn); }, parentElement: { querySelector() { return tip; } },
    handlers, tip, tipHandlers, link, get tipWrites() { return tipWrites; },
  };
  tip.parentElement = canvas.parentElement;
  return canvas;
}
const sectorCanvas = makeSectorCanvas();
const sectorRoot = { querySelectorAll(selector) { return selector === "canvas.hn-sector-matrix-canvas" ? [sectorCanvas] : []; } };
charts.mountSectorBreadthMatrix(sectorRoot);
const interactiveSectorRows = [{ name: "Banks", up: 2, flat: 1, down: 1, count: 4, avgRet: 0.2, members: [{ ticker: "MCB", ret: 0.4 }, { ticker: "ABL", ret: -0.2 }] }];
sectorCanvas._hnSectorRows = interactiveSectorRows;
charts.drawSectorBreadthMatrix(sectorCanvas, interactiveSectorRows);
sectorCanvas.handlers.pointermove[0]({ clientY: 34 });
assert.equal(sectorCanvas.tip.hidden, false, "sector pointer hover opens the constituent panel");
assert.match(sectorCanvas.tip.innerHTML, /MCB/, "sector panel lists constituent tickers");
const writesAfterFirstHover = sectorCanvas.tipWrites;
sectorCanvas.handlers.pointermove[0]({ clientY: 34 });
assert.equal(sectorCanvas.tipWrites, writesAfterFirstHover, "same-row pointermove does not rebuild focused links");
sectorCanvas.handlers.pointerdown[0]({ clientY: 34, preventDefault() {} });
sectorCanvas.handlers.pointerleave[0]();
await new Promise(resolve => setTimeout(resolve, 150));
assert.equal(sectorCanvas.tip.hidden, false, "tap pins the sector panel while pointer leaves canvas");
documentHandlers.pointerdown({ target: {} });
assert.equal(sectorCanvas.tip.hidden, true, "outside pointer dismisses pinned sector panel");
sectorCanvas.handlers.focus[0]();
sectorCanvas.handlers.blur[0]({ relatedTarget: sectorCanvas.link });
await new Promise(resolve => setTimeout(resolve, 150));
assert.equal(sectorCanvas.tip.hidden, false, "tabbing from canvas into a panel link keeps it open");
sectorCanvas.tipHandlers.focusout({ relatedTarget: null });
await new Promise(resolve => setTimeout(resolve, 150));
assert.equal(sectorCanvas.tip.hidden, true, "leaving panel focus dismisses the sector panel");

console.log("today chart data checks passed (OOS normalization, unknown catalysts, radar labels, sector popover interactions)");
