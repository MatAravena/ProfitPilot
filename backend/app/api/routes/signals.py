from __future__ import annotations
from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import LOCAL_USER_ID, get_db
from app.models.db.signal_record import SignalRecord

router = APIRouter(prefix="/signals", tags=["signals"])


class SignalResponse(BaseModel):
    id: UUID
    strategy_instance_id: UUID
    symbol: str
    timeframe: str
    direction: str
    confidence: float
    source: str
    generated_at: datetime
    close_price: Optional[float]

    model_config = {"from_attributes": True}


@router.get("", response_model=List[SignalResponse])
async def list_signals(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=200),
    strategy_id: Optional[UUID] = Query(None),
):
    """Return most recent signals for the local user, newest first."""
    q = select(SignalRecord).where(SignalRecord.user_id == LOCAL_USER_ID)
    if strategy_id:
        q = q.where(SignalRecord.strategy_instance_id == strategy_id)
    q = q.order_by(SignalRecord.generated_at.desc()).limit(limit)

    result = await db.execute(q)
    return list(result.scalars().all())
