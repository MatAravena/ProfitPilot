from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Type
import structlog

from app.core.enums import ForecastingLibrary, MarketType, Timeframe, ModelStatus
from app.core.types import ModelFeatures, ForecastResult, ModelMetrics

logger = structlog.get_logger(__name__)


class TrainingDataset:
    """Wraps training data — kept generic so any adapter can consume it."""
    def __init__(
        self,
        symbol: str,
        timeframe: Timeframe,
        features: List[ModelFeatures],
        labels: List[float],        # target returns
        dataset_id: str,
    ):
        self.symbol = symbol
        self.timeframe = timeframe
        self.features = features
        self.labels = labels
        self.dataset_id = dataset_id
        self.size = len(features)


class TrainingResult:
    def __init__(
        self,
        model_id: str,
        success: bool,
        metrics: Optional[ModelMetrics],
        artifact_path: Optional[str],
        error: Optional[str] = None,
    ):
        self.model_id = model_id
        self.success = success
        self.metrics = metrics
        self.artifact_path = artifact_path
        self.error = error


class ForecastingModelAdapter(ABC):
    """
    Abstract base for every ML forecasting model in ProfitPilot.

    Concrete implementations wrap a specific library (PyTorch, XGBoost, etc.)
    but expose a single, consistent interface to strategies.

    Rules:
    - Never call a forecasting library directly from a strategy.
    - One class per model type — XGBoostAdapter, LSTMAdapter, etc.
    - Register every implementation with ForecastingModelRegistry.
    """

    def __init__(
        self,
        model_id: str,
        library: ForecastingLibrary,
        supported_markets: List[MarketType],
        supported_horizons: List[int],
        supported_timeframes: List[Timeframe],
        supported_symbols: Optional[List[str]] = None,   # None = all symbols
    ):
        self.model_id = model_id
        self.library = library
        self.supported_markets = supported_markets
        self.supported_horizons = supported_horizons
        self.supported_timeframes = supported_timeframes
        self.supported_symbols = supported_symbols
        self.status = ModelStatus.UNTRAINED
        self._artifact_path: Optional[str] = None

        self._log = logger.bind(model_id=model_id, library=library.value)

    # ── Abstract Interface ─────────────────────────────────────────────────────

    @abstractmethod
    async def predict(self, features: ModelFeatures) -> ForecastResult:
        """
        Run inference on a prepared feature set.
        Must return a ForecastResult regardless of the underlying library.
        Raise ValueError if model is not ready.
        """
        ...

    @abstractmethod
    async def train(self, dataset: TrainingDataset) -> TrainingResult:
        """
        Train (or fine-tune) the model on the given dataset.
        This is called from a Celery worker — can be long-running.
        """
        ...

    @abstractmethod
    async def evaluate(self, dataset: TrainingDataset) -> ModelMetrics:
        """
        Evaluate the model on a held-out dataset.
        Returns standardized metrics regardless of library.
        """
        ...

    @abstractmethod
    async def load(self, artifact_path: str) -> None:
        """Load model weights/artifact from disk or object storage."""
        ...

    @abstractmethod
    async def save(self, artifact_path: str) -> str:
        """Persist model weights/artifact. Returns the path written."""
        ...

    # ── Concrete Helpers ───────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return self.status == ModelStatus.TRAINED

    def supports(self, market: MarketType, horizon: int, timeframe: Timeframe) -> bool:
        market_ok    = market in self.supported_markets
        horizon_ok   = horizon in self.supported_horizons
        timeframe_ok = timeframe in self.supported_timeframes
        return market_ok and horizon_ok and timeframe_ok

    def _guard_ready(self) -> None:
        if not self.is_ready:
            raise RuntimeError(
                f"Model '{self.model_id}' is not ready (status={self.status.value}). "
                "Train or load the model first."
            )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.model_id} lib={self.library.value} status={self.status.value}>"


# ── Registry ───────────────────────────────────────────────────────────────────

class ForecastingModelRegistry:
    """
    Central registry for all forecasting model adapters.
    Strategies look up models here — they never instantiate adapters directly.
    """

    _registry: Dict[str, ForecastingModelAdapter] = {}

    @classmethod
    def register(cls, adapter: ForecastingModelAdapter) -> None:
        if adapter.model_id in cls._registry:
            logger.warning("forecasting_model.overwrite", model_id=adapter.model_id)
        cls._registry[adapter.model_id] = adapter
        logger.info("forecasting_model.registered", model_id=adapter.model_id, library=adapter.library.value)

    @classmethod
    def get(cls, model_id: str) -> ForecastingModelAdapter:
        adapter = cls._registry.get(model_id)
        if adapter is None:
            raise KeyError(f"Forecasting model '{model_id}' not found in registry.")
        return adapter

    @classmethod
    def list_all(cls) -> List[ForecastingModelAdapter]:
        return list(cls._registry.values())

    @classmethod
    def list_ready(cls) -> List[ForecastingModelAdapter]:
        return [a for a in cls._registry.values() if a.is_ready]

    @classmethod
    def find_compatible(
        cls,
        market: MarketType,
        horizon: int,
        timeframe: Timeframe,
    ) -> List[ForecastingModelAdapter]:
        """Find all registered models that support the given requirements."""
        return [
            a for a in cls._registry.values()
            if a.is_ready and a.supports(market, horizon, timeframe)
        ]
