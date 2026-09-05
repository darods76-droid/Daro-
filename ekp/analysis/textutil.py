"""Textnormalisierung fuer die Signalerkennung."""

from __future__ import annotations

import re
import unicodedata

_UMLAUTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"}
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def fold(text: str) -> str:
    """Kleinschreibung, HTML raus, Umlaute/Akzente auf ASCII abbilden.

    Danach koennen alle Muster in reinem ASCII geschrieben werden und treffen
    sowohl "Geschäftsklima" als auch "Geschaeftsklima".
    """
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    for src, dst in _UMLAUTS.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _WS_RE.sub(" ", text.lower()).strip()
