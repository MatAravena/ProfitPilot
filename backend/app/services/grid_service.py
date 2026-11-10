from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import structlog

from app.core.constants import MIN_BACKTEST_BARS
from app.domain.backtest.engine import BacktestEngine  # reuse the bars-per-year mapping
from app.domain.strategies.grid.params import GridParams, RegimeParams
from app.domain.strategies.grid.planner import build_plan_series
from app.domain.strategies.grid.policies import AccumulateNoStopPolicy, GuardedReanchorPolicy
from app.domain.strategies.grid.simulator import GridArmResult, run_grid_backtest
from app.models.schemas.grid_schemas import GridRequest
from app.services.backtest_service import BacktestService, _TIMEFRAME_MAP

logger = structlog.get_logger(__name__)


@dataclass
class GridBundle:
    symbol: str
    timeframe: str
    allow_intrabar_roundtrip: bool
    arms: Dict[str, GridArmResult]


class GridService:
    """Runs both grid arms over identical data. Mirrors AccumulationCompareService: reuses
    BacktestService for the OHLCV fetch/cache path (single source of truth for market data);
    domain math stays pure, this layer owns data access + config translation."""

    def __init__(self, backtest_service: Optional[BacktestService] = None) -> None:
        self._backtests = backtest_service or BacktestService()

    async def run(self, req: GridRequest) -> GridBundle:
        timeframe = _TIMEFRAME_MAP.get(req.timeframe)
        if timeframe is None:
            raise ValueError(f"Unknown timeframe: {req.timeframe}. Use one of {list(_TIMEFRAME_MAP)}")

        bars = await self._backtests._get_bars(req, timeframe)  # noqa: SLF001 — intentional reuse
        if len(bars) < MIN_BACKTEST_BARS:
            raise ValueError(f"Not enough data ({len(bars)} bars). Try a longer date range.")

        grid_params = GridParams(**req.grid.model_dump())
        regime_params = RegimeParams(**req.regime.model_dump())
        plan_series = build_plan_series(bars, grid_params, regime_params)
        bars_per_year = BacktestEngine._infer_bars_per_year(timeframe)  # noqa: SLF001

        common = dict(
            bars=bars, plan_series=plan_series, grid_params=grid_params,
            initial_capital=req.initial_capital, notional_per_rung=req.notional_per_rung,
            allow_intrabar_roundtrip=req.allow_intrabar_roundtrip, bars_per_year=bars_per_year,
        )
        arms: Dict[str, GridArmResult] = {
            "grid_guarded_reanchor": run_grid_backtest(policy=GuardedReanchorPolicy(grid_params), **common),
            "grid_accumulate_nostop": run_grid_backtest(policy=AccumulateNoStopPolicy(grid_params), **common),
        }

        return GridBundle(
            symbol=req.symbol, timeframe=req.timeframe,
            allow_intrabar_roundtrip=req.allow_intrabar_roundtrip, arms=arms,
        )
