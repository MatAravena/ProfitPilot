"""Integration tests for the DCA-vs-cycle-grid comparison endpoint."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.types import OHLCV
from tests.conftest import make_bars


def _btc_bars(n: int = 400) -> list[OHLCV]:
    # A cyclical-ish series is enough; the endpoint just needs >= MIN_BACKTEST_BARS bars.
    closes = [20_000 + 8_000 * math.sin(i / 60) + i * 20 for i in range(n)]
    return make_bars(closes)


def _blowoff_to_top_bars() -> list[OHLCV]:
    """Blow-off rise into the predicted 2025-10-07 cycle top (~248 days after base) then a crash —
    so the rotation arms actually DISTRIBUTE and their params change the outcome."""
    base = datetime(2025, 2, 1, tzinfo=timezone.utc)   # base + 248d == 2025-10-07 (predicted top)
    closes = [20_000 + 100_000 * (j / 247) ** 3 for j in range(248)]      # blow-off into the top
    closes += [120_000 + (48_000 - 120_000) * (j / 79) for j in range(80)]  # sharp crash after it
    return make_bars(closes, base_ts=base)


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
async def test_dca_compare_returns_all_arms(client):
    with patch("app.services.backtest_service.fetch_ohlcv",
               new=AsyncMock(return_value=_btc_bars(400))):
        resp = await client.post("/api/v1/backtests/dca-compare", json=_body())
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["arms"]) == {
        "flat_dca", "smart_accumulate", "full_rotation", "cycle_hunter", "accumulator_grid",
        "cycle_rotation_v2", "cycle_rotation_auto",
    }
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
    assert contribs["flat_dca"] == pytest.approx(contribs["cycle_hunter"])
    assert contribs["flat_dca"] == pytest.approx(contribs["accumulator_grid"])
    assert contribs["flat_dca"] == pytest.approx(contribs["cycle_rotation_v2"])
    assert contribs["flat_dca"] == pytest.approx(contribs["cycle_rotation_auto"])


@pytest.mark.asyncio
async def test_dca_compare_lump_sum_requires_budget(client):
    with patch("app.services.backtest_service.fetch_ohlcv",
               new=AsyncMock(return_value=_btc_bars(400))):
        resp = await client.post("/api/v1/backtests/dca-compare",
                                 json=_body(capital_model="lump_sum", lump_sum_budget=0))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_dca_compare_rotation_params_flow_through(client):
    # A tunable rotation param must change the result -> proves the body params reach the policy.
    with patch("app.services.backtest_service.fetch_ohlcv",
               new=AsyncMock(return_value=_blowoff_to_top_bars())):
        default = await client.post("/api/v1/backtests/dca-compare",
                                    json=_body(rotation={"sell_fraction_at_ath": 0.2}))
        tuned = await client.post("/api/v1/backtests/dca-compare",
                                  json=_body(rotation={"sell_fraction_at_ath": 1.0}))
    a = default.json()["arms"]["cycle_rotation_v2"]["final_value"]
    b = tuned.json()["arms"]["cycle_rotation_v2"]["final_value"]
    assert a != b


@pytest.mark.asyncio
async def test_dca_compare_persists_and_reuses_ohlcv(client):
    # 1st call seeds the cache (no start bound); 2nd call reads from the DB and only fetches the tail.
    mock = AsyncMock(return_value=_btc_bars(400))
    with patch("app.services.backtest_service.fetch_ohlcv", new=mock):
        await client.post("/api/v1/backtests/dca-compare", json=_body())
        await client.post("/api/v1/backtests/dca-compare", json=_body())
    assert mock.call_count == 2
    assert mock.call_args_list[0].kwargs.get("start") is None       # seed: full fetch
    assert mock.call_args_list[1].kwargs.get("start") is not None   # reuse: incremental tail only


@pytest.mark.asyncio
async def test_dca_compare_reports_cycle_markers(client):
    with patch("app.services.backtest_service.fetch_ohlcv",
               new=AsyncMock(return_value=_btc_bars(600))):
        resp = await client.post("/api/v1/backtests/dca-compare", json=_body())
    assert resp.status_code == 200
    markers = resp.json()["cycle_markers"]
    assert all(m["kind"] in ("top", "bottom") for m in markers)
