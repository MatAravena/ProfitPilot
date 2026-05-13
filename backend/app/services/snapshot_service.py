from __future__ import annotations
import asyncio
import uuid
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger(__name__)

_SNAPSHOT_INTERVAL = 60  # seconds between portfolio snapshots


async def portfolio_snapshot_loop(session_factory, user_id: uuid.UUID) -> None:
    """
    Periodically fetches portfolio summary and persists a snapshot row.
    Runs as a background asyncio task.
    Powers the P&L-over-time graph in the Portfolio page.
    """
    await asyncio.sleep(5)  # let startup settle

    while True:
        try:
            await _take_snapshot(session_factory, user_id)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("snapshot.error", error=str(exc))

        try:
            await asyncio.sleep(_SNAPSHOT_INTERVAL)
        except asyncio.CancelledError:
            break


async def _take_snapshot(session_factory, user_id: uuid.UUID) -> None:
    from app.db.base import AsyncSessionLocal
    from app.models.db.portfolio_snapshot import PortfolioSnapshot
    from app.repositories.broker_connection_repository import BrokerConnectionRepository
    from app.services.broker_service import BrokerService
    from app.services.portfolio_service import PortfolioService

    async with session_factory() as session:
        repo = BrokerConnectionRepository(session)
        broker_svc = BrokerService(repo)
        portfolio_svc = PortfolioService(broker_svc)

        try:
            summary = await portfolio_svc.get_summary(user_id)
            if summary.total_equity == 0.0:
                return  # No broker connected — skip
        except Exception:
            return

        snap = PortfolioSnapshot(
            id=uuid.uuid4(),
            user_id=user_id,
            equity=summary.total_equity,
            cash=summary.total_cash,
            unrealized_pnl=summary.total_unrealized_pnl,
            snapped_at=datetime.now(timezone.utc),
        )
        session.add(snap)
        await session.commit()
        logger.debug("snapshot.saved", equity=summary.total_equity)
