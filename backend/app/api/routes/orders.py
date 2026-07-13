from __future__ import annotations
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import LOCAL_USER_ID, get_db
from app.models.db.order_record import OrderRecord
from app.models.schemas.order_schemas import OrderHistoryResponse

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=OrderHistoryResponse)
async def list_orders(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """User-wide order history (newest first), paginated for the Portfolio page."""
    base = select(OrderRecord).where(OrderRecord.user_id == LOCAL_USER_ID)

    total = await db.scalar(select(func.count()).select_from(base.subquery()))

    q = base.order_by(OrderRecord.created_at.desc()).limit(limit).offset(offset)
    items = list((await db.execute(q)).scalars().all())

    return OrderHistoryResponse(items=items, total=total or 0)
