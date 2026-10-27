"""Muse Code (Meta) session logs.

Closed source. Validated against the shipped Linux binary 1.4.2-R4684.1
(serde field names from `strings`), the vendor skills unpacked beside it
(`read-session/SKILL.md`, `doctor/scripts/session-evidence.py`) and a real
install on Linux, October 2026, with a synthetic fixture; see
`research/muse-code.md`. Files, relative to the home (the same layout on
macOS and Windows, which resolve `XDG_DATA_HOME` or the home):

* `.local/share/muse/sessions/YYYY/MM/DD/<session id>/session.jsonl` and
  `.../<session id>/subagent/<child id>/session.jsonl` (one log per
  subagent, same format). One JSON object per line, three shapes:
  - envelope: `stream.id` (session id, or the subagent's own id),
    `recorded_at` (integer microseconds since the epoch, UTC),
    `payload_type`, `payload`.
  - `retained_frame`: `children[].child_index`, `children[].record_json`
    (a JSON string holding a whole envelope; the observed children are the
    permission records below).
  - `retained_marker`: a placeholder for a live-only record; skipped.
  A file whose first parseable record is neither an envelope nor a frame
  is not Muse and gives no rows.
* `payload_type: "runtime.session"`, `payload.kind: "run"`, `payload.run_id`,
  `payload.event.kind`:
  - `started` (`prompt`): `user` in a top-level log, `system` in a
    subagent log (the task the runtime gave the child).
  - `inbox_item_queued` (`source.source`, `payload.prompt`, `body`,
    `summary`): `user` when the source is `user_steer`, else `system`.
  - `assistant_message_committed` (`text`): `assistant`.
  - `reasoning_summary_committed` (`message_id`, `text`) and
    `reasoning_committed` with non-empty `text`: `thinking`, only with
    `include_thinking`. `reasoning_summary_delta` (`message_id`, `text`)
    repeats the committed record and is skipped, unless its `message_id`
    has no committed record (a cut log): then the deltas joined by a blank
    line give one `thinking` row at the last delta.
  - `assistant_tool_calls_committed` (`tool_calls[].name`, `.call_id`,
    `.args`, a JSON string or an object): one `tool_use` each.
  - `tool_result_batch_committed` (`results[].tool_call_id`, `.text`), and
    the alternative names `tool_results_committed`, `tool_result_committed`
    and `tool_result` (`tool_call_id` or `call_id`; `text`, `output`,
    `result`, `tool_result_model_visible_content` or `content`): one
    `tool_result` each, joined on the call id. A result `text` that decodes
    to an object with `output` (bash) gives that output, prefixed
    `[exit N]` when `exit_code` is non-zero.
  - `provider_tool_call_completed` (`call_id`, `status`, `action`,
    `results`): a `tool_use` and a `tool_result`, not observed on disk.
  - `terminal` (`terminal`, `reason`): a `system` row unless `completed`.
  - `context_compaction_installed`, `run_retracted`, `turn_task_died`:
    `system` rows with the event as compact JSON.
  - `model_completed` (`model`): the run's model when
    `run.model.configured` gave none (and then a model row, below).
* `payload.kind: "approval"`, all `system` rows carrying the tool name and
  call id: `requested` (`tool_name`, `tool_call_id`, `raw_args`,
  `pending_action_id`) is `approval requested: <raw_args>`;
  `automated_review_completed` (`assessment.outcome`, `.risk_level`,
  `.user_authorization`, `.rationale`, `status`) is `permission decision:
  <outcome> kind=automated_review_completed risk_level=<r>
  user_authorization=<u> status=<s> <rationale>`, joined to the latest
  request before it (the record names no pending action);
  `decision_applied` (`decision`, `decision_source.kind`, `policy_result`,
  `amendment`, `pending_action_id`, joined to the request) is
  `permission decision: <decision> source=<decision_source.kind>
  policy_result=<p> amendment=<a>`. A missing or null value is `-`. These
  rows stay at the record's place in the log, before the call's
  `tool_result`, because the decision precedes the execution.
* Permission mode (issue 97), tracked per log: a
  `runtime.session.permission_profile_committed` record (a frame child;
  `resolved_snapshot.approval`, `resolved_snapshot.reviewer`, `source.id`,
  `cause`) is `permission mode: approval=<a> reviewer=<r> profile=<id>`
  the first time and `permission mode: <old> -> <new>` on a change,
  followed by ` cause=<cause>` and ` format=<format>` from the
  `runtime.session.permission_format_declared` record (`format`) before it.
  `session.opened.observed` (`security_mode`) is tracked on its own as
  `permission mode: security_mode=<value>`.
* Model (issue 96), tracked per log: the first model named by
  `runtime.session.metadata` `model_id`, `run.model.configured`
  `model_id` or a run's `model_completed` `model` (when the run has no
  configured model) is `model: <id>`, and each different one later
  `model: <old> -> <new>`, followed by ` provider=<provider_id>` when the
  record has one. `runtime.model_reconfigure.completed` (a `/model`
  change; `effective.model_id`, `previous.model_id`, `apply_outcome`)
  first yields `model: <previous>` when no model was named yet, then
  `model: <old> -> <effective>` (even when unchanged, since the user typed
  it), followed by ` apply_outcome=<value>` when set; without an
  `effective.model_id` it is a `system` row of its compact JSON. The
  research lists `previous{...}` without its fields; `model_id` is read
  there because `effective` carries it.
* Fact records, read from `payload.record` then `payload`:
  `runtime.session.metadata` (`workspace_root`, `model_id`),
  `runtime.session.route_facts` (`cwd`, the project fallback),
  `session.workspace_branch.observed` (`reference.kind`, `reference.name`),
  `run.model.configured` (`model_id`, `run_stream.id` = the run id,
  `provider_id`) fill columns and give only the model rows above.
  `session.name.changed` (`new_name`) is a `system` row.
  `runtime.user_intent.accepted` (`intent_id`,
  `model_messages[].content[].text`) repeats the run's `started` prompt
  and is used only when that run has no `started` record.
  `user_shell.command` (`command_id`, `command_text`) and
  `user_shell.result` (`command_id`, `visible_output`, `exit_code`,
  `terminal_state`) are a `tool_use` and `tool_result` named `user_shell`;
  `subagent.control.spawn_accepted` and `.start_attested` are `system`
  rows of compact JSON. These three are binary field names only, not
  observed. Task, effect, telemetry and every unknown type are skipped.
* A subagent log records no workspace: its project path and branch come
  from the parent `session.jsonl` above its `subagent/` directory, read up
  to `PARENT_SCAN_LINES` lines.
* `.local/share/muse/tui-history.jsonl`: two lines per prompt, a JSON
  string (the text) then `{project, session}`. No timestamp. A secondary
  source (`dedup.py`): its rows have an empty `timestamp_utc`, so each
  matches a session row of the same session and text with no time
  constraint, and is kept only when no session row has the text.
* `.config/muse/trust.json` (`projects.<absolute path>.decision`): one
  `system` row per project, `permission setting:
  projects.<path>.decision=<decision> (from .config/muse/trust.json, file
  mtime)`, with `project_path` the path, `timestamp_utc` the file's
  modification time and `session_id` empty; a file that is not a JSON
  object is one `system` row. No other key is read. The `trust` key of
  `.config/muse/skills/.muse/lock.json` is not read: the research names
  the file's keys but not its structure.

Not read: `approval-review/*.jsonl` (the automated reviewer's log, on a
synthetic clock), `tool-outputs/`, `cli-*.log`, `.msp-view-v1/`, the
SQLite stores.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
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
    track_change,
)

SESSION_RX = re.compile(
    r"^\.local/share/muse/sessions/\d{4}/\d{2}/\d{2}/[^/]+/(?:subagent/[^/]+/)*session\.jsonl$"
)
HISTORY_REL = ".local/share/muse/tui-history.jsonl"
TRUST_REL = ".config/muse/trust.json"
PARENT_SCAN_LINES = 2000

ARG_KEYS = (
    "command",
    "cmd",
    "url",
    "query",
    "path",
    "file_path",
    "target_path",
    "target",
    "filename",
)
RESULT_KEYS = ("text", "output", "result", "tool_result_model_visible_content", "content")
RESULT_EVENTS = ("tool_result_batch_committed", "tool_results_committed", "tool_result_committed")
LOGGED_EVENTS = ("context_compaction_installed", "run_retracted", "turn_task_died")
SUBAGENT_CONTROL = ("subagent.control.spawn_accepted", "subagent.control.start_attested")


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _str(value) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else compact_json(value)


def _pair_value(value) -> str:
    """A field value in a `key=value` pair: `-` when missing or null."""
    return "-" if value in (None, "") else setting_value(value)


def _fact(payload: dict) -> dict:
    """A fact record's fields: `payload.record`, falling back to `payload`."""
    record = payload.get("record")
    return record if isinstance(record, dict) else payload


def micros_to_utc(value) -> str:
    """`recorded_at` is microseconds; `to_utc` reads large numbers as ms."""
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return to_utc(value / 1_000_000)
    if isinstance(value, str) and value.isdigit():
        return to_utc(int(value) / 1_000_000)
    return ""


def args_summary(args) -> str:
    if isinstance(args, str):
        try:
            decoded = json.loads(args)
        except ValueError:
            return args
        args = decoded
    if isinstance(args, dict):
        for k in ARG_KEYS:
            value = args.get(k)
            if value not in (None, ""):
                return _str(value)
        return compact_json(args)
    return _str(args)


def result_text(text) -> str:
    """A tool result's text; bash results are a JSON object with `output`."""
    if not isinstance(text, str):
        return _str(text)
    if text.startswith("{"):
        try:
            decoded = json.loads(text)
        except ValueError:
            return text
        if isinstance(decoded, dict) and "output" in decoded:
            out = _str(decoded.get("output"))
            code = decoded.get("exit_code")
            if code not in (None, 0):
                out = "[exit %s] %s" % (code, out)
            return out
    return text


def records(path, errors: list) -> Iterator[tuple[int, dict]]:
    """(line, envelope) for every envelope, frames unpacked in child order,
    markers dropped. Stops at once when the first record is not Muse."""
    first = True
    for line_number, record in iter_jsonl(path, errors):
        if first:
            first = False
            if "retained_frame" not in record and not (
                "stream" in record and "payload_type" in record
            ):
                return
        if "retained_marker" in record:
            continue
        if "retained_frame" in record:
            children = [item for item in record.get("children") or [] if isinstance(item, dict)]
            children.sort(key=lambda item: item.get("child_index") or 0)
            for entry in children:
                child = entry.get("record_json")
                try:
                    inner = json.loads(child or "")
                except (TypeError, ValueError) as error:
                    raw = child if isinstance(child, str) else ""
                    errors.append(
                        (line_number, "unparseable line (retained_frame child: %s)" % error, raw)
                    )
                    continue
                if isinstance(inner, dict):
                    yield line_number, inner
            continue
        yield line_number, record


def workspace(log_records: Iterable[tuple[int, dict]], limit: int = 0) -> tuple[str, str]:
    """(project path, branch) from a session log's records: the last
    metadata `workspace_root` (else `route_facts` `cwd`) and the last branch
    name. `limit` caps the lines read (0 reads them all)."""
    project = cwd = branch = ""
    for line_number, record in log_records:
        if limit and line_number > limit:
            break
        payload_type = record.get("payload_type")
        payload = _dict(record.get("payload"))
        fact = _fact(payload)
        if payload_type == "runtime.session.metadata":
            workspace_root = fact.get("workspace_root") or payload.get("workspace_root")
            if workspace_root:
                project = str(workspace_root)
        elif payload_type == "runtime.session.route_facts" and fact.get("cwd"):
            cwd = str(fact.get("cwd"))
        elif payload_type == "session.workspace_branch.observed":
            reference = _dict(fact.get("reference"))
            if reference.get("kind") == "branch" and reference.get("name"):
                branch = str(reference.get("name"))
    return project or cwd, branch


class MuseCodeParser(Parser):
    agent = "muse-code"
    name = "muse-code"
    has_secondary = True

    def __init__(self) -> None:
        self._parent_cache: dict[Path, tuple[str, str]] = {}

    def wants(self, artifact: Artifact) -> bool:
        return artifact.rel in (HISTORY_REL, TRUST_REL) or bool(SESSION_RX.match(artifact.rel))

    def secondary(self, artifact: Artifact) -> bool:
        return artifact.rel == HISTORY_REL

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        if artifact.rel == HISTORY_REL:
            yield from self._parse_history(artifact, opts)
        elif artifact.rel == TRUST_REL:
            yield from self._parse_trust(artifact)
        else:
            yield from self._parse_session(artifact, opts)

    # -- session logs -------------------------------------------------------

    def _parent_workspace(self, artifact: Artifact) -> tuple[str, str]:
        """Project and branch of the nearest ancestor log that has them,
        walking up through `subagent/<id>/` levels. Symlinks are not read."""
        directory = artifact.disk_path.parent
        while directory.parent.name == "subagent":
            directory = directory.parent.parent
            log = directory / "session.jsonl"
            if log.is_symlink() or not log.is_file():
                continue
            if log not in self._parent_cache:
                self._parent_cache[log] = workspace(records(log, []), PARENT_SCAN_LINES)
            found = self._parent_cache[log]
            if found[0]:
                return found
        return "", ""

    def _parse_session(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        errors: list = []
        log_records = list(records(artifact.disk_path, errors))
        if not log_records:
            yield from error_rows(self, artifact, errors)
            return
        is_subagent = "/subagent/" in artifact.rel

        # Pre-pass: values a row may need before the record that sets them.
        run_model: dict[str, str] = {}
        run_completed_model: dict[str, str] = {}
        started_runs: set[str] = set()
        committed_summaries: set[str] = set()
        last_delta: dict[str, int] = {}
        session_model = ""
        for i, (_, record) in enumerate(log_records):
            payload_type = record.get("payload_type")
            payload = _dict(record.get("payload"))
            fact = _fact(payload)
            if payload_type == "run.model.configured":
                run_key = _dict(fact.get("run_stream")).get("id")
                if run_key and fact.get("model_id"):
                    run_model[str(run_key)] = str(fact.get("model_id"))
            elif (
                payload_type == "runtime.session.metadata"
                and fact.get("model_id")
                and not session_model
            ):
                session_model = str(fact.get("model_id"))
            elif payload_type == "runtime.session" and payload.get("kind") == "run":
                event = _dict(payload.get("event"))
                run_key = str(payload.get("run_id") or "")
                kind = event.get("kind")
                if kind == "started":
                    started_runs.add(run_key)
                elif kind == "model_completed" and event.get("model"):
                    run_completed_model.setdefault(run_key, str(event.get("model")))
                elif kind == "reasoning_summary_committed":
                    committed_summaries.add(str(event.get("message_id") or ""))
                elif kind == "reasoning_summary_delta":
                    last_delta[str(event.get("message_id") or "")] = i

        # Defaults for rows before the first metadata record; a subagent log
        # records no workspace of its own and takes its parent's.
        project, branch = workspace(log_records)
        if is_subagent and not project:
            project, branch = self._parent_workspace(artifact)
        session_id = ""
        deltas: dict[str, list[str]] = {}
        calls: dict[str, str] = {}
        approvals: dict[str, tuple[str, str]] = {}
        last_request: tuple[str, str] = ("", "")
        shell_ids: list[str] = []
        models: dict = {}
        modes: dict = {}
        declared_format = ""

        for i, (line_number, record) in enumerate(log_records):
            payload_type = record.get("payload_type")
            payload = _dict(record.get("payload"))
            fact = _fact(payload)
            stream_id = _dict(record.get("stream")).get("id")
            if stream_id and not session_id:
                session_id = str(stream_id)
            run_id = str(payload.get("run_id") or "")
            model = run_model.get(run_id) or run_completed_model.get(run_id) or session_model

            def make_row(
                turn: str,
                text: str,
                tool_name: str = "",
                tool_use_id: str = "",
                source_line=line_number,
                record=record,
                model=model,
                session_id=session_id,
                project=project,
                branch=branch,
            ) -> Row:
                row = self.base_row(artifact)
                row.source_line = source_line
                row.timestamp_utc = micros_to_utc(record.get("recorded_at"))
                row.session_id = session_id
                row.project_path = project
                row.git_branch = branch
                row.model = model
                row.turn_type = turn
                row.tool_name = tool_name
                row.tool_use_id = tool_use_id
                row.text = compact(text)
                return row

            if payload_type == "runtime.session.metadata":
                if fact.get("model_id"):
                    session_model = str(fact.get("model_id"))
                    yield from self._model_row(make_row, models, session_id, session_model, fact)
                workspace_root = fact.get("workspace_root") or payload.get("workspace_root")
                if workspace_root:
                    project = str(workspace_root)
            elif payload_type == "run.model.configured" and fact.get("model_id"):
                yield from self._model_row(
                    make_row, models, session_id, str(fact["model_id"]), fact
                )
            elif payload_type == "runtime.session.permission_format_declared":
                declared_format = _str(fact.get("format"))
            elif payload_type == "runtime.session.permission_profile_committed":
                snapshot = _dict(fact.get("resolved_snapshot"))
                value = "approval=%s reviewer=%s profile=%s" % (
                    _pair_value(snapshot.get("approval")),
                    _pair_value(snapshot.get("reviewer")),
                    _pair_value(_dict(fact.get("source")).get("id")),
                )
                text = track_change("permission mode", modes, session_id, value)
                if text:
                    if fact.get("cause") not in (None, ""):
                        text += " cause=%s" % _pair_value(fact.get("cause"))
                    if declared_format:
                        text += " format=%s" % declared_format
                    yield make_row("system", text)
            elif payload_type == "session.opened.observed" and fact.get("security_mode") not in (
                None,
                "",
            ):
                text = track_change(
                    "permission mode",
                    modes,
                    (session_id, "security_mode"),
                    "security_mode=%s" % _pair_value(fact.get("security_mode")),
                )
                if text:
                    yield make_row("system", text)
            elif payload_type == "session.workspace_branch.observed":
                reference = _dict(fact.get("reference"))
                branch = (
                    str(reference.get("name") or "") if reference.get("kind") == "branch" else ""
                )
            elif payload_type == "session.name.changed":
                yield make_row("system", "session name: %s" % _str(fact.get("new_name")))
            elif payload_type == "runtime.model_reconfigure.completed":
                effective_model = _str(_dict(fact.get("effective")).get("model_id"))
                previous = _str(_dict(fact.get("previous")).get("model_id"))
                if not effective_model:
                    yield make_row("system", "%s: %s" % (payload_type, compact_json(fact)))
                    continue
                session_model = effective_model
                if previous and session_id not in models:
                    yield make_row(
                        "system",
                        track_change("model", models, session_id, previous),
                        model=previous,
                    )
                # A `/model` the user typed keeps its row even when the model
                # did not change.
                text = track_change(
                    "model", models, session_id, effective_model
                ) or "model: %s -> %s" % (effective_model, effective_model)
                if fact.get("apply_outcome") not in (None, ""):
                    text += " apply_outcome=%s" % _pair_value(fact.get("apply_outcome"))
                yield make_row("system", text, model=effective_model)
            elif payload_type == "runtime.user_intent.accepted":
                intent = str(payload.get("intent_id") or "")
                if intent and intent not in started_runs:
                    parts = []
                    for message in payload.get("model_messages") or []:
                        for block in _dict(message).get("content") or []:
                            block_text = _dict(block).get("text")
                            if isinstance(block_text, str):
                                parts.append(block_text)
                    if parts:
                        yield make_row(
                            "system" if is_subagent else "user",
                            "\n".join(parts),
                            model=run_model.get(intent) or model,
                        )
            elif payload_type == "user_shell.command":
                command_id = _str(fact.get("command_id"))
                shell_ids.append(command_id)
                yield make_row("tool_use", _str(fact.get("command_text")), "user_shell", command_id)
            elif payload_type == "user_shell.result":
                command_id = _str(fact.get("command_id")) or (shell_ids[-1] if shell_ids else "")
                out = _str(fact.get("visible_output"))
                notes = []
                if fact.get("exit_code") not in (None, 0):
                    notes.append("exit %s" % fact.get("exit_code"))
                state = fact.get("terminal_state")
                if state and state != "completed":
                    notes.append(str(state))
                if notes:
                    out = "[%s] %s" % (", ".join(notes), out)
                yield make_row("tool_result", out, "user_shell", command_id)
            elif payload_type in SUBAGENT_CONTROL:
                yield make_row("system", "%s: %s" % (payload_type, compact_json(fact)))
            elif payload_type == "runtime.session":
                kind = payload.get("kind")
                event = _dict(payload.get("event"))
                if kind == "run":
                    if (
                        event.get("kind") == "model_completed"
                        and event.get("model")
                        and run_id not in run_model
                    ):
                        yield from self._model_row(
                            make_row, models, session_id, str(event["model"]), {}
                        )
                    yield from self._run_event(
                        event,
                        i,
                        make_row,
                        opts,
                        is_subagent,
                        calls,
                        deltas,
                        committed_summaries,
                        last_delta,
                    )
                elif kind == "approval":
                    event_kind = event.get("kind")
                    if event_kind == "requested":
                        tool_name = _str(event.get("tool_name"))
                        tool_id = _str(event.get("tool_call_id"))
                        approvals[_str(event.get("pending_action_id"))] = (tool_name, tool_id)
                        last_request = (tool_name, tool_id)
                        yield make_row(
                            "system",
                            "approval requested: %s" % _str(event.get("raw_args")),
                            tool_name,
                            tool_id,
                        )
                    elif event_kind == "automated_review_completed":
                        assessment = _dict(event.get("assessment"))
                        text = (
                            "permission decision: %s kind=automated_review_completed "
                            "risk_level=%s user_authorization=%s status=%s"
                            % (
                                _pair_value(assessment.get("outcome")),
                                _pair_value(assessment.get("risk_level")),
                                _pair_value(assessment.get("user_authorization")),
                                _pair_value(event.get("status")),
                            )
                        )
                        if assessment.get("rationale") not in (None, ""):
                            text += " " + _str(assessment.get("rationale"))
                        yield make_row("system", text, *last_request)
                    elif event_kind == "decision_applied":
                        tool_name, tool_id = approvals.get(
                            _str(event.get("pending_action_id")), ("", "")
                        )
                        yield make_row(
                            "system",
                            "permission decision: %s source=%s policy_result=%s amendment=%s"
                            % (
                                _pair_value(event.get("decision")),
                                _pair_value(_dict(event.get("decision_source")).get("kind")),
                                _pair_value(event.get("policy_result")),
                                _pair_value(event.get("amendment")),
                            ),
                            tool_name,
                            tool_id,
                        )
            # Task and effect records, telemetry, permission records and
            # unknown payload types are bookkeeping: no row.

        for error_row in error_rows(self, artifact, errors, session_id, project):
            error_row.git_branch = branch
            yield error_row

    @staticmethod
    def _model_row(row, models: dict, session_id: str, model: str, fact: dict) -> Iterator[Row]:
        """`model: <id>` at the log's first model and `model: <old> -> <new>`
        on a change, with ` provider=<provider_id>` when the record has one."""
        text = track_change("model", models, session_id, model)
        if text:
            if fact.get("provider_id") not in (None, ""):
                text += " provider=%s" % _pair_value(fact.get("provider_id"))
            yield row("system", text, model=model)

    # -- trusted projects ---------------------------------------------------

    def _parse_trust(self, artifact: Artifact) -> Iterator[Row]:
        """`~/.config/muse/trust.json`: one `permission setting:` row per
        `projects.<path>.decision`, at the file's modification time."""
        timestamp = file_mtime(artifact)
        try:
            document = json.loads(artifact.disk_path.read_bytes().decode("utf-8", errors="replace"))
        except (OSError, ValueError):
            document = None
        if not isinstance(document, dict):
            row = self.base_row(artifact)
            row.source_line = 1
            row.turn_type = "system"
            row.timestamp_utc = timestamp
            row.text = "parser: trust.json is not a JSON object"
            yield row
            return
        projects = document.get("projects")
        if not isinstance(projects, dict):
            return
        for path, entry in projects.items():
            if not isinstance(entry, dict) or "decision" not in entry:
                continue
            row = self.base_row(artifact)
            row.source_line = 1
            row.turn_type = "system"
            row.timestamp_utc = timestamp
            row.project_path = str(path)
            row.text = compact(
                "permission setting: projects.%s.decision=%s (from %s, file mtime)"
                % (path, setting_value(entry["decision"]), artifact.rel)
            )
            yield row

    def _run_event(
        self,
        event: dict,
        i: int,
        row,
        opts: Options,
        is_subagent: bool,
        calls: dict[str, str],
        deltas: dict[str, list[str]],
        committed_summaries: set[str],
        last_delta: dict[str, int],
    ) -> Iterator[Row]:
        kind = event.get("kind")
        if kind == "started":
            prompt = _str(event.get("prompt"))
            if is_subagent:
                yield row("system", "subagent task: %s" % prompt)
            else:
                yield row("user", prompt)
        elif kind == "inbox_item_queued":
            source = _str(_dict(event.get("source")).get("source"))
            text = _str(_dict(event.get("payload")).get("prompt")) or _str(event.get("body"))
            if source == "user_steer":
                yield row("user", text)
            else:
                yield row("system", "inbox %s: %s" % (source, text or _str(event.get("summary"))))
        elif kind == "assistant_message_committed":
            text = _str(event.get("text"))
            if text:
                yield row("assistant", text)
        elif kind in ("reasoning_summary_committed", "reasoning_committed"):
            # reasoning_committed text was empty in every observed record;
            # its content is the opaque encrypted_content.
            if opts.include_thinking and event.get("text"):
                yield row("thinking", _str(event.get("text")))
        elif kind == "reasoning_summary_delta":
            message_id = _str(event.get("message_id"))
            if message_id in committed_summaries:
                return
            deltas.setdefault(message_id, []).append(_str(event.get("text")))
            if last_delta.get(message_id) == i and opts.include_thinking:
                yield row(
                    "thinking", "\n\n".join(delta for delta in deltas.pop(message_id) if delta)
                )
        elif kind == "assistant_tool_calls_committed":
            for call in event.get("tool_calls") or []:
                call = _dict(call)
                name = _str(call.get("name"))
                call_id = _str(call.get("call_id"))
                calls[call_id] = name
                yield row("tool_use", args_summary(call.get("args")), name, call_id)
        elif kind in RESULT_EVENTS or kind == "tool_result":
            results = event.get("results")
            items = results if isinstance(results, list) else [event]
            for result in items:
                result = _dict(result)
                call_id = _str(result.get("tool_call_id") or result.get("call_id"))
                raw = next((result[k] for k in RESULT_KEYS if result.get(k) is not None), "")
                yield row("tool_result", result_text(raw), calls.get(call_id, ""), call_id)
        elif kind == "provider_tool_call_completed":
            call_id = _str(event.get("call_id"))
            action = _dict(event.get("action"))
            name = _str(action.get("type")) or "provider_tool"
            calls[call_id] = name
            yield row("tool_use", args_summary(action) if action else "", name, call_id)
            text = compact_json(event.get("results")) if event.get("results") is not None else ""
            status = _str(event.get("status"))
            if status and status != "completed":
                text = "[%s] %s" % (status, text)
            yield row("tool_result", text, name, call_id)
        elif kind == "terminal":
            term = _str(event.get("terminal"))
            if term and term != "completed":
                yield row("system", "run %s: %s" % (term, _str(event.get("reason"))))
        elif kind in LOGGED_EVENTS:
            yield row("system", "%s: %s" % (kind, compact_json(event)))

    # -- prompt history -----------------------------------------------------

    def _parse_history(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        errors: list = []
        pending: tuple[int, str] | None = None

        def emit(line: int, text: str, meta: dict) -> Row:
            row = self.base_row(artifact)
            row.source_line = line
            row.turn_type = "user"
            row.session_id = _str(meta.get("session"))
            row.project_path = _str(meta.get("project"))
            row.text = compact(text)
            return row

        with open(artifact.disk_path, "rb") as handle:
            for line_number, raw in enumerate(handle, 1):
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped.decode("utf-8", errors="replace"))
                except ValueError as error:
                    errors.append((line_number, "unparseable line (%s)" % error, line_text(raw)))
                    continue
                if isinstance(record, str):
                    if pending is not None:
                        yield emit(pending[0], pending[1], {})
                    pending = (line_number, record)
                elif isinstance(record, dict) and pending is not None:
                    yield emit(pending[0], pending[1], record)
                    pending = None
        if pending is not None:
            yield emit(pending[0], pending[1], {})
        yield from error_rows(self, artifact, errors)
