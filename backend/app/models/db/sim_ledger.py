"""Persisted virtual ledger for the paper-trading SimulatedBrokerAdapter.

Keeps paper positions and cash durable across restarts, so a running paper
strategy resumes from its real state rather than a blank slate.
"""
from __future__ import annotations
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SimAccount(Base):
    __tablename__ = "sim_accounts"
    __table_args__ = (UniqueConstraint("strategy_instance_id", name="uq_sim_account_strategy"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(native_uuid=False), primary_key=True, default=uuid.uuid4)
    strategy_instance_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(native_uuid=False),
        ForeignKey("strategy_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(native_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    starting_equity: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SimPosition(Base):
    __tablename__ = "sim_positions"
    __table_args__ = (
        UniqueConstraint("strategy_instance_id", "symbol", name="uq_sim_position_strategy_symbol"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(native_uuid=False), primary_key=True, default=uuid.uuid4)
    strategy_instance_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(native_uuid=False),
        ForeignKey("strategy_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(native_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    avg_entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
