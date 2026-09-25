/* Henneth Desk SPA — path router, 4 themes, canvas charts.
   Routes: /board · /ticker/SYM · /dividends · /news
   All data from ../state/*.json (DPS-sourced). No external deps. */

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function safeExternalHref(u) {
  const s = String(u ?? "").trim();
  try {
    const parsed = new URL(s);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? s : "";
  } catch {
    return "";
  }
}
function externalLink(u, html, attrs = "") {
  const href = safeExternalHref(u);
  return href ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer"${attrs ? " " + attrs : ""}>${html}</a>` : "";
}
const sgn = v => (v > 0 ? "+" : "") + v;
const cls = v => v > 0.05 ? "up" : v < -0.05 ? "dn" : "";
const fmt = (v, d = 2) => v == null ? "—" : Number(v).toLocaleString("en", { maximumFractionDigits: d });
// Today's PKT calendar date. `new Date().toISOString().slice(0,10)` is the UTC date, and PKT is
// UTC+5 — so between 00:00 and 04:59 PKT it names YESTERDAY. Every date in state/ is a PKT
// trading date (CLAUDE.md), so comparing them to a UTC date is an off-by-one for five hours a
// day: a results date that has already passed still reads as "next", with a negative countdown.
// Use this for any date COMPARISON against state/ data; a display-only stamp can stay as-is.
const todayPKT = () => new Date(Date.now() + 5 * 3600000).toISOString().slice(0, 10);

// Data source: local dev reads ../state/ ; the deployed dashboard (GitHub Pages)
// reads state/ published alongside it by the GitHub Actions pipeline every 30 min.
const LOCAL = ["localhost", "127.0.0.1", ""].includes(location.hostname);
const DATA_BASE = LOCAL ? "../state/" : "state/";
const APP_BASE = (document.querySelector("base")?.getAttribute("href") || "/").replace(/\/$/, "") || "";
function appPathname() {
  const p = location.pathname || "/";
  return APP_BASE && p.startsWith(APP_BASE + "/") ? p.slice(APP_BASE.length) || "/" : p;
}
window.appPathname = appPathname;

/* --------------------------------------------------------------------------
   ONE ROUTER, TWO TRANSITION STATES

   The dashboard is a static SPA, so the URL is both its addressable deep link
   and its browser history. `navigate()` is the only in-app transition helper;
   `route()` below remains the only dispatcher. The small `routeHash()` adapter
   exists only for page renderers that still compare their current route while
   this migration is rolled out. It never writes a fragment to the URL.

   Supabase email callbacks still arrive as protocol fragments (`#access_token=`,
   `#error_code=`, etc.). Those are intentionally handled separately below and
   are never treated as dashboard routes. */
function routeHash() {
  const p = appPathname().replace(/\/+$/, "") || "/";
  return p === "/" ? "#/today" : "#" + p + (location.search || "");
}

function normalizeLegacyHash() {
  const h = location.hash || "";
  if (!h.startsWith("#/")) return false;
  const raw = h.slice(1);
  try {
    const u = new URL(raw, location.origin);
    history.replaceState(null, "", APP_BASE + u.pathname + u.search);
    return true;
  } catch { return false; }
}

function navigate(path, replace = false) {
  const u = new URL(path || "/today", location.origin);
  const clean = u.pathname.replace(/\/{2,}/g, "/");
  const target = (APP_BASE && !clean.startsWith(APP_BASE + "/") ? APP_BASE : "") + clean + u.search;
  const current = (location.pathname || "/") + (location.search || "");
  if (target === current && !location.hash) { route(true); return; }
  history[replace ? "replaceState" : "pushState"]({}, "", target);
  try { window.dispatchEvent(new CustomEvent("henneth:navigate", { detail: { path: target, replace } })); } catch {}
  route(false);
}
window.navigate = navigate;

// Overlay history: opening a full-screen/modal overlay pushes a history entry so the phone's
// Back gesture closes it instead of leaving the desk. popstate runs the most-recently-registered
// closer. Escape-key handlers stay as they are — this is additive, not a replacement.
// Re-entrant safe: _overlayBack guards our own history.back() unwind (Escape/outside-click close
// while the overlay's entry is still live), and _inPopstate stops a popstate-driven close from
// calling history.back() again.
const _overlayStack = [];
let _overlayBack = false;
let _inPopstate = false;

// Focus containment for overlays: keeps Tab/Shift+Tab cycling inside `el`, makes the app shell
// (or whatever's behind it) inert while open, and restores focus to the trigger on release().
// One helper shared by every overlay on the pushOverlay stack rather than one trap per overlay.
const FOCUSABLE_SEL = 'a[href], button, input, select, textarea, summary, [tabindex], [contenteditable="true"]';
function focusableIn(root) {
  return [...root.querySelectorAll(FOCUSABLE_SEL)].filter(el =>
    !el.hasAttribute("hidden") && !el.disabled && el.tabIndex !== -1
  );
}
function trapFocus(el, { noInert } = {}) {
  const trigger = document.activeElement;
  const shellEl = document.getElementById("shell");
  // Only inert the shell if `el` isn't part of it (e.g. the mobile drawer lives inside #shell —
  // inerting the shell would make the drawer, and its own trigger button, unreachable).
  const inerted = !noInert && shellEl && !shellEl.contains(el);
  if (inerted) shellEl.inert = true;
  let first = focusableIn(el)[0];
  if (!first) { if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "-1"); first = el; }
  first.focus();
  function onKeydown(e) {
    if (e.key !== "Tab") return;
    const items = focusableIn(el);
    if (!items.length) { e.preventDefault(); return; }
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === items[0]) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); items[0].focus(); }
  }
  el.addEventListener("keydown", onKeydown);
  return function release() {
    el.removeEventListener("keydown", onKeydown);
    if (inerted) shellEl.inert = false;
    if (trigger && typeof trigger.focus === "function" && document.body.contains(trigger)) trigger.focus();
  };
}

// `el` (optional) is the overlay/panel to trap focus inside; `opts` is forwarded to trapFocus
// (e.g. { noInert: true } for panels that live inside #shell, like the mobile drawer).
function pushOverlay(close, el, opts) {
  _overlayStack.push({ close, release: el ? trapFocus(el, opts) : null });
  history.pushState({ henOverlay: true }, "", location.href);
}
function popOverlay(close) {
  const i = _overlayStack.findIndex(o => o.close === close);
  if (i === -1) return; // already unwound (e.g. by the popstate handler below)
  const [entry] = _overlayStack.splice(i, 1);
  entry.release?.();
  if (!_inPopstate) { _overlayBack = true; history.back(); }
}
// Exposed so overlays living in other bundles (topbar.js) share one stack.
window.pushOverlay = pushOverlay;
window.popOverlay = popOverlay;
window.addEventListener("popstate", () => {
  if (_overlayBack) { _overlayBack = false; return; } // our own unwind — nothing to close
  const entry = _overlayStack[_overlayStack.length - 1];
  if (!entry) return;
  _inPopstate = true;
  entry.close();
  _inPopstate = false;
});

// Keep ordinary dashboard anchors in the SPA while retaining real links for
// modified clicks, downloads, external URLs, and mailto actions. The route
// parser above remains the single source of truth; this only chooses whether
// the browser performs a full document load or a History API transition.
document.addEventListener("click", (e) => {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  const a = e.target.closest?.("a[href]");
  if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
  let u;
  try { u = new URL(a.href, location.href); } catch { return; }
  if (u.origin !== location.origin || u.hash || u.pathname.startsWith("/state/") || u.pathname.startsWith("/api/") || /\.[a-z0-9]{2,6}$/i.test(u.pathname)) return;
  e.preventDefault();
  navigate(u.pathname + u.search + u.hash);
});

// Some browser extensions (ad/anti-fraud blockers) monkey-patch window.fetch and
// throw "TypeError: Failed to fetch" on same-origin requests unrelated to ads —
// seen in the wild breaking every state/*.json load. XHR isn't patched by those
// extensions, so it's the fallback when fetch itself throws (not just a bad response).
function xhrJson(url, token) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("GET", url, true);
    if (token) x.setRequestHeader("Authorization", "Bearer " + token);
    x.onload = () => { if (x.status >= 200 && x.status < 300) { try { resolve(JSON.parse(x.responseText)); } catch (e) { reject(e); } } else reject(new Error("HTTP " + x.status)); };
    x.onerror = () => reject(new Error("xhr network error"));
    x.send();
  });
}

/* ==========================================================================================
   THE ACCOUNT GATE, CLIENT SIDE

   Every /state/ request now carries the Supabase access token, which middleware.js verifies at
   the edge before the CDN will serve the file. Without it the desk's research is a public
   download; see that file's header for the full reasoning.

   READ ORDER MATTERS. localStorage is read FIRST and the Supabase client only as a fallback:
   `sb` is declared with `const` far below this line, and j() runs long before that line is
   evaluated. Touching a const in its temporal dead zone throws ReferenceError — and `typeof`
   does NOT save you, it throws too. This file has hit that exact bug three times (applyDeskMode,
   isSignedIn, and the boot flash), so the primary path deliberately avoids `sb` entirely and the
   fallback is wrapped in try/catch that swallows the TDZ throw.

   The storage key is derived from the Supabase project ref and must track SB_URL below and the
   boot script in index.html. If the project ref ever changes and this string does not, every
   request silently loses its token and the desk 401s on everything. */
const SB_STORAGE_KEY = "sb-qteoncckohuoatbjjykb-auth-token";

function tokenFromStorage() {
  try {
    const raw = localStorage.getItem(SB_STORAGE_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw);
    return s?.access_token || null;
  } catch { return null; }
}

async function authToken() {
  const stored = tokenFromStorage();
  if (stored) return stored;
  // Fallback only — and only if `sb` has actually been initialised by now.
  try {
    const { data } = await sb.auth.getSession();
    return data?.session?.access_token || null;
  } catch { return null; }
}

/* Access tokens live about an hour. The Supabase client refreshes them in the background and
   writes the new one back to localStorage, but a tab left open past expiry can still fire a
   request with a stale token and get a 401. Rather than surface that as a data failure, force one
   refresh and let the caller retry — this is the difference between "the desk broke" and a hiccup
   the user never sees. */
let _refreshing = null;
async function refreshSession() {
  if (_refreshing) return _refreshing;
  _refreshing = (async () => {
    try {
      const { data } = await sb.auth.refreshSession();
      return data?.session?.access_token || null;
    } catch { return null; }
    finally { setTimeout(() => { _refreshing = null; }, 1000); }
  })();
  return _refreshing;
}

/* A single persistent banner slot for desk-wide conditions the user must know about even though
   nothing on the current page failed to render (offline, session expired). Only one banner shows
   at a time — session-expired is the more urgent of the two and replaces an offline banner if both
   fire, since there is no point telling someone to check their connection when the real problem is
   their sign-in. */
const BANNER_PRIORITY = { sessionBanner: 2, offlineBanner: 1 };
function showBanner(id, html) {
  const myRank = BANNER_PRIORITY[id] || 0;
  // Enforce the one-banner invariant documented above: a more urgent banner already
  // showing keeps its slot (this call is a no-op); showing a more urgent banner evicts
  // any less-urgent one first.
  for (const other in BANNER_PRIORITY) {
    if (other === id) continue;
    if (BANNER_PRIORITY[other] > myRank) return;
    if (BANNER_PRIORITY[other] < myRank) hideBanner(other);
  }
  let b = document.getElementById(id);
  if (!b) {
    b = document.createElement("div");
    b.id = id;
    /* IN FLOW, NOT FIXED, AND FIRST IN THE BODY — deliberate. It used to be
       `position:fixed;top:0` appended to the end of body, which floated it over the topbar and hid
       the nav exactly when the user most needs it (offline / signed out). In flow at the top it
       pushes the whole page down instead, so nothing is ever covered and no element needs to know
       the banner's height. */
    b.style.cssText = "position:relative;z-index:9998;background:var(--dn);color:#fff;"
      + "font:13px/1.4 system-ui,sans-serif;padding:8px 14px;text-align:center;border-radius:0";
    document.body.prepend(b);
  }
  b.innerHTML = html;
}
function hideBanner(id) { document.getElementById(id)?.remove(); }

window.addEventListener("offline", () => showBanner("offlineBanner", "You're offline — showing the last data the desk loaded."));
window.addEventListener("online", () => hideBanner("offlineBanner"));

const cache = {};
/* backtests.json stores each strategy's name/category ONCE in `meta`, not repeated on all
   ~200 per-ticker rows (that duplication was most of the file's weight, and the file is
   rewritten and committed every cycle). Re-attach them here, at the single load point, so
   every reader downstream keeps seeing entry.name / entry.category exactly as before.
   Tolerates the old shape: if a file without `meta` is served (stale deploy, cached copy),
   the per-entry values are already present and nothing is overwritten. */
function rehydrateBacktests(v) {
  const meta = v?.meta, tpl = v?.templates;
  if (!meta || !tpl) return v;
  for (const [sid, per] of Object.entries(tpl)) {
    const m = meta[sid];
    if (!m || !per) continue;
    for (const row of Object.values(per)) {
      if (row && row.name == null) { row.name = m.name; row.category = m.category; }
    }
  }
  return v;
}

/* HOW LONG A PAYLOAD MAY BE REUSED, keyed to how often the desk actually rewrites it.

   This used to be a flat 25s for every file, combined with a `?t=<now>` cache-buster on the URL.
   Together those two made mobile navigation as slow as it is: the buster gives every request a
   unique URL, so the browser's HTTP cache can never serve or even revalidate one, and the 25s
   window expires while somebody is still reading the page they are on. Tap through to another
   page a minute later and the desk re-downloads the whole payload — dossiers.json alone is
   ~840 KB, rooms.json ~286 KB — over a mobile connection, every single time.

   Nothing needed that. The desk rewrites state on a 30-minute cycle, so a client-side window
   measured in minutes is still an order of magnitude fresher than the data behind it. Only the
   handful of files that genuinely move inside a cycle keep a short window AND the buster. */
const TTL_LIVE = 30_000;          // moves intraday — must not be held
const TTL_DEFAULT = 10 * 60_000;  // rewritten at most once per 30-minute cycle
const LIVE_FILES = new Set(["live.json", "health.json", "runlog.json", "news.json", "newslog.json", "live_triggers.json"]);

async function j(p, ttl) {
  if (ttl == null) ttl = LIVE_FILES.has(p) ? TTL_LIVE : TTL_DEFAULT;
  const now = Date.now();
  if (cache[p] && now - cache[p].t < ttl) return cache[p].v;
  // several attempts across two transports; never cache a failure (a transient miss
  // must not blank the page for the whole TTL) — falls back to last-known-good if all fail.
  //
  // The buster is now scoped to the live files only. Everything else is fetched at a STABLE url so
  // the HTTP cache can do its job: a repeat navigation inside the Cache-Control window costs no
  // network at all, and outside it costs a 304 with no body instead of a fresh megabyte.
  const url = () => DATA_BASE + p + (LIVE_FILES.has(p) ? "?t=" + Date.now() : "");
  let lastErr = null;
  let tok = await authToken();
  let refreshed401 = false; // the refresh already happened once — a second 401 means the session is really gone
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const hdrs = tok ? { Authorization: "Bearer " + tok } : undefined;
      const v = attempt < 2
        ? await fetch(url(), { headers: hdrs }).then(async r => {
            // 401 from the edge gate means the token is stale, not that the data is gone.
            // Refresh once and let the retry loop use the new one. Distinguished from every
            // other HTTP error so a genuine 404 is not masked as an auth problem.
            if (r.status === 401) {
              if (refreshed401) return Promise.reject(new Error("HTTP 401 (session expired)"));
              refreshed401 = true;
              const fresh = await refreshSession();
              if (fresh && fresh !== tok) tok = fresh;
              return Promise.reject(new Error("HTTP 401 (auth refreshed, retrying)"));
            }
            return r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status));
          })
        : await xhrJson(url(), tok); // last attempt: bypass a fetch() an extension may have broken
      cache[p] = { t: Date.now(), v: p === "backtests.json" ? rehydrateBacktests(v) : v };
      // A successful fetch clears BOTH conditions the banner slot tracks: we're back online,
      // and the token just worked, so a stale "session expired" banner from an earlier 401
      // no longer applies — leaving it pinned would strand a recovered user forever.
      hideBanner("offlineBanner");
      hideBanner("sessionBanner");
      return cache[p].v;
    } catch (e) { lastErr = e; /* fall through to retry */ }
    if (attempt < 2) await new Promise(res => setTimeout(res, 300));
  }
  // All 3 attempts (2x fetch + 1x XHR) failed — surface this, don't swallow it silently.
  // A "Failed to fetch" with no HTTP status usually means a browser extension or network
  // policy blocked the request before it left the browser (check the Network tab's status
  // column for "(blocked)" / "ERR_BLOCKED_BY_CLIENT"), not a server-side data problem.
  console.warn(`[psx-desk] j("${p}") failed after all attempts:`, lastErr);
  // The refresh already ran once (refreshed401) and STILL got a 401 — this is not a network
  // hiccup, the session is gone. middleware.js fails closed, so silently serving stale/null here
  // is a dead screen with no way back. Tell the user and point them at the same sign-in path
  // acctOut/openAuth already use, rather than inventing a second auth flow.
  if (refreshed401 && /401/.test(lastErr?.message || "")) {
    showBanner("sessionBanner", `Your session expired — <button id="sessionSignIn" style="background:none;border:1px solid #fff;color:#fff;padding:2px 10px;border-radius:0;cursor:pointer;margin-left:6px">Sign in again</button>`);
    document.getElementById("sessionSignIn")?.addEventListener("click", () => { hideBanner("sessionBanner"); openAuth("signin"); });
  } else {
    showBanner("offlineBanner", "You're offline — showing the last data the desk loaded.");
  }
  return cache[p]?.v ?? null; // serve last-known-good if we ever had it
}

/* ---------- header chips ---------- */
function marketStatus() {
  const d = new Date(), day = d.getDay(), m = d.getHours() * 60 + d.getMinutes();
  const bt = (a, b) => m >= a && m <= b;
  if (day === 0 || day === 6) return ["WEEKEND", false];
  if (day === 5) return bt(557, 720) || bt(872, 990) ? ["LIVE", true] : ["CLOSED", false];
  return bt(572, 930) ? ["LIVE", true] : ["CLOSED", false];
}
/* ------------------------------------------------------------------------------------------
   VERSION + WHAT'S NEW.

   Reads state/changelog.json, which scripts/build_changelog.py extracts from the `public` blocks
   in CHANGELOG.md. That file is the ENGINEERING record — it names migrations and describes a
   security hole that was closed — so nothing here ever renders it directly. Only the curated
   notes reach a reader, and the extractor fails closed when a release has no public block.

   The badge is always visible so "how current is my desk?" is answerable at a glance. The dot,
   and the panel, appear only when the published version differs from the last one this browser
   acknowledged — so a returning reader is told once, not nagged every visit.

   VERSIONING is CalVer (YYYY.MM.DD, plus .2 for a second release the same day). Comparison is a
   plain string inequality on purpose: any change at all is "something is new", and trying to
   decide whether a version is NEWER would need parsing, which buys nothing here — the desk only
   ever moves forward. */
const VER_SEEN_KEY = "henneth:ver-seen";

/* WRITE ONLY WHAT CHANGED. The header re-renders on every route AND on a 60s timer, and it used to
   re-assign every string unconditionally. An assignment to textContent/innerHTML replaces the node
   even when the text is identical — which reflows the topbar and fires the MutationObserver below,
   whose flush() then walks the whole document. Comparing first makes the common case (nothing
   moved) cost nothing at all. */
function setText(el, v) { if (el && el.textContent !== v) el.textContent = v; }
function setClass(el, v) { if (el && el.className !== v) el.className = v; }
function setHtml(el, v) { if (el && el.innerHTML !== v) el.innerHTML = v; }
function setDisp(el, v) { if (el && el.style.display !== v) el.style.display = v; }

/* ONE closing path for every overlay in this file. Each modal used to remove its node outright,
   so the exit animation the stylesheet defines never played on most of them — and the two that
   did animate had hand-rolled, subtly different fallbacks. The overlay (and its box, when the
   animation lives there) gets `modal-closing`; the node drops on animationend, with a 250ms
   timer for reduced-motion or an element that never animates. Double-close guarded: Esc and a
   backdrop click can both land in the same frame. */
function closeAnimated(ov, boxSel) {
  if (!ov || ov.dataset.closing) return;
  ov.dataset.closing = "1";
  ov.classList.add("modal-closing");
  const box = boxSel ? ov.querySelector(boxSel) : null;
  if (box) box.classList.add("modal-closing");
  let gone = false;
  const drop = () => { if (gone) return; gone = true; ov.remove(); };
  ov.addEventListener("animationend", e => { if (e.target === ov || e.target === box) drop(); });
  setTimeout(drop, 250);
}

/* A number that moved on a poll should say so for a moment. Only a REAL change flashes — same
   value, unparseable value, or first render (no old value) stay silent, so a quiet tape looks
   quiet. The class is stripped again on animationend, with a timer as the belt-and-braces path
   in case the element is off-screen and the animation never fires. */
function flashDelta(el, oldV, newV) {
  if (!el) return;
  const num = v => { const f = parseFloat(String(v == null ? "" : v).replace(/[^0-9.\-]/g, "")); return isNaN(f) ? null : f; };
  const a = num(oldV), b = num(newV);
  if (a === null || b === null || a === b) return;
  el.classList.remove("flash-up", "flash-dn");
  const k = b > a ? "flash-up" : "flash-dn";
  // re-adding on the next frame restarts a still-running animation without a forced reflow —
  // the tape patches up to 18 of these per poll, and a sync offsetWidth read per cell added up
  requestAnimationFrame(() => el.classList.add(k));
  const off = () => { el.classList.remove(k); el.removeEventListener("animationend", off); clearTimeout(t); };
  const t = setTimeout(off, 500);
  el.addEventListener("animationend", off);
}

async function renderVersion() {
  const el = $("sideVer");
  if (!el) return;
  const cl = await j("changelog.json");
  const cur = cl?.current;
  if (!cur) return;                       // no changelog yet -> no badge, not a broken row
  let seen = null;
  try { seen = localStorage.getItem(VER_SEEN_KEY); } catch {}
  const fresh = seen !== cur;
  // count releases newer than the last one this browser saw, so the bell shows HOW MANY
  // updates piled up (e.g. tickers added across several cycles), not just "something changed"
  const rels = cl?.releases || [];
  const seenIdx = seen === null ? -1 : rels.findIndex(r => r.version === seen);
  const unseen = seen === null ? 0 : (seenIdx === -1 ? rels.length : seenIdx);
  if (el.hidden) el.hidden = false;
  setClass(el, "side-ver" + (fresh ? " fresh" : ""));
  const badge = fresh && unseen > 0 ? `<i class="ver-dot">${unseen > 9 ? "9+" : unseen}</i>` : "";
  setHtml(el, `${bellSvg()}<span>v${esc(cur)}</span>${badge}`);
  el.title = fresh ? `${unseen} update${unseen === 1 ? "" : "s"} since you last looked — click to read` : "What's new";
  el.onclick = () => openWhatsNew(cl);
  // First run on a browser that has never stored a version: record it WITHOUT showing the panel.
  // Otherwise every new visitor is greeted by a changelog for a product they have not used yet.
  if (seen === null) { try { localStorage.setItem(VER_SEEN_KEY, cur); } catch {} setClass(el, "side-ver"); setHtml(el, `${bellSvg()}<span>v${esc(cur)}</span>`); }
}

function bellSvg() {
  return '<svg class="ver-bell" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 4 1.5 5.5 2 6.5H4c.5-1 2-2.5 2-6.5"/><path d="M10 19a2 2 0 0 0 4 0"/></svg>';
}

function openWhatsNew(cl) {
  const rels = (cl?.releases || []).slice(0, 5);
  if (!rels.length) return;
  try { localStorage.setItem(VER_SEEN_KEY, cl.current); } catch {}
  const body = rels.map((r, i) => `
    <div class="wn-rel${i === 0 ? " wn-now" : ""}">
      <div class="wn-h"><b>v${esc(r.version)}</b>${r.title ? `<span>${esc(r.title)}</span>` : ""}<i>${esc(r.date)}</i></div>
      <ul>${(r.notes || []).map(n => `<li>${esc(n)}</li>`).join("")}</ul>
    </div>`).join("");
  const ov = document.createElement("div");
  ov.className = "pl-overlay wn-overlay";
  // `wn-panel` carries its own box (background, border, max-height, scroll). It used to also carry
  // `pl-panel` — a class that has never existed: the lesson player's box is `.pl-box`. Nothing
  // styled the panel, so it rendered as bare text floating over the dimmed page.
  ov.innerHTML = `<div class="wn-panel" role="dialog" aria-modal="true" aria-label="What's new">
    <div class="wn-top">
      <h2>What's new</h2>
      <button class="pl-x wn-x" aria-label="Close">✕</button>
    </div>
    <p class="sub wn-sub">Changes a reader would notice. The full engineering record stays in the repo.</p>
    <div class="wn-body">${body}</div>
  </div>`;
  function esc2(e) { if (e.key === "Escape") close(); }
  const close = () => { document.removeEventListener("keydown", esc2); popOverlay(close); closeAnimated(ov, ".wn-panel"); renderVersion(); };
  ov.onclick = e => { if (e.target === ov || e.target.classList.contains("pl-x")) close(); };
  document.addEventListener("keydown", esc2);
  pushOverlay(close, ov);
  ov._close = () => { document.removeEventListener("keydown", esc2); popOverlay(close); ov.remove(); };  // route() teardown: node + listener, skip renderVersion
  document.body.appendChild(ov);
}

async function renderHeader() {
  renderVersion();          // fire and forget — the badge must never delay the header
  const [health, quant, live, macro, dash] = await Promise.all([j("health.json"), j("quant.json"), j("live.json"), j("macro.json"), j("dashboard.json")]);
  const [mt, mo] = marketStatus();
  setText($("mkt"), "PSX " + mt); setClass($("mkt"), "pill " + (mo ? "ok" : ""));
  if (health) { setText($("health"), "HEALTH " + health.status.toUpperCase()); setClass($("health"), "pill " + (health.status === "ok" ? "ok" : "bad")); $("health").title = (health.problems || []).join("; "); }
  const reg = macro?.regime || "—";
  setText($("regime"), "REGIME: " + reg.toUpperCase()); setClass($("regime"), "pill clickable " + (reg === "risk-off" ? "bad" : reg === "risk-on" ? "ok" : ""));
  $("regime").onclick = () => navigate("/macro");
  const geo = dash?.geo_risk;
  const gc = $("georisk");
  if (gc && geo?.score != null) {
    setDisp(gc, "");
    // the one numeric pill in the topbar: say so when the 60s poll moves it. (The others are
    // words — market/health/regime — and #updated is a timestamp, which flashes on every poll.)
    flashDelta(gc, gc.textContent, "RISK " + geo.score);
    setText(gc, "RISK " + geo.score);
    setClass(gc, "pill clickable " + (geo.band === "elevated" ? "bad" : geo.band === "calm" ? "ok" : ""));
    gc.title = `Geopolitical & market-stress radar: ${geo.score}/100 (${geo.band}). Click for the factors.`;
    gc.onclick = () => navigate("/macro");
  } else if (gc) { setDisp(gc, "none"); }
  $("regime").title = reg === "—" ? "Macro regime — not published yet this cycle" :
    `Macro regime = the desk's risk posture (${reg}). ${reg === "risk-on" ? "Full setups allowed." : reg === "risk-off" ? "Max 2 setups, defensive only." : "Neutral — normal caution."} Click for the drivers.`;
  setText($("updated"), "analysis built " + (quant?.updated || "—") + " · market snapshot " + (live?.source_at || "unknown"));
}

/* ---------- canvas chart ---------- */
/* THEME COLOURS ARE READ ONCE, NOT PER DRAW. getComputedStyle() forces a style flush, and the
   chart redraws on every range button, every resize and every ticker navigation. The palette is
   stamped on <body data-theme> at boot and nothing in the app rewrites it, so one read is honest.
   invalidateChartColors() exists so a future theme switcher has a hook to call. */
let _chartCss = null;
function chartColors() {
  if (_chartCss) return _chartCss;
  const css = getComputedStyle(document.body);
  _chartCss = {
    up: css.getPropertyValue("--up").trim(),
    dn: css.getPropertyValue("--dn").trim(),
    accent: css.getPropertyValue("--accent").trim(),
    ink: css.color,
  };
  return _chartCss;
}
function invalidateChartColors() { _chartCss = null; }

/* One rAF per frame, no matter how many mousemove events land in it. Raw mousemove fires far
   faster than the screen repaints, and each handler wrote innerHTML + two style properties —
   layout work thrown away before it was ever seen. */
function rafTooltip(canvas, handler) {
  let latest = null, pending = false;
  canvas.onmousemove = e => {
    latest = { clientX: e.clientX, clientY: e.clientY };
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; if (latest) handler(latest); });
  };
}

function drawChart(canvas, tooltip, hist, days) {
  const rows = hist.slice(-days);
  const W = canvas.clientWidth, H = canvas.clientHeight || 320;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext("2d"); ctx.scale(dpr, dpr);
  const _c = chartColors();
  const up = _c.up, dn = _c.dn;
  const accent = _c.accent;
  const ink = _c.ink;
  const padL = 8, padR = 56, padT = 10, volH = 46, plotH = H - volH - 26;

  const closes = rows.map(r => r.close), vols = rows.map(r => r.volume);
  const lo = Math.min(...closes), hi = Math.max(...closes), span = (hi - lo) || 1;
  const vmax = Math.max(...vols) || 1;
  const X = i => padL + i / (rows.length - 1) * (W - padL - padR);
  const Y = v => padT + (1 - (v - lo) / span) * plotH;

  ctx.clearRect(0, 0, W, H);
  // gridlines + right axis labels
  ctx.globalAlpha = .35; ctx.strokeStyle = ink; ctx.lineWidth = .5;
  ctx.font = "10px sans-serif"; ctx.fillStyle = ink;
  for (let g = 0; g <= 3; g++) {
    const v = lo + span * g / 3, y = Y(v);
    ctx.globalAlpha = .12; ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
    ctx.globalAlpha = .55; ctx.fillText(fmt(v), W - padR + 6, y + 3);
  }
  ctx.globalAlpha = 1;
  // volume bars
  const pos = closes[closes.length - 1] >= closes[0];
  rows.forEach((r, i) => {
    ctx.fillStyle = (i > 0 && r.close >= rows[i - 1].close) ? up : dn;
    ctx.globalAlpha = .45;
    const bh = (r.volume / vmax) * volH;
    ctx.fillRect(X(i) - 1, H - 20 - bh, 2, bh);
  });
  ctx.globalAlpha = 1;
  // price line + soft area
  const lineC = pos ? up : dn;
  ctx.beginPath();
  rows.forEach((r, i) => i ? ctx.lineTo(X(i), Y(r.close)) : ctx.moveTo(X(i), Y(r.close)));
  ctx.strokeStyle = lineC; ctx.lineWidth = 2; ctx.stroke();
  ctx.lineTo(X(rows.length - 1), padT + plotH); ctx.lineTo(X(0), padT + plotH); ctx.closePath();
  ctx.globalAlpha = .08; ctx.fillStyle = lineC; ctx.fill(); ctx.globalAlpha = 1;
  // date ticks
  ctx.fillStyle = ink; ctx.globalAlpha = .55;
  [0, Math.floor(rows.length / 2), rows.length - 1].forEach(i => {
    ctx.fillText(rows[i].date, Math.min(X(i), W - padR - 58), H - 6);
  });
  ctx.globalAlpha = 1;

  rafTooltip(canvas, e => {
    const rect = canvas.getBoundingClientRect();
    const i = Math.round((e.clientX - rect.left - padL) / (W - padL - padR) * (rows.length - 1));
    if (i < 0 || i >= rows.length) { tooltip.style.display = "none"; return; }
    const r = rows[i];
    tooltip.style.display = "block";
    tooltip.style.left = Math.min(e.clientX - rect.left + 12, W - 150) + "px";
    tooltip.style.top = "8px";
    const chg = i ? ((r.close / rows[i - 1].close - 1) * 100) : 0;
    tooltip.innerHTML = `<b>${r.date}</b><br>close ${fmt(r.close)} <span class="${cls(chg)}">${sgn(chg.toFixed(2))}%</span><br>vol ${fmt(r.volume, 0)}`;
  });
  canvas.onmouseleave = () => tooltip.style.display = "none";
}

function drawIntraday(canvas, tooltip, points, prevClose) {
  const W = canvas.clientWidth, H = canvas.clientHeight || 320, dpr = window.devicePixelRatio || 1;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext("2d"); ctx.scale(dpr, dpr);
  const _c = chartColors();
  const up = _c.up, dn = _c.dn, ink = _c.ink;
  const padL = 8, padR = 56, padT = 12, plotH = H - 40;
  const prices = points.map(p => p.p);
  const lo = Math.min(prevClose, ...prices), hi = Math.max(prevClose, ...prices), span = (hi - lo) || 1;
  const X = i => padL + i / (points.length - 1) * (W - padL - padR);
  const Y = v => padT + (1 - (v - lo) / span) * plotH;
  ctx.clearRect(0, 0, W, H);
  ctx.font = "10px sans-serif"; ctx.fillStyle = ink;
  for (let g = 0; g <= 3; g++) { const v = lo + span * g / 3, y = Y(v); ctx.globalAlpha = .1; ctx.strokeStyle = ink; ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke(); ctx.globalAlpha = .55; ctx.fillText(fmt(v), W - padR + 6, y + 3); }
  ctx.globalAlpha = .5; ctx.strokeStyle = ink; ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(padL, Y(prevClose)); ctx.lineTo(W - padR, Y(prevClose)); ctx.stroke(); ctx.setLineDash([]); ctx.globalAlpha = 1;
  const pos = prices[prices.length - 1] >= prevClose, lineC = pos ? up : dn;
  ctx.beginPath(); points.forEach((p, i) => i ? ctx.lineTo(X(i), Y(p.p)) : ctx.moveTo(X(i), Y(p.p)));
  ctx.strokeStyle = lineC; ctx.lineWidth = 1.8; ctx.stroke();
  ctx.lineTo(X(points.length - 1), padT + plotH); ctx.lineTo(X(0), padT + plotH); ctx.closePath();
  ctx.globalAlpha = .08; ctx.fillStyle = lineC; ctx.fill(); ctx.globalAlpha = 1;
  const tlabel = t => new Date(t * 1000).toLocaleTimeString("en", { hour: "2-digit", minute: "2-digit" });
  ctx.fillStyle = ink; ctx.globalAlpha = .55;
  [0, Math.floor(points.length / 2), points.length - 1].forEach(i => ctx.fillText(tlabel(points[i].t), Math.min(X(i), W - padR - 40), H - 6));
  ctx.globalAlpha = 1;
  rafTooltip(canvas, e => {
    const rect = canvas.getBoundingClientRect();
    const i = Math.round((e.clientX - rect.left - padL) / (W - padL - padR) * (points.length - 1));
    if (i < 0 || i >= points.length) { tooltip.style.display = "none"; return; }
    const p = points[i], chg = (p.p / prevClose - 1) * 100;
    tooltip.style.display = "block"; tooltip.style.left = Math.min(e.clientX - rect.left + 12, W - 140) + "px"; tooltip.style.top = "8px";
    tooltip.innerHTML = `<b>${tlabel(p.t)}</b><br>${fmt(p.p)} <span class="${cls(chg)}">${sgn(chg.toFixed(2))}%</span>`;
  });
  canvas.onmouseleave = () => tooltip.style.display = "none";
}

/* ---------- pages ---------- */
/* The global tape lives OUTSIDE #view, in a fixed host, and is never re-created. Rendering it as
   part of a page's innerHTML meant every route render and every 60s poll built a fresh .gtrack —
   and a fresh element restarts the CSS marquee, so the scroll snapped back to zero. Now the node
   is built once and only its numbers are patched in place. Pages that want it call
   showGlobalStrip(gl); route() calls hideGlobalStrip() before dispatch so pages that don't want
   it simply never turn it back on. */
const GSTRIP_ORDER = ["BZ=F", "^GSPC", "^DJI", "^VIX", "GC=F", "BTC-USD", "ETH-USD", "PKR=X", "DX-Y.NYB"];

function globalStripData(gl) {
  const inst = gl?.instruments || {};
  // Fixed TWO decimals, always. fmt() has no minimum, so 53,885.1 -> 53,885 shrinks the cell and
  // a digit-count change resizes .gtrack mid-marquee (it translates -50% of track width). A
  // constant decimal count plus the CSS min-width floor makes the track width immutable.
  const p2 = n => Number(n).toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return GSTRIP_ORDER.filter(s => inst[s]).map(s => {
    const v = inst[s];
    return { k: s, label: v.label, read: v.psx_read, price: p2(v.price), chg: sgn(v.chg_1d_pct) + "%", chgCls: cls(v.chg_1d_pct) };
  });
}

/* Hiding the host with display:none took it out of the layout, which restarts the CSS marquee —
   the same defect the rebuild guard below exists to avoid, just triggered by navigation instead.
   A body-level flag drives `visibility:hidden` in CSS: the node keeps its box and its animation
   keeps running, so returning to a page that wants the tape resumes mid-scroll. */
function hideGlobalStrip() { document.body.dataset.strip = "off"; }

function showGlobalStrip(gl) {
  const host = $("gstripHost");
  if (!host) return;
  const data = globalStripData(gl);
  if (!data.length) { document.body.dataset.strip = "off"; return; }

  // Rebuild only when an instrument appears that the track doesn't have (each run is duplicated
  // for a seamless loop). An instrument merely MISSING this cycle must not rebuild — that restarts
  // the marquee; its cells just keep last cycle's numbers until it returns.
  let track = host.querySelector(".gtrack");
  const want = data.map(d => d.k).join(",");
  const have = (host.dataset.keys || "").split(",");
  if (!track || data.some(d => !have.includes(d.k))) {
    const items = data.map(d =>
      `<div class="gitem" data-gk="${esc(d.k)}" title="${esc(d.read)}"><span>${esc(d.label)}</span>
      <b class="num"></b><i class="num"></i></div>`).join("");
    host.innerHTML = `<div class="gstrip clickable" onclick="navigate('/macro')"><div class="gtrack">${items}${items}</div></div>`;
    host.dataset.keys = want;
    track = host.querySelector(".gtrack");
  }
  delete document.body.dataset.strip;

  data.forEach(d => {
    host.querySelectorAll(`.gitem[data-gk="${d.k}"]`).forEach(el => {
      const b = el.querySelector("b"), i = el.querySelector("i");
      if (b) { flashDelta(b, b.textContent, d.price); setText(b, d.price); }
      if (i) { setText(i, d.chg); setClass(i, "num " + d.chgCls); }
      if (el.title !== (d.read || "")) el.title = d.read || "";
    });
  });
}

/* The tape is desk chrome, shown on every page, so it cannot depend on a page renderer fetching
   global.json. route() calls this on every dispatch; the cached read is free after the first one,
   and the 60s poll keeps the numbers fresh from there. */
function primeGlobalStrip() {
  j("global.json").then(gl => { if (gl) showGlobalStrip(gl); }).catch(() => {});
}

/* PSX's own index board. ALLSHR / KMIALLSHR matter because the desk's universe runs well past the
   KSE100 — benchmarking a mid-cap against an index it isn't in is a quiet way to be wrong. */
const IDX_LABEL = {
  KSE100: ["KSE100", "the headline 100"], ALLSHR: ["KSE All Share", "every listed company"],
  KMI30: ["KMI30", "Shariah, top 30"], KMIALLSHR: ["KMI All Share", "every Shariah-compliant name"],
  KSE30: ["KSE30", "free-float top 30"], BKTI: ["Banks", "sector index"], OGTI: ["Oil & Gas", "sector index"],
};
const INDEX_ROUNDING_TOLERANCE = 0.011;
function readIndexDailyChange(idx, key) {
  const entry = idx?.daily_change?.[key];
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const source = typeof idx?.source_at === "string" && idx.source_at.trim() ? idx.source_at : "";
  const session = typeof idx?.live_session_date === "string" && idx.live_session_date.trim() ? idx.live_session_date : "";
  const sourceDate = /^(\d{4}-\d{2}-\d{2})/.exec(source)?.[1] || "";
  if (!entry || typeof entry !== "object" || !source || !session || sourceDate !== session) return null;
  if (!["current", "change", "percent", "derived_previous_close"].every(field => finite(entry[field]))) return null;
  if (entry.current <= 0 || entry.derived_previous_close <= 0) return null;
  if (entry.source_at !== source || entry.session_date !== session) return null;
  const live = idx?.live?.[key];
  if (!finite(live) || live <= 0 || Math.abs(entry.current - live) > INDEX_ROUNDING_TOLERANCE) return null;
  if (Math.abs(entry.derived_previous_close - (entry.current - entry.change)) > INDEX_ROUNDING_TOLERANCE) return null;
  if (Math.abs(entry.percent - (entry.change / entry.derived_previous_close * 100)) > INDEX_ROUNDING_TOLERANCE) return null;
  return entry;
}
window.HennethIndexDailyChange = readIndexDailyChange;
function indexBoard(idx) {
  const live = idx?.live || {};
  const days = Object.keys(idx?.history || {}).sort();
  // One compact row. The descriptive line lives in the tooltip, not in the cell — it was making
  // the board three times taller than the numbers needed, and Pixelify (a numerals face) was
  // rendering prose like "first session" with broken ligatures.
  const cells = Object.keys(IDX_LABEL).filter(k => typeof live[k] === "number" && Number.isFinite(live[k]) && live[k] > 0).map(k => {
    const [label, sub] = IDX_LABEL[k];
    const daily = readIndexDailyChange(idx, k);
    const chg = daily ? daily.percent : null;
    return `<div class="idx-cell" title="${esc(label)} — ${esc(sub)}">
      <span class="idx-k">${esc(label)}</span>
      <b class="num">${fmt(live[k], 0)}</b>
      ${chg != null ? `<i class="num ${cls(chg)}">${sgn(+chg.toFixed(2))}%</i>`
      : `<i class="idx-new" title="PSX daily change is unavailable or inconsistent in this snapshot.">—</i>`}
    </div>`;
  }).join("");
  return cells ? `<div class="seg"><h2>PSX indices</h2><div class="ln"></div><span class="pill">${days.length} session${days.length === 1 ? "" : "s"} kept</span></div>
    <div class="idx-board">${cells}</div>
    <p class="sub idx-foot">Daily moves use PSX's published board change; stored history remains append-only. <b>All Share</b> is the honest benchmark for names outside the KSE100.</p>` : "";
}

async function pageBoard() {
  const [quant, pred, dash, news, pos, smap, trig, live, fvAll, fndAll, fsAll, idxAll] = await Promise.all([
    j("quant.json"), j("predictability.json"), j("dashboard.json"), j("newslog.json"),
    j("positions.json"), j("strategy_map.json"), j("live_triggers.json"), j("live.json"),
    j("fairvalue.json"), j("fundamentals.json"), j("fundamental_scores.json"), j("indices.json")]);
  const q = quant?.tickers || {};
  const lv = live?.tickers || {};

  const sigs = dash?.signals || [];
  const sigBadge = s => s.audit === "PASS" ? '<span class="tag badge-ok up">audited ✓</span>'
    : '<span class="tag" title="Triggering now, proven on this stock\'s own history. Backtest-proven, not auditor-verified. Research, not advice.">backtest-proven</span>';
  // PUBLICATION_RESTRUCTURE_V2 §4a/§4b — the card shows only what a research publication may:
  // strategy, its backtest track record, the reworded thesis, and a route into the reader's own
  // level tool. No entry/stop/target/risk-per-share on a named security (SECP Reg 2(ha)); the
  // reader derives their own at /tools/strategy-level-calculator/ (Reg 2(h) general commentary).
  const sigHtml = sigs.length ? sigs.map(s => {
    const bt = s.backtest || {};
    const hit = bt.hit_rate != null ? Math.round(bt.hit_rate * 100) + "%" : "—";
    const nx = bt.net_expectancy_pct;
    return `
    <div class="card clickable" onclick="navigate('/ticker/${esc(s.ticker)}')">
      <div class="tk-head"><span class="sym">${esc(s.ticker)}</span><span class="tag">${esc(s.template || "")}</span>
      ${sigBadge(s)}${s.confidence ? `<span class="pill ${s.confidence === "high" ? "ok" : ""}">${esc(s.confidence)}</span>` : ""}</div>
      <div class="statgrid num">
        <div class="stat"><span>hit rate</span><b>${hit}</b></div>
        <div class="stat"><span>sample</span><b>${bt.n != null ? "n" + bt.n : "—"}</b></div>
        <div class="stat"><span>net/trade</span><b class="${nx > 0 ? "up" : nx < 0 ? "dn" : ""}">${nx != null ? (nx > 0 ? "+" : "") + nx + "%" : "—"}</b></div>
        <div class="stat"><span>hold</span><b>${s.hold_sessions != null ? s.hold_sessions + "d" : "—"}</b></div>
      </div><div class="sub" style="margin-top:8px">${esc(s.thesis || "")}</div>
      <a class="tool-cta" href="/tools/strategy-level-calculator/" onclick="event.stopPropagation()">Work out your own levels →</a></div>`;
  }).join("")
    : `<div class="card"><div class="empty">No setups triggering right now — the desk only flags a stock when a strategy proven on its own history fires. Patience is the edge.</div></div>`;

  const tg = trig?.triggers || [];
  const trigHtml = tg.length ? `<div class="card"><h2>Live triggers</h2><div class="sub">proven patterns firing now · unvetted</div>
    <table><thead><tr><th>Ticker</th><th>Strategy</th><th class="r">Price</th><th class="r">Hist</th><th class="r">When</th></tr></thead><tbody>${
      tg.map(t => `<tr class="clickable" onclick="navigate('/ticker/${esc(t.ticker)}')"><td><b>${esc(t.ticker)}</b></td><td>${esc(t.name)}</td>
      <td class="r num">${t.price}</td><td class="r num">${Math.round(t.backtest.hit_rate * 100)}%·n${t.backtest.n}</td><td class="r num">${t.ts}</td></tr>`).join("")}</tbody></table></div>` : "";

  const heat = Object.entries(q).sort((a, b) => b[1].ret_1d - a[1].ret_1d).map(([s, v]) => {
    const a = Math.min(Math.abs(v.ret_1d) / 5, 1) * 0.5;
    const col = v.ret_1d > 0.05 ? "var(--up)" : v.ret_1d < -0.05 ? "var(--dn)" : null;
    const bg = col ? `style="background:color-mix(in srgb, ${col} ${Math.round(a * 100)}%, transparent)"` : "";
    return `<div class="cell clickable" ${bg} onclick="navigate('/ticker/${s}')" title="RSI ${v.rsi14} · 20d ${sgn(v.ret_20d)}%">
      <b>${s}</b><span class="px num">${fmt(lv[s]?.current ?? v.close)}</span><span class="num ${cls(v.ret_1d)}">${sgn(v.ret_1d)}%</span></div>`;
  }).join("");

  const sm = Object.entries(smap?.tickers || {}).flatMap(([s, l]) => l.map(t => ({ s, ...t })))
    .sort((a, b) => b.net_expectancy_pct - a.net_expectancy_pct).slice(0, 12);
  const pt = Object.entries(pred?.tickers || {}).sort((a, b) => b[1].score - a[1].score).slice(0, 10);
  const nn = (news || []).slice(-10).reverse();
  const aw = dash?.agent_wire || [];
  const op = pos?.open || [];

  const posCard = `<div class="card"><h2>Positions</h2><div class="sub"></div>${op.length ? `<table><thead><tr><th>Ticker</th><th class="r">Entry</th><th class="r">Last</th><th class="r">P/L</th><th>Status</th></tr></thead><tbody>${
      op.map(p => `<tr class="clickable" onclick="navigate('/ticker/${esc(p.ticker)}')"><td><b>${esc(p.ticker)}</b></td><td class="r num">${p.entry}</td><td class="r num">${p.last_price ?? "—"}</td><td class="r num ${cls(p.unrealized_pct || 0)}">${p.unrealized_pct != null ? sgn(p.unrealized_pct) + "%" : "—"}</td><td>${esc(p.status || "HOLD")}</td></tr>`).join("")}</tbody></table>` : '<div class="empty">Flat — no open positions.</div>'}</div>`;
  const provenCard = `<div class="card"><h2>Proven strategies</h2><div class="sub">cleared backtest + out-of-sample bars · click through</div>
      <table><thead><tr><th>Ticker</th><th>Strategy</th><th class="r">Hit</th><th class="r">Net</th><th class="r">n</th></tr></thead><tbody>${
      sm.map(t => `<tr class="clickable" onclick="navigate('/ticker/${t.s}')"><td><b>${t.s}</b></td><td><span class="tag">${esc(t.name)}</span></td><td class="r num">${Math.round(t.hit_rate * 100)}%</td><td class="r num up">${sgn(t.net_expectancy_pct)}%</td><td class="r num">${t.n}</td></tr>`).join("")}</tbody></table></div>`;
  // The universe is the longest block on the board and the least urgent — at two cells per row on
  // a phone it buried predictability and proven strategies under ~60 rows of scrolling, and even on
  // a desktop grid it runs well past the fold. Cap it; wireTiles() sizes the cap to the viewport.
  const universeCard = `<div class="card"><h2>Universe</h2><div class="sub">day move · click any name</div>
    <div class="tilebox"><div class="tilebody"><div class="heat">${heat}</div></div></div></div>`;
  const predCard = `<div class="card"><h2>Predictability</h2><div class="sub"></div><table><thead><tr><th>Ticker</th><th class="r">Score</th><th class="r">RSI</th><th class="r">20d</th></tr></thead><tbody>${
      pt.map(([s, v]) => `<tr class="clickable" onclick="navigate('/ticker/${s}')"><td><b>${s}</b></td><td class="r num">${v.score}</td><td class="r num">${q[s]?.rsi14 ?? "—"}</td><td class="r num ${cls(q[s]?.ret_20d || 0)}">${q[s] ? sgn(q[s].ret_20d) + "%" : "—"}</td></tr>`).join("")}</tbody></table></div>`;
  const newsCard = `<div class="card"><h2>News wire</h2><div class="sub"><a href="/news">full wire →</a></div><div class="wire">${
      nn.length ? nn.map(n => `<p><span class="tag">${n.impact ?? ""}</span> <span class="t">${esc((n.ts || "").slice(5, 16))}</span><b>${(n.tickers || []).join(", ")}</b> ${esc(n.headline || n.summary || "")}</p>`).join("") : '<div class="empty">Wire silent.</div>'}</div></div>`;
  const agentCard = `<div class="card"><h2>Agent wire</h2><div class="sub">this cycle</div><div class="wire">${
      aw.length ? aw.map(a => `<p><b style="color:var(--accent)">${esc(a.agent)}</b> ${esc(a.summary)}</p>`).join("") : '<div class="empty">No cycle run yet.</div>'}</div></div>`;

  // the daily opportunity scanner — six ranked lists from the scored data, rebuilt every cycle
  const scanCats = scannerLists(q, fvAll?.tickers || {}, fndAll?.tickers || {}, pred?.tickers || {}, fsAll?.tickers || {});
  $("view").innerHTML = `${indexBoard(idxAll)}
  <div class="grid-board">
    <div class="cards">${sigHtml}${trigHtml}${posCard}</div>
    <div class="cards">${universeCard}${predCard}${provenCard}</div>
    <div class="cards">${newsCard}${agentCard}</div>
  </div>
  <div class="seg"><h2>Today's scanner</h2><div class="ln"></div><span class="pill">rebuilt every cycle</span></div>
  ${scannerHtml(scanCats)}`;
}

// pageValue lives in its own page file (redesign 2026-09).

/* What actually moves each sector — measured, not assumed. Rendered from sector_macro.json, which
   regresses 19 years of sector returns on the global tape with the same permutation machinery the
   astro test used. That symmetry IS the point: the same bar that found nothing in the sky finds
   oil in the E&P names. */
const FACTOR_LABEL = {
  oil: "oil (WTI)", gold: "gold", usdpkr: "USD/PKR", sp500: "S&P 500",
  em_equity: "EM equity flows", us10y: "US 10y yield", dollar: "dollar index",
};
const FACTOR_PLAIN = {
  oil: "crude", gold: "gold", usdpkr: "a weaker rupee", sp500: "Wall Street's last close",
  em_equity: "money moving into emerging markets", us10y: "the US cost of money",
  dollar: "a stronger dollar",
};
function sectorDriverLine(sm, sector) {
  const rec = sm?.by_sector?.[sector];
  if (!rec) return "";
  const demo = (rec.drivers || []).filter(d => d.demonstrated);
  if (!demo.length) {
    return `<span class="sub">No global factor has a demonstrated effect on ${esc(sector)} — over 19 years its days have been made locally, not on the world tape.</span>`;
  }
  const d = demo[0];
  const dir = d.corr > 0 ? "rises with" : "falls when";
  return `<span class="sub"><b>${esc(sector)}</b> ${dir} <b>${esc(FACTOR_PLAIN[d.factor] || d.factor)}</b>${d.corr > 0 ? "" : " rises"}${demo.length > 1 ? `, and also tracks ${demo.slice(1, 3).map(x => esc(FACTOR_PLAIN[x.factor] || x.factor)).join(" and ")}` : ""} — measured over 19 years, correction-survived. Even so, the whole global tape explains only <b>${rec.joint_r2_pct ?? "—"}%</b> of this sector's daily moves.</span>`;
}

async function pageMacro() {
  const [gl, macro, geo, sm] = await Promise.all([
    j("global.json"), j("macro.json"), j("georisk.json"), j("sector_macro.json")]);
  const inst = gl?.instruments || {};
  const groups = {
    energy: "Energy — oil drives Pakistan's import bill, PKR & inflation",
    risk: "Global risk appetite — frontier flows follow",
    safe_haven: "Safe haven",
    crypto: "Crypto — global liquidity / retail risk barometer",
    fx: "Currency — the biggest macro lever for PSX",
  };
  // the world tape as tiles, not tables: a price is read at a glance, a table row is read line by
  // line. Each tile is one instrument — level, both changes, and why a PSX reader should care.
  const GROUP_WHY = {
    fx: "the biggest macro lever",
    energy: "the import bill, PKR and inflation",
    risk: "frontier flows follow",
    crypto: "global liquidity / retail risk",
    safe_haven: "the hedge bid",
  };
  const gTile = ([, v]) => `<div class="gtile">
    <span class="gt-k">${esc(v.label)}${v.stale ? ' <span class="tag">stale</span>' : ""}</span>
    <b class="gt-p">${fmt(v.price)}</b>
    <span class="gt-ch"><em class="${cls(v.chg_1d_pct)}">${sgn(v.chg_1d_pct)}%<i>1d</i></em><em class="${cls(v.chg_1mo_pct)}">${sgn(v.chg_1mo_pct)}%<i>1mo</i></em></span>
    <span class="gt-why" title="${esc(v.psx_read)}">${esc(v.psx_read)}</span></div>`;
  const card = (gk, title) => {
    const rows = Object.entries(inst).filter(([, v]) => v.group === gk);
    if (!rows.length) return "";
    return `<div class="gband">
      <div class="gband-h"><b>${esc(String(title).split(" — ")[0])}</b><i>${esc(GROUP_WHY[gk] || String(title).split(" — ")[1] || "")}</i></div>
      <div class="gtiles">${rows.map(gTile).join("")}</div></div>`;
  };

  const m = macro || {};
  const dom = m.domestic || {};
  const drivers = m.drivers || [];
  const macroCard = `<div class="card"><h2>Pakistan macro</h2>
    <div class="sub">regime <b>${esc(t(m.regime || "—").toUpperCase())}</b> · ${esc(tp(m, "global_read"))} · updated ${esc(m.updated || "—")} ${m.updated ? "" : "(run macro-agent to populate)"}</div>
    ${(() => {
      const facts = [
        ["SBP policy rate", m.sbp_rate],
        ["CPI YoY", m.cpi_yoy],
        ["FX reserves", m.reserves_usd_bn ? "$" + m.reserves_usd_bn + "bn" : null],
        ["6m T-bill", dom.tbill_6m],
        ["10y PIB", dom.pib_10y],
        ["Remittances", dom.remittances],
        ["USD/PKR", m.pkr_usd],
      ];
      const have = facts.filter(([, v]) => v != null && v !== "");
      const missing = facts.filter(([, v]) => v == null || v === "").map(([k]) => k);
      return `<div class="facts">${have.map(([k, v]) => `<div class="fact"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join("")}</div>
      ${missing.length ? `<p class="sub" style="margin-top:8px;font-size:10.5px">Pending this cycle: ${missing.join(", ")} — the macro-agent fills these from SBP/PBS primary sources on the next full run.</p>` : ""}`;
    })()}
    ${dom.debt_note ? `<p class="sub" style="margin-top:10px"><b>Debt/borrowing:</b> ${esc(tp(dom, "debt_note"))}</p>` : ""}
    ${drivers.length ? `<div class="sub" style="margin-top:10px"><b>Drivers:</b><ul style="margin:6px 0 0 16px">${tpArr(m, "drivers").map(d => `<li>${esc(d)}</li>`).join("")}</ul></div>` : ""}
    ${(m.next_events || []).length ? `<p class="sub" style="margin-top:8px"><b>Next:</b> ${m.next_events.map(e => `${esc(e.date)} ${esc(tp(e, "event"))}`).join(" · ")}</p>` : ""}
    ${(m.sector_tilt) ? `<p class="sub" style="margin-top:8px"><b class="up">Favored:</b> ${(tpArr(m.sector_tilt, "favored")).join(", ") || "—"} · <b class="dn">Avoid:</b> ${(tpArr(m.sector_tilt, "avoid")).join(", ") || "—"}</p>` : ""}</div>`;

  // geo-risk radar (worldmonitor-style, from free signals)
  const geoCard = geo ? (() => {
    const band = geo.band, col = band === "elevated" ? "var(--dn)" : band === "calm" ? "var(--up)" : "var(--accent)";
    const bar = s => `<div style="height:6px;border-radius:0;background:var(--line2);overflow:hidden"><div style="height:100%;width:${s}%;background:${s >= 65 ? "var(--dn)" : s <= 40 ? "var(--up)" : "var(--accent)"};transform-origin:left"></div></div>`;
    return `<div class="card"><div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:6px">
      <h2>Geopolitical & risk radar</h2>
      <span class="pill" style="background:color-mix(in srgb,${col} 15%,transparent);color:${col}">${geo.score}/100 · ${esc(band)}</span></div>
      <div class="sub" style="color:var(--ink2);margin-bottom:14px">${esc(geo.read)} <span style="opacity:.7">· ${esc(geo.source)}</span></div>
      <table><tbody>${geo.factors.map(f => `<tr>
        <td style="width:150px"><b>${esc(f.factor)}</b></td>
        <td class="num" style="width:150px">${esc(f.value)}</td>
        <td style="width:90px" class="r num">${f.stress}</td>
        <td style="min-width:110px">${bar(f.stress)}</td>
        <td class="sub" style="color:var(--ink2)">${esc(f.read)}</td></tr>`).join("")}</tbody></table>
      ${geo.sector_pressure?.length ? `<p class="sub" style="margin-top:12px"><b>Sector read-through:</b> ${geo.sector_pressure.map(esc).join(" · ")}</p>` : ""}
      ${geo.upgrade_note ? `<p class="sub" style="margin-top:8px;opacity:.7">${esc(geo.upgrade_note)}</p>` : ""}</div>`;
  })() : "";

  // glance row: the regime and the three prices that actually move PSX, before any prose
  const sTile = (label, val, sub, k) => `<div class="sumtile"><span class="sk">${label}</span><b class="${k || ""}">${val}</b>${sub ? `<i>${sub}</i>` : ""}</div>`;
  const iTile = (label, code, why) => { const v = inst[code];
    return sTile(label, v ? fmt(v.price) : "—", v ? `${sgn(v.chg_1d_pct)}% today · ${why}` : why, v ? cls(v.chg_1d_pct) : ""); };
  // the feed writes "risk-off"; don't assume a separator — strip everything but letters
  const regime = (m.regime || "").toLowerCase().replace(/[^a-z]/g, "");
  const glanceRow = `<div class="sumstrip s4">
    ${sTile("Macro regime", t(m.regime || "—").toUpperCase(), m.updated ? `desk read · ${esc(m.updated)}` : "run macro-agent to populate", regime === "riskon" ? "up" : regime === "riskoff" ? "dn" : "")}
    ${iTile("USD/PKR", "PKR=X", "the biggest lever")}
    ${iTile("Brent crude", "BZ=F", "the import bill")}
    ${geo ? sTile("Geo risk", `${geo.score}/100`, esc(geo.band || ""), geo.band === "elevated" ? "dn" : geo.band === "calm" ? "up" : "") : iTile("Global risk", "^GSPC", "frontier flows follow")}
  </div>`;

  // ---- what ACTUALLY moves each sector, measured over 19 years
  const smCard = (() => {
    if (!sm?.by_sector) return "";
    const h = sm.headline || {};
    const rows = Object.entries(sm.by_sector)
      .sort((a, b) => (b[1].joint_r2_pct ?? 0) - (a[1].joint_r2_pct ?? 0))
      .map(([sec, rec]) => {
        const demo = (rec.drivers || []).filter(d => d.demonstrated);
        const chips = demo.length
          ? demo.slice(0, 3).map(d => `<span class="mf-chip ${d.corr > 0 ? "up" : "dn"}" title="correlation ${d.corr}, p=${d.p_value}">${esc(FACTOR_LABEL[d.factor] || d.factor)} ${d.corr > 0 ? "↑" : "↓"}</span>`).join("")
          : `<span class="sub" style="opacity:.7">nothing beat chance</span>`;
        return `<tr><td><b>${esc(sec)}</b></td><td>${chips}</td>
          <td class="r num">${rec.joint_r2_pct != null ? rec.joint_r2_pct + "%" : "—"}</td></tr>`;
      }).join("");
    return `<div class="seg"><h2>What actually moves each sector</h2><div class="ln"></div><span class="pill ok">${h.survivors_bonferroni} of ${h.hypotheses_tested} measured</span></div>
    <div class="card" style="padding:0"><table><thead><tr><th>Sector</th><th>Demonstrated drivers</th><th class="r">Global tape explains</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="sub" style="margin-top:8px">Nineteen years of daily returns against the global tape — oil, gold, USD/PKR, the S&amp;P, EM flows, the US 10y — each lagged a day, since those markets close after Karachi. The same test found nothing in <a href="/astro" style="color:var(--accent)">astrology</a>. Here it finds <b>${h.survivors_bonferroni}</b>. That contrast is the point.</p>
    <p class="sub" style="margin-top:6px"><b>Read the last column first.</b> Even at its strongest, the world tape explains a few percent of a day's move — PSX is made at home. A driver says what <i>has tended</i> to move a sector, never what will.</p>`;
  })();

  $("view").innerHTML = `
    <div class="seg" style="margin-top:4px"><h2>What moves PSX</h2><div class="ln"></div></div>
    ${glanceRow}
    <p class="sub" style="margin-bottom:14px">Global markets refresh every cycle (Yahoo Finance); Pakistan numbers are verified from primary sources. Each tile says why that price matters to Karachi.</p>
    <div class="gwrap">
      ${card("fx", groups.fx)}
      ${card("energy", groups.energy)}
      ${card("risk", groups.risk)}
      ${card("crypto", groups.crypto)}
      ${card("safe_haven", groups.safe_haven)}
    </div>
    ${smCard}
    ${geoCard}
    ${macroCard}`;
}

async function pageToday() {
  const [dr, quant, live, uni] = await Promise.all([j("daily_read.json"), j("quant.json"), j("live.json"), j("universe.json")]);
  if (!dr) { $("view").innerHTML = `<div class="seg" style="margin-top:4px"><h2>Daily read</h2><div class="ln"></div></div><div class="card"><div class="empty">The daily read is written by the market-analyst agent in the pre-market cycle. Run a full cycle to generate today's note.</div></div>`; return; }
  const toneClass = { constructive: "ok", defensive: "bad", cautious: "bad" }[dr.tone] || "";
  const stanceTag = s => `<span class="pill ${s === "favoured" ? "ok" : s === "avoid" ? "bad" : ""}">${esc(s)}</span>`;
  const q = quant?.tickers || {}, lv = live?.tickers || {};

  // ---- personal layer: your watchlist surfaces first (same desk read for everyone) ----
  const wl = (typeof watchlist === "function" ? watchlist() : []).filter(s => q[s]);
  const myWatch = (me && wl.length) ? `
  <div class="seg" style="margin-top:4px"><h2>On your watchlist</h2><div class="ln"></div><span class="pill ok">${wl.length}</span></div>
  <div class="card" style="padding:0"><table class="wl-mini"><tbody>${wl.map(s => {
    const qq = q[s], px = lv[s]?.current ?? qq.close;
    return `<tr class="clickable" onclick="navigate('/ticker/${s}')"><td><b>${s}</b> <span class="sub">${esc((uni?.symbols?.[s]?.name || "").slice(0, 24))}</span></td><td class="r num">${fmt(px)}</td><td class="r num ${cls(qq.ret_1d)}">${sgn(qq.ret_1d)}%</td></tr>`;
  }).join("")}</tbody></table></div>` : "";

  // radar names: the ones you watch float to the top, badged
  const iw = typeof isWatched === "function" ? isWatched : () => false;
  const radar = (dr.watchlist || []).slice().sort((a, b) => (iw(b.ticker) ? 1 : 0) - (iw(a.ticker) ? 1 : 0));

  // glance row: the day in four hard items, before the read
  const sTile = (label, val, sub, k) => `<div class="sumtile"><span class="sk">${label}</span><b class="${k || ""}">${val}</b>${sub ? `<i>${sub}</i>` : ""}</div>`;
  const fav = (dr.sectors || []).filter(s => s.stance === "favoured"), avoid = (dr.sectors || []).filter(s => s.stance === "avoid");
  const nextCat = (dr.catalysts || [])[0];
  const glanceRow = `<div class="sumstrip s4">
    ${sTile("The desk's tone", t(dr.tone || "—").toUpperCase(), esc(dr.date || ""), toneClass === "ok" ? "up" : toneClass === "bad" ? "dn" : "")}
    ${sTile("Favoured", fav.length ? esc(fav.map(s => s.name).slice(0, 2).join(", ")) : "none", fav.length > 2 ? `+${fav.length - 2} more sectors` : "sectors", fav.length ? "up" : "")}
    ${sTile("Avoiding", avoid.length ? esc(avoid.map(s => s.name).slice(0, 2).join(", ")) : "none", avoid.length > 2 ? `+${avoid.length - 2} more sectors` : "sectors", avoid.length ? "dn" : "")}
    ${sTile("Next catalyst", nextCat ? esc(nextCat.date) : "—", nextCat ? esc(String(nextCat.event).slice(0, 34)) : "none dated", "")}
  </div>`;

  // ---- the daily lesson: one card, 60 seconds, different every day ----
  // For a signed-in learner it is the next unfinished lesson (their real place in the journey).
  // Otherwise it is a date-seeded pick, so everyone sees the same lesson on a given day and a
  // different one tomorrow — deterministic, no state, no repeats until the syllabus is exhausted.
  let dailyCard = "";
  try {
    const cur = await j("curriculum.json");
    const all = (cur?.levels || []).flatMap(v => v.lessons.map(l => ({ lv: v.id, l })));
    if (all.length) {
      const doneKeys = learnProgress();
      const next = all.find(x => !doneKeys[x.lv + "/" + x.l.id]);
      const epochDay = Math.floor(Date.now() / 86400000);
      const pick = (me && next) ? next : all[epochDay % all.length];
      const isNext = !!(me && next);
      dailyCard = `<div class="card daily-lesson" onclick="openLesson('${esc(pick.lv)}','${esc(pick.l.id)}')">
        <div class="dl-left"><div class="ark">${isNext ? "your next lesson" : "today's lesson"} · ${pick.l.mins} min</div>
          <b>${esc(pick.l.title)}</b><span class="sub">${esc(pick.l.why)}</span></div>
        <span class="dl-go">${isNext ? "Continue" : "Learn it"} →</span></div>`;
    }
  } catch { /* the daily lesson is a bonus — never break Today over it */ }

  // the astro hook, surfaced where visitors actually land. Only for those without a chart yet —
  // once cast, it's replaced by their own reading in the sidebar, so this never nags.
  const astroTease = natalChart() ? "" : `
  <div class="card mc-tease" onclick="navigate('/cast')">
    <div class="mc-tease-glyphs">${["Sun", "Moon", "Jupiter", "Saturn"].map(b => pixelGlyph(b, 22)).join("")}</div>
    <div class="mc-tease-txt">
      <b>Read the whole exchange against your birth chart</b>
      <span class="sub">Vedic astrology has always matched two charts. The desk turns that on the market — cast yours free, in your browser, in about a minute.</span>
    </div>
    <span class="mc-tease-go">Cast my chart →</span>
  </div>`;

  const sinceBanner = await sinceLastVisit(q, lv);

  // ---- desk setup: the same four-question onboarding the terminal runs, offered until activation ----
  const onboardPrompt = (me && myProfile && !myProfile.activated_at) ? onboardCardHtml() : "";
  if (onboardPrompt && !_onboardShownTracked) { _onboardShownTracked = true; track("onboard_prompt_shown"); }

  $("view").innerHTML = `
  ${sinceBanner}
  ${onboardPrompt}
  ${glanceRow}
  ${dailyCard}
  ${astroTease}
  ${myWatch}
  <div class="card">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px"><span class="pill ${toneClass}">${esc(t(dr.tone || "").toUpperCase())}</span><span class="sub">${esc(dr.date || "")}</span></div>
    <h2 style="font-size:22px;line-height:1.3;margin-bottom:12px">${esc(tp(dr, "headline"))}</h2>
    <p style="font-size:14.5px;line-height:1.65;color:var(--ink2)">${esc(tp(dr, "summary"))}</p>
  </div>
  <div class="two-col">
    <div class="card"><h2>Sectors to watch</h2><div class="sub"></div>
      <table><tbody>${(dr.sectors || []).map(s => `<tr><td><b>${esc(s.name)}</b></td><td>${stanceTag(s.stance)}</td><td class="sub" style="color:var(--ink2)">${esc(tp(s, "why"))}</td></tr>`).join("") || '<tr><td class="empty">—</td></tr>'}</tbody></table></div>
    <div class="card"><h2>Key risks</h2><div class="sub">what would spoil the read</div>
      <ul style="margin-top:6px;padding-left:18px;line-height:1.7">${tpArr(dr, "risks").map(r => `<li>${esc(r)}</li>`).join("") || "<li class='sub'>none flagged</li>"}</ul>
      ${(dr.catalysts || []).length ? `<div class="sub" style="margin-top:12px"><b>Catalysts:</b> ${dr.catalysts.map(c => `${esc(c.date)} ${esc(tp(c, "event"))}`).join(" · ")}</div>` : ""}</div>
  </div>
  <div class="seg"><h2>Names on the desk's radar</h2><div class="ln"></div></div>
  ${radar.length ? `<div class="card" style="padding:0"><table><thead><tr><th>Ticker</th><th>The desk's angle</th><th>Key risk</th></tr></thead><tbody>${
    radar.map(w => `<tr class="clickable" onclick="navigate('/ticker/${esc(w.ticker)}')">
      <td style="white-space:nowrap"><b>${esc(w.ticker)}</b>${iw(w.ticker) ? ' <span class="wbadge">★ yours</span>' : ""}</td>
      <td class="sub" style="color:var(--ink2)">${esc(tp(w, "angle"))}</td>
      <td class="sub"><b class="dn">Risk:</b> ${esc(tp(w, "risk"))}</td></tr>`).join("")}</tbody></table></div>`
      : '<div class="card"><div class="empty">Patient today — nothing stacks up strongly enough to flag.</div></div>'}
  <p class="sub" style="margin-top:14px">${esc(tDisclaimer(dr))}</p>`;
  showGlobalStrip(gl);
}

async function pageStrategies() {
  const [bt, smap, lib, uni] = await Promise.all([
    j("backtests.json"), j("strategy_map.json"), j("strategy_library.json"), j("universe.json")]);
  const tpls = bt?.templates || {};
  let rows;
  if (Object.keys(tpls).length) {
    // full roll-up from backtests: proven count + tested count + stocks
    rows = Object.entries(tpls).map(([id, per]) => {
      const all = Object.values(per);
      const elig = all.filter(t => t.eligible);
      const avgNet = elig.length ? elig.reduce((a, t) => a + t.net_expectancy_pct, 0) / elig.length : null;
      return { id, name: all[0]?.name || id, cat: all[0]?.category || "", tested: all.length,
        proven: elig.length, avgNet, provenOn: Object.entries(per).filter(([, t]) => t.eligible).map(([s]) => s) };
    });
  } else {
    // bundled/snapshot fallback: derive from strategy_map (per-ticker proven lists)
    const agg = {};
    Object.entries(smap?.tickers || {}).forEach(([sym, list]) => list.forEach(p => {
      const a = agg[p.id] || (agg[p.id] = { id: p.id, name: p.name, cat: p.category, nets: [], provenOn: [] });
      a.nets.push(p.net_expectancy_pct); a.provenOn.push(sym);
    }));
    rows = Object.values(agg).map(a => ({ id: a.id, name: a.name, cat: a.cat, tested: null,
      proven: a.provenOn.length, avgNet: a.nets.reduce((x, y) => x + y, 0) / a.nets.length, provenOn: a.provenOn }));
  }
  rows.sort((a, b) => b.proven - a.proven);
  const byCat = {};
  rows.forEach(r => (byCat[r.cat] = byCat[r.cat] || []).push(r));
  const descs = {};
  (lib?.strategies || []).forEach(s => { descs[s.id] = s; });

  const names = uni?.symbols || {};
  const nStrat = bt?.n_strategies || rows.length || 52;
  const provenPairs = Object.values(smap?.tickers || {}).reduce((a, l) => a + l.length, 0);
  const nCovered = Object.keys(smap?.tickers || {}).length;
  const sTile = (label, val, sub, k) => `<div class="sumtile"><span class="sk">${label}</span><b class="${k || ""}">${val}</b>${sub ? `<i>${sub}</i>` : ""}</div>`;

  // ---- your board: pick stocks, run the whole library across them ----
  // Nothing is revealed on adding — a stock sits "waiting for a run" until the library
  // actually runs on it. The work has to be seen to be worth anything.
  const board = stratBoard();
  const pending = board.filter(s => !stratRunOn(s));
  const anyRan = board.some(stratRunOn);
  const provenCount = s => (smap?.tickers?.[s] || []).length;
  const tiles = board.map(s => { const ranS = stratRunOn(s);
    return `<div class="sb-tile clickable" onclick="if(!event.target.closest('.sb-x'))navigate('/ticker/${esc(s)}')">
      <button class="sb-x" data-sbdel="${esc(s)}" title="Remove ${esc(s)} from the board" aria-label="remove ${esc(s)}">✕</button>
      <b>${esc(s)}</b><span class="sb-nm">${esc((names[s]?.name || "").slice(0, 24))}</span>
      <span class="pill ${ranS && provenCount(s) ? "ok" : ranS ? "" : "wait"}">${ranS ? provenCount(s) + " of " + nStrat + " proven" : "waiting for a run"}</span>
    </div>`; }).join("");
  const addTile = `<div class="sb-tile sb-add">
      <span class="sk">Add a stock</span>
      <input id="sb-tkr" class="ph-in combo" type="search" enterkeyhint="search" placeholder="e.g. FFC" autocomplete="off" onkeydown="if(event.key==='Enter'&&!document.querySelector('.combo-opt.on'))addBoardTicker()">
      <button class="note-save" onclick="addBoardTicker()">Add to board</button>
    </div>`;

  /* Publication frame (§4). These read the backtests already computed by backtest.py in the
     deterministic cycle — no user action starts a backtest, and the numbers are identical for
     every subscriber. The copy says "read", not "run", because "run" described work being done
     for this reader on request, which is not what happens. */
  const runBar = pending.length ? `<button class="run-desk run-strat" onclick="playBoardRun()">
    <span class="run-ico">▶</span>
    <span class="run-txt"><b>The strategy library on ${anyRan ? `your ${pending.length} new stock${pending.length > 1 ? "s" : ""}` : `your ${board.length} stock${board.length > 1 ? "s" : ""}`}</b><i>All ${nStrat} of the desk's strategies, backtested across ${pending.length === 1 ? "its" : "each stock's"} ~19-year history — costs included, out-of-sample checked — with every stock–strategy pair that survived, ranked.</i></span>
    <span class="run-meta">${bt?.updated ? `<span class="run-last">Library updated · ${esc(String(bt.updated).slice(0, 10))}</span>` : ""}<span class="run-go">Read ›</span></span>
  </button>` : board.length ? `<button class="run-desk run-strat ran" onclick="playBoardRun()">
    <span class="run-ico">▶</span>
    <span class="run-txt"><b>The strategy library on your ${board.length} stock${board.length > 1 ? "s" : ""}</b><i>All ${nStrat} strategies across every stock on your board, re-ranked by what survives. Worth revisiting as the library and the price history move on.</i></span>
    <span class="run-meta">${bt?.updated ? `<span class="run-last">Library updated · ${esc(String(bt.updated).slice(0, 10))}</span>` : ""}<span class="run-go">Replay ›</span></span>
  </button>` : "";

  // ---- results: per board stock. A stock shows NOTHING until the library has actually run on it. ----
  const results = !board.length ? "" : board.map(s => {
    const list = smap?.tickers?.[s] || [];
    const head = `<div class="sb-res-head clickable" onclick="navigate('/ticker/${esc(s)}')"><b>${esc(s)}</b><span class="sub">${esc((names[s]?.name || "").slice(0, 30))}</span><span class="pill ${stratRunOn(s) ? (list.length ? "ok" : "") : "wait"}">${stratRunOn(s) ? list.length + " proven" : "not run yet"}</span></div>`;
    if (!stratRunOn(s)) return `<div class="card" style="padding:0">${head}
      <div class="empty" style="padding:14px 17px">The library's results for <b>${esc(s)}</b> aren't open yet — hit <b>Read ›</b> above for all ${nStrat} strategies backtested across ${esc(s)}'s own ~19 years of price history, and what actually held up.</div></div>`;
    return `<div class="card" style="padding:0">${head}
      ${list.length ? `<table><thead><tr><th>Strategy</th><th class="r">Win rate</th><th class="r">Avg net/trade</th><th class="r">Trades</th><th class="r">Out-of-sample</th></tr></thead><tbody>${
        list.map(t => `<tr><td><b>${esc(t.name)}</b> <span class="tag">${esc((t.category || "").replace(/_/g, " "))}</span></td>
          <td class="r num">${Math.round(t.hit_rate * 100)}%</td><td class="r num up">${sgn(t.net_expectancy_pct)}%</td>
          <td class="r num">${t.n}</td><td class="r num">${t.oos_hit != null ? Math.round(t.oos_hit * 100) + "% · n" + t.oos_n : "—"}</td></tr>`).join("")}</tbody></table>`
        : `<div class="empty" style="padding:14px 17px">No strategy cleared the bar on ${esc(s)} — none held win rate ≥55%, positive expectancy after costs, AND out-of-sample. The desk wouldn't signal it. That's a finding, not a gap.</div>`}</div>`;
  }).join("");

  // ---- the dictionary: every strategy the desk runs, in plain English ----
  const dict = `<details class="dict"><summary><b>What's in the library</b><span class="sub">every strategy the desk runs, and how each one works</span><span class="dict-arrow">▾</span></summary>
    ${Object.entries(byCat).map(([cat, list]) => `<div class="dict-cat">${esc((cat || "other").replace(/_/g, " "))}</div>
      ${list.map(r => { const d = descs[r.id] || {};
        return `<div class="dict-row"><div><b>${esc(r.name)}</b>${d.target_pct != null ? `<span class="dict-meta">target +${d.target_pct}% · stop −${d.stop_pct}% · max ${d.hold} sessions</span>` : ""}</div>
        <p>${esc(d.description || "")}</p>
        <span class="dict-proven ${r.proven ? "" : "none"}">${r.proven ? `proven on ${r.proven} stock${r.proven === 1 ? "" : "s"}` : "hasn't cleared the bar anywhere yet"}</span></div>`; }).join("")}`).join("")}
  </details>`;

  // ---- request a strategy (signed-in; stored in the desk's request queue) ----
  const reqForm = `<div class="seg"><h2>Request a strategy</h2><div class="ln"></div><span class="pill">the desk tests it</span></div>
  <div class="card">
    <p class="sub" style="margin-bottom:12px">Trade by a rule that isn't in the library? Explain it below. The desk codes it, backtests it on ~19 years, and if it clears the bar it joins the library.</p>
    ${me ? `<div class="rq-form">
      <div class="ph-row"><input id="rq-title" class="ph-in" inputmode="text" enterkeyhint="next" aria-label="Strategy name" placeholder="Name it (e.g. Monday gap fade)" maxlength="80">
      <input id="rq-tkr" class="ph-in combo" type="search" enterkeyhint="search" aria-label="Ticker (optional)" style="flex:0 1 150px" placeholder="Ticker (optional)" autocomplete="off"></div>
      <textarea id="rq-desc" class="tknote" style="min-height:88px" placeholder="Explain the rules in plain English: when it buys, when it exits, any filters (volume, trend, day of week…)."></textarea>
      <div class="tknote-bar"><button class="note-save" onclick="submitStratRequest()">Send to the desk</button><span id="rq-msg" class="sub"></span></div></div>`
    : `<div class="empty">Sign in to send the desk a strategy to test.<br><br><button class="auth-go" style="max-width:220px" onclick="openAuth('signup')">Create a free account</button></div>`}
  </div>`;

  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Strategies</h2><div class="ln"></div><span class="pill">${nStrat} strategies</span></div>
  <p class="sub" style="margin-bottom:14px">An open rule set, backtested on each stock's own ~19 years. It counts only where it cleared the bar — win rate ≥55%, positive expectancy after costs, profitable out-of-sample. Research, not advice.</p>
  <div class="sumstrip s4">
    ${sTile("Strategies", nStrat, "transparent rule sets", "")}
    ${sTile("Proven pairs", provenPairs, "strategy × stock, after costs + OOS", provenPairs ? "up" : "")}
    ${sTile("Stocks with a proven edge", nCovered, "across the universe", "")}
    ${sTile("Library updated", bt?.updated ? String(bt.updated).slice(0, 10) : "—", "full re-backtest", "")}
  </div>

  <div class="seg"><h2>Your board</h2><div class="ln"></div><span class="pill">${board.length ? board.length + " stock" + (board.length > 1 ? "s" : "") : "empty"}</span></div>
  <div class="card">
    <div class="sb-grid">${tiles}${addTile}</div>
    <span id="sb-msg" class="sub" style="display:block;margin-top:8px"></span>
    ${!me && board.length ? `<span class="sub" style="display:block;margin-top:4px">Your board lives in this session only — <a style="color:var(--accent);cursor:pointer" onclick="openAuth('signup')">sign in</a> to keep it.</span>` : ""}
  </div>
  ${isSubscribed() ? runBar + results
    : planWall("The strategy library on your board",
      "Pick your stocks above to read every strategy's results on each — ~19 years of that stock's own history per rule, with win rate, expectancy after costs and out-of-sample honesty.")}

  <div class="seg"><h2>The library</h2><div class="ln"></div></div>
  ${dict}
  ${reqForm}`;
}

/* ==========================================================================================
   PERSONAL ASTRO — a user casts their own birth chart in the browser, and the tradition reads it
   against every PSX chart. This is a financial-astrology EXPLORATION, not investment advice: it
   speaks in "the tradition reads / your chart resonates", never "buy" or "this will be profitable".
   The desk's own tests found astro has no measurable edge on PSX (published on /astro); this feature
   is the engaging, honest interpretation layer, and its calls are scored in public like any other.
   ========================================================================================== */
const D2R = Math.PI / 180, R2D = 180 / Math.PI;
const NAK = ["Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya",
  "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha",
  "Anuradha", "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta",
  "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"];
const SIGN12 = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo", "Libra", "Scorpio",
  "Sagittarius", "Capricorn", "Aquarius", "Pisces"];
const NEPH_BODIES = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Rahu", "Ketu"];

let _ephem = null;
async function loadEphem() {
  if (_ephem) return _ephem;
  const hdr = await j("natal_ephem.json");
  const buf = await fetch(DATA_BASE + "natal_ephem.bin?t=" + Date.now()).then(r => r.ok ? r.arrayBuffer() : Promise.reject(new Error("ephem HTTP " + r.status)));
  _ephem = { hdr, dv: new DataView(buf), start: Date.UTC(...hdr.start.split("-").map((x, i) => i === 1 ? +x - 1 : +x)) };
  return _ephem;
}
function _lahiri(jd) { return 23.853 + 0.0139686 * ((jd - 2451545.0) / 365.25); }   // matches the derived table
function _toJD(y, m, d, hourUT) {
  if (m <= 2) { y -= 1; m += 12; }
  const A = Math.floor(y / 100), B = 2 - A + Math.floor(A / 4);
  return Math.floor(365.25 * (y + 4716)) + Math.floor(30.6001 * (m + 1)) + d + B - 1524.5 + hourUT / 24;
}
function _lerpLon(a, b, f) { const d = ((b - a + 540) % 360) - 180; return (a + d * f + 360) % 360; }
function nakOf(lon) { const s = 360 / 27, i = Math.floor(lon / s) % 27, p = Math.floor((lon % s) / (s / 4)) + 1; return { nak: NAK[i], pada: p, i }; }

/* Compute a sidereal (Lahiri) birth chart in the browser from date/time/place.
   grahas from the shipped daily table (interpolated to the birth minute); ascendant computed live
   from local sidereal time + latitude. Returns positions + a moon-cusp honesty flag. */
async function computeNatal(bd) {
  const { date, time, tz, lat, lon } = bd;
  // The wizard persists this as `time_known` (snake_case, matching the Supabase column); accept both
  // spellings. Reading only `timeKnown` meant every chart silently fell back to Chandra lagna and no
  // ascendant was ever computed, however exact the birth time given.
  const timeKnown = bd.timeKnown ?? bd.time_known ?? false;
  const e = await loadEphem();
  const [Y, M, D] = date.split("-").map(Number);
  const [hh, mm] = (time || "12:00").split(":").map(Number);
  const localH = (hh || 0) + (mm || 0) / 60;
  const utH = localH - (tz || 0);                             // local clock -> UT
  // day index into the table, plus fraction of day (UT), spilling across midnight if utH<0 or >=24
  let dayMs = Date.UTC(Y, M - 1, D) + utH * 3600000;
  const dayIdx = Math.floor((dayMs - e.start) / 86400000);
  const frac = (dayMs - e.start) / 86400000 - dayIdx;
  const grahas = {};
  if (dayIdx < 0 || dayIdx >= e.hdr.n_days - 1) return { error: "birth date outside the ephemeris range (1950–2035)" };
  const readRow = (di) => NEPH_BODIES.map((_, b) => e.dv.getUint16((di * 9 + b) * 2, true) / 10);
  const r0 = readRow(dayIdx), r1 = readRow(dayIdx + 1);
  let moonCusp = false;
  NEPH_BODIES.forEach((body, b) => {
    const lonv = _lerpLon(r0[b], r1[b], frac);
    const si = Math.floor(lonv / 30) % 12, nk = nakOf(lonv);
    if (body === "Moon") { const s = 360 / 27, edge = Math.min(lonv % s, s - (lonv % s)); if (edge < 0.5) moonCusp = true; }
    grahas[body] = { lon: +lonv.toFixed(2), sign: SIGN12[si], sign_i: si, deg_in_sign: +(lonv % 30).toFixed(2), nakshatra: nk.nak, pada: nk.pada };
  });
  // ascendant (needs the exact minute + place)
  let ascend = null;
  if (timeKnown) {
    const jd = _toJD(Y, M, D, utH);
    const T = (jd - 2451545.0) / 36525;
    let gmst = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T * T - T * T * T / 38710000;
    const lst = (((gmst + lon) % 360) + 360) % 360;
    const eps = (23.4392911 - 0.0130042 * T) * D2R;
    const ramc = lst * D2R, phi = lat * D2R;
    let asc = Math.atan2(Math.cos(ramc), -(Math.sin(ramc) * Math.cos(eps) + Math.tan(phi) * Math.sin(eps))) * R2D;
    asc = ((asc % 360) + 360) % 360;
    const sid = ((asc - _lahiri(jd)) % 360 + 360) % 360;
    ascend = { lon: +sid.toFixed(2), sign: SIGN12[Math.floor(sid / 30) % 12], deg_in_sign: +(sid % 30).toFixed(2), nakshatra: nakOf(sid).nak };
  }
  return { grahas, ascendant: ascend, moon_cusp: moonCusp,
    dasha: vimshottariFor(grahas.Moon.lon, date), computed_at: new Date().toISOString() };
}

/* Vimshottari maha-dasha sequence for a person, from the natal Moon's nakshatra. Birth time known,
   so unlike the stock charts these dates are honest (no first-trade-time ambiguity). */
const _DORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"];
const _DYEARS = { Ketu: 7, Venus: 20, Sun: 6, Moon: 10, Mars: 7, Rahu: 18, Jupiter: 16, Saturn: 19, Mercury: 17 };
function vimshottariFor(moonLon, birthISO) {
  const span = 360 / 27, nakI = Math.floor(moonLon / span) % 27, lord = _DORDER[nakI % 9];
  const fracDone = (moonLon % span) / span, YD = 365.2425;
  let cursor = new Date(birthISO + "T12:00:00Z").getTime() - fracDone * _DYEARS[lord] * YD * 86400000;
  const start = _DORDER.indexOf(lord), seq = [];
  for (let k = 0; k < 9; k++) {
    const g = _DORDER[(start + k) % 9], end = cursor + _DYEARS[g] * YD * 86400000;
    seq.push({ lord: g, from: new Date(cursor).toISOString().slice(0, 10), to: new Date(end).toISOString().slice(0, 10), years: _DYEARS[g] });
    cursor = end;
  }
  const now = Date.now();
  const cur = seq.find(d => new Date(d.from).getTime() <= now && now < new Date(d.to).getTime()) || seq[0];
  // antardasha: the sub-period inside the running maha-dasha. Each maha of L years splits into 9
  // antardashas of L*antarYears/120 years, in the same graha order starting from the maha lord.
  const antar = antardashaOf(cur, now);
  return { current: { ...cur, ...antar }, antar_sequence: antardashaSeq(cur), sequence: seq };
}
function antardashaSeq(maha) {
  const YD = 365.2425, si = _DORDER.indexOf(maha.lord);
  let s = new Date(maha.from + "T12:00:00Z").getTime(), out = [];
  for (let k = 0; k < 9; k++) {
    const g = _DORDER[(si + k) % 9], e = s + _DYEARS[maha.lord] * _DYEARS[g] / 120 * YD * 86400000;
    out.push({ lord: g, from: new Date(s).toISOString().slice(0, 10), to: new Date(e).toISOString().slice(0, 10) });
    s = e;
  }
  return out;
}
function antardashaOf(maha, at) {
  const cur = antardashaSeq(maha).find(a => new Date(a.from).getTime() <= at && at < new Date(a.to).getTime());
  return cur ? { antar: cur.lord, antar_from: cur.from, antar_to: cur.to } : {};
}

/* ---------- the natal orrery: a 2D SVG that reads as 3D — nine grahas on tilted concentric
   orbits (foreshortened ellipses = perspective), each at its true sidereal longitude, with depth
   from layered shadows and a light gradient. Pure inline SVG (CSP-safe), pixel-glyph planets. */
const ORBIT_ORDER = ["Moon", "Mercury", "Venus", "Sun", "Mars", "Jupiter", "Saturn", "Rahu", "Ketu"];
function natalOrrery(grahas, ascendant, transits) {
  const W = 440, H = 300, cx = W / 2, cy = H / 2 + 8, TILT = 0.46;   // ry/rx foreshorten
  const rings = ORBIT_ORDER.length;
  const rMin = 30, rMax = 196;
  // zodiac ring (outermost) with 12 sign spokes
  const rxZ = rMax + 16, ryZ = rxZ * TILT;
  let spokes = "", signLbls = "";
  for (let s = 0; s < 12; s++) {
    const a = (s * 30) * Math.PI / 180, a2 = (s * 30 + 30) * Math.PI / 180;
    const x1 = cx + rxZ * Math.cos(a), y1 = cy - ryZ * Math.sin(a);
    spokes += `<line x1="${cx + (rMin - 8) * Math.cos(a)}" y1="${cy - (rMin - 8) * TILT * Math.sin(a)}" x2="${x1.toFixed(1)}" y2="${y1.toFixed(1)}" class="orr-spoke"/>`;
    const am = (s * 30 + 15) * Math.PI / 180;
    signLbls += `<text x="${(cx + (rxZ + 12) * Math.cos(am)).toFixed(1)}" y="${(cy - (ryZ + 12) * Math.sin(am)).toFixed(1)}" class="orr-sign">${["ARI", "TAU", "GEM", "CAN", "LEO", "VIR", "LIB", "SCO", "SAG", "CAP", "AQU", "PIS"][s]}</text>`;
  }
  // concentric orbit ellipses (back-to-front for depth)
  let orbits = "";
  ORBIT_ORDER.forEach((b, i) => {
    const rx = rMin + (rMax - rMin) * (i / (rings - 1)), ry = rx * TILT;
    orbits += `<ellipse cx="${cx}" cy="${cy}" rx="${rx.toFixed(1)}" ry="${ry.toFixed(1)}" class="orr-orbit" style="opacity:${0.28 + 0.05 * i}"/>`;
  });
  // ascendant ray
  let ascRay = "";
  if (ascendant) {
    const a = ascendant.lon * Math.PI / 180;
    ascRay = `<line x1="${cx}" y1="${cy}" x2="${(cx + rxZ * Math.cos(a)).toFixed(1)}" y2="${(cy - ryZ * Math.sin(a)).toFixed(1)}" class="orr-asc"/>
      <text x="${(cx + (rxZ + 6) * Math.cos(a)).toFixed(1)}" y="${(cy - (ryZ + 6) * Math.sin(a)).toFixed(1)}" class="orr-asc-lbl">ASC</text>`;
  }
  // planets — placed on their orbit at true longitude, drawn front-to-back so nearer ones overlap
  const placed = ORBIT_ORDER.map((b, i) => {
    const g = grahas[b]; if (!g) return null;
    const rx = rMin + (rMax - rMin) * (i / (rings - 1)), ry = rx * TILT;
    const a = g.lon * Math.PI / 180;
    const x = cx + rx * Math.cos(a), y = cy - ry * Math.sin(a);
    return { b, x, y, depth: y };
  }).filter(Boolean).sort((p, q) => p.depth - q.depth);
  const planets = placed.map(p => `<g class="orr-planet">
      <ellipse cx="${p.x.toFixed(1)}" cy="${(p.y + 11).toFixed(1)}" rx="9" ry="2.5" class="orr-shadow"/>
      <g class="orr-g">${pixelRects(p.b, 19, p.x, p.y)}</g></g>`).join("");
  // today's sky — the same nine grahas as they stand RIGHT NOW, faint on the outermost ring.
  // The natal chart is fixed; this ring drifts a little every day, which is the whole point.
  let transitMarks = "";
  if (transits) transitMarks = NEPH_BODIES.map(b => {
    const t = transits[b]; if (!t) return "";
    const a = t.lon * Math.PI / 180;
    return `<g class="orr-transit">${pixelRects(b, 11, cx + rxZ * Math.cos(a), cy - ryZ * Math.sin(a))}</g>`;
  }).join("");
  return `<div class="orrery"><svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet">
    <defs><radialGradient id="orrBg" cx="50%" cy="46%" r="62%"><stop offset="0%" stop-color="var(--panel2)"/><stop offset="100%" stop-color="var(--panel)"/></radialGradient></defs>
    <ellipse cx="${cx}" cy="${cy}" rx="${rxZ + 26}" ry="${(rxZ + 26) * TILT + 10}" fill="url(#orrBg)"/>
    ${orbits}${spokes}${ascRay}
    <g class="orr-earth"><circle cx="${cx}" cy="${cy}" r="4"/><text x="${cx}" y="${cy + 15}" class="orr-earth-lbl">you</text></g>
    ${planets}${transitMarks}${signLbls}
  </svg></div>`;
}

/* ==========================================================================================
   GOCHARA — the moving sky read against the user's natal Moon, recomputed every day from the same
   ephemeris table the natal cast uses. The natal chart is static; THIS is what changes daily, and
   the dated "worth another look" shifts are the reason a reading is worth returning to.
   ========================================================================================== */
const GOCHARA_FAV = {   // classical favourable houses counted from the natal Moon
  Sun: [3, 6, 10, 11], Moon: [1, 3, 6, 7, 10, 11], Mars: [3, 6, 11],
  Mercury: [2, 4, 6, 8, 10, 11], Jupiter: [2, 5, 7, 9, 11],
  Venus: [1, 2, 3, 4, 5, 8, 9, 11, 12], Saturn: [3, 6, 11], Rahu: [3, 6, 11], Ketu: [3, 6, 11],
};

/* sidereal longitudes of the nine grahas for any instant inside the table (1950–2035) */
async function skyOn(dateMs) {
  const e = await loadEphem();
  const di = Math.floor((dateMs - e.start) / 86400000);
  if (di < 0 || di >= e.hdr.n_days - 1) return null;
  const frac = (dateMs - e.start) / 86400000 - di;
  const read = k => NEPH_BODIES.map((_, b) => e.dv.getUint16(((di + k) * 9 + b) * 2, true) / 10);
  const r0 = read(0), r1 = read(1), out = {};
  NEPH_BODIES.forEach((body, b) => {
    const lo = _lerpLon(r0[b], r1[b], frac), si = Math.floor(lo / 30) % 12;
    out[body] = { lon: lo, sign_i: si, sign: SIGN12[si] };
  });
  return out;
}

function gocharaRead(nc, sky, amap) {
  const moonI = nc.grahas.Moon.sign_i ?? Math.floor(nc.grahas.Moon.lon / 30) % 12;
  const tiles = NEPH_BODIES.map(g => {
    const t = sky[g];
    const house = ((t.sign_i - moonI + 12) % 12) + 1;
    const fav = (GOCHARA_FAV[g] || []).includes(house);
    // "testing" is reserved for the classical hard Saturn seats (Sade Sati houses + the 8th);
    // everything else non-favourable is simply neutral — gochara is weather, not doom.
    const tag = fav ? "favourable" : (g === "Saturn" && [12, 1, 2, 8].includes(house)) ? "testing" : "neutral";
    let conj = null;
    // 2.5deg orb matches scripts/astro_natal.py's transits_to_natal() on purpose — same question
    // ("is anything conjunct this natal point today"), same answer, whether the chart is a person's
    // or a company's.
    for (const ng of NEPH_BODIES) {
      const d = Math.abs(((t.lon - nc.grahas[ng].lon + 540) % 360) - 180);
      if (d <= 2.5) { conj = ng; break; }
    }
    const domains = (amap?.grahas?.[g]?.domains || []).slice(0, 2).join(", ");
    return { g, sign: t.sign, house, fav, tag, conj, domains };
  });
  return { tiles, sadeSati: [12, 1, 2].includes(tiles.find(t => t.g === "Saturn").house) };
}

/* The comeback calendar: scan the ephemeris forward for the dates the sky re-deals THIS chart —
   sign ingresses (house-from-Moon changes) for everything but the too-fast Moon and mirror Ketu,
   plus the user's own dasha/antardasha turnovers. Sorted, dated, honest. */
async function upcomingShifts(nc, horizon = 400) {
  const e = await loadEphem();
  const t0 = Date.now();
  const di0 = Math.floor((t0 - e.start) / 86400000);
  if (di0 < 0) return [];
  const moonI = Math.floor(nc.grahas.Moon.lon / 30) % 12;
  const bodies = ["Sun", "Mars", "Mercury", "Venus", "Jupiter", "Saturn", "Rahu"];
  const bi = bodies.map(b => NEPH_BODIES.indexOf(b));
  const maxDi = Math.min(di0 + horizon, e.hdr.n_days - 1);
  const out = [];
  let prev = bi.map(b => Math.floor((e.dv.getUint16((di0 * 9 + b) * 2, true) / 10) / 30) % 12);
  for (let di = di0 + 1; di <= maxDi; di++) {
    bi.forEach((b, k) => {
      const si = Math.floor((e.dv.getUint16((di * 9 + b) * 2, true) / 10) / 30) % 12;
      if (si !== prev[k]) {
        const house = ((si - moonI + 12) % 12) + 1;
        out.push({ date: new Date(e.start + di * 86400000).toISOString().slice(0, 10),
          kind: "ingress", body: bodies[k], sign: SIGN12[si], house, fav: (GOCHARA_FAV[bodies[k]] || []).includes(house) });
        prev[k] = si;
      }
    });
  }
  const cur = nc.dasha?.current || {};
  for (const [d, kind, body] of [[cur.antar_to, "antar", cur.antar], [cur.to, "maha", cur.lord]]) {
    const t = d && new Date(d).getTime();
    if (t && t > t0 && t - t0 < horizon * 86400000) out.push({ date: String(d).slice(0, 10), kind, body });
  }
  out.sort((a, b) => a.date.localeCompare(b.date));
  return out;
}

/* ---------- the dasha timeline: the "when". The user's Vimshottari maha-dasha ribbon with the
   current period + sub-period marked, and which market each period's lord favours. This is the
   map of TIME the owner asked for — framed as tradition's rhythm, never "invest on this date". */
function dashaTimeline(chart, amap) {
  const seq = chart.dasha?.sequence || [];
  if (!seq.length) return "";
  const now = Date.now();
  const t0 = new Date(seq[0].from).getTime(), t1 = new Date(seq[seq.length - 1].to).getTime(), span = t1 - t0;
  const nowPct = Math.max(0, Math.min(100, (now - t0) / span * 100));
  const segs = seq.map(d => {
    const a = new Date(d.from).getTime(), b = new Date(d.to).getTime();
    const active = a <= now && now < b;
    return `<div class="dt-seg ${active ? "on" : ""}" style="flex:${b - a}" title="${d.lord} ${d.from}–${d.to}">
      <span class="dt-glyph">${pixelGlyph(d.lord, 16)}</span><span class="dt-lord">${esc(d.lord)}</span><span class="dt-yr">${d.from.slice(0, 4)}</span></div>`;
  }).join("");
  const cur = chart.dasha?.current || {};
  const domains = b => ((amap?.grahas?.[b] || {}).domains || []).slice(0, 3).join(", ");
  const future = seq.filter(d => new Date(d.to).getTime() > now).slice(0, 3);
  return `<div class="dt-wrap">
    <div class="dt-ribbon">${segs}<div class="dt-now" style="left:${nowPct}%"><span>now</span></div></div>
    <div class="dt-legend">${future.map((d, i) => `<div class="dt-leg ${i === 0 ? "cur" : ""}"><b>${pixelGlyph(d.lord, 14)} ${esc(d.lord)} period</b><span class="sub">${d.from.slice(0, 4)}–${d.to.slice(0, 4)} · tradition lights up ${esc(domains(d.lord)) || "—"}</span></div>`).join("")}</div>
  </div>`;
}

/* The sub-period (antardasha) ribbon inside the running maha-dasha — the nearer, finer "when". */
function antardashaStrip(chart, amap) {
  const seq = chart.dasha?.antar_sequence || [];
  const maha = chart.dasha?.current;
  if (!seq.length || !maha) return "";
  const now = Date.now();
  const t0 = new Date(seq[0].from).getTime(), t1 = new Date(seq[seq.length - 1].to).getTime(), span = t1 - t0 || 1;
  const nowPct = Math.max(0, Math.min(100, (now - t0) / span * 100));
  const segs = seq.map(d => {
    const a = new Date(d.from).getTime(), b = new Date(d.to).getTime();
    return `<div class="dt-seg sm ${a <= now && now < b ? "on" : ""}" style="flex:${b - a}" title="${d.lord} ${d.from}–${d.to}">
      <span class="dt-glyph">${pixelGlyph(d.lord, 12)}</span><span class="dt-lord">${esc(d.lord)}</span></div>`;
  }).join("");
  const cur = seq.find(d => new Date(d.from).getTime() <= now && now < new Date(d.to).getTime());
  const domains = b => ((amap?.grahas?.[b] || {}).domains || []).slice(0, 3).join(", ");
  return `<div class="dt-sub"><div class="dt-sub-lbl">Sub-periods within your ${esc(maha.lord)} maha</div>
    <div class="dt-ribbon sub">${segs}<div class="dt-now" style="left:${nowPct}%"><span>now</span></div></div>
    ${cur ? `<p class="sub" style="margin-top:8px">Now: <b>${esc(maha.lord)} / ${esc(cur.lord)}</b> to ~${esc(String(cur.to).slice(0, 7))} — tradition colours these months with ${esc(domains(cur.lord)) || "—"}.</p>` : ""}</div>`;
}

/* Which of the user's own periods a given stock brightens under — the per-stock "when". */
function stockTiming(user, stock, sector, amap) {
  const seq = user.dasha?.sequence || [];
  const now = Date.now();
  const target = stock && stock.natal ? SIGN_LORD[Math.floor((stock.natal.Moon.lon % 360) / 30) % 12]
    : (sector ? (amap?.sector_significators?.[sector] || {}).primary : null);
  if (!target) return null;
  const horizon = now + 25 * 365.25 * 86400000;   // within a working lifetime, not centuries out
  const windows = seq.filter(d => new Date(d.to).getTime() > now && new Date(d.from).getTime() < horizon)
    .map(d => ({ ...d, rel: d.lord === target ? "peak" : (FRIEND[d.lord]?.f || []).includes(target) ? "warm" : (FRIEND[d.lord]?.e || []).includes(target) ? "cool" : "neutral" }))
    .filter(d => d.rel === "peak" || d.rel === "warm").slice(0, 2);
  if (!windows.length) return null;
  return { target, windows };
}

/* ---------- synastry: how the tradition reads a person's chart against a stock's.
   Uses classical Vedic techniques (Tara koota on the Moon nakshatras, planetary friendship of the
   sign lords, dasha resonance) — the same methods used for personal compatibility, applied to the
   market chart. A resonance score 0–100 with an explained breakdown. This is astrological
   interpretation, presented as such; it is never a recommendation to buy or a profit forecast. */
const SIGN_LORD = ["Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter"];
const FRIEND = {
  Sun: { f: ["Moon", "Mars", "Jupiter"], e: ["Venus", "Saturn"] },
  Moon: { f: ["Sun", "Mercury"], e: [] },
  Mars: { f: ["Sun", "Moon", "Jupiter"], e: ["Mercury"] },
  Mercury: { f: ["Sun", "Venus"], e: ["Moon"] },
  Jupiter: { f: ["Sun", "Moon", "Mars"], e: ["Mercury", "Venus"] },
  Venus: { f: ["Mercury", "Saturn"], e: ["Sun", "Moon"] },
  Saturn: { f: ["Mercury", "Venus"], e: ["Sun", "Moon", "Mars"] },
  Rahu: { f: ["Venus", "Saturn"], e: ["Sun", "Moon"] },
  Ketu: { f: ["Mars", "Jupiter"], e: ["Moon"] },
};
const NAT_BENEFIC = { Jupiter: 1, Venus: 1, Moon: 1, Mercury: 0.5 };
const NAT_MALEFIC = { Saturn: 1, Mars: 1, Rahu: 1, Ketu: 1, Sun: 0.5 };
function friendship(a, b) {
  if (a === b) return "same";
  const r = FRIEND[a] || { f: [], e: [] };
  if (r.f.includes(b)) return "friend";
  if (r.e.includes(b)) return "enemy";
  return "neutral";
}
// Tara koota: count person's Moon nakshatra -> stock's, the classical 9-fold auspiciousness
function taraKoota(userNakI, stockNakI) {
  const cnt = ((stockNakI - userNakI + 27) % 27) + 1, r = cnt % 9;
  const good = { 2: "Sampat (wealth)", 4: "Kshema (well-being)", 6: "Sadhaka (accomplishment)", 8: "Maitra (friendship)", 0: "Mitra (ally)" };
  const bad = { 3: "Vipat (loss)", 5: "Pratyari (obstacle)", 7: "Vadha (harm)" };
  if (good[r]) return { band: "harmonious", tara: good[r], w: 1 };
  if (bad[r]) return { band: "discordant", tara: bad[r], w: -1 };
  return { band: "mixed", tara: "Janma (the self)", w: 0 };
}

/* Commodities carry their own traditional rulerships in financial astrology — the metals, energy and
   crops a Pakistani investor actually watches. Scored against the user's chart the same way a
   chartless stock is: through the ruling graha. */
const COMMODITIES = [
  { name: "Gold", sig: "Sun", note: "the Sun's metal — kingship and store of value", glyph: "Sun" },
  { name: "Silver", sig: "Moon", note: "the Moon's metal — liquidity and the public's hoard", glyph: "Moon" },
  { name: "Crude oil", sig: "Saturn", note: "Saturn's — what is dug from deep underground", glyph: "Saturn" },
  { name: "Natural gas", sig: "Rahu", note: "Rahu's — the volatile and the piped", glyph: "Rahu" },
  { name: "Copper", sig: "Venus", note: "Venus's metal — wiring, comfort, industry", glyph: "Venus" },
  { name: "Wheat", sig: "Moon", note: "the Moon's — the staple crop and its rains", glyph: "Moon" },
  { name: "Cotton", sig: "Venus", note: "Venus's fibre — cloth and its trade", glyph: "Venus" },
  { name: "Sugar", sig: "Venus", note: "Venus's sweetness — cane and refinery", glyph: "Venus" },
];
/* Resonance of the user's chart with a single ruling graha — the shared core behind both the
   chartless-stock and commodity readings. Returns a 0-100 score + explained reasons. */
function resonanceWithGraha(user, target, label, amap) {
  if (!target) return { score: null, reasons: [] };
  const uMoon = user.grahas.Moon, uLord = SIGN_LORD[Math.floor((uMoon.lon % 360) / 30) % 12];
  const uDasha = user.dasha?.current?.lord, uAntar = user.dasha?.current?.antar;
  let score = 50; const reasons = [];
  const fr = friendship(uLord, target);
  const fw = fr === "friend" || fr === "same" ? 1 : fr === "enemy" ? -1 : 0;
  score += fw * 14;
  reasons.push({ k: `You & ${target}`, v: fr, why: `${label} answers to ${target}. Your Moon-lord ${uLord} is ${fr === "same" ? "that same planet" : "traditionally its " + fr}.`, w: fw });
  if (uDasha === target) { score += 16; reasons.push({ k: "You're in its period", v: `${target} dasha`, why: `You are running a ${target} maha-dasha — the very planet that rules ${label}.`, w: 1 }); }
  else if (uDasha) { const d = friendship(uDasha, target); const dw = d === "friend" ? 1 : d === "enemy" ? -1 : 0; score += dw * 7; reasons.push({ k: "Your current period", v: `${uDasha} dasha`, why: `Your ${uDasha} period is ${d} to ${target}.`, w: dw }); }
  if (uAntar === target) { score += 10; reasons.push({ k: "And your sub-period", v: `${uAntar} antardasha`, why: `Your running sub-period is ${uAntar}'s too — a sharper, nearer window.`, w: 1 }); }
  const ug = user.grahas[target];
  if (ug && SIGN_LORD[Math.floor((ug.lon % 360) / 30) % 12] === target) { score += 8; reasons.push({ k: `Your ${target}`, v: "strong", why: `${target} sits in its own sign ${ug.sign} in your chart — a dignified placement.`, w: 1 }); }
  else if (ug && amap) {
    // Rahu/Ketu carry no agreed exaltation/debilitation in astro_map.json (dispute noted there) — both fields null, so no claim is made for them here.
    const gd = amap.grahas?.[target] || {};
    if (gd.exalted?.sign && ug.sign === gd.exalted.sign) { score += 12; reasons.push({ k: `Your ${target}`, v: "exalted", why: `${target} sits in ${ug.sign} in your chart — its sign of exaltation, the strongest placement it can take.`, w: 1 }); }
    else if (gd.debilitated?.sign && ug.sign === gd.debilitated.sign) { score -= 10; reasons.push({ k: `Your ${target}`, v: "debilitated", why: `${target} sits in ${ug.sign} in your chart — its sign of debilitation, a weak placement.`, w: -1 }); }
  }
  score = Math.max(2, Math.min(98, Math.round(score)));
  const verdict = score >= 68 ? "harmonious" : score >= 55 ? "favourable" : score >= 45 ? "neutral" : score >= 32 ? "testing" : "discordant";
  return { score, verdict, reasons };
}

/* Goal-tailored framing. The user's stated goal colours the LANGUAGE of the reading — which grahas
   the tradition emphasises for that aim — never the maths. */
const GOAL_LENS = {
  growth: { label: "long-term growth", lead: "Jupiter", grahas: ["Jupiter", "Sun", "Mars"], line: "Tradition ties lasting growth to Jupiter's expansion — so its houses and periods carry the most weight for you." },
  income: { label: "dividend income", lead: "Venus", grahas: ["Venus", "Moon", "Jupiter"], line: "For steady income the tradition looks to Venus and the Moon — comfort, liquidity, the recurring yield." },
  trading: { label: "active trading", lead: "Mercury", grahas: ["Mercury", "Moon", "Mars"], line: "For quick moves the tradition watches Mercury and the fast Moon — and your nearer sub-periods matter more than the long arc." },
  curious: { label: "exploration", lead: null, grahas: [], line: "" },
};
function goalLens() { return GOAL_LENS[(astroPrefs().goal || "curious")] || GOAL_LENS.curious; }

/* Score a person's chart against one stock. If the stock has a verified natal chart, the full
   technique set runs; otherwise it falls back to the sector's significator graha. */
function synastry(user, stock, sector, amap, astroNow) {
  const reasons = [];
  let score = 50;   // neutral start
  const uMoon = user.grahas.Moon, uLordUser = SIGN_LORD[uMoon.sign_i];
  const uDasha = user.dasha?.current?.lord;

  const _si = p => Math.floor((p.lon % 360) / 30) % 12;   // stock natal carries lon, not sign_i
  if (stock && stock.natal) {
    const sMoon = stock.natal.Moon;
    // 1. Tara koota on the Moon nakshatras — the heart of Vedic compatibility
    const tk = taraKoota(nakOf(uMoon.lon).i, nakOf(sMoon.lon).i);
    score += tk.w * 16;
    reasons.push({ k: "Moon compatibility (Tara)", v: tk.band, why: `Counting from your Moon star to the stock's lands on ${tk.tara}.`, w: tk.w });
    // 2. friendship of the Moon-sign lords
    const sLord = SIGN_LORD[_si(sMoon)], fr = friendship(uLordUser, sLord);
    const fw = fr === "friend" || fr === "same" ? 1 : fr === "enemy" ? -1 : 0;
    score += fw * 10;
    reasons.push({ k: "Sign-lord friendship", v: fr, why: `Your Moon rules through ${uLordUser}; the stock's through ${sLord} — ${fr === "same" ? "the same planet" : "traditionally " + fr + "s"}.`, w: fw });
    // 3. your benefics / malefics landing on the stock's Sun or Moon sign
    let bw = 0;
    ["Jupiter", "Venus", "Saturn", "Mars"].forEach(g => {
      const ug = user.grahas[g]; if (!ug) return;
      [["Sun", sMoon && stock.natal.Sun], ["Moon", sMoon]].forEach(([nm, sp]) => {
        if (sp && ug.sign_i === Math.floor(sp.lon / 30) % 12) {
          const ben = NAT_BENEFIC[g] ? 1 : -1; bw += ben;
          reasons.push({ k: `Your ${g} on its natal ${nm}`, v: ben > 0 ? "supportive" : "testing", why: `Your ${g} sits in ${ug.sign}, the stock's natal ${nm} sign — tradition reads ${g} there as ${ben > 0 ? "a blessing" : "a strain"}.`, w: ben });
        }
      });
    });
    score += Math.max(-14, Math.min(14, bw * 7));
    // 4. dasha resonance: are you running a period whose lord the stock's chart welcomes?
    if (uDasha) {
      const dfr = friendship(uDasha, sLord);
      const dw = dfr === "friend" || dfr === "same" ? 1 : dfr === "enemy" ? -1 : 0;
      score += dw * 8;
      reasons.push({ k: "Your current period", v: `${uDasha} dasha`, why: `You are in a ${uDasha} period; the stock's Moon-lord ${sLord} is ${dfr === "same" ? "the very same" : "traditionally its " + dfr}.`, w: dw });
    }
  } else {
    // no stock chart (listed pre-2000) — read against the sector's significator graha, same
    // technique the commodities lens uses, so a chartless name gets the same resonance dimensions
    // (including the antardasha check) rather than a hand-rolled duplicate missing one.
    const sig = sector ? (amap?.sector_significators?.[sector] || {}) : {};
    const prim = sig.primary;
    if (!prim) return { score: null, verdict: "no reading", reasons: [] };
    return resonanceWithGraha(user, prim, sector, amap);
  }
  score = Math.max(2, Math.min(98, Math.round(score)));
  const verdict = score >= 68 ? "harmonious" : score >= 55 ? "favourable" : score >= 45 ? "neutral" : score >= 32 ? "testing" : "discordant";
  return { score, verdict, reasons };
}

/* ---------- pixel grahas: 11x11 one-bit glyphs, drawn as SVG rects in currentColor.
   The classical symbols, pixelated — Saturn's ring, Jupiter's band, the Sun's rays. ---------- */
const PIXEL_GRAHAS = {
  Sun: ["....#....", ".#..#..#.", "..#####..", ".##...##.", "#.#.#.#.#", ".##...##.", "..#####..", ".#..#..#.", "....#...."],
  Moon: ["...###...", "..##.....", ".##......", ".##......", ".##......", ".##......", ".##......", "..##.....", "...###..."],
  Mercury: [".#.....#.", "..#####..", ".##...##.", ".##...##.", "..#####..", "....#....", "..#####..", "....#....", "....#...."],
  Venus: ["..#####..", ".##...##.", ".##...##.", ".##...##.", "..#####..", "....#....", "..#####..", "....#....", "....#...."],
  Mars: [".....####", "......##.", "....##.##", "..#####..", ".##...#..", ".##......", ".##......", "..#####..", "........."],
  Jupiter: ["..#####..", ".##...##.", "#########", "#########", ".##...##.", ".##...##.", "..#####..", ".........", "........."],
  Saturn: ["..#####..", ".##...##.", ".##...##.", "###...###", "#########", "###...###", ".##...##.", "..#####..", "........."],
  Rahu: ["..#####..", ".##...##.", ".##...##.", ".##...##.", "..#...#..", "..#...#..", ".##...##.", "##.....##", "........."],
  Ketu: ["##.....##", ".##...##.", "..#...#..", "..#...#..", ".##...##.", ".##...##.", ".##...##.", "..#####..", "........."],
};
function pixelGlyph(body, px) {
  const g = PIXEL_GRAHAS[body];
  if (!g) return "";
  const n = 9, cell = Math.max(1, Math.floor(px / n));
  let rects = "";
  g.forEach((row, y) => { [...row].forEach((c, x) => { if (c === "#") rects += `<rect x="${x * cell}" y="${y * cell}" width="${cell}" height="${cell}"/>`; }); });
  return `<svg class="pxg" viewBox="0 0 ${n * cell} ${n * cell}" width="${px}" height="${px}" fill="currentColor" aria-label="${body}">${rects}</svg>`;
}
const GRAHA_AB = { Sun: "Su", Moon: "Mo", Mercury: "Me", Venus: "Ve", Mars: "Ma", Jupiter: "Ju", Saturn: "Sa", Rahu: "Ra", Ketu: "Ke" };
// raw <rect> string for embedding a glyph DIRECTLY in a parent SVG (no foreignObject — which fails
// in Safari and breaks screenshot/export renderers). Centred on (ox,oy), total size px.
function pixelRects(body, px, ox, oy, fill) {
  const g = PIXEL_GRAHAS[body]; if (!g) return "";
  const n = 9, cell = Math.max(1, px / n), o0 = -px / 2;
  let r = "";
  g.forEach((row, y) => { [...row].forEach((c, x) => { if (c === "#") r += `<rect x="${(ox + o0 + x * cell).toFixed(1)}" y="${(oy + o0 + y * cell).toFixed(1)}" width="${cell.toFixed(1)}" height="${cell.toFixed(1)}"/>`; }); });
  return `<g fill="${fill || "currentColor"}">${r}</g>`;
}

/* the zodiac strip: 12 sidereal signs as columns; transiting grahas on the top lane, the natal
   chart (when one exists) on the bottom lane — so a transit sitting on a natal point is VISIBLE
   as a vertical alignment, which is the whole thing astrologers look for. */
function zodiacStrip(transitPos, natalPos) {
  const SIGNS12 = ["Ari", "Tau", "Gem", "Can", "Leo", "Vir", "Lib", "Sco", "Sag", "Cap", "Aqu", "Pis"];
  const lane = pos => {
    const bySign = {};
    Object.entries(pos || {}).forEach(([b, p]) => {
      const si = Math.floor((p.lon ?? 0) / 30) % 12;
      (bySign[si] = bySign[si] || []).push(b);
    });
    return SIGNS12.map((_, i) => `<div class="zs-cell">${(bySign[i] || []).map(b =>
      `<span class="zs-g" title="${b}${pos[b].retrograde ? " (retrograde)" : ""}">${pixelGlyph(b, 18)}<i>${GRAHA_AB[b]}${pos[b].retrograde ? "ᴿ" : ""}</i></span>`).join("")}</div>`).join("");
  };
  return `<div class="zstrip">
    <div class="zs-lane"><span class="zs-lbl">sky now</span>${lane(transitPos)}</div>
    ${natalPos ? `<div class="zs-lane natal"><span class="zs-lbl">at birth</span>${lane(natalPos)}</div>` : ""}
    <div class="zs-lane signs"><span class="zs-lbl"></span>${SIGNS12.map(s => `<div class="zs-cell sign">${s}</div>`).join("")}</div>
  </div>`;
}

/* ---------- the astro board (profiles.astro_board; session-only for guests) ---------- */
function astroBoard() {
  if (me) return (myProfile && myProfile.astro_board) || [];
  try { return JSON.parse(sessionStorage.getItem("astroboard") || "[]"); } catch (e) { return []; }
}
async function saveAstroBoard(list) {
  if (me) return saveProfile({ astro_board: list });
  try { sessionStorage.setItem("astroboard", JSON.stringify(list)); } catch (e) { /* private mode */ }
  return null;
}
function astroRunOn(sym) { try { return !!sessionStorage.getItem("astroran:" + sym); } catch (e) { return false; } }
async function addAstroTicker() {
  if (addAstroTicker._busy) return;
  addAstroTicker._busy = true;
  try {
    const inp = document.getElementById("ab-tkr"), msg = document.getElementById("ab-msg");
    const say = t => { if (msg) msg.textContent = t; };
    const sym = (inp?.value || "").toUpperCase().trim();
    if (!sym) return;
    const uni = await j("universe.json");
    if (!uni?.symbols?.[sym]) return say(`${sym} isn't in the desk's universe — try the suggestions as you type.`);
    const cur = astroBoard();
    if (cur.includes(sym)) return say(`${sym} is already on your board.`);
    if (cur.length >= 8) return say("The board holds 8 charts — remove one first.");
    const err = await saveAstroBoard([...cur, sym]);
    if (err) return say("Couldn't save — try again.");
    pageAstro();
  } finally {
    addAstroTicker._busy = false;
  }
}
async function removeAstroTicker(sym) {
  const err = await saveAstroBoard(astroBoard().filter(s => s !== sym));
  if (!err) pageAstro();
}

/* ---------- the reading: what the tradition says about this chart, composed strictly from the
   computed layers (astro_natal / astro / astro_map). Template prose over real data — no agent, no
   invention, and NEVER a call. The desk's tested-vs-untested status is stated inside the reading. */
/* The four blocks that turn a chart printout into something worth reading. Each answers a different
   question, and each is built ONLY from state/: the tradition's dated claim (dashas), what the desk
   measured on THIS name (astro_backtest), how the name's weather compares to the country's and the
   market's own charts (astro_context), and what the sky is doing right now expressed in the exact
   vocabulary the backtest used. Nothing here is a call — every block that states a tradition claim
   carries the untested stamp, and every block that states a measurement carries the p-value. */
const NATURE_WORD = { benefic: "supportive", malefic: "difficult", mixed: "mixed" };

// (a) the dasha ladder with DATES — the tradition's one genuinely falsifiable-in-advance structure
function arDashaBlock(dasha, amap, who) {
  const cur = dasha?.current;
  if (!cur?.maha) return "";
  const nat = b => (amap?.grahas?.[b] || {}).natural_nature || "mixed";
  const why = b => (amap?.grahas?.[b] || {}).nature_note || "";
  const dom = b => ((amap?.grahas?.[b] || {}).domains || []).slice(0, 3).join(", ");
  const lane = (kind, lord, from, to, on) => {
    const n = nat(lord);
    return `<div class="ar-drow ${n}">
      <span class="ar-dl">${pixelGlyph(lord, 13)} ${esc(lord)}</span>
      <span class="ar-dk">${esc(kind)}</span>
      <span class="ar-dd">${esc(on || `${String(from || "").slice(0, 7)} → ${String(to || "").slice(0, 7)}`)}</span>
      <span class="ar-dn ${n}">${esc(NATURE_WORD[n])}</span></div>`;
  };
  const up = (dasha.upcoming || []).slice(0, 3);
  return `<div class="ar-block">
    <div class="ar-bh"><b>The period, and when it turns</b><span class="tag">tradition's claim · untested</span></div>
    <p class="ar-bp">Vimshottari divides a chart's life into dated planetary periods. ${esc(who)} is running a
      <b>${esc(cur.maha)}</b> mahadasha${cur.antar ? ` with a <b>${esc(cur.antar)}</b> sub-period` : ""}. Tradition ties
      ${esc(cur.maha)} to ${esc(dom(cur.maha))}, and classes it a natural ${esc(nat(cur.maha))} — ${esc(why(cur.maha))}.
      The dates below are fixed by the birth moment, so they were set long before any price was.</p>
    <div class="ar-dl-wrap">
      ${lane("mahadasha", cur.maha, cur.maha_from, cur.maha_to)}
      ${cur.antar ? lane("running now", cur.antar, cur.antar_from, cur.antar_to) : ""}
      ${up.map(u => lane(u.kind === "maha" ? "next mahadasha" : "next sub-period", u.lord, null, null, u.on)).join("")}
    </div>
    <p class="ar-bn">"Supportive" and "difficult" are the tradition's own labels for the period lord (natural
      benefic vs malefic), shown so you can see what it claims — not what the desk found. The desk's tests on
      these names produced no surviving edge, which is the next block.</p>
  </div>`;
}

// (b) the falsification receipt — what the desk actually measured, on THIS name where it has it
function arReceiptBlock(sym, sect, bt) {
  const all = bt?.all_tests || [];
  if (!all.length) return "";
  let rows = all.filter(t => t.subject === sym), scope = `${sym}`, note = `Tested on ${sym}'s own price history.`;
  if (!rows.length && sect) {
    rows = all.filter(t => t.sector === sect);
    const peers = [...new Set(rows.map(t => t.subject))];
    scope = `${sect}`;
    note = `${sym} is not one of the ${bt?.headline?.subjects_tested || "tested"} names with enough history, so this
      is its sector — ${peers.length} peer${peers.length === 1 ? "" : "s"} (${peers.slice(0, 6).join(", ")}${peers.length > 6 ? "…" : ""}).`;
  }
  if (!rows.length) {
    rows = all.filter(t => t.subject === "KSE100 (proxy)");
    scope = "KSE-100";
    note = `Neither ${sym} nor its sector carries enough history, so this is the market proxy.`;
  }
  if (!rows.length) return "";
  const surv = rows.filter(t => t.survives_fdr || t.survives_bonferroni).length;
  const raw = rows.filter(t => t.p_value < 0.05).length;
  const top = [...rows].sort((a, b) => a.p_value - b.p_value).slice(0, 5);
  return `<div class="ar-block">
    <div class="ar-bh"><b>What the desk measured</b><span class="pill ${surv ? "" : "ok"}">${surv} survived</span></div>
    <p class="ar-bp">Every condition below was run against ${esc(String(bt?.window?.trading_days || ""))} trading days
      (${esc(bt?.window?.from)} → ${esc(bt?.window?.to)}), returns beta-adjusted, significance from a permutation test.
      ${esc(note)} <b>${raw}</b> of ${rows.length} looked significant before correcting for how many were tried;
      <b>${surv}</b> survived that correction.</p>
    <div class="ar-tt"><table><thead><tr><th>Condition · ${esc(scope)}</th><th class="r">days</th>
      <th class="r">effect %/day</th><th class="r">p</th><th class="r">survives</th></tr></thead><tbody>
      ${top.map(t => `<tr><td>${esc(t.condition)}${t.subject !== sym ? ` <span class="sub">${esc(t.subject)}</span>` : ""}</td>
        <td class="r num sub">${t.days_in}</td>
        <td class="r num ${t.effect_pct_per_day > 0 ? "up" : "dn"}">${t.effect_pct_per_day > 0 ? "+" : ""}${t.effect_pct_per_day}</td>
        <td class="r num">${t.p_value}</td>
        <td class="r">${t.survives_fdr || t.survives_bonferroni ? '<span class="pill ok">yes</span>' : '<span class="tag">no</span>'}</td></tr>`).join("")}
    </tbody></table></div>
    <p class="ar-bn">${esc(bt?.honesty || "")} Across the whole study ${esc(String(bt?.headline?.hypotheses_tested || ""))} hypotheses
      were tried and ${esc(String(bt?.headline?.survivors_after_fdr ?? "0"))} survived — about what pure chance produces.</p>
  </div>`;
}

// (c) the country's and the market's own charts — slow grahas only, because the birth times are disputed
function arCompareBlock(ctx) {
  const pk = ctx?.reference?.pakistan, ks = ctx?.reference?.kse100;
  if (!pk || !ks) return "";
  const shared = ctx.shared || [];
  const same = shared.filter(r => r.same_sign);
  const cell = (r) => `<div class="ar-cmp">
    <span class="ark">${esc(r.label)} · ${esc(r.date)}</span>
    <b>${Object.entries(r.grahas).map(([b, p]) => `${esc(b)} ${esc(p.sign)}`).join(" · ")}</b>
    <i>Saturn has come back to its birth degree ${r.saturn_return?.completed ?? 0}× ${r.saturn_return?.next
      ? `— the next return falls ${esc(r.saturn_return.next)}` : ""}.</i></div>`;
  return `<div class="ar-block">
    <div class="ar-bh"><b>The weather above it — Pakistan and the KSE-100</b><span class="tag">slow grahas only</span></div>
    <p class="ar-bp">Every PSX name trades inside two older charts. Neither has a known birth TIME, so only Saturn,
      Jupiter, Rahu and Ketu are published — they move too slowly for a day of uncertainty to move their sign.
      The Moon and the ascendant are refused outright.</p>
    <div class="ar-cmpg">${cell({ ...pk, label: "Pakistan" })}${cell({ ...ks, label: "KSE-100" })}</div>
    <p class="ar-bn">${same.length
      ? `The two charts share ${same.map(r => `<b>${esc(r.graha)}</b> in ${esc(r.pakistan_sign)}`).join(" and ")} — the
         classical marker of a linked chart.`
      : "The two charts share no slow-graha sign, so the tradition would read the market's fortunes as running on their own clock rather than the country's."}
      ${esc(pk.time_note)} Comparison shown because the tradition makes it; the desk has measured no market effect from it.</p>
  </div>`;
}

// (d) today's sky, in the exact words the backtest used — the join that makes the null result concrete
function arLiveBlock(sym, sect, ctx, bt) {
  const conds = ctx?.today?.conditions || [];
  if (!conds.length) return `<div class="ar-block"><div class="ar-bh"><b>The sky today</b></div>
    <p class="ar-bp">No tested condition is active today — the sky is, by the desk's own vocabulary, quiet.</p></div>`;
  const all = bt?.all_tests || [];
  const scoped = c => {
    const mine = all.filter(t => t.condition === c && t.subject === sym);
    if (mine.length) return { rows: mine, who: sym };
    const sec = sect ? all.filter(t => t.condition === c && t.sector === sect) : [];
    if (sec.length) return { rows: sec, who: sect };
    return { rows: all.filter(t => t.condition === c && t.subject === "KSE100 (proxy)"), who: "the KSE-100" };
  };
  return `<div class="ar-block">
    <div class="ar-bh"><b>The sky today, and what it was worth</b><span class="tag">${conds.length} condition${conds.length > 1 ? "s" : ""} live</span></div>
    <p class="ar-bp">These are live right now, named exactly as the desk's study named them — so the claim and the
      measurement sit on the same line instead of on different pages.</p>
    <div class="ar-live">
      ${conds.map(c => { const { rows, who } = scoped(c.condition);
        const eff = rows.length ? (rows.reduce((s, t) => s + t.effect_pct_per_day, 0) / rows.length) : null;
        const best = rows.length ? Math.min(...rows.map(t => t.p_value)) : null;
        const survived = rows.some(t => t.survives_fdr || t.survives_bonferroni);
        return `<div class="ar-lrow">
          <span class="ar-lc">${esc(c.condition)}</span>
          <span class="ar-ld">${esc(c.detail)}</span>
          <span class="ar-lm">${eff === null ? '<i class="sub">not tested</i>'
            : `<em class="${eff > 0 ? "up" : "dn"}">${eff > 0 ? "+" : ""}${eff.toFixed(3)}%/day</em>
               <i>on ${esc(who)} · best p ${best} · ${survived ? "survived" : "did not survive"} correction</i>`}</span>
        </div>`; }).join("")}
    </div>
    <p class="ar-bn">Measured effects this small, at these p-values, are what a fair coin looks like when you flip it
      ${esc(String(bt?.headline?.hypotheses_tested || "thousands of"))} times. Shown so the tradition's claim can be
      checked against the record rather than taken on trust.</p>
  </div>`;
}

function composeAstroReading(sym, data) {
  const { natal, sky, amap, sectors, uni, bt, ctx } = data;
  const subj = natal?.subjects?.[sym];
  const name = uni?.symbols?.[sym]?.name || "";
  const sect = (sectors?.tickers?.[sym] || {}).sector;
  const domains = b => ((amap?.grahas?.[b] || {}).domains || []).slice(0, 3).join(", ");
  const skyPos = sky?.positions || {};
  const events14 = (sky?.events || []).filter(e => e.importance >= 3 && e.date <= new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10)).slice(0, 3);

  if (subj) {
    const moon = subj.natal?.Moon || {};
    const das = subj.dasha?.current || {};
    const ts = subj.time_sensitivity || {};
    const ss = subj.sade_sati || {};
    const hits = (subj.transits_to_natal || []).slice(0, 3);
    const natPos = subj.natal;
    return `
      <div class="ar-head"><b>${esc(sym)}</b><span class="sub">${esc(name.slice(0, 34))}</span>
        <span class="pill ok">natal chart</span></div>
      <div class="ar-birth sub">${esc(sym)}'s chart, cast for its first trade on ${esc(subj.birth?.date)}. Sidereal, Lahiri.</div>
      ${zodiacStrip(skyPos, natPos)}
      <div class="ar-grid">
        <div class="ar-cell"><span class="ark">Natal Moon</span><b>${esc(moon.sign)} · ${esc(moon.nakshatra)}</b>
          <i>Read from the Moon — the Chandra lagna, the mind of the chart.</i></div>
        <div class="ar-cell"><span class="ark">The period (dasha)</span><b>${pixelGlyph(das.maha, 16)} ${esc(das.maha || "—")}${das.antar ? ` / ${esc(das.antar)}` : ""}</b>
          <i>${das.maha ? `A ${esc(das.maha)} maha-dasha, running to ~${esc(String(das.maha_to || "").slice(0, 7))}. Tradition ties ${esc(das.maha)} to ${esc(domains(das.maha))}.` : "—"}</i></div>
        <div class="ar-cell"><span class="ark">Saturn's passage</span><b>${ss.active ? "SADE SATI · " + esc((ss.phase || "").split(" (")[0]) : ss.phase ? esc(ss.phase.split(" (")[0]) : "quiet"}</b>
          <i>${ss.active ? "Saturn is crossing the natal Moon's neighbourhood — the seven-and-a-half-year passage the tradition treats as its heaviest weather." : "No Sade Sati running on this chart."}</i></div>
        <div class="ar-cell"><span class="ark">On this chart now</span><b>${hits.length ? hits.map(h => `${GRAHA_AB[h.transiting]}→${GRAHA_AB[h.over_natal]}`).join(" · ") : "no tight contacts"}</b>
          <i>${hits.length ? hits.map(h => `transiting ${esc(h.transiting)} sits on natal ${esc(h.over_natal)} (${h.orb_deg}°)`).join("; ") + "." : "No transiting graha within 3° of a natal point today."}</i></div>
      </div>
      <div class="ar-read">
        <p><b>The days ahead:</b> ${events14.length ? `the sky's next marks are ${events14.map(e => `${esc(e.text)} (${esc(e.date)})`).join("; ")}.` : "no high-rank sky events in the next two weeks."} ${hits.length ? `Tradition would watch the ${esc(hits[0].transiting)}–natal-${esc(hits[0].over_natal)} contact most closely.` : ""}</p>
        <p><b>The months:</b> ${das.antar ? `the running sub-period is ${esc(das.antar)} (to ~${esc(String(das.antar_to || "").slice(0, 7))}) — tradition colours these months with ${esc(domains(das.antar))}.` : ""}</p>
        <p><b>The years:</b> ${das.maha ? `the ${esc(das.maha)} maha-dasha frames the longer arc.` : "—"}</p>
      </div>
      ${arDashaBlock(subj.dasha, amap, `${sym}'s chart`)}
      ${arReceiptBlock(sym, sect, bt)}
      ${arLiveBlock(sym, sect, ctx, bt)}
      ${arCompareBlock(ctx)}
      <p class="ar-caveat">The tradition's reading of ${esc(sym)}'s chart, set beside what the desk measured — for
        exploration, not advice. Nothing here is a buy, sell or hold, a target or a stop.</p>`;
  }
  // read through the sector's ruling planet — a mundane-astrology technique in its own right
  const sig = sect ? (amap?.sector_significators?.[sect] || {}) : {};
  const prim = sig.primary;
  const p = prim ? skyPos[prim] : null;
  const mkt = natal?.subjects?.KSE100;
  const mdas = mkt?.dasha?.current || {};
  return `
    <div class="ar-head"><b>${esc(sym)}</b><span class="sub">${esc(name.slice(0, 34))}</span>
      <span class="pill">sector reading</span></div>
    <div class="ar-birth sub">${prim ? `The tradition reads ${esc(sym)} through ${esc(sect)}, and its ruling planet ${esc(prim)}.` : `${esc(sym)} read against the market's own chart.`}</div>
    ${zodiacStrip(skyPos, null)}
    <div class="ar-grid">
      ${prim ? `<div class="ar-cell"><span class="ark">Ruling planet</span><b>${pixelGlyph(prim, 16)} ${esc(prim)}</b>
        <i>${esc(prim)} governs ${esc(sect)} — ${esc(domains(prim))}. Right now it moves through ${esc(p?.sign || "—")}, ${esc(p?.nakshatra || "—")}${p?.retrograde ? ", retrograde" : ""}.</i></div>` : ""}
      <div class="ar-cell"><span class="ark">The market's chart</span><b>KSE-100 · ${esc(mdas.maha || "—")}${mdas.antar ? "/" + esc(mdas.antar) : ""} period</b>
        <i>The index's chart, born 1991, is the weather every PSX name trades inside${mkt?.sade_sati?.active ? " — and it is running Sade Sati" : ""}.</i></div>
    </div>
    ${arDashaBlock(mkt?.dasha, amap, "the KSE-100's own chart, which every PSX name trades inside,")}
    ${arReceiptBlock(sym, sect, bt)}
    ${arLiveBlock(sym, sect, ctx, bt)}
    ${arCompareBlock(ctx)}
    <p class="ar-caveat">${esc(sym)} has no birth chart on the desk — no first-trade date the ephemeris can be cast
      for — so this is read through its sector's ruling planet and the market's own chart. For exploration, not
      advice. Nothing here is a buy, sell or hold, a target or a stop.</p>`;
}

/* ---------- the run: 10–20s of real computation narrated, then the readings reveal ---------- */
async function playAstroBoardRun() {
  const board = astroBoard();
  if (!board.length) return;
  const [natal, sky, amap, sectors, uni, bt, ctx] = await Promise.all([
    j("astro_natal.json"), j("astro.json"), j("astro_map.json"), j("sectors.json"), j("universe.json"),
    j("astro_backtest.json"), j("astro_context.json")]);
  const data = { natal, sky, amap, sectors, uni, bt, ctx };
  const verified = board.filter(s => natal?.subjects?.[s]);
  const ayan = sky?.system?.ayanamsa_deg;

  const steps = [
    `Computing the sidereal sky — Lahiri ayanamsa <b>${esc(ayan)}°</b>, derived from Spica`,
    ...board.map(s => natal?.subjects?.[s]
      ? `Casting <b>${esc(s)}</b>'s birth chart — first trade ${esc(natal.subjects[s].birth?.date)}, Karachi open`
      : `<b>${esc(s)}</b> — reading through its sector's ruling planet`),
    ...verified.slice(0, 3).map(s => `Vimshottari — balancing the ${esc(natal.subjects[s].dasha?.current?.maha || "")} period from the natal Moon's nakshatra`),
    `Checking Saturn against every natal Moon — Sade Sati scan`,
    `Scanning transits to natal points (3° orb)`,
    `Composing the readings — tradition's words, the desk's tests attached`,
  ];

  runRevealModal({
    sym: "", kicker: "The astro desk · your charts",
    title: `Casting ${board.length} chart${board.length > 1 ? "s" : ""} against today's sky`,
    sub: `Real ephemeris math — sidereal positions, Vimshottari periods, Saturn's passage — for every name on your board, read the way the tradition would.`,
    steps,
    onReveal: () => { try { board.forEach(s => sessionStorage.setItem("astroran:" + s, "1")); } catch (e) { /* private */ } },
    onClose: () => { if (routeHash().replace(/^#\/?/, "").startsWith("astro")) pageAstro(); },
    renderReveal: (bodyEl) => {
      bodyEl.innerHTML = `<div class="rp-reveal">
        <div class="rp-reveal-head"><b>Your charts · ${board.map(esc).join(" · ")}</b><span>read sidereal, Lahiri ${esc(ayan)}° — the tradition's reading of each name</span></div>
        ${board.map(s => `<div class="card ar-card" style="margin-top:10px">${composeAstroReading(s, data)}</div>`).join("")}
        <div class="rp-reveal-foot"><span>The tradition's reading — for exploration, not advice.</span>
          <span class="rp-foot-btns"><button class="rp-btn2" data-a="replay">↻ Replay</button></span></div>
      </div>`;
    },
  });
}

/* ==========================================================================================
   YOUR CHART — the personal financial-astrology journey. A user casts their own birth chart and
   the tradition reads the whole PSX universe against it. Framed throughout as astrological
   exploration, never advice: "the tradition finds your chart harmonious with X", never "buy X".
   ========================================================================================== */
/* --- the funnel: casting a chart needs NO account. computeNatal() is pure client-side math over
   an ephemeris table the browser already fetches, so a guest can cast, see their real chart and a
   taste of the market read. The account is what PERSISTS it; the subscription is what unlocks the
   full map and the daily sky against it. A guest chart lives in localStorage and is migrated up to
   the profile on sign-in (GUEST_KEY), so nobody ever types their birth details twice. --- */
/* ==========================================================================================
   LANGUAGE — English / اردو. A plain client-side dictionary, so switching is instant with no
   network call and no rebuild. Scope: the interface, the Investor-desk surfaces and the
   disclaimers are translated via the exact-string dictionary (UR_STRINGS/translateTree, below).

   Dynamic agent prose (daily read, Room debates, macro, news, sector debates) has no fixed
   dictionary entry — it's new every cycle — so it's translated separately, near generation time,
   by a dedicated agent (.claude/agents/state-translator.md) that is fact-blind by construction
   (Read/Write tools only, no data-layer or market access): it only reworks English prose already
   written by the source agent into a `<field>_ur` sibling in the same state/*.json file. tp()/
   tpArr() below read that sibling at render time, falling back to English if absent. This is a
   separate path from translateTree() and does not touch it.
   ========================================================================================== */
const LANG_KEY = "psx_lang";
// Corpus lives in i18n-ur.js (loaded before this file) so it can grow into full-page coverage
// without bloating app.js. Empty object fallback keeps the app from crashing if that file 404s.
const UR = window.UR_STRINGS || {};
function lang() {
  try { return localStorage.getItem(LANG_KEY) === "ur" ? "ur" : "en"; } catch { return "en"; }
}
function t(s) { return lang() === "ur" ? (UR[s] || s) : s; }
/* Agent-prose translation (Layer 5). Reads the `<field>_ur` sibling a source agent's cycle wrote
   into state/*.json (via .claude/agents/state-translator.md), falling back to English if the
   field hasn't been translated yet (or ever). Separate from t()/UR_STRINGS above — those are the
   static-chrome exact-string dictionary; this is per-record dynamic prose. */
function tp(obj, field) {
  if (!obj) return "";
  if (lang() === "ur" && obj[field + "_ur"]) return obj[field + "_ur"];
  return obj[field] || "";
}
function tpArr(obj, field) {
  if (!obj) return [];
  if (lang() === "ur" && Array.isArray(obj[field + "_ur"])) return obj[field + "_ur"];
  return Array.isArray(obj[field]) ? obj[field] : [];
}
/* Disclaimer text is legal-sensitive — NOT LLM-translated. One static, human-reviewed Urdu
   string, swapped in directly (no _ur sibling, no state-translator involvement). */
const DAILY_READ_DISCLAIMER_UR = "تحقیق ہے، مشورہ نہیں۔ ڈیسک اشارے تیار کرتا ہے؛ خود آرڈر نہیں دیتا۔ نقصان متوقع ہے۔";
function tDisclaimer(dr) {
  if (lang() === "ur") return DAILY_READ_DISCLAIMER_UR;
  return dr.disclaimer || "Research, not advice.";
}
function setLang(l) {
  try { localStorage.setItem(LANG_KEY, l); } catch { /* private mode */ }
  applyLang();
  if (me) saveProfile({ lang: l });     // follows the account across devices
  if (typeof route === "function") route(true);
}
/* Translate the static chrome (nav labels, badges) in place, and flag the language on <body> so
   CSS can switch font + text direction for Urdu. Page bodies re-render via route(). */
function applyLang() {
  const l = lang();
  document.body.dataset.lang = l;
  document.documentElement.setAttribute("dir", l === "ur" ? "rtl" : "ltr");
  document.querySelectorAll("[data-nav] span").forEach(s => {
    if (!s.dataset.en) s.dataset.en = s.textContent;
    s.textContent = l === "ur" ? (UR[s.dataset.en] || s.dataset.en) : s.dataset.en;
  });
  /* The rail tabs are static markup outside #view, so translateTree — which runs on a page
     render — never reaches them, and they sat in English while the nav beside them switched.
     Same snapshot-and-restore shape as the nav above: the English original is stashed once in
     data-en, which is what makes switching BACK to English work. translateTree only mutates
     in the Urdu direction, so anything it touched outside a re-rendered subtree would be
     stuck in Urdu. */
  document.querySelectorAll("[data-rail-tab]").forEach(b => {
    if (!b.dataset.en) b.dataset.en = b.textContent;
    b.textContent = l === "ur" ? (UR[b.dataset.en] || b.dataset.en) : b.dataset.en;
  });
  const badge = document.querySelector(".research-badge");
  if (badge) { if (!badge.dataset.en) badge.dataset.en = badge.textContent; badge.textContent = t(badge.dataset.en); }
  const sb = document.querySelector(".searchbtn .sb-label");
  if (sb) { if (!sb.dataset.en) sb.dataset.en = sb.textContent; sb.textContent = t(sb.dataset.en); }
  const btn = document.getElementById("langBtn");
  if (btn) btn.textContent = l === "ur" ? "EN" : "اردو";
}

/* ==========================================================================================
   FULL-PAGE TRANSLATION.
   applyLang() above only touches the static chrome (nav labels, badges) because those never
   get replaced by route(). Everything else is rebuilt fresh from English string templates on
   every render, so translating it is a walk-and-replace pass over the rendered DOM rather than
   a template change — far cheaper than threading a translated string through ~40 render
   functions. translateTree() runs after every render (piggybacked on the render-observer
   further down this file) and is one-directional: EN -> UR only. It never restores English,
   because a language switch calls route(true), which rebuilds the DOM from the English
   template strings again, so the next pass simply has fresh English to translate.

   ?i18n=audit on the URL turns on a silent harvester alongside it: every candidate string that
   has no UR[] entry gets counted in window.__i18nMisses, regardless of the current language, so
   coverage can be checked while browsing in English (fastest) or hunted for leftovers while
   browsing in Urdu. Click the on-page badge (or call i18nAuditReport() in the console) to dump
   the list, sorted by how often each miss occurred. */
const I18N_SKIP_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "SVG", "PATH", "CODE", "PRE"]);
const I18N_ATTRS = ["placeholder", "title", "aria-label"];
// Pure numbers/punctuation/currency and short ALL-CAPS tokens (tickers, PE/EPS/NAV-style
// acronyms) are never translatable — leave them alone and keep them out of the audit noise.
const I18N_SKIP_RE = /^[\s\d.,:/%+\-–—()₨$KMBkmb ]*$/;
const I18N_TICKER_RE = /^[A-Z][A-Z0-9&.\-]{1,9}$/;
// translateTree re-walks the whole root on every render, so a node it already turned into Urdu
// on a prior pass comes back through here again. UR[] only maps EN -> UR, so an Urdu string
// always misses that lookup — without this check it gets logged as a false "missing" entry in
// audit mode every time anything else on the page re-renders.
const I18N_URDU_RE = /[؀-ۿ]/;

function i18nAuditOn() {
  try { return new URLSearchParams(location.search).get("i18n") === "audit"; } catch { return false; }
}
window.__i18nMisses = window.__i18nMisses || new Map();   // text -> occurrence count, audit mode only

function i18nCandidate(raw) {
  const v = raw.trim();
  if (v.length < 2) return false;
  if (I18N_SKIP_RE.test(v)) return false;
  if (I18N_TICKER_RE.test(v)) return false;
  if (I18N_URDU_RE.test(v)) return false;
  return true;
}
function i18nTranslateOne(raw) {
  const v = raw.trim();
  if (UR[v]) return raw.replace(v, UR[v]);
  if (i18nAuditOn() && i18nCandidate(v)) window.__i18nMisses.set(v, (window.__i18nMisses.get(v) || 0) + 1);
  return raw;
}
function translateTree(root = document.body) {
  if (!root) return;
  const audit = i18nAuditOn();
  const isUr = lang() === "ur";
  if (!isUr && !audit) return;   // nothing to do in English outside audit mode
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const p = node.parentElement;
      if (!p || I18N_SKIP_TAGS.has(p.tagName) || p.closest("[data-no-i18n]")) return NodeFilter.FILTER_REJECT;
      return i18nCandidate(node.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    }
  });
  const nodes = [];
  let n;
  while ((n = walker.nextNode())) nodes.push(n);
  nodes.forEach(node => {
    if (isUr) node.nodeValue = i18nTranslateOne(node.nodeValue);
    else i18nTranslateOne(node.nodeValue);   // audit-only: harvest, never mutate English DOM
  });
  root.querySelectorAll?.("[placeholder],[title],[aria-label]").forEach(el => {
    if (el.closest("[data-no-i18n]")) return;
    I18N_ATTRS.forEach(attr => {
      const v = el.getAttribute(attr);
      if (!v || !i18nCandidate(v)) return;
      if (isUr) el.setAttribute(attr, i18nTranslateOne(v));
      else i18nTranslateOne(v);
    });
  });
  if (audit) i18nAuditPaint();
}
let _i18nAuditT = null;
function i18nAuditPaint() {
  clearTimeout(_i18nAuditT);
  _i18nAuditT = setTimeout(() => {
    let badge = document.getElementById("i18nAuditBadge");
    if (!badge) {
      badge = document.createElement("div");
      badge.id = "i18nAuditBadge";
      badge.setAttribute("data-no-i18n", "1");
      badge.style.cssText = "position:fixed;bottom:10px;right:10px;z-index:9999;background:#c0392b;"
        + "color:#fff;font:12px/1.4 monospace;padding:6px 10px;cursor:pointer;box-shadow:0 2px 10px rgba(0,0,0,.4)";
      badge.title = "Click to dump untranslated strings to console";
      badge.addEventListener("click", () => window.i18nAuditReport());
      document.body.appendChild(badge);
    }
    badge.textContent = `i18n audit: ${window.__i18nMisses.size} untranslated`;
  }, 200);
}
window.i18nAuditReport = function i18nAuditReport() {
  const rows = [...window.__i18nMisses.entries()].sort((a, b) => b[1] - a[1]).map(([text, count]) => ({ text, count }));
  console.table(rows);
  console.log(JSON.stringify(rows.map(r => r.text), null, 2));
  return rows;
};

const GUEST_KEY = "psx_guest_chart";
function guestChart() {
  try { return JSON.parse(localStorage.getItem(GUEST_KEY) || "null"); } catch { return null; }
}
function setGuestChart(o) {
  try { o ? localStorage.setItem(GUEST_KEY, JSON.stringify(o)) : localStorage.removeItem(GUEST_KEY); } catch { /* private mode */ }
}
function birthData() { return (me && myProfile && myProfile.birth_data) || guestChart()?.birth_data || null; }
function natalChart() { return (me && myProfile && myProfile.natal_chart) || guestChart()?.natal_chart || null; }
function astroPrefs() { return (me && myProfile && myProfile.astro_prefs) || guestChart()?.astro_prefs || {}; }

/* ==========================================================================================
   PLANS — three desks for three kinds of user, plus the free tier everyone starts on.
   Payment is NOT wired: there is no Stripe in Pakistan, so a local gateway (PayFast or similar)
   comes later. Until then `plan` is set by the desk owner and the DB refuses client writes to it
   (see the freeze_plan / force_free_plan triggers). BILLING_LIVE is the ONE switch: while false,
   any signed-in account reads as subscribed, so gating cannot strip access from existing accounts.
   ========================================================================================== */
const BILLING_LIVE = false;
const FREE_MATCHES = 3;                       // how many resonance cards a guest sees in full
const PLANS = {
  free: { label: "Free", tag: "", blurb: "Cast your chart, read the daily desk note, and follow the public track record.",
    features: [] },
  // NOT "Learner" — a paid tier should be named for what the user becomes, not for what they lack.
  investor: { label: "Investor", tag: "start here",
    blurb: "Become an investor who reads for themselves. The guided journey from 'why invest' to your first practice position — on real PSX filings and real prices.",
    features: ["learn", "practice", "tools", "astro_full", "dividends_full", "earnings_full"] },
  pro: { label: "Pro", tag: "TA & FA",
    blurb: "The full desk. Tested strategies, model fair value, the research library, and every lens the desk runs.",
    features: ["learn", "practice", "tools", "astro_full", "dividends_full", "earnings_full", "value_full", "strategies_run", "research_full", "screener", "scenarios", "scanner", "watch_intel", "ask", "alignment", "xray", "marketplace"] },
  // Feature list intentionally EMPTY while the tier is unbuilt. Listing seventeen inherited Pro
  // features next to a "coming soon" badge reads as a spec of what you get today, and none of it
  // is purchasable — the honest card is the promise plus nothing else until the tier ships.
  broker: { label: "Broker", tag: "coming soon", soon: true,
    blurb: "Everything in Pro, plus your own desk's calls scored in public on the same bar as everyone else.",
    features: [] },
};
/* `free` stays here and stays FIRST: it is the internal default that realPlan() falls back to for
   any signed-in account without a stored plan, and hasFeature() reads PLANS[planOf()].features.
   Removing the entry would leave those undefined and break entitlement for every user. What the
   owner asked to remove is the free CARD, not the free CONCEPT — see PLAN_CARDS. */
const PLAN_ORDER = ["free", "investor", "pro", "broker"];
/* The tiers actually shown on the plans page. Free is not offered as a choice: there is nothing
   to select (every account starts there) and a fourth column of three bullets made the paid
   tiers look like the exception rather than the product. */
const PLAN_CARDS = ["investor", "pro", "broker"];
/* Owner-only: preview the product as any plan without changing the stored plan. Set from the Plans
   page; lives in memory only, so a reload returns you to your real plan. */
let _previewPlan = null;
function realPlan() { return (me && myProfile && myProfile.plan) || "free"; }
function isOwner() { return !!(me && (me.email || "").toLowerCase() === "mwasayi@gmail.com"); }
function planOf() { return (_previewPlan && isOwner()) ? _previewPlan : realPlan(); }
/* While BILLING_LIVE is false every signed-in account behaves as Pro — nobody loses what they have
   today. Once it flips, access is decided purely by the plan's feature list. */
function hasFeature(key) {
  if (!me) return false;
  // While previewing, judge by the previewed plan — that is the entire point of the preview.
  if (!BILLING_LIVE && !(_previewPlan && isOwner())) return true;
  return (PLANS[planOf()]?.features || []).includes(key);
}
function isSubscribed() {
  if (!me) return false;
  if (_previewPlan && isOwner()) return planOf() !== "free";
  return !BILLING_LIVE || planOf() !== "free";
}
/* Which product shell to render. The Investor desk is a different information architecture, not a
   reskin, so it gets its own nav and home. Pros/brokers see the full desk. */
function deskMode() {
  if (!me) return "pro";
  if (planOf() === "investor") return "learn";
  return (myProfile && myProfile.ui_mode === "learn") ? "learn" : "pro";
}

/* The one paywall card, used on every gated page. Language is fixed: the thing sits in "the paid
   plan" (plans being drawn for three desks — new investors, pros, brokers). Never scare copy;
   always name exactly what's behind the wall. Returns "" for subscribers so call sites can inline it. */
function planWall(what, teaser) {
  if (isSubscribed()) return "";
  return `<div class="card plan-wall">
    <div class="mc-lock-kick">part of the paid plan</div>
    <h3>${what}</h3>
    <p class="sub">${teaser}</p>
    <p class="sub">${me
      ? "This sits in the paid plan. Plans are being drawn for three desks — new investors, pros, and brokers."
      : "Create a free account to start exploring. Three desks are being drawn: new investors, pros, and brokers."}</p>
    <button class="bw-go" style="max-width:250px" onclick="${me ? "navigate('/settings')" : "openAuth('signup')"}">${me ? "See plans →" : "Create a free account →"}</button>
  </div>`;
}

/* Called on sign-in: lift a guest's chart into their profile so the details survive the account
   boundary. Never clobbers a chart already on the profile. */
async function migrateGuestChart() {
  const g = guestChart();
  if (!me || !g || !g.natal_chart) return false;
  if (myProfile && myProfile.birth_data) { setGuestChart(null); return false; }  // profile wins
  const patch = { birth_data: g.birth_data, natal_chart: g.natal_chart, astro_prefs: g.astro_prefs || {} };
  const err = await saveProfile(patch);
  if (!err) { setGuestChart(null); markActivated("cast_migrated"); return true; }  // guest cast never called markActivated — mark retroactively at sign-in
  return false;
}

const _bw = { step: 0, data: {} };
const BW_STEPS = ["intro", "date", "time", "place", "goals", "cast"];
function openBirthWizard() {
  _bw.step = 0; _bw.data = { ...(birthData() || {}) };
  renderBirthWizard();
}
function bwClose() { document.querySelector(".bw-overlay")?.remove(); }
async function clearBirthData() {
  if (!confirm("Remove your birth details and chart? You can add them again any time.")) return;
  setGuestChart(null);
  if (me) {
    myProfile = { ...(myProfile || {}), birth_data: null, natal_chart: null };
    await saveProfile({ birth_data: null, natal_chart: null });
  }
  if (typeof pageSettings === "function") pageSettings();
}
function bwNext() { if (_bw.step < BW_STEPS.length - 1) { _bw.step++; renderBirthWizard(); } }
function bwBack() { if (_bw.step > 0) { _bw.step--; renderBirthWizard(); } }
function bwSet(k, v) { _bw.data[k] = v; }
function bwCommitDate() {
  const dd = +document.getElementById("bw-dd").value, mm = +document.getElementById("bw-mm").value, yyyy = +document.getElementById("bw-yyyy").value;
  if (!dd || !mm || !yyyy || String(yyyy).length !== 4) return;
  if (mm < 1 || mm > 12 || dd < 1 || dd > 31) return;
  // calendar-aware: 31 Feb passes the range check above, then Date.UTC() silently rolls it to
  // 3 March and the natal chart is computed for a day the user never entered. Reject instead.
  const probe = new Date(Date.UTC(yyyy, mm - 1, dd));
  if (probe.getUTCMonth() !== mm - 1 || probe.getUTCDate() !== dd) return;
  bwSet("date", `${yyyy}-${bwPad2(mm)}-${bwPad2(dd)}`);
  bwNext();
}
function bwCommitTime() {
  const known = _bw.data.time_known !== false;
  if (!known) { bwSet("time", "12:00"); bwNext(); return; }
  const hh = document.getElementById("bw-hh").value, mi = document.getElementById("bw-mi").value;
  if (hh === "" || mi === "") return;
  if (+hh < 0 || +hh > 23 || +mi < 0 || +mi > 59) return;
  bwSet("time", `${bwPad2(+hh)}:${bwPad2(+mi)}`);
  bwNext();
}
function bwPad2(n) { return String(n).padStart(2, "0"); }
// Fixed-length numeric box (DD/MM/YYYY/HH/MI). A single native "input" event can carry more than
// one keystroke (fast typing, IME, mobile coalescing) — slicing to maxLen and stopping there drops
// the overflow digits. Fix: split on overflow, keep this box's own digits, forward the remainder
// into `next` and re-dispatch "input" on it so excess cascades through instead of being lost.
function bindDigitBox(box, maxLen, next) {
  box.addEventListener("input", () => {
    let digits = box.value.replace(/\D/g, ""), overflow = "";
    if (digits.length > maxLen) { overflow = digits.slice(maxLen); digits = digits.slice(0, maxLen); }
    box.value = digits;
    try { box.setSelectionRange(box.value.length, box.value.length); } catch {}
    if (digits.length !== maxLen || !next) return;
    if (overflow) { next.value = overflow + next.value; next.focus(); next.dispatchEvent(new Event("input", { bubbles: true })); }
    else next.focus();
  });
}

function renderBirthWizard() {
  let ov = document.querySelector(".bw-overlay");
  if (!ov) { ov = document.createElement("div"); ov.className = "bw-overlay"; document.body.appendChild(ov);
    ov.addEventListener("click", e => { if (e.target === ov) bwClose(); }); }
  const s = BW_STEPS[_bw.step], d = _bw.data;
  const dots = BW_STEPS.slice(1, 5).map((_, i) => `<span class="bw-dot ${_bw.step - 1 === i ? "on" : _bw.step - 1 > i ? "did" : ""}"></span>`).join("");
  let body = "";
  if (s === "intro") body = `
    <div class="bw-kick">Your chart × the market</div>
    <h2 class="bw-h">The sky you were born under, read against every stock on the exchange.</h2>
    <p class="bw-p">Give the desk your birth details and it casts your Vedic (sidereal) chart, then reads the whole PSX universe against it the way the tradition would — which names your chart runs <b>harmonious</b> with, which it finds <b>testing</b>, and the periods your own dasha lights up.</p>
    <p class="bw-note">A note in plain sight: this is <b>astrological exploration</b>, not investment advice — a lens to explore, never a reason to buy. ${me
      ? "Your birth details stay private to your account."
      : "No account needed — your chart is cast in your browser and your birth details stay on this device until you choose to save them."}</p>
    <button class="bw-go" onclick="bwNext()">Begin →</button>`;
  else if (s === "date") { const [dY, dM, dD] = (d.date || "").split("-"); body = `
    <div class="bw-kick">Step 1 of 4 · ${dots}</div>
    <h2 class="bw-h">When were you born?</h2>
    <p class="bw-p">The date sets your planets. Everything else refines it.</p>
    <div class="bw-digitrow">
      <div class="bw-digitfield"><label for="bw-dd">Day</label><input type="text" inputmode="numeric" enterkeyhint="next" autocomplete="off" maxlength="2" class="bw-digit" id="bw-dd" placeholder="DD" value="${esc(dD || "")}"></div>
      <div class="bw-digitfield"><label for="bw-mm">Month</label><input type="text" inputmode="numeric" enterkeyhint="next" autocomplete="off" maxlength="2" class="bw-digit" id="bw-mm" placeholder="MM" value="${esc(dM || "")}"></div>
      <div class="bw-digitfield"><label for="bw-yyyy">Year</label><input type="text" inputmode="numeric" enterkeyhint="next" autocomplete="off" maxlength="4" class="bw-digit bw-digit-y" id="bw-yyyy" placeholder="YYYY" value="${esc(dY || "")}"></div>
    </div>
    <div class="bw-nav"><button class="bw-back" onclick="bwBack()">← back</button><button class="bw-go" onclick="bwCommitDate()">Next →</button></div>`; }
  else if (s === "time") { const [tH, tM] = (d.time || "").split(":"); body = `
    <div class="bw-kick">Step 2 of 4 · ${dots}</div>
    <h2 class="bw-h">What time?</h2>
    <p class="bw-p">Your birth time sets the fast-moving Moon and your rising sign (ascendant). The more exact, the sharper the reading.</p>
    <div class="bw-digitrow">
      <div class="bw-digitfield"><label for="bw-hh">Hour</label><input type="text" inputmode="numeric" enterkeyhint="next" autocomplete="off" maxlength="2" class="bw-digit" id="bw-hh" placeholder="HH" value="${esc(tH || "")}" ${d.time_known === false ? "disabled" : ""}></div>
      <div class="bw-digitfield"><label for="bw-mi">Minute</label><input type="text" inputmode="numeric" enterkeyhint="next" autocomplete="off" maxlength="2" class="bw-digit" id="bw-mi" placeholder="MM" value="${esc(tM || "")}" ${d.time_known === false ? "disabled" : ""}></div>
    </div>
    <label class="bw-check"><input type="checkbox" ${d.time_known === false ? "checked" : ""} onchange="bwSet('time_known',!this.checked);const hh=document.getElementById('bw-hh'),mi=document.getElementById('bw-mi');hh.disabled=mi.disabled=this.checked;if(this.checked){bwSet('time','12:00')}"> I don't know my birth time</label>
    <p class="bw-note">${d.time_known === false ? "No problem — your Moon sign anchors the reading, the way Vedic astrology reads a chart from the Moon (Chandra lagna)." : "Even an approximate time sharpens your rising sign. If you don't know it, tick the box above."}</p>
    <div class="bw-nav"><button class="bw-back" onclick="bwBack()">← back</button><button class="bw-go" onclick="bwCommitTime()">Next →</button></div>`; }
  else if (s === "place") body = `
    <div class="bw-kick">Step 3 of 4 · ${dots}</div>
    <h2 class="bw-h">Where?</h2>
    <p class="bw-p">Your birthplace fixes the horizon for your rising sign.</p>
    <input class="bw-in combo-city" id="bw-place" type="search" enterkeyhint="search" placeholder="Start typing a city…" autocomplete="off" value="${esc(d.place || "")}">
    <div id="bw-place-pop" class="bw-city-pop"></div>
    <div class="bw-tzrow"><label>UTC offset at birth <input type="text" inputmode="decimal" enterkeyhint="done" class="bw-tz" id="bw-tz" value="${d.tz ?? 5}" onchange="bwSet('tz',+this.value)"></label>
      <span class="bw-note" style="margin:0">set from the city; adjust if you were born during daylight-saving</span></div>
    <div class="bw-nav"><button class="bw-back" onclick="bwBack()">← back</button><button class="bw-go" onclick="if(_bw.data.lat!=null){bwNext()}else{document.getElementById('bw-place').focus()}">Next →</button></div>`;
  else if (s === "goals") body = `
    <div class="bw-kick">Almost there</div>
    <h2 class="bw-h">What are you here to explore?</h2>
    <p class="bw-p">This only colours the language of your reading — pick what fits, or skip.</p>
    <div class="bw-opts">${[["growth", "Long-term growth"], ["income", "Dividend income"], ["trading", "Active trading"], ["curious", "Just curious"]].map(([k, l]) => `<button class="bw-opt ${d.goal === k ? "on" : ""}" onclick="bwSet('goal','${k}');document.querySelectorAll('.bw-opt').forEach(b=>b.classList.remove('on'));this.classList.add('on')">${l}</button>`).join("")}</div>
    <div class="bw-nav"><button class="bw-back" onclick="bwBack()">← back</button><button class="bw-go" onclick="bwNext()">See my chart →</button></div>`;
  else if (s === "cast") { renderBirthCast(ov); return; }
  ov.innerHTML = `<div class="bw-box"><button class="bw-x" aria-label="Close" title="Close" onclick="bwClose()">✕</button>${body}</div>`;
  if (s === "place") wireCityCombo();
  if (s === "date") setTimeout(() => { document.getElementById("bw-dd")?.focus(); bindDigitBox(document.getElementById("bw-dd"), 2, document.getElementById("bw-mm")); bindDigitBox(document.getElementById("bw-mm"), 2, document.getElementById("bw-yyyy")); bindDigitBox(document.getElementById("bw-yyyy"), 4, null); }, 40);
  if (s === "time") setTimeout(() => { bindDigitBox(document.getElementById("bw-hh"), 2, document.getElementById("bw-mi")); bindDigitBox(document.getElementById("bw-mi"), 2, null); }, 40);
}

async function wireCityCombo() {
  const cd = await j("cities.json");
  const inp = document.getElementById("bw-place"), pop = document.getElementById("bw-place-pop");
  if (!inp) return;
  const render = q => {
    q = (q || "").toLowerCase().trim();
    const hits = (q ? (cd.cities || []).filter(c => c.name.toLowerCase().includes(q)) : (cd.cities || [])).slice(0, 30);
    pop.innerHTML = hits.map(c => `<div class="bw-city" data-name="${esc(c.name)}" data-lat="${c.lat}" data-lon="${c.lon}" data-tz="${c.tz}"><b>${esc(c.name)}</b><span>${esc(c.cc)}</span></div>`).join("");
    pop.style.display = hits.length ? "block" : "none";
  };
  inp.addEventListener("focus", () => render(inp.value));
  inp.addEventListener("input", () => render(inp.value));
  pop.addEventListener("click", e => {
    const it = e.target.closest(".bw-city"); if (!it) return;
    inp.value = it.dataset.name; bwSet("place", it.dataset.name); bwSet("lat", +it.dataset.lat); bwSet("lon", +it.dataset.lon); bwSet("tz", +it.dataset.tz);
    const tz = document.getElementById("bw-tz"); if (tz) tz.value = it.dataset.tz;
    pop.style.display = "none";
  });
}

async function renderBirthCast(ov) {
  const d = _bw.data;
  // compute the chart UP FRONT (it's fast, <100ms) so the success reveal has real values to show
  // and myProfile is set the instant the loader lands — the loader is theatre over ready data.
  const [cast, uniQuick] = await Promise.all([computeNatal(d), j("universe.json")]);
  const castErr = cast.error || null;
  // live count, not a hardcoded figure that silently goes stale as the universe grows
  const psxCount = Object.values(uniQuick?.symbols || {}).filter(m => ((m || {}).market ?? "PSX") === "PSX").length;
  if (!castErr) {
    const rec = { birth_data: d, natal_chart: cast, astro_prefs: { goal: d.goal } };
    if (me) { myProfile = { ...(myProfile || {}), ...rec }; saveProfile(rec); }  // persist in background
    else setGuestChart(rec);                                                     // guest: this device only
    track("cast_completed", { guest: !me });
    if (me) markActivated("cast");
  }
  const steps = [
    `Placing the nine grahas — sidereal, Lahiri ayanamsa`,
    d.time_known === false ? `Reading your Moon and its nakshatra` : `Rising sign from ${esc(d.place)} at ${esc(d.time)}`,
    `Balancing your Vimshottari dasha from the Moon's nakshatra`,
    `Reading all ${psxCount} PSX charts against yours — Tara, friendship, dasha`,
    `Ranking the market by resonance with your chart`,
  ];
  runRevealModal({
    sym: "", kicker: "Casting your chart", title: "Reading the market against your stars",
    sub: "Real sidereal math on your birth chart, then the tradition's compatibility techniques across every name on the exchange.",
    steps, flagKey: null,
    // the ONE exit: navigate to the reading (myProfile already holds the chart)
    onClose: () => { if (routeHash().replace(/^#\/?/, "").startsWith("mychart")) pageMyChart(); else navigate("/mychart"); },
    renderReveal: (bodyEl) => {
      if (castErr) {
        bodyEl.innerHTML = `<div class="rp-reveal"><div class="rp-reveal-head"><b>Couldn't cast the chart</b><span>${esc(castErr)}</span></div>
          <div class="empty" style="padding:16px">Check your birth date is between 1950 and 2035, then try again.</div>
          <div class="rp-reveal-foot"><span></span><span class="rp-foot-btns"><button class="rp-btn2" onclick="this.closest('.replay-overlay').querySelector('.replay-x').click();openBirthWizard()">Edit details</button></span></div></div>`;
        return;
      }
      const moon = cast?.grahas?.Moon, cur = cast?.dasha?.current;
      bodyEl.innerHTML = `<div class="rp-reveal cast-done">
        <div class="cast-tick">✓</div>
        <h2 class="cast-h">Your chart is cast, and the market is matched.</h2>
        <p class="cast-p">The desk placed your nine grahas${moon ? `, found your Moon in <b>${esc(moon.sign)} · ${esc(moon.nakshatra)}</b>` : ""}${cur ? `, balanced your <b>${esc(cur.lord)}</b> period` : ""}, and read all ${psxCount} PSX names against your stars.</p>
        <div class="cast-stats">
          <div><span>${moon ? esc(moon.sign) : "—"}</span><i>your Moon sign</i></div>
          <div><span>${cur ? esc(cur.lord) : "—"}</span><i>your current period</i></div>
          <div><span>${psxCount}</span><i>names matched</i></div>
        </div>
        <button class="bw-go cast-go" onclick="this.closest('.replay-overlay').querySelector('.replay-x').click()">See my reading →</button>
        <p class="cast-note">Astrological exploration, not advice. ${me
          ? "Saved privately to your account — edit any time in Settings."
          : "Your chart is on this device only. Create a free account to keep it and read it from anywhere."}</p>
      </div>`;
    },
  });
  ov.remove();
}

async function pageMyChart() {
  // yield one microtask: the initial route() runs before `let me` initializes further down the
  // file, and unlike other pages this one reads `me` before its first data await. This defers that
  // read past the synchronous module evaluation, avoiding a temporal-dead-zone error on cold load.
  await Promise.resolve();
  const bd = birthData(), nc = natalChart();
  if (!bd || !nc || nc.error) {
    $("view").innerHTML = `<div class="seg" style="margin-top:4px"><h2>Your chart</h2><div class="ln"></div><span class="pill">personal</span></div>
      <div class="disclaimer">Astrological exploration, not investment advice. A lens to read your own chart against the market — never a reason to buy.</div>
      <div class="card mychart-cta">
        <div class="mc-hero">${["Sun", "Moon", "Jupiter", "Saturn"].map(b => pixelGlyph(b, 30)).join("")}</div>
        <h2>Read the whole market against your birth chart</h2>
        <p class="sub">Vedic astrology has always matched two charts for compatibility. The desk turns that on the market: give it your birth details and it reads every PSX name against your stars — which your chart runs harmonious with, which it finds testing, and the periods your own dasha lights up.</p>
        <button class="bw-go" onclick="openBirthWizard()">Cast my birth chart →</button>
        <p class="sub" style="margin-top:10px;opacity:.7">Takes a minute. Your birth details stay private to your account.</p>
      </div>`;
    return;
  }
  const [uni, sectors, amap, natalAll, astroNow] = await Promise.all([
    j("universe.json"), j("sectors.json"), j("astro_map.json"), j("astro_natal.json"), j("astro.json")]);
  const names = uni?.symbols || {};
  const cur = nc.dasha?.current || {};
  const locked = !isSubscribed();
  // the daily layer: today's sky over this chart, and the dates it next re-deals
  const sky = await skyOn(Date.now()).catch(() => null);
  const goch = sky ? gocharaRead(nc, sky, amap) : null;
  const shifts = (goch && !locked) ? await upcomingShifts(nc).catch(() => []) : [];
  // score every ticker
  const scored = Object.keys(names).map(sym => {
    const stock = natalAll?.subjects?.[sym];
    const sector = (sectors?.tickers?.[sym] || {}).sector;
    const r = synastry(nc, stock, sector, amap, astroNow);
    return { sym, name: names[sym]?.name || "", sector, hasChart: !!stock, timing: stockTiming(nc, stock, sector, amap), ...r };
  }).filter(x => x.score != null).sort((a, b) => b.score - a.score);
  // curated slices, not threshold dumps — the strongest handful each way, so "harmonious" stays meaningful
  const harmon = scored.filter(x => x.score >= 58).slice(0, 8);
  const testing = scored.filter(x => x.score <= 44).slice(-6).reverse();
  const moon = nc.grahas.Moon, asc = nc.ascendant;
  const gl = goalLens();
  // commodities, scored against the chart the same way chartless stocks are
  const comm = COMMODITIES.map(c => ({ ...c, ...resonanceWithGraha(nc, c.sig, c.name, amap) }))
    .filter(c => c.score != null).sort((a, b) => b.score - a.score);

  // The wall lands where desire peaks: a guest reads their real chart and their strongest few
  // matches in full, then sees that a ranked map of the whole exchange exists behind it.
  const lockCard = (kicker, what) => `<div class="card mc-lock">
    <div class="mc-lock-blur" aria-hidden="true">${scored.slice(FREE_MATCHES, FREE_MATCHES + 4).map(x =>
      `<div class="mc-lock-row"><b>${esc(x.sym)}</b><span class="sub">${esc((x.sector || "").slice(0, 18))}</span><span class="num">${x.score}</span></div>`).join("")}</div>
    <div class="mc-lock-face">
      <div class="mc-lock-kick">${esc(kicker)}</div>
      <h3>${esc(what)}</h3>
      <p class="sub">${me
        ? "Your full reading — every name on the exchange ranked against your chart, your commodities, your timing windows, and the sky read against your chart each day."
        : "Create a free account to keep the chart you just cast. Unlock the full reading to see every name on the exchange ranked against it, your commodities, your timing windows, and the sky read against your chart each day."}</p>
      <button class="bw-go" style="max-width:260px" onclick="${me ? "navigate('/settings')" : "openAuth('signup')"}">${me ? "Unlock my full reading →" : "Create a free account →"}</button>
      ${me ? "" : `<p class="sub" style="margin-top:8px;opacity:.7">Already have one? <a href="#" onclick="openAuth('signin');return false" style="color:var(--accent)">Sign in</a></p>`}
    </div></div>`;

  const rowCard = (x) => {
    const tm = x.timing;
    return `<div class="card syn-card"><div class="syn-head clickable" onclick="navigate('/ticker/${esc(x.sym)}')">
      <span class="syn-score s-${x.verdict.replace(/\s/g, "")}">${x.score}</span>
      <div><b>${esc(x.sym)}</b> <span class="sub">${esc((x.name || "").slice(0, 26))}</span><div class="sub">${esc(x.sector || "")}${x.hasChart ? "" : " · sector reading"}</div></div>
      <span class="pill ${x.verdict === "harmonious" || x.verdict === "favourable" ? "ok" : x.verdict === "testing" || x.verdict === "discordant" ? "bad" : ""}">${esc(x.verdict)}</span></div>
    <div class="syn-why">${x.reasons.slice(0, 3).map(r => `<div class="syn-r ${r.w > 0 ? "up" : r.w < 0 ? "dn" : ""}"><b>${esc(r.k)}</b> ${esc(r.why)}</div>`).join("")}
    ${tm ? `<div class="syn-time"><span class="dt-glyph">${pixelGlyph(tm.windows[0].lord, 14)}</span> <b>The tradition's timing:</b> your ${esc(tm.windows[0].lord)} period (${tm.windows[0].from.slice(0, 4)}–${tm.windows[0].to.slice(0, 4)}) is when your chart most resonates with ${esc(x.sym)}${tm.windows[1] ? `, again under ${esc(tm.windows[1].lord)} from ${tm.windows[1].from.slice(0, 4)}` : ""}. A rhythm, not a date to act on.</div>` : ""}</div></div>`;
  };

  /* ---- Daily market weather: behavioural framing, NOT prediction. The tradition's read of the
     day's sky against this chart, expressed as questions about the user's own temperament —
     focus, patience, impulse — never as a claim about prices. Different daily because the sky is. ---- */
  let weather = "";
  if (goch) {
    const HOUSE = ["", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th", "11th", "12th"];
    const g = n => goch.tiles.find(x => x.g === n);
    const merc = g("Mercury"), mars = g("Mars"), sat = g("Saturn"), jup = g("Jupiter");
    const fav = x => x && x.tag === "favourable";
    const dims = [
      { k: "Focus", v: fav(merc) ? "clear" : merc?.tag === "testing" ? "scattered" : "steady",
        why: `Mercury — analysis, records, paperwork — sits in your ${HOUSE[merc?.house] || "—"} from the Moon. ${fav(merc) ? "Tradition associates this with reading carefully and finishing what you start." : "Tradition would say re-check what you read today rather than trusting the first pass."}` },
      { k: "Patience", v: fav(sat) ? "long" : sat?.tag === "testing" ? "short" : "workable",
        why: `Saturn governs endurance and delay, currently your ${HOUSE[sat?.house] || "—"} from the Moon. ${sat?.tag === "testing" ? "Read classically as a stretch where waiting feels harder than usual — worth noticing before acting on impatience." : "Placed where the tradition associates it with letting things mature."}` },
      { k: "Impulse risk", v: fav(mars) ? "channelled" : mars?.tag === "testing" ? "elevated" : "ordinary",
        why: `Mars is drive and haste, in your ${HOUSE[mars?.house] || "—"}. ${fav(mars) ? "Energy the tradition reads as directed rather than reactive." : "Classically a placement for acting faster than you have thought. If you feel an urge to do something decisive today, that urge is worth a second look."}` },
      { k: "Good for", v: fav(jup) ? "learning" : fav(merc) ? "review" : "routine",
        why: fav(jup) ? "Jupiter — teaching, perspective, expansion — is well placed from your Moon. Tradition calls this a day for study rather than action." : fav(merc) ? "A day the tradition associates with going back over your own records and reasoning." : "Nothing in the tradition marks this day out; ordinary maintenance is the honest read." },
    ];
    weather = `
  <div class="seg"><h2>Your market weather</h2><div class="ln"></div><span class="pill">${new Date().toISOString().slice(0, 10)}</span></div>
  <p class="sub" style="margin-bottom:12px">The moving sky read against your chart as a note on <b>your own temperament today</b> — focus, patience, impulse. It says nothing about prices and makes no prediction: it is a prompt to check <i>how</i> you are approaching decisions, which is the one place this tradition and sound investing practice genuinely overlap.</p>
  <div class="weather-grid">${dims.map(d => `<div class="wx-card">
    <div class="ark">${esc(d.k)}</div><b>${esc(d.v)}</b><span class="sub">${d.why}</span></div>`).join("")}</div>
  <div class="tnote">Behavioural reflection drawn from Vedic gochara — <b>not a forecast, not a signal, and not a reason to trade or to avoid trading</b>. The desk tested astrology against PSX returns and found no predictive edge; this exists because reviewing your own state of mind before deciding is sound practice whatever prompts it.</div>`;
  }

  // ---- "Today, against your chart" — the section that is different every single day ----
  const ord = n => n === 1 ? "1st" : n === 2 ? "2nd" : n === 3 ? "3rd" : n + "th";
  let todaySection = "";
  if (goch) {
    const gTile = t => `<div class="goch-tile ${t.tag === "favourable" ? "up" : t.tag === "testing" ? "dn" : ""}">
      <div class="goch-top"><span class="dt-glyph">${pixelGlyph(t.g, 16)}</span><b>${esc(t.g)}</b><span class="pill ${t.tag === "favourable" ? "ok" : t.tag === "testing" ? "bad" : ""}">${t.tag}</span></div>
      <div class="sub">in ${esc(t.sign)} — your ${ord(t.house)} from the Moon${t.conj ? ` · <b>crossing your natal ${esc(t.conj)}</b>` : ""}${t.domains ? ` · ${esc(t.domains)}` : ""}</div></div>`;
    const shiftLine = s => s.kind === "antar" ? `your sub-period turns to <b>${esc(s.body || "")}</b> — your readings and commodities re-rank`
      : s.kind === "maha" ? `your <b>${esc(s.body || "")}</b> maha-dasha closes — a new long chapter opens`
      : `<b>${esc(s.body)}</b> enters ${esc(s.sign)} — your ${ord(s.house)} from the Moon, traditionally ${s.fav ? "favourable" : "a quieter seat"}`;
    const big = shifts.find(s => s.kind === "ingress" && ["Jupiter", "Saturn", "Rahu"].includes(s.body));
    const list = shifts.slice(0, 4);
    if (big && !list.includes(big)) list.push(big);
    todaySection = `
  <div class="seg"><h2>Today, against your chart</h2><div class="ln"></div><span class="pill">${new Date().toISOString().slice(0, 10)} · refreshes daily</span></div>
  <p class="sub" style="margin-bottom:12px">Gochara — the tradition reads the moving sky from your natal Moon. The nine grahas that stood still the moment you were born have kept moving; this is where each stands over your chart <b>today</b>. A daily lens for exploration, never a signal.</p>
  ${locked
    ? `<div class="goch-grid">${goch.tiles.filter(t => t.g === "Moon").map(gTile).join("")}</div>
       ${planWall("The daily sky, read against your chart",
      "All nine grahas placed from your Moon and refreshed every day, the days they cross your natal points — and the dates the sky next re-deals your chart, so you know exactly when to look again.")}`
    : `<div class="goch-grid">${goch.tiles.map(gTile).join("")}</div>
       ${goch.sadeSati ? `<div class="disclaimer">Saturn is moving through the signs around your natal Moon — the stretch tradition calls <b>Sade Sati</b> and reads as slow-earned lessons. A weather report from the tradition, not a verdict.</div>` : ""}
       ${list.length ? `<div class="card next-look"><div class="mc-lock-kick">worth another look</div>
        ${list.map(s => `<div class="nl-row"><b class="num">${esc(s.date)}</b><span>${shiftLine(s)}</span></div>`).join("")}
        <p class="sub" style="margin-top:8px">The sky re-deals a little every day — these are the dates it re-deals <b>your</b> chart meaningfully. Each is worth a fresh read.</p></div>` : ""}`}`;
  }

  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Your chart</h2><div class="ln"></div><span class="pill">${esc(bd.place || "")} · ${esc(bd.date || "")}</span></div>
  <div class="disclaimer">Astrological exploration, <b>not investment advice</b>. A lens to read your chart against the market as the tradition would — never a recommendation to buy or a forecast of profit.</div>

  <div class="card">
    <div class="mc-chart-top"><div>
      <div class="ark">Your Moon</div><b style="font-size:18px">${esc(moon.sign)} · ${esc(moon.nakshatra)}</b>
      <div class="sub">${asc ? `Rising sign ${esc(asc.sign)}` : "Chandra lagna · a Moon-led chart"}</div>
    </div>
    <div><div class="ark">Your current period</div><b style="font-size:18px">${pixelGlyph(cur.lord, 18)} ${esc(cur.lord || "—")}${cur.antar ? ` / ${esc(cur.antar)}` : ""} dasha</b>
      <div class="sub">${cur.antar ? `${esc(cur.antar)} sub-period to ~${esc(String(cur.antar_to || "").slice(0, 7))} · ` : ""}${esc(cur.lord || "")} maha to ~${esc(String(cur.to || "").slice(0, 7))}</div></div>
    </div>
    ${natalOrrery(nc.grahas, asc, sky)}
    <p class="sub" style="margin-top:6px;text-align:center">Your birth sky — the nine grahas at the moment you were born${sky ? ", with <b>today's sky</b> faint on the outer ring. It drifts a little every day" : ""}. Sidereal, Lahiri.</p>
    ${gl.line ? `<p class="sub goal-line" style="text-align:center;margin-top:4px">You're here for <b>${esc(gl.label)}</b>. ${esc(gl.line)}</p>` : ""}
  </div>
  ${weather}
  ${todaySection}

  <div class="seg"><h2>Your timing — the map of when</h2><div class="ln"></div><span class="pill">Vimshottari</span></div>
  <p class="sub" style="margin-bottom:12px">Vedic astrology divides a life into planetary periods (dashas), and each into sub-periods (antardashas). Each, tradition says, colours the time it rules. This is your ribbon — the long arc above, the nearer sub-periods below. A rhythm to understand your chart by, <b>never</b> a schedule to trade on.</p>
  <div class="card">${dashaTimeline(nc, amap)}${antardashaStrip(nc, amap)}</div>

  <div class="seg"><h2>The market your chart favours</h2><div class="ln"></div><span class="pill ok">your strongest</span></div>
  <p class="sub" style="margin-bottom:12px">The names the tradition reads as most in tune with your chart — by Moon-star compatibility (Tara), the friendship of your ruling planets, and your running dasha. High resonance means astrological harmony, <b>not</b> a prediction of gains.</p>
  ${(locked ? harmon.slice(0, FREE_MATCHES) : harmon).map(rowCard).join("") || '<div class="card"><div class="empty">Nothing scores strongly harmonious — your chart sits neutral to most of the market.</div></div>'}
  ${locked ? lockCard("the rest of your map", `${scored.length - FREE_MATCHES} more names, ranked against your chart`) : ""}

  ${locked ? "" : `<div class="seg"><h2>The names that test your chart</h2><div class="ln"></div><span class="pill bad">most friction</span></div>
  <p class="sub" style="margin-bottom:12px">Where the tradition reads friction between your chart and the stock's. Not "avoid" — friction, in astrology, is simply a harder resonance to work with.</p>
  ${testing.map(rowCard).join("") || '<div class="card"><div class="empty">Nothing scores strongly discordant.</div></div>'}

  <div class="seg"><h2>Commodities &amp; metals</h2><div class="ln"></div><span class="pill">${comm.length} read</span></div>
  <p class="sub" style="margin-bottom:12px">Gold, silver, oil and the crops carry their own rulers in the tradition — read against your chart the same way. ${gl.grahas.length ? `For <b>${esc(gl.label)}</b>, the tradition would look first to ${gl.grahas.map(esc).join(", ")}.` : ""}</p>
  <div class="comm-grid">${comm.map(c => `<div class="comm-card ${c.verdict === "harmonious" || c.verdict === "favourable" ? "up" : c.verdict === "testing" || c.verdict === "discordant" ? "dn" : ""}">
    <div class="comm-top"><span class="comm-glyph">${pixelGlyph(c.glyph, 20)}</span><b>${esc(c.name)}</b><span class="comm-score">${c.score}</span></div>
    <div class="sub comm-note">${esc(c.note)}. <b>${esc(c.verdict)}</b> with your chart — ${esc((c.reasons[0] || {}).why || "")}</div></div>`).join("")}</div>

  <div class="seg"><h2>Your whole-market map</h2><div class="ln"></div><span class="pill">${scored.length} names ranked</span></div>
  <div class="card" style="padding:0"><table><thead><tr><th>Stock</th><th>Sector</th><th class="r">Resonance</th><th>Tradition's read</th></tr></thead><tbody>${
    scored.map(x => `<tr class="clickable" onclick="navigate('/ticker/${esc(x.sym)}')"><td><b>${esc(x.sym)}</b></td><td class="sub">${esc((x.sector || "").slice(0, 20))}</td>
      <td class="r num ${x.score >= 60 ? "up" : x.score <= 40 ? "dn" : ""}">${x.score}</td><td class="sub">${esc(x.verdict)}</td></tr>`).join("")}</tbody></table></div>`}

  <p class="sub" style="margin-top:14px"><button class="note-save" onclick="openBirthWizard()">Edit my birth details</button> · Your resonance map is astrological interpretation — a lens for exploration and your own decisions, never advice.</p>`;
}

/* ---------- Astro: the sky, computed — and the test that says it doesn't predict anything.
   The null result LEADS. The calendar is the secondary thing, offered as calendar, not signal.
   This page exists because we tested it, not because we believe it. ---------- */
async function pageAstro() {
  const [a, natal, amap, sectors, uni, bt, ctx] = await Promise.all([
    j("astro.json"), j("astro_natal.json"), j("astro_map.json"),
    j("sectors.json"), j("universe.json"), j("astro_backtest.json"), j("astro_context.json")]);
  if (!a || a.status !== "ok") {
    $("view").innerHTML = `<div class="seg" style="margin-top:4px"><h2>Astro</h2><div class="ln"></div></div>
      <div class="card"><div class="empty">The sky is unavailable this cycle${a?.error ? ` (${esc(a.error)})` : ""}. Check back shortly.</div></div>`;
    return;
  }
  const sys = a.system || {};

  // ---- your charts: the board. Nothing shows until the desk is RUN on it (same discipline
  // as the strategy board) — the casting is the experience.
  const board = astroBoard();
  const names = uni?.symbols || {};
  const verifiedOf = s => !!natal?.subjects?.[s];
  const tiles = board.map(s => { const ran = astroRunOn(s);
    return `<div class="sb-tile clickable" onclick="if(!event.target.closest('.sb-x'))navigate('/ticker/${esc(s)}')">
      <button class="sb-x" data-abdel="${esc(s)}" title="Remove ${esc(s)}" aria-label="remove ${esc(s)}">✕</button>
      <b>${esc(s)}</b><span class="sb-nm">${esc((names[s]?.name || "").slice(0, 24))}</span>
      <span class="pill ${ran ? (verifiedOf(s) ? "ok" : "") : "wait"}">${ran ? (verifiedOf(s) ? "natal chart" : "sector reading") : "waiting for a cast"}</span>
    </div>`; }).join("");
  const addTile = `<div class="sb-tile sb-add">
      <span class="sk">Add a stock</span>
      <input id="ab-tkr" class="ph-in combo" type="search" enterkeyhint="search" placeholder="e.g. UBL" autocomplete="off" onkeydown="if(event.key==='Enter'&&!document.querySelector('.combo-opt.on'))addAstroTicker()">
      <button class="note-save" onclick="addAstroTicker()">Add to board</button>
    </div>`;
  const pendingA = board.filter(s => !astroRunOn(s));
  const runBarA = board.length ? `<button class="run-desk run-strat ${pendingA.length ? "" : "ran"}" onclick="playAstroBoardRun()">
    <span class="run-ico">▶</span>
    <span class="run-txt"><b>${pendingA.length ? `Cast the charts for your ${board.length} stock${board.length > 1 ? "s" : ""}` : `Cast your ${board.length} chart${board.length > 1 ? "s" : ""} again`}</b><i>Real ephemeris math against today's sky — birth charts, Vimshottari periods, Saturn's passage, transits to natal points. The tradition's reading of each name.</i></span>
    <span class="run-meta"><span class="run-last">Sky as of · ${esc((a.updated || "").slice(0, 10))}</span><span class="run-go">${pendingA.length ? "Cast ›" : "Cast again ›"}</span></span>
  </button>` : "";
  const dataPack = { natal, sky: a, amap, sectors, uni, bt, ctx };
  const readings = board.filter(astroRunOn).map(s =>
    `<div class="card ar-card">${composeAstroReading(s, dataPack)}</div>`).join("");
  const boardStub = board.length && pendingA.length === board.length
    ? `<div class="card"><div class="empty">Your readings land here — hit <b>Cast ›</b> above and the desk works each chart against today's sky.</div></div>` : "";
  const sTile = (label, val, sub, k) => `<div class="sumtile"><span class="sk">${label}</span><b class="${k || ""}">${val}</b>${sub ? `<i>${sub}</i>` : ""}</div>`;

  // today's sky — the almanac
  const pos = a.positions || {};
  const skyRows = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Rahu", "Ketu"].map(b => {
    const p = pos[b]; if (!p) return "";
    return `<tr><td><b>${esc(b)}</b></td><td>${esc(p.sign)} <span class="sub">${p.deg_in_sign}°</span></td>
      <td class="sub">${esc(p.nakshatra)} <span style="opacity:.6">pada ${p.pada}</span></td>
      <td class="r">${p.retrograde ? '<span class="tag">retrograde</span>' : ""}</td></tr>`;
  }).join("");

  const evs = (a.events || []).filter(e => e.importance >= 3).slice(0, 14);
  const evRows = evs.map(e => `<tr><td class="num">${esc(e.date)}</td>
    <td><b>${esc(e.text)}</b></td>
    <td class="r"><span class="pill ${e.importance >= 5 ? "bad" : ""}">${e.importance >= 5 ? "rare" : e.importance >= 4 ? "material" : "notable"}</span></td></tr>`).join("");

  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Astro</h2><div class="ln"></div><span class="pill">the sky, read</span></div>
  <div class="disclaimer">Real charts and real sidereal ephemeris math. Astrological exploration — never a signal, a prediction, or advice.</div>

  <div class="seg"><h2>Your charts</h2><div class="ln"></div><span class="pill">${board.length ? board.length + " on the board" : "empty"}</span></div>
  <div class="card">
    <div class="sb-grid">${tiles}${addTile}</div>
    <span id="ab-msg" class="sub" style="display:block;margin-top:8px"></span>
    ${!me && board.length ? `<span class="sub" style="display:block;margin-top:4px">Your board lives in this session only — <a style="color:var(--accent);cursor:pointer" onclick="openAuth('signup')">sign in</a> to keep it.</span>` : ""}
  </div>
  ${runBarA}
  ${boardStub}
  ${readings}

  <div class="sumstrip" style="grid-template-columns:repeat(4,1fr);margin-top:16px">
    ${sTile("Zodiac", "Sidereal", "Lahiri (Chitrapaksha)", "")}
    ${sTile("Ayanamsa", (sys.ayanamsa_deg ?? "—") + "°", "the current precession", "")}
    ${sTile("Grahas", "9", "the classical set", "")}
    ${sTile("Sky as of", esc((a.updated || "").slice(0, 10)), "recomputed every day", "")}
  </div>

  <div class="seg"><h2>The sky right now</h2><div class="ln"></div><span class="pill">sidereal · Lahiri</span></div>
  <div class="card" style="padding:0"><table><thead><tr><th>Graha</th><th>Sign</th><th>Nakshatra</th><th class="r"></th></tr></thead><tbody>${skyRows}</tbody></table></div>
  <p class="sub" style="margin-top:8px">Where the nine grahas stand today — sidereal positions, Lahiri ayanamsa.</p>

  ${evs.length ? `<div class="seg"><h2>What the sky does next</h2><div class="ln"></div><span class="pill">${a.horizon_days} days</span></div>
  <div class="card" style="padding:0"><table><thead><tr><th>Date</th><th>Event</th><th class="r">Rank</th></tr></thead><tbody>${evRows}</tbody></table></div>
  <p class="sub" style="margin-top:8px">The dated turns in the sky over the coming weeks — ingresses, stations, eclipses and moons, ranked by weight. An almanac.</p>` : ""}`;
}

function maxDrawdown(bars) {
  // returns {mdd%, peakDate, troughDate} over the given bars
  let peak = bars[0]?.close || 0, peakDate = bars[0]?.date, mdd = 0, pk = peak, pkd = peakDate, td = peakDate;
  for (const b of bars) {
    if (b.close > pk) { pk = b.close; pkd = b.date; }
    const dd = b.close / pk - 1;
    if (dd < mdd) { mdd = dd; peakDate = pkd; td = b.date; }
  }
  return { mdd: mdd * 100, peakDate, troughDate: td };
}
function behaviorStats(hist) {
  /* Null-safe at the source. The ticker page no longer dead-ends when the price history alone
     fails to fetch, so this can now legitimately be called with nothing. Returning a shape of
     nulls (rather than throwing, or returning zeros) keeps every caller's optional-chaining and
     "—" fallbacks working, and — more importantly — means a missing file can never be rendered
     as a real statistic of 0%. */
  if (!hist || hist.length < 2) {
    return { total: null, mdd: null, mddPeak: null, mddTrough: null, mddRecent: null,
             mddRecentTrough: null, upPct: null, avgAbs: null, best: null, worst: null };
  }
  const c = hist.map(h => h.close);
  const rets = c.slice(1).map((v, i) => v / c[i] - 1);
  const upDays = rets.filter(r => r > 0).length;
  const full = maxDrawdown(hist);
  // recent-era drawdown (last ~10 years) — the number that actually describes today's risk,
  // separate from a decades-old crisis extreme
  const cutoff = new Date(); cutoff.setFullYear(cutoff.getFullYear() - 10);
  const cut = cutoff.toISOString().slice(0, 10);
  const recentBars = hist.filter(b => b.date >= cut);
  const recent = recentBars.length > 30 ? maxDrawdown(recentBars) : full;
  return {
    total: (c[c.length - 1] / c[0] - 1) * 100,
    mdd: full.mdd, mddPeak: full.peakDate, mddTrough: full.troughDate,
    mddRecent: recent.mdd, mddRecentTrough: recent.troughDate,
    upPct: upDays / rets.length * 100,
    avgAbs: rets.reduce((a, r) => a + Math.abs(r), 0) / rets.length * 100,
    best: Math.max(...rets) * 100,
    worst: Math.min(...rets) * 100,
  };
}
function yr(d) { return (d || "").slice(0, 4); }

/* The test log — every strategy tested on a ticker written out in plain English, pass AND fail,
   with the exact reason each one made or missed the bar. Composed from backtests.json + the
   library's own descriptions, so it can never claim more than the numbers say. */
function renderTestLog(sym, allTested, lib, cfg) {
  if (!allTested.length) return "";
  const descs = {}; (lib?.strategies || []).forEach(s => { descs[s.id] = s; });
  const c = cfg || {};
  const minHit = (c.min_hit_rate ?? 0.55) * 100, minNet = c.min_net_expectancy_pct ?? 0.5,
    fric = c.friction_pct ?? 0.6, minN = c.min_trades ?? 8;
  // one decimal, trailing .0 dropped — rounding to whole percent made the verdict read as a
  // contradiction ("54.9% rejected for being below the 55% bar" showed as "55% below 55%")
  const pct = v => v == null ? "—" : (Math.round(v * 1000) / 10).toFixed(1).replace(/\.0$/, "") + "%";
  const entry = t => {
    const d = descs[t.id] || {}, oos = t.oos || {};
    const oosNet = (oos.avg_return_pct ?? 0) - fric;
    const why = [];
    if (t.n < minN) why.push(`it only triggered ${t.n} time${t.n === 1 ? "" : "s"} — under the ${minN}-trade minimum, too thin a sample to trust`);
    if ((t.hit_rate ?? 0) < minHit / 100) why.push(`its ${pct(t.hit_rate)} win rate is below the ${minHit.toFixed(0)}% bar`);
    if ((t.net_expectancy_pct ?? -99) < minNet) why.push(`after ${fric}% costs each trade averages ${sgn(t.net_expectancy_pct)}%, short of the +${minNet}% the desk demands`);
    if (!(oos.n >= 3 && oosNet > 0)) why.push(oos.n >= 3 ? `it stopped working out-of-sample (${sgn(oosNet.toFixed(2))}% net on the unseen last third)` : `it left only ${oos.n || 0} out-of-sample trades — not enough to prove it still works on unseen data`);
    return `<div class="tl-row ${t.eligible ? "pass" : "fail"}">
      <div class="tl-head"><b>${esc(t.name || t.id)}</b><span class="tag">${esc((t.category || "").replace(/_/g, " "))}</span>
        <span class="tl-verdict ${t.eligible ? "up" : ""}">${t.eligible ? "PROVEN" : "rejected"}</span></div>
      ${d.description ? `<p class="tl-rule"><i>The rule:</i> ${esc(d.description)}${d.target_pct != null ? ` Takes profit at +${d.target_pct}%, stops out at −${d.stop_pct}%, gives up after ${d.hold} sessions.` : ""}</p>` : ""}
      <p class="tl-p">On ${esc(sym)}'s own history this triggered <b>${t.n}</b> time${t.n === 1 ? "" : "s"} and won <b>${pct(t.hit_rate)}</b> of them. The average trade made <b>${sgn(t.avg_return_pct)}%</b> before costs — <b class="${(t.net_expectancy_pct ?? 0) > 0 ? "up" : "dn"}">${sgn(t.net_expectancy_pct)}%</b> after the desk's ${fric}% friction assumption.${t.payoff_ratio != null ? ` Its average win was <b>${t.payoff_ratio}×</b> its average loss.` : ""}${t.worst_pct != null ? ` The worst single trade lost <b>${Math.abs(t.worst_pct)}%</b>.` : ""} Out-of-sample — the last third of the history, which the rule never saw while being judged — it took <b>${oos.n || 0}</b> trade${oos.n === 1 ? "" : "s"}${oos.n ? ` and won <b>${pct(oos.hit_rate)}</b>` : ""}.</p>
      <p class="tl-why">${t.eligible
        ? `<b class="up">Cleared every bar</b> — win rate above ${minHit.toFixed(0)}%, positive expectancy after costs, and still profitable on data it had never seen. The desk will use it on ${esc(sym)}.`
        : `<b>Rejected</b> because ${why.slice(0, 2).join(", and ")}. The desk won't signal ${esc(sym)} on this rule — a strategy that works elsewhere doesn't get a pass here.`}</p>
    </div>`;
  };
  const passed = allTested.filter(t => t.eligible), failed = allTested.filter(t => !t.eligible);
  return `<details class="testlog">
    <summary><b>The full test log</b><span class="sub">all ${allTested.length} strategies tested on ${esc(sym)} — what each rule is, what it did, and exactly why it passed or failed</span><span class="dict-arrow">▾</span></summary>
    <div class="tl-wrap">
      <p class="tr-intro">Every rule below was run bar-by-bar across ${esc(sym)}'s own price history — no peeking ahead, costs deducted, and then re-checked on the last third of the data it had never seen. The failures are published for the same reason as the passes: a library that only shows its winners is a sales pitch, not a test.</p>
      ${passed.length ? `<div class="tl-sec">${passed.length} cleared the bar</div>${passed.map(entry).join("")}` : ""}
      ${failed.length ? `<div class="tl-sec">${failed.length} rejected</div>${failed.map(entry).join("")}` : ""}
    </div>
  </details>`;
}

/* QA verdicts are internal ops vocabulary (clean/flags/blocked) — never surface that raw to a
   reader. "blocked" means the verifier found a wrong number on screen, so that case is gated out
   entirely before this ever renders (see renderRoom); this map only ever has to soften clean/flags. */
function qaLabel(v) {
  return { clean: "Verified", flags: "Notes pending" }[v] || "Checked";
}

/* The full session transcript — every analyst's turn, in the order they spoke, with everything
   they actually wrote (including the fields the summary view leaves out). For people who want to
   read the desk's working rather than its verdict. Pure render of the stored session: no agent runs. */
function renderTranscript(room, sym) {
  const ta = room.ta_memo || {}, fa = room.fa_memo || {}, bull = room.bull_case || {}, bear = room.bear_case || {};
  const stanceClass = s => ({ constructive: "up", cautious: "dn", neutral: "", unclear: "", near_fair: "" }[s] || "");
  const P = t => t ? `<p class="tr-p">${esc(t)}</p>` : "";
  const UL = a => (a || []).length ? `<ul class="tr-ul">${a.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
  const NOTE = (label, t) => t ? `<div class="tr-note"><span>${label}</span>${esc(t)}</div>` : "";
  const facts = arr => { const f = arr.filter(x => x[1] != null && x[1] !== "" && x[1] !== "—");
    return f.length ? `<div class="tr-facts">${f.map(([k, v]) => `<span><i>${k}</i> <b>${esc(String(v).replace(/_/g, " "))}</b></span>`).join("")}</div>` : ""; };
  const turn = (av, name, role, stance, body) => `<div class="tr-turn">
    <div class="tr-rail"><span class="tr-av">${av}</span></div>
    <div class="tr-body"><div class="tr-head"><b>${name}</b><span class="tr-role">${role}</span>${stance ? `<span class="stance ${stanceClass(stance)}">${esc(stance)}</span>` : ""}</div>${body}</div>
  </div>`;

  return `<details class="room-transcript">
    <summary>The full transcript — read the desk's actual working, turn by turn <span class="exhint">click to expand</span></summary>
    <div class="tr-wrap">
      <p class="tr-intro">The session ran on <b>${esc(String(room.built || room.dossier_asof || "").slice(0, 16))}</b> against ${esc(sym)}'s dossier at Rs ${fmt(room.price_at_session)}. The two desks work <b>in isolation</b> — the chartist never sees the fundamentals, and the fundamentalist never sees the chart — so when they agree, they agree independently. Then a bull and a bear are told to argue, hard. Nothing below is edited.</p>

      ${turn("MC", "Meher", "The Chartist · technical desk · spoke first", ta.technical_stance,
        P(tp(ta, "read")) + facts([["structure", ta.structure], ["momentum", ta.momentum], ["support", ta.levels?.support != null ? fmt(ta.levels.support) : null], ["resistance", ta.levels?.resistance != null ? fmt(ta.levels.resistance) : null]])
        + NOTE("On liquidity", tp(ta, "liquidity_note"))
        + ((ta.proven_now || []).length ? `<div class="tr-note"><span>Proven patterns firing on this bar</span>${ta.proven_now.map(esc).join(" · ")}</div>` : ""))}

      ${turn("DO", "Dr. Omar", "The Fundamentalist · fundamental desk · spoke second", fa.fundamental_stance,
        P(tp(fa, "read")) + facts([["valuation", fa.valuation_stance]])
        + NOTE("Earnings quality", tp(fa, "earnings_quality")) + NOTE("Dividend safety", tp(fa, "dividend_safety"))
        + NOTE("Balance-sheet flags", Array.isArray(fa.balance_sheet_flags) ? fa.balance_sheet_flags.join(" · ") : fa.balance_sheet_flags)
        + NOTE("On the brokers", tp(fa, "broker_view")))}

      ${turn("ZB", "Zoya", "The Bull · argued the case FOR", "constructive",
        P(tp(bull, "thesis")) + UL(bull.pillars) + NOTE("Her strongest evidence", tp(bull, "best_evidence"))
        + NOTE("What would break her case", tp(bull, "what_would_break_it")))}

      ${turn("KB", "Khurram", "The Bear · argued the case AGAINST", "cautious",
        P(tp(bear, "thesis")) + UL(bear.pillars) + NOTE("His attack on the bull", tp(bear, "attack_on_bull"))
        + NOTE("His strongest evidence", tp(bear, "best_evidence"))
        + NOTE("What would break his case", tp(bear, "what_would_break_it")))}

      ${room.qa ? turn("QA", "The Verifier", "QA · fact-checked the session against the data and live sources", "",
        `<div class="tr-note"><span>Verdict</span><b class="${room.qa.verdict === "clean" ? "up" : ""}">${esc(qaLabel(room.qa.verdict))}</b>${room.qa.checked ? ` · checked ${esc(room.qa.checked)}` : ""}</div>` + P(tp(room.qa, "note")))
        : turn("QA", "The Verifier", "QA · not yet run on this session", "",
        `<div class="tr-note"><span>Verdict</span><b>Not yet verified</b></div><p class="tr-p">This session hasn't been through the Verifier — nothing above has been cross-checked against the data or live sources yet. Read the bull/bear case with that in mind.</p>`)}

      <div class="tr-close">↑ That is where the session ends — the desk publishes the debate, not a verdict. No house view, no call, no target on ${esc(sym)}.</div>
    </div>
  </details>`;
}

/* The Desk Room — named AI-analyst personas debate a ticker (from state/rooms.json). */
function renderRoom(room, sym) {
  const head = `<div class="seg"><h2>The Desk Room</h2><div class="ln"></div><span class="pill">AI analysts · research, not advice</span></div>`;
  // The session is terminal at the bull/bear debate now (no Chair verdict) — bull_case is present
  // in every real session, so it, not the removed house_view, is what marks a room as covered.
  if (!room || !room.bull_case) {
    return `${head}<div class="card"><div class="empty">No Room session for ${esc(sym)} yet. The desk's AI analysts — a technical desk, a fundamental desk, a bull and a bear — cover names in rotation (results, high-impact news and signals jump the queue). ${esc(sym)} is in the queue.</div></div>`;
  }
  // The verifier's "blocked" verdict means a wrong number is on screen — do not publish that
  // content as-is, softened label or not. Withhold the session and say so plainly instead.
  if (room.qa && room.qa.verdict === "blocked") {
    return `${head}<div class="card"><div class="empty">The desk's session on ${esc(sym)} is being re-checked before it republishes — nothing shown here right now. It'll be back once the recheck clears.</div></div>`;
  }
  return `${head}
  <p class="sub" style="margin:-4px 0 12px">Named AI analyst personas research and debate <b>${esc(sym)}</b>. The technical and fundamental desks work <b>separately</b>, then a bull and a bear argue the case, hard. This is general commentary — research, not advice: no house view, no call, no target.</p>

  ${renderTranscript(room, sym)}`;
}

async function pageTicker(sym, _retry = 0) {
  sym = sym.toUpperCase();
  const [quant, bt, smap, uni, live, news, divs, fund, fscore, cal, hist, deep, intra, fvAll, roomsAll, claimsAll, researchIdx, explainAll, sigAll, stratLib, sectAll, smAll, predAll, liqAll, insiderAll, offmktAll, verifyAll] = await Promise.all([
    j("quant.json"), j("backtests_meta.json"), j("strategy_map.json"), j("universe.json"),
    j("live.json"), j("newslog.json"), j("dividends.json"), j("fundamentals.json"),
    j("fundamental_scores.json"), j("earnings_calendar.json"), j("history/" + sym + ".json", 300000),
    j("history_deep/" + sym + ".json", 600000), j("intraday/" + sym + ".json", 20000), j("fairvalue.json"), j("rooms.json"), j("claims.json"), j("research_index.json"), j("explainer.json"), j("signals.json"), j("strategy_library.json"), j("sectors.json"), j("sector_macro.json"), j("predictability.json"), j("liquidity.json"), j("insider_activity.json"), j("offmarket_activity.json"), j("verify.json")]);
  /* qRaw vs q: `qRaw` answers "did the quant snapshot arrive?", `q` is what the rest of the page
     reads from. Keeping them separate is what lets the page render without quant instead of
     throwing on the first `q.avg_daily_traded_value` — the fields simply come back undefined and
     the existing "—" fallbacks handle them. */
  const qRaw = quant?.tickers?.[sym], u = uni?.symbols?.[sym], lv = live?.tickers?.[sym];
  const q = qRaw || {};
  const lq = liqAll?.tickers?.[sym];
  const proven = (smap?.tickers?.[sym]) || [];
  const fsc = fscore?.tickers?.[sym];
  const fv = fvAll?.tickers?.[sym];
  const room = roomsAll?.[sym];
  const verIssues = (Array.isArray(verifyAll?.[sym]) ? verifyAll[sym] : []);
  const staleIssue = verIssues.find(i => i.field === "room.price_staleness");
  const divYieldIssue = verIssues.find(i => i.field === "fundamentals.div_yield");
  const claimIssues = verIssues.filter(i => i.field === "claim.price");
  const escalated = (verifyAll?._meta?.escalate_to_agent || []).includes(sym);
  // real PSX sector name — the feed only carries a numeric code ("0809"), so the old
  // `isNaN(lv.sector)` guard meant this tag never rendered for any ticker
  const mySector = (sectAll?.tickers?.[sym] || {}).sector || "";
  // broker calls on this ticker (from the weekly harvest) — the "real picture" from the houses
  const brokerDocs = ((researchIdx?.by_ticker?.[sym]) || []).filter(d => d.doc_type === "broker call");
  const brokerClaims = (claimsAll?.claims || []).filter(c => c.ticker === sym && c.source_type === "broker");
  const ex = explainAll?.[sym];
  const glance = ex ? (() => {
    const tile = (label, o) => o ? `<div class="glance-tile"><span class="glance-q">${label}</span><b>${esc(o.verdict)}</b><div class="sub">${esc(o.one_line)}</div></div>` : "";
    const rets = ex.return_by_year || [];
    const spark = rets.length ? `<div class="glance-tile"><span class="glance-q">Yearly price change</span>
      <div class="yearbars">${rets.map(r => `<div class="yb"><span class="ybbar ${r.ret_pct >= 0 ? "up" : "dn"}" style="height:${Math.min(100, Math.abs(r.ret_pct) / 2.2 + 6)}%"></span><i class="${cls(r.ret_pct)}">${r.ret_pct >= 0 ? "+" : ""}${Math.round(r.ret_pct)}%</i><em>${r.year.slice(2)}</em></div>`).join("")}</div></div>` : "";
    const cp = ex.company_profile || {};
    const inc = cp.incorporation?.value || cp.incorporation?.matched_text || "";
    const profile = (cp.business_description || inc) ? `<div class="glance-tile"><span class="glance-q">What does it do?</span>
      ${cp.business_description ? `<div class="sub" style="margin-bottom:5px">${esc(cp.business_description)}</div>` : ""}
      ${inc ? `<div class="sub" style="margin-bottom:5px">Incorporation: ${esc(inc)}</div>` : ""}
      <div class="sub">${cp.stale ? "Profile fetch is stale; showing last retained DPS profile. " : ""}Source: ${externalLink(cp.source_url, "DPS company page") || "DPS company page"}${cp.fetched ? ` · fetched ${esc(cp.fetched)}` : ""}</div>
    </div>` : "";
    return `<div class="seg" style="margin-top:2px"><h2>At a glance</h2><div class="ln"></div><span class="pill">plain english</span></div>
    <div class="card"><div class="sub">The quick read for ${esc(sym)}${ex.name ? " (" + esc(ex.name) + ")" : ""} — is it healthy, is the price reasonable, and what changed. Educational, not advice.</div>
      <div class="glance-grid">
        ${profile}
        ${tile("Is it healthy?", ex.health)}
        ${tile("Is the price reasonable?", ex.value)}
        ${tile("Which way is it moving?", ex.momentum)}
        ${tile("Does it pay income?", ex.income)}
        ${spark}
        <div class="glance-tile"><span class="glance-q">What changed recently</span>${(ex.what_changed || []).map(c => `<div class="sub" style="margin-bottom:3px">• ${esc(c)}</div>`).join("")}</div>
      </div></div>`;
  })() : "";
  // deep history (Yahoo, ~18y) preferred for chart + behavior; DPS as fallback
  const series = (deep && deep.length > (hist?.length || 0)) ? deep : hist;
  const yearsSpan = series ? ((new Date(series[series.length - 1].date) - new Date(series[0].date)) / 3.156e10) : 0;
  const f = fund?.tickers?.[sym] || {};
  // P/E here is the DESK's own live-price/EPS derivation (score_fundamentals.py live_pe), not the
  // vendor's scrape-time snapshot. Payout ratio is the vendor's figure as-is — payout is DPS/EPS
  // and has no price term, so there is nothing to re-derive off a live price (see 2026-08-01 fix).
  const fs = fscore?.tickers?.[sym]?.metrics || {};
  const today0 = todayPKT();
  const nextOfType = t => (cal?.events || [])
    .filter(e => e.ticker === sym && e.type === t && e.date >= today0)
    .sort((a, b) => a.date.localeCompare(b.date))[0];
  // earnings_calendar.json is the ONLY source these rows should read. Do not add a "fallback" to
  // fundamentals.json's next_earnings / ex_div_date: build_calendar.py already builds this file
  // from exactly those two fields, and it parses them better than JS can. Its parse_loose() rolls
  // a year-less "Aug 28" forward to the next occurrence, where new Date("Aug 28") yields 2001;
  // it also drops anything already past, which matters because 91 of the 94 scraped ex_div_date
  // values are stale — a fallback would print a months-old date under a label meaning "next".
  // A "—" here means the desk has no forward event for this ticker, which is the honest answer.
  const nextEarn = nextOfType("results");
  const nextXdiv = nextOfType("ex_dividend");
  const daysTo = d => d ? Math.ceil((new Date(d) - new Date()) / 86400000) : null;
  /* THE ALL-OR-NOTHING GUARD — narrowed, deliberately.

     This page fetches 24 files in one Promise.all and used to dead-end if EITHER quant or the
     price history was missing. That is why "Couldn't load market data for <SYM> just now" kept
     appearing on different tickers (UBL, then BML) even though every file for those names exists
     server-side: any ONE of 24 concurrent requests losing all three of its attempts threw away the
     other 23 and blanked a page that had everything it needed to render.

     Two sources carry price independently — quant.json (close, ret_1d) and live.json (ldcp, open,
     high, low) — and the chart needs only `series`. Losing one of those is a degraded page, not a
     dead one. So the hard stop now fires only when we have NO price from ANY source AND no series;
     everything softer renders what arrived and says plainly what did not.

     `_retry` still re-fetches in the background, so a genuinely transient miss self-heals while the
     visitor is already reading the parts that did load. */
  /* WHERE THE LINE SITS, and why it is not "render no matter what".

     Missing QUANT is survivable: it carries the close, the traded value and the volatility rank,
     and every consumer of those already falls back to "—". That was the reported failure — the
     screenshot said "market data", which is this branch — and it now renders.

     Missing HISTORY is not survivable, and pretending otherwise would be worse than the bug. The
     chart, the drawdown, the up-day share, the average daily move and the whole risk profile are
     all computed from the series. With it gone the page is a shell, and the only alternatives are
     to print a dozen "—" or to fabricate zeros. So this stops, says so, and retries.

     I tested the render-anyway version: it threw `null.toFixed` from the behaviour stats. Rather
     than scatter null-guards through a dozen formatting sites and hope none were missed, the
     dependency is stated honestly here. */
  if (!series || series.length < 2) {
    $("view").innerHTML = `<a class="crumb" href="/board">← board</a>
      <div class="card"><div class="empty">Couldn't load the price history for ${esc(sym)} just now.<br><br>
      Everything on a ticker page — the chart, the drawdown, the risk profile — is computed from it, so the desk would rather show you nothing than a page of dashes. This is almost always a network blip, not a missing stock.<br>
      <button class="acct-signin" id="tkretry" style="margin-top:12px">Retry</button></div></div>`;
    const btn = document.getElementById("tkretry");
    if (btn) btn.onclick = () => pageTicker(sym, 0);
    if (_retry < 3) setTimeout(() => { if (routeHash().toUpperCase().includes(sym)) pageTicker(sym, _retry + 1); }, 1200);
    return;
  }
  /* Partial load: render, but never let a missing file masquerade as a fact. The banner names
     exactly what is absent so nothing on the page is silently computed from a hole. */
  const _gaps = [];
  if (!qRaw) _gaps.push("the quant snapshot");
  if (!lv) _gaps.push("the live tape");
  /* ONE background retry, and only for the files that are actually missing. The old code re-ran
     the whole 26-file pageTicker up to three times, which tore down a page the reader was already
     looking at — repeatedly — for the sake of one absent file. Now the rendered page stays put; if
     the targeted re-fetch fills the gap the page refreshes once, and if it doesn't, the banner
     simply stays honest. */
  if (_gaps.length && _retry < 1) {
    const missing = [];
    if (!qRaw) missing.push("quant.json");
    if (!lv) missing.push("live.json");
    setTimeout(async () => {
      if (!routeHash().toUpperCase().includes(sym)) return;
      const got = await Promise.all(missing.map(f => j(f, 0).catch(() => null)));
      const filled = got.some(d => !!d?.tickers?.[sym]);
      if (!filled) return;                       // still absent — leave the honest banner alone
      if (routeHash().toUpperCase().includes(sym)) pageTicker(sym, 1);
    }, 1500);
  }
  const gapBanner = _gaps.length
    ? `<div class="card" id="tkgap" style="border-color:var(--dn)"><div class="sub" style="padding:10px 12px">
        Showing a partial page for ${esc(sym)}: ${_gaps.join(", ")} didn't load this time.
        ${_retry < 1 ? "The desk is retrying in the background — nothing below is estimated to fill the gap."
                     : "The retry didn't fill it either — nothing below is estimated to fill the gap."}
        <button class="acct-signin" id="tkretry" style="margin-left:8px">Retry now</button></div></div>`
    : "";

  // Price falls back across both sources rather than assuming quant is present.
  const px = lv?.current ?? q?.close ?? lv?.ldcp ?? (series?.length ? series[series.length - 1].close : null);
  const b = behaviorStats(series);
  const histYears = Math.max(1, Math.round(yearsSpan));
  const tickerNews = (news || []).filter(n => (n.tickers || []).includes(sym)).slice(-10).reverse();
  const dHist = (divs?.history || []).filter(d => d.symbol === sym);
  const dUp = (divs?.upcoming || []).filter(d => d.symbol === sym);
  // Mirrors room_dossier.py's recent_dividends "type" derivation from the same period code.
  const divType = p => ["I", "II", "III", "IV"].includes(p) ? "Interim" : p === "F" ? "Final" : "Unknown";
  const insiderRows = insiderAll?.symbols?.[sym] || [];
  // offmktAll is {days: {iso_date: {symbol: {shares, value, trades}}}} -- retained history, not
  // a single trailing-week snapshot. Aggregate this symbol's rows across every retained day.
  const offRetentionDays = offmktAll?.retention_days ?? 90;
  const offmkt = (() => {
    const days = offmktAll?.days || {};
    let shares = 0, value = 0, trades = 0, dayCount = 0;
    for (const d in days) {
      const row = days[d][sym];
      if (!row) continue;
      shares += row.shares; value += row.value; trades += row.trades; dayCount++;
    }
    return dayCount ? { shares, value, trades, dayCount } : null;
  })();
  /* backtests.json is ~4.8 MB — 62% of everything this page fetches — and its per-ticker results
     are only shown AFTER the "Run to reveal" click. `bt` above is now the small meta file (two
     numbers). Pull the real thing only when this ticker's run has actually been revealed, so a
     first visit costs 4.8 MB less and has one fewer fetch that can fail the whole page. */
  const btFull = stratRunOn(sym) ? await j("backtests.json") : null;
  const allTested = Object.entries(btFull?.templates || {}).map(([id, per]) => ({ id, ...(per[sym] || {}) })).filter(t => t.n).sort((a, b) => (b.net_expectancy_pct ?? -99) - (a.net_expectancy_pct ?? -99));
  const provenIds = new Set(proven.map(p => p.id));
  const hasIntra = intra && intra.date === live?.session_date && intra.points?.length > 3;

  // ---- educational / risk layer (all from the data layer; no advice language) ----
  const NUM = s => { const n = parseFloat(String(s).replace(/[^0-9.\-]/g, "")); return isNaN(n) ? null : n; };
  const epsN = NUM(f.eps), peN = NUM(f.pe), fpeN = NUM(f.forward_pe), betaN = NUM(f.beta),
    dyN = NUM(f.div_yield), payN = NUM(f.payout_ratio), niN = NUM(f.net_income);
  const tvv = q.avg_daily_traded_value || 0;
  const liq = tvv < 20e6 ? "low" : tvv < 150e6 ? "moderate" : "adequate";
  const vr = q.volatility_rank;
  const vol = vr == null ? null : vr < 20 ? "low" : vr < 50 ? "moderate" : "high";
  const peerFair = fv?.methods?.relative_pe;
  const peerRich = (peerFair != null && fv?.price) ? peerFair < fv.price : null;   // fair-vs-peers below price ⇒ priced above peers
  const mddAbs = Math.abs(b.mdd);
  const mddRecentAbs = Math.abs(b.mddRecent);
  const mddIsOld = yr(b.mddTrough) && (new Date().getFullYear() - +yr(b.mddTrough)) >= 6;
  const mddContext = `${mddAbs.toFixed(0)}% (peak ${yr(b.mddPeak)}→trough ${yr(b.mddTrough)}${mddIsOld ? `, an old extreme` : ""})${mddIsOld && mddRecentAbs > 5 ? `; ${mddRecentAbs.toFixed(0)}% in the last decade` : ""}`;
  const lossmaking = epsN != null && epsN <= 0;
  const priceSrc = lv?.current != null ? "DPS snapshot as of " + esc(live?.source_at || "unknown") : "last available end-of-day close " + esc(q.date || "unknown");

  // "What the data flags" — factual observations, not predictions
  const pros = [], cons = [];
  if (proven.length) pros.push(`${proven.length} strateg${proven.length > 1 ? "ies have" : "y has"} been historically profitable on ${sym}`);
  if (fv && fv.mispricing_pct > 0) pros.push(`Trades ${Math.abs(fv.mispricing_pct)}% below the model's blended fair value`);
  if (fpeN != null && peN != null && fpeN < peN) pros.push(`Market expects earnings to grow (forward P/E ${f.forward_pe} below trailing ${f.pe})`);
  if (dyN != null && dyN >= 5 && payN != null && payN < 85) pros.push(`Above-average dividend yield (${f.div_yield}), covered by earnings`);
  if (betaN != null && betaN < 0.7) pros.push(`Historically calmer than the market (beta ${f.beta})`);
  if (payN != null && payN > 90) cons.push(`Dividend payout is stretched (${f.payout_ratio} of earnings)`);
  if (vol === "high") cons.push(`High price volatility (rank ${vr.toFixed(0)}/100)`);
  if (liq === "low") cons.push(`Low trading liquidity — can be hard to buy or sell quickly`);
  if (peerRich === true) cons.push(`Valued above sector peers on P/E`);
  if (mddRecentAbs >= 45) cons.push(`Has fallen ${mddRecentAbs.toFixed(0)}% peak-to-trough within the last decade`);
  if (betaN != null && betaN > 1.3) cons.push(`Amplifies market swings (beta ${f.beta})`);
  if (lossmaking) cons.push(`Currently lossmaking (EPS ${f.eps})`);
  // Insider/off-market: metadata only, no direction inferred (desk hard-rule) -- these land as
  // neutral "info" flags, never pro/con, since a filing or an off-market print says nothing about
  // intent on its own.
  const infos = [];
  const cutoff30 = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);
  const recentInsider = insiderRows.filter(r => r.date && r.date >= cutoff30);
  if (recentInsider.length) infos.push(`${recentInsider.length} insider/substantial-shareholder filing${recentInsider.length > 1 ? "s" : ""} in the last 30 days`);
  if (offmkt) infos.push(`Off-market: ${offmkt.shares.toLocaleString()} shares · Rs ${offmkt.value.toLocaleString()} across ${offmkt.dayCount} day${offmkt.dayCount === 1 ? "" : "s"} (trailing ${offRetentionDays}d)`);
  const flagList = (arr, kind) => arr.length
    ? arr.map(t => `<div class="flag ${kind}"><span>${kind === "pro" ? "▲" : kind === "con" ? "▼" : "●"}</span>${esc(t)}</div>`).join("")
    : `<div class="sub" style="padding:6px 0">No notable data flags on this measure.</div>`;

  // Questions before buying — data-answered, informational
  const qmark = (s, label, ans) => `<div class="qrow"><div class="qmark ${s}">${s === "ok" ? "✓" : s === "warn" ? "!" : "?"}</div><div><b>${label}</b><div class="sub">${ans}</div></div></div>`;
  const checklist = [
    lossmaking ? qmark("warn", "Is profit positive and growing?", `Reported a net loss — earnings are currently negative (EPS ${f.eps}).`)
      : niN != null ? qmark(fpeN != null && peN != null && fpeN < peN ? "ok" : "info", "Is profit positive and growing?",
        `Reported positive net income (${f.net_income}).${fpeN != null && peN != null && fpeN < peN ? ` Forward P/E ${f.forward_pe} below trailing ${f.pe} — the market expects earnings to rise.` : " Multi-year growth trend isn't in the feed — check the latest results."}`)
      : qmark("info", "Is profit positive and growing?", "Earnings data unavailable in the feed right now."),
    qmark(niN != null && niN > 0 ? "info" : "warn", "Is the company generating cash?",
      `Net income is ${f.net_income || "—"}. The feed has no cash-flow statement, so treat net income only as a proxy — confirm operating cash flow before relying on it.`),
    qmark("info", "Is debt manageable?", "Balance-sheet debt isn't in the desk's feed. Don't assume leverage is safe — open the company's latest financials."),
    peerRich === true ? qmark("warn", "Is the stock expensive versus peers?", `On the peer-P/E model it screens above sector peers (model fair ~Rs ${fmt(peerFair)} vs price Rs ${fmt(fv.price)}).`)
      : peerRich === false ? qmark("ok", "Is the stock expensive versus peers?", "In line with or below sector peers on the peer-P/E model.")
        : qmark("info", "Is the stock expensive versus peers?", "Peer valuation unavailable for this name."),
    payN == null || (dyN != null && dyN === 0) ? qmark("info", "Is the dividend sustainable?", "Pays no dividend on record right now.")
      : payN > 90 ? qmark("warn", "Is the dividend sustainable?", `Payout ratio ${f.payout_ratio} — most of earnings are paid out, leaving little buffer if profits dip. ${dHist.length} payouts on record.`)
        : qmark("ok", "Is the dividend sustainable?", `Payout ratio ${f.payout_ratio}, yield ${f.div_yield || "—"} — covered by earnings. ${dHist.length} payouts on record.`),
    qmark(mddRecentAbs >= 30 ? "warn" : "info", "Can I tolerate a 30–50% decline?",
      `${sym}'s worst drop in the last decade was ${mddRecentAbs.toFixed(0)}% (to ${yr(b.mddRecentTrough)})${mddIsOld ? `; its all-time worst was ${mddAbs.toFixed(0)}% back in the ${yr(b.mddTrough)} era` : ""}. Only commit money you can hold through a fall like that.`),
    qmark("info", "What is my time horizon?", "This desk is daily-timeframe swing research — not day-trading, and not a buy-and-forget rating. Match any position to your own horizon and risk tolerance."),
  ].join("");

  /* ---- The beginner's checklist: seven traffic lights, no ratios on the surface ----
     Green / amber / grey, each with one plain sentence. Grey means "the desk cannot answer this
     from its data" — it is never dressed up as a pass, because an unknown is not a green light.
     Ratios stay available underneath for anyone who wants them. */
  const LIGHTS = [
    (() => {          // 1. business understandable — honest: only the user can answer this
      const sec = mySector;
      return { k: "Business you can explain", s: "ask", why: sec
        ? `${sym} operates in ${sec}. Can you say in one sentence how it earns money? If not, that is a reason to keep reading, not to buy.`
        : `Can you say in one sentence how ${sym} earns money? Only you can answer this one — and it is the first question, not the last.` };
    })(),
    lossmaking ? { k: "Earnings growing", s: "no", why: `Currently lossmaking (EPS ${f.eps}). A company can recover, but it is not earning today.` }
      : niN != null ? (fpeN != null && peN != null && fpeN < peN
        ? { k: "Earnings growing", s: "yes", why: `Profitable, and the market expects more: forward P/E ${f.forward_pe} sits below trailing ${f.pe}.` }
        : { k: "Earnings growing", s: "part", why: `Profitable (net income ${f.net_income}), but the desk's feed has no multi-year growth trend — check the last three annual reports.` })
        : { k: "Earnings growing", s: "unk", why: "Earnings data is not in the desk's feed for this name right now." },
    { k: "Debt healthy", s: "unk", why: "Balance-sheet debt is not in the desk's feed. This is a real gap — open the company's latest balance sheet and compare total debt against equity before assuming it is safe." },
    (dyN != null && dyN > 0)
      ? (payN != null && payN > 90
        ? { k: "Pays a dividend", s: "part", why: `Yields ${f.div_yield}, but pays out ${f.payout_ratio} of earnings — little buffer if profits dip. ${dHist.length} payouts on record.` }
        : { k: "Pays a dividend", s: "yes", why: `Yields ${f.div_yield}${payN != null ? `, covered by earnings (payout ${f.payout_ratio})` : ""}. ${dHist.length} payouts on record.` })
      : { k: "Pays a dividend", s: "no", why: "No dividend on record. Not a fault — younger or reinvesting companies often pay none — but this will not produce income." },
    fv ? (fv.verdict === "overvalued"
      ? { k: "Fairly valued", s: "no", why: `Priced ${Math.abs(fv.mispricing_pct)}% ABOVE the desk's blended model fair value of Rs ${fmt(fv.composite_fair)}.` }
      : fv.verdict === "undervalued"
        ? { k: "Fairly valued", s: "yes", why: `Priced ${Math.abs(fv.mispricing_pct)}% below the blended model fair value of Rs ${fmt(fv.composite_fair)} — cheap on the model, which is not the same as a good business.` }
        : { k: "Fairly valued", s: "part", why: `Close to the blended model fair value of Rs ${fmt(fv.composite_fair)}.` })
      : { k: "Fairly valued", s: "unk", why: "The fair-value model could not be built for this name." },
    { k: "Risk you can sit through", s: mddRecentAbs >= 50 ? "no" : mddRecentAbs >= 30 ? "part" : "yes",
      why: `Worst fall in the last decade was ${mddRecentAbs.toFixed(0)}%${vol ? `, and it moves ±${b.avgAbs.toFixed(1)}% on an average day (${vol} volatility)` : ""}. Could you hold through that without selling?` },
    { k: "Easy to buy and sell", s: liq === "low" ? "no" : liq === "moderate" ? "part" : "yes",
      why: `About Rs ${fmt(tvv / 1e6, 0)}M changes hands daily. ${liq === "low" ? "Thin — getting out quickly can move the price against you." : liq === "moderate" ? "Moderate depth; large orders may still move it." : "Deep enough to enter and exit readily."}` },
  ];
  const LIGHT_LABEL = { yes: "yes", no: "no", part: "partly", unk: "unknown", ask: "your call" };
  const nGreen = LIGHTS.filter(x => x.s === "yes").length, nRed = LIGHTS.filter(x => x.s === "no").length,
    nGrey = LIGHTS.filter(x => x.s === "unk" || x.s === "ask").length;
  const lightsCard = `
  <div class="seg"><h2>The beginner's checklist</h2><div class="ln"></div><span class="pill">${nGreen} green · ${nRed} red · ${nGrey} unanswered</span></div>
  <p class="sub" style="margin-bottom:12px">Seven questions in plain language, answered from the desk's data. <b>Grey is not a pass</b> — it means the desk cannot answer it, and you should go and find out. This is a thinking checklist, never a score to buy on.</p>
  <div class="card lights">${LIGHTS.map(x => `<div class="lrow s-${x.s}">
      <span class="ldot">${x.s === "yes" ? "✓" : x.s === "no" ? "✕" : x.s === "part" ? "~" : "?"}</span>
      <div class="lbody"><b>${esc(x.k)}</b><span class="sub">${esc(x.why)}</span></div>
      <span class="lstate">${LIGHT_LABEL[x.s]}</span></div>`).join("")}
    <div class="sub lights-foot">Educational only — not a recommendation, not a rating, and not a substitute for reading the company's own filings.</div>
  </div>`;

  // Risk profile — more than volatility; honest gaps
  const rl = (k, t) => `<span class="rlvl ${k}">${t}</span>`;
  const NA = '<span class="sub">not scored</span>';
  const rrow = (factor, chip, text) => `<tr><td style="width:180px;vertical-align:top"><b>${factor}</b></td><td style="width:96px;vertical-align:top">${chip}</td><td class="sub">${text}</td></tr>`;
  const riskRows = [
    rrow("Price volatility", vol ? rl(vol === "high" ? "hi" : vol === "moderate" ? "md" : "lo", vol) : NA,
      `Average daily move ±${b.avgAbs.toFixed(1)}%${vr != null ? ` (volatility rank ${vr.toFixed(0)}/100 across the universe)` : ""}.`),
    rrow("Maximum decline", rl(mddRecentAbs > 60 ? "hi" : mddRecentAbs > 35 ? "md" : "lo", mddRecentAbs > 60 ? "severe" : mddRecentAbs > 35 ? "large" : "moderate"),
      `Worst drawdown ${mddContext}. A drop of this size can recur.`),
    rrow("Liquidity", rl(liq === "low" ? "hi" : liq === "moderate" ? "md" : "lo", liq === "adequate" ? "adequate" : liq),
      `~Rs ${fmt(tvv / 1e6, 0)}M traded per day. ${liq === "low" ? "Thin — exiting quickly may move the price against you." : liq === "moderate" ? "Moderate depth." : "Deep enough to enter and exit readily."}`),
    rrow("Market sensitivity", betaN != null ? rl(betaN > 1.3 ? "hi" : betaN > 0.8 ? "md" : "lo", "beta " + f.beta) : NA,
      betaN != null ? `${betaN > 1 ? "Tends to move more than" : "Tends to move less than"} the broad market.` : "Beta not available."),
    rrow("Valuation", fv ? (fv.verdict === "overvalued" ? rl("hi", "above fair") : fv.verdict === "undervalued" ? rl("lo", "below fair") : rl("md", "near fair")) : NA,
      fv ? `Blended model fair value Rs ${fmt(fv.composite_fair)} vs price Rs ${fmt(fv.price)} (${sgn(fv.mispricing_pct)}%). A low share price does not mean a cheap company — value depends on earnings, not the rupee price.` : "Fair-value model unavailable."),
    rrow("Dividend reliability", dHist.length >= 4 ? rl("lo", "established") : dHist.length ? rl("md", "limited") : NA,
      dHist.length ? `${dHist.length} dividends on record; most recent closure ${dHist[0]?.bc_start || "—"}.` : "No payout on record."),
    rrow("Debt / leverage", NA, "Balance-sheet debt is not in the desk's data feed — review the latest financial statements before relying on any leverage assumption."),
    rrow("Earnings stability", NA, "A multi-year earnings series isn't in the feed yet, so year-to-year stability can't be scored here."),
  ].join("");

  // ---- 5-item summary strip: the whole story in one glance, before anything else ----
  let rg = "Moderate", rgk = "md";
  if (vr != null) { if (vr < 20) { rg = "Lower"; rgk = "lo"; } else if (vr >= 50) { rg = "Higher"; rgk = "hi"; } }
  if (liq === "low" || mddRecentAbs >= 55) { rg = "Higher"; rgk = "hi"; }
  const daysToEarn = nextEarn ? daysTo(nextEarn.date) : null;
  // The Room ends at the bull/bear debate now (no Chair house view) — bull_case marks a covered
  // session, and that presence, not a verdict, is what the reveal bar and Signal Stack key off.
  const hasRoom = !!(room && room.bull_case);
  const sTile = (label, val, sub, k) => `<div class="sumtile"><span class="sk">${label}</span><b class="${k || ""}">${val}</b>${sub ? `<i>${sub}</i>` : ""}</div>`;
  // hard facts only — the lens verdicts live in the Signal Stack, and the desk's own view stays
  // behind its run (a tile here would spoil it)
  const summaryStrip = `<div class="sumstrip s4">
    ${sTile("Fair value vs price", fv ? `Rs ${fmt(fv.composite_fair)}` : "—", fv ? `price Rs ${fmt(fv.price)} · ${sgn(fv.mispricing_pct)}%` : "model n/a", fv ? (fv.verdict === "undervalued" ? "up" : fv.verdict === "overvalued" ? "dn" : "") : "")}
    ${sTile("Scorecard", fsc ? ({ attractive: "Stronger", caution: "Weaker", neutral: "Mixed", mixed: "Mixed" }[fsc.rating] || fsc.rating) : "—", fsc ? "business quality" : "not scored", fsc ? (fsc.rating === "attractive" ? "up" : fsc.rating === "caution" ? "dn" : "") : "")}
    ${sTile("Risk grade", rg, vr != null ? `volatility ${vr.toFixed(0)}/100` : "liquidity " + liq, rgk === "hi" ? "dn" : rgk === "lo" ? "up" : "")}
    ${sTile("Next event", nextEarn ? "Results" : "—", nextEarn ? `${nextEarn.date}${daysToEarn != null ? ` · ${daysToEarn}d` : ""}` : "none scheduled", "")}
  </div>`;

  // ---- private per-ticker note (only you can see it) ----
  const noteCard = me
    ? `<div class="seg"><h2>Your private note</h2><div class="ln"></div><span class="pill">only you can see this</span></div>
    <div class="card"><textarea id="tknote" class="tknote" placeholder="Private notes on ${esc(sym)} — your own thesis, price levels you care about, reminders. Saved to your account, visible only to you.">${esc(noteFor(sym))}</textarea>
      <div class="tknote-bar"><button class="note-save" onclick="saveTickerNote('${esc(sym)}')">Save note</button><span id="tknote-status" class="sub"></span></div></div>`
    : `<div class="seg"><h2>Your private note</h2><div class="ln"></div></div>
    <div class="card"><div class="empty">Sign in to keep a private note on ${esc(sym)} — your own thesis and reminders, saved to your account and visible only to you.<br><br><button class="auth-go" style="max-width:220px" onclick="openAuth('signup')">Create a free account</button></div></div>`;

  /* ---- The Desk Room reveal bar.
     PUBLICATION FRAME (docs/PUBLICATION_RESTRUCTURE.md §4). This button has never triggered
     anything: it renders only when `hasRoom` is true — i.e. when the session is ALREADY in
     state/rooms.json — and playDeskReplay() replays a debate that was written on the desk's own
     editorial schedule by room_queue.py, identically for every subscriber.
     The old copy ("Run the desk on FFC", "Run ›", "Once it finishes…") claimed the opposite:
     on-demand analysis performed for this reader. That is the advisory framing the restructure
     exists to remove, and it was never even true — the desk was publication-shaped underneath and
     marketing itself as something riskier than it is.
     So: reveal is described as reveal, and the publication date leads. ---- */
  const lastRun = room ? String(room.built || room.dossier_asof || "").slice(0, 16) : "";
  const deskRan = (() => { try { return !!sessionStorage.getItem("deskran:" + sym); } catch (e) { return false; } })();
  const runDeskBar = hasRoom ? `<button class="run-desk ${deskRan ? "ran" : ""}" onclick="playDeskReplay('${esc(sym)}')">
    <span class="run-ico">▶</span>
    <span class="run-txt"><b>The desk's debate on ${esc(sym)}</b><i>A chartist and a fundamentalist work ${esc(sym)} separately, then a bull and a bear argue it out. Watch the debate play out — no verdict, no call.</i></span>
    <span class="run-meta">${lastRun ? `<span class="run-last">Published · ${esc(lastRun)}</span>` : ""}<span class="run-go">${deskRan ? "Replay ›" : "Read ›"}</span></span>
  </button>` : "";
  const deskStub = `<div class="seg"><h2>The Desk Room</h2><div class="ln"></div><span class="pill">AI analysts · research, not advice</span></div>
    <div class="card"><div class="empty">The desk's published debate on ${esc(sym)} — open it with <b>Read ›</b> near the top ↑. The full analyst argument, both sides, appears right here.</div></div>`;

  // ---- The strategy-library reveal bar. Same correction: playStrategyRun() reads the backtests
  // already computed by backtest.py in the deterministic cycle. It does not run a backtest. ----
  const stratRan = stratRunOn(sym);
  const runStratBar = `<button class="run-desk run-strat ${stratRan ? "ran" : ""}" onclick="playStrategyRun('${esc(sym)}')">
    <span class="run-ico">▶</span>
    <span class="run-txt"><b>The strategy library on ${esc(sym)}</b><i>All ${bt?.n_strategies ?? 52} of the desk's strategies, backtested across ${esc(sym)}'s ~19-year history — which held up, and which did not.</i></span>
    <span class="run-meta"><span class="run-go">${stratRan ? "Replay ›" : "Read ›"}</span></span></button>`;
  const stratStub = `<div class="card"><div class="empty">All ${bt?.n_strategies ?? 52} strategies, backtested on ${esc(sym)}'s history — open the results with <b>Read ›</b> above ↑.</div></div>`;

  /* ---- The Signal Stack: every lens the desk has on this name, in ONE grammar
     (lean · conviction · why), so they can be read against each other in five seconds.
     Every lean is computed mechanically from the data layer — nothing here is invented,
     and the note always names exactly what drove it. Lenses the user hasn't run stay
     locked, because the desk's own view is worth watching happen. ---- */
  const liveSig = ((sigAll?.active) || []).find(s => s.ticker === sym);
  const stanceVal = s => /constructive|positive|bullish/i.test(s || "") ? 1 : /cautious|negative|bearish/i.test(s || "") ? -1 : 0;
  const leanChip = n => n > 0 ? { k: "up", v: "Bullish" } : n < 0 ? { k: "dn", v: "Bearish" } : { k: "", v: "Neutral" };

  // 1. Charts (quant layer — booleans straight off the indicator file)
  const taLean = (q.above_sma20 ? 1 : -1) + (q.above_sma50 ? 1 : -1);
  const rsiTxt = q.rsi14 != null ? `RSI14 ${q.rsi14.toFixed(0)}${q.rsi14 >= 70 ? " overbought" : q.rsi14 <= 30 ? " oversold" : ""}` : "RSI n/a";
  const taLens = { ...leanChip(taLean), conv: Math.abs(taLean) === 2 ? "medium" : "low",
    note: `${q.above_sma50 ? "above" : "below"} SMA50 · ${q.above_sma20 ? "above" : "below"} SMA20 · ${rsiTxt} · 20-day ${sgn(q.ret_20d)}%` };

  // 2. Value (fair-value composite, corroborated by the business scorecard)
  const fvLean = fv ? (fv.verdict === "undervalued" ? 1 : fv.verdict === "overvalued" ? -1 : 0) : 0;
  const fsLean = fsc ? (fsc.rating === "attractive" ? 1 : fsc.rating === "caution" ? -1 : 0) : 0;
  const fscWord = fsc ? ({ attractive: "stronger", caution: "weaker" }[fsc.rating] || "mixed") + " scorecard" : "not scored";
  const faLens = !fv ? { k: "", v: "No model", conv: "", note: "The fair-value model can't price this name — earnings data is missing or negative." }
    : { ...leanChip(fvLean), v: fvLean > 0 ? "Bullish" : fvLean < 0 ? "Bearish" : "Fair",
      conv: fvLean !== 0 && fsLean === fvLean ? "high" : fvLean !== 0 ? "medium" : "low",
      note: `${Math.abs(fv.mispricing_pct)}% ${fv.mispricing_pct > 0 ? "below" : "above"} the model's blended fair value · ${fscWord}` };

  // 3. The Desk Room (gated — the debate is the product)
  const taSt = room?.ta_memo?.technical_stance, faSt = room?.fa_memo?.fundamental_stance;
  const deskLean = stanceVal(taSt) + stanceVal(faSt);
  const roomLens = !hasRoom ? { k: "", v: "In queue", conv: "", note: `${esc(sym)} hasn't been through the Desk Room yet — the analysts cover names in rotation, and results or high-impact news jump the queue.` }
    : !deskRan ? { locked: true, run: `playDeskReplay('${esc(sym)}')`, note: "A chartist and a fundamentalist work it separately, then a bull and a bear argue it out. Read the debate to see where each desk landed." }
      : { ...leanChip(deskLean), v: deskLean > 0 ? "Constructive" : deskLean < 0 ? "Cautious" : "Split",
        conv: "", note: `charts read ${esc(taSt || "—")} · fundamentals read ${esc(faSt || "—")} — the debate, not a verdict` };

  // 4. Strategies (gated — directional only when a proven rule is actually firing today)
  const topProven = proven[0];
  const stratLens = !stratRan ? { locked: true, run: `playStrategyRun('${esc(sym)}')`, note: `Backtest all ${bt?.n_strategies ?? 52} of the desk's strategies on ${esc(sym)}'s own ~19 years and see which held up.` }
    : liveSig ? { k: "up", v: "Firing now", conv: esc(liveSig.confidence || "medium"),
      note: `${esc(liveSig.template)} triggered today · won ${Math.round((liveSig.backtest?.hit_rate || 0) * 100)}% over ${liveSig.backtest?.n} past trades on ${esc(sym)}` }
      : proven.length ? { k: "", v: "Edge, not firing", conv: "",
        note: `${proven.length} rule set${proven.length > 1 ? "s have" : " has"} held up here — ${esc(topProven.name)} leads (${Math.round(topProven.hit_rate * 100)}% win, ${sgn(topProven.net_expectancy_pct)}%/trade) — but none is triggering today.` }
        : { k: "", v: "No edge", conv: "", note: `Not one of the ${bt?.n_strategies ?? 52} strategies cleared the bar on ${esc(sym)}'s history. That's a finding, not a gap.` };

  // 5. Brokers (public calls on the record — evidence to weigh, and every one of them is scored)
  const brokDir = brokerClaims.map(c => c.claim?.direction).filter(Boolean);
  const brokUp = brokDir.filter(d => /up|buy|overweight/i.test(d)).length;
  const brokDn = brokDir.filter(d => /down|sell|underweight/i.test(d)).length;
  const brokLens = !brokerClaims.length ? { k: "", v: "None on record", conv: "", note: "No PSX research house has a public call on this name in the desk's log." }
    : { ...leanChip(brokUp - brokDn), conv: brokerClaims.length >= 3 ? "medium" : "low",
      note: `${brokUp} positive · ${brokDn} negative of ${brokerClaims.length} on record — latest: ${esc(brokerClaims[brokerClaims.length - 1].source)}${brokerClaims[brokerClaims.length - 1].claim?.target_price ? ", target Rs " + fmt(brokerClaims[brokerClaims.length - 1].claim.target_price) : ""}` };

  // 6. Insider & off-market — metadata only (desk hard-rule: no direction inferred from a filing
  // or an off-market print alone). Kept out of the confluence for the same reason Astro is: it
  // makes no edge claim, just states what's on file.
  const insiderLens = (!recentInsider.length && !offmkt) ? { k: "", v: "Nothing on file", conv: "",
    note: `No insider/substantial-shareholder filings in the last 30 days, no off-market trades in the trailing ${offRetentionDays}d.` }
    : { k: "", v: "On file", conv: "",
      note: [recentInsider.length ? `${recentInsider.length} filing${recentInsider.length > 1 ? "s" : ""} in last 30d` : null,
        offmkt ? `${offmkt.shares.toLocaleString()} shares off-market (Rs ${offmkt.value.toLocaleString()}) over ${offmkt.dayCount}d, trailing ${offRetentionDays}d` : null]
        .filter(Boolean).join(" · ") + " — metadata only, no direction inferred" };

  // 7. Astro — a pointer to the immersive astrological reading, not a tested signal. Kept out of the
  // confluence (it makes no edge claim); framed as an exploration lens, never desk analytics.
  const astroLens = { k: "", v: "reading", conv: "",
    note: `The tradition's read of ${esc(sym)}'s chart — explore it on the <a href="/astro" style="color:var(--accent)">Astro</a> board, or against your own in <a href="/mychart" style="color:var(--accent)">Your Chart</a>.` };

  const LENSES = [
    ["Charts · TA", taLens], ["Value · FA", faLens], ["The Desk Room", roomLens],
    ["Strategies", stratLens], ["Brokers", brokLens], ["Insider & off-market", insiderLens], ["Astro", astroLens],
  ];
  // confluence counts only lenses that are BOTH revealed and directional — an honest denominator
  const revealed = LENSES.filter(([, o]) => !o.locked && (o.k === "up" || o.k === "dn"));
  const bullN = revealed.filter(([, o]) => o.k === "up").length, bearN = revealed.filter(([, o]) => o.k === "dn").length;
  const lockedN = LENSES.filter(([, o]) => o.locked).length;
  const oneWay = (n, word, k) => n === 1
    ? `<b class="${k}">The only lens that leans, leans ${word}.</b> One lens is a hint, not a case.`
    : `<b class="${k}">All ${n} lenses that lean, lean ${word}.</b> Agreement is not proof — they can be wrong together.`;
  const confTxt = !revealed.length ? `Nothing leans either way yet${lockedN ? ` — ${lockedN} lens${lockedN > 1 ? "es are" : " is"} still unrun` : ""}.`
    : bullN && !bearN ? oneWay(bullN, "bullish", "up")
      : bearN && !bullN ? oneWay(bearN, "bearish", "dn")
        : `<b>${bullN} bullish vs ${bearN} bearish</b> — the lenses disagree. That's information: the case isn't settled.`;
  const sigRow = (lens, o) => o.locked
    ? `<div class="sig-row locked clickable" onclick="${o.run}"><span class="sig-lens">${lens}</span>
        <span class="sig-chip lock">▶ Run to reveal</span><span class="sig-conv"></span><span class="sig-note">${o.note}</span></div>`
    : `<div class="sig-row"><span class="sig-lens">${lens}</span>
        <span class="sig-chip ${o.k}">${o.v}</span><span class="sig-conv">${o.conv ? esc(o.conv) + " conviction" : ""}</span><span class="sig-note">${o.note}</span></div>`;
  const sigStack = `<div class="seg" style="margin-top:2px"><h2>The Signal Stack</h2><div class="ln"></div><span class="pill">every lens · one view</span></div>
    <div class="card sigstack">
      ${LENSES.map(([n, o]) => sigRow(n, o)).join("")}
      <div class="sig-conf"><span class="sig-lens">Confluence</span><span class="sig-note">${confTxt}${lockedN ? ` <span class="sig-locknote">${lockedN} lens${lockedN > 1 ? "es" : ""} still to run.</span>` : ""}</span></div>
    </div>`;
  const stratCards = `<div class="card"><div class="sub">Of the desk's ${bt?.n_strategies ?? 52} tested strategies, these cleared the bar on ${sym}'s own ~19-year history — win rate ≥55%, positive expectancy after costs, AND still profitable in the unseen last third (out-of-sample). This is what actually worked here, not theory.</div>
    ${proven.length ? `<table><thead><tr><th>Strategy</th><th>Type</th><th class="r">Win rate</th><th class="r">Avg net/trade</th><th class="r">Trades</th><th class="r">Out-of-sample</th></tr></thead><tbody>${
      proven.map(t => `<tr><td><b>${esc(t.name)}</b></td><td><span class="tag">${esc(t.category.replace("_", " "))}</span></td>
        <td class="r num">${Math.round(t.hit_rate * 100)}%</td><td class="r num up">${sgn(t.net_expectancy_pct)}%</td>
        <td class="r num">${t.n}</td><td class="r num">${t.oos_hit != null ? Math.round(t.oos_hit * 100) + "% · n" + t.oos_n : "—"}</td></tr>`).join("")}</tbody></table>`
      : '<div class="empty">No strategy cleared the bar on this name — the desk would not signal it. That is a finding, not a gap: its history is too choppy for these rules.</div>'}</div>
  ${allTested.length > proven.length ? `<div class="card"><h2 style="font-size:13px">All ${allTested.length} strategies tested here</h2><div class="sub">full transparency — including the ones that failed. <span class="pill ok">proven</span> = made the cut.</div>
    <table><thead><tr><th>Strategy</th><th class="r">Win</th><th class="r">Net</th><th class="r">n</th><th class="r">Verdict</th></tr></thead><tbody>${
    allTested.slice(0, 20).map(t => `<tr><td>${esc(t.name || t.id)}</td><td class="r num">${t.hit_rate != null ? Math.round(t.hit_rate * 100) + "%" : "—"}</td>
      <td class="r num ${(t.net_expectancy_pct || 0) > 0 ? "up" : "dn"}">${sgn(t.net_expectancy_pct ?? 0)}%</td><td class="r num">${t.n}</td>
      <td class="r">${provenIds.has(t.id) ? '<span class="pill ok">proven</span>' : '<span style="opacity:.45">rejected</span>'}</td></tr>`).join("")}</tbody></table></div>` : ""}
  ${renderTestLog(sym, allTested, stratLib, bt?.bars)}`;

  /* Coverage honesty. The universe covers every KSE All Share constituent, but the expensive
     analysis (deep backtests, fundamentals, fair value, Desk Room) runs only on the core tier.
     Say that plainly on a wider-coverage name instead of letting empty sections imply the desk
     looked and found nothing. */
  const coverageNote = (u?.tier === "listed" && !lq?.research_eligible) ? `
  <div class="tnote"><b>Wider-coverage name.</b> ${esc(sym)} is a listed PSX company outside the
  KSE100 and KMI30 that does not clear the desk's liquidity bar for deep research, so the desk
  carries its <b>prices, quant measures, sector and payout history</b> — but not the backtests,
  fundamental scores, model fair value or Desk Room debate. Sections that need those will say so
  rather than guess. The desk covers the whole market so nothing is invisible; it does not pretend
  to research every name equally.</div>` : "";

  /* Tradeability. A thin name must say WHY it carries no setup instead of showing an empty
     signal section, which reads as "the desk looked and found nothing" when the truth is
     "the desk will not trade something this thin at any price". */
  const liqCard = lq ? (() => {
    const g = lq.grade, low = g === "D" || g === "E";
    const bucket = { highly_liquid: "Highly liquid", moderately_liquid: "Moderately liquid", illiquid: "Illiquid" }[lq.sec_bucket] || "—";
    const pos = liqAll?.max_position_value_pkr;
    const shareOfDay = (pos && lq.adtv_pkr) ? (pos / lq.adtv_pkr) * 100 : null;
    return `<div class="card"><h2 style="font-size:13px">Can you actually trade it?</h2>
    <div class="sub">Turnover says how much you can buy; the spread says what it costs you. Both are measured from ${esc(String(liqAll?.window_sessions || 60))} sessions of this stock's own tape.</div>
    <div class="liq-grid">
      <div class="liq-cell"><span class="liq-k">Liquidity grade</span><b class="liq-v ${low ? "dn" : "up"}">${esc(g || "—")}</b></div>
      <div class="liq-cell"><span class="liq-k">Typical day's turnover</span><b class="liq-v">Rs ${fmt(lq.adtv_m)}M</b></div>
      <div class="liq-cell"><span class="liq-k">Est. round-trip cost</span><b class="liq-v ${(lq.spread_pct ?? 0) > 1.5 ? "dn" : ""}">${lq.spread_pct != null ? lq.spread_pct.toFixed(2) + "%" : "unknown"}</b></div>
      <div class="liq-cell"><span class="liq-k">Sessions to exit a full position</span><b class="liq-v ${(lq.days_to_liquidate_stress ?? 0) > 7 ? "dn" : ""}">${lq.days_to_liquidate_stress == null ? "—" : lq.days_to_liquidate_stress < 1 ? "under 1" : fmt(lq.days_to_liquidate_stress)}</b></div>
    </div>
    <div class="sub" style="margin-top:9px">Classified <b>${esc(bucket)}</b> on the SEC's Rule 22e-4 test, measured at the stressed 10%-of-volume rate rather than the comfortable one.${
      shareOfDay != null ? ` A full position here would be <b>${shareOfDay < 1 ? "under 1" : Math.round(shareOfDay)}%</b> of everything that trades in a normal day.` : ""}</div>
    ${!lq.signal_eligible ? `<div class="tnote" style="margin-top:10px"><b>No setups will be published on this name.</b>
      It trades below the desk's liquidity floor, so even a strategy that backtests well here is one you
      could not enter or exit at the tested price. That is a deliberate refusal, not missing analysis.</div>` : ""}
    ${lq.spread_pct != null && lq.spread_pct > 0.6 ? `<div class="sub" style="margin-top:8px">Its backtests are charged <b>${lq.spread_pct.toFixed(2)}%</b> per round trip rather than the desk's ${esc(String(bt?.bars?.friction_pct ?? 0.6))}% floor — a wide spread eats a breakout strategy's edge first, so pretending otherwise would flatter exactly the names that deserve it least.</div>` : ""}
    </div>`;
  })() : "";

  $("view").innerHTML = `
  <a class="crumb" href="/board">← board</a>
  ${gapBanner}
  <div class="card">
    <div class="tk-head">
      <span class="sym">${sym}</span>
      <span class="px num">${fmt(px)}</span>
      <span class="num ${cls(q.ret_1d)}" style="font-size:16px;font-weight:700">${sgn(q.ret_1d)}%</span>
      <span class="tag">${esc(u?.name || "")}</span>${mySector ? `<span class="tag">${esc(mySector)}</span>` : ""}
      <span class="tag">${(u?.in || []).join(" · ")}</span>
      <a class="tag" target="_blank" href="https://www.tradingview.com/chart/?symbol=PSX%3A${sym}">TradingView ↗ (15m delayed)</a>
      ${escalated ? `<span class="pill bad" title="Deterministic QA flagged a claim on this ticker for the LLM room-verifier to web-check.">QA: escalated</span>` : ""}
      ${typeof starBtn === "function" ? starBtn(sym) : ""}
    </div>
    <div class="prov">Prices in <b>Rs (PKR)</b> · ${priceSrc} · quant as of ${q.date} close · fundamentals ${f.fetched || "—"} · long-history chart is split/bonus-adjusted (Yahoo); DPS close is unadjusted.${liq === "low" ? ' · <b class="dn">low liquidity</b>' : ""}${lossmaking ? ' · <b class="dn">earnings negative</b>' : ""}</div>
    ${mySector ? `<div class="tk-driver">${sectorDriverLine(smAll, mySector)}</div>` : ""}
    <div class="ranges" id="ranges">
      ${hasIntra ? '<button data-d="intra">1D</button>' : ""}<button data-d="63">3M</button><button data-d="126">6M</button><button class="on" data-d="252">1Y</button><button data-d="1260">5Y</button><button data-d="99999">Max${histYears >= 5 ? " (" + histYears + "y)" : ""}</button>
    </div>
    <div class="chartwrap"><canvas id="chart" style="height:340px"></canvas><div class="tooltip" id="tt"></div></div>
  </div>

  <div class="disclaimer">Educational and informational research only — <b>not personalized investment advice</b>. Past performance does not guarantee future results. Investing in PSX carries risk, including the possible loss of capital. The desk never places orders; any decision and its outcome are your own.</div>

  ${glance}
  ${noteCard}
  ${summaryStrip}

  ${fsc ? `<div class="seg"><h2>Business scorecard</h2><div class="ln"></div><span class="pill ${fsc.rating === "attractive" ? "ok" : fsc.rating === "caution" ? "bad" : ""}">${esc({ attractive: "stronger scorecard", caution: "weaker scorecard", neutral: "mixed scorecard" }[fsc.rating] || fsc.rating)}</span></div>
  <div class="card"><div class="sub" style="font-size:13px;color:var(--ink2);margin-bottom:14px">${esc(fsc.overall)}</div>
    <div class="two-col" style="gap:12px">${fsc.cards.map(c => `<div style="border:1px solid var(--line);border-radius:0;padding:12px 14px">
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px"><b>${esc(c[0])}</b><span class="tag">${esc(c[1])}</span></div>
      <div class="sub" style="color:var(--ink2)">${esc(c[2])}</div></div>`).join("")}</div></div>` : ""}

  ${fv ? (() => {
    const vcol = fv.verdict === "undervalued" ? "var(--up)" : fv.verdict === "overvalued" ? "var(--dn)" : "var(--ink2)";
    const vlabel = { undervalued: "below model fair value", overvalued: "above model fair value", fair: "near model fair value" }[fv.verdict] || fv.verdict;
    const mlabel = { relative_pe: "Peer P/E (priced like sector)", earnings_power: "Earnings power (vs bond yield)", graham: "Graham value (earnings + growth)", ddm: "Dividend discount model" };
    const mvals2 = Object.values(fv.methods || {}).filter(v => v != null);
    const spreadWide = mvals2.length > 1 && (Math.max(...mvals2) - Math.min(...mvals2)) / fv.composite_fair > 0.3;
    return `<div class="seg"><h2>Fair value model</h2><div class="ln"></div>
      <span class="pill" style="background:color-mix(in srgb,${vcol} 15%,transparent);color:${vcol}">${vlabel} · ${sgn(fv.mispricing_pct)}%</span>
      ${mvals2.length > 1 ? `<span class="pill" style="margin-left:6px">models split ${fmt(Math.min(...mvals2))}–${fmt(Math.max(...mvals2))}</span>` : ""}</div>
    <div class="card"><div class="sub" style="margin-bottom:14px">The desk values ${sym} four ways, then takes the middle (median) estimate. Today it trades at <b>${fmt(fv.price)}</b>; the blended model fair value is <b style="color:${vcol}">${fmt(fv.composite_fair)}</b> — ${fv.mispricing_pct >= 0 ? "the price sits <b>below</b> the model's blended fair value" : "the price sits <b>above</b> the model's blended fair value"} by ${Math.abs(fv.mispricing_pct)}%. This is a model estimate on public fundamentals — <b>not a price target or a recommendation</b>, and a low share price never means a company is cheap.${spreadWide ? ` <b style="color:var(--dn)">The four methods disagree sharply here</b> (Rs ${fmt(Math.min(...mvals2))}–${fmt(Math.max(...mvals2))}) — treat the composite as a rough screen, not a precise number.` : ""}</div>
      <table><thead><tr><th>Method</th><th class="r">Fair value</th><th class="r">vs price</th></tr></thead><tbody>${
      Object.entries(fv.methods).map(([k, val]) => { const up = (val / fv.price - 1) * 100; return `<tr><td>${esc(mlabel[k] || k)}</td><td class="r num">${fmt(val)}</td><td class="r num ${cls(up)}">${sgn(up.toFixed(0))}%</td></tr>`; }).join("")}
        <tr style="border-top:2px solid var(--line)"><td><b>Composite (median)</b></td><td class="r num"><b>${fmt(fv.composite_fair)}</b></td><td class="r num ${cls(fv.mispricing_pct)}"><b>${sgn(fv.mispricing_pct)}%</b></td></tr>
      </tbody></table>
      <div class="sub" style="margin-top:8px">EPS ${fv.eps} · growth est ${fv.growth_est_pct}% · P/E ${fv.pe ?? "—"}${(fv.eps_basis || "unknown") === "unknown" ? ` <span title="Consolidated vs unconsolidated EPS could not be confirmed from the source.">(EPS basis unknown)</span>` : ""}. A wide spread between methods means the models disagree — treat as a rough screen, not a precise number.</div></div>`;
  })() : ""}

  ${runDeskBar}
  ${!hasRoom ? renderRoom(room, sym) : (deskRan ? renderRoom(room, sym) : deskStub)}
  ${hasRoom && (staleIssue || claimIssues.length) ? `<div class="card">
    ${staleIssue ? `<div class="fact"><span>Room price staleness</span><b><span class="pill ${staleIssue.sev === "high" ? "bad" : "wait"}">${staleIssue.room_price_stale_pct}% stale</span></b><i class="sub" style="display:block;margin-top:4px">${esc(staleIssue.msg)}</i></div>` : ""}
    ${claimIssues.length ? `<div class="fact" style="margin-top:${staleIssue ? "10px" : "0"}"><span>Claim price flags</span><b>${claimIssues.length}</b><ul class="tr-ul">${claimIssues.map(i => `<li>${esc(i.msg)}</li>`).join("")}</ul></div>` : ""}
  </div>` : ""}

  ${brokerClaims.length ? `<div class="seg"><h2>What the brokers say</h2><div class="ln"></div><span class="pill">${brokerClaims.length}</span></div>
  <div class="card"><div class="sub">public calls from PSX research houses on ${sym}, on the record — <b>evidence to weigh, not advice to follow</b>. Each is scored on the <a href="/leaderboard" style="color:var(--accent)">Scores</a> board when it resolves.</div>
    <table><thead><tr><th>House</th><th>Call</th><th class="r">By</th><th class="r">Status</th></tr></thead><tbody>${
    brokerClaims.map(c => {
      const src = externalLink(c.source_url, "↗", 'style="color:var(--accent)"');
      return `<tr><td><b>${esc(c.source)}</b></td><td>${esc(c.claim?.text || c.claim?.rating || "")}${src ? ` ${src}` : ""}</td><td class="r num">${esc(c.resolve_by || "—")}</td><td class="r"><span class="pill ${c.status === "hit" ? "ok" : c.status === "miss" ? "bad" : ""}">${esc(c.status)}</span></td></tr>`;
    }).join("")}</tbody></table></div>` : ""}

  ${sigStack}

  <div class="seg"><h2>Strategies proven on ${sym}</h2><div class="ln"></div><span class="pill ok">${proven.length} proven</span></div>
  ${runStratBar}
  ${stratRan ? stratCards : stratStub}

  <div class="seg"><h2>What the data flags</h2><div class="ln"></div></div>
  <div class="card"><div class="sub" style="margin-bottom:12px">Factual observations pulled from the desk's data — not predictions and not advice. The absence of a flag is not a green light.</div>
    <div class="two-col" style="gap:14px">
      <div><div class="flaghdr up">What could go right</div>${flagList(pros, "pro")}</div>
      <div><div class="flaghdr dn">What could go wrong</div>${flagList(cons, "con")}</div>
    </div>
    ${infos.length ? `<div style="margin-top:10px"><div class="flaghdr">Insider &amp; off-market activity — metadata only, no direction inferred</div>${flagList(infos, "info")}</div>` : ""}
    </div>

  ${lightsCard}

  ${hasFeature("alignment") ? alignmentCard(alignmentOf(sym, {
    q: q || {}, fv: fv || {}, fs: fsc || {}, pred: predAll?.tickers?.[sym]?.score,
    claims: claimsAll, news: news, sm: smAll, sector: mySector,
  })) : planWall("Evidence alignment",
    "Every lens the desk runs — valuation, trend, momentum, quality, income, predictability, news, brokers, macro — counted for agreement on one bar. Not a buy/sell rating: a measure of how much the evidence actually converges, including when it doesn't.")}

  <details class="how"><summary><b>The same questions, in full detail</b><span class="sub">ratios and the desk's working</span><span class="dict-arrow">▾</span></summary>
    <div class="sub" style="margin-bottom:12px">Answered from the data where the desk has it — and honest about where it doesn't. A thinking aid, not a recommendation.</div>
    <div class="checklist">${checklist}</div></details>

  ${liqCard}

  <div class="seg"><h2>Risk profile</h2><div class="ln"></div></div>
  <div class="card"><div class="sub" style="margin-bottom:12px">Risk is more than volatility. A low rupee price does <b>not</b> mean a stock is cheap — a Rs 20 share can be dearer than a Rs 500 one depending on earnings.</div>
    <table class="risktbl"><tbody>${riskRows}</tbody></table></div>

  ${coverageNote}

  <div class="card"><h2>Key facts</h2><div class="sub">fundamentals · stockanalysis.com${f.fetched ? " · " + f.fetched : ""}</div>
    <div class="facts">
      <div class="fact"><span>Market cap</span><b>${esc(f.market_cap || "—")}</b></div>
      <div class="fact"><span>P/E (TTM)</span><b>${lossmaking ? '<span class="sub" style="font-size:11px">n/a · earnings negative</span>' : esc(fs.pe != null ? fs.pe : (f.pe || "—"))}</b>${(f.eps_basis || "unknown") === "unknown" ? ` <span class="sub" style="font-size:10px" title="Whether this EPS is consolidated or unconsolidated could not be confirmed from the source page.">EPS basis unknown</span>` : ""}</div>
      <div class="fact"><span>Forward P/E</span><b>${esc(f.forward_pe || "—")}</b></div>
      <div class="fact"><span>EPS (TTM)</span><b>${esc(f.eps || "—")}</b></div>
      <div class="fact"><span>Div yield</span><b>${esc(f.div_yield || "—")}</b>${divYieldIssue ? ` <span class="tag" style="color:var(--dn)" title="${esc(divYieldIssue.msg)}">crossfoot flag</span>` : ""}</div>
      <div class="fact"><span>Payout ratio</span><b>${esc(fs.payout_ratio != null ? fs.payout_ratio + "%" : (f.payout_ratio || "—"))}</b></div>
      <div class="fact"><span>Beta</span><b>${esc(f.beta || "—")}</b></div>
      <div class="fact"><span>Revenue</span><b>${esc(f.revenue || "—")}</b></div>
      <div class="fact"><span>Net income</span><b>${esc(f.net_income || "—")}</b></div>
      <div class="fact"><span>Shares out</span><b>${esc(f.shares_out || "—")}</b></div>
      <div class="fact"><span>Next results</span><b>${nextEarn ? esc(nextEarn.date) + ` <span class="cd ${daysTo(nextEarn.date) <= 7 ? "soon" : ""}">${daysTo(nextEarn.date)}d</span>` : "—"}</b></div>
      <div class="fact"><span>Ex-dividend</span><b>${nextXdiv ? esc(nextXdiv.date) : "—"}</b></div>
    </div></div>
  <div class="card"><h2>Quant snapshot</h2><div class="sub">as of ${q.date} close</div>
    <div class="statgrid num">
      <div class="stat"><span>RSI 14</span><b>${q.rsi14}</b></div>
      <div class="stat"><span>SMA 20</span><b class="${q.above_sma20 ? "up" : "dn"}">${q.sma20}</b></div>
      <div class="stat"><span>SMA 50</span><b class="${q.above_sma50 ? "up" : "dn"}">${q.sma50}</b></div>
      <div class="stat"><span>ATR proxy</span><b>${q.atr14_proxy}</b></div>
      <div class="stat"><span>5d / 20d</span><b><span class="${cls(q.ret_5d)}">${sgn(q.ret_5d)}%</span> / <span class="${cls(q.ret_20d)}">${sgn(q.ret_20d)}%</span></b></div>
      <div class="stat"><span>vol surge</span><b>${q.vol_surge ?? "—"}×</b></div>
      <div class="stat"><span>vola rank</span><b>${q.volatility_rank ?? "—"}</b></div>
      <div class="stat"><span>to 20d high</span><b>${sgn(q.dist_to_20d_high_pct)}%</b></div>
      <div class="stat"><span>avg traded/day</span><b>${fmt(q.avg_daily_traded_value / 1e6, 0)}M</b></div>
      <div class="stat"><span>index weight</span><b>${u?.weight_pct ?? "—"}%</b></div>
    </div></div>
  <div class="two-col">
    <div class="card"><h2>${histYears}-year behavior</h2><div class="sub">${series[0].date} → ${series[series.length - 1].date}${series === deep ? " · Yahoo history" : ""}</div>
      <div class="statgrid num">
        <div class="stat"><span>total return</span><b class="${cls(b.total)}">${sgn(b.total.toFixed(0))}%</b></div>
        <div class="stat"><span>max drawdown</span><b class="dn">${b.mdd.toFixed(0)}%</b></div>
        <div class="stat"><span>up days</span><b>${b.upPct.toFixed(0)}%</b></div>
        <div class="stat"><span>avg daily move</span><b>±${b.avgAbs.toFixed(2)}%</b></div>
        <div class="stat"><span>best day</span><b class="up">+${b.best.toFixed(1)}%</b></div>
        <div class="stat"><span>worst day</span><b class="dn">${b.worst.toFixed(1)}%</b></div>
      </div></div>
    <div class="card"><h2>Dividends</h2><div class="sub">face value Rs 10 assumed · buy BEFORE ex-date (~2 sessions pre-closure)</div>${
      dUp.length ? `<p style="margin-bottom:10px"><b class="up">UPCOMING:</b> ${dUp.map(d => `${esc(d.announcement)} — closure ${d.bc_start}, buy by <b>${d.buy_by}</b>`).join("; ")}</p>` : ""}
      <table><thead><tr><th>Announced</th><th>Payout</th><th class="r">Rs/sh</th><th class="r">Yield@now</th><th class="r">Closure</th></tr></thead><tbody>${
      dHist.length ? dHist.slice(0, 8).map(d => `<tr><td>${esc((d.announced || "").split(" ").slice(0, 3).join(" "))}</td><td>${esc(d.announcement)} <span class="tag">${divType(d.period)}</span></td>
        <td class="r num">${d.dividend_rs ?? "—"}</td><td class="r num">${d.yield_pct_at_close ? d.yield_pct_at_close + "%" : "—"}</td><td class="r num">${d.bc_start || "—"}</td></tr>`).join("") : '<tr><td colspan="5" class="empty">no payout records</td></tr>'}</tbody></table></div>
  </div>
  <div class="card"><h2>News & developments</h2><div class="sub">sentinel-tagged for ${sym}</div><div class="wire">${
    tickerNews.length ? tickerNews.map(n => `<p><span class="tag">${n.impact}</span> <span class="t">${esc((n.ts || "").slice(0, 16))}</span>${esc(n.headline || "")} ${externalLink(n.url, "source ↗", 'style="color:var(--accent)"')}<br><span class="t">${esc(n.summary || "")}</span></p>`).join("") : '<div class="empty">Nothing tagged yet — sentinel populates this each cycle.</div>'}</div></div>
  <div class="card"><h2>Insider & off-market activity</h2><div class="sub">DPS filing metadata + off-market trades, retained history · metadata only, no direction inferred</div>
    ${insiderRows.length ? `<table><thead><tr><th>Date</th><th>Insider</th><th>Role</th><th>Type</th><th class="r">Shares</th><th class="r">Price</th><th></th></tr></thead><tbody>${
      [...insiderRows].sort((a, b) => (b.date || "").localeCompare(a.date || "")).map(r => {
        const txns = r.transactions && r.transactions.length ? r.transactions : [null];
        return txns.map(t => `<tr><td>${esc(r.date)}</td><td>${esc(t?.insider_name || "—")}</td><td>${esc(t?.insider_role || "—")}</td>
          <td>${esc(t?.transaction_type || r.title || "filing")}</td>
          <td class="r num">${t?.shares_traded != null ? Number(t.shares_traded).toLocaleString() : "—"}</td>
          <td class="r num">${t?.price_per_share != null ? t.price_per_share : "—"}</td>
          <td class="r">${externalLink(r.pdf_url, "view ↗", 'style="color:var(--accent)"') || "—"}</td></tr>`).join("");
      }).join("")
    }</tbody></table>` : '<div class="empty">No insider/substantial-shareholder filings tagged for this name.</div>'}
    ${offmkt ? `<p style="margin-top:10px"><b>Off-market:</b> ${offmkt.shares.toLocaleString()} shares · Rs ${offmkt.value.toLocaleString()} value · ${offmkt.trades} trade${offmkt.trades === 1 ? "" : "s"} across ${offmkt.dayCount} day${offmkt.dayCount === 1 ? "" : "s"} (trailing ${offRetentionDays}d)</p>` : `<div class="empty" style="margin-top:10px">No off-market trades in the trailing ${offRetentionDays}d.</div>`}
  </div>`;

  // The partial-load banner's button, when the page rendered without one of its inputs.
  const gapBtn = document.getElementById("tkretry");
  if (gapBtn) gapBtn.onclick = () => pageTicker(sym, 0);

  /* Chart wiring is now conditional. `series` can legitimately be null here (that is the whole
     point of the narrowed guard above), and drawChart would throw on it — which would surface as
     "Couldn't render ticker" and put us right back where we started, just with a different
     message. No history, no chart; the rest of the page still stands. */
  const canvas = $("chart"), ranges = $("ranges");
  if (canvas && series && series.length > 1) {
    const redraw = d => {
      if (d === "intra") drawIntraday(canvas, $("tt"), intra.points, q.close);
      else drawChart(canvas, $("tt"), series, +d);
    };
    ranges?.addEventListener("click", e => {
      if (!e.target.dataset.d) return;
      ranges.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === e.target));
      redraw(e.target.dataset.d);
    });
    redraw(252);
  } else if (canvas) {
    const holder = canvas.parentElement;
    if (holder) holder.innerHTML = `<div class="empty" style="padding:28px 12px">No price history loaded for ${esc(sym)} — the chart is unavailable on this render. The desk is retrying.</div>`;
    if (ranges) ranges.style.display = "none";
  }
}

function daysFromNow(d) { return d ? Math.ceil((new Date(d) - new Date()) / 86400000) : null; }
function cdBadge(d) { const n = daysFromNow(d); return n == null ? "" : `<span class="cd ${n <= 3 ? "soon" : ""}">${n >= 0 ? n + "d" : "past"}</span>`; }

async function pageDividends() {
  const [cal, divs] = await Promise.all([j("earnings_calendar.json"), j("dividends.json")]);
  const ev = cal?.events || [];
  const divUp = ev.filter(e => e.type === "ex_dividend" || e.type === "book_closure");
  const past = (divs?.history || []).filter(d => d.bc_start && !d.upcoming)
    .sort((a, b) => b.bc_start.localeCompare(a.bc_start)).slice(0, 40);

  const dvLocked = !isSubscribed();
  const divShown = dvLocked ? divUp.slice(0, 3) : divUp;
  const divHtml = divUp.length ? divShown.map(d => `
    <tr class="clickable" onclick="navigate('/ticker/${d.ticker}')">
      <td><b>${d.ticker}</b></td>
      <td>${esc(d.announcement || d.type.replace("_", " "))}</td>
      <td class="r num">${d.dividend_rs ?? "—"}</td>
      <td class="r num">${d.yield_pct || (d.div_yield ? esc(d.div_yield) : "—")}</td>
      <td class="r num up"><b>${d.buy_by || "—"}</b> ${cdBadge(d.buy_by)}</td>
      <td class="r num">${d.sell_ok_from || d.date}</td>
    </tr>`).join("")
    : `<tr><td colspan="6" class="empty">No <b>announced</b> ex-dividend / book-closure dates yet — this is data, not a gap. PSX payouts cluster right after results (Jul–Aug); the desk lists a date only once a company files it, never a guess. The <b>${past.length} recent payouts below</b> show what these names actually pay and their yields.</td></tr>`;

  $("view").innerHTML = `
  <div class="timing">
    <div><span>How to collect a dividend</span><b>Buy before → hold through → sell after</b></div>
    <div><span>① Buy by</span><b>the last session before the ex-date</b></div>
    <div><span>② Sell on / after</span><b>the ex-date — you keep the full payout</b></div>
  </div>

  <div class="seg"><h2>Upcoming dividends & book closures</h2><div class="ln"></div></div>
  <div class="card"><div class="sub">own the share BEFORE the ex-dividend date to receive the cash · updated ${esc(cal?.updated || "—")}</div>
    <table><thead><tr><th>Ticker</th><th>Payout</th><th class="r">Rs/sh</th><th class="r">Yield</th><th class="r">Buy by</th><th class="r">Ex / sell-after</th></tr></thead><tbody>${divHtml}</tbody></table></div>

  ${dvLocked ? planWall("The full dividend desk",
    `Every announced payout with its buy-by and sell-after dates${divUp.length > 3 ? ` (${divUp.length - 3} more upcoming)` : ""}, plus the last ${past.length} real payouts and the yields they actually delivered.`) : `
  <div class="seg"><h2>Past payouts</h2><div class="ln"></div></div>
  <div class="card"><div class="sub">last ${past.length} closures · cash dividends (D) as % of Rs 10 face value</div>
    <table><thead><tr><th>Ticker</th><th>Payout</th><th class="r">Rs/sh</th><th class="r">Yield@now</th><th class="r">Announced</th><th class="r">Closure start</th></tr></thead><tbody>${
    past.map(d => `<tr class="clickable" onclick="navigate('/ticker/${d.symbol}')"><td><b>${d.symbol}</b></td><td>${esc(d.announcement)}</td>
      <td class="r num">${d.dividend_rs ?? "—"}</td><td class="r num">${d.yield_pct_at_close ? d.yield_pct_at_close + "%" : "—"}</td>
      <td class="r num">${esc((d.announced || "").split(" ").slice(0, 3).join(" "))}</td><td class="r num">${d.bc_start}</td></tr>`).join("")}</tbody></table></div>`}`;
}

async function pageCalendar() {
  const cal = await j("earnings_calendar.json");
  const earnings = (cal?.events || []).filter(e => e.type === "results");
  const byMonth = {};
  earnings.forEach(e => { const m = e.date.slice(0, 7); (byMonth[m] = byMonth[m] || []).push(e); });

  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Earnings calendar</h2><div class="ln"></div></div>
  <p class="sub" style="margin-bottom:16px">${earnings.length} upcoming results dates · <span class="pill ok">verified</span> = confirmed against a board-meeting notice · <span class="tag">estimate</span> = scraped, pending. The desk won't hold a swing through an unconfirmed results date — earnings gaps blow through stops.</p>
  ${(isSubscribed() ? Object.keys(byMonth).sort() : Object.keys(byMonth).sort().slice(0, 1)).map(m => {
    const label = new Date(m + "-01").toLocaleDateString("en", { month: "long", year: "numeric" });
    return `<div class="card cal-month"><h2 style="font-size:13px">${label}</h2>
      <table><thead><tr><th>Date</th><th class="r">In</th><th>Ticker</th><th>Event</th><th class="r">Status</th></tr></thead><tbody>${
      byMonth[m].map(e => `<tr class="clickable" onclick="navigate('/ticker/${e.ticker}')">
        <td class="num">${e.date}</td><td class="r">${cdBadge(e.date)}</td><td><b>${e.ticker}</b></td>
        <td class="sub">${esc(e.note || "results")}</td>
        <td class="r">${e.confirmed ? '<span class="pill ok">verified</span>' : '<span class="tag">estimate</span>'}</td></tr>`).join("")}</tbody></table></div>`;
  }).join("") || '<div class="card"><div class="empty">Calendar builds on the first full cycle.</div></div>'}
  ${Object.keys(byMonth).length > 1 ? planWall("The full earnings calendar",
    `${earnings.length} dated results across the coming months, each verified against a board-meeting notice — the dates that gap prices, known before they land.`) : ""}`;
}

let newsFilter = { imp: 0, q: "" };
async function pageNews() {
  const news = (await j("newslog.json")) || [];
  const rows = news.filter(n => (n.impact || 0) >= newsFilter.imp
    && (!newsFilter.q || (n.tickers || []).join(" ").toUpperCase().includes(newsFilter.q) || (n.headline || "").toUpperCase().includes(newsFilter.q)))
    .slice(-80).reverse();
  $("view").innerHTML = `
  <div class="card"><h2>News wire</h2><div class="sub">${news.length} items logged · nothing is ever deleted — this is the desk's memory</div>
    <div class="ranges">
      ${[0, 3, 4, 5].map(i => `<button data-imp="${i}" class="${newsFilter.imp === i ? "on" : ""}">${i ? "impact ≥" + i : "all"}</button>`).join("")}
      <input id="nq" type="search" inputmode="search" enterkeyhint="search" placeholder="filter ticker/text" value="${esc(newsFilter.q)}" style="font:inherit;padding:4px 10px;border:1px solid currentColor;opacity:.7;background:transparent;color:inherit;border-radius:0">
    </div>
    <div class="wire">${rows.length ? rows.map(n => `<p><span class="tag">${n.impact}</span> <span class="t">${esc((n.ts || "").slice(0, 16))}</span>
      ${(n.tickers || []).map(t => `<a href="/ticker/${esc(t)}" style="color:var(--accent);font-weight:700">${esc(t)}</a>`).join(" ")}
      <b>${esc(tp(n, "headline"))}</b> ${externalLink(n.url, "↗", 'style="color:var(--accent)"')}<br>
      <span class="t">${esc(tp(n, "summary"))} · ${esc(n.source || "")}</span></p>`).join("") : '<div class="empty">Wire silent — sentinel runs every cycle during market hours.</div>'}</div></div>`;
  $("view").querySelector(".ranges").addEventListener("click", e => {
    if (e.target.dataset.imp != null) { newsFilter.imp = +e.target.dataset.imp; pageNews(); }
  });
  $("nq").addEventListener("change", e => { newsFilter.q = e.target.value.toUpperCase(); pageNews(); });
}

/* ---------- Research library (broker notes + filings, digested) ---------- */
async function pageResearch() {
  const idx = await j("research_index.json");
  const docs = Object.values(idx?.documents || {}).sort((a, b) => (b.date || "").localeCompare(a.date || ""));
  const followed = new Set(followedBrokers());
  // followed broker desks surface first on the wire, then by date
  const brokers = docs.filter(d => d.source_type === "broker")
    .sort((a, b) => (followed.has(b.source) ? 1 : 0) - (followed.has(a.source) ? 1 : 0));
  const filings = docs.filter(d => d.source_type !== "broker");
  const dtLabel = { corporate_briefing: "corporate briefing", agm: "AGM", results: "results", board_meeting: "board meeting", filing: "filing", morning_note: "morning note", company_note: "broker note" };
  const docRow = d => `<div class="rdoc">
    <div class="rdoc-top"><span class="tag">${esc(dtLabel[d.doc_type] || d.doc_type)}</span>
      <span class="rdoc-src">${esc(d.source)}${followed.has(d.source) ? ' <span class="wbadge">★ following</span>' : ""}${d.digest_level === "headline" ? ' · <span class="sub">headline only</span>' : ""}</span>
      <span class="t">${esc(d.date || "")}</span>
      ${(d.tickers || []).slice(0, 4).map(t => `<a href="/ticker/${esc(t)}" class="tag clickable">${esc(t)}</a>`).join(" ")}</div>
    <div class="rdoc-digest">${esc(d.digest || "")}${externalLink(d.url, "source ↗", 'style="color:var(--accent)"') ? ` ${externalLink(d.url, "source ↗", 'style="color:var(--accent)"')}` : ""}</div>
    ${(d.claims || []).length ? `<div class="sub" style="margin-top:4px"><b>Claims (scored later):</b> ${d.claims.map(c => esc(c.claim?.text || "")).join(" · ")}</div>` : ""}
    ${d.omissions ? `<div class="sub" style="margin-top:4px"><b class="dn">What it glosses over:</b> ${esc(d.omissions)}</div>` : ""}</div>`;
  // glance row: what's in the library and how much of it is on the record
  const sTile = (label, val, sub, k) => `<div class="sumtile"><span class="sk">${label}</span><b class="${k || ""}">${val}</b>${sub ? `<i>${sub}</i>` : ""}</div>`;
  const nClaims = docs.reduce((a, d) => a + ((d.claims || []).length), 0);
  const houses = new Set(docs.filter(d => d.source_type === "broker").map(d => d.source));
  const latest = docs[0]?.date || "—";
  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Research library</h2><div class="ln"></div><span class="pill">${docs.length} documents</span></div>
  <div class="sumstrip s4">
    ${sTile("Broker notes", brokers.length, `${houses.size} house${houses.size === 1 ? "" : "s"}${followed.size ? ` · ${followed.size} you follow` : ""}`, "")}
    ${sTile("Filings & briefings", filings.length, "results · AGM · board", "")}
    ${sTile("Claims on the record", nClaims, "each scored when it resolves", nClaims ? "up" : "")}
    ${sTile("Latest document", esc(latest), "the wire updates weekly", "")}
  </div>
  <div class="disclaimer">Broker research and company filings are <b>evidence the desk cross-examines, never takes at face value</b>. Brokers miss things, carry sector bias, and are often wrong — every broker claim here is extracted, scored against what actually happens, and ranked on the <a href="/leaderboard" style="color:inherit;text-decoration:underline">broker leaderboard</a>. Educational, not advice.</div>
  <div class="seg"><h2>Broker notes</h2><div class="ln"></div><span class="pill">${brokers.length}</span></div>
  <div class="card">${brokers.length ? (isSubscribed() ? brokers : brokers.slice(0, 2)).map(docRow).join("") : '<div class="empty">No broker notes digested yet. Add public sources in config/broker_sources.json; the desk digests each once and scores its calls. Until then, the desk forms its own view without leaning on brokers.</div>'}</div>
  <div class="seg"><h2>Company filings & briefings</h2><div class="ln"></div><span class="pill">${filings.length}</span></div>
  <div class="card">${filings.length ? (isSubscribed() ? filings : filings.slice(0, 2)).map(docRow).join("") : '<div class="empty">No filings tagged yet — the news sentinel surfaces results, board-meeting and corporate-briefing notices here as companies file them.</div>'}</div>
  ${docs.length > 4 ? planWall("The full research library",
    `${docs.length} digested documents — broker notes, results filings and corporate briefings, each cross-examined with every claim extracted for public scoring.`) : ""}`;
}

/* ---------- Leaderboards: our analysts + the brokers, scored on real outcomes ---------- */
async function pageLeaderboard() {
  const [lb, bs, claimsAll] = await Promise.all([j("leaderboard.json"), j("broker_scorecard.json"), j("claims.json")]);
  const personas = lb?.personas || {};
  const brokers = bs?.brokers || {};
  // SECP Reg 2(ha) (§4, S.R.O.7(I)/2026): the desk does NOT publish a track record of its OWN calls
  // on a named security. Legacy per-named-stock persona claims still sit in claims.json but are
  // neither scored (scripts/room_score.py drops them) nor shown — filter them out of every count and
  // table here so the page only reflects the desk's sector/macro commentary + third-party brokers.
  const allClaims = (claimsAll?.claims || []).filter(c => !(c.source_type === "persona" && c.ticker));
  const pending = allClaims.filter(c => c.status === "pending");
  const resolved = allClaims.filter(c => c.status === "hit" || c.status === "miss");
  const claimDates = allClaims.map(c => (c.made_on || c.made_at || "")).filter(Boolean).sort();
  const since = claimDates.length ? claimDates[0].slice(0, 10) : null;
  const daysSince = since ? Math.max(0, Math.round((Date.now() - new Date(since)) / 86400000)) : null;
  const clkTile = (label, val, sub) => `<div class="clk-tile"><span>${label}</span><b>${val}</b>${sub ? `<i>${sub}</i>` : ""}</div>`;
  const trackClock = `<div class="trackclock">
    ${clkTile("Scoring calls since", since || "—", daysSince != null ? `${daysSince} day${daysSince === 1 ? "" : "s"} on the record` : "the clock starts with the first dated call")}
    ${clkTile("Calls on the record", allClaims.length, "desk analysts + brokers")}
    ${clkTile("Resolved", resolved.length, "graded against real outcomes")}
    ${clkTile("Pending", pending.length, "awaiting their horizon")}
  </div>`;
  const pendBroker = pending.filter(c => c.source_type === "broker");
  const pendByBroker = {};
  pendBroker.forEach(c => (pendByBroker[c.source] = pendByBroker[c.source] || []).push(c));
  const pRow = (name, r) => `<tr><td><b>${esc(name)}</b></td><td class="r num">${r.calls}</td><td class="r num ${r.hit_rate >= 0.55 ? "up" : r.hit_rate != null && r.hit_rate < 0.45 ? "dn" : ""}">${r.hit_rate != null ? Math.round(r.hit_rate * 100) + "%" : "—"}</td><td class="r num">${r.avg_target_err_pct != null ? r.avg_target_err_pct + "%" : "—"}</td></tr>`;
  const sectorRow = (sect, s) => `<tr><td style="padding-left:22px" class="sub">${esc(sect.replace(/_/g, " "))}</td><td class="r num">${s.calls}</td><td class="r num ${!s.ranked ? "" : s.hit_rate >= 0.55 ? "up" : "dn"}">${s.hit_rate != null ? Math.round(s.hit_rate * 100) + "%" : "—"}${!s.ranked ? ' <span class="sub">unranked</span>' : ""}</td><td class="r num">${s.avg_target_err_pct != null ? s.avg_target_err_pct + "%" : "—"}</td></tr>`;
  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Track records</h2><div class="ln"></div></div>
  ${trackClock}
  <div class="disclaimer">Every dated call — the desk's own AI analysts <b>and</b> the brokers — is scored against what prices actually did. This is accountability, not advice. A thin record (below ${bs?._meta?.min_sample_to_rank ?? 5} calls) is shown <b>unranked</b> so no one is over-trusted on luck.</div>

  <div class="seg"><h2>The desk's AI analysts</h2><div class="ln"></div><span class="pill">${Object.keys(personas).length}</span></div>
  <div class="card"><div class="sub">the desk scores its own <b>sector and macro commentary</b> against outcomes — the same standard it holds the brokers to. It does not publish or track calls on individual stocks.</div>
    ${Object.keys(personas).length ? `<table><thead><tr><th>Analyst</th><th class="r">Calls</th><th class="r">Hit rate</th><th class="r">Avg target err</th></tr></thead><tbody>${Object.entries(personas).map(([n, r]) => pRow(n, r)).join("")}</tbody></table>` : '<div class="empty">No resolved calls yet. The desk scores its own sector and macro reads the same way it scores brokers; calls on individual stocks aren\'t published, so nothing is tracked per name here.</div>'}</div>

  <div class="seg"><h2>Brokers — ranked on what came true</h2><div class="ln"></div><span class="pill">${Object.keys(brokers).length}</span></div>
  <div class="card"><div class="sub">overall and per sector — a broker's bank desk and E&P desk have different records, so they're scored separately.</div>
    ${Object.keys(brokers).length ? Object.entries(brokers).map(([n, r]) => `<table style="margin-bottom:14px"><thead><tr><th>${esc(n)}</th><th class="r">Calls</th><th class="r">Hit rate</th><th class="r">Avg target err</th></tr></thead><tbody>${pRow("overall", r)}${Object.entries(r.by_sector || {}).map(([s, sv]) => sectorRow(s, sv)).join("")}</tbody></table>`).join("") : '<div class="empty">No broker calls have <b>resolved</b> yet — rankings appear once a call reaches its horizon. Calls already on the record are shown below and will be graded when they resolve.</div>'}</div>

  ${pendBroker.length ? `<div class="seg"><h2>Broker calls on the record — pending</h2><div class="ln"></div><span class="pill">${pendBroker.length}</span></div>
  <div class="card"><div class="sub">harvested from public research; each will be scored against what actually happens by its horizon. Recorded to grade the house, not to follow it.</div>
    <table><thead><tr><th>House</th><th>Ticker</th><th>Call</th><th class="r">Resolves</th></tr></thead><tbody>${
    pendBroker.slice(0, 40).map(c => `<tr><td><b>${esc(c.source)}</b></td><td><a href="/ticker/${esc(c.ticker)}" style="color:var(--accent);font-weight:700">${esc(c.ticker)}</a></td><td class="sub">${esc(c.claim?.text || c.claim?.rating || "")}</td><td class="r num">${esc(c.resolve_by || "—")}</td></tr>`).join("")}</tbody></table></div>` : ""}`;
}

/* ---------- legal pages (Terms / Privacy / Risk) — content from state/legal.json ---------- */
async function pageLegal() {
  const doc = await j("legal.json");
  const which = routeHash().split("/")[2] || "terms";
  const tabs = [["terms", "Terms of Service"], ["privacy", "Privacy Policy"], ["risk", "Risk Disclosure"]];
  const tabBar = `<div class="legal-tabs">${tabs.map(([k, t]) => `<a href="/legal/${k}" class="${k === which ? "on" : ""}">${t}</a>`).join("")}</div>`;
  const L = doc && doc[which];
  if (!L) { $("view").innerHTML = `<div class="seg" style="margin-top:4px"><h2>Legal</h2><div class="ln"></div></div>${tabBar}<div class="card"><div class="skelwrap"><div class="skel-line"></div><div class="skel-line"></div><div class="skel-line"></div><div class="skel-line"></div><div class="skel-line short"></div></div></div>`; return; }
  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>${esc(L.title)}</h2><div class="ln"></div><span class="pill">updated ${esc(L.updated)}</span></div>
  ${tabBar}
  <div class="card legal-doc">
    <p class="legal-intro">${esc(L.intro)}</p>
    ${(L.sections || []).map(([h, b]) => `<h3>${esc(h)}</h3><p>${esc(b)}</p>`).join("")}
    <p class="sub" style="margin-top:20px">Contact: <a href="mailto:${esc(doc.contact || "")}" style="color:var(--accent)">${esc(doc.contact || "")}</a>${doc.jurisdiction ? ` · Governed by the laws of ${esc(doc.jurisdiction)}.` : ""}</p>
  </div>`;
}

/* ---------- unsubscribe (ungated — /unsubscribe?t=<uuid>, reached only from an email link) ---------- */
async function pageUnsubscribe() {
  const q = (routeHash().split("?")[1] || "");
  const token = new URLSearchParams(q).get("t") || "";
  const card = (body) => { $("view").innerHTML = `<div class="seg" style="margin-top:4px"><h2>Email preferences</h2><div class="ln"></div></div><div class="card">${body}</div>`; };
  if (!token) { card(`<div class="empty">This link is missing its token — open the unsubscribe link from an actual desk email.</div>`); return; }
  card(`<div class="sub">Stop desk emails to this address?</div>
    <div style="margin-top:14px;display:flex;gap:10px;flex-wrap:wrap">
      <button class="btn" data-unsub-scope="digest">Just the weekly digest</button>
      <button class="btn" data-unsub-scope="all">All desk emails</button>
    </div>`);
  // token is raw attacker-controlled input (URL query, unauthenticated route). Bind via
  // addEventListener with the token as a real JS value, not string-interpolated into an
  // onclick="" attribute — esc() only HTML-entity-escapes, and the browser HTML-decodes an
  // attribute value before handing it to the JS parser, so an interpolated token can still
  // break out of the string literal and execute arbitrary JS in this origin.
  $("view").querySelectorAll("[data-unsub-scope]").forEach(btn => {
    btn.addEventListener("click", () => doUnsub(token, btn.dataset.unsubScope));
  });
}
async function doUnsub(token, scope) {
  const { data, error } = await sb.rpc("email_unsubscribe", { p_token: token, p_scope: scope });
  const ok = !error && data === true;
  track("email_unsub", { scope, ok });
  $("view").querySelector(".card").innerHTML = ok
    ? `<div class="sub">Done — ${scope === "all" ? "all desk emails" : "the weekly digest"} turned off for this address.</div>`
    : `<div class="empty">Couldn't process that — the link may be expired or already used.</div>`;
}

/* ---------- Shared "run" modal: a ~10–20s loader that streams REAL precomputed steps, then a
   reveal. Zero agents run per view — it animates already-computed data. Used by both the Desk
   Room run and the strategy-library run so the loader/orchestration lives in ONE place. ---------- */
function runRevealModal(opts) {
  // opts: { sym, kicker, title, sub, steps:[html], flagKey, renderReveal(bodyEl, {runLoader}) }
  const ov = document.createElement("div");
  ov.className = "replay-overlay";
  ov.innerHTML = `<div class="replay-box">
    <div class="replay-head"><span class="replay-kicker">${esc(opts.kicker)}</span>
      <button class="replay-x" aria-label="close" style="margin-left:auto">✕</button></div>
    <div class="replay-body" id="rpBody"></div>
  </div>`;
  document.body.appendChild(ov);
  const body = ov.querySelector("#rpBody");
  let raf = null, done = false, closing = false;

  function close() {
    if (closing) return;                     // Esc + backdrop click can both land; close once
    closing = true;
    // done blocks the pending setTimeout(reveal, 550) that the loader queues once the bar hits
    // 100%. Without it, closing inside that window still fires reveal(): it sets the "already
    // seen" session flag and runs onReveal into a body that closeAnimated has already detached.
    done = true;
    cancelAnimationFrame(raf); document.removeEventListener("keydown", key);
    popOverlay(close);
    closeAnimated(ov, ".replay-box");   // let the exit animation play, then drop the node
    // reveal the results inline on the page (reveal() sets the session flag once the run finishes)
    if (opts.onClose) opts.onClose();
    else if (opts.sym && typeof pageTicker === "function" && routeHash().toUpperCase().includes(opts.sym)) pageTicker(opts.sym);
  }
  function key(e) { if (e.key === "Escape") close(); }
  ov.addEventListener("click", e => {
    if (e.target === ov || e.target.classList.contains("replay-x")) return close();
    const b = e.target.closest("[data-a]");
    if (b && b.dataset.a === "replay") runLoader();
    // "read the full transcript / test log" — close out to the page and open the deep dive there
    if (b && b.dataset.a === "deep") { const t = b.dataset.target; close(); setTimeout(() => {
      const d = document.querySelector("." + t);
      if (d) { d.open = true; d.scrollIntoView({ behavior: "smooth", block: "start" }); }
    }, 300); }
  });
  document.addEventListener("keydown", key);
  pushOverlay(close, ov);
  // Teardown hook for route(): drop the node AND the document listener without the close()
  // side effects (onClose/pageTicker would re-render a page we are navigating away from).
  ov._close = () => { closing = true; done = true; cancelAnimationFrame(raf); document.removeEventListener("keydown", key); popOverlay(close); ov.remove(); };

  function runLoader() {
    done = false;
    body.innerHTML = `<div class="rp-load">
      <div class="rp-load-title">${esc(opts.title)}</div>
      <div class="rp-load-sub">${opts.sub}</div>
      <div data-no-enhance="1">
        <div class="rp-prog"><div class="rp-prog-fill" id="rpFill" style="width:100%;transform:scaleX(0);transform-origin:left;transition:none"></div></div>
        <div class="rp-pct" id="rpPct"><b id="rpPctN">0</b><span>%</span></div>
      </div>
      <div class="rp-steps" id="rpSteps" data-no-enhance="1"></div></div>`;
    const fill = ov.querySelector("#rpFill"), pctEl = ov.querySelector("#rpPctN"), stepsEl = ov.querySelector("#rpSteps"), subEl = ov.querySelector(".rp-load-sub");
    const total = 10000 + Math.floor(Math.random() * 10000), longRun = total > 15500, t0 = performance.now();  // 10–20s, varied for anticipation
    let shown = 0, lastPct = -1;
    function tick(now) {
      // route() removes the overlay node on a real navigation; without this bail the loop keeps
      // running against a detached tree for the remaining run and fires reveal() on a dead page
      if (!ov.isConnected) { done = true; return; }
      const p = Math.min(100, (now - t0) / total * 100);
      // A width write relayouts the bar every frame, and rewriting the counter's innerHTML tore
      // down and rebuilt the "%" node ~60×/s — both showed up as a MutationObserver flush over
      // the whole document. Composited transform + a text write only when the integer moves.
      fill.style.transform = "scaleX(" + (p / 100) + ")";
      const ip = Math.floor(p);
      if (ip !== lastPct) { lastPct = ip; pctEl.textContent = String(ip); }
      if (longRun && p > 52 && !subEl.dataset.longed) { subEl.dataset.longed = "1"; subEl.textContent = "Taking a little longer than usual on this one — the desk is being thorough."; }
      const want = Math.round(p / 100 * opts.steps.length);
      while (shown < want && shown < opts.steps.length) {
        if (shown > 0) { const prev = stepsEl.children[shown - 1]; if (prev) prev.classList.add("did"); }
        stepsEl.insertAdjacentHTML("beforeend", `<div class="rp-step-line"><span class="rp-step-mk">▸</span><span class="rp-step-tx">${opts.steps[shown]}</span></div>`);
        stepsEl.scrollTop = stepsEl.scrollHeight;   // scrollIntoView() also scrolls the PAGE behind the modal
        shown++;
      }
      if (p < 100 && !done) { raf = requestAnimationFrame(tick); }
      else if (!done) { [...stepsEl.children].forEach(c => c.classList.add("did")); setTimeout(reveal, 550); }
    }
    raf = requestAnimationFrame(tick);
  }
  function reveal() {
    if (done) return;
    done = true; cancelAnimationFrame(raf);
    try { if (opts.flagKey) sessionStorage.setItem(opts.flagKey, "1"); } catch (e) { /* private mode */ }
    if (opts.onReveal) opts.onReveal();
    opts.renderReveal(body, { runLoader });
    body.scrollTop = 0;
  }
  runLoader();
}

/* ---------- Desk Room run: streams the REAL steps the desk ran (RSI/SMA/fair-value from the data
   layer) then lands on the parallel split-desk view — the two desks and the bull/bear debate. The
   session is terminal at the debate (no Chair verdict): general commentary, not a call. ---------- */
async function playDeskReplay(sym) {
  sym = (sym || "").toUpperCase();
  const [rooms, uni, quant, fund, fvAll] = await Promise.all([
    j("rooms.json"), j("universe.json"), j("quant.json"), j("fundamentals.json"), j("fairvalue.json")]);
  const s = rooms && rooms[sym];
  if (!s || !s.bull_case) return;
  track("deskroom_played", { sym });
  markActivated("deskroom");   // fire-and-forget — a lookup is the activation moment, don't block the replay
  const name = uni?.symbols?.[sym]?.name || "";
  const q = quant?.tickers?.[sym] || {}, f = fund?.tickers?.[sym] || {}, fv = fvAll?.tickers?.[sym] || {};
  const ta = s.ta_memo || {}, fa = s.fa_memo || {}, bull = s.bull_case || {}, bear = s.bear_case || {};
  const li = arr => (arr || []).slice(0, 3).map(x => `<li>${esc(x)}</li>`).join("");
  const stance = v => ({ constructive: "up", cautious: "dn", bullish: "up", bearish: "dn", positive: "up", negative: "dn" }[v] || "");
  const nz = v => (v == null || v === "") ? "—" : (typeof v === "number" ? fmt(v) : esc(v));

  const steps = [
    `Loading price history — <b>${esc(sym)}</b>${name ? " · " + esc(name) : ""}`,
    `Technicals · RSI14 <b>${nz(q.rsi14)}</b> · SMA20 <b>${nz(q.sma20)}</b> · SMA50 <b>${nz(q.sma50)}</b>`,
    `Fundamentals · P/E <b>${esc(f.pe || "—")}</b> · yield <b>${esc(f.div_yield || "—")}</b> · beta <b>${esc(f.beta || "—")}</b>`,
    `Fair value · 4 models → composite <b>Rs ${nz(fv.composite_fair)}</b> (${esc(fv.verdict || "—")})`,
    `Strategies · scanned 52 → <b>${(ta.proven_now || []).length}</b> firing on ${esc(sym)}`,
    `Technical desk (Meher) &amp; fundamental desk (Dr. Omar) — memos in`,
    `Bull (Zoya) vs Bear (Khurram) — stress-testing both sides`,
  ];
  if (s.qa) steps.push(`QA agent — cross-examined every number in the room`);
  steps.push(`Bull and bear cases in — points for, points against. Your call.`);

  const panel = (av, nm, role, st, read, facts) => `<div class="rp-panel ${st ? "accent-" + st : ""}">
    <div class="rp-panel-head"><span class="rp-av sm">${av}</span><div><b>${esc(nm)}</b><span class="rp-role">${role}</span></div></div>
    <p class="rp-panel-read">${esc(read || "—")}</p>${facts ? `<div class="rp-facts">${facts}</div>` : ""}</div>`;

  runRevealModal({
    sym, kicker: `Desk Room · ${esc(sym)}`, flagKey: "deskran:" + sym,
    title: `Running the desk on ${esc(sym)}`,
    sub: `Working through ${esc(sym)} the way the desk does — pulling the price history, the technicals and the valuation, then letting the two desks and a bull and a bear argue it out. No verdict at the end — the debate is the point.`,
    steps,
    renderReveal: (bodyEl) => {
      bodyEl.innerHTML = `<div class="rp-reveal">
        <div class="rp-reveal-head"><b>${esc(sym)}${name ? " · " + esc(name) : ""}</b><span>the whole desk, at a glance — computed ${esc(s.dossier_asof || "")} at Rs ${nz(s.price_at_session)}</span>${s.qa ? `<span class="qabadge ok">QA checked</span>` : `<span class="qabadge warn">Not yet verified</span>`}</div>
        <div class="rp-desk">
          ${panel("MC", "Meher", "the chartist · TA", stance(ta.technical_stance), tp(ta, "read"), ta.levels ? `support <b>${nz(ta.levels.support)}</b> · resistance <b>${nz(ta.levels.resistance)}</b> · momentum <b>${esc(ta.momentum || "—")}</b>` : "")}
          ${panel("DO", "Dr. Omar", "the fundamentalist · FA", stance(fa.fundamental_stance), tp(fa, "read"), `valuation <b>${esc((fa.valuation_stance || "—").replace(/_/g, " "))}</b> · dividend <b>${esc(tp(fa, "dividend_safety") || "—")}</b>`)}
          ${panel("ZB", "Zoya", "the bull · case FOR", "up", tp(bull, "thesis"), bull.pillars ? `<ul class="rp-ul">${li(bull.pillars)}</ul>` : "")}
          ${panel("KB", "Khurram", "the bear · case AGAINST", "dn", tp(bear, "thesis"), bear.pillars ? `<ul class="rp-ul">${li(bear.pillars)}</ul>` : "")}
        </div>
        <div class="rp-reveal-foot"><span>Two desks, two sides — the desk's read on ${esc(sym)}, argued both ways. No call, no target: general commentary, not advice.</span>
          <span class="rp-foot-btns"><button class="rp-btn2" data-a="replay">↻ Replay</button><button class="rp-btn2" data-a="deep" data-target="room-transcript">Read the full transcript ›</button></span></div>
      </div>`;
    },
  });
}

/* ---------- Strategy-library run: replays the REAL backtest of all ~52 strategies on this ticker
   and reveals which ones cleared the bar, ranked. Animates precomputed backtests.json. ---------- */
async function playStrategyRun(sym) {
  sym = (sym || "").toUpperCase();
  const [smap, bt, uni] = await Promise.all([j("strategy_map.json"), j("backtests.json"), j("universe.json")]);
  const proven = ((smap?.tickers?.[sym]) || []).slice().sort((a, b) => (b.net_expectancy_pct ?? -99) - (a.net_expectancy_pct ?? -99));
  const nTested = bt?.n_strategies || 52;
  const allTested = Object.entries(bt?.templates || {}).map(([id, per]) => ({ id, ...(per[sym] || {}) })).filter(t => t.n);
  const name = uni?.symbols?.[sym]?.name || "";
  const top = proven[0];
  const pct = h => h != null ? Math.round(h * 100) + "%" : "—";

  const steps = [
    `Loading <b>${esc(sym)}</b>'s full price history — ~19 years`,
    `Backtesting <b>${nTested}</b> strategies bar-by-bar`,
    `Applying trading costs &amp; slippage on every trade`,
    `Filter · win rate ≥ 55% and positive expectancy after costs`,
    `Out-of-sample check · must still work on the unseen last third`,
    `Ranking survivors by net expectancy per trade`,
    `<b>${proven.length}</b> of ${allTested.length || nTested} strategies cleared the bar on ${esc(sym)}`,
  ];

  runRevealModal({
    sym, kicker: `Strategy library · ${esc(sym)}`, flagKey: "stratran:" + sym,
    title: `Running the strategy library on ${esc(sym)}`,
    sub: `Backtesting all ${nTested} of the desk's strategies across ${esc(sym)}'s own ~19 years of price history — costs included, then checked on data the strategy never saw.`,
    steps,
    renderReveal: (bodyEl) => {
      bodyEl.innerHTML = `<div class="rp-reveal">
        <div class="rp-reveal-head"><b>${esc(sym)}${name ? " · " + esc(name) : ""}</b><span>what actually worked — ${proven.length} of ${allTested.length || nTested} strategies cleared win-rate ≥55%, positive expectancy, and out-of-sample</span></div>
        ${proven.length ? `<div class="rp-strat-top"><div class="rp-strat-rank">#1</div>
          <div style="flex:1;min-width:0"><b>${esc(top.name)}</b><span class="rp-role">${esc((top.category || "").replace(/_/g, " "))} · the strongest on ${esc(sym)}</span>
            <div class="rp-facts" style="margin-top:6px">win rate <b>${pct(top.hit_rate)}</b> · net/trade <b class="up">${sgn(top.net_expectancy_pct)}%</b> · trades <b>${top.n}</b> · out-of-sample <b>${pct(top.oos_hit)}</b></div></div></div>
        <div class="card" style="margin-top:10px;padding:0"><table><thead><tr><th>Strategy</th><th class="r">Win</th><th class="r">Net/trade</th><th class="r">Trades</th><th class="r">OOS</th></tr></thead><tbody>${
          proven.map(t => `<tr><td><b>${esc(t.name)}</b> <span class="tag">${esc((t.category || "").replace(/_/g, " "))}</span></td><td class="r num">${pct(t.hit_rate)}</td><td class="r num up">${sgn(t.net_expectancy_pct)}%</td><td class="r num">${t.n}</td><td class="r num">${pct(t.oos_hit)}</td></tr>`).join("")}</tbody></table></div>`
          : `<div class="card"><div class="empty">No strategy cleared the bar on ${esc(sym)} — none held win rate ≥55%, positive expectancy after costs, AND profitability out-of-sample. The desk wouldn't signal it. That's a finding, not a gap.</div></div>`}
        <div class="rp-reveal-foot"><span>Backtested on ${esc(sym)}'s own ~19-year history, costs included, checked on unseen data. Past performance does not predict future results. Research, not advice.</span>
          <span class="rp-foot-btns"><button class="rp-btn2" data-a="replay">↻ Replay</button><button class="rp-btn2" data-a="deep" data-target="testlog">Read the full test log ›</button><button class="rp-btn2" onclick="navigate('/strategies')">All strategies ›</button></span></div>
      </div>`;
    },
  });
}

/* Has the strategy library actually been run on this ticker this session? One flag, shared by the
   ticker page and the board — running it in either place counts, so the product never contradicts
   itself. Adding a stock to the board does NOT set it: the work has to be watched to mean anything. */
function stratRunOn(sym) { try { return !!sessionStorage.getItem("stratran:" + sym); } catch (e) { return false; } }

/* ---------- strategy board (profiles.strategy_board; session-only for guests) ---------- */
function stratBoard() {
  if (me) return (myProfile && myProfile.strategy_board) || [];
  try { return JSON.parse(sessionStorage.getItem("stratboard") || "[]"); } catch (e) { return []; }
}
async function saveStratBoard(list) {
  if (me) return saveProfile({ strategy_board: list });
  try { sessionStorage.setItem("stratboard", JSON.stringify(list)); } catch (e) { /* private mode: board just won't persist */ }
  return null;
}
async function addBoardTicker() {
  if (addBoardTicker._busy) return;
  addBoardTicker._busy = true;
  try {
    const inp = document.getElementById("sb-tkr"), msg = document.getElementById("sb-msg");
    const say = t => { if (msg) msg.textContent = t; };
    const sym = (inp?.value || "").toUpperCase().trim();
    if (!sym) return;
    const uni = await j("universe.json");
    if (!uni?.symbols?.[sym]) return say(`${sym} isn't in the desk's universe — try the suggestions as you type.`);
    const cur = stratBoard();
    if (cur.includes(sym)) return say(`${sym} is already on your board.`);
    if (cur.length >= 12) return say("The board holds 12 stocks — remove one first.");
    const err = await saveStratBoard([...cur, sym]);
    if (err) return say("Couldn't save — try again.");
    pageStrategies();
  } finally {
    addBoardTicker._busy = false;
  }
}
async function removeBoardTicker(sym) {
  const err = await saveStratBoard(stratBoard().filter(s => s !== sym));
  if (!err) pageStrategies();
}

/* ---------- board run: backtests the whole library across every stock on the board and
   ranks the surviving stock–strategy pairs. Animates precomputed backtests, zero agents. ---------- */
async function playBoardRun() {
  const board = stratBoard();
  if (!board.length) return;
  const [smap, bt, uni] = await Promise.all([j("strategy_map.json"), j("backtests.json"), j("universe.json")]);
  const nT = bt?.n_strategies || 52;
  const pct = h => h != null ? Math.round(h * 100) + "%" : "—";
  const pairs = board.flatMap(s => (smap?.tickers?.[s] || []).map(t => ({ sym: s, ...t })))
    .sort((a, b) => (b.net_expectancy_pct ?? -99) - (a.net_expectancy_pct ?? -99));
  const blanks = board.filter(s => !(smap?.tickers?.[s] || []).length);
  const top = pairs[0];

  const steps = [
    `Loading ~19 years of price history for <b>${board.length}</b> stock${board.length > 1 ? "s" : ""}`,
    ...board.map(s => `Backtesting <b>${nT}</b> strategies on <b>${esc(s)}</b> bar-by-bar`),
    `Applying trading costs &amp; slippage on every trade`,
    `Filter · win rate ≥ 55% and positive expectancy after costs`,
    `Out-of-sample check · must still work on the unseen last third`,
    `Ranking <b>${pairs.length}</b> surviving stock–strategy pairs by net expectancy`,
  ];

  runRevealModal({
    sym: "", kicker: "Strategy library · your board",
    title: `Running ${nT} strategies on your ${board.length}-stock board`,
    sub: `Backtesting the desk's whole library across every stock on your board — costs included, then checked on data each strategy never saw — and ranking what actually held up.`,
    steps,
    // per-ticker flags: only the stocks this run actually covered unlock — anywhere in the product
    onReveal: () => { try { board.forEach(s => sessionStorage.setItem("stratran:" + s, "1")); } catch (e) { /* private mode */ } },
    onClose: () => { if (routeHash().replace(/^#\/?/, "").startsWith("strategies")) pageStrategies(); },
    renderReveal: (bodyEl) => {
      bodyEl.innerHTML = `<div class="rp-reveal">
        <div class="rp-reveal-head"><b>Your board · ${board.map(esc).join(" · ")}</b><span>what actually worked — ${pairs.length} stock–strategy pair${pairs.length === 1 ? "" : "s"} cleared win-rate ≥55%, positive expectancy after costs, and out-of-sample</span></div>
        ${top ? `<div class="rp-strat-top"><div class="rp-strat-rank">#1</div>
          <div style="flex:1;min-width:0"><b>${esc(top.name)} on ${esc(top.sym)}</b><span class="rp-role">${esc((top.category || "").replace(/_/g, " "))} · the strongest pair on your board</span>
            <div class="rp-facts" style="margin-top:6px">win rate <b>${pct(top.hit_rate)}</b> · net/trade <b class="up">${sgn(top.net_expectancy_pct)}%</b> · trades <b>${top.n}</b> · out-of-sample <b>${pct(top.oos_hit)}</b></div></div></div>` : ""}
        ${pairs.length ? `<div class="card" style="margin-top:10px;padding:0"><table><thead><tr><th>Stock</th><th>Strategy</th><th class="r">Win</th><th class="r">Net/trade</th><th class="r">Trades</th><th class="r">OOS</th></tr></thead><tbody>${
          pairs.slice(0, 20).map(t => `<tr><td><b>${esc(t.sym)}</b></td><td>${esc(t.name)} <span class="tag">${esc((t.category || "").replace(/_/g, " "))}</span></td><td class="r num">${pct(t.hit_rate)}</td><td class="r num up">${sgn(t.net_expectancy_pct)}%</td><td class="r num">${t.n}</td><td class="r num">${pct(t.oos_hit)}</td></tr>`).join("")}</tbody></table>${pairs.length > 20 ? `<div class="sub" style="padding:10px 17px">…and ${pairs.length - 20} more — the full list is on the page behind this.</div>` : ""}</div>`
          : `<div class="card"><div class="empty">No strategy cleared the bar on ${board.length === 1 ? "this stock" : "any of these stocks"} — none held win rate ≥55%, positive expectancy after costs, AND profitability out-of-sample. The desk wouldn't signal them. That's a finding, not a gap.</div></div>`}
        ${blanks.length && pairs.length ? `<div class="sub" style="margin-top:10px">Nothing cleared the bar on <b>${blanks.map(esc).join(", ")}</b> — their histories are too choppy for these rules.</div>` : ""}
        <div class="rp-reveal-foot"><span>Backtested on each stock's own ~19-year history, costs included, checked on unseen data. Past performance does not predict future results. Research, not advice.</span>
          <span class="rp-foot-btns"><button class="rp-btn2" data-a="replay">↻ Replay</button></span></div>
      </div>`;
    },
  });
}

/* ---------- request a strategy → strategy_requests (RLS: own rows only) ---------- */
async function submitStratRequest() {
  if (!me || !sb) { openAuth("signup"); return; }
  if (submitStratRequest._busy) return;
  submitStratRequest._busy = true;
  try {
    const v = id => (document.getElementById(id)?.value || "").trim();
    const msg = document.getElementById("rq-msg");
    const say = t => { if (msg) msg.textContent = t; };
    const title = v("rq-title"), desc = v("rq-desc"), tkr = v("rq-tkr").toUpperCase();
    if (!title) return say("Give it a name first.");
    if (desc.length < 20) return say("Explain the rules — a few sentences, so the desk can code it faithfully.");
    say("Sending…");
    const { error } = await sb.from("strategy_requests").insert({ title, description: desc, ticker: tkr || null });
    if (error) return say("Couldn't send — try again.");
    ["rq-title", "rq-desc", "rq-tkr"].forEach(id => { const el = document.getElementById(id); if (el) el.value = ""; });
    say("Received ✓ — the desk backtests it, and if it clears the bar it joins the library.");
  } finally {
    submitStratRequest._busy = false;
  }
}

/* ---------- router ---------- */
/* ---------- followed brokers + digest preferences (profiles.followed_brokers / digest_prefs) ---------- */
function followedBrokers() { return (myProfile && myProfile.followed_brokers) || []; }
function digestPrefs() { return (myProfile && myProfile.digest_prefs) || {}; }
async function toggleBroker(name) {
  if (!me) { openAuth("signup"); return; }
  const s = new Set(followedBrokers());
  s.has(name) ? s.delete(name) : s.add(name);
  await saveProfile({ followed_brokers: [...s] });
  pageSettings();
}
async function saveDigest(patch) {
  await saveProfile({ digest_prefs: { ...digestPrefs(), ...patch } });
  pageSettings();
}
async function toggleDigestInc(key) {
  const inc = { ...(digestPrefs().include || {}) };
  inc[key] = !inc[key];
  await saveDigest({ include: inc });
}

async function pageSettings() {
  const [bs, claimsAll] = await Promise.all([j("broker_scorecard.json"), j("claims.json")]);
  if (!me) {
    $("view").innerHTML = `<div class="seg" style="margin-top:4px"><h2>Settings</h2><div class="ln"></div></div>
      <div class="card"><div class="empty">Sign in to set your preferences — follow the broker desks you care about and choose your digest.<br><br>
      <button class="auth-go" style="max-width:220px" onclick="openAuth('signup')">Create a free account</button></div></div>`;
    return;
  }
  const brokerSet = new Set(Object.keys(bs?.brokers || {}));
  (claimsAll?.claims || []).forEach(c => { if (c.source_type === "broker" && c.source) brokerSet.add(c.source); });
  const brokers = [...brokerSet].sort();
  const fb = new Set(followedBrokers());
  const dp = digestPrefs();
  const freq = dp.frequency || "off";
  const inc = dp.include || {};
  const freqBtn = (v, label) => `<button class="seg-opt ${freq === v ? "on" : ""}" onclick="saveDigest({frequency:'${v}'})">${label}</button>`;
  const incRow = (key, label) => `<label class="chk-row"><input type="checkbox" ${inc[key] ? "checked" : ""} onchange="toggleDigestInc('${key}')"> <span>${label}</span></label>`;

  const bd = birthData();
  const birthRow = (l, v) => `<div class="bd-row"><span>${l}</span><b>${esc(v || "—")}</b></div>`;

  const pl = PLANS[planOf()];
  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Settings</h2><div class="ln"></div><span class="pill">${esc(me.email || "")}</span></div>

  <div class="seg"><h2>Your plan</h2><div class="ln"></div><span class="pill ${planOf() === "free" ? "" : "ok"}">${esc(pl.label)}</span></div>
  <div class="card">
    <div class="pc-top"><b style="font-size:16px">${esc(pl.label)} plan</b>${pl.tag ? `<span class="pill">${esc(pl.tag)}</span>` : ""}</div>
    <p class="sub" style="margin:4px 0 10px">${esc(pl.blurb)}</p>
    <div class="bd-bar"><button class="note-save" onclick="navigate('/plans')">See all plans</button>
      <button class="note-save" onclick="setDeskMode('${deskMode() === "learn" ? "pro" : "learn"}')">Switch to the ${deskMode() === "learn" ? "Pro" : "Learner"} desk</button></div>
    <p class="sub" style="margin-top:10px">Payments aren't open yet — card processing through international providers isn't available in Pakistan, so billing will run through a local gateway. Nothing is charged, and plans are set manually until then.</p>
  </div>

  <div class="seg"><h2>Your birth details</h2><div class="ln"></div><span class="pill">${bd ? "on file" : "not set"}</span></div>
  <div class="card">
    <p class="sub" style="margin-bottom:12px">The date, time and place that cast your chart on <a href="/mychart" style="color:var(--accent)">Your Chart</a>. Made a mistake? Edit it and the desk recasts everything. Private to your account.</p>
    ${bd ? `<div class="bd-grid">
      ${birthRow("Date", bd.date)}
      ${birthRow("Time", bd.time_known === false ? "unknown (read from Moon)" : bd.time)}
      ${birthRow("Place", bd.place)}
      ${birthRow("UTC offset", bd.tz != null ? (bd.tz >= 0 ? "+" : "") + bd.tz : "—")}
    </div>
    <div class="bd-bar"><button class="note-save" onclick="openBirthWizard()">Edit birth details</button>
      <button class="bd-clear" onclick="clearBirthData()">Remove</button></div>`
    : `<button class="note-save" onclick="openBirthWizard()">Add my birth details</button>`}
  </div>

  <div class="seg"><h2>Your digest</h2><div class="ln"></div></div>
  <div class="card">
    <p class="sub" style="margin-bottom:12px">A periodic email of what changed on your watchlist and the desk. <b>Delivery isn't switched on yet</b> — we're saving your preference so it's ready the moment email sending goes live.</p>
    <div class="sk" style="margin-bottom:6px">Frequency</div>
    <div class="seg-opts">${freqBtn("off", "Off")}${freqBtn("daily", "Daily")}${freqBtn("weekly", "Weekly")}</div>
    <div class="sk" style="margin:14px 0 6px">Include</div>
    ${incRow("watchlist", "What moved on my watchlist")}
    ${incRow("dailyread", "The desk's daily read")}
    ${incRow("calls", "Newly resolved calls (hits / misses)")}
    ${incRow("brokers", "New broker calls on names I follow")}
  </div>

  <div class="seg"><h2>Followed broker desks</h2><div class="ln"></div><span class="pill">${fb.size} followed</span></div>
  <div class="card">
    <p class="sub" style="margin-bottom:12px">Pick the research houses you want surfaced first on your Research wire. The desk still audits and scores every broker — following one never means trusting it. Research, not advice.</p>
    ${brokers.length ? `<div class="follow-grid">${brokers.map(n => `<button class="follow-chip ${fb.has(n) ? "on" : ""}" data-broker="${esc(n)}">${fb.has(n) ? "✓ " : ""}${esc(n)}</button>`).join("")}</div>`
      : '<div class="empty">No broker desks tracked yet — they appear here as the weekly harvest records their public calls.</div>'}
  </div>

  <div class="seg"><h2>Legal</h2><div class="ln"></div></div>
  <div class="card"><div class="follow-grid">
    <a class="follow-chip" href="/legal/terms">Terms of Service</a>
    <a class="follow-chip" href="/legal/privacy">Privacy Policy</a>
    <a class="follow-chip" href="/legal/risk">Risk Disclosure</a>
  </div></div>`;
}

/* ---------- Plans: what each desk includes. Payment is not wired (no Stripe in Pakistan — a local
   gateway follows), so this page states plainly where things stand rather than dangling a dead
   checkout button. ---------- */
const FEATURE_LABEL = {
  learn: "The Investment Journey + deep-dive course",
  practice: "Practice portfolio — PKR 500k virtual, real prices",
  tools: "Compounding, SIP & zakat calculators",
  astro_full: "Your full astro reading + the daily sky",
  dividends_full: "Every announced payout + buy-by dates",
  earnings_full: "The full earnings calendar",
  value_full: "Model fair value on every stock",
  screener: "Plain-English screener on scored fields",
  scenarios: "Scenario simulator on measured sector betas",
  scanner: "The daily opportunity scanner",
  watch_intel: "Watchlist intelligence — what changed",
  ask: "Ask the desk — instant answers from its data",
  alignment: "Evidence alignment on every stock",
  marketplace: "Publish strategies + community marketplace",
  xray: "Portfolio X-ray against the desk's own rules",
  strategies_run: "Run the strategy library on your board",
  research_full: "The full research library",
  broker_tools: "Your desk's calls scored in public",
};
async function pagePlans() {
  await Promise.resolve();
  const cur = planOf();
  const rank = k => PLAN_ORDER.indexOf(k);
  const card = (k) => {
    const p = PLANS[k], on = me && cur === k;
    const isUp = me && !p.soon && rank(k) > rank(cur);          // a plan above the one you're on
    return `<div class="plan-card ${on ? "on" : ""} ${p.soon ? "soon" : ""}">
      <div class="pc-top"><b>${esc(p.label)}</b>${p.tag ? `<span class="pill ${p.soon ? "" : "ok"}">${esc(p.tag)}</span>` : ""}${on ? '<span class="pill ok">your plan</span>' : ""}</div>
      <p class="sub">${esc(p.blurb)}</p>
      ${p.features.length
        ? `<div class="pc-feats">${p.features.map(f => `<div class="pc-f">${esc(FEATURE_LABEL[f] || f)}</div>`).join("")}</div>`
        // An empty list used to fall through to the Free plan's three bullets — which would now
        // print "Cast your birth chart" on the Broker card. A tier with nothing to list says so.
        : `<div class="pc-feats"><div class="pc-f pc-soon">Scope is still being defined with research houses — nothing is listed here until it is real.</div></div>`}
      ${on
        ? `<div class="pc-cta"><button class="pc-btn ghost" disabled>Your current plan</button></div>`
        : p.soon ? `<div class="pc-cta"><button class="pc-btn ghost" disabled>Coming soon</button></div>`
          : isUp ? `<div class="pc-cta"><button class="pc-btn" onclick="notifyUpgrade('${k}')">Upgrade to ${esc(p.label)} →</button>
              <div class="pc-price sub">Pricing announced when payments open</div></div>`
            : k === "free" ? "" : `<div class="pc-cta"><div class="pc-price sub">Included in your plan</div></div>`}
    </div>`;
  };
  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Plans</h2><div class="ln"></div>${me ? `<span class="pill ${cur === "free" ? "" : "ok"}">${esc(PLANS[cur].label)}</span>` : ""}</div>
  <p class="sub" style="margin-bottom:14px">One data layer, read three ways. <b>Investor</b> teaches you to read the market for yourself; <b>Pro</b> is the full analytical desk; <b>Broker</b> adds public scoring for a research house's own calls.</p>
  <div class="disclaimer"><b>Payments aren't open yet.</b> Card processing through international providers isn't available in Pakistan, so billing will run through a local gateway. Until that's live, nothing is charged and everything currently available to your account stays available.</div>
  <div class="plan-grid plan-grid-3">${PLAN_CARDS.map(card).join("")}</div>
  <div id="upgmsg" class="sub" style="margin-top:10px"></div>
  ${isOwner() ? `<div class="card owner-preview"><div class="ark">owner · preview as</div>
    <p class="sub" style="margin:6px 0 10px">See exactly what each plan's product looks like. This changes only what <b>you</b> see, never your stored plan — reload to return to ${esc(PLANS[realPlan()].label)}.</p>
    <div class="mode-row">${PLAN_ORDER.map(k => `<button class="seg-opt ${planOf() === k ? "on" : ""}" onclick="previewAs('${k}')">${esc(PLANS[k].label)}</button>`).join("")}
      ${_previewPlan ? `<button class="seg-opt" onclick="previewAs(null)">Exit preview</button>` : ""}</div></div>` : ""}
  ${me ? `<div class="card" style="margin-top:12px"><div class="ark">how you're reading the desk</div>
    <p class="sub" style="margin:6px 0 10px">The Learner desk reorders everything around the lessons. You can switch view at any time — it doesn't change your plan.</p>
    <div class="mode-row">
      <button class="seg-opt ${deskMode() === "pro" ? "on" : ""}" onclick="setDeskMode('pro')">Pro desk</button>
      <button class="seg-opt ${deskMode() === "learn" ? "on" : ""}" onclick="setDeskMode('learn')">Learner desk</button>
    </div></div>` : ""}`;
}
/* No checkout to send anyone to yet, so record the interest honestly instead of faking a flow. */
function notifyUpgrade(k) {
  const m = document.getElementById("upgmsg");
  if (!me) { openAuth("signup"); return; }
  if (m) m.innerHTML = `<b>Noted — ${esc(PLANS[k].label)}.</b> Payments open once the local gateway is live; nothing has been charged. Your account keeps everything it has today.`;
}
function previewAs(k) {
  if (!isOwner()) return;
  _previewPlan = k;
  applyDeskMode();
  renderAccountButton();
  pagePlans();
}
async function setDeskMode(m) {
  if (!me) { openAuth("signup"); return; }
  if (planOf() === "investor" && m !== "learn") return;   // the Investor plan is the Investor desk
  myProfile = { ...(myProfile || {}), ui_mode: m };
  await saveProfile({ ui_mode: m });
  applyDeskMode();
  // History API navigation calls route() directly. Only route directly when the
  // destination is already active, because pushState would otherwise add a duplicate entry.
  const target = m === "learn" ? "/learn" : "/today";
  if (appPathname() === target) route(true);
  else navigate(target);
}
/* The nav is declared once in HTML; the shell just flips which group is visible, so there is one
   source of truth for routes and no second menu to keep in sync. */
function applyDeskMode() {
  document.body.dataset.desk = deskMode();
  const badge = document.getElementById("planBadge");
  if (badge) { badge.textContent = PLANS[planOf()].label; badge.hidden = !me; }
}

/* ==========================================================================================
   THE LEARNER DESK — a guided path for people who have never invested. Same data layer, different
   information architecture: lessons in order, each taught on real PSX filings and real desk numbers
   rather than toy examples. Educational only — CLAUDE.md Rule 5 applies here hardest of all: this
   teaches how to read the market, never what to buy.
   ========================================================================================== */
function learnProgress() { return (me && myProfile && myProfile.learn_progress) || {}; }
async function markLesson(stageId, lessonId, done) {
  if (!me) { openAuth("signup"); return; }
  const p = { ...learnProgress() };
  const key = stageId + "/" + lessonId;
  if (done) p[key] = new Date().toISOString(); else delete p[key];
  myProfile = { ...(myProfile || {}), learn_progress: p };
  await saveProfile({ learn_progress: p });
  pageLearn();
}
function lessonDone(stageId, lessonId) { return !!learnProgress()[stageId + "/" + lessonId]; }

/* Each lesson can pull one real slice of the desk into itself, so nothing is taught abstractly. */
async function lessonLive(kind) {
  try {
    if (kind === "dividends") {
      const d = await j("dividends.json");
      const rows = (d?.history || []).filter(x => x.dividend_rs).slice(-3).reverse();
      if (!rows.length) return "";
      return `<div class="ll-live"><b>Real payouts on the desk right now</b>
        ${rows.map(r => `<div class="ll-row"><span>${esc(r.symbol)}</span><span class="sub">${esc(r.announcement || "cash dividend")}</span><b class="num">Rs ${esc(String(r.dividend_rs))}/sh</b></div>`).join("")}
        <a href="/dividends" class="ll-go">See every announced payout, with its buy-by date →</a></div>`;
    }
    if (kind === "earnings") {
      const c = await j("earnings_calendar.json");
      const ev = (c?.events || []).filter(e => e.type === "results").slice(0, 3);
      if (!ev.length) return "";
      return `<div class="ll-live"><b>Results dates the desk already knows about</b>
        ${ev.map(e => `<div class="ll-row"><span>${esc(e.ticker)}</span><span class="sub">${esc(e.note || "results")}</span><b class="num">${esc(e.date)}</b></div>`).join("")}
        <a href="/calendar" class="ll-go">See the full earnings calendar →</a></div>`;
    }
    if (kind === "value") {
      const fv = await j("fairvalue.json");
      const rows = Object.entries(fv?.tickers || {}).slice(0, 3);
      if (!rows.length) return "";
      return `<div class="ll-live"><b>The same ratios, on real companies</b>
        ${rows.map(([s, v]) => `<div class="ll-row"><span>${esc(s)}</span><span class="sub">P/E ${esc(String(v.pe ?? "—"))}× · EPS Rs ${esc(String(v.eps ?? "—"))}</span><b class="num">Rs ${fmt(v.price)}</b></div>`).join("")}
        <a href="/value" class="ll-go">See how the desk values every stock four ways →</a></div>`;
    }
    if (kind === "research") {
      const idx = await j("research_index.json");
      const docs = Object.values(idx?.documents || {}).slice(0, 3);
      if (!docs.length) return "";
      return `<div class="ll-live"><b>Filings the desk has digested</b>
        ${docs.map(d => `<div class="ll-row"><span>${esc(d.source || "")}</span><span class="sub">${esc((d.digest || "").slice(0, 70))}…</span><b class="num">${esc(d.date || "")}</b></div>`).join("")}
        <a href="/research" class="ll-go">Read the research library →</a></div>`;
    }
    if (kind === "strategies") {
      const bt = await j("backtest.json");
      const n = Object.keys(bt?.results || bt?.strategies || {}).length;
      return `<div class="ll-live"><b>The bar, applied</b>
        <p class="sub">The desk holds every rule to win rate ≥55%, positive expectancy after costs, and profitability out-of-sample${n ? ` across ${n} tested sets` : ""} — and publishes the ones that failed too.</p>
        <a href="/strategies" class="ll-go">See which rules actually cleared it →</a></div>`;
    }
    if (kind === "astro") {
      return `<div class="ll-live"><b>Your own chart</b>
        <p class="sub">Cast your birth chart in your browser and read the tradition against the market — framed as exploration, with the test result stated plainly.</p>
        <a href="/mychart" class="ll-go">Open Your Chart →</a></div>`;
    }
  } catch { /* a lesson must never fail to render because a data file is missing */ }
  return "";
}

/* ---------- the lesson player: one idea per card, not a wall of text ----------
   A lesson is played in a focused overlay. Every card type gets its own visual treatment so it is
   never ambiguous whether you are being taught, shown real data, or tested. */
let _pl = null;   // {levelId, lesson, i, answered}

async function openLesson(levelId, lessonId) {
  const cur = await j("curriculum.json");
  const lv = (cur?.levels || []).find(l => l.id === levelId);
  const lesson = lv?.lessons.find(l => l.id === lessonId);
  if (!lesson) return;
  // Fetch the real anchor figures ONCE, before the first paint. renderPlayer must stay synchronous:
  // awaiting inside it let a second render interleave and leave stale .anatomy nodes in the DOM,
  // so clicks bound to a detached copy did nothing.
  const anchor = (lesson.cards || []).some(c => c.type === "anatomy" && c.doc === "income_statement")
    ? await anatomyAnchor() : null;
  _pl = { levelId, lesson, i: 0, answered: false, cur, anchor };
  renderPlayer();
}
function closePlayer() { _pl = null; document.querySelector(".pl-overlay")?.remove(); document.body.style.overflow = ""; pageLearn(); }
function plGo(d) {
  if (!_pl) return;
  const total = _pl.lesson.cards.length + (_pl.lesson.check ? 1 : 0);
  _pl.i = Math.max(0, Math.min(total - 1, _pl.i + d));
  renderPlayer();
}
function plAnswer(btn, correct) {
  const wrap = btn.closest(".pl-quiz");
  const picked = +btn.dataset.i;
  wrap.querySelectorAll(".ls-opt").forEach(b => b.disabled = true);
  const ok = picked === correct;
  btn.classList.add(ok ? "right" : "wrong");
  // one-shot pulse on the button the learner actually pressed
  btn.classList.add(ok ? "quiz-right" : "quiz-wrong");
  const clearPulse = () => { btn.classList.remove("quiz-right", "quiz-wrong"); btn.removeEventListener("animationend", clearPulse); };
  btn.addEventListener("animationend", clearPulse);
  setTimeout(clearPulse, 600);
  if (!ok) wrap.querySelector(`.ls-opt[data-i="${correct}"]`)?.classList.add("right");
  wrap.querySelector(".ls-explain").hidden = false;
  _pl.answered = true;
  const f = document.querySelector(".pl-foot-next");
  if (f) f.hidden = false;
}

/* An interactive, labelled financial statement. Structure is general accounting form; any figure
   shown as real is pulled from the desk's own fundamentals for a real company and labelled with
   its source. Lines the desk does not hold are marked "find this in the filing" — never invented. */
function anatomyHtml(kind, cur, anchor) {
  const a = cur?.anatomies?.[kind];
  if (!a) return "";
  const rows = a.lines.map((ln, i) => {
    if (ln.head) return `<div class="an-head">${esc(ln.l)}</div>`;
    const val = ln.field && anchor?.vals?.[ln.field];
    return `<button class="an-row ${ln.bold ? "b" : ""} ${val ? "has" : ""}" data-i="${i}" onclick="anaPick(this)">
      <span class="an-l" style="padding-left:${(ln.ind || 0) * 16}px">${esc(ln.l)}</span>
      <span class="an-v ${ln.neg ? "neg" : ""}">${val ? esc(val) : `<i>in the filing</i>`}</span>
      <span class="an-i">?</span></button>`;
  }).join("");
  return `<div class="anatomy" data-kind="${esc(kind)}">
    <div class="an-top"><b>${esc(a.title)}</b><span class="sub">${esc(a.subtitle)}</span></div>
    ${anchor ? `<div class="an-src">Real reported figures for <b>${esc(anchor.sym)}</b>${anchor.name ? ` — ${esc(anchor.name)}` : ""}, from the desk's data layer. The lines marked <i>in the filing</i> are the ones to go find in the company's own annual report — the desk does not hold them, so it does not show a number.</div>` : ""}
    <div class="an-rows">${rows}</div>
    <div class="an-detail" id="anDetail"><span class="sub">Tap any line to learn what it is and what to watch for.</span></div>
  </div>`;
}
function anaPick(btn) {
  const i = +btn.dataset.i, kind = btn.closest(".anatomy")?.dataset.kind;
  const a = _pl?.cur?.anatomies?.[kind]; if (!a) return;
  const ln = a.lines[i];
  document.querySelectorAll(".anatomy .an-row").forEach(b => b.classList.remove("on"));
  btn.classList.add("on");
  const d = document.getElementById("anDetail");
  if (d) d.innerHTML = `<div class="an-d-t">${esc(ln.l)}</div>
    <p>${esc(ln.what)}</p>
    <div class="an-d-w"><span class="ark">what to watch</span>${esc(ln.watch)}</div>`;
}

function docmapHtml(cur) {
  return `<div class="docmap">${(cur?.docmap || []).map((d, i) => `<button class="dm-item" data-i="${i}" onclick="dmPick(this)">
    <b>${esc(d.k)}</b><span class="sub">${esc(d.when)}</span></button>`).join("")}
    <div class="dm-detail" id="dmDetail"><span class="sub">Tap a document to see what it is and what to look for.</span></div></div>`;
}
function dmPick(btn) {
  const d = _pl?.cur?.docmap?.[+btn.dataset.i]; if (!d) return;
  document.querySelectorAll(".dm-item").forEach(b => b.classList.remove("on"));
  btn.classList.add("on");
  const el = document.getElementById("dmDetail");
  if (el) el.innerHTML = `<div class="an-d-t">${esc(d.k)} <span class="pill">${esc(d.when)}</span></div>
    <p>${esc(d.what)}</p><div class="an-d-w"><span class="ark">what to look for</span>${esc(d.look)}</div>`;
}

const DIV_TIMELINE = [
  { k: "Announcement", d: "The board declares a dividend.", n: "Nothing is owed to anyone yet." },
  { k: "Ex-dividend date", d: "From this day the share trades WITHOUT the dividend.", n: "You must already own it before this date. This is the one that decides whether you are paid.", hot: true },
  { k: "Book closure", d: "The register is frozen to determine who gets paid.", n: "Transfers are not processed during this window." },
  { k: "Payment date", d: "Cash actually reaches you.", n: "Withholding tax is deducted at this point." },
];
function timelineHtml() {
  return `<div class="divtl">${DIV_TIMELINE.map((s, i) => `<div class="dt-step ${s.hot ? "hot" : ""}">
    <div class="dt-dot">${i + 1}</div><div class="dt-c"><b>${esc(s.k)}</b><span class="sub">${esc(s.d)}</span>
    <div class="dt-n">${esc(s.n)}</div></div></div>`).join("")}</div>`;
}

function renderPlayer() {
  if (!_pl) return;
  let ov = document.querySelector(".pl-overlay");
  if (!ov) {
    ov = document.createElement("div"); ov.className = "pl-overlay"; document.body.appendChild(ov);
    document.body.style.overflow = "hidden";
    ov.addEventListener("click", e => { if (e.target === ov) closePlayer(); });
  }
  const { lesson, levelId } = _pl;
  const cards = lesson.cards || [];
  const total = cards.length + (lesson.check ? 1 : 0);
  const isQuiz = _pl.i >= cards.length;
  const c = cards[_pl.i];
  const KIND = { text: "lesson", warn: "watch out", key: "the point", anatomy: "interactive", docmap: "interactive", timeline: "interactive" };

  let body = "";
  if (isQuiz) {
    body = `<div class="pl-card k-q">
      <div class="pl-kind k-quiz">check yourself</div>
      <div class="pl-q">${esc(lesson.check.q)}</div>
      <div class="pl-quiz">
        ${lesson.check.options.map((o, i) => `<button class="ls-opt" data-i="${i}" onclick="plAnswer(this,${lesson.check.answer})">${esc(o)}</button>`).join("")}
        <div class="ls-explain" hidden>${esc(lesson.check.explain)}</div>
      </div></div>`;
  } else {
    const inner = c.type === "anatomy" ? anatomyHtml(c.doc, _pl.cur, c.doc === "income_statement" ? _pl.anchor : null)
      : c.type === "docmap" ? docmapHtml(_pl.cur)
        : c.type === "timeline" ? timelineHtml() : "";
    // card-kind classes are namespaced (k-*): a bare `anatomy` class would collide with the
    // .anatomy component rendered inside the card and inherit its border.
    body = `<div class="pl-card k-${c.type}">
      <div class="pl-kind k-${c.type}">${esc(KIND[c.type] || "lesson")}</div>
      ${c.h ? `<h2 class="pl-h">${esc(c.h)}</h2>` : ""}
      ${(c.p || []).map(p => `<p>${esc(p)}</p>`).join("")}
      ${inner}
    </div>`;
  }

  ov.innerHTML = `<div class="pl-box">
    <div class="pl-top">
      <div class="pl-title"><span class="ark">${esc((_pl.cur.levels.find(l => l.id === levelId) || {}).title || "")}</span><b>${esc(lesson.title)}</b></div>
      <button class="pl-x" aria-label="Close lesson" title="Close" onclick="closePlayer()">✕</button>
    </div>
    <div class="pl-dots">${Array.from({ length: total }, (_, i) =>
    `<span class="pl-dot ${i === _pl.i ? "on" : i < _pl.i ? "did" : ""}"></span>`).join("")}</div>
    <div class="pl-body">${body}</div>
    <div class="pl-foot">
      <button class="pl-back" onclick="plGo(-1)" ${_pl.i === 0 ? "disabled" : ""}>← back</button>
      <span class="pl-count">${_pl.i + 1} / ${total}</span>
      ${isQuiz
      ? `<button class="bw-go pl-foot-next" ${_pl.answered ? "" : "hidden"} onclick="finishLesson()">Complete lesson →</button>`
      : `<button class="bw-go" onclick="plGo(1)">Next →</button>`}
    </div>
  </div>`;

}

/* Pick a well-known name the desk actually holds figures for, and format them honestly. */
async function anatomyAnchor() {
  try {
    const [f, uni] = await Promise.all([j("fundamentals.json"), j("universe.json")]);
    const t = f?.tickers || {};
    const pref = ["FFC", "OGDC", "LUCK", "MCB", "ENGRO", "PPL", "HUBC"];
    const sym = pref.find(s => t[s]?.revenue && t[s]?.net_income && t[s]?.eps)
      || Object.keys(t).find(s => t[s]?.revenue && t[s]?.net_income && t[s]?.eps);
    if (!sym) return null;
    const d = t[sym];
    return { sym, name: uni?.symbols?.[sym]?.name || "",
      vals: { revenue: "Rs " + d.revenue, net_income: "Rs " + d.net_income, eps: "Rs " + d.eps } };
  } catch { return null; }
}

async function finishLesson() {
  if (!_pl) return;
  const { levelId, lesson } = _pl;
  closePlayer();
  await markLesson(levelId, lesson.id, true);
}

/* Streak: consecutive calendar days (ending today or yesterday) with at least one lesson completed.
   Derived from the ISO timestamps learn_progress already stores — no extra state. */
function learnStreak() {
  const days = new Set(Object.values(learnProgress()).map(ts => String(ts).slice(0, 10)));
  if (!days.size) return 0;
  const d = new Date(); let n = 0;
  if (!days.has(d.toISOString().slice(0, 10))) d.setDate(d.getDate() - 1);   // today not yet studied → streak may still be alive from yesterday
  while (days.has(d.toISOString().slice(0, 10))) { n++; d.setDate(d.getDate() - 1); }
  return n;
}

/* Journey step actions: real product actions, auto-detected — never a self-declared checkbox. */
function journeyActionState(a) {
  if (a === "watchlist") {
    const n = watchlist().length;
    return { done: n >= 3, label: n >= 3 ? `Watchlist built — ${n} companies starred` : `Star at least 3 companies (${n}/3 so far)`, go: "/board", cta: "Browse the board →" };
  }
  if (a === "paper") {
    const n = (paperState().trades || []).length;
    return { done: n > 0, label: n > 0 ? "First practice position taken" : "Open your practice portfolio and take a position", go: "/practice", cta: "Open Practice →" };
  }
  return null;
}

async function pageLearn() {
  await Promise.resolve();
  const cur = await j("curriculum.json");
  const levels = (cur?.levels || []).filter(v => !v.hidden);
  const lessonOf = (lv, ls) => (cur?.levels || []).find(v => v.id === lv)?.lessons.find(l => l.id === ls);
  const journey = (cur?.journey || []).map(st => ({ ...st,
    ls: st.lessons.map(([lv, ll]) => ({ lv, ll, l: lessonOf(lv, ll) })).filter(x => x.l),
    act: journeyActionState(st.action) }));
  if (!journey.length && !levels.length) {
    $("view").innerHTML = `<div class="seg" style="margin-top:4px"><h2>Learn</h2><div class="ln"></div></div>
      <div class="card"><div class="empty">The syllabus is being prepared.</div></div>`;
    return;
  }
  const stepDone = st => st.ls.every(x => lessonDone(x.lv, x.ll)) && (!st.act || st.act.done);
  const doneSteps = journey.filter(stepDone).length;
  // the current step is the first incomplete one; steps beyond it are locked (the path is the point)
  const curIdx = journey.findIndex(st => !stepDone(st));
  const streak = learnStreak();
  // today's card: the next unfinished lesson anywhere on the journey
  const nextLesson = journey.flatMap(st => st.ls).find(x => !lessonDone(x.lv, x.ll));

  const stepHtml = (st, i) => {
    const done = stepDone(st), lockd = curIdx >= 0 && i > curIdx;
    return `<div class="jy-step ${done ? "done" : ""} ${i === curIdx ? "cur" : ""} ${lockd ? "locked" : ""}">
      <div class="jy-rail"><span class="jy-node">${done ? "✓" : i + 1}</span>${i < journey.length - 1 ? '<span class="jy-line"></span>' : ""}</div>
      <div class="jy-body">
        <div class="jy-head"><b>${esc(st.title)}</b><span class="sub">${esc(st.sub)}</span></div>
        ${lockd ? `<div class="sub jy-lock">Finish the step above first.</div>` : `
        <div class="jy-lessons">${st.ls.map(x => {
      const d = lessonDone(x.lv, x.ll);
      return `<button class="jy-lsn ${d ? "done" : ""}" onclick="openLesson('${esc(x.lv)}','${esc(x.ll)}')">
            <span class="jy-tick">${d ? "✓" : "○"}</span>${esc(x.l.title)}<span class="jy-min">${x.l.mins}m</span></button>`;
    }).join("")}</div>
        ${st.act ? `<div class="jy-act ${st.act.done ? "done" : ""}"><span class="jy-tick">${st.act.done ? "✓" : "→"}</span>
          <span>${esc(st.act.label)}</span>${st.act.done ? "" : `<a href="${st.act.go}" class="jy-go">${esc(st.act.cta)}</a>`}</div>` : ""}`}
      </div></div>`;
  };

  const doneIn = v => v.lessons.filter(l => lessonDone(v.id, l.id)).length;
  const unlocked = i => i === 0 || doneIn(levels[i - 1]) === levels[i - 1].lessons.length;

  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Become an investor</h2><div class="ln"></div><span class="pill">${doneSteps}/${journey.length} steps</span></div>
  <div class="disclaimer">Education, <b>not investment advice</b>. This teaches you to read companies, prices and payouts for yourself — it never tells you what to buy, and nothing here is a recommendation or a forecast.</div>

  <div class="card learn-hero">
    <div class="lh-top">
      <div><div class="ark">the investment journey</div><b style="font-size:22px">${doneSteps} of ${journey.length}</b><span class="sub"> steps complete</span></div>
      <div class="lh-side">${streak ? `<span class="streak-chip" title="Days in a row with at least one lesson completed">◆ ${streak}-day streak</span>` : ""}
      <div class="lh-pct"><b>${Math.round(doneSteps / journey.length * 100)}%</b></div></div>
    </div>
    <div class="lh-bar"><span style="transform:scaleX(${(doneSteps / journey.length).toFixed(4)})"></span></div>
    ${nextLesson ? `<div class="today-card"><div class="ark">today's lesson · ${nextLesson.l.mins} min</div>
      <b>${esc(nextLesson.l.title)}</b><span class="sub">${esc(nextLesson.l.why)}</span>
      <button class="bw-go" style="max-width:240px;margin-top:10px" onclick="openLesson('${esc(nextLesson.lv)}','${esc(nextLesson.ll)}')">${Object.keys(learnProgress()).length ? "Continue" : "Start the journey"} →</button></div>`
      : `<p class="sub" style="margin-top:12px"><b>Journey complete.</b> The market keeps teaching — your watchlist, the News wire and your practice portfolio are where the next lessons come from.</p>`}
  </div>

  <div class="jy">${journey.map(stepHtml).join("")}</div>

  <div class="seg"><h2>Deep dives</h2><div class="ln"></div><span class="pill">${levels.length} levels</span></div>
  <p class="sub" style="margin-bottom:12px">The full course behind the journey — every document a listed company publishes, read line by line. Open in any order once unlocked.</p>
  ${levels.map((v, i) => {
    const dn = doneIn(v), open = unlocked(i), full = dn === v.lessons.length;
    return `<div class="lvl ${open ? "" : "locked"} ${full ? "full" : ""}">
      <div class="lvl-head">
        <span class="lvl-n">${full ? "✓" : v.n}</span>
        <div class="lvl-t"><b>Level ${v.n} · ${esc(v.title)}</b><span class="sub">${esc(v.blurb)}</span></div>
        <span class="pill ${full ? "ok" : ""}">${dn}/${v.lessons.length}</span>
      </div>
      ${open ? `<div class="lvl-lessons">${v.lessons.map((l, k) => {
      const d = lessonDone(v.id, l.id);
      return `<button class="lsn ${d ? "done" : ""}" onclick="openLesson('${esc(v.id)}','${esc(l.id)}')">
          <span class="lsn-n">${d ? "✓" : k + 1}</span>
          <span class="lsn-t"><b>${esc(l.title)}</b><span class="sub">${esc(l.why)}</span></span>
          <span class="lsn-m">${l.mins} min</span></button>`;
    }).join("")}</div>`
        : `<div class="lvl-locked"><span class="sub">Finish Level ${v.n - 1} to open this — the lessons build on each other.</span></div>`}
    </div>`;
  }).join("")}`;
}

/* ==========================================================================================
   PRACTICE PORTFOLIO — virtual PKR 500k at real DPS prices. No real money, ever. The state is a
   replayable trade log (not balances), so P/L is always re-derivable and auditable. Fills happen
   at the live price at the moment of the order — the same thing a real market order gets — and a
   teaching commission is charged so costs are never invisible. Educational only.
   ========================================================================================== */
const PAPER_START = 500000;
function paperState() { return (me && myProfile && myProfile.paper && myProfile.paper.trades) ? myProfile.paper : { trades: [], credited: [] }; }
function paperFee(value) { return Math.max(25, Math.round(value * 0.0015)); } // teaching fee: 0.15%, min Rs 25 — labelled as illustrative, real brokers differ

function paperPositions(p) {
  const pos = {};
  for (const t of p.trades) {
    const q = pos[t.sym] || (pos[t.sym] = { sh: 0, cost: 0, firstBuy: t.ts });
    if (t.side === "buy") { q.cost += t.sh * t.px + t.fee; q.sh += t.sh; }
    else { const avg = q.sh ? q.cost / q.sh : 0; q.cost -= avg * t.sh; q.sh -= t.sh; }
    if (q.sh <= 0) delete pos[t.sym];
  }
  return pos;
}
function paperCash(p) {
  let cash = PAPER_START;
  for (const t of p.trades) cash += (t.side === "buy" ? -(t.sh * t.px + t.fee) : (t.sh * t.px - t.fee));
  for (const c of (p.credits || [])) cash += c.amt;
  return cash;
}

/* Credit announced cash dividends for held positions once a book closure passes. Simplified on
   purpose (uses current share count, bc_start as the cut) and labelled as such in the UI. */
function paperCreditDividends(p, divs) {
  const pos = paperPositions(p);
  const credited = new Set((p.credits || []).map(c => c.id));
  const today = new Date().toISOString().slice(0, 10);
  let changed = false;
  for (const d of (divs?.history || [])) {
    if (!d.dividend_rs || !d.bc_start || !pos[d.symbol]) continue;
    const id = d.symbol + "|" + d.bc_start;
    if (credited.has(id) || d.bc_start > today) continue;
    if (new Date(pos[d.symbol].firstBuy).toISOString().slice(0, 10) >= d.bc_start) continue; // bought after the closure — not entitled
    (p.credits = p.credits || []).push({ id, sym: d.symbol, amt: +(pos[d.symbol].sh * d.dividend_rs).toFixed(2), rs: d.dividend_rs, on: d.bc_start });
    changed = true;
  }
  return changed;
}

async function paperTrade(side) {
  const sym = (document.getElementById("pp-sym")?.value || "").trim().toUpperCase();
  const sh = Math.floor(+(document.getElementById("pp-sh")?.value || 0));
  const msg = document.getElementById("pp-msg");
  const say = t => { if (msg) msg.textContent = t; };
  if (!me) { openAuth("signup"); return; }
  if (!sym || sh <= 0) return say("Pick a stock and a whole number of shares.");
  const [lv, q] = await Promise.all([j("live.json"), j("quant.json")]);
  const px = lv?.tickers?.[sym]?.current ?? q?.tickers?.[sym]?.close;
  if (!px) return say(`No price for ${sym} in the data layer — check the symbol.`);
  const p = { trades: [], credits: [], ...paperState() };
  const fee = paperFee(sh * px);
  if (side === "buy") {
    const cash = paperCash(p);
    if (sh * px + fee > cash) return say(`Not enough virtual cash — that's Rs ${fmt(sh * px + fee)} with the fee, you have Rs ${fmt(cash)}.`);
  } else {
    const held = paperPositions(p)[sym]?.sh || 0;
    if (sh > held) return say(`You hold ${held} shares of ${sym} — can't sell ${sh}.`);
  }
  p.trades.push({ side, sym, sh, px, fee, ts: new Date().toISOString() });
  myProfile = { ...(myProfile || {}), paper: p };
  await saveProfile({ paper: p });
  pagePractice();
}
async function paperReset() {
  if (!confirm("Reset the practice portfolio to Rs 500,000? The trade history is cleared.")) return;
  myProfile = { ...(myProfile || {}), paper: { trades: [], credits: [] } };
  await saveProfile({ paper: { trades: [], credits: [] } });
  pagePractice();
}

async function pagePractice() {
  await Promise.resolve();
  if (!me) {
    $("view").innerHTML = `<div class="seg" style="margin-top:4px"><h2>Practice portfolio</h2><div class="ln"></div></div>
      <div class="disclaimer">Virtual money at real market prices — <b>education, not advice</b>, and never a forecast of real returns.</div>
      <div class="card mychart-cta">
        <h2>Learn with PKR 500,000 you can't lose</h2>
        <p class="sub">Real PSX prices, no real money: buy, size, sit through red days, collect dividends at book closure. Every mechanic of investing, none of the damage. Free with an account.</p>
        <button class="bw-go" style="max-width:260px" onclick="openAuth('signup')">Create a free account →</button></div>`;
    return;
  }
  const [lv, q, uni, sectors, divs, idx, corr] = await Promise.all([
    j("live.json"), j("quant.json"), j("universe.json"), j("sectors.json"), j("dividends.json"), j("indices.json"), j("correlation.json"),
    loadDeskRules()]);   // Rule 4 limits from config, not the hardcoded fallback
  const p = { trades: [], credits: [], ...paperState() };
  if (paperCreditDividends(p, divs)) { myProfile = { ...(myProfile || {}), paper: p }; saveProfile({ paper: p }); }
  const pos = paperPositions(p), cash = paperCash(p);
  const pxOf = s => lv?.tickers?.[s]?.current ?? q?.tickers?.[s]?.close;
  const rows = Object.entries(pos).map(([s, x]) => {
    const px = pxOf(s), val = px ? px * x.sh : null, avg = x.cost / x.sh;
    return { s, sh: x.sh, avg, px, val, pl: val != null ? val - x.cost : null, plp: val != null ? (val / x.cost - 1) * 100 : null, sector: sectors?.tickers?.[s]?.sector || "" };
  }).sort((a, b) => (b.val || 0) - (a.val || 0));
  const invested = rows.reduce((a, r) => a + (r.val || 0), 0);
  const total = cash + invested, ret = (total / PAPER_START - 1) * 100;
  // benchmark: KSE100 since the first trade — same window, honest comparison
  let bench = null;
  if (p.trades.length && idx?.history) {
    const d0 = p.trades[0].ts.slice(0, 10);
    const days = Object.keys(idx.history).sort();
    const k0 = idx.history[days.find(d => d >= d0) || days[days.length - 1]]?.KSE100;
    const k1 = idx.live?.KSE100 ?? idx.history[days[days.length - 1]]?.KSE100;
    if (k0 && k1) bench = (k1 / k0 - 1) * 100;
  }
  // sector concentration — echo the desk's own rule as education
  const bySec = {};
  rows.forEach(r => { if (r.sector && r.val) bySec[r.sector] = (bySec[r.sector] || 0) + r.val; });
  const heavy = Object.entries(bySec).filter(([, v]) => invested && v / total > 0.35).map(([k]) => k);
  const sTile = (label, val, sub, k) => `<div class="sumtile"><span class="sk">${label}</span><b class="${k || ""}">${val}</b>${sub ? `<i>${sub}</i>` : ""}</div>`;

  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Practice portfolio</h2><div class="ln"></div><span class="pill">virtual money · real prices</span></div>
  <div class="disclaimer">Virtual PKR ${fmt(PAPER_START)} at real market prices, for <b>education only</b>. Paper results overstate real ones — they can't simulate fear, and fills here ignore market depth. A teaching commission (0.15%, min Rs 25) is applied so costs are never invisible; real brokers' fees differ.</div>
  <div class="sumstrip s4">
    ${sTile("Portfolio value", "Rs " + fmt(total), `started Rs ${fmt(PAPER_START)}`, ret >= 0 ? "up" : "dn")}
    ${sTile("Return", sgn(+ret.toFixed(2)) + "%", bench != null ? `KSE100 ${sgn(+bench.toFixed(2))}% same period` : "since your first trade", ret >= 0 ? "up" : "dn")}
    ${sTile("Cash", "Rs " + fmt(Math.round(cash)), `${rows.length} position${rows.length === 1 ? "" : "s"}`, "")}
    ${sTile("Dividends credited", "Rs " + fmt(Math.round((p.credits || []).reduce((a, c) => a + c.amt, 0))), (p.credits || []).length ? `${(p.credits || []).length} payout${(p.credits || []).length === 1 ? "" : "s"}` : "when book closures pass", "")}
  </div>
  ${heavy.length ? `<div class="disclaimer"><b>Concentration flag:</b> over a third of this portfolio sits in ${heavy.map(esc).join(", ")}. The desk's own rules never allow two positions in one sector — worth practising the same discipline.</div>` : ""}
  ${deskRulePanel(rows, total, invested, corr)}

  <div class="card">
    <div class="ark">place a practice order</div>
    <div class="pp-form">
      <input id="pp-sym" class="ph-in combo" type="search" enterkeyhint="next" aria-label="Ticker to trade" placeholder="Ticker (e.g. FFC)" autocomplete="off" style="flex:0 1 170px">
      <input id="pp-sh" class="ph-in" aria-label="Number of shares" type="text" inputmode="numeric" enterkeyhint="done" placeholder="Shares" style="flex:0 1 130px">
      <button class="note-save" onclick="paperTrade('buy')">Buy</button>
      <button class="note-save" onclick="paperTrade('sell')">Sell</button>
      <span id="pp-msg" class="sub"></span>
    </div>
    <p class="sub" style="margin-top:8px">Fills at the current DPS price — the same price the whole desk runs on. Write one sentence for why, before you press the button; that habit is the actual lesson.</p>
  </div>

  <div class="seg"><h2>Holdings</h2><div class="ln"></div><span class="pill">${rows.length}</span>${rows.length ? csvBtn("holdings") : ""}</div>
  <div class="card" style="padding:0">${rows.length ? `<table><thead><tr><th>Stock</th><th>Sector</th><th class="r">Shares</th><th class="r">Avg cost</th><th class="r">Price</th><th class="r">Value</th><th class="r">P/L</th></tr></thead><tbody>${
    rows.map(r => `<tr class="clickable" onclick="navigate('/ticker/${r.s}')"><td><b>${r.s}</b> <span class="sub">${esc((uni?.symbols?.[r.s]?.name || "").slice(0, 20))}</span></td>
      <td class="sub">${esc((r.sector || "").slice(0, 18))}</td><td class="r num">${r.sh}</td><td class="r num">${fmt(r.avg)}</td>
      <td class="r num">${r.px ? fmt(r.px) : "—"}</td><td class="r num">${r.val ? fmt(Math.round(r.val)) : "—"}</td>
      <td class="r num ${r.pl >= 0 ? "up" : "dn"}">${r.pl != null ? sgn(+r.plp.toFixed(1)) + "%" : "—"}</td></tr>`).join("")}</tbody></table>`
    : `<div class="empty">No positions yet. Study a company first — then take your first position with money that can't hurt you.</div>`}</div>

  ${(p.credits || []).length ? `<div class="seg"><h2>Dividends received</h2><div class="ln"></div></div>
  <div class="card" style="padding:0"><table><thead><tr><th>Stock</th><th class="r">Rs/sh</th><th class="r">Credited</th><th class="r">On closure</th></tr></thead><tbody>${
    p.credits.map(c => `<tr><td><b>${esc(c.sym)}</b></td><td class="r num">${c.rs}</td><td class="r num up">Rs ${fmt(c.amt)}</td><td class="r num">${esc(c.on)}</td></tr>`).join("")}</tbody></table>
  <div class="sub" style="padding:10px 15px">Simplified crediting: current shares × announced Rs/share once a book closure date passes, if the position predates it. Real settlements involve withholding tax and exact register timing.</div></div>` : ""}

  ${p.trades.length ? `<div class="seg"><h2>Trade log</h2><div class="ln"></div><span class="pill">${p.trades.length}</span></div>
  <div class="card" style="padding:0"><table><thead><tr><th>When</th><th>Side</th><th>Stock</th><th class="r">Shares</th><th class="r">Price</th><th class="r">Fee</th></tr></thead><tbody>${
    p.trades.slice().reverse().slice(0, 40).map(t => `<tr><td class="num sub">${esc(t.ts.slice(0, 16).replace("T", " "))}</td>
      <td><span class="pill ${t.side === "buy" ? "ok" : "bad"}">${t.side}</span></td><td><b>${esc(t.sym)}</b></td>
      <td class="r num">${t.sh}</td><td class="r num">${fmt(t.px)}</td><td class="r num">${t.fee}</td></tr>`).join("")}</tbody></table></div>
  <p class="sub" style="margin-top:10px"><button class="note-save" onclick="paperReset()">Reset to Rs 500,000</button> · The log is the point — review it monthly and ask which trades had a written reason.</p>` : ""}`;
}

/* ==========================================================================================
   SINCE YOUR LAST VISIT — what actually changed while you were away.
   Kept entirely in localStorage: no account needed, nothing leaves the browser, and no server
   state to keep in sync. The snapshot is only re-taken after SNAP_MIN minutes so that a reload
   (or the 30-second auto-refresh) cannot silently consume the very diff you came back to read.
   ========================================================================================== */
const VISIT_KEY = "psx_visit", SNAP_MIN = 30, VISIT_MIN_GAP_H = 6;
function visitSnap() { try { return JSON.parse(localStorage.getItem(VISIT_KEY) || "null"); } catch { return null; } }
async function sinceLastVisit(q, lv) {
  let prev = null;
  try { prev = visitSnap(); } catch { return ""; }
  const dash = await j("dashboard.json");
  const wl = (typeof watchlist === "function" ? watchlist() : []) || [];
  const pxOf = s => lv?.[s]?.current ?? q?.[s]?.close;
  const now = Date.now();
  const snap = { ts: now,
    sigs: (dash?.signals || []).map(s => s.id).filter(Boolean),
    news: (dash?.news || []).filter(n => (n.impact || 0) >= 4).length,
    px: Object.fromEntries(wl.map(s => [s, pxOf(s)]).filter(([, p]) => p != null)) };
  const save = () => { try { localStorage.setItem(VISIT_KEY, JSON.stringify(snap)); } catch { /* private mode — the feature simply doesn't persist */ } };
  if (!prev || !prev.ts) { save(); return ""; }                       // first ever visit: nothing to diff against
  const hours = (now - prev.ts) / 3.6e6;
  if (hours < VISIT_MIN_GAP_H) { if (hours > SNAP_MIN / 60) save(); return ""; }   // same session — no banner, refresh the snapshot
  const newSigs = snap.sigs.filter(id => !(prev.sigs || []).includes(id));
  const movers = Object.entries(snap.px)
    .map(([s, p]) => ({ s, p, was: prev.px?.[s] }))
    .filter(x => x.was && Math.abs(x.p / x.was - 1) * 100 >= 3)
    .map(x => ({ s: x.s, chg: (x.p / x.was - 1) * 100 }))
    .sort((a, b) => Math.abs(b.chg) - Math.abs(a.chg)).slice(0, 4);
  const newsDelta = Math.max(0, (snap.news || 0) - (prev.news || 0));
  save();
  if (!newSigs.length && !movers.length && !newsDelta) return "";
  const ago = hours < 48 ? `${Math.round(hours)} hours` : `${Math.round(hours / 24)} days`;
  const bits = [];
  if (newSigs.length) bits.push(`<b>${newSigs.length} new setup${newSigs.length === 1 ? "" : "s"}</b>`);
  if (newsDelta) bits.push(`<b>${newsDelta} material news item${newsDelta === 1 ? "" : "s"}</b> (impact 4+)`);
  if (movers.length) bits.push(`on your watchlist: ${movers.map(m => `<a href="/ticker/${esc(m.s)}" class="${m.chg > 0 ? "up" : "dn"}" style="font-weight:700">${esc(m.s)} ${sgn(+m.chg.toFixed(1))}%</a>`).join(", ")}`);
  return `<div class="card since-card">
    <div class="since-head"><span class="ark">since your last visit · ${esc(ago)} ago</span>
      <button class="since-x" onclick="this.closest('.since-card').remove()" aria-label="Dismiss">✕</button></div>
    <div class="since-body">${bits.join(" · ")}</div>
    <div class="sub" style="margin-top:6px">Price moves are measured from what you last saw, not from any entry — this is a catch-up note, not a performance figure.</div>
  </div>`;
}

/* ==========================================================================================
   DESK RULES — the desk's own Rule 4 risk limits, checked live against the practice book.

   Sourced from state/desk_rules.json, which build_dashboard.py exports from config/desk.json
   every cycle. config/ itself is deliberately NOT served: it holds capital_pkr (the owner's
   real trading capital) and the Telegram token, so the export is an allow-list of rule
   constants only — a secret added to desk.json later cannot leak by default.

   The literals below are a FALLBACK for a failed fetch, not a second source of truth. They
   were previously the only copy, which drifts silently the moment config changes. loadDeskRules()
   overwrites them; if it ever can't, the checker still works and says the values are defaults.
   ========================================================================================== */
const DESK_RULES = { max_positions: 4, max_total_exposure_pct: 20, max_same_sector_positions: 1,
  risk_per_trade_pct: 1, max_pct_per_trade: 8 };
let DESK_RULES_SOURCE = "fallback";

async function loadDeskRules() {
  if (DESK_RULES_SOURCE !== "fallback") return DESK_RULES;
  const d = await j("desk_rules.json");
  const r = d?.rules;
  if (r && r.max_pct_per_trade != null) {
    Object.assign(DESK_RULES, r);
    DESK_RULES_SOURCE = "config";
  }
  return DESK_RULES;
}

/* CLAUDE.md Rule 4's sizing formula — THE only one. Kept as a single function so the practice
   sizer and any future caller cannot drift into two different answers. */
function deskSize(capital, entry, stop) {
  if (!(capital > 0) || !(entry > 0) || !(stop >= 0) || entry <= stop) return null;   // entry<=stop is invalid, not merely zero
  const riskBudget = capital * DESK_RULES.risk_per_trade_pct / 100;
  const shares = Math.floor(Math.min(riskBudget / (entry - stop), capital * DESK_RULES.max_pct_per_trade / 100 / entry));
  return shares > 0 ? { shares, value: shares * entry, risk: shares * (entry - stop),
    capped: riskBudget / (entry - stop) > capital * DESK_RULES.max_pct_per_trade / 100 / entry } : null;
}
/* The correlation layer catches what the sector rule structurally cannot: two names in DIFFERENT
   sectors that nonetheless move together (an E&P and an OMC; two affiliates filed under different
   sector codes). Rule 4 would wave those through as diversified. This warns; it never blocks or
   sizes anything — sector remains the hard constraint. Note the peer lists are top-N truncated and
   therefore ASYMMETRIC, so a hit in EITHER direction counts. */
function correlatedPairs(held, corr) {
  const t = corr?.tickers || {}, out = [], seen = new Set();
  for (const a of held) for (const b of held) {
    if (a.s === b.s) continue;
    const key = [a.s, b.s].sort().join("|");
    if (seen.has(key)) continue;
    const hit = (t[a.s]?.peers || []).find(p => p.symbol === b.s) || (t[b.s]?.peers || []).find(p => p.symbol === a.s);
    if (hit && hit.r >= (corr.high_corr_threshold ?? 0.6)) { seen.add(key); out.push({ a: a.s, b: b.s, r: hit.r, sameSector: a.sector && a.sector === b.sector }); }
  }
  return out.sort((x, y) => y.r - x.r);
}
function deskRulePanel(rows, total, invested, corr) {
  const held = rows.filter(r => r.val);
  const secCount = {};
  held.forEach(r => { if (r.sector) secCount[r.sector] = (secCount[r.sector] || 0) + 1; });
  const dupes = Object.entries(secCount).filter(([, n]) => n > DESK_RULES.max_same_sector_positions);
  const corrPairs = correlatedPairs(held, corr);
  const crossSector = corrPairs.filter(p => !p.sameSector);
  const expo = total ? invested / total * 100 : 0;
  const check = (ok, label, detail) => `<div class="dr-row"><span class="dr-dot ${ok ? "ok" : "no"}">${ok ? "✓" : "!"}</span>
    <span class="dr-lab">${label}</span><span class="dr-det sub">${detail}</span></div>`;
  return `
  <div class="seg"><h2>Against the desk's own rules</h2><div class="ln"></div><span class="pill">Rule 4</span>${
    DESK_RULES_SOURCE === "fallback" ? '<span class="pill wait" title="state/desk_rules.json did not load — showing built-in defaults, which may not match the desk\'s current config">defaults</span>' : ""}</div>
  <div class="card">
    <p class="sub" style="margin-bottom:10px">The desk holds itself to hard limits it cannot override. Your practice book is checked against the same ones — as <b>education about one specific discipline</b>, not a verdict on your portfolio.</p>
    ${check(held.length <= DESK_RULES.max_positions, `Max ${DESK_RULES.max_positions} concurrent positions`, `you hold ${held.length}`)}
    ${check(expo <= DESK_RULES.max_total_exposure_pct, `Max ${DESK_RULES.max_total_exposure_pct}% total exposure`, `you are ${expo.toFixed(1)}% invested, ${(100 - expo).toFixed(1)}% cash`)}
    ${check(!dupes.length, "No two positions in one sector", dupes.length ? `${dupes.map(([s, n]) => `${esc(s)} ×${n}`).join(", ")}` : `${Object.keys(secCount).length} sector${Object.keys(secCount).length === 1 ? "" : "s"}, no doubles`)}
    ${corr ? check(!crossSector.length, "No two positions that move together", crossSector.length
      ? `${crossSector.map(p => `${esc(p.a)}~${esc(p.b)} r=${p.r}`).join(", ")}`
      : held.length > 1 ? "no pair above r=" + (corr.high_corr_threshold ?? 0.6) : "needs two or more positions") : ""}
    <div class="tnote" style="margin-top:10px"><b>Read the exposure rule in context.</b> 20% is deliberately severe because it governs a <b>concentrated, stop-loss-driven research book</b> — four positions at most, each exited on a defined stop. It is not a claim that a long-term investor should hold 80% cash, and this panel is not telling you to sell anything. Different objective, different rules.</div>
    ${crossSector.length ? `<div class="tnote warn" style="margin-top:8px"><b>Different sectors, same trade.</b> ${crossSector.map(p => `<b>${esc(p.a)}</b> and <b>${esc(p.b)}</b> have moved together ${Math.round(p.r * 100)}% of the way`).join("; ")} over the measured window — so the sector rule reads this book as diversified when, historically, these names have not been. Correlation is backward-looking and rises further in sell-offs, which is exactly when diversification is supposed to help.</div>` : ""}
  </div>

  <div class="seg"><h2>Position sizer</h2><div class="ln"></div><span class="pill">the desk's formula</span></div>
  <div class="card">
    <p class="sub" style="margin-bottom:10px">Size is decided by <b>where your stop is</b>, never by how much you like the idea. This is the exact formula the desk's Strategist and Auditor both compute — if they ever disagree, the setup is killed.</p>
    <div class="pp-form">
      <label class="dr-f">Capital (Rs)<input id="dz-cap" class="ph-in" type="text" inputmode="decimal" enterkeyhint="next" value="${Math.round(total) || PAPER_START}" oninput="deskSizeRun()"></label>
      <label class="dr-f">Entry (Rs)<input id="dz-entry" class="ph-in" type="text" inputmode="decimal" enterkeyhint="next" placeholder="e.g. 245.56" oninput="deskSizeRun()"></label>
      <label class="dr-f">Stop (Rs)<input id="dz-stop" class="ph-in" type="text" inputmode="decimal" enterkeyhint="done" placeholder="e.g. 233.28" oninput="deskSizeRun()"></label>
    </div>
    <div id="dz-out" class="sub" style="margin-top:10px">Enter an entry and a stop to size it.</div>
  </div>`;
}
function deskSizeRun() {
  const num = id => parseFloat($(id)?.value);
  const cap = num("dz-cap"), entry = num("dz-entry"), stop = num("dz-stop"), out = $("dz-out");
  if (!out) return;
  if (!(cap > 0) || !(entry > 0) || !(stop > 0)) { out.innerHTML = "Enter an entry and a stop to size it."; return; }
  if (entry <= stop) { out.innerHTML = `<b class="dn">Invalid setup.</b> The stop must sit BELOW the entry — the desk is long-only, so a stop at or above entry has no risk-per-share to size against and the setup is rejected outright.`; return; }
  const r = deskSize(cap, entry, stop);
  if (!r) { out.innerHTML = `<b class="dn">Size works out to zero shares.</b> The stop is too far from the entry for this capital — at these levels a single share would risk more than the ${DESK_RULES.risk_per_trade_pct}% budget allows. The desk treats that as an invalid setup, not a reason to round up.`; return; }
  track("sizer_computed", {});   // no financial values in the event — Rule 5, no advice language, applies to analytics too
  markActivated("sizer");
  const riskBudget = cap * DESK_RULES.risk_per_trade_pct / 100;
  out.innerHTML = `<div class="statgrid num" style="margin-bottom:8px">
      <div class="stat"><span>shares</span><b>${fmt(r.shares, 0)}</b></div>
      <div class="stat"><span>position value</span><b>Rs ${fmt(Math.round(r.value), 0)}</b></div>
      <div class="stat"><span>risked if stopped</span><b class="dn">Rs ${fmt(Math.round(r.risk), 0)}</b></div>
      <div class="stat"><span>% of capital</span><b>${(r.value / cap * 100).toFixed(1)}%</b></div>
    </div>
    Risk budget is <b>${DESK_RULES.risk_per_trade_pct}% of capital = Rs ${fmt(Math.round(riskBudget), 0)}</b>; risk per share is <b>Rs ${(entry - stop).toFixed(2)}</b>.
    ${r.capped ? `<b>The ${DESK_RULES.max_pct_per_trade}% position-value cap is what bound this size</b>, not the stop distance — meaning the stop is tight enough that the risk budget alone would have allowed a position too large to hold in one name.`
      : `The stop distance bound this size; the position sits under the ${DESK_RULES.max_pct_per_trade}% position-value cap.`}
    <br><br>Sizing arithmetic, not a recommendation to take this trade.`;
}

/* ==========================================================================================
   TOOLS — seven calculators, tailored to rupees and PSX rather than generic web widgets.
   Every default that can be anchored to a REAL, sourced Pakistani number is (SBP policy rate,
   PBS CPI, T-bill/PIB yields, gold + USD/PKR for zakat nisab), pulled live from the data layer —
   never typed from memory (CLAUDE.md Rule 2). The dividend-reinvestment tool runs on actual PSX
   payout history and actual prices. Nothing here forecasts or advises.
   ========================================================================================== */
let _tools = { tab: "compound", macro: null, mh: null };
const TOOL_TABS = [
  ["compound", "Compound growth"], ["sip", "SIP / monthly"], ["inflation", "Inflation"],
  ["divreinvest", "Dividend reinvestment"], ["goal", "Goal planner"],
  ["mortgage", "Mortgage"], ["zakat", "Zakat on shares"],
];
const tnum = id => +(document.getElementById(id)?.value || 0) || 0; // text inputmode="decimal" can yield non-numeric text; NaN -> 0
const rs = n => "Rs " + fmt(Math.round(n));
/* real anchors, read from the desk's own macro layer */
function tAnchors() {
  const m = _tools.macro || {};
  return { cpi: m.cpi_yoy, policy: m.sbp_rate, tbill: m.domestic?.tbill_6m, pib: m.domestic?.pib_10y, when: (m.updated || "").slice(0, 10) };
}
function anchorChips() {
  const a = tAnchors(); const c = [];
  if (a.cpi != null) c.push(`<span class="tchip">CPI <b>${a.cpi}%</b></span>`);
  if (a.policy != null) c.push(`<span class="tchip">SBP policy <b>${a.policy}%</b></span>`);
  if (a.tbill != null) c.push(`<span class="tchip">6M T-bill <b>${a.tbill}%</b></span>`);
  if (a.pib != null) c.push(`<span class="tchip">10Y PIB <b>${a.pib}%</b></span>`);
  return c.length ? `<div class="tchips">${c.join("")}<span class="sub">live from the desk's macro layer${a.when ? ` · ${esc(a.when)}` : ""}</span></div>` : "";
}
function toolTile(k, v, sub, cls) { return `<div class="sumtile"><span class="sk">${k}</span><b class="${cls || ""}">${v}</b>${sub ? `<i>${sub}</i>` : ""}</div>`; }

/* future value of a lump sum + monthly contributions, monthly compounding */
function fvSeries(lump, monthly, years, annualRate) {
  const mr = Math.pow(1 + annualRate, 1 / 12) - 1, n = Math.round(years * 12);
  let v = lump; const yearly = [];
  for (let i = 1; i <= n; i++) { v = v * (1 + mr) + monthly; if (i % 12 === 0) yearly.push(v); }
  return { end: v, contributed: lump + monthly * n, yearly };
}
/* a small inline bar chart — contributions vs growth, year by year */
function growthBars(yearly, lump, monthly) {
  if (!yearly.length) return "";
  const max = yearly[yearly.length - 1] || 1;
  return `<div class="tbars">${yearly.map((v, i) => {
    const put = lump + monthly * 12 * (i + 1);
    const h = Math.max(2, v / max * 100), ph = Math.max(1, Math.min(h, put / max * 100));
    return `<div class="tbar" title="Year ${i + 1}: ${rs(v)} (you put in ${rs(put)})">
      <span class="tb-grow" style="height:${h}%"></span><span class="tb-put" style="height:${ph}%"></span>
      <i>${i + 1}</i></div>`;
  }).join("")}</div>
  <div class="tlegend"><span><span class="sw put"></span>what you put in</span><span><span class="sw grow"></span>total value</span></div>`;
}

function toolCompound() {
  const lump = tnum("t-lump"), years = tnum("t-years"), rate = tnum("t-rate") / 100, infl = tnum("t-infl") / 100;
  const r = fvSeries(lump, 0, years, rate);
  const real = r.end / Math.pow(1 + infl, years);
  const beatsInflation = rate > infl;
  return `<div class="sumstrip s4">
    ${toolTile("Ending value", rs(r.end), `after ${years} years`, "up")}
    ${toolTile("You put in", rs(r.contributed), "one lump sum", "")}
    ${toolTile("Growth", rs(r.end - r.contributed), `at ${(rate * 100).toFixed(1)}%/yr`, r.end >= r.contributed ? "up" : "dn")}
    ${toolTile("In today's rupees", rs(real), `after ${(infl * 100).toFixed(1)}% inflation`, real >= lump ? "up" : "dn")}
  </div>
  ${growthBars(r.yearly, lump, 0)}
  <div class="tnote ${beatsInflation ? "" : "warn"}">${beatsInflation
    ? `At ${(rate * 100).toFixed(1)}% against ${(infl * 100).toFixed(1)}% inflation, this money grows in <b>real</b> terms — the "today's rupees" tile is the honest one, and it is what your savings would actually buy.`
    : `<b>This loses purchasing power.</b> ${(rate * 100).toFixed(1)}% against ${(infl * 100).toFixed(1)}% inflation means the ending amount buys <b>less</b> than what you put in. Beating inflation is the first job, not the last.`}</div>`;
}
function toolSip() {
  const monthly = tnum("t-monthly"), lump = tnum("t-lump2"), years = tnum("t-years2"), rate = tnum("t-rate2") / 100, infl = tnum("t-infl2") / 100;
  const r = fvSeries(lump, monthly, years, rate);
  const real = r.end / Math.pow(1 + infl, years);
  return `<div class="sumstrip s4">
    ${toolTile("Ending value", rs(r.end), `${years} yrs × Rs ${fmt(monthly)}/mo`, "up")}
    ${toolTile("You put in", rs(r.contributed), `${Math.round(years * 12)} contributions`, "")}
    ${toolTile("Growth", rs(r.end - r.contributed), `at ${(rate * 100).toFixed(1)}%/yr`, "up")}
    ${toolTile("In today's rupees", rs(real), `after ${(infl * 100).toFixed(1)}% inflation`, "")}
  </div>
  ${growthBars(r.yearly, lump, monthly)}
  <div class="tnote">Saving a fixed amount every month buys more shares when prices are low and fewer when high — which is the whole argument for regularity over timing. Note how much of the ending value is <b>your own contributions</b> in the early years: compounding only becomes the bigger half late, which is why starting early beats starting big.</div>`;
}
function toolInflation() {
  const amt = tnum("t-iamt"), years = tnum("t-iyears"), infl = tnum("t-irate") / 100;
  const future = amt * Math.pow(1 + infl, years);      // what you'd need then to match today
  const worth = amt / Math.pow(1 + infl, years);       // what today's amount buys then
  const a = tAnchors();
  return `<div class="sumstrip s3">
    ${toolTile("Rs " + fmt(amt) + " today", rs(worth), `will buy this much in ${years} yrs`, "dn")}
    ${toolTile("To match it you'd need", rs(future), `in ${years} years`, "")}
    ${toolTile("Purchasing power lost", (100 - worth / amt * 100).toFixed(1) + "%", `at ${(infl * 100).toFixed(1)}%/yr`, "dn")}
  </div>
  <div class="tnote warn">This is the case for investing in one number. Cash left idle at ${(infl * 100).toFixed(1)}% inflation loses about <b>${(100 - worth / amt * 100).toFixed(0)}%</b> of its purchasing power over ${years} years — a certainty, not a risk.${a.cpi != null ? ` Pakistan's latest reported CPI is <b>${a.cpi}%</b>${a.tbill != null ? `, and 6-month T-bills yield about <b>${a.tbill}%</b> — the near-riskless bar any investment should be judged against` : ""}.` : ""}</div>`;
}
function toolGoal() {
  const target = tnum("t-gtarget"), years = tnum("t-gyears"), rate = tnum("t-grate") / 100,
    infl = tnum("t-ginfl") / 100, have = tnum("t-ghave");
  const targetReal = target * Math.pow(1 + infl, years);   // the goal costs more by then
  const mr = Math.pow(1 + rate, 1 / 12) - 1, n = Math.round(years * 12);
  const grownHave = have * Math.pow(1 + mr, n);
  const need = Math.max(0, targetReal - grownHave);
  // monthly payment solving FV of an ordinary annuity
  const monthly = mr === 0 ? need / n : need * mr / (Math.pow(1 + mr, n) - 1);
  return `<div class="sumstrip s4">
    ${toolTile("Goal in today's money", rs(target), `${years} years away`, "")}
    ${toolTile("What it'll actually cost", rs(targetReal), `at ${(infl * 100).toFixed(1)}% inflation`, "dn")}
    ${toolTile("Your savings will grow to", rs(grownHave), `from ${rs(have)} today`, "up")}
    ${toolTile("Save per month", rs(monthly), `for ${n} months at ${(rate * 100).toFixed(1)}%`, "up")}
  </div>
  <div class="tnote">The tile most goal calculators hide is the second one: a goal priced in <b>today's</b> rupees costs materially more by the time you reach it. Plan against ${rs(targetReal)}, not ${rs(target)}. If the monthly figure looks impossible, the honest levers are a longer horizon or a smaller goal — not a higher assumed return.</div>`;
}
function toolMortgage() {
  const price = tnum("t-mprice"), down = tnum("t-mdown"), years = tnum("t-myears"), rate = tnum("t-mrate") / 100;
  const principal = Math.max(0, price - down);
  const mr = rate / 12, n = Math.round(years * 12);
  const pay = mr === 0 ? principal / n : principal * mr / (1 - Math.pow(1 + mr, -n));
  const total = pay * n, interest = total - principal;
  const a = tAnchors();
  return `<div class="sumstrip s4">
    ${toolTile("Monthly instalment", rs(pay), `${years} yrs at ${(rate * 100).toFixed(2)}%`, "")}
    ${toolTile("You borrow", rs(principal), `${rs(down)} down on ${rs(price)}`, "")}
    ${toolTile("Total interest", rs(interest), `over ${n} payments`, "dn")}
    ${toolTile("Total repaid", rs(total), interest > principal ? "more than double the loan" : "principal + interest", "dn")}
  </div>
  <div class="tnote warn">Over ${years} years you repay <b>${rs(total)}</b> on a <b>${rs(principal)}</b> loan — interest alone is <b>${rs(interest)}</b>, ${(interest / principal * 100).toFixed(0)}% of what you borrowed.
  Pakistani home finance is usually priced at <b>KIBOR + a bank spread</b> and re-prices as rates move, so a fixed illustration understates the risk of a rising-rate year.${a.policy != null ? ` The SBP policy rate is currently <b>${a.policy}%</b>${a.tbill != null ? ` and 6M T-bills yield <b>${a.tbill}%</b>` : ""} — home finance typically sits above these, not at them.` : ""} The desk does not hold a live KIBOR feed, so enter the rate your bank actually quotes.</div>`;
}
function toolZakat() {
  const val = tnum("t-zval"), cash = tnum("t-zcash"), owed = tnum("t-zowed");
  const net = Math.max(0, val + cash - owed);
  const g = _tools.gold;   // {pkrPerGram, usdOz, usdpkr, date}
  const nisabGold = g ? g.pkrPerGram * 87.48 : null;
  const above = nisabGold != null ? net >= nisabGold : null;
  return `<div class="sumstrip s3">
    ${toolTile("Zakatable total", rs(net), "shares + cash − debts due", "")}
    ${toolTile("Zakat at 2.5%", rs(net * 0.025), above === false ? "only if above nisab" : "payable if held a lunar year", "up")}
    ${toolTile("Gold nisab (87.48g)", nisabGold != null ? rs(nisabGold) : "—", g ? `gold $${g.usdOz}/oz · USD/PKR ${g.usdpkr}` : "gold price unavailable", "")}
  </div>
  ${nisabGold != null ? `<div class="tnote ${above ? "" : "warn"}">${above
    ? `Your ${rs(net)} is <b>above</b> the gold nisab of ${rs(nisabGold)}, so zakat would be due if the wealth has been held for a lunar year.`
    : `Your ${rs(net)} is <b>below</b> the gold nisab of ${rs(nisabGold)}. Note that the <b>silver</b> nisab (612.36g) is considerably lower and is what many scholars apply — the desk does not hold a silver price, so check the current silver rate before concluding zakat is not due.`}</div>` : ""}
  <div class="tnote">Nisab above is computed from the desk's live gold price${g ? ` ($${g.usdOz}/oz on ${esc(g.date)}) and USD/PKR (${g.usdpkr})` : ""}, at 87.48g of gold. Scholars differ on real questions here — whether shares held long-term are zakatable at full market value or only on the company's zakatable assets, and whether gold or silver nisab applies. <b>This is a calculator, not a fatwa</b> — confirm with your own scholar or zakat authority.</div>`;
}

/* Dividend reinvestment on REAL PSX history: actual announced payouts, actual prices.
   Deep history from the desk is split/bonus-adjusted but NOT dividend-adjusted (the fetcher stores
   Yahoo's raw quote series), so applying dividends on top does not double-count them. */
/* One reinvestment simulation over a window. Returns null if there isn't enough history. */
function divSim(hist, pays, amount, years, todayDate) {
  const startDate = new Date(new Date(todayDate).getTime() - years * 365.25 * 86400000).toISOString().slice(0, 10);
  const bars = hist.filter(b => b.date >= startDate && b.close > 0);
  if (bars.length < 30) return null;
  const priceOn = d => { for (let i = 0; i < bars.length; i++) if (bars[i].date >= d) return bars[i].close; return bars[bars.length - 1].close; };
  const startPx = bars[0].close, endPx = bars[bars.length - 1].close;
  const win = pays.filter(p => p.ex >= bars[0].date && p.ex <= todayDate);
  let shR = amount / startPx; const shC = amount / startPx;
  let cash = 0; const events = [];
  for (const p of win) {
    const px = priceOn(p.ex);
    const paidR = shR * p.rs, bought = px > 0 ? paidR / px : 0;
    shR += bought; cash += shC * p.rs;
    events.push({ d: p.ex, rsps: p.rs, px, paidR, bought, shR });
  }
  const valR = shR * endPx, valC = shC * endPx + cash, valP = shC * endPx;
  const yrs = (new Date(todayDate) - new Date(bars[0].date)) / (365.25 * 86400000);
  const cagr = v => yrs > 0 ? (Math.pow(v / amount, 1 / yrs) - 1) * 100 : 0;
  return { from: bars[0].date, startPx, endPx, shR, shC, cash, valR, valC, valP, events,
    n: win.length, yrs, cagrR: cagr(valR), cagrC: cagr(valC), cagrP: cagr(valP) };
}

async function toolDivRun() {
  const sym = (document.getElementById("t-dsym")?.value || "").trim().toUpperCase();
  const amount = tnum("t-damt"), years = +(document.getElementById("t-dyears")?.value || 10);
  _tools.dsym = sym; _tools.dyears = years;
  const out = document.getElementById("t-out");
  if (!sym) { out.innerHTML = `<div class="tnote warn">Enter a PSX ticker to run it on real payout history.</div>`; return; }
  out.innerHTML = `<div class="sub" style="padding:10px 0">Running ${esc(sym)} on real dividend history…</div>`;
  const [hist, deep, uni] = await Promise.all([
    j("history_deep/" + sym + ".json", 600000), j("dividends_deep.json"), j("universe.json")]);
  if (!hist || !hist.length) { out.innerHTML = `<div class="tnote warn">The desk holds no long price history for <b>${esc(sym)}</b>. Try a larger name.</div>`; return; }
  const today = hist[hist.length - 1].date;
  // 18 years of real payouts (Yahoo events), in the same split-adjusted space as these prices
  const pays = (deep?.tickers?.[sym] || []).slice().sort((a, b) => a.ex.localeCompare(b.ex));
  const name = uni?.symbols?.[sym]?.name || "";
  if (!pays.length) {
    out.innerHTML = `<div class="tnote warn"><b>${esc(sym)}</b>${name ? ` (${esc(name.slice(0, 34))})` : ""} has no cash dividends on record in the desk's ${esc(String(deep?.coverage_from || "").slice(0, 4))}–${esc(today.slice(0, 4))} history. Reinvestment has nothing to compound — try a dividend payer.</div>`;
    return;
  }
  const r = divSim(hist, pays, amount, years, today);
  if (!r) { out.innerHTML = `<div class="tnote warn">Not enough price history for <b>${esc(sym)}</b> over ${years} years — the desk's series starts ${esc(hist[0].date)}.</div>`; return; }
  // the comparison that makes the point: the same question at several horizons
  const horizons = [1, 3, 5, 10, 15].map(y => ({ y, r: divSim(hist, pays, amount, y, today) })).filter(x => x.r);
  const pct = v => ((v / amount - 1) * 100);
  const divShare = r.valR > 0 ? (r.valR - r.valP) / r.valR * 100 : 0;

  out.innerHTML = `
  <div class="sumstrip s4">
    ${toolTile("Reinvested", rs(r.valR), `${sgn(+pct(r.valR).toFixed(1))}% · ${r.cagrR.toFixed(1)}%/yr`, r.valR >= amount ? "up" : "dn")}
    ${toolTile("Dividends spent", rs(r.valC), `${sgn(+pct(r.valC).toFixed(1))}% · ${r.cagrC.toFixed(1)}%/yr`, r.valC >= amount ? "up" : "dn")}
    ${toolTile("Reinvesting added", rs(r.valR - r.valC), `${r.n} payouts compounded`, r.valR >= r.valC ? "up" : "dn")}
    ${toolTile("Price alone", rs(r.valP), `dividends ignored · ${r.cagrP.toFixed(1)}%/yr`, r.valP >= amount ? "up" : "dn")}
  </div>

  <div class="tnote"><b>${rs(amount)}</b> into <b>${esc(sym)}</b>${name ? ` (${esc(name.slice(0, 34))})` : ""} on <b>${esc(r.from)}</b> bought
  <b>${r.shC.toFixed(0)}</b> shares at Rs ${fmt(r.startPx)}. Over ${r.yrs.toFixed(1)} years it paid <b>${r.n}</b> cash dividend${r.n === 1 ? "" : "s"};
  reinvesting each one grew the holding to <b>${r.shR.toFixed(0)}</b> shares, against ${r.shC.toFixed(0)} if the cash had been spent.
  Price on ${esc(today)}: Rs ${fmt(r.endPx)}. <b>${divShare > 0 ? `Dividends account for ${divShare.toFixed(0)}% of the reinvested result` : "Dividends made no difference over this window"}</b> — which is the entire argument for reinvesting.
  Past payouts are history, <b>not a forecast</b>: companies cut dividends, and this is not a recommendation.</div>

  ${horizons.length > 1 ? `<div class="seg" style="margin-top:16px"><h2>Same question, different horizons</h2><div class="ln"></div></div>
  <div class="card" style="padding:0"><table><thead><tr><th>Held for</th><th class="r">Payouts</th><th class="r">Reinvested</th><th class="r">Dividends spent</th><th class="r">Price only</th><th class="r">Reinvesting added</th></tr></thead><tbody>${
    horizons.map(h => `<tr class="${h.y === years ? "exp" : ""}"><td><b>${h.y} year${h.y > 1 ? "s" : ""}</b> <span class="sub">from ${esc(h.r.from)}</span></td>
      <td class="r num">${h.r.n}</td>
      <td class="r num up">${rs(h.r.valR)} <span class="sub">${h.r.cagrR.toFixed(1)}%/yr</span></td>
      <td class="r num">${rs(h.r.valC)}</td><td class="r num">${rs(h.r.valP)}</td>
      <td class="r num ${h.r.valR >= h.r.valC ? "up" : "dn"}">${rs(h.r.valR - h.r.valC)}</td></tr>`).join("")}</tbody></table>
    <div class="sub" style="padding:9px 14px">Each row is the same ${rs(amount)}, held for a different length of time to today. The gap between "reinvested" and "price only" widens with time — that widening is compounding doing its work.</div></div>` : ""}

  <div class="seg" style="margin-top:16px"><h2>Every payout in the window</h2><div class="ln"></div><span class="pill">${r.n}</span></div>
  <div class="card" style="padding:0"><table><thead><tr><th>Ex-date</th><th class="r">Rs/share</th><th class="r">Price then</th><th class="r">Cash paid</th><th class="r">Shares bought</th><th class="r">Shares held</th></tr></thead><tbody>${
    r.events.slice(-18).reverse().map(e => `<tr><td class="num">${esc(e.d)}</td><td class="r num">${e.rsps}</td><td class="r num">${fmt(e.px)}</td>
      <td class="r num up">${rs(e.paidR)}</td><td class="r num">${e.bought.toFixed(1)}</td><td class="r num">${e.shR.toFixed(0)}</td></tr>`).join("")}</tbody></table>
    <div class="sub" style="padding:9px 14px">Payouts from Yahoo's dividend events (${esc(String(deep?.coverage_from || ""))} onward), split/bonus-adjusted to match the price series — so per-share amounts are comparable to the prices shown, and dividends are not double-counted. Reinvested at the ex-date close; real reinvestment happens on the payment date, in whole shares, after withholding tax. Announced and upcoming payouts with buy-by dates live on the <a href="/dividends" style="color:var(--accent)">Dividends</a> page.</div></div>`;
}

function toolPanel() {
  const t = _tools.tab, a = tAnchors();
  const cpi = a.cpi != null ? a.cpi : 11, rate = a.tbill != null ? a.tbill : 12;
  const F = (label, id, val, step) => `<label>${label}<input id="${id}" type="text" inputmode="decimal" enterkeyhint="done" class="ph-in" value="${val}"${step ? ` step="${step}"` : ""}></label>`;
  const run = `onclick="toolRun()"`;
  if (t === "compound") return `<div class="tgrid">
      ${F("Amount today (Rs)", "t-lump", 500000)}${F("Years", "t-years", 10)}
      ${F("Assumed return %/yr", "t-rate", 15, "0.1")}${F("Inflation %/yr", "t-infl", cpi, "0.1")}
      <button class="note-save" ${run}>Calculate</button></div>`;
  if (t === "sip") return `<div class="tgrid">
      ${F("Monthly saving (Rs)", "t-monthly", 15000)}${F("Starting amount (Rs)", "t-lump2", 100000)}
      ${F("Years", "t-years2", 10)}${F("Assumed return %/yr", "t-rate2", 15, "0.1")}${F("Inflation %/yr", "t-infl2", cpi, "0.1")}
      <button class="note-save" ${run}>Calculate</button></div>`;
  if (t === "inflation") return `<div class="tgrid">
      ${F("Amount (Rs)", "t-iamt", 1000000)}${F("Years", "t-iyears", 10)}${F("Inflation %/yr", "t-irate", cpi, "0.1")}
      <button class="note-save" ${run}>Calculate</button></div>`;
  if (t === "goal") return `<div class="tgrid">
      ${F("Goal in today's Rs", "t-gtarget", 5000000)}${F("Years away", "t-gyears", 8)}
      ${F("Already saved (Rs)", "t-ghave", 200000)}${F("Assumed return %/yr", "t-grate", 15, "0.1")}${F("Inflation %/yr", "t-ginfl", cpi, "0.1")}
      <button class="note-save" ${run}>Calculate</button></div>`;
  if (t === "mortgage") return `<div class="tgrid">
      ${F("Property price (Rs)", "t-mprice", 15000000)}${F("Down payment (Rs)", "t-mdown", 4500000)}
      ${F("Years", "t-myears", 20)}${F("Rate %/yr (your bank's quote)", "t-mrate", 18, "0.01")}
      <button class="note-save" ${run}>Calculate</button></div>`;
  if (t === "zakat") return `<div class="tgrid">
      ${F("Value of shares (Rs)", "t-zval", 500000)}${F("Cash & bank (Rs)", "t-zcash", 200000)}${F("Debts due now (Rs)", "t-zowed", 0)}
      <button class="note-save" ${run}>Calculate</button></div>`;
  if (t === "divreinvest") return `<div class="tgrid">
      <label>PSX ticker<input id="t-dsym" class="ph-in combo" type="search" enterkeyhint="search" aria-label="PSX ticker" placeholder="e.g. FFC" autocomplete="off" value="${esc(_tools.dsym || "FFC")}"></label>
      ${F("Amount invested (Rs)", "t-damt", 500000)}
      <label>Held for<select id="t-dyears" class="ph-in">${[1, 3, 5, 10, 15].map(y => `<option value="${y}"${(_tools.dyears || 10) === y ? " selected" : ""}>${y} year${y > 1 ? "s" : ""}</option>`).join("")}</select></label>
      <button class="note-save" onclick="toolDivRun()">Run on real history</button></div>`;
  return "";
}
function toolRun() {
  const out = document.getElementById("t-out"); if (!out) return;
  const f = { compound: toolCompound, sip: toolSip, inflation: toolInflation, goal: toolGoal, mortgage: toolMortgage, zakat: toolZakat }[_tools.tab];
  if (f) out.innerHTML = f();
}
function toolTab(k) { _tools.tab = k; pageTools(); }

async function pageTools() {
  await Promise.resolve();
  if (!_tools.macro) {
    const [m, mh] = await Promise.all([j("macro.json"), j("macro_history.json")]);
    _tools.macro = m || {};
    // zakat nisab needs a real gold price in rupees: gold is quoted USD/oz, so convert via USD/PKR
    try {
      const gs = mh?.factors?.gold?.series || {}, us = mh?.factors?.usdpkr?.series || {};
      const gd = Object.keys(gs).sort(), ud = Object.keys(us).sort();
      const usdOz = gs[gd[gd.length - 1]], usdpkr = us[ud[ud.length - 1]];
      if (usdOz && usdpkr) _tools.gold = { usdOz, usdpkr, date: gd[gd.length - 1], pkrPerGram: usdOz * usdpkr / 31.1034768 };
    } catch { /* nisab tile degrades to "—" rather than inventing a price */ }
  }
  const DESC = {
    compound: "What one amount becomes if left to grow — and what it will actually buy after inflation.",
    sip: "Saving a fixed amount every month. The case for regularity over timing.",
    inflation: "What idle rupees lose. The argument for investing, in one number.",
    divreinvest: "Real PSX payout history: what reinvesting dividends actually did, versus spending them.",
    goal: "House, wedding, education — what you must save monthly, priced in future rupees.",
    mortgage: "Instalment and true lifetime interest on Pakistani home finance.",
    zakat: "2.5% on shares and cash, against a nisab computed from today's real gold price.",
  };
  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Tools</h2><div class="ln"></div><span class="pill">rupees · PSX · real rates</span></div>
  <div class="disclaimer">Calculators run on <b>your own inputs</b>, with defaults anchored to Pakistan's real reported rates. Nothing here is a forecast, a promised return, or advice — assumed returns are <b>your assumption</b>, and no market pays a steady rate.</div>
  ${anchorChips()}
  <div class="ttabs">${TOOL_TABS.map(([k, l]) => `<button class="ttab ${_tools.tab === k ? "on" : ""}" onclick="toolTab('${k}')">${esc(l)}</button>`).join("")}</div>
  <div class="card tpanel">
    <div class="ark">${esc(TOOL_TABS.find(x => x[0] === _tools.tab)?.[1] || "")}</div>
    <p class="sub" style="margin:5px 0 4px">${esc(DESC[_tools.tab] || "")}</p>
    ${toolPanel()}
    <div id="t-out"></div>
  </div>`;
  // the ticker combo is wired by the delegated focusin handler — nothing to bind here
  if (_tools.tab === "divreinvest") toolDivRun(); else toolRun();
}

/* ==========================================================================================
   PRO WORKFLOWS — deterministic, computed from the desk's own scored data. No tokens, no
   marginal cost, and every claim traceable to a state file. Research framing throughout.
   ========================================================================================== */

/* ---- Opportunity Scanner: six daily top-lists, each with a one-line why. Board page. ---- */
function scannerLists(q, fvt, fnd, predT, fs) {
  const rows = Object.keys(q).map(s => {
    const v = q[s] || {}, fv = fvt[s] || {}, f = fnd[s] || {}, m = fs?.[s]?.metrics || {};
    return { s, ...v, gap: fv.mispricing_pct, verdict: fv.verdict, fair: fv.composite_fair,
      dy: parseFloat(f.div_yield) || 0, payout: parseFloat(f.payout_ratio), margin: m.net_margin,
      pe: m.pe, fpe: m.forward_pe, pred: predT[s]?.score };
  });
  const liq = r => (r.avg_daily_traded_value || 0) >= 10e6;
  return [
    // |gap| > 150% is treated as a model artifact (usually an EPS quirk feeding one model), not a
    // bargain — a "top opportunities" list led by a 300% number reads as broken because it is.
    { key: "undervalued", title: "Below model fair value", rows: rows.filter(r => r.verdict === "undervalued" && liq(r) && r.gap <= 150).sort((a, b) => b.gap - a.gap).slice(0, 5)
        .map(r => ({ s: r.s, m: sgn(r.gap) + "%", why: `Rs ${fmt(r.close)} vs blended model fair Rs ${fmt(r.fair)} — cheap on the model, which is not the same as a good business.` })) },
    { key: "momentum", title: "Momentum", rows: rows.filter(r => r.above_sma50 && liq(r)).sort((a, b) => b.ret_20d - a.ret_20d).slice(0, 5)
        .map(r => ({ s: r.s, m: sgn(r.ret_20d) + "%", why: `+${r.ret_20d}% over 20 sessions, holding above its 50-day average. Momentum cuts both ways.` })) },
    { key: "dividend", title: "Covered dividend yield", rows: rows.filter(r => r.dy > 0 && r.payout != null && r.payout < 90).sort((a, b) => b.dy - a.dy).slice(0, 5)
        .map(r => ({ s: r.s, m: r.dy + "%", why: `Yields ${r.dy}% with ${r.payout}% of earnings paid out — covered, on last reported numbers.` })) },
    { key: "quality", title: "Quality earners", rows: rows.filter(r => (r.margin || 0) >= 12 && r.fpe && r.pe && r.fpe < r.pe && liq(r)).sort((a, b) => b.margin - a.margin).slice(0, 5)
        .map(r => ({ s: r.s, m: r.margin + "%", why: `Net margin ${r.margin}%, and forward P/E ${r.fpe} below trailing ${r.pe} — the market expects earnings to grow.` })) },
    { key: "predictable", title: "High predictability", rows: rows.filter(r => r.pred != null && liq(r)).sort((a, b) => b.pred - a.pred).slice(0, 5)
        .map(r => ({ s: r.s, m: String(r.pred), why: `Predictability ${r.pred}/100 — its historical patterns resolved consistently. Past consistency, not a promise.` })) },
    { key: "oversold", title: "Washed-out (RSI)", rows: rows.filter(r => r.rsi14 != null && r.rsi14 <= 35 && liq(r)).sort((a, b) => a.rsi14 - b.rsi14).slice(0, 5)
        .map(r => ({ s: r.s, m: "RSI " + Math.round(r.rsi14), why: `RSI ${Math.round(r.rsi14)} after selling pressure — where bounces have historically started, and where knives keep falling. Not a signal.` })) },
  ].filter(c => c.rows.length);
}
function scannerHtml(cats) {
  if (!hasFeature("scanner")) return planWall("The daily opportunity scanner",
    "Six ranked lists, rebuilt every cycle from the desk's scored data — below fair value, momentum, covered yield, quality, predictability, washed-out RSI — each with the reason it qualified.");
  return `<div class="scan-grid">${cats.map(c => `<div class="card scan-card">
    <h2>${esc(c.title)}</h2>
    ${c.rows.map(r => `<div class="scan-row clickable" onclick="navigate('/ticker/${esc(r.s)}')">
      <b>${esc(r.s)}</b><span class="num scan-m">${esc(r.m)}</span><span class="sub">${esc(r.why)}</span></div>`).join("")}
  </div>`).join("")}</div>
  <p class="sub" style="margin-top:8px">Ranked from the desk's own data each cycle — screens, not recommendations. A list a stock qualifies for is a place to start reading, never a reason to buy. (Shariah-status screens await a verified data source — the desk won't fake it.)</p>`;
}

/* ---- Scenario Simulator: measured sector×macro betas, scaled to the user's what-if. ---- */
const SCEN_FACTORS = {
  oil: { label: "Oil (WTI)", unit: "$", presetTargets: [95, 70] },
  usdpkr: { label: "USD/PKR", unit: "Rs", presetTargets: [340, 260] },
  gold: { label: "Gold", unit: "$" },
  sp500: { label: "S&P 500", unit: "" },
  us10y: { label: "US 10-year yield", unit: "" },
  dollar: { label: "Dollar index", unit: "" },
  em_equity: { label: "EM equity flows", unit: "" },
};
let _scen = { factor: "oil", movePct: 10 };
async function pageScenarios() {
  await Promise.resolve();
  const [sm, mh] = await Promise.all([j("sector_macro.json"), j("macro_history.json")]);
  const spots = {};
  for (const f of Object.keys(SCEN_FACTORS)) {
    const ser = mh?.factors?.[f]?.series || {};
    const days = Object.keys(ser).sort();
    if (days.length) spots[f] = { v: ser[days[days.length - 1]], d: days[days.length - 1] };
  }
  const presets = [
    ["oil", spots.oil ? (95 / spots.oil.v - 1) * 100 : 10, "Oil to $95"],
    ["usdpkr", spots.usdpkr ? (340 / spots.usdpkr.v - 1) * 100 : 20, "Rupee to 340"],
    ["gold", 10, "Gold +10%"],
    ["sp500", -5, "Wall Street −5%"],
    ["us10y", -10, "US yields fall 10%"],
    ["dollar", 5, "Dollar +5%"],
  ];
  const run = () => {
    const { factor, movePct } = _scen;
    const hits = [], quiet = [];
    for (const [sec, rec] of Object.entries(sm?.by_sector || {})) {
      const d = (rec.drivers || []).find(x => x.factor === factor && x.demonstrated);
      if (d) hits.push({ sec, est: d.beta * movePct, corr: d.corr, r2: rec.joint_r2_pct });
      else quiet.push(sec);
    }
    hits.sort((a, b) => b.est - a.est);
    const win = hits.filter(h => h.est > 0), lose = hits.filter(h => h.est < 0).reverse();
    const spot = spots[factor];
    const fl = SCEN_FACTORS[factor];
    const tile = h => `<div class="sc-tile ${h.est > 0 ? "up" : "dn"} clickable" title="measured correlation ${h.corr} · sector joint R² ${h.r2}%">
      <b>${esc(h.sec)}</b><span class="num">${h.est > 0 ? "+" : ""}${h.est.toFixed(2)}%</span>
      <i>${Math.abs(h.corr) >= 0.15 ? "strong" : Math.abs(h.corr) >= 0.07 ? "clear" : "faint"} link</i></div>`;
    return `
    <div class="sc-verdict"><b>${esc(fl.label)} ${movePct > 0 ? "+" : ""}${movePct.toFixed(1)}%</b>
      ${spot ? `<span class="sub">from ${fl.unit}${fmt(spot.v)} (${esc(spot.d)}) ${fl.unit ? `→ ~${fl.unit}${fmt(spot.v * (1 + movePct / 100))}` : ""}</span>` : ""}</div>
    ${hits.length ? `<div class="sc-cols">
      <div><div class="ark" style="color:var(--up)">historically leaned up</div>${win.length ? win.map(tile).join("") : '<div class="sub" style="padding:8px 0">none measurably</div>'}</div>
      <div><div class="ark" style="color:var(--dn)">historically leaned down</div>${lose.length ? lose.map(tile).join("") : '<div class="sub" style="padding:8px 0">none measurably</div>'}</div>
    </div>` : `<div class="empty">No sector shows a demonstrated link to this factor.</div>`}
    ${quiet.length ? `<p class="sub" style="margin-top:10px"><b>${quiet.length} sectors show no measurable link</b> — over 19 years their days were made locally, not by this factor. That silence is a finding too.</p>` : ""}
    <div class="tnote">Each estimate = the sector's <b>measured daily beta</b> to ${esc(fl.label)} (2007–2026, correction-survived) × your move — the typical <i>co-movement</i>, not a forecast. Even the strongest links explain only a few percent of a sector's daily variance, and a real ${esc(fl.label)} shock arrives tangled with everything else. History, not prophecy — and never advice.</div>`;
  };
  const locked = !hasFeature("scenarios");
  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Scenarios</h2><div class="ln"></div><span class="pill">measured, not imagined</span></div>
  <p class="sub" style="margin-bottom:12px">"What if oil hits $95?" — answered from what 19 years of data actually show, not from a story. Pick a question or set your own move.</p>
  ${locked ? planWall("The scenario simulator",
    "Oil to $95, rupee to 340, Wall Street −5% — which PSX sectors historically leaned up or down, from measured sector betas, with the honest R² attached.") : `
  <div class="card">
    <div class="sc-presets">${presets.map(([f, m, l]) => `<button class="seg-opt ${_scen.factor === f && Math.abs(_scen.movePct - m) < 0.01 ? "on" : ""}" onclick="_scen={factor:'${f}',movePct:${m.toFixed(2)}};pageScenarios()">${esc(l)}</button>`).join("")}</div>
    <div class="sc-custom">
      <label>Factor<select id="sc-f" class="ph-in" onchange="_scen.factor=this.value;pageScenarios()">${Object.entries(SCEN_FACTORS).map(([k, v]) => `<option value="${k}"${_scen.factor === k ? " selected" : ""}>${esc(v.label)}</option>`).join("")}</select></label>
      <label>Move %<input id="sc-m" type="text" inputmode="decimal" enterkeyhint="done" class="ph-in" value="${_scen.movePct.toFixed(1)}" onchange="_scen.movePct=+this.value||0;pageScenarios()"></label>
    </div>
    <div id="sc-out">${run()}</div>
  </div>
  <p class="sub" style="margin-top:10px">Domestic SBP-rate scenarios aren't offered because the desk has only measured <b>global</b> factors against sectors — US yields are the closest measured cousin, and pretending otherwise would be a guess dressed as data.</p>`}`;
}

/* ---- Smart Screener: plain English in, transparent parsed filters out. ---- */
let _scr = { text: "dividend > 6% and below fair value", saved: null };
let _insiderSymbols = new Set();  // populated by pageScreener from insider_activity.json
function parseScreen(text, sectorNames) {
  const f = [], warn = [], t = " " + text.toLowerCase() + " ";
  const num = re => { const m = t.match(re); return m ? parseFloat(m[1]) : null; };
  const dy = num(/(?:dividend|yield)[^0-9<>]*(?:>|above|over|at least)?\s*(\d+(?:\.\d+)?)\s*%/);
  if (dy != null) f.push({ label: `yield ≥ ${dy}%`, fn: r => r.dy >= dy });
  else if (/dividend|yield/.test(t)) f.push({ label: "pays a dividend", fn: r => r.dy > 0 });
  const peLt = num(/p\/?e\s*(?:<|under|below|less than)\s*(\d+(?:\.\d+)?)/);
  if (peLt != null) f.push({ label: `P/E < ${peLt}`, fn: r => r.pe != null && r.pe > 0 && r.pe < peLt });
  if (/below graham|graham/.test(t)) f.push({ label: "below Graham value", fn: r => r.graham != null && r.price != null && r.graham > r.price });
  if (/undervalued|below fair/.test(t)) f.push({ label: "below model fair value", fn: r => r.verdict === "undervalued" });
  if (/overvalued|above fair/.test(t)) f.push({ label: "above model fair value", fn: r => r.verdict === "overvalued" });
  if (/earnings growth|growing|growth/.test(t)) f.push({ label: "earnings expected to grow (fwd P/E < trailing)", fn: r => r.fpe != null && r.pe != null && r.fpe < r.pe });
  if (/predictab/.test(t)) f.push({ label: "predictability ≥ 60", fn: r => (r.pred || 0) >= 60 });
  if (/momentum|rising|uptrend/.test(t)) f.push({ label: "20-day momentum > +5%, above 50-day", fn: r => (r.ret_20d || 0) > 5 && r.above_sma50 });
  if (/liquid/.test(t)) f.push({ label: "≥ Rs 25M traded/day", fn: r => (r.liq || 0) >= 25e6 });
  if (/defensive|low beta|calm/.test(t)) f.push({ label: "beta < 0.8", fn: r => r.beta != null && r.beta < 0.8 });
  if (/profitab|margin/.test(t)) f.push({ label: "net margin ≥ 10%", fn: r => (r.margin || 0) >= 10 });
  if (/covered/.test(t)) f.push({ label: "payout < 90%", fn: r => r.payout != null && r.payout < 90 });
  // sector match: any distinctive word of a sector name appearing in the query ("banks" →
  // "Commercial Banks"). Longest matched token wins so "oil marketing" beats plain "oil".
  let best = null;
  for (const sec of sectorNames) {
    for (const w of sec.toLowerCase().split(/[^a-z]+/)) {
      if (w.length >= 4 && t.includes(w) && (!best || w.length > best.w.length)) best = { sec, w };
    }
  }
  if (best) f.push({ label: `sector: ${best.sec}`, fn: r => r.sector === best.sec });
  if (/low debt|debt/.test(t)) warn.push("debt — balance-sheet debt isn't in the desk's feed yet, so it can't be filtered. Check the balance sheet directly.");
  if (/shariah|halal|islamic/.test(t)) warn.push("Shariah status — needs the verified KMI-30 constituent list, which the desk doesn't hold yet. It won't guess on a religious screen.");
  if (/insider/.test(t)) f.push({ label: "insider/substantial-shareholder filing in the last 30 days", fn: r => _insiderSymbols.has(r.s) });
  return { f, warn };
}
async function pageScreener() {
  await Promise.resolve();
  const locked = !hasFeature("screener");
  const [q, fv, fnd, pred, fs, sec, uni, insider] = await Promise.all([
    j("quant.json"), j("fairvalue.json"), j("fundamentals.json"), j("predictability.json"),
    j("fundamental_scores.json"), j("sectors.json"), j("universe.json"), j("insider_activity.json")]);
  // date-bounded to match the filter's own label and the 30d window used on the ticker page --
  // the whole file goes back months, so an unbounded key list would return "has ever filed".
  const insCutoff = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);
  _insiderSymbols = new Set(Object.entries(insider?.symbols || {})
    .filter(([, rows]) => (rows || []).some(r => r.date && r.date >= insCutoff)).map(([s]) => s));
  const sectorNames = [...new Set(Object.values(sec?.tickers || {}).map(x => x.sector).filter(Boolean))];
  const rows = Object.keys(q?.tickers || {}).map(s => {
    const v = q.tickers[s], t = fv?.tickers?.[s] || {}, f = fnd?.tickers?.[s] || {}, m = fs?.tickers?.[s]?.metrics || {};
    return { s, name: uni?.symbols?.[s]?.name || "", sector: sec?.tickers?.[s]?.sector || "",
      price: v.close, ret_20d: v.ret_20d, above_sma50: v.above_sma50, liq: v.avg_daily_traded_value,
      dy: parseFloat(f.div_yield) || 0, payout: parseFloat(f.payout_ratio), pe: m.pe, fpe: m.forward_pe,
      margin: m.net_margin, beta: m.beta, verdict: t.verdict, gap: t.mispricing_pct,
      graham: t.methods?.graham, pred: pred?.tickers?.[s]?.score };
  });
  const { f: filters, warn } = parseScreen(_scr.text, sectorNames);
  const out = filters.length ? rows.filter(r => filters.every(x => x.fn(r))) : [];
  const saved = (myProfile?.saved_screens || []);
  const SAMPLES = ["dividend > 8% and covered", "below graham value with earnings growth", "undervalued banks",
    "predictable with momentum", "defensive with dividend > 6%", "cement below fair value"];
  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Screener</h2><div class="ln"></div><span class="pill">plain English in</span></div>
  <p class="sub" style="margin-bottom:12px">No filter panels — say what you want. It shows how it read you, then screens the desk's <b>scored</b> fields: fair value, Graham value, predictability, covered yield. Nobody else screens these, because nobody else scores them.</p>
  ${locked ? planWall("The plain-English screener",
    `"Dividend above 8%, covered, below Graham value, with earnings growth" — one sentence, screened across all ${rows.length} names on the desk's scored fields.`) : `
  <div class="card">
    <div class="scr-row"><input id="scr-in" class="ph-in" type="search" inputmode="search" enterkeyhint="search" aria-label="Describe what you are screening for" style="flex:1" value="${esc(_scr.text)}" placeholder="e.g. dividend > 8% with earnings growth, below fair value"
      onkeydown="if(event.key==='Enter'){_scr.text=this.value;pageScreener()}">
      <button class="note-save" onclick="_scr.text=document.getElementById('scr-in').value;pageScreener()">Screen</button>
      ${me && filters.length ? `<button class="note-save" onclick="saveScreen()">Save</button>` : ""}</div>
    <div class="scr-chips">${filters.map(x => `<span class="scr-chip">${esc(x.label)}</span>`).join("")
      || '<span class="sub">Nothing parsed yet — try one of the examples below.</span>'}</div>
    ${warn.map(w => `<div class="tnote warn" style="margin-top:8px"><b>Can't screen on ${esc(w.split(" — ")[0])}</b> — ${esc(w.split(" — ")[1] || "")}</div>`).join("")}
    <div class="scr-samples">${SAMPLES.map(x => `<button class="scr-sample" onclick="_scr.text='${esc(x)}';pageScreener()">${esc(x)}</button>`).join("")}
    ${saved.map((x, i) => `<button class="scr-sample saved" onclick="_scr.text='${esc(x.text)}';pageScreener()" title="saved screen">★ ${esc(x.name)}</button>`).join("")}</div>
  </div>
  ${filters.length ? `<div class="seg"><h2>${out.length} match${out.length === 1 ? "" : "es"}</h2><div class="ln"></div>${out.length ? csvBtn("screen") : ""}</div>
  <div class="card" style="padding:0">${out.length ? `<table><thead><tr><th>Stock</th><th>Sector</th><th class="r">Price</th><th class="r">P/E</th><th class="r">Yield</th><th class="r">vs fair</th><th class="r">Predict.</th></tr></thead><tbody>${
      out.slice(0, 60).map(r => `<tr class="clickable" onclick="navigate('/ticker/${r.s}')"><td><b>${r.s}</b> <span class="sub">${esc((r.name || "").slice(0, 20))}</span></td>
        <td class="sub">${esc((r.sector || "").slice(0, 16))}</td><td class="r num">${fmt(r.price)}</td><td class="r num">${r.pe ?? "—"}</td>
        <td class="r num">${r.dy ? r.dy + "%" : "—"}</td><td class="r num ${r.gap > 0 ? "up" : r.gap < 0 ? "dn" : ""}">${r.gap != null ? sgn(r.gap) + "%" : "—"}</td>
        <td class="r num">${r.pred ?? "—"}</td></tr>`).join("")}</tbody></table>`
      : '<div class="empty">Nothing clears every condition — loosen one and try again. An empty screen is information too.</div>'}</div>
  <p class="sub" style="margin-top:10px">A screen is a reading list, not a portfolio. Every match still deserves the checklist on its own page.</p>` : ""}`}`;
}
async function saveScreen() {
  if (!me) { openAuth("signup"); return; }
  const name = prompt("Name this screen:", _scr.text.slice(0, 30)); if (!name) return;
  const list = [...(myProfile?.saved_screens || []), { name, text: _scr.text }].slice(-12);
  myProfile = { ...(myProfile || {}), saved_screens: list };
  await saveProfile({ saved_screens: list });
  pageScreener();
}

/* ---- Watchlist intelligence: "something important changed", computed per watched name. ---- */
function watchIntel(syms, { q, fvt, news, cal, claims, signals }) {
  const now = Date.now(), events = [];
  const recent = ts => ts && (now - new Date(ts).getTime()) < 72 * 3600000;
  const within = (d, days) => d && (new Date(d) - now) > 0 && (new Date(d) - now) < days * 86400000;
  for (const s of syms) {
    const v = q[s] || {}, fv = fvt[s] || {};
    if ((signals?.active || []).some(x => (x.ticker || x.sym) === s))
      events.push({ s, w: 5, tag: "signal", msg: "A proven strategy is firing on it right now — see the Board." });
    if (Math.abs(v.ret_1d || 0) >= 4)
      events.push({ s, w: 4, tag: v.ret_1d > 0 ? "move ↑" : "move ↓", msg: `Moved ${sgn(v.ret_1d)}% in a session — worth knowing why before reacting.` });
    // vol_surge alone is currently degenerate (true across the whole universe some cycles), so it
    // only counts when the price actually moved with it — volume without movement isn't an event.
    if (v.vol_surge && Math.abs(v.ret_1d || 0) >= 2)
      events.push({ s, w: 3, tag: "volume", msg: `Heavy volume behind a ${sgn(v.ret_1d)}% move — someone is repositioning with size.` });
    if (fv.mispricing_pct != null && Math.abs(fv.mispricing_pct) <= 3)
      events.push({ s, w: 2, tag: "at fair value", msg: `Sits within 3% of the model's fair value (Rs ${fmt(fv.composite_fair)}) — the discount/premium story just changed.` });
    for (const n of (news || []).slice(-60)) if (recent(n.ts) && (n.tickers || []).includes(s) && (n.impact || 0) >= 4)
      events.push({ s, w: 5, tag: "news " + n.impact, msg: (n.headline || "").slice(0, 90) });
    for (const e of (cal?.events || [])) {
      if (e.ticker !== s) continue;
      if (e.type === "results" && within(e.date, 7)) events.push({ s, w: 4, tag: "results", msg: `Reports ${e.date} — results gap risk inside a week.` });
      if ((e.type === "ex_dividend" || e.type === "book_closure") && within(e.buy_by || e.date, 7))
        events.push({ s, w: 3, tag: "ex-div", msg: `Buy-by date ${e.buy_by || e.date} to receive the announced payout.` });
    }
    for (const c of (claims?.claims || []).slice(-80)) if (c.source_type === "broker" && (c.tickers || [c.ticker]).includes(s) && recent(c.made || c.date))
      events.push({ s, w: 3, tag: "broker", msg: `${c.source || "A broker"} put a fresh call on it — now on the record and scored.` });
  }
  return events.sort((a, b) => b.w - a.w).slice(0, 12);
}

/* ==========================================================================================
   EVIDENCE ALIGNMENT ("conviction") — how many independent lenses agree, and which way.
   Deliberately NOT a buy/sell score and never rendered as one: it reports agreement among
   measurements the desk already publishes, and says plainly when the lenses disagree.
   ========================================================================================== */
function alignmentOf(sym, d) {
  const { q = {}, fv = {}, fs = {}, pred, claims, news, sm, sector } = d;
  const L = [];
  const push = (name, dir, note) => L.push({ name, dir, note });
  if (fv.verdict === "undervalued") push("Valuation", 1, `Below the blended model fair value (${sgn(fv.mispricing_pct)}%).`);
  else if (fv.verdict === "overvalued") push("Valuation", -1, `Above the blended model fair value (${sgn(fv.mispricing_pct)}%).`);
  else if (fv.verdict) push("Valuation", 0, "Priced close to the model's fair value.");
  if (q.above_sma50 != null) push("Trend", q.above_sma50 ? 1 : -1,
    q.above_sma50 ? "Trading above its 50-day average." : "Trading below its 50-day average.");
  if (q.ret_20d != null) push("Momentum", q.ret_20d > 3 ? 1 : q.ret_20d < -3 ? -1 : 0, `${sgn(q.ret_20d)}% over the last 20 sessions.`);
  const m = fs.metrics || {};
  if (m.net_margin != null || m.forward_pe != null) {
    const good = (m.net_margin || 0) >= 12 && (m.forward_pe != null && m.pe != null ? m.forward_pe < m.pe : true);
    const bad = (m.net_margin != null && m.net_margin < 3);
    push("Quality", good ? 1 : bad ? -1 : 0,
      m.net_margin != null ? `Net margin ${m.net_margin}%${m.forward_pe && m.pe ? `, forward P/E ${m.forward_pe} vs trailing ${m.pe}` : ""}.` : "Partial fundamentals only.");
  }
  if (m.div_yield) push("Income", m.payout_ratio != null && m.payout_ratio > 90 ? 0 : 1,
    `${m.div_yield}% yield${m.payout_ratio != null ? `, payout ${m.payout_ratio}%` : ""}.`);
  if (pred != null) push("Predictability", pred >= 60 ? 1 : pred <= 35 ? -1 : 0, `Historical patterns resolved ${pred}/100 consistently.`);
  const recent = (news || []).filter(n => (n.tickers || []).includes(sym)).slice(-3);
  const impact = recent.reduce((a, n) => Math.max(a, n.impact || 0), 0);
  if (recent.length) push("News", impact >= 4 ? -1 : 0, impact >= 4 ? `A high-impact item (${impact}/5) landed recently.` : `${recent.length} routine item${recent.length > 1 ? "s" : ""} on the wire.`);
  const bro = (claims?.claims || []).filter(c => c.source_type === "broker" && (c.tickers || [c.ticker]).includes(sym));
  if (bro.length) push("Brokers", 0, `${bro.length} public broker call${bro.length > 1 ? "s" : ""} on record — scored on the leaderboard, not trusted.`);
  const drv = (sm?.by_sector?.[sector]?.drivers || []).filter(x => x.demonstrated)[0];
  if (drv) push("Macro", 0, `${sector} measurably tracks ${FACTOR_PLAIN[drv.factor] || drv.factor} — the sector's own weather.`);
  const up = L.filter(x => x.dir > 0).length, dn = L.filter(x => x.dir < 0).length, neutral = L.length - up - dn;
  const net = up - dn;
  const label = L.length < 3 ? "too little evidence"
    : Math.abs(net) <= 1 ? "lenses disagree"
      : net >= 4 ? "strongly aligned, constructive" : net >= 2 ? "leaning constructive"
        : net <= -4 ? "strongly aligned, cautious" : "leaning cautious";
  return { lenses: L, up, dn, neutral, net, label };
}
function alignmentCard(a) {
  if (!a.lenses.length) return "";
  const tone = a.net >= 2 ? "up" : a.net <= -2 ? "dn" : "";
  return `<div class="seg"><h2>Evidence alignment</h2><div class="ln"></div><span class="pill ${tone}">${esc(a.label)}</span></div>
  <p class="sub" style="margin-bottom:12px">How many of the desk's independent lenses point the same way. <b>This is not a buy or sell rating</b> — it is a count of agreement, and disagreement is a legitimate and common answer.</p>
  <div class="card align-card">
    <div class="al-bar"><span class="al-up" style="flex:${a.up || 0.001}"></span><span class="al-nu" style="flex:${a.neutral || 0.001}"></span><span class="al-dn" style="flex:${a.dn || 0.001}"></span></div>
    <div class="al-legend"><span><b class="up">${a.up}</b> constructive</span><span><b>${a.neutral}</b> neutral</span><span><b class="dn">${a.dn}</b> cautious</span></div>
    <div class="al-rows">${a.lenses.map(l => `<div class="al-row"><span class="al-dot ${l.dir > 0 ? "up" : l.dir < 0 ? "dn" : ""}">${l.dir > 0 ? "+" : l.dir < 0 ? "−" : "="}</span>
      <b>${esc(l.name)}</b><span class="sub">${esc(l.note)}</span></div>`).join("")}</div>
  </div>`;
}

/* ==========================================================================================
   ASK THE DESK — free-form chat, answered by a live model (Groq, via /api/ask), grounded against
   the desk's own state files SERVER-SIDE. The model never gets open-ended state/ access — only a
   small JSON slice for whatever symbol or sector the question names — and its system prompt is
   instructed to say "unknown" rather than invent a figure (CLAUDE.md Rule 2) and to never use
   advice language (Rule 5). That is an instruction the model follows, not an architectural
   guarantee a template gave for free — see api/ask.js's header for the trade made to get real
   conversation instead of the old fixed-template engine, and why the UI below says "grounded in",
   not "cannot invent".
   ========================================================================================== */
let _ask = { history: [], busy: false, retry: null }; // history: [{role:"user"|"assistant", content, error?}]
const ASK_SAMPLES = ["Why is MEBL moving?", "Is FFC cheap?", "Tell me about LUCK", "FFC vs MCB",
  "Best dividend stocks", "What's happening in cement?", "What changed today?"];
const ASK_DEADLINE_MS = 35_000;
const ASK_HISTORY_LIMIT = 4;
const ASK_HISTORY_CONTENT_LIMIT = 500;
const ASK_ERROR_TEXT = Object.freeze({
  account_required: "Your session expired. Sign in again, then try the question once more.",
  owner_required: "This desk account cannot use Ask. Sign in with the owner account to continue.",
  service_unavailable: "The desk's assistant is not available right now. Try again shortly.",
  chat_not_configured: "The desk's assistant is not configured on this deployment yet.",
  provider_busy: "The desk's assistant is busy. Try again shortly.",
  provider_unavailable: "The desk could not reach its assistant. Try again shortly.",
  provider_error: "The desk's assistant had a provider error. Try again shortly.",
  model_unavailable: "The desk's assistant could not produce a validated answer. Try again shortly.",
  provider_invalid_response: "The desk's assistant could not produce a validated answer. Try again shortly.",
  model_truncated: "The assistant response was cut short. Try a narrower question.",
  data_unavailable: "The desk's data could not be read right now. Try again shortly.",
  desk_data_unavailable: "The desk's data could not be read right now. Try again shortly.",
  desk_data_too_large: "That data slice is too large to answer safely. Ask about a specific ticker or sector.",
  body_too_large: "That question is too large to send. Shorten it and try again.",
  bad_request: "That question could not be validated. Try rephrasing it.",
});

function askDeadlineError() { const e = new Error("ask_timeout"); e.code = "timeout"; return e; }
function askWithDeadline(work, deadline) {
  const remaining = deadline - Date.now();
  if (remaining <= 0) return Promise.reject(askDeadlineError());
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => { if (!settled) { settled = true; reject(askDeadlineError()); } }, remaining);
    Promise.resolve().then(work).then(v => { if (!settled) { settled = true; clearTimeout(timer); resolve(v); } }, e => {
      if (!settled) { settled = true; clearTimeout(timer); reject(e); }
    });
  });
}
function askHistoryPayload(history) {
  const clean = [];
  for (let i = 0; i < history.length - 1; i++) {
    const user = history[i], answer = history[i + 1];
    if (user?.role !== "user" || user.error || answer?.role !== "assistant" || answer.error) continue;
    const q = String(user.content || "").trim(), a = String(answer.content || "").trim();
    if (!q || !a) continue;
    clean.push({ role: "user", content: q.slice(0, ASK_HISTORY_CONTENT_LIMIT) });
    clean.push({ role: "assistant", content: a.slice(0, ASK_HISTORY_CONTENT_LIMIT) });
    i++;
  }
  return clean.slice(-ASK_HISTORY_LIMIT);
}
function askFriendlyError(body, status) {
  const key = body && typeof (body.error_code || body.error) === "string" ? (body.error_code || body.error) : "";
  if (ASK_ERROR_TEXT[key]) return ASK_ERROR_TEXT[key];
  if (status === 401 || status === 403) return ASK_ERROR_TEXT.account_required;
  if (status === 429) return ASK_ERROR_TEXT.provider_busy;
  if (status >= 500) return ASK_ERROR_TEXT.provider_error;
  return "The desk could not return an answer. Try again shortly.";
}
async function askRequest(question, history) {
  const deadline = Date.now() + ASK_DEADLINE_MS;
  let token = await askWithDeadline(() => authToken(), deadline);
  let refreshed = false;
  while (true) {
    const controller = new AbortController();
    let response;
    try {
      response = await askWithDeadline(() => fetch("/api/ask", {
        method: "POST", signal: controller.signal,
        headers: { "content-type": "application/json", Authorization: "Bearer " + (token || "") },
        body: JSON.stringify({ question, history }),
      }), deadline);
      const body = await askWithDeadline(() => response.json().catch(() => null), deadline);
      if (response.status === 401 && !refreshed) {
        refreshed = true;
        const fresh = await askWithDeadline(() => refreshSession(), deadline);
        if (fresh) { token = fresh; continue; }
      }
      if (!response.ok) return { ok: false, error: askFriendlyError(body, response.status) };
      if (!body || body.ok !== true || typeof body.answer !== "string" || !body.answer.trim())
        return { ok: false, error: "No answer came back. Try rephrasing or try again shortly." };
      return { ok: true, answer: body.answer };
    } catch (error) {
      if (error?.code === "timeout" || error?.name === "AbortError") throw askDeadlineError();
      throw error;
    } finally { controller.abort(); }
  }
}

/* The model writes plain-text markdown (a bare **Heading** line for a section, "- " for bullets,
   inline **bold** for emphasis) — that's its natural style, not something we asked it to stop doing.
   Showing that raw (esc() + pre-wrap) put literal asterisks on screen. This turns the same convention
   into real hierarchy (a heading element, a list) instead of asking the model to change how it writes. */
function inlineMd(s) { return esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>"); }
function mdLite(raw) {
  let html = "", inList = false;
  const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };
  for (const line of String(raw ?? "").split(/\r?\n/)) {
    const t = line.trim();
    if (!t) { closeList(); continue; }
    const heading = t.match(/^\*\*(.+?)\*\*:?$/);
    const bullet = t.match(/^[-*]\s+(.+)$/);
    if (heading) { closeList(); html += `<h4 class="ans-h">${esc(heading[1])}</h4>`; }
    else if (bullet) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${inlineMd(bullet[1])}</li>`; }
    else { closeList(); html += `<p>${inlineMd(t)}</p>`; }
  }
  closeList();
  return html || `<p>${esc(raw)}</p>`;
}

function askThreadHtml() {
  const latest = _ask.history.at(-1);
  const turns = _ask.history.map(m => m.role === "user"
    ? `<div class="ans-q">${esc(m.content)}</div>`
    : `<div class="ans-block"${m.error ? ' style="border-inline-start:3px solid var(--dn)"' : ""}>${m.error ? `<p style="white-space:pre-wrap">${esc(m.content)}</p>${m === latest && m.retry && _ask.retry && !_ask.busy ? '<button type="button" class="quiet-btn ask-retry" onclick="askRetry()">Try again</button>' : ""}` : mdLite(m.content)}</div>`
  ).join("");
  const busy = _ask.busy ? `<div class="ans-block"><p class="sub">Reading the desk's data and thinking…</p></div>` : "";
  const foot = _ask.history.length ? `<div class="ans-foot">Answered by a model grounded in the desk's own data — it's instructed to say "unknown" rather than invent a figure, but it is a live model, not a fixed template. Verify anything important on the ticker page. Research and education, never advice.</div>` : "";
  return turns + busy + foot;
}
function renderAsk() {
  const out = $("ask-out");
  if (out) {
    out.innerHTML = askThreadHtml();
    out.scrollTop = out.scrollHeight;
  }
  const busy = !!_ask.busy;
  const input = $("ask-in");
  // Keep the input editable while a request is in flight so a draft for the next
  // question survives the repaint; only actions that would submit are disabled.
  if (input) input.setAttribute?.("aria-busy", busy ? "true" : "false");
  document.querySelectorAll("[data-ask-send], [data-ask-sample]").forEach(el => { el.disabled = busy; });
  window.renderRailAsk?.();
}

async function askSend(qtext, opts = {}) {
  const inputEl = $("ask-in");
  const text = (qtext ?? inputEl?.value ?? "").trim().slice(0, 500);
  if (!text || _ask.busy) return;
  _ask.history.forEach(m => { if (m.retry) m.retry = false; });
  _ask.retry = null;
  // Only clear the page's own box when the question CAME from it. A rail send
  // or a sample chip passes qtext, and wiping #ask-in then erased a draft the
  // user was writing on the Ask page.
  if (qtext == null && inputEl) inputEl.value = "";

  if (LOCAL) { // /api/ask is a Vercel Edge Function — it only exists once deployed
    _ask.history.push({ role: "user", content: text },
      { role: "assistant", content: "Ask the desk needs the deployed site — this endpoint doesn't run under the local static server. Try it on the published desk.", error: true });
    renderAsk();
    return;
  }

  const priorHistory = opts.history || askHistoryPayload(_ask.history);
  _ask.history.push({ role: "user", content: text });
  _ask.busy = true;
  renderAsk();
  try {
    const body = await askRequest(text, priorHistory);
    if (body.ok) { _ask.retry = null; _ask.history.push({ role: "assistant", content: body.answer }); }
    else {
      _ask.retry = { question: text, history: priorHistory };
      _ask.history.push({ role: "assistant", content: body.error, error: true, retry: true });
    }
  } catch (error) {
    const message = error?.code === "timeout"
      ? "The desk took too long to answer. Try again shortly."
      : "The desk could not be reached. Check your connection and try again.";
    _ask.retry = { question: text, history: priorHistory };
    _ask.history.push({ role: "assistant", content: message, error: true, retry: true });
  } finally {
    _ask.busy = false;
    _ask.history = _ask.history.slice(-12);
    renderAsk();
  }
}
async function askRetry() {
  if (_ask.busy || !_ask.retry) return;
  const retry = _ask.retry;
  if (_ask.history.at(-1)?.error) _ask.history.pop();
  if (_ask.history.at(-1)?.role === "user") _ask.history.pop();
  _ask.retry = null;
  await askSend(retry.question, { history: retry.history });
}

async function pageAsk() {
  await Promise.resolve();
  const locked = !hasFeature("ask");
  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Ask the desk</h2><div class="ln"></div><span class="pill">grounded in the desk's data</span></div>
  <p class="sub" style="margin-bottom:12px">Plain English in, an answer grounded in the desk's own computed files out. It's instructed to say "unknown" rather than guess — verify anything important on the ticker page.</p>
  ${locked ? planWall("Ask the desk",
    "\"Why is MEBL moving?\" · \"Is FFC cheap?\" · \"What's happening in cement?\" — answered from the desk's own scored data, with sector context, the wire, and what the models say.") : `
  <div class="card">
    <div id="ask-out" style="max-height:60vh;overflow-y:auto"></div>
    <div class="scr-row" style="${_ask.history.length ? "margin-top:12px" : ""}"><input id="ask-in" class="ph-in" aria-label="Ask the desk a question" style="flex:1" placeholder="Why is MEBL moving?"
      onkeydown="if(event.key==='Enter')askSend()">
      <button class="note-save" data-ask-send onclick="askSend()">Ask</button></div>
    ${!_ask.history.length ? `<div class="scr-samples">${ASK_SAMPLES.map(x => `<button type="button" class="scr-sample" data-ask-sample="${esc(x)}">${esc(x)}</button>`).join("")}</div>` : ""}
  </div>`}`;
  $("view").querySelectorAll("[data-ask-sample]").forEach(btn => btn.addEventListener("click", () => askSend(btn.getAttribute("data-ask-sample"))));
  renderAsk();
}

/* ==========================================================================================
   SECTOR DEBATES — the Desk Room, one level up. Reads sessions the weekly agent run writes to
   state/sector_debates/. Purely a renderer: no agent runs from the browser.
   ========================================================================================== */
let _sectorPick = null, _secListOpen = false, _secSess = null, _secName = "";

/* Has the reader PLAYED this sector's debate in this tab? Session-scoped on purpose: the dot is a
   "you haven't seen this yet" marker, not a permanent trophy — a fresh visit should feel fresh. */
function secRan(sec) { try { return !!sessionStorage.getItem("secran:" + sec); } catch (e) { return false; } }

/* The crisp default. A session written by the current agents carries an explicit `tldr`; older ones
   don't, so the first two sentences of the long case stand in. Truncating mid-sentence would read as
   broken prose, and the full text is always one button away, so sentence boundaries are the cut. */
function secCrisp(o, key, n = 2) {
  const short = o && tp(o, "tldr");
  if (short) return short;
  const long = String((o && tp(o, key)) || "");
  const m = long.match(/[^.!?]+[.!?]+(?:\s|$)/g);
  return m ? m.slice(0, n).join(" ").trim() : long;
}

async function pageSectors() {
  await Promise.resolve();
  const [dos, idx, rot] = await Promise.all([
    j("sector_dossiers.json"), j("sector_debates/_index.json"), j("sector_debates/_rotation.json")]);
  const secs = Object.entries(dos?.sectors || {}).sort((a, b) => b[1].n_members - a[1].n_members);
  const sessions = idx?.sessions || {};
  const queue = rot?.queue || [];
  const cur = _sectorPick || secs[0]?.[0];
  const d = dos?.sectors?.[cur];
  const sess = sessions[cur];
  _secSess = sess || null; _secName = cur || "";
  const nRun = secs.filter(([s]) => sessions[s]).length;
  const pctl = (n, t) => t ? Math.round(n / t * 100) : 0;
  const drv = (d?.macro_drivers || []);

  // ---- left rail: every sector, stacked, each carrying its own run-state dot
  const dotOf = s => sessions[s] ? (secRan(s) ? "done" : "live") : "soon";
  const listItem = ([s, v]) => `<button class="sec-item ${cur === s ? "on" : ""}" onclick="_sectorPick='${esc(s)}';_secListOpen=false;pageSectors()">
    <span class="sec-dot ${dotOf(s)}"></span><span class="sec-nm">${esc(s)}</span><span class="sec-n">${v.n_members}</span></button>`;
  const rail = `<aside class="sec-list">
    <div class="sec-list-head"><span class="ark">sectors</span><span class="sub">${nRun} of ${secs.length} debated</span></div>
    ${secs.map(listItem).join("")}
    <div class="sec-legend"><span><i class="sec-dot live"></i>ready to run</span><span><i class="sec-dot done"></i>you've run it</span><span><i class="sec-dot soon"></i>in the queue</span></div>
  </aside>`;
  // mobile: the rail is a sheet behind one tap, so the debate — not the index — is what opens first
  const picker = `<button class="sec-picker" onclick="_secListOpen=!_secListOpen;pageSectors()">
    <span class="sec-dot ${dotOf(cur)}"></span><b>${esc(cur || "—")}</b>
    <span class="sec-pick-go">${_secListOpen ? "Close" : "Change sector"} ›</span></button>`;

  // ---- the tile group: house / for / against, crisp by default, full prose one tap away
  const pillars = side => (side?.pillars || []).slice(0, 2).map(p =>
    `<div class="sec-pt"><b>${esc(tp(p, "claim"))}</b><span>${esc(p.evidence)}</span></div>`).join("");
  const tile = (kind, label, badge, body, which) => `<article class="card sec-tile ${kind}">
    <div class="sec-tile-top"><span class="ark">${label}</span>${badge}</div>${body}
    <button class="sec-more" onclick="secTranscript('${which}')">Full transcript ›</button></article>`;
  const stanceCls = sess?.house_view?.stance === "constructive" ? "ok" : sess?.house_view?.stance === "cautious" ? "bad" : "";
  const tiles = sess?.house_view ? `<div class="sec-tiles">
    ${tile("t-house", "the house view", `<span class="pill ${stanceCls}">${esc(sess.house_view.stance)} · ${esc(sess.house_view.conviction)}</span>`,
    `<p class="sec-say">${esc(secCrisp(sess.house_view, "summary"))}</p>`, "house")}
    ${tile("t-for", "the case for", "", `<p class="sec-say">${esc(secCrisp(sess.bull, "case"))}</p>${pillars(sess.bull)}`, "for")}
    ${tile("t-against", "the case against", "", `<p class="sec-say">${esc(secCrisp(sess.bear, "case"))}</p>${pillars(sess.bear)}`, "against")}
  </div>` : "";

  // ---- run bar / empty state. Nothing runs from the browser: this replays a debate already written.
  const qpos = queue.indexOf(cur);
  const runBar = sess ? `<button class="run-desk ${secRan(cur) ? "ran" : ""}" onclick="playSectorDebate('${esc(cur)}')">
    <span class="run-ico">▶</span>
    <span class="run-txt"><b>The desk's debate on ${esc(cur)}</b><i>A sector bull and a sector bear argue the same evidence pack — breadth, valuation spread, income, the measured global factors — then the chair weighs it. Watch it play out.</i></span>
    <span class="run-meta">${sess.as_of ? `<span class="run-last">Debated · ${esc(String(sess.as_of).slice(0, 10))}</span>` : ""}<span class="run-go">${secRan(cur) ? "Replay ›" : "Run ›"}</span></span>
  </button>` : `<div class="card sec-empty">
    <div class="sec-empty-dot"><span class="sec-dot soon"></span></div>
    <b>${esc(cur)} hasn't been to the debate desk yet.</b>
    <p class="sub">One sector is debated each week on a fixed rotation.${qpos >= 0 ? ` <b>${esc(cur)}</b> is <b>#${qpos + 1}</b> in the queue — ${qpos === 0 ? "it's next up" : `${qpos} ${qpos === 1 ? "sector" : "sectors"} ahead of it`}.` : ""} The evidence pack below is already compiled; it is exactly what the two sides will argue from.</p>
    <div class="sec-empty-go">${secs.filter(([s]) => sessions[s] && s !== cur).slice(0, 2).map(([s]) =>
      `<button class="sec-more" onclick="_sectorPick='${esc(s)}';pageSectors()">Read ${esc(s)} ›</button>`).join("")}</div>
  </div>`;

  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Sectors</h2><div class="ln"></div><span class="pill">${nRun} of ${secs.length} debated</span></div>
  <p class="sub" style="margin-bottom:12px">The evidence pack behind every PSX sector — breadth, valuation spread, income quality, and the global factors that <b>measurably</b> move it. One sector goes to the debate desk each week; each debate lands as three short reads, with the full transcript behind every one.</p>
  <div class="sec-wrap ${_secListOpen ? "open" : ""}">
    ${picker}
    ${rail}
    <div class="sec-main">
    ${!d ? `<div class="card"><div class="empty">Sector dossiers build on the next cycle.</div></div>` : `
    ${runBar}
    ${tiles}
    <div class="card tpanel">
      <div class="sumstrip s4">
        <div class="sumtile"><span class="sk">Median 20-day</span><b class="${(d.returns.median_20d_pct || 0) >= 0 ? "up" : "dn"}">${sgn(d.returns.median_20d_pct)}%</b><i>${d.n_members} names</i></div>
        <div class="sumtile"><span class="sk">Breadth</span><b>${d.breadth.above_sma50}/${d.n_members}</b><i>above their 50-day (${pctl(d.breadth.above_sma50, d.n_members)}%)</i></div>
        <div class="sumtile"><span class="sk">Median P/E</span><b>${d.valuation.median_pe ?? "—"}</b><i>${d.valuation.n_undervalued} below fair · ${d.valuation.n_overvalued} above</i></div>
        <div class="sumtile"><span class="sk">Median yield</span><b>${d.income.median_yield_pct ?? "—"}%</b><i>${d.income.n_payers}/${d.n_members} pay · payout ${d.income.median_payout_pct ?? "—"}%</i></div>
      </div>
      <div class="tnote">${drv.length
      ? `<b>What measurably moves ${esc(cur)}:</b> ${drv.map(x => `${esc(FACTOR_PLAIN[x.factor] || x.factor)} (${x.corr > 0 ? "rises with" : "falls when it rises"}, β ${x.beta})`).join(", ")} — correction-survived over 19 years. But the whole global tape explains only <b>${d.macro_joint_r2_pct ?? "—"}%</b> of this sector's daily moves, so treat every macro story as a small part of the picture.`
      : `<b>No global factor has a demonstrated effect on ${esc(cur)}.</b> Over 19 years its days have been made locally, not on the world tape — that silence is a measured finding, not missing data.`}</div>
    </div>

    <div class="seg"><h2>Members</h2><div class="ln"></div><span class="pill">${d.n_members}</span></div>
    <div class="card" style="padding:0"><table><thead><tr><th>Stock</th><th class="r">Price</th><th class="r">20d</th><th class="r">P/E</th><th class="r">Yield</th><th class="r">vs fair</th></tr></thead><tbody>${
      d.members.map(m => `<tr class="clickable" onclick="navigate('/ticker/${esc(m.sym)}')"><td><b>${esc(m.sym)}</b> <span class="sub">${esc((m.name || "").slice(0, 20))}</span></td>
        <td class="r num">${fmt(m.close)}</td><td class="r num ${(m.ret_20d || 0) >= 0 ? "up" : "dn"}">${sgn(m.ret_20d)}%</td>
        <td class="r num">${m.pe ?? "—"}</td><td class="r num">${m.div_yield_pct ? m.div_yield_pct + "%" : "—"}</td>
        <td class="r num ${(m.fair_gap_pct || 0) > 0 ? "up" : (m.fair_gap_pct || 0) < 0 ? "dn" : ""}">${m.fair_gap_pct != null ? sgn(m.fair_gap_pct) + "%" : "—"}</td></tr>`).join("")}</tbody></table></div>`}
    </div>
  </div>`;
}

/* ---------- The full transcript. The tiles carry the crisp read; this is the unshortened debate —
   every pillar, the rebuttal, the dissent, and what the desk says would settle the argument. ---------- */
function secTranscript(which) {
  const s = _secSess;
  if (!s) return;
  const P = t => t ? `<p>${esc(t)}</p>` : "";
  const UL = arr => (arr || []).length ? `<ul>${arr.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
  const pil = side => (side?.pillars || []).map(p =>
    `<div class="sc-pt"><b>${esc(tp(p, "claim"))}</b><span>${esc(p.evidence)}</span></div>`).join("");
  let kicker = "", html = "";
  if (which === "house") {
    kicker = `House view · ${_secName}`;
    html = `<h3>The desk's house view</h3>
      <div class="sc-lead">${esc(s.house_view?.stance || "—")} · ${esc(s.house_view?.conviction || "—")} conviction</div>
      ${P(tp(s.house_view, "summary"))}
      ${(s.house_view?.key_evidence || []).length ? `<h4>What drove it</h4>${UL(tpArr(s.house_view, "key_evidence"))}` : ""}
      <h4>The strongest argument against this view</h4>${P(tp(s.house_view, "dissent"))}
      ${(s.what_would_settle_it || []).length ? `<h4>What would settle it</h4>${UL(s.what_would_settle_it)}` : ""}
      ${(s.dossier_gaps || []).length ? `<h4>What the evidence pack still can't answer</h4>${UL(s.dossier_gaps)}` : ""}`;
  } else if (which === "for") {
    kicker = `The case for · ${_secName}`;
    html = `<h3>The case for ${esc(_secName)}</h3>${P(tp(s.bull, "case"))}
      <h4>Pillars</h4>${pil(s.bull)}
      ${s.bull?.weakest_pillar ? `<h4>Its own weakest pillar</h4>${P(s.bull.weakest_pillar)}` : ""}
      ${s.bull_rebuttal ? `<h4>Rebuttal to the bear</h4>${P(s.bull_rebuttal)}` : ""}`;
  } else {
    kicker = `The case against · ${_secName}`;
    html = `<h3>The case against ${esc(_secName)}</h3>${P(tp(s.bear, "case"))}
      <h4>Pillars</h4>${pil(s.bear)}
      ${s.bear?.attacks_bull ? `<h4>Where it attacks the bull</h4>${P(s.bear.attacks_bull)}` : ""}
      ${s.bear?.weakest_pillar ? `<h4>Its own weakest pillar</h4>${P(s.bear.weakest_pillar)}` : ""}`;
  }
  secModal(kicker, `<div class="sec-script">${html}
    <p class="sub sc-foot">Debated ${esc(String(s.as_of || "").slice(0, 10))}. General commentary on a sector, not a call on any security.</p></div>`);
}

/* A plain dismissible overlay reusing the run modal's chrome — no loader, no steps, just the text. */
function secModal(kicker, html) {
  const ov = document.createElement("div");
  ov.className = "replay-overlay";
  ov.innerHTML = `<div class="replay-box"><div class="replay-head"><span class="replay-kicker">${esc(kicker)}</span>
    <button class="replay-x" aria-label="close" style="margin-left:auto">✕</button></div>
    <div class="replay-body">${html}</div></div>`;
  document.body.appendChild(ov);
  const key = e => { if (e.key === "Escape") close(); };
  function close() { closeAnimated(ov, ".replay-box"); document.removeEventListener("keydown", key); popOverlay(close); }
  ov.addEventListener("click", e => { if (e.target === ov || e.target.classList.contains("replay-x")) close(); });
  document.addEventListener("keydown", key);
  pushOverlay(close, ov);
  ov._close = () => { document.removeEventListener("keydown", key); popOverlay(close); ov.remove(); };  // route() teardown: node + listener, no exit animation
}

/* ---------- Sector debate run: same shape as the ticker Desk Room replay, one level up. The steps
   stream the REAL compiled dossier numbers the two sides argued from, then it lands on the three
   reads. Nothing is computed here — the weekly agent run already wrote the session. ---------- */
async function playSectorDebate(sec) {
  const [dos, idx] = await Promise.all([j("sector_dossiers.json"), j("sector_debates/_index.json")]);
  const d = dos?.sectors?.[sec] || {}, s = (idx?.sessions || {})[sec];
  if (!s) return;
  const drv = d.macro_drivers || [];
  const steps = [
    `Compiling the evidence pack — <b>${esc(sec)}</b> · ${d.n_members ?? "—"} members`,
    `Breadth · <b>${d.breadth?.above_sma50 ?? "—"}/${d.n_members ?? "—"}</b> above their 50-day`,
    `Returns · median 20-day <b>${sgn(d.returns?.median_20d_pct)}%</b> across the sector`,
    `Valuation · median P/E <b>${d.valuation?.median_pe ?? "—"}</b> · ${d.valuation?.n_undervalued ?? 0} below fair, ${d.valuation?.n_overvalued ?? 0} above`,
    `Income · median yield <b>${d.income?.median_yield_pct ?? "—"}%</b> · ${d.income?.n_payers ?? 0}/${d.n_members ?? "—"} pay`,
    drv.length
      ? `Global factors · ${drv.map(x => esc(FACTOR_PLAIN[x.factor] || x.factor)).join(", ")} — the whole tape explains <b>${d.macro_joint_r2_pct ?? "—"}%</b> of daily moves`
      : `Global factors · <b>none demonstrated</b> over 19 years — this sector's days are made locally`,
    `Sector bull and sector bear — same pack, opposite readings`,
    `Each side attacks the other's weakest pillar`,
    `The chair weighs it — stance, conviction, and the dissent that survives`,
  ];
  const li = arr => (arr || []).slice(0, 3).map(p => `<li><b>${esc(tp(p, "claim"))}</b> — ${esc(p.evidence)}</li>`).join("");
  runRevealModal({
    kicker: `Sector debate · ${esc(sec)}`, flagKey: "secran:" + sec,
    title: `Running the debate desk on ${esc(sec)}`,
    sub: `Working ${esc(sec)} the way the desk does — compiling breadth, valuation, income and the global factors that measurably move it, then letting a sector bull and a sector bear argue the same pack before the chair weighs it.`,
    steps,
    renderReveal: bodyEl => {
      bodyEl.innerHTML = `<div class="rp-reveal">
        <div class="rp-reveal-head"><b>${esc(sec)}</b><span>the whole debate, at a glance — evidence pack compiled ${esc(String(s.as_of || "").slice(0, 10))}</span></div>
        <div class="rp-desk">
          <div class="rp-panel accent-up"><div class="rp-panel-head"><span class="rp-av sm">FOR</span><div><b>The case for</b><span class="rp-role">sector bull</span></div></div>
            <p class="rp-panel-read">${esc(secCrisp(s.bull, "case"))}</p><ul class="rp-ul">${li(s.bull?.pillars)}</ul></div>
          <div class="rp-panel accent-dn"><div class="rp-panel-head"><span class="rp-av sm">AGST</span><div><b>The case against</b><span class="rp-role">sector bear</span></div></div>
            <p class="rp-panel-read">${esc(secCrisp(s.bear, "case"))}</p><ul class="rp-ul">${li(s.bear?.pillars)}</ul></div>
        </div>
        <div class="rp-panel rp-house"><div class="rp-panel-head"><span class="rp-av sm">HV</span><div><b>The house view</b><span class="rp-role">${esc(s.house_view?.stance || "—")} · ${esc(s.house_view?.conviction || "—")} conviction</span></div></div>
          <p class="rp-panel-read">${esc(secCrisp(s.house_view, "summary"))}</p></div>
        <div class="rp-reveal-foot"><span>Three reads, one evidence pack. General commentary on a sector — no call, no target, no named security.</span>
          <span class="rp-foot-btns"><button class="rp-btn2" data-a="replay">↻ Replay</button></span></div>
      </div>`;
    },
    onClose: () => { if (routeHash().startsWith("#/sectors")) pageSectors(); },
  });
}

/* ==========================================================================================
   STRATEGY MARKETPLACE — users publish CONFIGURED VARIANTS of the desk's own rule DSL. Nothing
   user-written is ever executed: a published strategy is a list of {lhs, op, rhs} conditions drawn
   from a fixed indicator vocabulary, evaluated by the same engine that runs the desk's own 70.
   Status and backtest results are desk-owned (DB triggers block client writes to both).
   ========================================================================================== */
const MKT_FIELDS = ["close", "open", "high", "low", "volume", "prev_close",
  "sma10", "sma20", "sma50", "sma100", "sma200", "ema9", "ema20", "ema50",
  "rsi2", "rsi7", "rsi14", "macd", "macd_signal", "macd_hist",
  "bb_upper", "bb_mid", "bb_lower", "bb_pctb", "bb_width_rank",
  "stoch_k", "stoch_d", "atr14", "atr_pct", "adx14", "plus_di", "minus_di",
  "willr14", "cci20", "donch_hi20", "donch_lo20", "donch_hi55", "donch_lo55",
  "hi252", "lo252", "roc10", "roc20", "roc60", "vol_surge", "vol_rank", "obv", "obv_ema20"];
const MKT_OPS = [["gt", "is above"], ["lt", "is below"], ["gte", "is at or above"], ["lte", "is at or below"],
  ["cross_above", "crosses above"], ["cross_below", "crosses below"]];
let _mkt = { tab: "browse", rules: [{ lhs: "close", op: "cross_above", rhs: "sma50" }], list: null, mine: null };

function mktRuleRow(r, i) {
  const opt = (v, sel) => `<option value="${esc(v)}"${v === sel ? " selected" : ""}>${esc(v)}</option>`;
  return `<div class="mkt-rule">
    <select onchange="_mkt.rules[${i}].lhs=this.value">${MKT_FIELDS.map(f => opt(f, r.lhs)).join("")}</select>
    <select onchange="_mkt.rules[${i}].op=this.value">${MKT_OPS.map(([v, l]) => `<option value="${v}"${v === r.op ? " selected" : ""}>${esc(l)}</option>`).join("")}</select>
    <input value="${esc(String(r.rhs))}" inputmode="text" enterkeyhint="done" onchange="_mkt.rules[${i}].rhs=isNaN(parseFloat(this.value))?this.value:parseFloat(this.value)" placeholder="field or number">
    ${_mkt.rules.length > 1 ? `<button class="mkt-x" aria-label="Remove condition" title="Remove condition" onclick="_mkt.rules.splice(${i},1);pageMarket()">✕</button>` : "<span></span>"}
  </div>`;
}
function mktValid() {
  return _mkt.rules.every(r => MKT_FIELDS.includes(r.lhs) && MKT_OPS.some(([v]) => v === r.op)
    && (typeof r.rhs === "number" || MKT_FIELDS.includes(r.rhs)));
}
async function mktPublish() {
  if (!me) { openAuth("signup"); return; }
  const name = (document.getElementById("mkt-name")?.value || "").trim();
  const desc = (document.getElementById("mkt-desc")?.value || "").trim();
  const tgt = +(document.getElementById("mkt-target")?.value || 0);
  const stp = +(document.getElementById("mkt-stop")?.value || 0);
  const hold = +(document.getElementById("mkt-hold")?.value || 0);
  const msg = document.getElementById("mkt-msg");
  const say = t => { if (msg) msg.textContent = t; };
  if (name.length < 3) return say("Give it a name (3+ characters).");
  if (!mktValid()) return say("Every rule needs a valid field, operator, and a number or field on the right.");
  if (!(tgt > 0 && stp > 0 && hold > 0)) return say("Target, stop and max hold must all be positive.");
  if (tgt <= stp) return say("A target below or equal to the stop loses money by construction — the desk won't publish it.");
  say("Publishing…");
  const { error } = await sb.from("published_strategies").insert({
    author_id: me.id, author_name: (me.email || "").split("@")[0],
    name, description: desc, category: "custom",
    spec: { entry: _mkt.rules, target_pct: tgt, stop_pct: stp, max_hold_sessions: hold },
  });
  if (error) return say("Couldn't publish — try again.");
  say("Published ✓ — the desk backtests it on ~19 years of every stock's own history, then it appears in the marketplace with its real numbers attached.");
  _mkt.mine = null; pageMarket();
}
async function pageMarket() {
  await Promise.resolve();
  const locked = !hasFeature("marketplace");
  const lib = await j("strategy_library.json");
  const deskN = (lib?.strategies || lib || []).length || 70;
  if (sb && me && _mkt.list === null) {
    const { data } = await sb.from("published_strategies").select("*").eq("status", "approved").order("created_at", { ascending: false }).limit(50);
    _mkt.list = data || [];
    const { data: mine } = await sb.from("published_strategies").select("*").eq("author_id", me.id).order("created_at", { ascending: false });
    _mkt.mine = mine || [];
  }
  const list = _mkt.list || [], mine = _mkt.mine || [];
  const card = s => `<div class="card mkt-card">
    <div class="mkt-top"><b>${esc(s.name)}</b><span class="tag">${esc(s.category)}</span>
      ${s.status !== "approved" ? `<span class="pill">${esc(s.status)}</span>` : ""}</div>
    <div class="sub">${esc(s.description || "")}</div>
    <div class="mkt-spec">${(s.spec?.entry || []).map(r => `<span class="scr-chip">${esc(r.lhs)} ${esc((MKT_OPS.find(o => o[0] === r.op) || [])[1] || r.op)} ${esc(String(r.rhs))}</span>`).join("")}</div>
    <div class="sub mkt-meta">target ${s.spec?.target_pct}% · stop ${s.spec?.stop_pct}% · max hold ${s.spec?.max_hold_sessions} sessions · by ${esc(s.author_name || "anon")}</div>
    ${s.backtest ? `<div class="mkt-bt"><span>win ${Math.round((s.backtest.hit_rate || 0) * 100)}%</span><span class="${(s.backtest.net_expectancy_pct || 0) >= 0 ? "up" : "dn"}">net ${sgn(s.backtest.net_expectancy_pct)}%</span><span>n ${s.backtest.n}</span></div>`
      : `<div class="sub mkt-bt-pending">Awaiting the desk's backtest — it will appear here with real win rate, expectancy after costs, and out-of-sample results, whatever they show.</div>`}
  </div>`;
  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Strategy marketplace</h2><div class="ln"></div><span class="pill">publishing coming soon</span></div>
  <p class="sub" style="margin-bottom:12px">Build from the same rule vocabulary the desk's own ${deskN} run on. <b>Publishing opens once every submission can be backtested</b> and shown whatever it shows — a failed strategy is as useful as one that worked. An untested one helps nobody.</p>
  ${locked ? planWall("The strategy marketplace",
    "Compose rules from the desk's indicator vocabulary and test the idea. Publishing, honest backtests and a ranked leaderboard follow.") : `
  <div class="ttabs">
    <button class="ttab ${_mkt.tab === "browse" ? "on" : ""}" onclick="_mkt.tab='browse';pageMarket()">Browse</button>
    <button class="ttab ${_mkt.tab === "build" ? "on" : ""}" onclick="_mkt.tab='build';pageMarket()">Build a strategy</button>
    <button class="ttab ${_mkt.tab === "mine" ? "on" : ""}" onclick="_mkt.tab='mine';pageMarket()">Mine (${mine.length})</button>
  </div>
  <div class="card tpanel">
  ${_mkt.tab === "build" ? `
    <div class="ark">compose a strategy</div>
    <p class="sub" style="margin:5px 0 10px">Entry fires when <b>all</b> conditions are true on the same bar. Fields are the desk's own indicators — nothing you write is executed as code, so a strategy is always safe to run.</p>
    <div class="tgrid">
      <label>Name<input id="mkt-name" class="ph-in" inputmode="text" enterkeyhint="next" aria-label="Strategy name" maxlength="80" placeholder="e.g. Quiet base breakout"></label>
      <label>Target %<input id="mkt-target" type="text" inputmode="decimal" enterkeyhint="next" class="ph-in" value="7"></label>
      <label>Stop %<input id="mkt-stop" type="text" inputmode="decimal" enterkeyhint="done" class="ph-in" value="3.5"></label>
      <label>Max hold (sessions)<input id="mkt-hold" type="text" inputmode="numeric" enterkeyhint="done" class="ph-in" value="15"></label>
    </div>
    <textarea id="mkt-desc" class="tknote" style="min-height:64px;margin-top:10px" maxlength="600" placeholder="What is the idea, in plain English? What market behaviour are you trying to capture?"></textarea>
    <div class="ark" style="margin-top:14px">entry conditions — all must be true</div>
    <div class="mkt-rules">${_mkt.rules.map(mktRuleRow).join("")}</div>
    <div class="tnote"><button class="note-save" onclick="_mkt.rules.push({lhs:'rsi14',op:'lt',rhs:40});pageMarket()">+ Add condition</button>
      <button class="pc-btn ghost" style="max-width:220px;display:inline-block;margin-left:8px" disabled>Publishing — coming soon</button>
      <div id="mkt-msg" class="sub" style="margin-top:8px"></div></div>
    <div class="tnote warn"><b>Why publishing isn't open yet.</b> A published strategy is only worth reading if the numbers beside it are real, so the desk won't accept submissions until it can backtest every one on ~19 years of each stock's own history and show the result <b>whatever it shows</b> — including losses. That pipeline is being built. Until it is, the builder above is yours to experiment with, and the desk's own ${deskN} strategies on the <a href="/strategies" style="color:var(--accent)">Strategies</a> page already carry their full, honest backtests.</div>`
      : _mkt.tab === "mine" ? (mine.length ? mine.map(card).join("")
        : `<div class="empty">You haven't published a strategy yet. Build one and the desk will test it properly.</div>`)
        : (list.length ? `<div class="mkt-grid">${list.map(card).join("")}</div>`
          : `<div class="empty"><b>Community publishing is coming soon.</b><br><br>The desk's own <b>${deskN}</b> strategies are live on the <a href="/strategies" style="color:var(--accent)">Strategies</a> page right now — every one backtested on each stock's own ~19-year history, with win rate, expectancy after costs and out-of-sample results shown in full. Use <b>Build a strategy</b> to compose your own idea in the meantime.</div>`)}
  </div>`}`;
}

/* Shareable entry point for the astro funnel: /cast drops you straight into the wizard.
   The reading itself lives at /mychart, which this hands off to. */
async function pageCast() {
  await pageMyChart();
  if (!natalChart()) setTimeout(openBirthWizard, 60);
}

/* ==========================================================================================
   CSV EXPORT — one delegated handler serves every table on the site.
   Rather than per-table export code, a button carrying data-csv="<filename>" serialises the
   nearest table in its own card. That means a new table gets export for free, and a table
   whose columns change can't drift out of sync with a hand-maintained column list.
   ========================================================================================== */
function csvCell(text) {
  // Excel/Sheets dialect: quote always, double any inner quote. Serialising the RENDERED text
  // keeps the file honest — what you exported is exactly what you were shown, em-dashes and all.
  return '"' + String(text ?? "").replace(/\s+/g, " ").trim().replace(/"/g, '""') + '"';
}
function tableToCSV(table) {
  return [...table.querySelectorAll("tr")]
    .map(tr => [...tr.querySelectorAll("th,td")].map(c => csvCell(c.innerText)).join(","))
    .join("\r\n");
}
function downloadCSV(name, csv) {
  // A BOM makes Excel read UTF-8 correctly — without it, company names with non-ASCII
  // characters arrive mojibake'd, which looks like a data bug and isn't one.
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob), a = document.createElement("a");
  a.href = url;
  a.download = `psx-desk-${name}-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);   // let the click consume it first
}
document.addEventListener("click", e => {
  const btn = e.target.closest("[data-csv]");
  if (!btn) return;
  e.preventDefault();
  const scope = btn.closest(".card, .seg")?.parentElement || document;
  const table = btn.closest(".card")?.querySelector("table") || scope.querySelector("table");
  if (!table) return;
  downloadCSV(btn.dataset.csv || "export", tableToCSV(table));
});
const csvBtn = name => `<button class="note-save csv-btn" data-csv="${esc(name)}" title="Download this table as a CSV file">↓ CSV</button>`;

/* ==========================================================================================
   GLOSSARY — every badge and scored term the desk shows, defined in one place.
   The desk invents vocabulary ("backtest-proven", "QA blocked", "composite fair"). A reader
   who guesses at those is reading a different product than the one that was built, so the
   definitions live in data, render as a page, and double as hover text on the badges.
   ========================================================================================== */
const GLOSSARY = [
  ["backtest-proven", "signals", "This exact rule was tested on this stock's own price history and cleared the desk's bar there. It is NOT a prediction — it means the pattern has paid on this name before, after costs. Always read the trade count beside it: a rule that won 60% over 10 trades is a much weaker claim than one that won 60% over 100."],
  ["audited ✓", "signals", "An independent Auditor agent re-derived every number in the setup from the raw data WITHOUT seeing the Strategist's reasoning, and got the same answer. Any mismatch kills the setup outright (CLAUDE.md Rule 7) — there is no override."],
  ["confidence (high / medium / low)", "signals", "The desk's own read on how much weight the evidence carries — driven mainly by the size and consistency of the backtest sample. High confidence on a small sample is still a small sample; the trade count is always shown next to it for exactly this reason."],
  ["out-of-sample", "signals", "The rule was fitted on an early slice of history, then tested on a later slice it had never seen. A strategy that looks good in-sample and falls apart out-of-sample was curve-fitted, not discovered — which is why both numbers are always published."],
  ["net expectancy", "signals", "Average profit or loss per trade AFTER the desk's estimated trading friction for that specific stock. Thin stocks are charged a wider spread than liquid ones, because assuming one flat cost flatters exactly the illiquid names that are hardest to actually trade."],
  ["composite fair value", "valuation", "The MEDIAN of four independent valuation methods (relative P/E, earnings power, Graham, dividend discount). A median is used so one method blowing out can't drag the blend. It is a model estimate on public fundamentals — research, never a price target."],
  ["method spread", "valuation", "How far apart the four valuation methods are. A wide spread means the methods fundamentally disagree about the company, so the single blended number deserves far less weight than a tight cluster would."],
  ["mispricing %", "valuation", "Distance between the live price and the composite fair value. Positive means the model reads it as below fair. A model reading cheap is a reason to investigate, never on its own a reason to buy."],
  ["predictability score", "quant", "How systematically a stock's own past behaviour has related to its next move, scored on ~19 years of its history. High predictability does not mean it will go up — it means its moves have been less random than its peers'."],
  ["QA clean / flags / blocked", "research", "The Verifier agent's adversarial fact-check of a published analysis. 'clean' = numbers verified. 'flags' = non-material caveats noted. 'blocked' = a real inconsistency was found and the analysis was corrected or explicitly caveated before publishing rather than quietly shipped."],
  ["research gate vs signal gate", "coverage", "Two separate liquidity bars. The research gate decides which names the desk ANALYSES; the stricter signal gate decides which it will ever publish a SETUP on. A stock can be fully researched and still never produce a setup — for a thin name that is the intended outcome, not a gap."],
  ["core / listed tier", "coverage", "'core' names get the full pipeline — deep history, backtests, fundamentals, debates. 'listed' names get prices, quant measures, sector and dividends, but not the expensive per-ticker analysis. Every listed company is visible and searchable; the ticker page says which tier it is rather than letting an empty section imply the desk looked and found nothing."],
  ["regime (risk-on / neutral / risk-off)", "macro", "The desk's read on Pakistan's macro backdrop — policy rate, PKR, inflation, external account, oil. It is context for sizing and patience, not a trade signal in itself."],
];
async function pageShipped() {
  const cl = await j("changelog.json");
  const rels = cl?.releases || [];
  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Recently shipped</h2><div class="ln"></div>${cl?.current ? `<span class="pill">v${esc(cl.current)}</span>` : ""}</div>
  <p class="sub" style="margin-bottom:12px">What actually changed on the desk, most recent first. Same list as the version badge's "What's new" popup — just always here, not just on the day it lands.</p>
  ${rels.length ? rels.map((r, i) => `
    <div class="card" style="margin-bottom:10px${i === 0 ? ";border-color:var(--accent)" : ""}">
      <div class="seg" style="margin:0 0 6px"><b>v${esc(r.version)}</b>${r.title ? `<span class="sub" style="margin-left:8px">${esc(r.title)}</span>` : ""}<span class="sub" style="margin-left:auto">${esc(r.date)}</span></div>
      <ul style="margin:0;padding-left:18px">${(r.notes || []).map(n => `<li>${esc(n)}</li>`).join("")}</ul>
    </div>`).join("") : `<div class="card"><div class="empty">No public release notes yet.</div></div>`}
  <p class="sub" style="margin-top:10px">The full engineering record stays in the repo — this is the reader-facing subset.</p>`;
}

async function pageGlossary() {
  await Promise.resolve();
  const groups = [...new Set(GLOSSARY.map(g => g[1]))];
  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Glossary</h2><div class="ln"></div><span class="pill">${GLOSSARY.length} terms</span></div>
  <p class="sub" style="margin-bottom:12px">Every badge and scored term this desk uses, in plain English — including what each one does <b>not</b> claim. If a word here is doing more work than you thought, that is the point of the page.</p>
  ${groups.map(g => `
    <div class="seg"><h2>${esc(g)}</h2><div class="ln"></div></div>
    <div class="card gloss-list">${GLOSSARY.filter(x => x[1] === g).map(([term, , def]) => `
      <div class="gloss-item"><div class="gloss-term">${esc(term)}</div><div class="gloss-def">${esc(def)}</div></div>`).join("")}</div>`).join("")}
  <p class="sub" style="margin-top:10px">Research and education, not advice. The desk never places orders.</p>`;
}
const GLOSS_TIP = Object.fromEntries(GLOSSARY.map(([term, , def]) => [term, def]));

/* ==========================================================================================
   COMPARE — up to four names side by side on the desk's own scored fields.
   The Ask page already answers "A vs B" in prose; this is the tabular counterpart, for when
   you want to read the same field across names rather than a narrative about two of them.
   ========================================================================================== */
let _cmp = { syms: [] };
function cmpAdd(sym) {
  sym = (sym || "").trim().toUpperCase();
  if (sym && !_cmp.syms.includes(sym) && _cmp.syms.length < 4) _cmp.syms.push(sym);
  pageCompare();
}
function cmpDrop(sym) { _cmp.syms = _cmp.syms.filter(x => x !== sym); pageCompare(); }
async function pageCompare() {
  await Promise.resolve();
  const [q, fv, fnd, fs, pred, sec, uni, bt] = await Promise.all([
    j("quant.json"), j("fairvalue.json"), j("fundamentals.json"), j("fundamental_scores.json"),
    j("predictability.json"), j("sectors.json"), j("universe.json"), j("backtests.json")]);
  const syms = _cmp.syms.filter(s => q?.tickers?.[s]);
  const missing = _cmp.syms.filter(s => !q?.tickers?.[s]);
  // "proven here" = strategies that cleared the bar on THIS stock's own history
  const provenCount = s => Object.values(bt?.templates || {})
    .reduce((n, per) => n + (per?.[s]?.eligible ? 1 : 0), 0);
  const col = s => {
    const v = q.tickers[s] || {}, t = fv?.tickers?.[s] || {}, f = fnd?.tickers?.[s] || {}, m = fs?.tickers?.[s]?.metrics || {};
    return { s, name: uni?.symbols?.[s]?.name || "", sector: sec?.tickers?.[s]?.sector || "—",
      price: v.close, ret20: v.ret_20d, rsi: v.rsi14, pe: m.pe, fpe: m.forward_pe,
      dy: parseFloat(f.div_yield) || null, payout: parseFloat(f.payout_ratio) || null,
      fair: t.composite_fair, gap: t.mispricing_pct, verdict: t.verdict,
      pred: pred?.tickers?.[s]?.score, proven: provenCount(s) };
  };
  const cols = syms.map(col);
  // Each row states its own units and, where the number is a model output rather than a fact,
  // says so — a compare table invites "bigger is better" reading more than a single page does.
  const ROWS = [
    ["Sector", c => esc(c.sector), ""],
    ["Price (Rs)", c => fmt(c.price), "num"],
    ["20-day move", c => c.ret20 != null ? `<b class="${cls(c.ret20)}">${sgn(c.ret20)}%</b>` : "—", "num"],
    ["RSI (14)", c => c.rsi ?? "—", "num"],
    ["P/E (trailing)", c => c.pe ?? "—", "num"],
    ["P/E (forward)", c => c.fpe ?? "—", "num"],
    ["Dividend yield", c => c.dy != null ? c.dy + "%" : "—", "num"],
    ["Payout ratio", c => c.payout != null ? c.payout + "%" : "—", "num"],
    ["Model fair value (Rs)", c => fmt(c.fair), "num"],
    ["vs fair value", c => c.gap != null ? `<b class="${c.gap > 0 ? "up" : c.gap < 0 ? "dn" : ""}">${sgn(c.gap)}%</b>` : "—", "num"],
    ["Predictability", c => c.pred ?? "—", "num"],
    ["Strategies proven here", c => c.proven || 0, "num"],
  ];
  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Compare</h2><div class="ln"></div><span class="pill">${cols.length}/4 names</span></div>
  <p class="sub" style="margin-bottom:12px">The same scored fields, read across names instead of down one page. Prefer a sentence? The <a href="/ask" style="color:var(--accent)">Ask</a> page answers "A vs B" in prose.</p>
  <div class="card">
    <div class="scr-row">
      <input id="cmp-in" class="ph-in combo" style="flex:1" aria-label="Add a company to compare" placeholder="Add a company — type a symbol or name"
        onkeydown="if(event.key==='Enter'){cmpAdd(this.value);this.value=''}">
      <button class="note-save" onclick="const i=document.getElementById('cmp-in');cmpAdd(i.value);i.value=''">Add</button>
    </div>
    <div class="scr-chips">${cols.length ? cols.map(c => `<span class="scr-chip">${esc(c.s)} <b class="cmp-x clickable" onclick="cmpDrop('${esc(c.s)}')" title="Remove ${esc(c.s)}">✕</b></span>`).join("")
      : '<span class="sub">Add two or more names to compare them.</span>'}</div>
    ${missing.length ? `<div class="tnote warn" style="margin-top:8px"><b>No data for ${missing.map(esc).join(", ")}</b> — check the symbol, or it may be a PSX board counter rather than a tradeable company.</div>` : ""}
  </div>
  ${cols.length < 2 ? `<div class="card"><div class="empty">Pick at least two names. Up to four fit side by side.</div></div>` : `
  <div class="card" style="padding:0"><table class="cmp-table"><thead><tr><th>Field</th>${
    cols.map(c => `<th class="r"><a href="/ticker/${esc(c.s)}" style="color:var(--accent);font-weight:700">${esc(c.s)}</a><div class="sub" style="font-weight:400">${esc((c.name || "").slice(0, 18))}</div></th>`).join("")}</tr></thead>
    <tbody>${ROWS.map(([label, render, kls]) => `<tr><td><b>${esc(label)}</b></td>${
      cols.map(c => `<td class="r ${kls}">${render(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
  <div class="tnote" style="margin-top:10px">${csvBtn("compare")}
    <span class="sub" style="margin-left:10px">Fair value is a <b>model estimate</b> on public fundamentals, not a price target — and the four methods behind it often disagree. "Strategies proven here" counts rules that cleared the bar on each stock's <b>own</b> history, so the counts are not directly comparable across names with different amounts of history. Terms explained in the <a href="/glossary" style="color:var(--accent)">glossary</a>.</span></div>`}`;
}

const PAGES = { learn: pageLearn, practice: pagePractice, tools: pageTools, screener: pageScreener, scenarios: pageScenarios, ask: pageAsk, sectors: pageSectors, market: pageMarket, plans: pagePlans, cast: pageCast, today: (...args) => window.HennethTodayRenderer ? window.HennethTodayRenderer(...args) : pageToday(...args), board: pageBoard, watchlist: pageWatchlist, portfolio: pagePortfolio, settings: pageSettings, strategies: pageStrategies, value: pageValue, macro: pageMacro, astro: pageAstro, mychart: pageMyChart, dividends: pageDividends, calendar: pageCalendar, research: pageResearch, leaderboard: pageLeaderboard, news: pageNews, legal: pageLegal, glossary: pageGlossary, compare: pageCompare, shipped: pageShipped, unsubscribe: pageUnsubscribe };
let lastPage = null;

let _enterT = 0;
function animateIn() {
  const v = $("view");
  v.classList.remove("enter"); void v.offsetWidth; v.classList.add("enter");
  // Drop the class only after the FULL stagger. An animationend listener fires on the first
  // bubbled child event, which cancels the still-delayed animations on later children mid-flight;
  // the timer covers max child delay + --dur-base with headroom, so anything the enhancement
  // pipeline inserts after that cannot replay the fade.
  clearTimeout(_enterT);
  _enterT = setTimeout(() => v.classList.remove("enter"), 480);
}

/* ==========================================================================================
   THE SIGN-IN GATE

   The terminal is members-only. Everything below is the PRODUCT gate — it decides which ROUTES
   render for a signed-out visitor, and it controls the funnel.

   IT IS NOT THE ONLY GATE ANY MORE, and the distinction matters. This comment used to end
   "every state/*.json is still fetchable by anyone who knows the URL — do not mistake this screen
   for that", which was true and important right up until 2026-07-21. It is now wrong. The DATA
   layer is gated independently by `middleware.js`, Vercel Edge Middleware matching `/state/:path*`,
   which verifies a Supabase ES256 access token against the project's published JWKS before the
   CDN serves the file. `curl https://desk.henneth.app/state/rooms.json` returns 401, and
   docs/OPERATIONS.md §9b keeps that as a standing regression check.

   So there are two independent gates and they fail independently:
     * THIS one hides routes in the browser. Bypassable by anyone reading the JS — it always was.
     * middleware.js withholds the research itself. Not bypassable from the client.

   Which means: do not add a route here and assume the data behind it is protected, and do not
   remove a file from middleware.js's PUBLIC_FILES set expecting this screen to cover it. They
   guard different things.

   OPEN_ROUTES is the deliberate exception list. /cast and /mychart stay open because casting
   a birth chart without an account IS the acquisition funnel — guestChart() + migrateGuestChart()
   exist precisely so that a stranger can get value first and carry it into the account they
   create afterwards. Gating them would close the top of the funnel to protect the bottom.
   Legal pages stay open because a visitor must be able to read terms before signing anything.
   ========================================================================================== */
const OPEN_ROUTES = ["cast", "mychart", "legal", "plans", "glossary", "shipped", "unsubscribe"];

/* `me` is declared with `let` further down this file (the accounts section), and route() runs
   before that line is reached at boot. Touching a `let` binding in its temporal dead zone throws
   ReferenceError — not undefined — which killed route() outright and rendered a blank page. This
   file has hit that exact bug before (applyDeskMode reading `me` at module top level).
   Catch it and FAIL CLOSED: unknown auth state shows the gate, and initAuth's route(true) repaints
   the moment the session resolves. */
function isSignedIn() {
  try { return !!me; } catch { return false; }
}

function gateAllows(page) {
  return isSignedIn() || OPEN_ROUTES.includes(page || "today");
}

/* AUTH IS UNKNOWN AT FIRST PAINT — and guessing is what caused the flash.
   sb.auth.getSession() restores the session from localStorage asynchronously, so at module-eval
   time `me` is not merely unset, it is in its temporal dead zone. isSignedIn() therefore fails
   closed to `false`, and the old boot called route() immediately: a signed-in member reloading
   the desk watched the sign-in gate paint and then get replaced, and a signed-out visitor watched
   the terminal shell paint and then get stripped. Two symptoms, one bug.
   The fix is to paint NOTHING until the answer is known. route() returns early while pending,
   index.html ships body[data-auth="pending"] so the static shell is hidden from the very first
   frame, and initAuth() is the single thing that clears the flag and triggers the first render. */
let authReady = false;

/* Boot-screen counter. Deliberately NOT a fake progress bar: there is nothing measurable to report
   (the work is one localStorage read plus one network call of unknown latency), so a smooth 0-100
   would be theatre. It eases toward 92 and STOPS there, then snaps to 100 the instant auth actually
   resolves — so the only two honest states, "still working" and "done", are the two it can show.
   The CSS keeps the whole screen hidden for the first 260ms, so a warm session never sees it. */
let _bootTimer = null;
function startBootCounter() {
  const el = document.getElementById("bootPct");
  if (!el) return;
  let v = 0;
  _bootTimer = setInterval(() => {
    v += Math.max(0.4, (92 - v) * 0.06);   // asymptotic — fast at first, never actually reaches 92
    el.textContent = Math.min(92, Math.round(v)) + "%";
  }, 55);
}
function stopBootCounter() {
  if (_bootTimer) { clearInterval(_bootTimer); _bootTimer = null; }
  const el = document.getElementById("bootPct");
  if (el) el.textContent = "100%";
}
startBootCounter();

function authResolved() {
  if (authReady) return;
  authReady = true;
  stopBootCounter();
  try { document.body.removeAttribute("data-auth"); } catch {}
}
/* Backstop. Everything that resolves auth is async and some of it is network: a blocked Supabase
   CDN, an offline reload, or a throw anywhere between here and initAuth() would otherwise leave a
   permanently blank page — strictly worse than the flash we are fixing. Fail CLOSED after the
   timeout: unknown auth shows the gate, which a real member can click straight through.

   8s, not 3s. This fires ONLY when the real auth path has already failed, so every second of it is
   spent on a screen no healthy session ever sees — while 3s was short enough to fire on a genuinely
   slow mobile connection and throw a signed-in member out to the gate for no reason. Long enough to
   never pre-empt a working session; short enough that a truly dead one still resolves to something
   clickable rather than hanging. */
const AUTH_BACKSTOP_MS = 8000;
setTimeout(() => {
  if (authReady) return;
  console.warn(`auth did not resolve in ${AUTH_BACKSTOP_MS}ms — failing closed to the sign-in gate`);
  authResolved();
  route(false);
}, AUTH_BACKSTOP_MS);

/* ------------------------------------------------------------------------------------------
   ONE TRACKING CALL, TWO DESTINATIONS.

   Both analytics tags on this page are loaded conditionally (see index.html — each is wrapped in
   a live-host check), so on localhost, on a file:// open and on any preview build BOTH `gtag` and
   `posthog` are simply undefined. Every call here therefore has to be optional-chained, and this
   helper exists so that is done in exactly one place rather than at thirty call sites.

   WHY THIS EXISTS AT ALL: until now the desk fired no events whatsoever — `gtag(` appeared zero
   times in this file. GA4 could see that somebody loaded the sign-in gate and nothing after that.
   Whether they read it and left, started typing and gave up, failed the captcha, or actually
   created an account were all the same event: one pageview. That is the single most expensive
   blind spot in the funnel, because it is the exact step paid traffic has to survive.

   NO PII. Never pass an email address, a password field, or anything derived from them. The
   properties below are counts, reasons and modes — enough to find where people fall out, not
   enough to identify who they were. */
function track(name, props) {
  try { window.posthog?.capture(name, props || {}); } catch {}
  try { window.gtag?.("event", name, props || {}); } catch {}
}

function renderGate(page) {
  /* The funnel's first measurable step: somebody hit a members-only page while signed out.
     `page` matters — arriving at the gate from a shared /ticker/ link is a different intent
     from landing on it cold, and the two convert differently. */
  track("gate_viewed", { page: page || "today", plan_intent: planIntent() || "none" });
  capturePlanIntent();          // route() reaches here before the module-level call below runs
  // strips the sidebar + in-app header controls (see themes.css [data-gated]); cleared in route()
  try { document.body.setAttribute("data-gated", "1"); } catch {}
  /* The gate IS the sign-in screen now. There is no interstitial card explaining that the desk is
     members-only and offering two buttons — the research terminal says the same thing by being the
     only thing on screen, and it costs a click less. */
  $("view").innerHTML = "";
  /* Moving between two gated pages re-runs route(), and remounting would replay the terminal's
     four-second boot sequence every time. The surface already up is the correct one. */
  if (_authTerm) return;
  // Somebody who picked a plan came here to create an account; everyone else is more likely returning.
  openAuth(planIntent() ? "signup" : "signin");
}

// Supabase email links (confirm / recovery) can bounce back an ERROR in the URL hash when the link
// is expired or already used, e.g. #error=access_denied&error_code=otp_expired&error_description=...
// detectSessionInUrl consumes SUCCESS tokens but leaves an error hash sitting in the URL — and
// route() bails on any error_code= hash, so without this the visitor is stranded on a permanently
// blank page with no explanation (the top signup-failure symptom in production). Parse the error,
// tell them plainly, offer a fresh link, then CLEAR the hash so routing resumes instead of looping.
function consumeAuthErrorHash() {
  const h = location.hash || "";
  if (!/error=|error_code=|error_description=/.test(h)) return false;
  const p = new URLSearchParams(h.replace(/^#\/?/, ""));
  const code = (p.get("error_code") || p.get("error") || "").toLowerCase();
  const desc = (p.get("error_description") || "").replace(/\+/g, " ");
  // Clear the hash FIRST so a reload or a re-entrant route() cannot loop on it.
  try { history.replaceState(null, "", location.pathname + location.search); }
  catch { try { location.hash = ""; } catch {} }
  try { track("auth_link_error", { code: code.slice(0, 40) }); } catch {}
  const expired = /otp_expired|expired|invalid/.test(code + " " + desc);
  // Expired link is almost always a confirmation link. Land the visitor on the SIGN-UP tab:
  // re-submitting the same email for an unconfirmed account makes Supabase resend the confirmation
  // (an already-confirmed email returns "already registered", which friendlyAuthError routes to
  // sign in). That's a recovery path the form actually performs, not an empty promise.
  const tab = expired ? "signup" : "signin";
  const msg = expired
    ? "That email link has expired or was already used. Re-enter your email below and we'll send a fresh confirmation link."
    : (desc || "That sign-in link didn't work. Enter your email below and try again.");
  try { openAuth(tab); authMsg(msg, true); } catch {}
  return true;
}

async function route(isPoll) {
  // Fragments from old dashboard links are not sent to Vercel, so canonicalize
  // them in the existing router before dispatching. Auth protocol fragments are
  // deliberately excluded by normalizeLegacyHash().
  normalizeLegacyHash();
  // Supabase auth callbacks (email confirm / password reset) arrive in the hash —
  // they're not routes; the client's detectSessionInUrl consumes SUCCESS tokens and fires
  // onAuthStateChange. Error hashes are handled up-front by consumeAuthErrorHash() in initAuth.
  if (/access_token=|error_code=|type=recovery|type=signup/.test(location.hash)) return;
  // Auth still resolving — render nothing rather than render the wrong thing and swap it out.
  // initAuth() (or the 3s backstop) calls route() again the moment the session is known.
  if (!authReady) return;
  const path = "/" + appPathname().replace(/^\/+|\/+$/g, "");
  const [, rawPage, ...rest] = path.split("/");
  const arg = rest.join("/");
  const page = rawPage || "today";
  document.querySelectorAll("[data-nav]").forEach(a => a.classList.toggle("on", a.dataset.nav === (page || "today")));
  // Fire and forget. Awaiting it blocked EVERY navigation on five header fetches, so a click on a
  // nav item did nothing at all until they resolved. The pills no longer jump when they land late
  // because they reserve their own width in CSS (min-width + tabular figures), which is where that
  // problem belongs — the fix was never worth stalling the whole route on.
  renderHeader();
  const key = page + (arg || "");
  const scrollWas = window.scrollY || 0;
  // A real navigation closes any open modal — otherwise its node, keydown listener and (for the
  // run modal) its rAF loop outlive the page they belonged to. The auth box survives: a sign-in
  // in progress must not be torn down by a hash change it may itself have caused.
  if (!isPoll) {
    document.querySelectorAll(".pl-overlay,.replay-overlay").forEach(o => {
      if (o.querySelector("#authbox")) return;
      // Modals register their close() on the node so teardown also removes their document-level
      // keydown listener (and, for the lesson player, restores body scroll). Bare remove() leaked
      // one listener per abandoned modal for the life of the tab.
      if (typeof o._close === "function") o._close(); else o.remove();
    });
    // The lesson player locks body scroll on open and only closePlayer() unlocks it — a hash
    // change away from an open lesson left the whole page permanently unscrollable.
    document.body.style.overflow = "";
  }
  // Members-only gate. Runs AFTER renderHeader so the shell/nav still paints (a bare white
  // screen reads as broken), and before any page render so no gated page fetches or flashes.
  if (!gateAllows(page)) { hideGlobalStrip(); lastPage = key; return renderGate(page); }
  // reached a permitted page: restore the full shell. Must be cleared here rather than only on
  // sign-in, because the open routes (/cast, legal, glossary) are reachable while signed out and
  // would otherwise inherit the stripped-down chrome from a previous gated view.
  try { document.body.removeAttribute("data-gated"); } catch {}
  // ...and drop the sign-in terminal with it: the open routes (/cast, legal, glossary) are
  // reachable while signed out, and the gate's terminal would otherwise stay over them.
  closeAuth();
  // The tape is desk chrome, not page content: it shows on every permitted page. Its box is
  // reserved here, before the async render — CSS gives #gstripHost a min-height so the
  // reservation holds even on first load, before the track exists. The only place it is ever
  // hidden is the members-only gate above.
  delete document.body.dataset.strip;
  primeGlobalStrip();
  // A page render is async (often several fetches). Until it resolves the old page just sat there,
  // so a nav click read as "nothing happened". Paint a skeleton the instant we know we're moving —
  // the page's own innerHTML write replaces it. Not on a poll: that would flash the current page out.
  if (!isPoll && key !== lastPage) {
    const v = $("view");
    if (v) v.innerHTML = '<div class="skelwrap"><div class="skel-line"></div><div class="skel-line"></div><div class="skel-line"></div><div class="skel-line short"></div></div>';
  } else {
    // silent re-render (poll, language switch, auth event): a lingering `enter` class would
    // replay the whole page-in animation on the freshly inserted children
    const v = $("view");
    if (v) v.classList.remove("enter");
  }
  try {
    if (page === "ticker" && arg) { await pageTicker(arg); }
    else { await (PAGES[page] || pageBoard)(); }
  } catch (err) {
    // a page render must NEVER leave a blank screen — show the failure instead
    console.error("page render failed:", page, arg, err);
    const v = $("view");
    if (v && (!v.innerHTML || v.innerText.trim().length < 40)) {
      v.innerHTML = `<a class="crumb" href="/board">← board</a>
        <div class="card"><div class="empty">Couldn't render ${esc((page || "this page") + (arg ? " " + arg : ""))} — a data file may still be loading or unavailable this cycle.<br><br>
        <b>Try:</b> reload the page (Ctrl+Shift+R to bypass cache). If it persists, the desk's data for this name may be missing this cycle.<br>
        <span class="sub">${esc(String(err && err.message || err)).slice(0, 160)}</span></div></div>`;
    }
  }
  // animate only on a real navigation (not the 30s silent refresh of the same page)
  if (!isPoll && key !== lastPage) { animateIn(); if (window.scrollTo) window.scrollTo(0, 0); }
  // A silent refresh of the SAME page rebuilds #view from scratch, which collapses the document
  // height for a frame and dumps the reader back at the top mid-read. Put them back where they were.
  else if (isPoll && key === lastPage && scrollWas && window.scrollTo) {
    requestAnimationFrame(() => window.scrollTo(0, scrollWas));
  }
  lastPage = key;
}
/* Keyboard access for click-only elements. Large parts of the UI use `onclick` on <div>, <span>
   and <tr> — fast to write, but unreachable by keyboard and invisible to screen readers. Rather
   than hand-editing every call site, make them focusable and Enter/Space-activatable here, once.
   A <tr> must not take role="button" (it breaks the table's semantics), so it gets tabindex only. */
function wireClickables(root = document) {
  root.querySelectorAll(".clickable:not([data-kb])").forEach(el => {
    el.dataset.kb = "1";
    if (!el.hasAttribute("tabindex")) el.tabIndex = 0;
    const tag = el.tagName;
    if (!el.hasAttribute("role") && tag !== "TR" && tag !== "A" && tag !== "BUTTON") el.setAttribute("role", "button");
  });
}
/* ------------------------------------------------------------------------------------------
   TABLES ON A PHONE.

   ~40 tables are built as raw HTML string templates all over this file. Rather than edit every
   call site, fix them all once, here, after each render.

   Two things happen:

   1. Each <table> gets wrapped in a `.tscroll` div. A <table> cannot scroll itself — the old CSS
      forced `display:block` on it, which silently drops `width:100%` (a block box shrink-wraps
      its content) and was half the reason tables looked broken on mobile. A wrapper scrolls
      properly and lets the table stay a real table that fills its card.

   2. Each <td> gets `data-l` = the text of the <th> above it, so the stacked mobile layout can
      print the column name next to the value. Without this a stacked row is a list of naked
      numbers with nothing saying which is the price and which is the yield.

   Idempotent: both steps mark what they touch and skip it next time. The MutationObserver below
   fires on every render, and this must not re-wrap on each pass. */
function enhanceTables(root = document) {
  root.querySelectorAll("table:not([data-tbl])").forEach(t => {
    t.dataset.tbl = "1";
    const heads = [...t.querySelectorAll("thead th")].map(h => h.textContent.trim());
    if (heads.length) {
      // A header cell may be deliberately blank (the caret/action column). Blank stays blank —
      // printing an empty label would leave a stray colon on every stacked row.
      t.querySelectorAll("tbody tr").forEach(tr => {
        [...tr.children].forEach((td, i) => {
          if (heads[i]) td.setAttribute("data-l", heads[i]);
        });
      });
      t.dataset.cols = heads.length;
    } else {
      /* Headless tables (the macro geo-factor grid, the ticker risk table) are built as bare
         <tbody> rows. They still need a column count so the stacking rule can reach them —
         the widest of these is 5 columns including a rendered bar, which at 321px squeezed its
         label column to 23px. Count the widest row, and mark it so the stacked cells render as
         plain blocks: there are no headers to print as labels. */
      const wid = Math.max(0, ...[...t.querySelectorAll("tbody tr")].map(tr => tr.children.length));
      if (wid) { t.dataset.cols = wid; t.dataset.nohead = "1"; }
    }
    const p = t.parentElement;
    if (p && p.classList.contains("tscroll")) return;
    const wrap = document.createElement("div");
    wrap.className = "tscroll";
    p.insertBefore(wrap, t);
    wrap.appendChild(t);
  });
  // restackTables() is NOT called here. It measures every table against its container, and tileify()
  // runs after this and moves tables into .tilebox wrappers — so measuring here measured the layout
  // that was about to change, then measured it all again. flush() calls it once, after tileify().
}

/* WHICH TABLES STACK IS MEASURED, NOT GUESSED.
   The first version of this keyed off the column count — "5 or more columns stacks". That was
   wrong in both directions: a 3-column sector table whose middle column holds three driver chips
   needs 460px and does not fit, while a 5-column table of short numbers fits fine. Column count
   is a proxy for width; width is available for free, so use it.

   Measure each table with stacking OFF, and turn it on only for the ones that genuinely do not
   fit their card. A table that fits stays a table — stacking a list that already works would
   triple its height and destroy the down-the-column scan that is the point of a table. */
function restackTables() {
  const narrow = window.innerWidth <= 560;
  const tables = [...document.querySelectorAll(".tscroll>table[data-cols]")];
  // Write → read → write PER TABLE forced a synchronous layout for every table on the page, and
  // each unstack-then-restack was visible on a phone as the rows flickering out of and back into
  // their stacked form. Do it in three passes instead: unstack everything, THEN measure everything
  // (one layout for the lot), THEN stack what needs it. All three run in one synchronous turn, so
  // the intermediate unstacked state is never painted.
  // Only touch the tables that actually carry the attribute. flush() runs on any body mutation, so
  // an unconditional strip/reapply churned the DOM on every pass; on a desktop width where nothing
  // is stacked this now does no writes at all.
  tables.filter(t => t.hasAttribute("data-stack")).forEach(t => t.removeAttribute("data-stack"));
  if (!narrow) return;
  const need = tables.map(t => {
    const room = t.parentElement.clientWidth;
    return !!room && t.scrollWidth > room + 2;
  });
  tables.forEach((t, i) => { if (need[i]) t.setAttribute("data-stack", "1"); });
}
/* A .tilebox's bottom fade and "scroll ▾" hint promise more content below. Both are lies once
   the user has reached the bottom, and lies from the first paint if the content already fits —
   and a permanent fade over a short list reads as a rendering bug. Measure instead of decorate. */
/* The cap is viewport-derived, so it only moves on a resize — but this ran tileDims() (which reads
   window.innerHeight) and then wrote --tilemax on every box on every flush, and each sync() read
   scrollHeight straight after its own write, forcing a synchronous layout per tile. Cache the cap,
   write it only when it actually changed, and do all the writes before any of the reads. */
let _tileMax = null;
function wireTiles(root = document) {
  if (_tileMax === null) _tileMax = tileDims().max;
  const boxes = [...root.querySelectorAll(".tilebox>.tilebody")];
  boxes.forEach(b => {
    const box = b.parentElement;
    if (box.dataset.tilemax !== String(_tileMax)) {
      box.dataset.tilemax = String(_tileMax);
      box.style.setProperty("--tilemax", _tileMax + "px");
    }
  });
  // Initial pass split read/write: interleaving each box's scrollHeight read with the previous
  // box's class toggle forced one synchronous layout PER TILE. Measure everything, then toggle.
  const meas = boxes.map(b => ({ b, room: b.scrollHeight - b.clientHeight, top: b.scrollTop }));
  meas.forEach(({ b, room, top }) => {
    const box = b.parentElement;
    box.classList.toggle("no-scroll", room <= 4);
    box.classList.toggle("at-end", top >= room - 4);
    if (!b.dataset.tile) {
      b.dataset.tile = "1";
      b.addEventListener("scroll", () => {
        const r = b.scrollHeight - b.clientHeight;
        box.classList.toggle("no-scroll", r <= 4);
        box.classList.toggle("at-end", b.scrollTop >= r - 4);
      }, { passive: true });
    }
  });
}

/* THE GLOBAL LONG-SCROLL PASS.
   An audit found ~40 blocks across 29 page functions that render an unbounded list: the calendar's
   every event of every month, the strategy library's 70 entries, a portfolio's holdings twice over
   (table then weight bars). Hand-wrapping each is 40 edits that go stale the day a page is added,
   and the caps live 20-80 lines from the markup they bound, so the next author will miss one.

   What actually matters is one measurable property — "this block is taller than the phone screen
   and the card below it is unreachable" — so measure that instead of enumerating class names. A
   direct child of a card, tall, and made of many sibling rows, is a list. Anything else is layout.

   Deliberately NOT tiled: short blocks — nothing is gained, and a fade over a list that ends is a lie.

   This applies on desktop too. The original version bailed above 900px on the theory that a wide
   screen makes the down-the-column scan worth the height, but that only holds for a list that is
   merely long. The board's universe grid is ~120 cells at any width; on a 1440px monitor it still
   pushed predictability and proven strategies a full screen and a half below the fold, and nobody
   scrolls past a wall of cells to find out there were cards under it. What changes with width is
   the BUDGET, not the rule — so the thresholds are derived from viewport height instead of frozen
   at phone values. */
const TILE_MIN_ROWS = 8;    // fewer sibling rows than this is a layout block, not a list
const TILE_TALL = 700;      // ...unless it is simply this tall, whatever it is made of
const TILE_SKIP = /\b(sumstrip|statgrid|seg|tk-head|ttabs|tilebox)\b/;

/* Trigger: a block taller than ~70% of the viewport means whatever follows it starts off-screen.
   Cap: a bit over half the viewport, so the tile reads as "a window onto a list" — tall enough to
   scan, short enough that the next card's heading is visible without scrolling. Both are clamped:
   the floors are the phone values that were already validated, the ceiling keeps a 4K monitor from
   producing a "cap" so tall it caps nothing. */
function tileDims() {
  const vh = window.innerHeight || 800;
  return {
    trigger: Math.max(460, Math.round(vh * 0.7)),
    max: Math.min(620, Math.max(340, Math.round(vh * 0.55))),
  };
}

/* THE OTHER SHAPE: the card that IS the list.
   The pass below looks for one tall child to wrap, which catches a wrapper like .wire or a table but
   misses a card whose direct children ARE the rows — research renders 16 sibling .rdoc blocks with no
   container at all. Every row is ~90px so nothing ever trips the trigger, yet the card runs 1500px and
   buries the card under it exactly the same way. So wrap the RUN.

   "Consecutive siblings sharing a class" is what separates a list from a card's assorted layout blocks:
   a heading, a sub, and a chart are three different classes in a row and can never form a run, while
   rows emitted by one .map() are always identical. An empty className is too ambiguous to judge and is
   left alone.

   Match on the FIRST class token, not the whole attribute. Rows from one .map() routinely carry a
   per-row state class — the ticker page emits `lrow s-yes` / `lrow s-ask` / `lrow s-no`, and the signal
   stack emits `sig-row` beside `sig-row locked clickable`. Comparing full classNames read those as
   seven unrelated blocks and wrapped nothing, while the card ran 1166px. The base class is what says
   "same kind of row"; the rest says what that row happens to contain.

   The run floor is lower than TILE_MIN_ROWS because a run is much stronger evidence than a child count:
   five siblings of the SAME kind that together fill most of the viewport is a list, whereas five
   assorted children of a container proves nothing about what the container is.

   A run must also agree on TAG, and paragraphs never count. Macro's country card runs
   `P.sub, P.sub, DIV.sub, P.sub, P.sub` — five siblings sharing the base class `sub`, because `sub` is
   this sheet's muted-text class and marks both a caption and a body paragraph. Matching on class alone
   read 906px of prose as a list and put it in a scroll box, which is the one outcome this pass is meant
   to avoid. Rows from a .map() are div soup; prose is <p>. Requiring the tag to match as well separates
   them without needing to know what `sub` means. */
const TILE_RUN_MIN = 5;
const baseCls = el => (el.className || "").toString().trim().split(/\s+/)[0] || "";
const runKey = el => el.tagName + "." + baseCls(el);

function tileRuns(card, trigger) {
  const kids = [...card.children];
  // Pass 1 — reads only. Wrapping run A used to invalidate layout before run B's offsetHeight
  // reads, forcing a reflow per run. Collect every qualifying run first, then do all the writes.
  const wraps = [];
  let i = 0;
  while (i < kids.length) {
    const cls = baseCls(kids[i]);
    if (!cls || kids[i].tagName === "P" || kids[i].dataset.tiled || TILE_SKIP.test(cls)) { i++; continue; }
    const key = runKey(kids[i]);
    let j = i, h = 0;
    while (j < kids.length && runKey(kids[j]) === key) { h += kids[j].offsetHeight; j++; }
    const run = kids.slice(i, j);
    if (run.length >= TILE_RUN_MIN && h >= trigger) wraps.push(run);
    i = j;
  }
  // Pass 2 — writes only.
  wraps.forEach(run => {
    const box = document.createElement("div");
    box.className = "tilebox";
    const body = document.createElement("div");
    body.className = "tilebody";
    card.insertBefore(box, run[0]);          // anchor before the run so DOM order is preserved
    box.appendChild(body);
    run.forEach(el => { el.dataset.tiled = "1"; body.appendChild(el); });
  });
}

function tileify(root = document) {
  const { trigger } = tileDims();
  // Cards are not the only thing that holds a list. The ticker page's "how to read this" disclosure
  // puts a 770px .checklist inside a <details>, which no .card ever contains — so an open disclosure
  // pushed everything under it off-screen while being invisible to this pass. Any block that can hold
  // a long list is a container here.
  const cards = [...root.querySelectorAll(".card, details")];
  // Pass 1 — reads only, across ALL cards. The single-loop version wrapped card A's child (a
  // write) and then read card B's offsetHeight, forcing a synchronous reflow per wrapped block.
  const jobs = [];
  cards.forEach(card => {
    [...card.children].forEach(el => {
      if (el.dataset.tiled || TILE_SKIP.test(el.className || "")) return;
      if (el.tagName !== "DIV" && el.tagName !== "TABLE") return;
      if (el.offsetHeight < trigger) return;
      // A table is a list by construction, so it needs no further proof — and demanding one was
      // wrong: the dividends table stacks on a phone into 4 rows of 170px, which is neither 8 rows
      // nor (at 679px) over the height escape, so it slipped through by 21px while being exactly
      // the thing this pass exists to cap. A .tscroll wrapper holds exactly one table, so look
      // through it. Everything else must still prove it is a list rather than prose or layout:
      // many sibling rows, or sheer height. Chopping a paragraph into a scroll box is worse than
      // a long paragraph, which is why the DIV/TABLE tag gate above excludes <p> outright.
      const isList = el.tagName === "TABLE" || !!el.querySelector(":scope>table>tbody");
      if (!isList && el.children.length < TILE_MIN_ROWS && el.offsetHeight < TILE_TALL) return;
      jobs.push({ card, el });
    });
  });
  // Pass 2 — writes only.
  jobs.forEach(({ card, el }) => {
    el.dataset.tiled = "1";
    const box = document.createElement("div");
    box.className = "tilebox";
    const body = document.createElement("div");
    body.className = "tilebody";
    card.insertBefore(box, el);
    box.appendChild(body);
    body.appendChild(el);      // moving a node keeps its inline onclick and its listeners
  });
  cards.forEach(card => tileRuns(card, trigger));  // after the child pass, so anything already wrapped is out of the way
  wireTiles(root);
}

/* Rotating the phone changes the answer. Attribute writes don't trip the childList observer, so
   this cannot loop. */
let _restackT = null;
window.addEventListener("resize", () => {
  clearTimeout(_restackT);
  _restackT = setTimeout(() => { _tileMax = tileDims().max; tileify(); restackTables(); }, 150);
});

document.addEventListener("keydown", e => {
  if (e.key !== "Enter" && e.key !== " ") return;
  const el = e.target.closest?.(".clickable");
  if (!el || ["INPUT", "TEXTAREA", "SELECT", "A", "BUTTON"].includes(e.target.tagName)) return;
  e.preventDefault();
  el.click();
});
/* Pages re-render constantly, and .clickable elements also live OUTSIDE #view (the global strip,
   modals appended to body), so observe the whole document rather than just the view container. */
if (window.MutationObserver) {
  let queued = false, catchTimer = 0;
  /* flush() itself mutates the DOM (wrapping tables in .tscroll, tileifying, swapping translated
     text), so it re-armed the observer it was answering: every render cost a second full pass over
     the whole document, and on a phone that pass is what the eye sees as the layout settling twice.
     Every step of flush() is synchronous, so nothing else can mutate the DOM while it runs — which
     means every record sitting in the queue when it returns was raised BY it. Drop exactly those.
     A real mutation arriving afterwards re-arms the observer normally, and flush() re-walks the
     entire document rather than a delta, so nothing that landed before it can be missed. */
  /* Some regions mutate every frame BY DESIGN — the run modal's progress counter, the boot
     percentage. Each of those writes woke a full-document pass (wrap ~40 tables, measure every
     tile, walk the tree for translation) that could not possibly change anything, which is what
     made the loader animation stutter. Marking a region [data-no-enhance] says "nothing in here
     needs enhancing"; a batch made up entirely of such records is dropped. A batch that also
     touches anything else still flushes normally. */
  const inert = recs => recs.length > 0 && recs.every(r => {
    const t = r.target;
    return t && (t.nodeType === 1 ? t : t.parentElement)?.closest?.("[data-no-enhance]");
  });
  const flush = () => {
    queued = false;
    wireClickables(document); enhanceTables(document); tileify(document);
    restackTables();          // after tileify(): tables must be measured in their FINAL container
    // icons are attribute-only (no text node) — tag before translateTree rewrites heading text,
    // or the icon hook is gone by the time translation runs
    iconify(document);
    translateTree(document.body);
    mo.takeRecords();
  };
  const mo = new MutationObserver(recs => {         // batch: renders fire hundreds of mutations
    if (queued) return;
    if (inert(recs)) return;
    queued = true;
    // guard: in a background tab rAF callbacks pile up while the catch-up timer does the real
    // flushing — on refocus they'd all run in one frame, each a full document pass
    requestAnimationFrame(() => { if (queued) flush(); });
    /* rAF does not run in a hidden tab. The desk re-renders every 30s on a poll, so a page
       rendered while the tab was in the background used to come back with none of this applied
       until something else forced a repaint. Timers still fire when hidden — catch up with one. */
    clearTimeout(catchTimer);
    catchTimer = setTimeout(() => { if (queued) flush(); }, 300);
  });
  mo.observe(document.body, { childList: true, subtree: true });
}
wireClickables(document);   // whatever is already on the page at boot
enhanceTables(document);
restackTables();            // enhanceTables() no longer calls it — see flush()
document.getElementById("langBtn")?.addEventListener("click", () => setLang(lang() === "ur" ? "en" : "ur"));
/* applyLang() MUST run before translateTree(): it caches each chrome element's true English
   text into dataset.en on first touch. If translateTree() ran first (lang="ur" from a prior
   session), it would mutate the text to Urdu before applyLang() ever saw it, permanently
   caching the Urdu string as "English" and making setLang('en') unable to ever restore it. */
applyLang();   // safe at module top level: reads localStorage only, never `me`
translateTree(document.body);
window.addEventListener("popstate", () => route(false));
// NOTE: do NOT call applyDeskMode() here — this line runs before `let me` is initialized further
// down the file, and deskMode() reads it, which throws a TDZ error and aborts the whole module.
// index.html ships data-desk="pro" as the default; initAuth re-stamps it once the plan is known.
// The first render is NOT triggered here any more. route() no-ops until auth is known, and
// initAuth() (bottom of file) performs the first paint once the session has resolved — otherwise
// this line renders a guess that gets replaced a moment later, which is the flash.
route(false);
// Keep only the top status pills current on a gentle cadence — do NOT re-render the whole
// page body (that caused a jarring full-page refresh/flicker every cycle). Header-only, and
// paused while a modal is open. The body updates on navigation or a manual reload.
setInterval(() => {
  if (document.querySelector(".replay-overlay, #authbox, .wizbox:not([hidden])")) return;
  // Drop ONLY the files the header actually reads intraday. Wiping the whole cache also threw
  // away dossiers.json (~840 KB) and rooms.json, so the next navigation re-downloaded a megabyte
  // every minute — the heavy files keep their 10-minute TTL and are re-fetched on their own clock.
  LIVE_FILES.forEach(k => { delete cache[k]; });
  delete cache["quant.json"]; delete cache["macro.json"]; delete cache["dashboard.json"];  // the other pills
  if (typeof renderHeader === "function") renderHeader();
  // The global tape is chrome too, and it lives outside #view — so on the pages that show it, its
  // numbers froze at whatever the last full page render fetched. Patch it on the same cadence as
  // the pills (showGlobalStrip patches in place and flashes what moved; it never rebuilds).
  const gh = $("gstripHost");
  if (document.body.dataset.strip !== "off" && gh && gh.dataset.keys) {
    delete cache["global.json"];
    j("global.json").then(gl => { if (gl) showGlobalStrip(gl); }).catch(() => {});
  }
}, 60000);

/* ---------- ticker search ---------- */
let searchIndex = null;
async function loadSearchIndex() {
  if (searchIndex) return searchIndex;
  // The universe is the whole KSE All Share (554), but that constituent list includes PSX board
  // counters that are not tradeable companies (…XD ex-dividend, …XB ex-bonus, …NC non-compliant)
  // and return no price series. coverage.json lists what actually has data — searching should find
  // every real listed company and nothing that would dead-end on an empty page.
  const [uni, cov] = await Promise.all([j("universe.json"), j("coverage.json")]);
  const bars = cov?.bars || null;
  searchIndex = Object.entries(uni?.symbols || {})
    .filter(([s]) => !bars || bars[s])          // no coverage file yet -> fail open, show everything
    .map(([s, v]) => ({ s, name: (v.name || "").toLowerCase(), disp: v.name || "" }));
  return searchIndex;
}

/* ---------- themed ticker combobox: replaces the native <datalist>, which browsers render
   unstyled (the raw grey popup). One delegated instance serves every input with class "combo";
   it filters the universe, is keyboard-navigable, and matches the terminal's hard-cornered look. */
let _comboEl = null, _comboInput = null, _comboIdx = -1;
function _comboClose() { if (_comboEl) { _comboEl.remove(); _comboEl = null; _comboInput = null; _comboIdx = -1; } }
async function _comboOpen(input) {
  const idx = await loadSearchIndex();
  _comboInput = input;
  if (!_comboEl) { _comboEl = document.createElement("div"); _comboEl.className = "combo-pop"; document.body.appendChild(_comboEl); }
  _comboRender(idx, input.value);
  _comboPosition();
}
function _comboPosition() {
  if (!_comboEl || !_comboInput) return;
  const r = _comboInput.getBoundingClientRect();
  _comboEl.style.left = r.left + window.scrollX + "px";
  _comboEl.style.top = r.bottom + window.scrollY + "px";
  _comboEl.style.width = Math.max(180, r.width) + "px";
}
function _comboRender(idx, q) {
  q = (q || "").trim().toUpperCase();
  const hits = (q
    ? idx.filter(x => x.s.startsWith(q)).concat(idx.filter(x => !x.s.startsWith(q) && (x.s.includes(q) || x.name.includes(q.toLowerCase()))))
    : idx.slice()).slice(0, 40);
  _comboIdx = -1;
  _comboEl.innerHTML = hits.length
    ? hits.map((h, i) => `<div class="combo-opt" data-sym="${h.s}" data-i="${i}"><b>${h.s}</b><span>${esc((h.disp || "").slice(0, 30))}</span></div>`).join("")
    : `<div class="combo-empty">No match for "${esc(q)}"</div>`;
}
function _comboPick(sym) {
  if (_comboInput) {
    _comboInput.value = sym;
    _comboInput.dispatchEvent(new Event("input", { bubbles: true }));
    const btn = _comboInput.closest(".sb-add, .ph-form, .ph-row, .rq-form")?.querySelector(".note-save");
    _comboInput.focus();
  }
  _comboClose();
}
document.addEventListener("focusin", e => { const el = e.target.closest("input.combo"); if (el) _comboOpen(el); });
document.addEventListener("input", e => { if (e.target.closest("input.combo") && _comboEl) loadSearchIndex().then(idx => _comboRender(idx, e.target.value)); });
document.addEventListener("click", e => {
  const opt = e.target.closest(".combo-opt");
  if (opt) { e.preventDefault(); _comboPick(opt.dataset.sym); return; }
  if (!e.target.closest("input.combo") && !e.target.closest(".combo-pop")) _comboClose();
});
document.addEventListener("keydown", e => {
  if (!_comboEl || !_comboInput || document.activeElement !== _comboInput) return;
  const opts = [..._comboEl.querySelectorAll(".combo-opt")];
  if (!opts.length) return;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    _comboIdx = (_comboIdx + (e.key === "ArrowDown" ? 1 : -1) + opts.length) % opts.length;
    opts.forEach((o, i) => o.classList.toggle("on", i === _comboIdx));
    opts[_comboIdx].scrollIntoView({ block: "nearest" });
  } else if (e.key === "Enter" && _comboIdx >= 0) {
    e.preventDefault(); _comboPick(opts[_comboIdx].dataset.sym);
  } else if (e.key === "Escape") { _comboClose(); }
});
// passive: _comboPosition only reads a rect and writes styles on the popup — it never
// preventDefault()s, so telling the browser that up front keeps scrolling off the main thread.
window.addEventListener("scroll", _comboPosition, { capture: true, passive: true });
window.addEventListener("resize", _comboPosition);
function openSearch() {
  const box = $("searchbox"); box.hidden = false;
  const inp = $("searchinput"); inp.value = ""; $("searchresults").innerHTML = "";
  loadSearchIndex(); setTimeout(() => inp.focus(), 30);
  pushOverlay(closeSearch, box);
}
function closeSearch() { const b = $("searchbox"); if (b && !b.hidden) { b.hidden = true; popOverlay(closeSearch); } }
function goTicker(sym) { closeSearch(); navigate("/ticker/" + encodeURIComponent(sym)); }
async function runSearch(q) {
  q = q.trim().toUpperCase();
  const res = $("searchresults");
  if (!q) { res.innerHTML = ""; return; }
  const idx = await loadSearchIndex();
  const hits = idx.filter(x => x.s.startsWith(q)).concat(
    idx.filter(x => !x.s.startsWith(q) && (x.s.includes(q) || x.name.includes(q.toLowerCase())))
  ).slice(0, 12);
  res.innerHTML = hits.length
    ? hits.map(h => `<div class="searchitem" data-sym="${h.s}"><b>${h.s}</b><span>${esc(h.name)}</span></div>`).join("")
    : `<div class="searchitem" style="opacity:.6">No match for "${esc(q)}"</div>`;
}
// header exists at load (script is at end of body), so wire immediately:
$("searchbtn")?.addEventListener("click", openSearch);
$("searchinput")?.addEventListener("input", e => runSearch(e.target.value));
$("searchinput")?.addEventListener("keydown", e => {
  if (e.key === "Escape") closeSearch();
  if (e.key === "Enter") { const first = document.querySelector(".searchitem[data-sym]"); if (first) goTicker(first.dataset.sym); }
});
$("searchresults")?.addEventListener("click", e => {
  const it = e.target.closest(".searchitem[data-sym]"); if (it) goTicker(it.dataset.sym);
});
$("searchbox")?.addEventListener("click", e => { if (e.target.id === "searchbox") closeSearch(); });
$("searchclose")?.addEventListener("click", closeSearch);
// closing whenever the route changes (e.g. after picking a ticker) and on Escape anywhere
window.addEventListener("henneth:navigate", closeSearch);
window.addEventListener("popstate", closeSearch);
document.addEventListener("keydown", e => {
  if (e.key === "Escape") closeSearch();
  if (e.key === "/" && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) { e.preventDefault(); openSearch(); }
});

/* ---------- sidebar: collapse (desktop) + drawer (mobile) ---------- */
const shell = $("shell");
if (shell && localStorage.getItem("sideCollapsed") === "1") shell.classList.add("collapsed");
/* The label has to track the state, not the artwork. Collapsed, the button shows the desk mark
   and only reveals the chevron on hover — a screen-reader user gets neither, so "Collapse menu"
   on an already-collapsed rail would be simply wrong. */
function syncSideToggleLabel() {
  const b = $("sideToggle");
  if (!b || !shell) return;
  const label = shell.classList.contains("collapsed") ? "Expand menu" : "Collapse menu";
  b.setAttribute("aria-label", label);
  b.setAttribute("title", label);
  b.setAttribute("aria-expanded", shell.classList.contains("collapsed") ? "false" : "true");
}
syncSideToggleLabel();   // the collapsed class is restored from localStorage above, before this runs
$("sideToggle")?.addEventListener("click", () => {
  const c = shell.classList.toggle("collapsed");
  localStorage.setItem("sideCollapsed", c ? "1" : "0");
  syncSideToggleLabel();
});
// noInert: the sidebar lives inside #shell, so inerting the shell here would also inert the
// drawer (and unreachable-ize #sideOpen, its own trigger). Trap focus in the sidebar only.
const openDrawer = () => { shell.classList.add("drawer"); pushOverlay(closeDrawer, $("sidebar"), { noInert: true }); };
const closeDrawer = () => { if (shell.classList.contains("drawer")) { shell.classList.remove("drawer"); popOverlay(closeDrawer); } };
$("sideOpen")?.addEventListener("click", openDrawer);
$("sideBackdrop")?.addEventListener("click", closeDrawer);
// close the mobile drawer after navigating or on Escape
window.addEventListener("henneth:navigate", closeDrawer);
window.addEventListener("popstate", closeDrawer);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });

/* drag-to-resize the sidebar (desktop, expanded only), clamped + persisted */
const SIDE_MIN = 168, SIDE_MAX = 380;
if (shell) {
  const savedW = parseInt(localStorage.getItem("sideW"), 10);
  if (savedW >= SIDE_MIN && savedW <= SIDE_MAX) shell.style.setProperty("--side-w", savedW + "px");
  // Transitions stay off until one frame after the collapsed/width restore above — otherwise a
  // returning visitor watches the sidebar animate from the stylesheet default to their saved
  // state on every load. CSS: .shell:not(.side-ready) .sidebar{transition:none}.
  // rAF is throttled to zero in hidden tabs, so back it with a timer — either way the class
  // lands after the restore and before any user interaction.
  const sideReady = () => shell.classList.add("side-ready");
  requestAnimationFrame(sideReady);
  setTimeout(sideReady, 300);
}
const sideResize = $("sideResize");
if (sideResize) {
  sideResize.style.touchAction = "none";
  let dragging = false, dragId = null;
  sideResize.addEventListener("pointerdown", e => {
    if (shell.classList.contains("collapsed") || (e.pointerType === "mouse" && e.button !== 0)) return;
    dragging = true;
    dragId = e.pointerId;
    sideResize.setPointerCapture(e.pointerId);
    shell.classList.add("resizing");
    e.preventDefault();
  });
  sideResize.addEventListener("pointermove", e => {
    if (!dragging || e.pointerId !== dragId) return;
    const w = Math.min(SIDE_MAX, Math.max(SIDE_MIN, e.clientX));
    shell.style.setProperty("--side-w", w + "px");
  });
  const endSideResize = e => {
    if (!dragging || e.pointerId !== dragId) return;
    dragging = false;
    dragId = null;
    if (sideResize.hasPointerCapture(e.pointerId)) sideResize.releasePointerCapture(e.pointerId);
    shell.classList.remove("resizing");
    const w = parseInt(getComputedStyle(shell).getPropertyValue("--side-w"), 10);
    if (w) localStorage.setItem("sideW", w);
  };
  sideResize.addEventListener("pointerup", endSideResize);
  sideResize.addEventListener("pointercancel", endSideResize);
}


/* ================= ACCOUNTS + ONBOARDING (merged from auth.js: the deploy workflow only ships app.js) ================= */
/* Henneth Desk — accounts + onboarding (Supabase Auth).
   Security model: the publishable key below is CLIENT-SAFE by design — all authority
   lives server-side in Row-Level Security (a user can only touch their own profiles row).
   Passwords are never handled by our code; Supabase Auth does hashing/JWT/rate limits.
   The shared research data stays public; only the per-user layer needs an account. */

const SB_URL = "https://qteoncckohuoatbjjykb.supabase.co";
const SB_KEY = "sb_publishable_aQu8P4yrAY7l8Y0AcLth5g_Z3VceUnw";
const sb = window.supabase ? window.supabase.createClient(SB_URL, SB_KEY, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
}) : null;

/* ==========================================================================================
   BOT PROTECTION — Cloudflare Turnstile on the auth endpoints.

   Why it matters more than it looks: an unprotected signup endpoint lets a bot POST thousands of
   addresses, and every one triggers a confirmation email. That burns the Supabase email quota and,
   worse, gets the sending domain flagged as a spam source — which then silently kills delivery of
   the real confirmation emails to real users. Paid traffic pointed at an unprotected form is
   exactly the condition that invites it.

   ────────────────────────────────────────────────────────────────────────────────────────────
   TO SWITCH IT ON (two steps, in THIS ORDER — reversing them breaks signup for everyone):

     1. Paste the Turnstile SITE key below and deploy. Nothing changes for users: the widget
        renders and sends a token, and Supabase ignores tokens while its own captcha setting is
        off. This is deliberately the safe half, and it can sit live for as long as you like.
     2. THEN enable it in Supabase → Authentication → Attack Protection → "Enable Captcha
        protection", provider "Turnstile", pasting the SECRET key there.

   Doing 2 before 1 means the server starts demanding a token the client is not yet sending, and
   every signup and sign-in fails until the deploy lands.

   Keys come from Cloudflare dashboard → Turnstile → Add site (free, unlimited). You get a SITE
   key (public — belongs here, safe to commit) and a SECRET key (server-side — belongs only in
   the Supabase dashboard, never in this file).
   ────────────────────────────────────────────────────────────────────────────────────────────

   Empty string = feature entirely inert: no script fetched, no widget, no token, and the auth
   calls below are byte-identical to what they were before this existed.

   This is the SITE key and it is PUBLIC by design — Turnstile embeds it in page source on every
   site that uses it, and it is useless without the secret half. The SECRET key lives only in the
   Supabase dashboard (Authentication → Attack Protection) and must never appear in this repo.
   Widget: Cloudflare → Turnstile → "Henneth Desk", Managed mode, hostnames desk.henneth.app +
   localhost. If the widget stops rendering, check the hostname list first — Turnstile silently
   refuses to render on a domain that is not on it. */
const CAPTCHA_SITE_KEY = "";  // DISABLED 2026-07-23: Turnstile was blocking real signups (mobile + privacy blockers could not produce a token; see PostHog auth funnel). MUST stay blank UNLESS Supabase Auth → Attack Protection → Captcha is also re-enabled first, or every auth call fails "captcha required". Old site key: 0x4AAAAAAD6UK0K_7bHULZry

let _tsLoading = null;
let _tsWidget = null;
let _tsToken = null;

const captchaOn = () => !!CAPTCHA_SITE_KEY;

function loadTurnstile() {
  if (!captchaOn()) return Promise.resolve(false);
  if (window.turnstile) return Promise.resolve(true);
  if (_tsLoading) return _tsLoading;
  _tsLoading = new Promise(resolve => {
    const s = document.createElement("script");
    s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    s.async = true; s.defer = true;
    s.onload = () => resolve(true);
    // Blocked by an extension or offline. Resolve false rather than hanging: the SERVER is the
    // real gate, so a client that cannot produce a token simply gets a clear rejection from
    // Supabase instead of a form that never submits.
    s.onerror = () => resolve(false);
    document.head.appendChild(s);
  });
  return _tsLoading;
}

/* Renders into #capBox if the auth form is showing one. Managed mode usually solves silently;
   the callback caches the token so submit does not have to wait for it. */
async function mountCaptcha() {
  if (!captchaOn()) return;
  const host = document.getElementById("capBox");
  if (!host) return;
  const ok = await loadTurnstile();
  if (!ok || !window.turnstile) return;
  _tsToken = null;
  _tsWidget = window.turnstile.render(host, {
    sitekey: CAPTCHA_SITE_KEY,
    callback: t => { _tsToken = t; },
    "expired-callback": () => { _tsToken = null; },
    "error-callback": () => { _tsToken = null; },
    theme: "light",
  });
}

/* A Turnstile token is SINGLE USE. After any failed submit the widget must be reset or the next
   attempt reuses a spent token and fails with a confusing "captcha verification failed". */
function resetCaptcha() {
  _tsToken = null;
  try { if (window.turnstile && _tsWidget !== null) window.turnstile.reset(_tsWidget); } catch {}
}

/* Returns the token, waiting briefly if the challenge is still solving. `undefined` (not null or
   "") is returned when the feature is off, because that is what makes the options object below
   collapse to exactly the call we made before captcha existed. */
async function captchaToken() {
  if (!captchaOn()) return undefined;
  if (_tsToken) return _tsToken;
  const ok = await loadTurnstile();
  if (!ok || !window.turnstile) return undefined;
  for (let i = 0; i < 25 && !_tsToken; i++) {          // up to ~5s
    await new Promise(r => setTimeout(r, 200));
    try { const t = window.turnstile.getResponse(_tsWidget); if (t) _tsToken = t; } catch {}
  }
  return _tsToken || undefined;
}

let me = null;        // auth user
let myProfile = null; // profiles row
let profileRealtimeChannel = null;
let _onboardShownTracked = false;
/* The mounted research terminal (auth-terminal.js), or null when no auth surface is up.
   _authHold keeps it mounted through onboarding: a successful signup fires SIGNED_IN, whose
   handler calls closeAuth(), and without the hold that tears the onboarding shell down the
   instant it appears. */
let _authTerm = null;
let _authHold = false;

/* ---------- tiny helpers ---------- */
const el = (h) => { const d = document.createElement("div"); d.innerHTML = h.trim(); return d.firstChild; };
/* Two auth surfaces exist: the research terminal, and the plain panel openRecovery() builds.
   Messages go to whichever is actually on screen. */
const authMsg = (t, bad) => {
  if (_authTerm) { _authTerm.setMsg(t, bad); return; }
  const m = document.getElementById("authmsg");
  if (m) { m.textContent = t || ""; m.className = "authmsg" + (bad ? " bad" : ""); }
};

/* ---------- colour scheme control (system / light / dark) ----------
   Contract: localStorage "deskScheme" is "light", "dark", or ABSENT (= follow OS).
   A single attribute write on <html>, never on document.body, so it never trips the
   enhancement MutationObserver (BLINK LAW — that observer watches document.body only). */
function deskScheme() {
  try { const v = localStorage.getItem("deskScheme"); return (v === "dark" || v === "light") ? v : "system"; }
  catch (e) { return "system"; }
}
function applyDeskScheme(choice) {
  try {
    if (choice === "dark" || choice === "light") localStorage.setItem("deskScheme", choice);
    else localStorage.removeItem("deskScheme");
  } catch (e) {}
  // Kill transitions for exactly one frame (see palette.css) so the whole palette lands in a
  // single paint instead of ~40 frames of crossfade through two backdrop-filtered panes.
  const root = document.documentElement;
  root.setAttribute("data-scheme-switching", "");
  if (choice === "dark" || choice === "light") root.setAttribute("data-scheme", choice);
  else root.removeAttribute("data-scheme");
  const clear = () => root.removeAttribute("data-scheme-switching");
  // rAF gets us the frame after the repaint; the timeout is the guard, because rAF never fires in
  // a background tab and stranding the attribute would leave the desk permanently transition-less.
  requestAnimationFrame(() => requestAnimationFrame(clear));
  setTimeout(clear, 150);
}
/* The topbar control. One button that cycles System → Light → Dark, sitting next to the
   search button so the scheme is never buried inside a menu (and is reachable signed-out). */
const SCHEME_CYCLE = { system: "light", light: "dark", dark: "system" };
const SCHEME_ICON = {
  system: '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 010 16z" fill="currentColor" stroke="none"/>',
  light: '<circle cx="12" cy="12" r="4.2"/><path d="M12 2v2.4M12 19.6V22M2 12h2.4M19.6 12H22M4.9 4.9l1.7 1.7M17.4 17.4l1.7 1.7M19.1 4.9l-1.7 1.7M6.6 17.4l-1.7 1.7"/>',
  dark: '<path d="M20 14.2A8.2 8.2 0 019.8 4 8.4 8.4 0 1020 14.2z"/>',
};
const SCHEME_LABEL = { system: "System", light: "Light", dark: "Dark" };
function renderSchemeBtn() {
  const btn = document.getElementById("schemeBtn");
  if (!btn) return;
  const cur = deskScheme();
  const next = SCHEME_CYCLE[cur];
  btn.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${SCHEME_ICON[cur]}</svg>`;
  btn.title = `Theme: ${SCHEME_LABEL[cur]} — click for ${SCHEME_LABEL[next]}`;
  btn.setAttribute("aria-label", btn.title);
  btn.setAttribute("data-scheme-state", cur);
}
document.getElementById("schemeBtn")?.addEventListener("click", () => {
  applyDeskScheme(SCHEME_CYCLE[deskScheme()]);
  renderSchemeBtn();
});
renderSchemeBtn();

/* ---------- account button in the topbar ---------- */
function renderAccountButton() {
  const holder = document.getElementById("acctSlot");
  if (!holder) return;
  if (me) {
    const initial = (me.email || "?")[0].toUpperCase();
    const plan = PLANS[planOf()];
    // account menu, in the shape people already know: identity at the top, the plan you're on
    // stated plainly under it, then actions.
    holder.innerHTML = `<button class="acct-btn" id="acctBtn" title="${me.email}">${initial}</button>
      <div class="acct-menu" id="acctMenu" hidden>
        <div class="acct-id"><span class="acct-av">${initial}</span><div><div class="acct-email">${me.email}</div>
          <div class="acct-plan">${esc(plan.label)} plan</div></div></div>
        <div class="acct-sep"></div>
        <button id="acctPlans"><span>Plans</span><span class="acct-chip ${planOf() === "free" ? "" : "on"}">${esc(plan.label)}</span></button>
        <button id="acctSettings">Settings</button>
        <button id="acctMode">${deskMode() === "learn" ? "Switch to the Pro desk" : "Switch to the Learner desk"}</button>
        <button id="acctTour">Show me around</button>
        <div class="acct-sep"></div>
        <button id="acctOut">Sign out</button>
      </div>`;
    const menu = document.getElementById("acctMenu");
    document.getElementById("acctBtn").onclick = (e) => { e.stopPropagation(); menu.hidden ? openAcct() : closeAcct(); };
    document.getElementById("acctOut").onclick = async () => { await sb.auth.signOut(); location.reload(); };
    document.getElementById("acctSettings").onclick = () => { menu.hidden = true; navigate("/settings"); };
    document.getElementById("acctPlans").onclick = () => { menu.hidden = true; navigate("/plans"); };
    document.getElementById("acctMode").onclick = () => { menu.hidden = true; setDeskMode(deskMode() === "learn" ? "pro" : "learn"); };
    document.getElementById("acctTour").onclick = () => { menu.hidden = true; startTour(); };
  } else {
    holder.innerHTML = `<button class="acct-signin" id="acctIn">Sign in</button>`;
    document.getElementById("acctIn").onclick = () => openAuth("signin");
  }
}

// Open/close the account menu through the shared overlay-history stack so the phone's Back
// gesture closes the menu instead of leaving the desk (mirrors openDrawer/closeDrawer above).
// Single stable function references so pushOverlay/popOverlay always match up.
function openAcct() {
  const m = document.getElementById("acctMenu");
  if (!m || !m.hidden) return;
  m.hidden = false;
  pushOverlay(closeAcct);
}
function closeAcct() {
  const m = document.getElementById("acctMenu");
  if (!m || m.hidden) return;
  m.hidden = true;
  popOverlay(closeAcct);
}

// Close the account menu on any outside click / Escape / navigation. Registered ONCE,
// in the CAPTURE phase so a stopPropagation() elsewhere in the SPA can't keep it stuck open.
if (!window.__acctMenuGuard) {
  window.__acctMenuGuard = true;
  document.addEventListener("click", (e) => {
    const m = document.getElementById("acctMenu"), holder = document.getElementById("acctSlot");
    if (m && !m.hidden && holder && !holder.contains(e.target)) closeAcct();
  }, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeAcct(); });
  window.addEventListener("henneth:navigate", closeAcct);
}

/* ---------- auth surface (sign in / create account) ----------
   The screen itself is auth-terminal.js: markup, boot sequence, tab switching, the four-question
   onboarding and the personalized Today panel. This file owns Supabase, the validation copy, the
   tracking and the persistence, and reaches the terminal only through the handles mount() returns.
   One design and one onboarding — the desk carried two of each, and they disagreed. */
function openAuth(mode) {
  closeAuth();
  /* The starting tab is passed INTO mount(); switching after mount would collide with the boot
     timeline, which is animating the same nodes for its first four seconds. */
  const t = window.HennethAuthTerminal.mount(mode === "signup" ? "create" : "signin");
  _authTerm = t;
  _authHold = false;
  // No-op while CAPTCHA_SITE_KEY is blank. Fired here rather than on submit so the challenge has
  // the whole time the user spends typing to solve itself — by submit there is nothing to wait for.
  mountCaptcha();

  t.hooks.onTabChange = () => { t.clearErrors(); t.setMsg(""); };

  t.hooks.onForgot = async (email) => {
    if (!email) return t.setErr("email", "Enter your email first, then press reset.");
    t.setMsg("Sending reset link…");
    // Password reset is captcha-protected server-side too — it sends mail, so it is the same
    // spam vector as signup and Supabase enforces the token on it as well.
    const tok = await captchaToken();
    const { error } = await sb.auth.resetPasswordForEmail(email, {
      redirectTo: location.origin + location.pathname,
      ...(tok ? { captchaToken: tok } : {}),
    });
    if (error) resetCaptcha();
    t.setMsg(error ? friendlyAuthError(error) : "Reset link sent — check your email.", !!error);
  };

  /* `tab` is the terminal's LIVE tab, not openAuth's captured `mode` — the user can switch tabs
     inside the terminal without this function running again. */
  t.hooks.onSubmit = async (tab) => {
    const signup = tab === "create";
    const name = signup ? t.els.nameInput.value.trim() : "";
    const email = t.els.emailInput.value.trim();
    const pw = t.els.pwInput.value;

    // validate before spending a network round trip, and point at the offending field
    let bad = "";
    t.clearErrors();
    if (signup && !name) { t.setErr("name", "Enter your name."); bad = bad || "name"; }
    if (!email) { t.setErr("email", "Enter your email."); bad = bad || "email"; }
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { t.setErr("email", "That doesn't look like an email address."); bad = bad || "email"; }
    if (!pw) { t.setErr("pw", "Enter your password."); bad = bad || "password"; }
    /* 10, matching the server floor set in Supabase (Auth → Sign In / Providers → Email →
       Minimum password length). Keep the two in step: this check is only a courtesy that saves a
       round trip and points at the right field — the server is the actual gate, because anyone
       can POST to the Supabase auth API directly and never load this form.
       Length rather than composition rules is deliberate, per NIST SP 800-63B: forcing a symbol
       and a digit reliably produces "P@ssw0rd1", while length is what actually resists cracking. */
    else if (signup && pw.length < 10) { t.setErr("pw", "Passwords need at least 10 characters. A short phrase works well."); bad = bad || "password"; }
    /* Client-side validation rejections are tracked, because they are friction the desk CHOSE.
       The 10-character floor and the captcha are both deliberate, both correct, and both cost
       some proportion of signups — a proportion nobody could previously measure. `field` says
       which rule bit, never what was typed. */
    if (bad) {
      t.setMsg("");
      track("auth_validation_failed", { mode: signup ? "signup" : "signin", field: bad });
      return;
    }

    t.setBusy(true);
    t.setMsg(signup ? "Creating your account…" : "Signing in…");
    track(signup ? "signup_started" : "signin_started", { plan_intent: planIntent() || "none" });
    try {
      /* `undefined` when captcha is off, which makes `options` collapse to the exact call this
         was before bot protection existed — no behaviour change while the key is blank. */
      const captchaTok = await captchaToken();
      const opts = captchaTok ? { captchaToken: captchaTok } : undefined;
      if (signup) {
        /* Held BEFORE the await: a successful signUp fires SIGNED_IN, whose handler calls
           closeAuth(), and without the hold that tears down the terminal at the exact moment
           onboarding is supposed to start inside it. */
        _authHold = true;
        const { data, error } = await sb.auth.signUp({ email, password: pw, options: { ...(opts || {}), data: { full_name: name } } });
        if (error) throw error;
        /* Two DIFFERENT successes, and conflating them would flatter the numbers badly. With
           email confirmation on, no session comes back — the account exists but the person is
           not in yet, and whether they return from that email is the real question. Counting
           this as a completed signup would report a conversion rate the desk does not have. */
        if (!data.session) {
          _authHold = false;
          track("signup_pending_confirmation");
          t.setMsg("Almost there — we sent a confirmation link to " + email + ". Click it to activate your account.");
          return;
        }
        track("signup_completed", { plan_intent: planIntent() || "none" });
        t.setMsg("");
        t.startOnboarding();   // straight into the four questions, in the same screen
        return;
      }
      const { error } = await sb.auth.signInWithPassword({ email, password: pw, options: opts });
      if (error) throw error;
      track("signin_completed");
      closeAuth();
    } catch (err) {
      _authHold = false;
      // A Turnstile token is spent on use; without this reset the retry sends a used token and
      // fails with "captcha verification failed" no matter what the user types.
      resetCaptcha();
      /* The REASON is the point of this event. "captcha verification failed" repeating means the
         bot protection is eating real people; "User already registered" means they want the
         sign-in tab and cannot find it. Those need opposite fixes, and without the reason they
         look identical in the funnel. Supabase's own message is used rather than the friendly
         rewrite, since the rewrite is tuned for humans and would blur the categories. */
      track(signup ? "signup_failed" : "signin_failed", { reason: String((err && err.message) || err).slice(0, 80) });
      t.setMsg(friendlyAuthError(err), true);
    } finally { t.setBusy(false); }
  };

  t.hooks.onOnboardingDone = (answers, how) => applyOnboarding(answers, how);
  t.hooks.onEnterDesk = () => { _authHold = false; closeAuth(); route(true); };
  return t;
}

/* Where the four answers live. Presentation only — Today's ordering and language read this — so
   localStorage is the honest home for it: `profiles` has no column for these, and inventing one
   client-side would silently drop them on the next device. */
const DESK_PROFILE_KEY = "henneth-desk-profile";
function deskProfile() {
  try { return JSON.parse(localStorage.getItem(DESK_PROFILE_KEY) || "null"); } catch (e) { return null; }
}

/* The single exit from onboarding, whichever way it ended.
   `how`: 'confirmed' (the preview was accepted) · 'saved' (finish later) · 'blank' (start clean) ·
   'skipped'. Only 'confirmed' applies anything — "save and continue later" has not been confirmed
   yet, and applying it would configure a desk the user never agreed to. */
async function applyOnboarding(answers, how) {
  const a = answers || {};
  const radar = a.radar || {};
  track("onboard_done", { how, goal: a.goal || "", lens: a.lens || "", horizon: a.horizon || "", radar_source: radar.source || "" });
  if (how === "blank") { localStorage.removeItem(DESK_PROFILE_KEY); return; }
  if (how !== "confirmed") return;

  localStorage.setItem(DESK_PROFILE_KEY, JSON.stringify({
    goal: a.goal || "", lens: a.lens || "", horizon: a.horizon || "",
    radar_source: radar.source || "", saved_at: new Date().toISOString(),
  }));

  if (!me || !_authTerm) return;
  /* The sector → symbol map lives in the terminal, so the resolved list comes from there rather
     than being duplicated here and drifting. */
  const picks = _authTerm.radarSymbols();
  if (!picks.length) return;
  /* The ticker box takes free text, so the universe is the gate — an unknown symbol would sit on
     the watchlist forever rendering as a dead row. */
  const uni = await j("universe.json");
  const cur = watchlist();
  const add = picks.filter(s => uni?.symbols?.[s] && !cur.includes(s));
  if (!add.length) return;
  /* APPENDED, never assigned, and in one write rather than one per symbol: a returning user who
     redoes setup must not lose the watchlist they already had. */
  if (await saveProfile({ watchlist: [...cur, ...add] })) return;
  track("onboard_radar_saved", { count: add.length });
  await markActivated("watchlist");
}

/* Today's way into the SAME onboarding, for anyone who skipped it at signup or is mid-draft. */
function onboardCardHtml() {
  const resuming = !!localStorage.getItem("henneth-onboarding-draft");
  return `<div class="card onboard-prompt">
    <div class="onboard-kicker">Desk setup</div>
    <b class="onboard-title">${resuming ? "Pick up where you left off." : "Let's prepare your desk around how you actually invest."}</b>
    <span class="onboard-copy">Four quick choices tune your daily brief, radar, screeners and lessons. You can change anything later.</span>
    <div class="onboard-actions">
      <button class="btn" onclick="openOnboarding()">${resuming ? "Resume setup" : "Prepare my desk"}</button>
      <button class="btn-ghost" onclick="dismissOnboardPrompt()">Not now</button>
    </div>
  </div>`;
}
function openOnboarding() {
  track("onboard_prompt_opened");
  // An explicit "prepare my desk" overrides an earlier skip, which would otherwise send the
  // terminal straight past the questions to its Today panel.
  localStorage.removeItem("henneth-onboarding-skipped");
  const t = openAuth("signin");
  _authHold = true;                 // nothing may close this surface until the user leaves it
  t.startOnboarding();
}
function dismissOnboardPrompt() {
  track("onboard_prompt_dismissed");
  document.querySelector(".onboard-prompt")?.remove();
}

/* Supabase's raw errors are accurate and unhelpful ("Invalid login credentials" tells a user
   nothing about which half was wrong, and "User already registered" reads like an accusation).
   Translate the ones people actually hit; pass anything unrecognised through unchanged rather
   than swallowing a real error behind a generic apology. */
function friendlyAuthError(err) {
  const m = (err && (err.message || err.error_description)) || String(err || "");
  const s = m.toLowerCase();
  if (s.includes("invalid login credentials")) return "That email and password don't match. Check the password, or use “Forgot password?” below.";
  if (s.includes("email not confirmed")) return "This account isn't activated yet — click the confirmation link we emailed you, then sign in.";
  if (s.includes("user already registered") || s.includes("already been registered")) return "There's already an account with this email. Switch to “Sign in”, or reset the password if you've forgotten it.";
  if (s.includes("password should be at least")) return "Passwords need at least 10 characters. A short phrase works well.";
  /* Email-send quota (Supabase over_email_send_rate_limit). This is the SERVER's cap on how many
     confirmation emails it will send per hour — NOT the user retrying too fast — so "wait a minute"
     is wrong and blames them for our limit. Say what's true: it's on us, their details are fine. */
  if (s.includes("email rate limit") || s.includes("over_email_send") || s.includes("email send rate")) {
    return "We're sending confirmation emails faster than our mail service allows right now. Your details are fine — please try again in a few minutes, and if it keeps happening, email hello@henneth.app.";
  }
  if (s.includes("rate limit") || s.includes("too many")) return "Too many attempts just now. Wait a minute and try again.";
  /* Captcha failures. The second case is the one that matters in the wild: a privacy extension or
     a blocked challenges.cloudflare.com means the token never exists, and without naming that the
     user just sees a form that refuses them for no visible reason. */
  if (s.includes("captcha")) {
    return captchaOn()
      ? "The bot check didn't complete. If you use a privacy blocker, allow challenges.cloudflare.com and try again."
      : "The server is asking for a bot check this page can't provide yet. Please tell us at hello@henneth.app.";
  }
  if (s.includes("failed to fetch") || s.includes("networkerror")) return "Couldn't reach the server. Check your connection and try again.";
  if (s.includes("provider is not enabled")) return "Google sign-in isn't switched on for this site yet.";
  return m || "Something went wrong. Try again.";
}
function closeAuth() {
  /* The research terminal, when one is up. `_authHold` is what keeps it alive through onboarding:
     signup fires SIGNED_IN, whose handler calls closeAuth(), and the onboarding shell lives inside
     this same surface. */
  if (_authTerm) {
    if (_authHold) return;
    window.HennethAuthTerminal.unmount();
    _authTerm = null;
    return;
  }
  // The plain panel openRecovery() builds is a different surface and still closes the old way.
  const ov = document.getElementById("authbox");
  // Drop the id BEFORE animating out: the node now lives on for ~250ms, and openRecovery() calls
  // closeAuth() then immediately appends a fresh #authbox — two nodes sharing an id would make
  // every getElementById("authbox") resolve to the dying one.
  if (ov) { ov.removeAttribute("id"); closeAnimated(ov, ".authpanel"); }
}


/* ---------- password recovery (arrives via email link) ---------- */
function openRecovery() {
  closeAuth();
  const box = el(`<div class="authbox" id="authbox"><div class="authpanel">
    <div class="auth-head"><b>Set a new password</b></div>
    <form id="recform"><label>New password<input type="password" id="recPw" inputmode="text" enterkeyhint="go" minlength="8" required autocomplete="new-password"></label>
    <button type="submit" class="auth-go">Save password</button></form>
    <div class="authmsg" id="authmsg"></div></div></div>`);
  document.body.appendChild(box);
  document.getElementById("recform").onsubmit = async (e) => {
    e.preventDefault();
    const { error } = await sb.auth.updateUser({ password: document.getElementById("recPw").value });
    authMsg(error ? error.message : "Password updated — you're signed in.", !!error);
    if (!error) setTimeout(closeAuth, 1200);
  };
}

/* ---------- profile ---------- */
async function loadProfile() {
  if (!me) return null;
  const { data } = await sb.from("profiles").select("*").eq("id", me.id).maybeSingle();
  myProfile = data;
  return data;
}
async function saveProfile(patch) {
  if (!me) return "not_signed_in";   // distinguishable from success (falsy) — never silently equated with it
  patch.id = me.id;
  const { error } = await sb.from("profiles").upsert(patch);
  if (!error) myProfile = { ...(myProfile || {}), ...patch };
  return error;
}

function stopProfileRealtime() {
  if (profileRealtimeChannel && sb) {
    sb.removeChannel(profileRealtimeChannel);
    profileRealtimeChannel = null;
  }
}

function refreshVisibleTickerNote(notes) {
  const match = (routeHash() || "").match(/^#\/ticker\/([^?]+)/);
  if (!match) return;
  let sym = "";
  try { sym = decodeURIComponent(match[1]).toUpperCase(); } catch {}
  const ta = document.getElementById("tknote");
  if (!ta || !sym || document.activeElement === ta) return;
  ta.value = (notes || {})[sym] || "";
  const status = document.getElementById("tknote-status");
  if (status) status.textContent = "Updated from your account";
  setTimeout(() => {
    if (status && status.isConnected && status.textContent === "Updated from your account") status.textContent = "";
  }, 2200);
}

function startProfileRealtime(userId) {
  stopProfileRealtime();
  if (!sb || !userId) return;
  profileRealtimeChannel = sb
    .channel("profile-notes-" + userId)
    .on("postgres_changes", {
      event: "UPDATE",
      schema: "public",
      table: "profiles",
      filter: "id=eq." + userId
    }, (payload) => {
      const next = payload && payload.new;
      if (!next) return;
      myProfile = { ...(myProfile || {}), ...next };
      refreshVisibleTickerNote(next.notes || {});
    })
    .subscribe((status) => {
      if (status === "CHANNEL_ERROR" || status === "TIMED_OUT") {
        console.warn("Profile live sync unavailable:", status);
      }
    });
}

// Activation event — the desk's one real-action-in-30-seconds metric. Server-authoritative:
// `saveProfile` can no longer write activated_at/activation_type (revoked from `authenticated`
// in docs/lifecycle_email.sql), so this goes through the write-once mark_activated(p_type) RPC.
// `coalesce` server-side means only the FIRST call across all four sites ever sticks; safe to
// call unconditionally on every qualifying action without checking myProfile first.
async function markActivated(kind) {
  if (!me) return;
  if (myProfile && myProfile.activated_at) return;   // local shortcut, RPC is the real guard
  const { error } = await sb.rpc("mark_activated", { p_type: kind });
  if (!error) {
    myProfile = { ...(myProfile || {}), activated_at: myProfile?.activated_at || new Date().toISOString(), activation_type: myProfile?.activation_type || kind };
    track("activated", { type: kind });
  }
}

/* ---------- watchlist (per-user, persisted to profiles.watchlist) ---------- */
function watchlist() { return (myProfile && myProfile.watchlist) || []; }
function isWatched(sym) { return watchlist().includes(sym); }

/* ---------- private per-ticker notes (persisted to profiles.notes, RLS-scoped) ---------- */
function noteFor(sym) { return ((myProfile && myProfile.notes) || {})[sym] || ""; }
async function saveTickerNote(sym) {
  const ta = document.getElementById("tknote"); if (!ta) return;
  const st = document.getElementById("tknote-status");
  if (!me) { if (st) st.textContent = "Signed out — sign in to save"; openAuth("signin"); return; }
  if (saveTickerNote._busy) return;
  saveTickerNote._busy = true;
  try {
    const notes = { ...((myProfile && myProfile.notes) || {}) };
    const v = ta.value.trim(); if (v) notes[sym] = v; else delete notes[sym];
    if (st) st.textContent = "Saving…";
    const err = await saveProfile({ notes });
    if (st) { st.textContent = err ? "Save failed — try again" : "Saved ✓"; setTimeout(() => { if (st.isConnected) st.textContent = ""; }, 2500); }
  } finally {
    saveTickerNote._busy = false;
  }
}
async function toggleWatch(sym, btn) {
  if (!me) { openAuth("signup"); return; }               // must be signed in to save
  const cur = new Set(watchlist());
  const adding = !cur.has(sym);
  cur.has(sym) ? cur.delete(sym) : cur.add(sym);
  const next = [...cur];
  if (btn) { btn.classList.toggle("on", cur.has(sym)); btn.disabled = true; }
  await saveProfile({ watchlist: next });
  if (btn) btn.disabled = false;
  track(adding ? "watchlist_add" : "watchlist_remove", { sym });
  if (adding) await markActivated("watchlist");           // add only — removing isn't the activation moment
  if (routeHash() === "#/watchlist") pageWatchlist();   // live-refresh the list view
  // The rail's Watchlist tab reads the same profile, so it goes stale the
  // moment a star is toggled from anywhere else on the desk.
  if (typeof window.refreshRail === "function") window.refreshRail();
}
// star button markup (used on ticker pages). onclick wired via delegation below.
function starBtn(sym) {
  return `<button class="starbtn ${isWatched(sym) ? "on" : ""}" data-watch="${esc(sym)}" title="${me ? "Add to / remove from your watchlist" : "Sign in to save to a watchlist"}" aria-label="watchlist">
    <svg viewBox="0 0 24 24"><path d="M12 3l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 18l-5.9 3 1.2-6.5L2.5 9.9 9.1 9z"/></svg></button>`;
}
// one delegated handler for every star on the page
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-watch]");
  if (b) {
    e.preventDefault(); e.stopPropagation();
    b.classList.add("star-press");
    const unpress = () => { b.classList.remove("star-press"); b.removeEventListener("animationend", unpress); };
    b.addEventListener("animationend", unpress);
    setTimeout(unpress, 200);
    toggleWatch(b.dataset.watch, b);
  }
  const bk = e.target.closest("[data-broker]");
  if (bk) { e.preventDefault(); e.stopPropagation(); toggleBroker(bk.dataset.broker); }
  const sd = e.target.closest("[data-sbdel]");
  if (sd) { e.preventDefault(); e.stopPropagation(); removeBoardTicker(sd.dataset.sbdel); }
  const ad = e.target.closest("[data-abdel]");
  if (ad) { e.preventDefault(); e.stopPropagation(); removeAstroTicker(ad.dataset.abdel); }
});

/* ---------- portfolio: read-only holdings tracker (profiles.portfolio, RLS-scoped) ---------- */
function portfolio() { return (myProfile && myProfile.portfolio) || []; }
async function addHolding(sym, shares, avgCost) {
  if (!me) { openAuth("signup"); return "sign in first"; }
  sym = (sym || "").toUpperCase().trim();
  shares = +shares; avgCost = +avgCost;
  if (!sym || !(shares > 0) || !(avgCost > 0)) return "enter a ticker, a share count and an average cost";
  const p = portfolio().filter(h => h.ticker !== sym);   // one row per ticker; re-adding overwrites
  p.push({ ticker: sym, shares, avg_cost: avgCost, added: new Date().toISOString().slice(0, 10) });
  const saveErr = await saveProfile({ portfolio: p });
  return saveErr ? "couldn't save — try again" : null;
}
async function removeHolding(sym) {
  await saveProfile({ portfolio: portfolio().filter(h => h.ticker !== (sym || "").toUpperCase()) });
  if (routeHash().startsWith("#/portfolio")) pagePortfolio();
}
async function submitHolding() {
  const t = document.getElementById("ph-tkr"), s = document.getElementById("ph-sh"), c = document.getElementById("ph-cost");
  const msg = document.getElementById("ph-msg");
  const err = await addHolding(t.value, s.value, c.value);
  if (err) { if (msg) { msg.textContent = err; msg.className = "sub dn"; } return; }
  t.value = s.value = c.value = "";
  pagePortfolio();
}

async function pagePortfolio() {
  const [quant, uni, live, divs, sectAll, fvAll, fsAll, deepDiv] = await Promise.all([
    j("quant.json"), j("universe.json"), j("live.json"), j("dividends.json"), j("sectors.json"),
    j("fairvalue.json"), j("fundamental_scores.json"), j("dividends_deep.json")]);
  if (!me) {
    $("view").innerHTML = `<div class="seg" style="margin-top:4px"><h2>Your portfolio</h2><div class="ln"></div></div>
      <div class="card"><div class="empty">Sign in to track your holdings — live value, profit/loss, weights and estimated dividend income. Private to you, read-only: the desk never trades. Research, not advice.<br><br>
      <button class="auth-go" style="max-width:220px" onclick="openAuth('signup')">Create a free account</button></div></div>`;
    return;
  }
  const q = quant?.tickers || {}, lv = live?.tickers || {}, names = uni?.symbols || {};
  const dHist = divs?.history || [];
  const rows = portfolio().map(h => {
    const qq = q[h.ticker];
    const px = lv[h.ticker]?.current ?? qq?.close ?? null;
    const mv = px != null ? px * h.shares : null;
    const cost = h.avg_cost * h.shares;
    const pl = mv != null ? mv - cost : null;
    const plPct = (mv != null && cost > 0) ? (mv / cost - 1) * 100 : null;
    const lastDiv = dHist.filter(d => d.symbol === h.ticker).sort((a, b) => (b.bc_start || "").localeCompare(a.bc_start || ""))[0];
    const annualDiv = lastDiv?.dividend_rs ? lastDiv.dividend_rs * h.shares : null;
    return { ...h, px, mv, cost, pl, plPct, annualDiv, name: names[h.ticker]?.name || "", known: !!qq,
      sector: (sectAll?.tickers?.[h.ticker] || {}).sector || null };
  });
  const totMv = rows.reduce((a, r) => a + (r.mv || 0), 0);
  const totCost = rows.reduce((a, r) => a + r.cost, 0);
  const totPl = totMv - totCost;
  const totPlPct = totCost > 0 ? (totMv / totCost - 1) * 100 : null;
  const totDiv = rows.reduce((a, r) => a + (r.annualDiv || 0), 0);
  const withW = rows.map(r => ({ ...r, w: totMv > 0 ? (r.mv || 0) / totMv * 100 : 0 })).sort((a, b) => b.w - a.w);
  const top = withW[0], top3 = withW.slice(0, 3).reduce((a, r) => a + r.w, 0);
  const concFlag = !withW.length ? "" :
    top.w >= 40 ? `Your largest position, <b>${esc(top.ticker)}</b>, is <b>${top.w.toFixed(0)}%</b> of the portfolio.`
      : top3 >= 65 && withW.length >= 3 ? `Your top 3 positions make up <b>${top3.toFixed(0)}%</b> of the portfolio.`
        : `Your largest position is <b>${top.w.toFixed(0)}%</b> — reasonably spread across ${withW.length} name${withW.length === 1 ? "" : "s"}.`;

  // ---- sector concentration: the exposure that actually bites. Two banks are one bet on rates,
  // however different their tickers look. (This used to say sectors weren't in the feed — they are now.)
  const secW = {};
  withW.forEach(r => { const k = r.sector || "Unclassified"; secW[k] = (secW[k] || 0) + r.w; });
  const secRows = Object.entries(secW).sort((a, b) => b[1] - a[1]);
  const topSec = secRows[0];
  const secFlag = !secRows.length ? "" :
    secRows.length === 1 ? `Every rupee you hold is in <b>${esc(topSec[0])}</b>. One sector shock moves your whole portfolio at once.`
      : topSec[1] >= 50 ? `<b>${topSec[1].toFixed(0)}%</b> of your portfolio sits in <b>${esc(topSec[0])}</b> — those names tend to rise and fall together, whatever their tickers say.`
        : `Your biggest sector is <b>${esc(topSec[0])}</b> at <b>${topSec[1].toFixed(0)}%</b>, spread across ${secRows.length} sectors.`;
  const sTile = (label, val, sub, k) => `<div class="sumtile"><span class="sk">${label}</span><b class="${k || ""}">${val}</b>${sub ? `<i>${sub}</i>` : ""}</div>`;

  /* ---- X-RAY: the desk's own risk rules, run over the user's actual mix. Framed as "how the
     desk's rules would read this", never "you should trim" — Rule 5 applies hardest here, because
     this is the one page where the user's own money is on screen. ---- */
  let xray = "";
  if (rows.length) {
    if (!hasFeature("xray")) {
      xray = planWall("Portfolio X-ray",
        "Your holdings measured against the desk's own published risk rules: weighted beta, blended valuation, expected dividend income from 18 years of real payout history, and how your concentration reads against the limits the desk imposes on itself.");
    } else {
      const FS = fsAll?.tickers || {}, FV = fvAll?.tickers || {};
      const wsum = withW.reduce((a, r) => a + (r.mv || 0), 0) || 1;
      // weighted beta — only over holdings that actually have a beta, and we say what we covered
      let bW = 0, bCov = 0, yW = 0, yCov = 0, gapW = 0, gapCov = 0;
      withW.forEach(r => {
        const m = FS[r.ticker]?.metrics || {}, fv = FV[r.ticker] || {};
        if (m.beta != null) { bW += m.beta * (r.mv || 0); bCov += (r.mv || 0); }
        if (m.div_yield != null) { yW += m.div_yield * (r.mv || 0); yCov += (r.mv || 0); }
        if (fv.mispricing_pct != null) { gapW += fv.mispricing_pct * (r.mv || 0); gapCov += (r.mv || 0); }
      });
      const beta = bCov ? bW / bCov : null, yld = yCov ? yW / yCov : null, gap = gapCov ? gapW / gapCov : null;
      // expected annual dividends from REAL trailing-12m payouts (deep history), not a forward promise
      const cutoff = new Date(Date.now() - 365 * 86400000).toISOString().slice(0, 10);
      let expDiv = 0, divCov = 0;
      withW.forEach(r => {
        const pays = (deepDiv?.tickers?.[r.ticker] || []).filter(p => p.ex >= cutoff);
        if (pays.length) { expDiv += pays.reduce((a, p) => a + p.rs, 0) * r.shares; divCov += (r.mv || 0); }
      });
      // desk rules, applied literally (CLAUDE.md Rule 4)
      const dupSec = Object.entries(secW).filter(([k, v]) => k !== "Unclassified" && withW.filter(r => r.sector === k).length > 1);
      /* PUBLICATION FRAME (docs/PUBLICATION_RESTRUCTURE.md §2a). The split here is deliberate and
         it is the whole point of this block:

           `k` and `why`  — the desk's OWN rule and the reason the desk holds it. Impersonal,
                            identical for every reader, and already published methodology.
           `v` and `ok`   — arithmetic over the reader's own holdings. That is tracking, which the
                            restructure explicitly allows.

         What was removed is the third thing that used to sit in `why`: prose that read the
         reader's specific mix back to them — "You hold 6", "FFC is 34% of the portfolio… one
         company's bad quarter sets the whole result". Stating a rule and showing someone their
         number is reference. Narrating what their particular portfolio means is the advisory line,
         and it was the only part of this surface that crossed it. The numbers all survive; the
         reader draws the conclusion. */
      const checks = [
        { ok: withW.length <= 4, k: "Max 4 concurrent positions", v: `${withW.length} holding${withW.length === 1 ? "" : "s"}`,
          why: "The desk caps itself at 4 open positions so each one gets real attention." },
        { ok: !dupSec.length, k: "No two positions in one sector", v: dupSec.length ? `${dupSec.map(([k]) => esc(k)).join(", ")} doubled` : "none doubled",
          why: "The desk allows itself one position per sector — two names in one sector is one bet wearing two tickers." },
        { ok: top ? top.w <= 20 : true, k: "Position ≤ 20% of capital", v: top ? `largest ${esc(top.ticker)} ${top.w.toFixed(0)}%` : "—",
          why: "The desk caps any single position at 20% of capital, so one company's bad quarter cannot set the whole result." },
      ];
      const nPass = checks.filter(c => c.ok).length;
      xray = `
      <div class="seg"><h2>Portfolio X-ray</h2><div class="ln"></div><span class="pill ${nPass === checks.length ? "ok" : ""}">${nPass}/${checks.length} desk rules met</span></div>
      <p class="sub" style="margin-bottom:12px">The desk's own risk rules, run over your actual holdings. These are <b>the constraints the desk imposes on itself</b> — shown so you can see how your mix reads against them. Not instructions, and not a suggestion to trade.</p>
      <div class="sumstrip s4">
        ${sTile("Weighted beta", beta != null ? beta.toFixed(2) : "—", beta != null ? (beta > 1.1 ? "amplifies market swings" : beta < 0.9 ? "calmer than the market" : "moves with the market") + ` · ${(bCov / wsum * 100).toFixed(0)}% covered` : "no beta data", beta != null && beta > 1.2 ? "dn" : "")}
        ${sTile("Blended yield", yld != null ? yld.toFixed(2) + "%" : "—", `${(yCov / wsum * 100).toFixed(0)}% of value covered`, "")}
        ${sTile("Expected dividends", divCov ? "Rs " + fmt(expDiv, 0) : "—", divCov ? "from the last 12 months' real payouts" : "no payout history", divCov ? "up" : "")}
        ${sTile("Vs model fair value", gap != null ? sgn(+gap.toFixed(1)) + "%" : "—", "value-weighted across holdings", gap > 0 ? "up" : gap < 0 ? "dn" : "")}
      </div>
      <div class="card xray">
        ${checks.map(c => `<div class="xr-row ${c.ok ? "ok" : "flag"}">
          <span class="xr-dot">${c.ok ? "✓" : "!"}</span>
          <div><b>${esc(c.k)}</b><span class="sub">${c.why}</span></div>
          <span class="xr-v">${esc(c.v)}</span></div>`).join("")}
        <div class="sub xr-foot">Expected dividends are the <b>last twelve months' actual payouts</b> applied to your share counts — history, not a forecast: companies cut dividends. Beta and yield are value-weighted over the holdings the desk has data for, and the coverage is stated so a partial figure is never mistaken for a complete one.</div>
      </div>`;
    }
  }

  $("view").innerHTML = `
  <div class="seg" style="margin-top:4px"><h2>Your portfolio</h2><div class="ln"></div><span class="pill">${rows.length} holding${rows.length === 1 ? "" : "s"}</span></div>
  <div class="disclaimer">A private, <b>read-only</b> tracker of what you own — the desk never places orders and holds no money. Every figure below is a <b>fact about your holdings</b>, computed from desk prices; none of it is advice or a recommendation to buy or sell.</div>

  <div class="card ph-form">
    <div class="ph-row">
      <input id="ph-tkr" type="search" enterkeyhint="next" placeholder="Ticker (e.g. FFC)" aria-label="Ticker" class="ph-in combo" autocomplete="off">
      <input id="ph-sh" type="text" inputmode="numeric" enterkeyhint="next" placeholder="Shares" aria-label="Shares held" class="ph-in">
      <input id="ph-cost" type="text" inputmode="decimal" enterkeyhint="done" placeholder="Avg cost (Rs)" aria-label="Average cost per share in rupees" class="ph-in">
      <button class="note-save" onclick="submitHolding()">Add holding</button>
    </div>
    <span id="ph-msg" class="sub"></span>
  </div>

  ${rows.length ? `<div class="sumstrip s4">
    ${sTile("Portfolio value", "Rs " + fmt(totMv, 0), "at desk prices", "")}
    ${sTile("Total profit / loss", (totPl >= 0 ? "+" : "") + "Rs " + fmt(totPl, 0), totPlPct != null ? sgn(totPlPct) + "% on cost" : "", totPl >= 0 ? "up" : "dn")}
    ${sTile("Est. annual dividend", "Rs " + fmt(totDiv, 0), "from last declared payouts", "")}
    ${sTile("Positions", rows.length, "one row per ticker", "")}
  </div>

  <div class="card"><table><thead><tr><th>Ticker</th><th class="r">Shares</th><th class="r">Avg cost</th><th class="r">Price</th><th class="r">Value</th><th class="r">P/L</th><th class="r">Weight</th><th></th></tr></thead><tbody>${
    withW.map(r => `<tr>
      <td class="clickable" onclick="navigate('/ticker/${esc(r.ticker)}')"><b>${esc(r.ticker)}</b> <span class="sub">${esc((r.name || "").slice(0, 16))}</span>${r.known ? "" : ' <span class="sub dn">not in universe</span>'}${r.sector ? `<div class="sub" style="opacity:.7">${esc(r.sector)}</div>` : ""}</td>
      <td class="r num">${fmt(r.shares)}</td><td class="r num">${fmt(r.avg_cost)}</td>
      <td class="r num">${r.px != null ? fmt(r.px) : "—"}</td>
      <td class="r num">${r.mv != null ? fmt(r.mv, 0) : "—"}</td>
      <td class="r num ${r.pl == null ? "" : r.pl >= 0 ? "up" : "dn"}">${r.plPct != null ? sgn(r.plPct) + "%" : "—"}${r.pl != null ? `<div class="sub">${(r.pl >= 0 ? "+" : "") + fmt(r.pl, 0)}</div>` : ""}</td>
      <td class="r num">${r.w.toFixed(0)}%</td>
      <td class="r"><button class="ph-del" onclick="removeHolding('${esc(r.ticker)}')" title="Remove holding">✕</button></td></tr>`).join("")}
  </tbody><tfoot><tr><td><b>Total</b></td><td></td><td></td><td></td><td class="r num"><b>${fmt(totMv, 0)}</b></td>
    <td class="r num ${totPl >= 0 ? "up" : "dn"}"><b>${totPlPct != null ? sgn(totPlPct) + "%" : "—"}</b></td><td></td><td></td></tr></tfoot></table></div>

  <div class="seg"><h2>Concentration</h2><div class="ln"></div><span class="pill">fact, not advice</span></div>
  <div class="card">
    <p class="sub" style="line-height:1.6;margin-bottom:12px">${concFlag} Concentration means your portfolio rises and falls with fewer bets; diversification spreads that risk across more names. Whether that's right for you depends on your own goals and risk tolerance — the desk states the fact and the general principle, and never tells you to buy or sell.</p>
    <div class="ph-bars">${withW.map(r => `<div class="ph-bar-row"><span class="ph-bar-lbl">${esc(r.ticker)}</span><span class="ph-bar-track"><span class="ph-bar-fill" style="width:${Math.max(2, r.w).toFixed(0)}%"></span></span><span class="ph-bar-val num">${r.w.toFixed(0)}%</span></div>`).join("")}</div>
  </div>

  <div class="seg"><h2>Sector concentration</h2><div class="ln"></div><span class="pill">${secRows.length} sector${secRows.length === 1 ? "" : "s"}</span></div>
  <div class="card">
    <p class="sub" style="line-height:1.6;margin-bottom:12px">${secFlag} This is the exposure position weights hide: two banks are one bet on interest rates, and two cement names are one bet on construction — however different the tickers look. Sectors are PSX's own classification. Stated as a fact about your holdings, not as advice.</p>
    <div class="ph-bars">${secRows.map(([s, pct]) => `<div class="ph-bar-row"><span class="ph-bar-lbl" title="${esc(s)}">${esc(s.length > 22 ? s.slice(0, 21) + "…" : s)}</span><span class="ph-bar-track"><span class="ph-bar-fill" style="width:${Math.max(2, pct).toFixed(0)}%"></span></span><span class="ph-bar-val num">${pct.toFixed(0)}%</span></div>`).join("")}</div>
  </div>

  ${xray}

  <p class="sub" style="margin-top:14px">Estimated dividend income is each holding's most recent declared dividend × your shares — an estimate from past payouts, not a promise; companies can cut or skip dividends. Prices are desk end-of-day/live figures and may differ from your broker. Research, not advice.</p>`
    : `<div class="card"><div class="empty">No holdings yet. Add one above — enter a ticker, how many shares, and your average cost, and the desk tracks your live value, profit/loss and position weights here.</div></div>`}`;
}

// pageWatchlist lives in its own page file (redesign 2026-09).

/* ---------- plan intent, carried in from the marketing site ----------------------------
   plans.astro links to `${appUrl}/?plan=investor|pro`. Persist it immediately: the visitor is
   about to leave for an email confirmation and come back on a fresh page load, and the query
   string will not survive that round trip. It decides which onboarding they get, and it is
   INTENT ONLY — never an entitlement. Plan still comes from the DB (see realPlan/planOf),
   because anything a browser can set, a browser can forge. */
/* The key is inlined rather than held in a `const` on purpose. route() — and therefore the gate
   that wants to read this — runs BEFORE this point in the file at boot, and a `const` referenced
   in its temporal dead zone throws. Function declarations hoist, so these two stay callable from
   anywhere; a const would not. (First pass had exactly this bug: the gate rendered its generic
   copy because the intent had not been captured yet.) */
function capturePlanIntent() {
  try {
    const p = new URLSearchParams(location.search).get("plan");
    if (!p) return;
    if (PLANS[p]) localStorage.setItem("henneth_plan_intent", p);
    // strip ?plan= so a refresh or a shared link doesn't re-trigger it, keeping the path route
    // Preserve a Supabase callback fragment while removing the marketing intent query.
    history.replaceState(null, "", location.pathname + (location.hash || ""));
  } catch { /* private mode: intent is a nicety, never required */ }
}
function planIntent() { try { return localStorage.getItem("henneth_plan_intent"); } catch { return null; } }
capturePlanIntent();

/* `?auth=signup` (or signin) from a marketing CTA opens the form directly. Someone who just
   clicked "Get started" should not have to find the button again. Deferred to the next tick so
   auth has resolved — otherwise a signed-in returning visitor gets a pointless login modal. */
(function honourAuthParam() {
  let want = null;
  try { want = new URLSearchParams(location.search).get("auth"); } catch { return; }
  if (want !== "signup" && want !== "signin") return;
  try { history.replaceState(null, "", location.pathname + (location.hash || "")); } catch {}
  setTimeout(() => { if (!me && typeof openAuth === "function") openAuth(want); }, 600);
})();

/* ---------- onboarding: one activation prompt + a dismissible coach strip -------------
   Replaces the old 8-11 step quiz+tour wizard. The wizard measured "tour completed", a metric
   nobody cared about; this measures a real action (watchlist add / Room lookup / sizer run /
   birth-chart cast) via markActivated(), gated on activated_at is null, not the frozen legacy
   onboarded column. */
const COACH_STEPS = [
  { route: "/today", title: "Today", body: "The desk's daily plain-English read — mood, favoured sectors, a short watchlist." },
  { route: "/board", title: "Board", body: "The whole tape: live moves, signals that fired from backtested rules." },
  { route: "/ticker/FFC", title: "Desk Room", body: "Open any ticker and read the desk's debate — TA and FA argue it out, no verdict." },
  { route: "/leaderboard", title: "Scores", body: "Every call, ours and the brokerage houses', graded against what price did." },
];
let coachIdx = 0;

function maybeCoach() {
  if (!myProfile || myProfile.activated_at) return;
  if (localStorage.getItem("psx_coach_dismissed")) return;
  renderCoach();
}
function startTour() {
  localStorage.removeItem("psx_coach_dismissed");
  coachIdx = 0;
  renderCoach();
}
function dismissCoach() {
  document.getElementById("coachStrip")?.remove();
  localStorage.setItem("psx_coach_dismissed", "1");
  track && track("coach_card_dismissed", { step: coachIdx });
}
function renderCoach() {
  document.getElementById("coachStrip")?.remove();
  const s = COACH_STEPS[coachIdx];
  if (!s) { track && track("tour_completed", {}); return; }
  if (coachIdx === 0) track && track("tour_started", {});
  navigate(s.route);
  const strip = el(`<div class="coach-strip" id="coachStrip">
    <div class="coach-body">
      <b class="coach-title">${s.title}</b>
      <p class="coach-text">${s.body}</p>
    </div>
    <div class="coach-nav">
      <button class="coach-next" id="coachNext">${coachIdx === COACH_STEPS.length - 1 ? "Done" : "Next"}</button>
      <button class="coach-skip" id="coachSkip">Dismiss</button>
    </div>
  </div>`);
  document.body.appendChild(strip);
  track && track("coach_card_shown", { step: coachIdx });
  document.getElementById("coachNext").onclick = () => { coachIdx++; renderCoach(); };
  document.getElementById("coachSkip").onclick = () => dismissCoach();
}

/* Ties the anonymous session that arrived from an ad to the account it became, so the whole
   path — ad click, marketing page, gate, signup, first ticker opened — reads as one person
   instead of two strangers who happen to share a browser.

   The Supabase user id is used, NOT the email. The id is already an opaque UUID that means
   nothing outside this system, whereas shipping email addresses into a third-party analytics
   product is a materially bigger promise than "we measure usage" — and state/legal.json is still
   review_status: DRAFT. Plan goes on as a property because it is the one dimension worth
   segmenting every other number by. */
function identifyUser() {
  try {
    if (!window.posthog) return;
    if (me?.id) posthog.identify(me.id, { plan: (myProfile && myProfile.plan) || "free" });
    else posthog.reset();   // signed out: stop attributing this browser to the previous account
  } catch {}
}

/* ---------- boot ---------- */
async function initAuth() {
  // NOTE: this function now owns the FIRST paint of the session. Nothing renders before it —
  // see authResolved() in the gate section for why. Every path out of the try/catch below must
  // therefore reach the `finally`, or the visitor is left staring at a blank page.
  try {
    if (sb) {   // no sb = CDN blocked; the shared research still works, accounts just hidden
      const { data: { session } } = await sb.auth.getSession();
      me = session?.user || null;
      renderAccountButton();
      identifyUser();
      if (me) {
        // Resolved BEFORE the first render, not after it: the pages that depend on the signed-in
        // user — Your Chart, Portfolio, Watchlist, Settings — used to paint their signed-out state
        // and then re-render, which is visible as a second flash on exactly those pages.
        await loadProfile();
        startProfileRealtime(me?.id);
        await migrateGuestChart();   // a chart cast before signing up follows the user into their account
        if (myProfile?.lang && myProfile.lang !== lang()) { try { localStorage.setItem(LANG_KEY, myProfile.lang); } catch {} }
        applyLang();
        applyDeskMode();
      }
    }
  } catch (err) {
    // A failed session restore or profile fetch must not strand anyone on a blank screen. Unknown
    // auth falls back to signed-out, which shows the gate — a member can click through it.
    console.error("auth init failed — falling back to the sign-in gate:", err);
  } finally {
    authResolved();
    // Surface & clear any expired/invalid email-link error hash BEFORE routing — otherwise route()
    // sees error_code= in the hash, bails, and leaves a permanently blank page (top signup-failure
    // symptom). This shows the message and clears the hash so the paint below succeeds.
    try { consumeAuthErrorHash(); } catch (e) { console.error("auth error-hash handling failed:", e); }
    route(false);              // <- the first paint of the session, with auth actually known
  }
  if (me && myProfile) maybeCoach();
  if (!sb) return;
  sb.auth.onAuthStateChange(async (event, sess) => {
    const prevId = me?.id || null;
    me = sess?.user || null;
    renderAccountButton();
    if (event === "PASSWORD_RECOVERY") return openRecovery();
    if (event === "SIGNED_IN") {
      // supabase-js re-validates the stored session whenever the tab regains focus and re-fires
      // SIGNED_IN for a session that was already active. That is not a sign-in, but it used to run
      // the whole block below — including route(true), which rewrites #view.innerHTML from scratch.
      // That full destroy-and-rebuild is the desk "blinking" every time you come back to the tab.
      if (me?.id && me.id === prevId) return;
      closeAuth();
      await loadProfile();
      startProfileRealtime(me?.id);
      await migrateGuestChart();   // the whole point of the funnel: never ask for birth details twice
      applyDeskMode();
      identifyUser();              // after loadProfile, so the plan property is the real one
      if (typeof route === "function") route(true);   // re-render the page you're on with your account
      if (myProfile) maybeCoach();
    }
    if (event === "SIGNED_OUT") {
      stopProfileRealtime();
      myProfile = null; applyDeskMode(); identifyUser();
      if (typeof route === "function") route(true);
    }
  });
}
initAuth();
