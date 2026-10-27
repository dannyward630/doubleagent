"""nanobot sessions, memory history, WebUI mirror, CLI history, settings, run records.

Validated against source, HKUDS/nanobot at acdae3d (see
`research/nanobot.md`), with a synthetic fixture; no real install
was checked. The SQLite session store below is source-derived from
HKUDS/nanobot at 909b277 (2026-10-19), whose `pyproject.toml` still reads
0.3.5 while the import module names 0.3.6 as the version that introduces
the store, so it may not be in a release yet. The state directory is
`.nanobot`, or `.nanobot-<instance>` (an instance's `--config` or `--home`
root under the home).
Files:

* `sessions/<workspace-id>/sessions.sqlite3` (with its `-wal` sidecar,
  read through `sqlite_util.open_copy`): the session store of record from
  0.3.6. Table `sessions` (`key`, `created_at`, `updated_at`, `metadata`
  JSON text) is the JSONL metadata line, one row per session, and
  `messages` (`session_key`, `position`, `record` JSON text) one message
  per row, `record` exactly a JSONL message line; both map as below.
  Sessions come in `created_at` order, each with its messages in
  `position` order and `source_line` the row's `rowid`. A `record` that
  is not a JSON object is its own row, `parser: unparseable record
  <position> (<reason>): <record>`, and a `metadata` value that is not
  one `parser: unparseable session metadata (<reason>): <metadata>`; the
  other rows are still yielded. `checkpoints` and `pending_inputs` are
  not read. `project_path` is the namespace's `.workspace`.
* `sessions/<workspace-id>/<stem>.jsonl`: one file per session key,
  `<workspace-id>` 32 hex characters, `<stem>` the URL-safe base64 of the
  key without padding. The sibling `sessions/<workspace-id>/.workspace`
  holds the workspace path, used as `project_path`. Legacy global
  `sessions/<key with ":" as "_">.jsonl` files (no `.workspace`) and
  `sessions/<workspace-id>/.migration-conflicts/*.jsonl` copies have the
  same format. Line 1 is `{"_type":"metadata", "key", "created_at",
  "updated_at", "metadata"}` (`metadata._nanobot_model_preset`,
  `metadata.last_channel`); an optional `{"_type":"provider_state"}` line
  is opaque and skipped; every other line is an OpenAI chat message:
  `role` (`user`, `assistant`, `tool`, `system`), `content` (string or
  `{type:"text", text}` blocks), `timestamp`, assistant `tool_calls[]`
  {`id`, `function`: {`name`, `arguments` (JSON string)}} and
  `reasoning_content`, tool `tool_call_id` and `name`, and the flags
  `_hidden_history` (a synthetic user message standing in for summarised
  history, emitted as `system`) and `_runtime_context` (context attached to
  a real user message, which stays `user`). `*.checkpoint.json` sidecars
  are volatile and not read.
* `memory/history.jsonl` under a nanobot directory (the default workspace
  is `.nanobot/workspace`): the compressed long-term journal, lines
  `{cursor, timestamp: "YYYY-MM-DD HH:MM", content, session_key?}`, each
  one `system` row with `session_id` the `session_key` and `project_path`
  the workspace holding `memory/`.

`session_id` is the metadata `key` (`<channel>:<chat_id>` names the
external sender, or `cli:direct`, `heartbeat`, `unified:default`), falling
back to the decoded file name. Every timestamp nanobot writes is naive host
local time (`datetime.now().isoformat()`), and the collection does not
record the host's zone, so they are emitted as if they were UTC, the same
convention as the Aider parser; correct them by the host's offset, which
`llm_usage.sqlite3` `llm_calls.started_at_ms` (true UTC) can give. Messages
without a timestamp inherit the previous one, else the metadata
`updated_at`. No model is recorded per message: the session's
`_nanobot_model_preset`, when set, is the `model` of every row. No git
branch is recorded. A preset also becomes a `system` row after the session
start row, at its time, `model: <preset> (preset)`: the value names a model
preset of nanobot's configuration, not a model id. `/new` empties a session
file, so earlier turns may survive only in `memory/history.jsonl` and the
WebUI mirror below.

Source-derived from HKUDS/nanobot at 909b277, not observed on any real
install (issue 207):

* Relay. A session key `<channel>:<chat_id>` whose channel is one of
  `MESSAGING_CHANNELS` (each channel's `name`) gives `session relayed:
  <channel> chat <chat_id> (from session key)` after the session start
  row, and a `metadata.last_channel` route of such a channel that differs
  from the key (a `unified:default` session answering through Telegram)
  `session relayed: <channel> chat <chat_id> (from
  metadata.last_channel)`; `records_relay` is set.
* Model switches. `/model <name>` keeps a `_command` user message and a
  `_command` assistant reply starting ``Switched model preset to
  `<preset>`.`` with a ``- Model: `<id>` `` line. Each such reply gives
  `model: <old> -> <new> (preset) requested=<name> resolved=<id>` after
  it; the metadata keeps only the last preset, so in a switched session
  the first switch, whose previous preset is recorded nowhere, reads
  `model: <new> (preset) requested=<name> resolved=<id>`, the start row's
  `model: <preset> (preset)` is not written, and the `model` column is
  empty before the first switch and the switched preset after each.
* Permission mode. `metadata.workspace_scope` {`project_path`,
  `access_mode` `restricted` or `full`}, the last WebUI scope, gives
  `permission mode: access_mode=<mode> project=<path> (from session
  metadata workspace_scope)` after the session start row, at its time.
* `config.json` (secret-flagged by the collector, since it holds API keys;
  only the keys below are read): one row per standing setting at the
  file's modification time, `permission setting: <key>=<value> (from
  <path>, file mtime)`, `<path>` relative to the home, for
  `tools.restrictToWorkspace`, `tools.ssrfWhitelist`,
  `tools.webuiAllowLocalServiceAccess` (or its legacy
  `allowLocalPreviewAccess`), `tools.webuiAllowRemotePackageInstall`,
  `tools.exec.enable`, `tools.exec.sandbox`, `tools.exec.allowPatterns`,
  `denyPatterns`, `sandboxRoBinds`, `sandboxRwBinds`, `allowedEnvKeys` and
  each `channels.<name>.allowFrom`, a list giving one row per entry; the
  key is named as the file spells it (camelCase as nanobot saves it, or
  snake_case, which it also accepts). A key the file lacks gives no row.
* `pairing.json` `{approved: {<channel>: [<sender_id>]}, pending: {<code>:
  {channel, sender_id, created_at, expires_at, delivery_status}}}`:
  `permission setting: pairing.approved.<channel>=<sender_id> (from <path>,
  file mtime)` per approved sender and `permission setting:
  pairing.pending.<channel>=<sender_id> expires_at=<utc>
  delivery_status=<status> (from <path>, created_at)` per pending request
  at its `created_at` (epoch seconds, true UTC); the pairing code is not
  shown.
* Cron and trigger run records, `cron/runs/<run id>.json` and
  `triggers/runs/<delivery id>.json` under a workspace (the default
  workspace inside the state directory, the state directory for the legacy
  cron location, or a project workspace the collector collected through
  the project catalog). Secondary: each repeats the turn of the bound
  session, and survives the session's deletion. A cron record (`job_id`,
  `job_name`, `session_key`, `prompt_vars.message`, `rendered_prompt`,
  `status`, `response`, `error`, `run_id`, `updated_at_ms`) gives a `user`
  row of the text the session stores for the turn, `Scheduled cron job
  triggered: <job_name>` and a blank line and the message (else
  `rendered_prompt`), at the run's start, the epoch milliseconds inside
  `run_id` (`<job id>:<ms>:<hex>`); an `assistant` row of `response` at
  `updated_at_ms`; and `cron run: job <job_name> (<job_id>) run <run_id>
  status=<status>` with ` error=<error>` at `updated_at_ms`. A trigger
  record (`trigger_id`, `delivery_id`, `content`, `created_at_ms`,
  `attempts`, `last_error`, `trigger_name`, `session_key`, `status`,
  `response`, `error`) gives `Local trigger received: <trigger_name or
  trigger_id>` and a blank line and `content` as `user` at
  `created_at_ms`, `response` as `assistant` and `trigger run: trigger
  <trigger_name> (<trigger_id>) delivery <delivery_id> status=<status>
  attempts=<n>` with ` error=<error>` at `updated_at_ms`. `session_id` is
  `session_key`, `project_path` the workspace holding `cron/` or
  `triggers/`. Every time is true UTC while the session's are local time
  emitted as if UTC, so the window is `WEBUI_TOLERANCE_SECONDS`, as for the
  WebUI transcript. A trigger's content and response longer than 4,000
  characters are cut in the record and then match nothing.
* `sessions/<workspace-id>/.webui_session_index.json`, the WebUI sidebar's
  rebuildable cache `{version, sessions: [...]}` of the WebUI transcripts
  that have no session row (a chat whose session is gone among them): one
  `system` row per entry, `webui sidebar entry: key=<key> title=<title>
  preview=<preview> model_preset=<preset> updated_at=<updated_at> (from
  .webui_session_index.json version <n>)`, absent fields left out, at
  `created_at` (naive local time, as the session files'), `session_id` the
  key. Secondary; its rows never pair, since they are `system` rows.

A file the parser reads whole (`config.json`, `pairing.json`, a run
record, the sidebar cache) that cannot be read or is not a JSON object is
one `parser:` row; a sidebar entry that is not an object is its own
`parser: unparseable record <n> (not a JSON object): <entry>` row.

`memory/history.jsonl` is a primary record, not a secondary source: its
entries are model-written summaries of archived messages, or `[RAW] <n>
messages` blocks of several formatted messages, never one event of the
session file, so no row of it repeats a session row.

These secondary sources (issues 122 and 178) repeat session events and
are read on every run; `secondary()` is True for them, and
`dedup.deduplicate` drops a row the session store also yields:

* The session JSONL a `sessions.sqlite3` imported, once the database is
  beside it: the namespace's own `sessions/<workspace-id>/<stem>.jsonl`,
  imported on the store's first start and never written again, so a
  frozen copy of the session as it stood that day; and
  `sessions/<workspace-id>/jsonl-backup/<name>.jsonl`, the older
  `<workspace>/sessions/<key with ":" as "_">.jsonl` files, imported, then
  copied there byte for byte and removed from the workspace. Same format
  and the same `timestamp` strings as the database's records, so the
  default 2-second window applies; a turn the database has since lost (a
  `/new`, a rewind, a deleted session) is kept from the copy. Without a
  database beside it, a namespace's JSONL is the store of record and is
  primary, as before 0.3.6. `.migration-conflicts/` copies and legacy
  global `sessions/*.jsonl` files, which the import does not read, stay
  primary. The frozen copy's session start row names the `updated_at` of
  the import, not the database's, and is kept beside the database's.

* `webui/<safe key>.jsonl` and `webui/<safe key>.segments/NNNNNN.jsonl`
  under a nanobot directory: the WebUI display transcript (schema version
  3), written only for WebUI chats, whose session key is
  `websocket:<chat_id>`. `<safe key>` is the key with `:` as `_`
  (`websocket_<chat_id>`), not the base64 stem of the session files. The
  active file holds the recent turns; when it passes 2 MiB, nanobot moves
  the older turns into the next numbered segment and rewrites the active
  file with the rest, so each file holds different turns and every one is
  read (`segments/manifest.json` is an index and is not). One event per
  line, `event` naming it, with `chat_id` and `created_at_ms` (epoch
  milliseconds, true UTC): `user` (`text`, `media_paths[]`) is a `user`
  row; `message` with no `kind` is an `assistant` row of `text`;
  `message` with `kind` `tool_hint` or `progress` carries `tool_events[]`
  {`phase` `start`/`end`/`error`, `call_id`, `name`, `arguments` (an
  object), `result`, `error`}, each `start` a `tool_use` row and each
  `end` or `error` a `tool_result` row, joined on `call_id` (the session's
  `tool_calls[].id`), and its `text`, a breadcrumb, becomes a `system`
  row only when it has no tool events; `message` `kind` `reasoning` and
  `reasoning_end` (`text`) are `thinking` rows, opt-in; `stream_end`
  (`text`) is an `assistant` row, except one with `merge_next`, whose
  text the next `stream_end` repeats; `file_edit` `edits[]` {`call_id`,
  `tool`, `absolute_path`, `phase`, `status`, `added`, `deleted`,
  `operation`} gives one `system` row per finished edit; `fork_marker`
  and `context_compaction` (`phase`) are `system` rows; `delta`,
  `reasoning_delta` (folded into their end records, and no longer
  written) and `turn_end` (latency and token counts) yield nothing, and
  any other event is a `system` row naming it. `session_id` is
  `websocket:` plus the record's `chat_id` (the session file's metadata
  `key`), else from the file name; `project_path` is the `.workspace` of
  the session file of that key under the same nanobot directory, when
  exactly one workspace has one, else empty. The legacy
  `webui/<safe key>.json` thread is not read: its shape is not recorded.
  Times: `created_at_ms` is true UTC while the session file's times are
  host local time emitted as if UTC, so the two differ by the host's UTC
  offset, at most 14 hours (UTC-12 to UTC+14); and the session file
  stamps a turn's assistant and tool messages when the turn is saved, at
  its end, while the WebUI stamps each as it streams. The tolerance is
  therefore `WEBUI_TOLERANCE_SECONDS`, 15 hours: the largest offset plus
  an hour of turn. A turn longer than that hour, a transcript written by
  a fork (every row stamped at the fork) and a user message carrying
  runtime context (appended to the session's copy, not the WebUI's) are
  shown twice. A WebUI row kept because no session row matched carries
  true UTC, unlike every other nanobot row.
  The `project_path` lookup reads session JSONL files only, so a WebUI
  chat whose session exists only in `sessions.sqlite3` gets none.
* `history/cli_history` under the state directory: `~/.nanobot` for every
  `--config` instance, but the `--home <dir>` option of 909b277 moves it
  into the chosen root (`nanobot/config/home.py`, `config/paths.py`
  `get_cli_history_path`), so it is selected under any `.nanobot*`
  directory, as the catalog's entries are. The CLI's prompt_toolkit
  `FileHistory`, `# <timestamp>`
  then one `+<line>` per input line, read with the Aider parser's
  `read_input_history`. Each entry is a `user` row at its own time (naive
  local time, emitted as if UTC like the session file's, so the default
  2-second window applies), with no `session_id` or `project_path`: the
  file is shared by every CLI session, so a row matches a session row of
  the same text on time alone.
"""

from __future__ import annotations

import base64
import json
import re
import sqlite3
from collections.abc import Generator, Iterable, Iterator
from pathlib import Path

from ..inputs import Artifact, error_reason
from ..model import Row, compact
from ..sqlite_util import is_sqlite, open_copy, table_names
from ..timeutil import to_utc
from .aider import read_input_history
from .base import (
    Options,
    Parser,
    compact_json,
    error_rows,
    file_mtime,
    iter_jsonl,
    setting_value,
    text_of,
    track_change,
)
from .openclaw import tool_args_text

STATE = r"\.nanobot(?:-[^/]+)?"
SESSION_RX = re.compile(
    r"^"
    + STATE
    + r"/sessions/(?:(?P<ws>[0-9a-f]{32})/(?P<sub>\.migration-conflicts/|jsonl-backup/)?)?"
    r"(?P<stem>[^/]+)\.jsonl$"
)
DB_RX = re.compile(r"^" + STATE + r"/sessions/[0-9a-f]{32}/sessions\.sqlite3$")
DB_NAME = "sessions.sqlite3"
HISTORY_RX = re.compile(r"^" + STATE + r"/(?:.+/)?memory/history\.jsonl$")
WEBUI_RX = re.compile(
    r"^" + STATE + r"/webui/(?:(?P<seg>[^/]+)\.segments/\d{6}|(?P<stem>[^/]+))\.jsonl$"
)
CLI_HISTORY_RX = re.compile(r"^" + STATE + r"/history/cli_history$")
CONFIG_RX = re.compile(r"^" + STATE + r"/config\.json$")
PAIRING_RX = re.compile(r"^" + STATE + r"/pairing\.json$")
SIDEBAR_RX = re.compile(r"^" + STATE + r"/sessions/[0-9a-f]{32}/\.webui_session_index\.json$")
# A cron or trigger run record: under a workspace inside the state directory
# (`.nanobot/workspace/cron/runs/`), under the state directory itself (the
# legacy `cron/jobs.json` location), or at the root of a project workspace
# the collector collected (the bare form, accepted only for a project base).
RUN_RX = re.compile(r"^(?:" + STATE + r"/(?P<ws>.+/)?)?(?P<kind>cron|triggers)/runs/[^/]+\.json$")
ORIGINAL_RUN_RX = re.compile(r"^(.*)[\\/](?:cron|triggers)[\\/]runs[\\/][^\\/]+$")
WEBUI_PREFIX = "websocket:"
# The host's UTC offset (at most 14 hours) plus an hour of turn; see the
# module docstring. The cron and trigger run records use it too.
WEBUI_TOLERANCE_SECONDS = 15 * 3600.0
# Session key prefixes of the channels that carry a chat through a messaging
# platform (each channel's `name`, nanobot/channels/*/runtime.py at 909b277);
# `websocket` (the WebUI), `cli`, `api`, `heartbeat`, `dream:` and
# `unified:default` are local.
MESSAGING_CHANNELS = frozenset(
    {
        "dingtalk",
        "discord",
        "email",
        "feishu",
        "linear",
        "matrix",
        "mattermost",
        "mochat",
        "msteams",
        "napcat",
        "qq",
        "signal",
        "slack",
        "telegram",
        "wecom",
        "weixin",
        "whatsapp",
        "whatsapp_agent",
    }
)
# `config.json` settings that grant or restrict what the agent may do: each
# tuple is the spellings nanobot accepts for one key (camelCase, as it saves
# them, snake_case and any legacy alias); the row names the key as the file
# spells it, and a list gives one row per entry.
CONFIG_TOOL_KEYS = (
    ("restrictToWorkspace", "restrict_to_workspace"),
    ("ssrfWhitelist", "ssrf_whitelist"),
    (
        "webuiAllowLocalServiceAccess",
        "webui_allow_local_service_access",
        "allowLocalPreviewAccess",
        "allow_local_preview_access",
    ),
    ("webuiAllowRemotePackageInstall", "webui_allow_remote_package_install"),
)
CONFIG_EXEC_KEYS = (
    ("enable",),
    ("sandbox",),
    ("allowPatterns", "allow_patterns"),
    ("denyPatterns", "deny_patterns"),
    ("sandboxRoBinds", "sandbox_ro_binds"),
    ("sandboxRwBinds", "sandbox_rw_binds"),
    ("allowedEnvKeys", "allowed_env_keys"),
)
# The `/model <preset>` command and its reply (nanobot/command/builtin.py).
MODEL_COMMAND_RX = re.compile(r"^/model\s+(\S.*?)\s*$", re.S)
SWITCH_RX = re.compile(r"^Switched model preset to `([^`]*)`")
RESOLVED_RX = re.compile(r"^- Model: `([^`]*)`", re.M)
# Stream chunks (folded into their end records) and the turn boundary.
WEBUI_SILENT = frozenset({"delta", "reasoning_delta", "turn_end"})
ORIGINAL_MEMORY_RX = re.compile(r"^(.*)[\\/]memory[\\/]history\.jsonl$")


def decode_stem(stem: str) -> str:
    """Session key from a file stem: URL-safe base64 without padding, or the
    legacy lossy `<channel>_<chat>` form returned unchanged."""
    try:
        key = base64.urlsafe_b64decode(stem + "=" * (-len(stem) % 4)).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return stem
    if base64.urlsafe_b64encode(key.encode("utf-8")).decode("ascii").rstrip("=") != stem:
        return stem
    return key


def _read_marker(path: Path) -> str:
    """The stripped text of a `.workspace` file, "" when it is missing, a
    symlink or unreadable."""
    try:
        if path.is_symlink() or not path.is_file():
            return ""
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _json_object(raw: object, rowid: int, label: str, errors: list) -> dict | None:
    """`raw`, a stored JSON text, decoded to an object; None, with
    (rowid, `<label> (<reason>)`, the value as text) appended to `errors`,
    when it does not decode to one."""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    try:
        value = json.loads(text)
    except ValueError as error:
        errors.append((rowid, "%s (%s)" % (label, error), text))
        return None
    if not isinstance(value, dict):
        errors.append((rowid, "%s (not a JSON object)" % label, text))
        return None
    return value


def relay_texts(session_id: str, last_channel: object) -> list[str]:
    """The `session relayed:` row texts of a session: one for a session key
    `<channel>:<chat_id>` whose channel is a messaging platform, and one for
    a `metadata.last_channel` route of a messaging platform that differs
    from the key (`unified:default` answering through Telegram)."""
    texts = []
    channel, _, chat = session_id.partition(":")
    if channel in MESSAGING_CHANNELS and chat:
        texts.append("session relayed: %s chat %s (from session key)" % (channel, chat))
    if isinstance(last_channel, str) and last_channel != session_id:
        channel, _, chat = last_channel.partition(":")
        if channel in MESSAGING_CHANNELS and chat:
            texts.append(
                "session relayed: %s chat %s (from metadata.last_channel)" % (channel, chat)
            )
    return texts


def _first_key(mapping: dict, names: tuple[str, ...]) -> tuple[str, object] | None:
    """(name, value) of the first of `names` that `d` holds, else None."""
    for name in names:
        if name in mapping:
            return name, mapping[name]
    return None


def _has_switch(records: list[tuple[int, dict]]) -> bool:
    """True when a session records a `/model` switch: a `_command` assistant
    message whose text starts `Switched model preset to`."""
    return any(
        record.get("role") == "assistant"
        and record.get("_command")
        and SWITCH_RX.match(text_of(record.get("content")))
        for _, record in records
    )


class NanobotParser(Parser):
    agent = "nanobot"
    name = "nanobot"
    has_secondary = True
    records_relay = True

    def wants(self, artifact: Artifact) -> bool:
        return bool(
            SESSION_RX.match(artifact.rel)
            or HISTORY_RX.match(artifact.rel)
            or WEBUI_RX.match(artifact.rel)
            or DB_RX.match(artifact.rel)
            or CLI_HISTORY_RX.match(artifact.rel)
            or CONFIG_RX.match(artifact.rel)
            or PAIRING_RX.match(artifact.rel)
            or SIDEBAR_RX.match(artifact.rel)
            or self._is_run(artifact)
        )

    @staticmethod
    def _is_run(artifact: Artifact) -> bool:
        """True for a cron or trigger run record; the bare `cron/runs/` form
        only at the root of a project base, where the project catalog put
        it."""
        match = RUN_RX.match(artifact.rel)
        if match is None:
            return False
        return artifact.rel.startswith(".nanobot") or artifact.home.project

    def secondary(self, artifact: Artifact) -> bool:
        return (
            bool(
                WEBUI_RX.match(artifact.rel)
                or CLI_HISTORY_RX.match(artifact.rel)
                or SIDEBAR_RX.match(artifact.rel)
            )
            or self._is_run(artifact)
            or self._frozen(artifact)
        )

    @staticmethod
    def _namespace(artifact: Artifact) -> Path | None:
        """The `sessions/<workspace-id>` directory of a namespaced session
        file (the file's own directory, or its parent for a
        `.migration-conflicts/` or `jsonl-backup/` copy); None for a legacy
        global file or any other path."""
        match = SESSION_RX.match(artifact.rel)
        if not match or not match.group("ws"):
            return None
        return artifact.disk_path.parent.parent if match.group("sub") else artifact.disk_path.parent

    @classmethod
    def _frozen(cls, artifact: Artifact) -> bool:
        """True for a session JSONL that the namespace's `sessions.sqlite3`
        imported: a `<stem>.jsonl` of the namespace or a `jsonl-backup/`
        copy, when the database is beside it. A `.migration-conflicts/`
        copy and a legacy global file were never imported."""
        match = SESSION_RX.match(artifact.rel)
        namespace = cls._namespace(artifact)
        if match is None or namespace is None or match.group("sub") == ".migration-conflicts/":
            return False
        database = namespace / DB_NAME
        return not database.is_symlink() and database.is_file()

    def secondary_tolerance(self, artifact: Artifact) -> float:
        if WEBUI_RX.match(artifact.rel) or self._is_run(artifact):
            return WEBUI_TOLERANCE_SECONDS
        return super().secondary_tolerance(artifact)

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        if SESSION_RX.match(artifact.rel):
            yield from self._parse_session(artifact, opts)
        elif DB_RX.match(artifact.rel):
            yield from self._parse_db(artifact, opts)
        elif WEBUI_RX.match(artifact.rel):
            yield from self._parse_webui(artifact, opts)
        elif CLI_HISTORY_RX.match(artifact.rel):
            yield from self._parse_cli_history(artifact)
        elif CONFIG_RX.match(artifact.rel):
            yield from self._parse_config(artifact)
        elif PAIRING_RX.match(artifact.rel):
            yield from self._parse_pairing(artifact)
        elif SIDEBAR_RX.match(artifact.rel):
            yield from self._parse_sidebar(artifact)
        elif RUN_RX.match(artifact.rel):
            yield from self._parse_run(artifact)
        else:
            yield from self._parse_history(artifact, opts)

    def _parse_session(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        match = SESSION_RX.match(artifact.rel)
        assert match is not None  # parse() routes only matching paths here
        namespace = self._namespace(artifact)
        project = _read_marker(namespace / ".workspace") if namespace else ""
        errors: list = []
        session_id = yield from self._session_rows(
            artifact,
            opts,
            decode_stem(match.group("stem")),
            project,
            iter_jsonl(artifact.disk_path, errors),
        )
        yield from error_rows(self, artifact, errors, session_id, project)

    def _session_rows(
        self,
        artifact: Artifact,
        opts: Options,
        session_id: str,
        project: str,
        records: Iterable[tuple[int, dict]],
    ) -> Generator[Row, None, str]:
        """The rows of one session from its (source_line, record) pairs: the
        metadata record first, then the messages, as a session JSONL holds
        them and as `_parse_db` rebuilds them from `sessions.sqlite3`.
        Returns the session id, the metadata `key` when there is one."""
        model = ""
        last_timestamp = ""
        models: dict = {}
        records = list(records)
        # With a `/model` switch in the session, the metadata's preset is the
        # last switch's, not the session's first: the switch rows name the
        # presets instead, and the rows before the first switch name none.
        switched = _has_switch(records)
        preset = ""  # the preset the last switch set, "" before any
        requested = ""  # the preset name of the last `/model <name>`

        def make_row(
            source_line: int, turn_type: str, text: str, tool_name: str = "", tool_use_id: str = ""
        ) -> Row:
            row = self.base_row(artifact)
            row.source_line = source_line
            row.session_id = session_id
            row.project_path = project
            row.timestamp_utc = last_timestamp
            row.model = model
            row.turn_type = turn_type
            row.tool_name = tool_name
            row.tool_use_id = tool_use_id
            row.text = compact(text)
            return row

        for line_number, record in records:
            record_type = record.get("_type")
            if record_type == "metadata":
                if record.get("key"):
                    session_id = str(record["key"])
                meta = record.get("metadata")
                if not isinstance(meta, dict):
                    meta = {}
                model = "" if switched else str(meta.get("_nanobot_model_preset") or "")
                last_timestamp = to_utc(record.get("created_at")) or to_utc(
                    record.get("updated_at")
                )
                yield make_row(
                    line_number,
                    "system",
                    " ".join(
                        part
                        for part in (
                            "session start: key=%s" % session_id,
                            "last_channel=%s" % meta["last_channel"]
                            if meta.get("last_channel")
                            else "",
                            "updated_at=%s" % record["updated_at"]
                            if record.get("updated_at")
                            else "",
                            "workspace=%s" % project if project else "",
                        )
                        if part
                    ),
                )
                for text in relay_texts(session_id, meta.get("last_channel")):
                    yield make_row(line_number, "system", text)
                text = track_change("model", models, session_id, model)
                if text:
                    yield make_row(line_number, "system", text + " (preset)")
                scope = meta.get("workspace_scope")
                if isinstance(scope, dict) and (
                    scope.get("access_mode") or scope.get("project_path")
                ):
                    yield make_row(
                        line_number,
                        "system",
                        "permission mode: access_mode=%s project=%s"
                        " (from session metadata workspace_scope)"
                        % (scope.get("access_mode") or "", scope.get("project_path") or ""),
                    )
                continue
            if record_type is not None and "role" not in record:
                continue  # provider_state and future record types
            last_timestamp = to_utc(record.get("timestamp")) or last_timestamp
            role = record.get("role")
            text = text_of(record.get("content"))
            if role == "user":
                if record.get("_hidden_history"):
                    yield make_row(line_number, "system", "summarised history: " + text)
                else:
                    if record.get("_command"):
                        match = MODEL_COMMAND_RX.match(text)
                        requested = match.group(1) if match else requested
                    yield make_row(line_number, "user", text)
            elif role == "assistant":
                reasoning = record.get("reasoning_content")
                if opts.include_thinking and isinstance(reasoning, str) and reasoning:
                    yield make_row(line_number, "thinking", reasoning)
                if text:
                    yield make_row(line_number, "assistant", text)
                match = SWITCH_RX.match(text) if record.get("_command") else None
                if match:
                    resolved = RESOLVED_RX.search(text)
                    switch = "model: %s%s (preset)%s%s" % (
                        preset + " -> " if preset else "",
                        match.group(1),
                        " requested=%s" % requested if requested else "",
                        " resolved=%s" % resolved.group(1) if resolved else "",
                    )
                    preset = model = match.group(1)
                    requested = ""
                    yield make_row(line_number, "system", switch)
                for tool_call in record.get("tool_calls") or []:
                    if not isinstance(tool_call, dict):
                        continue
                    function = tool_call.get("function")
                    if not isinstance(function, dict):
                        function = {}
                    yield make_row(
                        line_number,
                        "tool_use",
                        tool_args_text(function.get("arguments")),
                        str(function.get("name") or ""),
                        str(tool_call.get("id") or ""),
                    )
            elif role == "tool":
                yield make_row(
                    line_number,
                    "tool_result",
                    text,
                    str(record.get("name") or ""),
                    str(record.get("tool_call_id") or ""),
                )
            else:
                yield make_row(line_number, "system", "%s: %s" % (role or "message", text))
        return session_id

    def _parse_db(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        project = _read_marker(artifact.disk_path.parent / ".workspace")
        if not is_sqlite(artifact.disk_path):
            yield self._file_row(artifact, project, "parser: not a SQLite database")
            return
        messages: dict[str, list[tuple[int, object, object]]] = {}
        try:
            with open_copy(artifact.disk_path) as connection:
                missing = {"sessions", "messages"} - table_names(connection)
                if missing:
                    text = "parser: no %s table in the session database" % " or ".join(
                        sorted(missing)
                    )
                    yield self._file_row(artifact, project, text)
                    return
                sessions = [
                    tuple(table_row)
                    for table_row in connection.execute(
                        "SELECT rowid, key, created_at, updated_at, metadata FROM sessions"
                        " ORDER BY created_at, key"
                    )
                ]
                for rowid, key, position, record in connection.execute(
                    "SELECT rowid, session_key, position, record FROM messages"
                    " ORDER BY session_key, position"
                ):
                    messages.setdefault(str(key), []).append((rowid, position, record))
        except sqlite3.DatabaseError as error:
            yield self._file_row(artifact, project, "parser: SQLite error: %s" % error)
            return
        known = {str(sess[1]) for sess in sessions}
        # Messages whose session row is gone (nanobot enforces the foreign
        # key only on its own connections) still yield their rows.
        heads: list[tuple[str, tuple | None]] = [(str(sess[1]), sess) for sess in sessions]
        heads += [(k, None) for k in sorted(messages) if k not in known]
        for key, head in heads:
            errors: list = []
            records = self._db_records(head, messages.get(key, []), errors)
            session_id = yield from self._session_rows(artifact, opts, key, project, records)
            yield from error_rows(self, artifact, errors, session_id, project)

    @staticmethod
    def _db_records(
        head: tuple | None, messages: list[tuple[int, object, object]], errors: list
    ) -> Iterator[tuple[int, dict]]:
        """(rowid, record) pairs of one session of `sessions.sqlite3`: its
        `sessions` row as the JSONL metadata record, when the row exists,
        then each `messages.record` in `position` order. A `metadata` or
        `record` value that is not a JSON object is appended to `errors` as
        (rowid, message, the stored value as text) and skipped."""
        if head is not None:
            rowid, key, created_at, updated_at, raw = head
            meta = _json_object(raw, rowid, "unparseable session metadata", errors)
            yield (
                rowid,
                {
                    "_type": "metadata",
                    "key": key,
                    "created_at": created_at,
                    "updated_at": updated_at,
                    "metadata": meta or {},
                },
            )
        for rowid, position, raw in messages:
            record = _json_object(raw, rowid, "unparseable record %s" % position, errors)
            if record is not None:
                yield rowid, record

    def _file_row(self, artifact: Artifact, project: str, text: str) -> Row:
        """A whole-file `parser:` row for a database that cannot be read."""
        row = self.base_row(artifact)
        row.project_path = project
        row.turn_type = "system"
        row.text = text
        return row

    def _parse_history(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        match = ORIGINAL_MEMORY_RX.match(artifact.original or "")
        project = match.group(1) if match else ""
        errors: list = []
        for line_number, record in iter_jsonl(artifact.disk_path, errors):
            row = self.base_row(artifact)
            row.source_line = line_number
            row.session_id = str(record.get("session_key") or "")
            row.project_path = project
            row.timestamp_utc = to_utc(record.get("timestamp"))
            row.turn_type = "system"
            row.text = compact(
                "memory history #%s: %s" % (record.get("cursor", ""), record.get("content") or ""),
            )
            yield row
        yield from error_rows(self, artifact, errors, "", project)

    @staticmethod
    def _webui_workspace(artifact: Artifact, session_id: str) -> str:
        """The `.workspace` of the session file for `session_id` under the
        same nanobot directory, when exactly one workspace holds one."""
        match = WEBUI_RX.match(artifact.rel)
        assert match is not None  # parse() routes only matching paths here
        state = artifact.disk_path.parents[2 if match.group("seg") else 1]
        stem = base64.urlsafe_b64encode(session_id.encode("utf-8")).decode("ascii").rstrip("=")
        found: set[str] = set()
        try:
            for session_file in (state / "sessions").glob("*/%s.jsonl" % stem):
                if (
                    not (session_file.is_symlink() or session_file.parent.is_symlink())
                    and session_file.is_file()
                ):
                    found.add(_read_marker(session_file.parent / ".workspace"))
        except OSError:
            return ""
        found.discard("")
        return found.pop() if len(found) == 1 else ""

    def _parse_webui(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        match = WEBUI_RX.match(artifact.rel)
        assert match is not None  # parse() routes only matching paths here
        stem = match.group("seg") or match.group("stem")
        fallback = stem
        if stem.startswith("websocket_"):
            fallback = WEBUI_PREFIX + stem[len("websocket_") :]
        projects: dict[str, str] = {}
        errors: list = []

        def make_row(
            source_line: int,
            row_session_id: str,
            timestamp: object,
            event: tuple[str, str, str, str],
        ) -> Row:
            turn_type, text, tool_name, tool_use_id = event
            if row_session_id not in projects:
                projects[row_session_id] = self._webui_workspace(artifact, row_session_id)
            row = self.base_row(artifact)
            row.source_line = source_line
            row.session_id = row_session_id
            row.project_path = projects[row_session_id]
            row.timestamp_utc = to_utc(timestamp)
            row.turn_type = turn_type
            row.tool_name = tool_name
            row.tool_use_id = tool_use_id
            row.text = compact(text)
            return row

        session_id = fallback
        for line_number, record in iter_jsonl(artifact.disk_path, errors):
            chat = record.get("chat_id")
            session_id = WEBUI_PREFIX + chat if isinstance(chat, str) and chat else fallback
            for event in self._webui_events(record, opts):
                yield make_row(line_number, session_id, record.get("created_at_ms"), event)
        if errors:
            if session_id not in projects:
                projects[session_id] = self._webui_workspace(artifact, session_id)
            yield from error_rows(self, artifact, errors, session_id, projects[session_id])

    @staticmethod
    def _webui_events(record: dict, opts: Options) -> Iterator[tuple[str, str, str, str]]:
        """(turn_type, text, tool_name, tool_use_id) per row of one WebUI
        record; the module docstring maps each event."""
        event = record.get("event")
        text = record.get("text") if isinstance(record.get("text"), str) else ""
        if event == "user":
            media = [
                str(media_path) for media_path in record.get("media_paths") or [] if media_path
            ]
            yield (
                "user",
                text or " ".join("[media: %s]" % media_path for media_path in media),
                "",
                "",
            )
        elif event == "message":
            kind = record.get("kind")
            tool_events = [
                item for item in record.get("tool_events") or [] if isinstance(item, dict)
            ]
            for entry in tool_events:
                name, call_id = str(entry.get("name") or ""), str(entry.get("call_id") or "")
                if entry.get("phase") == "start":
                    yield "tool_use", tool_args_text(entry.get("arguments")), name, call_id
                elif entry.get("phase") == "end":
                    result = entry.get("result")
                    body = result if isinstance(result, str) else compact_json(result)
                    yield "tool_result", body, name, call_id
                elif entry.get("phase") == "error":
                    yield "tool_result", str(entry.get("error") or ""), name, call_id
            if kind == "reasoning":
                if opts.include_thinking and text:
                    yield "thinking", text, "", ""
            elif kind in ("tool_hint", "progress"):
                if text and not tool_events:
                    yield "system", "%s: %s" % (str(kind).replace("_", " "), text), "", ""
            elif text:
                yield "assistant", text, "", ""
        elif event == "stream_end":
            if text and not record.get("merge_next"):
                yield "assistant", text, "", ""
        elif event == "reasoning_end":
            if opts.include_thinking and text:
                yield "thinking", text, "", ""
        elif event == "file_edit":
            for entry in record.get("edits") or []:
                if isinstance(entry, dict) and entry.get("phase") != "start":
                    yield (
                        "system",
                        "file edit: %s %s +%s -%s%s"
                        % (
                            entry.get("status") or entry.get("phase") or "",
                            entry.get("absolute_path") or entry.get("path") or "",
                            entry.get("added", 0),
                            entry.get("deleted", 0),
                            " (%s)" % entry["operation"] if entry.get("operation") else "",
                        ),
                        str(entry.get("tool") or ""),
                        str(entry.get("call_id") or ""),
                    )
        elif event == "fork_marker":
            yield "system", "webui fork marker: the fork starts here", "", ""
        elif event == "context_compaction":
            yield "system", "context compaction: %s" % (record.get("phase") or ""), "", ""
        elif isinstance(event, str) and event and event not in WEBUI_SILENT:
            yield "system", "webui event: %s" % event, "", ""

    def _load_object(self, artifact: Artifact, what: str) -> tuple[dict | None, Row | None]:
        """The JSON object in `artifact`, or None and the whole-file
        `parser:` row that says why it could not be read."""
        try:
            value = json.loads(artifact.disk_path.read_text(encoding="utf-8", errors="replace"))
        except OSError as error:
            return None, self._file_row(
                artifact, "", "parser: unreadable %s: %s" % (what, error_reason(error))
            )
        except ValueError as error:
            return None, self._file_row(
                artifact, "", "parser: %s did not parse: %s" % (what, error)
            )
        if not isinstance(value, dict):
            return None, self._file_row(artifact, "", "parser: %s is not a JSON object" % what)
        return value, None

    def _setting_row(
        self, artifact: Artifact, timestamp: str, text: str, session_id: str = ""
    ) -> Row:
        row = self.base_row(artifact)
        row.timestamp_utc = timestamp
        row.session_id = session_id
        row.turn_type = "system"
        row.text = compact(text)
        return row

    def _parse_config(self, artifact: Artifact) -> Iterator[Row]:
        """One `permission setting:` row per standing setting of
        `config.json` that grants or restricts the agent, at the file's
        modification time; no other key (the file holds API keys) is read."""
        data, problem = self._load_object(artifact, "config.json")
        if data is None:
            yield from [problem] if problem else []
            return
        timestamp = file_mtime(artifact)
        tail = " (from %s, file mtime)" % artifact.rel
        tools = data.get("tools")
        tools = tools if isinstance(tools, dict) else {}
        settings: list[tuple[str, object]] = []
        for names in CONFIG_TOOL_KEYS:
            hit = _first_key(tools, names)
            if hit:
                settings.append(("tools.%s" % hit[0], hit[1]))
        exec_config = tools.get("exec")
        exec_config = exec_config if isinstance(exec_config, dict) else {}
        for names in CONFIG_EXEC_KEYS:
            hit = _first_key(exec_config, names)
            if hit:
                settings.append(("tools.exec.%s" % hit[0], hit[1]))
        channels = data.get("channels")
        for name, config in (channels if isinstance(channels, dict) else {}).items():
            if isinstance(config, dict):
                hit = _first_key(config, ("allowFrom", "allow_from"))
                if hit:
                    settings.append(("channels.%s.%s" % (name, hit[0]), hit[1]))
        for key, value in settings:
            for entry in value if isinstance(value, list) else [value]:
                yield self._setting_row(
                    artifact,
                    timestamp,
                    "permission setting: %s=%s%s" % (key, setting_value(entry), tail),
                )

    def _parse_pairing(self, artifact: Artifact) -> Iterator[Row]:
        """`pairing.json`: a row per approved chat sender at the file's
        modification time, and one per pending request at its `created_at`.
        The pending request's code is not shown."""
        data, problem = self._load_object(artifact, "pairing.json")
        if data is None:
            yield from [problem] if problem else []
            return
        timestamp = file_mtime(artifact)
        approved = data.get("approved")
        for channel, senders in (approved if isinstance(approved, dict) else {}).items():
            for sender in senders if isinstance(senders, list) else []:
                yield self._setting_row(
                    artifact,
                    timestamp,
                    "permission setting: pairing.approved.%s=%s (from %s, file mtime)"
                    % (channel, setting_value(sender), artifact.rel),
                )
        pending = data.get("pending")
        for info in (pending if isinstance(pending, dict) else {}).values():
            if not isinstance(info, dict):
                continue
            yield self._setting_row(
                artifact,
                to_utc(info.get("created_at")),
                "permission setting: pairing.pending.%s=%s expires_at=%s%s (from %s, created_at)"
                % (
                    info.get("channel") or "",
                    setting_value(info.get("sender_id") or ""),
                    to_utc(info.get("expires_at")),
                    " delivery_status=%s" % info["delivery_status"]
                    if info.get("delivery_status")
                    else "",
                    artifact.rel,
                ),
            )

    def _parse_sidebar(self, artifact: Artifact) -> Iterator[Row]:
        """`.webui_session_index.json`: one `system` row per cached sidebar
        entry, at its `created_at` (naive local time, as the session files'),
        naming the session key, title, preview and model preset."""
        data, problem = self._load_object(artifact, ".webui_session_index.json")
        if data is None:
            yield from [problem] if problem else []
            return
        entries = data.get("sessions")
        if not isinstance(entries, list):
            yield self._file_row(
                artifact, "", "parser: .webui_session_index.json has no sessions list"
            )
            return
        errors: list = []
        for i, entry in enumerate(entries, 1):
            if not isinstance(entry, dict):
                errors.append(
                    (0, "unparseable record %d (not a JSON object)" % i, compact_json(entry))
                )
                continue
            key = str(entry.get("key") or "")
            text = " ".join(
                part
                for part in (
                    "webui sidebar entry: key=%s" % key,
                    "title=%s" % entry["title"] if entry.get("title") else "",
                    "preview=%s" % entry["preview"] if entry.get("preview") else "",
                    "model_preset=%s" % entry["model_preset"] if entry.get("model_preset") else "",
                    "updated_at=%s" % entry["updated_at"] if entry.get("updated_at") else "",
                    "(from .webui_session_index.json version %s)" % data.get("version", ""),
                )
                if part
            )
            yield self._setting_row(artifact, to_utc(entry.get("created_at")), text, key)
        yield from error_rows(self, artifact, errors)

    def _parse_run(self, artifact: Artifact) -> Iterator[Row]:
        """A cron or trigger run record: the prompt as the session stored it
        (`user`), the reply (`assistant`) and a `system` row with the run's
        status; see the module docstring."""
        match = RUN_RX.match(artifact.rel)
        assert match is not None  # parse() routes only matching paths here
        kind = match.group("kind")
        project = ""
        if match.group("ws") or artifact.home.project:
            original_match = ORIGINAL_RUN_RX.match(artifact.original or "")
            project = original_match.group(1) if original_match else ""
        record, problem = self._load_object(artifact, "%s run record" % kind)
        if record is None:
            if problem:
                problem.project_path = project
                yield problem
            return
        session_id = str(record.get("session_key") or "")
        end = to_utc(record.get("updated_at_ms"))

        def make_row(timestamp: str, turn_type: str, text: str) -> Row:
            row = self._setting_row(artifact, timestamp, text, session_id)
            row.turn_type = turn_type
            row.project_path = project
            return row

        if kind == "cron":
            prompt_vars = record.get("prompt_vars")
            message = prompt_vars.get("message") if isinstance(prompt_vars, dict) else None
            if record.get("job_name") and isinstance(message, str):
                prompt = "Scheduled cron job triggered: %s\n\n%s" % (record["job_name"], message)
            else:
                prompt = str(record.get("rendered_prompt") or "")
            # `run_id` is `<job id>:<epoch ms at the run's start>:<hex>`.
            parts = str(record.get("run_id") or "").rsplit(":", 2)
            start = to_utc(int(parts[1])) if len(parts) == 3 and parts[1].isdigit() else end
            status = "cron run: job %s (%s) run %s status=%s" % (
                record.get("job_name") or "",
                record.get("job_id") or "",
                record.get("run_id") or "",
                record.get("status") or "",
            )
        else:
            label = str(record.get("trigger_name") or "").strip() or str(
                record.get("trigger_id") or ""
            )
            prompt = "Local trigger received: %s\n\n%s" % (label, record.get("content") or "")
            start = to_utc(record.get("created_at_ms")) or end
            status = "trigger run: trigger %s (%s) delivery %s status=%s attempts=%s" % (
                record.get("trigger_name") or "",
                record.get("trigger_id") or "",
                record.get("delivery_id") or record.get("run_id") or "",
                record.get("status") or "",
                record.get("attempts", ""),
            )
        if prompt.strip():
            yield make_row(start, "user", prompt)
        if isinstance(record.get("response"), str) and record["response"]:
            yield make_row(end, "assistant", record["response"])
        error = record.get("error") or record.get("last_error")
        yield make_row(end, "system", status + (" error=%s" % error if error else ""))

    def _parse_cli_history(self, artifact: Artifact) -> Iterator[Row]:
        errors: list = []
        for line_number, timestamp, text in read_input_history(artifact.disk_path, errors):
            row = self.base_row(artifact)
            row.source_line = line_number
            row.timestamp_utc = to_utc(timestamp)
            row.turn_type = "user"
            row.text = compact(text)
            yield row
        yield from error_rows(self, artifact, errors)


__all__ = ["NanobotParser", "decode_stem"]
