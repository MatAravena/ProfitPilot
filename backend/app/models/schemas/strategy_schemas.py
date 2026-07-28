from __future__ import annotations
from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.config import get_settings

_s = get_settings()


class ExecutionConfig(BaseModel):
    """Per-strategy config. Behavioral fields (size, short, poll) are always set on the
    strategy. Risk fields are OPTIONAL overrides — None means inherit the user's RiskProfile.
    A 0% stop/target would trigger at entry, so risk %s are gt=0; 'no take-profit' is null."""

    # Behavioral — always per-strategy.
    size_pct: float = Field(default=_s.DEFAULT_MAX_POSITION_SIZE_PCT, gt=0, le=1,
                            description="Position size as a fraction of account equity")
    allow_short: bool = True
    poll_seconds: Optional[int] = Field(default=None, ge=5,
                                        description="Override poll cadence; None derives it from the timeframe")

    # Risk overrides — None = inherit the user's risk profile.
    stop_loss_pct: Optional[float] = Field(default=None, gt=0, le=1)
    take_profit_pct: Optional[float] = Field(default=None, gt=0, le=5)
    max_open_positions: Optional[int] = Field(default=None, ge=1)
    max_daily_drawdown_pct: Optional[float] = Field(default=None, ge=0, le=1)
    max_total_drawdown_pct: Optional[float] = Field(default=None, ge=0, le=1)
    max_orders_per_minute: Optional[int] = Field(default=None, ge=1)
    kill_switch_enabled: Optional[bool] = None

    @classmethod
    def from_instance(cls, inst) -> "ExecutionConfig":
        # model_construct: reading persisted state must not re-run input validators. A row
        # written under looser bounds (or a bound we later tighten) would otherwise raise on
        # read and 500 the whole list endpoint. Column values are already trusted.
        #
        # Field names are derived from the model itself — this class is the single source of
        # truth for the config field set. Every ExecutionConfig field must have a matching
        # StrategyInstance column (enforced by test_execution_config_fields_map_to_orm_columns).
        return cls.model_construct(**{name: getattr(inst, name) for name in cls.model_fields})


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
    """Partial update of a strategy's execution/risk config: only fields present in
    the request body are applied (see StrategyService.update_config + exclude_unset).
    Omitted fields keep their current value; an explicit null clears a risk override."""


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
