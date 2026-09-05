"""Synthetischer Provider fuer Tests und den Offline-Betrieb.

Erzeugt reproduzierbare Kursverlaeufe mit realistischen Eigenschaften:
Trendphasen, Volatilitaetsclusterung und eingebaute Kompressionsphasen mit
anschliessendem Ausbruch. Dadurch laesst sich die Signallogik ohne
Netzzugang pruefen.
"""

from __future__ import annotations

import math
import random
import time

from ..models import Candle, Series
from .base import DataProvider, timeframe_seconds

BASE_PRICES = {
    "EURUSD": 1.0850, "GBPUSD": 1.2700, "USDJPY": 151.20, "USDCHF": 0.8900,
    "AUDUSD": 0.6600, "USDCAD": 1.3600, "NZDUSD": 0.6100, "EURJPY": 164.00,
    "EURGBP": 0.8540, "GBPJPY": 192.00, "XAUUSD": 2320.0, "DXY": 104.5,
}


class SyntheticProvider(DataProvider):
    name = "synthetic"
    native_timeframes = ("1m", "5m", "15m", "30m", "1h", "4h", "1d")

    def __init__(self, seed: int | None = None) -> None:
        self._seed = seed

    async def fetch(self, symbol: str, timeframe: str, limit: int = 500) -> Series:
        symbol = symbol.upper()
        rng = random.Random(self._seed if self._seed is not None else hash((symbol, timeframe)) & 0xFFFF)
        step = timeframe_seconds(timeframe)
        now = int(time.time()) // step * step
        base = BASE_PRICES.get(symbol, 1.2000)
        price = base

        candles: list[Candle] = []
        drift = 0.0
        vol = 1.0
        for i in range(limit):
            # Trend wechselt langsam und bleibt beschraenkt, damit der Kurs
            # nicht davonlaeuft; Volatilitaet clustert wie am echten Markt.
            if i % 60 == 0:
                drift = max(-1.0, min(1.0, drift * 0.5 + rng.gauss(0, 0.35)))
            vol = max(0.25, min(3.0, vol * 0.94 + rng.random() * 0.4))

            # Alle ~120 Kerzen eine Kompression mit anschliessendem Ausbruch,
            # damit die Squeeze-Erkennung etwas zu finden hat.
            phase = i % 120
            breakout = 0.0
            if 80 <= phase < 108:
                vol *= 0.35
            elif 108 <= phase < 118:
                vol *= 2.4
                breakout = 0.8 if (i // 120) % 2 == 0 else -0.8

            # Multiplikative Rendite haelt den Kurs strikt positiv.
            ret = (drift * 0.15 + breakout * 0.4 + rng.gauss(0, 1.0)) * 0.0006 * vol
            # Sanfte Rueckkehr zum Ausgangsniveau verhindert Wegdriften
            ret += (math.log(base / price)) * 0.002

            open_ = price
            close = price * math.exp(ret)
            span = price * 0.0006 * vol
            high = max(open_, close) + abs(rng.gauss(0, 0.7)) * span
            low = min(open_, close) - abs(rng.gauss(0, 0.7)) * span
            price = close
            candles.append(
                Candle(
                    ts=now - (limit - 1 - i) * step,
                    open=round(open_, 6),
                    high=round(high, 6),
                    low=round(low, 6),
                    close=round(close, 6),
                    volume=round(abs(rng.gauss(1000, 300)) * (1 + vol), 1),
                )
            )
        return Series(symbol, timeframe.lower(), candles)
