from __future__ import annotations
import asyncio
import json
import uuid

import structlog
from fastapi import APIRouter
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.api.deps import LOCAL_USER_ID
from app.api.ws.manager import manager

logger = structlog.get_logger(__name__)

router = APIRouter()

# How often to push portfolio snapshots to subscribed clients (seconds)
_PORTFOLIO_PUSH_INTERVAL = 15


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    client_id = str(uuid.uuid4())
    await manager.connect(ws, client_id)

    # Auto-subscribe new clients to portfolio and strategy channels
    manager.subscribe(client_id, "portfolio.snapshot")
    manager.subscribe(client_id, "strategy.status")

    # Kick off a per-connection portfolio push loop
    push_task = asyncio.create_task(_portfolio_push_loop(client_id))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")
            channel = msg.get("channel", "")

            if msg_type == "subscribe":
                manager.subscribe(client_id, channel)
            elif msg_type == "unsubscribe":
                manager.unsubscribe(client_id, channel)
            elif msg_type == "ping":
                await manager.send(client_id, "pong", {})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("ws.error", client_id=client_id, error=str(exc))
    finally:
        push_task.cancel()
        manager.disconnect(client_id)


async def _portfolio_push_loop(client_id: str) -> None:
    """Push a portfolio snapshot to a single client every N seconds."""
    await asyncio.sleep(1)  # small delay so the connection is fully established
    while True:
        try:
            snapshot = await _build_portfolio_snapshot()
            await manager.send(client_id, "portfolio.snapshot", snapshot)
        except Exception as exc:
            logger.warning("ws.portfolio_push_failed", client_id=client_id, error=str(exc))
        await asyncio.sleep(_PORTFOLIO_PUSH_INTERVAL)


async def _build_portfolio_snapshot() -> dict:
    """
    Build a lightweight portfolio snapshot.
    Returns zeros when no broker is connected — the frontend handles this gracefully.
    """
    from app.db.base import AsyncSessionLocal
    from app.repositories.broker_connection_repository import BrokerConnectionRepository
    from app.services.broker_service import BrokerService
    from app.services.portfolio_service import PortfolioService
    import time

    async with AsyncSessionLocal() as session:
        repo = BrokerConnectionRepository(session)
        broker_svc = BrokerService(repo)
        portfolio_svc = PortfolioService(broker_svc)

        try:
            summary = await portfolio_svc.get_summary(LOCAL_USER_ID)
            positions = [
                {
                    "symbol": p.symbol,
                    "market_type": p.market_type,
                    "broker_id": p.broker_id,
                    "quantity": p.quantity,
                    "avg_entry_price": p.avg_entry_price,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "unrealized_pnl_pct": p.unrealized_pnl_pct,
                    "opened_at": p.opened_at.isoformat(),
                }
                for p in summary.positions
            ]
            return {
                "equity": summary.total_equity,
                "cashBalance": summary.total_cash,
                "dailyPnl": 0.0,  # TODO: calculate from snapshots
                "totalPnl": summary.total_unrealized_pnl,
                "drawdown": 0.0,
                "positions": positions,
                "updatedAt": int(time.time()),
            }
        except Exception:
            # No broker connected or broker API error — return zeroes
            return {
                "equity": 0.0,
                "cashBalance": 0.0,
                "dailyPnl": 0.0,
                "totalPnl": 0.0,
                "drawdown": 0.0,
                "positions": [],
                "updatedAt": int(time.time()),
            }
