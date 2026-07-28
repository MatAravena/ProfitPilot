"""Realistic trading-cost model: adverse slippage on every fill.

Commission is a symmetric fee; slippage is an *adverse price move* (you buy a touch
higher and sell a touch lower than the reference price — crossing the spread + market
impact). It must make every backtest strictly more conservative and is applied to all
fills: entries, signal-closes, and stop/target exits.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.enums import Direction, MarketType, SignalSource, Timeframe
from app.core.types import MarketData, OHLCV, Signal
from app.domain.backtest.engine import BacktestEngine

pytestmark = pytest.mark.asyncio


class _LongThenClose:
    name = "L"
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
            return [self._sig(data, Direction.LONG)]
        if idx == 5:
            return [self._sig(data, Direction.CLOSE)]
        return []


def _bar(i, c):
    return OHLCV(
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
        symbol="X", open=c, high=c, low=c, close=c, volume=1.0, timeframe=Timeframe.D1,
    )


async def _run(prices, *, slippage_pct=0.0, position_size_pct=1.0, commission_pct=0.0):
    bars = [_bar(i, p) for i, p in enumerate(prices)]
    engine = BacktestEngine(
        _LongThenClose(), bars, initial_capital=10_000, commission_pct=commission_pct,
        warmup_bars=2, position_size_pct=position_size_pct, slippage_pct=slippage_pct,
    )
    return await engine.run()


async def test_slippage_costs_a_flat_round_trip_two_crossings():
    # Buy at 100 and sell at 100 (flat), 1% slippage each side, all-in → ~-2% (enter high, exit low).
    result = await _run([100] * 9, slippage_pct=0.01)
    assert result.metrics.total_return_pct == pytest.approx(-1.99, abs=0.05)
    assert result.trades[0].entry_price == pytest.approx(101.0, abs=1e-6)   # bought 1% higher
    assert result.trades[0].exit_price == pytest.approx(99.0, abs=1e-6)     # sold 1% lower


async def test_slippage_reduces_a_winners_return():
    prices = [100, 100, 100, 100, 100, 110, 110, 110, 110]   # +10% move
    clean = await _run(prices, slippage_pct=0.0)
    slipped = await _run(prices, slippage_pct=0.005)
    assert slipped.metrics.total_return_pct < clean.metrics.total_return_pct


async def test_no_slippage_by_default_is_backward_compatible():
    # Engine default slippage is 0 → a flat round trip is break-even (existing behavior).
    result = await _run([100] * 9)
    assert result.metrics.total_return_pct == pytest.approx(0.0, abs=1e-9)
