"""Vorberechnung aller Indikatoren fuer eine Kerzenreihe.

Die Signalerkennung greift ausschliesslich auf ein ``Features``-Objekt zu.
Dadurch wird jeder Indikator pro Timeframe genau einmal berechnet – wichtig,
weil der Backtest dieselbe Logik einige tausend Mal durchlaeuft.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Series
from . import indicators as ind
from .structure import Swing, find_swings, market_structure


@dataclass(slots=True)
class Features:
    series: Series
    closes: list[float] = field(default_factory=list)
    highs: list[float] = field(default_factory=list)
    lows: list[float] = field(default_factory=list)

    ema20: list[ind.Num] = field(default_factory=list)
    ema50: list[ind.Num] = field(default_factory=list)
    ema200: list[ind.Num] = field(default_factory=list)
    rsi14: list[ind.Num] = field(default_factory=list)
    atr14: list[ind.Num] = field(default_factory=list)

    bb_upper: list[ind.Num] = field(default_factory=list)
    bb_mid: list[ind.Num] = field(default_factory=list)
    bb_lower: list[ind.Num] = field(default_factory=list)
    kc_upper: list[ind.Num] = field(default_factory=list)
    kc_mid: list[ind.Num] = field(default_factory=list)
    kc_lower: list[ind.Num] = field(default_factory=list)

    dc_upper: list[ind.Num] = field(default_factory=list)
    dc_lower: list[ind.Num] = field(default_factory=list)

    macd_line: list[ind.Num] = field(default_factory=list)
    macd_signal: list[ind.Num] = field(default_factory=list)
    macd_hist: list[ind.Num] = field(default_factory=list)

    adx: list[ind.Num] = field(default_factory=list)
    plus_di: list[ind.Num] = field(default_factory=list)
    minus_di: list[ind.Num] = field(default_factory=list)

    stoch_k: list[ind.Num] = field(default_factory=list)
    stoch_d: list[ind.Num] = field(default_factory=list)

    bb_width: list[ind.Num] = field(default_factory=list)
    squeeze_on: list[bool] = field(default_factory=list)
    swings: list[Swing] = field(default_factory=list)
    structure: str = "unklar"

    # -- bequeme Zugriffe auf den aktuellen Rand ---------------------------

    @property
    def price(self) -> float:
        return self.closes[-1] if self.closes else 0.0

    @property
    def atr_now(self) -> float:
        value = ind.last_valid(self.atr14)
        return value if value else 0.0

    def __len__(self) -> int:
        return len(self.closes)


def build_features(series: Series) -> Features:
    """Alle Indikatoren einer Reihe in einem Durchgang berechnen."""
    closes, highs, lows = series.closes, series.highs, series.lows
    f = Features(series=series, closes=closes, highs=highs, lows=lows)
    if len(closes) < 30:
        return f

    f.ema20 = ind.ema(closes, 20)
    f.ema50 = ind.ema(closes, 50)
    f.ema200 = ind.ema(closes, 200)
    f.rsi14 = ind.rsi(closes, 14)
    f.atr14 = ind.atr(highs, lows, closes, 14)

    f.bb_upper, f.bb_mid, f.bb_lower = ind.bollinger(closes, 20, 2.0)
    f.kc_upper, f.kc_mid, f.kc_lower = ind.keltner(highs, lows, closes, 20, 1.5)
    f.dc_upper, f.dc_lower = ind.donchian(highs, lows, 20)

    f.macd_line, f.macd_signal, f.macd_hist = ind.macd(closes)
    f.adx, f.plus_di, f.minus_di = ind.adx(highs, lows, closes, 14)
    f.stoch_k, f.stoch_d = ind.stochastic(highs, lows, closes, 14, 3)

    # Bandbreite der Bollinger-Baender, normiert auf den Preis -> vergleichbar
    f.bb_width = [
        ((u - l) / m * 100.0) if (u is not None and l is not None and m) else None
        for u, m, l in zip(f.bb_upper, f.bb_mid, f.bb_lower)
    ]

    # Squeeze nach Bollinger/Keltner: liegen die Bollinger-Baender komplett
    # innerhalb des Keltner-Kanals, ist die Volatilitaet aussergewoehnlich
    # niedrig – der klassische Zustand *vor* einer Ausdehnung.
    f.squeeze_on = [
        bool(
            bu is not None and bl is not None and ku is not None and kl is not None
            and bu < ku and bl > kl
        )
        for bu, bl, ku, kl in zip(f.bb_upper, f.bb_lower, f.kc_upper, f.kc_lower)
    ]

    f.swings = find_swings(series.candles, 2, 2)
    f.structure = market_structure(f.swings)
    return f


def squeeze_length(f: Features) -> int:
    """Wie viele Kerzen liegt der Squeeze bereits an? (0 = kein Squeeze)"""
    count = 0
    for flag in reversed(f.squeeze_on):
        if flag:
            count += 1
        else:
            break
    return count


def squeeze_just_released(f: Features, within: int = 2) -> bool:
    """Wurde ein laengerer Squeeze in den letzten `within` Kerzen aufgeloest?"""
    if len(f.squeeze_on) < 10 + within:
        return False
    recent = f.squeeze_on[-within:]
    before = f.squeeze_on[-(within + 6) : -within]
    return not any(recent) and sum(before) >= 4
