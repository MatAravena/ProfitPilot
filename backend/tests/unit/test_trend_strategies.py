"""Signal logic of the trend-family built-ins, on hand-made series."""
from __future__ import annotations

import pytest

from app.core.enums import Direction, Timeframe
from app.core.types import MarketData
from app.domain.strategy.examples.trend import DonchianBreakout, RsiPullbackInTrend, TrendFilter
from tests.conftest import make_bars

pytestmark = pytest.mark.asyncio


async def _signal(strategy, closes):
    data = MarketData(symbol="BTCUSDT", timeframe=Timeframe.D1, bars=make_bars(closes))
    out = await strategy.generate_signals(data)
    return out[-1].direction if out else None


# ── DonchianBreakout ─────────────────────────────────────────────────────────

async def test_donchian_goes_long_on_a_new_high():
    s = DonchianBreakout({"entry_bars": 20, "exit_bars": 10})
    assert await _signal(s, [100.0] * 30 + [105.0]) == Direction.LONG


async def test_donchian_exits_on_a_new_low():
    s = DonchianBreakout({"entry_bars": 20, "exit_bars": 10})
    assert await _signal(s, [100.0] * 30 + [95.0]) == Direction.CLOSE


async def test_donchian_holds_inside_the_channel():
    # Prior 20 bars span ~99.8 (low) to ~110.1 (high); 105 breaks neither side.
    s = DonchianBreakout({"entry_bars": 20, "exit_bars": 20})
    assert await _signal(s, [100.0] * 15 + [110.0] * 15 + [105.0]) is None


async def test_donchian_compares_against_previous_bars_not_the_current_one():
    """The breakout level excludes the current bar, or a close could never exceed it."""
    s = DonchianBreakout({"entry_bars": 5, "exit_bars": 3})
    assert await _signal(s, [100, 101, 102, 103, 104, 105]) == Direction.LONG


async def test_donchian_needs_enough_history():
    s = DonchianBreakout({"entry_bars": 20, "exit_bars": 10})
    assert await _signal(s, [100.0] * 20) is None


def test_donchian_rejects_bad_params():
    with pytest.raises(ValueError):
        DonchianBreakout({"entry_bars": 1, "exit_bars": 10})


# ── TrendFilter ──────────────────────────────────────────────────────────────

async def test_trend_filter_long_above_the_average_flat_below():
    s = TrendFilter({"period": 50})
    assert await _signal(s, [100.0] * 50 + [120.0]) == Direction.LONG
    assert await _signal(s, [100.0] * 50 + [80.0]) == Direction.CLOSE


async def test_trend_filter_needs_enough_history():
    assert await _signal(TrendFilter({"period": 50}), [100.0] * 49) is None


# ── RsiPullbackInTrend ───────────────────────────────────────────────────────

def _uptrend_then_dip():
    closes = [100 + i * 0.5 for i in range(220)]           # well above the 200 SMA
    return closes + [closes[-1] - 3, closes[-1] - 6]      # sharp 2-day dip → RSI(2) ≈ 0


async def test_pullback_buys_a_dip_inside_an_uptrend():
    s = RsiPullbackInTrend({"rsi_period": 2, "entry_rsi": 10, "trend_period": 200, "exit_period": 5})
    assert await _signal(s, _uptrend_then_dip()) == Direction.LONG


async def test_pullback_ignores_dips_in_a_downtrend():
    closes = [300 - i * 0.5 for i in range(220)]
    closes += [closes[-1] - 3, closes[-1] - 6]
    s = RsiPullbackInTrend({"rsi_period": 2, "entry_rsi": 10, "trend_period": 200, "exit_period": 5})
    assert await _signal(s, closes) is None


async def test_pullback_exits_on_the_bounce_above_the_short_average():
    closes = _uptrend_then_dip() + [_uptrend_then_dip()[-3] + 2]
    s = RsiPullbackInTrend({"rsi_period": 2, "entry_rsi": 10, "trend_period": 200, "exit_period": 5})
    assert await _signal(s, closes) == Direction.CLOSE


def test_pullback_rejects_bad_params():
    with pytest.raises(ValueError):
        RsiPullbackInTrend({"rsi_period": 2, "entry_rsi": 150, "trend_period": 200, "exit_period": 5})


# ── Registration ─────────────────────────────────────────────────────────────

def test_new_built_ins_are_registered_and_described_for_the_ui():
    from app.domain.strategy.loader import get_all_strategy_classes
    names = {s["class_name"]: s for s in get_all_strategy_classes()}
    for cls in ("DonchianBreakout", "TrendFilter", "RsiPullbackInTrend"):
        assert cls in names
        assert names[cls]["parameters"], f"{cls} needs UI parameter metadata"
