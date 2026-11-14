"""Alembic environment.

Two entry points:
  * the app on startup (`app.db.migrate`) passes an open connection in
    `config.attributes["connection"]` — that path never opens its own engine;
  * the `alembic` CLI, which connects with the app's DATABASE_URL.
"""
from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.base import Base
import app.models.db  # noqa: F401 — registers every ORM model on Base.metadata

target_metadata = Base.metadata


def _configure_and_run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,       # SQLite can't ALTER most things; batch mode copies the table
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_cli() -> None:
    from app.core.config import get_settings
    engine = create_async_engine(get_settings().DATABASE_URL)
    async with engine.connect() as conn:
        await conn.run_sync(_configure_and_run)
        await conn.commit()
    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline (--sql) mode is not supported; run against a database.")

connection = context.config.attributes.get("connection")
if connection is not None:
    _configure_and_run(connection)
else:
    asyncio.run(_run_cli())
