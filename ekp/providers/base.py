"""Provider-Schnittstellen."""

from __future__ import annotations

from typing import Protocol

from ..models import EconomicEvent, NewsItem


class CalendarProvider(Protocol):
    name: str

    def fetch(self, lookahead_hours: int) -> list[EconomicEvent]:
        """Liefert Termine von jetzt bis ``lookahead_hours`` in die Zukunft."""
        ...


class NewsProvider(Protocol):
    name: str

    def fetch(self, lookback_hours: int) -> list[NewsItem]:
        """Liefert Nachrichten der letzten ``lookback_hours`` Stunden."""
        ...
