from datetime import datetime, timedelta, timezone

from app.core.enums import Timeframe
from app.core.types import OHLCV
from app.domain.strategies.grid.params import GridParams, RegimeParams
from app.domain.strategies.grid.planner import build_plan_series
from app.domain.strategies.grid.regime import GridDirection


def _bars(closes):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    out = []
    for i, c in enumerate(closes):
        out.append(OHLCV(
            timestamp=start + timedelta(hours=i), symbol="BTCUSDT",
            open=c, high=c * 1.003, low=c * 0.997, close=c, volume=100,
            timeframe=Timeframe.H1,
        ))
    return out


def test_flat_direction_has_no_levels():
    bars = _bars([100.0] * 250)
    series = build_plan_series(bars, GridParams(), RegimeParams())
    flat_plans = [p for p in series.plans if p.direction == GridDirection.FLAT]
    assert flat_plans
    assert all(p.levels is None for p in flat_plans)


def test_active_direction_has_levels_with_rungs():
    # Deterministic wiggle (the same series the causality test uses). A linear ramp would make ATR
    # monotonic through the proportional-spread _bars() helper, pinning its rolling percentile
    # outside the vol band and gating every bar to FLAT -- leaving `active` empty.
    closes = [100.0 + 5 * ((i * 37) % 23 - 11) / 11 for i in range(300)]
    bars = _bars(closes)
    series = build_plan_series(bars, GridParams(), RegimeParams())
    active = [p for p in series.plans if p.direction != GridDirection.FLAT]
    assert active
    assert all(p.levels is not None and len(p.levels.rungs) >= 2 for p in active)


def test_causality_golden_truncation():
    """The whole point of the planner: plan[i] must never depend on bars after i. Truncating the
    tail must not change any earlier plan's direction or rung ladder."""
    closes = [100.0 + 5 * ((i * 37) % 23 - 11) / 11 for i in range(300)]   # deterministic wiggle
    bars = _bars(closes)
    params, rparams = GridParams(), RegimeParams()

    full = build_plan_series(bars, params, rparams)
    truncated = build_plan_series(bars[:180], params, rparams)

    for i in range(180):
        assert full.plans[i].direction == truncated.plans[i].direction, f"direction diverged at {i}"
        full_levels = full.plans[i].levels
        trunc_levels = truncated.plans[i].levels
        if full_levels is None or trunc_levels is None:
            assert full_levels is None and trunc_levels is None, f"levels presence diverged at {i}"
        else:
            assert full_levels.rungs == trunc_levels.rungs, f"rungs diverged at {i}"
