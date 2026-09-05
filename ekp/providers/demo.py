"""Demo-Datenquellen.

Erzeugen realistische, aber synthetische Termine und Meldungen relativ zum
aktuellen Zeitpunkt. Damit laesst sich die komplette Kette ohne Netzzugang
und ohne API-Schluessel vorfuehren und testen.
"""

from __future__ import annotations

from datetime import timedelta

from ..models import EconomicEvent, NewsItem, utcnow

name = "demo"


# (Stunden ab jetzt, Titel, Land, Waehrung, Wichtigkeit, Prognose, Vorwert, Einheit, Ist-Wert)
_EVENTS: tuple[tuple[float, str, str, str, int, float | None, float | None, str, float | None], ...] = (
    (6, "US Verbraucherpreise (CPI) y/y", "US", "USD", 3, 2.9, 2.7, "%", None),
    (9, "Einzelhandelsumsätze m/m", "DE", "EUR", 2, 0.3, -0.2, "%", None),
    (20, "EZB Zinsentscheid (Hauptrefinanzierungssatz)", "EA", "EUR", 3, 3.25, 3.25, "%", None),
    (30, "ifo Geschäftsklimaindex", "DE", "EUR", 3, 87.5, 86.9, "Pkt.", None),
    (34, "Rohöllagerbestände (EIA)", "US", "USD", 2, -1.5, 2.4, "Mio. brl", None),
    (44, "Nonfarm Payrolls", "US", "USD", 3, 165.0, 142.0, "Tsd.", None),
    (46, "Arbeitslosenquote", "US", "USD", 3, 4.3, 4.3, "%", None),
    (52, "Erstanträge Arbeitslosenhilfe", "US", "USD", 2, 225.0, 219.0, "Tsd.", None),
    (58, "Einkaufsmanagerindex Industrie (PMI)", "EA", "EUR", 2, 47.8, 47.2, "Pkt.", None),
    (66, "Bruttoinlandsprodukt q/q", "DE", "EUR", 3, 0.2, 0.1, "%", None),
    # Bereits veroeffentlichte Termine - fuer die Trefferquoten-Auswertung.
    (-30, "US Erzeugerpreise (PPI) y/y", "US", "USD", 2, 2.4, 2.2, "%", 2.9),
    (-54, "Industrieproduktion m/m", "DE", "EUR", 2, 0.4, -1.1, "%", -0.3),
)


_NEWS: tuple[tuple[float, str, str, str, float, str], ...] = (
    # (Stunden zurueck, Titel, Anriss, Quelle, Quellengewicht, URL-Suffix)
    (3, "Ölpreise steigen deutlich: Brent klettert auf Sechsmonatshoch",
     "Nach der überraschenden Förderkürzung der OPEC+ ziehen die Energiepreise in den USA weiter an. "
     "Auch die Benzinpreise steigen kräftig.", "Reuters", 0.95, "oel-brent"),
    (7, "US-Mieten und Dienstleistungen treiben die Teuerung",
     "Ökonomen erwarten für die USA einen Anstieg der Verbraucherpreise, weil die Lohnabschlüsse in "
     "der Dienstleistungsbranche hoch ausfallen.", "Bloomberg", 0.95, "us-mieten"),
    (12, "Tarifabschluss in den USA: Deutliches Lohnplus für Millionen Beschäftigte",
     "Die Gewerkschaft setzt eine kräftige Gehaltserhöhung durch. Volkswirte sehen darin zusätzlichen "
     "Preisdruck für die amerikanische Wirtschaft.", "Handelsblatt", 0.85, "us-tarif"),
    (18, "Frachtraten ziehen an: Lieferengpässe belasten US-Importeure erneut",
     "Der Hafenstau an der Westküste sorgt für höhere Kosten entlang der Lieferkette.",
     "Wall Street Journal", 0.9, "frachtraten"),
    (26, "Inflation in den USA hartnäckiger als gedacht",
     "Die Kerninflation kommt seit Monaten höher als erwartet herein, warnen Analysten vor dem "
     "nächsten Preisbericht.", "Financial Times", 0.9, "sticky"),

    (5, "Großer US-Techkonzern kündigt massiven Stellenabbau an",
     "Betroffen sind mehrere tausend Arbeitsplätze in den USA. Weitere Entlassungen in der Branche "
     "gelten als wahrscheinlich.", "Reuters", 0.95, "us-layoffs"),
    (11, "US-Arbeitsmarkt kühlt ab: Zahl der Kündigungen steigt",
     "Der amerikanische Arbeitsmarkt schwächt sich ab, die Zahl offener Stellen geht zurück.",
     "Bloomberg", 0.95, "arbeitsmarkt-kuehlt"),
    (21, "Einstellungsstopp bei US-Einzelhändlern vor der Saison",
     "Mehrere Ketten in den USA verhängen einen Hiring Freeze und verweisen auf schwache Nachfrage.",
     "CNBC", 0.8, "hiring-freeze"),
    (33, "Insolvenzwelle bei US-Zulieferern nimmt zu",
     "Die Zahl der Firmenpleiten in den USA steigt, tausende Jobs stehen auf der Kippe.",
     "Reuters", 0.95, "insolvenzen"),

    (8, "ifo: Deutsche Unternehmen etwas zuversichtlicher",
     "Die Stimmung in der deutschen Wirtschaft hellt sich leicht auf, das Geschäftsklima verbessert "
     "sich moderat.", "ifo Institut", 0.9, "ifo-stimmung"),
    (16, "Deutsche Industrie: Auftragsflaute hält an",
     "Die Produktion in Deutschland wurde gedrosselt, die Auftragsbücher bleiben dünn.",
     "Handelsblatt", 0.85, "auftragsflaute"),
    (24, "Deutsche Exporte ziehen wieder an",
     "Die Ausfuhren aus Deutschland steigen dank besserer Nachfrage aus Asien.",
     "Destatis", 0.9, "exporte"),
    (14, "Kauflaune der deutschen Verbraucher erholt sich",
     "Der Einzelhandel in Deutschland meldet eine robuste Nachfrage, der Konsum zieht an.",
     "GfK", 0.8, "kauflaune"),
    (36, "Rezessionssorgen in Deutschland nehmen zu",
     "Ökonomen warnen vor einem Abschwung, mehrere Institute haben ihre Prognose gesenkt.",
     "Süddeutsche Zeitung", 0.75, "rezession"),

    (10, "EZB-Ratsmitglied dringt auf weitere Straffung",
     "In der Eurozone sei die Inflation zu hartnäckig, höhere Zinsen blieben nötig, sagte der "
     "Notenbanker.", "Reuters", 0.95, "ezb-hawkish"),
    (19, "Märkte preisen Zinssenkung der EZB ein",
     "Analysten in der Eurozone rechnen mit einer dovishen Wende der Europäischen Zentralbank.",
     "Bloomberg", 0.95, "ezb-dovish"),
    (28, "Kreditvergabe im Euroraum verschärft sich weiter",
     "Die Banken in der Eurozone melden strengere Standards bei der Kreditvergabe.",
     "EZB Bank Lending Survey", 0.9, "ezb-lending"),

    (13, "US-Rohöllager: Raffinerien fahren Produktion hoch",
     "In den USA wird mehr Rohöl verarbeitet, die Ölpreise geben leicht nach.",
     "EIA", 0.85, "raffinerie"),
    (30, "Euro schwächelt gegenüber dem Dollar",
     "Die europäische Währung fällt auf ein Mehrmonatstief, Importe werden teurer.",
     "Reuters", 0.9, "euro-schwach"),
    (40, "Baugenehmigungen in den USA brechen ein",
     "Der Wohnungsbau leidet unter hohen Hypothekenzinsen, die Bauwirtschaft meldet einen Einbruch.",
     "Wall Street Journal", 0.9, "bau-usa"),
    (44, "Handelsstreit: Neue Strafzölle belasten europäische Exporteure",
     "Die Zölle treffen die Ausfuhren aus Europa, Unternehmen kappen ihre Prognose.",
     "Financial Times", 0.9, "zoelle"),
    (50, "Lebensmittelpreise steigen wegen Dürre in Südamerika",
     "Die Missernte lässt die Getreidepreise weltweit klettern.", "Reuters", 0.95, "lebensmittel"),

    # Ältere Meldungen – sie liegen vor den bereits veröffentlichten Terminen und
    # machen die Gegenprüfung (`ekp verify`, `ekp score`) im Demobetrieb sichtbar.
    (58, "US-Erzeugerpreise unter Druck: Rohstoffkosten klettern deutlich",
     "Die Rohstoffpreise in den USA ziehen kräftig an, Vorleistungen werden teurer.",
     "Bloomberg", 0.95, "us-rohstoffe"),
    (64, "Frachtkosten für die US-Industrie steigen kräftig",
     "Lieferengpässe verteuern die Vorprodukte amerikanischer Hersteller.",
     "Wall Street Journal", 0.9, "us-fracht"),
    (70, "Deutsche Industrie drosselt die Produktion erneut",
     "Die Industrieproduktion in Deutschland sinkt, Werke fahren Schichten herunter.",
     "Handelsblatt", 0.9, "de-produktion"),
    (76, "Auftragsflaute in der deutschen Industrie verschärft sich",
     "Die Auftragseingänge der deutschen Industrie brechen weiter ein.",
     "FAZ Wirtschaft", 0.85, "de-auftraege"),
)


def _anchor():
    """Volle Stunde als Bezugspunkt.

    So erzeugen mehrere Scans innerhalb derselben Stunde identische Termin-IDs
    und der Demo-Kalender legt keine Dubletten an.
    """
    return utcnow().replace(minute=0, second=0, microsecond=0)


class DemoCalendarProvider:
    name = "demo"

    def fetch(self, lookahead_hours: int) -> list[EconomicEvent]:
        now = _anchor()
        events: list[EconomicEvent] = []
        for offset, title, country, ccy, imp, forecast, previous, unit, actual in _EVENTS:
            if offset > lookahead_hours:
                continue
            events.append(EconomicEvent(
                title=title,
                country=country,
                currency=ccy,
                when=now + timedelta(hours=offset),
                importance=imp,
                forecast=forecast,
                previous=previous,
                actual=actual,
                unit=unit,
                source="demo",
            ))
        return sorted(events, key=lambda e: e.when)


class DemoNewsProvider:
    name = "demo"

    def fetch(self, lookback_hours: int) -> list[NewsItem]:
        now = _anchor()
        items: list[NewsItem] = []
        for hours_ago, title, summary, source, weight, slug in _NEWS:
            if hours_ago > lookback_hours:
                continue
            items.append(NewsItem(
                title=title,
                summary=summary,
                url=f"https://example.invalid/demo/{slug}",
                published=now - timedelta(hours=hours_ago),
                source=source,
                source_weight=weight,
            ))
        return sorted(items, key=lambda n: -n.published.timestamp())
