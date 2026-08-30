#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const APP = path.join(ROOT, "Henneth Desk 2.CI.0", "app.js");
const CSS = path.join(ROOT, "Henneth Desk 2.CI.0", "styles.css");
const SLICE = path.join(ROOT, "Henneth Desk 2.CI.0", "data", "company_intelligence.json");
const STATE = path.join(ROOT, "state", "company_intel", "event_to_value_product_readiness.json");
const NAV = path.join(ROOT, "scripts", "check_company_navigation_ui.mjs");

let checks = 0;
const assert = (condition, message) => {
  checks += 1;
  if (!condition) throw new Error(message);
};

function main() {
  const app = fs.readFileSync(APP, "utf8");
  const css = fs.readFileSync(CSS, "utf8");
  const nav = fs.readFileSync(NAV, "utf8");
  const slice = JSON.parse(fs.readFileSync(SLICE, "utf8"));
  const state = fs.existsSync(STATE) ? JSON.parse(fs.readFileSync(STATE, "utf8")) : null;

  assert(app.includes('["alpha_readiness", "Event-to-Value readiness"]'), "readiness tab registered");
  assert(app.includes('key: "alpha", label: "Alpha readiness"'), "readiness tree group distinct from case UI");
  assert(app.includes("function renderEventToValueProductReadiness("), "desk renderer present");
  assert(app.includes('state.view === "alpha_readiness" ? renderEventToValueProductReadiness()'), "desk route dispatch");
  assert(!app.includes("renderEventToValueProductReadiness(r)"), "readiness view is desk-level, not company-case");
  const start = app.indexOf("function renderEventToValueProductReadiness(");
  const end = app.indexOf("function renderForecastReadiness(");
  assert(start >= 0 && end > start, "renderer bounded before forecast readiness");
  const body = app.slice(start, end);
  assert(body.includes("event_to_value_product_readiness_not_generated"), "missing projection fail-closed");
  assert(body.includes("This is not an Intelligence Case") || body.includes("does not score a company, open an Intelligence Case"), "visibly distinct from case UI");
  assert(body.includes("esc(metric.label") && body.includes("esc(metric.definition") && body.includes("esc(metric.source_path") && body.includes("esc(reason)"), "readiness values escaped");
  assert(!/you should buy|recommend buying|target price/i.test(body), "advice language absent");
  assert(css.includes(".alpha-readiness-shell") && css.includes("@media (max-width:900px){.alpha-readiness-grid{grid-template-columns:1fr}}"), "mobile readiness stack present");
  assert(nav.includes("alpha_readiness"), "navigation checker knows the new research tool");

  const projected = slice.meta?.event_to_value_product_readiness;
  assert(projected && Array.isArray(projected.metrics) && projected.metrics.length === 12, "slice projects 12 Alpha metrics");
  if (state) {
    assert(projected.product_version === state.product_version, "slice version matches state");
    assert(JSON.stringify(projected.metrics) === JSON.stringify(state.metrics), "slice metrics match state");
  }
  const blocked = (projected.metrics || []).filter(metric => metric.status !== "available");
  for (const metric of blocked) {
    assert(metric.reason, metric.id + " blocked without reason");
  }
  console.log("event_to_value_product_readiness_ui: PASS (" + checks + " assertions)");
}

try { main(); }
catch (error) {
  console.error("event_to_value_product_readiness_ui: FAIL — " + error.message);
  process.exitCode = 1;
}
