"""Weboberflaeche, JSON-API und Kommandozeile."""

import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from ekp import server as server_mod
from ekp.cli import bar, fmt_value, main


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["EKP_DB"] = str(Path(cls.tmp.name) / "api.sqlite3")
        os.environ["EKP_CALENDAR_PROVIDER"] = "demo"
        os.environ["EKP_NEWS_PROVIDER"] = "demo"
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_mod.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()
        for key in ("EKP_DB", "EKP_CALENDAR_PROVIDER", "EKP_NEWS_PROVIDER"):
            os.environ.pop(key, None)

    def get(self, path):
        with urllib.request.urlopen(f"{self.base}{path}", timeout=20) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")

    def get_json(self, path):
        status, body, _ = self.get(path)
        return status, json.loads(body)

    def post_json(self, path):
        req = urllib.request.Request(f"{self.base}{path}", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read())

    def test_health(self):
        status, payload = self.get_json("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")

    def test_startseite_und_statische_dateien(self):
        for path, marker in (("/", b"<!doctype html>"), ("/static/style.css", b":root"),
                             ("/static/app.js", b"use strict")):
            status, body, _ = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertIn(marker, body[:400].lower() if path == "/" else body)

    def test_pfadwechsel_wird_abgewehrt(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/static/../../ekp/config.py")
        self.assertEqual(ctx.exception.code, 404)

    def test_unbekannte_route(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/api/gibtesnicht")
        self.assertEqual(ctx.exception.code, 404)

    def test_scan_und_abruf(self):
        status, payload = self.post_json("/api/scan")
        self.assertEqual(status, 200)
        self.assertGreater(payload["summary"]["events_kept"], 0)

        status, payload = self.get_json("/api/assessments")
        self.assertEqual(status, 200)
        self.assertTrue(payload["assessments"])
        first = payload["assessments"][0]
        for key in ("p_above", "p_confirm", "p_below", "verdict", "confidence", "evidence"):
            self.assertIn(key, first)
        self.assertAlmostEqual(first["p_above"] + first["p_confirm"] + first["p_below"],
                               1.0, places=5)

        status, payload = self.get_json("/api/scoreboard")
        self.assertEqual(status, 200)
        self.assertIn("counts", payload)

        status, payload = self.get_json("/api/news?hours=96")
        self.assertEqual(status, 200)
        self.assertTrue(payload["news"])


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["EKP_DB"] = str(Path(self.tmp.name) / "cli.sqlite3")
        os.environ["EKP_CALENDAR_PROVIDER"] = "demo"
        os.environ["EKP_NEWS_PROVIDER"] = "demo"

    def tearDown(self):
        self.tmp.cleanup()
        for key in ("EKP_DB", "EKP_CALENDAR_PROVIDER", "EKP_NEWS_PROVIDER"):
            os.environ.pop(key, None)

    @staticmethod
    def run_quiet(argv):
        """Fuehrt einen CLI-Befehl aus, ohne die Testausgabe zu fluten."""
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(argv)
        return code, buffer.getvalue()

    def test_befehle_laufen_durch(self):
        self.assertEqual(self.run_quiet(["scan", "--json"])[0], 0)
        for argv in (["list"], ["list", "--all"], ["news"], ["verify"], ["score"],
                     ["score", "--json"], ["show", "Verbraucherpreise"]):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_quiet(argv)[0], 0)

    def test_scan_ausgabe_enthaelt_urteile(self):
        code, text = self.run_quiet(["scan"])
        self.assertEqual(code, 0)
        self.assertIn("Anstehende Termine", text)
        self.assertIn("Verbraucherpreise", text)

    def test_json_ausgabe_ist_gueltig(self):
        _, text = self.run_quiet(["scan", "--json"])
        payload = json.loads(text)
        self.assertIn("summary", payload)
        self.assertTrue(payload["assessments"])

    def test_unbekannter_termin_meldet_fehler(self):
        self.run_quiet(["scan", "--json"])
        self.assertEqual(self.run_quiet(["show", "gibtesnicht"])[0], 1)

    def test_formatierung(self):
        self.assertEqual(fmt_value(None), "–")
        self.assertEqual(fmt_value(2.9, "%"), "2.9%")
        self.assertEqual(fmt_value(165.0, "Tsd."), "165 Tsd.")
        self.assertEqual(len(bar(0.5, 10)), 10)
        self.assertEqual(bar(1.0, 4), "████")


if __name__ == "__main__":
    unittest.main()
