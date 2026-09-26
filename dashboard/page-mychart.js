// mychart page (Your chart) — redesign 2026-09
// Behaviour/markup parity source: old pageMyChart (app.js lines 2264-2430, removed there, kept in
// git history) — moved here verbatim except for the additive pieces called out below. Every real
// helper it depends on (birthData/natalChart, pixelGlyph/PIXEL_GRAHAS, natalOrrery, synastry,
// stockTiming, resonanceWithGraha, goalLens, dashaTimeline/antardashaStrip, gocharaRead/skyOn/
// upcomingShifts, isSubscribed/deskMode/planWall, FREE_MATCHES, esc/$/j) stays a shared global in
// app.js and is reused unmodified — nothing here re-derives any of it.
// Visual source: the README "Your chart" section + docs/redesign-mockups/mychart-mockup.html asked
// for pixel planet icons, a 3D wheel, a coloured interactive hero, an "IN <SIGN> AT BIRTH" chip
// strip, and two-way highlight between the chips and the wheel. The pixel icons and the tilted 3D
// wheel already existed (natalOrrery()/pixelGlyph(), app.js) and are reused, not rebuilt. This file
// adds only what was genuinely missing: the gradient hero on the Moon-sign headline (.mc-sign,
// page-mychart.css), the chip strip + its mcHighlight() two-way toggle with the wheel (data-g
// attributes on the wheel elements were added directly in natalOrrery(), app.js — this file only
// consumes them), and the .mc-page CSS scope (page-mychart.css) matching the .st-page/.cmp-page
// convention used by the other ported pages.
// Real data only: every number/sign/date below comes from state/ via j() or the already-computed
// natal chart (natalChart()); nothing here is sample/mockup data. Missing data renders "unknown"
// via the same helpers the old page used (esc(), the "—" placeholders already in the old markup).
// No advice language: output reads "the setup"/"the tradition's read", never "you should buy".

function mcHighlight(g) {
  const page = document.querySelector(".mc-page");
  if (!page) return;
  const chip = page.querySelector(`.mc-chip[data-g="${g}"]`);
  const already = chip && chip.classList.contains("hl");
  page.querySelectorAll(".hl").forEach(el => el.classList.remove("hl"));
  const orrery = page.querySelector(".orrery");
  if (already) { orrery && orrery.classList.remove("mc-dim"); return; }
  page.querySelectorAll(`[data-g="${g}"]`).forEach(el => el.classList.add("hl"));
  orrery && orrery.classList.add("mc-dim");
}

async function pageMyChart() {
  // yield one microtask: the initial route() runs before `let me` initializes further down the
  // file, and unlike other pages this one reads `me` before its first data await. This defers that
  // read past the synchronous module evaluation, avoiding a temporal-dead-zone error on cold load.
  await Promise.resolve();
  const bd = birthData(), nc = natalChart();
  if (!bd || !nc || nc.error) {
    $("view").innerHTML = `<div class="today-page mc-page">
      <div class="seg" style="margin-top:4px"><h2>Your chart</h2><div class="ln"></div><span class="pill">personal</span></div>
      <div class="disclaimer">Astrological exploration, not investment advice. A lens to read your own chart against the market — never a reason to buy.</div>
      <div class="card mychart-cta">
        <div class="mc-hero">${["Sun", "Moon", "Jupiter", "Saturn"].map(b => pixelGlyph(b, 30)).join("")}</div>
        <h2>Read the whole market against your birth chart</h2>
        <p class="sub">Vedic astrology has always matched two charts for compatibility. The desk turns that on the market: give it your birth details and it reads every PSX name against your stars — which your chart runs harmonious with, which it finds testing, and the periods your own dasha lights up.</p>
        <button class="bw-go" onclick="openBirthWizard()">Cast my birth chart →</button>
        <p class="sub" style="margin-top:10px;opacity:.7">Takes a minute. Your birth details stay private to your account.</p>
      </div></div>`;
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

  // ---- "IN <SIGN> AT BIRTH" chip strip: one chip per graha plus the ascendant, each toggling a
  // two-way highlight with the matching data-g element on the wheel (natalOrrery, app.js). New —
  // nothing in the old page had this; the underlying data (nc.grahas[b].sign / nc.ascendant.sign)
  // is the same real natal chart the wheel already renders.
  const chipStrip = `<div class="mc-chips">${ORBIT_ORDER.filter(b => nc.grahas[b]).map(b =>
    `<button type="button" class="mc-chip" data-g="${b}" style="--g:var(--g-${b})" onclick="mcHighlight('${b}')">${pixelGlyph(b, 14)}<b>${esc(b)}</b> ${esc(nc.grahas[b].sign)}</button>`).join("")}${
    asc ? `<button type="button" class="mc-chip" data-g="Asc" style="--g:var(--g-Asc)" onclick="mcHighlight('Asc')"><b>ASC</b> ${esc(asc.sign)}</button>` : ""}</div>`;

  $("view").innerHTML = `<div class="today-page mc-page">
  <div class="seg" style="margin-top:4px"><h2>Your chart</h2><div class="ln"></div><span class="pill">${esc(bd.place || "")} · ${esc(bd.date || "")}</span></div>
  <div class="disclaimer">Astrological exploration, <b>not investment advice</b>. A lens to read your chart against the market as the tradition would — never a recommendation to buy or a forecast of profit.</div>

  <div class="card">
    <div class="mc-chart-top"><div>
      <div class="ark">Your Moon</div><b class="mc-sign" style="font-size:18px">${esc(moon.sign)} · ${esc(moon.nakshatra)}</b>
      <div class="sub">${asc ? `Rising sign ${esc(asc.sign)}` : "Chandra lagna · a Moon-led chart"}</div>
    </div>
    <div><div class="ark">Your current period</div><b style="font-size:18px">${pixelGlyph(cur.lord, 18)} ${esc(cur.lord || "—")}${cur.antar ? ` / ${esc(cur.antar)}` : ""} dasha</b>
      <div class="sub">${cur.antar ? `${esc(cur.antar)} sub-period to ~${esc(String(cur.antar_to || "").slice(0, 7))} · ` : ""}${esc(cur.lord || "")} maha to ~${esc(String(cur.to || "").slice(0, 7))}</div></div>
    </div>
    <p class="ark" style="margin-top:10px">in sign, at birth</p>
    ${chipStrip}
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

  <p class="sub" style="margin-top:14px"><button class="note-save" onclick="openBirthWizard()">Edit my birth details</button> · Your resonance map is astrological interpretation — a lens for exploration and your own decisions, never advice.</p>
  </div>`;
}
