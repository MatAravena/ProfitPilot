"""Integration tests for the DCA-vs-cycle-grid comparison endpoint."""
from __future__ import annotations

import math
from unittest.mock import AsyncMock, patch

import pytest

from app.core.types import OHLCV
from tests.conftest import make_bars


def _btc_bars(n: int = 400) -> list[OHLCV]:
    # A cyclical-ish series is enough; the endpoint just needs >= MIN_BACKTEST_BARS bars.
    closes = [20_000 + 8_000 * math.sin(i / 60) + i * 20 for i in range(n)]
    return make_bars(closes)


def _body(**overrides) -> dict:
    body = {
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "capital_model": "contributions",
        "contribution_amount": 100.0,
        "contribution_interval_days": 7,
    }
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_dca_compare_returns_three_arms(client):
    with patch("app.services.backtest_service.fetch_ohlcv",
               new=AsyncMock(return_value=_btc_bars(400))):
        resp = await client.post("/api/v1/backtests/dca-compare", json=_body())
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["arms"]) == {"flat_dca", "smart_accumulate", "full_rotation"}
    assert body["caveat"]
    for arm in body["arms"].values():
        assert arm["total_contributed"] > 0
        assert len(arm["equity_curve"]) > 0


@pytest.mark.asyncio
async def test_dca_compare_same_contributions_across_arms(client):
    with patch("app.services.backtest_service.fetch_ohlcv",
               new=AsyncMock(return_value=_btc_bars(400))):
        resp = await client.post("/api/v1/backtests/dca-compare", json=_body())
    arms = resp.json()["arms"]
    contribs = {name: a["total_contributed"] for name, a in arms.items()}
    assert contribs["flat_dca"] == pytest.approx(contribs["smart_accumulate"])
    assert contribs["flat_dca"] == pytest.approx(contribs["full_rotation"])


@pytest.mark.asyncio
async def test_dca_compare_lump_sum_requires_budget(client):
    with patch("app.services.backtest_service.fetch_ohlcv",
               new=AsyncMock(return_value=_btc_bars(400))):
        resp = await client.post("/api/v1/backtests/dca-compare",
                                 json=_body(capital_model="lump_sum", lump_sum_budget=0))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_dca_compare_reports_cycle_markers(client):
    with patch("app.services.backtest_service.fetch_ohlcv",
               new=AsyncMock(return_value=_btc_bars(600))):
        resp = await client.post("/api/v1/backtests/dca-compare", json=_body())
    assert resp.status_code == 200
    markers = resp.json()["cycle_markers"]
    assert all(m["kind"] in ("top", "bottom") for m in markers)
