"""Wirtschaftskalender.

Termine mit hoher Wirkung (Zinsentscheide, Arbeitsmarkt, Inflation) sind der
einzige Grund fuer eine bevorstehende Bewegung, der sich *sicher* im Voraus
kennen laesst. Das System nutzt sie doppelt:

* als Chance – vor einem Termin baut sich regelmaessig eine Kompression auf,
* als Risiko  – laufende Setups sollten vor dem Termin abgesichert sein.

Zwei kostenlose Quellen werden nacheinander versucht; faellt beides aus,
bleibt der Kalender leer und das System arbeitet ohne Termindaten weiter.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

log = logging.getLogger("forexwatch.calendar")

FAIRECONOMY_URLS = (
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
)
TRADINGVIEW_URL = "https://economic-calendar.tradingview.com/events"

# Waehrung -> Laendercode fuer die TradingView-Abfrage
CURRENCY_TO_COUNTRY = {
    "USD": "US", "EUR": "EU", "GBP": "GB", "JPY": "JP",
    "CHF": "CH", "AUD": "AU", "CAD": "CA", "NZD": "NZ", "CNY": "CN",
}
COUNTRY_TO_CURRENCY = {v: k for k, v in CURRENCY_TO_COUNTRY.items()}

# Schluesselbegriffe, die einen Termin unabhaengig von der Quellbewertung
# als hochrelevant kennzeichnen.
HIGH_IMPACT_KEYWORDS = (
    "interest rate", "rate decision", "fomc", "non-farm", "nonfarm", "nfp",
    "cpi", "inflation", "gdp", "unemployment", "payroll", "ecb press",
    "monetary policy", "powell", "lagarde", "pce",
)


@dataclass(slots=True)
class Event:
    ts: int
    title: str
    currency: str
    impact: str  # "hoch" | "mittel" | "niedrig"
    forecast: str = ""
    previous: str = ""
    actual: str = ""

    @property
    def when(self) -> datetime:
        return datetime.fromtimestamp(self.ts, tz=timezone.utc)

    def minutes_from(self, now: datetime) -> int:
        return int((self.when - now).total_seconds() // 60)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["iso"] = self.when.isoformat()
        return data


_IMPACT_ORDER = {"niedrig": 0, "mittel": 1, "hoch": 2}


def _title_key(title: str, currency: str) -> str:
    """Normalisierter Schluessel, damit derselbe Termin aus zwei Quellen
    nicht doppelt auftaucht (Schreibweisen unterscheiden sich leicht)."""
    cleaned = "".join(ch for ch in title.lower() if ch.isalnum())
    return f"{currency}:{cleaned[:28]}"


def _classify(title: str, raw_impact: str) -> str:
    lowered = title.lower()
    if any(word in lowered for word in HIGH_IMPACT_KEYWORDS):
        return "hoch"
    mapping = {"high": "hoch", "medium": "mittel", "low": "niedrig", "holiday": "niedrig"}
    return mapping.get(raw_impact.lower(), "niedrig")


async def _fetch_faireconomy(client: httpx.AsyncClient) -> list[Event]:
    """Laufende und kommende Woche zusammenfuehren, damit auch am Wochenende
    bereits Vorlauf auf die naechsten Termine besteht."""
    rows: list[dict] = []
    for url in FAIRECONOMY_URLS:
        try:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            rows.extend(response.json())
        except Exception as exc:
            log.debug("Kalenderdatei %s nicht ladbar: %s", url, exc)
    if not rows:
        raise RuntimeError("keine Kalenderdaten von faireconomy")

    events: list[Event] = []
    seen: set[tuple[int, str, str]] = set()
    for row in rows:
        currency = str(row.get("country", "")).upper()
        if currency not in CURRENCY_TO_COUNTRY:
            continue
        try:
            when = datetime.fromisoformat(str(row["date"]))
        except (KeyError, ValueError):
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        title = str(row.get("title", "")).strip()
        key = (int(when.timestamp()), currency, title)
        if key in seen:
            continue
        seen.add(key)
        events.append(
            Event(
                ts=int(when.timestamp()),
                title=title,
                currency=currency,
                impact=_classify(title, str(row.get("impact", ""))),
                forecast=str(row.get("forecast", "") or ""),
                previous=str(row.get("previous", "") or ""),
            )
        )
    return events


async def _fetch_tradingview(client: httpx.AsyncClient) -> list[Event]:
    now = datetime.now(timezone.utc)
    params = {
        "from": now.strftime("%Y-%m-%dT00:00:00.000Z"),
        "to": (now + timedelta(days=7)).strftime("%Y-%m-%dT00:00:00.000Z"),
        "countries": ",".join(sorted(CURRENCY_TO_COUNTRY.values())),
    }
    response = await client.get(
        TRADINGVIEW_URL,
        params=params,
        headers={"User-Agent": "Mozilla/5.0", "Origin": "https://www.tradingview.com"},
    )
    response.raise_for_status()
    payload = response.json()
    importance_map = {1: "hoch", 0: "mittel", -1: "niedrig"}
    events: list[Event] = []
    for row in payload.get("result", []):
        currency = COUNTRY_TO_CURRENCY.get(str(row.get("country", "")).upper())
        if not currency:
            continue
        try:
            when = datetime.fromisoformat(str(row["date"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        title = str(row.get("title", "")).strip()
        raw = importance_map.get(row.get("importance"), "niedrig")
        impact = "hoch" if _classify(title, "") == "hoch" else raw
        events.append(
            Event(
                ts=int(when.timestamp()),
                title=title,
                currency=currency,
                impact=impact,
                forecast=str(row.get("forecast") or ""),
                previous=str(row.get("previous") or ""),
                actual=str(row.get("actual") or ""),
            )
        )
    return events


class EconomicCalendar:
    """Haelt die Termine der laufenden Woche vor und cached sie."""

    def __init__(self, ttl_seconds: int = 1800) -> None:
        self._events: list[Event] = []
        self._fetched_at: float = 0.0
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()
        self.source: str = "-"

    async def refresh(self, force: bool = False) -> list[Event]:
        now = datetime.now(timezone.utc).timestamp()
        if not force and self._events and (now - self._fetched_at) < self._ttl:
            return self._events

        async with self._lock:
            if not force and self._events and (now - self._fetched_at) < self._ttl:
                return self._events
            merged: dict[tuple[int, str], Event] = {}
            used: list[str] = []
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                # Beide Quellen werden zusammengefuehrt: faireconomy liefert die
                # laufende Woche sehr zuverlaessig, tradingview reicht weiter in
                # die Zukunft. Doppelte Termine werden ueber Zeit + Waehrung +
                # normalisierten Titel entfernt.
                tasks = {
                    "faireconomy": _fetch_faireconomy(client),
                    "tradingview": _fetch_tradingview(client),
                }
                results = await asyncio.gather(*tasks.values(), return_exceptions=True)
                for name, result in zip(tasks, results):
                    if isinstance(result, BaseException):
                        log.warning("Kalenderquelle %s nicht erreichbar: %s", name, result)
                        continue
                    if not result:
                        continue
                    used.append(name)
                    for event in result:
                        key = (event.ts // 300, _title_key(event.title, event.currency))
                        existing = merged.get(key)
                        if existing is None:
                            merged[key] = event
                        elif _IMPACT_ORDER[event.impact] > _IMPACT_ORDER[existing.impact]:
                            merged[key] = event

            if merged:
                events = sorted(merged.values(), key=lambda e: e.ts)
                self._events = events
                self._fetched_at = now
                self.source = " + ".join(used)
                log.info("Kalender geladen: %d Termine aus %s", len(events), self.source)
                return events

            log.warning("Kein Wirtschaftskalender verfuegbar – System laeuft ohne Termindaten")
            self._fetched_at = now
            return self._events

    # -- Abfragen ----------------------------------------------------------

    def upcoming(self, hours: int = 24, min_impact: str = "mittel") -> list[Event]:
        """Termine der naechsten `hours` Stunden ab der gewuenschten Relevanz."""
        order = _IMPACT_ORDER
        threshold = order.get(min_impact, 1)
        now = datetime.now(timezone.utc)
        limit = now + timedelta(hours=hours)
        return [
            e
            for e in self._events
            if now <= e.when <= limit and order.get(e.impact, 0) >= threshold
        ]

    def for_symbol(self, symbol: str, hours: int = 24, min_impact: str = "mittel") -> list[Event]:
        """Termine, die die beiden Waehrungen eines Paares betreffen."""
        base, quote = symbol[:3].upper(), symbol[3:6].upper()
        return [e for e in self.upcoming(hours, min_impact) if e.currency in (base, quote)]

    def risk_window(self, symbol: str, minutes: int = 90) -> dict[str, Any] | None:
        """Steht fuer dieses Paar in Kuerze ein wichtiger Termin an?

        Rueckgabe enthaelt auch eine Handlungsempfehlung, denn kurz vor einem
        Hochrelevanz-Termin ist ein Neueinstieg meist die schlechtere Wahl.
        """
        now = datetime.now(timezone.utc)
        relevant = self.for_symbol(symbol, hours=max(1, minutes // 60 + 1), min_impact="hoch")
        soon = [e for e in relevant if 0 <= e.minutes_from(now) <= minutes]
        if not soon:
            return None
        nearest = min(soon, key=lambda e: e.ts)
        remaining = nearest.minutes_from(now)
        if remaining <= 15:
            advice = "Kein Neueinstieg – Spreads weiten sich, Slippage-Gefahr"
        elif remaining <= 45:
            advice = "Nur mit reduzierter Groesse handeln, Stop weiter fassen"
        else:
            advice = "Termin einplanen, Position vorher absichern"
        return {
            "title": nearest.title,
            "currency": nearest.currency,
            "impact": nearest.impact,
            "minutes": remaining,
            "iso": nearest.when.isoformat(),
            "advice": advice,
            "count": len(soon),
        }

    @property
    def events(self) -> list[Event]:
        return list(self._events)


calendar = EconomicCalendar()
