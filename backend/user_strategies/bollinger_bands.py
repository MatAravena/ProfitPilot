"""
Bollinger Bands mean-reversion strategy.

Signals:
  LONG  — price closes below the lower band (oversold squeeze)
  CLOSE — price closes above the upper band (overbought / take profit)
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from app.core.enums import Direction, MarketType, SignalSource, Timeframe
from app.core.types import Fill, MarketData, RiskConfig, Signal, Tick
from app.domain.strategy.base import StrategyBase, StrategyRegistry


# Optional: define STRATEGY_META so the UI shows a clean form with defaults.
# If omitted, the UI will show the class name and no parameter fields.
STRATEGY_META = {
    "display_name": "Bollinger Bands",
    "description": "Mean-reversion: buy below lower band, close above upper band",
    "parameters": [
        {"key": "period",  "type": "int",   "default": 20,  "label": "Period"},
        {"key": "std_dev", "type": "float", "default": 2.0, "label": "Std Dev Multiplier"},
    ],
}


@StrategyRegistry.register
class BollingerBands(StrategyBase):
    """Bollinger Bands mean-reversion strategy."""

    def __init__(self, parameters: dict, **kwargs):
        super().__init__(
            strategy_id=kwargs.get("strategy_id", uuid4()),
            name="BollingerBands",
            version="1.0.0",
            market_type=MarketType.CRYPTO,
            timeframe=kwargs.get("timeframe", Timeframe.H4),
            parameters=parameters,
            risk_config=kwargs.get("risk_config", RiskConfig()),
            forecasting_models=kwargs.get("forecasting_models"),
            broker=kwargs.get("broker"),
        )
        self.validate_parameters()

    def validate_parameters(self) -> None:
        period = self.get_param("period", 20)
        std_dev = self.get_param("std_dev", 2.0)
        if not isinstance(period, int) or period < 5:
            raise ValueError("period must be an integer >= 5")
        if std_dev <= 0:
            raise ValueError("std_dev must be > 0")

    def get_required_symbols(self) -> List[str]:
        return [self.get_param("symbol", "BTCUSDT")]

    async def generate_signals(self, data: MarketData) -> List[Signal]:
        period = self.get_param("period", 20)
        k = self.get_param("std_dev", 2.0)

        if len(data.bars) < period + 1:
            return []

        closes = [b.close for b in data.bars]
        upper, lower = _bands(closes, period, k)
        prev_upper, prev_lower = _bands(closes[:-1], period, k)

        price = closes[-1]
        prev_price = closes[-2]

        signals: List[Signal] = []

        if prev_price >= prev_lower and price < lower:
            signals.append(self._make_signal(data, Direction.LONG))
        elif prev_price <= prev_upper and price > upper:
            signals.append(self._make_signal(data, Direction.CLOSE))

        return signals

    async def on_tick(self, tick: Tick) -> Optional[Signal]:
        return None

    async def on_fill(self, fill: Fill) -> None:
        self.last_signal_at = datetime.utcnow()

    def _make_signal(self, data: MarketData, direction: Direction) -> Signal:
        self.last_signal_at = datetime.utcnow()
        return Signal(
            signal_id=uuid4(),
            strategy_id=self.strategy_id,
            symbol=data.symbol,
            market_type=self.market_type,
            timeframe=self.timeframe,
            direction=direction,
            confidence=0.6,
            source=SignalSource.QUANT,
            generated_at=datetime.utcnow(),
        )


def _bands(closes: List[float], period: int, k: float) -> tuple[float, float]:
    window = closes[-period:]
    mean = sum(window) / period
    variance = sum((x - mean) ** 2 for x in window) / period
    std = math.sqrt(variance)
    return mean + k * std, mean - k * std
