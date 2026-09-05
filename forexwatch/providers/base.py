"""Gemeinsame Basis aller Marktdatenquellen."""

from __future__ import annotations

import abc

from ..models import Candle, Series

# Timeframe -> Dauer in Sekunden
TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}


def timeframe_seconds(timeframe: str) -> int:
    return TIMEFRAME_SECONDS.get(timeframe.lower(), 3600)


def resample(series: Series, target: str) -> Series:
    """Kerzen auf einen groesseren Timeframe verdichten.

    Wird gebraucht, weil viele kostenlose Quellen z. B. kein 4h-Intervall
    anbieten. Die Buckets richten sich am UTC-Raster aus, damit die 4h-Kerzen
    reproduzierbar auf 00/04/08/12/16/20 Uhr fallen.
    """
    step = timeframe_seconds(target)
    buckets: dict[int, list[Candle]] = {}
    for candle in series.candles:
        bucket = candle.ts - (candle.ts % step)
        buckets.setdefault(bucket, []).append(candle)

    merged: list[Candle] = []
    for bucket in sorted(buckets):
        group = buckets[bucket]
        merged.append(
            Candle(
                ts=bucket,
                open=group[0].open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=group[-1].close,
                volume=sum(c.volume for c in group),
            )
        )
    return Series(series.symbol, target, merged)


class DataProvider(abc.ABC):
    """Schnittstelle, die jede Datenquelle erfuellen muss."""

    name: str = "base"
    #: Timeframes, die die Quelle direkt liefert. Alles andere wird resampled.
    native_timeframes: tuple[str, ...] = ()

    @abc.abstractmethod
    async def fetch(self, symbol: str, timeframe: str, limit: int = 500) -> Series:
        """Kerzen fuer ein Instrument laden (aelteste zuerst)."""

    async def close(self) -> None:  # pragma: no cover - optionaler Aufraeumhaken
        return None

    # -- Hilfen fuer Unterklassen -----------------------------------------

    @staticmethod
    def _source_timeframe(target: str, native: tuple[str, ...]) -> tuple[str, int]:
        """Passenden nativen Timeframe und den noetigen Faktor bestimmen."""
        target = target.lower()
        if target in native:
            return target, 1
        want = timeframe_seconds(target)
        candidates = [
            (tf, want // timeframe_seconds(tf))
            for tf in native
            if timeframe_seconds(tf) < want and want % timeframe_seconds(tf) == 0
        ]
        if not candidates:
            return (native[0] if native else "1h"), 1
        # Den groessten passenden Teiler nehmen -> kleinste Datenmenge
        tf, factor = max(candidates, key=lambda item: timeframe_seconds(item[0]))
        return tf, factor
