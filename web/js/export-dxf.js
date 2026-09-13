// DXF-Export im Browser (AutoCAD R12 ASCII) -- Uebertragung von daro_cad/dxf.py.
// R12 lesen FreeCAD, LibreCAD, QCAD, AutoCAD und Inkscape zuverlaessig.
import * as P from "./prims.js";
import { polylineSegments, parseScale, ellipsePoints } from "./doc.js";

// AutoCAD Color Index -> RGB (nur die gebraeuchlichen Farben).
const ACI_RGB = {
  1: [255, 0, 0], 2: [255, 255, 0], 3: [0, 255, 0], 4: [0, 255, 255],
  5: [0, 0, 255], 6: [255, 0, 255], 7: [0, 0, 0], 8: [128, 128, 128],
  9: [192, 192, 192], 30: [255, 127, 0], 40: [255, 191, 0],
  130: [127, 0, 255], 230: [255, 0, 127], 250: [51, 51, 51], 253: [153, 153, 153],
};

const DXF_LTYPES = {
  CONTINUOUS: ["Durchgezogen", []],
  DASHED: ["Strichlinie ___ ___ ___", [4, -2]],
  DOTTED: ["Punktlinie . . . . .", [0, -1.6]],
  CENTER: ["Strichpunktlinie ____ _ ____", [12, -2, 0.5, -2]],
  PHANTOM: ["Strichzweipunkt ___ _ _ ___", [12, -2, 0.5, -2, 0.5, -2]],
};

const LT_NAME = { continuous: "CONTINUOUS", dashed: "DASHED", dotted: "DOTTED",
  center: "CENTER", phantom: "PHANTOM" };

export function hexToAci(color) {
  const c = String(color || "").replace("#", "");
  const rgb = [parseInt(c.slice(0, 2), 16), parseInt(c.slice(2, 4), 16), parseInt(c.slice(4, 6), 16)];
  if (rgb.some(Number.isNaN)) return 7;
  let best = 7, bestD = Infinity;
  for (const [idx, ref] of Object.entries(ACI_RGB)) {
    const d = rgb.reduce((s, v, i) => s + (v - ref[i]) ** 2, 0);
    if (d < bestD) { bestD = d; best = Number(idx); }
  }
  return best;
}

class Writer {
  constructor() { this.parts = []; }

  /**
   * Ein Gruppenpaar schreiben.
   *
   * JavaScript kennt keinen Unterschied zwischen 1 und 1.0, deshalb entscheidet
   * der Gruppencode ueber die Schreibweise -- so wie es die DXF-Spezifikation
   * ohnehin festlegt: 10-59 sind Gleitkommazahlen, 60-79 ganze Zahlen, der Rest
   * Text. Dadurch entstehen dieselben Dateien wie im Python-Kern.
   */
  tag(code, value) {
    let text;
    if (typeof value === "number" && code >= 10 && code <= 59) text = value.toFixed(6);
    else if (typeof value === "number" && code >= 60 && code <= 79) text = String(Math.round(value));
    else text = String(value);
    this.parts.push(`${code}\n${text}\n`);
  }
  tags(pairs) { for (const [c, v] of pairs) this.tag(c, v); }
  text() { return this.parts.join(""); }
}

const ALIGN_CODE = { left: 0, center: 1, right: 2, start: 0, middle: 1, end: 2 };

function common(w, layer, lt) {
  w.tag(8, layer || "0");
  if (lt) w.tag(6, LT_NAME[lt] || "CONTINUOUS");
}

function writePolyline(w, layer, pts, bulges, closed, lt) {
  if (pts.length < 2) return;
  w.tag(0, "POLYLINE"); common(w, layer, lt);
  w.tags([[66, 1], [10, 0.0], [20, 0.0], [30, 0.0], [70, closed ? 1 : 0]]);
  pts.forEach((p, i) => {
    w.tag(0, "VERTEX"); w.tag(8, layer || "0");
    w.tags([[10, Number(p[0])], [20, Number(p[1])], [30, 0.0]]);
    if (bulges && Math.abs(bulges[i] || 0) > 1e-12) w.tag(42, Number(bulges[i]));
  });
  w.tag(0, "SEQEND"); w.tag(8, layer || "0");
}

function writeText(w, layer, p, h, textValue, rot = 0, align = "left") {
  const code = ALIGN_CODE[align] ?? 0;
  w.tag(0, "TEXT"); common(w, layer);
  w.tags([[10, Number(p[0])], [20, Number(p[1])], [30, 0.0], [40, Number(h)]]);
  w.tag(1, textValue);
  w.tags([[50, Number(rot)], [7, "STANDARD"], [72, code]]);
  if (code) w.tags([[11, Number(p[0])], [21, Number(p[1])], [31, 0.0]]);
}

/** Gefuelltes Dreieck/Viereck (Bemassungspfeil). */
function writeSolid(w, layer, pts) {
  const q = pts.slice(0, 4);
  while (q.length < 4) q.push(q[q.length - 1]);
  // DXF-SOLID erwartet die Punkte in Z-Reihenfolge, nicht umlaufend
  const order = [q[0], q[1], q[3], q[2]];
  w.tag(0, "SOLID"); common(w, layer);
  order.forEach((p, i) => {
    w.tags([[10 + i, Number(p[0])], [20 + i, Number(p[1])], [30 + i, 0.0]]);
  });
}

function writePrimitive(w, layer, prim) {
  const lt = prim.lt || "continuous";
  switch (prim.k) {
    case "line":
      w.tag(0, "LINE"); common(w, layer, lt);
      w.tags([[10, Number(prim.a[0])], [20, Number(prim.a[1])], [30, 0.0],
        [11, Number(prim.b[0])], [21, Number(prim.b[1])], [31, 0.0]]);
      break;
    case "poly":
      writePolyline(w, layer, prim.pts, null, !!prim.close, lt);
      break;
    case "circle":
      w.tag(0, "CIRCLE"); common(w, layer, lt);
      w.tags([[10, Number(prim.c[0])], [20, Number(prim.c[1])], [30, 0.0], [40, Number(prim.r)]]);
      break;
    case "arc":
      w.tag(0, "ARC"); common(w, layer, lt);
      w.tags([[10, Number(prim.c[0])], [20, Number(prim.c[1])], [30, 0.0], [40, Number(prim.r)],
        [50, Number(prim.start)], [51, Number(prim.end)]]);
      break;
    case "fill":
      writeSolid(w, layer, prim.pts);
      break;
    case "text":
      writeText(w, layer, prim.p, prim.h, prim.text, prim.rot || 0, prim.anchor || "start");
      break;
  }
}

function writeEntity(w, drawing, e) {
  const layer = e.layer || "0";
  const lt = e.linetype;
  switch (e.type) {
    case "line":
      w.tag(0, "LINE"); common(w, layer, lt);
      w.tags([[10, Number(e.a[0])], [20, Number(e.a[1])], [30, 0.0],
        [11, Number(e.b[0])], [21, Number(e.b[1])], [31, 0.0]]);
      break;
    case "circle":
      w.tag(0, "CIRCLE"); common(w, layer, lt);
      w.tags([[10, Number(e.c[0])], [20, Number(e.c[1])], [30, 0.0], [40, Number(e.r)]]);
      break;
    case "arc":
      w.tag(0, "ARC"); common(w, layer, lt);
      w.tags([[10, Number(e.c[0])], [20, Number(e.c[1])], [30, 0.0], [40, Number(e.r)],
        [50, Number(e.start)], [51, Number(e.end)]]);
      break;
    case "polyline":
      writePolyline(w, layer, e.pts, e.bulges, !!e.closed, lt);
      break;
    case "text":
      writeText(w, layer, e.p, e.h, e.text, e.rot || 0, e.align || "left");
      break;
    case "point":
      w.tag(0, "POINT"); common(w, layer);
      w.tags([[10, Number(e.p[0])], [20, Number(e.p[1])], [30, 0.0]]);
      break;
    case "ellipse": {
      // R12 kennt keine ELLIPSE -- als Polylinie schreiben, wie bei Schraffuren
      const pts = ellipsePoints(e);
      const closed = Math.abs((e.end ?? 360) - (e.start ?? 0)) >= 359.999;
      writePolyline(w, layer, closed ? pts.slice(0, -1) : pts, null, closed, lt);
      break;
    }
    case "leader":
    case "surface":
    case "fcf":
    case "hatch":
    case "dim":
      // In Einzelelemente aufgeloest, damit es ueberall gleich aussieht
      for (const prim of P.entityPrimitives(drawing, e)) writePrimitive(w, layer, prim);
      break;
    case "insert":
      // R12-INSERT waere kuerzer, aber aufgeloest sieht der Block in jedem
      // Zielprogramm gleich aus -- dieselbe Linie wie bei der Bemassung.
      for (const sub of drawing.resolveInsert(e)) {
        const lay = drawing.layer(sub.layer);
        if (!lay || !lay.visible || lay.printable === false) continue;
        writeEntity(w, drawing, sub);
      }
      break;
  }
}

/** Zeichnung als DXF-R12-Text. */
export function render(drawing, withSheet = true) {
  const w = new Writer();
  const box = drawing.bbox() || [0, 0, 100, 100];
  const scale = parseScale(drawing.meta.scale);

  // ---- HEADER -------------------------------------------------------
  w.tags([[0, "SECTION"], [2, "HEADER"]]);
  w.tags([[9, "$ACADVER"], [1, "AC1009"]]);
  w.tags([[9, "$INSUNITS"], [70, 4]]);                 // 4 = Millimeter
  w.tags([[9, "$DWGCODEPAGE"], [3, "ANSI_1252"]]);
  w.tags([[9, "$EXTMIN"], [10, box[0]], [20, box[1]], [30, 0.0]]);
  w.tags([[9, "$EXTMAX"], [10, box[2]], [20, box[3]], [30, 0.0]]);
  w.tags([[9, "$LTSCALE"], [40, 1 / Math.max(1e-6, scale)]]);
  w.tags([[9, "$TEXTSTYLE"], [7, "STANDARD"]]);
  w.tag(0, "ENDSEC");

  // ---- TABLES -------------------------------------------------------
  w.tags([[0, "SECTION"], [2, "TABLES"]]);

  const ltypeNames = Object.keys(DXF_LTYPES);
  w.tags([[0, "TABLE"], [2, "LTYPE"], [70, ltypeNames.length]]);
  for (const name of ltypeNames) {
    const [descr, pattern] = DXF_LTYPES[name];
    const total = pattern.reduce((s, v) => s + Math.abs(v), 0);
    w.tags([[0, "LTYPE"], [2, name], [70, 0], [3, descr], [72, 65],
      [73, pattern.length], [40, total]]);
    for (const v of pattern) w.tag(49, v);
  }
  w.tag(0, "ENDTAB");

  const sheetLayer = { name: "Rahmen", color: "#111111", linetype: "continuous", visible: true };
  const tableLayers = withSheet ? [...drawing.layers, sheetLayer] : drawing.layers;
  w.tags([[0, "TABLE"], [2, "LAYER"], [70, tableLayers.length]]);
  for (const lay of tableLayers) {
    const aci = hexToAci(lay.color);
    w.tags([[0, "LAYER"], [2, lay.name], [70, lay.visible === false ? 1 : 0],
      [62, lay.visible === false ? -aci : aci],
      [6, LT_NAME[lay.linetype] || "CONTINUOUS"]]);
  }
  w.tag(0, "ENDTAB");

  w.tags([[0, "TABLE"], [2, "STYLE"], [70, 1]]);
  w.tags([[0, "STYLE"], [2, "STANDARD"], [70, 0], [40, 0.0], [41, 0.85], [50, 0.0],
    [71, 0], [42, 3.5], [3, "isocp.shx"], [4, ""]]);
  w.tag(0, "ENDTAB");
  w.tag(0, "ENDSEC");

  // ---- ENTITIES -----------------------------------------------------
  w.tags([[0, "SECTION"], [2, "ENTITIES"]]);
  for (const e of drawing.entities) {
    const lay = drawing.layer(e.layer);
    if (!lay || !lay.visible || lay.printable === false) continue;
    writeEntity(w, drawing, e);
  }
  if (withSheet) {
    for (const prim of P.sheetPrimitives(drawing.meta)) writePrimitive(w, "Rahmen", prim);
  }
  w.tag(0, "ENDSEC");
  w.tag(0, "EOF");
  return w.text();
}
