"""Broker adapters resolve symbols through the injected `InstrumentCatalog`.

These tests inject a two-instrument catalog rather than the shipped seed — that is the
whole point of adapters depending on the abstraction: no network, no pybit/alpaca-py,
and the assertions stay true when the seed grows.
"""
from __future__ import annotations

import pytest

from app.core.enums import BrokerID, MarketType
from app.domain.broker.adapters.alpaca_adapter import AlpacaAdapter
from app.domain.broker.adapters.bybit_adapter import BybitAdapter
from app.domain.instruments import (
    Instrument,
    InstrumentKind,
    InstrumentRegistry,
    VenueListing,
)

BTC_SPOT = Instrument(
    symbol="BTCUSDT", base="BTC", quote="USDT",
    market_type=MarketType.CRYPTO, kind=InstrumentKind.SPOT,
    tick_size=0.01, lot_step=0.00001, min_qty=0.00001, min_notional=5.0,
    venues={
        BrokerID.BYBIT: VenueListing("BTCUSDT", category="spot"),
        BrokerID.ALPACA: VenueListing("BTC/USD"),
    },
)
BTC_PERP = Instrument(
    symbol="BTCUSDT.P", base="BTC", quote="USDT",
    market_type=MarketType.CRYPTO, kind=InstrumentKind.PERP,
    tick_size=0.1, lot_step=0.001, min_qty=0.001, min_notional=5.0,
    venues={BrokerID.BYBIT: VenueListing("BTCUSDT", category="linear")},
)
AAPL = Instrument(
    symbol="AAPL", base="AAPL", quote="USD",
    market_type=MarketType.STOCK, kind=InstrumentKind.SPOT,
    tick_size=0.01, lot_step=0.001, min_qty=0.001, min_notional=1.0,
    venues={BrokerID.ALPACA: VenueListing("AAPL")},
)


@pytest.fixture
def catalog() -> InstrumentRegistry:
    return InstrumentRegistry([BTC_SPOT, BTC_PERP, AAPL])


@pytest.fixture
def bybit(catalog) -> BybitAdapter:
    return BybitAdapter(api_key="k", secret_key="s", paper_mode=True, instruments=catalog)


@pytest.fixture
def alpaca(catalog) -> AlpacaAdapter:
    return AlpacaAdapter(api_key="k", secret_key="s", paper_mode=True, instruments=catalog)


# ── Bybit ──────────────────────────────────────────────────────────────────────────

def test_bybit_routes_spot_to_spot_not_linear(bybit):
    """The old resolver ignored its argument and always returned "linear", so every
    spot order was submitted against the perpetual product."""
    assert bybit._resolve_category("BTCUSDT") == "spot"


def test_bybit_routes_the_perp_to_linear(bybit):
    assert bybit._resolve_category("BTCUSDT.P") == "linear"


def test_bybit_falls_back_to_linear_for_an_unseeded_symbol(bybit):
    """Unknown symbols keep the previous behaviour rather than break an in-flight
    order; the adapter logs a warning so the gap gets seeded."""
    assert bybit._resolve_category("NOPECOIN") == "linear"


def test_bybit_translates_to_its_own_notation(bybit):
    assert bybit._venue_symbol("BTCUSDT.P") == "BTCUSDT"
    assert bybit._venue_symbol("BTCUSDT") == "BTCUSDT"


def test_bybit_passes_through_an_unseeded_symbol(bybit):
    assert bybit._venue_symbol("NOPECOIN") == "NOPECOIN"


# ── Alpaca ─────────────────────────────────────────────────────────────────────────

def test_alpaca_translates_canonical_crypto_to_slash_notation(alpaca):
    assert alpaca._venue_symbol("BTCUSDT") == "BTC/USD"


def test_alpaca_leaves_equities_alone(alpaca):
    assert alpaca._venue_symbol("AAPL") == "AAPL"


def test_alpaca_reads_market_type_from_the_catalog_not_the_symbol_shape(alpaca):
    """`"/" in symbol` called the canonical BTCUSDT a stock and sent it to the equities
    data client, which does not list it."""
    assert alpaca._market_type("BTCUSDT") is MarketType.CRYPTO
    assert alpaca._market_type("AAPL") is MarketType.STOCK


def test_alpaca_market_type_still_recognises_the_venue_notation(alpaca):
    assert alpaca._market_type("BTC/USD") is MarketType.CRYPTO


def test_alpaca_falls_back_to_the_shape_heuristic_when_unseeded(alpaca):
    assert alpaca._market_type("FOO/USD") is MarketType.CRYPTO
    assert alpaca._market_type("FOO") is MarketType.STOCK


# ── The abstraction itself ─────────────────────────────────────────────────────────

def test_adapters_accept_any_catalog_not_just_the_shipped_registry(catalog):
    """Dependency inversion: the constructor takes the `InstrumentCatalog` interface,
    so a broker-refreshed or DB-backed catalog drops in without an adapter change."""
    from app.domain.instruments import InstrumentCatalog

    assert isinstance(catalog, InstrumentCatalog)
    adapter = BybitAdapter(api_key="k", secret_key="s", instruments=catalog)
    assert adapter._instruments is catalog
