"""An update restarts the app at an arbitrary moment. A running bot must carry on as if nothing
happened: no second entry on the bar it already acted on, same paper account, same position.

A restart is simulated the way it really happens: the in-memory executor is thrown away
(including its "last bar processed" cursor) and a brand-new one boots from the database and
processes the SAME bar again.
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.api.deps import LOCAL_USER_ID
from app.core.enums import Direction, MarketType, SignalSource, Timeframe
from app.core.types import RiskConfig, Signal
from app.domain.strategy.base import StrategyRegistry

pytestmark = pytest.mark.asyncio
API = "/api/v1"
SYMBOL = "BTCUSDT"


def _register(name: str, fires_on_every_bar: bool):
    """`fires_on_every_bar=True`: state strategy (TrendFilter-like, LONG every bar while in).
    False: event strategy (MACD-like, LONG only on the bar the cross happens — the bar the
    restart re-processes)."""

    class _S:
        def __init__(self, parameters=None, timeframe=None):
            self.parameters = parameters or {}

        async def generate_signals(self, data):
            if not fires_on_every_bar and len(data.bars) != 60:
                return []
            return [Signal(signal_id=uuid4(), strategy_id=uuid4(), symbol=data.symbol,
                           market_type=MarketType.CRYPTO, timeframe=Timeframe.D1,
                           direction=Direction.LONG, confidence=1.0, source=SignalSource.QUANT,
                           generated_at=datetime.now(timezone.utc))]

        async def on_fill(self, fill):
            return None

    _S.__name__ = name
    StrategyRegistry.register(_S)
    return name


async def _cycle(executor, sid, class_name):
    from app.db.base import AsyncSessionLocal
    return await executor._execute_once(
        sid, class_name, SYMBOL, Timeframe.D1, {}, LOCAL_USER_ID, "paper", None,
        RiskConfig(max_position_size_pct=0.1), False, AsyncSessionLocal,
    )


async def _account(sid):
    from sqlalchemy import select
    from app.db.base import AsyncSessionLocal
    from app.models.db.sim_ledger import SimAccount, SimPosition
    async with AsyncSessionLocal() as s:
        acct = (await s.execute(select(SimAccount).where(SimAccount.strategy_instance_id == sid))).scalar_one()
        pos = (await s.execute(select(SimPosition).where(SimPosition.strategy_instance_id == sid))).scalars().all()
        return acct.cash, [(p.symbol, p.quantity) for p in pos]


@pytest.mark.parametrize("fires_on_every_bar", [True, False], ids=["state-strategy", "event-strategy"])
async def test_restart_mid_bar_does_not_trade_twice(client, monkeypatch, fires_on_every_bar):
    from app.services.strategy_executor import StrategyExecutor
    from tests.conftest import make_bars

    async def fake_fetch(symbol, timeframe, limit=None):
        return make_bars([100.0] * 60, symbol=SYMBOL, timeframe=Timeframe.D1)

    monkeypatch.setattr("app.domain.backtest.data_provider.fetch_ohlcv", fake_fetch)
    class_name = _register(f"_Restart{'State' if fires_on_every_bar else 'Event'}", fires_on_every_bar)
    resp = await client.post(f"{API}/strategies", json={
        "class_name": class_name, "symbol": SYMBOL, "timeframe": "1d", "parameters": {},
        "execution": {"size_pct": 0.1, "allow_short": False},
    })
    sid = uuid.UUID(resp.json()["id"])

    before_restart = StrategyExecutor(notify=lambda t: None)
    assert await _cycle(before_restart, sid, class_name)
    cash_before, positions_before = await _account(sid)
    assert positions_before, "the first cycle must have opened a position"

    # ── "update": process dies, a new one boots from the DB and re-processes the same bar ──
    after_restart = StrategyExecutor(notify=lambda t: None)
    assert await _cycle(after_restart, sid, class_name)
    assert await _cycle(after_restart, sid, class_name)   # and keeps polling

    cash_after, positions_after = await _account(sid)
    assert positions_after == positions_before            # same position, not doubled
    assert cash_after == pytest.approx(cash_before)       # no second purchase
    orders = (await client.get(f"{API}/strategies/{sid}/orders")).json()
    assert Counter(o["status"] for o in orders) == {"opened_long": 1}
