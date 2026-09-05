// Canvas-Renderer: Modellkoordinaten (mm, Y nach oben) -> Bildschirm.
import * as G from "./geom.js";
import * as P from "./prims.js";
import { LINETYPES, polylineSegments, outlinePoints, parseScale } from "./doc.js";

const GRID_STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000];

export class Renderer {
  constructor(canvas, drawing) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.drawing = drawing;
    this.view = { zoom: 2, cx: 150, cy: 100 };
    this.showGrid = true;
    this.showSheet = true;
    this.showLineweights = true;
    this.gridStep = 10;
    this.selection = new Set();
    this.hover = null;
    this.snapMarker = null;
    this.preview = null;          // {entities:[], hints:[]}
    this.cache = new Map();
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
  }

  get scaleFactor() { return parseScale(this.drawing.meta.scale); }

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.max(1, Math.round(rect.width * this.dpr));
    this.canvas.height = Math.max(1, Math.round(rect.height * this.dpr));
    this.width = rect.width;
    this.height = rect.height;
  }

  toScreen(p) {
    return [(p[0] - this.view.cx) * this.view.zoom + this.width / 2,
            this.height / 2 - (p[1] - this.view.cy) * this.view.zoom];
  }

  toModel(s) {
    return [this.view.cx + (s[0] - this.width / 2) / this.view.zoom,
            this.view.cy - (s[1] - this.height / 2) / this.view.zoom];
  }

  /** Bildschirmpixel in Modell-Millimeter. */
  px(n = 1) { return n / this.view.zoom; }

  zoomAt(screenPoint, factor) {
    const before = this.toModel(screenPoint);
    this.view.zoom = Math.max(0.02, Math.min(400, this.view.zoom * factor));
    const after = this.toModel(screenPoint);
    this.view.cx += before[0] - after[0];
    this.view.cy += before[1] - after[1];
  }

  pan(dxPx, dyPx) {
    this.view.cx -= dxPx / this.view.zoom;
    this.view.cy += dyPx / this.view.zoom;
  }

  zoomTo(box, margin = 1.12) {
    if (!box) return;
    const w = Math.max(box[2] - box[0], 1e-6), h = Math.max(box[3] - box[1], 1e-6);
    this.view.cx = (box[0] + box[2]) / 2;
    this.view.cy = (box[1] + box[3]) / 2;
    this.view.zoom = Math.max(0.02, Math.min(400,
      Math.min(this.width / (w * margin), this.height / (h * margin))));
  }

  zoomExtents() {
    const box = this.drawing.bbox();
    if (box && box[2] - box[0] > 1e-6) return this.zoomTo(box);
    const [w, h] = this.drawing.sheetSizeModel();
    this.zoomTo([0, 0, w, h]);
  }

  zoomSheet() {
    const [w, h] = this.drawing.sheetSizeModel();
    this.zoomTo([0, 0, w, h]);
  }

  // -- Zeichnen ------------------------------------------------------------

  draw() {
    const ctx = this.ctx;
    ctx.save();
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, this.width, this.height);
    ctx.fillStyle = "#f4f5f7";
    ctx.fillRect(0, 0, this.width, this.height);

    if (this.showSheet) this.drawSheetBackground();
    if (this.showGrid) this.drawGrid();
    this.drawOrigin();
    if (this.showSheet) {
      for (const prim of this.sheetPrims()) this.prim(prim, 1);
    }

    for (const e of this.drawing.visible()) {
      const selected = this.selection.has(e.id);
      const hovered = this.hover === e.id;
      this.entity(e, selected ? "#e2680f" : (hovered ? "#1a7fd4" : null),
        selected || hovered ? 1.6 : 1);
    }

    if (this.preview) {
      for (const e of this.preview.entities || []) this.entity(e, "#e2680f", 1, true);
      for (const hint of this.preview.hints || []) this.hint(hint);
    }

    this.drawSelectionMarkers();
    if (this.snapMarker) this.drawSnap(this.snapMarker);
    ctx.restore();
  }

  sheetPrims() {
    const key = "sheet:" + JSON.stringify(this.drawing.meta);
    let prims = this.cache.get(key);
    if (!prims) {
      prims = P.sheetPrimitives(this.drawing.meta);
      this.cache.clear();
      this.cache.set(key, prims);
    }
    return prims;
  }

  drawSheetBackground() {
    const [w, h] = this.drawing.sheetSizeModel();
    const a = this.toScreen([0, h]), b = this.toScreen([w, 0]);
    const ctx = this.ctx;
    ctx.save();
    ctx.fillStyle = "#ffffff";
    ctx.shadowColor = "rgba(15,23,42,0.18)";
    ctx.shadowBlur = 14;
    ctx.shadowOffsetY = 3;
    ctx.fillRect(a[0], a[1], b[0] - a[0], b[1] - a[1]);
    ctx.restore();
  }

  drawGrid() {
    const ctx = this.ctx;
    const scale = this.scaleFactor;
    let step = GRID_STEPS.find((s) => s * this.view.zoom >= 8) || 1000;
    this.gridStep = step;
    const [x0, y0] = this.toModel([0, this.height]);
    const [x1, y1] = this.toModel([this.width, 0]);
    const startX = Math.floor(x0 / step) * step;
    const startY = Math.floor(y0 / step) * step;
    ctx.save();
    ctx.lineWidth = 1;
    for (let x = startX; x <= x1; x += step) {
      const major = Math.abs(x % (step * 10)) < 1e-6;
      ctx.strokeStyle = major ? "rgba(90,110,140,0.28)" : "rgba(90,110,140,0.13)";
      const a = this.toScreen([x, y0]), b = this.toScreen([x, y1]);
      ctx.beginPath();
      ctx.moveTo(Math.round(a[0]) + 0.5, a[1]);
      ctx.lineTo(Math.round(b[0]) + 0.5, b[1]);
      ctx.stroke();
    }
    for (let y = startY; y <= y1; y += step) {
      const major = Math.abs(y % (step * 10)) < 1e-6;
      ctx.strokeStyle = major ? "rgba(90,110,140,0.28)" : "rgba(90,110,140,0.13)";
      const a = this.toScreen([x0, y]), b = this.toScreen([x1, y]);
      ctx.beginPath();
      ctx.moveTo(a[0], Math.round(a[1]) + 0.5);
      ctx.lineTo(b[0], Math.round(b[1]) + 0.5);
      ctx.stroke();
    }
    ctx.restore();
  }

  drawOrigin() {
    const ctx = this.ctx;
    const o = this.toScreen([0, 0]);
    ctx.save();
    ctx.strokeStyle = "#c0392b";
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.moveTo(o[0] - 12, o[1]); ctx.lineTo(o[0] + 12, o[1]);
    ctx.moveTo(o[0], o[1] - 12); ctx.lineTo(o[0], o[1] + 12);
    ctx.stroke();
    ctx.restore();
  }

  // -- Entitaeten ----------------------------------------------------------

  style(layer, entity, override, boost) {
    const color = override || entity.color || layer.color || "#111";
    const lwPaper = entity.lineweight ?? layer.lineweight ?? 0.25;
    const lt = entity.linetype || layer.linetype || "continuous";
    let widthPx = this.showLineweights
      ? (lwPaper / this.scaleFactor) * this.view.zoom * boost
      : 1.2 * boost;
    widthPx = Math.max(1, Math.min(widthPx, 40));
    const pattern = (LINETYPES[lt] || []).map((v) => (v / this.scaleFactor) * this.view.zoom);
    return { color, widthPx, pattern };
  }

  applyStyle(st) {
    const ctx = this.ctx;
    ctx.strokeStyle = st.color;
    ctx.fillStyle = st.color;
    ctx.lineWidth = st.widthPx;
    ctx.setLineDash(st.pattern.length ? st.pattern : []);
  }

  entity(e, override = null, boost = 1, preview = false) {
    const layer = this.drawing.layer(e.layer) || { color: "#111", lineweight: 0.25 };
    const st = this.style(layer, e, override, boost);
    const ctx = this.ctx;
    ctx.save();
    if (preview) ctx.globalAlpha = 0.85;
    this.applyStyle(st);

    switch (e.type) {
      case "line": this.strokePath([e.a, e.b]); break;
      case "circle": this.strokeCircle(e.c, e.r); break;
      case "arc": this.strokeArc(e.c, e.r, e.start, e.end); break;
      case "polyline": {
        ctx.beginPath();
        let first = true;
        for (const seg of polylineSegments(e)) {
          if (seg.kind === "line") {
            const a = this.toScreen(seg.a), b = this.toScreen(seg.b);
            if (first) { ctx.moveTo(a[0], a[1]); first = false; } else ctx.lineTo(a[0], a[1]);
            ctx.lineTo(b[0], b[1]);
          } else {
            const pts = G.flattenArc(seg.c, seg.r, seg.start, seg.end);
            for (const p of pts) {
              const s = this.toScreen(p);
              if (first) { ctx.moveTo(s[0], s[1]); first = false; } else ctx.lineTo(s[0], s[1]);
            }
          }
        }
        if (e.closed) ctx.closePath();
        ctx.stroke();
        break;
      }
      case "text": this.text(e, st); break;
      case "point": {
        const s = this.toScreen(e.p);
        ctx.setLineDash([]);
        ctx.beginPath();
        ctx.moveTo(s[0] - 5, s[1]); ctx.lineTo(s[0] + 5, s[1]);
        ctx.moveTo(s[0], s[1] - 5); ctx.lineTo(s[0], s[1] + 5);
        ctx.stroke();
        break;
      }
      case "hatch": {
        ctx.setLineDash([]);
        for (const [a, b] of this.hatchOf(e)) this.strokePath([a, b]);
        break;
      }
      case "dim": {
        for (const prim of this.dimOf(e)) this.prim(prim, boost, override);
        break;
      }
    }
    ctx.restore();
  }

  hatchOf(e) {
    const key = "h:" + e.id + ":" + JSON.stringify([e.pts, e.angle, e.spacing, this.scaleFactor]);
    let lines = this.cache.get(key);
    if (!lines) {
      lines = P.hatchLines(outlinePoints(e), e.angle ?? 45,
        (e.spacing ?? 3) / this.scaleFactor);
      this.cache.set(key, lines);
    }
    return lines;
  }

  dimOf(e) {
    const layer = this.drawing.layer(e.layer);
    const key = "d:" + e.id + ":" + JSON.stringify([e, layer.color, layer.lineweight, this.scaleFactor]);
    let prims = this.cache.get(key);
    if (!prims) {
      prims = P.dimPrimitives(e, e.color || layer.color, e.lineweight ?? layer.lineweight,
        this.scaleFactor, this.drawing.meta.decimalComma !== false);
      this.cache.set(key, prims);
    }
    return prims;
  }

  prim(prim, boost = 1, override = null) {
    const ctx = this.ctx;
    ctx.save();
    const color = override || prim.color || "#111";
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = Math.max(1, Math.min(40,
      ((prim.lw || 0.25) / this.scaleFactor) * this.view.zoom * boost));
    const pattern = (LINETYPES[prim.lt] || []).map((v) => (v / this.scaleFactor) * this.view.zoom);
    ctx.setLineDash(pattern.length ? pattern : []);
    switch (prim.k) {
      case "line": this.strokePath([prim.a, prim.b]); break;
      case "poly": this.strokePath(prim.pts, prim.close); break;
      case "circle": this.strokeCircle(prim.c, prim.r); break;
      case "arc": this.strokeArc(prim.c, prim.r, prim.start, prim.end); break;
      case "fill": {
        ctx.beginPath();
        prim.pts.forEach((p, i) => {
          const s = this.toScreen(p);
          i ? ctx.lineTo(s[0], s[1]) : ctx.moveTo(s[0], s[1]);
        });
        ctx.closePath();
        ctx.fill();
        break;
      }
      case "text": this.text({ p: prim.p, h: prim.h, text: prim.text, rot: prim.rot,
        align: { start: "left", middle: "center", end: "right" }[prim.anchor] || "left" },
        { color }); break;
    }
    ctx.restore();
  }

  strokePath(points, close = false) {
    const ctx = this.ctx;
    ctx.beginPath();
    points.forEach((p, i) => {
      const s = this.toScreen(p);
      i ? ctx.lineTo(s[0], s[1]) : ctx.moveTo(s[0], s[1]);
    });
    if (close) ctx.closePath();
    ctx.stroke();
  }

  strokeCircle(c, r) {
    const s = this.toScreen(c);
    const rp = r * this.view.zoom;
    if (rp < 0.4) return;
    this.ctx.beginPath();
    this.ctx.arc(s[0], s[1], rp, 0, Math.PI * 2);
    this.ctx.stroke();
  }

  strokeArc(c, r, start, end) {
    const s = this.toScreen(c);
    const rp = r * this.view.zoom;
    if (rp < 0.4) return;
    // Y-Spiegelung: aus CCW im Modell wird CW auf dem Bildschirm
    this.ctx.beginPath();
    this.ctx.arc(s[0], s[1], rp, -start * Math.PI / 180, -end * Math.PI / 180, true);
    this.ctx.stroke();
  }

  text(e, st) {
    const ctx = this.ctx;
    const size = (e.h || 3.5) * this.view.zoom;
    if (size < 3) return;
    const s = this.toScreen(e.p);
    ctx.save();
    ctx.setLineDash([]);
    ctx.fillStyle = st.color;
    ctx.font = `${size}px "Arial Narrow", "Liberation Sans Narrow", Arial, sans-serif`;
    ctx.textAlign = { left: "left", center: "center", right: "right" }[e.align || "left"];
    ctx.textBaseline = "alphabetic";
    ctx.translate(s[0], s[1]);
    if (e.rot) ctx.rotate(-e.rot * Math.PI / 180);
    ctx.fillText(e.text || "", 0, 0);
    ctx.restore();
  }

  // -- Hinweise, Auswahl, Fangpunkte --------------------------------------

  hint(h) {
    const ctx = this.ctx;
    ctx.save();
    ctx.strokeStyle = "#8a94a6";
    ctx.fillStyle = "#334155";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    if (h.k === "line") this.strokePath([h.a, h.b]);
    if (h.k === "rect") {
      const a = this.toScreen([h.box[0], h.box[3]]);
      const b = this.toScreen([h.box[2], h.box[1]]);
      ctx.setLineDash(h.crossing ? [6, 4] : []);
      ctx.strokeStyle = h.crossing ? "#2f9e44" : "#1a7fd4";
      ctx.fillStyle = h.crossing ? "rgba(47,158,68,0.10)" : "rgba(26,127,212,0.10)";
      ctx.fillRect(a[0], a[1], b[0] - a[0], b[1] - a[1]);
      ctx.strokeRect(a[0], a[1], b[0] - a[0], b[1] - a[1]);
    }
    if (h.k === "label") {
      const s = this.toScreen(h.p);
      ctx.setLineDash([]);
      ctx.font = "12px system-ui, sans-serif";
      ctx.fillStyle = "rgba(15,23,42,0.85)";
      const w = ctx.measureText(h.text).width + 10;
      ctx.fillRect(s[0] + 12, s[1] - 26, w, 19);
      ctx.fillStyle = "#fff";
      ctx.fillText(h.text, s[0] + 17, s[1] - 12);
    }
    ctx.restore();
  }

  drawSelectionMarkers() {
    if (!this.selection.size) return;
    const ctx = this.ctx;
    ctx.save();
    ctx.fillStyle = "#e2680f";
    ctx.setLineDash([]);
    for (const id of this.selection) {
      const e = this.drawing.byId(id);
      if (!e) continue;
      for (const p of gripPoints(e)) {
        const s = this.toScreen(p);
        ctx.fillRect(s[0] - 3, s[1] - 3, 6, 6);
      }
    }
    ctx.restore();
  }

  drawSnap(snap) {
    const ctx = this.ctx;
    const s = this.toScreen(snap.p);
    ctx.save();
    ctx.strokeStyle = "#0f9d58";
    ctx.fillStyle = "rgba(15,157,88,0.15)";
    ctx.lineWidth = 1.8;
    ctx.setLineDash([]);
    const r = 6;
    switch (snap.kind) {
      case "endpoint":
        ctx.strokeRect(s[0] - r, s[1] - r, r * 2, r * 2); break;
      case "midpoint":
        ctx.beginPath();
        ctx.moveTo(s[0], s[1] - r); ctx.lineTo(s[0] + r, s[1] + r);
        ctx.lineTo(s[0] - r, s[1] + r); ctx.closePath(); ctx.stroke(); break;
      case "center":
        ctx.beginPath(); ctx.arc(s[0], s[1], r, 0, Math.PI * 2); ctx.stroke(); break;
      case "intersection":
        ctx.beginPath();
        ctx.moveTo(s[0] - r, s[1] - r); ctx.lineTo(s[0] + r, s[1] + r);
        ctx.moveTo(s[0] + r, s[1] - r); ctx.lineTo(s[0] - r, s[1] + r);
        ctx.stroke(); break;
      case "quadrant":
        ctx.beginPath();
        ctx.moveTo(s[0], s[1] - r); ctx.lineTo(s[0] + r, s[1]);
        ctx.lineTo(s[0], s[1] + r); ctx.lineTo(s[0] - r, s[1]);
        ctx.closePath(); ctx.stroke(); break;
      case "perpendicular":
        ctx.beginPath();
        ctx.moveTo(s[0] - r, s[1] - r); ctx.lineTo(s[0] - r, s[1] + r);
        ctx.lineTo(s[0] + r, s[1] + r);
        ctx.moveTo(s[0] - r, s[1] + 2); ctx.lineTo(s[0] - 2, s[1] + 2);
        ctx.lineTo(s[0] - 2, s[1] + r); ctx.stroke(); break;
      default:
        ctx.beginPath(); ctx.arc(s[0], s[1], 3.5, 0, Math.PI * 2); ctx.stroke();
    }
    if (snap.label) {
      ctx.font = "11px system-ui, sans-serif";
      ctx.fillStyle = "rgba(15,23,42,0.82)";
      const w = ctx.measureText(snap.label).width + 8;
      ctx.fillRect(s[0] + 10, s[1] + 8, w, 17);
      ctx.fillStyle = "#fff";
      ctx.fillText(snap.label, s[0] + 14, s[1] + 20);
    }
    ctx.restore();
  }
}

export function gripPoints(e) {
  switch (e.type) {
    case "line": return [e.a, G.lerp(e.a, e.b, 0.5), e.b];
    case "circle": return [e.c, G.arcPoint(e.c, e.r, 0), G.arcPoint(e.c, e.r, 90),
      G.arcPoint(e.c, e.r, 180), G.arcPoint(e.c, e.r, 270)];
    case "arc": return [e.c, G.arcPoint(e.c, e.r, e.start), G.arcPoint(e.c, e.r, e.end)];
    case "polyline": case "hatch": return e.pts;
    case "text": case "point": return [e.p];
    case "dim": return [e.p1, e.p2, e.pos];
    default: return [];
  }
}
