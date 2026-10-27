"""Read-only access to collected SQLite databases.

Agents that use WAL mode (OpenCode, Crush, Goose, Kilo, Antigravity's
conversation stores) keep recent rows in a `-wal` sidecar until a checkpoint,
so the database, its `-wal` and its `-shm` are copied together into a scratch
directory and opened there. The originals are never opened, let alone
written, which matters because SQLite would otherwise checkpoint the WAL into
the evidence copy."""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def open_copy(path: Path) -> Iterator[sqlite3.Connection]:
    path = Path(path)
    scratch = tempfile.mkdtemp(prefix="cac-sqlite-")
    try:
        target = Path(scratch) / path.name
        shutil.copyfile(path, target)
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(path) + suffix)
            if sidecar.is_file():
                shutil.copyfile(sidecar, Path(str(target) + suffix))
        connection = sqlite3.connect(str(target))
        try:
            connection.row_factory = sqlite3.Row
            yield connection
        finally:
            connection.close()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def table_names(connection: sqlite3.Connection) -> set:
    return {
        row[0] for row in connection.execute("select name from sqlite_master where type='table'")
    }


def is_sqlite(path: Path) -> bool:
    try:
        with open(path, "rb") as handle:
            return handle.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False
