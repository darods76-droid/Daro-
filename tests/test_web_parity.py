"""Browser-Fassung gegen den Python-Kern pruefen.

Die Zeichen-App rechnet Bemassung, Ansichten und Export im Browser noch einmal
nach, damit sie ohne Server auskommt (siehe ``DARO-CAD.html``). Diese Tests
stellen sicher, dass beide Wege exakt dasselbe liefern -- sonst saehe eine
Zeichnung am Bildschirm anders aus als im gedruckten PDF.

Benoetigt Node.js. Fehlt es, werden die Tests uebersprungen.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from daro_cad import dxf, geom, pdf_export, solid, svg_export, views
from daro_cad.model import Document

NODE = shutil.which("node")


def run_node(script: str) -> str:
    """Ein ES-Modul-Skript im Ordner der Web-App ausfuehren."""
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", dir=ROOT / "web" / "js",
                                     encoding="utf-8", delete=False) as fh:
        fh.write(script)
        path = Path(fh.name)
    try:
        proc = subprocess.run([NODE, str(path)], capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise AssertionError(f"Node meldet einen Fehler:\n{proc.stderr[-2000:]}")
        return proc.stdout
    finally:
        path.unlink(missing_ok=True)


def beispiel_dokument() -> Document:
    """Eine Zeichnung, die jede Entitaetsart mindestens einmal enthaelt."""
    d = Document()
    d.meta.update({"title": "Prüfteil", "drawingNumber": "DC-9", "scale": "1:2",
                   "sheet": "A3", "material": "S235JR", "author": "Test",
                   "date": "13.09.2026"})
    d.add({"type": "polyline", "pts": [[60, 80], [160, 80], [160, 140], [60, 140]],
           "closed": True, "bulges": [0, 0.4142, 0, 0], "layer": "Kontur"})
    d.add({"type": "circle", "c": [110, 110], "r": 20, "layer": "Kontur"})
    d.add({"type": "arc", "c": [60, 80], "r": 15, "start": 0, "end": 90, "layer": "Mittellinie"})
    d.add({"type": "text", "p": [70, 150], "h": 5, "text": "Ø40 H7 groß",
           "align": "center", "layer": "Text"})
    d.add({"type": "dim", "kind": "linear", "p1": [60, 80], "p2": [160, 80],
           "pos": [110, 60], "layer": "Bemassung"})
    d.add({"type": "dim", "kind": "diameter", "p1": [110, 110], "p2": [110, 130],
           "pos": [150, 160], "layer": "Bemassung"})
    d.add({"type": "hatch", "pts": [[60, 80], [100, 80], [100, 100], [60, 100]],
           "angle": 45, "spacing": 3, "layer": "Schraffur"})

    # Die 2026 ergaenzten Arten muessen ebenso deckungsgleich herauskommen
    d.add({"type": "ellipse", "c": [210, 110], "rx": 40, "ry": 22, "rot": 18,
           "layer": "Kontur"})
    d.add({"type": "leader", "p1": [110, 110], "p2": [180, 165], "text": "4x M8",
           "layer": "Text"})
    d.add({"type": "surface", "p": [90, 60], "kind": "machined", "value": "Ra 1,6",
           "layer": "Text"})
    d.add({"type": "surface", "p": [130, 60], "kind": "nomachine", "value": "Rz 25",
           "layer": "Text"})
    d.add({"type": "fcf", "p": [200, 45], "sym": "Rechtwinkligkeit", "tol": "0,05",
           "datums": ["A"], "layer": "Text"})
    d.add({"type": "fcf", "p": [200, 25], "sym": "Position", "tol": "Ø0,2",
           "datums": ["A", "B", "C"], "layer": "Text"})
    d.add({"type": "dim", "kind": "linear", "axis": "y", "p1": [60, 80], "p2": [60, 140],
           "pos": [40, 110], "tolMode": "sym", "tolUpper": 0.2, "layer": "Bemassung"})
    d.add({"type": "dim", "kind": "aligned", "p1": [160, 140], "p2": [210, 175],
           "pos": [195, 165], "tolMode": "limits", "tolUpper": 0.05,
           "tolLower": -0.15, "layer": "Bemassung"})
    d.add({"type": "dim", "kind": "linear", "p1": [60, 170], "p2": [160, 170],
           "pos": [110, 185], "tolMode": "fit", "fit": "H7", "layer": "Bemassung"})

    # Ein Block, zweimal eingefuegt -- gedreht und vergroessert
    d.define_block("Schraube M8", [
        {"type": "circle", "c": [0, 0], "r": 4, "layer": "Kontur"},
        {"type": "line", "a": [-6, 0], "b": [6, 0], "layer": "Mittellinie"},
        {"type": "line", "a": [0, -6], "b": [0, 6], "layer": "Mittellinie"},
        {"type": "text", "p": [7, -1.5], "h": 3.5, "text": "M8", "layer": "Text"},
    ], base=(0.0, 0.0))
    d.add({"type": "insert", "name": "Schraube M8", "p": [250, 60], "layer": "Kontur"})
    d.add({"type": "insert", "name": "Schraube M8", "p": [250, 130], "rot": 37.5,
           "scale": 1.75, "layer": "Kontur"})
    return d


@unittest.skipUnless(NODE, "Node.js ist nicht installiert")
class TestExportParitaet(unittest.TestCase):
    """SVG, DXF und PDF muessen aus beiden Umgebungen byteweise gleich sein."""

    @classmethod
    def setUpClass(cls):
        cls.doc = beispiel_dokument()
        cls.tmp = tempfile.TemporaryDirectory()
        doc_path = Path(cls.tmp.name) / "doc.json"
        doc_path.write_text(cls.doc.to_json(), encoding="utf-8")
        out = Path(cls.tmp.name)
        cls.js_out = out
        run_node(f"""
import fs from 'node:fs';
const [D, SVG, DXF, PDF] = await Promise.all([
  import('./doc.js'), import('./export-svg.js'),
  import('./export-dxf.js'), import('./export-pdf.js')]);
const d = new D.Drawing();
d.load(JSON.parse(fs.readFileSync({json.dumps(str(doc_path))}, 'utf8')));
fs.writeFileSync({json.dumps(str(out / 'js.svg'))}, SVG.render(d));
fs.writeFileSync({json.dumps(str(out / 'js.dxf'))}, DXF.render(d));
fs.writeFileSync({json.dumps(str(out / 'js.pdf'))}, Buffer.from(PDF.render(d)));
""")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_svg_identisch(self):
        js = (self.js_out / "js.svg").read_text(encoding="utf-8")
        self.assertEqual(svg_export.render(self.doc), js)

    def test_dxf_identisch(self):
        js = (self.js_out / "js.dxf").read_text(encoding="utf-8")
        self.assertEqual(dxf.export(self.doc), js)

    def test_pdf_identisch(self):
        js = (self.js_out / "js.pdf").read_bytes()
        self.assertEqual(pdf_export.render(self.doc, compress=False), js)


@unittest.skipUnless(NODE, "Node.js ist nicht installiert")
class TestModellParitaet(unittest.TestCase):
    """Extrusion und Ansichtsableitung muessen dieselben Kanten liefern."""

    def setUp(self):
        self.outer = [(0, 0), (80, 0), (80, 50), (0, 50)]
        self.hole = [(40 + 10 * math.cos(math.radians(a)),
                      25 + 10 * math.sin(math.radians(a))) for a in range(0, 360, 10)]

    def js_result(self) -> dict:
        return json.loads(run_node("""
const [S, V, G] = await Promise.all([
  import('./solid.js'), import('./views.js'), import('./geom.js')]);
const outer = [[0,0],[80,0],[80,50],[0,50]];
const hole = [];
for (let a = 0; a < 360; a += 10) {
  hole.push([40 + 10*Math.cos(a*Math.PI/180), 25 + 10*Math.sin(a*Math.PI/180)]);
}
const s = S.extrude(outer, [hole], 12);
const r4 = v => +v.toFixed(4);
const res = { volume: +S.volume(s).toFixed(4), verts: s.verts.length,
              edges: s.edges.length, views: {} };
for (const name of ['front','top','left']) {
  const d = V.project([s], name);
  res.views[name] = {
    v: d.visible.map(g => [...g[0].map(r4), ...g[1].map(r4)]).sort(),
    h: d.hidden.map(g => [...g[0].map(r4), ...g[1].map(r4)]).sort(),
  };
}
const ents = V.derive([s], ['front','top','left'], {origin:[150,190], gap:30});
res.derive = { count: ents.length,
  layers: [...new Set(ents.map(e => e.layer))].sort(),
  bbox: G.bbox(ents.filter(e => e.type === 'line').flatMap(e => [e.a, e.b])).map(r4) };
console.log(JSON.stringify(res));
"""))

    def test_extrusion_und_ansichten(self):
        s = solid.extrude(self.outer, [self.hole], 12)
        js = self.js_result()

        self.assertEqual(js["verts"], len(s["verts"]))
        self.assertEqual(js["edges"], len(s["edges"]))
        self.assertAlmostEqual(js["volume"], round(solid.volume(s), 4), places=4)

        for name in ("front", "top", "left"):
            data = views.project([s], name)
            for key, py_key in (("v", "visible"), ("h", "hidden")):
                py = sorted([round(v, 4) for v in seg[0]] + [round(v, 4) for v in seg[1]]
                            for seg in data[py_key])
                self.assertEqual(sorted(js["views"][name][key]), py,
                                 f"Ansicht {name}, {py_key}")

        ents = views.derive([s], ("front", "top", "left"), origin=(150, 190), gap=30)
        self.assertEqual(js["derive"]["count"], len(ents))
        self.assertEqual(js["derive"]["layers"], sorted({e["layer"] for e in ents}))
        box = geom.bbox([p for e in ents if e["type"] == "line" for p in (e["a"], e["b"])])
        self.assertEqual(js["derive"]["bbox"], [round(v, 4) for v in box])


@unittest.skipUnless(NODE, "Node.js ist nicht installiert")
class TestDxfImportParitaet(unittest.TestCase):
    """Der DXF-Leser im Browser muss dieselbe Zeichnung ergeben."""

    def test_import(self):
        text = dxf.export(beispiel_dokument())
        with tempfile.NamedTemporaryFile("w", suffix=".dxf", encoding="utf-8",
                                         delete=False) as fh:
            fh.write(text)
            path = Path(fh.name)
        try:
            js = json.loads(run_node(f"""
import fs from 'node:fs';
const IMP = await import('./import-dxf.js');
const doc = IMP.parse(fs.readFileSync({json.dumps(str(path))}, 'utf8'));
const counts = {{}};
for (const e of doc.entities) counts[e.type] = (counts[e.type] || 0) + 1;
console.log(JSON.stringify({{ entities: doc.entities.length,
  types: counts, layers: doc.layers.map(l => l.name).sort() }}));
"""))
        finally:
            path.unlink(missing_ok=True)

        py = dxf.load(text)
        from collections import Counter
        self.assertEqual(js["entities"], len(py.entities))
        self.assertEqual({k: v for k, v in sorted(js["types"].items())},
                         dict(sorted(Counter(e["type"] for e in py.entities).items())))
        self.assertEqual(js["layers"], sorted(py.layer_names()))


class TestBildschirmDeckung(unittest.TestCase):
    """Jede Entitaetsart muss auch **am Bildschirm** gezeichnet werden.

    Export und Anzeige liefen einmal auseinander: Ellipse, Hinweislinie,
    Oberflaechenzeichen und Form-/Lagerahmen standen im PDF, blieben auf der
    Leinwand aber unsichtbar, weil ``render.js`` keinen Fall dafuer hatte.
    Dieser Test vergleicht die Faelle des Renderers mit den bekannten Arten.
    """

    def faelle(self, quelle: str, funktion: str) -> set[str]:
        """Die ``case "..."``-Marken eines Blocks einsammeln."""
        start = quelle.index(funktion)
        tiefe, i, ende = 0, quelle.index("{", start), None
        for pos in range(i, len(quelle)):
            if quelle[pos] == "{":
                tiefe += 1
            elif quelle[pos] == "}":
                tiefe -= 1
                if tiefe == 0:
                    ende = pos
                    break
        block = quelle[start:ende]
        return set(re.findall(r'case\s+"([a-z]+)"', block))

    def test_renderer_kennt_jede_art(self):
        from daro_cad.model import ENTITY_TYPES
        src = (ROOT / "web" / "js" / "render.js").read_text(encoding="utf-8")
        gezeichnet = self.faelle(src, "  entity(e, override")
        fehlend = set(ENTITY_TYPES) - gezeichnet
        self.assertEqual(fehlend, set(),
                         f"render.js zeichnet diese Arten nicht: {sorted(fehlend)}")

    def test_primitive_fuer_jede_art(self):
        """Auch der Export-Weg muss jede Art kennen -- in beiden Kernen."""
        from daro_cad.model import ENTITY_TYPES
        from daro_cad import primitives
        doc = Document()
        muster = {
            "line": {"a": [0, 0], "b": [10, 0]},
            "circle": {"c": [0, 0], "r": 5},
            "arc": {"c": [0, 0], "r": 5, "start": 0, "end": 90},
            "polyline": {"pts": [[0, 0], [10, 0], [10, 10]]},
            "text": {"p": [0, 0], "h": 3.5, "text": "A"},
            "dim": {"kind": "linear", "p1": [0, 0], "p2": [10, 0], "pos": [5, -5]},
            "point": {"p": [0, 0]},
            "hatch": {"pts": [[0, 0], [10, 0], [10, 10]]},
            "ellipse": {"c": [0, 0], "rx": 10, "ry": 5},
            "leader": {"p1": [0, 0], "p2": [10, 10], "text": "A"},
            "surface": {"p": [0, 0], "kind": "machined", "value": "Ra 1,6"},
            "fcf": {"p": [0, 0], "sym": "Ebenheit", "tol": "0,1"},
            "insert": {"name": "Probe", "p": [20, 20], "rot": 30, "scale": 2},
        }
        doc.define_block("Probe", [{"type": "circle", "c": [0, 0], "r": 4,
                                    "layer": "Kontur"}])
        self.assertEqual(set(muster), set(ENTITY_TYPES), "Muster fehlt eine Art")
        for art, felder in muster.items():
            ent = doc.add({"type": art, "layer": "Kontur", **felder})
            prims = primitives.entity_primitives(doc, ent)
            self.assertTrue(prims, f"{art} erzeugt keine Zeichenelemente")


class TestBuendel(unittest.TestCase):
    """Die eigenstaendige HTML-Datei muss sich erzeugen lassen und vollstaendig sein."""

    def test_bau(self):
        import build_standalone
        self.assertEqual(build_standalone.build(), 0)
        target = ROOT / "DARO-CAD.html"
        self.assertTrue(target.is_file())
        html = target.read_text(encoding="utf-8")

        # Kein Nachladen externer Dateien -- das scheitert bei file:// sonst
        self.assertNotIn('src="js/', html)
        self.assertNotIn('href="css/', html)
        self.assertIn("<style>", html)
        for name in build_standalone.MODULES:
            self.assertIn(build_standalone.module_var(name), html, name)
        self.assertGreater(len(html), 150_000)

    def test_exportnamen_werden_erkannt(self):
        import build_standalone
        src = (ROOT / "web" / "js" / "prims.js").read_text(encoding="utf-8")
        names = build_standalone.export_names(src)
        # mehrfache Deklarationen in einer Zeile muessen vollstaendig erfasst sein
        for expected in ("ARROW_LEN", "SHEET_LW", "TITLE_BLOCK_H", "dimPrimitives",
                         "sheetPrimitives", "entityPrimitives"):
            self.assertIn(expected, names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
