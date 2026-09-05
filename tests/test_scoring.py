"""Uebersetzung von Nachrichten in gerichtete Evidenz."""

import unittest
from datetime import timedelta

from ekp.analysis.scoring import (dedupe_evidence, is_digest, outcome_bucket,
                                  recency_weight, score_news, surprise_z)
from ekp.analysis.taxonomy import classify
from ekp.models import EconomicEvent, NewsItem, utcnow


def event(title="US Verbraucherpreise (CPI) y/y", country="US", in_hours=12, **kw):
    return EconomicEvent(title=title, country=country, currency=kw.pop("currency", "USD"),
                         when=utcnow() + timedelta(hours=in_hours), **kw)


def news(title, hours_ago=2, summary="", source="Reuters", weight=0.9):
    return NewsItem(title=title, summary=summary, url=f"https://x.invalid/{abs(hash(title))}",
                    published=utcnow() - timedelta(hours=hours_ago),
                    source=source, source_weight=weight)


class TestAktualitaet(unittest.TestCase):
    def test_frische_meldung_wiegt_schwerer(self):
        ev = event(in_hours=48)
        self.assertGreater(recency_weight(news("x", 1), ev), recency_weight(news("x", 40), ev))

    def test_abstand_zum_termin_ist_egal(self):
        # Massgeblich ist das Alter der Meldung, nicht der Abstand zum Termin.
        frisch = news("x", 1)
        self.assertAlmostEqual(recency_weight(frisch, event(in_hours=6)),
                               recency_weight(frisch, event(in_hours=60)), places=6)

    def test_meldung_nach_dem_termin_zaehlt_nicht(self):
        vergangen = event(in_hours=-10)
        self.assertEqual(recency_weight(news("x", 1), vergangen), 0.0)

    def test_halbwertszeit(self):
        ev = event(in_hours=72)
        self.assertAlmostEqual(recency_weight(news("x", 36), ev, 36.0), 0.5, places=3)


class TestEvidenz(unittest.TestCase):
    def test_energiepreise_heben_inflationserwartung(self):
        ev = event()
        ergebnis = score_news(ev, classify(ev.title),
                              news("US-Benzinpreise steigen deutlich"))
        self.assertIsNotNone(ergebnis)
        self.assertEqual(ergebnis.direction, +1)
        self.assertIn("energiepreise↑", ergebnis.signals)

    def test_gleiche_nachricht_wirkt_je_indikator_anders(self):
        meldung = news("US-Konzerne kündigen massiven Stellenabbau an")
        stellen = event("Nonfarm Payrolls")
        quote = event("Arbeitslosenquote")
        e1 = score_news(stellen, classify(stellen.title), meldung)
        e2 = score_news(quote, classify(quote.title), meldung)
        self.assertEqual(e1.direction, -1)   # weniger neue Stellen
        self.assertEqual(e2.direction, +1)   # hoehere Arbeitslosenquote

    def test_themenfremde_meldung_wird_verworfen(self):
        ev = event()
        self.assertIsNone(score_news(ev, classify(ev.title),
                                     news("Japans Notenbank hebt die Zinsen an")))

    def test_meldung_ohne_signal_wird_verworfen(self):
        ev = event()
        self.assertIsNone(score_news(ev, classify(ev.title),
                                     news("US-Konferenz zur Wirtschaftspolitik beginnt")))

    def test_sammelmeldungen_werden_verworfen(self):
        ev = event()
        self.assertIsNone(score_news(ev, classify(ev.title),
                                     news("Business-Ticker: US-Ölpreise steigen deutlich")))

    def test_globale_rohstoffmeldung_zaehlt_ohne_landbezug(self):
        ev = event()
        ergebnis = score_news(ev, classify(ev.title),
                              news("Weltweite Lebensmittelpreise steigen stark"))
        self.assertIsNotNone(ergebnis)
        self.assertEqual(ergebnis.direction, +1)

    def test_starke_quelle_wiegt_schwerer(self):
        ev = event()
        fam = classify(ev.title)
        stark = score_news(ev, fam, news("US-Benzinpreise steigen deutlich", weight=1.0))
        schwach = score_news(ev, fam, news("US-Benzinpreise steigen deutlich", weight=0.4))
        self.assertGreater(stark.strength, schwach.strength)


class TestAufbereitung(unittest.TestCase):
    def test_dedupe_entfernt_doppelte_schlagzeilen(self):
        ev = event()
        fam = classify(ev.title)
        a = score_news(ev, fam, news("US-Benzinpreise steigen deutlich", source="Reuters"))
        b = score_news(ev, fam, news("US-Benzinpreise steigen deutlich", source="dpa"))
        self.assertEqual(len(dedupe_evidence([a, b])), 1)

    def test_dedupe_begrenzt_je_quelle(self):
        ev = event()
        fam = classify(ev.title)
        items = [score_news(ev, fam, news(f"US-Benzinpreise steigen deutlich Teil {i}"))
                 for i in range(9)]
        self.assertLessEqual(len(dedupe_evidence([i for i in items if i], max_per_source=4)), 4)

    def test_digest_erkennung(self):
        self.assertTrue(is_digest("+++ USA +++: Neues"))
        self.assertTrue(is_digest("Liveblog: Konjunktur"))
        self.assertFalse(is_digest("Ölpreise steigen"))


class TestUeberpruefung(unittest.TestCase):
    def test_abweichung_in_sigma(self):
        from ekp.analysis.taxonomy import sigma_for
        ev = event(forecast=2.9, actual=3.3)
        fam = classify(ev.title)
        # sigma ist das Maximum aus Familienwert (0.20) und 8 % der Prognose (0.232).
        self.assertAlmostEqual(sigma_for(fam, 2.9), 0.232, places=6)
        self.assertAlmostEqual(surprise_z(ev, fam), 0.4 / 0.232, places=6)

    def test_abweichung_ist_vorzeichenrichtig(self):
        fam = classify("US Verbraucherpreise (CPI) y/y")
        self.assertGreater(surprise_z(event(forecast=2.9, actual=3.3), fam), 0)
        self.assertLess(surprise_z(event(forecast=2.9, actual=2.5), fam), 0)

    def test_ohne_istwert_keine_abweichung(self):
        ev = event(forecast=2.9)
        self.assertIsNone(surprise_z(ev, classify(ev.title)))

    def test_ergebnisklassen(self):
        self.assertEqual(outcome_bucket(1.4, 0.5), "HOEHER")
        self.assertEqual(outcome_bucket(-1.4, 0.5), "NIEDRIGER")
        self.assertEqual(outcome_bucket(0.2, 0.5), "BESTAETIGT")


if __name__ == "__main__":
    unittest.main()
