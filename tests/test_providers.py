"""Tests der Datenquellen und des Resamplings."""

from __future__ import annotations

import pytest

from forexwatch.models import Candle, Series
from forexwatch.providers import get_provider
from forexwatch.providers.base import DataProvider, resample, timeframe_seconds
from forexwatch.providers.synthetic import SyntheticProvider
from forexwatch.providers.twelvedata import to_td_symbol
from forexwatch.providers.yahoo import YahooProvider, to_yahoo_symbol


class TestSymbolzuordnung:
    def test_yahoo_paare(self):
        assert to_yahoo_symbol("EURUSD") == "EURUSD=X"
        assert to_yahoo_symbol("eurusd") == "EURUSD=X"
        assert to_yahoo_symbol("EUR/USD") == "EURUSD=X"

    def test_yahoo_sonderfaelle(self):
        assert to_yahoo_symbol("XAUUSD") == "GC=F"
        assert to_yahoo_symbol("DXY") == "DX-Y.NYB"
        assert to_yahoo_symbol("^GSPC") == "^GSPC"

    def test_twelvedata_paare(self):
        assert to_td_symbol("EURUSD") == "EUR/USD"
        assert to_td_symbol("XAUUSD") == "XAU/USD"


class TestResampling:
    def test_stunden_zu_vier_stunden(self):
        candles = [
            Candle(i * 3600, 1.0 + i, 2.0 + i, 0.5 + i, 1.5 + i, 10.0) for i in range(8)
        ]
        result = resample(Series("X", "1h", candles), "4h")
        assert len(result) == 2
        first = result.candles[0]
        assert first.ts % 14400 == 0
        assert first.open == candles[0].open
        assert first.close == candles[3].close
        assert first.high == max(c.high for c in candles[:4])
        assert first.low == min(c.low for c in candles[:4])
        assert first.volume == pytest.approx(40.0)

    def test_raster_ist_utc_ausgerichtet(self):
        # Beginn mitten in einem 4h-Block -> erster Bucket rastet dennoch ein
        candles = [Candle(3600 * (i + 2), 1.0, 1.0, 1.0, 1.0) for i in range(8)]
        result = resample(Series("X", "1h", candles), "4h")
        assert all(c.ts % 14400 == 0 for c in result.candles)

    def test_quell_timeframe_wahl(self):
        native = ("1m", "5m", "15m", "30m", "1h", "1d")
        assert DataProvider._source_timeframe("4h", native) == ("1h", 4)
        assert DataProvider._source_timeframe("1h", native) == ("1h", 1)
        assert DataProvider._source_timeframe("15m", native) == ("15m", 1)

    def test_timeframe_sekunden(self):
        assert timeframe_seconds("1h") == 3600
        assert timeframe_seconds("4h") == 14400
        assert timeframe_seconds("unbekannt") == 3600


class TestSynthetisch:
    @pytest.mark.asyncio
    async def test_liefert_gueltige_kerzen(self):
        series = await SyntheticProvider(seed=1).fetch("EURUSD", "1h", 200)
        assert len(series) == 200
        for c in series.candles:
            assert c.low <= min(c.open, c.close)
            assert c.high >= max(c.open, c.close)
            assert c.low > 0

    @pytest.mark.asyncio
    async def test_reproduzierbar(self):
        a = await SyntheticProvider(seed=7).fetch("EURUSD", "1h", 50)
        b = await SyntheticProvider(seed=7).fetch("EURUSD", "1h", 50)
        assert a.closes == b.closes

    @pytest.mark.asyncio
    async def test_kurs_bleibt_in_plausiblem_rahmen(self):
        series = await SyntheticProvider(seed=3).fetch("EURUSD", "1h", 1000)
        assert 0.5 < min(series.closes) and max(series.closes) < 2.5

    @pytest.mark.asyncio
    async def test_zeitstempel_aufsteigend(self):
        series = await SyntheticProvider(seed=2).fetch("EURUSD", "1h", 100)
        stamps = [c.ts for c in series.candles]
        assert stamps == sorted(stamps)


class TestAuswahl:
    def test_unbekannter_provider_faellt_auf_yahoo(self):
        assert isinstance(get_provider("gibtsnicht"), YahooProvider)

    def test_twelvedata_ohne_schluessel_faellt_zurueck(self):
        # Ohne FW_TWELVEDATA_KEY waere der Provider nutzlos
        from forexwatch.config import settings

        provider = get_provider("twelvedata")
        if not settings.twelvedata_key:
            assert isinstance(provider, YahooProvider)


class TestYahooAuswertung:
    def test_luecken_werden_verworfen(self):
        payload = {
            "chart": {"result": [{
                "timestamp": [1, 2, 3],
                "indicators": {"quote": [{
                    "open": [1.0, None, 3.0],
                    "high": [1.1, None, 3.1],
                    "low": [0.9, None, 2.9],
                    "close": [1.05, None, 3.05],
                    "volume": [10, None, 30],
                }]},
            }]}
        }
        candles = YahooProvider._parse(payload)
        assert len(candles) == 2
        assert [c.ts for c in candles] == [1, 3]

    def test_leere_antwort(self):
        assert YahooProvider._parse({"chart": {"result": []}}) == []
        assert YahooProvider._parse({}) == []

    def test_doppelte_zeitstempel_werden_zusammengefasst(self):
        payload = {
            "chart": {"result": [{
                "timestamp": [1, 1, 2],
                "indicators": {"quote": [{
                    "open": [1.0, 1.1, 2.0], "high": [1.0, 1.1, 2.0],
                    "low": [1.0, 1.1, 2.0], "close": [1.0, 1.1, 2.0],
                    "volume": [1, 1, 1],
                }]},
            }]}
        }
        candles = YahooProvider._parse(payload)
        assert len(candles) == 2
        assert candles[0].close == 1.1  # der spaetere Wert gewinnt
