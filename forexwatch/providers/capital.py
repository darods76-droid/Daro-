"""Capital.com als Datenquelle.

Capital.com stellt eine REST-Schnittstelle bereit, die Kerzen fuer alle
handelbaren Maerkte liefert. Anders als bei Yahoo sind das die Kurse, zu
denen tatsaechlich gehandelt wird – inklusive Geld- und Briefkurs, woraus
sich der Spread direkt ablesen laesst.

Zugang
------
Benoetigt werden drei Angaben aus dem Capital.com-Konto:

    FW_CAPITAL_API_KEY       Einstellungen -> API-Schluessel
    FW_CAPITAL_IDENTIFIER    die E-Mail-Adresse des Kontos
    FW_CAPITAL_PASSWORD      das API-Passwort (nicht das Login-Passwort)

Mit ``FW_CAPITAL_DEMO=1`` laeuft alles gegen das Demokonto. Fehlt eine der
Angaben, weicht die App selbsttaetig auf Yahoo aus.

Anmeldung
---------
Ein Aufruf von ``POST /session`` liefert zwei Kopfzeilen (``CST`` und
``X-SECURITY-TOKEN``), die jede weitere Anfrage mitfuehren muss. Die
Sitzung laeuft nach etwa zehn Minuten Untaetigkeit ab und wird bei Bedarf
automatisch erneuert.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from ..config import settings
from ..models import Candle, Series
from .base import DataProvider, resample, timeframe_seconds

log = logging.getLogger("forexwatch.capital")

LIVE_URL = "https://api-capital.backend-capital.com/api/v1"
DEMO_URL = "https://demo-api-capital.backend-capital.com/api/v1"

# Interner Timeframe -> Aufloesung bei Capital.com
RESOLUTIONS = {
    "1m": "MINUTE",
    "5m": "MINUTE_5",
    "15m": "MINUTE_15",
    "30m": "MINUTE_30",
    "1h": "HOUR",
    "4h": "HOUR_4",
    "1d": "DAY",
    "1w": "WEEK",
}

# Instrumente, deren Kuerzel bei Capital.com anders heisst
EPIC_OVERRIDES = {
    "XAUUSD": "GOLD",
    "XAGUSD": "SILVER",
    "DXY": "DXY",
    "WTI": "OIL_CRUDE",
    "SPX": "US500",
    "NDX": "US100",
    "DAX": "DE40",
}

# Hoechstzahl Kerzen je Anfrage laut Schnittstelle
MAX_PER_REQUEST = 1000

# Die Sitzung gilt zehn Minuten; etwas frueher erneuern.
SESSION_TTL = 8 * 60


def to_epic(symbol: str) -> str:
    """Internes Kuerzel in ein Capital.com-Epic uebersetzen."""
    key = symbol.upper().replace("/", "")
    return EPIC_OVERRIDES.get(key, key)


class CapitalProvider(DataProvider):
    name = "capital"
    native_timeframes = ("1m", "5m", "15m", "30m", "1h", "4h", "1d")

    def __init__(
        self,
        api_key: str | None = None,
        identifier: str | None = None,
        password: str | None = None,
        demo: bool | None = None,
    ) -> None:
        self._key = api_key if api_key is not None else settings.capital_api_key
        self._identifier = identifier if identifier is not None else settings.capital_identifier
        self._password = password if password is not None else settings.capital_password
        self._demo = settings.capital_demo if demo is None else demo
        self.base_url = DEMO_URL if self._demo else LIVE_URL

        self._client: httpx.AsyncClient | None = None
        self._cst: str = ""
        self._token: str = ""
        self._authenticated_at: float = 0.0
        self._auth_lock = asyncio.Lock()
        # Die Schnittstelle erlaubt rund zehn Anfragen je Sekunde. Vier
        # gleichzeitige Abrufe bleiben sicher darunter.
        self._gate = asyncio.Semaphore(4)

    @property
    def configured(self) -> bool:
        return bool(self._key and self._identifier and self._password)

    # -- Verbindung --------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(25.0),
                follow_redirects=True,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
        return self._client

    async def _ensure_session(self, force: bool = False) -> bool:
        """Anmelden bzw. die Sitzung erneuern. Liefert, ob ein Zugang besteht."""
        if not self.configured:
            return False
        if not force and self._cst and (time.time() - self._authenticated_at) < SESSION_TTL:
            return True

        async with self._auth_lock:
            # Ein zweiter Aufrufer koennte inzwischen angemeldet haben
            if not force and self._cst and (time.time() - self._authenticated_at) < SESSION_TTL:
                return True

            client = await self._get_client()
            try:
                response = await client.post(
                    "/session",
                    headers={"X-CAP-API-KEY": self._key},
                    json={
                        "identifier": self._identifier,
                        "password": self._password,
                        "encryptedPassword": False,
                    },
                )
            except Exception as exc:
                log.warning("Capital.com nicht erreichbar: %s", exc)
                return False

            if response.status_code != 200:
                # Zugangsdaten oder Schluessel stimmen nicht – das laesst
                # sich durch Wiederholen nicht beheben.
                log.error(
                    "Anmeldung bei Capital.com fehlgeschlagen (%s): %s",
                    response.status_code,
                    response.text[:200],
                )
                self._cst = self._token = ""
                return False

            self._cst = response.headers.get("CST", "")
            self._token = response.headers.get("X-SECURITY-TOKEN", "")
            self._authenticated_at = time.time()
            if not (self._cst and self._token):
                log.error("Capital.com lieferte keine Sitzungsmerkmale zurueck")
                return False

            account = ""
            try:
                account = response.json().get("currentAccountId", "")
            except Exception:
                pass
            log.info(
                "Bei Capital.com angemeldet (%s%s)",
                "Demokonto" if self._demo else "Echtgeldkonto",
                f", Konto {account}" if account else "",
            )
            return True

    def _auth_headers(self) -> dict[str, str]:
        return {
            "X-CAP-API-KEY": self._key,
            "CST": self._cst,
            "X-SECURITY-TOKEN": self._token,
        }

    # -- Kerzen ------------------------------------------------------------

    async def fetch(self, symbol: str, timeframe: str, limit: int = 500) -> Series:
        if not self.configured:
            log.warning("Capital.com ohne Zugangsdaten aufgerufen – leere Reihe")
            return Series(symbol.upper(), timeframe, [])

        source_tf, factor = self._source_timeframe(timeframe, self.native_timeframes)
        resolution = RESOLUTIONS.get(source_tf, "HOUR")
        needed = limit * max(1, factor)

        candles = await self._load(symbol, resolution, source_tf, needed)
        series = Series(symbol.upper(), source_tf, candles)
        if factor > 1 or timeframe.lower() != source_tf:
            series = resample(series, timeframe.lower())
        if len(series.candles) > limit:
            series.candles = series.candles[-limit:]
        return series

    async def _load(
        self, symbol: str, resolution: str, source_tf: str, needed: int
    ) -> list[Candle]:
        """Kerzen holen, bei Bedarf ueber mehrere Anfragen hinweg.

        Die Schnittstelle gibt hoechstens 1000 Kerzen je Aufruf heraus. Fuer
        laengere Historien wird rueckwaerts in Zeitfenstern geblaettert.
        """
        epic = to_epic(symbol)
        step = timeframe_seconds(source_tf)
        collected: dict[int, Candle] = {}
        end = datetime.now(timezone.utc)

        while len(collected) < needed:
            batch = min(MAX_PER_REQUEST, needed - len(collected) + 50)
            # Grosszuegig zurueckgreifen: an Wochenenden und Feiertagen
            # fehlen Kerzen, sonst bricht die Schleife zu frueh ab.
            start = end - timedelta(seconds=step * batch * 2)

            page = await self._request_prices(epic, resolution, start, end, batch)
            if not page:
                break

            before = len(collected)
            for candle in page:
                collected[candle.ts] = candle
            if len(collected) == before:
                break  # keine neuen Kerzen mehr – Historie erschoepft

            end = datetime.fromtimestamp(min(collected), tz=timezone.utc)
            if len(page) < batch // 2:
                break  # Quelle liefert sichtbar weniger als moeglich

        return [collected[ts] for ts in sorted(collected)]

    async def _request_prices(
        self, epic: str, resolution: str, start: datetime, end: datetime, limit: int
    ) -> list[Candle]:
        if not await self._ensure_session():
            return []

        params = {
            "resolution": resolution,
            "max": str(min(MAX_PER_REQUEST, limit)),
            "from": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "to": end.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        client = await self._get_client()
        for attempt in range(3):
            async with self._gate:
                try:
                    response = await client.get(
                        f"/prices/{epic}", params=params, headers=self._auth_headers()
                    )
                except Exception as exc:
                    if attempt == 2:
                        log.warning("Kursabruf %s fehlgeschlagen: %s", epic, exc)
                        return []
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue

            if response.status_code == 200:
                return self._parse(response.json())

            if response.status_code in (401, 403):
                # Sitzung abgelaufen -> einmal neu anmelden und erneut versuchen
                log.info("Sitzung bei Capital.com abgelaufen, melde neu an")
                if not await self._ensure_session(force=True):
                    return []
                continue

            if response.status_code == 429:
                await asyncio.sleep(2.0 * (attempt + 1))
                continue

            log.warning(
                "Capital.com meldet %s fuer %s: %s",
                response.status_code, epic, response.text[:160],
            )
            return []
        return []

    @staticmethod
    def _mid(node: dict | None) -> float | None:
        """Mittelkurs aus Geld- und Briefkurs.

        Der Vergleich mit anderen Quellen und saemtliche Indikatoren
        erwarten Mittelkurse. Liegt nur eine Seite vor, wird sie genommen.
        """
        if not isinstance(node, dict):
            return None
        bid, ask = node.get("bid"), node.get("ask")
        if bid is not None and ask is not None:
            return (float(bid) + float(ask)) / 2.0
        if bid is not None:
            return float(bid)
        if ask is not None:
            return float(ask)
        return None

    @classmethod
    def _parse(cls, payload: dict) -> list[Candle]:
        candles: list[Candle] = []
        for row in payload.get("prices", []) or []:
            stamp = row.get("snapshotTimeUTC") or row.get("snapshotTime")
            if not stamp:
                continue
            try:
                text = str(stamp).replace("Z", "+00:00")
                when = datetime.fromisoformat(text)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

            o = cls._mid(row.get("openPrice"))
            h = cls._mid(row.get("highPrice"))
            l = cls._mid(row.get("lowPrice"))
            c = cls._mid(row.get("closePrice"))
            if None in (o, h, l, c):
                continue

            volume = row.get("lastTradedVolume") or 0
            try:
                volume = float(volume)
            except (TypeError, ValueError):
                volume = 0.0

            # Hoch und Tief absichern: einzelne Datensaetze sind gelegentlich
            # inkonsistent, was sonst negative Spannen ergaebe.
            high = max(o, h, l, c)
            low = min(o, h, l, c)
            candles.append(Candle(int(when.timestamp()), o, high, low, c, volume))

        candles.sort(key=lambda x: x.ts)
        return candles

    # -- Zusatzangaben -----------------------------------------------------

    async def spread_pips(self, symbol: str) -> float | None:
        """Aktueller Spread in Pips – Capital.com liefert ihn unmittelbar."""
        if not await self._ensure_session():
            return None
        from ..risk import pip_size

        client = await self._get_client()
        try:
            response = await client.get(
                f"/markets/{to_epic(symbol)}", headers=self._auth_headers()
            )
            if response.status_code != 200:
                return None
            snapshot = response.json().get("snapshot") or {}
            bid, offer = snapshot.get("bid"), snapshot.get("offer")
            if bid is None or offer is None:
                return None
            return abs(float(offer) - float(bid)) / pip_size(symbol)
        except Exception:
            return None

    async def search(self, term: str) -> list[dict]:
        """Instrumente suchen – hilfreich, um das richtige Epic zu finden."""
        if not await self._ensure_session():
            return []
        client = await self._get_client()
        try:
            response = await client.get(
                "/markets", params={"searchTerm": term}, headers=self._auth_headers()
            )
            if response.status_code != 200:
                return []
            return [
                {
                    "epic": m.get("epic"),
                    "name": m.get("instrumentName"),
                    "type": m.get("instrumentType"),
                }
                for m in response.json().get("markets", [])
            ]
        except Exception:
            return []

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
