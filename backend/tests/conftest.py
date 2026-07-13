"""
Shared fixtures for all tests.

Unit tests import domain code directly — no DB, no HTTP.
Integration tests use an in-memory SQLite DB via the FastAPI TestClient.
"""
from __future__ import annotations

import os

# Force an isolated in-memory DB BEFORE any app module imports (and thus caches
# get_settings()). Otherwise `.env`'s file-backed DATABASE_URL wins and the whole
# suite runs against — and mutates — the real dev DB (profitpilot.db). Must run
# at conftest import time, before the `from app.core...` imports below.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from datetime import datetime, timezone
from typing import List

from app.core.enums import Timeframe
from app.core.types import OHLCV


# ── OHLCV factory ──────────────────────────────────────────────────────────────

def make_bars(
    closes: List[float],
    symbol: str = "BTCUSDT",
    timeframe: Timeframe = Timeframe.D1,
    base_ts: datetime | None = None,
) -> List[OHLCV]:
    """Build a list of OHLCV bars from a list of close prices."""
    if base_ts is None:
        base_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)

    from datetime import timedelta
    bars = []
    for i, close in enumerate(closes):
        ts = base_ts + timedelta(days=i)
        bars.append(OHLCV(
            timestamp=ts,
            symbol=symbol,
            open=close * 0.999,
            high=close * 1.001,
            low=close * 0.998,
            close=close,
            volume=1000.0,
            timeframe=timeframe,
        ))
    return bars


# ── Async HTTP client for integration tests ────────────────────────────────────

@pytest.fixture()
async def client():
    """FastAPI async test client backed by an in-memory SQLite DB."""
    import os
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    from httpx import AsyncClient, ASGITransport
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
