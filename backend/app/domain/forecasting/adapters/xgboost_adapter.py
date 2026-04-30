from __future__ import annotations
import asyncio
import pickle
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

import numpy as np
import structlog

from app.core.enums import (
    Direction, ForecastingLibrary, MarketType, ModelStatus, Timeframe,
)
from app.core.types import ForecastResult, ModelFeatures, ModelMetrics
from app.domain.forecasting.base import (
    ForecastingModelAdapter, TrainingDataset, TrainingResult,
)

logger = structlog.get_logger(__name__)


class XGBoostForecastAdapter(ForecastingModelAdapter):
    """
    Gradient boosting forecasting model using XGBoost.

    Good for:
    - Tabular feature-based prediction (technical indicators, lags)
    - Fast inference (CPU-friendly)
    - Interpretable feature importance
    - Solid baseline before neural models

    Not good for: sequential/temporal dependencies — use LSTMAdapter for that.
    """

    def __init__(
        self,
        model_id: str,
        horizon_bars: int,
        timeframe: Timeframe,
        supported_markets: Optional[List[MarketType]] = None,
        n_estimators: int = 500,
        max_depth: int = 6,
        learning_rate: float = 0.05,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        random_state: int = 42,
        confidence_threshold: float = 0.55,
    ):
        super().__init__(
            model_id=model_id,
            library=ForecastingLibrary.XGBOOST,
            supported_markets=supported_markets or [MarketType.STOCK, MarketType.CRYPTO],
            supported_horizons=[horizon_bars],
            supported_timeframes=[timeframe],
        )
        self._horizon_bars = horizon_bars
        self._timeframe = timeframe
        self._confidence_threshold = confidence_threshold

        # XGBoost hyperparams — stored so they survive save/load
        self._hyperparams = {
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "learning_rate": learning_rate,
            "subsample": subsample,
            "colsample_bytree": colsample_bytree,
            "random_state": random_state,
            "objective": "reg:squarederror",
            "tree_method": "hist",      # fast CPU/GPU compatible
        }
        self._model = None              # XGBRegressor — loaded lazily

    # ── Abstract Implementation ────────────────────────────────────────────────

    async def predict(self, features: ModelFeatures) -> ForecastResult:
        self._guard_ready()

        feature_vector = self._features_to_array(features)

        # Run XGBoost inference in thread pool (CPU-bound — don't block event loop)
        predicted_return = await asyncio.get_event_loop().run_in_executor(
            None, self._model.predict, feature_vector
        )
        predicted_return = float(predicted_return[0])

        direction, confidence = self._return_to_signal(predicted_return)

        self._log.debug(
            "xgb.predict",
            symbol=features.symbol,
            predicted_return=round(predicted_return, 5),
            direction=direction.value,
            confidence=round(confidence, 3),
        )

        return ForecastResult(
            model_id=self.model_id,
            symbol=features.symbol,
            timestamp=features.timestamp,
            direction=direction,
            predicted_return=predicted_return,
            confidence=confidence,
            horizon_bars=self._horizon_bars,
            horizon_timeframe=self._timeframe,
            metadata={"feature_count": len(features.features)},
        )

    async def train(self, dataset: TrainingDataset) -> TrainingResult:
        import xgboost as xgb

        self._log.info("xgb.training.start", dataset_size=dataset.size)
        self.status = ModelStatus.TRAINING

        try:
            X, y = self._dataset_to_arrays(dataset)

            model = xgb.XGBRegressor(**self._hyperparams)

            # Train in thread pool — this can take minutes for large datasets
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: model.fit(
                    X, y,
                    eval_set=[(X[-len(X) // 10:], y[-len(y) // 10:])],  # last 10% as quick val
                    verbose=False,
                )
            )

            self._model = model
            self.status = ModelStatus.TRAINED

            metrics = await self.evaluate(dataset)

            self._log.info(
                "xgb.training.complete",
                mae=metrics.mae,
                directional_accuracy=metrics.directional_accuracy,
            )

            return TrainingResult(
                model_id=self.model_id,
                success=True,
                metrics=metrics,
                artifact_path=self._artifact_path,
            )

        except Exception as exc:
            self.status = ModelStatus.FAILED
            self._log.error("xgb.training.failed", error=str(exc))
            return TrainingResult(
                model_id=self.model_id,
                success=False,
                metrics=None,
                artifact_path=None,
                error=str(exc),
            )

    async def evaluate(self, dataset: TrainingDataset) -> ModelMetrics:
        self._guard_ready()

        X, y_true = self._dataset_to_arrays(dataset)

        y_pred = await asyncio.get_event_loop().run_in_executor(
            None, self._model.predict, X
        )

        mae = float(np.mean(np.abs(y_true - y_pred)))
        rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
        directional_accuracy = float(
            np.mean(np.sign(y_true) == np.sign(y_pred))
        )

        return ModelMetrics(
            model_id=self.model_id,
            dataset_id=dataset.dataset_id,
            mae=mae,
            rmse=rmse,
            directional_accuracy=directional_accuracy,
            evaluated_at=datetime.utcnow(),
        )

    async def load(self, artifact_path: str) -> None:
        path = Path(artifact_path)
        if not path.exists():
            raise FileNotFoundError(f"Model artifact not found: {artifact_path}")

        with open(path, "rb") as f:
            payload = pickle.load(f)

        self._model = payload["model"]
        self._hyperparams = payload["hyperparams"]
        self._artifact_path = artifact_path
        self.status = ModelStatus.TRAINED

        self._log.info("xgb.loaded", path=artifact_path)

    async def save(self, artifact_path: str) -> str:
        if self._model is None:
            raise RuntimeError("Cannot save — model has not been trained yet.")

        path = Path(artifact_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {"model": self._model, "hyperparams": self._hyperparams}
        with open(path, "wb") as f:
            pickle.dump(payload, f)

        self._artifact_path = artifact_path
        self._log.info("xgb.saved", path=artifact_path)
        return artifact_path

    # ── Private Helpers ────────────────────────────────────────────────────────

    def _features_to_array(self, features: ModelFeatures) -> np.ndarray:
        """Convert ModelFeatures dict to a 2D numpy array for XGBoost."""
        values = list(features.features.values())
        return np.array(values, dtype=np.float32).reshape(1, -1)

    def _dataset_to_arrays(self, dataset: TrainingDataset):
        X = np.array(
            [list(f.features.values()) for f in dataset.features],
            dtype=np.float32,
        )
        y = np.array(dataset.labels, dtype=np.float32)
        return X, y

    def _return_to_signal(self, predicted_return: float) -> tuple[Direction, float]:
        """
        Convert a scalar predicted return into a direction + confidence.
        Confidence is derived from the magnitude relative to a threshold.
        """
        abs_return = abs(predicted_return)
        confidence = min(abs_return / (self._confidence_threshold * 2), 1.0)

        if predicted_return > self._confidence_threshold / 100:
            return Direction.LONG, confidence
        elif predicted_return < -(self._confidence_threshold / 100):
            return Direction.SHORT, confidence
        else:
            return Direction.NEUTRAL, 1.0 - confidence
