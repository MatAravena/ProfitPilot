from __future__ import annotations
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.risk_profile import RiskProfile


class RiskProfileRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_user(self, user_id: UUID) -> Optional[RiskProfile]:
        stmt = select(RiskProfile).where(RiskProfile.user_id == user_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, profile: RiskProfile) -> RiskProfile:
        self._session.add(profile)
        await self._session.flush()
        await self._session.refresh(profile)
        return profile
