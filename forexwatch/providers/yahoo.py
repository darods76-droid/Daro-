"""Yahoo-Finance-Provider.

Benoetigt keinen API-Schluessel und liefert Intraday-Kerzen fuer alle
gaengigen Waehrungspaare sowie fuer Gold und den Dollar-Index. Yahoo kennt
kein 4h-Intervall, deshalb wird bei Bedarf aus 1h-Kerzen verdichtet.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from ..models import Candle, Series
from .base import DataProvider, resample, timeframe_seconds

log = logging.getLogger("forexwatch.yahoo")

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# Instrumente, die nicht dem Schema "PAAR=X" folgen
SPECIAL_SYMBOLS = {
    "XAUUSD": "GC=F",      # Gold-Future als Ersatz fuer Gold-Spot
    "XAGUSD": "SI=F",      # Silber
    "DXY": "DX-Y.NYB",     # US-Dollar-Index
    "WTI": "CL=F",
    "SPX": "^GSPC",
    "NDX": "^NDC",
    "DAX": "^GDAXI",
}

# Yahoo verlangt zu jedem Intervall eine passende Zeitspanne
RANGE_FOR_INTERVAL = {
    "1m": "7d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "60m": "730d",
    "1h": "730d",
    "1d": "5y",
    "1wk": "10y",
}

INTERVAL_MAP = {"1h": "60m", "1w": "1wk"}


def to_yahoo_symbol(symbol: str) -> str:
    """Internes Kuerzel in ein Yahoo-Ticker uebersetzen."""
    key = symbol.upper().replace("/", "")
    if key in SPECIAL_SYMBOLS:
        return SPECIAL_SYMBOLS[key]
    if "=" in key or "^" in key:
        return key
    return f"{key}=X"


class YahooProvider(DataProvider):
    name = "yahoo"
    native_timeframes = ("1m", "5m", "15m", "30m", "1h", "1d")

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(20.0),
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
                    ),
                    "Accept": "application/json",
                },
            )
        return self._client

    async def fetch(self, symbol: str, timeframe: str, limit: int = 500) -> Series:
        source_tf, factor = self._source_timeframe(timeframe, self.native_timeframes)
        interval = INTERVAL_MAP.get(source_tf, source_tf)
        span = RANGE_FOR_INTERVAL.get(interval, "60d")

        # Genug Historie anfordern, damit nach dem Verdichten noch `limit`
        # Kerzen uebrig bleiben.
        needed = limit * max(1, factor)
        raw = await self._request(symbol, interval, span)

        if len(raw) < needed and interval in ("60m", "1h"):
            raw = await self._request(symbol, interval, "730d")

        series = Series(symbol.upper(), source_tf, raw)
        if factor > 1 or timeframe.lower() != source_tf:
            series = resample(series, timeframe.lower())

        # Letzte Kerze ist bei Yahoo noch unvollstaendig (laufende Periode).
        # Sie bleibt erhalten, wird aber sauber als solche erkennbar gehalten:
        # die Analyse arbeitet bewusst mit dem aktuellen Stand.
        if len(series.candles) > limit:
            series.candles = series.candles[-limit:]
        return series

    async def _request(self, symbol: str, interval: str, span: str) -> list[Candle]:
        client = await self._get_client()
        url = BASE_URL.format(symbol=to_yahoo_symbol(symbol))
        params = {"interval": interval, "range": span, "includePrePost": "false"}

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return self._parse(response.json())
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))
        log.warning("Yahoo-Abruf fuer %s (%s) fehlgeschlagen: %s", symbol, interval, last_error)
        return []

    @staticmethod
    def _parse(payload: dict) -> list[Candle]:
        chart = payload.get("chart") or {}
        results = chart.get("result") or []
        if not results:
            return []
        result = results[0]
        stamps = result.get("timestamp") or []
        quote_list = (result.get("indicators") or {}).get("quote") or [{}]
        quote = quote_list[0] if quote_list else {}

        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []

        candles: list[Candle] = []
        for i, ts in enumerate(stamps):
            try:
                o, h, l, c = opens[i], highs[i], lows[i], closes[i]
            except IndexError:
                continue
            # Yahoo liefert Luecken als null – solche Kerzen werden verworfen.
            if None in (o, h, l, c):
                continue
            volume = 0.0
            if i < len(volumes) and volumes[i] is not None:
                volume = float(volumes[i])
            candles.append(
                Candle(int(ts), float(o), float(h), float(l), float(c), volume)
            )

        candles.sort(key=lambda c: c.ts)
        # Doppelte Zeitstempel entfernen (kommt bei Yahoo gelegentlich vor)
        deduped: list[Candle] = []
        for candle in candles:
            if deduped and deduped[-1].ts == candle.ts:
                deduped[-1] = candle
            else:
                deduped.append(candle)
        return deduped

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
