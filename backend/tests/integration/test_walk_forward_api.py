"""POST /api/v1/backtests/walk-forward — through the real route, service, engine."""
from __future__ import annotations

import math
from unittest.mock import AsyncMock, patch

import pytest

import app.domain.strategy.examples.sma_crossover  # noqa: F401 — registers built-ins
from tests.conftest import make_bars

URL = "/api/v1/backtests/walk-forward"


def _bars(n=900):
    return make_bars([30_000 + 1_500 * math.sin(i / 9) + 800 * math.sin(i / 37) + i * 3 for i in range(n)])


def _body(**overrides):
    body = {
        "strategy_name": "SmaCrossover", "symbol": "BTCUSDT", "timeframe": "1d",
        "param_grid": {"fast_period": [5, 10, 60], "slow_period": [30, 50]},
        "train_days": 300, "test_days": 100,
    }
    body.update(overrides)
    return body


async def _post(client, body, bars=None):
    with patch("app.services.backtest_service.fetch_ohlcv",
               new=AsyncMock(return_value=bars if bars is not None else _bars())):
        return await client.post(URL, json=body)


@pytest.mark.asyncio
async def test_walk_forward_returns_out_of_sample_folds(client):
    resp = await _post(client, _body())
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # 900 daily bars, 300 train + 100 test, stepping by 100 → 6 folds.
    assert len(body["folds"]) == 6
    assert body["train_bars"] == 300 and body["test_bars"] == 100
    # fast=60 is >= both slow values → rejected by the strategy itself, not fatal.
    assert body["combinations"] == 4 and body["skipped_combinations"] == 2
    folds = body["folds"]
    assert all(a["test_end"] < b["test_start"] for a, b in zip(folds, folds[1:]))
    assert all(f["train_end"] < f["test_start"] for f in folds)
    assert all(f["params"]["fast_period"] in (5, 10) for f in folds)
    assert body["equity_curve"] and body["buy_hold_curve"]
    assert "out-of-sample" in body["caveat"]


@pytest.mark.asyncio
async def test_windows_are_calendar_days_for_markets_closed_at_weekends(client):
    """Stocks trade ~252 days a year. 365 calendar days of training must be ~252 bars,
    not 365 (which would silently be ~1.45 years of stock data)."""
    from datetime import datetime, timedelta, timezone
    from app.core.enums import Timeframe
    from app.core.types import OHLCV

    day, bars = datetime(2020, 1, 1, tzinfo=timezone.utc), []
    while len(bars) < 1200:
        if day.weekday() < 5:
            price = 300 + 20 * math.sin(len(bars) / 11)
            bars.append(OHLCV(timestamp=day, symbol="SPY", open=price, high=price * 1.01,
                              low=price * 0.99, close=price, volume=1.0, timeframe=Timeframe.D1))
        day += timedelta(days=1)

    resp = await _post(client, _body(symbol="SPY", train_days=365, test_days=91), bars=bars)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert 245 <= body["train_bars"] <= 265
    assert 60 <= body["test_bars"] <= 68


@pytest.mark.asyncio
async def test_too_little_data_for_one_fold_is_a_400(client):
    resp = await _post(client, _body(train_days=800, test_days=200))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_param_both_fixed_and_searched_is_a_400(client):
    resp = await _post(client, _body(parameters={"fast_period": 5}))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_oversized_grid_is_rejected_before_running(client):
    grid = {"fast_period": list(range(2, 22)), "slow_period": list(range(30, 50))}   # 400 combos
    resp = await _post(client, _body(param_grid=grid))
    assert resp.status_code == 422
