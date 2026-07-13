"""End-to-end OHLCV cache-aside flow through BacktestService.

Complements the repo-level unit tests (chunking/idempotency): here we verify the
service's cache-aside logic — first run over an uncached range is a cache MISS
(fetch + write), and a second identical run is a cache HIT served from the DB
without re-fetching. The 200-bar range also exercises the chunked write path
(>112 rows per the SQLite bind-variable limit).
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.enums import Timeframe
from app.models.schemas.backtest_schemas import BacktestRequest
from app.services.backtest_service import BacktestService
from tests.conftest import make_bars

pytestmark = pytest.mark.asyncio

# Unique symbol → the cache starts empty regardless of bars other tests left behind.
_SYMBOL = "RANGECACHEUSDT"


async def _create_tables():
    from app.db.base import engine, Base
    import app.models.db  # noqa: F401 — registers ORM models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _clear_symbol():
    """Drop any cached bars for our symbol so the first run is a guaranteed miss
    (the shared dev DB can persist rows between runs)."""
    from sqlalchemy import delete
    from app.db.base import AsyncSessionLocal
    from app.models.db.ohlcv_bar import OhlcvBar
    async with AsyncSessionLocal() as s:
        await s.execute(delete(OhlcvBar).where(OhlcvBar.symbol == _SYMBOL))
        await s.commit()


async def test_cache_aside_writes_then_serves_from_db(client):
    await _create_tables()
    await _clear_symbol()

    # 200 daily bars from 2022-01-01 (>112 → chunked write), spanning the
    # requested [start, end] so _cache_covers() treats the range as covered.
    bars = make_bars(
        [30_000 + i for i in range(200)],
        symbol=_SYMBOL, timeframe=Timeframe.D1,
        base_ts=datetime(2022, 1, 1, tzinfo=timezone.utc),
    )
    req = BacktestRequest(
        strategy_name="AlwaysLong", symbol=_SYMBOL, timeframe="1d",
        start="2022-01-01T00:00:00Z", end="2022-06-30T00:00:00Z",
        initial_capital=10_000, commission_pct=0.001, parameters={},
    )
    svc = BacktestService()
    fetch_mock = AsyncMock(return_value=bars)

    with patch("app.services.backtest_service.fetch_ohlcv", new=fetch_mock):
        first = await svc._get_bars(req, Timeframe.D1)    # cache miss → fetch + write
        second = await svc._get_bars(req, Timeframe.D1)   # cache hit → from DB

    # Provider hit exactly once across both runs (second run served from cache).
    fetch_mock.assert_awaited_once()
    assert len(first) == 200
    assert len(second) > 0

    # The write path actually persisted all 200 bars.
    from app.db.base import AsyncSessionLocal
    from app.repositories.ohlcv_repository import OhlcvRepository
    async with AsyncSessionLocal() as s:
        stored = await OhlcvRepository(s).get_range(_SYMBOL, "1d", start=None, end=None)
    assert len(stored) == 200

    await _clear_symbol()  # leave no residue in the shared dev DB
