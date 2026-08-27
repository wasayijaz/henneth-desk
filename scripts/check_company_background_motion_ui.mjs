#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const ciRoot = path.join(ROOT, "Henneth Desk 2.CI.0");
const app = fs.readFileSync(path.join(ciRoot, "app.js"), "utf8");
const index = fs.readFileSync(path.join(ciRoot, "index.html"), "utf8");
const css = fs.readFileSync(path.join(ciRoot, "styles.css"), "utf8");
const registrySource = fs.readFileSync(path.join(ciRoot, "company_backgrounds.js"), "utf8");
const registryContext = vm.createContext({});
vm.runInContext(registrySource, registryContext, { filename: "company_backgrounds.js" });
const registry = registryContext.HENNETH_COMPANY_BACKGROUNDS;
let checks = 0;
const assert = (condition, message) => { checks += 1; if (!condition) throw new Error(message); };

try {
  assert(index.includes('<script src="company_backgrounds.js"></script>') && index.indexOf("company_backgrounds.js") < index.indexOf("app.js"), "background registry loads before app.js");
  assert(index.includes('<body class="gate-open">') && css.includes('body.gate-open{background:#172a35 url("login-background.webp")') && css.includes("body.gate-open .workspace{background:transparent}") && !css.includes("body:has(.gate)"), "login background uses an explicit first-paint gate class");
  assert(fs.statSync(path.join(ciRoot, "login-background.webp")).size > 0, "login background asset exists");
  assert(app.includes('document.body.classList.add("gate-open")') && app.includes('document.body.classList.remove("gate-open")'), "app toggles login background state explicitly");
  assert(app.includes("window.HENNETH_COMPANY_BACKGROUNDS") && app.includes("typeof registry.forSymbol === \"function\""), "app consumes registry global when supplied");
  assert(app.includes("CI_REVEAL_SIDES") && app.includes('"left"') && app.includes('"right"') && app.includes('"top"') && app.includes('"bottom"'), "all four reveal sides available");
  assert(app.includes("function randomRevealSide") && app.includes("crypto?.getRandomValues") && app.includes("new Uint32Array(1)") && app.includes("ciHash(fallbackSeed)") && !app.includes("Math.random"), "reveal side is securely randomized with a stable fallback");
  assert(app.includes("function companyVisual") && app.includes("registry?.forSymbol(symbol)") && app.includes("product-background-(\\d{2})"), "company visual resolver reads background IDs from registry paths");
  assert(app.includes("CI_BACKGROUND_ASSET_COUNT = 25") && app.includes("fallbackIndex") && app.includes("% assetCount") && app.includes('padStart(2, "0")'), "fallback covers the 25 background assets");
  assert(app.includes("safeBackgroundCssUrl") && app.includes("app.style.setProperty(\"--ci-company-bg\", cssUrl)") && app.includes("product-background-\\d{2}\\.(?:png|webp)"), "registry path is written to the CSS background variable safely");
  assert(app.includes("const activeIndex = row ? Math.max") && app.includes("companyVisual(row, activeIndex)"), "active company row drives the visual contract");
  assert(app.includes("app.dataset.companyBg = visual.backgroundId") && app.includes("app.dataset.revealSide = visual.revealSide"), "app writes CSS data attributes");
  assert(app.includes("app.dataset.companyBackgroundSrc = visual.backgroundPath") && app.includes("delete app.dataset.companyBg"), "app exposes and clears background source metadata");
  assert(app.includes("function renderGate(message)") && app.includes("delete app.dataset.revealSide") && app.includes("delete app.dataset.companyBackgroundSrc"), "the signed-out gate clears an earlier company texture");
  assert(app.includes("enhanceMotion({ visual, animate: !searchState })"), "search/focus rerenders skip replaying the transition");
  assert(app.includes('window.matchMedia("(prefers-reduced-motion: reduce)").matches'), "reduced-motion users do not get the replayed transition");
  assert(app.includes('app.classList.remove("is-entering")') && app.includes('app.classList.add("is-entering")'), "render lifecycle retriggers one-shot processing transition");
  assert(css.includes(".workspace[data-company-bg]") && css.includes("background-image:var(--ci-company-bg)") && css.includes('[data-reveal-side="left"]') && css.includes('[data-reveal-side="right"]') && css.includes('[data-reveal-side="top"]') && css.includes('[data-reveal-side="bottom"]'), "stylesheet consumes the app-side attributes and runtime background variable");
  assert(registry?.assetCount === 25 && Object.keys(registry.pilot || {}).length === 20 && (registry.reserved || []).length === 5, "registry covers 20 pilot plus five reserved assets");
  for (let i = 1; i <= 25; i += 1) {
    const id = String(i).padStart(2, "0");
    const expected = `product-background-${id}.webp`;
    assert(Object.values(registry.pilot || {}).includes(expected) || (registry.reserved || []).includes(expected), `background ${id} is registry-covered`);
  }
  console.log(`company_background_motion_ui: PASS (${checks} assertions)`);
} catch (error) {
  console.error(`company_background_motion_ui: FAIL - ${error.message}`);
  process.exitCode = 1;
}
