#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const APP_PATH = path.join(ROOT, "Henneth Desk 2.CI.0", "app.js");
const CSS_PATH = path.join(ROOT, "Henneth Desk 2.CI.0", "styles.css");
const SLICE_PATH = path.join(ROOT, "Henneth Desk 2.CI.0", "data", "company_intelligence.json");
const ASSUMPTIONS_PATH = path.join(ROOT, "state", "company_intel", "financial_engine_assumptions.json");

const app = fs.readFileSync(APP_PATH, "utf8");
const css = fs.readFileSync(CSS_PATH, "utf8");
const slice = JSON.parse(fs.readFileSync(SLICE_PATH, "utf8"));
const assumptions = JSON.parse(fs.readFileSync(ASSUMPTIONS_PATH, "utf8"));
let checks = 0;

function assert(condition, message) {
  checks += 1;
  if (!condition) throw new Error(message);
}

function functionBlock(source, name, nextName) {
  const start = source.indexOf(`function ${name}`);
  const end = nextName ? source.indexOf(`function ${nextName}`, start + 1) : -1;
  assert(start >= 0, `${name} renderer missing`);
  return source.slice(start, end >= 0 ? end : undefined);
}

function candidateRefs(row) {
  const readiness = row.forecast_readiness || {};
  return readiness.qualification_candidate_document_refs || readiness.qualification_candidate_documents || [];
}

function assumptionGap(row) {
  return row.financial_engine_assumption_gaps;
}

function manifestGap(symbol) {
  return assumptions.assumption_gaps?.companies?.[symbol];
}

function list(value) {
  return Array.isArray(value) ? value : [];
}

function main() {
  const rows = Array.isArray(slice.tickers) ? slice.tickers : [];
  const symbols = rows.map(row => row?.symbol).filter(Boolean);
  assert(symbols.length === 20 && new Set(symbols).size === 20, "CI slice must contain exactly 20 unique pilot companies");

  const readinessRows = rows.filter(row => row && Object.hasOwn(row, "forecast_readiness"));
  assert(readinessRows.length === 20, "row.forecast_readiness must be emitted for all 20 pilot companies");

  for (const row of rows) {
    const readiness = row.forecast_readiness;
    assert(readiness && typeof readiness === "object" && !Array.isArray(readiness), `${row.symbol} forecast_readiness missing`);
    if (readiness.status === "input_ready") {
      assert(readiness.qualified_period_count >= 3, `${row.symbol} qualified period count must be at least three`);
      assert(readiness.missing_requirements.length === 0, `${row.symbol} input-ready row must not name missing input requirements`);
    } else {
      assert(typeof readiness.status === "string" && readiness.status.startsWith("blocked"), `${row.symbol} forecast readiness must remain blocked without qualified inputs`);
      assert(readiness.missing_requirements.length > 0, `${row.symbol} blocked row must name missing requirements`);
    }
    assert(readiness.model_registry && typeof readiness.model_registry === "object" && !Array.isArray(readiness.model_registry), `${row.symbol} model_registry missing`);
    assert(readiness.model_registry.status === "covered", `${row.symbol} qualitative driver registry must be covered`);
    assert(readiness.model_registry.coverage_type === "qualitative_sector_driver_registry", `${row.symbol} registry coverage type missing`);
    assert(typeof readiness.registry_version === "string" && readiness.registry_version.length > 0, `${row.symbol} registry_version missing`);
    assert(readiness.model_adapter && typeof readiness.model_adapter === "object", `${row.symbol} numerical adapter metadata missing`);
    if (readiness.status === "input_ready") {
      assert(readiness.model_adapter.status === "available", `${row.symbol} input-ready row must expose an available adapter`);
      assert(readiness.model_adapter.selected_sector === "CEMENT", `${row.symbol} available adapter must be cement-scoped`);
      assert(readiness.model_adapter.source_owner, `${row.symbol} available adapter must name the formula source owner`);
    } else if (readiness.model_adapter.status === "available") {
      assert(readiness.model_adapter.selected_sector === "CEMENT", `${row.symbol} available adapter must be cement-scoped`);
    } else {
      assert(readiness.model_adapter.status === "unavailable", `${row.symbol} unavailable adapter status mismatch`);
    }
    assert(Number.isInteger(readiness.qualified_period_count), `${row.symbol} qualified_period_count missing`);
    assert(Array.isArray(readiness.missing_requirements), `${row.symbol} missing_requirements missing`);
    assert(Array.isArray(candidateRefs(row)), `${row.symbol} qualification candidate document refs missing`);
    for (const doc of candidateRefs(row)) {
      assert(doc && typeof doc === "object" && !Array.isArray(doc), `${row.symbol} candidate ref must be object`);
      assert(doc.document_id || doc.doc_id || doc.ref_id, `${row.symbol} candidate ref must carry official document id`);
      assert(/^https?:\/\//i.test(String(doc.source_url || doc.url || "")), `${row.symbol} candidate ref must carry official http(s) source`);
    }
    const downstream = readiness.downstream_status || {};
    for (const key of ["forecast", "valuation", "market_expectations", "numeric_impact"]) {
      assert(typeof downstream[key] === "string" && downstream[key].startsWith("blocked"), `${row.symbol} ${key} must remain blocked`);
    }
    assert(readiness.policy && typeof readiness.policy === "object" && !Array.isArray(readiness.policy), `${row.symbol} policy missing`);
    assert(Array.isArray(readiness.limitations), `${row.symbol} limitations missing`);

    const gap = assumptionGap(row);
    const manifest = manifestGap(row.symbol);
    assert(gap && typeof gap === "object" && !Array.isArray(gap), `${row.symbol} financial_engine_assumption_gaps missing`);
    assert(manifest && typeof manifest === "object" && !Array.isArray(manifest), `${row.symbol} source assumption_gaps manifest missing`);
    assert(gap.status === manifest.status, `${row.symbol} gap status does not match manifest`);
    assert(gap.forecast_readiness_status === manifest.forecast_readiness_status, `${row.symbol} readiness status does not match manifest`);
    assert(gap.financial_model_inputs_status === manifest.financial_model_inputs_status, `${row.symbol} financial input status does not match manifest`);
    assert(gap.reference_cases_can_satisfy_missing_records === false, `${row.symbol} reference cases must not satisfy missing approved records`);
    assert(gap.next_required_action === manifest.next_required_action, `${row.symbol} next action does not match manifest`);
    assert(gap.policy?.gap_manifest_only === true, `${row.symbol} gap manifest policy missing`);
    assert(gap.policy?.does_not_approve_assumptions === true, `${row.symbol} approval policy missing`);
    assert(gap.policy?.does_not_compute_formal_outputs === true, `${row.symbol} no-compute policy missing`);
    assert(gap.policy?.derived_reference_cases_are_not_approved_records === true, `${row.symbol} reference-case policy missing`);
    for (const product of ["forecast", "valuation", "market_expectations"]) {
      const projected = gap.products?.[product];
      const source = manifest.products?.[product];
      assert(projected && typeof projected === "object" && !Array.isArray(projected), `${row.symbol} ${product} projected gap missing`);
      assert(source && typeof source === "object" && !Array.isArray(source), `${row.symbol} ${product} manifest gap missing`);
      assert(projected.status === source.status, `${row.symbol} ${product} status mismatch`);
      assert(JSON.stringify(list(projected.required_approved_records)) === JSON.stringify(list(source.required_approved_records)), `${row.symbol} ${product} required approved records mismatch`);
      assert(JSON.stringify(list(projected.missing_approved_records)) === JSON.stringify(list(source.missing_approved_records)), `${row.symbol} ${product} missing approved records mismatch`);
      assert(JSON.stringify(list(projected.missing_prerequisites)) === JSON.stringify(list(source.missing_prerequisites)), `${row.symbol} ${product} missing prerequisites mismatch`);
      assert(list(projected.accepted_records).every(record => record.metric && record.record_type && record.approval_scope && record.source_id && record.source_path), `${row.symbol} ${product} accepted records must retain source fields`);
    }
  }

  assert(app.includes('["forecast", "Forecast readiness"]'), "Forecast Readiness tab missing");
  assert(app.includes('state.view === "forecast" ? renderForecastReadiness(r)'), "Forecast Readiness tab is not wired");
  assert(app.includes("function renderForecastReadiness(r)"), "Forecast Readiness renderer missing");
  const block = functionBlock(app, "renderForecastReadiness", "renderFinancialCoverage");
  assert(block.includes("r.forecast_readiness"), "renderer must read row.forecast_readiness");
  assert(block.includes("readiness.status"), "exact backend status must be displayed");
  assert(block.includes("readiness.model_registry"), "model_registry must be displayed");
  assert(block.includes("readiness.registry_version") && block.includes("readiness.model_adapter"), "registry and adapter states must be displayed");
  assert(block.includes("readiness.qualified_period_count"), "qualified_period_count must be displayed");
  assert(block.includes("readiness.missing_requirements"), "missing requirements must be displayed");
  assert(block.includes("qualification_candidate_document_refs") && block.includes("readinessDocLink(doc)"), "qualification candidate refs must be displayed as official refs");
  assert(block.includes("downstream_status") && block.includes("numeric_impact"), "downstream blocked states must include numeric impact");
  assert(block.includes("readiness.policy") && block.includes("readiness.limitations"), "policy and limitations must be displayed");
  assert(block.includes("does not infer qualification, calculate projections, value the company, estimate odds, emit targets, or turn this into advice"), "read-only no-forecast boundary copy missing");
  assert(app.includes("function readinessDocLink(doc)") && app.includes("safeHref(doc?.source_url || doc?.url)"), "candidate document links must use safeHref");
  assert(app.includes("function renderFinancialEngineAssumptionReview(r)"), "financial engine assumption review renderer missing");
  assert(app.includes("financial_engine_assumption_gaps"), "financial engine assumption gaps field is not read by the app");
  assert(app.includes("financial_engine_assumptions.assumption_gaps"), "assumption gap manifest source label missing");
  assert(app.includes("does not approve assumptions, compute formal outputs, or turn reference cases into forecast inputs"), "assumption review boundary copy missing");
  assert(app.includes("reference_cases_can_satisfy_missing_records") && app.includes("Reference cases satisfy gaps"), "reference-case non-activation status missing");
  assert(app.includes("function renderAssumptionGapProduct") && app.includes("required_approved_records") && app.includes("missing_approved_records") && app.includes("accepted_records"), "assumption review product tables missing");
  assert(app.includes("safeHref(record?.source_url)"), "assumption record links must use safeHref");

  const reviewBlock = functionBlock(app, "renderFinancialEngineAssumptionReview", "renderEventToValueProductReadiness");
  assert(reviewBlock.includes("r.financial_engine_assumption_gaps"), "assumption review must read row.financial_engine_assumption_gaps");
  assert(reviewBlock.includes("does_not_approve_assumptions") && reviewBlock.includes("does_not_compute_formal_outputs"), "assumption review must display manifest policy");
  assert(!/\b(?:approve|approved)\s*\(/i.test(reviewBlock), "assumption review must not call approval code");
  assert(!/\b(?:fetch|companyThesisRequest|authRequest|calculateScenario|setScenarioInputs)\s*\(/i.test(reviewBlock), "assumption review must not fetch, write, or calculate");
  assert(!/\bvalue\b/.test(reviewBlock), "assumption review must not render accepted assumption values");

  const forbidden = [
    /\b(?:eps|price|revenue|income|cashflow|cash_flow|fcf|ebitda)\s*[*+\-/]/i,
    /\b(?:target|upside|downside|fair value|buy|sell|hold|recommend|should buy|should sell)\b/i,
    /\b(?:probability|odds|chance)\s*[:=]/i,
    /\b(?:forecast|valuation|projection|numeric impact)\s*[:=]\s*(?!.*blocked)/i,
    /\b(?:calculate|compute|infer|derive|project|predict|estimate|valueCompany)\s*\(/i,
    /\bfetch\s*\(/i,
  ];
  const sanitized = block
    .replace("does not infer qualification, calculate projections, value the company, estimate odds, emit targets, or turn this into advice", "")
    .replaceAll("Forecast / valuation readiness", "")
    .replaceAll("Forecast Readiness", "");
  for (const pattern of forbidden) assert(!pattern.test(sanitized), `renderer contains forbidden calculation/advice pattern: ${pattern}`);

  assert(css.includes(".forecast-readiness-shell") && css.includes(".forecast-readiness-summary") && css.includes(".forecast-readiness-docs"), "Forecast Readiness styles missing");
  assert(/@media \(max-width:900px\)[\s\S]*?\.forecast-readiness-summary/.test(css), "Forecast Readiness responsive styles missing");

  console.log(`forecast_readiness_ui: PASS (${checks} UI assertions, ${symbols.length} company rows)`);
}

try {
  main();
} catch (error) {
  console.error(`forecast_readiness_ui: FAIL - ${error.message}`);
  process.exitCode = 1;
}
