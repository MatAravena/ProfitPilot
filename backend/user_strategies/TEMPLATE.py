"""
MyStrategy — replace this with your strategy description.

HOW TO USE
----------
1. Copy this file to a new name, e.g. my_strategy.py (no leading underscore).
2. Rename the class and fill in your logic in generate_signals().
3. Restart the backend — the strategy is auto-discovered and appears in the UI.

OPTIONAL: define STRATEGY_META (below) to get a nice form with parameter fields.
If you skip it, the UI will show the class name with no parameter inputs.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from app.core.enums import Direction, MarketType, SignalSource, Timeframe
from app.core.types import Fill, MarketData, RiskConfig, Signal, Tick
from app.domain.strategy.base import StrategyBase, StrategyRegistry


# ── Optional UI metadata ──────────────────────────────────────────────────────
STRATEGY_META = {
    "display_name": "My Strategy",
    "description": "Short description shown in the UI",
    "parameters": [
        # Add your parameters here. Supported types: "int", "float"
        {"key": "my_param", "type": "int", "default": 14, "label": "My Param"},
    ],
}


# ── Strategy class ────────────────────────────────────────────────────────────
@StrategyRegistry.register
class MyStrategy(StrategyBase):
    """One-line description for code readers."""

    def __init__(self, parameters: dict, **kwargs):
        super().__init__(
            strategy_id=kwargs.get("strategy_id", uuid4()),
            name="MyStrategy",
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
        # Raise ValueError with a clear message if any parameter is invalid.
        pass

    def get_required_symbols(self) -> List[str]:
        return [self.get_param("symbol", "BTCUSDT")]

    async def generate_signals(self, data: MarketData) -> List[Signal]:
        """
        Core logic. Return [] for no signal, or a list of Signal objects.
        data.bars is a list of OHLCV bars up to and including the current bar.
        """
        closes = [b.close for b in data.bars]

        # Example: always return no signal
        # Replace this with your actual logic.
        return []

    async def on_tick(self, tick: Tick) -> Optional[Signal]:
        # Bar-based strategies can just return None here.
        return None

    async def on_fill(self, fill: Fill) -> None:
        self.last_signal_at = datetime.utcnow()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _make_signal(self, data: MarketData, direction: Direction) -> Signal:
        self.last_signal_at = datetime.utcnow()
        return Signal(
            signal_id=uuid4(),
            strategy_id=self.strategy_id,
            symbol=data.symbol,
            market_type=self.market_type,
            timeframe=self.timeframe,
            direction=direction,
            confidence=0.65,
            source=SignalSource.QUANT,
            generated_at=datetime.utcnow(),
        )
