"""Twinny chat conversations.

Validated against source, twinnydotdev/twinny at 9339bd10 (see
`research/twinny.md`), with a synthetic fixture; no real install
was checked. Twinny keeps no transcript file of its own: every conversation
is inside the `ItemTable` row `key = 'rjmacarthy.twinny'` of the editor's
`<User dir>/globalStorage/state.vscdb`, whose JSON value is the extension's
whole global state. The catalog attributes that file to `vscode`, or to the
fork (Cursor, Windsurf, PearAI, Kiro, Antigravity) whose `User/` directory
it sits in, so this parser lists all of them, `vscode_state.EDITOR_AGENTS`,
in `reads_agents`.

Keys read from the value: `twinny.conversations` (an object keyed by
conversation id) and `twinny.active-conversation` (a copy of the open
conversation, used only when its id is missing from the first). Conversation
fields: `id`, `title`, `updatedAt` (epoch ms, absent in older builds),
`messages[]`. Message fields: `role` (`user` or `assistant`), `content` (a
string, reasoning inline as `<think>...</think>` or
`<thinking>...</thinking>`), `images`, `meta.model`, `meta.withheld`
(counts of credentials Twinny's secret shield masked), `changes` (`id`,
`files[]` with `path`, `status`, `added`, `removed`, `undone`, `noUndo`)
and `toolSteps[]` (`id`, `name`, `summary`, `args`, `command`, `output`,
`status`, `approval`, `said`).

Model and permission rows, all `system`: `meta.model` gives `model: <id>`
at the first assistant message of a conversation that names one and
`model: <old> -> <new>` on every later change, before that message's
rows. A tool step saved while it waited for the user's Run or Skip
(`status` `waiting`, with `approval` `command` or `change` naming what
was asked) or after it was skipped (`status` `skipped`: the user chose
Skip, or a stop answered the wait with Skip) becomes
`permission decision: <status>`, with ` approval=<approval>` when the
step records it, after the step's `tool_result` row. An approved step
ends `done` or `failed` like one that needed no approval, and a
`stopped` step may or may not have waited, so neither gets a row.
`node/trusted-peers.json` is not read: its shape is not recorded.

Source-derived; not observed on any real install (twinnydotdev/twinny at
0337b265, 4.3.15), with an empty `session_id` and the file's modification
time, each text ending `(from state.vscdb rjmacarthy.twinny, file mtime)`:

- Standing grants, from the global state keys the webview prefixes
  `twinny-global-context-` (storage.ts:25-35, chat/index.ts:162-192 and
  466-491): `twinny-global-context-agentMode` (boolean) gives `permission
  mode: agentMode=<true|false>`; `twinny-global-context-autoRunCommands`
  (boolean) gives `permission setting: autoRunCommands=<true|false>`;
  each entry of `twinny-global-context-alwaysRunCommands` and
  `twinny-global-context-alwaysRunMcpTools` (string lists) gives
  `permission setting: alwaysRunCommands=<command>` or
  `permission setting: alwaysRunMcpTools=<server/tool>`.
- The team policy a developer accepted when connecting to a team gateway,
  `twinny.teamPolicy` (`url`, `policy`, `providerIds`, `fetchedAt`;
  providers/policy.ts:20-49, protocol/types.ts:44-100): one
  `permission setting: twinny.teamPolicy.<dotted key>=<value>` row per
  leaf, a list giving one row per entry.

Each assistant message's `changes` gives one `file changed: <status>
<path> +<added> -<removed> reply=<changes.id>` row per file, with
` undone=true` and ` noUndo=true` when set, after the message's tool
steps. Source-derived as above.

Secondary sources (`secondary()` True), source-derived as above:

- `<User dir>/workspaceStorage/<id>/rjmacarthy.twinny/agent-changes/
  <uuid>.json` (or `globalStorage/rjmacarthy.twinny/agent-changes/` with
  no folder open), one JSON object per agent-mode reply that changed
  files, `{id, root, createdAt, files[]}` (reply-changes.ts:35-47,
  211-259): the same `file changed:` row per file, with `project_path`
  the `root`, the time `createdAt` (epoch ms) and an empty `session_id`,
  since the record names no conversation; `reply=<id>` is the join to the
  conversation's `changes.id`. The conversation records no project path
  and no time per reply, so deduplication cannot pair the two copies and
  both are shown. `before` (the file's text before the reply) and
  `afterHash` are never emitted.
- The Twinny log channel, `<editor logs>/.../rjmacarthy.twinny/Twinny.log`
  and the copies VS Code rotates it to at 5 MB, `Twinny.log_1` to
  `Twinny.log_6` (microsoft/vscode at 4d22f4f9,
  src/vs/platform/log/common/fileLog.ts:14, 41-44, 78-81). VS Code writes
  each entry as `YYYY-MM-DD HH:MM:SS.mmm [<level>] <message>` in host
  local time (fileLog.ts:62-101); a block entry (Twinny's `Chat messages`,
  `Chat reply`, `FIM #<n> raw` and others, logger.ts:77-87 and 140-144)
  continues on lines indented four spaces. Every entry gives one `system`
  row `log <level>: <first line> (from <file name>, log line time,
  host-local)`, followed by its continuation lines with the four-space
  indent removed, with an empty `session_id` and `source_line` the
  header's line number. A line that is neither a header nor a
  continuation (indented or empty) is a bad line. The time has no zone
  and is emitted as if it were UTC.

Source host, source-derived as above: the `rjmacarthy.twinny` row of
`<User dir>/workspaceStorage/<id>/state.vscdb` keeps the owner and
repository the pull request review tab last listed pull requests for, as
`twinny-workspace-context-reviewOwner` and
`twinny-workspace-context-reviewRepo` (review.tsx:25-62; the extension
fetches them from api.github.com, review/service.ts:154-197). Both set
give `source host repository: https://github.com/<owner>/<repo>
type=review (from workspaceStorage state.vscdb rjmacarthy.twinny, file
mtime)`. No account login is recorded; the GitHub token is the
`twinny.githubToken` editor setting, which this parser never reads.

The same global state value holds `twinny.inference-providers` and the
`twinny.active-*-provider` objects, each with an `apiKey`, and
`twinny.chatgpt-plan.profile` (the ChatGPT plan account's email and
subject): those keys are never read, and nothing from the value is emitted
except the fields above. `secret://` rows are never read (see
`vscode_state.py`).

Messages carry no timestamp, so every row of a conversation inherits its
`updatedAt`, the time of the last save rather than of each turn; order
within a conversation is the order of `messages[]`. Each `toolSteps[]`
entry becomes a `tool_use` (`command`, else `args` as JSON, else
`summary`) and a `tool_result` (`output`, prefixed with the status when it
is not `done`) sharing the step `id`. Since 4.3.5 a message the user
sends while a reply runs is saved among that reply's `toolSteps[]` as a
step with `said: true` (`name` `said`, `id` `said.<id>`, the message in
`summary`, `status` `done`; tool-steps.ts:101-104 and types.ts:129-133 at
0337b265, 4.3.15); it is not a tool call and becomes a `user` row, in its
place among the steps, where the model read it. `<think>` blocks become `thinking`
rows, opt-in, and are removed from the assistant text. There is no
project path, git branch or line number in the conversations:
`source_line` is 0.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

from ..inputs import Artifact, error_reason
from ..model import Row, compact
from ..timeutil import to_utc
from ..vscode_state import EDITOR_AGENTS, STATE_DB_RX, read_item
from .base import (
    Options,
    Parser,
    compact_json,
    error_rows,
    file_mtime,
    line_text,
    setting_value,
    text_of,
    track_change,
)

ITEM_KEY = "rjmacarthy.twinny"
CONVERSATIONS = "twinny.conversations"
ACTIVE = "twinny.active-conversation"
THINK_RX = re.compile(r"<(think|thinking)>(.*?)(?:</\1>|$)", re.S)

# The webview's global values, stored as `twinny-global-context-<key>`
# (webview/base.ts:44, 348-360 at 0337b265), in the order they are written.
GLOBAL_PREFIX = "twinny-global-context-"
STANDING_KEYS = ("agentMode", "autoRunCommands", "alwaysRunCommands", "alwaysRunMcpTools")
TEAM_POLICY = "twinny.teamPolicy"
STANDING_SOURCE = "(from state.vscdb rjmacarthy.twinny, file mtime)"

WORKSPACE_DB_RX = re.compile(r"(?:^|/)User/workspaceStorage/[^/]+/state\.vscdb$")
WORKSPACE_PREFIX = "twinny-workspace-context-"
CHANGES_RX = re.compile(
    r"(?:^|/)User/(?:workspaceStorage/[^/]+|globalStorage)/rjmacarthy\.twinny/"
    r"agent-changes/[^/]+\.json$"
)
LOG_RX = re.compile(r"(?:^|/)logs/(?:[^/]+/)+rjmacarthy\.twinny/Twinny\.log(?:_[0-9]+)?$")
LOG_HEADER_RX = re.compile(
    r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}) \[(trace|debug|info|warning|error)\] (.*)$"
)


def split_think(content: str):
    """(text without reasoning blocks, [reasoning texts])."""
    thoughts: list[str] = []

    def keep(match):
        if match.group(2).strip():
            thoughts.append(match.group(2).strip())
        return ""

    return THINK_RX.sub(keep, content).strip(), thoughts


def file_change_text(change_id, entry: dict) -> str:
    """`file changed: <status> <path> +<added> -<removed> reply=<id>`, with
    ` undone=true` and ` noUndo=true` when the entry sets them."""
    text = "file changed: %s %s +%s -%s reply=%s" % (
        setting_value(entry.get("status", "")),
        setting_value(entry.get("path", "")),
        setting_value(entry.get("added", "")),
        setting_value(entry.get("removed", "")),
        setting_value(change_id if change_id is not None else ""),
    )
    for flag in ("undone", "noUndo"):
        if entry.get(flag) is True:
            text += " %s=true" % flag
    return text


def flatten(prefix: str, value) -> Iterator[tuple[str, str]]:
    """(dotted key, value text) per leaf of `value`; a list gives one pair
    per entry under its own key."""
    if isinstance(value, dict):
        for member, item in value.items():
            yield from flatten("%s.%s" % (prefix, member), item)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                yield prefix, compact_json(item)
            else:
                yield prefix, setting_value(item)
    elif value is not None:
        yield prefix, setting_value(value)


class TwinnyParser(Parser):
    agent = "twinny"
    name = "twinny"
    reads_agents = EDITOR_AGENTS
    has_secondary = True

    def wants(self, artifact: Artifact) -> bool:
        rel = artifact.rel
        return bool(
            STATE_DB_RX.search(rel)
            or WORKSPACE_DB_RX.search(rel)
            or CHANGES_RX.search(rel)
            or LOG_RX.search(rel)
        )

    def secondary(self, artifact: Artifact) -> bool:
        return bool(CHANGES_RX.search(artifact.rel) or LOG_RX.search(artifact.rel))

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        rel = artifact.rel
        if CHANGES_RX.search(rel):
            yield from self._parse_changes(artifact)
            return
        if LOG_RX.search(rel):
            yield from self._parse_log(artifact)
            return
        state, problems = read_item(artifact.disk_path, ITEM_KEY)
        workspace = bool(WORKSPACE_DB_RX.search(rel))
        if isinstance(state, dict):
            if workspace:
                yield from self._workspace_rows(artifact, state)
            else:
                yield from self._global_rows(artifact, state, opts)
        elif state is not None:
            problems = problems or ["%s value is not a JSON object" % ITEM_KEY]
        for problem in problems:
            row = self.base_row(artifact)
            row.turn_type = "system"
            # never echo the value itself: it holds provider apiKeys
            row.text = "parser: " + problem.split(" (", 1)[0]
            yield row

    def _global_rows(self, artifact: Artifact, state: dict, opts: Options) -> Iterator[Row]:
        convs = state.get(CONVERSATIONS)
        convs = (
            list(convs.values())
            if isinstance(convs, dict)
            else convs
            if isinstance(convs, list)
            else []
        )
        convs = [conversation for conversation in convs if isinstance(conversation, dict)]
        active = state.get(ACTIVE)
        ids = {str(conversation.get("id")) for conversation in convs}
        if isinstance(active, dict) and active.get("messages") and str(active.get("id")) not in ids:
            convs.append(active)
        for conv in convs:
            yield from self._conversation(artifact, conv, opts)
        yield from self._standing_rows(artifact, state)

    def _system_row(self, artifact: Artifact, timestamp: str, text: str) -> Row:
        row = self.base_row(artifact)
        row.timestamp_utc = timestamp
        row.turn_type = "system"
        row.text = text
        return row

    def _standing_rows(self, artifact: Artifact, state: dict) -> Iterator[Row]:
        """Standing grants and the team policy, at the file's mtime."""
        timestamp = ""
        for key in STANDING_KEYS:
            value = state.get(GLOBAL_PREFIX + key)
            if value is None:
                continue
            timestamp = timestamp or file_mtime(artifact)
            label = "permission mode" if key == "agentMode" else "permission setting"
            values = value if isinstance(value, list) else [value]
            for item in values:
                text = "%s: %s=%s %s" % (label, key, setting_value(item), STANDING_SOURCE)
                yield self._system_row(artifact, timestamp, text)
        policy = state.get(TEAM_POLICY)
        if isinstance(policy, dict):
            timestamp = timestamp or file_mtime(artifact)
            for key, value in flatten(TEAM_POLICY, policy):
                text = "permission setting: %s=%s %s" % (key, value, STANDING_SOURCE)
                yield self._system_row(artifact, timestamp, text)

    def _workspace_rows(self, artifact: Artifact, state: dict) -> Iterator[Row]:
        """The repository the pull request review tab last listed."""
        owner = state.get(WORKSPACE_PREFIX + "reviewOwner")
        repo = state.get(WORKSPACE_PREFIX + "reviewRepo")
        if isinstance(owner, str) and owner and isinstance(repo, str) and repo:
            text = (
                "source host repository: https://github.com/%s/%s type=review "
                "(from workspaceStorage state.vscdb rjmacarthy.twinny, file mtime)" % (owner, repo)
            )
            yield self._system_row(artifact, file_mtime(artifact), text)

    def _parse_changes(self, artifact: Artifact) -> Iterator[Row]:
        """`file changed:` rows of one agent-changes record."""
        try:
            raw = artifact.disk_path.read_bytes()
        except OSError as error:
            yield from error_rows(
                self, artifact, [(0, "unreadable (%s)" % error_reason(error), "")]
            )
            return
        try:
            record = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError as error:
            msg = "agent-changes record is not valid JSON (%s)" % error
            yield from error_rows(self, artifact, [(0, msg, "")])
            return
        if not isinstance(record, dict):
            msg = "agent-changes record is not a JSON object"
            yield from error_rows(self, artifact, [(0, msg, "")])
            return
        root = record.get("root")
        root = root if isinstance(root, str) else ""
        timestamp = to_utc(record.get("createdAt"))
        files = record.get("files")
        for entry in files if isinstance(files, list) else []:
            if not isinstance(entry, dict):
                continue
            row = self._system_row(artifact, timestamp, file_change_text(record.get("id"), entry))
            row.project_path = root
            yield row

    def _parse_log(self, artifact: Artifact) -> Iterator[Row]:
        """One `system` row per entry of a Twinny log channel file."""
        name = artifact.disk_path.name
        errors: list = []
        entries: list[tuple[int, str, str, str, list[str]]] = []
        more: list[str] | None = None  # the open entry's continuation lines
        try:
            with open(artifact.disk_path, "rb") as handle:
                for line_number, raw in enumerate(handle, 1):
                    line = line_text(raw)
                    match = LOG_HEADER_RX.match(line)
                    if match:
                        more = []
                        entries.append(
                            (line_number, match.group(1), match.group(2), match.group(3), more)
                        )
                    elif more is not None and (not line or line[0] in " \t"):
                        more.append(line[4:] if line.startswith("    ") else line)
                    elif line:
                        errors.append((line_number, "unparseable line (no log line header)", line))
                        more = None  # a continuation after a bad line has no entry
        except OSError as error:
            yield from error_rows(
                self, artifact, [(0, "unreadable (%s)" % error_reason(error), "")]
            )
            return
        for line_number, when, level, message, lines in entries:
            head = "log %s: %s (from %s, log line time, host-local)" % (level, message, name)
            row = self._system_row(artifact, to_utc(when), "\n".join([head, *lines]))
            row.source_line = line_number
            yield row
        yield from error_rows(self, artifact, errors)

    def _conversation(self, artifact: Artifact, conv: dict, opts: Options) -> Iterator[Row]:
        timestamp = to_utc(conv.get("updatedAt"))
        sid = str(conv.get("id") or "")
        messages = conv.get("messages")
        messages = (
            [message for message in messages if isinstance(message, dict)]
            if isinstance(messages, list)
            else []
        )

        def row(turn: str, text, model: str = "", name: str = "", tid: str = "") -> Row:
            result = self.base_row(artifact)
            result.timestamp_utc = timestamp
            result.session_id = sid
            result.turn_type = turn
            result.model = model
            result.tool_name = name
            result.tool_use_id = tid
            result.text = compact(text)
            return result

        yield row(
            "system",
            "conversation: %s | messages=%d%s"
            % (conv.get("title") or "", len(messages), "" if timestamp else " | updatedAt unknown"),
        )
        seen: dict = {}  # per conversation, so the tracked key needs no session id
        for msg in messages:
            role = msg.get("role")
            meta = msg.get("meta")
            if not isinstance(meta, dict):
                meta = {}
            model = str(meta.get("model") or "")
            if role == "assistant":
                change = track_change("model", seen, "model", model)
                if change:
                    yield row("system", change, model)
            content = msg.get("content")
            text = content if isinstance(content, str) else text_of(content)
            text, thoughts = split_think(text)
            if opts.include_thinking:
                for thought in thoughts:
                    yield row("thinking", thought, model)
            images = msg.get("images")
            if isinstance(images, list) and images:
                text = ("%s\n[%d image(s)]" % (text, len(images))).strip()
            if text:
                turn = (
                    "user" if role == "user" else "assistant" if role == "assistant" else "system"
                )
                yield row(
                    turn,
                    text if turn != "system" else "%s: %s" % (role or "unknown", text),
                    model if turn != "user" else "",
                )
            for step in msg.get("toolSteps") or []:
                if not isinstance(step, dict):
                    continue
                if step.get("said") is True:
                    # Not a tool: a message the user sent while the reply ran.
                    said = step.get("summary")
                    # A summary that is not a string is kept whole, as JSON.
                    said = (
                        said
                        if isinstance(said, str)
                        else ""
                        if said is None
                        else compact_json(said)
                    )
                    yield row("user", said)
                    continue
                name, tid = str(step.get("name") or ""), str(step.get("id") or "")
                args = step.get("args")
                body = (
                    step.get("command")
                    or (compact_json(args) if args else "")
                    or step.get("summary")
                    or ""
                )
                yield row("tool_use", body, model, name, tid)
                out = step.get("output")
                out = out if isinstance(out, str) else compact_json(out) if out is not None else ""
                status = str(step.get("status") or "")
                if status and status != "done":
                    out = "[%s] %s" % (status, out)
                yield row("tool_result", out, model, name, tid)
                if status in ("waiting", "skipped"):
                    decision = "permission decision: " + status
                    if step.get("approval"):
                        decision += " approval=" + setting_value(step["approval"])
                    yield row("system", decision, model, name, tid)
            changes = msg.get("changes")
            if isinstance(changes, dict) and isinstance(changes.get("files"), list):
                for entry in changes["files"]:
                    if isinstance(entry, dict):
                        yield row("system", file_change_text(changes.get("id"), entry), model)
            withheld = meta.get("withheld")
            if withheld:
                yield row("system", "secret shield withheld: %s" % compact_json(withheld), model)


__all__ = ["TwinnyParser", "split_think"]
