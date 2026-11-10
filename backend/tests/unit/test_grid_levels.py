import pytest

from app.domain.strategies.grid.levels import compute_levels, cost_floor_step_pct
from app.domain.strategies.grid.params import GridParams


def test_cost_floor_scales_with_min_edge_and_costs():
    params = GridParams(min_edge=3.0, fee_pct=0.001, slippage_pct=0.0005)
    # 3 * 2 * (0.001 + 0.0005) = 0.009
    assert cost_floor_step_pct(params) == pytest.approx(0.009)


def test_spacing_never_falls_below_the_cost_floor():
    params = GridParams(spacing_atr_mult=0.01, min_edge=5.0)   # tiny ATR term, big cost floor
    levels = compute_levels(center=100.0, atr=0.1, params=params)
    assert levels.step_pct >= cost_floor_step_pct(params)


def test_rung_count_clamped_between_min_and_max():
    params = GridParams(min_rungs=8, max_rungs=30)
    tight = compute_levels(center=100.0, atr=50.0, params=params)   # huge range, few natural rungs
    assert params.min_rungs <= len(tight.rungs) <= params.max_rungs

    wide = compute_levels(center=100.0, atr=0.5, params=GridParams(
        min_rungs=8, max_rungs=30, spacing_atr_mult=0.01, min_edge=0.1, fee_pct=0.0001, slippage_pct=0.0,
    ))
    assert params.min_rungs <= len(wide.rungs) <= 30


def test_range_clipped_to_confirmed_swing_high_low():
    # min_rungs=2 keeps this test about clipping only: the swing-clipped [95, 105] band is narrow
    # enough that the default min_rungs=8 would trigger the cost-floor-respecting EXTENSION path
    # (see test_extension_beyond_swing_clip_when_floor_demands_it below), which deliberately can
    # push past a swing clip when the cost floor requires it -- a different property than this
    # test asserts.
    params = GridParams(min_rungs=2)
    levels = compute_levels(center=100.0, atr=10.0, params=params, swing_high=105.0, swing_low=95.0)
    assert levels.rungs[0] >= 95.0
    assert levels.rungs[-1] <= 105.0


def test_geometric_spacing_is_constant_percent_per_rung():
    params = GridParams(spacing_mode="geometric")
    levels = compute_levels(center=1000.0, atr=100.0, params=params)
    ratios = [levels.rungs[i + 1] / levels.rungs[i] for i in range(len(levels.rungs) - 1)]
    assert max(ratios) - min(ratios) < 1e-9


def test_extension_beyond_swing_clip_when_floor_demands_it():
    """The cost floor wins over the swing clip: a swing-clipped range too narrow to fit
    min_rungs at floor-respecting spacing must EXTEND past the clip, not cram rungs in closer
    together than round-trip costs allow. This is the same [95, 105] scenario as
    test_range_clipped_to_confirmed_swing_high_low, but with the default min_rungs=8."""
    params = GridParams()   # min_rungs=8 by default
    levels = compute_levels(center=100.0, atr=10.0, params=params, swing_high=105.0, swing_low=95.0)
    assert len(levels.rungs) >= params.min_rungs
    # Extending past the clip is the whole point of this test -- assert it actually happened.
    assert levels.rungs[0] < 95.0 or levels.rungs[-1] > 105.0
    _assert_every_gap_clears_floor(levels, params)


def test_actual_rung_spacing_clears_cost_floor_when_natural_count_is_below_min_rungs():
    """Regression test: the OLD _clamp_rung_count uniformly resampled across the natural range to
    hit min_rungs, silently discarding step_pct -- GridLevels.step_pct reported the floor-
    respecting value while the REAL gap between rungs could be far below it (measured: 17x below
    the declared floor in this exact scenario before the fix). Assert the ACTUAL rung-to-rung
    spacing, not the reported field."""
    params = GridParams(min_rungs=6, max_rungs=30, range_atr_mult=1.0, spacing_atr_mult=0.01,
                         min_edge=5.0, fee_pct=0.002, slippage_pct=0.001)
    levels = compute_levels(center=100.0, atr=1.0, params=params)
    assert len(levels.rungs) >= params.min_rungs
    _assert_every_gap_clears_floor(levels, params)


def test_actual_rung_spacing_clears_cost_floor_when_natural_count_exceeds_max_rungs():
    """Truncating to max_rungs must never touch the gap between the rungs that remain."""
    params = GridParams(min_rungs=2, max_rungs=5, range_atr_mult=3.0)
    levels = compute_levels(center=100.0, atr=50.0, params=params)
    assert len(levels.rungs) == params.max_rungs
    _assert_every_gap_clears_floor(levels, params)


def _assert_every_gap_clears_floor(levels, params: GridParams) -> None:
    floor = cost_floor_step_pct(params)
    for a, b in zip(levels.rungs, levels.rungs[1:]):
        gap_pct = (b - a) / a
        assert gap_pct == pytest.approx(floor, abs=1e-9) or gap_pct > floor


def test_arithmetic_extension_never_produces_non_positive_rungs():
    params = GridParams(spacing_mode="arithmetic", spacing_atr_mult=5.0, min_rungs=12)
    levels = compute_levels(center=100.0, atr=6.0, params=params)   # step = 30% of center
    assert len(levels.rungs) >= params.min_rungs
    assert min(levels.rungs) > 0


def test_swing_pivot_on_the_wrong_side_of_center_is_ignored():
    params = GridParams(min_rungs=2)
    # Breakout: last confirmed swing high (95) now sits BELOW center.
    levels = compute_levels(center=100.0, atr=2.0, params=params, swing_high=95.0)
    assert levels.rungs[-1] > 100.0
