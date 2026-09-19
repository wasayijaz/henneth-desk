#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const APP_PATH = path.join(ROOT, "Henneth Desk 2.CI.0", "app.js");
const SLICE_PATH = path.join(ROOT, "Henneth Desk 2.CI.0", "data", "company_intelligence.json");

const app = fs.readFileSync(APP_PATH, "utf8");
const slice = JSON.parse(fs.readFileSync(SLICE_PATH, "utf8"));
let checks = 0;

function assert(condition, message) {
  checks += 1;
  if (!condition) throw new Error(message);
}

function main() {
  const rows = Array.isArray(slice.tickers) ? slice.tickers : [];
  assert(rows.length === 20 && new Set(rows.map(row => row?.symbol)).size === 20, "CI slice must contain exactly 20 unique pilot companies");
  assert(app.includes('renderGuidanceDomainView(r, "guidance"'), "Guidance route uses backend guidance renderer");
  assert(app.includes('renderGuidanceDomainView(r, "risks"'), "Risks route uses backend guidance renderer");
  assert(app.includes("function renderGuidanceDomainView"), "Guidance domain renderer exists");
  const block = app.slice(app.indexOf("function guidanceState"), app.indexOf("function renderCompanyOperations"));
  assert(block.includes("r.guidance_contradictions"), "renderer reads row.guidance_contradictions");
  assert(block.includes("The browser will not derive guidance, risks, contradictions, forecasts, valuation, or advice"), "missing-state copy forbids browser derivation");
  assert(block.includes("only displays emitted assertion objects and exact-key contradiction rows"), "generated-state copy stays display-only");
  assert(block.includes("state.contradiction_count"), "renderer displays backend contradiction count");
  assert(block.includes("row.match_rule"), "renderer displays backend match rule");
  assert(!/assertion_key\s*===|conflict_key\s*===|INCOMPATIBLE|match\(|reduce\(/.test(block), "renderer must not browser-match assertions or contradictions");
  for (const row of rows) {
    const state = row?.guidance_contradictions;
    assert(state && typeof state === "object" && !Array.isArray(state), `${row?.symbol} guidance_contradictions must be an object`);
    assert(["available", "no_guidance_objects"].includes(state.status), `${row?.symbol} invalid guidance status`);
    assert(Array.isArray(state.objects), `${row?.symbol} objects must be an array`);
    assert(Array.isArray(state.contradictions), `${row?.symbol} contradictions must be an array`);
    for (const obj of state.objects) {
      assert(["guidance", "risks"].includes(obj.domain), `${row.symbol} invalid guidance domain`);
      assert(obj.assertion_key && obj.conflict_key, `${row.symbol} missing normalized keys`);
      assert(obj.evidence?.source_url && obj.evidence?.document_id && obj.evidence?.page && obj.evidence?.available_on, `${row.symbol} missing provenance`);
    }
  }
  console.log(`guidance_contradictions_ui: PASS (${checks} UI assertions, ${rows.length} company rows)`);
}

try { main(); } catch (error) {
  console.error(`guidance_contradictions_ui: FAIL - ${error.message}`);
  process.exitCode = 1;
}
