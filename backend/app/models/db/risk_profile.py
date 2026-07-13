from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskProfile(Base):
    """Per-user risk defaults. SL/TP and account-level risk limits live here (not on the
    strategy) — every strategy the user runs is governed by this one profile."""

    __tablename__ = "risk_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_risk_profile_user"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(native_uuid=False), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(native_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stop_loss_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.015)
    take_profit_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_open_positions: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_daily_drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.03)
    max_total_drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.10)
    max_orders_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    kill_switch_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
