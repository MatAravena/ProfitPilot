"""Symbol classification + cross-provider symbol normalization.

Decides whether a ticker is crypto (routed to Bybit) or a stock/ETF (routed to
Alpaca, with Yahoo as fallback), and converts between the notations each provider
expects:

    BTCUSDT  (Bybit)   ⇄   BTC/USD  (Alpaca crypto)   ⇄   BTC-USD  (Yahoo crypto)
    AAPL, SPY  → stock everywhere
"""
from __future__ import annotations

from app.core.enums import MarketType

# Canonical crypto base assets we support. Used both for classification and for
# normalizing pair notation. Kept broad but explicit so a stock like "USDT" or an
# ambiguous ticker never gets misrouted.
CRYPTO_BASES: frozenset[str] = frozenset({
    "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX", "DOT", "MATIC",
    "LINK", "LTC", "UNI", "ATOM", "NEAR", "ARB", "OP", "TRX", "BCH", "ETC",
    "FIL", "APT", "SUI", "SHIB", "PEPE",
})

# Quote currencies that indicate a crypto pair when suffixed (e.g. BTCUSDT).
_CRYPTO_QUOTES = ("USDT", "USDC")


def _split_pair(symbol: str) -> tuple[str, str] | None:
    """Return (base, quote) if `symbol` looks like a crypto pair, else None."""
    s = symbol.upper().strip()

    # Explicit separators: BTC/USD, BTC-USD
    for sep in ("/", "-"):
        if sep in s:
            base, _, quote = s.partition(sep)
            if base in CRYPTO_BASES:
                return base, quote
            return None

    # Concatenated stable pairs: BTCUSDT, ETHUSDC
    for q in _CRYPTO_QUOTES:
        if s.endswith(q):
            base = s[: -len(q)]
            if base in CRYPTO_BASES:
                return base, q

    # Concatenated USD pairs: BTCUSD
    if s.endswith("USD") and s[:-3] in CRYPTO_BASES:
        return s[:-3], "USD"

    return None


def classify_market(symbol: str) -> MarketType:
    """Classify a ticker as CRYPTO or STOCK. Everything non-crypto is treated as STOCK."""
    return MarketType.CRYPTO if _split_pair(symbol) is not None else MarketType.STOCK


def is_crypto(symbol: str) -> bool:
    return classify_market(symbol) is MarketType.CRYPTO


def to_bybit_symbol(symbol: str) -> str:
    """Normalize to Bybit's concatenated form, e.g. BTC/USD → BTCUSDT.

    Bybit linear perps quote in USDT, so a USD/USDC quote maps to USDT.
    """
    pair = _split_pair(symbol)
    if pair is None:
        return symbol.upper().strip()
    base, quote = pair
    quote = "USDT" if quote in ("USD", "USDC") else quote
    return f"{base}{quote}"


def to_alpaca_symbol(symbol: str) -> str:
    """Normalize to Alpaca's form: crypto as BASE/USD, stocks unchanged (uppercased)."""
    pair = _split_pair(symbol)
    if pair is None:
        return symbol.upper().strip()
    base, quote = pair
    quote = "USD" if quote in ("USDT", "USDC") else quote
    return f"{base}/{quote}"
