from __future__ import annotations
from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CreateStrategyRequest(BaseModel):
    class_name: str
    label: str = Field("", max_length=128)
    symbol: str = Field(..., min_length=1, max_length=32)
    timeframe: str = "1d"
    broker_connection_id: Optional[UUID] = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class UpdateStrategyStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(draft|paper|live|paused|archived)$")


class StrategyInstanceResponse(BaseModel):
    id: UUID
    class_name: str
    label: str
    symbol: str
    timeframe: str
    broker_connection_id: Optional[UUID]
    status: str
    parameters: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    last_signal_at: Optional[datetime]
    error_count: int

    model_config = {"from_attributes": True}
