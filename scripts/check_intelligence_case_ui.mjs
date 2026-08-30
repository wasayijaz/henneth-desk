#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const APP = path.join(ROOT, "Henneth Desk 2.CI.0", "app.js");
const CSS = path.join(ROOT, "Henneth Desk 2.CI.0", "styles.css");
const INDEX = path.join(ROOT, "Henneth Desk 2.CI.0", "index.html");
const VIEW = path.join(ROOT, "Henneth Desk 2.CI.0", "intelligence_case_view.js");
const VERCEL = path.join(ROOT, "Henneth Desk 2.CI.0", "vercel.json");
const SLICE = path.join(ROOT, "Henneth Desk 2.CI.0", "data", "company_intelligence.json");
const MIDDLEWARE = path.join(ROOT, "Henneth Desk 2.CI.0", "middleware.js");
const NAV_CHECK = path.join(ROOT, "scripts", "check_company_navigation_ui.mjs");

let checks = 0;
const assert = (condition, message) => {
  checks += 1;
  if (!condition) throw new Error(message);
};

function loadView() {
  const context = { window: {}, console };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(VIEW, "utf8"), context);
  return context.window.HennethIntelligenceCaseView;
}

function buildFixture() {
  const fixture = {
    observed_mlcf: {
      symbol: "MLCF",
      status: "observed_seed_available",
      cases: [{
        case_id: "case_mlcf_pioc_control_observed_v1",
        symbol: "MLCF",
        target_symbol: "PIOC",
        case_family: "industrial_cement",
        case_type: "acquisition_control",
        status: "Observed",
        epistemic_type: "reported_fact",
        summary: "Observed official-source seed: MLCF reported a public offer/control transaction for Pioneer Cement.",
        observed_facts: [{
          fact_id: "mlcf_pioc_public_offer_control",
          statement: "MLCF reported a public offer to acquire PIOC shares.",
          reported_values: [{ label: "offer_price", value: "PKR 478.43 per share" }],
          evidence: [{ document_id: "psx:267429", page: 3, source_url: "https://dps.psx.com.pk/download/document/267429.pdf", text: "PUBLIC OFFER" }],
        }],
        alternative_readings: [{
          alternative_id: "public_offer_not_full_model",
          reading: "Official offer/control disclosure, not a quantified earnings model.",
          status: "retained_as_observed_only",
          rejection_condition: "Reject modelling if source-qualified operands are absent.",
        }],
        promotion_blocks: {
          Corroborated: "Blocked: official MLCF/PSX chain, not independent-originator corroboration.",
          Modelled: "Blocked: no source-qualified financial impact model or owner-approved assumptions are attached.",
          Published: "Blocked: no forecast, valuation, reverse-expectations output, investor conclusion or release gate is complete.",
        },
        policy: { observed_only: true, no_forecast: true, no_valuation: true, no_market_expectations: true, no_recommendation: true },
        source_lineage: [{ document_id: "psx:267429", page: 3, source_url: "https://dps.psx.com.pk/download/document/267429.pdf" }],
      }],
    },
    observed_mari: {
      symbol: "MARI",
      status: "observed_seed_available",
      cases: [{
        case_id: "case_mari_offshore_exploration_blocks_observed_v1",
        symbol: "MARI",
        case_family: "e_and_p",
        case_type: "offshore_exploration_block_acquisition",
        status: "Observed",
        epistemic_type: "reported_fact",
        summary: "Observed official-source seed: Mari Energies reported its acquisition of offshore exploration blocks.",
        observed_facts: [{
          fact_id: "mari_offshore_exploration_blocks_acquisition",
          statement: "Mari Energies reported the acquisition of offshore exploration blocks.",
          reported_values: [{ label: "stated_purpose", value: "find new hydrocarbon resources" }],
          evidence: [{ document_id: "psx:265594", page: 3, source_url: "https://dps.psx.com.pk/download/document/265594.pdf", text: "offshore exploration blocks" }],
        }],
        alternative_readings: [{
          alternative_id: "blocks_not_proved_reserves",
          reading: "Block acquisition does not establish reserves or future production.",
          status: "retained_as_observed_only",
          rejection_condition: "Reject promotion if no official source identifies a development path.",
        }],
        promotion_blocks: {
          Corroborated: "Blocked: single official Mari/PSX source.",
          Modelled: "Blocked: no source-qualified working interest or financial-model inputs are attached.",
          Published: "Blocked: no forecast, valuation, reverse-expectations output, investor conclusion or release gate is complete.",
        },
        policy: { observed_only: true, no_forecast: true, no_valuation: true, no_market_expectations: true, no_recommendation: true },
        source_lineage: [{ document_id: "psx:265594", page: 3, source_url: "https://dps.psx.com.pk/download/document/265594.pdf" }],
      }],
    },
    explicit_sections: {
      symbol: "MLCF",
      cases: [{
        case_id: "case_mlcf_pioc_control_observed_v1",
        symbol: "MLCF",
        status: "Observed",
        summary: "Observed seed.",
        sections: {
          mechanism: { status: "blocked", reason: "not_yet_modelled" },
          formulas: { status: "blocked", reason: "formula_id_not_emitted" },
        },
      }],
    },
  };
  return fixture;
}

function main() {
  const app = fs.readFileSync(APP, "utf8");
  const css = fs.readFileSync(CSS, "utf8");
  const index = fs.readFileSync(INDEX, "utf8");
  const vercel = JSON.parse(fs.readFileSync(VERCEL, "utf8"));
  const middleware = fs.readFileSync(MIDDLEWARE, "utf8");
  const navCheck = fs.readFileSync(NAV_CHECK, "utf8");
  const slice = JSON.parse(fs.readFileSync(SLICE, "utf8"));
  const checker = fs.readFileSync(new URL(import.meta.url), "utf8");
  const fixture = buildFixture();
  const api = loadView();

  assert(index.includes('src="intelligence_case_view.js"'), "index loads case view helper");
  assert(app.includes("function renderIntelligenceCase("), "case renderer present");
  assert(app.includes("applyCaseRouteFromLocation"), "path parser wired");
  assert(app.includes("state.caseRoute"), "case route state present");
  assert(app.includes("const routeTicker = state.caseRoute?.ticker || null"), "route ticker is preserved");
  assert(app.includes("allRows.find(item => item && item.symbol === routeTicker)"), "route selects exact company row");
  assert(app.includes("state.caseRoute ? renderIntelligenceCase(r, state.caseRoute.caseId)"), "case route has render priority");
  const deskBlockStart = app.indexOf("function renderDesk(");
  const deskBlockEnd = app.indexOf("function currentPilotSymbols(");
  const deskBlock = app.slice(deskBlockStart, deskBlockEnd);
  assert(/const row = routeTicker[\s\S]*\? allRows\.find\(item => item && item\.symbol === routeTicker\)[\s\S]*: \(state\.selected \? list\.find/.test(deskBlock), "filtered directory cannot replace an exact route row");
  const caseBlockStart = app.indexOf("function renderIntelligenceCase(");
  const caseBlockEnd = app.indexOf("function renderIntelligenceConfidence(");
  assert(caseBlockStart >= 0 && caseBlockEnd > caseBlockStart, "case renderer block bounded");
  const caseBlock = app.slice(caseBlockStart, caseBlockEnd);
  assert(caseBlock.includes("Research, not advice") || caseBlock.includes("research, not advice"), "research-only copy present");
  assert(!/you should buy|recommend buying|target price/i.test(caseBlock), "advice language absent from case renderer");
  assert(!caseBlock.includes('|| "reported_fact"'), "case renderer never defaults epistemic type to reported_fact");
  assert(css.includes(".case-shell"), "case CSS present");
  assert((vercel.rewrites || []).some(rule => rule.source === "/company/:ticker/intelligence/:case_id" && rule.destination === "/"), "CI rewrite present");
  assert(middleware.includes('matcher: "/data/:path*"'), "data gate matcher unchanged");
  assert(middleware.includes("CI_OWNER_USER_ID"), "owner gate unchanged");
  assert(!navCheck.includes("intelligence_case"), "navigation checker left untouched");
  assert(app.includes('fetch("data/company_intelligence.json"'), "live surface still reads the private slice");
  assert(!checker.includes("write" + "FileSync") && !checker.includes("make" + "dirSync"), "checker is read-only");

  const parsed = api.parsePath("/company/mlcf/intelligence/case_mlcf_pioc_control_observed_v1");
  assert(parsed.ticker === "MLCF" && parsed.caseId === "case_mlcf_pioc_control_observed_v1", "path parse");
  assert(api.parsePath("/company/MLCF") === null, "non-case path ignored");

  const missing = api.findCase({ symbol: "MLCF" }, "case_mlcf_pioc_control_observed_v1", "MLCF");
  assert(missing.ok === false && missing.reason === "intelligence_cases_state_missing", "missing state fail-closed");

  for (const key of ["observed_mlcf", "observed_mari"]) {
    const row = { symbol: fixture[key].symbol, intelligence_cases: fixture[key] };
    const found = api.findCase(row, fixture[key].cases[0].case_id, fixture[key].symbol);
    assert(found.ok, key + " found");
    const conclusion = api.resolveSection(found.case, "conclusion");
    const evidence = api.resolveSection(found.case, "evidence");
    const hypotheses = api.resolveSection(found.case, "hypotheses");
    const sources = api.resolveSection(found.case, "sources");
    assert(conclusion.status === "available" && conclusion.epistemic_type === "reported_fact", key + " conclusion");
    assert(evidence.status === "available" && evidence.items.length >= 1, key + " evidence");
    assert(hypotheses.status === "available" && hypotheses.items[0].rejection_condition, key + " hypotheses");
    assert(sources.status === "available", key + " sources");
    for (const sectionKey of ["mechanism", "analogues", "financial_impact", "scenarios", "valuation", "expectations", "confidence", "watch_next", "formulas"]) {
      const section = api.resolveSection(found.case, sectionKey);
      assert(String(section.status).startsWith("blocked"), key + " " + sectionKey + " blocked");
      assert(section.reason && section.reason !== "coming soon" && section.reason !== "placeholder", key + " " + sectionKey + " specific reason");
    }
    assert(api.resolveSection(found.case, "formulas").reason === "formula_id_not_emitted", key + " formula reason");
    const unknown = api.findCase(row, "case_does_not_exist", fixture[key].symbol);
    assert(unknown.ok === false && unknown.reason === "case_not_found", key + " unknown case");
  }

  const mlcfRow = { symbol: "MLCF", intelligence_cases: fixture.observed_mlcf };
  assert(api.findCase(mlcfRow, fixture.observed_mlcf.cases[0].case_id, "MARI").reason === "ticker_identity_mismatch", "unknown or mismatched ticker fails closed");
  assert(api.findCase({ symbol: "MLCF", intelligence_cases: { ...fixture.observed_mlcf, symbol: "MARI" } }, fixture.observed_mlcf.cases[0].case_id, "MLCF").reason === "payload_symbol_mismatch", "cross-symbol payload fails closed");
  const crossSymbolCase = structuredClone(fixture.observed_mlcf);
  crossSymbolCase.cases[0].symbol = "MARI";
  assert(api.findCase({ symbol: "MLCF", intelligence_cases: crossSymbolCase }, crossSymbolCase.cases[0].case_id, "MLCF").reason === "case_symbol_mismatch", "cross-symbol case fails closed");
  const duplicateCases = structuredClone(fixture.observed_mlcf);
  duplicateCases.cases.push(structuredClone(duplicateCases.cases[0]));
  assert(api.findCase({ symbol: "MLCF", intelligence_cases: duplicateCases }, duplicateCases.cases[0].case_id, "MLCF").reason === "duplicate_case_id", "duplicate case ids fail closed");
  const invalidLifecycle = structuredClone(fixture.observed_mlcf);
  invalidLifecycle.cases[0].status = "Draft";
  assert(api.findCase({ symbol: "MLCF", intelligence_cases: invalidLifecycle }, invalidLifecycle.cases[0].case_id, "MLCF").reason === "case_lifecycle_invalid", "invalid lifecycle fails closed");
  const missingEpistemicType = structuredClone(fixture.observed_mlcf);
  delete missingEpistemicType.cases[0].epistemic_type;
  assert(api.findCase({ symbol: "MLCF", intelligence_cases: missingEpistemicType }, missingEpistemicType.cases[0].case_id, "MLCF").reason === "case_epistemic_type_invalid", "missing epistemic type fails closed");
  const invalidEpistemicType = structuredClone(fixture.observed_mlcf);
  invalidEpistemicType.cases[0].epistemic_type = "unknown";
  assert(api.findCase({ symbol: "MLCF", intelligence_cases: invalidEpistemicType }, invalidEpistemicType.cases[0].case_id, "MLCF").reason === "case_epistemic_type_invalid", "invalid epistemic type fails closed");
  const invalidSectionKey = structuredClone(fixture.observed_mlcf);
  invalidSectionKey.cases[0].sections = { unsupported: { status: "blocked" } };
  assert(api.findCase({ symbol: "MLCF", intelligence_cases: invalidSectionKey }, invalidSectionKey.cases[0].case_id, "MLCF").reason === "section_key_invalid", "invalid section key fails closed");
  const invalidSectionStatus = structuredClone(fixture.observed_mlcf);
  invalidSectionStatus.cases[0].sections = { mechanism: { status: "pending" } };
  assert(api.findCase({ symbol: "MLCF", intelligence_cases: invalidSectionStatus }, invalidSectionStatus.cases[0].case_id, "MLCF").reason === "section_status_invalid", "invalid section status fails closed");
  const emptyExplicit = structuredClone(fixture.observed_mlcf.cases[0]);
  emptyExplicit.sections = { evidence: { items: [] }, hypotheses: { text: "   " }, confidence: { dimensions: [] } };
  assert(api.resolveSection(emptyExplicit, "evidence").status === "empty_state", "empty explicit array is an empty state");
  assert(api.resolveSection(emptyExplicit, "hypotheses").status === "empty_state", "empty explicit text is an empty state");
  assert(api.resolveSection(emptyExplicit, "confidence").status === "empty_state", "empty explicit dimensions are an empty state");
  const emptyAvailable = structuredClone(fixture.observed_mlcf.cases[0]);
  emptyAvailable.sections = { evidence: { status: "available", items: [] } };
  assert(api.resolveSection(emptyAvailable, "evidence").status === "empty_state", "available empty section cannot render as available");

  const explicit = api.resolveSection(fixture.explicit_sections.cases[0], "mechanism");
  assert(explicit.reason === "not_yet_modelled", "explicit section reason preserved");
  assert(api.resolveSection(fixture.explicit_sections.cases[0], "formulas").reason === "formula_id_not_emitted", "explicit formula reason preserved");

  assert(Array.isArray(slice.tickers) && slice.tickers.length === 20, "live slice still 20 companies");
  assert(!JSON.stringify(slice).includes("you should buy"), "slice has no advice language check token");

  console.log("intelligence_case_ui: PASS (" + checks + " assertions)");
}

try { main(); }
catch (error) {
  console.error("intelligence_case_ui: FAIL — " + error.message);
  process.exitCode = 1;
}
