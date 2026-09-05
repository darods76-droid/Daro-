"""Wahrscheinlichkeitsmodell und Bewertung der Trefferqualitaet."""

import unittest

from ekp.analysis.probability import aggregate, brier_score, phi, verdict_for


class TestVerteilung(unittest.TestCase):
    def test_phi(self):
        self.assertAlmostEqual(phi(0.0), 0.5, places=6)
        self.assertAlmostEqual(phi(1.96), 0.975, places=3)

    def test_summe_ist_eins(self):
        for vals in ([], [0.5], [-3.0, 2.0], [1.0] * 10):
            r = aggregate(vals)
            self.assertAlmostEqual(r.p_above + r.p_confirm + r.p_below, 1.0, places=9)

    def test_ohne_evidenz_symmetrisch(self):
        r = aggregate([])
        self.assertAlmostEqual(r.p_above, r.p_below, places=9)
        self.assertEqual(r.mu, 0.0)
        self.assertEqual(r.confidence, 0.0)

    def test_richtung_folgt_der_evidenz(self):
        hoch = aggregate([1.0, 1.2, 0.8], source_count=3)
        tief = aggregate([-1.0, -1.2, -0.8], source_count=3)
        self.assertGreater(hoch.p_above, hoch.p_below)
        self.assertGreater(tief.p_below, tief.p_above)
        self.assertAlmostEqual(hoch.mu, -tief.mu, places=9)

    def test_mehr_evidenz_verschiebt_weiter(self):
        wenig = aggregate([1.0])
        viel = aggregate([1.0, 1.0, 1.0, 1.0])
        self.assertGreater(viel.p_above, wenig.p_above)

    def test_erwartungswert_bleibt_begrenzt(self):
        # Auch eine Flut gleichgerichteter Meldungen kippt die Prognose nicht beliebig.
        r = aggregate([5.0] * 50)
        self.assertLessEqual(abs(r.mu), 2.0)

    def test_gegenlaeufige_evidenz_hebt_sich_auf(self):
        r = aggregate([1.5, -1.5], source_count=2)
        self.assertAlmostEqual(r.mu, 0.0, places=9)
        self.assertLess(r.agreement, 0.01)
        self.assertGreater(r.evidence_mass, 0)

    def test_konfidenz_waechst_mit_masse_und_quellen(self):
        eine = aggregate([1.0], source_count=1)
        viele = aggregate([1.0, 1.0, 1.0, 1.0], source_count=4)
        self.assertGreater(viele.confidence, eine.confidence)

    def test_breiteres_band_erhoeht_bestaetigung(self):
        eng = aggregate([0.2], confirm_band=0.3)
        weit = aggregate([0.2], confirm_band=1.5)
        self.assertGreater(weit.p_confirm, eng.p_confirm)

    def test_prior_verschiebt_erwartungswert(self):
        ohne = aggregate([])
        mit = aggregate([], prior_mu=0.5)
        self.assertGreater(mit.p_above, ohne.p_above)


class TestUrteil(unittest.TestCase):
    def test_ohne_evidenz_unbestaetigt(self):
        self.assertEqual(verdict_for(aggregate([])), "UNBESTAETIGT")

    def test_schwache_lage_unbestaetigt(self):
        self.assertEqual(verdict_for(aggregate([0.05], source_count=1)), "UNBESTAETIGT")

    def test_klare_lage_widerlegt(self):
        self.assertEqual(verdict_for(aggregate([2.0, 1.8, 1.5], source_count=3)),
                         "WIDERLEGT_HOEHER")
        self.assertEqual(verdict_for(aggregate([-2.0, -1.8, -1.5], source_count=3)),
                         "WIDERLEGT_NIEDRIGER")

    def test_ausgeglichene_lage_bestaetigt(self):
        self.assertEqual(verdict_for(aggregate([1.2, -1.2, 0.9, -0.9], source_count=4)),
                         "BESTAETIGT")


class TestBrier(unittest.TestCase):
    def test_perfekte_und_maximal_falsche_vorhersage(self):
        self.assertAlmostEqual(brier_score(1.0, 0.0, 0.0, "HOEHER"), 0.0)
        self.assertAlmostEqual(brier_score(0.0, 0.0, 1.0, "HOEHER"), 2.0)

    def test_unsicherheit_liegt_dazwischen(self):
        score = brier_score(1 / 3, 1 / 3, 1 / 3, "BESTAETIGT")
        self.assertTrue(0 < score < 2)

    def test_unbekanntes_ergebnis(self):
        with self.assertRaises(ValueError):
            brier_score(0.3, 0.4, 0.3, "VIELLEICHT")


if __name__ == "__main__":
    unittest.main()
