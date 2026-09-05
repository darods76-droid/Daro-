"""Tests des Backtests – vor allem: kein Blick in die Zukunft."""

from __future__ import annotations

import pytest

from forexwatch.analysis.features import build_features
from forexwatch.backtest import SWING_CONFIRM_BARS, run_backtest, slice_features, spread_for
from forexwatch.models import Series
from tests.conftest import make_series


class TestKeinBlickInDieZukunft:
    """Der wichtigste Test des ganzen Projekts.

    Wenn die zurueckgeschnittene Sicht auch nur einen Wert enthaelt, der zum
    damaligen Zeitpunkt noch nicht bekannt war, sind saemtliche Kennzahlen des
    Backtests wertlos.
    """

    @pytest.mark.parametrize("cut", [120, 180, 240])
    def test_geschnittene_sicht_gleicht_neuberechnung(self, cut):
        series = make_series(300)
        full = build_features(series)
        view = slice_features(full, cut)
        fresh = build_features(Series(series.symbol, series.timeframe, series.candles[: cut + 1]))

        for name in (
            "ema20", "ema50", "rsi14", "atr14",
            "bb_upper", "bb_mid", "bb_lower",
            "kc_upper", "kc_lower", "dc_upper", "dc_lower",
            "macd_line", "macd_signal", "macd_hist",
            "adx", "plus_di", "minus_di", "stoch_k", "stoch_d",
            "bb_width", "squeeze_on",
        ):
            a = getattr(view, name)
            b = getattr(fresh, name)
            assert len(a) == len(b) == cut + 1, name
            for i, (x, y) in enumerate(zip(a, b)):
                if x is None or y is None:
                    assert x == y, f"{name}[{i}]: {x} vs {y}"
                else:
                    assert x == pytest.approx(y, rel=1e-9), f"{name}[{i}]: {x} vs {y}"

    def test_laenge_entspricht_dem_schnitt(self):
        full = build_features(make_series(300))
        assert len(slice_features(full, 150).closes) == 151

    def test_swings_erst_nach_bestaetigung_sichtbar(self):
        """Ein Swing braucht Kerzen *nach* dem Hoch. Bis dahin darf er im
        Rueckblick nicht auftauchen."""
        series = make_series(300)
        full = build_features(series)
        cut = 200
        view = slice_features(full, cut)
        assert view.swings, "Testreihe sollte bestaetigte Swings enthalten"
        for swing in view.swings:
            assert swing.index <= cut - SWING_CONFIRM_BARS

    def test_keine_kerze_aus_der_zukunft(self):
        series = make_series(300)
        full = build_features(series)
        cut = 175
        view = slice_features(full, cut)
        assert view.series.candles[-1].ts == series.candles[cut].ts
        assert len(view.series.candles) == cut + 1


class TestDurchlauf:
    def _series_by_tf(self, n=700):
        base = make_series(n)
        from forexwatch.providers.base import resample

        return {
            "1h": base,
            "4h": resample(base, "4h"),
            "1d": resample(base, "1d"),
        }

    def test_liefert_auswertbares_ergebnis(self):
        result = run_backtest(self._series_by_tf(), "EURUSD", "1h", horizon=12, warmup=250)
        data = result.to_dict()
        assert data["bars"] == 700
        assert data["armed_count"] >= 0
        assert set(data) >= {"expansion", "direction", "trading", "spread_pips"}
        assert 0.0 <= data["direction"]["hit_rate"] <= 100.0
        assert 0.0 <= data["trading"]["win_rate"] <= 100.0

    def test_zu_wenig_daten_ergibt_leeres_ergebnis(self):
        base = make_series(80)
        result = run_backtest({"1h": base}, "EURUSD", "1h", horizon=12, warmup=250)
        assert result.armed_count == 0
        assert result.trades == []

    def test_fehlender_timeframe_meldet_fehler(self):
        with pytest.raises(ValueError):
            run_backtest({"1h": make_series(300)}, "EURUSD", "4h")

    def test_sperrfrist_begrenzt_die_signalzahl(self):
        data = self._series_by_tf()
        eng = run_backtest(data, "EURUSD", "1h", horizon=12, warmup=250, cooldown_bars=1)
        weit = run_backtest(data, "EURUSD", "1h", horizon=12, warmup=250, cooldown_bars=60)
        assert weit.armed_count <= eng.armed_count

    def test_spread_verschlechtert_das_ergebnis(self):
        data = self._series_by_tf(900)
        ohne = run_backtest(data, "EURUSD", "1h", horizon=12, warmup=250, spread_pips=0)
        mit = run_backtest(data, "EURUSD", "1h", horizon=12, warmup=250, spread_pips=5)
        if ohne.trades and mit.trades:
            assert mit.expectancy_r < ohne.expectancy_r

    def test_handelsergebnisse_sind_stimmig(self):
        result = run_backtest(self._series_by_tf(900), "EURUSD", "1h", horizon=12, warmup=250)
        for trade in result.trades:
            assert trade.bias in ("long", "short")
            assert trade.won == (trade.result_r > 0)
            if trade.bias == "long":
                assert trade.stop < trade.entry < trade.target
            else:
                assert trade.stop > trade.entry > trade.target
            # Ein Verlust kann durch den Spread etwas unter -1R liegen,
            # aber nie dramatisch darunter.
            assert trade.result_r >= -1.5

    def test_standardspread_je_paar(self):
        assert spread_for("EURUSD") < spread_for("GBPJPY")
        assert spread_for("UNBEKANNT") > 0
