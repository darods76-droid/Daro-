"""Risiko- und Positionsberechnung.

Ein Signal ohne Stop, Ziel und Positionsgroesse ist keine Handelsidee,
sondern nur eine Meinung. Dieses Modul rechnet aus einem erkannten Setup
konkrete Niveaus und eine zum Kontorisiko passende Losgroesse.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Levels

# Waehrungspaare mit JPY haben zwei statt vier Nachkommastellen im Pip
JPY_PIP = 0.01
STANDARD_PIP = 0.0001
METAL_PIP = 0.1


def pip_size(symbol: str) -> float:
    """Groesse eines Pips fuer das Instrument."""
    key = symbol.upper()
    if key.startswith(("XAU", "XAG")):
        return METAL_PIP
    if key.endswith("JPY") or "JPY" in key[3:]:
        return JPY_PIP
    return STANDARD_PIP


def to_pips(symbol: str, distance: float) -> float:
    """Preisabstand in Pips umrechnen."""
    size = pip_size(symbol)
    return abs(distance) / size if size else 0.0


def build_levels(
    symbol: str,
    price: float,
    atr: float,
    bias: str,
    trigger_long: float,
    trigger_short: float,
    stop_atr: float = 1.2,
    rr_target: float = 1.8,
) -> Levels:
    """Ein- und Ausstiegsniveaus aus Ausbruchsmarke und ATR ableiten.

    Der Stop liegt bewusst hinter der gegenueberliegenden Seite der
    Kompressionszone bzw. mindestens ``stop_atr`` ATR entfernt – enger
    gesetzte Stops werden beim Ausbruch regelmaessig abgeholt.
    """
    atr = atr if atr > 0 else max(price * 0.0006, 1e-6)

    if bias == "short":
        entry = trigger_short
        # Stop oberhalb der Zone, mindestens stop_atr entfernt
        stop = max(trigger_long, entry + atr * stop_atr)
        risk = abs(stop - entry)
        tp1 = entry - risk * rr_target
        tp2 = entry - risk * rr_target * 1.8
    else:
        entry = trigger_long
        stop = min(trigger_short, entry - atr * stop_atr)
        risk = abs(entry - stop)
        tp1 = entry + risk * rr_target
        tp2 = entry + risk * rr_target * 1.8

    rr = (abs(tp1 - entry) / risk) if risk > 0 else 0.0
    digits = 3 if pip_size(symbol) >= JPY_PIP else 5
    return Levels(
        entry=round(entry, digits),
        stop=round(stop, digits),
        take_profit_1=round(tp1, digits),
        take_profit_2=round(tp2, digits),
        trigger_long=round(trigger_long, digits),
        trigger_short=round(trigger_short, digits),
        atr=round(atr, digits + 1),
        rr=round(rr, 2),
    )


@dataclass(slots=True)
class PositionPlan:
    risk_amount: float
    risk_pips: float
    lots: float
    units: float
    pip_value: float
    account_currency: str
    approximated: bool
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "risk_amount": round(self.risk_amount, 2),
            "risk_pips": round(self.risk_pips, 1),
            "lots": round(self.lots, 2),
            "units": int(self.units),
            "pip_value": round(self.pip_value, 4),
            "account_currency": self.account_currency,
            "approximated": self.approximated,
            "note": self.note,
        }


def _convert(amount: float, frm: str, to: str, rates: dict[str, float]) -> float | None:
    """Betrag von einer Waehrung in eine andere umrechnen.

    Zuerst wird ein direktes Paar gesucht, danach der Weg ueber den
    US-Dollar. Letzteres ist der Normalfall: fuer USDJPY liegt selten ein
    JPY/EUR-Kurs vor, wohl aber USDJPY und EURUSD.
    """
    if frm == to:
        return amount

    def direct(a: str, b: str) -> float | None:
        rate = rates.get(f"{a}{b}")
        if rate:
            return rate
        inverse = rates.get(f"{b}{a}")
        if inverse:
            return 1.0 / inverse
        return None

    rate = direct(frm, to)
    if rate is not None:
        return amount * rate

    # Umweg ueber den US-Dollar
    if "USD" not in (frm, to):
        first = direct(frm, "USD")
        second = direct("USD", to)
        if first is not None and second is not None:
            return amount * first * second
    return None


def pip_value_per_lot(
    symbol: str, price: float, account_currency: str, rates: dict[str, float] | None = None
) -> tuple[float, bool]:
    """Wert eines Pips je Standardlot in Kontowaehrung.

    Rueckgabe: (Wert, ob geschaetzt). Laesst sich der Kurs weder direkt noch
    ueber den US-Dollar ermitteln, wird der Wert in der Kurswaehrung
    zurueckgegeben und als Naeherung gekennzeichnet.
    """
    rates = dict(rates or {})
    symbol = symbol.upper()
    quote = symbol[3:6] if len(symbol) >= 6 else "USD"
    lot_units = 100_000.0
    if symbol.startswith(("XAU", "XAG")):
        lot_units = 100.0  # ein Lot Gold sind 100 Unzen
        quote = "USD"

    # Der eigene Kurs ist selbst eine Umrechnungsquelle.
    rates.setdefault(symbol, price)

    value_in_quote = pip_size(symbol) * lot_units
    converted = _convert(value_in_quote, quote, account_currency, rates)
    if converted is not None:
        return converted, False
    return value_in_quote, True


def position_plan(
    symbol: str,
    entry: float,
    stop: float,
    balance: float,
    risk_percent: float,
    account_currency: str = "EUR",
    rates: dict[str, float] | None = None,
) -> PositionPlan:
    """Losgroesse, bei der ein ausgeloester Stop genau `risk_percent` kostet."""
    risk_amount = balance * (risk_percent / 100.0)
    risk_pips = to_pips(symbol, entry - stop)
    value, approximated = pip_value_per_lot(symbol, entry, account_currency, rates)

    if risk_pips <= 0 or value <= 0:
        return PositionPlan(
            risk_amount, risk_pips, 0.0, 0.0, value, account_currency, approximated,
            "Stopabstand ist null – keine Positionsgroesse berechenbar",
        )

    lots = risk_amount / (risk_pips * value)
    lot_units = 100.0 if symbol.upper().startswith(("XAU", "XAG")) else 100_000.0
    note = ""
    if approximated:
        note = (
            f"Pip-Wert in {symbol[3:6]} angegeben – ohne Wechselkurs nach "
            f"{account_currency} ist die Groesse eine Naeherung"
        )
    return PositionPlan(
        risk_amount=risk_amount,
        risk_pips=risk_pips,
        lots=max(0.0, lots),
        units=max(0.0, lots * lot_units),
        pip_value=value,
        account_currency=account_currency,
        approximated=approximated,
        note=note,
    )
