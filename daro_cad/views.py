"""Ansichten aus Koerpern ableiten (Vorderansicht, Draufsicht, Seitenansicht).

Die Projektion arbeitet mit einer echten Verdeckt-Kanten-Ermittlung: jede Kante
wird an den Umrissen der zum Betrachter zeigenden Flaechen zerlegt und in
sichtbare und verdeckte Abschnitte getrennt.  Verdeckte Kanten landen auf dem
Layer "Verdeckt" und werden dadurch strichliert dargestellt -- wie in DIN ISO
128-24 gefordert.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import geom, solid as solid_mod
from .model import Point
from .solid import Vec3, cross3, dot3, norm3, sub3

# Basis der Vorderansicht: der Betrachter blickt entlang -Z auf die XY-Ebene,
# sieht also genau die gezeichnete Kontur in wahrer Groesse.
U0: Vec3 = (1.0, 0.0, 0.0)
V0: Vec3 = (0.0, 1.0, 0.0)
W0: Vec3 = (0.0, 0.0, -1.0)      # Tiefenrichtung: vom Betrachter weg


def _neg(v: Vec3) -> Vec3:
    return (-v[0], -v[1], -v[2])


# Blickrichtungen, abgeleitet aus der Basis der Vorderansicht.
VIEW_BASIS: Dict[str, Tuple[Vec3, Vec3, Vec3]] = {
    "front":  (U0, V0, W0),
    "back":   (_neg(U0), V0, _neg(W0)),
    "top":    (U0, W0, _neg(V0)),          # Blick von oben
    "bottom": (U0, _neg(W0), V0),          # Blick von unten
    "left":   (_neg(W0), V0, U0),          # Blick von links
    "right":  (W0, V0, _neg(U0)),          # Blick von rechts
}

VIEW_LABELS = {
    "front": "Vorderansicht", "back": "Rückansicht", "top": "Draufsicht",
    "bottom": "Untersicht", "left": "Ansicht von links", "right": "Ansicht von rechts",
}

# Anordnung relativ zur Vorderansicht in Vielfachen von (Breite, Hoehe).
# Projektionsmethode 1 (Europa/DIN): Blick von links wird rechts angeordnet.
PLACEMENT_FIRST = {"front": (0, 0), "left": (1, 0), "right": (-1, 0),
                   "top": (0, -1), "bottom": (0, 1), "back": (2, 0)}
PLACEMENT_THIRD = {"front": (0, 0), "left": (-1, 0), "right": (1, 0),
                   "top": (0, 1), "bottom": (0, -1), "back": (-2, 0)}

SILHOUETTE_EPS = 1e-9


def _to_view(p: Sequence[float], u: Vec3, v: Vec3, w: Vec3) -> Tuple[float, float, float]:
    p3 = (float(p[0]), float(p[1]), float(p[2]))
    return (dot3(p3, u), dot3(p3, v), dot3(p3, w))


def _face_polys(face: Dict[str, Any], pts: Sequence[Tuple[float, float, float]]):
    loops = [[(pts[i][0], pts[i][1]) for i in loop] for loop in face["loops"]]
    return loops


def _point_in_face(p: Point, loops: Sequence[Sequence[Point]]) -> bool:
    if not loops or not geom.point_in_polygon(p, loops[0]):
        return False
    for hole in loops[1:]:
        if geom.point_in_polygon(p, hole):
            return False
    return True


def project(solids: Sequence[Dict[str, Any]], view: str = "front",
            smooth_angle: float = solid_mod.SMOOTH_ANGLE) -> Dict[str, List[Tuple[Point, Point]]]:
    """Kanten aller Koerper in eine Ansicht projizieren.

    Rueckgabe: ``{"visible": [...], "hidden": [...]}`` mit 2D-Strecken.
    """
    u, v, w = VIEW_BASIS.get(view, VIEW_BASIS["front"])
    visible: List[Tuple[Point, Point]] = []
    hidden: List[Tuple[Point, Point]] = []

    # Alle Flaechen aller Koerper sammeln (Koerper verdecken sich gegenseitig)
    faces: List[Dict[str, Any]] = []
    all_pts: List[List[Tuple[float, float, float]]] = []
    for sol in solids:
        pts = [_to_view(p, u, v, w) for p in sol["verts"]]
        all_pts.append(pts)
        for face in sol["faces"]:
            n = face["normal"]
            nv = (dot3(n, u), dot3(n, v), dot3(n, w))
            if nv[2] >= -SILHOUETTE_EPS:
                continue                     # abgewandte Flaeche verdeckt nichts
            loops = _face_polys(face, pts)
            if not loops or len(loops[0]) < 3:
                continue
            ref = pts[face["loops"][0][0]]
            faces.append({
                "loops": loops,
                "n": nv,
                "c": nv[0] * ref[0] + nv[1] * ref[1] + nv[2] * ref[2],
                "bbox": geom.bbox(loops[0]),
            })

    size = 1.0
    box = solid_mod.bbox3(solids)
    if box:
        size = max(1.0, max(box[3] - box[0], box[4] - box[1], box[5] - box[2]))
    eps = size * 1e-6

    for sol, pts in zip(solids, all_pts):
        for edge in sol["edges"]:
            if not _edge_wanted(sol, edge, pts, u, v, w, smooth_angle):
                continue
            a, b = pts[edge["a"]], pts[edge["b"]]
            for seg, is_visible in _split_edge(a, b, faces, eps):
                (visible if is_visible else hidden).append(seg)

    vis, hid = _resolve(visible, hidden)
    return {"visible": vis, "hidden": hid}


def _edge_wanted(sol, edge, pts, u: Vec3, v: Vec3, w: Vec3, smooth_angle: float) -> bool:
    """Weiche Kanten (Zylindertessellierung) nur als Silhouette zeichnen."""
    faces = edge.get("faces", [])
    if len(faces) < 2:
        return True
    n1 = sol["faces"][faces[0]]["normal"]
    n2 = sol["faces"][faces[1]]["normal"]
    cos_a = max(-1.0, min(1.0, dot3(n1, n2)))
    if math.degrees(math.acos(cos_a)) > smooth_angle:
        return True
    d1 = dot3(n1, w)
    d2 = dot3(n2, w)
    return (d1 < 0.0) != (d2 < 0.0)          # Silhouettenkante


def _split_edge(a, b, faces, eps: float):
    """Kante an allen Flaechenumrissen zerlegen und Sichtbarkeit bestimmen."""
    a2, b2 = (a[0], a[1]), (b[0], b[1])
    if geom.dist(a2, b2) < 1e-9:
        return []
    params = {0.0, 1.0}
    dvec = geom.sub(b2, a2)
    dlen2 = geom.dot(dvec, dvec)
    for face in faces:
        fb = face["bbox"]
        if fb and (max(a2[0], b2[0]) < fb[0] - eps or min(a2[0], b2[0]) > fb[2] + eps or
                   max(a2[1], b2[1]) < fb[1] - eps or min(a2[1], b2[1]) > fb[3] + eps):
            continue
        for loop in face["loops"]:
            n = len(loop)
            for i in range(n):
                hit = geom.line_line_intersection(a2, b2, loop[i], loop[(i + 1) % n])
                if hit is None:
                    continue
                t = geom.dot(geom.sub(hit, a2), dvec) / dlen2
                if 1e-9 < t < 1 - 1e-9:
                    params.add(t)
    ordered = sorted(params)
    out: List[Tuple[Tuple[Point, Point], bool]] = []
    for i in range(len(ordered) - 1):
        t0, t1 = ordered[i], ordered[i + 1]
        if t1 - t0 < 1e-9:
            continue
        tm = (t0 + t1) / 2.0
        pm = geom.lerp(a2, b2, tm)
        depth = a[2] + (b[2] - a[2]) * tm
        vis = True
        for face in faces:
            nz = face["n"][2]
            if abs(nz) < 1e-12:
                continue
            if not _point_in_face(pm, face["loops"]):
                continue
            fd = (face["c"] - face["n"][0] * pm[0] - face["n"][1] * pm[1]) / nz
            if fd < depth - eps:
                vis = False
                break
        out.append(((geom.lerp(a2, b2, t0), geom.lerp(a2, b2, t1)), vis))
    return out


def _line_key(a: Point, b: Point):
    """Kanonische Kennung der Traegergeraden einer Strecke."""
    d = geom.normalize(geom.sub(b, a))
    if d[0] < -1e-9 or (abs(d[0]) <= 1e-9 and d[1] < 0):
        d = (-d[0], -d[1])
    off = geom.cross(d, a)                     # vorzeichenbehafteter Abstand zum Ursprung
    return d, off, (round(d[0], 7), round(d[1], 7), round(off, 4))


def _group(segments: Sequence[Tuple[Point, Point]]) -> Dict[Any, Dict[str, Any]]:
    groups: Dict[Any, Dict[str, Any]] = {}
    for a, b in segments:
        if geom.dist(a, b) < 1e-9:
            continue
        d, _off, key = _line_key(a, b)
        ta, tb = geom.dot(a, d), geom.dot(b, d)
        rec = groups.setdefault(key, {"d": d, "base": geom.sub(a, geom.mul(d, ta)), "iv": []})
        rec["iv"].append((min(ta, tb), max(ta, tb)))
    return groups


def _merge_intervals(iv: List[Tuple[float, float]], tol: float = 1e-7):
    out: List[List[float]] = []
    for lo, hi in sorted(iv):
        if out and lo <= out[-1][1] + tol:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return [(lo, hi) for lo, hi in out if hi - lo > tol]


def _subtract_intervals(iv, cuts, tol: float = 1e-7):
    out = list(iv)
    for clo, chi in cuts:
        nxt = []
        for lo, hi in out:
            if chi <= lo + tol or clo >= hi - tol:
                nxt.append((lo, hi)); continue
            if clo > lo + tol:
                nxt.append((lo, min(hi, clo)))
            if chi < hi - tol:
                nxt.append((max(lo, chi), hi))
        out = nxt
    return [(lo, hi) for lo, hi in out if hi - lo > tol]


def _emit(groups: Dict[Any, Dict[str, Any]]) -> List[Tuple[Point, Point]]:
    out: List[Tuple[Point, Point]] = []
    for rec in groups.values():
        d, base = rec["d"], rec["base"]
        for lo, hi in rec["iv"]:
            out.append((geom.add(base, geom.mul(d, lo)), geom.add(base, geom.mul(d, hi))))
    return out


def _resolve(visible: Sequence[Tuple[Point, Point]], hidden: Sequence[Tuple[Point, Point]]):
    """Doppelte Kanten entfernen; verdeckte Linien weichen deckungsgleichen sichtbaren."""
    vis = _group(visible)
    hid = _group(hidden)
    for rec in vis.values():
        rec["iv"] = _merge_intervals(rec["iv"])
    for key, rec in hid.items():
        rec["iv"] = _merge_intervals(rec["iv"])
        if key in vis:
            rec["iv"] = _subtract_intervals(rec["iv"], vis[key]["iv"])
    return _emit(vis), _emit(hid)


# ---------------------------------------------------------------------------
# Ansichten auf dem Blatt anordnen
# ---------------------------------------------------------------------------

def derive(solids: Sequence[Dict[str, Any]], views: Sequence[str] = ("front", "top", "left"),
           origin: Point = (0.0, 0.0), gap: float = 25.0, projection: str = "first",
           labels: bool = True, center_lines: bool = True,
           label_height: float = 5.0) -> List[Dict[str, Any]]:
    """Vollstaendigen Ansichtssatz als Zeichnungselemente erzeugen."""
    if not solids:
        return []
    placement = PLACEMENT_FIRST if projection == "first" else PLACEMENT_THIRD
    results: Dict[str, Dict[str, Any]] = {}

    for name in views:
        data = project(solids, name)
        pts = [p for seg in data["visible"] + data["hidden"] for p in seg]
        box = geom.bbox(pts) or (0.0, 0.0, 0.0, 0.0)
        results[name] = {"data": data, "bbox": box}

    ref = results.get("front") or next(iter(results.values()))
    rb = ref["bbox"]
    ref_w = rb[2] - rb[0]
    ref_h = rb[3] - rb[1]

    entities: List[Dict[str, Any]] = []
    for name, info in results.items():
        col, row = placement.get(name, (0, 0))
        box = info["bbox"]
        vw = box[2] - box[0]
        vh = box[3] - box[1]
        # Ansichten fluchten: gleiche Hoehe in einer Zeile, gleiche Breite in einer Spalte
        if col > 0:
            ox = origin[0] + ref_w / 2.0 + gap + vw / 2.0 + (col - 1) * (vw + gap)
        elif col < 0:
            ox = origin[0] - ref_w / 2.0 - gap - vw / 2.0 + (col + 1) * (vw + gap)
        else:
            ox = origin[0]
        if row > 0:
            oy = origin[1] + ref_h / 2.0 + gap + vh / 2.0 + (row - 1) * (vh + gap)
        elif row < 0:
            oy = origin[1] - ref_h / 2.0 - gap - vh / 2.0 + (row + 1) * (vh + gap)
        else:
            oy = origin[1]

        dx = ox - (box[0] + box[2]) / 2.0
        dy = oy - (box[1] + box[3]) / 2.0
        shift = lambda p: (p[0] + dx, p[1] + dy)

        for layer, key in (("Kontur", "visible"), ("Verdeckt", "hidden")):
            for a, b in info["data"][key]:
                entities.append({"type": "line", "a": shift(a), "b": shift(b),
                                 "layer": layer, "view": name})

        if center_lines:
            entities.extend(_center_lines(solids, name, shift, box))

        if labels:
            entities.append({
                "type": "text", "p": (ox, oy - vh / 2.0 - label_height * 1.8),
                "h": label_height, "text": VIEW_LABELS.get(name, name),
                "align": "center", "layer": "Text", "view": name})
    return entities


def _center_lines(solids, view: str, shift, box) -> List[Dict[str, Any]]:
    """Mittellinien fuer runde Bohrungen ergaenzen."""
    u, v, w = VIEW_BASIS.get(view, VIEW_BASIS["front"])
    out: List[Dict[str, Any]] = []
    for sol in solids:
        prof = sol.get("profile") or {}
        z0, z1 = sol.get("z0", 0.0), sol.get("z1", 0.0)
        for feat in solid_mod.circular_features(prof):
            cx, cy = feat["center"]
            r = feat["r"]
            p_low = _to_view((cx, cy, z0), u, v, w)
            p_high = _to_view((cx, cy, z1), u, v, w)
            axis = geom.sub((p_high[0], p_high[1]), (p_low[0], p_low[1]))
            over = r * 0.25 + 2.0
            if geom.length(axis) < 1e-6:
                # Achse zeigt zum Betrachter -> Mittenkreuz
                c = shift((p_low[0], p_low[1]))
                out.append({"type": "line", "a": (c[0] - r - over, c[1]),
                            "b": (c[0] + r + over, c[1]), "layer": "Mittellinie", "view": view})
                out.append({"type": "line", "a": (c[0], c[1] - r - over),
                            "b": (c[0], c[1] + r + over), "layer": "Mittellinie", "view": view})
            else:
                d = geom.normalize(axis)
                a = shift(geom.sub((p_low[0], p_low[1]), geom.mul(d, over)))
                b = shift(geom.add((p_high[0], p_high[1]), geom.mul(d, over)))
                out.append({"type": "line", "a": a, "b": b, "layer": "Mittellinie", "view": view})
    return out
