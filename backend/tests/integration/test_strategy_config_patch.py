"""PATCH /strategies/{id}/config must be a PARTIAL update — omitted fields keep
their current value instead of silently resetting to schema defaults."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def _create_tables():
    from app.db.base import engine, Base
    import app.models.db  # noqa: F401 — registers ORM models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _create_strategy(client, execution: dict) -> dict:
    resp = await client.post("/api/v1/strategies", json={
        "class_name": "AlwaysLong", "symbol": "BTCUSDT", "timeframe": "1d",
        "parameters": {}, "execution": execution,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_patch_config_updates_only_provided_fields(client):
    await _create_tables()
    created = await _create_strategy(client, {
        "size_pct": 0.05, "allow_short": False,
        "stop_loss_pct": 0.02, "take_profit_pct": 0.04,
    })
    sid = created["id"]
    assert created["execution"]["allow_short"] is False
    assert created["execution"]["stop_loss_pct"] == 0.02

    # Partial PATCH: only size_pct — everything else must be preserved.
    resp = await client.patch(f"/api/v1/strategies/{sid}/config", json={"size_pct": 0.08})
    assert resp.status_code == 200, resp.text
    execution = resp.json()["execution"]

    assert execution["size_pct"] == 0.08          # updated
    assert execution["allow_short"] is False       # preserved (bug would reset to True)
    assert execution["stop_loss_pct"] == 0.02      # preserved (bug would reset to None)
    assert execution["take_profit_pct"] == 0.04    # preserved


async def test_patch_config_can_clear_a_risk_override(client):
    """Explicitly sending null clears a risk override (revert to profile inherit)."""
    await _create_tables()
    created = await _create_strategy(client, {"stop_loss_pct": 0.02})
    sid = created["id"]
    assert created["execution"]["stop_loss_pct"] == 0.02

    resp = await client.patch(f"/api/v1/strategies/{sid}/config", json={"stop_loss_pct": None})
    assert resp.status_code == 200, resp.text
    assert resp.json()["execution"]["stop_loss_pct"] is None


async def test_risk_per_trade_is_saved_and_reaches_the_live_risk_config(client):
    """Risk-mode sizing is a per-strategy setting: saved via the API, carried into the
    RiskConfig the executor sizes with, and cleared back to fixed sizing with null."""
    await _create_tables()
    created = await _create_strategy(client, {"size_pct": 1.0, "stop_loss_pct": 0.10})
    sid = created["id"]
    assert created["execution"]["risk_per_trade_pct"] is None

    resp = await client.patch(f"/api/v1/strategies/{sid}/config", json={"risk_per_trade_pct": 0.005})
    assert resp.status_code == 200, resp.text
    assert resp.json()["execution"]["risk_per_trade_pct"] == 0.005

    from uuid import UUID
    from app.db.base import AsyncSessionLocal
    from app.models.db.strategy_instance import StrategyInstance
    from app.services.strategy_executor import StrategyExecutor
    async with AsyncSessionLocal() as session:
        inst = await session.get(StrategyInstance, UUID(sid))
        cfg = await StrategyExecutor()._build_risk_cfg(session, inst)
    assert cfg.risk_per_trade_pct == 0.005 and cfg.max_position_size_pct == 1.0

    resp = await client.patch(f"/api/v1/strategies/{sid}/config", json={"risk_per_trade_pct": None})
    assert resp.json()["execution"]["risk_per_trade_pct"] is None


async def test_risk_per_trade_above_ten_percent_is_rejected(client):
    await _create_tables()
    sid = (await _create_strategy(client, {}))["id"]
    resp = await client.patch(f"/api/v1/strategies/{sid}/config", json={"risk_per_trade_pct": 0.5})
    assert resp.status_code == 422
