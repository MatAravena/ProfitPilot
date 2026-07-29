from __future__ import annotations

from dataclasses import asdict

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
    MonteCarloMethodResponse,
    MonteCarloRequest,
    MonteCarloResponse,
    PricePointResponse,
    TradeRecordResponse,
)
from app.services.backtest_service import BacktestService
from app.services.monte_carlo_service import MonteCarloService

router = APIRouter(prefix="/backtests", tags=["backtests"])

logger = structlog.get_logger(__name__)

_svc = BacktestService()
_mc_svc = MonteCarloService(_svc)


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


@router.post("/montecarlo", response_model=MonteCarloResponse)
async def run_montecarlo(req: MonteCarloRequest):
    """Run the backtest, then resample its trade sequence to turn one path into a
    distribution (bootstrap = sampling risk, shuffle = ordering risk). Opt-in: this
    re-runs the backtest server-side, so it isn't folded into every ordinary /run.

    `< 2` trades → 400 (a distribution needs at least two samples).
    """
    try:
        result, mc = await _mc_svc.run(req)
    except ValueError as exc:
        # Bad params / not enough data / < 2 trades. Client-fixable → 400.
        raise AppError(str(exc), code=ErrorCode.BAD_REQUEST) from exc
    except AppError:
        raise
    except Exception as exc:
        logger.error(
            "montecarlo.failed",
            strategy=req.strategy_name,
            symbol=req.symbol,
            timeframe=req.timeframe,
            error=str(exc),
            exc_info=exc,
        )
        raise BacktestError(f"Monte Carlo failed: {exc}") from exc

    return MonteCarloResponse(
        strategy_name=result.strategy_name,
        symbol=result.symbol,
        timeframe=result.timeframe,
        initial_capital=result.initial_capital,
        n_simulations=mc.n_simulations,
        n_trades=mc.n_trades,
        realized_total_return_pct=mc.realized_total_return_pct,
        drawdown_threshold_pct=mc.drawdown_threshold_pct,
        # Domain dataclass field names match the response schema → build straight from asdict.
        methods={name: MonteCarloMethodResponse(**asdict(m)) for name, m in mc.methods.items()},
    )
