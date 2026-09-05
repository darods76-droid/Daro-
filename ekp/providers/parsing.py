"""Gemeinsame Parser fuer Kalender-APIs (Zahlen, Laender, Wichtigkeit)."""

from __future__ import annotations

import re

_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")
_SUFFIX = {"k": 1.0, "m": 1.0, "b": 1.0, "t": 1.0}   # Einheit bleibt wie geliefert

COUNTRY_CODES = {
    "united states": "US", "usa": "US", "us": "US",
    "germany": "DE", "deutschland": "DE", "de": "DE",
    "euro area": "EA", "euro zone": "EA", "eurozone": "EA", "european union": "EU",
    "ea": "EA", "eu": "EU",
    "united kingdom": "GB", "uk": "GB", "great britain": "GB", "gb": "GB",
    "japan": "JP", "jp": "JP", "china": "CN", "cn": "CN",
    "switzerland": "CH", "ch": "CH", "france": "FR", "fr": "FR",
    "italy": "IT", "it": "IT", "spain": "ES", "es": "ES",
    "canada": "CA", "ca": "CA", "australia": "AU", "au": "AU",
}

IMPORTANCE_WORDS = {"low": 1, "medium": 2, "moderate": 2, "high": 3,
                    "niedrig": 1, "mittel": 2, "hoch": 3}


def parse_number(raw) -> float | None:
    """Wandelt API-Werte wie '2.9%', '165K', '-1,5 Mio.' in eine Zahl.

    Der Skalenfaktor (K/M/B) wird bewusst *nicht* angewandt: Prognose, Vorwert
    und Ist-Wert kommen in derselben Einheit, und das Modell rechnet ohnehin
    nur mit Differenzen.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if not text or text in ("-", "--", "n/a", "N/A"):
        return None
    text = text.replace("−", "-")
    # Tausenderpunkte/-kommas entfernen, Dezimaltrenner vereinheitlichen.
    if re.search(r"\d,\d{3}\b", text):
        text = text.replace(",", "")
    match = _NUM_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def parse_unit(raw) -> str:
    if raw is None:
        return ""
    text = str(raw).strip()
    if "%" in text:
        return "%"
    m = re.search(r"[A-Za-zÄÖÜäöü€$£.]+\s*$", text)
    return (m.group(0).strip() if m else "")[:12]


def country_code(raw: str) -> str:
    key = (raw or "").strip().lower()
    if key in COUNTRY_CODES:
        return COUNTRY_CODES[key]
    return (raw or "").strip().upper()[:2]


def importance(raw) -> int:
    if raw is None:
        return 2
    if isinstance(raw, (int, float)):
        return max(1, min(3, int(raw)))
    text = str(raw).strip().lower()
    if text in IMPORTANCE_WORDS:
        return IMPORTANCE_WORDS[text]
    try:
        return max(1, min(3, int(float(text))))
    except ValueError:
        return 2
