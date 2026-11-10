from app.domain.strategies.grid.levels import GridLevels
from app.domain.strategies.grid.params import GridParams
from app.domain.strategies.grid.planner import GridPlan
from app.domain.strategies.grid.policies import AccumulateNoStopPolicy, GuardedReanchorPolicy
from app.domain.strategies.grid.regime import GridDirection


def _plan(direction, rungs, supertrend_bullish):
    levels = GridLevels(center=100.0, step_pct=0.02, rungs=rungs)
    return GridPlan(direction=direction, levels=levels, supertrend_bullish=supertrend_bullish,
                    swing_high=None, swing_low=None)


class _Bar:
    def __init__(self, close):
        self.close = close
        self.low = close
        self.high = close


def test_guarded_reanchor_exits_long_biased_on_breakdown_with_bearish_supertrend():
    policy = GuardedReanchorPolicy(GridParams(reanchor_buffer_pct=0.01))
    plan = _plan(GridDirection.LONG_BIASED, [96, 98, 100, 102, 104], supertrend_bullish=False)
    bar = _Bar(close=94.0)   # below range_low * (1 - buffer) = 96 * 0.99 = 95.04
    assert policy.should_force_close(0, bar, plan, ledger=None) is True


def test_guarded_reanchor_does_not_exit_on_a_wick_without_supertrend_confirmation():
    policy = GuardedReanchorPolicy(GridParams(reanchor_buffer_pct=0.01))
    plan = _plan(GridDirection.LONG_BIASED, [96, 98, 100, 102, 104], supertrend_bullish=True)
    bar = _Bar(close=94.0)
    assert policy.should_force_close(0, bar, plan, ledger=None) is False


def test_guarded_reanchor_short_biased_exit_mirrors_the_long_condition():
    policy = GuardedReanchorPolicy(GridParams(reanchor_buffer_pct=0.01))
    plan = _plan(GridDirection.SHORT_BIASED, [96, 98, 100, 102, 104], supertrend_bullish=True)
    bar = _Bar(close=106.0)   # above range_high * (1 + buffer) = 104 * 1.01 = 105.04
    assert policy.should_force_close(0, bar, plan, ledger=None) is True


def test_accumulate_nostop_never_force_closes():
    policy = AccumulateNoStopPolicy(GridParams())
    plan = _plan(GridDirection.LONG_BIASED, [96, 98, 100, 102, 104], supertrend_bullish=False)
    bar = _Bar(close=50.0)
    assert policy.should_force_close(0, bar, plan, ledger=None) is False


def test_accumulate_nostop_extends_range_when_broken_and_stops_at_max_extensions():
    params = GridParams(max_extensions=2, range_atr_mult=3.0)
    policy = AccumulateNoStopPolicy(params)
    policy.prepare(bars=[], plan_series=None)
    plan = _plan(GridDirection.LONG_BIASED, [96, 98, 100, 102, 104], supertrend_bullish=False)
    broken_bar = _Bar(close=90.0)   # below the bottom rung

    ext1 = policy.extend_range_mult(0, broken_bar, plan, ledger=None)
    ext2 = policy.extend_range_mult(1, broken_bar, plan, ledger=None)
    ext3 = policy.extend_range_mult(2, broken_bar, plan, ledger=None)   # exceeds max_extensions=2

    assert ext1 is not None and ext2 is not None
    assert ext2 > ext1 > params.range_atr_mult
    assert ext3 is None


def test_two_arms_diverge_on_a_broken_range():
    """The one contract the design leans on: same broken-range bar, opposite behavior."""
    params = GridParams(max_extensions=2, reanchor_buffer_pct=0.01)
    guarded = GuardedReanchorPolicy(params)
    nostop = AccumulateNoStopPolicy(params)
    plan = _plan(GridDirection.LONG_BIASED, [96, 98, 100, 102, 104], supertrend_bullish=False)
    bar = _Bar(close=90.0)

    assert guarded.should_force_close(0, bar, plan, ledger=None) is True
    assert nostop.should_force_close(0, bar, plan, ledger=None) is False
