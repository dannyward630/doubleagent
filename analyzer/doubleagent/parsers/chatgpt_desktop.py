"""ChatGPT desktop app: the account conversation list (issue 49).

Closed source. Validated against real installs of the ChatGPT desktop
app, build 26.1013.40934 on macOS (2026-10-18) and build 26.1007.9446.0
on Windows 11 (2026-10-15), with a synthetic fixture; see
`research/chatgpt-desktop.md`. A ChatGPT-mode conversation (one started
on chatgpt.com, or replied to inside the app) leaves no transcript on
disk: its only local trace is a row the app writes at sign-in into its
own database, `.codex/sqlite/codex-dev.db`. The catalog attributes
`.codex` to `codex-cli`, so this parser lists that agent in
`reads_agents`, the routing Cody and Twinny use for an editor's
`state.vscdb`. The app's Codex-mode threads are Codex rollouts, read by
the `codex-cli` parser, which does not read this database.

* `.codex/sqlite/codex-dev.db`, SQLite in WAL mode (opened through
  `sqlite_util`, which copies the `-wal` and `-shm` sidecars with it),
  table `local_thread_catalog`, the rows whose `source_kind` is
  `chatgpt`; the `vscode` rows are the app's Codex threads, which their
  rollouts already give, and are skipped. Columns read: `thread_id` (the
  chatgpt.com conversation id), `display_title`, `source_created_at`,
  `source_updated_at` (REAL epoch seconds with a fraction),
  `conversation_origin` (empty, or `tpp`, a value the app sets whose
  meaning is not determined), `host_id`
  (`chatgpt:<workspace uuid>:<user id>`) and `source_kind`.
  Every column is read as possibly NULL; a NULL title, origin, host or
  time prints `-`.

Three `system` rows per conversation, in rowid order, each with
`session_id` the `thread_id`, `project_path`, `model` and `git_branch`
empty, `source_line` 0 and `timestamp_utc` the row's `source_updated_at`
(its `source_created_at` when that is NULL):

1. `account conversation: <display_title> origin=<conversation_origin>
   created=<UTC> updated=<UTC> host=<host_id> (from
   .codex/sqlite/codex-dev.db local_thread_catalog)`
2. `session origin: remote chatgpt.com conversation <thread_id> (listed
   at sign-in; its transcript is server-side)`, so `records_origin` is
   set and `sessions.jsonl` `origin` reads `remote`.
3. `session synced: chatgpt.com holds conversation <thread_id>, no local
   transcript`, so `records_sync` is set and `synced` reads `yes`.

The rows are a sign-in snapshot: on the macOS install a reply to one of
these conversations from inside the app did not update its row, and a
delete of a Codex-mode thread removed only that thread's `vscode` row.
The conversation's text is not on disk, so these sessions have no user
or assistant turns. No per-call permission decision, model or relay is
recorded for them. No secondary source. A file that is not SQLite, a
SQLite error, or a database without the table is one `parser:` row.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from ..inputs import Artifact
from ..model import Row
from ..sqlite_util import is_sqlite, open_copy, table_names
from ..timeutil import to_utc
from .base import Options, Parser

DB_REL = ".codex/sqlite/codex-dev.db"
TABLE = "local_thread_catalog"


def _value(value) -> str:
    """A column as row text: `-` for NULL or empty."""
    if value is None or value == "":
        return "-"
    return str(value)


class ChatGptDesktopParser(Parser):
    agent = "chatgpt-desktop"
    name = "chatgpt-desktop"
    # The database sits under `.codex`, which the catalog gives to codex-cli.
    reads_agents = ("codex-cli",)
    records_sync = True
    records_origin = True
    has_secondary = False

    def wants(self, artifact: Artifact) -> bool:
        return artifact.rel == DB_REL

    def _system(self, artifact: Artifact, session_id: str, timestamp: str, text: str) -> Row:
        row = self.base_row(artifact)
        row.turn_type = "system"
        row.session_id = session_id
        row.timestamp_utc = timestamp
        row.text = text
        return row

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        if not is_sqlite(artifact.disk_path):
            yield self._system(artifact, "", "", "parser: not a SQLite database")
            return
        try:
            with open_copy(artifact.disk_path) as connection:
                if TABLE not in table_names(connection):
                    yield self._system(artifact, "", "", "parser: no %s table" % TABLE)
                    return
                records = [
                    dict(row)
                    for row in connection.execute(
                        "select rowid as _rowid, * from %s order by rowid" % TABLE
                    )
                ]
        except sqlite3.DatabaseError as error:
            yield self._system(artifact, "", "", "parser: SQLite error: %s" % error)
            return
        for record in records:
            if record.get("source_kind") != "chatgpt":
                continue
            yield from self._conversation_rows(artifact, record)

    def _conversation_rows(self, artifact: Artifact, record: dict) -> Iterator[Row]:
        thread_id = str(record.get("thread_id") or "")
        created = to_utc(record.get("source_created_at"))
        updated = to_utc(record.get("source_updated_at"))
        timestamp = updated or created
        yield self._system(
            artifact,
            thread_id,
            timestamp,
            "account conversation: %s origin=%s created=%s updated=%s host=%s (from %s %s)"
            % (
                _value(record.get("display_title")),
                _value(record.get("conversation_origin")),
                created or "-",
                updated or "-",
                _value(record.get("host_id")),
                DB_REL,
                TABLE,
            ),
        )
        yield self._system(
            artifact,
            thread_id,
            timestamp,
            "session origin: remote chatgpt.com conversation %s"
            " (listed at sign-in; its transcript is server-side)" % _value(thread_id),
        )
        yield self._system(
            artifact,
            thread_id,
            timestamp,
            "session synced: chatgpt.com holds conversation %s, no local transcript"
            % _value(thread_id),
        )
