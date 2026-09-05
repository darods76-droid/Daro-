"""Datenmodelle des Systems."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# --------------------------------------------------------------------------
# Marktdaten
# --------------------------------------------------------------------------


@dataclass(slots=True)
class Candle:
    """Eine einzelne OHLC-Kerze. `ts` ist ein UTC-Unix-Timestamp in Sekunden."""

    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def bullish(self) -> bool:
        return self.close >= self.open

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Series:
    """Eine Kerzenreihe fuer ein Instrument in einem Timeframe."""

    symbol: str
    timeframe: str
    candles: list[Candle] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.candles)

    @property
    def closes(self) -> list[float]:
        return [c.close for c in self.candles]

    @property
    def highs(self) -> list[float]:
        return [c.high for c in self.candles]

    @property
    def lows(self) -> list[float]:
        return [c.low for c in self.candles]

    @property
    def opens(self) -> list[float]:
        return [c.open for c in self.candles]

    @property
    def last(self) -> Candle | None:
        return self.candles[-1] if self.candles else None

    def slice(self, end: int) -> "Series":
        """Kopie mit nur den ersten `end` Kerzen – Basis fuer den Backtest."""
        return Series(self.symbol, self.timeframe, self.candles[:end])


# --------------------------------------------------------------------------
# Analyse-Ergebnisse
# --------------------------------------------------------------------------


@dataclass(slots=True)
class SignalHit:
    """Ein einzelner erkannter Zustand (Baustein eines Setups)."""

    key: str
    label: str
    # Beitrag zur Aufladung des Marktes (0..1) – "wie sehr steht eine Bewegung bevor"
    readiness: float
    # Richtungsbeitrag: -1 (short) .. +1 (long); 0 = richtungsneutral
    direction: float
    weight: float
    detail: str = ""
    category: str = "sonstige"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Levels:
    """Konkrete Preisniveaus fuer die Ausfuehrung."""

    entry: float
    stop: float
    take_profit_1: float
    take_profit_2: float
    trigger_long: float
    trigger_short: float
    atr: float
    rr: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Setup:
    """Das Gesamturteil zu einem Instrument."""

    symbol: str
    timeframe: str
    ts: int
    price: float
    # WATCH  – beobachten, noch nichts zu tun
    # ARMED  – Markt ist aufgeladen, Ausbruch steht bevor (Vor-Bewegung!)
    # TRIGGERED – Ausbruchsniveau wurde soeben genommen
    # COOLDOWN – Bewegung laeuft bereits, Einstieg verpasst/zu spaet
    state: str
    readiness: float
    direction: float
    confidence: float
    bias: str
    hits: list[SignalHit] = field(default_factory=list)
    levels: Levels | None = None
    regime: str = "unbekannt"
    session: str = ""
    notes: list[str] = field(default_factory=list)
    event_risk: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["hits"] = [h.to_dict() for h in self.hits]
        data["levels"] = self.levels.to_dict() if self.levels else None
        return data


@dataclass(slots=True)
class Alert:
    """Eine ausgeloeste Benachrichtigung."""

    ts: int
    symbol: str
    timeframe: str
    state: str
    bias: str
    readiness: float
    message: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
