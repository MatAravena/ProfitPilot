"""Bring a database schema to the latest Alembic revision on startup.

Replaces `create_all`, which only creates missing tables and never alters an existing
one — so a model change would silently not reach a database that already holds data.

Works on a *sync* connection; the app calls it through `AsyncConnection.run_sync`.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import structlog
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Connection

logger = structlog.get_logger(__name__)

# The revision whose schema equals what `create_all` produced before Alembic existed.
BASELINE_REVISION = "0001"

_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _config(connection: Connection) -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "migrations"))
    cfg.attributes["connection"] = connection
    return cfg


def upgrade_to_head(connection: Connection) -> None:
    cfg = _config(connection)
    tables = set(inspect(connection).get_table_names())
    if "alembic_version" not in tables and "users" in tables:
        # Pre-Alembic database made by create_all: adopt it at the baseline instead of
        # trying to create tables that already exist. Data is untouched.
        logger.info("db.migrate.adopting_existing_database", baseline=BASELINE_REVISION)
        command.stamp(cfg, BASELINE_REVISION)
    command.upgrade(cfg, "head")

    drift = schema_drift(connection)
    if drift:
        # Most likely a model changed without a migration. The app still starts — the
        # guard test in tests/unit/test_migrations.py is what blocks this in CI.
        logger.warning("db.migrate.schema_drift", differences=[str(d) for d in drift][:20])


def schema_drift(connection: Connection) -> List[tuple]:
    """Differences between the live schema and the ORM models (empty = in sync)."""
    from app.db.base import Base
    import app.models.db  # noqa: F401 — registers every ORM model on Base.metadata

    ctx = MigrationContext.configure(connection, opts={"compare_type": True})
    return compare_metadata(ctx, Base.metadata)
