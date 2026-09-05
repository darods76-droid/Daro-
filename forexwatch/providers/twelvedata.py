"""TwelveData-Provider (optional, benoetigt einen kostenlosen API-Schluessel).

Liefert im Vergleich zu Yahoo saubere Forex-Zeitreihen inklusive 4h-Intervall
und ist die bessere Wahl, wenn ein Schluessel hinterlegt ist.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from ..config import settings
from ..models import Candle, Series
from .base import DataProvider, resample

log = logging.getLogger("forexwatch.twelvedata")

BASE_URL = "https://api.twelvedata.com/time_series"

INTERVAL_MAP = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "1d": "1day",
    "1w": "1week",
}


def to_td_symbol(symbol: str) -> str:
    """EURUSD -> EUR/USD (TwelveData erwartet den Schraegstrich)."""
    key = symbol.upper().replace("/", "")
    if key == "XAUUSD":
        return "XAU/USD"
    if len(key) == 6:
        return f"{key[:3]}/{key[3:]}"
    return key


class TwelveDataProvider(DataProvider):
    name = "twelvedata"
    native_timeframes = ("1m", "5m", "15m", "30m", "1h", "2h", "4h", "1d")

    def __init__(self, api_key: str | None = None) -> None:
        self._key = api_key or settings.twelvedata_key
        self._client: httpx.AsyncClient | None = None
        # Der kostenlose Tarif erlaubt 8 Anfragen pro Minute – deshalb wird
        # bewusst serialisiert statt parallelisiert.
        self._gate = asyncio.Semaphore(2)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(25.0), follow_redirects=True)
        return self._client

    async def fetch(self, symbol: str, timeframe: str, limit: int = 500) -> Series:
        if not self._key:
            log.warning("TwelveData ohne API-Schluessel aufgerufen – leere Reihe")
            return Series(symbol.upper(), timeframe, [])

        source_tf, factor = self._source_timeframe(timeframe, self.native_timeframes)
        interval = INTERVAL_MAP.get(source_tf, "1h")
        outputsize = min(5000, max(50, limit * max(1, factor) + 10))

        params = {
            "symbol": to_td_symbol(symbol),
            "interval": interval,
            "outputsize": str(outputsize),
            "apikey": self._key,
            "format": "JSON",
            "timezone": "UTC",
        }

        async with self._gate:
            candles = await self._request(params, symbol)

        series = Series(symbol.upper(), source_tf, candles)
        if factor > 1 or timeframe.lower() != source_tf:
            series = resample(series, timeframe.lower())
        if len(series.candles) > limit:
            series.candles = series.candles[-limit:]
        return series

    async def _request(self, params: dict, symbol: str) -> list[Candle]:
        client = await self._get_client()
        for attempt in range(3):
            try:
                response = await client.get(BASE_URL, params=params)
                response.raise_for_status()
                payload = response.json()
                if payload.get("status") == "error":
                    log.warning("TwelveData meldet Fehler fuer %s: %s", symbol, payload.get("message"))
                    return []
                return self._parse(payload)
            except Exception as exc:
                if attempt < 2:
                    await asyncio.sleep(2.0 * (attempt + 1))
                else:
                    log.warning("TwelveData-Abruf fuer %s fehlgeschlagen: %s", symbol, exc)
        return []

    @staticmethod
    def _parse(payload: dict) -> list[Candle]:
        from datetime import datetime, timezone

        candles: list[Candle] = []
        for row in payload.get("values", []):
            try:
                raw = str(row["datetime"])
                when = datetime.fromisoformat(raw) if " " in raw or "T" in raw else datetime.strptime(raw, "%Y-%m-%d")
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                candles.append(
                    Candle(
                        ts=int(when.timestamp()),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume") or 0.0),
                    )
                )
            except (KeyError, ValueError, TypeError):
                continue
        candles.sort(key=lambda c: c.ts)
        return candles

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
