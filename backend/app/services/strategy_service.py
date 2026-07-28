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
        # Partial update: only touch fields the client actually sent. Omitted fields
        # keep their current value; an explicit null clears a risk override. Sending
        # the full config (the current UI) still replaces everything, as before.
        provided = cfg.model_dump(exclude_unset=True)
        for field in _CONFIG_FIELDS:
            if field in provided:
                setattr(instance, field, provided[field])
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


# ExecutionConfig fields map 1:1 onto StrategyInstance columns (same names). The
# ExecutionConfig model is the single source of truth for this field set, so the list is
# derived from it rather than hand-maintained; test_execution_config_fields_map_to_orm_columns
# asserts every field has a matching column.
_CONFIG_FIELDS: tuple[str, ...] = tuple(ExecutionConfig.model_fields)


def _config_columns(cfg: ExecutionConfig) -> dict:
    """Map an ExecutionConfig onto the StrategyInstance column names (used on create)."""
    return {field: getattr(cfg, field) for field in _CONFIG_FIELDS}
