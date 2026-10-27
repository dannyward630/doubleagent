"""Parse OpenCode sessions from its database, its JSON trees and its terminal UI state.

Follows `research/opencode.md`. Validated against source, sst/opencode at 907b3bc
(1.x) and anomalyco/opencode at cb07c55 (CLI 2.0.32: the 2.0 tables, refusals,
archives, permission rules, worktrees and the terminal UI state), with a
synthetic fixture; no real install. Kilo Code's CLI is an OpenCode fork, so
`KiloCodeParser` subclasses this one with its own paths. Files read:

- `.local/share/opencode/opencode[-<channel>].db`, through
  `sqlite_util.open_copy`: `session_v2` and `session` (`id`, `project_id`,
  `parent_id`, `directory`, `title`, `agent`, `permission`, `time_*`),
  `project(id, worktree)`, the V1 `message` and `part` tables and the V2
  `session_message` (`data` JSON with a `type`), `session_share` (never its
  `secret`), `session.updated.1` rows of `event`, `worktree` or
  `project_directory`, and `permission`. In a 2.0 database `session_message`
  is the transcript and the 1.x rows are read, marked recovered, only for a
  session it lacks; in a 1.x one the reverse.
- `opencode-next.db`, a pre-release 2.0 database, a secondary source (a file
  repeating events the main database holds).
- The legacy `storage/` and per-project `project/<slug>/storage/session/`
  JSON trees of session, message and part files.
- `.local/state/opencode`: `prompt-history.jsonl` (secondary),
  `prompt-stash.jsonl` and `session.json` (pinned ids, secondary).

Model and agent (an OpenCode agent is a mode with its own permission rules)
are tracked per session as `model:` and `permission mode:` rows. Shares give
`session synced:` rows, so `records_sync` is set. `project_path` is the
session's `directory`, else the project `worktree` unless `/`, else the
message's `path.cwd`; no git branch is recorded. `source_line` is the SQLite
`rowid`, or 1 for a JSON file.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Generator, Iterator
from pathlib import Path

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
    iter_jsonl,
    track_change,
)

# The session-start row of a session that a 2.0 database holds only in the 1.x
# `session` table: deleted in 2.0, which leaves the 1.x rows behind.
LEGACY_NOTE = "(only in the 1.x session table)"

# Which tool input field best identifies the action, in order of preference.
TOOL_KEYS = (
    "command",
    "filePath",
    "file_path",
    "pattern",
    "path",
    "url",
    "query",
    "description",
    "prompt",
)


def tool_summary(value) -> str:
    """Return the most identifying argument of a tool input, else the input as JSON."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in TOOL_KEYS:
            argument = value.get(key)
            if isinstance(argument, str) and argument:
                if key == "pattern" and isinstance(value.get("path"), str) and value.get("path"):
                    return "%s | %s" % (argument, value["path"])
                return argument
    if value in (None, "", {}):
        return ""
    return compact_json(value)


def model_name(provider, model) -> str:
    """Return `<provider>/<model>`, or whichever of the two is set."""
    provider = provider if isinstance(provider, str) else ""
    model = model if isinstance(model, str) else ""
    if provider and model:
        return "%s/%s" % (provider, model)
    return model or provider


def message_ref(msg: dict) -> tuple[object, object]:
    """Return (providerID, model id) of a V1 message.

    That is the assistant's own `providerID`/`modelID`, else the user
    message's `model` object.
    """
    if msg.get("role") == "assistant":
        return msg.get("providerID"), msg.get("modelID")
    model = msg.get("model")
    if isinstance(model, dict):
        return model.get("providerID"), model.get("modelID") or model.get("id")
    return None, None


def message_model(msg: dict) -> str:
    """Return a V1 message's model as `<provider>/<model>`."""
    return model_name(*message_ref(msg))


def model_row_text(seen: dict, key, provider, model_id) -> str:
    """Return the `model:` row text of a model reference, through `track_change`.

    That is `model: <id> provider=<provider>` for the first model of a
    session and `model: <old id> -> <new id> provider=<provider>` when the id
    or the provider changes; "" when it is unchanged or names no model id.
    """
    provider = provider if isinstance(provider, str) else ""
    model_id = model_id if isinstance(model_id, str) else ""
    if not model_id:
        return ""
    old = seen.get(key)
    if not track_change("model", seen, key, "%s\n%s" % (provider, model_id)):
        return ""
    text = "model: %s -> %s" % (old.split("\n", 1)[1], model_id) if old else "model: " + model_id
    return text + (" provider=" + provider if provider else "")


def agent_row_text(seen: dict, key, agent) -> str:
    """Return the `permission mode: agent=<name>` text when a session's agent is new or changed.

    An OpenCode agent (`build`, `plan`, a custom one) is a mode with its own
    permission set, so it is tracked as the mode.
    """
    if not isinstance(agent, str) or not agent:
        return ""
    return track_change("permission mode", seen, key, "agent=" + agent)


def _dict_or_empty(value) -> dict:
    return value if isinstance(value, dict) else {}


def _loads(value) -> dict | None:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value)
    except ValueError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _decode(value) -> tuple[dict | None, str, str]:
    """Return (record, reason, raw text) of a stored JSON value.

    The record is the value when it decodes to an object, else None with the
    reason and the value as text (bytes decoded UTF-8 with
    `errors="replace"`), for an error row that carries it in full.
    """
    if value is None:
        return None, "no data", ""
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    elif isinstance(value, str):
        text = value
    else:
        return None, "not JSON text", str(value)
    try:
        decoded = json.loads(text)
    except ValueError as error:
        return None, str(error), text
    if not isinstance(decoded, dict):
        return None, "not a JSON object", text
    return decoded, "", text


def _read_part(path: Path) -> tuple[dict | None, str, str]:
    """Return `_decode` of a part file's bytes; an unreadable file gives the reason, no text."""
    try:
        with open(path, "rb") as handle:
            return _decode(handle.read())
    except OSError as error:
        return None, "unreadable: %s" % (error.strerror or error), ""


def _read_json(path: Path) -> dict | None:
    try:
        with open(path, "rb") as handle:
            return _loads(handle.read())
    except OSError:
        return None


def _join(*parts) -> str:
    return " ".join(str(part) for part in parts if part not in (None, ""))


def _error_text(err) -> str:
    if isinstance(err, str):
        return err
    error = _dict_or_empty(err)
    data = _dict_or_empty(error.get("data"))
    msg = data.get("message") or error.get("message") or ""
    return _join(error.get("name") or error.get("type") or "", msg) or (
        compact_json(err) if err else ""
    )


# The refusal texts a tool's error carries (research/opencode.md, Permission
# records; research/kilo-code.md, Permission rows). 1.x and Kilo Code store
# the error's message as the tool part's `state.error` string; 2.0 stores
# `{type, message}` on the tool item.
V1_REJECTED = "The user rejected permission to use this specific tool call."
V1_FEEDBACK = (
    "The user rejected permission to use this specific tool call with the following feedback: "
)
V1_RULE = "The user has specified a rule which prevents you from using this specific tool call."
V2_DECLINED = "The user declined this tool call"


def decision_text(err) -> str:
    """Return the `permission decision:` text of a tool error that records a refusal, else "".

    The 2.0 `permission.rejected` type covers both a deny rule and a
    rejection with feedback, which its message does not tell apart, so it
    keeps the agent's own term.
    """
    if isinstance(err, str):
        etype, msg = "", err
    elif isinstance(err, dict):
        etype, msg = err.get("type"), err.get("message")
        etype = etype if isinstance(etype, str) else ""
        msg = msg if isinstance(msg, str) else ""
    else:
        return ""
    if etype == "permission.rejected":
        return "permission decision: rejected (permission.rejected)"
    if etype in ("", "aborted") and msg == V2_DECLINED:
        return "permission decision: rejected"
    if msg.startswith(V1_FEEDBACK):
        return "permission decision: rejected with feedback"
    if msg.startswith(V1_REJECTED):
        return "permission decision: rejected"
    if msg.startswith(V1_RULE):
        return "permission decision: denied by rule"
    return ""


def session_rules(value) -> list[tuple[str, str, str]] | None:
    """Return (permission, pattern, effect) per rule of a session's `permission` column.

    The column is a JSON array of 2.0 `{action, resource, effect}` or 1.x
    and Kilo Code `{permission, pattern, action}` objects. None when the
    value is not a JSON array; entries that are neither shape are skipped.
    """
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    try:
        rules = json.loads(value) if isinstance(value, str) else None
    except ValueError:
        return None
    if not isinstance(rules, list):
        return None
    out = []
    for rule in rules:
        rule = _dict_or_empty(rule)
        if "effect" in rule:
            keys = ("action", "resource", "effect")
        elif "permission" in rule:
            keys = ("permission", "pattern", "action")
        else:
            continue
        perm, pattern, effect = (
            str(rule[key]) if rule.get(key) not in (None, "") else "-" for key in keys
        )
        out.append((perm, pattern, effect))
    return out


class _Ctx:
    """Session-level values shared by every row of a session."""

    def __init__(self, session_id: str = "", project_path: str = ""):
        self.session_id = session_id
        self.project_path = project_path
        # The model and agent last seen in the session, for `track_change`.
        self.models: dict = {}
        self.modes: dict = {}


class OpenCodeParser(Parser):
    """Parse OpenCode's databases, legacy JSON trees and terminal UI state files."""

    agent = "opencode"
    name = "opencode"
    records_sync = True
    # The pre-release 2.0 database (`opencode-next.db`) that 2.0 imports and
    # leaves in place is secondary to the database it was imported into.
    has_secondary = True
    next_db = "opencode-next.db"
    data_dir = ".local/share/opencode"
    db_prefixes: tuple[str, ...] = ("opencode",)
    # The terminal UI's state directory: `prompt-history.jsonl` (secondary),
    # `prompt-stash.jsonl` and, for OpenCode, `session.json` (secondary).
    state_dir = ".local/state/opencode"
    pinned_sessions = True

    def __init__(self) -> None:
        """Compile the path patterns from the class's data and state directories."""
        data_dir = re.escape(self.data_dir)
        state_dir = re.escape(self.state_dir)
        self.history_rx = re.compile(r"^%s/prompt-history\.jsonl$" % state_dir)
        self.stash_rx = re.compile(r"^%s/prompt-stash\.jsonl$" % state_dir)
        self.pinned_rx = re.compile(
            r"^%s/session\.json$" % state_dir if self.pinned_sessions else r"(?!)"
        )
        prefixes = "|".join(re.escape(prefix) for prefix in self.db_prefixes)
        self.db_rx = re.compile(r"^%s/(?:%s)(?:-[^/]+)?\.db$" % (data_dir, prefixes))
        self.session_rx = re.compile(r"^%s/storage/session/([^/]+)/([^/]+)\.json$" % data_dir)
        self.message_rx = re.compile(r"^%s/storage/message/([^/]+)/([^/]+)\.json$" % data_dir)
        self.old_session_rx = re.compile(
            r"^%s/project/[^/]+/storage/session/info/([^/]+)\.json$" % data_dir
        )
        self.old_message_rx = re.compile(
            r"^%s/project/[^/]+/storage/session/message/([^/]+)/([^/]+)\.json$" % data_dir
        )

    def wants(self, artifact: Artifact) -> bool:
        """Return True for a database, a JSON tree file or a terminal UI state file."""
        rel = artifact.rel
        return any(
            pattern.match(rel)
            for pattern in (
                self.db_rx,
                self.session_rx,
                self.message_rx,
                self.old_session_rx,
                self.old_message_rx,
                self.history_rx,
                self.stash_rx,
                self.pinned_rx,
            )
        )

    def secondary(self, artifact: Artifact) -> bool:
        """Return True for the prompt history, the pinned sessions or `opencode-next.db`."""
        rel = artifact.rel
        if self.history_rx.match(rel) or self.pinned_rx.match(rel):
            return True
        return bool(self.db_rx.match(rel)) and self.db_label(artifact) == self.next_db

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        """Yield the rows of one OpenCode file."""
        rel = artifact.rel
        if self.history_rx.match(rel):
            yield from self._parse_history(artifact)
        elif self.stash_rx.match(rel):
            yield from self._parse_stash(artifact)
        elif self.pinned_rx.match(rel):
            yield from self._parse_pinned(artifact)
        elif self.db_rx.match(rel):
            yield from self._parse_db(artifact, opts)
        elif self.session_rx.match(rel) or self.old_session_rx.match(rel):
            yield from self._parse_session_file(artifact, opts)
        elif self.message_rx.match(rel):
            yield from self._parse_message_file(artifact, opts, old=False)
        elif self.old_message_rx.match(rel):
            yield from self._parse_message_file(artifact, opts, old=True)

    # -- shared row builders --------------------------------------------------------
    def _row(
        self,
        artifact: Artifact,
        ctx: _Ctx,
        source_file: str,
        line: int,
        timestamp: str,
        model: str = "",
    ) -> Row:
        row = self.base_row(artifact)
        if source_file:
            row.source_file = source_file
        row.source_line = line
        row.session_id = ctx.session_id
        row.project_path = ctx.project_path
        row.timestamp_utc = timestamp
        row.model = model
        return row

    def _session_row(
        self,
        artifact: Artifact,
        ctx: _Ctx,
        session: dict,
        created,
        line: int,
        opts: Options,
        source_file: str = "",
        note: str = "",
    ) -> Row:
        row = self._row(artifact, ctx, source_file, line, to_utc(created))
        row.turn_type = "system"
        row.text = compact(
            _join(
                "session start:",
                session.get("title") or "",
                "slug=%s" % session["slug"] if session.get("slug") else "",
                "version=%s" % session["version"] if session.get("version") else "",
                "agent=%s" % session["agent"] if session.get("agent") else "",
                "parent=%s" % (session.get("parent_id") or session.get("parentID"))
                if (session.get("parent_id") or session.get("parentID"))
                else "",
                "fork=%s" % session["fork_session_id"] if session.get("fork_session_id") else "",
                "directory=%s" % session["directory"] if session.get("directory") else "",
                note,
            ),
        )
        return row

    def _message_rows(
        self,
        artifact: Artifact,
        ctx: _Ctx,
        msg: dict,
        msg_src: tuple[str, int, object],
        parts: list[tuple[dict, str, int, object]],
        opts: Options,
        errors: list,
    ) -> Iterator[Row]:
        """Yield the rows of one V1 message and its parts.

        `msg_src` and each part entry carry (source_file, source_line,
        fallback time). A part whose data could not be decoded is in `errors`
        instead, as (line, message, raw, source_file), and becomes its own
        `parser:` row after the message's rows; `source_file` "" means the
        artifact.
        """
        role = msg.get("role")
        model = message_model(msg)
        msg_file, msg_line, msg_time = msg_src
        msg_ts = to_utc(_dict_or_empty(msg.get("time")).get("created")) or to_utc(msg_time)
        if not ctx.project_path:
            ctx.project_path = str(_dict_or_empty(msg.get("path")).get("cwd") or "")
        for text in (
            model_row_text(ctx.models, ctx.session_id, *message_ref(msg)),
            agent_row_text(ctx.modes, ctx.session_id, msg.get("agent")),
        ):
            if text:
                row = self._row(artifact, ctx, msg_file, msg_line, msg_ts, model)
                row.turn_type = "system"
                row.text = text
                yield row
        user_text: list[str] = []
        first_user: tuple[str, int, int] | None = None
        out: list[Row] = []
        for data, pfile, pline, ptime in parts:
            ptype = data.get("type")
            pts = to_utc(_dict_or_empty(data.get("time")).get("start")) or to_utc(ptime) or msg_ts

            def make_row(turn: str, text, timestamp: str = "") -> Row:
                row = self._row(artifact, ctx, pfile, pline, timestamp or pts, model)
                row.turn_type = turn
                row.text = compact(text)
                out.append(row)
                return row

            if ptype == "text":
                text = data.get("text") or ""
                if data.get("synthetic") or data.get("ignored"):
                    make_row(
                        "system", _join("synthetic:" if data.get("synthetic") else "ignored:", text)
                    )
                elif role == "user":
                    if text:
                        user_text.append(text)
                        if first_user is None:
                            first_user = (pfile, pline, len(out))
                elif text:
                    make_row("assistant", text)
            elif ptype == "reasoning":
                if opts.include_thinking and data.get("text"):
                    make_row("thinking", data.get("text"))
            elif ptype == "tool":
                self._tool_rows(make_row, data)
            elif ptype == "step-finish":
                tokens = _dict_or_empty(data.get("tokens"))
                make_row(
                    "system",
                    _join(
                        "step-finish",
                        "reason=%s" % data["reason"] if data.get("reason") else "",
                        "cost=%s" % data["cost"] if data.get("cost") is not None else "",
                        "tokens_in=%s" % tokens["input"] if tokens.get("input") is not None else "",
                        "tokens_out=%s" % tokens["output"]
                        if tokens.get("output") is not None
                        else "",
                    ),
                )
            elif ptype == "subtask":
                make_row(
                    "system",
                    _join(
                        "subtask",
                        "agent=%s" % data["agent"] if data.get("agent") else "",
                        (data.get("description") or "") + ":",
                        data.get("prompt") or "",
                    ),
                )
            elif ptype == "compaction":
                make_row("system", _join("compaction", "auto" if data.get("auto") else ""))
            elif ptype == "file":
                make_row(
                    "system", _join("file:", data.get("filename") or "", data.get("url") or "")
                )
            elif ptype == "agent":
                make_row("system", _join("agent:", data.get("name") or ""))
            elif ptype == "retry":
                make_row(
                    "system",
                    _join(
                        "retry",
                        "attempt=%s" % data["attempt"] if data.get("attempt") else "",
                        _error_text(data.get("error")),
                    ),
                )
            elif ptype == "patch":
                files = data.get("files")
                make_row(
                    "system",
                    _join(
                        "patch:",
                        " ".join(str(file) for file in files) if isinstance(files, list) else "",
                    ),
                )
            elif ptype in ("step-start", "snapshot"):
                continue
            else:
                make_row("system", _join("%s:" % (ptype or "part"), compact_json(data)))
        if user_text and first_user:
            pfile, pline, position = first_user
            row = self._row(artifact, ctx, pfile, pline, msg_ts, model)
            row.turn_type = "user"
            row.text = compact("\n".join(user_text))
            out.insert(position, row)
        yield from out
        if msg.get("error"):
            row = self._row(
                artifact,
                ctx,
                msg_file,
                msg_line,
                to_utc(_dict_or_empty(msg.get("time")).get("completed")) or msg_ts,
                model,
            )
            row.turn_type = "system"
            row.text = compact("error: " + _error_text(msg.get("error")))
            yield row
        bad_rows = error_rows(self, artifact, errors, ctx.session_id, ctx.project_path)
        for entry, row in zip(errors, bad_rows, strict=True):
            if entry[3]:
                row.source_file = entry[3]
            yield row

    @staticmethod
    def _tool_rows(make_row, data: dict) -> None:
        """Append a tool_use row, and a tool_result row once finished, via `make_row`."""
        state = _dict_or_empty(data.get("state"))
        times = _dict_or_empty(state.get("time"))
        name = str(data.get("tool") or "")
        call_id = str(data.get("callID") or "")
        use = make_row(
            "tool_use",
            tool_summary(state.get("input")) or state.get("title") or "",
            to_utc(times.get("start")),
        )
        use.tool_name, use.tool_use_id = name, call_id
        status = state.get("status")
        if status in ("completed", "error"):
            if status == "error":
                text = "[error] " + _error_text(state.get("error"))
            else:
                out = state.get("output")
                text = out if isinstance(out, str) else compact_json(out)
            res = make_row(
                "tool_result", text, to_utc(times.get("end")) or to_utc(times.get("start"))
            )
            res.tool_name, res.tool_use_id = name, call_id
            decision = decision_text(state.get("error")) if status == "error" else ""
            if decision:
                row = make_row("system", decision, res.timestamp_utc)
                row.tool_name, row.tool_use_id = name, call_id

    # -- SQLite ---------------------------------------------------------------------
    def _parse_db(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        if not is_sqlite(artifact.disk_path):
            return
        rows: list[Row] = []
        try:
            with open_copy(artifact.disk_path) as con:
                for row in self._db_rows(con, artifact, opts):
                    rows.append(row)
        except sqlite3.DatabaseError as error:
            row = self.base_row(artifact)
            row.turn_type = "system"
            row.text = "parser: database could not be read: %s" % error
            rows.append(row)
        yield from rows

    def _db_rows(self, con: sqlite3.Connection, artifact: Artifact, opts: Options) -> Iterator[Row]:
        tables = table_names(con)
        projects: dict[object, dict] = {}  # keyed by the raw id column value
        if "project" in tables:
            for record in con.execute("select * from project"):
                projects[record["id"]] = dict(record)
        # OpenCode 2.0 keeps its sessions in `session_v2` and leaves the 1.x
        # `session`, `message` and `part` tables behind after the upgrade.
        has_v2 = "session_v2" in tables
        sessions: dict[str, tuple[int, dict, str]] = {}  # id -> (rowid, row, table)
        for table in ("session_v2", "session"):
            if table in tables:
                for record in con.execute(
                    "select rowid as _rowid, * from %s order by time_created, id" % table
                ):
                    sessions.setdefault(str(record["id"]), (record["_rowid"], dict(record), table))
        ctxs: dict[str, _Ctx] = {}

        def ctx_for(sid: str) -> _Ctx:
            context = ctxs.get(sid)
            if context is None:
                session = sessions.get(sid, (0, {}, ""))[1]
                path = session.get("directory") or ""
                if not path:
                    worktree = projects.get(session.get("project_id"), {}).get("worktree") or ""
                    path = worktree if worktree != "/" else ""
                context = ctxs[sid] = _Ctx(sid, path)
            return context

        for sid, (rowid, session, table) in sessions.items():
            note = LEGACY_NOTE if has_v2 and table == "session" else ""
            yield self._session_row(
                artifact, ctx_for(sid), session, session.get("time_created"), rowid, opts, note=note
            )

        # (rowid, message, raw, session id) per record whose data does not decode.
        errors: list[tuple[int, str, str, str]] = []
        yield from self._share_rows(con, tables, artifact, ctx_for, errors)
        yield from self._state_rows(con, tables, artifact, sessions, projects, ctx_for, errors)
        if has_v2:
            # 2.0: `session_message` is the transcript. The 1.x rows repeat a
            # migrated session and are read only for a session it does not
            # hold (one deleted in 2.0, which leaves the 1.x rows), as
            # recovered rows.
            covered = self._session_message_ids(con, tables)
            yield from self._v2_messages(con, tables, artifact, ctx_for, set(), errors, opts)
            yield from self._v1_messages(
                con, tables, artifact, ctx_for, covered, errors, opts, recovered=True
            )
        else:
            # 1.x: `message` and `part` are the transcript; the V2 projection
            # was wiped once by a migration, so it is read only for a session
            # with no V1 rows.
            covered = yield from self._v1_messages(
                con, tables, artifact, ctx_for, set(), errors, opts
            )
            yield from self._v2_messages(con, tables, artifact, ctx_for, covered, errors, opts)
        for entry, row in zip(errors, error_rows(self, artifact, errors), strict=True):
            sid = entry[3]
            row.session_id = sid
            row.project_path = ctx_for(sid).project_path if sid else ""
            yield row

    @staticmethod
    def _session_message_ids(con: sqlite3.Connection, tables: set) -> set[str]:
        """Return the ids of the sessions that have a `session_message` row."""
        if "session_message" not in tables:
            return set()
        return {
            str(row[0] or "")
            for row in con.execute("select distinct session_id from session_message")
        }

    def _v1_messages(
        self,
        con: sqlite3.Connection,
        tables: set,
        artifact: Artifact,
        ctx_for,
        skip: set[str],
        errors: list,
        opts: Options,
        recovered: bool = False,
    ) -> Generator[Row, None, set[str]]:
        """Yield the rows of the V1 `message` and `part` tables for every session not in `skip`.

        An undecodable `message` row is appended to `errors` as (rowid,
        message, raw, session id); an undecodable `part` row becomes a
        `parser:` row after its message's rows. With `recovered`, every row
        other than `system` is marked `recovered` "yes". Returns the ids of
        the sessions that have a `message` row.
        """
        covered: set[str] = set()
        if "message" not in tables:
            return covered
        has_parts = "part" in tables
        for message_row in con.execute(
            "select rowid as _rowid, id, session_id, time_created, data from message "
            "order by session_id, time_created, id"
        ).fetchall():
            sid = str(message_row["session_id"] or "")
            covered.add(sid)
            if sid in skip:
                continue
            msg, reason, raw = _decode(message_row["data"])
            if msg is None:
                label = "unparseable record %d (message.data: %s)" % (message_row["_rowid"], reason)
                errors.append((message_row["_rowid"], label, raw, sid))
                continue
            msg.setdefault("id", message_row["id"])
            parts = []
            part_errors: list[tuple[int, str, str, str]] = []
            if has_parts:
                for part_row in con.execute(
                    "select rowid as _rowid, time_created, data from part "
                    "where message_id = ? order by id",
                    (message_row["id"],),
                ):
                    data, reason, raw = _decode(part_row["data"])
                    if data is None:
                        label = "unparseable record %d (part.data: %s)" % (
                            part_row["_rowid"],
                            reason,
                        )
                        part_errors.append((part_row["_rowid"], label, raw, ""))
                    else:
                        parts.append((data, "", part_row["_rowid"], part_row["time_created"]))
            msg_src = ("", message_row["_rowid"], message_row["time_created"])
            for row in self._message_rows(
                artifact, ctx_for(sid), msg, msg_src, parts, opts, part_errors
            ):
                if recovered and row.turn_type != "system":
                    row.recovered = "yes"
                yield row
        return covered

    def _v2_messages(
        self,
        con: sqlite3.Connection,
        tables: set,
        artifact: Artifact,
        ctx_for,
        skip: set[str],
        errors: list,
        opts: Options,
    ) -> Iterator[Row]:
        """Yield the rows of `session_message` for every session not in `skip`.

        An undecodable row is appended to `errors` as (rowid, message, raw,
        session id).
        """
        if "session_message" not in tables:
            return
        for message_row in con.execute(
            "select rowid as _rowid, session_id, type, seq, time_created, data "
            "from session_message order by session_id, seq, time_created"
        ).fetchall():
            sid = str(message_row["session_id"] or "")
            if sid in skip:
                continue
            data, reason, raw = _decode(message_row["data"])
            if data is None:
                label = "unparseable record %d (session_message.data: %s)" % (
                    message_row["_rowid"],
                    reason,
                )
                errors.append((message_row["_rowid"], label, raw, sid))
                continue
            yield from self._v2_rows(
                artifact,
                ctx_for(sid),
                message_row["type"] or data.get("type") or "",
                data,
                message_row["_rowid"],
                message_row["time_created"],
                opts,
            )

    def _share_rows(
        self, con: sqlite3.Connection, tables: set, artifact: Artifact, ctx_for, errors: list
    ) -> Iterator[Row]:
        """Yield the database's sync rows, one per `session_share` row, then the event shares.

        A session with no share row gets the share URL and the unshare its
        `session.updated.1` events record. An event row whose `data` does not
        decode is appended to `errors` as (rowid, message, raw, session id).
        `secret` is never selected.
        """
        database = self.db_label(artifact)
        shared: set[str] = set()
        if "session_share" in tables:
            for record in con.execute(
                "select rowid as _rowid, session_id, id, url, time_created from session_share "
                "order by time_created, session_id"
            ):
                sid = str(record["session_id"] or "")
                shared.add(sid)
                row = self._row(
                    artifact, ctx_for(sid), "", record["_rowid"], to_utc(record["time_created"])
                )
                row.turn_type = "system"
                row.text = compact(
                    "session synced: share %s url %s (from %s session_share, time_created)"
                    % (record["id"] or "-", record["url"] or "-", database)
                )
                yield row
        if "event" not in tables:
            return
        state: dict[str, str] = {}  # session id -> "shared" or "unshared"
        for record in con.execute(
            "select rowid as _rowid, aggregate_id, data from event "
            "where type = 'session.updated.1' order by aggregate_id, seq"
        ):
            sid = str(record["aggregate_id"] or "")
            data, reason, raw = _decode(record["data"])
            if data is None:
                label = "unparseable record %d (event.data: %s)" % (record["_rowid"], reason)
                errors.append((record["_rowid"], label, raw, sid))
                continue
            if sid in shared or state.get(sid) == "unshared":
                continue
            info = _dict_or_empty(data.get("info"))
            url = _dict_or_empty(info.get("share")).get("url")
            timestamp = to_utc(_dict_or_empty(info.get("time")).get("updated"))
            if url and sid not in state:
                state[sid] = "shared"
                text = "session synced: share url %s" % url
            elif not url and state.get(sid) == "shared":
                state[sid] = "unshared"
                text = "session unshared"
            else:
                continue
            row = self._row(artifact, ctx_for(sid), "", record["_rowid"], timestamp)
            row.turn_type = "system"
            row.text = compact(
                "%s (from %s event session.updated.1, info.time.updated)" % (text, database)
            )
            yield row

    def _state_rows(
        self,
        con: sqlite3.Connection,
        tables: set,
        artifact: Artifact,
        sessions: dict,
        projects: dict,
        ctx_for,
        errors: list,
    ) -> Iterator[Row]:
        """Yield the database's standing state as `system` rows.

        Per session a `session archived` row at `time_archived` and one
        `permission setting: session ...` row per rule of its `permission`
        column at `time_updated`; one `scratch directory:` row per worktree
        OpenCode made (`worktree`, else `project_directory` of type
        `git_worktree`); one `permission setting:` row per saved grant of the
        `permission` table. A `permission` value that is not a JSON array is
        appended to `errors` as (rowid, message, raw, session id).
        """
        database = self.db_label(artifact)

        def make_row(ctx: _Ctx, line: int, when, text: str, project: str | None = None) -> Row:
            row = self._row(artifact, ctx, "", line, to_utc(when))
            row.turn_type = "system"
            row.text = compact(text)
            if project is not None:
                row.project_path = project
            return row

        for sid, (rowid, session, table) in sessions.items():
            if session.get("time_archived"):
                yield make_row(
                    ctx_for(sid),
                    rowid,
                    session["time_archived"],
                    "session archived (from %s %s, time_archived)" % (database, table),
                )
            if session.get("permission") in (None, ""):
                continue
            rules = session_rules(session["permission"])
            if rules is None:
                raw = session["permission"]
                raw = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
                label = "unparseable record %d (%s.permission: not a JSON array)" % (rowid, table)
                errors.append((rowid, label, raw, sid))
                continue
            for perm, pattern, effect in rules:
                yield make_row(
                    ctx_for(sid),
                    rowid,
                    session.get("time_updated"),
                    "permission setting: session %s %s=%s (from %s %s.permission, time_updated)"
                    % (perm, pattern, effect, database, table),
                )

        def worktree_of(project_id) -> str:
            worktree = projects.get(project_id, {}).get("worktree") or ""
            return worktree if worktree != "/" else ""

        seen: set[str] = set()
        for table in ("worktree", "project_directory"):
            if table not in tables:
                continue
            for record in con.execute(
                "select rowid as _rowid, * from %s order by time_created, directory" % table
            ):
                record = dict(record)
                directory = str(record.get("directory") or "")
                if not directory or directory in seen:
                    continue
                if table == "project_directory" and record.get("type") != "git_worktree":
                    continue
                seen.add(directory)
                text = "scratch directory: %s (git worktree of %s strategy=%s) (from %s %s, " % (
                    directory,
                    worktree_of(record.get("project_id")) or "-",
                    record.get("strategy") or "-",
                    database,
                    table,
                )
                yield make_row(
                    _Ctx(),
                    record["_rowid"],
                    record.get("time_created"),
                    text + "time_created)",
                    directory,
                )

        if "permission" in tables:
            for record in con.execute(
                "select rowid as _rowid, * from permission order by time_created, id"
            ):
                record = dict(record)
                if "action" not in record:
                    # The first migration's `permission(project_id, data)`,
                    # dropped later; its `data` shape is not in the research.
                    break
                yield make_row(
                    _Ctx(),
                    record["_rowid"],
                    record.get("time_created"),
                    "permission setting: %s %s=allow (from %s permission, time_created)"
                    % (record.get("action") or "-", record.get("resource") or "-", database),
                    worktree_of(record.get("project_id")),
                )

    @staticmethod
    def db_label(artifact: Artifact) -> str:
        """Return the database's file name for row text (`opencode.db`, `kilo.db`, ...)."""
        return artifact.rel.rsplit("/", 1)[-1]

    def _v2_rows(
        self,
        artifact: Artifact,
        ctx: _Ctx,
        mtype: str,
        data: dict,
        line: int,
        created,
        opts: Options,
    ) -> Iterator[Row]:
        timestamp = to_utc(_dict_or_empty(data.get("time")).get("created")) or to_utc(created)
        model_ref = _dict_or_empty(data.get("model"))
        model = model_name(
            model_ref.get("providerID"), model_ref.get("modelID") or model_ref.get("id")
        )

        def make_row(turn: str, text, when: str = "") -> Row:
            row = self._row(artifact, ctx, "", line, when or timestamp, model)
            row.turn_type = turn
            row.text = compact(text)
            return row

        if mtype == "model-switched":
            text = model_row_text(
                ctx.models,
                ctx.session_id,
                model_ref.get("providerID"),
                model_ref.get("id") or model_ref.get("modelID"),
            )
            if text:
                yield make_row("system", text)
        elif mtype == "agent-switched":
            text = agent_row_text(ctx.modes, ctx.session_id, data.get("agent"))
            if text:
                yield make_row("system", text)
        elif mtype == "user":
            yield make_row("user", data.get("text") or "")
        elif mtype in ("synthetic", "system"):
            yield make_row("system", _join("%s:" % mtype, data.get("text") or ""))
        elif mtype == "shell":
            yield from self._shell_rows(make_row, data)
        elif mtype == "compaction":
            yield make_row(
                "system",
                _join(
                    "compaction",
                    data.get("reason") or "",
                    data.get("status") or "",
                    data.get("summary") or "",
                    _error_text(data.get("error")) if data.get("error") else "",
                ),
            )
        elif mtype == "location-switched":
            loc = _dict_or_empty(data.get("location"))
            prev = _dict_or_empty(_dict_or_empty(data.get("previous")).get("location"))
            yield make_row(
                "system",
                _join(
                    "location switched:",
                    "%s ->" % prev["directory"] if prev.get("directory") else "",
                    loc.get("directory") or "",
                    "workspace=%s" % loc["workspaceID"] if loc.get("workspaceID") else "",
                    "subpath=%s" % data["subpath"] if data.get("subpath") else "",
                ),
            )
        elif mtype == "skill":
            yield make_row(
                "system", _join("skill %s:" % (data.get("name") or ""), data.get("text") or "")
            )
        elif mtype == "idle":
            yield make_row(
                "system",
                _join(
                    "idle:",
                    data.get("outcome") or "",
                    _error_text(data.get("error")) if data.get("error") else "",
                ),
            )
        elif mtype == "assistant":
            for text in (
                model_row_text(
                    ctx.models,
                    ctx.session_id,
                    model_ref.get("providerID"),
                    model_ref.get("id") or model_ref.get("modelID"),
                ),
                agent_row_text(ctx.modes, ctx.session_id, data.get("agent")),
            ):
                if text:
                    yield make_row("system", text)
            for item in data.get("content") or []:
                item = _dict_or_empty(item)
                itype = item.get("type")
                if itype == "text" and item.get("text"):
                    yield make_row("assistant", item["text"])
                elif itype == "reasoning":
                    if opts.include_thinking and item.get("text"):
                        yield make_row("thinking", item["text"])
                elif itype == "tool":
                    state = _dict_or_empty(item.get("state"))
                    times = _dict_or_empty(item.get("time"))
                    name, call_id = str(item.get("name") or ""), str(item.get("id") or "")
                    use = make_row(
                        "tool_use", tool_summary(state.get("input")), to_utc(times.get("created"))
                    )
                    use.tool_name, use.tool_use_id = name, call_id
                    yield use
                    status = state.get("status")
                    if status in ("completed", "error"):
                        if status == "error":
                            text = "[error] " + _error_text(state.get("error"))
                        else:
                            text = "\n".join(
                                str(chunk.get("text"))
                                for chunk in state.get("content") or []
                                if isinstance(chunk, dict) and chunk.get("text") is not None
                            )
                        res = make_row(
                            "tool_result",
                            text,
                            to_utc(times.get("completed")) or to_utc(times.get("ran")),
                        )
                        res.tool_name, res.tool_use_id = name, call_id
                        yield res
                        decision = decision_text(state.get("error")) if status == "error" else ""
                        if decision:
                            row = make_row("system", decision, res.timestamp_utc)
                            row.tool_name, row.tool_use_id = name, call_id
                            yield row
            if data.get("error"):
                yield make_row("system", "error: " + _error_text(data.get("error")))
        elif mtype:
            yield make_row(
                "system",
                _join(
                    "%s:" % mtype,
                    compact_json({key: value for key, value in data.items() if key != "time"}),
                ),
            )

    @staticmethod
    def _shell_rows(make_row, data: dict) -> Iterator[Row]:
        """Yield a `shell` record's tool_use row and, once it has output or has ended, its result.

        1.x records `callID` and `output` as a string; 2.0 `shellID`, `status`
        (`running`, `exited`, `timeout`, `killed`), `exit` and
        `output.output`. A result that did not exit 0 starts `[<status>]` or
        `[exit <code>]`.
        """
        call_id = str(data.get("callID") or data.get("shellID") or "")
        times = _dict_or_empty(data.get("time"))
        use = make_row("tool_use", data.get("command") or "")
        use.tool_name, use.tool_use_id = "shell", call_id
        yield use
        output, status, code = data.get("output"), data.get("status"), data.get("exit")
        if output is None and status in (None, "running"):
            return
        text = _dict_or_empty(output).get("output") if isinstance(output, dict) else output
        text = text if isinstance(text, str) else ""
        if status in ("timeout", "killed"):
            text = _join("[%s]" % status, text)
        elif code not in (None, 0):
            text = _join("[exit %s]" % code, text)
        res = make_row("tool_result", text, to_utc(times.get("completed")))
        res.tool_name, res.tool_use_id = "shell", call_id
        yield res

    # -- terminal UI state ----------------------------------------------------------
    def _parse_history(self, artifact: Artifact) -> Iterator[Row]:
        """Yield one row per prompt of `prompt-history.jsonl`, the terminal UI's last 50.

        The rows have an empty `timestamp_utc`, `session_id` and
        `project_path`, since the line records none. A prompt is a `user`
        row; a shell command (`mode` `shell`) a `tool_use` row with tool
        `shell` and no id, which pairs on text with the transcript's command.
        2.0 writes the prompt as `text`, 1.x and Kilo Code as `input`.
        """
        errors: list = []
        for line_number, rec in iter_jsonl(artifact.disk_path, errors):
            text = rec.get("text") if isinstance(rec.get("text"), str) else rec.get("input")
            if not isinstance(text, str) or not text.strip():
                continue
            row = self._row(artifact, _Ctx(), "", line_number, "")
            if rec.get("mode") == "shell":
                row.turn_type, row.tool_name = "tool_use", "shell"
            else:
                row.turn_type = "user"
            row.text = compact(text)
            yield row
        yield from error_rows(self, artifact, errors)

    def _parse_stash(self, artifact: Artifact) -> Iterator[Row]:
        """Yield one `prompt stashed (unsent):` row per prompt set aside in `prompt-stash.jsonl`.

        Each row is at the line's `timestamp` (epoch ms). 2.0 writes
        `{prompt: {text, ...}, timestamp}`, 1.x and Kilo Code `{input, parts,
        timestamp}`.
        """
        errors: list = []
        for line_number, rec in iter_jsonl(artifact.disk_path, errors):
            prompt = rec.get("prompt")
            text = (
                _dict_or_empty(prompt).get("text") if isinstance(prompt, dict) else rec.get("input")
            )
            if not isinstance(text, str) or not text.strip():
                continue
            row = self._row(artifact, _Ctx(), "", line_number, to_utc(rec.get("timestamp")))
            row.turn_type = "system"
            row.text = compact(
                "prompt stashed (unsent): %s (from %s, timestamp)" % (text.strip(), artifact.rel)
            )
            yield row
        yield from error_rows(self, artifact, errors)

    def _parse_pinned(self, artifact: Artifact) -> Iterator[Row]:
        """Yield one `session pinned:` row per id of `session.json` `pinned`, at the file's mtime.

        The id stays after the session is deleted, so a pinned session with
        no other row is a trace of a deleted one. A file that is not a JSON
        object is one `parser:` row.
        """
        doc = _read_json(artifact.disk_path)
        timestamp = file_mtime(artifact)
        if doc is None:
            row = self._row(artifact, _Ctx(), "", 1, timestamp)
            row.turn_type = "system"
            row.text = "parser: %s is not a JSON object" % artifact.rel
            yield row
            return
        pinned = doc.get("pinned")
        for sid in pinned if isinstance(pinned, list) else []:
            if not isinstance(sid, str) or not sid:
                continue
            row = self._row(artifact, _Ctx(sid), "", 1, timestamp)
            row.turn_type = "system"
            row.text = "session pinned: %s (from %s pinned, file mtime)" % (sid, artifact.rel)
            yield row

    # -- legacy JSON tree -----------------------------------------------------------
    @staticmethod
    def _orig_root(artifact: Artifact, depth: int) -> tuple[str, str, Path]:
        """Return (original root, separator, disk root) of the directory `depth` levels up.

        The original path is cut by the length of the relative tail, which is
        the same whatever the separator.
        """
        tail = "/".join(artifact.rel.split("/")[-depth:])
        orig = artifact.original
        sep = "\\" if orig.count("\\") > orig.count("/") else "/"
        root = orig[: len(orig) - len(tail)].rstrip("/\\")
        disk = artifact.disk_path
        for _ in range(depth):
            disk = disk.parent
        return root, sep, disk

    @staticmethod
    def _children(directory: Path) -> list[Path]:
        try:
            return sorted(
                path
                for path in directory.iterdir()
                if path.suffix == ".json" and not path.is_symlink() and path.is_file()
            )
        except OSError:
            return []

    def _previous_message(self, path: Path) -> dict | None:
        siblings = self._children(path.parent)
        names = [sibling.name for sibling in siblings]
        if path.name not in names:
            return None
        position = names.index(path.name)
        return _read_json(siblings[position - 1]) if position > 0 else None

    def _session_ctx(self, root: Path, session_id: str, old: bool, msg: dict) -> tuple[_Ctx, dict]:
        session: dict | None = None
        if old:
            session = _read_json(root / "info" / (session_id + ".json"))
        else:
            session_dir = root / "session"
            try:
                candidates = sorted(
                    directory / (session_id + ".json")
                    for directory in session_dir.iterdir()
                    if not directory.is_symlink() and directory.is_dir()
                )
            except OSError:
                candidates = []
            for candidate in candidates:
                if candidate.is_file() and not candidate.is_symlink():
                    session = _read_json(candidate)
                    if session is not None:
                        break
        session = session or {}
        path = session.get("directory") or ""
        if not path and not old and session.get("projectID"):
            worktree = (
                _read_json(root / "project" / (str(session["projectID"]) + ".json")) or {}
            ).get("worktree") or ""
            path = worktree if worktree != "/" else ""
        if not path:
            message_path = _dict_or_empty(msg.get("path"))
            path = message_path.get("root") or message_path.get("cwd") or ""
        return _Ctx(session_id, str(path)), session

    def _parse_session_file(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        session = _read_json(artifact.disk_path)
        if session is None:
            row = self.base_row(artifact)
            row.source_line = 1
            row.session_id = artifact.disk_path.stem
            row.turn_type = "system"
            row.text = "parser: session file could not be decoded"
            yield row
            return
        path = session.get("directory") or ""
        if not path and session.get("projectID") and not self.old_session_rx.match(artifact.rel):
            proj = (
                artifact.disk_path.parent.parent.parent
                / "project"
                / (str(session["projectID"]) + ".json")
            )
            worktree = (_read_json(proj) or {}).get("worktree") or ""
            path = worktree if worktree != "/" else ""
        ctx = _Ctx(str(session.get("id") or artifact.disk_path.stem), str(path))
        yield self._session_row(
            artifact, ctx, session, _dict_or_empty(session.get("time")).get("created"), 1, opts
        )

    def _parse_message_file(self, artifact: Artifact, opts: Options, old: bool) -> Iterator[Row]:
        # new: storage/message/<ses>/<msg>.json, root is storage/
        # old: project/<slug>/storage/session/message/<ses>/<msg>.json, root is storage/session/
        orig_root, sep, root = self._orig_root(artifact, 3)
        session_id = artifact.disk_path.parent.name
        msg = _read_json(artifact.disk_path)
        if msg is None:
            ctx, _ = self._session_ctx(root, session_id, old, {})
            row = self._row(artifact, ctx, "", 1, "")
            row.turn_type = "system"
            row.text = "parser: message file could not be decoded"
            yield row
            return
        session_id = str(msg.get("sessionID") or session_id)
        msg_id = str(msg.get("id") or artifact.disk_path.stem)
        msg.setdefault("id", msg_id)
        ctx, _ = self._session_ctx(root, session_id, old, msg)
        # One file holds one message, so the model and agent in force come
        # from the message before it (message ids sort in time order).
        prev = self._previous_message(artifact.disk_path)
        if prev is not None:
            model_row_text(ctx.models, ctx.session_id, *message_ref(prev))
            agent_row_text(ctx.modes, ctx.session_id, prev.get("agent"))
        part_dir_parts = ["part", session_id, msg_id] if old else ["part", msg_id]
        part_dir = root.joinpath(*part_dir_parts)
        parts = []
        errors: list[tuple[int, str, str, str]] = []
        for file in self._children(part_dir):
            data, reason, raw = _read_part(file)
            src = orig_root + sep + sep.join([*part_dir_parts, file.name])
            if data is None:
                errors.append((1, "unparseable part %s (%s)" % (file.stem, reason), raw, src))
            else:
                parts.append((data, src, 1, None))
        yield from self._message_rows(artifact, ctx, msg, ("", 1, None), parts, opts, errors)
