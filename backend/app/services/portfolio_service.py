from __future__ import annotations
import asyncio
from typing import List
from uuid import UUID

import structlog

from app.core.types import Account, Position
from app.models.schemas.broker_schemas import PortfolioSummaryResponse, PositionResponse, AccountResponse
from app.services.broker_service import BrokerService

logger = structlog.get_logger(__name__)


class PortfolioService:
    def __init__(self, broker_service: BrokerService):
        self._brokers = broker_service

    async def get_summary(self, user_id: UUID) -> PortfolioSummaryResponse:
        adapters = await self._brokers.get_all_adapters(user_id)
        if not adapters:
            return PortfolioSummaryResponse(
                total_equity=0.0,
                total_cash=0.0,
                total_unrealized_pnl=0.0,
                positions=[],
                accounts=[],
            )

        # Fan out to all connected brokers in parallel
        async def fetch(adapter):
            await adapter.connect()
            try:
                account, positions = await asyncio.gather(
                    adapter.get_account(),
                    adapter.get_positions(),
                )
                return account, positions
            except Exception as exc:
                logger.error("portfolio.fetch.failed", broker=adapter.broker_id.value, error=str(exc))
                return None, []
            finally:
                await adapter.disconnect()

        results = await asyncio.gather(*[fetch(a) for a in adapters])

        accounts: List[Account] = []
        all_positions: List[Position] = []
        for account, positions in results:
            if account:
                accounts.append(account)
            all_positions.extend(positions)

        total_equity = sum(a.equity for a in accounts)
        total_cash = sum(a.cash for a in accounts)
        total_unrealized_pnl = sum(p.unrealized_pnl for p in all_positions)

        return PortfolioSummaryResponse(
            total_equity=total_equity,
            total_cash=total_cash,
            total_unrealized_pnl=total_unrealized_pnl,
            positions=[_map_position(p) for p in all_positions],
            accounts=[_map_account(a) for a in accounts],
        )

    async def get_positions(self, user_id: UUID) -> List[PositionResponse]:
        summary = await self.get_summary(user_id)
        return summary.positions


def _map_position(p: Position) -> PositionResponse:
    return PositionResponse(
        symbol=p.symbol,
        market_type=p.market_type.value,
        broker_id=p.broker_id,
        quantity=p.quantity,
        avg_entry_price=p.avg_entry_price,
        current_price=p.current_price,
        unrealized_pnl=p.unrealized_pnl,
        unrealized_pnl_pct=p.unrealized_pnl_pct,
        opened_at=p.opened_at,
    )


def _map_account(a: Account) -> AccountResponse:
    return AccountResponse(
        broker_id=a.broker_id,
        account_id=a.account_id,
        equity=a.equity,
        cash=a.cash,
        buying_power=a.buying_power,
        paper_mode=a.paper_mode,
        currency=a.currency,
        updated_at=a.updated_at,
    )
