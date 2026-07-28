"""Tests for OHLCV normalization (dedupe + sort) — the guard that keeps duplicate /
out-of-order bars from any data provider from reaching the engine and the FE chart."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.enums import Timeframe
from app.core.types import OHLCV
from app.domain.market_data.normalize import dedupe_sort_bars


def _bar(ts: datetime, close: float) -> OHLCV:
    return OHLCV(
        timestamp=ts, symbol="BTCUSDT", open=close, high=close, low=close,
        close=close, volume=1.0, timeframe=Timeframe.H1,
    )


_T0 = datetime(2025, 3, 30, 0, 0, tzinfo=timezone.utc)


def test_empty_input_returns_empty():
    assert dedupe_sort_bars([]) == []


def test_sorts_out_of_order_bars_ascending():
    bars = [_bar(_T0 + timedelta(hours=2), 2), _bar(_T0, 0), _bar(_T0 + timedelta(hours=1), 1)]
    out = dedupe_sort_bars(bars)
    assert [b.timestamp for b in out] == [_T0, _T0 + timedelta(hours=1), _T0 + timedelta(hours=2)]


def test_collapses_duplicate_timestamps_keeping_last():
    # The exact crash scenario: two bars at the same instant (DST boundary).
    dup_ts = _T0 + timedelta(hours=1)
    bars = [_bar(_T0, 0), _bar(dup_ts, 100), _bar(dup_ts, 105)]
    out = dedupe_sort_bars(bars)
    assert [b.timestamp for b in out] == [_T0, dup_ts]
    assert out[1].close == 105   # later duplicate wins


def test_output_is_strictly_ascending_and_unique():
    # setData contract: no equal or descending adjacent timestamps for arbitrary input.
    dup = _T0 + timedelta(hours=1)
    bars = [_bar(dup, 1), _bar(dup, 9), _bar(_T0 + timedelta(hours=5), 5), _bar(_T0, 0), _bar(dup, 8)]
    out = dedupe_sort_bars(bars)
    for prev, cur in zip(out, out[1:]):
        assert cur.timestamp > prev.timestamp
