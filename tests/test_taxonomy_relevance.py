"""Zuordnung von Terminen zu Indikator-Familien und Relevanzpruefung."""

import unittest

from ekp.analysis.relevance import country_match, relevance, topic_match
from ekp.analysis.taxonomy import GENERIC_FAMILY, classify, get_family, sigma_for
from ekp.analysis.textutil import fold


class TestKlassifikation(unittest.TestCase):
    def test_bekannte_termine(self):
        cases = {
            "US CPI y/y": "inflation_vpi",
            "Verbraucherpreisindex (VPI)": "inflation_vpi",
            "Nonfarm Payrolls": "beschaeftigung",
            "Arbeitslosenquote": "arbeitslosenquote",
            "Initial Jobless Claims": "erstantraege",
            "Bruttoinlandsprodukt q/q": "bip",
            "ISM Manufacturing PMI": "pmi",
            "ifo Geschäftsklimaindex": "stimmung",
            "Einzelhandelsumsätze m/m": "einzelhandel",
            "EZB Zinsentscheid": "zinsentscheid",
            "Handelsbilanz": "handelsbilanz",
            "Baugenehmigungen": "immobilien",
            "Rohöllagerbestände": "rohoel_lager",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(classify(title).key, expected)

    def test_unbekannter_termin_faellt_auf_allgemein(self):
        self.assertEqual(classify("Rede des Finanzministers").key, GENERIC_FAMILY.key)

    def test_inverse_familien(self):
        # Bei diesen Indikatoren ist ein hoher Wert die schlechtere Nachricht.
        for key in ("inflation_vpi", "arbeitslosenquote", "erstantraege"):
            self.assertFalse(get_family(key).good_is_up, key)
        for key in ("beschaeftigung", "bip", "pmi"):
            self.assertTrue(get_family(key).good_is_up, key)

    def test_sigma_waechst_mit_grosser_prognose(self):
        fam = get_family("handelsbilanz")
        self.assertGreater(sigma_for(fam, 200.0), sigma_for(fam, 1.0))
        self.assertGreater(sigma_for(fam, None), 0)


class TestRelevanz(unittest.TestCase):
    def test_laendertreffer(self):
        self.assertEqual(country_match("US", "", fold("Die Fed in Washington")), 1.0)
        self.assertEqual(country_match("DE", "", fold("Die Bundesbank in Berlin")), 1.0)
        self.assertLess(country_match("US", "", fold("Neues aus Japan")), 0.3)

    def test_waehrung_ersetzt_fehlenden_laendercode(self):
        self.assertEqual(country_match("", "USD", fold("Fed hebt Zinsen an")), 1.0)

    def test_themenbezug(self):
        fam = classify("US CPI y/y")
        self.assertGreater(topic_match(fam, fold("Die Inflation zieht an")), 0.5)
        self.assertEqual(topic_match(fam, fold("Fussball-Ergebnisse")), 0.0)

    def test_land_wirkt_als_filter(self):
        fam = classify("US CPI y/y")
        passend = relevance(fam, "US", "USD", "US-Inflation zieht an")
        fremd = relevance(fam, "US", "USD", "Inflation in Japan zieht an")
        self.assertGreater(passend, 0.7)
        self.assertLess(fremd, 0.35)

    def test_globaler_boden_hebt_rohstoffmeldungen(self):
        fam = classify("US CPI y/y")
        text = "Weltweite Lebensmittelpreise steigen"
        self.assertLess(relevance(fam, "US", "USD", text), 0.35)
        self.assertGreater(relevance(fam, "US", "USD", text, country_floor=0.7), 0.35)


if __name__ == "__main__":
    unittest.main()
