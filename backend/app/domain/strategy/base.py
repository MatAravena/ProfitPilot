from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Optional, Type
from uuid import UUID

import structlog

from app.core.enums import MarketType, StrategyStatus, Timeframe
from app.core.types import Fill, MarketData, Order, RiskConfig, Signal, Tick
from app.domain.forecasting.base import ForecastingModelAdapter
from app.domain.broker.base import BrokerAdapter

logger = structlog.get_logger(__name__)


class StrategyBase(ABC):
    """
    Abstract base for every trading strategy in ProfitPilot.

    A strategy:
    1. Receives market data (OHLCV, ticks)
    2. Uses injected forecasting models + quant logic to generate signals
    3. Converts signals into orders
    4. Orders go through RiskManager BEFORE the broker — always

    Strategies NEVER:
    - Call broker adapters directly
    - Call forecasting libraries (PyTorch, XGBoost) directly
    - Bypass the RiskManager
    - Hardcode symbols or parameters

    All dependencies are injected — strategies are stateless logic units.
    """

    def __init__(
        self,
        strategy_id: UUID,
        name: str,
        version: str,
        market_type: MarketType,
        timeframe: Timeframe,
        parameters: Dict,
        risk_config: RiskConfig,
        # Injected dependencies
        forecasting_models: Optional[List[ForecastingModelAdapter]] = None,
        broker: Optional[BrokerAdapter] = None,
        llm_enrichment=None,            # Optional[LLMEnrichmentAdapter] — avoids circular import
    ):
        self.strategy_id = strategy_id
        self.name = name
        self.version = version
        self.market_type = market_type
        self.timeframe = timeframe
        self.parameters = parameters
        self.risk_config = risk_config

        # Injected — set after construction via DI container
        self.forecasting_models: List[ForecastingModelAdapter] = forecasting_models or []
        self.broker: Optional[BrokerAdapter] = broker
        self.llm_enrichment = llm_enrichment    # always Optional

        self.status: StrategyStatus = StrategyStatus.DRAFT
        self.created_at: datetime = datetime.now(timezone.utc)
        self.last_signal_at: Optional[datetime] = None
        self.error_count: int = 0

        self._log = logger.bind(strategy=name, strategy_id=str(strategy_id))

    # ── Abstract Interface ─────────────────────────────────────────────────────

    @abstractmethod
    async def generate_signals(self, data: MarketData) -> List[Signal]:
        """
        Core strategy logic. Given market data, return a list of Signals.
        Call self.forecasting_models[n].predict() for ML signals.
        Apply your own quant logic here.
        Do NOT place orders here — return signals only.
        """
        ...

    @abstractmethod
    async def on_tick(self, tick: Tick) -> Optional[Signal]:
        """
        Called on every live tick. Return a Signal if the tick triggers one.
        Return None if no action needed.
        Designed for high-frequency intrabar decisions.
        """
        ...

    @abstractmethod
    async def on_fill(self, fill: Fill) -> None:
        """
        Called when one of this strategy's orders is filled.
        Use to update internal state, trigger follow-on orders (e.g. stop loss placement).
        """
        ...

    @abstractmethod
    def get_required_symbols(self) -> List[str]:
        """Return the list of symbols this strategy needs data for."""
        ...

    @abstractmethod
    def validate_parameters(self) -> None:
        """
        Validate self.parameters against the strategy's requirements.
        Raise ValueError with a clear message if anything is invalid.
        Called at instantiation and before activation.
        """
        ...

    # ── Concrete Helpers ───────────────────────────────────────────────────────

    def get_model(self, model_id: str) -> Optional[ForecastingModelAdapter]:
        """Look up an injected forecasting model by ID."""
        return next((m for m in self.forecasting_models if m.model_id == model_id), None)

    def get_param(self, key: str, default=None):
        """Safe parameter access with optional default."""
        return self.parameters.get(key, default)

    def is_active(self) -> bool:
        return self.status in (StrategyStatus.PAPER, StrategyStatus.LIVE)

    def set_status(self, status: StrategyStatus) -> None:
        old = self.status
        self.status = status
        self._log.info("strategy.status_change", old=old.value, new=status.value)

    def halt(self, reason: str) -> None:
        """Emergency halt — triggered by RiskManager or kill switch."""
        self.set_status(StrategyStatus.HALTED)
        self._log.warning("strategy.halted", reason=reason)

    def record_error(self, error: Exception) -> None:
        self.error_count += 1
        self._log.error("strategy.error", count=self.error_count, error=str(error))
        if self.error_count >= 5:
            self.halt(reason=f"Too many consecutive errors ({self.error_count})")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} v={self.version} status={self.status.value}>"


# ── Registry ────────────────────────────────────────────────────────────────────

class StrategyRegistry:
    """
    Registry for strategy *classes* (not instances).
    Strategy instances are created by StrategyFactory with injected dependencies.
    """

    _classes: Dict[str, Type[StrategyBase]] = {}

    @classmethod
    def register(cls, strategy_class: Type[StrategyBase]) -> Type[StrategyBase]:
        """Decorator — @StrategyRegistry.register"""
        name = strategy_class.__name__
        cls._classes[name] = strategy_class
        logger.info("strategy.class_registered", name=name)
        return strategy_class

    @classmethod
    def get(cls, class_name: str) -> Type[StrategyBase]:
        klass = cls._classes.get(class_name)
        if klass is None:
            raise KeyError(f"Strategy class '{class_name}' not registered.")
        return klass

    @classmethod
    def list_all(cls) -> List[str]:
        return list(cls._classes.keys())
