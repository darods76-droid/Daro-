"""Marktdatenquellen."""

from __future__ import annotations

from ..config import settings
from .base import DataProvider
from .synthetic import SyntheticProvider
from .twelvedata import TwelveDataProvider
from .yahoo import YahooProvider

_REGISTRY: dict[str, type[DataProvider]] = {
    "yahoo": YahooProvider,
    "twelvedata": TwelveDataProvider,
    "synthetic": SyntheticProvider,
}


def get_provider(name: str | None = None) -> DataProvider:
    """Provider nach Namen erzeugen; unbekannte Namen fallen auf Yahoo zurueck."""
    key = (name or settings.provider).lower()
    cls = _REGISTRY.get(key, YahooProvider)
    if cls is TwelveDataProvider and not settings.twelvedata_key:
        # Ohne Schluessel waere der Provider nutzlos – lieber sauber ausweichen.
        cls = YahooProvider
    return cls()


__all__ = ["DataProvider", "get_provider", "YahooProvider", "TwelveDataProvider", "SyntheticProvider"]
