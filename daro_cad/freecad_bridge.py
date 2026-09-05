"""Bruecke zu FreeCAD.

DARO-CAD laeuft vollstaendig ohne FreeCAD.  Ist FreeCAD vorhanden, kommen
zusaetzliche Ausgabeformate dazu:

* ``.FCStd``  -- native FreeCAD-Datei mit Skizze, Volumenkoerper und
  TechDraw-Blatt; dort laesst sich parametrisch weiterkonstruieren
* ``.step``   -- genormtes Austauschformat fuer den Maschinenbau
* ``.stl``    -- Netz fuer den 3D-Druck
* Import von ``.FCStd``/``.step`` ueber den Umweg DXF

Die Kopplung laeuft ueber ``freecadcmd``: DARO-CAD schreibt die Zeichnung als
JSON, erzeugt ein Skript und laesst es von FreeCAD ausfuehren.  Damit bleibt der
Kern frei von Abhaengigkeiten und funktioniert auch dann, wenn FreeCAD in einer
anderen Python-Version installiert ist (AppImage, Snap, Flatpak).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .model import Document

# Uebliche Namen der FreeCAD-Kommandozeile
CANDIDATES = ["freecadcmd", "FreeCADCmd", "freecad-cmd", "freecad", "FreeCAD"]

# Uebliche Installationsorte, wenn nichts im PATH liegt
EXTRA_PATHS = [
    "/usr/lib/freecad/bin", "/usr/lib/freecad-python3/bin", "/usr/local/bin",
    "/opt/freecad/bin", "/snap/bin",
    "/Applications/FreeCAD.app/Contents/Resources/bin",
    "C:\\Program Files\\FreeCAD\\bin", "C:\\Program Files\\FreeCAD 1.0\\bin",
]

TIMEOUT = 300


def find_executable() -> Optional[str]:
    """Pfad zur FreeCAD-Kommandozeile suchen (Umgebungsvariable hat Vorrang)."""
    override = os.environ.get("FREECAD_CMD")
    if override and (shutil.which(override) or Path(override).exists()):
        return override
    for name in CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    for folder in EXTRA_PATHS:
        for name in CANDIDATES:
            for suffix in ("", ".exe"):
                candidate = Path(folder) / (name + suffix)
                if candidate.exists():
                    return str(candidate)
    return None


def has_module() -> bool:
    """Laeuft DARO-CAD bereits in einem Python mit FreeCAD-Modul?"""
    try:
        import FreeCAD  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False


def status() -> Dict[str, Any]:
    exe = find_executable()
    info: Dict[str, Any] = {
        "available": bool(exe) or has_module(),
        "executable": exe,
        "module": has_module(),
        "version": None,
        "formats": ["svg", "dxf", "pdf", "json"],
    }
    if info["available"]:
        info["formats"] += ["fcstd", "step", "stl"]
        info["version"] = _version(exe)
    return info


def _version(exe: Optional[str]) -> Optional[str]:
    if has_module():
        try:
            import FreeCAD  # type: ignore
            return str(FreeCAD.Version()[0:3])
        except Exception:
            pass
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30)
        text = (out.stdout or out.stderr or "").strip().splitlines()
        return text[0] if text else None
    except Exception:
        return None


class FreeCADError(RuntimeError):
    pass


def run_script(script: str, payload: Optional[Dict[str, Any]] = None) -> str:
    """Ein Python-Skript in FreeCAD ausfuehren.

    Das Skript erhaelt den Pfad zur JSON-Nutzlast in ``sys.argv[1]``.
    """
    exe = find_executable()
    if not exe and not has_module():
        raise FreeCADError(
            "FreeCAD wurde nicht gefunden. Bitte FreeCAD installieren "
            "(https://www.freecad.org) oder FREECAD_CMD auf die ausfuehrbare "
            "Datei setzen.")

    with tempfile.TemporaryDirectory(prefix="daro_cad_") as tmp:
        script_path = Path(tmp) / "job.py"
        data_path = Path(tmp) / "data.json"
        script_path.write_text(script, encoding="utf-8")
        data_path.write_text(json.dumps(payload or {}, ensure_ascii=False), encoding="utf-8")

        if exe:
            cmd = [exe, "--console", str(script_path), str(data_path)]
        else:
            cmd = [sys.executable, str(script_path), str(data_path)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        except subprocess.TimeoutExpired as exc:
            raise FreeCADError(f"FreeCAD antwortet nicht (>{TIMEOUT}s).") from exc

        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0 or "DARO_OK" not in output:
            raise FreeCADError(f"FreeCAD meldet einen Fehler:\n{output.strip()[-2000:]}")
        return output


# ---------------------------------------------------------------------------
# Skript, das in FreeCAD laeuft
# ---------------------------------------------------------------------------

BUILD_SCRIPT = r'''
# -*- coding: utf-8 -*-
"""Wird von DARO-CAD in FreeCAD ausgefuehrt: baut Zeichnung und Koerper auf."""
import json, math, sys

import FreeCAD as App
import Part

data = json.load(open(sys.argv[1], encoding="utf-8"))
doc_data = data["document"]
solids_data = data.get("solids") or []
targets = data.get("targets") or {}
meta = doc_data.get("meta") or {}

doc = App.newDocument(str(meta.get("drawingNumber") or "DARO"))


def vec(p, z=0.0):
    return App.Vector(float(p[0]), float(p[1]), float(z))


def edges_of(entity):
    """Zeichnungselement in Part-Kanten uebersetzen."""
    t = entity.get("type")
    out = []
    if t == "line":
        a, b = vec(entity["a"]), vec(entity["b"])
        if a.distanceToPoint(b) > 1e-9:
            out.append(Part.LineSegment(a, b).toShape())
    elif t == "circle":
        out.append(Part.Circle(vec(entity["c"]), App.Vector(0, 0, 1),
                               float(entity["r"])).toShape())
    elif t == "arc":
        circle = Part.Circle(vec(entity["c"]), App.Vector(0, 0, 1), float(entity["r"]))
        s = math.radians(float(entity["start"]))
        e = math.radians(float(entity["end"]))
        if e <= s:
            e += 2 * math.pi
        out.append(Part.ArcOfCircle(circle, s, e).toShape())
    elif t == "polyline":
        pts = entity.get("pts") or []
        n = len(pts)
        if n >= 2:
            idx = list(range(n - 1)) + ([n - 1] if entity.get("closed") else [])
            for i in idx:
                a, b = vec(pts[i]), vec(pts[(i + 1) % n])
                if a.distanceToPoint(b) > 1e-9:
                    out.append(Part.LineSegment(a, b).toShape())
    return out


# ---- 2D-Geometrie, nach Layern gruppiert ------------------------------
groups = {}
for entity in doc_data.get("entities") or []:
    shapes = edges_of(entity)
    if shapes:
        groups.setdefault(entity.get("layer") or "0", []).extend(shapes)

for layer, shapes in groups.items():
    obj = doc.addObject("Part::Feature", "Layer_" + "".join(
        ch if ch.isalnum() else "_" for ch in str(layer)))
    obj.Shape = Part.makeCompound(shapes)
    obj.Label = str(layer)

# ---- Texte als beschriftbare Objekte ----------------------------------
try:
    import Draft
    for entity in doc_data.get("entities") or []:
        if entity.get("type") == "text" and entity.get("text"):
            placement = App.Placement(vec(entity["p"]), App.Rotation(
                App.Vector(0, 0, 1), float(entity.get("rot") or 0.0)))
            text = Draft.make_text([str(entity["text"])], placement)
            if hasattr(text, "ViewObject") and text.ViewObject:
                text.ViewObject.FontSize = float(entity.get("h") or 3.5)
except Exception as exc:      # Draft ist optional
    App.Console.PrintWarning("Draft nicht verfuegbar: %s\n" % exc)

# ---- Volumenkoerper ---------------------------------------------------
built = []
for i, sol in enumerate(solids_data):
    profile = sol.get("profile") or {}
    outer = profile.get("outer") or []
    if len(outer) < 3:
        continue
    z0 = float(sol.get("z0") or 0.0)
    height = float(sol.get("height") or 1.0)

    def wire(points):
        pts = [vec(p, z0) for p in points]
        if pts[0].distanceToPoint(pts[-1]) > 1e-9:
            pts.append(pts[0])
        return Part.makePolygon(pts)

    face = Part.Face(wire(outer))
    for hole in profile.get("holes") or []:
        if len(hole) >= 3:
            face = face.cut(Part.Face(wire(hole)))
    shape = face.extrude(App.Vector(0, 0, height))
    obj = doc.addObject("Part::Feature", "Koerper%d" % (i + 1))
    obj.Shape = shape
    obj.Label = str(sol.get("name") or ("Koerper %d" % (i + 1)))
    built.append(obj)

doc.recompute()

# ---- TechDraw-Blatt ---------------------------------------------------
if built and targets.get("techdraw", True):
    try:
        page = doc.addObject("TechDraw::DrawPage", "Blatt")
        template = doc.addObject("TechDraw::DrawSVGTemplate", "Vorlage")
        import FreeCAD as _App
        template.Template = _App.getResourceDir() + "Mod/TechDraw/Templates/A3_Landscape_TD.svg"
        page.Template = template
        scale = float(data.get("scaleFactor") or 1.0)
        positions = {"front": (60, 180), "top": (60, 90), "left": (190, 180)}
        directions = {"front": (0, 0, 1), "top": (0, -1, 0), "left": (-1, 0, 0)}
        for name in data.get("views") or ["front", "top", "left"]:
            view = doc.addObject("TechDraw::DrawViewPart", "Ansicht_" + name)
            page.addView(view)
            view.Source = built
            view.Direction = App.Vector(*directions.get(name, (0, 0, 1)))
            view.Scale = scale
            view.X, view.Y = positions.get(name, (100, 150))
            view.HardHidden = True
        doc.recompute()
    except Exception as exc:
        App.Console.PrintWarning("TechDraw-Blatt uebersprungen: %s\n" % exc)

# ---- Ausgabe ----------------------------------------------------------
fcstd = targets.get("fcstd")
if fcstd:
    doc.saveAs(fcstd)

step = targets.get("step")
if step and built:
    Part.export(built, step)

stl = targets.get("stl")
if stl and built:
    import Mesh
    Mesh.export(built, stl)

dxf = targets.get("dxf")
if dxf:
    try:
        import importDXF
        importDXF.export(list(doc.Objects), dxf)
    except Exception as exc:
        App.Console.PrintWarning("DXF-Export uebersprungen: %s\n" % exc)

print("DARO_OK")
'''


READ_SCRIPT = r'''
# -*- coding: utf-8 -*-
"""Wird von DARO-CAD ausgefuehrt: liest FCStd/STEP und schreibt DXF."""
import json, sys
import FreeCAD as App

data = json.load(open(sys.argv[1], encoding="utf-8"))
source = data["source"]
target = data["target"]

if source.lower().endswith(".fcstd"):
    doc = App.openDocument(source)
else:
    doc = App.newDocument("Import")
    import Import
    Import.insert(source, doc.Name)
doc.recompute()

import importDXF
importDXF.export(list(doc.Objects), target)
print("DARO_OK")
'''


# ---------------------------------------------------------------------------
# Oeffentliche Funktionen
# ---------------------------------------------------------------------------

def build(doc: Document, solids: Sequence[Dict[str, Any]] = (),
          fcstd: Optional[str] = None, step: Optional[str] = None,
          stl: Optional[str] = None, dxf: Optional[str] = None,
          views: Sequence[str] = ("front", "top", "left"),
          techdraw: bool = True) -> Dict[str, Any]:
    """Zeichnung in FreeCAD aufbauen und in die gewuenschten Formate schreiben."""
    targets = {k: v for k, v in
               (("fcstd", fcstd), ("step", step), ("stl", stl), ("dxf", dxf)) if v}
    if not targets:
        raise ValueError("Kein Ausgabeformat angegeben.")
    targets["techdraw"] = techdraw
    payload = {
        "document": doc.to_dict(),
        "solids": [dict(s) for s in solids],
        "targets": targets,
        "views": list(views),
        "scaleFactor": doc.scale_factor,
    }
    output = run_script(BUILD_SCRIPT, payload)
    written = {k: v for k, v in targets.items() if isinstance(v, str) and Path(v).exists()}
    return {"written": written, "log": output.strip()[-2000:]}


def import_file(path: str) -> Document:
    """FCStd oder STEP ueber FreeCAD einlesen (Umweg ueber DXF)."""
    from . import dxf as dxf_mod

    source = str(Path(path).resolve())
    if not Path(source).exists():
        raise FileNotFoundError(source)
    with tempfile.TemporaryDirectory(prefix="daro_cad_imp_") as tmp:
        target = str(Path(tmp) / "out.dxf")
        run_script(READ_SCRIPT, {"source": source, "target": target})
        if not Path(target).exists():
            raise FreeCADError("FreeCAD hat keine DXF-Datei erzeugt.")
        return dxf_mod.load(Path(target).read_text(encoding="utf-8", errors="replace"))
