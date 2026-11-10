from datetime import datetime, timedelta, timezone

import pytest

from app.core.enums import Timeframe
from app.core.types import OHLCV
from app.domain.strategies.grid.levels import GridLevels
from app.domain.strategies.grid.params import GridParams, RegimeParams
from app.domain.strategies.grid.planner import GridPlan, GridPlanSeries, build_plan_series
from app.domain.strategies.grid.policies import AccumulateNoStopPolicy, GuardedReanchorPolicy
from app.domain.strategies.grid.regime import GridDirection, RegimeSeries
from app.domain.strategies.grid.simulator import run_grid_backtest

# Small windows so a short synthetic series still reaches an active (non-FLAT) regime.
_RPARAMS = RegimeParams(
    ema_fast=3, ema_mid=5, ema_slow=8, atr_period=5,
    atr_pctile_window=20, bandwidth_pctile_window=20, swing_confirm_bars=2,
    supertrend_period=5,
)


def _sawtooth_bars(n=150, low=95.0, high=105.0, period=10):
    """A clean triangular wave between low and high, starting and ending near the same price --
    so any net gain over the run is (almost) entirely grid income, not mark-to-market drift."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(n):
        phase = i % period
        half = period / 2
        frac = phase / half if phase <= half else (period - phase) / half
        price = low + (high - low) * frac
        bars.append(OHLCV(
            timestamp=start + timedelta(hours=i), symbol="BTCUSDT",
            open=price, high=price * 1.004, low=price * 0.996, close=price, volume=100,
            timeframe=Timeframe.H1,
        ))
    return bars


def test_sawtooth_produces_grid_trades_and_income_dominated_pnl():
    bars = _sawtooth_bars()
    grid_params = GridParams(range_atr_mult=2.0, spacing_atr_mult=0.15, min_edge=1.0,
                             fee_pct=0.0005, slippage_pct=0.0002)
    plan_series = build_plan_series(bars, grid_params, _RPARAMS)
    policy = GuardedReanchorPolicy(grid_params)

    result = run_grid_backtest(
        bars, plan_series, policy, grid_params,
        initial_capital=10_000.0, notional_per_rung=200.0, bars_per_year=8760,
    )

    assert result.grid_trades > 0
    assert result.grid_realized_pnl > 0
    # Price ends near where it started -> the P&L should be dominated by realized grid income,
    # not by a lucky mark-to-market drift on whatever happened to still be open.
    assert abs(result.mark_to_market_pnl) < result.grid_realized_pnl


def test_two_arms_diverge_on_a_trending_breakout():
    """A one-way trend beyond the range: guarded_reanchor should force-close (bounded loss),
    accumulate_nostop should extend instead (unbounded exposure) -- the documented divergence."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [
        OHLCV(timestamp=start + timedelta(hours=i), symbol="BTCUSDT",
              open=100 - i * 0.8, high=100 - i * 0.8, low=100 - i * 0.8, close=100 - i * 0.8,
              volume=100, timeframe=Timeframe.H1)
        for i in range(60)
    ]
    grid_params = GridParams(range_atr_mult=1.5, spacing_atr_mult=0.15, min_edge=1.0, max_extensions=2)
    plan_series = build_plan_series(bars, grid_params, _RPARAMS)

    guarded = run_grid_backtest(bars, plan_series, GuardedReanchorPolicy(grid_params), grid_params,
                               initial_capital=10_000.0, notional_per_rung=200.0)
    nostop = run_grid_backtest(bars, plan_series, AccumulateNoStopPolicy(grid_params), grid_params,
                               initial_capital=10_000.0, notional_per_rung=200.0)

    assert nostop.max_inventory_notional >= guarded.max_inventory_notional
    assert nostop.worst_unrealized_pct >= guarded.worst_unrealized_pct


def test_result_reports_disclosure_metrics_and_benchmark_inputs():
    bars = _sawtooth_bars()
    grid_params = GridParams(range_atr_mult=2.0, spacing_atr_mult=0.15, min_edge=1.0)
    plan_series = build_plan_series(bars, grid_params, _RPARAMS)
    result = run_grid_backtest(bars, plan_series, GuardedReanchorPolicy(grid_params), grid_params,
                              initial_capital=10_000.0, notional_per_rung=200.0)

    assert 0.0 <= result.fill_rate <= 100.0
    assert 0.0 <= result.time_in_grid_pct <= 100.0
    assert 0.0 <= result.time_underwater_pct <= 100.0
    assert result.max_inventory_notional >= 0.0
    assert len(result.equity_curve) == len(bars)


class _NoOpPolicy:
    """Never force-closes, never extends -- isolates the test to plan selection / fill logic."""

    def prepare(self, bars, plan_series):
        pass

    def should_force_close(self, i, bar, plan, ledger):
        return False

    def extend_range_mult(self, i, bar, plan, ledger):
        return None


def test_simulator_fills_bar_i_using_plan_i_minus_1_not_plan_i():
    """Regression test for same-bar look-ahead. A resting limit order can only be placed at a
    price known BEFORE the bar it fills in -- bar i's ladder must come from plans[i-1], never
    from a plan built using bar i's own high/low.

    Proven by hand-constructing a plan series where plans[1] and plans[2] point at completely
    disjoint ladders. Bar 2's own price (99-101) touches ONLY plans[1]'s ladder (rungs at
    90/100/110); it never comes near plans[2]'s ladder (rungs at 190/200/210). If the simulator
    filled bar 2 against plans[2] (the same-bar plan), no rung would ever cross and no lot would
    open. Only filling against plans[1] (the previous bar's plan) can open a lot here -- so this
    test can only pass once bar i is decided by plans[i-1]."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [
        OHLCV(timestamp=start, symbol="BTCUSDT", open=50, high=50, low=50, close=50,
              volume=1, timeframe=Timeframe.H1),
        OHLCV(timestamp=start + timedelta(hours=1), symbol="BTCUSDT", open=50, high=50, low=50,
              close=50, volume=1, timeframe=Timeframe.H1),
        OHLCV(timestamp=start + timedelta(hours=2), symbol="BTCUSDT", open=100, high=101, low=99,
              close=100, volume=1, timeframe=Timeframe.H1),
    ]
    near_levels = GridLevels(center=100.0, step_pct=0.10, rungs=[90.0, 100.0, 110.0])
    far_levels = GridLevels(center=200.0, step_pct=0.05, rungs=[190.0, 200.0, 210.0])
    plans = [
        GridPlan(direction=GridDirection.FLAT, levels=None, supertrend_bullish=True,
                 swing_high=None, swing_low=None),
        GridPlan(direction=GridDirection.LONG_BIASED, levels=near_levels, supertrend_bullish=True,
                 swing_high=None, swing_low=None),
        GridPlan(direction=GridDirection.LONG_BIASED, levels=far_levels, supertrend_bullish=True,
                 swing_high=None, swing_low=None),
    ]
    regime = RegimeSeries(
        direction=[p.direction for p in plans], supertrend_dir=[1, 1, 1],
        bb_mid=[None, 100.0, 200.0], atr=[None, 1.0, 1.0], squeeze=[False, False, False],
    )
    plan_series = GridPlanSeries(plans=plans, regime=regime)
    grid_params = GridParams()

    result = run_grid_backtest(
        bars, plan_series, _NoOpPolicy(), grid_params,
        initial_capital=10_000.0, notional_per_rung=200.0,
    )

    # A lot can only have opened during bar 2 if it was filled against near_levels
    # (plans[1] -- the previous bar's plan), never against far_levels (plans[2] -- the same-bar
    # plan, which bar 2's own price never touches).
    assert result.time_in_grid_pct > 0
    assert result.grid_trades == 0   # opened this bar, never touched its target -- not yet closed


def test_pnl_buckets_reconcile_to_total_return_including_forced_exits():
    """The mandatory realized-vs-mark-to-market split must actually reconcile. Before this fix, a
    forced (guard-triggered) exit's P&L vanished into neither grid_realized_pnl nor
    mark_to_market_pnl -- a reader adding the two reported buckets for the guarded arm would find
    they didn't sum to total_return_pct, with the gap being exactly where its reanchor-exit
    losses live.

    Hand-built plan series (same technique as the look-ahead regression test above) rather than
    the real regime/planner pipeline: reliably producing a guard-triggering breakdown through the
    full pipeline in a short synthetic window proved fragile (the ladder recenters on a lagging
    bb_mid and easily drifts away from a fast-moving synthetic price before ever crossing a rung).
    Direct construction makes the scenario deterministic: bar 1 opens a long lot on plans[0]'s
    ladder, then bar 2's price breaks far below plans[1]'s range with a bearish Supertrend,
    triggering GuardedReanchorPolicy's forced exit on the very lot just opened."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = [
        OHLCV(timestamp=start, symbol="BTCUSDT", open=100, high=100, low=100, close=100,
              volume=1, timeframe=Timeframe.H1),
        OHLCV(timestamp=start + timedelta(hours=1), symbol="BTCUSDT", open=95, high=95.5,
              low=94.5, close=95, volume=1, timeframe=Timeframe.H1),
        OHLCV(timestamp=start + timedelta(hours=2), symbol="BTCUSDT", open=80, high=80, low=80,
              close=80, volume=1, timeframe=Timeframe.H1),
    ]
    ladder = GridLevels(center=100.0, step_pct=0.05, rungs=[90.0, 95.0, 100.0, 105.0, 110.0])
    plans = [
        GridPlan(direction=GridDirection.LONG_BIASED, levels=ladder, supertrend_bullish=True,
                 swing_high=None, swing_low=None),
        GridPlan(direction=GridDirection.LONG_BIASED, levels=ladder, supertrend_bullish=False,
                 swing_high=None, swing_low=None),
        GridPlan(direction=GridDirection.LONG_BIASED, levels=ladder, supertrend_bullish=False,
                 swing_high=None, swing_low=None),
    ]
    regime = RegimeSeries(
        direction=[p.direction for p in plans], supertrend_dir=[1, -1, -1],
        bb_mid=[100.0, 100.0, 100.0], atr=[1.0, 1.0, 1.0], squeeze=[False, False, False],
    )
    plan_series = GridPlanSeries(plans=plans, regime=regime)
    grid_params = GridParams(reanchor_buffer_pct=0.01)

    result = run_grid_backtest(
        bars, plan_series, GuardedReanchorPolicy(grid_params), grid_params,
        initial_capital=10_000.0, notional_per_rung=200.0,
    )

    assert result.force_close_count == 1   # the scenario must actually exercise a forced exit
    assert result.forced_exit_pnl < 0       # entered at 95, forced out at 80 -- a real loss
    implied_total_pnl = result.grid_realized_pnl + result.forced_exit_pnl + result.mark_to_market_pnl
    actual_total_pnl = result.final_equity - 10_000.0
    assert implied_total_pnl == pytest.approx(actual_total_pnl, abs=0.02)
