// Geometrie-Grundlagen der Zeichenflaeche.
// Spiegelt daro_cad/geom.py -- gleiche Konventionen: Millimeter, Y nach oben,
// Winkel in Grad gegen den Uhrzeigersinn.

export const EPS = 1e-9;

export const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
export const sub = (a, b) => [a[0] - b[0], a[1] - b[1]];
export const mul = (a, s) => [a[0] * s, a[1] * s];
export const dot = (a, b) => a[0] * b[0] + a[1] * b[1];
export const cross = (a, b) => a[0] * b[1] - a[1] * b[0];
export const len = (a) => Math.hypot(a[0], a[1]);
export const dist = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);
export const perp = (a) => [-a[1], a[0]];
export const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
export const eq = (a, b, tol = 1e-7) => dist(a, b) <= tol;

export function normalize(a) {
  const n = len(a);
  return n < EPS ? [0, 0] : [a[0] / n, a[1] / n];
}

export function rotate(p, deg, origin = [0, 0]) {
  const a = deg * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
  const dx = p[0] - origin[0], dy = p[1] - origin[1];
  return [origin[0] + dx * c - dy * s, origin[1] + dx * s + dy * c];
}

export function normAngle(deg) {
  let d = deg % 360;
  if (d < 0) d += 360;
  return d;
}

export const angleOf = (a) => normAngle(Math.atan2(a[1], a[0]) * 180 / Math.PI);

export function polar(origin, deg, radius) {
  const a = deg * Math.PI / 180;
  return [origin[0] + Math.cos(a) * radius, origin[1] + Math.sin(a) * radius];
}

export function arcSweep(start, end) {
  const s = normAngle(end - start);
  return s < EPS ? 360 : s;
}

export const arcPoint = (c, r, deg) => polar(c, deg, r);

export function arcContains(start, end, deg) {
  return normAngle(deg - start) <= arcSweep(start, end) + 1e-7;
}

export function flattenArc(c, r, start, end, steps = 0) {
  const sweep = arcSweep(start, end);
  const n = steps || Math.max(6, Math.ceil(sweep / 6));
  const out = [];
  for (let i = 0; i <= n; i++) out.push(arcPoint(c, r, start + sweep * i / n));
  return out;
}

// DXF-Bulge -> Kreisbogen {c, r, start, end}
export function bulgeToArc(a, b, bulge) {
  const chord = dist(a, b);
  if (chord < EPS || Math.abs(bulge) < EPS) return null;
  const theta = 4 * Math.atan(bulge);
  const r = chord / (2 * Math.sin(Math.abs(theta) / 2));
  const mid = lerp(a, b, 0.5);
  const h = r * Math.cos(theta / 2);
  const dir = normalize(perp(sub(b, a)));
  const c = add(mid, mul(dir, bulge > 0 ? h : -h));
  let sa = angleOf(sub(a, c)), ea = angleOf(sub(b, c));
  if (bulge < 0) { const t = sa; sa = ea; ea = t; }
  return { c, r, start: sa, end: ea };
}

export function arcToBulge(c, r, start, end) {
  const sweep = arcSweep(start, end);
  return Math.tan(sweep * Math.PI / 180 / 4);
}

// -- Schnittpunkte ---------------------------------------------------------

export function lineLine(a1, a2, b1, b2, segment = true) {
  const r = sub(a2, a1), s = sub(b2, b1);
  const denom = cross(r, s);
  if (Math.abs(denom) < EPS) return null;
  const t = cross(sub(b1, a1), s) / denom;
  const u = cross(sub(b1, a1), r) / denom;
  if (segment && !(t >= -1e-9 && t <= 1 + 1e-9 && u >= -1e-9 && u <= 1 + 1e-9)) return null;
  return add(a1, mul(r, t));
}

export function lineCircle(a, b, c, r, segment = true) {
  const d = sub(b, a), f = sub(a, c);
  const aa = dot(d, d);
  if (aa < EPS) return [];
  const bb = 2 * dot(f, d);
  const cc = dot(f, f) - r * r;
  let disc = bb * bb - 4 * aa * cc;
  if (disc < 0) return [];
  disc = Math.sqrt(disc);
  const out = [];
  for (const t of [(-bb - disc) / (2 * aa), (-bb + disc) / (2 * aa)]) {
    if (segment && (t < -1e-9 || t > 1 + 1e-9)) continue;
    out.push(add(a, mul(d, t)));
  }
  return out;
}

export function circleCircle(c1, r1, c2, r2) {
  const d = dist(c1, c2);
  if (d < EPS || d > r1 + r2 + EPS || d < Math.abs(r1 - r2) - EPS) return [];
  const a = (r1 * r1 - r2 * r2 + d * d) / (2 * d);
  const h = Math.sqrt(Math.max(0, r1 * r1 - a * a));
  const base = add(c1, mul(sub(c2, c1), a / d));
  if (h < EPS) return [base];
  const off = mul(perp(normalize(sub(c2, c1))), h);
  return [add(base, off), sub(base, off)];
}

export function closestOnSegment(p, a, b) {
  const d = sub(b, a), aa = dot(d, d);
  if (aa < EPS) return a;
  const t = Math.max(0, Math.min(1, dot(sub(p, a), d) / aa));
  return add(a, mul(d, t));
}

export function distToSegment(p, a, b) {
  return dist(p, closestOnSegment(p, a, b));
}

export function distToArc(p, c, r, start, end) {
  const ang = angleOf(sub(p, c));
  if (arcContains(start, end, ang)) return Math.abs(dist(p, c) - r);
  return Math.min(dist(p, arcPoint(c, r, start)), dist(p, arcPoint(c, r, end)));
}

// -- Polygone --------------------------------------------------------------

export function signedArea(pts) {
  let s = 0;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    s += a[0] * b[1] - b[0] * a[1];
  }
  return s / 2;
}

export function pointInPolygon(p, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const a = pts[i], b = pts[j];
    if ((a[1] > p[1]) !== (b[1] > p[1])) {
      const x = a[0] + (p[1] - a[1]) / (b[1] - a[1]) * (b[0] - a[0]);
      if (x > p[0]) inside = !inside;
    }
  }
  return inside;
}

export function bbox(points) {
  if (!points.length) return null;
  let [x0, y0] = points[0], x1 = x0, y1 = y0;
  for (const p of points) {
    if (p[0] < x0) x0 = p[0];
    if (p[1] < y0) y0 = p[1];
    if (p[0] > x1) x1 = p[0];
    if (p[1] > y1) y1 = p[1];
  }
  return [x0, y0, x1, y1];
}

export const bboxOverlap = (a, b) =>
  a && b && a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];

export const bboxInside = (inner, outer) =>
  inner && outer && inner[0] >= outer[0] && inner[2] <= outer[2] &&
  inner[1] >= outer[1] && inner[3] <= outer[3];

export function round(value, step) {
  return step > 0 ? Math.round(value / step) * step : value;
}
