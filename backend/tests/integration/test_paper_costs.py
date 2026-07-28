"""Paper trading (SimulatedBrokerAdapter) must model the SAME costs as the backtest —
adverse slippage + commission on every fill — so a paper run is a faithful preview of a
backtest (and of real live), not an artificially frictionless one.

Cost model (identical to BacktestEngine): the effective fill price bakes in slippage then
commission — a BUY pays base·(1+slip)·(1+comm), a SELL receives base·(1-slip)·(1-comm).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models.db  # noqa: F401 — registers models on Base.metadata
from app.core.enums import MarketType, OrderSide, OrderType
from app.core.types import Order
from app.db.base import Base
from app.domain.broker.adapters.simulated_adapter import SimulatedBrokerAdapter
from app.models.db.strategy_instance import StrategyInstance
from app.models.db.user import User

pytestmark = pytest.mark.asyncio

SYMBOL = "BTCUSDT"
START = 100_000.0


@pytest_asyncio.fixture()
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id, strat_id = uuid.uuid4(), uuid.uuid4()
    async with factory() as s:
        s.add(User(id=user_id, email="t@t.com", username="t", hashed_password="x"))
        s.add(StrategyInstance(id=strat_id, user_id=user_id, class_name="X",
                               symbol=SYMBOL, timeframe="1d", status="paper"))
        await s.commit()
    yield factory, user_id, strat_id
    await engine.dispose()


def _order(side: OrderSide, qty: float, price: float) -> Order:
    return Order(
        order_id=uuid.uuid4(), strategy_id=uuid.uuid4(), broker_id="sim", symbol=SYMBOL,
        side=side, order_type=OrderType.MARKET, quantity=qty, limit_price=price,
        signal_id=None, metadata={}, created_at=datetime.now(timezone.utc),
    )


def _adapter(session, strat_id, user_id, *, commission=0.0, slippage=0.0):
    return SimulatedBrokerAdapter(
        session=session, strategy_id=strat_id, user_id=user_id, starting_equity=START,
        market_type=MarketType.CRYPTO, commission_pct=commission, slippage_pct=slippage,
    )


async def test_buy_fill_pays_slippage_and_commission(db):
    factory, user_id, strat_id = db
    async with factory() as s:
        adapter = _adapter(s, strat_id, user_id, commission=0.001, slippage=0.0005)
        adapter.set_mark(SYMBOL, 100.0)
        await adapter.place_order(_order(OrderSide.BUY, 10, 100.0))
        # Effective buy price = 100 * 1.0005 * 1.001; cash spent = 10 * that.
        eff = 100.0 * 1.0005 * 1.001
        acc = await adapter.get_account()
        assert acc.cash == pytest.approx(START - 10 * eff)


async def _realized(adapter, strat_id) -> float:
    """Realized P&L from the ledger row (the Account response doesn't carry it)."""
    row = await adapter._repo.get_account(strat_id)
    return row.realized_pnl


async def test_round_trip_realized_pnl_is_net_of_costs(db):
    factory, user_id, strat_id = db
    async with factory() as s:
        adapter = _adapter(s, strat_id, user_id, commission=0.001, slippage=0.0005)
        adapter.set_mark(SYMBOL, 100.0)
        await adapter.place_order(_order(OrderSide.BUY, 10, 100.0))     # open long
        adapter.set_mark(SYMBOL, 110.0)
        await adapter.place_order(_order(OrderSide.SELL, 10, 110.0))    # close

        entry_eff = 100.0 * 1.0005 * 1.001    # bought higher
        exit_eff = 110.0 * 0.9995 * 0.999     # sold lower
        expected = (exit_eff - entry_eff) * 10
        realized = await _realized(adapter, strat_id)
        # Realized P&L is strictly less than the frictionless +100 (10 * (110-100)).
        assert realized == pytest.approx(expected)
        assert realized < 100.0
        # Flat again → equity == start + realized.
        acc = await adapter.get_account()
        assert acc.equity == pytest.approx(START + expected)


async def test_zero_costs_is_backward_compatible(db):
    # Defaults (no costs) reproduce the old frictionless behavior: flat round trip @100→110
    # realizes exactly +100 on 10 units.
    factory, user_id, strat_id = db
    async with factory() as s:
        adapter = _adapter(s, strat_id, user_id)   # commission=0, slippage=0
        adapter.set_mark(SYMBOL, 100.0)
        await adapter.place_order(_order(OrderSide.BUY, 10, 100.0))
        adapter.set_mark(SYMBOL, 110.0)
        await adapter.place_order(_order(OrderSide.SELL, 10, 110.0))
        assert await _realized(adapter, strat_id) == pytest.approx(100.0)


async def test_short_round_trip_pays_costs_both_sides(db):
    # Short: SELL to open (receive less), BUY to cover (pay more). Price falls 100→90.
    factory, user_id, strat_id = db
    async with factory() as s:
        adapter = _adapter(s, strat_id, user_id, commission=0.001, slippage=0.0005)
        adapter.set_mark(SYMBOL, 100.0)
        await adapter.place_order(_order(OrderSide.SELL, 10, 100.0))    # open short
        adapter.set_mark(SYMBOL, 90.0)
        await adapter.place_order(_order(OrderSide.BUY, 10, 90.0))      # cover
        entry_eff = 100.0 * 0.9995 * 0.999    # sold lower
        exit_eff = 90.0 * 1.0005 * 1.001      # bought back higher
        # Short P&L = (entry - exit) * qty, net of costs; still profitable but < frictionless +100.
        expected = (entry_eff - exit_eff) * 10
        realized = await _realized(adapter, strat_id)
        assert realized == pytest.approx(expected)
        assert 0 < realized < 100.0
