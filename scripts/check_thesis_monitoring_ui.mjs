#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const APP_PATH = path.join(ROOT, "Henneth Desk 2.CI.0", "app.js");
const CSS_PATH = path.join(ROOT, "Henneth Desk 2.CI.0", "styles.css");
const CONTRACT_PATH = path.join(ROOT, "Henneth Desk 2.CI.0", "api", "ask_contract.js");
const SLICE_PATH = path.join(ROOT, "Henneth Desk 2.CI.0", "data", "company_intelligence.json");

const app = fs.readFileSync(APP_PATH, "utf8");
const css = fs.readFileSync(CSS_PATH, "utf8");
const contract = fs.readFileSync(CONTRACT_PATH, "utf8");
const slice = JSON.parse(fs.readFileSync(SLICE_PATH, "utf8"));
let checks = 0;

function assert(condition, message) {
  checks += 1;
  if (!condition) throw new Error(message);
}

function main() {
  const rows = Array.isArray(slice.tickers) ? slice.tickers : [];
  const thesisProjection = /function projectThesisMonitoring\(row\) \{([\s\S]*?)\r?\n\}\r?\n\r?\nfunction projectConfidenceComponents/.exec(contract)?.[1] || "";
  assert(rows.length === 20, "CI slice must contain exact 20 rows");
  assert(new Set(rows.map((row) => row?.symbol)).size === 20, "CI slice symbols must be unique");
  assert(app.includes('["thesis", `Thesis monitor ${r.thesis_monitoring?.active_thesis_count || 0}`]'), "Thesis monitor tab is registered");
  assert(app.includes('state.view === "thesis" ? renderThesisMonitor(r)'), "Thesis monitor route is wired");
  assert(/function renderThesisMonitor\(r\)[\s\S]*?monitor\.status/.test(app), "Thesis monitor reads backend status");
  assert(!/function renderThesisMonitor\(r\)[\s\S]*?assessment\s*===/.test(app), "UI does not infer company status from assessment");
  assert(app.includes("Strengthening") && app.includes("Stable") && app.includes("Weakening") && app.includes("Broken"), "canonical status labels are explicit");
  assert(app.includes("No active thesis is being monitored"), "no-active state is explicit");
  assert(app.includes("source_cluster_id"), "source cluster is rendered");
  assert(app.includes("Inference label"), "inference label is rendered");
  assert(app.includes("Confidence band"), "confidence band is rendered");
  assert(app.includes("monitored_assertion"), "monitored assertion is rendered");
  assert(app.includes("renderThesisChecks(\"Prove checks\""), "prove checks are rendered");
  assert(app.includes("renderThesisChecks(\"Kill checks\""), "kill checks are rendered");
  assert(app.includes("renderThesisWatch(thesis.watch_items)"), "watch items are rendered");
  assert(/function renderThesisEvidence[\s\S]*?safeHref\(item\?\.source_url\)/.test(app), "evidence links use safeHref");
  assert(css.includes(".thesis-shell") && css.includes(".thesis-card") && css.includes(".thesis-evidence"), "Thesis monitor styles exist");
  assert(/@media \(max-width:900px\)[\s\S]*?\.thesis-status/.test(css), "Thesis monitor has mobile layout");
  assert(thesisProjection.includes("slice(0, 4)"), "Ask thesis projection caps at four theses");
  assert(!/(?:\bevidence\b|source_url|excerpt)/.test(thesisProjection), "Ask thesis projection does not expose evidence, URLs, or excerpts");
  console.log(`thesis_monitoring_ui: PASS (${checks} UI/contract assertions, ${rows.length} company rows)`);
}

try { main(); } catch (error) {
  console.error(`thesis_monitoring_ui: FAIL - ${error.message}`);
  process.exitCode = 1;
}
