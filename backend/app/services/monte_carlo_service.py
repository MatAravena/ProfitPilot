from __future__ import annotations

from typing import Tuple

import structlog

from app.core.types import RiskConfig
from app.domain.backtest.engine import BacktestResult
from app.domain.backtest.monte_carlo import MonteCarloResult, run_monte_carlo, trade_returns
from app.models.schemas.backtest_schemas import MonteCarloRequest
from app.services.backtest_service import BacktestService

logger = structlog.get_logger(__name__)


class MonteCarloService:
    """Orchestrates a Monte Carlo run.

    Runs the backtest through :class:`BacktestService` — the single source of truth for
    trades, so MC never re-implements execution — derives the fixed-fractional per-trade
    return series, and resamples it. Domain math stays pure; this layer owns the
    BacktestService dependency and config access (the risk-profile drawdown limit).
    """

    def __init__(self, backtest_service: BacktestService | None = None) -> None:
        self._backtests = backtest_service or BacktestService()

    async def run(self, req: MonteCarloRequest) -> Tuple[BacktestResult, MonteCarloResult]:
        # MonteCarloRequest is a superset of BacktestRequest, so this reproduces the exact
        # run the ordinary /run endpoint would (same costs, sizing, dates).
        result = await self._backtests.run(req)

        pnls = [t.pnl for t in result.trades]
        # Raises ValueError on < 2 trades — the router maps that to a 400.
        returns = trade_returns(pnls, result.initial_capital)

        # Threshold for risk_of_exceeding_drawdown = the user's total-drawdown limit (default 10%).
        # RiskConfig stores it as a fraction; MC works in percent.
        drawdown_threshold_pct = RiskConfig().max_total_drawdown_pct * 100.0

        mc = run_monte_carlo(
            returns,
            result.initial_capital,
            n_simulations=req.n_simulations,
            methods=req.methods,
            seed=req.seed,
            drawdown_threshold_pct=drawdown_threshold_pct,
        )
        return result, mc
