"""Unit tests for SmaCrossover strategy signal generation."""
from __future__ import annotations

import pytest

from app.core.enums import Direction, Timeframe
from app.core.types import MarketData
from tests.conftest import make_bars


# Ensure the strategy class is registered
import app.domain.strategy.examples.sma_crossover  # noqa: F401
from app.domain.strategy.examples.sma_crossover import SmaCrossover


def _strategy(fast: int = 5, slow: int = 10) -> SmaCrossover:
    return SmaCrossover(parameters={"symbol": "BTCUSDT", "fast_period": fast, "slow_period": slow})


def _market(closes: list[float]) -> MarketData:
    return MarketData(symbol="BTCUSDT", timeframe=Timeframe.D1, bars=make_bars(closes))


class TestSmaCrossover:
    @pytest.mark.asyncio
    async def test_insufficient_bars_returns_empty(self):
        strat = _strategy(fast=5, slow=10)
        signals = await strat.generate_signals(_market([100.0] * 5))
        assert signals == []

    @pytest.mark.asyncio
    async def test_golden_cross_emits_long(self):
        """Fast SMA crosses above slow SMA → LONG signal."""
        strat = _strategy(fast=3, slow=5)
        # Flat then a big spike on the last bar forces fast above slow
        closes = [100, 100, 100, 100, 100, 100, 100, 300]
        signals = await strat.generate_signals(_market(closes))
        directions = [s.direction for s in signals]
        assert Direction.LONG in directions

    @pytest.mark.asyncio
    async def test_death_cross_emits_close(self):
        """Fast SMA crosses below slow SMA → CLOSE signal."""
        strat = _strategy(fast=3, slow=5)
        # Steady uptrend (fast > slow) then a crash on the last bar pulls fast below slow
        closes = [50, 100, 150, 200, 250, 300, 350, 10]
        signals = await strat.generate_signals(_market(closes))
        directions = [s.direction for s in signals]
        assert Direction.CLOSE in directions

    @pytest.mark.asyncio
    async def test_flat_market_no_cross(self):
        """Perfectly flat close prices produce no cross signals."""
        strat = _strategy(fast=3, slow=5)
        closes = [100.0] * 20
        signals = await strat.generate_signals(_market(closes))
        assert signals == []

    def test_invalid_params_raises(self):
        with pytest.raises(ValueError, match="slow_period"):
            _strategy(fast=10, slow=5)  # slow must be > fast

    @pytest.mark.asyncio
    async def test_confidence_in_range(self):
        """All emitted signals must have confidence in [0, 1]."""
        strat = _strategy(fast=3, slow=5)
        closes = [100, 100, 100, 100, 100, 100, 100, 300]
        signals = await strat.generate_signals(_market(closes))
        assert signals, "expected at least one signal"
        for s in signals:
            assert 0.0 <= s.confidence <= 1.0
