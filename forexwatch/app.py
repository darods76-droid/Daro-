"""Weboberflaeche und JSON-Schnittstelle."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .analysis import sessions
from .backtest import run_backtest
from .calendar import calendar
from .config import WEB_DIR, settings
from .engine import Engine
from .risk import position_plan

log = logging.getLogger("forexwatch.app")

engine = Engine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await engine.start()
    try:
        yield
    finally:
        await engine.stop()


app = FastAPI(
    title="ForexWatch",
    description="Marktbeobachtung und Fruehwarnsystem fuer den Devisenmarkt",
    version="1.0.0",
    lifespan=lifespan,
)


# --------------------------------------------------------------------------
# Oberflaeche
# --------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


# --------------------------------------------------------------------------
# Zustand und Setups
# --------------------------------------------------------------------------


@app.get("/api/status")
async def api_status() -> dict[str, Any]:
    return engine.status()


@app.get("/api/setups")
async def api_setups(
    state: str | None = Query(None, description="Nur diesen Zustand liefern"),
    min_readiness: float = Query(0.0, ge=0.0, le=100.0),
) -> dict[str, Any]:
    setups = engine.setups
    if state:
        wanted = state.upper()
        setups = [s for s in setups if s.state == wanted]
    if min_readiness > 0:
        setups = [s for s in setups if s.readiness >= min_readiness]
    return {
        "count": len(setups),
        "last_scan": engine.last_scan,
        "setups": [s.to_dict() for s in setups],
    }


@app.get("/api/setup/{symbol}")
async def api_setup(symbol: str) -> dict[str, Any]:
    setup = engine.setup(symbol)
    if not setup:
        raise HTTPException(404, f"Keine Bewertung fuer {symbol.upper()} vorhanden")
    return setup.to_dict()


@app.get("/api/candles/{symbol}")
async def api_candles(
    symbol: str,
    timeframe: str = Query(default="", alias="tf"),
    limit: int = Query(200, ge=20, le=1000),
) -> dict[str, Any]:
    """Kerzen samt der wichtigsten Indikatorlinien fuer den Chart."""
    timeframe = (timeframe or settings.execution_timeframe).lower()
    series = engine.series(symbol, timeframe)
    if not series or len(series) < 5:
        raise HTTPException(404, f"Keine Kursdaten fuer {symbol.upper()} ({timeframe})")

    features = engine.features(symbol, timeframe)
    candles = series.candles[-limit:]
    offset = len(series.candles) - len(candles)

    def tail(values: list | None) -> list:
        return list(values[offset:]) if values else []

    payload: dict[str, Any] = {
        "symbol": series.symbol,
        "timeframe": timeframe,
        "candles": [c.to_dict() for c in candles],
    }
    if features:
        payload["indicators"] = {
            "ema20": tail(features.ema20),
            "ema50": tail(features.ema50),
            "bb_upper": tail(features.bb_upper),
            "bb_lower": tail(features.bb_lower),
            "kc_upper": tail(features.kc_upper),
            "kc_lower": tail(features.kc_lower),
            "rsi": tail(features.rsi14),
            "atr": tail(features.atr14),
            "squeeze": tail(features.squeeze_on),
        }
    setup = engine.setup(symbol)
    if setup and setup.levels:
        payload["levels"] = setup.levels.to_dict()
    return payload


# --------------------------------------------------------------------------
# Kalender, Sessions, Alarme
# --------------------------------------------------------------------------


@app.get("/api/calendar")
async def api_calendar(
    hours: int = Query(48, ge=1, le=336),
    impact: str = Query("mittel", pattern="^(niedrig|mittel|hoch)$"),
    symbol: str | None = None,
) -> dict[str, Any]:
    await calendar.refresh()
    events = (
        calendar.for_symbol(symbol, hours, impact)
        if symbol
        else calendar.upcoming(hours, impact)
    )
    return {"source": calendar.source, "count": len(events), "events": [e.to_dict() for e in events]}


@app.get("/api/sessions")
async def api_sessions() -> dict[str, Any]:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    name, minutes = sessions.next_key_moment(now)
    return {
        "now": now.isoformat(),
        "label": sessions.session_label(now),
        "active": sessions.active_sessions(now),
        "factor": sessions.session_volatility_factor(now),
        "market_open": not sessions.is_weekend(now),
        "next_moment": {"name": name, "minutes": minutes},
        "windows": {
            name: {"start_utc": s, "end_utc": e, "weight": w}
            for name, (s, e, w) in sessions.SESSIONS.items()
        },
    }


@app.get("/api/alerts")
async def api_alerts(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    return {"alerts": engine.storage.recent_alerts(limit)}


@app.get("/api/history/{symbol}")
async def api_history(symbol: str, limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
    return {"history": engine.storage.setup_history(symbol, limit)}


# --------------------------------------------------------------------------
# Werkzeuge
# --------------------------------------------------------------------------


@app.post("/api/scan")
async def api_scan() -> dict[str, Any]:
    """Einen Scan ausserhalb des Zeitplans anstossen."""
    setups = await engine.scan()
    return {"count": len(setups), "setups": [s.to_dict() for s in setups]}


@app.get("/api/position")
async def api_position(
    symbol: str,
    entry: float,
    stop: float,
    balance: float | None = None,
    risk_percent: float | None = None,
    currency: str | None = None,
) -> dict[str, Any]:
    """Positionsgroesse fuer ein Setup berechnen."""
    if entry == stop:
        raise HTTPException(400, "Einstieg und Stop duerfen nicht identisch sein")

    # Aktuelle Kurse als Umrechnungsbasis fuer den Pip-Wert mitgeben
    rates: dict[str, float] = {}
    for setup in engine.setups:
        rates[setup.symbol] = setup.price

    plan = position_plan(
        symbol=symbol.upper(),
        entry=entry,
        stop=stop,
        balance=balance if balance is not None else settings.account_balance,
        risk_percent=risk_percent if risk_percent is not None else settings.risk_percent,
        account_currency=(currency or settings.account_currency).upper(),
        rates=rates,
    )
    return plan.to_dict()


@app.get("/api/backtest/{symbol}")
async def api_backtest(
    symbol: str,
    timeframe: str = Query(default="", alias="tf"),
    horizon: int = Query(12, ge=3, le=60),
    bars: int = Query(3000, ge=400, le=12000),
) -> dict[str, Any]:
    """Die Signallogik ueber die Historie pruefen.

    Laeuft in einem Arbeitsthread, damit der Scanner waehrenddessen nicht
    blockiert wird.
    """
    symbol = symbol.upper()
    timeframe = (timeframe or settings.execution_timeframe).lower()

    series_by_tf = {}
    for tf in settings.timeframes:
        count = bars if tf == timeframe else max(400, bars // 4)
        try:
            series = await engine.provider.fetch(symbol, tf, count)
        except Exception as exc:
            raise HTTPException(502, f"Kursdaten fuer {symbol} nicht abrufbar: {exc}") from exc
        if len(series) >= 60:
            series_by_tf[tf] = series

    if timeframe not in series_by_tf:
        raise HTTPException(404, f"Zu wenige Kursdaten fuer {symbol} ({timeframe})")

    try:
        result = await asyncio.to_thread(
            run_backtest, series_by_tf, symbol, timeframe, horizon
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result.to_dict()


# --------------------------------------------------------------------------
# Live-Verbindung
# --------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(socket: WebSocket) -> None:
    await socket.accept()
    queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(maxsize=32)

    async def receive(event: str, payload: dict[str, Any]) -> None:
        try:
            queue.put_nowait((event, payload))
        except asyncio.QueueFull:
            pass  # langsame Verbindung: lieber verwerfen als den Scanner bremsen

    engine.subscribe(receive)
    try:
        await socket.send_json(
            {
                "event": "snapshot",
                "payload": {
                    "status": engine.status(),
                    "setups": [s.to_dict() for s in engine.setups],
                },
            }
        )
        while True:
            event, payload = await queue.get()
            await socket.send_json({"event": event, "payload": payload})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.debug("WebSocket beendet: %s", exc)
    finally:
        engine.unsubscribe(receive)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
