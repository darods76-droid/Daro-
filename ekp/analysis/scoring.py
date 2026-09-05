"""Uebersetzt Nachrichtensignale in gerichtete Evidenz fuer einen Termin."""

from __future__ import annotations

import math

from ..models import EconomicEvent, Evidence, NewsItem, utcnow
from .lexicon import extract_from_item
from .relevance import GLOBAL_COUNTRY_FLOOR, GLOBAL_GROUPS, relevance
from .taxonomy import IndicatorFamily

import re

MIN_RELEVANCE = 0.35      # darunter gilt eine Nachricht als themenfremd

# Sammel- und Live-Formate buendeln viele unabhaengige Meldungen in einem
# Eintrag. Ihr Anrisstext mischt Themen und erzeugt Scheinsignale.
_DIGEST_RE = re.compile(
    r"^\s*(\+{3}|business-?ticker|news-?ticker|ticker:|liveblog|newsblog|"
    r"marktbericht|was heute wichtig|die wichtigsten meldungen|"
    r"morning briefing|live updates?|briefing:)", re.IGNORECASE)


def is_digest(title: str) -> bool:
    """Erkennt Ticker-, Blog- und Sammelmeldungen."""
    return bool(_DIGEST_RE.search(title or ""))
MIN_STRENGTH = 0.05       # darunter ist der Beitrag vernachlaessigbar

# Gewicht der direkten Ueberraschungsaussagen und der generischen Bewertung.
DIRECT_WEIGHT = 1.1
GENERIC_WEIGHT = 0.35


def recency_weight(news: NewsItem, event: EconomicEvent, half_life_hours: float = 36.0) -> float:
    """Aktualitaetsgewicht einer Meldung.

    Massgeblich ist das *Alter der Meldung* zum Bewertungszeitpunkt, nicht ihr
    Abstand zum Termin: eine Schlagzeile von heute Morgen ist frisch, egal ob
    der Termin morgen oder in drei Tagen ansteht. Bezugspunkt ist deshalb
    ``min(jetzt, Terminzeit)`` - bei bereits veroeffentlichten Terminen zaehlt
    das Alter zum Zeitpunkt der Veroeffentlichung.

    Meldungen *nach* dem Termin fliessen gar nicht ein: sie koennen eine
    Prognose nicht mehr vorab bestaetigen oder widerlegen.
    """
    if news.published > event.when:
        return 0.0
    reference = min(utcnow(), event.when)
    age_hours = max(0.0, (reference - news.published).total_seconds() / 3600.0)
    return 0.5 ** (age_hours / max(half_life_hours, 1e-6))


def score_news(
    event: EconomicEvent,
    family: IndicatorFamily,
    news: NewsItem,
    half_life_hours: float = 36.0,
) -> Evidence | None:
    """Bewertet eine einzelne Nachricht fuer einen Termin.

    Rueckgabe ``None``, wenn die Nachricht themenfremd, zu alt, zu neu oder
    ohne verwertbares Signal ist.
    """
    if is_digest(news.title):
        return None

    rec = recency_weight(news, event, half_life_hours)
    if rec <= 0.01:
        return None

    signals = extract_from_item(news.title, news.summary)
    if not signals:
        return None

    # Weltweit wirkende Treiber (Energie, Nahrungsmittel, Lieferketten) gelten
    # auch dann, wenn die Meldung kein Land nennt.
    floor = (GLOBAL_COUNTRY_FLOOR
             if any(sig.group in GLOBAL_GROUPS for sig in signals) else 0.0)
    rel = relevance(family, event.country, event.currency, news.text, country_floor=floor)
    if rel < MIN_RELEVANCE:
        return None

    contribution = 0.0
    labels: list[str] = []
    for sig in signals:
        if sig.group == "direkt_hoeher":
            coeff = DIRECT_WEIGHT
        elif sig.group == "direkt_niedriger":
            coeff = -DIRECT_WEIGHT
        elif sig.group == "gute_nachricht":
            coeff = GENERIC_WEIGHT if family.good_is_up else -GENERIC_WEIGHT
        elif sig.group == "schlechte_nachricht":
            coeff = -GENERIC_WEIGHT if family.good_is_up else GENERIC_WEIGHT
        else:
            coeff = family.drivers.get(sig.group, 0.0)

        if coeff == 0.0:
            continue
        part = sig.signed * coeff
        contribution += part
        arrow = "↑" if part > 0 else "↓"
        labels.append(f"{sig.group}{arrow}")

    if abs(contribution) < 1e-9 or not labels:
        return None

    strength = abs(contribution) * rel * news.source_weight * rec
    if strength < MIN_STRENGTH:
        return None

    direction = 1 if contribution > 0 else -1
    richtung = "über" if direction > 0 else "unter"
    rationale = (
        f"{', '.join(labels)} → spricht für einen Wert {richtung} der Prognose "
        f"(Relevanz {rel:.2f}, Aktualität {rec:.2f}, Quelle {news.source_weight:.2f})"
    )

    return Evidence(
        news_id=news.news_id,
        headline=news.title,
        url=news.url,
        source=news.source,
        published=news.published,
        direction=direction,
        strength=round(strength, 4),
        relevance=rel,
        recency=round(rec, 4),
        signals=labels,
        rationale=rationale,
    )


def dedupe_evidence(items: list[Evidence], max_per_source: int = 4) -> list[Evidence]:
    """Begrenzt gleichartige Meldungen, damit Agenturuebernahmen nicht dominieren."""
    seen_titles: set[str] = set()
    per_source: dict[str, int] = {}
    out: list[Evidence] = []
    for ev in sorted(items, key=lambda e: -e.strength):
        key = " ".join(ev.headline.lower().split()[:8])
        if key in seen_titles:
            continue
        if per_source.get(ev.source, 0) >= max_per_source:
            continue
        seen_titles.add(key)
        per_source[ev.source] = per_source.get(ev.source, 0) + 1
        out.append(ev)
    return out


def surprise_z(event: EconomicEvent, family: IndicatorFamily) -> float | None:
    """Tatsaechliche Abweichung des Ist-Werts von der Prognose in Sigma."""
    from .taxonomy import sigma_for

    if event.actual is None or event.forecast is None:
        return None
    sigma = sigma_for(family, event.forecast)
    return (event.actual - event.forecast) / sigma


def outcome_bucket(z: float, confirm_band: float) -> str:
    if z > confirm_band:
        return "HOEHER"
    if z < -confirm_band:
        return "NIEDRIGER"
    return "BESTAETIGT"


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def log_odds(p: float) -> float:
    p = clamp(p, 1e-6, 1 - 1e-6)
    return math.log(p / (1 - p))
