// Dokumentmodell im Browser -- identisches JSON wie der Python-Kern.
import * as G from "./geom.js";

export const LINETYPES = {
  continuous: [],
  dashed: [4, 2],
  dotted: [0.4, 1.6],
  center: [12, 2, 2, 2],
  phantom: [12, 2, 2, 2, 2, 2],
};

export const LINETYPE_LABELS = {
  continuous: "Volllinie",
  dashed: "Strichlinie (verdeckt)",
  dotted: "Punktlinie",
  center: "Strichpunktlinie (Mitte)",
  phantom: "Strich-Zweipunkt",
};

export const WIDE = 0.5, NARROW = 0.25;

export const DEFAULT_LAYERS = [
  { name: "Kontur", color: "#111111", lineweight: WIDE, linetype: "continuous" },
  { name: "Verdeckt", color: "#8a6d3b", lineweight: NARROW, linetype: "dashed" },
  { name: "Mittellinie", color: "#b03060", lineweight: NARROW, linetype: "center" },
  { name: "Bemassung", color: "#1c6ea4", lineweight: NARROW, linetype: "continuous" },
  { name: "Schraffur", color: "#4a7f4a", lineweight: NARROW, linetype: "continuous" },
  { name: "Hilfslinie", color: "#999999", lineweight: NARROW, linetype: "continuous", printable: false },
  { name: "Text", color: "#111111", lineweight: NARROW, linetype: "continuous" },
];

export const SHEETS = {
  A4: [210, 297], A4L: [297, 210], A3: [420, 297],
  A2: [594, 420], A1: [841, 594], A0: [1189, 841],
};

export const SCALES = ["50:1", "20:1", "10:1", "5:1", "2:1", "1:1", "1:2", "1:2.5",
  "1:5", "1:10", "1:20", "1:50", "1:100", "1:200", "1:500", "1:1000"];

export const DEFAULT_META = {
  title: "Bauteil", subtitle: "", drawingNumber: "0001", revision: "0", date: "",
  author: "", approvedBy: "", company: "", material: "S235JR", weight: "",
  scale: "1:1", sheet: "A3", landscape: true, sheetName: "1", sheetCount: "1",
  projection: "first", generalTolerance: "ISO 2768-m", surface: "", units: "mm",
  decimalComma: true, docType: "Technische Zeichnung",
};

let idCounter = 0;
// Wie tief Bloecke ineinander stecken duerfen -- verhindert Endlosschleifen,
// wenn ein Block (versehentlich) sich selbst enthaelt.
export const MAX_BLOCK_DEPTH = 8;

export function newId() {
  idCounter += 1;
  return "e" + Date.now().toString(36) + idCounter.toString(36);
}

export function parseScale(text) {
  if (typeof text !== "string") return 1;
  if (text.includes(":")) {
    const [a, b] = text.split(":");
    const n = parseFloat(a), d = parseFloat(b);
    return d ? n / d : 1;
  }
  return parseFloat(text) || 1;
}

export function sheetSize(name, landscape = true) {
  const size = SHEETS[name] || SHEETS.A3;
  if (name === "A4") return size;
  return landscape && size[1] > size[0] ? [size[1], size[0]] : size;
}

// -- Entitaeten ------------------------------------------------------------

export const TOL_MODES = ["none", "sym", "limits", "fit"];

export const FCF_SYMBOLS = ["Geradheit", "Ebenheit", "Rundheit", "Zylindrizitaet",
  "Linienprofil", "Flaechenprofil", "Parallelitaet", "Rechtwinkligkeit",
  "Neigung", "Position", "Konzentrizitaet", "Symmetrie", "Rundlauf", "Gesamtlauf"];

export const FCF_LABELS = {
  Geradheit: "Geradheit", Ebenheit: "Ebenheit", Rundheit: "Rundheit",
  Zylindrizitaet: "Zylindrizität", Linienprofil: "Linienprofil",
  Flaechenprofil: "Flächenprofil", Parallelitaet: "Parallelität",
  Rechtwinkligkeit: "Rechtwinkligkeit", Neigung: "Neigung", Position: "Position",
  Konzentrizitaet: "Konzentrizität", Symmetrie: "Symmetrie",
  Rundlauf: "Rundlauf", Gesamtlauf: "Gesamtlauf",
};

/** Ellipse als Polygonzug -- gleiche Schrittregel wie ellipse_points in Python. */
export function ellipsePoints(e, sagitta = 0.05) {
  const { c, rx, ry } = e;
  const start = e.start ?? 0;
  const end = e.end ?? 360;
  let sweep = end - start;
  if (Math.abs(sweep) < 1e-9) sweep = 360;
  const r = Math.max(rx, ry);
  const ratio = r > sagitta ? Math.max(0, Math.min(1, 1 - sagitta / r)) : 0;
  const step = ratio < 1 ? Math.acos(ratio) * 2 * 180 / Math.PI : 5;
  const n = Math.max(16, Math.ceil(Math.abs(sweep) / Math.max(step, 0.5)));
  const rot = (e.rot || 0) * Math.PI / 180;
  const ca = Math.cos(rot), sa = Math.sin(rot);
  const out = [];
  for (let i = 0; i <= n; i++) {
    const a = (start + sweep * i / n) * Math.PI / 180;
    const x = rx * Math.cos(a), y = ry * Math.sin(a);
    out.push([c[0] + x * ca - y * sa, c[1] + x * sa + y * ca]);
  }
  return out;
}

export function entityPoints(e) {
  switch (e.type) {
    case "line": return [e.a, e.b];
    case "circle": return [[e.c[0] - e.r, e.c[1] - e.r], [e.c[0] + e.r, e.c[1] + e.r]];
    case "arc": {
      const pts = [G.arcPoint(e.c, e.r, e.start), G.arcPoint(e.c, e.r, e.end)];
      for (const a of [0, 90, 180, 270]) {
        if (G.arcContains(e.start, e.end, a)) pts.push(G.arcPoint(e.c, e.r, a));
      }
      return pts;
    }
    case "polyline": case "hatch": return e.pts;
    case "ellipse": {
      const r = Math.max(e.rx, e.ry);
      return [[e.c[0] - r, e.c[1] - r], [e.c[0] + r, e.c[1] + r]];
    }
    case "leader": return [e.p1, e.p2];
    case "text": case "point": case "surface": case "fcf": return [e.p];
    case "dim": return e.center ? [e.p1, e.p2, e.pos, e.center] : [e.p1, e.p2, e.pos];
    // Blockverweis: ohne die Zeichnung ist nur der Einfuegepunkt bekannt --
    // die wirkliche Ausdehnung liefert `drawing.flatten()`.
    case "insert": return [e.p];
    default: return [];
  }
}

export function entityBBox(e, drawing = null) {
  if (e.type === "insert" && drawing) {
    const pts = [];
    for (const sub of drawing.resolveInsert(e)) pts.push(...entityPoints(sub));
    return pts.length ? G.bbox(pts) : G.bbox([e.p]);
  }
  return G.bbox(entityPoints(e));
}

export function polylineSegments(e) {
  const pts = e.pts || [], n = pts.length;
  if (n < 2) return [];
  const bulges = e.bulges || [];
  const idx = [];
  for (let i = 0; i < n - 1; i++) idx.push(i);
  if (e.closed) idx.push(n - 1);
  const out = [];
  for (const i of idx) {
    const a = pts[i], b = pts[(i + 1) % n];
    const bulge = bulges[i] || 0;
    const arc = bulge ? G.bulgeToArc(a, b, bulge) : null;
    out.push(arc ? { kind: "arc", ...arc } : { kind: "line", a, b });
  }
  return out;
}

export function outlinePoints(e) {
  switch (e.type) {
    case "line": return [e.a, e.b];
    case "circle": return G.flattenArc(e.c, e.r, 0, 360, 0.05, 16).slice(0, -1);
    case "ellipse": return ellipsePoints(e);
    case "arc": return G.flattenArc(e.c, e.r, e.start, e.end);
    case "polyline": case "hatch": {
      const pts = [];
      for (const seg of polylineSegments(e)) {
        const part = seg.kind === "line" ? [seg.a, seg.b]
          : G.flattenArc(seg.c, seg.r, seg.start, seg.end);
        const from = pts.length && G.eq(pts[pts.length - 1], part[0]) ? 1 : 0;
        for (let i = from; i < part.length; i++) pts.push(part[i]);
      }
      return pts.length ? pts : (e.pts || []);
    }
    default: return entityPoints(e);
  }
}

/** Abstand eines Punktes zur Entitaet -- fuer Auswahl und Fangen. */
export function distanceTo(e, p, drawing = null) {
  switch (e.type) {
    case "insert": {
      if (!drawing) return Infinity;
      let best = Infinity;
      for (const sub of drawing.resolveInsert(e)) {
        best = Math.min(best, distanceTo(sub, p, drawing));
      }
      return best;
    }
    case "line": return G.distToSegment(p, e.a, e.b);
    case "circle": return Math.abs(G.dist(p, e.c) - e.r);
    case "arc": return G.distToArc(p, e.c, e.r, e.start, e.end);
    case "polyline": {
      let best = Infinity;
      for (const seg of polylineSegments(e)) {
        best = Math.min(best, seg.kind === "line"
          ? G.distToSegment(p, seg.a, seg.b)
          : G.distToArc(p, seg.c, seg.r, seg.start, seg.end));
      }
      return best;
    }
    case "hatch": {
      const pts = outlinePoints(e);
      let best = Infinity;
      for (let i = 0; i < pts.length; i++) {
        best = Math.min(best, G.distToSegment(p, pts[i], pts[(i + 1) % pts.length]));
      }
      return G.pointInPolygon(p, pts) ? Math.min(best, 0.5) : best;
    }
    case "text": {
      const w = (e.text || "").length * e.h * 0.55;
      const dx = { left: 0, center: -w / 2, right: -w }[e.align || "left"] || 0;
      const box = [e.p[0] + dx, e.p[1], e.p[0] + dx + w, e.p[1] + e.h];
      const cx = Math.max(box[0], Math.min(p[0], box[2]));
      const cy = Math.max(box[1], Math.min(p[1], box[3]));
      return G.dist(p, [cx, cy]);
    }
    case "point": return G.dist(p, e.p);
    case "ellipse": {
      const pts = ellipsePoints(e);
      let best = Infinity;
      for (let i = 0; i < pts.length - 1; i++) {
        best = Math.min(best, G.distToSegment(p, pts[i], pts[i + 1]));
      }
      return best;
    }
    case "leader": return Math.min(G.distToSegment(p, e.p1, e.p2), G.dist(p, e.p2));
    case "surface": case "fcf": return G.dist(p, e.p);
    case "dim": {
      let best = Math.min(G.dist(p, e.p1), G.dist(p, e.p2), G.dist(p, e.pos));
      best = Math.min(best, G.distToSegment(p, e.p1, e.pos), G.distToSegment(p, e.p2, e.pos));
      return best;
    }
    default: return Infinity;
  }
}

/**
 * Ein Element aus dem Blockraum in die Zeichnung setzen.
 *
 * Nur Drehstreckung: gleichmaessiger Massstab, Drehung, Verschiebung.  Weil
 * Winkel dabei erhalten bleiben, genuegt es, Punkte abzubilden, Halbmesser und
 * Schrifthoehen zu strecken und Winkel zu drehen -- Woelbungen der Polylinie
 * bleiben unveraendert.  Wortgleich zu `place_entity` in daro_cad/model.py.
 */
export function placeEntity(e, base, target, rot = 0, scale = 1) {
  const ca = Math.cos(rot * Math.PI / 180), sa = Math.sin(rot * Math.PI / 180);
  const map = (pt) => {
    const x = (pt[0] - base[0]) * scale, y = (pt[1] - base[1]) * scale;
    return [target[0] + x * ca - y * sa, target[1] + x * sa + y * ca];
  };
  const out = JSON.parse(JSON.stringify(e));
  out.id = newId();
  const abs = Math.abs(scale);
  switch (out.type) {
    case "line": out.a = map(out.a); out.b = map(out.b); break;
    case "circle": case "arc":
      out.c = map(out.c); out.r *= abs;
      if (out.type === "arc") {
        out.start = G.normAngle(out.start + rot);
        out.end = G.normAngle(out.end + rot);
      }
      break;
    case "polyline": case "hatch":
      out.pts = out.pts.map(map);
      if (out.type === "hatch") { out.angle += rot; out.spacing *= abs; }
      break;
    case "ellipse":
      out.c = map(out.c); out.rx *= abs; out.ry *= abs; out.rot += rot; break;
    case "leader":
      out.p1 = map(out.p1); out.p2 = map(out.p2); out.h *= abs; break;
    case "text": case "surface":
      out.p = map(out.p); out.h *= abs; out.rot += rot; break;
    case "fcf":
      // Der Rahmen nach ISO 1101 steht immer waagerecht -- nicht mitdrehen
      out.p = map(out.p); out.h *= abs; break;
    case "point": out.p = map(out.p); break;
    case "dim":
      out.p1 = map(out.p1); out.p2 = map(out.p2); out.pos = map(out.pos);
      if (out.center) out.center = map(out.center);
      out.h *= abs;
      break;
    case "insert":
      out.p = map(out.p); out.rot += rot; out.scale *= scale; break;
  }
  return out;
}

/** Entitaet um einen Vektor verschieben (in place auf einer Kopie). */
export function transformEntity(e, fn) {
  const out = JSON.parse(JSON.stringify(e));
  const map = (p) => fn(p);
  switch (out.type) {
    case "line": out.a = map(out.a); out.b = map(out.b); break;
    case "circle": case "arc": {
      const before = out.c;
      out.c = map(before);
      if (out.type === "arc") {
        // Drehung/Spiegelung wirkt auch auf die Winkel
        const p0 = map(G.arcPoint(before, out.r, out.start));
        const p1 = map(G.arcPoint(before, out.r, out.end));
        const s = G.angleOf(G.sub(p0, out.c));
        const eAng = G.angleOf(G.sub(p1, out.c));
        const mid = map(G.arcPoint(before, out.r, out.start + G.arcSweep(out.start, out.end) / 2));
        const mAng = G.angleOf(G.sub(mid, out.c));
        if (G.arcContains(s, eAng, mAng)) { out.start = s; out.end = eAng; }
        else { out.start = eAng; out.end = s; }
        out.r = G.dist(out.c, p0);
      } else {
        out.r = G.dist(out.c, map(G.arcPoint(before, out.r, 0)));
      }
      break;
    }
    case "polyline": case "hatch": out.pts = out.pts.map(map); break;
    case "ellipse": {
      const before = out.c;
      out.c = map(before);
      const axis = map(G.add(before, G.polar([0, 0], out.rot || 0, out.rx)));
      out.rx = G.dist(out.c, axis);
      out.rot = G.angleOf(G.sub(axis, out.c));
      break;
    }
    case "leader": out.p1 = map(out.p1); out.p2 = map(out.p2); break;
    case "text": case "point": case "surface": case "fcf": case "insert":
      out.p = map(out.p); break;
    case "dim":
      out.p1 = map(out.p1); out.p2 = map(out.p2); out.pos = map(out.pos);
      if (out.center) out.center = map(out.center);
      break;
  }
  return out;
}

// -- Dokument --------------------------------------------------------------

export class Drawing extends EventTarget {
  constructor() {
    super();
    this.meta = { ...DEFAULT_META };
    this.layers = DEFAULT_LAYERS.map((l) => ({ visible: true, locked: false, printable: true, ...l }));
    this.entities = [];
    this.solids = [];
    // Bloecke: Name -> {entities, base}.  Die Elemente liegen im Blockraum;
    // beim Einfuegen wandert `base` auf den Zielpunkt.
    this.blocks = {};
    this.activeLayer = "Kontur";
    this.undoStack = [];
    this.redoStack = [];
    this.limit = 200;
    this.lastState = this.snapshot();   // Zustand vor der naechsten Aenderung
  }

  get scaleFactor() { return parseScale(this.meta.scale); }
  sheetSize() { return sheetSize(this.meta.sheet, this.meta.landscape); }
  sheetSizeModel() {
    const [w, h] = this.sheetSize(), s = this.scaleFactor;
    return [w / s, h / s];
  }

  layer(name) {
    return this.layers.find((l) => l.name === name) || this.layers[0];
  }

  snapshot() {
    return JSON.stringify({ meta: this.meta, layers: this.layers,
      entities: this.entities, solids: this.solids, blocks: this.blocks,
      activeLayer: this.activeLayer });
  }

  /**
   * Aenderung abschliessen: der Zustand *vor* der Aenderung wandert auf den
   * Rueckgaengig-Stapel, der neue Zustand wird zum Bezugspunkt.
   */
  commit(label = "") {
    this.undoStack.push({ label, state: this.lastState });
    if (this.undoStack.length > this.limit) this.undoStack.shift();
    this.redoStack.length = 0;
    this.lastState = this.snapshot();
    this.changed();
  }

  restore(text) {
    const data = JSON.parse(text);
    this.meta = data.meta;
    this.layers = data.layers;
    this.entities = data.entities;
    this.solids = data.solids || [];
    this.blocks = data.blocks || {};
    this.activeLayer = data.activeLayer || this.layers[0].name;
    this.lastState = text;
  }

  undo() {
    if (!this.undoStack.length) return false;
    const entry = this.undoStack.pop();
    this.redoStack.push({ label: entry.label, state: this.lastState });
    this.restore(entry.state);
    this.changed();
    return true;
  }

  redo() {
    if (!this.redoStack.length) return false;
    const entry = this.redoStack.pop();
    this.undoStack.push({ label: entry.label, state: this.lastState });
    this.restore(entry.state);
    this.changed();
    return true;
  }

  changed() { this.dispatchEvent(new CustomEvent("change")); }

  add(entity, layer) {
    const e = { id: newId(), layer: layer || this.activeLayer, ...entity };
    this.entities.push(e);
    return e;
  }

  remove(ids) {
    const set = new Set(ids);
    this.entities = this.entities.filter((e) => !set.has(e.id));
  }

  byId(id) { return this.entities.find((e) => e.id === id); }

  // -- Bloecke -------------------------------------------------------------

  /** Einen Block anlegen oder ueberschreiben. */
  defineBlock(name, entities, base = [0, 0]) {
    const blk = { base: [base[0], base[1]],
      entities: entities.map((e) => ({ ...JSON.parse(JSON.stringify(e)), id: newId() })) };
    this.blocks[String(name)] = blk;
    return blk;
  }

  blockNames() { return Object.keys(this.blocks).sort((a, b) => a.localeCompare(b, "de")); }

  /** Einen Blockverweis in gewoehnliche Elemente aufloesen. */
  resolveInsert(ins, depth = 0) {
    const blk = this.blocks[ins.name];
    if (!blk || depth >= MAX_BLOCK_DEPTH) return [];
    const names = new Set(this.layers.map((l) => l.name));
    const out = [];
    for (const src of blk.entities) {
      const ent = placeEntity(src, blk.base || [0, 0], ins.p, ins.rot || 0,
        ins.scale === undefined ? 1 : ins.scale);
      if (!names.has(ent.layer)) ent.layer = ins.layer;
      if (ent.type === "insert") out.push(...this.resolveInsert(ent, depth + 1));
      else out.push(ent);
    }
    return out;
  }

  /** Elementliste, in der jeder Blockverweis durch seinen Inhalt ersetzt ist. */
  flatten(entities = null) {
    const out = [];
    for (const e of (entities || this.entities)) {
      if (e.type === "insert") out.push(...this.resolveInsert(e));
      else out.push(e);
    }
    return out;
  }

  visible() {
    return this.entities.filter((e) => {
      const l = this.layer(e.layer);
      return l && l.visible;
    });
  }

  selectable() {
    return this.visible().filter((e) => !this.layer(e.layer).locked);
  }

  /** Sichtbare Geometrie zum Fangen -- Bloecke sind darin aufgeloest. */
  snapTargets() {
    return this.flatten(this.visible()).filter((e) => {
      const l = this.layer(e.layer);
      return l && l.visible;
    });
  }

  bbox() {
    const pts = [];
    for (const e of this.flatten()) pts.push(...entityPoints(e));
    return G.bbox(pts);
  }

  toJSON() {
    return { version: 1, meta: this.meta, layers: this.layers,
      entities: this.entities, solids: this.solids, blocks: this.blocks };
  }

  load(data) {
    this.meta = { ...DEFAULT_META, ...(data.meta || {}) };
    this.layers = (data.layers && data.layers.length)
      ? data.layers.map((l) => ({ visible: true, locked: false, printable: true, ...l }))
      : DEFAULT_LAYERS.map((l) => ({ visible: true, locked: false, printable: true, ...l }));
    const names = new Set(this.layers.map((l) => l.name));
    this.entities = (data.entities || []).map((e) => ({
      ...e, id: e.id || newId(), layer: names.has(e.layer) ? e.layer : this.layers[0].name }));
    this.solids = data.solids || [];
    this.blocks = {};
    for (const [name, blk] of Object.entries(data.blocks || {})) {
      this.defineBlock(name, (blk || {}).entities || [], (blk || {}).base || [0, 0]);
    }
    if (!names.has(this.activeLayer)) this.activeLayer = this.layers[0].name;
    this.undoStack.length = 0;
    this.redoStack.length = 0;
    this.lastState = this.snapshot();
    this.changed();
  }
}
