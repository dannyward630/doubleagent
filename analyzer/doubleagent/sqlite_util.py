"""Open collected SQLite databases without touching the evidence copy.

An agent in WAL (write-ahead log) mode keeps recent rows in a `-wal` sidecar
until a checkpoint, so the database and its `-wal`, `-shm` and `-journal`
sidecars are copied together into a scratch directory and opened there.
The originals are never opened: SQLite would otherwise checkpoint the WAL
into the evidence copy.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def open_copy(path: Path) -> Iterator[sqlite3.Connection]:
    """Yield a connection to a scratch copy of the database and its sidecars.

    Rows come back as `sqlite3.Row`. The copy is removed when the context ends.
    """
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
    """Return the names of the database's tables."""
    return {
        row[0] for row in connection.execute("select name from sqlite_master where type='table'")
    }


def is_sqlite(path: Path) -> bool:
    """Return whether the file starts with the SQLite header."""
    try:
        with open(path, "rb") as handle:
            return handle.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False
