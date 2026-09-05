"""Historische Ueberpruefung der Signallogik.

Warum das dazugehoert
---------------------
Ein Fruehwarnsystem, das seine Treffer nie nachrechnet, ist wertlos. Dieses
Modul spielt die *identische* Signallogik ueber historische Kerzen ab und
beantwortet drei Fragen:

1. Dehnt sich die Volatilitaet nach einem ARMED-Zustand tatsaechlich aus?
   (Das ist die eigentliche Kernbehauptung: "vor dem Ausschlag".)
2. Wie oft laeuft der Kurs anschliessend in die vorhergesagte Richtung?
3. Was haette ein Handel nach Plan (Einstieg an der Ausbruchsmarke, Stop und
   Ziel wie angezeigt) unter dem Strich ergeben?

Zu jedem Wert wird ein Vergleichswert ueber *alle* Kerzen ausgewiesen. Nur
die Differenz zwischen beiden sagt aus, ob die Signale einen Mehrwert haben.

Kein Blick in die Zukunft
-------------------------
Die Indikatoren werden einmal ueber die gesamte Reihe berechnet und dann
zurueckgeschnitten. Das ist zulaessig, weil alle Indikatoren rein
rueckwaertsgerichtet sind. Die einzige Ausnahme sind Swingpunkte, die zur
Bestaetigung Kerzen *nach* dem Hoch brauchen – sie werden deshalb erst ab
dem Zeitpunkt ihrer Bestaetigung sichtbar gemacht.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .analysis.features import Features, build_features
from .analysis.scoring import evaluate
from .analysis.signals import MarketContext
from .config import settings
from .models import Series

#: Wie viele Kerzen die Swing-Erkennung zur Bestaetigung nach rechts braucht.
SWING_CONFIRM_BARS = 2

#: Typische Spreads in Pips bei einem Broker mit engen Konditionen. Ohne
#: Kostenabzug sieht jede Strategie besser aus, als sie ist – gerade bei
#: Ausbruchshandel, wo sich der Spread im Moment des Einstiegs oft weitet.
DEFAULT_SPREADS = {
    "EURUSD": 0.8, "GBPUSD": 1.2, "USDJPY": 0.9, "USDCHF": 1.3,
    "AUDUSD": 1.1, "USDCAD": 1.4, "NZDUSD": 1.6, "EURJPY": 1.5,
    "EURGBP": 1.3, "GBPJPY": 2.2, "XAUUSD": 25.0,
}
FALLBACK_SPREAD = 1.5


def spread_for(symbol: str) -> float:
    return DEFAULT_SPREADS.get(symbol.upper(), FALLBACK_SPREAD)


def slice_features(full: Features, end: int) -> Features:
    """Sicht auf die Indikatoren bis einschliesslich Kerze `end`.

    Alle Reihen werden abgeschnitten; Swingpunkte werden zusaetzlich um die
    Bestaetigungsverzoegerung bereinigt, damit im Rueckblick nichts sichtbar
    ist, was zum damaligen Zeitpunkt noch nicht feststand.
    """
    stop = end + 1
    view = Features(
        series=Series(full.series.symbol, full.series.timeframe, full.series.candles[:stop]),
        closes=full.closes[:stop],
        highs=full.highs[:stop],
        lows=full.lows[:stop],
        ema20=full.ema20[:stop],
        ema50=full.ema50[:stop],
        ema200=full.ema200[:stop],
        rsi14=full.rsi14[:stop],
        atr14=full.atr14[:stop],
        bb_upper=full.bb_upper[:stop],
        bb_mid=full.bb_mid[:stop],
        bb_lower=full.bb_lower[:stop],
        kc_upper=full.kc_upper[:stop],
        kc_mid=full.kc_mid[:stop],
        kc_lower=full.kc_lower[:stop],
        dc_upper=full.dc_upper[:stop],
        dc_lower=full.dc_lower[:stop],
        macd_line=full.macd_line[:stop],
        macd_signal=full.macd_signal[:stop],
        macd_hist=full.macd_hist[:stop],
        adx=full.adx[:stop],
        plus_di=full.plus_di[:stop],
        minus_di=full.minus_di[:stop],
        stoch_k=full.stoch_k[:stop],
        stoch_d=full.stoch_d[:stop],
        bb_width=full.bb_width[:stop],
        squeeze_on=full.squeeze_on[:stop],
        swings=[s for s in full.swings if s.index <= end - SWING_CONFIRM_BARS],
    )
    from .analysis.structure import market_structure

    view.structure = market_structure(view.swings)
    return view


@dataclass(slots=True)
class Trade:
    index: int
    ts: int
    bias: str
    entry: float
    stop: float
    target: float
    exit_price: float
    exit_index: int
    result_r: float
    won: bool


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    bars: int
    horizon: int
    spread_pips: float = 0.0

    armed_count: int = 0
    # Volatilitaets-Ausdehnung
    expansion_after_armed: float = 0.0
    expansion_baseline: float = 0.0
    expansion_hit_rate: float = 0.0
    expansion_baseline_rate: float = 0.0
    # Vergleich nur gegen Kerzen mit aehnlich niedriger Vorlauf-Volatilitaet
    expansion_matched: float = 0.0
    expansion_matched_rate: float = 0.0
    matched_sample: int = 0
    # Richtung
    direction_hit_rate: float = 0.0
    direction_baseline: float = 0.0
    # Handel nach Plan
    trades: list[Trade] = field(default_factory=list)
    win_rate: float = 0.0
    expectancy_r: float = 0.0
    total_r: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_r: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "bars": self.bars,
            "horizon": self.horizon,
            "spread_pips": self.spread_pips,
            "armed_count": self.armed_count,
            "expansion": {
                "after_armed": round(self.expansion_after_armed, 3),
                "baseline": round(self.expansion_baseline, 3),
                "lift": round(self.expansion_after_armed - self.expansion_baseline, 3),
                "hit_rate": round(self.expansion_hit_rate, 1),
                "baseline_rate": round(self.expansion_baseline_rate, 1),
                "matched": round(self.expansion_matched, 3),
                "matched_rate": round(self.expansion_matched_rate, 1),
                "matched_lift": round(self.expansion_after_armed - self.expansion_matched, 3),
                "matched_rate_lift": round(self.expansion_hit_rate - self.expansion_matched_rate, 1),
                "matched_sample": self.matched_sample,
            },
            "direction": {
                "hit_rate": round(self.direction_hit_rate, 1),
                "baseline": round(self.direction_baseline, 1),
                "lift": round(self.direction_hit_rate - self.direction_baseline, 1),
            },
            "trading": {
                "trades": len(self.trades),
                "win_rate": round(self.win_rate, 1),
                "expectancy_r": round(self.expectancy_r, 3),
                "total_r": round(self.total_r, 2),
                "profit_factor": round(self.profit_factor, 2),
                "max_drawdown_r": round(self.max_drawdown_r, 2),
            },
            "sample_trades": [
                {
                    "ts": t.ts,
                    "bias": t.bias,
                    "entry": t.entry,
                    "stop": t.stop,
                    "target": t.target,
                    "result_r": round(t.result_r, 2),
                    "won": t.won,
                }
                for t in self.trades[-25:]
            ],
        }


def _atr_at(features: Features, index: int) -> float:
    for i in range(index, max(-1, index - 30), -1):
        value = features.atr14[i] if i < len(features.atr14) else None
        if value:
            return value
    return 0.0


def _realized_range(candles, start: int, end: int) -> float:
    window = candles[start:end]
    if not window:
        return 0.0
    return max(c.high for c in window) - min(c.low for c in window)


def run_backtest(
    series_by_tf: dict[str, Series],
    symbol: str,
    execution_tf: str,
    horizon: int = 12,
    wait_bars: int = 6,
    expansion_factor: float = 1.5,
    warmup: int = 220,
    cooldown_bars: int = 0,
    spread_pips: float | None = None,
) -> BacktestResult:
    """Die Signallogik ueber die Historie abspielen.

    ``horizon``          Kerzen, die nach einem Signal beobachtet werden
    ``wait_bars``        so lange gilt eine Ausbruchsmarke als aktiv
    ``expansion_factor`` ab welchem Vielfachen der vorherigen Spanne von einer
                         echten Ausdehnung gesprochen wird
    ``cooldown_bars``    Sperrfrist nach einem Signal. Ohne sie wuerde ein
                         mehrere Kerzen anhaltender ARMED-Zustand denselben
                         Handel mehrfach zaehlen und die Stichprobe
                         kuenstlich vergroessern. Standard: ein Horizont.
    ``spread_pips``      Handelskosten. Standard ist ein realistischer Wert
                         je Paar; 0 zeigt das Ergebnis ohne Kosten.
    """
    if cooldown_bars <= 0:
        cooldown_bars = horizon
    if spread_pips is None:
        spread_pips = spread_for(symbol)
    if execution_tf not in series_by_tf:
        raise ValueError(f"Keine Kursdaten fuer {symbol} im Timeframe {execution_tf}")

    exec_series = series_by_tf[execution_tf]
    full = {tf: build_features(s) for tf, s in series_by_tf.items() if len(s) >= 60}
    if execution_tf not in full:
        raise ValueError(f"Zu wenig Daten fuer {symbol} ({execution_tf})")

    exec_full = full[execution_tf]
    candles = exec_series.candles
    total = len(candles)
    result = BacktestResult(
        symbol=symbol, timeframe=execution_tf, bars=total, horizon=horizon,
        spread_pips=spread_pips,
    )

    if total < warmup + horizon + 10:
        return result

    # Zuordnung: zu jeder Ausfuehrungskerze der passende Index in den
    # hoeheren Zeitebenen (nur Kerzen, die zu diesem Zeitpunkt geschlossen
    # waren – sonst waere es ein Blick in die Zukunft).
    higher_index: dict[str, list[int]] = {}
    for tf, f in full.items():
        if tf == execution_tf:
            continue
        stamps = [c.ts for c in f.series.candles]
        mapping: list[int] = []
        pointer = -1
        for candle in candles:
            while pointer + 1 < len(stamps) and stamps[pointer + 1] <= candle.ts:
                pointer += 1
            mapping.append(pointer)
        higher_index[tf] = mapping

    from .risk import pip_size

    cost = spread_pips * pip_size(symbol)

    expansions_armed: list[float] = []
    expansions_all: list[float] = []
    # (prior-Spanne, Ausdehnungsverhaeltnis) je Kerze – Grundlage fuer den
    # volatilitaetsbereinigten Vergleich weiter unten.
    all_samples: list[tuple[float, float]] = []
    armed_priors: list[float] = []
    last_signal_index = -10**9
    direction_hits = 0
    direction_total = 0
    baseline_hits = 0
    baseline_total = 0

    for i in range(warmup, total - horizon - 1):
        prior = _realized_range(candles, i - horizon, i + 1)
        forward = _realized_range(candles, i + 1, i + 1 + horizon)
        ratio = (forward / prior) if prior > 0 else 0.0
        expansions_all.append(ratio)
        if prior > 0:
            all_samples.append((prior, ratio))

        # Vergleichswert Richtung: reine Muenzwurf-Referenz ueber alle Kerzen
        move = candles[i + horizon].close - candles[i].close
        if move != 0:
            baseline_total += 1
            baseline_hits += 1 if move > 0 else 0

        features = {execution_tf: slice_features(exec_full, i)}
        for tf, mapping in higher_index.items():
            end = mapping[i]
            if end >= 60:
                features[tf] = slice_features(full[tf], end)

        context = MarketContext(
            symbol=symbol,
            execution_tf=execution_tf,
            features=features,
            now=datetime.fromtimestamp(candles[i].ts, tz=timezone.utc),
            peers={},
            calendar_risk=None,
        )
        setup = evaluate(context)

        if setup.state != "ARMED" or setup.readiness < settings.arm_threshold:
            continue

        # Sperrfrist: ein anhaltender ARMED-Zustand ist *ein* Signal,
        # nicht eines pro Kerze.
        if i - last_signal_index < cooldown_bars:
            continue
        last_signal_index = i

        result.armed_count += 1
        expansions_armed.append(ratio)
        if prior > 0:
            armed_priors.append(prior)

        # Richtungstreffer nur werten, wenn eine Richtung angezeigt wurde
        if setup.bias in ("long", "short"):
            direction_total += 1
            gain = candles[i + horizon].close - candles[i].close
            if (gain > 0 and setup.bias == "long") or (gain < 0 and setup.bias == "short"):
                direction_hits += 1

        trade = _simulate(candles, i, setup, wait_bars, horizon, cost)
        if trade:
            result.trades.append(trade)

    # -- Auswertung --------------------------------------------------------

    if expansions_armed:
        result.expansion_after_armed = statistics.mean(expansions_armed)
        result.expansion_hit_rate = (
            sum(1 for r in expansions_armed if r >= expansion_factor) / len(expansions_armed) * 100.0
        )
    if expansions_all:
        result.expansion_baseline = statistics.mean(expansions_all)
        result.expansion_baseline_rate = (
            sum(1 for r in expansions_all if r >= expansion_factor) / len(expansions_all) * 100.0
        )

    # Volatilitaetsbereinigter Vergleich.
    #
    # Der einfache Vergleich oben ist zugunsten des Systems verzerrt: ein
    # ARMED-Zustand setzt eine enge Vorlaufspanne voraus, also ist der Nenner
    # des Verhaeltnisses bauartbedingt klein. Ein Teil der gemessenen
    # "Ausdehnung" ist damit blosse Rueckkehr der Volatilitaet zum Mittel und
    # kein Verdienst der Signallogik.
    #
    # Deshalb wird zusaetzlich nur gegen jene Kerzen verglichen, deren
    # Vorlaufspanne im selben Bereich lag wie bei den ARMED-Kerzen. Erst
    # dieser Wert zeigt, ob die Erkennung ueber die reine Enge hinaus etwas
    # beitraegt.
    if armed_priors and all_samples:
        low = min(armed_priors)
        high = max(armed_priors)
        matched = [ratio for prior, ratio in all_samples if low <= prior <= high]
        if matched:
            result.matched_sample = len(matched)
            result.expansion_matched = statistics.mean(matched)
            result.expansion_matched_rate = (
                sum(1 for r in matched if r >= expansion_factor) / len(matched) * 100.0
            )
    if direction_total:
        result.direction_hit_rate = direction_hits / direction_total * 100.0
    if baseline_total:
        result.direction_baseline = baseline_hits / baseline_total * 100.0

    if result.trades:
        wins = [t for t in result.trades if t.won]
        results = [t.result_r for t in result.trades]
        result.win_rate = len(wins) / len(result.trades) * 100.0
        result.expectancy_r = statistics.mean(results)
        result.total_r = sum(results)
        gross_win = sum(r for r in results if r > 0)
        gross_loss = abs(sum(r for r in results if r < 0))
        result.profit_factor = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

        equity = 0.0
        peak = 0.0
        drawdown = 0.0
        for value in results:
            equity += value
            peak = max(peak, equity)
            drawdown = min(drawdown, equity - peak)
        result.max_drawdown_r = drawdown

    return result


def _simulate(candles, index: int, setup, wait_bars: int, horizon: int, cost: float = 0.0) -> Trade | None:
    """Einen Handel nach dem angezeigten Plan durchspielen.

    Regeln, bewusst konservativ:
    * Einstieg erst, wenn die Ausbruchsmarke innerhalb von `wait_bars`
      tatsaechlich durchbrochen wird – ein ARMED allein ist kein Handel.
    * Werden Stop und Ziel in derselben Kerze beruehrt, gilt der Stop.
      Ohne Tickdaten laesst sich die Reihenfolge nicht klaeren, und die
      unguenstige Annahme verhindert geschoente Ergebnisse.
    * Vom Ergebnis geht der Spread ab. Bei Ausbruchshandel mit engen Stops
      ist er kein Rundungsfehler, sondern entscheidet ueber Gewinn und
      Verlust.
    """
    levels = setup.levels
    if not levels:
        return None

    bias = setup.bias if setup.bias in ("long", "short") else None
    entry_price: float | None = None
    entry_index = -1

    for j in range(index + 1, min(index + 1 + wait_bars, len(candles))):
        candle = candles[j]
        if bias in (None, "long") and candle.high >= levels.trigger_long:
            bias, entry_price, entry_index = "long", levels.trigger_long, j
            break
        if bias in (None, "short") and candle.low <= levels.trigger_short:
            bias, entry_price, entry_index = "short", levels.trigger_short, j
            break

    if entry_price is None or bias is None:
        return None

    if bias == "long":
        stop, target = levels.stop, levels.take_profit_1
        if stop >= entry_price or target <= entry_price:
            return None
    else:
        stop, target = levels.stop, levels.take_profit_1
        if stop <= entry_price or target >= entry_price:
            return None

    risk = abs(entry_price - stop)
    if risk <= 0:
        return None

    exit_price = candles[min(entry_index + horizon, len(candles) - 1)].close
    exit_index = min(entry_index + horizon, len(candles) - 1)

    for j in range(entry_index, min(entry_index + horizon + 1, len(candles))):
        candle = candles[j]
        if bias == "long":
            if candle.low <= stop:
                exit_price, exit_index = stop, j
                break
            if candle.high >= target:
                exit_price, exit_index = target, j
                break
        else:
            if candle.high >= stop:
                exit_price, exit_index = stop, j
                break
            if candle.low <= target:
                exit_price, exit_index = target, j
                break

    gain = (exit_price - entry_price) if bias == "long" else (entry_price - exit_price)
    result_r = (gain - cost) / risk
    return Trade(
        index=index,
        ts=candles[index].ts,
        bias=bias,
        entry=entry_price,
        stop=stop,
        target=target,
        exit_price=exit_price,
        exit_index=exit_index,
        result_r=result_r,
        won=result_r > 0,
    )
