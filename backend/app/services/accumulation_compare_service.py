from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Tuple

import structlog

from app.core.constants import MIN_BACKTEST_BARS
from app.domain.backtest.accumulation import (
    ArmResult, CycleWeightedPolicy, FlatDcaPolicy, run_accumulation,
)
from app.domain.backtest.engine import BacktestEngine  # reuse the bars-per-year mapping
from app.domain.backtest.halving_cycle import CycleParams, cycle_markers
from app.models.schemas.backtest_schemas import DcaCompareRequest
from app.services.backtest_service import BacktestService, _TIMEFRAME_MAP

logger = structlog.get_logger(__name__)


@dataclass
class DcaCompareBundle:
    symbol: str
    timeframe: str
    capital_model: str
    cycle_markers: List[Tuple[date, str]]
    arms: Dict[str, ArmResult]


class AccumulationCompareService:
    """Runs flat DCA, cycle-weighted accumulation, and full rotation over identical BTC data.

    Reuses BacktestService for the OHLCV fetch/cache path (single source of truth for market
    data). Domain math stays pure; this layer owns data access + config translation.
    """

    def __init__(self, backtest_service: BacktestService | None = None) -> None:
        self._backtests = backtest_service or BacktestService()

    async def run(self, req: DcaCompareRequest) -> DcaCompareBundle:
        timeframe = _TIMEFRAME_MAP.get(req.timeframe)
        if timeframe is None:
            raise ValueError(f"Unknown timeframe: {req.timeframe}. Use one of {list(_TIMEFRAME_MAP)}")

        if req.capital_model == "contributions" and req.contribution_amount <= 0:
            raise ValueError("contribution_amount must be > 0 for the contributions model")
        if req.capital_model == "lump_sum" and req.lump_sum_budget <= 0:
            raise ValueError("lump_sum_budget must be > 0 for the lump_sum model")

        # Reuse the backtest cache/fetch path (single source of truth for OHLCV).
        bars = await self._backtests._get_bars(req, timeframe)  # noqa: SLF001 — intentional reuse
        if len(bars) < MIN_BACKTEST_BARS:
            raise ValueError(
                f"Not enough data ({len(bars)} bars). Try a longer date range."
            )

        params = CycleParams(
            days_to_top=req.cycle.days_to_top,
            top_to_bottom=req.cycle.top_to_bottom,
            sigma_top=req.cycle.sigma_top,
            sigma_bottom=req.cycle.sigma_bottom,
            base_buy=req.cycle.base_buy,
        )
        bars_per_year = BacktestEngine._infer_bars_per_year(timeframe)  # noqa: SLF001

        common = dict(
            capital_model=req.capital_model,
            contribution_amount=req.contribution_amount,
            contribution_interval_days=req.contribution_interval_days,
            lump_sum_budget=req.lump_sum_budget,
            commission_pct=req.commission_pct,
            slippage_pct=req.slippage_pct,
            bars_per_year=bars_per_year,
        )

        arms: Dict[str, ArmResult] = {
            "flat_dca": run_accumulation(bars, FlatDcaPolicy(), **common),
            "smart_accumulate": run_accumulation(
                bars,
                CycleWeightedPolicy(params, distribute=False, k_buy=req.cycle.k_buy,
                                    k_sell=req.cycle.k_sell, rolling_window=req.cycle.rolling_window),
                **common,
            ),
            "full_rotation": run_accumulation(
                bars,
                CycleWeightedPolicy(params, distribute=True, k_buy=req.cycle.k_buy,
                                    k_sell=req.cycle.k_sell, rolling_window=req.cycle.rolling_window),
                **common,
            ),
        }

        markers = cycle_markers(bars[0].timestamp.date(), bars[-1].timestamp.date(), params)

        return DcaCompareBundle(
            symbol=req.symbol,
            timeframe=req.timeframe,
            capital_model=req.capital_model,
            cycle_markers=markers,
            arms=arms,
        )
