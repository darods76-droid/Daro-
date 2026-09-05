"""Weboberflaeche und JSON-API auf Basis der Standardbibliothek."""

from __future__ import annotations

import json
import threading
import urllib.parse
import webbrowser
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__
from .config import get_settings
from .models import utcnow
from .pipeline import scan
from .store import Store

WEB_DIR = Path(__file__).parent / "web"
_SCAN_LOCK = threading.Lock()

CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml",
                 ".ico": "image/x-icon", ".json": "application/json; charset=utf-8"}


class Handler(BaseHTTPRequestHandler):
    server_version = f"ekp/{__version__}"

    # ── Hilfsfunktionen ──────────────────────────────────────────────────────
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload, status: int = 200) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _static(self, filename: str) -> None:
        # Verzeichniswechsel unterbinden - nur Dateien direkt aus web/.
        safe = Path(filename).name
        path = WEB_DIR / safe
        if not path.is_file():
            self._json({"error": "nicht gefunden"}, 404)
            return
        self._send(200, path.read_bytes(),
                   CONTENT_TYPES.get(path.suffix, "application/octet-stream"))

    def log_message(self, fmt: str, *args) -> None:      # ruhigere Konsole
        return

    # ── Routen ───────────────────────────────────────────────────────────────
    def do_GET(self) -> None:                            # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"
        query = urllib.parse.parse_qs(parsed.query)
        settings = get_settings()

        if route in ("/", "/index.html"):
            self._static("index.html")
        elif route.startswith("/static/"):
            self._static(route[len("/static/"):])
        elif route == "/api/health":
            self._json({"status": "ok", "version": __version__,
                        "calendar_provider": settings.calendar_provider,
                        "news_provider": settings.news_provider})
        elif route == "/api/assessments":
            upcoming = query.get("upcoming", ["1"])[0] != "0"
            with Store(settings.db_path) as store:
                self._json({"assessments": store.latest_assessments(upcoming_only=upcoming),
                            "counts": store.counts(),
                            "generated_at": utcnow().isoformat()})
        elif route == "/api/scoreboard":
            with Store(settings.db_path) as store:
                self._json({**store.scoreboard(), "counts": store.counts(),
                            "priors": store.family_priors()})
        elif route == "/api/news":
            hours = int(query.get("hours", ["96"])[0])
            with Store(settings.db_path) as store:
                items = store.news_since(utcnow() - timedelta(hours=hours))
                self._json({"news": [n.to_dict() for n in items]})
        else:
            self._json({"error": "unbekannte Route"}, 404)

    def do_HEAD(self) -> None:                           # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:                           # noqa: N802
        route = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        if route != "/api/scan":
            self._json({"error": "unbekannte Route"}, 404)
            return
        if not _SCAN_LOCK.acquire(blocking=False):
            self._json({"error": "Ein Scan läuft bereits."}, 409)
            return
        try:
            settings = get_settings()
            with Store(settings.db_path) as store:
                report = scan(settings, store)
                self._json({"summary": report.summary(),
                            "assessments": store.latest_assessments(upcoming_only=True)})
        except Exception as exc:                          # pragma: no cover - Schutznetz
            self._json({"error": f"Scan fehlgeschlagen: {exc}"}, 500)
        finally:
            _SCAN_LOCK.release()


def serve(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"\n  Wirtschaftskalender-Prognose läuft auf {url}")
    print("  Beenden mit Strg+C\n")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Beendet.")
    finally:
        httpd.server_close()
