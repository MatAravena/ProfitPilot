from __future__ import annotations
from datetime import datetime
from typing import List, Optional

import httpx
import structlog

from app.core.enums import Timeframe
from app.core.types import OHLCV

logger = structlog.get_logger(__name__)

_BYBIT_PUBLIC = "https://api.bybit.com/v5/market/kline"

_BYBIT_INTERVAL = {
    Timeframe.M1: "1", Timeframe.M5: "5", Timeframe.M15: "15",
    Timeframe.M30: "30", Timeframe.H1: "60", Timeframe.H4: "240",
    Timeframe.D1: "D", Timeframe.W1: "W",
}

# Symbols that Bybit supports (crypto linear pairs)
_BYBIT_SYMBOLS = {
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT", "LINKUSDT", "LTCUSDT",
    "UNIUSDT", "ATOMUSDT", "NEARUSDT", "ARBUSDT", "OPUSDT",
}


async def fetch_ohlcv(
    symbol: str,
    timeframe: Timeframe,
    limit: int = 1000,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> List[OHLCV]:
    """
    Fetch OHLCV bars. Tries Yahoo Finance first (broader coverage: stocks, ETFs,
    forex, crypto), falls back to Bybit for crypto-only symbols.
    """
    from app.domain.market_data.yfinance_provider import fetch_ohlcv as _yf_fetch

    try:
        bars = await _yf_fetch(symbol=symbol, timeframe=timeframe, limit=limit, start=start, end=end)
        if bars:
            return bars
    except Exception as exc:
        logger.warning("data_provider.yfinance_failed", symbol=symbol, error=str(exc))

    # Fallback: Bybit public API (crypto only)
    if symbol.upper() in _BYBIT_SYMBOLS:
        logger.info("data_provider.bybit_fallback", symbol=symbol)
        return await _fetch_bybit(symbol=symbol, timeframe=timeframe, limit=limit, start=start, end=end)

    logger.warning("data_provider.no_source", symbol=symbol)
    return []


async def _fetch_bybit(
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

    logger.info("bybit.fetched", symbol=symbol, bars=len(bars))
    return bars
