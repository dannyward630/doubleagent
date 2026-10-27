"""Letta Code transcripts.

Validated against source, letta-ai/letta-code at 77faf36e (October 2026)
and, for the settings permissions, channel routing, scheduled tasks and
interrupted turns, at 2a46615d (0.34.17, reviewed 2026-10-21), with a
synthetic fixture; see `research/letta.md`. Letta keeps conversations on
the Letta server by default; these local stores are parsed:

* `~/.letta/lc-local-backend/conversations/<base64url key>/messages.jsonl`
  (local backend only; the key is `conversation:<id>` or
  `default:<agent id>`). `manifest.json` `message_format`
  `pi-session-entry-jsonl` (schema 2): pi's session format, read with
  `pi.read_session` and `pi.entry_rows`. Header `id` (conversation id,
  falling back to the decoded directory name) and `cwd`; entries `message`
  and `compaction`. `message.id` starts `letta-msg-` and a message may be
  re-appended with the same `id` as a replacement snapshot, so only the
  last copy of each `message.id` is kept. Schema 1 files
  (`pi-ai-message-jsonl`, one bare message per line, no header) are read
  too, timed by `message.metadata.created_at` or `message.timestamp`.
* `~/.letta/transcripts/<agent>/<conversation>/transcript.jsonl` (both
  backends, appended after each turn): `kind` user, assistant, reasoning
  (a `thinking` row, opt-in) or error (system) with `text`; or
  `kind: "tool_call"` with `name`, `argsText`, `resultText`, `resultOk`,
  emitted as a tool_use and a tool_result with no tool id. `argsText` is
  the streamed arguments JSON; when it parses, the tool_use text is
  `pi.args_summary` of it (the command, path or query), as the
  `messages.jsonl` row for the same call renders it, else the raw text.
  Every line has `captured_at` (ISO 8601 Z, shared by a turn's lines). No
  model and no cwd: the session id is the conversation directory name
  (the conversation id, `local-conv-<n>` or `default`, which the directory
  sanitisation leaves unchanged, so it equals the `messages.jsonl` header
  `id`) and the project path is the `project` of the `sessions.jsonl` line
  with the same `agent_id` and the earliest `timestamp` at or after
  `captured_at` (the exit line of the CLI session the turn belongs to),
  else of the latest line before it, a heuristic.

  A secondary source (`secondary()`, issue 122): in local-backend mode it
  repeats the turns of the conversation's `messages.jsonl`, the store of
  record, and it is read always, whether or not that file was collected,
  so a conversation whose local-backend directory was deleted (deleting an
  agent removes its conversation directories, not its transcripts) or a
  server-backend conversation (no local store at all) is still recovered.
  Letta stamps `captured_at` once per turn, when the turn ends
  (`new Date()` in `appendTranscriptDeltaJsonl`, called after the turn's
  `end_turn` stop reason), so every line of a turn is later than its
  `messages.jsonl` twin by up to the turn's duration, the user prompt by
  all of it. `secondary_tolerance()` is therefore `TURN_TOLERANCE_SECONDS`
  (one hour) instead of the default 2 seconds; a turn longer than that
  (a long unattended run, an approval left waiting) leaves its earlier
  lines unpaired, shown twice. The pairing is confined to one
  conversation and one text, so the wide window can only pair a line with
  an identical event of the same conversation. Turns that end in an
  error or an interrupt are never appended, so the transcript lacks them.
* `~/.letta/sessions.jsonl`: one exit line per CLI session that ended
  with `/exit` (`exit_reason` `exit_command`) or `/logout` (`logout`),
  written by `recordSessionEnd`; `recordSessionStart` has no caller at
  77faf36e or 2a46615d (issue 158), so a session still running or ended
  any other way has no line. Keys: `agent_id`, `session_id` (the CLI's
  telemetry session id), `timestamp` (ms, the time of exit), `project`,
  `model`, `provider`, `message_count`, `tool_call_count`, `exit_reason`,
  `duration.wall_ms`. One system row per line (`letta session end: ...`;
  a line without `exit_reason` or `message_count`, which no caller writes,
  reads `letta session start: ...`), followed by `model: <model>
  provider=<provider>` on the first line of a `session_id` that names a
  model and `model: <old> -> <new> provider=<provider>` when a later line
  of it names another.

* `~/.letta/settings.json`, the legacy `~/.config/letta/settings.json`,
  and a project's `.letta/settings.json` and `.letta/settings.local.json`
  (an artifact whose `home.project` is set; `project_path` is the
  project): `sessionsByServer` (not in the legacy file, which Letta reads
  only for permissions), an object keyed by the server's host and port
  (`api.letta.com`, `localhost:8283`) or `local:<store path>` for the
  local backend, each value `{agentId, conversationId}`, the last session
  used on that server; the `permissions` object (`mode`, `allow`, `deny`,
  `ask`, `alwaysAsk`, `additionalDirectories`); and, in
  `~/.letta/settings.json`, `agents[]` (`agentId`, `baseUrl`, absent for
  Letta Cloud) for the transcript rows below. No other key is read: `env`
  and the token keys hold credentials. A file that is not a JSON object
  is one `parser:` row.

Read since the 2026-10-21 review of letta-ai/letta-code at 2a46615d
(0.34.17), source-derived; not observed on any real install (issue 202):

* Permission rows: one `system` row per entry of a settings file's
  `permissions` object, `permission setting: permissions.<key>=<value>
  (from <file>, file mtime)`, one per rule of `allow`, `deny`, `ask` and
  `alwaysAsk` (Claude Code's rule form, `Bash(npm test)`), one per
  `additionalDirectories` entry and one for `mode` (as recorded: `standard`,
  `acceptEdits`, `unrestricted`, `strict`, or a legacy `default`,
  `bypassPermissions`, `fullAccess`), at the file's modification time with
  an empty `session_id`. `/approve-always` appends to `allow`.
* `~/.letta/channels/<channel>/routing.json` (or the legacy
  `routing.yaml`, which holds the same JSON): `routes[]` with `accountId`,
  `chatId`, `chatType`, `threadId`, `agentId`, `conversationId`,
  `enabled`, `outboundEnabled`, `detached`, `createdAt`, `updatedAt`. One
  row per route, `session relayed: <channel> chat <chatId> type
  <chatType> thread <threadId> account <accountId> agent <agentId>
  enabled=<enabled> outbound=<outboundEnabled> detached=<detached>
  updated=<updatedAt> (from <file>, createdAt)`, at `createdAt` (the file's
  modification time, ending `file mtime)`, when it has none), with the
  `conversationId` as `session_id`; so `records_relay` is set. A file
  without a `routes` list is one `parser:` row.
* `~/.letta/crons.json`: `tasks[]` with `id`, `agent_id`,
  `conversation_id` (`default`, `new` or a conversation id), `name`,
  `description`, `cron`, `timezone`, `recurring`, `prompt`, `status`,
  `created_at`, `scheduled_for`, `last_fired_at`, `fire_count`,
  `cancel_reason`, `last_run_at`, `last_run_outcome`, `last_run_reason`,
  `last_run_error`. One row per task, `scheduled task: <id> name=<name>
  status=<status> cron=<cron> timezone=<tz> recurring=<bool>
  scheduled_for=<UTC> agent=<agent_id> conversation=<conversation_id>
  fire_count=<n> last_fired=<UTC> last_run=<UTC> outcome=<outcome>
  reason=<reason> error=<error> cancel_reason=<reason> (from
  .letta/crons.json, created_at) description: <description> prompt:
  <prompt>`, at `created_at`, `session_id` the conversation (empty for
  `new`). Primary: the scheduled turn sends the prompt wrapped in a
  header (`formatScheduledTaskPrompt`), so no transcript line repeats it,
  and fired, missed and cancelled tasks are dropped after a day.
* `~/.letta/runs/<task id>.jsonl`, one line per run: `ts` (ms), `jobId`,
  `action`, `status`, `outcome`, `reason`, `error`, `summary`, `agentId`,
  `conversationId`, `runId`, `scheduledFor`, `firedAt`, `missedCount`. One
  row per line, `scheduled task run: <jobId> action=<action>
  status=<status> outcome=<outcome> reason=<reason> agent=<agentId>
  conversation=<conversationId> run=<runId> scheduled_for=<UTC>
  fired=<UTC> missed=<n> summary=<summary> error=<error> (from <file>,
  ts)`, at `ts`. Primary; bad lines are reported.
* `~/.letta/listener-state/<24 hex>/<agent id>_<conversation id>.json`,
  a turn the remote listener did not finish, which no transcript holds:
  `agentId`, `conversationId`, `runId`, `toolCallIds`,
  `unstartedToolCallIds`, `results`, `workingDirectory`, `actingUserId`.
  One row `interrupted turn: agent <agentId> conversation
  <conversationId> run <runId> tool_calls=<ids> unstarted=<ids>
  results=<n> working_directory=<dir> acting_user=<id> (from <file>, file
  mtime)`, then per `results` entry (the Letta client SDK's
  `ApprovalReturn` `{type, approve, tool_call_id, reason}` or `ToolReturn`
  `{type, status, tool_call_id, tool_return, stdout, stderr}`) a
  `permission decision: <approve|deny> reason=<reason> (from <file>,
  interrupted turn, file mtime)` row or a `tool_result` row (`[error] `
  before the text when `status` is `error`), each with the
  `tool_call_id` as `tool_use_id`; all at the file's modification time
  (the record holds no time), `session_id` the conversation and
  `project_path` the working directory. Primary. The `.json.recovery-*`
  sidecars and `.tmp` files beside it are not wanted.

`-` stands for an absent value in all of these rows.

Sync rows (issue 153), so `records_sync` is set. In the default `api`
backend a conversation is server state, so a transcript directory whose
agent id does not start `agent-local-` (the local backend's prefix) gets
one `system` row before its first line's rows, at that line's
`captured_at`: `session synced: server conversation <conversation id>
agent <agent id> server <server> (from .letta/transcripts path, first
captured_at)`, `<server>` the matching `agents[]` entry's `baseUrl` in
`~/.letta/settings.json`, `api.letta.com` when the entry has none, `-`
when there is no entry or no file. Each `sessionsByServer` entry whose
key does not start `local:` gives one row at the file's modification
time, `session_id` the `conversationId`: `session synced: last session
on <key> agent <agentId> conversation <conversationId> (from <file>,
file mtime)`, `<file>` the path relative to the home or project, `-` for
an absent value.

Model rows in `messages.jsonl` come from the pi reader (`pi.model_text`):
`model: <id> provider=<provider>` at the first assistant `message.model`
(or `responseModel`) of a conversation and `model: <old> -> <new> ...` on
each change. The reflection transcript records no model.

Not parsed: `logs/chunk-logs/` (stream chunks cut to 200 characters),
the input ledger `state/<24 hex>/input-dispositions-v2.json`, and the
retired Letta server's `sqlite.db` (column encodings unverified).
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Iterator

from ..inputs import Artifact
from ..model import Row, compact
from ..timeutil import to_utc
from .base import (
    Options,
    Parser,
    error_rows,
    file_mtime,
    iter_jsonl,
    setting_value,
    text_of,
)
from .pi import SessionFile, args_summary, entry_rows, model_text, read_session

TRANSCRIPT_RX = re.compile(r"^\.letta/transcripts/([^/]+)/([^/]+)/transcript\.jsonl$")
LOCAL_RX = re.compile(r"^\.letta/lc-local-backend/conversations/([^/]+)/messages\.jsonl$")
SESSIONS_REL = ".letta/sessions.jsonl"
SETTINGS_REL = ".letta/settings.json"
LOCAL_SETTINGS_REL = ".letta/settings.local.json"
LEGACY_SETTINGS_REL = ".config/letta/settings.json"
CRONS_REL = ".letta/crons.json"
ROUTING_RX = re.compile(r"^\.letta/channels/([^/]+)/routing\.(?:json|yaml)$")
RUNS_RX = re.compile(r"^\.letta/runs/[^/]+\.jsonl$")
LISTENER_RX = re.compile(r"^\.letta/listener-state/[0-9a-f]{24}/[^/]+\.json$")
# The keys of a settings file's `permissions` object (PermissionRules).
PERMISSION_KEYS = ("mode", "allow", "deny", "ask", "alwaysAsk", "additionalDirectories")
LOCAL_AGENT_PREFIX = "agent-local-"
LETTA_CLOUD = "api.letta.com"
# The window a transcript line may lag its messages.jsonl twin: a turn's
# whole duration, since captured_at is stamped at the turn's end.
TURN_TOLERANCE_SECONDS = 3600.0


def decode_key(name: str) -> str:
    """`conversation:<id>` or `default:<agent id>` from a base64url
    directory name, or empty."""
    try:
        return base64.urlsafe_b64decode(name + "=" * (-len(name) % 4)).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return ""


def sanitize(segment: str) -> str:
    """The transcript directory name Letta derives from an id."""
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", segment).strip()
    return name or "unknown"


def _args_text(args) -> str:
    """A transcript `argsText` as the pi reader renders the same call's
    arguments: `args_summary` of the parsed JSON, else the text itself."""
    if not isinstance(args, str):
        return args_summary(args)
    try:
        return args_summary(json.loads(args))
    except ValueError:
        return args


def read_settings(path) -> dict | None:
    """A Letta settings file as a dict, or None when it cannot be read or
    is not a JSON object."""
    try:
        with open(path, "rb") as handle:
            document = json.loads(handle.read().decode("utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None


def _val(value) -> str:
    """A record value as row text, `-` when absent or empty."""
    if value is None or value == "":
        return "-"
    return setting_value(value)


def _bare_messages(session: SessionFile) -> SessionFile:
    """Schema 1: every line a bare pi-ai message. Wrapped as entries."""
    out = SessionFile()
    out.errors = session.errors
    for line_number, record in session.entries:
        meta = record.get("metadata")
        if not isinstance(meta, dict):
            meta = {}
        out.entries.append(
            (
                line_number,
                {"type": "message", "timestamp": meta.get("created_at"), "message": record},
            )
        )
    return out


def _last_snapshots(session: SessionFile) -> SessionFile:
    """Keep only the last entry for each `message.id`."""
    last: dict[str, int] = {}
    for i, (_, record) in enumerate(session.entries):
        message = record.get("message")
        if isinstance(message, dict) and message.get("id"):
            last[str(message.get("id"))] = i
    out = SessionFile()
    out.header, out.header_line, out.errors = session.header, session.header_line, session.errors
    for i, (line_number, record) in enumerate(session.entries):
        message = record.get("message")
        if isinstance(message, dict) and message.get("id") and last[str(message.get("id"))] != i:
            continue
        out.entries.append((line_number, record))
    return out


def _session_project(sessions: list[tuple[str, str]], timestamp: str) -> str:
    """The project of a transcript line captured at `ts`: that of the
    agent's earliest `sessions.jsonl` line at or after `ts` (the exit line
    of the CLI session the turn belongs to), else, when no line is later (a
    session still running, or one that ended without `/exit`), that of the
    latest line before it."""
    if not timestamp:
        return ""
    before = ""
    for session_time, project in sessions:
        if session_time >= timestamp:
            return project
        before = project
    return before


class LettaParser(Parser):
    agent = "letta"
    name = "letta"
    has_secondary = True
    records_sync = True
    records_relay = True

    def wants(self, artifact: Artifact) -> bool:
        rel = artifact.rel
        return (
            rel in (SESSIONS_REL, SETTINGS_REL, LOCAL_SETTINGS_REL, LEGACY_SETTINGS_REL, CRONS_REL)
            or bool(TRANSCRIPT_RX.match(rel))
            or bool(LOCAL_RX.match(rel))
            or bool(ROUTING_RX.match(rel))
            or bool(RUNS_RX.match(rel))
            or bool(LISTENER_RX.match(rel))
        )

    def secondary(self, artifact: Artifact) -> bool:
        return bool(TRANSCRIPT_RX.match(artifact.rel))

    def secondary_tolerance(self, artifact: Artifact) -> float:
        return TURN_TOLERANCE_SECONDS

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        if artifact.rel == SESSIONS_REL:
            yield from self._parse_sessions(artifact, opts)
            return
        if artifact.rel in (SETTINGS_REL, LOCAL_SETTINGS_REL, LEGACY_SETTINGS_REL):
            yield from self._parse_settings(artifact)
            return
        if artifact.rel == CRONS_REL:
            yield from self._parse_crons(artifact)
            return
        if RUNS_RX.match(artifact.rel):
            yield from self._parse_runs(artifact)
            return
        if LISTENER_RX.match(artifact.rel):
            yield from self._parse_interrupted(artifact)
            return
        route = ROUTING_RX.match(artifact.rel)
        if route:
            yield from self._parse_routing(artifact, route.group(1))
            return
        match = LOCAL_RX.match(artifact.rel)
        if match:
            yield from self._parse_local(artifact, match.group(1), opts)
            return
        match = TRANSCRIPT_RX.match(artifact.rel)
        assert match is not None  # wants() accepted only matching paths
        yield from self._parse_transcript(artifact, match.group(1), match.group(2), opts)

    # -- local backend ----------------------------------------------------

    def _parse_local(self, artifact: Artifact, dirname: str, opts: Options) -> Iterator[Row]:
        session = read_session(artifact.disk_path)
        key = decode_key(dirname)
        session_id = str(session.header.get("id") or key.partition(":")[2])
        cwd = str(session.header.get("cwd") or "")
        if (
            not session.header
            and session.entries
            and all(
                "role" in record and record.get("type") != "message"
                for _, record in session.entries
            )
        ):
            session = _bare_messages(session)
        else:
            session = _last_snapshots(session)
        if session.header:
            row = self.base_row(artifact)
            row.source_line = session.header_line
            row.timestamp_utc = to_utc(session.header.get("timestamp"))
            row.session_id, row.project_path, row.turn_type = session_id, cwd, "system"
            row.text = compact(
                "letta local-backend conversation start: %s cwd=%s" % (key or session_id, cwd),
            )
            yield row
        yield from entry_rows(self, artifact, session, opts, session_id, cwd)
        yield from error_rows(self, artifact, session.errors, session_id, cwd)

    # -- reflection transcript ------------------------------------------

    def _sessions(self, artifact: Artifact, agent_dir: str) -> list[tuple[str, str]]:
        """(timestamp, project) of the sessions.jsonl lines for this agent,
        sorted by time."""
        sessions_path = artifact.home.disk_path / SESSIONS_REL
        if (
            sessions_path.is_symlink()
            or not sessions_path.is_file()
            or (artifact.home.disk_path / ".letta").is_symlink()
        ):
            return []
        out = []
        for _, record in iter_jsonl(sessions_path, []):
            if sanitize(str(record.get("agent_id") or "")) == agent_dir and record.get("project"):
                timestamp = to_utc(record.get("timestamp"))
                if timestamp:
                    out.append((timestamp, str(record.get("project"))))
        return sorted(out)

    @staticmethod
    def _server(artifact: Artifact, agent_dir: str) -> str:
        """The server of a transcript's agent: the `baseUrl` of its
        `agents[]` entry in `~/.letta/settings.json`, `api.letta.com` when
        the entry has none, `-` when there is no entry or no file."""
        settings_path = artifact.home.disk_path / SETTINGS_REL
        if (
            settings_path.is_symlink()
            or not settings_path.is_file()
            or (artifact.home.disk_path / ".letta").is_symlink()
        ):
            return "-"
        agents = (read_settings(settings_path) or {}).get("agents")
        for entry in agents if isinstance(agents, list) else []:
            if isinstance(entry, dict) and sanitize(str(entry.get("agentId") or "")) == agent_dir:
                return str(entry.get("baseUrl") or LETTA_CLOUD)
        return "-"

    def _parse_transcript(
        self, artifact: Artifact, agent_dir: str, conversation_dir: str, opts: Options
    ) -> Iterator[Row]:
        sessions = self._sessions(artifact, agent_dir)
        server_side = not agent_dir.startswith(LOCAL_AGENT_PREFIX)
        errors: list = []
        for line_number, record in iter_jsonl(artifact.disk_path, errors):
            timestamp = to_utc(record.get("captured_at"))
            project = _session_project(sessions, timestamp)

            def base() -> Row:
                row = self.base_row(artifact)
                row.source_line = line_number
                row.timestamp_utc = timestamp
                row.session_id = conversation_dir
                row.project_path = project
                return row

            if server_side:
                server_side = False
                row = base()
                row.turn_type = "system"
                row.text = compact(
                    "session synced: server conversation %s agent %s server %s "
                    "(from .letta/transcripts path, first captured_at)"
                    % (conversation_dir, agent_dir, self._server(artifact, agent_dir))
                )
                yield row

            kind = record.get("kind")
            text = str(record.get("text") or "")
            if kind in ("user", "assistant"):
                row = base()
                row.turn_type = kind
                row.text = compact(text)
                yield row
            elif kind == "reasoning":
                if opts.include_thinking:
                    row = base()
                    row.turn_type = "thinking"
                    row.text = compact(text)
                    yield row
            elif kind == "error":
                row = base()
                row.turn_type = "system"
                row.text = compact("error: " + text)
                yield row
            elif kind == "tool_call":
                name = str(record.get("name") or "")
                row = base()
                row.turn_type, row.tool_name = "tool_use", name
                row.text = compact(_args_text(record.get("argsText")))
                yield row
                if "resultText" in record or "resultOk" in record:
                    result = str(record.get("resultText") or "")
                    if record.get("resultOk") is False:
                        result = "[error] " + result
                    row = base()
                    row.turn_type, row.tool_name = "tool_result", name
                    row.text = compact(result)
                    yield row
        yield from error_rows(self, artifact, errors, conversation_dir)

    # -- settings.json and settings.local.json ---------------------------

    def _parse_settings(self, artifact: Artifact) -> Iterator[Row]:
        """One sync row per `sessionsByServer` entry whose key does not
        start `local:` (not in the legacy `.config/letta/settings.json`,
        which Letta reads only for its permissions), then one permission
        row per entry of the `permissions` object, all at the file's
        modification time; one `parser:` row when the file is not a JSON
        object."""
        document = read_settings(artifact.disk_path)
        project = artifact.home.original if artifact.home.project else ""
        timestamp = file_mtime(artifact)

        def base() -> Row:
            row = self.base_row(artifact)
            row.source_line, row.turn_type, row.timestamp_utc = 1, "system", timestamp
            row.project_path = project
            return row

        if document is None:
            row = base()
            row.text = "parser: %s is not a JSON object" % artifact.rel
            yield row
            return
        servers = document.get("sessionsByServer")
        if artifact.rel == LEGACY_SETTINGS_REL or not isinstance(servers, dict):
            servers = {}
        for key, entry in servers.items():
            if str(key).startswith("local:"):
                continue
            entry = entry if isinstance(entry, dict) else {}
            row = base()
            row.session_id = str(entry.get("conversationId") or "")
            row.text = compact(
                "session synced: last session on %s agent %s conversation %s "
                "(from %s, file mtime)"
                % (
                    key,
                    entry.get("agentId") or "-",
                    entry.get("conversationId") or "-",
                    artifact.rel,
                )
            )
            yield row
        permissions = document.get("permissions")
        if not isinstance(permissions, dict):
            permissions = {}
        for key in PERMISSION_KEYS:
            value = permissions.get(key)
            entries = value if isinstance(value, list) else [] if value is None else [value]
            for entry in entries:
                row = base()
                row.text = compact(
                    "permission setting: permissions.%s=%s (from %s, file mtime)"
                    % (key, setting_value(entry), artifact.rel)
                )
                yield row

    # -- channels/<channel>/routing.json -----------------------------------

    def _parse_routing(self, artifact: Artifact, channel: str) -> Iterator[Row]:
        """One `session relayed:` row per route, at its `createdAt`, or at
        the file's modification time when it has none."""
        document = read_settings(artifact.disk_path)
        routes = document.get("routes") if document is not None else None
        if not isinstance(routes, list):
            row = self.base_row(artifact)
            row.source_line, row.turn_type = 1, "system"
            row.text = "parser: %s is not a JSON object with a routes list" % artifact.rel
            yield row
            return
        mtime = file_mtime(artifact)
        for route in routes:
            if not isinstance(route, dict):
                continue
            created = to_utc(route.get("createdAt"))
            row = self.base_row(artifact)
            row.source_line, row.turn_type = 1, "system"
            row.timestamp_utc = created or mtime
            row.session_id = str(route.get("conversationId") or "")
            row.text = compact(
                "session relayed: %s chat %s type %s thread %s account %s agent %s "
                "enabled=%s outbound=%s detached=%s updated=%s (from %s, %s)"
                % (
                    channel,
                    _val(route.get("chatId")),
                    _val(route.get("chatType")),
                    _val(route.get("threadId")),
                    _val(route.get("accountId")),
                    _val(route.get("agentId")),
                    _val(route.get("enabled")),
                    _val(route.get("outboundEnabled")),
                    _val(route.get("detached")),
                    _val(to_utc(route.get("updatedAt"))),
                    artifact.rel,
                    "createdAt" if created else "file mtime",
                )
            )
            yield row

    # -- crons.json and runs/<task id>.jsonl ---------------------------------

    def _parse_crons(self, artifact: Artifact) -> Iterator[Row]:
        """One `scheduled task:` row per task, at its `created_at`, or at
        the file's modification time when it has none."""
        document = read_settings(artifact.disk_path)
        if document is None:
            row = self.base_row(artifact)
            row.source_line, row.turn_type = 1, "system"
            row.text = "parser: %s is not a JSON object" % artifact.rel
            yield row
            return
        tasks = document.get("tasks")
        mtime = file_mtime(artifact)
        for task in tasks if isinstance(tasks, list) else ():
            if not isinstance(task, dict):
                continue
            created = to_utc(task.get("created_at"))
            conversation = str(task.get("conversation_id") or "")
            row = self.base_row(artifact)
            row.source_line, row.turn_type = 1, "system"
            row.timestamp_utc = created or mtime
            row.session_id = "" if conversation == "new" else conversation
            row.text = compact(
                "scheduled task: %s name=%s status=%s cron=%s timezone=%s recurring=%s "
                "scheduled_for=%s agent=%s conversation=%s fire_count=%s last_fired=%s "
                "last_run=%s outcome=%s reason=%s error=%s cancel_reason=%s "
                "(from %s, %s) description: %s prompt: %s"
                % (
                    _val(task.get("id")),
                    _val(task.get("name")),
                    _val(task.get("status")),
                    _val(task.get("cron")),
                    _val(task.get("timezone")),
                    _val(task.get("recurring")),
                    _val(to_utc(task.get("scheduled_for"))),
                    _val(task.get("agent_id")),
                    _val(conversation),
                    _val(task.get("fire_count")),
                    _val(to_utc(task.get("last_fired_at"))),
                    _val(to_utc(task.get("last_run_at"))),
                    _val(task.get("last_run_outcome")),
                    _val(task.get("last_run_reason")),
                    _val(task.get("last_run_error")),
                    _val(task.get("cancel_reason")),
                    artifact.rel,
                    "created_at" if created else "file mtime",
                    _val(task.get("description")),
                    _val(task.get("prompt")),
                )
            )
            yield row

    def _parse_runs(self, artifact: Artifact) -> Iterator[Row]:
        """One `scheduled task run:` row per line, at its `ts`."""
        errors: list = []
        for line_number, record in iter_jsonl(artifact.disk_path, errors):
            row = self.base_row(artifact)
            row.source_line, row.turn_type = line_number, "system"
            row.timestamp_utc = to_utc(record.get("ts"))
            row.session_id = str(record.get("conversationId") or "")
            row.text = compact(
                "scheduled task run: %s action=%s status=%s outcome=%s reason=%s agent=%s "
                "conversation=%s run=%s scheduled_for=%s fired=%s missed=%s summary=%s "
                "error=%s (from %s, ts)"
                % (
                    _val(record.get("jobId")),
                    _val(record.get("action")),
                    _val(record.get("status")),
                    _val(record.get("outcome")),
                    _val(record.get("reason")),
                    _val(record.get("agentId")),
                    _val(record.get("conversationId")),
                    _val(record.get("runId")),
                    _val(to_utc(record.get("scheduledFor"))),
                    _val(to_utc(record.get("firedAt"))),
                    _val(record.get("missedCount")),
                    _val(record.get("summary")),
                    _val(record.get("error")),
                    artifact.rel,
                )
            )
            yield row
        yield from error_rows(self, artifact, errors)

    # -- listener-state/<hash>/<agent>_<conversation>.json -------------------

    def _parse_interrupted(self, artifact: Artifact) -> Iterator[Row]:
        """An interrupted remote-listener turn: one `interrupted turn:` row,
        then per entry of `results` a `permission decision:` row (an
        `ApprovalReturn`, with `approve`) or a `tool_result` row (a
        `ToolReturn`, with `status`), joined on `tool_call_id`; all at the
        file's modification time, since the record holds no time."""
        document = read_settings(artifact.disk_path)
        timestamp = file_mtime(artifact)
        if document is None:
            row = self.base_row(artifact)
            row.source_line, row.turn_type, row.timestamp_utc = 1, "system", timestamp
            row.text = "parser: %s is not a JSON object" % artifact.rel
            yield row
            return
        session_id = str(document.get("conversationId") or "")
        cwd = str(document.get("workingDirectory") or "")

        def base() -> Row:
            row = self.base_row(artifact)
            row.source_line, row.turn_type, row.timestamp_utc = 1, "system", timestamp
            row.session_id, row.project_path = session_id, cwd
            return row

        def ids(key: str) -> str:
            value = document.get(key)
            items = [str(entry) for entry in value] if isinstance(value, list) else []
            return ",".join(items) or "-"

        results = document.get("results")
        results = (
            [entry for entry in results if isinstance(entry, dict)]
            if isinstance(results, list)
            else []
        )
        row = base()
        row.text = compact(
            "interrupted turn: agent %s conversation %s run %s tool_calls=%s unstarted=%s "
            "results=%d working_directory=%s acting_user=%s (from %s, file mtime)"
            % (
                _val(document.get("agentId")),
                _val(session_id),
                _val(document.get("runId")),
                ids("toolCallIds"),
                ids("unstartedToolCallIds"),
                len(results),
                _val(cwd),
                _val(document.get("actingUserId")),
                artifact.rel,
            )
        )
        yield row
        for result in results:
            row = base()
            row.tool_use_id = str(result.get("tool_call_id") or "")
            if "approve" in result:
                row.text = compact(
                    "permission decision: %s reason=%s (from %s, interrupted turn, file mtime)"
                    % (
                        "approve" if result.get("approve") is True else "deny",
                        _val(result.get("reason")),
                        artifact.rel,
                    )
                )
            else:
                text = text_of(result.get("tool_return"))
                row.turn_type = "tool_result"
                row.text = compact(("[error] " if result.get("status") == "error" else "") + text)
            yield row

    # -- sessions.jsonl --------------------------------------------------

    def _parse_sessions(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        errors: list = []
        seen: dict = {}  # the model per CLI session, for the `model:` rows
        for line_number, record in iter_jsonl(artifact.disk_path, errors):
            row = self.base_row(artifact)
            row.source_line = line_number
            row.timestamp_utc = to_utc(record.get("timestamp"))
            row.session_id = str(record.get("session_id") or "")
            row.project_path = str(record.get("project") or "")
            row.model = str(record.get("model") or "")
            row.turn_type = "system"
            duration = record.get("duration")
            if not isinstance(duration, dict):
                duration = {}
            if "exit_reason" in record or "message_count" in record:
                text = (
                    "letta session end: agent=%s exit_reason=%s messages=%s tool_calls=%s wall_ms=%s"
                    % (
                        record.get("agent_id") or "",
                        record.get("exit_reason") or "",
                        record.get("message_count", ""),
                        record.get("tool_call_count", ""),
                        duration.get("wall_ms", ""),
                    )
                )
            else:
                text = "letta session start: agent=%s provider=%s model=%s project=%s" % (
                    record.get("agent_id") or "",
                    record.get("provider") or "",
                    row.model,
                    row.project_path,
                )
            row.text = compact(text)
            yield row
            model_message = model_text(
                seen, row.session_id, row.model, str(record.get("provider") or "")
            )
            if model_message:
                model_row = self.base_row(artifact)
                model_row.source_line, model_row.turn_type = line_number, "system"
                model_row.timestamp_utc, model_row.session_id = row.timestamp_utc, row.session_id
                model_row.project_path, model_row.model = row.project_path, row.model
                model_row.text = compact(model_message)
                yield model_row
        yield from error_rows(self, artifact, errors)
