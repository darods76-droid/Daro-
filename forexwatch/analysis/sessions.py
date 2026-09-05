"""Handelssessions und ihre Bedeutung fuer die Volatilitaet.

Der Devisenmarkt hat einen sehr stabilen Tagesrhythmus. Die Ueberschneidung
London/New York traegt den Grossteil des Tagesvolumens, waehrend die
Asien-Session meist eine enge Spanne bildet. Genau diese Spanne wird beim
London-Open ueberdurchschnittlich oft gebrochen – der wichtigste planbare
Zeitpunkt fuer eine bevorstehende Bewegung.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import Candle

# Name -> (Start-Stunde UTC, End-Stunde UTC, Volatilitaetsfaktor)
SESSIONS: dict[str, tuple[int, int, float]] = {
    "Sydney": (21, 6, 0.55),
    "Tokio": (0, 9, 0.70),
    "London": (7, 16, 1.35),
    "New York": (12, 21, 1.25),
}

# Zeitpunkte, an denen erfahrungsgemaess Bewegung entsteht (Stunde, Minute) UTC
KEY_MOMENTS: list[tuple[str, int, int]] = [
    ("Tokio-Open", 0, 0),
    ("Frankfurt-Open", 6, 0),
    ("London-Open", 7, 0),
    ("London-Fixing", 15, 0),
    ("New-York-Open", 12, 0),
    ("US-Datenfenster", 13, 30),
    ("London-Close", 16, 0),
]


def _in_window(hour: int, start: int, end: int) -> bool:
    """Auch ueber Mitternacht laufende Fenster korrekt pruefen."""
    return start <= hour < end if start < end else (hour >= start or hour < end)


def active_sessions(now: datetime | None = None) -> list[str]:
    """Alle aktuell geoeffneten Sessions."""
    now = now or datetime.now(timezone.utc)
    return [name for name, (s, e, _) in SESSIONS.items() if _in_window(now.hour, s, e)]


def is_weekend(now: datetime | None = None) -> bool:
    """Der FX-Markt ruht von Freitag 21:00 UTC bis Sonntag 21:00 UTC."""
    now = now or datetime.now(timezone.utc)
    if now.weekday() == 5:  # Samstag
        return True
    if now.weekday() == 4 and now.hour >= 21:  # Freitagabend
        return True
    if now.weekday() == 6 and now.hour < 21:  # Sonntag vor Eroeffnung
        return True
    return False


def session_volatility_factor(now: datetime | None = None) -> float:
    """Erwartete Volatilitaet relativ zum Tagesdurchschnitt (1.0 = normal)."""
    now = now or datetime.now(timezone.utc)
    if is_weekend(now):
        return 0.0
    active = [SESSIONS[name][2] for name in active_sessions(now)]
    if not active:
        return 0.4
    # Ueberschneidungen addieren sich abgeschwaecht statt linear
    base = max(active)
    extra = sum(sorted(active, reverse=True)[1:]) * 0.35
    return round(base + extra, 3)


def next_key_moment(now: datetime | None = None) -> tuple[str, int]:
    """Naechster markanter Zeitpunkt -> (Name, Minuten bis dahin)."""
    now = now or datetime.now(timezone.utc)
    best: tuple[str, int] | None = None
    for name, hour, minute in KEY_MOMENTS:
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        minutes = int((target - now).total_seconds() // 60)
        if best is None or minutes < best[1]:
            best = (name, minutes)
    return best or ("-", 0)


def session_label(now: datetime | None = None) -> str:
    """Kurzbeschreibung der aktuellen Marktphase."""
    now = now or datetime.now(timezone.utc)
    if is_weekend(now):
        return "Markt geschlossen (Wochenende)"
    active = active_sessions(now)
    if not active:
        return "Zwischen den Sessions (duenne Liquiditaet)"
    if "London" in active and "New York" in active:
        return "London/New York Ueberschneidung – hoechste Liquiditaet"
    return " + ".join(active)


def asian_range(candles: list[Candle], now: datetime | None = None) -> dict | None:
    """Hoch und Tief der letzten Asien-Session (00:00-07:00 UTC).

    Eine ungewoehnlich enge Asien-Spanne ist einer der zuverlaessigsten
    Hinweise darauf, dass beim London-Open eine Ausdehnung folgt.

    Die Funktion laeuft im Backtest einige tausend Mal, deshalb arbeitet sie
    ausschliesslich auf ganzzahligen Zeitstempeln und in einem einzigen
    Durchlauf ueber die Kerzen.
    """
    if not candles:
        return None
    now = now or datetime.now(timezone.utc)

    # Referenztag bestimmen: vor 07:00 UTC laeuft die Session noch.
    day = now.date() if now.hour >= 7 else (now - timedelta(days=1)).date()
    start = int(datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    if now.hour < 7:
        start = int(
            datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc).timestamp()
        )
        end = int(now.timestamp())
    else:
        end = start + 7 * 3600

    high = low = None
    count = 0
    # Vergleichsspannen der 20 Tage davor, in einem Rutsch mitgezaehlt.
    day_high: dict[int, float] = {}
    day_low: dict[int, float] = {}
    window_start = start - 20 * 86400

    for candle in candles:
        ts = candle.ts
        if start <= ts < end:
            count += 1
            high = candle.high if high is None else max(high, candle.high)
            low = candle.low if low is None else min(low, candle.low)
        elif window_start <= ts < start:
            bucket = (ts - window_start) // 86400
            if bucket in day_high:
                if candle.high > day_high[bucket]:
                    day_high[bucket] = candle.high
                if candle.low < day_low[bucket]:
                    day_low[bucket] = candle.low
            else:
                day_high[bucket] = candle.high
                day_low[bucket] = candle.low

    if count < 3 or high is None or low is None or high <= low:
        return None

    daily_spans = [day_high[b] - day_low[b] for b in day_high]
    span = high - low
    ratio = (span / (sum(daily_spans) / len(daily_spans))) if daily_spans else None
    return {
        "high": round(high, 6),
        "low": round(low, 6),
        "span": round(span, 6),
        "span_pct": round(span / low * 100.0, 4),
        "ratio_to_daily": round(ratio, 3) if ratio is not None else None,
        "compressed": bool(ratio is not None and ratio < 0.45),
        "candles": count,
    }


def minutes_to_session_open(name: str, now: datetime | None = None) -> int:
    """Minuten bis zur naechsten Eroeffnung der genannten Session."""
    now = now or datetime.now(timezone.utc)
    start_hour = SESSIONS.get(name, (7, 16, 1.0))[0]
    target = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return int((target - now).total_seconds() // 60)
