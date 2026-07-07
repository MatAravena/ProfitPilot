from __future__ import annotations
from datetime import datetime, timezone
from typing import List
from uuid import UUID, uuid4

from app.models.db.strategy_instance import StrategyInstance
from app.models.schemas.strategy_schemas import CreateStrategyRequest, ExecutionConfig
from app.repositories.strategy_instance_repository import StrategyInstanceRepository


class StrategyService:
    def __init__(self, repo: StrategyInstanceRepository):
        self._repo = repo

    async def list(self, user_id: UUID) -> List[StrategyInstance]:
        return await self._repo.list_by_user(user_id)

    async def create(self, user_id: UUID, req: CreateStrategyRequest) -> StrategyInstance:
        cfg = req.execution
        instance = StrategyInstance(
            id=uuid4(),
            user_id=user_id,
            class_name=req.class_name,
            label=req.label or req.class_name,
            symbol=req.symbol.upper(),
            timeframe=req.timeframe,
            broker_connection_id=req.broker_connection_id,
            status="draft",
            parameters=req.parameters,
            **_config_columns(cfg),
        )
        return await self._repo.add(instance)

    async def update_config(self, id: UUID, user_id: UUID, cfg: ExecutionConfig) -> StrategyInstance:
        instance = await self._repo.get_by_user(id, user_id)
        if instance is None:
            raise KeyError(f"Strategy {id} not found")
        for field, value in _config_columns(cfg).items():
            setattr(instance, field, value)
        instance.updated_at = datetime.now(timezone.utc)
        await self._repo._session.flush()
        await self._repo._session.refresh(instance)
        return instance

    async def update_status(self, id: UUID, user_id: UUID, status: str) -> StrategyInstance:
        instance = await self._repo.get_by_user(id, user_id)
        if instance is None:
            raise KeyError(f"Strategy {id} not found")
        instance.status = status
        instance.updated_at = datetime.now(timezone.utc)
        await self._repo._session.flush()
        await self._repo._session.refresh(instance)
        return instance

    async def delete(self, id: UUID, user_id: UUID) -> None:
        instance = await self._repo.get_by_user(id, user_id)
        if instance is None:
            raise KeyError(f"Strategy {id} not found")
        await self._repo.delete(instance)


def _config_columns(cfg: ExecutionConfig) -> dict:
    """Map an ExecutionConfig onto the StrategyInstance column names."""
    return {
        "size_pct": cfg.size_pct,
        "stop_loss_pct": cfg.stop_loss_pct,
        "take_profit_pct": cfg.take_profit_pct,
        "max_open_positions": cfg.max_open_positions,
        "max_daily_drawdown_pct": cfg.max_daily_drawdown_pct,
        "max_total_drawdown_pct": cfg.max_total_drawdown_pct,
        "max_orders_per_minute": cfg.max_orders_per_minute,
        "allow_short": cfg.allow_short,
        "kill_switch_enabled": cfg.kill_switch_enabled,
        "poll_seconds": cfg.poll_seconds,
    }
