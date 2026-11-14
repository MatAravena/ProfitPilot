"""The executor must tell someone when a strategy stops making progress.

Drives the real StrategyExecutor (paper) with an injected notifier and asserts the
alerts a human would need: halted, failing (once, not every poll), and staleness.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.api.deps import LOCAL_USER_ID
from app.core.enums import Timeframe
from app.core.types import RiskConfig

pytestmark = pytest.mark.asyncio

SYMBOL = "BTCUSDT"
API = "/api/v1"


async def _new_paper_strategy(client) -> uuid.UUID:
    resp = await client.post(f"{API}/strategies", json={
        "class_name": "SmaCrossover", "symbol": SYMBOL, "timeframe": "1d",
        "parameters": {}, "execution": {"size_pct": 0.02},
    })
    assert resp.status_code == 201, resp.text
    return uuid.UUID(resp.json()["id"])


def _executor(sent):
    from app.services.strategy_executor import StrategyExecutor

    async def notify(text):
        sent.append(text)

    return StrategyExecutor(notify=notify)


async def _run_once(executor, sid):
    from app.db.base import AsyncSessionLocal
    return await executor._execute_once(
        sid, "SmaCrossover", SYMBOL, Timeframe.D1, {}, LOCAL_USER_ID,
        "paper", None, RiskConfig(), True, AsyncSessionLocal,
    )


def _break_broker(monkeypatch):
    from app.domain.broker.adapters.simulated_adapter import SimulatedBrokerAdapter

    async def boom(self):
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(SimulatedBrokerAdapter, "get_account", boom)


def _fake_data(monkeypatch):
    from tests.conftest import make_bars

    async def fake_fetch(symbol, timeframe, limit=200):
        return make_bars([100.0] * 60, symbol=SYMBOL, timeframe=Timeframe.D1)

    monkeypatch.setattr("app.domain.backtest.data_provider.fetch_ohlcv", fake_fetch)


async def test_failing_strategy_alerts_once_then_alerts_when_halted(client, monkeypatch):
    _fake_data(monkeypatch)
    sid = await _new_paper_strategy(client)
    sent: list[str] = []
    executor = _executor(sent)
    _break_broker(monkeypatch)

    assert await _run_once(executor, sid) is True
    assert await _run_once(executor, sid) is True
    assert len(sent) == 1, "a failing strategy alerts on the first error only, not every poll"
    assert "SmaCrossover BTCUSDT" in sent[0] and "broker unreachable" in sent[0]

    keep_going = True
    for _ in range(5):
        keep_going = await _run_once(executor, sid)
        if not keep_going:
            break
    assert keep_going is False
    assert len(sent) == 2 and "HALTED" in sent[1]


async def test_halted_strategy_is_untracked_before_the_alert_goes_out(client, monkeypatch):
    """The halt alert can take seconds; the strategy must already be gone from the executor's
    books, or a re-activate during that window is silently ignored."""
    _fake_data(monkeypatch)
    sid = await _new_paper_strategy(client)
    from app.services.strategy_executor import StrategyExecutor

    seen_at_alert: list[tuple[bool, list]] = []

    async def notify(text):
        if "HALTED" in text:
            seen_at_alert.append((str(sid) in executor._tasks, executor.health(datetime.now(timezone.utc))))

    executor = StrategyExecutor(notify=notify)
    executor._tasks[str(sid)] = object()          # stand-in for the running loop task
    executor._track(str(sid), "SmaCrossover BTCUSDT 1d", 3600, datetime.now(timezone.utc))
    _break_broker(monkeypatch)

    for _ in range(6):
        if not await _run_once(executor, sid):
            break

    assert seen_at_alert == [(False, [])]


async def test_failing_signal_generation_alerts_and_is_not_progress(client, monkeypatch):
    """generate_signals raising every bar used to look perfectly healthy: no error, no stale."""
    _fake_data(monkeypatch)
    sid = await _new_paper_strategy(client)
    sent: list[str] = []
    executor = _executor(sent)
    start = datetime.now(timezone.utc) - timedelta(hours=5)
    executor._track(str(sid), "SmaCrossover BTCUSDT 1d", poll_secs=3600, now=start)

    from app.domain.strategy.examples.sma_crossover import SmaCrossover

    async def boom(self, data):
        raise ValueError("bad indicator\nTraceback line that must not be forwarded")

    monkeypatch.setattr(SmaCrossover, "generate_signals", boom)

    assert await _run_once(executor, sid) is True
    assert await _run_once(executor, sid) is True

    assert len(sent) == 1 and "ValueError: bad indicator" in sent[0]
    assert "Traceback line" not in sent[0], "only the first line of an error is forwarded"
    assert executor.health(datetime.now(timezone.utc))[0]["stale"] is True


async def test_recovery_rearms_the_error_alert(client, monkeypatch):
    _fake_data(monkeypatch)
    sid = await _new_paper_strategy(client)
    sent: list[str] = []
    executor = _executor(sent)

    with monkeypatch.context() as m:
        _break_broker(m)
        await _run_once(executor, sid)
    await _run_once(executor, sid)          # healthy cycle clears the flag
    _break_broker(monkeypatch)
    await _run_once(executor, sid)

    assert len(sent) == 2


async def test_health_marks_a_strategy_stale_when_it_stops_progressing(client, monkeypatch):
    _fake_data(monkeypatch)
    sid = await _new_paper_strategy(client)
    executor = _executor([])
    start = datetime.now(timezone.utc)
    executor._track(str(sid), "SmaCrossover BTCUSDT 1d", poll_secs=3600, now=start)

    await _run_once(executor, sid)
    fresh = executor.health(datetime.now(timezone.utc) + timedelta(minutes=30))
    stale = executor.health(datetime.now(timezone.utc) + timedelta(hours=3))

    assert [r["stale"] for r in fresh] == [False]
    assert [r["stale"] for r in stale] == [True]
    assert stale[0]["label"] == "SmaCrossover BTCUSDT 1d"


async def test_no_market_data_does_not_count_as_progress(client, monkeypatch):
    sid = await _new_paper_strategy(client)
    executor = _executor([])
    start = datetime.now(timezone.utc) - timedelta(hours=5)
    executor._track(str(sid), "SmaCrossover BTCUSDT 1d", poll_secs=3600, now=start)

    async def no_bars(symbol, timeframe, limit=200):
        return []

    monkeypatch.setattr("app.domain.backtest.data_provider.fetch_ohlcv", no_bars)
    await _run_once(executor, sid)

    assert executor.health(datetime.now(timezone.utc))[0]["stale"] is True
