// Ansichten aus Koerpern ableiten (Vorderansicht, Draufsicht, Seitenansicht).
// Uebertragung von daro_cad/views.py samt echter Verdeckt-Kanten-Ermittlung:
// jede Kante wird an den Umrissen der zum Betrachter zeigenden Flaechen zerlegt
// und in sichtbare und verdeckte Abschnitte getrennt (DIN ISO 128-24).
import * as G from "./geom.js";
import { SMOOTH_ANGLE, bbox3, circularFeatures, dot3 } from "./solid.js";

// Basis der Vorderansicht: der Betrachter blickt entlang -Z auf die XY-Ebene,
// sieht also genau die gezeichnete Kontur in wahrer Groesse.
const U0 = [1, 0, 0];
const V0 = [0, 1, 0];
const W0 = [0, 0, -1];          // Tiefenrichtung: vom Betrachter weg
const neg = (v) => [-v[0], -v[1], -v[2]];

export const VIEW_BASIS = {
  front: [U0, V0, W0],
  back: [neg(U0), V0, neg(W0)],
  top: [U0, W0, neg(V0)],        // Blick von oben
  bottom: [U0, neg(W0), V0],     // Blick von unten
  left: [neg(W0), V0, U0],       // Blick von links
  right: [W0, V0, neg(U0)],      // Blick von rechts
};

export const VIEW_LABELS = {
  front: "Vorderansicht", back: "Rückansicht", top: "Draufsicht",
  bottom: "Untersicht", left: "Ansicht von links", right: "Ansicht von rechts",
};

// Anordnung relativ zur Vorderansicht in Vielfachen von (Breite, Hoehe).
// Projektionsmethode 1 (Europa/DIN): Blick von links wird rechts angeordnet.
const PLACEMENT_FIRST = { front: [0, 0], left: [1, 0], right: [-1, 0],
  top: [0, -1], bottom: [0, 1], back: [2, 0] };
const PLACEMENT_THIRD = { front: [0, 0], left: [-1, 0], right: [1, 0],
  top: [0, 1], bottom: [0, -1], back: [-2, 0] };

const SILHOUETTE_EPS = 1e-9;

const toView = (p, u, v, w) => [dot3(p, u), dot3(p, v), dot3(p, w)];

function pointInFace(p, loops) {
  if (!loops.length || !G.pointInPolygon(p, loops[0])) return false;
  for (let i = 1; i < loops.length; i++) if (G.pointInPolygon(p, loops[i])) return false;
  return true;
}

/** Kanten aller Koerper in eine Ansicht projizieren. */
export function project(solids, view = "front", smoothAngle = SMOOTH_ANGLE) {
  const [u, v, w] = VIEW_BASIS[view] || VIEW_BASIS.front;
  const visible = [], hidden = [];

  // Alle Flaechen aller Koerper sammeln (Koerper verdecken sich gegenseitig)
  const faces = [];
  const allPts = [];
  for (const sol of solids) {
    const pts = sol.verts.map((p) => toView(p, u, v, w));
    allPts.push(pts);
    for (const face of sol.faces) {
      const n = face.normal;
      const nv = [dot3(n, u), dot3(n, v), dot3(n, w)];
      if (nv[2] >= -SILHOUETTE_EPS) continue;      // abgewandte Flaeche verdeckt nichts
      const loops = face.loops.map((loop) => loop.map((i) => [pts[i][0], pts[i][1]]));
      if (!loops.length || loops[0].length < 3) continue;
      const ref = pts[face.loops[0][0]];
      faces.push({
        loops, n: nv,
        c: nv[0] * ref[0] + nv[1] * ref[1] + nv[2] * ref[2],
        bbox: G.bbox(loops[0]),
      });
    }
  }

  let size = 1;
  const box = bbox3(solids);
  if (box) size = Math.max(1, box[3] - box[0], box[4] - box[1], box[5] - box[2]);
  const eps = size * 1e-6;

  solids.forEach((sol, si) => {
    const pts = allPts[si];
    for (const edge of sol.edges) {
      if (!edgeWanted(sol, edge, w, smoothAngle)) continue;
      const a = pts[edge.a], b = pts[edge.b];
      for (const [seg, isVisible] of splitEdge(a, b, faces, eps)) {
        (isVisible ? visible : hidden).push(seg);
      }
    }
  });

  return resolve(visible, hidden);
}

/** Weiche Kanten (Zylindertessellierung) nur als Silhouette zeichnen. */
function edgeWanted(sol, edge, w, smoothAngle) {
  const f = edge.faces || [];
  if (f.length < 2) return true;
  const n1 = sol.faces[f[0]].normal, n2 = sol.faces[f[1]].normal;
  const cosA = Math.max(-1, Math.min(1, dot3(n1, n2)));
  if (Math.acos(cosA) * 180 / Math.PI > smoothAngle) return true;
  return (dot3(n1, w) < 0) !== (dot3(n2, w) < 0);      // Silhouettenkante
}

/** Kante an allen Flaechenumrissen zerlegen und Sichtbarkeit bestimmen. */
function splitEdge(a, b, faces, eps) {
  const a2 = [a[0], a[1]], b2 = [b[0], b[1]];
  if (G.dist(a2, b2) < 1e-9) return [];
  const params = new Set([0, 1]);
  const dvec = G.sub(b2, a2);
  const dlen2 = G.dot(dvec, dvec);

  for (const face of faces) {
    const fb = face.bbox;
    if (fb && (Math.max(a2[0], b2[0]) < fb[0] - eps || Math.min(a2[0], b2[0]) > fb[2] + eps ||
               Math.max(a2[1], b2[1]) < fb[1] - eps || Math.min(a2[1], b2[1]) > fb[3] + eps)) continue;
    for (const loop of face.loops) {
      for (let i = 0; i < loop.length; i++) {
        const hit = G.lineLine(a2, b2, loop[i], loop[(i + 1) % loop.length]);
        if (!hit) continue;
        const t = G.dot(G.sub(hit, a2), dvec) / dlen2;
        if (t > 1e-9 && t < 1 - 1e-9) params.add(t);
      }
    }
  }

  const ordered = [...params].sort((x, y) => x - y);
  const out = [];
  for (let i = 0; i < ordered.length - 1; i++) {
    const t0 = ordered[i], t1 = ordered[i + 1];
    if (t1 - t0 < 1e-9) continue;
    const tm = (t0 + t1) / 2;
    const pm = G.lerp(a2, b2, tm);
    const depth = a[2] + (b[2] - a[2]) * tm;
    let vis = true;
    for (const face of faces) {
      const nz = face.n[2];
      if (Math.abs(nz) < 1e-12) continue;
      if (!pointInFace(pm, face.loops)) continue;
      const fd = (face.c - face.n[0] * pm[0] - face.n[1] * pm[1]) / nz;
      if (fd < depth - eps) { vis = false; break; }
    }
    out.push([[G.lerp(a2, b2, t0), G.lerp(a2, b2, t1)], vis]);
  }
  return out;
}

// -- Doppelte Kanten entfernen, verdeckte weichen sichtbaren -----------------

function lineKey(a, b) {
  let d = G.normalize(G.sub(b, a));
  if (d[0] < -1e-9 || (Math.abs(d[0]) <= 1e-9 && d[1] < 0)) d = [-d[0], -d[1]];
  const off = G.cross(d, a);
  return { d, key: `${d[0].toFixed(7)}|${d[1].toFixed(7)}|${off.toFixed(4)}` };
}

function group(segments) {
  const groups = new Map();
  for (const [a, b] of segments) {
    if (G.dist(a, b) < 1e-9) continue;
    const { d, key } = lineKey(a, b);
    const ta = G.dot(a, d), tb = G.dot(b, d);
    let rec = groups.get(key);
    if (!rec) { rec = { d, base: G.sub(a, G.mul(d, ta)), iv: [] }; groups.set(key, rec); }
    rec.iv.push([Math.min(ta, tb), Math.max(ta, tb)]);
  }
  return groups;
}

function mergeIntervals(iv, tol = 1e-7) {
  const out = [];
  for (const [lo, hi] of iv.slice().sort((x, y) => x[0] - y[0])) {
    if (out.length && lo <= out[out.length - 1][1] + tol) {
      out[out.length - 1][1] = Math.max(out[out.length - 1][1], hi);
    } else out.push([lo, hi]);
  }
  return out.filter(([lo, hi]) => hi - lo > tol);
}

function subtractIntervals(iv, cuts, tol = 1e-7) {
  let out = iv.slice();
  for (const [clo, chi] of cuts) {
    const next = [];
    for (const [lo, hi] of out) {
      if (chi <= lo + tol || clo >= hi - tol) { next.push([lo, hi]); continue; }
      if (clo > lo + tol) next.push([lo, Math.min(hi, clo)]);
      if (chi < hi - tol) next.push([Math.max(lo, chi), hi]);
    }
    out = next;
  }
  return out.filter(([lo, hi]) => hi - lo > tol);
}

function emit(groups) {
  const out = [];
  for (const rec of groups.values()) {
    for (const [lo, hi] of rec.iv) {
      out.push([G.add(rec.base, G.mul(rec.d, lo)), G.add(rec.base, G.mul(rec.d, hi))]);
    }
  }
  return out;
}

function resolve(visible, hidden) {
  const vis = group(visible);
  const hid = group(hidden);
  for (const rec of vis.values()) rec.iv = mergeIntervals(rec.iv);
  for (const [key, rec] of hid) {
    rec.iv = mergeIntervals(rec.iv);
    if (vis.has(key)) rec.iv = subtractIntervals(rec.iv, vis.get(key).iv);
  }
  return { visible: emit(vis), hidden: emit(hid) };
}

// ---------------------------------------------------------------------------
// Ansichten auf dem Blatt anordnen
// ---------------------------------------------------------------------------

export function derive(solids, views = ["front", "top", "left"], opts = {}) {
  if (!solids.length) return [];
  const origin = opts.origin || [0, 0];
  const gap = opts.gap ?? 25;
  const placement = (opts.projection || "first") === "first" ? PLACEMENT_FIRST : PLACEMENT_THIRD;
  const labels = opts.labels !== false;
  const centerLines = opts.centerLines !== false;
  const labelHeight = opts.labelHeight ?? 5;

  const results = new Map();
  for (const name of views) {
    const data = project(solids, name);
    const pts = [...data.visible, ...data.hidden].flat();
    results.set(name, { data, bbox: G.bbox(pts) || [0, 0, 0, 0] });
  }

  const ref = results.get("front") || results.values().next().value;
  const refW = ref.bbox[2] - ref.bbox[0];
  const refH = ref.bbox[3] - ref.bbox[1];

  const entities = [];
  for (const [name, info] of results) {
    const [col, row] = placement[name] || [0, 0];
    const box = info.bbox;
    const vw = box[2] - box[0], vh = box[3] - box[1];

    // Ansichten fluchten: gleiche Hoehe in einer Zeile, gleiche Breite in einer Spalte
    let ox;
    if (col > 0) ox = origin[0] + refW / 2 + gap + vw / 2 + (col - 1) * (vw + gap);
    else if (col < 0) ox = origin[0] - refW / 2 - gap - vw / 2 + (col + 1) * (vw + gap);
    else ox = origin[0];
    let oy;
    if (row > 0) oy = origin[1] + refH / 2 + gap + vh / 2 + (row - 1) * (vh + gap);
    else if (row < 0) oy = origin[1] - refH / 2 - gap - vh / 2 + (row + 1) * (vh + gap);
    else oy = origin[1];

    const dx = ox - (box[0] + box[2]) / 2;
    const dy = oy - (box[1] + box[3]) / 2;
    const shift = (p) => [p[0] + dx, p[1] + dy];

    for (const [layer, key] of [["Kontur", "visible"], ["Verdeckt", "hidden"]]) {
      for (const [a, b] of info.data[key]) {
        entities.push({ type: "line", a: shift(a), b: shift(b), layer, view: name });
      }
    }
    if (centerLines) entities.push(...centerLinesFor(solids, name, shift));
    if (labels) {
      entities.push({ type: "text", p: [ox, oy - vh / 2 - labelHeight * 1.8],
        h: labelHeight, text: VIEW_LABELS[name] || name, align: "center",
        layer: "Text", view: name });
    }
  }
  return entities;
}

/** Mittellinien fuer runde Bohrungen ergaenzen. */
function centerLinesFor(solids, view, shift) {
  const [u, v, w] = VIEW_BASIS[view] || VIEW_BASIS.front;
  const out = [];
  for (const sol of solids) {
    const prof = sol.profile || {};
    const z0 = sol.z0 ?? 0, z1 = sol.z1 ?? 0;
    for (const feat of circularFeatures(prof)) {
      const [cx, cy] = feat.center;
      const r = feat.r;
      const pLow = toView([cx, cy, z0], u, v, w);
      const pHigh = toView([cx, cy, z1], u, v, w);
      const axis = G.sub([pHigh[0], pHigh[1]], [pLow[0], pLow[1]]);
      const over = r * 0.25 + 2;
      if (G.len(axis) < 1e-6) {
        // Achse zeigt zum Betrachter -> Mittenkreuz
        const c = shift([pLow[0], pLow[1]]);
        out.push({ type: "line", a: [c[0] - r - over, c[1]], b: [c[0] + r + over, c[1]],
          layer: "Mittellinie", view });
        out.push({ type: "line", a: [c[0], c[1] - r - over], b: [c[0], c[1] + r + over],
          layer: "Mittellinie", view });
      } else {
        const d = G.normalize(axis);
        out.push({ type: "line",
          a: shift(G.sub([pLow[0], pLow[1]], G.mul(d, over))),
          b: shift(G.add([pHigh[0], pHigh[1]], G.mul(d, over))),
          layer: "Mittellinie", view });
      }
    }
  }
  return out;
}
