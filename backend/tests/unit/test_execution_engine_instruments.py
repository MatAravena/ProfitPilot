"""ExecutionEngine conforms every order to the instrument's tick/lot grid before it
reaches RiskManager or the broker.

Opens are validated (an order too small to clear the exchange's minimum, or a symbol the
catalog has never heard of, must never open a position). Closes are quantized only and
always execute, mirroring the existing rule that a close/stop-loss must never be blocked
by the risk veto — including when the symbol is unseeded, since a position already held
must always be closable.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.core.enums import Direction, MarketType, OrderStatus, SignalSource, Timeframe
from app.core.types import Account, OrderResult, Position, RiskConfig, Signal
from app.domain.execution.execution_engine import ACTION_CLOSED, ACTION_OPENED_LONG, ACTION_REJECTED, ExecutionEngine
from app.domain.instruments import Instrument, InstrumentKind, InstrumentRegistry
from app.domain.risk.risk_manager import RiskManager

pytestmark = pytest.mark.asyncio

STRAT = uuid.uuid4()
SYMBOL = "BTCUSDT"

COARSE = Instrument(
    symbol=SYMBOL, base="BTC", quote="USDT",
    market_type=MarketType.CRYPTO, kind=InstrumentKind.SPOT,
    tick_size=1.0, lot_step=5.0, min_qty=5.0, min_notional=5.0,
    venues={},
)


class FakeBroker:
    def __init__(self):
        self.orders = []

    async def place_order(self, order):
        self.orders.append(order)
        return OrderResult(
            order_id=order.order_id, broker_order_id=f"sim-{order.order_id}",
            status=OrderStatus.FILLED, submitted_at=datetime.now(timezone.utc),
        )


def account(equity: float = 100_000.0) -> Account:
    return Account(
        broker_id="sim", account_id="acc", equity=equity, cash=equity,
        buying_power=equity, paper_mode=True, updated_at=datetime.now(timezone.utc),
    )


def position(qty: float, entry: float, mark: float) -> Position:
    return Position(
        symbol=SYMBOL, market_type=MarketType.CRYPTO, broker_id="sim",
        quantity=qty, avg_entry_price=entry, current_price=mark,
        unrealized_pnl=(mark - entry) * qty, unrealized_pnl_pct=0.0,
        opened_at=datetime.now(timezone.utc),
    )


def signal(direction: Direction) -> Signal:
    return Signal(
        signal_id=uuid.uuid4(), strategy_id=STRAT, symbol=SYMBOL,
        market_type=MarketType.CRYPTO, timeframe=Timeframe.D1, direction=direction,
        confidence=0.9, source=SignalSource.QUANT, generated_at=datetime.now(timezone.utc),
    )


async def run(eng, broker, *, position=None, signals, equity=100_000.0,
              cfg=None, latest_close=100.0, allow_short=True):
    return await eng.reconcile_and_execute(
        strategy_id=STRAT, symbol=SYMBOL, broker_id="sim", adapter=broker,
        account=account(equity), position=position, signals=signals,
        risk_cfg=cfg or RiskConfig(), latest_close=latest_close, allow_short=allow_short,
    )


# ── Injection ────────────────────────────────────────────────────────────────────────

def test_accepts_an_injected_catalog_not_just_the_default_registry():
    catalog = InstrumentRegistry([COARSE])
    eng = ExecutionEngine(RiskManager(), instruments=catalog)
    assert eng._instruments is catalog


# ── Opens: conformed and validated ─────────────────────────────────────────────────────

async def test_open_quantity_is_floored_to_the_lot_step():
    eng = ExecutionEngine(RiskManager(), instruments=InstrumentRegistry([COARSE]))
    broker = FakeBroker()
    # equity 101_000 * 2% / price 100 = 20.2 → floored to the 5.0 lot step = 20.0.
    outcomes = await run(eng, broker, signals=[signal(Direction.LONG)], equity=101_000.0)
    assert outcomes[0].action == ACTION_OPENED_LONG
    assert broker.orders[0].quantity == pytest.approx(20.0)


async def test_open_price_is_rounded_to_the_tick_size():
    eng = ExecutionEngine(RiskManager(), instruments=InstrumentRegistry([COARSE]))
    broker = FakeBroker()
    outcomes = await run(eng, broker, signals=[signal(Direction.LONG)], latest_close=100.37)
    assert outcomes[0].action == ACTION_OPENED_LONG
    assert broker.orders[0].limit_price == pytest.approx(100.0)


async def test_open_below_min_notional_is_rejected_before_reaching_risk_or_broker():
    tiny = Instrument(
        symbol=SYMBOL, base="BTC", quote="USDT",
        market_type=MarketType.CRYPTO, kind=InstrumentKind.SPOT,
        tick_size=0.01, lot_step=0.001, min_qty=0.001, min_notional=10_000.0,
        venues={},
    )
    eng = ExecutionEngine(RiskManager(), instruments=InstrumentRegistry([tiny]))
    broker = FakeBroker()
    # equity 100_000 * 2% / price 100 = 20 qty → $2,000 notional, under the $10,000 floor.
    outcomes = await run(eng, broker, signals=[signal(Direction.LONG)])
    assert outcomes[0].action == ACTION_REJECTED
    assert "below BTCUSDT's minimum" in outcomes[0].reason
    assert broker.orders == []


# ── Closes: quantized, never blocked ────────────────────────────────────────────────────

async def test_close_is_never_rejected_by_a_min_size_violation():
    """A close/stop-loss must always execute — same rule the risk veto already follows."""
    impossible = Instrument(
        symbol=SYMBOL, base="BTC", quote="USDT",
        market_type=MarketType.CRYPTO, kind=InstrumentKind.SPOT,
        tick_size=1.0, lot_step=5.0, min_qty=5.0, min_notional=1_000_000.0,
        venues={},
    )
    eng = ExecutionEngine(RiskManager(), instruments=InstrumentRegistry([impossible]))
    broker = FakeBroker()
    pos = position(qty=22.0, entry=100, mark=110)
    outcomes = await run(eng, broker, position=pos, signals=[signal(Direction.CLOSE)],
                         latest_close=110)
    assert outcomes[0].action == ACTION_CLOSED
    assert len(broker.orders) == 1
    assert broker.orders[0].quantity == pytest.approx(20.0)   # floored 22.0 → 20.0 (step 5)


# ── Unseeded symbol ──────────────────────────────────────────────────────────────────

async def test_unseeded_symbol_rejects_an_open():
    """Per `UnknownInstrument`'s own contract: an un-vetted symbol must not open a
    position sized/rounded on guesses."""
    empty = InstrumentRegistry([])   # SYMBOL is not registered
    eng = ExecutionEngine(RiskManager(), instruments=empty)
    broker = FakeBroker()
    outcomes = await run(eng, broker, signals=[signal(Direction.LONG)])
    assert outcomes[0].action == ACTION_REJECTED
    assert "Unknown instrument" in outcomes[0].reason
    assert broker.orders == []


async def test_unseeded_symbol_still_allows_a_close():
    """A position already held must always be closable, even for a symbol the catalog
    has never heard of."""
    empty = InstrumentRegistry([])
    eng = ExecutionEngine(RiskManager(), instruments=empty)
    broker = FakeBroker()
    pos = position(qty=20.0, entry=100, mark=110)
    outcomes = await run(eng, broker, position=pos, signals=[signal(Direction.CLOSE)],
                         latest_close=110.0)
    assert outcomes[0].action == ACTION_CLOSED
    assert broker.orders[0].quantity == pytest.approx(20.0)
    assert broker.orders[0].limit_price == pytest.approx(110.0)   # unrounded, unconformed
