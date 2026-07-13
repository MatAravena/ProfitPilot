"""Unit tests for OhlcvRepository.

Regression coverage for the SQLite "too many SQL variables" failure: a large
backtest range (e.g. 4h bars over several years) returns thousands of bars, and
a single multi-row INSERT blows past SQLITE_MAX_VARIABLE_NUMBER. upsert_bars
must chunk the write so any number of bars can be persisted.
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.db.ohlcv_bar import OhlcvBar  # noqa: F401 — registers the table on Base
from app.repositories.ohlcv_repository import OhlcvRepository
from tests.conftest import make_bars


@pytest.fixture()
async def session() -> AsyncSession:
    """In-memory SQLite session with the ohlcv table created."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_upsert_bars_handles_large_batch(session: AsyncSession):
    """Persisting more rows than SQLite's bind-variable limit must not raise.

    Modern SQLite caps a statement at 32766 bind params; with 8 columns per row
    that is ~4095 rows. Use well above that so a single-INSERT implementation
    fails with 'too many SQL variables' and the chunked implementation passes.
    """
    closes = [30_000 + i for i in range(6000)]
    bars = make_bars(closes)  # 6000 bars × 8 columns = 48000 bind params

    repo = OhlcvRepository(session)
    await repo.upsert_bars(bars)
    await session.commit()

    stored = await repo.get_range("BTCUSDT", "1d", start=None, end=None)
    assert len(stored) == 6000


@pytest.mark.asyncio
async def test_upsert_bars_is_idempotent(session: AsyncSession):
    """ON CONFLICT DO NOTHING: re-upserting the same bars adds no duplicates."""
    bars = make_bars([100.0 + i for i in range(10)])
    repo = OhlcvRepository(session)

    await repo.upsert_bars(bars)
    await repo.upsert_bars(bars)
    await session.commit()

    stored = await repo.get_range("BTCUSDT", "1d", start=None, end=None)
    assert len(stored) == 10
