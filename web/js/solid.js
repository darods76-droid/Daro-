// Extrusion von 2D-Profilen zu Koerpern.
// Uebertragung von daro_cad/solid.py -- gleiche Datenstruktur, gleiche Ergebnisse,
// damit die eigenstaendige HTML-Fassung rechnet wie der Python-Kern.
import * as G from "./geom.js";
import { outlinePoints } from "./doc.js";

// Kanten zwischen fast parallelen Flaechen (Tessellierung eines Zylinders)
// gelten als "weich" und werden nur als Silhouette gezeichnet.
export const SMOOTH_ANGLE = 20;

export const sub3 = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const dot3 = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross3 = (a, b) => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];

export function norm3(a) {
  const n = Math.sqrt(dot3(a, a));
  return n < 1e-12 ? [0, 0, 0] : [a[0] / n, a[1] / n, a[2] / n];
}

// ---------------------------------------------------------------------------
// Konturen aus Zeichnungselementen bilden
// ---------------------------------------------------------------------------

export function buildLoops(entities, tol = 0.05) {
  const chains = [];
  const loops = [];

  for (const e of entities) {
    const t = e.type;
    if (t === "circle" || (t === "polyline" && e.closed)) {
      loops.push(outlinePoints(e));
      continue;
    }
    if (t === "line" || t === "arc" || t === "polyline") {
      const pts = outlinePoints(e);
      if (pts.length >= 2) chains.push(pts.slice());
    }
  }

  // offene Stuecke aneinanderhaengen
  let changed = true;
  while (changed && chains.length) {
    changed = false;
    for (let i = 0; i < chains.length && !changed; i++) {
      if (!chains[i].length) continue;
      for (let j = 0; j < chains.length; j++) {
        if (i === j || !chains[j].length) continue;
        const a = chains[i], b = chains[j];
        if (G.dist(a[a.length - 1], b[0]) <= tol) chains[i] = a.concat(b.slice(1));
        else if (G.dist(a[a.length - 1], b[b.length - 1]) <= tol)
          chains[i] = a.concat(b.slice().reverse().slice(1));
        else if (G.dist(a[0], b[b.length - 1]) <= tol) chains[i] = b.concat(a.slice(1));
        else if (G.dist(a[0], b[0]) <= tol) chains[i] = b.slice().reverse().concat(a.slice(1));
        else continue;
        chains[j] = [];
        changed = true;
        break;
      }
    }
  }

  for (const chain of chains) {
    if (chain.length >= 3 && G.dist(chain[0], chain[chain.length - 1]) <= tol) {
      loops.push(dedupe(chain.slice(0, -1)));
    }
  }
  return loops.filter((lp) => lp.length >= 3 && Math.abs(G.signedArea(lp)) > 1e-6);
}

function dedupe(pts, tol = 1e-7) {
  const out = [];
  for (const p of pts) if (!out.length || G.dist(out[out.length - 1], p) > tol) out.push(p);
  return out;
}

/** Konturen in Aussen- und Innenkonturen (Bohrungen) sortieren. */
export function classifyLoops(loops) {
  const items = loops.map((lp) => ({ pts: lp.slice(), area: Math.abs(G.signedArea(lp)) }));
  items.sort((a, b) => b.area - a.area);
  const profiles = [];
  for (const it of items) {
    const inner = it.pts[0];
    let host = null;
    for (const prof of profiles) if (G.pointInPolygon(inner, prof.outer)) host = prof;
    if (host) host.holes.push(it.pts);
    else profiles.push({ outer: it.pts, holes: [] });
  }
  return profiles;
}

function orient(pts, ccw) {
  const out = pts.slice();
  if (G.signedArea(out) > 0 !== ccw) out.reverse();
  return out;
}

// ---------------------------------------------------------------------------
// Extrusion
// ---------------------------------------------------------------------------

/** Prisma aus einer Aussenkontur und optionalen Bohrungen. */
export function extrude(outer, holes = [], height = 10, z0 = 0, name = "Körper") {
  height = Number(height);
  if (Math.abs(height) < 1e-9) height = 1e-9;
  let z1 = z0 + height;
  if (height < 0) { const t = z0; z0 = z1; z1 = t; }

  const outerLoop = orient(dedupe(outer), true);
  const holeLoops = holes.filter((h) => h.length >= 3).map((h) => orient(dedupe(h), false));

  const verts = [];
  const bottomLoops = [];
  const topLoops = [];

  for (const loop of [outerLoop, ...holeLoops]) {
    const bi = [], ti = [];
    for (const p of loop) {
      bi.push(verts.length); verts.push([p[0], p[1], z0]);
      ti.push(verts.length); verts.push([p[0], p[1], z1]);
    }
    bottomLoops.push(bi);
    topLoops.push(ti);
  }

  const faces = [];
  // Deckel: Aussenkontur mit Loechern; Normale nach unten bzw. oben
  faces.push({
    loops: [bottomLoops[0].slice().reverse(), ...bottomLoops.slice(1).map((h) => h.slice().reverse())],
    normal: [0, 0, -1],
  });
  faces.push({ loops: [topLoops[0], ...topLoops.slice(1)], normal: [0, 0, 1] });

  const edges = new Map();
  const addEdge = (a, b, face) => {
    const key = Math.min(a, b) + ":" + Math.max(a, b);
    let rec = edges.get(key);
    if (!rec) { rec = { a: Math.min(a, b), b: Math.max(a, b), faces: [] }; edges.set(key, rec); }
    if (!rec.faces.includes(face)) rec.faces.push(face);
  };

  [outerLoop, ...holeLoops].forEach((loop, li) => {
    const bi = bottomLoops[li], ti = topLoops[li];
    const n = loop.length;
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      const fi = faces.length;
      const a3 = verts[bi[i]];
      const normal = norm3(cross3(sub3(verts[bi[j]], a3), sub3(verts[ti[i]], a3)));
      faces.push({ loops: [[bi[i], bi[j], ti[j], ti[i]]], normal });
      addEdge(bi[i], bi[j], fi);
      addEdge(ti[i], ti[j], fi);
      addEdge(bi[i], ti[i], fi);
      addEdge(bi[j], ti[j], fi);
      addEdge(bi[i], bi[j], 0);
      addEdge(ti[i], ti[j], 1);
    }
  });

  return {
    name, verts, faces, edges: [...edges.values()], height, z0, z1,
    profile: {
      outer: outerLoop.map((p) => [p[0], p[1]]),
      holes: holeLoops.map((h) => h.map((p) => [p[0], p[1]])),
    },
  };
}

/** Kreisrunde Innenkonturen erkennen -- fuer Mittellinien in den Ansichten. */
export function circularFeatures(profile) {
  const out = [];
  for (const loop of profile.holes || []) {
    if (loop.length < 8) continue;
    const cx = loop.reduce((s, p) => s + p[0], 0) / loop.length;
    const cy = loop.reduce((s, p) => s + p[1], 0) / loop.length;
    const radii = loop.map((p) => G.dist([cx, cy], p));
    const r = radii.reduce((s, v) => s + v, 0) / radii.length;
    if (r > 1e-6 && Math.max(...radii.map((v) => Math.abs(v - r))) < r * 0.02) {
      out.push({ center: [cx, cy], r });
    }
  }
  return out;
}

export function bbox3(solids) {
  const pts = solids.flatMap((s) => s.verts);
  if (!pts.length) return null;
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (const p of pts) {
    for (let i = 0; i < 3; i++) {
      if (p[i] < min[i]) min[i] = p[i];
      if (p[i] > max[i]) max[i] = p[i];
    }
  }
  return [min[0], min[1], min[2], max[0], max[1], max[2]];
}

/** Volumen in mm³ (Aussenkontur minus Bohrungen). */
export function volume(sol) {
  const prof = sol.profile || {};
  let area = Math.abs(G.signedArea(prof.outer || []));
  for (const h of prof.holes || []) area -= Math.abs(G.signedArea(h));
  return Math.max(0, area) * Math.abs(sol.height || 0);
}

/** Masse in kg bei gegebener Dichte (Standard: Stahl). */
export function mass(sol, density = 7.85) {
  return volume(sol) / 1.0e6 * density;
}
