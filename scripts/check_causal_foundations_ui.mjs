#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const APP_PATH = path.join(ROOT, "Henneth Desk 2.CI.0", "app.js");
const CSS_PATH = path.join(ROOT, "Henneth Desk 2.CI.0", "styles.css");
const SLICE_PATH = path.join(ROOT, "Henneth Desk 2.CI.0", "data", "company_intelligence.json");

const app = fs.readFileSync(APP_PATH, "utf8");
const css = fs.readFileSync(CSS_PATH, "utf8");
const slice = JSON.parse(fs.readFileSync(SLICE_PATH, "utf8"));
let checks = 0;

function assert(condition, message) {
  checks += 1;
  if (!condition) throw new Error(message);
}

function rendererBlock() {
  const start = app.indexOf("function renderCausalFoundations");
  const end = app.indexOf("function overviewObjectItems", start);
  assert(start >= 0 && end > start, "causal renderer block must exist before overview");
  return app.slice(start, end);
}

function requireString(value, label) {
  assert(typeof value === "string" && value.length > 0, `${label} must be a non-empty string`);
}

try {
  const rows = Array.isArray(slice.tickers) ? slice.tickers : [];
  const symbols = rows.map(row => row?.symbol).filter(Boolean);
  assert(symbols.length === 20 && new Set(symbols).size === 20, "CI slice must contain exactly 20 unique pilot companies");

  assert(app.includes('state.view === "causal" ? renderCausalFoundations(r)'), "causal tab dispatch is missing");
  assert(app.includes('["causal", `Causal map ${r.causal_foundations?.causal_rows?.length || 0}`]'), "causal tab label is missing");
  assert(app.includes("function causalPolicyStatus(policy, key)"), "causal policy helper is missing");
  assert(app.includes("function renderCausalEventRefs(refs)"), "event-ref renderer is missing");
  assert(app.includes("function renderCausalStudyRefs(refs)"), "study-ref renderer is missing");

  const block = rendererBlock();
  for (const token of [
    "r.causal_foundations",
    "causal_rows",
    "evidence_status",
    "driver",
    "target",
    "edge_basis",
    "event_refs",
    "event_study_refs",
    "next_data_requirement",
    "numeric_impact",
    "forecast",
    "valuation",
    "does not estimate impact, forecast, value the company, or turn this into advice",
  ]) {
    assert(block.includes(token), `causal renderer missing ${token}`);
  }

  assert(!block.includes("r.driver_graph"), "causal renderer must not derive from driver_graph");
  assert(!block.includes("r.sector"), "causal renderer must not substitute the row sector for emitted foundations");
  assert(!block.includes("r.operating_events"), "causal renderer must not derive from operating_events");
  assert(!block.includes("r.event_studies"), "causal renderer must not derive from event_studies");
  assert(!block.includes(".reduce("), "causal renderer must not derive evidence aggregates in the browser");
  assert(block.includes("coverage.evidence_status_counts"), "causal status counts must come from emitted coverage");
  assert(block.includes('coverage.driver_edge_count ?? "unknown"') && block.includes('coverage.causal_row_count ?? "unknown"'), "causal summary must fail closed when emitted counts are absent");
  assert(!/revenue_impact|ebitda_impact|eps_impact|fcf_impact|valuation_impact/.test(block), "causal renderer must not display scenario impact fields");
  assert(!/\b(Math|parseFloat|parseInt)\b/.test(block), "causal renderer must not calculate estimates");
  assert(!/\b(price|shares|entry|stop|target_price)\b\s*[+\-*/=]/i.test(block), "causal renderer must not calculate trading or valuation values");

  for (const token of [
    ".causal-shell",
    ".causal-summary",
    ".causal-status-strip",
    ".causal-card",
    ".causal-edge",
    ".causal-policy",
    "@media (max-width:900px)",
    "@media (max-width:560px)",
  ]) {
    assert(css.includes(token), `css missing ${token}`);
  }

  let causalRows = 0;
  let officialEventRefs = 0;
  let strictStudyRefs = 0;
  for (const row of rows) {
    const foundations = row.causal_foundations;
    assert(foundations && typeof foundations === "object" && !Array.isArray(foundations), `${row.symbol}: causal_foundations must be an object`);
    assert(foundations.symbol === row.symbol, `${row.symbol}: causal_foundations symbol mismatch`);
    requireString(foundations.sector, `${row.symbol}: sector`);
    assert(Array.isArray(foundations.causal_rows), `${row.symbol}: causal_rows must be an array`);
    assert(foundations.causal_rows.length > 0, `${row.symbol}: causal_rows must not be empty`);
    assert(foundations.coverage && typeof foundations.coverage === "object", `${row.symbol}: coverage must exist`);
    assert(foundations.coverage.causal_row_count === foundations.causal_rows.length, `${row.symbol}: coverage causal count mismatch`);

    for (const cause of foundations.causal_rows) {
      causalRows += 1;
      assert(cause.symbol === row.symbol, `${row.symbol}: causal row symbol mismatch`);
      requireString(cause.causal_id, `${row.symbol}: causal_id`);
      requireString(cause.edge_id, `${row.symbol}: edge_id`);
      requireString(cause.driver, `${row.symbol}: driver`);
      requireString(cause.target, `${row.symbol}: target`);
      requireString(cause.statement_line, `${row.symbol}: statement_line`);
      requireString(cause.unit, `${row.symbol}: unit`);
      requireString(cause.edge_basis, `${row.symbol}: edge_basis`);
      requireString(cause.evidence_status, `${row.symbol}: evidence_status`);
      requireString(cause.next_data_requirement, `${row.symbol}: next_data_requirement`);
      assert(Array.isArray(cause.event_refs), `${row.symbol}: event_refs must be an array`);
      assert(Array.isArray(cause.event_study_refs), `${row.symbol}: event_study_refs must be an array`);
      assert(cause.policy && typeof cause.policy === "object" && !Array.isArray(cause.policy), `${row.symbol}: policy must be an object`);
      assert(cause.policy.numeric_impact === "blocked", `${row.symbol}: numeric impact must stay blocked`);
      assert(cause.policy.forecast === "blocked", `${row.symbol}: forecast must stay blocked`);
      assert(cause.policy.valuation === "blocked", `${row.symbol}: valuation must stay blocked`);

      for (const ref of cause.event_refs) {
        officialEventRefs += 1;
        requireString(ref.event_id, `${row.symbol}: event ref id`);
        requireString(ref.event_type, `${row.symbol}: event ref type`);
        assert(ref.effective_date === null || typeof ref.effective_date === "string", `${row.symbol}: event ref date must be null or string`);
        requireString(ref.source_url, `${row.symbol}: event ref source URL`);
      }
      for (const ref of cause.event_study_refs) {
        strictStudyRefs += 1;
        requireString(ref.study_id, `${row.symbol}: study ref id`);
        requireString(ref.event_id, `${row.symbol}: study event id`);
        assert(typeof ref.strict_no_lookahead === "boolean", `${row.symbol}: strict_no_lookahead must be boolean`);
        requireString(ref.baseline_status, `${row.symbol}: study baseline status`);
      }
    }
  }

  assert(causalRows > 0, "causal rows must be present");
  console.log(`causal_foundations_ui: PASS (${checks} assertions, ${symbols.length} company rows, ${causalRows} causal rows, ${officialEventRefs} event refs, ${strictStudyRefs} study refs)`);
} catch (error) {
  console.error(`causal_foundations_ui: FAIL - ${error.message}`);
  process.exitCode = 1;
}
