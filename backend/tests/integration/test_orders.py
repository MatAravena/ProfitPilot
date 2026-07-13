"""GET /orders — user-wide paginated order history for the Portfolio page."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.asyncio


async def _reset_and_seed(n: int):
    """Clean the order_records table (shared in-memory DB) and seed n rows."""
    from sqlalchemy import delete
    from app.db.base import engine, AsyncSessionLocal, Base
    import app.models.db  # noqa: F401 — registers ORM models
    from app.models.db.order_record import OrderRecord
    from app.api.deps import LOCAL_USER_ID

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as s:
        await s.execute(delete(OrderRecord))
        for i in range(n):
            s.add(OrderRecord(
                strategy_instance_id=uuid.uuid4(), user_id=LOCAL_USER_ID,
                symbol="BTCUSDT", side="buy" if i % 2 == 0 else "sell",
                quantity=0.1, status="opened_long", filled_qty=0.1, avg_price=30000.0 + i,
                created_at=datetime(2024, 1, 1 + i, tzinfo=timezone.utc),
            ))
        await s.commit()


async def test_orders_paginated_newest_first(client):
    await _reset_and_seed(3)

    resp = await client.get("/api/v1/orders?limit=2&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    # Newest first: seeded created_at increases with i, so the last seeded is first.
    assert body["items"][0]["avg_price"] == 30002.0

    resp2 = await client.get("/api/v1/orders?limit=2&offset=2")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["total"] == 3
    assert len(body2["items"]) == 1
    assert body2["items"][0]["avg_price"] == 30000.0


async def test_orders_empty(client):
    await _reset_and_seed(0)
    resp = await client.get("/api/v1/orders")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"items": [], "total": 0}
