"""Persistenz auf SQLite-Basis.

Gespeichert werden drei Dinge:

* ein Verlauf aller Bewertungen  – damit sich nachvollziehen laesst, was das
  System *vor* einer Bewegung gemeldet hat,
* alle ausgeloesten Alarme,
* ein Kerzen-Cache, damit der Dienst nach einem Neustart sofort
  arbeitsfaehig ist und Ausfaelle der Datenquelle ueberbrueckt werden.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .models import Alert, Candle, Series, Setup

SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    symbol    TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts        INTEGER NOT NULL,
    open      REAL NOT NULL,
    high      REAL NOT NULL,
    low       REAL NOT NULL,
    close     REAL NOT NULL,
    volume    REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, timeframe, ts)
);

CREATE TABLE IF NOT EXISTS setups (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         INTEGER NOT NULL,
    symbol     TEXT NOT NULL,
    timeframe  TEXT NOT NULL,
    state      TEXT NOT NULL,
    bias       TEXT NOT NULL,
    readiness  REAL NOT NULL,
    direction  REAL NOT NULL,
    confidence REAL NOT NULL,
    price      REAL NOT NULL,
    payload    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_setups_symbol_ts ON setups (symbol, ts DESC);
CREATE INDEX IF NOT EXISTS idx_setups_state ON setups (state, ts DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        INTEGER NOT NULL,
    symbol    TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    state     TEXT NOT NULL,
    bias      TEXT NOT NULL,
    readiness REAL NOT NULL,
    message   TEXT NOT NULL,
    payload   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts (ts DESC);
"""


class Storage:
    """Duenne, threadsichere Huelle um SQLite."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL erlaubt gleichzeitiges Lesen waehrend der Scanner schreibt.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # -- Kerzen ------------------------------------------------------------

    def save_candles(self, series: Series) -> None:
        if not series.candles:
            return
        rows = [
            (series.symbol, series.timeframe, c.ts, c.open, c.high, c.low, c.close, c.volume)
            for c in series.candles
        ]
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO candles "
                "(symbol, timeframe, ts, open, high, low, close, volume) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            self._conn.commit()

    def load_candles(self, symbol: str, timeframe: str, limit: int = 500) -> Series:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT ts, open, high, low, close, volume FROM candles "
                "WHERE symbol = ? AND timeframe = ? ORDER BY ts DESC LIMIT ?",
                (symbol, timeframe, limit),
            )
            rows = cursor.fetchall()
        candles = [
            Candle(r["ts"], r["open"], r["high"], r["low"], r["close"], r["volume"])
            for r in reversed(rows)
        ]
        return Series(symbol, timeframe, candles)

    def prune_candles(self, keep_per_series: int = 3000) -> int:
        """Alte Kerzen entfernen, damit die Datei nicht unbegrenzt waechst."""
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM candles WHERE rowid NOT IN ("
                "  SELECT rowid FROM ("
                "    SELECT rowid, ROW_NUMBER() OVER "
                "      (PARTITION BY symbol, timeframe ORDER BY ts DESC) AS rn"
                "    FROM candles"
                "  ) WHERE rn <= ?"
                ")",
                (keep_per_series,),
            )
            self._conn.commit()
            return cursor.rowcount

    # -- Bewertungen -------------------------------------------------------

    def save_setup(self, setup: Setup) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO setups (ts, symbol, timeframe, state, bias, readiness, "
                "direction, confidence, price, payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    setup.ts,
                    setup.symbol,
                    setup.timeframe,
                    setup.state,
                    setup.bias,
                    setup.readiness,
                    setup.direction,
                    setup.confidence,
                    setup.price,
                    json.dumps(setup.to_dict(), ensure_ascii=False),
                ),
            )
            self._conn.commit()

    def setup_history(self, symbol: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT * FROM setups"
        params: list[Any] = []
        if symbol:
            query += " WHERE symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._row_with_payload(r) for r in rows]

    # -- Alarme ------------------------------------------------------------

    def save_alert(self, alert: Alert) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO alerts (ts, symbol, timeframe, state, bias, readiness, message, payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    alert.ts,
                    alert.symbol,
                    alert.timeframe,
                    alert.state,
                    alert.bias,
                    alert.readiness,
                    alert.message,
                    json.dumps(alert.payload, ensure_ascii=False),
                ),
            )
            self._conn.commit()

    def recent_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_with_payload(r) for r in rows]

    # -- Hilfen ------------------------------------------------------------

    @staticmethod
    def _row_with_payload(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        try:
            data["payload"] = json.loads(data.get("payload") or "{}")
        except json.JSONDecodeError:
            data["payload"] = {}
        return data

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "candles": self._conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0],
                "setups": self._conn.execute("SELECT COUNT(*) FROM setups").fetchone()[0],
                "alerts": self._conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0],
            }

    def close(self) -> None:
        with self._lock:
            self._conn.close()
