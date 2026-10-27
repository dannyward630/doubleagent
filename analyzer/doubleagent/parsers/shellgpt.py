"""ShellGPT chat and REPL sessions.

Validated against source, TheR1D/shell_gpt at a082bd5 (1.5.1) and the
pre-1.5.0 function-call shape at 6bd0bde, with a synthetic fixture; no real
install was used. See `research/shellgpt.md`.

Files: every file directly under a `chat_cache/` directory, at any depth.
ShellGPT keeps its chat cache in the temp directory, not the home
(`tempfile.gettempdir()/chat_cache`, before 0.9.0
`gettempdir()/shell_gpt/chat_cache`), so the catalog reaches it only on
Windows as `AppData/Local/Temp/chat_cache/<id>` or
`AppData/Local/Temp/shell_gpt/chat_cache/<id>`; a copied Linux or macOS
temp directory given as loose input matches by the same directory name. The
settings file, the function store and the response cache are read as
described at the end of this docstring; the roles under
`.config/shell_gpt/roles/` are not.

Each file is named by the chat id typed after `--chat` or `--repl` and holds
one single-line JSON array of OpenAI chat messages, rewritten in full on
every turn and cut to the system message plus the last `CHAT_CACHE_LENGTH`
messages. Fields read: `role`, `content`, `tool_calls[].{id,
function.{name, arguments}}` and `tool_call_id` (1.5.0 and later), and the
legacy `function_call.{name, arguments}` on assistant messages with
`{"role": "function", "name", "content"}` results (1.1.0 to 1.4.x).

Rows: `system`, `user` and `assistant` messages map to their role (an
assistant message with no content yields no row of its own); each
`tool_calls[]` entry is a `tool_use` whose text is the `shell_command`
argument when present, else the arguments; a `tool` message is a
`tool_result` joined on `tool_call_id`. A legacy `function_call` has no id,
so the parser synthesises `function_call_<array index>` and gives it to the
`function` message that immediately follows it, which is how ShellGPT itself
paired them. Nothing in the file records a time, model, working directory
or branch: those columns stay empty. The only time is the file's mtime,
which is in the manifest but not passed to parsers. The session id is the
file name, and `source_line` is 1 for every row since the file is one line.
A file cut mid-write yields the messages before the cut and one `system`
row.

Settings, functions and the response cache (issue 189), all source-derived
from a082bd5 and not observed on any real install:

* `.config/shell_gpt/.sgptrc`, `KEY=value` lines (ShellGPT's own reader
  skips blank lines and lines starting with `#` and splits on the first
  `=`). Only four keys are read: `OPENAI_USE_FUNCTIONS`,
  `DEFAULT_EXECUTE_SHELL_CMD` and `SHELL_INTERACTION` each give
  `permission setting: <key>=<value> (from <rel>, file mtime)`, and
  `DEFAULT_MODEL` gives `model: <value> (configured default, from <rel>,
  file mtime)`, all at the file's modification time with an empty
  `session_id`. The file holds `OPENAI_API_KEY`, so no other key, value or
  line is ever put in a row: a line with no `=` is reported as
  `parser: unparseable line <n> (no "=" separator; not shown, the file
  holds the API key)` without the line itself. An environment variable of
  the same name overrides the file at run time and leaves no trace here.
* `.config/shell_gpt/functions/*.py`, the function store: every file is
  imported on each start and offered to the model, whose calls run with no
  confirmation. Each yields `permission setting: function <file name>
  (from <directory rel>, file mtime)` at its modification time; the code
  is not read.
* The response cache, `<CACHE_PATH>/<md5>`, one bare response string per
  file, reached only as the pre-0.9.0 Windows `AppData/Local/Temp/
  shell_gpt/cache/<md5>` (the current `AppData/Local/Temp/cache` is not a
  catalog line). A secondary source (`secondary()`): each non-empty file is
  one `assistant` row with no timestamp, session or project, so it matches
  a chat file's assistant row on text alone and survives as a recovered
  row for a turn the 100-message cut dropped, a one-shot prompt or a chat
  file the temp cleaner removed. Known miss: after a function call the
  final answer is cached on its own, while the chat file stores it behind
  the `> @FunctionCall` marker, so that answer is shown twice, once as a
  recovered row.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

from ..inputs import Artifact
from ..model import Row, compact
from .base import Options, Parser, error_rows, file_mtime, text_of

CHAT_RX = re.compile(r"(^|/)chat_cache/[^/]+$")
SGPTRC_RX = re.compile(r"(^|/)\.config/shell_gpt/\.sgptrc$")
FUNCTION_RX = re.compile(r"(^|/)\.config/shell_gpt/functions/[^/]+\.py$")
CACHE_RX = re.compile(r"(^|/)shell_gpt/cache/[0-9a-f]{32}$")
# The `.sgptrc` keys read; every other key (OPENAI_API_KEY above all) is skipped.
PERMISSION_KEYS = ("OPENAI_USE_FUNCTIONS", "DEFAULT_EXECUTE_SHELL_CMD", "SHELL_INTERACTION")
MODEL_KEY = "DEFAULT_MODEL"


def _dict_or_empty(value) -> dict:
    return value if isinstance(value, dict) else {}


def load_messages(raw: str) -> tuple[list[dict], str]:
    """(messages, error). A whole array parses at once; a truncated one is
    decoded element by element so the messages before the cut survive."""
    try:
        data = json.loads(raw)
    except ValueError as error:
        err = str(error)
    else:
        if isinstance(data, list):
            return [message for message in data if isinstance(message, dict)], ""
        return [], "not a JSON array"
    text = raw.lstrip()
    if not text.startswith("["):
        return [], err
    dec = json.JSONDecoder()
    out: list[dict] = []
    i = 1
    while True:
        while i < len(text) and text[i] in " \t\r\n,":
            i += 1
        if i >= len(text) or text[i] == "]":
            break
        try:
            value, i = dec.raw_decode(text, i)
        except ValueError:
            break
        if isinstance(value, dict):
            out.append(value)
    return out, "truncated after %d message(s): %s" % (len(out), err)


def call_text(arguments) -> str:
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except ValueError:
            return arguments
        if isinstance(parsed, dict) and isinstance(parsed.get("shell_command"), str):
            return parsed["shell_command"]
        return arguments
    if isinstance(arguments, dict):
        if isinstance(arguments.get("shell_command"), str):
            return arguments["shell_command"]
        return json.dumps(arguments, ensure_ascii=False, sort_keys=True)
    return "" if arguments is None else str(arguments)


def read_sgptrc(raw: str, errors: list) -> list[tuple[str, str]]:
    """(key, value) for each of `PERMISSION_KEYS` and `MODEL_KEY` in file
    order, read as ShellGPT's `Config._read` does. A non-blank line with no
    `=` appends `(line, message, "")` to `errors`: the raw line is never
    kept, since the file holds the API key."""
    out = []
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for line_number, line in enumerate(lines, 1):
        if not line.strip() or line.startswith("#"):
            continue
        if "=" not in line:
            errors.append(
                (
                    line_number,
                    'unparseable line %d (no "=" separator; not shown, the file holds the API key)'
                    % line_number,
                    "",
                )
            )
            continue
        key, value = line.strip().split("=", 1)
        if key in PERMISSION_KEYS or key == MODEL_KEY:
            out.append((key, value))
    return out


class ShellGptParser(Parser):
    agent = "shellgpt"
    name = "shellgpt"
    has_secondary = True

    def wants(self, artifact: Artifact) -> bool:
        rel = artifact.rel
        return bool(
            CHAT_RX.search(rel)
            or SGPTRC_RX.search(rel)
            or FUNCTION_RX.search(rel)
            or CACHE_RX.search(rel)
        )

    def secondary(self, artifact: Artifact) -> bool:
        return bool(CACHE_RX.search(artifact.rel))

    def _system(self, artifact: Artifact, timestamp: str, text: str) -> Row:
        row = self.base_row(artifact)
        row.timestamp_utc = timestamp
        row.turn_type = "system"
        row.source_line = 1
        row.text = text
        return row

    def _parse_sgptrc(self, artifact: Artifact) -> Iterator[Row]:
        timestamp = file_mtime(artifact)
        errors: list = []
        with open(artifact.disk_path, "rb") as handle:
            raw = handle.read().decode("utf-8", errors="replace")
        for key, value in read_sgptrc(raw, errors):
            if key == MODEL_KEY:
                text = "model: %s (configured default, from %s, file mtime)" % (value, artifact.rel)
                row = self._system(artifact, timestamp, text)
                row.model = value
            else:
                text = "permission setting: %s=%s (from %s, file mtime)" % (
                    key,
                    value,
                    artifact.rel,
                )
                row = self._system(artifact, timestamp, text)
            yield row
        yield from error_rows(self, artifact, errors)

    def _parse_function(self, artifact: Artifact) -> Iterator[Row]:
        directory = artifact.rel.rsplit("/", 1)[0]
        text = "permission setting: function %s (from %s, file mtime)" % (
            artifact.disk_path.name,
            directory,
        )
        yield self._system(artifact, file_mtime(artifact), text)

    def _parse_cache(self, artifact: Artifact) -> Iterator[Row]:
        with open(artifact.disk_path, "rb") as handle:
            text = handle.read().decode("utf-8", errors="replace")
        if not text.strip():
            return
        row = self.base_row(artifact)
        row.turn_type = "assistant"
        row.source_line = 1
        row.text = compact(text)
        yield row

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        rel = artifact.rel
        if SGPTRC_RX.search(rel):
            yield from self._parse_sgptrc(artifact)
            return
        if FUNCTION_RX.search(rel):
            yield from self._parse_function(artifact)
            return
        if CACHE_RX.search(rel):
            yield from self._parse_cache(artifact)
            return
        session_id = artifact.disk_path.name

        def make_row(turn_type: str, text: str, tool_name: str = "", tool_use_id: str = "") -> Row:
            row = self.base_row(artifact)
            row.session_id = session_id
            row.turn_type = turn_type
            row.tool_name, row.tool_use_id = tool_name, tool_use_id
            row.source_line = 1
            row.text = compact(text)
            return row

        with open(artifact.disk_path, "rb") as handle:
            raw = handle.read().decode("utf-8", errors="replace")
        messages, error = load_messages(raw)
        if not any("role" in message for message in messages):
            yield make_row(
                "system", "parser: not a ShellGPT chat file" + (": " + error if error else "")
            )
            return

        names = {}  # tool call id -> function name
        pending = ("", "")  # (synthetic id, name) of a legacy function_call awaiting its result
        for i, message in enumerate(messages):
            role = str(message.get("role") or "")
            content = text_of(message.get("content"))
            prev, pending = pending, ("", "")
            if role in ("system", "user"):
                yield make_row(role, content)
            elif role == "assistant":
                if content.strip():
                    yield make_row("assistant", content)
                for call in message.get("tool_calls") or []:
                    call = _dict_or_empty(call)
                    function = _dict_or_empty(call.get("function"))
                    call_id, name = str(call.get("id") or ""), str(function.get("name") or "")
                    names[call_id] = name
                    yield make_row("tool_use", call_text(function.get("arguments")), name, call_id)
                function_call = message.get("function_call")
                if isinstance(function_call, dict):
                    pending = ("function_call_%d" % i, str(function_call.get("name") or ""))
                    yield make_row(
                        "tool_use",
                        call_text(function_call.get("arguments")),
                        pending[1],
                        pending[0],
                    )
            elif role == "tool":
                call_id = str(message.get("tool_call_id") or "")
                yield make_row("tool_result", content, names.get(call_id, ""), call_id)
            elif role == "function":
                yield make_row("tool_result", content, str(message.get("name") or prev[1]), prev[0])
            else:
                yield make_row("system", "%s: %s" % (role or "message", content))
        if error:
            yield make_row("system", "parser: " + error)
