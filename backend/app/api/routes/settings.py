from __future__ import annotations
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import LOCAL_USER_ID, get_db
from app.models.schemas.risk_schemas import RiskProfileSchema
from app.repositories.risk_profile_repository import RiskProfileRepository
from app.services.risk_profile_service import RiskProfileService

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_service(db: Annotated[AsyncSession, Depends(get_db)]) -> RiskProfileService:
    return RiskProfileService(RiskProfileRepository(db))


@router.get("/risk", response_model=RiskProfileSchema)
async def get_risk_profile(svc: Annotated[RiskProfileService, Depends(_get_service)]):
    profile = await svc.get_or_create(LOCAL_USER_ID)
    return RiskProfileSchema.from_profile(profile)


@router.put("/risk", response_model=RiskProfileSchema)
async def update_risk_profile(
    body: RiskProfileSchema,
    svc: Annotated[RiskProfileService, Depends(_get_service)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    profile = await svc.update(LOCAL_USER_ID, body)
    await db.commit()
    # NOTE: deliberately does NOT restart running strategies. Changing the user's default
    # risk only affects forms that pre-fill from it (backtest, new live bot). A running bot
    # adapts only when its OWN config is edited (see PATCH /strategies/{id}/config).
    return RiskProfileSchema.from_profile(profile)
