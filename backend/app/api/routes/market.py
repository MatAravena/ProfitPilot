from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.core.enums import Timeframe
from app.domain.backtest.data_provider import _fetch_bybit_page, fetch_ohlcv
from app.domain.market_data.yfinance_provider import fetch_ohlcv as fetch_yfinance

router = APIRouter(prefix="/market", tags=["market"])

_TIMEFRAME_MAP = {
    "1m": Timeframe.M1,  "5m": Timeframe.M5,  "15m": Timeframe.M15,
    "30m": Timeframe.M30, "1h": Timeframe.H1,  "4h": Timeframe.H4,
    "1d": Timeframe.D1,   "1w": Timeframe.W1,
}


@router.get("/ohlcv")
async def get_ohlcv(
    symbol: str = Query("BTCUSDT"),
    timeframe: str = Query("1d"),
    limit: int = Query(500, ge=1, le=1000),
    source: Optional[str] = Query(None, description="bybit | yfinance | auto (default)"),
):
    """
    Fetch OHLCV candles.
    - source=bybit   → Bybit public API (live crypto, no credentials)
    - source=yfinance → Yahoo Finance (stocks, ETFs, forex, crypto)
    - source omitted  → yfinance first, Bybit fallback
    """
    tf = _TIMEFRAME_MAP.get(timeframe)
    if tf is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown timeframe '{timeframe}'. Use: {list(_TIMEFRAME_MAP)}",
        )
    try:
        if source == "bybit":
            bars = await _fetch_bybit_page(symbol=symbol, timeframe=tf, limit=limit)
        elif source == "yfinance":
            bars = await fetch_yfinance(symbol=symbol, timeframe=tf, limit=limit)
        else:
            bars = await fetch_ohlcv(symbol=symbol, timeframe=tf, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return [
        {
            "time": int(b.timestamp.timestamp()),
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
        }
        for b in bars
    ]
