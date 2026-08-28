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

function main() {
  const rows = Array.isArray(slice.tickers) ? slice.tickers : [];
  const symbols = rows.map(row => row?.symbol).filter(Boolean);
  assert(symbols.length === 20 && new Set(symbols).size === 20, "CI slice must contain exactly 20 unique pilot companies");

  for (const row of rows) {
    const coverage = row.financial_coverage;
    assert(coverage && typeof coverage === "object" && !Array.isArray(coverage), `${row.symbol} financial_coverage missing`);
    assert(coverage.symbol === row.symbol, `${row.symbol} financial_coverage symbol mismatch`);
    assert(typeof coverage.status === "string" && coverage.status.length > 0, `${row.symbol} status missing`);
    assert(Number.isInteger(coverage.indexed_official_financial_doc_count), `${row.symbol} indexed doc count missing`);
    assert(Array.isArray(coverage.required_annual_periods) && coverage.required_annual_periods.length === 3, `${row.symbol} annual slots mismatch`);
    assert(Array.isArray(coverage.missing_revenue_pat_eps_by_annual_period) && coverage.missing_revenue_pat_eps_by_annual_period.length === 3, `${row.symbol} missing metric slots mismatch`);
    const slots = coverage.missing_revenue_pat_eps_by_annual_period;
    if (row.forecast_readiness?.status === "input_ready") {
      assert(slots.filter(slot => slot.period_end).some(slot => (slot.missing_metrics || []).length === 0 && slot.status === "complete"), `${row.symbol} qualified annual revenue/PAT/EPS coverage missing`);
    } else {
      assert(slots.every(slot => Array.isArray(slot.missing_metrics) && Array.isArray(slot.present_model_ready_metrics) && typeof slot.status === "string"), `${row.symbol} missing revenue/PAT/EPS coverage is not explicit`);
    }
    assert(coverage.audit_only_series && Number.isInteger(coverage.audit_only_series.audit_only_fact_count), `${row.symbol} audit-only count missing`);
    assert(coverage.qualification_queue && typeof coverage.qualification_queue.status === "string", `${row.symbol} queue status missing`);
    assert(Array.isArray(coverage.qualification_queue.candidate_documents), `${row.symbol} candidate docs missing`);
    assert(coverage.model_readiness?.downstream_status?.forecast === "blocked_not_implemented", `${row.symbol} forecast must remain blocked`);
    assert(coverage.model_readiness?.downstream_status?.valuation === "blocked_not_implemented", `${row.symbol} valuation must remain blocked`);
  }

  assert(app.includes("${renderFinancialCoverage(r)}"), "Financial Coverage panel is inside Financial Baseline");
  assert(app.includes("function renderFinancialCoverage(r)"), "Financial Coverage renderer exists");
  const coverageStart = app.indexOf("function renderFinancialCoverage");
  const coverageEnd = app.indexOf("function renderFinancialTruthQualification");
  const block = app.slice(coverageStart, coverageEnd);
  assert(block.includes("r.financial_coverage"), "renderer reads row.financial_coverage");
  assert(block.includes("coverage.status"), "status is displayed");
  assert(block.includes("indexed_official_financial_doc_count"), "indexed official doc count is displayed");
  assert(block.includes("required_annual_periods"), "three annual slots are displayed");
  assert(app.includes("function coveragePeriodLabel(slot)") && app.includes("coveragePeriodLabel(slot)") && app.includes("unresolved"), "explicit vs unresolved annual dates are displayed");
  assert(block.includes("missing_revenue_pat_eps_by_annual_period"), "missing revenue/PAT/EPS rows are displayed");
  assert(block.includes("audit_only_fact_count") && block.includes("Quarantined / not promoted"), "audit-only count is labelled quarantined/not promoted");
  assert(block.includes("qualification_queue") && block.includes("candidate_documents"), "qualification queue and candidate documents are displayed");
  assert(block.includes("coverageDocLink(doc)") && app.includes("safeHref(doc?.source_url)"), "official URLs use safeHref");
  assert(block.includes("downstream.forecast") && block.includes("downstream.valuation"), "forecast and valuation blocked states are displayed");
  assert(block.includes("does not infer periods, promote values, parse PDFs, or trigger restage"), "browser read-only boundary is visible");
  assert(!/fetch\(|companyThesisRequest|restage|parsePdf|parsePDF|calculate|infer/i.test(block.replace("does not infer periods, promote values, parse PDFs, or trigger restage", "")), "renderer must not fetch, infer, calculate, parse, or restage");

  assert(css.includes(".financial-coverage-panel") && css.includes(".financial-coverage-summary") && css.includes(".financial-coverage-docs"), "Financial Coverage styles exist");
  assert(/@media \(max-width:900px\)[\s\S]*?\.financial-coverage-summary/.test(css), "Financial Coverage has mobile layout");

  console.log(`financial_coverage_ui: PASS (${checks} UI assertions, ${symbols.length} company rows)`);
}

try { main(); } catch (error) {
  console.error(`financial_coverage_ui: FAIL - ${error.message}`);
  process.exitCode = 1;
}
