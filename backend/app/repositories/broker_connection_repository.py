from __future__ import annotations
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.broker_connection import BrokerConnection
from app.repositories.base import BaseRepository


class BrokerConnectionRepository(BaseRepository[BrokerConnection]):
    def __init__(self, session: AsyncSession):
        super().__init__(BrokerConnection, session)

    async def get_by_user(self, user_id: UUID) -> List[BrokerConnection]:
        result = await self._session.execute(
            select(BrokerConnection).where(
                BrokerConnection.user_id == user_id,
                BrokerConnection.is_active == True,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    async def get_by_user_and_broker(self, user_id: UUID, broker_id: str) -> Optional[BrokerConnection]:
        result = await self._session.execute(
            select(BrokerConnection).where(
                BrokerConnection.user_id == user_id,
                BrokerConnection.broker_id == broker_id,
                BrokerConnection.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def deactivate(self, connection: BrokerConnection) -> None:
        connection.is_active = False
        await self._session.flush()
