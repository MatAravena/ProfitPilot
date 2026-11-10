from __future__ import annotations

import math
from unittest.mock import AsyncMock

import pytest

from app.core.enums import Timeframe
from app.models.schemas.grid_schemas import GridRequest
from app.services.backtest_service import BacktestService
from app.services.grid_service import GridService
from tests.conftest import make_bars


def _oscillating_bars(n: int = 300):
    closes = [30_000 + 3_000 * math.sin(i / 12) for i in range(n)]
    return make_bars(closes, timeframe=Timeframe.H1)


@pytest.mark.asyncio
async def test_grid_service_runs_both_arms():
    backtests = BacktestService()
    backtests._get_bars = AsyncMock(return_value=_oscillating_bars())  # noqa: SLF001 test stub
    service = GridService(backtests)

    bundle = await service.run(GridRequest(symbol="BTCUSDT", timeframe="1h"))

    assert set(bundle.arms) == {"grid_guarded_reanchor", "grid_accumulate_nostop"}
    for arm in bundle.arms.values():
        assert len(arm.equity_curve) == 300


@pytest.mark.asyncio
async def test_grid_service_rejects_unknown_timeframe():
    service = GridService(BacktestService())
    with pytest.raises(ValueError, match="Unknown timeframe"):
        await service.run(GridRequest(symbol="BTCUSDT", timeframe="3h"))


@pytest.mark.asyncio
async def test_grid_service_rejects_too_little_data():
    backtests = BacktestService()
    backtests._get_bars = AsyncMock(return_value=_oscillating_bars(10))  # noqa: SLF001 test stub
    service = GridService(backtests)
    with pytest.raises(ValueError, match="Not enough data"):
        await service.run(GridRequest(symbol="BTCUSDT", timeframe="1h"))
