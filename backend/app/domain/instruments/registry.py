"""Instrument lookup — canonical symbol in, `Instrument` out.

Callers depend on `InstrumentRegistry`, not on the module-level `INSTRUMENTS` singleton,
so a test (or a future broker-refreshed source) can inject its own set.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from app.core.enums import BrokerID
from app.domain.instruments.base import InstrumentCatalog
from app.domain.instruments.instrument import (
    Instrument,
    InstrumentViolation,
    UnknownInstrument,
)


def normalize_symbol(symbol: str) -> str:
    """Lookup key: case-, whitespace- and separator-insensitive.

    BTC/USD, btc-usd and BTCUSD all collapse onto the same key so a user (or a broker
    response) may use any common notation.
    """
    return symbol.strip().upper().replace("/", "").replace("-", "").replace("_", "")


class InstrumentRegistry(InstrumentCatalog):
    """In-memory `InstrumentCatalog`: canonical symbol → `Instrument`, plus per-broker
    symbol translation.

    Two lookup layers, in priority order:

    1. **Canonical** — the instrument's own `symbol`. Authoritative, never shadowed.
    2. **Aliases** — venue symbols and separator variants. An alias that would resolve
       to more than one instrument is dropped as ambiguous rather than guessed at:
       BTCUSDT-the-perp is "BTCUSDT" at Bybit too, and silently resolving that to the
       perp would have a spot strategy trading a funding-paying contract.
    """

    def __init__(self, instruments: Iterable[Instrument] = ()) -> None:
        self._canonical: Dict[str, Instrument] = {}
        self._aliases: Dict[str, Optional[Instrument]] = {}   # None = ambiguous
        for inst in instruments:
            self.register(inst)

    # ── Building ────────────────────────────────────────────────────────────────

    def register(self, instrument: Instrument) -> None:
        key = normalize_symbol(instrument.symbol)
        if key in self._canonical:
            raise ValueError(f"Duplicate instrument symbol '{instrument.symbol}'")
        self._canonical[key] = instrument
        for listing in instrument.venues.values():
            self._add_alias(normalize_symbol(listing.symbol), instrument)
        self._add_alias(normalize_symbol(f"{instrument.base}{instrument.quote}"), instrument)

    def _add_alias(self, key: str, instrument: Instrument) -> None:
        existing = self._aliases.get(key, instrument)
        # Already claimed by a different instrument → ambiguous, resolve to nothing.
        self._aliases[key] = instrument if existing is instrument else None

    # ── Lookup ──────────────────────────────────────────────────────────────────

    def get(self, symbol: str) -> Optional[Instrument]:
        key = normalize_symbol(symbol)
        return self._canonical.get(key) or self._aliases.get(key)

    def require(self, symbol: str) -> Instrument:
        """Like `get`, but fails loud — the order path must never guess."""
        instrument = self.get(symbol)
        if instrument is None:
            raise UnknownInstrument(symbol)
        return instrument

    def all(self) -> List[Instrument]:
        return list(self._canonical.values())

    def symbol_for(self, symbol: str, broker: BrokerID) -> str:
        """The broker's own notation for `symbol`, e.g. BTCUSDT → BTC/USD at Alpaca."""
        instrument = self.require(symbol)
        listing = instrument.listing(broker)
        if listing is None:
            raise InstrumentViolation(
                "not_listed", f"{instrument.symbol} is not listed on {broker.value}"
            )
        return listing.symbol

    def category_for(self, symbol: str, broker: BrokerID) -> str:
        """The broker's product bucket for `symbol` ("spot"/"linear" at Bybit)."""
        listing = self.require(symbol).listing(broker)
        return listing.category if listing else ""

    def symbols_on(self, broker: BrokerID) -> List[str]:
        """Every broker-notation symbol this registry can route to `broker`."""
        return [i.venues[broker].symbol for i in self.all() if broker in i.venues]
