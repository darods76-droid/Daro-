/* ForexWatch – Oberflaeche */
(function () {
  "use strict";

  const $  = (id) => document.getElementById(id);
  const el = (tag, cls, html) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (html != null) node.innerHTML = html;
    return node;
  };
  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

  const state = {
    setups: [],
    status: {},
    selected: null,
    timeframe: null,
    chart: null,
  };

  // ---------------------------------------------------------------- Format

  const fmtPrice = (v) => (v == null ? "–" : Number(v).toFixed(Math.abs(v) >= 20 ? 3 : 5));
  const fmtTime  = (ts) => new Date(ts * 1000).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  const fmtDate  = (iso) => new Date(iso).toLocaleString("de-DE",
    { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

  const stateColor = (s) => ({
    TRIGGERED: "var(--triggered)", ARMED: "var(--armed)",
    WATCH: "var(--muted)", COOLDOWN: "var(--muted)", GESCHLOSSEN: "#5e6b7d",
  }[s] || "var(--muted)");

  const biasColor = (b) => b === "long" ? "var(--long)" : b === "short" ? "var(--short)" : "var(--muted)";
  const biasWord  = (b) => ({ long: "aufwaerts", short: "abwaerts", neutral: "offen" }[b] || b);

  // ------------------------------------------------------------ Kopfzeile

  function renderStatus() {
    const s = state.status;
    if (!s.pairs) return;
    const scanned = s.last_scan ? fmtTime(s.last_scan) : "–";
    const next = s.next_moment || {};
    $("statusbar").innerHTML = `
      <span>Markt <b style="color:${s.market_open ? "var(--long)" : "var(--short)"}">
        ${s.market_open ? "offen" : "geschlossen"}</b></span>
      <span>${esc(s.session || "")}</span>
      <span>Naechster Impuls <b>${esc(next.name || "–")}</b> in ${next.minutes ?? "–"} Min.</span>
      <span>Quelle <b>${esc(s.provider)}</b></span>
      <span>Letzter Scan <b>${scanned}</b> (#${s.scan_count || 0})</span>
      <span>Termine <b>${s.calendar_events || 0}</b></span>`;
  }

  // ----------------------------------------------------------- Wachliste

  function renderPairs() {
    const filter = $("filter-state").value;
    const list = $("pairs");
    list.innerHTML = "";
    const items = filter ? state.setups.filter((s) => s.state === filter) : state.setups;

    if (!items.length) {
      list.appendChild(el("li", "muted", "Keine Instrumente in diesem Zustand."));
      return;
    }

    for (const s of items) {
      const li = el("li", s.symbol === state.selected ? "active" : "");
      li.innerHTML = `
        <div class="row1">
          <span class="sym">${esc(s.symbol)}</span>
          <span class="price">${fmtPrice(s.price)}</span>
        </div>
        <div class="row2">
          <span class="badge ${s.state.toLowerCase()}">${esc(s.state)}</span>
          <span class="badge ${s.bias}">${esc(biasWord(s.bias))}</span>
          <span class="bar"><span style="width:${s.readiness}%;background:${stateColor(s.state)}"></span></span>
          <span class="bar-val">${Math.round(s.readiness)}</span>
        </div>`;
      li.onclick = () => select(s.symbol);
      list.appendChild(li);
    }
  }

  // -------------------------------------------------------------- Detail

  function currentSetup() {
    return state.setups.find((s) => s.symbol === state.selected) || null;
  }

  function renderDetail() {
    const s = currentSetup();
    if (!s) return;

    $("d-symbol").textContent = s.symbol;
    $("d-sub").innerHTML =
      `${fmtPrice(s.price)} · ${esc(s.regime)} · ${esc(s.session)}` +
      (s.event_risk ? ` · <span class="warn">${esc(s.event_risk.title)} in ${s.event_risk.minutes} Min.</span>` : "");

    // Kennzahlen
    $("gauges").innerHTML = [
      gauge("Zustand", s.state, null, stateColor(s.state)),
      gauge("Bereitschaft", Math.round(s.readiness), s.readiness, stateColor(s.state)),
      gauge("Richtung", (s.direction > 0 ? "+" : "") + Math.round(s.direction),
            Math.abs(s.direction), biasColor(s.bias)),
      gauge("Vertrauen", Math.round(s.confidence), s.confidence, "var(--accent)"),
    ].join("");

    // Bausteine
    const hits = $("hits");
    hits.innerHTML = "";
    if (!s.hits.length) {
      hits.appendChild(el("li", "muted", "Derzeit keine auffaelligen Signale."));
    }
    for (const h of [...s.hits].sort((a, b) => b.readiness * b.weight - a.readiness * a.weight)) {
      const li = el("li");
      li.innerHTML = `
        <div class="hit-head">
          <span class="hit-label">${esc(h.label)}</span>
          <span class="cat ${esc(h.category)}">${esc(h.category)}</span>
        </div>
        <div class="hit-detail">${esc(h.detail)}</div>
        <div class="hit-meta">Aufladung ${(h.readiness * 100).toFixed(0)}%
          · Richtung ${h.direction >= 0 ? "+" : ""}${(h.direction * 100).toFixed(0)}
          · Gewicht ${h.weight}</div>`;
      hits.appendChild(li);
    }

    renderPlan(s);
    renderTimeframes();
    loadChart();
    calcPosition();
  }

  function gauge(key, value, pct, color) {
    const bar = pct == null ? "" :
      `<span class="bar"><span style="width:${Math.min(100, pct)}%;background:${color}"></span></span>`;
    return `<div class="gauge"><div class="k">${esc(key)}</div>
            <div class="v" style="color:${color}">${esc(value)}</div>${bar}</div>`;
  }

  function renderPlan(s) {
    const lv = s.levels;
    if (!lv) { $("plan").innerHTML = '<p class="muted">Keine Niveaus berechnet.</p>'; return; }
    const notes = (s.notes || []).map((n) => `<li>${esc(n)}</li>`).join("");
    $("plan").innerHTML = `
      <div class="levels">
        <div class="lv long"><div class="k">Ausbruch oben</div><div class="v">${fmtPrice(lv.trigger_long)}</div></div>
        <div class="lv short"><div class="k">Ausbruch unten</div><div class="v">${fmtPrice(lv.trigger_short)}</div></div>
        <div class="lv"><div class="k">Einstieg (${esc(biasWord(s.bias))})</div><div class="v">${fmtPrice(lv.entry)}</div></div>
        <div class="lv stop"><div class="k">Stop</div><div class="v">${fmtPrice(lv.stop)}</div></div>
        <div class="lv long"><div class="k">Ziel 1</div><div class="v">${fmtPrice(lv.take_profit_1)}</div></div>
        <div class="lv"><div class="k">CRV</div><div class="v">${lv.rr}</div></div>
      </div>
      ${notes ? `<ul class="notes">${notes}</ul>` : ""}
      <p class="muted" style="margin-top:12px">
        Rahmen fuer die eigene Planung, kein Signal: die Richtungsprognose des Systems
        trifft historisch nur knapp besser als der Zufall.
      </p>`;
  }

  function renderTimeframes() {
    const box = $("tf-switch");
    box.innerHTML = "";
    for (const tf of state.status.timeframes || []) {
      const b = el("button", tf === state.timeframe ? "on" : "", tf);
      b.onclick = () => { state.timeframe = tf; renderTimeframes(); loadChart(); };
      box.appendChild(b);
    }
  }

  // --------------------------------------------------------------- Chart

  async function loadChart() {
    if (!state.selected) return;
    const tf = state.timeframe || state.status.execution_timeframe;
    try {
      const res = await fetch(`/api/candles/${state.selected}?tf=${tf}&limit=180`);
      if (!res.ok) throw new Error(await res.text());
      state.chart = await res.json();
    } catch (err) {
      $("chart-legend").textContent = "Chartdaten nicht verfuegbar.";
      return;
    }
    drawChart();
    $("chart-legend").innerHTML = `
      <span><i style="background:#4da3ff"></i>EMA 20</span>
      <span><i style="background:#f0a92e"></i>EMA 50</span>
      <span><i style="background:rgba(77,163,255,.5)"></i>Bollinger</span>
      <span><i style="background:rgba(132,148,168,.4)"></i>Keltner</span>
      <span><i style="background:rgba(240,169,46,.35);height:8px"></i>Kompression (Squeeze)</span>`;
  }

  function drawChart() {
    if (!state.chart) return;
    window.FWChart.drawCandles($("chart"), state.chart);
    window.FWChart.drawRsi($("chart-rsi"), state.chart);
  }

  // ------------------------------------------------------- Positionsgroesse

  let calcTimer = null;
  function calcPosition() {
    clearTimeout(calcTimer);
    calcTimer = setTimeout(async () => {
      const s = currentSetup();
      if (!s || !s.levels) return;
      const params = new URLSearchParams({
        symbol: s.symbol,
        entry: s.levels.entry,
        stop: s.levels.stop,
        balance: $("c-balance").value || 10000,
        risk_percent: $("c-risk").value || 1,
        currency: ($("c-currency").value || "EUR").toUpperCase(),
      });
      try {
        const res = await fetch("/api/position?" + params);
        const p = await res.json();
        if (!res.ok) throw new Error(p.error || "Fehler");
        $("calc-out").innerHTML = `
          <div><span class="big">${p.lots.toFixed(2)} Lot</span>
            <span class="muted">(${p.units.toLocaleString("de-DE")} Einheiten)</span></div>
          <div class="muted" style="margin-top:6px">
            Risiko ${p.risk_amount.toLocaleString("de-DE")} ${esc(p.account_currency)}
            ueber ${p.risk_pips.toFixed(1)} Pips · Pip-Wert ${p.pip_value.toFixed(2)} je Lot
          </div>
          ${p.note ? `<div class="muted warn" style="margin-top:6px">${esc(p.note)}</div>` : ""}`;
      } catch (err) {
        $("calc-out").innerHTML = `<span class="muted">${esc(err.message)}</span>`;
      }
    }, 250);
  }

  // ------------------------------------------------------ Termine & Alarme

  async function loadCalendar() {
    try {
      const res = await fetch("/api/calendar?hours=72&impact=hoch");
      const data = await res.json();
      $("cal-source").textContent = data.source || "";
      const list = $("calendar");
      list.innerHTML = "";
      if (!data.events.length) {
        list.appendChild(el("li", "muted", "Keine hochrelevanten Termine in den naechsten 72 Stunden."));
        return;
      }
      for (const e of data.events.slice(0, 25)) {
        const li = el("li");
        li.innerHTML = `<div class="ev-head">
            <span class="ev-time">${esc(fmtDate(e.iso))}</span>
            <span class="ev-cur">${esc(e.currency)}</span>
            <span class="imp ${esc(e.impact)}">${esc(e.impact)}</span>
          </div>
          <div class="muted" style="margin-top:3px">${esc(e.title)}
            ${e.forecast ? `· Prognose ${esc(e.forecast)}` : ""}
            ${e.previous ? `· zuvor ${esc(e.previous)}` : ""}</div>`;
        list.appendChild(li);
      }
    } catch (err) { /* Kalender ist optional */ }
  }

  async function loadAlerts() {
    try {
      const res = await fetch("/api/alerts?limit=25");
      const data = await res.json();
      renderAlerts(data.alerts || []);
    } catch (err) { /* still */ }
  }

  function renderAlerts(alerts) {
    const list = $("alerts");
    list.innerHTML = "";
    $("alert-count").textContent = alerts.length ? `${alerts.length} zuletzt` : "";
    if (!alerts.length) {
      list.appendChild(el("li", "muted", "Noch keine Alarme. Es wird gemeldet, sobald ein Markt scharf wird."));
      return;
    }
    for (const a of alerts) {
      const li = el("li");
      li.innerHTML = `<div class="when">${fmtTime(a.ts)}</div><pre>${esc(a.message)}</pre>`;
      list.appendChild(li);
    }
  }

  // ------------------------------------------------------------ Backtest

  async function runBacktest() {
    if (!state.selected) return;
    const btn = $("btn-backtest");
    btn.disabled = true; btn.textContent = "prueft …";
    $("backtest").innerHTML = '<p class="muted">Die Signallogik wird ueber die Kurshistorie abgespielt. Das dauert einen Moment.</p>';
    try {
      const tf = state.timeframe || state.status.execution_timeframe;
      const res = await fetch(`/api/backtest/${state.selected}?tf=${tf}&bars=6000`);
      const d = await res.json();
      if (!res.ok) throw new Error(d.error || "Fehler");
      renderBacktest(d);
    } catch (err) {
      $("backtest").innerHTML = `<p class="muted">Pruefung fehlgeschlagen: ${esc(err.message)}</p>`;
    } finally {
      btn.disabled = false; btn.textContent = "Fuer dieses Paar pruefen";
    }
  }

  function renderBacktest(d) {
    const e = d.expansion, dir = d.direction, t = d.trading;
    const cls = (v) => v > 0 ? "good" : v < 0 ? "bad" : "";
    $("backtest").innerHTML = `
      <div class="bt-grid">
        <div class="bt-card">
          <div class="k">Bewegung folgte</div>
          <div class="v ${cls(e.matched_rate_lift)}">${e.hit_rate}%</div>
          <div class="c">gegenueber ${e.matched_rate}% in vergleichbar ruhigen Phasen
            (${e.matched_rate_lift > 0 ? "+" : ""}${e.matched_rate_lift} Prozentpunkte)</div>
        </div>
        <div class="bt-card">
          <div class="k">Ausdehnung der Spanne</div>
          <div class="v">${e.after_armed}×</div>
          <div class="c">vergleichbar ruhige Phasen: ${e.matched}×</div>
        </div>
        <div class="bt-card">
          <div class="k">Richtung getroffen</div>
          <div class="v ${cls(dir.lift)}">${dir.hit_rate}%</div>
          <div class="c">Zufallsniveau ${dir.baseline}% (${dir.lift > 0 ? "+" : ""}${dir.lift} pp)</div>
        </div>
        <div class="bt-card">
          <div class="k">Erwartungswert je Handel</div>
          <div class="v ${cls(t.expectancy_r)}">${t.expectancy_r > 0 ? "+" : ""}${t.expectancy_r} R</div>
          <div class="c">${t.trades} Handel · Trefferquote ${t.win_rate}% · inkl. ${d.spread_pips} Pip Spread</div>
        </div>
      </div>
      <p class="muted">
        Grundlage: ${d.bars} Kerzen im ${esc(d.timeframe)}-Chart, ${d.armed_count} scharfe Setups,
        Beobachtungsfenster ${d.horizon} Kerzen. Der Vergleichswert nimmt nur Kerzen mit
        aehnlich niedriger Vorlauf-Volatilitaet – sonst waere der Vorsprung geschoent, weil ein
        scharfes Setup enge Spannen ohnehin voraussetzt.
        <br><br>
        <strong>Lies es so:</strong> Ein deutlicher Vorsprung bei „Bewegung folgte" heisst, dass der
        Zeitpunkt gut erkannt wird. Liegt „Richtung getroffen" nahe am Zufallsniveau, taugt die
        Anzeige als Zeitgeber, aber nicht als Kaufsignal.
      </p>`;
  }

  // --------------------------------------------------------------- Steuerung

  function select(symbol) {
    state.selected = symbol;
    renderPairs();
    renderDetail();
  }

  function applyScan(setups) {
    state.setups = setups;
    if (!state.selected && setups.length) state.selected = setups[0].symbol;
    renderPairs();
    renderDetail();
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${proto}://${location.host}/ws`);

    socket.onopen = () => $("conn-dot").classList.add("on");
    socket.onclose = () => {
      $("conn-dot").classList.remove("on");
      setTimeout(connect, 3000); // Verbindung fiel weg -> erneut versuchen
    };
    socket.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.event === "snapshot") {
        state.status = msg.payload.status;
        state.timeframe = state.timeframe || state.status.execution_timeframe;
        renderStatus();
        applyScan(msg.payload.setups);
      } else if (msg.event === "scan") {
        applyScan(msg.payload.setups);
        fetch("/api/status").then((r) => r.json()).then((s) => { state.status = s; renderStatus(); });
      } else if (msg.event === "alert") {
        loadAlerts();
      }
    };
  }

  function init() {
    $("filter-state").onchange = renderPairs;
    $("btn-help").onclick = () => ($("help").hidden = false);
    $("help-close").onclick = () => ($("help").hidden = true);
    $("help").onclick = (e) => { if (e.target === $("help")) $("help").hidden = true; };
    $("btn-backtest").onclick = runBacktest;

    $("btn-scan").onclick = async () => {
      const btn = $("btn-scan");
      btn.disabled = true; btn.textContent = "scannt …";
      try {
        const res = await fetch("/api/scan", { method: "POST" });
        const data = await res.json();
        applyScan(data.setups);
      } finally {
        btn.disabled = false; btn.textContent = "Jetzt scannen";
      }
    };

    for (const id of ["c-balance", "c-risk", "c-currency"]) $(id).oninput = calcPosition;
    window.addEventListener("resize", drawChart);

    connect();
    loadCalendar();
    loadAlerts();
    setInterval(loadCalendar, 15 * 60 * 1000);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
