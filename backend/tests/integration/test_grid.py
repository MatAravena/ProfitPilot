"""Integration tests for the grid-backtest endpoint. Mirrors test_dca_compare.py's pattern:
patch fetch_ohlcv at its import site in backtest_service, drive the real HTTP client fixture."""
from __future__ import annotations

import math
from unittest.mock import AsyncMock, patch

import pytest

from app.core.enums import Timeframe
from tests.conftest import make_bars


def _btc_bars(n: int = 300):
    closes = [30_000 + 3_000 * math.sin(i / 12) for i in range(n)]
    return make_bars(closes, timeframe=Timeframe.H1)


@pytest.mark.asyncio
async def test_grid_endpoint_returns_both_arms(client):
    with patch("app.services.backtest_service.fetch_ohlcv", new=AsyncMock(return_value=_btc_bars())):
        resp = await client.post("/api/v1/backtests/grid", json={"symbol": "BTCUSDT", "timeframe": "1h"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["arms"]) == {"grid_guarded_reanchor", "grid_accumulate_nostop"}
    assert body["funding_rate_caveat"]
    for arm in body["arms"].values():
        assert len(arm["equity_curve"]) > 0
        assert "worst_unrealized_pct" in arm


@pytest.mark.asyncio
async def test_grid_endpoint_rejects_too_little_data(client):
    with patch("app.services.backtest_service.fetch_ohlcv", new=AsyncMock(return_value=_btc_bars(10))):
        resp = await client.post("/api/v1/backtests/grid", json={"symbol": "BTCUSDT", "timeframe": "1h"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_grid_endpoint_rejects_unknown_timeframe(client):
    with patch("app.services.backtest_service.fetch_ohlcv", new=AsyncMock(return_value=_btc_bars())):
        resp = await client.post("/api/v1/backtests/grid", json={"symbol": "BTCUSDT", "timeframe": "3h"})
    assert resp.status_code == 400
