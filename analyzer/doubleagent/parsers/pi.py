"""pi coding agent sessions.

Validated against source, earendil-works/pi at 20038712 (coding-agent
1.0.2, October 2026; v0.83.0 at 845d6ff1 where the schema differs), with a
synthetic fixture; see `research/pi.md`. The `defaultProjectTrust` row, the
little-coder permission-gate rows, `pi-debug.log` and `crashes.json` were
added from source at 5c1736f8 (coding-agent 1.3.0, October 2026) and are
source-derived; no real install has shown them. Files:

* `~/.pi/agent/sessions/--<encoded cwd>--/<ISO time>_<session id>.jsonl`,
  and legacy `~/.pi/agent/*.jsonl`. One JSON object per line, append-only:
  - line 1, the header: `type: "session"`, `version` (3; absent in v1),
    `id` (session id), `timestamp` (ISO 8601 Z), `cwd`, optional
    `parentSession` (absolute path of the file this one was forked or
    branched from). Files whose first record is not a header are skipped.
  - entries: `type`, `id`, `parentId`, `timestamp` (ISO). Types:
    `message` (`message.role` below), `model_change` (`provider`,
    `modelId`), `thinking_level_change` (`thinkingLevel`), `compaction`
    (`summary`, `tokensBefore`), `branch_summary` (`summary`, `fromId`),
    `custom_message` (`customType`, `content`), `context_edit`
    (`targetId`, `replacement.content`), `session_info` (`name`) become
    system rows; `custom`, `label` and `usage` are extension or UI state
    and are skipped, as are unknown types, except the `custom` entry
    with `customType` `pi.bug-report` below.
  - `message.role`, each with `timestamp` in Unix ms (the fallback when
    the entry has none): `user` (`content` string or text/image parts);
    `assistant` (`content[]` of `text`, `thinking` (`thinking`,
    `redacted`), `toolCall` (`id`, `name`, `arguments`); `provider`,
    `model`, `responseModel`, `stopReason`, `errorMessage`); `toolResult` (`toolCallId`,
    `toolName`, `content[]`, `isError`); `bashExecution` (a user
    `!command`: `command`, `output`, `exitCode`, `cancelled`), emitted as a
    tool_use and a tool_result joined on the entry `id`; `system`
    (`content`, the system prompt), `custom` (`customType`, `content`),
    `branchSummary` and `compactionSummary` (`summary`) as system rows.
  The file holds every branch of the `id`/`parentId` tree; rows follow
  file order, not the active branch.
  Model rows: `model: <id> provider=<provider>` at the first entry that
  names a model (a `model_change` `modelId` or an assistant
  `responseModel`, else `model`) and `model: <old> -> <new>
  provider=<provider>` on every later entry whose model differs, with
  ` requested=<model>` when an assistant `responseModel` (the concrete
  model the provider reported) differs from its `model` (the one asked
  for). A `model_change` entry is the user's own switch, so one that
  names the model already in force still yields `model: <id>
  provider=<provider>`; an assistant message that repeats it yields
  nothing. The `model` column is `responseModel`, else `model`. No entry type
  records a per-call permission decision; an extension that blocks a call
  leaves an error `toolResult` whose text is its reason. little-coder's
  permission gate refuses with `edit cancelled by user`, `command
  cancelled by user` or a text starting `shell whitelist:`, so an error
  `toolResult` with one of those texts is followed by `permission
  decision: denied (<the text>)` with the call's `tool_name` and
  `tool_use_id`.
* Sync rows (issue 153), so `records_sync` is set: `/bug` (not at
  v0.83.0) appends `{type: "custom", customType: "pi.bug-report", data:
  {id, createdAt, hint, sessionIncluded, summaryIncluded, delivery,
  path?}}` once a report is uploaded or exported. `delivery` `upload`
  gives `session synced: bug report <id> uploaded to radius.pi.dev
  transcript=<sessionIncluded> summary=<summaryIncluded> (from session
  entry pi.bug-report, entry timestamp)`, and `zip` gives `bug report
  exported: <id> path=<path> (from session entry pi.bug-report, entry
  timestamp)`, both at the entry's `timestamp` with the session's id;
  an absent value prints `-`. `/share` leaves no local record. `hint`,
  the user's description, is not printed.
* Forks: pi copies every parent entry into the child file verbatim, ids
  and timestamps included. When the header's `parentSession` resolves to a
  file present in the same collected home, child entries whose `id` and
  `timestamp` match a parent entry are dropped and one system row says how
  many, so a fork does not double the timeline.
* little-coder (a pi launcher) writes into pi's own directory and the
  header names no producer. A session with a `custom_message` whose
  `customType` starts `lc-`, an assistant `provider` of `llamacpp`, or a
  `~/.little-coder/checkpoints/<this file name>/` directory gets one
  system row saying so; its rows stay agent `pi`, as the manifest says.
* `~/.pi/agent/trust.json` (in the directory little-coder shares; pi
  v0.83.0, which little-coder pins, writes it too): an object whose keys
  are absolute project paths and whose values are `true` (trusted) or
  `false`. One `permission setting: <path>=<value> (from
  .pi/agent/trust.json, file mtime)` row per key, `project_path` the key,
  `session_id` empty, timestamped by the file's modification time, which
  is not the time of the decision. A file that is not a JSON object is
  one `system` row.
* `~/.pi/agent/settings.json`: only the global `defaultProjectTrust`
  (`ask`, `always`, `never`; since 1.3.0), which decides a project
  `trust.json` has no entry for, is read: `permission setting:
  defaultProjectTrust=<value> (from .pi/agent/settings.json, file mtime)`
  at the file's modification time; no row when the key is absent (the
  default, `ask`). No other key is read.
* `~/.pi/agent/pi-debug.log`, rewritten by each `/debug` (v0.83.0 too): a
  `Debug output at <ISO time>` line, the rendered screen, then `=== Agent
  messages (JSONL) ===` and the open session's messages, one
  `message`-shaped object per line, with no session id or cwd. A
  secondary source (`secondary()`): one `debug snapshot:` system row at
  the first line's time, then the messages through the session reader
  with an empty `session_id` and `project_path`, each at the message's
  own `timestamp` (ms). The session file stamps an entry when the message
  ends and an assistant message's own `timestamp` is when its stream
  started, so `secondary_tolerance()` is one hour. Bad lines after the
  marker are reported; the screen lines before it are not JSON and are
  not read.
* `~/.pi/agent/crashes.json` (not at v0.83.0): a JSON array of up to five
  recent crashes, `{timestamp, version, kind, message, stack,
  sessionFile, cwd, notified}`. One `crash: <kind> <message>
  version=<version> sessionFile=<sessionFile> (from .pi/agent/crashes.json,
  record timestamp)` system row per record at its `timestamp`, the stack
  on the lines after it, `project_path` the `cwd` and `session_id` taken
  from the `sessionFile` name; `-` for an absent value. It repeats no
  session event, so it is not a secondary source.
* `~/.pi/agent/experimental/sessions/<id>/meta.json` (`PI_EXPERIMENTAL=1`,
  not at v0.83.0): `{createdAt (ms), cwd}`, one system row per session.
  The transcript beside it, `session.sqlite`, is not parsed: its `record`
  JSON shape was not determined by the research. The experimental server
  that wrote these was removed by coding-agent 1.3.0 (5c1736f8), so the
  reader serves only installs where an older build ran.

The session reader (`read_session`, `entry_rows`) is shared with
`letta.py`, whose local backend writes the same format.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path

from ..inputs import Artifact
from ..model import Row, compact
from ..timeutil import to_utc
from .base import (
    Options,
    Parser,
    compact_json,
    error_rows,
    file_mtime,
    iter_jsonl,
    line_text,
    setting_value,
    text_of,
    track_change,
)
from .cline_legacy import iter_json_array

SESSION_RX = re.compile(r"^\.pi/agent/(?:sessions/[^/]+/)?[^/]+\.jsonl$")
TRUST_REL = ".pi/agent/trust.json"
SETTINGS_REL = ".pi/agent/settings.json"
DEBUG_REL = ".pi/agent/pi-debug.log"
CRASHES_REL = ".pi/agent/crashes.json"
DEBUG_MARKER = "=== Agent messages (JSONL) ==="
DEBUG_HEADER = "Debug output at "
# The debug log's messages carry their own `timestamp`, which for an
# assistant message is when its stream started; the session file stamps the
# entry when the message ended.
DEBUG_TOLERANCE_SECONDS = 3600.0
SESSION_NAME_RX = re.compile(r"_([^_/]+)\.jsonl$")
# The refusal texts of little-coder's permission-gate extension.
GATE_REFUSALS = ("edit cancelled by user", "command cancelled by user")
GATE_PREFIX = "shell whitelist:"
META_RX = re.compile(r"^\.pi/agent/experimental/sessions/([^/]+)/meta\.json$")

ARG_KEYS = ("command", "path", "file_path", "pattern", "code", "url", "query")
SKIPPED_ENTRIES = ("custom", "label", "usage")
BUG_REPORT = "pi.bug-report"


class SessionFile:
    """One pi-format session file: the header (empty when line 1 is not
    one), the entries after it as (line, record), and unparseable lines."""

    def __init__(self) -> None:
        self.header: dict = {}
        self.header_line = 0
        self.entries: list[tuple[int, dict]] = []
        self.errors: list = []


def read_session(path) -> SessionFile:
    session = SessionFile()
    first = True
    for line_number, rec in iter_jsonl(path, session.errors):
        if first:
            first = False
            if rec.get("type") == "session":
                session.header, session.header_line = rec, line_number
                continue
        session.entries.append((line_number, rec))
    return session


def entry_keys(path) -> set[tuple[str, str]]:
    """(id, timestamp) of every entry, for fork deduplication."""
    out: set[tuple[str, str]] = set()
    for _, rec in read_session(path).entries:
        if rec.get("id"):
            out.add((str(rec.get("id")), str(rec.get("timestamp") or "")))
    return out


def args_summary(args) -> str:
    """The most identifying tool argument, else the arguments as JSON."""
    if isinstance(args, dict):
        for k in ARG_KEYS:
            value = args.get(k)
            if value not in (None, ""):
                return value if isinstance(value, str) else compact_json(value)
        return compact_json(args)
    if args in (None, ""):
        return ""
    return args if isinstance(args, str) else compact_json(args)


def _label(prefix: str, text: str) -> str:
    return "%s: %s" % (prefix, text) if text else prefix


def model_text(seen: dict, key: str, model: str, provider: str, requested: str = "") -> str:
    """The `model:` row text when `model` is new or changed for `key`, with
    ` provider=` and, when the provider reported a concrete model other than
    the one asked for, ` requested=<model asked for>`; empty otherwise."""
    text = track_change("model", seen, key, model)
    if text and provider:
        text += " provider=%s" % provider
    if text and requested and requested != model:
        text += " requested=%s" % requested
    return text


def switch_text(seen: dict, key: str, model: str, provider: str) -> str:
    """The row text for a `model_change` entry, the user's own switch: the
    `model_text` row, or, when it names the model already in force, the
    plain `model: <id> provider=<provider>` row, so the switch keeps a row."""
    text = model_text(seen, key, model, provider)
    if not text and model:
        text = "model: %s" % model + (" provider=%s" % provider if provider else "")
    return text


def entry_rows(
    parser: Parser,
    artifact: Artifact,
    session: SessionFile,
    opts: Options,
    session_id: str = "",
    project_path: str = "",
    skip: set[tuple[str, str]] | None = None,
) -> Iterator[Row]:
    """Timeline rows for the entries of a pi-format session. `skip` holds
    (id, timestamp) keys to drop (entries a fork copied from its parent)."""
    skip = skip or set()
    seen: dict = {}  # the model in use, for the `model:` rows
    for line_number, rec in session.entries:
        if skip and (str(rec.get("id") or ""), str(rec.get("timestamp") or "")) in skip:
            continue
        etype = rec.get("type")
        raw_msg = rec.get("message")
        msg: dict = raw_msg if isinstance(raw_msg, dict) else {}

        def base(model: str = "") -> Row:
            row = parser.base_row(artifact)
            row.source_line = line_number
            row.timestamp_utc = to_utc(rec.get("timestamp")) or to_utc(msg.get("timestamp"))
            row.session_id = session_id
            row.project_path = project_path
            row.model = model
            return row

        def emit(row: Row, turn: str, text: str, tool_name: str = "", tool_use_id: str = "") -> Row:
            row.turn_type = turn
            row.tool_name = tool_name
            row.tool_use_id = tool_use_id
            row.text = compact(text)
            return row

        if etype == "message":
            yield from _message_rows(msg, rec, base, emit, opts, seen, session_id)
        elif etype == "model_change":
            model = str(rec.get("modelId") or "")
            text = switch_text(seen, session_id, model, str(rec.get("provider") or ""))
            if text:
                yield emit(base(model), "system", text)
        elif etype == "thinking_level_change":
            yield emit(
                base(), "system", "thinking_level_change: %s" % (rec.get("thinkingLevel") or "")
            )
        elif etype == "compaction":
            yield emit(
                base(),
                "system",
                _label(
                    "compaction: tokensBefore=%s" % (rec.get("tokensBefore") or ""),
                    str(rec.get("summary") or ""),
                ),
            )
        elif etype == "branch_summary":
            yield emit(
                base(),
                "system",
                _label(
                    "branch_summary from %s" % (rec.get("fromId") or ""),
                    str(rec.get("summary") or ""),
                ),
            )
        elif etype == "custom_message":
            yield emit(
                base(),
                "system",
                _label(
                    "custom_message %s" % (rec.get("customType") or ""), text_of(rec.get("content"))
                ),
            )
        elif etype == "context_edit":
            rep = rec.get("replacement")
            what = text_of(rep.get("content")) if isinstance(rep, dict) else "omitted from context"
            yield emit(
                base(),
                "system",
                _label("context_edit target=%s" % (rec.get("targetId") or ""), what),
            )
        elif etype == "session_info":
            yield emit(base(), "system", "session_info: name=%s" % (rec.get("name") or ""))
        elif etype == "custom" and rec.get("customType") == BUG_REPORT:
            text = bug_report_text(rec.get("data"))
            if text:
                yield emit(base(), "system", text)
        # Other custom entries, label, usage and unknown types carry no
        # conversation content.


def bug_report_text(data) -> str:
    """The row text for a `pi.bug-report` entry's `data`: `session synced:`
    for an upload, `bug report exported:` for a zip, empty for any other
    `delivery`. `hint` is not printed."""
    if not isinstance(data, dict):
        return ""

    def val(key: str) -> str:
        value = data.get(key)
        return "-" if value in (None, "") else setting_value(value)

    src = "(from session entry %s, entry timestamp)" % BUG_REPORT
    if data.get("delivery") == "upload":
        return (
            "session synced: bug report %s uploaded to radius.pi.dev transcript=%s summary=%s %s"
            % (
                val("id"),
                val("sessionIncluded"),
                val("summaryIncluded"),
                src,
            )
        )
    if data.get("delivery") == "zip":
        return "bug report exported: %s path=%s %s" % (val("id"), val("path"), src)
    return ""


def _message_rows(
    msg: dict, rec: dict, base, emit, opts: Options, seen: dict, session_id: str
) -> Iterator[Row]:
    role = msg.get("role")
    if role == "user":
        text = text_of(msg.get("content"))
        if text:
            yield emit(base(), "user", text)
    elif role == "assistant":
        requested = str(msg.get("model") or "")
        model = str(msg.get("responseModel") or "") or requested
        text = model_text(seen, session_id, model, str(msg.get("provider") or ""), requested)
        if text:
            yield emit(base(model), "system", text)
        content = msg.get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        for part in content if isinstance(content, list) else []:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")
            if ptype == "text" and part.get("text"):
                yield emit(base(model), "assistant", str(part.get("text")))
            elif ptype == "thinking" and opts.include_thinking:
                text = str(part.get("thinking") or "")
                if part.get("redacted") and not text:
                    text = "[redacted]"
                if text:
                    yield emit(base(model), "thinking", text)
            elif ptype == "toolCall":
                name = str(part.get("name") or "")
                yield emit(
                    base(model),
                    "tool_use",
                    args_summary(part.get("arguments")),
                    tool_name=name,
                    tool_use_id=str(part.get("id") or ""),
                )
        if msg.get("stopReason") in ("error", "aborted"):
            yield emit(
                base(model),
                "system",
                _label(
                    "assistant stopReason=%s" % msg.get("stopReason"),
                    str(msg.get("errorMessage") or ""),
                ),
            )
    elif role == "toolResult":
        reason = text_of(msg.get("content"))
        text = "[error] " + reason if msg.get("isError") else reason
        tool_name = str(msg.get("toolName") or "")
        tool_use_id = str(msg.get("toolCallId") or "")
        yield emit(base(), "tool_result", text, tool_name=tool_name, tool_use_id=tool_use_id)
        if msg.get("isError") and (reason in GATE_REFUSALS or reason.startswith(GATE_PREFIX)):
            yield emit(
                base(),
                "system",
                "permission decision: denied (%s)" % reason,
                tool_name=tool_name,
                tool_use_id=tool_use_id,
            )
    elif role == "bashExecution":
        eid = str(rec.get("id") or "")
        yield emit(
            base(), "tool_use", str(msg.get("command") or ""), tool_name="bash", tool_use_id=eid
        )
        out = str(msg.get("output") or "")
        notes = []
        if msg.get("exitCode") not in (None, 0):
            notes.append("exit %s" % msg.get("exitCode"))
        if msg.get("cancelled"):
            notes.append("cancelled")
        if msg.get("truncated"):
            notes.append("truncated")
        if notes:
            out = (out + "\n" if out else "") + "[%s]" % ", ".join(notes)
        yield emit(base(), "tool_result", out, tool_name="bash", tool_use_id=eid)
    elif role == "system":
        yield emit(base(), "system", _label("system prompt", text_of(msg.get("content"))))
    elif role == "custom":
        yield emit(
            base(),
            "system",
            _label("custom %s" % (msg.get("customType") or ""), text_of(msg.get("content"))),
        )
    elif role in ("branchSummary", "compactionSummary"):
        yield emit(base(), "system", _label(role, str(msg.get("summary") or "")))


def home_file(artifact: Artifact, original: str, marker: str) -> Path | None:
    """The collected copy of `original` (a path on the source host) inside
    the artifact's home, or None. Tried relative to the home's original path,
    then from the last `marker` segment (loose input whose home path is not
    the host's). Symlinks are never followed."""
    path = original.replace("\\", "/")
    rels = []
    home = artifact.home.original.replace("\\", "/").rstrip("/")
    if home and path.startswith(home + "/"):
        rels.append(path[len(home) + 1 :])
    i = path.rfind("/" + marker)
    if i >= 0:
        rels.append(path[i + 1 :])
    root = artifact.home.disk_path
    for rel in rels:
        parts = [part for part in rel.split("/") if part]
        if not parts or ".." in parts:
            continue
        cur = root
        safe = True
        for part in parts:
            cur = cur / part
            if cur.is_symlink():
                safe = False
                break
        if safe and cur.is_file():
            return cur
    return None


class PiParser(Parser):
    agent = "pi"
    name = "pi"
    records_sync = True
    has_secondary = True

    def __init__(self) -> None:
        self._parent_cache: dict[Path, set[tuple[str, str]]] = {}

    def wants(self, artifact: Artifact) -> bool:
        return artifact.rel in (TRUST_REL, SETTINGS_REL, DEBUG_REL, CRASHES_REL) or bool(
            SESSION_RX.match(artifact.rel) or META_RX.match(artifact.rel)
        )

    def secondary(self, artifact: Artifact) -> bool:
        return artifact.rel == DEBUG_REL

    def secondary_tolerance(self, artifact: Artifact) -> float:
        if artifact.rel == DEBUG_REL:
            return DEBUG_TOLERANCE_SECONDS
        return super().secondary_tolerance(artifact)

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        if artifact.rel == TRUST_REL:
            yield from self._parse_trust(artifact)
            return
        if artifact.rel == SETTINGS_REL:
            yield from self._parse_settings(artifact)
            return
        if artifact.rel == DEBUG_REL:
            yield from self._parse_debug_log(artifact, opts)
            return
        if artifact.rel == CRASHES_REL:
            yield from self._parse_crashes(artifact)
            return
        match = META_RX.match(artifact.rel)
        if match:
            yield from self._parse_meta(artifact, match.group(1), opts)
            return
        session = read_session(artifact.disk_path)
        header = session.header
        if not header:
            if not session.entries:
                yield from error_rows(self, artifact, session.errors)
            return
        sid = str(header.get("id") or "")
        cwd = str(header.get("cwd") or "")
        parent = str(header.get("parentSession") or "")

        row = self.base_row(artifact)
        row.source_line = session.header_line
        row.timestamp_utc = to_utc(header.get("timestamp"))
        row.session_id, row.project_path, row.turn_type = sid, cwd, "system"
        text = "session start: version=%s cwd=%s" % (header.get("version") or 1, cwd)
        if parent:
            text += " parentSession=%s" % parent
        row.text = compact(text)
        yield row

        skip: set[tuple[str, str]] = set()
        if parent:
            parent_file = home_file(artifact, parent, ".pi/")
            if parent_file is not None and parent_file != artifact.disk_path:
                if parent_file not in self._parent_cache:
                    self._parent_cache[parent_file] = entry_keys(parent_file)
                skip = self._parent_cache[parent_file]
        dropped = 0
        if skip:
            dropped = sum(
                1
                for _, record in session.entries
                if (str(record.get("id") or ""), str(record.get("timestamp") or "")) in skip
            )
            if dropped:
                row = self.base_row(artifact)
                row.source_line = session.header_line
                row.timestamp_utc = to_utc(header.get("timestamp"))
                row.session_id, row.project_path, row.turn_type = sid, cwd, "system"
                row.text = compact(
                    "fork: %d entries copied from the parent session %s omitted; "
                    "they are in the parent's rows" % (dropped, parent),
                )
                yield row

        yield from entry_rows(self, artifact, session, opts, sid, cwd, skip if dropped else None)

        why = little_coder_markers(artifact, session)
        if why:
            row = self.base_row(artifact)
            row.source_line = session.header_line
            row.timestamp_utc = to_utc(header.get("timestamp"))
            row.session_id, row.project_path, row.turn_type = sid, cwd, "system"
            row.text = compact(
                "session driven by little-coder (pi launcher): %s" % "; ".join(why),
            )
            yield row
        yield from error_rows(self, artifact, session.errors, sid, cwd)

    def _parse_trust(self, artifact: Artifact) -> Iterator[Row]:
        """`trust.json`: one standing row per project path, `true` or
        `false`, timestamped by the file's modification time."""
        try:
            doc = json.loads(artifact.disk_path.read_bytes().decode("utf-8", errors="replace"))
        except (OSError, ValueError):
            doc = None
        timestamp = file_mtime(artifact)
        if not isinstance(doc, dict):
            row = self.base_row(artifact)
            row.source_line, row.turn_type, row.timestamp_utc = 1, "system", timestamp
            row.text = "parser: %s is not a JSON object" % TRUST_REL
            yield row
            return
        for path, value in doc.items():
            row = self.base_row(artifact)
            row.source_line, row.turn_type, row.timestamp_utc = 1, "system", timestamp
            row.project_path = str(path)
            row.text = compact(
                "permission setting: %s=%s (from %s, file mtime)"
                % (path, setting_value(value), artifact.rel)
            )
            yield row

    def _parse_settings(self, artifact: Artifact) -> Iterator[Row]:
        """`settings.json`: the global `defaultProjectTrust` alone, one
        standing row timestamped by the file's modification time."""
        try:
            doc = json.loads(artifact.disk_path.read_bytes().decode("utf-8", errors="replace"))
        except (OSError, ValueError):
            return  # settings, not a transcript: no standing value to report
        value = doc.get("defaultProjectTrust") if isinstance(doc, dict) else None
        if value in (None, ""):
            return
        row = self.base_row(artifact)
        row.source_line, row.turn_type, row.timestamp_utc = 1, "system", file_mtime(artifact)
        row.text = compact(
            "permission setting: defaultProjectTrust=%s (from %s, file mtime)"
            % (setting_value(value), artifact.rel)
        )
        yield row

    def _parse_debug_log(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        """`pi-debug.log`: the messages after the JSONL marker, with no
        session id; the screen lines before it are not read."""
        session = SessionFile()
        written = ""
        in_messages = False
        with open(artifact.disk_path, "rb") as handle:
            for line_number, raw in enumerate(handle, 1):
                line = line_text(raw)
                if line_number == 1 and line.startswith(DEBUG_HEADER):
                    written = to_utc(line[len(DEBUG_HEADER) :].strip())
                if not in_messages:
                    in_messages = line == DEBUG_MARKER
                    continue
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except ValueError as error:
                    session.errors.append((line_number, "unparseable line (%s)" % error, line))
                    continue
                if not isinstance(msg, dict):
                    session.errors.append(
                        (line_number, "unparseable line (not a JSON object)", line)
                    )
                    continue
                session.entries.append((line_number, {"type": "message", "message": msg}))
        row = self.base_row(artifact)
        row.source_line, row.turn_type, row.timestamp_utc = 1, "system", written
        row.text = compact(
            "debug snapshot: /debug wrote %d message(s) of the open session, which the log "
            "does not name (from %s, Debug output at line)" % (len(session.entries), artifact.rel)
        )
        yield row
        yield from entry_rows(self, artifact, session, opts)
        yield from error_rows(self, artifact, session.errors)

    def _parse_crashes(self, artifact: Artifact) -> Iterator[Row]:
        """`crashes.json`: one row per crash record, at its own time."""
        errors: list = []
        for index, rec in iter_json_array(artifact.disk_path, errors):
            if not isinstance(rec, dict):
                continue
            session_file = str(rec.get("sessionFile") or "")
            match = SESSION_NAME_RX.search(session_file.replace("\\", "/"))
            row = self.base_row(artifact)
            row.source_line, row.turn_type = index, "system"
            row.timestamp_utc = to_utc(rec.get("timestamp"))
            row.session_id = match.group(1) if match else ""
            row.project_path = str(rec.get("cwd") or "")
            text = "crash: %s %s version=%s sessionFile=%s (from %s, record timestamp)" % (
                _dash(rec.get("kind")),
                _dash(rec.get("message")),
                _dash(rec.get("version")),
                _dash(rec.get("sessionFile")),
                artifact.rel,
            )
            if rec.get("stack"):
                text += "\n" + str(rec.get("stack"))
            row.text = compact(text)
            yield row
        yield from error_rows(self, artifact, errors)

    def _parse_meta(self, artifact: Artifact, sid: str, opts: Options) -> Iterator[Row]:
        row = self.base_row(artifact)
        row.session_id, row.turn_type, row.source_line = sid, "system", 1
        try:
            with open(artifact.disk_path, "rb") as handle:
                meta = json.loads(handle.read().decode("utf-8", errors="replace"))
        except ValueError as error:
            row.text = "parser: %s" % error
            yield row
            return
        if not isinstance(meta, dict):
            meta = {}
        row.timestamp_utc = to_utc(meta.get("createdAt"))
        row.project_path = str(meta.get("cwd") or "")
        row.text = compact(
            "experimental durable session created: cwd=%s (transcript in session.sqlite, "
            "not parsed)" % row.project_path,
        )
        yield row


def _dash(value) -> str:
    """A record value as row text, `-` when it is absent or empty."""
    return "-" if value in (None, "") else setting_value(value)


def little_coder_markers(artifact: Artifact, session: SessionFile) -> list[str]:
    """Why a pi session looks driven by little-coder, empty when it does not."""
    types: dict[str, None] = {}
    llamacpp = False
    for _, rec in session.entries:
        if rec.get("type") == "custom_message":
            custom_type = str(rec.get("customType") or "")
            if custom_type.startswith("lc-"):
                types.setdefault(custom_type)
        elif rec.get("type") == "message":
            msg = rec.get("message")
            if (
                isinstance(msg, dict)
                and msg.get("role") == "assistant"
                and msg.get("provider") == "llamacpp"
            ):
                llamacpp = True
    why = []
    if types:
        why.append("custom_message types " + ", ".join(types))
    if llamacpp:
        why.append("assistant provider llamacpp")
    checkpoint = (
        artifact.home.disk_path / ".little-coder" / "checkpoints" / os.path.basename(artifact.rel)
    )
    if not checkpoint.is_symlink() and checkpoint.is_dir():
        why.append("checkpoints in ~/.little-coder/checkpoints/%s" % checkpoint.name)
    return why
