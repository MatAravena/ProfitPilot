from datetime import datetime, timedelta, timezone

from app.core.enums import Timeframe
from app.core.types import OHLCV
from app.domain.backtest.accumulation import bars_per_day
from app.domain.backtest.indicators import bandwidth, bollinger, swing_pivots


def test_bollinger_mid_matches_sma_and_bands_widen_with_volatility():
    values = [100.0] * 20 + [100, 110, 90, 120, 80, 130, 70, 140, 60, 150]
    mid, upper, lower = bollinger(values, period=20, num_std=2.0)
    assert mid[19] == 100.0
    assert upper[19] == 100.0 and lower[19] == 100.0   # zero variance in the flat window
    assert upper[-1] > mid[-1] > lower[-1]              # bands widen once volatility appears


def test_bandwidth_is_zero_when_flat_and_positive_when_volatile():
    values = [100.0] * 25
    mid, upper, lower = bollinger(values, period=20)
    bw = bandwidth(mid, upper, lower)
    assert bw[20] == 0.0

    volatile = [100.0] * 20 + [100, 130, 70, 140, 60]
    mid2, upper2, lower2 = bollinger(volatile, period=20)
    bw2 = bandwidth(mid2, upper2, lower2)
    assert bw2[-1] > 0.0


def test_swing_pivots_confirms_only_after_confirm_bars_and_is_causal():
    # A clean local high at index 10, flat elsewhere either side.
    highs = [100.0] * 20
    highs[10] = 110.0
    lows = [90.0] * 20
    swing_high, _ = swing_pivots(highs, lows, confirm_bars=3)

    # Not visible until index 13 (10 + confirm_bars) — never at its own index.
    assert swing_high[10] is None
    assert swing_high[12] is None
    assert swing_high[13] == 110.0
    assert swing_high[19] == 110.0   # stays "last confirmed" going forward


def test_swing_pivots_causality_golden_truncation():
    highs = [100.0 + (i % 7) for i in range(40)]
    lows = [90.0 + (i % 5) for i in range(40)]
    full_high, full_low = swing_pivots(highs, lows, confirm_bars=3)

    truncated_high, truncated_low = swing_pivots(highs[:25], lows[:25], confirm_bars=3)

    assert full_high[:25] == truncated_high
    assert full_low[:25] == truncated_low


def test_bars_per_day_hourly():
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [
        OHLCV(timestamp=start + timedelta(hours=i), symbol="BTCUSDT", open=1, high=1, low=1,
              close=1, volume=1, timeframe=Timeframe.H1)
        for i in range(48)
    ]
    assert bars_per_day(bars) == 24.0
