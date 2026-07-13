from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.enums import Direction, MarketType, SignalSource, Timeframe
from app.core.types import MarketData, OHLCV, Signal
from app.domain.backtest.engine import BacktestEngine

pytestmark = pytest.mark.asyncio


class _AlwaysLong:
    name = "AL"
    timeframe = Timeframe.D1

    async def generate_signals(self, data: MarketData):
        return [Signal(
            signal_id=uuid4(), strategy_id=uuid4(), symbol=data.symbol,
            market_type=MarketType.CRYPTO, timeframe=Timeframe.D1, direction=Direction.LONG,
            confidence=1.0, source=SignalSource.QUANT, generated_at=datetime.now(timezone.utc),
        )]


def _bar(i, o, h, l, c):
    return OHLCV(
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
        symbol="BTCUSDT", open=o, high=h, low=l, close=c, volume=1000.0, timeframe=Timeframe.D1,
    )


async def _run(bars, **kw):
    engine = BacktestEngine(_AlwaysLong(), bars, initial_capital=10_000,
                            commission_pct=0.0, warmup_bars=2, **kw)
    return await engine.run()


async def test_stop_loss_exits_at_stop_price():
    bars = [
        _bar(0, 100, 100, 100, 100), _bar(1, 100, 100, 100, 100),
        _bar(2, 100, 100, 100, 100),   # LONG here → fill at bar3 open (100)
        _bar(3, 100, 101, 99, 100),    # low 99 > stop 98 → no exit
        _bar(4, 100, 101, 95, 100),    # low 95 ≤ stop 98 → exit at 98
        _bar(5, 100, 100, 100, 100),
    ]
    result = await _run(bars, stop_loss_pct=0.02)
    assert any(abs(t.exit_price - 98.0) < 1e-6 for t in result.trades), \
        [t.exit_price for t in result.trades]


async def test_take_profit_exits_at_target_price():
    bars = [
        _bar(0, 100, 100, 100, 100), _bar(1, 100, 100, 100, 100),
        _bar(2, 100, 100, 100, 100),   # LONG → fill at 100
        _bar(3, 100, 106, 100, 100),   # high 106 ≥ target 105 → exit at 105
        _bar(4, 100, 100, 100, 100),
    ]
    result = await _run(bars, take_profit_pct=0.05)
    assert any(abs(t.exit_price - 105.0) < 1e-6 for t in result.trades), \
        [t.exit_price for t in result.trades]


async def test_no_sl_tp_means_no_intrabar_exit():
    # Same dip as the stop test, but no stop configured → position is not closed intrabar.
    bars = [
        _bar(0, 100, 100, 100, 100), _bar(1, 100, 100, 100, 100),
        _bar(2, 100, 100, 100, 100), _bar(3, 100, 101, 90, 100),
        _bar(4, 100, 100, 100, 100),
    ]
    result = await _run(bars)   # no SL/TP
    # No trade exits at the 90-ish dip; the only close is the end-of-data flatten at 100.
    assert all(abs(t.exit_price - 100.0) < 1e-6 for t in result.trades), \
        [t.exit_price for t in result.trades]
