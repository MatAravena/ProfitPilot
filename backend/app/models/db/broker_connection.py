from __future__ import annotations
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BrokerConnection(Base):
    __tablename__ = "broker_connections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(native_uuid=False), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(native_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    broker_id: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(String(512), nullable=False)
    encrypted_secret_key: Mapped[str] = mapped_column(String(512), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    is_paper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user: Mapped[User] = relationship("User", back_populates="broker_connections")


from app.models.db.user import User  # noqa: E402, F401
