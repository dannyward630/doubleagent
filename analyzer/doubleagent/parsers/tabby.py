"""Tabby server chat threads and completion events.

Tabby (TabbyML/tabby, checked at 21b2904) is a self-hosted completion and
chat server, so its transcripts live under the server account's home, not
the developer's: the `user` column is the account the server ran as, and the
person who chatted is named in the thread's `system` row. See
`research/tabby.md`.

Files, relative to the home directory. A server root collected from a
Docker or Podman named volume (the `tabby|*tabby*` volume line; the images
set `TABBY_ROOT=/data`) has the volume's `_data` as its base, so the
leading `.tabby/` is absent there and the paths start at `ee/`, `events/`
or `config.toml` (issue 124; source-derived, not observed on any real
install):

* `.tabby/ee/db.sqlite` (production builds) or `.tabby/ee/dev-db.sqlite`
  (source builds), with `-wal` and `-shm` sidecars (WAL mode). Read through
  `sqlite_util.open_copy`; only these columns are selected, each only if the
  table has it:
  - `users`: `id`, `email`, `name` (owner of a thread or event).
  - `threads`: `id`, `is_ephemeral`, `user_id`, `created_at`, `updated_at`,
    `relevant_questions` (JSON array of strings).
  - `thread_messages`: `id`, `thread_id`, `role` (`user`, `assistant`),
    `content` (Markdown), `code_source_id`, `attachment` (JSON with `code[]`
    {`git_url`, `commit`, `filepath`, `start_line`}, `client_code[]`
    {`filepath`, `start_line`}, `doc[]` {`title`, `link`, `page_link`,
    `sha`}, `code_file_list` {`file_list`}), `created_at`. Backups made before
    0.25 have no `attachment` column; their `code_attachments`,
    `client_code_attachments` and `doc_attachments` arrays are read instead.
  - `user_events`: `id`, `user_id`, `kind`, `created_at`, `payload` (the
    pretty-printed event, same shape as an event log line's `event`).
  - `pages`: `id`, `author_id`, `title`, `content`, `code_source_id`,
    `created_at`; `page_sections`: `id`, `page_id`, `title`, `content`,
    `position`, `attachment` (the `thread_messages` attachment JSON),
    `created_at`. AI-written pages, which outlive the thread they were made
    from (issue 211; source-derived, not observed on any real install).
  - `integrations`: `id`, `kind` (`github`, `gitlab`, `github_self_hosted`,
    `gitlab_self_hosted`), `display_name`, `api_base`, `created_at`;
    `provided_repositories`: `id`, `integration_id`, `name`, `git_url`,
    `active`, `updated_at`. The source-host integrations and the repository
    list cached from them (source-derived, not observed on any real install).
* `.tabby/ee/db.backup-YYYYMMDD.sqlite` and `dev-db.backup-YYYYMMDD.sqlite`:
  copies made before each schema migration. Parsed like the live database,
  with a leading `system` row naming the backup file, because ephemeral
  threads untouched for 7 days are deleted from the live database and may
  survive only here. A secondary source (issue 122): its rows are copies of
  the live database's, with the same thread ids, texts and times, so
  `dedup.deduplicate` drops those the live database (or an earlier backup)
  still holds and keeps the rest; the leading row names the file and so
  never pairs.
* `.tabby/events/YYYY-MM-DD.json`: JSON Lines, one `LogEntry` per line:
  `user` (encoded server user id or null), `ts` (Unix milliseconds), `event`
  (externally tagged): `completion` {`completion_id`, `language`, `prompt`,
  `segments` {`git_url`, `filepath`}, `choices[]` {`index`, `text`},
  `user_agent`}; `view`, `select`, `dismiss` {`completion_id`,
  `choice_index`, `view_id`, `elapsed`, `kind`}; `chat_completion` {}.
  A secondary source (issue 122): the server hands every event to both
  loggers (`ComposedLogger`), and the database logger writes it to
  `user_events` when the event names a server user, with `ts` truncated to
  whole seconds, so a `user_events` row is the same event as a log line.
  The database is the primary store because it is the one Tabby reads
  back (its user-event service queries `user_events`; nothing reads the log)
  and because the parser can only mark whole files, and the database file
  also holds the threads. Each log row carries its own millisecond time,
  within a second of the database's, so the default 2-second window
  applies. The log keeps what the database lacks: events with no user,
  events of a server run without the database, and events older than the
  three months `user_events` retains; those rows have no twin and are kept.
  Only the `user` and `assistant` rows pair: the `system` rows name the
  owner as the log's encoded id there and as the account's email in the
  database, so their texts differ and both copies are kept. The evidence
  is in the "What survives a delete" part of the research
  document's Transcript stores.
* `.tabby/config.toml`: `[model.<completion|chat|embedding>.http]` with
  `kind`, `model_name`, `api_endpoint`, `supported_models`, or
  `[model.<group>.local]` with `model_id`. One `system` row per configured
  model at the file's modification time; `api_key` is never read into a row.
  Read with `tomllib` (Python 3.11 or later); on 3.10 one `parser:` row says
  the tables were not read (issue 211; source-derived, not observed on any
  real install).
* `<IDE config dir>/options/intellij-tabby-command-history.xml` under
  `.config/JetBrains/<product>`, `Library/Application Support/JetBrains/
  <product>` or `AppData/Roaming/JetBrains/<product>`: the IntelliJ plugin's
  `CommandHistory` component, its `history` option a list of up to 30
  inline-edit instructions, newest first, with no times. Every `value`
  attribute under that option is read. Whether the IDE writes the file there
  or to the project's `.idea/` is not determined from source. A secondary
  source with empty timestamps (issue 211; source-derived, not observed on
  any real install).
* `<editor User dir>/globalStorage/state.vscdb` of `vscode` and its forks
  (`reads_agents`): the `ItemTable` row `TabbyML.vscode-tabby`, its
  `edit.recentlyCommand` list of `JSON.stringify({command, context[]})`
  strings (`context[].uri`), newest first, with no times. Nothing else of
  the row is read: it also holds the endpoint tokens. A secondary source
  with empty timestamps (issue 211; source-derived, not observed on any
  real install).

The database also stores plaintext secrets (`users.auth_token`,
`users.password_encrypted`, `registration_token`, `refresh_tokens`,
`integrations.access_token`, `email_setting.smtp_password`,
`oauth_credential.client_secret`, `ldap_credential.bind_password`). Those
columns are never selected, and of those tables only `users` and
`integrations` are read, through the whitelisted columns above.

Rows: per thread one `system` row (owner email and name, ephemeral flag,
relevant questions) then one `user` or `assistant` row per message, with an
attachment summary appended to the text. `session_id` is the thread id;
`project_path` is the first `code[].git_url` attached anywhere in the thread
(a repository URL: Tabby records no local working directory). Per completion
event one `system` row (server user, language, file, client), one `user` row
with the full prompt and one `assistant` row per choice; `session_id` is the
`completion_id` and `project_path` is `segments.git_url`. View, select,
dismiss and chat-completion events are `system` rows. Database timestamps
are UTC text with second precision; event log times are milliseconds;
`user_events` rows carry the second-precision `created_at`. Per page one
`system` row (`page start`, title, author, code source) and `assistant`
rows for its content and sections, `session_id` `page:<id>`. Per
integration `source host: <host> integration <display_name> kind=<kind>
api_base=<api_base> (account not recorded; from integrations table,
created_at)` and per cached repository `source host repository: <git_url>
type=<kind> name=<name> active=<yes|no> (integration <display_name>; from
provided_repositories table, updated_at)`, at their own times. Per
configured model `model configured: <group> <model_name or model_id> via
<http|local>[ kind=<kind>][ endpoint=<api_endpoint>][
supported_models=<a,b>] (from config.toml [model.<group>.<http|local>],
file mtime)`. Per command history `inline edit command history: <N>
commands, newest first (from <source>, no times)` then one `user` row per
command, `source_line` its 1-based position. No model per message, tool
calls, thinking or git branch are recorded.
"""

from __future__ import annotations

import json
import re
import sqlite3
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from urllib.parse import urlparse

from ..inputs import Artifact
from ..model import Row, compact
from ..sqlite_util import is_sqlite, open_copy, table_names
from ..timeutil import to_utc
from ..vscode_state import EDITOR_AGENTS, STATE_DB_RX, read_item
from .base import Options, Parser, compact_json, error_rows, file_mtime, iter_jsonl
from .codex import flat_toml, load_toml

# The server root a path starts with: `.tabby/` under a user's home, or
# nothing when the collection base is a Docker or Podman named volume's
# `_data` (the `tabby|*tabby*` volume line), which holds the server root
# itself, since the images set `TABBY_ROOT=/data` (issue 124).
ROOT = r"(?:\.tabby/)?"
DB_RX = re.compile(r"^%see/(?:dev-)?db\.sqlite$" % ROOT)
BACKUP_RX = re.compile(r"^%see/(?:dev-)?db\.backup-[^/]+\.sqlite$" % ROOT)
EVENTS_RX = re.compile(r"^%sevents/\d{4}-\d{2}-\d{2}\.json$" % ROOT)
CONFIG_RX = re.compile(r"^%sconfig\.toml$" % ROOT)
# The IntelliJ plugin's inline-edit command history, in the IDE's `options/`
# directory where the catalog's `intellij-tabby*.xml` lines collect it.
INTELLIJ_HISTORY_RX = re.compile(
    r"(?:^|/)JetBrains/[^/]+/options/intellij-tabby-command-history\.xml$"
)
INTELLIJ_HISTORY_COMPONENT = "com.tabbyml.intellijtabby.inlineChat.CommandHistory"
# The VS Code extension's global state row in the editor's state.vscdb.
VSCODE_ITEM_KEY = "TabbyML.vscode-tabby"
VSCODE_HISTORY_KEY = "edit.recentlyCommand"
MODEL_GROUPS = ("completion", "chat", "embedding")

# The only columns ever read. No secret-bearing column is listed: of the
# tables holding one, `users` and `integrations` are read without it.
COLUMNS = {
    "users": ("id", "email", "name"),
    "threads": ("id", "is_ephemeral", "user_id", "created_at", "updated_at", "relevant_questions"),
    "thread_messages": (
        "id",
        "thread_id",
        "role",
        "content",
        "code_source_id",
        "attachment",
        "code_attachments",
        "client_code_attachments",
        "doc_attachments",
        "created_at",
    ),
    "user_events": ("id", "user_id", "kind", "created_at", "payload"),
    "pages": ("id", "author_id", "title", "content", "code_source_id", "created_at"),
    "page_sections": ("id", "page_id", "title", "content", "position", "attachment", "created_at"),
    # `integrations.access_token` is never selected.
    "integrations": ("id", "kind", "display_name", "api_base", "created_at"),
    "provided_repositories": ("id", "integration_id", "name", "git_url", "active", "updated_at"),
}
# The host a source-host integration of each kind talks to; self-hosted kinds
# take the host of their `api_base` (integration.rs:79-93).
INTEGRATION_HOSTS = {"github": "github.com", "gitlab": "gitlab.com"}


def _json(value, default):
    if value is None or value == "":
        return default
    if isinstance(value, (bytes, bytearray)):
        value = bytes(value).decode("utf-8", errors="replace")
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except ValueError:
        return default


def _join(*parts: str) -> str:
    return " | ".join(part for part in parts if part)


def _list(value) -> list:
    return value if isinstance(value, list) else []


def _select(con: sqlite3.Connection, table: str, order: str) -> Iterator[dict]:
    """Rows of `table` restricted to the whitelisted columns it has."""
    have = {row[1] for row in con.execute("pragma table_info(%s)" % table)}
    cols = [column for column in COLUMNS[table] if column in have]
    if not cols:
        return
    order_cols = [column for column in order.split(",") if column.strip() in have]
    sql = "select %s from %s" % (", ".join(cols), table)
    if order_cols:
        sql += " order by " + ", ".join(order_cols)
    for row in con.execute(sql):
        yield dict(zip(cols, row, strict=False))


def _loc(filepath, start_line) -> str:
    path_text = str(filepath or "")
    return (
        "%s:%s" % (path_text, start_line)
        if path_text and start_line not in (None, "")
        else path_text
    )


def attachment_parts(att: dict) -> list[str]:
    """Short descriptions of what was attached to a message."""
    parts: list[str] = []
    for code in _list(att.get("code")):
        if isinstance(code, dict):
            repo = str(code.get("git_url") or "")
            if code.get("commit"):
                repo += "@" + str(code["commit"])
            parts.append(
                _join("code", repo, _loc(code.get("filepath"), code.get("start_line"))).replace(
                    " | ", " "
                )
            )
    for code in _list(att.get("client_code")):
        if isinstance(code, dict):
            parts.append(
                ("client_code " + _loc(code.get("filepath"), code.get("start_line"))).strip()
            )
    for doc in _list(att.get("doc")):
        if isinstance(doc, dict):
            label = doc.get("title") or doc.get("sha") or ""
            link = doc.get("link") or doc.get("page_link") or ""
            parts.append(_join("doc", str(label), str(link)).replace(" | ", " "))
    file_list = att.get("code_file_list")
    if isinstance(file_list, dict) and isinstance(file_list.get("file_list"), list):
        parts.append("code_file_list %d files" % len(file_list["file_list"]))
    return parts


def message_attachment(message: dict) -> dict:
    att = _json(message.get("attachment"), None)
    if isinstance(att, dict):
        return att
    # Pre-0.25 databases (threads.rs:34-38): separate columns, no `attachment`.
    return {
        "code": _json(message.get("code_attachments"), None),
        "client_code": _json(message.get("client_code_attachments"), None),
        "doc": _json(message.get("doc_attachments"), None),
    }


def first_git_url(att: dict) -> str:
    for code in _list(att.get("code")):
        if isinstance(code, dict) and code.get("git_url"):
            return str(code["git_url"])
    return ""


def _model_text(group: str, kind: str, body: dict) -> str:
    """`model configured:` text for one `[model.<group>.<kind>]` table: the
    `http` form's `model_name`, `kind`, `api_endpoint` and `supported_models`,
    or the `local` form's `model_id`. `api_key` is never read."""
    if kind == "http":
        supported = body.get("supported_models")
        detail = " ".join(
            part
            for part in (
                "kind=%s" % body["kind"] if body.get("kind") else "",
                "endpoint=%s" % body["api_endpoint"] if body.get("api_endpoint") else "",
                "supported_models=%s" % ",".join(str(part) for part in supported)
                if isinstance(supported, list) and supported
                else "",
            )
            if part
        )
        model = body.get("model_name")
    else:
        detail = ""
        model = body.get("model_id")
    return "model configured: %s %s via %s%s (from config.toml [model.%s.%s], file mtime)" % (
        group,
        model or "-",
        kind,
        " " + detail if detail else "",
        group,
        kind,
    )


def _command_text(item) -> str:
    """One `edit.recentlyCommand` entry: `JSON.stringify({command, context})`,
    or a bare command string (quickPick.ts:322-351), as row text with the
    context files' URIs appended."""
    cmd = _json(item, None) if isinstance(item, str) else item
    if isinstance(cmd, dict) and cmd.get("command"):
        text = str(cmd["command"])
        files = [
            str(context.get("uri"))
            for context in _list(cmd.get("context"))
            if isinstance(context, dict) and context.get("uri")
        ]
        return "%s [context: %s]" % (text, "; ".join(files)) if files else text
    if item in (None, ""):
        return ""
    return item if isinstance(item, str) else compact_json(item)


class TabbyParser(Parser):
    agent = "tabby"
    name = "tabby"
    has_secondary = True
    # The VS Code extension's command history is a row of the editor's
    # state.vscdb, which the catalog attributes to the editor.
    reads_agents = EDITOR_AGENTS

    def _own(self, artifact: Artifact) -> bool:
        # A stand-in artifact with no agent (a wants() test) counts as own.
        return getattr(artifact, "agent", self.agent) == self.agent

    def wants(self, artifact: Artifact) -> bool:
        rel = artifact.rel
        if not self._own(artifact):
            return bool(STATE_DB_RX.search(rel))
        return bool(
            DB_RX.match(rel)
            or BACKUP_RX.match(rel)
            or EVENTS_RX.match(rel)
            or CONFIG_RX.match(rel)
            or INTELLIJ_HISTORY_RX.search(rel)
        )

    def secondary(self, artifact: Artifact) -> bool:
        rel = artifact.rel
        if not self._own(artifact):
            return bool(STATE_DB_RX.search(rel))
        return bool(BACKUP_RX.match(rel) or EVENTS_RX.match(rel) or INTELLIJ_HISTORY_RX.search(rel))

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        rel = artifact.rel
        if not self._own(artifact):
            yield from self._parse_vscode_state(artifact, opts)
        elif EVENTS_RX.match(rel):
            yield from self._parse_events(artifact, opts)
        elif CONFIG_RX.match(rel):
            yield from self._parse_config(artifact, opts)
        elif INTELLIJ_HISTORY_RX.search(rel):
            yield from self._parse_intellij_history(artifact, opts)
        else:
            yield from self._parse_db(artifact, opts, bool(BACKUP_RX.match(rel)))

    def _row(
        self,
        artifact: Artifact,
        line: int,
        session_id: str = "",
        project_path: str = "",
        timestamp: str = "",
        turn_type: str = "system",
        text: str = "",
        opts: Options | None = None,
    ) -> Row:
        row = self.base_row(artifact)
        row.source_line = line
        row.session_id = session_id
        row.project_path = project_path
        row.timestamp_utc = timestamp
        row.turn_type = turn_type
        row.text = compact(text)
        return row

    # -- db.sqlite and its backups -------------------------------------------------------
    def _parse_db(self, artifact: Artifact, opts: Options, backup: bool) -> Iterator[Row]:
        if not is_sqlite(artifact.disk_path):
            yield self._row(artifact, 0, text="parser: not a SQLite database")
            return
        if backup:
            yield self._row(
                artifact,
                0,
                opts=opts,
                text=(
                    "backup database %s copied before a schema migration; it can hold threads and "
                    "events since deleted from the live database" % artifact.rel.rsplit("/", 1)[-1]
                ),
            )
        try:
            with open_copy(artifact.disk_path) as con:
                tables = table_names(con)
                users: dict[str, str] = {}
                if "users" in tables:
                    for user in _select(con, "users", "id"):
                        label = str(user.get("email") or "")
                        if user.get("name"):
                            label = (
                                "%s (%s)" % (label, user["name"]) if label else str(user["name"])
                            )
                        users[str(user.get("id"))] = label
                if "threads" in tables:
                    yield from self._threads(artifact, con, tables, users, opts)
                if "pages" in tables:
                    yield from self._pages(artifact, con, tables, users, opts)
                if "user_events" in tables:
                    yield from self._user_events(artifact, con, users, opts)
                if "integrations" in tables:
                    yield from self._integrations(artifact, con, tables, opts)
        except sqlite3.DatabaseError as error:
            yield self._row(artifact, 0, text="parser: SQLite error: %s" % error)

    def _threads(
        self,
        artifact: Artifact,
        con: sqlite3.Connection,
        tables: set,
        users: dict[str, str],
        opts: Options,
    ) -> Iterator[Row]:
        messages: dict[str, list[dict]] = {}
        if "thread_messages" in tables:
            for message in _select(con, "thread_messages", "thread_id,created_at,id"):
                messages.setdefault(str(message.get("thread_id")), []).append(message)
        threads = list(_select(con, "threads", "created_at,id"))
        known = {str(thread.get("id")) for thread in threads}
        # Messages whose thread row is gone still get parsed, under their thread id.
        threads += [{"id": tid} for tid in messages if tid not in known]
        for thread in threads:
            tid = str(thread.get("id"))
            msgs = messages.get(tid, [])
            atts = [message_attachment(message) for message in msgs]
            project = next(
                (url for url in (first_git_url(attachment) for attachment in atts) if url), ""
            )
            questions = [
                str(question) for question in _list(_json(thread.get("relevant_questions"), None))
            ]
            owner = users.get(str(thread.get("user_id")), "")
            yield self._row(
                artifact,
                int(thread["id"]) if str(thread.get("id")).isdigit() else 0,
                tid,
                project,
                to_utc(thread.get("created_at")),
                opts=opts,
                text=_join(
                    "thread start",
                    "owner %s" % owner
                    if owner
                    else (
                        "owner user_id=%s" % thread["user_id"]
                        if thread.get("user_id") is not None
                        else ""
                    ),
                    "ephemeral" if thread.get("is_ephemeral") else "",
                    "thread row missing" if "user_id" not in thread else "",
                    "relevant questions: " + "; ".join(questions) if questions else "",
                ),
            )
            for message, att in zip(msgs, atts, strict=False):
                role = str(message.get("role") or "")
                text = str(message.get("content") or "")
                parts = attachment_parts(att)
                if message.get("code_source_id"):
                    parts.insert(0, "code_source %s" % message["code_source_id"])
                if parts:
                    text = "%s [attachments: %s]" % (text, "; ".join(parts))
                if role not in ("user", "assistant"):
                    text = "%s: %s" % (role, text)
                yield self._row(
                    artifact,
                    message.get("id") or 0,
                    tid,
                    project,
                    to_utc(message.get("created_at")),
                    role if role in ("user", "assistant") else "system",
                    text,
                    opts,
                )

    def _user_events(
        self, artifact: Artifact, con: sqlite3.Connection, users: dict[str, str], opts: Options
    ) -> Iterator[Row]:
        for user_event in _select(con, "user_events", "created_at,id"):
            line = user_event.get("id") or 0
            timestamp = to_utc(user_event.get("created_at"))
            owner = "user=%s" % (
                users.get(str(user_event.get("user_id")), "") or user_event.get("user_id")
            )
            event = _json(user_event.get("payload"), None)
            if not isinstance(event, dict):
                yield self._row(
                    artifact,
                    line,
                    timestamp=timestamp,
                    opts=opts,
                    text="parser: user_event %s payload did not parse" % user_event.get("id"),
                )
                continue
            yield from self._event_rows(
                artifact, line, timestamp, owner, event, opts, str(user_event.get("kind") or "")
            )

    def _pages(
        self,
        artifact: Artifact,
        con: sqlite3.Connection,
        tables: set,
        users: dict[str, str],
        opts: Options,
    ) -> Iterator[Row]:
        """AI-written pages (page.rs:92-150): one `system` row per page, then
        its content and each section, in position order, as `assistant` rows."""
        sections: dict[str, list[dict]] = {}
        if "page_sections" in tables:
            for sec in _select(con, "page_sections", "page_id,position,id"):
                sections.setdefault(str(sec.get("page_id")), []).append(sec)
        pages = list(_select(con, "pages", "created_at,id"))
        known = {str(page.get("id")) for page in pages}
        # Sections whose page row is gone still get parsed, under their page id.
        pages += [{"id": pid} for pid in sections if pid not in known]
        for page in pages:
            pid = str(page.get("id"))
            line = int(pid) if pid.isdigit() else 0
            sid = "page:%s" % pid
            secs = sections.get(pid, [])
            atts = [_json(sec.get("attachment"), {}) for sec in secs]
            atts = [attachment if isinstance(attachment, dict) else {} for attachment in atts]
            project = next(
                (url for url in (first_git_url(attachment) for attachment in atts) if url), ""
            )
            timestamp = to_utc(page.get("created_at"))
            owner = users.get(str(page.get("author_id")), "")
            if owner:
                author = "author %s" % owner
            elif page.get("author_id") is not None:
                author = "author user_id=%s" % page["author_id"]
            else:
                author = ""
            yield self._row(
                artifact,
                line,
                sid,
                project,
                timestamp,
                opts=opts,
                text=_join(
                    "page start",
                    "title %s" % page["title"] if page.get("title") else "",
                    author,
                    "code_source %s" % page["code_source_id"] if page.get("code_source_id") else "",
                    "page row missing" if "author_id" not in page else "",
                ),
            )
            if page.get("content"):
                yield self._row(
                    artifact, line, sid, project, timestamp, "assistant", str(page["content"]), opts
                )
            for sec, att in zip(secs, atts, strict=False):
                text = "\n\n".join(
                    str(part)
                    for part in (sec.get("title"), sec.get("content"))
                    if part not in (None, "")
                )
                parts = attachment_parts(att)
                if parts:
                    text = "%s [attachments: %s]" % (text, "; ".join(parts))
                yield self._row(
                    artifact,
                    sec.get("id") or 0,
                    sid,
                    project,
                    to_utc(sec.get("created_at")) or timestamp,
                    "assistant",
                    text,
                    opts,
                )

    def _integrations(
        self, artifact: Artifact, con: sqlite3.Connection, tables: set, opts: Options
    ) -> Iterator[Row]:
        """Source-host integrations and the repositories cached from them
        (schema.sql:142-165). The token column is never selected."""
        names: dict[str, tuple[str, str]] = {}
        for i in _select(con, "integrations", "created_at,id"):
            kind = str(i.get("kind") or "")
            api_base = str(i.get("api_base") or "")
            host = INTEGRATION_HOSTS.get(kind) or urlparse(api_base).hostname or "-"
            name = str(i.get("display_name") or "")
            names[str(i.get("id"))] = (name, kind)
            yield self._row(
                artifact,
                i.get("id") or 0,
                timestamp=to_utc(i.get("created_at")),
                opts=opts,
                text="source host: %s integration %s kind=%s api_base=%s (account not recorded; "
                "from integrations table, created_at)"
                % (host, name or "-", kind or "-", api_base or "-"),
            )
        if "provided_repositories" not in tables:
            return
        for repository in _select(con, "provided_repositories", "integration_id,id"):
            name, kind = names.get(str(repository.get("integration_id")), ("", ""))
            yield self._row(
                artifact,
                repository.get("id") or 0,
                timestamp=to_utc(repository.get("updated_at")),
                opts=opts,
                text="source host repository: %s type=%s name=%s active=%s (integration %s; "
                "from provided_repositories table, updated_at)"
                % (
                    repository.get("git_url") or "-",
                    kind or "-",
                    repository.get("name") or "-",
                    "yes" if repository.get("active") else "no",
                    name or "integration_id=%s" % repository.get("integration_id"),
                ),
            )

    # -- config.toml ---------------------------------------------------------------------
    def _parse_config(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        """One `system` row per configured model (config.rs:259-342), at the
        file's modification time. Only the model tables' names, kinds and
        endpoints are read; `api_key` never reaches a row."""
        timestamp = file_mtime(artifact)
        if load_toml is flat_toml:
            # flat_toml reads only the top-level keys; the model tables need tomllib.
            yield self._row(
                artifact,
                0,
                timestamp=timestamp,
                opts=opts,
                text="parser: config.toml model tables not read: Python 3.11 or later needed",
            )
            return
        try:
            data = load_toml(artifact.disk_path.read_text(encoding="utf-8", errors="replace"))
        except ValueError as error:
            # tomllib's message names a line and column, never the value.
            yield self._row(
                artifact,
                0,
                timestamp=timestamp,
                opts=opts,
                text="parser: config.toml is not valid TOML (%s)" % error,
            )
            return
        models = data.get("model") if isinstance(data, dict) else None
        if not isinstance(models, dict):
            return
        for group in MODEL_GROUPS:
            conf = models.get(group)
            if not isinstance(conf, dict):
                continue
            for kind in ("http", "local"):
                body = conf.get(kind)
                if isinstance(body, dict):
                    yield self._row(
                        artifact,
                        0,
                        timestamp=timestamp,
                        opts=opts,
                        text=_model_text(group, kind, body),
                    )

    # -- editor command histories ----------------------------------------------------------
    def _history_rows(
        self, artifact: Artifact, source: str, commands: list[str], opts: Options
    ) -> Iterator[Row]:
        """A leading `system` row, then one `user` row per command, newest
        first, with no timestamp: the histories record none."""
        yield self._row(
            artifact,
            0,
            opts=opts,
            text="inline edit command history: %d commands, newest first (from %s, no times)"
            % (len(commands), source),
        )
        for index, cmd in enumerate(commands, 1):
            yield self._row(artifact, index, turn_type="user", text=cmd, opts=opts)

    def _parse_intellij_history(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        try:
            root = ET.parse(artifact.disk_path).getroot()
        except (ET.ParseError, OSError) as error:
            yield self._row(
                artifact, 0, opts=opts, text="parser: not a readable XML document (%s)" % error
            )
            return
        commands: list[str] = []
        for comp in root.iter("component"):
            if comp.get("name") != INTELLIJ_HISTORY_COMPONENT:
                continue
            for opt in comp.iter("option"):
                if opt.get("name") == "history":
                    commands += [
                        str(element.get("value"))
                        for element in opt.iter()
                        if element is not opt and element.get("value") is not None
                    ]
        if commands:
            yield from self._history_rows(
                artifact, "intellij-tabby-command-history.xml", commands, opts
            )

    def _parse_vscode_state(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        state, problems = read_item(artifact.disk_path, VSCODE_ITEM_KEY)
        if isinstance(state, dict):
            history = state.get(VSCODE_HISTORY_KEY)
            commands = [
                command for command in (_command_text(i) for i in _list(history)) if command
            ]
            if commands:
                source = "state.vscdb %s %s" % (VSCODE_ITEM_KEY, VSCODE_HISTORY_KEY)
                yield from self._history_rows(artifact, source, commands, opts)
        elif state is not None:
            problems = problems or ["%s value is not a JSON object" % VSCODE_ITEM_KEY]
        for prob in problems:
            # Never echo the value: the same row holds the endpoint tokens.
            yield self._row(artifact, 0, opts=opts, text="parser: " + prob.split(" (", 1)[0])

    # -- events/YYYY-MM-DD.json ----------------------------------------------------------
    def _parse_events(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        errors: list = []
        for line_number, rec in iter_jsonl(artifact.disk_path, errors):
            user = rec.get("user")
            owner = "user=%s" % user if user not in (None, "") else ""
            event = rec.get("event")
            if not isinstance(event, dict):
                yield self._row(
                    artifact,
                    line_number,
                    timestamp=to_utc(rec.get("ts")),
                    opts=opts,
                    text="unknown log entry: " + compact_json(rec),
                )
                continue
            yield from self._event_rows(
                artifact, line_number, to_utc(rec.get("ts")), owner, event, opts
            )
        yield from error_rows(self, artifact, errors)

    # -- one Event, from either store -----------------------------------------------------
    def _event_rows(
        self,
        artifact: Artifact,
        line: int,
        timestamp: str,
        owner: str,
        event: dict,
        opts: Options,
        kind: str = "",
    ) -> Iterator[Row]:
        if len(event) != 1:
            yield self._row(
                artifact,
                line,
                timestamp=timestamp,
                opts=opts,
                text=_join(kind or "event", owner, compact_json(event)),
            )
            return
        tag, body = next(iter(event.items()))
        body = body if isinstance(body, dict) else {}
        cid = str(body.get("completion_id") or "")
        if tag == "completion":
            seg = body.get("segments")
            if not isinstance(seg, dict):
                seg = {}
            project = str(seg.get("git_url") or "")
            yield self._row(
                artifact,
                line,
                cid,
                project,
                timestamp,
                opts=opts,
                text=_join(
                    "completion",
                    owner,
                    "language=%s" % body["language"] if body.get("language") else "",
                    "file=%s" % seg["filepath"] if seg.get("filepath") else "",
                    "client=%s" % body["user_agent"] if body.get("user_agent") else "",
                ),
            )
            yield self._row(
                artifact, line, cid, project, timestamp, "user", str(body.get("prompt") or ""), opts
            )
            for choice in _list(body.get("choices")):
                if isinstance(choice, dict):
                    yield self._row(
                        artifact,
                        line,
                        cid,
                        project,
                        timestamp,
                        "assistant",
                        str(choice.get("text") or ""),
                        opts,
                    )
        elif tag in ("view", "select", "dismiss"):
            yield self._row(
                artifact,
                line,
                cid,
                timestamp=timestamp,
                opts=opts,
                text=_join(
                    "%s choice %s" % (tag, body.get("choice_index", "")),
                    owner,
                    "kind=%s" % body["kind"] if body.get("kind") else "",
                    "view=%s" % body["view_id"] if body.get("view_id") else "",
                    "elapsed=%sms" % body["elapsed"] if body.get("elapsed") is not None else "",
                ),
            )
        else:
            yield self._row(
                artifact,
                line,
                cid,
                timestamp=timestamp,
                opts=opts,
                text=_join(str(tag), owner, compact_json(body) if body else ""),
            )
