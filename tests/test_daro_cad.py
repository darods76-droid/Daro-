"""Testsuite fuer den DARO-CAD-Kern.

Ausfuehren mit:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import base64
import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daro_cad import dxf, geom, model, pdf_export, primitives, solid, svg_export, views
from daro_cad.model import Document, normalize_entity, outline_points, parse_scale


def rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def circle_pts(cx, cy, r, steps=36):
    return [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
            for a in range(0, 360, 360 // steps)]


class TestGeom(unittest.TestCase):
    def test_bulge_halbkreis(self):
        center, radius, start, end = geom.bulge_to_arc((0, 0), (10, 0), 1.0)
        self.assertAlmostEqual(center[0], 5.0)
        self.assertAlmostEqual(center[1], 0.0, places=6)
        self.assertAlmostEqual(radius, 5.0)
        self.assertAlmostEqual(geom.arc_sweep(start, end), 180.0, places=5)

    def test_bulge_vorzeichen(self):
        """Positiver Bulge laeuft gegen den Uhrzeigersinn (DXF-Konvention)."""
        c, r, s, e = geom.bulge_to_arc((0, 0), (10, 0), 0.1)
        self.assertGreater(c[1], 0)                      # Mittelpunkt links der Fahrtrichtung
        mid = geom.arc_point(c, r, s + geom.arc_sweep(s, e) / 2)
        self.assertLess(mid[1], 0)                       # Bogen woelbt sich nach unten

    def test_schnittpunkte(self):
        self.assertEqual(geom.line_line_intersection((0, 0), (10, 0), (5, -5), (5, 5)), (5.0, 0.0))
        self.assertIsNone(geom.line_line_intersection((0, 0), (10, 0), (0, 1), (10, 1)))
        self.assertEqual(len(geom.line_circle_intersection((-10, 0), (10, 0), (0, 0), 5)), 2)
        self.assertEqual(len(geom.circle_circle_intersection((0, 0), 5, (8, 0), 5)), 2)
        self.assertEqual(geom.circle_circle_intersection((0, 0), 5, (50, 0), 5), [])

    def test_bogen_abflachung(self):
        pts = geom.flatten_arc((0, 0), 100, 0, 90, max_sagitta=0.05)
        for p in pts:
            self.assertAlmostEqual(geom.dist((0, 0), p), 100.0, places=6)
        # Stichmass eingehalten?
        for a, b in zip(pts, pts[1:]):
            mid = geom.lerp(a, b, 0.5)
            self.assertLess(100.0 - geom.dist((0, 0), mid), 0.05 + 1e-9)

    def test_punkt_in_polygon(self):
        square = rect(0, 0, 10, 10)
        self.assertTrue(geom.point_in_polygon((5, 5), square))
        self.assertFalse(geom.point_in_polygon((15, 5), square))
        self.assertTrue(geom.point_in_polygon((0, 5), square))     # Rand zaehlt als innen


class TestModel(unittest.TestCase):
    def test_massstab(self):
        self.assertEqual(parse_scale("1:2"), 0.5)
        self.assertEqual(parse_scale("2:1"), 2.0)
        self.assertEqual(parse_scale("kaputt"), 1.0)

    def test_json_rundlauf(self):
        doc = Document()
        doc.meta["title"] = "Träger"
        doc.add({"type": "line", "a": [0, 0], "b": [100, 0]})
        doc.add({"type": "polyline", "pts": rect(0, 0, 50, 30), "closed": True,
                 "bulges": [0, 0.5, 0, 0]})
        doc.add({"type": "dim", "kind": "linear", "p1": [0, 0], "p2": [100, 0], "pos": [50, -20]})
        again = Document.from_json(doc.to_json())
        self.assertEqual(len(again.entities), 3)
        self.assertEqual(again.meta["title"], "Träger")
        self.assertEqual(again.entities[1]["bulges"][1], 0.5)

    def test_unbekannter_typ(self):
        with self.assertRaises(ValueError):
            normalize_entity({"type": "kaputt"})

    def test_unbekannter_layer_faellt_zurueck(self):
        doc = Document.from_dict({"entities": [
            {"type": "line", "a": [0, 0], "b": [1, 1], "layer": "gibtsnicht"}]})
        self.assertEqual(doc.entities[0]["layer"], doc.layers[0].name)

    def test_bogen_umriss(self):
        e = normalize_entity({"type": "arc", "c": [0, 0], "r": 10, "start": 0, "end": 90})
        pts = outline_points(e)
        self.assertAlmostEqual(pts[0][0], 10.0)
        self.assertAlmostEqual(pts[-1][1], 10.0)


class TestBemassung(unittest.TestCase):
    def test_masszahlen(self):
        lin = normalize_entity({"type": "dim", "kind": "linear",
                                "p1": [0, 0], "p2": [100, 0], "pos": [50, -20]})
        self.assertEqual(primitives.dim_measure(lin), 100.0)
        self.assertEqual(primitives.dim_text(lin), "100")

        dia = normalize_entity({"type": "dim", "kind": "diameter",
                                "p1": [0, 0], "p2": [0, 20], "pos": [40, 40]})
        self.assertEqual(primitives.dim_text(dia), "Ø40")

        rad = normalize_entity({"type": "dim", "kind": "radius",
                                "p1": [0, 0], "p2": [12.5, 0], "pos": [30, 30]})
        self.assertEqual(primitives.dim_text(rad), "R12,5")

        ang = normalize_entity({"type": "dim", "kind": "angular", "center": [0, 0],
                                "p1": [10, 0], "p2": [0, 10], "pos": [15, 15], "decimals": 0})
        self.assertEqual(primitives.dim_text(ang), "90°")

    def test_punkt_statt_komma(self):
        d = normalize_entity({"type": "dim", "kind": "linear",
                              "p1": [0, 0], "p2": [12.5, 0], "pos": [6, -10]})
        self.assertEqual(primitives.dim_text(d, comma=True), "12,5")
        self.assertEqual(primitives.dim_text(d, comma=False), "12.5")

    def test_pfeile_und_hilfslinien(self):
        d = normalize_entity({"type": "dim", "kind": "linear",
                              "p1": [0, 0], "p2": [100, 0], "pos": [50, -20]})
        prims = primitives.dim_primitives(d, "#000", 0.25, 1.0)
        kinds = [p["k"] for p in prims]
        self.assertEqual(kinds.count("fill"), 2)          # zwei Pfeilspitzen
        self.assertEqual(kinds.count("text"), 1)
        self.assertGreaterEqual(kinds.count("line"), 3)   # 2 Hilfslinien + Masslinie

    def test_enges_mass_setzt_pfeile_nach_aussen(self):
        d = normalize_entity({"type": "dim", "kind": "linear",
                              "p1": [0, 0], "p2": [4, 0], "pos": [2, -10]})
        prims = primitives.dim_primitives(d, "#000", 0.25, 1.0)
        line = [p for p in prims if p["k"] == "line"][-1]
        self.assertLess(line["a"][0], 0)                  # Masslinie ragt hinaus

    def test_kleine_bohrung_ohne_masslinie_im_kreis(self):
        """Bei engen Bohrungen nur Hinweislinie mit einem Pfeil (ISO 129-1)."""
        klein = normalize_entity({"type": "dim", "kind": "diameter",
                                  "p1": [0, 0], "p2": [0, 3.5], "pos": [20, 20]})
        gross = normalize_entity({"type": "dim", "kind": "diameter",
                                  "p1": [0, 0], "p2": [0, 12], "pos": [30, 30]})
        klein_k = [p["k"] for p in primitives.dim_primitives(klein, "#000", 0.25, 1.0)]
        gross_k = [p["k"] for p in primitives.dim_primitives(gross, "#000", 0.25, 1.0)]
        self.assertEqual(klein_k.count("fill"), 1)
        self.assertEqual(gross_k.count("fill"), 2)
        self.assertEqual(klein_k.count("line"), 2)    # nur Hinweislinie und Auslauf

    def test_schraffur_liegt_innen(self):
        lines = primitives.hatch_lines(rect(0, 0, 40, 20), 45, 3)
        self.assertGreater(len(lines), 5)
        for a, b in lines:
            for p in (a, b, geom.lerp(a, b, 0.5)):
                self.assertTrue(geom.point_in_polygon(p, rect(0, 0, 40, 20)))


class TestSchriftfeld(unittest.TestCase):
    def test_zellen_passen_ins_feld(self):
        cells = primitives.title_block_cells(Document().meta)
        for c in cells:
            self.assertLessEqual(c["x"] + c["w"], model.TITLE_BLOCK_W + 1e-9)
            self.assertLessEqual(c["y"] + c["h"], model.TITLE_BLOCK_H + 1e-9)
        self.assertTrue(any(c["label"] == "Maßstab" for c in cells))
        self.assertTrue(any(c["label"] == "Zeichnungsnummer" for c in cells))

    def test_blatt_masse(self):
        doc = Document()
        doc.meta["sheet"] = "A3"
        self.assertEqual(doc.sheet_size(), (420.0, 297.0))
        doc.meta["scale"] = "1:2"
        self.assertEqual(doc.sheet_size_model(), (840.0, 594.0))

    def test_projektionssymbol_seitenwechsel(self):
        first = primitives.projection_symbol(0, 0, 6, True, "#000", 0.25)
        third = primitives.projection_symbol(0, 0, 6, False, "#000", 0.25)
        # Methode 1: Kreise rechts; Methode 3: Kreise links
        self.assertGreater(first[0]["c"][0], 0)
        self.assertLess(third[0]["c"][0], 0)


class TestExport(unittest.TestCase):
    def setUp(self):
        self.doc = Document()
        self.doc.meta.update({"title": "Prüfteil", "scale": "1:1", "sheet": "A4L"})
        self.doc.add({"type": "polyline", "pts": rect(60, 80, 100, 60), "closed": True,
                      "layer": "Kontur"})
        self.doc.add({"type": "circle", "c": [110, 110], "r": 20, "layer": "Kontur"})
        self.doc.add({"type": "arc", "c": [60, 80], "r": 15, "start": 0, "end": 90,
                      "layer": "Mittellinie"})
        self.doc.add({"type": "text", "p": [70, 150], "h": 5, "text": "Ø40 H7", "layer": "Text"})
        self.doc.add({"type": "dim", "kind": "linear", "p1": [60, 80], "p2": [160, 80],
                      "pos": [110, 60], "layer": "Bemassung"})

    def test_svg(self):
        out = svg_export.render(self.doc)
        self.assertTrue(out.startswith("<?xml"))
        self.assertIn('width="297mm"', out)
        self.assertIn('height="210mm"', out)
        self.assertIn("<circle", out)
        self.assertIn("Ø40 H7", out)
        self.assertIn("Prüfteil", out)

    def test_svg_ohne_rahmen(self):
        with_sheet = svg_export.render(self.doc, with_sheet=True)
        without = svg_export.render(self.doc, with_sheet=False)
        self.assertLess(len(without), len(with_sheet))
        self.assertNotIn("Zeichnungsnummer", without)

    def test_pdf_struktur(self):
        data = pdf_export.render(self.doc)
        self.assertTrue(data.startswith(b"%PDF-1.4"))
        self.assertTrue(data.rstrip().endswith(b"%%EOF"))
        self.assertIn(b"/MediaBox", data)
        self.assertIn(b"startxref", data)
        # Querverweistabelle muss auf gueltige Objektpositionen zeigen
        pos = int(data.rsplit(b"startxref", 1)[1].split()[0])
        self.assertEqual(data[pos:pos + 4], b"xref")

    def test_pdf_textbreite(self):
        self.assertGreater(pdf_export.text_width("MMMM", 10), pdf_export.text_width("iiii", 10))

    def test_dxf_rundlauf(self):
        text = dxf.export(self.doc, with_sheet=False)
        self.assertIn("AC1009", text)
        back = dxf.load(text)
        types = sorted(e["type"] for e in back.entities)
        self.assertIn("circle", types)
        self.assertIn("arc", types)
        self.assertIn("polyline", types)
        self.assertIn("text", types)
        circle = next(e for e in back.entities if e["type"] == "circle")
        self.assertAlmostEqual(circle["r"], 20.0)
        self.assertAlmostEqual(circle["c"][0], 110.0)

    def test_dxf_bulge_bleibt_erhalten(self):
        doc = Document()
        doc.add({"type": "polyline", "pts": [(0, 0), (50, 0), (50, 40)],
                 "bulges": [0.5, 0, 0], "closed": True})
        back = dxf.load(dxf.export(doc, with_sheet=False))
        pl = next(e for e in back.entities if e["type"] == "polyline")
        self.assertAlmostEqual(pl["bulges"][0], 0.5)
        self.assertTrue(pl["closed"])

    def test_dxf_layer_und_farben(self):
        text = dxf.export(self.doc)
        self.assertIn("Mittellinie", text)
        self.assertIn("CENTER", text)
        back = dxf.load(text)
        self.assertIn("Rahmen", back.layer_names())

    def test_dxf_kaputte_datei(self):
        doc = dxf.load("völliger Unsinn\nohne Gruppencodes")
        self.assertEqual(len(doc.entities), 0)


class TestSolid(unittest.TestCase):
    def test_extrusion_kennwerte(self):
        s = solid.extrude(rect(0, 0, 80, 50), [circle_pts(40, 25, 10)], 12)
        self.assertEqual(len(s["verts"]), (4 + 36) * 2)
        erwartet = (80 * 50 - math.pi * 100) * 12
        self.assertLess(abs(solid.volume(s) - erwartet) / erwartet, 0.01)
        self.assertAlmostEqual(solid.mass(s), solid.volume(s) / 1e6 * 7.85)

    def test_konturen_ketten(self):
        ents = [normalize_entity(e) for e in [
            {"type": "line", "a": (0, 0), "b": (50, 0)},
            {"type": "line", "a": (50, 0), "b": (50, 30)},
            {"type": "line", "a": (50, 30), "b": (0, 30)},
            {"type": "line", "a": (0, 30), "b": (0, 0)},
            {"type": "circle", "c": (25, 15), "r": 6}]]
        loops = solid.build_loops(ents)
        self.assertEqual(len(loops), 2)
        profiles = solid.classify_loops(loops)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(len(profiles[0]["holes"]), 1)
        self.assertEqual(len(profiles[0]["outer"]), 4)

    def test_offene_kontur_wird_verworfen(self):
        ents = [normalize_entity({"type": "line", "a": (0, 0), "b": (50, 0)})]
        self.assertEqual(solid.build_loops(ents), [])

    def test_negative_hoehe(self):
        s = solid.extrude(rect(0, 0, 10, 10), [], -5)
        self.assertLess(s["z0"], s["z1"])
        self.assertAlmostEqual(solid.volume(s), 500.0)


class TestViews(unittest.TestCase):
    def setUp(self):
        self.solid = solid.extrude(rect(0, 0, 80, 50), [circle_pts(40, 25, 10)], 12)

    def test_vorderansicht_zeigt_kontur(self):
        data = views.project([self.solid], "front")
        # Aussenkontur (4) + Bohrung (36), keine doppelten Kanten
        self.assertEqual(len(data["visible"]), 40)
        self.assertEqual(len(data["hidden"]), 0)

    def test_draufsicht_zeigt_bohrung_verdeckt(self):
        data = views.project([self.solid], "top")
        self.assertEqual(len(data["visible"]), 4)          # Rechteck 80 x 12
        self.assertEqual(len(data["hidden"]), 2)           # zwei Bohrungswandungen
        xs = sorted(round(seg[0][0], 3) for seg in data["hidden"])
        self.assertEqual(xs, [30.0, 50.0])

    def test_seitenansicht(self):
        data = views.project([self.solid], "left")
        self.assertEqual(len(data["visible"]), 4)
        self.assertEqual(len(data["hidden"]), 2)

    def test_verdeckte_weicht_sichtbarer_linie(self):
        """Deckungsgleiche Kanten: sichtbar gewinnt (DIN ISO 128-24)."""
        data = views.project([self.solid], "front")
        for hidden in data["hidden"]:
            for visible in data["visible"]:
                self.assertFalse(
                    geom.dist(hidden[0], visible[0]) < 1e-6 and
                    geom.dist(hidden[1], visible[1]) < 1e-6)

    def test_anordnung_methode_1(self):
        ents = views.derive([self.solid], ("front", "top", "left"), projection="first")
        def box(name):
            pts = []
            for e in ents:
                if e.get("view") == name and e["type"] == "line":
                    pts.extend([e["a"], e["b"]])
            return geom.bbox(pts)
        front, top, left = box("front"), box("top"), box("left")
        self.assertLess(top[3], front[1])        # Draufsicht unterhalb
        self.assertGreater(left[0], front[2])    # Ansicht von links rechts daneben

    def test_anordnung_methode_3(self):
        ents = views.derive([self.solid], ("front", "top", "left"), projection="third")
        def box(name):
            pts = []
            for e in ents:
                if e.get("view") == name and e["type"] == "line":
                    pts.extend([e["a"], e["b"]])
            return geom.bbox(pts)
        self.assertGreater(box("top")[1], box("front")[3])
        self.assertLess(box("left")[2], box("front")[0])

    def test_mittellinien_und_beschriftung(self):
        ents = views.derive([self.solid])
        layers = {e["layer"] for e in ents}
        self.assertIn("Kontur", layers)
        self.assertIn("Verdeckt", layers)
        self.assertIn("Mittellinie", layers)
        texte = [e["text"] for e in ents if e["type"] == "text"]
        self.assertIn("Vorderansicht", texte)
        self.assertIn("Draufsicht", texte)


class TestServer(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["DARO_CAD_WORKSPACE"] = self._tmp.name
        from daro_cad import server
        self.server = server
        self.doc = Document()
        self.doc.add({"type": "polyline", "pts": rect(0, 0, 80, 50), "closed": True})
        self.doc.add({"type": "circle", "c": [40, 25], "r": 10})

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.pop("DARO_CAD_WORKSPACE", None)

    def payload(self, **extra):
        return {"document": self.doc.to_dict(), **extra}

    def test_status(self):
        info = self.server.api_status({})
        self.assertTrue(info["ok"])
        self.assertIn("svg", info["freecad"]["formats"])

    def test_speichern_und_laden(self):
        res = self.server.api_save({"name": "Prüfzeichnung", **self.payload()})
        self.assertTrue(res["ok"])
        listing = self.server.api_files({})
        self.assertEqual(listing["files"][0]["name"], "Prüfzeichnung")
        loaded = self.server.api_load({"name": "Prüfzeichnung"})
        self.assertEqual(len(loaded["document"]["entities"]), 2)

    def test_dateiname_wird_geprueft(self):
        for bad in ("../../etc/passwd", "a/b", "..", ".versteckt", "x" * 130):
            with self.assertRaises(self.server.ApiError, msg=bad):
                self.server.api_save({"name": bad, **self.payload()})

    def test_leerer_name_nutzt_die_benennung(self):
        """Ohne Namen wird die Benennung aus dem Schriftfeld verwendet."""
        self.doc.meta["title"] = "Lagerplatte"
        res = self.server.api_save({"name": "", **self.payload()})
        self.assertEqual(res["name"], "Lagerplatte.darocad.json")
        self.assertTrue(Path(res["path"]).is_file())

    def test_extrusion_ueber_api(self):
        res = self.server.api_solids(self.payload(height=15))
        self.assertEqual(res["count"], 1)
        self.assertGreater(res["volume"], 0)
        self.assertEqual(len(res["solids"][0]["profile"]["holes"]), 1)

    def test_ansichten_ueber_api(self):
        solids = self.server.api_solids(self.payload(height=15))["solids"]
        res = self.server.api_views(self.payload(solids=solids))
        self.assertGreater(res["count"], 10)
        self.assertTrue(any(e["layer"] == "Verdeckt" for e in res["entities"]))

    def test_ansichten_ohne_koerper(self):
        with self.assertRaises(self.server.ApiError):
            self.server.api_views(self.payload())

    def test_export_formate(self):
        for fmt, head in (("svg", b"<?xml"), ("pdf", b"%PDF"), ("json", b"{")):
            res = self.server.api_export(self.payload(), fmt)
            data = base64.b64decode(res["data"])
            self.assertTrue(data.startswith(head), fmt)
            self.assertTrue(res["filename"].endswith(fmt.replace("json", "json")))

    def test_export_unbekannt(self):
        with self.assertRaises(self.server.ApiError):
            self.server.api_export(self.payload(), "dwg")

    def test_freecad_format_ohne_freecad(self):
        from daro_cad import freecad_bridge
        if freecad_bridge.status()["available"]:
            self.skipTest("FreeCAD ist installiert -- Fehlerpfad nicht pruefbar")
        with self.assertRaises(self.server.ApiError) as ctx:
            self.server.api_export(self.payload(solids=[{"verts": [[0, 0, 0]]}]), "step")
        self.assertIn("FreeCAD", str(ctx.exception))

    def test_import_dxf(self):
        text = dxf.export(self.doc, with_sheet=False)
        res = self.server.api_import({
            "filename": "test.dxf",
            "data": base64.b64encode(text.encode("utf-8")).decode("ascii")})
        self.assertGreaterEqual(res["entities"], 2)

    def test_import_unbekanntes_format(self):
        with self.assertRaises(self.server.ApiError):
            self.server.api_import({"filename": "x.dwg", "data": base64.b64encode(b"x").decode()})


class TestFreeCADBridge(unittest.TestCase):
    def test_status_meldet_formate(self):
        from daro_cad import freecad_bridge
        info = freecad_bridge.status()
        self.assertIn("svg", info["formats"])
        self.assertEqual(info["available"], bool(info["executable"]) or info["module"])

    def test_skripte_sind_gueltiges_python(self):
        from daro_cad import freecad_bridge
        compile(freecad_bridge.BUILD_SCRIPT, "build.py", "exec")
        compile(freecad_bridge.READ_SCRIPT, "read.py", "exec")

    def test_ohne_ziel_kein_lauf(self):
        from daro_cad import freecad_bridge
        with self.assertRaises(ValueError):
            freecad_bridge.build(Document())


if __name__ == "__main__":
    unittest.main(verbosity=2)
