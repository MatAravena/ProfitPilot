from __future__ import annotations
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.db.user import User
from app.repositories.broker_connection_repository import BrokerConnectionRepository
from app.repositories.user_repository import UserRepository
from app.services.broker_service import BrokerService
from app.services.portfolio_service import PortfolioService

# Fixed UUID for the single local user — stable across restarts
LOCAL_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


async def get_current_user(db: Annotated[AsyncSession, Depends(get_db)]) -> User:
    """Phase 1 (local mode): always returns the seeded local user. No auth required."""
    user = await UserRepository(db).get(LOCAL_USER_ID)
    if user is None:
        raise RuntimeError("Local user not seeded — check startup logs")
    return user


def get_broker_service(db: Annotated[AsyncSession, Depends(get_db)]) -> BrokerService:
    return BrokerService(BrokerConnectionRepository(db))


def get_portfolio_service(
    broker_service: Annotated[BrokerService, Depends(get_broker_service)],
) -> PortfolioService:
    return PortfolioService(broker_service)
