"""PDF-Export -- druckfertiges Vektor-PDF in exakter Blattgroesse.

Bewusst ohne Fremdbibliothek: ein einzelner Content-Stream mit Pfaden und
Helvetica-Text (WinAnsi).  Boegen werden mit begrenztem Stichmass in
Polygonzuege zerlegt, dadurch bleibt die Datei klein und exakt.
"""

from __future__ import annotations

import math
import zlib
from typing import Any, Dict, List, Sequence, Tuple

from . import geom, primitives
from .model import Document, LINETYPES, Point

MM_TO_PT = 72.0 / 25.4

# Helvetica-Zeichenbreiten (1/1000 em) fuer die Textausrichtung.
_W = {
    32: 278, 33: 278, 34: 355, 35: 556, 36: 556, 37: 889, 38: 667, 39: 191,
    40: 333, 41: 333, 42: 389, 43: 584, 44: 278, 45: 333, 46: 278, 47: 278,
    58: 278, 59: 278, 60: 584, 61: 584, 62: 584, 63: 556, 64: 1015,
    65: 667, 66: 667, 67: 722, 68: 722, 69: 667, 70: 611, 71: 778, 72: 722,
    73: 278, 74: 500, 75: 667, 76: 556, 77: 833, 78: 722, 79: 778, 80: 667,
    81: 778, 82: 722, 83: 667, 84: 611, 85: 722, 86: 667, 87: 944, 88: 667,
    89: 667, 90: 611, 91: 278, 92: 278, 93: 278, 94: 469, 95: 556, 96: 333,
    97: 556, 98: 556, 99: 500, 100: 556, 101: 556, 102: 278, 103: 556, 104: 556,
    105: 222, 106: 222, 107: 500, 108: 222, 109: 833, 110: 556, 111: 556,
    112: 556, 113: 556, 114: 333, 115: 500, 116: 278, 117: 556, 118: 500,
    119: 722, 120: 500, 121: 500, 122: 500, 123: 334, 124: 260, 125: 334, 126: 584,
    176: 400, 216: 778, 223: 611, 228: 556, 246: 556, 252: 556, 196: 667, 214: 778, 220: 722,
}
for _d in range(48, 58):
    _W[_d] = 556


def text_width(text: str, size: float) -> float:
    return sum(_W.get(ord(ch), 556) for ch in text) / 1000.0 * size


def _esc(text: str) -> bytes:
    out = bytearray()
    for ch in text:
        code = ord(ch)
        if code > 255:
            code = {0x2300: 0xD8, 0x2205: 0xD8, 0x00B0: 0xB0}.get(code, 0x3F)
        if code in (0x28, 0x29, 0x5C):
            out.append(0x5C)
        out.append(code)
    return bytes(out)


def _hex_to_rgb(color: str) -> Tuple[float, float, float]:
    c = (color or "#111111").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return tuple(int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore
    except ValueError:
        return (0.07, 0.07, 0.07)


class _Content:
    def __init__(self, scale: float):
        self.s = scale
        self.parts: List[bytes] = []
        self.state: Dict[str, Any] = {}

    def pt(self, p: Point) -> Tuple[float, float]:
        return (p[0] * self.s * MM_TO_PT, p[1] * self.s * MM_TO_PT)

    def add(self, text: str) -> None:
        self.parts.append(text.encode("latin-1", "replace"))

    def raw(self, data: bytes) -> None:
        self.parts.append(data)

    def stroke_style(self, prim: Dict[str, Any]) -> None:
        color = _hex_to_rgb(prim.get("color", "#111111"))
        lw = max(0.05, float(prim.get("lw", 0.25))) * MM_TO_PT
        pattern = LINETYPES.get(prim.get("lt", "continuous")) or []
        key = (color, round(lw, 4), tuple(pattern))
        if self.state.get("stroke") == key:
            return
        self.state["stroke"] = key
        self.add("%.3f %.3f %.3f RG\n" % color)
        self.add("%.3f w\n" % lw)
        if pattern:
            dashes = " ".join("%.3f" % (v * MM_TO_PT) for v in pattern)
            self.add(f"[{dashes}] 0 d\n")
        else:
            self.add("[] 0 d\n")

    def fill_style(self, color: str) -> None:
        rgb = _hex_to_rgb(color)
        if self.state.get("fill") == rgb:
            return
        self.state["fill"] = rgb
        self.add("%.3f %.3f %.3f rg\n" % rgb)

    def path(self, pts: Sequence[Point], close: bool, fill: bool = False) -> None:
        if len(pts) < 2:
            return
        x, y = self.pt(pts[0])
        self.add("%.3f %.3f m\n" % (x, y))
        for p in pts[1:]:
            x, y = self.pt(p)
            self.add("%.3f %.3f l\n" % (x, y))
        if close:
            self.add("h\n")
        self.add("f\n" if fill else "S\n")


def _primitive(c: _Content, prim: Dict[str, Any]) -> None:
    k = prim.get("k")
    if k == "line":
        c.stroke_style(prim)
        c.path([prim["a"], prim["b"]], False)
    elif k == "poly":
        c.stroke_style(prim)
        c.path(prim["pts"], prim.get("close", False))
    elif k == "circle":
        c.stroke_style(prim)
        c.path(geom.flatten_arc(prim["c"], prim["r"], 0.0, 360.0, 0.02, 24), True)
    elif k == "arc":
        c.stroke_style(prim)
        c.path(geom.flatten_arc(prim["c"], prim["r"], prim["start"], prim["end"], 0.02), False)
    elif k == "fill":
        c.fill_style(prim.get("color", "#111111"))
        c.path(prim["pts"], True, fill=True)
    elif k == "text":
        size = prim["h"] * c.s * MM_TO_PT
        if size <= 0.1:
            return
        c.fill_style(prim.get("color", "#111111"))
        width = text_width(prim["text"], size)
        anchor = prim.get("anchor", "start")
        dx = {"middle": -width / 2.0, "end": -width}.get(anchor, 0.0)
        dy = {"middle": -size * 0.36, "top": -size * 0.72}.get(prim.get("valign", "base"), 0.0)
        x, y = c.pt(prim["p"])
        rot = math.radians(float(prim.get("rot", 0.0)))
        ca, sa = math.cos(rot), math.sin(rot)
        tx = x + dx * ca - dy * sa
        ty = y + dx * sa + dy * ca
        c.add("BT\n/F1 %.3f Tf\n" % size)
        c.add("%.5f %.5f %.5f %.5f %.3f %.3f Tm\n" % (ca, sa, -sa, ca, tx, ty))
        c.raw(b"(" + _esc(prim["text"]) + b") Tj\n")
        c.add("ET\n")


def render(doc: Document, with_sheet: bool = True, compress: bool = True) -> bytes:
    pw, ph = doc.sheet_size()
    c = _Content(doc.scale_factor)
    c.add("1 1 1 rg\n0 0 %.3f %.3f re f\n" % (pw * MM_TO_PT, ph * MM_TO_PT))
    c.add("1 J 1 j\n")
    prims: List[Dict[str, Any]] = []
    if with_sheet:
        prims.extend(primitives.sheet_primitives(doc))
    prims.extend(primitives.document_primitives(doc, for_print=True))
    for prim in prims:
        _primitive(c, prim)

    stream = b"".join(c.parts)
    filters = b""
    if compress:
        stream = zlib.compress(stream, 9)
        filters = b"/Filter /FlateDecode "

    objects: List[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.3f %.3f] /Resources "
         "<< /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
         % (pw * MM_TO_PT, ph * MM_TO_PT)).encode("latin-1"),
        b"<< " + filters + ("/Length %d >>" % len(stream)).encode("latin-1") +
        b"\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        ("<< /Title (%s) /Creator (DARO-CAD) /Producer (DARO-CAD) >>"
         % _esc(str(doc.meta.get("title", "Zeichnung"))).decode("latin-1")).encode("latin-1"),
    ]

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += ("%d 0 obj\n" % i).encode("latin-1") + body + b"\nendobj\n"
    xref_pos = len(out)
    count = len(objects) + 1
    out += ("xref\n0 %d\n" % count).encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += ("%010d 00000 n \n" % off).encode("latin-1")
    out += ("trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (count, len(objects), xref_pos)).encode("latin-1")
    return bytes(out)
