"""Tests der Indikatorbibliothek."""

from __future__ import annotations

import math

import pytest

from forexwatch.analysis import indicators as ind


class TestGleitendeDurchschnitte:
    def test_sma_bekannter_wert(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert ind.sma(values, 3) == [None, None, 2.0, 3.0, 4.0]

    def test_ema_startet_mit_sma(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = ind.ema(values, 3)
        assert result[2] == pytest.approx(2.0)
        # k = 2/(3+1) = 0.5 -> 4*0.5 + 2*0.5 = 3.0
        assert result[3] == pytest.approx(3.0)

    def test_konstante_reihe_ergibt_konstante(self):
        values = [5.0] * 30
        assert ind.sma(values, 10)[-1] == pytest.approx(5.0)
        assert ind.ema(values, 10)[-1] == pytest.approx(5.0)
        assert ind.stdev(values, 10)[-1] == pytest.approx(0.0)

    def test_zu_kurze_reihe_liefert_nur_none(self):
        assert ind.sma([1.0, 2.0], 5) == [None, None]
        assert ind.ema([1.0, 2.0], 5) == [None, None]

    def test_leere_eingabe(self):
        assert ind.sma([], 5) == []
        assert ind.rsi([]) == []
        assert ind.atr([], [], []) == []


class TestVolatilitaet:
    def test_true_range_beruecksichtigt_luecke(self):
        # Kurssprung nach oben: TR misst vom Vorschluss, nicht nur High-Low
        highs = [10.0, 15.0]
        lows = [9.0, 14.0]
        closes = [9.5, 14.5]
        assert ind.true_range(highs, lows, closes) == [1.0, pytest.approx(5.5)]

    def test_atr_positiv(self, ):
        highs = [i + 1.0 for i in range(50)]
        lows = [i - 1.0 for i in range(50)]
        closes = [float(i) for i in range(50)]
        result = ind.atr(highs, lows, closes, 14)
        assert result[-1] is not None and result[-1] > 0

    def test_bollinger_baender_umschliessen_mittellinie(self):
        values = [1.0 + 0.1 * math.sin(i) for i in range(60)]
        upper, mid, lower = ind.bollinger(values, 20, 2.0)
        assert upper[-1] > mid[-1] > lower[-1]

    def test_donchian_ist_hoch_und_tief(self):
        highs = [1.0, 3.0, 2.0, 5.0, 4.0]
        lows = [0.5, 1.0, 0.2, 2.0, 1.5]
        up, dn = ind.donchian(highs, lows, 3)
        assert up[2] == 3.0 and dn[2] == 0.2
        assert up[4] == 5.0 and dn[4] == 0.2


class TestMomentum:
    def test_rsi_bei_stetigem_anstieg_nahe_100(self):
        values = [float(i) for i in range(1, 60)]
        assert ind.rsi(values, 14)[-1] == pytest.approx(100.0)

    def test_rsi_bei_stetigem_rueckgang_nahe_null(self):
        values = [float(i) for i in range(60, 1, -1)]
        assert ind.rsi(values, 14)[-1] == pytest.approx(0.0)

    def test_rsi_bleibt_im_bereich(self):
        import random

        rng = random.Random(1)
        values = [100 + rng.gauss(0, 3) for _ in range(200)]
        for value in ind.rsi(values, 14):
            if value is not None:
                assert 0.0 <= value <= 100.0

    def test_macd_histogramm_ist_differenz(self):
        values = [float(i) + math.sin(i) for i in range(120)]
        line, signal, hist = ind.macd(values)
        assert hist[-1] == pytest.approx(line[-1] - signal[-1])

    def test_stochastik_bleibt_im_bereich(self):
        highs = [10 + math.sin(i) for i in range(80)]
        lows = [8 + math.sin(i) for i in range(80)]
        closes = [9 + math.sin(i) for i in range(80)]
        k, d = ind.stochastic(highs, lows, closes)
        for value in k:
            if value is not None:
                assert 0.0 <= value <= 100.0

    def test_adx_erkennt_starken_trend(self):
        # Sauberer Aufwaertstrend -> ADX deutlich ueber 25
        highs = [100 + i * 1.0 for i in range(120)]
        lows = [99 + i * 1.0 for i in range(120)]
        closes = [99.5 + i * 1.0 for i in range(120)]
        adx, plus_di, minus_di = ind.adx(highs, lows, closes, 14)
        assert adx[-1] is not None and adx[-1] > 25
        assert plus_di[-1] > minus_di[-1]


class TestHilfsfunktionen:
    def test_percentile_rank(self):
        window = [1.0, 2.0, 3.0, 4.0]
        assert ind.percentile_rank(window, 0.5) == 0.0
        assert ind.percentile_rank(window, 5.0) == 100.0
        assert ind.percentile_rank(window, 2.5) == 50.0

    def test_percentile_rank_leeres_fenster(self):
        assert ind.percentile_rank([], 1.0) == 50.0

    def test_linreg_slope_vorzeichen(self):
        assert ind.linreg_slope([1.0, 2.0, 3.0, 4.0]) > 0
        assert ind.linreg_slope([4.0, 3.0, 2.0, 1.0]) < 0
        assert ind.linreg_slope([2.0, 2.0, 2.0]) == pytest.approx(0.0)

    def test_pearson_grenzfaelle(self):
        a = [1.0, 2.0, 3.0, 4.0]
        assert ind.pearson(a, a) == pytest.approx(1.0)
        assert ind.pearson(a, [4.0, 3.0, 2.0, 1.0]) == pytest.approx(-1.0)
        assert ind.pearson([1.0], [1.0]) == 0.0
        assert ind.pearson(a, [2.0, 2.0, 2.0, 2.0]) == 0.0

    def test_last_valid_mit_versatz(self):
        values = [1.0, None, 2.0, None, 3.0]
        assert ind.last_valid(values) == 3.0
        assert ind.last_valid(values, 1) == 2.0
        assert ind.last_valid([None, None]) is None


class TestLaengentreue:
    """Jeder Indikator muss exakt so lang sein wie die Eingabe – darauf
    stuetzen sich Chart und Backtest."""

    def test_alle_indikatoren_laengentreu(self, series):
        n = len(series)
        closes, highs, lows = series.closes, series.highs, series.lows
        arrays = [
            ind.sma(closes, 20), ind.ema(closes, 20), ind.rma(closes, 20),
            ind.stdev(closes, 20), ind.rsi(closes), ind.atr(highs, lows, closes),
            *ind.bollinger(closes), *ind.keltner(highs, lows, closes),
            *ind.donchian(highs, lows), *ind.macd(closes),
            *ind.adx(highs, lows, closes), *ind.stochastic(highs, lows, closes),
        ]
        for arr in arrays:
            assert len(arr) == n
