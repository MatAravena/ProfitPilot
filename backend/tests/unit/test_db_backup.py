"""SQLite backup: a consistent copy, pruned to the newest N, no-op for non-file DBs."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

from app.db.backup import backup_sqlite, latest_backup_date


def _make_db(path):
    con = sqlite3.connect(path)
    con.execute("create table t (x integer)")
    con.execute("insert into t values (7)")
    con.commit()
    con.close()


def test_backup_is_a_readable_copy(tmp_path):
    src = tmp_path / "profitpilot.db"
    _make_db(src)

    out = backup_sqlite(f"sqlite+aiosqlite:///{src.as_posix()}", tmp_path / "backups",
                        now=datetime(2026, 11, 13, 7, 0, tzinfo=timezone.utc))

    assert out is not None and out.name == "profitpilot-20261113-070000.db"
    con = sqlite3.connect(out)
    assert con.execute("select x from t").fetchall() == [(7,)]
    con.close()


def test_backup_keeps_only_the_newest_n(tmp_path):
    src = tmp_path / "profitpilot.db"
    _make_db(src)
    url = f"sqlite+aiosqlite:///{src.as_posix()}"

    for day in (10, 11, 12, 13):
        backup_sqlite(url, tmp_path / "b", keep=2, now=datetime(2026, 11, day, tzinfo=timezone.utc))

    assert sorted(p.name for p in (tmp_path / "b").iterdir()) == [
        "profitpilot-20261112-000000.db", "profitpilot-20261113-000000.db",
    ]


def test_pruning_never_touches_files_it_did_not_write(tmp_path):
    src = tmp_path / "profitpilot.db"
    _make_db(src)
    bdir = tmp_path / "b"
    bdir.mkdir()
    for foreign in ("profitpilot-old.db", "profitpilot-test.db", "profitpilot-2.db"):
        (bdir / foreign).write_text("mine")

    out = backup_sqlite(f"sqlite+aiosqlite:///{src.as_posix()}", bdir, keep=1,
                        now=datetime(2026, 11, 13, tzinfo=timezone.utc))

    assert out is not None and out.is_file(), "the backup just written must survive pruning"
    assert len(list(bdir.iterdir())) == 4


def test_keep_below_one_still_keeps_the_newest(tmp_path):
    src = tmp_path / "profitpilot.db"
    _make_db(src)
    url = f"sqlite+aiosqlite:///{src.as_posix()}"

    for day in (12, 13):
        backup_sqlite(url, tmp_path / "b", keep=0, now=datetime(2026, 11, day, tzinfo=timezone.utc))

    assert [p.name for p in (tmp_path / "b").iterdir()] == ["profitpilot-20261113-000000.db"]


def test_latest_backup_date_reads_the_newest_stamp(tmp_path):
    src = tmp_path / "profitpilot.db"
    _make_db(src)
    url = f"sqlite+aiosqlite:///{src.as_posix()}"
    assert latest_backup_date(url, tmp_path / "b") is None

    backup_sqlite(url, tmp_path / "b", now=datetime(2026, 11, 12, 7, tzinfo=timezone.utc))
    backup_sqlite(url, tmp_path / "b", now=datetime(2026, 11, 13, 7, tzinfo=timezone.utc))

    assert latest_backup_date(url, tmp_path / "b") == date(2026, 11, 13)


def test_non_file_databases_are_skipped(tmp_path):
    assert backup_sqlite("sqlite+aiosqlite:///:memory:", tmp_path / "b") is None
    assert backup_sqlite("postgresql+asyncpg://u:p@localhost/db", tmp_path / "b") is None
    assert not (tmp_path / "b").exists()
