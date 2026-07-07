from __future__ import annotations
from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.config import get_settings

_s = get_settings()


class ExecutionConfig(BaseModel):
    """Per-strategy execution + risk envelope. Every field is adjustable per
    instance; defaults come from the global settings."""

    size_pct: float = Field(default=_s.DEFAULT_MAX_POSITION_SIZE_PCT, gt=0, le=1,
                            description="Position size as a fraction of account equity")
    stop_loss_pct: float = Field(default=_s.DEFAULT_STOP_LOSS_PCT, ge=0, le=1)
    take_profit_pct: Optional[float] = Field(default=None, ge=0, le=5)
    max_open_positions: int = Field(default=_s.DEFAULT_MAX_OPEN_POSITIONS, ge=1)
    max_daily_drawdown_pct: float = Field(default=_s.DEFAULT_MAX_DAILY_DRAWDOWN_PCT, ge=0, le=1)
    max_total_drawdown_pct: float = Field(default=_s.DEFAULT_MAX_TOTAL_DRAWDOWN_PCT, ge=0, le=1)
    max_orders_per_minute: int = Field(default=_s.DEFAULT_MAX_ORDERS_PER_MINUTE, ge=1)
    allow_short: bool = True
    kill_switch_enabled: bool = True
    poll_seconds: Optional[int] = Field(default=None, ge=5,
                                        description="Override poll cadence; None derives it from the timeframe")

    @classmethod
    def from_instance(cls, inst) -> "ExecutionConfig":
        return cls(
            size_pct=inst.size_pct,
            stop_loss_pct=inst.stop_loss_pct,
            take_profit_pct=inst.take_profit_pct,
            max_open_positions=inst.max_open_positions,
            max_daily_drawdown_pct=inst.max_daily_drawdown_pct,
            max_total_drawdown_pct=inst.max_total_drawdown_pct,
            max_orders_per_minute=inst.max_orders_per_minute,
            allow_short=inst.allow_short,
            kill_switch_enabled=inst.kill_switch_enabled,
            poll_seconds=inst.poll_seconds,
        )


class CreateStrategyRequest(BaseModel):
    class_name: str
    label: str = Field("", max_length=128)
    symbol: str = Field(..., min_length=1, max_length=32)
    timeframe: str = "1d"
    broker_connection_id: Optional[UUID] = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)


class UpdateStrategyStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(draft|paper|live|paused|archived)$")


class UpdateStrategyConfigRequest(ExecutionConfig):
    """Full replacement of a strategy's execution/risk config."""


class StrategyInstanceResponse(BaseModel):
    id: UUID
    class_name: str
    label: str
    symbol: str
    timeframe: str
    broker_connection_id: Optional[UUID]
    status: str
    parameters: dict[str, Any]
    execution: ExecutionConfig
    created_at: datetime
    updated_at: datetime
    last_signal_at: Optional[datetime]
    error_count: int

    model_config = {"from_attributes": True}

    @classmethod
    def from_instance(cls, inst) -> "StrategyInstanceResponse":
        return cls(
            id=inst.id,
            class_name=inst.class_name,
            label=inst.label,
            symbol=inst.symbol,
            timeframe=inst.timeframe,
            broker_connection_id=inst.broker_connection_id,
            status=inst.status,
            parameters=inst.parameters,
            execution=ExecutionConfig.from_instance(inst),
            created_at=inst.created_at,
            updated_at=inst.updated_at,
            last_signal_at=inst.last_signal_at,
            error_count=inst.error_count,
        )
