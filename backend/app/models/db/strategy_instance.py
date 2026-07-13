from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StrategyInstance(Base):
    __tablename__ = "strategy_instances"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(native_uuid=False), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(native_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    class_name: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False, default="1d")
    broker_connection_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(native_uuid=False), ForeignKey("broker_connections.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # ── Behavioral config (always per-strategy) ──
    size_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.02)
    allow_short: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    poll_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # None → derive from timeframe

    # ── Risk overrides (NULL ⇒ inherit the user's RiskProfile) ──
    stop_loss_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_open_positions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_daily_drawdown_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_total_drawdown_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_orders_per_minute: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    kill_switch_enabled: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_signal_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Persisted total-drawdown high-water mark, so the baseline survives restarts.
    peak_equity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
