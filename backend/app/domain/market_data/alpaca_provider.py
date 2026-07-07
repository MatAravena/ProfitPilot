"""Alpaca OHLCV provider for stocks/ETFs (and crypto, if ever routed here).

Standalone historical-data client built from config-level Alpaca keys — it does NOT
require a per-user broker connection. Stocks use the configured data feed (free
"iex" by default). Raises `AlpacaCredentialsMissing` when keys are absent so the
router can fall back to Yahoo.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List, Optional

import structlog

from app.core.config import get_settings
from app.core.enums import Timeframe
from app.core.types import OHLCV
from app.domain.market_data.classify import is_crypto, to_alpaca_symbol

logger = structlog.get_logger(__name__)


class AlpacaCredentialsMissing(RuntimeError):
    """Raised when Alpaca data is requested but no API keys are configured."""


# Cached clients keyed by (api_key, secret) so we build them once.
_stock_client = None
_crypto_client = None
_client_creds: tuple[str, str] | None = None


def _timeframe(tf: Timeframe):
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    tf_map = {
        Timeframe.M1: TimeFrame(1, TimeFrameUnit.Minute),
        Timeframe.M5: TimeFrame(5, TimeFrameUnit.Minute),
        Timeframe.M15: TimeFrame(15, TimeFrameUnit.Minute),
        Timeframe.M30: TimeFrame(30, TimeFrameUnit.Minute),
        Timeframe.H1: TimeFrame(1, TimeFrameUnit.Hour),
        Timeframe.H4: TimeFrame(4, TimeFrameUnit.Hour),
        Timeframe.D1: TimeFrame(1, TimeFrameUnit.Day),
        Timeframe.W1: TimeFrame(1, TimeFrameUnit.Week),
    }
    alpaca_tf = tf_map.get(tf)
    if alpaca_tf is None:
        raise ValueError(f"Unsupported timeframe for Alpaca: {tf}")
    return alpaca_tf


def _feed():
    from alpaca.data.enums import DataFeed

    return DataFeed.SIP if get_settings().ALPACA_DATA_FEED.lower() == "sip" else DataFeed.IEX


def _ensure_clients():
    """Lazily build (and cache) the historical data clients from config keys."""
    global _stock_client, _crypto_client, _client_creds
    settings = get_settings()
    key, secret = settings.ALPACA_API_KEY, settings.ALPACA_SECRET_KEY
    if not key or not secret:
        raise AlpacaCredentialsMissing(
            "Alpaca API key/secret not configured (set ALPACA_API_KEY / ALPACA_SECRET_KEY)."
        )
    if _client_creds != (key, secret):
        from alpaca.data.historical import (
            CryptoHistoricalDataClient,
            StockHistoricalDataClient,
        )

        _stock_client = StockHistoricalDataClient(api_key=key, secret_key=secret)
        _crypto_client = CryptoHistoricalDataClient(api_key=key, secret_key=secret)
        _client_creds = (key, secret)
    return _stock_client, _crypto_client


async def fetch_ohlcv(
    symbol: str,
    timeframe: Timeframe,
    limit: int = 500,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> List[OHLCV]:
    """Fetch OHLCV bars from Alpaca. Raises AlpacaCredentialsMissing if keys absent."""
    stock_client, crypto_client = _ensure_clients()
    alpaca_tf = _timeframe(timeframe)
    crypto = is_crypto(symbol)
    alpaca_symbol = to_alpaca_symbol(symbol)

    def _download():
        from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest

        req_kwargs = dict(symbol_or_symbols=alpaca_symbol, timeframe=alpaca_tf)
        if start is not None:
            req_kwargs["start"] = start
        if end is not None:
            req_kwargs["end"] = end
        # Alpaca returns most-recent bars when limit is set without an explicit start.
        if start is None:
            req_kwargs["limit"] = limit

        if crypto:
            bars = crypto_client.get_crypto_bars(CryptoBarsRequest(**req_kwargs))
        else:
            req_kwargs["feed"] = _feed()
            bars = stock_client.get_stock_bars(StockBarsRequest(**req_kwargs))
        return list(bars[alpaca_symbol]) if alpaca_symbol in bars.data else []

    try:
        raw = await asyncio.get_event_loop().run_in_executor(None, _download)
    except AlpacaCredentialsMissing:
        raise
    except Exception as exc:
        logger.warning("alpaca.fetch_failed", symbol=alpaca_symbol, error=str(exc))
        return []

    bars = [
        OHLCV(
            timestamp=b.timestamp.replace(tzinfo=None),
            symbol=symbol,
            open=float(b.open), high=float(b.high), low=float(b.low),
            close=float(b.close), volume=float(b.volume or 0.0),
            timeframe=timeframe,
        )
        for b in raw
    ]
    if start is None and len(bars) > limit:
        bars = bars[-limit:]
    logger.info("alpaca.fetched", symbol=alpaca_symbol, bars=len(bars), feed=None if crypto else get_settings().ALPACA_DATA_FEED)
    return bars
