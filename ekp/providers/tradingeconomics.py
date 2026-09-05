"""Wirtschaftskalender ueber die Trading-Economics-API.

Der kostenlose Gast-Schluessel ``guest:guest`` liefert einen eingeschraenkten
Ausschnitt und reicht zum Ausprobieren.
"""

from __future__ import annotations

import urllib.parse
from datetime import timedelta

from ..config import Settings
from ..models import EconomicEvent, utcnow
from .http import get_json
from .parsing import country_code, importance, parse_number, parse_unit
from .rss import parse_datetime

BASE = "https://api.tradingeconomics.com/calendar"


class TradingEconomicsCalendar:
    name = "tradingeconomics"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def fetch(self, lookahead_hours: int) -> list[EconomicEvent]:
        now = utcnow()
        until = now + timedelta(hours=lookahead_hours)
        params = urllib.parse.urlencode({
            "c": self.settings.te_key or "guest:guest",
            "d1": now.strftime("%Y-%m-%d"),
            "d2": until.strftime("%Y-%m-%d"),
            "f": "json",
        })
        rows = get_json(f"{BASE}?{params}", timeout=self.settings.http_timeout)
        if not isinstance(rows, list):
            return []

        events: list[EconomicEvent] = []
        for row in rows:
            when = parse_datetime(str(row.get("Date", "")))
            if when is None or not (now - timedelta(hours=6) <= when <= until):
                continue
            title = (row.get("Event") or row.get("Category") or "").strip()
            if not title:
                continue
            events.append(EconomicEvent(
                title=title,
                country=country_code(row.get("Country", "")),
                currency=(row.get("Currency") or "").strip().upper(),
                when=when,
                importance=importance(row.get("Importance")),
                forecast=parse_number(row.get("Forecast")) or parse_number(row.get("TEForecast")),
                previous=parse_number(row.get("Previous")),
                actual=parse_number(row.get("Actual")),
                unit=parse_unit(row.get("Unit") or row.get("Forecast")),
                source="tradingeconomics",
            ))
        return sorted(events, key=lambda e: e.when)
