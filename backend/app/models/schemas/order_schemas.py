from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class OrderRecordResponse(BaseModel):
    """One row from order_records — an order attempt made by the executor."""

    id: UUID
    symbol: str
    side: Optional[str]
    quantity: Optional[float]
    status: str
    reason: Optional[str]
    avg_price: Optional[float]
    filled_qty: Optional[float]
    realized_pnl: Optional[float]
    signal_id: Optional[UUID]
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderHistoryResponse(BaseModel):
    """Paginated user-wide order history."""

    items: List[OrderRecordResponse]
    total: int
