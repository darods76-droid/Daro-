"""Indikator-Taxonomie.

Ordnet einen Kalendertermin einer *Indikator-Familie* zu und beschreibt,
welche Nachrichtenthemen (Signalgruppen) den Wert dieses Indikators in
welche Richtung treiben. Das ist der fachliche Kern der Prognosepruefung:
Ein Bericht ueber steigende Oelpreise ist ein Argument fuer eine hoehere
Inflationsrate, aber kein Argument fuer mehr neue Stellen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class IndicatorFamily:
    key: str
    label: str
    patterns: tuple[str, ...]
    drivers: dict[str, float]
    sigma_abs: float                 # typische Ueberraschung in Einheiten des Indikators
    good_is_up: bool = True          # True: hoher Wert = "besser als erwartet"
    topic_terms: tuple[str, ...] = ()
    note: str = ""

    def matches(self, title: str) -> bool:
        t = title.lower()
        return any(re.search(p, t) for p in self.patterns)


# Signalgruppen (Themen), die in Nachrichten erkannt werden.
SIGNAL_GROUPS = (
    "energiepreise",
    "nahrungsmittelpreise",
    "loehne",
    "entlassungen",
    "einstellungen",
    "konsumnachfrage",
    "kreditbedingungen",
    "lieferketten",
    "unternehmensstimmung",
    "immobilienmarkt",
    "aussenhandel",
    "waehrungsschwaeche",
    "notenbank_straff",
    "wachstum",
    "industrieproduktion",
    "direkt_hoeher",     # Nachricht nennt explizit eine Aufwaertsueberraschung
    "direkt_niedriger",
    "gute_nachricht",    # generische Bewertung, wird ueber good_is_up uebersetzt
    "schlechte_nachricht",
)


FAMILIES: tuple[IndicatorFamily, ...] = (
    IndicatorFamily(
        key="inflation_vpi",
        label="Verbraucherpreise / Inflation",
        patterns=(r"\bcpi\b", r"verbraucherpreis", r"\bvpi\b", r"inflation", r"\bhicp\b",
                  r"consumer price", r"lebenshaltungskost", r"kerninflation", r"core price"),
        drivers={
            "energiepreise": 0.95, "nahrungsmittelpreise": 0.80, "loehne": 0.55,
            "lieferketten": 0.50, "waehrungsschwaeche": 0.45, "konsumnachfrage": 0.35,
            "notenbank_straff": -0.20, "kreditbedingungen": -0.15,
        },
        sigma_abs=0.20, good_is_up=False,
        topic_terms=("inflation", "preise", "teuerung", "price", "cpi", "verbraucherpreis"),
        note="Hoehere Energie- und Nahrungsmittelpreise sowie Lohndruck heben die Rate.",
    ),
    IndicatorFamily(
        key="inflation_ppi",
        label="Erzeugerpreise",
        patterns=(r"\bppi\b", r"erzeugerpreis", r"producer price", r"grosshandelspreis",
                  r"wholesale price", r"einfuhrpreis", r"import price"),
        drivers={
            "energiepreise": 1.00, "lieferketten": 0.70, "nahrungsmittelpreise": 0.45,
            "waehrungsschwaeche": 0.55, "industrieproduktion": 0.25, "loehne": 0.30,
        },
        sigma_abs=0.30, good_is_up=False,
        topic_terms=("erzeugerpreis", "producer price", "ppi", "rohstoff", "commodity"),
    ),
    IndicatorFamily(
        key="beschaeftigung",
        label="Beschäftigung / Stellenaufbau",
        patterns=(r"non.?farm", r"\bnfp\b", r"payroll", r"beschaeftigt", r"beschäftigt",
                  r"arbeitsmarktbericht", r"employment change", r"stellenaufbau",
                  r"\badp\b", r"job openings", r"\bjolts\b"),
        drivers={
            "einstellungen": 1.00, "entlassungen": -1.00, "wachstum": 0.50,
            "unternehmensstimmung": 0.40, "konsumnachfrage": 0.25, "kreditbedingungen": -0.20,
        },
        sigma_abs=60.0, good_is_up=True,
        topic_terms=("arbeitsmarkt", "stellen", "jobs", "beschaeftigung", "payroll", "employment"),
        note="Einstellungswellen heben, Entlassungswellen senken den Stellenaufbau.",
    ),
    IndicatorFamily(
        key="arbeitslosenquote",
        label="Arbeitslosenquote",
        patterns=(r"arbeitslosenquote", r"arbeitslosenzahl", r"unemployment rate",
                  r"unemployment", r"jobless rate", r"erwerbslos"),
        drivers={
            "entlassungen": 0.95, "einstellungen": -0.95, "wachstum": -0.45,
            "unternehmensstimmung": -0.35, "kreditbedingungen": 0.20,
        },
        sigma_abs=0.15, good_is_up=False,
        topic_terms=("arbeitslos", "unemployment", "jobless", "arbeitsmarkt"),
    ),
    IndicatorFamily(
        key="erstantraege",
        label="Erstanträge Arbeitslosenhilfe",
        patterns=(r"jobless claims", r"initial claims", r"erstantr", r"continuing claims",
                  r"arbeitslosenhilfe"),
        drivers={
            "entlassungen": 1.00, "einstellungen": -0.80, "wachstum": -0.35,
        },
        sigma_abs=12.0, good_is_up=False,
        topic_terms=("claims", "erstantr", "entlassung", "layoff", "kurzarbeit"),
    ),
    IndicatorFamily(
        key="bip",
        label="Bruttoinlandsprodukt",
        patterns=(r"\bbip\b", r"\bgdp\b", r"bruttoinlandsprodukt", r"wirtschaftsleistung",
                  r"wirtschaftswachstum", r"economic growth"),
        drivers={
            "wachstum": 1.00, "konsumnachfrage": 0.65, "industrieproduktion": 0.55,
            "unternehmensstimmung": 0.40, "aussenhandel": 0.35, "einstellungen": 0.30,
            "entlassungen": -0.40, "kreditbedingungen": -0.35, "energiepreise": -0.25,
        },
        sigma_abs=0.30, good_is_up=True,
        topic_terms=("konjunktur", "wachstum", "rezession", "economy", "growth", "gdp", "bip"),
    ),
    IndicatorFamily(
        key="pmi",
        label="Einkaufsmanagerindex / ISM",
        patterns=(r"\bpmi\b", r"einkaufsmanager", r"\bism\b", r"purchasing manager"),
        drivers={
            "unternehmensstimmung": 1.00, "industrieproduktion": 0.70, "wachstum": 0.55,
            "aussenhandel": 0.35, "lieferketten": -0.30, "kreditbedingungen": -0.30,
            "entlassungen": -0.45, "energiepreise": -0.25,
        },
        sigma_abs=1.20, good_is_up=True,
        topic_terms=("pmi", "einkaufsmanager", "ism", "industrie", "dienstleist", "manufacturing"),
    ),
    IndicatorFamily(
        key="stimmung",
        label="Stimmungsindikatoren (ifo, ZEW, Verbrauchervertrauen)",
        patterns=(r"\bifo\b", r"\bzew\b", r"sentix", r"gfk", r"verbrauchervertrauen",
                  r"consumer confidence", r"consumer sentiment", r"michigan",
                  r"geschaeftsklima", r"geschäftsklima", r"business climate", r"economic sentiment"),
        drivers={
            "unternehmensstimmung": 1.00, "wachstum": 0.55, "konsumnachfrage": 0.45,
            "entlassungen": -0.50, "energiepreise": -0.35, "kreditbedingungen": -0.30,
            "notenbank_straff": -0.20,
        },
        sigma_abs=2.50, good_is_up=True,
        topic_terms=("stimmung", "vertrauen", "klima", "sentiment", "confidence", "ifo", "zew"),
    ),
    IndicatorFamily(
        key="einzelhandel",
        label="Einzelhandelsumsätze",
        patterns=(r"einzelhandel", r"retail sales", r"konsumausgaben", r"consumer spending",
                  r"personal spending"),
        drivers={
            "konsumnachfrage": 1.00, "loehne": 0.45, "einstellungen": 0.35,
            "energiepreise": -0.35, "kreditbedingungen": -0.35, "entlassungen": -0.45,
        },
        sigma_abs=0.50, good_is_up=True,
        topic_terms=("einzelhandel", "konsum", "retail", "spending", "verbraucher", "shopping"),
    ),
    IndicatorFamily(
        key="industrie",
        label="Industrieproduktion / Auftragseingänge",
        patterns=(r"industrieproduktion", r"industrial production", r"auftragseingang",
                  r"factory orders", r"durable goods", r"gueterauftraege", r"produktion"),
        drivers={
            "industrieproduktion": 1.00, "aussenhandel": 0.50, "unternehmensstimmung": 0.45,
            "lieferketten": -0.55, "energiepreise": -0.35, "wachstum": 0.40,
        },
        sigma_abs=0.80, good_is_up=True,
        topic_terms=("industrie", "produktion", "auftraege", "fabrik", "factory", "orders"),
    ),
    IndicatorFamily(
        key="zinsentscheid",
        label="Zinsentscheid",
        patterns=(r"zinsentscheid", r"leitzins", r"interest rate decision", r"rate decision",
                  r"\bfomc\b", r"\bezb\b", r"\becb\b", r"\bfed\b funds", r"bank rate",
                  r"geldpolit"),
        drivers={
            "notenbank_straff": 1.00, "energiepreise": 0.30, "loehne": 0.30,
            "wachstum": 0.25, "entlassungen": -0.40, "kreditbedingungen": -0.25,
        },
        sigma_abs=0.12, good_is_up=True,
        topic_terms=("notenbank", "zentralbank", "leitzins", "geldpolitik", "central bank",
                     "fed", "ezb", "ecb", "boe", "boj"),
        note="Getrieben von Aussagen der Notenbanker, nicht von Konjunkturdaten allein.",
    ),
    IndicatorFamily(
        key="handelsbilanz",
        label="Handelsbilanz / Leistungsbilanz",
        patterns=(r"handelsbilanz", r"trade balance", r"leistungsbilanz", r"current account",
                  r"exporte", r"importe", r"exports", r"imports"),
        drivers={
            "aussenhandel": 1.00, "waehrungsschwaeche": 0.40, "industrieproduktion": 0.45,
            "lieferketten": -0.40, "energiepreise": -0.30,
        },
        sigma_abs=1.50, good_is_up=True,
        topic_terms=("handel", "export", "import", "zoll", "tariff", "trade"),
    ),
    IndicatorFamily(
        key="immobilien",
        label="Immobilienmarkt (Baubeginne, Hausverkäufe)",
        patterns=(r"baugenehmigung", r"baubeginn", r"housing starts", r"building permits",
                  r"home sales", r"hausverkaeufe", r"immobilienpreis", r"house price",
                  r"hypothek", r"mortgage"),
        drivers={
            "immobilienmarkt": 1.00, "kreditbedingungen": -0.70, "notenbank_straff": -0.45,
            "einstellungen": 0.30, "konsumnachfrage": 0.30,
        },
        sigma_abs=5.00, good_is_up=True,
        topic_terms=("immobilie", "bau", "housing", "mortgage", "hypothek", "miete"),
    ),
    IndicatorFamily(
        key="rohoel_lager",
        label="Rohöllagerbestände",
        patterns=(r"rohoellager", r"rohöllager", r"crude oil inventories", r"\beia\b",
                  r"\bapi\b weekly", r"lagerbestaende"),
        drivers={
            "energiepreise": -0.70, "industrieproduktion": -0.35, "lieferketten": 0.40,
            "wachstum": -0.30,
        },
        sigma_abs=2.00, good_is_up=False,
        topic_terms=("oel", "öl", "oil", "crude", "opec", "raffinerie", "lager"),
    ),
)


GENERIC_FAMILY = IndicatorFamily(
    key="allgemein",
    label="Sonstiger Konjunkturindikator",
    patterns=(),
    drivers={"wachstum": 0.60, "unternehmensstimmung": 0.45, "konsumnachfrage": 0.35,
             "entlassungen": -0.40, "einstellungen": 0.35},
    sigma_abs=1.0, good_is_up=True,
    topic_terms=("konjunktur", "wirtschaft", "economy"),
    note="Keine spezifische Familie erkannt - es wird ein allgemeines Konjunkturmodell genutzt.",
)


_BY_KEY = {f.key: f for f in FAMILIES}


def classify(event_title: str) -> IndicatorFamily:
    """Ordnet einen Termintitel der passenden Indikator-Familie zu."""
    for fam in FAMILIES:
        if fam.matches(event_title):
            return fam
    return GENERIC_FAMILY


def get_family(key: str) -> IndicatorFamily:
    return _BY_KEY.get(key, GENERIC_FAMILY)


def sigma_for(family: IndicatorFamily, forecast: float | None) -> float:
    """Massstab, um eine Abweichung in Sigma-Einheiten umzurechnen.

    Neben dem familientypischen Absolutwert wird ein relativer Anteil der
    Prognose beruecksichtigt, damit sehr grosse Werte (z. B. Handelsbilanz in
    Mrd.) nicht jede Abweichung als Sensation erscheinen lassen.
    """
    base = family.sigma_abs
    if forecast is not None:
        base = max(base, abs(forecast) * 0.08)
    return max(base, 1e-6)
