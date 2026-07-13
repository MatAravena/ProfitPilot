"""AlwaysLong — deterministic test strategy that always signals LONG.

Purpose: smoke-testing the live execution path (e.g. Bybit testnet). It enters a
long position on the first bar and then holds — order-level idempotency turns the
repeated LONG into a no-op, so exactly one entry order is placed. Not a real trading
strategy; for verification only. See docs/runbooks/testnet-smoke-test.md.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from app.core.enums import Direction, MarketType, SignalSource, Timeframe
from app.core.types import Fill, MarketData, RiskConfig, Signal, Tick
from app.domain.strategy.base import StrategyBase, StrategyRegistry


STRATEGY_META = {
    "display_name": "Always Long (test)",
    "description": "Deterministic test strategy — always signals LONG. For smoke-testing execution.",
    "parameters": [],
}


@StrategyRegistry.register
class AlwaysLong(StrategyBase):
    """Always emits a LONG signal — deterministic execution smoke test."""

    def __init__(self, parameters: dict, **kwargs):
        super().__init__(
            strategy_id=kwargs.get("strategy_id", uuid4()),
            name="AlwaysLong",
            version="1.0.0",
            market_type=MarketType.CRYPTO,
            timeframe=kwargs.get("timeframe", Timeframe.M1),
            parameters=parameters,
            risk_config=kwargs.get("risk_config", RiskConfig()),
            forecasting_models=kwargs.get("forecasting_models"),
            broker=kwargs.get("broker"),
        )
        self.validate_parameters()

    def validate_parameters(self) -> None:
        return None

    def get_required_symbols(self) -> List[str]:
        return [self.get_param("symbol", "BTCUSDT")]

    async def generate_signals(self, data: MarketData) -> List[Signal]:
        if not data.bars:
            return []
        return [self._make_signal(data, Direction.LONG)]

    async def on_tick(self, tick: Tick) -> Optional[Signal]:
        return None

    async def on_fill(self, fill: Fill) -> None:
        self.last_signal_at = datetime.now(timezone.utc)

    def _make_signal(self, data: MarketData, direction: Direction) -> Signal:
        self.last_signal_at = datetime.now(timezone.utc)
        return Signal(
            signal_id=uuid4(),
            strategy_id=self.strategy_id,
            symbol=data.symbol,
            market_type=self.market_type,
            timeframe=self.timeframe,
            direction=direction,
            confidence=1.0,
            source=SignalSource.MANUAL,
            generated_at=datetime.now(timezone.utc),
        )
