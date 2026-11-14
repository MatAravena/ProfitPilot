import asyncio
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import LOCAL_USER_ID
from app.core.config import get_settings
from app.api.routes import strategies, brokers, forecasting, backtests, signals, portfolio, health, market, builder, orders, settings as settings_routes
from app.api.ws.router import router as ws_router

logger = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("profitpilot.starting", version=settings.APP_VERSION)

    # Create all DB tables (dev convenience — use Alembic migrations in production)
    from app.db.base import engine, Base, AsyncSessionLocal
    import app.models.db  # noqa: F401 — registers all ORM models with Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed the single local user (Phase 1 — no auth needed)
    await _seed_local_user(AsyncSessionLocal)

    # Start strategy execution loop and portfolio snapshot loop
    from app.services.strategy_executor import executor
    from app.services.snapshot_service import portfolio_snapshot_loop
    await executor.boot(AsyncSessionLocal)
    snapshot_task = asyncio.create_task(
        portfolio_snapshot_loop(AsyncSessionLocal, LOCAL_USER_ID)
    )
    monitor_task = asyncio.create_task(_build_monitor(executor).run())

    yield

    executor.shutdown()
    snapshot_task.cancel()
    monitor_task.cancel()
    logger.info("profitpilot.stopping")
    await engine.dispose()


def _build_monitor(executor):
    """Wire the operational monitor: executor health → Telegram, plus the daily DB backup."""
    from app.db.backup import backup_sqlite, latest_backup_date
    from app.services.alerts import send_alert
    from app.services.monitor import Monitor

    def backup():
        if not settings.BACKUP_DIR:
            return None
        return backup_sqlite(settings.DATABASE_URL, settings.BACKUP_DIR, settings.BACKUP_KEEP)

    done = latest_backup_date(settings.DATABASE_URL, settings.BACKUP_DIR) if settings.BACKUP_DIR else None
    return Monitor(executor, send_alert, backup=backup,
                   heartbeat_hour_utc=settings.HEARTBEAT_HOUR_UTC, last_heartbeat=done)


async def _seed_local_user(session_factory) -> None:
    from app.api.deps import LOCAL_USER_ID
    from app.models.db.user import User
    from app.repositories.user_repository import UserRepository

    async with session_factory() as session:
        repo = UserRepository(session)
        existing = await repo.get(LOCAL_USER_ID)
        if existing is None:
            user = User(
                id=LOCAL_USER_ID,
                email="local@profitpilot.local",
                username="local",
                hashed_password="",   # no auth in Phase 1
                is_active=True,
            )
            await repo.add(user)
            await session.commit()
            logger.info("local_user.seeded", user_id=str(LOCAL_USER_ID))
        else:
            logger.info("local_user.exists", user_id=str(LOCAL_USER_ID))


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # In Phase 1 (local-only) allow all localhost origins via regex.
    # Phase 2: replace with explicit production origin list.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Structured error responses + traceback logging (traceback echoed only in DEBUG)
    from app.core.errors import register_exception_handlers
    register_exception_handlers(app)

    prefix = settings.API_V1_PREFIX
    app.include_router(health.router,       prefix=prefix, tags=["health"])
    app.include_router(strategies.router,   prefix=prefix, tags=["strategies"])
    app.include_router(brokers.router,      prefix=prefix)
    app.include_router(forecasting.router,  prefix=prefix, tags=["forecasting"])
    app.include_router(backtests.router,    prefix=prefix, tags=["backtests"])
    app.include_router(signals.router,      prefix=prefix, tags=["signals"])
    app.include_router(portfolio.router,    prefix=prefix)
    app.include_router(market.router,       prefix=prefix)
    app.include_router(builder.router,      prefix=prefix, tags=["builder"])
    app.include_router(orders.router,       prefix=prefix, tags=["orders"])
    app.include_router(settings_routes.router, prefix=prefix, tags=["settings"])

    # WebSocket — added directly on app to avoid router prefix issues
    from app.api.ws.router import websocket_endpoint
    app.add_api_websocket_route("/ws", websocket_endpoint)

    # Built frontend (single-container hosting) — answers only what no route matched.
    from app.api.spa import mount_spa
    mount_spa(app, settings.FRONTEND_DIST_DIR)

    return app


app = create_app()
