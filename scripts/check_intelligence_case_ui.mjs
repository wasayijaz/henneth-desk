#!/usr/bin/env node
import fs from "node:fs";
import crypto from "node:crypto";
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
const FIXTURE = path.join(ROOT, "scripts", "fixtures", "intelligence_case_ui.json");
const MLCF_CASE_ID = "case_mlcf_pioc_control_observed_v1";
const MARI_CASE_ID = "case_mari_working_interest_observed_v1";
const RETIRED_MARI_CASE_IDS = Object.freeze(["case_mari_offshore_exploration_blocks_observed_v1"]);

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

function fileSnapshot(filePath) {
  if (!fs.existsSync(filePath)) return { exists: false, sha256: null };
  return {
    exists: true,
    sha256: crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex"),
  };
}

function buildFixture() {
  const fixture = {
    observed_mlcf: {
      symbol: "MLCF",
      status: "observed_seed_available",
      cases: [{
        case_id: MLCF_CASE_ID,
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
        case_id: MARI_CASE_ID,
        symbol: "MARI",
        case_family: "e_and_p",
        case_type: "working_interest_acquisition",
        status: "Observed",
        epistemic_type: "reported_fact",
        summary: "Observed official-source seed: Mari Energies reported a working-interest acquisition.",
        observed_facts: [{
          fact_id: "mari_working_interest_acquisition",
          statement: "Mari Energies reported a working-interest acquisition.",
          reported_values: [{ label: "interest_type", value: "working interest" }],
          evidence: [{ document_id: "psx:260446", page: 1, source_url: "https://dps.psx.com.pk/download/document/260446.pdf", text: "working interest" }],
        }],
        alternative_readings: [{
          alternative_id: "working_interest_not_proved_reserves",
          reading: "Working-interest acquisition does not establish reserves or future production.",
          status: "retained_as_observed_only",
          rejection_condition: "Reject promotion if no official source qualifies the acquired interest or development path.",
        }],
        promotion_blocks: {
          Corroborated: "Blocked: single official Mari/PSX source.",
          Modelled: "Blocked: no source-qualified working interest or financial-model inputs are attached.",
          Published: "Blocked: no forecast, valuation, reverse-expectations output, investor conclusion or release gate is complete.",
        },
        policy: { observed_only: true, no_forecast: true, no_valuation: true, no_market_expectations: true, no_recommendation: true },
        source_lineage: [{ document_id: "psx:260446", page: 1, source_url: "https://dps.psx.com.pk/download/document/260446.pdf" }],
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
  const beforeSlice = fileSnapshot(SLICE);
  const beforeFixture = fileSnapshot(FIXTURE);
  const app = fs.readFileSync(APP, "utf8");
  const view = fs.readFileSync(VIEW, "utf8");
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
  assert(RETIRED_MARI_CASE_IDS.length === 1 && checker.includes(RETIRED_MARI_CASE_IDS[0]), "retired MARI case id remains an explicit checker-only rejection list");
  assert(!view.includes(RETIRED_MARI_CASE_IDS[0]), "production helper does not hard-code retired MARI case ids");

  const parsed = api.parsePath("/company/mlcf/intelligence/" + MLCF_CASE_ID);
  assert(parsed.ticker === "MLCF" && parsed.caseId === MLCF_CASE_ID, "path parse");
  assert(api.parsePath("/company/MLCF") === null, "non-case path ignored");

  const missing = api.findCase({ symbol: "MLCF" }, MLCF_CASE_ID, "MLCF");
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

  const currentMariRow = { symbol: "MARI", intelligence_cases: fixture.observed_mari };
  const currentMari = api.findCase(currentMariRow, MARI_CASE_ID, "MARI");
  const retiredMariLookups = RETIRED_MARI_CASE_IDS.map(caseId => api.findCase(currentMariRow, caseId, "MARI"));
  const currentMariDiscovery = api.discoverableCases(currentMariRow);
  assert(currentMari.ok && currentMari.case.case_id === MARI_CASE_ID, "current MARI working-interest route accepted");
  assert(retiredMariLookups.every(lookup => lookup.ok === false && lookup.reason === "case_not_found"), "retired MARI offshore route fails closed with no alias");
  assert(currentMariDiscovery.status === "available" && currentMariDiscovery.items.length === 1, "current MARI discovery emits one case");
  assert(currentMariDiscovery.items[0].href === "/company/MARI/intelligence/" + MARI_CASE_ID, "current MARI discovery emits only working-interest href");
  assert(!currentMariDiscovery.items.some(item => RETIRED_MARI_CASE_IDS.includes(item.case_id) || RETIRED_MARI_CASE_IDS.some(caseId => item.href.endsWith(caseId))), "retired MARI offshore case is not discoverable");

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

  assert(typeof api.discoverableCases === "function", "discoverableCases exported");
  assert(api.caseHref("MLCF", MLCF_CASE_ID) === "/company/MLCF/intelligence/" + MLCF_CASE_ID, "safe case href");
  assert(api.caseHref("MLCF", "javascript:alert(1)") === "", "unsafe case id rejected");
  assert(api.discoverableCases({ symbol: "OGDC" }).status === "absent", "absent projection emits no items");
  assert(api.discoverableCases({ symbol: "OGDC", intelligence_cases: { symbol: "OGDC", status: "no_observed_case", cases: [] } }).status === "empty", "empty projection emits no items");
  assert(api.discoverableCases({ symbol: "OGDC", intelligence_cases: "bad" }).reason === "intelligence_cases_state_missing", "invalid projection fail-closed");
  const discoveryPayloadMismatch = api.discoverableCases({ symbol: "MLCF", intelligence_cases: { ...fixture.observed_mlcf, symbol: "MARI" } });
  assert(discoveryPayloadMismatch.status === "invalid" && discoveryPayloadMismatch.reason === "payload_symbol_mismatch" && discoveryPayloadMismatch.items.length === 0, "discovery payload mismatch emits no links");
  const discoveryCrossIssuer = structuredClone(fixture.observed_mlcf);
  discoveryCrossIssuer.cases[0].symbol = "MARI";
  const crossIssuerDiscovery = api.discoverableCases({ symbol: "MLCF", intelligence_cases: discoveryCrossIssuer });
  assert(crossIssuerDiscovery.status === "invalid" && crossIssuerDiscovery.reason === "case_symbol_mismatch" && crossIssuerDiscovery.items.length === 0, "discovery cross-issuer case emits no links");
  const discoveryDuplicates = structuredClone(fixture.observed_mlcf);
  discoveryDuplicates.cases.push(structuredClone(discoveryDuplicates.cases[0]));
  const duplicateDiscovery = api.discoverableCases({ symbol: "MLCF", intelligence_cases: discoveryDuplicates });
  assert(duplicateDiscovery.status === "invalid" && duplicateDiscovery.reason === "duplicate_case_id" && duplicateDiscovery.items.length === 0, "discovery duplicate case id emits no links");
  const discoveryBadLifecycle = structuredClone(fixture.observed_mlcf);
  discoveryBadLifecycle.cases[0].status = "Draft";
  const lifecycleDiscovery = api.discoverableCases({ symbol: "MLCF", intelligence_cases: discoveryBadLifecycle });
  assert(lifecycleDiscovery.status === "invalid" && lifecycleDiscovery.reason === "case_lifecycle_invalid" && lifecycleDiscovery.items.length === 0, "discovery invalid lifecycle emits no links");
  const discoveryBadSections = structuredClone(fixture.observed_mlcf);
  discoveryBadSections.cases[0].sections = "bad";
  const sectionsDiscovery = api.discoverableCases({ symbol: "MLCF", intelligence_cases: discoveryBadSections });
  assert(sectionsDiscovery.status === "invalid" && sectionsDiscovery.reason === "sections_shape_invalid" && sectionsDiscovery.items.length === 0, "discovery invalid sections emits no links");
  const discoveryBadSourceSection = structuredClone(fixture.observed_mlcf);
  discoveryBadSourceSection.cases[0].sections = { sources: "bad" };
  const sourceSectionDiscovery = api.discoverableCases({ symbol: "MLCF", intelligence_cases: discoveryBadSourceSection });
  assert(sourceSectionDiscovery.status === "invalid" && sourceSectionDiscovery.reason === "section_shape_invalid" && sourceSectionDiscovery.items.length === 0, "discovery invalid source section emits no links");
  const discoveredMlcf = api.discoverableCases({ symbol: "MLCF", intelligence_cases: fixture.observed_mlcf });
  const discoveredMari = api.discoverableCases({ symbol: "MARI", intelligence_cases: fixture.observed_mari });
  assert(discoveredMlcf.status === "available" && discoveredMlcf.items[0].href === "/company/MLCF/intelligence/" + MLCF_CASE_ID, "MLCF discovery href");
  assert(discoveredMari.status === "available" && discoveredMari.items[0].href === "/company/MARI/intelligence/" + MARI_CASE_ID, "MARI discovery href");
  const intelStart = app.indexOf("function renderIntelligenceCaseIndex(");
  const intelEnd = app.indexOf("function renderIntelligence(r)");
  assert(intelStart >= 0 && intelEnd > intelStart, "case index renderer present");
  const intelBlock = app.slice(intelStart, intelEnd);
  assert(app.includes("renderIntelligenceCaseIndex(r)"), "intelligence tab mounts case index");
  assert(intelBlock.includes("esc(item.title)") && intelBlock.includes("esc(item.summary") && intelBlock.includes("esc(item.status)") && intelBlock.includes("esc(href)"), "discovery values escaped");
  assert(intelBlock.includes("not a forecast or valuation") || intelBlock.includes("not treated as forecasts or valuations"), "blocked fields not framed as forecast/valuation");
  assert(css.includes(".case-index-link") && css.includes("@media (max-width:900px){.case-index .intel-grid{grid-template-columns:1fr}}"), "mobile case-index stack present");
  const liveBySymbol = Object.fromEntries((slice.tickers || []).map(row => [row.symbol, row]));
  const liveMlcf = api.discoverableCases(liveBySymbol.MLCF);
  const liveMari = api.discoverableCases(liveBySymbol.MARI);
  const liveOgdc = api.discoverableCases(liveBySymbol.OGDC);
  assert(liveMlcf.status === "available" && liveMlcf.items.some(item => item.href === "/company/MLCF/intelligence/" + MLCF_CASE_ID), "live MLCF case link projected");
  assert(liveMari.status === "available" && liveMari.items.length === 1 && liveMari.items[0].href === "/company/MARI/intelligence/" + MARI_CASE_ID, "live MARI working-interest case link projected");
  assert(api.findCase(liveBySymbol.MARI, MARI_CASE_ID, "MARI").ok, "live MARI working-interest route accepted");
  assert(api.findCase(liveBySymbol.MARI, RETIRED_MARI_CASE_IDS[0], "MARI").reason === "case_not_found", "live retired MARI offshore route fails closed");
  assert(!liveMari.items.some(item => RETIRED_MARI_CASE_IDS.includes(item.case_id)), "live retired MARI offshore case is not discoverable");
  assert(liveOgdc.status === "empty" || liveOgdc.status === "absent", "non-case company emits no discovery link");
  assert(Array.isArray(slice.tickers) && slice.tickers.length === 20, "live slice still 20 companies");
  assert(!JSON.stringify(slice).includes("you should buy"), "slice has no advice language check token");
  const afterSlice = fileSnapshot(SLICE);
  const afterFixture = fileSnapshot(FIXTURE);
  assert(beforeSlice.exists === afterSlice.exists && beforeSlice.sha256 === afterSlice.sha256, "checker leaves served slice hash unchanged");
  assert(beforeFixture.exists === afterFixture.exists && beforeFixture.sha256 === afterFixture.sha256, "checker leaves fixture hash unchanged");

  console.log("intelligence_case_ui: PASS (" + checks + " assertions)");
}

try { main(); }
catch (error) {
  console.error("intelligence_case_ui: FAIL — " + error.message);
  process.exitCode = 1;
}
