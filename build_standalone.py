#!/usr/bin/env python3
"""Die Zeichen-App in eine einzige HTML-Datei buendeln.

Ergebnis: ``DARO-CAD.html`` -- herunterladen, doppelklicken, fertig. Kein Python,
kein Server, keine Installation.

Warum ein Buendel noetig ist: Browser verweigern aus Sicherheitsgruenden das
Nachladen von ES-Modulen ueber ``file://``. Deshalb werden alle Module hier in
je eine Funktion gekapselt und in eine Datei geschrieben; die ``import``-Zeilen
werden dabei in Zugriffe auf die vorher definierten Module umgeschrieben.

Aufruf:  python3 build_standalone.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
TARGET = ROOT / "DARO-CAD.html"

# Reihenfolge nach Abhaengigkeiten -- jedes Modul kennt nur die vorherigen.
MODULES = [
    "geom", "doc", "prims", "solid", "views", "snap", "modify",
    "export-svg", "export-dxf", "export-pdf", "import-dxf",
    "api-local", "render", "tools", "view3d", "app",
]

# app.js spricht die Server-API an; eigenstaendig zeigt derselbe Name auf api-local.
ALIASES = {"api": "api-local"}

IMPORT_RE = re.compile(
    r'^import\s+(?P<what>.+?)\s+from\s+["\'](?P<path>[^"\']+)["\'];?\s*$',
    re.MULTILINE)


def module_var(name: str) -> str:
    return "__m_" + re.sub(r"[^A-Za-z0-9_]", "_", name)


def split_top_level(text: str) -> List[str]:
    """Eine Deklarationsliste an Kommas der obersten Ebene zerlegen."""
    parts, depth, quote, current = [], 0, "", []
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                current.append(ch)
                i += 1
                if i < len(text):
                    current.append(text[i])
                i += 1
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'`":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    if current:
        parts.append("".join(current))
    return parts


def statement_after(src: str, start: int) -> str:
    """Text bis zum Semikolon der obersten Ebene ab ``start``."""
    depth, quote = 0, ""
    i = start
    while i < len(src):
        ch = src[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'`":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ";" and depth == 0:
            return src[start:i]
        i += 1
    return src[start:]


def export_names(src: str) -> List[str]:
    """Alle exportierten Namen eines Moduls einsammeln."""
    names: List[str] = []
    for m in re.finditer(r"^export\s+(?:async\s+)?(?:function|class|let|var)\s+([A-Za-z_$][\w$]*)",
                         src, re.MULTILINE):
        names.append(m.group(1))
    for m in re.finditer(r"^export\s+const\s+", src, re.MULTILINE):
        for part in split_top_level(statement_after(src, m.end())):
            ident = re.match(r"\s*([A-Za-z_$][\w$]*)\s*=", part)
            if ident:
                names.append(ident.group(1))
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def rewrite_imports(src: str) -> str:
    """``import``-Zeilen in Zugriffe auf die schon definierten Module wandeln."""
    def repl(match: re.Match) -> str:
        what = match.group("what").strip()
        path = match.group("path")
        stem = Path(path).stem
        stem = ALIASES.get(stem, stem)
        if stem not in MODULES:
            raise SystemExit(f"Unbekanntes Modul im Import: {path}")
        var = module_var(stem)
        star = re.match(r"\*\s+as\s+([A-Za-z_$][\w$]*)$", what)
        if star:
            return f"const {star.group(1)} = {var};"
        if what.startswith("{"):
            inner = what.strip()[1:-1]
            fields = []
            for piece in split_top_level(inner):
                piece = piece.strip()
                if not piece:
                    continue
                alias = re.match(r"([A-Za-z_$][\w$]*)\s+as\s+([A-Za-z_$][\w$]*)$", piece)
                fields.append(f"{alias.group(1)}: {alias.group(2)}" if alias else piece)
            return "const { " + ", ".join(fields) + " } = " + var + ";"
        raise SystemExit(f"Importform wird nicht unterstuetzt: {what}")
    return IMPORT_RE.sub(repl, src)


def strip_exports(src: str) -> str:
    return re.sub(r"^export\s+", "", src, flags=re.MULTILINE)


def bundle_module(name: str) -> str:
    src = (WEB / "js" / f"{name}.js").read_text(encoding="utf-8")
    names = export_names(src)
    body = strip_exports(rewrite_imports(src))
    indented = "\n".join(("  " + line) if line.strip() else line for line in body.split("\n"))
    returns = ", ".join(names)
    return (f"// ---- {name}.js " + "-" * max(0, 60 - len(name)) + "\n"
            f"const {module_var(name)} = (function () {{\n"
            f"{indented}\n"
            f"  return {{ {returns} }};\n"
            f"}})();\n")


def embedded_example() -> str:
    """Beispielzeichnung mitliefern, damit der Startbildschirm sie ohne Netz zeigt."""
    source = ROOT / "examples" / "lagerplatte.darocad.json"
    if not source.is_file():
        print("Hinweis: keine Beispielzeichnung gefunden -- Startbildschirm ohne Beispiel.")
        return ""
    data = json.loads(source.read_text(encoding="utf-8"))
    # Kompakt schreiben; "</script>" darf im JSON nicht vorkommen
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    text = text.replace("</", "<\\/")
    return f'<script type="application/json" id="beispielZeichnung">{text}</script>'


def build() -> int:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    css = (WEB / "css" / "app.css").read_text(encoding="utf-8")

    parts = [bundle_module(name) for name in MODULES]
    script = "\n".join(parts)

    html = html.replace('<link rel="stylesheet" href="css/app.css">',
                        f"<style>\n{css}\n</style>")
    html = html.replace("<!-- BEISPIEL-PLATZHALTER -->", embedded_example())
    html = html.replace('<script type="module" src="js/app.js"></script>',
                        '<script type="module">\n' + script + "\n</script>")
    # Kurzer, wiedererkennbarer Name -- er steht im Browser-Reiter und, wenn die
    # Datei veroeffentlicht wird, in der Uebersicht.
    html = html.replace("<title>DARO-CAD – Technische Zeichnungen</title>",
                        "<title>DARO-CAD</title>")

    if "<style>" not in html or "__m_geom" not in html:
        print("Buendeln fehlgeschlagen: Platzhalter in index.html nicht gefunden.",
              file=sys.stderr)
        return 1

    TARGET.write_text(html, encoding="utf-8")
    size = TARGET.stat().st_size
    print(f"{TARGET.name} geschrieben: {size/1024:.0f} kB, {len(MODULES)} Module")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
