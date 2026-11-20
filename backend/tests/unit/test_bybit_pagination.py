"""Bybit pagination must return the WHOLE requested range.

Fake that mirrors the real kline endpoint (probed 2026-11-15): with an `end`, a page is the
latest ≤1000 bars in [start, end]; with only a `start`, it is the EARLIEST 1000 bars from start.
Two bugs this pins: no `end` returned just the first 1000 bars (6 weeks of hourly data out of
6.5 years), and a 20-page cap silently truncated long hourly ranges (a 2019 request began in 2024).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.core.enums import Timeframe
from app.core.types import OHLCV
from app.domain.backtest import data_provider

pytestmark = pytest.mark.asyncio

LISTED = datetime(2020, 3, 25)             # first bar Bybit has
NOW = datetime(2026, 11, 1)
HOURS = int((NOW - LISTED).total_seconds() // 3600)   # ~58k hourly bars


def _bar(i: int) -> OHLCV:
    return OHLCV(timestamp=LISTED + timedelta(hours=i), symbol="BTCUSDT", open=1, high=1, low=1,
                 close=1, volume=1, timeframe=Timeframe.H1)


async def _fake_page(symbol, timeframe, limit=1000, start=None, end=None):
    lo = 0 if start is None else max(0, int((start - LISTED).total_seconds() // 3600))
    hi = HOURS if end is None else min(HOURS, int((end - LISTED).total_seconds() // 3600))
    if lo > hi:
        return []
    if end is None:                       # Bybit: start only → oldest bars from start
        return [_bar(i) for i in range(lo, min(hi + 1, lo + limit))]
    return [_bar(i) for i in range(max(lo, hi - limit + 1), hi + 1)]   # latest bars before end


@pytest.fixture(autouse=True)
def fake_bybit(monkeypatch):
    monkeypatch.setattr(data_provider, "_fetch_bybit_page", _fake_page)
    monkeypatch.setattr(data_provider, "_utcnow", lambda: NOW)


async def test_start_without_end_returns_everything_up_to_now():
    bars = await data_provider._fetch_bybit_paginated("BTCUSDT", Timeframe.H1, start=datetime(2019, 1, 1))
    assert bars[0].timestamp == LISTED
    assert bars[-1].timestamp == NOW
    assert len(bars) == HOURS + 1


async def test_long_hourly_range_is_not_silently_truncated():
    bars = await data_provider._fetch_bybit_paginated(
        "BTCUSDT", Timeframe.H1, start=datetime(2019, 1, 1), end=NOW)
    assert bars[0].timestamp == LISTED      # old 20-page cap started in 2024
    assert len(bars) == HOURS + 1


async def test_bars_stay_inside_the_requested_window():
    start, end = datetime(2023, 1, 1), datetime(2023, 3, 1)
    bars = await data_provider._fetch_bybit_paginated("BTCUSDT", Timeframe.H1, start=start, end=end)
    assert bars[0].timestamp == start and bars[-1].timestamp == end
    assert all(b.timestamp < c.timestamp for b, c in zip(bars, bars[1:]))
