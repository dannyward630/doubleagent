"""Claude Code transcripts.

Validated against a real install (Claude Code 2.1.286 to 2.1.289, October
2026), the shipped 2.1.289 package, 2.1.295 installs on Linux and macOS
(2026-10-11) for the permission decision and the process registry, and a
per-step round of 2.1.309 (native installer, win32-arm64) on Windows 11
arm64 (2026-10-23, issue 256) for the CLI and the VS Code extension, and
a per-step round of 2.1.310 (native installer, linux-arm64) on Ubuntu
26.04 arm64 (2026-10-25/26, issue 256) for the same two surfaces, and a
per-step round of 2.1.310 (native installer, darwin-arm64) on macOS 26.6.2
arm64 (2026-10-26, issue 256) for the CLI, Remote Control, a teleported
cloud session and the VS Code extension; the evidence is in
`research/claude-code.md`. Files:

* `~/.claude/projects/<slug>/<session>.jsonl`: one JSON object per line.
  Records with `type` user, assistant, system or attachment carry `uuid`,
  `parentUuid`, `timestamp` (ISO 8601 Z), `sessionId`, `cwd`, `gitBranch`,
  `version`, `entrypoint` and `isSidechain`; 2.1.309 adds `sessionKind`
  (`bg` in a session-daemon worker's file) and `slug`, which a `system`
  row's detail JSON leaves out with the other envelope keys. On a
  detached head `gitBranch` is the literal `HEAD` (2.1.310 Linux), which
  is passed through as the row's branch.
  `message.content` is a string or a list of blocks typed text, thinking
  (`thinking`, `signature`), redacted_thinking, tool_use (`id`, `name`,
  `input`) or tool_result (`tool_use_id`, `content`, `is_error`); a
  tool_result `content` list holds `text` blocks and `tool_reference`
  blocks (`tool_name`).
  - The surface. `entrypoint` names the program that wrote the line
    (`cli` for the terminal and `claude-vscode` for the VS Code extension
    on 2.1.309; `claude-desktop` for the desktop app's Code tab). The
    first record of a file that carries it becomes a `system` row
    `session surface: <entrypoint>` before that line's other rows, and a
    later different value `session surface: <old> -> <new>`; each file,
    subagent files included, tracks its own. The row takes the line's
    timestamp, else the latest one seen.
  - `user` records: `isMeta`, `origin.kind` (human, task-notification,
    peer, coordinator, auto-continuation), `isCompactSummary` and
    `interruptedMessageId` say who wrote the text; the text markers
    `<task-notification>`, `<command-name>`, `<command-message>`,
    `<local-command-stdout>`, `<local-command-caveat>`, `<system-reminder>`
    and `<fork-boilerplate>` (the task of a forked subagent, after the
    context it inherited) do the same when no field does. Only text the
    person typed becomes a `user` row; the rest is a `system` row labelled
    `task notification:`, `peer message:`, `coordinator message:`,
    `auto-continuation:`, `slash command:`, `command output:`,
    `compaction summary:`, `interrupted:`, `subagent task:` or `context:`.
    The prompt keys `promptSource` and `turnOrigin` (2.1.295) say what
    started the turn; they do not change a row's label. A `user` record
    whose `promptSource` is set and not `typed`, or whose `turnOrigin` is
    set and not `human`, gets one `system` row after its own rows,
    `prompt trigger: promptSource=<promptSource> turnOrigin=<turnOrigin>`
    (`-` for a missing key). Values seen on 2.1.309 and 2.1.310:
    `promptSource` `typed`, `system` (a task notification), `queued` (a
    prompt sent from a Remote Control client such as the phone), `sdk`
    (the VS Code extension; on 2.1.310 macOS also a prompt sent from
    claude.ai to a Remote Control spawn and the cloud prompt of a
    teleported session) and `suggestion_accepted` (a prompt Claude
    suggested and the person accepted; on 2.1.310 Linux the suggestion
    picked in the `/schedule` flow); on 2.1.310 macOS `queued` is also a
    prompt typed while a turn ran, delivered from the queue, and
    `system` also the completion notice of a background shell, delivered
    through the queue (`queue-operation` lines); `turnOrigin` `human`,
    `task_notification` and `scheduled` (a `/loop` firing, after the
    `scheduled_task_fire` record below). A settings error at start
    (2.1.310 macOS: `cleanupPeriodDays` 0) opens a settings-fix flow with
    an injected first prompt (`Help me fix these Claude Code settings
    issues.`) and a shell call the person did not type; its `user` line is
    an ordinary prompt and carries `promptSource` like any other.
    `sandboxed` (on a line that ran a shell call), `turnPosition`,
    `serverClassifierContext` (on the result line of an auto-mode
    classifier decision), `queueSkipAttachments` (2.1.310: on a prompt
    typed while another turn ran), `queueSkipSlashCommands`, `mcpMeta` (on
    an MCP tool's result line), `isVisibleInTranscriptOnly` (2.1.310 macOS,
    beside `isCompactSummary`) and the scheduled-fire keys
    (`scheduledFireId`, `scheduledTaskId`, `wakeupSource`,
    `turnCompanion`, `queuePriority`) are not read.
    `permissionMode` feeds the mode tracker below.
    `permissionDecision` (2.1.295, on a line that carries `tool_result`
    blocks: `decision`, `source`, `reasonType`; 2.1.309 adds `grantScope`
    and `reasonCode`) becomes one `system` row after that line's
    `tool_result` rows, `permission decision: <decision> source=<source>
    reason=<reasonType>` (`-` for a missing key), followed by the object's
    compact JSON when it has other keys, so `grantScope` and `reasonCode`
    are in that JSON; its `tool_use_id` is the line's first `tool_result`
    block's and `tool_name` is empty, as on `tool_result` rows. Values seen
    on 2.1.309: `decision` `accept`, `reject`; `source` `config` (the mode
    or the auto-mode classifier allowed it), `user_temporary` (approved
    once), `user_permanent` (the allow-always answer), `user_reject`;
    `reasonType` `classifier`, `mode`, `other`, and on 2.1.310
    `subcommandResults` with `source` `config` (absent on a user's
    answer); `grantScope` `once` (only on a one-time approval);
    `reasonCode` `other`, `unknown`, `subcommandResults` (a piped command
    approved as a whole), and on 2.1.310 Linux `bashMiss:no-rule-match`
    (a Bash command that matched no allow rule, on a `user_temporary`, a
    `user_permanent` and a `user_reject` decision alike). The same line's
    `toolDenialKind` (`user-rejected`
    on 2.1.309) and `userFeedback` (the reason the person typed) are
    appended as ` toolDenialKind=<kind> userFeedback=<text>` when present.
    A line with `toolDenialKind` and no `permissionDecision` is a denial
    that interrupted the turn: 2.1.310 on macOS (2026-10-26) wrote it for
    `No` at the permission dialog with and without the Tab amendment (`No,
    and tell Claude what to do differently`) and for option 3 of the plan
    dialog (`Tell Claude what to change`), with no `userFeedback`, the
    reason being the next typed prompt. It becomes `permission decision:
    reject (interrupted) toolDenialKind=<kind>`; a line with only
    `userFeedback` gets the row with `-` for the three decision keys. A
    declined plan is a rejected `ExitPlanMode` call and gets the same row.
    On 2.1.310 macOS `source` `config` also comes with `reasonType`
    `classifier` (the auto-mode classifier, with `serverClassifierContext`
    on the line), `subcommandResults` with `reasonCode` `unknown` (a
    read-only shell command allowed in manual mode) and, on the replayed
    turn of a teleported cloud session, `rule` with `ruleSource` `cliArg`,
    which the compact JSON carries.
  - `assistant` records: `message.model` and `requestedModel` (2.1.295);
    `wireIngestContext` (2.1.310, the `cd <dir> &&` prefix record) is not
    read; `wireToolInputs[<tool_use id>]`
    is the input as the model sent it, used for the Bash command because
    the stored `input.command` lacks its `cd <dir> &&` prefix. A record
    with `isApiErrorMessage` or model `<synthetic>` is a local API error
    (`apiErrorStatus`, `error`) and becomes a `system` row `api error:`.
    Empty thinking blocks (the text was not returned, only a `signature`)
    are skipped; `redacted_thinking` is `[redacted]`.
  - `system` records: `subtype` and `content`; `turn_duration` uses
    `durationMs` and `messageCount`; a subtype without `content`
    (`api_error`, `memory_saved`, ...) is shown with the compact JSON of
    its fields other than the envelope. Subtypes seen on 2.1.309:
    `turn_duration`, `away_summary`, `local_command` (`commandRun`),
    `compact_boundary` (`compactMetadata`) and `bridge_status` (`url`,
    read for the sync row below), each a `<subtype>: <content>` row.
    `scheduled_task_fire` (`content`, `cron`, `prompt`, `taskId`; a
    `/loop` firing, which the `CronCreate` and `CronDelete` tool calls,
    ordinary `tool_use` rows, start and stop) is `scheduled task fired:
    <taskId> cron=<cron>` (`-` for a missing key). The 2.1.310 macOS
    `compact_boundary` has `logicalParentUuid` and `compactMetadata`
    (`trigger`, `preTokens`, `postTokens`, `cumulativeDroppedTokens`,
    `durationMs`, `preCompactDiscoveredTools`, `preservedSegment`
    {`headUuid`, `anchorUuid`, `tailUuid`}, `preservedMessages`
    {`allUuids`, `uuids`}), none of which is read. `stop_hook_summary`
    (`hookCount`, `hookErrors`, `hookInfos`, `hookAdditionalContext`,
    `hasOutput`, `preventedContinuation`, `stopReason`, `toolUseID`; on
    a teleported session the cloud environment's own hook command) has no
    `content` and is shown as its detail JSON; `informational` (`Session
    resumed` after a teleport) is `informational: <content>`. 2.1.310 adds
    `pendingBackgroundAgentCount` to the `system` key set; it is shown
    only in the detail JSON of a subtype without `content`.
  - `attachment` records, by `attachment.type`: `queued_command`
    (`prompt`, `origin.kind`) is a `user` row when `origin.kind` is human,
    else a labelled `system` row; `hook_system_message` (`hookName`,
    `content`) is `hook:`; `edited_text_file` (`filename`; the `snippet`
    is not shown) is `edited file:`. `environment` (`snapshot`, and on the
    VS Code extension also `changes`) is read for one key,
    `snapshot.scratchpadDirectory`, the session's scratchpad under the
    temp root (`%LOCALAPPDATA%\\Temp\\claude\\<slug>\\<session>\\scratchpad`
    on Windows): once per session and path a `system` row
    `scratch directory: <path> (session scratchpad, from the environment
    attachment)` whose `project_path` is that path, so inventory.json
    lists it under `scratch_directories` (issue 149). Every other
    attachment type is runtime context (system prompt, tool lists,
    reminders, `remote_session_change` with the session's PR and commit,
    `command_permissions` (`allowedTools`, the tool grant of a command
    such as `/loop`), `task_reminder`, `bash_output_audience_note`,
    `batching_reminder_sent`, `deferred_tools_delta`, whose 2.1.310 form
    adds `needsAuthMcpServers`) and is skipped, and so are
    the attachments a compaction re-injects (2.1.310 Linux):
    `compact_file_reference` (`displayPath`, `filename`),
    `plan_file_reference` (`planContent`, `planFilePath`) and `file`
    (`content`, `displayPath`, `filename`). So are the mode attachments,
    whose 2.1.309 shapes are
    now known (issue 98): `auto_mode` (`autoModeConsentFlow`, `bashFirst`,
    `bashFirstSteer`, `bypass`, `finishExposedWork`, `steerOnly`) is the
    turn's auto-mode configuration, not a decision, and `plan_mode`
    (`isSubAgent`, `planExists`, `planFilePath`, `reminderType`),
    `plan_mode_exit` (`planExists`, `planFilePath`) and `auto_mode_exit`
    (`bashFirst`, `finishExposedWork`, `steerOnly`, read on 2.1.310 macOS)
    mark a mode change that the `permission mode:` rows already show, as
    does `plan_mode_reentry` (`planFilePath`, observed on 2.1.310 Linux).
    On 2.1.310 macOS `auto_mode` came at the first turn of a session in
    auto mode, not only with a shell call.
  - Origin (issue 256, 2.1.310 macOS). A file whose `user` records include
    one with `entrypoint` `sdk-cli` and `promptSource` `sdk` is a session
    started from claude.ai through a Remote Control spawn-mode bridge: its
    first `sdk-cli` record gets `session origin: remote (Remote Control,
    entrypoint sdk-cli)`. A record with `remoteSourced` true is a turn of a
    cloud session replayed by `claude --teleport`: the session's first one
    gets `session origin: remote (teleport, remoteSourced)` and, beside
    it, `session synced: cloud session (teleported: remoteSourced records
    replayed from the vendor's copy)`, since the conversation is held on
    the vendor's servers (`synced` `yes`, like a Remote Control spawn); the cloud
    `session_01...` id sits only inside URL and text values and is not
    extracted, and `entrypoint` stays `cli`. The replayed records come
    first in the file and the local process's own after them, so an
    `environment` attachment on or before the file's last `remoteSourced`
    line is the cloud machine's (`/tmp/claude-0/-home-user-repo/...`),
    replayed with the cloud turn, whatever its `<slug>` directory (the
    cloud and the local checkout may share a path, and a local slug may
    differ by case or after a `relocated` record): it gives `session
    origin: remote (teleport, cloud scratchpad <path>)` instead of a
    `scratch directory:` row, since the path is not on this host. A
    record of the VS Code extension (`entrypoint` `claude-vscode`)
    gives `session origin: local (VS Code extension)` once per session;
    its `promptSource` `sdk` is not a remote mark on its own. So
    `records_origin` is set, and a session without a `session origin:
    remote` row reads `origin` `local`. Each row comes before the record's
    other rows, after the surface row.
  - Session-state records carry no `timestamp`, `cwd` or `gitBranch`; their
    rows take the latest timestamp, cwd and branch seen in the file (the
    first ones when none has been seen yet). `ai-title` (`aiTitle`),
    `custom-title` (`customTitle`) and `agent-name` (`agentName`) become
    `session title:` once per distinct value per session; `relocated`
    (`relocatedCwd`) becomes `cwd changed:` and sets `project_path` for
    every later row of the file; `pr-link` (`prUrl`, `prNumber`) is re-
    appended on every metadata flush and is emitted once per session and
    URL (the first record wins); `queue-operation` (`operation`, `content`,
    `timestamp`; the VS Code extension's lines have no `content` on
    2.1.310 and give `queue <operation>:` with nothing after it) is
    `queue <operation>: <content>`, except an `enqueue`
    whose `content` a `queued_command` attachment or a `user` record of the
    same file delivers: the prompt text stays on that record's row, and the
    enqueue keeps the time it was typed as `prompt queued: delivered at
    line N` (the first delivering line after the enqueue, else the first).
    `continued-in` (`continuedInSessionId`, `sessionId`, `timestamp`;
    2.1.309), written in a console session's file when the session daemon
    hands the session to a worker, becomes `session continued in:
    <continuedInSessionId>`, so the console file names the worker's
    session file that holds the later turns. `bridge-session`
    (`bridgeSessionId`, `lastSequenceNum`, `ownerAccountUuid`,
    `ownerOrganizationUuid`, `sessionId`; Remote Control) becomes `remote
    control: bridge session <bridgeSessionId or none> lastSequenceNum=<n>`
    once per change of the two values (`none` is the detach, when
    `bridgeSessionId` is null); the owner UUIDs are identity values and
    are not printed. The first `bridge-session` record of a session that
    names a bridge id also gives `session synced: remote control bridge
    <bridgeSessionId> url <url>`, the URL being the `url` key of the
    `bridge_status` system record that belongs to that bridge: among the
    status records between the previous and the next `bridge-session`
    record of another id (a detach counts), the first at or after the
    line, else the nearest before, else `-`, so a second bridge never
    takes the first one's URL: the bridge puts the session on
    claude.ai, so `records_sync` is set and a session without the row is
    `synced` `no`. The 2.1.310 spawn-mode bridge of macOS wrote no
    `bridge-session` record in its child's file: the child's marks are its
    `sdk-cli` records (Origin above) and `ccr-tip.json` (below). The
    other state types (mode, last-prompt, cost-state, which 2.1.310 also
    writes in a VS Code extension session file, when a Remote Control
    bridge stops and, on macOS, on a resumed session and at the end of a
    file closed by `/clear`, file-history-snapshot, file-history-delta,
    atis-latch, and the
    2.1.309 request-capture lines `api-request`, `api-request-shape` and
    `api-request-blob`, which repeat the prompt inside the request they
    record) are skipped.
  - Compaction. A `/compact` writes a `compact_boundary` system record
    and re-emits the session's `mode`, `permission-mode`, `ai-title`,
    `last-prompt`, `atis-latch` and `file-history-snapshot` records after
    it (2.1.310 Linux), so their counts are not turn counts. The copies
    change no value, so the mode tracker below and the once-per-value
    title rows yield nothing for them.
  - Deletion. A `/clear` starts a new session file in the same process
    and deletes nothing: the old file ends with its `cost-state` line
    (skipped) and the new file's first `user` records are the `/clear`
    command in tag form and its output (2.1.310 macOS), its `slash
    command:` and `command output:` rows (a `system` `local_command`
    record, `commandRun` and `content`, is a `local_command:` row), so no
    deletion row is written. `agent-name` and `cost-state` lines are
    also appended to a session resumed with `--resume` or `--continue`,
    which on 2.1.310 macOS continues the same file under the same
    `sessionId`. The retention sweep deletes
    a transcript older than `cleanupPeriodDays` together with its
    scratchpad directory under the temp root and keeps the session's
    `history.jsonl` line; on 2.1.310 Linux (2026-10-26) it ran on an
    in-session timer 10 to 20 minutes after a session's last prompt
    (about 30 minutes after the start in two of the three runs) and never
    in a session without a prompt. So a session known only from
    `history.jsonl` (`recovered` `yes`) is the expected trace of a swept
    session, and the setting itself is a `retention setting:` row (below).
  - Permission mode and model (issue 93). A `permission-mode` record
    (`permissionMode`, `sessionId`, no `timestamp`) and the `permissionMode`
    key of a `user` record feed one tracker per session id: the first value
    becomes a `system` row `permission mode: <mode>` and each later
    different value `permission mode: <old> -> <new>`, before that line's
    other rows, at the line's timestamp (a `permission-mode` record takes
    the latest one seen). The values the 2.1.296 binary accepts are
    `default`, `acceptEdits`, `plan`, `bypassPermissions`, `dontAsk` and
    `auto`. The first `message.model` of a session's `assistant` records
    (API errors and `<synthetic>` excluded) becomes `model: <id>` and each
    change `model: <old> -> <new>`, followed by ` requested=<requestedModel>`
    when that key is set and differs; the row's `model` column is the new
    model. Re-appended `permission-mode` records with an unchanged value
    yield nothing. Each subagent file tracks its own mode and model. The
    `/model` command's `<local-command-stdout>Set model to ...` line keeps
    its `command output:` row. A subagent can run another model than its
    parent (2.1.310 macOS: `toolUseResult.resolvedModel` on the parent's
    `Agent` result line named the account default after a `/model`
    switch); the subagent file's own `model:` row shows it, and the
    parent's result line yields nothing more. The model alias saved in
    `settings.json` is a `model setting:` row (below).
* `~/.claude/projects/<slug>/<session>/subagents/[<dir>/]agent-<id>.jsonl`:
  subagent transcripts in the same format; `sessionId` is the parent
  session's id and `agentId` the subagent's. Each file starts with a
  `system` row `subagent <agentId> of <sessionId>`, and its first `user`
  record (the parent's task) is `subagent task:`. A forked subagent's file
  starts with a copy of the forking agent's context, whose `uuid`s and tool
  ids match no other file reliably, so those rows are kept; its
  `<fork-boilerplate>` block is the `subagent task:` row.
* `~/.claude/projects/<slug>/<session>/tool-results/<name>.txt`: the full
  output of a tool result too large to keep inline (`<name>` is nine
  base-36 characters on 2.1.309). The tool_result text is then a stub,
  `<persisted-output>` ... `Full output saved to: <path>` ..., and the
  `tool_result` row carries the file's text instead. 2.1.309 also names
  the file in the line's `toolUseResult.persistedOutputPath` (beside
  `persistedOutputSize`, not read); when that key is set and the line has
  one tool_result block, the path is taken from it, else from the stub's
  text. The file is looked up only in the transcript's own session
  directory (the path's directory names must be `<session>/tool-results`)
  and never through a symlink; when it is missing the stub is kept with a
  note.
* `~/.claude/projects/<slug>/<session>/ccr-tip.json` (2.1.310 macOS;
  "ccr" is Claude Code Remote): `{eventId, updatedAt}`, the last
  claude.ai event the local side of a Remote Control session processed,
  written with the session's directory and kept after the bridge stops.
  One `system` row `session synced: remote event <eventId> at <updatedAt>
  (from <path>, file mtime)` at the file's modification time, with
  `session_id` the directory name: the session's copy is on claude.ai.
* `~/.claude/projects/<slug>/bridge-pointer.json` (2.1.310 macOS):
  `{environmentId, pid, procStart, sessionId, source}`, the Remote Control
  environment enabled for the project (`source` `standalone` for `claude
  remote-control`), left behind, naming a dead pid, when the bridge
  stops. One project-level `system` row `remote control: environment
  <environmentId> session <sessionId> source=<source> (from <path>, file
  mtime)` at the file's modification time; `sessionId` is the bridge's
  32-hex id, not a transcript's, so `session_id` is empty, and `pid` and
  `procStart` are not printed.
  Either file that is not a JSON object is one `parser:` row.
* `~/.claude/history.jsonl`: `{display, pastedContents, project, sessionId,
  timestamp}` per prompt, `timestamp` in epoch milliseconds. A secondary
  source: the timeline drops a line whose event the session file also
  records (`dedup.py`), and keeps the rest, since it survives session
  deletion. `pastedContents` (2.1.309: `{"<n>": {contentHash, id, type}}`
  for a long paste, the text itself in `paste-cache/<contentHash>.txt`;
  2.1.310 Linux and macOS: `{"<n>": {content, id, type}}` for a paste
  under the cache threshold of 1,024 characters, the text inline; `<n>` is
  the paste's number within the session) is read to expand the
  `[Pasted text #<n> +<m> lines]` placeholders of `display`: the row is
  `display` with each placeholder replaced by the inline `content`, else
  by the `paste-cache/<contentHash>.txt` file beside the history file
  (never through a symlink), else kept as written, since the retention
  sweep removes the cache. The transcript's `user` line carries the
  pasted text in place of the placeholder, inside a `<pasted_content
  id="<4 hex>">` ... `</pasted_content>` wrapper on 2.1.310, so the
  expanded row is the same event. A slash command is a history line as typed (`/model`,
  `/rename lab-round`) and a tag-form `user` record in the transcript;
  `match_form` gives `dedup.py` the form both match under (a `slash
  command:` or `local_command:` row, `/help` being the latter, as the
  `user` text `/<name>` plus ` <args>` when `<command-args>` is not
  empty; a prompt with the transcript's `<pasted_content id="<4 hex>">`
  ... `</pasted_content>` wrapper removed and each run of ASCII whitespace
  collapsed to one space), and
  `match_tolerance` widens a command line's window to
  `COMMAND_TOLERANCE_SECONDS`, since a command that opens a picker or an
  overlay (`/model`, `/help`, `/install-github-app`) is recorded when it
  completes (2.1.310 macOS, rows 10, 27a and 27b of the round). Three
  history lines have no transcript record to match and stay `recovered`,
  by design: an `/exit` typed while a turn was still running, which
  writes no transcript line; `/logout`, which ends the process before any
  line is written; and `/clear`, whose history line carries the ended
  session's `sessionId` while its command record is the first line of the
  new session's file, so the two never meet within a session. A prompt
  sent through a console attached with `claude agents` is not a history
  line.

* `~/.claude/sessions/<pid>.json`: the per-process registry the CLI keeps
  while it runs (2.1.295 keys observed on Linux and macOS). Read: `pid`,
  `sessionId`, `cwd`, `startedAt` (epoch ms), `kind`, `status`,
  `entrypoint`, `bridgeSessionId`, `hostSessionId`. One `system` row at
  `startedAt`, `claude-code process <pid> <kind> status=<status>
  entrypoint=<entrypoint> bridge=<bridgeSessionId or none>
  host_session=<hostSessionId or none>`. `bridgeSessionId` is patched into
  the file while Remote Control is attached, so its presence means the
  process was under Remote Control when the collector ran, and a file
  that names one also gives `session synced: remote control bridge
  <bridgeSessionId> url - (from <path>, file mtime)` at the file's
  modification time, the marker that is left when the transcript is
  gone, so a registry-only session reads `synced` `yes`; a record can
  outlive a crashed process until the CLI's housekeeping sweep, so pair it
  with the EDR's process list. The `<pid>.<sha256>.key` sibling is a
  secret and is never read: a JSON object `{peerToken, pidDomain,
  procStart}` on Linux (2.1.310, `procStart` the process start tick) and
  on macOS (2.1.310, `pidDomain` `darwin`, 108 bytes) and `{peerToken,
  pidDomain, procStartFt}` on Windows (2.1.309). A Remote Control spawn's
  child (2.1.310 macOS) has `entrypoint` `sdk-cli` and `bridgeSessionId`
  in its file; the `remote-control` parent process writes none. A file
  that is not a JSON object is one `system` row.

* Standing permission settings (issue 93), one `system` row per entry,
  timestamped by the file's modification time (the manifest `mtime` when
  there is one, else the file's own) and saying so in the text,
  `session_id` empty:
  - `~/.claude/settings.json`, `~/.claude/settings.local.json` and a
    project's `.claude/settings.json` and `.claude/settings.local.json`
    (artifacts whose `home.project` is set, the collector's project
    catalog files; `project_path` is the project directory, the manifest
    `home` of the row). Read: `permissions.allow`,
    `permissions.deny`, `permissions.ask` and
    `permissions.additionalDirectories` (one row per entry) and
    `permissions.defaultMode` and `permissions.disableBypassPermissionsMode`
    (one row each), as `permission setting: permissions.<key>=<value>
    (from <path relative to the home or project>, file mtime)`, then the
    top-level `cleanupPeriodDays` as `retention setting:
    cleanupPeriodDays=<n> (from <path>, file mtime)`, because the value
    decides what the retention sweep removes (see Deletion above), then a
    string `model` as `model setting: model=<alias> (from <path>, file
    mtime)`: the model alias (`fable`, `opus`) that `/model` saves as the
    default for new sessions on 2.1.310, which the VS Code extension's
    start also rewrote to its own default with no command (2.1.310 macOS),
    so the row is the file's value at collection, not a session's model.
    No other key is read: `env`, `apiKeyHelper`, hooks and MCP settings
    can carry credentials, and `theme` and `agentPushNotifEnabled`
    (2.1.310, the phone's push-notification opt-in) are not permission,
    retention or model state.
  - `~/.claude.json`: for each `projects.<path>` object, one row per
    `allowedTools` entry and one each for `hasTrustDialogAccepted` and
    `hasClaudeMdExternalIncludesApproved` when present, as
    `permission setting: allowedTools=<entry> (from .claude.json, file
    mtime)`, with `project_path` the `<path>` key, and, when the project
    has `remoteControlSpawnMode` (2.1.310 macOS, `same-dir` or
    `worktree`, saved by `claude remote-control`), `remote control: spawn
    mode <mode> for <path> (from .claude.json, file mtime)`. Then, when
    `githubWebConnectionStatusCache` is an object (`accountUuid`,
    `orgUuid`, `status`; `status` `connected` on 2.1.310 Linux after
    `/install-github-app`; 2.1.309 wrote no such key), one row
    `source host: github status=<status> (from .claude.json, file mtime)`
    (`-` for a missing status) with `project_path` empty; the two UUIDs
    are identity values and are not printed. Then, when set,
    `remoteControlMachineId` (a UUID, written when Remote Control is
    first enabled) as `remote control: machine id set (from .claude.json,
    file mtime)`, the id not printed, and `hasRemoteEnvironment` (written
    when `claude --cloud` creates a cloud session, whose id is only
    printed on the terminal) as `cloud: hasRemoteEnvironment=<value>
    (from .claude.json, file mtime)`, both with `project_path` empty
    (2.1.310 macOS). `githubRepoPaths`
    (repository to local paths, from the git remote) is not read. The
    collector flags this file `secret: true` (it holds the account's
    OAuth details); nothing else in it is read. Backups
    (`.claude.json.backup*`) are not wanted.
  A settings file that is not a JSON object is one `system` row.

The same files under a config home moved with `CLAUDE_CONFIG_DIR` to a
`.claude-<name>` directory in the home (such as `~/.claude-work`) are read
too: `SESSION_RX`, `HISTORY_RX`, `REGISTRY_RX` and `SETTINGS_RX` accept
`.claude` or `.claude-<name>` as the first path component, matching the
catalog's `.claude-*/projects` and `.claude-*/history.jsonl` entries, and
`GLOBAL_CONFIG_RX` accepts `.claude-<name>/.claude.json` (the 2.1.296
binary keeps the global config and the user settings inside
`CLAUDE_CONFIG_DIR` when it is set). The catalog has no
`.claude-*/settings*.json` line (claude-mem's `~/.claude-mem/settings.json`
shares the prefix and holds provider keys), so the collector does not
collect those two files from a moved config home; only the
`permissions` object would be read if one were offered. A config home
anywhere else is not collected.

Not read: the `.meta.json` subagent sidecars (2.1.310 adds `isBuiltIn` to
their keys, and on macOS `launchedWithDefaults`, `requestNonInteractive`
and `requestShape`, `background` for a subagent), the `assistant` keys
`attributionMcpServer` and `attributionMcpTool` of an MCP tool call
(2.1.310 macOS; the tool name `mcp__<server>__<tool>` already names
both), `custom-title.json` beside a
session (2.1.310 macOS, `{customTitle, sessionId}`; the `custom-title`
line holds the same title), the
`sessions/<pid>.*.key` files, `paste-cache/`, `file-history/`, `plans/`,
the session daemon's `daemon/` and `jobs/` trees and the MCP logs of the
CLI cache directory. The `debug/<session>.txt` log that `--debug` writes
(with its `debug/latest` symlink) is not a store the parser reads.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

from ..dedup import MATCH_FORMS, MATCH_TOLERANCES
from ..inputs import Artifact
from ..model import ORIGIN_PREFIX, SCRATCH_PREFIX, SYNCED_PREFIX, Row, compact
from ..timeutil import to_utc
from .base import (
    Options,
    Parser,
    compact_json,
    error_rows,
    file_mtime,
    iter_jsonl,
    setting_value,
    text_of,
)

# The sync row of a teleported cloud session, beside its origin row: the
# vendor holds the conversation the `remoteSourced` records replay.
TELEPORT_SYNCED = (
    SYNCED_PREFIX
    + " cloud session (teleported: remoteSourced records replayed from the vendor's copy)"
)

SESSION_RX = re.compile(r"^\.claude(?:-[^/]+)?/projects/[^/]+/.*\.jsonl$")
SUBAGENT_RX = re.compile(r"/subagents/(?:[^/]+/)*agent-([^/]+)\.jsonl$")
HISTORY_RX = re.compile(r"^\.claude(?:-[^/]+)?/history\.jsonl$")
REGISTRY_RX = re.compile(r"^\.claude(?:-[^/]+)?/sessions/\d+\.json$")
SETTINGS_RX = re.compile(r"^\.claude(?:-[^/]+)?/settings(?:\.local)?\.json$")
GLOBAL_CONFIG_RX = re.compile(r"^(?:\.claude-[^/]+/)?\.claude\.json$")
# Remote Control and cloud sidecars beside the transcripts (2.1.310 macOS,
# research/claude-code.md, Remote Control): `ccr-tip.json` in a session's
# directory, `bridge-pointer.json` in a project's.
CCR_TIP_RX = re.compile(r"^\.claude(?:-[^/]+)?/projects/[^/]+/([^/]+)/ccr-tip\.json$")
BRIDGE_POINTER_RX = re.compile(r"^\.claude(?:-[^/]+)?/projects/[^/]+/bridge-pointer\.json$")
# Settings `permissions` keys read, the lists first (claude 2.1.296 settings
# schema, research/claude-code.md, Other stores).
PERMISSION_LISTS = ("allow", "deny", "ask", "additionalDirectories")
PERMISSION_SCALARS = ("defaultMode", "disableBypassPermissionsMode")
# `.claude.json` `projects.<path>` flags read beside `allowedTools`.
PROJECT_FLAGS = ("hasTrustDialogAccepted", "hasClaudeMdExternalIncludesApproved")
# The settings key that sets the retention sweep's period, and the
# `.claude.json` cache of the GitHub app connection (2.1.310 Linux,
# research/claude-code.md).
RETENTION_KEY = "cleanupPeriodDays"
GITHUB_STATUS_KEY = "githubWebConnectionStatusCache"
# `.claude.json` Remote Control and cloud keys (2.1.310 macOS): the machine
# id (a UUID, never printed), the per-project spawn mode and the flag set
# when a cloud session is created from the CLI.
RC_MACHINE_KEY = "remoteControlMachineId"
RC_SPAWN_KEY = "remoteControlSpawnMode"
CLOUD_ENV_KEY = "hasRemoteEnvironment"
# The settings key that holds the model alias (`fable`, `opus`).
MODEL_KEY = "model"
# A history line's paste placeholder, `[Pasted text #<n> +<m> lines]` or
# `[Pasted text #<n>]`, and the `paste-cache/<contentHash>.txt` name.
PASTE_RX = re.compile(r"\[Pasted text #(\d+)(?: \+\d+ lines)?\]")
PASTE_HASH_RX = re.compile(r"^[0-9A-Za-z]+$")
# The parts of a slash command's tag form in a transcript record.
COMMAND_NAME_RX = re.compile(r"<command-name>(.*?)</command-name>", re.S)
COMMAND_ARGS_RX = re.compile(r"<command-args>(.*?)</command-args>", re.S)
ASCII_SPACE_RX = re.compile(r"[ \t\r\n\f\v]+")
# The wrapper 2.1.310 puts around a paste in the transcript's prompt,
# `<pasted_content id="<4 hex>">` ... `</pasted_content>`.
PASTE_WRAPPER_RX = re.compile(r"</?pasted_content(?:\s[^>]*)?>")
# A history line that is a slash command as typed (`/model`, `/rename x`).
HISTORY_COMMAND_RX = re.compile(r"^/[A-Za-z][A-Za-z0-9:_-]*(?:[ \t]|$)")
# How far a history command line may be from its transcript record: a
# command that opens a picker, an overlay or a flow (`/model`, `/help`,
# `/install-github-app`) is written to the transcript when it completes,
# 27 seconds after the history line for the `/model` of the 2.1.310 macOS
# round (rows 10 and 27a), where a typed prompt is within the default 2.
COMMAND_TOLERANCE_SECONDS = 600.0
PERSISTED_MARK = "<persisted-output>"
PERSISTED_RX = re.compile(r"Full output saved to: ([^\r\n]*?tool-results[/\\][^/\\\r\n]+?\.txt)")

# Which tool_use input field best identifies the action, per tool name.
TOOL_KEYS = {
    "Bash": ("command",),
    "Read": ("file_path",),
    "Write": ("file_path",),
    "Edit": ("file_path",),
    "MultiEdit": ("file_path",),
    "NotebookEdit": ("notebook_path",),
    "Glob": ("pattern", "path"),
    "Grep": ("pattern", "path"),
    "WebFetch": ("url",),
    "WebSearch": ("query",),
    "Agent": ("description", "prompt"),
    "Task": ("description", "prompt"),
    "Skill": ("skill", "args"),
    "LS": ("path",),
}

# Text markers at the start of a user record's text, and the label of the
# system row they become.
TEXT_MARKERS = (
    ("<task-notification>", "task notification"),
    ("<command-name>", "slash command"),
    ("<command-message>", "slash command"),
    ("<local-command-stdout>", "command output"),
    ("<local-command-caveat>", "context"),
    ("<system-reminder>", "context"),
    ("<fork-boilerplate>", "subagent task"),
)
FORK_MARK = "<fork-boilerplate>"

# `origin.kind` values that are not the person, and their labels.
ORIGIN_LABELS = {
    "task-notification": "task notification",
    "peer": "peer message",
    "coordinator": "coordinator message",
    "auto-continuation": "auto-continuation",
}

TITLE_FIELDS = {"ai-title": "aiTitle", "custom-title": "customTitle", "agent-name": "agentName"}

# `promptSource` and `turnOrigin` values of a prompt the person typed; any
# other value gets a `prompt trigger:` row (2.1.309, research/claude-code.md,
# Record schema).
TYPED_SOURCES = ("", "typed")
HUMAN_ORIGINS = ("", "human")

# Envelope fields of a system record, left out of its detail JSON.
SYSTEM_ENVELOPE = frozenset(
    (
        "type",
        "subtype",
        "uuid",
        "parentUuid",
        "logicalParentUuid",
        "timestamp",
        "sessionId",
        "session_id",
        "cwd",
        "gitBranch",
        "version",
        "isSidechain",
        "userType",
        "entrypoint",
        "slug",
        "agentId",
        "isMeta",
        "content",
        "sessionKind",
    )
)

TRANSCRIPT_TYPES = ("user", "assistant", "system", "attachment")

# `user` record keys appended to the `permission decision:` row, in this
# order; `userFeedback` is free text, so it comes last (the research document's Record schema).
DENIAL_KEYS = ("toolDenialKind", "userFeedback")


def tool_summary(name: str, inp) -> str:
    if not isinstance(inp, dict):
        return compact_json(inp)
    keys = TOOL_KEYS.get(name)
    if keys:
        vals = [str(inp[k]) for k in keys if inp.get(k) not in (None, "")]
        if vals:
            return " | ".join(vals)
    for k in ("command", "file_path", "path", "pattern", "url", "query", "description"):
        if inp.get(k) not in (None, ""):
            return str(inp[k])
    return compact_json(inp)


def result_text(content) -> str:
    """A tool_result's text; a `tool_reference` block is its tool name."""
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_reference":
                parts.append(str(b.get("tool_name") or ""))
            else:
                parts.append(text_of([b]))
        return "\n".join(p for p in parts if p)
    return text_of(content)


def marker_label(text: str) -> str:
    head = text.lstrip()
    for mark, label in TEXT_MARKERS:
        if head.startswith(mark):
            return label
    return ""


def session_dir(artifact: Artifact) -> Path:
    """The directory that holds a transcript's sidecars: `<session>/` next to
    a session file, or the directory above `subagents/` for a subagent."""
    p = artifact.disk_path
    if SUBAGENT_RX.search(artifact.rel):
        d = p.parent
        while d.name != "subagents" and d != d.parent:
            d = d.parent
        return d.parent
    return p.with_suffix("")


def persisted_text(artifact: Artifact, stub: str, path: str = "") -> str:
    """The full text of a persisted tool output's file, or the stub with a
    note when the file is not in this session's `tool-results/`. `path` is
    the line's `toolUseResult.persistedOutputPath` (2.1.309); without it the
    path is read from a `<persisted-output>` stub's text."""
    if not path:
        m = PERSISTED_RX.search(stub)
        if not m:
            return stub
        path = m.group(1)
    parts = re.split(r"[/\\]", path)
    name = parts[-1]
    sdir = session_dir(artifact)
    note = "%s\n[persisted output not found: tool-results/%s]" % (stub, name)
    if (
        len(parts) < 3
        or parts[-2] != "tool-results"
        or parts[-3] != sdir.name
        or name in ("", ".", "..")
    ):
        return note
    tdir = sdir / "tool-results"
    f = tdir / name
    try:
        if sdir.is_symlink() or tdir.is_symlink() or f.is_symlink() or not f.is_file():
            return note
        return f.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return note


def match_form(row: Row) -> tuple[str, str]:
    """The `(turn_type, text)` a row is deduplicated under (`dedup.MATCH_FORMS`).
    A `history.jsonl` line records a slash command as typed (`/rename
    lab-round`) and the transcript as a `user` record in tag form
    (`<command-name>/rename</command-name>` ... `<command-args>lab-round
    </command-args>`), which is a `slash command:` row (or a `local_command:`
    row from a `system` record); both match as the `user` text `/<name>
    <args>`, the args and the space before them only when `<command-args>`
    is not empty (`/model` has `<command-args></command-args>`). A
    prompt's text matches with the `<pasted_content id="...">` wrapper the
    transcript puts around a paste removed and each run of ASCII
    whitespace collapsed to one space, since the history line holds the
    bare paste and may join it to the typed text with other whitespace;
    the whitespace itself stays, so `echo a b` and `echo ab` are distinct
    prompts. Every other row matches as it is."""
    text = row.text
    if row.turn_type == "system":
        if text.startswith(("slash command: ", "local_command: ")):
            name = COMMAND_NAME_RX.search(text)
            if name:
                cmd = name.group(1).strip(" \t\r\n")
                if not cmd.startswith("/"):
                    cmd = "/" + cmd
                args = COMMAND_ARGS_RX.search(text)
                if args and args.group(1).strip(" \t\r\n"):
                    cmd += " " + args.group(1).strip(" \t\r\n")
                return "user", _squash(cmd)
        return row.turn_type, text
    if row.turn_type == "user":
        return "user", _squash(PASTE_WRAPPER_RX.sub(" ", text))
    return row.turn_type, text


def _squash(text: str) -> str:
    """`text` with each run of ASCII whitespace collapsed to one space and
    the ends trimmed."""
    return ASCII_SPACE_RX.sub(" ", text).strip(" ")


def match_tolerance(row: Row) -> float | None:
    """The forward time window, in seconds, of a secondary row that is a
    slash command as typed (`COMMAND_TOLERANCE_SECONDS`: how long after the
    line its transcript record may be written), or None for the source's
    own (`dedup.MATCH_TOLERANCES`)."""
    if row.turn_type == "user" and HISTORY_COMMAND_RX.match(row.text):
        return COMMAND_TOLERANCE_SECONDS
    return None


def read_paste(history: Path, content_hash: str) -> tuple[str | None, str]:
    """`(text, problem)` for `paste-cache/<content_hash>.txt` beside
    `history`: the file's text and ""; `(None, "")` when the name is not a
    plain hash, the file is missing, or the directory or file is a symlink,
    which is never followed; and `(None, "<message>")` when a file that is
    there could not be read, since a read failure is evidence, not an
    absent cache entry (issue 136)."""
    if not PASTE_HASH_RX.match(content_hash):
        return None, ""
    cache = history.parent / "paste-cache"
    f = cache / (content_hash + ".txt")
    try:
        if cache.is_symlink() or f.is_symlink() or not f.is_file():
            return None, ""
        return f.read_bytes().decode("utf-8", errors="replace"), ""
    except OSError as e:
        return None, "paste-cache/%s.txt unreadable (%s)" % (content_hash, e)


def expand_pastes(
    history: Path, display: str, pasted, errors: list | None = None, line: int = 0
) -> str:
    """`display` with each `[Pasted text #<n> ...]` placeholder replaced by
    the paste's text: `pastedContents.<n>.content` when the paste is kept
    inline, else `paste-cache/<contentHash>.txt`; a placeholder whose text
    is in neither place is kept as written. A cache file that is there but
    cannot be read keeps the placeholder too and adds `(line, message, "")`
    to `errors`, which `error_rows` turns into a `parser:` row naming it."""
    if not isinstance(pasted, dict) or not pasted:
        return display

    def sub(m: re.Match) -> str:
        entry = pasted.get(m.group(1))
        if not isinstance(entry, dict) or entry.get("type", "text") != "text":
            return m.group(0)
        content = entry.get("content")
        if isinstance(content, str):
            return content
        h = entry.get("contentHash")
        text, problem = read_paste(history, h) if isinstance(h, str) else (None, "")
        if problem and errors is not None:
            errors.append((line, problem, ""))
        return m.group(0) if text is None else text

    return PASTE_RX.sub(sub, display)


class _Prescan:
    """What `_parse_session` needs to know about a whole transcript file
    before its first row: the lines that deliver each queued prompt, whether
    the file is a fork, the first cwd and branch, the `(line, url)` of each
    `bridge_status` record and the `(line, id)` of each `bridge-session`
    record, whether a `user` record of the `sdk-cli` entrypoint has
    `promptSource` `sdk` (a Remote Control spawn), and the line of the
    last record that carries `remoteSourced` (a teleported cloud session;
    0 when none), which ends the replayed block."""

    __slots__ = (
        "branch",
        "bridge_lines",
        "bridge_urls",
        "cwd",
        "delivered",
        "fork",
        "remote_last",
        "sdk_spawn",
    )

    def __init__(self) -> None:
        self.delivered: dict[str, list[int]] = {}
        self.fork = False
        self.cwd = ""
        self.branch = ""
        self.bridge_urls: list[tuple[int, str]] = []
        self.bridge_lines: list[tuple[int, str | None]] = []
        self.sdk_spawn = False
        self.remote_last = 0


class ClaudeCodeParser(Parser):
    agent = "claude-code"
    name = "claude-code"
    has_secondary = True
    # A Remote Control bridge puts the session on claude.ai (issue 256).
    records_sync = True

    def __init__(self) -> None:
        # A Remote Control spawn or a teleported cloud session began on
        # claude.ai (issue 256). Set per instance, so that the
        # claude-desktop subclass, whose origin is not established, keeps
        # `origin` "".
        self.records_origin = self.agent == "claude-code"

    def wants(self, artifact: Artifact) -> bool:
        rel = artifact.rel
        return any(
            rx.match(rel)
            for rx in (
                HISTORY_RX,
                SESSION_RX,
                REGISTRY_RX,
                SETTINGS_RX,
                GLOBAL_CONFIG_RX,
                CCR_TIP_RX,
                BRIDGE_POINTER_RX,
            )
        )

    def secondary(self, artifact: Artifact) -> bool:
        return bool(HISTORY_RX.match(artifact.rel))

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        if HISTORY_RX.match(artifact.rel):
            yield from self._parse_history(artifact, opts)
        elif REGISTRY_RX.match(artifact.rel):
            yield from self._parse_registry(artifact)
        elif SETTINGS_RX.match(artifact.rel):
            yield from self._parse_settings(artifact)
        elif GLOBAL_CONFIG_RX.match(artifact.rel):
            yield from self._parse_global_config(artifact)
        elif CCR_TIP_RX.match(artifact.rel):
            yield from self._parse_ccr_tip(artifact)
        elif BRIDGE_POINTER_RX.match(artifact.rel):
            yield from self._parse_bridge_pointer(artifact)
        else:
            yield from self._parse_session(artifact, opts)

    def _parse_history(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        errors: list = []
        for n, rec in iter_jsonl(artifact.disk_path, errors):
            row = self.base_row(artifact)
            row.source_line = n
            row.timestamp_utc = to_utc(rec.get("timestamp"))
            row.session_id = str(rec.get("sessionId") or "")
            row.project_path = str(rec.get("project") or "")
            row.turn_type = "user"
            display = rec.get("display")
            if isinstance(display, str):
                display = expand_pastes(
                    artifact.disk_path, display, rec.get("pastedContents"), errors, n
                )
            row.text = compact(display)
            yield row
        yield from error_rows(self, artifact, errors)

    def _parse_ccr_tip(self, artifact: Artifact) -> Iterator[Row]:
        """`projects/<slug>/<session>/ccr-tip.json` (`eventId`, `updatedAt`):
        the last claude.ai event the local side of a Remote Control session
        processed, one `session synced:` row at the file's modification
        time."""
        m = CCR_TIP_RX.match(artifact.rel)
        session = m.group(1) if m else ""
        doc, bad = self._settings_doc(artifact, "ccr-tip.json")
        if doc is None:
            if bad is not None:
                bad.session_id = session
                yield bad
            return
        row = self._file_row(artifact)
        row.session_id = session
        row.text = compact(
            "%s remote event %s at %s (from %s, file mtime)"
            % (SYNCED_PREFIX, self._val(doc, "eventId"), self._val(doc, "updatedAt"), artifact.rel)
        )
        yield row

    def _parse_bridge_pointer(self, artifact: Artifact) -> Iterator[Row]:
        """`projects/<slug>/bridge-pointer.json` (`environmentId`, `pid`,
        `procStart`, `sessionId`, `source`): the Remote Control environment
        last enabled for the project, kept after the bridge stops. One
        project-level row at the file's modification time; `sessionId` is
        the bridge's, not a transcript's, so `session_id` stays empty."""
        doc, bad = self._settings_doc(artifact, "bridge-pointer.json")
        if doc is None:
            if bad is not None:
                yield bad
            return
        row = self._file_row(artifact)
        row.text = compact(
            "remote control: environment %s session %s source=%s (from %s, file mtime)"
            % (
                self._val(doc, "environmentId"),
                self._val(doc, "sessionId"),
                self._val(doc, "source"),
                artifact.rel,
            )
        )
        yield row

    @staticmethod
    def _val(doc: dict, key: str) -> str:
        """A JSON value as row text, `-` when missing or empty."""
        v = doc.get(key)
        return "-" if v in (None, "") else setting_value(v)

    def _file_row(self, artifact: Artifact) -> Row:
        """A `system` row at the file's modification time."""
        row = self.base_row(artifact)
        row.source_line = 1
        row.turn_type = "system"
        row.timestamp_utc = file_mtime(artifact)
        return row

    def _parse_registry(self, artifact: Artifact) -> Iterator[Row]:
        row = self.base_row(artifact)
        row.source_line = 1
        row.turn_type = "system"
        try:
            rec = json.loads(artifact.disk_path.read_bytes().decode("utf-8", errors="replace"))
        except (OSError, ValueError):
            rec = None
        if not isinstance(rec, dict):
            row.text = "parser: session registry file is not a JSON object"
            yield row
            return

        def val(key: str, missing: str) -> str:
            v = rec.get(key)
            return missing if v in (None, "") else str(v)

        row.timestamp_utc = to_utc(rec.get("startedAt"))
        row.session_id = val("sessionId", "")
        row.project_path = val("cwd", "")
        row.text = "claude-code process %s %s status=%s entrypoint=%s bridge=%s host_session=%s" % (
            val("pid", artifact.disk_path.stem),
            val("kind", "-"),
            val("status", "-"),
            val("entrypoint", "-"),
            val("bridgeSessionId", "none"),
            val("hostSessionId", "none"),
        )
        yield row
        bridge = rec.get("bridgeSessionId")
        if isinstance(bridge, str) and bridge:
            sync = self.base_row(artifact)
            sync.source_line = 1
            sync.turn_type = "system"
            sync.timestamp_utc = file_mtime(artifact)
            sync.session_id = row.session_id
            sync.project_path = row.project_path
            sync.text = "%s remote control bridge %s url - (from %s, file mtime)" % (
                SYNCED_PREFIX,
                bridge,
                artifact.rel,
            )
            yield sync

    def _standing_row(
        self,
        artifact: Artifact,
        ts: str,
        project: str,
        key: str,
        value,
        label: str = "permission setting",
    ) -> Row:
        row = self.base_row(artifact)
        row.source_line = 1
        row.turn_type = "system"
        row.timestamp_utc = ts
        row.project_path = project
        row.text = compact(
            "%s: %s=%s (from %s, file mtime)" % (label, key, setting_value(value), artifact.rel)
        )
        return row

    def _settings_doc(self, artifact: Artifact, what: str) -> tuple[dict | None, Row | None]:
        """The file as a JSON object, or a `system` row saying it is not one."""
        try:
            doc = json.loads(artifact.disk_path.read_bytes().decode("utf-8", errors="replace"))
        except (OSError, ValueError):
            doc = None
        if isinstance(doc, dict):
            return doc, None
        row = self.base_row(artifact)
        row.source_line = 1
        row.turn_type = "system"
        row.timestamp_utc = file_mtime(artifact)
        row.text = "parser: %s is not a JSON object" % what
        return None, row

    def _parse_settings(self, artifact: Artifact) -> Iterator[Row]:
        doc, bad = self._settings_doc(artifact, "settings file")
        if doc is None:
            if bad is not None:
                yield bad
            return
        ts = file_mtime(artifact)
        project = artifact.home.original if artifact.home.project else ""
        perms = doc.get("permissions")
        if isinstance(perms, dict):
            for key in PERMISSION_LISTS:
                entries = perms.get(key)
                if isinstance(entries, list):
                    for entry in entries:
                        yield self._standing_row(artifact, ts, project, "permissions." + key, entry)
            for key in PERMISSION_SCALARS:
                if perms.get(key) is not None:
                    yield self._standing_row(
                        artifact, ts, project, "permissions." + key, perms[key]
                    )
        if doc.get(RETENTION_KEY) is not None:
            yield self._standing_row(
                artifact, ts, project, RETENTION_KEY, doc[RETENTION_KEY], "retention setting"
            )
        if isinstance(doc.get(MODEL_KEY), str) and doc[MODEL_KEY]:
            yield self._standing_row(
                artifact, ts, project, MODEL_KEY, doc[MODEL_KEY], "model setting"
            )

    def _parse_global_config(self, artifact: Artifact) -> Iterator[Row]:
        doc, bad = self._settings_doc(artifact, ".claude.json")
        if doc is None:
            if bad is not None:
                yield bad
            return
        ts = file_mtime(artifact)
        projects = doc.get("projects")
        for path, proj in projects.items() if isinstance(projects, dict) else ():
            if not isinstance(proj, dict):
                continue
            tools = proj.get("allowedTools")
            if isinstance(tools, list):
                for entry in tools:
                    yield self._standing_row(artifact, ts, str(path), "allowedTools", entry)
            for key in PROJECT_FLAGS:
                if proj.get(key) is not None:
                    yield self._standing_row(artifact, ts, str(path), key, proj[key])
            spawn = proj.get(RC_SPAWN_KEY)
            if spawn not in (None, ""):
                row = self._file_row(artifact)
                row.timestamp_utc = ts
                row.project_path = str(path)
                row.text = compact(
                    "remote control: spawn mode %s for %s (from %s, file mtime)"
                    % (setting_value(spawn), path, artifact.rel)
                )
                yield row
        github = doc.get(GITHUB_STATUS_KEY)
        if isinstance(github, dict):
            # accountUuid and orgUuid are identity values: never printed.
            status = github.get("status")
            row = self.base_row(artifact)
            row.source_line = 1
            row.turn_type = "system"
            row.timestamp_utc = ts
            row.text = compact(
                "source host: github status=%s (from %s, file mtime)"
                % ("-" if status in (None, "") else setting_value(status), artifact.rel)
            )
            yield row
        if doc.get(RC_MACHINE_KEY) not in (None, ""):
            # The machine id is an identity value: never printed.
            row = self._file_row(artifact)
            row.timestamp_utc = ts
            row.text = "remote control: machine id set (from %s, file mtime)" % artifact.rel
            yield row
        if doc.get(CLOUD_ENV_KEY) is not None:
            row = self._file_row(artifact)
            row.timestamp_utc = ts
            row.text = compact(
                "cloud: %s=%s (from %s, file mtime)"
                % (CLOUD_ENV_KEY, setting_value(doc[CLOUD_ENV_KEY]), artifact.rel)
            )
            yield row

    @staticmethod
    def _prescan(artifact: Artifact) -> _Prescan:
        """The lines that deliver each prompt by an attachment or a user
        record (so a queue enqueue can point at them instead of repeating the
        text), whether the file is a fork, the first cwd and branch (for
        state records before any transcript one), the `(line, url)` of
        each `bridge_status` system record (for the sync row of a
        `bridge-session` record, which has no URL of its own), the
        `(line, bridgeSessionId or None)` of each `bridge-session` record,
        which bound the status lines a bridge may take its URL from, and
        the two origin marks (`_Prescan`). The errors are discarded: the
        same file is parsed in full and reported on by `_parse_session`."""
        pre = _Prescan()

        def deliver(text: str, n: int) -> None:
            if text:
                pre.delivered.setdefault(text, []).append(n)

        for n, rec in iter_jsonl(artifact.disk_path, []):
            rtype = rec.get("type")
            if not pre.cwd and rec.get("cwd"):
                pre.cwd = str(rec.get("cwd"))
            if not pre.branch and rec.get("gitBranch"):
                pre.branch = str(rec.get("gitBranch"))
            if rec.get("remoteSourced") is True:
                pre.remote_last = n
            if rtype == "system" and rec.get("subtype") == "bridge_status" and rec.get("url"):
                pre.bridge_urls.append((n, str(rec.get("url"))))
            if rtype == "bridge-session":
                b = rec.get("bridgeSessionId")
                pre.bridge_lines.append((n, b if isinstance(b, str) and b else None))
            if rtype == "attachment":
                att = rec.get("attachment") or {}
                if isinstance(att, dict) and att.get("type") == "queued_command":
                    deliver(text_of(att.get("prompt")), n)
            elif rtype == "user":
                if rec.get("entrypoint") == "sdk-cli" and rec.get("promptSource") == "sdk":
                    pre.sdk_spawn = True
                content = (rec.get("message") or {}).get("content")
                if isinstance(content, str):
                    deliver(content, n)
                elif isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "text":
                            t = str(b.get("text") or "")
                            deliver(t, n)
                            if t.lstrip().startswith(FORK_MARK):
                                pre.fork = True
        return pre

    @staticmethod
    def _origin_text(rec, pre: _Prescan) -> str:
        """The `session origin:` text a record marks, or "": the first
        record of the `sdk-cli` entrypoint in a Remote Control spawn's file,
        a `remoteSourced` record (a teleported cloud turn), or a record of
        the VS Code extension (`claude-vscode`)."""
        entrypoint = rec.get("entrypoint")
        if entrypoint == "sdk-cli" and pre.sdk_spawn:
            return ORIGIN_PREFIX + " (Remote Control, entrypoint sdk-cli)"
        if rec.get("remoteSourced") is True:
            return ORIGIN_PREFIX + " (teleport, remoteSourced)"
        if entrypoint == "claude-vscode":
            return "session origin: local (VS Code extension)"
        return ""

    def _parse_session(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        errors: list = []
        pre = self._prescan(artifact)
        delivered = pre.delivered
        sub = SUBAGENT_RX.search(artifact.rel)
        file_agent_id = sub.group(1) if sub else ""
        header_done = not sub
        task_done = not sub or pre.fork
        session_id = ""
        last_ts = ""
        last_cwd = pre.cwd
        last_branch = pre.branch
        seen_origin: set = set()
        relocated = ""
        seen_pr: set = set()
        seen_title: set = set()
        modes: dict[str, str] = {}
        models: dict[str, str] = {}
        surface = ""
        seen_scratch: set = set()
        bridges: dict[str, tuple] = {}
        seen_sync: set = set()

        for n, rec in iter_jsonl(artifact.disk_path, errors):
            rtype = rec.get("type")
            sid = rec.get("sessionId") or rec.get("session_id")
            if sid:
                session_id = str(sid)
            ts = to_utc(rec.get("timestamp"))
            if ts:
                last_ts = ts
            if rec.get("cwd"):
                last_cwd = str(rec.get("cwd"))
            if rec.get("gitBranch"):
                last_branch = str(rec.get("gitBranch"))

            def base(ts=ts) -> Row:
                row = self.base_row(artifact)
                row.source_line = n
                row.timestamp_utc = ts
                row.session_id = session_id
                row.project_path = relocated or last_cwd
                row.git_branch = last_branch
                return row

            def state_row(text: str) -> Row:
                row = base(ts or last_ts)
                row.turn_type = "system"
                row.text = compact(text)
                return row

            if not header_done and rtype in TRANSCRIPT_TYPES:
                header_done = True
                row = base()
                row.turn_type = "system"
                row.text = "subagent %s of %s" % (
                    rec.get("agentId") or file_agent_id,
                    session_id,
                )
                yield row

            entrypoint = rec.get("entrypoint")
            if isinstance(entrypoint, str) and entrypoint and entrypoint != surface:
                yield state_row(
                    "session surface: %s -> %s" % (surface, entrypoint)
                    if surface
                    else "session surface: " + entrypoint
                )
                surface = entrypoint
            origin = self._origin_text(rec, pre) if rtype in TRANSCRIPT_TYPES else ""
            if origin and (session_id, origin) not in seen_origin:
                seen_origin.add((session_id, origin))
                yield state_row(origin)
                if origin.endswith("(teleport, remoteSourced)"):
                    # The conversation is held on the vendor's servers and
                    # replayed here, so the session is synced as well.
                    yield state_row(TELEPORT_SYNCED)

            mode = rec.get("permissionMode") if rtype in ("user", "permission-mode") else None
            if isinstance(mode, str) and mode and modes.get(session_id) != mode:
                old = modes.get(session_id)
                modes[session_id] = mode
                yield state_row(
                    "permission mode: %s -> %s" % (old, mode) if old else "permission mode: " + mode
                )
            if rtype == "assistant":
                model_row = self._model_row(rec, base, models, session_id)
                if model_row is not None:
                    yield model_row

            if rtype == "user":
                yield from self._user(rec, base, artifact, opts, not task_done)
                task_done = True
            elif rtype == "assistant":
                yield from self._assistant(rec, base, opts)
            elif rtype == "system":
                row = base()
                row.turn_type = "system"
                subtype = str(rec.get("subtype") or "system")
                detail = text_of(rec.get("content"))
                if subtype == "turn_duration":
                    detail = "%s ms, %s messages" % (rec.get("durationMs"), rec.get("messageCount"))
                elif subtype == "scheduled_task_fire":
                    row.text = compact(
                        "scheduled task fired: %s cron=%s"
                        % (self._val(rec, "taskId"), self._val(rec, "cron"))
                    )
                    yield row
                    continue
                elif not detail:
                    rest = {k: v for k, v in rec.items() if k not in SYSTEM_ENVELOPE}
                    detail = compact_json(rest) if rest else ""
                row.text = compact("%s: %s" % (subtype, detail) if detail else subtype)
                yield row
            elif rtype == "attachment":
                row = self._attachment(rec, base)
                if row is not None:
                    yield row
                scratch = self._scratchpad(rec)
                if scratch and (session_id, scratch) not in seen_scratch:
                    seen_scratch.add((session_id, scratch))
                    if n <= pre.remote_last:
                        # A teleport replays the cloud session's records
                        # before the local process writes its own, so this
                        # environment is the cloud machine's: its scratchpad
                        # is not on this host and marks the session's origin.
                        yield state_row(
                            "%s (teleport, cloud scratchpad %s)" % (ORIGIN_PREFIX, scratch)
                        )
                        continue
                    row = state_row(
                        "%s %s (session scratchpad, from the environment attachment)"
                        % (SCRATCH_PREFIX, scratch)
                    )
                    row.project_path = scratch
                    yield row
            elif rtype == "continued-in":
                yield state_row(
                    "session continued in: %s" % (rec.get("continuedInSessionId") or "-")
                )
            elif rtype == "bridge-session":
                yield from self._bridge(
                    rec,
                    n,
                    state_row,
                    session_id,
                    bridges,
                    seen_sync,
                    pre.bridge_urls,
                    pre.bridge_lines,
                )
            elif rtype in TITLE_FIELDS:
                title = str(rec.get(TITLE_FIELDS[rtype]) or "")
                if title and (session_id, title) not in seen_title:
                    seen_title.add((session_id, title))
                    yield state_row("session title: " + title)
            elif rtype == "relocated":
                new_cwd = str(rec.get("relocatedCwd") or "")
                if new_cwd:
                    relocated = new_cwd
                    yield state_row("cwd changed: " + new_cwd)
            elif rtype == "pr-link":
                url = str(rec.get("prUrl") or rec.get("prNumber") or "")
                if (session_id, url) not in seen_pr:
                    seen_pr.add((session_id, url))
                    yield state_row("pr-link: " + url)
            elif rtype == "queue-operation":
                content = text_of(rec.get("content"))
                lines = delivered.get(content) if rec.get("operation") == "enqueue" else None
                if lines:
                    at = next((x for x in lines if x > n), lines[0])
                    yield state_row("prompt queued: delivered at line %d" % at)
                    continue
                yield state_row("queue %s: %s" % (rec.get("operation"), content))
        yield from error_rows(self, artifact, errors, session_id)

    @staticmethod
    def _model_row(rec, base, models: dict, session_id: str) -> Row | None:
        """`model: <id>` at a session's first assistant record and
        `model: <old> -> <new>` when `message.model` changes."""
        msg = rec.get("message")
        model = str(msg.get("model") or "") if isinstance(msg, dict) else ""
        if not model or model == "<synthetic>" or rec.get("isApiErrorMessage"):
            return None
        old = models.get(session_id)
        if old == model:
            return None
        models[session_id] = model
        text = "model: %s -> %s" % (old, model) if old else "model: " + model
        requested = rec.get("requestedModel")
        if requested not in (None, "") and str(requested) != model:
            text += " requested=%s" % requested
        row = base()
        row.turn_type = "system"
        row.model = model
        row.text = compact(text)
        return row

    @staticmethod
    def _bridge(
        rec, n: int, state_row, session_id: str, bridges, seen_sync, urls, lines
    ) -> Iterator[Row]:
        """The rows of a `bridge-session` record: `remote control: bridge
        session ...` when the bridge id or sequence number changes, and the
        `session synced:` row the first time a session names a bridge id,
        with the URL of the `bridge_status` record that belongs to that
        bridge. `urls` are the `(line, url)` of the status records and
        `lines` the `(line, id)` of the `bridge-session` records; the
        status records of this bridge are those between the previous and
        the next `bridge-session` record of another id (a detach counts),
        the first at or after the line is taken, else the nearest before,
        else `-`, so a second bridge never takes the first one's URL."""
        bridge = rec.get("bridgeSessionId")
        seq = rec.get("lastSequenceNum")
        if bridges.get(session_id) != (bridge, seq):
            bridges[session_id] = (bridge, seq)
            yield state_row(
                "remote control: bridge session %s lastSequenceNum=%s"
                % (bridge or "none", "-" if seq in (None, "") else seq)
            )
        if bridge and (session_id, bridge) not in seen_sync:
            seen_sync.add((session_id, bridge))
            start = max((x for x, b in lines if x < n and b != bridge), default=0)
            end = min((x for x, b in lines if x > n and b != bridge), default=None)
            after = [u for x, u in urls if x >= n and (end is None or x < end)]
            before = [u for x, u in urls if start < x < n]
            url = after[0] if after else (before[-1] if before else "-")
            yield state_row("%s remote control bridge %s url %s" % (SYNCED_PREFIX, bridge, url))

    @staticmethod
    def _scratchpad(rec) -> str:
        """An `environment` attachment's `snapshot.scratchpadDirectory`."""
        att = rec.get("attachment")
        if not isinstance(att, dict) or att.get("type") != "environment":
            return ""
        snap = att.get("snapshot")
        path = snap.get("scratchpadDirectory") if isinstance(snap, dict) else None
        return path if isinstance(path, str) else ""

    def _user(self, rec, base, artifact: Artifact, opts: Options, is_task: bool) -> Iterator[Row]:
        yield from self._user_blocks(rec, base, artifact, is_task)
        source = rec.get("promptSource")
        origin = rec.get("turnOrigin")
        source = "" if source is None else str(source)
        origin = "" if origin is None else str(origin)
        if source not in TYPED_SOURCES or origin not in HUMAN_ORIGINS:
            row = base()
            row.turn_type = "system"
            row.text = compact(
                "prompt trigger: promptSource=%s turnOrigin=%s" % (source or "-", origin or "-")
            )
            yield row
        decision = rec.get("permissionDecision")
        denial = any(rec.get(k) not in (None, "") for k in DENIAL_KEYS)
        if decision is not None or denial:
            yield self._permission_row(rec, decision, base)

    @staticmethod
    def _permission_row(rec, decision, base) -> Row:
        """The `system` row of a 2.1.295 `permissionDecision`."""
        row = base()
        row.turn_type = "system"
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, list):
            first = next(
                (b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"),
                None,
            )
            if first is not None:
                row.tool_use_id = str(first.get("tool_use_id") or "")
        denial = "".join(
            " %s=%s" % (k, setting_value(rec[k]))
            for k in DENIAL_KEYS
            if rec.get(k) not in (None, "")
        )
        if decision is None and rec.get("toolDenialKind") not in (None, ""):
            # 2.1.310 macOS: a `No` at the permission dialog (with or
            # without the Tab amendment) and a declined plan interrupt the
            # turn and write no decision record, only the denial kind.
            row.text = compact("permission decision: reject (interrupted)" + denial)
            return row
        if decision is None:
            decision = {}
        if not isinstance(decision, dict):
            row.text = compact("permission decision: " + compact_json(decision) + denial)
            return row

        def val(key: str) -> str:
            v = decision.get(key)
            return "-" if v in (None, "") else str(v)

        text = "permission decision: %s source=%s reason=%s" % (
            val("decision"),
            val("source"),
            val("reasonType"),
        )
        if set(decision) - {"decision", "source", "reasonType"}:
            text += " " + compact_json(decision)
        row.text = compact(text + denial)
        return row

    def _user_blocks(self, rec, base, artifact: Artifact, is_task: bool) -> Iterator[Row]:
        content = (rec.get("message") or {}).get("content")
        origin = rec.get("origin") or {}
        kind = origin.get("kind") if isinstance(origin, dict) else None
        if rec.get("isCompactSummary"):
            record_label = "compaction summary"
        elif is_task:
            record_label = "subagent task"
        elif rec.get("interruptedMessageId"):
            record_label = "interrupted"
        else:
            record_label = ""

        def text_row(text: str) -> Row:
            label = (
                record_label
                or marker_label(text)
                or ORIGIN_LABELS.get(str(kind), "")
                or ("context" if rec.get("isMeta") else "")
            )
            row = base()
            if label:
                row.turn_type = "system"
                text = "%s: %s" % (label, text)
            else:
                row.turn_type = "user"
            row.text = compact(text)
            return row

        if not isinstance(content, list):
            yield text_row(text_of(content))
            return
        # 2.1.309 names the persisted output's file in `toolUseResult`; the
        # key belongs to the line's one tool call, so it is used only when
        # the line has one tool_result block.
        tur = rec.get("toolUseResult")
        saved = tur.get("persistedOutputPath") if isinstance(tur, dict) else None
        results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
        if not isinstance(saved, str) or len(results) != 1:
            saved = ""
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "tool_result":
                row = base()
                row.turn_type = "tool_result"
                row.tool_use_id = str(block.get("tool_use_id") or "")
                text = result_text(block.get("content"))
                if saved:
                    text = persisted_text(artifact, text, saved)
                elif text.lstrip().startswith(PERSISTED_MARK):
                    text = persisted_text(artifact, text)
                if block.get("is_error"):
                    text = "[error] " + text
                row.text = compact(text)
                yield row
            elif btype in ("text", "image"):
                yield text_row(text_of([block]))

    def _assistant(self, rec, base, opts: Options) -> Iterator[Row]:
        msg = rec.get("message") or {}
        model = str(msg.get("model") or "")
        content = msg.get("content")
        if rec.get("isApiErrorMessage") or model == "<synthetic>":
            row = base()
            row.turn_type = "system"
            status = " ".join(
                str(v) for v in (rec.get("apiErrorStatus"), rec.get("error")) if v not in (None, "")
            )
            text = text_of(content)
            row.text = compact(
                "api error: %s" % ": ".join(p for p in (status, text) if p),
            )
            yield row
            return
        wire = rec.get("wireToolInputs")
        blocks = (
            content if isinstance(content, list) else [{"type": "text", "text": text_of(content)}]
        )
        for block in blocks:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "tool_use":
                row = base()
                row.turn_type = "tool_use"
                row.model = model
                row.tool_name = str(block.get("name") or "")
                row.tool_use_id = str(block.get("id") or "")
                inp = block.get("input")
                if row.tool_name == "Bash" and isinstance(wire, dict):
                    sent = wire.get(row.tool_use_id)
                    if isinstance(sent, dict) and sent.get("command"):
                        inp = sent
                row.text = compact(tool_summary(row.tool_name, inp))
                yield row
            elif btype == "text":
                text = block.get("text")
                if not text:
                    continue
                row = base()
                row.turn_type = "assistant"
                row.model = model
                row.text = compact(text)
                yield row
            elif btype in ("thinking", "redacted_thinking") and opts.include_thinking:
                if btype == "thinking":
                    text = block.get("thinking")
                    if not text:
                        continue
                else:
                    text = "[redacted]"
                row = base()
                row.turn_type = "thinking"
                row.model = model
                row.text = compact(text)
                yield row

    @staticmethod
    def _attachment(rec, base) -> Row | None:
        att = rec.get("attachment") or {}
        if not isinstance(att, dict):
            return None
        atype = att.get("type")
        if atype == "queued_command":
            text = text_of(att.get("prompt"))
            origin = att.get("origin") or {}
            kind = origin.get("kind") if isinstance(origin, dict) else None
            row = base()
            if kind == "human" and not att.get("isMeta"):
                label = marker_label(text)
            else:
                label = marker_label(text) or ORIGIN_LABELS.get(str(kind), "") or "queued command"
            if label:
                row.turn_type = "system"
                text = "%s: %s" % (label, text)
            else:
                row.turn_type = "user"
            row.text = compact(text)
            return row
        if atype == "hook_system_message":
            row = base()
            row.turn_type = "system"
            name = str(att.get("hookName") or att.get("hookEvent") or "")
            body = text_of(att.get("content"))
            row.text = compact("hook: %s" % ": ".join(p for p in (name, body) if p))
            return row
        if atype == "edited_text_file":
            row = base()
            row.turn_type = "system"
            row.text = compact("edited file: %s" % (att.get("filename") or ""))
            return row
        return None


# A history line and its transcript record differ in form for slash
# commands and pastes, and a command's record can come long after its
# history line; `dedup.deduplicate` matches them under `match_form` and
# `match_tolerance`.
MATCH_FORMS[ClaudeCodeParser.agent] = match_form
MATCH_TOLERANCES[ClaudeCodeParser.agent] = match_tolerance
