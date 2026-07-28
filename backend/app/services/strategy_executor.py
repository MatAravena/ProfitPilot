from __future__ import annotations
import asyncio
import importlib
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import structlog

from app.core.config import get_settings
from app.core.enums import BrokerID, MarketType, Timeframe
from app.core.types import MarketData, RiskConfig
from app.domain.broker.base import BrokerAdapter
from app.domain.execution.execution_engine import (
    ACTION_CLOSED,
    ACTION_ERROR,
    ACTION_NOOP,
    ExecutionEngine,
    ExecutionOutcome,
)
from app.domain.market_data.classify import classify_market
from app.domain.risk.risk_manager import RiskManager

logger = structlog.get_logger(__name__)
settings = get_settings()

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

# Routine no-ops we don't persist (avoids an OrderRecord every poll while holding).
_SILENT_NOOP_REASONS = {"no signal", "flat, no action", "already in position"}

_MAX_CONSECUTIVE_ERRORS = 5


class StrategyExecutor:
    """
    Manages one asyncio task per active (paper/live) strategy instance.
    Each task polls market data on the strategy's timeframe, generates signals,
    reconciles them against the current position through the ExecutionEngine
    (sizing → risk gate → broker), persists orders + signals, and broadcasts.
    """

    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}
        self._risk = RiskManager()
        self._engine = ExecutionEngine(self._risk)
        # Last processed bar timestamp per strategy — drives new-bar gating so signals
        # are generated once per closed bar, not on every poll.
        self._last_bar_ts: dict[str, object] = {}

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
            risk_cfgs = {inst.id: await self._build_risk_cfg(session, inst) for inst in instances}
            await session.commit()   # persist any risk profiles created on first access

        for inst in instances:
            await self._rehydrate_risk_state(inst, session_factory)
            self._launch(inst, risk_cfgs[inst.id], session_factory)

        logger.info("executor.booted", running=len(self._tasks))

    async def _build_risk_cfg(self, session, instance) -> RiskConfig:
        """Merge the user's risk profile with the strategy's per-strategy overrides."""
        from app.repositories.risk_profile_repository import RiskProfileRepository
        from app.services.risk_profile_service import RiskProfileService
        profile = await RiskProfileService(RiskProfileRepository(session)).get_or_create(instance.user_id)
        return _merge_risk_config(profile, instance)

    async def _rehydrate_risk_state(self, instance, session_factory) -> None:
        """Seed RiskManager state from persisted broker/ledger truth so drawdown and
        max-position limits are correct immediately after a restart."""
        market_type = classify_market(instance.symbol)
        async with session_factory() as session:
            adapter, _ = await self._resolve_adapter(
                session, instance.status, instance.id, instance.user_id,
                instance.broker_connection_id, market_type,
            )
            if adapter is None:
                return
            try:
                await adapter.connect()
                account = await adapter.get_account()
                positions = await adapter.get_positions()
            except Exception as exc:
                logger.warning("executor.rehydrate_failed", strategy_id=str(instance.id), error=str(exc))
                return
            finally:
                try:
                    await adapter.disconnect()
                except Exception:  # pragma: no cover - defensive
                    pass
            daily_pnl = await self._reconstruct_daily_pnl(session, instance.id)
        # Count only this strategy's symbol: a live broker's get_positions() returns the whole
        # account, and seeding an account-wide count would spuriously trip max_open_positions.
        open_positions = sum(1 for p in positions if p.symbol == instance.symbol)
        self._risk.seed_state(
            instance.id, equity=account.equity, open_position_count=open_positions,
            peak_equity=instance.peak_equity,   # persisted high-water mark (None on first run)
            daily_pnl=daily_pnl,
        )

    async def _reconstruct_daily_pnl(self, session, strategy_id) -> float:
        """Sum realized P&L of today's (UTC) closes so the daily-drawdown kill switch
        resumes accurately after a restart."""
        from sqlalchemy import select
        from app.models.db.order_record import OrderRecord

        midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(OrderRecord.realized_pnl, OrderRecord.created_at).where(
            OrderRecord.strategy_instance_id == strategy_id,
            OrderRecord.status == ACTION_CLOSED,
        )
        total = 0.0
        for pnl, created in (await session.execute(stmt)).all():
            if pnl is None:
                continue
            when = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
            if when >= midnight:
                total += pnl
        return total

    def notify_status_change(self, instance, risk_cfg: RiskConfig, session_factory) -> None:
        """Called when a strategy's status changes — starts or stops its loop."""
        sid = str(instance.id)
        if instance.status in ("paper", "live"):
            if sid not in self._tasks:
                # Explicitly (re)activating a strategy is the manual authorization to
                # clear any prior kill-switch halt — otherwise the relaunched loop would
                # be vetoed on every order by the stale halted flag.
                self._risk.release_halt(instance.id, authorized_by="status_change")
                self._launch(instance, risk_cfg, session_factory)
        else:
            self._stop(sid)

    def notify_config_change(self, instance, risk_cfg: RiskConfig, session_factory) -> None:
        """Called when a running strategy's config is edited — restarts only that strategy's
        loop so the new (merged) config takes effect immediately. No-op if not running."""
        sid = str(instance.id)
        if sid in self._tasks and instance.status in ("paper", "live"):
            self._stop(sid)
            self._launch(instance, risk_cfg, session_factory)
            logger.info("executor.config_reloaded", strategy_id=sid)

    def shutdown(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()

    # ── Internal ─────────────────────────────────────────────────────────────────

    def _launch(self, instance, risk_cfg: RiskConfig, session_factory) -> None:
        sid = str(instance.id)
        task = asyncio.create_task(
            self._run_loop(
                instance.id, instance.class_name, instance.symbol, instance.timeframe,
                instance.parameters, instance.user_id, instance.status,
                instance.broker_connection_id, risk_cfg,
                instance.allow_short, instance.poll_seconds, session_factory,
            ),
            name=f"strategy_{sid}",
        )
        self._tasks[sid] = task
        logger.info("executor.started", strategy_id=sid, class_name=instance.class_name,
                    symbol=instance.symbol, timeframe=instance.timeframe, status=instance.status)

    def _stop(self, strategy_id: str) -> None:
        task = self._tasks.pop(strategy_id, None)
        # Drop the new-bar cursor so a subsequent relaunch (e.g. a config reload) re-evaluates
        # the current bar with the new config instead of waiting for the next bar close — and
        # so the dict doesn't leak entries for stopped strategies.
        self._last_bar_ts.pop(strategy_id, None)
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
        status: str,
        broker_connection_id: Optional[uuid.UUID],
        risk_cfg: RiskConfig,
        allow_short: bool,
        poll_override: Optional[int],
        session_factory,
    ) -> None:
        poll_secs = poll_override or _POLL_SECONDS.get(timeframe_str, 3600)
        timeframe = _TF_MAP.get(timeframe_str, Timeframe.D1)

        # Small jitter so strategies don't all fire at the same second
        await asyncio.sleep(2)

        while True:
            try:
                keep_going = await self._execute_once(
                    strategy_id, class_name, symbol, timeframe, parameters,
                    user_id, status, broker_connection_id, risk_cfg, allow_short,
                    session_factory,
                )
                if not keep_going:
                    logger.warning("executor.halted", strategy_id=str(strategy_id))
                    self._tasks.pop(str(strategy_id), None)
                    self._last_bar_ts.pop(str(strategy_id), None)
                    break
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
        status: str,
        broker_connection_id: Optional[uuid.UUID],
        risk_cfg: RiskConfig,
        allow_short: bool,
        session_factory,
    ) -> bool:
        """Run one poll cycle. Returns False if the strategy should stop (halted)."""
        from app.domain.backtest.data_provider import fetch_ohlcv
        from app.domain.strategy.base import StrategyRegistry
        from app.domain.strategy.loader import load_user_strategies
        from app.api.ws.manager import manager

        # Ensure strategy classes are registered — built-ins always, user_strategies/*.py
        # only when the requested class isn't registered yet (avoids a filesystem glob on
        # every poll cycle).
        importlib.import_module("app.domain.strategy.examples.sma_crossover")
        if class_name not in StrategyRegistry.list_all():
            load_user_strategies()

        bars = await fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=200)
        if not bars:
            logger.warning("executor.no_data", symbol=symbol)
            return True

        market_data = MarketData(symbol=symbol, timeframe=timeframe, bars=bars)

        try:
            strategy_class = StrategyRegistry.get(class_name)
        except KeyError:
            logger.error("executor.unknown_class", class_name=class_name)
            return True

        params = {"symbol": symbol, **parameters}
        strategy = strategy_class(parameters=params, timeframe=timeframe)

        latest_close = bars[-1].close
        now = datetime.now(timezone.utc)

        # New-bar gating: (re)generate signals only once per closed bar. Exit / stop-loss
        # checks below run every poll regardless (they don't need a fresh signal), so a slow
        # timeframe polled frequently keeps intraday stop protection.
        sid = str(strategy_id)
        bar_ts = bars[-1].timestamp
        signals = []
        if self._last_bar_ts.get(sid) != bar_ts:
            try:
                signals = await strategy.generate_signals(market_data)
                self._last_bar_ts[sid] = bar_ts
            except Exception as exc:
                logger.error("executor.generate_failed", strategy_id=sid, error=str(exc))
                # Leave signals empty and retry generation next poll; still run exits below.

        async with session_factory() as session:
            self._persist_signals(session, strategy_id, user_id, symbol, timeframe, signals, latest_close, now)
            outcomes = await self._trade_on_signals(
                session, strategy=strategy, strategy_id=strategy_id, user_id=user_id,
                symbol=symbol, status=status, broker_connection_id=broker_connection_id,
                signals=signals, latest_close=latest_close,
                risk_cfg=risk_cfg, allow_short=allow_short,
            )
            keep_going = await self._update_instance(session, strategy_id, signals, outcomes, now)
            await session.commit()

        await self._broadcast(manager, strategy_id, symbol, signals, outcomes, latest_close, now)
        return keep_going

    # ── Trade execution ──────────────────────────────────────────────────────────

    async def _trade_on_signals(
        self, session, *, strategy, strategy_id, user_id, symbol, status,
        broker_connection_id, signals, latest_close, risk_cfg, allow_short,
    ) -> List[ExecutionOutcome]:
        market_type = classify_market(symbol)
        adapter, broker_id = await self._resolve_adapter(
            session, status, strategy_id, user_id, broker_connection_id, market_type
        )
        if adapter is None:
            self._persist_order_record(
                session, strategy_id, user_id, symbol,
                ExecutionOutcome(action=ACTION_ERROR, reason="no active broker connection"),
            )
            return [ExecutionOutcome(action=ACTION_ERROR, reason="no active broker connection")]

        try:
            if hasattr(adapter, "set_mark"):
                adapter.set_mark(symbol, latest_close)
            await adapter.connect()
            account = await adapter.get_account()
            self._risk.observe_equity(strategy_id, account.equity)   # track high-water mark
            positions = await adapter.get_positions()
            pos = next((p for p in positions if p.symbol == symbol), None)

            outcomes = await self._engine.reconcile_and_execute(
                strategy_id=strategy_id, symbol=symbol, broker_id=broker_id, adapter=adapter,
                account=account, position=pos, signals=signals,
                risk_cfg=risk_cfg, latest_close=latest_close, allow_short=allow_short,
            )

            for o in outcomes:
                if o.fill is not None:
                    try:
                        await strategy.on_fill(o.fill)
                    except Exception as exc:
                        logger.warning("executor.on_fill_failed", error=str(exc))
                if self._should_persist(o):
                    self._persist_order_record(session, strategy_id, user_id, symbol, o)
            return outcomes
        except Exception as exc:
            # Broker/network failure (connect, get_account, get_positions, …). Record it as an
            # error outcome so error_count advances and the strategy eventually halts, matching
            # the no-connection branch — rather than propagating and retrying forever.
            # Roll back first: a DB-origin failure (e.g. the paper ledger flush) leaves the
            # session in a failed-transaction state, and persisting/committing on it would raise
            # PendingRollbackError and skip the error accounting.
            await session.rollback()
            logger.error("executor.trade_failed", strategy_id=str(strategy_id), error=str(exc))
            outcome = ExecutionOutcome(action=ACTION_ERROR, reason=str(exc))
            self._persist_order_record(session, strategy_id, user_id, symbol, outcome)
            return [outcome]
        finally:
            try:
                await adapter.disconnect()
            except Exception:  # pragma: no cover - defensive
                pass

    async def _resolve_adapter(
        self, session, status, strategy_id, user_id, broker_connection_id,
        market_type: MarketType,
    ) -> Tuple[Optional[BrokerAdapter], str]:
        if status == "paper":
            from app.domain.broker.adapters.simulated_adapter import SimulatedBrokerAdapter
            adapter = SimulatedBrokerAdapter(
                session=session, strategy_id=strategy_id, user_id=user_id,
                starting_equity=settings.SIM_STARTING_EQUITY, market_type=market_type,
                # Inject realistic costs so paper ≈ backtest ≈ live (adapter itself defaults to 0).
                commission_pct=settings.SIM_COMMISSION_PCT,
                slippage_pct=settings.SIM_SLIPPAGE_PCT,
            )
            return adapter, "sim"

        # live — resolve a real broker connection
        if broker_connection_id is None:
            return None, ""
        from app.models.db.broker_connection import BrokerConnection
        from app.services.broker_service import _build_adapter
        conn = await session.get(BrokerConnection, broker_connection_id)
        if conn is None or not conn.is_active:
            return None, ""
        adapter = _build_adapter(conn)
        broker_id = getattr(adapter.broker_id, "value", adapter.broker_id)
        return adapter, broker_id

    @staticmethod
    def _should_persist(o: ExecutionOutcome) -> bool:
        if o.action != ACTION_NOOP:
            return True
        return o.reason not in _SILENT_NOOP_REASONS

    # ── Persistence ──────────────────────────────────────────────────────────────

    def _persist_signals(self, session, strategy_id, user_id, symbol, timeframe, signals, latest_close, now):
        from app.models.db.signal_record import SignalRecord
        for sig in signals:
            session.add(SignalRecord(
                id=uuid.uuid4(),
                strategy_instance_id=strategy_id,
                user_id=user_id,
                symbol=symbol,
                timeframe=timeframe.value,
                direction=sig.direction.value,
                confidence=sig.confidence,
                source=sig.source.value,
                generated_at=now,
                close_price=latest_close,
            ))

    def _persist_order_record(self, session, strategy_id, user_id, symbol, o: ExecutionOutcome):
        from app.models.db.order_record import OrderRecord
        order = o.order
        session.add(OrderRecord(
            id=uuid.uuid4(),
            strategy_instance_id=strategy_id,
            user_id=user_id,
            symbol=symbol,
            side=order.side.value if order else None,
            quantity=order.quantity if order else None,
            status=o.action,
            reason=o.reason,
            broker_order_id=o.order_result.broker_order_id if o.order_result else None,
            filled_qty=o.fill.filled_quantity if o.fill else None,
            avg_price=o.fill.avg_price if o.fill else None,
            realized_pnl=o.realized_pnl,
            signal_id=order.signal_id if order else None,
        ))

    async def _update_instance(self, session, strategy_id, signals, outcomes, now) -> bool:
        from app.models.db.strategy_instance import StrategyInstance
        inst = await session.get(StrategyInstance, strategy_id)
        if inst is None:
            return True

        if signals:
            inst.last_signal_at = now

        # Persist the running high-water mark so total-drawdown survives a restart.
        peak = self._risk.peak_equity(strategy_id)
        if peak is not None:
            inst.peak_equity = peak

        halted = any(o.halted for o in outcomes)
        errored = any(o.action == ACTION_ERROR for o in outcomes)

        if errored:
            inst.error_count += 1
        else:
            inst.error_count = 0

        if halted or inst.error_count >= _MAX_CONSECUTIVE_ERRORS:
            inst.status = "halted"
            return False
        return True

    async def _broadcast(self, manager, strategy_id, symbol, signals, outcomes, latest_close, now):
        for sig in signals:
            await manager.broadcast("strategy.signal", {
                "strategy_id": str(strategy_id),
                "symbol": symbol,
                "direction": sig.direction.value,
                "confidence": sig.confidence,
                "close_price": latest_close,
                "generated_at": now.isoformat(),
            })
        for o in outcomes:
            if o.order is None:
                continue
            await manager.broadcast("strategy.order", {
                "strategy_id": str(strategy_id),
                "symbol": symbol,
                "action": o.action,
                "side": o.order.side.value,
                "quantity": o.order.quantity,
                "reason": o.reason,
                "filled": o.fill is not None,
                "price": latest_close,
                "at": now.isoformat(),
            })


def _merge_risk_config(profile, instance) -> RiskConfig:
    """Merge the user's RiskProfile (defaults) with the strategy's per-strategy overrides.
    A NULL override inherits the profile value; position size is always per-strategy."""
    def pick(override, default):
        return override if override is not None else default

    return RiskConfig(
        max_position_size_pct=instance.size_pct,
        stop_loss_pct=pick(instance.stop_loss_pct, profile.stop_loss_pct),
        take_profit_pct=pick(instance.take_profit_pct, profile.take_profit_pct),
        max_open_positions=pick(instance.max_open_positions, profile.max_open_positions),
        max_daily_drawdown_pct=pick(instance.max_daily_drawdown_pct, profile.max_daily_drawdown_pct),
        max_total_drawdown_pct=pick(instance.max_total_drawdown_pct, profile.max_total_drawdown_pct),
        max_orders_per_minute=pick(instance.max_orders_per_minute, profile.max_orders_per_minute),
        kill_switch_enabled=pick(instance.kill_switch_enabled, profile.kill_switch_enabled),
    )


# Module-level singleton — imported by main.py lifespan
executor = StrategyExecutor()
