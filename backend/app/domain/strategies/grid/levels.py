"""Rung geometry: range anchoring, the cost floor, and rung-count clamping. Pure, no bar loop —
called once per bar by the planner (Task 5) with that bar's regime inputs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from app.domain.strategies.grid.params import GridParams


@dataclass(frozen=True)
class GridLevels:
    center: float
    step_pct: float
    rungs: List[float]   # ascending price levels


def cost_floor_step_pct(params: GridParams) -> float:
    """Minimum spacing (as a fraction of price) that clears min_edge round trips of fee+slippage.
    Omitting this term is, per the design, the #1 reason retail grid bots bleed."""
    round_trip_cost = 2 * (params.fee_pct + params.slippage_pct)
    return params.min_edge * round_trip_cost


def compute_levels(
    *, center: float, atr: float, params: GridParams,
    swing_high: Optional[float] = None, swing_low: Optional[float] = None,
) -> GridLevels:
    half_width = params.range_atr_mult * atr
    # Prices can't go non-positive: a huge ATR relative to center would otherwise push range_low
    # to <= 0, and geometric multiplication by (1 + step_pct) diverges to -inf on a non-positive
    # base instead of ever exceeding range_high (infinite loop in _geometric_rungs below).
    range_low = max(center - half_width, center * 1e-3)
    range_high = center + half_width
    # A stale pivot on the wrong side of center (price broke out past it) isn't structure for
    # this ladder -- clamping to it would shove every rung to one side of center.
    if swing_low is not None and swing_low < center:
        range_low = max(range_low, swing_low)
    if swing_high is not None and swing_high > center:
        range_high = min(range_high, swing_high)
    if range_high <= range_low:
        range_high, range_low = center * 1.001, center * 0.999   # degenerate-range guard

    step_pct = max(params.spacing_atr_mult * atr / center, cost_floor_step_pct(params))

    if params.spacing_mode == "geometric":
        rungs = _geometric_rungs(range_low, range_high, step_pct)
    else:
        rungs = _arithmetic_rungs(range_low, range_high, step_pct * center)

    rungs = _clamp_rung_count(rungs, params, step_pct=step_pct, center=center,
                               spacing_mode=params.spacing_mode)
    return GridLevels(center=center, step_pct=step_pct, rungs=rungs)


def _geometric_rungs(low: float, high: float, step_pct: float) -> List[float]:
    rungs = [low]
    while rungs[-1] * (1 + step_pct) <= high:
        rungs.append(rungs[-1] * (1 + step_pct))
    return rungs


def _arithmetic_rungs(low: float, high: float, step: float) -> List[float]:
    rungs = [low]
    while rungs[-1] + step <= high:
        rungs.append(rungs[-1] + step)
    return rungs


def _clamp_rung_count(
    rungs: List[float], params: GridParams, *, step_pct: float, center: float, spacing_mode: str,
) -> List[float]:
    """Enforce [min_rungs, max_rungs] WITHOUT ever touching the actual price gap between
    adjacent rungs -- resampling to hit a target count (the previous approach) silently discards
    step_pct and can place rungs far closer together than the cost floor allows, defeating the
    one guarantee this module exists to provide (see cost_floor_step_pct's docstring)."""
    n = len(rungs)
    if n > params.max_rungs:
        # Too many natural rungs at floor-respecting spacing -- truncate symmetrically around
        # center rather than dropping one whole end, keeping every remaining gap untouched.
        center_idx = min(range(n), key=lambda i: abs(rungs[i] - center))
        half = params.max_rungs // 2
        start = max(0, center_idx - half)
        end = start + params.max_rungs
        if end > n:
            end = n
            start = end - params.max_rungs
        return rungs[start:end]
    if n < params.min_rungs:
        # Too few natural rungs -- EXTEND outward at the same floor-respecting spacing instead of
        # uniformly resampling across the (too-narrow) range. This can push past the ATR-derived
        # range when the floor demands it; that is the honest outcome ("this instrument is too
        # quiet to grid at these costs"), not a bug to hide by cramming rungs in closer together.
        out = list(rungs) if rungs else [center]
        floor = center * 1e-3   # same positivity floor as compute_levels
        grow_high = True
        while len(out) < params.min_rungs:
            if not grow_high and spacing_mode != "geometric" and out[0] - step_pct * center < floor:
                grow_high = True   # arithmetic can't step lower without going non-positive
            if grow_high:
                nxt = out[-1] * (1 + step_pct) if spacing_mode == "geometric" else out[-1] + step_pct * center
                out.append(nxt)
            else:
                prv = out[0] / (1 + step_pct) if spacing_mode == "geometric" else out[0] - step_pct * center
                out.insert(0, prv)
            grow_high = not grow_high
        return out
    return rungs
