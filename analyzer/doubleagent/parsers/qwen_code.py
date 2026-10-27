"""Parse Qwen Code sessions, prompt logs, settings, channel routes and usage records.

Follows `research/qwen-code.md`. Validated against source, QwenLM/qwen-code at
2c591ecc (0.24.7) and 5dcf7c7c (0.25.3: injected user records, settings, usage
records, `executionContext`, approval modes and tool-call telemetry), with a
synthetic fixture; no real install. Qwen Code forked Gemini CLI, but its
sessions are a Claude-Code-style record stream. Files read:

- `.qwen/projects/<cwd>/chats/[archive/]<sessionId>.jsonl`, one `ChatRecord`
  per line: `sessionId`, `timestamp`, `type`, `subtype`, `cwd`, `gitBranch`,
  `provenance`, `agentId`, `agentName`, `model`, `executionContext {modelId,
  authType, approvalMode}`, `systemPayload` and `message.parts[]` (`text`,
  `thought`, `functionCall`, `functionResponse`), `toolCallResult {callId,
  status, resultDisplay, errorType}`. A `user` record the user did not type
  (`injected_origin`) is a `system` row. `.ledger.jsonl` sidecars are skipped.
- `.qwen/tmp/<hash>/logs.json`, a JSON array of `{sessionId, messageId,
  timestamp, type, message}`, a secondary source (a file repeating the
  chats' events); `model_switch` entries give `model:` rows.
- `.qwen/trustedFolders.json`, read by the Gemini CLI parser's
  `trusted_folder_rows`.
- `.qwen/channels/sessions.json` and `channels/daemon/<hash>/routes.json`:
  one `session relayed:` row per route, since the conversation also sits on
  the messaging platform.
- `.qwen/settings.json` (home or project), read as JSONC: only
  `permissions.{allow,ask,deny}` and `tools.approvalMode`, since the file
  holds provider keys and channel tokens.
- `.qwen/usage_record.jsonl`, secondary: one `session usage:` row per line.

Model and approval mode are tracked per `sessionId`. Not parsed:
`checkpoint-<tag>.json` and `shell_history`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

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
    setting_value,
    tail_text,
    track_change,
)
from .gemini_cli import parse_jsonc, trusted_folder_rows

SESSION_RX = re.compile(r"^\.qwen/projects/[^/]+/chats/(?:archive/)?[^/]+\.jsonl$")
LOGS_RX = re.compile(r"^\.qwen/tmp/[^/]+/logs\.json$")
TRUSTED_RX = re.compile(r"^\.qwen/trustedFolders\.json$")
CHANNELS_RX = re.compile(r"^\.qwen/(channels/(?:sessions\.json|daemon/[^/]+/routes\.json))$")
# `~/.qwen/settings.json`, or a project's `.qwen/settings.json` (a project
# catalog file), for the standing permission rules.
SETTINGS_RX = re.compile(r"^\.qwen/settings\.json$")
USAGE_RX = re.compile(r"^\.qwen/usage_record\.jsonl$")
PERMISSION_LISTS = ("allow", "ask", "deny")
# `ToolCallEvent` as `logToolCall` records it in a `ui_telemetry` record,
# and the class's own default name, which an older build may have written.
TOOL_CALL_EVENTS = ("qwen-code.tool_call", "tool_call")
DECISION_STATUSES = ("cancelled", "awaiting_approval")
SIDECAR_SUFFIX = ".ledger.jsonl"
# `type: user` subtypes that never hold a prompt the user typed.
INJECTED_SUBTYPES = ("notification", "cron", "agent_message")

ARG_KEYS = (
    "command",
    "absolute_path",
    "file_path",
    "path",
    "pattern",
    "url",
    "query",
    "prompt",
    "description",
)


def args_summary(args) -> str:
    """Return the most identifying argument of a function call, else the arguments as JSON."""
    if isinstance(args, dict):
        for key in ARG_KEYS:
            value = args.get(key)
            if value not in (None, ""):
                return value if isinstance(value, str) else compact_json(value)
        return compact_json(args)
    if args in (None, ""):
        return ""
    return args if isinstance(args, str) else compact_json(args)


def _parts(rec: dict) -> list:
    msg = rec.get("message")
    if not isinstance(msg, dict):
        return []
    parts = msg.get("parts")
    return [part for part in parts if isinstance(part, dict)] if isinstance(parts, list) else []


def _response_text(response) -> str:
    if isinstance(response, dict):
        for key in ("output", "error", "llmContent"):
            value = response.get(key)
            if isinstance(value, str) and value:
                return value
        return compact_json(response)
    if response in (None, ""):
        return ""
    return response if isinstance(response, str) else compact_json(response)


def system_text(subtype: str, payload) -> str:
    """Return the row text of a `system` record: its subtype and a summary of its payload."""
    fields = payload if isinstance(payload, dict) else {}
    if subtype == "slash_command":
        detail = "%s %s" % (fields.get("phase") or "", fields.get("rawCommand") or "")
    elif subtype == "session_model":
        detail = "%s auth=%s" % (fields.get("modelId") or "", fields.get("authType") or "")
    elif subtype == "custom_title":
        detail = fields.get("customTitle") or ""
    elif subtype == "turn_result":
        detail = "%s %s" % (fields.get("state") or "", fields.get("resultText") or "")
    elif subtype == "rewind":
        detail = "truncated %s record(s)" % fields.get("truncatedCount")
    elif subtype == "chat_compression":
        detail = compact_json(fields.get("info")) if fields.get("info") is not None else ""
    else:
        detail = compact_json(payload) if payload else ""
    detail = str(detail).strip()
    return "%s: %s" % (subtype, detail) if detail else subtype


def injected_origin(rec: dict) -> str:
    """Return the row prefix of a `type: user` record the user did not type, else "".

    The prefix is `<subtype> (provenance=<provenance> agent=<agentName>
    agentId=<agentId>)`, with the parts not recorded left out. A record is
    the user's when its `provenance` is absent or `real_user`, unless its
    subtype is one only the system or another agent writes.
    """
    provenance = str(rec.get("provenance") or "")
    subtype = str(rec.get("subtype") or "")
    if provenance in ("", "real_user") and subtype not in INJECTED_SUBTYPES:
        return ""
    payload = rec.get("systemPayload")
    author = payload.get("author") if isinstance(payload, dict) else None
    author = author if isinstance(author, dict) else {}
    name = rec.get("agentName") or author.get("name")
    agent_id = rec.get("agentId") or author.get("agentId")
    keys = [
        "%s=%s" % (key, value)
        for key, value in (("provenance", provenance), ("agent", name), ("agentId", agent_id))
        if value not in (None, "")
    ]
    label = subtype or "user"
    return "%s (%s)" % (label, " ".join(keys)) if keys else label


class QwenCodeParser(Parser):
    """Parse Qwen Code's chat files, prompt logs, settings, routes and usage records."""

    agent = "qwen-code"
    name = "qwen-code"
    has_secondary = True
    records_relay = True

    def wants(self, artifact: Artifact) -> bool:
        """Return True for a chat file (not its ledger sidecar) or another read file."""
        rel = artifact.rel
        for pattern in (LOGS_RX, TRUSTED_RX, CHANNELS_RX, SETTINGS_RX, USAGE_RX):
            if pattern.match(rel):
                return True
        return bool(SESSION_RX.match(rel)) and not rel.endswith(SIDECAR_SUFFIX)

    def secondary(self, artifact: Artifact) -> bool:
        """Return True for a prompt log or the usage records."""
        return bool(LOGS_RX.match(artifact.rel) or USAGE_RX.match(artifact.rel))

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        """Yield the rows of one Qwen Code file."""
        channels = CHANNELS_RX.match(artifact.rel)
        if TRUSTED_RX.match(artifact.rel):
            yield from trusted_folder_rows(self, artifact)
        elif SETTINGS_RX.match(artifact.rel):
            yield from self._parse_settings(artifact)
        elif USAGE_RX.match(artifact.rel):
            yield from self._parse_usage(artifact)
        elif channels:
            yield from self._parse_channel_routes(artifact, channels.group(1))
        elif LOGS_RX.match(artifact.rel):
            yield from self._parse_logs(artifact, opts)
        else:
            yield from self._parse_session(artifact, opts)

    def _parse_channel_routes(self, artifact: Artifact, name: str) -> Iterator[Row]:
        """One `session relayed:` row per entry of a channel routes file."""
        try:
            doc = json.loads(artifact.disk_path.read_bytes().decode("utf-8", errors="replace"))
        except (OSError, ValueError):
            doc = None
        if not isinstance(doc, dict):
            yield from error_rows(self, artifact, [(0, "%s is not a JSON object" % name, "")])
            return
        mtime = ""
        errors: list = []
        for index, (key, entry) in enumerate(doc.items(), 1):
            if not isinstance(entry, dict):
                errors.append((index, "entry %s is not a JSON object" % key, ""))
                continue
            target = entry.get("target")
            target = target if isinstance(target, dict) else {}

            def value(key: str, target: dict = target) -> str:
                field = target.get(key)
                return str(field) if field not in (None, "") else "-"

            row = self.base_row(artifact)
            row.source_line = index
            row.turn_type = "system"
            row.session_id = str(entry.get("sessionId") or "")
            row.project_path = str(entry.get("cwd") or "")
            row.timestamp_utc = to_utc(entry.get("startedAt"))
            when = "startedAt"
            if not row.timestamp_utc:
                mtime = mtime or file_mtime(artifact)
                row.timestamp_utc, when = mtime, "file mtime"
            row.text = "session relayed: channel %s chat %s sender %s thread %s (from %s, %s)" % (
                value("channelName"),
                value("chatId"),
                value("senderId"),
                value("threadId"),
                name,
                when,
            )
            yield row
        yield from error_rows(self, artifact, errors)

    def _settings_row(self, artifact: Artifact, timestamp: str, project: str, text: str) -> Row:
        row = self.base_row(artifact)
        row.source_line = 1
        row.turn_type = "system"
        row.timestamp_utc = timestamp
        row.project_path = project
        row.text = compact(text)
        return row

    def _parse_settings(self, artifact: Artifact) -> Iterator[Row]:
        """Yield the permission rules and approval mode of a `settings.json`.

        One `permission setting:` row per `permissions.allow`, `ask` and
        `deny` rule and one for `tools.approvalMode`, read as JSONC as Qwen
        Code reads it; no other key is read, since the file can hold provider
        keys and channel tokens.
        """
        timestamp = file_mtime(artifact)
        project = artifact.home.original if artifact.home.project else ""
        try:
            doc = parse_jsonc(artifact.disk_path.read_bytes())
        except (OSError, ValueError):
            doc = None
        if not isinstance(doc, dict):
            text = "parser: %s is not a JSON object" % artifact.rel
            yield self._settings_row(artifact, timestamp, project, text)
            return
        settings: list = []
        perms = doc.get("permissions")
        perms = perms if isinstance(perms, dict) else {}
        for key in PERMISSION_LISTS:
            entries = perms.get(key)
            if isinstance(entries, list):
                settings.extend(("permissions." + key, entry) for entry in entries)
        tools = doc.get("tools")
        if isinstance(tools, dict) and tools.get("approvalMode") is not None:
            settings.append(("tools.approvalMode", tools["approvalMode"]))
        for key, value in settings:
            text = "permission setting: %s=%s (from %s, file mtime)" % (
                key,
                setting_value(value),
                artifact.rel,
            )
            yield self._settings_row(artifact, timestamp, project, text)

    def _parse_usage(self, artifact: Artifact) -> Iterator[Row]:
        """Yield one `session usage:` row per `usage_record.jsonl` line, at its `startTime`.

        The file survives the session's delete.
        """
        errors: list = []
        for line_number, rec in iter_jsonl(artifact.disk_path, errors):
            models = rec.get("models")
            tools = rec.get("tools")
            by_name = tools.get("byName") if isinstance(tools, dict) else None
            counts = [
                "%s=%s" % (name, stats.get("count") if isinstance(stats, dict) else stats)
                for name, stats in (by_name.items() if isinstance(by_name, dict) else ())
            ]
            row = self.base_row(artifact)
            row.source_line = line_number
            row.turn_type = "system"
            row.timestamp_utc = to_utc(rec.get("startTime"))
            row.session_id = str(rec.get("sessionId") or "")
            row.project_path = str(rec.get("project") or "")
            duration = rec.get("durationMs")
            row.text = compact(
                "session usage: project %s duration %s models %s tools %s"
                " (from usage_record.jsonl, startTime)"
                % (
                    row.project_path or "-",
                    "%sms" % duration if duration not in (None, "") else "-",
                    ",".join(models) if isinstance(models, dict) and models else "-",
                    ",".join(counts) or "-",
                )
            )
            yield row
        yield from error_rows(self, artifact, errors)

    @staticmethod
    def _context_changes(rec: dict, session_id: str, models: dict, modes: dict) -> list:
        """Return the `model:` and `permission mode:` changes a record's `executionContext` makes.

        Each item is (row text, model for the `model` column), for a model or
        mode that differs from the one in force for the session.
        """
        ctx = rec.get("executionContext")
        if not isinstance(ctx, dict):
            return []
        out = []
        model = str(ctx.get("modelId") or "")
        change = track_change("model", models, session_id, model)
        if change:
            auth = ctx.get("authType")
            out.append((change + (" auth=%s" % auth if auth else ""), model))
        mode = track_change(
            "permission mode", modes, session_id, str(ctx.get("approvalMode") or "")
        )
        if mode:
            out.append((mode, ""))
        return out

    def _parse_session(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        errors: list = []
        session_id = project_path = ""
        models: dict = {}  # session id -> model in force, for the model rows
        modes: dict = {}  # session id -> approval mode in force
        for line_number, rec in iter_jsonl(artifact.disk_path, errors):
            rtype = rec.get("type")
            if rec.get("sessionId"):
                session_id = str(rec["sessionId"])
            if rec.get("cwd"):
                project_path = str(rec["cwd"])

            def base(turn_type: str, text: str) -> Row:
                row = self.base_row(artifact)
                row.source_line = line_number
                row.timestamp_utc = to_utc(rec.get("timestamp"))
                row.session_id = session_id
                row.project_path = str(rec.get("cwd") or "")
                row.git_branch = str(rec.get("gitBranch") or "")
                row.turn_type = turn_type
                row.text = compact(text)
                return row

            for text, model in self._context_changes(rec, session_id, models, modes):
                row = base("system", text)
                row.model = model
                yield row
            parts = _parts(rec)
            if rtype == "user":
                text = "\n".join(
                    part["text"]
                    for part in parts
                    if isinstance(part.get("text"), str) and not part.get("thought")
                )
                if not text:
                    payload = rec.get("systemPayload")
                    if isinstance(payload, dict):
                        text = str(payload.get("displayText") or "")
                origin = injected_origin(rec)
                if origin:
                    yield base("system", "%s: %s" % (origin, text) if text else origin)
                else:
                    yield base("user", text)
            elif rtype == "assistant":
                model = str(rec.get("model") or "")
                change = track_change("model", models, session_id, model)
                if change:
                    row = base("system", change)
                    row.model = model
                    yield row
                for part in parts:
                    function_call = part.get("functionCall")
                    if isinstance(function_call, dict):
                        row = base("tool_use", args_summary(function_call.get("args")))
                        row.tool_name = str(function_call.get("name") or "")
                        row.tool_use_id = str(function_call.get("id") or "")
                    elif isinstance(part.get("text"), str) and part.get("thought"):
                        if not opts.include_thinking:
                            continue
                        row = base("thinking", part["text"])
                    elif isinstance(part.get("text"), str) and part["text"]:
                        row = base("assistant", part["text"])
                    else:
                        continue
                    row.model = model
                    yield row
            elif rtype == "tool_result":
                tcr = rec.get("toolCallResult")
                tcr = tcr if isinstance(tcr, dict) else {}
                responses = [
                    part["functionResponse"]
                    for part in parts
                    if isinstance(part.get("functionResponse"), dict)
                ]
                first_response = responses[0] if responses else {}
                display = tcr.get("resultDisplay")
                if isinstance(display, str) and display:
                    text = display
                elif first_response:
                    text = _response_text(first_response.get("response"))
                else:
                    text = compact_json(display) if display else ""
                status = str(tcr.get("status") or "")
                if status and status != "success":
                    tag = (
                        status
                        if not tcr.get("errorType")
                        else "%s %s" % (status, tcr.get("errorType"))
                    )
                    text = "[%s] %s" % (tag, text)
                row = base("tool_result", text)
                row.tool_name = str(first_response.get("name") or "")
                row.tool_use_id = str(tcr.get("callId") or first_response.get("id") or "")
                yield row
                if status in DECISION_STATUSES:
                    decision_row = base("system", "permission decision: %s" % status)
                    decision_row.tool_name, decision_row.tool_use_id = (
                        row.tool_name,
                        row.tool_use_id,
                    )
                    yield decision_row
            elif rtype == "system":
                subtype = str(rec.get("subtype") or "system")
                payload = rec.get("systemPayload")
                text = system_text(subtype, payload)
                model = ""
                if subtype == "session_model" and isinstance(payload, dict):
                    model = str(payload.get("modelId") or "")
                    if model:
                        change = track_change("model", models, session_id, model)
                        text = "%s auth=%s" % (
                            change or "model: %s" % model,
                            payload.get("authType") or "",
                        )
                elif subtype == "session_approval_mode" and isinstance(payload, dict):
                    mode = str(payload.get("mode") or "")
                    if mode:
                        change = track_change("permission mode", modes, session_id, mode)
                        extras = [
                            " %s=%s" % (key, payload[key])
                            for key in ("prePlanMode", "planExecutionMode")
                            if payload.get(key)
                        ]
                        text = (change or "permission mode: %s" % mode) + "".join(extras)
                row = base("system", text)
                row.model = model
                yield row
                event = payload.get("uiEvent") if isinstance(payload, dict) else None
                if (
                    subtype == "ui_telemetry"
                    and isinstance(event, dict)
                    and event.get("event.name") in TOOL_CALL_EVENTS
                    and event.get("decision")
                ):
                    decision_row = base(
                        "system",
                        "permission decision: %s (tool_call ui_telemetry)" % event["decision"],
                    )
                    decision_row.tool_name = str(event.get("function_name") or "")
                    decision_row.tool_use_id = str(event.get("call_id") or "")
                    yield decision_row
        yield from error_rows(self, artifact, errors, session_id, project_path)

    def _parse_logs(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        errors: list = []
        for idx, entry in self._iter_array(artifact.disk_path, errors):
            row = self.base_row(artifact)
            row.source_line = idx
            row.timestamp_utc = to_utc(entry.get("timestamp"))
            row.session_id = str(entry.get("sessionId") or "")
            etype = entry.get("type")
            message = entry.get("message")
            if etype == "user":
                row.turn_type = "user"
                text = message if isinstance(message, str) else compact_json(message)
            else:
                row.turn_type = "system"
                event = message
                if isinstance(message, str):
                    try:
                        event = json.loads(message)
                    except ValueError:
                        event = message
                if etype == "model_switch" and isinstance(event, dict):
                    text = "model: %s -> %s reason=%s" % (
                        event.get("fromModel"),
                        event.get("toModel"),
                        event.get("reason"),
                    )
                    row.model = str(event.get("toModel") or "")
                else:
                    text = "%s: %s" % (
                        etype,
                        event if isinstance(event, str) else compact_json(event),
                    )
            row.text = compact(text)
            yield row
        yield from error_rows(self, artifact, errors)

    @staticmethod
    def _iter_array(path, errors: list):
        """Yield (1-based index, entry) from a JSON array, decoding element by element.

        A file cut mid-write still yields the entries before the cut. A parse
        failure is recorded in `errors` as (index, message, raw) and ends the
        walk; raw is the text from the element the failed decode started at
        to the end of the file, less a trailing line terminator, since a
        broken element has no boundary of its own. A whole-file error has
        raw `""`.
        """
        with open(path, "rb") as handle:
            data = handle.read().decode("utf-8", errors="replace")
        decoder = json.JSONDecoder()
        pos = 0
        length = len(data)

        def skip(position: int) -> int:
            while position < length and data[position] in " \t\r\n":
                position += 1
            return position

        pos = skip(pos)
        if pos >= length:
            return
        if data[pos] != "[":
            errors.append((0, "not a JSON array", ""))
            return
        pos = skip(pos + 1)
        idx = 0
        while pos < length and data[pos] != "]":
            idx += 1
            try:
                value, pos = decoder.raw_decode(data, pos)
            except ValueError as error:
                errors.append(
                    (idx, "unparseable record %d (%s)" % (idx, error), tail_text(data, pos))
                )
                return
            if isinstance(value, dict):
                yield idx, value
            pos = skip(pos)
            if pos < length and data[pos] == ",":
                pos = skip(pos + 1)
        if pos >= length:
            errors.append((idx + 1, "unterminated JSON array", ""))
