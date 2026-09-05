"""Geometrische Grundfunktionen fuer DARO-CAD.

Alle Koordinaten sind Modellkoordinaten in Millimetern, Y-Achse zeigt nach oben
(CAD-Konvention).  Winkel werden in Grad gefuehrt und gegen den Uhrzeigersinn
gemessen -- wie in DXF.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Sequence, Tuple

Point = Tuple[float, float]

EPS = 1e-9


def add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def mul(a: Point, s: float) -> Point:
    return (a[0] * s, a[1] * s)


def dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def length(a: Point) -> float:
    return math.hypot(a[0], a[1])


def dist(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def normalize(a: Point) -> Point:
    n = length(a)
    if n < EPS:
        return (0.0, 0.0)
    return (a[0] / n, a[1] / n)


def perp(a: Point) -> Point:
    """Um 90 Grad gegen den Uhrzeigersinn gedreht."""
    return (-a[1], a[0])


def lerp(a: Point, b: Point, t: float) -> Point:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def rotate(p: Point, angle_deg: float, origin: Point = (0.0, 0.0)) -> Point:
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    dx, dy = p[0] - origin[0], p[1] - origin[1]
    return (origin[0] + dx * ca - dy * sa, origin[1] + dx * sa + dy * ca)


def angle_of(a: Point) -> float:
    """Winkel des Vektors in Grad, normiert auf [0, 360)."""
    return norm_angle(math.degrees(math.atan2(a[1], a[0])))


def norm_angle(deg: float) -> float:
    deg = math.fmod(deg, 360.0)
    if deg < 0:
        deg += 360.0
    return deg


def polar(origin: Point, angle_deg: float, radius: float) -> Point:
    a = math.radians(angle_deg)
    return (origin[0] + math.cos(a) * radius, origin[1] + math.sin(a) * radius)


def arc_sweep(start_deg: float, end_deg: float) -> float:
    """Ueberstrichener Winkel eines Bogens (immer gegen den Uhrzeigersinn)."""
    sweep = norm_angle(end_deg - start_deg)
    if sweep < EPS:
        sweep = 360.0
    return sweep


def arc_point(center: Point, radius: float, angle_deg: float) -> Point:
    return polar(center, angle_deg, radius)


def arc_contains_angle(start_deg: float, end_deg: float, angle_deg: float) -> bool:
    """Liegt der Winkel auf dem Bogen von start nach end (CCW)?"""
    sweep = arc_sweep(start_deg, end_deg)
    rel = norm_angle(angle_deg - start_deg)
    return rel <= sweep + 1e-7


def flatten_arc(center: Point, radius: float, start_deg: float, end_deg: float,
                max_sagitta: float = 0.05, min_segments: int = 4) -> List[Point]:
    """Bogen in einen Polygonzug zerlegen.

    ``max_sagitta`` begrenzt den Stichmass-Fehler in mm, sodass Exporte auch bei
    grossen Radien glatt aussehen.
    """
    sweep = arc_sweep(start_deg, end_deg)
    if radius <= EPS:
        return [center, center]
    ratio = max(0.0, min(1.0, 1.0 - max_sagitta / radius))
    step = math.degrees(2.0 * math.acos(ratio)) if ratio < 1.0 else 5.0
    step = max(step, 0.5)
    n = max(min_segments, int(math.ceil(sweep / step)))
    return [arc_point(center, radius, start_deg + sweep * i / n) for i in range(n + 1)]


def bulge_to_arc(a: Point, b: Point, bulge: float):
    """DXF-Bulge in Kreisbogen umrechnen.

    Rueckgabe ``(center, radius, start_deg, end_deg)``; bei negativem Bulge
    laeuft der Bogen im Uhrzeigersinn, deshalb werden Start und Ende getauscht,
    damit die CCW-Konvention erhalten bleibt.
    """
    chord = dist(a, b)
    if chord < EPS or abs(bulge) < EPS:
        return None
    theta = 4.0 * math.atan(bulge)          # ueberstrichener Winkel, vorzeichenbehaftet
    radius = chord / (2.0 * math.sin(abs(theta) / 2.0))
    mid = lerp(a, b, 0.5)
    h = radius * math.cos(theta / 2.0)
    direction = normalize(perp(sub(b, a)))
    center = add(mid, mul(direction, h if bulge > 0 else -h))
    sa = angle_of(sub(a, center))
    ea = angle_of(sub(b, center))
    if bulge < 0:
        sa, ea = ea, sa
    return center, radius, sa, ea


# --------------------------------------------------------------------------
# Schnittpunkte -- Basis fuer Fangpunkte, Trimmen und Abrunden
# --------------------------------------------------------------------------

def line_line_intersection(a1: Point, a2: Point, b1: Point, b2: Point,
                           segment: bool = True):
    """Schnittpunkt zweier Strecken bzw. Geraden, ``None`` bei Parallelitaet."""
    r = sub(a2, a1)
    s = sub(b2, b1)
    denom = cross(r, s)
    if abs(denom) < EPS:
        return None
    t = cross(sub(b1, a1), s) / denom
    u = cross(sub(b1, a1), r) / denom
    if segment and not (-1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9):
        return None
    return add(a1, mul(r, t))


def line_circle_intersection(a: Point, b: Point, center: Point, radius: float,
                             segment: bool = True) -> List[Point]:
    d = sub(b, a)
    f = sub(a, center)
    aa = dot(d, d)
    if aa < EPS:
        return []
    bb = 2 * dot(f, d)
    cc = dot(f, f) - radius * radius
    disc = bb * bb - 4 * aa * cc
    if disc < 0:
        return []
    disc = math.sqrt(disc)
    out = []
    for t in ((-bb - disc) / (2 * aa), (-bb + disc) / (2 * aa)):
        if segment and not (-1e-9 <= t <= 1 + 1e-9):
            continue
        out.append(add(a, mul(d, t)))
    return out


def circle_circle_intersection(c1: Point, r1: float, c2: Point, r2: float) -> List[Point]:
    d = dist(c1, c2)
    if d < EPS or d > r1 + r2 + EPS or d < abs(r1 - r2) - EPS:
        return []
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h2 = r1 * r1 - a * a
    h = math.sqrt(max(0.0, h2))
    base = add(c1, mul(sub(c2, c1), a / d))
    if h < EPS:
        return [base]
    off = mul(perp(normalize(sub(c2, c1))), h)
    return [add(base, off), sub(base, off)]


def closest_point_on_segment(p: Point, a: Point, b: Point) -> Point:
    d = sub(b, a)
    aa = dot(d, d)
    if aa < EPS:
        return a
    t = max(0.0, min(1.0, dot(sub(p, a), d) / aa))
    return add(a, mul(d, t))


# --------------------------------------------------------------------------
# Polygone
# --------------------------------------------------------------------------

def signed_area(pts: Sequence[Point]) -> float:
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def is_ccw(pts: Sequence[Point]) -> bool:
    return signed_area(pts) > 0


def point_in_polygon(p: Point, pts: Sequence[Point]) -> bool:
    """Ray-Casting; Punkte auf dem Rand gelten als innen."""
    x, y = p
    inside = False
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if abs(cross(sub((x2, y2), (x1, y1)), sub(p, (x1, y1)))) < 1e-9:
            if min(x1, x2) - 1e-9 <= x <= max(x1, x2) + 1e-9 and \
               min(y1, y2) - 1e-9 <= y <= max(y1, y2) + 1e-9:
                return True
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
            if xi > x:
                inside = not inside
    return inside


def bbox(points: Iterable[Point]):
    pts = list(points)
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def dedupe(pts: Sequence[Point], tol: float = 1e-7) -> List[Point]:
    out: List[Point] = []
    for p in pts:
        if not out or dist(out[-1], p) > tol:
            out.append(p)
    return out
