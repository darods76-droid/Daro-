// Bemassung, Schraffur und Schriftfeld als Zeichenprimitive.
// Spiegelt daro_cad/primitives.py, damit Bildschirm und Export identisch sind.
import * as G from "./geom.js";
import { parseScale, sheetSize } from "./doc.js";

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

/** Bemassung in Linien, Pfeile und Text aufloesen (Modellkoordinaten). */
export function dimPrimitives(dim, color, lw, scale, comma = true) {
  const paper = (v) => v / scale;
  const out = [];
  const { p1, p2, pos } = dim;
  const h = paper(dim.h || 3.5);
  const alen = paper(ARROW_LEN);
  const label = dimText(dim, comma);
  const kind = dim.kind || "linear";

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
    return out;
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
    return out;
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
        "#666666", 0, "start", "base"));
    }
    const value = String(c.value || "");
    if (value) {
      const vy = c.h <= 12 ? y + 1.6 : y + (c.h - c.vh) / 2;
      out.push(text(P(x + c.w / 2, vy), c.vh / scale, value, color, 0, "middle", "base"));
    }
    if (c.label === "Projektion") {
      const px = x + c.w / 2, py = y + c.h / 2 - 1;
      for (const prim of projectionSymbol(px, py, 6, meta.projection === "first",
        color, SHEET_LW)) {
        out.push(scalePrim(prim, scale));
      }
    }
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
