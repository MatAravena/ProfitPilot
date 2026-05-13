"""Unit tests for RsiMeanReversion strategy signal generation."""
from __future__ import annotations

import pytest

from app.core.enums import Direction, Timeframe
from app.core.types import MarketData
from tests.conftest import make_bars

import app.domain.strategy.examples.sma_crossover  # noqa: F401 — registers both strategies
from app.domain.strategy.examples.sma_crossover import RsiMeanReversion


def _strategy(**kwargs) -> RsiMeanReversion:
    params = {"symbol": "BTCUSDT", "rsi_period": 5, "oversold": 30, "overbought": 70, **kwargs}
    return RsiMeanReversion(parameters=params)


def _market(closes: list[float]) -> MarketData:
    return MarketData(symbol="BTCUSDT", timeframe=Timeframe.D1, bars=make_bars(closes))


class TestRsiMeanReversion:
    @pytest.mark.asyncio
    async def test_insufficient_bars_returns_empty(self):
        strat = _strategy()
        signals = await strat.generate_signals(_market([100.0] * 3))
        assert signals == []

    @pytest.mark.asyncio
    async def test_oversold_dip_emits_long(self):
        """RSI transitions from just-above oversold to below it → LONG signal."""
        strat = _strategy(rsi_period=5, oversold=30)
        # Mostly sideways (RSI ~33) then a sharp drop on the last bar drives RSI <30
        closes = [100, 102, 98, 101, 99, 100, 98, 50]
        signals = await strat.generate_signals(_market(closes))
        directions = [s.direction for s in signals]
        assert Direction.LONG in directions

    @pytest.mark.asyncio
    async def test_overbought_rally_emits_close(self):
        """RSI transitions from just-below overbought to above it → CLOSE signal."""
        strat = _strategy(rsi_period=5, overbought=70)
        # Mostly sideways (RSI ~67) then a sharp spike on the last bar drives RSI >70
        closes = [100, 98, 102, 99, 101, 100, 102, 150]
        signals = await strat.generate_signals(_market(closes))
        directions = [s.direction for s in signals]
        assert Direction.CLOSE in directions

    @pytest.mark.asyncio
    async def test_sideways_no_signal(self):
        """Alternating small up/down → RSI stays mid-range → no signal."""
        strat = _strategy(rsi_period=5, oversold=20, overbought=80)
        closes = [100, 101, 99, 101, 100, 101, 99, 101, 100]
        signals = await strat.generate_signals(_market(closes))
        assert signals == []

    def test_invalid_params_oversold_gte_overbought(self):
        with pytest.raises(ValueError):
            _strategy(oversold=70, overbought=30)

    def test_invalid_period(self):
        with pytest.raises(ValueError):
            _strategy(rsi_period=1)
