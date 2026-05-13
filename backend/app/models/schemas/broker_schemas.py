from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ConnectBrokerRequest(BaseModel):
    broker_id: str = Field(..., pattern="^(bybit|binance|alpaca)$")
    api_key: str = Field(..., min_length=1)
    secret_key: str = Field(..., min_length=1)
    label: str = Field("", max_length=100)
    is_paper: bool = True


class BrokerConnectionResponse(BaseModel):
    id: UUID
    broker_id: str
    label: str
    is_paper: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountResponse(BaseModel):
    broker_id: str
    account_id: str
    equity: float
    cash: float
    buying_power: float
    paper_mode: bool
    currency: str
    updated_at: datetime


class PositionResponse(BaseModel):
    symbol: str
    market_type: str
    broker_id: str
    quantity: float
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    opened_at: datetime


class PortfolioSummaryResponse(BaseModel):
    total_equity: float
    total_cash: float
    total_unrealized_pnl: float
    positions: list[PositionResponse]
    accounts: list[AccountResponse]


class PlaceOrderRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32)
    side: str = Field(..., pattern="^(buy|sell)$")
    order_type: str = Field(..., pattern="^(market|limit)$")
    quantity: float = Field(..., gt=0)
    limit_price: Optional[float] = Field(None, gt=0)
    time_in_force: str = Field("gtc", pattern="^(day|gtc|ioc|fok)$")


class OrderResultResponse(BaseModel):
    order_id: str
    broker_order_id: str
    status: str
    submitted_at: datetime
