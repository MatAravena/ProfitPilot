"""Unit tests for the canonical instrument registry.

The registry is the single source of truth for what a symbol *is* — its venue symbols,
tick size, lot step, min notional, multiplier, and whether it is spot or a perpetual.
"""
from __future__ import annotations

import pytest

from app.core.enums import BrokerID, MarketType
from app.domain.instruments import (
    INSTRUMENTS,
    Instrument,
    InstrumentKind,
    InstrumentRegistry,
    InstrumentViolation,
    UnknownInstrument,
    VenueListing,
    conform_order,
)


# ── Fixtures: a tiny hand-built registry so spec tests don't depend on seed values ──

BTC = Instrument(
    symbol="BTCUSDT",
    base="BTC", quote="USDT",
    market_type=MarketType.CRYPTO, kind=InstrumentKind.SPOT,
    tick_size=0.01, lot_step=0.000001, min_qty=0.000001, min_notional=5.0,
    venues={
        BrokerID.BYBIT: VenueListing("BTCUSDT", category="spot"),
        BrokerID.ALPACA: VenueListing("BTC/USD"),
    },
)
BTC_PERP = Instrument(
    symbol="BTCUSDT.P",
    base="BTC", quote="USDT",
    market_type=MarketType.CRYPTO, kind=InstrumentKind.PERP,
    tick_size=0.1, lot_step=0.001, min_qty=0.001, min_notional=5.0,
    venues={BrokerID.BYBIT: VenueListing("BTCUSDT", category="linear")},
)
AAPL = Instrument(
    symbol="AAPL",
    base="AAPL", quote="USD",
    market_type=MarketType.STOCK, kind=InstrumentKind.SPOT,
    tick_size=0.01, lot_step=0.001, min_qty=0.001, min_notional=1.0,
    venues={BrokerID.ALPACA: VenueListing("AAPL")},
)


@pytest.fixture
def reg() -> InstrumentRegistry:
    return InstrumentRegistry([BTC, BTC_PERP, AAPL])


# ── Lookup ─────────────────────────────────────────────────────────────────────────

def test_require_returns_the_canonical_instrument(reg):
    inst = reg.require("BTCUSDT")
    assert inst.symbol == "BTCUSDT"
    assert inst.market_type is MarketType.CRYPTO
    assert inst.kind is InstrumentKind.SPOT


@pytest.mark.parametrize("alias", ["btcusdt", " BTCUSDT ", "BTC/USD", "BTC-USD", "btc/usd"])
def test_lookup_is_case_and_separator_insensitive(reg, alias):
    assert reg.require(alias).symbol == "BTCUSDT"


def test_unknown_symbol_fails_loud(reg):
    assert reg.get("NOPECOIN") is None
    with pytest.raises(UnknownInstrument):
        reg.require("NOPECOIN")


def test_spot_and_perp_are_distinct_instruments(reg):
    spot, perp = reg.require("BTCUSDT"), reg.require("BTCUSDT.P")
    assert spot is not perp
    assert perp.kind is InstrumentKind.PERP
    # Both are "BTCUSDT" at Bybit — the *category* is what separates them.
    assert spot.listing(BrokerID.BYBIT).category == "spot"
    assert perp.listing(BrokerID.BYBIT).category == "linear"


def test_a_venue_alias_never_shadows_a_canonical_symbol(reg):
    """The perp's Bybit symbol is "BTCUSDT", which collides with the spot's canonical
    symbol. Canonical always wins — otherwise a spot strategy would silently trade perps."""
    assert reg.require("BTCUSDT") is reg.require("BTCUSDT")
    assert reg.require("BTCUSDT").kind is InstrumentKind.SPOT


def test_symbol_for_translates_to_the_brokers_own_notation(reg):
    assert reg.symbol_for("BTCUSDT", BrokerID.ALPACA) == "BTC/USD"
    assert reg.symbol_for("BTCUSDT", BrokerID.BYBIT) == "BTCUSDT"


def test_symbol_for_an_unlisted_broker_fails_loud(reg):
    with pytest.raises(InstrumentViolation):
        reg.symbol_for("AAPL", BrokerID.BYBIT)


def test_registering_a_second_instrument_with_the_same_symbol_is_rejected(reg):
    with pytest.raises(ValueError):
        reg.register(BTC)


# ── Quantization ───────────────────────────────────────────────────────────────────

def test_quantity_is_floored_to_the_lot_step(reg):
    """Floored, never rounded up: rounding up could push the order past the risk cap
    that sizing just computed, and RiskManager would veto the entry."""
    qty, _ = conform_order(BTC_PERP, quantity=1.2349, price=50_000.0)
    assert qty == pytest.approx(1.234)


def test_price_is_rounded_to_the_tick_size(reg):
    _, price = conform_order(BTC_PERP, quantity=1.0, price=50_000.06)
    assert price == pytest.approx(50_000.1)


def test_step_math_is_exact_under_float_noise(reg):
    """0.1 + 0.2 arithmetic must not shave a step off the quantity."""
    qty, _ = conform_order(BTC_PERP, quantity=0.1 + 0.2, price=50_000.0)
    assert qty == pytest.approx(0.3)


def test_price_is_optional(reg):
    qty, price = conform_order(AAPL, quantity=2.0, price=None)
    assert (qty, price) == (2.0, None)


# ── Validation ─────────────────────────────────────────────────────────────────────

def test_quantity_below_the_minimum_is_rejected(reg):
    with pytest.raises(InstrumentViolation) as exc:
        conform_order(BTC_PERP, quantity=0.0004, price=50_000.0)
    assert exc.value.rule == "min_qty"


def test_notional_below_the_minimum_is_rejected(reg):
    # 0.001 BTC at $100 = $0.10, under the $5 minimum.
    with pytest.raises(InstrumentViolation) as exc:
        conform_order(BTC_PERP, quantity=0.001, price=100.0)
    assert exc.value.rule == "min_notional"


def test_notional_uses_the_contract_multiplier(reg):
    """A x10 multiplier makes the same qty*price ten times the notional."""
    contract = Instrument(
        symbol="TEST.F", base="TEST", quote="USD",
        market_type=MarketType.FUTURES, kind=InstrumentKind.PERP,
        tick_size=0.01, lot_step=1.0, min_qty=1.0, min_notional=1_000.0, multiplier=10.0,
        venues={BrokerID.BYBIT: VenueListing("TESTF", category="linear")},
    )
    # 1 x $150 = $150 nominal, but x10 multiplier = $1,500 → passes the $1,000 floor.
    qty, _ = conform_order(contract, quantity=1.0, price=150.0)
    assert qty == 1.0
    with pytest.raises(InstrumentViolation):
        conform_order(contract, quantity=1.0, price=50.0)


def test_an_order_to_a_broker_that_does_not_list_the_instrument_is_rejected(reg):
    with pytest.raises(InstrumentViolation) as exc:
        conform_order(AAPL, quantity=1.0, price=200.0, broker=BrokerID.BYBIT)
    assert exc.value.rule == "not_listed"


def test_a_broker_the_registry_does_not_know_skips_the_venue_check(reg):
    """The simulated/paper adapter has no venue constraints — an unrecognized broker
    string must not block paper trading."""
    qty, _ = conform_order(AAPL, quantity=1.0, price=200.0, broker="sim")
    assert qty == 1.0


def test_a_valid_order_passes_through_quantized(reg):
    qty, price = conform_order(BTC, quantity=0.0123456789, price=64_321.987,
                               broker=BrokerID.BYBIT)
    assert qty == pytest.approx(0.012345)
    assert price == pytest.approx(64_321.99)


# ── The shipped seed ───────────────────────────────────────────────────────────────

def test_the_default_registry_covers_the_symbols_the_app_ships_with():
    for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "AAPL", "SPY"):
        assert INSTRUMENTS.require(symbol).symbol == symbol


def test_every_seeded_instrument_is_listed_on_at_least_one_venue():
    orphans = [i.symbol for i in INSTRUMENTS.all() if not i.venues]
    assert orphans == [], f"instruments with no venue are untradable: {orphans}"


def test_every_seeded_instrument_has_sane_specs():
    for i in INSTRUMENTS.all():
        assert i.tick_size > 0, i.symbol
        assert i.lot_step > 0, i.symbol
        assert i.min_qty >= i.lot_step, i.symbol
        assert i.min_notional >= 0, i.symbol
        assert i.multiplier > 0, i.symbol


def test_seeded_crypto_pairs_default_to_spot():
    """The app's own strategies accumulate coins — spot, not funding-paying perps.
    Perps are separate instruments with an explicit .P suffix."""
    assert INSTRUMENTS.require("BTCUSDT").kind is InstrumentKind.SPOT
    assert INSTRUMENTS.require("BTCUSDT.P").kind is InstrumentKind.PERP
