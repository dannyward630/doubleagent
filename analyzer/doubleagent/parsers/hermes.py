"""Hermes Agent sessions.

Hermes (NousResearch/hermes-agent, checked at 8b66a51) keeps every
conversation of a profile, whatever the front end (CLI, TUI, desktop,
messaging gateway, cron, subagents), in one SQLite database in OpenAI
chat-completions message shape. See `research/hermes.md`.

Files, relative to the home directory, where `<hermes>` is `.hermes`,
`.hermes_<suffix>`, `AppData/Local/hermes` or `AppData/Local/hermes_<suffix>`,
optionally followed by `profiles/<name>` (named profiles are complete homes).
A Hermes home collected from a Docker or Podman named volume (the
`hermes|*hermes*` volume line; the image mounts the Hermes home at
`/opt/data`) has the volume's `_data` as its base, so `<hermes>` is empty
there and the paths start at `state.db`, `sessions/`, `state-snapshots/`,
`pastes/` or `profiles/<name>/` (issue 181; source-derived, not observed on
any real install):

* `<hermes>/state.db`, with `-wal` and `-shm` sidecars (WAL mode, schema
  version 31 at the checked commit). Migrations add columns in place, so
  every column is read with a default.
  - `sessions`: `id`, `source`, `model`, `parent_session_id`, `started_at`
    (epoch seconds), `end_reason`, `cwd`, `git_branch`, `git_repo_root`,
    `title`.
  - `messages`: `id` (write order), `session_id`, `role` (`user`,
    `assistant`, `tool`, `system`), `content` (text; list or dict content is
    stored as `"\\x00json:"` + JSON), `tool_calls` (JSON list of `{id,
    call_id, type, function: {name, arguments}}`, `arguments` a JSON
    string), `tool_call_id`, `tool_name`, `timestamp` (epoch seconds),
    `reasoning`, `reasoning_content`, `finish_reason`, `active`,
    `display_kind` (`model_switch` marks a model-switch marker).
* `<hermes>/state-snapshots/<id>/state.db`: quick snapshots, consistent
  copies of `state.db` made with SQLite's backup API by `/snapshot`,
  `hermes backup --quick` and `hermes update` (20 kept by default). `<id>` is
  the UTC time `YYYYmmdd-HHMMSS`, optionally followed by `-<label>` and a
  `-<n>` collision suffix. Read with the `state.db` reader, after one
  `system` row `state snapshot <id>: older copy of state.db`, timestamped
  from the id when it starts with a valid time, else empty. Collectors
  before the issue 123 change excluded `state-snapshots` unless run with
  `--full`.
* `<hermes>/sessions/<session_id>.jsonl`: written only when `state.db` was
  replaced under a running process; one message dict per line with the same
  keys as a `messages` row (`tool_calls` may be a list rather than a string,
  `timestamp` may be absent). It records no working directory or model.
* `<hermes>/pastes/pending.json`: a JSON list of `{url, expire_at}`
  (`expire_at` epoch seconds, a float: the upload time plus 21600 s), the
  paste.rs links of `hermes debug share`, the gateway's `/debug` and the
  dashboard's debug share, whose logs hold verbatim recent messages; an
  entry is dropped after `hermes debug delete` or once it is a day past
  its expiry. One `system` row per entry, `debug report uploaded: <url>
  (from pastes/pending.json, expire_at minus 6 hours)`, at `expire_at`
  minus 21600 seconds, with an empty `session_id`: the upload is host-wide
  and marks no session, so `records_sync` stays False. A file that is not
  a JSON list is one `parser:` row; an entry that is not an object with a
  `url` is its own `parser: unparseable record <n>` row carrying the
  entry. Fixture only: no real install has shown the file.

Secondary sources (issue 122, `secondary`): the snapshots and the
`sessions/<id>.jsonl` diverts. `state.db` is the store of record; a
snapshot is a copy of it at the snapshot time, so its rows carry the same
`session_id`, `cwd` project path and message timestamps as the live rows
and pair with them exactly; what survives is what the live database has
lost since (a session pruned after 90 idle days, a deleted session, a
`state.db` replaced or rebuilt). Repeats across several snapshots
collapse to the first copy. A row whose text changed since the snapshot
(a turn rewound or compacted later, now `[rewound] ...`; a session whose
`end_reason` was set later) does not pair and both are kept. A divert
holds the messages a live process could not write to the replaced
database, so its rows pair only when those messages also reached a
database the parser reads (a snapshot, a later `state.db`); they carry the
message's own `timestamp` when the line has one, else none (they then
match on text within the session), the session id from the file name and
no project path. Both use the default 2-second tolerance; the copies are
exact.

Rows: one `system` row per session (title, source, parent, end reason); per
message one `user`, `assistant`, `tool_result` (role `tool`, joined on
`tool_call_id`) or `system` row for non-empty content, a `thinking` row for
`reasoning`/`reasoning_content` with `--include-thinking`, and one `tool_use`
row per `tool_calls` entry whose text is the `command` or `path` argument,
else the arguments. A `tool_calls` value that is not valid JSON, is not a
list or holds an entry that is not an object yields one `parser:
unparseable record <messages.id> (<reason>): <value as stored>` row through
`error_rows` after the message's other rows, with the message's session
and project path (issue 182); the entries that are objects still give
`tool_use` rows. Messages are ordered by `timestamp, id`. Rewind and
compaction keep the old rows with `active = 0` instead of deleting them (both
set the same flags, so the two cannot be told apart); those rows are still
evidence and are emitted with a `[rewound]` prefix on their text (except
model-switch markers, below). The model is the session's `model`; messages
record none of their own beyond the markers. `project_path`
is `sessions.cwd`, else `git_repo_root`, and `git_branch` is
`sessions.git_branch`. Not parsed: the legacy `sessions/<id>.json` and
`session_<id>.json` snapshots (nothing at the checked commit writes them,
only `_remove_session_files` deletes them, so their shape is not known),
`/save` exports, the `backups/*.zip` archives, the copies of
`response_store.db` and the other stores inside a quick snapshot, the
`approvals` settings nested in `config.yaml`, and the desktop app's
single-connection `connection.json`.

Model rows (issue 96), `system`, after each session's start row:
`session_model_usage` (`session_id`, `model`, `billing_provider`, `task`,
`first_seen` in epoch seconds) holds one row per model, billing route and
task that a session's API calls used, so its main-loop rows (`task` empty;
auxiliary calls such as compression or title generation name their task
and are skipped) ordered by `first_seen` give `model: <id>` for the first
and `model: <old> -> <new>` for each later one, timestamped at
`first_seen` and suffixed ` provider=<billing_provider>` when set. The
table aggregates per model, so a switch back to a model already used is
not visible. A session with no such rows (an older database, or no API call
yet) gets one `model: <sessions.model>` row at `started_at`;
`sessions.model` is rewritten by a `/model` switch, so it is the latest
model, not necessarily the first. The `model` column of the other rows
stays `sessions.model`.

Model-switch markers (issue 180): a switch made in the TUI, the desktop
app or another TUI gateway front end is a `messages` row with `role`
`user`, `display_kind` `model_switch` and the content `[System: The
active model for this chat has changed to <model> via provider
<provider>. From this point forward, ...]` (the provider part only when
one is set), at the switch time (tui_gateway/server.py:1274-1331 at
86fa9e6, present at 8b66a51 as well). Each switch sets `active = 0` on
the session's earlier markers (hermes_state_messages.py:1064-1070 at
86fa9e6), which is not a rewind. Each marker is one `system` row
`model: <old> -> <model> provider=<provider>` at its time, with `model`
set to the new model and no `[rewound]` prefix, never a `user` row. The
marker names only the new model: `<old>` is the session's previous
marker's model, else the last main-loop `session_model_usage` model first
seen before the marker; with neither, or when it equals the new one, the
row is `model: <model> provider=<provider>`. A marker whose text does not
have that form is a `system` row `model_switch: <text>`. The classic
CLI's `/model` writes no marker. Source-derived: no real install has
shown a marker row.

Issue 208, source-derived from hermes-agent 86fa9e6 (not observed on any
real install); the field names each depends on are in brackets.

* Session rows, after a session's model rows, at its `started_at`
  [`sessions.source`, `chat_id`, `chat_type`, `thread_id`, `user_id`,
  `display_name`, `origin_json` (`user_name`, `chat_name`,
  `imported_from` {`tool`, `path`, `foreign_session_id`}), `model_config`
  (`yolo_mode`), `archived`, `cwd`, `git_branch`]: `session relayed:
  <source> chat <chat_id> type <chat_type> thread <thread_id> user
  <user_id> name <user_name> display <display_name> (from state.db
  sessions, started_at)` for a session whose `source` is a messaging
  platform of gateway/config.py (every one but `local` and `api_server`)
  or that has a `chat_id`, so `records_relay` is True; `permission
  setting: yolo_mode=<true|false> (from state.db sessions.model_config,
  started_at)` for a session whose `/yolo` bypass is recorded; and
  `scratch directory: <cwd> (git worktree the agent created in <repo>,
  branch <git_branch>)` for a `cwd` of the form `<repo>/.worktrees/<name>`
  on a branch starting `hermes/` or `hermes-subagent/`. The start row ends
  ` | archived=1` for an archived session and ` | imported from <tool>
  <path> session <foreign_session_id>` for a session copied from Claude
  Code or Codex CLI. `-` stands for an absent value.
* `permission decision: approved (<approval>)`, `permission decision:
  blocked <error>` (with ` user_summary=<user_summary>`) and `permission
  decision: pending pattern=<pattern_key> smart_denied=<smart_denied>`
  after a `terminal` tool result whose JSON content has `approval` or a
  `status` of `blocked` or `pending_approval`, with the call's
  `tool_use_id`.
* `state_meta` (`key`, `value`): `session deleted: <id>[ sweep] (from
  state.db state_meta gateway.retired_session.v1, retired_at)` per
  deletion fence, at its `retired_at`, ` sweep` when `expires` is set.
  `conversation_generations` (`source`, `session_key`, `generation`):
  `relay peer: <source> <session_key> generation <n> (from state.db
  conversation_generations)` per row, with no time. `hosted_room_events`
  (`room_id`, `seq`, `kind`, `actor_json` {`kind`, `id`,
  `display_name`}, `payload_json` {`text`}, `created_at`) with
  `hosted_rooms.name`: `bot mode room <name> (<room_id>) seq <seq> <kind>
  actor <kind>:<id> (<display_name>): <text or payload>`.
* `<hermes>/config.yaml`: `permission setting: command_allowlist=<pattern>
  (from config.yaml, file mtime)` per entry of the top-level block list;
  any other construct under the key is a whole-file `parser:` row.
  `<hermes>/[platforms/]pairing/<platform>-approved.json` (user id ->
  {`user_name`, `approved_at`}): `permission setting:
  pairing.<platform>.<user id> user_name=<user_name> (from
  <dir>/<platform>-approved.json, approved_at)` at `approved_at`.
* Secondary sources: `<hermes>/.hermes_history` (prompt_toolkit
  `FileHistory`; `user` rows, `slash command: <entry>` for an entry that
  starts with `/`), `<hermes>/cron/output/<job>/<time>.md` (`cron run:
  job <job> ...`, then the prompt as `user` and the response as
  `assistant`, by the `**Prompt Characters:**` and `**Response
  Characters:**` frames or the `## Prompt` and last `## Response`
  headings, else `cron run output: <document>`), `<hermes>/response_store.db`
  (`responses.response_id`, `data` {`response` {`status`, `model`,
  `created_at`}, `conversation_history`, `session_id`},
  `conversations.name`; a header row per response, then the history
  messages no earlier response of the session held at the same position)
  and the trajectory files `trajectory_samples.jsonl` and
  `failed_trajectories.jsonl` of a project (`conversations` [{`from`,
  `value`}], `timestamp`, `model`, `completed`). The history and the cron
  files keep host-local times without a zone (the TUI's history entries
  are UTC), emitted as if UTC, so their `secondary_tolerance` is 14 hours
  plus 2 seconds; history, response-store messages and trajectory turns
  carry no session id, or, for the response store, no time.
* The desktop app's `connections.json` in its Electron userData directory
  (`connections` [{`kind`, `label`, `url`, `host`, `user`, `port`,
  `org`, `name`, `remoteProfile`}], `quarantined` [{`reason`}]): `remote
  backend: <kind> <label> <target> (from connections.json, file mtime)`
  per connection that is not `local`, and `remote backend quarantined by
  the app: <reason>` per quarantined entry. Its `token` and `headers` are
  never printed.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator

from ..dedup import TOLERANCE_SECONDS
from ..inputs import Artifact
from ..model import Row, compact
from ..sqlite_util import is_sqlite, open_copy, table_names
from ..timeutil import to_utc
from .aider import read_input_history
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

# The Hermes home a path starts with: `.hermes[_<suffix>]/` or
# `AppData/Local/hermes[_<suffix>]/` under a user's home, or nothing when the
# collection base is a Docker or Podman named volume's `_data` (the
# `hermes|*hermes*` volume line), which holds the Hermes home itself (issue
# 181); either one optionally followed by `profiles/<name>/`.
HOME = r"(?:(?:\.hermes(?:_[^/]+)?|AppData/Local/hermes(?:_[^/]+)?)/)?(?:profiles/[^/]+/)?"
DB_RX = re.compile(r"^%sstate\.db$" % HOME)
JSONL_RX = re.compile(r"^%ssessions/[^/]+\.jsonl$" % HOME)
SNAP_RX = re.compile(r"^%sstate-snapshots/([^/]+)/state\.db$" % HOME)
SNAP_TIME_RX = re.compile(r"^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})(?:-|$)")
PASTES_RX = re.compile(r"^%spastes/pending\.json$" % HOME)
# A paste.rs upload's `expire_at` is its upload time plus this (hermes_cli/debug.py).
PASTE_LIFETIME = 21600
# Issue 208, source-derived (hermes-agent 86fa9e6): standing permission files,
# the prompt history, the cron run archive, the API server's response store,
# the trajectory files a run with --save-trajectories leaves in its working
# directory (project files; the base is the project) and the desktop app's
# connection registry in its Electron userData directory.
CONFIG_RX = re.compile(r"^%sconfig\.yaml$" % HOME)
PAIRING_RX = re.compile(r"^%s((?:platforms/)?pairing)/([^/]+)-approved\.json$" % HOME)
HISTORY_RX = re.compile(r"^%s\.hermes_history$" % HOME)
CRON_RX = re.compile(r"^%scron/output/([^/]+)/([^/]+)\.md$" % HOME)
CRON_TIME_RX = re.compile(r"^(\d{4}-\d\d-\d\d)_(\d\d)-(\d\d)-(\d\d)$")
RESPONSES_RX = re.compile(r"^%sresponse_store\.db$" % HOME)
TRAJECTORY_RX = re.compile(r"^(?:trajectory_samples|failed_trajectories)\.jsonl$")
CONNECTIONS_RX = re.compile(
    r"^(?:\.config|Library/Application Support|AppData/Roaming)/Hermes/connections\.json$"
)
# The classic CLI's history entries and the cron run files carry host-local
# times with no zone (prompt_toolkit's `datetime.now()`, `hermes_time.now()`
# formatted without an offset), emitted as if UTC; the window that pairs them
# with the store's UTC times spans every zone offset.
LOCAL_TOLERANCE = 14 * 3600 + TOLERANCE_SECONDS
# gateway/config.py Platform values that are messaging platforms: every one
# but `local` (the CLI) and `api_server` (the OpenAI-compatible HTTP API).
MESSAGING = frozenset(
    (
        "telegram",
        "discord",
        "whatsapp",
        "whatsapp_cloud",
        "slack",
        "signal",
        "mattermost",
        "matrix",
        "email",
        "sms",
        "dingtalk",
        "webhook",
        "msgraph_webhook",
        "feishu",
        "wecom",
        "wecom_callback",
        "weixin",
        "bluebubbles",
        "qqbot",
        "yuanbao",
        "relay",
    )
)
NOT_RELAYED = frozenset(("local", "api_server"))
RETIRED_PREFIX = "gateway.retired_session.v1."
WORKTREE_RX = re.compile(r"^(.*)[/\\]\.worktrees[/\\][^/\\]+[/\\]?$")
WORKTREE_BRANCHES = ("hermes/", "hermes-subagent/")
# The cron run document's length frames (cron/scheduler_prompt.py).
CRON_PROMPT_FRAME_RX = re.compile(r"(?m)^\*\*Prompt Characters:\*\* (\d+)\n## Prompt\n\n")
CRON_RESPONSE_FRAME_RX = re.compile(r"\*\*Response Characters:\*\* (\d+)\n## Response\n\n")
CRON_PROMPT_HEADING = "## Prompt\n\n"
CRON_RESPONSE_HEADING = "## Response\n\n"
# ShareGPT `from` values of a trajectory entry (agent/agent_runtime_helpers.py).
TRAJECTORY_TYPES = {"human": "user", "gpt": "assistant", "tool": "tool_result"}

JSON_PREFIX = "\x00json:"
# The TUI gateway's model-switch marker (tui_gateway/server.py:1274-1300 at
# 86fa9e6): `<prefix><model>[ via provider <provider>]<end> ...]`.
SWITCH_PREFIX = "[System: The active model for this chat has changed to "
SWITCH_END = ". From this point forward,"
SWITCH_PROVIDER = " via provider "
ROLE_TYPES = {"user": "user", "assistant": "assistant", "tool": "tool_result", "system": "system"}


def decode_content(value):
    """`messages.content` as Hermes stored it: plain text, or list/dict
    multimodal parts behind the NUL-prefixed JSON sentinel."""
    if isinstance(value, str) and value.startswith(JSON_PREFIX):
        try:
            return json.loads(value[len(JSON_PREFIX) :])
        except ValueError:
            return value[len(JSON_PREFIX) :]
    return value


def content_text(value) -> str:
    content = decode_content(value)
    if isinstance(content, list):
        content = [
            {"type": "image"}
            if isinstance(block, dict) and block.get("type") in ("image_url", "input_image")
            else block
            for block in content
        ]
    return text_of(content)


def _json(value, default):
    if value is None or value == "":
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except ValueError:
        return default


def model_switch(content) -> tuple[str, str] | None:
    """(model, provider) named by a model-switch marker's text, provider
    `""` when the marker has none; None when the text is not one."""
    if not isinstance(content, str) or not content.startswith(SWITCH_PREFIX):
        return None
    head, separator, _ = content[len(SWITCH_PREFIX) :].partition(SWITCH_END)
    if not separator:
        return None
    model, _, provider = head.partition(SWITCH_PROVIDER)
    return (model, provider) if model else None


def tool_calls(message: dict, line) -> tuple[list, list]:
    """The `tool_calls` of message `m` as (calls, errors). A value that is
    not valid JSON, is not a list (a lone object is taken as a one-call
    list) or holds an entry that is not an object is an `errors` entry
    carrying the value as stored, for `error_rows` (issue 182); the
    entries that are objects are still returned."""
    value = message.get("tool_calls")
    if value is None or value == "":
        return [], []
    raw = value if isinstance(value, str) else compact_json(value)
    label = "unparseable record %s" % line
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as error:
            return [], [(line, "%s (tool_calls is not valid JSON: %s)" % (label, error), raw)]
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return [], [(line, "%s (tool_calls is not a list)" % label, raw)]
    calls = [call for call in value if isinstance(call, dict)]
    if len(calls) != len(value):
        return calls, [(line, "%s (tool_calls entry is not an object)" % label, raw)]
    return calls, []


def call_summary(arguments) -> str:
    args = _json(arguments, arguments)
    if isinstance(args, dict):
        for k in ("command", "path", "file_path", "url", "query"):
            if args.get(k) not in (None, ""):
                return str(args[k])
        return compact_json(args)
    return args if isinstance(args, str) else compact_json(args)


def _join(*parts: str) -> str:
    return " | ".join(part for part in parts if part)


def _dash(value) -> str:
    """A row text field: the value as text, `-` when it is absent or empty."""
    if value is None or value == "":
        return "-"
    return setting_value(value)


def terminal_decision(content) -> str:
    """The `permission decision:` row text, less its label, for a `terminal`
    tool result whose JSON records an approval outcome
    (tools/terminal_tool.py:1062-1087 at 86fa9e6): `approved (<approval
    note>)`, `blocked <error>` with ` user_summary=<summary>` when a person
    was asked, or `pending pattern=<pattern_key> smart_denied=<bool>` for a
    command waiting on a gateway `/approve`; `""` for any other result."""
    value = decode_content(content)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return ""
    if not isinstance(value, dict):
        return ""
    if isinstance(value.get("approval"), str) and value["approval"]:
        return "approved (%s)" % value["approval"]
    status = value.get("status")
    if status == "blocked":
        text = "blocked %s" % _dash(value.get("error"))
        if value.get("user_summary"):
            text += " user_summary=%s" % setting_value(value["user_summary"])
        return text
    if status == "pending_approval":
        return "pending pattern=%s smart_denied=%s" % (
            _dash(value.get("pattern_key")),
            setting_value(bool(value.get("smart_denied"))),
        )
    return ""


def yaml_scalar(value: str) -> str | None:
    """A one-line YAML scalar as a string: double-quoted (JSON escapes),
    single-quoted (`''` for a quote) or plain (a trailing ` #` comment
    removed); None for anything else (a mapping, a flow collection, an
    alias, a block scalar, an unterminated quote)."""
    if value[:1] in ("'", '"'):
        quote, i = value[0], 1
        while i < len(value):
            # a backslash escape in a double-quoted scalar, `''` in a single-quoted one
            escaped = value[i] == "\\" if quote == '"' else value[i : i + 2] == "''"
            if escaped:
                i += 2
            elif value[i] == quote:
                break
            else:
                i += 1
        rest = value[i + 1 :].strip()
        if i >= len(value) or (rest and not rest.startswith("#")):
            return None
        if quote == "'":
            return value[1:i].replace("''", "'")
        try:
            out = json.loads(value[: i + 1])
        except ValueError:
            return None
        return out if isinstance(out, str) else None
    plain = value.split(" #", 1)[0].rstrip()
    if not plain or plain[0] in "[]{}&*!|>%@`#," or ": " in plain or plain.endswith(":"):
        return None
    return plain


def read_flat_list(lines: list[str], key: str) -> tuple[list[tuple[int, str]], str]:
    """The strings of the top-level YAML block list `key` in `lines`, as
    (line number, string), and an error naming the first line that is not a
    `- <scalar>` item of it (`""` when there is none). Only that shape is
    read: an absent key, `key:` with no items and `key: []` give no entries,
    and any other construct under the key is an error."""
    entries: list[tuple[int, str]] = []
    start = 0
    for line_number, line in enumerate(lines, 1):
        if line.startswith(key + ":"):
            start = line_number
            rest = line[len(key) + 1 :].split(" #", 1)[0].strip()
            if rest not in ("", "[]", "null", "~"):
                return [], "line %d: %s is not a block list" % (line_number, key)
            break
    if not start:
        return [], ""
    for line_number in range(start + 1, len(lines) + 1):
        line = lines[line_number - 1]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line[0].isspace() and not stripped.startswith("-"):
            break  # the next top-level key
        value = yaml_scalar(stripped[2:].strip()) if stripped.startswith("- ") else None
        if value is None:
            return entries, "line %d: not a string item of %s" % (line_number, key)
        entries.append((line_number, value))
    return entries, ""


def split_cron_doc(document: str) -> tuple[str, str] | None:
    """(prompt, response) of a cron run document: by its length frames when
    the writer stamped them (`**Prompt Characters:** <n>` before `## Prompt`,
    `**Response Characters:** <n>` before `## Response`), else at the first
    `## Prompt` heading and the last `## Response` heading (an unframed
    document of an older writer); None for a document with neither (a failed,
    blocked or script-gated run, whose document is kept whole)."""
    frame = CRON_PROMPT_FRAME_RX.search(document)
    if frame and document.find(CRON_PROMPT_HEADING) == frame.end() - len(CRON_PROMPT_HEADING):
        end = frame.end() + int(frame.group(1))
        reply = CRON_RESPONSE_FRAME_RX.match(document, end + 2)
        if reply:
            prompt = document[frame.end() : end]
            return prompt, document[reply.end() : reply.end() + int(reply.group(1))]
    start = document.find(CRON_PROMPT_HEADING)
    cut = document.rfind(CRON_RESPONSE_HEADING)
    if start < 0 or cut <= start:
        return None
    prompt = document[start + len(CRON_PROMPT_HEADING) : cut]
    if prompt.endswith("\n\n"):
        prompt = prompt[:-2]
    reply_text = document[cut + len(CRON_RESPONSE_HEADING) :]
    if reply_text.endswith("\n"):
        reply_text = reply_text[:-1]
    return prompt, reply_text


class HermesParser(Parser):
    agent = "hermes"
    name = "hermes"
    has_secondary = True
    records_relay = True

    WANTED = (
        DB_RX,
        SNAP_RX,
        JSONL_RX,
        PASTES_RX,
        CONFIG_RX,
        PAIRING_RX,
        HISTORY_RX,
        CRON_RX,
        RESPONSES_RX,
        TRAJECTORY_RX,
        CONNECTIONS_RX,
    )
    SECONDARY = (SNAP_RX, JSONL_RX, HISTORY_RX, CRON_RX, RESPONSES_RX, TRAJECTORY_RX)

    def wants(self, artifact: Artifact) -> bool:
        return any(pattern.match(artifact.rel) for pattern in self.WANTED)

    def secondary(self, artifact: Artifact) -> bool:
        return any(pattern.match(artifact.rel) for pattern in self.SECONDARY)

    def secondary_tolerance(self, artifact: Artifact) -> float:
        """`.hermes_history` and the cron run files keep host-local times with
        no zone, emitted as if UTC, so their window spans every zone offset
        (14 hours) plus the default 2 seconds; the other sources keep the
        default, their times being copies of the store's."""
        if HISTORY_RX.match(artifact.rel) or CRON_RX.match(artifact.rel):
            return LOCAL_TOLERANCE
        return TOLERANCE_SECONDS

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        rel = artifact.rel
        snapshot = SNAP_RX.match(rel)
        if snapshot:
            yield self._snapshot_row(artifact, snapshot.group(1))
            yield from self._parse_db(artifact, opts)
        elif DB_RX.match(rel):
            yield from self._parse_db(artifact, opts)
        elif PASTES_RX.match(rel):
            yield from self._parse_pastes(artifact)
        elif CONFIG_RX.match(rel):
            yield from self._parse_config(artifact)
        elif pairing := PAIRING_RX.match(rel):
            yield from self._parse_pairing(artifact, pairing)
        elif HISTORY_RX.match(rel):
            yield from self._parse_history(artifact)
        elif cron := CRON_RX.match(rel):
            yield from self._parse_cron(artifact, cron)
        elif RESPONSES_RX.match(rel):
            yield from self._parse_responses(artifact, opts)
        elif TRAJECTORY_RX.match(rel):
            yield from self._parse_trajectory(artifact)
        elif CONNECTIONS_RX.match(rel):
            yield from self._parse_connections(artifact)
        else:
            yield from self._parse_jsonl(artifact, opts)

    def _snapshot_row(self, artifact: Artifact, snap_id: str) -> Row:
        """The `system` row naming a quick snapshot, at the UTC time its id
        starts with (`backup.py` names it `%Y%m%d-%H%M%S[-label]`)."""
        row = self._system(artifact, 0, {}, "state snapshot %s: older copy of state.db" % snap_id)
        match = SNAP_TIME_RX.match(snap_id)
        if match:
            row.timestamp_utc = to_utc("%s-%s-%sT%s:%s:%sZ" % match.groups())
        return row

    def _row(self, artifact: Artifact, line: int, session: dict, timestamp: str = "") -> Row:
        row = self.base_row(artifact)
        row.source_line = line
        row.session_id = str(session.get("id") or "")
        row.project_path = str(session.get("cwd") or session.get("git_repo_root") or "")
        row.git_branch = str(session.get("git_branch") or "")
        row.model = str(session.get("model") or "")
        row.timestamp_utc = timestamp
        return row

    def _system(self, artifact: Artifact, line: int, session: dict, text: str) -> Row:
        row = self._row(artifact, line, session)
        row.turn_type = "system"
        row.text = text
        return row

    def _message_rows(
        self,
        artifact: Artifact,
        message: dict,
        session: dict,
        line: int,
        tool_names: dict[str, str],
        opts: Options,
        switches: dict[str, str],
        usage: dict[str, list[dict]] | None = None,
    ) -> Iterator[Row]:
        timestamp = to_utc(message.get("timestamp"))
        role = str(message.get("role") or "")
        if message.get("display_kind") == "model_switch":
            yield self._switch_row(artifact, message, session, line, switches, usage or {})
            return
        marker = "[rewound] " if message.get("active", 1) in (0, "0", False) else ""

        def make_row(turn_type: str, text: str) -> Row:
            row = self._row(artifact, line, session, timestamp)
            row.turn_type = turn_type
            row.text = compact(marker + text)
            return row

        if opts.include_thinking:
            reasoning = message.get("reasoning") or message.get("reasoning_content")
            if reasoning:
                yield make_row("thinking", str(reasoning))
        text = content_text(message.get("content"))
        turn_type = ROLE_TYPES.get(role, "system")
        if turn_type == "tool_result":
            row = make_row("tool_result", text)
            row.tool_use_id = str(message.get("tool_call_id") or "")
            row.tool_name = str(message.get("tool_name") or tool_names.get(row.tool_use_id, ""))
            yield row
            decision = (
                terminal_decision(message.get("content")) if row.tool_name == "terminal" else ""
            )
            if decision:
                permission = self._row(artifact, line, session, timestamp)
                permission.turn_type = "system"
                permission.text = compact("permission decision: " + decision)
                permission.tool_name, permission.tool_use_id = row.tool_name, row.tool_use_id
                yield permission
        elif text:
            if turn_type == "system" and role not in ("", "system"):
                text = "%s: %s" % (role, text)
            yield make_row(turn_type, text)
        calls, errors = tool_calls(message, line)
        for call in calls:
            function = call.get("function")
            if not isinstance(function, dict):
                function = {}
            row = make_row("tool_use", call_summary(function.get("arguments")))
            row.tool_use_id = str(call.get("id") or call.get("call_id") or "")
            row.tool_name = str(function.get("name") or "")
            tool_names[row.tool_use_id] = row.tool_name
            yield row
        yield from error_rows(
            self,
            artifact,
            errors,
            str(session.get("id") or ""),
            str(session.get("cwd") or session.get("git_repo_root") or ""),
        )

    def _switch_row(
        self,
        artifact: Artifact,
        message: dict,
        session: dict,
        line: int,
        switches: dict[str, str],
        usage: dict[str, list[dict]],
    ) -> Row:
        """The `system` row for a TUI gateway model-switch marker (a `user`
        message with `display_kind` `model_switch`, issue 180): `model: <old>
        -> <new> provider=<provider>` at the marker's time. The marker names
        only the new model; the old one is the session's previous marker's,
        else the last main-loop `session_model_usage` model first seen
        before the marker, else unknown (`model: <new>`). A later switch
        sets the marker's `active` to 0, which is not a rewind, so the row
        has no `[rewound]` prefix. A marker whose text does not parse is a
        `system` row `model_switch: <text>`."""
        row = self._row(artifact, line, session, to_utc(message.get("timestamp")))
        row.turn_type = "system"
        session_id = row.session_id
        parsed = model_switch(message.get("content"))
        if parsed is None:
            row.text = compact("model_switch: " + content_text(message.get("content")))
            return row
        model, provider = parsed
        old = switches.get(session_id, "")
        switch_time = message.get("timestamp")
        if not old and isinstance(switch_time, (int, float)):
            for usage_row in usage.get(session_id) or []:
                first = usage_row.get("first_seen")
                if isinstance(first, (int, float)) and first < switch_time:
                    old = str(usage_row.get("model") or "")
        switches[session_id] = model
        row.text = "model: %s -> %s" % (old, model) if old and old != model else "model: " + model
        if provider:
            row.text += " provider=%s" % provider
        row.model = model
        return row

    def _model_rows(
        self,
        artifact: Artifact,
        session: dict,
        start: Row,
        usage: dict[str, list[dict]],
        seen: dict[str, str],
    ) -> Iterator[Row]:
        session_id = start.session_id
        uses = usage.get(session_id) or []
        if not uses:
            text = track_change("model", seen, session_id, str(session.get("model") or ""))
            if text:
                yield self._copy(start, text, str(session.get("model") or ""))
            return
        for usage_row in uses:
            model = str(usage_row.get("model") or "")
            text = track_change("model", seen, session_id, model)
            if not text:
                continue
            if usage_row.get("billing_provider"):
                text += " provider=%s" % usage_row["billing_provider"]
            row = self._copy(start, text, model)
            row.source_line = usage_row["_rowid"]
            row.timestamp_utc = to_utc(usage_row.get("first_seen")) or start.timestamp_utc
            yield row

    @staticmethod
    def _copy(base: Row, text: str, model: str) -> Row:
        row = Row(**base.__dict__)
        row.turn_type = "system"
        row.model = model
        row.text = text
        return row

    # -- state.db ------------------------------------------------------------------------
    def _parse_db(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        if not is_sqlite(artifact.disk_path):
            yield self._system(artifact, 0, {}, "parser: not a SQLite database")
            return
        try:
            with open_copy(artifact.disk_path) as connection:
                tables = table_names(connection)
                if "messages" not in tables:
                    return
                # (session_id, project_path, error entry) per record that does
                # not decode, reported after the file's other rows.
                record_errors: list[tuple[str, str, tuple]] = []
                sessions: dict[str, dict] = {}
                usage = self._usage(connection, tables)
                if "sessions" in tables:
                    seen_model: dict[str, str] = {}
                    for session_row in connection.execute(
                        "select rowid as _rowid, * from sessions order by started_at, rowid"
                    ):
                        session_row = dict(session_row)
                        sessions[str(session_row.get("id") or "")] = session_row
                        yield from self._session_rows(
                            artifact, session_row, usage, seen_model, record_errors
                        )
                tool_names: dict[str, str] = {}
                switches: dict[str, str] = {}
                for message in connection.execute("select * from messages order by timestamp, id"):
                    message = dict(message)
                    session_id = str(message.get("session_id") or "")
                    session = sessions.get(session_id) or {"id": session_id}
                    yield from self._message_rows(
                        artifact,
                        message,
                        session,
                        message.get("id") or 0,
                        tool_names,
                        opts,
                        switches,
                        usage,
                    )
                if "state_meta" in tables:
                    yield from self._retired_rows(artifact, connection, sessions, record_errors)
                if "conversation_generations" in tables:
                    yield from self._generation_rows(artifact, connection)
                if "hosted_room_events" in tables:
                    yield from self._room_rows(artifact, connection, tables, record_errors)
                for session_id, project, entry in record_errors:
                    yield from error_rows(self, artifact, [entry], session_id, project)
        except sqlite3.DatabaseError as error:
            yield self._system(artifact, 0, {}, "parser: SQLite error: %s" % error)

    @staticmethod
    def _usage(connection, tables) -> dict[str, list[dict]]:
        """The main-loop `session_model_usage` rows per session, by `first_seen`."""
        usage: dict[str, list[dict]] = {}
        if "session_model_usage" in tables:
            for usage_row in connection.execute(
                "select rowid as _rowid, * from session_model_usage order by first_seen, rowid"
            ):
                usage_row = dict(usage_row)
                if not usage_row.get("task"):
                    usage.setdefault(str(usage_row.get("session_id") or ""), []).append(usage_row)
        return usage

    @staticmethod
    def _column_json(session: dict, column: str, record_errors: list) -> dict:
        """`sessions.<column>` decoded as a JSON object, `{}` when it is empty;
        a value that does not decode to an object is an entry of
        `record_errors` carrying the value as stored."""
        raw = session.get(column)
        if raw is None or raw == "":
            return {}
        session_id = str(session.get("id") or "")
        project = str(session.get("cwd") or session.get("git_repo_root") or "")
        label = "unparseable record %s (sessions.%s" % (session.get("_rowid"), column)
        try:
            value = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError as error:
            record_errors.append(
                (session_id, project, (session.get("_rowid"), "%s: %s)" % (label, error), raw))
            )
            return {}
        if not isinstance(value, dict):
            entry = (session.get("_rowid"), "%s: not a JSON object)" % label, str(raw))
            record_errors.append((session_id, project, entry))
            return {}
        return value

    def _session_rows(
        self,
        artifact: Artifact,
        session: dict,
        usage: dict[str, list[dict]],
        seen_model: dict[str, str],
        record_errors: list,
    ) -> Iterator[Row]:
        """A session's start row, its model rows, and, at `started_at`, its
        relay, `/yolo` and worktree rows (issue 208, source-derived)."""
        origin = self._column_json(session, "origin_json", record_errors)
        config = self._column_json(session, "model_config", record_errors)
        imported = origin.get("imported_from")
        imported_text = ""
        if isinstance(imported, dict):
            imported_text = "imported from %s %s session %s" % (
                _dash(imported.get("tool")),
                _dash(imported.get("path")),
                _dash(imported.get("foreign_session_id")),
            )
        start = self._system(
            artifact,
            session["_rowid"],
            session,
            compact(
                _join(
                    "session start",
                    str(session.get("title") or ""),
                    "source=%s" % session["source"] if session.get("source") else "",
                    "parent=%s" % session["parent_session_id"]
                    if session.get("parent_session_id")
                    else "",
                    "end=%s" % session["end_reason"] if session.get("end_reason") else "",
                    "archived=1" if session.get("archived") in (1, "1", True) else "",
                    imported_text,
                ),
            ),
        )
        start.timestamp_utc = to_utc(session.get("started_at"))
        yield start
        yield from self._model_rows(artifact, session, start, usage, seen_model)
        source = str(session.get("source") or "")
        if source in MESSAGING or (session.get("chat_id") and source not in NOT_RELAYED):
            yield self._copy(
                start,
                "session relayed: %s chat %s type %s thread %s user %s name %s display %s"
                " (from state.db sessions, started_at)"
                % (
                    source,
                    _dash(session.get("chat_id")),
                    _dash(session.get("chat_type")),
                    _dash(session.get("thread_id")),
                    _dash(session.get("user_id")),
                    _dash(origin.get("user_name")),
                    _dash(session.get("display_name") or origin.get("chat_name")),
                ),
                start.model,
            )
        if "yolo_mode" in config:
            yield self._copy(
                start,
                "permission setting: yolo_mode=%s (from state.db sessions.model_config, started_at)"
                % setting_value(config["yolo_mode"]),
                start.model,
            )
        cwd = str(session.get("cwd") or "")
        tree = WORKTREE_RX.match(cwd)
        branch = str(session.get("git_branch") or "")
        if tree and branch.startswith(WORKTREE_BRANCHES):
            yield self._copy(
                start,
                "scratch directory: %s (git worktree the agent created in %s, branch %s)"
                % (cwd, tree.group(1), branch),
                start.model,
            )

    def _retired_rows(
        self, artifact, connection, sessions: dict, record_errors: list
    ) -> Iterator[Row]:
        """One `session deleted:` row per `state_meta` deletion fence
        `gateway.retired_session.v1.<session id>`
        (hermes_state_mutation_retirement.py at 86fa9e6), at its `retired_at`,
        with ` sweep` after the id when a sweep, not a delete, retired it
        (`expires`)."""
        for table_row in connection.execute(
            "select rowid as _rowid, key, value from state_meta where key like ? order by rowid",
            (RETIRED_PREFIX + "%",),
        ):
            session_id = str(table_row["key"])[len(RETIRED_PREFIX) :]
            session = sessions.get(session_id) or {"id": session_id}
            project = str(session.get("cwd") or session.get("git_repo_root") or "")
            try:
                value = json.loads(table_row["value"] or "")
                reason = "not a JSON object"
            except (TypeError, ValueError) as error:
                value, reason = None, str(error)
            if not isinstance(value, dict):
                label = "unparseable record %s (state_meta.value: %s)" % (
                    table_row["_rowid"],
                    reason,
                )
                record_errors.append(
                    (
                        session_id,
                        project,
                        (table_row["_rowid"], label, str(table_row["value"] or "")),
                    )
                )
                continue
            row = self._system(
                artifact,
                table_row["_rowid"],
                session,
                "session deleted: %s%s (from state.db state_meta gateway.retired_session.v1,"
                " retired_at)" % (session_id, " sweep" if value.get("expires") else ""),
            )
            row.timestamp_utc = to_utc(value.get("retired_at"))
            yield row

    def _generation_rows(self, artifact, connection) -> Iterator[Row]:
        """One `relay peer:` row per `conversation_generations` row, which
        Hermes never deletes: the messaging chats that ever had a
        conversation. The table has no time, so the rows have none."""
        for table_row in connection.execute(
            "select rowid as _rowid, source, session_key, generation"
            " from conversation_generations order by rowid"
        ):
            yield self._system(
                artifact,
                table_row["_rowid"],
                {},
                "relay peer: %s %s generation %s (from state.db conversation_generations)"
                % (
                    _dash(table_row["source"]),
                    _dash(table_row["session_key"]),
                    _dash(table_row["generation"]),
                ),
            )

    def _room_rows(self, artifact, connection, tables, record_errors: list) -> Iterator[Row]:
        """One `system` row per Bot Mode room event (`hosted_room_events`,
        gateway/hosted_rooms.py at 86fa9e6), at its `created_at`: `bot mode
        room <name> (<room_id>) seq <seq> <kind> actor <actor kind>:<actor
        id> (<display_name>): <text>` for a `message.user` or
        `message.member` event, the payload as compact JSON for the other
        kinds. Whether a room message is also a `messages` row was not
        determined, so these are never `user` rows."""
        names: dict[str, str] = {}
        if "hosted_rooms" in tables:
            for table_row in connection.execute("select room_id, name from hosted_rooms"):
                names[str(table_row["room_id"])] = str(table_row["name"] or "")
        for table_row in connection.execute(
            "select rowid as _rowid, * from hosted_room_events order by created_at, room_id, seq"
        ):
            table_row = dict(table_row)
            parsed = [
                self._room_json(table_row, column, record_errors)
                for column in ("actor_json", "payload_json")
            ]
            actor, payload = parsed
            if actor is None or payload is None:
                continue
            kind = str(table_row.get("kind") or "")
            room = str(table_row.get("room_id") or "")
            body = payload.get("text") if kind in ("message.user", "message.member") else None
            row = self._system(
                artifact,
                table_row["_rowid"],
                {},
                "bot mode room %s (%s) seq %s %s actor %s:%s (%s): %s"
                % (
                    _dash(names.get(room)),
                    room,
                    _dash(table_row.get("seq")),
                    kind,
                    _dash(actor.get("kind")),
                    _dash(actor.get("id")),
                    _dash(actor.get("display_name")),
                    body if isinstance(body, str) else compact_json(payload),
                ),
            )
            row.timestamp_utc = to_utc(table_row.get("created_at"))
            yield row

    @staticmethod
    def _room_json(room_event: dict, column: str, record_errors: list) -> dict | None:
        """`hosted_room_events.<column>` of event `r` as a JSON object; None,
        with an entry in `record_errors`, when it does not decode to one."""
        try:
            value = json.loads(room_event.get(column) or "")
            reason = "not a JSON object"
        except (TypeError, ValueError) as error:
            value, reason = None, str(error)
        if isinstance(value, dict):
            return value
        label = "unparseable record %s (hosted_room_events.%s: %s)" % (
            room_event["_rowid"],
            column,
            reason,
        )
        record_errors.append(
            ("", "", (room_event["_rowid"], label, str(room_event.get(column) or "")))
        )
        return None

    # -- sessions/<id>.jsonl -------------------------------------------------------------
    def _parse_jsonl(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        errors: list[tuple] = []
        session = {"id": artifact.disk_path.name[: -len(".jsonl")]}
        tool_names: dict[str, str] = {}
        switches: dict[str, str] = {}
        for line_number, record in iter_jsonl(artifact.disk_path, errors):
            yield from self._message_rows(
                artifact, record, session, line_number, tool_names, opts, switches
            )
        yield from error_rows(
            self,
            artifact,
            errors,
            str(session.get("id") or ""),
            str(session.get("cwd") or session.get("git_repo_root") or ""),
        )

    # -- pastes/pending.json -------------------------------------------------------------
    def _parse_pastes(self, artifact: Artifact) -> Iterator[Row]:
        """One `debug report uploaded:` row per entry, at `expire_at` minus
        the 6-hour paste lifetime; a file that is not a JSON list is one
        `parser:` row and an entry that is not an object with a `url` is
        its own row carrying the entry."""
        try:
            document = json.loads(artifact.disk_path.read_bytes().decode("utf-8", errors="replace"))
        except (OSError, ValueError) as error:
            yield from error_rows(
                self, artifact, [(0, "pastes/pending.json did not parse (%s)" % error, "")]
            )
            return
        if not isinstance(document, list):
            yield from error_rows(
                self, artifact, [(0, "pastes/pending.json is not a JSON list", "")]
            )
            return
        errors: list = []
        for position, entry in enumerate(document, 1):
            if not isinstance(entry, dict) or not entry.get("url"):
                errors.append(
                    (
                        position,
                        "unparseable record %d (not an object with a url)" % position,
                        compact_json(entry),
                    )
                )
                continue
            row = self._system(
                artifact,
                position,
                {},
                "debug report uploaded: %s (from pastes/pending.json, expire_at minus 6 hours)"
                % entry["url"],
            )
            expire = entry.get("expire_at")
            if isinstance(expire, (int, float)) and not isinstance(expire, bool):
                row.timestamp_utc = to_utc(expire - PASTE_LIFETIME)
            yield row
        yield from error_rows(self, artifact, errors)

    def _read_json(self, artifact: Artifact, name: str, errors: list):
        """The decoded JSON document of `artifact`, or None with a whole-file
        entry naming `name` appended to `errors` when it cannot be read."""
        try:
            return json.loads(artifact.disk_path.read_bytes().decode("utf-8", errors="replace"))
        except (OSError, ValueError) as error:
            errors.append((0, "%s did not parse (%s)" % (name, error), ""))
            return None

    def _setting(self, artifact: Artifact, line: int, text: str, timestamp: str) -> Row:
        row = self._system(artifact, line, {}, text)
        row.timestamp_utc = timestamp
        return row

    # -- config.yaml (issue 208) ---------------------------------------------------------
    def _parse_config(self, artifact: Artifact) -> Iterator[Row]:
        """One `permission setting: command_allowlist=<pattern> (from
        config.yaml, file mtime)` row per entry of the top-level
        `command_allowlist` block list, the patterns an "always" answer
        approved for good (tools/approval.py:401-495 at 86fa9e6). The
        nested `approvals` settings are not read. Any other construct under
        the key is one whole-file `parser:` row after the entries before it."""
        errors: list = []
        try:
            text = artifact.disk_path.read_bytes().decode("utf-8", errors="replace")
        except OSError as error:
            errors.append((0, "config.yaml could not be read (%s)" % error, ""))
            text = ""
        entries, problem = read_flat_list(text.splitlines(), "command_allowlist")
        timestamp = file_mtime(artifact) if entries else ""
        for line_number, pattern in entries:
            yield self._setting(
                artifact,
                line_number,
                "permission setting: command_allowlist=%s (from config.yaml, file mtime)" % pattern,
                timestamp,
            )
        if problem:
            errors.append(
                (0, "config.yaml command_allowlist is not a flat list (%s)" % problem, "")
            )
        yield from error_rows(self, artifact, errors)

    # -- pairing/<platform>-approved.json (issue 208) ------------------------------------
    def _parse_pairing(self, artifact: Artifact, match: re.Match) -> Iterator[Row]:
        """One `permission setting: pairing.<platform>.<user id>
        user_name=<user_name> (from <dir>/<platform>-approved.json,
        approved_at)` row per user the gateway's owner approved to drive the
        agent (gateway/pairing.py:431-438 at 86fa9e6), at `approved_at`."""
        name = "%s/%s-approved.json" % (match.group(1), match.group(2))
        errors: list = []
        document = self._read_json(artifact, name, errors)
        if document is not None and not isinstance(document, dict):
            errors.append((0, "%s is not a JSON object" % name, ""))
            document = None
        for position, (user, info) in enumerate((document or {}).items(), 1):
            if not isinstance(info, dict):
                label = "unparseable record %d (not an object)" % position
                errors.append((position, label, compact_json({user: info})))
                continue
            yield self._setting(
                artifact,
                position,
                "permission setting: pairing.%s.%s user_name=%s (from %s, approved_at)"
                % (match.group(2), user, _dash(info.get("user_name")), name),
                to_utc(info.get("approved_at")),
            )
        yield from error_rows(self, artifact, errors)

    # -- .hermes_history (issue 208) -----------------------------------------------------
    def _parse_history(self, artifact: Artifact) -> Iterator[Row]:
        """The prompt history of the classic CLI and the TUI, prompt_toolkit's
        `FileHistory` form read with the Aider parser's `read_input_history`:
        one `user` row per entry at its time, or a `system` row `slash
        command: <entry>` for an entry that starts with `/`, with no session
        or project. The TUI writes UTC times with milliseconds, the classic
        CLI host-local ones with microseconds; both are emitted as written."""
        errors: list = []
        for line_number, timestamp, text in read_input_history(artifact.disk_path, errors):
            row = self.base_row(artifact)
            row.source_line = line_number
            row.timestamp_utc = to_utc(timestamp)
            if text.startswith("/"):
                row.turn_type, row.text = "system", compact("slash command: " + text)
            else:
                row.turn_type, row.text = "user", compact(text)
            yield row
        yield from error_rows(self, artifact, errors)

    # -- cron/output/<job>/<time>.md (issue 208) -----------------------------------------
    def _parse_cron(self, artifact: Artifact, match: re.Match) -> Iterator[Row]:
        """A cron run's document (cron/scheduler.py:2238-2246 and 2634-2640 at
        86fa9e6): a `system` row `cron run: job <job id> (from cron/output,
        file name time, host-local)`, then the run's prompt as a `user` row
        and its response as an `assistant` row, or the whole document as a
        `system` row `cron run output: <document>` when it has no prompt and
        response sections. All at the file name's time, which is Hermes'
        configured zone or the host's, written as if UTC; no session id."""
        clock = CRON_TIME_RX.match(match.group(2))
        timestamp = to_utc("%sT%s:%s:%s" % clock.groups()) if clock else ""
        errors: list = []
        try:
            document = artifact.disk_path.read_bytes().decode("utf-8", errors="replace")
        except OSError as error:
            errors.append((0, "cron run file could not be read (%s)" % error, ""))
            document = ""
        rows = [("system", "cron run: job %s (from cron/output, file name time, host-local)")]
        parts = split_cron_doc(document) if document else None
        if parts:
            rows += [("user", parts[0]), ("assistant", parts[1])]
        elif document:
            rows.append(("system", "cron run output: " + document))
        for position, (turn_type, text) in enumerate(rows):
            row = self.base_row(artifact)
            row.source_line = position
            row.timestamp_utc = timestamp
            row.turn_type = turn_type
            row.text = compact(text % match.group(1) if position == 0 else text)
            yield row
        yield from error_rows(self, artifact, errors)

    # -- response_store.db (issue 208) ---------------------------------------------------
    def _parse_responses(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        """The API server's Responses store
        (gateway/platforms/api_server_response_store.py at 86fa9e6): per
        `responses` row, by the response's `created_at`, a `system` row `api
        server response <id> status=<status> model=<model>
        conversation=<name> (from response_store.db responses, created_at)`,
        then the messages of its `conversation_history` that an earlier
        response of the same session did not already hold at the same
        position (each row stores the whole history to that point), read as
        `state.db` messages with `data.session_id` and no time of their own."""
        if not is_sqlite(artifact.disk_path):
            yield self._system(artifact, 0, {}, "parser: not a SQLite database")
            return
        record_errors: list = []
        try:
            with open_copy(artifact.disk_path) as connection:
                tables = table_names(connection)
                if "responses" not in tables:
                    yield self._system(artifact, 0, {}, "parser: no responses table")
                    return
                names: dict[str, str] = {}
                if "conversations" in tables:
                    for table_row in connection.execute(
                        "select name, response_id from conversations"
                    ):
                        names[str(table_row["response_id"])] = str(table_row["name"])
                stored = self._responses(connection, record_errors)
        except sqlite3.DatabaseError as error:
            yield self._system(artifact, 0, {}, "parser: SQLite error: %s" % error)
            return
        seen: dict[str, set] = {}
        tool_names: dict[str, str] = {}
        switches: dict[str, str] = {}
        for _, rowid, response_id, data in stored:
            session_id = str(data.get("session_id") or "")
            response = data.get("response") if isinstance(data.get("response"), dict) else {}
            header = self._system(
                artifact,
                rowid,
                {"id": session_id},
                "api server response %s status=%s model=%s conversation=%s"
                " (from response_store.db responses, created_at)"
                % (response_id, _dash(response.get("status")), _dash(response.get("model")),
                   _dash(names.get(response_id))),
            )  # fmt: skip
            header.timestamp_utc = to_utc(response.get("created_at"))
            yield header
            history = data.get("conversation_history")
            for i, message in enumerate(history if isinstance(history, list) else []):
                if not isinstance(message, dict):
                    label = "unparseable record %s (responses.data conversation_history %d" % (
                        rowid,
                        i,
                    )
                    record_errors.append((rowid, label + ": not an object)", compact_json(message)))
                    continue
                key = (i, compact_json(message))
                if key in seen.setdefault(session_id, set()):
                    continue
                seen[session_id].add(key)
                yield from self._message_rows(
                    artifact, message, {"id": session_id}, rowid, tool_names, opts, switches
                )
        yield from error_rows(self, artifact, record_errors)

    @staticmethod
    def _responses(connection, record_errors: list) -> list[tuple]:
        """(created_at, rowid, response_id, data) per `responses` row whose
        `data` decodes to an object, by the response's `created_at`."""
        out = []
        for table_row in connection.execute(
            "select rowid as _rowid, response_id, data from responses"
        ):
            try:
                data = json.loads(table_row["data"] or "")
                reason = "not a JSON object"
            except (TypeError, ValueError) as error:
                data, reason = None, str(error)
            if not isinstance(data, dict):
                label = "unparseable record %s (responses.data: %s)" % (table_row["_rowid"], reason)
                record_errors.append((table_row["_rowid"], label, str(table_row["data"] or "")))
                continue
            response = data.get("response")
            created = response.get("created_at") if isinstance(response, dict) else None
            if not isinstance(created, (int, float)) or isinstance(created, bool):
                created = 0
            out.append((created, table_row["_rowid"], str(table_row["response_id"] or ""), data))
        out.sort(key=lambda entry: (entry[0], entry[1]))
        return out

    # -- trajectory_samples.jsonl, failed_trajectories.jsonl (issue 208) -------------------
    def _parse_trajectory(self, artifact: Artifact) -> Iterator[Row]:
        """A `--save-trajectories` file in the run's working directory
        (agent/trajectory.py:37-41 at 86fa9e6): per line a `system` row
        `trajectory: model=<model> completed=<completed> (from <file>,
        timestamp host-local)` at the line's `timestamp` (local time without
        a zone, written as if UTC), then one row per ShareGPT entry of
        `conversations` with no time of its own: `human` a `user` row,
        `gpt` an `assistant` row, `tool` a `tool_result` row, `system` a
        `system` row `trajectory system prompt: <value>`, any other a
        `system` row `<from>: <value>`. No session; the project is the
        directory the file was collected from."""
        errors: list = []
        project = artifact.home.original if artifact.home.project else ""
        name = artifact.disk_path.name
        with open(artifact.disk_path, "rb") as handle:
            for line_number, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                try:
                    record = json.loads(raw.decode("utf-8", errors="replace"))
                    reason = "not a JSON object"
                except ValueError as error:
                    record, reason = None, str(error)
                if not isinstance(record, dict):
                    errors.append((line_number, "unparseable line (%s)" % reason, line_text(raw)))
                    continue
                conversations = record.get("conversations")
                if not isinstance(conversations, list):
                    reason = "conversations is not a list"
                    errors.append((line_number, "unparseable line (%s)" % reason, line_text(raw)))
                    continue
                head = self.base_row(artifact)
                head.source_line, head.project_path, head.turn_type = line_number, project, "system"
                head.model = str(record.get("model") or "")
                head.timestamp_utc = to_utc(record.get("timestamp"))
                head.text = "trajectory: model=%s completed=%s (from %s, timestamp host-local)" % (
                    _dash(record.get("model")),
                    _dash(record.get("completed")),
                    name,
                )
                yield head
                for entry in conversations:
                    row = self.base_row(artifact)
                    row.source_line, row.project_path, row.model = line_number, project, head.model
                    sender = entry.get("from") if isinstance(entry, dict) else None
                    value = text_of(entry.get("value")) if isinstance(entry, dict) else ""
                    if sender in TRAJECTORY_TYPES:
                        row.turn_type, row.text = TRAJECTORY_TYPES[sender], compact(value)
                    elif sender == "system":
                        row.turn_type = "system"
                        row.text = compact("trajectory system prompt: " + value)
                    else:
                        row.turn_type = "system"
                        row.text = compact("%s: %s" % (_dash(sender), value or compact_json(entry)))
                    yield row
        yield from error_rows(self, artifact, errors, "", project)

    # -- Hermes desktop connections.json (issue 208) -----------------------------------
    def _parse_connections(self, artifact: Artifact) -> Iterator[Row]:
        """The desktop app's connection registry
        (apps/desktop/electron/connection-registry.ts at 86fa9e6): one
        `remote backend: <kind> <label> <url, or user@host:port for ssh>
        (from connections.json, file mtime)` row per connection that is not
        the app's own `local` runtime, ending with ` org=`, ` name=` and
        ` profile=` when recorded, and `remote backend quarantined by the app:
        <reason> (from connections.json, file mtime)` per entry the app could
        not load. Tokens and headers are never printed."""
        errors: list = []
        document = self._read_json(artifact, "connections.json", errors)
        connections = document.get("connections") if isinstance(document, dict) else None
        if document is not None and not isinstance(connections, list):
            errors.append((0, "connections.json has no connections list", ""))
        timestamp = file_mtime(artifact)
        tail = " (from connections.json, file mtime)"
        for position, connection in enumerate(
            connections if isinstance(connections, list) else [], 1
        ):
            if not isinstance(connection, dict):
                errors.append(
                    (
                        position,
                        "unparseable record %d (not an object)" % position,
                        compact_json(connection),
                    )
                )
                continue
            if connection.get("kind") == "local":
                continue
            target = connection.get("url")
            if not target and connection.get("host"):
                target = "%s%s%s" % (
                    "%s@" % connection["user"] if connection.get("user") else "",
                    connection["host"],
                    ":%s" % connection["port"] if connection.get("port") else "",
                )
            text = "remote backend: %s %s %s" % (
                _dash(connection.get("kind")),
                _dash(connection.get("label")),
                _dash(target),
            )
            for key, label in (("org", "org"), ("name", "name"), ("remoteProfile", "profile")):
                if connection.get(key):
                    text += " %s=%s" % (label, setting_value(connection[key]))
            yield self._setting(artifact, position, text + tail, timestamp)
        quarantined = document.get("quarantined") if isinstance(document, dict) else None
        for entry in quarantined if isinstance(quarantined, list) else []:
            reason = entry.get("reason") if isinstance(entry, dict) else None
            text = "remote backend quarantined by the app: %s" % _dash(reason)
            yield self._setting(artifact, 0, text + tail, timestamp)
        yield from error_rows(self, artifact, errors)
