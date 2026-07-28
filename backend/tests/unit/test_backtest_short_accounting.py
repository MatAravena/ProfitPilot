"""Cash-accounting correctness for SHORT positions in the backtest engine.

Regression guard for a bug where closing a short *added* the buyback notional to
cash (correct only for a long), so a flat short reported +200% return / 3x equity
even though the trade's own pnl was 0. Closing a short must *subtract* the cost of
buying the units back.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.enums import Direction, MarketType, SignalSource, Timeframe
from app.core.types import MarketData, OHLCV, Signal
from app.domain.backtest.engine import BacktestEngine

pytestmark = pytest.mark.asyncio


class _ShortThenClose:
    """SHORT at bar index 2 (fills next open), CLOSE at bar index 5."""

    name = "S"
    timeframe = Timeframe.D1

    def _sig(self, data, direction):
        return Signal(
            signal_id=uuid4(), strategy_id=uuid4(), symbol=data.symbol,
            market_type=MarketType.CRYPTO, timeframe=Timeframe.D1, direction=direction,
            confidence=1.0, source=SignalSource.QUANT, generated_at=datetime.now(timezone.utc),
        )

    async def generate_signals(self, data: MarketData):
        idx = len(data.bars) - 1
        if idx == 2:
            return [self._sig(data, Direction.SHORT)]
        if idx == 5:
            return [self._sig(data, Direction.CLOSE)]
        return []


def _bar(i, c):
    return OHLCV(
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
        symbol="X", open=c, high=c, low=c, close=c, volume=1.0, timeframe=Timeframe.D1,
    )


async def _run(prices, commission_pct=0.0):
    bars = [_bar(i, p) for i, p in enumerate(prices)]
    engine = BacktestEngine(_ShortThenClose(), bars, initial_capital=10_000,
                            commission_pct=commission_pct, warmup_bars=2)
    return await engine.run()


async def test_flat_short_is_break_even():
    # Enter and exit a short at 100, zero commission → ~0% return, equity back to start.
    result = await _run([100.0] * 9)
    assert result.metrics.total_trades == 1
    assert abs(result.metrics.total_return_pct) < 1e-6, result.metrics.total_return_pct
    assert abs(result.equity_curve[-1].value - 10_000) < 1e-6, result.equity_curve[-1].value


async def test_profitable_short_gains_when_price_falls():
    # Short at 100, price falls to 90 by the close bar → ~+10% (all-in, 100 units × 10).
    result = await _run([100, 100, 100, 100, 100, 90, 90, 90, 90])
    assert result.trades[0].side == "short"
    assert result.trades[0].pnl == pytest.approx(1000.0, abs=1.0)
    assert result.metrics.total_return_pct == pytest.approx(10.0, abs=0.1)


async def test_losing_short_loses_when_price_rises():
    # Short at 100, price rises to 110 → ~-10%.
    result = await _run([100, 100, 100, 100, 100, 110, 110, 110, 110])
    assert result.trades[0].pnl == pytest.approx(-1000.0, abs=1.0)
    assert result.metrics.total_return_pct == pytest.approx(-10.0, abs=0.1)
