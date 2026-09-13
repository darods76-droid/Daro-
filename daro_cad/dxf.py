"""DXF-Export und -Import (AutoCAD R12 ASCII).

R12 ist das am breitesten unterstuetzte DXF-Format -- FreeCAD, LibreCAD,
QCAD, AutoCAD und Inkscape lesen es zuverlaessig.  Beim Import werden
zusaetzlich LWPOLYLINE und ELLIPSE aus neueren Versionen verstanden.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import geom, model, primitives
from .model import Document, LINETYPES, Point

# AutoCAD Color Index -> RGB (nur die gebraeuchlichen Farben).
ACI_RGB: Dict[int, Tuple[int, int, int]] = {
    1: (255, 0, 0), 2: (255, 255, 0), 3: (0, 255, 0), 4: (0, 255, 255),
    5: (0, 0, 255), 6: (255, 0, 255), 7: (0, 0, 0), 8: (128, 128, 128),
    9: (192, 192, 192), 30: (255, 127, 0), 40: (255, 191, 0),
    130: (127, 0, 255), 230: (255, 0, 127), 250: (51, 51, 51), 253: (153, 153, 153),
}

# Linienarten-Definitionen fuer die LTYPE-Tabelle (Muster in Zeichnungseinheiten).
DXF_LTYPES = {
    "CONTINUOUS": ("Durchgezogen", []),
    "DASHED": ("Strichlinie ___ ___ ___", [4.0, -2.0]),
    "DOTTED": ("Punktlinie . . . . .", [0.0, -1.6]),
    "CENTER": ("Strichpunktlinie ____ _ ____", [12.0, -2.0, 0.5, -2.0]),
    "PHANTOM": ("Strichzweipunkt ___ _ _ ___", [12.0, -2.0, 0.5, -2.0, 0.5, -2.0]),
}

LT_NAME = {"continuous": "CONTINUOUS", "dashed": "DASHED", "dotted": "DOTTED",
           "center": "CENTER", "phantom": "PHANTOM"}
LT_REVERSE = {v: k for k, v in LT_NAME.items()}


def hex_to_aci(color: str) -> int:
    try:
        c = color.lstrip("#")
        rgb = (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
    except (ValueError, IndexError):
        return 7
    best, best_d = 7, None
    for idx, ref in ACI_RGB.items():
        d = sum((a - b) ** 2 for a, b in zip(rgb, ref))
        if best_d is None or d < best_d:
            best, best_d = idx, d
    return best


class _Writer:
    def __init__(self) -> None:
        self.parts: List[str] = []

    def tag(self, code: int, value: Any) -> None:
        if isinstance(value, float):
            text = f"{value:.6f}"
        else:
            text = str(value)
        self.parts.append(f"{code}\n{text}\n")

    def tags(self, *pairs) -> None:
        for code, value in pairs:
            self.tag(code, value)

    def text(self) -> str:
        return "".join(self.parts)


def _lineweight_to_scale(lw: float) -> float:
    return 1.0


def export(doc: Document, explode_dimensions: bool = True, with_sheet: bool = True) -> str:
    """Zeichnung als DXF-R12-Text.

    Bemassungen werden in Linien, Pfeile (SOLID) und TEXT aufgeloest, damit sie
    in jedem Zielprogramm identisch aussehen.
    """
    w = _Writer()
    minx, miny, maxx, maxy = doc.bbox() or (0.0, 0.0, 100.0, 100.0)

    # ---- HEADER -------------------------------------------------------
    w.tags((0, "SECTION"), (2, "HEADER"))
    w.tags((9, "$ACADVER"), (1, "AC1009"))
    w.tags((9, "$INSUNITS"), (70, 4))                 # 4 = Millimeter
    w.tags((9, "$DWGCODEPAGE"), (3, "ANSI_1252"))
    w.tags((9, "$EXTMIN"), (10, float(minx)), (20, float(miny)), (30, 0.0))
    w.tags((9, "$EXTMAX"), (10, float(maxx)), (20, float(maxy)), (30, 0.0))
    w.tags((9, "$LTSCALE"), (40, 1.0 / max(1e-6, doc.scale_factor)))
    w.tags((9, "$TEXTSTYLE"), (7, "STANDARD"))
    w.tag(0, "ENDSEC")

    # ---- TABLES -------------------------------------------------------
    w.tags((0, "SECTION"), (2, "TABLES"))

    w.tags((0, "TABLE"), (2, "LTYPE"), (70, len(DXF_LTYPES)))
    for name, (descr, pattern) in DXF_LTYPES.items():
        total = sum(abs(v) for v in pattern)
        w.tags((0, "LTYPE"), (2, name), (70, 0), (3, descr), (72, 65),
               (73, len(pattern)), (40, float(total)))
        for value in pattern:
            w.tag(49, float(value))
    w.tag(0, "ENDTAB")

    sheet_layer = model.Layer("Rahmen", color="#111111", lineweight=model.NARROW)
    table_layers = list(doc.layers) + ([sheet_layer] if with_sheet else [])
    w.tags((0, "TABLE"), (2, "LAYER"), (70, len(table_layers)))
    for lay in table_layers:
        w.tags((0, "LAYER"), (2, lay.name), (70, 0 if lay.visible else 1),
               (62, hex_to_aci(lay.color) * (1 if lay.visible else -1)),
               (6, LT_NAME.get(lay.linetype, "CONTINUOUS")))
    w.tag(0, "ENDTAB")

    w.tags((0, "TABLE"), (2, "STYLE"), (70, 1))
    w.tags((0, "STYLE"), (2, "STANDARD"), (70, 0), (40, 0.0), (41, 0.85), (50, 0.0),
           (71, 0), (42, 3.5), (3, "isocp.shx"), (4, ""))
    w.tag(0, "ENDTAB")
    w.tag(0, "ENDSEC")

    # ---- ENTITIES -----------------------------------------------------
    w.tags((0, "SECTION"), (2, "ENTITIES"))
    for e in doc.visible_entities(for_print=True):
        _write_entity(w, doc, e, explode_dimensions)
    if with_sheet:
        _write_sheet(w, doc)
    w.tag(0, "ENDSEC")
    w.tag(0, "EOF")
    return w.text()


def _common(w: _Writer, layer: str, linetype: Optional[str] = None) -> None:
    w.tag(8, layer or "0")
    if linetype:
        w.tag(6, LT_NAME.get(linetype, "CONTINUOUS"))


def _write_entity(w: _Writer, doc: Document, e: Dict[str, Any], explode_dims: bool) -> None:
    t = e["type"]
    layer = e.get("layer", "0")
    lt = e.get("linetype")

    if t == "line":
        w.tag(0, "LINE"); _common(w, layer, lt)
        w.tags((10, float(e["a"][0])), (20, float(e["a"][1])), (30, 0.0),
               (11, float(e["b"][0])), (21, float(e["b"][1])), (31, 0.0))
    elif t == "circle":
        w.tag(0, "CIRCLE"); _common(w, layer, lt)
        w.tags((10, float(e["c"][0])), (20, float(e["c"][1])), (30, 0.0), (40, float(e["r"])))
    elif t == "arc":
        w.tag(0, "ARC"); _common(w, layer, lt)
        w.tags((10, float(e["c"][0])), (20, float(e["c"][1])), (30, 0.0), (40, float(e["r"])),
               (50, float(e["start"])), (51, float(e["end"])))
    elif t == "polyline":
        _write_polyline(w, layer, e["pts"], e.get("bulges"), e.get("closed", False), lt)
    elif t == "text":
        _write_text(w, layer, e["p"], e["h"], e["text"], e.get("rot", 0.0), e.get("align", "left"))
    elif t == "point":
        w.tag(0, "POINT"); _common(w, layer)
        w.tags((10, float(e["p"][0])), (20, float(e["p"][1])), (30, 0.0))
    elif t == "ellipse":
        # R12 kennt keine ELLIPSE -- als Polylinie schreiben, wie bei Schraffuren
        pts = model.ellipse_points(e)
        closed = abs(e["end"] - e["start"]) >= 359.999
        _write_polyline(w, layer, pts[:-1] if closed else pts, None, closed, lt)
    elif t in ("hatch", "dim", "leader", "surface", "fcf"):
        for prim in primitives.entity_primitives(doc, e):
            _write_primitive(w, layer, prim)
    elif t == "insert":
        # R12-INSERT waere kuerzer, aber aufgeloest sieht der Block in jedem
        # Zielprogramm gleich aus -- dieselbe Linie wie bei der Bemassung.
        for sub in doc.resolve_insert(e):
            lay = doc.layer(sub.get("layer", ""))
            if not lay.visible or not lay.printable:
                continue
            _write_entity(w, doc, sub, explode_dims)


def _write_polyline(w: _Writer, layer: str, pts: Sequence[Point],
                    bulges: Optional[Sequence[float]] = None, closed: bool = False,
                    lt: Optional[str] = None) -> None:
    if len(pts) < 2:
        return
    w.tag(0, "POLYLINE"); _common(w, layer, lt)
    w.tags((66, 1), (10, 0.0), (20, 0.0), (30, 0.0), (70, 1 if closed else 0))
    for i, p in enumerate(pts):
        w.tag(0, "VERTEX"); w.tag(8, layer or "0")
        w.tags((10, float(p[0])), (20, float(p[1])), (30, 0.0))
        if bulges and i < len(bulges) and abs(bulges[i]) > 1e-12:
            w.tag(42, float(bulges[i]))
    w.tag(0, "SEQEND"); w.tag(8, layer or "0")


_ALIGN_CODE = {"left": 0, "center": 1, "right": 2, "start": 0, "middle": 1, "end": 2}


def _write_text(w: _Writer, layer: str, p: Point, h: float, text: str,
                rot: float = 0.0, align: str = "left") -> None:
    code = _ALIGN_CODE.get(align, 0)
    w.tag(0, "TEXT"); _common(w, layer)
    w.tags((10, float(p[0])), (20, float(p[1])), (30, 0.0), (40, float(h)), (1, text),
           (50, float(rot)), (7, "STANDARD"), (72, code))
    if code:
        w.tags((11, float(p[0])), (21, float(p[1])), (31, 0.0))


def _write_solid(w: _Writer, layer: str, pts: Sequence[Point]) -> None:
    """Gefuelltes Dreieck/Viereck (Bemassungspfeil)."""
    q = list(pts)[:4]
    while len(q) < 4:
        q.append(q[-1])
    # DXF-SOLID erwartet die Punkte in Z-Reihenfolge, nicht umlaufend
    order = [q[0], q[1], q[3], q[2]]
    w.tag(0, "SOLID"); _common(w, layer)
    for i, p in enumerate(order):
        w.tags((10 + i, float(p[0])), (20 + i, float(p[1])), (30 + i, 0.0))


def _write_primitive(w: _Writer, layer: str, prim: Dict[str, Any]) -> None:
    k = prim.get("k")
    lt = prim.get("lt", "continuous")
    if k == "line":
        w.tag(0, "LINE"); _common(w, layer, lt)
        w.tags((10, float(prim["a"][0])), (20, float(prim["a"][1])), (30, 0.0),
               (11, float(prim["b"][0])), (21, float(prim["b"][1])), (31, 0.0))
    elif k == "poly":
        _write_polyline(w, layer, prim["pts"], None, prim.get("close", False), lt)
    elif k == "circle":
        w.tag(0, "CIRCLE"); _common(w, layer, lt)
        w.tags((10, float(prim["c"][0])), (20, float(prim["c"][1])), (30, 0.0),
               (40, float(prim["r"])))
    elif k == "arc":
        w.tag(0, "ARC"); _common(w, layer, lt)
        w.tags((10, float(prim["c"][0])), (20, float(prim["c"][1])), (30, 0.0),
               (40, float(prim["r"])), (50, float(prim["start"])), (51, float(prim["end"])))
    elif k == "fill":
        _write_solid(w, layer, prim["pts"])
    elif k == "text":
        _write_text(w, layer, prim["p"], prim["h"], prim["text"],
                    prim.get("rot", 0.0), prim.get("anchor", "start"))


def _write_sheet(w: _Writer, doc: Document) -> None:
    for prim in primitives.sheet_primitives(doc):
        _write_primitive(w, "Rahmen", prim)


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def _pairs(text: str) -> List[Tuple[int, str]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: List[Tuple[int, str]] = []
    for i in range(0, len(lines) - 1, 2):
        raw = lines[i].strip()
        if not raw:
            continue
        try:
            code = int(raw)
        except ValueError:
            continue
        out.append((code, lines[i + 1]))
    return out


def _num(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except ValueError:
        return default


def load(text: str) -> Document:
    """DXF einlesen.  Unbekannte Entitaeten werden uebersprungen."""
    doc = Document()
    doc.entities = []
    pairs = _pairs(text)

    layers: Dict[str, Dict[str, Any]] = {}
    entities: List[Dict[str, Any]] = []
    section = ""
    table = ""
    current: Optional[Dict[str, Any]] = None
    kind = ""
    vertices: List[Dict[str, Any]] = []
    poly: Optional[Dict[str, Any]] = None

    def flush() -> None:
        nonlocal current, kind, poly, vertices
        if current is None:
            current = None
            return
        ent = _build_entity(kind, current, vertices, poly)
        if ent:
            entities.append(ent)
        current = None
        kind = ""

    for code, value in pairs:
        if code == 0:
            name = value.strip().upper()
            if name in ("SECTION", "ENDSEC", "TABLE", "ENDTAB", "EOF"):
                if name in ("ENDSEC", "EOF", "ENDTAB"):
                    if kind in ("POLYLINE",) and name != "ENDTAB":
                        pass
                    flush()
                    if name == "ENDSEC":
                        section = ""
                continue
            if section == "TABLES":
                if name == "LAYER":
                    current = {}
                    kind = "LAYER"
                continue
            if section != "ENTITIES":
                continue
            if name == "VERTEX" and poly is not None:
                if current and kind == "VERTEX":
                    vertices.append(current)
                current = {}
                kind = "VERTEX"
                continue
            if name == "SEQEND":
                if current and kind == "VERTEX":
                    vertices.append(current)
                current = None
                if poly is not None:
                    ent = _build_polyline(poly, vertices)
                    if ent:
                        entities.append(ent)
                poly = None
                vertices = []
                kind = ""
                continue
            if current and kind == "VERTEX":
                vertices.append(current)
                current = None
            if kind and kind != "VERTEX":
                flush()
            if name == "POLYLINE":
                poly = {}
                current = poly
                kind = "POLYLINE"
                vertices = []
                continue
            current = {}
            kind = name
            continue

        if code == 2 and current is None:
            table = value.strip().upper()
            if section == "":
                section = value.strip().upper()
            continue
        if current is None:
            continue
        if kind == "LAYER":
            if code == 2:
                current["name"] = value.strip()
            elif code == 62:
                current["color"] = int(_num(value, 7))
            elif code == 6:
                current["linetype"] = value.strip().upper()
            if code == 6 or code == 62:
                if current.get("name"):
                    layers[current["name"]] = dict(current)
            continue
        current.setdefault("_tags", []).append((code, value))

    flush()

    # Layer uebernehmen
    if layers:
        doc.layers = []
        for name, info in layers.items():
            aci = abs(int(info.get("color", 7)))
            rgb = ACI_RGB.get(aci, (17, 17, 17))
            doc.layers.append(model.Layer(
                name=name,
                color="#%02x%02x%02x" % rgb,
                linetype=LT_REVERSE.get(info.get("linetype", "CONTINUOUS"), "continuous"),
                lineweight=model.WIDE if "kontur" in name.lower() else model.NARROW,
                visible=int(info.get("color", 7)) >= 0,
            ))
    if not doc.layers:
        doc.layers = [model.Layer("0")]

    known = set(doc.layer_names())
    for ent in entities:
        if ent.get("layer") not in known:
            ent["layer"] = doc.layers[0].name
        try:
            doc.entities.append(model.normalize_entity(ent, doc.layers[0].name))
        except ValueError:
            continue
    return doc


def _tagmap(tags: List[Tuple[int, str]]) -> Dict[int, List[str]]:
    out: Dict[int, List[str]] = {}
    for code, value in tags:
        out.setdefault(code, []).append(value)
    return out


def _get(tm: Dict[int, List[str]], code: int, default: float = 0.0, index: int = 0) -> float:
    values = tm.get(code)
    if not values or index >= len(values):
        return default
    return _num(values[index], default)


def _build_entity(kind: str, data: Dict[str, Any], vertices, poly) -> Optional[Dict[str, Any]]:
    if not kind or kind in ("LAYER", "VERTEX", "POLYLINE"):
        return None
    tm = _tagmap(data.get("_tags", []))
    layer = (tm.get(8) or ["0"])[0].strip()
    lt = LT_REVERSE.get((tm.get(6) or ["CONTINUOUS"])[0].strip().upper())

    def base(ent: Dict[str, Any]) -> Dict[str, Any]:
        ent["layer"] = layer
        if lt and lt != "continuous":
            ent["linetype"] = lt
        return ent

    if kind == "LINE":
        return base({"type": "line",
                     "a": (_get(tm, 10), _get(tm, 20)),
                     "b": (_get(tm, 11), _get(tm, 21))})
    if kind == "CIRCLE":
        return base({"type": "circle", "c": (_get(tm, 10), _get(tm, 20)), "r": _get(tm, 40, 1.0)})
    if kind == "ARC":
        return base({"type": "arc", "c": (_get(tm, 10), _get(tm, 20)), "r": _get(tm, 40, 1.0),
                     "start": _get(tm, 50), "end": _get(tm, 51, 90.0)})
    if kind == "LWPOLYLINE":
        xs = [_num(v) for v in tm.get(10, [])]
        ys = [_num(v) for v in tm.get(20, [])]
        pts = list(zip(xs, ys))
        if len(pts) < 2:
            return None
        flags = int(_get(tm, 70))
        bulges = [_num(v) for v in tm.get(42, [])]
        if bulges and len(bulges) != len(pts):
            bulges = []          # Bulges ohne Zuordnung lieber verwerfen
        return base({"type": "polyline", "pts": pts, "closed": bool(flags & 1),
                     "bulges": bulges})
    if kind in ("TEXT", "MTEXT"):
        text = (tm.get(1) or [""])[0]
        if kind == "MTEXT":
            text = text.replace("\\P", " ")
            for token in ("\\A1;", "\\A0;", "{", "}"):
                text = text.replace(token, "")
        align = int(_get(tm, 72))
        px, py = _get(tm, 10), _get(tm, 20)
        if align and tm.get(11):
            px, py = _get(tm, 11), _get(tm, 21)
        return base({"type": "text", "p": (px, py), "h": _get(tm, 40, 3.5) or 3.5,
                     "text": text, "rot": _get(tm, 50),
                     "align": {0: "left", 1: "center", 2: "right"}.get(align, "left")})
    if kind == "POINT":
        return base({"type": "point", "p": (_get(tm, 10), _get(tm, 20))})
    if kind == "ELLIPSE":
        # Als Polylinie annaehern -- ausreichend fuer den Import
        c = (_get(tm, 10), _get(tm, 20))
        major = (_get(tm, 11), _get(tm, 21))
        ratio = _get(tm, 40, 1.0)
        start, end = _get(tm, 41, 0.0), _get(tm, 42, 2 * math.pi)
        a = geom.length(major)
        b = a * ratio
        rot = geom.angle_of(major)
        pts = []
        steps = 64
        for i in range(steps + 1):
            t = start + (end - start) * i / steps
            p = (a * math.cos(t), b * math.sin(t))
            pts.append(geom.add(c, geom.rotate(p, rot)))
        return base({"type": "polyline", "pts": pts, "closed": abs(end - start) >= 2 * math.pi - 1e-6})
    return None


def _build_polyline(poly: Dict[str, Any], vertices: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    tm = _tagmap(poly.get("_tags", []))
    layer = (tm.get(8) or ["0"])[0].strip()
    flags = int(_get(tm, 70))
    pts: List[Point] = []
    bulges: List[float] = []
    for v in vertices:
        vt = _tagmap(v.get("_tags", []))
        pts.append((_get(vt, 10), _get(vt, 20)))
        bulges.append(_get(vt, 42))
    if len(pts) < 2:
        return None
    ent = {"type": "polyline", "pts": pts, "closed": bool(flags & 1), "layer": layer}
    if any(abs(b) > 1e-12 for b in bulges):
        ent["bulges"] = bulges
    lt = LT_REVERSE.get((tm.get(6) or ["CONTINUOUS"])[0].strip().upper())
    if lt and lt != "continuous":
        ent["linetype"] = lt
    return ent
