"""Causal (bars, i) -> GridPlan. Precomputes the full plan series once per run — no consumer may
ever look at plans[j] for j > i while processing bar i (see the causality golden test).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Optional

from app.core.types import OHLCV
from app.domain.backtest.indicators import swing_pivots
from app.domain.strategies.grid.levels import GridLevels, compute_levels
from app.domain.strategies.grid.params import GridParams, RegimeParams
from app.domain.strategies.grid.regime import GridDirection, RegimeSeries, compute_regime


@dataclass
class GridPlan:
    direction: GridDirection
    levels: Optional[GridLevels]
    supertrend_bullish: bool
    swing_high: Optional[float]
    swing_low: Optional[float]


@dataclass
class GridPlanSeries:
    plans: List[GridPlan]
    regime: RegimeSeries


def build_plan_series(
    bars: List[OHLCV], grid_params: GridParams, regime_params: RegimeParams,
) -> GridPlanSeries:
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]

    regime = compute_regime(highs, lows, closes, regime_params)
    swing_high, swing_low = swing_pivots(highs, lows, confirm_bars=regime_params.swing_confirm_bars)

    plans: List[GridPlan] = []
    for i in range(len(bars)):
        direction = regime.direction[i]
        st_bull = regime.supertrend_dir[i] == 1
        center = regime.bb_mid[i]
        a = regime.atr[i]

        if direction == GridDirection.FLAT or center is None or a is None:
            plans.append(GridPlan(
                direction=direction, levels=None, supertrend_bullish=st_bull,
                swing_high=swing_high[i], swing_low=swing_low[i],
            ))
            continue

        eff_params = _tighten(grid_params) if regime.squeeze[i] else grid_params
        levels = compute_levels(
            center=center, atr=a, params=eff_params,
            swing_high=swing_high[i], swing_low=swing_low[i],
        )
        plans.append(GridPlan(
            direction=direction, levels=levels, supertrend_bullish=st_bull,
            swing_high=swing_high[i], swing_low=swing_low[i],
        ))

    return GridPlanSeries(plans=plans, regime=regime)


def _tighten(params: GridParams) -> GridParams:
    """Under a bandwidth squeeze, pack more rungs into the compressed range instead of leaving it
    under-populated."""
    return replace(params, spacing_atr_mult=params.spacing_atr_mult * 0.6)
