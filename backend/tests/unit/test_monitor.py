"""Monitor: stale-strategy alerts fire once, and the daily heartbeat (with backup) fires once a day."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.monitor import Monitor

pytestmark = pytest.mark.asyncio


class FakeExecutor:
    def __init__(self):
        self.rows = []

    def health(self, now):
        return self.rows


def _row(label="Macd BTCUSDT 1d", stale=False):
    return {"strategy_id": label, "label": label, "stale": stale, "last_progress": None}


def _monitor(executor, sent, backup=lambda: None, hour=7):
    async def notify(text):
        sent.append(text)
    return Monitor(executor, notify, backup=backup, heartbeat_hour_utc=hour)


def _at(day, hour):
    return datetime(2026, 11, day, hour, 0, tzinfo=timezone.utc)


async def test_stale_strategy_alerts_once_then_again_after_recovery():
    ex, sent = FakeExecutor(), []
    mon = _monitor(ex, sent, hour=23)
    ex.rows = [_row(stale=True)]

    await mon.tick(_at(13, 1))
    await mon.tick(_at(13, 2))
    assert len(sent) == 1 and "Macd BTCUSDT 1d" in sent[0]

    ex.rows = [_row(stale=False)]
    await mon.tick(_at(13, 3))
    ex.rows = [_row(stale=True)]
    await mon.tick(_at(13, 4))
    assert len(sent) == 2


async def test_heartbeat_fires_once_per_day_after_the_hour_and_runs_backup():
    ex, sent, backups = FakeExecutor(), [], []
    ex.rows = [_row("A"), _row("B")]
    mon = _monitor(ex, sent, backup=lambda: backups.append(1) or "profitpilot-x.db")

    await mon.tick(_at(13, 6))          # before the hour → nothing
    assert sent == [] and backups == []

    await mon.tick(_at(13, 7))
    await mon.tick(_at(13, 8))          # same day → not again
    assert len(sent) == 1 and len(backups) == 1
    assert "2 strategies running" in sent[0] and "profitpilot-x.db" in sent[0]

    await mon.tick(_at(14, 7))          # next day → again
    assert len(sent) == 2 and len(backups) == 2


async def test_restart_after_todays_heartbeat_does_not_repeat_it():
    """A crash loop must not take a backup per restart (it would rotate out every good one)."""
    ex, sent, backups = FakeExecutor(), [], []

    async def notify(text):
        sent.append(text)

    mon = Monitor(ex, notify, backup=lambda: backups.append(1), heartbeat_hour_utc=7,
                  last_heartbeat=_at(13, 7).date())

    await mon.tick(_at(13, 9))
    assert sent == [] and backups == []

    await mon.tick(_at(14, 7))
    assert len(sent) == 1 and len(backups) == 1


async def test_backup_failure_is_reported_not_raised():
    ex, sent = FakeExecutor(), []

    def broken():
        raise OSError("disk full")

    mon = _monitor(ex, sent, backup=broken)
    await mon.tick(_at(13, 7))

    assert len(sent) == 1 and "backup FAILED" in sent[0]
