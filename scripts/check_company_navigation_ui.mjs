#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const index = fs.readFileSync(path.join(ROOT, "Henneth Desk 2.CI.0", "index.html"), "utf8");
const app = fs.readFileSync(path.join(ROOT, "Henneth Desk 2.CI.0", "app.js"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "Henneth Desk 2.CI.0", "styles.css"), "utf8");
const slice = JSON.parse(fs.readFileSync(path.join(ROOT, "Henneth Desk 2.CI.0", "data", "company_intelligence.json"), "utf8"));
let checks = 0;
const assert = (condition, message) => { checks += 1; if (!condition) throw new Error(message); };
const READINESS_STATUSES = new Set([
  "blocked_model_adapter_unavailable",
  "blocked_insufficient_qualified_history",
  "blocked_unsupported_sector_model",
  "blocked_pending_owner_approved_assumptions",
  "input_ready",
]);
const BLOCKED_READINESS_STATUSES = new Set([
  "blocked_model_adapter_unavailable",
  "blocked_insufficient_qualified_history",
  "blocked_unsupported_sector_model",
]);

const PRIMARY = [
  ["overview", "Overview"],
  ["intelligence", "Intelligence"],
  ["financials", "Financials"],
  ["earnings", "Earnings"],
  ["business", "Business"],
  ["operations", "Operations"],
  ["scenarios", "Scenarios"],
  ["valuation", "Valuation"],
  ["guidance", "Guidance"],
  ["catalysts", "Catalysts"],
  ["risks", "Risks"],
  ["events", "Events"],
  ["filings", "Filings"],
  ["peers", "Peers"],
  ["ownership", "Ownership"],
  ["quant", "Quant"],
  ["research", "Research"],
];
const ADVANCED = ["snapshot", "timeline", "changes", "trends", "baseline", "forecast", "alpha_readiness", "thesis", "watchlist", "monitoring", "ask", "graph", "operating", "conditional", "causal", "coverage", "sources", "brief"];

function extractRegistry(name) {
  const match = app.match(new RegExp(`const ${name} = (\\[[\\s\\S]*?\\]);\\r?\\n`));
  assert(match, `${name} registry present`);
  return Function(`"use strict"; return (${match[1]});`)();
}

function extractFunctionBody(name, nextName) {
  const match = app.match(new RegExp(`function ${name}\\([^)]*\\) \\{([\\s\\S]*?)\\r?\\n\\}\\r?\\n\\r?\\nfunction ${nextName}`));
  assert(match, `${name} body present`);
  return match[1];
}

try {
  assert(Array.isArray(slice.tickers) && slice.tickers.length === 20, "exact 20-company slice");
  const primary = extractRegistry("PRIMARY_COMPANY_TABS");
  const advanced = extractRegistry("RESEARCH_TOOL_TABS");
  assert(JSON.stringify(primary) === JSON.stringify(PRIMARY), "exact primary tab registry/order");
  assert(JSON.stringify(advanced.map(([key]) => key)) === JSON.stringify(ADVANCED), "secondary research-tools registry");
  assert(!primary.some(([key]) => ADVANCED.includes(key)), "primary and secondary routes do not overlap");
  assert(app.includes('aria-label="Primary company sections"') && app.includes('aria-label="Research tools"'), "separate tablist aria labels");
  assert(app.includes('data-view-group="primary"') && app.includes('data-view-group="advanced"'), "view groups emitted");
  assert(app.includes('button.parentElement?.closest("[data-view-group]")'), "keyboard navigation scoped to closest tab row");
  assert(!app.includes('document.querySelectorAll("[data-view]");'), "keyboard navigation is not global across both tablists");
  for (const [key] of PRIMARY) assert(app.includes(`state.view === "${key}"`) || key === "overview", `${key}: primary route dispatch`);
  for (const key of ADVANCED) assert(app.includes(`state.view === "${key}"`), `${key}: advanced route dispatch`);
  for (const name of ["Financials", "Earnings", "Business", "Operations", "Valuation", "Events", "Peers", "Ownership", "Quant", "Research", "DomainView"]) {
    assert(app.includes(`function renderCompany${name}`), `renderCompany${name} exists`);
  }
  const peersBody = extractFunctionBody("renderCompanyPeers", "renderCompanyOwnership");
  assert(app.includes("blocked_insufficient_qualified_history") && app.includes("Forward earnings remain source-gated") && app.includes("Historical earnings bridge"), "earnings formal-gate/history split");
  assert(app.includes("Formal CI valuation") && app.includes("Legacy fair-value screen, not formal CI valuation"), "formal valuation separate from legacy fair value");
  assert(app.includes("Formal pilot-sector cohort") && app.includes("pilot-sector cohort") && app.includes("International peer registry"), "peers registry view");
  assert(peersBody.includes("r.peer_registry || {}") && peersBody.includes("registry.formal_peer_details") && peersBody.includes("registry.member_details"), "peers read emitted registry details");
  assert(!peersBody.includes("registry.sector || r.sector"), "peers do not substitute row sector for emitted registry sector");
  assert(!/state\.data\?\.tickers[\s\S]*\.filter/.test(peersBody), "peers do not filter slice rows into groups");
  assert(!/\.filter\([^)]*sector/i.test(peersBody), "peers do not filter by sector in browser");
  assert(app.includes("blocked_no_formal_peer_registry") && app.includes("unknown_no_authoritative_peer_data"), "peers missing-registry fallback");
  assert(!/state\.data\?\.tickers[\s\S]*filter/.test(peersBody), "peers do not derive same-sector rows in browser");
  assert(!/(comparable|comparability|valuation|performance|rank|ranking|similarity|multiple|benchmark)/i.test(peersBody), "peers avoid comparability/valuation/performance/rank/similarity claims");
  assert(app.includes("unknown_no_authoritative_ownership_data") && app.includes("not ownership percentages"), "ownership unknown state");
  assert(app.includes("Company Brain domain") && app.includes("renderDomainRefs") && app.includes("brainObjectMap"), "Company Brain domain references");
  assert(app.includes("data-research-route") && app.includes("querySelectorAll(\"[data-research-route]\")"), "Research hub route binding");
  assert(index.includes("iconify-icon") && index.includes("code.iconify.design") && app.includes("lucide:building-2") && app.includes("lucide:folder-open"), "utility rail and tree use external icon-library assets");
  assert(!app.includes('aria-hidden="true">CI</span>') && !app.includes('aria-hidden="true">SIG</span>') && !app.includes('aria-hidden="true">WAT</span>') && !app.includes('aria-hidden="true">RES</span>'), "utility rail does not use letter labels as visible icons");
  assert(!app.includes("icon-rail-brand"), "utility rail does not duplicate the header logo");
  assert(index.includes("Henneth <em>Company Intelligence</em>") && !index.includes("Henneth <em>Desk</em>"), "header brand is Henneth Company Intelligence");
  assert(index.includes("companyDrawerOpen") && index.includes("intelligenceDrawerOpen"), "mobile header drawer controls exist");
  assert(app.includes("mobile-left-open") && app.includes("mobile-right-open") && app.includes('event.target.closest?.("#companyDrawerOpen")'), "mobile drawer controls use stable delegated app-level state");
  assert(app.includes("closeMobileDrawers()") && app.includes("btn.onclick = () => pick(btn.dataset.symbol)") && app.includes("state.view = btn.dataset.view"), "company/tab selection closes mobile drawers");
  assert(/class="drawer-backdrop company-backdrop"[^>]*hidden/.test(app) && /class="drawer-backdrop intelligence-backdrop"[^>]*hidden/.test(app), "drawer backdrops are hidden in markup before CSS/runtime enhancement");
  assert(app.includes("function syncDrawerBackdrops") && app.includes('document.querySelectorAll(".drawer-backdrop")') && app.includes("backdrop.hidden =") && app.includes('event.target.closest?.("[data-drawer-close]")'), "drawer backdrop visibility is controlled by the app state and outside action closes drawers");
  assert(css.includes("scrollbar-color:transparent transparent") && css.includes(".detail:hover") && css.includes(".tree-panel:focus-within") && css.includes(".list:focus-within"), "panel scrollbars are hidden until hover or focus");
  assert(css.includes(".workspace.mobile-left-open .rail") && css.includes(".workspace.mobile-right-open .tree-panel") && css.includes(".drawer-backdrop"), "mobile drawers are app-state controlled");
  assert(css.includes(".drawer-backdrop{display:none}") && css.includes(".drawer-backdrop[hidden]{display:none!important}"), "mobile drawer backdrops do not consume desktop workspace grid cells");
  assert(!css.includes(".workspace[data-company-bg]>*{position:relative;z-index:1}"), "company background layering does not override every direct workspace child");
  assert(css.includes("@media (min-width:901px){.workspace[data-company-bg]>.icon-rail") && css.includes("@media (max-width:900px){.workspace[data-company-bg]>.detail{position:relative;z-index:1}"), "company background layering preserves fixed mobile drawers");
  assert(css.includes(".viewnav-shell") && css.includes(".research-tools") && css.includes(".company-domain-shell") && css.includes(".blocked-shell") && css.includes(".research-hub-grid"), "navigation/domain CSS");
  for (const row of slice.tickers) {
    assert(row.symbol && row.company_brain?.domains, `${row.symbol || "unknown"}: Company Brain available`);
    assert(row.company_brain.domains.forecasts?.status === "blocked", `${row.symbol}: forecasts blocked`);
    assert(row.company_brain.domains.valuation?.status === "blocked", `${row.symbol}: valuation blocked`);
    if (row.forecast_readiness?.status === "input_ready") {
      assert(row.forecast_readiness?.qualified_period_count >= 3, `${row.symbol}: forecast readiness input-ready`);
    } else {
      assert(BLOCKED_READINESS_STATUSES.has(row.forecast_readiness?.status), `${row.symbol}: forecast readiness blocked`);
      if ((row.forecast_readiness?.qualified_period_count || 0) >= 3) {
        assert(row.forecast_readiness?.status === "blocked_model_adapter_unavailable", `${row.symbol}: qualified history blocked by adapter availability`);
      }
    }
    for (const [key, value] of Object.entries(row.forecast_readiness?.downstream_status || {})) {
      assert(READINESS_STATUSES.has(value), `${row.symbol}: ${key} readiness status`);
    }
    assert(row.scenario_lab?.status?.valuation === "ready_scenario_multiple_only", `${row.symbol}: scenario multiple status separate`);
    assert(row.peer_registry?.method === "pilot_official_sector_cohort_v1", `${row.symbol}: formal peer registry emitted`);
    assert(row.peer_registry?.peer_set_kind === "pilot_sector_cohort", `${row.symbol}: peer registry kind`);
    assert(Array.isArray(row.peer_registry?.formal_peers), `${row.symbol}: formal peers list`);
    assert(row.peer_registry?.international_peers?.status === "unavailable", `${row.symbol}: international peers unavailable`);
    for (const domain of ["guidance", "catalysts", "risks"]) assert(row.company_brain.domains[domain], `${row.symbol}: ${domain} domain exists`);
  }
  console.log(`company_navigation_ui: PASS (${checks} assertions, 20 company rows)`);
} catch (error) {
  console.error(`company_navigation_ui: FAIL — ${error.message}`);
  process.exitCode = 1;
}
