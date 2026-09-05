"""Der Scanner: haelt Marktdaten aktuell und bewertet alle Instrumente.

Ablauf eines Durchgangs
-----------------------
1. Kerzen aller Instrumente und Zeitebenen laden (parallel, aber gedrosselt),
2. Indikatoren berechnen,
3. jedes Instrument bewerten,
4. Ergebnis speichern, bei Bedarf Alarm ausloesen und an die Oberflaeche
   verteilen.

Damit die Datenquelle nicht unnoetig belastet wird, bekommt jede Zeitebene
ein eigenes Aktualisierungsintervall: eine Tageskerze muss nicht jede Minute
neu geladen werden.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from .alerts import AlertEngine
from .analysis.features import Features, build_features
from .analysis.scoring import evaluate
from .analysis.signals import MarketContext
from .calendar import calendar
from .config import settings
from .models import Alert, Series, Setup
from .providers import get_provider
from .providers.base import timeframe_seconds
from .risk import position_plan
from .storage import Storage

log = logging.getLogger("forexwatch.engine")

# Wie viele Kerzen je Zeitebene vorgehalten werden. 200er-EMA und die
# Perzentil-Berechnungen brauchen spuerbar Historie.
CANDLE_LIMIT = 400

# Gleichzeitige Anfragen an die Datenquelle
MAX_PARALLEL_REQUESTS = 6


class Engine:
    def __init__(self, storage: Storage | None = None) -> None:
        self.provider = get_provider()
        self.storage = storage or Storage(settings.db_path)
        self.alerts = AlertEngine()

        self._series: dict[tuple[str, str], Series] = {}
        self._fetched_at: dict[tuple[str, str], float] = {}
        self._features: dict[tuple[str, str], Features] = {}
        self._setups: dict[str, Setup] = {}

        self._subscribers: list[Callable[[str, dict[str, Any]], Awaitable[None]]] = []
        self._gate = asyncio.Semaphore(MAX_PARALLEL_REQUESTS)
        self._task: asyncio.Task | None = None
        self._running = False

        self.last_scan: float = 0.0
        self.last_error: str = ""
        self.scan_count: int = 0

        self.alerts.on_alert = self._on_alert

    # -- Abonnenten (WebSocket) -------------------------------------------

    def subscribe(self, callback: Callable[[str, dict[str, Any]], Awaitable[None]]) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[str, dict[str, Any]], Awaitable[None]]) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def _broadcast(self, event: str, payload: dict[str, Any]) -> None:
        for callback in list(self._subscribers):
            try:
                await callback(event, payload)
            except Exception:
                self.unsubscribe(callback)

    async def _on_alert(self, alert: Alert) -> None:
        self.storage.save_alert(alert)
        await self._broadcast("alert", alert.to_dict())

    # -- Datenbeschaffung --------------------------------------------------

    def _refresh_interval(self, timeframe: str) -> float:
        """Wie oft muss diese Zeitebene neu geladen werden?"""
        if timeframe == settings.execution_timeframe:
            return float(settings.scan_interval)
        return max(float(settings.scan_interval), timeframe_seconds(timeframe) / 6.0)

    async def _load(self, symbol: str, timeframe: str) -> Series:
        """Kerzen laden – mit Cache, Ratenbegrenzung und Rueckfall auf die
        Datenbank, falls die Quelle gerade nicht erreichbar ist."""
        key = (symbol, timeframe)
        now = time.time()

        cached = self._series.get(key)
        if cached and (now - self._fetched_at.get(key, 0.0)) < self._refresh_interval(timeframe):
            return cached

        async with self._gate:
            try:
                series = await self.provider.fetch(symbol, timeframe, CANDLE_LIMIT)
            except Exception as exc:
                log.warning("Abruf %s %s fehlgeschlagen: %s", symbol, timeframe, exc)
                series = Series(symbol, timeframe, [])

        if len(series) < 30:
            # Quelle liefert nichts Brauchbares -> letzten bekannten Stand nutzen
            fallback = cached or self.storage.load_candles(symbol, timeframe, CANDLE_LIMIT)
            if len(fallback) >= 30:
                log.info("Nutze zwischengespeicherte Daten fuer %s %s", symbol, timeframe)
                self._series[key] = fallback
                return fallback
            return series

        self._series[key] = series
        self._fetched_at[key] = now
        self.storage.save_candles(series)
        return series

    async def warm_start(self) -> None:
        """Beim Start zuerst aus der Datenbank fuellen, damit die Oberflaeche
        sofort etwas anzeigt, auch wenn der erste Abruf noch laeuft."""
        for symbol in settings.pairs:
            for timeframe in settings.timeframes:
                series = self.storage.load_candles(symbol, timeframe, CANDLE_LIMIT)
                if len(series) >= 30:
                    self._series[(symbol, timeframe)] = series

    # -- Bewertung ---------------------------------------------------------

    async def scan(self) -> list[Setup]:
        """Ein vollstaendiger Durchgang ueber alle Instrumente."""
        started = time.time()
        now = datetime.now(timezone.utc)

        try:
            await calendar.refresh()
        except Exception as exc:
            log.warning("Kalender konnte nicht aktualisiert werden: %s", exc)

        # 1) Alle Kerzen laden
        jobs = [
            self._load(symbol, timeframe)
            for symbol in settings.pairs
            for timeframe in settings.timeframes
        ]
        await asyncio.gather(*jobs, return_exceptions=True)

        # 2) Indikatoren berechnen
        self._features = {}
        for (symbol, timeframe), series in self._series.items():
            if len(series) >= 30:
                self._features[(symbol, timeframe)] = build_features(series)

        exec_tf = settings.execution_timeframe
        peers = {
            symbol: f
            for (symbol, timeframe), f in self._features.items()
            if timeframe == exec_tf
        }

        # Aktuelle Kurse als Umrechnungsbasis fuer die Pip-Werte
        rates = {sym: f.price for sym, f in peers.items()}

        # 3) Bewerten
        setups: list[Setup] = []
        for symbol in settings.pairs:
            features = {
                timeframe: self._features[(symbol, timeframe)]
                for timeframe in settings.timeframes
                if (symbol, timeframe) in self._features
            }
            if exec_tf not in features:
                continue
            try:
                context = MarketContext(
                    symbol=symbol,
                    execution_tf=exec_tf,
                    features=features,
                    now=now,
                    peers=peers,
                    calendar_risk=calendar.risk_window(symbol, minutes=240),
                    calendar_events=[e.to_dict() for e in calendar.for_symbol(symbol, 24, "hoch")],
                )
                setup = evaluate(context)
            except Exception as exc:
                log.exception("Bewertung von %s fehlgeschlagen: %s", symbol, exc)
                continue

            # Positionsgroesse und Termine gleich mitliefern, damit die
            # Oberflaeche alles Wesentliche in einem Zug bekommt.
            setup.events = [e.to_dict() for e in calendar.for_symbol(symbol, 96, "hoch")[:5]]
            if setup.levels:
                setup.position = position_plan(
                    symbol=symbol,
                    entry=setup.levels.entry,
                    stop=setup.levels.stop,
                    balance=settings.account_balance,
                    risk_percent=settings.risk_percent,
                    account_currency=settings.account_currency,
                    rates=rates,
                ).to_dict()

            setups.append(setup)
            self._setups[symbol] = setup
            self.storage.save_setup(setup)
            await self.alerts.process(setup)

        # 4) Nach Dringlichkeit sortieren und verteilen
        setups.sort(key=_urgency, reverse=True)
        self.last_scan = time.time()
        self.scan_count += 1
        self.last_error = ""
        log.info(
            "Scan #%d: %d Instrumente in %.1fs (%d ARMED, %d TRIGGERED)",
            self.scan_count,
            len(setups),
            self.last_scan - started,
            sum(1 for s in setups if s.state == "ARMED"),
            sum(1 for s in setups if s.state == "TRIGGERED"),
        )
        await self._broadcast("scan", {"setups": [s.to_dict() for s in setups], "ts": self.last_scan})
        return setups

    # -- Dauerbetrieb ------------------------------------------------------

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.scan()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                log.exception("Scan fehlgeschlagen: %s", exc)
            try:
                await asyncio.sleep(settings.scan_interval)
            except asyncio.CancelledError:
                raise

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self.warm_start()
        self._task = asyncio.create_task(self._loop())
        log.info(
            "Scanner gestartet: %d Instrumente, Zeitebenen %s, Intervall %ds, Quelle %s",
            len(settings.pairs),
            ", ".join(settings.timeframes),
            settings.scan_interval,
            self.provider.name,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.provider.close()

    # -- Abfragen fuer die Weboberflaeche ---------------------------------

    @property
    def setups(self) -> list[Setup]:
        return sorted(self._setups.values(), key=_urgency, reverse=True)

    def setup(self, symbol: str) -> Setup | None:
        return self._setups.get(symbol.upper())

    def series(self, symbol: str, timeframe: str) -> Series | None:
        return self._series.get((symbol.upper(), timeframe))

    def features(self, symbol: str, timeframe: str) -> Features | None:
        return self._features.get((symbol.upper(), timeframe))

    def status(self) -> dict[str, Any]:
        from .analysis import sessions

        now = datetime.now(timezone.utc)
        name, minutes = sessions.next_key_moment(now)
        return {
            "provider": self.provider.name,
            "running": self._running,
            "pairs": settings.pairs,
            "timeframes": settings.timeframes,
            "execution_timeframe": settings.execution_timeframe,
            "scan_interval": settings.scan_interval,
            "arm_threshold": settings.arm_threshold,
            "last_scan": self.last_scan,
            "scan_count": self.scan_count,
            "last_error": self.last_error,
            "market_open": not sessions.is_weekend(now),
            "session": sessions.session_label(now),
            "session_factor": sessions.session_volatility_factor(now),
            "next_moment": {"name": name, "minutes": minutes},
            "calendar_source": calendar.source,
            "calendar_events": len(calendar.events),
            "storage": self.storage.stats(),
        }


def _urgency(setup: Setup) -> tuple[int, float]:
    """Sortierschluessel: erst der Zustand, dann die Aufladung."""
    order = {"TRIGGERED": 4, "ARMED": 3, "COOLDOWN": 2, "WATCH": 1, "GESCHLOSSEN": 0}
    return order.get(setup.state, 0), setup.readiness
