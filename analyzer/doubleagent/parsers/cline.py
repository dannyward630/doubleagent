"""Cline transcripts, legacy task layout and SDK sessions.

Validated against source (cline/cline at 39ff2359, see
`research/cline.md`) with a synthetic fixture; no real install.

Legacy task layout, under the VS Code extension's
`<editor>/User/globalStorage/saoudrizwan.claude-dev/` or `~/.cline/data/`
(CLI and JetBrains): `tasks/<taskId>/ui_messages.json`,
`api_conversation_history.json` and `task_metadata.json` are read by the
shared mapping in `cline_legacy.py`, whose docstring lists the fields. The
task id is a `Date.now()` millisecond string, which is also the session
timestamp that API history records (which carry no timestamp of their own)
inherit when `ui_messages.json` is missing. The API history stays a
fallback, not a secondary source: it records a turn in other words than
`ui_messages.json` (the first prompt wrapped in `<task>` tags, tool calls
as content blocks or XML), so `dedup.deduplicate` could not pair the two
(the Parser plan of the research document).

* `state/taskHistory.json`: JSON array of `HistoryItem {id, ts, task,
  tokensIn, tokensOut, cacheWrites, cacheReads, totalCost, size,
  cwdOnTaskInitialization, modelId, apiProvider}`. One `system` row per
  task, kept because it survives deletion of the task directory; it is also
  where the task's project path and fallback model come from. Older VS Code
  builds kept this list in the editor's `state.vscdb`, which is not read.

SDK session layout, `~/.cline/data/sessions/<sessionId>/`:

* `<sessionId>.json` manifest: `session_id, source, pid, started_at,
  ended_at, exit_code, status, interactive, provider, model, cwd,
  workspace_root, prompt, metadata.title`. A `system` row for the start,
  then `model: <model> provider=<provider>` when the manifest names a
  model, and, when `ended_at` is set, one row for the end.
* `<sessionId>.messages.json` and subagent `<agentId>[__<teamTaskId>]
  .messages.json`: `{version, updated_at, agent, sessionId, messages:
  [{id, role, content, modelInfo: {id, provider}, metrics, ts}]}` with
  Anthropic-style content blocks (`text`, `tool_use {id, name, input}`,
  `tool_result {tool_use_id, name, content, is_error}`, `thinking`,
  `redacted_thinking`, `image`, `file {path}`). One row per block;
  `ts` is epoch milliseconds; a message without one takes the previous
  message's time, or for the first message the manifest `started_at` and
  then the file's `updated_at`. `session_id` is the session directory
  name, so subagent rows group with their lead session; `project_path` and
  the fallback model come from the manifest beside it. A message whose
  `modelInfo.id` differs from the model before it yields `model: <old> ->
  <new> provider=<modelInfo.provider>` ahead of its rows; the lead
  transcript starts from the manifest `model`, so its first message yields
  `model: <id>` only when the manifest names none, and a subagent
  transcript starts from its own first `modelInfo.id`.
* `~/.cline/data/db/sessions.db`, table `sessions` (`session_id, source,
  started_at, ended_at, status, provider, model, cwd, workspace_root,
  prompt, parent_session_id, is_subagent`): a `system` row, followed by
  `model: <model> provider=<provider>`, only for a session whose manifest
  is not on disk, so deleted sessions still show.
* Sync: the manifest's `metadata` key `enterprise.blobUpload` (one key with
  a dot in its name; the same object in the `sessions.db` column
  `metadata_json`), `{version, storage: {adapterType, bucket, region?,
  endpoint?, accountId?}, userDistinctId?}`, written at session start when
  an enterprise organisation's remote config turns on prompt uploading;
  every rewrite of `<sessionId>.messages.json` is then PUT to the object
  `sessions/<userDistinctId or unknown>/<sessionId>/messages.json` of that
  S3, R2 or Azure bucket (`sdk/packages/shared/src/remote-config/
  blob-storage.ts:56-57`, `129-160`, `367-414` at 39ff2359). One `system`
  row after the session start (or `model:`) row, at the manifest's
  `started_at`: `session synced: enterprise prompt upload to <adapterType>
  bucket <bucket> object sessions/<userDistinctId or
  unknown>/<session_id>/messages.json endpoint=<endpoint or -> region=<region
  or -> account=<accountId or -> (from <session_id>.json metadata
  enterprise.blobUpload, started_at)`; from the `sessions.db` row of a
  session whose manifest is gone, the same text ending `(from sessions.db
  sessions.metadata_json enterprise.blobUpload, started_at)`. A key that is
  not an object yields no row. Fixture only: no real install has shown the
  key. The legacy task layout records no sync.
* `~/.cline/data/db/session-search.db`, a secondary source (issue 122):
  the full-text index the SDK hub server keeps of each session's lead
  transcript, tables `indexed_sessions (session_id, source_revision,
  indexed_at, document_count, index_version, title)` and the FTS5 (SQLite
  full-text search) table `session_search (session_id, document_id,
  ordinal, role, started_at, workspace_root, title, content)`. Per session
  one document `<sessionId>:metadata`, `ordinal` -1 and `role` `session`,
  holds the title and the session's `prompt`; then one document per
  `<sessionId>.messages.json` message with any text, `ordinal` its 0-based
  position in that file, `role` the message's (`unknown` when it has
  none), and `content` every string value of the message's `content`
  (block type names, tool ids and tool input included; `data`, `image`,
  `images`, `reasoning`, `thinking` and `metadata` values left out) joined
  with line breaks and capped at 128 KiB. Rows: one `system` row per
  session, `session search index: title=... workspace_root=... prompt=...
  document_count=... indexed_at=...`, at the session's `started_at`; then
  one row per message document in `ordinal` order, `user` or `assistant`
  by `role` (`system` for any other), with an empty `timestamp_utc`, since
  the index records no time per message, so `dedup.deduplicate` matches
  them on text and session alone. `source_line` is `ordinal + 1`, the
  message's position in the transcript (0 when the ordinal is not a
  number). `session_id` is the index's, the SDK session id the manifest
  and messages rows carry; `project_path` is the manifest's `cwd` (else
  `workspace_root`) when the manifest is on disk, as the messages reader
  takes it, else the document's `workspace_root`. A message whose
  `content` is a plain string (a prompt with no attached image or file)
  pairs with its transcript row; a block array's text keeps the block type
  names and tool ids, so it never equals a transcript row and is kept. The
  hub reconciles the index at start and every five minutes while it runs:
  it drops a session that has left `sessions.db` and re-indexes one whose
  messages file changed or is gone, so the index outlives a deleted
  transcript only until the hub next runs. When the SQLite build lacks
  FTS5, one `system` row says so and only `indexed_sessions` is read, each
  session row then without a time.

* `~/.cline/data/cache/user_input_history.jsonl`, a secondary source
  (issue 122): the CLI's prompt history for up-arrow recall, one JSON line
  `{prompt, ts}` per prompt submitted in the terminal UI, trimmed, oldest
  first, each prompt kept once (a repeat moves to the end) and the last 20
  kept. No session id and no project are recorded. The CLI rewrites the
  whole file on every prompt and stamps every line with that write's
  `Date.now()`, so only the last line's `ts` (epoch milliseconds) is its
  own prompt's time. Rows: one `user` row per line, `source_line` the
  line; the last line has its `ts`, the others an empty `timestamp_utc`,
  and every line is undated when the file has a bad line, since the last
  parsed line may then not be the newest. Undated rows match a
  transcript row of any Cline session on text alone. Each bad line is its
  own `system` row carrying the line in full (issue 136).

* Sync, second source: the VS Code extension's enterprise prompt upload
  queue `<editor>/User/globalStorage/saoudrizwan.claude-dev/cache/sync-queue.json`
  (`apps/vscode/src/shared/services/worker/sync.ts:27-29` at 39ff2359),
  `{items: {<taskId>/<key>: {id, taskId, key, data, timestamp, status,
  retryCount, lastError}}}`, `timestamp` epoch ms of the enqueue and
  `status` `pending`, `synced` or `failed` (`queue.ts:9-31`, `157-170`);
  `data` is the task file's content and is never read into a row, nor is
  `lastError`. One `system` row per item, `source_line` its position in
  `items`, `session_id` the `taskId`, `project_path` the task's
  `cwdOnTaskInitialization` from the `state/taskHistory.json` beside it
  when there is one, at the item's `timestamp`: for a `synced` item
  `session synced: enterprise prompt upload synced key <key> retries
  <retryCount> (from saoudrizwan.claude-dev/cache/sync-queue.json, item
  timestamp)`, and for any other status (`pending`, `failed`) the same
  text without the `session synced: ` prefix, `enterprise prompt upload
  <status> key ...`, since that file has not reached the bucket; `-` for
  a value absent or empty. A file that is not a JSON object, or has no
  `items` object, is one `parser:` row, and so is an item that is not an
  object. Fixture only: no real install has shown the file.

The items below are source-derived (cline/cline at 41e75efc, research
document's Parser plan); not observed on any real install.

* Permission decisions, SDK messages: a call the runtime did not run ends
  in a `tool_result` block with `is_error` true and `content` the JSON
  string `{"error": <reason>}` (`sdk/packages/agents/src/
  agent-runtime.ts:2469-2512`, `sdk/packages/core/src/session/
  persisted-tool-result-content.ts:9-24`). A reason ending
  ` -- NOT a tool or system failure. Clarify with user before proceeding.`
  (`TOOL_REJECTION_SUFFIX`, every approval that came back not approved:
  the user's rejection, a denied edit, a follow-up message, a timeout, a
  missing approval callback) yields `permission decision: rejected
  reason=<reason without the suffix>`; the fixed `Tool "<name>" is
  disabled by policy` and `Tool <name> was blocked by a runtime hook`
  yield `permission decision: blocked reason=<reason>`. The `system` row
  follows the `tool_result` row it governs, with its `tool_use_id`,
  `tool_name`, time and model. A hook's own skip reason matches neither
  and yields no row; an approved call leaves no mark.
* Standing permission settings, one `system` row per value or list entry,
  `permission setting: <key>=<value> (from <rel>, file mtime)` at the
  file's modification time, `session_id` and `project_path` empty:
  `~/.cline/data/globalState.json` `autoApprovalSettings` (`enabled`,
  `maxRequests`, each `favorites` entry, each `actions.<name>`) and
  `mode`; `~/.cline/data/settings/global-settings.json` `toolAutoApprove`,
  `planActMode`, each `disabledTools`, `disabledPlugins` and
  `disabledAgentPlugins` entry, and `tools.<name>.enabled`; each
  `mcpServers.<name>` of `settings/cline_mcp_settings.json` (under
  `~/.cline/data` or the extension's globalStorage) as
  `mcpServers.<name>.autoApprove=<tool>` per entry and
  `mcpServers.<name>.disabled=<bool>`. No other key of these files is read
  (globalState.json holds much else; the MCP file can carry `env`,
  `headers` and OAuth state). A file that is not a JSON object is one
  `parser:` row.
* Origin and sync, Cline Cloud: `globalState.json` `cloudSessionStatuses`
  `{<ses- id>: {status, observedAt}}` yields per session, at `observedAt`
  (epoch ms) with `session_id` the id, `session origin: remote cline-cloud
  session <id> status <status> (from .cline/data/globalState.json
  cloudSessionStatuses, observedAt)` and `session synced: cline-cloud
  holds session <id>, no local transcript (from ... cloudSessionStatuses,
  observedAt)`. Each `{sessionId, account, endpoint}` record of
  `~/.cline/data/cloud-pending-starts/<pid>-<uuid>.json` yields the same
  pair, the origin row reading `sandbox start pending account=<account>
  endpoint=<endpoint>` in place of the status, at the file's modification
  time and ending `(from <rel>, file mtime)`; a file that is not a JSON
  array is one `parser:` row, a record without a `sessionId` one row per
  record. `cloudTaskTarget {target, repositoryId, branch}` yields one
  `cloud task target: target=<target> repository_id=<id> branch=<branch>
  (from .cline/data/globalState.json, file mtime)` row; the repository id
  is GitHub's. `records_origin` is set.
* Imported sessions: `metadata.importedFrom {tool, sourceSessionId,
  sourcePath, importedAt, sourceProvider, sourceModel}` of the manifest
  (or the `sessions.db` `metadata_json`) is named on the session start
  row as `imported_from=`, `imported_session=`, `imported_path=`,
  `imported_at=`, `imported_provider=` and `imported_model=`, so a copy of
  another agent's transcript is not read as Cline's own work.
* `~/.cline/data/logs/hooks.jsonl`, a secondary source: the SDK's hook
  audit log, one JSON line per event, `{ts (ISO 8601), hookName,
  clineVersion, timestamp, taskId, sessionContext.rootSessionId,
  workspaceRoots, userId, agent_id, parent_agent_id, ...}`
  (`sdk/packages/core/src/hooks/hook-file-hooks.ts:234-254`, `629-756`),
  appended only and never rotated. `session_id` is `rootSessionId` (else
  `taskId`, else `sessionId`), the SDK session directory name the
  messages reader uses; `project_path` the first `workspaceRoots` entry.
  `prompt_submit` (`userPromptSubmit.prompt`) is a `user` row;
  `tool_call` (`tool_call {id, name, input}`) a `tool_use` row with the
  tool's summary as the transcript writes it; `tool_result`
  (`tool_result {id, name, input, output, error}`, `postToolUse.result`)
  a `tool_result` row, `[error] <error>` when the call failed; both carry
  the call id, so `dedup.deduplicate` pairs them with the transcript's
  rows on it. `agent_end` (`turn.outputText`) is an `assistant` row.
  Every other line (`agent_start`, `agent_abort`, `agent_error`,
  `session_shutdown`, appended by the session store as `{ts, hookName,
  reason, sessionId, pid, source}`) is a `system` row `hook audit:
  <hookName>` followed by `cline_version=`, `user=`, `agent=`,
  `parent_agent=`, `reason=`, `pid=` and `source=` when present and
  `error=<name>: <message>` for `agent_error` (never the stack). The
  window is an hour (`secondary_tolerance`), since a call line is stamped
  when the call starts or ends and the transcript message when the turn
  is persisted. Each bad line is its own `system` row.

Not read: `<sessionId>.compaction.json`, `sessions/sessions.index.json`
and `teams/teams.db`.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

from ..inputs import Artifact
from ..model import Row, compact
from ..sqlite_util import is_sqlite, open_copy, table_names
from ..timeutil import to_utc
from .base import (
    Options,
    compact_json,
    error_rows,
    file_mtime,
    iter_jsonl,
    setting_value,
    text_of,
    track_change,
)
from .claude_code import tool_summary
from .cline_legacy import (
    LegacyTaskParser,
    content_rows,
    iter_array_at,
    iter_json_array,
    load_json,
    read_text,
)

ROOT = r"(?:(?:.*/)?User/globalStorage/saoudrizwan\.claude-dev|\.cline/data)"
STATE_RX = re.compile(r"^%s/state/taskHistory\.json$" % ROOT, re.I)
MANIFEST_RX = re.compile(r"^\.cline/data/sessions/([^/]+)/\1\.json$")
MESSAGES_RX = re.compile(r"^\.cline/data/sessions/[^/]+/[^/]+\.messages\.json$")
SESSIONS_DB_REL = ".cline/data/db/sessions.db"
SYNC_QUEUE_RX = re.compile(
    r"^(?:.*/)?User/globalStorage/saoudrizwan\.claude-dev/cache/sync-queue\.json$", re.I
)
SEARCH_DB_REL = ".cline/data/db/session-search.db"
INPUT_HISTORY_REL = ".cline/data/cache/user_input_history.jsonl"
SEARCH_COLUMNS = (
    "session_id, document_id, ordinal, role, started_at, workspace_root, title, content"
)
BLOB_UPLOAD_KEY = "enterprise.blobUpload"
SEARCH_KEYS = ("title", "workspace_root", "prompt", "document_count", "indexed_at")
MESSAGES_KEY_RX = re.compile(r'"messages"\s*:\s*(?=\[)')
HOOKS_REL = ".cline/data/logs/hooks.jsonl"
# A tool_call or tool_result line is written when the call starts or ends,
# the transcript's message when the whole turn is persisted, which can be a
# long command later; the call id pairs them, so the wide window is safe.
HOOKS_TOLERANCE_SECONDS = 3600.0
GLOBAL_STATE_REL = ".cline/data/globalState.json"
GLOBAL_SETTINGS_REL = ".cline/data/settings/global-settings.json"
MCP_SETTINGS_RX = re.compile(r"^%s/settings/cline_mcp_settings\.json$" % ROOT, re.I)
PENDING_START_RX = re.compile(r"^\.cline/data/cloud-pending-starts/\d+-[0-9a-f-]+\.json$")
# The runtime appends this to every rejected approval's reason
# (sdk/packages/shared/src/llms/tools.ts:104-105, agent-runtime.ts:2490).
REJECTION_SUFFIX = " -- NOT a tool or system failure. Clarify with user before proceeding."
# The two fixed reasons of a call the runtime skips without asking
# (sdk/packages/agents/src/agent-runtime.ts:2469, 2481).
BLOCKED_RX = re.compile(
    r'^(?:Tool "[^"\n]*" is disabled by policy|Tool [^\n]* was blocked by a runtime hook)$'
)
# Hook audit keys named on a `hook audit:` row, with the name the row uses.
HOOK_KEYS = (
    ("clineVersion", "cline_version"),
    ("userId", "user"),
    ("agent_id", "agent"),
    ("parent_agent_id", "parent_agent"),
    ("reason", "reason"),
    ("pid", "pid"),
    ("source", "source"),
)
# metadata.importedFrom keys named on the session start row.
IMPORTED_KEYS = (
    ("tool", "imported_from"),
    ("sourceSessionId", "imported_session"),
    ("sourcePath", "imported_path"),
    ("importedAt", "imported_at"),
    ("sourceProvider", "imported_provider"),
    ("sourceModel", "imported_model"),
)


class ClineParser(LegacyTaskParser):
    agent = "cline"
    # `enterprise.blobUpload` in a session's metadata marks an uploaded transcript.
    records_sync = True
    # Cline Cloud sessions listed in globalState.json or a pending-start file.
    records_origin = True
    name = "cline"
    has_secondary = True
    ROOT = ROOT
    PROJECT_KEY = "cwdOnTaskInitialization"

    def wants(self, artifact: Artifact) -> bool:
        rel = artifact.rel
        return bool(
            self.task_match(artifact)
            or STATE_RX.match(rel)
            or MANIFEST_RX.match(rel)
            or MESSAGES_RX.match(rel)
            or SYNC_QUEUE_RX.match(rel)
            or MCP_SETTINGS_RX.match(rel)
            or PENDING_START_RX.match(rel)
        ) or rel in (
            SESSIONS_DB_REL,
            SEARCH_DB_REL,
            INPUT_HISTORY_REL,
            HOOKS_REL,
            GLOBAL_STATE_REL,
            GLOBAL_SETTINGS_REL,
        )

    def secondary(self, artifact: Artifact) -> bool:
        return artifact.rel in (SEARCH_DB_REL, INPUT_HISTORY_REL, HOOKS_REL)

    def secondary_tolerance(self, artifact: Artifact) -> float:
        """An hour for `logs/hooks.jsonl` (`HOOKS_TOLERANCE_SECONDS`): its
        call lines are stamped when a call starts or ends, the transcript's
        message when the turn is persisted."""
        if artifact.rel == HOOKS_REL:
            return HOOKS_TOLERANCE_SECONDS
        return super().secondary_tolerance(artifact)

    def history_item(self, task_dir: Path, root: Path, task_id: str) -> dict | None:
        items = self.cached_json(root / "state" / "taskHistory.json")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and str(item.get("id")) == task_id:
                    return item
        return None

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        rel = artifact.rel
        if self.task_match(artifact):
            yield from self.parse_task_file(artifact, opts)
        elif STATE_RX.match(rel):
            yield from self._parse_task_history(artifact, opts)
        elif MANIFEST_RX.match(rel):
            yield from self._parse_manifest(artifact, opts)
        elif MESSAGES_RX.match(rel):
            yield from self._parse_messages(artifact, opts)
        elif rel == SESSIONS_DB_REL:
            yield from self._parse_sessions_db(artifact, opts)
        elif rel == SEARCH_DB_REL:
            yield from self._parse_search_db(artifact)
        elif rel == INPUT_HISTORY_REL:
            yield from self._parse_input_history(artifact)
        elif SYNC_QUEUE_RX.match(rel):
            yield from self._parse_sync_queue(artifact)
        elif rel == HOOKS_REL:
            yield from self._parse_hooks_log(artifact)
        elif rel == GLOBAL_STATE_REL:
            yield from self._parse_global_state(artifact)
        elif rel == GLOBAL_SETTINGS_REL:
            yield from self._parse_global_settings(artifact)
        elif MCP_SETTINGS_RX.match(rel):
            yield from self._parse_mcp_settings(artifact)
        elif PENDING_START_RX.match(rel):
            yield from self._parse_pending_starts(artifact)

    # -- cache/sync-queue.json (VS Code extension)

    def _parse_sync_queue(self, artifact: Artifact) -> Iterator[Row]:
        """One `enterprise prompt upload <status>` row per queued task file,
        prefixed `session synced: ` only when the item's status is `synced`;
        `data` and `lastError` are never read into a row."""
        doc = load_json(artifact.disk_path)
        items = doc.get("items") if isinstance(doc, dict) else None
        if not isinstance(items, dict):
            message = "sync-queue.json is not a JSON object with an items object"
            yield from error_rows(self, artifact, [(0, message, "")])
            return
        root = artifact.disk_path.parent.parent
        errors: list = []
        for position, (key, item) in enumerate(items.items(), 1):
            if not isinstance(item, dict):
                errors.append((position, "sync-queue item %s is not a JSON object" % key, ""))
                continue

            def value(k: str, item: dict = item) -> str:
                found = item.get(k)
                return str(found) if found not in (None, "") else "-"

            task_id = str(item.get("taskId") or "")
            history = self.history_item(root, root, task_id) if task_id else None
            row = self.base_row(artifact)
            row.source_line = position
            row.turn_type = "system"
            row.session_id = task_id
            row.project_path = str((history or {}).get(self.PROJECT_KEY) or "")
            row.timestamp_utc = to_utc(item.get("timestamp"))
            row.text = (
                "enterprise prompt upload %s key %s retries %s"
                " (from saoudrizwan.claude-dev/cache/sync-queue.json, item timestamp)"
                % (value("status"), value("key"), value("retryCount"))
            )
            if item.get("status") == "synced":
                row.text = "session synced: " + row.text
            yield row
        yield from error_rows(self, artifact, errors)

    def _parse_task_history(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        errors: list = []
        for position, item in iter_json_array(artifact.disk_path, errors):
            if isinstance(item, dict):
                yield self.history_row(artifact, item, position, opts)
        yield from error_rows(self, artifact, errors)

    # -- SDK sessions

    def _session_start(
        self,
        session: dict,
        artifact: Artifact,
        position: int,
        opts: Options,
        time_key: str,
        label: str,
        keys,
    ) -> Row:
        row = self.base_row(artifact)
        row.source_line = position
        row.timestamp_utc = to_utc(session.get(time_key))
        row.session_id = str(session.get("session_id") or "")
        row.project_path = str(session.get("cwd") or session.get("workspace_root") or "")
        row.model = str(session.get("model") or "")
        row.turn_type = "system"
        detail = " ".join(
            "%s=%s" % (k, session[k]) for k in keys if session.get(k) not in (None, "")
        )
        row.text = compact("%s: %s" % (label, detail))
        return row

    def _model_start(self, start: Row, session: dict) -> Iterator[Row]:
        """`model: <model> provider=<provider>` after a session start or index
        row, with its time, session and project."""
        model = str(session.get("model") or "")
        if not model:
            return
        provider = str(session.get("provider") or "")
        yield replace(
            start,
            model=model,
            text=compact("model: %s%s" % (model, " provider=%s" % provider if provider else "")),
        )

    def _blob_upload(self, start: Row, meta, source: str) -> Iterator[Row]:
        """The `session synced:` row of an `enterprise.blobUpload` metadata
        key, with the start row's time, session and project; nothing when
        `meta` has no such object."""
        blob = meta.get(BLOB_UPLOAD_KEY) if isinstance(meta, dict) else None
        if not isinstance(blob, dict):
            return
        storage = blob.get("storage")
        storage = storage if isinstance(storage, dict) else {}

        def value(key: str, default: str = "-") -> str:
            found = storage.get(key)
            return str(found) if found not in (None, "") else default

        user = blob.get("userDistinctId")
        text = (
            "session synced: enterprise prompt upload to %s bucket %s object"
            " sessions/%s/%s/messages.json endpoint=%s region=%s account=%s"
            " (from %s %s, started_at)"
            % (
                value("adapterType"),
                value("bucket"),
                user if user not in (None, "") else "unknown",
                start.session_id,
                value("endpoint"),
                value("region"),
                value("accountId"),
                source,
                BLOB_UPLOAD_KEY,
            )
        )
        yield replace(start, text=text)

    START_KEYS = (
        "source",
        "provider",
        "status",
        "interactive",
        "pid",
        "parent_session_id",
        "is_subagent",
        "title",
        "prompt",
        *(name for _, name in IMPORTED_KEYS),
    )
    END_KEYS = ("status", "exit_code")

    def _parse_manifest(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        manifest = load_json(artifact.disk_path)
        if not isinstance(manifest, dict):
            yield from error_rows(
                self,
                artifact,
                [(0, "session manifest is not a JSON object", "")],
                artifact.disk_path.parent.name,
            )
            return
        manifest = dict(manifest)
        manifest.setdefault("session_id", artifact.disk_path.parent.name)
        meta = manifest.get("metadata")
        if isinstance(meta, dict) and meta.get("title"):
            manifest["title"] = meta["title"]
        _imported(manifest, meta)
        start = self._session_start(
            manifest, artifact, 0, opts, "started_at", "session start", self.START_KEYS
        )
        yield start
        yield from self._model_start(start, manifest)
        yield from self._blob_upload(start, meta, artifact.disk_path.name + " metadata")
        if manifest.get("ended_at"):
            yield self._session_start(
                manifest, artifact, 0, opts, "ended_at", "session end", self.END_KEYS
            )

    def _parse_messages(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        session_id = artifact.disk_path.parent.name
        manifest = load_json(artifact.disk_path.parent / (session_id + ".json"))
        manifest = manifest if isinstance(manifest, dict) else {}
        project = str(manifest.get("cwd") or manifest.get("workspace_root") or "")
        raw_text = read_text(artifact.disk_path)
        errors: list = []
        payload = None
        if raw_text is None:
            errors.append((0, "unreadable", ""))
        else:
            try:
                payload = json.loads(raw_text)
            except ValueError:
                payload = None
        if isinstance(payload, dict):
            messages = enumerate(payload.get("messages") or [], 1)
            fallback = to_utc(manifest.get("started_at")) or to_utc(payload.get("updated_at"))
        elif raw_text is not None:
            # Cut mid-write: walk the messages array as far as it parses.
            match = MESSAGES_KEY_RX.search(raw_text)
            if match:
                messages = iter_array_at(raw_text, match.end(), errors)
            else:
                errors.append((0, "messages file is not a JSON object", ""))
                messages = iter(())
            fallback = to_utc(manifest.get("started_at"))
        else:
            messages = iter(())
            fallback = ""
        # The lead transcript continues from the manifest's model, whose start
        # row the manifest yields; a subagent transcript tracks its own.
        seen: dict = {}
        if artifact.disk_path.name == session_id + ".messages.json" and manifest.get("model"):
            seen[session_id] = str(manifest["model"])
        for position, message in messages:
            if not isinstance(message, dict):
                continue
            timestamp = to_utc(message.get("ts")) or fallback
            fallback = timestamp
            info = message.get("modelInfo")
            info = info if isinstance(info, dict) else {}
            model = str(info.get("id") or manifest.get("model") or "")
            change = track_change("model", seen, session_id, str(info.get("id") or ""))
            if change:
                row = self.base_row(artifact)
                row.source_line = position
                row.timestamp_utc = timestamp
                row.session_id = session_id
                row.project_path = project
                row.model = model
                row.turn_type = "system"
                provider = str(info.get("provider") or "")
                row.text = compact(change + (" provider=%s" % provider if provider else ""))
                yield row
            role = message.get("role")
            base_turn = (
                "user" if role == "user" else "assistant" if role == "assistant" else "system"
            )
            decisions = _decisions(message.get("content"))
            for turn, text, name, tool_id in content_rows(
                message.get("content"), base_turn, opts.include_thinking
            ):
                row = self.base_row(artifact)
                row.source_line = position
                row.timestamp_utc = timestamp
                row.session_id = session_id
                row.project_path = project
                row.model = model
                row.turn_type = turn
                row.tool_name = name
                row.tool_use_id = tool_id
                row.text = compact(text)
                yield row
                if turn == "tool_result" and tool_id in decisions:
                    yield replace(row, turn_type="system", text=decisions.pop(tool_id))
        yield from error_rows(self, artifact, errors, session_id, project)

    def _parse_sessions_db(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        if not is_sqlite(artifact.disk_path):
            yield from error_rows(self, artifact, [(0, "sessions.db is not a SQLite database", "")])
            return
        sessions_dir = artifact.disk_path.parent.parent / "sessions"
        try:
            with open_copy(artifact.disk_path) as connection:
                if "sessions" not in table_names(connection):
                    return
                rows = [
                    dict(db_row)
                    for db_row in connection.execute("select rowid as _rowid, * from sessions")
                ]
        except Exception as error:  # noqa: BLE001 - a damaged database must not stop the timeline
            yield from error_rows(self, artifact, [(0, "sessions.db unreadable (%s)" % error, "")])
            return
        for session in rows:
            session_id = str(session.get("session_id") or "")
            if session_id and (sessions_dir / session_id / (session_id + ".json")).is_file():
                continue
            meta = (
                load_json_text(session["metadata_json"]) if session.get("metadata_json") else None
            )
            if isinstance(meta, dict) and meta.get("title"):
                session["title"] = meta["title"]
            _imported(session, meta)
            start = self._session_start(
                session,
                artifact,
                int(session.get("_rowid") or 0),
                opts,
                "started_at",
                "session index",
                (*self.START_KEYS, "ended_at", "exit_code"),
            )
            yield start
            yield from self._model_start(start, session)
            yield from self._blob_upload(start, meta, "sessions.db sessions.metadata_json")

    # -- logs/hooks.jsonl (secondary)

    def _parse_hooks_log(self, artifact: Artifact) -> Iterator[Row]:
        """One row per hook audit line: `prompt_submit` a `user` row,
        `tool_call` a `tool_use` row, `tool_result` a `tool_result` row (both
        with the call id), `agent_end` an `assistant` row with the final
        reply, and every other line a `hook audit: <hookName> ...` row."""
        errors: list = []
        for line_number, record in iter_jsonl(artifact.disk_path, errors):
            session_context = _obj(record.get("sessionContext"))
            roots = record.get("workspaceRoots")
            row = self.base_row(artifact)
            row.source_line = line_number
            row.timestamp_utc = to_utc(record.get("ts") or record.get("timestamp"))
            row.session_id = str(
                session_context.get("rootSessionId")
                or record.get("taskId")
                or record.get("sessionId")
                or ""
            )
            if isinstance(roots, list) and roots and isinstance(roots[0], str):
                row.project_path = roots[0]
            hook = str(record.get("hookName") or "")
            if not _hook_event(row, hook, record):
                detail = "".join(
                    " %s=%s" % (name, setting_value(record[key]))
                    for key, name in HOOK_KEYS
                    if record.get(key) not in (None, "")
                )
                error = _obj(record.get("error"))
                if error:
                    detail += " error=%s: %s" % (
                        _dash(error.get("name")),
                        _dash(error.get("message")),
                    )
                row.turn_type = "system"
                row.text = compact("hook audit: %s%s" % (hook or "-", detail))
            yield row
        yield from error_rows(self, artifact, errors)

    # -- standing settings and Cline Cloud state

    def _settings_row(self, artifact: Artifact, timestamp: str, key: str, value) -> Row:
        row = self.base_row(artifact)
        row.source_line = 1
        row.turn_type = "system"
        row.timestamp_utc = timestamp
        row.text = compact(
            "permission setting: %s=%s (from %s, file mtime)"
            % (key, setting_value(value), artifact.rel)
        )
        return row

    def _json_object(self, artifact: Artifact, what: str) -> tuple[dict | None, list]:
        """The file as a JSON object, or None with the whole-file error."""
        doc = load_json(artifact.disk_path)
        if isinstance(doc, dict):
            return doc, []
        return None, [(0, "%s is not a JSON object" % what, "")]

    def _parse_global_state(self, artifact: Artifact) -> Iterator[Row]:
        """`autoApprovalSettings` and `mode` as `permission setting:` rows,
        `cloudTaskTarget` as one `cloud task target:` row, and each
        `cloudSessionStatuses` entry as `session origin:` and `session
        synced:` rows. No other key is read."""
        doc, errors = self._json_object(artifact, "globalState.json")
        if doc is None:
            yield from error_rows(self, artifact, errors)
            return
        timestamp = file_mtime(artifact)
        auto = _obj(doc.get("autoApprovalSettings"))
        for key in ("enabled", "maxRequests"):
            if key in auto:
                yield self._settings_row(
                    artifact, timestamp, "autoApprovalSettings." + key, auto[key]
                )
        favorites = auto.get("favorites")
        for entry in favorites if isinstance(favorites, list) else []:
            yield self._settings_row(artifact, timestamp, "autoApprovalSettings.favorites", entry)
        for key, value in _obj(auto.get("actions")).items():
            yield self._settings_row(
                artifact, timestamp, "autoApprovalSettings.actions." + key, value
            )
        if doc.get("mode") not in (None, ""):
            yield self._settings_row(artifact, timestamp, "mode", doc["mode"])
        target = doc.get("cloudTaskTarget")
        if isinstance(target, dict):
            row = self.base_row(artifact)
            row.source_line = 1
            row.turn_type = "system"
            row.timestamp_utc = timestamp
            row.text = "cloud task target: target=%s repository_id=%s branch=%s (from %s, %s)" % (
                _dash(target.get("target")),
                _dash(target.get("repositoryId")),
                _dash(target.get("branch")),
                artifact.rel,
                "file mtime",
            )
            yield row
        source = "%s cloudSessionStatuses, observedAt" % artifact.rel
        for session_id, status in _obj(doc.get("cloudSessionStatuses")).items():
            status = _obj(status)
            yield from self._cloud_rows(
                artifact,
                str(session_id),
                to_utc(status.get("observedAt")),
                "status %s" % _dash(status.get("status")),
                source,
            )

    def _cloud_rows(
        self, artifact: Artifact, session_id: str, timestamp: str, detail: str, source: str
    ) -> Iterator[Row]:
        """The `session origin:` and `session synced:` rows of one Cline
        Cloud session, whose transcript is on the vendor's servers."""
        row = self.base_row(artifact)
        row.turn_type = "system"
        row.timestamp_utc = timestamp
        row.session_id = session_id
        row.text = "session origin: remote cline-cloud session %s %s (from %s)" % (
            session_id,
            detail,
            source,
        )
        yield row
        yield replace(
            row,
            text="session synced: cline-cloud holds session %s, no local transcript (from %s)"
            % (session_id, source),
        )

    def _parse_pending_starts(self, artifact: Artifact) -> Iterator[Row]:
        """One pair of Cline Cloud rows per `{sessionId, account, endpoint}`
        record, at the file's modification time."""
        doc = load_json(artifact.disk_path)
        if not isinstance(doc, list):
            message = "cloud pending-start file is not a JSON array"
            yield from error_rows(self, artifact, [(0, message, "")])
            return
        timestamp = file_mtime(artifact)
        errors: list = []
        for position, record in enumerate(doc, 1):
            if not isinstance(record, dict) or not isinstance(record.get("sessionId"), str):
                errors.append((position, "pending-start record %d has no sessionId" % position, ""))
                continue
            detail = "sandbox start pending account=%s endpoint=%s" % (
                _dash(record.get("account")),
                _dash(record.get("endpoint")),
            )
            source = "%s, file mtime" % artifact.rel
            for row in self._cloud_rows(artifact, record["sessionId"], timestamp, detail, source):
                row.source_line = position
                yield row
        yield from error_rows(self, artifact, errors)

    def _parse_global_settings(self, artifact: Artifact) -> Iterator[Row]:
        """The CLI and SDK's standing tool settings, one `permission
        setting:` row per value or list entry."""
        doc, errors = self._json_object(artifact, "global-settings.json")
        if doc is None:
            yield from error_rows(self, artifact, errors)
            return
        timestamp = file_mtime(artifact)
        for key in ("toolAutoApprove", "planActMode"):
            if doc.get(key) not in (None, ""):
                yield self._settings_row(artifact, timestamp, key, doc[key])
        for key in ("disabledTools", "disabledPlugins", "disabledAgentPlugins"):
            entries = doc.get(key)
            for entry in entries if isinstance(entries, list) else []:
                yield self._settings_row(artifact, timestamp, key, entry)
        for name, tool in _obj(doc.get("tools")).items():
            tool = _obj(tool)
            if "enabled" in tool:
                yield self._settings_row(
                    artifact, timestamp, "tools.%s.enabled" % name, tool["enabled"]
                )

    def _parse_mcp_settings(self, artifact: Artifact) -> Iterator[Row]:
        """Each MCP server's `autoApprove` entries and `disabled` flag; the
        server's command, `env`, `headers` and OAuth state are never read."""
        doc, errors = self._json_object(artifact, "cline_mcp_settings.json")
        if doc is None:
            yield from error_rows(self, artifact, errors)
            return
        timestamp = file_mtime(artifact)
        for name, server in _obj(doc.get("mcpServers")).items():
            server = _obj(server)
            entries = server.get("autoApprove")
            for entry in entries if isinstance(entries, list) else []:
                key = "mcpServers.%s.autoApprove" % name
                yield self._settings_row(artifact, timestamp, key, entry)
            if isinstance(server.get("disabled"), bool):
                key = "mcpServers.%s.disabled" % name
                yield self._settings_row(artifact, timestamp, key, server["disabled"])

    # -- cache/user_input_history.jsonl

    def _parse_input_history(self, artifact: Artifact) -> Iterator[Row]:
        errors: list = []
        entries = [
            (entry_line, record["prompt"], record.get("ts"))
            for entry_line, record in iter_jsonl(artifact.disk_path, errors)
            if isinstance(record.get("prompt"), str) and record["prompt"].strip()
        ]
        for k, (line_number, prompt, timestamp) in enumerate(entries):
            row = self.base_row(artifact)
            row.source_line = line_number
            row.turn_type = "user"
            # Every line carries the time of the file's last rewrite, the
            # newest prompt's own time only; a bad line makes that unsure.
            if k == len(entries) - 1 and not errors and isinstance(timestamp, (int, float)):
                row.timestamp_utc = to_utc(timestamp)
            row.text = compact(prompt)
            yield row
        yield from error_rows(self, artifact, errors)

    # -- session-search.db

    def _parse_search_db(self, artifact: Artifact) -> Iterator[Row]:
        if not is_sqlite(artifact.disk_path):
            yield from error_rows(
                self, artifact, [(0, "session-search.db is not a SQLite database", "")]
            )
            return
        problem = ""
        try:
            with open_copy(artifact.disk_path) as connection:
                tables = table_names(connection)
                indexed = []
                if "indexed_sessions" in tables:
                    indexed = [
                        dict(db_row)
                        for db_row in connection.execute(
                            "select * from indexed_sessions order by rowid"
                        )
                    ]
                docs = []
                if "session_search" in tables:
                    try:
                        docs = [
                            dict(db_row)
                            for db_row in connection.execute(
                                "select %s from session_search order by rowid" % SEARCH_COLUMNS
                            )
                        ]
                    except sqlite3.OperationalError as error:
                        problem = (
                            "session_search unreadable (%s), indexed_sessions read alone" % error
                        )
        except Exception as error:  # noqa: BLE001 - a damaged database must not stop the timeline
            yield from error_rows(
                self, artifact, [(0, "session-search.db unreadable (%s)" % error, "")]
            )
            return
        if problem:
            yield from error_rows(self, artifact, [(0, problem, "")])
        by_session: dict[str, list[dict]] = {}
        for indexed_session in indexed:
            by_session.setdefault(str(indexed_session.get("session_id") or ""), [])
        for document in docs:
            by_session.setdefault(str(document.get("session_id") or ""), []).append(document)
        meta = {str(entry.get("session_id") or ""): entry for entry in indexed}
        sessions_dir = artifact.disk_path.parent.parent / "sessions"
        for session_id, session_docs in by_session.items():
            yield from self._search_session(
                artifact, session_id, meta.get(session_id, {}), session_docs, sessions_dir
            )

    def _search_session(
        self, artifact: Artifact, session_id: str, indexed: dict, docs: list, sessions_dir: Path
    ) -> Iterator[Row]:
        """The index's rows for one session: the session row, then one row
        per message document in transcript order."""
        head = next((candidate for candidate in docs if candidate.get("role") == "session"), None)
        docs = sorted(
            (candidate for candidate in docs if candidate.get("role") != "session"),
            key=lambda candidate: _ordinal(candidate.get("ordinal")),
        )
        workspace = str((head or (docs[0] if docs else {})).get("workspace_root") or "")
        manifest = (
            load_json(sessions_dir / session_id / (session_id + ".json")) if session_id else None
        )
        if isinstance(manifest, dict):
            project = str(manifest.get("cwd") or manifest.get("workspace_root") or "")
        else:
            project = workspace
        fields = {
            "title": indexed.get("title") or (head or {}).get("title"),
            "workspace_root": workspace,
            "prompt": (head or {}).get("content"),
            "document_count": indexed.get("document_count"),
            "indexed_at": indexed.get("indexed_at"),
        }
        row = self.base_row(artifact)
        row.timestamp_utc = to_utc((head or (docs[0] if docs else {})).get("started_at"))
        row.session_id = session_id
        row.project_path = project
        row.turn_type = "system"
        detail = " ".join(
            "%s=%s" % (k, fields[k]) for k in SEARCH_KEYS if fields[k] not in (None, "")
        )
        row.text = compact("session search index: %s" % detail)
        yield row
        for document in docs:
            role = document.get("role")
            row = self.base_row(artifact)
            row.source_line = _ordinal(document.get("ordinal")) + 1
            row.session_id = session_id
            row.project_path = project
            row.turn_type = role if role in ("user", "assistant") else "system"
            row.text = compact(document.get("content"))
            yield row


def _ordinal(value) -> int:
    """A message document's `ordinal`, -1 when it is not a number."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def load_json_text(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _obj(value) -> dict:
    """`value` when it is a JSON object, else an empty one."""
    return value if isinstance(value, dict) else {}


def _dash(value) -> str:
    """A value for row text, `-` when absent or empty."""
    return "-" if value in (None, "") else str(value)


def _imported(session: dict, meta) -> None:
    """Copy `metadata.importedFrom` onto the session record under the
    `imported_*` names the start row prints."""
    source = _obj(_obj(meta).get("importedFrom"))
    for key, name in IMPORTED_KEYS:
        if source.get(key) not in (None, ""):
            session[name] = source[key]


def _denial(content) -> str:
    """The `permission decision:` text of a skipped call's tool_result
    content (`{"error": <reason>}`, stored as a JSON string), or `""`."""
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            return ""
    reason = _obj(content).get("error")
    if not isinstance(reason, str):
        return ""
    if reason.endswith(REJECTION_SUFFIX):
        return "permission decision: rejected reason=%s" % reason[: -len(REJECTION_SUFFIX)]
    if BLOCKED_RX.match(reason):
        return "permission decision: blocked reason=%s" % reason
    return ""


def _decisions(content) -> dict:
    """tool_use_id -> `permission decision:` text for each errored
    tool_result block of a message whose reason is a rejection or a block."""
    out: dict = {}
    for block in content if isinstance(content, list) else []:
        block = _obj(block)
        if block.get("type") == "tool_result" and block.get("is_error"):
            text = _denial(block.get("content"))
            if text:
                out[str(block.get("tool_use_id") or "")] = compact(text)
    return out


def _hook_event(row: Row, hook: str, entry: dict) -> bool:
    """Fill `row` as the transcript event a hook audit line repeats, and
    say whether it is one."""
    if hook == "prompt_submit":
        prompt = _obj(entry.get("userPromptSubmit")).get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return False
        row.turn_type, row.text = "user", compact(prompt)
    elif hook == "tool_call":
        call = _obj(entry.get("tool_call"))
        row.turn_type = "tool_use"
        row.tool_name = str(call.get("name") or "")
        row.tool_use_id = str(call.get("id") or "")
        row.text = compact(tool_summary(row.tool_name, call.get("input")))
    elif hook == "tool_result":
        record = _obj(entry.get("tool_result"))
        post = _obj(entry.get("postToolUse"))
        row.turn_type = "tool_result"
        row.tool_name = str(record.get("name") or post.get("toolName") or "")
        row.tool_use_id = str(record.get("id") or "")
        if record.get("error"):
            row.text = compact("[error] %s" % record["error"])
        elif isinstance(post.get("result"), str):
            row.text = compact(post["result"])
        else:
            output = record.get("output")
            row.text = compact(
                text_of(output) if isinstance(output, (str, list)) else compact_json(output)
            )
    elif hook == "agent_end":
        text = _obj(entry.get("turn")).get("outputText")
        if not isinstance(text, str) or not text.strip():
            return False
        row.turn_type, row.text = "assistant", compact(text)
    else:
        return False
    return True
