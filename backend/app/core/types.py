from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID

from app.core.enums import (
    Direction, MarketType, OrderSide, OrderType,
    OrderStatus, Timeframe, SignalSource,
)


# ── Market Data ────────────────────────────────────────────────────────────────

class OHLCV(BaseModel):
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timeframe: Timeframe

    @field_validator("high")
    @classmethod
    def high_gte_low(cls, v: float, info: Any) -> float:
        if "low" in info.data and v < info.data["low"]:
            raise ValueError("high must be >= low")
        return v


class Tick(BaseModel):
    timestamp: datetime
    symbol: str
    price: float
    size: float
    side: Optional[OrderSide] = None


class MarketData(BaseModel):
    symbol: str
    timeframe: Timeframe
    bars: List[OHLCV]

    @property
    def latest(self) -> Optional[OHLCV]:
        return self.bars[-1] if self.bars else None


# ── Forecasting ─────────────────────────────────────────────────────────────────

class ModelFeatures(BaseModel):
    """Typed feature vector passed to any ForecastingModelAdapter."""
    symbol: str
    timeframe: Timeframe
    timestamp: datetime
    features: Dict[str, float]      # feature name → value
    sequence: Optional[List[Dict[str, float]]] = None  # for sequential models (LSTM etc.)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ForecastResult(BaseModel):
    """Output from any ForecastingModelAdapter — direction, size, confidence."""
    model_id: str
    symbol: str
    timestamp: datetime
    direction: Direction
    predicted_return: float         # expected % return (positive = up, negative = down)
    confidence: float = Field(ge=0.0, le=1.0)
    horizon_bars: int               # how many bars ahead this forecast covers
    horizon_timeframe: Timeframe
    metadata: Dict[str, Any] = Field(default_factory=dict)  # model-specific extras


class ModelMetrics(BaseModel):
    """Evaluation metrics for a trained forecasting model."""
    model_id: str
    dataset_id: str
    mae: float                      # mean absolute error
    rmse: float                     # root mean squared error
    directional_accuracy: float     # % of correct direction predictions
    sharpe_simulated: Optional[float] = None    # simulated Sharpe from model signals
    evaluated_at: datetime


# ── Signals ────────────────────────────────────────────────────────────────────

class Signal(BaseModel):
    signal_id: UUID
    strategy_id: UUID
    symbol: str
    market_type: MarketType
    timeframe: Timeframe
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    source: SignalSource
    forecast: Optional[ForecastResult] = None   # populated if source includes FORECAST
    metadata: Dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime


class EnrichedSignal(Signal):
    """Signal enriched by the optional LLM layer."""
    llm_sentiment: Optional[float] = Field(None, ge=-1.0, le=1.0)
    llm_reasoning: Optional[str] = None
    llm_provider: Optional[str] = None
    original_confidence: float      # confidence before LLM enrichment
    enriched_at: datetime


# ── Orders & Fills ─────────────────────────────────────────────────────────────

class Order(BaseModel):
    order_id: UUID
    strategy_id: UUID
    broker_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "day"
    signal_id: Optional[UUID] = None    # traceability
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class OrderResult(BaseModel):
    order_id: UUID
    broker_order_id: str            # broker's own reference
    status: OrderStatus
    submitted_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Fill(BaseModel):
    fill_id: UUID
    order_id: UUID
    broker_fill_id: str
    symbol: str
    side: OrderSide
    filled_quantity: float
    avg_price: float
    commission: float
    filled_at: datetime


# ── Portfolio ──────────────────────────────────────────────────────────────────

class Position(BaseModel):
    symbol: str
    market_type: MarketType
    broker_id: str
    quantity: float
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    opened_at: datetime

    @property
    def side(self) -> OrderSide:
        return OrderSide.BUY if self.quantity > 0 else OrderSide.SELL


class Account(BaseModel):
    broker_id: str
    account_id: str
    equity: float
    cash: float
    buying_power: float
    paper_mode: bool
    currency: str = "USD"
    updated_at: datetime


# ── Risk ───────────────────────────────────────────────────────────────────────

class RiskConfig(BaseModel):
    max_position_size_pct: float = 0.02
    max_open_positions: int = 5
    max_daily_drawdown_pct: float = 0.03
    max_total_drawdown_pct: float = 0.10
    stop_loss_pct: float = 0.015
    take_profit_pct: Optional[float] = None
    max_orders_per_minute: int = 10
    kill_switch_enabled: bool = True


class RiskVeto(BaseModel):
    """Returned by RiskManager when an order is rejected."""
    order_id: UUID
    reason: str
    rule_violated: str
    current_value: float
    limit_value: float
