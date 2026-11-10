"""Symmetric long/short/neutral/flat regime detection. trend_down mirrors trend_up so the grid
can lean into a downtrend the same way it leans into an uptrend, instead of only falling back to
a direction-agnostic ladder when there's no uptrend (see design doc, "Regime model")."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from app.domain.backtest.indicators import (
    atr as atr_ind, bandwidth, bollinger, ema, rolling_percentile, supertrend,
)
from app.domain.strategies.grid.params import RegimeParams


class GridDirection(str, Enum):
    LONG_BIASED = "long_biased"
    SHORT_BIASED = "short_biased"
    NEUTRAL = "neutral"
    FLAT = "flat"


@dataclass
class RegimeSeries:
    direction: List[GridDirection]
    supertrend_dir: List[int]
    bb_mid: List[Optional[float]]
    atr: List[Optional[float]]
    squeeze: List[bool]


def compute_regime(
    highs: List[float], lows: List[float], closes: List[float], params: RegimeParams,
) -> RegimeSeries:
    """Precomputed once per run (mirrors accumulation policies' prepare() pattern) — every index
    depends only on bars up to and including it."""
    ema_fast = ema(closes, params.ema_fast)
    ema_mid = ema(closes, params.ema_mid)
    ema_slow = ema(closes, params.ema_slow)
    atrv = atr_ind(highs, lows, closes, params.atr_period)
    atr_pctile = rolling_percentile(atrv, params.atr_pctile_window)
    bb_mid, bb_upper, bb_lower = bollinger(closes, params.bb_period, params.bb_std)
    bw = bandwidth(bb_mid, bb_upper, bb_lower)
    bw_pctile = rolling_percentile(bw, params.bandwidth_pctile_window)
    st_dir = supertrend(highs, lows, closes, params.supertrend_period, params.supertrend_mult)

    direction: List[GridDirection] = []
    squeeze: List[bool] = []
    for i in range(len(closes)):
        ef, em_, es = ema_fast[i], ema_mid[i], ema_slow[i]
        vol_ok = ef is not None and params.atr_vol_low <= atr_pctile[i] <= params.atr_vol_high
        squeeze.append(bw[i] is not None and bw_pctile[i] < params.squeeze_pctile)
        if not vol_ok or ef is None or em_ is None or es is None:
            direction.append(GridDirection.FLAT)
            continue
        trend_up = ef > em_ and closes[i] > es
        trend_down = ef < em_ and closes[i] < es
        if trend_up:
            direction.append(GridDirection.LONG_BIASED)
        elif trend_down:
            direction.append(GridDirection.SHORT_BIASED)
        else:
            direction.append(GridDirection.NEUTRAL)

    return RegimeSeries(direction=direction, supertrend_dir=st_dir, bb_mid=bb_mid, atr=atrv, squeeze=squeeze)
