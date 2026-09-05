"""Wirtschaftskalender ueber Financial Modeling Prep (benoetigt EKP_FMP_KEY)."""

from __future__ import annotations

import urllib.parse
from datetime import timedelta

from ..config import Settings
from ..models import EconomicEvent, utcnow
from .http import get_json
from .parsing import country_code, importance, parse_number, parse_unit
from .rss import parse_datetime

BASE = "https://financialmodelingprep.com/api/v3/economic_calendar"


class FMPCalendar:
    name = "fmp"

    def __init__(self, settings: Settings) -> None:
        if not settings.fmp_key:
            raise ValueError("EKP_FMP_KEY ist nicht gesetzt.")
        self.settings = settings

    def fetch(self, lookahead_hours: int) -> list[EconomicEvent]:
        now = utcnow()
        until = now + timedelta(hours=lookahead_hours)
        params = urllib.parse.urlencode({
            "from": now.strftime("%Y-%m-%d"),
            "to": until.strftime("%Y-%m-%d"),
            "apikey": self.settings.fmp_key,
        })
        rows = get_json(f"{BASE}?{params}", timeout=self.settings.http_timeout)
        if not isinstance(rows, list):
            return []

        events: list[EconomicEvent] = []
        for row in rows:
            when = parse_datetime(str(row.get("date", "")).replace(" ", "T") + "+00:00")
            if when is None or not (now - timedelta(hours=6) <= when <= until):
                continue
            title = (row.get("event") or "").strip()
            if not title:
                continue
            events.append(EconomicEvent(
                title=title,
                country=country_code(row.get("country", "")),
                currency=(row.get("currency") or "").strip().upper(),
                when=when,
                importance=importance(row.get("impact")),
                forecast=parse_number(row.get("estimate")),
                previous=parse_number(row.get("previous")),
                actual=parse_number(row.get("actual")),
                unit=parse_unit(row.get("unit")),
                source="fmp",
            ))
        return sorted(events, key=lambda e: e.when)
