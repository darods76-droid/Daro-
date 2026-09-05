// Objektfang: Endpunkt, Mitte, Zentrum, Quadrant, Schnittpunkt, Lot, Naechster.
import * as G from "./geom.js";
import { polylineSegments, outlinePoints } from "./doc.js";

export const SNAP_LABELS = {
  endpoint: "Endpunkt", midpoint: "Mittelpunkt", center: "Zentrum",
  quadrant: "Quadrant", intersection: "Schnittpunkt", perpendicular: "Lot",
  nearest: "Nächster", grid: "Raster",
};

export const DEFAULT_SNAPS = {
  endpoint: true, midpoint: true, center: true, quadrant: true,
  intersection: true, perpendicular: true, nearest: false, grid: true,
};

const PRIORITY = ["endpoint", "intersection", "center", "midpoint", "quadrant",
  "perpendicular", "nearest", "grid"];

/** Alle Strecken/Boegen einer Entitaet -- Grundlage fuer Fang und Schnittpunkte. */
export function primitivesOf(e) {
  switch (e.type) {
    case "line": return [{ kind: "line", a: e.a, b: e.b }];
    case "circle": return [{ kind: "circle", c: e.c, r: e.r }];
    case "arc": return [{ kind: "arc", c: e.c, r: e.r, start: e.start, end: e.end }];
    case "polyline": return polylineSegments(e).map((s) =>
      s.kind === "line" ? { kind: "line", a: s.a, b: s.b }
        : { kind: "arc", c: s.c, r: s.r, start: s.start, end: s.end });
    case "hatch": {
      const pts = outlinePoints(e);
      return pts.map((p, i) => ({ kind: "line", a: p, b: pts[(i + 1) % pts.length] }));
    }
    default: return [];
  }
}

function candidatesFor(prim, kinds) {
  const out = [];
  if (prim.kind === "line") {
    if (kinds.endpoint) out.push({ p: prim.a, kind: "endpoint" }, { p: prim.b, kind: "endpoint" });
    if (kinds.midpoint) out.push({ p: G.lerp(prim.a, prim.b, 0.5), kind: "midpoint" });
  } else if (prim.kind === "circle") {
    if (kinds.center) out.push({ p: prim.c, kind: "center" });
    if (kinds.quadrant) {
      for (const a of [0, 90, 180, 270]) out.push({ p: G.arcPoint(prim.c, prim.r, a), kind: "quadrant" });
    }
  } else if (prim.kind === "arc") {
    if (kinds.center) out.push({ p: prim.c, kind: "center" });
    if (kinds.endpoint) {
      out.push({ p: G.arcPoint(prim.c, prim.r, prim.start), kind: "endpoint" },
        { p: G.arcPoint(prim.c, prim.r, prim.end), kind: "endpoint" });
    }
    if (kinds.midpoint) {
      out.push({ p: G.arcPoint(prim.c, prim.r,
        prim.start + G.arcSweep(prim.start, prim.end) / 2), kind: "midpoint" });
    }
    if (kinds.quadrant) {
      for (const a of [0, 90, 180, 270]) {
        if (G.arcContains(prim.start, prim.end, a)) {
          out.push({ p: G.arcPoint(prim.c, prim.r, a), kind: "quadrant" });
        }
      }
    }
  }
  return out;
}

export function intersectPrims(p1, p2) {
  if (p1.kind === "line" && p2.kind === "line") {
    const hit = G.lineLine(p1.a, p1.b, p2.a, p2.b);
    return hit ? [hit] : [];
  }
  if (p1.kind === "line" && p2.kind !== "line") return arcHits(p2, G.lineCircle(p1.a, p1.b, p2.c, p2.r));
  if (p2.kind === "line" && p1.kind !== "line") return arcHits(p1, G.lineCircle(p2.a, p2.b, p1.c, p1.r));
  const hits = G.circleCircle(p1.c, p1.r, p2.c, p2.r);
  return arcHits(p1, arcHits(p2, hits));
}

function arcHits(prim, points) {
  if (prim.kind !== "arc") return points;
  return points.filter((p) => G.arcContains(prim.start, prim.end, G.angleOf(G.sub(p, prim.c))));
}

function nearestOn(prim, p) {
  if (prim.kind === "line") return G.closestOnSegment(p, prim.a, prim.b);
  const dir = G.normalize(G.sub(p, prim.c));
  if (!dir[0] && !dir[1]) return null;
  const cand = G.add(prim.c, G.mul(dir, prim.r));
  if (prim.kind === "arc" && !G.arcContains(prim.start, prim.end, G.angleOf(G.sub(cand, prim.c)))) {
    return null;
  }
  return cand;
}

function perpendicularOn(prim, from) {
  if (prim.kind === "line") {
    const d = G.sub(prim.b, prim.a);
    const dd = G.dot(d, d);
    if (dd < 1e-12) return null;
    const t = G.dot(G.sub(from, prim.a), d) / dd;
    if (t < -1e-6 || t > 1 + 1e-6) return null;
    return G.add(prim.a, G.mul(d, t));
  }
  return nearestOn(prim, from);
}

/**
 * Fangpunkt suchen.
 * @param {object} opts {tolerance (Modell-mm), snaps, gridStep, from (Bezugspunkt), enabled}
 */
export function findSnap(entities, point, opts = {}) {
  const tol = opts.tolerance ?? 1;
  const snaps = opts.snaps || DEFAULT_SNAPS;
  if (opts.enabled === false) return null;

  const near = [];
  for (const e of entities) {
    if (e.type === "text" || e.type === "dim") continue;
    for (const prim of primitivesOf(e)) {
      const box = primBBox(prim);
      if (box && (point[0] < box[0] - tol * 3 || point[0] > box[2] + tol * 3 ||
                  point[1] < box[1] - tol * 3 || point[1] > box[3] + tol * 3)) continue;
      near.push(prim);
    }
  }

  const found = [];
  for (const prim of near) {
    for (const cand of candidatesFor(prim, snaps)) {
      if (G.dist(cand.p, point) <= tol) found.push(cand);
    }
  }

  if (snaps.intersection) {
    for (let i = 0; i < near.length; i++) {
      for (let j = i + 1; j < near.length; j++) {
        for (const hit of intersectPrims(near[i], near[j])) {
          if (G.dist(hit, point) <= tol) found.push({ p: hit, kind: "intersection" });
        }
      }
    }
  }

  if (snaps.perpendicular && opts.from) {
    for (const prim of near) {
      const p = perpendicularOn(prim, opts.from);
      if (p && G.dist(p, point) <= tol) found.push({ p, kind: "perpendicular" });
    }
  }

  if (snaps.nearest) {
    for (const prim of near) {
      const p = nearestOn(prim, point);
      if (p && G.dist(p, point) <= tol) found.push({ p, kind: "nearest" });
    }
  }

  if (found.length) {
    found.sort((a, b) => {
      const pa = PRIORITY.indexOf(a.kind), pb = PRIORITY.indexOf(b.kind);
      if (pa !== pb) return pa - pb;
      return G.dist(a.p, point) - G.dist(b.p, point);
    });
    const best = found[0];
    return { p: best.p, kind: best.kind, label: SNAP_LABELS[best.kind] };
  }

  if (snaps.grid && opts.gridStep) {
    const g = [G.round(point[0], opts.gridStep), G.round(point[1], opts.gridStep)];
    if (G.dist(g, point) <= Math.min(tol, opts.gridStep / 2)) {
      return { p: g, kind: "grid", label: SNAP_LABELS.grid };
    }
  }
  return null;
}

function primBBox(prim) {
  if (prim.kind === "line") return G.bbox([prim.a, prim.b]);
  return [prim.c[0] - prim.r, prim.c[1] - prim.r, prim.c[0] + prim.r, prim.c[1] + prim.r];
}
