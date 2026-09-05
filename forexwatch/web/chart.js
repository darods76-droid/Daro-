/* Schlanker Kerzenchart auf Canvas – bewusst ohne Fremdbibliothek,
   damit die App vollstaendig offline und ohne CDN laeuft. */
(function (global) {
  "use strict";

  const COLORS = {
    up: "#26c281",
    down: "#ef5b5b",
    grid: "#1e2937",
    axis: "#64748b",
    ema20: "#4da3ff",
    ema50: "#f0a92e",
    band: "rgba(77,163,255,.28)",
    kc: "rgba(132,148,168,.22)",
    squeeze: "rgba(240,169,46,.13)",
    entry: "#4da3ff",
    stop: "#ef5b5b",
    target: "#26c281",
    text: "#8494a8",
  };

  function niceStep(range, targetLines) {
    const raw = range / targetLines;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    const step = norm >= 5 ? 5 : norm >= 2 ? 2 : 1;
    return step * mag;
  }

  function setupCanvas(canvas) {
    const ratio = global.devicePixelRatio || 1;
    const width = canvas.clientWidth || 800;
    const height = canvas.height;
    canvas.width = width * ratio;
    canvas.style.height = height + "px";
    canvas.height = height * ratio;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    return { ctx, width, height };
  }

  function line(ctx, points, color, width) {
    ctx.strokeStyle = color;
    ctx.lineWidth = width || 1.2;
    ctx.beginPath();
    let started = false;
    for (const p of points) {
      if (p === null) { started = false; continue; }
      if (!started) { ctx.moveTo(p[0], p[1]); started = true; }
      else ctx.lineTo(p[0], p[1]);
    }
    ctx.stroke();
  }

  /** Hauptchart: Kerzen, Baender, Durchschnitte, Handelsniveaus. */
  function drawCandles(canvas, data) {
    const { ctx, width, height } = setupCanvas(canvas);
    const candles = data.candles || [];
    if (!candles.length) return;

    const padL = 8, padR = 62, padT = 10, padB = 20;
    const plotW = width - padL - padR;
    const plotH = height - padT - padB;
    const ind = data.indicators || {};

    // Wertebereich aus Kursen, Baendern und Niveaus
    let lo = Infinity, hi = -Infinity;
    for (const c of candles) { if (c.low < lo) lo = c.low; if (c.high > hi) hi = c.high; }
    for (const key of ["bb_upper", "bb_lower", "kc_upper", "kc_lower"]) {
      for (const v of ind[key] || []) { if (v == null) continue; if (v < lo) lo = v; if (v > hi) hi = v; }
    }
    if (data.levels) {
      for (const k of ["trigger_long", "trigger_short", "stop", "take_profit_1"]) {
        const v = data.levels[k];
        if (typeof v === "number") { if (v < lo) lo = v; if (v > hi) hi = v; }
      }
    }
    const span = (hi - lo) || 1;
    lo -= span * 0.06; hi += span * 0.06;

    const y = (v) => padT + (hi - v) / (hi - lo) * plotH;
    const step = plotW / candles.length;
    const x = (i) => padL + i * step + step / 2;

    // Squeeze-Phasen hinterlegen: hier ist der Markt aufgeladen
    const sq = ind.squeeze || [];
    ctx.fillStyle = COLORS.squeeze;
    let runStart = -1;
    for (let i = 0; i <= sq.length; i++) {
      if (sq[i]) { if (runStart < 0) runStart = i; }
      else if (runStart >= 0) {
        ctx.fillRect(padL + runStart * step, padT, (i - runStart) * step, plotH);
        runStart = -1;
      }
    }

    // Raster und Preisachse
    const gridStep = niceStep(hi - lo, 5);
    // An der Groessenordnung des Kurses ausrichten: JPY-Paare notieren mit
    // drei, die uebrigen Paare mit fuenf Nachkommastellen.
    const digits = hi >= 1000 ? 2 : hi >= 20 ? 3 : 5;
    ctx.font = "10px ui-monospace, monospace";
    ctx.textBaseline = "middle";
    for (let v = Math.ceil(lo / gridStep) * gridStep; v <= hi; v += gridStep) {
      const py = y(v);
      ctx.strokeStyle = COLORS.grid;
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padL, py); ctx.lineTo(padL + plotW, py); ctx.stroke();
      ctx.fillStyle = COLORS.axis;
      ctx.fillText(v.toFixed(digits), padL + plotW + 6, py);
    }

    // Bollinger- und Keltner-Grenzen
    const band = (key, color, w) => {
      const pts = (ind[key] || []).map((v, i) => (v == null ? null : [x(i), y(v)]));
      if (pts.length) line(ctx, pts, color, w || 1);
    };
    band("kc_upper", COLORS.kc);
    band("kc_lower", COLORS.kc);
    band("bb_upper", COLORS.band);
    band("bb_lower", COLORS.band);

    // Kerzen
    const bodyW = Math.max(1, Math.min(9, step * 0.66));
    for (let i = 0; i < candles.length; i++) {
      const c = candles[i];
      const color = c.close >= c.open ? COLORS.up : COLORS.down;
      const cx = x(i);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(cx, y(c.high)); ctx.lineTo(cx, y(c.low)); ctx.stroke();
      const yo = y(c.open), yc = y(c.close);
      ctx.fillStyle = color;
      ctx.fillRect(cx - bodyW / 2, Math.min(yo, yc), bodyW, Math.max(1, Math.abs(yc - yo)));
    }

    band("ema20", COLORS.ema20, 1.4);
    band("ema50", COLORS.ema50, 1.4);

    // Handelsniveaus als gestrichelte Linien
    if (data.levels) {
      const marks = [
        ["trigger_long", COLORS.target, "Ausbruch oben"],
        ["trigger_short", COLORS.stop, "Ausbruch unten"],
        ["stop", COLORS.stop, "Stop"],
        ["take_profit_1", COLORS.target, "Ziel"],
      ];
      // Mehrere Niveaus fallen oft auf denselben Kurs (etwa Stop und
      // Ausbruchsmarke bei einem Short). Sie werden zu einer Linie mit
      // gemeinsamer Beschriftung zusammengefasst, sonst ueberlappt der Text.
      const groups = new Map();
      for (const [key, color, label] of marks) {
        const v = data.levels[key];
        if (typeof v !== "number" || v < lo || v > hi) continue;
        const py = Math.round(y(v));
        const hit = groups.get(py);
        if (hit) hit.labels.push(label);
        else groups.set(py, { color, labels: [label] });
      }

      ctx.setLineDash([4, 4]);
      ctx.font = "9px system-ui, sans-serif";
      for (const [py, g] of groups) {
        ctx.strokeStyle = g.color; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(padL, py); ctx.lineTo(padL + plotW, py); ctx.stroke();
        ctx.fillStyle = g.color;
        ctx.fillText(g.labels.join(" / "), padL + 4, py - 7);
      }
      ctx.setLineDash([]);
    }

    // Zeitachse
    ctx.fillStyle = COLORS.axis;
    ctx.font = "10px ui-monospace, monospace";
    const labelEvery = Math.max(1, Math.floor(candles.length / 6));
    for (let i = 0; i < candles.length; i += labelEvery) {
      const d = new Date(candles[i].ts * 1000);
      const text = d.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
      ctx.fillText(text, x(i) - 22, height - 8);
    }
  }

  /** Unteres Feld: RSI mit den Schwellen 30 und 70. */
  function drawRsi(canvas, data) {
    const { ctx, width, height } = setupCanvas(canvas);
    const values = (data.indicators || {}).rsi || [];
    if (!values.length) return;

    const padL = 8, padR = 62, padT = 8, padB = 10;
    const plotW = width - padL - padR;
    const plotH = height - padT - padB;
    const y = (v) => padT + (100 - v) / 100 * plotH;
    const step = plotW / values.length;

    for (const level of [30, 50, 70]) {
      const py = y(level);
      ctx.strokeStyle = level === 50 ? COLORS.grid : "#243040";
      ctx.setLineDash(level === 50 ? [] : [3, 3]);
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padL, py); ctx.lineTo(padL + plotW, py); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = COLORS.axis; ctx.font = "9px ui-monospace, monospace";
      ctx.textBaseline = "middle";
      ctx.fillText(String(level), padL + plotW + 6, py);
    }

    line(ctx, values.map((v, i) => (v == null ? null : [padL + i * step + step / 2, y(v)])), "#b06bff", 1.4);

    const last = [...values].reverse().find((v) => v != null);
    if (last != null) {
      ctx.fillStyle = COLORS.text; ctx.font = "10px ui-monospace, monospace";
      ctx.fillText("RSI " + last.toFixed(0), padL + 4, padT + 8);
    }
  }

  global.FWChart = { drawCandles, drawRsi };
})(window);
