from __future__ import annotations
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Optional

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


class LSTMForecastAdapter(ForecastingModelAdapter):
    """
    Sequential LSTM model for time series forecasting using PyTorch.

    Good for:
    - Capturing sequential/temporal dependencies (trend, momentum memory)
    - Multi-step ahead forecasting
    - Patterns that XGBoost misses (order of events matters)

    Requires: features.sequence populated (list of feature dicts over a window)
    """

    def __init__(
        self,
        model_id: str,
        horizon_bars: int,
        timeframe: Timeframe,
        sequence_length: int = 60,          # lookback window
        hidden_size: int = 128,
        num_layers: int = 2,
        dropout: float = 0.2,
        learning_rate: float = 1e-3,
        max_epochs: int = 100,
        batch_size: int = 64,
        patience: int = 10,                 # early stopping
        supported_markets: Optional[List[MarketType]] = None,
        device: str = "auto",               # "cpu" | "cuda" | "auto"
    ):
        super().__init__(
            model_id=model_id,
            library=ForecastingLibrary.PYTORCH,
            supported_markets=supported_markets or [MarketType.STOCK, MarketType.CRYPTO],
            supported_horizons=[horizon_bars],
            supported_timeframes=[timeframe],
        )
        self._horizon_bars = horizon_bars
        self._timeframe = timeframe
        self._sequence_length = sequence_length
        self._hidden_size = hidden_size
        self._num_layers = num_layers
        self._dropout = dropout
        self._lr = learning_rate
        self._max_epochs = max_epochs
        self._batch_size = batch_size
        self._patience = patience
        self._device_arg = device

        self._model = None
        self._input_size: Optional[int] = None   # set on first train
        self._device = None

    # ── Abstract Implementation ────────────────────────────────────────────────

    async def predict(self, features: ModelFeatures) -> ForecastResult:
        self._guard_ready()

        if not features.sequence:
            raise ValueError(
                f"LSTMForecastAdapter '{self.model_id}' requires features.sequence "
                f"(a list of {self._sequence_length} feature dicts). Got None."
            )

        import torch

        tensor = self._sequence_to_tensor(features.sequence)

        with torch.no_grad():
            predicted_return = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._model(tensor).item()
            )

        direction, confidence = self._return_to_signal(predicted_return)

        self._log.debug(
            "lstm.predict",
            symbol=features.symbol,
            predicted_return=round(predicted_return, 5),
            direction=direction.value,
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
            metadata={"sequence_length": self._sequence_length, "device": str(self._device)},
        )

    async def train(self, dataset: TrainingDataset) -> TrainingResult:
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset

        self._log.info("lstm.training.start", dataset_size=dataset.size)
        self.status = ModelStatus.TRAINING

        try:
            self._device = self._resolve_device()
            self._input_size = len(dataset.features[0].features)

            self._model = _LSTMModel(
                input_size=self._input_size,
                hidden_size=self._hidden_size,
                num_layers=self._num_layers,
                dropout=self._dropout,
            ).to(self._device)

            X, y = self._dataset_to_tensors(dataset)
            loader = DataLoader(
                TensorDataset(X, y),
                batch_size=self._batch_size,
                shuffle=True,
            )

            optimizer = torch.optim.Adam(self._model.parameters(), lr=self._lr)
            criterion = nn.MSELoss()

            best_loss = float("inf")
            no_improve = 0

            def _train_loop():
                nonlocal best_loss, no_improve
                for epoch in range(self._max_epochs):
                    self._model.train()
                    epoch_loss = 0.0
                    for xb, yb in loader:
                        xb, yb = xb.to(self._device), yb.to(self._device)
                        optimizer.zero_grad()
                        pred = self._model(xb).squeeze()
                        loss = criterion(pred, yb)
                        loss.backward()
                        torch.nn.utils.clip_grad_norm_(self._model.parameters(), 1.0)
                        optimizer.step()
                        epoch_loss += loss.item()

                    avg_loss = epoch_loss / len(loader)

                    if avg_loss < best_loss:
                        best_loss = avg_loss
                        no_improve = 0
                    else:
                        no_improve += 1
                        if no_improve >= self._patience:
                            logger.info("lstm.early_stop", epoch=epoch, best_loss=best_loss)
                            break

            await asyncio.get_event_loop().run_in_executor(None, _train_loop)

            self._model.eval()
            self.status = ModelStatus.TRAINED
            metrics = await self.evaluate(dataset)

            self._log.info("lstm.training.complete", mae=metrics.mae, da=metrics.directional_accuracy)

            return TrainingResult(
                model_id=self.model_id,
                success=True,
                metrics=metrics,
                artifact_path=self._artifact_path,
            )

        except Exception as exc:
            self.status = ModelStatus.FAILED
            self._log.error("lstm.training.failed", error=str(exc))
            return TrainingResult(
                model_id=self.model_id, success=False, metrics=None, artifact_path=None, error=str(exc)
            )

    async def evaluate(self, dataset: TrainingDataset) -> ModelMetrics:
        import torch
        self._guard_ready()

        X, y_true_t = self._dataset_to_tensors(dataset)
        with torch.no_grad():
            y_pred_t = self._model(X.to(self._device)).squeeze().cpu()

        y_true = y_true_t.numpy()
        y_pred = y_pred_t.numpy()

        return ModelMetrics(
            model_id=self.model_id,
            dataset_id=dataset.dataset_id,
            mae=float(np.mean(np.abs(y_true - y_pred))),
            rmse=float(np.sqrt(np.mean((y_true - y_pred) ** 2))),
            directional_accuracy=float(np.mean(np.sign(y_true) == np.sign(y_pred))),
            evaluated_at=datetime.utcnow(),
        )

    async def load(self, artifact_path: str) -> None:
        import torch
        path = Path(artifact_path)
        if not path.exists():
            raise FileNotFoundError(f"Model artifact not found: {artifact_path}")

        self._device = self._resolve_device()
        checkpoint = torch.load(path, map_location=self._device)

        self._input_size = checkpoint["input_size"]
        self._hidden_size = checkpoint["hidden_size"]
        self._num_layers = checkpoint["num_layers"]

        self._model = _LSTMModel(
            input_size=self._input_size,
            hidden_size=self._hidden_size,
            num_layers=self._num_layers,
            dropout=self._dropout,
        ).to(self._device)
        self._model.load_state_dict(checkpoint["state_dict"])
        self._model.eval()

        self._artifact_path = artifact_path
        self.status = ModelStatus.TRAINED
        self._log.info("lstm.loaded", path=artifact_path, device=str(self._device))

    async def save(self, artifact_path: str) -> str:
        import torch
        if self._model is None:
            raise RuntimeError("Cannot save — model not trained.")

        path = Path(artifact_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        torch.save({
            "state_dict": self._model.state_dict(),
            "input_size": self._input_size,
            "hidden_size": self._hidden_size,
            "num_layers": self._num_layers,
        }, path)

        self._artifact_path = artifact_path
        self._log.info("lstm.saved", path=artifact_path)
        return artifact_path

    # ── Private Helpers ────────────────────────────────────────────────────────

    def _resolve_device(self):
        import torch
        if self._device_arg == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        return torch.device(self._device_arg)

    def _sequence_to_tensor(self, sequence: list) -> "torch.Tensor":
        import torch
        arr = np.array([list(s.values()) for s in sequence], dtype=np.float32)
        return torch.tensor(arr).unsqueeze(0)       # (1, seq_len, input_size)

    def _dataset_to_tensors(self, dataset: TrainingDataset):
        import torch
        sequences = [f.sequence for f in dataset.features]
        X = np.array(
            [[list(s.values()) for s in seq] for seq in sequences],
            dtype=np.float32,
        )
        y = np.array(dataset.labels, dtype=np.float32)
        return torch.tensor(X), torch.tensor(y)

    def _return_to_signal(self, predicted_return: float) -> tuple[Direction, float]:
        threshold = 0.003   # 0.3% minimum move to act
        abs_ret = abs(predicted_return)
        confidence = min(abs_ret / (threshold * 3), 1.0)
        if predicted_return > threshold:
            return Direction.LONG, confidence
        elif predicted_return < -threshold:
            return Direction.SHORT, confidence
        return Direction.NEUTRAL, 1.0 - confidence


# ── Internal PyTorch Module ─────────────────────────────────────────────────────

class _LSTMModel:
    """Private PyTorch LSTM — only used internally by LSTMForecastAdapter."""

    def __new__(cls, input_size: int, hidden_size: int, num_layers: int, dropout: float):
        import torch.nn as nn
        # Dynamically create as a proper nn.Module at import time
        class _Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.lstm = nn.LSTM(
                    input_size=input_size,
                    hidden_size=hidden_size,
                    num_layers=num_layers,
                    dropout=dropout if num_layers > 1 else 0.0,
                    batch_first=True,
                )
                self.head = nn.Linear(hidden_size, 1)

            def forward(self, x):
                out, _ = self.lstm(x)
                return self.head(out[:, -1, :])     # last timestep → scalar

        return _Net()
