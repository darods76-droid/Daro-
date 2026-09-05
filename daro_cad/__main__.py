"""Startpunkt: ``python3 -m daro_cad``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="daro_cad", description="DARO-CAD -- App fuer technische Zeichnungen")
    parser.add_argument("--host", default="127.0.0.1", help="Adresse (Standard: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port (Standard: 8765)")
    parser.add_argument("--no-browser", action="store_true", help="Browser nicht oeffnen")
    parser.add_argument("--workspace", help="Ordner fuer Zeichnungen")
    sub = parser.add_subparsers(dest="command")

    conv = sub.add_parser("export", help="Zeichnung ohne Oberflaeche exportieren")
    conv.add_argument("source", help="DARO-CAD-JSON oder DXF")
    conv.add_argument("target", help="Zieldatei (.svg .pdf .dxf .FCStd .step .stl)")

    info = sub.add_parser("info", help="Umgebung pruefen")

    args = parser.parse_args(argv)

    import os
    if args.workspace:
        os.environ["DARO_CAD_WORKSPACE"] = args.workspace

    if args.command == "info":
        from . import freecad_bridge
        from .server import workspace
        state = freecad_bridge.status()
        print("DARO-CAD")
        print("  Arbeitsordner :", workspace())
        print("  FreeCAD       :", state["executable"] or "nicht gefunden")
        print("  Version       :", state["version"] or "-")
        print("  Formate       :", ", ".join(state["formats"]))
        return 0

    if args.command == "export":
        return _export(Path(args.source), Path(args.target))

    from .server import serve
    serve(args.host, args.port, not args.no_browser)
    return 0


def _export(source: Path, target: Path) -> int:
    from . import dxf as dxf_mod, pdf_export, svg_export, freecad_bridge
    from .model import Document
    from .server import rebuild_solid

    if not source.exists():
        print(f"Quelle nicht gefunden: {source}", file=sys.stderr)
        return 2
    text = source.read_text(encoding="utf-8", errors="replace")
    doc = dxf_mod.load(text) if source.suffix.lower() == ".dxf" else Document.from_json(text)

    suffix = target.suffix.lower()
    if suffix == ".svg":
        target.write_text(svg_export.render(doc), encoding="utf-8")
    elif suffix == ".pdf":
        target.write_bytes(pdf_export.render(doc))
    elif suffix == ".dxf":
        target.write_text(dxf_mod.export(doc), encoding="utf-8")
    elif suffix in (".json",):
        target.write_text(doc.to_json(), encoding="utf-8")
    elif suffix in (".fcstd", ".step", ".stp", ".stl"):
        solids = [rebuild_solid(s) for s in doc.solids if s.get("profile")]
        key = {"fcstd": "fcstd", "step": "step", "stp": "step", "stl": "stl"}[suffix.lstrip(".")]
        try:
            freecad_bridge.build(doc, solids, **{key: str(target)})
        except freecad_bridge.FreeCADError as exc:
            print(str(exc), file=sys.stderr)
            return 3
    else:
        print(f"Unbekannte Endung: {suffix}", file=sys.stderr)
        return 2
    print(f"{target}  ({target.stat().st_size} Bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
