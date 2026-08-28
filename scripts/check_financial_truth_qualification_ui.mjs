#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const APP = fs.readFileSync(path.join(ROOT, "Henneth Desk 2.CI.0", "app.js"), "utf8");
const SLICE = JSON.parse(fs.readFileSync(path.join(ROOT, "Henneth Desk 2.CI.0", "data", "company_intelligence.json"), "utf8"));
const STATE = JSON.parse(fs.readFileSync(path.join(ROOT, "state", "company_intel", "financial_truth_qualification.json"), "utf8"));
let checks = 0;
const assert = (condition, message) => { checks += 1; if (!condition) throw new Error(message); };

try {
  const rows = Array.isArray(SLICE.tickers) ? SLICE.tickers : [];
  assert(rows.length === 20, "CI slice must contain the 20-company pilot");
  assert(APP.includes("${renderFinancialTruthQualification(r)}"), "Financial Baseline must render financial-truth qualification");
  const start = APP.indexOf("function renderFinancialTruthQualification");
  const end = APP.indexOf("function referenceCaseRows", start);
  assert(start >= 0 && end > start, "financial-truth renderer missing");
  const renderer = APP.slice(start, end);
  for (const token of ["r.financial_truth_qualification", "annual_income_triplets", "qualified_reported_quarter_fact_sets", "documented_interim_metadata", "annual_operating_cash_flow", "financial_tie_out", "candidate_documents", "does not qualify facts"]) assert(renderer.includes(token), `renderer missing ${token}`);
  assert(!/fetch\(|filter\(|reduce\(|parsePdf|parsePDF/i.test(renderer), "renderer must display only backend state");
  for (const row of rows) {
    const truth = row.financial_truth_qualification;
    const expected = STATE.companies?.[row.symbol];
    assert(truth && typeof truth === "object", `${row.symbol} financial truth missing`);
    assert(JSON.stringify(truth) === JSON.stringify(expected), `${row.symbol} financial truth slice mismatch`);
    assert(truth.status === "not_qualified", `${row.symbol} may not claim qualification`);
    assert(truth.downstream?.forecast === "blocked_financial_truth_not_qualified", `${row.symbol} forecast must stay blocked`);
  }
  console.log(`financial_truth_qualification_ui: PASS (${checks} UI/data assertions, ${rows.length} company rows)`);
} catch (error) {
  console.error(`financial_truth_qualification_ui: FAIL - ${error.message}`);
  process.exitCode = 1;
}
