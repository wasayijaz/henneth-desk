// research page — redesign 2026-09
// Behaviour parity source: old pageResearch (app.js, removed here, kept in git history) —
// preserves isSubscribed()/planWall() gating and the followedBrokers() "★ following" sort.
// New visual structure ported from docs/redesign-mockups/research-mockup.html (4 sections:
// the weekly shelf, what the brokers said, what companies filed, the company-website archive).
// Real data only — every number below is read from state/ via j(): research_index.json
// (documents), claims.json (broker claims only — the file also carries persona/astro/desk
// claims that use a different shape and are NOT research-library claims), broker_scorecard.json,
// universe.json (names) and quant.json (last close, for the price-position glyph). Nothing is
// invented client-side beyond counting, sorting and simple date/percent maths.
// No advice language: broker/company wording appears ONLY inside an expanded call row,
// explicitly credited to its house — never presented as the desk's view. Missing price/date/
// target always renders "unknown" or "—", never 0.

const RS_MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const rsN0 = v => v == null || !isFinite(v) ? "unknown" : Math.round(v).toLocaleString("en-US");
const rsPx = v => v == null || !isFinite(v) ? "unknown" : "Rs " + (+v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
// Mirrors the mockup's fD/fDY exactly: slice the ISO string (zero-padded day
// kept, e.g. "07 Oct"), never round-trip through Date — sidesteps TZ drift.
const rsDY = s => s ? `${s.slice(8, 10)} ${RS_MON[+s.slice(5, 7) - 1]}` : "unknown";
const rsD = s => s ? `${rsDY(s)} ${s.slice(0, 4)}` : "unknown";
const rsDays = (a, b) => Math.round((new Date(b) - new Date(a)) / 86400000);
const RS_TODAY = new Date().toISOString().slice(0, 10);

// doc-type -> family, for the filings chapter and the weekly mix bar. Families are a display
// grouping only (no state file carries them) — every key below is a doc_type actually written
// by scripts/research_index.py; unrecognised types fall into "announce".
const RS_FAM = {
  results: { label: "Results & statements", types: ["financial_results", "results", "financial_statement", "financial_report", "annual_report"] },
  meetings: { label: "Meetings & briefings", types: ["board_meeting", "meeting_notice", "corporate_briefing", "agm"] },
  actions: { label: "Corporate actions", types: ["corporate_action", "material_information"] },
  people: { label: "People & disclosures", types: ["management_change", "insider_disclosure"] },
  announce: { label: "Announcements", types: ["company_announcement", "governance_document", "presentation", "filing"] },
};
const RS_FAM_OF = {};
for (const [k, v] of Object.entries(RS_FAM)) for (const t of v.types) RS_FAM_OF[t] = k;
const rsFamOf = d => RS_FAM_OF[d.doc_type] || "announce";
const RS_DT = { financial_results: "results", results: "results", financial_statement: "financial statement", financial_report: "financial report", annual_report: "annual report", board_meeting: "board meeting", meeting_notice: "meeting notice", corporate_briefing: "corporate briefing", agm: "AGM", corporate_action: "corporate action", material_information: "material information", management_change: "management change", insider_disclosure: "insider disclosure", company_announcement: "announcement", governance_document: "governance document", presentation: "presentation", filing: "filing", company_note: "broker note", issuer_document: "issuer document" };
const RS_GENERIC = /^(download( pdf)?|document|untitled|attachment|file|report)\.?$/i;

// price-position glyph for a call: bar from price-at-call to target, with a tick for last close.
// data-tip/aria-label carry the house's own numbers — never the desk's view; nulls read
// "unknown"/"no target reported", never a fabricated position.
function rsGlyph(c, close) {
  const at = c.made_at_price, tg = c.claim?.target_price, dir = c.claim?.direction, now = close?.close;
  const arrow = dir === "up" ? '<span class="arr up">↑</span>' : dir === "down" ? '<span class="arr dn">↓</span>' : '<span class="arr mut">–</span>';
  if (at == null || tg == null || !isFinite(at) || !isFinite(tg)) {
    const why = at == null && tg == null ? "no price at call · no target reported" : at == null ? `reported target ${rsPx(tg)} · price at call unknown` : "no target reported";
    return `<div class="rs-g nt">${arrow}<span>${esc(why)}</span></div>`;
  }
  const pts = [at, tg, now].filter(v => v != null && isFinite(v));
  const lo = Math.min(...pts), hi = Math.max(...pts), pad = (hi - lo) * 0.08 || hi * 0.02 || 1;
  const p = v => (((v - lo + pad) / (hi - lo + 2 * pad)) * 100).toFixed(2);
  const a = +p(at), t = +p(tg);
  const segCls = dir === "up" ? "up" : dir === "down" ? "dn" : tg >= at ? "up" : "dn";
  const pct = at ? Math.abs((tg / at - 1) * 100).toFixed(1) : "0.0";
  const tipTxt = `${c.source} · ${c.ticker}\nPrice at call (${rsDY(c.made_on)}): ${rsPx(at)}\nReported target: ${rsPx(tg)} (${tg >= at ? "+" : "−"}${pct}% from the call price)` +
    (now != null && isFinite(now) ? `\nLast close (${rsDY(close?.date)}): ${rsPx(now)}` : "\nLast close: unknown") +
    (rsOdd(c) ? `\nCHECK: reported direction is ${dir || "unclear"}, but the recorded target sits on the other side of the call price` : "");
  return `<div class="rs-g" data-tip="${esc(tipTxt)}" tabindex="0" aria-label="${esc(tipTxt)}">
    <span class="base"></span><span class="seg ${segCls}" style="left:${Math.min(a, t)}%;width:${Math.abs(t - a)}%"></span>
    <span class="tgt" style="left:${t}%"></span><span class="call" style="left:${a}%"></span>${now != null && isFinite(now) ? `<span class="now" style="left:${p(now)}%"></span>` : ""}
    <span class="lb ${a > t ? "r" : ""}" style="left:${a}%">${rsPx(at)}</span><span class="lb ${a > t ? "" : "r"}" style="left:${t}%">${rsPx(tg)}</span>
  </div>`;
}
// a call is "odd" — flagged CHECK TARGET — when the direction and target contradict each other
// (an "up" call with a target below the call price, or a "down" call with a target above it).
const rsOdd = c => { const at = c.made_at_price, tg = c.claim?.target_price, d = c.claim?.direction; return at != null && tg != null && ((d === "up" && tg < at) || (d === "down" && tg > at)); };
// countdown bar toward resolve_by; "late" once past the date and still pending. Caption is always
// visible (not tooltip-only) — "resolves <date> · N d left", or the overdue/resolved variants.
function rsHorizon(c) {
  const tot = Math.max(1, rsDays(c.made_on, c.resolve_by));
  const gone = rsDays(c.made_on, RS_TODAY);
  const left = rsDays(RS_TODAY, c.resolve_by);
  const late = c.status === "pending" && left < 0;
  const pct = Math.min(100, Math.max(0, (gone / tot) * 100));
  const caption = late ? `past resolve-by ${rsDY(c.resolve_by)} · still pending` : c.status !== "pending" ? `resolved ${rsD(c.resolved_on)}` : `resolves ${rsD(c.resolve_by)} · ${left} d left`;
  return `<div class="rs-hz${late ? " late" : ""}"><div class="bar"><i style="width:${pct.toFixed(1)}%"></i></div><small>${esc(caption)}</small></div>`;
}

// fixed 6-column grid (shared with the .rs-cl-h header): date | house | ticker+name+tag | glyph |
// horizon | chevron. The CHECK TARGET tag lives inside .rs-tk so a flagged row never shifts the
// other columns out of alignment with the rows around it.
function rsCallRow(c, close, names) {
  const odd = rsOdd(c);
  const nm = names[c.ticker];
  return `<details class="rs-call">
    <summary>
      <span class="d">${esc(rsDY(c.made_on))}</span>
      <span class="hs">${esc(c.source)}</span>
      <span class="rs-tk">
        <span class="clickable" onclick="event.preventDefault();event.stopPropagation();navigate('/ticker/${esc(c.ticker)}')">${esc(c.ticker)}</span>
        <small>${esc(nm || "name unknown")}</small>
        ${odd ? `<span class="mc-flag" style="width:max-content" data-tip="direction and target price disagree — read this one carefully">CHECK TARGET</span>` : ""}
      </span>
      ${rsGlyph(c, close[c.ticker])}
      ${rsHorizon(c)}
      <span class="chev" aria-hidden="true">›</span>
    </summary>
    <div class="rs-det">
      <blockquote>${esc(c.claim?.text || "")}</blockquote>
      <p class="sub">— ${esc(c.source)}'s wording, not the desk's view. Extracted from the note below and scored against what actually happened.</p>
      <dl>
        <dt>Kind</dt><dd>${esc(c.kind || "unknown")}${c.claim?.direction ? " · " + esc(c.claim.direction) : ""}</dd>
        <dt>Price at call</dt><dd>${c.made_at_price == null ? '<span class="sub">unknown</span>' : rsPx(c.made_at_price)}</dd>
        <dt>Reported target</dt><dd>${c.claim?.target_price == null ? '<span class="sub">none reported</span>' : rsPx(c.claim.target_price)}</dd>
        <dt>Last close</dt><dd>${close[c.ticker]?.close != null ? `${rsPx(close[c.ticker].close)} (${esc(rsD(close[c.ticker].date))})` : '<span class="sub">unknown</span>'}</dd>
        ${odd ? `<dt>Record check</dt><dd class="dn">direction/target mismatch — flagged, not corrected</dd>` : ""}
        <dt>Horizon</dt><dd>${esc(rsD(c.made_on))} → ${esc(rsD(c.resolve_by))}</dd>
        <dt>Source</dt><dd>${externalLink(c.source_url, "original ↗", 'style="color:var(--accent)"') || "unknown"}</dd>
      </dl>
    </div>
  </details>`;
}

function rsHouseTile(h, calls, sc, mins) {
  const mine = calls.filter(c => c.source === h);
  const up = mine.filter(c => c.claim?.direction === "up").length, dn = mine.filter(c => c.claim?.direction === "down").length;
  const rank = sc?.[h];
  const n = rank?.n_calls ?? mine.length;
  const dots = Array.from({ length: mins }, (_, i) => `<i class="${i < Math.min(n, mins) ? "on" : ""}"></i>`).join("");
  return `<button class="rs-house" data-house="${esc(h)}" type="button" aria-pressed="false">
    <b>${esc(h)}</b><span class="ln">${mine.length} call${mine.length === 1 ? "" : "s"} · ${up} up · ${dn} down</span>
    <span class="rs-samp">${dots}</span>
    <span class="rank">${rank?.hit_rate != null ? `${Math.round(rank.hit_rate * 100)}% hit rate` : `unranked — needs ${mins} calls to rank`}</span>
  </button>`;
}

async function pageResearch() {
  const [idx, claimsFile, sc, uni, quant] = await Promise.all([
    j("research_index.json"), j("claims.json"), j("broker_scorecard.json"), j("universe.json"), j("quant.json"),
  ]);
  const view = $("view");
  const docs = Object.values(idx?.documents || {});
  if (!docs.length) {
    view.innerHTML = `<div class="today-page rs-page"><div class="empty">Research library is empty — nothing digested yet.</div></div>`;
    return;
  }
  const names = {}; for (const [sym, s] of Object.entries(uni?.symbols || {})) names[sym] = s.name || "";
  const close = {}; for (const [sym, t] of Object.entries(quant?.tickers || {})) close[sym] = { close: t.close, date: t.date };
  const followed = new Set(followedBrokers());
  const brokerDocs = docs.filter(d => d.source_type === "broker").sort((a, b) => (followed.has(b.source) ? 1 : 0) - (followed.has(a.source) ? 1 : 0) || (b.date || "").localeCompare(a.date || ""));
  const filingDocs = docs.filter(d => d.source_type === "filing").sort((a, b) => (b.date || "").localeCompare(a.date || ""));
  const archiveDocs = docs.filter(d => d.source_type === "issuer_document");
  const claims = (claimsFile?.claims || []).filter(c => c.source_type === "broker").sort((a, b) => (b.made_on || "").localeCompare(a.made_on || ""));
  const houses = [...new Set(brokerDocs.map(d => d.source))].sort((a, b) => brokerDocs.filter(d => d.source === b).length - brokerDocs.filter(d => d.source === a).length);
  const scBrokers = sc?.brokers || {};
  const mins = sc?._meta?.min_sample_to_rank ?? 5;
  const noClaim = brokerDocs.filter(d => !claims.some(c => c.id === "claim:" + d.hash));

  // 26-week filing/broker flow — mirrors the mockup's weekly shelf chart
  const WEEKS = 26;
  const monday = t => { const d = new Date(t); const wd = (d.getDay() + 6) % 7; d.setDate(d.getDate() - wd); return d; };
  const W0 = monday(new Date()); W0.setDate(W0.getDate() - 7 * (WEEKS - 1));
  const weeks = Array.from({ length: WEEKS }, (_, i) => { const t = new Date(W0); t.setDate(t.getDate() + 7 * i); return { t, f: 0, b: 0 }; });
  const isoD = t => t.toISOString().slice(0, 10);
  const weekIdx = dstr => { if (!dstr) return -1; const wm = monday(new Date(dstr + "T00:00:00")); return Math.round((wm - W0) / (7 * 86400000)); };
  for (const d of docs) { if (d.source_type === "astro") continue; const wi = weekIdx(d.date); if (wi >= 0 && wi < WEEKS) { if (d.source_type === "broker") weeks[wi].b++; else weeks[wi].f++; } }
  const wMax = Math.max(1, ...weeks.map(w => w.f + w.b));
  const flowBars = weeks.map((w, i) => { const h = 64, fh = (w.f / wMax) * h, bh = (w.b / wMax) * h; return `<div class="rs-flowcol" data-tip="${esc(`week of ${isoD(w.t)}: ${w.f} filing${w.f === 1 ? "" : "s"}, ${w.b} broker note${w.b === 1 ? "" : "s"}`)}"><i class="rs-flowbar rs-flow-f" style="height:${fh}px"></i><i class="rs-flowbar rs-flow-b" style="height:${bh}px"></i></div>`; }).join("");

  const nClaims = claims.length;
  const latest = docs.reduce((a, d) => (!a || (d.date || "") > (a || "")) ? (d.date || a) : a, null) || "—";
  const sTile = (label, val, sub) => `<div class="sumtile"><span class="sk">${esc(label)}</span><b>${val}</b>${sub ? `<i>${esc(sub)}</i>` : ""}</div>`;

  const mixTotal = filingDocs.length || 1;
  const famCount = k => filingDocs.filter(d => rsFamOf(d) === k).length;
  const mixBar = Object.entries(RS_FAM).map(([k, v]) => `<span class="rs-mixseg rs-mix-${esc(k)}" style="width:${(famCount(k) / mixTotal) * 100}%" data-tip="${esc(v.label)}: ${famCount(k)}"></span>`).join("");
  const cut90 = new Date(Date.now() - 90 * 86400000).toISOString().slice(0, 10);
  const topNames = (fam) => { const pool = filingDocs.filter(d => (d.date || "") >= cut90 && (!fam || rsFamOf(d) === fam)); const cnt = {}; for (const d of pool) for (const t of d.tickers || []) cnt[t] = (cnt[t] || 0) + 1; return Object.entries(cnt).sort((a, b) => b[1] - a[1]).slice(0, 10); };
  const docRow = d => `<div class="rdoc">
    <div class="rdoc-top"><span class="tag">${esc(RS_DT[d.doc_type] || d.doc_type)}</span>
      <span class="rdoc-src">${esc(d.source)}${d.digest_level === "headline" ? ' · <span class="sub">headline only</span>' : ""}</span>
      <span class="t">${esc(rsD(d.date))}</span>
      ${(d.tickers || []).slice(0, 4).map(t => `<span class="tag clickable" onclick="navigate('/ticker/${esc(t)}')">${esc(t)}</span>`).join(" ")}</div>
    <div class="rdoc-digest">${esc(d.digest || "")}${externalLink(d.url, "source ↗", 'style="color:var(--accent)"') ? ` ${externalLink(d.url, "source ↗", 'style="color:var(--accent)"')}` : ""}</div></div>`;

  // archive (issuer-website) tiles
  const arVerified = archiveDocs.filter(d => d.download?.status === "verified").length;
  const arFailed = archiveDocs.filter(d => d.download?.status && d.download.status !== "verified").length;
  const arGeneric = archiveDocs.filter(d => RS_GENERIC.test((d.title || "").trim())).length;
  const mb = b => b == null || !isFinite(b) ? "unknown" : (b / 1e6).toFixed(1) + " MB";
  const aRow = d => `<div class="rdoc${d.download?.status && d.download.status !== "verified" ? " rs-arc-bad" : ""}">
    <div class="rdoc-top"><span class="tag">${d.download?.status === "verified" ? "verified" : d.download?.status ? "failed" : "unchecked"}</span>
      ${(d.tickers || []).slice(0, 3).map(t => `<span class="tag clickable" onclick="navigate('/ticker/${esc(t)}')">${esc(t)}</span>`).join(" ")}
      <span class="t">${d.first_seen_at ? esc(rsD(String(d.first_seen_at).slice(0, 10))) : "unknown"}</span></div>
    <div class="rdoc-digest">${RS_GENERIC.test((d.title || "").trim()) ? '<span class="mc-flag">GENERIC TITLE</span> ' : ""}${externalLink(d.url, esc(d.title || "document"), 'style="color:var(--accent)"') || esc(d.title || "document")} <span class="sub">· ${mb(d.content_length)}</span></div></div>`;

  function render() {
    view.innerHTML = `<div class="today-page rs-page">
      <div class="seg" style="margin-top:4px"><h2>Research library</h2><div class="ln"></div><span class="pill">${docs.length} documents</span></div>
      <div class="rs-hero">
        <div class="rs-flow"><div class="rs-flowchart">${flowBars}</div><span class="sub">weekly document flow · ${WEEKS} weeks · filings vs broker notes</span></div>
        <div class="sumstrip s4">
          ${sTile("Broker notes", brokerDocs.length, `${houses.length} house${houses.length === 1 ? "" : "s"}${followed.size ? ` · ${followed.size} you follow` : ""}`)}
          ${sTile("Filings & briefings", filingDocs.length, "results · AGM · board")}
          ${sTile("Claims on the record", nClaims, nClaims ? "each scored when it resolves" : "")}
          ${sTile("Latest document", esc(rsD(latest)), "the wire updates weekly")}
        </div>
      </div>
      <div class="disclaimer">Broker research and company filings are <b>evidence the desk cross-examines, never takes at face value</b>. Brokers miss things, carry sector bias, and are often wrong — every broker claim here is extracted, scored against what actually happens, and ranked on the <a href="/leaderboard" style="color:inherit;text-decoration:underline">broker leaderboard</a>. Educational, not advice.</div>

      <div class="seg"><h2>What the brokers said</h2><div class="ln"></div><span class="pill">${claims.length} calls</span></div>
      <div class="rs-houses">${houses.length ? houses.map(h => rsHouseTile(h, claims, scBrokers, mins)).join("") : '<div class="empty">No broker sources configured yet.</div>'}</div>
      <div class="rs-cl-h" aria-hidden="true"><span class="d">DATE</span><span class="hs">HOUSE</span><span class="rs-tk">NAME</span><span class="rs-g">PRICE AT CALL → REPORTED TARGET</span><span class="rs-hz">SCORED BY</span><span class="chev"></span></div>
      <div class="card rs-calls">${(isSubscribed() ? claims : claims.slice(0, 2)).slice(0, 6).map(c => rsCallRow(c, close, names)).join("") || '<div class="empty">No broker calls digested yet — the desk forms its own view without leaning on brokers.</div>'}</div>
      <div class="rs-key"><span><i class="k-call"></i>price when the call was made</span><span><i class="k-tgt"></i>house's reported target</span><span><i class="k-now"></i>last close (${esc(rsD(Object.values(close).map(v => v.date).filter(Boolean).sort().slice(-1)[0]))})</span><span><i class="k-seg"></i>reported direction, up or down</span></div>
      ${claims.length > 6 ? `<button class="btn rs-showmore" type="button">Show all ${claims.length} calls${claims.filter(c => rsOdd(c)).length ? ` · ${claims.filter(c => rsOdd(c)).length} flagged` : ""}</button>` : ""}
      ${noClaim.length ? `<details class="rs-fold"><summary>${noClaim.length} broker note${noClaim.length === 1 ? "" : "s"} with no extracted claim</summary><div class="card">${noClaim.slice(0, isSubscribed() ? 999 : 2).map(docRow).join("")}</div></details>` : ""}

      <div class="seg"><h2>What companies filed</h2><div class="ln"></div><span class="pill">${filingDocs.length}</span></div>
      <div class="rs-mixbar">${mixBar}</div>
      <div class="rs-famtiles">${Object.entries(RS_FAM).map(([k, v]) => `<button class="chip" data-fam="${esc(k)}" type="button">${esc(v.label)} <span class="sub">${famCount(k)}</span></button>`).join("")}</div>
      <div class="rs-fil2col">
        <div><h3 class="sub">Latest filings</h3><div class="card rs-latest">${(isSubscribed() ? filingDocs : filingDocs.slice(0, 2)).slice(0, 8).map(docRow).join("") || '<div class="empty">No filings tagged yet.</div>'}</div></div>
        <div><h3 class="sub">Most active in 90 days</h3><div class="card rs-top">${topNames(null).map(([t, n]) => `<div class="rdoc rs-toprow"><span class="tag clickable" onclick="navigate('/ticker/${esc(t)}')">${esc(t)}</span><span class="sub">${esc(names[t] || "")}</span><b>${n}</b></div>`).join("") || '<div class="empty">Nothing filed in the last 90 days.</div>'}</div></div>
      </div>

      <div class="seg"><h2>The company-website archive</h2><div class="ln"></div><span class="pill">${archiveDocs.length}</span></div>
      <div class="sumstrip s4">
        ${sTile("Downloaded", archiveDocs.length, "from issuer websites")}
        ${sTile("Verified", arVerified, "hash checked on pull")}
        ${sTile("Failed", arFailed, arFailed ? "outlined below" : "")}
        ${sTile("Generic titles", arGeneric, "titled just \"download\" or similar")}
      </div>
      <details class="rs-fold"><summary>Full archive — ${archiveDocs.length} document${archiveDocs.length === 1 ? "" : "s"}</summary><div class="card">${(isSubscribed() ? archiveDocs : archiveDocs.slice(0, 2)).map(aRow).join("") || '<div class="empty">Nothing pulled from issuer websites yet.</div>'}</div></details>

      ${docs.length > 4 ? planWall("The full research library", `${docs.length} digested documents — broker notes, results filings and corporate briefings, each cross-examined with every claim extracted for public scoring.`) : ""}
      <div class="disclaimer">What this page is: a raw evidence library — nothing here is the desk's view. Broker wording inside an expanded call is that broker's wording, credited to the house that wrote it, not the desk's. Educational research, not advice. No performance promises.</div>
      <div class="wl-tip" aria-hidden="true"></div>
    </div>`;

    const root = view.firstElementChild;
    const tip = () => root.querySelector(".wl-tip");
    const showTip = (e, html) => { const t = tip(); if (!t) return; t.innerHTML = html; t.style.display = "block"; t.style.left = Math.max(8, Math.min(e.clientX + 14, innerWidth - 290)) + "px"; t.style.top = (e.clientY + 14) + "px"; };
    const hideTip = () => { const t = tip(); if (t) t.style.display = "none"; };
    root.addEventListener("mousemove", e => { const t = e.target.closest("[data-tip]"); if (t) { showTip(e, esc(t.dataset.tip)); return; } hideTip(); });
    root.addEventListener("mouseleave", hideTip);

    let houseFilter = null;
    root.querySelectorAll(".rs-house").forEach(btn => btn.addEventListener("click", () => {
      houseFilter = houseFilter === btn.dataset.house ? null : btn.dataset.house;
      root.querySelectorAll(".rs-house").forEach(b => { b.classList.toggle("on", b.dataset.house === houseFilter); b.setAttribute("aria-pressed", b.dataset.house === houseFilter ? "true" : "false"); });
      root.querySelector(".rs-calls").innerHTML = (isSubscribed() ? claims : claims.slice(0, 2)).filter(c => !houseFilter || c.source === houseFilter).slice(0, 6).map(c => rsCallRow(c, close, names)).join("") || '<div class="empty">No calls from this house.</div>';
    }));
    const showMoreBtn = root.querySelector(".rs-showmore");
    if (showMoreBtn) showMoreBtn.addEventListener("click", () => {
      root.querySelector(".rs-calls").innerHTML = (isSubscribed() ? claims : claims.slice(0, 2)).filter(c => !houseFilter || c.source === houseFilter).map(c => rsCallRow(c, close, names)).join("");
      showMoreBtn.remove();
    });
    root.querySelectorAll("[data-fam]").forEach(btn => btn.addEventListener("click", () => {
      const on = !btn.classList.contains("on");
      root.querySelectorAll("[data-fam]").forEach(b => b.classList.remove("on"));
      if (on) btn.classList.add("on");
      const fam = on ? btn.dataset.fam : null;
      const pool = fam ? filingDocs.filter(d => rsFamOf(d) === fam) : filingDocs;
      root.querySelector(".rs-latest").innerHTML = (isSubscribed() ? pool : pool.slice(0, 2)).slice(0, 8).map(docRow).join("") || '<div class="empty">Nothing in this family.</div>';
      root.querySelector(".rs-top").innerHTML = topNames(fam).map(([t, n]) => `<div class="rdoc rs-toprow"><span class="tag clickable" onclick="navigate('/ticker/${esc(t)}')">${esc(t)}</span><span class="sub">${esc(names[t] || "")}</span><b>${n}</b></div>`).join("") || '<div class="empty">Nothing filed in the last 90 days.</div>';
    }));
  }
  render();
}
