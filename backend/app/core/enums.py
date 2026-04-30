from enum import Enum


class MarketType(str, Enum):
    STOCK = "stock"
    CRYPTO = "crypto"
    FUTURES = "futures"
    FOREX = "forex"


class Timeframe(str, Enum):
    M1  = "1m"
    M5  = "5m"
    M15 = "15m"
    M30 = "30m"
    H1  = "1h"
    H4  = "4h"
    D1  = "1d"
    W1  = "1w"


class Direction(str, Enum):
    LONG    = "long"
    SHORT   = "short"
    NEUTRAL = "neutral"
    CLOSE   = "close"


class OrderSide(str, Enum):
    BUY  = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET     = "market"
    LIMIT      = "limit"
    STOP       = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    PENDING   = "pending"
    SUBMITTED = "submitted"
    PARTIAL   = "partial"
    FILLED    = "filled"
    CANCELLED = "cancelled"
    REJECTED  = "rejected"
    EXPIRED   = "expired"


class StrategyStatus(str, Enum):
    DRAFT       = "draft"
    BACKTESTING = "backtesting"
    PAPER       = "paper"
    LIVE        = "live"
    PAUSED      = "paused"
    ARCHIVED    = "archived"
    HALTED      = "halted"       # triggered by kill switch / risk breach


class SignalSource(str, Enum):
    QUANT      = "quant"
    FORECAST   = "forecast"     # ML forecasting model
    LLM        = "llm"          # large language model enrichment
    HYBRID     = "hybrid"       # combination of multiple sources
    MANUAL     = "manual"


class ModelStatus(str, Enum):
    UNTRAINED  = "untrained"
    TRAINING   = "training"
    TRAINED    = "trained"
    FAILED     = "failed"
    DEPRECATED = "deprecated"


class BrokerID(str, Enum):
    ALPACA  = "alpaca"
    BYBIT   = "bybit"
    BINANCE = "binance"


class ForecastingLibrary(str, Enum):
    PYTORCH      = "pytorch"
    XGBOOST      = "xgboost"
    LIGHTGBM     = "lightgbm"
    DARTS        = "darts"
    NEURALFORECAST = "neuralforecast"
    STATSFORECAST  = "statsforecast"
    PROPHET      = "prophet"
    SKTIME       = "sktime"
    CHRONOS      = "chronos"
    ENSEMBLE     = "ensemble"
    CUSTOM       = "custom"
