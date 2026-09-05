"""Zeichnung in flache Zeichenprimitive uebersetzen.

Alle Exporter (SVG, PDF, DXF-Bemassung) arbeiten auf demselben Primitivstrom,
damit Blattrahmen, Schriftfeld und Bemassung ueberall identisch aussehen.

Primitive (Modellkoordinaten, mm):
    {"k": "line",  "a", "b"}
    {"k": "poly",  "pts", "close"}
    {"k": "circle","c", "r"}
    {"k": "arc",   "c", "r", "start", "end"}
    {"k": "fill",  "pts"}                       -- gefuelltes Polygon (Pfeilspitze)
    {"k": "text",  "p", "h", "text", "rot", "anchor", "valign"}
Gemeinsame Attribute: ``color``, ``lw`` (Papier-mm), ``lt`` (Linienart).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import geom, model
from .model import Document, Point

# Papierbezogene Konstanten nach DIN ISO 129-1 (Bemassung).
ARROW_LEN = 3.5          # Pfeillaenge in mm
ARROW_W = 1.2            # Pfeilbreite in mm
EXT_GAP = 0.8            # Abstand Kontur -> Massshilfslinie
EXT_OVER = 2.0           # Ueberstand ueber die Masslinie
TEXT_GAP = 1.0           # Abstand Masszahl -> Masslinie
FRAME_LW = 0.7           # Rahmenlinie
SHEET_LW = 0.25


def _line(a: Point, b: Point, color: str, lw: float, lt: str = "continuous") -> Dict[str, Any]:
    return {"k": "line", "a": a, "b": b, "color": color, "lw": lw, "lt": lt}


def _text(p: Point, h: float, text: str, color: str = "#111111", rot: float = 0.0,
          anchor: str = "start", valign: str = "base", lw: float = 0.25) -> Dict[str, Any]:
    return {"k": "text", "p": p, "h": h, "text": text, "color": color, "rot": rot,
            "anchor": anchor, "valign": valign, "lw": lw, "lt": "continuous"}


def format_value(value: float, decimals: int = 1, comma: bool = True) -> str:
    txt = f"{value:.{max(0, decimals)}f}"
    if "." in txt:
        txt = txt.rstrip("0").rstrip(".")
    if txt in ("", "-0"):
        txt = "0"
    return txt.replace(".", ",") if comma else txt


# ---------------------------------------------------------------------------
# Bemassung
# ---------------------------------------------------------------------------

def arrow(tip: Point, direction: Point, size: float, color: str) -> Dict[str, Any]:
    """Gefuellte Pfeilspitze; ``direction`` zeigt von der Spitze weg."""
    d = geom.normalize(direction)
    if d == (0.0, 0.0):
        d = (1.0, 0.0)
    base = geom.add(tip, geom.mul(d, size))
    off = geom.mul(geom.perp(d), size * ARROW_W / ARROW_LEN)
    return {"k": "fill", "pts": [tip, geom.add(base, off), geom.sub(base, off)],
            "color": color, "lw": 0, "lt": "continuous"}


def dim_measure(dim: Dict[str, Any]) -> float:
    """Der gemessene Wert (mm bzw. Grad)."""
    p1, p2 = dim["p1"], dim["p2"]
    kind = dim.get("kind", "linear")
    if kind == "linear":
        axis = dim.get("axis", "auto")
        if axis == "auto":
            axis = "x" if abs(p2[0] - p1[0]) >= abs(p2[1] - p1[1]) else "y"
        return abs(p2[0] - p1[0]) if axis == "x" else abs(p2[1] - p1[1])
    if kind == "aligned":
        return geom.dist(p1, p2)
    if kind in ("radius", "diameter"):
        r = geom.dist(p1, p2)
        return r * 2.0 if kind == "diameter" else r
    if kind == "angular":
        c = dim.get("center", (0.0, 0.0))
        a1 = geom.angle_of(geom.sub(p1, c))
        a2 = geom.angle_of(geom.sub(p2, c))
        sweep = geom.norm_angle(a2 - a1)
        return sweep if sweep <= 180.0 else 360.0 - sweep
    return 0.0


def dim_text(dim: Dict[str, Any], comma: bool = True) -> str:
    if dim.get("text"):
        return str(dim["text"])
    kind = dim.get("kind", "linear")
    value = dim_measure(dim)
    decimals = int(dim.get("decimals", 1))
    txt = format_value(value, decimals, comma)
    if kind == "angular":
        return txt + "°"
    prefix = dim.get("prefix") or ""
    if kind == "diameter" and "Ø" not in prefix:
        prefix = "Ø" + prefix
    elif kind == "radius" and not prefix.startswith("R"):
        prefix = "R" + prefix
    return f"{prefix}{txt}{dim.get('suffix') or ''}"


def dim_primitives(dim: Dict[str, Any], color: str, lw: float, scale: float,
                   comma: bool = True) -> List[Dict[str, Any]]:
    """Bemassung in Linien, Pfeile und Text aufloesen."""
    def paper(v: float) -> float:      # Papier-mm -> Modell-mm
        return v / scale

    out: List[Dict[str, Any]] = []
    kind = dim.get("kind", "linear")
    p1, p2, pos = dim["p1"], dim["p2"], dim["pos"]
    h = paper(float(dim.get("h", 3.5)))
    arrow_len = paper(ARROW_LEN)
    label = dim_text(dim, comma)

    if kind in ("linear", "aligned"):
        if kind == "aligned":
            direction = geom.normalize(geom.sub(p2, p1)) or (1.0, 0.0)
        else:
            axis = dim.get("axis", "auto")
            if axis == "auto":
                axis = "x" if abs(p2[0] - p1[0]) >= abs(p2[1] - p1[1]) else "y"
            direction = (1.0, 0.0) if axis == "x" else (0.0, 1.0)
        normal = geom.perp(direction)
        # Abstand der Masslinie von p1 entlang der Normalen
        offset = geom.dot(geom.sub(pos, p1), normal)
        d1 = geom.add(p1, geom.mul(normal, offset))
        d2 = geom.add(p2, geom.mul(normal, offset))
        # Auf die Masslinien-Richtung projizieren (linear misst nur eine Achse)
        d2 = geom.add(d1, geom.mul(direction, geom.dot(geom.sub(d2, d1), direction)))

        sign = 1.0 if offset >= 0 else -1.0
        for base, tip in ((p1, d1), (p2, d2)):
            gap = geom.mul(normal, sign * paper(EXT_GAP))
            over = geom.mul(normal, sign * paper(EXT_OVER))
            start = geom.add(base, gap)
            end = geom.add(tip, over)
            if geom.dist(start, end) > 1e-6:
                out.append(_line(start, end, color, lw))

        length = geom.dist(d1, d2)
        inside = length > 3.0 * arrow_len
        if inside:
            out.append(_line(d1, d2, color, lw))
            out.append(arrow(d1, geom.sub(d2, d1), arrow_len, color))
            out.append(arrow(d2, geom.sub(d1, d2), arrow_len, color))
        else:
            # Enge Masse: Pfeile aussen, Masslinie ueber die Masshilfslinien hinaus
            ext = geom.mul(direction, arrow_len * 2.0)
            out.append(_line(geom.sub(d1, ext), geom.add(d2, ext), color, lw))
            out.append(arrow(d1, geom.mul(direction, -1.0), arrow_len, color))
            out.append(arrow(d2, direction, arrow_len, color))

        mid = geom.lerp(d1, d2, 0.5)
        rot = geom.angle_of(direction)
        if 90.0 < rot <= 270.0:
            rot -= 180.0                     # Masszahl nie auf dem Kopf
        text_normal = geom.perp(geom.polar((0, 0), rot, 1.0))
        anchor_pt = geom.add(mid, geom.mul(text_normal, paper(TEXT_GAP)))
        if not inside:
            anchor_pt = geom.add(anchor_pt, geom.mul(direction, arrow_len * 3.0))
        out.append(_text(anchor_pt, h, label, color, rot, "middle", "base"))
        return out

    if kind in ("radius", "diameter"):
        center, on_circle = p1, p2
        radius = geom.dist(center, on_circle)
        direction = geom.normalize(geom.sub(on_circle, center)) or (1.0, 0.0)
        # Bei kleinen Bohrungen ist im Kreis kein Platz fuer Masslinie und Pfeile;
        # dann nur die Hinweislinie mit einem Pfeil von aussen (ISO 129-1).
        roomy = radius >= 1.6 * arrow_len
        if roomy:
            if kind == "diameter":
                opposite = geom.sub(center, geom.mul(direction, radius))
                out.append(_line(opposite, on_circle, color, lw))
                out.append(arrow(opposite, direction, arrow_len, color))
            else:
                out.append(_line(center, on_circle, color, lw))
            out.append(arrow(on_circle, geom.mul(direction, -1.0), arrow_len, color))
        else:
            out.append(arrow(on_circle, direction, arrow_len, color))
        # Hinweislinie zur Masszahl mit waagerechtem Auslauf
        out.append(_line(on_circle, pos, color, lw))
        side = 1.0 if pos[0] >= center[0] else -1.0
        tail = geom.add(pos, (side * h * 1.5, 0.0))
        out.append(_line(pos, tail, color, lw))
        anchor = "start" if side > 0 else "end"
        text_pt = geom.add(tail, (side * paper(TEXT_GAP), paper(TEXT_GAP)))
        out.append(_text(text_pt, h, label, color, 0.0, anchor, "base"))
        return out

    if kind == "angular":
        c = dim.get("center", (0.0, 0.0))
        a1 = geom.angle_of(geom.sub(p1, c))
        a2 = geom.angle_of(geom.sub(p2, c))
        if geom.norm_angle(a2 - a1) > 180.0:
            a1, a2 = a2, a1
        radius = geom.dist(c, pos)
        r1, r2 = geom.dist(c, p1), geom.dist(c, p2)
        for ang, rr in ((a1, r1), (a2, r2)):
            far = max(radius + paper(EXT_OVER), rr)
            out.append(_line(geom.polar(c, ang, min(rr, radius)),
                             geom.polar(c, ang, far), color, lw))
        out.append({"k": "arc", "c": c, "r": radius, "start": a1, "end": a2,
                    "color": color, "lw": lw, "lt": "continuous"})
        for ang, way in ((a1, 1.0), (a2, -1.0)):
            tip = geom.polar(c, ang, radius)
            tangent = geom.perp(geom.normalize(geom.sub(tip, c)))
            out.append(arrow(tip, geom.mul(tangent, way), arrow_len, color))
        mid_angle = a1 + geom.norm_angle(a2 - a1) / 2.0
        text_pt = geom.polar(c, mid_angle, radius + paper(TEXT_GAP) + h * 0.3)
        out.append(_text(text_pt, h, label, color, 0.0, "middle", "base"))
        return out

    return out


# ---------------------------------------------------------------------------
# Schraffur
# ---------------------------------------------------------------------------

def hatch_lines(pts: Sequence[Point], angle_deg: float, spacing: float) -> List[Tuple[Point, Point]]:
    """Parallele Schnittlinien innerhalb eines geschlossenen Polygons."""
    if len(pts) < 3 or spacing <= 0:
        return []
    box = geom.bbox(pts)
    if not box:
        return []
    minx, miny, maxx, maxy = box
    center = ((minx + maxx) / 2.0, (miny + maxy) / 2.0)
    diag = geom.dist((minx, miny), (maxx, maxy)) / 2.0 + spacing
    direction = geom.polar((0.0, 0.0), angle_deg, 1.0)
    normal = geom.perp(direction)
    out: List[Tuple[Point, Point]] = []
    steps = int(diag / spacing) + 1
    for i in range(-steps, steps + 1):
        base = geom.add(center, geom.mul(normal, i * spacing))
        a = geom.sub(base, geom.mul(direction, diag))
        b = geom.add(base, geom.mul(direction, diag))
        hits: List[float] = []
        n = len(pts)
        for j in range(n):
            p = geom.line_line_intersection(a, b, pts[j], pts[(j + 1) % n], segment=False)
            if p is None:
                continue
            # Nur echte Treffer auf der Polygonkante zaehlen
            edge_a, edge_b = pts[j], pts[(j + 1) % n]
            if geom.dist(geom.closest_point_on_segment(p, edge_a, edge_b), p) > 1e-7:
                continue
            hits.append(geom.dot(geom.sub(p, a), direction))
        hits.sort()
        merged: List[float] = []
        for t in hits:
            if not merged or abs(merged[-1] - t) > 1e-7:
                merged.append(t)
        for k in range(0, len(merged) - 1, 2):
            s, e = merged[k], merged[k + 1]
            if e - s < 1e-9:
                continue
            mid = geom.add(a, geom.mul(direction, (s + e) / 2.0))
            if not geom.point_in_polygon(mid, pts):
                continue
            out.append((geom.add(a, geom.mul(direction, s)),
                        geom.add(a, geom.mul(direction, e))))
    return out


# ---------------------------------------------------------------------------
# Entitaeten -> Primitive
# ---------------------------------------------------------------------------

def entity_primitives(doc: Document, entity: Dict[str, Any]) -> List[Dict[str, Any]]:
    lay = doc.layer(entity.get("layer", ""))
    color = entity.get("color") or lay.color
    lw = float(entity.get("lineweight") or lay.lineweight)
    lt = entity.get("linetype") or lay.linetype
    scale = doc.scale_factor
    comma = bool(doc.meta.get("decimalComma", True))
    t = entity["type"]

    if t == "line":
        return [_line(entity["a"], entity["b"], color, lw, lt)]
    if t == "circle":
        return [{"k": "circle", "c": entity["c"], "r": entity["r"],
                 "color": color, "lw": lw, "lt": lt}]
    if t == "arc":
        return [{"k": "arc", "c": entity["c"], "r": entity["r"],
                 "start": entity["start"], "end": entity["end"],
                 "color": color, "lw": lw, "lt": lt}]
    if t == "polyline":
        out = []
        for seg in model.polyline_segments(entity):
            if seg[0] == "line":
                out.append(_line(seg[1], seg[2], color, lw, lt))
            else:
                out.append({"k": "arc", "c": seg[1], "r": seg[2], "start": seg[3],
                            "end": seg[4], "color": color, "lw": lw, "lt": lt})
        return out
    if t == "text":
        anchor = {"left": "start", "center": "middle", "right": "end"}.get(
            entity.get("align", "left"), "start")
        return [_text(entity["p"], entity["h"], entity["text"], color,
                      entity.get("rot", 0.0), anchor, "base", lw)]
    if t == "point":
        p = entity["p"]
        d = 1.0 / scale
        return [_line((p[0] - d, p[1]), (p[0] + d, p[1]), color, lw),
                _line((p[0], p[1] - d), (p[0], p[1] + d), color, lw)]
    if t == "hatch":
        pts = model.outline_points(entity)
        spacing = float(entity.get("spacing", 3.0)) / scale
        return [_line(a, b, color, lw, "continuous")
                for a, b in hatch_lines(pts, entity.get("angle", 45.0), spacing)]
    if t == "dim":
        return dim_primitives(entity, color, lw, scale, comma)
    return []


def document_primitives(doc: Document, for_print: bool = True) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for e in doc.visible_entities(for_print=for_print):
        out.extend(entity_primitives(doc, e))
    return out


# ---------------------------------------------------------------------------
# Blattrahmen und Schriftfeld nach DIN EN ISO 5457 / 7200
# ---------------------------------------------------------------------------

def _cell(x: float, y: float, w: float, h: float, label: str, value: str,
          vh: float = 4.0, lh: float = 2.0) -> Dict[str, Any]:
    return {"x": x, "y": y, "w": w, "h": h, "label": label, "value": value,
            "vh": vh, "lh": lh}


def title_block_cells(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Zellenraster des Schriftfelds (Papier-mm, Ursprung unten links)."""
    sheet = meta.get("sheet", "A3")
    scale = meta.get("scale", "1:1")
    r = 63.0 / 6.0                       # sechs Zeilen a 10,5 mm
    left_w = 110.0
    return [
        _cell(0, 5 * r, left_w, r, "Firma / Verantwortliche Abteilung", meta.get("company", "")),
        _cell(0, 4 * r, 55, r, "Erstellt durch", meta.get("author", "")),
        _cell(55, 4 * r, 55, r, "Datum", meta.get("date", "")),
        _cell(0, 3 * r, 55, r, "Geprüft durch", meta.get("approvedBy", "")),
        _cell(55, 3 * r, 55, r, "Dokumentenart", meta.get("docType", "Technische Zeichnung")),
        _cell(0, 2 * r, left_w, r, "Werkstoff / Halbzeug", meta.get("material", "")),
        _cell(0, 1 * r, 55, r, "Allgemeintoleranz", meta.get("generalTolerance", "")),
        _cell(55, 1 * r, 55, r, "Oberfläche", meta.get("surface", "")),
        _cell(0, 0, 37, r, "Maßstab", scale),
        _cell(37, 0, 37, r, "Gewicht", meta.get("weight", "")),
        _cell(74, 0, 36, r, "Einheit", meta.get("units", "mm")),
        _cell(left_w, 4 * r, 70, 2 * r, "Benennung", meta.get("title", ""), vh=6.0),
        _cell(left_w, 2 * r, 70, 2 * r, "Zeichnungsnummer", meta.get("drawingNumber", ""), vh=7.0),
        _cell(left_w, 1 * r, 35, r, "Projektion", ""),
        _cell(left_w + 35, 1 * r, 35, r, "Format", sheet),
        _cell(left_w, 0, 35, r, "Revision", meta.get("revision", "")),
        _cell(left_w + 35, 0, 35, r, "Blatt", f"{meta.get('sheetName', '1')} / {meta.get('sheetCount', '1')}"),
    ]


def projection_symbol(cx: float, cy: float, size: float, first_angle: bool,
                      color: str, lw: float) -> List[Dict[str, Any]]:
    """Projektionssymbol (Kegelstumpf) nach DIN ISO 128-30.

    Konvention hier: Kegelstumpf mit kleiner Flaeche links.  Die Vorderansicht
    ist damit das Trapez, die Ansicht von links sind die konzentrischen Kreise.
    Bei Projektionsmethode 1 (Europa) wird die Ansicht von links rechts
    angeordnet -- Trapez links, Kreise rechts; bei Methode 3 umgekehrt.
    """
    out: List[Dict[str, Any]] = []
    r_out = size * 0.45
    r_in = size * 0.28
    gap = size * 0.75
    trap_w = size * 0.8
    h_big = r_out * 2.0
    h_small = r_in * 2.0

    circles_x = cx + gap if first_angle else cx - gap
    trap_x = cx - gap if first_angle else cx + gap

    out.append({"k": "circle", "c": (circles_x, cy), "r": r_out,
                "color": color, "lw": lw, "lt": "continuous"})
    out.append({"k": "circle", "c": (circles_x, cy), "r": r_in,
                "color": color, "lw": lw, "lt": "continuous"})
    x0 = trap_x - trap_w / 2.0
    x1 = trap_x + trap_w / 2.0
    out.append({"k": "poly", "close": True, "color": color, "lw": lw, "lt": "continuous",
                "pts": [(x0, cy - h_small / 2.0), (x0, cy + h_small / 2.0),
                        (x1, cy + h_big / 2.0), (x1, cy - h_big / 2.0)]})
    span = size * 1.9
    out.append(_line((cx - span / 2.0, cy), (cx + span / 2.0, cy), color, lw * 0.6, "center"))
    return out


def sheet_primitives(doc: Document) -> List[Dict[str, Any]]:
    """Blattrand, Zeichnungsrahmen und Schriftfeld -- in Modellkoordinaten."""
    scale = doc.scale_factor
    pw, ph = doc.sheet_size()
    color = "#111111"

    def P(x: float, y: float) -> Point:      # Papier-mm -> Modell-mm
        return (x / scale, y / scale)

    def rect(x, y, w, h, lw, lt="continuous"):
        pts = [P(x, y), P(x + w, y), P(x + w, y + h), P(x, y + h)]
        return {"k": "poly", "pts": pts, "close": True, "color": color, "lw": lw, "lt": lt}

    out: List[Dict[str, Any]] = [rect(0, 0, pw, ph, SHEET_LW)]

    left = 20.0 if pw >= 297.0 else 20.0      # Heftrand nach ISO 5457
    margin = 10.0
    fw = pw - left - margin
    fh = ph - 2 * margin
    out.append(rect(left, margin, fw, fh, FRAME_LW))

    # Schriftfeld unten rechts, buendig im Zeichnungsrahmen
    tb_x = left + fw - model.TITLE_BLOCK_W
    tb_y = margin
    out.append(rect(tb_x, tb_y, model.TITLE_BLOCK_W, model.TITLE_BLOCK_H, FRAME_LW))

    for cell in title_block_cells(doc.meta):
        x, y, w, h = cell["x"] + tb_x, cell["y"] + tb_y, cell["w"], cell["h"]
        out.append(rect(x, y, w, h, SHEET_LW))
        if cell["label"]:
            out.append(_text(P(x + 1.2, y + h - cell["lh"] - 0.8), cell["lh"] / scale,
                             cell["label"], "#555555", 0.0, "start", "base", SHEET_LW))
        value = str(cell["value"] or "")
        if value:
            # In hohen Zellen die Eintragung senkrecht mittig setzen
            vy = y + 1.6 if h <= 12.0 else y + (h - cell["vh"]) / 2.0
            out.append(_text(P(x + w / 2.0, vy), cell["vh"] / scale, value,
                             color, 0.0, "middle", "base", SHEET_LW))

    # Projektionssymbol in seine Zelle setzen
    for cell in title_block_cells(doc.meta):
        if cell["label"] != "Projektion":
            continue
        cx = tb_x + cell["x"] + cell["w"] / 2.0
        cy = tb_y + cell["y"] + cell["h"] / 2.0 - 1.0
        for prim in projection_symbol(cx, cy, 6.0,
                                      doc.meta.get("projection", "first") == "first",
                                      color, SHEET_LW):
            out.append(_scale_prim(prim, scale))
        break
    return out


def _scale_prim(prim: Dict[str, Any], scale: float) -> Dict[str, Any]:
    """Ein in Papier-mm erzeugtes Primitiv nach Modell-mm umrechnen."""
    p = dict(prim)
    conv = lambda pt: (pt[0] / scale, pt[1] / scale)
    if "a" in p:
        p["a"] = conv(p["a"])
    if "b" in p:
        p["b"] = conv(p["b"])
    if "c" in p:
        p["c"] = conv(p["c"])
    if "p" in p:
        p["p"] = conv(p["p"])
    if "r" in p:
        p["r"] = p["r"] / scale
    if "h" in p and p.get("k") == "text":
        p["h"] = p["h"] / scale
    if "pts" in p:
        p["pts"] = [conv(pt) for pt in p["pts"]]
    return p
