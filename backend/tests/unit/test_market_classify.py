"""Unit tests for market-data symbol classification and normalization."""
from __future__ import annotations

import pytest

from app.core.enums import MarketType
from app.domain.market_data.classify import (
    classify_market,
    is_crypto,
    to_alpaca_symbol,
    to_bybit_symbol,
)


@pytest.mark.parametrize(
    "symbol",
    ["BTCUSDT", "ETHUSDT", "BTC/USD", "ETH-USD", "SOLUSDC", "BTCUSD", "btcusdt"],
)
def test_crypto_symbols_classified_as_crypto(symbol):
    assert classify_market(symbol) is MarketType.CRYPTO
    assert is_crypto(symbol) is True


@pytest.mark.parametrize("symbol", ["AAPL", "SPY", "TSLA", "MSFT", "aapl"])
def test_stock_symbols_classified_as_stock(symbol):
    assert classify_market(symbol) is MarketType.STOCK
    assert is_crypto(symbol) is False


def test_unknown_crypto_base_is_not_misrouted():
    # A stable-suffix pair whose base isn't a known crypto stays a stock.
    assert classify_market("XYZUSDT") is MarketType.STOCK
    # A ticker that merely contains "USD" is not a crypto pair.
    assert classify_market("USDX") is MarketType.STOCK


def test_to_bybit_symbol_normalizes_quotes():
    assert to_bybit_symbol("BTC/USD") == "BTCUSDT"
    assert to_bybit_symbol("BTC-USD") == "BTCUSDT"
    assert to_bybit_symbol("ETHUSDC") == "ETHUSDT"
    assert to_bybit_symbol("BTCUSDT") == "BTCUSDT"
    assert to_bybit_symbol("aapl") == "AAPL"  # stocks pass through, uppercased


def test_to_alpaca_symbol_normalizes_pairs():
    assert to_alpaca_symbol("BTCUSDT") == "BTC/USD"
    assert to_alpaca_symbol("ETHUSDC") == "ETH/USD"
    assert to_alpaca_symbol("BTC-USD") == "BTC/USD"
    assert to_alpaca_symbol("AAPL") == "AAPL"  # stocks unchanged
