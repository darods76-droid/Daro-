#!/usr/bin/env python3
"""Startpunkt fuer ForexWatch.

    python run.py                  Weboberflaeche starten
    python run.py --scan           einen einzelnen Scan im Terminal ausgeben
    python run.py --backtest EURUSD  Signallogik historisch pruefen
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(name)-20s  %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def _single_scan() -> int:
    from forexwatch.engine import Engine

    engine = Engine()
    setups = await engine.scan()
    print()
    print(f"{'Paar':8s} {'Zustand':12s} {'Bereit':>7s} {'Richtung':>9s} {'Vertrauen':>10s}  Hinweise")
    print("-" * 100)
    for setup in setups:
        top = sorted(setup.hits, key=lambda h: h.readiness * h.weight, reverse=True)[:2]
        reasons = "; ".join(h.label for h in top) or "-"
        print(
            f"{setup.symbol:8s} {setup.state:12s} {setup.readiness:7.1f} "
            f"{setup.direction:+9.1f} {setup.confidence:10.1f}  {reasons}"
        )
    await engine.stop()
    return 0


async def _run_backtest(symbol: str, timeframe: str, bars: int) -> int:
    import json

    from forexwatch.backtest import run_backtest
    from forexwatch.config import settings
    from forexwatch.providers import get_provider

    provider = get_provider()
    series_by_tf = {}
    for tf in settings.timeframes:
        count = bars if tf == timeframe else max(400, bars // 4)
        series = await provider.fetch(symbol, tf, count)
        if len(series) >= 60:
            series_by_tf[tf] = series
    await provider.close()

    if timeframe not in series_by_tf:
        print(f"Zu wenige Kursdaten fuer {symbol} ({timeframe})", file=sys.stderr)
        return 1

    result = run_backtest(series_by_tf, symbol, timeframe)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ForexWatch")
    parser.add_argument("--scan", action="store_true", help="einen Scan ausgeben und beenden")
    parser.add_argument("--backtest", metavar="PAAR", help="Signallogik historisch pruefen")
    parser.add_argument("--timeframe", default="", help="Timeframe fuer den Backtest")
    parser.add_argument("--bars", type=int, default=3000, help="Kerzen fuer den Backtest")
    parser.add_argument("--host", default="", help="Adresse der Weboberflaeche")
    parser.add_argument("--port", type=int, default=0, help="Port der Weboberflaeche")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    _setup_logging(args.verbose)
    from forexwatch.config import settings

    if args.scan:
        return asyncio.run(_single_scan())
    if args.backtest:
        timeframe = (args.timeframe or settings.execution_timeframe).lower()
        return asyncio.run(_run_backtest(args.backtest.upper(), timeframe, args.bars))

    import uvicorn

    host = args.host or settings.host
    port = args.port or settings.port
    print(f"\n  ForexWatch laeuft auf  http://{host}:{port}\n")
    uvicorn.run("forexwatch.app:app", host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
