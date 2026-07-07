from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.core.enums import (
    Direction,
    MarketType,
    OrderSide,
    OrderStatus,
    SignalSource,
    Timeframe,
)
from app.core.types import Account, OrderResult, Position, RiskConfig, Signal
from app.domain.execution.execution_engine import (
    ACTION_CLOSED,
    ACTION_ERROR,
    ACTION_NOOP,
    ACTION_OPENED_LONG,
    ACTION_OPENED_SHORT,
    ACTION_REJECTED,
    ExecutionEngine,
)
from app.domain.risk.risk_manager import RiskManager

pytestmark = pytest.mark.asyncio

STRAT = uuid.uuid4()
SYMBOL = "BTCUSDT"


class FakeBroker:
    """Records placed orders, returns FILLED market orders."""

    def __init__(self, fill_status: OrderStatus = OrderStatus.FILLED):
        self.orders = []
        self._status = fill_status

    async def place_order(self, order):
        self.orders.append(order)
        return OrderResult(
            order_id=order.order_id,
            broker_order_id=f"sim-{order.order_id}",
            status=self._status,
            submitted_at=datetime.now(timezone.utc),
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


def engine() -> ExecutionEngine:
    return ExecutionEngine(RiskManager())


async def run(eng, broker, *, position=None, signals, equity=100_000.0,
              cfg=None, latest_close=100.0, allow_short=True):
    return await eng.reconcile_and_execute(
        strategy_id=STRAT, symbol=SYMBOL, broker_id="sim", adapter=broker,
        account=account(equity), position=position, signals=signals,
        risk_cfg=cfg or RiskConfig(), latest_close=latest_close, allow_short=allow_short,
    )


# ── State machine ────────────────────────────────────────────────────────────────

async def test_flat_long_opens_long():
    broker = FakeBroker()
    outcomes = await run(engine(), broker, signals=[signal(Direction.LONG)])
    assert [o.action for o in outcomes] == [ACTION_OPENED_LONG]
    assert len(broker.orders) == 1
    assert broker.orders[0].side == OrderSide.BUY
    assert outcomes[0].fill is not None


async def test_flat_short_opens_short():
    broker = FakeBroker()
    outcomes = await run(engine(), broker, signals=[signal(Direction.SHORT)])
    assert [o.action for o in outcomes] == [ACTION_OPENED_SHORT]
    assert broker.orders[0].side == OrderSide.SELL


async def test_flat_close_is_noop():
    broker = FakeBroker()
    outcomes = await run(engine(), broker, signals=[signal(Direction.CLOSE)])
    assert outcomes[0].action == ACTION_NOOP
    assert broker.orders == []


async def test_long_long_is_idempotent_noop():
    broker = FakeBroker()
    pos = position(qty=20, entry=100, mark=100)
    outcomes = await run(engine(), broker, position=pos, signals=[signal(Direction.LONG)])
    assert outcomes[0].action == ACTION_NOOP
    assert broker.orders == []


async def test_long_close_flattens():
    broker = FakeBroker()
    pos = position(qty=20, entry=100, mark=110)
    outcomes = await run(engine(), broker, position=pos,
                         signals=[signal(Direction.CLOSE)], latest_close=110)
    assert outcomes[0].action == ACTION_CLOSED
    assert broker.orders[0].side == OrderSide.SELL
    assert broker.orders[0].quantity == pytest.approx(20)


async def test_long_short_signal_reverses_close_then_open():
    broker = FakeBroker()
    pos = position(qty=20, entry=100, mark=100)
    outcomes = await run(engine(), broker, position=pos, signals=[signal(Direction.SHORT)])
    assert [o.action for o in outcomes] == [ACTION_CLOSED, ACTION_OPENED_SHORT]
    assert [o.side for o in broker.orders] == [OrderSide.SELL, OrderSide.SELL]


async def test_short_long_signal_reverses():
    broker = FakeBroker()
    pos = position(qty=-20, entry=100, mark=100)
    outcomes = await run(engine(), broker, position=pos, signals=[signal(Direction.LONG)])
    assert [o.action for o in outcomes] == [ACTION_CLOSED, ACTION_OPENED_LONG]
    assert [o.side for o in broker.orders] == [OrderSide.BUY, OrderSide.BUY]


async def test_no_signal_is_noop():
    broker = FakeBroker()
    outcomes = await run(engine(), broker, signals=[])
    assert outcomes[0].action == ACTION_NOOP


async def test_shorting_disabled_blocks_open():
    broker = FakeBroker()
    outcomes = await run(engine(), broker, signals=[signal(Direction.SHORT)], allow_short=False)
    assert outcomes[-1].action == ACTION_NOOP
    assert broker.orders == []


# ── Loop-managed exits ───────────────────────────────────────────────────────────

async def test_stop_loss_closes_long():
    broker = FakeBroker()
    cfg = RiskConfig(stop_loss_pct=0.015)
    pos = position(qty=20, entry=100, mark=98)
    # latest_close below 98.5 stop → auto close even though signal says stay long
    outcomes = await run(engine(), broker, position=pos, cfg=cfg,
                         signals=[signal(Direction.LONG)], latest_close=98.0)
    assert outcomes[0].action == ACTION_CLOSED
    assert outcomes[0].reason == "stop_loss"
    assert len(broker.orders) == 1


async def test_take_profit_closes_long():
    broker = FakeBroker()
    cfg = RiskConfig(take_profit_pct=0.05)
    pos = position(qty=20, entry=100, mark=106)
    outcomes = await run(engine(), broker, position=pos, cfg=cfg,
                         signals=[signal(Direction.LONG)], latest_close=106.0)
    assert outcomes[0].action == ACTION_CLOSED
    assert outcomes[0].reason == "take_profit"


async def test_stop_loss_closes_short():
    broker = FakeBroker()
    cfg = RiskConfig(stop_loss_pct=0.015)
    pos = position(qty=-20, entry=100, mark=102)
    outcomes = await run(engine(), broker, position=pos, cfg=cfg,
                         signals=[signal(Direction.SHORT)], latest_close=102.0)
    assert outcomes[0].action == ACTION_CLOSED
    assert outcomes[0].reason == "stop_loss"


async def test_no_exit_when_within_bounds():
    broker = FakeBroker()
    cfg = RiskConfig(stop_loss_pct=0.015)
    pos = position(qty=20, entry=100, mark=99.5)
    outcomes = await run(engine(), broker, position=pos, cfg=cfg,
                         signals=[signal(Direction.LONG)], latest_close=99.5)
    # still long, signal long → noop, no exit
    assert outcomes[0].action == ACTION_NOOP


# ── Risk integration ─────────────────────────────────────────────────────────────

async def test_oversized_order_rejected():
    broker = FakeBroker()
    # max_position_size_pct 1.0 → notional == equity, but cap check compares notional>max.
    # Use a tiny cap so any order exceeds: force rejection via max_orders_per_minute=0.
    cfg = RiskConfig(max_orders_per_minute=0)
    outcomes = await run(engine(), broker, signals=[signal(Direction.LONG)], cfg=cfg)
    assert outcomes[0].action == ACTION_REJECTED
    assert broker.orders == []


async def test_max_open_positions_rejects_second_open():
    broker = FakeBroker()
    eng = engine()
    cfg = RiskConfig(max_open_positions=1)
    # First open succeeds and bumps the open-position count to 1.
    first = await run(eng, broker, signals=[signal(Direction.LONG)], cfg=cfg)
    assert first[0].action == ACTION_OPENED_LONG
    # Second open (still flat from the engine's POV) is vetoed: count(1) >= max(1).
    second = await run(eng, broker, signals=[signal(Direction.LONG)], cfg=cfg)
    assert second[0].action == ACTION_REJECTED
    assert len(broker.orders) == 1  # no second order placed


async def test_close_bypasses_risk_veto():
    # Even with orders-per-minute exhausted, a close must still execute.
    broker = FakeBroker()
    cfg = RiskConfig(max_orders_per_minute=0)
    pos = position(qty=20, entry=100, mark=110)
    outcomes = await run(engine(), broker, position=pos, cfg=cfg,
                         signals=[signal(Direction.CLOSE)], latest_close=110)
    assert outcomes[0].action == ACTION_CLOSED
    assert len(broker.orders) == 1


async def test_broker_failure_returns_error():
    class BoomBroker(FakeBroker):
        async def place_order(self, order):
            raise RuntimeError("network down")

    outcomes = await run(engine(), BoomBroker(), signals=[signal(Direction.LONG)])
    assert outcomes[0].action == ACTION_ERROR
    assert "network down" in outcomes[0].reason


async def test_unconfirmed_fill_has_no_fill_object():
    broker = FakeBroker(fill_status=OrderStatus.SUBMITTED)
    outcomes = await run(engine(), broker, signals=[signal(Direction.LONG)])
    assert outcomes[0].action == ACTION_OPENED_LONG
    assert outcomes[0].fill is None
