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

# A single multi-row INSERT binds (rows × columns) parameters. SQLite caps this
# at SQLITE_MAX_VARIABLE_NUMBER (999 before 3.32, 32766 after), so a multi-year
# intraday fetch of several thousand bars overflows it with "too many SQL
# variables". Insert in chunks that stay well under even the pre-3.32 limit.
_COLUMNS_PER_ROW = 8
_MAX_BIND_PARAMS = 900
_CHUNK_ROWS = _MAX_BIND_PARAMS // _COLUMNS_PER_ROW  # 112 rows per statement


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
        for i in range(0, len(values), _CHUNK_ROWS):
            chunk = values[i : i + _CHUNK_ROWS]
            stmt = _insert(OhlcvBar).values(chunk).on_conflict_do_nothing()
            await self._session.execute(stmt)
        await self._session.flush()
