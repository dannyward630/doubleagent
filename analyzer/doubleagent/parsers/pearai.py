"""Parse PearAI chat sessions (a Continue fork) and agent tasks (a Roo Code fork).

Follows `research/pearai.md`. Validated against source, trypear/pearai-submodule
at 51eceef6, trypear/PearAI-Roo-Code at 0b6df736 (Roo Code 3.15) and
trypear/pearai-app at d930f023, with a synthetic fixture; no real install. Both
forks are older snapshots of their upstreams, so the shapes differ from
`continue_dev.py` and `roo_code.py`. Files read:

- `.pearai/sessions/<sessionId>.json`: `sessionId`, `title`,
  `workspaceDirectory`, `history[]` and `perplexityHistory[]`, each item's
  `message` (`role`, `content`), `contextItems[]`, `citations[]` and
  `promptLogs[].completionOptions.model`. Every row takes the index's
  `dateCreated`; `source_line` is the item's position across both lists.
- `.pearai/sessions/sessions.json`, the index, read through
  `continue_dev.read_index`; it yields rows only for what it loses.
- `User/globalStorage/pearai.pearai-roo-cline/tasks/<taskId>/` task files,
  read by the shared mapping of `cline_legacy.py`; tool calls are XML tags in
  the assistant text (`xml_blocks`) and have no id, so `tool_use_id` is the
  message's position. Results that open with a `PERMISSION_TEXTS` prefix give
  `permission decision:` rows.
- `User/globalStorage/state.vscdb`, row `pearai.pearai-roo-cline`:
  `taskHistory[]` (one row per task, so a task whose directory is gone still
  shows) and the `STANDING_KEYS` as `permission setting:` rows.
- The `PearAI` output channel log and `.pearai/dev_data/chat.jsonl`,
  secondary sources (files repeating the sessions' prompts and replies) with
  no time; `.pearai/dev_data/tokens_generated.jsonl`, one `tokens generated:`
  row per request.

No git branch is recorded; the chat surface has no tools or permission state.
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
    """Return the decision a Roo 3.15 tool result block records, or ""."""
    text = text.lstrip()
    for prefix, decision in PERMISSION_TEXTS:
        if text.startswith(prefix):
            return decision
    return ""


def prompt_turn(prompt: str) -> tuple[str, str]:
    """Return (turn_type, text) for a logged prompt.

    A prompt in `_formatChatMessages` form gives its last `<user>` block as
    `user`; any other prompt is a `system` row `model request: <prompt>`.
    """
    blocks = list(ROLE_BLOCK_RX.finditer(prompt))
    if not blocks or blocks[0].start() != 0:
        return "system", "model request: " + prompt
    users = [i for i, match in enumerate(blocks) if match.group(1) == "user"]
    if not users:
        return "system", "model request: " + prompt
    i = users[-1]
    end = blocks[i + 1].start() if i + 1 < len(blocks) else len(prompt)
    return "user", prompt[blocks[i].end() : end]


def xml_blocks(text: str, include_thinking: bool) -> Iterator[tuple[str, str, str]]:
    """Yield (turn_type, text, tool_name) for Roo assistant text with XML tool tags."""
    pos = 0
    for match in BLOCK_RX.finditer(text):
        before = text[pos : match.start()].strip()
        if before:
            yield "assistant", before, ""
        pos = match.end()
        tag, body = match.group(1), match.group(2)
        if tag == "thinking":
            if include_thinking and body.strip():
                yield "thinking", body.strip(), ""
            continue
        params = [value.strip() for _, value in PARAM_RX.findall(body) if value.strip()]
        yield "tool_use", " | ".join(params) if params else body.strip(), tag
    rest = text[pos:].strip()
    if rest:
        yield "assistant", rest, ""


class PearAiParser(LegacyTaskParser):
    """Parse PearAI's chat sessions, agent tasks, editor state and chat logs."""

    agent = "pearai"
    name = "pearai"
    has_secondary = True
    ROOT = ROOT
    PROJECT_KEY = "workspace"

    def __init__(self) -> None:
        """Start with a Continue parser for its index reader and an empty state cache."""
        super().__init__()
        self._continue = ContinueParser()  # for its cached sessions.json reader
        self._state: dict[tuple, tuple[object, list[str]]] = {}

    def wants(self, artifact: Artifact) -> bool:
        """Return True for a session (the index included), task, log, dev_data or state file."""
        rel = artifact.rel
        return bool(
            SESSION_RX.match(rel)
            or self.task_match(artifact)
            or LOG_RX.match(rel)
            or DEVDATA_RX.match(rel)
            or STATE_RX.match(rel)
        )

    def secondary(self, artifact: Artifact) -> bool:
        """Return True for the output channel log or `dev_data/chat.jsonl`."""
        match = DEVDATA_RX.match(artifact.rel)
        return bool(LOG_RX.match(artifact.rel) or (match and match.group(1) == "chat"))

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        """Yield the rows of one PearAI file."""
        match = SESSION_RX.match(artifact.rel)
        dev = DEVDATA_RX.match(artifact.rel)
        if match and match.group(1) + ".json" == INDEX_NAME:
            errors = self._continue.index_errors(artifact.disk_path)
            yield from error_rows(self, artifact, errors)
        elif match:
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

    def _global_state(self, database: Path) -> tuple[object, list[str]]:
        """Return the extension's global state from `state.vscdb`, and its problems."""
        try:
            stat = database.lstat()
        except OSError:
            return None, []
        key = (str(database), stat.st_mtime_ns, stat.st_size)
        if key not in self._state:
            self._state[key] = read_item(database, EXTENSION_ID)
        return self._state[key]

    def history_item(self, task_dir: Path, root: Path, task_id: str) -> dict | None:
        """Return the task's `taskHistory[]` entry from the editor's global state, or None."""
        state = self._global_state(root.parent / "state.vscdb")[0]
        items = state.get("taskHistory") if isinstance(state, dict) else None
        for entry in items if isinstance(items, list) else []:
            if isinstance(entry, dict) and str(entry.get("id")) == task_id:
                return entry
        return None

    def parse_task_file(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        """Yield a task file's rows; beside `ui_messages.json`, the API history's decisions only."""
        name = artifact.disk_path.name.lower()
        if name in API_FILES and (artifact.disk_path.parent / UI_FILE).is_file():
            # ui_messages.json holds the transcript; the API history alone
            # holds the permission decisions.
            yield from self._api_permission_rows(artifact)
            return
        yield from super().parse_task_file(artifact, opts)

    def _api_permission_rows(self, artifact: Artifact) -> Iterator[Row]:
        ctx = self.context(artifact)
        ui_messages = self.cached_json(artifact.disk_path.parent / UI_FILE)
        asks = sorted(
            message["ts"]
            for message in (ui_messages if isinstance(ui_messages, list) else [])
            if isinstance(message, dict)
            and isinstance(message.get("ts"), (int, float))
            and str(message.get("ask") or message.get("say") or "") in TOOL_USE_KINDS
        )
        errors: list = []
        for index, msg in iter_json_array(artifact.disk_path, errors):
            if not isinstance(msg, dict) or msg.get("role") != "user":
                continue
            content = msg.get("content")
            timestamp = msg.get("ts")
            name = ""
            for block in content if isinstance(content, list) else []:
                text = (
                    block.get("text")
                    if isinstance(block, dict) and block.get("type") == "text"
                    else None
                )
                if not isinstance(text, str):
                    continue
                hit = RESULT_RX.match(text.strip())
                if hit:
                    name = hit.group(1)
                    continue
                decision = permission_decision(text)
                if not decision:
                    continue
                before = [
                    ask for ask in asks if isinstance(timestamp, (int, float)) and ask <= timestamp
                ]
                row = self._row(artifact, ctx, index, to_utc(timestamp) or ctx.start)
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
            for index, item in enumerate(items if isinstance(items, list) else [], 1):
                if not isinstance(item, dict):
                    continue
                row = self.history_row(artifact, item, index, opts)
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
        yield from error_rows(self, artifact, [(0, problem, "") for problem in problems])

    def api_content_rows(
        self, msg: dict, n: int, base_turn: str, include_thinking: bool
    ) -> Iterator[tuple[str, str, str, str]]:
        """Yield (turn_type, text, tool_name, tool_use_id) for one API history message.

        Assistant text is split at its XML tool tags; a user message's
        `[<tool> ...] Result:` blocks become `tool_result` rows, each followed
        by the permission decision its text records.
        """
        content = msg.get("content")
        if base_turn == "assistant":
            k = 0
            for turn, text, name, tid in content_rows(content, base_turn, include_thinking):
                if turn != "assistant":
                    yield turn, text, name, tid
                    continue
                for kind, body, tool in xml_blocks(text, include_thinking):
                    if kind == "tool_use":
                        k += 1
                        tid = str(n) if k == 1 else "%d.%d" % (n, k)
                    yield kind, body, tool, tid if kind == "tool_use" else ""
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
            out = [("tool_result", "\n".join(part for part in result if part), name, str(n - 1))]
            if decision:
                out.append(("system", "permission decision: " + decision, name, str(n - 1)))
            return out

        for block in content:
            text = (
                block.get("text")
                if isinstance(block, dict) and block.get("type") == "text"
                else None
            )
            if isinstance(text, str):
                match = RESULT_RX.match(text.strip())
                notice = NOTICE_RX.match(text.strip())
                hit = match or notice
                if hit:
                    yield from flush()
                    name = hit.group(1)
                    result = [] if match else [text.strip()]
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
                task = TASK_RX.match(text)
                if task:
                    text = task.group(1)
                if text.strip():
                    yield "user", text, "", ""
                continue
            rows = list(content_rows([block], base_turn, include_thinking))
            if result is not None:
                result.extend(entry[1] for entry in rows)
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
            match = SESSION_RX.match(artifact.rel)
            assert match is not None  # wants() accepted only matching paths
            session_id = match.group(1)
        session_id = str(session_id)
        entry = self._continue._index(artifact.disk_path.parent).get(session_id, {})
        timestamp = to_utc(entry.get("dateCreated"))
        project = str(sess.get("workspaceDirectory") or entry.get("workspaceDirectory") or "")
        history = sess.get("history")
        if not isinstance(history, list):
            history = []
        search = sess.get("perplexityHistory")
        if not isinstance(search, list):
            search = []

        def base(line_number: int, turn: str, text, model: str = "") -> Row:
            row = self.base_row(artifact)
            row.source_line = line_number
            row.timestamp_utc = timestamp
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
        if not timestamp:
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
            for prompt_log in item.get("promptLogs") or []:
                options = (
                    prompt_log.get("completionOptions") if isinstance(prompt_log, dict) else None
                )
                if isinstance(options, dict) and options.get("model"):
                    model = str(options["model"])
                    change = track_change("model", models, session_id, model)
                    if change:
                        yield base(i, "system", change, model)
            if role == "user":
                ctx = [
                    str(context_item.get("description") or context_item.get("name") or "")
                    for context_item in item.get("contextItems") or []
                    if isinstance(context_item, dict)
                ]
                ctx = [label for label in ctx if label]
                if ctx:
                    text = "%s\n[context: %s]" % (text, ", ".join(ctx))
                if text:
                    yield base(i, "user", text)
            elif role == "assistant":
                cites = [
                    str(citation.get("url") or citation.get("title") or "")
                    for citation in item.get("citations") or []
                    if isinstance(citation, dict)
                ]
                cites = [label for label in cites if label]
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
        starts = [match.end() for match in LOG_SEPARATOR_RX.finditer(raw)]
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
                result = self.base_row(artifact)
                result.source_line = line
                result.turn_type = turn
                result.model = model
                result.text = compact(text)
                return result

            if record.startswith("Settings:\n"):
                header, rule, prompt = record.partition(LOG_RULE)
                if not rule:
                    errors.append(
                        (line, "unparseable record (no prompt rule)", record.rstrip("\n"))
                    )
                    continue
                settings = dict(
                    header_line.split(": ", 1)
                    for header_line in header.splitlines()[1:]
                    if ": " in header_line
                )
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
        for line_number, rec in iter_jsonl(artifact.disk_path, errors):
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
                row.source_line = line_number
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
        for line_number, rec in iter_jsonl(artifact.disk_path, errors):
            row = self.base_row(artifact)
            row.source_line = line_number
            row.turn_type = "system"
            row.model = str(rec.get("model") or "")
            row.text = "tokens generated: " + " ".join(
                "%s=%s" % (k, setting_value(rec.get(k)) if k in rec else "-")
                for k in ("model", "provider", "promptTokens", "generatedTokens")
            )
            yield row
        yield from error_rows(self, artifact, errors)


__all__ = ["PearAiParser", "permission_decision", "prompt_turn", "xml_blocks"]
