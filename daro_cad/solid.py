"""Extrusion von 2D-Profilen zu Koerpern.

Aus geschlossenen Konturen entstehen Prismen: Aussenkontur plus beliebig viele
Innenkonturen (Bohrungen, Ausschnitte).  Der Koerper wird als Kantenmodell mit
Flaecheninformation gefuehrt -- genau das braucht die Ansichtsableitung fuer die
Ermittlung verdeckter Kanten.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import geom, model
from .model import Point

Vec3 = Tuple[float, float, float]

# Kanten zwischen fast parallelen Flaechen (Tessellierung eines Zylinders)
# gelten als "weich" und werden nur als Silhouette gezeichnet.
SMOOTH_ANGLE = 20.0


def _v3(x: float, y: float, z: float) -> Vec3:
    return (float(x), float(y), float(z))


def sub3(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def cross3(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot3(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def norm3(a: Vec3) -> Vec3:
    n = math.sqrt(dot3(a, a))
    if n < 1e-12:
        return (0.0, 0.0, 0.0)
    return (a[0] / n, a[1] / n, a[2] / n)


# ---------------------------------------------------------------------------
# Konturen aus Zeichnungselementen bilden
# ---------------------------------------------------------------------------

def build_loops(entities: Sequence[Dict[str, Any]], tol: float = 0.05,
                sagitta: float = 0.08) -> List[List[Point]]:
    """Aus Linien, Boegen, Kreisen und Polylinien geschlossene Konturen ketten."""
    chains: List[List[Point]] = []
    loops: List[List[Point]] = []

    for e in entities:
        t = e.get("type")
        if t == "circle":
            loops.append(model.outline_points(e, sagitta))
            continue
        if t == "polyline" and e.get("closed"):
            loops.append(model.outline_points(e, sagitta))
            continue
        if t in ("line", "arc", "polyline"):
            pts = model.outline_points(e, sagitta)
            if len(pts) >= 2:
                chains.append(list(pts))

    # offene Stuecke aneinanderhaengen
    changed = True
    while changed and chains:
        changed = False
        for i in range(len(chains)):
            if not chains[i]:
                continue
            for j in range(len(chains)):
                if i == j or not chains[j]:
                    continue
                a, b = chains[i], chains[j]
                if geom.dist(a[-1], b[0]) <= tol:
                    chains[i] = a + b[1:]
                elif geom.dist(a[-1], b[-1]) <= tol:
                    chains[i] = a + list(reversed(b))[1:]
                elif geom.dist(a[0], b[-1]) <= tol:
                    chains[i] = b + a[1:]
                elif geom.dist(a[0], b[0]) <= tol:
                    chains[i] = list(reversed(b)) + a[1:]
                else:
                    continue
                chains[j] = []
                changed = True
                break

    for chain in chains:
        if len(chain) >= 3 and geom.dist(chain[0], chain[-1]) <= tol:
            loops.append(geom.dedupe(chain[:-1]))

    return [lp for lp in loops if len(lp) >= 3 and abs(geom.signed_area(lp)) > 1e-6]


def classify_loops(loops: Sequence[Sequence[Point]]) -> List[Dict[str, Any]]:
    """Konturen in Aussen- und Innenkonturen (Bohrungen) sortieren."""
    items = [{"pts": list(lp), "area": abs(geom.signed_area(lp))} for lp in loops]
    items.sort(key=lambda it: it["area"], reverse=True)
    profiles: List[Dict[str, Any]] = []
    for it in items:
        inner = it["pts"][0]
        host = None
        for prof in profiles:
            if geom.point_in_polygon(inner, prof["outer"]):
                host = prof
        if host is None:
            profiles.append({"outer": it["pts"], "holes": []})
        else:
            host["holes"].append(it["pts"])
    return profiles


def orient(pts: Sequence[Point], ccw: bool) -> List[Point]:
    out = list(pts)
    if geom.is_ccw(out) != ccw:
        out.reverse()
    return out


# ---------------------------------------------------------------------------
# Extrusion
# ---------------------------------------------------------------------------

def extrude(outer: Sequence[Point], holes: Sequence[Sequence[Point]] = (),
            height: float = 10.0, z0: float = 0.0,
            name: str = "Koerper") -> Dict[str, Any]:
    """Prisma aus einer Aussenkontur und optionalen Bohrungen erzeugen."""
    height = float(height)
    if abs(height) < 1e-9:
        height = 1e-9
    z1 = z0 + height
    if height < 0:
        z0, z1 = z1, z0

    outer = orient(geom.dedupe(outer), ccw=True)
    holes = [orient(geom.dedupe(h), ccw=False) for h in holes if len(h) >= 3]

    verts: List[Vec3] = []
    bottom_loops: List[List[int]] = []
    top_loops: List[List[int]] = []

    for loop in [outer] + list(holes):
        bi, ti = [], []
        for p in loop:
            bi.append(len(verts)); verts.append(_v3(p[0], p[1], z0))
            ti.append(len(verts)); verts.append(_v3(p[0], p[1], z1))
        bottom_loops.append(bi)
        top_loops.append(ti)

    faces: List[Dict[str, Any]] = []
    # Deckel: Aussenkontur mit Loechern; Normale nach unten bzw. oben
    faces.append({"loops": [list(reversed(bottom_loops[0]))] + [list(reversed(h)) for h in bottom_loops[1:]],
                  "normal": (0.0, 0.0, -1.0)})
    faces.append({"loops": [top_loops[0]] + list(top_loops[1:]),
                  "normal": (0.0, 0.0, 1.0)})

    edges: Dict[Tuple[int, int], Dict[str, Any]] = {}

    def add_edge(a: int, b: int, face: int) -> None:
        key = (min(a, b), max(a, b))
        rec = edges.setdefault(key, {"a": key[0], "b": key[1], "faces": []})
        if face not in rec["faces"]:
            rec["faces"].append(face)

    for li, loop in enumerate([outer] + list(holes)):
        bi, ti = bottom_loops[li], top_loops[li]
        n = len(loop)
        for i in range(n):
            j = (i + 1) % n
            fi = len(faces)
            quad = [bi[i], bi[j], ti[j], ti[i]]
            a3 = verts[bi[i]]
            normal = norm3(cross3(sub3(verts[bi[j]], a3), sub3(verts[ti[i]], a3)))
            faces.append({"loops": [quad], "normal": normal})
            add_edge(bi[i], bi[j], fi)
            add_edge(ti[i], ti[j], fi)
            add_edge(bi[i], ti[i], fi)
            add_edge(bi[j], ti[j], fi)
            add_edge(bi[i], bi[j], 0)
            add_edge(ti[i], ti[j], 1)

    return {
        "name": name,
        "verts": [list(v) for v in verts],
        "faces": faces,
        "edges": list(edges.values()),
        "height": height,
        "z0": z0,
        "z1": z1,
        "profile": {"outer": [list(p) for p in outer], "holes": [[list(p) for p in h] for h in holes]},
    }


def circular_features(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Kreisrunde Innenkonturen erkennen -- fuer Mittellinien in den Ansichten."""
    out = []
    for loop in profile.get("holes", []):
        pts = [tuple(p) for p in loop]
        if len(pts) < 8:
            continue
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        radii = [geom.dist((cx, cy), p) for p in pts]
        r = sum(radii) / len(radii)
        if r > 1e-6 and max(abs(v - r) for v in radii) < r * 0.02:
            out.append({"center": (cx, cy), "r": r})
    return out


def bbox3(solids: Sequence[Dict[str, Any]]):
    pts = [v for s in solids for v in s["verts"]]
    if not pts:
        return None
    return (min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts))


def volume(sol: Dict[str, Any]) -> float:
    """Volumen des Prismas in mm^3 (Aussenkontur minus Bohrungen)."""
    prof = sol.get("profile") or {}
    area = abs(geom.signed_area([tuple(p) for p in prof.get("outer", [])]))
    for h in prof.get("holes", []):
        area -= abs(geom.signed_area([tuple(p) for p in h]))
    return max(0.0, area) * abs(sol.get("height", 0.0))


def mass(sol: Dict[str, Any], density_kg_dm3: float = 7.85) -> float:
    """Masse in kg bei gegebener Dichte (Standard: Stahl)."""
    return volume(sol) / 1.0e6 * density_kg_dm3
