"""The two arms. Direction (regime.py) and risk posture (here) are orthogonal axes -- a policy
answers "what happens when the range breaks," never "which way to trade" (see design doc).
"""
from __future__ import annotations

from typing import List, Optional, Protocol

from app.domain.strategies.grid.params import GridParams
from app.domain.strategies.grid.planner import GridPlan, GridPlanSeries
from app.domain.strategies.grid.regime import GridDirection


class GridPolicy(Protocol):
    def prepare(self, bars: List, plan_series: Optional[GridPlanSeries]) -> None: ...
    def should_force_close(self, i: int, bar, plan: GridPlan, ledger) -> bool: ...
    def extend_range_mult(self, i: int, bar, plan: GridPlan, ledger) -> Optional[float]: ...


class GuardedReanchorPolicy:
    """Bounded loss -- the deployable arm. Forces a full close when the range breaks against the
    active bias AND Supertrend confirms, so a wick alone doesn't stop you out. The exit mirrors
    under direction: long exits below range_low, short exits above range_high."""

    def __init__(self, params: GridParams) -> None:
        self.params = params

    def prepare(self, bars: List, plan_series: Optional[GridPlanSeries]) -> None:
        return None

    def should_force_close(self, i: int, bar, plan: GridPlan, ledger) -> bool:
        if plan.levels is None:
            return False
        buffer = self.params.reanchor_buffer_pct
        rungs = plan.levels.rungs
        if plan.direction in (GridDirection.LONG_BIASED, GridDirection.NEUTRAL):
            return bar.close < rungs[0] * (1 - buffer) and not plan.supertrend_bullish
        if plan.direction == GridDirection.SHORT_BIASED:
            return bar.close > rungs[-1] * (1 + buffer) and plan.supertrend_bullish
        return False

    def extend_range_mult(self, i: int, bar, plan: GridPlan, ledger) -> Optional[float]:
        return None


class AccumulateNoStopPolicy:
    """Unbounded exposure by construction -- no stop. Extends the ladder up to max_extensions
    times instead of exiting; GridArmResult (Task 8) reports max_inventory_notional /
    worst_unrealized_pct / time_underwater_pct so the failure mode is disclosed, never hidden."""

    def __init__(self, params: GridParams) -> None:
        self.params = params
        self._extensions_used = 0
        self._active_mult: Optional[float] = None

    def prepare(self, bars: List, plan_series: Optional[GridPlanSeries]) -> None:
        self._extensions_used = 0
        self._active_mult = None

    def should_force_close(self, i: int, bar, plan: GridPlan, ledger) -> bool:
        return False

    def extend_range_mult(self, i: int, bar, plan: GridPlan, ledger) -> Optional[float]:
        """`bar` must be the bar the plan was built from (i-1), never the bar about to fill --
        deciding on a close and then filling that same bar's low/high is look-ahead. One budget
        slot buys one break episode: the wider ladder holds while price stays outside the range
        and is released once it comes back in."""
        if plan.levels is None:
            return None
        rungs = plan.levels.rungs
        broke_low = (
            plan.direction in (GridDirection.LONG_BIASED, GridDirection.NEUTRAL)
            and bar.close < rungs[0]
        )
        broke_high = plan.direction == GridDirection.SHORT_BIASED and bar.close > rungs[-1]
        if not (broke_low or broke_high):
            self._active_mult = None
            return None
        if self._active_mult is None and self._extensions_used < self.params.max_extensions:
            self._extensions_used += 1
            self._active_mult = self.params.range_atr_mult * (1 + self._extensions_used)
        return self._active_mult
