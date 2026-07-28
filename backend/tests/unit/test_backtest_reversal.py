"""The backtest engine must do FULL reversals like the live executor: a direction flip
(long→short or short→long) closes the current position AND opens the opposite one in the
same step. Previously the backtest dropped the second leg (SHORT-while-long only closed;
LONG-while-short was ignored), so a flip strategy traded differently in backtest vs live.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.enums import Direction, MarketType, SignalSource, Timeframe
from app.core.types import MarketData, OHLCV, Signal
from app.domain.backtest.engine import BacktestEngine

pytestmark = pytest.mark.asyncio


class _Scripted:
    """Emits a scripted direction at specific bar indices."""
    name = "S"
    timeframe = Timeframe.D1

    def __init__(self, script: dict[int, Direction]):
        self._script = script

    async def generate_signals(self, data: MarketData):
        idx = len(data.bars) - 1
        d = self._script.get(idx)
        if d is None:
            return []
        return [Signal(
            signal_id=uuid4(), strategy_id=uuid4(), symbol=data.symbol,
            market_type=MarketType.CRYPTO, timeframe=Timeframe.D1, direction=d,
            confidence=1.0, source=SignalSource.QUANT, generated_at=datetime.now(timezone.utc),
        )]


def _bar(i, c):
    return OHLCV(
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
        symbol="X", open=c, high=c, low=c, close=c, volume=1.0, timeframe=Timeframe.D1,
    )


async def _run(script, prices, *, allow_short=True):
    bars = [_bar(i, p) for i, p in enumerate(prices)]
    engine = BacktestEngine(_Scripted(script), bars, initial_capital=10_000,
                            commission_pct=0.0, warmup_bars=2, allow_short=allow_short)
    return await engine.run()


async def test_long_to_short_flip_opens_the_short(script_prices=None):
    # LONG at bar 2 (fills bar 3), SHORT at bar 5 (fills bar 6): must close long + open short.
    script = {2: Direction.LONG, 5: Direction.SHORT}
    result = await _run(script, [100] * 12)
    sides = [t.side for t in result.trades]
    assert "long" in sides and "short" in sides, sides
    # Exactly one long (closed at the flip) and one short (opened at the flip, closed at end).
    assert sides.count("long") == 1
    assert sides.count("short") == 1


async def test_short_to_long_flip_is_not_ignored():
    # SHORT at bar 2, LONG at bar 5: the LONG must reverse the short, not be ignored.
    script = {2: Direction.SHORT, 5: Direction.LONG}
    result = await _run(script, [100] * 12)
    sides = [t.side for t in result.trades]
    assert sides.count("short") == 1
    assert sides.count("long") == 1


async def test_flip_respects_allow_short_false():
    # LONG then SHORT, but shorting disabled → close the long, do NOT open a short.
    script = {2: Direction.LONG, 5: Direction.SHORT}
    result = await _run(script, [100] * 12, allow_short=False)
    sides = [t.side for t in result.trades]
    assert sides == ["long"], sides   # only the long, closed by the (suppressed) reversal


async def test_repeated_same_direction_signal_is_held_not_rechurned():
    # SHORT at bar 2 and again at bar 4 while already short → the second is a no-op (one short trade).
    script = {2: Direction.SHORT, 4: Direction.SHORT}
    result = await _run(script, [100] * 12)
    assert [t.side for t in result.trades] == ["short"], [t.side for t in result.trades]
