"""Signalerkennung in Schlagzeilen."""

import unittest

from ekp.analysis.lexicon import extract_from_item, extract_signals
from ekp.analysis.textutil import fold


def groups(text: str) -> dict[str, int]:
    return {h.group: h.direction for h in extract_signals(text)}


class TestFold(unittest.TestCase):
    def test_umlaute_und_html(self):
        self.assertEqual(fold("Ölpreise"), "oelpreise")
        self.assertEqual(fold("GESCHÄFTSKLIMA"), "geschaeftsklima")
        self.assertEqual(fold("<b>Straße</b>  x"), "strasse x")
        self.assertEqual(fold(""), "")


class TestSignals(unittest.TestCase):
    def test_richtung_energie(self):
        self.assertEqual(groups("Ölpreise steigen deutlich")["energiepreise"], +1)
        self.assertEqual(groups("Ölpreise fallen kräftig")["energiepreise"], -1)

    def test_negation_dreht_richtung(self):
        self.assertEqual(groups("Keine Zinserhöhung in Sicht")["notenbank_straff"], -1)

    def test_verstaerker_erhoeht_staerke(self):
        stark = extract_signals("Ölpreise steigen massiv")[0].strength
        leicht = extract_signals("Ölpreise steigen leicht")[0].strength
        self.assertGreater(stark, leicht)

    def test_direkte_ueberraschung(self):
        self.assertIn("direkt_hoeher", groups("Inflation kommt höher als erwartet"))
        self.assertIn("direkt_niedriger", groups("Retail sales miss expectations"))

    def test_naeherungsschicht_freie_formulierung(self):
        # Entitaet und Richtungswort stehen nicht direkt nebeneinander.
        self.assertEqual(groups("Oil settles higher as OPEC signals restraint")["energiepreise"], +1)
        self.assertEqual(groups("US retail sales unexpectedly fall")["konsumnachfrage"], -1)

    def test_keine_fehltreffer_bei_teilwoertern(self):
        # "boom" steckt in "Babyboomer" - darf kein Wachstumssignal ausloesen.
        self.assertEqual(groups("Babyboomer gehen in Rente"), {})

    def test_kursmeldungen_werden_ignoriert(self):
        self.assertEqual(groups("Oil giant BP shares fall 3% after earnings"), {})
        self.assertEqual(groups("Ölkonzern-Aktie sinkt nach Quartalszahlen"), {})

    def test_waehrung_invers(self):
        # Ein erstarkender Euro bedeutet weniger Waehrungsschwaeche.
        self.assertEqual(groups("Euro rallies against the dollar")["waehrungsschwaeche"], -1)

    def test_widerspruechliche_richtung_ergibt_kein_signal(self):
        # Die Naeherungsschicht verwirft Entitaeten, um die herum Auf- und
        # Abwaertswoerter gleichzeitig stehen.
        self.assertNotIn("energiepreise",
                         groups("Ölpreis: Analysten sehen Anstieg, Händler erwarten Rückgang"))


class TestTitelGewichtung(unittest.TestCase):
    def test_titel_wiegt_schwerer_als_anriss(self):
        im_titel = extract_from_item("Ölpreise steigen deutlich", "")
        im_anriss = extract_from_item("Nachrichten des Tages", "Ölpreise steigen deutlich")
        self.assertGreater(im_titel[0].strength, im_anriss[0].strength)

    def test_anriss_ergaenzt_fehlende_titelsignale(self):
        hits = extract_from_item("Was gestern geschah", "Die Entlassungswelle setzt sich fort")
        self.assertIn("entlassungen", {h.group for h in hits})


if __name__ == "__main__":
    unittest.main()
