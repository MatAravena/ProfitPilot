from __future__ import annotations

import structlog

from app.core.enums import Timeframe
from app.domain.backtest.data_provider import fetch_ohlcv
from app.domain.backtest.engine import BacktestEngine, BacktestResult
from app.domain.strategy.base import StrategyRegistry
from app.domain.strategy.loader import get_all_strategy_classes, load_user_strategies
from app.models.schemas.backtest_schemas import AvailableStrategiesResponse, BacktestRequest

logger = structlog.get_logger(__name__)

_TIMEFRAME_MAP = {
    "1m": Timeframe.M1,
    "5m": Timeframe.M5,
    "15m": Timeframe.M15,
    "30m": Timeframe.M30,
    "1h": Timeframe.H1,
    "4h": Timeframe.H4,
    "1d": Timeframe.D1,
    "1w": Timeframe.W1,
}


class BacktestService:
    async def run(self, req: BacktestRequest) -> BacktestResult:
        load_user_strategies()

        timeframe = _TIMEFRAME_MAP.get(req.timeframe)
        if timeframe is None:
            raise ValueError(f"Unknown timeframe: {req.timeframe}. Use one of {list(_TIMEFRAME_MAP)}")

        try:
            strategy_class = StrategyRegistry.get(req.strategy_name)
        except KeyError:
            available = StrategyRegistry.list_all()
            raise ValueError(f"Strategy '{req.strategy_name}' not found. Available: {available}")

        params = {"symbol": req.symbol, **req.parameters}
        strategy = strategy_class(parameters=params, timeframe=timeframe)

        logger.info("backtest.service.run", strategy=req.strategy_name, symbol=req.symbol)

        bars = await fetch_ohlcv(
            symbol=req.symbol,
            timeframe=timeframe,
            limit=1000,
            start=req.start,
            end=req.end,
        )

        if len(bars) < 60:
            raise ValueError(
                f"Not enough data returned ({len(bars)} bars). "
                "Try a longer date range or smaller timeframe."
            )

        engine = BacktestEngine(
            strategy=strategy,
            bars=bars,
            initial_capital=req.initial_capital,
            commission_pct=req.commission_pct,
        )
        return await engine.run()

    def list_strategies(self) -> AvailableStrategiesResponse:
        return AvailableStrategiesResponse(strategies=get_all_strategy_classes())
