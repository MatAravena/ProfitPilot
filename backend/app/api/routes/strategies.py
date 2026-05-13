from __future__ import annotations
from typing import Annotated, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import LOCAL_USER_ID, get_db
from app.domain.strategy.loader import get_all_strategy_classes
from app.models.schemas.strategy_schemas import (
    CreateStrategyRequest,
    StrategyInstanceResponse,
    UpdateStrategyStatusRequest,
)
from app.repositories.strategy_instance_repository import StrategyInstanceRepository
from app.services.strategy_service import StrategyService

router = APIRouter(prefix="/strategies", tags=["strategies"])


def _get_service(db: Annotated[AsyncSession, Depends(get_db)]) -> StrategyService:
    return StrategyService(StrategyInstanceRepository(db))


@router.get("/classes")
async def list_strategy_classes():
    return get_all_strategy_classes()


@router.get("", response_model=List[StrategyInstanceResponse])
async def list_strategies(svc: Annotated[StrategyService, Depends(_get_service)]):
    return await svc.list(LOCAL_USER_ID)


@router.post("", response_model=StrategyInstanceResponse, status_code=201)
async def create_strategy(
    body: CreateStrategyRequest,
    svc: Annotated[StrategyService, Depends(_get_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    instance = await svc.create(LOCAL_USER_ID, body)
    await db.commit()
    return instance


@router.patch("/{strategy_id}/status", response_model=StrategyInstanceResponse)
async def update_strategy_status(
    strategy_id: UUID,
    body: UpdateStrategyStatusRequest,
    svc: Annotated[StrategyService, Depends(_get_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from app.db.base import AsyncSessionLocal
    from app.services.strategy_executor import executor

    try:
        instance = await svc.update_status(strategy_id, LOCAL_USER_ID, body.status)
        await db.commit()
        # Start or stop the execution loop for this strategy
        executor.notify_status_change(instance, AsyncSessionLocal)
        return instance
    except KeyError:
        raise HTTPException(status_code=404, detail="Strategy not found")


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(
    strategy_id: UUID,
    svc: Annotated[StrategyService, Depends(_get_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        await svc.delete(strategy_id, LOCAL_USER_ID)
        await db.commit()
    except KeyError:
        raise HTTPException(status_code=404, detail="Strategy not found")
