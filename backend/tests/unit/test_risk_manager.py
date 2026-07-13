from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.core.enums import OrderSide, OrderType
from app.core.types import Account, Order, RiskConfig, RiskVeto
from app.domain.risk.risk_manager import RiskManager

pytestmark = pytest.mark.asyncio


def _account(equity: float) -> Account:
    return Account(
        broker_id="sim", account_id="a", equity=equity, cash=equity,
        buying_power=equity, paper_mode=True, updated_at=datetime.now(timezone.utc),
    )


def _order(sid: uuid.UUID, qty: float = 1.0, price: float = 100.0) -> Order:
    return Order(
        order_id=uuid.uuid4(), strategy_id=sid, broker_id="sim", symbol="BTCUSDT",
        side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=qty,
        limit_price=price, created_at=datetime.now(timezone.utc),
    )


def test_seed_state_sets_peak_equity_and_positions():
    rm = RiskManager()
    sid = uuid.uuid4()
    rm.seed_state(sid, equity=50_000, open_position_count=2)
    state = rm._states[sid]
    assert state.peak_equity == 50_000
    assert state.open_position_count == 2


def test_seed_state_never_lowers_existing_peak():
    rm = RiskManager()
    sid = uuid.uuid4()
    rm.seed_state(sid, equity=80_000, open_position_count=1)
    rm.seed_state(sid, equity=60_000, open_position_count=1)
    assert rm._states[sid].peak_equity == 80_000


async def test_seeded_open_positions_enforce_max_after_restart():
    rm = RiskManager()
    sid = uuid.uuid4()
    rm.seed_state(sid, equity=100_000, open_position_count=5)
    verdict = await rm.approve_order(_order(sid), _account(100_000), RiskConfig(max_open_positions=5))
    assert isinstance(verdict, RiskVeto)
    assert verdict.rule_violated == "max_open_positions"


def test_observe_equity_tracks_high_water_mark():
    rm = RiskManager()
    sid = uuid.uuid4()
    rm.observe_equity(sid, 100_000)
    rm.observe_equity(sid, 105_000)
    rm.observe_equity(sid, 102_000)      # a dip doesn't lower the peak
    assert rm.peak_equity(sid) == 105_000


def test_seed_state_keeps_persisted_peak_over_depressed_equity():
    # Restart while underwater: persisted peak 100k must win over current equity 92k.
    rm = RiskManager()
    sid = uuid.uuid4()
    rm.seed_state(sid, equity=92_000, open_position_count=0, peak_equity=100_000)
    assert rm._states[sid].peak_equity == 100_000


async def test_order_sized_exactly_to_cap_is_approved():
    # Sizer targets notional == equity*pct; qty*price can float a few ULPs above the cap.
    rm = RiskManager()
    sid = uuid.uuid4()
    cfg = RiskConfig(max_position_size_pct=0.02)
    qty = (10_000 * 0.02) / 11.0        # 200/11 — a price that trips exact float equality
    verdict = await rm.approve_order(_order(sid, qty=qty, price=11.0), _account(10_000), cfg)
    assert verdict is True


async def test_vetoed_order_does_not_consume_rate_budget():
    rm = RiskManager()
    sid = uuid.uuid4()
    cfg = RiskConfig(max_position_size_pct=0.02, max_orders_per_minute=1)
    # Oversized → vetoed by position-size; must NOT increment the per-minute counter.
    oversized = await rm.approve_order(_order(sid, qty=1000, price=100), _account(100_000), cfg)
    assert isinstance(oversized, RiskVeto) and oversized.rule_violated == "max_position_size_pct"
    # A subsequent correctly-sized order is the first to reach the rate check → approved.
    ok = await rm.approve_order(_order(sid, qty=10, price=100), _account(100_000), cfg)
    assert ok is True
