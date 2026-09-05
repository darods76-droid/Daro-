"""Speicher, Gesamtdurchlauf und Ueberpruefung der Urteile."""

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from ekp.analysis.engine import AnalysisEngine
from ekp.config import Settings
from ekp.models import EconomicEvent, NewsItem, utcnow
from ekp.pipeline import scan, verify
from ekp.providers.demo import DemoCalendarProvider, DemoNewsProvider
from ekp.store import Store


def demo_settings(db_path: str) -> Settings:
    s = Settings()
    s.calendar_provider = "demo"
    s.news_provider = "demo"
    s.db_path = db_path
    s.lookahead_hours = 72
    s.min_importance = 2
    return s


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()


class TestSpeicher(StoreTest):
    def test_termine_und_nachrichten_ablegen(self):
        events = DemoCalendarProvider().fetch(72)
        self.store.upsert_events(events)
        self.store.upsert_events(events)          # zweimal: keine Dubletten
        self.assertEqual(self.store.counts()["events"], len(events))

        news = DemoNewsProvider().fetch(96)
        self.store.upsert_news(news)
        self.store.upsert_news(news)
        self.assertEqual(self.store.counts()["news"], len(news))

    def test_istwert_wird_nicht_von_leerem_wert_ueberschrieben(self):
        ev = EconomicEvent("US CPI y/y", "US", utcnow() + timedelta(hours=5), forecast=2.9)
        self.store.upsert_events([ev])
        self.store.set_actual(ev.event_id, 3.2)
        self.store.upsert_events([ev])            # erneuter Scan ohne Ist-Wert
        self.assertEqual(self.store.event(ev.event_id).actual, 3.2)

    def test_nur_die_neueste_bewertung_je_termin(self):
        settings = demo_settings(":memory:")
        events = DemoCalendarProvider().fetch(72)
        pool = DemoNewsProvider().fetch(96)
        self.store.upsert_events(events)
        engine = AnalysisEngine(settings)
        for _ in range(3):
            for a in engine.assess_all(events, pool):
                self.store.save_assessment(a)
        self.assertEqual(self.store.counts()["assessments"], 3 * len(events))
        rows = self.store.latest_assessments(upcoming_only=False, limit=500)
        self.assertEqual(len(rows), len(events))

    def test_nachrichten_zeitfenster(self):
        self.store.upsert_news([
            NewsItem("alt", "https://x/1", utcnow() - timedelta(hours=200), "Q"),
            NewsItem("neu", "https://x/2", utcnow() - timedelta(hours=2), "Q"),
        ])
        titel = [n.title for n in self.store.news_since(utcnow() - timedelta(hours=48))]
        self.assertEqual(titel, ["neu"])


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "test.sqlite3")
        self.settings = demo_settings(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_durchlauf_erzeugt_bewertungen(self):
        with Store(self.db) as store:
            report = scan(self.settings, store)
        self.assertGreater(report.events_kept, 0)
        self.assertGreater(report.news_pool, 0)
        self.assertEqual(len(report.assessments), report.events_kept)
        for a in report.assessments:
            self.assertIn(a.verdict, {"BESTAETIGT", "WIDERLEGT_HOEHER",
                                      "WIDERLEGT_NIEDRIGER", "UNBESTAETIGT"})
            self.assertAlmostEqual(a.p_above + a.p_confirm + a.p_below, 1.0, places=6)

    def test_nachrichtenlage_wird_ausgewertet(self):
        with Store(self.db) as store:
            report = scan(self.settings, store)
        nach_titel = {a.event.title: a for a in report.assessments}
        # Die Demo-Lage enthaelt Preisdruck (Öl, Löhne) und eine Entlassungswelle.
        cpi = next(a for t, a in nach_titel.items() if "Verbraucherpreise" in t)
        nfp = next(a for t, a in nach_titel.items() if "Nonfarm" in t)
        self.assertEqual(cpi.verdict, "WIDERLEGT_HOEHER")
        self.assertGreater(cpi.p_above, cpi.p_below)
        self.assertGreater(nfp.p_below, nfp.p_above)
        self.assertTrue(cpi.evidence)
        self.assertTrue(all(e.url for e in cpi.evidence))

    def test_wiederholter_scan_legt_keine_dubletten_an(self):
        with Store(self.db) as store:
            scan(self.settings, store)
            erste = store.counts()["events"]
            scan(self.settings, store)
            self.assertEqual(store.counts()["events"], erste)
            self.assertEqual(len(store.latest_assessments(upcoming_only=False, limit=500)), erste)

    def test_ueberpruefung_und_trefferbilanz(self):
        with Store(self.db) as store:
            scan(self.settings, store)          # prueft veroeffentlichte Termine gleich mit
            board = store.scoreboard()
            self.assertGreater(board["n"], 0)
            self.assertIsNotNone(board["brier"])
            self.assertEqual(verify(self.settings, store), [])   # nichts Offenes mehr

    def test_urteil_wird_gegen_istwert_geprueft(self):
        with Store(self.db) as store:
            scan(self.settings, store)
            ev = EconomicEvent("US Verbraucherpreise (CPI) y/y", "US",
                               utcnow() - timedelta(hours=2), forecast=2.9)
            store.upsert_events([ev])
            engine = AnalysisEngine(self.settings)
            pool = DemoNewsProvider().fetch(96)
            store.save_assessment(engine.assess(ev, pool))
            store.set_actual(ev.event_id, 3.6)                  # deutlich ueber Prognose
            ergebnisse = verify(self.settings, store)
            treffer = [r for r in ergebnisse if r["event_id"] == ev.event_id]
            self.assertEqual(len(treffer), 1)
            self.assertEqual(treffer[0]["outcome"], "HOEHER")

    def test_priors_bleiben_begrenzt(self):
        with Store(self.db) as store:
            scan(self.settings, store)
            for key, value in store.family_priors().items():
                self.assertLessEqual(abs(value), 1.0, key)

    def test_fehlende_nachrichten_ergeben_kein_urteil(self):
        settings = demo_settings(self.db)
        with Store(self.db) as store:
            events = DemoCalendarProvider().fetch(72)
            store.upsert_events(events)
            engine = AnalysisEngine(settings)
            for a in engine.assess_all(events, []):
                self.assertEqual(a.verdict, "UNBESTAETIGT")
                self.assertEqual(a.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
