"""A user can hold a paper (testnet) and a live connection for the same broker at
once — connecting one must not silently kill the other, and account/position/order
routes must address a specific connection, not guess between two same-broker ones."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.deps import LOCAL_USER_ID

pytestmark = pytest.mark.asyncio

API = "/api/v1"


async def _create_tables_and_seed_user():
    from sqlalchemy import delete
    from app.db.base import engine, Base, AsyncSessionLocal
    import app.models.db  # noqa: F401 — registers ORM models
    from app.models.db.user import User
    from app.models.db.broker_connection import BrokerConnection

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as s:
        await s.execute(delete(BrokerConnection))
        if await s.get(User, LOCAL_USER_ID) is None:
            s.add(User(id=LOCAL_USER_ID, email="local@profitpilot.dev",
                        username="local", hashed_password="x"))
        await s.commit()


class _FakeAdapter:
    """Stands in for BybitAdapter — equity differs by is_paper so tests can tell
    which connection a route actually resolved."""

    def __init__(self, conn):
        self._conn = conn
        self.broker_id = SimpleNamespace(value=conn.broker_id)

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def get_account(self):
        from app.core.types import Account
        equity = 1_000.0 if self._conn.is_paper else 50_000.0
        return Account(
            broker_id=self._conn.broker_id, account_id=str(self._conn.id), equity=equity,
            cash=equity, buying_power=equity, paper_mode=self._conn.is_paper,
            currency="USDT", updated_at=datetime.now(timezone.utc),
        )

    async def get_positions(self):
        return []


def _connect_payload(is_paper: bool, key: str) -> dict:
    return {"broker_id": "bybit", "api_key": key, "secret_key": key, "is_paper": is_paper}


async def test_paper_and_live_bybit_connections_coexist(client, monkeypatch):
    await _create_tables_and_seed_user()
    monkeypatch.setattr("app.services.broker_service._build_adapter", lambda conn: _FakeAdapter(conn))

    paper = await client.post(f"{API}/brokers", json=_connect_payload(True, "testnet-key"))
    live = await client.post(f"{API}/brokers", json=_connect_payload(False, "mainnet-key"))
    assert paper.status_code == 201, paper.text
    assert live.status_code == 201, live.text

    listing = (await client.get(f"{API}/brokers")).json()
    by_id = {c["id"]: c["is_paper"] for c in listing}
    assert by_id == {paper.json()["id"]: True, live.json()["id"]: False}

    paper_acct = await client.get(f"{API}/brokers/{paper.json()['id']}/account")
    live_acct = await client.get(f"{API}/brokers/{live.json()['id']}/account")
    assert paper_acct.json()["equity"] == 1_000.0
    assert live_acct.json()["equity"] == 50_000.0


async def test_reconnecting_one_mode_leaves_the_other_untouched(client, monkeypatch):
    await _create_tables_and_seed_user()
    monkeypatch.setattr("app.services.broker_service._build_adapter", lambda conn: _FakeAdapter(conn))

    paper1 = await client.post(f"{API}/brokers", json=_connect_payload(True, "p1"))
    live = await client.post(f"{API}/brokers", json=_connect_payload(False, "l1"))
    paper2 = await client.post(f"{API}/brokers", json=_connect_payload(True, "p2"))
    assert paper2.status_code == 201

    active_ids = {c["id"] for c in (await client.get(f"{API}/brokers")).json()}
    assert paper1.json()["id"] not in active_ids   # replaced by paper2, same mode
    assert live.json()["id"] in active_ids          # different mode — untouched
    assert paper2.json()["id"] in active_ids

    stale = await client.get(f"{API}/brokers/{paper1.json()['id']}/account")
    assert stale.status_code == 404
