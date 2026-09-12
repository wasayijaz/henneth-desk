/* Offline checks for the Today external-article adapter; no network or browser required. */
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const source = fs.readFileSync("dashboard/today.js", "utf8");
const context = { window: {}, console, Date, URL, String, Number, Object, Array, Set };
vm.runInNewContext(source, context);
const article = context.window.HennethTodayArticle;
assert(article, "Today article adapter is exposed");

const rows = [
  { headline: "Undated should not win", ts: "not-a-date", summary: "bad timestamp" },
  { headline: "Older valid story", ts: "2026-09-03", url: "https://example.test/old" },
  { headline: "Newest valid story", ts: "2026-09-04", source: "Wire", summary: "Provided excerpt only.", url: "https://example.test/new" },
  { summary: "Headline missing" },
];
assert.equal(article.latest(rows).headline, "Newest valid story", "latest valid dated headline wins over malformed timestamp");
const sameDay = [{ headline: "Earlier same-day story", ts: "2026-09-04" }, { headline: "Later appended story", ts: "2026-09-04" }];
const sameDayBefore = JSON.stringify(sameDay);
assert.equal(article.latest(sameDay).headline, "Later appended story", "later append wins when newslog timestamps share a date");
assert.equal(JSON.stringify(sameDay), sameDayBefore, "latest selection does not mutate append-only input order");
assert.equal(article.href("https://example.test/a"), "https://example.test/a");
assert.equal(article.href("HTTP://example.test/a"), "HTTP://example.test/a");
assert.equal(article.href("https://"), "", "absolute-looking URL without a host is rejected");
assert.equal(article.href("javascript:alert(1)"), "", "javascript URL is rejected");
assert.equal(article.href("/blog/story"), "", "relative URL is not treated as an external article link");
assert.equal(article.href("data:text/html,hello"), "", "data URL is rejected");

const html = article.card(rows);
assert.match(html, /Newest valid story/);
assert.match(html, /ARTICLE/);
assert.match(html, /2026-09-04/);
assert.match(html, /Provided excerpt only\./);
assert.match(html, /href="https:\/\/example\.test\/new"/);
assert.match(html, /Read article/);
const escaped = article.card([{ headline: "<script>alert('x')</script>", source: "A&B", ts: "not-a-date", summary: "<b>no HTML</b>", url: "javascript:bad" }]);
assert.match(escaped, /&lt;script&gt;alert\(&#39;x&#39;\)&lt;\/script&gt;/, "headline is escaped");
assert.match(escaped, /A&amp;B/);
assert.match(escaped, /&lt;b&gt;no HTML&lt;\/b&gt;/);
assert.match(escaped, /date unknown/);
assert.doesNotMatch(escaped, /Read article/);
assert.equal(article.latest(null), null, "malformed feed has no article");
assert.equal(article.card([]), "", "empty feed renders no card");
assert.equal(article.card([{ headline: "   " }]), "", "blank headline renders no card");

console.log("today article checks passed (selection, malformed dates, safe links, escaping, empty feed)");

// A Saturday rebuild must not relabel Friday's prices, including the chart adapter input.
const root = { innerHTML: "", querySelector: () => null };
const states = {
  "daily_read.json": { date: "2026-09-11" },
  "indices.json": { live: { KSE100: 170511.85 }, history: {
    "2026-09-10": { KSE100: 170610.7 }, "2026-09-11": { KSE100: 170511.85 } },
    daily_change: { KSE100: { current: 170511.85, change: 1646.81, percent: 0.98,
      derived_previous_close: 168865.04, source_at: "2026-09-11T16:50:00+05:00", session_date: "2026-09-11" } },
    live_session_date: "2026-09-11",
    source_at: "2026-09-11T16:50:00+05:00", live_at: "2026-09-12T21:00:00+05:00",
    updated: "2026-09-12 21:00" },
  "live.json": { source_at: "2026-09-11T16:50:00+05:00", session_date: "2026-09-11", tickers: {} },
};
let chartInput;
context.$ = () => root;
context.j = async name => states[name] || {};
context.window.HennethTodayCharts = { enhance: (_root, input) => { chartInput = input; } };
await context.window.HennethTodayRenderer();
assert.match(root.innerHTML, /Index snapshot · 2026-09-11T16:50:00\+05:00/);
assert.doesNotMatch(root.innerHTML, /2026-09-12/);
assert.equal(chartInput.live.source_at, states["live.json"].source_at);
assert.equal(chartInput.index.updated, states["indices.json"].source_at);
assert.match(root.innerHTML, /WHAT CHANGED/);
assert.match(root.innerHTML, /1,646.81 points/);
assert.match(root.innerHTML, /\+0\.98%/);
assert.doesNotMatch(root.innerHTML, /-98\.85/);
delete states["indices.json"].source_at;
await context.window.HennethTodayRenderer();
assert.match(root.innerHTML, /Index snapshot · date unknown/);
assert.doesNotMatch(root.innerHTML, /WHAT CHANGED/);
console.log("today price source dates: PASS (capture time never substitutes for exchange time)");

// A malformed official move must be unknown, even when historical rows would produce a number.
states["indices.json"] = {
  live: { KSE100: 170511.85 }, history: { "2026-09-10": { KSE100: 170610.7 }, "2026-09-11": { KSE100: 170511.85 } },
  daily_change: { KSE100: { current: 170511.85, change: -10, percent: -9.09,
    derived_previous_close: 170521.85, source_at: "2026-09-11T16:50:00+05:00", session_date: "2026-09-11" } },
  live_session_date: "2026-09-11", source_at: "2026-09-11T16:50:00+05:00"
};
await context.window.HennethTodayRenderer();
assert.doesNotMatch(root.innerHTML, /WHAT CHANGED/);
assert.match(root.innerHTML, /CURRENT SNAPSHOT/);
console.log("today official daily-change checks: PASS (coherent metadata used; malformed metadata does not fall back to history)");

// Offline fallback fixture: an old quant close keeps its own date while a live row
// uses the newer live snapshot and never falls back through LDCP as current price.
states["daily_read.json"] = { date: "2026-09-11", tone: "cautious", catalysts: [] };
states["quant.json"] = { tickers: {
  PHDL: { close: 50.4, date: "2025-01-20", ret_1d: 1.2, ret_5d: -2.3, ret_20d: 4.5 },
  LIVE: { close: 99, date: "2026-09-11", ret_1d: 2.5, ret_5d: 3.5, ret_20d: 5.5 },
} };
states["live.json"] = { source_at: "2026-09-11T16:50:00+05:00", tickers: {
  PHDL: { ldcp: 51.1 },
  LIVE: { current: 110, ldcp: 105 },
} };
states["universe.json"] = { symbols: { PHDL: { name: "Phool" }, LIVE: { name: "Live Co" } } };
context.watchlist = () => ["PHDL", "LIVE"];
await context.window.HennethTodayRenderer();
assert.match(root.innerHTML, /PHDL/);
assert.match(root.innerHTML, /50\.4/);
assert.match(root.innerHTML, /Last available close · 2025-01-20/);
assert.match(root.innerHTML, /2025-01-20/);
assert.match(root.innerHTML, /DPS snapshot · 2026-09-11T16:50:00\+05:00/);
assert.match(root.innerHTML, /110/);
assert.doesNotMatch(root.innerHTML, /2026-09-12/);
assert.doesNotMatch(root.innerHTML, /PHDL[^<]*51\.1/);
console.log("today fallback price provenance: PASS (per-row prices, sources, and quant dates render without future labels)");
