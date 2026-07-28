"""Shared OHLCV normalization: guarantee bars are ascending and unique by timestamp.

Every data source flows through here before reaching the backtest engine / executor /
frontend chart, all of which assume strictly-ascending, unique timestamps. A provider can
violate that (pagination overlap, or a DST-boundary bar) — this is the single chokepoint
that makes such quirks impossible downstream.
"""
from __future__ import annotations

from typing import Iterable, List

from app.core.types import OHLCV


def dedupe_sort_bars(bars: Iterable[OHLCV]) -> List[OHLCV]:
    """Return bars sorted ascending by timestamp with duplicates collapsed.

    When two bars share a timestamp the LATER one in input order wins — for paginated
    fetches the freshest page is appended last, so this keeps the most recent value.
    """
    by_ts: dict = {}
    for bar in bars:
        by_ts[bar.timestamp] = bar   # later duplicate overwrites earlier
    return [by_ts[ts] for ts in sorted(by_ts)]
