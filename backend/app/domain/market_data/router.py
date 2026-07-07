"""Provider routing: pick the right OHLCV source for a symbol.

    crypto     → Bybit  (public API, no credentials)
    non-crypto → Alpaca (config keys) → Yahoo Finance (fallback when keys absent
                 or Alpaca returns nothing)

This is the single fetch entry point behind the cache. It replaces the Yahoo-first
logic that used to live in domain/backtest/data_provider.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import structlog

from app.core.enums import Timeframe
from app.core.types import OHLCV
from app.domain.market_data import alpaca_provider, bybit_provider, yfinance_provider
from app.domain.market_data.alpaca_provider import AlpacaCredentialsMissing
from app.domain.market_data.classify import is_crypto

logger = structlog.get_logger(__name__)

# Explicit source override values accepted by callers (e.g. the ?source= query param).
Source = str  # "bybit" | "alpaca" | "yfinance" | None (auto)


async def fetch_ohlcv(
    symbol: str,
    timeframe: Timeframe,
    limit: int = 1000,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    source: Optional[Source] = None,
) -> List[OHLCV]:
    """Fetch bars from the appropriate provider. `source` forces a specific provider."""
    if source == "bybit":
        return await bybit_provider.fetch_ohlcv(symbol, timeframe, limit, start, end)
    if source == "alpaca":
        return await alpaca_provider.fetch_ohlcv(symbol, timeframe, limit, start, end)
    if source == "yfinance":
        return await yfinance_provider.fetch_ohlcv(symbol, timeframe, limit, start, end)

    # Auto routing.
    if is_crypto(symbol):
        return await bybit_provider.fetch_ohlcv(symbol, timeframe, limit, start, end)

    # Stocks/ETFs: prefer Alpaca, fall back to Yahoo.
    try:
        bars = await alpaca_provider.fetch_ohlcv(symbol, timeframe, limit, start, end)
        if bars:
            return bars
        logger.info("router.alpaca_empty_fallback_yahoo", symbol=symbol)
    except AlpacaCredentialsMissing:
        logger.info("router.alpaca_keys_missing_fallback_yahoo", symbol=symbol)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("router.alpaca_error_fallback_yahoo", symbol=symbol, error=str(exc))

    return await yfinance_provider.fetch_ohlcv(symbol, timeframe, limit, start, end)
