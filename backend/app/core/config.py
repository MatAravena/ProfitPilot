from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_NAME: str = "ProfitPilot"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    SECRET_KEY: str = Field(..., description="Random secret key for JWT signing")

    # API
    API_V1_PREFIX: str = "/api/v1"
    # Allow all localhost ports in dev; set explicit origins in production
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
    ]

    # Database
    DATABASE_URL: str = Field(..., description="Async PostgreSQL DSN e.g. postgresql+asyncpg://...")
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Market data
    # Alpaca powers stock/ETF candles (free account API keys required). Crypto uses
    # Bybit's public API (no keys). When ALPACA_API_KEY is empty, stock symbols fall
    # back to Yahoo Finance.
    ALPACA_API_KEY: str = ""
    ALPACA_SECRET_KEY: str = ""
    ALPACA_DATA_FEED: str = "iex"   # free feed; "sip" requires a paid subscription
    # Hot-cache TTL for the most-recent (unbounded) candle requests, in seconds.
    MARKET_CACHE_TTL_SECONDS: int = 60

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # LLM Enrichment (optional layer — all empty by default)
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-5"
    OPENAI_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Model storage
    MODEL_ARTIFACT_DIR: str = "./model_artifacts"   # local dev
    MODEL_ARTIFACT_S3_BUCKET: str = ""              # prod — if set, overrides local

    # Risk defaults (overridable per strategy instance)
    DEFAULT_MAX_POSITION_SIZE_PCT: float = 0.02
    DEFAULT_MAX_OPEN_POSITIONS: int = 5
    DEFAULT_MAX_DAILY_DRAWDOWN_PCT: float = 0.03
    DEFAULT_MAX_TOTAL_DRAWDOWN_PCT: float = 0.10
    DEFAULT_STOP_LOSS_PCT: float = 0.015
    DEFAULT_MAX_ORDERS_PER_MINUTE: int = 10

    # Paper-trading simulator. Costs mirror the backtest engine's defaults so a paper run is a
    # faithful preview of a backtest (and of real live), not an artificially frictionless one.
    SIM_STARTING_EQUITY: float = 100_000.0    # virtual starting cash for paper strategies
    SIM_COMMISSION_PCT: float = 0.001         # 0.1% of notional per fill
    SIM_SLIPPAGE_PCT: float = 0.0005          # 5 bps adverse slippage per fill

    # JWT
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h


@lru_cache
def get_settings() -> Settings:
    return Settings()
