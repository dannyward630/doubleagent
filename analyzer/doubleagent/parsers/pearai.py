"""PearAI chat sessions (Continue fork) and agent tasks (Roo Code fork).

Validated against source, trypear/pearai-submodule at 51eceef6 and
trypear/PearAI-Roo-Code at 0b6df736 (see `research/pearai.md`),
with a synthetic fixture; no real install was checked. Both forks are older
snapshots of their upstreams, so the shapes differ from `continue_dev.py`
and `roo_code.py`.

Chat sessions, `.pearai/sessions/` (the Continue fork's global dir):

* `<sessionId>.json`: `sessionId`, `title`, `workspaceDirectory`,
  `history[]` and `perplexityHistory[]` ("PearAI Search" turns). Items:
  `message` (`role` user, assistant or system; `content` a string or
  `{type: "text", text}` / `{type: "imageUrl"}` parts), `contextItems[]`
  (`name`, `description`), `promptLogs[].completionOptions.model`,
  `citations[]` (`url`, `title`). There are no tool calls, tool messages or
  thinking in this fork.
* `sessions.json`: the index, `{sessionId, title, dateCreated (ms epoch as
  a string), workspaceDirectory, integrationType}`; read for the time
  through `continue_dev.read_index`, and yields rows only for what it
  loses (issue 170), with the same texts as the Continue parser: `parser:
  unreadable session index: <reason>`, `parser: not a JSON array`,
  `parser: unparseable record <N> (<reason>): <the text from that element
  to the end of the file>`, `parser: array cut off after record <N>`,
  `parser: unparseable record <N> (not an object with a sessionId):
  <the element as JSON>` and `parser: unparseable data after the JSON
  array`. A session the index lost has an empty `timestamp_utc`.

Every row of a session inherits `dateCreated` (no per-message time).
`history[]` rows come first, then `perplexityHistory[]`; `source_line` is
the 1-based item position, continuing from `history[]` into
`perplexityHistory[]`, and 0 for the session row. User rows list the
context items (`description`, else `name`); assistant rows list citation
URLs. A truncated session file keeps the `history[]` items decoded before
the cut (via `continue_dev.load_session`) plus one `system` row;
`perplexityHistory[]` is not recovered from a damaged file. The first
item whose `promptLogs[].completionOptions.model` names a model yields
`model: <model>` ahead of the item's rows, and a later item naming a
different one yields `model: <old> -> <new>`. The format has no switch
record, so a change is only seen as a different value between items. The
chat surface has no tools and records no permission state.

Agent tasks, `<editor User dir>/globalStorage/pearai.pearai-roo-cline/tasks/
<taskId>/` (Roo Code 3.15): `ui_messages.json`, `api_conversation_history.json`
and `task_metadata.json`, read by the shared mapping in `cline_legacy.py`
exactly as for Roo Code, so `ui_messages.json` is preferred and the API
history is parsed only when it is absent. The task's project is
`taskHistory[].workspace` from the `pearai.pearai-roo-cline` row of the
`state.vscdb` beside the extension directory, when it was collected.

API history records carry `ts` (ms) and Anthropic content blocks, but tool
calls are XML inside assistant text: `<execute_command><command>npm
test</command></execute_command>`, tool names from `toolNames` in
`src/schemas/index.ts`. Each such tag becomes a `tool_use` row whose text
is the parameter values joined with ` | `; `<thinking>` blocks become
`thinking` rows (opt-in); the remaining text is an `assistant` row. Results
come back in the next user message as a text block
`[<tool> for '<arg>'] Result:` followed by the output blocks, or a
`Skipping tool [...]` / `Tool [...] was not executed` notice; each becomes a
`tool_result` row. Tool calls have no id, so `tool_use_id` is the
assistant message's position in the array (with `.2`, `.3` for further
tags in the same message) and a result takes the position of the message
before it; Roo runs one tool per message and the API history alternates
roles. `<environment_details>` blocks become `system` rows, and the
`<task>` wrapper of the first prompt is removed. No model or git branch is
recorded.

The items below are source-derived (pearai-submodule at 51eceef6,
PearAI-Roo-Code at 0b6df736, pearai-app at d930f023) and not observed on
any real install.

Permission decisions (Roo Code 3.15.3 texts, `src/core/prompts/responses.ts`
of the fork): a tool result block that starts `The user denied this
operation.` is followed by `permission decision: denied`, one that starts
`The user denied this operation and provided the following feedback:` by
`permission decision: denied with feedback`, and one that starts `The user
approved this operation and provided the following context:` by
`permission decision: approved with feedback`, each a `system` row with the
call's `tool_name` and `tool_use_id` at the API message's `ts`. An approval
with no note, by the user or by auto-approve, leaves no mark. When
`ui_messages.json` is present the API history is still read, for these rows
only (and its bad records): the `tool_use_id` is then the `ts` of the last
`ui_messages.json` tool ask (`tool`, `command`, `use_mcp_server`,
`browser_action_launch`, ...) at or before the API message, the id the
`ui_messages.json` rows give that call, or empty when there is none.

The editor's `state.vscdb` (`<User dir>/globalStorage/state.vscdb`), the
`pearai.pearai-roo-cline` row of `ItemTable`: one `system` row per
`taskHistory[]` entry (`id`, `number`, `ts`, `task`, `tokensIn`,
`tokensOut`, `cacheWrites`, `cacheReads`, `totalCost`, `size`, `workspace`,
`creatorModeConfig{creatorMode, newProjectType, newProjectPath}`), `task:
<task> | tokensIn=.. tokensOut=.. totalCost=.. number=<n>`, ending
` | creator mode: newProjectType=<t> newProjectPath=<p>` for a task
PearAI Creator started, at the entry's `ts`, with the task id as
`session_id` and `workspace` as `project_path`, so a task whose directory
is missing from the collection still shows (the agent's own delete removes
the entry with the directory). Then one `permission setting: <key>=<value> (from
state.vscdb pearai.pearai-roo-cline, file mtime)` row per standing
auto-approval key present (`autoApprovalEnabled`, `alwaysAllowReadOnly`,
`alwaysAllowReadOnlyOutsideWorkspace`, `alwaysAllowWrite`,
`alwaysAllowWriteOutsideWorkspace`, `alwaysAllowBrowser`,
`alwaysApproveResubmit`, `alwaysAllowMcp`, `alwaysAllowModeSwitch`,
`alwaysAllowSubtasks`, `alwaysAllowExecute`, `allowedCommands`), at the
file's modification time. A database without the row yields nothing; a
damaged one or a value that is not JSON is one `parser:` row.

Secondary sources of the chat surface (`secondary()` is True for them):

* The `PearAI` output channel log, `<User data dir>/logs/<YYYYMMDDTHHMMSS>/
  window<N>/exthost/output_logging_<time>/<n>-PearAI.log`. Each write is two
  lines of 74 `=` followed by either `Settings:` (`key: value` lines, the
  `model` among them, a blank line, a line of 44 `#`, a blank line and the
  prompt) or `Completion:`, a blank line and the reply. A prompt in the
  `<role>` form of `_formatChatMessages` (`<system>`, `<user>` and
  `<assistant>` blocks) yields its last `<user>` block as a `user` row; any
  other prompt (autocomplete's `<prefix><FIM><suffix>`, a templated prompt)
  is a `system` row `model request: <prompt>`. A `Completion:` record is an
  `assistant` row after a `<role>` prompt and a `system` row `model
  completion: <reply>` otherwise. A request's `model` value yields `model:
  <id>` and `model: <old> -> <new>` rows tracked over the file. The file
  records no time, session or project, so every row has an empty
  `timestamp_utc`, `session_id` and `project_path` and matches on text
  alone; a prompt sent with context items carries them in its `<user>`
  block and so never pairs with the session's `user` row. A record that
  starts with neither header, or a `Settings:` record with no `#` rule (a
  write cut off), is `parser: unparseable record (<reason>): <record>`, the
  record as read, at its first line.
* `.pearai/dev_data/chat.jsonl`, one line per prompt log of an item the
  user rated: `completionOptions.model`, `prompt`, `completion`,
  `feedback` (a boolean) and `sessionId`. The prompt yields a `user` row
  as above, the completion an `assistant` row, then `user feedback:
  <true|false> (from dev_data/chat.jsonl)`, all with the line's
  `sessionId`, the session's `workspaceDirectory` from `sessions.json`, the
  model in the `model` column and an empty `timestamp_utc`.

`.pearai/dev_data/tokens_generated.jsonl` (`model`, `provider`,
`promptTokens`, `generatedTokens`, one line per model request) repeats no
event of the session files, so it is a primary source: one `system` row
per line, `tokens generated: model=<model> provider=<provider>
promptTokens=<n> generatedTokens=<n>`, with the model in the `model`
column and an empty `timestamp_utc`, `session_id` and `project_path`. Every
bad line of either `dev_data` file is its own `parser:` row.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from ..inputs import Artifact
from ..model import Row, compact
from ..timeutil import to_utc
from ..vscode_state import read_item
from .base import (
    Options,
    error_rows,
    file_mtime,
    iter_jsonl,
    setting_value,
    track_change,
)
from .cline_legacy import (
    API_FILES,
    TOOL_USE_KINDS,
    UI_FILE,
    LegacyTaskParser,
    content_rows,
    iter_json_array,
    read_text,
)
from .continue_dev import ContinueParser, load_session, message_text

ROOT = r"(?:.*/)?User/globalStorage/pearai\.pearai-roo-cline"
SESSION_RX = re.compile(r"^(?:.*/)?\.pearai/sessions/([^/]+)\.json$")
INDEX_NAME = "sessions.json"
EXTENSION_ID = "pearai.pearai-roo-cline"
# The editor's output channel file for the chat extension's `PearAI` channel
# (pearai-app src/vs/workbench/api/common/extHostOutput.ts:121, :160-170).
LOG_RX = re.compile(r"^(?:.*/)?logs/[^/]+/window\d+/exthost/output_logging_[^/]+/\d+-PearAI\.log$")
DEVDATA_RX = re.compile(r"^(?:.*/)?\.pearai/dev_data/(chat|tokens_generated)\.jsonl$")
STATE_RX = re.compile(r"^(?:.*/)?User/globalStorage/state\.vscdb$")
# Each write to the channel: two lines of 74 `=` (VsCodeExtension.ts:147-155),
# then `Settings:` ... a rule of 44 `#` ... the prompt, or `Completion:`
# (core/llm/index.ts:247-261, :586-587).
LOG_SEPARATOR_RX = re.compile(r"={74}\n={74}\n")
LOG_RULE = "\n\n" + "#" * 44 + "\n\n"
ROLE_BLOCK_RX = re.compile(r"^<(system|user|assistant)>\n", re.M)
PERMISSION_TEXTS = (
    ("The user denied this operation and provided the following feedback:", "denied with feedback"),
    (
        "The user approved this operation and provided the following context:",
        "approved with feedback",
    ),
    ("The user denied this operation.", "denied"),
)
STANDING_KEYS = (
    "autoApprovalEnabled",
    "alwaysAllowReadOnly",
    "alwaysAllowReadOnlyOutsideWorkspace",
    "alwaysAllowWrite",
    "alwaysAllowWriteOutsideWorkspace",
    "alwaysAllowBrowser",
    "alwaysApproveResubmit",
    "alwaysAllowMcp",
    "alwaysAllowModeSwitch",
    "alwaysAllowSubtasks",
    "alwaysAllowExecute",
    "allowedCommands",
)

TOOL_NAMES = (
    "execute_command",
    "read_file",
    "write_to_file",
    "apply_diff",
    "insert_content",
    "search_and_replace",
    "search_files",
    "list_files",
    "list_code_definition_names",
    "browser_action",
    "use_mcp_tool",
    "access_mcp_resource",
    "ask_followup_question",
    "attempt_completion",
    "switch_mode",
    "new_task",
    "fetch_instructions",
)
BLOCK_RX = re.compile(r"<(thinking|%s)>(.*?)(?:</\1>|$)" % "|".join(TOOL_NAMES), re.S)
PARAM_RX = re.compile(r"<([a-z_]+)>(.*?)(?:</\1>|$)", re.S)
RESULT_RX = re.compile(r"^\[([a-z_]+)\b.*\] Result:\s*$", re.S)
NOTICE_RX = re.compile(r"^(?:Skipping tool|Tool) \[([a-z_]+)")
TASK_RX = re.compile(r"^\s*<task>\s*(.*?)\s*</task>\s*$", re.S)


def permission_decision(text: str) -> str:
    """The decision a Roo 3.15 tool result block records, or ""."""
    text = text.lstrip()
    for prefix, decision in PERMISSION_TEXTS:
        if text.startswith(prefix):
            return decision
    return ""


def prompt_turn(prompt: str) -> tuple[str, str]:
    """(turn_type, text) for a logged prompt: the last `<user>` block of a
    prompt in `_formatChatMessages` form as `user`, any other prompt as a
    `system` row `model request: <prompt>`."""
    blocks = list(ROLE_BLOCK_RX.finditer(prompt))
    if not blocks or blocks[0].start() != 0:
        return "system", "model request: " + prompt
    users = [i for i, m in enumerate(blocks) if m.group(1) == "user"]
    if not users:
        return "system", "model request: " + prompt
    i = users[-1]
    end = blocks[i + 1].start() if i + 1 < len(blocks) else len(prompt)
    return "user", prompt[blocks[i].end() : end]


def xml_blocks(text: str, include_thinking: bool) -> Iterator[tuple[str, str, str]]:
    """(turn_type, text, tool_name) for Roo assistant text with XML tool tags."""
    pos = 0
    for m in BLOCK_RX.finditer(text):
        before = text[pos : m.start()].strip()
        if before:
            yield "assistant", before, ""
        pos = m.end()
        tag, body = m.group(1), m.group(2)
        if tag == "thinking":
            if include_thinking and body.strip():
                yield "thinking", body.strip(), ""
            continue
        params = [v.strip() for _, v in PARAM_RX.findall(body) if v.strip()]
        yield "tool_use", " | ".join(params) if params else body.strip(), tag
    rest = text[pos:].strip()
    if rest:
        yield "assistant", rest, ""


class PearAiParser(LegacyTaskParser):
    agent = "pearai"
    name = "pearai"
    has_secondary = True
    ROOT = ROOT
    PROJECT_KEY = "workspace"

    def __init__(self) -> None:
        super().__init__()
        self._continue = ContinueParser()  # for its cached sessions.json reader
        self._state: dict[tuple, tuple[object, list[str]]] = {}

    def wants(self, artifact: Artifact) -> bool:
        # sessions.json too, for the rows that say what the index lost
        rel = artifact.rel
        return bool(
            SESSION_RX.match(rel)
            or self.task_match(artifact)
            or LOG_RX.match(rel)
            or DEVDATA_RX.match(rel)
            or STATE_RX.match(rel)
        )

    def secondary(self, artifact: Artifact) -> bool:
        m = DEVDATA_RX.match(artifact.rel)
        return bool(LOG_RX.match(artifact.rel) or (m and m.group(1) == "chat"))

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        m = SESSION_RX.match(artifact.rel)
        dev = DEVDATA_RX.match(artifact.rel)
        if m and m.group(1) + ".json" == INDEX_NAME:
            errors = self._continue.index_errors(artifact.disk_path)
            yield from error_rows(self, artifact, errors)
        elif m:
            yield from self._parse_session(artifact, opts)
        elif self.task_match(artifact):
            yield from self.parse_task_file(artifact, opts)
        elif LOG_RX.match(artifact.rel):
            yield from self._parse_output_log(artifact)
        elif dev and dev.group(1) == "chat":
            yield from self._parse_dev_chat(artifact)
        elif dev:
            yield from self._parse_tokens(artifact)
        elif STATE_RX.match(artifact.rel):
            yield from self._parse_state(artifact, opts)

    # ---- agent tasks (Roo fork) ------------------------------------------------

    def _global_state(self, db: Path) -> tuple[object, list[str]]:
        """The extension's global state from `state.vscdb`, and problems."""
        try:
            st = db.lstat()
        except OSError:
            return None, []
        key = (str(db), st.st_mtime_ns, st.st_size)
        if key not in self._state:
            self._state[key] = read_item(db, EXTENSION_ID)
        return self._state[key]

    def history_item(self, task_dir: Path, root: Path, task_id: str) -> dict | None:
        state = self._global_state(root.parent / "state.vscdb")[0]
        items = state.get("taskHistory") if isinstance(state, dict) else None
        for e in items if isinstance(items, list) else []:
            if isinstance(e, dict) and str(e.get("id")) == task_id:
                return e
        return None

    def parse_task_file(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        name = artifact.disk_path.name.lower()
        if name in API_FILES and (artifact.disk_path.parent / UI_FILE).is_file():
            # ui_messages.json holds the transcript; the API history alone
            # holds the permission decisions.
            yield from self._api_permission_rows(artifact)
            return
        yield from super().parse_task_file(artifact, opts)

    def _api_permission_rows(self, artifact: Artifact) -> Iterator[Row]:
        ctx = self.context(artifact)
        ui = self.cached_json(artifact.disk_path.parent / UI_FILE)
        asks = sorted(
            m["ts"]
            for m in (ui if isinstance(ui, list) else [])
            if isinstance(m, dict)
            and isinstance(m.get("ts"), (int, float))
            and str(m.get("ask") or m.get("say") or "") in TOOL_USE_KINDS
        )
        errors: list = []
        for n, msg in iter_json_array(artifact.disk_path, errors):
            if not isinstance(msg, dict) or msg.get("role") != "user":
                continue
            content = msg.get("content")
            ts = msg.get("ts")
            name = ""
            for b in content if isinstance(content, list) else []:
                text = b.get("text") if isinstance(b, dict) and b.get("type") == "text" else None
                if not isinstance(text, str):
                    continue
                hit = RESULT_RX.match(text.strip())
                if hit:
                    name = hit.group(1)
                    continue
                decision = permission_decision(text)
                if not decision:
                    continue
                before = [t for t in asks if isinstance(ts, (int, float)) and t <= ts]
                row = self._row(artifact, ctx, n, to_utc(ts) or ctx.start)
                row.turn_type = "system"
                row.tool_name = name
                row.tool_use_id = str(before[-1]) if before else ""
                row.text = "permission decision: " + decision
                yield row
        yield from error_rows(self, artifact, errors, ctx.task_id, ctx.project_path)

    def _parse_state(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        state, problems = self._global_state(artifact.disk_path)
        if isinstance(state, dict):
            items = state.get("taskHistory")
            for n, item in enumerate(items if isinstance(items, list) else [], 1):
                if not isinstance(item, dict):
                    continue
                row = self.history_row(artifact, item, n, opts)
                extra = []
                if item.get("number") not in (None, ""):
                    extra.append("number=%s" % item["number"])
                text = row.text + (" " + " ".join(extra) if extra else "")
                creator = item.get("creatorModeConfig")
                if isinstance(creator, dict) and creator:
                    text += " | creator mode: newProjectType=%s newProjectPath=%s" % (
                        creator.get("newProjectType") or "-",
                        creator.get("newProjectPath") or "-",
                    )
                row.text = compact(text)
                yield row
            mtime = file_mtime(artifact)
            for key in STANDING_KEYS:
                if key not in state or state[key] is None:
                    continue
                row = self.base_row(artifact)
                row.timestamp_utc = mtime
                row.turn_type = "system"
                row.text = "permission setting: %s=%s (from state.vscdb %s, file mtime)" % (
                    key,
                    setting_value(state[key]),
                    EXTENSION_ID,
                )
                yield row
        elif state is not None and not problems:
            problems = ["%s global state is not a JSON object" % EXTENSION_ID]
        yield from error_rows(self, artifact, [(0, p, "") for p in problems])

    def api_content_rows(
        self, message: dict, position: int, base_turn: str, include_thinking: bool
    ) -> Iterator[tuple[str, str, str, str]]:
        content = message.get("content")
        if base_turn == "assistant":
            k = 0
            for turn, text, name, tid in content_rows(content, base_turn, include_thinking):
                if turn != "assistant":
                    yield turn, text, name, tid
                    continue
                for t, body, tool in xml_blocks(text, include_thinking):
                    if t == "tool_use":
                        k += 1
                        tid = str(position) if k == 1 else "%d.%d" % (position, k)
                    yield t, body, tool, tid if t == "tool_use" else ""
            return
        if base_turn != "user" or not isinstance(content, list):
            yield from content_rows(content, base_turn, include_thinking)
            return
        result: list[str] | None = None
        name = ""

        decision = ""

        def flush() -> list[tuple[str, str, str, str]]:
            # the result, then the permission decision its text records
            if result is None:
                return []
            out = [("tool_result", "\n".join(x for x in result if x), name, str(position - 1))]
            if decision:
                out.append(("system", "permission decision: " + decision, name, str(position - 1)))
            return out

        for b in content:
            text = b.get("text") if isinstance(b, dict) and b.get("type") == "text" else None
            if isinstance(text, str):
                m = RESULT_RX.match(text.strip())
                notice = NOTICE_RX.match(text.strip())
                hit = m or notice
                if hit:
                    yield from flush()
                    name = hit.group(1)
                    result = [] if m else [text.strip()]
                    decision = ""
                    continue
                if text.lstrip().startswith("<environment_details>"):
                    yield from flush()
                    result = None
                    yield "system", text.strip(), "", ""
                    continue
                if result is not None:
                    if not result and not decision:
                        decision = permission_decision(text)
                    result.append(text)
                    continue
                t = TASK_RX.match(text)
                if t:
                    text = t.group(1)
                if text.strip():
                    yield "user", text, "", ""
                continue
            rows = list(content_rows([b], base_turn, include_thinking))
            if result is not None:
                result.extend(r[1] for r in rows)
            else:
                yield from rows
        yield from flush()

    # ---- chat sessions (Continue fork) -----------------------------------------

    def _parse_session(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        raw = read_text(artifact.disk_path)
        if raw is None:
            row = self.base_row(artifact)
            row.turn_type = "system"
            row.text = "parser: unreadable session file"
            yield row
            return
        sess, problem = load_session(raw)
        session_id = sess.get("sessionId")
        if not session_id:
            m = SESSION_RX.match(artifact.rel)
            assert m is not None  # wants() accepted only matching paths
            session_id = m.group(1)
        session_id = str(session_id)
        entry = self._continue._index(artifact.disk_path.parent).get(session_id, {})
        ts = to_utc(entry.get("dateCreated"))
        project = str(sess.get("workspaceDirectory") or entry.get("workspaceDirectory") or "")
        history = sess.get("history")
        if not isinstance(history, list):
            history = []
        search = sess.get("perplexityHistory")
        if not isinstance(search, list):
            search = []

        def base(n: int, turn: str, text, model: str = "") -> Row:
            row = self.base_row(artifact)
            row.source_line = n
            row.timestamp_utc = ts
            row.session_id = session_id
            row.project_path = project
            row.turn_type = turn
            row.model = model
            row.text = compact(text)
            return row

        bits = ["session start: %s" % (sess.get("title") or entry.get("title") or "")]
        if entry.get("integrationType"):
            bits.append("integration=%s" % entry["integrationType"])
        bits.append("history=%d perplexityHistory=%d" % (len(history), len(search)))
        if not ts:
            bits.append("dateCreated unknown")
        yield base(0, "system", " | ".join(bits))

        models: dict = {}
        for i, item in enumerate(history + search, 1):
            if not isinstance(item, dict) or not isinstance(item.get("message"), dict):
                continue
            msg = item["message"]
            role = msg.get("role")
            text = message_text(msg.get("content"))
            model = ""
            for pl in item.get("promptLogs") or []:
                co = pl.get("completionOptions") if isinstance(pl, dict) else None
                if isinstance(co, dict) and co.get("model"):
                    model = str(co["model"])
                    change = track_change("model", models, session_id, model)
                    if change:
                        yield base(i, "system", change, model)
            if role == "user":
                ctx = [
                    str(c.get("description") or c.get("name") or "")
                    for c in item.get("contextItems") or []
                    if isinstance(c, dict)
                ]
                ctx = [c for c in ctx if c]
                if ctx:
                    text = "%s\n[context: %s]" % (text, ", ".join(ctx))
                if text:
                    yield base(i, "user", text)
            elif role == "assistant":
                cites = [
                    str(c.get("url") or c.get("title") or "")
                    for c in item.get("citations") or []
                    if isinstance(c, dict)
                ]
                cites = [c for c in cites if c]
                if cites:
                    text = "%s\n[citations: %s]" % (text, ", ".join(cites))
                if text:
                    yield base(i, "assistant", text, model)
            elif text:
                yield base(
                    i,
                    "system",
                    text if role == "system" else "%s: %s" % (role or "unknown", text),
                    model,
                )

        if problem:
            yield base(0, "system", "parser: " + problem)

    # ---- chat use outside the session files (secondary sources) ----------------

    def _parse_output_log(self, artifact: Artifact) -> Iterator[Row]:
        raw = read_text(artifact.disk_path)
        if raw is None:
            yield from error_rows(self, artifact, [(0, "unreadable output channel log", "")])
            return
        errors: list = []
        models: dict = {}
        model = ""
        chat = False
        starts = [m.end() for m in LOG_SEPARATOR_RX.finditer(raw)]
        # Two lines of 74 `=` and their newlines before every write.
        preamble = raw[: starts[0] - 2 * 75] if starts else raw
        if preamble.strip():
            errors.append(
                (1, "unparseable record (before the first separator)", preamble.rstrip("\n"))
            )
        for i, start in enumerate(starts):
            end = starts[i + 1] - 2 * 75 if i + 1 < len(starts) else len(raw)
            record = raw[start:end]
            line = raw.count("\n", 0, start) + 1

            def row(turn: str, text: str, model: str = "", line: int = line) -> Row:
                r = self.base_row(artifact)
                r.source_line = line
                r.turn_type = turn
                r.model = model
                r.text = compact(text)
                return r

            if record.startswith("Settings:\n"):
                header, rule, prompt = record.partition(LOG_RULE)
                if not rule:
                    errors.append(
                        (line, "unparseable record (no prompt rule)", record.rstrip("\n"))
                    )
                    continue
                settings = dict(ln.split(": ", 1) for ln in header.splitlines()[1:] if ": " in ln)
                model = settings.get("model", "")
                change = track_change("model", models, "", model)
                if change:
                    yield row("system", change, model)
                turn, text = prompt_turn(prompt)
                chat = turn == "user"
                yield row(turn, text, model)
            elif record.startswith("Completion:\n"):
                reply = record[len("Completion:\n") :].strip()
                if chat:
                    yield row("assistant", reply, model)
                else:
                    yield row("system", "model completion: " + reply, model)
            else:
                errors.append(
                    (
                        line,
                        "unparseable record (not a Settings: or Completion: write)",
                        record.rstrip("\n"),
                    )
                )
        yield from error_rows(self, artifact, errors)

    def _parse_dev_chat(self, artifact: Artifact) -> Iterator[Row]:
        errors: list = []
        index = self._continue._index(artifact.disk_path.parent.parent / "sessions")
        for n, rec in iter_jsonl(artifact.disk_path, errors):
            options = rec.get("completionOptions")
            model = str(options.get("model") or "") if isinstance(options, dict) else ""
            session_id = str(rec.get("sessionId") or "")
            project = str(index.get(session_id, {}).get("workspaceDirectory") or "")
            texts = []
            if isinstance(rec.get("prompt"), str):
                texts.append(prompt_turn(rec["prompt"]))
            if isinstance(rec.get("completion"), str):
                texts.append(("assistant", rec["completion"]))
            if isinstance(rec.get("feedback"), bool):
                texts.append(
                    (
                        "system",
                        "user feedback: %s (from dev_data/chat.jsonl)"
                        % setting_value(rec["feedback"]),
                    )
                )
            for turn, text in texts:
                row = self.base_row(artifact)
                row.source_line = n
                row.session_id = session_id
                row.project_path = project
                row.turn_type = turn
                row.model = model
                row.text = compact(text)
                if row.text:
                    yield row
        yield from error_rows(self, artifact, errors)

    def _parse_tokens(self, artifact: Artifact) -> Iterator[Row]:
        errors: list = []
        for n, rec in iter_jsonl(artifact.disk_path, errors):
            row = self.base_row(artifact)
            row.source_line = n
            row.turn_type = "system"
            row.model = str(rec.get("model") or "")
            row.text = "tokens generated: " + " ".join(
                "%s=%s" % (k, setting_value(rec.get(k)) if k in rec else "-")
                for k in ("model", "provider", "promptTokens", "generatedTokens")
            )
            yield row
        yield from error_rows(self, artifact, errors)


__all__ = ["PearAiParser", "permission_decision", "prompt_turn", "xml_blocks"]
