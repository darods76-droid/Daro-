/* ForexWatch – Oberflaeche.
   Grundsatz: eine grosse Aussage (der Tacho), ein Satz Klartext, drei Kurse.
   Alles Weitere erklaert, warum – ohne Prozentzahlen und Fachbegriffe. */
(function () {
  "use strict";

  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  };

  var state = { setups: [], status: {}, symbol: null, timeframe: null, chart: null };

  // ------------------------------------------------------------ Formate

  function digits(sym) { return /JPY/.test(sym || "") ? 3 : 5; }
  function px(v, sym) { return v == null ? "–" : Number(v).toFixed(digits(sym)); }
  function clock(ts) {
    return new Date(ts * 1000).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  }
  // Alle Uhrzeiten in der Zeitzone des Rechners. Intern rechnet das System
  // in UTC, weil der Devisenmarkt danach getaktet ist – auf dem Bildschirm
  // soll aber die eigene Uhr stehen.
  function evTime(iso) {
    return new Date(iso).toLocaleString("de-DE",
      { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  }
  function zoneName() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "lokale Zeit";
    } catch (e) {
      return "lokale Zeit";
    }
  }
  function de(n, d) {
    return Number(n).toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d });
  }

  /** Farbklasse zum Tachowert: gruen kaufen, rot verkaufen, grau abwarten. */
  function tone(score) {
    if (score >= 61) { return "buy"; }
    if (score <= 40) { return "sell"; }
    return "wait";
  }
  function toneColor(score) {
    if (score >= 82) { return "var(--buy)"; }
    if (score >= 61) { return "var(--buy-weak)"; }
    if (score <= 19) { return "var(--sell)"; }
    if (score <= 40) { return "var(--sell-weak)"; }
    return "var(--wait)";
  }

  function current() {
    for (var i = 0; i < state.setups.length; i++) {
      if (state.setups[i].symbol === state.symbol) { return state.setups[i]; }
    }
    return null;
  }

  // ---------------------------------------------------------- Kopfzeile

  function renderStatus() {
    var s = state.status;
    if (!s.pairs) { return; }
    var loud = 0;
    for (var i = 0; i < state.setups.length; i++) {
      var t = state.setups[i].tension;
      if (t === "Hohe Spannung" || t === "Bewegung laeuft") { loud++; }
    }
    $("statusbar").innerHTML =
      '<span>Markt <b style="color:' + (s.market_open ? "var(--buy)" : "var(--sell)") + '">' +
        (s.market_open ? "offen" : "geschlossen") + '</b></span>' +
      '<span>' + esc(s.session || "") + '</span>' +
      '<span>Unter Spannung <b>' + loud + '</b></span>' +
      '<span>Kurse von <b>' + esc(s.provider === "capital" ? "Capital.com" : s.provider) + '</b></span>' +
      '<span>Zuletzt gepr&uuml;ft <b>' + (s.last_scan ? clock(s.last_scan) : "–") + '</b></span>' +
      '<span title="Alle Uhrzeiten in deiner Zeitzone">Zeiten in <b>' + esc(zoneName()) + '</b></span>';
  }

  // ---------------------------------------------------------- Wachliste

  function renderPairs() {
    var ul = $("pairs");
    ul.innerHTML = "";
    state.setups.forEach(function (s) {
      var cls = tone(s.score);
      var hot = (s.tension === "Hohe Spannung" || s.tension === "Bewegung laeuft");
      var li = document.createElement("li");
      li.innerHTML =
        '<button class="pair ' + cls + '" type="button" data-sym="' + esc(s.symbol) + '"' +
        ' aria-current="' + (s.symbol === state.symbol) + '">' +
          '<span class="pair-top">' +
            '<span class="pair-sym">' + esc(s.symbol) + '</span>' +
            '<span class="pair-score" style="color:' + toneColor(s.score) + '">' + s.score + '</span>' +
          '</span>' +
          '<span class="pair-mid">' +
            '<span class="pair-act" style="color:' + toneColor(s.score) + '">' + esc(s.action) + '</span>' +
            '<span class="pair-px">' + px(s.price, s.symbol) + '</span>' +
          '</span>' +
          '<span class="scalebar"><i style="left:' + s.score + '%"></i></span>' +
          '<span class="pair-tension' + (hot ? " hot" : "") + '">' + esc(s.tension) + '</span>' +
        '</button>';
      ul.appendChild(li);
    });
    Array.prototype.forEach.call(ul.querySelectorAll(".pair"), function (b) {
      b.addEventListener("click", function () { select(b.dataset.sym); });
    });
  }

  // -------------------------------------------------------------- Tacho

  /** Halbrunder Tacho.

      Der Bogen ist in fuenf Felder geteilt, von rot nach gruen. Der Zeiger
      sitzt bewusst nur im aeusseren Bereich: liefe er bis zur Mitte, wuerde
      er bei einem Wert um 50 senkrecht durch die Zahl schneiden. */
  function renderTacho(score) {
    var W = 300, H = 176, cx = 150, cy = 150, R = 124;

    function pt(value, radius) {
      var a = Math.PI * (1 - (value - 1) / 99);
      return [cx + Math.cos(a) * radius, cy - Math.sin(a) * radius];
    }
    function arc(from, to, radius, width, color) {
      var p1 = pt(from, radius), p2 = pt(to, radius);
      return '<path d="M ' + p1[0].toFixed(1) + ' ' + p1[1].toFixed(1) +
             ' A ' + radius + ' ' + radius + ' 0 0 1 ' + p2[0].toFixed(1) + ' ' + p2[1].toFixed(1) +
             '" fill="none" stroke="' + color + '" stroke-width="' + width + '"/>';
    }

    var bands = [
      [1, 19, "var(--sell)"],
      [19, 40, "var(--sell-weak)"],
      [40, 61, "var(--wait)"],
      [61, 82, "var(--buy-weak)"],
      [82, 100, "var(--buy)"]
    ];
    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Anzeige ' +
              score + ' von 100, ' + esc(actionFor(score)) + '">';
    bands.forEach(function (b) { svg += arc(b[0], b[1], R, 20, b[2]); });

    svg += '<text x="14" y="170" fill="var(--sell)" font-size="13" font-weight="700">1</text>';
    svg += '<text x="264" y="170" fill="var(--buy)" font-size="13" font-weight="700">100</text>';

    // Zeiger: kurzer Strich am Bogen statt langer Nadel durch die Mitte
    var outer = pt(score, R + 12), inner = pt(score, R - 34);
    svg += '<line x1="' + inner[0].toFixed(1) + '" y1="' + inner[1].toFixed(1) +
           '" x2="' + outer[0].toFixed(1) + '" y2="' + outer[1].toFixed(1) +
           '" stroke="var(--panel)" stroke-width="9" stroke-linecap="round"/>';
    svg += '<line x1="' + inner[0].toFixed(1) + '" y1="' + inner[1].toFixed(1) +
           '" x2="' + outer[0].toFixed(1) + '" y2="' + outer[1].toFixed(1) +
           '" stroke="' + toneColor(score) + '" stroke-width="4" stroke-linecap="round"/>';
    svg += '</svg>';
    return svg;
  }

  /** Beschriftung zum Tachowert – gleiche Grenzen wie im Rechenkern. */
  function actionFor(score) {
    if (score <= 19) { return "Verkaufen"; }
    if (score <= 40) { return "Eher verkaufen"; }
    if (score <= 60) { return "Abwarten"; }
    if (score <= 81) { return "Eher kaufen"; }
    return "Kaufen";
  }

  // ------------------------------------------------------------- Detail

  function renderDetail() {
    var s = current();
    if (!s) { return; }

    $("tacho").innerHTML = renderTacho(s.score) +
      '<div class="tacho-read">' +
        '<div class="tacho-num" style="color:' + toneColor(s.score) + '">' + s.score + '</div>' +
        '<div class="tacho-act" style="color:' + toneColor(s.score) + '">' + esc(s.action) + '</div>' +
        '<div class="tacho-of">von 100</div>' +
      '</div>';

    $("v-sym").textContent = s.symbol;
    $("v-say").textContent = s.headline;

    var hot = (s.tension === "Hohe Spannung" || s.tension === "Bewegung laeuft");
    var meta =
      '<span class="badge ' + (hot ? "tension" : "calm") + '">' + esc(s.tension) + '</span>' +
      '<span class="badge plain">' + esc(s.regime) + '</span>' +
      '<span class="badge plain">Kurs ' + px(s.price, s.symbol) + '</span>';
    if (s.event_risk) {
      meta += '<span class="badge sell">' + esc(s.event_risk.title) +
              ' in ' + s.event_risk.minutes + ' Min.</span>';
    }
    $("v-meta").innerHTML = meta;

    renderOrders(s);
    renderNotes(s);
    renderReasons(s);
    renderEvents(s);
    renderTimeframes();
    loadChart();
  }

  function renderOrders(s) {
    var lv = s.levels;
    if (!lv) { $("v-orders").innerHTML = ""; $("v-size").innerHTML = ""; return; }

    // Nur drei Kurse: wo einsteigen, wo aussteigen wenn es schiefgeht,
    // wo Gewinn mitnehmen.
    var entry, entryLabel, entryCls;
    if (s.bias === "short") {
      entry = lv.trigger_short; entryLabel = "Verkaufen unter"; entryCls = "sell";
    } else if (s.bias === "long") {
      entry = lv.trigger_long; entryLabel = "Kaufen &uuml;ber"; entryCls = "buy";
    } else {
      entry = null;
    }

    var html = "";
    if (entry === null) {
      // Richtung offen: nur die beiden Marken zeigen. Ein Notausstieg waere
      // hier dieselbe Zahl wie eine der Marken und wuerde nur verwirren –
      // er ergibt sich erst, wenn eine Seite durchbrochen ist.
      html =
        card("buy", "Kaufen &uuml;ber", px(lv.trigger_long, s.symbol), "wenn der Kurs dar&uuml;ber steigt") +
        card("sell", "Verkaufen unter", px(lv.trigger_short, s.symbol), "wenn der Kurs darunter f&auml;llt") +
        card("", "Notausstieg", "\u2013", "steht fest, sobald eine Seite bricht");
    } else {
      html =
        card(entryCls, entryLabel, px(entry, s.symbol), "erst dann einsteigen") +
        card("sell", "Notausstieg", px(lv.stop, s.symbol), "hier war die Idee falsch") +
        card("buy", "Gewinn mitnehmen", px(lv.take_profit_1, s.symbol), "erstes Ziel");
    }
    $("v-orders").innerHTML = html;

    var pos = s.position;
    $("v-size").innerHTML = pos
      ? '<div class="sizehint">' +
          '<span class="big">' + de(pos.lots, 2) + ' Lot</span>' +
          '<span class="t">so gro&szlig; darf die Position sein, damit bei ' +
          de(pos.risk_amount, 0) + '&nbsp;' + esc(pos.account_currency) +
          ' Verlust Schluss ist</span>' +
        '</div>'
      : "";
  }

  function card(cls, k, v, n) {
    return '<div class="order ' + cls + '">' +
             '<div class="k">' + k + '</div>' +
             '<div class="v">' + v + '</div>' +
             '<div class="n">' + n + '</div>' +
           '</div>';
  }

  function renderNotes(s) {
    var ul = $("v-notes");
    ul.innerHTML = (s.notes || []).map(function (n) {
      return "<li>" + esc(n) + "</li>";
    }).join("");
  }

  /** Die Gruende nach Richtung sortieren.
      Ohne diese Trennung stehen widerspruechliche Hinweise unkommentiert
      nebeneinander und wirken wie ein Fehler. Getrennt zeigen sie, dass
      der Markt selbst uneins ist. */
  function renderReasons(s) {
    var forUp = [], forDown = [], neutral = [];
    (s.hits || []).slice()
      .sort(function (a, b) { return b.readiness * b.weight - a.readiness * a.weight; })
      .forEach(function (h) {
        if (h.direction > 0.05) { forUp.push(h); }
        else if (h.direction < -0.05) { forDown.push(h); }
        else { neutral.push(h); }
      });

    var html = "";
    html += column("buy", "Spricht f&uuml;r steigende Kurse", forUp, "Nichts spricht gerade daf&uuml;r.");
    html += column("sell", "Spricht f&uuml;r fallende Kurse", forDown, "Nichts spricht gerade daf&uuml;r.");
    if (neutral.length) {
      html += '<div class="reason-col" style="grid-column:1/-1;border-left:0;border-top:1px solid var(--line)">' +
              head("wait", "Sagt nur: gleich wird es bewegt", neutral.length) +
              list(neutral, "wait") + '</div>';
    }
    $("reasons").innerHTML = html;
  }

  function column(cls, title, items, emptyText) {
    return '<div class="reason-col">' + head(cls, title, items.length) +
           (items.length ? list(items, cls) : '<p class="reason-empty">' + emptyText + '</p>') +
           '</div>';
  }

  function head(cls, title, count) {
    return '<div class="reason-head ' + cls + '">' + title +
           '<span class="cnt">' + count + '</span></div>';
  }

  function list(items, cls) {
    return '<ul class="reason-list">' + items.map(function (h) {
      // Staerke als Punkte statt als Prozentzahl
      var dots = h.readiness >= 0.7 ? "●●●"
               : h.readiness >= 0.4 ? "●●○" : "●○○";
      return '<li>' +
        '<div class="t"><span class="strength ' + cls + '">' + dots + '</span>' + esc(h.label) + '</div>' +
        '<div class="d">' + esc(h.detail) + '</div>' +
      '</li>';
    }).join("") + '</ul>';
  }

  function renderEvents(s) {
    var ul = $("events");
    var events = (s.events || []);
    if (!events.length) {
      ul.innerHTML = '<li class="empty">Keine wichtigen Termine in den n&auml;chsten Tagen.</li>';
      return;
    }
    ul.innerHTML = events.map(function (e) {
      return '<li>' +
        '<span class="ev-time">' + esc(evTime(e.iso)) + '</span>' +
        '<span class="ev-cur">' + esc(e.currency) + '</span>' +
        '<span class="ev-title">' + esc(e.title) + '</span>' +
      '</li>';
    }).join("");
  }

  function renderTimeframes() {
    var box = $("tfs");
    box.innerHTML = "";
    (state.status.timeframes || []).forEach(function (tf) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = tf;
      b.setAttribute("aria-pressed", String(tf === state.timeframe));
      b.addEventListener("click", function () {
        state.timeframe = tf;
        renderTimeframes();
        loadChart();
      });
      box.appendChild(b);
    });
  }

  // -------------------------------------------------------------- Chart

  function loadChart() {
    if (!state.symbol) { return; }
    var tf = state.timeframe || state.status.execution_timeframe;
    fetch("/api/candles/" + state.symbol + "?tf=" + tf + "&limit=160")
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("keine Daten")); })
      .then(function (d) { state.chart = d; drawChart(); })
      .catch(function () { state.chart = null; });
  }

  function drawChart() {
    if (!state.chart) { return; }
    window.FWChart.drawCandles($("chart"), state.chart);
    window.FWChart.drawRsi($("chart-rsi"), state.chart);
  }

  // ----------------------------------------------------------- Meldungen

  function loadAlerts() {
    fetch("/api/alerts?limit=20").then(function (r) { return r.json(); }).then(function (d) {
      var ul = $("alerts");
      var items = d.alerts || [];
      if (!items.length) {
        ul.innerHTML = '<li class="empty">Noch nichts. Sobald ein Paar unter Spannung ' +
                       'ger&auml;t, steht es hier.</li>';
        return;
      }
      ul.innerHTML = items.map(function (a) {
        return '<li><div class="when">' + clock(a.ts) + '</div><pre>' + esc(a.message) + '</pre></li>';
      }).join("");
    }).catch(function () { /* Meldungen sind zweitrangig */ });
  }

  // ----------------------------------------------------------- Steuerung

  function select(sym) {
    state.symbol = sym;
    renderPairs();
    renderDetail();
  }

  function applyScan(setups) {
    state.setups = setups;
    if (!state.symbol && setups.length) { state.symbol = setups[0].symbol; }
    renderStatus();
    renderPairs();
    renderDetail();
  }

  function connect() {
    var proto = location.protocol === "https:" ? "wss" : "ws";
    var socket = new WebSocket(proto + "://" + location.host + "/ws");
    socket.onopen = function () { $("conn-dot").classList.add("on"); };
    socket.onclose = function () {
      $("conn-dot").classList.remove("on");
      setTimeout(connect, 3000);
    };
    socket.onmessage = function (event) {
      var msg = JSON.parse(event.data);
      if (msg.event === "snapshot") {
        state.status = msg.payload.status;
        state.timeframe = state.timeframe || state.status.execution_timeframe;
        applyScan(msg.payload.setups);
      } else if (msg.event === "scan") {
        applyScan(msg.payload.setups);
        fetch("/api/status").then(function (r) { return r.json(); })
          .then(function (s) { state.status = s; renderStatus(); });
      } else if (msg.event === "alert") {
        loadAlerts();
      }
    };
  }

  function init() {
    $("btn-help").onclick = function () { $("help").hidden = false; };
    $("help-close").onclick = function () { $("help").hidden = true; };
    $("help").onclick = function (e) { if (e.target === $("help")) { $("help").hidden = true; } };
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { $("help").hidden = true; }
    });

    $("btn-scan").onclick = function () {
      var btn = $("btn-scan");
      btn.disabled = true;
      btn.textContent = "prüft …";
      fetch("/api/scan", { method: "POST" })
        .then(function (r) { return r.json(); })
        .then(function (d) { applyScan(d.setups); })
        .finally(function () { btn.disabled = false; btn.textContent = "Jetzt prüfen"; });
    };

    var timer = null;
    window.addEventListener("resize", function () {
      clearTimeout(timer);
      timer = setTimeout(drawChart, 120);
    });

    connect();
    loadAlerts();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
