from __future__ import annotations
from typing import Generic, List, Optional, Type, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, model: Type[ModelT], session: AsyncSession):
        self._model = model
        self._session = session

    async def get(self, id: UUID) -> Optional[ModelT]:
        return await self._session.get(self._model, id)

    async def list(self) -> List[ModelT]:
        result = await self._session.execute(select(self._model))
        return list(result.scalars().all())

    async def add(self, obj: ModelT) -> ModelT:
        self._session.add(obj)
        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self._session.delete(obj)
        await self._session.flush()
