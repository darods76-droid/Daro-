// Bemassung, Schraffur und Schriftfeld als Zeichenprimitive.
// Spiegelt daro_cad/primitives.py, damit Bildschirm und Export identisch sind.
import * as G from "./geom.js";
import { parseScale, sheetSize, polylineSegments, outlinePoints,
         ellipsePoints } from "./doc.js";

export const ARROW_LEN = 3.5, ARROW_W = 1.2, EXT_GAP = 0.8, EXT_OVER = 2.0,
  TEXT_GAP = 1.0, FRAME_LW = 0.7, SHEET_LW = 0.25;
export const TITLE_BLOCK_W = 180, TITLE_BLOCK_H = 63;

const line = (a, b, color, lw, lt = "continuous") => ({ k: "line", a, b, color, lw, lt });
const text = (p, h, t, color = "#111111", rot = 0, anchor = "start", valign = "base") =>
  ({ k: "text", p, h, text: t, color, rot, anchor, valign, lw: 0.25, lt: "continuous" });

export function formatValue(value, decimals = 1, comma = true) {
  let t = value.toFixed(Math.max(0, decimals));
  if (t.includes(".")) t = t.replace(/0+$/, "").replace(/\.$/, "");
  if (t === "" || t === "-0") t = "0";
  return comma ? t.replace(".", ",") : t;
}

export function arrow(tip, dir, size, color) {
  let d = G.normalize(dir);
  if (!d[0] && !d[1]) d = [1, 0];
  const base = G.add(tip, G.mul(d, size));
  const off = G.mul(G.perp(d), size * ARROW_W / ARROW_LEN);
  return { k: "fill", pts: [tip, G.add(base, off), G.sub(base, off)], color, lw: 0, lt: "continuous" };
}

export function dimAxis(dim) {
  const axis = dim.axis || "auto";
  if (axis !== "auto") return axis;
  return Math.abs(dim.p2[0] - dim.p1[0]) >= Math.abs(dim.p2[1] - dim.p1[1]) ? "x" : "y";
}

export function dimMeasure(dim) {
  const { p1, p2 } = dim;
  switch (dim.kind) {
    case "aligned": return G.dist(p1, p2);
    case "radius": return G.dist(p1, p2);
    case "diameter": return G.dist(p1, p2) * 2;
    case "angular": {
      const c = dim.center || [0, 0];
      const a1 = G.angleOf(G.sub(p1, c)), a2 = G.angleOf(G.sub(p2, c));
      const s = G.normAngle(a2 - a1);
      return s <= 180 ? s : 360 - s;
    }
    default:
      return dimAxis(dim) === "x" ? Math.abs(p2[0] - p1[0]) : Math.abs(p2[1] - p1[1]);
  }
}

export function dimText(dim, comma = true) {
  if (dim.text) return String(dim.text);
  const value = dimMeasure(dim);
  const t = formatValue(value, dim.decimals ?? 1, comma);
  if (dim.kind === "angular") return t + "°";
  let prefix = dim.prefix || "";
  if (dim.kind === "diameter" && !prefix.includes("Ø")) prefix = "Ø" + prefix;
  else if (dim.kind === "radius" && !prefix.startsWith("R")) prefix = "R" + prefix;
  return prefix + t + (dim.suffix || "");
}

/**
 * Toleranz am Maß (ISO 129-1 / ISO 286).
 * Rückgabe [anhang, oben, unten] -- der Anhang steht hinter der Grundzahl,
 * Grenzabmaße werden kleiner darüber und darunter gesetzt.
 */
export function dimTolerance(dim, comma = true) {
  const mode = dim.tolMode || "none";
  if (mode === "sym") {
    return [" ±" + formatValue(Math.abs(dim.tolUpper ?? 0.1), 3, comma), null, null];
  }
  if (mode === "fit") return [" " + String(dim.fit ?? "").trim(), null, null];
  if (mode === "limits") {
    const sign = (v) => (v >= 0 ? "+" : "-") + formatValue(Math.abs(v), 3, comma);
    return ["", sign(dim.tolUpper ?? 0.1), sign(dim.tolLower ?? -0.1)];
  }
  return ["", null, null];
}

/** Bemassung in Linien, Pfeile und Text aufloesen (Modellkoordinaten). */
export function dimPrimitives(dim, color, lw, scale, comma = true) {
  const paper = (v) => v / scale;
  const out = [];
  const { p1, p2, pos } = dim;
  const h = paper(dim.h || 3.5);
  const alen = paper(ARROW_LEN);
  const [suffix, tolUp, tolLo] = dimTolerance(dim, comma);
  const label = dimText(dim, comma) + suffix;
  const kind = dim.kind || "linear";

  /** Grenzabmaße klein über und unter die Grundzahl setzen. */
  const withLimits = (prims) => {
    if (tolUp === null) return prims;
    const base = [...prims].reverse().find((q) => q.k === "text");
    if (!base) return prims;
    const small = h * 0.62;
    const dx = h * 0.34 * (label.length + 1);
    for (const [value, dy] of [[tolUp, h * 0.55], [tolLo, -h * 0.55]]) {
      prims.push(text(G.add(base.p, [dx, dy]), small, value, color, base.rot || 0,
        "start", "base"));
    }
    return prims;
  };

  if (kind === "linear" || kind === "aligned") {
    const dir = kind === "aligned"
      ? (G.normalize(G.sub(p2, p1))[0] || G.normalize(G.sub(p2, p1))[1]
        ? G.normalize(G.sub(p2, p1)) : [1, 0])
      : (dimAxis(dim) === "x" ? [1, 0] : [0, 1]);
    const nrm = G.perp(dir);
    const offset = G.dot(G.sub(pos, p1), nrm);
    const d1 = G.add(p1, G.mul(nrm, offset));
    let d2 = G.add(p2, G.mul(nrm, offset));
    d2 = G.add(d1, G.mul(dir, G.dot(G.sub(d2, d1), dir)));
    const sign = offset >= 0 ? 1 : -1;

    for (const [base, tip] of [[p1, d1], [p2, d2]]) {
      const start = G.add(base, G.mul(nrm, sign * paper(EXT_GAP)));
      const end = G.add(tip, G.mul(nrm, sign * paper(EXT_OVER)));
      if (G.dist(start, end) > 1e-6) out.push(line(start, end, color, lw));
    }

    const length = G.dist(d1, d2);
    const inside = length > 3 * alen;
    if (inside) {
      out.push(line(d1, d2, color, lw));
      out.push(arrow(d1, G.sub(d2, d1), alen, color));
      out.push(arrow(d2, G.sub(d1, d2), alen, color));
    } else {
      const ext = G.mul(dir, alen * 2);
      out.push(line(G.sub(d1, ext), G.add(d2, ext), color, lw));
      out.push(arrow(d1, G.mul(dir, -1), alen, color));
      out.push(arrow(d2, dir, alen, color));
    }

    const mid = G.lerp(d1, d2, 0.5);
    let rot = G.angleOf(dir);
    if (rot > 90 && rot <= 270) rot -= 180;
    const tn = G.perp(G.polar([0, 0], rot, 1));
    let anchorPt = G.add(mid, G.mul(tn, paper(TEXT_GAP)));
    if (!inside) anchorPt = G.add(anchorPt, G.mul(dir, alen * 3));
    out.push(text(anchorPt, h, label, color, rot, "middle", "base"));
    return withLimits(out);
  }

  if (kind === "radius" || kind === "diameter") {
    const center = p1, onCircle = p2;
    const radius = G.dist(center, onCircle);
    let dir = G.normalize(G.sub(onCircle, center));
    if (!dir[0] && !dir[1]) dir = [1, 0];
    // Bei kleinen Bohrungen ist im Kreis kein Platz fuer Masslinie und Pfeile;
    // dann nur die Hinweislinie mit einem Pfeil von aussen (ISO 129-1).
    const roomy = radius >= 1.6 * alen;
    if (roomy) {
      if (kind === "diameter") {
        const opposite = G.sub(center, G.mul(dir, radius));
        out.push(line(opposite, onCircle, color, lw));
        out.push(arrow(opposite, dir, alen, color));
      } else {
        out.push(line(center, onCircle, color, lw));
      }
      out.push(arrow(onCircle, G.mul(dir, -1), alen, color));
    } else {
      out.push(arrow(onCircle, dir, alen, color));
    }
    out.push(line(onCircle, pos, color, lw));
    const side = pos[0] >= center[0] ? 1 : -1;
    const tail = G.add(pos, [side * h * 1.5, 0]);
    out.push(line(pos, tail, color, lw));
    out.push(text(G.add(tail, [side * paper(TEXT_GAP), paper(TEXT_GAP)]), h, label, color, 0,
      side > 0 ? "start" : "end", "base"));
    return withLimits(out);
  }

  if (kind === "angular") {
    const c = dim.center || [0, 0];
    let a1 = G.angleOf(G.sub(p1, c)), a2 = G.angleOf(G.sub(p2, c));
    if (G.normAngle(a2 - a1) > 180) { const t = a1; a1 = a2; a2 = t; }
    const radius = G.dist(c, pos);
    const r1 = G.dist(c, p1), r2 = G.dist(c, p2);
    for (const [ang, rr] of [[a1, r1], [a2, r2]]) {
      out.push(line(G.polar(c, ang, Math.min(rr, radius)),
        G.polar(c, ang, Math.max(radius + paper(EXT_OVER), rr)), color, lw));
    }
    out.push({ k: "arc", c, r: radius, start: a1, end: a2, color, lw, lt: "continuous" });
    for (const [ang, way] of [[a1, 1], [a2, -1]]) {
      const tip = G.polar(c, ang, radius);
      const tangent = G.perp(G.normalize(G.sub(tip, c)));
      out.push(arrow(tip, G.mul(tangent, way), alen, color));
    }
    const midAngle = a1 + G.normAngle(a2 - a1) / 2;
    out.push(text(G.polar(c, midAngle, radius + paper(TEXT_GAP) + h * 0.3), h, label,
      color, 0, "middle", "base"));
    return out;
  }
  return out;
}

// -- Beschriftung: Hinweislinie, Oberfläche, Form- und Lagetoleranz ---------

/** Hinweislinie: Pfeil, Knick, waagerechter Auslauf, Text (ISO 128-22). */
export function leaderPrimitives(e, color, lw, scale) {
  const { p1, p2 } = e;
  const h = (e.h || 3.5) / scale;
  const alen = ARROW_LEN / scale;
  const out = [arrow(p1, G.sub(p2, p1), alen, color), line(p1, p2, color, lw)];
  const side = p2[0] >= p1[0] ? 1 : -1;
  const tail = G.add(p2, [side * h * 2, 0]);
  out.push(line(p2, tail, color, lw));
  if (e.text) {
    out.push(text(G.add(tail, [side * TEXT_GAP / scale, TEXT_GAP / scale]),
      h, e.text, color, 0, side > 0 ? "start" : "end", "base"));
  }
  return out;
}

/**
 * Oberflächenangabe nach ISO 1302.
 * Grundsinnbild ist ein Haken mit ungleich langen Schenkeln; ein waagerechter
 * Balken verlangt spanende Bearbeitung, ein Kreis verbietet sie.
 */
export function surfacePrimitives(e, color, lw, scale) {
  const p = e.p;
  const h = (e.h || 3.5) / scale;
  const rot = e.rot || 0;
  const shortLeg = h * 1.6, longLeg = h * 3.2;
  const at = (angle, dist) => G.rotate(G.polar(p, angle, dist), rot, p);

  const left = at(120, shortLeg), right = at(60, longLeg);
  const out = [line(p, left, color, lw), line(p, right, color, lw)];

  const kind = e.kind || "machined";
  if (kind === "machined") {
    out.push(line(left, at(60, shortLeg), color, lw));
  } else if (kind === "nomachine") {
    out.push({ k: "circle", c: at(90, shortLeg * 0.62), r: h * 0.45,
      color, lw, lt: "continuous" });
  }
  if (e.value) out.push(text(at(150, shortLeg * 1.15), h, e.value, color, rot, "end", "base"));
  if (e.value2) out.push(text(at(70, longLeg * 1.05), h, e.value2, color, rot, "start", "base"));
  return out;
}

/** Sinnbilder nach ISO 1101 in einem Kästchen der Kantenlänge s um (cx, cy). */
export function fcfSymbol(name, cx, cy, s, color, lw) {
  const r = s * 0.34;
  const ln = (a, b) => line(a, b, color, lw);
  const circ = (rr) => ({ k: "circle", c: [cx, cy], r: rr, color, lw, lt: "continuous" });
  switch (name) {
    case "Geradheit": return [ln([cx - r, cy], [cx + r, cy])];
    case "Ebenheit": return [{ k: "poly", close: true, color, lw, lt: "continuous",
      pts: [[cx - r, cy - r * 0.6], [cx + r * 0.4, cy - r * 0.6],
            [cx + r, cy + r * 0.6], [cx - r * 0.4, cy + r * 0.6]] }];
    case "Rundheit": return [circ(r)];
    case "Zylindrizitaet": return [circ(r * 0.72),
      ln([cx - r, cy - r], [cx - r, cy + r]), ln([cx + r, cy - r], [cx + r, cy + r])];
    case "Linienprofil": return [{ k: "arc", c: [cx, cy - r * 0.5], r, start: 30, end: 150,
      color, lw, lt: "continuous" }];
    case "Flaechenprofil": return [
      { k: "arc", c: [cx, cy - r * 0.5], r, start: 30, end: 150, color, lw, lt: "continuous" },
      ln([cx - r * 0.9, cy - r * 0.5], [cx + r * 0.9, cy - r * 0.5])];
    case "Parallelitaet": return [ln([cx - r * 0.9, cy - r], [cx - r * 0.1, cy + r]),
      ln([cx + r * 0.1, cy - r], [cx + r * 0.9, cy + r])];
    case "Rechtwinkligkeit": return [ln([cx - r * 0.7, cy - r], [cx - r * 0.7, cy + r]),
      ln([cx - r, cy - r], [cx + r, cy - r])];
    case "Neigung": return [ln([cx - r, cy - r], [cx + r, cy - r]),
      ln([cx - r * 0.6, cy - r], [cx + r * 0.6, cy + r])];
    case "Position": return [circ(r * 0.62),
      ln([cx - r, cy], [cx + r, cy]), ln([cx, cy - r], [cx, cy + r])];
    case "Konzentrizitaet": return [circ(r), circ(r * 0.45)];
    case "Symmetrie": return [ln([cx - r, cy], [cx + r, cy]),
      ln([cx - r * 0.6, cy + r * 0.55], [cx + r * 0.6, cy + r * 0.55]),
      ln([cx - r * 0.6, cy - r * 0.55], [cx + r * 0.6, cy - r * 0.55])];
    case "Rundlauf": case "Gesamtlauf": {
      const out = [arrow([cx + r, cy + r], [-1, -1], s * 0.34, color),
        ln([cx - r, cy - r], [cx + r, cy + r])];
      if (name === "Gesamtlauf") out.push(ln([cx - r, cy - r * 0.35], [cx + r * 0.65, cy + r]));
      return out;
    }
    default: return [circ(r * 0.6)];
  }
}

/** Form- und Lagetoleranz nach ISO 1101: Rahmen mit Sinnbild, Wert, Bezug. */
export function fcfPrimitives(e, color, lw, scale) {
  const h = (e.h || 3.5) / scale;
  const box = h * 2;
  const [x, y] = e.p;
  const rect = (x0, w) => ({ k: "poly", close: true, color, lw, lt: "continuous",
    pts: [[x0, y], [x0 + w, y], [x0 + w, y + box], [x0, y + box]] });

  const out = [rect(x, box)];
  out.push(...fcfSymbol(e.sym || "Position", x + box / 2, y + box / 2, box * 0.72, color, lw));
  let cursor = x + box;

  const tol = String(e.tol ?? "");
  const width = Math.max(box * 2, h * 0.62 * tol.length + h * 1.2);
  out.push(rect(cursor, width));
  out.push(text([cursor + width / 2, y + box * 0.3], h, tol, color, 0, "middle", "base"));
  cursor += width;

  for (const datum of e.datums || []) {
    const w = box * 1.2;
    out.push(rect(cursor, w));
    out.push(text([cursor + w / 2, y + box * 0.3], h, datum, color, 0, "middle", "base"));
    cursor += w;
  }
  return out;
}

/** Parallele Schnittlinien innerhalb eines geschlossenen Polygons. */
export function hatchLines(pts, angleDeg, spacing) {
  if (pts.length < 3 || spacing <= 0) return [];
  const box = G.bbox(pts);
  if (!box) return [];
  const center = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2];
  const diag = G.dist([box[0], box[1]], [box[2], box[3]]) / 2 + spacing;
  const dir = G.polar([0, 0], angleDeg, 1);
  const nrm = G.perp(dir);
  const out = [];
  const steps = Math.min(2000, Math.floor(diag / spacing) + 1);
  for (let i = -steps; i <= steps; i++) {
    const base = G.add(center, G.mul(nrm, i * spacing));
    const a = G.sub(base, G.mul(dir, diag));
    const b = G.add(base, G.mul(dir, diag));
    const hits = [];
    for (let j = 0; j < pts.length; j++) {
      const p = G.lineLine(a, b, pts[j], pts[(j + 1) % pts.length], false);
      if (!p) continue;
      const e1 = pts[j], e2 = pts[(j + 1) % pts.length];
      if (G.dist(G.closestOnSegment(p, e1, e2), p) > 1e-7) continue;
      hits.push(G.dot(G.sub(p, a), dir));
    }
    hits.sort((x, y) => x - y);
    const merged = [];
    for (const t of hits) if (!merged.length || Math.abs(merged[merged.length - 1] - t) > 1e-7) merged.push(t);
    for (let k = 0; k + 1 < merged.length; k += 2) {
      const s = merged[k], e = merged[k + 1];
      if (e - s < 1e-9) continue;
      const mid = G.add(a, G.mul(dir, (s + e) / 2));
      if (!G.pointInPolygon(mid, pts)) continue;
      out.push([G.add(a, G.mul(dir, s)), G.add(a, G.mul(dir, e))]);
    }
  }
  return out;
}

// -- Entitäten -> Primitive -------------------------------------------------

/** Eine Zeichnungsentität in Primitive auflösen (Spiegel von entity_primitives). */
export function entityPrimitives(drawing, entity) {
  const lay = drawing.layer(entity.layer) || { color: "#111", lineweight: 0.25,
    linetype: "continuous" };
  const color = entity.color || lay.color;
  const lw = entity.lineweight ?? lay.lineweight;
  const lt = entity.linetype || lay.linetype;
  const scale = parseScale(drawing.meta.scale);
  const comma = drawing.meta.decimalComma !== false;

  switch (entity.type) {
    case "line":
      return [line(entity.a, entity.b, color, lw, lt)];
    case "circle":
      return [{ k: "circle", c: entity.c, r: entity.r, color, lw, lt }];
    case "arc":
      return [{ k: "arc", c: entity.c, r: entity.r, start: entity.start, end: entity.end,
        color, lw, lt }];
    case "polyline":
      return polylineSegments(entity).map((seg) => seg.kind === "line"
        ? line(seg.a, seg.b, color, lw, lt)
        : { k: "arc", c: seg.c, r: seg.r, start: seg.start, end: seg.end, color, lw, lt });
    case "text": {
      const anchor = { left: "start", center: "middle", right: "end" }[entity.align || "left"]
        || "start";
      return [text(entity.p, entity.h, entity.text, color, entity.rot || 0, anchor, "base")];
    }
    case "point": {
      const d = 1 / scale;
      return [
        line([entity.p[0] - d, entity.p[1]], [entity.p[0] + d, entity.p[1]], color, lw),
        line([entity.p[0], entity.p[1] - d], [entity.p[0], entity.p[1] + d], color, lw),
      ];
    }
    case "hatch":
      return hatchLines(outlinePoints(entity), entity.angle ?? 45, (entity.spacing ?? 3) / scale)
        .map(([a, b]) => line(a, b, color, lw, "continuous"));
    case "ellipse":
      return [{ k: "poly", pts: ellipsePoints(entity),
        close: Math.abs((entity.end ?? 360) - (entity.start ?? 0)) >= 359.999,
        color, lw, lt }];
    case "leader":
      return leaderPrimitives(entity, color, lw, scale);
    case "surface":
      return surfacePrimitives(entity, color, lw, scale);
    case "fcf":
      return fcfPrimitives(entity, color, lw, scale);
    case "dim":
      return dimPrimitives(entity, color, lw, scale, comma);
    case "insert": {
      // Blockverweis: Inhalt aufloesen und ganz normal zeichnen
      const out = [];
      for (const sub of drawing.resolveInsert(entity)) {
        out.push(...entityPrimitives(drawing, sub));
      }
      return out;
    }
    default:
      return [];
  }
}

/** Alle druckbaren Elemente der Zeichnung als Primitive. */
export function documentPrimitives(drawing, forPrint = true) {
  const out = [];
  for (const e of drawing.entities) {
    const lay = drawing.layer(e.layer);
    if (!lay || !lay.visible) continue;
    if (forPrint && lay.printable === false) continue;
    out.push(...entityPrimitives(drawing, e));
  }
  return out;
}

// -- Schriftfeld nach DIN EN ISO 7200 --------------------------------------

const cell = (x, y, w, h, label, value, vh = 4, lh = 2) => ({ x, y, w, h, label, value, vh, lh });

export function titleBlockCells(meta) {
  const r = TITLE_BLOCK_H / 6, leftW = 110;
  return [
    cell(0, 5 * r, leftW, r, "Firma / Verantwortliche Abteilung", meta.company || ""),
    cell(0, 4 * r, 55, r, "Erstellt durch", meta.author || ""),
    cell(55, 4 * r, 55, r, "Datum", meta.date || ""),
    cell(0, 3 * r, 55, r, "Geprüft durch", meta.approvedBy || ""),
    cell(55, 3 * r, 55, r, "Dokumentenart", meta.docType || "Technische Zeichnung"),
    cell(0, 2 * r, leftW, r, "Werkstoff / Halbzeug", meta.material || ""),
    cell(0, r, 55, r, "Allgemeintoleranz", meta.generalTolerance || ""),
    cell(55, r, 55, r, "Oberfläche", meta.surface || ""),
    cell(0, 0, 37, r, "Maßstab", meta.scale || "1:1"),
    cell(37, 0, 37, r, "Gewicht", meta.weight || ""),
    cell(74, 0, 36, r, "Einheit", meta.units || "mm"),
    cell(leftW, 4 * r, 70, 2 * r, "Benennung", meta.title || "", 6),
    cell(leftW, 2 * r, 70, 2 * r, "Zeichnungsnummer", meta.drawingNumber || "", 7),
    cell(leftW, r, 35, r, "Projektion", ""),
    cell(leftW + 35, r, 35, r, "Format", meta.sheet || "A3"),
    cell(leftW, 0, 35, r, "Revision", meta.revision || ""),
    cell(leftW + 35, 0, 35, r, "Blatt", `${meta.sheetName || "1"} / ${meta.sheetCount || "1"}`),
  ];
}

/** Projektionssymbol (Kegelstumpf) -- Methode 1: Trapez links, Kreise rechts. */
export function projectionSymbol(cx, cy, size, firstAngle, color, lw) {
  const out = [];
  const rOut = size * 0.45, rIn = size * 0.28, gap = size * 0.75, trapW = size * 0.8;
  const circlesX = firstAngle ? cx + gap : cx - gap;
  const trapX = firstAngle ? cx - gap : cx + gap;
  out.push({ k: "circle", c: [circlesX, cy], r: rOut, color, lw, lt: "continuous" });
  out.push({ k: "circle", c: [circlesX, cy], r: rIn, color, lw, lt: "continuous" });
  const x0 = trapX - trapW / 2, x1 = trapX + trapW / 2;
  out.push({ k: "poly", close: true, color, lw, lt: "continuous",
    pts: [[x0, cy - rIn], [x0, cy + rIn], [x1, cy + rOut], [x1, cy - rOut]] });
  out.push(line([cx - size * 0.95, cy], [cx + size * 0.95, cy], color, lw * 0.6, "center"));
  return out;
}

/** Blattrand, Zeichnungsrahmen und Schriftfeld in Modellkoordinaten. */
export function sheetPrimitives(meta) {
  const scale = parseScale(meta.scale);
  const [pw, ph] = sheetSize(meta.sheet, meta.landscape);
  const color = "#111111";
  const P = (x, y) => [x / scale, y / scale];
  const rect = (x, y, w, h, lw, lt = "continuous") => ({
    k: "poly", close: true, color, lw, lt,
    pts: [P(x, y), P(x + w, y), P(x + w, y + h), P(x, y + h)] });

  const out = [rect(0, 0, pw, ph, SHEET_LW)];
  const left = 20, margin = 10;
  const fw = pw - left - margin, fh = ph - 2 * margin;
  out.push(rect(left, margin, fw, fh, FRAME_LW));

  const tbX = left + fw - TITLE_BLOCK_W, tbY = margin;
  out.push(rect(tbX, tbY, TITLE_BLOCK_W, TITLE_BLOCK_H, FRAME_LW));

  for (const c of titleBlockCells(meta)) {
    const x = c.x + tbX, y = c.y + tbY;
    out.push(rect(x, y, c.w, c.h, SHEET_LW));
    if (c.label) {
      out.push(text(P(x + 1.2, y + c.h - c.lh - 0.8), c.lh / scale, c.label,
        "#555555", 0, "start", "base"));
    }
    const value = String(c.value || "");
    if (value) {
      const vy = c.h <= 12 ? y + 1.6 : y + (c.h - c.vh) / 2;
      out.push(text(P(x + c.w / 2, vy), c.vh / scale, value, color, 0, "middle", "base"));
    }
  }

  // Projektionssymbol zuletzt, damit es ueber dem Zellenraster liegt
  for (const c of titleBlockCells(meta)) {
    if (c.label !== "Projektion") continue;
    const px = tbX + c.x + c.w / 2, py = tbY + c.y + c.h / 2 - 1;
    for (const prim of projectionSymbol(px, py, 6, meta.projection === "first",
      color, SHEET_LW)) {
      out.push(scalePrim(prim, scale));
    }
    break;
  }
  return out;
}

function scalePrim(prim, scale) {
  const conv = (p) => [p[0] / scale, p[1] / scale];
  const p = { ...prim };
  if (p.a) p.a = conv(p.a);
  if (p.b) p.b = conv(p.b);
  if (p.c) p.c = conv(p.c);
  if (p.p) p.p = conv(p.p);
  if (typeof p.r === "number") p.r /= scale;
  if (p.k === "text") p.h /= scale;
  if (p.pts) p.pts = p.pts.map(conv);
  return p;
}
