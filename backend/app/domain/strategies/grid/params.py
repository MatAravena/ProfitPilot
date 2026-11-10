"""Every grid knob, frozen so a running backtest can't mutate its own config mid-run."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SpacingMode = Literal["geometric", "arithmetic"]


@dataclass(frozen=True)
class GridParams:
    range_atr_mult: float = 3.0
    spacing_mode: SpacingMode = "geometric"
    spacing_atr_mult: float = 0.30
    min_edge: float = 3.0
    min_rungs: int = 8
    max_rungs: int = 30
    fee_pct: float = 0.001
    slippage_pct: float = 0.0005
    max_extensions: int = 3
    reanchor_buffer_pct: float = 0.01
    cooldown_bars: int = 5


@dataclass(frozen=True)
class RegimeParams:
    ema_fast: int = 9
    ema_mid: int = 20
    ema_slow: int = 50
    atr_period: int = 14
    atr_vol_low: float = 0.35
    atr_vol_high: float = 0.90
    bb_period: int = 20
    bb_std: float = 2.0
    squeeze_pctile: float = 0.20
    atr_pctile_window: int = 200
    bandwidth_pctile_window: int = 200
    swing_confirm_bars: int = 3
    supertrend_period: int = 10
    supertrend_mult: float = 3.0
