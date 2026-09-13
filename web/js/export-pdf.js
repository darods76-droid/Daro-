// PDF-Export im Browser -- Uebertragung von daro_cad/pdf_export.py.
// Ein einzelner Content-Stream mit Pfaden und Helvetica-Text (WinAnsi).
// Anders als im Python-Kern wird nicht komprimiert: der Browser bringt kein
// zlib mit, und ein Zeichnungsblatt bleibt auch unkomprimiert klein.
import * as G from "./geom.js";
import * as P from "./prims.js";
import { LINETYPES, parseScale, sheetSize } from "./doc.js";

const MM_TO_PT = 72 / 25.4;

// Helvetica-Zeichenbreiten (1/1000 em) fuer die Textausrichtung.
const W = {
  32: 278, 33: 278, 34: 355, 35: 556, 36: 556, 37: 889, 38: 667, 39: 191,
  40: 333, 41: 333, 42: 389, 43: 584, 44: 278, 45: 333, 46: 278, 47: 278,
  58: 278, 59: 278, 60: 584, 61: 584, 62: 584, 63: 556, 64: 1015,
  65: 667, 66: 667, 67: 722, 68: 722, 69: 667, 70: 611, 71: 778, 72: 722,
  73: 278, 74: 500, 75: 667, 76: 556, 77: 833, 78: 722, 79: 778, 80: 667,
  81: 778, 82: 722, 83: 667, 84: 611, 85: 722, 86: 667, 87: 944, 88: 667,
  89: 667, 90: 611, 91: 278, 92: 278, 93: 278, 94: 469, 95: 556, 96: 333,
  97: 556, 98: 556, 99: 500, 100: 556, 101: 556, 102: 278, 103: 556, 104: 556,
  105: 222, 106: 222, 107: 500, 108: 222, 109: 833, 110: 556, 111: 556,
  112: 556, 113: 556, 114: 333, 115: 500, 116: 278, 117: 556, 118: 500,
  119: 722, 120: 500, 121: 500, 122: 500, 123: 334, 124: 260, 125: 334, 126: 584,
  176: 400, 216: 778, 223: 611, 228: 556, 246: 556, 252: 556,
  196: 667, 214: 778, 220: 722,
};
for (let d = 48; d < 58; d++) W[d] = 556;

export function textWidth(text, size) {
  let sum = 0;
  for (const ch of String(text)) sum += W[ch.codePointAt(0)] ?? 556;
  return sum / 1000 * size;
}

/** Text nach WinAnsi wandeln und PDF-Sonderzeichen schuetzen. */
function esc(text) {
  let out = "";
  for (const ch of String(text)) {
    let code = ch.codePointAt(0);
    if (code > 255) code = ({ 0x2300: 0xD8, 0x2205: 0xD8, 0x00B0: 0xB0 })[code] ?? 0x3F;
    if (code === 0x28 || code === 0x29 || code === 0x5C) out += "\\";
    out += String.fromCharCode(code);
  }
  return out;
}

/**
 * Zahl wie Pythons ``"%.Nf"`` formatieren.
 *
 * JavaScript wirft bei ``(-0).toFixed()`` das Vorzeichen weg, Python behaelt es.
 * Ohne diesen Ausgleich unterscheiden sich sonst identische Zeichnungen aus
 * Browser und Python-Kern -- der Vergleichstest wuerde dadurch blind.
 */
const fx = (v, n) => (Object.is(v, -0) ? "-" + (0).toFixed(n) : v.toFixed(n));

function hexToRgb(color) {
  let c = String(color || "#111111").replace("#", "");
  if (c.length === 3) c = c.split("").map((x) => x + x).join("");
  const v = [0, 2, 4].map((i) => parseInt(c.slice(i, i + 2), 16) / 255);
  return v.some(Number.isNaN) ? [0.07, 0.07, 0.07] : v;
}

class Content {
  constructor(scale) {
    this.s = scale;
    this.parts = [];
    this.state = {};
  }
  pt(p) { return [p[0] * this.s * MM_TO_PT, p[1] * this.s * MM_TO_PT]; }
  add(text) { this.parts.push(text); }

  strokeStyle(prim) {
    const color = hexToRgb(prim.color);
    const lw = Math.max(0.05, prim.lw ?? 0.25) * MM_TO_PT;
    const pattern = LINETYPES[prim.lt || "continuous"] || [];
    const key = `${color.join(",")}|${lw.toFixed(4)}|${pattern.join(",")}`;
    if (this.state.stroke === key) return;
    this.state.stroke = key;
    this.add(`${color.map((v) => fx(v, 3)).join(" ")} RG\n`);
    this.add(`${fx(lw, 3)} w\n`);
    this.add(pattern.length
      ? `[${pattern.map((v) => (v * MM_TO_PT).toFixed(3)).join(" ")}] 0 d\n`
      : "[] 0 d\n");
  }

  fillStyle(color) {
    const rgb = hexToRgb(color);
    const key = rgb.join(",");
    if (this.state.fill === key) return;
    this.state.fill = key;
    this.add(`${rgb.map((v) => fx(v, 3)).join(" ")} rg\n`);
  }

  path(pts, close, fill = false) {
    if (pts.length < 2) return;
    const first = this.pt(pts[0]);
    this.add(`${fx(first[0], 3)} ${fx(first[1], 3)} m\n`);
    for (const p of pts.slice(1)) {
      const s = this.pt(p);
      this.add(`${fx(s[0], 3)} ${fx(s[1], 3)} l\n`);
    }
    if (close) this.add("h\n");
    this.add(fill ? "f\n" : "S\n");
  }
}

function writePrim(c, prim) {
  switch (prim.k) {
    case "line":
      c.strokeStyle(prim); c.path([prim.a, prim.b], false); break;
    case "poly":
      c.strokeStyle(prim); c.path(prim.pts, !!prim.close); break;
    case "circle":
      c.strokeStyle(prim);
      c.path(G.flattenArc(prim.c, prim.r, 0, 360, 0.02, 24), true); break;
    case "arc":
      c.strokeStyle(prim);
      c.path(G.flattenArc(prim.c, prim.r, prim.start, prim.end, 0.02), false);
      break;
    case "fill":
      c.fillStyle(prim.color); c.path(prim.pts, true, true); break;
    case "text": {
      const size = prim.h * c.s * MM_TO_PT;
      if (size <= 0.1) return;
      c.fillStyle(prim.color);
      const width = textWidth(prim.text, size);
      const dx = { middle: -width / 2, end: -width }[prim.anchor] ?? 0;
      const dy = { middle: -size * 0.36, top: -size * 0.72 }[prim.valign] ?? 0;
      const [x, y] = c.pt(prim.p);
      const rot = (prim.rot || 0) * Math.PI / 180;
      const ca = Math.cos(rot), sa = Math.sin(rot);
      const tx = x + dx * ca - dy * sa;
      const ty = y + dx * sa + dy * ca;
      c.add(`BT\n/F1 ${fx(size, 3)} Tf\n`);
      c.add(`${fx(ca, 5)} ${fx(sa, 5)} ${fx(-sa, 5)} ${fx(ca, 5)} ` +
        `${fx(tx, 3)} ${fx(ty, 3)} Tm\n`);
      c.add(`(${esc(prim.text)}) Tj\n`);
      c.add("ET\n");
      break;
    }
  }
}

const bytesOf = (text) => {
  const out = new Uint8Array(text.length);
  for (let i = 0; i < text.length; i++) out[i] = text.charCodeAt(i) & 0xff;
  return out;
};

/** Zeichnung als PDF (Uint8Array). */
export function render(drawing, withSheet = true) {
  const scale = parseScale(drawing.meta.scale);
  const [pw, ph] = sheetSize(drawing.meta.sheet, drawing.meta.landscape);
  const c = new Content(scale);
  c.add(`1 1 1 rg\n0 0 ${(pw * MM_TO_PT).toFixed(3)} ${(ph * MM_TO_PT).toFixed(3)} re f\n`);
  c.add("1 J 1 j\n");

  const prims = [];
  if (withSheet) prims.push(...P.sheetPrimitives(drawing.meta));
  prims.push(...P.documentPrimitives(drawing, true));
  for (const prim of prims) writePrim(c, prim);

  const stream = c.parts.join("");
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${(pw * MM_TO_PT).toFixed(3)} ` +
      `${(ph * MM_TO_PT).toFixed(3)}] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>`,
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    `<< /Title (${esc(drawing.meta.title || "Zeichnung")}) /Creator (DARO-CAD) ` +
      "/Producer (DARO-CAD) >>",
  ];

  let out = "%PDF-1.4\n%\xe2\xe3\xcf\xd3\n";
  const offsets = [];
  objects.forEach((body, i) => {
    offsets.push(out.length);
    out += `${i + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xrefPos = out.length;
  const count = objects.length + 1;
  out += `xref\n0 ${count}\n0000000000 65535 f \n`;
  for (const off of offsets) out += `${String(off).padStart(10, "0")} 00000 n \n`;
  out += `trailer\n<< /Size ${count} /Root 1 0 R /Info ${objects.length} 0 R >>\n` +
    `startxref\n${xrefPos}\n%%EOF\n`;
  return bytesOf(out);
}
