"""Aider chat, input and LLM history files.

Validated against source, Aider-AI/aider at 5dc9490 (`aider/io.py`,
`aider/utils.py`, `aider/coders/base_coder.py`) and prompt_toolkit's
`FileHistory`, with a synthetic fixture; see `research/aider.md`.

Aider writes into the git root of the repository it runs in (else the
working directory), so these files usually arrive through the collector's
project catalog with the project directory as the home, and
`artifact.rel` is the bare file name. Collectors from 1.12.0 attribute them
to `aider` when the project catalog names it; earlier ones recorded agent
`project`, which the analyzer re-attributes from its bundled project
catalog, and a file the catalog leaves to `project` is offered to every
parser. Either way this parser takes it and labels the rows `aider`. A
history file directly in a home is
attributed to `aider` by the main catalog. Either way `project_path` is the
directory holding the file. Files:

* `.aider.chat.history.md`, appended markdown. `# aider chat started at
  YYYY-MM-DD HH:MM:SS` opens a session; `#### ` lines are user input (one
  per input line, `#### <blank>` for empty input, slash commands included);
  `> ` blockquote lines are tool and system output (applied edits, commits,
  errors; `>>>>>>> REPLACE` is not one); anything else is assistant
  markdown, SEARCH/REPLACE blocks included. Consecutive lines of one kind
  are one row.
* `.aider.input.history`, prompt_toolkit `FileHistory`: `# YYYY-MM-DD
  HH:MM:SS.ffffff` then one `+<line>` per input line.
* `.aider.llm.history`, only with `--llm-history-file`: `TO LLM
  YYYY-MM-DDTHH:MM:SS` followed by `-------`-separated messages whose lines
  are prefixed with the upper-case role, and `LLM RESPONSE <ts>` followed by
  `ASSISTANT <line>` lines.

Every timestamp in these files is host local time with no zone, and the
collection does not record the host's zone, so they are emitted as if they
were UTC; correct them by the host's offset. The session id is synthesised
as `<path of .aider.chat.history.md>#<header timestamp>`. Chat history rows
take the session header's time, or, from a user prompt on, the time of the
matching `.aider.input.history` entry (same text, between this header and
the next). Input and LLM history rows are assigned to the last session
header at or before their own time when the chat history sits beside them.
No git branch or tool call id is recorded.

The model is named only in the chat history's announcement lines, written
at startup and again after each `/model`, `/weak-model`, `/editor-model` or
`/chat-mode` switch (`base_coder.py` `get_announcements`): `Model: <name>
with <format> edit format[, ...]`, or `Main model: ...` when a separate
weak model is in use, `Editor model: <name> with <format> edit format` in
architect mode, and `Weak model: <name>`. A blockquote run that holds a
main-model line is read for them, and after its `tool_result` row the
parser yields `model: <name>` at the first announcement of a session and
`model: <old> -> <new>` on each later one that names another model, with
` (editor model)` or ` (weak model)` appended for those two roles. A
`Model:` line means the weak model is the main model: it sets the weak
model with no row of its own, unless it replaces a separate weak model,
so a later `Weak model:` line reads `model: <main> -> <weak> (weak
model)`. The `model` column of such a row is the new model; other rows leave
it empty. Each `confirm_ask` line (`io.py`), `<question> (Y)es/(N)o[/(A)ll]
[/(S)kip all][/(D)on't ask again] [<default>]: <answer>`, with the answer's
first letter in lower case, yields `permission decision: <yes|no|all|skip
all|don't ask again> (<question>) answer=<letter> default=<default>` after
the run's `tool_result` row; a `y` or `n` answer adds `; may be automatic
(--yes-always)`, because under `--yes-always` Aider writes the same line
without asking (`y`, or `n` for a question that needs an explicit yes,
such as `Run shell command?`). The subject (the command, path or URL) is
the blockquote text before the question in the same `tool_result` row. A
question declined silently after "Don't ask again" leaves no line. Both
row kinds are source-derived (Aider-AI/aider at 5dc9490) and not observed
on any real install. Each `TO LLM` request
becomes one `system` row naming the message count and the last user
message; the full prompt is at `source_file:source_line`. A non-blank
input or LLM history line that fits neither format is its own `system`
row carrying the line in full (`error_rows`, issue 136).

The chat history is the primary store; the input and LLM histories are
secondary sources (`secondary()`, issue 122), read on every run beside it.
Aider writes the same prompt to both the input history (prompt_toolkit's
`FileHistory`, `aider/io.py` `add_to_input_history`) and the chat history
(`user_input`), so an input-history row and the chat row it timed carry
the same text, session id, project path and timestamp and pair exactly:
the input-history row is dropped. One the chat history lacks is kept: an
entry written after a chat-history write error, which turns chat logging
off for the rest of the run (`append_chat_history`), a `/run <command>`
entry Aider adds for a shell command it suggested
(`base_coder.py` `handle_shell_commands`), or a prompt whose chat history
was deleted or written elsewhere with `--chat-history-file`. Both files
record each event's own time, so the default two-second window applies.
The LLM history rarely pairs: its `system` rows summarise a request no
chat row repeats, and an `LLM RESPONSE` row is stamped when the response
arrived, while the chat history's assistant row takes the prompt's time
and may hold several such responses or be split by blockquote lines.
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Callable, Iterator
from pathlib import Path

from ..inputs import Artifact
from ..model import Row, compact
from ..timeutil import to_utc
from .base import Options, Parser, error_rows, line_text

CHAT = ".aider.chat.history.md"
INPUT = ".aider.input.history"
LLM = ".aider.llm.history"
FILE_RX = re.compile(r"^(?:.*/)?(\.aider\.(?:chat\.history\.md|input\.history|llm\.history))$")
HEADER_RX = re.compile(r"^# aider chat started at (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s*$")
INPUT_TS_RX = re.compile(r"^# (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(?:\.\d+)?)\s*$")
LLM_RX = re.compile(r"^(TO LLM|LLM RESPONSE) (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)\s*$")
ROLE_TURN = {"USER": "user", "ASSISTANT": "assistant", "SYSTEM": "system"}
# Announcement lines (`base_coder.py` `get_announcements`): the main model with
# its edit format and options, the editor model in architect mode, the weak
# model when it is not the main model.
MAIN_MODEL_RX = re.compile(r"^(?:Main model|Model): (\S.*?) with (\S+) edit format(?:, .*)?$")
EDITOR_MODEL_RX = re.compile(r"^Editor model: (\S.*?) with (\S+) edit format$")
WEAK_MODEL_RX = re.compile(r"^Weak model: (\S.*)$")
# A `confirm_ask` line (`io.py`): the question, its options, the default in
# brackets, and the first letter of the answer, lower case.
CONFIRM_RX = re.compile(
    r"^(?P<question>.+?) \(Y\)es/\(N\)o(?:/\(A\)ll)?(?:/\(S\)kip all)?"
    r"(?:/\(D\)on't ask again)? \[(?P<default>[^\]]*)\]: (?P<answer>[ynasd])$"
)
DECISION = {"y": "yes", "n": "no", "a": "all", "s": "skip all", "d": "no, don't ask again"}


def _lines(path: Path) -> Iterator[tuple[int, str]]:
    with open(path, "rb") as handle:
        for line_number, raw in enumerate(handle, 1):
            yield line_number, line_text(raw)


def _norm(text: str) -> str:
    return " ".join(text.split())


def sibling(original: str, name: str) -> str:
    """The path of `name` in the directory holding `original`, keeping the
    source host's separator."""
    i = max(original.rfind("/"), original.rfind("\\"))
    if i < 0:
        return name
    return original[: i + 1] + name


def project_dir(original: str) -> str:
    i = max(original.rfind("/"), original.rfind("\\"))
    return original[:i] if i > 0 else original[: i + 1]


def read_input_history(path: Path, errors: list | None = None) -> list[tuple[int, str, str]]:
    """(line, local timestamp, text) per prompt_toolkit FileHistory entry.
    A non-blank line that is neither a timestamp nor a `+` entry line is
    appended to `errors` as (line, message, the line less its terminator)."""
    out: list[list] = []
    for line_number, line in _lines(path):
        match = INPUT_TS_RX.match(line)
        if match:
            out.append([line_number, match.group(1), []])
        elif line.startswith("+"):
            if not out:
                out.append([line_number, "", []])
            out[-1][2].append(line[1:])
        elif line.strip() and errors is not None:
            errors.append((line_number, "unparseable line (not a FileHistory line)", line))
    return [(entry[0], entry[1], "\n".join(entry[2])) for entry in out]


def read_headers(path: Path) -> list[str]:
    """Session header timestamps of a chat history, in file order."""
    if not path.is_file() or path.is_symlink():
        return []
    return [
        match.group(1) for _, line in _lines(path) for match in [HEADER_RX.match(line)] if match
    ]


class AiderParser(Parser):
    agent = "aider"
    name = "aider"
    has_secondary = True

    def wants(self, artifact: Artifact) -> bool:
        return bool(FILE_RX.match(artifact.rel))

    def secondary(self, artifact: Artifact) -> bool:
        match = FILE_RX.match(artifact.rel)
        return bool(match) and match.group(1) != CHAT

    def base_row(self, artifact: Artifact) -> Row:
        row = Row(
            host=artifact.home.host,
            user=artifact.home.user,
            agent="aider",
            source_file=artifact.original,
        )
        row.project_path = project_dir(artifact.original)
        return row

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        match = FILE_RX.match(artifact.rel)
        assert match is not None  # wants() accepted only matching paths
        kind = match.group(1)
        if kind == CHAT:
            yield from self._parse_chat(artifact, opts)
        elif kind == INPUT:
            yield from self._parse_input(artifact, opts)
        else:
            yield from self._parse_llm(artifact, opts)

    def _session_for(self, artifact: Artifact) -> Callable[[str], str]:
        """Map a local timestamp to the session id of the last chat header at
        or before it, using the chat history beside this file."""
        headers = sorted(read_headers(artifact.disk_path.parent / CHAT))
        chat = sibling(artifact.original, CHAT)

        def lookup(timestamp: str) -> str:
            if not timestamp or not headers:
                return ""
            i = bisect.bisect_right(headers, timestamp.replace("T", " ")[:19])
            return "%s#%s" % (chat, headers[i - 1]) if i else ""

        return lookup

    # ---- .aider.chat.history.md ------------------------------------------------

    def _parse_chat(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        headers = read_headers(artifact.disk_path)
        inputs = []
        input_path = artifact.disk_path.parent / INPUT
        if input_path.is_file() and not input_path.is_symlink():
            try:
                inputs = [entry for entry in read_input_history(input_path) if entry[1]]
            except OSError:
                inputs = []
        next_input = 0
        models: dict[str, str] = {}
        session_id = ""
        header = ""
        next_header = ""
        header_count = 0
        timestamp = ""
        kind = ""
        buffer: list[str] = []
        line_numbers: list[int] = []
        start = 0

        def flush() -> Iterator[Row]:
            nonlocal next_input, timestamp
            text = "\n".join(buffer).strip()
            if not text or not kind:
                return
            if kind == "user" and header:
                for j in range(next_input, len(inputs)):
                    entry_timestamp = inputs[j][1]
                    if entry_timestamp[:19] < header:
                        continue
                    if next_header and entry_timestamp[:19] >= next_header:
                        break
                    if _norm(inputs[j][2]) == _norm(text):
                        timestamp = to_utc(entry_timestamp)
                        next_input = j + 1
                        break
            row = self.base_row(artifact)
            row.source_line = start
            row.timestamp_utc = timestamp
            row.session_id = session_id
            row.turn_type = {"user": "user", "tool": "tool_result", "assistant": "assistant"}[kind]
            row.text = compact(text)
            yield row
            if kind == "tool":
                yield from self._tool_system_rows(
                    artifact, buffer, line_numbers, timestamp, session_id, models
                )

        for line_number, line in _lines(artifact.disk_path):
            match = HEADER_RX.match(line)
            if match:
                yield from flush()
                kind, buffer, line_numbers = "", [], []
                models = {}
                header = match.group(1)
                header_count += 1
                next_header = headers[header_count] if header_count < len(headers) else ""
                timestamp = to_utc(header)
                session_id = "%s#%s" % (artifact.original, header)
                row = self.base_row(artifact)
                row.source_line = line_number
                row.timestamp_utc = timestamp
                row.session_id = session_id
                row.turn_type = "system"
                row.text = "aider chat started at %s (local time)" % header
                yield row
                continue
            if line.startswith("#### ") or line.rstrip() == "####":
                new, content = "user", line[5:]
            elif line.startswith("> ") or line == ">":
                new, content = "tool", line[2:]
            else:
                new, content = "assistant", line
            if new != kind:
                yield from flush()
                kind, buffer, line_numbers, start = new, [], [], line_number
            if not any(buffered.strip() for buffered in buffer):
                start = line_number
            buffer.append(content.rstrip() if new != "assistant" else content)
            line_numbers.append(line_number)
        yield from flush()

    def _tool_system_rows(
        self,
        artifact: Artifact,
        lines: list[str],
        line_numbers: list[int],
        timestamp: str,
        session_id: str,
        models: dict[str, str],
    ) -> Iterator[Row]:
        """The `model:` and `permission decision:` rows of one blockquote run,
        after its `tool_result` row. `models` holds the session's main, editor
        and weak model so far and is updated in place."""
        announced = any(MAIN_MODEL_RX.match(text_line) for text_line in lines)
        for line_number, line in zip(line_numbers, lines, strict=True):
            changes: list[tuple[str, str, str, bool]] = []
            match = MAIN_MODEL_RX.match(line) if announced else None
            if match:
                changes.append(("main", match.group(1), "", True))
                if line.startswith("Model: "):
                    # no separate weak model: the weak model is the main model,
                    # a row only when it replaces a separate one
                    changes.append(("weak", match.group(1), " (weak model)", False))
            elif announced and (match := EDITOR_MODEL_RX.match(line)):
                changes.append(("editor", match.group(1), " (editor model)", True))
            elif announced and (match := WEAK_MODEL_RX.match(line)):
                changes.append(("weak", match.group(1), " (weak model)", True))
            for role, name, label, first in changes:
                old = models.get(role, "")
                models[role] = name
                if old != name and (old or first):
                    text = "model: %s%s" % ("%s -> %s" % (old, name) if old else name, label)
                    yield self._system_row(
                        artifact, line_number, timestamp, session_id, text, model=name
                    )
            if changes:
                continue
            match = CONFIRM_RX.match(line)
            if match:
                answer = match.group("answer")
                text = "permission decision: %s (%s) answer=%s default=%s" % (
                    DECISION[answer],
                    match.group("question"),
                    answer,
                    match.group("default"),
                )
                if answer in "yn":
                    text += "; may be automatic (--yes-always)"
                yield self._system_row(artifact, line_number, timestamp, session_id, text)

    def _system_row(
        self,
        artifact: Artifact,
        line: int,
        timestamp: str,
        session_id: str,
        text: str,
        model: str = "",
    ) -> Row:
        row = self.base_row(artifact)
        row.source_line = line
        row.timestamp_utc = timestamp
        row.session_id = session_id
        row.turn_type = "system"
        row.model = model
        row.text = text
        return row

    # ---- .aider.input.history --------------------------------------------------

    def _parse_input(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        errors: list = []
        session_for = self._session_for(artifact)
        for line_number, timestamp, text in read_input_history(artifact.disk_path, errors):
            row = self.base_row(artifact)
            row.source_line = line_number
            row.timestamp_utc = to_utc(timestamp)
            row.session_id = session_for(timestamp)
            row.turn_type = "user"
            row.text = compact(text)
            yield row
        yield from error_rows(self, artifact, errors)

    # ---- .aider.llm.history ----------------------------------------------------

    def _parse_llm(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        errors: list = []
        session_for = self._session_for(artifact)
        block: dict | None = None

        def emit(current_block: dict | None) -> Iterator[Row]:
            if current_block is None:
                return
            row = self.base_row(artifact)
            row.source_line = current_block["line"]
            row.timestamp_utc = to_utc(current_block["ts"])
            row.session_id = session_for(current_block["ts"])
            if current_block["kind"] == "LLM RESPONSE":
                text = "\n".join(
                    _strip_role(response_line, "ASSISTANT")
                    for response_line in current_block["lines"]
                ).strip()
                if not text:
                    return
                row.turn_type = "assistant"
                row.text = compact(text)
                yield row
                return
            messages: list[tuple[str, list[str]]] = []
            for text_line in current_block["lines"]:
                if text_line == "-------":
                    messages.append(("", []))
                elif messages:
                    role, body = messages[-1]
                    if not role:
                        role = text_line.split(" ", 1)[0]
                        messages[-1] = (role, body)
                    body.append(_strip_role(text_line, role))
            counts: dict[str, int] = {}
            last_user = ""
            for role, body in messages:
                counts[role] = counts.get(role, 0) + 1
                if role == "USER":
                    last_user = "\n".join(body)
            row.turn_type = "system"
            row.text = compact(
                "TO LLM: %d message(s) (%s); last user message: %s"
                % (
                    len(messages),
                    ", ".join("%s %d" % role_count for role_count in counts.items()),
                    last_user,
                ),
            )
            yield row

        for line_number, line in _lines(artifact.disk_path):
            match = LLM_RX.match(line)
            if match:
                yield from emit(block)
                block = {
                    "kind": match.group(1),
                    "ts": match.group(2),
                    "line": line_number,
                    "lines": [],
                }
            elif block is not None:
                block["lines"].append(line)
            elif line.strip():
                errors.append(
                    (
                        line_number,
                        "unparseable line (text before the first TO LLM / LLM RESPONSE marker)",
                        line,
                    )
                )
        yield from emit(block)
        yield from error_rows(self, artifact, errors)


def _strip_role(line: str, role: str) -> str:
    if line == role:
        return ""
    if role and line.startswith(role + " "):
        return line[len(role) + 1 :]
    return line
