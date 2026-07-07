"""Bybit public-API OHLCV provider (crypto only, no credentials required).

Moved here from domain/backtest/data_provider.py so all market-data sources live
under domain/market_data/. Handles Bybit's 1000-bar-per-request limit via pagination.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

import httpx
import structlog

from app.core.enums import Timeframe
from app.core.types import OHLCV
from app.domain.market_data.classify import to_bybit_symbol

logger = structlog.get_logger(__name__)

_BYBIT_PUBLIC = "https://api.bybit.com/v5/market/kline"

_BYBIT_INTERVAL = {
    Timeframe.M1: "1", Timeframe.M5: "5", Timeframe.M15: "15",
    Timeframe.M30: "30", Timeframe.H1: "60", Timeframe.H4: "240",
    Timeframe.D1: "D", Timeframe.W1: "W",
}


async def fetch_ohlcv(
    symbol: str,
    timeframe: Timeframe,
    limit: int = 1000,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> List[OHLCV]:
    """Fetch crypto OHLCV bars from Bybit. Paginates when a start bound is given."""
    bybit_symbol = to_bybit_symbol(symbol)
    if start is None:
        # No lower bound — a single page (most-recent `limit` bars) is enough.
        return await _fetch_page(bybit_symbol, timeframe, limit=limit, start=None, end=end)
    return await _fetch_paginated(bybit_symbol, timeframe, start=start, end=end)


async def _fetch_paginated(
    symbol: str,
    timeframe: Timeframe,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> List[OHLCV]:
    """Paginate Bybit's 1000-bar-per-request limit to fetch the full requested range."""
    all_bars: List[OHLCV] = []
    current_end = end

    for _ in range(20):  # safety cap: 20 pages × 1000 = 20,000 bars
        page = await _fetch_page(symbol, timeframe, limit=1000, start=start, end=current_end)
        if not page:
            break

        # Pages come back chronologically; prepend so all_bars stays sorted.
        all_bars = page + all_bars

        if len(page) < 1000 or (start is not None and page[0].timestamp <= start):
            break

        current_end = page[0].timestamp - timedelta(milliseconds=1)

    # Deduplicate (overlap safety) and filter to requested bounds.
    seen: set = set()
    result: List[OHLCV] = []
    for bar in all_bars:
        if bar.timestamp not in seen:
            seen.add(bar.timestamp)
            result.append(bar)

    if start:
        result = [b for b in result if b.timestamp >= start]
    if end:
        result = [b for b in result if b.timestamp <= end]

    logger.info("bybit.paginated.fetched", symbol=symbol, bars=len(result))
    return result


async def _fetch_page(
    symbol: str,
    timeframe: Timeframe,
    limit: int = 1000,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> List[OHLCV]:
    interval = _BYBIT_INTERVAL.get(timeframe)
    if interval is None:
        raise ValueError(f"Unsupported timeframe for Bybit: {timeframe}")

    params: dict = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": min(limit, 1000),
    }
    if start:
        params["start"] = int(start.timestamp() * 1000)
    if end:
        params["end"] = int(end.timestamp() * 1000)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(_BYBIT_PUBLIC, params=params)
        resp.raise_for_status()
        body = resp.json()

    if body.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {body.get('retMsg')}")

    raw_list = list(reversed(body["result"]["list"]))
    bars: List[OHLCV] = []
    for row in raw_list:
        ts_ms, o, h, l, c, vol, _ = row
        bars.append(OHLCV(
            timestamp=datetime.utcfromtimestamp(int(ts_ms) / 1000),
            symbol=symbol,
            open=float(o), high=float(h), low=float(l),
            close=float(c), volume=float(vol),
            timeframe=timeframe,
        ))

    logger.info("bybit.page.fetched", symbol=symbol, bars=len(bars))
    return bars
