from __future__ import annotations
from typing import Optional

from pydantic import BaseModel, Field

from app.core.config import get_settings

_s = get_settings()


class RiskProfileSchema(BaseModel):
    """Per-user risk defaults (SL/TP + account-level limits). Used for GET and PUT."""

    stop_loss_pct: float = Field(default=_s.DEFAULT_STOP_LOSS_PCT, gt=0, le=1)
    take_profit_pct: Optional[float] = Field(default=None, gt=0, le=5)
    max_open_positions: int = Field(default=_s.DEFAULT_MAX_OPEN_POSITIONS, ge=1)
    max_daily_drawdown_pct: float = Field(default=_s.DEFAULT_MAX_DAILY_DRAWDOWN_PCT, ge=0, le=1)
    max_total_drawdown_pct: float = Field(default=_s.DEFAULT_MAX_TOTAL_DRAWDOWN_PCT, ge=0, le=1)
    max_orders_per_minute: int = Field(default=_s.DEFAULT_MAX_ORDERS_PER_MINUTE, ge=1)
    kill_switch_enabled: bool = True

    @classmethod
    def from_profile(cls, p) -> "RiskProfileSchema":
        # model_construct: reading persisted state must not re-run input validators.
        return cls.model_construct(
            stop_loss_pct=p.stop_loss_pct,
            take_profit_pct=p.take_profit_pct,
            max_open_positions=p.max_open_positions,
            max_daily_drawdown_pct=p.max_daily_drawdown_pct,
            max_total_drawdown_pct=p.max_total_drawdown_pct,
            max_orders_per_minute=p.max_orders_per_minute,
            kill_switch_enabled=p.kill_switch_enabled,
        )
