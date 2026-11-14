from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import structlog

from app.core.constants import STRATEGY_LOOKBACK_BARS
from app.core.types import RiskConfig
from app.domain.backtest.accumulation import bars_per_day
from app.domain.backtest.engine import BacktestEngine
from app.domain.backtest.walk_forward import WalkForwardResult, expand_grid, walk_forward
from app.domain.strategy.base import StrategyRegistry
from app.domain.strategy.loader import load_user_strategies
from app.models.schemas.walk_forward_schemas import WalkForwardRequest
from app.services.backtest_service import BacktestService, _TIMEFRAME_MAP

logger = structlog.get_logger(__name__)


@dataclass
class WalkForwardRun:
    strategy_name: str
    symbol: str
    timeframe: str
    train_bars: int
    test_bars: int
    skipped_combinations: int
    bar_timestamps_ms: List[int]
    result: WalkForwardResult


class WalkForwardService:
    """Orchestrates a walk-forward run. Market data comes through BacktestService (one
    cache path); every backtest goes through BacktestEngine inside the pure domain
    `walk_forward` (one execution path) with the same costs, sizing and history window
    as an ordinary backtest and as live."""

    def __init__(self, backtest_service: Optional[BacktestService] = None) -> None:
        self._backtests = backtest_service or BacktestService()

    async def run(self, req: WalkForwardRequest) -> WalkForwardRun:
        load_user_strategies()
        timeframe = _TIMEFRAME_MAP.get(req.timeframe)
        if timeframe is None:
            raise ValueError(f"Unknown timeframe: {req.timeframe}. Use one of {list(_TIMEFRAME_MAP)}")
        try:
            strategy_class = StrategyRegistry.get(req.strategy_name)
        except KeyError:
            raise ValueError(f"Strategy '{req.strategy_name}' not found. Available: {StrategyRegistry.list_all()}")

        overlap = set(req.param_grid) & set(req.parameters)
        if overlap:
            raise ValueError(f"Parameters both fixed and searched: {sorted(overlap)}")

        def make(params: Dict[str, Any]):
            return strategy_class(parameters={"symbol": req.symbol, **req.parameters, **params},
                                  timeframe=timeframe)

        # Drop combos the strategy itself rejects (e.g. fast >= slow) instead of failing the run.
        valid: List[Dict[str, Any]] = []
        combos = expand_grid(req.param_grid)
        total = len(combos)
        for combo in combos:
            try:
                make(combo)
                valid.append(combo)
            except (ValueError, TypeError):
                pass
        if not valid:
            raise ValueError("No parameter combination in param_grid is valid for this strategy")

        bars = await self._backtests._get_bars(req, timeframe)  # noqa: SLF001 — intentional reuse
        per_day = bars_per_day(bars)
        train_bars = max(2, round(req.train_days * per_day))
        test_bars = max(1, round(req.test_days * per_day))

        size_pct = req.position_size_pct
        if size_pct is None:   # same default as an ordinary backtest: the live risk model's
            size_pct = RiskConfig().max_position_size_pct

        grid = {"__combo__": list(range(len(valid)))}   # search over the pre-validated combos
        result = await walk_forward(
            bars, lambda p: make(valid[p["__combo__"]]), grid,
            train_bars=train_bars, test_bars=test_bars, objective=req.objective,
            initial_capital=req.initial_capital, lookback_bars=STRATEGY_LOOKBACK_BARS,
            bars_per_year=BacktestEngine._infer_bars_per_year(timeframe),  # noqa: SLF001
            commission_pct=req.commission_pct, slippage_pct=req.slippage_pct,
            position_size_pct=size_pct, risk_per_trade_pct=req.risk_per_trade_pct,
            stop_loss_pct=req.stop_loss_pct,
            take_profit_pct=req.take_profit_pct,
        )
        for fold in result.folds:   # report real parameter names, not the combo index
            fold.params = valid[fold.params["__combo__"]]
        result.distinct_param_sets = len({tuple(sorted(f.params.items())) for f in result.folds})

        logger.info("walk_forward.complete", strategy=req.strategy_name, symbol=req.symbol,
                    folds=len(result.folds), oos_return=round(result.oos_total_return_pct, 2))
        return WalkForwardRun(
            strategy_name=req.strategy_name, symbol=req.symbol, timeframe=req.timeframe,
            train_bars=train_bars, test_bars=test_bars,
            skipped_combinations=total - len(valid),
            bar_timestamps_ms=[int(b.timestamp.timestamp() * 1000) for b in bars],
            result=result,
        )
