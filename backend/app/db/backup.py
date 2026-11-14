"""Consistent on-line backup of the SQLite database file.

Uses SQLite's own backup API (safe while the app is writing), not a file copy.
Postgres and in-memory databases are skipped — back those up with their own tools.
"""
from __future__ import annotations

import os
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional, Union

from sqlalchemy.engine import make_url

_STAMP = "%Y%m%d-%H%M%S"


def _sqlite_file(database_url: str) -> Optional[Path]:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


def _own_backups(backup_dir: Path, stem: str) -> List[Path]:
    """Only files this module wrote (`<stem>-YYYYMMDD-HHMMSS.db`), oldest first. A loose glob
    would let pruning delete unrelated files that merely share the prefix."""
    pattern = re.compile(rf"^{re.escape(stem)}-\d{{8}}-\d{{6}}\.db$")
    if not backup_dir.is_dir():
        return []
    return sorted(p for p in backup_dir.iterdir() if pattern.match(p.name))


def backup_sqlite(
    database_url: str,
    backup_dir: Union[str, Path],
    keep: int = 14,
    now: Optional[datetime] = None,
) -> Optional[Path]:
    """Write `<db-stem>-<UTC timestamp>.db` into `backup_dir`, keep the newest `keep` (min 1).

    Returns the new file, or None when there is no SQLite file to back up.
    """
    src = _sqlite_file(database_url)
    if src is None or not src.is_file():
        return None

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    dst = backup_dir / f"{src.stem}-{(now or datetime.now(timezone.utc)).strftime(_STAMP)}.db"
    tmp = dst.with_suffix(".tmp")

    # Write to a temp name and rename: a failed backup (disk full) must not leave a
    # half-written file that looks like a good one and takes a retention slot.
    try:
        with closing(sqlite3.connect(src)) as source, closing(sqlite3.connect(tmp)) as target:
            source.backup(target)
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)

    for old in _own_backups(backup_dir, src.stem)[:-max(keep, 1)]:
        old.unlink()
    return dst


def latest_backup_date(database_url: str, backup_dir: Union[str, Path]) -> Optional[date]:
    """UTC date of the newest backup, so a restart can tell today's is already done."""
    src = _sqlite_file(database_url)
    if src is None:
        return None
    backups = _own_backups(Path(backup_dir), src.stem)
    if not backups:
        return None
    return datetime.strptime(backups[-1].stem[len(src.stem) + 1:], _STAMP).date()
