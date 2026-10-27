"""Roo Code transcripts.

Validated against source (RooCodeInc/Roo-Code at b867ec91, see
`research/roo-code.md`) with a synthetic fixture; no real install.

Roo Code forked Cline and keeps its per-task layout, so the transcript files
are read by the shared mapping in `cline_legacy.py`, whose docstring lists
the fields. Roots: the extension's
`<editor>/User/globalStorage/rooveterinaryinc.roo-cline/` and the CLI's
`~/.vscode-mock/global-storage/`. A root moved with the
`roo-cline.customStoragePath` setting is not found.

* `tasks/<taskId>/ui_messages.json`, `api_conversation_history.json` (or
  the pre-rename `claude_messages.json`) and `task_metadata.json`, as in
  Cline. Roo's differences: the task prompt is the first `say: "text"`
  record (there is no `say: "task"`), `condense_context` carries
  `contextCondense {summary, prevContextTokens, newContextTokens, cost}`,
  API history records carry their own `ts`, and `task_metadata.json` holds
  only `files_in_context` with `roo_read_date` and `roo_edit_date`. The task
  id is a UUID, so API history records without `ts` inherit the
  `HistoryItem.ts`.
* `tasks/<taskId>/history_item.json`: one `HistoryItem {id, ts, task,
  tokensIn, tokensOut, totalCost, size, workspace, mode, status,
  apiConfigName, parentTaskId, rootTaskId}`. One `system` row; `workspace`
  is the task's project path. When `mode` is set, a second `system` row
  `permission mode: <mode>` follows it: the mode slug decides the tool
  groups the task may use.
* `tasks/_index.json`: `{version, updatedAt, entries: HistoryItem[]}`. A
  `system` row (and its `permission mode:` row) only for entries whose
  `history_item.json` is not on disk, so a deleted task still shows
  without doubling the others.

Per-call permission decisions, source-derived (Roo-Code at b867ec91; not
observed on any real install), all `system` rows beside the call:

* `ui_messages.json`: a `tool` ask with `isAnswered: true` was approved,
  by a click or by the auto-approval settings (the record does not tell
  them apart); `permission decision: approved isAnswered=true (user or
  auto-approval)` follows the ask's `tool_use` row with its `tool_use_id`
  (the ask's `ts`). A denied ask keeps no mark there.
* `api_conversation_history.json`: a `tool_result` whose text opens with
  `formatResponse`'s JSON `{"status": "denied"|"approved", "message"?,
  "feedback"?}` gives `permission decision: <status>`, plus
  ` feedback=<feedback>` when the key is set, with the result's
  `tool_use_id` and the `tool_use` block's `name`. Without
  `ui_messages.json` the row follows the `tool_result` row; beside it, the
  API history yields only these rows (and its own bad-record rows), since
  the transcript rows come from `ui_messages.json`.

Standing settings, source-derived, one `system` row per scalar or list
entry, `permission setting: <key>=<value> (from <file>, file mtime)` at the
file's modification time with an empty `session_id`:

* The extension's global state, the `ItemTable` row
  `RooVeterinaryInc.roo-cline` (or its lower-case form) of an editor's
  `User/globalStorage/state.vscdb`, and the CLI's
  `.vscode-mock/global-storage/global-state.json`, a flat JSON object:
  `autoApprovalEnabled`, `alwaysAllow*`, `allowedCommands`,
  `deniedCommands`, `commandTimeoutAllowlist`, `allowedMaxRequests`,
  `allowedMaxCost`, `mode`, and in the CLI file `roo-cline.allowedCommands`
  and `roo-cline.deniedCommands`. The text names
  `<file> ItemTable <key>` for the database.
* `.roo/cli-settings.json`: `requireApproval`, `dangerouslySkipPermissions`,
  `mode`.
* `settings/mcp_settings.json` under either root and a project's
  `.roo/mcp.json`: `mcpServers.<name>.alwaysAllow`, one row per tool name
  (`project_path` the project when the base is a collected project).
  Nothing else in these files is read: they can hold `env` and `headers`.

Roo Code Cloud, the vendor service of releases up to 3.53.0, source-derived
(Roo-Code v3.53.0 at 44f6bba2): the same global state can hold the
settings cache the signed-in client kept, `user-settings.settings.
taskSyncEnabled` (`unset (defaults to true)` when absent) and
`organization-settings.cloudSettings.{recordTaskMessages,
enableTaskSharing, allowPublicTaskSharing, taskShareExpirationDays,
allowMembersViewAllTasks, workspaceTaskVisibility}`, each one `sync
setting: <key>=<value> (from <file>, Roo Code Cloud settings cache, file
mtime)` row. Uploads were not recorded per task, so no `session synced:`
row is written and `records_sync` stays False. A failed upload the client
queued for retry is in the workspace state, `roo.retryQueue[]` `{id, url,
options {method, body, headers}, timestamp, retryCount, type, operation,
lastError}` in an editor's `User/workspaceStorage/<hash>/state.vscdb` row
or the CLI's `.vscode-mock/workspace-storage/<hash>/workspace-state.json`;
each entry is `cloud upload queued: <body type, else operation, else -> task=<taskId
or -> type=<type> retries=<retryCount> url=<url>[ lastError=<lastError>]
(Roo Code Cloud retry queue, from <file> roo.retryQueue, request
timestamp)` at its `timestamp`, `session_id` the body's
`properties.taskId`. The headers hold a bearer token and the body the
message: neither is written.

A file above that is not a JSON object is one `parser: <name> is not a JSON
object` row; a state.vscdb problem is one `parser:` row that never echoes
the value.
* `.roo/cli-history.json`, the Roo CLI's input history (the `.roo` directory
  is `getConfigDir()`): `{version: 1, entries: string[]}`, every line
  submitted in the interactive CLI (a task prompt, a follow-up answer, a
  slash command such as `/new`), trimmed, oldest first, consecutive
  duplicates and empty lines skipped, capped at the newest 500. One `user`
  row per string entry in file order, `source_line` the 1-based entry
  index; non-string and blank entries are skipped as the CLI's own
  `loadHistory` skips them. A file cut mid-write yields the entries before
  the cut and one `system` row for the cut (issue 136): the entry that
  does not decode, `parser: unparseable record <N> (<reason>): <raw>` with
  the text from its first character to the end of the file, or `parser: array cut off after record N` when the cut falls
  between entries; a file with no `entries` array is one `system` row. The file records no time, no task id
  and no workspace, so the rows have an empty `timestamp_utc`,
  `session_id` and `project_path`. A secondary source (`dedup.py`): each
  row matches a task's `user` row (the prompt's `say: "text"` or a
  `user_feedback`) on text alone, any task, and is kept only when no task
  has the text, which recovers a prompt whose task directory was deleted.

No model name is recorded anywhere in Roo transcripts (`apiConfigName` is a
profile name), so `model` is always empty. No git branch is recorded.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Iterator
from pathlib import Path

from ..inputs import Artifact
from ..model import Row, compact
from ..timeutil import to_utc
from ..vscode_state import EDITOR_AGENTS, STATE_DB_RX, read_items
from .base import Options, error_rows, file_mtime, setting_value, text_of
from .cline_legacy import (
    API_FILES,
    UI_FILE,
    LegacyTaskParser,
    iter_array_at,
    iter_json_array,
    load_json,
    read_text,
)

ROOT = r"(?:(?:.*/)?User/globalStorage/rooveterinaryinc\.roo-cline|\.vscode-mock/global-storage)"
ITEM_RX = re.compile(r"^%s/tasks/[^/]+/history_item\.json$" % ROOT, re.I)
INDEX_RX = re.compile(r"^%s/tasks/_index\.json$" % ROOT, re.I)
MCP_RX = re.compile(r"^%s/settings/mcp_settings\.json$" % ROOT, re.I)
CLI_HISTORY_REL = ".roo/cli-history.json"
CLI_SETTINGS_REL = ".roo/cli-settings.json"
PROJECT_MCP_REL = ".roo/mcp.json"
GLOBAL_STATE_REL = ".vscode-mock/global-storage/global-state.json"
WORKSPACE_STATE_RX = re.compile(r"^\.vscode-mock/workspace-storage/[^/]+/workspace-state\.json$")
WORKSPACE_DB_RX = re.compile(r"(?:^|/)User/workspaceStorage/[^/]+/state\.vscdb$")
ENTRIES_KEY_RX = re.compile(r'"entries"\s*:\s*(?=\[)')
ITEM_FILE = "history_item.json"

# The extension's global and workspace state is one `ItemTable` row keyed
# by `<publisher>.<name>` (src/package.json: `RooVeterinaryInc`,
# `roo-cline`); the lower-case form is read too in case an editor
# normalises it.
EXTENSION_KEYS = ("RooVeterinaryInc.roo-cline", "rooveterinaryinc.roo-cline")
# Global-state keys that grant or limit what runs without asking
# (packages/types/src/global-settings.ts:97-118 and :192 at b867ec91), and
# the two VS Code settings the CLI's shim keeps in the same file.
STANDING_KEYS = (
    "autoApprovalEnabled",
    "alwaysAllowReadOnly",
    "alwaysAllowReadOnlyOutsideWorkspace",
    "alwaysAllowWrite",
    "alwaysAllowWriteOutsideWorkspace",
    "alwaysAllowWriteProtected",
    "alwaysAllowMcp",
    "alwaysAllowModeSwitch",
    "alwaysAllowSubtasks",
    "alwaysAllowExecute",
    "alwaysAllowFollowupQuestions",
    "allowedCommands",
    "deniedCommands",
    "commandTimeoutAllowlist",
    "allowedMaxRequests",
    "allowedMaxCost",
    "mode",
    "roo-cline.allowedCommands",
    "roo-cline.deniedCommands",
)
CLI_SETTING_KEYS = ("requireApproval", "dangerouslySkipPermissions", "mode")
# Roo Code Cloud (releases up to 3.53.0): cached account settings that
# decide whether task messages were uploaded.
ORG_SYNC_KEYS = (
    "recordTaskMessages",
    "enableTaskSharing",
    "allowPublicTaskSharing",
    "taskShareExpirationDays",
    "allowMembersViewAllTasks",
    "workspaceTaskVisibility",
)
RETRY_QUEUE_KEY = "roo.retryQueue"


class RooCodeParser(LegacyTaskParser):
    agent = "roo-code"
    name = "roo-code"
    has_secondary = True
    # The extension's global state (standing permission settings, the Roo
    # Code Cloud settings cache) and workspace state (the cloud retry queue)
    # are rows of the editor's state.vscdb, which the catalog attributes to
    # the editor.
    reads_agents = EDITOR_AGENTS
    ROOT = ROOT
    PROJECT_KEY = "workspace"

    def wants(self, artifact: Artifact) -> bool:
        rel = artifact.rel
        return bool(
            self.task_match(artifact)
            or ITEM_RX.match(rel)
            or INDEX_RX.match(rel)
            or MCP_RX.match(rel)
            or WORKSPACE_STATE_RX.match(rel)
            or rel in (CLI_HISTORY_REL, CLI_SETTINGS_REL, PROJECT_MCP_REL, GLOBAL_STATE_REL)
            or STATE_DB_RX.search(rel)
            or WORKSPACE_DB_RX.search(rel)
        )

    def secondary(self, artifact: Artifact) -> bool:
        return artifact.rel == CLI_HISTORY_REL

    def history_item(self, task_dir: Path, root: Path, task_id: str) -> dict | None:
        item = load_json(task_dir / ITEM_FILE)
        if isinstance(item, dict):
            return item
        index = self.cached_json(root / "tasks" / "_index.json")
        entries = index.get("entries") if isinstance(index, dict) else None
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and str(entry.get("id")) == task_id:
                    return entry
        return None

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        rel = artifact.rel
        if self.task_match(artifact):
            yield from self.parse_task_file(artifact, opts)
        elif ITEM_RX.match(rel):
            item = load_json(artifact.disk_path)
            if isinstance(item, dict):
                yield from self._history_rows(artifact, item, 1, opts)
            else:
                yield from error_rows(
                    self,
                    artifact,
                    [(0, "history_item.json is not a JSON object", "")],
                    artifact.disk_path.parent.name,
                )
        elif INDEX_RX.match(rel):
            yield from self._parse_index(artifact, opts)
        elif rel == CLI_HISTORY_REL:
            yield from self._parse_cli_history(artifact)
        elif MCP_RX.match(rel) or rel == PROJECT_MCP_REL:
            yield from self._parse_mcp(artifact)
        elif rel == CLI_SETTINGS_REL:
            yield from self._parse_cli_settings(artifact)
        elif rel == GLOBAL_STATE_REL:
            state = self._json_object(artifact)
            if state is None:
                yield self._bad_file(artifact, "global-state.json is not a JSON object")
            else:
                yield from self._global_state_rows(artifact, state, rel)
        elif WORKSPACE_STATE_RX.match(rel):
            state = self._json_object(artifact)
            if state is None:
                yield self._bad_file(artifact, "workspace-state.json is not a JSON object")
            else:
                yield from self._retry_queue_rows(artifact, state, rel)
        elif STATE_DB_RX.search(rel) or WORKSPACE_DB_RX.search(rel):
            yield from self._parse_state_db(artifact)

    # ---- per-call permission decisions ---------------------------------------

    def parse_task_file(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        name = artifact.disk_path.name.lower()
        if name == UI_FILE:
            yield from self._ui_with_decisions(artifact, opts)
        elif name in API_FILES:
            yield from self._api_with_decisions(artifact, opts)
        else:
            yield from super().parse_task_file(artifact, opts)

    def _ui_with_decisions(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        """The shared `ui_messages.json` rows, with a `permission decision:`
        row after the `tool_use` row of each `tool` ask marked
        `isAnswered: true` (approved by a click or automatically). The
        pre-scan's errors are dropped: the shared reader reports them."""
        answered = {
            index
            for index, msg in iter_json_array(artifact.disk_path, [])
            if isinstance(msg, dict)
            and msg.get("type") == "ask"
            and msg.get("ask") == "tool"
            and msg.get("isAnswered") is True
        }
        for row in self._parse_ui(artifact, self.context(artifact), opts):
            yield row
            if row.turn_type == "tool_use" and row.source_line in answered:
                answered.discard(row.source_line)
                yield system_like(row, APPROVED_TEXT)

    def _api_with_decisions(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        """API history. Beside `ui_messages.json` it yields only the decision
        rows (and the file's bad-record rows), since the transcript rows come
        from that file; alone, it yields the shared rows with each decision
        after its `tool_result` row."""
        ctx = self.context(artifact)
        if (artifact.disk_path.parent / UI_FILE).is_file():
            errors: list = []
            for index, timestamp, tid, name, text in api_decisions(artifact.disk_path, errors):
                row = self._row(artifact, ctx, index, to_utc(timestamp) or ctx.start)
                row.tool_use_id = tid
                row.tool_name = name
                yield system_like(row, text)
            yield from error_rows(self, artifact, errors, ctx.task_id, ctx.project_path)
            return
        pending: dict[str, list[tuple[str, str]]] = {}
        for _index, _timestamp, tid, name, text in api_decisions(artifact.disk_path, []):
            pending.setdefault(tid, []).append((name, text))
        for row in self._parse_api(artifact, ctx, opts):
            yield row
            if row.turn_type == "tool_result" and pending.get(row.tool_use_id):
                name, text = pending[row.tool_use_id].pop(0)
                decision = system_like(row, text)
                decision.tool_name = decision.tool_name or name
                yield decision

    # ---- task index entries ---------------------------------------------------

    def _history_rows(
        self, artifact: Artifact, item: dict, index: int, opts: Options
    ) -> Iterator[Row]:
        """The shared task row, then `permission mode: <mode>` from the
        task's `mode` slug, which decides the tool groups the task may use."""
        row = self.history_row(artifact, item, index, opts)
        yield row
        mode = item.get("mode")
        if isinstance(mode, str) and mode:
            yield system_like(row, "permission mode: %s" % mode)

    def _parse_cli_history(self, artifact: Artifact) -> Iterator[Row]:
        errors: list = []
        data = load_json(artifact.disk_path)
        if isinstance(data, dict) and isinstance(data.get("entries"), list):
            entries = enumerate(data["entries"], 1)
        else:
            # Cut mid-write (the CLI rewrites the whole file per prompt): walk
            # the entries array as far as it parses.
            text = read_text(artifact.disk_path) if data is None else None
            match = ENTRIES_KEY_RX.search(text) if text is not None else None
            if match and text is not None:
                entries = iter_array_at(text, match.end(), errors)
            else:
                errors.append((0, "cli-history.json has no entries array", ""))
                entries = iter(())
        for index, entry in entries:
            if not isinstance(entry, str) or not entry.strip():
                continue
            row = self.base_row(artifact)
            row.source_line = index
            row.turn_type = "user"
            row.text = entry
            yield row
        if data is None and not errors:
            errors.append((0, "cli-history.json unparseable after its entries array", ""))
        yield from error_rows(self, artifact, errors)

    def _parse_index(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        index = load_json(artifact.disk_path)
        if not isinstance(index, dict) or not isinstance(index.get("entries"), list):
            yield from error_rows(self, artifact, [(0, "_index.json has no entries array", "")])
            return
        tasks = artifact.disk_path.parent
        for position, entry in enumerate(index["entries"], 1):
            if not isinstance(entry, dict):
                continue
            tid = str(entry.get("id") or "")
            if tid and (tasks / tid / ITEM_FILE).is_file():
                continue
            yield from self._history_rows(artifact, entry, position, opts)

    # ---- standing settings ----------------------------------------------------

    @staticmethod
    def _json_object(artifact: Artifact) -> dict | None:
        data = load_json(artifact.disk_path)
        return data if isinstance(data, dict) else None

    def _bad_file(self, artifact: Artifact, message: str) -> Row:
        row = self.base_row(artifact)
        row.turn_type = "system"
        row.timestamp_utc = file_mtime(artifact)
        row.text = "parser: " + message
        return row

    def _setting_row(
        self, artifact: Artifact, label: str, key: str, value, source: str, project: str = ""
    ) -> Row:
        row = self.base_row(artifact)
        row.source_line = 1
        row.turn_type = "system"
        row.timestamp_utc = file_mtime(artifact)
        row.project_path = project
        row.text = compact(
            "%s: %s=%s (from %s, file mtime)" % (label, key, setting_value(value), source)
        )
        return row

    def _settings_rows(self, artifact: Artifact, doc: dict, keys, source: str) -> Iterator[Row]:
        """One `permission setting:` row per scalar, or per entry of a list."""
        for key in keys:
            value = doc.get(key)
            if value is None:
                continue
            for item in value if isinstance(value, list) else [value]:
                yield self._setting_row(artifact, "permission setting", key, item, source)

    def _global_state_rows(self, artifact: Artifact, state: dict, source: str) -> Iterator[Row]:
        """Standing permission settings, then the Roo Code Cloud settings
        cache (releases up to 3.53.0), which exists only while the extension
        was signed in and says whether task messages were uploaded."""
        yield from self._settings_rows(artifact, state, STANDING_KEYS, source)
        cloud_source = "%s, Roo Code Cloud settings cache" % source
        user = state.get("user-settings")
        if isinstance(user, dict):
            conf = user.get("settings")
            value = conf.get("taskSyncEnabled") if isinstance(conf, dict) else None
            yield self._setting_row(
                artifact,
                "sync setting",
                "user-settings.settings.taskSyncEnabled",
                "unset (defaults to true)" if value is None else value,
                cloud_source,
            )
        org = state.get("organization-settings")
        cloud = org.get("cloudSettings") if isinstance(org, dict) else None
        if isinstance(cloud, dict):
            for key in ORG_SYNC_KEYS:
                if cloud.get(key) is not None:
                    yield self._setting_row(
                        artifact,
                        "sync setting",
                        "organization-settings.cloudSettings." + key,
                        cloud[key],
                        cloud_source,
                    )

    def _parse_cli_settings(self, artifact: Artifact) -> Iterator[Row]:
        doc = self._json_object(artifact)
        if doc is None:
            yield self._bad_file(artifact, "cli-settings.json is not a JSON object")
            return
        yield from self._settings_rows(artifact, doc, CLI_SETTING_KEYS, artifact.rel)

    def _parse_mcp(self, artifact: Artifact) -> Iterator[Row]:
        """`mcpServers.<name>.alwaysAllow`, one row per tool name. Nothing
        else is read: the server entries can hold `env` and `headers`."""
        doc = self._json_object(artifact)
        if doc is None:
            yield self._bad_file(artifact, "%s is not a JSON object" % artifact.disk_path.name)
            return
        project = artifact.home.original if artifact.home.project else ""
        servers = doc.get("mcpServers")
        for name, conf in servers.items() if isinstance(servers, dict) else ():
            tools = conf.get("alwaysAllow") if isinstance(conf, dict) else None
            for tool in tools if isinstance(tools, list) else ():
                yield self._setting_row(
                    artifact,
                    "permission setting",
                    "mcpServers.%s.alwaysAllow" % name,
                    tool,
                    artifact.rel,
                    project,
                )

    def _parse_state_db(self, artifact: Artifact) -> Iterator[Row]:
        values, problems = read_items(artifact.disk_path, EXTENSION_KEYS)
        workspace = bool(WORKSPACE_DB_RX.search(artifact.rel))
        for key in EXTENSION_KEYS:
            state = values.get(key)
            if state is None:
                continue
            if not isinstance(state, dict):
                if not any(key in problem for problem in problems):
                    problems.append("%s value is not a JSON object" % key)
                continue
            source = "%s ItemTable %s" % (artifact.rel, key)
            if workspace:
                yield from self._retry_queue_rows(artifact, state, source)
            else:
                yield from self._global_state_rows(artifact, state, source)
        for problem in problems:
            # never echo the value: the workspace state's retry queue holds a
            # bearer token
            yield self._bad_file(artifact, problem.split(" (", 1)[0])

    # ---- Roo Code Cloud retry queue -------------------------------------------

    def _retry_queue_rows(self, artifact: Artifact, state: dict, source: str) -> Iterator[Row]:
        """One row per request the Roo Code Cloud client (releases up to
        3.53.0) queued after a failed upload. The request's headers carry a
        bearer token and its body the event, so only the event type, the task
        id, the URL and the retry state are written."""
        queue = state.get(RETRY_QUEUE_KEY)
        for index, req in enumerate(queue if isinstance(queue, list) else [], 1):
            if not isinstance(req, dict):
                continue
            event = queued_event(req)
            props = event.get("properties")
            task_id = props.get("taskId") if isinstance(props, dict) else None
            row = self.base_row(artifact)
            row.source_line = index
            row.turn_type = "system"
            row.timestamp_utc = to_utc(req.get("timestamp"))
            row.session_id = str(task_id or "")
            parts = [
                "cloud upload queued: %s" % (event.get("type") or req.get("operation") or "-"),
                "task=%s" % (task_id or "-"),
                "type=%s" % (req.get("type") or "-"),
                "retries=%s" % req.get("retryCount", "-"),
                "url=%s" % (req.get("url") or "-"),
            ]
            if req.get("lastError"):
                parts.append("lastError=%s" % req["lastError"])
            row.text = compact(
                "%s (Roo Code Cloud retry queue, from %s %s, request timestamp)"
                % (" ".join(parts), source, RETRY_QUEUE_KEY)
            )
            yield row


APPROVED_TEXT = "permission decision: approved isAnswered=true (user or auto-approval)"


def system_like(like: Row, text: str) -> Row:
    """A `system` row with `text` and every other field of `like`."""
    return dataclasses.replace(like, turn_type="system", text=compact(text))


def queued_event(req: dict) -> dict:
    """The JSON event body of a queued request, or {} (a form upload or
    anything else that is not a JSON object)."""
    options = req.get("options")
    body = options.get("body") if isinstance(options, dict) else None
    if not isinstance(body, str):
        return {}
    try:
        event = json.loads(body)
    except ValueError:
        return {}
    return event if isinstance(event, dict) else {}


def api_decisions(path: Path, errors: list) -> Iterator[tuple[int, object, str, str, str]]:
    """(record position, record `ts`, tool_use_id, tool name, row text) for
    each `tool_result` of the API history whose text opens with the JSON
    `formatResponse` writes for a denial or an approval with feedback:
    `{"status":"denied","message":...}`, `{"status":"denied","feedback":...}`
    or `{"status":"approved","feedback":...}`, the last followed by the tool
    output."""
    names: dict[str, str] = {}
    dec = json.JSONDecoder()
    for index, msg in iter_json_array(path, errors):
        if not isinstance(msg, dict) or not isinstance(msg.get("content"), list):
            continue
        for block in msg["content"]:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                names[str(block.get("id") or "")] = str(block.get("name") or "")
                continue
            if block.get("type") != "tool_result":
                continue
            body = text_of(block.get("content")).lstrip()
            if not body.startswith("{"):
                continue
            try:
                status, _end = dec.raw_decode(body)
            except ValueError:
                continue
            if not isinstance(status, dict) or status.get("status") not in ("denied", "approved"):
                continue
            text = "permission decision: %s" % status["status"]
            if status.get("feedback") is not None:
                text += " feedback=%s" % setting_value(status["feedback"])
            tid = str(block.get("tool_use_id") or "")
            yield index, msg.get("ts"), tid, names.get(tid, ""), text
