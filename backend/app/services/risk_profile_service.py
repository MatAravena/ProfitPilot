from __future__ import annotations
from uuid import UUID

from app.core.config import get_settings
from app.models.db.risk_profile import RiskProfile
from app.models.schemas.risk_schemas import RiskProfileSchema
from app.repositories.risk_profile_repository import RiskProfileRepository

_settings = get_settings()


class RiskProfileService:
    def __init__(self, repo: RiskProfileRepository):
        self._repo = repo

    async def get_or_create(self, user_id: UUID) -> RiskProfile:
        """Return the user's risk profile, creating one seeded from the global defaults
        on first access."""
        profile = await self._repo.get_by_user(user_id)
        if profile is None:
            profile = await self._repo.add(RiskProfile(
                user_id=user_id,
                stop_loss_pct=_settings.DEFAULT_STOP_LOSS_PCT,
                take_profit_pct=None,
                max_open_positions=_settings.DEFAULT_MAX_OPEN_POSITIONS,
                max_daily_drawdown_pct=_settings.DEFAULT_MAX_DAILY_DRAWDOWN_PCT,
                max_total_drawdown_pct=_settings.DEFAULT_MAX_TOTAL_DRAWDOWN_PCT,
                max_orders_per_minute=_settings.DEFAULT_MAX_ORDERS_PER_MINUTE,
                kill_switch_enabled=True,
            ))
        return profile

    async def update(self, user_id: UUID, cfg: RiskProfileSchema) -> RiskProfile:
        profile = await self.get_or_create(user_id)
        profile.stop_loss_pct = cfg.stop_loss_pct
        profile.take_profit_pct = cfg.take_profit_pct
        profile.max_open_positions = cfg.max_open_positions
        profile.max_daily_drawdown_pct = cfg.max_daily_drawdown_pct
        profile.max_total_drawdown_pct = cfg.max_total_drawdown_pct
        profile.max_orders_per_minute = cfg.max_orders_per_minute
        profile.kill_switch_enabled = cfg.kill_switch_enabled
        await self._repo._session.flush()
        await self._repo._session.refresh(profile)
        return profile
