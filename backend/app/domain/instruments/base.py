"""The instrument-catalog abstraction.

Callers (broker adapters, the execution engine, market-data routes) depend on this
interface — never on `InstrumentRegistry`, and never on the `INSTRUMENTS` singleton.
That is what lets the seeded registry be swapped for a broker-refreshed or DB-backed
catalog later without touching a single caller, and lets tests inject a two-symbol
catalog instead of the full seed.

Only the questions a caller actually asks live here. Building a catalog (`register`)
is deliberately *not* part of the interface: consumers read, they do not mutate.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from app.core.enums import BrokerID
from app.domain.instruments.instrument import Instrument


class InstrumentCatalog(ABC):
    """Read-only lookup of what a symbol is and how each venue spells it."""

    @abstractmethod
    def get(self, symbol: str) -> Optional[Instrument]:
        """The instrument, or None when the catalog has never heard of `symbol`."""

    @abstractmethod
    def require(self, symbol: str) -> Instrument:
        """Like `get`, but raises `UnknownInstrument` — the order path must not guess."""

    @abstractmethod
    def all(self) -> List[Instrument]:
        """Every instrument in the catalog."""

    @abstractmethod
    def symbol_for(self, symbol: str, broker: BrokerID) -> str:
        """The broker's own notation, e.g. BTCUSDT → BTC/USD at Alpaca.

        Raises `InstrumentViolation("not_listed")` when the broker does not list it.
        """

    @abstractmethod
    def category_for(self, symbol: str, broker: BrokerID) -> str:
        """The broker's product bucket ("spot"/"linear" at Bybit), or "" if it has none."""

    @abstractmethod
    def symbols_on(self, broker: BrokerID) -> List[str]:
        """Every broker-notation symbol routable to `broker`."""
