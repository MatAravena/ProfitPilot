from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Tuple

import structlog

from app.core.constants import MIN_BACKTEST_BARS
from app.domain.backtest.accumulation import (
    AccumulatorGridParams, AccumulatorGridPolicy, ArmResult, CycleHunterParams,
    CycleHunterPolicy, CycleRotationParams, CycleRotationPolicy, CycleWeightedPolicy,
    FlatDcaPolicy, run_accumulation,
)
from app.domain.backtest.cycle_stats import auto_drop_estimator
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

        rotation_params = CycleRotationParams(
            sell_fraction_at_ath=req.rotation.sell_fraction_at_ath,
            ath_band=req.rotation.ath_band,
            sell_intensity_hi=req.rotation.sell_intensity_hi,
            k_sell_daily=req.rotation.k_sell_daily,
            sell_sharpness=req.rotation.sell_sharpness,
            expected_bear_drop=req.rotation.expected_bear_drop,
            buy_zone_top_frac=req.rotation.buy_zone_top_frac,
            k_deploy_daily=req.rotation.k_deploy_daily,
            deploy_floor=req.rotation.deploy_floor,
            reentry_gain=req.rotation.reentry_gain,
        )

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
            # ATH-aware rotation state machine (sell near top -> ~3-month cooldown ->
            # accumulate the decline). sell_cap tunable up to 1.0 via the request.
            "cycle_hunter": run_accumulation(
                bars,
                CycleHunterPolicy(params, CycleHunterParams(
                    sell_cap_frac=req.hunter.sell_cap_frac,
                    cooldown_days=req.hunter.cooldown_days,
                    reentry_within=req.hunter.reentry_within,
                    k_bear_daily=req.hunter.k_bear_daily,
                )),
                **common,
            ),
            # Buy-the-dip accumulation grid: deploy reserve into drawdowns, light trend-gated
            # profit trims, ratcheting core floor. Edge is on the buy side, not timing tops.
            "accumulator_grid": run_accumulation(
                bars, AccumulatorGridPolicy(AccumulatorGridParams()), **common,
            ),
            # Sell most near a confirmed ATH, then deploy the war chest across the lower half of
            # the drawdown. v2 = you set expected_bear_drop; auto = derived from past cycles.
            "cycle_rotation_v2": run_accumulation(
                bars, CycleRotationPolicy(params, rotation_params), **common,
            ),
            "cycle_rotation_auto": run_accumulation(
                bars,
                CycleRotationPolicy(
                    params, rotation_params,
                    drop_estimator=auto_drop_estimator(
                        [b.close for b in bars], caution_margin=req.rotation.caution_margin
                    ),
                ),
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
