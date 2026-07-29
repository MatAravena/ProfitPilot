"""End-to-end 'full live/paper usage' test.

Drives the REAL StrategyExecutor for a paper strategy across three poll cycles
(long → reversal to short → close) and verifies exactly what the strategy-detail
page consumes:

  - GET /strategies/{id}/orders   (order records → chart markers + order table)
  - GET /signals?strategy_id=...  (signal history)
  - strategy.signal / strategy.order WebSocket broadcasts (live updates)

Everything runs against the shared in-memory DB (the app and the executor's
AsyncSessionLocal point at the same engine), so this exercises the whole chain:
create via API → executor polls data → RiskManager → simulated fill (with costs) →
persist → broadcast → read back via the API the frontend actually calls.
"""
from __future__ import annotations

import pytest

from app.api.deps import LOCAL_USER_ID
from app.core.enums import Direction, Timeframe
from app.core.types import RiskConfig

pytestmark = pytest.mark.asyncio

SYMBOL = "BTCUSDT"
API = "/api/v1"


async def _create_tables():
    from app.db.base import engine, Base
    import app.models.db  # noqa: F401 — registers ORM models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _register_scripted_strategy():
    """A strategy that flips by bar count: 60 bars → LONG, 61 → SHORT (reversal), 62 → CLOSE."""
    from app.domain.strategy.base import StrategyRegistry
    from app.core.types import Signal
    from app.core.enums import MarketType, SignalSource
    from datetime import datetime, timezone
    from uuid import uuid4

    class _ScriptedFlip:
        def __init__(self, parameters=None, timeframe=None):
            self.parameters = parameters or {}
            self.timeframe = timeframe

        async def generate_signals(self, data):
            n = len(data.bars)
            direction = {60: Direction.LONG, 61: Direction.SHORT, 62: Direction.CLOSE}.get(n)
            if direction is None:
                return []
            return [Signal(
                signal_id=uuid4(), strategy_id=uuid4(), symbol=data.symbol,
                market_type=MarketType.CRYPTO, timeframe=Timeframe.D1, direction=direction,
                confidence=0.9, source=SignalSource.QUANT, generated_at=datetime.now(timezone.utc),
            )]

        async def on_fill(self, fill):
            return None

    StrategyRegistry.register(_ScriptedFlip)
    return "_ScriptedFlip"


async def test_paper_strategy_full_lifecycle(client, monkeypatch):
    await _create_tables()
    from tests.conftest import make_bars
    from app.db.base import AsyncSessionLocal
    from app.services.strategy_executor import StrategyExecutor
    import app.api.ws.manager as ws_manager

    class_name = _register_scripted_strategy()

    # Each cycle exposes one more (newer) bar so new-bar gating fires every cycle.
    # Latest close per cycle drives the paper fill mark: open long @100, flip @110, close @105.
    prices_by_cycle = {
        1: [100.0] * 60,
        2: [100.0] * 60 + [110.0],
        3: [100.0] * 60 + [110.0, 105.0],
    }
    cycle = {"n": 0}

    async def fake_fetch(symbol, timeframe, limit=200):
        return make_bars(prices_by_cycle[cycle["n"]], symbol=SYMBOL, timeframe=Timeframe.D1)

    monkeypatch.setattr("app.domain.backtest.data_provider.fetch_ohlcv", fake_fetch)

    # Capture WebSocket broadcasts (what the FE listens to for live updates).
    broadcasts: list[tuple[str, dict]] = []

    async def spy_broadcast(channel, data):
        broadcasts.append((channel, data))

    monkeypatch.setattr(ws_manager.manager, "broadcast", spy_broadcast)

    # 1) Create the paper strategy via the real API.
    resp = await client.post(f"{API}/strategies", json={
        "class_name": class_name, "symbol": SYMBOL, "timeframe": "1d",
        "parameters": {}, "execution": {"size_pct": 0.02, "allow_short": True},
    })
    assert resp.status_code == 201, resp.text
    strat_id = resp.json()["id"]

    # 2) Drive the real executor for three poll cycles (long → reversal → close).
    executor = StrategyExecutor()
    import uuid
    for n in (1, 2, 3):
        cycle["n"] = n
        keep_going = await executor._execute_once(
            uuid.UUID(strat_id), class_name, SYMBOL, Timeframe.D1, {}, LOCAL_USER_ID,
            "paper", None, RiskConfig(), True, AsyncSessionLocal,
        )
        assert keep_going is True

    # 3) Read back exactly what the strategy-detail page fetches.
    orders_resp = await client.get(f"{API}/strategies/{strat_id}/orders")
    assert orders_resp.status_code == 200, orders_resp.text
    orders = orders_resp.json()
    # Four order attempts: the entry, the reversal (close + opposite open), and the final close.
    # (Ordering of same-cycle rows isn't meaningful — assert the multiset; chronology is checked
    # via the ordered broadcast stream below.)
    from collections import Counter
    assert Counter(o["status"] for o in orders) == {"opened_long": 1, "opened_short": 1, "closed": 2}

    # The reversal cycle produced a close (reason "reversal") AND an opposite open — the trade the
    # backtest used to drop. Both closes realize a profit (long 100→110, short 110→105), net of costs.
    reversal_close = next(o for o in orders if o["status"] == "closed" and o["reason"] == "reversal")
    assert reversal_close["realized_pnl"] is not None and reversal_close["realized_pnl"] > 0
    assert all(o["realized_pnl"] > 0 for o in orders if o["status"] == "closed")
    # The opened_short carries a real simulated fill (price + qty), not an empty record.
    short_open = next(o for o in orders if o["status"] == "opened_short")
    assert short_open["avg_price"] is not None and short_open["filled_qty"]

    # Signals history the page renders (3 generated: long, short, close).
    sig_resp = await client.get(f"{API}/signals", params={"strategy_id": strat_id, "limit": 200})
    assert sig_resp.status_code == 200, sig_resp.text
    directions = {s["direction"] for s in sig_resp.json()}
    assert {"long", "short", "close"} <= directions

    # 4) WebSocket broadcasts the FE subscribes to for live updates — captured in execution order.
    channels = [c for c, _ in broadcasts]
    assert channels.count("strategy.signal") == 3            # one per generated signal
    order_events = [d for c, d in broadcasts if c == "strategy.order"]
    # Chronological action sequence: entry → reversal close → opposite open → final close.
    assert [e["action"] for e in order_events] == ["opened_long", "closed", "opened_short", "closed"]
    assert all(e["strategy_id"] == strat_id for e in order_events)
