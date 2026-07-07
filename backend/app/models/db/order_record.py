from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrderRecord(Base):
    """One row per order attempt made by the executor — placed, closed, skipped,
    rejected (risk veto) or errored. The audit trail for why a strategy did (or
    did not) act on a signal."""

    __tablename__ = "order_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(native_uuid=False), primary_key=True, default=uuid.uuid4)
    strategy_instance_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(native_uuid=False),
        ForeignKey("strategy_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(native_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)      # buy / sell
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)           # ExecutionOutcome.action
    reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    filled_qty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    signal_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(native_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
