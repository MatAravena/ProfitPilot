"""Built-in simulated broker for paper trading.

Fills market orders instantly at a mark price (the latest close, set per cycle),
and tracks virtual positions + cash in a DB-persisted ledger so paper strategies
survive process restarts. Implements the full BrokerAdapter interface so the
executor treats paper and live identically.

Accounting is intentionally simple for v1:
- Market orders fill fully at the mark price, zero commission/slippage.
- The engine only ever opens from flat or fully closes, so positions are never
  partially reduced here.

Ledger rows are mutated/added on the session passed in at construction and flushed
(not committed) — the executor commits once per cycle, keeping the fill and the
OrderRecord atomic.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MarketType, OrderSide, OrderStatus
from app.core.types import Account, Order, OrderResult, Position, Tick
from app.domain.broker.base import BrokerAdapter
from app.models.db.sim_ledger import SimPosition
from app.repositories.sim_ledger_repository import SimLedgerRepository

logger = structlog.get_logger(__name__)

_SIM_BROKER_ID = "sim"


class SimulatedBrokerAdapter(BrokerAdapter):
    def __init__(
        self,
        session: AsyncSession,
        strategy_id: UUID,
        user_id: UUID,
        starting_equity: float,
        market_type: MarketType = MarketType.CRYPTO,
        commission_pct: float = 0.0,
        slippage_pct: float = 0.0,
    ):
        # NB: deliberately does not call super().__init__ — there is no BrokerID
        # enum for the simulator and it is never placed in the BrokerRegistry.
        self.broker_id = _SIM_BROKER_ID
        self.paper_mode = True
        self.supported_markets = [market_type]
        self._market_type = market_type
        self._session = session
        self._repo = SimLedgerRepository(session)
        self._strategy_id = strategy_id
        self._user_id = user_id
        self._starting_equity = starting_equity
        # Cost model (mirrors BacktestEngine): adverse slippage + commission baked into the
        # effective fill price, so paper P&L matches a backtest and previews real live costs.
        # Default 0.0 keeps the adapter a pure mechanism; the executor injects the configured pcts.
        self._commission_pct = commission_pct
        self._slippage_pct = slippage_pct
        self._marks: Dict[str, float] = {}
        self._log = logger.bind(broker=_SIM_BROKER_ID, strategy_id=str(strategy_id))

    # ── Executor hook ────────────────────────────────────────────────────────────

    def set_mark(self, symbol: str, price: float) -> None:
        self._marks[symbol] = price

    def _mark_for(self, symbol: str, fallback: float) -> float:
        return self._marks.get(symbol, fallback)

    # ── BrokerAdapter interface ──────────────────────────────────────────────────

    def _effective_fill(self, base: float, side: OrderSide) -> float:
        """Fill price with costs baked in (same model as BacktestEngine): adverse slippage then
        commission. A BUY pays base·(1+slip)·(1+comm); a SELL receives base·(1-slip)·(1-comm).
        Folding both into the price keeps all downstream cash/P&L accounting unchanged."""
        if side == OrderSide.BUY:
            return base * (1 + self._slippage_pct) * (1 + self._commission_pct)
        return base * (1 - self._slippage_pct) * (1 - self._commission_pct)

    async def place_order(self, order: Order) -> OrderResult:
        base = self._marks.get(order.symbol) or order.limit_price
        if not base or base <= 0:
            raise ValueError(f"No mark price available for {order.symbol}")
        fill_price = self._effective_fill(base, order.side)

        acc = await self._get_or_create_account()
        pos = await self._repo.get_position(self._strategy_id, order.symbol)

        signed = order.quantity if order.side == OrderSide.BUY else -order.quantity
        # Cash: buying spends, selling receives.
        acc.cash -= signed * fill_price

        current_qty = pos.quantity if pos else 0.0
        new_qty = current_qty + signed

        if pos is None:
            # Opening from flat.
            self._repo.add_position(SimPosition(
                strategy_instance_id=self._strategy_id,
                user_id=self._user_id,
                symbol=order.symbol,
                quantity=signed,
                avg_entry_price=fill_price,
            ))
        elif abs(new_qty) < 1e-12:
            # Fully closed → realize P&L and drop the position.
            acc.realized_pnl += (fill_price - pos.avg_entry_price) * current_qty
            await self._repo.delete_position(pos)
        elif (current_qty > 0) == (signed > 0):
            # Same-direction add → weighted-average entry.
            pos.avg_entry_price = (
                pos.avg_entry_price * current_qty + fill_price * signed
            ) / new_qty
            pos.quantity = new_qty
        else:
            # Partial reduce (not produced by the engine today) — realize proportionally.
            acc.realized_pnl += (fill_price - pos.avg_entry_price) * (-signed)
            pos.quantity = new_qty

        await self._session.flush()

        return OrderResult(
            order_id=order.order_id,
            broker_order_id=f"sim-{order.order_id}",
            status=OrderStatus.FILLED,
            submitted_at=datetime.now(timezone.utc),
        )

    async def get_positions(self) -> List[Position]:
        rows = await self._repo.get_positions(self._strategy_id)
        out: List[Position] = []
        for r in rows:
            mark = self._mark_for(r.symbol, r.avg_entry_price)
            unrealized = (mark - r.avg_entry_price) * r.quantity
            pct = (mark / r.avg_entry_price - 1.0) if r.avg_entry_price else 0.0
            out.append(Position(
                symbol=r.symbol,
                market_type=self._market_type,
                broker_id=_SIM_BROKER_ID,
                quantity=r.quantity,
                avg_entry_price=r.avg_entry_price,
                current_price=mark,
                unrealized_pnl=unrealized,
                unrealized_pnl_pct=pct if r.quantity > 0 else -pct,
                opened_at=r.opened_at,
            ))
        return out

    async def get_account(self) -> Account:
        acc = await self._get_or_create_account()
        positions = await self._repo.get_positions(self._strategy_id)
        holdings_value = sum(
            self._mark_for(p.symbol, p.avg_entry_price) * p.quantity for p in positions
        )
        equity = acc.cash + holdings_value
        return Account(
            broker_id=_SIM_BROKER_ID,
            account_id=str(self._strategy_id),
            equity=equity,
            cash=acc.cash,
            buying_power=max(acc.cash, 0.0),
            paper_mode=True,
            updated_at=datetime.now(timezone.utc),
        )

    async def _get_or_create_account(self):
        acc = await self._repo.get_account(self._strategy_id)
        if acc is None:
            acc = await self._repo.create_account(
                self._strategy_id, self._user_id, self._starting_equity
            )
        return acc

    # ── Unused-for-paper stubs ───────────────────────────────────────────────────

    async def cancel_order(self, broker_order_id: str) -> bool:
        return True

    async def get_market_data(self, symbol: str, timeframe: str, limit: int = 200) -> List[dict]:
        return []

    async def stream_ticks(self, symbol: str) -> AsyncGenerator[Tick, None]:
        if False:  # pragma: no cover - simulator has no live stream
            yield  # type: ignore[misc]

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def health_check(self) -> bool:
        return True
