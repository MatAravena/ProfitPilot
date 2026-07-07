"""Integration tests for the market OHLCV endpoint."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_bars


@pytest.mark.asyncio
async def test_ohlcv_bybit_source(client):
    fake = make_bars([50_000.0] * 10)
    with patch("app.api.routes.market._fetch_bybit_page", new=AsyncMock(return_value=fake)):
        resp = await client.get("/api/v1/market/ohlcv?symbol=BTCUSDT&timeframe=1d&limit=10&source=bybit")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 10
    assert data[0]["close"] == 50_000.0
    assert "time" in data[0]


@pytest.mark.asyncio
async def test_ohlcv_unknown_timeframe_returns_400(client):
    resp = await client.get("/api/v1/market/ohlcv?symbol=BTCUSDT&timeframe=99y")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_ohlcv_response_shape(client):
    fake = make_bars([1.0, 2.0, 3.0])
    with patch("app.api.routes.market._fetch_bybit_page", new=AsyncMock(return_value=fake)):
        resp = await client.get("/api/v1/market/ohlcv?symbol=BTCUSDT&timeframe=1d&limit=3&source=bybit")
    assert resp.status_code == 200
    for candle in resp.json():
        for field in ("time", "open", "high", "low", "close", "volume"):
            assert field in candle
