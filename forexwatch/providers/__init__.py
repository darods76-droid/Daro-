"""Marktdatenquellen."""

from __future__ import annotations

import logging

from ..config import settings
from .base import DataProvider
from .capital import CapitalProvider
from .synthetic import SyntheticProvider
from .twelvedata import TwelveDataProvider
from .yahoo import YahooProvider

log = logging.getLogger("forexwatch.providers")

_REGISTRY: dict[str, type[DataProvider]] = {
    "capital": CapitalProvider,
    "yahoo": YahooProvider,
    "twelvedata": TwelveDataProvider,
    "synthetic": SyntheticProvider,
}


def resolve_name(name: str | None = None) -> str:
    """Welche Quelle soll genutzt werden?

    ``auto`` waehlt Capital.com, sobald die Zugangsdaten hinterlegt sind,
    und faellt sonst auf Yahoo zurueck. So laeuft die App ohne jede
    Einrichtung, nutzt aber die Broker-Kurse, sobald sie verfuegbar sind.
    """
    key = (name or settings.provider).lower()

    if key == "auto":
        return "capital" if settings.capital_ready else "yahoo"

    if key == "capital" and not settings.capital_ready:
        log.warning(
            "Capital.com ist ausgewaehlt, aber es fehlen Zugangsdaten "
            "(FW_CAPITAL_API_KEY, FW_CAPITAL_IDENTIFIER, FW_CAPITAL_PASSWORD) "
            "– es wird Yahoo genutzt."
        )
        return "yahoo"

    if key == "twelvedata" and not settings.twelvedata_key:
        log.warning("TwelveData ohne Schluessel ausgewaehlt – es wird Yahoo genutzt.")
        return "yahoo"

    if key not in _REGISTRY:
        log.warning("Unbekannte Datenquelle %r – es wird Yahoo genutzt.", key)
        return "yahoo"

    return key


def get_provider(name: str | None = None) -> DataProvider:
    """Datenquelle erzeugen."""
    return _REGISTRY[resolve_name(name)]()


__all__ = [
    "DataProvider",
    "get_provider",
    "resolve_name",
    "CapitalProvider",
    "YahooProvider",
    "TwelveDataProvider",
    "SyntheticProvider",
]
