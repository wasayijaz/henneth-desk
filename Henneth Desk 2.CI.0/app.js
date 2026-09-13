const SB_URL = "https://qteoncckohuoatbjjykb.supabase.co";
const SB_KEY = "sb_publishable_aQu8P4yrAY7l8Y0AcLth5g_Z3VceUnw";
const SESSION_KEY = "henneth-ci-session";

const $ = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));
// New intelligence views only link to explicit web sources. State is private input,
// so reject non-http(s) schemes before the existing esc() helper touches markup.
const safeHref = value => {
  const text = String(value ?? "").trim();
  return /^https?:\/\//i.test(text) ? esc(text) : "";
};
const fmt = (value, digits = 2) => value == null ? "unknown" : Number(value).toLocaleString("en", { maximumFractionDigits: digits });
const pct = value => value == null ? "unknown" : `${value > 0 ? "+" : ""}${fmt(value, 1)}%`;
const short = (value, limit = 80) => {
  const text = String(value ?? "");
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
};
const COMPANY_LOGO_DOMAINS = Object.freeze({
  MLCF: "kmlg.com", OGDC: "ogdcl.com", PPL: "ppl.com.pk", DGKC: "dgcement.com",
  PSO: "psopk.com", UBL: "ubldigital.com", FFC: "ffc.com.pk", LUCK: "lucky-cement.com",
  HUBC: "hubpower.com", PRL: "prl.com.pk", BOP: "bop.com.pk", NBP: "nbp.com.pk",
  MEBL: "meezanbank.com", ATRL: "arl.com.pk", HBL: "hbl.com", MARI: "marienergies.com.pk",
  ENGROH: "engro.com", GAL: "ghandharaautomobiles.com.pk", NRL: "nrlpak.com", CNERGY: "cnergyico.com",
});
const companyLogoUrl = symbol => {
  const domain = COMPANY_LOGO_DOMAINS[String(symbol || "").toUpperCase()];
  return domain ? `https://www.google.com/s2/favicons?domain_url=https%3A%2F%2F${encodeURIComponent(domain)}&sz=128` : "";
};
const companyBusinessSummary = value => {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return "No sourced business description is retained yet.";
  const sentences = text.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [text];
  const useful = sentences.find(sentence => /engaged in|principal activit|operates|provides|manufactur|production and sale|business of/i.test(sentence));
  return short((useful || sentences[0]).trim(), 170);
};
const humanActivityLabel = value => {
  const label = String(value || "").trim();
  if (!label) return "Retained company activity";
  if (/^https?:|^\//i.test(label)) return "Issuer web page retained";
  if (/^download pdf$/i.test(label)) return "Official PDF retained";
  if (/\btype=/.test(label)) {
    const type = label.match(/\btype=([^;]+)/i)?.[1]?.replaceAll("_", " ");
    const target = label.match(/\btarget=([^;]+)/i)?.[1]?.replaceAll("_", " ");
    return [target, type].filter(Boolean).join(" · ") || "Classified company event";
  }
  return label.replaceAll("_", " ");
};
const ciHumanStatus = value => {
  const status = String(value || "unknown");
  if (/financial_truth_not_qualified/i.test(status)) return "Waiting for complete reported financial history";
  if (/not_qualified/i.test(status)) return "Reported history has not passed qualification yet";
  if (/owner_approved_assumptions/i.test(status)) return "Waiting for reviewed model assumptions";
  if (/insufficient_qualified_history/i.test(status)) return "Not enough verified history to calculate this yet";
  if (/adapter_unavailable/i.test(status)) return "The sector calculation method is not connected yet";
  if (/not_generated|not_emitted|not_activated|unavailable|unknown/i.test(status)) return "Not available from retained evidence yet";
  if (/blocked/i.test(status)) return "Held back because a required input is missing";
  if (/computed|qualified|available|ready/i.test(status)) return "Available from qualified retained evidence";
  return status.replaceAll("_", " ");
};
const ciChart = (type, payload, label = "") => {
  const safe = encodeURIComponent(JSON.stringify(payload || {}));
  const itemSummary = Array.isArray(payload?.items) ? payload.items.slice(0, 8).map(item => [item?.date, item?.label, item?.value, item?.unit].filter(value => value != null && value !== "").join(" ")).filter(Boolean).join("; ") : "";
  const seriesSummary = Array.isArray(payload?.base) ? `Base series: ${payload.base.join(", ")}` : "";
  const summary = [label || payload?.label, payload?.reason, itemSummary, seriesSummary].filter(Boolean).join(". ");
  const readable = payload?.visible_summary && Array.isArray(payload?.items) ? `<div class="ci-chart-readable-summary" aria-label="Chart values">${payload.items.slice(0, 6).map(item => `<span><b>${esc(item?.label || item?.date || "Item")}</b><small>${esc([item?.value, item?.unit].filter(value => value != null && value !== "").join(" ") || item?.date || "Retained")}</small></span>`).join("")}</div>` : "";
  return `<div class="ci-chart" data-ci-chart="${esc(type)}" data-ci-chart-payload="${esc(safe)}"${label ? ` aria-label="${esc(label)}"` : ""}></div>${readable}${summary ? `<span class="sr-only">${esc(summary)}</span>` : ""}`;
};
const ciBlockedChart = (status, label, requirements = [], available = 0) => ciChart("blocked", {
  status: status || "blocked", reason: ciHumanStatus(status), label, requirements, available,
}, label);

function ciFindSeries(value, preferred = [], depth = 0) {
  if (depth > 6 || value == null) return null;
  if (Array.isArray(value)) {
    if (value.length === 8 && value.every(item => Number.isFinite(Number(item)))) return value.map(Number);
    if (value.length === 8 && value.every(item => item && typeof item === "object")) {
      for (const field of preferred) {
        const series = value.map(item => Number(item[field]));
        if (series.every(Number.isFinite)) return series;
      }
    }
    for (const item of value) {
      const found = ciFindSeries(item, preferred, depth + 1);
      if (found) return found;
    }
    return null;
  }
  if (typeof value === "object") {
    for (const field of preferred) {
      if (field in value) {
        const found = ciFindSeries(value[field], preferred, depth + 1);
        if (found) return found;
      }
    }
    for (const item of Object.values(value)) {
      const found = ciFindSeries(item, preferred, depth + 1);
      if (found) return found;
    }
  }
  return null;
}

function ciForecastChartPayload(r) {
  const engine = r.financial_forecasts || {};
  const result = engine.result;
  const requirements = engine.missing_requirements || ["Qualified financial history", "Approved assumptions", "Eight-quarter output"];
  if (!result || String(engine.status || "").startsWith("blocked")) return { status: engine.status, reason: ciHumanStatus(engine.status), label: "Eight-quarter trajectory is held back", requirements, available: 0 };
  const scenario = name => ciFindSeries(result?.scenarios?.[name] || result?.[name], ["eps_pkr", "eps", "pat_pkr", "revenue_pkr", "revenue"]);
  const base = scenario("base") || ciFindSeries(result, ["eps_pkr", "eps", "pat_pkr", "revenue_pkr", "revenue"]);
  const bear = scenario("bear"), bull = scenario("bull");
  if (!base || !bear || !bull) return { status: "blocked_scenario_series_not_emitted", reason: "Bear, base, and bull quarterly series were not emitted together", label: "Eight-quarter trajectory is held back", requirements: ["Bear series", "Base series", "Bull series"], available: [bear, base, bull].filter(Boolean).length };
  return { status: "computed", bear, base, bull, unit: result.unit || "model output", label: "Eight-quarter forecast trajectory" };
}

function ciExpectationPayload(r) {
  const market = Number(r.price?.current);
  const valuation = r.formal_valuations || {};
  const result = valuation.result || {};
  const base = Number(result.fair_value_per_share ?? result.fair_value_pkr_per_share ?? result.equity_value_per_share);
  if (!Number.isFinite(market) || !Number.isFinite(base) || String(valuation.status || "").startsWith("blocked")) return { status: valuation.status || "blocked_valuation_not_available", reason: ciHumanStatus(valuation.status), label: "Market expectations cannot be compared yet", requirements: ["Current retained price", "Qualified fair value", "Comparable per-share unit"], available: Number.isFinite(market) ? 1 : 0 };
  return { status: "computed", market, base, unit: "PKR/share", label: "Current price requires more than the base case" };
}
const CI_REVEAL_SIDES = Object.freeze(["left", "right", "top", "bottom"]);
const CI_BACKGROUND_ATTR_RE = /product-background-(\d{2})\.(?:png|webp)$/;
const CI_BACKGROUND_ASSET_COUNT = 25;
const CI_MOBILE_QUERY = "(max-width:900px)";
const CI_LEFT_MIN = 220;
const CI_LEFT_MAX = 360;
const CI_RIGHT_MIN = 248;
const CI_RIGHT_MAX = 420;
const RAIL_LINKS = [
  { href: "#companyDirectory", label: "Company directory", icon: "lucide:building-2", active: true },
  { href: "#companyIntelligenceTree", label: "Intelligence cases", icon: "lucide:layers-3" },
  { href: "#companyDetail", label: "Scenario Lab", icon: "lucide:sliders-horizontal" },
  { href: "#companyDetail", label: "Ask Henneth", icon: "lucide:message-circle-question" },
];

const ASK_MAX_QUESTION_BYTES = 4096;
const THESIS_STATUSES = ["Strengthening", "Stable", "Weakening", "Broken"];
const THESIS_COLUMNS = "id,symbol,thesis,expected_earnings_path,catalysts,risks,required_evidence,kill_conditions,user_fair_value_assumption,user_fair_value_basis,status,archived,created_at,updated_at";
const THESIS_LIMITS = { thesis: 5000, expected: 2000, basis: 1000, fairValueMax: 1000000, listItems: 50, listItem: 500 };
const PRIMARY_COMPANY_TABS = [
  ["overview", "Overview"],
  ["intelligence", "Intelligence"],
  ["financials", "Financials"],
  ["earnings", "Earnings"],
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
];
const RESEARCH_TOOL_TABS = [
  ["snapshot", "Investor snapshot"],
  ["timeline", "Typed timeline"],
  ["changes", "Change digest"],
  ["trends", "Financial trends"],
  ["baseline", "Financial baseline"],
  ["forecast", "Forecast readiness"],
  ["alpha_readiness", "Event-to-Value readiness"],
  ["thesis", "Thesis monitor"],
  ["watchlist", "Evidence watchlist"],
  ["monitoring", "CI monitoring"],
  ["ask", "Ask Henneth"],
  ["graph", "Knowledge graph"],
  ["operating", "Operating intelligence"],
  ["past_context", "Past Context"],
  ["conditional", "Conditional benchmarks"],
  ["causal", "Causal map"],
  ["coverage", "Coverage"],
  ["sources", "Sources"],
  ["brief", "Brief queue"],
];
// Six directory groups mirror the selected visual reference. Every existing route
// appears exactly once in this tree; grouping is presentation-only.
const TREE_GROUPS = [
  { key: "overview", label: "Overview", routes: [["snapshot", "Investor Snapshot"], ["overview", "Company Profile"]] },
  { key: "intelligence", label: "Intelligence", landing_route: "directory_intelligence", routes: [["ask", "Ask Henneth"], ["graph", "Knowledge Graph"], ["operating", "Operating Intelligence"], ["past_context", "Past Context"], ["intelligence", "Event-to-Value view"], ["timeline", "Typed timeline"]] },
  { key: "financials", label: "Financials", landing_route: "directory_financials", routes: [["trends", "Financial Trends"], ["baseline", "Financial Baseline"], ["forecast", "Forecast Readiness"], ["alpha_readiness", "Event-to-Value readiness"], ["financials", "Accounting Snapshot"]] },
  { key: "events", label: "Events & Filings", landing_route: "directory_events", routes: [["earnings", "Earnings"], ["events", "Events"], ["filings", "Filings"], ["sources", "Sources"], ["changes", "Change Digest"], ["brief", "Approved brief"]] },
  { key: "strategy", label: "Strategy", landing_route: "directory_strategy", routes: [["scenarios", "Scenarios"], ["valuation", "Valuation"], ["guidance", "Guidance"], ["catalysts", "Catalysts"], ["risks", "Risks"], ["quant", "Quant (legacy)"]] },
  { key: "ownership", label: "Ownership & Peers", landing_route: "directory_ownership", routes: [["ownership", "Ownership"], ["peers", "Peers"], ["watchlist", "Watchlist"], ["conditional", "Conditional Benchmarks"], ["causal", "Causal Map"], ["coverage", "Coverage"], ["thesis", "Thesis Monitor"], ["monitoring", "Monitoring"], ["operations", "Operations (legacy)"]] },
];
let state = {
  session: null,
  data: null,
  selected: null,
  filter: "",
  view: "directory_overview",
  caseRoute: null,
  tree: { expanded: {} },
  ask: { pending: {}, nextId: 0, bySymbol: {} },
  scenario: { bySymbol: {} },
  pastContext: { bySymbol: {} },
  theses: { loaded: false, loading: false, saving: false, error: null, bySymbol: {}, drafts: {}, smoke: { running: false, status: "not_run", checkedAt: null, error: null, rowCount: null } },
};

const SCHEME_CYCLE = { system: "light", light: "dark", dark: "system" };

function ciHash(text) {
  let hash = 2166136261;
  for (const char of String(text || "")) {
    hash ^= char.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function companyBackgroundRegistry() {
  const registry = window.HENNETH_COMPANY_BACKGROUNDS;
  return registry && typeof registry.forSymbol === "function" ? registry : null;
}

function randomRevealSide(fallbackSeed) {
  const entropy = new Uint32Array(1);
  if (globalThis.crypto?.getRandomValues) {
    globalThis.crypto.getRandomValues(entropy);
    return CI_REVEAL_SIDES[entropy[0] % CI_REVEAL_SIDES.length];
  }
  return CI_REVEAL_SIDES[ciHash(fallbackSeed) % CI_REVEAL_SIDES.length];
}

function companyVisual(row, index) {
  const symbol = String(row?.symbol || "").trim().toUpperCase();
  const registry = companyBackgroundRegistry();
  const backgroundPath = registry?.forSymbol(symbol) || "";
  const backgroundMatch = backgroundPath.match(CI_BACKGROUND_ATTR_RE);
  const assetCount = Number(registry?.assetCount) || CI_BACKGROUND_ASSET_COUNT;
  const fallbackIndex = ((ciHash(`${symbol}:${index}`) + Math.max(0, index)) % assetCount) + 1;
  const backgroundId = backgroundMatch ? backgroundMatch[1] : String(fallbackIndex).padStart(2, "0");
  const revealSide = randomRevealSide(`${symbol}:${backgroundId}:reveal`);
  return { backgroundId, backgroundPath, revealSide };
}

function safeBackgroundCssUrl(path) {
  const text = String(path || "").trim();
  return /^product backgrounds\/product-background-\d{2}\.(?:png|webp)$/i.test(text)
    // Encode the directory space for the actual HTTP request. Keeping the
    // registry's filesystem path readable lets the static inventory checker
    // stat the same file while the browser receives a valid served URL.
    ? `url("${encodeURI(text)}")`
    : "";
}

function ciScheme() {
  try {
    const value = localStorage.getItem("ciScheme");
    return value === "light" || value === "dark" ? value : "system";
  } catch { return "system"; }
}

function applyCIScheme(choice) {
  document.documentElement.setAttribute("data-scheme-switching", "");
  if (choice === "light" || choice === "dark") {
    document.documentElement.setAttribute("data-scheme", choice);
    try { localStorage.setItem("ciScheme", choice); } catch {}
  } else {
    document.documentElement.removeAttribute("data-scheme");
    try { localStorage.removeItem("ciScheme"); } catch {}
  }
  const button = $("schemeToggle");
  if (button) {
    button.textContent = `Scheme: ${choice}`;
    button.setAttribute("aria-label", `Colour scheme: ${choice}. Activate to change.`);
  }
  const clearSwitch = () => document.documentElement.removeAttribute("data-scheme-switching");
  requestAnimationFrame(() => requestAnimationFrame(clearSwitch));
  setTimeout(clearSwitch, 150);
}

function setAccessState(label, fileLabel) {
  $("authState").textContent = label;
  if ($("fileStatus")) $("fileStatus").textContent = fileLabel;
}

// The static shell is shared with the original visual template, but the
// Company Intelligence product must never present the Desk as its workspace.
// Normalize the server-rendered landmarks before auth/data rendering so the
// signed-out and signed-in surfaces use CI identity consistently.
function normalizeCIShell() {
  const brand = document.querySelector(".brand");
  if (brand) {
    brand.setAttribute("href", "/");
    brand.setAttribute("aria-label", "Henneth Company Intelligence");
  }
  const tab = document.querySelector(".ci-tab");
  if (tab) {
    tab.setAttribute("aria-label", "Company Intelligence workspace");
    const label = tab.querySelector("span");
    if (label) label.textContent = "Company Intelligence";
  }
  const footer = document.querySelector(".statusbar");
  if (footer) footer.setAttribute("aria-label", "Company Intelligence status");
  const terminal = document.querySelector(".status-left > span:not(.status-dot):not(.status-muted)");
  if (terminal) terminal.textContent = "Henneth Company Intelligence";
}

function storedSession() {
  try { return JSON.parse(localStorage.getItem(SESSION_KEY) || "null"); }
  catch { return null; }
}

function saveSession(session) {
  state.session = session;
  try {
    if (session) localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    else localStorage.removeItem(SESSION_KEY);
  } catch {}
}

async function authRequest(path, body) {
  const res = await fetch(`${SB_URL}/auth/v1/${path}`, {
    method: "POST",
    headers: { apikey: SB_KEY, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(payload.error_description || payload.msg || `HTTP ${res.status}`);
  return payload;
}

async function refreshSession() {
  if (!state.session?.refresh_token) return null;
  try {
    const next = await authRequest("token?grant_type=refresh_token", { refresh_token: state.session.refresh_token });
    saveSession(next);
    return next.access_token;
  } catch {
    saveSession(null);
    return null;
  }
}

function thesisErrorCode(status, payload) {
  const text = `${payload?.code || ""} ${payload?.message || ""} ${payload?.details || ""} ${payload?.hint || ""}`;
  if (status === 401) return "auth_expired";
  if (status === 404 || payload?.code === "PGRST205" || /schema cache.*company_theses|company_theses.*schema cache|relation .*company_theses.*does not exist|could not find .*company_theses/i.test(text)) return "schema_unavailable";
  return "request_failed";
}

async function companyThesisRequest(path, options = {}, retried = false) {
  const token = state.session?.access_token;
  if (!token) throw new Error("auth_expired");
  const headers = {
    apikey: SB_KEY,
    Authorization: `Bearer ${token}`,
  };
  if (options.body !== undefined) headers["content-type"] = "application/json";
  if (options.prefer) headers.Prefer = options.prefer;
  let res;
  try {
    res = await fetch(`${SB_URL}/rest/v1/company_theses${path}`, {
      method: options.method || "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new Error("network_unavailable");
  }
  if (res.status === 401 && !retried) {
    const fresh = await refreshSession();
    if (fresh) return companyThesisRequest(path, options, true);
  }
  if (res.status === 204) return null;
  const payload = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(thesisErrorCode(res.status, payload));
  return payload;
}

function groupCompanyTheses(rows) {
  const bySymbol = {};
  (Array.isArray(rows) ? rows : []).forEach(row => {
    if (!row?.symbol) return;
    (bySymbol[row.symbol] || (bySymbol[row.symbol] = [])).push(row);
  });
  Object.values(bySymbol).forEach(list => list.sort((a, b) => String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || ""))));
  return bySymbol;
}

async function loadCompanyTheses() {
  if (!state.session?.access_token) return;
  state.theses.loading = true;
  state.theses.error = null;
  renderDesk();
  try {
    const rows = await companyThesisRequest(`?select=${encodeURIComponent(THESIS_COLUMNS)}&order=updated_at.desc`);
    state.theses.bySymbol = groupCompanyTheses(rows);
    state.theses.loaded = true;
  } catch (error) {
    state.theses.error = error.message || "request_failed";
    state.theses.loaded = true;
  } finally {
    state.theses.loading = false;
    renderDesk();
  }
}

async function signIn(email, password) {
  const session = await authRequest("token?grant_type=password", { email, password });
  saveSession(session);
  await loadData();
}

async function loadData(retried = false) {
  const token = state.session?.access_token;
  if (!token) return renderGate("Sign in to open the private company file.");
  setAccessState("Loading private file", "checking private file");
  $("app").setAttribute("aria-busy", "true");
  let res;
  try {
    res = await fetch("data/company_intelligence.json", {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
  } catch {
    $("app").removeAttribute("aria-busy");
    setAccessState("Connection failed", "private file unavailable");
    return renderGate("The private file could not be reached. Your session is retained; sign in again to retry.");
  }
  if (res.status === 401 && !retried) {
    const fresh = await refreshSession();
    if (fresh) return loadData(true);
  }
  if (!res.ok) {
    setAccessState("Access blocked", "private file blocked");
    $("app").removeAttribute("aria-busy");
    return renderGate(res.status === 401
      ? "The data gate rejected this account. Owner access is required."
      : `Could not load the company file (${res.status}).`);
  }
  try {
    state.data = await res.json();
  } catch {
    $("app").removeAttribute("aria-busy");
    setAccessState("File invalid", "private file unavailable");
    return renderGate("The private company file was not valid JSON. The last-good deployment remains required.");
  }
  state.selected = state.data?.tickers?.[0]?.symbol || null;
  setAccessState("Private file open", "private file open");
  $("app").removeAttribute("aria-busy");
  $("signOut").hidden = false;
  applyCaseRouteFromLocation({ replace: true });
  renderDesk();
  loadCompanyTheses();
}

function caseViewApi() {
  return window.HennethIntelligenceCaseView || null;
}

function casePathFor(ticker, caseId) {
  return "/company/" + encodeURIComponent(String(ticker || "").toUpperCase()) + "/intelligence/" + encodeURIComponent(String(caseId || ""));
}

function syncCaseLocation(opts) {
  if (!state.caseRoute) return;
  const replace = Boolean(opts && opts.replace);
  const next = casePathFor(state.caseRoute.ticker, state.caseRoute.caseId);
  if (location.pathname + location.search + location.hash === next) return;
  const method = replace ? "replaceState" : "pushState";
  history[method]({ hennethIntelligenceCase: true, ticker: state.caseRoute.ticker, caseId: state.caseRoute.caseId }, "", next);
}

function applyCaseRouteFromLocation(opts) {
  const parsed = caseViewApi()?.parsePath?.(location.pathname) || null;
  if (!parsed) {
    if (state.caseRoute) state.caseRoute = null;
    return null;
  }
  state.caseRoute = parsed;
  state.selected = parsed.ticker;
  syncCaseLocation(opts);
  return parsed;
}

function openIntelligenceCase(ticker, caseId) {
  const symbol = String(ticker || "").toUpperCase();
  if (!symbol || !caseId) return;
  state.selected = symbol;
  state.caseRoute = { ticker: symbol, caseId: String(caseId) };
  closeMobileDrawers();
  syncCaseLocation();
  renderDesk();
}

function closeIntelligenceCase() {
  state.caseRoute = null;
  if (location.pathname.startsWith("/company/")) {
    history.pushState({ hennethIntelligenceCase: false }, "", "/");
  }
  closeMobileDrawers();
  renderDesk();
}

function boundAskQuestion(value) {
  let text = String(value || "").trim();
  if (new TextEncoder().encode(text).byteLength <= ASK_MAX_QUESTION_BYTES) return text;
  const chars = Array.from(text);
  while (chars.length && new TextEncoder().encode(chars.join("")).byteLength > ASK_MAX_QUESTION_BYTES) chars.pop();
  return chars.join("").trim();
}

async function askCompany(question) {
  const symbol = state.selected;
  const token = state.session?.access_token;
  const text = boundAskQuestion(question);
  if (!symbol || !token || !text || state.ask.pending[symbol]) return;
  const requestId = ++state.ask.nextId;
  state.ask.pending[symbol] = requestId;
  state.ask.bySymbol[symbol] = { question: text, error: null, answer: null, citations: [] };
  renderDesk({ focusAsk: true });
  let res;
  try {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const currentToken = state.session?.access_token;
      if (!currentToken) break;
      res = await fetch("api/ask", {
        method: "POST",
        headers: { Authorization: `Bearer ${currentToken}`, "content-type": "application/json" },
        body: JSON.stringify({ symbol, question: text }),
      });
      if (res.status !== 401 || attempt === 1 || !(await refreshSession())) break;
    }
  } catch {
    if (state.ask.pending[symbol] !== requestId) return;
    delete state.ask.pending[symbol];
    state.ask.bySymbol[symbol] = { question: text, error: "The Ask endpoint could not be reached.", answer: null, citations: [] };
    renderDesk({ focusAsk: state.selected === symbol });
    return;
  }
  if (state.ask.pending[symbol] !== requestId) return;
  if (!res) {
    delete state.ask.pending[symbol];
    state.ask.bySymbol[symbol] = { question: text, error: "Your session expired before Ask could complete.", answer: null, citations: [] };
    renderDesk({ focusAsk: state.selected === symbol });
    return;
  }
  const body = await res.json().catch(() => ({}));
  delete state.ask.pending[symbol];
  state.ask.bySymbol[symbol] = res.ok
    ? { question: text, error: null, answer: body.answer, citations: body.citations || [] }
    : { question: text, error: body.error || `Ask failed (${res.status}).`, answer: null, citations: [] };
  renderDesk({ focusAsk: state.selected === symbol });
}

function renderGate(message) {
  $("signOut").hidden = true;
  syncMobileControls(false);
  setAccessState("Signed out", "private file closed");
  if ($("companyStatus")) $("companyStatus").textContent = "Company Intelligence";
  const app = $("app");
  app.removeAttribute("aria-busy");
  app.classList.remove("is-entering");
  delete app.dataset.companyBg;
  delete app.dataset.revealSide;
  delete app.dataset.companyBackgroundSrc;
  app.style.removeProperty("--ci-company-bg");
  app.innerHTML = `
    <section class="gate" aria-labelledby="gateTitle">
      <img class="gate-background" src="/login-background.webp" alt="" aria-hidden="true" width="1672" height="942" loading="eager" decoding="async">
      <div>
        <p class="eyebrow">Private research workspace</p>
        <h1 id="gateTitle">Company context,<br>one layer deeper.</h1>
        <p>Sign in with the existing Henneth account. This surface reads one private JSON file and keeps execution out of the product.</p>
      </div>
      <form id="loginForm" class="login">
        <p class="form-title">Owner access</p>
        <label><span>Email</span><input id="email" type="email" autocomplete="email" required></label>
        <label><span>Password</span><input id="password" type="password" autocomplete="current-password" required></label>
        <button class="submit-btn" type="submit">Sign in</button>
        <p id="loginMsg" class="muted" role="status" aria-live="polite">${esc(message || "No signup here. Access is owner-only at the data gate.")}</p>
      </form>
    </section>`;
  bindLogin();
}

function rows() {
  const q = state.filter.trim().toUpperCase();
  return (state.data?.tickers || []).filter(r => {
    if (!q) return true;
    return r.symbol.includes(q)
      || String(r.name || "").toUpperCase().includes(q)
      || String(r.sector || "").toUpperCase().includes(q);
  });
}

function pick(symbol) {
  state.selected = symbol;
  if (state.caseRoute && state.caseRoute.ticker !== symbol) closeIntelligenceCase();
  else {
    closeMobileDrawers();
    renderDesk();
  }
}

function syncMobileControls(available) {
  const mobile = window.matchMedia(CI_MOBILE_QUERY).matches;
  const app = $("app");
  for (const id of ["companyDrawerOpen", "intelligenceDrawerOpen"]) {
    const button = $(id);
    if (!button) continue;
    button.hidden = !(available && mobile);
  }
  $("companyDrawerOpen")?.setAttribute("aria-expanded", app?.classList.contains("mobile-left-open") ? "true" : "false");
  $("intelligenceDrawerOpen")?.setAttribute("aria-expanded", app?.classList.contains("mobile-right-open") ? "true" : "false");
}

function bindPanelResize() {
  const workspace = $("app");
  if (!workspace) return;
  const saved = (key, fallback, min, max) => {
    let value = NaN;
    try { value = Number.parseInt(localStorage.getItem(key), 10); } catch {}
    return Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : fallback;
  };
  let leftW = saved("ciLeftW", 270, CI_LEFT_MIN, CI_LEFT_MAX);
  let rightW = saved("ciRightW", 320, CI_RIGHT_MIN, CI_RIGHT_MAX);
  workspace.style.setProperty("--ci-left-w", `${leftW}px`);
  workspace.style.setProperty("--ci-right-w", `${rightW}px`);

  const wire = (id, side) => {
    const handle = $(id);
    if (!handle) return;
    handle.style.touchAction = "none";
    handle.tabIndex = 0;
    handle.setAttribute("aria-valuemin", String(side === "left" ? CI_LEFT_MIN : CI_RIGHT_MIN));
    handle.setAttribute("aria-valuemax", String(side === "left" ? CI_LEFT_MAX : CI_RIGHT_MAX));
    let dragging = false;
    let pointerId = null;
    let startX = 0;
    let startW = 0;
    const setWidth = width => {
      const min = side === "left" ? CI_LEFT_MIN : CI_RIGHT_MIN;
      const max = side === "left" ? CI_LEFT_MAX : CI_RIGHT_MAX;
      const next = Math.min(max, Math.max(min, width));
      if (side === "left") leftW = next;
      else rightW = next;
      workspace.style.setProperty(side === "left" ? "--ci-left-w" : "--ci-right-w", `${next}px`);
      handle.setAttribute("aria-valuenow", String(next));
      return next;
    };
    setWidth(side === "left" ? leftW : rightW);
    handle.addEventListener("pointerdown", event => {
      if (event.pointerType === "mouse" && event.button !== 0) return;
      dragging = true;
      pointerId = event.pointerId;
      startX = event.clientX;
      startW = side === "left" ? leftW : rightW;
      handle.setPointerCapture(pointerId);
      workspace.classList.add("ci-resizing");
      event.preventDefault();
    });
    handle.addEventListener("pointermove", event => {
      if (!dragging || event.pointerId !== pointerId) return;
      const delta = side === "left" ? event.clientX - startX : startX - event.clientX;
      setWidth(startW + delta);
    });
    const end = event => {
      if (!dragging || event.pointerId !== pointerId) return;
      dragging = false;
      if (handle.hasPointerCapture(pointerId)) handle.releasePointerCapture(pointerId);
      pointerId = null;
      workspace.classList.remove("ci-resizing");
      try { localStorage.setItem(side === "left" ? "ciLeftW" : "ciRightW", String(side === "left" ? leftW : rightW)); } catch {}
    };
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
    handle.addEventListener("keydown", event => {
      const step = event.shiftKey ? 24 : 12;
      const current = side === "left" ? leftW : rightW;
      const keyStep = side === "left"
        ? { ArrowLeft: -step, ArrowRight: step }
        : { ArrowLeft: step, ArrowRight: -step };
      if (!(event.key in keyStep)) return;
      const next = setWidth(current + keyStep[event.key]);
      try { localStorage.setItem(side === "left" ? "ciLeftW" : "ciRightW", String(next)); } catch {}
      event.preventDefault();
    });
  };
  wire("companyResize", "left");
  wire("intelligenceResize", "right");
}

function syncDrawerBackdrops() {
  const app = $("app");
  const mobile = window.matchMedia(CI_MOBILE_QUERY).matches;
  const leftOpen = mobile && app?.classList.contains("mobile-left-open");
  const rightOpen = mobile && app?.classList.contains("mobile-right-open");
  document.querySelectorAll(".drawer-backdrop").forEach(backdrop => {
    backdrop.hidden = !((backdrop.classList.contains("company-backdrop") && leftOpen)
      || (backdrop.classList.contains("intelligence-backdrop") && rightOpen));
  });
}

let mobileDrawerOpener = null;

function closeMobileDrawers(restoreFocus = false) {
  const app = $("app");
  app?.classList.remove("mobile-left-open", "mobile-right-open");
  document.body.classList.remove("company-drawer-open", "intelligence-drawer-open");
  syncDrawerBackdrops();
  syncMobileControls(!!state.data);
  if (restoreFocus && mobileDrawerOpener?.isConnected) {
    const opener = mobileDrawerOpener;
    requestAnimationFrame(() => opener.focus({ preventScroll: true }));
  }
  if (restoreFocus) mobileDrawerOpener = null;
}

function openMobileDrawer(kind) {
  if (!window.matchMedia(CI_MOBILE_QUERY).matches) return;
  const app = $("app");
  if (!app) return;
  mobileDrawerOpener = kind === "company" ? $("companyDrawerOpen") : $("intelligenceDrawerOpen");
  app.classList.toggle("mobile-left-open", kind === "company");
  app.classList.toggle("mobile-right-open", kind === "intelligence");
  document.body.classList.toggle("company-drawer-open", kind === "company");
  document.body.classList.toggle("intelligence-drawer-open", kind === "intelligence");
  syncDrawerBackdrops();
  syncMobileControls(!!state.data);
  requestAnimationFrame(() => {
    const selector = kind === "company" ? "#companyDirectory input, #companyDirectory button" : "#companyIntelligenceTree button";
    document.querySelector(selector)?.focus({ preventScroll: true });
  });
}

function railLinkMarkup(item) {
  return `<a class="icon-rail-link ${item.active ? "is-active" : ""}" href="${esc(item.href)}" ${item.active ? 'aria-current="page"' : ""} title="${esc(item.label)}"><iconify-icon icon="${esc(item.icon)}" aria-hidden="true"></iconify-icon><span class="sr-only">${esc(item.label)}</span></a>`;
}

function renderDesk(searchState) {
  const list = rows();
  const routeTicker = state.caseRoute?.ticker || null;
  const allRows = state.data?.tickers || [];
  const row = routeTicker
    ? allRows.find(item => item && item.symbol === routeTicker) || null
    : (state.selected ? list.find(r => r.symbol === state.selected) : null) || list[0] || null;
  if (routeTicker) state.selected = routeTicker;
  else if (row) state.selected = row.symbol;
  const activeIndex = row ? Math.max(0, (state.data?.tickers || []).findIndex(item => item.symbol === row.symbol)) : -1;
  const visual = row ? companyVisual(row, activeIndex) : null;
  $("app").innerHTML = `
    <aside class="icon-rail" aria-label="Company Intelligence navigation">
      <nav class="icon-rail-nav" aria-label="Company Intelligence sections">
        ${RAIL_LINKS.map(railLinkMarkup).join("")}
      </nav>
      <div class="icon-rail-spacer"></div>
      <button class="icon-rail-link" type="button" id="railScheme" title="Change colour scheme"><iconify-icon icon="lucide:sun-moon" aria-hidden="true"></iconify-icon><span class="sr-only">Change colour scheme</span></button>
      <button class="icon-rail-link" type="button" id="railProfile" title="Sign out"><iconify-icon icon="lucide:user-round" aria-hidden="true"></iconify-icon><span class="sr-only">Sign out</span></button>
    </aside>
    <div class="drawer-backdrop company-backdrop" data-drawer-close="company" aria-hidden="true" hidden></div>
    <div class="drawer-backdrop intelligence-backdrop" data-drawer-close="intelligence" aria-hidden="true" hidden></div>
    <aside id="companyDirectory" class="rail" aria-label="Company directory">
      <div class="ci-resize-handle ci-resize-left" id="companyResize" role="separator" aria-orientation="vertical" aria-label="Resize company directory"></div>
      <div class="rail-head"><strong>Company directory</strong><span>${esc(list.length)} shown</span></div>
      <div class="toolbar">
        <input id="search" class="search" type="search" aria-label="Search companies" aria-controls="companyList" placeholder="Search symbol, company, sector" value="${esc(state.filter)}">
        <button id="clearFilter" type="button" aria-label="Clear company search"><iconify-icon icon="lucide:x" aria-hidden="true"></iconify-icon><span class="sr-only">Clear</span></button>
        <span class="muted">${esc(state.data?.meta?.count || 0)} companies. Built ${esc(state.data?.meta?.built || "unknown")}.</span>
      </div>
      <div id="companyList" class="list" role="listbox" aria-label="Companies">${list.map(r => `
        <button class="row ${r.symbol === row?.symbol ? "active" : ""}" type="button" role="option" aria-selected="${r.symbol === row?.symbol}" tabindex="${r.symbol === row?.symbol ? "0" : "-1"}" data-symbol="${esc(r.symbol)}">
          <span><b>${esc(r.symbol)}</b><small>${esc(r.name || "Name unavailable")}</small></span>
          <em>${fmt(r.liquidity?.adtv_m, 0)}M</em>
        </button>`).join("") || `<div class="empty" role="option" aria-disabled="true">No companies match that filter.</div>`}
      </div>
      <span class="sr-only" role="status" aria-live="polite">${esc(list.length)} companies match.</span>
    </aside>
    <section id="companyDetail" class="detail" role="tabpanel" tabindex="-1" aria-label="${row ? `${esc(row.symbol)} company intelligence` : "Company intelligence"}">${state.caseRoute ? renderIntelligenceCase(row, state.caseRoute.caseId) : row ? detail(row) : `<div class="empty">No company intelligence rows are available yet.</div>`}</section>
    <aside id="companyIntelligenceTree" class="tree-panel" aria-label="Company intelligence directory tree">
      <div class="ci-resize-handle ci-resize-right" id="intelligenceResize" role="separator" aria-orientation="vertical" aria-label="Resize intelligence directory"></div>
      ${row ? renderViewNav(row) : `<div class="tree-empty">No directories available.</div>`}
    </aside>`;
  requestAnimationFrame(() => window.HennethCICharts?.renderAll($("companyDetail")));
  if ($("companyStatus")) $("companyStatus").textContent = row ? `${row.symbol} · company intelligence` : "Company Intelligence";
  bindPanelResize();
  syncMobileControls(true);
  syncDrawerBackdrops();
  $("search").oninput = event => {
    const start = event.target.selectionStart;
    const end = event.target.selectionEnd;
    state.filter = event.target.value;
    renderDesk({ focus: true, start, end });
  };
  $("clearFilter").onclick = () => {
    state.filter = "";
    renderDesk({ focus: true, start: 0, end: 0 });
  };
  $("railScheme")?.addEventListener("click", () => $("schemeToggle")?.click());
  $("railProfile")?.addEventListener("click", () => $("signOut")?.click());
  const setMobilePanel = (side, open) => {
    const workspace = $("app");
    workspace?.classList.toggle(`mobile-${side}-open`, open);
    const button = side === "left" ? $("ciLeftToggle") : $("ciRightToggle");
    button?.setAttribute("aria-expanded", String(open));
  };
  $("ciLeftToggle")?.addEventListener("click", () => setMobilePanel("left", !$("app")?.classList.contains("mobile-left-open")));
  $("ciRightToggle")?.addEventListener("click", () => setMobilePanel("right", !$("app")?.classList.contains("mobile-right-open")));
  document.querySelectorAll("[data-symbol]").forEach(btn => {
    btn.onclick = () => pick(btn.dataset.symbol);
    btn.onkeydown = event => moveCompanyFocus(event, btn);
  });
  document.querySelectorAll("[data-view]").forEach(btn => {
    btn.onclick = () => {
      state.view = btn.dataset.view;
      if (state.caseRoute) {
        state.caseRoute = null;
        if (location.pathname.startsWith("/company/")) history.pushState({ hennethIntelligenceCase: false }, "", "/");
      }
      closeMobileDrawers();
      renderDesk({ focusView: state.view });
    };
    btn.onkeydown = event => moveViewFocus(event, btn);
  });
  document.querySelectorAll("[data-tree-toggle]").forEach(button => {
    button.onclick = event => {
      event.stopPropagation();
      const key = button.dataset.treeToggle;
      state.tree.expanded[key] = !state.tree.expanded[key];
      renderDesk();
    };
  });
  document.querySelectorAll("[data-research-route]").forEach(btn => {
    btn.onclick = () => {
      state.view = btn.dataset.researchRoute;
      closeMobileDrawers();
      renderDesk({ focusView: state.view });
    };
  });
  document.querySelectorAll("[data-past-context-id]").forEach(btn => {
    btn.onclick = () => {
      state.pastContext.bySymbol[state.selected] = btn.dataset.pastContextId;
      renderDesk();
    };
  });
  document.querySelectorAll("[data-company-logo]").forEach(image => {
    image.addEventListener("error", () => {
      image.hidden = true;
      image.nextElementSibling?.removeAttribute("hidden");
    }, { once: true });
  });
  document.querySelectorAll("[data-drawer-close]").forEach(backdrop => {
    backdrop.onclick = () => closeMobileDrawers(true);
  });
  const askForm = $("askForm");
  if (askForm) {
    askForm.onsubmit = event => {
      event.preventDefault();
      askCompany($("askInput")?.value);
    };
  }
  const scenarioForm = $("scenarioForm");
  if (scenarioForm && row) {
    scenarioForm.oninput = () => captureScenarioInputs(row.symbol);
    scenarioForm.onsubmit = event => {
      event.preventDefault();
      captureScenarioInputs(row.symbol);
      calculateScenario(row);
      renderDesk({ focusScenario: true });
    };
    $("scenarioClear")?.addEventListener("click", () => {
      state.scenario.bySymbol[row.symbol] = blankScenarioState();
      renderDesk({ focusScenario: true });
    });
  }
  if (row) bindPrivateTheses(row);
  if (searchState?.focus) {
    const input = $("search");
    input.focus({ preventScroll: true });
    input.setSelectionRange(searchState.start, searchState.end);
  }
  if (searchState?.focusView) {
    document.querySelector(`[data-view="${CSS.escape(searchState.focusView)}"]`)?.focus({ preventScroll: true });
  }
  if (searchState?.focusAsk) {
    $("askInput")?.focus({ preventScroll: true });
  }
  if (searchState?.focusScenario) {
    $("scenarioGrowth")?.focus({ preventScroll: true });
  }
  if (searchState?.focusThesis) {
    $("privateThesisText")?.focus({ preventScroll: true });
  }
  enhanceMotion({ visual, animate: !searchState || Boolean(searchState.focusView) });
}

function currentPilotSymbols() {
  return new Set((state.data?.tickers || []).map(row => row.symbol).filter(Boolean));
}

function moveCompanyFocus(event, button) {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  const options = [...document.querySelectorAll("[data-symbol]")];
  if (!options.length) return;
  event.preventDefault();
  let index = options.indexOf(button);
  if (event.key === "ArrowDown") index = (index + 1) % options.length;
  if (event.key === "ArrowUp") index = (index - 1 + options.length) % options.length;
  if (event.key === "Home") index = 0;
  if (event.key === "End") index = options.length - 1;
  state.selected = options[index].dataset.symbol;
  renderDesk();
  document.querySelector(`[data-symbol="${CSS.escape(state.selected)}"]`)?.focus({ preventScroll: true });
}

function moveViewFocus(event, button) {
  if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
  const group = button.parentElement?.closest("[data-view-group]");
  const tabs = [...(group || document).querySelectorAll("[data-view]")].filter(tab => !tab.closest("[hidden]"));
  if (!tabs.length) return;
  event.preventDefault();
  let index = tabs.indexOf(button);
  if (event.key === "ArrowRight") index = (index + 1) % tabs.length;
  if (event.key === "ArrowLeft") index = (index - 1 + tabs.length) % tabs.length;
  if (event.key === "Home") index = 0;
  if (event.key === "End") index = tabs.length - 1;
  state.view = tabs[index].dataset.view;
  renderDesk({ focusView: state.view });
}

function metric(label, value, note) {
  return `<div class="metric"><span>${esc(label)}</span><b>${esc(value)}</b><small class="muted">${esc(note || "")}</small></div>`;
}

function detail(r) {
  const f = r.fundamentals || {};
  const v = r.valuation || {};
  const p = r.profile || {};
  const liq = r.liquidity || {};
  const source = p.source_url ? `<a href="${esc(p.source_url)}" target="_blank" rel="noopener">DPS company page</a>` : "DPS company page";
  const inc = p.incorporation?.value || p.incorporation?.matched_text || "unknown";
  const intel = r.intelligence || {};
  const logoUrl = companyLogoUrl(r.symbol);
  const latestChange = r.change_intelligence?.latest_change_at || "No dated change";
  const move = Number(r.price?.ret_20d);
  const moveClass = Number.isFinite(move) ? (move > 0 ? "is-positive" : move < 0 ? "is-negative" : "is-flat") : "is-flat";
  return `
    <div class="hero">
      <div class="hero-main">
        <div class="hero-identity">
          <span class="company-logo-frame">${logoUrl ? `<img data-company-logo src="${esc(logoUrl)}" alt="${esc(r.name || r.symbol)} logo" width="128" height="128" loading="eager" decoding="async">` : ""}<span class="company-logo-fallback" ${logoUrl ? "hidden" : ""}>${esc(String(r.symbol || "?").slice(0, 2))}</span></span>
          <div><p class="eyebrow">${esc(r.sector || "Sector unknown")}</p><h1>${esc(r.symbol)}${r.name ? `<span>${esc(r.name)}</span>` : ""}</h1></div>
        </div>
        <p class="hero-summary"><iconify-icon icon="lucide:briefcase-business" aria-hidden="true"></iconify-icon><span>${esc(companyBusinessSummary(p.business_description))}</span></p>
        <div class="hero-context" aria-label="Company research context">
          <span><iconify-icon icon="lucide:landmark" aria-hidden="true"></iconify-icon><small>Market capitalisation</small><b>${esc(f.market_cap || "unknown")}</b></span>
          <span><iconify-icon icon="lucide:calendar-clock" aria-hidden="true"></iconify-icon><small>Latest retained change</small><b>${esc(String(latestChange).slice(0, 10))}</b></span>
          <span><iconify-icon icon="lucide:files" aria-hidden="true"></iconify-icon><small>Evidence footprint</small><b>${esc(intel.document_count ?? 0)} filings · ${esc(intel.event_count ?? 0)} events</b></span>
        </div>
      </div>
      <div class="stamp">
        <span class="kicker">Retained price</span>
        <b>Rs ${esc(fmt(r.price?.current))}</b>
        <strong class="hero-move ${moveClass}"><iconify-icon icon="${move > 0 ? "lucide:trending-up" : move < 0 ? "lucide:trending-down" : "lucide:minus"}" aria-hidden="true"></iconify-icon>${esc(pct(r.price?.ret_20d))}<small>20 sessions</small></strong>
        <span class="muted">As of ${esc(r.price?.date || "unknown")} · research, not advice</span>
      </div>
    </div>
    <div class="grid4">
      ${metric("Official filings", intel.document_count ?? 0, `${intel.event_count ?? 0} classified events`)}
      ${metric("Financial facts", intel.financial_fact_count ?? 0, `${r.financial_series?.coverage?.period_count ?? 0} explicit periods`)}
      ${metric("Change digest", intel.change_item_count ?? 0, `${r.change_intelligence?.latest_change_at || "no dated change"}`)}
      ${metric("Graph links", intel.graph_edge_count ?? 0, `${intel.graph_node_count ?? 0} nodes mapped`)}
    </div>
    ${state.caseRoute ? renderIntelligenceCase(r, state.caseRoute.caseId)
      : state.view === "directory_overview" ? renderOverviewDashboard(r)
      : state.view === "directory_intelligence" ? renderIntelligenceDashboard(r)
      : state.view === "directory_financials" ? renderFinancialsDashboard(r)
      : state.view === "directory_events" ? renderEventsDashboard(r)
      : state.view === "directory_strategy" ? renderStrategyDashboard(r)
      : state.view === "directory_ownership" ? renderOwnershipDashboard(r)
      : state.view === "past_context" ? renderPastContext(r)
      : state.view === "financials" ? renderCompanyFinancials(r)
      : state.view === "earnings" ? renderCompanyEarnings(r)
      : state.view === "operations" ? renderCompanyOperations(r)
      : state.view === "valuation" ? renderCompanyValuation(r)
      : state.view === "guidance" ? renderGuidanceDomainView(r, "guidance", "Guidance", "No retained official management assertion passed the strict source shape.")
      : state.view === "catalysts" ? renderCompanyDomainView(r, "catalysts", "Catalysts", "Catalysts are shown only when Company Brain references an existing typed object.")
      : state.view === "risks" ? renderGuidanceDomainView(r, "risks", "Risks", "No retained official risk assertion passed the strict source shape.")
      : state.view === "events" ? renderCompanyEvents(r)
      : state.view === "peers" ? renderCompanyPeers(r)
      : state.view === "ownership" ? renderCompanyOwnership(r)
      : state.view === "quant" ? renderCompanyQuant(r)
      : state.view === "snapshot" ? renderInvestorSnapshot(r)
      : state.view === "timeline" ? renderTimeline(r)
      : state.view === "changes" ? renderChangeIntelligence(r)
      : state.view === "trends" ? renderFinancials(r)
      : state.view === "baseline" ? renderFinancialBaseline(r)
      : state.view === "forecast" ? renderForecastReadiness(r)
      : state.view === "alpha_readiness" ? renderEventToValueProductReadiness()
      : state.view === "intelligence" ? renderIntelligence(r)
      : state.view === "thesis" ? renderThesisMonitor(r)
      : state.view === "watchlist" ? renderEvidenceWatchlist(r)
      : state.view === "monitoring" ? renderCiMonitoring(r)
      : state.view === "scenarios" ? renderScenarioLab(r)
      : state.view === "ask" ? renderAskHenneth(r)
      : state.view === "graph" ? renderGraph(r)
      : state.view === "operating" ? renderOperatingIntelligence(r)
      : state.view === "conditional" ? renderConditionalBenchmarks(r)
      : state.view === "causal" ? renderCausalFoundations(r)
      : state.view === "coverage" ? renderCoverage(r)
      : state.view === "filings" ? renderFilings(r)
      : state.view === "sources" ? renderSources(r)
      : state.view === "brief" ? renderBrief(r)
      : renderCompanyProfile(r, { f, v, p, liq, source, inc })}`;
}

function renderViewNav(r) {
  const toolLabels = new Map([
    ["timeline", `Typed timeline ${r.company_brain?.timeline?.length || 0}`],
    ["changes", `Change digest ${r.change_intelligence?.items?.length || 0}`],
    ["trends", `Financial trends ${r.financial_series?.facts?.length || 0}`],
    ["thesis", `Thesis monitor ${r.thesis_monitoring?.active_thesis_count || 0}`],
    ["watchlist", `Watchlist ${r.evidence_watchlist?.active_watch_count ?? "unknown"}`],
    ["monitoring", `Monitoring ${r.monitoring?.alert_count ?? "unknown"}`],
    ["graph", `Knowledge graph ${r.graph?.edges?.length || 0}`],
    ["operating", `Operating intelligence ${r.operating_events?.length || 0}`],
    ["conditional", `Conditional benchmarks ${r.conditional_benchmarks?.benchmarks?.length || 0}`],
    ["causal", `Causal map ${r.causal_foundations?.causal_rows?.length || 0}`],
    ["filings", `Filings detail ${r.filings?.length || 0}`],
    ["sources", `Sources ${(r.sources?.sources?.length || 0) + (r.sources?.documents?.length || 0)}`],
    ["brief", r.brief?.current ? "Approved brief" : "Brief queue"],
  ]);
  const routeGroup = key => PRIMARY_COMPANY_TABS.some(([route]) => route === key) ? "primary" : "advanced";
  const node = (key, label, depth = 0) => {
    const active = state.view === key;
    return `<button type="button" aria-current="${active ? "page" : "false"}" aria-controls="companyDetail" class="tree-leaf ${active ? "active" : ""} depth-${depth}" data-view="${key}" data-view-group="${routeGroup(key)}"><iconify-icon class="tree-file" icon="lucide:file-text" aria-hidden="true"></iconify-icon><span>${esc(label)}</span></button>`;
  };
  const folder = ({ key, label, landing_route: landingRoute, routes }) => {
    const expanded = state.tree.expanded[key] ?? true;
    const dashboardRoute = landingRoute || (key === "overview" ? "directory_overview" : null);
    const childNodes = routes.map(([route, routeLabel]) => node(route, toolLabels.get(route) || routeLabel, 1)).join("");
    return `<section class="tree-folder ${expanded ? "is-expanded" : ""}" data-tree-folder="${key}">
      <div class="tree-folder-row ${dashboardRoute && state.view === dashboardRoute ? "active" : ""}">
        <button class="tree-expander" type="button" aria-label="${expanded ? "Collapse" : "Expand"} ${esc(label)}" aria-expanded="${expanded}" data-tree-toggle="${key}"><iconify-icon icon="${expanded ? "lucide:chevron-down" : "lucide:chevron-right"}" aria-hidden="true"></iconify-icon></button>
        ${dashboardRoute ? `<button class="tree-folder-label" type="button" aria-current="${state.view === dashboardRoute ? "page" : "false"}" aria-controls="companyDetail" data-view="${dashboardRoute}" data-view-group="directory"><iconify-icon class="tree-folder-icon" icon="${expanded ? "lucide:folder-open" : "lucide:folder"}" aria-hidden="true"></iconify-icon><span>${esc(label)}</span></button>` : `<span class="tree-folder-label"><iconify-icon class="tree-folder-icon" icon="${expanded ? "lucide:folder-open" : "lucide:folder"}" aria-hidden="true"></iconify-icon><span>${esc(label)}</span></span>`}
      </div>
      <div class="tree-children" role="group" ${expanded ? "" : "hidden"}>${childNodes}</div>
    </section>`;
  };
  return `<div class="viewnav-shell tree-shell" aria-label="Company intelligence navigation">
    <div class="tree-head"><span class="tree-kicker">COMPANY INTELLIGENCE</span><span class="tree-count">${TREE_GROUPS.length} directories</span></div>
    <nav class="tree-view primary-tabs" aria-label="Primary company sections" data-view-group="primary">${TREE_GROUPS.map(folder).join("")}</nav>
    <div class="tree-divider" aria-hidden="true"></div>
    <div class="tree-group-label" aria-label="Research tools" data-view-group="advanced">RESEARCH TOOLS · NESTED ABOVE</div>
  </div>`;
}

const OBJECT_TYPE_LABELS = {
  reported_fact: "Reported Fact",
  derived_fact: "Derived Fact",
  inference: "Inference",
  scenario: "Scenario",
  forecast: "Forecast",
};

function objectTypeLabel(value) {
  const key = String(value || "").trim().toLowerCase();
  return OBJECT_TYPE_LABELS[key] || (key ? key.replaceAll("_", " ") : "Unknown object type");
}

function objectTypeClass(value) {
  const key = String(value || "").trim().toLowerCase().replaceAll("_", "-");
  return ["reported-fact", "derived-fact", "inference", "scenario", "forecast"].includes(key) ? key : "unknown";
}

function unknownValue(value, label = "Unknown — awaiting sourced inputs") {
  return value == null || value === "" ? label : esc(value);
}

function confidenceValue(value) {
  return value == null || value === "" ? "Unknown" : `${esc(fmt(value, 0))}/100`;
}

function probabilityValue(value) {
  if (value == null || value === "") return "Unknown";
  const number = Number(value);
  if (!Number.isFinite(number)) return "Unknown";
  const percent = number >= 0 && number <= 1 ? number * 100 : number;
  return `${esc(fmt(percent, 1))}%`;
}

function listValue(value, empty = "Unknown — awaiting sourced inputs") {
  if (!Array.isArray(value) || !value.length) return empty;
  return value.map(item => esc(item)).join(", ");
}

function operatingEvidence(items) {
  if (!Array.isArray(items) || !items.length) return `<div class="oi-empty-note">No bounded evidence citation is attached.</div>`;
  return `<div class="oi-evidence">${items.map(item => {
    const href = safeHref(item?.source_url);
    const page = Number(item?.page) > 0 ? `page ${Number(item.page)}` : "page unknown";
    const doc = item?.document_id || "document unknown";
    const sourceName = item?.source || "source unknown";
    const hash = item?.content_sha256 || item?.evidence_sha256 || "";
    const source = href ? `<a href="${href}" target="_blank" rel="noopener">${esc(page)} · source URL</a>` : esc(page);
    return `<div class="oi-evidence-row"><b>${esc(doc)}</b><span>${esc(sourceName)} · ${source}${hash ? ` · hash ${esc(short(hash, 12))}` : ""}</span><blockquote>${esc(short(item?.text || "No bounded excerpt supplied.", 280))}</blockquote></div>`;
  }).join("")}</div>`;
}

function operatingImpact(value) {
  return value == null || value === "" || (typeof value === "number" && !Number.isFinite(value))
    ? "Unknown — awaiting sourced inputs"
    : esc(value);
}

function renderCementOperatingSeries(r) {
  const row = r.cement_operating_series || {};
  const metrics = row.metrics && typeof row.metrics === "object" && !Array.isArray(row.metrics) ? row.metrics : {};
  const observations = Object.entries(metrics).flatMap(([metric, items]) => (Array.isArray(items) ? items : []).map(item => ({ ...item, metric })));
  const downstream = row.downstream_status || {};
  const metricLabels = {
    clinker_production: "Clinker production",
    cement_production: "Cement production",
    cement_sales_local: "Local sales",
    cement_sales_export: "Export sales",
    cement_sales_total: "Total cement sales",
  };
  const sourceLabel = source => {
    const href = safeHref(source.source_url);
    const page = Number(source.page) > 0 ? `page ${Number(source.page)}` : "page unknown";
    return href ? `<a href="${href}" target="_blank" rel="noopener">${esc(page)} · official source</a>` : esc(page);
  };
  const sourceAvailability = source => source.available_on
    ? `official availability ${esc(source.available_on)}`
    : `publication date not retained · retained ${esc(source.retained_on || source.retrieved_at || "unknown")}`;
  const observationCards = observations.length ? observations.map(observation => {
    const source = observation.source || {};
    return `<article class="oi-event cement-observation" aria-labelledby="cement-${esc(observation.observation_id || observation.metric || "unknown")}">
      <header class="oi-card-head"><div><span class="oi-type oi-type-reported-fact">Audit-only observation</span><span class="pill">${esc(metricLabels[observation.metric] || String(observation.metric || "metric").replaceAll("_", " "))}</span><h3 id="cement-${esc(observation.observation_id || observation.metric || "unknown")}">${esc(observation.period_end || "period unknown")} · ${esc(fmt(observation.value, 0))} ${esc(observation.unit || "")}</h3></div><span class="oi-confidence">not model-loadable</span></header>
      <div class="oi-facts"><div><span>Raw value</span><b>${esc(observation.raw_value || "unknown")}</b></div><div><span>Readiness</span><b>${esc(observation.readiness || "audit_only")}</b></div><div><span>Approval</span><b>${esc(observation.approval_status || "not_owner_approved_forecast_input")}</b></div><div><span>Availability</span><b>${sourceAvailability(source)}</b></div></div>
      <div class="oi-evidence"><div class="oi-evidence-row"><b>${esc(source.document_id || "document unknown")}</b><span>${sourceLabel(source)} · hash ${esc(short(source.content_sha256 || "hash unknown", 12))}</span><blockquote>${esc(short(source.text || "No bounded excerpt supplied.", 280))}</blockquote></div></div>
    </article>`;
  }).join("") : `<div class="empty oi-empty">${esc(row.status || "unknown")} — no retained annual cement operating observations are available for this company.</div>`;
  return `<section class="oi-section cement-operating-section"><header class="oi-section-head"><div><span class="kicker">Cement operating series</span><h3>Annual production and sales facts</h3></div><span class="pill">${esc(row.observation_count ?? observations.length)} observation${(row.observation_count ?? observations.length) === 1 ? "" : "s"}</span></header>
    <p class="section-note">Displayed exactly from the audit-only cement operating state. These rows are source-linked, not model-loadable, and do not activate financial_model_inputs, forecasts, valuations, or market expectations.</p>
    <div class="intel-status"><span>Status <b>${esc(row.status || "unknown")}</b></span><span>Activation <b>${esc(row.activation_status || "not_applicable")}</b></span><span>Annual periods <b>${esc(row.annual_period_count ?? 0)}</b></span><span>Model path <b>${esc(downstream.financial_model_inputs || "not_activated")}</b></span><span>Forecast <b>${esc(downstream.forecast || "not_activated")}</b></span><span>Valuation <b>${esc(downstream.valuation || "not_activated")}</b></span></div>
    <div class="oi-events">${observationCards}</div>
  </section>`;
}

function renderCementHistoricalReconciliation(r) {
  const row = r.cement_historical_reconciliation || {};
  if (row.status === "not_in_cement_reconciliation_scope") return "";
  const lanes = row.driver_lanes && typeof row.driver_lanes === "object" ? row.driver_lanes : {};
  const periods = Array.isArray(row.qualified_financial_periods) ? row.qualified_financial_periods : [];
  const missing = Array.isArray(row.missing_driver_lanes) ? row.missing_driver_lanes : [];
  const factLinks = periods.map(period => {
    const actuals = period.actuals || {};
    const links = Object.entries(actuals).map(([metric, actual]) => {
      const source = actual?.source || {};
      const href = safeHref(source.source_url);
      const page = Number(source.page) > 0 ? `page ${Number(source.page)}` : "page unknown";
      return `<span>${esc(metric.replaceAll("_", " "))}: ${href ? `<a href="${href}" target="_blank" rel="noopener">${esc(page)}</a>` : esc(page)}</span>`;
    }).join(" · ");
    return `<li><b>${esc(period.period_end || "period unknown")}</b> — reported actuals only · ${links}</li>`;
  }).join("");
  const laneRows = Object.entries(lanes).map(([lane, value]) => `<span>${esc(lane.replaceAll("_", " "))}: <b>${esc(value?.status || "unknown")}</b></span>`).join("");
  return `<section class="oi-section"><header class="oi-section-head"><div><span class="kicker">Cement reconciliation</span><h3>Historical actuals and model-input gaps</h3></div><span class="pill">adapter ${esc(row.adapter_status || "unavailable")}</span></header>
    <p class="section-note">Reported annual actuals are reconciled from qualified financial evidence only. Audit-only operating snippets are not promoted; no forecast, valuation or market-expectations output is created here.</p>
    <div class="intel-status"><span>Status <b>${esc(row.status || "unknown")}</b></span><span>Qualified annual periods <b>${esc(row.qualified_financial_period_count ?? 0)}</b></span><span>Missing driver lanes <b>${esc(missing.length ? missing.join(", ").replaceAll("_", " ") : "none")}</b></span></div>
    <div class="oi-facts">${laneRows || "<div><span>Driver lanes</span><b>Unknown — awaiting sourced inputs</b></div>"}</div>
    ${factLinks ? `<ul class="oi-limitations">${factLinks}</ul>` : `<div class="oi-empty-note">No conflict-free qualified annual actuals are available for reconciliation.</div>`}
  </section>`;
}

const BENCHMARK_HORIZONS = ["1Q", "2Q", "4Q", "8Q"];

function benchmarkReason(reason) {
  return reason ? `<small>Reason: ${esc(reason)}</small>` : "";
}

function benchmarkDate(value) {
  return unknownValue(value, "Unknown — awaiting sourced inputs");
}

function benchmarkReturn(value) {
  return value == null || value === "" || !Number.isFinite(Number(value))
    ? "Unknown — awaiting sourced inputs"
    : pct(Number(value));
}

function benchmarkProvenance(provenance) {
  if (!provenance || typeof provenance !== "object") return `<span>Provenance unavailable</span>`;
  const pieces = [];
  if (provenance.history_file) pieces.push(`history ${provenance.history_file}`);
  if (provenance.indices_file) pieces.push(`index ${provenance.indices_file}`);
  if (provenance.baseline_date) pieces.push(`baseline ${provenance.baseline_date}`);
  if (provenance.target_date) pieces.push(`target ${provenance.target_date}`);
  if (provenance.endpoint_date) pieces.push(`endpoint ${provenance.endpoint_date}`);
  if (provenance.selected_date) pieces.push(`selected ${provenance.selected_date}`);
  if (provenance.selected_dates && typeof provenance.selected_dates === "object") {
    const dates = Object.entries(provenance.selected_dates)
      .map(([horizon, values]) => `${horizon}: ${(Array.isArray(values) ? values : []).map(value => value || "unknown").join(" -> ")}`)
      .join("; ");
    if (dates) pieces.push(`selected dates ${dates}`);
  }
  return pieces.length ? pieces.map(piece => `<span>${esc(piece)}</span>`).join("") : `<span>Provenance unavailable</span>`;
}

function renderBenchmarkOutcomes(study) {
  const relative = study.kse100_relative || {};
  const stockMap = relative.stock_return_pct || {};
  const indexMap = relative.index_return_pct || {};
  const relMap = relative.relative_return_pct || relative.returns_pct || {};
  const reasons = relative.reasons || {};
  return `<div class="oi-benchmark-table" role="table" aria-label="Historical benchmark simple price returns">
    <div class="oi-benchmark-row oi-benchmark-head" role="row"><span>Horizon</span><span>Target / endpoint</span><span>Stock simple return</span><span>KSE100 return</span><span>Relative return</span><span>Status</span></div>
    ${BENCHMARK_HORIZONS.map(horizon => {
      const outcome = (study.horizons || {})[horizon] || {};
      const stockValue = outcome.return_pct ?? stockMap[horizon];
      const indexValue = indexMap[horizon];
      const relValue = relMap[horizon];
      const reason = outcome.reason || reasons[horizon];
      return `<div class="oi-benchmark-row" role="row">
        <span><b>${esc(horizon)}</b></span>
        <span>target ${benchmarkDate(outcome.target_date)}<small>endpoint ${benchmarkDate(outcome.selected_date || outcome.provenance?.endpoint_date)}</small></span>
        <span class="oi-stock-return"><b>${benchmarkReturn(stockValue)}</b>${stockValue == null ? benchmarkReason(reason) : ""}</span>
        <span><b>${benchmarkReturn(indexValue)}</b>${indexValue == null ? benchmarkReason(reasons[horizon]) : ""}</span>
        <span><b>${benchmarkReturn(relValue)}</b>${relValue == null ? benchmarkReason(reasons[horizon]) : ""}</span>
        <span>${esc(outcome.status || "unknown")}${benchmarkReason(reason)}</span>
      </div>`;
    }).join("")}
  </div>`;
}

function renderBenchmarkAnalogues(study) {
  const analogues = Array.isArray(study.analogues) ? study.analogues : [];
  if (!analogues.length) return `<div class="oi-empty-note">No same-company or same-sector analogue is available for this event.</div>`;
  return `<div class="oi-analogues">${analogues.map(analogue => `<article class="oi-analogue">
    <header><div><span class="kicker">${esc(String(analogue.classification || "analogue").replaceAll("_", " "))}</span><h4>${esc(analogue.symbol || "Unknown symbol")}</h4></div><span class="pill">${esc(analogue.event_id || "event unknown")}</span></header>
    <div class="oi-analogue-meta"><span>Event date ${benchmarkDate(analogue.effective_date)}</span><span>Relation ${esc(String(analogue.classification || "unknown").replaceAll("_", " "))}</span></div>
    <div class="oi-analogue-returns">${BENCHMARK_HORIZONS.map(horizon => {
      const outcome = (analogue.outcomes || {})[horizon] || {};
      return `<div><span>${esc(horizon)}</span><b>${benchmarkReturn(outcome.return_pct)}</b><small>endpoint ${benchmarkDate(outcome.endpoint_date)}${outcome.reason ? ` · ${esc(outcome.reason)}` : ""}</small></div>`;
    }).join("")}</div>
  </article>`).join("")}</div>`;
}

function renderBenchmarkAggregate(study) {
  const aggregate = study.analogue_aggregate || {};
  return `<div class="oi-aggregate-grid">${BENCHMARK_HORIZONS.map(horizon => {
    const row = aggregate[horizon] || {};
    const statistic = row.mean_return_pct == null ? "Unknown — awaiting sourced inputs" : pct(row.mean_return_pct);
    return `<div><span>${esc(horizon)} aggregate</span><b>${statistic}</b><small>sample n ${esc(row.n ?? "unknown")} · ${esc(row.status || "unknown")}${row.reason ? ` · ${esc(row.reason)}` : ""}</small></div>`;
  }).join("")}</div>`;
}

function renderHistoricalBenchmarks(r, events) {
  const studies = Array.isArray(r.event_studies) ? r.event_studies : [];
  if (!studies.length) {
    return `<section class="oi-section oi-benchmark-section"><header class="oi-section-head"><div><span class="kicker">Historical benchmark</span><h3>Simple price-return context</h3></div></header><div class="empty oi-empty">No historical benchmark study is available for these operating events.</div></section>`;
  }
  const eventById = new Map(events.map(event => [event.event_id, event]));
  return `<section class="oi-section oi-benchmark-section"><header class="oi-section-head"><div><span class="kicker">Historical benchmark</span><h3>Descriptive, not causal</h3></div><span class="pill">${esc(studies.length)} stud${studies.length === 1 ? "y" : "ies"}</span></header>
    <p class="section-note">Raw simple price-return methodology. These rows describe what happened after dated events; they do not attribute causality and are not advice.</p>
    <div class="oi-benchmark-list">${studies.map(study => {
      const event = eventById.get(study.event_id);
      const baseline = study.baseline || {};
      const limitations = Array.isArray(study.limitations) ? study.limitations : [];
      return `<article class="oi-benchmark-card" aria-labelledby="study-${esc(study.study_id || study.event_id || "unknown")}">
        <header class="oi-card-head"><div><span class="oi-type oi-type-derived-fact">Historical Benchmark</span><span class="pill">${esc(study.event_type || event?.event_type || "event")}</span><h3 id="study-${esc(study.study_id || study.event_id || "unknown")}">${esc(short(event?.description || study.event_id || "Benchmark study", 170))}</h3></div><span class="oi-confidence">descriptive, not causal</span></header>
        <div class="oi-benchmark-meta"><div><span>Event</span><b>${esc(study.event_id || "unknown")}</b></div><div><span>Event date</span><b>${benchmarkDate(study.effective_date || event?.effective_date)}</b></div><div><span>Data cutoff</span><b>${benchmarkDate(study.data_cutoff)}</b></div><div><span>Baseline</span><b>${benchmarkDate(baseline.selected_date)}</b><small>${esc(baseline.status || "unknown")}${baseline.reason ? ` · ${esc(baseline.reason)}` : ""}</small></div></div>
        ${renderBenchmarkOutcomes(study)}
        <div class="oi-provenance"><span class="kicker">Provenance</span>${benchmarkProvenance(baseline.provenance)}${benchmarkProvenance(study.kse100_relative?.provenance)}</div>
        <div class="oi-benchmark-subgrid"><section><span class="kicker">Analogues</span>${renderBenchmarkAnalogues(study)}</section><section><span class="kicker">Aggregate sample</span>${renderBenchmarkAggregate(study)}</section></div>
        <div class="oi-limitations"><span class="kicker">Limitations</span>${limitations.length ? `<ul>${limitations.map(item => `<li>${esc(String(item).replaceAll("_", " "))}</li>`).join("")}</ul>` : `<p>No benchmark limitation flag is attached.</p>`}</div>
      </article>`;
    }).join("")}</div>
  </section>`;
}

function renderOperatingIntelligence(r) {
  const events = Array.isArray(r.operating_events) ? r.operating_events : [];
  const graph = r.driver_graph || {};
  const scenarios = Array.isArray(r.impact_scenarios) ? r.impact_scenarios : [];
  const graphFlags = Array.isArray(graph.quality_flags) ? graph.quality_flags : [];
  const supported = Boolean(graph.sector && Array.isArray(graph.drivers) && graph.drivers.length && !graphFlags.includes("sector_model_not_in_wave_1"));
  const knownDrivers = new Set((graph.drivers || []).map(driver => String(driver)));
  const eventById = new Map(events.map(event => [event.event_id, event]));
  const grouped = new Map();
  scenarios.forEach(scenario => {
    const key = scenario.event_id || "unlinked";
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(scenario);
  });
  const eventCards = events.length ? events.map(event => {
    const eventDrivers = Array.isArray(event.affected_drivers) ? event.affected_drivers : [];
    const unmodeled = eventDrivers.filter(driver => !knownDrivers.has(String(driver)));
    const scenariosForEvent = grouped.get(event.event_id) || [];
    return `<article class="oi-event" aria-labelledby="oi-event-${esc(event.event_id || "unknown")}">
      <header class="oi-card-head"><div><span class="oi-type oi-type-${objectTypeClass(event.intelligence_type)}">${esc(objectTypeLabel(event.intelligence_type))}</span><span class="pill">${esc(event.event_type || "event")}${event.event_subtype ? ` · ${esc(event.event_subtype)}` : ""}</span><h3 id="oi-event-${esc(event.event_id || "unknown")}">${esc(short(event.description || "Operating event", 180))}</h3></div><span class="oi-confidence">confidence ${confidenceValue(event.confidence)}</span></header>
      <div class="oi-facts"><div><span>Effective</span><b>${unknownValue(event.effective_date, "Unknown")}</b></div><div><span>Detected</span><b>${unknownValue(event.detected_at, "Unknown")}</b></div><div><span>Source quality</span><b>Level ${unknownValue(event.source_quality_level, "Unknown")}</b></div><div><span>Quality flags</span><b>${listValue(event.quality_flags, "None")}</b></div></div>
      <p class="oi-description">${esc(event.description || "No event description supplied.")}</p>
      ${unmodeled.length ? `<p class="oi-warning">Unmodeled driver: ${listValue(unmodeled)}. No causal effect is measured.</p>` : ""}
      ${operatingEvidence(event.evidence || (event.source_url ? [{ document_id: "document unknown", page: null, text: event.description, source_url: event.source_url }] : []))}
      <div class="oi-event-scenarios"><span class="kicker">Scenario links</span><span>${esc(scenariosForEvent.length)} scenario${scenariosForEvent.length === 1 ? "" : "s"} attached</span></div>
    </article>`;
  }).join("") : `<div class="empty oi-empty">No operating events are available in the retained file.</div>`;

  const driverSection = supported ? `<div class="oi-driver-status"><span class="pill good">Supported sector model</span><span>${esc(graph.sector)} · declarative only</span></div>
    <div class="oi-driver-list">${(graph.drivers || []).map(driver => `<span class="pill">${esc(driver)}</span>`).join("")}</div>
    <div class="oi-edge-list">${(graph.edges || []).length ? graph.edges.map(edge => `<div class="oi-edge"><span>${esc(edge.from || "Unknown driver")}</span><b>→</b><span>${esc(edge.statement_line || "Unknown statement line")}</span><b>→</b><span>${esc(edge.to || "Unknown output")}</span><em>Declarative map / hypothesis</em></div>`).join("") : `<div class="oi-empty-note">No directed driver edges are available.</div>`}</div>`
    : `<div class="empty oi-empty">Sector model unsupported or unmodeled for this company. Driver hypotheses are not available.</div>`;

  const scenarioSection = scenarios.length ? [...new Set([...events.map(event => event.event_id), ...scenarios.map(scenario => scenario.event_id)])].filter(Boolean).map(eventId => {
    const event = eventById.get(eventId);
    const cards = grouped.get(eventId) || [];
    if (!cards.length) return "";
    return `<section class="oi-scenario-group"><header><div><span class="kicker">Operating event</span><h3>${esc(short(event?.description || eventId, 140))}</h3></div><span class="pill">${esc(event?.event_id || eventId)}</span></header><div class="oi-scenarios">${cards.map(scenario => `<article class="oi-scenario oi-${esc(String(scenario.scenario || "scenario").toLowerCase())}"><header class="oi-card-head"><div><span class="oi-type oi-type-scenario">Scenario</span><h4>${esc(scenario.scenario || "Scenario")}</h4></div><b>${probabilityValue(scenario.probability)}</b></header><div class="oi-facts"><div><span>Affected drivers</span><b>${listValue(scenario.assumptions?.affected_drivers)}</b></div><div><span>Required inputs</span><b>${listValue(scenario.assumptions?.required_inputs)}</b></div><div><span>Missing inputs</span><b>${listValue(scenario.assumptions?.missing_inputs)}</b></div><div><span>Timing</span><b>${unknownValue(scenario.timing?.effective_date, "Unknown")} · lag ${unknownValue(scenario.timing?.expected_lag, "Unknown")}</b></div><div><span>Confidence</span><b>${confidenceValue(scenario.confidence)}</b></div><div><span>Impact status</span><b>${unknownValue(scenario.impact_status, "Unknown")}</b></div><div><span>Quality flags</span><b>${listValue(scenario.quality_flags, "None")}</b></div></div><div class="oi-impact-grid">${[["Revenue", scenario.revenue_impact], ["EBITDA", scenario.ebitda_impact], ["EPS", scenario.eps_impact], ["FCF", scenario.fcf_impact], ["Valuation", scenario.valuation_impact]].map(([label, value]) => `<div><span>${label} impact</span><b>${operatingImpact(value)}</b></div>`).join("")}</div>${operatingEvidence(scenario.evidence)}</article>`).join("")}</div></section>`;
  }).join("") : `<div class="empty oi-empty">No scenarios are available. Scenario synthesis remains paused until sourced inputs are sufficient.</div>`;

  return `<section class="panel span9 oi-shell"><button type="button" class="overview-back-button" data-research-route="directory_intelligence">Intelligence workspace</button><span class="kicker">Operating intelligence</span><h2>Observation → event → driver map → scenario</h2><p class="section-note">Observation/report becomes an operating event, then a declarative driver hypothesis, then Bear/Base/Bull scenarios. Research only — not advice. Null impacts remain unknown; no values are fabricated.</p>${renderCementOperatingSeries(r)}${renderCementHistoricalReconciliation(r)}<section class="oi-section"><header class="oi-section-head"><div><span class="kicker">Operating events</span><h3>Evidence-linked observations</h3></div><span class="pill">${esc(events.length)} event${events.length === 1 ? "" : "s"}</span></header><div class="oi-events">${eventCards}</div></section><section class="oi-section"><header class="oi-section-head"><div><span class="kicker">Driver map</span><h3>Sector model and directed hypotheses</h3></div></header>${driverSection}</section><section class="oi-section"><header class="oi-section-head"><div><span class="kicker">Impact scenarios</span><h3>Bear / Base / Bull by operating event</h3></div></header>${scenarioSection}</section>${renderHistoricalBenchmarks(r, events)}</section>`;
}

function conditionalText(value, label = "unknown") {
  return value == null || value === "" ? label : esc(value);
}

function conditionalList(values, empty = "none emitted") {
  if (!Array.isArray(values) || !values.length) return empty;
  return values.map(value => esc(String(value).replaceAll("_", " "))).join(", ");
}

function conditionalCandidateLabel(candidate) {
  return conditionalText(candidate?.candidate_id || candidate?.event_id || candidate?.id, "candidate id unknown");
}

function renderConditionalCandidates(label, candidates) {
  const rows = Array.isArray(candidates) ? candidates : [];
  if (!rows.length) return `<section><h4>${esc(label)}</h4><div class="conditional-empty">No exact ${esc(label.toLowerCase())} candidate emitted.</div></section>`;
  return `<section><h4>${esc(label)}</h4><div class="conditional-candidates">${rows.map(candidate => {
    const href = safeHref(candidate?.source_url);
    const date = candidate?.effective_date || candidate?.event_date || candidate?.date || null;
    const classification = candidate?.classification || candidate?.event_class || candidate?.event_type || "class unknown";
    const title = candidate?.description || candidate?.context || candidate?.event_subtype || classification;
    return `<article>
      <header><b>${conditionalCandidateLabel(candidate)}</b><span>${conditionalText(candidate?.symbol, "symbol unknown")}</span></header>
      <div><span>Date</span><b>${conditionalText(date, "date unknown")}</b></div>
      <div><span>Class</span><b>${conditionalText(String(classification).replaceAll("_", " "), "class unknown")}</b></div>
      <p>${esc(short(title, 130))}</p>
      ${href ? `<a href="${href}" target="_blank" rel="noopener">source URL</a>` : `<small>No source URL emitted.</small>`}
    </article>`;
  }).join("")}</div></section>`;
}

function renderConditionalEvidenceSummary(summary) {
  const source = summary && typeof summary === "object" && !Array.isArray(summary) ? summary : {};
  const candidateCounts = source.candidate_counts && typeof source.candidate_counts === "object" ? source.candidate_counts : {};
  const matureCounts = source.mature_horizon_counts && typeof source.mature_horizon_counts === "object" ? source.mature_horizon_counts : {};
  return `<section><h4>Candidate evidence</h4><div class="conditional-policy">
    <span>Evidence status<b>${conditionalText(source.evidence_status, "unknown")}</b></span>
    <span>Same company exact<b>${conditionalText(candidateCounts.same_company_exact, "0")}</b></span>
    <span>Same sector exact<b>${conditionalText(candidateCounts.same_sector_exact, "0")}</b></span>
    <span>Latest prior candidate<b>${conditionalText(source.latest_prior_candidate_date, "none")}</b></span>
    <span>Mature horizons<b>${esc(Object.entries(matureCounts).map(([horizon, count]) => `${horizon}: ${count}`).join(", ") || "none")}</b></span>
  </div><p class="section-note">${esc(source.limitation || "Descriptive evidence only; no causal or forecast interpretation is emitted.")}</p></section>`;
}

function conditionalStats(stats, n) {
  if (!stats || typeof stats !== "object" || Number(n) < 3) return `<div class="conditional-empty">Numeric stats suppressed until n is at least 3.</div>`;
  const rows = Object.entries(stats).filter(([, value]) => value !== null && value !== undefined && value !== "");
  if (!rows.length) return `<div class="conditional-empty">No numeric stats emitted for this aggregate.</div>`;
  return `<div class="conditional-stats">${rows.map(([key, value]) => `<span>${esc(key.replaceAll("_", " "))}<b>${typeof value === "number" ? esc(fmt(value, 2)) : esc(value)}</b></span>`).join("")}</div>`;
}

function renderConditionalHorizons(aggregates) {
  const entries = aggregates && typeof aggregates === "object" && !Array.isArray(aggregates) ? Object.entries(aggregates) : [];
  if (!entries.length) return `<div class="conditional-empty">No horizon aggregate emitted.</div>`;
  return `<div class="conditional-horizons">${entries.map(([horizon, row]) => {
    const n = row?.n;
    return `<article>
      <header><b>${esc(horizon)}</b><span>${conditionalText(row?.status, "status unknown")}</span></header>
      <div class="conditional-horizon-meta">
        <span>n<b>${conditionalText(n, "unknown")}</b></span>
        <span>Reason<b>${conditionalText(row?.reason, "none emitted")}</b></span>
      </div>
      ${conditionalStats(row?.stats, n)}
    </article>`;
  }).join("")}</div>`;
}

function renderConditionalBlockedStates(blocked) {
  const source = blocked && typeof blocked === "object" && !Array.isArray(blocked) ? blocked : {};
  const keys = ["peer", "international", "financial", "causal"];
  return `<div class="conditional-blocked" aria-label="Blocked benchmark states">${keys.map(key => {
    const row = source[key] || source[`${key}_benchmark`] || source[`${key}_state`] || {};
    const status = typeof row === "string" ? row : (row.status || "blocked");
    const reason = typeof row === "string" ? "" : (row.reason || row.policy || "");
    return `<span>${esc(key)}<b>${conditionalText(status, "blocked")}</b>${reason ? `<small>${esc(reason)}</small>` : ""}</span>`;
  }).join("")}</div>`;
}

function renderConditionalPolicy(policy) {
  const source = policy && typeof policy === "object" && !Array.isArray(policy) ? policy : {};
  const rows = Object.entries(source);
  if (!rows.length) return `<div class="conditional-empty">No matching policy emitted.</div>`;
  return `<div class="conditional-policy">${rows.map(([key, value]) => `<span>${esc(key.replaceAll("_", " "))}<b>${Array.isArray(value) ? conditionalList(value) : conditionalText(String(value).replaceAll("_", " "))}</b></span>`).join("")}</div>`;
}

function renderConditionalBenchmarks(r) {
  const conditional = r.conditional_benchmarks || {};
  const benchmarks = Array.isArray(conditional.benchmarks) ? conditional.benchmarks : [];
  const limitations = Array.isArray(conditional.limitations) ? conditional.limitations : [];
  const statusCounts = benchmarks.reduce((acc, benchmark) => {
    const key = benchmark.status || "unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const statusStrip = Object.keys(statusCounts).length
    ? Object.entries(statusCounts).map(([status, count]) => `<span class="pill">${esc(status)} ${esc(count)}</span>`).join("")
    : `<span class="muted">No conditional benchmark status emitted.</span>`;
  const cards = benchmarks.length ? benchmarks.map(benchmark => {
    const target = benchmark.target_event || benchmark.event || {};
    const context = benchmark.context || benchmark.target_context || {};
    const matching = benchmark.matching_policy || benchmark.policy || {};
    const candidates = benchmark.candidates || {};
    const aggregates = benchmark.horizon_aggregates || benchmark.aggregates || {};
    return `<article class="conditional-card" aria-labelledby="conditional-${esc(benchmark.benchmark_id || target.event_id || "unknown")}">
      <header>
        <div><span class="pill">${conditionalText(benchmark.status, "status unknown")}</span><h3 id="conditional-${esc(benchmark.benchmark_id || target.event_id || "unknown")}">${esc(short(target.description || benchmark.description || target.event_id || "Conditional benchmark", 170))}</h3></div>
        <b>${conditionalText(benchmark.benchmark_id || target.event_id, "benchmark id unknown")}</b>
      </header>
      <div class="conditional-event">
        <div><span>Target event</span><b>${conditionalText(target.event_id || benchmark.event_id, "event id unknown")}</b></div>
        <div><span>Event date</span><b>${conditionalText(target.effective_date || benchmark.effective_date, "date unknown")}</b></div>
        <div><span>Event class</span><b>${conditionalText(target.event_class || target.classification || target.event_type || benchmark.event_type, "class unknown")}</b></div>
        <div><span>Context</span><b>${conditionalList(context.conditions || benchmark.conditions, conditionalText(context.summary || benchmark.context_summary, "conditions unknown"))}</b></div>
      </div>
      <section><h4>Matching policy</h4>${renderConditionalPolicy(matching)}</section>
      <div class="conditional-candidate-grid">
        ${renderConditionalCandidates("Same company exact", candidates.same_company_exact || benchmark.same_company_exact)}
        ${renderConditionalCandidates("Same sector exact", candidates.same_sector_exact || benchmark.same_sector_exact)}
      </div>
      ${renderConditionalEvidenceSummary(benchmark.candidate_evidence_summary)}
      <section><h4>Horizon aggregates</h4>${renderConditionalHorizons(aggregates)}</section>
      ${renderConditionalBlockedStates(benchmark.blocked_states || conditional.blocked_states)}
    </article>`;
  }).join("") : `<div class="empty">No conditional historical benchmark row was emitted for ${esc(r.symbol)}.</div>`;
  return `<section class="panel span9 conditional-shell" aria-labelledby="conditionalTitle">
    <button type="button" class="overview-back-button" data-research-route="directory_ownership">Ownership &amp; Peers workspace</button><span class="kicker">Conditional historical benchmarks</span><h2 id="conditionalTitle">Matched event context, descriptive only</h2>
    <p class="section-note">Read-only backend output from conditional_benchmarks. The browser displays exact candidate IDs, dates, classes, suppressed aggregate states and backend-supplied stats only; it does not match events, calculate benchmarks, infer causality, forecast, value the company, or provide advice.</p>
    <div class="conditional-summary">
      <div><span>Symbol</span><b>${conditionalText(conditional.symbol || r.symbol, "unknown")}</b></div>
      <div><span>Status</span><b>${conditionalText(conditional.status, "unknown")}</b></div>
      <div><span>Benchmarks</span><b>${esc(benchmarks.length)}</b></div>
      <div><span>Policy</span><b>${Object.keys(conditional.policy || {}).length ? "emitted" : "unknown"}</b></div>
    </div>
    <div class="conditional-status-strip" aria-label="Conditional benchmark statuses">${statusStrip}</div>
    <section class="conditional-section"><h3>Policy and limitations</h3>${renderConditionalPolicy(conditional.policy)}<div class="conditional-limitations">${limitations.length ? `<ul>${limitations.map(item => `<li>${esc(String(item).replaceAll("_", " "))}</li>`).join("")}</ul>` : `<p>No limitation flag is attached.</p>`}</div></section>
    <div class="conditional-grid">${cards}</div>
  </section>`;
}

function causalPolicyStatus(policy, key) {
  return esc(policy?.[key] || "blocked");
}

function renderCausalEventRefs(refs) {
  const items = Array.isArray(refs) ? refs : [];
  if (!items.length) return `<div class="causal-empty">No official event ref attached.</div>`;
  return `<div class="causal-refs">${items.map(ref => {
    const href = safeHref(ref?.source_url);
    const label = `${ref?.event_id || "event unknown"} · ${ref?.event_type || "type unknown"} · ${ref?.effective_date || "date unknown"}`;
    return href
      ? `<a href="${href}" target="_blank" rel="noopener">${esc(label)}</a>`
      : `<span>${esc(label)}</span>`;
  }).join("")}</div>`;
}

function renderCausalStudyRefs(refs) {
  const items = Array.isArray(refs) ? refs : [];
  if (!items.length) return `<div class="causal-empty">No strict event-study ref attached.</div>`;
  return `<div class="causal-refs">${items.map(ref => `<span>${esc(ref?.study_id || "study unknown")} · event ${esc(ref?.event_id || "unknown")} · no-lookahead ${esc(ref?.strict_no_lookahead === true ? "true" : "false")} · baseline ${esc(ref?.baseline_status || "unknown")}</span>`).join("")}</div>`;
}

function renderCausalFoundations(r) {
  const foundations = r.causal_foundations || {};
  const rows = Array.isArray(foundations.causal_rows) ? foundations.causal_rows : [];
  const coverage = foundations.coverage || {};
  const statusCounts = rows.reduce((acc, row) => {
    const key = row.evidence_status || "unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const statusStrip = Object.keys(statusCounts).length
    ? Object.entries(statusCounts).map(([status, count]) => `<span class="pill">${esc(status)} ${esc(count)}</span>`).join("")
    : `<span class="muted">No categorical evidence status emitted.</span>`;
  const cards = rows.length ? rows.map(row => {
    const policy = row.policy || {};
    return `<article class="causal-card" aria-labelledby="causal-${esc(row.causal_id || row.edge_id || "unknown")}">
      <header>
        <div><span class="pill">${esc(row.evidence_status || "unknown")}</span><h3 id="causal-${esc(row.causal_id || row.edge_id || "unknown")}">${esc(row.driver || "unknown driver")} → ${esc(row.target || "unknown target")}</h3></div>
        <b>${esc(row.causal_id || "causal id unknown")}</b>
      </header>
      <div class="causal-edge"><span>${esc(row.driver || "unknown driver")}</span><b>→</b><span>${esc(row.target || "unknown target")}</span></div>
      <div class="causal-facts">
        <div><span>Statement line</span><b>${esc(row.statement_line || "unknown")}</b></div>
        <div><span>Unit</span><b>${esc(row.unit || "unknown")}</b></div>
        <div><span>Edge basis</span><b>${esc(row.edge_basis || "unknown")}</b></div>
        <div><span>Edge ID</span><b>${esc(row.edge_id || "unknown")}</b></div>
      </div>
      <section><h4>Official event refs</h4>${renderCausalEventRefs(row.event_refs)}</section>
      <section><h4>Event-study refs</h4>${renderCausalStudyRefs(row.event_study_refs)}</section>
      <section><h4>Next data requirement</h4><p>${esc(row.next_data_requirement || "unknown")}</p></section>
      <div class="causal-policy" aria-label="Blocked downstream outputs">
        <span>Numeric impact<b>${causalPolicyStatus(policy, "numeric_impact")}</b></span>
        <span>Forecast<b>${causalPolicyStatus(policy, "forecast")}</b></span>
        <span>Valuation<b>${causalPolicyStatus(policy, "valuation")}</b></span>
      </div>
    </article>`;
  }).join("") : `<div class="empty">No causal foundation rows were emitted for ${esc(r.symbol)}.</div>`;
  return `<section class="panel span9 causal-shell" aria-labelledby="causalTitle">
    <button type="button" class="overview-back-button" data-research-route="directory_ownership">Ownership &amp; Peers workspace</button><span class="kicker">Causal driver evidence map</span><h2 id="causalTitle">Driver evidence, not impact estimates</h2>
    <p class="section-note">Read-only backend output from causal_foundations. The browser displays categorical evidence, exact refs and blocked downstream policy only; it does not estimate impact, forecast, value the company, or turn this into advice.</p>
    <div class="causal-summary">
      <div><span>Sector model</span><b>${esc(foundations.sector || r.sector || "unknown")}</b></div>
      <div><span>Driver edges</span><b>${esc(coverage.driver_edge_count ?? rows.length)}</b></div>
      <div><span>Causal rows</span><b>${esc(coverage.causal_row_count ?? rows.length)}</b></div>
      <div><span>Observed event rows</span><b>${esc(coverage.observed_event_rows ?? 0)}</b></div>
      <div><span>Strict study rows</span><b>${esc(coverage.strict_study_rows ?? 0)}</b></div>
    </div>
    <div class="causal-status-strip" aria-label="Categorical evidence statuses">${statusStrip}</div>
    <div class="causal-grid">${cards}</div>
  </section>`;
}

function overviewObjectItems(r) {
  const counts = (r.company_brain?.intelligence_objects || []).reduce((out, item) => {
    const key = objectTypeLabel(item.type);
    out[key] = (out[key] || 0) + 1;
    return out;
  }, {});
  return Object.entries(counts).map(([label, value]) => ({ label, value, unit: "objects" })).sort((a, b) => b.value - a.value).slice(0, 6);
}

function overviewDomainItems(r) {
  const preferred = ["segments", "products", "facilities", "capacity", "geography", "subsidiaries", "projects", "customers"];
  return preferred.map(name => {
    const domain = brainDomain(r.company_brain || {}, name);
    return { label: name.replaceAll("_", " "), value: (domain.object_refs || []).length, unit: "refs", status: domain.status || "unknown" };
  }).filter(item => item.value > 0).sort((a, b) => b.value - a.value).slice(0, 6);
}

function overviewActivityItems(r) {
  const watch = r.explainability?.monitoring?.what_to_watch || [];
  const operating = Array.isArray(r.operating_events) ? r.operating_events : [];
  const source = watch.length ? watch.map(item => ({ date: item.date, label: item.title })) : operating.map(item => ({ date: item.effective_date || item.detected_at, label: item.event_subtype || item.event_type }));
  const seen = new Set();
  return source.filter(item => item.date && item.label).map(item => ({ ...item, label: humanActivityLabel(item.label) })).filter(item => {
    const key = `${String(item.date).slice(0, 10)}|${item.label}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 8);
}

function overviewRouteCard(route, kicker, title, copy, chart, icon) {
  return `<article class="overview-dashboard-card" data-card-route="${esc(route)}"><header class="overview-card-heading"><span class="overview-card-icon" aria-hidden="true"><iconify-icon icon="${esc(icon)}"></iconify-icon></span><div><span class="kicker">${esc(kicker)}</span><h3>${esc(title)}</h3></div><span class="ci-card-route-pill">${esc(route)}</span></header>${chart}<p>${esc(copy)}</p><button type="button" class="overview-route-button" data-research-route="${esc(route)}" aria-label="Open ${esc(title)} research view">Open ${esc(title)}<iconify-icon icon="lucide:arrow-right" aria-hidden="true"></iconify-icon></button></article>`;
}

function renderOverviewDashboard(r) {
  const objects = overviewObjectItems(r);
  const domains = overviewDomainItems(r);
  const activity = overviewActivityItems(r);
  const objectChart = objects.length
    ? ciChart("assumptions", { status: "available", label: "Typed evidence in the company file", items: objects, comparable: true, visible_summary: true })
    : ciBlockedChart("blocked_no_typed_objects", "No typed evidence objects are retained", ["Typed evidence", "Source binding"]);
  const domainChart = domains.length
    ? ciChart("assumptions", { status: "available", label: "Business-profile coverage by retained reference count", items: domains, comparable: true, visible_summary: true })
    : ciBlockedChart("blocked_no_business_domain_refs", "Business-profile coverage is not retained", ["Company Brain domain", "Typed source reference"]);
  const activityChart = activity.length
    ? ciChart("timeline", { status: "available", label: "Latest retained company activity", items: activity })
    : ciBlockedChart("blocked_no_dated_activity", "No dated company activity is retained", ["Dated official source", "Classified event"]);
  return `<section class="panel span9 overview-dashboard-shell" aria-labelledby="overviewDashboardTitle">
    <header class="overview-dashboard-header"><div><span class="kicker">Overview workspace</span><h2 id="overviewDashboardTitle">Start with the company, then follow the evidence</h2><p>Use the snapshot for the research position today. Use the profile to understand what the company actually does and which parts of the business file are still thin.</p></div><span class="overview-dashboard-symbol">${esc(r.symbol)}</span></header>
    <div class="overview-dashboard-grid">
      ${overviewRouteCard("snapshot", "Research position", "Investor Snapshot", "A fast, source-aware view of the company, recent change, evidence mix, and the gates still holding back formal conclusions.", objectChart, "lucide:scan-search")}
      ${overviewRouteCard("overview", "Company understanding", "Company Profile", "The issuer’s stated business, corporate identity, operating-domain coverage, and the retained references behind that understanding.", domainChart, "lucide:building-2")}
      <article class="overview-dashboard-card overview-dashboard-wide"><header class="overview-card-heading"><span class="overview-card-icon" aria-hidden="true"><iconify-icon icon="lucide:history"></iconify-icon></span><div><span class="kicker">Evidence pulse</span><h3>What has entered the file recently</h3></div></header>${activityChart}<div class="overview-activity-list" aria-label="Recent retained company activity">${activity.slice(0, 5).map(item => `<span><time>${esc(String(item.date).slice(0, 10))}</time><b>${esc(item.label)}</b></span>`).join("")}</div><p>Dated activity is shown as retained. A mark means a source or monitored record exists; it does not imply financial impact.</p></article>
    </div>
  </section>`;
}

function renderCompanyProfile(r, ctx) {
  const { f, v, p, liq, source, inc } = ctx;
  const domains = ["segments", "products", "facilities", "capacity", "geography", "subsidiaries", "projects", "customers"];
  const coverage = overviewDomainItems(r);
  const coverageChart = coverage.length
    ? ciChart("assumptions", { status: "available", label: "Retained business-domain reference counts", items: coverage, comparable: true, visible_summary: true })
    : ciBlockedChart("blocked_no_business_domain_refs", "The business profile is waiting for typed source references", ["Issuer description", "Company Brain domain", "Typed source reference"]);
  return `<section class="panel span9 overview-detail-shell profile-detail" aria-labelledby="companyProfileTitle">
    <header class="overview-detail-header"><div><span class="kicker">Company profile</span><h2 id="companyProfileTitle">What ${esc(r.symbol)} is and how it operates</h2><p>${esc(p.business_description || "No sourced business description is retained.")}</p></div><button type="button" class="overview-back-button" data-research-route="directory_overview">Overview workspace</button></header>
    <div class="profile-fact-grid">
      <article><span class="overview-fact-label"><iconify-icon icon="lucide:landmark" aria-hidden="true"></iconify-icon>Incorporated</span><b>${esc(inc)}</b><small>Reported issuer identity</small></article>
      <article><span class="overview-fact-label"><iconify-icon icon="lucide:factory" aria-hidden="true"></iconify-icon>Sector</span><b>${esc(r.sector || "unknown")}</b><small>Company Intelligence classification</small></article>
      <article><span class="overview-fact-label"><iconify-icon icon="lucide:bar-chart-3" aria-hidden="true"></iconify-icon>Indices</span><b>${esc((r.indices || []).join(", ") || "unknown")}</b><small>Retained market membership</small></article>
      <article><span class="overview-fact-label"><iconify-icon icon="lucide:file-check-2" aria-hidden="true"></iconify-icon>Official source</span><b>${source}</b><small>${p.fetched ? `Fetched ${esc(p.fetched)}` : "Fetch date unknown"}${p.stale ? " · retained row is stale" : ""}</small></article>
    </div>
    <div class="overview-detail-grid">
      <article class="overview-evidence-card"><header><span class="kicker">Business-file coverage</span><h3>Where the retained profile is deep—and where it is still thin</h3></header>${coverageChart}<p>Lengths compare counts of typed references only. They do not score business quality or investment merit.</p></article>
      <article class="overview-plain-card"><header><span class="kicker">Market context</span><h3>Numbers already on file</h3></header><div class="profile-market-list">
        <span>Market capitalisation <b>${esc(f.market_cap || "unknown")}</b></span>
        <span>Reported EPS <b>${esc(f.eps || "unknown")}</b></span>
        <span>Price / earnings <b>${esc(f.pe || "unknown")}</b></span>
        <span>Forward P/E <b>${esc(f.forward_pe || "unknown")}</b></span>
        <span>Existing fair-value read <b>${esc(v.verdict || "unknown")}${v.mispricing_pct == null ? "" : ` · ${esc(pct(v.mispricing_pct))}`}</b></span>
      </div><p>These are ordinary retained values. The profile does not turn them into a forecast or recommendation.</p></article>
    </div>
    <section class="profile-domain-section"><header><span class="kicker">Operating map</span><h3>Business areas in the Company Brain</h3></header><div class="profile-domain-grid">${domains.map(name => {
      const domain = brainDomain(r.company_brain || {}, name);
      const count = (domain.object_refs || []).length;
      return `<article class="profile-domain-card status-${esc(domain.status || "unknown")}"><span>${esc(name.replaceAll("_", " "))}</span><b>${esc(ciHumanStatus(domain.status))}</b><small>${esc(count)} typed reference${count === 1 ? "" : "s"}${domain.reason ? ` · ${esc(String(domain.reason).replaceAll("_", " "))}` : ""}</small></article>`;
    }).join("")}</div></section>
    <section class="profile-reference-section"><header><span class="kicker">Source-linked detail</span><h3>Selected operating references</h3></header>${["products", "facilities", "capacity", "geography", "subsidiaries", "projects"].map(name => `<section><h4>${esc(name.replaceAll("_", " "))}</h4>${renderDomainRefs(r, name, `No retained ${name.replaceAll("_", " ")} reference is available.`)}</section>`).join("")}</section>
    <footer class="overview-detail-footer"><span>Research only · no execution</span><span>Missing business knowledge remains visible as unknown</span></footer>
  </section>`;
}

function renderDocs(r) {
  const docs = [...(r.news || []), ...(r.documents || [])];
  if (!docs.length) return `<p>No tagged documents or high-impact tape notes in the current slice.</p>`;
  return docs.map(d => `<div class="docrow">
    <b>${esc(d.date || "")} ${esc(d.headline || d.title || "Document")}</b>
    <span>${esc(d.type || (d.impact ? `impact ${d.impact}` : "news"))}${d.url ? `, <a href="${esc(d.url)}" target="_blank" rel="noopener">source</a>` : ""}</span>
  </div>`).join("");
}

function evidenceLink(item) {
  if (!item) return "";
  const page = Number(item.page) > 0 ? `page ${Number(item.page)}` : "source excerpt";
  const excerpt = item.text ? `<blockquote>${esc(item.text)}</blockquote>` : "";
  const link = item.source_url ? `<a href="${esc(item.source_url)}" target="_blank" rel="noopener">${page}</a>` : esc(page);
  return `<div class="evidence"><span>${link} · extracted evidence</span>${excerpt}</div>`;
}

function brainDomain(brain, name) {
  return brain?.domains?.[name] || { status: "unknown", object_refs: [] };
}

function brainObjectMap(brain) {
  return new Map((brain?.intelligence_objects || []).map(item => [item.id, item]));
}

function renderBrainRefObject(item) {
  if (!item) return `<article class="domain-ref missing"><h4>Missing typed object</h4><p>Company Brain references an object that is not present in this slice.</p></article>`;
  const refs = Array.isArray(item.evidence_refs) ? item.evidence_refs : [];
  const links = refs.length ? refs.slice(0, 3).map(ref => {
    const href = safeHref(ref.source_url);
    const page = ref.page ? `p.${esc(ref.page)}` : "source";
    const doc = ref.document_id || ref.doc_id || "document unknown";
    return href ? `<a href="${href}" target="_blank" rel="noopener">${esc(doc)} ${page}</a>` : `<span>${esc(doc)} ${page}</span>`;
  }).join("") : `<span>Evidence refs unavailable in this slice</span>`;
  return `<article class="domain-ref">
    <header><div><span class="oi-type oi-type-${objectTypeClass(item.type)}">${esc(objectTypeLabel(item.type))}</span><h4>${esc(item.source_id || item.id || "typed object")}</h4></div><b>${confidenceValue(item.confidence)}</b></header>
    <div class="domain-ref-meta">
      <span>Source product <b>${esc(String(item.source_product || "unknown").replaceAll("_", " "))}</b></span>
      <span>Available on <b>${esc(item.available_on || "unknown")}</b></span>
      <span>Object id <b>${esc(item.id || "unknown")}</b></span>
    </div>
    <div class="domain-ref-links">${links}</div>
  </article>`;
}

function renderDomainRefs(r, domainName, emptyText) {
  const brain = r.company_brain || {};
  const domain = brainDomain(brain, domainName);
  const objects = brainObjectMap(brain);
  const refs = Array.isArray(domain.object_refs) ? domain.object_refs : [];
  if (!refs.length) return `<div class="empty">${esc(emptyText || "Unknown — no typed Company Brain reference is available for this domain.")}</div>`;
  return `<div class="domain-ref-list">${refs.map(ref => renderBrainRefObject(objects.get(ref))).join("")}</div>`;
}

function renderCompanyDomainView(r, domainName, title, emptyText) {
  const domain = brainDomain(r.company_brain || {}, domainName);
  return `<section class="panel span9 company-domain-shell" aria-labelledby="domain-${esc(domainName)}">
    ${domainName === "catalysts" ? `<button type="button" class="overview-back-button" data-research-route="directory_strategy">Strategy workspace</button>` : ""}<span class="kicker">Company Brain domain</span><h2 id="domain-${esc(domainName)}">${esc(title)}</h2>
    <p class="section-note">Read-only Company Brain references. The browser displays existing typed objects and evidence refs only; missing knowledge stays unknown.</p>
    <div class="domain-status">
      <span>Status <b>${esc(domain.status || "unknown")}</b></span>
      <span>Typed references <b>${esc((domain.object_refs || []).length)}</b></span>
      <span>Reason <b>${esc(domain.reason || "none_emitted")}</b></span>
    </div>
    ${renderDomainRefs(r, domainName, emptyText)}
  </section>`;
}

function guidanceState(r) {
  return r.guidance_contradictions && typeof r.guidance_contradictions === "object" && !Array.isArray(r.guidance_contradictions)
    ? r.guidance_contradictions
    : null;
}

function guidanceObjects(state, domainName) {
  return (Array.isArray(state?.objects) ? state.objects : []).filter(item => item?.domain === domainName);
}

function renderGuidanceEvidence(evidence) {
  const href = safeHref(evidence?.source_url);
  const page = evidence?.page ? `p.${esc(evidence.page)}` : "page unknown";
  const doc = evidence?.document_id || "document unknown";
  const available = evidence?.available_on || "available-on unknown";
  const link = href ? `<a href="${href}" target="_blank" rel="noopener">${esc(doc)} ${page}</a>` : `<span>${esc(doc)} ${page}</span>`;
  return `<div class="domain-ref-links">${link}<span>${esc(available)}</span></div>`;
}

function renderGuidanceObject(obj) {
  return `<article class="domain-ref">
    <header><div><span class="oi-type oi-type-${objectTypeClass(obj.domain === "risks" ? "reported_fact" : "inference")}">${esc(obj.domain || "guidance")}</span><h4>${esc(obj.guidance_id || "guidance object")}</h4></div><b>${esc(obj.status || "unknown")}</b></header>
    <p>${esc(obj.statement || "Unknown — no statement emitted.")}</p>
    <div class="domain-ref-meta">
      <span>Modality <b>${esc(obj.modality || "unknown")}</b></span>
      <span>Topic key <b>${esc(obj.topic_key || "unknown")}</b></span>
      <span>Conflict key <b>${esc(obj.conflict_key || "unknown")}</b></span>
    </div>
    ${renderGuidanceEvidence(obj.evidence || {})}
  </article>`;
}

function renderGuidanceContradictions(state) {
  const rows = Array.isArray(state?.contradictions) ? state.contradictions : [];
  if (!rows.length) return `<div class="empty">No exact normalized-key contradictions were emitted.</div>`;
  return `<div class="domain-ref-list">${rows.map(row => `<article class="domain-ref">
    <header><div><span class="oi-type oi-type-inference">${esc(row.status || "conflict")}</span><h4>${esc(row.contradiction_id || "contradiction")}</h4></div><b>exact key</b></header>
    <div class="domain-ref-meta">
      <span>Conflict key <b>${esc(row.conflict_key || "unknown")}</b></span>
      <span>Objects <b>${esc((row.object_ids || []).join(" · ") || "none emitted")}</b></span>
      <span>Rule <b>${esc(row.match_rule || "unknown")}</b></span>
    </div>
  </article>`).join("")}</div>`;
}

function renderGuidanceDomainView(r, domainName, title, emptyText) {
  const state = guidanceState(r);
  if (!state) {
    return `<section class="panel span9 company-domain-shell" aria-labelledby="guidance-${esc(domainName)}">
      <button type="button" class="overview-back-button" data-research-route="directory_strategy">Strategy workspace</button><span class="kicker">Guidance & contradictions</span><h2 id="guidance-${esc(domainName)}">${esc(title)}</h2>
      <p class="section-note">Unavailable: the CI slice has not emitted guidance_contradictions for this company. The browser will not derive guidance, risks, contradictions, forecasts, valuation, or advice.</p>
      <div class="empty">Unavailable: not generated.</div>
    </section>`;
  }
  const objects = guidanceObjects(state, domainName);
  return `<section class="panel span9 company-domain-shell" aria-labelledby="guidance-${esc(domainName)}">
    <button type="button" class="overview-back-button" data-research-route="directory_strategy">Strategy workspace</button><span class="kicker">Guidance & contradictions</span><h2 id="guidance-${esc(domainName)}">${esc(title)}</h2>
    <p class="section-note">Read-only backend output from retained official evidence. Unknown stays unknown; the browser only displays emitted assertion objects and exact-key contradiction rows.</p>
    <div class="domain-status">
      <span>Status <b>${esc(state.status || "unknown")}</b></span>
      <span>${esc(title)} objects <b>${esc(objects.length)}</b></span>
      <span>Contradictions <b>${esc(state.contradiction_count ?? 0)}</b></span>
    </div>
    ${objects.length ? `<div class="domain-ref-list">${objects.map(renderGuidanceObject).join("")}</div>` : `<div class="empty">${esc(emptyText)} Status: ${esc(state.status || "unknown")}.</div>`}
    <section class="domain-subsection"><h3>Contradictions</h3>${renderGuidanceContradictions(state)}</section>
  </section>`;
}


function renderCompanyOperations(r) {
  return `<section class="company-route-stack">
    <button type="button" class="overview-back-button" data-research-route="directory_ownership">Ownership &amp; Peers workspace</button>
    ${renderCompanyDomainView(r, "operating_kpis", "Operating KPIs", "Unknown — no sourced operating KPI reference is available.")}
    ${renderOperatingIntelligence(r)}
  </section>`;
}

const FORMAL_ENGINE_LABELS = {
  financial_forecasts: "Financial forecast",
  formal_valuations: "Formal valuation",
  market_expectations: "Market expectations",
};

function humanEngineKey(value) {
  return String(value || "unknown").replaceAll("_", " ");
}

function formalEngineProduct(r, key) {
  const product = r?.[key];
  if (product && typeof product === "object" && !Array.isArray(product)) return product;
  return {
    symbol: r?.symbol,
    status: "blocked",
    reason: `${key}_not_emitted`,
    missing_requirements: [`${key}_not_emitted`],
    result: null,
    provenance: [],
    policy: { research_only: true, no_advice: true },
  };
}

function engineValue(value) {
  if (value == null || value === "") return "unknown";
  if (typeof value === "number" && Number.isFinite(value)) return fmt(value, 2);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "object") return short(JSON.stringify(value), 120);
  return value;
}

function renderFormalEngineResult(product) {
  const result = product?.result && typeof product.result === "object" && !Array.isArray(product.result)
    ? Object.entries(product.result)
    : [];
  if (!result.length) {
    const missing = Array.isArray(product?.missing_requirements) ? product.missing_requirements : [];
    return `<section class="forecast-readiness-section">
      <h3>Blocked inputs</h3>
      ${readinessList(missing, product?.reason || "No result emitted.")}
    </section>`;
  }
  return `<section class="forecast-readiness-section">
    <h3>Computed result</h3>
    <div class="baseline-table"><table><thead><tr><th>Field</th><th>Emitted value</th></tr></thead><tbody>
      ${result.map(([field, value]) => `<tr><td>${esc(humanEngineKey(field))}</td><td>${esc(engineValue(value))}</td></tr>`).join("")}
    </tbody></table></div>
  </section>`;
}

function renderFormalEngineProvenance(product) {
  const provenance = Array.isArray(product?.provenance) ? product.provenance : [];
  return `<section class="forecast-readiness-section">
    <h3>Provenance</h3>
    <div class="forecast-readiness-docs">${provenance.length ? provenance.slice(0, 8).map(ref => {
      const href = safeHref(ref.source_url);
      const label = ref.source_label || ref.source_id || ref.fact_id || ref.document_id || ref.metric || "source";
      const source = href
        ? `<a href="${href}" target="_blank" rel="noopener">${esc(label)}</a>`
        : `<span>${esc(label)}</span>`;
      const detail = [
        ref.metric ? humanEngineKey(ref.metric) : null,
        ref.record_type ? humanEngineKey(ref.record_type) : null,
        ref.period_end ? `period ${ref.period_end}` : null,
        ref.available_on ? `available ${ref.available_on}` : null,
      ].filter(Boolean).join(" · ");
      return `<article><b>${source}</b><span>${esc(ref.source_path || ref.document_id || "source path unavailable")}</span><small>${esc(detail || "No provenance detail emitted.")}</small></article>`;
    }).join("") : `<div class="empty">No provenance rows were emitted.</div>`}</div>
  </section>`;
}

function renderFormalEnginePolicy(product) {
  const policy = product?.policy && typeof product.policy === "object" && !Array.isArray(product.policy) ? product.policy : {};
  const entries = Object.entries(policy);
  return `<section class="forecast-readiness-section">
    <h3>Policy</h3>
    <div class="forecast-readiness-policy">
      ${entries.length ? entries.map(([key, value]) => `<span>${esc(humanEngineKey(key))}<b>${esc(engineValue(value))}</b></span>`).join("") : `<span>policy<b>not emitted</b></span>`}
    </div>
  </section>`;
}

function renderFormalEngineCard(r, key) {
  const product = formalEngineProduct(r, key);
  return `<section class="forecast-readiness-section">
    <h3>${esc(FORMAL_ENGINE_LABELS[key] || humanEngineKey(key))}</h3>
    <div class="blocked-grid">
      <span>Status <b>${esc(product.status || "unknown")}</b></span>
      <span>Formula <b>${esc(product.formula_id || "formula_id_not_emitted")}</b></span>
      <span>Reason <b>${esc(product.reason || (product.result ? "computed_result_emitted" : "reason_not_emitted"))}</b></span>
      <span>Result <b>${product.result ? "emitted" : "not emitted"}</b></span>
      <span>Missing inputs <b>${esc((product.missing_requirements || []).length)}</b></span>
      <span>Provenance <b>${esc((product.provenance || []).length)}</b></span>
    </div>
    ${renderFormalEngineResult(product)}
    ${renderFormalEngineProvenance(product)}
    ${renderFormalEnginePolicy(product)}
  </section>`;
}

function renderFormalEnginePanel(r, keys, kicker, title, note, titleId) {
  const products = keys.map(key => [key, formalEngineProduct(r, key)]);
  return `<section class="panel span9 forecast-readiness-shell" aria-labelledby="${esc(titleId)}">
    <span class="kicker">${esc(kicker)}</span><h2 id="${esc(titleId)}">${esc(title)}</h2>
    <p class="section-note">${esc(note)}</p>
    <div class="forecast-readiness-downstream">
      ${products.map(([key, product]) => `<span>${esc(FORMAL_ENGINE_LABELS[key] || humanEngineKey(key))}<b>${esc(product.status || "unknown")}</b></span>`).join("")}
    </div>
    ${keys.map(key => renderFormalEngineCard(r, key)).join("")}
  </section>`;
}

function renderFinancialsDashboard(r) {
  const series = r.financial_series || {};
  const facts = Array.isArray(series.facts) ? series.facts : [];
  const coverage = series.coverage || {};
  const model = r.financial_model_inputs || {};
  const truth = r.financial_truth_qualification || {};
  const readiness = r.forecast_readiness || {};
  const productAudit = state.data?.meta?.event_to_value_product_readiness || {};
  const summary = productAudit.summary || {};
  const factTypes = Object.entries(facts.reduce((counts, fact) => {
    const label = String(fact.metric || "Other fact").replaceAll("_", " ");
    counts[label] = (counts[label] || 0) + 1;
    return counts;
  }, {})).map(([label, value]) => ({ label, value, unit: "facts" })).sort((a, b) => b.value - a.value).slice(0, 6);
  const truthRows = [
    ["Annual income", truth.annual_income_triplets],
    ["Reported quarters", truth.qualified_reported_quarter_fact_sets],
    ["Operating cash flow", truth.annual_operating_cash_flow],
    ["Annual statements", truth.model_ready_financial_statement_coverage?.annual],
    ["Quarter statements", truth.model_ready_financial_statement_coverage?.reported_quarter],
  ].map(([label, item]) => ({ label, value: Number(item?.present || 0), unit: `of ${item?.required ?? "?"}` }));
  const factsChart = factTypes.length
    ? ciChart("assumptions", { status: "available", label: "Retained financial facts by line", items: factTypes, comparable: true, visible_summary: true })
    : ciBlockedChart("blocked_no_financial_facts", "No financial facts are retained", ["Official filing", "Explicit period", "Source-linked value"]);
  const truthChart = truthRows.some(item => item.value > 0)
    ? ciChart("assumptions", { status: "available", label: "Qualified financial-truth coverage", items: truthRows, comparable: false, visible_summary: true })
    : ciBlockedChart(truth.status || "blocked_no_qualified_truth", "Financial truth is not yet qualified", ["Annual income history", "Reported quarters", "Cash flow", "Share count tie-out"]);
  const forecastGate = readiness.downstream_status?.forecast || readiness.status || "blocked";
  const forecastChart = ciChart("blocked", { status: forecastGate, label: "Forecast and valuation gate", reason: ciHumanStatus(readiness.reason || forecastGate), requirements: (readiness.missing_requirements || []).slice(0, 5), available: 0 });
  const productChart = Number.isFinite(Number(summary.available_metric_count))
    ? ciChart("counter", { status: "available", label: "Available Event-to-Value product checks", value: Number(summary.available_metric_count), display: String(summary.available_metric_count), unit: `AVAILABLE · ${summary.blocked_metric_count ?? "?"} BLOCKED` })
    : ciBlockedChart("blocked_product_readiness_unavailable", "Product readiness audit is unavailable", ["Retained readiness audit"]);
  const accountingChart = ciChart("counter", { status: "available", label: "Retained accounting fact count", value: Number(coverage.fact_count ?? facts.length), display: String(coverage.fact_count ?? facts.length), unit: `${coverage.model_loadable_count ?? 0} MODEL-LOADABLE` });
  const stages = [
    ["Official facts", facts.length ? "available" : "missing"],
    ["Baseline", model.status || "unknown"],
    ["Truth qualification", truth.status || "unknown"],
    ["Forecast inputs", readiness.status || "unknown"],
    ["Formal forecast", forecastGate],
  ];
  return `<section class="panel span9 financials-dashboard-shell" aria-labelledby="financialsDashboardTitle">
    <header class="intelligence-dashboard-header"><div><span class="kicker">Financials workspace</span><h2 id="financialsDashboardTitle">Start with reported facts. See what the models can support.</h2><p>Move from source-linked accounting facts to comparable history, qualification, and formal-output gates. Missing periods stay visible and no browser-side forecast is invented.</p></div><div class="intelligence-dashboard-symbol"><iconify-icon icon="lucide:chart-no-axes-combined" aria-hidden="true"></iconify-icon><b>${esc(r.symbol)}</b><span>Reported before modelled</span></div></header>
    <div class="financials-stage-strip" aria-label="Financial evidence and model stages">${stages.map(([label, status]) => `<span><small>${esc(label)}</small><b>${esc(ciHumanStatus(status))}</b></span>`).join("")}</div>
    <div class="intelligence-dashboard-grid">
      ${intelligenceDashboardCard("trends", "lucide:chart-spline", "Reported history", "Financial trends", factsChart, "Compare only explicitly dated, compatible facts from official filings; conflicting rows remain visible.")}
      ${intelligenceDashboardCard("baseline", "lucide:database-zap", "Model inputs", "Financial baseline", truthChart, "Inspect which reported observations and deterministic derivations are qualified for downstream use.")}
      ${intelligenceDashboardCard("forecast", "lucide:shield-check", "Qualification gate", "Forecast readiness", forecastChart, "See the exact missing evidence holding back formal forecasts, valuation, and market-expectations outputs.")}
      ${intelligenceDashboardCard("alpha_readiness", "lucide:gauge", "Product gate", "Event-to-Value readiness", productChart, "Review retained product checks without confusing implemented machinery with proven live output.")}
      ${intelligenceDashboardCard("financials", "lucide:table-properties", "Accounting file", "Accounting snapshot", accountingChart, "Open the source-gated forecast panel alongside retained facts and the reported-history baseline.")}
    </div>
    <footer class="ci-editorial-footer"><span>Research only · no execution</span><span>Missing periods remain unknown; no forecast is inferred</span></footer>
  </section>`;
}

function renderCompanyFinancials(r) {
  return `<section class="company-route-stack">
    <button type="button" class="overview-back-button" data-research-route="directory_financials">Financials workspace</button>
    ${renderFormalEnginePanel(r, ["financial_forecasts"], "Source-gated engine", "Formal financial forecast", "Displayed from the authoritative financial_forecasts row only. Computed values appear only when the engine emits them with source provenance and research-only policy.", "formalForecastTitle")}
    ${renderFinancials(r)}
    ${renderFinancialBaseline(r)}
  </section>`;
}

function renderCompanyEarnings(r) {
  const readiness = r.forecast_readiness || {};
  const coverage = r.financial_coverage || {};
  const model = r.financial_model_inputs || {};
  const bridge = r.earnings_bridges || {};
  const bridges = Array.isArray(bridge.bridges) ? bridge.bridges : [];
  const historical = bridges.length ? `<section class="panel span9"><span class="kicker">Historical earnings bridge</span><h2>Reported annual changes</h2><p class="section-note">Historical, source-linked deltas only. This is not a forecast, valuation, or recommendation.</p><div class="reconciliation-list">${bridges.map(earningsBridgeRow).join("")}</div></section>` : `<section class="panel span9 blocked-shell"><span class="kicker">Historical earnings bridge</span><h2>No conflict-free annual bridge emitted</h2><p class="section-note">${esc(bridge.status || "blocked_insufficient_conflict_free_aligned_history")}. No forecast or valuation is inferred.</p></section>`;
  return `<section class="company-route-stack">
    ${historical}
    <section class="panel span9 blocked-shell" aria-labelledby="earningsTitle">
      <span class="kicker">Formal earnings engines</span><h2 id="earningsTitle">Forward earnings remain source-gated</h2>
      <p class="section-note">Earnings analysis is not generated until qualified multi-period annual consolidated history exists. This page shows readiness state only; it does not infer earnings direction, bridge drivers, forecast EPS, or value the company.</p>
      <div class="blocked-grid">
        <span>Readiness <b>${esc(readiness.status || "blocked")}</b></span>
        <span>Activation <b>${esc(readiness.activation_status || "blocked_insufficient_qualified_history")}</b></span>
        <span>Qualified periods <b>${esc(readiness.qualified_period_count ?? 0)}</b></span>
        <span>Coverage queue <b>${esc(coverage.status || "unknown")}</b></span>
        <span>Model inputs <b>${esc(model.status || "unknown")}</b></span>
        <span>Forecast gate <b>${esc(readiness.downstream_status?.forecast || "blocked_insufficient_qualified_history")}</b></span>
      </div>
      ${readinessList(readiness.missing_requirements, "Missing requirement: three aligned annual revenue, PAT and EPS periods.")}
    </section>
    ${renderFinancialEvidenceReconciliation(r)}
  </section>`;
}

function earningsBridgeSourceLink(source, fallback = "official source") {
  const href = safeHref(source?.source_url);
  const doc = source?.document_id || source?.fact_id || fallback;
  const page = source?.page ? ` · p.${source.page}` : "";
  const available = source?.available_on ? ` · available ${source.available_on}` : "";
  return href
    ? `<a href="${href}" target="_blank" rel="noopener">${esc(doc)}${esc(page)}${esc(available)}</a>`
    : `<span>${esc(doc)}${esc(page)}${esc(available)}</span>`;
}

function earningsBridgeMetricRow(metric, value) {
  const label = {
    revenue: "Revenue",
    profit_after_tax_attributable: "PAT",
    basic_eps: "EPS",
  }[metric] || metric;
  const changePct = value?.change_pct == null ? "Unknown" : `${esc(fmt(value.change_pct, 1))}%`;
  const changeAmount = value?.change_amount == null ? "Unknown" : esc(fmt(value.change_amount, 2));
  return `<article class="earnings-bridge-metric">
    <header><b>${esc(label)}</b><span>${changePct}</span></header>
    <div class="reconciliation-meta">
      <span>Previous <b>${esc(fmt(value?.previous_value, 2))}</b></span>
      <span>Current <b>${esc(fmt(value?.current_value, 2))}</b></span>
      <span>Change <b>${changeAmount}</b></span>
      <span>Unit <b>${esc(value?.unit || "unknown")}</b></span>
    </div>
    <div class="reconciliation-links">
      ${earningsBridgeSourceLink(value?.previous_source, "previous source")}
      ${earningsBridgeSourceLink(value?.current_source, "current source")}
    </div>
    <p>${esc(short(value?.current_source?.text || value?.previous_source?.text || "Reported annual source fact.", 160))}</p>
  </article>`;
}

function earningsBridgeRow(item) {
  const metrics = item.metrics || {};
  return `<article class="reconciliation-row earnings-bridge-row">
    <header><b>${esc(item.previous_period_end)} to ${esc(item.period_end)}</b><span>${esc(item.status)}</span></header>
    <div class="reconciliation-meta">
      <span>Bridge <b>${esc(item.bridge_type || "historical_reported_annual_change")}</b></span>
      <span>Type <b>${esc(item.intelligence_type || "derived_fact")}</b></span>
      <span>Available <b>${esc(item.available_on || "unknown")}</b></span>
      <span>Engine status <b>${esc(item.formal_engine_status?.forecast || "not_activated")}</b></span>
    </div>
    <div class="earnings-bridge-metrics">
      ${["revenue", "profit_after_tax_attributable", "basic_eps"].map(metric => earningsBridgeMetricRow(metric, metrics[metric] || {})).join("")}
    </div>
    <p>Descriptive history only. The browser displays emitted deltas and source links; it does not infer drivers, forecasts, valuation, price targets, or advice.</p>
  </article>`;
}

function reconciliationSourceLink(source, fallback = "official source") {
  const href = safeHref(source?.source_url);
  const doc = source?.document_id || source?.fact_id || fallback;
  const page = source?.page ? ` · p.${source.page}` : "";
  return href
    ? `<a href="${href}" target="_blank" rel="noopener">${esc(doc)}${esc(page)}</a>`
    : `<span>${esc(doc)}${esc(page)}</span>`;
}

function reconciliationFactRow(fact) {
  const source = fact?.source || {};
  const reasons = Array.isArray(fact?.reasons) ? fact.reasons : [];
  const value = fact?.normalized_value ?? "unknown";
  return `<article class="reconciliation-row">
    <header><b>${esc(fact?.metric || "metric unknown")}</b><span>${esc(fact?.status || "status unknown")}</span></header>
    <div class="reconciliation-meta">
      <span>Period <b>${esc(fact?.period_end || "unknown")}</b></span>
      <span>Value <b>${esc(value)}</b></span>
      <span>Basis <b>${esc(fact?.consolidation || "unknown")} · ${esc(fact?.currency || "currency unknown")}</b></span>
      <span>Evidence <b>${reconciliationSourceLink(source)}</b></span>
    </div>
    <p>${esc(short(source.text || reasons.join(", ") || fact?.evidence_label || "No evidence note emitted.", 180))}</p>
  </article>`;
}

function reconciliationConflictRow(conflict) {
  const values = Array.isArray(conflict?.values) ? conflict.values : [];
  return `<article class="reconciliation-row">
    <header><b>${esc(conflict?.metric || "metric unknown")} conflict</b><span>${esc(conflict?.status || "quarantined")}</span></header>
    <div class="reconciliation-meta">
      <span>Period <b>${esc(conflict?.period_end || "unknown")}</b></span>
      <span>Reason <b>${esc(conflict?.reason || "conflict retained")}</b></span>
      <span>Conflict ID <b>${esc(conflict?.conflict_id || "unknown")}</b></span>
    </div>
    <div class="reconciliation-links">
      ${values.length ? values.slice(0, 4).map(value => reconciliationSourceLink(value, value?.document_id || value?.fact_id || "conflict source")).join("") : `<span>No source values emitted.</span>`}
    </div>
  </article>`;
}

function reconciliationMissingSlotRow(slot) {
  const source = slot?.source || {};
  return `<article class="reconciliation-row">
    <header><b>${esc(slot?.metric || "metric unknown")} missing</b><span>${esc(slot?.status || "missing")}</span></header>
    <div class="reconciliation-meta">
      <span>Slot <b>${esc(slot?.slot || "annual slot")}</b></span>
      <span>Period <b>${esc(slot?.period_end || "unknown")}</b></span>
      <span>Evidence <b>${esc(slot?.period_evidence_status || "unknown")}</b></span>
      <span>Document <b>${esc(source.document_id || "no document")}</b></span>
    </div>
    <p>${esc(source.title || source.matched_text || slot?.reason || "Missing eligible reported fact for required annual slot.")}</p>
  </article>`;
}

function renderFinancialEvidenceReconciliation(r) {
  const reconciliation = r.financial_evidence_reconciliation && typeof r.financial_evidence_reconciliation === "object" && !Array.isArray(r.financial_evidence_reconciliation)
    ? r.financial_evidence_reconciliation
    : null;
  if (!reconciliation) {
    return `<section class="panel span9 financial-reconciliation" aria-labelledby="financialReconciliationTitle">
      <span class="kicker">Financial evidence reconciliation</span><h2 id="financialReconciliationTitle">Unavailable: not generated</h2>
      <p class="section-note">Read-only state is expected at row.financial_evidence_reconciliation. The browser does not qualify facts, count eligibility, match conflicts, calculate forecasts, value the company, or provide advice.</p>
      <div class="empty">Financial evidence reconciliation is unavailable: not generated.</div>
    </section>`;
  }
  const facts = Array.isArray(reconciliation.facts) ? reconciliation.facts : [];
  const conflicts = Array.isArray(reconciliation.conflicts) ? reconciliation.conflicts : [];
  const missing = Array.isArray(reconciliation.missing_slots) ? reconciliation.missing_slots : [];
  const readiness = reconciliation.readiness || {};
  return `<section class="panel span9 financial-reconciliation" aria-labelledby="financialReconciliationTitle">
    <span class="kicker">Financial evidence reconciliation</span><h2 id="financialReconciliationTitle">Source ledger behind earnings readiness</h2>
    <p class="section-note">Read-only backend output from row.financial_evidence_reconciliation. The browser displays emitted state only: it does not qualify facts, count eligibility from rows, choose among conflicts, calculate forecasts, value the company, or provide advice.</p>
    <div class="reconciliation-summary">
      <span>Status <b>${esc(reconciliation.status || "unknown")}</b></span>
      <span>Eligible <b>${esc(reconciliation.eligible_fact_count ?? "unknown")}</b></span>
      <span>Audit-only <b>${esc(reconciliation.audit_only_fact_count ?? "unknown")}</b></span>
      <span>Quarantined <b>${esc(reconciliation.quarantined_fact_count ?? "unknown")}</b></span>
      <span>Missing slots <b>${esc(reconciliation.missing_slot_count ?? "unknown")}</b></span>
      <span>Conflicts <b>${esc(reconciliation.source_conflict_count ?? "unknown")}</b></span>
    </div>
    <div class="reconciliation-readiness">
      <span>Earnings bridge <b>${esc(readiness.earnings_bridge_status || "blocked")}</b></span>
      <span>Forecast readiness <b>${esc(readiness.forecast_readiness_status || "blocked")}</b></span>
      <span>Forecast gate <b>${esc(readiness.forecast || "blocked_insufficient_qualified_history")}</b></span>
      <span>Reason <b>${esc(readiness.reason || "formal_forecast_readiness_remains_blocked")}</b></span>
    </div>
    <section class="reconciliation-section">
      <h3>Fact ledger</h3>
      ${facts.length ? `<div class="reconciliation-list">${facts.slice(0, 6).map(reconciliationFactRow).join("")}</div><p class="muted">Bounded backend fact-row preview. The emitted summary above is authoritative for the full ledger.</p>` : `<div class="empty">No fact rows were emitted.</div>`}
    </section>
    <section class="reconciliation-section">
      <h3>Conflicts</h3>
      ${conflicts.length ? `<div class="reconciliation-list">${conflicts.slice(0, 4).map(reconciliationConflictRow).join("")}</div>` : `<div class="empty">No source conflicts were emitted.</div>`}
    </section>
    <section class="reconciliation-section">
      <h3>Missing annual slots</h3>
      ${missing.length ? `<div class="reconciliation-list">${missing.slice(0, 9).map(reconciliationMissingSlotRow).join("")}</div>` : `<div class="empty">No missing annual slots were emitted.</div>`}
    </section>
  </section>`;
}

function renderCompanyValuation(r) {
  const readiness = r.forecast_readiness || {};
  const scenarioStatus = r.scenario_lab?.status || {};
  const legacy = r.valuation || {};
  return `<section class="panel span9 blocked-shell" aria-labelledby="valuationTitle">
    <button type="button" class="overview-back-button" data-research-route="directory_strategy">Strategy workspace</button><span class="kicker">Valuation overview</span><h2 id="valuationTitle">Formal CI valuation engine status</h2>
    <p class="section-note">Formal valuation and market expectations are displayed from the source-gated engine rows below. Scenario multiple sensitivity is separate caller-supplied algebra. Legacy fair-value screen remains a separate dashboard field.</p>
    <div class="blocked-grid">
      <span>Formal valuation <b>${esc(r.formal_valuations?.status || readiness.downstream_status?.valuation || "blocked_insufficient_qualified_history")}</b></span>
      <span>Forecast gate <b>${esc(readiness.status || "blocked")}</b></span>
      <span>Scenario sensitivity <b>${esc(scenarioStatus.valuation || "blocked")}</b></span>
      <span>Market expectations <b>${esc(r.market_expectations?.status || readiness.downstream_status?.market_expectations || "blocked_insufficient_qualified_history")}</b></span>
    </div>
    <section class="legacy-fair-value" aria-label="Legacy fair-value screen">
      <h3>Legacy fair-value screen, not formal CI valuation</h3>
      <p>Verdict: <b>${esc(legacy.verdict || "unknown")}</b>. Composite fair value: <b>${legacy.composite_fair == null ? "unknown" : `Rs ${esc(fmt(legacy.composite_fair, 2))}`}</b>. Mispricing: <b>${legacy.mispricing_pct == null ? "unknown" : esc(pct(legacy.mispricing_pct))}</b>.</p>
    </section>
  </section>
  ${renderFormalEnginePanel(r, ["formal_valuations", "market_expectations"], "Source-gated engines", "Formal valuation and market expectations", "Displayed exactly from the authoritative formal_valuations and market_expectations rows. The browser does not produce targets, reverse-solve growth, or fill missing operands.", "formalValuationEngineTitle")}`;
}

function renderCompanyEvents(r) {
  return `<section class="company-route-stack">
    ${renderTimeline(r)}
    ${renderChangeIntelligence(r)}
  </section>`;
}

function renderCompanyPeers(r) {
  const registry = r.peer_registry || {};
  const formalPeers = Array.isArray(registry.formal_peer_details) ? registry.formal_peer_details : [];
  const members = Array.isArray(registry.member_details) ? registry.member_details : [];
  const international = registry.international_peers || {};
  const peerCard = peer => `<article>
    <b>${esc(peer.symbol || "unknown")}</b>
    <span>${esc(peer.name || "Name unavailable")}</span>
    <small>${esc(registry.sector || "sector unknown")}</small>
  </article>`;
  if (!registry.method || registry.registry_status === "blocked_no_formal_peer_registry") {
    return `<section class="panel span9 blocked-shell" aria-labelledby="peersTitle">
      <button type="button" class="overview-back-button" data-research-route="directory_ownership">Ownership &amp; Peers workspace</button><span class="kicker">Peers</span><h2 id="peersTitle">No formal peer registry yet</h2>
      <p class="section-note">Peers are unavailable because no formal peer registry exists in the authoritative CI slice. The browser does not classify companies, derive peer groups from sector labels, infer financial metrics, or create an analogue set.</p>
      <div class="blocked-grid">
        <span>Formal registry <b>blocked_no_formal_peer_registry</b></span>
        <span>Sector label <b>${esc(r.sector || "unknown")}</b></span>
        <span>Peer set <b>unknown_no_authoritative_peer_data</b></span>
      </div>
      <div class="empty">No peer row is rendered until a dedicated producer emits an authoritative peer registry.</div>
    </section>`;
  }
  return `<section class="panel span9 blocked-shell" aria-labelledby="peersTitle">
    <button type="button" class="overview-back-button" data-research-route="directory_ownership">Ownership &amp; Peers workspace</button><span class="kicker">Peers</span><h2 id="peersTitle">Formal pilot-sector cohort</h2>
    <p class="section-note">Read-only formal peer registry. The backend groups the exact 20-company CI pilot by the retained official/exchange sector label only; this view does not estimate, forecast, sort by quality, or assign grades.</p>
    <div class="blocked-grid">
      <span>Registry method <b>${esc(registry.method || "unknown")}</b></span>
      <span>Sector label <b>${esc(registry.sector || "unknown")}</b></span>
      <span>Formal peers <b>${esc(formalPeers.length)}</b></span>
      <span>Cohort members <b>${esc(members.length)}</b></span>
      <span>Scope <b>${esc(registry.peer_set_kind || "pilot_sector_cohort")}</b></span>
      <span>International registry <b>${esc(international.status || "unavailable")}</b></span>
    </div>
    <section>
      <h3>Formal peers</h3>
      ${formalPeers.length ? `<div class="peer-list">${formalPeers.map(peerCard).join("")}</div>` : `<div class="empty">Explicit empty group: no other exact-pilot company shares this retained sector label.</div>`}
    </section>
    <section>
      <h3>Pilot-sector cohort</h3>
      ${members.length ? `<div class="peer-list">${members.map(peerCard).join("")}</div>` : `<div class="empty">No cohort members were emitted by the registry.</div>`}
    </section>
    <div class="empty">International peer registry: ${esc(international.reason || "no_authoritative_international_peer_registry")}.</div>
  </section>`;
}

function renderCompanyOwnership(r) {
  return `<section class="panel span9 blocked-shell" aria-labelledby="ownershipTitle">
    <button type="button" class="overview-back-button" data-research-route="directory_ownership">Ownership &amp; Peers workspace</button><span class="kicker">Ownership</span><h2 id="ownershipTitle">Ownership unknown without authoritative data</h2>
    <p class="section-note">No authoritative ownership table is present in the retained CI slice. Insider and off-market metadata are shown elsewhere as filings/activity metadata; they are not ownership percentages, beneficial-owner facts, or free-float analysis.</p>
    <div class="blocked-grid">
      <span>Ownership state <b>unknown_no_authoritative_ownership_data</b></span>
      <span>Insider filings metadata <b>${esc((r.insider_filings || []).length)}</b></span>
      <span>Off-market retained row <b>${r.offmarket ? "metadata_available" : "none"}</b></span>
    </div>
  </section>`;
}

function renderCompanyQuant(r) {
  const liq = r.liquidity || {};
  const studies = r.event_studies || [];
  const conditional = r.conditional_benchmarks?.benchmarks || [];
  return `<section class="panel span9 quant-shell" aria-labelledby="quantTitle">
    <button type="button" class="overview-back-button" data-research-route="directory_strategy">Strategy workspace</button><span class="kicker">Quant</span><h2 id="quantTitle">Existing quantitative state</h2>
    <p class="section-note">This view displays retained slice fields and existing benchmark availability only. It does not compute factors, backtests, forecasts, ranks, probabilities, or advice in the browser.</p>
    <div class="blocked-grid">
      <span>Current price <b>Rs ${esc(fmt(r.price?.current))}</b></span>
      <span>20-session return <b>${esc(pct(r.price?.ret_20d))}</b></span>
      <span>ADTV PKR <b>${esc(fmt(liq.adtv_pkr, 0))}</b></span>
      <span>Research eligible <b>${liq.research_eligible ? "yes" : "no"}</b></span>
      <span>Signal eligible <b>${liq.signal_eligible ? "yes" : "no"}</b></span>
      <span>Event studies <b>${esc(studies.length)}</b></span>
      <span>Conditional benchmarks <b>${esc(conditional.length)}</b></span>
    </div>
  </section>`;
}

function statusBucket(status) {
  const text = String(status || "unknown").toLowerCase();
  if (/blocked|missing|not_|unavailable|unknown|insufficient|pending|waiting/.test(text)) return "blocked";
  if (/computed|qualified|available|ready|active|emitted|verified|passed/.test(text)) return "available";
  return "retained";
}

function statusCountItems(rows) {
  const counts = rows.reduce((out, status) => {
    const key = ciHumanStatus(status);
    out[key] = (out[key] || 0) + 1;
    return out;
  }, {});
  return Object.entries(counts).map(([label, value]) => ({ label, value, unit: "states" })).slice(0, 6);
}

function strategyCounterChart(label, value, unit) {
  const number = Number(value);
  return Number.isFinite(number)
    ? ciChart("counter", { status: "available", label, value: number, display: String(value), unit })
    : ciBlockedChart("blocked_metric_not_retained", label, ["Retained field"]);
}

function strategyStatusChart(label, statuses, requirements = []) {
  const rows = (Array.isArray(statuses) ? statuses : [statuses]).filter(value => value != null && value !== "");
  const items = statusCountItems(rows);
  if (!items.length) return ciBlockedChart("blocked_status_not_retained", label, requirements.length ? requirements : ["Retained status"]);
  const hasAvailable = rows.some(status => statusBucket(status) === "available");
  return ciChart(hasAvailable ? "assumptions" : "blocked", {
    status: hasAvailable ? "available" : "blocked",
    label,
    items,
    comparable: false,
    visible_summary: true,
    reason: hasAvailable ? "Retained state is available" : "Retained state is blocked or unknown",
    requirements,
    available: rows.filter(status => statusBucket(status) === "available").length,
  });
}

function strategyTimelineChart(label, rows, requirements) {
  const items = (Array.isArray(rows) ? rows : []).map(item => ({
    date: item?.date || item?.effective_date || item?.detected_at || item?.available_on || item?.period_end,
    label: humanActivityLabel(item?.label || item?.title || item?.event_subtype || item?.event_type || item?.type || item?.metric || item?.document_id),
  })).filter(item => item.date && item.label).slice(-6);
  return items.length ? ciChart("timeline", { status: "available", label, items }) : ciBlockedChart("blocked_no_dated_strategy_items", label, requirements);
}

function strategyDashboardCard(route, icon, number, kicker, title, chart, copy, meta = "") {
  return `<article class="strategy-dashboard-card" data-flow-step="${esc(number)}" data-card-route="${esc(route)}"><header class="overview-card-heading"><span class="overview-card-icon" aria-hidden="true"><iconify-icon icon="${esc(icon)}"></iconify-icon></span><div><span class="kicker">${esc(kicker)}</span><h3>${esc(title)}</h3></div><span class="ci-card-route-pill">${esc(route)}</span></header>${chart}${meta ? `<div class="intelligence-card-meta">${meta}</div>` : ""}<p>${esc(copy)}</p><button type="button" class="overview-route-button" data-research-route="${esc(route)}" aria-label="Open ${esc(title)} research view">Open ${esc(title)}<iconify-icon icon="lucide:arrow-right" aria-hidden="true"></iconify-icon></button></article>`;
}

function renderStrategyDashboard(r) {
  const lab = r.scenario_lab || {};
  const labStatuses = Object.values(lab.status || {});
  const forecast = formalEngineProduct(r, "financial_forecasts");
  const valuation = formalEngineProduct(r, "formal_valuations");
  const expectations = formalEngineProduct(r, "market_expectations");
  const guidance = guidanceState(r);
  const guidanceObjectsCount = Array.isArray(guidance?.objects) ? guidance.objects.length : 0;
  const catalystsDomain = brainDomain(r.company_brain || {}, "catalysts");
  const catalystRefs = Array.isArray(catalystsDomain.object_refs) ? catalystsDomain.object_refs : [];
  const riskObjects = guidanceObjects(guidance, "risks");
  const studies = Array.isArray(r.event_studies) ? r.event_studies : [];
  const conditional = Array.isArray(r.conditional_benchmarks?.benchmarks) ? r.conditional_benchmarks.benchmarks : [];
  const quantStatuses = [
    r.liquidity?.research_eligible ? "available_research_eligible" : "blocked_research_eligibility_not_retained",
    studies.length ? "available_event_studies" : "blocked_no_event_studies",
    conditional.length ? "available_conditional_benchmarks" : "blocked_no_conditional_benchmarks",
  ];
  const flow = [
    ["01", "Scenario frame", labStatuses.length ? labStatuses[0] : lab.status?.scenario_lab || "blocked"],
    ["02", "Valuation gate", valuation.status || expectations.status || "blocked"],
    ["03", "Guidance check", guidance?.status || "unknown"],
    ["04", "Catalyst file", catalystsDomain.status || "unknown"],
    ["05", "Risk file", riskObjects.length ? guidance?.status || "available" : "unknown"],
    ["06", "Quant context", quantStatuses.find(status => statusBucket(status) === "available") || quantStatuses[0]],
  ];
  const scenarioChart = strategyStatusChart("Scenario Lab readiness", labStatuses.length ? labStatuses : [lab.status?.scenario_lab], ["Qualified financial truth", "Scenario baseline", "Source provenance"]);
  const valuationChart = strategyStatusChart("Formal valuation and expectations gates", [forecast.status, valuation.status, expectations.status], ["Financial forecast", "Formal valuation", "Market expectations"]);
  const guidanceChart = guidanceObjectsCount
    ? strategyCounterChart("Retained guidance assertion objects", guidanceObjectsCount, "GUIDANCE OBJECTS")
    : ciBlockedChart(guidance?.status || "blocked_no_guidance_objects", "No retained guidance assertions are available", ["Guidance contradictions row", "Official assertion object"]);
  const catalystChart = catalystRefs.length
    ? strategyCounterChart("Company Brain catalyst references", catalystRefs.length, "CATALYST REFS")
    : ciBlockedChart(catalystsDomain.status || "blocked_no_catalyst_refs", "No catalyst references are retained", ["Company Brain catalyst domain"]);
  const riskChart = riskObjects.length
    ? strategyCounterChart("Retained risk assertion objects", riskObjects.length, "RISK OBJECTS")
    : ciBlockedChart(guidance?.status || "blocked_no_risk_objects", "No retained risk assertions are available", ["Guidance contradictions row", "Risk assertion object"]);
  const quantChart = strategyStatusChart("Quant context availability", quantStatuses, ["Liquidity row", "Event studies", "Conditional benchmarks"]);
  const catalystEvents = [
    ...(Array.isArray(r.explainability?.monitoring?.what_to_watch) ? r.explainability.monitoring.what_to_watch : []),
    ...(Array.isArray(r.operating_events) ? r.operating_events : []),
  ];
  const monitoringChart = strategyTimelineChart("Strategy watch items and operating events", catalystEvents, ["Dated watch item", "Operating event"]);
  const valuationMeta = `<span><b>${esc(ciHumanStatus(forecast.status))}</b> forecast</span><span><b>${esc(ciHumanStatus(valuation.status))}</b> valuation</span><span><b>${esc(ciHumanStatus(expectations.status))}</b> expectations</span>`;
  return `<section class="panel span9 strategy-dashboard-shell" aria-labelledby="strategyDashboardTitle">
    <header class="strategy-dashboard-header"><div><span class="kicker">Strategy workspace</span><h2 id="strategyDashboardTitle">Turn retained evidence into a research decision flow.</h2><p>Use this hub to move from scenarios to valuation gates, guidance checks, catalysts, risks, and quantitative context. It is research-only; missing gates remain unknown and no action is recommended.</p></div><div class="strategy-dashboard-symbol"><iconify-icon icon="lucide:git-branch-plus" aria-hidden="true"></iconify-icon><b>${esc(r.symbol)}</b><span>Decision flow, not advice</span></div></header>
    <div class="strategy-flow" aria-label="Strategy research decision flow">${flow.map(([number, label, status]) => {
    const routeMap = { "Scenario frame": "scenarios", "Valuation gate": "valuation", "Guidance check": "guidance", "Catalyst file": "catalysts", "Risk file": "risks", "Quant context": "quant" };
    const stepRoute = routeMap[label] || "scenarios";
    return `<button type="button" class="strategy-flow-step" data-research-route="${esc(stepRoute)}" data-flow-status="${esc(statusBucket(status))}" aria-label="Jump to ${esc(label)}"><small>${esc(number)}</small><b>${esc(label)}</b><em>${esc(ciHumanStatus(status))}</em><iconify-icon icon="lucide:arrow-up-right" aria-hidden="true"></iconify-icon></button>`;
  }).join("")}</div>
    <div class="strategy-dashboard-grid">
      ${strategyDashboardCard("scenarios", "lucide:sliders-horizontal", "01", "Scenario frame", "Scenarios", scenarioChart, "Inspect caller-supplied sensitivity and reverse expectations only when the retained qualification gates allow it.")}
      ${strategyDashboardCard("valuation", "lucide:scale", "02", "Formal gates", "Valuation", valuationChart, "Read formal valuation and market-expectations status directly from source-gated engine rows; the browser does not fill missing operands.", valuationMeta)}
      ${strategyDashboardCard("guidance", "lucide:messages-square", "03", "Official assertions", "Guidance", guidanceChart, "Review retained management assertions and exact-key contradictions without turning them into a forecast.")}
      ${strategyDashboardCard("catalysts", "lucide:sparkles", "04", "Evidence watch", "Catalysts", catalystChart, "Open catalyst references retained by the Company Brain. A reference marks evidence, not financial impact.")}
      ${strategyDashboardCard("risks", "lucide:shield-alert", "05", "Break checks", "Risks", riskChart, "Review retained risk assertions and contradiction rows; absence of a row is shown as unknown, not safety.")}
      ${strategyDashboardCard("quant", "lucide:activity", "06", "Market context", "Quant", quantChart, "Use retained liquidity, event-study, and benchmark availability as context only. No browser-side factor score is calculated.")}
      <article class="strategy-dashboard-card strategy-dashboard-wide" data-flow-step="watch"><header class="overview-card-heading"><span class="overview-card-icon" aria-hidden="true"><iconify-icon icon="lucide:radar"></iconify-icon></span><div><span class="kicker">Monitoring layer</span><h3>What could move the research file next</h3></div></header>${monitoringChart}<p>Watch items and operating events are displayed as retained dated records. They are not treated as confirmations, price targets, or execution instructions.</p><button type="button" class="overview-route-button" data-research-route="monitoring">Open Monitoring<iconify-icon icon="lucide:arrow-right" aria-hidden="true"></iconify-icon></button></article>
    </div>
    <footer class="ci-editorial-footer"><span>Research only · no execution</span><span>Strategy previews retained state; child pages hold the detail</span></footer>
  </section>`;
}

function ownershipDashboardCard(route, icon, number, kicker, title, chart, copy, meta = "") {
  return `<article class="ownership-dashboard-card" data-ownership-step="${esc(number)}" data-card-route="${esc(route)}"><header class="overview-card-heading"><span class="overview-card-icon" aria-hidden="true"><iconify-icon icon="${esc(icon)}"></iconify-icon></span><div><span class="kicker">${esc(kicker)}</span><h3>${esc(title)}</h3></div><span class="ci-card-route-pill">${esc(route)}</span></header>${chart}${meta ? `<div class="intelligence-card-meta">${meta}</div>` : ""}<p>${esc(copy)}</p><button type="button" class="overview-route-button" data-research-route="${esc(route)}" aria-label="Open ${esc(title)} research view">Open ${esc(title)}<iconify-icon icon="lucide:arrow-right" aria-hidden="true"></iconify-icon></button></article>`;
}

function renderOwnershipDashboard(r) {
  const ownership = r.ownership && typeof r.ownership === "object" && !Array.isArray(r.ownership) ? r.ownership : null;
  const registry = r.peer_registry && typeof r.peer_registry === "object" && !Array.isArray(r.peer_registry) ? r.peer_registry : null;
  const formalPeers = Array.isArray(registry?.formal_peer_details) ? registry.formal_peer_details : [];
  const watch = r.evidence_watchlist && typeof r.evidence_watchlist === "object" && !Array.isArray(r.evidence_watchlist) ? r.evidence_watchlist : null;
  const watchItems = Array.isArray(watch?.items) ? watch.items : [];
  const watchTimeline = watchItems.map(item => ({ date: item.date || item.detected_at, label: item.monitored_assertion || item.status || "Evidence watch" })).filter(item => item.date).slice(-6);
  const conditional = r.conditional_benchmarks && typeof r.conditional_benchmarks === "object" && !Array.isArray(r.conditional_benchmarks) ? r.conditional_benchmarks : null;
  const benchmarks = Array.isArray(conditional?.benchmarks) ? conditional.benchmarks : [];
  const causal = r.causal_foundations && typeof r.causal_foundations === "object" && !Array.isArray(r.causal_foundations) ? r.causal_foundations : null;
  const causalRows = Array.isArray(causal?.causal_rows) ? causal.causal_rows : [];
  const financial = r.financial_series?.coverage || {};
  const sourceQuality = r.source_quality || {};
  const thesis = r.thesis_monitoring && typeof r.thesis_monitoring === "object" && !Array.isArray(r.thesis_monitoring) ? r.thesis_monitoring : null;
  const monitoring = r.monitoring && typeof r.monitoring === "object" && !Array.isArray(r.monitoring) ? r.monitoring : null;
  const operatingEvents = Array.isArray(r.operating_events) ? r.operating_events : [];
  const ownershipChart = ownership
    ? ciChart("assumptions", { status: ownership.status || "retained", label: "Authoritative ownership record state", items: [{ label: "Record state", value: ownership.status || "retained" }], visible_summary: true })
    : ciBlockedChart("blocked_no_authoritative_ownership_data", "Ownership remains unknown", ["Authoritative ownership table", "Beneficial-owner source", "Free-float source"]);
  const peerChart = registry && registry.registry_status !== "blocked_no_formal_peer_registry"
    ? ciChart("counter", { status: registry.registry_status || "retained", label: "Explicit formal peer rows", value: formalPeers.length, display: String(formalPeers.length), unit: "EMITTED FORMAL PEERS" })
    : ciBlockedChart("blocked_no_formal_peer_registry", "No authoritative peer registry is available", ["Formal peer registry", "Explicit peer identity", "Registry method"]);
  const watchChart = watchTimeline.length
    ? ciChart("timeline", { status: watch.status || "retained", label: "Dated evidence-watch records", items: watchTimeline })
    : Number.isFinite(Number(watch?.active_watch_count))
      ? ciChart("counter", { status: watch.status || "retained", label: "Active evidence-watch rows", value: Number(watch.active_watch_count), display: String(watch.active_watch_count), unit: "EMITTED WATCH ROWS" })
      : ciBlockedChart("blocked_no_evidence_watchlist", "No evidence-watch state is retained", ["Evidence watchlist object", "Confirmation check", "Break check"]);
  const benchmarkChart = conditional
    ? ciChart("counter", { status: conditional.status || "retained", label: "Descriptive conditional benchmark rows", value: benchmarks.length, display: String(benchmarks.length), unit: "EMITTED BENCHMARK ROWS" })
    : ciBlockedChart("blocked_no_conditional_benchmarks", "No conditional benchmark state is retained", ["Conditional benchmark row", "Explicit event match", "Historical sample"]);
  const causalChart = causal
    ? ciChart("counter", { status: "retained", label: "Causal-foundation evidence rows", value: causalRows.length, display: String(causalRows.length), unit: "CATEGORICAL EVIDENCE ROWS" })
    : ciBlockedChart("blocked_no_causal_foundations", "No causal evidence map is retained", ["Causal foundation row", "Official event reference", "Strict study reference"]);
  const coverageItems = [
    ["Financial facts", financial.fact_count],
    ["Explicit periods", financial.period_count],
    ["Monitored pages", sourceQuality.monitored_page_count],
    ["Official documents", sourceQuality.document_link_count],
  ].filter(([, value]) => value != null && value !== "").map(([label, value]) => ({ label, value, unit: "retained" }));
  const coverageChart = coverageItems.length
    ? ciChart("assumptions", { status: "retained", label: "Retained coverage footprint", items: coverageItems, comparable: true, visible_summary: true })
    : ciBlockedChart("blocked_no_coverage_summary", "Coverage counts are not retained", ["Financial coverage row", "Source-quality row"]);
  const thesisChart = thesis && Number.isFinite(Number(thesis.active_thesis_count))
    ? ciChart("counter", { status: thesis.status || "retained", label: "Active thesis-monitor rows", value: Number(thesis.active_thesis_count), display: String(thesis.active_thesis_count), unit: "EMITTED THESIS ROWS" })
    : ciBlockedChart("blocked_no_thesis_monitoring", "No thesis-monitor state is retained", ["Thesis monitoring row", "Official-source checks", "Status field"]);
  const monitorTimeline = monitoring ? [
    [monitoring.latest_source_at, "Latest retained source"],
    [monitoring.latest_change_at, "Latest retained change"],
    [monitoring.latest_event_at, "Latest retained event"],
  ].filter(([date]) => date).map(([date, label]) => ({ date, label })) : [];
  const monitoringChart = monitorTimeline.length
    ? ciChart("timeline", { status: monitoring.status || "retained", label: "Dated monitoring activity", items: monitorTimeline })
    : Number.isFinite(Number(monitoring?.alert_count))
      ? ciChart("counter", { status: monitoring.status || "retained", label: "Retained monitoring alerts", value: Number(monitoring.alert_count), display: String(monitoring.alert_count), unit: "EMITTED ALERT ROWS" })
      : ciBlockedChart("blocked_no_monitoring_state", "No monitoring activity is retained", ["Monitoring object", "Dated activity", "Alert state"]);
  const operationTimeline = operatingEvents.map(item => ({ date: item.effective_date || item.detected_at, label: humanActivityLabel(item.event_subtype || item.event_type || "Operating event") })).filter(item => item.date).slice(-6);
  const operationsChart = operationTimeline.length
    ? ciChart("timeline", { status: "retained", label: "Dated operating events", items: operationTimeline })
    : ciBlockedChart("blocked_no_operating_events", "No operating events are retained", ["Dated operating event", "Operating classification", "Source evidence"]);
  const flow = [
    ["01", "Ownership boundary", ownership ? ownership.status || "retained" : "blocked"],
    ["02", "Peer context", registry?.registry_status || "blocked"],
    ["03", "Evidence watch", watch?.status || "blocked"],
    ["04", "Cross-company context", conditional?.status || "blocked"],
    ["05", "Causal coverage", causal ? "retained" : "blocked"],
    ["06", "Thesis & alerts", monitoring?.status || thesis?.status || "blocked"],
  ];
  return `<section class="panel span9 ownership-dashboard-shell" aria-labelledby="ownershipDashboardTitle">
    <header class="ownership-dashboard-header"><div><span class="kicker">Ownership &amp; peers workspace</span><h2 id="ownershipDashboardTitle">Map the boundary around ${esc(r.symbol)}.</h2><p>Use this hub to separate what is authoritative from what remains unknown: ownership records, peer context, evidence watches, descriptive benchmarks, causal coverage, financial coverage, thesis checks, and dated monitoring activity. Missing inputs stay visible; no ownership percentage, free float, peer identity, trend, or readiness state is inferred.</p></div><div class="ownership-dashboard-symbol"><iconify-icon icon="lucide:network" aria-hidden="true"></iconify-icon><b>${esc(r.symbol)}</b><span>Connections before conclusions</span></div></header>
    <div class="ownership-flow" aria-label="Ownership and peers research flow">${flow.map(([number, label, status]) => {
    const routeMap = { "Ownership boundary": "ownership", "Peer context": "peers", "Evidence watch": "watchlist", "Cross-company context": "conditional", "Causal coverage": "causal", "Thesis & alerts": "thesis" };
    const stepRoute = routeMap[label] || "ownership";
    return `<button type="button" class="ownership-flow-step" data-research-route="${esc(stepRoute)}" data-flow-status="${esc(statusBucket(status))}" aria-label="Jump to ${esc(label)}"><small>${esc(number)}</small><b>${esc(label)}</b><em>${esc(ciHumanStatus(status))}</em><iconify-icon icon="lucide:arrow-up-right" aria-hidden="true"></iconify-icon></button>`;
  }).join("")}</div>
    <div class="ownership-dashboard-grid">
      ${ownershipDashboardCard("ownership", "lucide:lock-keyhole", "01", "Boundary check", "Ownership", ownershipChart, "No authoritative ownership table is present in the retained row. Filing metadata is not treated as ownership percentages or free-float evidence.")}
      ${ownershipDashboardCard("peers", "lucide:users-round", "02", "Explicit registry", "Peers", peerChart, "Open only the formal peer registry emitted by the backend. Sector labels never become an inferred peer set.", registry ? `<span>Method <b>${esc(registry.method || "not emitted")}</b></span><span>Scope <b>${esc(registry.peer_set_kind || "not emitted")}</b></span>` : "")}
      ${ownershipDashboardCard("watchlist", "lucide:eye", "03", "Evidence watch", "Watchlist", watchChart, "Review emitted confirmation and break checks. Silence is not confirmation, and a missing watch row is not safety.")}
      ${ownershipDashboardCard("conditional", "lucide:git-compare-arrows", "04", "Descriptive context", "Conditional Benchmarks", benchmarkChart, "Inspect exact historical context only where the backend emitted a benchmark row; these rows are not causal, predictive, or advice.")}
      ${ownershipDashboardCard("causal", "lucide:waypoints", "05", "Evidence map", "Causal Map", causalChart, "Trace categorical driver evidence and its source references. Numeric impact remains blocked unless the authoritative row says otherwise.")}
      ${ownershipDashboardCard("coverage", "lucide:scan-line", "06", "Source footprint", "Coverage", coverageChart, "See what financial and source-quality coverage is retained for this issuer without converting coverage into a score.")}
      ${ownershipDashboardCard("thesis", "lucide:clipboard-check", "07", "Thesis checks", "Thesis Monitor", thesisChart, "Open emitted thesis-monitor rows and their official-source checks. The browser does not upgrade, break, or rank a thesis.")}
      ${ownershipDashboardCard("monitoring", "lucide:radar", "08", "Dated activity", "Monitoring", monitoringChart, "Follow retained source, change, event, and alert timestamps. Activity is context, not a forecast or trading instruction.")}
      ${ownershipDashboardCard("operations", "lucide:factory", "09", "Legacy context", "Operations (legacy)", operationsChart, "Open the legacy operating view for retained event and driver context; no new operating conclusion is created here.")}
    </div>
    <footer class="ci-editorial-footer"><span>Research only · no execution</span><span>Every tile maps to retained row fields or an explicit blocked state</span></footer>
  </section>`;
}

function intelligenceDashboardCard(route, icon, kicker, title, chart, copy, meta = "") {
  return `<article class="intelligence-dashboard-card" data-card-route="${esc(route)}"><header class="overview-card-heading"><span class="overview-card-icon" aria-hidden="true"><iconify-icon icon="${esc(icon)}"></iconify-icon></span><div><span class="kicker">${esc(kicker)}</span><h3>${esc(title)}</h3></div><span class="ci-card-route-pill">${esc(route)}</span></header>${chart}${meta ? `<div class="intelligence-card-meta">${meta}</div>` : ""}<p>${esc(copy)}</p><button type="button" class="overview-route-button" data-research-route="${esc(route)}" aria-label="Open ${esc(title)} research view">Open ${esc(title)}<iconify-icon icon="lucide:arrow-right" aria-hidden="true"></iconify-icon></button></article>`;
}

function renderIntelligenceDashboard(r) {
  const envelope = r.explainability || {};
  const lifecycle = [
    ["Observation", envelope.observation],
    ["Mechanism", envelope.transmission_mechanism],
    ["Forecast", envelope.forecast_trajectory],
    ["Assumptions", envelope.key_assumptions],
    ["Expectations", envelope.expectations_gap],
    ["Conclusion", envelope.conclusion],
    ["Monitoring", envelope.monitoring],
  ];
  const askRecord = state.ask.bySymbol[r.symbol] || {};
  const citationCount = Array.isArray(askRecord.citations) ? askRecord.citations.length : null;
  const graphNodes = Array.isArray(r.graph?.nodes) ? r.graph.nodes : [];
  const graphEdges = Array.isArray(r.graph?.edges) ? r.graph.edges : [];
  const graphTypes = Object.entries(graphNodes.reduce((counts, node) => {
    const key = objectTypeLabel(node?.type || "other");
    counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {})).map(([label, value]) => ({ label, value, unit: "nodes" }));
  const operatingEvents = Array.isArray(r.operating_events) ? r.operating_events : [];
  const operatingTimeline = operatingEvents.map(item => ({ date: item.effective_date || item.detected_at, label: String(item.event_subtype || item.event_type || "Operating event").replaceAll("_", " ") })).filter(item => item.date).slice(-6);
  const typedTimeline = Array.isArray(r.company_brain?.timeline) ? r.company_brain.timeline : [];
  const chronology = typedTimeline.map(item => ({ date: item.date, label: objectTypeLabel(item.type) })).filter(item => item.date).slice(-6);
  const conclusion = envelope.conclusion || {};
  const historicalMap = r.historical_state_map || {};
  const historicalContexts = Array.isArray(historicalMap.contexts) ? historicalMap.contexts : [];
  const lifecycleRouteMap = { "Observation": "operating", "Mechanism": "graph", "Forecast": "past_context", "Assumptions": "intelligence", "Expectations": "intelligence", "Conclusion": "intelligence", "Monitoring": "timeline" };
  const lifecycleStrip = `<div class="intelligence-lifecycle" aria-label="Event-to-Value section states">${lifecycle.map(([label, section]) => {
    const route = lifecycleRouteMap[label] || "intelligence";
    return `<button type="button" class="intelligence-lifecycle-step" data-research-route="${esc(route)}" data-flow-status="${esc(statusBucket(section?.status))}" aria-label="Jump to ${esc(label)}: ${esc(ciHumanStatus(section?.status))}"><small>${esc(label)}</small><b>${esc(ciHumanStatus(section?.status))}</b><iconify-icon icon="lucide:arrow-up-right" aria-hidden="true"></iconify-icon></button>`;
  }).join("")}</div>`;
  const askChart = citationCount == null
    ? ciBlockedChart("blocked_no_session_answer", "No question has been answered in this session", ["Ask a company question", "Validate cited answer", "Inspect retained sources"])
    : ciChart("counter", { status: "available", label: "Citations in the current session answer", value: citationCount, display: String(citationCount), unit: "CITATIONS IN CURRENT ANSWER" });
  const graphChart = graphTypes.length
    ? ciChart("assumptions", { status: "available", label: "Retained graph nodes by type", items: graphTypes, comparable: true, visible_summary: true })
    : ciBlockedChart("blocked_no_graph_nodes", "No evidence connections are retained", ["Official document", "Typed object", "Evidence link"]);
  const operatingChart = operatingTimeline.length
    ? ciChart("timeline", { status: "available", label: "Latest retained operating events", items: operatingTimeline })
    : ciBlockedChart("blocked_no_operating_events", "No operating events are retained", ["Dated observation", "Official evidence", "Operating classification"]);
  const eventToValueChart = ciChart("blocked", ciEnvelopeBlocked(conclusion, "Formal Event-to-Value conclusion", ["Observed event", "Transmission mechanism", "Qualified financial truth", "Reviewed assumptions"]));
  const chronologyChart = chronology.length
    ? ciChart("timeline", { status: "available", label: "Latest typed company chronology", items: chronology })
    : ciBlockedChart("blocked_no_typed_timeline", "No typed chronology is retained", ["Official filing", "Typed object", "Dated record"]);
  const pastContextChart = historicalContexts.length
    ? ciChart("counter", { status: "available", label: "Retained Historical State Map cases", value: historicalContexts.length, display: String(historicalContexts.length), unit: "CUTOFF-SAFE CASE CONTEXTS" })
    : ciBlockedChart(historicalMap.status || "not_selected_for_historical_state_map", "No historical state map is retained for this company", ["Qualified observed case", "Cutoff-safe state vector", "Strict prior-event candidates"]);
  const operatingMeta = operatingEvents.length ? `<span><b>${esc(operatingEvents.length)}</b> retained event${operatingEvents.length === 1 ? "" : "s"}</span><span><b>${esc(ciHumanStatus(r.driver_graph?.status))}</b> sector model</span>` : "";
  const graphMeta = `<span><b>${esc(graphNodes.length)}</b> nodes</span><span><b>${esc(graphEdges.length)}</b> links</span>`;
  const chronologyMeta = typedTimeline.length ? `<span><b>${esc(typedTimeline.length)}</b> typed entries</span>` : "";
  return `<section class="panel span9 intelligence-dashboard-shell" aria-labelledby="intelligenceDashboardTitle">
    <header class="intelligence-dashboard-header"><div><span class="kicker">Intelligence workspace</span><h2 id="intelligenceDashboardTitle">Follow the event. Inspect the evidence.</h2><p>${esc(conclusion.text || "Move from retained observations to mechanisms, scenarios, questions, connections, and dated evidence without treating a missing output as a conclusion.")}</p></div><div class="intelligence-dashboard-symbol"><iconify-icon icon="lucide:network" aria-hidden="true"></iconify-icon><b>${esc(r.symbol)}</b><span>Evidence before inference</span></div></header>
    ${lifecycleStrip}
    <div class="intelligence-dashboard-grid">
      ${intelligenceDashboardCard("intelligence", "lucide:route", "Event-to-Value", "The full intelligence chain", eventToValueChart, "Inspect the seven evidence-backed sections and see exactly which formal outputs remain gated.")}
      ${intelligenceDashboardCard("operating", "lucide:factory", "Operating evidence", "Events and driver hypotheses", operatingChart, "Trace sourced operating observations into declarative sector drivers and retained scenarios—without claiming causality.", operatingMeta)}
      ${intelligenceDashboardCard("graph", "lucide:network", "Evidence connections", "Knowledge graph", graphChart, "See how the issuer, official documents, typed facts, events, periods, and source links connect.", graphMeta)}
      ${intelligenceDashboardCard("timeline", "lucide:history", "Chronology", "Typed timeline", chronologyChart, "Read what changed in dated order, with official-event chronology kept separate from document revisions.", chronologyMeta)}
      ${intelligenceDashboardCard("ask", "lucide:message-circle-question", "Research question", "Ask Henneth", askChart, "Question the retained company file. Factual claims appear only when the server returns validated citations.")}
      ${intelligenceDashboardCard("past_context", "lucide:scan-search", "Historical state map", "Past Context", pastContextChart, "Compare a qualified observed event with cutoff-safe historical context while keeping similarity, source trust, and forecast permissions separate.")}
    </div>
    <footer class="ci-editorial-footer"><span>Research only · no execution</span><span>Dashboard previews retained state; specialist pages hold the detail</span></footer>
  </section>`;
}

function pastContextCard(icon, number, kicker, title, chart, copy, details = "", wide = false) {
  return `<article class="past-context-card${wide ? " past-context-wide" : ""}" data-past-context-step="${esc(number)}">
    <header class="overview-card-heading">
      <span class="overview-card-icon" aria-hidden="true"><iconify-icon icon="${esc(icon)}"></iconify-icon></span>
      <div class="overview-card-heading-text">
        <div class="past-context-card-kicker-row">
          <span class="kicker">${esc(kicker)}</span>
          <span class="past-context-step-chip">STEP ${esc(number)}</span>
        </div>
        <h3>${esc(title)}</h3>
      </div>
    </header>
    ${chart}
    ${details}
    <p class="past-context-copy">${esc(copy)}</p>
  </article>`;
}

function renderPastContext(r) {
  const product = r.historical_state_map || {};
  const contexts = Array.isArray(product.contexts) ? product.contexts : [];
  if (!contexts.length) {
    return `<section class="panel span9 past-context-shell" aria-labelledby="pastContextTitle"><header class="past-context-header"><div><button type="button" class="overview-back-button" data-research-route="directory_intelligence">Intelligence workspace</button><span class="kicker">Past Context · historical state map</span><h2 id="pastContextTitle">No historical state map is retained for ${esc(r.symbol)} yet.</h2><p>This first bounded map covers selected Alpha cases only. An absent row is not evidence that the company has no analogue; it means Henneth has not qualified one in this product.</p></div><div class="past-context-seal"><iconify-icon icon="lucide:history" aria-hidden="true"></iconify-icon><b>${esc(r.symbol)}</b><span>Historical context · not forecast</span></div></header><div class="past-context-empty">${ciBlockedChart(product.status || "not_selected_for_historical_state_map", "Historical state map not available for this company", ["Qualified observed case", "Cutoff-safe state vector", "Strict prior-event candidates", "Source lineage"])}</div><footer class="ci-editorial-footer"><span>Research only · no execution</span><span>No analogue, outcome, or readiness inferred</span></footer></section>`;
  }
  const selectedId = state.pastContext.bySymbol[r.symbol];
  const context = contexts.find(item => item?.map_id === selectedId) || contexts[0];
  const caseData = context.case || {};
  const binding = context.event_binding || {};
  const vector = context.current_state_vector || {};
  const market = vector.market_setup || {};
  const operating = vector.operating_event || {};
  const financial = vector.financial_truth || {};
  const regime = vector.policy_regime || {};
  const past = context.past_context || {};
  const study = past.event_study || {};
  const benchmark = past.strict_analogue_benchmark || {};
  const evidence = Array.isArray(binding.source_lineage) ? binding.source_lineage : [];
  const horizons = study.horizons || {};
  const caseLabel = String(caseData.case_type || binding.event_subtype || "observed event").replaceAll("_", " ");
  const analogueCandidates = [
    ...(Array.isArray(benchmark.candidates) ? benchmark.candidates : []),
    ...(Array.isArray(benchmark.analogues) ? benchmark.analogues : []),
    ...(Array.isArray(benchmark.analogue_contexts) ? benchmark.analogue_contexts : []),
  ].filter(item => item && typeof item === "object");
  const preReturns = market.pre_event_returns || {};
  const stateChart = ciChart("state_colonnade", {
    status: "available",
    label: "Four retained state categories at the case cutoff",
    groups: [
      { label: "Technical / market", status: market.status, items: [
        { label: "Pre-event baseline", value: market.baseline?.close == null ? "Unknown" : `Rs ${fmt(market.baseline.close)}`, detail: market.baseline?.date },
        ...["5d", "15d", "60d"].map(label => ({ label: `${label} pre-event return`, value: preReturns[label]?.return_pct == null ? "Unknown" : pct(Number(preReturns[label].return_pct)), detail: `${preReturns[label]?.start_date || "unknown"} to ${preReturns[label]?.end_date || "unknown"}` })),
        { label: "5-to-60-session volume", value: market.pre_event_volume?.median_5_session_to_60_session_ratio == null ? "Unknown" : `${fmt(market.pre_event_volume.median_5_session_to_60_session_ratio, 2)}×`, detail: "Median volume ratio retained by backend" },
      ] },
      { label: "Operating event", status: operating.status, items: [
        { label: "Evidence count", value: String(operating.evidence_count ?? "Unknown") },
        { label: "Affected drivers", value: Array.isArray(operating.affected_drivers) && operating.affected_drivers.length ? operating.affected_drivers.join(", ") : "None emitted" },
        { label: "Estimated scale", value: operating.estimated_scale == null ? "Not emitted" : String(operating.estimated_scale) },
      ] },
      { label: "Financial / fundamental", status: financial.status, items: [
        { label: "Qualified annual periods", value: `${financial.annual?.present ?? "Unknown"} / ${financial.annual?.required ?? "Unknown"}` },
        { label: "Qualified quarters", value: `${financial.reported_quarter?.present ?? "Unknown"} / ${financial.reported_quarter?.required ?? "Unknown"}` },
        { label: "Formal outputs", value: financial.blocks_formal_outputs ? "Blocked" : "Not blocked" },
      ] },
      { label: "Policy / regime", status: regime.status, items: [
        { label: "Qualified regime model", value: regime.status === "available" ? "Available" : "Unavailable", detail: String(regime.reason || "No reason emitted").replaceAll("_", " ") },
      ] },
    ],
  });
  const separationChart = ciChart("evidence_convergence", {
    status: "available",
    label: "Similarity context remains separate from evidence trust",
    case_label: caseLabel,
    trust_label: `Source quality level ${binding.source_quality_level ?? "unknown"}`,
    context_label: `${benchmark.strict_candidate_count ?? 0} strict candidate${benchmark.strict_candidate_count === 1 ? "" : "s"}`,
    context_detail: "No similarity score or ranked analogue identity is emitted.",
    sources: evidence.map(item => ({ label: item.document_title || item.document_id || "Retained source", detail: `${item.source || "Official source"} · ${String(item.document_published_at || item.event_date || "date unknown").slice(0, 10)}` })),
  });
  const timelineItems = [
    market.baseline?.date ? { date: market.baseline.date, label: "Pre-event baseline", kind: "event", observed: true } : null,
    binding.effective_date ? { date: binding.effective_date, label: "Observed event", kind: "event", observed: true } : null,
    ...evidence.flatMap(item => [
      item.document_published_at ? { date: item.document_published_at, label: item.document_title || "Source published", kind: "source", observed: true, detail: "Published" } : null,
      item.document_retrieved_at ? { date: item.document_retrieved_at, label: item.document_title || "Source retrieved", kind: "source", observed: true, detail: "Retrieved" } : null,
    ]),
    ...Object.entries(horizons).map(([label, row]) => ({ date: row?.selected_date || row?.target_date, label: `${label} ${row?.status === "mature" ? "observed" : "target"}`, kind: "outcome", observed: row?.status === "mature", detail: row?.reason || undefined })),
  ].filter(Boolean);
  const timelineChart = timelineItems.length
    ? ciChart("dated_lineage", { status: "available", label: "Case, source, and outcome availability", items: timelineItems, cutoff: study.data_cutoff })
    : ciBlockedChart("blocked_no_dated_context", "No dated context is retained", ["Pre-event baseline", "Effective date", "Observed endpoint"]);
  const horizonOutcomes = ["1Q", "2Q", "4Q", "8Q"].map(label => {
    const row = horizons[label] || {};
    const hasOutcome = row.status === "mature" && row.return_pct != null && Number.isFinite(Number(row.return_pct));
    return { label, value: hasOutcome ? Number(row.return_pct) : null, unit: "%", status: row.status || "unavailable", date: hasOutcome ? row.selected_date : row.target_date, detail: row.reason || undefined };
  });
  const outcomesChart = horizonOutcomes.length
    ? ciChart("horizon_outcomes", { status: "available", label: "Observed raw-price returns after this event", items: horizonOutcomes, visible_summary: true })
    : ciBlockedChart(study.status || "blocked_no_mature_outcomes", "No mature outcome window is retained", ["Cutoff-safe event study", "Mature endpoint", "Raw-price return"]);
  const sourceDetails = evidence.length ? `<div class="past-context-sources" aria-label="Source lineage">${evidence.slice(0, 3).map(item => {
    const href = safeHref(item.source_url);
    const label = `${item.source || "Official source"} · ${String(item.document_published_at || item.event_date || "date unknown").slice(0, 10)}`;
    return `<span><b>${esc(label)}</b><small>${esc(item.document_title || item.document_id || "Retained document")}</small>${href ? `<a href="${href}" target="_blank" rel="noopener">Open source <iconify-icon icon="lucide:external-link" aria-hidden="true"></iconify-icon></a>` : ""}</span>`;
  }).join("")}</div>` : `<div class="past-context-gap"><span><b>Source lineage</b><small>No source reference emitted</small></span></div>`;
  const stateDetails = `<div class="past-context-state-grid"><span data-state="${esc(statusBucket(market.status))}"><small>Market setup</small><b>${esc(ciHumanStatus(market.status))}</b><em>${market.policy?.strictly_pre_event ? "Strictly pre-event" : "Cutoff policy unknown"}</em></span><span data-state="${esc(statusBucket(operating.status))}"><small>Operating event</small><b>${esc(ciHumanStatus(operating.status))}</b><em>${esc(operating.evidence_count ?? "unknown")} retained evidence item${operating.evidence_count === 1 ? "" : "s"}</em></span><span data-state="${esc(statusBucket(financial.status))}"><small>Financial truth</small><b>${esc(ciHumanStatus(financial.status))}</b><em>${esc(financial.annual?.present ?? "unknown")}/${esc(financial.annual?.required ?? "unknown")} annual · ${esc(financial.reported_quarter?.present ?? "unknown")}/${esc(financial.reported_quarter?.required ?? "unknown")} quarters</em></span><span data-state="${esc(statusBucket(regime.status))}"><small>Policy / regime</small><b>${esc(ciHumanStatus(regime.status))}</b><em>${esc(String(regime.reason || "No qualified regime model").replaceAll("_", " "))}</em></span></div><div class="past-context-gap"><span><b>Case state, not live state</b><small>Current technical state is not emitted; this chart shows the strictly pre-event setup retained for the case.</small></span></div>`;
  const bindingId = binding.matched_operating_event_id || binding.matched_canonical_event_id || binding.matched_event_id || "not emitted";
  const sourceId = binding.matched_source_document_id || evidence[0]?.document_id || "not emitted";
  const sourcePage = binding.matched_page ?? evidence[0]?.page ?? "not emitted";
  const sourceHash = binding.matched_content_sha256 || evidence[0]?.content_sha256 || "not emitted";
  const publishedAt = evidence[0]?.document_published_at || "not emitted";
  const bindingDetails = `<div class="past-context-binding" aria-label="Exact event binding"><span><small>Bound event</small><b>${esc(bindingId)}</b></span><span><small>Source document</small><b>${esc(sourceId)} · p.${esc(sourcePage)}</b></span><span><small>Content hash</small><b>${esc(sourceHash)}</b></span><span><small>Published</small><b>${esc(String(publishedAt).slice(0, 10))}</b></span></div>`;
  const analogueDetails = analogueCandidates.length
    ? `<div class="past-context-analogues" aria-label="Individual analogue contexts">${analogueCandidates.slice(0, 8).map(item => {
      const label = item.symbol || item.ticker || item.company || item.case_type || item.event_subtype || "Retained analogue";
      const date = item.effective_date || item.event_date || item.date || "date unknown";
      const classification = item.classification || item.match_type || item.analogue_type || "context";
      return `<span><b>${esc(label)}</b><small>${esc(String(classification).replaceAll("_", " "))} · ${esc(date)}</small></span>`;
    }).join("")}</div>`
    : `<div class="past-context-gap"><span><b>No prior exact analogue context retained</b><small>${esc(benchmark.strict_candidate_count ?? 0)} strict candidate${benchmark.strict_candidate_count === 1 ? "" : "s"}; individual benchmark outcomes remain unavailable.</small></span></div>`;
  const matchDetails = `<div class="past-context-separation"><span><small>Similarity context</small><b>${esc(benchmark.strict_candidate_count ?? 0)} strict candidate${benchmark.strict_candidate_count === 1 ? "" : "s"}</b><em>No similarity score or ranked analogue identity is emitted.</em></span><span><small>Evidence trust</small><b>Source quality level ${esc(binding.source_quality_level ?? "unknown")}</b><em>${esc(evidence.length)} hash-bound lineage reference${evidence.length === 1 ? "" : "s"}; trust is not similarity.</em></span></div>${analogueDetails}${bindingDetails}${sourceDetails}`;
  const horizonDetails = `<div class="past-context-horizons">${["1Q", "2Q", "4Q", "8Q"].map(label => {
    const row = horizons[label] || {};
    const hasOutcome = row.status === "mature" && row.return_pct != null && Number.isFinite(Number(row.return_pct));
    const endpoint = hasOutcome ? row.selected_date : row.target_date ? `Target ${row.target_date}; no endpoint` : "No endpoint";
    return `<span data-horizon-status="${esc(row.status || "unavailable")}"><small>${esc(label)}</small><b>${hasOutcome ? esc(pct(Number(row.return_pct))) : esc(ciHumanStatus(row.status))}</b><em>${esc(endpoint)}</em></span>`;
  }).join("")}</div><div class="past-context-gap past-context-gap-three"><span><b>Historical distribution</b><small>Suppressed: no horizon reaches the minimum sample of 3.</small></span><span><b>MAE / MFE</b><small>Not emitted by the backend.</small></span><span><b>Time to resolution</b><small>Not emitted by the backend.</small></span></div>`;
  const blockers = Array.isArray(past.calibration_blockers) ? past.calibration_blockers : [];
  const calibrationChart = ciChart("permission_tree", { status: "available", label: "Historical-context research permissions", root_label: "Historical context", items: [
    { label: "Answer then-versus-now descriptively", allowed: context.answer_contract?.can_answer_then_vs_now ?? null, detail: context.answer_contract?.why },
    { label: "Publish benchmark statistics", allowed: context.answer_contract?.can_publish_benchmark_stats ?? null, detail: "Thin samples remain suppressed" },
    { label: "Feed forecast or valuation", allowed: context.answer_contract?.can_feed_forecast_or_valuation ?? null, detail: "Historical context cannot activate a formal output" },
    { label: "Use for scenario calibration", allowed: past.usable_for_scenario_calibration ?? null, detail: blockers.map(item => String(item).replaceAll("_", " ")).join("; ") || "No blocker detail emitted" },
  ] });
  const calibrationDetails = `<div class="past-context-calibration"><span><small>Then vs now</small><b>${context.answer_contract?.can_answer_then_vs_now ? "Descriptive answer allowed" : "Held back"}</b></span><span><small>Benchmark statistics</small><b>${context.answer_contract?.can_publish_benchmark_stats ? "Publishable" : "Suppressed"}</b></span><span><small>Forecast / valuation feed</small><b>${context.answer_contract?.can_feed_forecast_or_valuation ? "Allowed" : "Prohibited"}</b></span></div>${blockers.length ? `<div class="past-context-blockers">${blockers.map(item => `<span>${esc(String(item).replaceAll("_", " "))}</span>`).join("")}</div>` : ""}`;
  return `<section class="panel span9 past-context-shell" aria-labelledby="pastContextTitle">
    <header class="past-context-header"><div><button type="button" class="overview-back-button" data-research-route="directory_intelligence">Intelligence workspace</button><span class="kicker">Past Context · historical state map</span><h2 id="pastContextTitle">What surrounded this event—and what followed.</h2><p>Compare a retained event setup with history without turning association into certainty. Similarity context, source trust, observed outcomes, and formal-output gates remain visibly separate.</p></div><div class="past-context-seal"><iconify-icon icon="lucide:history" aria-hidden="true"></iconify-icon><b>${esc(r.symbol)}</b><span>Historical context · not forecast</span></div></header>
    <div class="past-context-casebar"><div><small>Selected observed case</small><b>${esc(caseLabel)}</b><span>${esc(binding.effective_date || "date unknown")} · ${esc(caseData.alpha_lane || "Alpha lane unknown")}</span></div>${contexts.length > 1 ? `<div class="past-context-tabs" aria-label="Historical cases">${contexts.map((item, index) => `<button type="button" class="${item.map_id === context.map_id ? "active" : ""}" data-past-context-id="${esc(item.map_id)}" aria-pressed="${item.map_id === context.map_id}"><small>${esc(String(index + 1).padStart(2, "0"))}</small>${esc(String(item.case?.case_type || "case").replaceAll("_", " "))}</button>`).join("")}</div>` : `<span class="pill">1 retained case</span>`}</div>
    <div class="past-context-grid">
      ${pastContextCard("lucide:scan-search", "01", "Retained state", "Four dimensions at the event cutoff", stateChart, "The state map keeps market setup, operating evidence, financial qualification, and policy regime separate. A missing dimension remains a visible gap.", stateDetails, true)}
      ${pastContextCard("lucide:shield-check", "02", "Context ≠ trust", "How the match was made", separationChart, `The match policy is ${String(binding.match_policy || "not emitted").replaceAll("_", " ")}. Candidate count describes available context; source quality describes the evidence behind this case.`, matchDetails)}
      ${pastContextCard("lucide:calendar-range", "03", "Cutoff-safe chronology", "When evidence became observable", timelineChart, `The event study cutoff is ${study.data_cutoff || "not emitted"}. Dates show retained observability, not a causal clock.`, `<div class="past-context-meta"><span>Baseline <b>${esc(market.baseline?.date || study.baseline?.selected_date || "unknown")}</b></span><span>Event <b>${esc(binding.effective_date || "unknown")}</b></span><span>Study cutoff <b>${esc(study.data_cutoff || "unknown")}</b></span></div>`)}
      ${pastContextCard("lucide:chart-no-axes-combined", "04", "Observed aftermath", "Outcome windows—not a forecast", outcomesChart, "Only mature, cutoff-safe raw-price returns are drawn. They are unadjusted for dividends and are historical association, not causal attribution or a prediction.", horizonDetails, true)}
      ${pastContextCard("lucide:lock-keyhole", "05", "Research boundary", "What history can inform today", calibrationChart, context.answer_contract?.why || "Historical context stays descriptive until its qualification gates pass.", calibrationDetails, true)}
    </div>
    <footer class="ci-editorial-footer"><span>${esc(past.semantics || "historical_context/not_forecast")} · research only</span><span>${esc(product.product_version || "historical state map")} · no forecast, valuation, or execution activation</span></footer>
  </section>`;
}

function renderEventsDashboard(r) {
  const events = Array.isArray(r.timeline) ? r.timeline : [];
  const filings = Array.isArray(r.filings) ? r.filings : [];
  const changes = Array.isArray(r.change_intelligence?.items) ? r.change_intelligence.items : [];
  const sources = [...(r.sources?.sources || []), ...(r.sources?.documents || [])];
  const bridges = Array.isArray(r.earnings_bridges?.bridges) ? r.earnings_bridges.bridges : [];
  const dated = events.map(item => ({ date: item.date, label: String(item.type || "Official event").replaceAll("_", " ") })).filter(item => item.date).slice(-7);
  const eventChart = dated.length ? ciChart("timeline", { status: "available", label: "Latest official-document events", items: dated }) : ciBlockedChart("blocked_no_events", "No official events are retained", ["Official filing", "Dated extraction"]);
  const countChart = (label, value, unit) => ciChart("counter", { status: "available", label, value: Number(value || 0), display: String(value || 0), unit });
  const brief = r.brief?.current;
  return `<section class="panel span9 financials-dashboard-shell" aria-labelledby="eventsDashboardTitle">
    <header class="intelligence-dashboard-header"><div><span class="kicker">Events & filings workspace</span><h2 id="eventsDashboardTitle">See what arrived, what changed, and what is sourced.</h2><p>Keep official filings separate from extracted events and approved interpretation, while preserving dates and evidence.</p></div><div class="intelligence-dashboard-symbol"><iconify-icon icon="lucide:files" aria-hidden="true"></iconify-icon><b>${esc(r.symbol)}</b><span>Source before synthesis</span></div></header>
    <div class="intelligence-dashboard-grid">
      ${intelligenceDashboardCard("events", "lucide:calendar-range", "Dated record", "Events", eventChart, "Read extracted official-document events in date order and inspect their retained evidence.")}
      ${intelligenceDashboardCard("filings", "lucide:file-check-2", "Official documents", "Filings", countChart("Retained official filings", filings.length, "OFFICIAL FILINGS"), "Open the PSX and issuer document record with extraction status and page-level evidence.")}
      ${intelligenceDashboardCard("earnings", "lucide:chart-no-axes-combined", "Reported results", "Earnings", countChart("Historical earnings bridges", bridges.length, "REPORTED BRIDGES"), "Inspect source-linked historical earnings changes and the gates holding back forward output.")}
      ${intelligenceDashboardCard("sources", "lucide:link-2", "Source registry", "Sources", countChart("Monitored sources and documents", sources.length, "SOURCE RECORDS"), "Review issuer-owned pages and indexed documents without mixing them with model conclusions.")}
      ${intelligenceDashboardCard("changes", "lucide:history", "Revision trail", "Change digest", countChart("Retained change records", changes.length, "CHANGES"), "See the latest additions and revisions to the company file, separately from financial impact.")}
      ${intelligenceDashboardCard("brief", "lucide:badge-check", "Approved interpretation", brief ? "Approved brief" : "Brief queue", brief ? countChart("Approved current brief", 1, "OWNER-APPROVED BRIEF") : ciBlockedChart("blocked_no_approved_brief", "No owner-approved brief is current", ["Candidate synthesis", "Citation validation", "Owner approval"]), "Read only synthesis that has passed citation checks and explicit owner approval.")}
    </div><footer class="ci-editorial-footer"><span>Research only · no execution</span><span>Documents, events, changes, and interpretation remain distinct</span></footer>
  </section>`;
}

function renderInvestorSnapshot(r) {
  const brain = r.company_brain || {};
  const brief = r.brief?.current || {};
  const sections = brief.sections || {};
  const firstClaim = key => sections[key]?.[0]?.text || null;
  const evidenceItems = overviewObjectItems(r);
  const evidenceChart = evidenceItems.length
    ? ciChart("assumptions", { status: "available", label: "Typed evidence objects by epistemic class", items: evidenceItems, comparable: true, visible_summary: true })
    : ciBlockedChart("blocked_no_typed_objects", "No typed evidence objects are retained", ["Typed object", "Source reference"]);
  const forecast = r.explainability?.forecast_trajectory || {};
  const readinessChart = ciChart("blocked", ciEnvelopeBlocked(forecast, "Formal outputs remain gated", ["Qualified financial history", "Reviewed assumptions", "Deterministic forecast"]));
  const catalystDomain = brainDomain(brain, "catalysts");
  const riskDomain = brainDomain(brain, "risks");
  const signalCount = (r.signal_clusters?.clusters || []).length;
  return `<section class="panel span9 overview-detail-shell snapshot-detail" aria-labelledby="snapshotTitle">
    <header class="overview-detail-header"><div><span class="kicker">Investor snapshot</span><h2 id="snapshotTitle">The research position today</h2><p>A concise reading of what the retained company file supports now—and what it does not yet support.</p></div><button type="button" class="overview-back-button" data-research-route="directory_overview">Overview workspace</button></header>
    <div class="snapshot-kpis" aria-label="Retained market and accounting values">
      <article><span>Price</span><b>Rs ${esc(fmt(r.price?.current))}</b><small>As of ${esc(r.price?.date || "unknown")}</small></article>
      <article><span>20-session move</span><b>${esc(pct(r.price?.ret_20d))}</b><small>Daily price layer</small></article>
      <article><span>Market capitalisation</span><b>${esc(r.fundamentals?.market_cap || "unknown")}</b><small>Retained accounting context</small></article>
      <article><span>Reported EPS</span><b>${esc(r.fundamentals?.eps || "unknown")}</b><small>No browser-side derivation</small></article>
      <article><span>Price / earnings</span><b>${esc(r.fundamentals?.pe || "unknown")}</b><small>Retained value</small></article>
    </div>
    <div class="snapshot-story-grid">
      <article><header class="snapshot-story-heading"><span class="overview-card-icon" aria-hidden="true"><iconify-icon icon="lucide:building-2"></iconify-icon></span><div><span class="kicker">What the business does</span><h3>Company in one paragraph</h3></div></header><p>${esc(r.profile?.business_description || "Unknown — no sourced description is available.")}</p><button type="button" data-research-route="overview">Open company profile</button></article>
      <article><header class="snapshot-story-heading"><span class="overview-card-icon" aria-hidden="true"><iconify-icon icon="lucide:scan-search"></iconify-icon></span><div><span class="kicker">Current situation</span><h3>Latest approved framing</h3></div></header><p>${esc(brief.headline || "No owner-approved brief is current.")}</p></article>
      <article><header class="snapshot-story-heading"><span class="overview-card-icon" aria-hidden="true"><iconify-icon icon="lucide:history"></iconify-icon></span><div><span class="kicker">What changed</span><h3>Evidence-backed most recent change</h3></div></header><p>${esc(firstClaim("what_changed") || "No approved change claim is available.")}</p></article>
      <article><header class="snapshot-story-heading"><span class="overview-card-icon" aria-hidden="true"><iconify-icon icon="lucide:chart-no-axes-combined"></iconify-icon></span><div><span class="kicker">Earnings direction</span><h3>What history can support</h3></div></header><p>${esc(firstClaim("financial_read") || "Qualified history is not sufficient for an earnings direction.")}</p></article>
    </div>
    <div class="overview-detail-grid">
      <article class="overview-evidence-card"><header><span class="kicker">Evidence mix</span><h3>What kinds of intelligence are actually retained</h3></header>${evidenceChart}<p>Lengths compare counts of typed objects. They do not convert evidence volume into conviction.</p></article>
      <article class="overview-evidence-card"><header><span class="kicker">Readiness</span><h3>Why formal conclusions may still be held back</h3></header>${readinessChart}<p>${esc(forecast.text || "Formal outputs appear only when their evidence gates pass.")}</p><button type="button" class="overview-route-button" data-research-route="intelligence">Open Event-to-Value view<iconify-icon icon="lucide:arrow-right" aria-hidden="true"></iconify-icon></button><details class="ci-raw-status"><summary>Technical status</summary><code>${esc(JSON.stringify(forecast.formal_status || { forecast: forecast.status || "unknown" }))}</code></details></article>
    </div>
    <div class="snapshot-signal-grid">
      <article><span>Catalyst coverage</span><b>${esc(ciHumanStatus(catalystDomain.status))}</b><small>${esc((catalystDomain.object_refs || []).length)} typed references</small></article>
      <article><span>Risk coverage</span><b>${esc(ciHumanStatus(riskDomain.status))}</b><small>${esc((riskDomain.object_refs || []).length)} typed references</small></article>
      <article><span>Validated signal clusters</span><b>${esc(signalCount)}</b><small>Absence does not mean no change</small></article>
      <article><span>Monitoring</span><b>${esc(ciHumanStatus(r.monitoring?.status))}</b><small>${esc(r.monitoring?.alert_count ?? 0)} retained alerts</small></article>
    </div>
  </section>`;
}

function renderTimeline(r) {
  const events = r.timeline || [];
  const changes = r.changes || [];
  const brainTimeline = r.company_brain?.timeline || [];
  return `
    <section class="panel span6"><button type="button" class="overview-back-button" data-research-route="directory_intelligence">Intelligence workspace</button><span class="kicker">Evidence-linked chronology</span><h2>Company timeline</h2>
      <p class="section-note">Deterministically classified from official documents. Priority is an extraction-routing weight, not an investment score.</p>
      <div class="brain-timeline" aria-label="Typed Company Brain timeline">${brainTimeline.length ? brainTimeline.slice(-12).reverse().map(item => `<span><time>${esc(item.date || "undated")}</time><b>${esc(objectTypeLabel(item.type))}</b><small>${esc(String(item.source_product || "source").replaceAll("_", " "))}</small></span>`).join("") : `<p>No typed Brain chronology is available.</p>`}</div>
      <div class="timeline">${events.length ? events.map(event => `<article class="timeline-row">
        <time>${esc(String(event.date || "undated").slice(0, 10))}</time>
        <div><span class="pill">${esc(event.type || "other")}</span><span class="priority">priority ${esc(event.priority_weight ?? "unknown")}</span>
        ${(event.evidence || []).map(evidenceLink).join("")}</div>
      </article>`).join("") : `<div class="empty">No official-document event has been extracted for this company yet.</div>`}</div>
    </section>
    <aside class="panel span3"><span class="kicker">Revision ledger</span><h2>Document changes</h2>
      ${changes.length ? changes.map(change => `<div class="change-row"><b>${esc(String(change.date || "undated").slice(0, 16))}</b><span>${esc(change.type || "document revision")}</span>${renderFactDelta(change.fact_delta)}</div>`).join("") : `<p>No content-hash revision is recorded yet.</p>`}
    </aside>`;
}

function renderChangeIntelligence(r) {
  const digest = r.change_intelligence || {};
  const items = digest.items || [];
  const counts = digest.counts || {};
  return `<section class="panel span9">
    <span class="kicker">Official-source change intelligence</span><h2>What changed in the company file</h2>
    <p class="section-note">Built deterministically from official filings, monitored issuer pages, source-linked financial facts and event classifications. This is a research queue, not advice.</p>
    <div class="change-summary">
      ${metric("Status", digest.status || "quiet", `latest ${digest.latest_change_at || "unknown"}`)}
      ${metric("Documents", counts.document ?? 0, `${counts.issuer_document ?? 0} issuer PDFs`)}
      ${metric("Events", counts.event ?? 0, `${counts.financial ?? 0} financial movements`)}
      ${metric("Source pages", counts.source ?? 0, "same-domain hash changes")}
    </div>
    <div class="change-list">${items.length ? items.map(renderChangeItem).join("") : `<div class="empty">No source-backed change digest item is available for this company yet.</div>`}</div>
  </section>`;
}

function renderChangeItem(item) {
  const evidence = item.evidence || {};
  const page = Number(evidence.page) > 0 ? `p.${Number(evidence.page)}` : "source";
  const source = item.source_url ? `<a href="${esc(item.source_url)}" target="_blank" rel="noopener">${esc(page)}</a>` : esc(page);
  const delta = item.kind === "financial" ? renderChangeDelta(item) : "";
  return `<article class="change-card severity-${esc(item.severity || "routine")}">
    <header><div><time>${esc(item.date || "undated")}</time><h3>${esc(item.title || item.kind || "change")}</h3></div><span class="pill">${esc(item.severity || "routine")}</span></header>
    <p>${esc(item.summary || "Source-backed change retained for review.")}</p>
    ${delta}
    <footer><span>${esc(item.kind || "change")}${item.document_id ? ` · ${esc(item.document_id)}` : ""}</span><span>${source}</span></footer>
    ${evidence.text ? `<blockquote>${esc(evidence.text)}</blockquote>` : ""}
  </article>`;
}

function renderChangeDelta(item) {
  const pctText = item.delta_pct == null ? "" : ` · ${pct(item.delta_pct)}`;
  const period = item.previous_period_end && item.period_end ? `${item.previous_period_end} → ${item.period_end}` : item.period_end || "period unknown";
  return `<div class="change-delta"><b>${esc(fmt(item.delta, 2))}${esc(pctText)}</b><span>${esc(period)} · ${esc(item.consolidation || "basis unknown")}</span></div>`;
}

function renderFactDelta(delta) {
  if (!delta) return "";
  const parts = [
    ["added", delta.added], ["changed", delta.changed], ["removed", delta.removed],
  ].filter(([, value]) => Array.isArray(value) && value.length);
  return parts.length ? `<ul class="delta">${parts.map(([label, value]) => `<li>${esc(label)}: ${esc(value.length)}</li>`).join("")}</ul>` : "";
}

function scoreLabel(value) {
  return value == null || value === "" ? "No score" : esc(fmt(value, 1));
}

function confidenceComponentRows(components) {
  const rows = Array.isArray(components)
    ? components
    : components && typeof components === "object"
      ? Object.entries(components).map(([name, component]) => ({ name, ...(component || {}) }))
      : [];
  return rows.map(component => ({
    name: component.name || component.component || component.key || "unnamed_component",
    normalized_score: component.normalized_score ?? component.score ?? null,
    weighted_points: component.weighted_points ?? component.contribution ?? component.points ?? null,
    rationale: component.rationale || component.reason || component.status || "No rationale supplied.",
  }));
}


function caseEvidenceLink(ref) {
  if (!ref || typeof ref !== "object") return "<span>source unavailable</span>";
  const href = safeHref(ref.source_url);
  const label = [ref.document_id || ref.event_id || "source", ref.page ? "p." + ref.page : null].filter(Boolean).join(" · ");
  return href
    ? '<a href="' + href + '" target="_blank" rel="noopener">' + esc(label) + '</a>'
    : '<span>' + esc(label) + '</span>';
}

function renderCaseEvidenceItem(item) {
  const values = Array.isArray(item?.reported_values) ? item.reported_values : [];
  const evidence = Array.isArray(item?.evidence) ? item.evidence : [];
  return '<article class="intel-card case-evidence-card">'
    + '<header><span class="pill">' + esc(item?.fact_id || "observed_fact") + '</span><b>' + esc(item?.event_date || "date unknown") + '</b></header>'
    + '<p>' + esc(item?.statement || "No observed statement emitted.") + '</p>'
    + (values.length ? '<div class="blocked-grid">' + values.map(value => '<span>' + esc(value.label || "value") + '<b>' + esc(value.value || "unknown") + '</b></span>').join("") + '</div>' : "")
    + evidence.map(ref => '<div class="intel-evidence">' + caseEvidenceLink(ref) + ' · ' + esc(ref.source || "source unknown") + ' · ' + esc(ref.content_sha256 ? String(ref.content_sha256).slice(0, 12) : "hash unknown") + '<div>' + esc(ref.text || "No evidence text") + '</div></div>').join("")
    + '</article>';
}

function renderCaseHypothesis(item) {
  return '<article class="intel-card">'
    + '<header><span class="pill">' + esc(item?.status || "retained") + '</span><b>' + esc(item?.alternative_id || "reading") + '</b></header>'
    + '<p>' + esc(item?.reading || "No competing reading emitted.") + '</p>'
    + '<p class="section-note">Rejection condition: ' + esc(item?.rejection_condition || "not_yet_modelled") + '</p>'
    + '</article>';
}

function renderCaseSource(item) {
  return '<div class="intel-evidence">' + caseEvidenceLink(item) + ' · retrieved ' + esc(item?.document_retrieved_at || "unknown") + ' · published ' + esc(item?.document_published_at || "unknown") + '<div>' + esc(item?.document_title || item?.text || "No source title") + '</div></div>';
}

function renderCaseSectionBody(section) {
  const rawStatus = section && section.status ? section.status : "blocked";
  const rawReason = section && section.reason ? section.reason : rawStatus;
  const blocked = !section || String(section.status || "").startsWith("blocked") || section.status === "empty_state";
  if (blocked) {
    return '<div class="blocked-grid"><span>Status <b>' + esc(ciHumanStatus(rawStatus)) + '</b></span><span>Why it is held back <b>' + esc(ciHumanStatus(rawReason)) + '</b></span></div>';
  }
  if (section.key === "conclusion") {
    const validTypes = Array.isArray(window.HennethIntelligenceCaseView?.EPISTEMIC_TYPES)
      ? window.HennethIntelligenceCaseView.EPISTEMIC_TYPES
      : [];
    const epistemicType = validTypes.includes(section.epistemic_type) ? section.epistemic_type : null;
    const epistemicNote = epistemicType
      ? '<p class="section-note">Epistemic type: ' + esc(epistemicType) + '. Research only — not advice.</p>'
      : '<p class="section-note">Epistemic type not emitted. Research only — not advice.</p>';
    return '<p>' + esc(section.text || "Unknown") + '</p>' + epistemicNote;
  }
  if (section.key === "evidence") {
    const items = Array.isArray(section.items) ? section.items : [];
    return items.length ? '<div class="intel-grid">' + items.map(renderCaseEvidenceItem).join("") + '</div>' : '<div class="empty">No observed facts emitted.</div>';
  }
  if (section.key === "hypotheses") {
    const items = Array.isArray(section.items) ? section.items : [];
    return items.length ? '<div class="intel-grid">' + items.map(renderCaseHypothesis).join("") + '</div>' : '<div class="empty">No competing hypotheses emitted.</div>';
  }
  if (section.key === "mechanism") {
    const items = Array.isArray(section.items) ? section.items : [];
    const text = section.text ? '<p>' + esc(section.text) + '</p>' : '';
    const rows = items.map(item => {
      const evidence = Array.isArray(item?.evidence) ? item.evidence : [];
      return '<article><b>' + esc(item?.id || "reported_operating_linkage") + '</b>'
        + '<span>' + esc(item?.text || "No reported operating linkage emitted.") + '</span>'
        + '<em>' + esc(item?.reason || "") + '</em>'
        + evidence.map(ref => '<div class="intel-evidence">' + caseEvidenceLink(ref) + ' · ' + esc(ref?.source || "source unknown") + '</div>').join("")
        + '</article>';
    }).join("");
    return text + (rows ? '<div class="intel-list">' + rows + '</div>' : '<div class="empty">No operating linkage emitted.</div>');
  }
  if (section.key === "confidence") {
    const dims = Array.isArray(section.dimensions) ? section.dimensions : [];
    return dims.length
      ? '<div class="blocked-grid">' + dims.map(dim => '<span>' + esc(dim.name || dim.id || "dimension") + '<b>' + esc(dim.status || dim.score || "unknown") + '</b></span>').join("") + '</div>'
      : '<div class="blocked-grid"><span>Status <b>blocked</b></span><span>Reason <b>not_yet_modelled</b></span></div>';
  }
  if (section.key === "formulas") {
    const formulas = Array.isArray(section.formulas) ? section.formulas : [];
    return formulas.length
      ? '<div class="intel-list">' + formulas.map(formula => '<article><b>' + esc(formula.formula_id || "formula_id_not_emitted") + '</b><span>' + esc((formula.operands || []).join(", ") || "operands not emitted") + '</span><em>' + esc(formula.source || "source not emitted") + '</em></article>').join("") + '</div>'
      : '<div class="blocked-grid"><span>Status <b>blocked</b></span><span>Reason <b>formula_id_not_emitted</b></span></div>';
  }
  if (section.key === "sources") {
    const items = Array.isArray(section.items) ? section.items : [];
    return items.length ? items.map(renderCaseSource).join("") : '<div class="empty">No source lineage emitted.</div>';
  }
  if (Array.isArray(section.items) && section.items.length) {
    return '<div class="intel-list">' + section.items.map(item => '<article><b>' + esc(item.id || item.name || section.key) + '</b><span>' + esc(item.text || item.status || "emitted") + '</span><em>' + esc(item.reason || "") + '</em></article>').join("") + '</div>';
  }
  if (section.text) return '<p>' + esc(section.text) + '</p>';
  return '<div class="blocked-grid"><span>Status <b>' + esc(ciHumanStatus(rawStatus)) + '</b></span><span>Why it is held back <b>' + esc(ciHumanStatus(rawReason)) + '</b></span></div>';
}

function ciCaseSectionChart(section) {
  const key = section?.key || "unknown";
  const status = section?.status || "blocked";
  const missing = { status, reason: ciHumanStatus(section?.reason || status), label: `${key.replaceAll("_", " ")} is held back`, requirements: ["Retained evidence", "Qualified operands", "Deterministic output"] };
  if (key === "evidence") {
    const items = (section.items || []).map(item => ({ date: item.event_date || item.date || item.available_on, label: item.statement || item.title || item.fact_id })).filter(item => item.date);
    return items.length ? ciChart("timeline", { status, label: "Observed evidence in filing order", items }) : ciChart("blocked", missing);
  }
  if (key === "mechanism") {
    const drivers = (section.items || []).map(item => item.id || item.text).filter(Boolean);
    return drivers.length ? ciChart("mechanism", { status, label: "How the observed event may transmit", drivers, target: "Financial output" }) : ciChart("blocked", missing);
  }
  if (key === "confidence") {
    const items = (section.dimensions || []).map(item => ({ label: item.name || item.id, value: Number(String(item.score ?? item.status ?? "").match(/[0-9.]+/)?.[0]), unit: "/100" })).filter(item => Number.isFinite(item.value));
    return items.length ? ciChart("assumptions", { status, label: "Confidence by evidence dimension", items }) : ciChart("blocked", missing);
  }
  if (key === "sources") {
    const items = (section.items || []).map(item => ({ date: item.document_published_at || item.published_at || item.date, label: item.document_title || item.title || item.document_id })).filter(item => item.date);
    return items.length ? ciChart("timeline", { status, label: "Source publication lineage", items }) : ciChart("blocked", missing);
  }
  if (key === "watch_next") {
    const drivers = (section.items || []).map(item => item.text || item.id).filter(Boolean);
    return drivers.length ? ciChart("mechanism", { status, label: "Evidence checks that advance or break the case", drivers, target: "Case status" }) : ciChart("blocked", missing);
  }
  const available = !String(status).startsWith("blocked") && status !== "empty_state";
  return available
    ? ciChart("counter", { status, label: `${key.replaceAll("_", " ")} state`, value: 1, display: "ON FILE", unit: "RETAINED CASE SECTION" })
    : ciChart("blocked", missing);
}

function renderIntelligenceCase(r, caseId) {
  const api = caseViewApi();
  const requestedTicker = state.caseRoute?.ticker || r?.symbol || null;
  const lookup = api?.findCase ? api.findCase(r, caseId, requestedTicker) : { ok: false, reason: "intelligence_cases_state_missing", payload: { cases: [] }, case: null };
  if (!lookup.ok) {
    const title = lookup.reason === "case_not_found" ? "Case not found" : "Intelligence case unavailable";
    const reason = lookup.reason || "intelligence_cases_state_missing";
    return '<section class="panel span9 blocked-shell case-shell" aria-labelledby="caseTitle"><span class="kicker">Intelligence case</span><h2 id="caseTitle">' + esc(title) + '</h2><p class="section-note">Read-only case surface. Missing objects stay fail-closed. This is research, not advice.</p><div class="blocked-grid"><span>Ticker <b>' + esc(requestedTicker || "unknown") + '</b></span><span>Requested case <b>' + esc(caseId || "unknown") + '</b></span><span>Reason <b>' + esc(reason) + '</b></span></div><p><button type="button" class="chrome-btn" data-case-close="1">Back to company file</button></p></section>';
  }
  const caseObject = lookup.case;
  const lifecycle = api.LIFECYCLE || ["Observed", "Corroborated", "Modelled", "Validated", "Published", "Monitoring", "Closed"];
  const sections = (api.SECTIONS || []).map(([key, label]) => {
    const section = api.resolveSection(caseObject, key);
    const number = String((api.SECTIONS || []).findIndex(item => item[0] === key) + 1).padStart(2, "0");
    return '<section class="intel-section ci-editorial-tile" data-case-section="' + esc(key) + '"><header><div><span class="ci-section-number">' + esc(number) + '</span><h3>' + esc(label) + '</h3></div><span class="pill">' + esc(ciHumanStatus(section.status || "blocked")) + '</span></header>' + ciCaseSectionChart(section) + '<div class="ci-editorial-copy">' + renderCaseSectionBody(section) + '</div><details class="ci-raw-status"><summary>Technical status</summary><code>' + esc(section.status || "blocked") + '</code></details></section>';
  }).join("");
  const stage = lifecycle.map(name => '<span class="pill' + (name === caseObject.status ? " active" : "") + '">' + esc(name) + '</span>').join("");
  return '<section class="panel span9 intel-shell case-shell" aria-labelledby="caseTitle">'
    + '<span class="kicker">Intelligence case</span>'
    + '<h2 id="caseTitle">' + esc(caseObject.symbol || r.symbol) + ' · ' + esc(caseObject.case_id) + '</h2>'
    + '<p class="section-note">Observed evidence only. Later Event-to-Value outputs appear when the case object emits them. Research, not advice.</p>'
    + '<p><button type="button" class="chrome-btn" data-case-close="1">Back to company file</button></p>'
    + '<div class="blocked-grid">'
    + '<span>Status <b>' + esc(caseObject.status || "unknown") + '</b></span>'
    + '<span>Family <b>' + esc(caseObject.case_family || "unknown") + '</b></span>'
    + '<span>Type <b>' + esc(caseObject.case_type || "unknown") + '</b></span>'
    + '<span>Epistemic type <b>' + esc(caseObject.epistemic_type || "unknown") + '</b></span>'
    + '<span>As of <b>' + esc(caseObject.as_of || "unknown") + '</b></span>'
    + '<span>Target <b>' + esc(caseObject.target_symbol || "none emitted") + '</b></span>'
    + '</div>'
    + '<div class="intel-watch" aria-label="Case lifecycle">' + stage + '</div>'
    + sections
    + '</section>';
}

function renderIntelligenceConfidence(r) {
  const confidence = r.intelligence_confidence || {};
  const assessments = Array.isArray(confidence.assessments) ? confidence.assessments : [];
  const aggregateScore = confidence.aggregate_score ?? confidence.score ?? null;
  const aggregateBand = confidence.aggregate_band || confidence.band || "no-score";
  const status = confidence.status || (assessments.length ? "available" : "no_score");
  const noScore = aggregateScore == null && !assessments.length;
  const cards = assessments.length ? assessments.map(assessment => {
    const components = confidenceComponentRows(assessment.components);
    return `<article class="confidence-card">
      <header><div><span class="pill">${esc(assessment.band || "unknown band")}</span><h4>${esc(assessment.source_cluster_id || assessment.confidence_id || "source cluster")}</h4></div><b>${scoreLabel(assessment.score)}</b></header>
      <div class="confidence-components">${components.length ? components.map(component => `<div><span>${esc(component.name)}</span><b>${scoreLabel(component.normalized_score)}</b><em>${component.weighted_points == null ? "points unknown" : `${esc(fmt(component.weighted_points, 2))} pts`}</em><small>${esc(component.rationale)}</small></div>`).join("") : `<div><span>components</span><b>0</b><small>No component rows supplied.</small></div>`}</div>
      <footer><span>${esc((assessment.provenance_refs || []).length)} provenance reference${(assessment.provenance_refs || []).length === 1 ? "" : "s"}</span></footer>
    </article>`;
  }).join("") : `<div class="empty">No intelligence-confidence assessment is available for this company.</div>`;
  return `<section class="intel-section confidence-panel" aria-label="Intelligence confidence">
    <header><h3>Intelligence confidence</h3><span class="pill">${esc(status)}</span></header>
    <div class="confidence-summary ${noScore ? "is-empty" : ""}">
      <span>Aggregate score <b>${scoreLabel(aggregateScore)}</b></span>
      <span>Aggregate band <b>${esc(aggregateBand)}</b></span>
      <span>Assessments <b>${esc(confidence.assessment_count ?? assessments.length)}</b></span>
    </div>
    <p class="section-note">Displayed exactly as emitted by the intelligence-confidence state. The browser does not calculate, reweight, or infer missing scores.</p>
    <div class="confidence-grid">${cards}</div>
  </section>`;
}

function renderIntelligenceCaseIndex(r) {
  const api = caseViewApi();
  const discovery = api?.discoverableCases ? api.discoverableCases(r) : { status: "absent", reason: "intelligence_cases_state_missing", items: [] };
  if (discovery.status === "absent" || discovery.status === "empty") return "";
  if (discovery.status === "invalid") {
    return '<section class="intel-section case-index" aria-label="Intelligence cases"><header><h3>Intelligence cases</h3><span class="pill">blocked</span></header><div class="blocked-grid"><span>Status <b>blocked</b></span><span>Reason <b>' + esc(discovery.reason || "intelligence_cases_shape_invalid") + '</b></span></div><p class="section-note">Projected case objects are shown only when the shape is valid. This list is research, not a forecast or valuation.</p></section>';
  }
  const cards = discovery.items.map(item => {
    const href = /^\/company\/[A-Z0-9]+\/intelligence\/[A-Za-z0-9._-]+$/.test(item.href) ? item.href : "";
    if (!href) return '';
    return '<article class="intel-card case-index-card"><header><span class="pill">' + esc(item.status) + '</span><b>' + esc(item.case_id) + '</b></header><h3>' + esc(item.title) + '</h3><p>' + esc(item.summary || "No case summary emitted.") + '</p><a class="case-index-link" href="' + esc(href) + '">Open case</a></article>';
  }).join("");
  if (!cards) return "";
  return '<section class="intel-section case-index" aria-label="Intelligence cases"><header><h3>Intelligence cases</h3><span class="pill">' + esc(discovery.items.length) + '</span></header><p class="section-note">Read-only links to projected Intelligence Cases. Status is displayed as emitted; blocked later sections are not treated as forecasts or valuations.</p><div class="intel-grid">' + cards + '</div></section>';
}


function ciEnvelopeBlocked(section, fallbackLabel, fallbackRequirements = []) {
  return {
    status: section?.status || "blocked",
    reason: section?.text || section?.reason || ciHumanStatus(section?.status),
    label: section?.label || fallbackLabel,
    requirements: section?.missing_gates?.length ? section.missing_gates : fallbackRequirements,
    available: 0,
  };
}

function ciActiveObservedCase(r) {
  const cases = Array.isArray(r.intelligence_cases?.cases) ? r.intelligence_cases.cases : [];
  if (r.symbol === "MLCF") return cases.find(item => item.case_type !== "acquisition_control") || null;
  if (r.symbol === "MARI") return cases.find(item => item.case_family === "e_and_p") || null;
  return cases[0] || null;
}

function renderIntelligence(r) {
  const envelope = r.explainability || {};
  const observation = envelope.observation || {};
  const mechanism = envelope.transmission_mechanism || {};
  const forecast = envelope.forecast_trajectory || {};
  const assumptions = envelope.key_assumptions || {};
  const expectations = envelope.expectations_gap || {};
  const conclusion = envelope.conclusion || {};
  const monitoring = envelope.monitoring || {};
  const studies = Array.isArray(r.event_studies) ? r.event_studies : [];
  const activeCase = ciActiveObservedCase(r);
  const caseFacts = Array.isArray(activeCase?.observed_facts) ? activeCase.observed_facts : [];
  const observationItems = caseFacts.map(item => ({ date: item.event_date, label: item.statement || item.fact_id })).filter(item => item.date);
  if (!observationItems.length && observation.date && !(r.symbol === "MLCF" && !activeCase)) observationItems.push({ date: observation.date, label: observation.event_subtype || observation.event_type || observation.label });
  const observationBlocked = r.symbol === "MLCF" && !activeCase;
  const eventSummary = activeCase?.summary || (observationBlocked
    ? observation.vertical_case?.text || "No retained plant, capacity-expansion, or commissioning case is currently emitted for MLCF. The PIOC record remains a separate observed corporate-control case and is not presented as the cement expansion model."
    : observation.text || "No eligible evidence-backed event has been retained for this company.");
  const drivers = Array.isArray(mechanism.drivers) ? mechanism.drivers : [];
  const targetsByDriver = new Map((mechanism.chain || []).map(item => [item.driver, item.statement_line || item.target]));
  const assumptionItems = (assumptions.items || []).map(item => ({ label: item.name || item.label, value: item.value == null || item.value === "" ? null : Number(item.value), unit: item.unit })).filter(item => Number.isFinite(item.value));
  const forecastPayload = Array.isArray(forecast.bear) && Array.isArray(forecast.base) && Array.isArray(forecast.bull)
    ? { status: forecast.status, label: forecast.label, bear: forecast.bear, base: forecast.base, bull: forecast.bull, unit: forecast.unit || "model output" }
    : ciEnvelopeBlocked(forecast, "Eight-quarter forecast trajectory", ["Qualified financial history", "Approved assumptions", "Eight-quarter output"]);
  const expectationPayload = expectations.market != null && expectations.market !== "" && expectations.base_case != null && expectations.base_case !== "" && Number.isFinite(Number(expectations.market)) && Number.isFinite(Number(expectations.base_case))
    ? { status: expectations.status, label: expectations.label, market: Number(expectations.market), base: Number(expectations.base_case), unit: expectations.unit || "PKR/share" }
    : ciEnvelopeBlocked(expectations, "Expectations gap", ["Current retained price", "Qualified fair value", "Comparable per-share basis"]);
  const monitorItems = (monitoring.what_to_watch || []).map(item => ({ date: item.date, label: item.title })).filter(item => item.date);
  const caseDiscovery = caseViewApi()?.discoverableCases?.(r);
  const caseLinks = caseDiscovery?.items?.length ? `<div class="ci-case-links">${caseDiscovery.items.map(item => `<a href="${esc(item.href)}"><span>${esc(item.case_id === activeCase?.case_id ? "Active observed case" : "Separate observed case")}</span><b>${esc(item.title || item.case_id)}</b></a>`).join("")}</div>` : "";
  const tile = (number, title, status, chart, copy, wide = false) => `<article class="ci-editorial-tile${wide ? " ci-tile-wide" : ""}"><header><div><span class="ci-section-number">${number}</span><h3>${esc(title)}</h3></div><span class="pill">${esc(ciHumanStatus(status))}</span></header>${chart}<p>${esc(copy || "No explanatory text was emitted.")}</p></article>`;
  return `<section class="panel span9 intel-shell ci-editorial-shell">
    <header class="ci-editorial-header"><div><button type="button" class="overview-back-button" data-research-route="directory_intelligence">Intelligence workspace</button><span class="kicker">Event-to-Value intelligence</span><h2>What Henneth is saying</h2><p>${esc(eventSummary)}</p></div><div class="ci-editorial-index"><b>${esc(envelope.schema_version ? "07" : "—")}</b><span>explainability sections</span><small>${esc(studies.length)} historical reference record${studies.length === 1 ? "" : "s"}</small></div></header>
    <div class="ci-editorial-grid">
      ${tile("01", "Observation & event", observationBlocked ? "blocked_no_active_expansion_case" : observation.status, observationItems.length ? ciChart("timeline", { status: observation.status, label: "Retained dated observation", items: observationItems }) : ciChart("blocked", observationBlocked ? { status: observation.vertical_case?.status || "blocked_no_active_expansion_case", label: "No active expansion event is emitted", reason: observation.vertical_case?.text || eventSummary, requirements: ["Official filing", "Expansion or commissioning event", "Canonical case binding"], available: 0 } : ciEnvelopeBlocked(observation, "No active expansion event is emitted", ["Official filing", "Expansion or commissioning event", "Canonical case binding"])), eventSummary, true)}
      ${caseLinks ? `<div class="ci-editorial-case-row">${caseLinks}</div>` : ""}
      ${tile("02", "Transmission mechanism", mechanism.status, drivers.length ? ciChart("mechanism", { status: mechanism.status, label: `${mechanism.sector_model || r.sector || "Sector"} operating-driver map`, drivers, targets: drivers.map(item => targetsByDriver.get(item) || "Financial line") }) : ciChart("blocked", ciEnvelopeBlocked(mechanism, "Sector transmission mechanism", ["Sector driver graph", "Operating driver", "Financial line"])), mechanism.text)}
      ${tile("03", "Forecast trajectory", forecast.status, forecastPayload.base ? ciChart("fan", forecastPayload) : ciChart("blocked", forecastPayload), forecast.text, true)}
      ${tile("04", "Key assumptions", assumptions.status, assumptionItems.length ? ciChart("assumptions", { status: assumptions.status, label: assumptions.label, items: assumptionItems }) : ciChart("blocked", { ...ciEnvelopeBlocked(assumptions, "Key formal-engine assumptions", ["Source-labelled assumption", "Owner review"]), reason: "Waiting for reviewed model assumptions" }), assumptions.text)}
      ${tile("05", "Expectations gap", expectations.status, expectationPayload.market != null ? ciChart("expectations", expectationPayload) : ciChart("blocked", expectationPayload), expectations.text)}
      ${tile("06", "Research conclusion", conclusion.status, ciChart("blocked", ciEnvelopeBlocked(conclusion, "Formal conclusion held back", ["Qualified forecast", "Qualified valuation", "Expectations comparison"])), conclusion.text, true)}
      ${tile("07", "Monitoring", monitoring.status, monitorItems.length ? ciChart("timeline", { status: monitoring.status, label: "What the retained monitor is watching", items: monitorItems }) : ciChart("counter", { status: monitoring.status, label: monitoring.label || "Monitoring", value: Number(monitoring.alert_count || 0), display: String(monitoring.alert_count || 0), unit: "RETAINED ALERTS" }), monitoring.text, true)}
    </div>
    <footer class="ci-editorial-footer"><span>Research only · no execution</span><span>Every visual mark maps to the row-level explainability envelope</span></footer>
  </section>`;
}

function renderThesisMonitor(r) {
  const monitor = r.thesis_monitoring || {};
  const theses = Array.isArray(monitor.theses) ? monitor.theses : [];
  const readiness = monitor.financial_readiness || {};
  const status = monitor.status || "unknown";
  const canonicalStatuses = "Strengthening Stable Weakening Broken";
  const thesisCards = theses.length ? theses.map(renderThesisCard).join("") : `<div class="empty thesis-empty">No active thesis is being monitored for ${esc(r.symbol)}. Company Intelligence will show a thesis here only after the backend emits one with official-source checks.</div>`;
  return `<section class="panel span9 thesis-shell" aria-labelledby="thesisTitle">
    <button type="button" class="overview-back-button" data-research-route="directory_ownership">Ownership &amp; Peers workspace</button><span class="kicker">Thesis monitor</span><h2 id="thesisTitle">Active thesis checks</h2>
    <p class="section-note">Private user-authored theses are stored separately from Henneth's deterministic monitoring. Status is displayed exactly from each source; the browser does not infer upgrades or breaks.</p>
    ${renderPrivateTheses(r)}
    <div class="thesis-status">
      <span>Company status <b>${esc(status)}</b></span>
      <span>Active theses <b>${esc(monitor.active_thesis_count ?? theses.length)}</b></span>
      <span>Source clusters <b>${esc(monitor.source_cluster_count ?? 0)}</b></span>
      <span>Financial readiness <b>${esc(readiness.status || "unknown")}</b></span>
    </div>
    ${renderManagementDelivery(r)}
    ${thesisCards}
  </section>`;
}

function emptyThesisDraft(symbol) {
  return {
    id: null,
    symbol,
    thesis: "",
    expected_earnings_path: "",
    catalysts: "",
    risks: "",
    required_evidence: "",
    kill_conditions: "",
    user_fair_value_assumption: "",
    user_fair_value_basis: "",
    status: "Stable",
  };
}

function thesisDraft(symbol) {
  return state.theses.drafts[symbol] || (state.theses.drafts[symbol] = emptyThesisDraft(symbol));
}

function linesToArray(value) {
  return String(value || "").split(/\r?\n/).map(line => line.trim()).filter(Boolean);
}

function listLimitError(items) {
  if (items.length > THESIS_LIMITS.listItems) return true;
  return items.some(item => item.length > THESIS_LIMITS.listItem);
}

function arrayToLines(value) {
  return Array.isArray(value) ? value.join("\n") : "";
}

function hydrateThesisDraft(row) {
  return {
    id: row.id,
    symbol: row.symbol,
    thesis: row.thesis || "",
    expected_earnings_path: row.expected_earnings_path || "",
    catalysts: arrayToLines(row.catalysts),
    risks: arrayToLines(row.risks),
    required_evidence: arrayToLines(row.required_evidence),
    kill_conditions: arrayToLines(row.kill_conditions),
    user_fair_value_assumption: row.user_fair_value_assumption ?? "",
    user_fair_value_basis: row.user_fair_value_basis || "",
    status: THESIS_STATUSES.includes(row.status) ? row.status : "Stable",
  };
}

function readableThesisError(error) {
  const map = {
    auth_expired: "Your session expired. Sign in again, then retry.",
    schema_unavailable: "Private thesis storage is not activated yet. The company_theses table is unavailable or not visible to this account.",
    network_unavailable: "Private thesis storage could not be reached. Your draft is still on this screen.",
    invalid_form: "Complete the required thesis fields and keep them inside the table limits. A private fair value must be above 0, no higher than 1,000,000, and include a basis.",
    request_failed: "Private thesis storage returned an unavailable state. Try again shortly.",
  };
  return map[error] || "Private thesis storage is unavailable. Try again shortly.";
}

function privateThesisStorageMeta() {
  return state.data?.meta?.private_thesis_storage || {};
}

function privateThesisSmokeText() {
  const smoke = state.theses.smoke || {};
  if (smoke.running) return "Checking this signed-in owner session...";
  if (smoke.status === "passed") {
    const checked = smoke.checkedAt ? ` at ${String(smoke.checkedAt).slice(11, 16)} UTC` : "";
    const rowCount = smoke.rowCount == null ? "unknown row visibility" : `${smoke.rowCount} visible sample row${smoke.rowCount === 1 ? "" : "s"}`;
    return `Read check passed${checked}: company_theses was reachable with this bearer token (${rowCount}).`;
  }
  if (smoke.status === "failed") return `Read check failed: ${readableThesisError(smoke.error)}`;
  return "Not run in this browser session.";
}

async function runPrivateThesisSmokeCheck() {
  state.theses.smoke = { running: true, status: "checking", checkedAt: null, error: null, rowCount: null };
  renderDesk();
  try {
    // Read-only owner-session smoke test: this must never create, edit, archive, restore or delete thesis rows.
    const rows = await companyThesisRequest(`?select=${encodeURIComponent("id,symbol,updated_at")}&limit=1`, { method: "GET" });
    state.theses.smoke = {
      running: false,
      status: "passed",
      checkedAt: new Date().toISOString(),
      error: null,
      rowCount: Array.isArray(rows) ? rows.length : null,
    };
  } catch (error) {
    state.theses.smoke = {
      running: false,
      status: "failed",
      checkedAt: new Date().toISOString(),
      error: error.message || "request_failed",
      rowCount: null,
    };
  } finally {
    renderDesk();
  }
}

function renderPrivateTheses(r) {
  const rows = state.theses.bySymbol[r.symbol] || [];
  const active = rows.filter(row => !row.archived);
  const archived = rows.filter(row => row.archived);
  const draft = thesisDraft(r.symbol);
  const formTitle = draft.id ? "Edit private thesis" : "Create private thesis";
  const storage = privateThesisStorageMeta();
  const liveStatus = storage.live_verification_status || "unknown";
  const schemaStatus = storage.schema_status || "unknown";
  const liveCopy = liveStatus === "verified"
    ? "Live verification receipt is recorded."
    : "Live completion is not verified. Cross-user RLS proof is still required before this storage is complete.";
  return `<section class="private-thesis" aria-labelledby="privateThesisTitle">
    <header>
      <div><span class="kicker">Private thesis notebook</span><h3 id="privateThesisTitle">${esc(formTitle)}</h3></div>
      <span class="pill">${esc(liveStatus === "verified" ? "live verified" : `live ${liveStatus}`)}</span>
    </header>
    <p class="section-note">These rows are private user input in Supabase <code>company_theses</code>. They do not change Henneth's deterministic thesis monitoring below.</p>
    <div class="private-thesis-verification" aria-live="polite">
      <span>Schema receipt <b>${esc(schemaStatus)}</b></span>
      <span>Live verification <b>${esc(liveStatus)}</b></span>
      <span>Owner-session read check <b>${esc(privateThesisSmokeText())}</b></span>
      <p>${esc(liveCopy)}</p>
      <button id="privateThesisSmoke" class="secondary" type="button" ${state.theses.smoke?.running ? "disabled" : ""}>${state.theses.smoke?.running ? "Checking" : "Check live storage"}</button>
    </div>
    ${state.theses.error ? `<div class="thesis-error" role="alert">${esc(readableThesisError(state.theses.error))}</div>` : ""}
    <form id="privateThesisForm" class="private-thesis-form">
      <label class="wide"><span>Thesis</span><textarea id="privateThesisText" required maxlength="5000" rows="3" placeholder="Write the company thesis in your own words.">${esc(draft.thesis)}</textarea></label>
      <label><span>Status</span><select id="privateThesisStatus">${THESIS_STATUSES.map(status => `<option value="${esc(status)}" ${draft.status === status ? "selected" : ""}>${esc(status)}</option>`).join("")}</select></label>
      <label><span>Expected earnings path</span><input id="privateThesisEarnings" type="text" maxlength="2000" value="${esc(draft.expected_earnings_path)}" placeholder="Private user view"></label>
      <label><span>Private user fair value</span><input id="privateThesisFairValue" type="number" min="0.01" max="1000000" step="0.01" value="${esc(draft.user_fair_value_assumption)}" placeholder="Optional"></label>
      <label><span>Fair-value basis</span><input id="privateThesisFairValueBasis" type="text" maxlength="1000" value="${esc(draft.user_fair_value_basis)}" placeholder="Required if fair value is entered"></label>
      <label><span>Catalysts, one per line</span><textarea id="privateThesisCatalysts" rows="3" data-list-limit="50" data-line-limit="500">${esc(draft.catalysts)}</textarea></label>
      <label><span>Risks, one per line</span><textarea id="privateThesisRisks" rows="3" data-list-limit="50" data-line-limit="500">${esc(draft.risks)}</textarea></label>
      <label><span>Required evidence, one per line</span><textarea id="privateThesisEvidenceRequired" rows="3" data-list-limit="50" data-line-limit="500">${esc(draft.required_evidence)}</textarea></label>
      <label><span>Kill conditions, one per line</span><textarea id="privateThesisKill" rows="3" data-list-limit="50" data-line-limit="500">${esc(draft.kill_conditions)}</textarea></label>
      <p class="private-thesis-note">Any fair value here is Private user input, never Henneth output, a target price, or advice.</p>
      <div class="private-thesis-actions">
        <button type="submit" ${state.theses.saving ? "disabled" : ""}>${state.theses.saving ? "Saving" : draft.id ? "Save edits" : "Create thesis"}</button>
        ${draft.id ? `<button id="privateThesisCancel" class="secondary" type="button">Cancel edit</button>` : ""}
      </div>
    </form>
    <div class="private-thesis-list">
      <h4>Active private theses</h4>
      ${active.length ? active.map(renderPrivateThesisRow).join("") : `<div class="empty thesis-empty">No private thesis has been saved for ${esc(r.symbol)}.</div>`}
      ${archived.length ? `<details class="private-thesis-archive"><summary>Archived private theses (${esc(archived.length)})</summary>${archived.map(renderPrivateThesisRow).join("")}</details>` : ""}
    </div>
  </section>`;
}

function renderPrivateThesisRow(row) {
  const list = (label, items) => Array.isArray(items) && items.length
    ? `<div><b>${esc(label)}</b><span>${items.map(esc).join(" · ")}</span></div>`
    : "";
  return `<article class="private-thesis-card ${row.archived ? "is-archived" : ""}">
    <header><div><span class="pill">${esc(row.status || "Stable")}</span><h4>${esc(row.thesis || "Private thesis")}</h4></div><time>${esc(String(row.updated_at || row.created_at || "undated").slice(0, 10))}</time></header>
    <div class="private-thesis-meta">
      <span>Expected earnings path <b>${esc(row.expected_earnings_path || "not specified")}</b></span>
      <span>Private user fair value <b>${row.user_fair_value_assumption == null ? "not entered" : `Rs ${esc(fmt(row.user_fair_value_assumption, 2))}`}</b><small>Private user input, never Henneth output.</small></span>
      <span>Basis <b>${esc(row.user_fair_value_basis || "not specified")}</b></span>
    </div>
    <div class="private-thesis-points">
      ${list("Catalysts", row.catalysts)}${list("Risks", row.risks)}${list("Required evidence", row.required_evidence)}${list("Kill conditions", row.kill_conditions)}
    </div>
    <footer>
      <button type="button" data-thesis-action="edit" data-thesis-id="${esc(row.id)}">Edit</button>
      <button type="button" data-thesis-action="${row.archived ? "restore" : "archive"}" data-thesis-id="${esc(row.id)}">${row.archived ? "Restore" : "Archive"}</button>
      <button type="button" class="danger" data-thesis-action="delete" data-thesis-id="${esc(row.id)}">Delete permanently</button>
    </footer>
  </article>`;
}

function privateThesisPayload(symbol) {
  const fairValueText = $("privateThesisFairValue")?.value.trim() || "";
  const fairValue = fairValueText === "" ? null : Number(fairValueText);
  return {
    symbol,
    thesis: $("privateThesisText")?.value.trim() || "",
    expected_earnings_path: $("privateThesisEarnings")?.value.trim() || null,
    catalysts: linesToArray($("privateThesisCatalysts")?.value),
    risks: linesToArray($("privateThesisRisks")?.value),
    required_evidence: linesToArray($("privateThesisEvidenceRequired")?.value),
    kill_conditions: linesToArray($("privateThesisKill")?.value),
    user_fair_value_assumption: fairValue,
    user_fair_value_basis: $("privateThesisFairValueBasis")?.value.trim() || null,
    status: THESIS_STATUSES.includes($("privateThesisStatus")?.value) ? $("privateThesisStatus").value : "Stable",
    archived: false,
    updated_at: new Date().toISOString(),
  };
}

function payloadToDraft(payload, id = null) {
  return {
    id,
    symbol: payload.symbol,
    thesis: payload.thesis || "",
    expected_earnings_path: payload.expected_earnings_path || "",
    catalysts: arrayToLines(payload.catalysts),
    risks: arrayToLines(payload.risks),
    required_evidence: arrayToLines(payload.required_evidence),
    kill_conditions: arrayToLines(payload.kill_conditions),
    user_fair_value_assumption: payload.user_fair_value_assumption ?? "",
    user_fair_value_basis: payload.user_fair_value_basis || "",
    status: THESIS_STATUSES.includes(payload.status) ? payload.status : "Stable",
  };
}

function validatePrivateThesisPayload(payload) {
  if (!currentPilotSymbols().has(payload.symbol)) return false;
  if (!payload.thesis || payload.thesis.length > THESIS_LIMITS.thesis) return false;
  if ((payload.expected_earnings_path || "").length > THESIS_LIMITS.expected) return false;
  if ((payload.user_fair_value_basis || "").length > THESIS_LIMITS.basis) return false;
  if (payload.user_fair_value_assumption != null && (!Number.isFinite(payload.user_fair_value_assumption) || payload.user_fair_value_assumption <= 0 || payload.user_fair_value_assumption > THESIS_LIMITS.fairValueMax || !payload.user_fair_value_basis)) return false;
  return [payload.catalysts, payload.risks, payload.required_evidence, payload.kill_conditions].every(items => Array.isArray(items) && !listLimitError(items));
}

function findPrivateThesis(id) {
  return Object.values(state.theses.bySymbol).flat().find(row => row.id === id);
}

async function savePrivateThesis(symbol) {
  const draft = thesisDraft(symbol);
  const payload = privateThesisPayload(symbol);
  state.theses.drafts[symbol] = payloadToDraft(payload, draft.id);
  if (!validatePrivateThesisPayload(payload)) {
    state.theses.error = "invalid_form";
    renderDesk({ focusThesis: true });
    return;
  }
  state.theses.saving = true;
  state.theses.error = null;
  renderDesk({ focusThesis: true });
  try {
    if (draft.id) await companyThesisRequest(`?id=eq.${encodeURIComponent(draft.id)}`, { method: "PATCH", body: payload, prefer: "return=representation" });
    else await companyThesisRequest("", { method: "POST", body: payload, prefer: "return=representation" });
    state.theses.drafts[symbol] = emptyThesisDraft(symbol);
    await loadCompanyTheses();
  } catch (error) {
    state.theses.error = error.message || "request_failed";
  } finally {
    state.theses.saving = false;
    renderDesk({ focusThesis: true });
  }
}

async function setPrivateThesisArchived(id, archived) {
  state.theses.saving = true;
  state.theses.error = null;
  renderDesk();
  try {
    await companyThesisRequest(`?id=eq.${encodeURIComponent(id)}`, { method: "PATCH", body: { archived, updated_at: new Date().toISOString() }, prefer: "return=representation" });
    await loadCompanyTheses();
  } catch (error) {
    state.theses.error = error.message || "request_failed";
  } finally {
    state.theses.saving = false;
    renderDesk();
  }
}

async function deletePrivateThesis(id) {
  if (!window.confirm("Permanently delete this private thesis? This cannot be undone.")) return;
  state.theses.saving = true;
  state.theses.error = null;
  renderDesk();
  try {
    await companyThesisRequest(`?id=eq.${encodeURIComponent(id)}`, { method: "DELETE", prefer: "return=minimal" });
    await loadCompanyTheses();
  } catch (error) {
    state.theses.error = error.message || "request_failed";
  } finally {
    state.theses.saving = false;
    renderDesk();
  }
}

function bindPrivateTheses(row) {
  const form = $("privateThesisForm");
  if (form) {
    form.onsubmit = event => {
      event.preventDefault();
      savePrivateThesis(row.symbol);
    };
  }
  $("privateThesisCancel")?.addEventListener("click", () => {
    state.theses.drafts[row.symbol] = emptyThesisDraft(row.symbol);
    state.theses.error = null;
    renderDesk({ focusThesis: true });
  });
  $("privateThesisSmoke")?.addEventListener("click", runPrivateThesisSmokeCheck);
  document.querySelectorAll("[data-thesis-action]").forEach(button => {
    button.onclick = () => {
      const id = button.dataset.thesisId;
      const action = button.dataset.thesisAction;
      const thesis = findPrivateThesis(id);
      if (!id || !thesis) return;
      if (action === "edit") {
        state.theses.drafts[row.symbol] = hydrateThesisDraft(thesis);
        state.theses.error = null;
        renderDesk({ focusThesis: true });
      } else if (action === "archive") {
        setPrivateThesisArchived(id, true);
      } else if (action === "restore") {
        setPrivateThesisArchived(id, false);
      } else if (action === "delete") {
        deletePrivateThesis(id);
      }
    };
  });
}

function deliveryArray(value) {
  if (Array.isArray(value)) return value.map(item => String(item || "").trim()).filter(Boolean);
  const text = String(value || "").trim();
  return text ? [text] : [];
}

function deliveryValue(value, fallback = "unknown") {
  return value == null || value === "" ? fallback : esc(value);
}

function renderDeliveryList(label, values, empty) {
  const rows = deliveryArray(values);
  return `<div><span>${esc(label)}</span><b>${rows.length ? rows.map(esc).join(" · ") : esc(empty || "none emitted")}</b></div>`;
}

function renderManagementDelivery(r) {
  const delivery = r.management_delivery && typeof r.management_delivery === "object" && !Array.isArray(r.management_delivery)
    ? r.management_delivery
    : null;
  if (!delivery) {
    return `<section class="management-delivery" aria-labelledby="managementDeliveryTitle">
      <header><div><span class="kicker">Management delivery</span><h3 id="managementDeliveryTitle">Guidance follow-through</h3></div><span class="pill">unavailable_not_generated</span></header>
      <p class="section-note">Management delivery has not been generated into this CI slice yet. The browser does not infer blocked guidance, match assertions, score delivery, forecast results, value the company, or turn this into advice.</p>
      <div class="delivery-empty">Unavailable: not generated.</div>
    </section>`;
  }
  const records = Array.isArray(delivery.records) ? delivery.records : [];
  return `<section class="management-delivery" aria-labelledby="managementDeliveryTitle">
    <header><div><span class="kicker">Management delivery</span><h3 id="managementDeliveryTitle">Guidance follow-through</h3></div><span class="pill">${esc(delivery.status || "unknown")}</span></header>
    <p class="section-note">Read-only backend output. The browser does not match assertions, score delivery, forecast results, value the company, or turn this into advice.</p>
    <div class="delivery-grid">
      <div><span>Company status</span><b>${esc(delivery.status || "unknown")}</b></div>
      <div><span>Active theses</span><b>${esc(delivery.active_thesis_count ?? 0)}</b></div>
      <div><span>Delivery records</span><b>${esc(delivery.delivery_record_count ?? records.length)}</b></div>
      <div><span>Generated symbol</span><b>${esc(delivery.symbol || r.symbol || "unknown")}</b></div>
    </div>
    <div class="delivery-records">${records.length ? records.map(renderManagementDeliveryRecord).join("") : `<div class="delivery-empty">${delivery.status === "no_active_thesis" ? "No active thesis records are available for management delivery." : "No management-delivery records were emitted."}</div>`}</div>
  </section>`;
}

function renderManagementDeliveryRecord(record) {
  const source = record.source_assertion || {};
  const match = record.matched_event || null;
  const confidence = record.confidence_link || null;
  const reasons = deliveryArray(record.reasons);
  const limitations = deliveryArray(record.limitations);
  const laterDate = match?.available_at || match?.effective_date || null;
  return `<article class="delivery-record">
    <header><div><span class="pill">${esc(record.status || "unknown")}</span><h4>${esc(record.delivery_id || "delivery record")}</h4></div><b>${esc(record.score_method || "method unknown")}</b></header>
    <div class="delivery-grid">
      ${renderDeliveryList("Linked assertion IDs", [record.thesis_id, record.assertion_key, record.conflict_key], "no assertion link emitted")}
      ${renderDeliveryList("Linked event IDs", source.linked_event_ids, "no source event link emitted")}
      <div><span>Later evidence event</span><b>${esc(match?.event_id || "not observed")}</b></div>
      <div><span>Later evidence date</span><b>${deliveryValue(laterDate, "not observed")}</b></div>
      <div><span>Confidence link</span><b>${confidence ? esc([confidence.confidence_id, confidence.source_cluster_id, confidence.band].filter(Boolean).join(" · ")) : "not linked"}</b></div>
    </div>
    <div class="delivery-record-copy">
      <div><span class="kicker">Status reason</span>${reasons.length ? `<ul>${reasons.map(item => `<li>${esc(item)}</li>`).join("")}</ul>` : `<p>No reason emitted.</p>`}</div>
      <div><span class="kicker">Limitations</span>${limitations.length ? `<ul>${limitations.map(item => `<li>${esc(item)}</li>`).join("")}</ul>` : `<p>No limitations emitted.</p>`}</div>
    </div>
  </article>`;
}

function watchlistArray(value) {
  if (Array.isArray(value)) return value;
  if (value == null || value === "") return [];
  return [value];
}

function watchlistText(value, fallback = "unknown") {
  if (value == null || value === "") return esc(fallback);
  if (Array.isArray(value)) return value.length ? value.map(item => esc(item)).join(" · ") : esc(fallback);
  if (typeof value === "object") return Object.entries(value).length
    ? Object.entries(value).map(([key, item]) => `${esc(key)}: ${esc(item)}`).join(" · ")
    : esc(fallback);
  return esc(value);
}

function renderEvidenceWatchlist(r) {
  const watch = r.evidence_watchlist && typeof r.evidence_watchlist === "object" && !Array.isArray(r.evidence_watchlist)
    ? r.evidence_watchlist
    : null;
  if (!watch) {
    return `<section class="panel span9 evidence-watchlist" aria-labelledby="evidenceWatchlistTitle">
      <button type="button" class="overview-back-button" data-research-route="directory_ownership">Ownership &amp; Peers workspace</button><span class="kicker">Evidence Watchlist</span><h2 id="evidenceWatchlistTitle">What would confirm or break this signal</h2>
      <p class="section-note">Unavailable: the CI slice has not emitted row.evidence_watchlist for this company. The browser will not create checks from other state.</p>
      <div class="watchlist-empty">No evidence-watchlist object was emitted for ${esc(r.symbol)}.</div>
    </section>`;
  }
  const items = Array.isArray(watch.items) ? watch.items : [];
  const counts = watch.status_counts && typeof watch.status_counts === "object" && !Array.isArray(watch.status_counts)
    ? Object.entries(watch.status_counts)
    : [];
  return `<section class="panel span9 evidence-watchlist" aria-labelledby="evidenceWatchlistTitle">
    <button type="button" class="overview-back-button" data-research-route="directory_ownership">Ownership &amp; Peers workspace</button><span class="kicker">Evidence Watchlist</span><h2 id="evidenceWatchlistTitle">What would confirm or break this signal</h2>
    <p class="section-note">Read-only backend checklist. The browser displays emitted statuses, checks, links, readiness, and policy flags only.</p>
    <div class="watchlist-status">
      <div><span>Active watches</span><b>${esc(watch.active_watch_count ?? "unknown")}</b></div>
      <div><span>Current status</span><b>${esc(watch.status || "unknown")}</b></div>
      <div><span>Status reason</span><b>${esc(watch.status_reason || "not emitted")}</b></div>
      <div><span>Financial readiness</span><b>${watchlistText(watch.financial_readiness, "unknown")}</b></div>
    </div>
    <div class="watchlist-counts" aria-label="Evidence watch status counts">${counts.length ? counts.map(([status, count]) => `<span>${esc(status)} <b>${esc(count)}</b></span>`).join("") : `<span>Status counts <b>not emitted</b></span>`}</div>
    ${items.length ? `<div class="watchlist-items">${items.map(renderEvidenceWatchItem).join("")}</div>` : `<div class="watchlist-empty">No active evidence watch is open for ${esc(r.symbol)}. This pilot company is inactive until the backend emits a monitored assertion with confirm and break checks.</div>`}
  </section>`;
}

function renderEvidenceWatchItem(item) {
  return `<article class="watchlist-card">
    <header><div><span class="pill">${esc(item.status || "unknown")}</span><h3>${esc(item.monitored_assertion || "No monitored assertion emitted.")}</h3></div><b>${esc(item.confidence || "unknown confidence")}</b></header>
    <div class="watchlist-status">
      <div><span>Status reason</span><b>${esc(item.status_reason || "not emitted")}</b></div>
      <div><span>Financial readiness</span><b>${watchlistText(item.financial_readiness, "unknown")}</b></div>
      <div><span>Policy flags</span><b>${watchlistText(item.policy_flags, "none emitted")}</b></div>
    </div>
    <div class="watchlist-checks">
      ${renderEvidenceWatchCheck("Confirmation check", item.confirmation_check)}
      ${renderEvidenceWatchCheck("Break check", item.break_check)}
      ${renderEvidenceWatchCheck("Next evidence", item.next_evidence)}
    </div>
    <div class="watchlist-sources">
      ${renderEvidenceWatchLinks("Source evidence", item.source_evidence)}
      ${renderEvidenceWatchLinks("Matched evidence", item.matched_evidence)}
    </div>
  </article>`;
}

function renderEvidenceWatchCheck(label, value) {
  return `<section><h4>${esc(label)}</h4><p>${watchlistText(value, "not emitted")}</p></section>`;
}

function renderEvidenceWatchLinks(label, values) {
  const rows = watchlistArray(values);
  return `<section><h4>${esc(label)}</h4>${rows.length ? rows.map(renderEvidenceWatchLink).join("") : `<p>No official-source link emitted.</p>`}</section>`;
}

function renderEvidenceWatchLink(item) {
  const href = safeHref(typeof item === "string" ? item : item?.source_url || item?.url);
  const page = Number(item?.page) > 0 ? `page ${Number(item.page)}` : "page unknown";
  const label = typeof item === "string" ? "official source" : item?.title || item?.document_id || item?.source || item?.source_id || "official source";
  const reason = typeof item === "string" ? "" : item?.reason || item?.match_reason || item?.status || "";
  const link = href
    ? `<a href="${href}" target="_blank" rel="noopener">${esc(label)} · ${esc(page)}</a>`
    : `<span>${esc(label)} · ${esc(page)}</span>`;
  return `<div>${link}${reason ? `<small>${esc(reason)}</small>` : ""}</div>`;
}

function eventWindowRows(value) {
  return Array.isArray(value) ? value : [];
}

function eventWindowText(item, keys, fallback = "unknown") {
  for (const key of keys) {
    const value = item?.[key];
    if (value !== undefined && value !== null && String(value).trim() !== "") return value;
  }
  return fallback;
}

function renderEventWindowSource(item) {
  const source = item?.source && typeof item.source === "object" && !Array.isArray(item.source) ? item.source : {};
  const href = safeHref(item?.source_url || (typeof item?.source === "string" ? item.source : null) || source.source_url || source.url);
  const label = item?.source_title || source.title || item?.document_id || source.document_id || source.source_id || "retained source";
  const pageValue = item?.page ?? source.page;
  const page = Number(pageValue) > 0 ? `page ${Number(pageValue)}` : "page unknown";
  return href
    ? `<a href="${href}" target="_blank" rel="noopener">${esc(label)} · ${esc(page)}</a>`
    : `<span>${esc(label)} · ${esc(page)}</span>`;
}

function renderEventWindowCard(item, kind) {
  const title = eventWindowText(item, ["title", "event_title", "label", "type", "event_type"], `${kind.label} row`);
  const status = eventWindowText(item, ["status", "state", "evidence_state", "confidence_state"]);
  const date = eventWindowText(item, ["date", "event_date", "filing_date", "retained_event_date", "expected_date"]);
  const window = item?.window && typeof item.window === "object" && !Array.isArray(item.window) ? item.window : item;
  const start = eventWindowText(window, ["window_start", "start", "expected_start", "review_start"]);
  const end = eventWindowText(window, ["window_end", "end", "expected_end", "review_end"]);
  const basis = eventWindowText(item, ["basis", "reason", "status_reason", "source_basis", "method"], "No emitted basis supplied.");
  return `<article class="event-window-row ${esc(kind.className)}">
    <header><div><span class="pill">${esc(kind.label)}</span><h3>${esc(title)}</h3></div><b>${esc(status)}</b></header>
    <div class="event-window-meta">
      <span>Event date <b>${esc(date)}</b></span>
      <span>Window start <b>${esc(start)}</b></span>
      <span>Window end <b>${esc(end)}</b></span>
    </div>
    <p>${esc(basis)}</p>
    <footer>${renderEventWindowSource(item)}</footer>
  </article>`;
}

function renderEventWindowGroup(title, note, rows, kind, emptyText) {
  return `<section class="event-window-group">
    <header><div><span class="kicker">${esc(title)}</span><p>${esc(note)}</p></div><span class="pill">${esc(rows.length)} row${rows.length === 1 ? "" : "s"}</span></header>
    ${rows.length ? `<div class="event-window-list">${rows.map(item => renderEventWindowCard(item, kind)).join("")}</div>` : `<div class="monitoring-empty">${esc(emptyText)}</div>`}
  </section>`;
}

function renderCiEventWindows(r) {
  const eventWindows = r.event_review_windows && typeof r.event_review_windows === "object" && !Array.isArray(r.event_review_windows)
    ? r.event_review_windows
    : null;
  if (!eventWindows) {
    return `<section class="event-window-panel" aria-label="Deterministic event windows">
      <header><div><span class="kicker">Event windows</span><h3>Deterministic operating calendar</h3></div><span class="pill">unknown</span></header>
      <p class="section-note">Unavailable: the CI slice has not emitted row.event_review_windows for this company. The browser will not invent dates, schedule AI tasks, infer a filing, or treat silence as an event.</p>
      <div class="monitoring-empty">No event-window object was emitted for ${esc(r.symbol)}.</div>
    </section>`;
  }
  const confirmed = eventWindowRows(eventWindows.confirmed_events);
  const retainedCalendar = eventWindowRows(eventWindows.known_events);
  const expected = eventWindowRows(eventWindows.expected_reporting_windows);
  const reviews = eventWindowRows(eventWindows.review_windows);
  return `<section class="event-window-panel status-${esc(eventWindows.status || "unknown")}" aria-label="Deterministic event windows">
    <header>
      <div><span class="kicker">Event windows</span><h3>Deterministic operating calendar</h3></div>
      <span class="pill">${esc(eventWindows.status || "unknown")}</span>
    </header>
    <p class="section-note">Read-only backend output from row.event_review_windows. It does not schedule AI tasks or infer a filing; confirmed rows are retained events, expected rows are conservative reporting windows, and review rows show the intended 3-5-day intensified deterministic review window only when emitted.</p>
    <div class="event-window-summary" aria-label="Event window state">
      <div><span>As of</span><b>${esc(eventWindows.as_of || eventWindows.generated_at || "unknown")}</b></div>
      <div><span>State reason</span><b>${esc(eventWindows.status_reason || "not emitted")}</b></div>
      <div><span>Confirmed retained</span><b>${esc(confirmed.length)}</b></div>
      <div><span>Retained calendar</span><b>${esc(retainedCalendar.length)}</b></div>
      <div><span>Expected windows</span><b>${esc(expected.length)}</b></div>
      <div><span>Review windows</span><b>${esc(reviews.length)}</b></div>
    </div>
    ${renderEventWindowGroup(
      "Known retained calendar events",
      "Retained calendar rows, with their emitted confirmation state; no browser-side event discovery.",
      retainedCalendar,
      { label: "Retained calendar event", className: "confirmed" },
      "No retained calendar event row was emitted; state remains explicitly unknown or empty as supplied."
    )}
    ${renderEventWindowGroup(
      "Conservative expected reporting windows",
      "Expected reporting windows are emitted estimates, not filings and not confirmations.",
      expected,
      { label: "Conservative expected reporting window", className: "expected" },
      "No conservative expected reporting window row was emitted."
    )}
    ${renderEventWindowGroup(
      "Intensified deterministic review windows",
      "The intended 3-5-day review window is displayed only from emitted start/end fields.",
      reviews,
      { label: "Intensified deterministic review window", className: "review" },
      "No intensified deterministic review window row was emitted."
    )}
  </section>`;
}

function renderCiMonitoring(r) {
  const monitoring = r.monitoring && typeof r.monitoring === "object" && !Array.isArray(r.monitoring)
    ? r.monitoring
    : null;
  if (!monitoring) {
    return `<section class="panel span9 ci-monitoring" aria-labelledby="ciMonitoringTitle">
      <button type="button" class="overview-back-button" data-research-route="directory_ownership">Ownership &amp; Peers workspace</button><span class="kicker">CI monitoring</span><h2 id="ciMonitoringTitle">Freshness and alert state</h2>
      <p class="section-note">Unavailable: the CI slice has not emitted row.monitoring for this company. The browser will not infer freshness, source health, alert state, forecasts, valuation, or advice.</p>
      <div class="monitoring-empty">No monitoring object was emitted for ${esc(r.symbol)}.</div>
      ${renderCiEventWindows(r)}
    </section>`;
  }
  const sourceHealth = monitoring.source_health && typeof monitoring.source_health === "object" && !Array.isArray(monitoring.source_health)
    ? monitoring.source_health
    : {};
  const activity = monitoring.activity && typeof monitoring.activity === "object" && !Array.isArray(monitoring.activity)
    ? monitoring.activity
    : {};
  const alerts = Array.isArray(monitoring.alerts) ? monitoring.alerts : [];
  return `<section class="panel span9 ci-monitoring status-${esc(monitoring.status || "unknown")}" aria-labelledby="ciMonitoringTitle">
    <button type="button" class="overview-back-button" data-research-route="directory_ownership">Ownership &amp; Peers workspace</button><span class="kicker">CI monitoring</span><h2 id="ciMonitoringTitle">Freshness and alert state</h2>
    <p class="section-note">Read-only backend output from row.monitoring. The browser displays emitted freshness, source health, activity counts and source-linked alerts only; it does not calculate status, reduce alerts, score companies, forecast, value the company, or turn this into advice.</p>
    <div class="monitoring-summary" aria-label="CI monitoring status">
      <div><span>Status</span><b>${esc(monitoring.status || "unknown")}</b></div>
      <div><span>Status reason</span><b>${esc(monitoring.status_reason || "not emitted")}</b></div>
      <div><span>Alert count</span><b>${esc(monitoring.alert_count ?? "unknown")}</b></div>
      <div><span>Registry status</span><b>${esc(sourceHealth.registry_status || "unknown")}</b></div>
    </div>
    <div class="monitoring-times" aria-label="Latest retained monitoring timestamps">
      <div><span>Latest source</span><b>${esc(monitoring.latest_source_at || "unknown")}</b></div>
      <div><span>Latest change</span><b>${esc(monitoring.latest_change_at || "unknown")}</b></div>
      <div><span>Latest event</span><b>${esc(monitoring.latest_event_at || "unknown")}</b></div>
    </div>
    <div class="monitoring-activity" aria-label="Backend monitoring activity">
      <div><span>Change status</span><b>${esc(activity.change_status || "unknown")}</b></div>
      <div><span>Watch status</span><b>${esc(activity.watch_status || "unknown")}</b></div>
      <div><span>Active watches</span><b>${esc(activity.active_watch_count ?? "unknown")}</b></div>
      <div><span>Guidance status</span><b>${esc(activity.guidance_status || "unknown")}</b></div>
      <div><span>Guidance contradictions</span><b>${esc(activity.guidance_contradiction_count ?? "unknown")}</b></div>
      <div><span>Monitored pages</span><b>${esc(sourceHealth.monitored_page_count ?? "unknown")}</b></div>
    </div>
    ${renderCiEventWindows(r)}
    ${alerts.length ? `<div class="monitoring-alerts">${alerts.map(renderCiMonitoringAlert).join("")}</div>` : `<div class="monitoring-empty">No backend alert row is active for ${esc(r.symbol)}.</div>`}
  </section>`;
}

function renderCiMonitoringAlert(alert) {
  const source = alert?.source && typeof alert.source === "object" && !Array.isArray(alert.source) ? alert.source : {};
  const href = safeHref(source.source_url);
  const page = Number(source.page) > 0 ? `page ${Number(source.page)}` : "page unknown";
  const label = source.document_id || source.source_id || source.source || "official source";
  const sourceLink = href
    ? `<a href="${href}" target="_blank" rel="noopener">${esc(label)} · ${esc(page)}</a>`
    : `<span>${esc(label)} · ${esc(page)}</span>`;
  return `<article class="monitoring-alert">
    <header><div><span class="pill">${esc(alert?.type || "unknown")}</span><h3>${esc(alert?.title || alert?.alert_id || "Monitoring alert")}</h3></div><b>${esc(alert?.status || "unknown")}</b></header>
    <div class="monitoring-alert-meta">
      <span>Date <b>${esc(alert?.date || "unknown")}</b></span>
      <span>Alert ID <b>${esc(alert?.alert_id || "unknown")}</b></span>
    </div>
    <p>${esc(alert?.reason || "No backend reason emitted.")}</p>
    <footer>${sourceLink}</footer>
  </article>`;
}

function renderThesisCard(thesis) {
  const evidence = Array.isArray(thesis.evidence) ? thesis.evidence : [];
  return `<article class="thesis-card">
    <header>
      <div><span class="pill">${esc(thesis.status || "unknown")}</span><h3>${esc(thesis.thesis_type || "official thesis")}</h3></div>
      <b>${esc(thesis.confidence_band || "unknown confidence")}</b>
    </header>
    <div class="thesis-facts">
      <span>Source cluster <b>${esc(thesis.source_cluster_id || "unknown")}</b></span>
      <span>Inference label <b>${esc(thesis.assessment || thesis.intelligence_type || "unknown")}</b></span>
      <span>Confidence band <b>${esc(thesis.confidence_band || "unknown")}</b></span>
    </div>
    <p class="thesis-assertion">${esc(thesis.monitored_assertion || thesis.assertion_key || "No monitored assertion supplied.")}</p>
    <div class="thesis-checks">
      ${renderThesisChecks("Prove checks", thesis.prove_checks)}
      ${renderThesisChecks("Kill checks", thesis.kill_checks)}
      ${renderThesisWatch(thesis.watch_items)}
    </div>
    <div class="thesis-evidence">
      <span class="kicker">Evidence links</span>
      ${evidence.length ? evidence.slice(0, 6).map(renderThesisEvidence).join("") : `<p>No bounded evidence link is attached.</p>`}
    </div>
  </article>`;
}

function renderThesisChecks(label, checks) {
  const rows = Array.isArray(checks) ? checks : [];
  return `<section><h4>${esc(label)}</h4>${rows.length ? rows.map(item => `<div><b>${esc(item.current_status || "not_observed")}</b><span>${esc(item.condition || "No condition supplied.")}</span><em>${esc(item.source_required || "official source required")}</em></div>`).join("") : `<p>No ${esc(label.toLowerCase())} are defined.</p>`}</section>`;
}

function renderThesisWatch(items) {
  const rows = Array.isArray(items) ? items : [];
  return `<section><h4>Watch items</h4>${rows.length ? rows.map(item => `<div><b>${esc(item.watch_type || "watch")}</b><span>${esc(item.description || "No watch description supplied.")}</span><em>${esc(item.source_required || "source required")}</em></div>`).join("") : `<p>No watch items are defined.</p>`}</section>`;
}

function renderThesisEvidence(item) {
  const href = safeHref(item?.source_url);
  const page = Number(item?.page) > 0 ? `page ${Number(item.page)}` : "page unknown";
  const label = `${item?.document_id || "document unknown"} · ${page}`;
  return href
    ? `<a href="${href}" target="_blank" rel="noopener">${esc(label)}</a>`
    : `<span>${esc(label)}</span>`;
}

function blankScenarioState() {
  return { revenueGrowth: "", netMargin: "", exitPe: "", result: null, error: null };
}

function scenarioState(symbol) {
  return state.scenario.bySymbol[symbol] || (state.scenario.bySymbol[symbol] = blankScenarioState());
}

function captureScenarioInputs(symbol) {
  const current = scenarioState(symbol);
  current.revenueGrowth = $("scenarioGrowth")?.value ?? current.revenueGrowth;
  current.netMargin = $("scenarioMargin")?.value ?? current.netMargin;
  current.exitPe = $("scenarioPe")?.value ?? current.exitPe;
}

function scenarioNumber(name, value, low, high) {
  if (String(value).trim() === "") throw new Error(`${name} is required.`);
  const number = Number(value);
  if (!Number.isFinite(number) || number < low || number > high) {
    throw new Error(`${name} must be between ${low} and ${high}.`);
  }
  return number;
}

function calculateScenario(r) {
  const current = scenarioState(r.symbol);
  if (!scenarioLabIsActive(r.scenario_lab, r.financial_truth_qualification)) {
    current.result = null;
    current.error = "Scenario Lab remains unavailable until financial-truth qualification is complete.";
    return;
  }
  const baseline = r.scenario_lab?.baseline || {};
  try {
    const revenue = scenarioNumber("Snapshot revenue", baseline.revenue, Number.MIN_VALUE, Number.MAX_VALUE);
    const shares = scenarioNumber("Shares outstanding", baseline.shares_out, Number.MIN_VALUE, Number.MAX_VALUE);
    const price = scenarioNumber("Latest price", baseline.latest_price, Number.MIN_VALUE, Number.MAX_VALUE);
    const growth = scenarioNumber("Revenue growth", current.revenueGrowth, -99.999999, 1000);
    const margin = scenarioNumber("Net margin", current.netMargin, 0.000001, 100);
    const pe = scenarioNumber("Exit P/E", current.exitPe, 0.000001, 200);
    // Deliberate browser mirror of scripts/company_scenario_lab.py. The Python
    // checker owns the formulas; check_company_scenario_lab_ui.mjs locks this
    // interactive copy to the same operands, bounds and golden case.
    const scenarioRevenue = revenue * (1 + growth / 100);
    const scenarioNetIncome = scenarioRevenue * margin / 100;
    const scenarioEps = scenarioNetIncome / shares;
    const multipleImpliedPrice = scenarioEps * pe;
    const requiredEps = price / pe;
    const requiredNetIncome = requiredEps * shares;
    const requiredRevenue = requiredNetIncome / (margin / 100);
    const requiredRevenueGrowthPct = (requiredRevenue / revenue - 1) * 100;
    current.result = {
      scenarioRevenue,
      scenarioNetIncome,
      scenarioEps,
      multipleImpliedPrice,
      priceDelta: multipleImpliedPrice - price,
      priceDeltaPct: (multipleImpliedPrice / price - 1) * 100,
      requiredEps,
      requiredNetIncome,
      requiredRevenue,
      requiredRevenueGrowthPct,
      expectationsGapPct: requiredRevenueGrowthPct - growth,
    };
    current.error = null;
  } catch (error) {
    current.result = null;
    current.error = error.message || "Enter valid assumptions.";
  }
}

function scenarioLabIsActive(lab, financialTruth) {
  return financialTruth?.status === "qualified"
    && lab?.financial_truth_status === "qualified"
    && lab?.status?.scenario_lab === "ready_snapshot_sensitivity";
}

function scenarioMetric(label, value, suffix = "") {
  return `<div><span>${esc(label)}</span><b>${esc(value == null ? "unknown" : `${fmt(value, 2)}${suffix}`)}</b></div>`;
}

function renderScenarioLab(r) {
  const lab = r.scenario_lab || {};
  const baseline = lab.baseline || {};
  const provenance = lab.provenance || {};
  const current = scenarioState(r.symbol);
  const result = current.result;
  const active = scenarioLabIsActive(lab, r.financial_truth_qualification);
  const fundamentalsHref = safeHref(provenance.fundamentals_source_url);
  const priceHref = safeHref(provenance.price_source_url);
  const source = (href, label) => href ? `<a href="${href}" target="_blank" rel="noopener">${esc(label)}</a>` : esc(`${label} unavailable`);
  return `<section class="panel span9 scenario-shell" aria-labelledby="scenarioTitle">
    <button type="button" class="overview-back-button" data-research-route="directory_strategy">Strategy workspace</button><span class="kicker">Scenario sensitivity</span><h2 id="scenarioTitle">Change assumptions, inspect the arithmetic</h2>
    <p class="section-note">A transparent snapshot sensitivity and reverse solve. It is not a prediction or a house case; Henneth supplies no default assumptions.</p>
    <div class="scenario-baseline">
      ${scenarioMetric("Snapshot revenue", baseline.revenue)}
      ${scenarioMetric("Snapshot net income", baseline.net_income)}
      ${scenarioMetric("Shares outstanding", baseline.shares_out)}
      ${scenarioMetric("Snapshot EPS", baseline.eps)}
      ${scenarioMetric("Latest price", baseline.latest_price)}
    </div>
    <p class="scenario-source">Fundamentals ${source(fundamentalsHref, provenance.fundamentals_as_of || "date unknown")} · Price ${source(priceHref, provenance.price_as_of || "date unknown")}</p>
    ${active ? `<form id="scenarioForm" class="scenario-form" aria-describedby="scenarioHelp scenarioError">
      <label><span>Revenue growth %</span><input id="scenarioGrowth" type="number" min="-99.999999" max="1000" step="0.1" value="${esc(current.revenueGrowth)}" placeholder="Enter assumption"></label>
      <label><span>Net margin %</span><input id="scenarioMargin" type="number" min="0.000001" max="100" step="0.1" value="${esc(current.netMargin)}" placeholder="Enter assumption"></label>
      <label><span>Exit P/E</span><input id="scenarioPe" type="number" min="0.000001" max="200" step="0.1" value="${esc(current.exitPe)}" placeholder="Enter assumption"></label>
      <div class="scenario-actions"><button type="submit">Calculate</button><button id="scenarioClear" type="button" class="secondary">Clear</button></div>
      <p id="scenarioHelp" class="muted">All three assumptions are required. Values are kept only in this browser session for ${esc(r.symbol)}.</p>
      <p id="scenarioError" class="scenario-error" role="alert" aria-live="polite">${esc(current.error || "")}</p>
    </form>
    ${result ? `<div class="scenario-results">
      <section><h3>Scenario outputs</h3><div class="scenario-metrics">
        ${scenarioMetric("Revenue", result.scenarioRevenue)}${scenarioMetric("Net income", result.scenarioNetIncome)}${scenarioMetric("EPS", result.scenarioEps)}${scenarioMetric("Multiple-implied price", result.multipleImpliedPrice)}${scenarioMetric("Price difference", result.priceDelta)}${scenarioMetric("Price difference", result.priceDeltaPct, "%")}
      </div></section>
      <section><h3>Reverse expectations at the current price</h3><div class="scenario-metrics">
        ${scenarioMetric("Required EPS", result.requiredEps)}${scenarioMetric("Required net income", result.requiredNetIncome)}${scenarioMetric("Required revenue", result.requiredRevenue)}${scenarioMetric("Required revenue growth", result.requiredRevenueGrowthPct, "%")}
      </div></section>
      <section><h3>Market-implied gap</h3><div class="scenario-metrics">
        ${scenarioMetric("Caller revenue growth", current.revenueGrowth, "%")}${scenarioMetric("Required revenue growth", result.requiredRevenueGrowthPct, "%")}${scenarioMetric("Gap", result.expectationsGapPct, "%")}
      </div></section>
    </div>` : `<div class="empty">Enter all three assumptions to calculate a sensitivity and reverse expectations.</div>`}` : `<div class="empty">Scenario Lab is blocked by financial-truth qualification. Snapshot inputs remain visible for provenance, but no forecast, valuation, market-expectations, or reverse-solve output can be calculated.</div>`}
    <div class="scenario-blocked" aria-label="Unavailable model outputs">
      ${["forecast", "valuation", "market expectations", "scenario lab", "EBITDA", "FCF", "DCF"].map(key => `<span>${esc(key)}<b>${esc(["forecast", "valuation", "market expectations", "scenario lab"].includes(key) ? (lab.status?.[key.replaceAll(" ", "_")] || "blocked") : "blocked_insufficient_qualified_history")}</b></span>`).join("")}
    </div>
  </section>`;
}

const ASK_SECTION_LABELS = {
  conclusion: "Conclusion",
  evidence: "Evidence",
  mechanism: "Mechanism",
  historical_benchmark: "Historical benchmark",
  financial_impact: "Financial impact",
  scenarios: "Scenarios",
  valuation_readiness: "Valuation readiness",
  confidence: "Confidence",
  what_to_watch: "What to watch",
};

function renderAskHenneth(r) {
  const record = state.ask.bySymbol[r.symbol] || {};
  const busy = Boolean(state.ask.pending[r.symbol]);
  const value = record.question || "";
  return `<section class="panel span9 ask-shell" aria-labelledby="askTitle">
    <button type="button" class="overview-back-button" data-research-route="directory_intelligence">Intelligence workspace</button><span class="kicker">Ask Henneth</span><h2 id="askTitle">Question this company file</h2>
    <p class="section-note">Answers are built from the private company-intelligence contract. The model can only add validated qualitative text; facts, readiness, sections and citations are server-owned.</p>
    <form id="askForm" class="ask-form">
      <label for="askInput">Question for ${esc(r.symbol)}</label>
      <div>
        <input id="askInput" type="text" maxlength="4096" aria-describedby="askHelp" autocomplete="off" value="${esc(value)}" placeholder="What changed in the latest filing?">
        <button type="submit" ${busy ? "disabled" : ""}>${busy ? "Reading" : "Ask"}</button>
      </div>
      <p id="askHelp" class="muted" role="status" aria-live="polite">${busy ? "Reading retained evidence and validating the answer." : "Use company-specific, qualitative questions. Unsafe requests are rejected before any answer is shown."}</p>
    </form>
    ${record.error ? `<div class="ask-error" role="alert">${esc(readableAskError(record.error))}</div>` : ""}
    ${record.answer ? renderAskAnswer(record.answer, record.citations || []) : `<div class="empty">No Ask answer has been requested for ${esc(r.symbol)} yet.</div>`}
  </section>`;
}

function readableAskError(error) {
  const map = {
    question_contains_numeric_token: "Ask rejected the question because it contained a numeric token.",
    question_contains_unsafe_language: "Ask rejected the question because it looked like advice, prediction, prompt disclosure, or unsupported market language.",
    provider_not_configured: "Ask is not configured on this deployment yet.",
    provider_busy: "The model provider is busy. Try again shortly.",
    model_output_rejected: "The answer was rejected by the contract validator.",
    missing_citation_tie: "The answer was rejected because it was not tied to retained evidence.",
  };
  return map[error] || "Ask could not return a validated answer. Try again shortly.";
}

function renderAskAnswer(answer, citations) {
  const citationById = Object.fromEntries((citations || []).map(citation => [citation.citation_id, citation]));
  const sections = answer.sections || {};
  const order = Object.keys(ASK_SECTION_LABELS);
  return `<div class="ask-answer" aria-label="Ask Henneth answer for ${esc(answer.symbol || "company")}">
    ${order.map(key => renderAskSection(key, sections[key], citationById)).join("")}
  </div>`;
}

function renderAskSection(key, section, citationById) {
  if (!section) return `<article class="ask-section"><header><h3>${esc(ASK_SECTION_LABELS[key])}</h3><span class="pill">missing</span></header><p>Unknown.</p></article>`;
  const status = section.status || "unknown";
  let body = "";
  if (key === "evidence") {
    const items = section.items || [];
    body = items.length ? `<div class="ask-cites">${items.map(item => renderAskCitation(item.citation_id, citationById[item.citation_id])).join("")}</div>` : `<p>No retained citation is attached.</p>`;
  } else if (key === "historical_benchmark") {
    const studies = section.studies || [];
    body = studies.length ? `<div class="ask-mini-list">${studies.map(study => `<div><b>${esc(study.event_id || "event")}</b><span>${esc(study.methodology || section.methodology || "descriptive, not causal")}</span></div>`).join("")}</div>` : `<p>No historical benchmark study is available.</p>`;
  } else if (key === "scenarios") {
    const scenarios = section.scenarios || [];
    body = scenarios.length ? `<div class="ask-mini-list">${scenarios.map(scenario => `<div><b>${esc(scenario.case_name || scenario.scenario_type || "Scenario")}</b><span>${esc(scenario.impact_status || "unknown impact status")}</span></div>`).join("")}</div>` : `<p>No sourced scenario set is available.</p>`;
  } else if (key === "valuation_readiness") {
    const downstream = section.downstream_status || {};
    body = `<div class="ask-readiness">${["forecast", "valuation", "market_expectations", "scenario_lab"].map(item => `<span>${esc(item.replaceAll("_", " "))}<b>${esc(downstream[item] || "blocked_not_implemented")}</b></span>`).join("")}</div>`;
  } else if (key === "confidence") {
    const assessments = section.assessments || [];
    body = `<p>${esc(section.aggregate_band || section.band || "unknown")}${section.aggregate_score == null ? "" : ` · ${scoreLabel(section.aggregate_score)}`}</p>${assessments.length ? `<div class="ask-mini-list">${assessments.map(assessment => `<div><b>${esc(assessment.source_cluster_id || assessment.confidence_id || "assessment")} · ${scoreLabel(assessment.score)} · ${esc(assessment.band || "unknown")}</b><span>${(assessment.components || []).map(component => `${esc(component.name)} ${scoreLabel(component.normalized_score)} / ${component.weighted_points == null ? "points unknown" : `${esc(fmt(component.weighted_points, 2))} pts`}`).join(" · ")}</span></div>`).join("")}</div>` : `<p>No intelligence-confidence assessment is available.</p>`}`;
  } else {
    body = `<p>${esc(section.text || "Unknown.")}</p>${renderAskCitationLinks(section.citation_ids, citationById)}`;
  }
  return `<article class="ask-section"><header><h3>${esc(ASK_SECTION_LABELS[key])}</h3><span class="pill">${esc(status)}</span></header>${body}</article>`;
}

function renderAskCitationLinks(ids, citationById) {
  const rows = (ids || []).map(id => renderAskCitation(id, citationById[id])).join("");
  return rows ? `<div class="ask-cites compact">${rows}</div>` : "";
}

function renderAskCitation(id, citation) {
  if (!citation) return `<span>${esc(id || "citation unavailable")}</span>`;
  const href = safeHref(citation.source_url);
  const label = citation.label || citation.document_id || citation.citation_id;
  const page = citation.page ? `page ${citation.page}` : "page unknown";
  return href
    ? `<a href="${href}" target="_blank" rel="noopener">${esc(label)} · ${esc(page)}</a>`
    : `<span>${esc(label)} · ${esc(page)}</span>`;
}

function coveragePeriodLabel(slot) {
  if (!slot) return "not emitted";
  return slot.period_end
    ? `${slot.period_end} · explicit ${slot.period_type || "period"} date`
    : `unresolved · ${slot.evidence_status || slot.source || "missing explicit annual period evidence"}`;
}

function coverageDocLink(doc) {
  const href = safeHref(doc?.source_url);
  const label = doc?.document_id || "document unknown";
  return href
    ? `<a href="${href}" target="_blank" rel="noopener">${esc(label)}</a>`
    : esc(label);
}

function readinessDocLink(doc) {
  const href = safeHref(doc?.source_url || doc?.url);
  const label = doc?.document_id || doc?.doc_id || doc?.ref_id || "document unknown";
  return href
    ? `<a href="${href}" target="_blank" rel="noopener">${esc(label)}</a>`
    : esc(label);
}

function readinessList(items, empty = "None emitted") {
  return Array.isArray(items) && items.length
    ? `<ul>${items.map(item => `<li>${esc(item)}</li>`).join("")}</ul>`
    : `<p class="muted">${esc(empty)}</p>`;
}

const ASSUMPTION_GAP_PRODUCTS = [
  ["forecast", "Forecast"],
  ["valuation", "Valuation"],
  ["market_expectations", "Market expectations"],
];

function assumptionMetricLabel(value) {
  const labels = {
    revenue_growth_pct: "Revenue growth",
    net_margin_pct: "Net margin",
    shares_out: "Shares outstanding",
    current_price: "Current price",
    exit_pe: "Exit P/E",
    net_debt: "Net debt",
  };
  return labels[value] || humanEngineKey(value);
}

function assumptionRecordLink(record) {
  const label = record?.source_label || record?.source_id || record?.metric || "source";
  const href = safeHref(record?.source_url);
  return href
    ? `<a href="${href}" target="_blank" rel="noopener">${esc(label)}</a>`
    : `<span>${esc(label)}</span>`;
}

function renderAssumptionGapProduct(key, product) {
  const required = Array.isArray(product?.required_approved_records) ? product.required_approved_records : [];
  const missing = Array.isArray(product?.missing_approved_records) ? product.missing_approved_records : [];
  const accepted = Array.isArray(product?.accepted_records) ? product.accepted_records : [];
  const prerequisites = Array.isArray(product?.missing_prerequisites) ? product.missing_prerequisites : [];
  return `<section class="forecast-readiness-section">
    <h3>${esc(ASSUMPTION_GAP_PRODUCTS.find(([item]) => item === key)?.[1] || humanEngineKey(key))}</h3>
    <div class="blocked-grid">
      <span>Status <b>${esc(product?.status || "not_evaluated")}</b></span>
      <span>Required records <b>${esc(required.length)}</b></span>
      <span>Accepted records <b>${esc(accepted.length)}</b></span>
      <span>Missing approvals <b>${esc(missing.length)}</b></span>
    </div>
    <div class="baseline-table"><table><thead><tr><th>Required record</th><th>Review state</th><th>Source / blocker</th></tr></thead><tbody>
      ${required.length ? required.map(metric => {
        const record = accepted.find(item => item.metric === metric);
        const isMissing = missing.includes(metric);
        const blocker = isMissing ? "owner approval required" : prerequisites.join(", ") || "accepted deterministic operand";
        const source = record ? assumptionRecordLink(record) : esc(blocker);
        return `<tr><td>${esc(assumptionMetricLabel(metric))}</td><td>${esc(record ? "accepted" : isMissing ? "missing approved record" : "pending prerequisite")}</td><td>${source}</td></tr>`;
      }).join("") : `<tr><td colspan="3">No required records were emitted for this product.</td></tr>`}
    </tbody></table></div>
  </section>`;
}

function renderFinancialEngineAssumptionReview(r) {
  const gaps = r.financial_engine_assumption_gaps && typeof r.financial_engine_assumption_gaps === "object" && !Array.isArray(r.financial_engine_assumption_gaps)
    ? r.financial_engine_assumption_gaps
    : null;
  if (!gaps) {
    return `<section class="forecast-readiness-section"><h3>Owner assumption review</h3><div class="empty">financial_engine_assumptions.assumption_gaps is not available in the CI slice.</div></section>`;
  }
  const products = gaps.products || {};
  const refs = Array.isArray(gaps.historical_reference_cases) ? gaps.historical_reference_cases : [];
  const policy = gaps.policy || {};
  return `<section class="forecast-readiness-section" aria-labelledby="assumptionGapReviewTitle">
    <h3 id="assumptionGapReviewTitle">Owner assumption review</h3>
    <p class="section-note">Read-only projection of financial_engine_assumptions.assumption_gaps. It shows which owner-approved, source-labelled records are still needed before formal forecasts, valuations, or market expectations can activate; it does not approve assumptions, compute formal outputs, or turn reference cases into forecast inputs.</p>
    <div class="forecast-readiness-summary">
      <div><span>Status</span><b>${esc(gaps.status || "unknown")}</b></div>
      <div><span>Financial inputs</span><b>${esc(gaps.financial_model_inputs_status || "unknown")}</b></div>
      <div><span>Readiness</span><b>${esc(gaps.forecast_readiness_status || "unknown")}</b></div>
      <div><span>Qualified periods</span><b>${esc(gaps.qualified_period_count ?? "unknown")}</b></div>
      <div><span>Next action</span><b>${esc(gaps.next_required_action || "not emitted")}</b></div>
      <div><span>Reference cases satisfy gaps</span><b>${gaps.reference_cases_can_satisfy_missing_records ? "yes" : "no"}</b></div>
    </div>
    ${ASSUMPTION_GAP_PRODUCTS.map(([key]) => renderAssumptionGapProduct(key, products[key])).join("")}
    <section class="forecast-readiness-section">
      <h3>Historical reference cases</h3>
      <p class="section-note">Reference cases are reported-history baselines only. They remain separate from owner-approved forward and valuation records.</p>
      <div class="forecast-readiness-docs">${refs.length ? refs.map(ref => `<article><b>${esc(assumptionMetricLabel(ref.metric || "reference_case"))}</b><span>${esc(ref.assumption_status || ref.case_type || "historical_reference_case")}</span><small>${esc(ref.available_on || "available_on unknown")} · ${esc(ref.formula_version || "formula not emitted")}</small></article>`).join("") : `<div class="empty">No historical reference-case refs were emitted for this company.</div>`}</div>
    </section>
    <section class="forecast-readiness-section">
      <h3>Manifest policy</h3>
      <div class="forecast-readiness-policy">
        <span>Gap manifest only <b>${policy.gap_manifest_only ? "true" : "not emitted"}</b></span>
        <span>Does not approve assumptions <b>${policy.does_not_approve_assumptions ? "true" : "not emitted"}</b></span>
        <span>Does not compute outputs <b>${policy.does_not_compute_formal_outputs ? "true" : "not emitted"}</b></span>
        <span>Reference cases are not approved records <b>${policy.derived_reference_cases_are_not_approved_records ? "true" : "not emitted"}</b></span>
      </div>
    </section>
  </section>`;
}

function renderEventToValueProductReadiness() {
  const audit = state.data?.meta?.event_to_value_product_readiness;
  if (!audit || typeof audit !== "object" || Array.isArray(audit) || !Array.isArray(audit.metrics)) {
    return '<section class="panel span9 alpha-readiness-shell"><button type="button" class="overview-back-button" data-research-route="directory_financials">Financials workspace</button><span class="kicker">Event-to-Value Alpha</span><h2>Product readiness not generated</h2><p class="section-note">Retained-state audit unavailable; no progress is inferred.</p></section>';
  }
  const summary = audit.summary || {};
  const cards = audit.metrics.map(metric => `<article class="alpha-readiness-card" data-status="${esc(metric.status || "unknown")}"><header><span class="pill">${esc(metric.status || "unknown")}</span><h3>${esc(metric.label || metric.id || "metric")}</h3></header><b>${esc(metric.display || (metric.value == null ? "unknown" : metric.value))}</b><p>${esc(metric.definition || "Retained-state metric")}</p><div class="blocked-grid"><span>Source <b>${esc(metric.source_path || "unknown")}</b></span><span>Reason <b>${esc(metric.reason || "none")}</b></span></div></article>`).join("");
  return `<section class="panel span9 alpha-readiness-shell"><button type="button" class="overview-back-button" data-research-route="directory_financials">Financials workspace</button><span class="kicker">Event-to-Value Alpha</span><h2>Product readiness from retained artifacts</h2><p class="section-note">Research-only gate. Implemented engines remain distinct from proven live outputs; blocked evidence is shown explicitly.</p><div class="blocked-grid"><span>Status <b>${esc(audit.status || "unknown")}</b></span><span>Available <b>${esc(summary.available_metric_count ?? "unknown")}</b></span><span>Blocked <b>${esc(summary.blocked_metric_count ?? "unknown")}</b></span><span>As of <b>${esc(audit.as_of || "unknown")}</b></span></div><div class="alpha-readiness-grid">${cards}</div></section>`;
}

function renderForecastReadiness(r) {
  const readiness = r.forecast_readiness && typeof r.forecast_readiness === "object" && !Array.isArray(r.forecast_readiness)
    ? r.forecast_readiness
    : null;
  if (!readiness) {
    return `<section class="panel span9 forecast-readiness-shell" aria-labelledby="forecastReadinessTitle">
      <button type="button" class="overview-back-button" data-research-route="directory_financials">Financials workspace</button><span class="kicker">Forecast / valuation readiness</span><h2 id="forecastReadinessTitle">Backend state not generated</h2>
      <p class="section-note">Read-only readiness state is expected at row.forecast_readiness. The browser does not infer qualification, calculate projections, value the company, estimate odds, emit targets, or turn this into advice.</p>
      <div class="empty">Forecast readiness is unavailable: not generated.</div>
    </section>`;
  }
  const downstream = readiness.downstream_status || {};
  const registry = readiness.model_registry && typeof readiness.model_registry === "object" ? readiness.model_registry : {};
  const adapter = readiness.model_adapter && typeof readiness.model_adapter === "object" ? readiness.model_adapter : {};
  const candidates = readiness.qualification_candidate_document_refs || readiness.qualification_candidate_documents || [];
  const policy = readiness.policy || {};
  const limitations = readiness.limitations || [];
  return `<section class="panel span9 forecast-readiness-shell" aria-labelledby="forecastReadinessTitle">
    <button type="button" class="overview-back-button" data-research-route="directory_financials">Financials workspace</button><span class="kicker">Forecast / valuation readiness</span><h2 id="forecastReadinessTitle">Model gate and blocked outputs</h2>
    <p class="section-note">Read-only backend output from row.forecast_readiness. The browser displays exact status, version, missing requirements, official candidate refs, policy and blocked downstream states only.</p>
    <div class="forecast-readiness-summary">
      <div><span>Status</span><b>${esc(readiness.status || "unknown")}</b></div>
      <div><span>Driver registry</span><b>${esc(registry.status || "unknown")} · ${esc(registry.selected_sector || "unknown")}</b></div>
      <div><span>Registry version</span><b>${esc(readiness.registry_version || registry.registry_version || "unknown")}</b></div>
      <div><span>Numerical adapter</span><b>${esc(readiness.adapter_version || adapter.adapter_version || adapter.status || "unknown")}</b></div>
      <div><span>Qualified periods</span><b>${esc(readiness.qualified_period_count ?? "unknown")}</b></div>
    </div>
    <div class="forecast-readiness-downstream" aria-label="Blocked downstream model states">
      ${["forecast", "valuation", "market_expectations", "numeric_impact"].map(key => `<span>${esc(key.replaceAll("_", " "))}<b>${esc(downstream[key] || "blocked_model_adapter_unavailable")}</b></span>`).join("")}
    </div>
    <section class="forecast-readiness-section">
      <h3>Missing requirements</h3>
      ${readinessList(readiness.missing_requirements, "No missing requirements emitted.")}
    </section>
    ${renderFinancialEngineAssumptionReview(r)}
    <section class="forecast-readiness-section">
      <h3>Qualification candidate document refs</h3>
      <div class="forecast-readiness-docs">${Array.isArray(candidates) && candidates.length ? candidates.map(doc => `<article><b>${readinessDocLink(doc)}</b><span>${esc(doc.title || doc.document_title || "untitled official document")}</span><small>${esc(doc.published_at || doc.date || "date unknown")} · ${esc(doc.reason || doc.candidate_reason || doc.status || "candidate")}</small></article>`).join("") : `<div class="empty">No qualification candidate document refs were emitted.</div>`}</div>
    </section>
    <section class="forecast-readiness-section">
      <h3>Policy</h3>
      <div class="forecast-readiness-policy">
        <span>Forecasts <b>${esc(policy.forecasts || policy.forecast || "blocked_until_qualified")}</b></span>
        <span>Valuation <b>${esc(policy.valuation || "blocked_until_qualified")}</b></span>
        <span>Market expectations <b>${esc(policy.market_expectations || "blocked_until_qualified")}</b></span>
        <span>Numeric impact <b>${esc(policy.numeric_impact || "blocked_until_sourced_operands")}</b></span>
      </div>
    </section>
    ${(limitations || []).length ? `<section class="forecast-readiness-section"><h3>Limitations</h3>${readinessList(limitations)}</section>` : ""}
  </section>`;
}

function renderFinancialCoverage(r) {
  const coverage = r.financial_coverage && typeof r.financial_coverage === "object" && !Array.isArray(r.financial_coverage)
    ? r.financial_coverage
    : null;
  if (!coverage) {
    return `<section class="baseline-section financial-coverage-panel"><h3>Financial coverage & qualification</h3><div class="empty">Financial coverage is unavailable: not generated.</div></section>`;
  }
  const annualSlots = Array.from({ length: 3 }, (_, index) => (coverage.required_annual_periods || [])[index] || { slot: `annual_period_${index + 1}`, period_end: null, evidence_status: "not_emitted" });
  const missingRows = coverage.missing_revenue_pat_eps_by_annual_period || [];
  const audit = coverage.audit_only_series || {};
  const queue = coverage.qualification_queue || {};
  const model = coverage.model_readiness || {};
  const downstream = model.downstream_status || {};
  const candidateDocs = queue.candidate_documents || [];
  return `<section class="baseline-section financial-coverage-panel" aria-labelledby="financialCoverageTitle">
    <h3 id="financialCoverageTitle">Financial coverage & qualification</h3>
    <p class="section-note">Read-only coverage metadata. The browser does not infer periods, promote values, parse PDFs, or trigger restage.</p>
    <div class="financial-coverage-summary">
      <div><span>Status</span><b>${esc(coverage.status || "unknown")}</b></div>
      <div><span>Official docs indexed</span><b>${esc(coverage.indexed_official_financial_doc_count ?? 0)}</b></div>
      <div><span>Queue status</span><b>${esc(queue.status || "unknown")}</b></div>
      <div><span>Forecast</span><b>${esc(downstream.forecast || "blocked_not_implemented")}</b></div>
      <div><span>Valuation</span><b>${esc(downstream.valuation || "blocked_not_implemented")}</b></div>
    </div>
    <div class="financial-coverage-slots">${annualSlots.map(slot => `<article><span>${esc(slot.slot || "annual slot")}</span><b>${esc(coveragePeriodLabel(slot))}</b><small>${esc(slot.document_id || "no official annual document resolved")}</small></article>`).join("")}</div>
    <div class="financial-coverage-missing">${missingRows.length ? missingRows.map(row => `<article><span>${esc(row.slot || "annual slot")}</span><b>${esc((row.missing_metrics || []).join(", ") || "none emitted")}</b><small>${esc(row.period_evidence_status || row.status || "unknown")}</small></article>`).join("") : `<div class="empty">No missing revenue/PAT/EPS rows were emitted.</div>`}</div>
    <div class="financial-coverage-audit">
      <div><span>Audit-only facts</span><b>${esc(audit.audit_only_fact_count ?? 0)}</b><small>Quarantined / not promoted</small></div>
      <div><span>Model-loadable facts</span><b>${esc(audit.model_loadable_count ?? 0)}</b><small>${esc(audit.note || "Audit-only facts are retained as coverage signals only.")}</small></div>
    </div>
    <div class="financial-coverage-docs">
      <span class="kicker">Candidate official documents</span>
      ${candidateDocs.length ? candidateDocs.map(doc => `<article><b>${coverageDocLink(doc)}</b><span>${esc(doc.title || "untitled official document")}</span><small>${esc(doc.published_at || "date unknown")} · ${esc(doc.reason || "candidate")}</small></article>`).join("") : `<div class="empty">No candidate documents were emitted for the qualification queue.</div>`}
    </div>
    ${(coverage.limitations || []).length ? `<div class="financial-coverage-limits"><span class="kicker">Limitations</span><ul>${coverage.limitations.map(item => `<li>${esc(item)}</li>`).join("")}</ul></div>` : ""}
  </section>`;
}

function renderFinancialTruthQualification(r) {
  const truth = r.financial_truth_qualification && typeof r.financial_truth_qualification === "object" && !Array.isArray(r.financial_truth_qualification)
    ? r.financial_truth_qualification
    : null;
  if (!truth) return `<section class="baseline-section financial-coverage-panel"><h3>Financial-truth qualification</h3><div class="empty">Financial-truth qualification is unavailable: not generated.</div></section>`;
  const annual = truth.annual_income_triplets || {};
  const quarters = truth.qualified_reported_quarter_fact_sets || {};
  const documentedInterim = truth.documented_interim_metadata || {};
  const cashflow = truth.annual_operating_cash_flow || {};
  const fullStatement = truth.model_ready_financial_statement_coverage || {};
  const annualStatements = fullStatement.annual || {};
  const quarterStatements = fullStatement.reported_quarter || {};
  const shares = truth.share_count || {};
  const tieOut = truth.financial_tie_out || {};
  const documents = Array.isArray(truth.candidate_documents) ? truth.candidate_documents : [];
  return `<section class="baseline-section financial-coverage-panel" aria-labelledby="financialTruthQualificationTitle">
    <h3 id="financialTruthQualificationTitle">Financial-truth qualification</h3>
    <p class="section-note">Read-only backend qualification state. The browser does not qualify facts, infer coverage, promote audit-only evidence, parse documents, restage sources, calculate forecasts, or value the company.</p>
    <div class="financial-coverage-summary">
      <div><span>Status</span><b>${esc(truth.status || "unknown")}</b></div>
      <div><span>Candidate rank</span><b>${esc(truth.candidate_rank ?? "unknown")}</b></div>
      <div><span>Selection</span><b>${esc(truth.selection_status || "not selected")}</b></div>
      <div><span>Tie-out</span><b>${esc(tieOut.status || "unknown")}</b></div>
      <div><span>Forecast</span><b>${esc(truth.downstream?.forecast || "blocked")}</b></div>
    </div>
    <div class="financial-coverage-slots">
      <article><span>Annual income triplets</span><b>${esc(annual.present ?? 0)} / ${esc(annual.required ?? 5)}</b><small>${esc((annual.qualified_periods || []).join(", ") || "none")}</small></article>
      <article><span>Qualified reported quarters</span><b>${esc(quarters.present ?? 0)} / ${esc(quarters.required ?? 8)}</b><small>${esc((quarters.qualified_periods || []).join(", ") || "none")} · metadata-only docs: ${esc(documentedInterim.present ?? 0)}</small></article>
      <article><span>Annual operating cash flow</span><b>${esc(cashflow.present ?? 0)} / ${esc(cashflow.required ?? 5)}</b><small>${esc((cashflow.qualified_periods || []).join(", ") || "none")}</small></article>
      <article><span>Annual full statements</span><b>${esc(annualStatements.present ?? 0)} / ${esc(annualStatements.required ?? 5)}</b><small>Source-bound income, balance sheet, cash flow, EBITDA and FCF lineage.</small></article>
      <article><span>Quarterly full statements</span><b>${esc(quarterStatements.present ?? 0)} / ${esc(quarterStatements.required ?? 8)}</b><small>Direct reported quarter flows and point-in-time balance-sheet coverage.</small></article>
    </div>
    <div class="financial-coverage-audit"><div><span>Shares outstanding</span><b>${esc(shares.status || "unknown")}</b><small>${esc(shares.limitation || "Official capital-note tie-out required.")}</small></div><div><span>Next evidence blocker</span><b>${esc(tieOut.reason || "unknown")}</b><small>Qualification remains intentionally blocked.</small></div></div>
    <div class="financial-coverage-docs"><span class="kicker">Retained official document candidates</span>${documents.length ? documents.map(doc => `<article><b>${coverageDocLink(doc)}</b><span>${esc(doc.title || "untitled official document")}</span><small>${esc(doc.reason || "owner review required")}</small></article>`).join("") : `<div class="empty">No retained candidate document references were emitted.</div>`}</div>
  </section>`;
}

function referenceCaseRows(r) {
  return Array.isArray(r?.historical_reference_cases?.cases) ? r.historical_reference_cases.cases : [];
}

function referenceCaseValue(value, unit) {
  if (value == null || value === "") return "not emitted";
  const body = typeof value === "number" && Number.isFinite(value) ? fmt(value, 4) : value;
  return `${body}${unit ? ` ${unit}` : ""}`;
}

function referenceCasePeriods(record) {
  const periods = Array.isArray(record?.period_ends) ? record.period_ends : [];
  return periods.length ? periods.join(", ") : "period_ends not emitted";
}

function referenceCaseFormula(record) {
  const formula = record?.formula && typeof record.formula === "object" && !Array.isArray(record.formula) ? record.formula : {};
  const detail = Object.entries(formula)
    .map(([key, value]) => `${humanEngineKey(key)}: ${engineValue(value)}`)
    .join(" · ");
  return [record?.formula_version, formula.name, detail].filter(Boolean).join(" · ") || "formula not emitted";
}

function referenceCaseSourceLinks(record) {
  const facts = Array.isArray(record?.source_facts) ? record.source_facts : [];
  const seen = new Set();
  const links = facts.flatMap(fact => {
    const pages = Array.isArray(fact?.evidence_pages) && fact.evidence_pages.length ? fact.evidence_pages : [null];
    return pages.map(page => ({ fact, page }));
  }).filter(({ fact, page }) => {
    const key = [fact?.source_url, fact?.document_id, fact?.period_end, page].join("|");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  if (!links.length) return `<div class="empty">No official source fact links were emitted.</div>`;
  return links.map(({ fact, page }) => {
    const href = safeHref(fact?.source_url);
    const label = [
      fact?.document_id || "official document",
      fact?.period_end || "period unknown",
      page ? `p.${page}` : "page unknown",
    ].join(" · ");
    const body = href
      ? `<a href="${href}" target="_blank" rel="noopener">${esc(label)}</a>`
      : `<span>${esc(label)}</span>`;
    return `<article>${body}<small>${esc(fact?.line || "line unknown")} · ${esc(fact?.consolidation || "basis unknown")} · ${esc(fact?.available_on || "availability unknown")}</small></article>`;
  }).join("");
}

function renderHistoricalReferenceCases(r) {
  const records = referenceCaseRows(r);
  return `<section class="baseline-section historical-reference-cases" aria-labelledby="historicalReferenceCasesTitle">
    <h3 id="historicalReferenceCasesTitle">Reported-history reference cases</h3>
    <p class="section-note">Read-only rows from row.historical_reference_cases. They are reported-history-derived reference cases only: not forecasts, not formal valuations, not targets, not recommendations, and not advice.</p>
    ${records.length ? `<div class="reference-case-list">${records.map(record => `<article class="reference-case-card">
      <header>
        <div><span>Metric</span><b>${esc(record.metric || "metric not emitted")}</b></div>
        <div><span>Derived value</span><b>${esc(referenceCaseValue(record.derived_value, record.unit))}</b></div>
      </header>
      <div class="reference-case-grid">
        <span>Covered period ends <b>${esc(referenceCasePeriods(record))}</b></span>
        <span>Availability <b>${esc(record.available_on || "available_on not emitted")}</b></span>
        <span>Status <b>${esc(record.assumption_status || record.approval_scope || "status not emitted")}</b></span>
        <span>Record type <b>${esc(record.record_type || record.case_type || "record type not emitted")}</b></span>
      </div>
      <div class="reference-case-formula"><span class="kicker">Formula</span><p>${esc(referenceCaseFormula(record))}</p></div>
      <div class="reference-case-sources"><span class="kicker">Official source links</span>${referenceCaseSourceLinks(record)}</div>
    </article>`).join("")}</div>` : `<div class="empty">No historical_reference_cases rows were emitted for ${esc(r.symbol || "this company")}.</div>`}
  </section>`;
}

function renderFinancialBaseline(r) {
  const model = r.financial_model_inputs || {};
  const observations = model.observations || {};
  const derived = model.derived || {};
  const observationRows = Object.entries(observations)
    .flatMap(([line, values]) => (Array.isArray(values) ? values : []).map(item => ({ line, item })));
  const readiness = model.status || "unknown";
  const downstream = model.downstream_status || {};
  const downstreamCard = (key, label) => `<div><span>${esc(label)}</span><b>${esc(downstream[key] || "blocked_not_implemented")}</b></div>`;
  const row = (line, item) => `<tr><td>${esc(line)}</td><td>${esc(item.period_end || "Unknown")}</td><td>${esc(item.normalized_value ?? item.value ?? "Unknown")}</td><td>${esc(item.currency || "Unknown")} · ${esc(item.unit || "Unknown")} × ${esc(item.unit_multiplier ?? "Unknown")}</td><td>${esc(item.column_role || "Unknown")} · ${esc(item.consolidation || "Unknown")}</td><td>${esc(item.source_url || item.document_id || "No citation")}</td></tr>`;
  const derivedRows = Object.entries(derived).flatMap(([name, values]) => (values || []).map(v => `<tr><td>${esc(name)}</td><td>${esc(v.period_end || "Unknown")}</td><td>${esc(v.value ?? "Unknown")}</td><td>${esc(v.formula_version || "Unknown")}</td><td>${esc((v.source_fact_ids || []).join(", ") || "Unknown")}</td><td>${esc(v.availability || "Unknown")}</td></tr>`)).join("");
  return `<section class="panel span9 baseline-shell"><span class="kicker">Financial baseline</span><h2>Reported history and deterministic derivations</h2><p class="section-note">Only current parser-version observations are shown. Values, units, citations, and readiness remain exactly as supplied by the financial model input state.</p><div class="baseline-status"><div><span>Readiness</span><b>${esc(readiness)}</b></div><div><span>Driver registry</span><b>${esc(model.registry_version || "qualitative_registry_only")}</b></div>${downstreamCard("forecast", "Forecast")}${downstreamCard("valuation", "Valuation")}${downstreamCard("market_expectations", "Market expectations")}${downstreamCard("scenario_lab", "Scenario Lab")}</div>${model.quality_flags?.length ? `<p class="baseline-warning">Quality flags: ${esc(model.quality_flags.join(", "))}</p>` : ""}${renderFinancialTruthQualification(r)}${renderFinancialCoverage(r)}${renderHistoricalReferenceCases(r)}<section class="baseline-section"><h3>Reported observations</h3>${observationRows.length ? `<div class="baseline-table"><table><thead><tr><th>Line</th><th>Period</th><th>Value</th><th>Unit</th><th>Role / basis</th><th>Official citation</th></tr></thead><tbody>${observationRows.map(({ line, item }) => row(line, item)).join("")}</tbody></table></div>` : `<div class="empty">No verified model-loadable observations are available.</div>`}</section><section class="baseline-section"><h3>Derived metrics</h3>${derivedRows ? `<div class="baseline-table"><table><thead><tr><th>Metric</th><th>Period</th><th>Value</th><th>Formula</th><th>Operands</th><th>Available on</th></tr></thead><tbody>${derivedRows}</tbody></table></div>` : `<div class="empty">No derived growth or margin outputs are available.</div>`}</section></section>`;
}

function renderFinancials(r) {
  const series = r.financial_series || {};
  const facts = series.facts || [];
  const coverage = series.coverage || {};
  const conflicts = series.conflicts || [];
  const trends = buildTrends(facts);
  return `<section class="panel span9">
    <button type="button" class="overview-back-button" data-research-route="directory_financials">Financials workspace</button><span class="kicker">Period-aware extraction</span><h2>Financial facts from official PDFs</h2>
    <p class="section-note">Only labelled values with document/page evidence are shown. Unknown period, unit, basis or currency stays flagged instead of being guessed.</p>
    <div class="series-health">
      ${metric("Facts", coverage.fact_count ?? facts.length, `${coverage.source_documents ?? 0} source documents`)}
      ${metric("Model-loadable", coverage.model_loadable_count ?? 0, `${coverage.audit_only_count ?? facts.length} audit-only`)}
      ${metric("Conflicts", coverage.conflict_count ?? conflicts.length, "same metric/period/basis")}
    </div>
    ${conflicts.length ? `<div class="extract-error">Conflicts need review: ${esc(conflicts.map(c => `${c.metric || "metric"} ${c.period_end || "period unknown"}`).join(", "))}</div>` : ""}
    ${trends.length ? `<div class="trend-grid">${trends.map(renderTrend).join("")}</div>` : `<div class="empty">At least two comparable, explicitly dated facts are required before a trend is drawn.</div>`}
    <div class="fact-table" role="table" aria-label="Extracted financial facts">
      <div role="row" class="fact-table-head"><span>Metric</span><span>Period</span><span>Value</span><span>Basis</span><span>Evidence</span><span>Flags</span></div>
      ${facts.length ? facts.map(fact => {
        const cite = (fact.evidence || [])[0] || {};
        const page = Number(cite.page) > 0 ? `p.${Number(cite.page)}` : "page?";
        const evidence = fact.source_url ? `<a href="${esc(fact.source_url)}" target="_blank" rel="noopener">${esc(page)}</a>` : esc(page);
        const flags = (fact.quality_flags || []).length ? fact.quality_flags.join(", ") : "clean";
        return `<div role="row" class="fact-table-row">
          <span>${esc(fact.metric || "other")}</span>
          <span>${esc(fact.period_end || "unknown")}<small>${esc(fact.period_type || "period type unknown")}</small></span>
          <span><b>${esc(fact.raw_value ?? "unknown")}</b><small>${esc(fact.currency || "currency unknown")} · x${esc(fact.unit_multiplier ?? "?")}</small></span>
          <span>${esc(fact.consolidation || "basis unknown")}<small>${esc(fact.readiness || "audit_only")}</small></span>
          <span>${evidence}</span>
          <span>${esc(flags)}</span>
        </div>`;
      }).join("") : `<div class="empty">No source-linked financial fact has been normalized for this company yet.</div>`}
    </div>
  </section>`;
}

function buildTrends(facts) {
  const groups = new Map();
  facts.forEach(fact => {
    const value = Number(fact.normalized_value);
    if (!fact.period_end || !Number.isFinite(value) || (fact.quality_flags || []).includes("conflict")) return;
    const key = [fact.metric, fact.consolidation, fact.currency, fact.unit_multiplier].join("|");
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(fact);
  });
  return [...groups.values()].map(points => points.sort((a, b) => String(a.period_end).localeCompare(String(b.period_end))))
    .filter(points => points.length >= 2).sort((a, b) => b.length - a.length).slice(0, 6);
}

function renderTrend(points) {
  const values = points.map(point => Number(point.normalized_value));
  const low = Math.min(...values), high = Math.max(...values), spread = high - low || 1;
  const coords = values.map((value, index) => {
    const x = points.length === 1 ? 120 : 8 + index * (224 / (points.length - 1));
    const y = 56 - ((value - low) / spread) * 48;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const latest = points.at(-1);
  return `<article class="trend-card">
    <header><div><span>${esc(latest.metric || "metric")}</span><b>${esc(latest.raw_value ?? "unknown")}</b></div><em>${esc(latest.consolidation || "basis unknown")}</em></header>
    <svg viewBox="0 0 240 64" role="img" aria-label="${esc(latest.metric || "metric")} across ${esc(points.length)} explicitly dated periods"><polyline points="${coords}"></polyline>${coords.split(" ").map(pair => { const [cx, cy] = pair.split(","); return `<circle cx="${cx}" cy="${cy}" r="2.4"></circle>`; }).join("")}</svg>
    <footer><span>${esc(points[0].period_end)}</span><span>${esc(latest.period_end)}</span></footer>
  </article>`;
}

function renderGraphSummary(r) {
  const graph = r.graph || {};
  const summary = graph.summary || {};
  return `<div class="graph-summary">
    <div><b>${esc(summary.document ?? 0)}</b><span>official documents</span></div>
    <div><b>${esc(summary.fact ?? 0)}</b><span>financial fact nodes</span></div>
    <div><b>${esc(summary.period ?? 0)}</b><span>explicit periods</span></div>
    <div><b>${esc(summary.event ?? 0)}</b><span>document events</span></div>
    <div><b>${esc(summary.source ?? 0)}</b><span>issuer/source links</span></div>
  </div>`;
}

function renderGraph(r) {
  const graph = r.graph || {};
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];
  const byId = Object.fromEntries(nodes.map(node => [node.id, node]));
  const layout = layoutGraph(nodes);
  const visibleIds = new Set(layout.map(item => item.node.id));
  const visibleEdges = edges.filter(edge => visibleIds.has(edge.from) && visibleIds.has(edge.to));
  const positions = Object.fromEntries(layout.map(item => [item.node.id, item]));
  const rows = visibleEdges.slice(0, 40);
  return `<section class="panel span9">
    <button type="button" class="overview-back-button" data-research-route="directory_intelligence">Intelligence workspace</button><span class="kicker">Knowledge graph</span><h2>Issuer relationships</h2>
    <p class="section-note">This is a deterministic relationship map over official documents, extracted events, financial facts, periods and monitored issuer sources.</p>
    ${renderGraphSummary(r)}
    ${layout.length ? `<div class="graph-canvas" role="img" aria-label="Evidence-backed company relationship graph">
      <svg viewBox="0 0 1000 540" aria-hidden="true">${visibleEdges.map(edge => {
        const from = positions[edge.from], to = positions[edge.to];
        return `<line x1="${from.x * 10}" y1="${from.y * 5.4}" x2="${to.x * 10}" y2="${to.y * 5.4}"></line>`;
      }).join("")}</svg>
      ${layout.map(({node, x, y}) => renderGraphNode(node, x, y)).join("")}
    </div>` : `<div class="empty">No graph nodes have been built for this company yet.</div>`}
    <div class="edge-list">${rows.length ? rows.map(edge => {
      const left = byId[edge.from]?.label || edge.from;
      const right = byId[edge.to]?.label || edge.to;
      const evidence = edge.evidence || {};
      const provenance = evidence.source_url
        ? `<a href="${esc(evidence.source_url)}" target="_blank" rel="noopener">${evidence.page ? `p.${esc(evidence.page)}` : "source"}</a>`
        : "source unavailable";
      return `<div class="edge-row"><span>${esc(short(left, 30))}</span><b>${esc(edge.type || "linked")}</b><span>${esc(short(right, 30))}</span><em>${provenance}</em></div>`;
    }).join("") : `<div class="empty">No graph edges have been built for this company yet.</div>`}</div>
  </section>`;
}

function layoutGraph(nodes) {
  const layerFor = { company: 0, document: 1, source: 1, event: 2, fact: 2, change: 2, period: 3 };
  const layers = [[], [], [], []];
  nodes.forEach(node => layers[layerFor[node.type] ?? 2].push(node));
  const x = [8, 34, 64, 90];
  return layers.flatMap((layer, layerIndex) => layer.slice(0, layerIndex === 0 ? 1 : 9).map((node, index) => ({
    node, x: x[layerIndex], y: layer.length === 1 ? 50 : 8 + index * (84 / Math.max(1, Math.min(layer.length, 9) - 1)),
  })));
}

function renderGraphNode(node, x, y) {
  const body = `<b>${esc(short(node.label || node.id, 32))}</b><span>${esc(node.type || "node")}</span>`;
  const style = `left:${x}%;top:${y}%`;
  return node.source_url || node.url
    ? `<a class="graph-node kind-${esc(node.type || "other")}" style="${style}" href="${esc(node.source_url || node.url)}" target="_blank" rel="noopener">${body}</a>`
    : `<div class="graph-node kind-${esc(node.type || "other")}" style="${style}">${body}</div>`;
}

function renderFilings(r) {
  const filings = r.filings || [];
  return `<section class="panel span9"><span class="kicker">Official PSX / PUCARS record</span><h2>Filings and announcements</h2>
    <p class="section-note">Facts below are machine-extracted and always paired with their source page. Agent synthesis remains paused for owner approval.</p>
    <div class="filings">${filings.length ? filings.map(doc => `<article class="filing">
      <header><div><time>${esc(String(doc.date || "undated").slice(0, 10))}</time><h3>${esc(doc.title || doc.type || "Official document")}</h3></div><span class="pill ${doc.status === "ready" ? "good" : ""}">${esc(doc.status || "unknown")}</span></header>
      <p class="filing-meta">${esc(doc.type || "unclassified")} · ${doc.url ? `<a href="${esc(doc.url)}" target="_blank" rel="noopener">open official source</a>` : "source unavailable"} · synthesis ${esc(doc.synthesis?.approval_status || "not queued")}</p>
      ${doc.error ? `<p class="extract-error">Extraction retained for retry: ${esc(doc.error)}</p>` : ""}
      ${renderFacts(doc.facts)}
      ${(doc.evidence || []).map(evidenceLink).join("")}
    </article>`).join("") : `<div class="empty">No official PDF has completed extraction for this company yet.</div>`}</div>
  </section>`;
}

function renderFacts(facts) {
  if (!facts?.length) return `<p class="muted">No labelled financial fact was extracted from this document.</p>`;
  return `<div class="fact-grid">${facts.map(fact => {
    const citation = fact.evidence?.[0];
    const page = Number(citation?.page) > 0 ? `page ${Number(citation.page)}` : "page unknown";
    const source = citation?.source_url ? `<a href="${esc(citation.source_url)}" target="_blank" rel="noopener">${esc(page)}</a>` : esc(page);
    return `<div><span>${esc(fact.type || "fact")}</span><b>${esc(fact.raw_value ?? "unknown")}</b><small>${esc(fact.unit || "reported units")} · ${source}</small></div>`;
  }).join("")}</div>`;
}

function renderSources(r) {
  const registry = r.sources || {};
  const pages = registry.sources || [];
  const docs = registry.documents || [];
  return `
    <section class="panel span5"><span class="kicker">Issuer-owned web estate</span><h2>Monitored sources</h2>
      <p class="section-note">Discovered from the official DPS company profile, then restricted to the same issuer domain.</p>
      ${registry.issuer_url ? `<p><a href="${esc(registry.issuer_url)}" target="_blank" rel="noopener">Open issuer website</a></p>` : ""}
      ${pages.length ? pages.map(page => `<div class="source-row"><div><b>${esc(page.title || page.kind || "Issuer page")}</b><span>${esc(page.kind || "page")} · ${esc(page.status || "unknown")}${page.changed ? " · changed" : ""}</span></div><a href="${esc(page.url)}" target="_blank" rel="noopener">open</a></div>`).join("") : `<div class="empty">No issuer page has been verified yet.</div>`}
    </section>
    <section class="panel span4"><span class="kicker">Issuer document index</span><h2>Reports and presentations</h2>
      ${docs.length ? docs.map(doc => `<div class="source-row"><div><b>${esc(doc.title || doc.type || "Issuer document")}</b><span>${esc(doc.type || "document")}${doc.first_seen ? ` · first seen ${esc(String(doc.first_seen).slice(0, 10))}` : ""}</span></div><a href="${esc(doc.url)}" target="_blank" rel="noopener">open</a></div>`).join("") : `<div class="empty">No same-domain report link has been indexed yet.</div>`}
    </section>`;
}

function renderCoverage(r) {
  const quality = r.source_quality || {};
  const financial = r.financial_series?.coverage || {};
  const intel = r.intelligence || {};
  const flags = quality.quality_flags || [];
  return `
    <section class="panel span5"><button type="button" class="overview-back-button" data-research-route="directory_ownership">Ownership &amp; Peers workspace</button><span class="kicker">Evidence coverage</span><h2>What is currently usable</h2>
      <div class="coverage-grid">
        ${metric("Extracted filings", intel.document_count ?? 0, `${intel.event_count ?? 0} events classified`)}
        ${metric("Financial facts", financial.fact_count ?? 0, `${financial.model_loadable_count ?? 0} model-loadable`)}
        ${metric("Issuer documents", quality.document_link_count ?? 0, `${quality.monitored_page_count ?? 0} monitored pages`)}
        ${metric("Pending synthesis", intel.pending_synthesis ?? 0, "owner approval required")}
      </div>
    </section>
    <section class="panel span4"><span class="kicker">Source QA</span><h2>Known limitations</h2>
      <p>Status: <b>${esc(quality.status || "unknown")}</b>. Missing required source: <b>${quality.missing_required_source ? "yes" : "no"}</b>.</p>
      ${flags.length ? `<ul class="quality-flags">${flags.map(flag => `<li>${esc(flag.replaceAll("_", " "))}</li>`).join("")}</ul>` : `<p>No source-registry flag is active for this company.</p>`}
      ${financial.missing_period_count ? `<p>${esc(financial.missing_period_count)} extracted fact${financial.missing_period_count === 1 ? "" : "s"} remain audit-only because the reporting period was not explicit.</p>` : ""}
      ${financial.conflict_count ? `<p>${esc(financial.conflict_count)} comparable period/basis conflict${financial.conflict_count === 1 ? "" : "s"} require review.</p>` : ""}
    </section>`;
}

function renderBrief(r) {
  const current = r.brief?.current;
  if (!current) {
    return `<section class="panel span9"><span class="kicker">Training mode</span><h2>No owner-approved brief yet</h2>
      <p class="section-note">Model synthesis is intentionally paused here. Candidates are written to ignored local cache, independently verified, then approved by the owner before anything becomes durable state.</p>
      <div class="queue-panel">
        <div><b>${esc(r.intelligence?.pending_synthesis ?? 0)}</b><span>pending queue items</span></div>
        <div><b>${esc(r.intelligence?.brief_status || "training_only")}</b><span>publication state</span></div>
        <div><b>${esc(r.brief?.history_count ?? 0)}</b><span>approved history rows</span></div>
      </div>
    </section>`;
  }
  const sections = current.sections || {};
  return `<section class="panel span9"><span class="kicker">Owner-approved synthesis</span><h2>${esc(current.headline || "Company brief")}</h2>
    <p class="section-note">This brief passed deterministic citation validation and independent verifier review before owner approval.</p>
    ${["what_changed", "financial_read", "management_and_capital", "open_questions"].map(key => `<section class="brief-section">
      <h3>${esc(key.replaceAll("_", " "))}</h3>
      ${(sections[key] || []).length ? sections[key].map(item => `<p>${esc(item.text || "")} ${renderBriefEvidence(item.evidence)}</p>`).join("") : `<p class="muted">No approved statements in this section.</p>`}
    </section>`).join("")}
    ${(current.limitations || []).length ? `<div class="limitations"><b>Limitations</b><ul>${current.limitations.map(item => `<li>${esc(item)}</li>`).join("")}</ul></div>` : ""}
  </section>`;
}

function renderBriefEvidence(refs) {
  if (!Array.isArray(refs) || !refs.length) return "";
  return `<small class="brief-cites">${refs.map(ref => {
    const label = `${esc(ref.doc_id || "doc")} p.${esc(ref.page || "?")}`;
    return ref.source_url ? `<a href="${esc(ref.source_url)}" target="_blank" rel="noopener">${label}</a>` : label;
  }).join(" · ")}</small>`;
}

function bindLogin() {
  const form = $("loginForm");
  if (!form) return;
  form.onsubmit = async event => {
    event.preventDefault();
    $("loginMsg").textContent = "Signing in";
    try {
      await signIn($("email").value.trim(), $("password").value);
    } catch (err) {
      $("loginMsg").textContent = err.message || "Sign-in failed.";
    }
  };
}

function enhanceMotion({ visual, animate } = {}) {
  const app = $("app");
  if (!app) return;
  app.classList.remove("is-entering");
  if (visual?.backgroundId) {
    app.dataset.companyBg = visual.backgroundId;
    app.dataset.revealSide = visual.revealSide;
    app.dataset.companyBackgroundSrc = visual.backgroundPath || "";
    const cssUrl = safeBackgroundCssUrl(visual.backgroundPath);
    if (cssUrl) app.style.setProperty("--ci-company-bg", cssUrl);
    else app.style.removeProperty("--ci-company-bg");
  } else {
    delete app.dataset.companyBg;
    delete app.dataset.revealSide;
    delete app.dataset.companyBackgroundSrc;
    app.style.removeProperty("--ci-company-bg");
  }
  if (!animate || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  requestAnimationFrame(() => app.classList.add("is-entering"));
}

$("signOut").onclick = () => {
  saveSession(null);
  state.data = null;
  state.ask.pending = {};
  state.ask.nextId += 1;
  state.theses = { loaded: false, loading: false, saving: false, error: null, bySymbol: {}, drafts: {} };
  renderGate("Signed out.");
};

$("schemeToggle").onclick = () => applyCIScheme(SCHEME_CYCLE[ciScheme()]);
document.addEventListener("click", event => {
  if (event.target.closest?.("[data-case-close]")) {
    event.preventDefault();
    closeIntelligenceCase();
    return;
  }
  if (event.target.closest?.("[data-drawer-close]")) {
    closeMobileDrawers(true);
    return;
  }
  const left = event.target.closest?.("#companyDrawerOpen");
  const right = event.target.closest?.("#intelligenceDrawerOpen");
  if (!left && !right) return;
  event.preventDefault();
  openMobileDrawer(left ? "company" : "intelligence");
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape") closeMobileDrawers(true);
});
window.addEventListener("popstate", () => {
  applyCaseRouteFromLocation({ replace: true });
  if (state.data) renderDesk();
});
window.addEventListener("resize", () => {
  if (!window.matchMedia(CI_MOBILE_QUERY).matches) closeMobileDrawers();
  else syncMobileControls(!!state.data);
});
normalizeCIShell();
applyCIScheme(SCHEME_CYCLE[ciScheme()]);

state.session = storedSession();
if (state.session) loadData();
else renderGate();
