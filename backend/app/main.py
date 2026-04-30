from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.routes import strategies, brokers, forecasting, backtests, signals, portfolio, health

logger = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("profitpilot.starting", version=settings.APP_VERSION)

    # TODO: Initialize broker adapters
    # TODO: Load trained forecasting models from registry
    # TODO: Start strategy heartbeat scheduler

    yield

    logger.info("profitpilot.stopping")
    # TODO: Graceful strategy shutdown
    # TODO: Close broker connections


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    prefix = settings.API_V1_PREFIX
    app.include_router(health.router,       prefix=prefix, tags=["health"])
    app.include_router(strategies.router,   prefix=prefix, tags=["strategies"])
    app.include_router(brokers.router,      prefix=prefix, tags=["brokers"])
    app.include_router(forecasting.router,  prefix=prefix, tags=["forecasting"])
    app.include_router(backtests.router,    prefix=prefix, tags=["backtests"])
    app.include_router(signals.router,      prefix=prefix, tags=["signals"])
    app.include_router(portfolio.router,    prefix=prefix, tags=["portfolio"])

    return app


app = create_app()
