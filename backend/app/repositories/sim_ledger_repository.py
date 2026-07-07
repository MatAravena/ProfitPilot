from __future__ import annotations
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.sim_ledger import SimAccount, SimPosition


class SimLedgerRepository:
    """DB access for the paper-trading virtual ledger. No accounting logic here —
    that lives in SimulatedBrokerAdapter."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_account(self, strategy_id: UUID) -> Optional[SimAccount]:
        stmt = select(SimAccount).where(SimAccount.strategy_instance_id == strategy_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create_account(
        self, strategy_id: UUID, user_id: UUID, starting_equity: float
    ) -> SimAccount:
        acc = SimAccount(
            strategy_instance_id=strategy_id,
            user_id=user_id,
            cash=starting_equity,
            realized_pnl=0.0,
            starting_equity=starting_equity,
        )
        self._session.add(acc)
        await self._session.flush()
        return acc

    async def get_positions(self, strategy_id: UUID) -> List[SimPosition]:
        stmt = select(SimPosition).where(SimPosition.strategy_instance_id == strategy_id)
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_position(self, strategy_id: UUID, symbol: str) -> Optional[SimPosition]:
        stmt = (
            select(SimPosition)
            .where(SimPosition.strategy_instance_id == strategy_id)
            .where(SimPosition.symbol == symbol)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    def add_position(self, pos: SimPosition) -> None:
        self._session.add(pos)

    async def delete_position(self, pos: SimPosition) -> None:
        await self._session.delete(pos)
