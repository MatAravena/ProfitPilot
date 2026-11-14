"""Alembic is the only thing that creates or changes the schema in a real database.

The drift test is the important one: it fails as soon as an ORM model changes without
a matching migration — exactly the change `create_all` used to silently drop on an
existing database.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import command

from app.db.migrate import BASELINE_REVISION, _config, schema_drift, upgrade_to_head


def _engine(tmp_path):
    return sa.create_engine(f"sqlite:///{(tmp_path / 'm.db').as_posix()}")


def _make_legacy_database(conn):
    """What create_all produced before Alembic: the BASELINE schema with no alembic_version
    table. (Not create_all of today's models — those include columns added by later
    migrations, which a genuinely old database does not have.)"""
    command.upgrade(_config(conn), BASELINE_REVISION)
    conn.execute(sa.text("drop table alembic_version"))


def _revision(conn):
    return conn.execute(sa.text("select version_num from alembic_version")).scalar_one()


def test_migrations_build_exactly_the_orm_schema(tmp_path):
    """If this fails: you changed a model. Run, from backend/,
    `alembic revision --autogenerate -m "<what changed>"`, read the generated file, commit it."""
    with _engine(tmp_path).begin() as conn:
        upgrade_to_head(conn)
        assert schema_drift(conn) == []


def test_upgrade_is_idempotent(tmp_path):
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        upgrade_to_head(conn)
        first = _revision(conn)
    with engine.begin() as conn:
        upgrade_to_head(conn)
        assert _revision(conn) == first


def test_existing_create_all_database_is_adopted_without_data_loss(tmp_path):
    """Databases made before Alembic (the dev DB, an early box) have the tables but no
    alembic_version. They are stamped at the baseline, then upgraded — never recreated."""
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        _make_legacy_database(conn)
        conn.execute(sa.text(
            "insert into users (id, email, username, hashed_password, is_active) "
            "values ('00000000000000000000000000000001', 'a@b.c', 'u', '', 1)"
        ))

    with engine.begin() as conn:
        upgrade_to_head(conn)

    with engine.begin() as conn:
        assert conn.execute(sa.text("select count(*) from users")).scalar_one() == 1
        assert _revision(conn) is not None
        assert schema_drift(conn) == []


def test_adopted_database_missing_an_index_is_repaired(tmp_path):
    """The real dev DB lost ix_strategy_instances_user_id in a July table rebuild."""
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        _make_legacy_database(conn)
        conn.execute(sa.text("drop index ix_strategy_instances_user_id"))

    with engine.begin() as conn:
        upgrade_to_head(conn)
        assert schema_drift(conn) == []


def test_baseline_stamp_only_applies_to_pre_alembic_databases(tmp_path):
    engine = _engine(tmp_path)
    with engine.begin() as conn:
        upgrade_to_head(conn)
        head = _revision(conn)
    assert head >= BASELINE_REVISION
