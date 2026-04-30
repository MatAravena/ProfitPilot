from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Optional, Union
from uuid import UUID

import structlog

from app.core.types import Account, Order, RiskConfig, RiskVeto

logger = structlog.get_logger(__name__)


@dataclass
class RiskState:
    """Mutable per-strategy risk state tracked at runtime."""
    strategy_id: UUID
    daily_pnl: float = 0.0
    total_pnl: float = 0.0
    peak_equity: float = 0.0
    open_position_count: int = 0
    orders_this_minute: int = 0
    last_order_minute: Optional[int] = None   # minute-of-day
    halted: bool = False
    halt_reason: Optional[str] = None
    last_updated: datetime = field(default_factory=datetime.utcnow)


class RiskManager:
    """
    Hard veto layer — sits between strategy signals and broker execution.

    Every order must pass through `approve_order()` before reaching a BrokerAdapter.
    This is non-negotiable and cannot be bypassed in production.

    The RiskManager:
    - Validates position sizing
    - Enforces max open positions
    - Tracks and enforces daily + total drawdown limits
    - Enforces order rate limits (throttle runaway strategies)
    - Triggers kill switch on breaches
    - Never modifies orders — it either approves or vetoes
    """

    def __init__(self):
        self._states: Dict[UUID, RiskState] = {}
        self._log = logger.bind(component="RiskManager")

    # ── Main Entry Point ───────────────────────────────────────────────────────

    async def approve_order(
        self,
        order: Order,
        account: Account,
        risk_config: RiskConfig,
    ) -> Union[bool, RiskVeto]:
        """
        Returns True if the order is approved.
        Returns a RiskVeto if the order is rejected — includes the reason.

        Callers must check the return type:
            result = await risk_manager.approve_order(order, account, config)
            if isinstance(result, RiskVeto):
                log and discard the order
        """
        state = self._get_or_create_state(order.strategy_id, account)

        # Kill switch check — no orders if halted
        if state.halted:
            return RiskVeto(
                order_id=order.order_id,
                reason=f"Strategy is halted: {state.halt_reason}",
                rule_violated="kill_switch",
                current_value=1.0,
                limit_value=0.0,
            )

        # Run all checks in sequence — first failure returns a veto
        checks = [
            self._check_position_size(order, account, risk_config),
            self._check_max_positions(state, risk_config),
            self._check_daily_drawdown(state, account, risk_config),
            self._check_total_drawdown(state, account, risk_config),
            self._check_order_rate(state, risk_config),
        ]

        for veto in checks:
            if veto is not None:
                self._log.warning(
                    "risk.order_vetoed",
                    strategy_id=str(order.strategy_id),
                    rule=veto.rule_violated,
                    reason=veto.reason,
                )
                # Trigger halt if it's a drawdown breach
                if "drawdown" in veto.rule_violated and risk_config.kill_switch_enabled:
                    self._halt_strategy(state, veto.reason)
                return veto

        # All checks passed
        self._log.info(
            "risk.order_approved",
            strategy_id=str(order.strategy_id),
            symbol=order.symbol,
            side=order.side.value,
            qty=order.quantity,
        )
        return True

    # ── State Updates (call after fills/PnL updates) ───────────────────────────

    def update_daily_pnl(self, strategy_id: UUID, pnl_delta: float) -> None:
        if strategy_id not in self._states:
            return
        state = self._states[strategy_id]
        state.daily_pnl += pnl_delta
        state.total_pnl += pnl_delta
        state.last_updated = datetime.utcnow()

    def increment_open_positions(self, strategy_id: UUID, delta: int = 1) -> None:
        if strategy_id in self._states:
            self._states[strategy_id].open_position_count += delta

    def reset_daily_state(self, strategy_id: UUID) -> None:
        """Call at the start of each trading day."""
        if strategy_id in self._states:
            self._states[strategy_id].daily_pnl = 0.0
            self._log.info("risk.daily_reset", strategy_id=str(strategy_id))

    def release_halt(self, strategy_id: UUID, authorized_by: str) -> None:
        """
        Manually release a halted strategy.
        Requires explicit authorization — never auto-released.
        """
        if strategy_id in self._states:
            self._states[strategy_id].halted = False
            self._states[strategy_id].halt_reason = None
            self._log.warning("risk.halt_released", strategy_id=str(strategy_id), by=authorized_by)

    # ── Private Checks ─────────────────────────────────────────────────────────

    def _check_position_size(
        self,
        order: Order,
        account: Account,
        config: RiskConfig,
    ) -> Optional[RiskVeto]:
        if order.quantity <= 0:
            return RiskVeto(
                order_id=order.order_id,
                reason="Order quantity must be positive",
                rule_violated="invalid_quantity",
                current_value=order.quantity,
                limit_value=0.0,
            )

        # Estimate order notional — use limit price if available
        estimated_price = order.limit_price or 0.0
        if estimated_price > 0:
            notional = order.quantity * estimated_price
            max_notional = account.equity * config.max_position_size_pct
            if notional > max_notional:
                return RiskVeto(
                    order_id=order.order_id,
                    reason=f"Order notional ${notional:.2f} exceeds max position size ${max_notional:.2f}",
                    rule_violated="max_position_size_pct",
                    current_value=notional,
                    limit_value=max_notional,
                )
        return None

    def _check_max_positions(
        self,
        state: RiskState,
        config: RiskConfig,
    ) -> Optional[RiskVeto]:
        if state.open_position_count >= config.max_open_positions:
            return RiskVeto(
                order_id=UUID(int=0),    # placeholder — filled by caller
                reason=f"Max open positions ({config.max_open_positions}) reached",
                rule_violated="max_open_positions",
                current_value=float(state.open_position_count),
                limit_value=float(config.max_open_positions),
            )
        return None

    def _check_daily_drawdown(
        self,
        state: RiskState,
        account: Account,
        config: RiskConfig,
    ) -> Optional[RiskVeto]:
        daily_dd = state.daily_pnl / account.equity if account.equity > 0 else 0.0
        if daily_dd < -config.max_daily_drawdown_pct:
            return RiskVeto(
                order_id=UUID(int=0),
                reason=f"Daily drawdown {daily_dd:.2%} exceeded limit {-config.max_daily_drawdown_pct:.2%}",
                rule_violated="max_daily_drawdown",
                current_value=abs(daily_dd),
                limit_value=config.max_daily_drawdown_pct,
            )
        return None

    def _check_total_drawdown(
        self,
        state: RiskState,
        account: Account,
        config: RiskConfig,
    ) -> Optional[RiskVeto]:
        if state.peak_equity <= 0:
            return None
        dd = (state.peak_equity - account.equity) / state.peak_equity
        if dd > config.max_total_drawdown_pct:
            return RiskVeto(
                order_id=UUID(int=0),
                reason=f"Total drawdown {dd:.2%} exceeded limit {config.max_total_drawdown_pct:.2%}",
                rule_violated="max_total_drawdown",
                current_value=dd,
                limit_value=config.max_total_drawdown_pct,
            )
        return None

    def _check_order_rate(
        self,
        state: RiskState,
        config: RiskConfig,
    ) -> Optional[RiskVeto]:
        current_minute = datetime.utcnow().hour * 60 + datetime.utcnow().minute
        if state.last_order_minute != current_minute:
            state.orders_this_minute = 0
            state.last_order_minute = current_minute

        state.orders_this_minute += 1

        if state.orders_this_minute > config.max_orders_per_minute:
            return RiskVeto(
                order_id=UUID(int=0),
                reason=f"Order rate {state.orders_this_minute}/min exceeds limit {config.max_orders_per_minute}/min",
                rule_violated="max_orders_per_minute",
                current_value=float(state.orders_this_minute),
                limit_value=float(config.max_orders_per_minute),
            )
        return None

    def _halt_strategy(self, state: RiskState, reason: str) -> None:
        state.halted = True
        state.halt_reason = reason
        self._log.warning("risk.strategy_halted", strategy_id=str(state.strategy_id), reason=reason)

    def _get_or_create_state(self, strategy_id: UUID, account: Account) -> RiskState:
        if strategy_id not in self._states:
            self._states[strategy_id] = RiskState(
                strategy_id=strategy_id,
                peak_equity=account.equity,
            )
        else:
            state = self._states[strategy_id]
            if account.equity > state.peak_equity:
                state.peak_equity = account.equity
        return self._states[strategy_id]
