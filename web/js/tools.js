// Werkzeuge und Befehlsablauf der Zeichenflaeche.
import * as G from "./geom.js";
import * as M from "./modify.js";
import * as P from "./prims.js";
import { outlinePoints, newId, ellipsePoints } from "./doc.js";

/** Koordinateneingabe: "100,50" | "@50,0" | "@100<45" | "100<45" */
export function parsePoint(text, last) {
  const t = String(text).trim().replace(/\s+/g, "");
  if (!t) return null;
  const relative = t.startsWith("@");
  const body = relative ? t.slice(1) : t;
  const base = relative ? (last || [0, 0]) : [0, 0];
  const num = (v) => parseFloat(String(v).replace(",", "."));

  if (body.includes("<")) {
    const [r, a] = body.split("<");
    const radius = num(r), angle = num(a);
    if (!isFinite(radius) || !isFinite(angle)) return null;
    return G.polar(base, angle, radius);
  }
  const parts = body.split(/[;/]/).length > 1 ? body.split(/[;/]/) : body.split(",");
  if (parts.length === 2) {
    const x = num(parts[0]), y = num(parts[1]);
    if (!isFinite(x) || !isFinite(y)) return null;
    return [base[0] + x, base[1] + y];
  }
  return null;
}

const ORTHO_ANGLES = [0, 45, 90, 135, 180, 225, 270, 315];

export function applyOrtho(from, to, mode) {
  if (!from || mode === "off") return to;
  const d = G.sub(to, from);
  const dist = G.len(d);
  if (dist < 1e-9) return to;
  if (mode === "ortho") {
    return Math.abs(d[0]) >= Math.abs(d[1])
      ? [to[0], from[1]] : [from[0], to[1]];
  }
  const angle = G.angleOf(d);
  let best = ORTHO_ANGLES[0], bestDiff = 999;
  for (const a of ORTHO_ANGLES) {
    const diff = Math.abs(((angle - a + 540) % 360) - 180);
    if (diff < bestDiff) { bestDiff = diff; best = a; }
  }
  return G.polar(from, best, dist);
}

// ---------------------------------------------------------------------------
// Werkzeugdefinitionen
// ---------------------------------------------------------------------------

/** Ellipse aus Mittelpunkt, Ende der Hauptachse und einem Punkt der Nebenachse. */
function ellipseFrom(c, major, side) {
  const rx = G.dist(c, major);
  if (rx < 1e-9) return null;
  const rot = G.angleOf(G.sub(major, c));
  // Nebenhalbmesser ist der Abstand des dritten Punktes zur Hauptachse
  const rel = G.sub(side, c);
  const ry = Math.abs(G.cross(G.normalize(G.sub(major, c)), rel));
  return { type: "ellipse", c, rx, ry: Math.max(ry, 1e-6), rot, start: 0, end: 360 };
}

/** Gleichseitiges Vieleck, einbeschrieben in den Kreis durch den Eckpunkt. */
function polygonShape(center, corner, sides) {
  const n = Math.max(3, Math.min(64, Math.round(sides || 6)));
  const r = G.dist(center, corner);
  const start = G.angleOf(G.sub(corner, center));
  const pts = [];
  for (let i = 0; i < n; i++) pts.push(G.polar(center, start + 360 * i / n, r));
  return { type: "polyline", pts, closed: true };
}

/** Bogen durch drei Punkte -- der mittlere legt die Richtung fest. */
function arcFrom3(a, b, c) {
  const d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]));
  if (Math.abs(d) < 1e-12) return null;          // die drei Punkte liegen auf einer Geraden
  const sq = (p) => p[0] * p[0] + p[1] * p[1];
  const ux = (sq(a) * (b[1] - c[1]) + sq(b) * (c[1] - a[1]) + sq(c) * (a[1] - b[1])) / d;
  const uy = (sq(a) * (c[0] - b[0]) + sq(b) * (a[0] - c[0]) + sq(c) * (b[0] - a[0])) / d;
  const centre = [ux, uy];
  const r = G.dist(centre, a);
  let start = G.angleOf(G.sub(a, centre));
  let end = G.angleOf(G.sub(c, centre));
  const mid = G.angleOf(G.sub(b, centre));
  // Laeuft der Bogen gegen den Uhrzeigersinn ueber den mittleren Punkt?
  if (!G.arcContains(start, end, mid)) { const t = start; start = end; end = t; }
  return { type: "arc", c: centre, r, start, end };
}

/** Zweiten Eckpunkt so verschieben, dass ein Quadrat entsteht. */
function squareCorner(a, p) {
  const dx = p[0] - a[0], dy = p[1] - a[1];
  const side = Math.max(Math.abs(dx), Math.abs(dy));
  return [a[0] + (dx < 0 ? -side : side), a[1] + (dy < 0 ? -side : side)];
}

/**
 * Rechteck oder Quadrat.
 * Beim Rechteck erzwingt die Umschalttaste ebenfalls gleiche Seiten -- so wie
 * man es aus anderen Zeichenprogrammen kennt.
 */
function rectTool(label, forceSquare) {
  const corner = (s, a, p) =>
    (forceSquare || s.opts.square || s.app.shiftKey) ? squareCorner(a, p) : p;
  const shape = (a, b, layer) => ({
    type: "polyline", closed: true, layer,
    pts: [a, [b[0], a[1]], b, [a[0], b[1]]],
  });
  return {
    label, group: "Zeichnen", picks: 2,
    hints: forceSquare
      ? ["Erste Ecke", "Gegenüberliegende Ecke"]
      : ["Erste Ecke", "Gegenüberliegende Ecke (Umschalt = Quadrat)"],
    build: (s) => {
      const a = s.pts[0];
      return [shape(a, corner(s, a, s.pts[1]))];
    },
    preview(s, p) {
      if (!s.pts.length) return [];
      const a = s.pts[0];
      return [shape(a, corner(s, a, p), s.layer())];
    },
  };
}

const dimTool = (kind, label, extra = {}) => ({
  label, group: "Bemassung", layer: "Bemassung",
  hints: extra.hints || ["Erster Punkt", "Zweiter Punkt", "Lage der Maßlinie"],
  picks: extra.picks || 3,
  build: (s) => {
    const [p1, p2, pos] = s.pts;
    return [{ type: "dim", kind, p1, p2, pos, h: s.app.textHeight,
      decimals: s.app.dimDecimals, tolMode: s.app.tolMode,
      tolUpper: s.app.tolUpper, tolLower: s.app.tolLower, fit: s.app.fit,
      ...(extra.fields ? extra.fields(s) : {}) }];
  },
  ...extra,
});

export const TOOLS = {
  select: { label: "Auswahl", group: "Allgemein", cursor: "default", select: true,
    hints: ["Objekte wählen"] },

  line: {
    label: "Linie", group: "Zeichnen", chain: true, hints: ["Startpunkt", "Nächster Punkt"],
    onPoint(s) {
      if (s.pts.length >= 2) {
        const [a, b] = s.pts.slice(-2);
        if (G.dist(a, b) > 1e-9) s.add({ type: "line", a, b });
        s.commit("Linie");
      }
    },
    preview(s, p) {
      const last = s.pts[s.pts.length - 1];
      return last ? [{ type: "line", a: last, b: p, layer: s.layer() }] : [];
    },
  },

  polyline: {
    label: "Polylinie", group: "Zeichnen", chain: true,
    hints: ["Startpunkt", "Nächster Punkt (Enter beendet, S schließt)"],
    preview(s, p) {
      if (!s.pts.length) return [];
      return [{ type: "polyline", pts: [...s.pts, p], layer: s.layer() }];
    },
    finish(s, close = false) {
      if (s.pts.length >= 2) {
        s.add({ type: "polyline", pts: [...s.pts], closed: close });
        s.commit("Polylinie");
      }
      return true;
    },
  },

  rect: rectTool("Rechteck", false),
  square: rectTool("Quadrat", true),

  circle: {
    label: "Kreis", group: "Zeichnen", picks: 2, hints: ["Mittelpunkt", "Radius / Punkt"],
    build: (s) => {
      const r = s.opts.radius ?? G.dist(s.pts[0], s.pts[1]);
      return r > 1e-9 ? [{ type: "circle", c: s.pts[0], r }] : [];
    },
    preview(s, p) {
      if (!s.pts.length) return [];
      const r = G.dist(s.pts[0], p);
      return r > 1e-9 ? [{ type: "circle", c: s.pts[0], r, layer: s.layer() }] : [];
    },
    onNumber(s, value) {
      if (s.pts.length === 1 && value > 0) {
        s.opts.radius = s.app.diameterInput ? value / 2 : value;
        s.pushPoint(G.add(s.pts[0], [s.opts.radius, 0]));
      }
    },
  },

  arc: {
    label: "Bogen", group: "Zeichnen", picks: 3,
    hints: ["Mittelpunkt", "Startpunkt", "Endpunkt (gegen Uhrzeigersinn)"],
    build: (s) => {
      const [c, a, b] = s.pts;
      const r = G.dist(c, a);
      if (r < 1e-9) return [];
      return [{ type: "arc", c, r, start: G.angleOf(G.sub(a, c)), end: G.angleOf(G.sub(b, c)) }];
    },
    preview(s, p) {
      if (s.pts.length === 1) return [{ type: "circle", c: s.pts[0], r: G.dist(s.pts[0], p),
        layer: "Hilfslinie" }];
      if (s.pts.length === 2) {
        const [c, a] = s.pts;
        return [{ type: "arc", c, r: G.dist(c, a), layer: s.layer(),
          start: G.angleOf(G.sub(a, c)), end: G.angleOf(G.sub(p, c)) }];
      }
      return [];
    },
  },

  ellipse: {
    label: "Ellipse", group: "Zeichnen", picks: 3,
    hints: ["Mittelpunkt", "Ende der Hauptachse", "Nebenachse"],
    build: (s) => {
      const e = ellipseFrom(s.pts[0], s.pts[1], s.pts[2]);
      return e ? [e] : [];
    },
    preview(s, p) {
      if (s.pts.length === 1) {
        return [{ type: "line", a: s.pts[0], b: p, layer: "Hilfslinie" }];
      }
      if (s.pts.length === 2) {
        const e = ellipseFrom(s.pts[0], s.pts[1], p);
        return e ? [{ ...e, layer: s.layer() }] : [];
      }
      return [];
    },
  },

  polygon: {
    label: "Vieleck", group: "Zeichnen", picks: 2,
    hints: ["Mittelpunkt", "Eckpunkt (Seitenzahl in den Einstellungen)"],
    build: (s) => [polygonShape(s.pts[0], s.pts[1], s.app.polygonSides)],
    preview(s, p) {
      if (!s.pts.length) return [];
      return [{ ...polygonShape(s.pts[0], p, s.app.polygonSides), layer: s.layer() }];
    },
  },

  arc3: {
    label: "Bogen 3-Punkt", group: "Zeichnen", picks: 3,
    hints: ["Startpunkt", "Punkt auf dem Bogen", "Endpunkt"],
    build: (s) => {
      const a = arcFrom3(s.pts[0], s.pts[1], s.pts[2]);
      return a ? [a] : [];
    },
    preview(s, p) {
      if (s.pts.length === 1) return [{ type: "line", a: s.pts[0], b: p, layer: "Hilfslinie" }];
      if (s.pts.length === 2) {
        const a = arcFrom3(s.pts[0], s.pts[1], p);
        return a ? [{ ...a, layer: s.layer() }] : [];
      }
      return [];
    },
  },

  point: { label: "Punkt", group: "Zeichnen", picks: 1, hints: ["Position"],
    build: (s) => [{ type: "point", p: s.pts[0] }] },

  text: {
    label: "Text", group: "Zeichnen", picks: 1, layer: "Text", hints: ["Textposition"],
    build: (s) => {
      const value = s.opts.value ?? s.app.askText("Text eingeben:", "");
      if (!value) return [];
      return [{ type: "text", p: s.pts[0], h: s.app.textHeight, text: value, rot: 0 }];
    },
  },

  hatch: {
    label: "Schraffur", group: "Zeichnen", layer: "Schraffur", pickEntities: 1,
    hints: ["Geschlossene Kontur wählen"],
    onEntities(s, entities) {
      const e = entities[0];
      const pts = outlinePoints(e);
      if (pts.length < 3) { s.app.toast("Die gewählte Kontur ist nicht geschlossen."); return true; }
      s.add({ type: "hatch", pts, angle: s.app.hatchAngle, spacing: s.app.hatchSpacing });
      s.commit("Schraffur");
      return true;
    },
  },

  dimlinear: dimTool("linear", "Maß linear"),
  dimaligned: dimTool("aligned", "Maß ausgerichtet"),
  dimangular: dimTool("angular", "Winkelmaß", {
    hints: ["Scheitelpunkt", "Erster Schenkel", "Zweiter Schenkel", "Lage des Bogens"],
    picks: 4,
    build: (s) => {
      const [center, p1, p2, pos] = s.pts;
      return [{ type: "dim", kind: "angular", center, p1, p2, pos,
        h: s.app.textHeight, decimals: 0 }];
    },
  }),
  dimradius: {
    label: "Radiusmaß", group: "Bemassung", layer: "Bemassung", pickEntities: 1, picks: 1,
    hints: ["Kreis oder Bogen wählen", "Lage der Maßzahl"],
    onEntities(s, entities) {
      const e = entities[0];
      if (e.type !== "circle" && e.type !== "arc") {
        s.app.toast("Bitte einen Kreis oder Bogen wählen."); return true;
      }
      s.data.entity = e;
      s.prompt("Lage der Maßzahl");
      return false;
    },
    onPoint(s, p) {
      const e = s.data.entity;
      if (!e) return;
      const dir = G.normalize(G.sub(p, e.c));
      const on = G.add(e.c, G.mul(dir[0] || dir[1] ? dir : [1, 0], e.r));
      s.add({ type: "dim", kind: s.opts.diameter ? "diameter" : "radius",
        p1: e.c, p2: on, pos: p, h: s.app.textHeight, decimals: s.app.dimDecimals });
      s.commit("Radiusmass");
      s.restart();
    },
  },

  leader: {
    label: "Hinweislinie", group: "Bemassung", layer: "Text", picks: 2,
    hints: ["Worauf zeigen?", "Textlage"],
    build: (s) => {
      const value = s.app.askText("Text der Hinweislinie:", s.app.lastLeaderText || "");
      if (!value) return [];
      s.app.lastLeaderText = value;
      return [{ type: "leader", p1: s.pts[0], p2: s.pts[1], text: value,
        h: s.app.textHeight }];
    },
    preview(s, p) {
      if (!s.pts.length) return [];
      return [{ type: "leader", p1: s.pts[0], p2: p, text: "Abc",
        h: s.app.textHeight, layer: s.layer() }];
    },
  },

  surface: {
    label: "Oberfläche", group: "Bemassung", layer: "Text", picks: 1,
    hints: ["Auf welche Fläche zeigen?"],
    build: (s) => [{ type: "surface", p: s.pts[0], h: s.app.textHeight,
      kind: s.app.surfaceKind, value: s.app.surfaceValue }],
    preview(s, p) {
      return [{ type: "surface", p, h: s.app.textHeight, kind: s.app.surfaceKind,
        value: s.app.surfaceValue, layer: s.layer() }];
    },
  },

  fcf: {
    label: "Form & Lage", group: "Bemassung", layer: "Text", picks: 1,
    hints: ["Lage des Rahmens"],
    build: (s) => [{ type: "fcf", p: s.pts[0], h: s.app.textHeight,
      sym: s.app.fcfSymbol, tol: s.app.fcfTolerance,
      datums: String(s.app.fcfDatums || "").split(/[ ,]+/).filter(Boolean) }],
    preview(s, p) {
      return [{ type: "fcf", p, h: s.app.textHeight, sym: s.app.fcfSymbol,
        tol: s.app.fcfTolerance,
        datums: String(s.app.fcfDatums || "").split(/[ ,]+/).filter(Boolean),
        layer: s.layer() }];
    },
  },

  array: {
    label: "Reihe", group: "Aendern", needsSelection: true,
    hints: ["Einstellungen prüfen, dann Enter"],
    picks: 1,
    finish(s) {
      const app = s.app;
      const opts = app.arrayKind === "polar"
        ? { kind: "polar", count: app.arrayCount, total: 360,
            center: s.pts[0] || app.cursor }
        : { kind: "rect", cols: app.arrayCols, rows: app.arrayRows,
            dx: app.arrayDx, dy: app.arrayDy };
      const copies = M.array(s.selectedEntities(), opts);
      if (!copies.length) { app.toast("Die Reihe ergibt keine Kopien."); return true; }
      for (const e of copies) s.addEntity(e);
      s.commit("Reihe");
      app.toast(`${copies.length} Kopien erzeugt.`);
      return true;
    },
    onPoint(s) {
      // Bei der Rundreihe ist der erste Klick der Drehpunkt
      if (s.app.arrayKind === "polar") s.finish();
    },
    hintFor(s) {
      return s.app.arrayKind === "polar" ? "Drehpunkt anklicken" : "Enter drücken";
    },
  },

  blockmake: {
    label: "Block erstellen", group: "Bloecke", needsSelection: true,
    picks: 1, hints: ["Basispunkt anklicken"],
    finish(s) {
      const app = s.app;
      const chosen = s.selectedEntities();
      const name = (app.blockName || "").trim();
      if (!name) { app.toast("Bitte oben einen Namen für den Block eintragen."); return true; }
      if (!chosen.length) { app.toast("Erst Elemente auswählen."); return true; }
      const base = s.pts[0] || app.cursor || [0, 0];
      if (chosen.some((e) => e.type === "insert" && e.name === name)) {
        app.toast("Ein Block kann sich nicht selbst enthalten."); return true;
      }
      s.drawing.defineBlock(name, chosen, base);
      s.drawing.remove(chosen.map((e) => e.id));
      const ins = s.addEntity({ type: "insert", name, p: base, rot: 0, scale: 1,
        layer: chosen[0].layer });
      app.selection = new Set([ins.id]);
      s.commit("Block erstellen");
      app.refreshBlocks();
      app.toast(`Block „${name}" aus ${chosen.length} Elementen erstellt.`);
      return true;
    },
    // Der Klick auf den Basispunkt schliesst das Werkzeug ab
    onPoint(s) { s.finish(); },
  },

  blockinsert: {
    label: "Block einfügen", group: "Bloecke", picks: 1, repeat: true,
    hints: ["Einfügepunkt anklicken"],
    onStart(s) {
      // Ohne Symbole waere das Werkzeug wirkungslos -- dann Bibliothek holen
      if (s.app.stockBlocks()) s.app.toast("Symbole geladen — eins oben auswählen.");
    },
    build(s) {
      const app = s.app;
      const name = app.blockPick;
      if (!name || !s.drawing.blocks[name]) return null;
      return [{ type: "insert", name, p: s.pts[0], rot: app.blockRot || 0,
        scale: app.blockScale || 1 }];
    },
    preview(s, p) {
      const app = s.app;
      const name = app.blockPick;
      if (!name || !s.drawing.blocks[name]) return null;
      return [{ type: "insert", name, p, rot: app.blockRot || 0,
        scale: app.blockScale || 1, layer: s.drawing.activeLayer }];
    },
  },

  measure: {
    label: "Messen", group: "Allgemein", picks: 2, hints: ["Von", "Nach"],
    build: (s) => {
      const [a, b] = s.pts;
      const d = G.dist(a, b);
      const ang = G.angleOf(G.sub(b, a));
      s.app.toast(`Länge ${P.formatValue(d, 3)} mm   ΔX ${P.formatValue(b[0] - a[0], 3)}   ` +
        `ΔY ${P.formatValue(b[1] - a[1], 3)}   Winkel ${P.formatValue(ang, 2)}°`, 8000);
      return [];
    },
    preview(s, p) {
      if (!s.pts.length) return [];
      const a = s.pts[0];
      return { entities: [], hints: [{ k: "line", a, b: p },
        { k: "label", p, text: `${P.formatValue(G.dist(a, p), 2)} mm  /  ` +
          `${P.formatValue(G.angleOf(G.sub(p, a)), 1)}°` }] };
    },
  },

  measurearea: {
    label: "Fläche messen", group: "Allgemein", pickEntities: 1,
    hints: ["Geschlossene Kontur wählen"],
    onEntities(s, entities) {
      const pts = outlinePoints(entities[0]);
      if (pts.length < 3) { s.app.toast("Das ist keine geschlossene Kontur."); return true; }
      const area = Math.abs(G.signedArea(pts));
      let umfang = 0;
      for (let i = 0; i < pts.length; i++) umfang += G.dist(pts[i], pts[(i + 1) % pts.length]);
      s.app.toast(`Fläche ${P.formatValue(area, 1)} mm² ` +
        `(${P.formatValue(area / 100, 2)} cm²)   Umfang ${P.formatValue(umfang, 1)} mm`, 9000);
      return true;
    },
  },

  // -- Aenderungswerkzeuge -------------------------------------------------
  move: {
    label: "Verschieben", group: "Aendern", needsSelection: true, picks: 2,
    hints: ["Basispunkt", "Zielpunkt"],
    apply(s) {
      const v = G.sub(s.pts[1], s.pts[0]);
      s.replaceSelection((e) => M.translate(e, v));
      s.commit("Verschieben");
    },
    preview(s, p) {
      if (s.pts.length !== 1) return [];
      const v = G.sub(p, s.pts[0]);
      return s.selectedEntities().map((e) => M.translate(e, v));
    },
  },

  copy: {
    label: "Kopieren", group: "Aendern", needsSelection: true, picks: 2, repeat: true,
    hints: ["Basispunkt", "Zielpunkt (Enter beendet)"],
    apply(s) {
      const v = G.sub(s.pts[1], s.pts[0]);
      for (const e of s.selectedEntities()) s.addEntity({ ...M.translate(e, v), id: newId() });
      s.commit("Kopieren");
      s.pts = [s.pts[0]];
    },
    preview(s, p) {
      if (s.pts.length !== 1) return [];
      const v = G.sub(p, s.pts[0]);
      return s.selectedEntities().map((e) => M.translate(e, v));
    },
  },

  rotate: {
    label: "Drehen", group: "Aendern", needsSelection: true, picks: 2,
    hints: ["Drehpunkt", "Drehwinkel (Punkt oder Zahl)"],
    apply(s) {
      const angle = s.data.angle ?? G.angleOf(G.sub(s.pts[1], s.pts[0])) - (s.data.ref ?? 0);
      s.replaceSelection((e) => M.rotateEntity(e, s.pts[0], angle));
      s.commit("Drehen");
    },
    onNumber(s, value) {
      if (s.pts.length === 1) {
        s.data.angle = value;
        s.pushPoint(G.polar(s.pts[0], value, 10));
      }
    },
    preview(s, p) {
      if (s.pts.length !== 1) return [];
      const angle = G.angleOf(G.sub(p, s.pts[0]));
      return { entities: s.selectedEntities().map((e) => M.rotateEntity(e, s.pts[0], angle)),
        hints: [{ k: "line", a: s.pts[0], b: p },
          { k: "label", p, text: `${P.formatValue(angle, 1)}°` }] };
    },
  },

  mirror: {
    label: "Spiegeln", group: "Aendern", needsSelection: true, picks: 2,
    hints: ["Erster Punkt der Spiegelachse", "Zweiter Punkt"],
    apply(s) {
      const [a, b] = s.pts;
      if (s.opts.keepOriginal) {
        for (const e of s.selectedEntities()) s.addEntity({ ...M.mirrorEntity(e, a, b), id: newId() });
      } else {
        s.replaceSelection((e) => M.mirrorEntity(e, a, b));
      }
      s.commit("Spiegeln");
    },
    preview(s, p) {
      if (s.pts.length !== 1) return [];
      return { entities: s.selectedEntities().map((e) => M.mirrorEntity(e, s.pts[0], p)),
        hints: [{ k: "line", a: s.pts[0], b: p }] };
    },
  },

  scale: {
    label: "Skalieren", group: "Aendern", needsSelection: true, picks: 2,
    hints: ["Basispunkt", "Faktor (Punkt oder Zahl)"],
    apply(s) {
      const factor = s.data.factor ?? (G.dist(s.pts[0], s.pts[1]) / (s.data.refLen || 1));
      if (!isFinite(factor) || Math.abs(factor) < 1e-9) return;
      s.replaceSelection((e) => M.scaleEntity(e, s.pts[0], factor));
      s.commit("Skalieren");
    },
    onNumber(s, value) {
      if (s.pts.length === 1) {
        s.data.factor = value;
        s.pushPoint(G.add(s.pts[0], [value, 0]));
      }
    },
  },

  offset: {
    label: "Versatz", group: "Aendern", pickEntities: 1, picks: 1, repeat: true,
    hints: ["Element wählen", "Seite anklicken"],
    onEntities(s, entities) {
      s.data.entity = entities[0];
      s.prompt("Seite anklicken");
      return false;
    },
    onPoint(s, p) {
      const result = M.offsetEntity(s.data.entity, s.app.offsetDistance, p);
      if (!result) { s.app.toast("Versatz nicht möglich."); s.restart(); return; }
      s.addEntity({ ...result, id: newId() });
      s.commit("Versatz");
      s.restart();
    },
  },

  trim: {
    label: "Stutzen", group: "Aendern", pickEntities: 1, repeat: true,
    hints: ["Zu stutzendes Stück anklicken"],
    onEntities(s, entities, point) {
      const target = entities[0];
      const others = s.drawing.selectable().filter((e) => e.id !== target.id);
      const pieces = M.trim(target, others, point);
      if (!pieces || !pieces.length) { s.app.toast("Keine Schnittstelle gefunden."); return true; }
      s.drawing.remove([target.id]);
      for (const piece of pieces) s.addEntity({ ...piece, id: newId() });
      s.commit("Stutzen");
      return true;
    },
  },

  extend: {
    label: "Dehnen", group: "Aendern", pickEntities: 1, repeat: true,
    hints: ["Linie nahe dem zu verlängernden Ende anklicken"],
    onEntities(s, entities, point) {
      const target = entities[0];
      const others = s.drawing.selectable().filter((e) => e.id !== target.id);
      const result = M.extend(target, others, point);
      if (!result) { s.app.toast("Keine Begrenzung gefunden."); return true; }
      Object.assign(target, { a: result.a, b: result.b });
      s.commit("Dehnen");
      return true;
    },
  },

  fillet: {
    label: "Runden", group: "Aendern", pickEntities: 2, repeat: true,
    hints: ["Erste Linie", "Zweite Linie"],
    onEntities(s, entities, point, points) {
      const [l1, l2] = entities;
      const result = M.fillet(l1, l2, s.app.filletRadius, points[0], points[1]);
      if (!result) { s.app.toast("Rundung nicht möglich – nur Linien mit gemeinsamem Schnittpunkt."); return true; }
      Object.assign(l1, { a: result.first.a, b: result.first.b });
      Object.assign(l2, { a: result.second.a, b: result.second.b });
      if (result.arc) s.addEntity({ ...result.arc, id: newId(), layer: l1.layer });
      s.commit("Runden");
      return true;
    },
  },

  explode: {
    label: "Auflösen", group: "Aendern", needsSelection: true,
    hints: ["Polylinien wählen, dann Enter"],
    finish(s) {
      let count = 0;
      for (const e of s.selectedEntities()) {
        // Ein Blockverweis wird zu den Elementen, die er darstellt
        const parts = e.type === "insert" ? s.drawing.resolveInsert(e) : M.explode(e);
        if (!parts || !parts.length) continue;
        s.drawing.remove([e.id]);
        for (const part of parts) s.addEntity(part);
        count += parts.length;
      }
      if (count) {
        s.app.selection.clear();
        s.commit("Auflösen");
        s.app.toast(`In ${count} Einzelelemente aufgelöst.`);
      } else {
        s.app.toast("Auflösen geht bei Polylinien, Kreisen und Blöcken.");
      }
      return true;
    },
  },

  erase: {
    label: "Löschen", group: "Aendern", needsSelection: true,
    hints: ["Objekte wählen, dann Enter"],
    finish(s) {
      const ids = [...s.app.selection];
      if (ids.length) {
        s.drawing.remove(ids);
        s.app.selection.clear();
        s.commit("Löschen");
      }
      return true;
    },
  },

  chamfer: {
    label: "Fasen", group: "Aendern", pickEntities: 2, repeat: true,
    hints: ["Erste Linie", "Zweite Linie"],
    onEntities(s, entities, point, points) {
      const [l1, l2] = entities;
      const result = M.chamfer(l1, l2, s.app.chamferSize, points[0], points[1]);
      if (!result) { s.app.toast("Fase nicht möglich."); return true; }
      Object.assign(l1, { a: result.first.a, b: result.first.b });
      Object.assign(l2, { a: result.second.a, b: result.second.b });
      s.addEntity({ ...result.line, id: newId(), layer: l1.layer });
      s.commit("Fasen");
      return true;
    },
  },
};

export const TOOL_GROUPS = ["Allgemein", "Zeichnen", "Bemassung", "Bloecke", "Aendern"];

// ---------------------------------------------------------------------------
// Ablaufsteuerung
// ---------------------------------------------------------------------------

export class Session {
  constructor(app) {
    this.app = app;
    this.drawing = app.drawing;
    this.name = "select";
    this.tool = TOOLS.select;
    this.pts = [];
    this.opts = {};
    this.data = {};
    this.picked = [];
    this.pickedPoints = [];
    this.phase = "idle";
  }

  layer() {
    return this.tool.layer && this.drawing.layer(this.tool.layer)
      ? this.tool.layer : this.drawing.activeLayer;
  }

  start(name, opts = {}) {
    const tool = TOOLS[name];
    if (!tool) return;
    this.reset();
    this.name = name;
    this.tool = tool;
    this.opts = { ...opts };
    if (tool.onStart) tool.onStart(this);
    if (tool.needsSelection && !this.app.selection.size) {
      this.phase = "select";
      this.prompt("Objekte wählen, dann Enter");
    } else {
      this.phase = tool.pickEntities ? "entities" : "points";
      this.prompt(tool.hints ? tool.hints[0] : tool.label);
    }
    this.app.refreshUI();
  }

  restart() {
    const { name, opts } = this;
    this.reset();
    this.name = name;
    this.tool = TOOLS[name];
    this.opts = { ...opts };
    this.phase = this.tool.pickEntities ? "entities" : "points";
    if (this.tool.needsSelection && !this.app.selection.size) this.phase = "select";
    this.prompt(this.tool.hints ? this.tool.hints[0] : this.tool.label);
  }

  reset() {
    this.pts = [];
    this.data = {};
    this.picked = [];
    this.pickedPoints = [];
    this.app.renderer.preview = null;
  }

  cancel() {
    this.reset();
    this.name = "select";
    this.tool = TOOLS.select;
    this.phase = "idle";
    this.prompt("");
    this.app.refreshUI();
  }

  prompt(text) { this.app.setPrompt(text || ""); }

  add(entity) {
    return this.drawing.add({ ...entity }, entity.layer || this.layer());
  }

  addEntity(entity) {
    const e = { id: entity.id || newId(), layer: entity.layer || this.layer(), ...entity };
    this.drawing.entities.push(e);
    return e;
  }

  commit(label) {
    this.drawing.commit(label);
    this.app.invalidate();
  }

  selectedEntities() {
    return this.app.selectedEntities();
  }

  replaceSelection(fn) {
    for (const id of this.app.selection) {
      const idx = this.drawing.entities.findIndex((e) => e.id === id);
      if (idx < 0) continue;
      const updated = fn(this.drawing.entities[idx]);
      this.drawing.entities[idx] = { ...updated, id };
    }
  }

  pushPoint(p) { this.point(p); }

  /** Ein Punkt wurde gesetzt (Klick oder Eingabe). */
  point(p) {
    const tool = this.tool;
    if (this.phase === "select") return;
    if (this.phase === "entities") {
      if (tool.onPoint) tool.onPoint(this, p);
      return;
    }
    this.pts.push(p);
    if (tool.onPoint) tool.onPoint(this, p);

    const need = tool.picks || 0;
    if (need && this.pts.length >= need) {
      if (tool.build) {
        const before = this.drawing.entities.length;
        for (const e of tool.build(this) || []) this.add(e);
        if (this.drawing.entities.length !== before) this.commit(tool.label);
      }
      if (tool.apply) tool.apply(this);
      if (tool.repeat && this.pts.length >= need) {
        if (!tool.apply) this.pts = [];
      } else {
        this.restart();
      }
    }
  }

  /** Elementauswahl im Modus "entities". */
  pickEntity(entity, point) {
    if (!entity) return;
    this.picked.push(entity);
    this.pickedPoints.push(point);
    const need = this.tool.pickEntities || 1;
    if (this.picked.length >= need) {
      const done = this.tool.onEntities
        ? this.tool.onEntities(this, this.picked, point, this.pickedPoints)
        : true;
      if (done !== false) {
        if (this.tool.repeat) {
          this.picked = [];
          this.pickedPoints = [];
          this.prompt(this.tool.hints[0]);
        } else {
          this.restart();
        }
      } else {
        this.phase = "points";
      }
    } else {
      this.prompt(this.tool.hints[this.picked.length] || this.tool.hints[0]);
    }
  }

  /** Auswahlphase abschliessen. */
  confirmSelection() {
    if (this.phase !== "select") return false;
    if (!this.app.selection.size) return false;
    this.phase = "points";
    this.prompt(this.tool.hints ? this.tool.hints[0] : this.tool.label);
    return true;
  }

  finish(close = false) {
    const tool = this.tool;
    if (this.phase === "select") return this.confirmSelection();
    if (tool.finish) {
      const done = tool.finish(this, close);
      if (done) this.restart();
      return true;
    }
    if (this.pts.length) { this.restart(); return true; }
    return false;
  }

  move(p) {
    const tool = this.tool;
    if (!tool.preview) { this.app.renderer.preview = null; return; }
    const result = tool.preview(this, p);
    if (!result) { this.app.renderer.preview = null; return; }
    this.app.renderer.preview = Array.isArray(result)
      ? { entities: result, hints: [] } : result;
  }

  /** Zahleneingabe aus der Befehlszeile (Laenge, Winkel, Faktor). */
  number(value, cursor) {
    const tool = this.tool;
    if (tool.onNumber) { tool.onNumber(this, value); return true; }
    const last = this.pts[this.pts.length - 1];
    if (last && cursor) {
      const dir = G.normalize(G.sub(cursor, last));
      if (dir[0] || dir[1]) { this.point(G.add(last, G.mul(dir, value))); return true; }
    }
    return false;
  }

  get hint() {
    const tool = this.tool;
    if (!tool.hints) return tool.label;
    if (this.phase === "select") return "Objekte wählen, dann Enter";
    const idx = this.phase === "entities" ? this.picked.length : this.pts.length;
    return tool.hints[Math.min(idx, tool.hints.length - 1)];
  }
}
