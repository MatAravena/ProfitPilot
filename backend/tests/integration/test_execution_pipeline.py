"""Integration tests for the live-trading pipeline using the real
SimulatedBrokerAdapter + a real SQLite DB (no network, no HTTP)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models.db  # noqa: F401 — registers all models on Base.metadata
from app.core.enums import Direction, MarketType, OrderSide, SignalSource, Timeframe
from app.core.types import RiskConfig, Signal
from app.db.base import Base
from app.domain.broker.adapters.simulated_adapter import SimulatedBrokerAdapter
from app.domain.execution.execution_engine import (
    ACTION_CLOSED,
    ACTION_NOOP,
    ACTION_OPENED_LONG,
    ExecutionEngine,
)
from app.domain.risk.risk_manager import RiskManager
from app.models.db.order_record import OrderRecord
from app.models.db.sim_ledger import SimAccount, SimPosition
from app.models.db.strategy_instance import StrategyInstance
from app.models.db.user import User

pytestmark = pytest.mark.asyncio

SYMBOL = "BTCUSDT"
START_EQUITY = 100_000.0


@pytest_asyncio.fixture()
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    user_id = uuid.uuid4()
    strat_id = uuid.uuid4()
    async with factory() as s:
        s.add(User(id=user_id, email="t@t.com", username="t", hashed_password="x"))
        s.add(StrategyInstance(
            id=strat_id, user_id=user_id, class_name="X", symbol=SYMBOL,
            timeframe="1d", status="paper",
        ))
        await s.commit()

    yield factory, user_id, strat_id
    await engine.dispose()


def make_signal(direction: Direction, strat_id: uuid.UUID) -> Signal:
    return Signal(
        signal_id=uuid.uuid4(), strategy_id=strat_id, symbol=SYMBOL,
        market_type=MarketType.CRYPTO, timeframe=Timeframe.D1, direction=direction,
        confidence=0.9, source=SignalSource.QUANT, generated_at=datetime.now(timezone.utc),
    )


async def run_cycle(factory, strat_id, user_id, engine, *, signals, latest_close):
    """One paper cycle: sim adapter → engine → persist OrderRecords, committed."""
    async with factory() as session:
        adapter = SimulatedBrokerAdapter(
            session=session, strategy_id=strat_id, user_id=user_id,
            starting_equity=START_EQUITY, market_type=MarketType.CRYPTO,
        )
        adapter.set_mark(SYMBOL, latest_close)
        account = await adapter.get_account()
        positions = await adapter.get_positions()
        pos = next((p for p in positions if p.symbol == SYMBOL), None)
        outcomes = await engine.reconcile_and_execute(
            strategy_id=strat_id, symbol=SYMBOL, broker_id="sim", adapter=adapter,
            account=account, position=pos, signals=signals,
            risk_cfg=RiskConfig(), latest_close=latest_close,
        )
        for o in outcomes:
            order = o.order
            session.add(OrderRecord(
                strategy_instance_id=strat_id, user_id=user_id, symbol=SYMBOL,
                side=order.side.value if order else None,
                quantity=order.quantity if order else None,
                status=o.action, reason=o.reason,
                broker_order_id=o.order_result.broker_order_id if o.order_result else None,
                filled_qty=o.fill.filled_quantity if o.fill else None,
                avg_price=o.fill.avg_price if o.fill else None,
            ))
        await session.commit()
    return outcomes


async def _positions(factory, strat_id):
    async with factory() as s:
        rows = (await s.execute(
            select(SimPosition).where(SimPosition.strategy_instance_id == strat_id)
        )).scalars().all()
        return list(rows)


async def _account(factory, strat_id):
    async with factory() as s:
        return (await s.execute(
            select(SimAccount).where(SimAccount.strategy_instance_id == strat_id)
        )).scalar_one()


async def _order_records(factory, strat_id):
    async with factory() as s:
        rows = (await s.execute(
            select(OrderRecord).where(OrderRecord.strategy_instance_id == strat_id)
        )).scalars().all()
        return list(rows)


# ── Tests ────────────────────────────────────────────────────────────────────────

async def test_full_paper_cycle_opens_and_persists(db):
    factory, user_id, strat_id = db
    engine = ExecutionEngine(RiskManager())

    outcomes = await run_cycle(factory, strat_id, user_id, engine,
                               signals=[make_signal(Direction.LONG, strat_id)], latest_close=100.0)

    assert [o.action for o in outcomes] == [ACTION_OPENED_LONG]

    positions = await _positions(factory, strat_id)
    assert len(positions) == 1
    assert positions[0].quantity == pytest.approx(20.0)          # 2% of 100k at price 100
    assert positions[0].avg_entry_price == pytest.approx(100.0)

    acc = await _account(factory, strat_id)
    assert acc.cash == pytest.approx(START_EQUITY - 2000.0)      # debited notional

    records = await _order_records(factory, strat_id)
    assert len(records) == 1
    assert records[0].status == ACTION_OPENED_LONG
    assert records[0].filled_qty == pytest.approx(20.0)


async def test_idempotent_second_long_does_not_double_fill(db):
    factory, user_id, strat_id = db
    engine = ExecutionEngine(RiskManager())

    await run_cycle(factory, strat_id, user_id, engine,
                    signals=[make_signal(Direction.LONG, strat_id)], latest_close=100.0)
    second = await run_cycle(factory, strat_id, user_id, engine,
                             signals=[make_signal(Direction.LONG, strat_id)], latest_close=101.0)

    assert second[0].action == ACTION_NOOP
    positions = await _positions(factory, strat_id)
    assert len(positions) == 1
    assert positions[0].quantity == pytest.approx(20.0)          # unchanged


async def test_round_trip_realizes_pnl(db):
    factory, user_id, strat_id = db
    engine = ExecutionEngine(RiskManager())

    await run_cycle(factory, strat_id, user_id, engine,
                    signals=[make_signal(Direction.LONG, strat_id)], latest_close=100.0)
    closed = await run_cycle(factory, strat_id, user_id, engine,
                             signals=[make_signal(Direction.CLOSE, strat_id)], latest_close=110.0)

    assert closed[0].action == ACTION_CLOSED
    assert await _positions(factory, strat_id) == []             # flat

    acc = await _account(factory, strat_id)
    # bought 20@100 (-2000), sold 20@110 (+2200) → cash back to start +200
    assert acc.realized_pnl == pytest.approx(200.0)
    assert acc.cash == pytest.approx(START_EQUITY + 200.0)


async def test_stop_loss_auto_closes(db):
    factory, user_id, strat_id = db
    engine = ExecutionEngine(RiskManager())

    await run_cycle(factory, strat_id, user_id, engine,
                    signals=[make_signal(Direction.LONG, strat_id)], latest_close=100.0)
    # Price drops below the 1.5% stop (98.5); LONG signal persists but must exit.
    dropped = await run_cycle(factory, strat_id, user_id, engine,
                              signals=[make_signal(Direction.LONG, strat_id)], latest_close=98.0)

    assert dropped[0].action == ACTION_CLOSED
    assert dropped[0].reason == "stop_loss"
    assert await _positions(factory, strat_id) == []


async def test_restart_durability_reloads_position(db):
    factory, user_id, strat_id = db
    engine = ExecutionEngine(RiskManager())

    await run_cycle(factory, strat_id, user_id, engine,
                    signals=[make_signal(Direction.LONG, strat_id)], latest_close=100.0)

    # Fresh adapter + fresh session against the same DB → position reloads from ledger.
    async with factory() as session:
        adapter = SimulatedBrokerAdapter(
            session=session, strategy_id=strat_id, user_id=user_id,
            starting_equity=START_EQUITY, market_type=MarketType.CRYPTO,
        )
        adapter.set_mark(SYMBOL, 105.0)
        positions = await adapter.get_positions()
        assert len(positions) == 1
        assert positions[0].quantity == pytest.approx(20.0)
        assert positions[0].current_price == pytest.approx(105.0)   # marked to new price
        account = await adapter.get_account()
        assert account.equity == pytest.approx(START_EQUITY + 100.0)  # 20 * (105-100) unrealized


# ── Executor smoke ───────────────────────────────────────────────────────────────

async def test_executor_execute_once_smoke(db, monkeypatch):
    """Drive the real StrategyExecutor._execute_once for a paper strategy."""
    from app.domain.strategy.base import StrategyRegistry
    from app.services.strategy_executor import StrategyExecutor
    from tests.conftest import make_bars

    factory, user_id, strat_id = db

    class _LongStrategy:
        def __init__(self, parameters=None, timeframe=None):
            self.parameters = parameters or {}
            self.timeframe = timeframe

        async def generate_signals(self, data):
            return [make_signal(Direction.LONG, strat_id)]

        async def on_fill(self, fill):
            return None

    StrategyRegistry.register(_LongStrategy)

    async def fake_fetch(symbol, timeframe, limit=200):
        return make_bars([100.0] * 60, symbol=SYMBOL, timeframe=Timeframe.D1)

    monkeypatch.setattr("app.domain.backtest.data_provider.fetch_ohlcv", fake_fetch)

    executor = StrategyExecutor()
    keep_going = await executor._execute_once(
        strat_id, "_LongStrategy", SYMBOL, Timeframe.D1, {}, user_id,
        "paper", None, RiskConfig(), True, factory,
    )

    assert keep_going is True
    records = await _order_records(factory, strat_id)
    assert any(r.status == ACTION_OPENED_LONG for r in records)

    async with factory() as s:
        inst = await s.get(StrategyInstance, strat_id)
        assert inst.last_signal_at is not None


async def test_allow_short_false_blocks_short_via_executor(db, monkeypatch):
    from app.domain.strategy.base import StrategyRegistry
    from app.services.strategy_executor import StrategyExecutor
    from tests.conftest import make_bars

    factory, user_id, strat_id = db

    class _ShortStrategy:
        def __init__(self, parameters=None, timeframe=None):
            self.parameters = parameters or {}
            self.timeframe = timeframe

        async def generate_signals(self, data):
            return [make_signal(Direction.SHORT, strat_id)]

        async def on_fill(self, fill):
            return None

    StrategyRegistry.register(_ShortStrategy)

    async def fake_fetch(symbol, timeframe, limit=200):
        return make_bars([100.0] * 60, symbol=SYMBOL, timeframe=Timeframe.D1)

    monkeypatch.setattr("app.domain.backtest.data_provider.fetch_ohlcv", fake_fetch)

    executor = StrategyExecutor()
    await executor._execute_once(
        strat_id, "_ShortStrategy", SYMBOL, Timeframe.D1, {}, user_id,
        "paper", None, RiskConfig(), False, factory,   # allow_short=False
    )

    # No position opened; the blocked short is recorded as a meaningful no-op.
    assert await _positions(factory, strat_id) == []
    records = await _order_records(factory, strat_id)
    assert any(r.status == ACTION_NOOP and r.reason == "shorting disabled" for r in records)


async def test_create_and_update_execution_config(db):
    from app.models.schemas.strategy_schemas import (
        CreateStrategyRequest,
        ExecutionConfig,
    )
    from app.repositories.strategy_instance_repository import StrategyInstanceRepository
    from app.services.strategy_executor import _risk_config_from_instance
    from app.services.strategy_service import StrategyService

    factory, user_id, _ = db

    async with factory() as session:
        svc = StrategyService(StrategyInstanceRepository(session))
        req = CreateStrategyRequest(
            class_name="X", symbol="ETHUSDT", timeframe="1h",
            execution=ExecutionConfig(size_pct=0.05, stop_loss_pct=0.02,
                                      allow_short=False, max_open_positions=3, poll_seconds=120),
        )
        inst = await svc.create(user_id, req)
        await session.commit()
        new_id = inst.id

        # Columns persisted from the request.
        assert inst.size_pct == pytest.approx(0.05)
        assert inst.allow_short is False
        assert inst.poll_seconds == 120

        # Maps cleanly onto a RiskConfig for the executor.
        rc = _risk_config_from_instance(inst)
        assert rc.max_position_size_pct == pytest.approx(0.05)
        assert rc.stop_loss_pct == pytest.approx(0.02)
        assert rc.max_open_positions == 3

        # Update replaces the config.
        updated = await svc.update_config(
            new_id, user_id, ExecutionConfig(size_pct=0.01, allow_short=True)
        )
        await session.commit()
        assert updated.size_pct == pytest.approx(0.01)
        assert updated.allow_short is True


def _fake_instance(strat_id, user_id, **overrides):
    from types import SimpleNamespace
    base = dict(
        id=strat_id, class_name="X", symbol=SYMBOL, timeframe="1d", parameters={},
        user_id=user_id, status="paper", broker_connection_id=None,
        size_pct=0.02, stop_loss_pct=0.015, take_profit_pct=None, max_open_positions=5,
        max_daily_drawdown_pct=0.03, max_total_drawdown_pct=0.1, max_orders_per_minute=10,
        allow_short=True, kill_switch_enabled=True, poll_seconds=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


async def test_config_change_restarts_running_task(db):
    from app.services.strategy_executor import StrategyExecutor

    factory, user_id, strat_id = db
    ex = StrategyExecutor()
    try:
        inst = _fake_instance(strat_id, user_id)
        ex._launch(inst, factory)
        first = ex._tasks[str(strat_id)]

        inst.allow_short = False   # edit config → reload
        ex.notify_config_change(inst, factory)
        second = ex._tasks[str(strat_id)]

        assert second is not first    # loop was restarted with fresh config
    finally:
        ex.shutdown()


async def test_config_change_noop_when_not_running(db):
    from app.services.strategy_executor import StrategyExecutor

    factory, user_id, strat_id = db
    ex = StrategyExecutor()
    inst = _fake_instance(strat_id, user_id, status="paper")   # never launched
    ex.notify_config_change(inst, factory)
    assert str(strat_id) not in ex._tasks
