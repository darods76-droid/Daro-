"""Technische Indikatoren in reinem Python.

Alle Funktionen geben Listen zurueck, die exakt so lang sind wie die Eingabe.
Positionen ohne gueltigen Wert enthalten ``None``. Dadurch bleibt der Index
einer Kerze ueber alle Indikatoren hinweg identisch, was den Backtest
erheblich vereinfacht.
"""

from __future__ import annotations

import math

Num = float | None


# --------------------------------------------------------------------------
# Gleitende Durchschnitte
# --------------------------------------------------------------------------


def sma(values: list[float], period: int) -> list[Num]:
    """Einfacher gleitender Durchschnitt."""
    out: list[Num] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    total = sum(values[:period])
    out[period - 1] = total / period
    for i in range(period, len(values)):
        total += values[i] - values[i - period]
        out[i] = total / period
    return out


def ema(values: list[float], period: int) -> list[Num]:
    """Exponentiell gewichteter Durchschnitt, initialisiert mit dem SMA."""
    out: list[Num] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    k = 2.0 / (period + 1.0)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1.0 - k)
        out[i] = prev
    return out


def rma(values: list[float], period: int) -> list[Num]:
    """Wilder-Glaettung (wird von RSI, ATR und ADX verwendet)."""
    out: list[Num] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = (prev * (period - 1) + values[i]) / period
        out[i] = prev
    return out


def stdev(values: list[float], period: int) -> list[Num]:
    """Rollende Standardabweichung (Population)."""
    out: list[Num] = [None] * len(values)
    if period <= 1 or len(values) < period:
        return out
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        mean = sum(window) / period
        var = sum((v - mean) ** 2 for v in window) / period
        out[i] = math.sqrt(var)
    return out


# --------------------------------------------------------------------------
# Volatilitaet
# --------------------------------------------------------------------------


def true_range(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
    """True Range je Kerze. Die erste Kerze nutzt schlicht High-Low."""
    out: list[float] = []
    for i in range(len(closes)):
        if i == 0:
            out.append(highs[i] - lows[i])
        else:
            prev = closes[i - 1]
            out.append(max(highs[i] - lows[i], abs(highs[i] - prev), abs(lows[i] - prev)))
    return out


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[Num]:
    """Average True Range nach Wilder."""
    return rma(true_range(highs, lows, closes), period)


def bollinger(
    values: list[float], period: int = 20, mult: float = 2.0
) -> tuple[list[Num], list[Num], list[Num]]:
    """Bollinger-Baender -> (oberes Band, Mittellinie, unteres Band)."""
    mid = sma(values, period)
    sd = stdev(values, period)
    upper: list[Num] = [None] * len(values)
    lower: list[Num] = [None] * len(values)
    for i in range(len(values)):
        if mid[i] is not None and sd[i] is not None:
            upper[i] = mid[i] + mult * sd[i]
            lower[i] = mid[i] - mult * sd[i]
    return upper, mid, lower


def keltner(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 20,
    mult: float = 1.5,
) -> tuple[list[Num], list[Num], list[Num]]:
    """Keltner-Kanal auf EMA-Basis -> (oben, Mitte, unten)."""
    mid = ema(closes, period)
    rng = atr(highs, lows, closes, period)
    upper: list[Num] = [None] * len(closes)
    lower: list[Num] = [None] * len(closes)
    for i in range(len(closes)):
        if mid[i] is not None and rng[i] is not None:
            upper[i] = mid[i] + mult * rng[i]
            lower[i] = mid[i] - mult * rng[i]
    return upper, mid, lower


def donchian(
    highs: list[float], lows: list[float], period: int = 20
) -> tuple[list[Num], list[Num]]:
    """Donchian-Kanal -> (hoechstes High, tiefstes Low) der letzten `period` Kerzen."""
    up: list[Num] = [None] * len(highs)
    dn: list[Num] = [None] * len(lows)
    for i in range(period - 1, len(highs)):
        up[i] = max(highs[i - period + 1 : i + 1])
        dn[i] = min(lows[i - period + 1 : i + 1])
    return up, dn


# --------------------------------------------------------------------------
# Momentum
# --------------------------------------------------------------------------


def rsi(values: list[float], period: int = 14) -> list[Num]:
    """Relative Strength Index nach Wilder."""
    out: list[Num] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = rma(gains[1:], period)
    avg_loss = rma(losses[1:], period)
    for i, (g, l) in enumerate(zip(avg_gain, avg_loss), start=1):
        if g is None or l is None:
            continue
        if l == 0:
            out[i] = 100.0
        else:
            rs = g / l
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def macd(
    values: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[Num], list[Num], list[Num]]:
    """MACD -> (Linie, Signal, Histogramm)."""
    fast_e = ema(values, fast)
    slow_e = ema(values, slow)
    line: list[Num] = [
        (f - s) if (f is not None and s is not None) else None for f, s in zip(fast_e, slow_e)
    ]
    valid = [v for v in line if v is not None]
    sig_valid = ema(valid, signal)
    sig: list[Num] = [None] * len(values)
    offset = len(line) - len(valid)
    for i, v in enumerate(sig_valid):
        sig[offset + i] = v
    hist: list[Num] = [
        (l - s) if (l is not None and s is not None) else None for l, s in zip(line, sig)
    ]
    return line, sig, hist


def stochastic(
    highs: list[float], lows: list[float], closes: list[float], k_period: int = 14, d_period: int = 3
) -> tuple[list[Num], list[Num]]:
    """Stochastik -> (%K, %D)."""
    k: list[Num] = [None] * len(closes)
    for i in range(k_period - 1, len(closes)):
        hh = max(highs[i - k_period + 1 : i + 1])
        ll = min(lows[i - k_period + 1 : i + 1])
        k[i] = 50.0 if hh == ll else (closes[i] - ll) / (hh - ll) * 100.0
    valid = [v for v in k if v is not None]
    d_valid = sma(valid, d_period)
    d: list[Num] = [None] * len(closes)
    offset = len(k) - len(valid)
    for i, v in enumerate(d_valid):
        d[offset + i] = v
    return k, d


def adx(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> tuple[list[Num], list[Num], list[Num]]:
    """ADX -> (ADX, +DI, -DI). Misst Trendstaerke, nicht Trendrichtung."""
    n = len(closes)
    empty: list[Num] = [None] * n
    if n < period * 2:
        return empty, list(empty), list(empty)

    plus_dm, minus_dm = [], []
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)

    tr = true_range(highs, lows, closes)[1:]
    tr_s = rma(tr, period)
    plus_s = rma(plus_dm, period)
    minus_s = rma(minus_dm, period)

    plus_di: list[Num] = [None] * n
    minus_di: list[Num] = [None] * n
    dx_vals: list[float] = []
    dx_index: list[int] = []
    for i in range(len(tr_s)):
        if tr_s[i] is None or plus_s[i] is None or minus_s[i] is None or tr_s[i] == 0:
            continue
        pdi = 100.0 * plus_s[i] / tr_s[i]
        mdi = 100.0 * minus_s[i] / tr_s[i]
        plus_di[i + 1] = pdi
        minus_di[i + 1] = mdi
        denom = pdi + mdi
        if denom > 0:
            dx_vals.append(100.0 * abs(pdi - mdi) / denom)
            dx_index.append(i + 1)

    adx_out: list[Num] = [None] * n
    smoothed = rma(dx_vals, period)
    for pos, value in enumerate(smoothed):
        if value is not None:
            adx_out[dx_index[pos]] = value
    return adx_out, plus_di, minus_di


# --------------------------------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------------------------------


def percentile_rank(window: list[float], value: float) -> float:
    """Perzentilrang von `value` innerhalb von `window` (0..100)."""
    if not window:
        return 50.0
    below = sum(1 for v in window if v < value)
    equal = sum(1 for v in window if v == value)
    return (below + 0.5 * equal) / len(window) * 100.0


def linreg_slope(values: list[float]) -> float:
    """Steigung der Regressionsgeraden, normiert auf den Mittelwert (in %/Kerze)."""
    n = len(values)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(values) / n
    num = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values))
    den = sum((i - mean_x) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    slope = num / den
    return (slope / mean_y * 100.0) if mean_y else 0.0


def pearson(a: list[float], b: list[float]) -> float:
    """Pearson-Korrelation zweier gleich langer Reihen (-1..1)."""
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    if da == 0 or db == 0:
        return 0.0
    return max(-1.0, min(1.0, num / (da * db)))


def returns(values: list[float]) -> list[float]:
    """Prozentuale Veraenderung von Kerze zu Kerze."""
    out = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        out.append(((values[i] - prev) / prev * 100.0) if prev else 0.0)
    return out


def last_valid(values: list[Num], offset: int = 0) -> float | None:
    """Letzter (bzw. `offset` Positionen davor liegender) nicht-``None``-Wert."""
    skipped = 0
    for value in reversed(values):
        if value is None:
            continue
        if skipped == offset:
            return value
        skipped += 1
    return None
