"""Verdichtung der Einzelsignale zu einem handelbaren Urteil.

Aus den ``SignalHit``s entsteht hier ein ``Setup`` mit drei Kennzahlen und
einem Zustand:

``readiness``  0..100  Wie aufgeladen ist der Markt? (Bewegung steht bevor)
``direction`` -100..100 Wohin zeigen die Hinweise?
``confidence`` 0..100  Wie einig sind sich die Signale?

Der Zustand ist die eigentliche Handlungsanweisung:

WATCH      – nur beobachten
ARMED      – aufgeladen, Ausbruch steht bevor  → **das ist der Vorlauf**
TRIGGERED  – Ausbruch laeuft gerade an
COOLDOWN   – Bewegung ist bereits gelaufen, Einstieg zu spaet
GESCHLOSSEN– Markt ruht (Wochenende)
"""

from __future__ import annotations

import math

from ..config import settings
from ..models import Setup, SignalHit
from ..risk import build_levels
from . import indicators as ind
from . import sessions
from .signals import MarketContext, detect_all

# Saettigungskonstante: bestimmt, ab welcher gewichteten Summe die
# Bereitschaft gegen 100 laeuft. Bei 6.0 ergeben ~6 Punkte rund 63,
# ~10 Punkte rund 81.
SATURATION = 6.0

STATE_WATCH = "WATCH"
STATE_ARMED = "ARMED"
STATE_TRIGGERED = "TRIGGERED"
STATE_COOLDOWN = "COOLDOWN"
STATE_CLOSED = "GESCHLOSSEN"


def _readiness_score(hits: list[SignalHit]) -> float:
    """Gewichtete Summe mit Saettigung – begrenzt auf 0..100."""
    raw = sum(h.readiness * h.weight for h in hits)
    return round(100.0 * (1.0 - math.exp(-raw / SATURATION)), 1)


def _direction_score(hits: list[SignalHit]) -> float:
    """Gewichteter Mittelwert der Richtungshinweise, -100..100."""
    directional = [h for h in hits if abs(h.direction) > 0.01]
    if not directional:
        return 0.0
    total_weight = sum(h.weight for h in directional)
    if total_weight <= 0:
        return 0.0
    value = sum(h.direction * h.weight for h in directional) / total_weight
    return round(max(-100.0, min(100.0, value * 100.0)), 1)


def _confidence_score(hits: list[SignalHit], direction: float) -> float:
    """Wie belastbar ist das Urteil?

    Drei Faktoren: Einigkeit der Richtungssignale, Breite der Abdeckung
    (wie viele verschiedene Kategorien melden sich) und die Anzahl der
    Treffer insgesamt.
    """
    if not hits:
        return 0.0

    directional = [h for h in hits if abs(h.direction) > 0.01]
    if directional:
        sign = 1.0 if direction >= 0 else -1.0
        aligned = sum(h.weight for h in directional if (h.direction > 0) == (sign > 0))
        agreement = aligned / sum(h.weight for h in directional)
    else:
        agreement = 0.4  # richtungsneutrale Aufladung: Ausbruch beidseitig moeglich

    categories = {h.category for h in hits}
    breadth = min(1.0, len(categories) / 4.0)
    depth = min(1.0, len(hits) / 6.0)

    score = (agreement * 0.5 + breadth * 0.3 + depth * 0.2) * 100.0
    return round(max(0.0, min(100.0, score)), 1)


# Der Tacho laeuft von 1 bis 100. Die Grenzen sind bewusst grob: eine
# feinere Abstufung wuerde eine Genauigkeit vortaeuschen, die die
# Richtungsprognose nicht hat.
# Symmetrisch um die Mitte: 20 liegt noch bei "Eher verkaufen", 80 bei
# "Eher kaufen". Erst darunter bzw. darueber wird es deutlich.
ACTION_BANDS: tuple[tuple[int, str], ...] = (
    (19, "Verkaufen"),
    (40, "Eher verkaufen"),
    (60, "Abwarten"),
    (81, "Eher kaufen"),
    (100, "Kaufen"),
)


def tacho_score(direction: float, confidence: float) -> int:
    """Richtung und Einigkeit zu einer Zahl von 1 bis 100 verrechnen.

    Die Einigkeit der Einzelsignale zieht den Zeiger zur Mitte: eine klare
    Richtung, auf die sich kaum ein Signal einigt, darf nicht denselben
    Ausschlag erzeugen wie eine, hinter der alles steht.
    """
    weight = 0.4 + 0.6 * max(0.0, min(100.0, confidence)) / 100.0
    value = 50.0 + (direction / 2.0) * weight
    return int(max(1, min(100, round(value))))


def action_for(score: int) -> str:
    """Handlungsempfehlung in Klartext."""
    for limit, label in ACTION_BANDS:
        if score <= limit:
            return label
    return "Abwarten"


def tension_for(state: str, readiness: float) -> str:
    """Wie stark sich eine Bewegung aufbaut – in Worten statt in Zahlen."""
    if state == STATE_CLOSED:
        return "Markt geschlossen"
    if state == STATE_TRIGGERED:
        return "Bewegung laeuft"
    if state == STATE_COOLDOWN:
        return "Bewegung vorbei"
    if readiness >= settings.arm_threshold:
        return "Hohe Spannung"
    if readiness >= 45:
        return "Es baut sich etwas auf"
    return "Ruhig"


def headline_for(symbol: str, state: str, action: str, tension: str) -> str:
    """Ein Satz, der Richtung und Spannung zusammen erklaert.

    Beides muss gemeinsam erzaehlt werden. Ein Tacho auf "Kaufen" waehrend
    am Markt nichts passiert, ist keine Kaufaufforderung, sondern nur die
    Feststellung, dass der Trend nach oben zeigt. Wuerde die Ueberschrift
    nur den Zustand nennen, staende sie im Widerspruch zum Zeiger.
    """
    richtung = {
        "Kaufen": "nach oben",
        "Eher kaufen": "eher nach oben",
        "Eher verkaufen": "eher nach unten",
        "Verkaufen": "nach unten",
    }.get(action, "")

    if state == STATE_CLOSED:
        return f"{symbol}: Der Markt ist geschlossen. Die Anzeige stammt vom letzten Handelstag."

    if state == STATE_TRIGGERED:
        if richtung:
            return f"{symbol}: Die Bewegung {richtung} hat begonnen. Fuer einen Einstieg ist es meist schon spaet."
        return f"{symbol}: Die Bewegung hat begonnen. Fuer einen Einstieg ist es meist schon spaet."

    if state == STATE_COOLDOWN:
        return f"{symbol}: Der Schub ist gelaufen. Auf einen Ruecksetzer warten."

    if state == STATE_ARMED:
        if not richtung:
            return (
                f"{symbol}: Es baut sich eine Bewegung auf, die Richtung ist aber offen. "
                f"Beide Ausbruchsmarken im Blick behalten."
            )
        return f"{symbol}: Eine Bewegung steht bevor, und zwar {richtung}."

    # Ruhige Lage – hier darf der Zeiger nicht als Handlungsaufforderung
    # missverstanden werden.
    if tension == "Es baut sich etwas auf":
        if richtung:
            return f"{symbol}: Der Markt wird ruhiger, der Trend zeigt {richtung}. Noch abwarten."
        return f"{symbol}: Der Markt wird ruhiger. Noch nichts zu tun, aber im Auge behalten."

    if richtung:
        return f"{symbol}: Der Trend zeigt {richtung}, im Moment passiert aber wenig. Kein Grund zur Eile."
    return f"{symbol}: Nichts Auffaelliges. Nur beobachten."


def _bias(direction: float) -> str:
    if direction >= 20.0:
        return "long"
    if direction <= -20.0:
        return "short"
    return "neutral"


def _triggers(ctx: MarketContext) -> tuple[float, float]:
    """Die beiden Ausbruchsmarken bestimmen.

    Bevorzugt wird die engere Zone aus Donchian-Kanal und Asien-Spanne –
    sie wird zuerst erreicht und definiert damit den echten Ausloeser.
    """
    f = ctx.exec_f
    high = ind.last_valid(f.dc_upper) or max(f.highs[-20:], default=f.price)
    low = ind.last_valid(f.dc_lower) or min(f.lows[-20:], default=f.price)

    asia = sessions.asian_range(f.series.candles, ctx.now)
    if asia and asia["high"] > asia["low"]:
        # Nur uebernehmen, wenn die Nachtspanne den Kurs tatsaechlich einschliesst
        if asia["low"] <= f.price <= asia["high"]:
            high = min(high, asia["high"])
            low = max(low, asia["low"])

    if high <= low:
        pad = f.atr_now or f.price * 0.0006
        high, low = f.price + pad, f.price - pad
    return high, low


def _already_moved(ctx: MarketContext) -> tuple[bool, str]:
    """Ist die Bewegung bereits gelaufen? Dann waere ein Einstieg zu spaet."""
    f = ctx.exec_f
    atr = f.atr_now
    if not atr or len(f.closes) < 5:
        return False, ""
    move = abs(f.closes[-1] - f.closes[-4]) / atr
    if move >= 2.5:
        return True, f"Kurs hat in 3 Kerzen bereits {move:.1f} ATR zurueckgelegt"
    last = f.series.candles[-1]
    if last.range >= atr * 2.2:
        return True, "Aktuelle Kerze ist aussergewoehnlich gross – Ausdehnung laeuft"
    return False, ""


def _broke_out(ctx: MarketContext, high: float, low: float) -> str | None:
    """Wurde eine Ausbruchsmarke in den letzten beiden Kerzen genommen?"""
    candles = ctx.exec_f.series.candles
    if len(candles) < 3:
        return None
    reference = candles[-3]
    for candle in candles[-2:]:
        if candle.close > high and reference.close <= high:
            return "long"
        if candle.close < low and reference.close >= low:
            return "short"
    return None


def evaluate(ctx: MarketContext) -> Setup:
    """Ein Instrument vollstaendig bewerten."""
    f = ctx.exec_f
    hits = detect_all(ctx)

    readiness = _readiness_score(hits)
    direction = _direction_score(hits)
    confidence = _confidence_score(hits, direction)
    bias = _bias(direction)

    high, low = _triggers(ctx)
    notes: list[str] = []

    # ---- Zustand bestimmen ------------------------------------------------
    if sessions.is_weekend(ctx.now):
        state = STATE_CLOSED
        notes.append("Der Devisenmarkt ruht. Die Werte stammen vom letzten Handelstag.")
    else:
        breakout = _broke_out(ctx, high, low)
        moved, move_note = _already_moved(ctx)
        released = any(h.key == "squeeze_release" for h in hits)

        if breakout or released:
            state = STATE_TRIGGERED
            if breakout:
                bias = breakout
                direction = 60.0 if breakout == "long" else -60.0
                notes.append("Der Kurs hat die Marke " + ("nach oben" if breakout == "long" else "nach unten") + " durchbrochen.")
        elif moved:
            state = STATE_COOLDOWN
            notes.append(move_note)
            notes.append("Fuer einen Einstieg auf einen Ruecksetzer warten.")
        elif readiness >= settings.arm_threshold:
            state = STATE_ARMED
            if bias == "neutral":
                notes.append("Die Richtung ist noch offen. Beide Ausbruchsmarken beobachten.")
        else:
            state = STATE_WATCH

    # ---- Handelsniveaus ---------------------------------------------------
    levels = build_levels(
        symbol=ctx.symbol,
        price=f.price,
        atr=f.atr_now,
        bias=bias if bias != "neutral" else "long",
        trigger_long=high,
        trigger_short=low,
    )

    # ---- Regime -----------------------------------------------------------
    adx_now = ind.last_valid(f.adx) or 0.0
    if adx_now >= 25:
        regime = "Der Kurs laeuft in eine Richtung"
    elif adx_now >= 18:
        regime = "Eine Richtung bildet sich gerade"
    else:
        regime = "Der Kurs pendelt seitwaerts"

    if ctx.calendar_risk:
        notes.append(ctx.calendar_risk["advice"])

    score = tacho_score(direction, confidence)
    action = action_for(score)
    tension = tension_for(state, readiness)

    last = f.series.candles[-1] if f.series.candles else None
    return Setup(
        symbol=ctx.symbol,
        timeframe=ctx.execution_tf,
        ts=last.ts if last else 0,
        price=round(f.price, 6),
        state=state,
        readiness=readiness,
        direction=direction,
        confidence=confidence,
        bias=bias,
        hits=hits,
        levels=levels,
        regime=regime,
        session=sessions.session_label(ctx.now),
        notes=notes,
        event_risk=ctx.calendar_risk,
        score=score,
        action=action,
        tension=tension,
        headline=headline_for(ctx.symbol, state, action, tension),
    )
