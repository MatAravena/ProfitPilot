"""Canonical instrument registry — the single source of truth for tradable symbols.

Import from this package, not from its modules: callers depend on the public names
below, which keeps the internal split (model / registry / seed) free to change.

`INSTRUMENTS` is the process-wide registry built from the shipped seed. Code that
needs to substitute its own set (tests, or a future broker-refreshed source) should
construct an `InstrumentRegistry` and inject it rather than mutating this singleton.
"""
from __future__ import annotations

from app.domain.instruments.base import InstrumentCatalog
from app.domain.instruments.instrument import (
    Instrument,
    InstrumentError,
    InstrumentKind,
    InstrumentViolation,
    UnknownInstrument,
    VenueListing,
    conform_order,
    floor_to_step,
    round_to_tick,
)
from app.domain.instruments.registry import InstrumentRegistry, normalize_symbol
from app.domain.instruments.seed import default_instruments

INSTRUMENTS = InstrumentRegistry(default_instruments())

__all__ = [
    "INSTRUMENTS",
    "Instrument",
    "InstrumentCatalog",
    "InstrumentError",
    "InstrumentKind",
    "InstrumentRegistry",
    "InstrumentViolation",
    "UnknownInstrument",
    "VenueListing",
    "conform_order",
    "default_instruments",
    "floor_to_step",
    "normalize_symbol",
    "round_to_tick",
]
