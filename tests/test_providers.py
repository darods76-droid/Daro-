"""Parser der Datenquellen."""

import unittest
from datetime import timezone

from ekp.providers.demo import DemoCalendarProvider, DemoNewsProvider
from ekp.providers.parsing import country_code, importance, parse_number, parse_unit
from ekp.providers.rss import parse_datetime, parse_feed

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Ölpreise steigen</title>
    <link>https://example.invalid/1</link>
    <description>Ein &lt;b&gt;fetter&lt;/b&gt; Anriss</description>
    <pubDate>Wed, 03 Sep 2025 10:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Zweite Meldung</title>
    <link>https://example.invalid/2</link>
    <pubDate>Wed, 03 Sep 2025 11:30:00 +0200</pubDate>
  </item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Fed holds rates</title>
    <link href="https://example.invalid/a"/>
    <summary>Unchanged</summary>
    <updated>2025-09-03T11:00:00Z</updated>
  </entry>
</feed>"""


class TestZahlen(unittest.TestCase):
    def test_varianten(self):
        cases = {"2.9%": 2.9, "165K": 165.0, "-1,5 Mio.": -1.5, "1,234.5": 1234.5,
                 "-0.3": -0.3, 3.4: 3.4, 7: 7.0}
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertAlmostEqual(parse_number(raw), expected)

    def test_leere_werte(self):
        for raw in (None, "", "-", "n/a", "keine Zahl"):
            self.assertIsNone(parse_number(raw))

    def test_einheit(self):
        self.assertEqual(parse_unit("2.9%"), "%")
        self.assertEqual(parse_unit(None), "")

    def test_laendercodes(self):
        self.assertEqual(country_code("United States"), "US")
        self.assertEqual(country_code("Euro Area"), "EA")
        self.assertEqual(country_code("Germany"), "DE")
        self.assertEqual(country_code("Narnia"), "NA")

    def test_wichtigkeit(self):
        self.assertEqual(importance("High"), 3)
        self.assertEqual(importance("low"), 1)
        self.assertEqual(importance(2), 2)
        self.assertEqual(importance("unklar"), 2)
        self.assertEqual(importance(99), 3)


class TestFeeds(unittest.TestCase):
    def test_rss(self):
        items = parse_feed(RSS, "Testquelle", 0.8)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "Ölpreise steigen")
        self.assertNotIn("<b>", items[0].summary)
        self.assertEqual(items[0].published.tzinfo, timezone.utc)
        self.assertEqual(items[0].source_weight, 0.8)

    def test_atom(self):
        items = parse_feed(ATOM, "Atomquelle", 0.9)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://example.invalid/a")

    def test_kaputtes_xml_wirft_nicht(self):
        self.assertEqual(parse_feed("<rss><channel><item>", "x", 0.5), [])
        self.assertEqual(parse_feed("", "x", 0.5), [])

    def test_zeitformate(self):
        self.assertIsNotNone(parse_datetime("Wed, 03 Sep 2025 10:00:00 GMT"))
        self.assertIsNotNone(parse_datetime("2025-09-03T11:00:00Z"))
        self.assertIsNone(parse_datetime("kein Datum"))
        self.assertIsNone(parse_datetime(""))


class TestDemo(unittest.TestCase):
    def test_kalender_liefert_termine(self):
        events = DemoCalendarProvider().fetch(72)
        self.assertGreater(len(events), 5)
        self.assertEqual(events, sorted(events, key=lambda e: e.when))
        self.assertTrue(any(e.forecast is not None for e in events))

    def test_ids_bleiben_ueber_mehrere_abrufe_stabil(self):
        erst = {e.event_id for e in DemoCalendarProvider().fetch(72)}
        zweit = {e.event_id for e in DemoCalendarProvider().fetch(72)}
        self.assertEqual(erst, zweit)

    def test_vorlauf_wird_beachtet(self):
        self.assertLess(len(DemoCalendarProvider().fetch(12)),
                        len(DemoCalendarProvider().fetch(72)))

    def test_nachrichten(self):
        items = DemoNewsProvider().fetch(96)
        self.assertGreater(len(items), 10)
        self.assertTrue(all(n.published.tzinfo is not None for n in items))


if __name__ == "__main__":
    unittest.main()
