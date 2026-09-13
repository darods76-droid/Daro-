// DXF einlesen -- Gegenstueck zu daro_cad/dxf.py (load).
// Versteht R12 (POLYLINE/VERTEX) ebenso wie neuere Dateien (LWPOLYLINE, ELLIPSE).
import * as G from "./geom.js";
import { DEFAULT_LAYERS, WIDE, NARROW, newId } from "./doc.js";

const ACI_RGB = {
  1: [255, 0, 0], 2: [255, 255, 0], 3: [0, 255, 0], 4: [0, 255, 255],
  5: [0, 0, 255], 6: [255, 0, 255], 7: [0, 0, 0], 8: [128, 128, 128],
  9: [192, 192, 192], 30: [255, 127, 0], 40: [255, 191, 0],
  130: [127, 0, 255], 230: [255, 0, 127], 250: [51, 51, 51], 253: [153, 153, 153],
};

const LT_REVERSE = { CONTINUOUS: "continuous", DASHED: "dashed", DOTTED: "dotted",
  CENTER: "center", PHANTOM: "phantom" };

function pairs(text) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  for (let i = 0; i + 1 < lines.length; i += 2) {
    const raw = lines[i].trim();
    if (!raw) continue;
    const code = Number.parseInt(raw, 10);
    if (Number.isNaN(code)) continue;
    out.push([code, lines[i + 1]]);
  }
  return out;
}

const num = (v, d = 0) => {
  const n = Number.parseFloat(v);
  return Number.isFinite(n) ? n : d;
};

/** Gruppencodes eines Blocks als {code: [werte]} */
function tagmap(tags) {
  const map = new Map();
  for (const [code, value] of tags) {
    if (!map.has(code)) map.set(code, []);
    map.get(code).push(value);
  }
  return map;
}

const get = (tm, code, dflt = 0, index = 0) => {
  const values = tm.get(code);
  return values && index < values.length ? num(values[index], dflt) : dflt;
};

const str = (tm, code, dflt = "") => {
  const values = tm.get(code);
  return values && values.length ? values[0] : dflt;
};

function buildEntity(kind, tags, vertices) {
  const tm = tagmap(tags);
  const layer = str(tm, 8, "0").trim();
  const ltRaw = str(tm, 6, "CONTINUOUS").trim().toUpperCase();
  const lt = LT_REVERSE[ltRaw];

  const base = (ent) => {
    ent.layer = layer;
    ent.id = newId();
    if (lt && lt !== "continuous") ent.linetype = lt;
    return ent;
  };

  switch (kind) {
    case "LINE":
      return base({ type: "line", a: [get(tm, 10), get(tm, 20)], b: [get(tm, 11), get(tm, 21)] });
    case "CIRCLE":
      return base({ type: "circle", c: [get(tm, 10), get(tm, 20)], r: get(tm, 40, 1) });
    case "ARC":
      return base({ type: "arc", c: [get(tm, 10), get(tm, 20)], r: get(tm, 40, 1),
        start: get(tm, 50), end: get(tm, 51, 90) });
    case "LWPOLYLINE": {
      const xs = (tm.get(10) || []).map((v) => num(v));
      const ys = (tm.get(20) || []).map((v) => num(v));
      const pts = xs.map((x, i) => [x, ys[i] ?? 0]);
      if (pts.length < 2) return null;
      let bulges = (tm.get(42) || []).map((v) => num(v));
      if (bulges.length && bulges.length !== pts.length) bulges = [];
      return base({ type: "polyline", pts, closed: !!(get(tm, 70) & 1), bulges });
    }
    case "POLYLINE": {
      const pts = [], bulges = [];
      for (const v of vertices) {
        const vt = tagmap(v);
        pts.push([get(vt, 10), get(vt, 20)]);
        bulges.push(get(vt, 42));
      }
      if (pts.length < 2) return null;
      const ent = base({ type: "polyline", pts, closed: !!(get(tm, 70) & 1) });
      if (bulges.some((b) => Math.abs(b) > 1e-12)) ent.bulges = bulges;
      return ent;
    }
    case "TEXT":
    case "MTEXT": {
      let value = str(tm, 1, "");
      if (kind === "MTEXT") {
        value = value.replace(/\\P/g, " ").replace(/\\A[01];|[{}]/g, "");
      }
      const align = Math.round(get(tm, 72));
      let px = get(tm, 10), py = get(tm, 20);
      if (align && tm.has(11)) { px = get(tm, 11); py = get(tm, 21); }
      return base({ type: "text", p: [px, py], h: get(tm, 40, 3.5) || 3.5, text: value,
        rot: get(tm, 50), align: { 0: "left", 1: "center", 2: "right" }[align] || "left" });
    }
    case "POINT":
      return base({ type: "point", p: [get(tm, 10), get(tm, 20)] });
    case "ELLIPSE": {
      // Als Polylinie annaehern -- ausreichend fuer den Import
      const c = [get(tm, 10), get(tm, 20)];
      const major = [get(tm, 11), get(tm, 21)];
      const ratio = get(tm, 40, 1);
      const start = get(tm, 41, 0), end = get(tm, 42, 2 * Math.PI);
      const a = G.len(major), b = a * ratio;
      const rot = G.angleOf(major);
      const pts = [];
      const steps = 64;
      for (let i = 0; i <= steps; i++) {
        const t = start + (end - start) * i / steps;
        pts.push(G.add(c, G.rotate([a * Math.cos(t), b * Math.sin(t)], rot)));
      }
      return base({ type: "polyline", pts,
        closed: Math.abs(end - start) >= 2 * Math.PI - 1e-6 });
    }
    default:
      return null;
  }
}

/** DXF-Text in ein Zeichnungsobjekt (wie Drawing.load erwartet) wandeln. */
export function parse(text) {
  const all = pairs(text);
  const entities = [];
  const layers = new Map();

  let section = "";
  let table = "";
  let kind = "";
  let tags = [];
  let vertices = [];
  let vertexTags = null;
  let layerTags = null;

  const flush = () => {
    if (!kind) return;
    if (vertexTags) { vertices.push(vertexTags); vertexTags = null; }
    const ent = buildEntity(kind, tags, vertices);
    if (ent) entities.push(ent);
    kind = ""; tags = []; vertices = [];
  };

  const flushLayer = () => {
    if (!layerTags) return;
    const tm = tagmap(layerTags);
    const name = str(tm, 2, "").trim();
    if (name) {
      layers.set(name, { name, color: Math.round(get(tm, 62, 7)),
        linetype: str(tm, 6, "CONTINUOUS").trim().toUpperCase() });
    }
    layerTags = null;
  };

  for (const [code, value] of all) {
    if (code === 0) {
      const name = value.trim().toUpperCase();
      if (name === "SECTION") { flush(); flushLayer(); section = "?"; continue; }
      if (name === "ENDSEC") { flush(); flushLayer(); section = ""; table = ""; continue; }
      if (name === "EOF") { flush(); flushLayer(); break; }
      if (name === "TABLE") { flushLayer(); table = "?"; continue; }
      if (name === "ENDTAB") { flushLayer(); table = ""; continue; }

      if (section === "TABLES") {
        if (name === "LAYER") { flushLayer(); layerTags = []; }
        else flushLayer();
        continue;
      }
      if (section !== "ENTITIES") continue;

      if (name === "VERTEX") {
        if (vertexTags) vertices.push(vertexTags);
        vertexTags = [];
        continue;
      }
      if (name === "SEQEND") {
        if (vertexTags) { vertices.push(vertexTags); vertexTags = null; }
        continue;
      }
      flush();
      kind = name;
      continue;
    }

    // Abschnitts- bzw. Tabellenname steht als Code 2 direkt hinter SECTION/TABLE
    if (code === 2 && section === "?") { section = value.trim().toUpperCase(); continue; }
    if (code === 2 && table === "?" && !layerTags) { table = value.trim().toUpperCase(); continue; }

    if (layerTags) { layerTags.push([code, value]); continue; }
    if (vertexTags) { vertexTags.push([code, value]); continue; }
    if (kind) tags.push([code, value]);
  }
  flush();
  flushLayer();

  // Layer uebernehmen, sonst die Voreinstellung
  let docLayers;
  if (layers.size) {
    docLayers = [...layers.values()].map((info) => {
      const aci = Math.abs(info.color);
      const rgb = ACI_RGB[aci] || [17, 17, 17];
      return {
        name: info.name,
        color: "#" + rgb.map((v) => v.toString(16).padStart(2, "0")).join(""),
        linetype: LT_REVERSE[info.linetype] || "continuous",
        lineweight: info.name.toLowerCase().includes("kontur") ? WIDE : NARROW,
        visible: info.color >= 0,
        locked: false,
        printable: true,
      };
    });
  } else {
    docLayers = DEFAULT_LAYERS.map((l) => ({ visible: true, locked: false, printable: true, ...l }));
  }

  const known = new Set(docLayers.map((l) => l.name));
  for (const e of entities) if (!known.has(e.layer)) e.layer = docLayers[0].name;

  return { version: 1, meta: {}, layers: docLayers, entities, solids: [] };
}
