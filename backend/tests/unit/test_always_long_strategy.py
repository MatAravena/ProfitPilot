from __future__ import annotations

import pytest

from app.core.enums import Direction, SignalSource, Timeframe
from app.core.types import MarketData
from app.domain.strategy.base import StrategyRegistry
from app.domain.strategy.loader import load_user_strategies
from tests.conftest import make_bars

pytestmark = pytest.mark.asyncio


def test_always_long_is_registered():
    load_user_strategies()
    assert "AlwaysLong" in StrategyRegistry.list_all()


async def test_always_long_emits_long_signal():
    load_user_strategies()
    cls = StrategyRegistry.get("AlwaysLong")
    strat = cls(parameters={"symbol": "BTCUSDT"}, timeframe=Timeframe.M1)

    data = MarketData(
        symbol="BTCUSDT", timeframe=Timeframe.M1,
        bars=make_bars([100.0, 101.0, 102.0], symbol="BTCUSDT", timeframe=Timeframe.M1),
    )
    signals = await strat.generate_signals(data)

    assert len(signals) == 1
    assert signals[0].direction == Direction.LONG
    assert signals[0].source == SignalSource.MANUAL


async def test_always_long_no_signal_without_bars():
    load_user_strategies()
    cls = StrategyRegistry.get("AlwaysLong")
    strat = cls(parameters={"symbol": "BTCUSDT"}, timeframe=Timeframe.M1)
    data = MarketData(symbol="BTCUSDT", timeframe=Timeframe.M1, bars=[])
    assert await strat.generate_signals(data) == []
