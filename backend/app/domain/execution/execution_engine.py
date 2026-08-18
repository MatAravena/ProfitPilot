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
from app.domain.execution.reconcile import CLOSE, OPEN_LONG, OPEN_SHORT, plan_actions
from app.domain.instruments import (
    INSTRUMENTS,
    InstrumentCatalog,
    InstrumentViolation,
    conform_order,
    floor_to_step,
    round_to_tick,
)
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
    realized_pnl: Optional[float] = None   # set for a filled close
    halted: bool = False


class ExecutionEngine:
    def __init__(self, risk_manager: RiskManager, instruments: InstrumentCatalog = INSTRUMENTS):
        self._risk = risk_manager
        # Injected abstraction, not the concrete registry — see the broker adapters.
        self._instruments = instruments
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
        current_side = "long" if held_long else ("short" if held else None)

        # 3. Decide the close→open plan from the shared reconcile policy — the SAME decision the
        # backtest engine uses, so a strategy trades identically live and in backtest.
        # NOTE: NEUTRAL == "go flat" (synonym for CLOSE), by design — a strategy that wants to
        # hold should return no signal, not NEUTRAL.
        actions = plan_actions(intent, current_side, allow_short)

        # Empty plan → a no-op; the reason explains which no-op it is.
        if not actions:
            if held:
                reason = "already in position"
            elif intent in (Direction.CLOSE, Direction.NEUTRAL):
                reason = "flat, no action"
            else:
                reason = "shorting disabled"   # flat + directional-short suppressed
            return [ExecutionOutcome(action=ACTION_NOOP, reason=reason)]

        # A close alongside a directional intent is a reversal; a plain CLOSE/NEUTRAL is not.
        directional = intent not in (Direction.CLOSE, Direction.NEUTRAL)
        opened = False
        outcomes: List[ExecutionOutcome] = []
        for action in actions:
            if action == CLOSE:
                outcomes.append(await self._close(
                    strategy_id, symbol, broker_id, adapter, account,
                    position, risk_cfg, latest_close, signal_id,
                    reason="reversal" if directional else "signal_close",
                ))
                position = None
            else:  # OPEN_LONG / OPEN_SHORT
                opened = True
                outcomes.append(await self._open(
                    strategy_id, symbol, broker_id, adapter, account,
                    risk_cfg, latest_close, signal_id, want_long=(action == OPEN_LONG),
                ))

        # Reversal whose opposite open was suppressed (short intent, shorting disabled): keep the
        # explicit "shorting disabled" no-op alongside the reversal close.
        if directional and intent == Direction.SHORT and not allow_short and not opened:
            outcomes.append(ExecutionOutcome(action=ACTION_NOOP, reason="shorting disabled"))
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
        # Conform to the instrument's tick/lot grid before anything downstream sees the
        # order — RiskManager must size-check the quantity that will actually be
        # submitted, never a pre-rounding one.
        conformed_qty, conformed_price = qty, latest_close
        instrument = self._instruments.get(symbol)
        if instrument is None and open_position:
            # Unseeded + opening a *new* position: fail loud, per `UnknownInstrument`'s own
            # contract ("deliberately fatal ... guessing a tick size is how orders get
            # routed to the wrong product"). An un-vetted symbol must not open a position
            # sized and rounded on guesses.
            order = Order(
                order_id=uuid.uuid4(), strategy_id=strategy_id, broker_id=broker_id,
                symbol=symbol, side=side, order_type=OrderType.MARKET, quantity=qty,
                limit_price=latest_close, signal_id=signal_id,
                metadata={"reason": close_reason} if close_reason else {},
                created_at=datetime.now(timezone.utc),
            )
            reason = (
                f"Unknown instrument '{symbol}': not in the instrument catalog, refusing "
                f"to open a position sized on guessed tick/lot. Seed it in "
                f"app/domain/instruments/seed.py."
            )
            self._log.warning("execution.instrument_unknown", symbol=symbol)
            return ExecutionOutcome(action=ACTION_REJECTED, reason=reason, order=order)
        elif instrument is None:
            # Unseeded + closing: pass through unconformed rather than blocking the exit —
            # a position already held must always be closable, even for a symbol the
            # catalog has never heard of (it predates the registry, or the seed lagged).
            self._log.warning("execution.instrument_unseeded_close", symbol=symbol)
        elif open_position:
            # Opens are validated and can be rejected — an order too small to be worth
            # the exchange's minimum should never open a position in the first place.
            try:
                conformed_qty, conformed_price = conform_order(
                    instrument, quantity=qty, price=latest_close, broker=broker_id,
                )
            except InstrumentViolation as exc:
                order = Order(
                    order_id=uuid.uuid4(), strategy_id=strategy_id, broker_id=broker_id,
                    symbol=symbol, side=side, order_type=OrderType.MARKET, quantity=qty,
                    limit_price=latest_close, signal_id=signal_id,
                    metadata={"reason": close_reason} if close_reason else {},
                    created_at=datetime.now(timezone.utc),
                )
                self._log.warning("execution.instrument_rejected", symbol=symbol,
                                  rule=exc.rule, error=str(exc))
                return ExecutionOutcome(action=ACTION_REJECTED, reason=str(exc), order=order)
        else:
            # Closes always execute — quantize only, never blocked by a min-size
            # violation the position may have drifted below (same rule as the risk veto:
            # a stop-loss/close must never be refused). Same reasoning as the ACTION_REJECTED
            # path above not applying here.
            conformed_qty = floor_to_step(qty, instrument.lot_step)
            conformed_price = round_to_tick(latest_close, instrument.tick_size)

        order = Order(
            order_id=uuid.uuid4(),
            strategy_id=strategy_id,
            broker_id=broker_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=conformed_qty,
            limit_price=conformed_price,   # reference price so RiskManager can size-check
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
                filled_quantity=order.quantity,
                avg_price=order.limit_price,
                commission=0.0,
                filled_at=datetime.now(timezone.utc),
            )
            if open_position:
                self._risk.increment_open_positions(strategy_id, +1)
            else:
                self._risk.increment_open_positions(strategy_id, -1)
                self._risk.update_daily_pnl(strategy_id, realized_pnl)

        realized = realized_pnl if (not open_position and fill is not None) else None
        return ExecutionOutcome(action=action, reason=close_reason, order=order,
                                order_result=result, fill=fill, realized_pnl=realized)
