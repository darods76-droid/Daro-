"""Marktstruktur: Swingpunkte, Zonen, Liquiditaets-Sweeps, Divergenzen."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Candle, Series
from .indicators import Num


@dataclass(slots=True)
class Swing:
    index: int
    price: float
    kind: str  # "high" | "low"


def find_swings(candles: list[Candle], left: int = 2, right: int = 2) -> list[Swing]:
    """Fraktale Swingpunkte.

    Ein Swing-High ist eine Kerze, deren High hoeher ist als das der `left`
    Kerzen davor und der `right` Kerzen danach. Die letzten `right` Kerzen
    koennen naturgemaess noch keinen bestaetigten Swing bilden.
    """
    swings: list[Swing] = []
    for i in range(left, len(candles) - right):
        window = candles[i - left : i + right + 1]
        pivot = candles[i]
        if all(pivot.high >= c.high for c in window) and any(
            pivot.high > c.high for c in window if c is not pivot
        ):
            swings.append(Swing(i, pivot.high, "high"))
        if all(pivot.low <= c.low for c in window) and any(
            pivot.low < c.low for c in window if c is not pivot
        ):
            swings.append(Swing(i, pivot.low, "low"))
    return swings


def recent_swings(swings: list[Swing], kind: str, count: int = 2) -> list[Swing]:
    """Die `count` juengsten Swings einer Art, chronologisch sortiert."""
    filtered = [s for s in swings if s.kind == kind]
    return filtered[-count:]


def market_structure(swings: list[Swing]) -> str:
    """Grobe Struktureinordnung anhand der letzten beiden Hochs und Tiefs."""
    highs = recent_swings(swings, "high", 2)
    lows = recent_swings(swings, "low", 2)
    if len(highs) < 2 or len(lows) < 2:
        return "unklar"
    hh = highs[-1].price > highs[-2].price
    hl = lows[-1].price > lows[-2].price
    lh = highs[-1].price < highs[-2].price
    ll = lows[-1].price < lows[-2].price
    if hh and hl:
        return "aufwaerts"
    if lh and ll:
        return "abwaerts"
    return "seitwaerts"


def liquidity_sweep(series: Series, lookback: int = 30, wick_ratio: float = 0.55) -> dict | None:
    """Erkennt einen Stop-Run ueber ein vorheriges Extrem mit Rueckkehr.

    Typisches Muster vor einer Gegenbewegung: der Kurs nimmt kurz die Liquiditaet
    oberhalb des letzten Hochs (bzw. unterhalb des letzten Tiefs), schliesst aber
    wieder innerhalb der alten Spanne. Der lange Docht zeigt die Ablehnung.
    """
    candles = series.candles
    if len(candles) < lookback + 3:
        return None
    last = candles[-1]
    prior = candles[-1 - lookback : -1]
    if not prior:
        return None
    prior_high = max(c.high for c in prior)
    prior_low = min(c.low for c in prior)
    rng = last.range
    if rng <= 0:
        return None

    upper_wick = last.high - max(last.open, last.close)
    lower_wick = min(last.open, last.close) - last.low

    if last.high > prior_high and last.close < prior_high and upper_wick / rng >= wick_ratio:
        return {
            "direction": "short",
            "level": prior_high,
            "wick_ratio": round(upper_wick / rng, 3),
            "text": "Der Kurs schoss kurz ueber das letzte Hoch und fiel sofort zurueck.",
        }
    if last.low < prior_low and last.close > prior_low and lower_wick / rng >= wick_ratio:
        return {
            "direction": "long",
            "level": prior_low,
            "wick_ratio": round(lower_wick / rng, 3),
            "text": "Der Kurs fiel kurz unter das letzte Tief und sprang sofort zurueck.",
        }
    return None


def divergence(
    candles: list[Candle], oscillator: list[Num], swings: list[Swing], max_age: int = 40
) -> dict | None:
    """Klassische Divergenz zwischen Preis und Oszillator.

    Bearish: hoeheres Hoch im Preis, tieferes Hoch im Oszillator.
    Bullish: tieferes Tief im Preis, hoeheres Tief im Oszillator.
    """
    n = len(candles)

    highs = [s for s in recent_swings(swings, "high", 4) if n - s.index <= max_age]
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        oa, ob = oscillator[a.index], oscillator[b.index]
        if oa is not None and ob is not None and b.price > a.price and ob < oa:
            return {
                "direction": "short",
                "strength": min(1.0, abs(oa - ob) / 12.0),
                "text": "Der Kurs steigt noch, aber mit immer weniger Kraft. "
                        "Oft ein Zeichen fuer eine Wende nach unten.",
            }

    lows = [s for s in recent_swings(swings, "low", 4) if n - s.index <= max_age]
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        oa, ob = oscillator[a.index], oscillator[b.index]
        if oa is not None and ob is not None and b.price < a.price and ob > oa:
            return {
                "direction": "long",
                "strength": min(1.0, abs(ob - oa) / 12.0),
                "text": "Der Kurs faellt noch, aber der Verkaufsdruck laesst nach. "
                        "Oft ein Zeichen fuer eine Wende nach oben.",
            }
    return None


def inside_bars(candles: list[Candle], count: int = 3) -> int:
    """Anzahl aufeinanderfolgender Inside Bars am Ende der Reihe."""
    streak = 0
    for i in range(len(candles) - 1, 0, -1):
        cur, prev = candles[i], candles[i - 1]
        if cur.high <= prev.high and cur.low >= prev.low:
            streak += 1
            if streak >= count * 3:
                break
        else:
            break
    return streak


def narrow_range(candles: list[Candle], lookback: int = 7) -> bool:
    """NR7: Die aktuelle Kerze hat die kleinste Spanne der letzten `lookback` Kerzen."""
    if len(candles) < lookback:
        return False
    window = candles[-lookback:]
    current = window[-1].range
    return all(current <= c.range for c in window[:-1])


def key_levels(series: Series, max_levels: int = 6) -> list[dict]:
    """Verdichtet Swingpunkte zu Unterstuetzungs- und Widerstandszonen.

    Swings, die naeher als eine halbe ATR beieinanderliegen, werden zu einer
    Zone zusammengefasst; je mehr Beruehrungen, desto relevanter.
    """
    candles = series.candles
    if len(candles) < 30:
        return []
    swings = find_swings(candles, 3, 3)
    if not swings:
        return []

    spans = [c.range for c in candles[-100:]]
    tolerance = (sum(spans) / len(spans)) * 1.5 if spans else 0.0
    if tolerance <= 0:
        return []

    clusters: list[dict] = []
    for swing in swings:
        for cluster in clusters:
            if abs(cluster["price"] - swing.price) <= tolerance:
                total = cluster["touches"] + 1
                cluster["price"] = (cluster["price"] * cluster["touches"] + swing.price) / total
                cluster["touches"] = total
                cluster["last_index"] = max(cluster["last_index"], swing.index)
                break
        else:
            clusters.append(
                {"price": swing.price, "touches": 1, "last_index": swing.index, "kind": swing.kind}
            )

    price = candles[-1].close
    for cluster in clusters:
        cluster["kind"] = "widerstand" if cluster["price"] > price else "unterstuetzung"
        cluster["distance_pct"] = abs(cluster["price"] - price) / price * 100.0
        # Relevanz: viele Beruehrungen, aktuell und nah am Kurs
        recency = 1.0 - min(1.0, (len(candles) - cluster["last_index"]) / len(candles))
        proximity = 1.0 / (1.0 + cluster["distance_pct"])
        cluster["score"] = round(cluster["touches"] * (0.5 + 0.5 * recency) * proximity, 3)

    clusters.sort(key=lambda c: c["score"], reverse=True)
    for cluster in clusters:
        cluster["price"] = round(cluster["price"], 6)
        cluster["distance_pct"] = round(cluster["distance_pct"], 3)
    return clusters[:max_levels]
