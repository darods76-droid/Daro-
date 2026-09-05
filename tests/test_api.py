"""Tests der JSON-Schnittstelle.

Der Scanner wird durch eine synthetische Datenquelle ersetzt, damit die
Tests ohne Netzzugang und reproduzierbar laufen.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from forexwatch import app as app_module
from forexwatch.providers.synthetic import SyntheticProvider


@pytest.fixture
def client(tmp_path, monkeypatch):
    from forexwatch.storage import Storage

    engine = app_module.engine
    engine.provider = SyntheticProvider(seed=5)
    engine.storage = Storage(tmp_path / "test.db")

    # Der Hintergrund-Scanner wird nicht gebraucht: ein einzelner Durchlauf
    # beim Start genuegt und macht die Tests deterministisch.
    async def start_once():
        await engine.scan()

    async def stop_noop():
        return None

    monkeypatch.setattr(engine, "start", start_once)
    monkeypatch.setattr(engine, "stop", stop_noop)

    with TestClient(app_module.app) as test_client:
        yield test_client


class TestZustand:
    def test_status(self, client):
        data = client.get("/api/status").json()
        assert data["provider"] == "synthetic"
        assert data["pairs"] and data["timeframes"]
        assert data["scan_count"] >= 1

    def test_setups(self, client):
        data = client.get("/api/setups").json()
        assert data["count"] > 0
        first = data["setups"][0]
        assert {"symbol", "state", "readiness", "direction", "confidence", "levels"} <= set(first)

    def test_setups_nach_zustand_gefiltert(self, client):
        data = client.get("/api/setups?state=WATCH").json()
        assert all(s["state"] == "WATCH" for s in data["setups"])

    def test_setups_nach_bereitschaft_gefiltert(self, client):
        data = client.get("/api/setups?min_readiness=50").json()
        assert all(s["readiness"] >= 50 for s in data["setups"])

    def test_einzelnes_setup(self, client):
        symbol = client.get("/api/setups").json()["setups"][0]["symbol"]
        assert client.get(f"/api/setup/{symbol}").json()["symbol"] == symbol

    def test_unbekanntes_setup_gibt_404(self, client):
        response = client.get("/api/setup/XXXYYY")
        assert response.status_code == 404
        assert "error" in response.json()


class TestKerzen:
    def test_kerzen_und_indikatoren(self, client):
        symbol = client.get("/api/setups").json()["setups"][0]["symbol"]
        data = client.get(f"/api/candles/{symbol}?limit=100").json()
        assert len(data["candles"]) == 100
        # Indikatorreihen muessen exakt zu den Kerzen passen, sonst
        # verrutscht der Chart.
        for name, values in data["indicators"].items():
            assert len(values) == 100, name

    def test_unbekanntes_paar_gibt_404(self, client):
        assert client.get("/api/candles/XXXYYY").status_code == 404


class TestWerkzeuge:
    def test_positionsgroesse(self, client):
        data = client.get(
            "/api/position",
            params={"symbol": "EURUSD", "entry": 1.1000, "stop": 1.0970,
                    "balance": 10000, "risk_percent": 1, "currency": "USD"},
        ).json()
        assert data["risk_pips"] == pytest.approx(30.0)
        # Die Ausgabe rundet auf 0.01 Lot – so handeln Broker auch. Deshalb
        # wird hier nur die Groessenordnung geprueft; die exakte Rechnung
        # deckt test_risk.py gegen den ungerundeten Wert ab.
        risk = data["lots"] * data["risk_pips"] * data["pip_value"]
        assert risk == pytest.approx(100.0, abs=data["risk_pips"] * data["pip_value"] * 0.005 + 1e-9)
        assert data["approximated"] is False

    def test_positionsgroesse_ohne_abstand_gibt_400(self, client):
        response = client.get(
            "/api/position", params={"symbol": "EURUSD", "entry": 1.1, "stop": 1.1}
        )
        assert response.status_code == 400

    def test_manueller_scan(self, client):
        data = client.post("/api/scan").json()
        assert data["count"] > 0

    def test_sessions(self, client):
        data = client.get("/api/sessions").json()
        assert "label" in data and "windows" in data
        assert isinstance(data["market_open"], bool)

    def test_alarme_und_verlauf(self, client):
        assert "alerts" in client.get("/api/alerts").json()
        symbol = client.get("/api/setups").json()["setups"][0]["symbol"]
        assert "history" in client.get(f"/api/history/{symbol}").json()

    def test_backtest(self, client):
        symbol = client.get("/api/setups").json()["setups"][0]["symbol"]
        data = client.get(f"/api/backtest/{symbol}?bars=600").json()
        assert {"expansion", "direction", "trading"} <= set(data)


class TestOberflaeche:
    def test_startseite(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "ForexWatch" in response.text

    def test_statische_dateien(self, client):
        for path in ("/static/app.js", "/static/chart.js", "/static/style.css"):
            assert client.get(path).status_code == 200


class TestLiveVerbindung:
    def test_websocket_liefert_snapshot(self, client):
        with client.websocket_connect("/ws") as socket:
            message = socket.receive_json()
            assert message["event"] == "snapshot"
            assert "status" in message["payload"]
            assert "setups" in message["payload"]
