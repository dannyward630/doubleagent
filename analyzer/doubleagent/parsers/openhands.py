"""OpenHands conversations (Agent Canvas, Agent Server and the `openhands` CLI).

Validated against source, OpenHands/software-agent-sdk at b347047 and
OpenHands/OpenHands at 7fbb48c (0.62.0, legacy layout), with a synthetic
fixture; no real install was used. The security-analyzer verdicts, the
standing permission settings, the model rows from switches and per-response
token usage, the CLI prompt history and the worktree scratch directory rows
are source-derived (software-agent-sdk at 33d8aa2, OpenHands-CLI at
0403f1a) and not observed on any real install. See `research/openhands.md`.

Files, relative to the home directory (the same layout on every OS):

* `.openhands/agent-canvas/dev_conversations/<hex>/`,
  `.openhands/agent-canvas/conversations/<hex>/` and
  `.openhands/conversations/<hex>/`, one directory per conversation named by
  its UUID as 32 hex digits. Each artifact is one event file,
  `events/event-<idx, 5+ digits>-<event id>.json`, holding one JSON object.
  Fields read: `kind`, `id`, `timestamp`, `source`, and per kind:
  - `MessageEvent`: `llm_message.{role, content[] ({type:"text", text} or
    {type:"image"}), tool_calls[].{id, name or function.name, arguments},
    tool_call_id, reasoning_content, thinking_blocks[].thinking}`.
  - `ActionEvent`: `thought[]`, `reasoning_content`, `thinking_blocks[]`,
    `action.{kind, command, path}`, `tool_name`, `tool_call_id`,
    `tool_call.arguments`, `security_risk`.
  - `ObservationEvent`: `tool_name`, `tool_call_id`, `observation.{content[],
    is_error}`; `UserRejectObservation`: `rejection_reason`,
    `rejection_source`; `AgentErrorEvent`: `error`.
  - `ACPToolCallEvent`: `tool_call_id`, `title`, `status`, `tool_kind`,
    `raw_input`, `raw_output`, `content`, `is_error`.
  - `SecurityAnalysisEvent`: `analyzer`, `policy`, `risks` (ActionEvent id
    to `UNKNOWN`, `LOW`, `MEDIUM` or `HIGH`), `details`.
  - `ObservationEvent` whose `observation.kind` is `SwitchLLMObservation`
    (`profile_name`, `active_model`, `is_error`) or
    `ClassifyAndSwitchLLMObservation` (`model`, the profile, `chosen_class`,
    `active_model`); `ActionEvent` and agent `MessageEvent`
    `llm_response_id`.
  - `SystemPromptEvent`: `system_prompt`, `tools`; `Condensation` and
    `CondensationSummaryEvent`: `summary`, `forgotten_event_ids`;
    `HookExecutionEvent`: `hook_event_type`, `hook_command`, `exit_code`,
    `blocked`, `stderr`; `ConversationStateUpdateEvent`: `key`, `value`.
  The sibling files of the conversation directory are read once per
  conversation: `meta.json` (`id`, `title`, `created_at`,
  `parent_conversation_id`, `forked_from_conversation_id`,
  `workspace.working_dir`) and `base_state.json` (`agent.llm.model`,
  `workspace.working_dir`, `confirmation_policy.{kind, threshold,
  confirm_unknown}`, `security_analyzer.kind`, `blocked_actions`,
  `stats.usage_to_metrics.*.token_usages[].{model, response_id}`). Every
  event file of the conversation is read once with them, to join the
  analyzer's verdicts and the blocked actions to their tool call and to
  place the model rows. A `meta.json` or `base_state.json` that exists
  but cannot be read, is not JSON (cut mid-write) or is not an object gives
  one whole-file `system` row on the first event file, after the header and
  model rows, `parser: <file name> could not be decoded (<reason>)`,
  `could not be read (<reason>)` or `is not a JSON object`, with an empty
  timestamp and the session id and `project_path` known from the other
  file; the header then lacks what that file held (issue 176). Their
  `secrets`, `api_key` and `secret_registry` fields are never read, and `settings.json`,
  `secrets.json` and `profiles/*.json` are never opened.
* `base_state.json` of each conversation is also an artifact of its own, at
  whose modification time it yields the standing permission rows,
  `permission setting: confirmation_policy=<kind>[ threshold=<threshold>]
  [ confirm_unknown=<bool>] (from base_state.json, file mtime)`,
  `permission setting: security_analyzer=<kind> (...)` (`none` when the key
  is absent; the file is written with `exclude_none`) and
  `permission setting: blocked_actions.<action id>=<reason> (...)` per
  hook-blocked action, with the action's `tool_name` and `tool_use_id`;
  and, when `agent.llm.model` differs from the last model the events show
  (a switch through the Agent Server's REST endpoints writes no event),
  `model: <old> -> <new> (from base_state.json agent.llm, file mtime)`. The
  file holds the state at its last write, not its history.
* `.openhands/projects/<sha256 of cwd>/prompt_history.json`, the CLI's last
  100 prompts per working directory: a JSON array of `{text, timestamp}`,
  oldest first, `timestamp` naive local time (emitted as if UTC, as the CLI
  conversations are). A secondary source: one `user` row per entry with an
  empty `session_id`, and `project_path` the `workspace.working_dir` of a
  conversation under the same `.openhands` whose SHA-256 is the directory
  name, else empty. A record that does not decode, or is not an object,
  is its own `parser: unparseable record <N> (<reason>)` row.
* Legacy 0.x `.openhands/sessions/<sid>/events/<n>.json` and
  `.openhands/users/<uid>/conversations/<sid>/events/<n>.json`: detected and
  reported as one `system` row per session (on the lowest-numbered event
  file), not parsed. The 1.x `v1_conversations/` tree and `bash_events/`
  are not read.

Timestamps. Event `timestamp` is `datetime.now().isoformat()`, naive host
local time. When `meta.json` has a UTC `created_at`, the host's offset is
taken as the difference between the first event's naive time (the lowest
index in `events/`) and `created_at`, floored to the quarter hour after
allowing one minute of clock skew, so a first event written up to 14
minutes after creation still gives the right offset; it is applied to every
event of that conversation. Without `meta.json` (the CLI does not write one)
the naive times are emitted as if they were UTC, as the Aider parser does.
The conversation's header row says which was done. An event timestamp that
does carry a zone is converted as is.

Rows. The first event file of a conversation also yields one `system`
header row (title, parent or fork, model, timestamp basis). `MessageEvent`
rows take their type from `llm_message.role` (`tool` is `tool_result`),
with any `tool_calls` as `tool_use` rows; `ActionEvent` and
`ACPToolCallEvent` are `tool_use` (an ACP call that has output also yields a
`tool_result`); `ObservationEvent`, `UserRejectObservation` and
`AgentErrorEvent` are `tool_result` joined on `tool_call_id`; everything else
is `system`. An `ActionEvent` with a `security_risk` (the security
analyzer's rating, `UNKNOWN`, `LOW`, ...) ends its `tool_use` text with
` security_risk=<value>`. A `UserRejectObservation` keeps its `tool_result`
row, `[rejected by <rejection_source>] <rejection_reason>`, and is followed
by a `system` row `permission decision: rejected rejection_source=<source>
<rejection_reason>` (`-` for a missing source) with the call's `tool_name`
and `tool_use_id`. The conversation's model, `agent.llm.model` from
`base_state.json`, becomes a `system` row `model: <id>` after the header
row, at the header's time. `base_state.json` holds only the
conversation's current model, so the `model: <id>` row names the model of
the first response (from `token_usages[]` joined on `llm_response_id`)
when one is recorded before any switch, else `agent.llm.model`. A response
whose model differs from the one in force is preceded by `model: <old> ->
<new>`; a successful `SwitchLLMObservation` or
`ClassifyAndSwitchLLMObservation` is followed by `model: <old> ->
<active_model> profile=<profile>[ class=<chosen_class>]`. The `model`
column of each event row is the model in force at its event. A
`SecurityAnalysisEvent` becomes one `system` row per entry of `risks`,
`permission decision: analyzed risk=<risk> analyzer=<analyzer>
policy=<policy>[ details=<JSON>]`, with the analysed action's `tool_name`
and `tool_use_id` (` action_id=<id>` instead when no ActionEvent has that
id). A conversation whose `workspace.working_dir` is under the Agent
Server's default worktree root, `/tmp/conversation-worktrees/` (or
`/private/tmp/...` on macOS), gets `scratch directory: <working_dir>
(conversation worktree under the Agent Server's default
conversation_worktree_root /tmp/conversation-worktrees)` after the model
row; a configured root is not recognised. Thoughts, `reasoning_content` and thinking blocks become
`thinking` rows with `--include-thinking`. The session id is the directory
name, `project_path` is `workspace.working_dir` from `meta.json`, else from
`base_state.json` (a container path under Canvas in Docker). No git branch is recorded. `source_line` is 1, since
every file holds one object.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..inputs import Artifact, error_reason
from ..model import Row, compact
from ..timeutil import to_utc
from .base import (
    Options,
    Parser,
    compact_json,
    error_rows,
    file_mtime,
    setting_value,
    text_of,
)
from .cline_legacy import iter_json_array

EVENT_RX = re.compile(
    r"^\.openhands/(?:agent-canvas/(?:dev_)?conversations|conversations)/"
    r"([0-9a-fA-F]{32})/events/event-(\d{5,})-[0-9a-fA-F-]{8,}\.json$"
)
EVENT_NAME_RX = re.compile(r"^event-(\d{5,})-[0-9a-fA-F-]{8,}\.json$")
STATE_RX = re.compile(
    r"^\.openhands/(?:agent-canvas/(?:dev_)?conversations|conversations)/"
    r"([0-9a-fA-F]{32})/base_state\.json$"
)
HISTORY_RX = re.compile(r"^\.openhands/projects/([0-9a-f]{64})/prompt_history\.json$")
CONVERSATION_GLOBS = (
    "agent-canvas/dev_conversations/*/base_state.json",
    "agent-canvas/conversations/*/base_state.json",
    "conversations/*/base_state.json",
    "agent-canvas/dev_conversations/*/meta.json",
    "agent-canvas/conversations/*/meta.json",
)
# The Agent Server's default `conversation_worktree_root`; macOS resolves
# /tmp to /private/tmp.
WORKTREE_ROOTS = ("/tmp/conversation-worktrees/", "/private/tmp/conversation-worktrees/")
SWITCH_KINDS = ("SwitchLLMObservation", "ClassifyAndSwitchLLMObservation")
LEGACY_RX = re.compile(
    r"^\.openhands/(?:sessions|users/[^/]+/conversations)/([^/]+)/events/(\d+)\.json$"
)

QUARTER = 900
SKEW = 60
MAX_OFFSET = 14 * 3600


def _dict_or_empty(value) -> dict:
    return value if isinstance(value, dict) else {}


def _join(*parts: str) -> str:
    return " | ".join(part for part in parts if part)


def _load_json(path: Path) -> tuple[object, str]:
    """The decoded JSON of `path` and "", or None and the reason it could not
    be read or decoded. A missing file, a symlink or a directory is None and
    "", since the CLI writes no `meta.json` and that is not an error."""
    try:
        if path.is_symlink() or not path.is_file():
            return None, ""
        with open(path, "rb") as handle:
            return json.loads(handle.read().decode("utf-8", errors="replace")), ""
    except OSError as error:
        return None, "could not be read (%s)" % error_reason(error)
    except ValueError as error:
        return None, "could not be decoded (%s)" % error


def _read_json(path: Path):
    return _load_json(path)[0]


def _is_file(path: Path) -> bool:
    try:
        return not path.is_symlink() and path.is_file()
    except OSError:
        return False


def _load_object(path: Path, problems: list[str]) -> dict:
    """The JSON object in `path`, else {}; a file that exists but cannot be
    read, decoded or is not an object appends `parser: <name> <reason>` to
    `problems`."""
    value, reason = _load_json(path)
    if not reason and not isinstance(value, dict) and (value is not None or _is_file(path)):
        reason = "is not a JSON object"  # a list, a scalar or a literal null
    if reason:
        problems.append("parser: %s %s" % (path.name, reason))
    return value if isinstance(value, dict) else {}


def _aware(value) -> datetime | None:
    """A UTC datetime from a string `to_utc` accepts, else None."""
    timestamp = to_utc(value) if isinstance(value, str) else ""
    if not timestamp:
        return None
    return datetime.fromisoformat(timestamp[:-1]).replace(tzinfo=timezone.utc)


def _naive(value) -> datetime | None:
    """A naive datetime when the timestamp has no zone, else None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", value.strip()))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is None else None


def _fmt_offset(seconds: int) -> str:
    sign = "+" if seconds >= 0 else "-"
    seconds = abs(seconds)
    return "UTC%s%02d:%02d" % (sign, seconds // 3600, seconds % 3600 // 60)


@dataclass
class _Conv:
    session_id: str
    project_path: str = ""
    model: str = ""
    offset: int | None = None  # seconds east of UTC, when anchored
    first_event: str = ""  # file name of the lowest-index event
    header: str = ""
    created: str = ""
    # Whole-file `parser:` rows for a meta.json or base_state.json that
    # exists but did not decode (issue 176).
    problems: list[str] = field(default_factory=list)
    # The model in force at the conversation's start: the model of the first
    # response before any switch, else `base_state.json` `agent.llm.model`.
    initial_model: str = ""
    # Per event file name: a `model:` row written before or after the
    # event's own rows, and the model in force at that event.
    model_before: dict[str, str] = field(default_factory=dict)
    model_after: dict[str, tuple[str, str]] = field(default_factory=dict)
    event_model: dict[str, str] = field(default_factory=dict)
    # A `model: <old> -> <new>` row for the base_state.json artifact when its
    # `agent.llm.model` differs from the last model the events show.
    final_model_row: str = ""
    # ActionEvent id -> (tool_name, tool_call_id), for the security
    # analyzer's verdicts and the blocked actions, which name action ids.
    actions: dict[str, tuple[str, str]] = field(default_factory=dict)
    # `permission setting:` rows from base_state.json, with their join.
    settings: list[tuple[str, str, str]] = field(default_factory=list)
    scratch: str = ""


class OpenHandsParser(Parser):
    agent = "openhands"
    name = "openhands"

    has_secondary = True

    def __init__(self) -> None:
        self._cache: dict[tuple, _Conv] = {}

    def wants(self, artifact: Artifact) -> bool:
        rel = artifact.rel
        return bool(
            EVENT_RX.match(rel)
            or LEGACY_RX.match(rel)
            or STATE_RX.match(rel)
            or HISTORY_RX.match(rel)
        )

    def secondary(self, artifact: Artifact) -> bool:
        return bool(HISTORY_RX.match(artifact.rel))

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        if LEGACY_RX.match(artifact.rel):
            yield from self._parse_legacy(artifact, opts)
            return
        if HISTORY_RX.match(artifact.rel):
            yield from self._parse_history(artifact)
            return
        if STATE_RX.match(artifact.rel):
            yield from self._parse_state(artifact)
            return
        conv = self._conversation(artifact.disk_path.parent.parent)
        name = artifact.disk_path.name
        if name == conv.first_event:
            row = self._row(artifact, conv, "system")
            row.timestamp_utc = conv.created
            row.text = compact(conv.header)
            yield row
            for text in (
                "model: " + conv.initial_model if conv.initial_model else "",
                conv.scratch,
            ):
                if text:
                    row = self._row(artifact, conv, "system")
                    row.timestamp_utc = conv.created
                    row.model = conv.initial_model or conv.model
                    row.text = text
                    yield row
            for problem in conv.problems:
                row = self._row(artifact, conv, "system")
                row.text = problem
                yield row
        event, reason = _load_json(artifact.disk_path)
        if not isinstance(event, dict):
            row = self._row(artifact, conv, "system")
            row.text = "parser: event file %s" % (reason or "is not a JSON object")
            yield row
            return
        timestamp = self._timestamp(event.get("timestamp"), conv)
        model = conv.event_model.get(name, conv.initial_model or conv.model)
        rows: list[Row] = []
        if name in conv.model_before:
            rows.append(self._row(artifact, conv, "system"))
            rows[-1].text = conv.model_before[name]
        rows.extend(self._event_rows(artifact, conv, event, opts))
        for row in rows:
            row.timestamp_utc = timestamp
            row.model = model
            yield row
        if name in conv.model_after:
            row = self._row(artifact, conv, "system")
            row.text, row.model = conv.model_after[name]
            row.timestamp_utc = timestamp
            yield row

    # -- base_state.json: standing permissions and a model set over REST ----------------
    def _parse_state(self, artifact: Artifact) -> Iterator[Row]:
        conv = self._conversation(artifact.disk_path.parent)
        timestamp = file_mtime(artifact)
        texts = list(conv.settings)
        if conv.final_model_row:
            texts.append((conv.final_model_row, "", ""))
        for text, tool_name, tool_use_id in texts:
            row = self._row(artifact, conv, "system")
            row.timestamp_utc = timestamp
            row.text = text
            row.tool_name, row.tool_use_id = tool_name, tool_use_id
            yield row

    # -- CLI prompt history (secondary) -----------------------------------------------
    def _parse_history(self, artifact: Artifact) -> Iterator[Row]:
        match = HISTORY_RX.match(artifact.rel)
        assert match is not None  # parse() routes only matching paths here
        project = _project_for_hash(artifact.disk_path.parent.parent.parent, match.group(1))
        errors: list = []
        for index, entry in iter_json_array(artifact.disk_path, errors):
            if not isinstance(entry, dict):
                message = "unparseable record %d (not a JSON object)" % index
                errors.append((index, message, compact_json(entry)))
                continue
            text = entry.get("text")
            if not isinstance(text, str) or not text:
                continue
            row = self.base_row(artifact)
            row.turn_type = "user"
            row.project_path = project
            row.source_line = index
            stamp = entry.get("timestamp")
            row.timestamp_utc = to_utc(stamp) if isinstance(stamp, str) else ""
            row.text = text
            yield row
        yield from error_rows(self, artifact, errors, "", project)

    # -- conversation context ---------------------------------------------------------
    def _conversation(self, cdir: Path) -> _Conv:
        def mtime(path: Path) -> int:
            try:
                return path.stat().st_mtime_ns
            except OSError:
                return 0

        key = (
            str(cdir),
            mtime(cdir / "meta.json"),
            mtime(cdir / "base_state.json"),
            mtime(cdir / "events"),
        )
        conv = self._cache.get(key)
        if conv is None:
            conv = self._load_conversation(cdir)
            if len(self._cache) > 256:
                self._cache.clear()
            self._cache[key] = conv
        return conv

    def _load_conversation(self, cdir: Path) -> _Conv:
        conv = _Conv(session_id=cdir.name)
        meta = _load_object(cdir / "meta.json", conv.problems)
        state = _load_object(cdir / "base_state.json", conv.problems)
        conv.project_path = str(
            _dict_or_empty(meta.get("workspace")).get("working_dir")
            or _dict_or_empty(state.get("workspace")).get("working_dir")
            or ""
        )
        conv.model = str(
            _dict_or_empty(_dict_or_empty(state.get("agent")).get("llm")).get("model") or ""
        )

        events: list[tuple[int, str]] = []
        try:
            for path in (cdir / "events").iterdir():
                match = EVENT_NAME_RX.match(path.name)
                if match and not path.is_symlink():
                    events.append((int(match.group(1)), path.name))
        except OSError:
            pass
        events.sort()
        conv.first_event = events[0][1] if events else ""
        loaded = [
            (fname, _dict_or_empty(_read_json(cdir / "events" / fname))) for _, fname in events
        ]
        first = loaded[0][1] if loaded else {}
        _track_models(conv, state, loaded)
        conv.settings = _settings(state, conv.actions)
        conv.scratch = _scratch(conv.project_path)

        created = _aware(meta.get("created_at"))
        naive_first = _naive(first.get("timestamp"))
        if created is not None and naive_first is not None:
            diff = (naive_first.replace(tzinfo=timezone.utc) - created).total_seconds()
            offset = int((diff + SKEW) // QUARTER) * QUARTER
            if abs(offset) <= MAX_OFFSET:
                conv.offset = offset
        if created is not None:
            conv.created = to_utc(meta.get("created_at"))
        else:
            conv.created = self._timestamp(first.get("timestamp"), conv)

        if conv.offset is not None:
            basis = (
                "event times are host local, corrected by %s from meta.json created_at"
                % _fmt_offset(conv.offset)
            )
        elif naive_first is not None:
            basis = "event times are host local with no zone, emitted as if UTC"
        else:
            basis = ""
        conv.header = _join(
            "conversation start",
            str(meta.get("title") or ""),
            "id=%s" % meta["id"] if meta.get("id") else "",
            "parent=%s" % meta["parent_conversation_id"]
            if meta.get("parent_conversation_id")
            else "",
            "forked_from=%s" % meta["forked_from_conversation_id"]
            if meta.get("forked_from_conversation_id")
            else "",
            "model=%s" % (conv.initial_model or conv.model)
            if conv.initial_model or conv.model
            else "",
            "status=%s" % state["execution_status"] if state.get("execution_status") else "",
            "%d events" % len(events),
            basis,
        )
        return conv

    @staticmethod
    def _timestamp(value, conv: _Conv) -> str:
        naive = _naive(value)
        if naive is not None and conv.offset is not None:
            return to_utc((naive - timedelta(seconds=conv.offset)).isoformat() + "+00:00")
        return to_utc(value) if isinstance(value, str) else ""

    def _row(self, artifact: Artifact, conv: _Conv, turn_type: str) -> Row:
        row = self.base_row(artifact)
        row.session_id = conv.session_id
        row.project_path = conv.project_path
        row.model = conv.model
        row.turn_type = turn_type
        row.source_line = 1
        return row

    # -- events -----------------------------------------------------------------------
    def _event_rows(
        self, artifact: Artifact, conv: _Conv, event: dict, opts: Options
    ) -> Iterator[Row]:
        kind = str(event.get("kind") or "")

        def make_row(turn_type: str, text: str, tool_name: str = "", tool_use_id: str = "") -> Row:
            row = self._row(artifact, conv, turn_type)
            row.tool_name, row.tool_use_id = tool_name, tool_use_id
            row.text = compact(text)
            return row

        if kind == "MessageEvent":
            msg = _dict_or_empty(event.get("llm_message"))
            role = str(msg.get("role") or event.get("source") or "")
            if opts.include_thinking:
                thinking = _thinking(msg)
                if thinking:
                    yield make_row("thinking", thinking)
            text = text_of(msg.get("content"))
            if role == "tool":
                yield make_row(
                    "tool_result",
                    text,
                    str(msg.get("name") or ""),
                    str(msg.get("tool_call_id") or ""),
                )
            elif text or role in ("user", "system"):
                yield make_row(role if role in ("user", "assistant", "system") else "system", text)
            for call in msg.get("tool_calls") or []:
                call = _dict_or_empty(call)
                function = _dict_or_empty(call.get("function"))
                yield make_row(
                    "tool_use",
                    str(call.get("arguments") or function.get("arguments") or ""),
                    str(call.get("name") or function.get("name") or ""),
                    str(call.get("id") or ""),
                )
        elif kind == "ActionEvent":
            if opts.include_thinking:
                thinking = _join(text_of(event.get("thought")), _thinking(event))
                if thinking:
                    yield make_row("thinking", thinking)
            risk = event.get("security_risk")
            yield make_row(
                "tool_use",
                _action_text(event)
                + (" security_risk=%s" % risk if risk not in (None, "") else ""),
                str(event.get("tool_name") or ""),
                str(event.get("tool_call_id") or ""),
            )
        elif kind == "ObservationEvent":
            obs = _dict_or_empty(event.get("observation"))
            text = text_of(obs.get("content"))
            if obs.get("is_error"):
                text = "[error] " + text
            yield make_row(
                "tool_result",
                text,
                str(event.get("tool_name") or ""),
                str(event.get("tool_call_id") or ""),
            )
        elif kind == "UserRejectObservation":
            tool_name, tool_use_id = (
                str(event.get("tool_name") or ""),
                str(event.get("tool_call_id") or ""),
            )
            yield make_row(
                "tool_result",
                "[rejected by %s] %s"
                % (event.get("rejection_source") or "user", event.get("rejection_reason") or ""),
                tool_name,
                tool_use_id,
            )
            yield make_row(
                "system",
                _join_space(
                    "permission decision: rejected rejection_source=%s"
                    % (event.get("rejection_source") or "-"),
                    str(event.get("rejection_reason") or ""),
                ),
                tool_name,
                tool_use_id,
            )
        elif kind == "AgentErrorEvent":
            yield make_row(
                "tool_result",
                "[error] %s" % (event.get("error") or ""),
                str(event.get("tool_name") or ""),
                str(event.get("tool_call_id") or ""),
            )
        elif kind == "ACPToolCallEvent":
            name, call_id = (
                str(event.get("tool_kind") or "acp"),
                str(event.get("tool_call_id") or ""),
            )
            raw_in = event.get("raw_input")
            yield make_row(
                "tool_use",
                _join(
                    str(event.get("title") or ""),
                    compact_json(raw_in) if raw_in is not None else "",
                ),
                name,
                call_id,
            )
            out = event.get("raw_output")
            out_text = _join(
                out if isinstance(out, str) else compact_json(out) if out is not None else "",
                text_of(event.get("content")) if isinstance(event.get("content"), list) else "",
            )
            if out_text or event.get("status") in ("completed", "failed"):
                if event.get("is_error") or event.get("status") == "failed":
                    out_text = "[error] " + out_text
                yield make_row("tool_result", out_text, name, call_id)
        elif kind == "SystemPromptEvent":
            tools = event.get("tools")
            yield make_row(
                "system",
                "system prompt, %d tools: %s"
                % (
                    len(tools) if isinstance(tools, list) else 0,
                    text_of(event.get("system_prompt")),
                ),
            )
        elif kind in ("Condensation", "CondensationSummaryEvent"):
            forgotten = event.get("forgotten_event_ids")
            yield make_row(
                "system",
                _join(
                    "%s:" % kind,
                    "%d events forgotten" % len(forgotten) if isinstance(forgotten, list) else "",
                    str(event.get("summary") or ""),
                ),
            )
        elif kind == "HookExecutionEvent":
            yield make_row(
                "system",
                _join(
                    "hook %s: %s"
                    % (event.get("hook_event_type") or "", event.get("hook_command") or ""),
                    "exit=%s" % event["exit_code"] if event.get("exit_code") is not None else "",
                    "blocked" if event.get("blocked") else "",
                    str(event.get("stderr") or ""),
                ),
            )
        elif kind == "ConversationStateUpdateEvent":
            # The full_state value is a whole ConversationState, secrets
            # included; only its key is reported.
            value = event.get("value")
            shown = (
                ""
                if isinstance(value, (dict, list)) or event.get("key") == "full_state"
                else str(value)
            )
            yield make_row(
                "system",
                "state update: %s%s" % (event.get("key") or "", "=" + shown if shown else ""),
            )
        elif kind == "SecurityAnalysisEvent" and _dict_or_empty(event.get("risks")):
            details = _dict_or_empty(event.get("details"))
            for action_id, risk in _dict_or_empty(event.get("risks")).items():
                tool_name, tool_use_id = conv.actions.get(str(action_id), ("", ""))
                detail = details.get(action_id)
                yield make_row(
                    "system",
                    _join_space(
                        "permission decision: analyzed risk=%s analyzer=%s policy=%s"
                        % (risk, event.get("analyzer") or "-", event.get("policy") or "-"),
                        "" if tool_use_id else "action_id=%s" % action_id,
                        "details=%s" % compact_json(detail) if detail else "",
                    ),
                    tool_name,
                    tool_use_id,
                )
        else:
            rest = {
                key: item
                for key, item in event.items()
                if key not in ("kind", "id", "timestamp", "source", "parent_id")
            }
            yield make_row(
                "system", _join("%s:" % (kind or "event"), compact_json(rest) if rest else "")
            )

    # -- legacy 0.x ---------------------------------------------------------------------
    def _parse_legacy(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        match = LEGACY_RX.match(artifact.rel)
        assert match is not None  # parse() routes only matching paths here
        mine = int(match.group(2))
        numbers = []
        try:
            for path in artifact.disk_path.parent.iterdir():
                if path.suffix == ".json" and path.stem.isdigit() and not path.is_symlink():
                    numbers.append(int(path.stem))
        except OSError:
            pass
        if numbers and mine != min(numbers):
            return
        event = _dict_or_empty(_read_json(artifact.disk_path))
        row = self.base_row(artifact)
        row.session_id = match.group(1)
        row.turn_type = "system"
        row.source_line = 1
        row.timestamp_utc = (
            to_utc(event.get("timestamp")) if isinstance(event.get("timestamp"), str) else ""
        )
        row.text = compact(
            "legacy OpenHands 0.x session, %d event files, not parsed; "
            "times are host local, emitted as if UTC" % len(numbers),
        )
        yield row


def _project_for_hash(root: Path, digest: str) -> str:
    """The `workspace.working_dir` of a conversation under `root` (the
    `.openhands` directory) whose SHA-256 is `digest`, the name the CLI gives
    a project's directory under `projects/`; "" when none matches."""
    for pattern in CONVERSATION_GLOBS:
        try:
            paths = sorted(root.glob(pattern))
        except OSError:
            continue
        for path in paths:
            working_dir = _dict_or_empty(_dict_or_empty(_read_json(path)).get("workspace")).get(
                "working_dir"
            )
            if isinstance(working_dir, str) and working_dir and _sha256(working_dir) == digest:
                return working_dir
    return ""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scratch(working_dir: str) -> str:
    """The `scratch directory:` row text for a working directory under the
    Agent Server's default worktree root, else ""."""
    for root in WORKTREE_ROOTS:
        if working_dir.startswith(root) and working_dir[len(root) :].strip("/"):
            return (
                "scratch directory: %s (conversation worktree under the Agent Server's "
                "default conversation_worktree_root /tmp/conversation-worktrees)" % working_dir
            )
    return ""


def _track_models(conv: _Conv, state: dict, loaded: list[tuple[str, dict]]) -> None:
    """Fill the conversation's model rows and its ActionEvent map from the
    event files in index order: the model of each response from
    `stats.usage_to_metrics.*.token_usages[]` joined on the event's
    `llm_response_id`, the agent's own switches from `SwitchLLMObservation`
    and `ClassifyAndSwitchLLMObservation` (`active_model`), and a final row
    when `base_state.json` `agent.llm.model` differs from the last model the
    events show, since a switch over REST leaves no event."""
    by_response: dict[str, str] = {}
    for metrics in _dict_or_empty(
        _dict_or_empty(state.get("stats")).get("usage_to_metrics")
    ).values():
        for usage in _dict_or_empty(metrics).get("token_usages") or []:
            usage = _dict_or_empty(usage)
            rid, model = usage.get("response_id"), usage.get("model")
            if isinstance(rid, str) and rid and isinstance(model, str) and model:
                by_response.setdefault(rid, model)

    initial, switched = "", False
    for _, event in loaded:
        if _switch(event)[0]:
            switched = True
            break
        initial = by_response.get(str(event.get("llm_response_id") or ""), "")
        if initial:
            break
    if not initial and not switched:
        initial = conv.model
    conv.initial_model = current = initial
    for fname, event in loaded:
        if event.get("kind") == "ActionEvent" and event.get("id"):
            conv.actions[str(event["id"])] = (
                str(event.get("tool_name") or ""),
                str(event.get("tool_call_id") or ""),
            )
        model = by_response.get(str(event.get("llm_response_id") or ""), "")
        if model and model != current:
            conv.model_before[fname] = _model_text(current, model)
            current = model
        conv.event_model[fname] = current
        new, suffix = _switch(event)
        if new and new != current:
            conv.model_after[fname] = (_model_text(current, new) + suffix, new)
            current = new
    if conv.model and current and conv.model != current:
        conv.final_model_row = "%s (from base_state.json agent.llm, file mtime)" % _model_text(
            current, conv.model
        )


def _model_text(old: str, new: str) -> str:
    return "model: %s -> %s" % (old, new) if old else "model: %s" % new


def _switch(event: dict) -> tuple[str, str]:
    """(new model, ` profile=<name>[ class=<chosen_class>]`) for a successful
    switch observation, else ("", "")."""
    obs = _dict_or_empty(event.get("observation"))
    if event.get("kind") != "ObservationEvent" or obs.get("kind") not in SWITCH_KINDS:
        return "", ""
    new = obs.get("active_model")
    if obs.get("is_error") or not isinstance(new, str) or not new:
        return "", ""
    profile = obs.get("profile_name") or obs.get("model")
    suffix = " profile=%s" % profile if isinstance(profile, str) and profile else ""
    if obs.get("chosen_class"):
        suffix += " class=%s" % obs["chosen_class"]
    return new, suffix


def _settings(state: dict, actions: dict[str, tuple[str, str]]) -> list[tuple[str, str, str]]:
    """(text, tool_name, tool_use_id) of each `permission setting:` row of
    base_state.json: the confirmation policy, the security analyzer (`none`
    when the key is absent, since the file is written with `exclude_none`)
    and one row per hook-blocked action, joined to its tool call when the
    events name the action."""
    if not state:
        return []
    tail = " (from base_state.json, file mtime)"
    out: list[tuple[str, str, str]] = []
    policy = _dict_or_empty(state.get("confirmation_policy"))
    if policy.get("kind"):
        text = "permission setting: confirmation_policy=%s" % policy["kind"]
        if policy.get("threshold"):
            text += " threshold=%s" % policy["threshold"]
        if "confirm_unknown" in policy:
            text += " confirm_unknown=%s" % setting_value(policy["confirm_unknown"])
        out.append((text + tail, "", ""))
    analyzer = _dict_or_empty(state.get("security_analyzer")).get("kind") or "none"
    out.append(("permission setting: security_analyzer=%s%s" % (analyzer, tail), "", ""))
    for action_id, reason in _dict_or_empty(state.get("blocked_actions")).items():
        tool_name, tool_use_id = actions.get(str(action_id), ("", ""))
        text = "permission setting: blocked_actions.%s=%s%s" % (
            action_id,
            setting_value(reason),
            tail,
        )
        out.append((text, tool_name, tool_use_id))
    return out


def _join_space(*parts: str) -> str:
    return " ".join(part for part in parts if part)


def _thinking(rec: dict) -> str:
    parts = []
    if isinstance(rec.get("reasoning_content"), str):
        parts.append(rec["reasoning_content"])
    for block in rec.get("thinking_blocks") or []:
        if isinstance(block, dict) and isinstance(block.get("thinking"), str):
            parts.append(block["thinking"])
    return _join(*parts)


def _action_text(event: dict) -> str:
    """The command for a terminal action, `<command> <path>` for a file
    editor action, else the call's JSON arguments."""
    action = _dict_or_empty(event.get("action"))
    cmd, path = action.get("command"), action.get("path")
    if isinstance(path, str) and path:
        return "%s %s" % (cmd, path) if isinstance(cmd, str) and cmd else path
    if isinstance(cmd, str) and cmd:
        return cmd
    args = _dict_or_empty(event.get("tool_call")).get("arguments")
    if isinstance(args, str) and args:
        return args
    rest = {key: value for key, value in action.items() if key != "kind"}
    return compact_json(rest) if rest else str(action.get("kind") or "")
