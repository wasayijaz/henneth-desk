#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const app = fs.readFileSync(path.join(ROOT, "Henneth Desk 2.CI.0", "app.js"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "Henneth Desk 2.CI.0", "styles.css"), "utf8");
const slice = JSON.parse(fs.readFileSync(path.join(ROOT, "Henneth Desk 2.CI.0", "data", "company_intelligence.json"), "utf8"));
let checks = 0;
const assert = (condition, message) => { checks += 1; if (!condition) throw new Error(message); };

function forward(baseline, growth, margin, pe) {
  const revenue = baseline.revenue * (1 + growth / 100);
  const income = revenue * margin / 100;
  const eps = income / baseline.shares_out;
  const price = eps * pe;
  return { revenue, income, eps, price, deltaPct: (price / baseline.latest_price - 1) * 100 };
}

function reverse(baseline, margin, pe) {
  const eps = baseline.latest_price / pe;
  const income = eps * baseline.shares_out;
  const revenue = income / (margin / 100);
  return { eps, income, revenue, growthPct: (revenue / baseline.revenue - 1) * 100 };
}

function gap(baseline, growth, margin, pe) {
  return reverse(baseline, margin, pe).growthPct - growth;
}

function main() {
  assert(slice.tickers.length === 20, "exact 20-company UI boundary");
  for (const row of slice.tickers) {
    const lab = row.scenario_lab;
    assert(lab?.symbol === row.symbol, `${row.symbol}: scenario seam`);
    assert(lab?.status?.scenario_lab === "blocked_financial_truth_not_qualified", `${row.symbol}: readiness`);
    assert(lab?.financial_truth_status === "not_qualified", `${row.symbol}: financial truth binding`);
    assert(lab.scenario === null && lab.reverse_expectations === null, `${row.symbol}: no chosen case`);
    assert(lab.market_expectations_gap === null, `${row.symbol}: no chosen gap`);
    assert(lab.formula_ids.includes("expectations_gap.v1"), `${row.symbol}: gap formula id`);
    assert(lab.ebitda === null && lab.fcf === null && lab.dcf === null, `${row.symbol}: blocked outputs`);
  }
  assert(app.includes('["scenarios", "Scenarios"]') && app.includes('state.view === "scenarios" ? renderScenarioLab(r)'), "tab and dispatch");
  assert(app.includes("function renderScenarioLab(r)") && app.includes('id="scenarioForm"'), "scenario renderer/form");
  assert(app.includes("function scenarioLabIsActive(lab, financialTruth)") && app.includes('financialTruth?.status === "qualified"') && app.includes('lab?.financial_truth_status === "qualified"'), "financial truth interaction gate");
  assert(app.includes('placeholder="Enter assumption"') && !app.includes('id="scenarioGrowth" type="number" value="'), "blank caller inputs");
  assert(app.includes("state.scenario.bySymbol[symbol]") && app.includes("blankScenarioState"), "per-company memory");
  assert(app.includes("revenue * (1 + growth / 100)") && app.includes("scenarioRevenue * margin / 100") && app.includes("scenarioEps * pe"), "forward formulas mirror Python");
  assert(app.includes("price / pe") && app.includes("requiredEps * shares") && app.includes("requiredNetIncome / (margin / 100)"), "reverse formulas mirror Python");
  assert(app.includes("requiredRevenueGrowthPct - growth"), "gap formula mirrors Python");
  assert(app.includes("-99.999999, 1000") && app.includes("0.000001, 100") && app.includes("0.000001, 200"), "bounds mirror Python");
  assert(app.includes("current.result = null") && app.includes('role="alert"'), "invalid clearing and accessible error");
  assert(app.includes("safeHref(provenance.fundamentals_source_url)") && app.includes("safeHref(provenance.price_source_url)"), "safe source links");
  const block = app.slice(app.indexOf("function renderScenarioLab"), app.indexOf("const ASK_SECTION_LABELS"));
  assert(!/fair value|target price|\bbuy\b|\bsell\b|\bhold\b|\badvice\b/i.test(block), "no verdict/advice labels");
  assert(block.includes("Multiple-implied price") && block.includes("Reverse expectations") && block.includes("Market-implied gap"), "correct product labels");
  assert(block.includes('["forecast", "valuation", "market expectations", "scenario lab", "EBITDA", "FCF", "DCF"]'), "blocked products visible");
  assert(css.includes(".scenario-shell") && css.includes("@media (max-width:900px)") && css.includes("@media (max-width:560px)"), "responsive scenario CSS");
  const baseline = { revenue: 1000, shares_out: 100, latest_price: 11 };
  const f = forward(baseline, 10, 20, 5);
  assert(f.revenue === 1100 && f.income === 220 && f.eps === 2.2 && f.price === 11 && f.deltaPct === 0, "forward golden");
  const r = reverse(baseline, 20, 5);
  assert(Math.abs(r.eps - 2.2) < 1e-9 && Math.abs(r.income - 220) < 1e-9 && Math.abs(r.revenue - 1100) < 1e-9 && Math.abs(r.growthPct - 10) < 1e-9, "reverse golden");
  assert(Math.abs(gap(baseline, 5, 20, 5) - 5) < 1e-9, "gap golden");
  console.log(`company_scenario_lab_ui: PASS (${checks} assertions, 20 company rows)`);
}

try { main(); } catch (error) { console.error(`company_scenario_lab_ui: FAIL — ${error.message}`); process.exitCode = 1; }
