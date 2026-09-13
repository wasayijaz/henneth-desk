import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const ciRoot = path.join(root, "Henneth Desk 2.CI.0");
const index = fs.readFileSync(path.join(ciRoot, "index.html"), "utf8");
const app = fs.readFileSync(path.join(ciRoot, "app.js"), "utf8");
const css = fs.readFileSync(path.join(ciRoot, "styles.css"), "utf8");

for (const [name, source] of [["index", index], ["app", app], ["styles", css]]) {
  assert(!source.includes("product-background-"), `${name}: product background reference remains`);
  assert(!source.includes("login-background.webp"), `${name}: login background reference remains`);
  assert(!source.includes("data-company-bg"), `${name}: company background state remains`);
}
assert(!index.includes("company_backgrounds.js"), "obsolete company background registry is still loaded");
assert(index.includes('class="brand-mark"') && app.includes("companyLogoUrl") && app.includes("data-company-logo"), "useful brand and company logos must remain");
assert(app.includes("enhanceMotion({ animate:"), "lightweight content entrance motion must remain");

console.log("ci_no_background_images: PASS (no decorative background requests; logos and content motion retained)");
