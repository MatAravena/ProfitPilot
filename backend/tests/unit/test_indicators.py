from __future__ import annotations

import pytest

from app.domain.backtest.indicators import (
    atr, ema, rolling_percentile, sma, supertrend, true_ranges,
)


def test_sma_none_until_period_then_trailing_mean():
    assert sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]


def test_sma_constant_series():
    assert sma([5.0] * 5, 3)[-1] == pytest.approx(5.0)


def test_ema_constant_series_equals_constant():
    out = ema([10.0] * 10, 4)
    assert out[3] == pytest.approx(10.0)
    assert out[-1] == pytest.approx(10.0)


def test_ema_none_before_seed():
    out = ema([1, 2, 3, 4, 5], 3)
    assert out[0] is None and out[1] is None
    assert out[2] is not None


def test_true_ranges_uses_prev_close():
    highs = [10, 12]
    lows = [8, 9]
    closes = [9, 11]
    # bar1: max(12-9, |12-9|, |9-9|) = 3
    assert true_ranges(highs, lows, closes) == [2, 3]


def test_atr_constant_range_converges():
    n = 20
    highs = [11.0] * n
    lows = [9.0] * n
    closes = [10.0] * n
    # TR is 2 every bar -> ATR = 2.
    out = atr(highs, lows, closes, 5)
    assert out[4] == pytest.approx(2.0)
    assert out[-1] == pytest.approx(2.0)


def test_supertrend_bullish_on_uptrend_bearish_on_downtrend():
    up_c = [float(x) for x in range(1, 40)]
    up = supertrend(up_c, up_c, up_c, 10, 3.0)
    assert up[-1] == 1
    down_c = [float(x) for x in range(40, 1, -1)]
    down = supertrend(down_c, down_c, down_c, 10, 3.0)
    assert down[-1] == -1


def test_rolling_percentile_increasing_series_is_one():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = rolling_percentile(vals, 3)
    assert out[-1] == pytest.approx(1.0)   # current is the max of its window


def test_rolling_percentile_counts_leq_in_window():
    # window 3 at i=2 over [5,3,4]: values <= 4 are {3,4} -> 2/3
    out = rolling_percentile([5.0, 3.0, 4.0], 3)
    assert out[2] == pytest.approx(2 / 3)


def test_rolling_percentile_skips_none():
    out = rolling_percentile([None, None, 2.0, 1.0, 3.0], 5)
    # at last, window non-None = {2,1,3}, current 3 -> 3/3
    assert out[-1] == pytest.approx(1.0)
