from __future__ import annotations
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.types import OHLCV
from app.models.db.ohlcv_bar import OhlcvBar

_IS_SQLITE = get_settings().DATABASE_URL.startswith("sqlite")

if _IS_SQLITE:
    from sqlalchemy.dialects.sqlite import insert as _insert
else:
    from sqlalchemy.dialects.postgresql import insert as _insert


class OhlcvRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_range(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[datetime],
        end: Optional[datetime],
    ) -> List[OhlcvBar]:
        stmt = (
            select(OhlcvBar)
            .where(OhlcvBar.symbol == symbol)
            .where(OhlcvBar.timeframe == timeframe)
        )
        if start:
            stmt = stmt.where(OhlcvBar.timestamp >= start)
        if end:
            stmt = stmt.where(OhlcvBar.timestamp <= end)
        stmt = stmt.order_by(OhlcvBar.timestamp)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_bars(self, bars: List[OHLCV]) -> None:
        if not bars:
            return
        values = [
            {
                "symbol": bar.symbol,
                "timeframe": bar.timeframe.value,
                "timestamp": bar.timestamp,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in bars
        ]
        stmt = _insert(OhlcvBar).values(values).on_conflict_do_nothing()
        await self._session.execute(stmt)
        await self._session.flush()
