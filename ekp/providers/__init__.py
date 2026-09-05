"""Datenquellen fuer Kalendertermine und Nachrichten."""

from __future__ import annotations

from ..config import Settings
from .base import CalendarProvider, NewsProvider


def build_calendar_provider(settings: Settings) -> CalendarProvider:
    name = (settings.calendar_provider or "demo").lower()
    if settings.offline or name == "demo":
        from .demo import DemoCalendarProvider
        return DemoCalendarProvider()
    if name in ("tradingeconomics", "te"):
        from .tradingeconomics import TradingEconomicsCalendar
        return TradingEconomicsCalendar(settings)
    if name == "fmp":
        from .fmp import FMPCalendar
        return FMPCalendar(settings)
    raise ValueError(f"Unbekannter Kalender-Provider: {settings.calendar_provider}")


def build_news_provider(settings: Settings) -> NewsProvider:
    name = (settings.news_provider or "rss").lower()
    if settings.offline or name == "demo":
        from .demo import DemoNewsProvider
        return DemoNewsProvider()
    if name == "rss":
        from .rss import RSSNewsProvider
        return RSSNewsProvider(settings)
    if name == "newsapi":
        from .newsapi import NewsAPIProvider
        return NewsAPIProvider(settings)
    raise ValueError(f"Unbekannter Nachrichten-Provider: {settings.news_provider}")
