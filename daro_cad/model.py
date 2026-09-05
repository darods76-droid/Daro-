"""Dokumentmodell von DARO-CAD.

Eine Zeichnung ist ein einfaches, JSON-serialisierbares Dokument.  Genau dieses
Format tauscht das Browser-Frontend mit dem Python-Kern aus, dadurch gibt es nur
eine einzige Wahrheit fuer Geometrie, Layer und Schriftfeld.

Entitaeten sind bewusst Dictionaries statt Klassen -- so wandern sie ohne
Konvertierung zwischen JavaScript, JSON-Datei und Exportern.
"""

from __future__ import annotations

import copy
import json
import math
import uuid
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import geom

Point = Tuple[float, float]

FORMAT_VERSION = 1

# ---------------------------------------------------------------------------
# Linienarten nach DIN ISO 128-20.  Muster in mm auf dem Papier (Blattmassstab).
# ---------------------------------------------------------------------------
LINETYPES: Dict[str, List[float]] = {
    "continuous": [],
    "dashed": [4.0, 2.0],
    "dotted": [0.4, 1.6],
    "center": [12.0, 2.0, 2.0, 2.0],
    "phantom": [12.0, 2.0, 2.0, 2.0, 2.0, 2.0],
}

# Liniengruppe 0,5 nach DIN ISO 128-20: breit 0,5 mm / schmal 0,25 mm.
WIDE = 0.5
NARROW = 0.25

DEFAULT_LAYERS: List[Dict[str, Any]] = [
    {"name": "Kontur",     "color": "#111111", "lineweight": WIDE,   "linetype": "continuous"},
    {"name": "Verdeckt",   "color": "#8a6d3b", "lineweight": NARROW, "linetype": "dashed"},
    {"name": "Mittellinie", "color": "#b03060", "lineweight": NARROW, "linetype": "center"},
    {"name": "Bemassung",  "color": "#1c6ea4", "lineweight": NARROW, "linetype": "continuous"},
    {"name": "Schraffur",  "color": "#4a7f4a", "lineweight": NARROW, "linetype": "continuous"},
    {"name": "Hilfslinie", "color": "#999999", "lineweight": NARROW, "linetype": "continuous",
     "printable": False},
    {"name": "Text",       "color": "#111111", "lineweight": NARROW, "linetype": "continuous"},
]

# Blattformate nach DIN EN ISO 5457 (Breite x Hoehe in mm, Querformat).
SHEETS: Dict[str, Tuple[float, float]] = {
    "A4": (210.0, 297.0),      # Hochformat -- Sonderfall, siehe sheet_size()
    "A4L": (297.0, 210.0),
    "A3": (420.0, 297.0),
    "A2": (594.0, 420.0),
    "A1": (841.0, 594.0),
    "A0": (1189.0, 841.0),
}

# Massstaebe nach DIN ISO 5455.
SCALES = ["50:1", "20:1", "10:1", "5:1", "2:1", "1:1", "1:2", "1:2.5", "1:5",
          "1:10", "1:20", "1:50", "1:100", "1:200", "1:500", "1:1000"]

TITLE_BLOCK_W = 180.0
TITLE_BLOCK_H = 63.0


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def parse_scale(text: str) -> float:
    """``"1:2"`` -> 0.5.  Der Faktor rechnet Modell-mm in Papier-mm um."""
    try:
        if ":" in text:
            a, b = text.split(":", 1)
            return float(a) / float(b)
        return float(text)
    except (ValueError, ZeroDivisionError):
        return 1.0


def sheet_size(name: str, landscape: bool = True) -> Tuple[float, float]:
    w, h = SHEETS.get(name, SHEETS["A3"])
    if name == "A4" and landscape:
        # A4 wird im Maschinenbau meist hoch verwendet -- explizit "A4L" waehlen.
        return (w, h)
    if landscape and h > w:
        return (h, w)
    return (w, h)


class Layer:
    __slots__ = ("name", "color", "lineweight", "linetype", "visible", "locked", "printable")

    def __init__(self, name: str, color: str = "#111111", lineweight: float = NARROW,
                 linetype: str = "continuous", visible: bool = True, locked: bool = False,
                 printable: bool = True):
        self.name = name
        self.color = color
        self.lineweight = float(lineweight)
        self.linetype = linetype if linetype in LINETYPES else "continuous"
        self.visible = bool(visible)
        self.locked = bool(locked)
        self.printable = bool(printable)

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in self.__slots__}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Layer":
        return cls(
            name=d.get("name", "0"),
            color=d.get("color", "#111111"),
            lineweight=d.get("lineweight", NARROW),
            linetype=d.get("linetype", "continuous"),
            visible=d.get("visible", True),
            locked=d.get("locked", False),
            printable=d.get("printable", True),
        )


DEFAULT_META: Dict[str, Any] = {
    "title": "Bauteil",
    "subtitle": "",
    "drawingNumber": "0001",
    "revision": "0",
    "date": "",
    "author": "",
    "approvedBy": "",
    "company": "",
    "material": "S235JR",
    "weight": "",
    "scale": "1:1",
    "sheet": "A3",
    "landscape": True,
    "sheetName": "1",
    "sheetCount": "1",
    "projection": "first",          # first = europaeische Projektion (DIN)
    "generalTolerance": "ISO 2768-m",
    "surface": "",
    "units": "mm",
}


class Document:
    """Eine Zeichnung: Layer, Entitaeten, extrudierte Koerper und Schriftfeld."""

    def __init__(self) -> None:
        self.meta: Dict[str, Any] = dict(DEFAULT_META)
        self.layers: List[Layer] = [Layer(**d) for d in copy.deepcopy(DEFAULT_LAYERS)]
        self.entities: List[Dict[str, Any]] = []
        self.solids: List[Dict[str, Any]] = []

    # -- Layer ------------------------------------------------------------
    def layer(self, name: str) -> Layer:
        for lay in self.layers:
            if lay.name == name:
                return lay
        return self.layers[0]

    def layer_names(self) -> List[str]:
        return [lay.name for lay in self.layers]

    # -- Entitaeten -------------------------------------------------------
    def add(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        entity = normalize_entity(entity, default_layer=self.layers[0].name)
        self.entities.append(entity)
        return entity

    def by_id(self, eid: str) -> Optional[Dict[str, Any]]:
        for e in self.entities:
            if e.get("id") == eid:
                return e
        return None

    def visible_entities(self, for_print: bool = False) -> List[Dict[str, Any]]:
        out = []
        for e in self.entities:
            lay = self.layer(e.get("layer", ""))
            if not lay.visible:
                continue
            if for_print and not lay.printable:
                continue
            out.append(e)
        return out

    # -- Kennzahlen -------------------------------------------------------
    @property
    def scale_factor(self) -> float:
        return parse_scale(self.meta.get("scale", "1:1"))

    def sheet_size(self) -> Tuple[float, float]:
        return sheet_size(self.meta.get("sheet", "A3"), self.meta.get("landscape", True))

    def sheet_size_model(self) -> Tuple[float, float]:
        """Blattgroesse in Modellkoordinaten (Papier / Massstab)."""
        w, h = self.sheet_size()
        s = self.scale_factor
        return (w / s, h / s)

    def bbox(self):
        pts: List[Point] = []
        for e in self.entities:
            pts.extend(entity_points(e))
        return geom.bbox(pts)

    # -- Serialisierung ---------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": FORMAT_VERSION,
            "meta": self.meta,
            "layers": [lay.to_dict() for lay in self.layers],
            "entities": self.entities,
            "solids": self.solids,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Document":
        doc = cls()
        meta = dict(DEFAULT_META)
        meta.update(data.get("meta") or {})
        doc.meta = meta
        layers = data.get("layers")
        if layers:
            doc.layers = [Layer.from_dict(d) for d in layers]
        if not doc.layers:
            doc.layers = [Layer("Kontur", lineweight=WIDE)]
        default_layer = doc.layers[0].name
        known = set(doc.layer_names())
        doc.entities = []
        for e in data.get("entities") or []:
            ent = normalize_entity(e, default_layer=default_layer)
            if ent.get("layer") not in known:
                ent["layer"] = default_layer
            doc.entities.append(ent)
        doc.solids = list(data.get("solids") or [])
        return doc

    def to_json(self, indent: int = 1) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "Document":
        return cls.from_dict(json.loads(text))


# ---------------------------------------------------------------------------
# Entitaeten
# ---------------------------------------------------------------------------

ENTITY_TYPES = {"line", "circle", "arc", "polyline", "text", "dim", "point", "hatch"}


def _pt(value: Any, fallback: Point = (0.0, 0.0)) -> Point:
    try:
        return (float(value[0]), float(value[1]))
    except (TypeError, ValueError, IndexError):
        return fallback


def normalize_entity(e: Dict[str, Any], default_layer: str = "Kontur") -> Dict[str, Any]:
    """Fehlende Felder ergaenzen und Zahlen in float wandeln."""
    e = dict(e)
    e.setdefault("id", new_id())
    e.setdefault("layer", default_layer)
    t = e.get("type")
    if t not in ENTITY_TYPES:
        raise ValueError(f"Unbekannter Entitaetstyp: {t!r}")

    if t == "line":
        e["a"] = _pt(e.get("a"))
        e["b"] = _pt(e.get("b"), (1.0, 0.0))
    elif t == "circle":
        e["c"] = _pt(e.get("c"))
        e["r"] = abs(float(e.get("r", 1.0)))
    elif t == "arc":
        e["c"] = _pt(e.get("c"))
        e["r"] = abs(float(e.get("r", 1.0)))
        e["start"] = geom.norm_angle(float(e.get("start", 0.0)))
        e["end"] = geom.norm_angle(float(e.get("end", 90.0)))
    elif t == "polyline":
        e["pts"] = [_pt(p) for p in e.get("pts", [])]
        e["closed"] = bool(e.get("closed", False))
        bulges = e.get("bulges") or []
        e["bulges"] = [float(b) for b in bulges[:len(e["pts"])]] + \
                      [0.0] * max(0, len(e["pts"]) - len(bulges))
    elif t == "text":
        e["p"] = _pt(e.get("p"))
        e["h"] = float(e.get("h", 3.5))
        e["text"] = str(e.get("text", ""))
        e["rot"] = float(e.get("rot", 0.0))
        e["align"] = e.get("align", "left")
    elif t == "point":
        e["p"] = _pt(e.get("p"))
    elif t == "hatch":
        e["pts"] = [_pt(p) for p in e.get("pts", [])]
        e["angle"] = float(e.get("angle", 45.0))
        e["spacing"] = abs(float(e.get("spacing", 3.0))) or 3.0
    elif t == "dim":
        e["kind"] = e.get("kind", "linear")
        e["p1"] = _pt(e.get("p1"))
        e["p2"] = _pt(e.get("p2"), (10.0, 0.0))
        e["pos"] = _pt(e.get("pos"), (0.0, 10.0))
        e["h"] = float(e.get("h", 3.5))
        if e.get("kind") == "angular":
            e["center"] = _pt(e.get("center"))
        if e.get("text") is not None:
            e["text"] = str(e["text"])
        e.setdefault("prefix", "")
        e.setdefault("suffix", "")
        e.setdefault("decimals", int(e.get("decimals", 1)))
    return e


def entity_points(e: Dict[str, Any]) -> List[Point]:
    """Charakteristische Punkte -- reicht fuer Bounding-Box und Auswahl."""
    t = e["type"]
    if t == "line":
        return [e["a"], e["b"]]
    if t == "circle":
        c, r = e["c"], e["r"]
        return [(c[0] - r, c[1] - r), (c[0] + r, c[1] + r)]
    if t == "arc":
        pts = [geom.arc_point(e["c"], e["r"], e["start"]),
               geom.arc_point(e["c"], e["r"], e["end"])]
        for a in (0.0, 90.0, 180.0, 270.0):
            if geom.arc_contains_angle(e["start"], e["end"], a):
                pts.append(geom.arc_point(e["c"], e["r"], a))
        return pts
    if t in ("polyline", "hatch"):
        return list(e["pts"])
    if t in ("text", "point"):
        return [e["p"]]
    if t == "dim":
        pts = [e["p1"], e["p2"], e["pos"]]
        if e.get("center"):
            pts.append(e["center"])
        return pts
    return []


def polyline_segments(e: Dict[str, Any]):
    """Polylinie in Strecken und Boegen zerlegen.

    Liefert Tupel ``("line", a, b)`` bzw. ``("arc", center, radius, start, end)``.
    """
    pts = e["pts"]
    bulges = e.get("bulges") or [0.0] * len(pts)
    n = len(pts)
    if n < 2:
        return []
    idx = list(range(n - 1)) + ([n - 1] if e.get("closed") else [])
    out = []
    for i in idx:
        a = pts[i]
        b = pts[(i + 1) % n]
        bulge = bulges[i] if i < len(bulges) else 0.0
        arc = geom.bulge_to_arc(a, b, bulge) if bulge else None
        if arc:
            out.append(("arc",) + arc)
        else:
            out.append(("line", a, b))
    return out


def outline_points(e: Dict[str, Any], sagitta: float = 0.05) -> List[Point]:
    """Entitaet als Polygonzug -- Grundlage fuer Schraffur, Extrusion, PDF."""
    t = e["type"]
    if t == "line":
        return [e["a"], e["b"]]
    if t == "circle":
        return geom.flatten_arc(e["c"], e["r"], 0.0, 360.0, sagitta, 16)[:-1]
    if t == "arc":
        return geom.flatten_arc(e["c"], e["r"], e["start"], e["end"], sagitta)
    if t in ("polyline", "hatch"):
        pts: List[Point] = []
        for seg in polyline_segments(e):
            if seg[0] == "line":
                part = [seg[1], seg[2]]
            else:
                part = geom.flatten_arc(seg[1], seg[2], seg[3], seg[4], sagitta)
            if pts and geom.dist(pts[-1], part[0]) < 1e-7:
                part = part[1:]
            pts.extend(part)
        if not pts:
            pts = list(e["pts"])
        return pts
    return entity_points(e)
