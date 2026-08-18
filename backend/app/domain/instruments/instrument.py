"""Canonical instrument definition + order conformance.

An `Instrument` is the single source of truth for what a tradable symbol *is*: which
venues list it and under what name, how finely its price and quantity may be sliced,
the smallest order it will accept, and whether it is spot or a perpetual future.

Pure domain: no DB, no FastAPI, no broker SDKs. `conform_order` is a pure function so
the execution engine, the backtester, and any future order path all round and validate
identically instead of each inventing its own rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from enum import Enum
from typing import Mapping, Optional, Tuple, Union

from app.core.enums import BrokerID, MarketType


class InstrumentKind(str, Enum):
    """What you actually hold when the order fills.

    SPOT — you own the asset (cash equity, crypto spot). No funding, no liquidation.
    PERP — a perpetual future: margined, pays/receives funding, can be liquidated.

    This is the axis `MarketType` does not capture: BTCUSDT spot and BTCUSDT perp are
    the same market type but two different things to own.
    """
    SPOT = "spot"
    PERP = "perp"


# ── Errors ─────────────────────────────────────────────────────────────────────────

class InstrumentError(Exception):
    """Base for every instrument-registry failure."""


class UnknownInstrument(InstrumentError):
    """A symbol reached the order path that the registry has never heard of.

    Deliberately fatal: guessing an unknown symbol's tick size or venue is how orders
    get routed to the wrong product.
    """

    def __init__(self, symbol: str) -> None:
        super().__init__(
            f"Unknown instrument '{symbol}'. Add it to app/domain/instruments/seed.py "
            f"or check the symbol."
        )
        self.symbol = symbol


class InstrumentViolation(InstrumentError):
    """An order breaks one of the instrument's own rules (`rule` names which)."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


# ── Model ──────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class VenueListing:
    """How one broker refers to — and buckets — an instrument.

    `category` is the broker's own product bucket. Bybit needs it on every call
    ("spot" vs "linear"); the other adapters ignore it.
    """
    symbol: str
    category: str = ""


@dataclass(frozen=True)
class Instrument:
    symbol: str                 # canonical internal symbol — the only form the app stores
    base: str
    quote: str
    market_type: MarketType
    kind: InstrumentKind
    tick_size: float            # minimum price increment
    lot_step: float             # minimum quantity increment
    min_qty: float              # smallest tradable quantity
    min_notional: float         # smallest tradable qty * price * multiplier
    multiplier: float = 1.0     # contract size; 1.0 for spot and crypto perps
    venues: Mapping[BrokerID, VenueListing] = field(default_factory=dict)

    def listing(self, broker: BrokerID) -> Optional[VenueListing]:
        return self.venues.get(broker)

    def is_tradable_on(self, broker: BrokerID) -> bool:
        return broker in self.venues


# ── Quantization ───────────────────────────────────────────────────────────────────
#
# Decimal, not float: `0.1 + 0.2` is 0.30000000000000004, and flooring that against a
# 0.001 lot step in binary float can silently shave a whole step off the order.

def _dec(value: float) -> Decimal:
    return Decimal(str(value))


def floor_to_step(value: float, step: float) -> float:
    """Largest multiple of `step` that is <= `value`."""
    if step <= 0:
        return value
    d_step = _dec(step)
    return float((_dec(value) / d_step).quantize(Decimal("1"), rounding=ROUND_DOWN) * d_step)


def round_to_tick(value: float, tick: float) -> float:
    """Nearest multiple of `tick`."""
    if tick <= 0:
        return value
    d_tick = _dec(tick)
    return float((_dec(value) / d_tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * d_tick)


def conform_order(
    instrument: Instrument,
    *,
    quantity: float,
    price: Optional[float] = None,
    broker: Union[BrokerID, str, None] = None,
) -> Tuple[float, Optional[float]]:
    """Snap an order to the instrument's grid and validate it, or raise.

    Quantity is **floored** to the lot step, never rounded up: sizing already computed
    the largest quantity the risk cap allows, and rounding up would push the order over
    it (RiskManager would then veto a legitimate entry).

    `broker` is checked only when it names a broker the registry knows — the simulated
    paper adapter has no venue constraints.

    Returns the conformed `(quantity, price)`. Raises `InstrumentViolation` if the
    order cannot be made valid.
    """
    venue = _as_broker(broker)
    if venue is not None and not instrument.is_tradable_on(venue):
        raise InstrumentViolation(
            "not_listed",
            f"{instrument.symbol} is not listed on {venue.value}",
        )

    qty = floor_to_step(quantity, instrument.lot_step)
    if qty < instrument.min_qty:
        raise InstrumentViolation(
            "min_qty",
            f"quantity {quantity:g} → {qty:g} is below {instrument.symbol}'s "
            f"minimum of {instrument.min_qty:g}",
        )

    conformed_price = round_to_tick(price, instrument.tick_size) if price is not None else None

    if conformed_price is not None and instrument.min_notional > 0:
        notional = qty * conformed_price * instrument.multiplier
        if notional < instrument.min_notional:
            raise InstrumentViolation(
                "min_notional",
                f"notional {notional:,.2f} is below {instrument.symbol}'s "
                f"minimum of {instrument.min_notional:,.2f}",
            )

    return qty, conformed_price


def _as_broker(broker: Union[BrokerID, str, None]) -> Optional[BrokerID]:
    """BrokerID for a known broker, else None (paper/simulated ids land here)."""
    if isinstance(broker, BrokerID):
        return broker
    if isinstance(broker, str):
        try:
            return BrokerID(broker.lower())
        except ValueError:
            return None
    return None
