"""Alarmierung.

Ein Alarm wird nur bei einer echten Zustandsaenderung ausgeloest, nicht bei
jedem Scan. Sonst waere das System nach wenigen Minuten unbrauchbar, weil
dasselbe Setup im Minutentakt gemeldet wuerde.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

from .config import settings
from .models import Alert, Setup

log = logging.getLogger("forexwatch.alerts")

# Zustaende, die ueberhaupt eine Meldung wert sind
ALERT_STATES = {"ARMED", "TRIGGERED"}

# Kuerzeste Zeit zwischen zwei Meldungen zum selben Instrument (Sekunden)
COOLDOWN = 15 * 60

# Um wie viele Punkte muss die Bereitschaft steigen, damit innerhalb des
# gleichen Zustands erneut gemeldet wird?
READINESS_STEP = 12.0


@dataclass(slots=True)
class _Last:
    state: str
    readiness: float
    bias: str
    ts: float


@dataclass
class AlertEngine:
    """Entscheidet ueber Alarme und verteilt sie an alle Kanaele."""

    on_alert: Callable[[Alert], Awaitable[None]] | None = None
    #: zuletzt gesehener Zustand je Instrument (jeder Scan)
    _seen: dict[str, _Last] = field(default_factory=dict)
    #: zuletzt *gemeldeter* Zustand je Instrument – nur hierauf stuetzt sich
    #: die Cooldown-Logik. Wuerde stattdessen der zuletzt gesehene Zustand
    #: herangezogen, ginge ausgerechnet der Uebergang WATCH -> ARMED
    #: verloren, also genau das Ereignis, auf das es ankommt.
    _alerted: dict[str, _Last] = field(default_factory=dict)

    # -- Entscheidung ------------------------------------------------------

    def should_alert(self, setup: Setup) -> tuple[bool, str]:
        """Ist dieses Setup eine Meldung wert? Liefert (ja/nein, Begruendung)."""
        if setup.state not in ALERT_STATES:
            return False, ""

        now = time.time()
        last = self._alerted.get(setup.symbol)

        if last is None:
            return True, "neu erkannt"

        if setup.state != last.state:
            # Der Uebergang zum bestaetigten Ausbruch ist immer relevant.
            if setup.state == "TRIGGERED":
                return True, "Ausbruch bestaetigt"
            # Rueckkehr nach ARMED nur, wenn zwischenzeitlich Zeit vergangen
            # ist – sonst wuerde ein Setup an der Schwelle hin- und herflattern.
            if now - last.ts >= COOLDOWN / 3:
                return True, f"Zustand {last.state} -> {setup.state}"
            return False, ""

        if setup.bias != last.bias and setup.bias != "neutral":
            return True, f"Richtung gedreht ({last.bias} -> {setup.bias})"

        if now - last.ts < COOLDOWN:
            return False, ""

        if setup.readiness >= last.readiness + READINESS_STEP:
            return True, f"Aufladung gestiegen ({last.readiness:.0f} -> {setup.readiness:.0f})"

        return False, ""

    def remember(self, setup: Setup) -> None:
        """Zuletzt gesehenen Zustand festhalten (unabhaengig von Alarmen)."""
        self._seen[setup.symbol] = _Last(setup.state, setup.readiness, setup.bias, time.time())

    def _remember_alert(self, setup: Setup) -> None:
        self._alerted[setup.symbol] = _Last(setup.state, setup.readiness, setup.bias, time.time())

    # -- Formulierung ------------------------------------------------------

    @staticmethod
    def compose(setup: Setup, reason: str) -> Alert:
        """Alarmtext in Klartext – ohne Fachbegriffe und ohne Zahlenkolonnen."""
        headline = {
            "ARMED": f"{setup.symbol}: Bewegung steht bevor",
            "TRIGGERED": f"{setup.symbol}: Die Bewegung hat begonnen",
        }.get(setup.state, f"{setup.symbol}")

        lines = [
            headline,
            "",
            setup.headline,
            "",
            f"Anzeige: {setup.score} von 100 – {setup.action}",
        ]

        if setup.levels:
            lv = setup.levels
            if setup.bias == "short":
                lines.append(f"Verkaufen unter {lv.trigger_short}")
            elif setup.bias == "long":
                lines.append(f"Kaufen ueber {lv.trigger_long}")
            else:
                lines.append(f"Ausbruch ueber {lv.trigger_long} oder unter {lv.trigger_short}")
            lines.append(f"Stop bei {lv.stop} – Ziel bei {lv.take_profit_1}")

        top = sorted(setup.hits, key=lambda h: h.readiness * h.weight, reverse=True)[:3]
        if top:
            lines.append("")
            lines.append("Warum:")
            for hit in top:
                lines.append(f"  - {hit.label}")

        if setup.event_risk:
            lines.append("")
            lines.append(f"Achtung: {setup.event_risk['title']} in {setup.event_risk['minutes']} Minuten.")

        return Alert(
            ts=int(time.time()),
            symbol=setup.symbol,
            timeframe=setup.timeframe,
            state=setup.state,
            bias=setup.bias,
            readiness=setup.readiness,
            message="\n".join(lines),
            payload=setup.to_dict(),
        )

    # -- Versand -----------------------------------------------------------

    async def dispatch(self, alert: Alert) -> None:
        """Alarm an alle konfigurierten Kanaele schicken.

        Faellt ein Kanal aus, laufen die uebrigen trotzdem – eine kaputte
        Webhook-URL darf den Scanner nicht anhalten.
        """
        log.info("ALARM %s [%s] %.0f", alert.symbol, alert.state, alert.readiness)

        if self.on_alert:
            try:
                await self.on_alert(alert)
            except Exception as exc:
                log.warning("Interner Alarm-Empfaenger fehlgeschlagen: %s", exc)

        async with httpx.AsyncClient(timeout=10.0) as client:
            if settings.webhook_url:
                try:
                    await client.post(settings.webhook_url, json=alert.to_dict())
                except Exception as exc:
                    log.warning("Webhook fehlgeschlagen: %s", exc)

            if settings.telegram_token and settings.telegram_chat_id:
                try:
                    await client.post(
                        f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
                        json={
                            "chat_id": settings.telegram_chat_id,
                            "text": alert.message,
                            "disable_web_page_preview": True,
                        },
                    )
                except Exception as exc:
                    log.warning("Telegram fehlgeschlagen: %s", exc)

    async def process(self, setup: Setup) -> Alert | None:
        """Pruefen, formulieren, verschicken – die uebliche Reihenfolge."""
        ok, reason = self.should_alert(setup)
        self.remember(setup)
        if not ok:
            return None
        self._remember_alert(setup)
        alert = self.compose(setup, reason)
        await self.dispatch(alert)
        return alert

    def state_snapshot(self) -> dict[str, dict[str, Any]]:
        return {
            symbol: {"state": v.state, "readiness": v.readiness, "bias": v.bias, "ts": v.ts}
            for symbol, v in self._seen.items()
        }
