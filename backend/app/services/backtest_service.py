from __future__ import annotations

from datetime import timedelta
from typing import List, Optional

import structlog

from app.core.enums import Timeframe
from app.core.types import OHLCV
from app.domain.backtest.data_provider import fetch_ohlcv
from app.domain.backtest.engine import BacktestEngine, BacktestResult
from app.domain.strategy.base import StrategyRegistry
from app.domain.strategy.loader import get_all_strategy_classes, load_user_strategies
from app.models.db.ohlcv_bar import OhlcvBar
from app.models.schemas.backtest_schemas import AvailableStrategiesResponse, BacktestRequest
from app.repositories.ohlcv_repository import OhlcvRepository

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

# Bars within this tolerance of the requested boundary are considered covered
_DATE_TOLERANCE = timedelta(days=5)


def _row_to_ohlcv(row: OhlcvBar, timeframe: Timeframe) -> OHLCV:
    return OHLCV(
        timestamp=row.timestamp,
        symbol=row.symbol,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume=row.volume,
        timeframe=timeframe,
    )


def _cache_covers(rows: List[OhlcvBar], start, end) -> bool:
    """True if the cached rows fully span the requested [start, end] range."""
    if not rows:
        return False
    earliest = rows[0].timestamp
    latest = rows[-1].timestamp
    start_ok = start is None or earliest <= start + _DATE_TOLERANCE
    end_ok = end is None or latest >= end - _DATE_TOLERANCE
    return start_ok and end_ok


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

        bars = await self._get_bars(req, timeframe)

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
            stop_loss_pct=req.stop_loss_pct,
            take_profit_pct=req.take_profit_pct,
        )
        return await engine.run()

    async def _get_bars(self, req: BacktestRequest, timeframe: Timeframe) -> List[OHLCV]:
        """Cache-aside: serve from DB when the range is fully covered, otherwise fetch and store."""
        from app.db.base import AsyncSessionLocal

        # Skip cache when no start bound — can't validate coverage without a lower bound.
        # Always fetch fresh with limit=1000; yfinance_provider will derive start from end.
        if req.start is None:
            logger.info("backtest.service.run", strategy=req.strategy_name, symbol=req.symbol)
            return await fetch_ohlcv(symbol=req.symbol, timeframe=timeframe, limit=1000, end=req.end)

        async with AsyncSessionLocal() as session:
            repo = OhlcvRepository(session)
            cached = await repo.get_range(req.symbol, req.timeframe, req.start, req.end)

            if _cache_covers(cached, req.start, req.end):
                logger.info(
                    "backtest.cache_hit",
                    symbol=req.symbol,
                    timeframe=req.timeframe,
                    bars=len(cached),
                )
                return [_row_to_ohlcv(row, timeframe) for row in cached]

            logger.info(
                "backtest.cache_miss",
                symbol=req.symbol,
                timeframe=req.timeframe,
                cached_bars=len(cached),
            )
            bars = await fetch_ohlcv(
                symbol=req.symbol,
                timeframe=timeframe,
                limit=1000,
                start=req.start,
                end=req.end,
            )

            if bars:
                await repo.upsert_bars(bars)
                await session.commit()

            return bars

    def list_strategies(self) -> AvailableStrategiesResponse:
        return AvailableStrategiesResponse(strategies=get_all_strategy_classes())
