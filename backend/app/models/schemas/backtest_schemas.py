from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.core.datetime_utils import to_naive_utc


class BacktestRequest(BaseModel):
    strategy_name: str = Field(..., description="'SmaCrossover' or 'RsiMeanReversion'")
    symbol: str = Field("BTCUSDT", description="e.g. BTCUSDT, ETHUSDT")
    timeframe: str = Field("1d", description="1m 5m 15m 1h 4h 1d")
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    initial_capital: float = Field(10_000.0, gt=0)
    commission_pct: float = Field(0.001, ge=0)
    # Adverse slippage per fill (spread + impact): buys fill higher, sells lower. Defaults to a
    # conservative 5 bps so backtests aren't optimistically frictionless. 0 = no slippage.
    slippage_pct: float = Field(0.0005, ge=0, le=0.1)
    # Fraction of equity risked per entry — the SAME risk model the live executor uses, so the
    # backtest curve reflects live magnitude. None → the service applies the live default (2%).
    # Pre-filled from the user's risk profile on the form (like SL/TP).
    position_size_pct: Optional[float] = Field(None, gt=0, le=1)
    # Optional risk exits for the run — arrangeable per backtest (pre-filled from the user's
    # risk profile on the form). None = no stop / no target.
    stop_loss_pct: Optional[float] = Field(None, gt=0, le=1)
    take_profit_pct: Optional[float] = Field(None, gt=0, le=5)
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("start", "end", mode="after")
    @classmethod
    def normalize_tz(cls, v: Optional[datetime]) -> Optional[datetime]:
        return to_naive_utc(v)


class TradeRecordResponse(BaseModel):
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    entry_time: int
    exit_time: int


class BacktestMetricsResponse(BaseModel):
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: Optional[float] = None   # None = no losing trades (rendered as "∞")
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    final_equity: float


class EquityPointResponse(BaseModel):
    timestamp: int
    value: float


class PricePointResponse(BaseModel):
    timestamp: int  # Unix ms
    close: float


class BacktestResponse(BaseModel):
    strategy_name: str
    symbol: str
    timeframe: str
    initial_capital: float
    metrics: BacktestMetricsResponse
    equity_curve: List[EquityPointResponse]
    trades: List[TradeRecordResponse]
    prices: List[PricePointResponse]


class MonteCarloRequest(BacktestRequest):
    """A backtest request plus resampling controls. Reuses every BacktestRequest field
    (same strategy/symbol/timeframe/dates/costs/sizing) so MC stresses the exact run the
    ordinary backtest would produce — no separate execution assumptions."""
    n_simulations: int = Field(5_000, ge=100, le=50_000)
    methods: List[Literal["bootstrap", "shuffle"]] = Field(default_factory=lambda: ["bootstrap", "shuffle"])
    seed: Optional[int] = Field(None, description="Set for deterministic (reproducible) runs.")


class PercentileStatsResponse(BaseModel):
    p5: float
    p25: float
    p50: float
    p75: float
    p95: float
    min: float
    max: float
    mean: float


class HistogramResponse(BaseModel):
    edges: List[float]   # len == counts + 1
    counts: List[int]


class MonteCarloMethodResponse(BaseModel):
    method: str
    final_equity: PercentileStatsResponse
    total_return_pct: PercentileStatsResponse
    max_drawdown_pct: PercentileStatsResponse
    prob_profit: float
    risk_of_exceeding_drawdown: float
    risk_of_ruin: float
    histogram: HistogramResponse


class MonteCarloResponse(BaseModel):
    strategy_name: str
    symbol: str
    timeframe: str
    initial_capital: float
    n_simulations: int
    n_trades: int
    realized_total_return_pct: float
    drawdown_threshold_pct: float
    methods: Dict[str, MonteCarloMethodResponse]


CAVEAT_TEXT = (
    "Only ~3 completed halving cycles exist; the cycle offsets are fit to past tops/bottoms. "
    "Read this as one live out-of-sample cycle, not proof."
)


class CycleParamsSchema(BaseModel):
    """Halving-clock knobs shared by every cycle_* arm.

    `timing_mode` picks HOW cycle position becomes behavior:
    - "gaussian" — smooth bell curves around the predicted top/bottom (sigma_* set their width);
    - "windows"  — discrete day windows: nothing before the start day, full intensity through the
      end day, nothing after. The *_day fields are days since the most recent halving; leave one
      null to derive it from the gaussian params (top/bottom +/- sigma).
    """
    days_to_top: int = Field(535, ge=200, le=900)
    top_to_bottom: int = Field(380, ge=200, le=900)
    sigma_top: float = Field(90.0, gt=0, le=400)
    sigma_bottom: float = Field(120.0, gt=0, le=400)
    base_buy: float = Field(0.25, ge=0, le=1)
    rolling_window: int = Field(90, ge=7, le=400)
    k_buy: float = Field(0.5, gt=0, le=1)
    k_sell: float = Field(0.35, gt=0, le=1)
    timing_mode: Literal["gaussian", "windows"] = "gaussian"
    sell_start_day: Optional[int] = Field(None, ge=0, le=1457)
    sell_end_day: Optional[int] = Field(None, ge=0, le=1457)
    buy_start_day: Optional[int] = Field(None, ge=0, le=1457)
    buy_end_day: Optional[int] = Field(None, ge=0, le=1457)
    ramp_days: int = Field(0, ge=0, le=200)


class HunterParamsSchema(BaseModel):
    """Tunable knobs for the cycle_ath_trim_rebuy arm (sell_cap can now go all the way to 1.0)."""
    sell_cap_frac: float = Field(0.30, ge=0, le=1)
    cooldown_days: int = Field(90, ge=0, le=365)
    reentry_within: float = Field(0.15, ge=0, le=1)
    k_bear_daily: float = Field(0.05, gt=0, le=1)


class RotationParamsSchema(BaseModel):
    """Tunable knobs for the cycle_selltop_redeploy_manual / _auto arms."""
    sell_fraction_at_ath: float = Field(0.70, ge=0, le=1)
    ath_band: float = Field(0.08, gt=0, le=0.5)
    sell_intensity_hi: float = Field(0.85, ge=0, le=1)
    k_sell_daily: float = Field(0.10, gt=0, le=1)
    sell_sharpness: float = Field(4.0, ge=1, le=12)
    expected_bear_drop: float = Field(0.70, gt=0, lt=1)   # manual arm
    buy_zone_top_frac: float = Field(0.50, ge=0, le=1)
    k_deploy_daily: float = Field(0.10, gt=0, le=1)
    deploy_floor: float = Field(0.30, ge=0, le=1)
    reentry_gain: float = Field(0.30, gt=0, le=2)
    caution_margin: float = Field(0.05, ge=0, le=0.5)     # auto arm shaves the derived drop shallower


class DcaCompareRequest(BaseModel):
    symbol: str = Field("BTCUSDT")
    timeframe: str = Field("1d")
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    capital_model: Literal["contributions", "lump_sum"] = "contributions"
    contribution_amount: float = Field(100.0, ge=0)
    contribution_interval_days: int = Field(7, ge=1, le=365)
    lump_sum_budget: float = Field(0.0, ge=0)
    commission_pct: float = Field(0.001, ge=0)
    slippage_pct: float = Field(0.0005, ge=0, le=0.1)
    cycle: CycleParamsSchema = Field(default_factory=CycleParamsSchema)
    hunter: HunterParamsSchema = Field(default_factory=HunterParamsSchema)
    rotation: RotationParamsSchema = Field(default_factory=RotationParamsSchema)

    @field_validator("start", "end", mode="after")
    @classmethod
    def normalize_tz(cls, v: Optional[datetime]) -> Optional[datetime]:
        return to_naive_utc(v)


class ArmResultResponse(BaseModel):
    equity_curve: List[EquityPointResponse]
    final_value: float
    total_contributed: float
    total_return_pct: float
    units_accumulated: float
    avg_cost_basis: float
    max_drawdown_pct: float
    sharpe_ratio: float
    dry_powder: float
    realized_pnl: float


class CycleMarker(BaseModel):
    timestamp: int   # Unix ms (UTC midnight of the predicted date)
    kind: str        # "top" | "bottom"


class DcaCompareResponse(BaseModel):
    symbol: str
    timeframe: str
    capital_model: str
    caveat: str
    cycle_markers: List[CycleMarker]
    arms: Dict[str, ArmResultResponse]   # keys: dca_flat, dca_dip_weighted_cycle, cycle_buydip_selltop, ...


class StrategyParamDef(BaseModel):
    key: str
    type: str
    default: Any
    label: str


class StrategyMeta(BaseModel):
    class_name: str
    display_name: str
    description: str
    parameters: List[StrategyParamDef]


class AvailableStrategiesResponse(BaseModel):
    strategies: List[StrategyMeta]
