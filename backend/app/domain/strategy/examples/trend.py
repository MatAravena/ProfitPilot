"""Trend-family built-ins: Donchian breakout, SMA trend filter, RSI pullback in an uptrend.

All long-only. They emit the signal for the state they want every bar the condition
holds (LONG while "in", CLOSE while "out"); the execution layer turns a repeated intent
into a no-op. State, not crossover events, so a restart or a missed bar can't leave the
strategy out of a trend it should be in.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from app.core.enums import Direction, MarketType, SignalSource, Timeframe
from app.core.types import Fill, MarketData, RiskConfig, Signal, Tick
from app.domain.strategy.base import StrategyBase, StrategyRegistry
from app.domain.strategy.examples.sma_crossover import _rsi, _sma


class _LongOnlyStrategy(StrategyBase):
    """Shared plumbing for the long-only built-ins in this module."""

    NAME = ""
    CONFIDENCE = 0.65

    def __init__(self, parameters: dict, **kwargs):
        super().__init__(
            strategy_id=kwargs.get("strategy_id", uuid4()),
            name=self.NAME,
            version="1.0.0",
            market_type=MarketType.CRYPTO,
            timeframe=kwargs.get("timeframe", Timeframe.D1),
            parameters=parameters,
            risk_config=kwargs.get("risk_config", RiskConfig()),
            forecasting_models=kwargs.get("forecasting_models"),
            broker=kwargs.get("broker"),
        )
        self.validate_parameters()

    def get_required_symbols(self) -> List[str]:
        return [self.get_param("symbol", "BTCUSDT")]

    async def on_tick(self, tick: Tick) -> Optional[Signal]:
        return None

    async def on_fill(self, fill: Fill) -> None:
        self.last_signal_at = datetime.now(timezone.utc)

    def _signal(self, data: MarketData, direction: Direction) -> List[Signal]:
        self.last_signal_at = datetime.now(timezone.utc)
        return [Signal(
            signal_id=uuid4(), strategy_id=self.strategy_id, symbol=data.symbol,
            market_type=self.market_type, timeframe=self.timeframe, direction=direction,
            confidence=self.CONFIDENCE, source=SignalSource.QUANT,
            generated_at=datetime.now(timezone.utc),
        )]

    def _int_param(self, key: str, default: int, minimum: int) -> int:
        value = self.get_param(key, default)
        if not isinstance(value, int) or value < minimum:
            raise ValueError(f"{key} must be an integer >= {minimum}")
        return value


@StrategyRegistry.register
class DonchianBreakout(_LongOnlyStrategy):
    """Long on a close above the prior `entry_bars` high; flat on a close below the prior
    `exit_bars` low. Levels exclude the current bar."""

    NAME = "DonchianBreakout"

    def validate_parameters(self) -> None:
        self._int_param("entry_bars", 55, 2)
        self._int_param("exit_bars", 20, 2)

    async def generate_signals(self, data: MarketData) -> List[Signal]:
        entry = self.get_param("entry_bars", 55)
        exit_ = self.get_param("exit_bars", 20)
        bars = data.bars
        if len(bars) < max(entry, exit_) + 1:
            return []
        close = bars[-1].close
        if close > max(b.high for b in bars[-entry - 1:-1]):
            return self._signal(data, Direction.LONG)
        if close < min(b.low for b in bars[-exit_ - 1:-1]):
            return self._signal(data, Direction.CLOSE)
        return []


@StrategyRegistry.register
class TrendFilter(_LongOnlyStrategy):
    """Long while the close is above its `period` SMA, flat while below."""

    NAME = "TrendFilter"

    def validate_parameters(self) -> None:
        self._int_param("period", 200, 2)

    async def generate_signals(self, data: MarketData) -> List[Signal]:
        period = self.get_param("period", 200)
        closes = [b.close for b in data.bars]
        if len(closes) < period + 1:
            return []
        above = closes[-1] > _sma(closes, period)
        return self._signal(data, Direction.LONG if above else Direction.CLOSE)


@StrategyRegistry.register
class RsiPullbackInTrend(_LongOnlyStrategy):
    """Buy when RSI(`rsi_period`) < `entry_rsi` while the close is above its `trend_period`
    SMA; exit when the close rises above its `exit_period` SMA."""

    NAME = "RsiPullbackInTrend"

    def validate_parameters(self) -> None:
        self._int_param("rsi_period", 2, 2)
        self._int_param("trend_period", 200, 2)
        self._int_param("exit_period", 5, 2)
        entry_rsi = self.get_param("entry_rsi", 10)
        if not isinstance(entry_rsi, (int, float)) or not 0 < entry_rsi < 100:
            raise ValueError("entry_rsi must be between 0 and 100")

    async def generate_signals(self, data: MarketData) -> List[Signal]:
        rsi_p = self.get_param("rsi_period", 2)
        trend_p = self.get_param("trend_period", 200)
        exit_p = self.get_param("exit_period", 5)
        entry_rsi = self.get_param("entry_rsi", 10)
        closes = [b.close for b in data.bars]
        if len(closes) < max(trend_p, exit_p, rsi_p + 1) + 1:
            return []
        close = closes[-1]
        if close > _sma(closes, trend_p) and _rsi(closes, rsi_p) < entry_rsi:
            return self._signal(data, Direction.LONG)
        if close > _sma(closes, exit_p):
            return self._signal(data, Direction.CLOSE)
        return []
