#!/usr/bin/env python3
"""Beispielzeichnungen erzeugen -- zugleich Vorlage fuer den Einsatz per Skript.

Aufruf:

    python3 examples/erzeuge_beispiele.py

Die Ergebnisse landen neben diesem Skript:

* ``*.darocad.json``  -- in der App ueber "Oeffnen" ladbar
* ``*.pdf``           -- druckfertig, exakte Blattgroesse
* ``*.dxf``           -- fuer FreeCAD, LibreCAD, QCAD, AutoCAD
* ``*.svg``           -- Vektorgrafik fuer Dokumente und Web

Wer FreeCAD installiert hat, kann zusaetzlich mit ``--freecad`` eine ``.FCStd``
und eine ``.step`` erzeugen lassen.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daro_cad import dxf, pdf_export, solid, svg_export, views
from daro_cad.model import Document

HERE = Path(__file__).resolve().parent

# Bulge einer Viertelkreis-Rundung gegen den Uhrzeigersinn: tan(90°/4)
QUARTER = math.tan(math.radians(90) / 4)


def gerundetes_rechteck(x: float, y: float, w: float, h: float, r: float) -> Dict[str, Any]:
    """Rechteck mit vier gleichen Eckrundungen als Polylinie mit Bulges."""
    return {
        "type": "polyline",
        "closed": True,
        "layer": "Kontur",
        "pts": [
            (x + r, y), (x + w - r, y),
            (x + w, y + r), (x + w, y + h - r),
            (x + w - r, y + h), (x + r, y + h),
            (x, y + h - r), (x, y + r),
        ],
        "bulges": [0, QUARTER, 0, QUARTER, 0, QUARTER, 0, QUARTER],
    }


def kreis_punkte(cx: float, cy: float, r: float, schritte: int = 48) -> List[Tuple[float, float]]:
    return [(cx + r * math.cos(2 * math.pi * i / schritte),
             cy + r * math.sin(2 * math.pi * i / schritte)) for i in range(schritte)]


def schreibe(doc: Document, name: str, solids: Sequence[Dict[str, Any]] = (),
             freecad: bool = False) -> None:
    """Zeichnung in allen Formaten ablegen."""
    stamm = HERE / name
    stamm.with_suffix(".darocad.json").write_text(doc.to_json(), encoding="utf-8")
    stamm.with_suffix(".svg").write_text(svg_export.render(doc), encoding="utf-8")
    stamm.with_suffix(".pdf").write_bytes(pdf_export.render(doc))
    stamm.with_suffix(".dxf").write_text(dxf.export(doc), encoding="utf-8")

    erzeugt = ["json", "svg", "pdf", "dxf"]
    if freecad:
        from daro_cad import freecad_bridge
        try:
            freecad_bridge.build(doc, solids,
                                 fcstd=str(stamm.with_suffix(".FCStd")),
                                 step=str(stamm.with_suffix(".step")))
            erzeugt += ["FCStd", "step"]
        except freecad_bridge.FreeCADError as exc:
            print(f"   FreeCAD uebersprungen: {exc}")

    print(f"   {name}: {len(doc.entities)} Elemente -> {', '.join(erzeugt)}")


# ---------------------------------------------------------------------------
# Beispiel 1 -- Lagerplatte mit abgeleitetem Ansichtssatz
# ---------------------------------------------------------------------------

def lagerplatte(freecad: bool = False) -> None:
    """Platte 120 x 70 x 14 mit zwei Bohrungen, drei Ansichten und Bemassung."""
    print("1) Lagerplatte")

    # -- Profil und Koerper (Konturen in eigenen Koordinaten) --------------
    breite, hoehe, dicke, radius = 120.0, 70.0, 14.0, 10.0
    bohrung_r = 12.0
    bohrungen = [(30.0, 35.0), (90.0, 35.0)]

    kontur = gerundetes_rechteck(0, 0, breite, hoehe, radius)
    profil = Document()
    profil.add(kontur)
    aussen = solid.build_loops([profil.entities[0]])[0]
    koerper = solid.extrude(aussen, [kreis_punkte(*b, bohrung_r) for b in bohrungen], dicke)

    # -- Ansichtssatz auf dem Blatt ----------------------------------------
    doc = Document()
    doc.meta.update({
        "title": "Lagerplatte", "drawingNumber": "DC-1001", "material": "S235JR",
        "company": "DARO Konstruktion", "author": "D. Rodriguez", "date": "05.09.2026",
        "approvedBy": "M. Keller", "scale": "1:1", "sheet": "A3",
        "generalTolerance": "ISO 2768-mK", "surface": "Ra 3,2",
        "weight": f"{solid.mass(koerper):.2f} kg".replace(".", ","), "revision": "A",
    })

    mitte = (150.0, 190.0)          # Mitte der Vorderansicht auf dem Blatt
    for e in views.derive([koerper], ("front", "top", "left"),
                          origin=mitte, gap=30.0, projection="first"):
        doc.add(e)

    # Blattkoordinate eines Punktes der Vorderansicht
    def va(x: float, y: float) -> Tuple[float, float]:
        return (mitte[0] - breite / 2 + x, mitte[1] - hoehe / 2 + y)

    doc.add({"type": "dim", "kind": "linear", "layer": "Bemassung", "decimals": 0,
             "p1": va(0, 0), "p2": va(breite, 0), "pos": va(breite / 2, -22)})
    doc.add({"type": "dim", "kind": "linear", "axis": "y", "layer": "Bemassung",
             "decimals": 0, "p1": va(breite, 0), "p2": va(breite, hoehe),
             "pos": va(breite + 22, hoehe / 2)})
    doc.add({"type": "dim", "kind": "linear", "layer": "Bemassung", "decimals": 0,
             "p1": va(*bohrungen[0]), "p2": va(*bohrungen[1]),
             "pos": va(breite / 2, hoehe + 18)})
    doc.add({"type": "dim", "kind": "diameter", "layer": "Bemassung", "decimals": 0,
             "p1": va(*bohrungen[0]),
             "p2": va(bohrungen[0][0] - bohrung_r * 0.707, bohrungen[0][1] + bohrung_r * 0.707),
             "pos": va(-30, hoehe + 14)})
    doc.add({"type": "dim", "kind": "radius", "layer": "Bemassung", "decimals": 0,
             "p1": va(radius, radius), "p2": va(radius - 7.07, radius - 7.07),
             "pos": va(-32, -18)})
    doc.add({"type": "text", "p": va(breite / 2, hoehe + 40), "h": 3.5, "align": "center",
             "layer": "Text", "text": "Kanten gebrochen 0,5 x 45°"})

    doc.solids = [{"name": koerper["name"], "height": koerper["height"],
                   "z0": koerper["z0"], "profile": koerper["profile"]}]
    schreibe(doc, "lagerplatte", [koerper], freecad)


# ---------------------------------------------------------------------------
# Beispiel 2 -- Winkelblech als Schnittdarstellung
# ---------------------------------------------------------------------------

def winkelblech(freecad: bool = False) -> None:
    """Geschnittenes Winkelblech mit Schraffur, Radien- und Winkelmass."""
    print("2) Winkelblech")

    doc = Document()
    doc.meta.update({
        "title": "Winkelblech", "subtitle": "Schnitt A-A", "drawingNumber": "DC-1002",
        "material": "AlMg3", "company": "DARO Konstruktion", "author": "D. Rodriguez",
        "date": "05.09.2026", "scale": "1:1", "sheet": "A4L",
        "generalTolerance": "ISO 2768-m", "weight": "0,21 kg",
    })

    # Winkelprofil: 80 lang, 60 hoch, 8 dick, Innenradius 8.
    # Platzierung oberhalb des Schriftfelds (A4 quer: Schriftfeld bis y = 73).
    x0, y0 = 80.0, 110.0
    t, laenge, hoehe, r = 8.0, 80.0, 60.0, 8.0
    kontur = [
        (x0, y0), (x0 + laenge, y0), (x0 + laenge, y0 + t),
        (x0 + t + r, y0 + t), (x0 + t, y0 + t + r),
        (x0 + t, y0 + hoehe), (x0, y0 + hoehe),
    ]
    bulges = [0, 0, 0, -math.tan(math.radians(90) / 4), 0, 0, 0]
    doc.add({"type": "polyline", "pts": kontur, "bulges": bulges, "closed": True,
             "layer": "Kontur"})

    # Schnittflaeche schraffieren (DIN ISO 128-50: 45°, gleichmaessiger Abstand)
    from daro_cad.model import outline_points
    doc.add({"type": "hatch", "pts": outline_points(doc.entities[0]), "angle": 45,
             "spacing": 3.0, "layer": "Schraffur"})

    # Bohrung mit Mittellinien
    bx, by, br = x0 + 60, y0 + t / 2, 3.5
    doc.add({"type": "circle", "c": (bx, by), "r": br, "layer": "Kontur"})
    doc.add({"type": "line", "a": (bx - br - 4, by), "b": (bx + br + 4, by),
             "layer": "Mittellinie"})
    doc.add({"type": "line", "a": (bx, by - br - 4), "b": (bx, by + br + 4),
             "layer": "Mittellinie"})

    doc.add({"type": "dim", "kind": "linear", "layer": "Bemassung", "decimals": 0,
             "p1": (x0, y0), "p2": (x0 + laenge, y0), "pos": (x0 + laenge / 2, y0 - 20)})
    doc.add({"type": "dim", "kind": "linear", "axis": "y", "layer": "Bemassung",
             "decimals": 0, "p1": (x0, y0), "p2": (x0, y0 + hoehe),
             "pos": (x0 - 20, y0 + hoehe / 2)})
    doc.add({"type": "dim", "kind": "linear", "axis": "y", "layer": "Bemassung",
             "decimals": 0, "p1": (x0 + laenge, y0), "p2": (x0 + laenge, y0 + t),
             "pos": (x0 + laenge + 18, y0 + t / 2)})
    doc.add({"type": "dim", "kind": "diameter", "layer": "Bemassung", "decimals": 0,
             "p1": (bx, by), "p2": (bx, by + br), "pos": (bx + 22, y0 + 34)})
    doc.add({"type": "dim", "kind": "radius", "layer": "Bemassung", "decimals": 0,
             "p1": (x0 + t + r, y0 + t + r), "p2": (x0 + t + r * 0.293, y0 + t + r * 0.293),
             "pos": (x0 + 46, y0 + 40)})
    doc.add({"type": "dim", "kind": "angular", "layer": "Bemassung", "decimals": 0,
             "center": (x0, y0), "p1": (x0 + 26, y0), "p2": (x0, y0 + 26),
             "pos": (x0 + 15, y0 + 15)})
    doc.add({"type": "text", "p": (x0 + laenge / 2, y0 + hoehe + 12), "h": 5,
             "align": "center", "layer": "Text", "text": "SCHNITT A-A"})

    schreibe(doc, "winkelblech", (), freecad)


def main(argv: Sequence[str]) -> int:
    freecad = "--freecad" in argv
    print(f"Beispiele werden erzeugt in {HERE}\n")
    lagerplatte(freecad)
    winkelblech(freecad)
    print("\nFertig. Zum Ansehen:  python3 -m daro_cad   und dann 'Öffnen'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
