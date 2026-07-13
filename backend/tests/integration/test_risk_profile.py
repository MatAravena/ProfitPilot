"""Phase 1: per-user risk profile (DB + service + endpoints)."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models.db  # noqa: F401 — registers models
from app.db.base import Base
from app.models.db.user import User
from app.models.schemas.risk_schemas import RiskProfileSchema
from app.repositories.risk_profile_repository import RiskProfileRepository
from app.services.risk_profile_service import RiskProfileService

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture()
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid.uuid4()
    async with factory() as s:
        s.add(User(id=user_id, email="t@t.com", username="t", hashed_password="x"))
        await s.commit()
    yield factory, user_id
    await engine.dispose()


async def test_get_or_create_seeds_defaults(db):
    factory, user_id = db
    async with factory() as s:
        svc = RiskProfileService(RiskProfileRepository(s))
        profile = await svc.get_or_create(user_id)
        await s.commit()
        assert profile.stop_loss_pct == pytest.approx(0.015)
        assert profile.max_open_positions == 5
        assert profile.kill_switch_enabled is True


async def test_get_or_create_is_idempotent(db):
    factory, user_id = db
    async with factory() as s:
        svc = RiskProfileService(RiskProfileRepository(s))
        p1 = await svc.get_or_create(user_id)
        await s.commit()
    async with factory() as s:
        svc = RiskProfileService(RiskProfileRepository(s))
        p2 = await svc.get_or_create(user_id)
        assert p2.id == p1.id      # no duplicate row


async def test_update_persists_changes(db):
    factory, user_id = db
    async with factory() as s:
        svc = RiskProfileService(RiskProfileRepository(s))
        updated = await svc.update(user_id, RiskProfileSchema(
            stop_loss_pct=0.02, take_profit_pct=0.05, max_open_positions=3,
        ))
        await s.commit()
        assert updated.stop_loss_pct == pytest.approx(0.02)
        assert updated.take_profit_pct == pytest.approx(0.05)
        assert updated.max_open_positions == 3


async def test_from_profile_does_not_revalidate(db):
    from types import SimpleNamespace
    legacy = SimpleNamespace(
        stop_loss_pct=0.0, take_profit_pct=0.0, max_open_positions=0,
        max_daily_drawdown_pct=0.0, max_total_drawdown_pct=0.0,
        max_orders_per_minute=0, kill_switch_enabled=True,
    )
    schema = RiskProfileSchema.from_profile(legacy)   # would raise under input validation
    assert schema.stop_loss_pct == 0.0
