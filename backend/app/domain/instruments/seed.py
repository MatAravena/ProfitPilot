"""The instruments ProfitPilot ships knowing about.

Specs are **conservative seed values** in the shape each venue actually publishes
(Binance `exchangeInfo`, Bybit `instruments-info`, Alpaca `assets`). They are good
enough to round orders correctly and to refuse ones that are too small; refreshing them
from the live broker endpoints is the natural follow-up, and the registry is built to
be handed a different set without any caller changing.

Crypto pairs default to **spot** — this app's own strategies accumulate coins, and spot
has no funding leg. Perpetuals are separate instruments with an explicit `.P` suffix,
because BTCUSDT-spot and BTCUSDT-perp are two different things to own even though every
venue happens to spell them the same way.
"""
from __future__ import annotations

from typing import Dict, List

from app.core.enums import BrokerID, MarketType
from app.domain.instruments.instrument import Instrument, InstrumentKind, VenueListing

# Crypto spot: base → (tick_size, lot_step). Quote is USDT on Bybit/Binance, USD on Alpaca.
_CRYPTO_SPOT: Dict[str, tuple] = {
    "BTC":   (0.01,       0.00001),
    "ETH":   (0.01,       0.0001),
    "SOL":   (0.01,       0.001),
    "BNB":   (0.01,       0.001),
    "XRP":   (0.0001,     1.0),
    "ADA":   (0.0001,     1.0),
    "DOGE":  (0.00001,    1.0),
    "AVAX":  (0.01,       0.01),
    "DOT":   (0.001,      0.1),
    "MATIC": (0.0001,     1.0),
    "LINK":  (0.001,      0.01),
    "LTC":   (0.01,       0.001),
    "UNI":   (0.001,      0.01),
    "ATOM":  (0.001,      0.01),
    "NEAR":  (0.001,      0.1),
    "ARB":   (0.0001,     0.1),
    "OP":    (0.0001,     0.1),
    "TRX":   (0.00001,    1.0),
    "BCH":   (0.01,       0.001),
    "ETC":   (0.01,       0.01),
    "FIL":   (0.001,      0.01),
    "APT":   (0.001,      0.01),
    "SUI":   (0.0001,     0.1),
    "SHIB":  (0.00000001, 1.0),
    "PEPE":  (0.00000001, 1.0),
}

# Crypto perpetuals (Bybit linear). Only the majors — add more when a strategy needs one.
_CRYPTO_PERP: Dict[str, tuple] = {
    "BTC": (0.1,   0.001),
    "ETH": (0.01,  0.01),
    "SOL": (0.001, 0.1),
}

# Alpaca lists a narrower crypto universe than Bybit/Binance.
_ALPACA_CRYPTO = frozenset({"BTC", "ETH", "SOL", "LTC", "BCH", "LINK", "UNI", "AVAX",
                            "DOT", "DOGE", "SHIB", "XRP"})

# US equities and ETFs. Alpaca supports fractional shares down to 0.001 / $1 notional.
_EQUITIES: List[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX", "INTC",
    "JPM", "V", "KO", "DIS", "BA", "COIN", "MSTR",
    "SPY", "QQQ", "VOO", "IWM", "GLD", "TLT",
]

_CRYPTO_MIN_NOTIONAL = 5.0     # Binance's floor; Bybit spot is lower, so this is the safe one
_EQUITY_TICK = 0.01
_EQUITY_LOT_STEP = 0.001
_EQUITY_MIN_NOTIONAL = 1.0


def _crypto_spot(base: str, tick: float, step: float) -> Instrument:
    venues = {
        BrokerID.BYBIT: VenueListing(f"{base}USDT", category="spot"),
        BrokerID.BINANCE: VenueListing(f"{base}USDT"),
    }
    if base in _ALPACA_CRYPTO:
        venues[BrokerID.ALPACA] = VenueListing(f"{base}/USD")
    return Instrument(
        symbol=f"{base}USDT", base=base, quote="USDT",
        market_type=MarketType.CRYPTO, kind=InstrumentKind.SPOT,
        tick_size=tick, lot_step=step, min_qty=step, min_notional=_CRYPTO_MIN_NOTIONAL,
        venues=venues,
    )


def _crypto_perp(base: str, tick: float, step: float) -> Instrument:
    return Instrument(
        symbol=f"{base}USDT.P", base=base, quote="USDT",
        market_type=MarketType.CRYPTO, kind=InstrumentKind.PERP,
        tick_size=tick, lot_step=step, min_qty=step, min_notional=_CRYPTO_MIN_NOTIONAL,
        venues={BrokerID.BYBIT: VenueListing(f"{base}USDT", category="linear")},
    )


def _equity(ticker: str) -> Instrument:
    return Instrument(
        symbol=ticker, base=ticker, quote="USD",
        market_type=MarketType.STOCK, kind=InstrumentKind.SPOT,
        tick_size=_EQUITY_TICK, lot_step=_EQUITY_LOT_STEP, min_qty=_EQUITY_LOT_STEP,
        min_notional=_EQUITY_MIN_NOTIONAL,
        venues={BrokerID.ALPACA: VenueListing(ticker)},
    )


def default_instruments() -> List[Instrument]:
    """Built fresh on each call so a caller can mutate its own registry safely."""
    return [
        *(_crypto_spot(base, *specs) for base, specs in _CRYPTO_SPOT.items()),
        *(_crypto_perp(base, *specs) for base, specs in _CRYPTO_PERP.items()),
        *(_equity(t) for t in _EQUITIES),
    ]
