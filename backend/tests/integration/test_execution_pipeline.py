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
from app.core.enums import Direction, MarketType, OrderSide, OrderStatus, SignalSource, Timeframe
from app.core.types import Account, OrderResult, Position, RiskConfig, Signal
from app.db.base import Base
from app.domain.broker.adapters.simulated_adapter import SimulatedBrokerAdapter
from app.domain.execution.execution_engine import (
    ACTION_CLOSED,
    ACTION_ERROR,
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
                realized_pnl=o.realized_pnl,
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
    from app.models.db.risk_profile import RiskProfile
    from app.repositories.strategy_instance_repository import StrategyInstanceRepository
    from app.services.strategy_executor import _merge_risk_config
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

        # Behavioral columns + risk overrides persisted from the request.
        assert inst.size_pct == pytest.approx(0.05)
        assert inst.allow_short is False
        assert inst.poll_seconds == 120
        assert inst.stop_loss_pct == pytest.approx(0.02)   # explicit override
        assert inst.max_total_drawdown_pct is None         # unset → inherit profile

        # Merge with a profile: overrides win, unset fields inherit the profile.
        profile = RiskProfile(
            user_id=user_id, stop_loss_pct=0.015, take_profit_pct=None,
            max_open_positions=5, max_daily_drawdown_pct=0.03, max_total_drawdown_pct=0.10,
            max_orders_per_minute=10, kill_switch_enabled=True,
        )
        rc = _merge_risk_config(profile, inst)
        assert rc.max_position_size_pct == pytest.approx(0.05)   # from strategy size_pct
        assert rc.stop_loss_pct == pytest.approx(0.02)           # strategy override
        assert rc.max_open_positions == 3                        # strategy override
        assert rc.max_total_drawdown_pct == pytest.approx(0.10)  # inherited from profile

        # Update replaces the config.
        updated = await svc.update_config(
            new_id, user_id, ExecutionConfig(size_pct=0.01, allow_short=True)
        )
        await session.commit()
        assert updated.size_pct == pytest.approx(0.01)
        assert updated.allow_short is True
        assert updated.stop_loss_pct is None    # override cleared → inherit profile again


def _fake_instance(strat_id, user_id, **overrides):
    from types import SimpleNamespace
    base = dict(
        id=strat_id, class_name="X", symbol=SYMBOL, timeframe="1d", parameters={},
        user_id=user_id, status="paper", broker_connection_id=None,
        size_pct=0.02, stop_loss_pct=0.015, take_profit_pct=None, max_open_positions=5,
        max_daily_drawdown_pct=0.03, max_total_drawdown_pct=0.1, max_orders_per_minute=10,
        allow_short=True, kill_switch_enabled=True, poll_seconds=None, peak_equity=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


async def test_config_change_restarts_running_task(db):
    from app.services.strategy_executor import StrategyExecutor

    factory, user_id, strat_id = db
    ex = StrategyExecutor()
    try:
        inst = _fake_instance(strat_id, user_id)
        ex._launch(inst, RiskConfig(), factory)
        first = ex._tasks[str(strat_id)]

        inst.allow_short = False   # edit config → reload
        ex.notify_config_change(inst, RiskConfig(), factory)
        second = ex._tasks[str(strat_id)]

        assert second is not first    # loop was restarted with fresh config
    finally:
        ex.shutdown()


async def test_config_change_noop_when_not_running(db):
    from app.services.strategy_executor import StrategyExecutor

    factory, user_id, strat_id = db
    ex = StrategyExecutor()
    inst = _fake_instance(strat_id, user_id, status="paper")   # never launched
    ex.notify_config_change(inst, RiskConfig(), factory)
    assert str(strat_id) not in ex._tasks


def test_merge_risk_config_inherits_unset_overrides():
    from types import SimpleNamespace
    from app.models.db.risk_profile import RiskProfile
    from app.services.strategy_executor import _merge_risk_config

    profile = RiskProfile(
        user_id=uuid.uuid4(), stop_loss_pct=0.02, take_profit_pct=0.04,
        max_open_positions=7, max_daily_drawdown_pct=0.05, max_total_drawdown_pct=0.20,
        max_orders_per_minute=20, kill_switch_enabled=False,
    )
    inst = SimpleNamespace(
        size_pct=0.03, stop_loss_pct=None, take_profit_pct=None, max_open_positions=4,
        max_daily_drawdown_pct=None, max_total_drawdown_pct=None,
        max_orders_per_minute=None, kill_switch_enabled=None,
    )
    rc = _merge_risk_config(profile, inst)
    assert rc.max_position_size_pct == pytest.approx(0.03)   # strategy behavior
    assert rc.max_open_positions == 4                        # strategy override
    assert rc.stop_loss_pct == pytest.approx(0.02)           # inherited
    assert rc.take_profit_pct == pytest.approx(0.04)         # inherited
    assert rc.max_total_drawdown_pct == pytest.approx(0.20)  # inherited
    assert rc.kill_switch_enabled is False                   # inherited




async def test_rehydrate_risk_state_after_restart(db):
    """A fresh executor (simulated restart) rebuilds risk state from the ledger."""
    from app.services.strategy_executor import StrategyExecutor

    factory, user_id, strat_id = db

    # Open a position through the pipeline so the ledger holds it.
    engine = ExecutionEngine(RiskManager())
    await run_cycle(factory, strat_id, user_id, engine,
                    signals=[make_signal(Direction.LONG, strat_id)], latest_close=100.0)

    # New executor with empty in-memory risk state → rehydrate from persisted truth.
    ex = StrategyExecutor()
    inst = _fake_instance(strat_id, user_id, status="paper")
    await ex._rehydrate_risk_state(inst, factory)

    state = ex._risk._states[strat_id]
    assert state.open_position_count == 1
    assert state.peak_equity == pytest.approx(START_EQUITY)


async def test_rehydrate_reconstructs_daily_pnl(db):
    """Today's realized P&L is summed back into risk state on restart."""
    from app.services.strategy_executor import StrategyExecutor

    factory, user_id, strat_id = db
    engine = ExecutionEngine(RiskManager())

    # Round trip: open long @100, close @110 → +200 realized on the close record.
    await run_cycle(factory, strat_id, user_id, engine,
                    signals=[make_signal(Direction.LONG, strat_id)], latest_close=100.0)
    await run_cycle(factory, strat_id, user_id, engine,
                    signals=[make_signal(Direction.CLOSE, strat_id)], latest_close=110.0)

    ex = StrategyExecutor()
    inst = _fake_instance(strat_id, user_id, status="paper")
    await ex._rehydrate_risk_state(inst, factory)

    assert ex._risk._states[strat_id].daily_pnl == pytest.approx(200.0)


async def test_rehydrate_keeps_persisted_peak_equity(db):
    """Total-drawdown baseline survives a restart while underwater — it isn't reset to the
    depressed current equity."""
    from app.services.strategy_executor import StrategyExecutor

    factory, user_id, strat_id = db
    ex = StrategyExecutor()
    # Persisted historical peak far above the sim's current equity (SIM_STARTING_EQUITY).
    inst = _fake_instance(strat_id, user_id, status="paper", peak_equity=250_000.0)
    await ex._rehydrate_risk_state(inst, factory)
    assert ex._risk._states[strat_id].peak_equity == pytest.approx(250_000.0)


async def test_peak_equity_persisted_after_cycle(db, monkeypatch):
    from app.services.strategy_executor import StrategyExecutor
    from tests.conftest import make_bars

    factory, user_id, strat_id = db
    name = _register_long_strategy("_PeakStrategy", strat_id)
    monkeypatch.setattr(
        "app.domain.backtest.data_provider.fetch_ohlcv",
        lambda symbol, timeframe, limit=200: _as_coro(
            make_bars([100.0] * 60, symbol=SYMBOL, timeframe=Timeframe.D1)),
    )

    ex = StrategyExecutor()
    await ex._execute_once(strat_id, name, SYMBOL, Timeframe.D1, {}, user_id,
                           "paper", None, RiskConfig(), True, factory)

    async with factory() as s:
        inst = await s.get(StrategyInstance, strat_id)
        assert inst.peak_equity == pytest.approx(START_EQUITY)   # observed at cycle start


async def test_new_bar_gating(db, monkeypatch):
    """Signals are generated once per closed bar, not on every poll."""
    from app.domain.strategy.base import StrategyRegistry
    from app.models.db.signal_record import SignalRecord
    from app.services.strategy_executor import StrategyExecutor
    from tests.conftest import make_bars

    factory, user_id, strat_id = db
    calls = {"n": 0}

    class _CountingStrategy:
        def __init__(self, parameters=None, timeframe=None):
            self.parameters = parameters or {}

        async def generate_signals(self, data):
            calls["n"] += 1
            return [make_signal(Direction.LONG, strat_id)]

        async def on_fill(self, fill):
            return None

    StrategyRegistry.register(_CountingStrategy)
    ex = StrategyExecutor()

    async def run_once():
        await ex._execute_once(
            strat_id, "_CountingStrategy", SYMBOL, Timeframe.D1, {}, user_id,
            "paper", None, RiskConfig(), True, factory,
        )

    # Same bar polled twice → generate_signals called only once.
    bars_v1 = make_bars([100.0] * 60, symbol=SYMBOL, timeframe=Timeframe.D1)
    monkeypatch.setattr("app.domain.backtest.data_provider.fetch_ohlcv",
                        lambda symbol, timeframe, limit=200: _as_coro(bars_v1))
    await run_once()
    await run_once()
    assert calls["n"] == 1

    # A new bar (later timestamp) → generate again.
    bars_v2 = make_bars([100.0] * 61, symbol=SYMBOL, timeframe=Timeframe.D1)
    monkeypatch.setattr("app.domain.backtest.data_provider.fetch_ohlcv",
                        lambda symbol, timeframe, limit=200: _as_coro(bars_v2))
    await run_once()
    assert calls["n"] == 2

    # One SignalRecord per generation; only one entry order despite 3 polls.
    async with factory() as s:
        sigs = (await s.execute(
            select(SignalRecord).where(SignalRecord.strategy_instance_id == strat_id)
        )).scalars().all()
    assert len(list(sigs)) == 2
    opened = [r for r in await _order_records(factory, strat_id) if r.status == ACTION_OPENED_LONG]
    assert len(opened) == 1


async def _as_coro(value):
    return value


# ── Live broker path (fake adapter, no network) ──────────────────────────────────

class FakeLiveBroker:
    """Stands in for a real BrokerAdapter resolved from a broker connection.
    No set_mark (unlike the simulator) — mirrors a real broker."""

    def __init__(self, equity: float = 100_000.0, positions=None):
        self.broker_id = "bybit"
        self.orders = []
        self._equity = equity
        self._positions = positions or []

    async def connect(self):
        return None

    async def disconnect(self):
        return None

    async def get_account(self):
        return Account(broker_id="bybit", account_id="acc", equity=self._equity,
                       cash=self._equity, buying_power=self._equity, paper_mode=False,
                       updated_at=datetime.now(timezone.utc))

    async def get_positions(self):
        return self._positions

    async def place_order(self, order):
        self.orders.append(order)
        return OrderResult(order_id=order.order_id, broker_order_id="bybit-123",
                           status=OrderStatus.FILLED, submitted_at=datetime.now(timezone.utc))


def _register_long_strategy(name: str, strat_id):
    from app.domain.strategy.base import StrategyRegistry

    class _Strat:
        def __init__(self, parameters=None, timeframe=None):
            self.parameters = parameters or {}

        async def generate_signals(self, data):
            return [make_signal(Direction.LONG, strat_id)]

        async def on_fill(self, fill):
            return None

    _Strat.__name__ = name
    StrategyRegistry.register(_Strat)
    return name


async def test_live_path_places_order_via_broker(db, monkeypatch):
    from app.models.db.broker_connection import BrokerConnection
    from app.services.strategy_executor import StrategyExecutor
    from tests.conftest import make_bars

    factory, user_id, strat_id = db
    conn_id = uuid.uuid4()
    async with factory() as s:
        s.add(BrokerConnection(
            id=conn_id, user_id=user_id, broker_id="bybit",
            encrypted_api_key="x", encrypted_secret_key="x", label="Bybit",
            is_paper=False, is_active=True,
        ))
        await s.commit()

    name = _register_long_strategy("_LiveLongStrategy", strat_id)
    fake = FakeLiveBroker()
    monkeypatch.setattr("app.services.broker_service._build_adapter", lambda conn: fake)
    monkeypatch.setattr(
        "app.domain.backtest.data_provider.fetch_ohlcv",
        lambda symbol, timeframe, limit=200: _as_coro(
            make_bars([100.0] * 60, symbol=SYMBOL, timeframe=Timeframe.D1)),
    )

    ex = StrategyExecutor()
    await ex._execute_once(strat_id, name, SYMBOL, Timeframe.D1, {}, user_id,
                           "live", conn_id, RiskConfig(), True, factory)

    assert len(fake.orders) == 1
    assert fake.orders[0].side == OrderSide.BUY
    opened = [r for r in await _order_records(factory, strat_id) if r.status == ACTION_OPENED_LONG]
    assert len(opened) == 1
    assert opened[0].broker_order_id == "bybit-123"


async def test_executor_runs_user_strategy(db, monkeypatch):
    """The executor loads user_strategies/*.py and runs AlwaysLong end to end."""
    from app.services.strategy_executor import StrategyExecutor
    from tests.conftest import make_bars

    factory, user_id, strat_id = db
    monkeypatch.setattr(
        "app.domain.backtest.data_provider.fetch_ohlcv",
        lambda symbol, timeframe, limit=200: _as_coro(
            make_bars([100.0] * 60, symbol=SYMBOL, timeframe=Timeframe.D1)),
    )

    ex = StrategyExecutor()
    await ex._execute_once(strat_id, "AlwaysLong", SYMBOL, Timeframe.D1, {}, user_id,
                           "paper", None, RiskConfig(), True, factory)

    opened = [r for r in await _order_records(factory, strat_id) if r.status == ACTION_OPENED_LONG]
    assert len(opened) == 1


def _fake_position(symbol: str) -> Position:
    return Position(
        symbol=symbol, market_type=MarketType.CRYPTO, broker_id="bybit",
        quantity=1.0, avg_entry_price=100.0, current_price=100.0,
        unrealized_pnl=0.0, unrealized_pnl_pct=0.0, opened_at=datetime.now(timezone.utc),
    )


async def _seed_broker_conn(factory, user_id, conn_id):
    from app.models.db.broker_connection import BrokerConnection
    async with factory() as s:
        s.add(BrokerConnection(
            id=conn_id, user_id=user_id, broker_id="bybit",
            encrypted_api_key="x", encrypted_secret_key="x", is_paper=False, is_active=True,
        ))
        await s.commit()


async def test_rehydrate_counts_only_strategy_symbol(db, monkeypatch):
    """A live broker's account-wide positions must not inflate the strategy's count."""
    from app.services.strategy_executor import StrategyExecutor

    factory, user_id, strat_id = db
    conn_id = uuid.uuid4()
    await _seed_broker_conn(factory, user_id, conn_id)

    fake = FakeLiveBroker(positions=[
        _fake_position(SYMBOL), _fake_position("ETHUSDT"), _fake_position("ETHUSDT"),
    ])
    monkeypatch.setattr("app.services.broker_service._build_adapter", lambda conn: fake)

    ex = StrategyExecutor()
    inst = _fake_instance(strat_id, user_id, status="live", broker_connection_id=conn_id)
    await ex._rehydrate_risk_state(inst, factory)

    assert ex._risk._states[strat_id].open_position_count == 1   # only BTCUSDT


async def test_reactivation_clears_prior_halt(db):
    from app.services.strategy_executor import StrategyExecutor

    factory, user_id, strat_id = db
    ex = StrategyExecutor()
    ex._risk.seed_state(strat_id, equity=100_000, open_position_count=0)
    ex._risk._states[strat_id].halted = True

    inst = _fake_instance(strat_id, user_id, status="paper")
    ex.notify_status_change(inst, RiskConfig(), factory)   # re-activate → authorizes halt release
    try:
        assert ex._risk._states[strat_id].halted is False
    finally:
        ex.shutdown()


async def test_stop_clears_last_bar_ts(db):
    from app.services.strategy_executor import StrategyExecutor

    factory, user_id, strat_id = db
    ex = StrategyExecutor()
    inst = _fake_instance(strat_id, user_id, status="paper")
    ex._launch(inst, RiskConfig(), factory)
    ex._last_bar_ts[str(strat_id)] = "sentinel"
    ex._stop(str(strat_id))
    assert str(strat_id) not in ex._last_bar_ts
    ex.shutdown()


async def test_live_adapter_failure_increments_error_count(db, monkeypatch):
    """A broker connection error records an error outcome and advances error_count
    (rather than propagating and retrying forever)."""
    from app.services.strategy_executor import StrategyExecutor
    from tests.conftest import make_bars

    factory, user_id, strat_id = db
    conn_id = uuid.uuid4()
    await _seed_broker_conn(factory, user_id, conn_id)
    name = _register_long_strategy("_LiveBoomStrategy", strat_id)

    class BoomBroker(FakeLiveBroker):
        async def connect(self):
            raise RuntimeError("broker down")

    monkeypatch.setattr("app.services.broker_service._build_adapter", lambda conn: BoomBroker())
    monkeypatch.setattr(
        "app.domain.backtest.data_provider.fetch_ohlcv",
        lambda symbol, timeframe, limit=200: _as_coro(
            make_bars([100.0] * 60, symbol=SYMBOL, timeframe=Timeframe.D1)),
    )

    ex = StrategyExecutor()
    await ex._execute_once(strat_id, name, SYMBOL, Timeframe.D1, {}, user_id,
                           "live", conn_id, RiskConfig(), True, factory)

    assert any(r.status == ACTION_ERROR for r in await _order_records(factory, strat_id))
    async with factory() as s:
        inst = await s.get(StrategyInstance, strat_id)
        assert inst.error_count == 1


async def test_db_error_in_paper_cycle_still_advances_error_count(db, monkeypatch):
    """A DB-origin failure poisons the session; the executor must roll back so the error
    record + error_count commit rather than raising PendingRollbackError and retrying forever."""
    from sqlalchemy import text
    from app.domain.broker.adapters.simulated_adapter import SimulatedBrokerAdapter
    from app.services.strategy_executor import StrategyExecutor
    from tests.conftest import make_bars

    factory, user_id, strat_id = db
    name = _register_long_strategy("_DbBoomStrategy", strat_id)
    monkeypatch.setattr(
        "app.domain.backtest.data_provider.fetch_ohlcv",
        lambda symbol, timeframe, limit=200: _as_coro(
            make_bars([100.0] * 60, symbol=SYMBOL, timeframe=Timeframe.D1)),
    )

    async def boom_get_account(self):
        await self._session.execute(text("SELECT * FROM __nonexistent__"))   # poisons the session

    monkeypatch.setattr(SimulatedBrokerAdapter, "get_account", boom_get_account)

    ex = StrategyExecutor()
    await ex._execute_once(strat_id, name, SYMBOL, Timeframe.D1, {}, user_id,
                           "paper", None, RiskConfig(), True, factory)

    assert any(r.status == ACTION_ERROR for r in await _order_records(factory, strat_id))
    async with factory() as s:
        inst = await s.get(StrategyInstance, strat_id)
        assert inst.error_count == 1


async def test_live_path_without_connection_records_error(db, monkeypatch):
    from app.services.strategy_executor import StrategyExecutor
    from tests.conftest import make_bars

    factory, user_id, strat_id = db
    name = _register_long_strategy("_LiveNoConnStrategy", strat_id)
    monkeypatch.setattr(
        "app.domain.backtest.data_provider.fetch_ohlcv",
        lambda symbol, timeframe, limit=200: _as_coro(
            make_bars([100.0] * 60, symbol=SYMBOL, timeframe=Timeframe.D1)),
    )

    ex = StrategyExecutor()
    await ex._execute_once(strat_id, name, SYMBOL, Timeframe.D1, {}, user_id,
                           "live", None, RiskConfig(), True, factory)   # no broker connection

    records = await _order_records(factory, strat_id)
    assert any(r.status == ACTION_ERROR and r.reason == "no active broker connection" for r in records)
