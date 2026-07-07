from __future__ import annotations

import structlog
from fastapi import APIRouter

from app.core.errors import AppError, BacktestError, ErrorCode
from app.domain.backtest.engine import BacktestResult
from app.models.schemas.backtest_schemas import (
    AvailableStrategiesResponse,
    BacktestMetricsResponse,
    BacktestRequest,
    BacktestResponse,
    EquityPointResponse,
    PricePointResponse,
    TradeRecordResponse,
)
from app.services.backtest_service import BacktestService

router = APIRouter(prefix="/backtests", tags=["backtests"])

logger = structlog.get_logger(__name__)

_svc = BacktestService()


@router.get("/strategies", response_model=AvailableStrategiesResponse)
async def list_strategies():
    """List all available built-in strategies with descriptions."""
    return _svc.list_strategies()


@router.post("/run", response_model=BacktestResponse)
async def run_backtest(req: BacktestRequest):
    """
    Run a backtest against Bybit public historical data.
    No broker credentials required.

    Example body:
    ```json
    {
      "strategy_name": "SmaCrossover",
      "symbol": "BTCUSDT",
      "timeframe": "1d",
      "initial_capital": 10000,
      "parameters": { "fast_period": 20, "slow_period": 50 }
    }
    ```
    """
    try:
        result: BacktestResult = await _svc.run(req)
    except ValueError as exc:
        # Expected: bad params / not enough data. Client-fixable → 400.
        raise AppError(str(exc), code=ErrorCode.BAD_REQUEST) from exc
    except AppError:
        raise
    except Exception as exc:
        # Unexpected failure inside the backtest pipeline. Log the full stack
        # trace so we can trace where it originated; return a structured 502.
        logger.error(
            "backtest.failed",
            strategy=req.strategy_name,
            symbol=req.symbol,
            timeframe=req.timeframe,
            error=str(exc),
            exc_info=exc,
        )
        raise BacktestError(f"Backtest failed: {exc}") from exc

    return BacktestResponse(
        strategy_name=result.strategy_name,
        symbol=result.symbol,
        timeframe=result.timeframe,
        initial_capital=result.initial_capital,
        metrics=BacktestMetricsResponse(**result.metrics._asdict()),
        equity_curve=[EquityPointResponse(timestamp=p.timestamp, value=p.value) for p in result.equity_curve],
        trades=[TradeRecordResponse(**t._asdict()) for t in result.trades],
        prices=[PricePointResponse(timestamp=p.timestamp, close=p.close) for p in result.prices],
    )
