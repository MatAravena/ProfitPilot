from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.datetime_utils import to_naive_utc
from app.models.schemas.backtest_schemas import EquityPointResponse

FUNDING_CAVEAT_TEXT = (
    "SHORT_BIASED grid legs omit perp funding-rate cost. Realism gap disclosed, not fixed for v1 "
    "-- see the design doc's Honesty guardrails."
)


class GridParamsSchema(BaseModel):
    range_atr_mult: float = Field(3.0, gt=0, le=10)
    spacing_mode: Literal["geometric", "arithmetic"] = "geometric"
    spacing_atr_mult: float = Field(0.30, gt=0, le=5)
    min_edge: float = Field(3.0, gt=0, le=20)
    min_rungs: int = Field(8, ge=2, le=100)
    max_rungs: int = Field(30, ge=2, le=100)
    fee_pct: float = Field(0.001, ge=0, le=0.05)
    slippage_pct: float = Field(0.0005, ge=0, le=0.05)
    max_extensions: int = Field(3, ge=0, le=10)
    reanchor_buffer_pct: float = Field(0.01, ge=0, le=0.5)
    cooldown_bars: int = Field(5, ge=0, le=500)

    @model_validator(mode="after")
    def check_rung_bounds(self) -> "GridParamsSchema":
        if self.min_rungs > self.max_rungs:
            raise ValueError("min_rungs must be <= max_rungs")
        return self


class RegimeParamsSchema(BaseModel):
    ema_fast: int = Field(9, ge=2, le=200)
    ema_mid: int = Field(20, ge=2, le=400)
    ema_slow: int = Field(50, ge=2, le=800)
    atr_period: int = Field(14, ge=2, le=200)
    atr_vol_low: float = Field(0.35, ge=0, le=1)
    atr_vol_high: float = Field(0.90, ge=0, le=1)
    bb_period: int = Field(20, ge=2, le=200)
    bb_std: float = Field(2.0, gt=0, le=5)
    squeeze_pctile: float = Field(0.20, ge=0, le=1)
    atr_pctile_window: int = Field(200, ge=10, le=2000)
    bandwidth_pctile_window: int = Field(200, ge=10, le=2000)
    swing_confirm_bars: int = Field(3, ge=1, le=50)
    supertrend_period: int = Field(10, ge=2, le=100)
    supertrend_mult: float = Field(3.0, gt=0, le=10)

    @model_validator(mode="after")
    def check_ordering(self) -> "RegimeParamsSchema":
        if self.atr_vol_low >= self.atr_vol_high:
            raise ValueError("atr_vol_low must be < atr_vol_high")
        if not self.ema_fast < self.ema_mid < self.ema_slow:
            raise ValueError("EMA periods must satisfy ema_fast < ema_mid < ema_slow")
        return self


class GridRequest(BaseModel):
    symbol: str = Field("BTCUSDT")
    timeframe: str = Field("1h")
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    initial_capital: float = Field(10_000.0, gt=0)
    notional_per_rung: float = Field(200.0, gt=0)
    allow_intrabar_roundtrip: bool = False
    grid: GridParamsSchema = Field(default_factory=GridParamsSchema)
    regime: RegimeParamsSchema = Field(default_factory=RegimeParamsSchema)

    @field_validator("start", "end", mode="after")
    @classmethod
    def normalize_tz(cls, v: Optional[datetime]) -> Optional[datetime]:
        return to_naive_utc(v)


class GridArmResultResponse(BaseModel):
    equity_curve: List[EquityPointResponse]
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    grid_trades: int
    grid_realized_pnl: float
    forced_exit_pnl: float
    force_close_count: int
    mark_to_market_pnl: float
    avg_profit_per_grid_pct: float
    fill_rate: float
    time_in_grid_pct: float
    max_inventory_notional: float
    worst_unrealized_pct: float
    time_underwater_pct: float


class GridResponse(BaseModel):
    symbol: str
    timeframe: str
    allow_intrabar_roundtrip: bool
    funding_rate_caveat: str
    arms: Dict[str, GridArmResultResponse]   # keys: grid_guarded_reanchor, grid_accumulate_nostop
