"""Tests des Capital.com-Providers.

Gegen einen nachgebauten Server, damit kein echtes Konto noetig ist und die
Tests reproduzierbar bleiben.
"""

from __future__ import annotations

import pytest

from forexwatch.providers import resolve_name
from forexwatch.providers.capital import CapitalProvider, to_epic

from . import mock_capital

PORT = 8127
BASE = f"http://127.0.0.1:{PORT}/api/v1"


@pytest.fixture(scope="module", autouse=True)
def server():
    srv = mock_capital.serve(PORT)
    yield srv
    srv.shutdown()


@pytest.fixture
def provider():
    mock_capital.STATE.update(sessions=0, price_calls=0, expire_after=10 ** 9,
                              calls_since_auth=0, expire_once=False)
    p = CapitalProvider(api_key="testkey", identifier="user@example.com", password="pw", demo=True)
    p.base_url = BASE
    return p


class TestEpics:
    def test_waehrungspaare_bleiben_gleich(self):
        assert to_epic("EURUSD") == "EURUSD"
        assert to_epic("eurusd") == "EURUSD"
        assert to_epic("EUR/USD") == "EURUSD"

    def test_sonderfaelle(self):
        assert to_epic("XAUUSD") == "GOLD"
        assert to_epic("XAGUSD") == "SILVER"
        assert to_epic("DAX") == "DE40"


class TestAuswertung:
    def test_mittelkurs_aus_geld_und_brief(self):
        assert CapitalProvider._mid({"bid": 1.0, "ask": 2.0}) == 1.5
        assert CapitalProvider._mid({"bid": 1.0}) == 1.0
        assert CapitalProvider._mid({"ask": 2.0}) == 2.0
        assert CapitalProvider._mid(None) is None
        assert CapitalProvider._mid({}) is None

    def test_unvollstaendige_kerzen_werden_verworfen(self):
        payload = {"prices": [
            {"snapshotTimeUTC": "2026-01-01T00:00:00",
             "openPrice": {"bid": 1, "ask": 1}, "highPrice": {"bid": 1, "ask": 1},
             "lowPrice": {"bid": 1, "ask": 1}, "closePrice": {"bid": 1, "ask": 1}},
            {"snapshotTimeUTC": "2026-01-01T01:00:00", "openPrice": {"bid": 1, "ask": 1}},
            {"openPrice": {"bid": 1, "ask": 1}},
        ]}
        assert len(CapitalProvider._parse(payload)) == 1

    def test_hoch_und_tief_werden_abgesichert(self):
        """Einzelne Datensaetze sind inkonsistent – das darf keine
        negative Kerzenspanne ergeben."""
        payload = {"prices": [{
            "snapshotTimeUTC": "2026-01-01T00:00:00",
            "openPrice": {"bid": 1.10, "ask": 1.10},
            "highPrice": {"bid": 1.05, "ask": 1.05},   # Hoch unter dem Open
            "lowPrice": {"bid": 1.15, "ask": 1.15},    # Tief ueber dem Open
            "closePrice": {"bid": 1.12, "ask": 1.12},
        }]}
        candle = CapitalProvider._parse(payload)[0]
        assert candle.high >= max(candle.open, candle.close)
        assert candle.low <= min(candle.open, candle.close)
        assert candle.range >= 0

    def test_leere_antwort(self):
        assert CapitalProvider._parse({}) == []
        assert CapitalProvider._parse({"prices": None}) == []

    def test_zeitstempel_werden_sortiert(self):
        payload = {"prices": [
            {"snapshotTimeUTC": f"2026-01-01T0{h}:00:00",
             "openPrice": {"bid": 1, "ask": 1}, "highPrice": {"bid": 1, "ask": 1},
             "lowPrice": {"bid": 1, "ask": 1}, "closePrice": {"bid": 1, "ask": 1}}
            for h in (3, 1, 2)
        ]}
        stamps = [c.ts for c in CapitalProvider._parse(payload)]
        assert stamps == sorted(stamps)


class TestAbruf:
    @pytest.mark.asyncio
    async def test_kerzen_holen(self, provider):
        series = await provider.fetch("EURUSD", "1h", 120)
        assert len(series) == 120
        assert mock_capital.STATE["sessions"] == 1
        for c in series.candles:
            assert c.low <= min(c.open, c.close)
            assert c.high >= max(c.open, c.close)
        await provider.close()

    @pytest.mark.asyncio
    async def test_lange_historie_ueber_mehrere_anfragen(self, provider):
        series = await provider.fetch("EURUSD", "1h", 2400)
        assert len(series) == 2400
        assert mock_capital.STATE["price_calls"] >= 3, "sollte blaettern"
        stamps = [c.ts for c in series.candles]
        assert len(set(stamps)) == len(stamps), "keine doppelten Kerzen"
        assert stamps == sorted(stamps)
        await provider.close()

    @pytest.mark.asyncio
    async def test_abgelaufene_sitzung_wird_erneuert(self, provider):
        # 0 bedeutet: schon die erste Kursanfrage nach der Anmeldung wird
        # abgelehnt – genau der Fall, den der Provider abfangen muss.
        mock_capital.STATE["expire_after"] = 0
        mock_capital.STATE["expire_once"] = True
        series = await provider.fetch("EURUSD", "1h", 100)
        assert len(series) == 100, "trotz Ablauf muessen Kerzen ankommen"
        assert mock_capital.STATE["sessions"] >= 2, "es muss neu angemeldet werden"
        await provider.close()

    @pytest.mark.asyncio
    async def test_unbekanntes_instrument(self, provider):
        assert len(await provider.fetch("UNKNOWN", "1h", 50)) == 0
        await provider.close()

    @pytest.mark.asyncio
    async def test_falscher_schluessel_meldet_nicht_durch(self, provider):
        bad = CapitalProvider(api_key="falsch", identifier="user@example.com", password="pw")
        bad.base_url = BASE
        assert len(await bad.fetch("EURUSD", "1h", 50)) == 0
        await bad.close()

    @pytest.mark.asyncio
    async def test_spread_wird_gelesen(self, provider):
        spread = await provider.spread_pips("EURUSD")
        assert spread == pytest.approx(1.6, abs=0.01)
        await provider.close()

    @pytest.mark.asyncio
    async def test_suche(self, provider):
        found = await provider.search("EUR")
        assert found and found[0]["epic"] == "EURUSD"
        await provider.close()


class TestOhneZugangsdaten:
    def test_nicht_konfiguriert(self):
        p = CapitalProvider(api_key="", identifier="", password="")
        assert p.configured is False

    @pytest.mark.asyncio
    async def test_liefert_leere_reihe(self):
        p = CapitalProvider(api_key="", identifier="", password="")
        assert len(await p.fetch("EURUSD", "1h", 50)) == 0
        await p.close()

    def test_auswahl_faellt_auf_yahoo_zurueck(self, monkeypatch):
        # Settings ist eingefroren, deshalb wird eine Kopie eingesetzt
        # statt einzelner Felder.
        import dataclasses

        from forexwatch import providers
        from forexwatch.config import settings

        leer = dataclasses.replace(
            settings, capital_api_key="", capital_identifier="", capital_password=""
        )
        monkeypatch.setattr(providers, "settings", leer)
        assert resolve_name("auto") == "yahoo"
        assert resolve_name("capital") == "yahoo"

    def test_auswahl_nimmt_capital_wenn_moeglich(self, monkeypatch):
        import dataclasses

        from forexwatch import providers
        from forexwatch.config import settings

        voll = dataclasses.replace(
            settings, capital_api_key="k", capital_identifier="i@x.de", capital_password="p"
        )
        monkeypatch.setattr(providers, "settings", voll)
        assert resolve_name("auto") == "capital"
        assert resolve_name("capital") == "capital"
