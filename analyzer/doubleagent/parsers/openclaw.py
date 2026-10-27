"""OpenClaw (formerly Clawdbot and Moltbot) agent transcripts.

Validated against source, openclaw/openclaw at 3b16db7 and, for the
relay, permission, model-override, past-use, deletion and PostgreSQL
anchor rows (issue 206), at 146284a (see `research/openclaw.md`), with
a synthetic fixture; no real install was checked, so every row named
below rests on source alone. The state directory is `.openclaw`, a profile's
`.openclaw-<profile>`, or the legacy `.clawdbot` / `.moltbot`. Files:

* `agents/<agentId>/agent/openclaw-agent.sqlite` (WAL, opened through
  `sqlite_util`), the live store since mid-2026:
  - `transcript_events(session_id, seq, event_json, event_zstd,
    created_at)`: one entry per row. Rows of 1 KiB to 4 MiB may hold the
    entry as one zstd frame in `event_zstd` with `event_json` NULL, decoded
    with the `zstandard` package; a frame that does not decode becomes one
    `system` row. `created_at` is epoch ms.
  - `session_windows(session_id, session_key, previous_session_id, reason,
    channel, account_id, chat_type, model_provider, model, started_at,
    parent_session_key, spawned_by, display_name)`: one row per transcript
    generation, read for the session-start row.
  - `session_transcript_archives(session_id, session_key, reason, encoding,
    archive_blob, archive_name, created_at)`: reset or deleted
    generations as JSONL (zstd when `encoding` is `zstd`), every one parsed,
    whether or not `published_at` says it was also written to the sessions
    directory. The schema calls this table the
    canonical owner of a reclaimed generation, from which the
    `.jsonl.reset.*` / `.jsonl.deleted.*` file is derived and may be
    recreated (`openclaw-agent-schema.sql:606-607`), so the blob is the
    primary copy and the file the secondary one.
  - `session_transcript_cold_archives(session_id, archive_name, storage,
    archive_blob)` with `storage` `sqlite`: a zstd JSONL envelope of
    `{"kind":"event","row":{"seq","event_json","created_at"}}` records
    (`src/config/sessions/session-cold-storage-codec.ts:48-100`, not in the
    research document). `storage` `file` means
    `agents/<id>/sessions/cold/<sha256>.jsonl.zst`, parsed as a file.
  - `session_nodes(rowid, session_key, current_session_id, entry_json)`:
    the session-metadata entry of each session key. Its `publicShare`
    `{id, sessionId, createdAt}` (a 48-hex grant id, the transcript
    generation it publishes, epoch ms; absent on a session never
    published, removed when access is turned off) marks a session whose
    user messages and final answers anyone with the public URL can read,
    served by the Gateway: one `session synced: public share <id>
    generation <sessionId> (from openclaw-agent.sqlite
    session_nodes.entry_json, publicShare.createdAt)` row after that
    generation's session-start row, at `createdAt`, `session_id` the
    generation (`records_sync`). A grant whose generation has no
    transcript rows in the database still yields its row, after the
    others. An `entry_json` that does not decode is its own `parser:` row
    carrying the column in full. The share URL's token is not stored.
    Fixture only: no real install has shown the key.
    The same `entry_json` gives, attached after the start row of the
    session's current generation (`current_session_id`) and timestamped
    by `session_nodes.updated_at` unless stated: `model: <modelOverride>
    provider=<providerOverride> source=<modelOverrideSource>[
    fallback_from=<modelOverrideFallbackOriginProvider>/<...Model>] (from
    openclaw-agent.sqlite session_nodes.entry_json modelOverride,
    updated_at)`, the model column set to `modelOverride`
    (`src/config/sessions/types.ts:502-516`; the entry keeps only the
    current override, so the row names no previous model); one
    `permission setting: <key>=<value> (from openclaw-agent.sqlite
    session_nodes.entry_json, updated_at)` per `elevatedLevel`, `execHost`,
    `execNode`, `execCwd`, `toolOverrides` (compact JSON) and `sendPolicy`
    (`types.ts:481-500`, `532`); `session archived: <archiveReason> by
    <archivedBy.type>:<archivedBy.id> (from openclaw-agent.sqlite
    session_nodes.entry_json, archivedAt)` at `archivedAt`
    (`types.ts:300-305`); and, when no conversation or window below gave
    the generation a relay row, `session relayed: <route.channel> account
    <route.accountId or origin.accountId> <origin.chatType> from
    <origin.from> to <origin.to> (from openclaw-agent.sqlite
    session_nodes.entry_json delivery, updated_at)` for a `delivery` of
    kind `external` (`types.ts:60-83`).
  - Relay (`records_relay`), attached after a generation's start row:
    `session relayed: <channel> account <account_id> <kind> peer
    <peer_id> thread <thread_id> role <role> (from openclaw-agent.sqlite
    session_conversations and conversations, first_seen_at)` per
    `session_conversations` link to a `conversations` row; else
    `session relayed: <channel> account <account_id> <chat_type> (from
    openclaw-agent.sqlite session_windows, started_at)` from
    `session_windows`; and `session relayed: gmail hook (from
    openclaw-agent.sqlite session_windows hook_external_content_source,
    started_at)` for a session a Gmail hook started. The Control UI
    channel `webchat` and the internal wake channels (`heartbeat`, `cron`,
    `webhook`, `voice`, `sessions_send`;
    `src/utils/message-channel-constants.ts:3`, `14-20`) are no platform.
  - `session_transcript_archives` rows with `reason` `deleted` add
    `session deleted: <session_id> archive <archive_name> (from
    openclaw-agent.sqlite session_transcript_archives reason deleted,
    created_at)` after the archive's rows.
  - `session_pending_inputs(seq, input_id, session_id, run_id,
    message_json, state, accepted_at, consumed_event_id)`, each accepted
    prompt (`message_json` a user message, `content`): a row never
    consumed (`consumed_event_id` NULL; a cancelled or interrupted prompt
    never reaches the transcript) yields a `user` row and `pending input:
    <state>, not consumed by the transcript (input <input_id> run
    <run_id>; from openclaw-agent.sqlite session_pending_inputs,
    accepted_at)`, at `accepted_at`, `source_line` the `seq`; a consumed
    one yields its `user` row, marked `recovered`, only when the
    transcript entry `consumed_event_id` names is not in the database. A
    `message_json` that does not decode is its own `parser:` row.
  - `session_transcript_fts`, the FTS5 index behind session search, read
    from its content table `session_transcript_fts_content` (`c0` text,
    `c1` session_id, `c2` message_id, `c3` role, `c4` timestamp) as a
    plain table: a `user` or `assistant` row (else `system`, `<role>:
    <text>`) per indexed entry whose `(session_id, message_id)` no
    transcript row of the database carries, marked `recovered`.
  - `conversation_deliveries` joined to `conversations`: `channel
    delivery: <operation_kind> <status> channel <channel> conversation
    <conversation_id> platform message <platform_message_id>[
    error=<rejection_error>] (from openclaw-agent.sqlite
    conversation_deliveries, created_at)` and, when a platform message
    replied to it, `channel delivery reply: <reply_text> (reply message
    <reply_message_id>; from openclaw-agent.sqlite
    conversation_deliveries, reply_timestamp)`; `session_id` is the
    current generation of `source_session_key`.
  - `memory_session_tombstones`: `session forgotten from memory:
    <session_id> agent <agent_id> reason=<reason> (from
    openclaw-agent.sqlite memory_session_tombstones, created_at)`.
  The full-text index and the pending inputs repeat transcript entries
  inside the primary database, where `secondary()` cannot mark them, so
  the parser joins them itself on the entry id and keeps only what the
  transcript lost. Rows read after the transcripts carry the `cwd` of
  their generation's header when the database has one.
  - `auth_profile_store`, `auth_profile_state` and `session_suggestions`
    hold credentials and are never read.
  - With the PostgreSQL engine the file is an anchor holding only
    `openclaw_engine_anchor(store_id, engine, schema)`
    (`src/infra/database-engine/open.ts:149`): one whole-file row
    `parser: agent database is a PostgreSQL anchor (store <store_id>,
    schema <schema>): transcripts are on the database server`.
* `state/openclaw.sqlite` (WAL, opened through `sqlite_util`), the
  Gateway's state database, table `backup_runs(id, created_at,
  archive_path, status, manifest_json)`, one row per `openclaw backup`
  attempt (`src/state/openclaw-state-schema.sql:1843-1849`), with
  `manifest_json` `{kind, target, namespace, pushFailed, bytes, location
  {name, provider, locationId, key, namespace, ...}}`
  (`src/state/backup-run-records.contract.ts:98-124`). A backup uploads
  the whole state directory, every agent database included, so the row is
  host-wide, not per session: one `system` row with an empty `session_id`
  per run with `status` `ok` and either a `location` (an upload to a
  storage location) or a Git `target` (the commit sha) without
  `pushFailed`, at `created_at`: `backup uploaded: <kind> to
  <location.name or archive_path> key <location.key or target> namespace
  <location.namespace or namespace or -> (from state/openclaw.sqlite
  backup_runs, created_at)`. A Git backup run without `--push` records
  the same manifest as a pushed one (`src/commands/backup-git.ts:140-151`),
  so a Git row says a commit was made and, unless the push failed, may
  have been pushed. A `manifest_json` that does not decode is its own
  `parser:` row carrying the column in full; a file that is not SQLite or
  does not open is one `parser:` row; a PostgreSQL anchor is one row
  `parser: state database is a PostgreSQL anchor (store <store_id>,
  schema <schema>): the Gateway state is on the database server`. Also
  read (`src/state/openclaw-state-schema.sql:356-475`, `512-529`,
  `794-801`, `1273-1294` at 146284a):
  - `operator_approvals(approval_id, kind, status, decision,
    terminal_reason, resolver_kind, source_session_id,
    source_tool_call_id, source_tool_name, created_at_ms,
    resolved_at_ms)`: `permission decision: <decision, else status>
    status=<status> kind=<kind> resolver=<resolver_kind>
    reason=<terminal_reason> approval <approval_id> (from
    state/openclaw.sqlite operator_approvals, <resolved_at_ms or
    created_at_ms>)` at that time, `session_id` `source_session_id`,
    `tool_name` `source_tool_name` and `tool_use_id`
    `source_tool_call_id`, so it joins the call it governed.
  - `exec_approvals_config(raw_json, updated_at_ms)`, the migrated
    `exec-approvals.json`: one `permission setting: <scope>.<setting>
    (from state/openclaw.sqlite exec_approvals_config, updated_at_ms)`
    per `security`, `ask`, `askFallback` and `autoAllowSkills`
    (`<key>=<value>`), allowlist entry (`allowlist=<pattern>[
    argPattern=<argPattern>] source=<source>`) and MCP tool grant
    (`mcpTools=<server>/<tool> source=<source>`) of `defaults` and of
    each `agents.<id>`. `socket` holds the approvals socket token and is
    never read; a `raw_json` that does not decode is one `parser:` row
    without the text, for the same reason.
  - `operator_approval_standing_grants`: `permission setting: standing
    grant <grant_id> allow-always cron job <cron_job_id> agent <agent_id>
    binding <operation_binding> approval <minted_by_approval_id>
    expires=<expires_at_ms> revoked=<revoked_at_ms> uses=<use_count> (from
    state/openclaw.sqlite operator_approval_standing_grants,
    created_at_ms)`.
  - `channel_pairing_allow_entries`: `permission setting: channel
    <channel_key> account <account_id> allowFrom=<entry> (from
    state/openclaw.sqlite channel_pairing_allow_entries, updated_at)`.
  - `channel_ingress_events`: `channel ingress: <channel_id> account
    <account_id> status <status>: <payload_json> (from
    state/openclaw.sqlite channel_ingress_events, received_at)`, the
    payload whole, since its shape per channel is not in the research;
    no session id.
  - `github_publication_requests`, `github_personal_publication_requests`
    and `github_repository_publication_requests` (lines 2093-2140,
    2410-2482, 2488-2531), one row per push or pull request the Gateway
    made on GitHub for a session: `source host: github account
    <identity_login> id <identity_account_id> identity <identity_source>;
    publication <status> repository <repository> branch <branch> pull
    request <pull_request_url> (from state/openclaw.sqlite <table>,
    created_at_ms)`, `session_id` the session. The OAuth token
    (`secret_store_entries`, name `github-oauth-<32 hex>`) is never read.
  - `projects(repo_root, origin_url, created_at_ms)` (lines 1901-1909),
    one row per repository registered with or cloned by the Gateway: a
    `git remote: <origin_url>` row at `created_at_ms` for a row whose
    `origin_url` is set, `project_path` the `repo_root`, no `session_id`
    (issue 253).
  Its other tables are not read. Fixture only.
* `agents/<agentId>/sessions/<sessionId>.jsonl` (and `sessions/` at the
  state root, the older single-agent layout): legacy transcripts not yet
  imported by `openclaw doctor`. The sibling legacy `sessions.json`,
  `{<sessionKey>: {"sessionId", ...}}`
  (`src/infra/state-migrations.legacy-session-store.ts:202-205`), gives the
  session key.
* Copies of a transcript in the same `sessions/` directory, each a
  secondary source (`secondary()`), in the same entry format and read the
  same way; their rows carry the entries' own timestamps, ids and header
  `cwd`, so they pair exactly with the primary store's rows for the same
  entries:
  - `<sessionId>.jsonl.reset.<ts>[.<gen>][.zst]` and `.jsonl.deleted.<...>`:
    the published file of a `session_transcript_archives` blob, one zstd
    frame when `.zst`. Kept after the database is lost or excluded; the
    blob outlives the file otherwise, since retention deletes the row
    only once the file is gone (`session-history-archive-pruning.worker.ts:105-114`).
  - `<sessionId>.checkpoint.<uuid>.jsonl`: a pre-compaction snapshot,
    `fs.copyFile` of the session file before compaction (written by
    releases before openclaw/openclaw c59635a,
    `src/gateway/session-compaction-checkpoints.ts:383-389` at 6814525; no
    release at 3b16db7 writes new ones, `legacy-compaction-history.ts:3-7`).
    It holds the entries the compaction later summarised.
  - `<sessionId>.jsonl.pre-doctor-(branch|openai-codex)-repair-<ts>.bak`:
    `fs.copyFile` of a legacy transcript before `openclaw doctor` rewrote
    it (`src/commands/doctor-session-transcripts.ts:258-261`, `285-288` at
    6559e3f, before 4273ca9 removed the file-era runtime). A branch repair
    keeps only the active branch, so the copy holds the abandoned branches
    too, which no other store has.
  The session id of every JSONL file, the legacy transcript and its
  copies alike, is its header `id`, else the name before the suffix, so a
  copy carries the id the database and the legacy file carry: a session
  forked from a checkpoint was written as `<ts>_<sessionId>.jsonl` (line
  323 at 6814525), its own checkpoints named after that file, and an
  archive of an id over 96 bytes is named `session-<sha256>`
  (`session-accessor.sqlite-archive-artifact.ts:24-29`). The session-start
  row of a copy names it (`archive=<reason>.<ts>`, `copy=<suffix>`), so it
  never pairs and each copy shows one row of its own.
  Not read: `*.trajectory.jsonl`, the trajectory flight recorder, whose
  runtime events are a different schema (`openclaw-trajectory`,
  `docs/tools/trajectory.md:76-102`); `*.migrated[.N]`, whose transcript
  writer is not in the source at 3b16db7 or 6559e3f (the suffix is used
  there for other migrated files, cron logs and pairing stores); and the
  `.jsonl.bak.<ts>` legacy compact backups (`artifacts.ts:43-50`), whose
  content is not recorded.

Entry fields: header `{type:"session", version, id, timestamp, cwd,
parentSession}`; then `type`, `id`, `parentId`, `timestamp` (ISO 8601) and
per type `message` (`message`), `model_change` (`provider`, `modelId`),
`thinking_level_change` (`thinkingLevel`), `compaction` (`summary`,
`tokensBefore`, `tokensAfter`), `reset` (`reason`), `branch_summary`
(`summary`), `custom` (`customType`, `data`), `custom_message`
(`customType`, `content`), `label` (`label`, `targetId`), `session_info`
(`name`). `message.role`: `user` (`content`, `runtimeContext`,
`runtimeContextCarrier`), `assistant` (`content` blocks `text`, `thinking`
{`thinking`, `redacted`}, `toolCall` {`id`, `name`, `arguments`}, `image`;
`model`, `responseModel`, `stopReason`, `errorMessage`), `toolResult`
(`toolCallId`, `toolName`, `content`, `isError`), `bashExecution`
(`command`, `output`, `exitCode`, `cancelled`), `custom`, `branchSummary`,
`compactionSummary` (`summary`); `message.timestamp` is epoch ms.

Rows: one `system` row per session carrying the session key
(`agent:<agentId>:<channel>:<accountId>:direct:<peerId>` names the external
sender), channel, account, chat type and parent; `session_id` is the
transcript id (`transcript_events.session_id`, the header `id`), and
`project_path` the header `cwd`. User messages flagged `runtimeContext` are
injected context, not human input, and become `system` rows. A
`bashExecution` (a `!` command the operator ran) becomes a `tool_use` row
named `bash` and a `tool_result` row, joined on the entry `id`. An assistant
message that ended with `stopReason` `error` or `aborted`, or carries an
`errorMessage`, adds a `system` row. Model rows: `model: <id>
provider=<provider>` at the first model a session names (the
`session_windows` `model` and `model_provider`, at the session-start time,
else a `model_change` `modelId` or an assistant `responseModel`, else
`model`) and `model: <old> -> <new> provider=<provider>` on every later
entry whose model differs, with ` requested=<model>` when an assistant
`responseModel` differs from its `model` (`pi.model_text`). A
`model_change` entry naming the model already in force still yields the
plain `model: <id> provider=<provider>` row (`pi.switch_text`).
`audit_events` is not read: its `kind` and `action` values are not in
the research. Timestamps are the entry `timestamp`,
else the message's ms timestamp, else the row's `created_at`. `source_line`
is the `transcript_events` (or archive table) rowid, or the JSONL line. No
git branch is recorded.

A line that does not decode is its own `system` row (issue 136, `error_rows`
in `base.py`), carrying the line in full after `parser: unparseable line
(<reason>): `, with the session's id and `cwd`; a line that decodes to a
JSON value other than an object is the same row with the reason `not a
JSON object` (issue 177). A legacy `sessions.json` that cannot be read,
does not decode or is not a JSON object is one whole-file row in each
transcript beside it, `parser: sessions.json unreadable (<reason>)`,
`parser: sessions.json unparseable (<reason>)` or `parser: sessions.json
is not a JSON object`, with `source_line` 0, after the line rows;
the transcript's other rows are still yielded, without the key. For a line inside an archive
blob the text is `parser: archive <name> line <n>: unparseable line
(<reason>): <line>` (or `cold archive`) and `source_line` is the archive row's rowid, as for the blob's other rows.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator

from ..inputs import Artifact
from ..model import GIT_REMOTE_PREFIX, Row, compact
from ..sqlite_util import is_sqlite, open_copy, table_names
from ..timeutil import to_utc
from .base import Options, Parser, compact_json, error_rows, line_text, text_of
from .pi import model_text, switch_text
from .zed import decompress

STATE = r"(?:\.openclaw(?:-[^/]+)?|\.clawdbot|\.moltbot)"
DB_RX = re.compile(r"^" + STATE + r"/agents/[^/]+/agent/openclaw-agent\.sqlite$")
STATE_DB_RX = re.compile(r"^" + STATE + r"/state/openclaw\.sqlite$")
SESSIONS = r"^" + STATE + r"/(?:agents/[^/]+/)?sessions/"
ARCHIVE_SUFFIX = r"\.jsonl\.(reset|deleted)\.\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d(?:\.\d{3})?Z(?:\.[0-9a-f]{32})?(?:\.zst)?"
# A pre-compaction checkpoint and a pre-doctor repair backup (`artifacts.ts:13-17`).
COPY_SUFFIX = (
    r"\.checkpoint\.[0-9a-fA-F-]{36}\.jsonl"
    r"|\.jsonl\.pre-doctor-(?:branch|openai-codex)-repair-"
    r"\d{4}-\d\d-\d\dT\d\d-\d\d-\d\d-\d{3}Z\.bak"
)
JSONL_RX = re.compile(
    SESSIONS
    + r"(?P<name>[^/]+?)(?:(?P<archive>"
    + ARCHIVE_SUFFIX
    + r")|(?P<copy>"
    + COPY_SUFFIX
    + r")|\.jsonl)$"
)
COLD_RX = re.compile(SESSIONS + r"cold/[0-9a-f]{64}\.jsonl\.zst$")
SKIP_NAME_RX = re.compile(r"\.trajectory$")
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
# Channels that are not a messaging platform: the Control UI and the
# internal wake sources (`src/utils/message-channel-constants.ts:3`, `14-20`).
NOT_PLATFORMS = frozenset(("webchat", "heartbeat", "cron", "webhook", "voice", "sessions_send"))
# Per-session permission state in `session_nodes.entry_json`
# (`src/config/sessions/types.ts:481-500`, `532`).
SESSION_PERMISSION_KEYS = (
    "elevatedLevel",
    "execHost",
    "execNode",
    "execCwd",
    "toolOverrides",
    "sendPolicy",
)
# The GitHub publication requests of `state/openclaw.sqlite`, each naming the
# GitHub account that pushed or opened the pull request
# (`src/state/openclaw-state-schema.sql:2093-2140`, `2410-2482`, `2488-2531`).
GITHUB_PUBLICATION_TABLES = (
    "github_publication_requests",
    "github_personal_publication_requests",
    "github_repository_publication_requests",
)
# The `state/openclaw.sqlite` tables read, in the order their rows are yielded.
STATE_QUERIES = (
    (
        "backup_runs",
        "select rowid as _rowid, id, created_at, archive_path, status, manifest_json"
        " from backup_runs order by created_at, id",
    ),
    (
        "operator_approvals",
        "select rowid as _rowid, approval_id, kind, status, decision, terminal_reason,"
        " resolver_kind, source_session_id, source_tool_call_id, source_tool_name,"
        " created_at_ms, resolved_at_ms from operator_approvals order by created_at_ms, rowid",
    ),
    (
        "exec_approvals_config",
        "select rowid as _rowid, raw_json, updated_at_ms from exec_approvals_config order by rowid",
    ),
    (
        "operator_approval_standing_grants",
        "select rowid as _rowid, grant_id, minted_by_approval_id, agent_id, cron_job_id,"
        " operation_binding, created_at_ms, expires_at_ms, revoked_at_ms, use_count"
        " from operator_approval_standing_grants order by created_at_ms, rowid",
    ),
    (
        "channel_pairing_allow_entries",
        "select rowid as _rowid, channel_key, account_id, entry, updated_at"
        " from channel_pairing_allow_entries order by channel_key, account_id, sort_order",
    ),
    (
        "channel_ingress_events",
        "select rowid as _rowid, channel_id, account_id, status, payload_json, received_at"
        " from channel_ingress_events order by received_at, rowid",
    ),
    *(
        (
            table,
            "select rowid as _rowid, session_id, identity_source, identity_account_id,"
            " identity_login, status, repository, branch, pull_request_url, created_at_ms"
            " from %s order by created_at_ms, rowid" % table,
        )
        for table in GITHUB_PUBLICATION_TABLES
    ),
    (
        "projects",
        "select rowid as _rowid, repo_root, origin_url, created_at_ms"
        " from projects order by created_at_ms, rowid",
    ),
)


def tool_args_text(args) -> str:
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return args
    if isinstance(args, dict):
        for k in ("command", "path", "url"):
            if isinstance(args.get(k), str) and args[k]:
                return args[k]
    if args in (None, "", {}):
        return ""
    return compact_json(args)


def _maybe_zstd(blob: bytes) -> tuple[bytes | None, str]:
    """(data, error): zstd frames are decompressed, anything else returned."""
    blob = bytes(blob)
    if not blob.startswith(ZSTD_MAGIC):
        return blob, ""
    try:
        return decompress(blob), ""
    except Exception as error:  # noqa: BLE001 - zstandard.ZstdError or a stream read error
        return None, "%s: %s" % (type(error).__name__, error)


def _iter_lines(data: bytes, errors: list) -> Iterator[tuple[int, dict]]:
    """(line number, record) for each JSON object line of `data`; a line that
    does not decode, or decodes to a value other than an object (an array, a
    string, a number, `null`), is appended to `errors` as (line, message,
    line text), the message `unparseable line (not a JSON object)` for the
    second kind, so `error_rows` reports it in full (issue 177)."""
    for line_number, raw in enumerate(data.split(b"\n"), 1):
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            rec = json.loads(stripped.decode("utf-8", errors="replace"))
        except ValueError as error:
            errors.append((line_number, "unparseable line (%s)" % error, line_text(raw)))
            continue
        if not isinstance(rec, dict):
            errors.append((line_number, "unparseable line (not a JSON object)", line_text(raw)))
            continue
        yield line_number, rec


def _platform(channel) -> bool:
    """True for a channel id that names a messaging platform."""
    return isinstance(channel, str) and bool(channel) and channel not in NOT_PLATFORMS


def _delivery_relay(delivery) -> str:
    """The `session relayed:` text of an `entry_json.delivery` of kind
    `external` whose `route.channel` is a platform, else `""`
    (`src/config/sessions/types.ts:60-83`; `route` is a `ChannelRouteRef`,
    `src/plugin-sdk/channel-route.ts:18-25`)."""
    if not isinstance(delivery, dict) or delivery.get("kind") != "external":
        return ""
    route = delivery.get("route")
    route = route if isinstance(route, dict) else {}
    origin = delivery.get("origin")
    origin = origin if isinstance(origin, dict) else {}
    channel = route.get("channel")
    if not _platform(channel):
        return ""
    return (
        "session relayed: %s account %s %s from %s to %s (from openclaw-agent.sqlite"
        " session_nodes.entry_json delivery, updated_at)"
        % (
            channel,
            route.get("accountId") or origin.get("accountId") or "-",
            origin.get("chatType") or "-",
            origin.get("from") or "-",
            origin.get("to") or "-",
        )
    )


def _override_text(entry: dict) -> str:
    """The `model:` text of a session's `modelOverride`
    (`src/config/sessions/types.ts:502-516`)."""
    origin = "/".join(
        str(entry[k])
        for k in ("modelOverrideFallbackOriginProvider", "modelOverrideFallbackOriginModel")
        if entry.get(k)
    )
    return (
        "model: %s provider=%s source=%s%s (from openclaw-agent.sqlite"
        " session_nodes.entry_json modelOverride, updated_at)"
        % (
            entry.get("modelOverride"),
            entry.get("providerOverride") or "-",
            entry.get("modelOverrideSource") or "-",
            " fallback_from=%s" % origin if origin else "",
        )
    )


def _policy_settings(policy) -> list[str]:
    """`<key>=<value>` for each policy field, allowlist entry and MCP tool
    grant of one `defaults` or `agents.<id>` object of an exec approvals
    file (`packages/gateway-protocol/src/schema/exec-approvals.ts:15-75`)."""
    if not isinstance(policy, dict):
        return []
    out = []
    for key in ("security", "ask", "askFallback", "autoAllowSkills"):
        value = policy.get(key)
        if value is not None:
            out.append("%s=%s" % (key, json.dumps(value) if isinstance(value, bool) else value))
    allowlist = policy.get("allowlist")
    for entry in allowlist if isinstance(allowlist, list) else []:
        if isinstance(entry, dict) and entry.get("pattern") is not None:
            arg = " argPattern=%s" % entry["argPattern"] if entry.get("argPattern") else ""
            out.append(
                "allowlist=%s%s source=%s" % (entry["pattern"], arg, entry.get("source") or "-")
            )
    grants = policy.get("mcpTools")
    for grant in grants if isinstance(grants, list) else []:
        if isinstance(grant, dict):
            out.append(
                "mcpTools=%s/%s source=%s"
                % (grant.get("server") or "-", grant.get("tool") or "-", grant.get("source") or "-")
            )
    return out


def _grant_text(row: dict) -> str:
    """The `permission setting:` text of an `operator_approval_standing_grants`
    row, the grant an `allow-always` decision on a cron job mints."""
    return (
        "permission setting: standing grant %s allow-always cron job %s agent %s binding %s"
        " approval %s expires=%s revoked=%s uses=%s (from state/openclaw.sqlite"
        " operator_approval_standing_grants, created_at_ms)"
        % (
            row.get("grant_id") or "-",
            row.get("cron_job_id") or "-",
            row.get("agent_id") or "-",
            row.get("operation_binding") or "-",
            row.get("minted_by_approval_id") or "-",
            to_utc(row.get("expires_at_ms")) or "-",
            to_utc(row.get("revoked_at_ms")) or "-",
            row.get("use_count") if row.get("use_count") is not None else "-",
        )
    )


def _publication_text(table: str, row: dict) -> str:
    """The `source host:` text of a GitHub publication request: the account
    the Gateway pushed or opened the pull request as, and what it published."""
    return (
        "source host: github account %s id %s identity %s; publication %s repository %s"
        " branch %s pull request %s (from state/openclaw.sqlite %s, created_at_ms)"
        % (
            row.get("identity_login") or "-",
            row.get("identity_account_id") if row.get("identity_account_id") is not None else "-",
            row.get("identity_source") or "-",
            row.get("status") or "-",
            row.get("repository") or "-",
            row.get("branch") or "-",
            row.get("pull_request_url") or "-",
            table,
        )
    )


class _Db:
    """What one agent database's passes share: the rows to attach after a
    generation's session-start row, the transcript entry ids already
    yielded (for the exact joins of the full-text index and the pending
    inputs) and each generation's `cwd`."""

    def __init__(self) -> None:
        # {generation: [(source_line, timestamp, text, model)]}
        self.attached: dict[str, list[tuple[int, str, str, str]]] = {}
        self.ids: set[tuple[str, str]] = set()
        self.cwds: dict[str, str] = {}

    def attach(self, sid: str, line: int, timestamp: str, text: str, model: str = "") -> None:
        self.attached.setdefault(sid, []).append((line, timestamp, text, model))


class _Session:
    """State carried across one transcript's entries."""

    def __init__(
        self,
        session_id: str = "",
        key: str = "",
        extra: str = "",
        model: str = "",
        provider: str = "",
    ):
        self.session_id = session_id
        self.key = key
        self.extra = extra
        self.model = model
        self.provider = provider
        self.cwd = ""
        self.header_id = False  # True: the header `id` replaces session_id
        self.started = False
        self.seen: dict = {}  # the model in use, for the `model:` rows
        # The agent database's shared state; the session-start row pops the
        # rows attached to its generation and yields them.
        self.ctx: _Db | None = None


class OpenClawParser(Parser):
    agent = "openclaw"
    name = "openclaw"
    has_secondary = True
    records_sync = True
    records_relay = True

    def wants(self, artifact: Artifact) -> bool:
        rel = artifact.rel
        if DB_RX.match(rel) or COLD_RX.match(rel) or STATE_DB_RX.match(rel):
            return True
        match = JSONL_RX.match(rel)
        return bool(match) and not SKIP_NAME_RX.search(match.group("name"))

    def secondary(self, artifact: Artifact) -> bool:
        """The published archive files and the checkpoint and pre-doctor
        copies; the database and the plain legacy `.jsonl` are primary."""
        match = JSONL_RX.match(artifact.rel)
        return bool(match) and bool(match.group("archive") or match.group("copy"))

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        if DB_RX.match(artifact.rel):
            if is_sqlite(artifact.disk_path):
                yield from self._parse_db(artifact, opts)
        elif STATE_DB_RX.match(artifact.rel):
            yield from self._parse_state_db(artifact)
        else:
            yield from self._parse_file(artifact, opts)

    # -- rows -------------------------------------------------------------------
    def _row(
        self,
        artifact: Artifact,
        session: _Session,
        line: int,
        timestamp: str,
        turn_type: str,
        text: str,
        opts: Options,
        model: str = "",
        tool_name: str = "",
        tool_use_id: str = "",
    ) -> Row:
        row = self.base_row(artifact)
        row.source_line = line
        row.session_id = session.session_id
        row.project_path = session.cwd
        row.timestamp_utc = timestamp
        row.turn_type = turn_type
        row.model = model
        row.tool_name = tool_name
        row.tool_use_id = tool_use_id
        row.text = compact(text)
        return row

    def _start(
        self,
        artifact: Artifact,
        session: _Session,
        line: int,
        timestamp: str,
        header: dict | None,
        opts: Options,
    ) -> Iterator[Row]:
        """The session-start row, then a `model:` row when the session
        window names the model the session started with."""
        session.started = True
        header = header or {}
        if header.get("id") and (session.header_id or not session.session_id):
            session.session_id = str(header["id"])
        if isinstance(header.get("cwd"), str):
            session.cwd = header["cwd"]
        parent = header.get("parentSession")
        text = " ".join(
            part
            for part in (
                "session start:",
                "key=%s" % session.key if session.key else "",
                session.extra,
                "version=%s" % header["version"] if header.get("version") is not None else "",
                "parent_session=%s" % parent if parent else "",
            )
            if part
        )
        timestamp = timestamp or to_utc(header.get("timestamp"))
        yield self._row(artifact, session, line, timestamp, "system", text, opts, session.model)
        mtext = model_text(session.seen, session.session_id, session.model, session.provider)
        if mtext:
            yield self._row(
                artifact, session, line, timestamp, "system", mtext, opts, session.model
            )
        if session.ctx is not None:
            session.ctx.cwds.setdefault(session.session_id, session.cwd)
            for aline, ats, atext, amodel in session.ctx.attached.pop(session.session_id, []):
                yield self._row(artifact, session, aline, ats, "system", atext, opts, amodel)

    def _entry_rows(
        self, artifact: Artifact, session: _Session, line: int, rec: dict, created_at, opts: Options
    ) -> Iterator[Row]:
        etype = rec.get("type")
        msg = rec.get("message")
        if not isinstance(msg, dict):
            msg = {}
        timestamp = (
            to_utc(rec.get("timestamp")) or to_utc(msg.get("timestamp")) or to_utc(created_at)
        )
        if etype == "session":
            yield from self._start(artifact, session, line, timestamp, rec, opts)
            return
        if not session.started:
            yield from self._start(artifact, session, line, timestamp, None, opts)
        if session.ctx is not None and rec.get("id") not in (None, ""):
            session.ctx.ids.add((session.session_id, str(rec["id"])))
        if etype == "message":
            yield from self._message_rows(artifact, session, line, timestamp, rec, msg, opts)
            return

        def system(text: str, model: str = "") -> Row:
            return self._row(artifact, session, line, timestamp, "system", text, opts, model)

        if etype == "model_change":
            session.model = str(rec.get("modelId") or "")
            mtext = switch_text(
                session.seen, session.session_id, session.model, str(rec.get("provider") or "")
            )
            if mtext:
                yield system(mtext, session.model)
        elif etype == "thinking_level_change":
            yield system("thinking level: %s" % (rec.get("thinkingLevel") or ""))
        elif etype == "compaction":
            tokens = " ".join(
                part
                for part in (
                    "tokens_before=%s" % rec["tokensBefore"]
                    if rec.get("tokensBefore") is not None
                    else "",
                    "tokens_after=%s" % rec["tokensAfter"]
                    if rec.get("tokensAfter") is not None
                    else "",
                )
                if part
            )
            yield system(
                "compaction%s: %s" % (" (%s)" % tokens if tokens else "", rec.get("summary") or "")
            )
        elif etype == "reset":
            yield system("reset: %s" % (rec.get("reason") or ""))
        elif etype == "branch_summary":
            yield system("branch summary: %s" % (rec.get("summary") or ""))
        elif etype == "custom":
            yield system(
                "custom %s: %s" % (rec.get("customType") or "", compact_json(rec.get("data")))
            )
        elif etype == "custom_message":
            yield system(
                "custom message %s: %s" % (rec.get("customType") or "", text_of(rec.get("content")))
            )
        elif etype == "label":
            yield system(
                "label: %s (entry %s)" % (rec.get("label") or "", rec.get("targetId") or "")
            )
        elif etype == "session_info":
            yield system("session name: %s" % (rec.get("name") or ""))
        else:
            rest = {
                key: value
                for key, value in rec.items()
                if key not in ("type", "id", "parentId", "timestamp")
            }
            yield system("%s: %s" % (etype or "entry", compact_json(rest)))

    def _message_rows(
        self,
        artifact: Artifact,
        session: _Session,
        line: int,
        timestamp: str,
        rec: dict,
        msg: dict,
        opts: Options,
    ) -> Iterator[Row]:
        role = msg.get("role")
        if role == "user":
            text = text_of(msg.get("content"))
            if msg.get("runtimeContext") or msg.get("runtimeContextCarrier"):
                yield self._row(
                    artifact, session, line, timestamp, "system", "runtime context: " + text, opts
                )
            else:
                yield self._row(artifact, session, line, timestamp, "user", text, opts)
        elif role == "assistant":
            requested = str(msg.get("model") or "")
            model = str(msg.get("responseModel") or "") or requested or session.model
            if model:
                session.model = model
            if msg.get("responseModel") or requested:
                mtext = model_text(
                    session.seen,
                    session.session_id,
                    model,
                    str(msg.get("provider") or ""),
                    requested,
                )
                if mtext:
                    yield self._row(
                        artifact, session, line, timestamp, "system", mtext, opts, model
                    )
            content = msg.get("content")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    if block.get("text"):
                        yield self._row(
                            artifact,
                            session,
                            line,
                            timestamp,
                            "assistant",
                            str(block["text"]),
                            opts,
                            model,
                        )
                elif block_type == "thinking":
                    if opts.include_thinking:
                        thinking = block.get("thinking") or (
                            "[redacted thinking]" if block.get("redacted") else ""
                        )
                        if thinking:
                            yield self._row(
                                artifact,
                                session,
                                line,
                                timestamp,
                                "thinking",
                                str(thinking),
                                opts,
                                model,
                            )
                elif block_type == "toolCall":
                    yield self._row(
                        artifact,
                        session,
                        line,
                        timestamp,
                        "tool_use",
                        tool_args_text(block.get("arguments")),
                        opts,
                        model,
                        str(block.get("name") or ""),
                        str(block.get("id") or ""),
                    )
                elif block_type == "image":
                    yield self._row(
                        artifact, session, line, timestamp, "assistant", "[image]", opts, model
                    )
            stop = msg.get("stopReason")
            if stop in ("error", "aborted") or msg.get("errorMessage"):
                yield self._row(
                    artifact,
                    session,
                    line,
                    timestamp,
                    "system",
                    "assistant %s: %s" % (stop or "error", msg.get("errorMessage") or ""),
                    opts,
                    model,
                )
        elif role == "toolResult":
            text = text_of(msg.get("content"))
            if msg.get("isError"):
                text = "[error] " + text
            yield self._row(
                artifact,
                session,
                line,
                timestamp,
                "tool_result",
                text,
                opts,
                "",
                str(msg.get("toolName") or ""),
                str(msg.get("toolCallId") or ""),
            )
        elif role == "bashExecution":
            tid = str(rec.get("id") or "")
            yield self._row(
                artifact,
                session,
                line,
                timestamp,
                "tool_use",
                str(msg.get("command") or ""),
                opts,
                "",
                "bash",
                tid,
            )
            status = "exit=%s" % msg.get("exitCode")
            if msg.get("cancelled"):
                status += " cancelled"
            if msg.get("truncated"):
                status += " truncated"
            yield self._row(
                artifact,
                session,
                line,
                timestamp,
                "tool_result",
                "[%s] %s" % (status, msg.get("output") or ""),
                opts,
                "",
                "bash",
                tid,
            )
        elif role in ("branchSummary", "compactionSummary"):
            label = "branch summary" if role == "branchSummary" else "compaction summary"
            yield self._row(
                artifact,
                session,
                line,
                timestamp,
                "system",
                "%s: %s" % (label, msg.get("summary") or ""),
                opts,
            )
        elif role == "custom":
            yield self._row(
                artifact,
                session,
                line,
                timestamp,
                "system",
                "custom %s: %s" % (msg.get("customType") or "", text_of(msg.get("content"))),
                opts,
            )
        else:
            yield self._row(
                artifact,
                session,
                line,
                timestamp,
                "system",
                "%s: %s" % (role or "message", text_of(msg.get("content")) or compact_json(msg)),
                opts,
            )

    def _bad(
        self,
        artifact: Artifact,
        session: _Session,
        line: int,
        text: str,
        opts: Options,
        timestamp: str = "",
    ) -> Row:
        return self._row(artifact, session, line, timestamp, "system", "parser: " + text, opts)

    def _blob_errors(
        self, artifact: Artifact, session: _Session, rowid: int, label: str, errors: list
    ) -> Iterator[Row]:
        """`error_rows` for the bad lines of an archive blob: `source_line` the
        archive row's rowid and the message prefixed with `label` and the
        line's number in the blob (`archive <name> line 3: unparseable line
        (<reason>)`)."""
        located = [
            (rowid, "%s line %d: %s" % (label, line_number, msg), raw)
            for line_number, msg, raw in errors
        ]
        yield from error_rows(self, artifact, located, session.session_id, session.cwd)

    def _records(
        self, artifact: Artifact, session: _Session, records, opts: Options, fixed_line: int = 0
    ) -> Iterator[Row]:
        """Rows from (line, record) pairs of a JSONL transcript or a cold
        archive envelope; `fixed_line` overrides the line for blobs."""
        for line_number, rec in records:
            line = fixed_line or line_number
            if "kind" in rec and "type" not in rec:
                kind = rec.get("kind")
                if kind == "header" and not session.session_id:
                    session.session_id = str(rec.get("sessionId") or "")
                if kind != "event" or not isinstance(rec.get("row"), dict):
                    continue
                inner = rec["row"]
                try:
                    entry = json.loads(inner.get("event_json") or "")
                except (TypeError, ValueError) as error:
                    yield self._bad(
                        artifact,
                        session,
                        line,
                        "cold archive event seq %s unreadable: %s" % (inner.get("seq"), error),
                        opts,
                        to_utc(inner.get("created_at")),
                    )
                    continue
                if isinstance(entry, dict):
                    yield from self._entry_rows(
                        artifact, session, line, entry, inner.get("created_at"), opts
                    )
                continue
            yield from self._entry_rows(artifact, session, line, rec, None, opts)

    # -- JSONL files ----------------------------------------------------------------
    def _parse_file(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        match = JSONL_RX.match(artifact.rel)
        session = _Session(session_id=match.group("name") if match else "")
        session.header_id = True
        if match and match.group("archive"):
            session.extra = "archive=%s" % match.group("archive")[len(".jsonl.") :]
        elif match and match.group("copy"):
            session.extra = "copy=%s" % match.group("copy").lstrip(".")
        key_error = ""
        if match:
            session.key, key_error = self._legacy_key(artifact, session.session_id)
        with open(artifact.disk_path, "rb") as handle:
            raw = handle.read()
        data, err = _maybe_zstd(raw)
        if data is None:
            yield self._bad(artifact, session, 1, "could not decompress (%s)" % err, opts)
            if key_error:
                yield from error_rows(
                    self, artifact, [(0, key_error, "")], session.session_id, session.cwd
                )
            return
        errors: list = []
        yield from self._records(artifact, session, _iter_lines(data, errors), opts)
        if key_error:
            errors.append((0, key_error, ""))
        yield from error_rows(self, artifact, errors, session.session_id, session.cwd)

    @staticmethod
    def _legacy_key(artifact: Artifact, session_id: str) -> tuple[str, str]:
        """(session key, error) for `session_id` from the sibling legacy
        `sessions.json`. A missing file is no error; a file that cannot be
        read, does not decode or is not a JSON object returns the whole-file
        message (`sessions.json unreadable (<reason>)`, `sessions.json
        unparseable (<reason>)`, `sessions.json is not a JSON object`) for a
        `parser:` row of the transcript that looked the key up (issue 177)."""
        store = artifact.disk_path.parent / "sessions.json"
        if store.is_symlink() or not store.is_file():
            return "", ""
        try:
            with open(store, encoding="utf-8", errors="replace") as handle:
                data = json.load(handle)
        except OSError as error:
            return "", "sessions.json unreadable (%s)" % error
        except ValueError as error:
            return "", "sessions.json unparseable (%s)" % error
        if not isinstance(data, dict):
            return "", "sessions.json is not a JSON object"
        for key, entry in data.items():
            if isinstance(entry, dict) and entry.get("sessionId") == session_id:
                return str(key), ""
        return "", ""

    # -- SQLite store -------------------------------------------------------------------
    def _parse_db(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        errors: list = []
        ctx = _Db()
        with open_copy(artifact.disk_path) as con:
            tables = table_names(con)
            if "transcript_events" not in tables and "openclaw_engine_anchor" in tables:
                yield from error_rows(self, artifact, [self._anchor_error(con, "agent")])
                return
            windows: dict[str, dict] = {}
            if "session_windows" in tables:
                for window in con.execute("select rowid as _rowid, * from session_windows"):
                    window = dict(window)
                    windows[str(window.get("session_id"))] = window
            relayed = self._db_relays(con, tables, windows, ctx)
            nodes = self._db_nodes(con, errors) if "session_nodes" in tables else []
            self._attach_nodes(nodes, relayed, ctx)
            if "transcript_events" in tables:
                yield from self._db_events(artifact, con, windows, ctx, opts)
            if "session_transcript_archives" in tables:
                yield from self._db_archives(artifact, con, windows, ctx, opts)
            if "session_transcript_cold_archives" in tables:
                yield from self._db_cold(artifact, con, windows, ctx, opts)
            if "session_pending_inputs" in tables:
                yield from self._db_pending(artifact, con, ctx, errors)
            if "session_transcript_fts_content" in tables:
                yield from self._db_fts(artifact, con, ctx)
            if "conversation_deliveries" in tables and "conversations" in tables:
                current = {
                    str(node["session_key"]): str(node["current_session_id"]) for node in nodes
                }
                yield from self._db_deliveries(artifact, con, ctx, current)
            if "memory_session_tombstones" in tables:
                yield from self._db_tombstones(artifact, con, ctx)
        # Rows attached to a generation with no transcript rows in the database.
        for sid, items in list(ctx.attached.items()):
            session = _Session(sid)
            session.cwd = ctx.cwds.get(sid, "")
            for line, timestamp, text, model in items:
                yield self._row(artifact, session, line, timestamp, "system", text, opts, model)
        yield from error_rows(self, artifact, errors)

    @staticmethod
    def _anchor_error(con, label: str) -> tuple[int, str, str]:
        """The whole-file error of a PostgreSQL engine anchor: the
        `openclaw_engine_anchor (store_id, engine, schema)` table that
        replaces the store when `database.engine` is `postgres`
        (`src/infra/database-engine/open.ts:149`)."""
        try:
            row = con.execute("select store_id, schema from openclaw_engine_anchor").fetchone()
        except sqlite3.DatabaseError:
            row = None
        store, schema = (row["store_id"], row["schema"]) if row is not None else ("-", "-")
        where = "transcripts are" if label == "agent" else "the Gateway state is"
        return (
            0,
            "%s database is a PostgreSQL anchor (store %s, schema %s): %s on the"
            " database server" % (label, store, schema, where),
            "",
        )

    @staticmethod
    def _db_nodes(con, errors: list) -> list[dict]:
        """The `session_nodes` rows with `entry_json` decoded into `entry`;
        an `entry_json` that does not decode is appended to `errors`."""
        nodes: list[dict] = []
        for row in con.execute(
            "select rowid as _rowid, session_key, current_session_id, entry_json, updated_at"
            " from session_nodes order by rowid"
        ):
            row = dict(row)
            raw = row["entry_json"] if isinstance(row["entry_json"], str) else ""
            try:
                entry = json.loads(raw)
            except ValueError as error:
                errors.append(
                    (row["_rowid"], "session_nodes entry_json unparseable (%s)" % error, raw)
                )
                continue
            row["entry"] = entry if isinstance(entry, dict) else {}
            nodes.append(row)
        return nodes

    @staticmethod
    def _attach_nodes(nodes: list[dict], relayed: set, ctx: _Db) -> None:
        """Rows of each session's metadata entry, attached to its current
        generation: the public share (to the generation it publishes), the
        external delivery route when no conversation or window recorded the
        relay, the model override, the per-session permission settings and
        the archive marker."""
        for node in nodes:
            entry, line = node["entry"], node["_rowid"]
            sid = str(node["current_session_id"] or "")
            timestamp = to_utc(node.get("updated_at"))
            grant = entry.get("publicShare")
            if isinstance(grant, dict) and grant.get("id"):
                ctx.attach(
                    str(grant.get("sessionId") or sid),
                    line,
                    to_utc(grant.get("createdAt")),
                    "session synced: public share %s generation %s (from openclaw-agent.sqlite"
                    " session_nodes.entry_json, publicShare.createdAt)"
                    % (grant.get("id") or "-", grant.get("sessionId") or "-"),
                )
            relay = _delivery_relay(entry.get("delivery"))
            if relay and sid not in relayed:
                ctx.attach(sid, line, timestamp, relay)
            override = entry.get("modelOverride")
            if isinstance(override, str) and override:
                ctx.attach(sid, line, timestamp, _override_text(entry), override)
            for key in SESSION_PERMISSION_KEYS:
                value = entry.get(key)
                if value in (None, "", {}, []):
                    continue
                ctx.attach(
                    sid,
                    line,
                    timestamp,
                    "permission setting: %s=%s (from openclaw-agent.sqlite"
                    " session_nodes.entry_json, updated_at)"
                    % (key, value if isinstance(value, str) else compact_json(value)),
                )
            if entry.get("archivedAt") is not None:
                archived_by = entry.get("archivedBy")
                archived_by = archived_by if isinstance(archived_by, dict) else {}
                actor = (
                    ":".join(str(archived_by[k]) for k in ("type", "id") if archived_by.get(k))
                    or "-"
                )
                ctx.attach(
                    sid,
                    line,
                    to_utc(entry.get("archivedAt")),
                    "session archived: %s by %s (from openclaw-agent.sqlite"
                    " session_nodes.entry_json, archivedAt)"
                    % (entry.get("archiveReason") or "-", actor),
                )

    @staticmethod
    def _db_relays(con, tables: set, windows: dict[str, dict], ctx: _Db) -> set:
        """Attach a `session relayed:` row per platform conversation linked to
        a generation (`session_conversations` joined to `conversations`),
        else one per generation whose window names a platform channel, and
        one per generation a Gmail hook started; returns the generations that
        got one. The Control UI and the internal wake channels are not
        platforms (`_platform`)."""
        relayed: set = set()
        if "session_conversations" in tables and "conversations" in tables:
            for row in con.execute(
                "select l.rowid as _rowid, l.session_id, l.role, l.first_seen_at, c.channel,"
                " c.account_id, c.kind, c.peer_id, c.thread_id from session_conversations l"
                " join conversations c using (conversation_id)"
                " order by l.first_seen_at, l.rowid"
            ):
                if not _platform(row["channel"]):
                    continue
                sid = str(row["session_id"] or "")
                ctx.attach(
                    sid,
                    row["_rowid"],
                    to_utc(row["first_seen_at"]),
                    "session relayed: %s account %s %s peer %s thread %s role %s (from"
                    " openclaw-agent.sqlite session_conversations and conversations,"
                    " first_seen_at)"
                    % (
                        row["channel"],
                        row["account_id"] or "-",
                        row["kind"] or "-",
                        row["peer_id"] or "-",
                        row["thread_id"] or "-",
                        row["role"] or "-",
                    ),
                )
                relayed.add(sid)
        for sid, window in windows.items():
            timestamp = to_utc(window.get("started_at")) or to_utc(window.get("created_at"))
            if sid not in relayed and _platform(window.get("channel")):
                ctx.attach(
                    sid,
                    window["_rowid"],
                    timestamp,
                    "session relayed: %s account %s %s (from openclaw-agent.sqlite"
                    " session_windows, started_at)"
                    % (
                        window["channel"],
                        window.get("account_id") or "-",
                        window.get("chat_type") or "-",
                    ),
                )
                relayed.add(sid)
            if window.get("hook_external_content_source") == "gmail":
                ctx.attach(
                    sid,
                    window["_rowid"],
                    timestamp,
                    "session relayed: gmail hook (from openclaw-agent.sqlite session_windows"
                    " hook_external_content_source, started_at)",
                )
                relayed.add(sid)
        return relayed

    def _ctx_row(
        self,
        artifact: Artifact,
        ctx: _Db,
        sid: str,
        line: int,
        timestamp: str,
        turn_type: str,
        text: str,
    ) -> Row:
        """A row of a table read after the transcripts, with the `cwd` the
        generation's header gave."""
        session = _Session(sid)
        session.cwd = ctx.cwds.get(sid, "")
        return self._row(artifact, session, line, timestamp, turn_type, text, Options())

    def _db_pending(self, artifact: Artifact, con, ctx: _Db, errors: list) -> Iterator[Row]:
        """Prompts in `session_pending_inputs`: one never consumed (`queued`,
        `interrupted` or `cancelled` with `consumed_event_id` NULL) never
        reached the transcript and yields its `user` row and a `pending
        input:` row; a consumed one yields its `user` row, marked recovered,
        only when the transcript entry that consumed it is not in the
        database. A `message_json` that does not decode is appended to
        `errors`."""
        for record in con.execute(
            "select seq, input_id, session_id, run_id, message_json, state, accepted_at,"
            " consumed_event_id from session_pending_inputs order by seq"
        ):
            sid = str(record["session_id"] or "")
            consumed = record["consumed_event_id"]
            if consumed and (sid, str(consumed)) in ctx.ids:
                continue
            raw = record["message_json"] if isinstance(record["message_json"], str) else ""
            try:
                msg = json.loads(raw)
            except ValueError as error:
                errors.append(
                    (
                        record["seq"],
                        "session_pending_inputs message_json unparseable (%s)" % error,
                        raw,
                    )
                )
                continue
            msg = msg if isinstance(msg, dict) else {}
            timestamp = to_utc(record["accepted_at"])
            row = self._ctx_row(
                artifact, ctx, sid, record["seq"], timestamp, "user", text_of(msg.get("content"))
            )
            if consumed:
                row.recovered = "yes"
                yield row
                continue
            yield row
            yield self._ctx_row(
                artifact,
                ctx,
                sid,
                record["seq"],
                timestamp,
                "system",
                "pending input: %s, not consumed by the transcript (input %s run %s; from"
                " openclaw-agent.sqlite session_pending_inputs, accepted_at)"
                % (record["state"] or "-", record["input_id"] or "-", record["run_id"] or "-"),
            )

    def _db_fts(self, artifact: Artifact, con, ctx: _Db) -> Iterator[Row]:
        """Rows of the full-text index `session_transcript_fts`, read from its
        FTS5 content table (`c0` text, `c1` session_id, `c2` message_id,
        `c3` role, `c4` timestamp) as a plain table, for the entries whose
        `(session_id, message_id)` the transcript no longer holds; each is
        marked recovered."""
        have = {
            record[1] for record in con.execute("pragma table_info(session_transcript_fts_content)")
        }
        if not {"id", "c0", "c1", "c2", "c3", "c4"} <= have:
            return
        for record in con.execute(
            "select id, c0, c1, c2, c3, c4 from session_transcript_fts_content order by id"
        ):
            sid, mid = str(record["c1"] or ""), str(record["c2"] or "")
            if mid and (sid, mid) in ctx.ids:
                continue
            role = str(record["c3"] or "")
            text = compact(record["c0"])
            timestamp = to_utc(record["c4"])
            if role in ("user", "assistant"):
                row = self._ctx_row(artifact, ctx, sid, record["id"], timestamp, role, text)
            else:
                label = "%s: %s" % (role or "message", text)
                row = self._ctx_row(artifact, ctx, sid, record["id"], timestamp, "system", label)
            row.recovered = "yes"
            yield row

    def _db_deliveries(
        self, artifact: Artifact, con, ctx: _Db, current: dict[str, str]
    ) -> Iterator[Row]:
        """One `channel delivery:` row per `conversation_deliveries` row, a
        send or turn to a platform conversation, and a `channel delivery
        reply:` row for the platform message that replied to it; the session
        is the current generation of `source_session_key`."""
        for row in con.execute(
            "select d.rowid as _rowid, d.*, c.channel from conversation_deliveries d"
            " join conversations c using (conversation_id) order by d.created_at, d.rowid"
        ):
            sid = current.get(str(row["source_session_key"] or ""), "")
            yield self._ctx_row(
                artifact,
                ctx,
                sid,
                row["_rowid"],
                to_utc(row["created_at"]),
                "system",
                "channel delivery: %s %s channel %s conversation %s platform message %s%s"
                " (from openclaw-agent.sqlite conversation_deliveries, created_at)"
                % (
                    row["operation_kind"] or "-",
                    row["status"] or "-",
                    row["channel"] or "-",
                    row["conversation_id"] or "-",
                    row["platform_message_id"] or "-",
                    " error=%s" % row["rejection_error"] if row["rejection_error"] else "",
                ),
            )
            if row["reply_text"] is not None:
                yield self._ctx_row(
                    artifact,
                    ctx,
                    sid,
                    row["_rowid"],
                    to_utc(row["reply_timestamp"]),
                    "system",
                    "channel delivery reply: %s (reply message %s; from openclaw-agent.sqlite"
                    " conversation_deliveries, reply_timestamp)"
                    % (row["reply_text"], row["reply_message_id"] or "-"),
                )

    def _db_tombstones(self, artifact: Artifact, con, ctx: _Db) -> Iterator[Row]:
        """One row per session `openclaw memory forget` removed from the
        memory index (`memory_session_tombstones`)."""
        for row in con.execute(
            "select rowid as _rowid, session_id, agent_id, reason, created_at"
            " from memory_session_tombstones order by created_at, rowid"
        ):
            sid = str(row["session_id"] or "")
            yield self._ctx_row(
                artifact,
                ctx,
                sid,
                row["_rowid"],
                to_utc(row["created_at"]),
                "system",
                "session forgotten from memory: %s agent %s reason=%s (from"
                " openclaw-agent.sqlite memory_session_tombstones, created_at)"
                % (sid or "-", row["agent_id"] or "-", row["reason"] or "-"),
            )

    # -- state/openclaw.sqlite ----------------------------------------------------------
    def _parse_state_db(self, artifact: Artifact) -> Iterator[Row]:
        """Rows from `state/openclaw.sqlite`: `backup uploaded:` from
        `backup_runs`, the permission rows of `operator_approvals`,
        `exec_approvals_config`, `operator_approval_standing_grants` and
        `channel_pairing_allow_entries`, `channel ingress:` from
        `channel_ingress_events`, `source host:` from the GitHub
        publication tables, and `git remote:` from `projects`."""
        if not is_sqlite(artifact.disk_path):
            yield from error_rows(
                self, artifact, [(0, "state/openclaw.sqlite is not a SQLite database", "")]
            )
            return
        data: dict[str, list[dict]] = {}
        try:
            with open_copy(artifact.disk_path) as con:
                tables = table_names(con)
                if "backup_runs" not in tables and "openclaw_engine_anchor" in tables:
                    yield from error_rows(self, artifact, [self._anchor_error(con, "state")])
                    return
                for table, query in STATE_QUERIES:
                    if table in tables:
                        data[table] = [dict(record) for record in con.execute(query)]
        except sqlite3.DatabaseError as error:
            yield from error_rows(
                self, artifact, [(0, "state/openclaw.sqlite unreadable (%s)" % error, "")]
            )
            return
        errors: list = []
        yield from self._backup_rows(artifact, data.get("backup_runs", []), errors)
        for record in data.get("operator_approvals", []):
            yield self._approval_row(artifact, record)
        for record in data.get("exec_approvals_config", []):
            yield from self._exec_config_rows(artifact, record, errors)
        for record in data.get("operator_approval_standing_grants", []):
            yield self._state_row(
                artifact, record["_rowid"], to_utc(record["created_at_ms"]), _grant_text(record)
            )
        for record in data.get("channel_pairing_allow_entries", []):
            yield self._state_row(
                artifact,
                record["_rowid"],
                to_utc(record["updated_at"]),
                "permission setting: channel %s account %s allowFrom=%s (from"
                " state/openclaw.sqlite channel_pairing_allow_entries, updated_at)"
                % (record["channel_key"] or "-", record["account_id"] or "-", record["entry"]),
            )
        for record in data.get("channel_ingress_events", []):
            yield self._state_row(
                artifact,
                record["_rowid"],
                to_utc(record["received_at"]),
                "channel ingress: %s account %s status %s: %s (from state/openclaw.sqlite"
                " channel_ingress_events, received_at)"
                % (
                    record["channel_id"] or "-",
                    record["account_id"] or "-",
                    record["status"] or "-",
                    record["payload_json"],
                ),
            )
        for table in GITHUB_PUBLICATION_TABLES:
            for record in data.get(table, []):
                yield self._state_row(
                    artifact,
                    record["_rowid"],
                    to_utc(record["created_at_ms"]),
                    _publication_text(table, record),
                    str(record["session_id"] or ""),
                )
        for record in data.get("projects", []):
            origin = compact(record["origin_url"])
            if origin:
                row = self._state_row(
                    artifact,
                    record["_rowid"],
                    to_utc(record["created_at_ms"]),
                    GIT_REMOTE_PREFIX + origin,
                )
                row.project_path = str(record["repo_root"] or "")
                yield row
        yield from error_rows(self, artifact, errors)

    def _state_row(
        self, artifact: Artifact, line: int, timestamp: str, text: str, session_id: str = ""
    ) -> Row:
        row = self.base_row(artifact)
        row.source_line = line
        row.timestamp_utc = timestamp
        row.turn_type = "system"
        row.session_id = session_id
        row.text = compact(text)
        return row

    def _backup_rows(self, artifact: Artifact, runs: list[dict], errors: list) -> Iterator[Row]:
        for run in runs:
            raw = run["manifest_json"] if isinstance(run.get("manifest_json"), str) else ""
            try:
                manifest = json.loads(raw)
            except ValueError as error:
                errors.append(
                    (run["_rowid"], "backup_runs manifest_json unparseable (%s)" % error, raw)
                )
                continue
            text = self._backup_text(run, manifest if isinstance(manifest, dict) else {})
            if text:
                yield self._state_row(artifact, run["_rowid"], to_utc(run.get("created_at")), text)

    def _approval_row(self, artifact: Artifact, record: dict) -> Row:
        """The `permission decision:` row of one `operator_approvals` row, at
        `resolved_at_ms` (`created_at_ms` while pending), joined to the call
        it governed on `source_session_id` and `source_tool_call_id`."""
        field = "resolved_at_ms" if record.get("resolved_at_ms") is not None else "created_at_ms"
        row = self._state_row(
            artifact,
            record["_rowid"],
            to_utc(record.get(field)),
            "permission decision: %s status=%s kind=%s resolver=%s reason=%s approval %s"
            " (from state/openclaw.sqlite operator_approvals, %s)"
            % (
                record.get("decision") or record.get("status") or "-",
                record.get("status") or "-",
                record.get("kind") or "-",
                record.get("resolver_kind") or "-",
                record.get("terminal_reason") or "-",
                record.get("approval_id") or "-",
                field,
            ),
            str(record.get("source_session_id") or ""),
        )
        row.tool_name = str(record.get("source_tool_name") or "")
        row.tool_use_id = str(record.get("source_tool_call_id") or "")
        return row

    def _exec_config_rows(self, artifact: Artifact, row: dict, errors: list) -> Iterator[Row]:
        """One `permission setting:` row per default and per-agent policy
        field, allowlist entry and MCP tool grant of `raw_json`, the
        migrated `exec-approvals.json`. `socket` holds the approvals
        socket's token and is never read; a `raw_json` that does not decode
        is reported without its text for the same reason."""
        try:
            doc = json.loads(row["raw_json"] if isinstance(row.get("raw_json"), str) else "")
        except ValueError as error:
            errors.append(
                (
                    row["_rowid"],
                    "exec_approvals_config raw_json unparseable (%s; text withheld,"
                    " it holds the approvals socket token)" % error,
                    "",
                )
            )
            return
        doc = doc if isinstance(doc, dict) else {}
        timestamp = to_utc(row.get("updated_at_ms"))
        scopes: list[tuple[str, object]] = [("defaults", doc.get("defaults"))]
        agents = doc.get("agents")
        if isinstance(agents, dict):
            scopes += [
                ("agents.%s" % agent_id, agent_policy) for agent_id, agent_policy in agents.items()
            ]
        for scope, policy in scopes:
            for setting in _policy_settings(policy):
                yield self._state_row(
                    artifact,
                    row["_rowid"],
                    timestamp,
                    "permission setting: %s.%s (from state/openclaw.sqlite"
                    " exec_approvals_config, updated_at_ms)" % (scope, setting),
                )

    @staticmethod
    def _backup_text(run: dict, manifest: dict) -> str:
        """The `backup uploaded:` text of a successful upload or Git backup;
        `""` for a failed run, a local archive or a Git push that failed."""
        if run.get("status") != "ok":
            return ""
        location = manifest.get("location")
        location = location if isinstance(location, dict) else {}
        target = manifest.get("target")
        pushed = manifest.get("kind") == "git" and target and manifest.get("pushFailed") is not True
        if not location and not pushed:
            return ""
        return (
            "backup uploaded: %s to %s key %s namespace %s"
            " (from state/openclaw.sqlite backup_runs, created_at)"
            % (
                manifest.get("kind") or "-",
                location.get("name") or run.get("archive_path") or "-",
                location.get("key") or target or "-",
                location.get("namespace") or manifest.get("namespace") or "-",
            )
        )

    @staticmethod
    def _window_session(
        session_id: str,
        windows: dict[str, dict],
        ctx: _Db,
        key: str = "",
        extra: str = "",
    ) -> _Session:
        window = windows.get(session_id) or {}
        parts: list[str] = []
        for col in (
            "channel",
            "account_id",
            "chat_type",
            "reason",
            "previous_session_id",
            "parent_session_key",
            "spawned_by",
            "display_name",
        ):
            if window.get(col) not in (None, ""):
                parts.append("%s=%s" % (col, window[col]))
        if extra:
            parts.append(extra)
        if window.get("model_provider"):
            parts.append("model_provider=%s" % window["model_provider"])
        session = _Session(
            session_id,
            key or str(window.get("session_key") or ""),
            " ".join(parts),
            str(window.get("model") or ""),
            str(window.get("model_provider") or ""),
        )
        session.ctx = ctx
        return session

    def _db_events(
        self, artifact: Artifact, con, windows: dict[str, dict], ctx: _Db, opts: Options
    ) -> Iterator[Row]:
        session: _Session | None = None
        for row in con.execute(
            "select rowid as _rowid, session_id, seq, event_json, event_zstd, created_at "
            "from transcript_events order by session_id, seq"
        ):
            row = dict(row)
            sid = str(row.get("session_id") or "")
            if session is None or session.session_id != sid:
                session = self._window_session(sid, windows, ctx)
            line = row["_rowid"]
            raw = row.get("event_json")
            if raw is None and row.get("event_zstd") is not None:
                data, err = _maybe_zstd(row["event_zstd"])
                if data is None:
                    if not session.started:
                        yield from self._start(
                            artifact, session, line, to_utc(row.get("created_at")), None, opts
                        )
                    yield self._bad(
                        artifact,
                        session,
                        line,
                        "event seq %s could not be decompressed (%s)" % (row.get("seq"), err),
                        opts,
                        to_utc(row.get("created_at")),
                    )
                    continue
                raw = data.decode("utf-8", errors="replace")
            err = None  # set only when the JSON does not parse
            try:
                rec = json.loads(
                    raw
                    if isinstance(raw, str)
                    else bytes(raw or b"").decode("utf-8", errors="replace")
                )
            except ValueError as error:
                rec = None
                err = str(error)
            if not isinstance(rec, dict):
                if not session.started:
                    yield from self._start(
                        artifact, session, line, to_utc(row.get("created_at")), None, opts
                    )
                yield self._bad(
                    artifact,
                    session,
                    line,
                    "event seq %s unreadable: %s"
                    % (row.get("seq"), err if err is not None else "not a JSON object"),
                    opts,
                    to_utc(row.get("created_at")),
                )
                continue
            yield from self._entry_rows(artifact, session, line, rec, row.get("created_at"), opts)

    def _db_archives(
        self, artifact: Artifact, con, windows: dict[str, dict], ctx: _Db, opts: Options
    ) -> Iterator[Row]:
        for row in con.execute(
            "select rowid as _rowid, session_id, session_key, reason, encoding, archive_name, "
            "created_at, archive_blob from session_transcript_archives "
            "order by created_at"
        ):
            row = dict(row)
            sid = str(row.get("session_id") or "")
            extra = "archive=%s name=%s" % (row.get("reason") or "", row.get("archive_name") or "")
            session = self._window_session(
                sid, windows, ctx, str(row.get("session_key") or ""), extra
            )
            line = row["_rowid"]
            data, err = _maybe_zstd(row.get("archive_blob") or b"")
            if data is None:
                yield self._bad(
                    artifact,
                    session,
                    line,
                    "archive %s could not be decompressed (%s)"
                    % (row.get("archive_name") or sid, err),
                    opts,
                    to_utc(row.get("created_at")),
                )
            else:
                errors: list = []
                records = _iter_lines(data, errors)
                yield from self._records(artifact, session, records, opts, fixed_line=line)
                label = "archive %s" % (row.get("archive_name") or sid)
                yield from self._blob_errors(artifact, session, line, label, errors)
            if row.get("reason") == "deleted":
                yield self._row(
                    artifact,
                    session,
                    line,
                    to_utc(row.get("created_at")),
                    "system",
                    "session deleted: %s archive %s (from openclaw-agent.sqlite"
                    " session_transcript_archives reason deleted, created_at)"
                    % (sid or "-", row.get("archive_name") or "-"),
                    opts,
                )

    def _db_cold(
        self, artifact: Artifact, con, windows: dict[str, dict], ctx: _Db, opts: Options
    ) -> Iterator[Row]:
        for row in con.execute(
            "select rowid as _rowid, session_id, archive_name, archived_at, archive_blob "
            "from session_transcript_cold_archives where storage = 'sqlite' order by archived_at"
        ):
            row = dict(row)
            sid = str(row.get("session_id") or "")
            session = self._window_session(
                sid, windows, ctx, extra="cold_archive=%s" % (row.get("archive_name") or "")
            )
            line = row["_rowid"]
            data, err = _maybe_zstd(row.get("archive_blob") or b"")
            if data is None:
                yield self._bad(
                    artifact,
                    session,
                    line,
                    "cold archive %s could not be decompressed (%s)"
                    % (row.get("archive_name") or sid, err),
                    opts,
                    to_utc(row.get("archived_at")),
                )
                continue
            errors: list = []
            yield from self._records(
                artifact, session, _iter_lines(data, errors), opts, fixed_line=line
            )
            label = "cold archive %s" % (row.get("archive_name") or sid)
            yield from self._blob_errors(artifact, session, line, label, errors)


__all__ = ["OpenClawParser", "tool_args_text"]
