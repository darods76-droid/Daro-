"""Tests der Risiko- und Positionsberechnung."""

from __future__ import annotations

import pytest

from forexwatch.risk import (
    build_levels,
    pip_size,
    pip_value_per_lot,
    position_plan,
    to_pips,
)


class TestPips:
    def test_pip_groessen(self):
        assert pip_size("EURUSD") == 0.0001
        assert pip_size("USDJPY") == 0.01
        assert pip_size("EURJPY") == 0.01
        assert pip_size("XAUUSD") == 0.1

    def test_umrechnung_in_pips(self):
        assert to_pips("EURUSD", 0.0030) == pytest.approx(30.0)
        assert to_pips("USDJPY", 0.30) == pytest.approx(30.0)
        assert to_pips("EURUSD", -0.0030) == pytest.approx(30.0)


class TestNiveaus:
    def test_long_reihenfolge(self):
        lv = build_levels("EURUSD", 1.0850, 0.0012, "long", 1.0865, 1.0835)
        assert lv.stop < lv.entry < lv.take_profit_1 < lv.take_profit_2
        assert lv.rr == pytest.approx(1.8, abs=0.05)

    def test_short_reihenfolge(self):
        lv = build_levels("USDJPY", 151.2, 0.18, "short", 151.6, 151.0)
        assert lv.stop > lv.entry > lv.take_profit_1 > lv.take_profit_2

    def test_stop_haelt_mindestabstand(self):
        # Sehr enge Zone: der Stop muss trotzdem mindestens 1.2 ATR entfernt liegen
        atr = 0.0020
        lv = build_levels("EURUSD", 1.0850, atr, "long", 1.08501, 1.08499)
        assert lv.entry - lv.stop >= atr * 1.2 * 0.999

    def test_atr_null_fuehrt_nicht_zu_division_durch_null(self):
        lv = build_levels("EURUSD", 1.0850, 0.0, "long", 1.0860, 1.0840)
        assert lv.rr > 0 and lv.stop < lv.entry


class TestPipWert:
    RATES = {"EURUSD": 1.16212, "GBPUSD": 1.35170, "USDJPY": 156.221}

    def test_kontowaehrung_gleich_kurswaehrung(self):
        value, approx = pip_value_per_lot("EURUSD", 1.16, "USD", {})
        assert value == pytest.approx(10.0) and approx is False

    def test_direkte_umrechnung(self):
        value, approx = pip_value_per_lot("EURUSD", 1.16212, "EUR", self.RATES)
        assert value == pytest.approx(10.0 / 1.16212, rel=1e-6)
        assert approx is False

    def test_umrechnung_ueber_us_dollar(self):
        # 1000 JPY -> USD -> EUR
        value, approx = pip_value_per_lot("USDJPY", 156.221, "EUR", self.RATES)
        expected = 1000.0 / 156.221 / 1.16212
        assert value == pytest.approx(expected, rel=1e-6)
        assert approx is False

    def test_ohne_kurse_naeherung(self):
        value, approx = pip_value_per_lot("GBPJPY", 211.0, "CHF", {})
        assert approx is True and value == pytest.approx(1000.0)

    def test_gold_hat_hundert_einheiten(self):
        value, _ = pip_value_per_lot("XAUUSD", 2320.0, "USD", {})
        assert value == pytest.approx(0.1 * 100)


class TestPositionsgroesse:
    def test_risiko_wird_genau_getroffen(self):
        rates = {"EURUSD": 1.16212}
        plan = position_plan("EURUSD", 1.1000, 1.0970, 10_000, 1.0, "EUR", rates)
        # Lots * Pips * Pip-Wert muss dem Risikobetrag entsprechen
        assert plan.lots * plan.risk_pips * plan.pip_value == pytest.approx(100.0, rel=1e-6)
        assert plan.risk_amount == pytest.approx(100.0)
        assert plan.risk_pips == pytest.approx(30.0)

    def test_hoeheres_risiko_ergibt_groessere_position(self):
        rates = {"EURUSD": 1.16212}
        klein = position_plan("EURUSD", 1.10, 1.097, 10_000, 1.0, "EUR", rates)
        gross = position_plan("EURUSD", 1.10, 1.097, 10_000, 2.0, "EUR", rates)
        assert gross.lots == pytest.approx(klein.lots * 2, rel=1e-6)

    def test_weiterer_stop_ergibt_kleinere_position(self):
        rates = {"EURUSD": 1.16212}
        eng = position_plan("EURUSD", 1.10, 1.097, 10_000, 1.0, "EUR", rates)
        weit = position_plan("EURUSD", 1.10, 1.094, 10_000, 1.0, "EUR", rates)
        assert weit.lots == pytest.approx(eng.lots / 2, rel=1e-6)

    def test_stop_gleich_einstieg_ergibt_null(self):
        plan = position_plan("EURUSD", 1.10, 1.10, 10_000, 1.0, "EUR", {})
        assert plan.lots == 0.0 and "null" in plan.note.lower()

    def test_serialisierbar(self):
        plan = position_plan("EURUSD", 1.10, 1.097, 10_000, 1.0, "EUR", {})
        data = plan.to_dict()
        assert set(data) >= {"lots", "units", "risk_amount", "risk_pips", "pip_value"}
