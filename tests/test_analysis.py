"""Tests fuer Marktstruktur, Sessions, Signale und Scoring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from forexwatch.analysis import sessions, structure
from forexwatch.analysis.features import build_features, squeeze_length
from forexwatch.analysis.scoring import evaluate
from forexwatch.analysis.signals import MarketContext, detect_all
from forexwatch.models import Candle, Series
from tests.conftest import make_series, make_squeeze_series


class TestStruktur:
    def test_swing_hoch_und_tief(self):
        # Zickzack: Index 2 ist ein Hoch, Index 4 ein Tief
        prices = [1.0, 1.1, 1.3, 1.1, 0.9, 1.1, 1.2]
        candles = [Candle(i, p, p + 0.01, p - 0.01, p) for i, p in enumerate(prices)]
        swings = structure.find_swings(candles, 2, 2)
        assert any(s.kind == "high" and s.index == 2 for s in swings)
        assert any(s.kind == "low" and s.index == 4 for s in swings)

    def test_struktur_aufwaerts(self):
        swings = [
            structure.Swing(0, 1.0, "low"), structure.Swing(1, 1.2, "high"),
            structure.Swing(2, 1.1, "low"), structure.Swing(3, 1.3, "high"),
        ]
        assert structure.market_structure(swings) == "aufwaerts"

    def test_struktur_abwaerts(self):
        swings = [
            structure.Swing(0, 1.3, "high"), structure.Swing(1, 1.1, "low"),
            structure.Swing(2, 1.2, "high"), structure.Swing(3, 1.0, "low"),
        ]
        assert structure.market_structure(swings) == "abwaerts"

    def test_struktur_unklar_bei_zu_wenig_swings(self):
        assert structure.market_structure([]) == "unklar"

    def test_liquiditaets_sweep_nach_oben(self):
        # Ruhige Spanne, dann eine Kerze mit langem Docht ueber das Hoch
        candles = [Candle(i, 1.10, 1.101, 1.099, 1.10) for i in range(40)]
        candles.append(Candle(40, 1.100, 1.115, 1.0995, 1.1005))
        result = structure.liquidity_sweep(Series("EURUSD", "1h", candles), lookback=30)
        assert result is not None
        assert result["direction"] == "short"
        assert result["level"] == pytest.approx(1.101)

    def test_kein_sweep_ohne_docht(self):
        candles = [Candle(i, 1.10, 1.101, 1.099, 1.10) for i in range(40)]
        candles.append(Candle(40, 1.101, 1.115, 1.1009, 1.1149))  # Ausbruch, kein Docht
        assert structure.liquidity_sweep(Series("EURUSD", "1h", candles), 30) is None

    def test_inside_bars(self):
        candles = [
            Candle(0, 1.0, 1.10, 0.90, 1.0),
            Candle(1, 1.0, 1.08, 0.92, 1.0),
            Candle(2, 1.0, 1.06, 0.94, 1.0),
        ]
        assert structure.inside_bars(candles) == 2

    def test_narrow_range(self):
        candles = [Candle(i, 1.0, 1.0 + 0.01, 1.0 - 0.01, 1.0) for i in range(7)]
        candles.append(Candle(7, 1.0, 1.0005, 0.9995, 1.0))
        assert structure.narrow_range(candles, 7) is True

    def test_key_levels_liefert_zonen(self):
        levels = structure.key_levels(make_series(200))
        assert levels
        assert all({"price", "touches", "kind", "score"} <= set(lv) for lv in levels)
        # Nach Relevanz absteigend sortiert
        assert [lv["score"] for lv in levels] == sorted(
            (lv["score"] for lv in levels), reverse=True
        )


class TestSessions:
    def test_fenster_ueber_mitternacht(self):
        # Sydney laeuft 21:00-06:00 UTC
        assert "Sydney" in sessions.active_sessions(datetime(2026, 9, 2, 23, tzinfo=timezone.utc))
        assert "Sydney" in sessions.active_sessions(datetime(2026, 9, 2, 3, tzinfo=timezone.utc))
        assert "Sydney" not in sessions.active_sessions(datetime(2026, 9, 2, 12, tzinfo=timezone.utc))

    def test_wochenende(self):
        assert sessions.is_weekend(datetime(2026, 9, 5, 12, tzinfo=timezone.utc))    # Samstag
        assert sessions.is_weekend(datetime(2026, 9, 4, 22, tzinfo=timezone.utc))    # Fr nach 21h
        assert sessions.is_weekend(datetime(2026, 9, 6, 12, tzinfo=timezone.utc))    # So vor 21h
        assert not sessions.is_weekend(datetime(2026, 9, 2, 12, tzinfo=timezone.utc))  # Mittwoch

    def test_volatilitaet_am_wochenende_null(self):
        assert sessions.session_volatility_factor(
            datetime(2026, 9, 5, 12, tzinfo=timezone.utc)
        ) == 0.0

    def test_ueberschneidung_hat_hoechsten_faktor(self):
        overlap = sessions.session_volatility_factor(datetime(2026, 9, 2, 14, tzinfo=timezone.utc))
        asia = sessions.session_volatility_factor(datetime(2026, 9, 2, 2, tzinfo=timezone.utc))
        assert overlap > asia

    def test_naechster_zeitpunkt_liegt_in_der_zukunft(self):
        now = datetime(2026, 9, 2, 6, 30, tzinfo=timezone.utc)
        name, minutes = sessions.next_key_moment(now)
        assert name == "London-Open" and minutes == 30

    def test_asien_spanne(self):
        # 00:00-07:00 UTC eng, davor 20 Tage mit weiter Spanne
        base = datetime(2026, 9, 2, tzinfo=timezone.utc)
        candles = []
        for day in range(20, 0, -1):
            start = base - timedelta(days=day)
            for h in range(24):
                ts = int((start + timedelta(hours=h)).timestamp())
                candles.append(Candle(ts, 1.10, 1.11, 1.09, 1.10))  # weite Tagesspanne
        for h in range(7):
            ts = int((base + timedelta(hours=h)).timestamp())
            candles.append(Candle(ts, 1.100, 1.1005, 1.0995, 1.100))  # enge Nacht

        result = sessions.asian_range(candles, base + timedelta(hours=8))
        assert result is not None
        assert result["compressed"] is True
        assert result["ratio_to_daily"] < 0.45

    def test_asien_spanne_ohne_daten(self):
        assert sessions.asian_range([], datetime(2026, 9, 2, 8, tzinfo=timezone.utc)) is None


class TestSignale:
    def _context(self, series, now=None, **kwargs):
        features = {"1h": build_features(series)}
        return MarketContext(
            symbol="EURUSD",
            execution_tf="1h",
            features=features,
            now=now or datetime(2026, 9, 2, 8, tzinfo=timezone.utc),
            **kwargs,
        )

    def test_squeeze_wird_erkannt(self, squeeze_series):
        features = build_features(squeeze_series)
        assert squeeze_length(features) > 0, "Testreihe sollte am Ende komprimiert sein"
        hits = detect_all(self._context(squeeze_series))
        assert any(h.key == "squeeze" for h in hits)

    def test_detektoren_liefern_gueltige_bereiche(self, series):
        for hit in detect_all(self._context(series)):
            assert 0.0 <= hit.readiness <= 1.0, hit.key
            assert -1.0 <= hit.direction <= 1.0, hit.key
            assert hit.weight > 0
            assert hit.label and hit.category

    def test_kalenderdruck_wird_gemeldet(self, series):
        risk = {"title": "NFP", "currency": "USD", "impact": "hoch",
                "minutes": 30, "advice": "warten"}
        hits = detect_all(self._context(series, calendar_risk=risk))
        hit = next((h for h in hits if h.key == "calendar_pressure"), None)
        assert hit is not None and "NFP" in hit.detail

    def test_kein_kalenderdruck_ohne_termin(self, series):
        hits = detect_all(self._context(series))
        assert not any(h.key == "calendar_pressure" for h in hits)

    def test_defekter_detektor_stoppt_den_lauf_nicht(self, series, monkeypatch):
        from forexwatch.analysis import signals as sig

        def kaputt(ctx):
            raise RuntimeError("absichtlicher Fehler")

        monkeypatch.setattr(sig, "DETECTORS", (kaputt, sig.detect_structure))
        # Darf nicht durchschlagen – ein Detektor darf den Scan nie anhalten
        assert isinstance(sig.detect_all(self._context(series)), list)


class TestScoring:
    def _setup(self, series, now=None, **kwargs):
        ctx = MarketContext(
            symbol="EURUSD",
            execution_tf="1h",
            features={"1h": build_features(series)},
            now=now or datetime(2026, 9, 2, 8, tzinfo=timezone.utc),
            **kwargs,
        )
        return evaluate(ctx)

    def test_kennzahlen_in_gueltigen_bereichen(self, series):
        s = self._setup(series)
        assert 0.0 <= s.readiness <= 100.0
        assert -100.0 <= s.direction <= 100.0
        assert 0.0 <= s.confidence <= 100.0
        assert s.bias in ("long", "short", "neutral")
        assert s.state in ("WATCH", "ARMED", "TRIGGERED", "COOLDOWN", "GESCHLOSSEN")

    def test_am_wochenende_geschlossen(self, series):
        s = self._setup(series, now=datetime(2026, 9, 5, 12, tzinfo=timezone.utc))
        assert s.state == "GESCHLOSSEN"

    def test_niveaus_sind_stimmig(self, series):
        s = self._setup(series)
        lv = s.levels
        assert lv is not None
        assert lv.trigger_long > lv.trigger_short
        if s.bias == "short":
            assert lv.stop > lv.entry > lv.take_profit_1
        else:
            assert lv.stop < lv.entry < lv.take_profit_1
        assert lv.rr > 0

    def test_setup_ist_serialisierbar(self, series):
        import json

        data = self._setup(series).to_dict()
        assert json.loads(json.dumps(data))["symbol"] == "EURUSD"
