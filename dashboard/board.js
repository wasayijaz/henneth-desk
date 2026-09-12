/* ============================================================
   Production script — Board centre-pane renderer.
   Repaints #view on /board with the reference layout from
   dashboard/psx-board-preview.html: .board-head, the 5-cell
   .market-strip, and the .board-grid tile set
   (strategy / universe / news / market / indices).

   Data discipline (CLAUDE.md rule 2): the reference's figures are
   mock and are NOT carried over. Every number below is derived
   from state/ at render time. Where the reference shows a field
   the data layer does not have (share Volume, a 52-week high, a
   per-headline HH:MM), the nearest REAL field is shown instead
   and the column is relabelled — nothing is invented.

   SECP (Reg 2(ha), see app.js:566): no entry / stop / target /
   risk-per-share on a named security. strategy_map.json carries
   target_pct and stop_pct — they are deliberately never painted.

   Loads after app.js as a classic script (dashboard/index.html
   loads it after rail.js/topbar.js, before shell.js), so app.js's
   top-level j() loader, its cache, and esc/fmt/sgn/IDX_LABEL are
   in scope. No second fetch layer.
   ============================================================ */

(function () {
  "use strict";

  var VIEW = document.getElementById("view");
  if (!VIEW) return;

  function onBoard() {
    var path = window.appPathname ? window.appPathname() : location.pathname;
    return (path || "/").replace(/^\/+|\/+$/g, "").split(/[?/]/)[0] === "board";
  }

  // ---- formatting ------------------------------------------------
  var WD = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  var MO = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function stamp(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}:\d{2}))?/.exec(s || "");
    if (!m) return s || "—";
    var d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    return WD[d.getUTCDay()] + ", " + (+m[3]) + " " + MO[+m[2] - 1] + " " + m[1] +
      (m[4] ? " · " + m[4] + " PKT" : "");
  }
  function shortDate(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || "");
    return m ? (+m[3]) + " " + MO[+m[2] - 1] : (s || "—");
  }
  function money(v) {
    if (v == null) return "—";
    var a = Math.abs(v);
    if (a >= 1e9) return fmt(v / 1e9, 2) + "B";
    if (a >= 1e6) return fmt(v / 1e6, 2) + "M";
    if (a >= 1e3) return fmt(v / 1e3, 1) + "K";
    return fmt(v, 0);
  }
  function pctCell(v) {
    if (v == null) return "<td>—</td>";
    var k = v > 0 ? "up" : v < 0 ? "down" : "";
    var g = v > 0 ? "▲ " : v < 0 ? "▼ " : "";
    return '<td class="' + k + '">' + g + fmt(Math.abs(v), 2) + "%</td>";
  }
  function pctText(v) {
    return v == null ? "—" : sgn(+v.toFixed(2)) + "%";
  }

  // ---- derivations ----------------------------------------------
  // Daily move is authoritative PSX board metadata exposed by app.js. Missing or inconsistent
  // metadata stays unknown; this renderer must not reconstruct it from append-only history.
  function indexRows(idx) {
    var live = (idx && idx.live) || {};
    return Object.keys(IDX_LABEL).filter(function (k) { return typeof live[k] === "number" && isFinite(live[k]) && live[k] > 0; }).map(function (k) {
      var daily = typeof window.HennethIndexDailyChange === "function"
        ? window.HennethIndexDailyChange(idx, k) : null;
      return {
        key: k, label: IDX_LABEL[k][0], sub: IDX_LABEL[k][1], value: live[k],
        abs: daily ? daily.change : null,
        chg: daily ? daily.percent : null
      };
    });
  }

  function signalRows(dash) {
    return (dash.signals || []).slice(0, 5).map(function (s) {
      var d = /^(\d{4})(\d{2})(\d{2})-/.exec(s.id || "");
      var b = s.backtest || {};
      return {
        sym: s.ticker,
        thesis: s.thesis || s.template || "",
        strat: s.template || s.strategy || "",
        score: b.hit_rate != null ? Math.round(b.hit_rate * 100) : null,
        when: d ? shortDate(d[1] + "-" + d[2] + "-" + d[3]) : shortDate(dash.updated)
      };
    });
  }

  function provenRows(smap) {
    var t = (smap && smap.tickers) || {};
    var out = [];
    Object.keys(t).forEach(function (sym) {
      (t[sym] || []).forEach(function (s) {
        out.push({
          sym: sym,
          thesis: (s.name || s.id || "") + " · " + fmt(s.net_expectancy_pct, 2) + "% net per trade over " + s.n + " trades",
          strat: s.category || "",
          score: s.hit_rate != null ? Math.round(s.hit_rate * 100) : null,
          when: shortDate(smap.updated),
          exp: s.net_expectancy_pct == null ? -99 : s.net_expectancy_pct
        });
      });
    });
    return out.sort(function (a, b) { return b.exp - a.exp; }).slice(0, 5);
  }

  function predictRows(pred) {
    var t = (pred && pred.tickers) || {};
    return Object.keys(t).map(function (sym) {
      var p = t[sym] || {}, best = null;
      Object.keys(p.patterns || {}).forEach(function (k) {
        var v = p.patterns[k];
        if (v && v.n >= 10 && (!best || v.hit_rate > best.hit_rate)) best = { name: k, hit_rate: v.hit_rate, n: v.n };
      });
      return {
        sym: sym,
        thesis: best
          ? best.name.replace(/_/g, " ") + " wins " + Math.round(best.hit_rate * 100) + "% over " + best.n + " signals"
          : "no pattern with 10+ signals on file",
        strat: "predictability",
        score: p.score != null ? Math.round(p.score) : null,
        when: shortDate(pred.updated)
      };
    }).sort(function (a, b) { return (b.score || 0) - (a.score || 0); }).slice(0, 5);
  }

  function triggerRows(trig) {
    return ((trig && trig.triggers) || []).slice(0, 5).map(function (x) {
      return {
        // scan_live.py emits {ticker,id,name,category,price,ts,backtest,...} and
        // nothing else — reason/note/symbol/strategy never existed, so both text
        // columns were permanently blank / stuck on the "live trigger" fallback.
        sym: x.ticker || "—",
        thesis: x.name || "",
        strat: x.category || "",
        score: null,
        when: shortDate(trig.date || trig.updated)
      };
    });
  }

  function quantRows(quant) {
    var t = (quant && quant.tickers) || {};
    return Object.keys(t).map(function (s) {
      var q = t[s] || {};
      return {
        sym: s, close: q.close, d1: q.ret_1d, d20: q.ret_20d,
        val: q.avg_daily_traded_value, near: q.dist_to_20d_high_pct
      };
    }).filter(function (r) { return r.close != null; });
  }

  // ---- markup ----------------------------------------------------
  // The row's whole job is navigate("/ticker/SYM"), so the symbol cell is a
  // real anchor: keyboard and screen-reader users get the route with no JS at all,
  // and the row click stays as a mouse-only convenience on top of it.
  function symCell(sym) {
    return '<td><a class="sym-link" href="/ticker/' + encodeURIComponent(sym) + '"><strong>' + esc(sym) + "</strong></a></td>";
  }

  function researchTable(rows) {
    if (!rows.length) return '<div class="tile-empty">Nothing on file for this view in the current cycle.</div>';
    return '<table class="research-table"><thead><tr><th>Idea</th><th>Thesis</th><th>Strategy</th><th>Score</th><th>Last updated</th></tr></thead><tbody>' +
      rows.map(function (r) {
        return '<tr class="clickable" data-sym="' + esc(r.sym) + '">' +
          symCell(r.sym) +
          "<td>" + esc(r.thesis) + "</td>" +
          "<td>" + esc(r.strat) + "</td>" +
          "<td>" + (r.score != null ? '<span class="score">' + r.score + "</span>" : "—") + "</td>" +
          "<td>" + esc(r.when) + "</td></tr>";
      }).join("") + "</tbody></table>";
  }

  function marketTable(rows) {
    if (!rows.length) return '<div class="tile-empty">No prices on file this cycle.</div>';
    return '<table class="data-table"><thead><tr><th>Symbol</th><th>Price</th><th>1 D %</th><th>20 D %</th><th>Value (PKR)</th></tr></thead><tbody>' +
      rows.map(function (r) {
        var k = r.d1 > 0 ? " pos" : r.d1 < 0 ? " neg" : "";
        return '<tr class="clickable' + k + '" data-sym="' + esc(r.sym) + '">' +
          symCell(r.sym) +
          "<td>" + fmt(r.close, 2) + "</td>" + pctCell(r.d1) + pctCell(r.d20) +
          "<td>" + money(r.val) + "</td></tr>";
      }).join("") + "</tbody></table>";
  }

  // Per-ticker Universe grid: bold symbol + colored 1-day % change, sorted
  // strongest to weakest, background magnitude-scaled per cell.
  function tickerHeatHtml(quant) {
    var t = (quant && quant.tickers) || {};
    var rows = Object.keys(t).map(function (s) { return { sym: s, chg: t[s].ret_1d }; })
      .filter(function (r) { return r.chg != null; })
      .sort(function (a, b) { return b.chg - a.chg; });
    if (!rows.length) return '<div class="tile-empty">No universe data available this cycle.</div>';
    return '<div class="heat">' + rows.map(function (r) {
      var a = Math.min(Math.abs(r.chg) / 5, 1) * 0.5;
      var col = r.chg > 0.05 ? "var(--up)" : r.chg < -0.05 ? "var(--dn)" : null;
      var bg = col ? ' style="background:color-mix(in srgb, ' + col + ' ' + Math.round(a * 100) + '%, transparent)"' : "";
      return '<div class="cell clickable" data-sym="' + esc(r.sym) + '"' + bg + '><b>' + esc(r.sym) + '</b><span class="num ' + cls(r.chg) + '">' + sgn(r.chg) + '%</span></div>';
    }).join("") + "</div>";
  }

  // Roving tabindex: only the selected tab is in the tab order, so Tab reaches the
  // tabset once and Arrow/Home/End move within it (WAI-ARIA tabs pattern).
  function tabs(id, labels) {
    return '<div class="research-tabs" role="tablist" data-tabset="' + id + '" aria-label="' + esc(id) + ' views">' +
      labels.map(function (l, i) {
        return '<button type="button" class="research-tab" role="tab" id="tab-' + id + "-" + i +
          '" aria-controls="tabpanel-' + id + '" aria-selected="' + (i === 0) +
          '" tabindex="' + (i === 0 ? "0" : "-1") + '" data-tab="' + i + '">' + esc(l) + "</button>";
      }).join("") + "</div>";
  }

  // The switched body is the tabpanel the tabs point at; tabindex="0" so a keyboard
  // user can move off the tab strip into the table it just swapped in.
  function tabPanel(id, html) {
    return '<div class="tabset-body" role="tabpanel" id="tabpanel-' + id +
      '" aria-labelledby="tab-' + id + '-0" tabindex="0" data-tabset-body="' + id + '">' + html + "</div>";
  }

  // rendered tab bodies, kept so switching a tab never refetches
  var TABSETS = {};

  function render(d) {
    var idx = indexRows(d.idx);
    var strip = idx.slice(0, 5);
    var qr = quantRows(d.quant);
    var news = (Array.isArray(d.news) ? d.news : []).slice(-8).reverse();

    TABSETS.strategy = [
      researchTable(signalRows(d.dash)),
      researchTable(provenRows(d.smap)),
      researchTable(predictRows(d.pred)),
      researchTable(triggerRows(d.trig))
    ];
    TABSETS.market = [
      marketTable(qr.slice().sort(function (a, b) { return (b.d1 == null ? -99 : b.d1) - (a.d1 == null ? -99 : a.d1); })),
      marketTable(qr.slice().sort(function (a, b) { return (a.d1 == null ? 99 : a.d1) - (b.d1 == null ? 99 : b.d1); })),
      marketTable(qr.slice().sort(function (a, b) { return (b.val || 0) - (a.val || 0); })),
      marketTable(qr.filter(function (r) { return r.near != null; }).sort(function (a, b) { return a.near - b.near; }))
    ];

    var html =
      '<div class="board-view">' +
      '<header class="board-head">' +
      "<div>" +
      '<div class="board-title">PSX Board</div>' +
      "</div>" +
      '<div class="board-actions">' +
      '<a class="quiet-btn" href="/today" aria-label="Open today\'s note">⋮</a>' +
      "</div></header>" +

      '<section class="market-strip" aria-label="Market overview">' +
      (strip.length ? strip.map(function (r) {
        var k = r.chg == null ? "" : r.chg > 0 ? "up" : r.chg < 0 ? "down" : "";
        return '<div class="market-stat" title="' + esc(r.label) + " — " + esc(r.sub) + '">' +
          '<div class="market-label">' + esc(r.label) + "</div>" +
          '<div class="market-value">' + fmt(r.value, 0) + "</div>" +
          '<div class="market-change ' + k + '">' +
          (r.chg == null ? "daily change unavailable" : sgn(+r.abs.toFixed(2)) + " · " + pctText(r.chg)) +
          "</div></div>";
      }).join("") : '<div class="tile-empty">No index values on file.</div>') +
      "</section>" +

      '<div class="board-grid">' +

      '<div class="board-col">' +

      '<section class="tile strategy-tile" data-tile="strategy">' +
      '<div class="tile-head"><h2 class="tile-title">Strategy Research</h2>' +
      '<span class="tile-meta">' + (d.dash.signals || []).length + " on file</span></div>" +
      '<div class="tile-body">' +
      tabs("strategy", ["Signals", "Proven Strategies", "Predictability", "Live Triggers"]) +
      tabPanel("strategy", TABSETS.strategy[0]) +
      '<a class="tile-link" href="/research">View all research →</a>' +
      "</div></section>" +

      '<section class="tile news-tile" data-tile="news">' +
      '<div class="tile-head"><h2 class="tile-title">News wire</h2>' +
      '<span class="tile-meta">' + (Array.isArray(d.news) ? d.news.length : 0) + " logged</span></div>" +
      '<div class="tile-body news-list">' +
      (news.length ? news.map(function (n) {
        return '<div class="news-row">' +
          '<span class="news-time">' + esc(shortDate(n.ts)) + "</span>" +
          '<span class="news-source" title="' + esc(n.source || "") + '">' + esc(n.source || "—") + "</span>" +
          '<span class="news-text">' + esc(n.headline || "") + "</span>" +
          (externalLink(n.url, "↗", 'class="news-open" aria-label="Open source"') || '<span class="news-open">·</span>') +
          "</div>";
      }).join("") : '<div class="tile-empty">No headlines logged.</div>') +
      '<a class="tile-link" href="/news">View all news →</a>' +
      "</div></section>" +

      "</div>" +

      '<div class="board-col">' +

      '<section class="tile universe-tile" data-tile="universe">' +
      '<div class="tile-head"><h2 class="tile-title">Universe</h2></div>' +
      '<div class="tile-body">' +
      '<div class="sub">day move · click any name</div>' +
      '<div class="tile-scroll"><div id="heatHost">' + tickerHeatHtml(d.quant) + "</div></div>" +
      "</div></section>" +

      '<section class="tile market-tile" data-tile="market">' +
      '<div class="tile-head"><h2 class="tile-title">Market Data</h2>' +
      '<span class="tile-meta">' + qr.length + " covered</span></div>" +
      '<div class="tile-body">' +
      tabs("market", ["Leaders", "Laggards", "Most Active", "Near 20 D High"]) +
      '<div class="tile-scroll">' + tabPanel("market", TABSETS.market[0]) + "</div>" +
      "</div></section>" +

      '<section class="tile indices-tile" data-tile="indices">' +
      '<div class="tile-head"><h2 class="tile-title">Indices</h2>' +
      '<span class="tile-meta">' + idx.length + "</span></div>" +
      '<div class="tile-body">' +
      '<div class="tile-scroll">' +
      (idx.length
        ? '<table class="data-table"><thead><tr><th>Index</th><th>Value</th><th>1 D %</th></tr></thead><tbody>' +
        idx.map(function (r) {
          var k = r.chg > 0 ? " pos" : r.chg < 0 ? " neg" : "";
          return '<tr class="' + k.trim() + '"><td>' + esc(r.label) + "</td><td>" + fmt(r.value, 0) + "</td>" + pctCell(r.chg) + "</tr>";
        }).join("") + "</tbody></table>"
        : '<div class="tile-empty">No index values on file.</div>') +
      "</div>" +
      "</div></section>" +

      "</div>" +

      "</div></div>";

    VIEW.innerHTML = html;
  }

  // ---- load + paint ----------------------------------------------
  function get(p) { return j(p).catch(function () { return null; }); }

  // `restage` is not belt-and-braces: app.js's route() rewrites #view while this
  // paint's seven fetches are still in flight (that is the normal order — its gate
  // and page renders are cheap, ours waits on the network). The observer fires
  // during that window, gets swallowed by `painting`, and no further mutation ever
  // comes — so without this the Board silently stays app.js's. Re-run once instead.
  var painting = false, restage = false;
  function paint() {
    if (!onBoard()) return;
    if (painting) { restage = true; return; }
    if (VIEW.querySelector(":scope > .board-view")) return; // already ours
    painting = true;
    restage = false;
    Promise.all([
      get("indices.json"), get("dashboard.json"), get("quant.json"),
      get("newslog.json"), get("strategy_map.json"), get("predictability.json"), get("live_triggers.json")
    ]).then(function (r) {
      if (!onBoard()) return;
      render({
        idx: r[0] || {}, dash: r[1] || {}, quant: r[2] || {},
        news: r[3] || [], smap: r[4] || {}, pred: r[5] || {}, trig: r[6] || {}
      });
    }).catch(function (e) {
      console.error("[board-preview] render failed", e);
    }).then(function () {
      painting = false;
      if (restage) paint();
    });
  }

  // ---- interaction ------------------------------------------------
  function selectTab(tab) {
    var strip = tab.closest('[role="tablist"]');
    if (!strip) return;
    var id = strip.getAttribute("data-tabset");
    strip.querySelectorAll(".research-tab").forEach(function (b) {
      var on = b === tab;
      b.setAttribute("aria-selected", String(on));
      b.tabIndex = on ? 0 : -1;
    });
    var body = VIEW.querySelector('[data-tabset-body="' + id + '"]');
    if (!body) return;
    if (TABSETS[id]) body.innerHTML = TABSETS[id][+tab.getAttribute("data-tab")] || "";
    // the panel is labelled by whichever tab is showing it
    body.setAttribute("aria-labelledby", tab.id);
  }

  VIEW.addEventListener("click", function (e) {
    var tab = e.target.closest(".research-tab");
    if (tab) {
      selectTab(tab);
      return;
    }
    var row = e.target.closest("tr.clickable, .cell.clickable");
    if (row && row.getAttribute("data-sym")) {
      // the symbol cell is a real anchor and already routes; this row handler is
      // only the mouse-only convenience on the rest of the row
      if (e.target.closest("a")) return;
      navigate("/ticker/" + encodeURIComponent(row.getAttribute("data-sym")));
      return;
    }
    // reference behaviour: selecting a tile must not fight its own controls
    var tile = e.target.closest("[data-tile]");
    if (tile) {
      if (e.target.closest("button, select, a")) return;
      var on = tile.classList.contains("is-selected");
      VIEW.querySelectorAll("[data-tile].is-selected").forEach(function (t) { t.classList.remove("is-selected"); });
      tile.classList.toggle("is-selected", !on);
    }
  });

  VIEW.addEventListener("keydown", function (e) {
    var tab = e.target.closest && e.target.closest(".research-tab");
    if (!tab) return;
    var strip = tab.closest('[role="tablist"]');
    if (!strip) return;
    var all = Array.prototype.slice.call(strip.querySelectorAll(".research-tab"));
    var i = all.indexOf(tab), next = null;
    if (e.key === "ArrowRight") next = all[(i + 1) % all.length];
    else if (e.key === "ArrowLeft") next = all[(i - 1 + all.length) % all.length];
    else if (e.key === "Home") next = all[0];
    else if (e.key === "End") next = all[all.length - 1];
    if (!next) return;
    e.preventDefault();
    selectTab(next);
    next.focus();
  });

  // ---- re-apply, same pattern as topbar.js -----------------
  var pending = false;
  new MutationObserver(function () {
    if (pending) return;
    pending = true;
    requestAnimationFrame(function () { pending = false; paint(); });
  }).observe(VIEW, { childList: true, subtree: true });

  function repaintOnNavigation() { setTimeout(paint, 60); }
  window.addEventListener("henneth:navigate", repaintOnNavigation);
  window.addEventListener("popstate", repaintOnNavigation);
  setTimeout(paint, 60);
})();
