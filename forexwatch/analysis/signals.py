"""Signalerkennung – der Kern des Fruehwarnsystems.

Grundgedanke
------------
Der Zeitpunkt einer Bewegung laesst sich nicht vorhersagen, ihr *Zustand
davor* aber sehr wohl beschreiben. Vor nahezu jeder groesseren Bewegung
laesst sich mindestens eines dieser Merkmale beobachten:

* die Volatilitaet ist ungewoehnlich niedrig (Kompression, "Squeeze"),
* die Handelsspanne verengt sich fortlaufend (Keilbildung),
* das Momentum laeuft dem Preis davon oder hinterher (Divergenz),
* mehrere Zeitebenen zeigen in dieselbe Richtung (Alignment),
* ein planbarer Ausloeser steht bevor (Session-Eroeffnung, Termin),
* korrelierte Paare sind auseinandergelaufen (Nachholbewegung).

Jeder Detektor liefert einen ``SignalHit`` mit zwei getrennten Groessen:

``readiness``  0..1  – wie stark ist der Markt "aufgeladen"?
``direction`` -1..1  – in welche Richtung zeigt der Hinweis?

Erst das Scoring-Modul verrechnet beide zu einem Gesamturteil. Diese
Trennung ist wichtig: Kompression sagt *dass* etwas passiert, Struktur und
Momentum sagen *wohin*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..models import SignalHit
from . import indicators as ind
from . import sessions
from .features import Features, squeeze_just_released, squeeze_length
from .structure import divergence, inside_bars, key_levels, liquidity_sweep, narrow_range

# Gewichte der einzelnen Bausteine. Sie bestimmen, wie stark ein Merkmal in
# das Gesamturteil eingeht, und sind bewusst an einer Stelle gebuendelt.
WEIGHTS: dict[str, float] = {
    "squeeze": 2.4,
    "volatility_low": 1.8,
    "range_contraction": 1.5,
    "narrow_range": 1.0,
    "ema_coil": 1.2,
    "squeeze_release": 2.2,
    "trend_alignment": 2.0,
    "structure": 1.4,
    "divergence": 1.8,
    "liquidity_sweep": 1.7,
    "adx_building": 1.3,
    "level_proximity": 1.2,
    "asian_range": 1.6,
    "session_timing": 1.1,
    "calendar_pressure": 1.4,
    "correlation_gap": 1.3,
}


@dataclass(slots=True)
class MarketContext:
    """Alles, was ein Detektor ueber ein Instrument wissen muss."""

    symbol: str
    execution_tf: str
    features: dict[str, Features]
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    peers: dict[str, Features] = field(default_factory=dict)
    calendar_risk: dict | None = None
    calendar_events: list = field(default_factory=list)

    @property
    def exec_f(self) -> Features:
        return self.features[self.execution_tf]

    def higher(self) -> list[Features]:
        """Alle Timeframes oberhalb des Ausfuehrungs-Timeframes."""
        from ..providers.base import timeframe_seconds

        base = timeframe_seconds(self.execution_tf)
        return [
            f
            for tf, f in self.features.items()
            if timeframe_seconds(tf) > base and len(f) >= 30
        ]


# --------------------------------------------------------------------------
# Gruppe 1 – Kompression: "Es staut sich etwas auf"
# --------------------------------------------------------------------------


def detect_squeeze(ctx: MarketContext) -> SignalHit | None:
    """Bollinger-Baender innerhalb des Keltner-Kanals.

    Je laenger dieser Zustand anhaelt, desto heftiger faellt die Aufloesung
    erfahrungsgemaess aus. Ab etwa 6 Kerzen wird es interessant, ab 20 ist
    die Aufladung ausgereizt.
    """
    f = ctx.exec_f
    length = squeeze_length(f)
    if length < 4:
        return None
    readiness = min(1.0, 0.35 + length / 24.0)

    # Lage im Kanal gibt einen schwachen Richtungshinweis: notiert der Kurs
    # im oberen Drittel der Kompression, ist ein Ausbruch nach oben etwas
    # wahrscheinlicher.
    direction = 0.0
    upper, lower = ind.last_valid(f.kc_upper), ind.last_valid(f.kc_lower)
    if upper and lower and upper > lower:
        position = (f.price - lower) / (upper - lower)
        direction = max(-0.5, min(0.5, (position - 0.5) * 1.6))

    return SignalHit(
        key="squeeze",
        label="Volatilitaets-Kompression",
        readiness=readiness,
        direction=direction,
        weight=WEIGHTS["squeeze"],
        detail=f"Squeeze seit {length} Kerzen – die Spanne ist ungewoehnlich eng",
        category="kompression",
    )


def detect_low_volatility(ctx: MarketContext) -> SignalHit | None:
    """ATR im unteren Perzentilbereich der letzten 100 Kerzen."""
    f = ctx.exec_f
    values = [v for v in f.atr14[-120:] if v is not None]
    if len(values) < 40:
        return None
    current = values[-1]
    rank = ind.percentile_rank(values, current)
    if rank > 30.0:
        return None
    readiness = min(1.0, (30.0 - rank) / 30.0 * 0.9 + 0.25)
    return SignalHit(
        key="volatility_low",
        label="Volatilitaet im Tief",
        readiness=readiness,
        direction=0.0,
        weight=WEIGHTS["volatility_low"],
        detail=f"ATR nur im {rank:.0f}. Perzentil – Ruhe geht Bewegung voraus",
        category="kompression",
    )


def detect_range_contraction(ctx: MarketContext) -> SignalHit | None:
    """Verengt sich die Bollinger-Bandbreite fortlaufend? (Keilbildung)"""
    f = ctx.exec_f
    widths = [v for v in f.bb_width[-30:] if v is not None]
    if len(widths) < 20:
        return None
    recent = sum(widths[-5:]) / 5.0
    earlier = sum(widths[-20:-10]) / 10.0
    if earlier <= 0 or recent >= earlier * 0.75:
        return None
    shrink = 1.0 - (recent / earlier)
    return SignalHit(
        key="range_contraction",
        label="Spanne verengt sich",
        readiness=min(1.0, shrink * 2.0),
        direction=0.0,
        weight=WEIGHTS["range_contraction"],
        detail=f"Bandbreite um {shrink * 100:.0f}% geschrumpft – der Markt zieht sich zusammen",
        category="kompression",
    )


def detect_narrow_range(ctx: MarketContext) -> SignalHit | None:
    """NR7 oder mehrere Inside Bars – sehr kurzfristige Aufladung."""
    f = ctx.exec_f
    candles = f.series.candles
    if len(candles) < 10:
        return None
    nr7 = narrow_range(candles, 7)
    inside = inside_bars(candles)
    if not nr7 and inside < 2:
        return None
    readiness = 0.0
    parts: list[str] = []
    if nr7:
        readiness += 0.45
        parts.append("engste Kerze der letzten 7")
    if inside >= 2:
        readiness += min(0.45, 0.15 * inside)
        parts.append(f"{inside} Inside Bars in Folge")
    return SignalHit(
        key="narrow_range",
        label="Enge Kerzenformation",
        readiness=min(1.0, readiness),
        direction=0.0,
        weight=WEIGHTS["narrow_range"],
        detail=" / ".join(parts),
        category="kompression",
    )


def detect_ema_coil(ctx: MarketContext) -> SignalHit | None:
    """Liegen EMA20, EMA50 und EMA200 dicht beieinander?

    Buendeln sich die Durchschnitte, fehlt dem Markt eine Richtung – das ist
    haeufig der Punkt kurz vor einem neuen Trendimpuls.
    """
    f = ctx.exec_f
    e20, e50, e200 = ind.last_valid(f.ema20), ind.last_valid(f.ema50), ind.last_valid(f.ema200)
    if not (e20 and e50 and e200) or not f.atr_now:
        return None
    spread = (max(e20, e50, e200) - min(e20, e50, e200)) / f.atr_now
    if spread > 1.6:
        return None
    readiness = min(1.0, (1.6 - spread) / 1.6)
    return SignalHit(
        key="ema_coil",
        label="Durchschnitte gebuendelt",
        readiness=readiness,
        direction=0.0,
        weight=WEIGHTS["ema_coil"],
        detail=f"EMA20/50/200 liegen innerhalb von {spread:.2f} ATR – Richtungsentscheidung steht an",
        category="kompression",
    )


def detect_squeeze_release(ctx: MarketContext) -> SignalHit | None:
    """Der Squeeze loest sich gerade auf – die Bewegung beginnt jetzt."""
    f = ctx.exec_f
    if not squeeze_just_released(f, within=2):
        return None
    hist = ind.last_valid(f.macd_hist)
    direction = 0.0
    if hist is not None:
        direction = 0.8 if hist > 0 else -0.8
    return SignalHit(
        key="squeeze_release",
        label="Kompression loest sich auf",
        readiness=0.9,
        direction=direction,
        weight=WEIGHTS["squeeze_release"],
        detail="Die Baender oeffnen sich – der Ausbruch laeuft an",
        category="ausloesung",
    )


# --------------------------------------------------------------------------
# Gruppe 2 – Richtung: "Wohin loest es sich auf?"
# --------------------------------------------------------------------------


def detect_trend_alignment(ctx: MarketContext) -> SignalHit | None:
    """Zeigen die hoeheren Zeitebenen einheitlich in eine Richtung?"""
    higher = ctx.higher()
    if not higher:
        return None
    votes: list[float] = []
    labels: list[str] = []
    for f in higher:
        e20, e50 = ind.last_valid(f.ema20), ind.last_valid(f.ema50)
        if not (e20 and e50):
            continue
        vote = 0.0
        if f.price > e20 > e50:
            vote = 1.0
        elif f.price < e20 < e50:
            vote = -1.0
        elif f.price > e50:
            vote = 0.4
        elif f.price < e50:
            vote = -0.4
        votes.append(vote)
        labels.append(f"{f.series.timeframe}:{'auf' if vote > 0 else 'ab' if vote < 0 else 'neutral'}")
    if not votes:
        return None

    direction = sum(votes) / len(votes)
    agreement = abs(direction)
    if agreement < 0.35:
        return None
    return SignalHit(
        key="trend_alignment",
        label="Zeitebenen im Gleichklang",
        readiness=min(1.0, agreement * 0.7),
        direction=max(-1.0, min(1.0, direction)),
        weight=WEIGHTS["trend_alignment"],
        detail="Uebergeordnet " + ", ".join(labels),
        category="richtung",
    )


def detect_structure(ctx: MarketContext) -> SignalHit | None:
    """Marktstruktur aus hoeheren Hochs/Tiefs."""
    f = ctx.exec_f
    mapping = {"aufwaerts": 0.7, "abwaerts": -0.7, "seitwaerts": 0.0, "unklar": 0.0}
    direction = mapping.get(f.structure, 0.0)
    if direction == 0.0:
        return None
    return SignalHit(
        key="structure",
        label="Marktstruktur",
        readiness=0.25,
        direction=direction,
        weight=WEIGHTS["structure"],
        detail=f"Struktur {f.structure}: {'hoehere Hochs und Tiefs' if direction > 0 else 'tiefere Hochs und Tiefs'}",
        category="richtung",
    )


def detect_divergence(ctx: MarketContext) -> SignalHit | None:
    """Momentum-Divergenz als Hinweis auf eine bevorstehende Umkehr."""
    f = ctx.exec_f
    result = divergence(f.series.candles, f.rsi14, f.swings)
    if not result:
        return None
    direction = 1.0 if result["direction"] == "long" else -1.0
    strength = float(result["strength"])
    return SignalHit(
        key="divergence",
        label="Momentum-Divergenz",
        readiness=min(1.0, 0.4 + strength * 0.5),
        direction=direction * min(1.0, 0.55 + strength * 0.45),
        weight=WEIGHTS["divergence"],
        detail=str(result["text"]),
        category="richtung",
    )


def detect_liquidity_sweep(ctx: MarketContext) -> SignalHit | None:
    """Stop-Run ueber ein Extrem mit anschliessender Ablehnung."""
    f = ctx.exec_f
    result = liquidity_sweep(f.series, lookback=30)
    if not result:
        return None
    direction = 1.0 if result["direction"] == "long" else -1.0
    return SignalHit(
        key="liquidity_sweep",
        label="Liquiditaets-Abgriff",
        readiness=0.6,
        direction=direction * 0.8,
        weight=WEIGHTS["liquidity_sweep"],
        detail=f"{result['text']} (Docht {result['wick_ratio'] * 100:.0f}% der Kerze)",
        category="richtung",
    )


def detect_adx_building(ctx: MarketContext) -> SignalHit | None:
    """ADX steigt aus dem Niemandsland – ein Trend formiert sich gerade."""
    f = ctx.exec_f
    values = [v for v in f.adx[-12:] if v is not None]
    if len(values) < 6:
        return None
    current, past = values[-1], values[-6]
    if not (12.0 <= current <= 30.0 and current > past + 3.0):
        return None
    pdi, mdi = ind.last_valid(f.plus_di), ind.last_valid(f.minus_di)
    direction = 0.0
    if pdi is not None and mdi is not None:
        direction = 0.6 if pdi > mdi else -0.6
    return SignalHit(
        key="adx_building",
        label="Trendstaerke waechst",
        readiness=min(1.0, (current - past) / 12.0 + 0.3),
        direction=direction,
        weight=WEIGHTS["adx_building"],
        detail=f"ADX steigt von {past:.0f} auf {current:.0f} – ein Trend beginnt sich zu bilden",
        category="richtung",
    )


def detect_level_proximity(ctx: MarketContext) -> SignalHit | None:
    """Kurs laeuft auf eine wichtige Zone zu – dort faellt die Entscheidung.

    Die Zonen stammen bewusst von der hoechsten verfuegbaren Zeitebene: ein
    Widerstand aus dem Tageschart haelt den Kurs deutlich zuverlaessiger auf
    als ein Zufallshoch aus dem 15-Minuten-Chart. Abstand und ATR werden
    dagegen auf dem Ausfuehrungs-Timeframe gemessen, weil dort gehandelt wird.
    """
    from ..providers.base import timeframe_seconds

    f = ctx.exec_f
    if not f.atr_now:
        return None

    candidates = [x for x in ctx.features.values() if len(x) >= 60]
    if not candidates:
        return None
    source = max(candidates, key=lambda x: timeframe_seconds(x.series.timeframe))

    levels = key_levels(source.series, max_levels=6)
    if not levels:
        return None

    price = f.price
    nearest = min(levels, key=lambda lv: abs(lv["price"] - price))
    distance = abs(nearest["price"] - price)
    if distance > f.atr_now * 1.5:
        return None
    closeness = 1.0 - (distance / (f.atr_now * 1.5))
    # Am Widerstand droht Abprall (short), an der Unterstuetzung Halt (long).
    direction = -0.4 if nearest["kind"] == "widerstand" else 0.4
    return SignalHit(
        key="level_proximity",
        label="Wichtige Zone in Reichweite",
        readiness=min(1.0, 0.35 + closeness * 0.5),
        direction=direction,
        weight=WEIGHTS["level_proximity"],
        detail=(
            f"{nearest['kind'].capitalize()} bei {nearest['price']:.5f} aus dem "
            f"{source.series.timeframe}-Chart ({nearest['touches']} Beruehrungen, "
            f"{distance / f.atr_now:.1f} ATR entfernt)"
        ),
        category="struktur",
    )


# Gruppe 3 – Timing: "Wann ist es so weit?"
# --------------------------------------------------------------------------


def detect_asian_range(ctx: MarketContext) -> SignalHit | None:
    """Enge Asien-Spanne vor der London-Eroeffnung.

    Das ist der planbarste Vorlauf ueberhaupt: eine ungewoehnlich schmale
    Nachtspanne wird beim London-Open ueberdurchschnittlich oft gebrochen.
    """
    f = ctx.exec_f
    result = sessions.asian_range(f.series.candles, ctx.now)
    if not result or not result.get("compressed"):
        return None

    minutes = sessions.minutes_to_session_open("London", ctx.now)
    hour = ctx.now.hour
    # Nur relevant kurz vor bzw. in den ersten Stunden nach der Eroeffnung
    if not (minutes <= 180 or 7 <= hour < 11):
        return None

    ratio = result.get("ratio_to_daily") or 0.45
    readiness = min(1.0, 0.5 + (0.45 - ratio))
    if minutes <= 90:
        readiness = min(1.0, readiness + 0.15)

    return SignalHit(
        key="asian_range",
        label="Enge Asien-Spanne",
        readiness=readiness,
        direction=0.0,
        weight=WEIGHTS["asian_range"],
        detail=(
            f"Nachtspanne {result['high']:.5f} / {result['low']:.5f} – nur "
            f"{ratio * 100:.0f}% einer normalen Tagesspanne"
        ),
        category="timing",
    )


def detect_session_timing(ctx: MarketContext) -> SignalHit | None:
    """Naehe zu einem Zeitpunkt mit erfahrungsgemaess hoher Bewegung."""
    if sessions.is_weekend(ctx.now):
        return None
    name, minutes = sessions.next_key_moment(ctx.now)
    factor = sessions.session_volatility_factor(ctx.now)
    if minutes > 60 and factor < 1.3:
        return None
    readiness = 0.0
    parts: list[str] = []
    if minutes <= 60:
        readiness += 0.35 + (60 - minutes) / 60.0 * 0.3
        parts.append(f"{name} in {minutes} Min.")
    if factor >= 1.3:
        readiness += 0.3
        parts.append(sessions.session_label(ctx.now))
    if readiness <= 0:
        return None
    return SignalHit(
        key="session_timing",
        label="Aktives Zeitfenster",
        readiness=min(1.0, readiness),
        direction=0.0,
        weight=WEIGHTS["session_timing"],
        detail=" | ".join(parts),
        category="timing",
    )


def detect_calendar_pressure(ctx: MarketContext) -> SignalHit | None:
    """Ein hochrelevanter Termin steht an.

    Vor solchen Terminen zieht sich der Markt oft zusammen und bricht danach
    aus. Der Hinweis ist bewusst richtungsneutral – die Richtung entscheidet
    sich erst mit der Zahl.
    """
    risk = ctx.calendar_risk
    if not risk:
        return None
    minutes = int(risk["minutes"])
    if minutes > 240:
        return None
    readiness = min(1.0, 0.4 + (240 - minutes) / 240.0 * 0.5)
    return SignalHit(
        key="calendar_pressure",
        label="Termin steht bevor",
        readiness=readiness,
        direction=0.0,
        weight=WEIGHTS["calendar_pressure"],
        detail=f"{risk['title']} ({risk['currency']}) in {minutes} Min.",
        category="timing",
    )


def detect_correlation_gap(ctx: MarketContext) -> SignalHit | None:
    """Korreliertes Paar ist davongelaufen – Nachholbewegung wahrscheinlich.

    Bewegt sich z. B. GBPUSD deutlich, waehrend EURUSD stehen bleibt, obwohl
    beide normalerweise eng zusammenlaufen, holt der Nachzuegler die Bewegung
    ueberdurchschnittlich oft nach.
    """
    f = ctx.exec_f
    if not ctx.peers or len(f) < 60:
        return None

    own = ind.returns(f.closes[-60:])
    best: tuple[str, float, float] | None = None
    for name, peer in ctx.peers.items():
        if name == ctx.symbol or len(peer) < 60:
            continue
        other = ind.returns(peer.closes[-60:])
        correlation = ind.pearson(own[:-5], other[:-5])
        if abs(correlation) < 0.65:
            continue
        # Bewegung der letzten 5 Kerzen vergleichen
        own_move = sum(own[-5:])
        peer_move = sum(other[-5:]) * (1.0 if correlation > 0 else -1.0)
        gap = peer_move - own_move
        if abs(gap) < 0.12:
            continue
        if best is None or abs(gap) > abs(best[2]):
            best = (name, correlation, gap)

    if not best:
        return None
    name, correlation, gap = best
    direction = max(-1.0, min(1.0, gap / 0.4))
    return SignalHit(
        key="correlation_gap",
        label="Korrelations-Luecke",
        readiness=min(1.0, 0.3 + abs(gap) / 0.6),
        direction=direction * 0.7,
        weight=WEIGHTS["correlation_gap"],
        detail=(
            f"{name} ist {gap:+.2f}% vorausgelaufen (Korrelation {correlation:+.2f}) – "
            f"{ctx.symbol} hinkt hinterher"
        ),
        category="richtung",
    )


# --------------------------------------------------------------------------
# Sammellauf
# --------------------------------------------------------------------------

DETECTORS = (
    detect_squeeze,
    detect_low_volatility,
    detect_range_contraction,
    detect_narrow_range,
    detect_ema_coil,
    detect_squeeze_release,
    detect_trend_alignment,
    detect_structure,
    detect_divergence,
    detect_liquidity_sweep,
    detect_adx_building,
    detect_level_proximity,
    detect_asian_range,
    detect_session_timing,
    detect_calendar_pressure,
    detect_correlation_gap,
)


def detect_all(ctx: MarketContext) -> list[SignalHit]:
    """Alle Detektoren ausfuehren und die Treffer sammeln."""
    hits: list[SignalHit] = []
    for detector in DETECTORS:
        try:
            hit = detector(ctx)
        except Exception:  # ein defekter Detektor darf den Scan nicht stoppen
            continue
        if hit is not None:
            hits.append(hit)
    return hits
