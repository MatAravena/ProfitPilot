from __future__ import annotations
import asyncio
import importlib
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog

from app.core.enums import Timeframe
from app.core.types import MarketData

logger = structlog.get_logger(__name__)

# How long to wait between signal checks per timeframe
_POLL_SECONDS = {
    "1m": 60,   "5m": 300,  "15m": 900,  "30m": 1800,
    "1h": 3600, "4h": 14400, "1d": 3600,  "1w": 3600,
    # For 1d/1w we still poll hourly — the strategy will only fire on new bar close
}

_TF_MAP = {
    "1m": Timeframe.M1,  "5m": Timeframe.M5,  "15m": Timeframe.M15,
    "30m": Timeframe.M30, "1h": Timeframe.H1,  "4h": Timeframe.H4,
    "1d": Timeframe.D1,   "1w": Timeframe.W1,
}


class StrategyExecutor:
    """
    Manages one asyncio task per active (paper/live) strategy instance.
    Each task polls market data on the strategy's timeframe, calls generate_signals(),
    persists results to signals table, and broadcasts via WebSocket.
    """

    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}

    # ── Lifecycle ────────────────────────────────────────────────────────────────

    async def boot(self, session_factory) -> None:
        """Load all currently active strategies and start their loops."""
        from app.models.db.strategy_instance import StrategyInstance
        from sqlalchemy import select

        async with session_factory() as session:
            result = await session.execute(
                select(StrategyInstance).where(StrategyInstance.status.in_(["paper", "live"]))
            )
            instances = list(result.scalars().all())

        for inst in instances:
            self._launch(inst, session_factory)

        logger.info("executor.booted", running=len(self._tasks))

    def notify_status_change(self, instance, session_factory) -> None:
        """Called when a strategy's status changes — starts or stops its loop."""
        sid = str(instance.id)
        if instance.status in ("paper", "live"):
            if sid not in self._tasks:
                self._launch(instance, session_factory)
        else:
            self._stop(sid)

    def shutdown(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()

    # ── Internal ─────────────────────────────────────────────────────────────────

    def _launch(self, instance, session_factory) -> None:
        sid = str(instance.id)
        task = asyncio.create_task(
            self._run_loop(instance.id, instance.class_name, instance.symbol,
                           instance.timeframe, instance.parameters, instance.user_id,
                           session_factory),
            name=f"strategy_{sid}",
        )
        self._tasks[sid] = task
        logger.info("executor.started", strategy_id=sid, class_name=instance.class_name,
                    symbol=instance.symbol, timeframe=instance.timeframe)

    def _stop(self, strategy_id: str) -> None:
        task = self._tasks.pop(strategy_id, None)
        if task:
            task.cancel()
            logger.info("executor.stopped", strategy_id=strategy_id)

    async def _run_loop(
        self,
        strategy_id: uuid.UUID,
        class_name: str,
        symbol: str,
        timeframe_str: str,
        parameters: dict,
        user_id: uuid.UUID,
        session_factory,
    ) -> None:
        poll_secs = _POLL_SECONDS.get(timeframe_str, 3600)
        timeframe = _TF_MAP.get(timeframe_str, Timeframe.D1)

        # Small jitter so strategies don't all fire at the same second
        await asyncio.sleep(2)

        while True:
            try:
                await self._execute_once(
                    strategy_id, class_name, symbol, timeframe, parameters, user_id, session_factory
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("executor.loop_error", strategy_id=str(strategy_id), error=str(exc))

            try:
                await asyncio.sleep(poll_secs)
            except asyncio.CancelledError:
                break

    async def _execute_once(
        self,
        strategy_id: uuid.UUID,
        class_name: str,
        symbol: str,
        timeframe: Timeframe,
        parameters: dict,
        user_id: uuid.UUID,
        session_factory,
    ) -> None:
        from app.domain.backtest.data_provider import fetch_ohlcv
        from app.domain.strategy.base import StrategyRegistry
        from app.models.db.signal_record import SignalRecord
        from app.api.ws.manager import manager

        # Ensure strategy classes are registered
        importlib.import_module("app.domain.strategy.examples.sma_crossover")

        bars = await fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=200)
        if not bars:
            logger.warning("executor.no_data", symbol=symbol)
            return

        market_data = MarketData(symbol=symbol, timeframe=timeframe, bars=bars)

        try:
            strategy_class = StrategyRegistry.get(class_name)
        except KeyError:
            logger.error("executor.unknown_class", class_name=class_name)
            return

        params = {"symbol": symbol, **parameters}
        strategy = strategy_class(parameters=params, timeframe=timeframe)

        try:
            signals = await strategy.generate_signals(market_data)
        except Exception as exc:
            logger.error("executor.generate_failed", strategy_id=str(strategy_id), error=str(exc))
            return

        if not signals:
            return

        close_price = bars[-1].close if bars else None
        now = datetime.now(timezone.utc)

        # Persist signals
        async with session_factory() as session:
            for sig in signals:
                record = SignalRecord(
                    id=uuid.uuid4(),
                    strategy_instance_id=strategy_id,
                    user_id=user_id,
                    symbol=symbol,
                    timeframe=timeframe.value,
                    direction=sig.direction.value,
                    confidence=sig.confidence,
                    source=sig.source.value,
                    generated_at=now,
                    close_price=close_price,
                )
                session.add(record)
            await session.commit()

        # Broadcast via WebSocket
        for sig in signals:
            await manager.broadcast("strategy.signal", {
                "strategy_id": str(strategy_id),
                "symbol": symbol,
                "direction": sig.direction.value,
                "confidence": sig.confidence,
                "close_price": close_price,
                "generated_at": now.isoformat(),
            })

        logger.info("executor.signals_generated",
                    strategy_id=str(strategy_id), count=len(signals), symbol=symbol)


# Module-level singleton — imported by main.py lifespan
executor = StrategyExecutor()
