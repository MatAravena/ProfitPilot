from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional

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
    profit_factor: float
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
