"""Ollama desktop chats, REPL prompt history and launcher auto-mode settings.

ollama/ollama at v0.35.1 (b0c1ca4), read from source with a synthetic
fixture; the desktop app does not exist on Linux, so no real `db.sqlite`
was checked. See `research/ollama.md`. Files, relative to the home:

* `Library/Application Support/Ollama/db.sqlite` (macOS) and
  `AppData/Local/Ollama/db.sqlite` (Windows, `%LOCALAPPDATA%`), written by
  the desktop app only, with `-wal` and `-shm` sidecars that `sqlite_util`
  reads beside the database. Schema versions 16 to 19 have the same
  transcript tables (the migrations add `settings` columns only), and no
  `settings` column is read.
  - `messages`: `id`, `chat_id`, `role` (`user`, `assistant`, `tool`,
    `system`), `content`, `thinking`, `model_name`, `created_at`,
    `tool_result` (JSON, the fallback text of a `tool` row).
  - `tool_calls`: `id`, `message_id`, `function_name`,
    `function_arguments` (a JSON string).
  - `attachments`: `message_id`, `filename`, and the byte length of
    `data`, computed in SQL so the file contents are never read.
  `created_at` is go-sqlite3's text form of a Go `time.Time`,
  `2006-01-02 15:04:05.999999999-07:00` (local time with an offset,
  trailing fraction zeros trimmed), converted to UTC.
* `.ollama/history`: the `ollama run` REPL's readline history, one entry
  per line, with no timestamp, session, working directory or model. Only
  the last 100 entries are kept, and a pasted multi-line prompt is written
  as several physical lines, so the file cannot tell one multi-line prompt
  from several prompts; each non-empty line is one row.

Rows from `db.sqlite`, ordered by `chat_id` then `messages.id` (the order
the app reads them; ids are reassigned on every save but the order is
kept): `user` rows, with `[attachment: <filename>, <n> bytes]` appended per
attachment; for an `assistant` message a `thinking` row (only with
`include_thinking`), an `assistant` row when `content` is non-empty, and
one `tool_use` row per `tool_calls` row, whose text is the `url` or
`query` argument when present, else the arguments; `tool` messages as
`tool_result`; `system` and unknown roles as `system`. An assistant
placeholder with no content, thinking or calls gives no row. There is no
call id: the n-th `tool` message after an assistant message pairs with that
message's n-th call, and `tool_use_id` is synthesised as
`<chat_id>:<tool_calls.id>`; an extra `tool` message takes the last call's
name and no id, as the app's reload does. `session_id` is the chat id,
`model` is `model_name` on assistant, thinking and tool_use rows, and
`project_path` and `git_branch` stay empty (the app has one global working
directory and no file tools). `source_line` is `messages.id`, or
`tool_calls.id` on `tool_use` rows. Messages whose chat row is gone are
still read. Model rows (issue 96): a `system` row `model: <model_name>`
before the rows of a chat's first assistant message that names a model,
and `model: <old> -> <new>` before the rows of each later assistant
message whose `model_name` differs (the model is chosen per message in the
app), with that message's time and `source_line`; an assistant placeholder
that yields no rows yields no model row either. The app asks before no
tool call, so there are no per-call permission rows; the standing settings
are below. The `users`
table (account name and email), `settings` and the
attachment bytes are never read.

Rows from `.ollama/history`: `user`, or `system` prefixed `slash command:`
for a line starting with `/`; `timestamp_utc` and `session_id` are empty,
so the rows sort after every dated row, drop out of `--since`/`--until`
unless `--keep-undated` is given, and are not in `sessions.jsonl`.
`source_line` is the line number. A line that is not valid UTF-8 (the
REPL writes the bytes typed at the prompt with `fmt.Fprintln` and checks
no encoding) is not turned into a `user` row with replacement characters:
it becomes its own `system` row
`parser: unparseable line (<decode error>): <line>`, the line as read
less its terminator (`error_rows`, issue 136), after the file's other
rows, which are still yielded (issue 174).

Standing permission rows (issue 188), source-derived from ollama/ollama at
678722224b (`cmd/config/config.go`, `cmd/launch/claude_desktop.go`) and not
observed on any real install, each a `system` row at the file's
modification time (`file_mtime`) with empty `session_id`:

* `.ollama/config.json`, the `ollama launch` configuration: for each
  `integrations.<name>` object holding an `automode` key,
  `permission setting: integrations.<name>.automode=<value> (from
  .ollama/config.json, file mtime)`. The launcher reads only the
  `claude-desktop` integration's key, as Claude Desktop's auto mode, and
  treats an absent key as true; an absent key gives no row.
* Claude Desktop's third-party profile that Ollama's launcher writes
  (`ollama launch claude-desktop`, or the macOS app's Claude Desktop
  settings, which also save the `automode` key above),
  `configLibrary/00000000-0000-4000-8000-000000000114.json` under
  `Library/Application Support/Claude-3p` (macOS; the launcher writes on
  macOS only at that commit) or `AppData/Local/Claude-3p` (the Windows
  base the launcher's restore edits). The catalog attributes it to
  `claude-desktop`, so that agent is in `reads_agents`. Its
  `autoModeEnabled` key gives `permission setting: autoModeEnabled=<value>
  (set by Ollama's Claude Desktop launcher, from <path relative to the
  home>, file mtime)`. `--restore` deletes the key, so a restored profile
  gives no row.

A config or profile that is not a JSON object is one `parser:` row.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator

from ..inputs import Artifact
from ..model import Row, compact
from ..sqlite_util import is_sqlite, open_copy, table_names
from ..timeutil import to_utc
from .base import (
    Options,
    Parser,
    compact_json,
    error_rows,
    file_mtime,
    line_text,
    setting_value,
    track_change,
)

DB_RX = re.compile(r"^(?:Library/Application Support/Ollama|AppData/Local/Ollama)/db\.sqlite$")
HISTORY_RX = re.compile(r"^\.ollama/history$")
CONFIG_RX = re.compile(r"^\.ollama/config\.json$")
# The profile id is Ollama's own (claudeDesktopProfileID).
PROFILE_RX = re.compile(
    r"^(?:Library/Application Support|AppData/Local)/Claude-3p/configLibrary/"
    r"00000000-0000-4000-8000-000000000114\.json$"
)


def call_text(arguments) -> str:
    """The `url` or `query` argument of a desktop tool call, else the
    arguments as stored."""
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
    except ValueError:
        return str(arguments or "")
    if isinstance(args, dict):
        for key in ("url", "query"):
            value = args.get(key)
            if isinstance(value, str) and value:
                return value
        return compact_json(args)
    return str(arguments or "") if isinstance(arguments, str) else compact_json(args)


def _result_fallback(value) -> str:
    if value is None or value == "" or value == "null":
        return ""
    try:
        return compact_json(json.loads(value))
    except (TypeError, ValueError):
        return str(value)


class OllamaParser(Parser):
    agent = "ollama"
    name = "ollama"
    # The Claude Desktop profile Ollama writes is under a claude-desktop base.
    reads_agents = ("claude-desktop",)

    def wants(self, artifact: Artifact) -> bool:
        rel = artifact.rel
        return any(pattern.match(rel) for pattern in (DB_RX, HISTORY_RX, CONFIG_RX, PROFILE_RX))

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        if DB_RX.match(artifact.rel):
            yield from self._parse_db(artifact, opts)
        elif CONFIG_RX.match(artifact.rel):
            yield from self._parse_config(artifact)
        elif PROFILE_RX.match(artifact.rel):
            yield from self._parse_profile(artifact)
        else:
            yield from self._parse_history(artifact)

    def _row(self, artifact: Artifact, line: int, session_id: str = "", timestamp: str = "") -> Row:
        row = self.base_row(artifact)
        row.source_line = line
        row.session_id = session_id
        row.timestamp_utc = timestamp
        return row

    def _system(self, artifact: Artifact, text: str) -> Row:
        row = self._row(artifact, 0)
        row.turn_type = "system"
        row.text = text
        return row

    # -- db.sqlite ------------------------------------------------------------------------
    def _parse_db(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        if not is_sqlite(artifact.disk_path):
            yield self._system(artifact, "parser: not a SQLite database")
            return
        try:
            with open_copy(artifact.disk_path) as connection:
                rows = list(self._db_rows(connection, artifact, opts))
        except sqlite3.DatabaseError as error:
            yield self._system(artifact, "parser: SQLite error: %s" % error)
            return
        yield from rows

    def _db_rows(
        self, connection: sqlite3.Connection, artifact: Artifact, opts: Options
    ) -> Iterator[Row]:
        tables = table_names(connection)
        if "messages" not in tables:
            return
        calls: dict[int, list[dict]] = {}
        if "tool_calls" in tables:
            for call in connection.execute(
                "select id, message_id, function_name, function_arguments"
                " from tool_calls order by message_id, id"
            ):
                calls.setdefault(call["message_id"], []).append(dict(call))
        files: dict[int, list[tuple[str, int]]] = {}
        if "attachments" in tables:
            for attachment in connection.execute(
                "select message_id, filename, length(data) as n from attachments"
                " order by message_id, id"
            ):
                files.setdefault(attachment["message_id"], []).append(
                    (attachment["filename"] or "", attachment["n"] or 0)
                )

        chat = None
        seen_model: dict[str, str] = {}
        pending: list[dict] = []  # calls of the last assistant message with calls
        used = 0
        for message in connection.execute("select * from messages order by chat_id, id"):
            message = dict(message)
            message_id = message.get("id") or 0
            session_id = str(message.get("chat_id") or "")
            if session_id != chat:
                chat, pending, used = session_id, [], 0
            role = str(message.get("role") or "")
            timestamp = to_utc(message.get("created_at"))
            content = message.get("content") or ""
            model = message.get("model_name") or ""

            if role == "user":
                row = self._row(artifact, message_id, session_id, timestamp)
                row.turn_type = "user"
                parts = [content] + [
                    "[attachment: %s, %d bytes]" % (filename, size)
                    for filename, size in files.get(message_id, [])
                ]
                row.text = compact("\n".join(part for part in parts if part))
                yield row
            elif role == "assistant":
                thinking = message.get("thinking") or ""
                if content or thinking or calls.get(message_id):
                    text = track_change("model", seen_model, session_id, model)
                    if text:
                        row = self._row(artifact, message_id, session_id, timestamp)
                        row.turn_type = "system"
                        row.model = model
                        row.text = text
                        yield row
                if thinking and opts.include_thinking:
                    row = self._row(artifact, message_id, session_id, timestamp)
                    row.turn_type = "thinking"
                    row.model = model
                    row.text = compact(thinking)
                    yield row
                if content:
                    row = self._row(artifact, message_id, session_id, timestamp)
                    row.turn_type = "assistant"
                    row.model = model
                    row.text = compact(content)
                    yield row
                message_calls = calls.get(message_id, [])
                if message_calls:
                    pending, used = message_calls, 0
                for call in message_calls:
                    row = self._row(artifact, call["id"], session_id, timestamp)
                    row.turn_type = "tool_use"
                    row.model = model
                    row.tool_name = call["function_name"] or ""
                    row.tool_use_id = "%s:%s" % (session_id, call["id"])
                    row.text = compact(call_text(call["function_arguments"]))
                    yield row
            elif role == "tool":
                row = self._row(artifact, message_id, session_id, timestamp)
                row.turn_type = "tool_result"
                if used < len(pending):
                    call = pending[used]
                    row.tool_name = call["function_name"] or ""
                    row.tool_use_id = "%s:%s" % (session_id, call["id"])
                elif pending:
                    row.tool_name = pending[-1]["function_name"] or ""
                used += 1
                row.text = compact(content or _result_fallback(message.get("tool_result")))
                yield row
            else:
                row = self._row(artifact, message_id, session_id, timestamp)
                row.turn_type = "system"
                row.text = compact(content if role == "system" else "%s: %s" % (role, content))
                yield row

    # -- .ollama/history ------------------------------------------------------------------
    def _parse_history(self, artifact: Artifact) -> Iterator[Row]:
        errors: list = []
        with open(artifact.disk_path, "rb") as handle:
            for line_number, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                try:
                    line = raw.decode("utf-8").strip()
                except UnicodeDecodeError as error:
                    errors.append((line_number, "unparseable line (%s)" % error, line_text(raw)))
                    continue
                if not line:
                    continue
                row = self._row(artifact, line_number)
                if line.startswith("/"):
                    row.turn_type = "system"
                    row.text = "slash command: " + line
                else:
                    row.turn_type = "user"
                    row.text = line
                yield row
        yield from error_rows(self, artifact, errors)

    # -- standing permissions -------------------------------------------------------------
    def _read_object(self, artifact: Artifact) -> tuple[dict | None, str]:
        try:
            document = json.loads(artifact.disk_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as error:
            return None, "parser: %s is not readable JSON (%s)" % (artifact.rel, error)
        if not isinstance(document, dict):
            return None, "parser: %s is not a JSON object" % artifact.rel
        return document, ""

    def _setting(self, artifact: Artifact, timestamp: str, text: str) -> Row:
        row = self._row(artifact, 0, "", timestamp)
        row.turn_type = "system"
        row.text = text
        return row

    def _parse_config(self, artifact: Artifact) -> Iterator[Row]:
        document, problem = self._read_object(artifact)
        if document is None:
            yield self._system(artifact, problem)
            return
        timestamp = file_mtime(artifact)
        integrations = document.get("integrations")
        if not isinstance(integrations, dict):
            return
        for name, entry in integrations.items():
            if isinstance(entry, dict) and "automode" in entry:
                yield self._setting(
                    artifact,
                    timestamp,
                    "permission setting: integrations.%s.automode=%s (from %s, file mtime)"
                    % (name, setting_value(entry["automode"]), artifact.rel),
                )

    def _parse_profile(self, artifact: Artifact) -> Iterator[Row]:
        document, problem = self._read_object(artifact)
        if document is None:
            yield self._system(artifact, problem)
            return
        if "autoModeEnabled" in document:
            yield self._setting(
                artifact,
                file_mtime(artifact),
                "permission setting: autoModeEnabled=%s (set by Ollama's Claude Desktop"
                " launcher, from %s, file mtime)"
                % (setting_value(document["autoModeEnabled"]), artifact.rel),
            )
