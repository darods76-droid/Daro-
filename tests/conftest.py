"""Gemeinsame Testbausteine."""

from __future__ import annotations

import math
import random

import pytest

from forexwatch.models import Candle, Series


def make_series(
    n: int = 300,
    start: float = 1.1000,
    seed: int = 42,
    vol: float = 0.0012,
    drift: float = 0.0,
    step: int = 3600,
) -> Series:
    """Zufaellige, aber reproduzierbare Kerzenreihe mit gueltigem OHLC."""
    rng = random.Random(seed)
    price = start
    candles: list[Candle] = []
    for i in range(n):
        open_ = price
        price = price * math.exp(rng.gauss(drift, vol))
        high = max(open_, price) * (1 + abs(rng.gauss(0, vol * 0.5)))
        low = min(open_, price) * (1 - abs(rng.gauss(0, vol * 0.5)))
        candles.append(Candle(i * step, open_, high, low, price, 100.0))
    return Series("EURUSD", "1h", candles)


def make_squeeze_series(n: int = 260) -> Series:
    """Reihe mit ausgepraegter Kompression am Ende – fuer die Squeeze-Tests."""
    candles: list[Candle] = []
    price = 1.1000
    for i in range(n):
        # Erste Haelfte bewegt, zweite Haelfte sehr ruhig
        amplitude = 0.004 if i < n - 60 else 0.00012
        price = 1.1000 + math.sin(i / 7.0) * amplitude
        open_ = 1.1000 + math.sin((i - 1) / 7.0) * amplitude
        high = max(open_, price) + amplitude * 0.15
        low = min(open_, price) - amplitude * 0.15
        candles.append(Candle(i * 3600, open_, high, low, price, 100.0))
    return Series("EURUSD", "1h", candles)


@pytest.fixture
def series() -> Series:
    return make_series()


@pytest.fixture
def squeeze_series() -> Series:
    return make_squeeze_series()
