"""Tests der Alarmlogik und der Persistenz."""

from __future__ import annotations

import time

import pytest

from forexwatch import alerts as alerts_module
from forexwatch.alerts import AlertEngine
from forexwatch.models import Alert, Levels, SignalHit, Setup
from forexwatch.storage import Storage
from tests.conftest import make_series


def make_setup(state="ARMED", readiness=70.0, bias="long", symbol="EURUSD") -> Setup:
    return Setup(
        symbol=symbol, timeframe="1h", ts=1_700_000_000, price=1.0850,
        state=state, readiness=readiness, direction=40.0, confidence=80.0, bias=bias,
        hits=[SignalHit("squeeze", "Kompression", 0.8, 0.0, 2.4, "Squeeze seit 12 Kerzen", "kompression")],
        levels=Levels(1.09, 1.086, 1.098, 1.102, 1.09, 1.086, 0.001, 1.8),
        regime="Trend", session="London",
    )


class TestAlarmentscheidung:
    def _fire(self, engine: AlertEngine, setup: Setup) -> tuple[bool, str]:
        ok, reason = engine.should_alert(setup)
        engine.remember(setup)
        if ok:
            engine._remember_alert(setup)
        return ok, reason

    def test_watch_loest_nichts_aus(self):
        engine = AlertEngine()
        assert self._fire(engine, make_setup("WATCH", 40))[0] is False

    def test_uebergang_watch_zu_armed_meldet(self):
        """Der wichtigste Fall ueberhaupt: aus der Ruhe wird ein scharfes Setup."""
        engine = AlertEngine()
        self._fire(engine, make_setup("WATCH", 40))
        ok, reason = self._fire(engine, make_setup("ARMED", 65))
        assert ok is True and reason == "neu erkannt"

    def test_kein_dauerfeuer_im_gleichen_zustand(self):
        engine = AlertEngine()
        self._fire(engine, make_setup("ARMED", 65))
        assert self._fire(engine, make_setup("ARMED", 66))[0] is False
        assert self._fire(engine, make_setup("ARMED", 67))[0] is False

    def test_ausbruch_meldet_immer(self):
        engine = AlertEngine()
        self._fire(engine, make_setup("ARMED", 65))
        ok, reason = self._fire(engine, make_setup("TRIGGERED", 78))
        assert ok is True and "Ausbruch" in reason

    def test_richtungswechsel_meldet(self):
        engine = AlertEngine()
        self._fire(engine, make_setup("ARMED", 65, "long"))
        ok, reason = self._fire(engine, make_setup("ARMED", 66, "short"))
        assert ok is True and "gedreht" in reason

    def test_erneute_meldung_nach_ablauf_der_sperre(self, monkeypatch):
        monkeypatch.setattr(alerts_module, "COOLDOWN", 0)
        engine = AlertEngine()
        self._fire(engine, make_setup("ARMED", 60))
        ok, reason = self._fire(engine, make_setup("ARMED", 80))
        assert ok is True and "gestiegen" in reason

    def test_zurueck_nach_armed_wird_gedaempft(self):
        """Flattern an der Schwelle darf keine Meldungslawine ausloesen."""
        engine = AlertEngine()
        self._fire(engine, make_setup("ARMED", 63))
        self._fire(engine, make_setup("WATCH", 58))
        assert self._fire(engine, make_setup("ARMED", 63))[0] is False

    def test_instrumente_werden_getrennt_verfolgt(self):
        engine = AlertEngine()
        assert self._fire(engine, make_setup("ARMED", 65, symbol="EURUSD"))[0] is True
        assert self._fire(engine, make_setup("ARMED", 65, symbol="GBPUSD"))[0] is True


class TestAlarmtext:
    def test_enthaelt_die_wesentlichen_angaben(self):
        alert = AlertEngine.compose(make_setup(), "neu erkannt")
        assert "EURUSD" in alert.message
        assert "Bereitschaft 70" in alert.message
        assert "Stop" in alert.message
        assert "Kompression" in alert.message
        assert alert.payload["symbol"] == "EURUSD"

    def test_richtungswort_wird_uebersetzt(self):
        assert "aufwaerts" in AlertEngine.compose(make_setup(bias="long"), "x").message
        assert "abwaerts" in AlertEngine.compose(make_setup(bias="short"), "x").message
        assert "beidseitig" in AlertEngine.compose(make_setup(bias="neutral"), "x").message

    @pytest.mark.asyncio
    async def test_versand_ueberlebt_defekten_empfaenger(self):
        engine = AlertEngine()

        async def kaputt(alert):
            raise RuntimeError("Empfaenger down")

        engine.on_alert = kaputt
        # Darf nicht durchschlagen – ein toter Kanal stoppt den Scanner nicht
        await engine.dispatch(AlertEngine.compose(make_setup(), "test"))


class TestSpeicher:
    def test_kerzen_roundtrip(self, tmp_path):
        store = Storage(tmp_path / "t.db")
        series = make_series(120)
        store.save_candles(series)
        back = store.load_candles("EURUSD", "1h", 120)
        assert len(back) == 120
        assert back.candles[-1].close == pytest.approx(series.candles[-1].close)
        store.close()

    def test_wiederholtes_speichern_erzeugt_keine_dubletten(self, tmp_path):
        store = Storage(tmp_path / "t.db")
        series = make_series(50)
        store.save_candles(series)
        store.save_candles(series)
        assert store.stats()["candles"] == 50
        store.close()

    def test_setups_und_alarme(self, tmp_path):
        store = Storage(tmp_path / "t.db")
        store.save_setup(make_setup())
        store.save_alert(Alert(int(time.time()), "EURUSD", "1h", "ARMED", "long", 70.0, "Hallo", {"k": 1}))

        history = store.setup_history("EURUSD")
        assert len(history) == 1
        assert history[0]["payload"]["readiness"] == 70.0

        alerts = store.recent_alerts()
        assert alerts[0]["message"] == "Hallo"
        assert alerts[0]["payload"] == {"k": 1}
        store.close()

    def test_aufraeumen_behaelt_die_neuesten(self, tmp_path):
        store = Storage(tmp_path / "t.db")
        store.save_candles(make_series(200))
        store.prune_candles(50)
        assert store.stats()["candles"] == 50
        back = store.load_candles("EURUSD", "1h", 100)
        # Die juengsten Kerzen muessen erhalten bleiben
        assert len(back) == 50
        store.close()

    def test_leere_reihe_wird_ignoriert(self, tmp_path):
        from forexwatch.models import Series

        store = Storage(tmp_path / "t.db")
        store.save_candles(Series("EURUSD", "1h", []))
        assert store.stats()["candles"] == 0
        store.close()
