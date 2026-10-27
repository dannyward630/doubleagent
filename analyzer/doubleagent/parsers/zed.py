"""Zed agent panel threads.

Validated against source, zed-industries/zed at a84689073d29 and, for
the settings, `db.sqlite` stores, denials, scratch directories and drafts,
at 9cd14daad768 (see `research/zed.md`), with a synthetic fixture; no real
install was checked, and every row the 9cd14daad768 review added is
source-derived, not observed on any real install. Files, relative to the
Zed data directory (`.local/share/zed`, `Library/Application Support/Zed`,
`AppData/Local/Zed`, or the Flatpak `.var/app/dev.zed.Zed*/data/zed`), and
to the config directory (`.config/zed`, `AppData/Roaming/Zed`, or
`.var/app/dev.zed.Zed*/config/zed`):

* `threads/threads.db` (rollback journal, so a `-journal` may sit beside it):
  table `threads(id, summary, updated_at, data_type, data, parent_id,
  folder_paths, folder_paths_order, created_at)`. `id` is the session id,
  `folder_paths` the project paths joined by newlines, `updated_at` and
  `created_at` RFC 3339. `data` is zstd-compressed JSON when `data_type` is
  `zstd` (decoded with the `zstandard` package) and raw UTF-8 JSON when
  `json`.
  The thread JSON, `version` `0.3.0`: `title`, `updated_at`,
  `initial_project_snapshot.timestamp`,
  `initial_project_snapshot.worktree_snapshots[].worktree_path`,
  `.git_state.current_branch` and `.git_state.remote_url`, `model.provider`, `model.model`,
  `subagent_context.parent_thread_id`, and `messages[]`, externally tagged:
  - `{"User": {"id", "content": [{"Text"}, {"Mention": {"uri"}}, {"Image"}]}}`
  - `{"Agent": {"content": [{"Text"}, {"Thinking": {"text"}},
    {"RedactedThinking"}, {"ToolUse": {"id", "name", "raw_input",
    "input"}}], "tool_results": {<id>: {"tool_use_id", "tool_name",
    "is_error", "content": [{"Text"}]}}}}`
  - `"Resume"`, `{"Compaction": {"Summary"}}` or
    `{"Compaction": {"ProviderNative"}}`.
  Versions `0.1.0` and `0.2.0` (`messages[].role`, `segments[]` with
  `type` text/thinking/RedactedThinking, `tool_uses[]`, `tool_results[]`)
  and the unversioned legacy shape (`messages[].role`, `.text`) are read
  on a best-effort basis; their role spelling was not confirmed.
  The blob's `sandboxed_terminal_temp_dir` (macOS only) is a
  `scratch directory: <path> (sandboxed terminal temp directory of thread
  <id>) (thread blob, as of updated_at)` row after the grant rows, with the
  path as `project_path` and no `session_id`, so the thread stays counted
  under its project; its `draft_prompt` (a list of ACP `ContentBlock`s,
  `type` `text`, `resource_link`, `resource`, `image`, `audio`) is an
  `unsent draft: <text> (thread blob, as of updated_at)` row after the
  messages.
* `db/0-<channel>/db.sqlite` (WAL), all `system` rows:
  - table `sidebar_threads(thread_id, session_id, agent_id, title,
    title_override, updated_at, interacted_at, folder_paths, archived,
    main_worktree_paths)`. A row with `agent_id` set is an external ACP agent
    thread whose transcript is not in `threads.db`: `external agent thread
    (no transcript in threads.db): agent=<id> title=<title>[ archived]` at
    `interacted_at`, else `updated_at`. A native row (`agent_id` NULL) with a
    `session_id` is the thread's sidebar state: `sidebar thread:
    title=<title> archived=<true|false> interacted_at=<time|-> main_worktree=
    <path|->` at `updated_at`, with the thread id. It is not a secondary
    source: it repeats no event of `threads.db` and is deleted with the
    thread. A native row with no `session_id` is a draft and has no row of
    its own.
  - table `trusted_worktrees(absolute_path, user_name, host_name)`:
    `permission setting: trusted_worktrees.<path>=true[ host=<user>@<host>]
    (from <file> trusted_worktrees, file mtime)`, `project_path` the path.
  - table `scoped_kv_store(namespace, key, value)`, namespace
    `agent_draft_prompts` (key the hyphenated `sidebar_threads.thread_id`,
    value a JSON array of ACP `ContentBlock`s): `unsent draft: <text>` at
    the draft's sidebar `updated_at`, `project_path` its first folder, or
    with ` (from <file> agent_draft_prompts, file mtime)` at the file's
    modification time when the sidebar row is gone; namespace
    `created_git_worktrees` (key `<host>` newline `<worktree path>`, `local`
    for this machine, value `{created_at_seconds, created_at_subsec_nanos}`):
    `scratch directory: <path> (Zed-created git worktree[ of <main>][
    host=<host>]) (from <file> created_git_worktrees, created_at)` at that
    time, `project_path` the worktree, `<main>` the
    `sidebar_threads.main_worktree_paths` of a thread whose `folder_paths`
    holds the worktree, else the `archived_git_worktrees.main_repo_path`.
  - tables `archived_git_worktrees(id, worktree_path, main_repo_path,
    branch_name, staged_commit_hash, unstaged_commit_hash,
    original_commit_hash)` and `thread_archived_worktrees(thread_id,
    archived_worktree_id)`: `archived worktree: <worktree_path> of
    <main_repo_path> branch=<b> staged=<hash> unstaged=<hash>
    original=<hash> ref=refs/archived-worktrees/<id> (from <file>
    archived_git_worktrees, file mtime)`, one per linked thread with its
    `session_id`, `project_path` the main repository; the archive time is not
    recorded.
  - table `sidebar_terminal_threads(title, custom_title, created_at,
    working_directory, folder_paths)`: `sidebar terminal: <title> cwd=<dir>`
    at `created_at`, `project_path` the first folder, no `session_id`.
  A value in `scoped_kv_store` that does not decode is `parser: unparseable
  record <rowid> (<namespace ...>: <reason>): <value>` at the end of the file.
* `settings.json` and `global_settings.json` in the config directory (JSONC,
  read with `parse_jsonc`): one `permission setting: <key>=<value> (from
  <file>, file mtime)` row per leaf of `agent.tool_permissions` (`default`,
  `tools.<tool>.default`, one per `always_allow`, `always_deny` and
  `always_confirm` entry `{pattern, case_sensitive}` as compact JSON) and of
  `agent.sandbox_permissions` (one per `network_hosts` and `write_paths`
  entry), and per `agent.always_allow_tool_actions` (the legacy boolean),
  `agent_servers.<id>.default_mode` and `session.trust_all_worktrees`, in
  the top level and in each `dev`, `nightly`, `preview`, `stable`, `macos`,
  `linux`, `windows` and `profiles.<name>.settings` block, whose name
  prefixes the key. A project's `.zed/settings.json` cannot hold these keys
  (it parses as `ProjectSettingsContent`) and is not read. A file that is
  not a JSON object is one `parser: <file> is not a JSON object` row.

There are no per-message timestamps. Every message row carries the thread's
`updated_at` (approximate: it is the last write, not the message time); the
thread-start row carries `initial_project_snapshot.timestamp`, falling back
to `created_at`. `source_line` is the SQLite `rowid` of the thread or
sidebar row. The git branch is the one captured at thread start, and so
is the remote: the `git_state.remote_url` of the snapshot whose
`worktree_path` is the thread's project (else of the first snapshot, as
for the branch) is a `system` row `git remote: <url>` at the thread-start
time, right after the thread-start row (issue 253).

Model and permission rows (issues 96 and 97), all `system`, after the
thread-start row and before the first message:

* `model: <model.model> provider=<model.provider>` once per thread, at the
  thread-start time. The blob holds one `model` per thread, so a switch
  inside a thread is not recorded and there is no change row.
* `permission setting: <key>=<value> (thread blob, as of updated_at)`, one
  row per entry of `profile`, `sandbox_grants.write_paths[]` (a path string,
  or an object in newer blobs, printed as compact JSON) and
  `sandbox_grants.network_hosts[]`, and one per `sandbox_grants` flag
  `network_any_host`, `allow_fs_write_all`, `unsandboxed` and
  `sandbox_fallback` that is `true`. These are the grants the user gave
  "for the rest of this thread", stored in the blob, so the row carries the
  thread id as `session_id` and the thread's `updated_at` as its time (the
  last write, not the moment of the grant, which is not recorded).

Per-call decisions: a failed tool result (`is_error` true) whose text is
`Permission to run tool denied by user` is followed by `permission
decision: denied`, and one whose text is a rule's automatic denial
(`Blocked by global default: deny`, `Command blocked by security rule for
<tool> tool`, `<tool> tool is disabled`, `Blocked by built-in security
rule. ...`, the invalid-terminal-command, invalid-regex and
unsupported-shell messages) by `permission decision: auto_denied
reason=<text>`, each with the call's `tool_name` and `tool_use_id`. An
approval, once or always, leaves no record in the thread, so it has no row;
an "always" choice shows only as the settings rows above.

Bad files and records (issues 136 and 168). A file that is not SQLite is
one `parser: not a SQLite database` row, and a SQLite error while reading
one `parser: SQLite error: <error>` row. Inside `threads.db`, each record
that does not decode is a `system` row with an empty `timestamp_utc`, the
thread's `session_id` and `project_path`, and `source_line` the `threads`
rowid:

* A `data` blob that does not decode to a JSON object is
  `parser: unparseable record <rowid> (<reason>): <stored value>`, the
  stored value being a `json` row's text, or a `zstd` row's compressed
  bytes as lowercase hex (a truncated frame can decompress to nothing, so
  the bytes are what is carried), its reason then ending `stored zstd
  blob as hex`.
* A `messages[]` item of no known variant (not `User`, `Agent`,
  `Compaction` with `Summary` or `ProviderNative`, a string or a legacy
  `role` message), an `Agent` content item of no known variant, a content
  or `segments[]` item that is not an object, or a `tool_uses[]` or
  `tool_results` entry that is not an object is
  `parser: unparseable record <N> (<reason>): <item as JSON>`, N the
  message's 1-based position in `messages[]` and the reason naming the
  item's place inside it. These rows follow the thread's other rows. An
  unknown `User` content object stays in the prompt text as JSON, as
  before.
"""

from __future__ import annotations

import io
import json
import re
import sqlite3
import uuid
from collections.abc import Iterator

import zstandard

from ..inputs import Artifact
from ..model import GIT_REMOTE_PREFIX, Row, compact
from ..sqlite_util import is_sqlite, open_copy, table_names
from ..timeutil import to_utc
from .base import Options, Parser, compact_json, error_rows, file_mtime, setting_value
from .gemini_cli import parse_jsonc

DATA_DIR = r"(?:\.local/share/zed|Library/Application Support/Zed|AppData/Local/Zed|\.var/app/dev\.zed\.Zed[A-Za-z]*/data/zed)"
SANDBOX_FLAGS = ("network_any_host", "allow_fs_write_all", "unsandboxed", "sandbox_fallback")
CONFIG_DIR = r"(?:\.config/zed|AppData/Roaming/Zed|\.var/app/dev\.zed\.Zed[A-Za-z]*/config/zed)"
THREADS_RX = re.compile(r"^" + DATA_DIR + r"/threads/threads\.db$")
SIDEBAR_RX = re.compile(r"^" + DATA_DIR + r"/db/0-[^/]+/db\.sqlite$")
SETTINGS_RX = re.compile(r"^" + CONFIG_DIR + r"/(?:global_)?settings\.json$")
# Release-channel and platform override blocks of a user settings file
# (`ReleaseChannelOverrides`, `PlatformOverrides`), each a whole settings
# object of its own.
SETTINGS_OVERRIDES = ("dev", "nightly", "preview", "stable", "macos", "linux", "windows")
USER_DENIAL = "Permission to run tool denied by user"
# The texts `ToolPermissionDecision::Deny` carries when the rules deny a
# call with no prompt (crates/agent/src/tool_permissions.rs at 9cd14da).
AUTO_DENIAL_RX = re.compile(
    r"(?:Blocked by global default: deny"
    r"|Command blocked by security rule for \S+ tool"
    r"|\S+ tool is disabled"
    r"|Blocked by built-in security rule\..*"
    r"|The terminal command could not be approved because .*"
    r"|The \S+ tool cannot run because \d+ regex patterns? failed to compile\..*"
    r'|The .+ shell does not support "always allow" patterns .*)',
    re.S,
)


def decompress(blob: bytes) -> bytes:
    dctx = zstandard.ZstdDecompressor()
    try:
        return dctx.decompress(blob)
    except zstandard.ZstdError:
        # No content size in the frame header: stream it instead.
        out = io.BytesIO()
        with dctx.stream_reader(io.BytesIO(blob)) as reader:
            while True:
                chunk = reader.read(65536)
                if not chunk:
                    break
                out.write(chunk)
        return out.getvalue()


def record_json(value) -> str:
    """A decoded blob item as error row text: compact JSON in the blob's own
    key order, non-ASCII kept, so the item is carried in full."""
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def content_text(content) -> str:
    """Text of a tool result `content`: a list of `{"Text": ...}` /
    `{"Image": ...}` items, a single such item, or a plain string."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        content = [content]
    if not isinstance(content, list):
        return compact_json(content)
    parts = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            if isinstance(item.get("Text"), str):
                parts.append(item["Text"])
            elif "Image" in item:
                parts.append("[image]")
            elif isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                parts.append(compact_json(item))
    return "\n".join(parts)


def mention_text(mention) -> str:
    if not isinstance(mention, dict):
        return "[mention]"
    uri = mention.get("uri")
    return "[mention] " + (uri if isinstance(uri, str) else compact_json(uri))


def tool_input_text(tool_use: dict) -> str:
    inp = tool_use.get("input")
    if isinstance(inp, dict) and set(inp) <= {"type", "value"} and "value" in inp:
        inp = inp["value"]
    if inp not in (None, "", {}):
        return inp if isinstance(inp, str) else compact_json(inp)
    raw = tool_use.get("raw_input")
    return raw if isinstance(raw, str) else ""


def first_folder(folder_paths) -> str:
    if not isinstance(folder_paths, str):
        return ""
    for path in folder_paths.split("\n"):
        if path.strip():
            return path
    return ""


def acp_blocks_text(blocks) -> str:
    """Text of a list of ACP `ContentBlock`s (`{"type": "text", "text"}`,
    `resource_link` and `resource` by URI, `image` and `audio` as markers),
    as a draft prompt stores them; another block is compact JSON."""
    if isinstance(blocks, dict):
        blocks = [blocks]
    if not isinstance(blocks, list):
        return compact_json(blocks)
    parts = []
    for block in blocks:
        kind = block.get("type") if isinstance(block, dict) else None
        if isinstance(block, str):
            parts.append(block)
        elif kind == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
        elif kind == "resource_link" and isinstance(block.get("uri"), str):
            parts.append("[mention] " + block["uri"])
        elif kind == "resource" and isinstance(block.get("resource"), dict):
            uri = block["resource"].get("uri")
            parts.append("[mention] " + (uri if isinstance(uri, str) else compact_json(uri)))
        elif kind in ("image", "audio"):
            parts.append("[%s]" % kind)
        else:
            parts.append(compact_json(block))
    return "\n".join(parts)


def denial_text(res: dict) -> str:
    """The `permission decision:` row text for a failed tool result whose
    text is one Zed writes when a call is denied, else "". An approval
    leaves no record, so only denials have a row."""
    if not res.get("is_error"):
        return ""
    text = content_text(res.get("content")).strip()
    if text == USER_DENIAL:
        return "permission decision: denied"
    if AUTO_DENIAL_RX.fullmatch(text):
        return "permission decision: auto_denied reason=" + text
    return ""


def thread_key(blob) -> str:
    """A `sidebar_threads.thread_id` (16 raw UUID bytes) as the hyphenated
    string the key-value store keys drafts by, else ""."""
    if isinstance(blob, (bytes, bytearray)) and len(blob) == 16:
        return str(uuid.UUID(bytes=bytes(blob)))
    return str(blob or "")


def flatten_setting(key: str, value) -> Iterator[tuple[str, object]]:
    """(dotted key, value) per leaf of a settings value: one per object
    member, recursively, and one per list entry."""
    if isinstance(value, dict):
        for member, member_value in value.items():
            yield from flatten_setting("%s.%s" % (key, member), member_value)
    elif isinstance(value, list):
        for entry in value:
            yield key, entry
    else:
        yield key, value


class ZedParser(Parser):
    agent = "zed"
    name = "zed"

    def wants(self, artifact: Artifact) -> bool:
        rel = artifact.rel
        return bool(THREADS_RX.match(rel) or SIDEBAR_RX.match(rel) or SETTINGS_RX.match(rel))

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        if SETTINGS_RX.match(artifact.rel):
            yield from self._parse_settings(artifact)
            return
        if not is_sqlite(artifact.disk_path):
            yield self._file_error(artifact, "not a SQLite database")
            return
        try:
            if THREADS_RX.match(artifact.rel):
                yield from self._parse_threads(artifact, opts)
            else:
                yield from self._parse_sidebar(artifact)
        except sqlite3.DatabaseError as error:
            yield self._file_error(artifact, "SQLite error: %s" % error)

    def _file_error(self, artifact: Artifact, message: str) -> Row:
        """The one `parser: <message>` row for a file that cannot be read."""
        row = self.base_row(artifact)
        row.turn_type = "system"
        row.text = "parser: " + message
        return row

    def _state_row(
        self,
        artifact: Artifact,
        text: str,
        timestamp: str,
        source_line: int,
        session_id: str = "",
        project: str = "",
    ) -> Row:
        """A `system` row of `artifact` with the given text and context."""
        row = self.base_row(artifact)
        row.source_line = source_line
        row.session_id = session_id
        row.project_path = project
        row.timestamp_utc = timestamp
        row.turn_type = "system"
        row.text = compact(text)
        return row

    # -- settings.json, global_settings.json ----------------------------------------
    def _parse_settings(self, artifact: Artifact) -> Iterator[Row]:
        """One `permission setting:` row per standing permission entry of a
        user settings file, at the file's modification time."""
        try:
            raw = artifact.disk_path.read_bytes()
        except OSError as error:
            yield self._file_error(artifact, "unreadable: %s" % error)
            return
        if not raw.strip():
            return
        try:
            doc = parse_jsonc(raw)
        except ValueError:
            doc = None
        if not isinstance(doc, dict):
            yield self._file_error(artifact, "%s is not a JSON object" % artifact.rel)
            return
        timestamp = file_mtime(artifact)
        for key, value in self._settings_entries(doc):
            text = "permission setting: %s=%s (from %s, file mtime)" % (
                key,
                setting_value(value),
                artifact.rel,
            )
            yield self._state_row(artifact, text, timestamp, 1)

    @staticmethod
    def _settings_entries(doc: dict) -> Iterator[tuple[str, object]]:
        """(dotted key, value) per entry of `agent.tool_permissions`,
        `agent.sandbox_permissions`, the legacy
        `agent.always_allow_tool_actions`, `agent_servers.<id>.default_mode`
        and `session.trust_all_worktrees`, in the top level, each
        release-channel and platform override block and each
        `profiles.<name>.settings`, the key prefixed with the block's."""
        layers: list[tuple[str, dict]] = [("", doc)]
        for name in SETTINGS_OVERRIDES:
            if isinstance(doc.get(name), dict):
                layers.append((name + ".", doc[name]))
        profiles = doc.get("profiles")
        if isinstance(profiles, dict):
            for name, prof in profiles.items():
                if isinstance(prof, dict) and isinstance(prof.get("settings"), dict):
                    layers.append(("profiles.%s.settings." % name, prof["settings"]))
        for prefix, block in layers:
            agent = block.get("agent")
            if isinstance(agent, dict):
                for sub in ("tool_permissions", "sandbox_permissions"):
                    if sub in agent:
                        yield from flatten_setting(prefix + "agent." + sub, agent[sub])
                if "always_allow_tool_actions" in agent:
                    legacy = agent["always_allow_tool_actions"]
                    yield prefix + "agent.always_allow_tool_actions", legacy
            servers = block.get("agent_servers")
            if isinstance(servers, dict):
                for sid, cfg in servers.items():
                    if isinstance(cfg, dict) and "default_mode" in cfg:
                        yield prefix + "agent_servers.%s.default_mode" % sid, cfg["default_mode"]
            session = block.get("session")
            if isinstance(session, dict) and "trust_all_worktrees" in session:
                yield prefix + "session.trust_all_worktrees", session["trust_all_worktrees"]

    # -- db/0-<channel>/db.sqlite -------------------------------------------------
    def _parse_sidebar(self, artifact: Artifact) -> Iterator[Row]:
        errors: list = []
        with open_copy(artifact.disk_path) as con:
            tables = table_names(con)
            sidebar = self._select(
                con,
                tables,
                "sidebar_threads",
                "select rowid as _rowid, * from sidebar_threads order by updated_at",
            )
            trusted = self._select(
                con,
                tables,
                "trusted_worktrees",
                "select rowid as _rowid, * from trusted_worktrees order by rowid",
            )
            key_values = self._select(
                con,
                tables,
                "scoped_kv_store",
                "select rowid as _rowid, namespace, key, value"
                " from scoped_kv_store where namespace in ('agent_draft_prompts',"
                " 'created_git_worktrees') order by rowid",
            )
            link = "thread_archived_worktrees" in tables
            archived = self._select(
                con,
                tables,
                "archived_git_worktrees",
                "select a.rowid as _rowid, a.*, t.thread_id as _thread from"
                " archived_git_worktrees a left join thread_archived_worktrees t"
                " on t.archived_worktree_id = a.id order by a.id"
                if link
                else "select rowid as _rowid, *, null as _thread from archived_git_worktrees"
                " order by id",
            )
            terminals = self._select(
                con,
                tables,
                "sidebar_terminal_threads",
                "select rowid as _rowid, * from sidebar_terminal_threads order by created_at",
            )
        by_key = {thread_key(row.get("thread_id")): row for row in sidebar}
        for row in sidebar:
            yield from self._sidebar_row(artifact, row)
        for row in trusted:
            yield self._trusted_row(artifact, row)
        for row in key_values:
            if row["namespace"] == "agent_draft_prompts":
                yield from self._draft(artifact, row, by_key, errors)
            else:
                yield from self._created_worktree(artifact, row, sidebar, archived, errors)
        for row in archived:
            yield self._archived_worktree(artifact, row, by_key)
        for row in terminals:
            title = row.get("custom_title") or row.get("title") or ""
            text = "sidebar terminal: %s cwd=%s" % (title, row.get("working_directory") or "-")
            project = first_folder(row.get("folder_paths"))
            timestamp = to_utc(row.get("created_at"))
            yield self._state_row(artifact, text, timestamp, row["_rowid"], "", project)
        yield from error_rows(self, artifact, errors)

    @staticmethod
    def _select(con: sqlite3.Connection, tables: set, table: str, sql: str) -> list[dict]:
        """The rows of `sql` as dicts, or [] when `table` does not exist."""
        if table not in tables:
            return []
        return [dict(row) for row in con.execute(sql)]

    def _sidebar_row(self, artifact: Artifact, row: dict) -> Iterator[Row]:
        """An external agent's thread (no transcript in `threads.db`), or the
        sidebar state of a native thread; a draft (no `session_id`) has no
        row of its own, only its draft prompt."""
        title = row.get("title_override") or row.get("title") or ""
        project = first_folder(row.get("folder_paths"))
        session_id = str(row.get("session_id") or "")
        if row.get("agent_id"):
            text = "external agent thread (no transcript in threads.db): agent=%s title=%s%s" % (
                row["agent_id"],
                title,
                " archived" if row.get("archived") else "",
            )
            timestamp = to_utc(row.get("interacted_at") or row.get("updated_at"))
            yield self._state_row(artifact, text, timestamp, row["_rowid"], session_id, project)
        elif session_id:
            text = "sidebar thread: title=%s archived=%s interacted_at=%s main_worktree=%s" % (
                title,
                "true" if row.get("archived") else "false",
                to_utc(row.get("interacted_at")) or "-",
                first_folder(row.get("main_worktree_paths")) or "-",
            )
            timestamp = to_utc(row.get("updated_at"))
            yield self._state_row(artifact, text, timestamp, row["_rowid"], session_id, project)

    def _trusted_row(self, artifact: Artifact, row: dict) -> Row:
        """The `permission setting:` row of one trusted project path."""
        path = str(row.get("absolute_path") or "")
        host = str(row.get("host_name") or "")
        if host and row.get("user_name"):
            host = "%s@%s" % (row["user_name"], host)
        text = "permission setting: trusted_worktrees.%s=true%s (from %s trusted_worktrees," % (
            path,
            " host=%s" % host if host else "",
            artifact.rel,
        )
        timestamp = file_mtime(artifact)
        return self._state_row(artifact, text + " file mtime)", timestamp, row["_rowid"], "", path)

    def _draft(self, artifact: Artifact, row: dict, by_key: dict, errors: list) -> Iterator[Row]:
        """`unsent draft: <text>` for an `agent_draft_prompts` entry, at the
        draft's sidebar `updated_at`, or at the file's modification time,
        saying so, when the draft has no sidebar row."""
        rowid, key, value = row["_rowid"], str(row["key"]), row["value"]
        try:
            blocks = json.loads(value)
        except (TypeError, ValueError) as error:
            label = "unparseable record %d (agent_draft_prompts %s: %s: %s)" % (
                rowid,
                key,
                type(error).__name__,
                error,
            )
            errors.append((rowid, label, str(value)))
            return
        text = acp_blocks_text(blocks)
        if not text.strip():
            return
        side = by_key.get(key)
        if side is not None:
            timestamp = to_utc(side.get("updated_at"))
            project = first_folder(side.get("folder_paths"))
            yield self._state_row(artifact, "unsent draft: " + text, timestamp, rowid, "", project)
            return
        text = "unsent draft: %s (from %s agent_draft_prompts, file mtime)" % (text, artifact.rel)
        yield self._state_row(artifact, text, file_mtime(artifact), rowid)

    def _created_worktree(
        self, artifact: Artifact, row: dict, sidebar: list, archived: list, errors: list
    ) -> Iterator[Row]:
        """`scratch directory:` for a `created_git_worktrees` entry, at the
        worktree's recorded creation time, `project_path` the worktree, and
        the main repository from the sidebar or the archived worktrees."""
        rowid, value = row["_rowid"], row["value"]
        host, _, path = str(row["key"]).partition("\n")
        try:
            rec = json.loads(value)
            seconds = rec["created_at_seconds"] + rec.get("created_at_subsec_nanos", 0) / 1e9
        except (TypeError, ValueError, KeyError, AttributeError) as error:
            label = "unparseable record %d (created_git_worktrees: %s: %s)" % (
                rowid,
                type(error).__name__,
                error,
            )
            errors.append((rowid, label, str(value)))
            return
        main = next(
            (
                first_folder(entry.get("main_worktree_paths"))
                for entry in sidebar
                if entry.get("main_worktree_paths")
                and path in str(entry.get("folder_paths") or "").split("\n")
            ),
            "",
        ) or next(
            (
                str(archive["main_repo_path"])
                for archive in archived
                if archive["worktree_path"] == path
            ),
            "",
        )
        text = "scratch directory: %s (Zed-created git worktree%s%s) (from %s" % (
            path,
            " of %s" % main if main else "",
            " host=%s" % host if host and host != "local" else "",
            artifact.rel,
        )
        text += " created_git_worktrees, created_at)"
        yield self._state_row(artifact, text, to_utc(seconds), rowid, "", path)

    def _archived_worktree(self, artifact: Artifact, row: dict, by_key: dict) -> Row:
        """The row of one archived worktree and one thread linked to it."""
        side = by_key.get(thread_key(row.get("_thread"))) if row.get("_thread") else None
        session_id = str((side or {}).get("session_id") or "")
        text = (
            "archived worktree: %s of %s branch=%s staged=%s unstaged=%s original=%s"
            " ref=refs/archived-worktrees/%s (from %s archived_git_worktrees, file mtime)"
        ) % (
            row.get("worktree_path") or "",
            row.get("main_repo_path") or "",
            row.get("branch_name") or "-",
            row.get("staged_commit_hash") or "-",
            row.get("unstaged_commit_hash") or "-",
            row.get("original_commit_hash") or "-",
            row.get("id"),
            artifact.rel,
        )
        project = str(row.get("main_repo_path") or "")
        timestamp = file_mtime(artifact)
        return self._state_row(artifact, text, timestamp, row["_rowid"], session_id, project)

    # -- threads/threads.db -------------------------------------------------------
    def _parse_threads(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        with open_copy(artifact.disk_path) as con:
            if "threads" not in table_names(con):
                return
            for row in con.execute("select rowid as _rowid, * from threads order by updated_at"):
                yield from self._thread_rows(artifact, dict(row), opts)

    def _thread_rows(self, artifact: Artifact, record: dict, opts: Options) -> Iterator[Row]:
        session_id = str(record.get("id") or "")
        project = first_folder(record.get("folder_paths"))
        updated = to_utc(record.get("updated_at"))

        def base(
            turn_type: str, text: str, timestamp: str = "", model: str = "", branch: str = ""
        ) -> Row:
            row = self.base_row(artifact)
            row.source_line = record["_rowid"]
            row.session_id = session_id
            row.project_path = project
            row.git_branch = branch
            row.timestamp_utc = timestamp or updated
            row.model = model
            row.turn_type = turn_type
            row.text = compact(text)
            return row

        thread, err, raw = self._decode(record)
        if thread is None:
            label = "unparseable record %d (%s)" % (record["_rowid"], err)
            yield from error_rows(
                self, artifact, [(record["_rowid"], label, raw)], session_id, project
            )
            return

        snap = thread.get("initial_project_snapshot")
        if not isinstance(snap, dict):
            snap = {}
        worktrees = [
            worktree
            for worktree in (snap.get("worktree_snapshots") or [])
            if isinstance(worktree, dict)
        ]
        if not project and worktrees:
            project = str(worktrees[0].get("worktree_path") or "")
        branches = [
            (worktree.get("worktree_path") == project, str(worktree["git_state"]["current_branch"]))
            for worktree in worktrees
            if isinstance(worktree.get("git_state"), dict)
            and worktree["git_state"].get("current_branch")
        ]
        branch = max(branches, key=lambda pair: pair[0])[1] if branches else ""
        # The project's own snapshot, else the first one; never another
        # worktree's, whose remote is another repository's.
        own = [
            worktree for worktree in worktrees if worktree.get("worktree_path") == project
        ] or worktrees[:1]
        remote = ""
        if own and isinstance(own[0].get("git_state"), dict):
            url = own[0]["git_state"].get("remote_url")
            remote = url.strip() if isinstance(url, str) else ""
        model_info = thread.get("model")
        if not isinstance(model_info, dict):
            model_info = {}
        model = "/".join(
            str(part) for part in (model_info.get("provider"), model_info.get("model")) if part
        )
        if not updated:
            updated = to_utc(thread.get("updated_at"))

        parent = record.get("parent_id") or (
            (thread.get("subagent_context") or {}).get("parent_thread_id")
            if isinstance(thread.get("subagent_context"), dict)
            else ""
        )
        start_ts = to_utc(snap.get("timestamp")) or to_utc(record.get("created_at")) or updated
        yield base(
            "system",
            " ".join(
                part
                for part in (
                    "thread start:",
                    str(thread.get("title") or record.get("summary") or ""),
                    "version=%s" % thread["version"] if thread.get("version") else "",
                    "parent=%s" % parent if parent else "",
                )
                if part
            ),
            start_ts,
            model,
            branch,
        )
        if remote:
            yield base("system", GIT_REMOTE_PREFIX + remote, start_ts, model, branch)
        if model_info.get("model"):
            text = "model: %s" % model_info["model"]
            if model_info.get("provider"):
                text += " provider=%s" % model_info["provider"]
            yield base("system", text, start_ts, model, branch)
        for key, value in self._grants(thread):
            yield base(
                "system",
                "permission setting: %s=%s (thread blob, as of updated_at)"
                % (key, setting_value(value)),
                "",
                model,
                branch,
            )

        temp_dir = thread.get("sandboxed_terminal_temp_dir")
        if isinstance(temp_dir, str) and temp_dir:
            # Its own project_path and no session_id, so the thread stays
            # counted under its project.
            text = (
                "scratch directory: %s (sandboxed terminal temp directory of thread %s)"
                " (thread blob, as of updated_at)" % (temp_dir, session_id)
            )
            yield self._state_row(artifact, text, updated, record["_rowid"], "", temp_dir)

        errors: list = []
        for kind, text, tool_name, tool_id in self._messages(thread, record["_rowid"], errors):
            if kind == "thinking" and not opts.include_thinking:
                continue
            if not text and kind not in ("tool_use", "tool_result"):
                continue
            row = base(kind, text, "", model, branch)
            row.tool_name = tool_name
            row.tool_use_id = tool_id
            yield row
        draft = thread.get("draft_prompt")
        if draft:
            text = acp_blocks_text(draft)
            if text.strip():
                text = "unsent draft: %s (thread blob, as of updated_at)" % text
                yield base("system", text, "", model, branch)
        yield from error_rows(self, artifact, errors, session_id, project)

    @staticmethod
    def _grants(thread: dict) -> Iterator[tuple[str, object]]:
        """(dotted key, value) per thread-scoped grant: the agent profile,
        each granted write path and network host, and each sandbox escape
        flag that is set (`DbSandboxGrants`, db.rs:91-122 at a84689073d29)."""
        if thread.get("profile") not in (None, ""):
            yield "profile", thread["profile"]
        grants = thread.get("sandbox_grants")
        if not isinstance(grants, dict):
            return
        for key in ("write_paths", "network_hosts"):
            entries = grants.get(key)
            if isinstance(entries, list):
                for entry in entries:
                    yield "sandbox_grants.%s" % key, entry
        for key in SANDBOX_FLAGS:
            if grants.get(key) is True:
                yield "sandbox_grants.%s" % key, True

    @staticmethod
    def _decode(row: dict) -> tuple[dict | None, str, str]:
        """(thread, "", "") for a blob that decodes to a JSON object, else
        (None, reason, the stored value as text). A `json` row's stored
        value is its text, decoded UTF-8 with `errors="replace"`; a `zstd`
        row's is its compressed bytes as lowercase hex, since they have no
        faithful text form and a truncated frame can decompress to nothing,
        and its reason ends `stored zstd blob as hex`."""
        data = row.get("data")
        if data is None:
            return None, "no data", ""
        binary = isinstance(data, (bytes, bytearray))
        stored = bytes(data) if binary else str(data).encode("utf-8")
        is_zstd = str(row.get("data_type") or "").lower() == "zstd"
        try:
            raw = decompress(stored) if is_zstd else stored
            thread = json.loads(raw.decode("utf-8", errors="replace"))
            if not isinstance(thread, dict):
                raise ValueError("not a JSON object")
        except Exception as error:  # noqa: BLE001 - ZstdError, the stream reader's errors, ValueError
            if is_zstd:
                reason = "%s: %s; stored zstd blob as hex" % (type(error).__name__, error)
                return None, reason, stored.hex()
            return (
                None,
                "%s: %s" % (type(error).__name__, error),
                stored.decode("utf-8", errors="replace"),
            )
        return thread, "", ""

    def _messages(
        self, thread: dict, rowid: int, errors: list
    ) -> Iterator[tuple[str, str, str, str]]:
        """(turn_type, text, tool_name, tool_use_id) in transcript order. A
        `messages[]` item, or a content, segment, tool use or tool result
        item inside one, of a shape not recognised is appended to `errors`
        as (rowid, `unparseable record <N> (<reason>)`, the item as JSON),
        N the message's 1-based position in `messages[]`."""
        messages = thread.get("messages")
        if messages is None:
            return
        if not isinstance(messages, list):
            reason = "unparseable record 0 (messages is not a list)"
            errors.append((rowid, reason, record_json(messages)))
            return

        def bad(position: int, reason: str, item) -> None:
            errors.append(
                (rowid, "unparseable record %d (%s)" % (position, reason), record_json(item))
            )

        for position, msg in enumerate(messages, 1):
            if isinstance(msg, str):
                yield "system", msg.lower(), "", ""
            elif not isinstance(msg, dict):
                bad(position, "unknown message variant", msg)
            elif "User" in msg:
                yield from self._user(msg["User"], position, bad)
            elif "Agent" in msg:
                yield from self._agent(msg["Agent"], position, bad)
            elif "Compaction" in msg:
                compaction = msg["Compaction"]
                if isinstance(compaction, dict) and isinstance(compaction.get("Summary"), str):
                    yield "system", "compaction: " + compaction["Summary"], "", ""
                elif isinstance(compaction, dict) and "ProviderNative" in compaction:
                    yield "system", "compaction: provider native", "", ""
                else:
                    bad(position, "unknown Compaction variant", msg)
            elif "role" in msg:
                yield from self._legacy(msg, position, bad)
            else:
                bad(position, "unknown message variant", msg)

    @staticmethod
    def _user(user_message, position: int, bad) -> Iterator[tuple[str, str, str, str]]:
        # One row per prompt: text, mentions and images of one User message
        # are joined so sessions.jsonl counts prompts, not content items. A
        # content object of an unknown variant stays in the prompt text as
        # JSON; an item that is not an object or string goes to `bad`.
        if not isinstance(user_message, dict):
            bad(position, "User message is not an object", {"User": user_message})
            return
        content = user_message.get("content")
        if isinstance(content, (str, dict)):
            content = [content]
        elif content is not None and not isinstance(content, list):
            bad(position, "User content is not a list", content)
            content = []
        parts = []
        for k, item in enumerate(content or []):
            if isinstance(item, str):
                parts.append(item)
            elif not isinstance(item, dict):
                bad(position, "unknown User content variant, content[%d]" % k, item)
            else:
                if isinstance(item.get("Text"), str):
                    parts.append(item["Text"])
                elif "Mention" in item:
                    parts.append(mention_text(item["Mention"]))
                elif "Image" in item:
                    parts.append("[image]")
                else:
                    parts.append(compact_json(item))
        yield "user", "\n".join(parts), "", ""

    @staticmethod
    def _agent(agent_message, position: int, bad) -> Iterator[tuple[str, str, str, str]]:
        if not isinstance(agent_message, dict):
            bad(position, "Agent message is not an object", {"Agent": agent_message})
            return
        results = agent_message.get("tool_results")
        if results is not None and not isinstance(results, dict):
            bad(position, "Agent tool_results is not an object", results)
        if not isinstance(results, dict):
            results = {}
        done = set()

        def result(key, res: dict):
            text = content_text(res.get("content"))
            if not text and res.get("output") is not None:
                text = (
                    content_text(res["output"])
                    if not isinstance(res["output"], dict)
                    else compact_json(res["output"])
                )
            if res.get("is_error"):
                text = "[error] " + text
            name, tid = str(res.get("tool_name") or ""), str(res.get("tool_use_id") or key)
            yield "tool_result", text, name, tid
            decision = denial_text(res)
            if decision:
                yield "system", decision, name, tid

        content = agent_message.get("content")
        if isinstance(content, (str, dict)):
            content = [content]
        elif content is not None and not isinstance(content, list):
            bad(position, "Agent content is not a list", content)
            content = []
        for k, item in enumerate(content or []):
            if isinstance(item, str):
                yield "assistant", item, "", ""
            elif not isinstance(item, dict):
                bad(position, "unknown Agent content variant, content[%d]" % k, item)
            elif isinstance(item.get("Text"), str):
                yield "assistant", item["Text"], "", ""
            elif "Thinking" in item:
                thinking = item["Thinking"]
                yield (
                    "thinking",
                    (thinking.get("text") if isinstance(thinking, dict) else str(thinking)) or "",
                    "",
                    "",
                )
            elif "RedactedThinking" in item:
                yield "thinking", "[redacted thinking]", "", ""
            elif isinstance(item.get("ToolUse"), dict):
                tool_use = item["ToolUse"]
                tid = str(tool_use.get("id") or "")
                yield "tool_use", tool_input_text(tool_use), str(tool_use.get("name") or ""), tid
                # The result follows its call, so the timeline reads in order.
                if isinstance(results.get(tid), dict):
                    done.add(tid)
                    yield from result(tid, results[tid])
            elif "Image" in item:
                yield "assistant", "[image]", "", ""
            else:
                bad(position, "unknown Agent content variant, content[%d]" % k, item)
        for key, res in results.items():
            if key in done:
                continue
            if isinstance(res, dict):
                yield from result(key, res)
            else:
                bad(position, "Agent tool_results entry %s is not an object" % key, res)

    @staticmethod
    def _legacy(msg: dict, position: int, bad) -> Iterator[tuple[str, str, str, str]]:
        role = str(msg.get("role") or "").lower()
        kind = "user" if role == "user" else "assistant" if role == "assistant" else "system"
        if isinstance(msg.get("text"), str):
            yield kind, msg["text"] if kind != "system" else "%s: %s" % (role, msg["text"]), "", ""
        for k, seg in enumerate(msg.get("segments") or []):
            segment_type = str(seg.get("type") or "").lower() if isinstance(seg, dict) else ""
            if segment_type == "text":
                yield kind, str(seg.get("text") or ""), "", ""
            elif segment_type == "thinking":
                yield "thinking", str(seg.get("text") or ""), "", ""
            elif segment_type == "redactedthinking":
                yield "thinking", "[redacted thinking]", "", ""
            else:
                bad(position, "unknown segment variant, segments[%d]" % k, seg)
        for k, tool_use in enumerate(msg.get("tool_uses") or []):
            if not isinstance(tool_use, dict):
                bad(position, "tool_uses[%d] is not an object" % k, tool_use)
            else:
                yield (
                    "tool_use",
                    tool_input_text(tool_use),
                    str(tool_use.get("name") or ""),
                    str(tool_use.get("id") or ""),
                )
        for k, res in enumerate(msg.get("tool_results") or []):
            if not isinstance(res, dict):
                bad(position, "tool_results[%d] is not an object" % k, res)
            else:
                text = content_text(res.get("content"))
                if res.get("is_error"):
                    text = "[error] " + text
                tid = str(res.get("tool_use_id") or "")
                yield "tool_result", text, "", tid
                decision = denial_text(res)
                if decision:
                    yield "system", decision, "", tid


__all__ = [
    "ZedParser",
    "acp_blocks_text",
    "content_text",
    "decompress",
    "denial_text",
    "first_folder",
    "record_json",
    "tool_input_text",
]
