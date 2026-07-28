"""Position sizing in the backtest engine.

The engine must size entries as ``capital * position_size_pct`` (the same risk model
the live executor uses via ``position_sizer.size_entry``), so a backtest's equity
curve reflects the magnitude the strategy would actually trade live — not an all-in
(100%-of-capital) curve that overstates returns ~50x at the 2% default.
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
            return [self._sig(data, Direction.LONG)]   # fills at bar 3 open (100)
        if idx == 5:
            return [self._sig(data, Direction.CLOSE)]   # fills at bar 6 open (110)
        return []


def _bar(i, c):
    return OHLCV(
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
        symbol="X", open=c, high=c, low=c, close=c, volume=1.0, timeframe=Timeframe.D1,
    )


# Entry fills at 100, exit at 110 → a +10% move in price.
_PRICES = [100, 100, 100, 100, 100, 110, 110, 110, 110]


async def _run(position_size_pct):
    bars = [_bar(i, p) for i, p in enumerate(_PRICES)]
    engine = BacktestEngine(_LongThenClose(), bars, initial_capital=10_000,
                            commission_pct=0.0, warmup_bars=2, position_size_pct=position_size_pct)
    return await engine.run()


async def test_two_percent_sizing_scales_return_to_exposure():
    # 2% of 10k = 200 exposed; a +10% price move → +0.2% on the whole account.
    result = await _run(0.02)
    assert result.metrics.total_return_pct == pytest.approx(0.2, abs=0.01)
    assert result.trades[0].pnl == pytest.approx(20.0, abs=0.5)


async def test_full_sizing_is_all_in():
    # position_size_pct=1.0 (the engine default) → fully invested, +10%.
    result = await _run(1.0)
    assert result.metrics.total_return_pct == pytest.approx(10.0, abs=0.01)


async def test_engine_defaults_to_all_in_when_size_pct_omitted():
    # Back-compat: constructing the engine without the arg keeps the old all-in behavior,
    # so direct-engine unit tests remain valid. The service supplies the real (live) pct.
    bars = [_bar(i, p) for i, p in enumerate(_PRICES)]
    engine = BacktestEngine(_LongThenClose(), bars, initial_capital=10_000,
                            commission_pct=0.0, warmup_bars=2)
    result = await engine.run()
    assert result.metrics.total_return_pct == pytest.approx(10.0, abs=0.01)
