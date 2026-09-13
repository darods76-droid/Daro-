// SVG-Export im Browser -- Uebertragung von daro_cad/svg_export.py.
// Das Ergebnis hat exakt die Blattgroesse in Millimetern.
import * as G from "./geom.js";
import * as P from "./prims.js";
import { LINETYPES, parseScale, sheetSize } from "./doc.js";

const FONT = "ISOCPEUR, 'Arial Narrow', Helvetica, Arial, sans-serif";

const fmt = (v) => {
  const s = v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  return s === "" || s === "-0" ? "0" : s;
};

const escape = (t) => String(t ?? "")
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;");

function styleOf(prim) {
  const lw = Math.max(0.05, prim.lw ?? 0.25);
  const parts = [`stroke="${prim.color || "#111"}"`, `stroke-width="${fmt(lw)}"`,
    'fill="none"', 'stroke-linecap="butt"', 'stroke-linejoin="round"'];
  const pattern = LINETYPES[prim.lt || "continuous"] || [];
  if (pattern.length) parts.push(`stroke-dasharray="${pattern.map(fmt).join(" ")}"`);
  return parts.join(" ");
}

function primToSvg(prim, m) {
  const style = styleOf(prim);
  switch (prim.k) {
    case "line": {
      const a = m(prim.a), b = m(prim.b);
      return `<line x1="${fmt(a[0])}" y1="${fmt(a[1])}" x2="${fmt(b[0])}" y2="${fmt(b[1])}" ${style}/>`;
    }
    case "poly": {
      const pts = prim.pts.map(m).map((p) => `${fmt(p[0])},${fmt(p[1])}`).join(" ");
      return `<${prim.close ? "polygon" : "polyline"} points="${pts}" ${style}/>`;
    }
    case "circle": {
      const c = m(prim.c);
      return `<circle cx="${fmt(c[0])}" cy="${fmt(c[1])}" r="${fmt(m.len(prim.r))}" ${style}/>`;
    }
    case "arc": {
      const sweep = G.arcSweep(prim.start, prim.end);
      const a = m(G.arcPoint(prim.c, prim.r, prim.start));
      const b = m(G.arcPoint(prim.c, prim.r, prim.end));
      const rr = m.len(prim.r);
      const large = sweep > 180 ? 1 : 0;
      // Die Y-Spiegelung dreht den Umlaufsinn: CCW im Modell -> sweep-flag 1 im SVG.
      return `<path d="M ${fmt(a[0])} ${fmt(a[1])} A ${fmt(rr)} ${fmt(rr)} 0 ${large} 1 ` +
        `${fmt(b[0])} ${fmt(b[1])}" ${style}/>`;
    }
    case "fill": {
      const pts = prim.pts.map(m).map((p) => `${fmt(p[0])},${fmt(p[1])}`).join(" ");
      return `<polygon points="${pts}" fill="${prim.color || "#111"}" stroke="none"/>`;
    }
    case "text": {
      const p = m(prim.p);
      const size = m.len(prim.h);
      const rot = -(prim.rot || 0);          // SVG dreht im Uhrzeigersinn
      const transform = Math.abs(rot) > 1e-6
        ? ` transform="rotate(${fmt(rot)} ${fmt(p[0])} ${fmt(p[1])})"` : "";
      const baseline = { base: "alphabetic", middle: "central", top: "hanging" }[
        prim.valign || "base"] || "alphabetic";
      return `<text x="${fmt(p[0])}" y="${fmt(p[1])}" font-family="${FONT}" ` +
        `font-size="${fmt(size)}" fill="${prim.color || "#111"}" ` +
        `text-anchor="${prim.anchor || "start"}" dominant-baseline="${baseline}"` +
        `${transform}>${escape(prim.text)}</text>`;
    }
    default:
      return "";
  }
}

/** Zeichnung als SVG-Text. */
export function render(drawing, withSheet = true, background = "#ffffff") {
  const scale = parseScale(drawing.meta.scale);
  const [pw, ph] = sheetSize(drawing.meta.sheet, drawing.meta.landscape);
  const m = (p) => [p[0] * scale, ph - p[1] * scale];
  m.len = (v) => v * scale;

  const prims = [];
  if (withSheet) prims.push(...P.sheetPrimitives(drawing.meta));
  prims.push(...P.documentPrimitives(drawing, true));

  const body = prims.map((p) => primToSvg(p, m)).filter(Boolean).join("\n");
  const bg = background
    ? `<rect x="0" y="0" width="${fmt(pw)}" height="${fmt(ph)}" fill="${background}"/>` : "";

  return '<?xml version="1.0" encoding="UTF-8"?>\n' +
    `<svg xmlns="http://www.w3.org/2000/svg" version="1.1" ` +
    `width="${fmt(pw)}mm" height="${fmt(ph)}mm" viewBox="0 0 ${fmt(pw)} ${fmt(ph)}">\n` +
    `<title>${escape(drawing.meta.title || "Zeichnung")}</title>\n${bg}\n${body}\n</svg>\n`;
}
