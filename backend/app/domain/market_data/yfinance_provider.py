from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

import structlog

from app.core.enums import Timeframe
from app.core.types import OHLCV

logger = structlog.get_logger(__name__)

# Yahoo Finance interval mapping
_YF_INTERVAL = {
    Timeframe.M1:  "1m",
    Timeframe.M5:  "5m",
    Timeframe.M15: "15m",
    Timeframe.M30: "30m",
    Timeframe.H1:  "1h",
    Timeframe.H4:  "1h",   # yfinance has no 4h; 1h bars are trimmed to limit
    Timeframe.D1:  "1d",
    Timeframe.W1:  "1wk",
}

# How many days one bar represents (for period estimation)
_BAR_DAYS = {
    Timeframe.M1:  1 / (60 * 24),
    Timeframe.M5:  5 / (60 * 24),
    Timeframe.M15: 15 / (60 * 24),
    Timeframe.M30: 30 / (60 * 24),
    Timeframe.H1:  1 / 24,
    Timeframe.H4:  4 / 24,
    Timeframe.D1:  1.0,
    Timeframe.W1:  7.0,
}

# Well-known Bybit/Binance crypto symbols → Yahoo Finance format
_CRYPTO_MAP = {
    "BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD", "SOLUSDT": "SOL-USD",
    "BNBUSDT": "BNB-USD",  "XRPUSDT": "XRP-USD", "ADAUSDT": "ADA-USD",
    "DOGEUSDT": "DOGE-USD", "AVAXUSDT": "AVAX-USD", "DOTUSDT": "DOT-USD",
    "MATICUSDT": "MATIC-USD", "LINKUSDT": "LINK-USD", "LTCUSDT": "LTC-USD",
    "UNIUSDT": "UNI-USD",  "ATOMUSDT": "ATOM-USD", "NEARUSDT": "NEAR-USD",
    "FTMUSDT": "FTM-USD",  "ARBUSDT": "ARB-USD",  "OPUSDT": "OP-USD",
}


def normalize_symbol(symbol: str) -> str:
    """Convert broker symbol (BTCUSDT) or stock (AAPL) to Yahoo Finance format."""
    upper = symbol.upper()
    if upper in _CRYPTO_MAP:
        return _CRYPTO_MAP[upper]
    # Already in Yahoo format (BTC-USD, AAPL, EURUSD=X)
    return upper


async def fetch_ohlcv(
    symbol: str,
    timeframe: Timeframe,
    limit: int = 500,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> List[OHLCV]:
    """
    Fetch historical OHLCV from Yahoo Finance.
    Covers crypto (BTC-USD / BTCUSDT), stocks (AAPL), forex (EURUSD=X), ETFs (SPY).
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance.not_installed")
        return []

    yf_symbol = normalize_symbol(symbol)
    interval = _YF_INTERVAL[timeframe]

    # If end is given but start is not, compute start so we fetch ~limit bars.
    # yfinance returns only ~30 days when start=None and end is explicit.
    if start is None and end is not None:
        days_needed = limit * _BAR_DAYS[timeframe] * 1.2
        start = end - timedelta(days=max(int(days_needed), 30))

    if start is None and end is None:
        days_needed = limit * _BAR_DAYS[timeframe] * 1.2  # 20% buffer
        if days_needed <= 7:
            period = "7d"
        elif days_needed <= 30:
            period = "1mo"
        elif days_needed <= 90:
            period = "3mo"
        elif days_needed <= 180:
            period = "6mo"
        elif days_needed <= 365:
            period = "1y"
        elif days_needed <= 730:
            period = "2y"
        else:
            period = "5y"
    else:
        period = None

    def _download() -> list:
        ticker = yf.Ticker(yf_symbol)
        if start or end:
            hist = ticker.history(
                start=start.strftime("%Y-%m-%d") if start else None,
                end=end.strftime("%Y-%m-%d") if end else None,
                interval=interval,
                auto_adjust=True,
            )
        else:
            hist = ticker.history(period=period, interval=interval, auto_adjust=True)
        if hist.empty:
            return []
        rows = []
        for ts, row in hist.iterrows():
            try:
                rows.append({
                    "ts": ts.to_pydatetime().replace(tzinfo=None),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row.get("Volume", 0)),
                })
            except Exception:
                continue
        return rows

    loop = asyncio.get_event_loop()
    try:
        rows = await loop.run_in_executor(None, _download)
    except Exception as exc:
        logger.warning("yfinance.fetch_failed", symbol=yf_symbol, error=str(exc))
        return []

    if not rows:
        logger.warning("yfinance.empty_result", symbol=yf_symbol)
        return []

    bars = [
        OHLCV(
            timestamp=r["ts"],
            symbol=symbol,
            open=r["open"],
            high=r["high"],
            low=r["low"],
            close=r["close"],
            volume=r["volume"],
            timeframe=timeframe,
        )
        for r in rows
    ]

    # Only enforce limit when no explicit date range was requested
    if not start and not end:
        bars = bars[-limit:] if len(bars) > limit else bars
    logger.info("yfinance.fetched", symbol=yf_symbol, bars=len(bars))
    return bars
