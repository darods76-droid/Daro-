"""SVG-Export -- massstabsgetreu in Millimetern.

Das erzeugte SVG hat exakt die Blattgroesse in mm und kann direkt gedruckt oder
in andere Programme importiert werden.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple
from xml.sax.saxutils import escape

from . import geom, primitives
from .model import Document, LINETYPES, Point

FONT = "ISOCPEUR, 'Arial Narrow', Helvetica, Arial, sans-serif"


def _fmt(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") or "0"


class _Mapper:
    """Modellkoordinaten -> Papierkoordinaten (mm, Y nach unten)."""

    def __init__(self, scale: float, sheet_h: float):
        self.s = scale
        self.h = sheet_h

    def __call__(self, p: Point) -> Point:
        return (p[0] * self.s, self.h - p[1] * self.s)

    def len(self, v: float) -> float:
        return v * self.s


def _style(prim: Dict[str, Any], m: _Mapper) -> str:
    lw = max(0.05, float(prim.get("lw", 0.25)))
    parts = [f'stroke="{prim.get("color", "#111")}"', f'stroke-width="{_fmt(lw)}"',
             'fill="none"', 'stroke-linecap="butt"', 'stroke-linejoin="round"']
    pattern = LINETYPES.get(prim.get("lt", "continuous")) or []
    if pattern:
        parts.append('stroke-dasharray="%s"' % " ".join(_fmt(v) for v in pattern))
    return " ".join(parts)


def _arc_path(prim: Dict[str, Any], m: _Mapper) -> str:
    c, r = prim["c"], prim["r"]
    start, end = prim["start"], prim["end"]
    sweep = geom.arc_sweep(start, end)
    a = m(geom.arc_point(c, r, start))
    b = m(geom.arc_point(c, r, end))
    rr = m.len(r)
    large = 1 if sweep > 180.0 else 0
    # Die Y-Spiegelung dreht den Umlaufsinn: CCW im Modell -> sweep-flag 1 im SVG.
    return (f'M {_fmt(a[0])} {_fmt(a[1])} A {_fmt(rr)} {_fmt(rr)} 0 {large} 1 '
            f'{_fmt(b[0])} {_fmt(b[1])}')


def primitive_to_svg(prim: Dict[str, Any], m: _Mapper) -> str:
    k = prim.get("k")
    style = _style(prim, m)
    if k == "line":
        a, b = m(prim["a"]), m(prim["b"])
        return (f'<line x1="{_fmt(a[0])}" y1="{_fmt(a[1])}" x2="{_fmt(b[0])}" '
                f'y2="{_fmt(b[1])}" {style}/>')
    if k == "poly":
        pts = " ".join(f"{_fmt(p[0])},{_fmt(p[1])}" for p in (m(q) for q in prim["pts"]))
        tag = "polygon" if prim.get("close") else "polyline"
        return f'<{tag} points="{pts}" {style}/>'
    if k == "circle":
        c = m(prim["c"])
        return (f'<circle cx="{_fmt(c[0])}" cy="{_fmt(c[1])}" '
                f'r="{_fmt(m.len(prim["r"]))}" {style}/>')
    if k == "arc":
        return f'<path d="{_arc_path(prim, m)}" {style}/>'
    if k == "fill":
        pts = " ".join(f"{_fmt(p[0])},{_fmt(p[1])}" for p in (m(q) for q in prim["pts"]))
        return f'<polygon points="{pts}" fill="{prim.get("color", "#111")}" stroke="none"/>'
    if k == "text":
        p = m(prim["p"])
        size = m.len(prim["h"])
        anchor = {"start": "start", "middle": "middle", "end": "end"}.get(
            prim.get("anchor", "start"), "start")
        rot = -float(prim.get("rot", 0.0))         # SVG dreht im Uhrzeigersinn
        transform = ""
        if abs(rot) > 1e-6:
            transform = f' transform="rotate({_fmt(rot)} {_fmt(p[0])} {_fmt(p[1])})"'
        baseline = {"base": "alphabetic", "middle": "central", "top": "hanging"}.get(
            prim.get("valign", "base"), "alphabetic")
        return (f'<text x="{_fmt(p[0])}" y="{_fmt(p[1])}" font-family="{FONT}" '
                f'font-size="{_fmt(size)}" fill="{prim.get("color", "#111")}" '
                f'text-anchor="{anchor}" dominant-baseline="{baseline}"'
                f'{transform}>{escape(prim["text"])}</text>')
    return ""


def render(doc: Document, with_sheet: bool = True, background: str = "#ffffff") -> str:
    pw, ph = doc.sheet_size()
    m = _Mapper(doc.scale_factor, ph)
    prims: List[Dict[str, Any]] = []
    if with_sheet:
        prims.extend(primitives.sheet_primitives(doc))
    prims.extend(primitives.document_primitives(doc, for_print=True))

    body = "\n".join(filter(None, (primitive_to_svg(p, m) for p in prims)))
    bg = (f'<rect x="0" y="0" width="{_fmt(pw)}" height="{_fmt(ph)}" fill="{background}"/>'
          if background else "")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
        f'width="{_fmt(pw)}mm" height="{_fmt(ph)}mm" '
        f'viewBox="0 0 {_fmt(pw)} {_fmt(ph)}">\n'
        f'<title>{escape(str(doc.meta.get("title", "Zeichnung")))}</title>\n'
        f'{bg}\n{body}\n</svg>\n'
    )
