"""Integration tests for the Monte Carlo backtest endpoint."""
from __future__ import annotations

import math
from unittest.mock import AsyncMock, patch

import pytest

import app.domain.strategy.examples.sma_crossover  # noqa: F401 — registers SmaCrossover (order-independent)
from app.core.types import OHLCV
from tests.conftest import make_bars


def _fake_bars(n: int = 200) -> list[OHLCV]:
    """Oscillating + drifting closes so SmaCrossover crosses several times (≥2 trades)."""
    closes = [30_000 + 1_500 * math.sin(i / 8) + i * 5 for i in range(n)]
    return make_bars(closes)


def _mc_body(**overrides) -> dict:
    body = {
        "strategy_name": "SmaCrossover",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "initial_capital": 10000,
        "commission_pct": 0.001,
        "parameters": {"fast_period": 10, "slow_period": 30},
        "n_simulations": 500,
        "seed": 42,
    }
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_montecarlo_returns_well_formed_distribution(client):
    with patch(
        "app.services.backtest_service.fetch_ohlcv",
        new=AsyncMock(return_value=_fake_bars(200)),
    ):
        resp = await client.post("/api/v1/backtests/montecarlo", json=_mc_body())

    assert resp.status_code == 200
    body = resp.json()
    assert body["strategy_name"] == "SmaCrossover"
    assert body["n_simulations"] == 500
    assert body["n_trades"] >= 2

    assert set(body["methods"]) == {"bootstrap", "shuffle"}
    for method in body["methods"].values():
        for metric in ("final_equity", "total_return_pct", "max_drawdown_pct"):
            stats = method[metric]
            assert stats["p5"] <= stats["p50"] <= stats["p95"]
        assert 0.0 <= method["prob_profit"] <= 1.0
        assert 0.0 <= method["risk_of_ruin"] <= 1.0
        hist = method["histogram"]
        assert len(hist["edges"]) == len(hist["counts"]) + 1
        assert sum(hist["counts"]) == 500


@pytest.mark.asyncio
async def test_montecarlo_fewer_than_two_trades_returns_400(client):
    # AlwaysLong opens once and holds → a single completed trade → cannot resample.
    with patch(
        "app.services.backtest_service.fetch_ohlcv",
        new=AsyncMock(return_value=_fake_bars(200)),
    ):
        resp = await client.post("/api/v1/backtests/montecarlo", json=_mc_body(
            strategy_name="AlwaysLong",
            symbol="MCONETRADEUSDT",
            parameters={},
        ))

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_montecarlo_seed_makes_response_deterministic(client):
    with patch(
        "app.services.backtest_service.fetch_ohlcv",
        new=AsyncMock(return_value=_fake_bars(200)),
    ):
        first = await client.post("/api/v1/backtests/montecarlo", json=_mc_body(seed=7))
        second = await client.post("/api/v1/backtests/montecarlo", json=_mc_body(seed=7))

    assert first.status_code == second.status_code == 200
    assert first.json()["methods"] == second.json()["methods"]


@pytest.mark.asyncio
async def test_montecarlo_only_requested_method_is_returned(client):
    with patch(
        "app.services.backtest_service.fetch_ohlcv",
        new=AsyncMock(return_value=_fake_bars(200)),
    ):
        resp = await client.post("/api/v1/backtests/montecarlo", json=_mc_body(methods=["bootstrap"]))

    assert resp.status_code == 200
    assert set(resp.json()["methods"]) == {"bootstrap"}
