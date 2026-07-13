"""Integration tests for the backtests endpoints."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.core.enums import Timeframe
from app.core.types import OHLCV
from tests.conftest import make_bars


def _fake_bars(n: int = 200) -> list[OHLCV]:
    """Generate n synthetic daily bars with a mild uptrend."""
    import math
    closes = [30_000 + 100 * math.sin(i / 10) + i * 5 for i in range(n)]
    return make_bars(closes)


@pytest.mark.asyncio
async def test_list_backtest_strategies(client):
    resp = await client.get("/api/v1/backtests/strategies")
    assert resp.status_code == 200
    body = resp.json()
    names = [s["class_name"] for s in body["strategies"]]
    assert "SmaCrossover" in names
    assert "RsiMeanReversion" in names


@pytest.mark.asyncio
async def test_list_strategies_have_metadata(client):
    resp = await client.get("/api/v1/backtests/strategies")
    assert resp.status_code == 200
    for strat in resp.json()["strategies"]:
        assert "display_name" in strat
        assert "description" in strat
        assert isinstance(strat["parameters"], list)


@pytest.mark.asyncio
async def test_run_backtest_sma_crossover(client):
    """Run a SmaCrossover backtest with mocked market data."""
    with patch(
        "app.services.backtest_service.fetch_ohlcv",
        new=AsyncMock(return_value=_fake_bars(200)),
    ):
        resp = await client.post("/api/v1/backtests/run", json={
            "strategy_name": "SmaCrossover",
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "initial_capital": 10000,
            "commission_pct": 0.001,
            "parameters": {"fast_period": 10, "slow_period": 30},
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["strategy_name"] == "SmaCrossover"
    assert body["symbol"] == "BTCUSDT"
    assert "metrics" in body
    assert "equity_curve" in body
    assert isinstance(body["trades"], list)


@pytest.mark.asyncio
async def test_run_backtest_forwards_requested_date_range(client):
    """Regression: the full requested [start, end] range must reach the data
    provider (not silently truncated to a default lookback)."""
    from app.db.base import engine, Base
    import app.models.db  # noqa: F401 — registers ORM models (ohlcv_bars for the cache path)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Use the always-loaded user strategy so this test is order-independent
    # (built-in examples only register once a /strategies endpoint is hit).
    fetch_mock = AsyncMock(return_value=_fake_bars(200))
    with patch("app.services.backtest_service.fetch_ohlcv", new=fetch_mock):
        resp = await client.post("/api/v1/backtests/run", json={
            # Unique symbol → the OHLCV cache is guaranteed empty, forcing the
            # cache-miss path that forwards start/end to the provider (hermetic
            # regardless of bars other tests left in the shared in-memory DB).
            "strategy_name": "AlwaysLong",
            "symbol": "RANGETESTUSDT",
            "timeframe": "1d",
            "start": "2022-01-01T00:00:00Z",
            "end": "2022-12-31T00:00:00Z",
            "initial_capital": 10000,
            "commission_pct": 0.001,
            "parameters": {},
        })

    assert resp.status_code == 200
    fetch_mock.assert_awaited_once()
    kwargs = fetch_mock.await_args.kwargs
    assert (kwargs["start"].year, kwargs["start"].month, kwargs["start"].day) == (2022, 1, 1)
    assert (kwargs["end"].year, kwargs["end"].month, kwargs["end"].day) == (2022, 12, 31)


@pytest.mark.asyncio
async def test_run_backtest_unknown_strategy_returns_400(client):
    with patch(
        "app.services.backtest_service.fetch_ohlcv",
        new=AsyncMock(return_value=_fake_bars(200)),
    ):
        resp = await client.post("/api/v1/backtests/run", json={
            "strategy_name": "DoesNotExist",
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "initial_capital": 10000,
            "commission_pct": 0.001,
            "parameters": {},
        })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_run_backtest_invalid_timeframe_returns_400(client):
    resp = await client.post("/api/v1/backtests/run", json={
        "strategy_name": "SmaCrossover",
        "symbol": "BTCUSDT",
        "timeframe": "99y",
        "initial_capital": 10000,
        "commission_pct": 0.001,
        "parameters": {},
    })
    assert resp.status_code == 400
