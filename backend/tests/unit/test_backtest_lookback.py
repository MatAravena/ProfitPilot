"""The strategy sees a bounded history window — the same one in backtest and live.

Windowing is what keeps a backtest linear in bar count (it was quadratic: every bar
re-sent the whole history). Results must not change for strategies that only look back
a bounded number of bars, and live must fetch exactly the same window.
"""
from __future__ import annotations

import math

import pytest

from app.core.constants import STRATEGY_LOOKBACK_BARS
from app.core.enums import Timeframe
from app.domain.backtest.engine import BacktestEngine
from app.domain.strategy.examples.sma_crossover import MacdCrossover, SmaCrossover
from tests.conftest import make_bars

pytestmark = pytest.mark.asyncio


def _wavy(n=1200):
    return make_bars([100 + 20 * math.sin(i / 15) + 5 * math.sin(i / 4) for i in range(n)])


def _trades(result):
    return [(t.entry_time, t.exit_time, t.side, t.pnl) for t in result.trades]


@pytest.mark.parametrize("cls,params", [
    (SmaCrossover, {"fast_period": 5, "slow_period": 50}),
    (MacdCrossover, {"fast_period": 12, "slow_period": 26, "signal_period": 9}),
])
async def test_windowed_run_matches_full_history(cls, params):
    bars = _wavy()
    full = await BacktestEngine(cls(parameters=params, timeframe=Timeframe.D1), bars).run()
    windowed = await BacktestEngine(cls(parameters=params, timeframe=Timeframe.D1), bars,
                                    lookback_bars=STRATEGY_LOOKBACK_BARS).run()
    assert full.trades, "fixture must actually trade"
    assert _trades(windowed) == _trades(full)


async def test_strategy_never_sees_more_than_the_window():
    seen = []

    class _Recorder(SmaCrossover):
        async def generate_signals(self, data):
            seen.append(len(data.bars))
            return []

    await BacktestEngine(_Recorder(parameters={}, timeframe=Timeframe.D1), _wavy(300),
                         lookback_bars=100).run()
    assert max(seen) == 100 and min(seen) == 51   # warm-up 50 → first decision sees 51 bars


async def test_invalid_window_is_rejected():
    with pytest.raises(ValueError):
        BacktestEngine(SmaCrossover(parameters={}), _wavy(100), lookback_bars=1)


async def test_live_executor_fetches_the_same_window(monkeypatch):
    from app.api.deps import LOCAL_USER_ID
    from app.core.types import RiskConfig
    from app.services.strategy_executor import StrategyExecutor
    import uuid

    asked = {}

    async def fake_fetch(symbol, timeframe, limit=None):
        asked["limit"] = limit
        return []

    monkeypatch.setattr("app.domain.backtest.data_provider.fetch_ohlcv", fake_fetch)
    await StrategyExecutor(notify=lambda t: None)._execute_once(
        uuid.uuid4(), "SmaCrossover", "BTCUSDT", Timeframe.D1, {}, LOCAL_USER_ID,
        "paper", None, RiskConfig(), True, None,
    )
    assert asked["limit"] == STRATEGY_LOOKBACK_BARS


async def test_backtest_service_uses_the_live_window(monkeypatch):
    from app.models.schemas.backtest_schemas import BacktestRequest
    from app.services import backtest_service

    captured = {}

    class _SpyEngine:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def run(self):
            return "ok"

    async def fake_bars(self, req, timeframe):
        return _wavy(100)

    monkeypatch.setattr(backtest_service, "BacktestEngine", _SpyEngine)
    monkeypatch.setattr(backtest_service.BacktestService, "_get_bars", fake_bars)

    await backtest_service.BacktestService().run(BacktestRequest(
        strategy_name="SmaCrossover", symbol="BTCUSDT", timeframe="1d",
    ))
    assert captured["lookback_bars"] == STRATEGY_LOOKBACK_BARS
