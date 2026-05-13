from __future__ import annotations
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.strategy_instance import StrategyInstance
from app.repositories.base import BaseRepository


class StrategyInstanceRepository(BaseRepository[StrategyInstance]):
    def __init__(self, session: AsyncSession):
        super().__init__(StrategyInstance, session)

    async def list_by_user(self, user_id: UUID) -> List[StrategyInstance]:
        result = await self._session.execute(
            select(StrategyInstance).where(StrategyInstance.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_by_user(self, id: UUID, user_id: UUID) -> Optional[StrategyInstance]:
        result = await self._session.execute(
            select(StrategyInstance).where(
                StrategyInstance.id == id,
                StrategyInstance.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()
