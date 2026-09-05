// Aenderungsbefehle: Verschieben, Drehen, Spiegeln, Versatz, Stutzen, Dehnen,
// Runden, Fasen, Reihe, Skalieren.
import * as G from "./geom.js";
import { transformEntity, polylineSegments, newId } from "./doc.js";
import { primitivesOf, intersectPrims } from "./snap.js";

export const translate = (e, v) => transformEntity(e, (p) => G.add(p, v));
export const rotateEntity = (e, origin, deg) => transformEntity(e, (p) => G.rotate(p, deg, origin));

export function mirrorEntity(e, a, b) {
  const d = G.normalize(G.sub(b, a));
  if (!d[0] && !d[1]) return { ...e };
  return transformEntity(e, (p) => {
    const rel = G.sub(p, a);
    const along = G.mul(d, G.dot(rel, d));
    const off = G.sub(rel, along);
    return G.add(a, G.sub(along, off));
  });
}

export function scaleEntity(e, origin, factor) {
  const out = transformEntity(e, (p) => G.add(origin, G.mul(G.sub(p, origin), factor)));
  if (out.type === "text") out.h *= Math.abs(factor);
  if (out.type === "dim") out.h *= Math.abs(factor);
  if (out.type === "circle" || out.type === "arc") out.r = Math.abs(out.r * factor) || out.r;
  return out;
}

export function copyEntity(e) {
  return { ...JSON.parse(JSON.stringify(e)), id: newId() };
}

/** Rechteckige oder polare Reihe. */
export function array(entities, opts) {
  const out = [];
  if (opts.kind === "polar") {
    const count = Math.max(1, Math.round(opts.count || 4));
    const total = opts.total ?? 360;
    const step = total >= 360 ? total / count : (count > 1 ? total / (count - 1) : 0);
    for (let i = 1; i < count; i++) {
      for (const e of entities) {
        const copy = rotateEntity(e, opts.center || [0, 0], step * i);
        out.push({ ...copy, id: newId() });
      }
    }
    return out;
  }
  const cols = Math.max(1, Math.round(opts.cols || 1));
  const rows = Math.max(1, Math.round(opts.rows || 1));
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (!r && !c) continue;
      const v = [c * (opts.dx || 0), r * (opts.dy || 0)];
      for (const e of entities) out.push({ ...translate(e, v), id: newId() });
    }
  }
  return out;
}

/** Parallelversatz einer Entitaet um ``distance`` in Richtung ``side``. */
export function offsetEntity(e, distance, side) {
  const d = Math.abs(distance);
  switch (e.type) {
    case "line": {
      const dir = G.normalize(G.sub(e.b, e.a));
      const n = G.perp(dir);
      const sign = G.dot(G.sub(side, e.a), n) >= 0 ? 1 : -1;
      const v = G.mul(n, d * sign);
      return { ...copyEntity(e), a: G.add(e.a, v), b: G.add(e.b, v) };
    }
    case "circle": {
      const outward = G.dist(side, e.c) >= e.r;
      const r = outward ? e.r + d : e.r - d;
      return r > 1e-6 ? { ...copyEntity(e), r } : null;
    }
    case "arc": {
      const outward = G.dist(side, e.c) >= e.r;
      const r = outward ? e.r + d : e.r - d;
      return r > 1e-6 ? { ...copyEntity(e), r } : null;
    }
    case "polyline": {
      const pts = e.pts;
      if (pts.length < 2) return null;
      // Seite anhand des naechstgelegenen Segments bestimmen
      let best = Infinity, sign = 1;
      const segs = e.closed ? pts.map((p, i) => [p, pts[(i + 1) % pts.length]])
        : pts.slice(0, -1).map((p, i) => [p, pts[i + 1]]);
      for (const [a, b] of segs) {
        const dd = G.distToSegment(side, a, b);
        if (dd < best) {
          best = dd;
          sign = G.dot(G.sub(side, a), G.perp(G.normalize(G.sub(b, a)))) >= 0 ? 1 : -1;
        }
      }
      const lines = segs.map(([a, b]) => {
        const v = G.mul(G.perp(G.normalize(G.sub(b, a))), d * sign);
        return [G.add(a, v), G.add(b, v)];
      });
      const out = [];
      for (let i = 0; i < lines.length; i++) {
        const cur = lines[i];
        const prev = lines[(i - 1 + lines.length) % lines.length];
        if (i === 0 && !e.closed) { out.push(cur[0]); continue; }
        const hit = G.lineLine(prev[0], prev[1], cur[0], cur[1], false);
        out.push(hit || cur[0]);
      }
      if (!e.closed) out.push(lines[lines.length - 1][1]);
      return { ...copyEntity(e), pts: out, bulges: undefined };
    }
    default: return null;
  }
}

// -- Stutzen und Dehnen ----------------------------------------------------

/** Parameter (0..1 bzw. Winkel) aller Schnittpunkte mit anderen Elementen. */
function cutParams(target, others) {
  const prims = primitivesOf(target);
  const params = [];
  for (const prim of prims) {
    for (const other of others) {
      for (const op of primitivesOf(other)) {
        for (const hit of intersectPrims(prim, op)) params.push(hit);
      }
    }
  }
  return params;
}

/** Element am Klickpunkt stutzen; gibt die verbleibenden Elemente zurueck. */
export function trim(target, others, clickPoint) {
  const hits = cutParams(target, others);
  if (!hits.length) return null;

  if (target.type === "line") {
    const d = G.sub(target.b, target.a);
    const dd = G.dot(d, d);
    if (dd < 1e-12) return null;
    const ts = hits
      .map((p) => G.dot(G.sub(p, target.a), d) / dd)
      .filter((t) => t > 1e-6 && t < 1 - 1e-6)
      .sort((a, b) => a - b);
    if (!ts.length) return null;
    const tc = G.dot(G.sub(clickPoint, target.a), d) / dd;
    const lo = [0, ...ts].filter((t) => t <= tc).pop() ?? 0;
    const hi = [...ts, 1].find((t) => t >= tc) ?? 1;
    const out = [];
    if (lo > 1e-6) out.push({ ...copyEntity(target), a: target.a, b: G.lerp(target.a, target.b, lo) });
    if (hi < 1 - 1e-6) out.push({ ...copyEntity(target), a: G.lerp(target.a, target.b, hi), b: target.b });
    return out;
  }

  if (target.type === "circle" || target.type === "arc") {
    const angles = hits
      .map((p) => G.angleOf(G.sub(p, target.c)))
      .filter((a) => target.type === "circle" || G.arcContains(target.start, target.end, a));
    if (angles.length < (target.type === "circle" ? 2 : 1)) return null;
    const clickAngle = G.angleOf(G.sub(clickPoint, target.c));
    const start = target.type === "circle" ? 0 : target.start;
    const sweep = target.type === "circle" ? 360 : G.arcSweep(target.start, target.end);
    const rel = angles.map((a) => G.normAngle(a - start)).sort((a, b) => a - b);
    const clickRel = G.normAngle(clickAngle - start);
    const lo = [0, ...rel].filter((t) => t <= clickRel).pop() ?? 0;
    const hi = [...rel, sweep].find((t) => t >= clickRel) ?? sweep;
    const out = [];
    if (target.type === "circle") {
      // Kreis wird zum Bogen: das angeklickte Stueck faellt weg
      out.push({ ...copyEntity(target), type: "arc", start: G.normAngle(start + hi),
        end: G.normAngle(start + lo + 360) });
    } else {
      if (lo > 1e-6) out.push({ ...copyEntity(target), end: G.normAngle(start + lo) });
      if (hi < sweep - 1e-6) out.push({ ...copyEntity(target), start: G.normAngle(start + hi) });
    }
    return out;
  }
  return null;
}

/** Linie bis zum naechsten Schnittpunkt verlaengern. */
export function extend(target, others, clickPoint) {
  if (target.type !== "line") return null;
  const dir = G.normalize(G.sub(target.b, target.a));
  const nearEnd = G.dist(clickPoint, target.b) < G.dist(clickPoint, target.a);
  const from = nearEnd ? target.b : target.a;
  const way = nearEnd ? dir : G.mul(dir, -1);
  const far = G.add(from, G.mul(way, 1e5));
  const probe = { kind: "line", a: from, b: far };

  let best = null, bestD = Infinity;
  for (const other of others) {
    for (const op of primitivesOf(other)) {
      for (const hit of intersectPrims(probe, op)) {
        const d = G.dist(from, hit);
        if (d > 1e-7 && d < bestD) { bestD = d; best = hit; }
      }
    }
  }
  if (!best) return null;
  return nearEnd ? { ...copyEntity(target), b: best } : { ...copyEntity(target), a: best };
}

// -- Runden und Fasen ------------------------------------------------------

function lineParam(line, p) {
  const d = G.sub(line.b, line.a);
  return G.dot(G.sub(p, line.a), d) / G.dot(d, d);
}

/**
 * Richtung vom Eckpunkt zu der Seite, die erhalten bleiben soll.
 * Massgeblich ist der angeklickte Punkt: der Schenkel, auf dem geklickt wurde,
 * bleibt stehen -- so verhaelt es sich auch in FreeCAD und AutoCAD.
 */
function keepDirection(line, corner, click) {
  const dir = G.normalize(G.sub(line.b, line.a));
  const ref = click || (G.dist(line.a, corner) > G.dist(line.b, corner) ? line.a : line.b);
  return G.dot(G.sub(ref, corner), dir) >= 0 ? dir : G.mul(dir, -1);
}

/**
 * Rundung zwischen zwei Linien.
 * Rueckgabe {arc, first, second} mit den gestutzten Linien.
 */
export function fillet(l1, l2, radius, p1 = null, p2 = null) {
  if (l1.type !== "line" || l2.type !== "line") return null;
  const corner = G.lineLine(l1.a, l1.b, l2.a, l2.b, false);
  if (!corner) return null;

  const d1 = keepDirection(l1, corner, p1), d2 = keepDirection(l2, corner, p2);
  const cosA = Math.max(-1, Math.min(1, G.dot(d1, d2)));
  const angle = Math.acos(cosA);
  if (angle < 1e-6 || Math.abs(angle - Math.PI) < 1e-6) return null;

  if (radius <= 1e-9) {                       // Radius 0 = nur verschneiden
    return { arc: null,
      first: { ...copyEntity(l1), ...replaceEnd(l1, corner, d1) },
      second: { ...copyEntity(l2), ...replaceEnd(l2, corner, d2) } };
  }

  const tangentLen = radius / Math.tan(angle / 2);
  const t1 = G.add(corner, G.mul(d1, tangentLen));
  const t2 = G.add(corner, G.mul(d2, tangentLen));
  const bis = G.normalize(G.add(d1, d2));
  const center = G.add(corner, G.mul(bis, radius / Math.sin(angle / 2)));

  let start = G.angleOf(G.sub(t1, center));
  let end = G.angleOf(G.sub(t2, center));
  // Richtung so waehlen, dass der Bogen die kurze Seite nimmt
  if (G.arcSweep(start, end) > 180) { const t = start; start = end; end = t; }

  return {
    arc: { type: "arc", c: center, r: radius, start, end, layer: l1.layer },
    first: { ...copyEntity(l1), ...replaceEnd(l1, corner, d1, t1) },
    second: { ...copyEntity(l2), ...replaceEnd(l2, corner, d2, t2) },
  };
}

/** Fase zwischen zwei Linien (gleiche Schenkellaenge). */
export function chamfer(l1, l2, size, p1 = null, p2 = null) {
  if (l1.type !== "line" || l2.type !== "line" || size <= 0) return null;
  const corner = G.lineLine(l1.a, l1.b, l2.a, l2.b, false);
  if (!corner) return null;
  const d1 = keepDirection(l1, corner, p1), d2 = keepDirection(l2, corner, p2);
  const t1 = G.add(corner, G.mul(d1, size));
  const t2 = G.add(corner, G.mul(d2, size));
  return {
    line: { type: "line", a: t1, b: t2, layer: l1.layer },
    first: { ...copyEntity(l1), ...replaceEnd(l1, corner, d1, t1) },
    second: { ...copyEntity(l2), ...replaceEnd(l2, corner, d2, t2) },
  };
}

/** Den zum Eckpunkt zeigenden Endpunkt der Linie auf ``target`` setzen. */
function replaceEnd(line, corner, keepDir, target = null) {
  const point = target || corner;
  const keepA = G.dot(G.sub(line.a, corner), keepDir) > G.dot(G.sub(line.b, corner), keepDir);
  return keepA ? { a: line.a, b: point } : { a: point, b: line.b };
}

/** Polylinie in einzelne Linien und Boegen zerlegen (Auflösen). */
export function explode(entity) {
  if (entity.type === "polyline") {
    return polylineSegments(entity).map((seg) => seg.kind === "line"
      ? { type: "line", a: seg.a, b: seg.b, layer: entity.layer, id: newId() }
      : { type: "arc", c: seg.c, r: seg.r, start: seg.start, end: seg.end,
          layer: entity.layer, id: newId() });
  }
  if (entity.type === "circle") {
    return [0, 180].map((a) => ({ type: "arc", c: entity.c, r: entity.r,
      start: a, end: a + 180, layer: entity.layer, id: newId() }));
  }
  return null;
}
