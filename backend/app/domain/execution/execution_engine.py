"""Execution engine — turns strategy signals into broker orders.

Pure orchestration: exits → state machine → sizing → risk gate → placement.
No DB and no FastAPI. The broker adapter and RiskManager are injected. Persistence,
WebSocket broadcasting, and strategy.on_fill hooks are the caller's job (the executor).

Returns a list of ExecutionOutcome (one per order attempt in the cycle — a reversal
produces two: a close then an open).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

import structlog

from app.core.enums import Direction, OrderSide, OrderStatus, OrderType
from app.core.types import (
    Account,
    Fill,
    Order,
    OrderResult,
    Position,
    RiskConfig,
    RiskVeto,
    Signal,
)
from app.domain.broker.base import BrokerAdapter
from app.domain.execution import position_sizer
from app.domain.risk.risk_manager import RiskManager

logger = structlog.get_logger(__name__)


# Outcome action codes — also used as OrderRecord.status by the executor.
ACTION_OPENED_LONG = "opened_long"
ACTION_OPENED_SHORT = "opened_short"
ACTION_CLOSED = "closed"
ACTION_NOOP = "noop"
ACTION_REJECTED = "rejected"
ACTION_ERROR = "error"


@dataclass
class ExecutionOutcome:
    action: str
    reason: Optional[str] = None
    order: Optional[Order] = None
    order_result: Optional[OrderResult] = None
    fill: Optional[Fill] = None
    halted: bool = False


class ExecutionEngine:
    def __init__(self, risk_manager: RiskManager):
        self._risk = risk_manager
        self._log = logger.bind(component="ExecutionEngine")

    async def reconcile_and_execute(
        self,
        *,
        strategy_id: UUID,
        symbol: str,
        broker_id: str,
        adapter: BrokerAdapter,
        account: Account,
        position: Optional[Position],
        signals: List[Signal],
        risk_cfg: RiskConfig,
        latest_close: float,
        allow_short: bool = True,
    ) -> List[ExecutionOutcome]:
        # 1. Loop-managed exits take priority over any new signal.
        exit_outcome = await self._check_exits(
            strategy_id, symbol, broker_id, adapter, account, position, risk_cfg, latest_close
        )
        if exit_outcome is not None:
            return [exit_outcome]

        # 2. Intent = the most recent signal this cycle.
        if not signals:
            return [ExecutionOutcome(action=ACTION_NOOP, reason="no signal")]
        intent = signals[-1].direction
        signal_id = signals[-1].signal_id

        held = position is not None and position.quantity != 0
        held_long = held and position.quantity > 0

        # 3. CLOSE / NEUTRAL — flatten if in a position, else nothing.
        if intent in (Direction.CLOSE, Direction.NEUTRAL):
            if held:
                return [await self._close(
                    strategy_id, symbol, broker_id, adapter, account,
                    position, risk_cfg, latest_close, signal_id, reason="signal_close"
                )]
            return [ExecutionOutcome(action=ACTION_NOOP, reason="flat, no action")]

        # 4. Directional intent.
        want_long = intent == Direction.LONG
        if held and (held_long == want_long):
            return [ExecutionOutcome(action=ACTION_NOOP, reason="already in position")]

        outcomes: List[ExecutionOutcome] = []

        # Opposite position open → close it first (reversal).
        if held:
            outcomes.append(await self._close(
                strategy_id, symbol, broker_id, adapter, account,
                position, risk_cfg, latest_close, signal_id, reason="reversal"
            ))
            position = None

        if not want_long and not allow_short:
            outcomes.append(ExecutionOutcome(action=ACTION_NOOP, reason="shorting disabled"))
            return outcomes

        outcomes.append(await self._open(
            strategy_id, symbol, broker_id, adapter, account,
            risk_cfg, latest_close, signal_id, want_long
        ))
        return outcomes

    # ── Internals ────────────────────────────────────────────────────────────────

    async def _check_exits(
        self, strategy_id, symbol, broker_id, adapter, account,
        position, risk_cfg, latest_close,
    ) -> Optional[ExecutionOutcome]:
        if position is None or position.quantity == 0:
            return None
        is_long = position.quantity > 0
        stop = position_sizer.stop_loss_price(position.avg_entry_price, is_long, risk_cfg)
        tp = position_sizer.take_profit_price(position.avg_entry_price, is_long, risk_cfg)

        if is_long:
            hit_stop = latest_close <= stop
            hit_tp = tp is not None and latest_close >= tp
        else:
            hit_stop = latest_close >= stop
            hit_tp = tp is not None and latest_close <= tp

        if hit_stop or hit_tp:
            reason = "stop_loss" if hit_stop else "take_profit"
            return await self._close(
                strategy_id, symbol, broker_id, adapter, account,
                position, risk_cfg, latest_close, signal_id=None, reason=reason
            )
        return None

    async def _open(
        self, strategy_id, symbol, broker_id, adapter, account,
        risk_cfg, latest_close, signal_id, want_long: bool,
    ) -> ExecutionOutcome:
        qty = position_sizer.size_entry(account.equity, latest_close, risk_cfg)
        if qty <= 0:
            return ExecutionOutcome(action=ACTION_ERROR, reason="computed quantity is zero")
        side = OrderSide.BUY if want_long else OrderSide.SELL
        action = ACTION_OPENED_LONG if want_long else ACTION_OPENED_SHORT
        return await self._submit(
            strategy_id, symbol, broker_id, adapter, account, risk_cfg,
            latest_close, signal_id, side, qty, action,
            open_position=True, risk_check=True,
        )

    async def _close(
        self, strategy_id, symbol, broker_id, adapter, account,
        position, risk_cfg, latest_close, signal_id, reason: str,
    ) -> ExecutionOutcome:
        qty = abs(position.quantity)
        # Closing a long = SELL; closing a short = BUY.
        side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
        realized = (latest_close - position.avg_entry_price) * position.quantity
        return await self._submit(
            strategy_id, symbol, broker_id, adapter, account, risk_cfg,
            latest_close, signal_id, side, qty, ACTION_CLOSED,
            open_position=False, risk_check=False,
            realized_pnl=realized, close_reason=reason,
        )

    async def _submit(
        self, strategy_id, symbol, broker_id, adapter, account, risk_cfg,
        latest_close, signal_id, side, qty, action, *,
        open_position: bool, risk_check: bool,
        realized_pnl: float = 0.0, close_reason: Optional[str] = None,
    ) -> ExecutionOutcome:
        order = Order(
            order_id=uuid.uuid4(),
            strategy_id=strategy_id,
            broker_id=broker_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=qty,
            limit_price=latest_close,   # reference price so RiskManager can size-check
            signal_id=signal_id,
            metadata={"reason": close_reason} if close_reason else {},
            created_at=datetime.now(timezone.utc),
        )

        # Exits/closes reduce exposure — they always execute and never pass through the
        # risk veto (a stop-loss must never be blocked). Only opens are risk-gated.
        if risk_check:
            verdict = await self._risk.approve_order(order, account, risk_cfg)
            if isinstance(verdict, RiskVeto):
                halted = "drawdown" in verdict.rule_violated and risk_cfg.kill_switch_enabled
                return ExecutionOutcome(
                    action=ACTION_REJECTED, reason=verdict.reason, order=order, halted=halted
                )

        try:
            result = await adapter.place_order(order)
        except Exception as exc:  # broker/network failure — surfaced, not raised
            self._log.error("execution.place_failed", symbol=symbol, error=str(exc))
            return ExecutionOutcome(action=ACTION_ERROR, reason=str(exc), order=order)

        fill: Optional[Fill] = None
        if result.status == OrderStatus.FILLED:
            fill = Fill(
                fill_id=uuid.uuid4(),
                order_id=order.order_id,
                broker_fill_id=result.broker_order_id,
                symbol=symbol,
                side=side,
                filled_quantity=qty,
                avg_price=latest_close,
                commission=0.0,
                filled_at=datetime.now(timezone.utc),
            )
            if open_position:
                self._risk.increment_open_positions(strategy_id, +1)
            else:
                self._risk.increment_open_positions(strategy_id, -1)
                self._risk.update_daily_pnl(strategy_id, realized_pnl)

        return ExecutionOutcome(action=action, reason=close_reason, order=order,
                                order_result=result, fill=fill)
