"""Relevanzpruefung: Passt eine Nachricht ueberhaupt zu diesem Termin?"""

from __future__ import annotations

from .taxonomy import IndicatorFamily
from .textutil import fold

# Laendercode -> Begriffe, die eine Nachricht diesem Wirtschaftsraum zuordnen.
COUNTRY_TERMS: dict[str, tuple[str, ...]] = {
    "US": ("usa", "us-", " us ", "amerika", "american", "united states", "washington",
           "fed ", "federal reserve", "fomc", "dollar", "wall street", "u.s."),
    "DE": ("deutschland", "deutsche", "german", "germany", "berlin", "bundesbank",
           "ifo", "dax", "bundesregierung"),
    "EA": ("eurozone", "euroraum", "euro-zone", "euro area", "ezb", "ecb", "euro ",
           "europaeische zentralbank", "bruessel", "eu-", "lagarde"),
    "EU": ("europa", "eu-", "europaeisch", "european union", "bruessel"),
    "GB": ("grossbritannien", "britisch", "britain", "uk ", "u.k.", "london",
           "bank of england", "boe", "pfund", "pound", "sterling"),
    "JP": ("japan", "japanisch", "japanese", "tokio", "tokyo", "bank of japan", "boj", "yen"),
    "CN": ("china", "chinesisch", "chinese", "peking", "beijing", "yuan", "renminbi"),
    "CH": ("schweiz", "swiss", "switzerland", "snb", "franken", "franc"),
    "FR": ("frankreich", "franzoesisch", "french", "france", "paris"),
    "IT": ("italien", "italienisch", "italian", "italy", "rom", "rome"),
    "CA": ("kanada", "canada", "canadian", "ottawa", "bank of canada", "loonie"),
    "AU": ("australien", "australia", "australian", "\brba\b", "aussie"),
}

# Waehrung -> Land, damit auch Termine ohne sauberen Laendercode zugeordnet werden.
CURRENCY_COUNTRY = {
    "USD": "US", "EUR": "EA", "GBP": "GB", "JPY": "JP",
    "CNY": "CN", "CHF": "CH", "CAD": "CA", "AUD": "AU",
}


def country_match(country: str, currency: str, folded_text: str) -> float:
    """0..1 - wie klar bezieht sich der Text auf diesen Wirtschaftsraum."""
    code = (country or "").upper()[:2]
    if not code and currency:
        code = CURRENCY_COUNTRY.get(currency.upper(), "")
    terms = COUNTRY_TERMS.get(code, ())
    if not terms:
        return 0.50   # unbekannter Raum: neutral, nicht ausschliessen
    if any(t in folded_text for t in terms):
        return 1.0
    # Eurozone und Mitgliedslaender greifen ineinander.
    if code == "EA" and any(t in folded_text for t in COUNTRY_TERMS["DE"] + COUNTRY_TERMS["EU"]):
        return 0.7
    if code == "DE" and any(t in folded_text for t in COUNTRY_TERMS["EA"]):
        return 0.7
    return 0.15


def topic_match(family: IndicatorFamily, folded_text: str) -> float:
    """0..1 - wie stark spricht der Text das Thema des Indikators direkt an."""
    if not family.topic_terms:
        return 0.4
    hits = sum(1 for t in family.topic_terms if fold(t) in folded_text)
    if hits == 0:
        return 0.0
    return min(1.0, 0.55 + 0.15 * (hits - 1))


# Themen, die weltweit wirken: der Oelpreis treibt die Teuerung in jedem Land,
# unabhaengig davon, ob die Meldung ein Land ueberhaupt nennt.
GLOBAL_GROUPS = frozenset({"energiepreise", "nahrungsmittelpreise", "lieferketten"})
GLOBAL_COUNTRY_FLOOR = 0.70


def relevance(family: IndicatorFamily, country: str, currency: str, text: str,
              country_floor: float = 0.0) -> float:
    """Gesamtrelevanz einer Nachricht fuer einen Termin (0..1).

    Der Wirtschaftsraum wirkt *multiplikativ* wie ein Filter: eine Meldung ueber
    die Eurozone taugt nicht als Beleg fuer einen US-Termin, egal wie gut das
    Thema passt. Die Themennennung wirkt als Verstaerker - auch ohne sie bleibt
    eine Meldung verwertbar, wenn sie einen Treiber des Indikators beschreibt.
    """
    folded = fold(text)
    c = max(country_match(country, currency, folded), country_floor)
    t = topic_match(family, folded)
    return round(min(1.0, max(0.0, c * (0.45 + 0.55 * t))), 4)
