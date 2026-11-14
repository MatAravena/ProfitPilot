"""Operational monitor: notices when strategies silently stop, and proves daily that the box is alive.

Detection here is deterministic on purpose — no LLM. Every dependency is injected
(executor health, notifier, backup), so the policy is testable with plain fakes.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Awaitable, Callable, Optional

import structlog

logger = structlog.get_logger(__name__)

Notify = Callable[[str], Awaitable[None]]


class Monitor:
    def __init__(
        self,
        executor,
        notify: Notify,
        *,
        backup: Callable[[], object],
        heartbeat_hour_utc: int = 7,
        last_heartbeat: Optional[date] = None,
    ):
        self._executor = executor
        self._notify = notify
        self._backup = backup
        self._heartbeat_hour = heartbeat_hour_utc
        self._stale_alerted: set[str] = set()
        # Seeded by the caller on startup (date of the newest backup) so a restart — or a
        # crash loop — after today's heartbeat doesn't take another backup each time and
        # rotate every good one out of retention.
        self._last_heartbeat: Optional[date] = last_heartbeat

    async def tick(self, now: datetime) -> None:
        rows = self._executor.health(now)

        stale = {r["strategy_id"]: r for r in rows if r["stale"]}
        for sid, row in stale.items():
            if sid not in self._stale_alerted:
                await self._notify(
                    f"STALE: {row['label']} has made no progress since {row['last_progress']}"
                )
        self._stale_alerted = set(stale)   # recovered strategies re-arm

        if now.hour >= self._heartbeat_hour and self._last_heartbeat != now.date():
            self._last_heartbeat = now.date()
            await self._heartbeat(rows, len(stale))

    async def _heartbeat(self, rows: list, stale_count: int) -> None:
        try:
            result = await asyncio.to_thread(self._backup)
            backup_line = f"backup: {getattr(result, 'name', result)}" if result else "backup: off"
        except Exception as exc:
            logger.error("monitor.backup_failed", error=str(exc))
            backup_line = f"backup FAILED: {exc}"
        await self._notify(
            f"Daily: {len(rows)} strategies running, {stale_count} stale. {backup_line}"
        )

    async def run(self, interval_seconds: int = 600) -> None:
        while True:
            try:
                await self.tick(datetime.now(timezone.utc))
            except asyncio.CancelledError:
                raise
            except Exception as exc:   # the monitor must outlive any single bad tick
                logger.error("monitor.tick_failed", error=str(exc))
            await asyncio.sleep(interval_seconds)
