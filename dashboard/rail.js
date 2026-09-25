/* ============================================================
   Production script — context rail mechanics + content
   Additive only. Linked from dashboard/index.html after app.js.
   Never edits app.js/route() internals — watches #view via
   MutationObserver instead. Mirrors the left sidebar's collapse/
   resize/drawer/no-flash-gate pattern (app.js sidebar block) with
   a second set of keys.
   ============================================================ */
(function () {
  "use strict";

  var shell = document.getElementById("shell");
  var rail = document.getElementById("contextRail");
  if (!shell || !rail) return;

  // Paint loop is wired FIRST, before any of the init below can throw. Everything
  // between here and the end of this IIFE touches localStorage, JSON and app.js
  // globals; one bad value there used to abort the whole file, and the five panes
  // sat on their "Loading…" placeholder forever with nothing in the console to
  // explain it. Function declarations hoist, and the timers fire after the IIFE
  // has finished, so the closures below are populated by the time these run.
  var view = document.getElementById("view");
  if (view) {
    new MutationObserver(function () { refreshRail(); })
      .observe(view, { childList: true, subtree: false });
  }
  function refreshOnNavigation() { setTimeout(refreshRail, 0); }
  window.addEventListener("henneth:navigate", refreshOnNavigation);
  window.addEventListener("popstate", refreshOnNavigation);
  // Initial paint — give app.js's first route() a tick to populate #view. The
  // second pass covers a slow first load where #view was filled before the
  // observer attached, leaving no mutation to react to. Every renderer compares
  // before it writes, so the repeat is a no-op when the first pass worked.
  setTimeout(refreshRail, 50);
  setTimeout(refreshRail, 600);
  // Exposed so a stuck rail can be re-driven from the console: refreshRail().
  window.refreshRail = refreshRail;

  // Every state/*.json read in this file goes through app.js's j(). That is not a
  // convenience — /state/:path* is bearer-gated at the edge (middleware.js:151), and
  // only j() attaches the Supabase token and refreshes it on a 401. A bare fetch()
  // here 401s in production while working fine locally, where the path resolves off
  // disk. j() also owns the per-file TTL, so the rail and the board can no longer
  // disagree about what "current" means, and it never caches a failure.

  var RAIL_MIN = 220, RAIL_MAX = 420;
  var railToggle = document.getElementById("railToggle");
  var railResize = document.getElementById("railResize");
  var railOpen = document.getElementById("railOpen");
  var railBackdrop = document.getElementById("railBackdrop");
  var sideOpen = document.getElementById("sideOpen");

  // ---- collapse ----
  function applyCollapsed(v) {
    shell.classList.toggle("rail-collapsed", v);
    if (railToggle) {
      var action = v ? "Expand panel" : "Collapse panel";
      railToggle.setAttribute("title", action);
      // aria-label names the ACTION, so it has to flip with aria-expanded or a
      // screen reader announces the opposite of what the button now does.
      railToggle.setAttribute("aria-label", action);
      railToggle.setAttribute("aria-expanded", String(!v));
    }
  }
  var collapsed = localStorage.getItem("railCollapsed") === "1";
  applyCollapsed(collapsed);
  if (railToggle) {
    railToggle.addEventListener("click", function () {
      collapsed = !collapsed;
      localStorage.setItem("railCollapsed", collapsed ? "1" : "0");
      applyCollapsed(collapsed);
    });
  }

  // ---- collapsed: the pane is display:none, #railToggle goes with it, so the
  // floating #railPeek glyph is the only way back in. Mirrors shell.js's
  // #sidePeek/#sideToggle pair: delegates to railToggle.click() rather than a
  // second writer of the same collapsed flag. All state above stays the one
  // source of truth. ----
  var railPeek = document.getElementById("railPeek");
  function visible(el) {
    return !!el && el.getClientRects().length > 0;
  }
  function syncRailPeek() {
    if (railPeek) railPeek.setAttribute("aria-expanded", String(!shell.classList.contains("rail-collapsed")));
  }
  if (railPeek && railToggle) {
    railPeek.addEventListener("click", function () {
      railToggle.click();
      syncRailPeek();
      if (visible(railToggle)) railToggle.focus();
    });
    railToggle.addEventListener("click", function () {
      syncRailPeek();
      if (shell.classList.contains("rail-collapsed") && document.activeElement === railToggle) railPeek.focus();
    });
    syncRailPeek();
  }

  // ---- resize (right-anchored: drag distance is inverted vs the left sidebar) ----
  var railW = parseInt(localStorage.getItem("railW"), 10);
  if (!railW || railW < RAIL_MIN || railW > RAIL_MAX) railW = 268;
  document.documentElement.style.setProperty("--rail-w", railW + "px");

  if (railResize) {
    var dragging = false, startX = 0, startW = 0, dragId = null;
    // pointer events, not mouse: the handle sits a few px from the viewport's right
    // edge, so a mouseup released over the browser chrome or off-screen never reaches
    // a window listener and the shell stays stuck in .rail-resizing forever. Capture
    // pins every move/up to the handle itself, and buys touch + pen in the same change.
    // touch-action is set here rather than in the sheet because this pass owns the JS
    // file only — without it the browser claims the gesture for scrolling and the
    // handle never gets a pointermove.
    railResize.style.touchAction = "none";
    railResize.addEventListener("pointerdown", function (ev) {
      if (shell.classList.contains("rail-collapsed") || (ev.pointerType === "mouse" && ev.button !== 0)) return;
      dragging = true; startX = ev.clientX; startW = railW; dragId = ev.pointerId;
      railResize.setPointerCapture(ev.pointerId);
      shell.classList.add("rail-resizing");
      ev.preventDefault();
    });
    railResize.addEventListener("pointermove", function (ev) {
      if (!dragging || ev.pointerId !== dragId) return;
      // rail is anchored to the right edge: dragging left (negative dx) widens it.
      var dx = startX - ev.clientX;
      var w = Math.max(RAIL_MIN, Math.min(RAIL_MAX, startW + dx));
      railW = w;
      document.documentElement.style.setProperty("--rail-w", w + "px");
    });
    // pointercancel is not optional: the OS stealing the gesture (system swipe, a
    // second finger) fires cancel and NEVER up, which is the stuck-drag bug in a
    // new shape, so both endings run the same teardown.
    function endDrag(ev) {
      if (!dragging || ev.pointerId !== dragId) return;
      dragging = false; dragId = null;
      if (railResize.hasPointerCapture(ev.pointerId)) railResize.releasePointerCapture(ev.pointerId);
      shell.classList.remove("rail-resizing");
      localStorage.setItem("railW", String(railW));
    }
    railResize.addEventListener("pointerup", endDrag);
    railResize.addEventListener("pointercancel", endDrag);
  }

  // ---- no-flash gate (mirrors side-ready) ----
  function markReady() { shell.classList.add("rail-ready"); }
  requestAnimationFrame(function () { requestAnimationFrame(markReady); });
  setTimeout(markReady, 300);

  // ---- mobile drawer (mutual exclusion with the left sidebar drawer) ----
  function closeRailDrawer() {
    shell.classList.remove("rail-drawer");
  }
  function openRailDrawer() {
    shell.classList.remove("drawer"); // close left drawer if open
    shell.classList.add("rail-drawer");
  }
  if (railOpen) railOpen.addEventListener("click", openRailDrawer);
  if (railBackdrop) railBackdrop.addEventListener("click", closeRailDrawer);
  if (sideOpen) sideOpen.addEventListener("click", closeRailDrawer, true);
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") closeRailDrawer();
  });
  window.addEventListener("henneth:navigate", closeRailDrawer);
  window.addEventListener("popstate", closeRailDrawer);

  // ============================================================
  // Tab switching
  // ============================================================
  var tabs = rail.querySelector(".rail-tabs");
  var panes = rail.querySelectorAll(".rail-pane");
  function setTab(name) {
    rail.querySelectorAll(".rail-tab").forEach(function (b) {
      var on = b.getAttribute("data-rail-tab") === name;
      b.classList.toggle("on", on);
      b.setAttribute("aria-selected", String(on));
      // roving tabindex (APG tabs): only the selected tab is a tab stop, so Tab
      // enters and leaves the tablist once instead of walking all four buttons.
      b.setAttribute("tabindex", on ? "0" : "-1");
    });
    panes.forEach(function (p) {
      p.classList.toggle("on", p.getAttribute("data-rail-pane") === name);
    });
    localStorage.setItem("railTab", name);
  }
  if (tabs) {
    tabs.addEventListener("click", function (ev) {
      var btn = ev.target.closest(".rail-tab");
      if (!btn) return;
      setTab(btn.getAttribute("data-rail-tab"));
    });
    tabs.addEventListener("keydown", function (ev) {
      var keys = { ArrowLeft: 1, ArrowRight: 1, Home: 1, End: 1 };
      if (!keys[ev.key]) return;
      var list = Array.prototype.slice.call(tabs.querySelectorAll(".rail-tab"));
      if (!list.length) return;
      var i = list.indexOf(ev.target.closest(".rail-tab"));
      if (i === -1) return;
      var next;
      if (ev.key === "Home") next = 0;
      else if (ev.key === "End") next = list.length - 1;
      else next = (i + (ev.key === "ArrowRight" ? 1 : -1) + list.length) % list.length;
      ev.preventDefault();
      setTab(list[next].getAttribute("data-rail-tab"));
      list[next].focus();
    });
  }
  var KNOWN_TABS = { ask: 1, notes: 1, watch: 1, alerts: 1, news: 1 };
  var savedTab = localStorage.getItem("railTab");
  setTab(KNOWN_TABS[savedTab] ? savedTab : "ask");

  // ============================================================
  // News tab — the desk's own news log (state/newslog.json, appended every
  // cycle by the news sentinel from Dawn, Business Recorder, ProPakistani,
  // Mettis, Express Tribune and the PSX/DPS feeds). The rail never scrapes;
  // it only shows what the pipeline already captured, newest day first.
  // ============================================================
  var NEWS_CAP = 80;
  var lastNewsHTML = null;
  function setNewsHTML(html) {
    // BLINK LAW: compare-before-write.
    var pane = rail.querySelector('[data-rail-pane="news"]');
    if (!pane || html === lastNewsHTML) return;
    lastNewsHTML = html;
    pane.innerHTML = html;
  }
  // Only http(s) survives. The log is desk-written, but `url` is the one field
  // in it that becomes a live link — a javascript: value there would run on click.
  function newsHref(u) {
    var s = String(u || "").trim();
    return /^https?:\/\//i.test(s) ? s : "";
  }
  function renderRailNews() {
    j("newslog.json").then(function (data) {
      if (!Array.isArray(data)) {
        setNewsHTML('<div class="empty">News log unavailable.</div>');
        return;
      }
      var items = data
        .filter(function (n) { return n && n.headline; })
        .sort(function (a, b) { return String(b.ts || "").localeCompare(String(a.ts || "")); })
        .slice(0, NEWS_CAP);
      if (!items.length) {
        setNewsHTML('<div class="empty">No news captured yet.</div>');
        return;
      }
      // newslog.json is a bare list with no `updated` field, so the freshest
      // thing the data layer actually knows is the newest item's date. Label it
      // as that, not as a refresh time the file never recorded.
      var html = '<div class="rail-news-head"><span>Latest</span>' +
        '<span class="rail-news-stamp">' + esc(items[0].ts || "—") + "</span></div>";
      var day = null;
      items.forEach(function (n) {
        if (n.ts !== day) {
          day = n.ts;
          html += '<div class="rail-news-day">' + esc(day || "undated") + "</div>";
        }
        var body =
          '<span class="rail-news-title">' + esc(n.headline) + "</span>" +
          '<span class="rail-news-meta"><span class="rail-news-src">' + esc(n.source || "—") + "</span>" +
          (Number(n.impact) >= 4 ? '<span class="rail-news-flag">impact ' + esc(String(n.impact)) + "</span>" : "") +
          (n.tickers && n.tickers.length
            ? '<span class="rail-news-tk">' + esc(n.tickers.slice(0, 4).join(" ")) + "</span>"
            : "") +
          "</span>";
        var href = newsHref(n.url);
        html += href
          ? '<a class="rail-news-item" href="' + esc(href) + '" target="_blank" rel="noopener noreferrer">' + body + "</a>"
          : '<div class="rail-news-item nolink">' + body + "</div>";
      });
      setNewsHTML(html);
    });
  }

  function labelFor(page, arg, path) {
    if (page === "ticker" && arg) return arg;
    var navEl = document.querySelector('[data-nav="' + page + '"]');
    if (navEl && navEl.getAttribute("title")) return navEl.getAttribute("title");
    return path.replace(/^\/+/, "") || "Home";
  }

  // ============================================================
  // Watch tab — watchlist symbols with price / day change, from
  // state/live.json only. SECP: symbol, price, % change — nothing else.
  // ============================================================
  var watchPane = rail.querySelector('[data-rail-pane="watch"]');
  var WATCH_CAP = 12;
  var lastWatchHTML = null;

  function renderRailWatch() {
    if (!watchPane) return;
    if (typeof isSignedIn === "function" && !isSignedIn()) {
      setWatchHTML('<div class="empty">Sign in to keep a watchlist — star any stock and it follows you here.' +
        '<br><br><button type="button" class="auth-go" style="max-width:200px" data-rail-auth="signin">Sign in</button></div>');
      return;
    }
    var list = (typeof watchlist === "function") ? watchlist() : [];
    if (!list.length) {
      setWatchHTML('<div class="empty">Star a company on the <a href="/board">board</a> to watch it.</div>');
      return;
    }
    j("live.json").then(function (data) {
      var tickers = data && data.tickers;
      if (!tickers) {
        setWatchHTML('<div class="empty">Live prices unreachable.</div>');
        return;
      }
      var here = currentTicker();
      var rows = list.slice(0, WATCH_CAP).map(function (sym) {
        var t = tickers[sym];
        var price = "—", chg = "—", chgClass = "";
        if (t && typeof t.current === "number") {
          price = t.current.toFixed(2);
          if (typeof t.ldcp === "number" && t.ldcp) {
            var pct = ((t.current - t.ldcp) / t.ldcp) * 100;
            chgClass = pct > 0 ? "up" : (pct < 0 ? "dn" : "");
            chg = (pct > 0 ? "+" : "") + pct.toFixed(2) + "%";
          }
        } else if (t && typeof t.ldcp === "number") {
          // No live tick. ldcp is the PREVIOUS session's close, so it is a real
          // number from the data layer but it is not the current price —
          // rendering it bare made a closed market look like a live one.
          price = t.ldcp.toFixed(2);
          chg = "close";
        }
        var here_mark = sym === here ? ' <span class="rail-watch-here" title="You are here">●</span>' : "";
        return '<a class="rail-watch-item" href="/ticker/' + encodeURIComponent(sym) + '">' +
          '<span class="rail-watch-sym">' + esc(sym) + here_mark + '</span>' +
          '<span class="rail-watch-price">' + esc(price) + '</span>' +
          '<span class="rail-watch-chg ' + chgClass + '">' + esc(chg) + '</span>' +
          '</a>';
      }).join("");
      setWatchHTML('<div class="rail-watch-list">' + rows + '</div>');
    });
  }
  function setWatchHTML(html) {
    if (!watchPane || html === lastWatchHTML) return;
    lastWatchHTML = html;
    watchPane.innerHTML = html;
  }

  // ============================================================
  // Alerts tab — what fired, on which name, when. Source:
  // state/live_triggers.json { date, updated, triggers: [], alerted: [] }.
  // SECP: never render entry/stop/target/risk-per-share even if present.
  // ============================================================
  var alertsPane = rail.querySelector('[data-rail-pane="alerts"]');
  var ALERTS_CAP = 20;
  var lastAlertsHTML = null;

  function setAlertsHTML(html) {
    if (!alertsPane || html === lastAlertsHTML) return;
    lastAlertsHTML = html;
    alertsPane.innerHTML = html;
  }

  // live_triggers.json carries the day at the file level (`date`) and the clock per
  // trigger (`ts`, written as "%H:%M" by scripts/scan_live.py). Neither alone is an
  // instant, so both are needed — and the PKT offset must be PINNED. A bare
  // "2026-07-12T11:59" is parsed as BROWSER-local: east of PKT it lands in the future
  // and Math.max(0,…) below pins the column to "just now" however stale the file is.
  // "+05:00" is not a quoted datum, it is the declared timezone of these fields
  // (CLAUDE.md); PKT is fixed UTC+5 with no DST, so a literal offset is exact.
  function fmtAlertsAgo(date, ts) {
    if (!date || !ts) return "";
    var t = Date.parse(date + "T" + ts + "+05:00");
    if (isNaN(t)) return "";
    var mins = Math.max(0, Math.round((Date.now() - t) / 60000));
    if (mins < 1) return "just now";
    if (mins < 60) return mins + "m ago";
    var hrs = Math.round(mins / 60);
    if (hrs < 24) return hrs + "h ago";
    return Math.round(hrs / 24) + "d ago";
  }

  function renderRailAlerts() {
    if (!alertsPane) return;
    j("live_triggers.json").then(function (data) {
      if (!data) {
        setAlertsHTML('<div class="empty">Alerts unreachable.</div>');
        return;
      }
      // A file from a previous session is not current data. Without this gate its
      // rows render as if they were firing now. "Nothing has triggered" would be the
      // wrong copy here too — the desk has not scanned today, so whether anything
      // triggered is unknown, and unknown is what it has to say (CLAUDE.md rule 2).
      if (data.date !== todayPKT()) {
        setAlertsHTML('<div class="empty">The desk has not scanned today.' +
          (data.date ? '<br><span class="rail-alert-stamp">Last scan ' + esc(data.date) + "</span>" : "") +
          "</div>");
        return;
      }
      var list = data.triggers;
      if (!list || !list.length) {
        // A bare "Nothing has triggered." is indistinguishable from a pane that
        // never loaded. The stamp proves the file was read, and shows its age —
        // an alerts feed that stopped updating is itself the thing worth seeing.
        var stamp = data.updated || data.date;
        setAlertsHTML('<div class="empty">Nothing has triggered.' +
          (stamp ? '<br><span class="rail-alert-stamp">Checked ' + esc(stamp) + "</span>" : "") +
          "</div>");
        return;
      }
      var rows = list.slice(-ALERTS_CAP).reverse().map(function (t) {
        // scan_live.py writes exactly {ticker, id, name, category, price, ts,
        // backtest, target_pct, stop_pct, hold}. Every other key this used to reach
        // for was invented, which is why the first column was the constant "Trigger".
        // SECP: ticker, strategy name, category and clock only — target_pct/stop_pct
        // sit in the same dict and must never be rendered against a named security.
        var sym = (t && t.ticker) || "—";
        var what = (t && t.name) || "";
        var cat = (t && t.category) || "";
        return '<div class="rail-alert-item">' +
          '<span class="rail-alert-what">' + esc(what) + '</span>' +
          (cat ? '<span class="rail-alert-cat">' + esc(cat.replace(/_/g, " ")) + '</span>' : "") +
          '<span class="rail-alert-sym">' + esc(sym) + '</span>' +
          '<span class="rail-alert-when">' + esc(fmtAlertsAgo(data.date, t && t.ts)) + '</span>' +
          '</div>';
      }).join("");
      setAlertsHTML('<div class="rail-alert-list">' + rows + '</div>');
    });
  }

  // ============================================================
  // Notes tab — a standalone multi-note pad, always available (not gated on a
  // ticker being open). Its own localStorage store, deliberately separate from
  // app.js's per-ticker #tknote card, which stays in #view untouched.
  // ============================================================
  var NOTE_KEY = "railNotes";
  var notesPane = rail.querySelector('[data-rail-pane="notes"]');
  var openNoteId = null;
  var noteSeq = 0;
  var lastNotesHTML = null;

  function readNotes() {
    try {
      var arr = JSON.parse(localStorage.getItem(NOTE_KEY) || "[]");
      return Array.isArray(arr) ? arr : [];
    } catch (e) { return []; }
  }
  function writeNotes(arr) {
    localStorage.setItem(NOTE_KEY, JSON.stringify(arr));
  }
  function sortNotes(arr) {
    return arr.slice().sort(function (a, b) {
      if (!!b.pinned !== !!a.pinned) return b.pinned ? 1 : -1;
      return (b.ts || 0) - (a.ts || 0);
    });
  }
  function findNote(arr, id) {
    for (var i = 0; i < arr.length; i++) if (arr[i].id === id) return arr[i];
    return null;
  }

  function renderNotes() {
    if (!notesPane) return;
    var notes = sortNotes(readNotes());
    var html = '<div class="rail-notes-head"><span>Notes</span>' +
      '<button type="button" class="quiet-btn" data-note-new>+ New note</button></div>';
    if (!notes.length) {
      html += '<div class="empty">No notes yet.</div>';
    } else {
      notes.forEach(function (n) {
        var open = n.id === openNoteId;
        // data-no-i18n on the whole row: everything inside it is the USER'S OWN
        // text (title, preview, and the open editor's input + textarea). The Urdu
        // pass matches on trimmed text and would rewrite a one-word note body in
        // place — and because innerHTML had just built the textarea, its value
        // tracks that text node, so the next keystroke persists the translation
        // over what the user wrote. The row's only chrome (Untitled / Pin note /
        // Delete note) has no dictionary entry, so nothing translatable is lost.
        html += '<div class="rail-note" data-no-i18n data-note-id="' + esc(n.id) + '">' +
          // NOT a <button>: the pin/delete buttons nest inside this row, and the
          // parser's button-in-scope rule would close it early and reparent them.
          '<div class="rail-note-bar">' +
          // The open target is this INNER span, not the row: with role=button on
          // the row, the pin and delete buttons sat inside the control's own hit
          // area and inside its accessible name.
          '<span class="rail-note-open" data-note-open role="button" tabindex="0" aria-expanded="' +
          (open ? "true" : "false") + '">' +
          '<span class="rail-note-pin">' + (n.pinned ? "▪" : "") + "</span>" +
          // data-no-enhance on the two spans the input handler live-patches below:
          // .textContent is a replace-all, so every keystroke fires a childList
          // record on document.body's observer and would queue a whole-document
          // enhancement flush per frame while typing. The attribute goes on the
          // spans, NOT the pane — inert() only drops a batch when EVERY record is
          // inside the region, and renderNotes' innerHTML write targets the pane
          // itself, which must stay enhanceable and translatable.
          '<span class="rail-note-title" data-no-enhance>' + esc(n.title || "Untitled") + "</span>" +
          '<span class="rail-note-ts" data-no-enhance>' + esc(fmtAgo(n.ts)) + "</span>" +
          "</span>" +
          '<span class="rail-note-acts">' +
          // aria-pressed carries the pin state: the ⌖ glyph and the .on tint are both
          // visual-only, so without it a screen reader cannot tell pinned from unpinned.
          '<button type="button" class="rail-note-act' + (n.pinned ? " on" : "") +
          '" data-note-act="pin" aria-pressed="' + (n.pinned ? "true" : "false") +
          '" title="' + (n.pinned ? "Unpin note" : "Pin note") + '" aria-label="' +
          (n.pinned ? "Unpin note" : "Pin note") + '">⌖</button>' +
          '<button type="button" class="rail-note-act" data-note-act="del" title="Delete note" aria-label="Delete note">✕</button>' +
          "</span>" +
          "</div>";
        if (open) {
          html += '<div class="rail-note-edit">' +
            '<input class="rail-note-title-in" data-note-field="title" placeholder="Title" value="' +
            esc(n.title || "") + '">' +
            '<textarea class="rail-note-body-in" data-note-field="body" placeholder="Note">' +
            esc(n.body || "") + "</textarea></div>";
        } else if (n.body) {
          html += '<div class="rail-note-prev">' + esc(n.body) + "</div>";
        }
        html += "</div>";
      });
    }
    // BLINK LAW: compare-before-write — app.js's enhancement MutationObserver
    // watches all of document.body, so an unguarded write here (even from a
    // click handler, not just a timer) still triggers a full-document flush.
    if (html === lastNotesHTML) return;
    lastNotesHTML = html;
    notesPane.innerHTML = html;
  }

  if (notesPane) {
    notesPane.addEventListener("click", function (ev) {
      if (ev.target.closest("[data-note-new]")) {
        var arr = readNotes();
        noteSeq += 1;
        var id = "n" + Date.now() + "-" + noteSeq;
        arr.push({ id: id, title: "", body: "", pinned: false, ts: Date.now() });
        writeNotes(arr);
        openNoteId = id;
        renderNotes();
        var input = notesPane.querySelector('[data-note-field="title"]');
        if (input) input.focus();
        return;
      }
      // the action buttons live INSIDE .rail-note-bar, so they must be tested first
      // or the bar's open/close handler swallows every pin and delete click.
      var act = ev.target.closest("[data-note-act]");
      var row = ev.target.closest(".rail-note");
      if (!row) return;
      var id = row.getAttribute("data-note-id");
      if (act) {
        ev.stopPropagation();
        var list = readNotes();
        if (act.getAttribute("data-note-act") === "pin") {
          var n = findNote(list, id);
          if (n) n.pinned = !n.pinned;
          writeNotes(list);
        } else {
          writeNotes(list.filter(function (x) { return x.id !== id; }));
          if (openNoteId === id) openNoteId = null;
        }
        renderNotes();
        return;
      }
      if (ev.target.closest("[data-note-open]")) {
        openNoteId = openNoteId === id ? null : id;
        renderNotes();
      }
    });

    // .rail-note-bar is a div with role=button, so Enter/Space activation is not
    // free — the browser only supplies it for real buttons.
    notesPane.addEventListener("keydown", function (ev) {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      var bar = ev.target.closest("[data-note-open]");
      if (!bar || ev.target.closest("[data-note-act]")) return;
      ev.preventDefault();
      var row = bar.closest(".rail-note");
      if (!row) return;
      var id = row.getAttribute("data-note-id");
      openNoteId = openNoteId === id ? null : id;
      renderNotes();
    });

    // Typing persists straight to storage and live-patches the bar's title text —
    // re-rendering on every keystroke would rebuild the field and drop the caret.
    notesPane.addEventListener("input", function (ev) {
      var field = ev.target.closest("[data-note-field]");
      if (!field) return;
      var row = ev.target.closest(".rail-note");
      if (!row) return;
      var id = row.getAttribute("data-note-id");
      var list = readNotes();
      var note = findNote(list, id);
      if (!note) return;
      note[field.getAttribute("data-note-field")] = field.value;
      note.ts = Date.now();
      writeNotes(list);
      var titleEl = row.querySelector(".rail-note-title");
      if (titleEl) titleEl.textContent = note.title || "Untitled";
      var tsEl = row.querySelector(".rail-note-ts");
      if (tsEl) tsEl.textContent = fmtAgo(note.ts);
    });

    renderNotes();
  }

  // ============================================================
  // Ask tab — no second fetch layer: repaints app.js's own _ask
  // state (history/busy) via its askThreadHtml()/askSend()/ASK_SAMPLES.
  // ============================================================
  var askPane = rail.querySelector('[data-rail-pane="ask"]');
  function railAskSamplesHtml() {
    var picks = (typeof ASK_SAMPLES !== "undefined" ? ASK_SAMPLES : []).slice(0, 3);
    if (!picks.length) return "";
    return '<div class="rail-ask-samples">' + picks.map(function (q) {
      return '<button type="button" class="rail-ask-chip" data-rail-ask-sample="' + esc(q) + '">' + esc(q) + "</button>";
    }).join("") + "</div>";
  }
  var lastAskThread = null;
  var lastAskCount = 0;
  // The shell (input + send + footer) is rebuilt ONLY when the pane's mode
  // changes. Rewriting askPane.innerHTML on every refresh destroyed and
  // recreated #railAskIn, which threw away whatever the user was mid-way
  // through typing and dropped focus. Mode is the only thing that can
  // legitimately change the shell; the thread repaints inside it.
  function renderRailAsk() {
    if (!askPane) return;
    // Signed out is not a plan gate: a visitor with no account has no plan to
    // upgrade, and telling them to buy one is the wrong door. They go to the
    // auth terminal, same as everywhere else on the desk.
    var signedOut = typeof isSignedIn === "function" && !isSignedIn();
    var locked = !signedOut && typeof hasFeature === "function" && !hasFeature("ask");
    var mode = signedOut ? "out" : locked ? "locked" : "open";

    if (askPane.dataset.askMode !== mode) {
      var shell;
      if (mode === "out") {
        shell = '<div class="empty">Sign in to ask the desk about a ticker, sector, or the market.' +
          '<br><br><button type="button" class="auth-go" style="max-width:200px" data-rail-auth="signin">Sign in</button></div>';
      } else if (mode === "locked") {
        shell = '<div class="empty">Ask needs a plan upgrade. <a href="/plans">See plans &rarr;</a></div>';
      } else {
        // aria-live lives on the status paragraph, not on #railAskOut: the
        // thread is rich markup and a live region over it makes a screen
        // reader re-read the whole conversation on every repaint.
        shell = '<div id="railAskOut" class="rail-ask-out"></div>' +
          '<p id="railAskStatus" class="rail-sr-only" role="status" aria-live="polite"></p>' +
          '<div class="rail-ask-bar">' +
          '<input id="railAskIn" class="rail-ask-in" type="text" inputmode="text" enterkeyhint="send" maxlength="500" placeholder="Ask the desk…" aria-label="Ask the desk">' +
          '<button type="button" class="quiet-btn" data-rail-ask-send>Ask</button>' +
          "</div>" +
          '<div class="rail-ask-foot"><a href="/ask">Open the full page &rarr;</a></div>';
      }
      askPane.innerHTML = shell;
      askPane.dataset.askMode = mode;
      lastAskThread = null;
      lastAskCount = 0;
    }
    if (mode !== "open") return;

    var hist = (typeof _ask !== "undefined" && _ask.history) ? _ask.history : [];
    var busy = typeof _ask !== "undefined" && !!_ask.busy;
    var thread = hist.length ? askThreadHtml() :
      '<div class="empty">Ask the desk about a ticker, sector, or the market.</div>' + railAskSamplesHtml();
    var out = askPane.querySelector("#railAskOut");
    // BLINK LAW: compare-before-write.
    if (out && thread !== lastAskThread) {
      out.innerHTML = thread;
      lastAskThread = thread;
      out.scrollTop = out.scrollHeight;
    }
    var status = askPane.querySelector("#railAskStatus");
    if (status) {
      var msg = busy ? "Asking the desk…" : (hist.length > lastAskCount ? "Answer ready." : status.textContent);
      if (status.textContent !== msg) status.textContent = msg;
    }
    if (!busy) lastAskCount = hist.length;
    var send = askPane.querySelector("[data-rail-ask-send]");
    // Property, not setAttribute: the attribute is ignored once the element
    // has been touched as a property elsewhere, and it never un-disables.
    if (send) send.disabled = busy;
  }
  function railAskSubmit() {
    // Busy check BEFORE clearing: the old order wiped the input and then
    // dropped the question on the floor, so a fast second Enter silently ate
    // what the user typed.
    if (typeof _ask !== "undefined" && _ask.busy) return;
    var input = askPane && askPane.querySelector("#railAskIn");
    var val = input ? input.value : "";
    if (!val.trim()) return;
    if (input) input.value = "";
    askSend(val);
  }
  if (askPane) {
    askPane.addEventListener("click", function (ev) {
      if (ev.target.closest("[data-rail-ask-send]")) { railAskSubmit(); return; }
      var chip = ev.target.closest("[data-rail-ask-sample]");
      if (chip) askSend(chip.getAttribute("data-rail-ask-sample"));
    });
    askPane.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" && ev.target && ev.target.id === "railAskIn") {
        ev.preventDefault();
        railAskSubmit();
      }
    });
    renderRailAsk();
  }
  window.renderRailAsk = renderRailAsk;

  // One delegated handler for every "Sign in" the rail's empty states offer.
  // There is no sign-in route to link to — auth opens as a terminal in place —
  // so these are buttons, and they all land here.
  rail.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-rail-auth]");
    if (!btn) return;
    ev.preventDefault();
    if (typeof openAuth === "function") openAuth(btn.getAttribute("data-rail-auth"));
  });

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // Relative stamp for note rows. Notes are the one thing in the rail the user
  // writes themselves, so the stamp stays coarse and human — an exact clock time
  // on your own scratch note is noise.
  function fmtAgo(ts) {
    var t = Number(ts);
    if (!t) return "";
    var mins = Math.floor((Date.now() - t) / 60000);
    if (mins < 1) return "now";
    if (mins < 60) return mins + "m";
    var hrs = Math.floor(mins / 60);
    if (hrs < 24) return hrs + "h";
    var days = Math.floor(hrs / 24);
    if (days < 7) return days + "d";
    return new Date(t).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  // ============================================================
  // Page-swap detection — MutationObserver on #view, no route() edits.
  // ============================================================
  var lastHref = null;
  function appPath() { return window.appPathname ? window.appPathname() : location.pathname; }
  function currentTicker() {
    var m = /^\/ticker\/([A-Za-z0-9.]+)/.exec(appPath() || "");
    return m ? m[1].toUpperCase() : null;
  }
  function currentPage() {
    var h = (appPath() || "/today").replace(/^\/+/, "");
    return h.split("/")[0] || "today";
  }
  // ============================================================
  // Page Info strip — persistent doc-block header above the pane
  // switcher. Shows only the current page/ticker name; the strip
  // has no timestamp, Type, or Source rows.
  // ============================================================
  var pageInfoName = document.getElementById("railPageInfoName");
  function renderPageInfo(sym) {
    if (!pageInfoName) return;
    var page = currentPage();
    var label = sym || labelFor(page, sym, appPath() || "/today");
    pageInfoName.textContent = label;
  }

  // ---- Data-health chip, appended into the page-info head strip ----
  var healthChip = null;
  var lastHealthText = null;
  function renderHealthChip() {
    j("health.json").then(function (data) {
      var head = pageInfoName && pageInfoName.parentNode;
      if (!head) return;
      if (!data || !data.status) {
        if (healthChip) { healthChip.remove(); healthChip = null; lastHealthText = null; }
        return;
      }
      var status = String(data.status);
      if (status === lastHealthText) return;
      lastHealthText = status;
      if (!healthChip) {
        healthChip = document.createElement("span");
        healthChip.className = "rail-health-chip";
        head.appendChild(healthChip);
      }
      healthChip.textContent = status;
      healthChip.className = "rail-health-chip" + (status === "ok" ? " ok" : " bad");
    });
  }

  // Each pane paints independently. One renderer throwing must never leave the
  // other four frozen on their pre-render placeholder — that ships a dead panel
  // to the user with no clue why. Failure is per-pane, loud in the console, and
  // recorded on window so the panel check in index.html can print the reason on
  // screen for anyone who never opens a console.
  function safe(label, fn) {
    try {
      fn();
    } catch (err) {
      console.error("[rail] " + label + " failed:", err);
      if (!window.__shellFail) window.__shellFail = label + " pane: " + (err && err.message ? err.message : err);
    }
  }

  function refreshRail() {
    var href = appPath() + location.search || "/today";
    var sym = currentTicker();
    safe("news", renderRailNews);
    lastHref = href;
    // renderNotes is NOT called here on purpose — the notes pad is page-independent,
    // and repainting it on every route change would blow away an in-progress edit.
    safe("pageinfo", function () { renderPageInfo(sym); });
    // No focus/value guard needed: renderRailAsk repaints the thread only and
    // never touches #railAskIn unless the pane's MODE changed.
    safe("ask", renderRailAsk);
    safe("watch", renderRailWatch);
    safe("alerts", renderRailAlerts);
    safe("health", renderHealthChip);
  }
})();
