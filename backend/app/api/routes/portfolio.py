from __future__ import annotations
from datetime import datetime
from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import LOCAL_USER_ID, get_current_user, get_db, get_portfolio_service
from app.models.db.portfolio_snapshot import PortfolioSnapshot
from app.models.db.user import User
from app.models.schemas.broker_schemas import PortfolioSummaryResponse, PositionResponse
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

CurrentUser = Annotated[User, Depends(get_current_user)]
PortfolioSvc = Annotated[PortfolioService, Depends(get_portfolio_service)]


@router.get("/summary", response_model=PortfolioSummaryResponse)
async def get_portfolio_summary(user: CurrentUser, svc: PortfolioSvc):
    """Aggregate equity, cash, P&L, and positions across all connected brokers."""
    try:
        return await svc.get_summary(user.id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Portfolio fetch failed: {exc}")


@router.get("/positions", response_model=List[PositionResponse])
async def get_positions(user: CurrentUser, svc: PortfolioSvc):
    """Return all open positions across all connected brokers (priority: Bybit → Binance → Alpaca)."""
    try:
        return await svc.get_positions(user.id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Positions fetch failed: {exc}")


class SnapshotPoint(BaseModel):
    snapped_at: datetime
    equity: float
    cash: float
    unrealized_pnl: float


@router.get("/history", response_model=List[SnapshotPoint])
async def get_portfolio_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(500, ge=1, le=2000),
):
    """Return equity-over-time snapshots for the P&L graph, oldest-first."""
    result = await db.execute(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.user_id == LOCAL_USER_ID)
        .order_by(PortfolioSnapshot.snapped_at.desc())
        .limit(limit)
    )
    rows = list(reversed(result.scalars().all()))
    return [
        SnapshotPoint(
            snapped_at=r.snapped_at,
            equity=r.equity,
            cash=r.cash,
            unrealized_pnl=r.unrealized_pnl,
        )
        for r in rows
    ]
