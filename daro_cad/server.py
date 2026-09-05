"""Lokaler Server: liefert die Zeichen-App und rechnet im Hintergrund.

Bewusst nur mit der Python-Standardbibliothek gebaut -- ``python3 -m daro_cad``
genuegt, es muss nichts installiert werden.

Endpunkte
    GET  /                     Zeichen-App
    GET  /api/status           Faehigkeiten, FreeCAD-Erkennung
    GET  /api/files            Zeichnungen im Arbeitsordner
    GET  /api/file?name=       Zeichnung laden
    POST /api/file?name=       Zeichnung speichern
    POST /api/import           DXF (oder FCStd/STEP mit FreeCAD) einlesen
    POST /api/export/<format>  svg | dxf | pdf | json | fcstd | step | stl
    POST /api/solids           Profile extrudieren, Kennwerte berechnen
    POST /api/views            Ansichten mit verdeckten Kanten ableiten
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import posixpath
import re
import socketserver
import sys
import threading
import traceback
import urllib.parse
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import dxf as dxf_mod
from . import freecad_bridge, pdf_export, solid as solid_mod, svg_export, views as views_mod
from .model import Document, SCALES, SHEETS

def _find_web_root() -> Path:
    """Ordner mit der Zeichen-App suchen.

    Deckt beide Faelle ab: Start aus dem Quellordner und Start nach einer
    Installation, bei der ``web/`` unter ``share/daro-cad/`` landet.
    """
    here = Path(__file__).resolve().parent
    candidates = [
        Path(os.environ["DARO_CAD_WEB"]) if os.environ.get("DARO_CAD_WEB") else None,
        here.parent / "web",                       # Quellordner
        here / "web",                              # als Paketdaten mitgeliefert
        Path(sys.prefix) / "share" / "daro-cad" / "web",
        Path(sys.prefix) / "local" / "share" / "daro-cad" / "web",
    ]
    for folder in candidates:
        if folder and (folder / "index.html").is_file():
            return folder.resolve()
    return (here.parent / "web").resolve()         # Fehlermeldung spaeter, mit Pfad


WEB_ROOT = _find_web_root()
MAX_BODY = 32 * 1024 * 1024
SAFE_NAME = re.compile(r"^[\w \-.()äöüÄÖÜß]{1,120}$")


class ApiError(Exception):
    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.code = code


def workspace() -> Path:
    folder = Path(os.environ.get("DARO_CAD_WORKSPACE", Path.home() / "DaroCAD"))
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _safe_path(name: str, suffix: str = ".darocad.json") -> Path:
    name = (name or "").strip()
    if not name:
        raise ApiError("Kein Dateiname angegeben.")
    if not SAFE_NAME.match(name) or "/" in name or "\\" in name or name.startswith("."):
        raise ApiError("Ungueltiger Dateiname.")
    if not name.endswith(suffix):
        name += suffix
    return workspace() / name


def _document(payload: Dict[str, Any]) -> Document:
    data = payload.get("document") if isinstance(payload, dict) else None
    if data is None:
        data = payload
    if not isinstance(data, dict):
        raise ApiError("Zeichnungsdaten fehlen.")
    try:
        return Document.from_dict(data)
    except Exception as exc:
        raise ApiError(f"Zeichnung nicht lesbar: {exc}")


def _solids_from(payload: Dict[str, Any], doc: Document) -> List[Dict[str, Any]]:
    """Koerper aus der Nutzlast uebernehmen oder aus dem Dokument neu bauen."""
    solids = payload.get("solids")
    if solids:
        return [s for s in solids if s.get("verts")]
    return [rebuild_solid(spec) for spec in doc.solids if spec.get("profile")]


def rebuild_solid(spec: Dict[str, Any]) -> Dict[str, Any]:
    profile = spec.get("profile") or {}
    return solid_mod.extrude(
        [tuple(p) for p in profile.get("outer", [])],
        [[tuple(p) for p in h] for h in profile.get("holes", [])],
        float(spec.get("height", 10.0)),
        float(spec.get("z0", 0.0)),
        str(spec.get("name") or "Koerper"),
    )


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def api_status(_payload: Dict[str, Any]) -> Dict[str, Any]:
    info = freecad_bridge.status()
    return {
        "ok": True,
        "freecad": info,
        "workspace": str(workspace()),
        "sheets": sorted(SHEETS.keys()),
        "scales": SCALES,
        "today": date.today().strftime("%d.%m.%Y"),
        "version": "1.0",
    }


def api_files(_payload: Dict[str, Any]) -> Dict[str, Any]:
    items = []
    for path in sorted(workspace().glob("*.darocad.json")):
        stat = path.stat()
        items.append({"name": path.name.replace(".darocad.json", ""),
                      "size": stat.st_size, "modified": int(stat.st_mtime)})
    return {"ok": True, "files": items, "folder": str(workspace())}


def api_load(payload: Dict[str, Any]) -> Dict[str, Any]:
    path = _safe_path(payload.get("name", ""))
    if not path.exists():
        raise ApiError(f"'{path.name}' nicht gefunden.", 404)
    return {"ok": True, "document": json.loads(path.read_text(encoding="utf-8"))}


def api_save(payload: Dict[str, Any]) -> Dict[str, Any]:
    doc = _document(payload)
    path = _safe_path(payload.get("name", "") or doc.meta.get("title", "Zeichnung"))
    path.write_text(doc.to_json(), encoding="utf-8")
    return {"ok": True, "name": path.name, "path": str(path)}


def api_solids(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Ausgewaehlte Elemente zu Konturen ketten und extrudieren."""
    doc = _document(payload)
    ids = set(payload.get("ids") or [])
    entities = [e for e in doc.entities if not ids or e.get("id") in ids]
    entities = [e for e in entities if e.get("type") in ("line", "arc", "circle", "polyline")]
    loops = solid_mod.build_loops(entities, tol=float(payload.get("tolerance", 0.05)))
    if not loops:
        raise ApiError("Keine geschlossene Kontur gefunden. "
                       "Die Umrisse muessen luekenlos aneinanderstossen.")
    height = float(payload.get("height", 10.0))
    z0 = float(payload.get("z0", 0.0))
    density = float(payload.get("density", 7.85))
    solids = []
    for i, profile in enumerate(solid_mod.classify_loops(loops)):
        sol = solid_mod.extrude(profile["outer"], profile["holes"], height, z0,
                                payload.get("name") or f"Koerper {i + 1}")
        solids.append(sol)
    return {
        "ok": True,
        "solids": solids,
        "count": len(solids),
        "volume": sum(solid_mod.volume(s) for s in solids),
        "mass": sum(solid_mod.mass(s, density) for s in solids),
        "bbox": solid_mod.bbox3(solids),
    }


def api_views(payload: Dict[str, Any]) -> Dict[str, Any]:
    doc = _document(payload)
    solids = _solids_from(payload, doc)
    if not solids:
        raise ApiError("Kein Koerper vorhanden. Bitte zuerst ein Profil extrudieren.")
    origin = payload.get("origin") or [0.0, 0.0]
    entities = views_mod.derive(
        solids,
        views=payload.get("views") or ["front", "top", "left"],
        origin=(float(origin[0]), float(origin[1])),
        gap=float(payload.get("gap", 25.0)),
        projection=doc.meta.get("projection", "first"),
        labels=bool(payload.get("labels", True)),
        center_lines=bool(payload.get("centerLines", True)),
    )
    return {"ok": True, "entities": entities, "count": len(entities)}


def _export_bytes(doc: Document, fmt: str, payload: Dict[str, Any]) -> Tuple[bytes, str, str]:
    """Zeichnung exportieren -> (Daten, MIME-Typ, Dateiendung)."""
    with_sheet = bool(payload.get("withSheet", True))
    if fmt == "svg":
        return svg_export.render(doc, with_sheet).encode("utf-8"), "image/svg+xml", "svg"
    if fmt == "pdf":
        return pdf_export.render(doc, with_sheet), "application/pdf", "pdf"
    if fmt == "dxf":
        text = dxf_mod.export(doc, with_sheet=with_sheet)
        return text.encode("utf-8"), "application/dxf", "dxf"
    if fmt == "json":
        return doc.to_json().encode("utf-8"), "application/json", "darocad.json"

    if fmt in ("fcstd", "step", "stl"):
        solids = _solids_from(payload, doc)
        if fmt in ("step", "stl") and not solids:
            raise ApiError(f"Fuer {fmt.upper()} wird ein Koerper benoetigt. "
                           "Bitte zuerst ein Profil extrudieren.")
        suffix = {"fcstd": ".FCStd", "step": ".step", "stl": ".stl"}[fmt]
        out = workspace() / f"{_stem(doc)}{suffix}"
        try:
            freecad_bridge.build(doc, solids, **{fmt: str(out)})
        except freecad_bridge.FreeCADError as exc:
            raise ApiError(str(exc), 501)
        if not out.exists():
            raise ApiError("FreeCAD hat keine Datei geschrieben.", 500)
        mime = {"fcstd": "application/octet-stream", "step": "model/step",
                "stl": "model/stl"}[fmt]
        return out.read_bytes(), mime, suffix.lstrip(".")
    raise ApiError(f"Unbekanntes Format: {fmt}")


def _stem(doc: Document) -> str:
    raw = f"{doc.meta.get('drawingNumber', '')}_{doc.meta.get('title', 'Zeichnung')}".strip("_")
    return re.sub(r"[^\w\-.]+", "_", raw) or "Zeichnung"


def api_export(payload: Dict[str, Any], fmt: str) -> Dict[str, Any]:
    doc = _document(payload)
    data, mime, ext = _export_bytes(doc, fmt, payload)
    result = {"ok": True, "mime": mime, "filename": f"{_stem(doc)}.{ext}",
              "data": base64.b64encode(data).decode("ascii"), "bytes": len(data)}
    if payload.get("save"):
        target = workspace() / result["filename"]
        target.write_bytes(data)
        result["path"] = str(target)
    return result


def api_import(payload: Dict[str, Any]) -> Dict[str, Any]:
    name = str(payload.get("filename") or "")
    raw = payload.get("data")
    if raw is None:
        raise ApiError("Keine Datei uebergeben.")
    try:
        blob = base64.b64decode(raw)
    except Exception:
        raise ApiError("Datei nicht lesbar (Base64 erwartet).")
    lower = name.lower()
    if lower.endswith(".dxf"):
        doc = dxf_mod.load(blob.decode("utf-8", errors="replace"))
    elif lower.endswith((".darocad.json", ".json")):
        doc = Document.from_json(blob.decode("utf-8", errors="replace"))
    elif lower.endswith((".fcstd", ".step", ".stp")):
        safe = re.sub(r"[^\w.-]+", "_", name) or "import"
        tmp = workspace() / ("_import_" + safe)
        tmp.write_bytes(blob)
        try:
            doc = freecad_bridge.import_file(str(tmp))
        except freecad_bridge.FreeCADError as exc:
            raise ApiError(str(exc), 501)
        finally:
            tmp.unlink(missing_ok=True)
    else:
        raise ApiError("Unterstuetzt werden DXF, DARO-CAD-JSON sowie "
                       "FCStd/STEP (mit FreeCAD).")
    return {"ok": True, "document": doc.to_dict(), "entities": len(doc.entities)}


ROUTES: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "/api/status": api_status,
    "/api/files": api_files,
    "/api/file/load": api_load,
    "/api/file/save": api_save,
    "/api/solids": api_solids,
    "/api/views": api_views,
    "/api/import": api_import,
}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "DaroCAD/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.environ.get("DARO_CAD_VERBOSE"):
            super().log_message(fmt, *args)

    # -- Hilfen ---------------------------------------------------------
    def _send(self, status: int, body: bytes, mime: str = "application/json",
              extra: Optional[Dict[str, str]] = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, data: Dict[str, Any]) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _error(self, exc: Exception) -> None:
        code = getattr(exc, "code", 500)
        if code >= 500:
            traceback.print_exc()
        self._json(code, {"ok": False, "error": str(exc)})

    def _body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ApiError("Datei zu gross (max. 32 MB).", 413)
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            raise ApiError("Ungueltiges JSON im Anfragekoerper.")

    # -- Methoden -------------------------------------------------------
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path.startswith("/api/"):
                query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
                if path == "/api/file":
                    return self._json(200, api_load(query))
                handler = ROUTES.get(path)
                if handler is None:
                    raise ApiError("Unbekannter Endpunkt.", 404)
                return self._json(200, handler(query))
            return self._static(path)
        except Exception as exc:
            self._error(exc)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            payload = self._body()
            if path.startswith("/api/export/"):
                return self._json(200, api_export(payload, path.rsplit("/", 1)[-1].lower()))
            if path == "/api/file":
                query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
                payload.setdefault("name", query.get("name", ""))
                return self._json(200, api_save(payload))
            handler = ROUTES.get(path)
            if handler is None:
                raise ApiError("Unbekannter Endpunkt.", 404)
            return self._json(200, handler(payload))
        except Exception as exc:
            self._error(exc)

    # -- statische Dateien ----------------------------------------------
    def _static(self, path: str) -> None:
        if path in ("/", ""):
            path = "/index.html"
        clean = posixpath.normpath(urllib.parse.unquote(path)).lstrip("/")
        target = (WEB_ROOT / clean).resolve()
        try:
            target.relative_to(WEB_ROOT.resolve())
        except ValueError:
            raise ApiError("Zugriff verweigert.", 403)
        if not target.is_file():
            raise ApiError("Nicht gefunden.", 404)
        mime, _ = mimetypes.guess_type(str(target))
        if target.suffix == ".js":
            mime = "text/javascript"
        body = target.read_bytes()
        charset = "; charset=utf-8" if (mime or "").startswith(("text/", "image/svg")) else ""
        self._send(200, body, (mime or "application/octet-stream") + charset)


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    mimetypes.add_type("text/javascript", ".js")
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    url = f"http://{host}:{port}/"
    info = freecad_bridge.status()
    print("DARO-CAD  --  Technische Zeichnungen")
    print(f"  Adresse       : {url}")
    print(f"  Arbeitsordner : {workspace()}")
    print(f"  FreeCAD       : {info['version'] or 'nicht gefunden (optionale Formate inaktiv)'}")
    print("  Beenden mit Strg+C")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nBeendet.")
    finally:
        httpd.server_close()
