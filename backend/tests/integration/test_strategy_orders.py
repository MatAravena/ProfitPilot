"""GET /strategies/{id}/orders — order history that feeds the live-strategy chart."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.asyncio


async def _create_tables():
    from app.db.base import engine, Base
    import app.models.db  # noqa: F401 — registers ORM models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def test_lists_orders_newest_first(client):
    from app.db.base import AsyncSessionLocal
    from app.models.db.order_record import OrderRecord
    from app.api.deps import LOCAL_USER_ID
    await _create_tables()

    strategy_id = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        s.add(OrderRecord(
            strategy_instance_id=strategy_id, user_id=LOCAL_USER_ID,
            symbol="BTCUSDT", side="buy", quantity=0.1, status="opened_long",
            filled_qty=0.1, avg_price=30000.0,
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ))
        s.add(OrderRecord(
            strategy_instance_id=strategy_id, user_id=LOCAL_USER_ID,
            symbol="BTCUSDT", side="sell", quantity=0.1, status="closed",
            filled_qty=0.1, avg_price=31000.0, realized_pnl=100.0,
            created_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
        ))
        await s.commit()

    resp = await client.get(f"/api/v1/strategies/{strategy_id}/orders")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["status"] == "closed"        # newest first
    assert data[0]["realized_pnl"] == 100.0
    assert data[1]["side"] == "buy"


async def test_unknown_strategy_returns_empty(client):
    await _create_tables()
    resp = await client.get(f"/api/v1/strategies/{uuid.uuid4()}/orders")
    assert resp.status_code == 200
    assert resp.json() == []
