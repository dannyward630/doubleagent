"""Output schema. `timeline.jsonl` and `sessions.jsonl` are interfaces that
analysts build on; add fields at the end, never rename or remove them
without a note in docs/output.md."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields

TIMELINE_COLUMNS = [
    "timestamp_utc",
    "host",
    "user",
    "agent",
    "session_id",
    "project_path",
    "git_branch",
    "turn_type",
    "model",
    "tool_name",
    "tool_use_id",
    "text",
    "source_file",
    "source_line",
    "recovered",
]

TURN_TYPES = ("user", "assistant", "tool_use", "tool_result", "system", "thinking")

SESSION_COLUMNS = [
    "host",
    "user",
    "agent",
    "session_id",
    "project_path",
    "first_timestamp_utc",
    "last_timestamp_utc",
    "models",
    "user_turns",
    "assistant_turns",
    "tool_calls",
    "source_file",
    "synced",
    "relayed",
    "origin",
    "recovered",
]

# The text that starts a parser's row for a session synced to a remote
# account (`Parser.records_sync`, issue 151).
SYNCED_PREFIX = "session synced:"
# The text that starts a parser's row for a session carried through a
# messaging platform (`Parser.records_relay`, issue 153).
RELAYED_PREFIX = "session relayed:"
# The text that starts a parser's row for a session that began on the
# vendor's servers (`Parser.records_origin`, issue 153).
ORIGIN_PREFIX = "session origin: remote"
# The text that starts a parser's row naming a scratch directory, a
# working directory that belongs to the agent rather than to the user
# (issue 149); inventory.json lists the row's `project_path` under
# `scratch_directories` instead of `projects`.
SCRATCH_PREFIX = "scratch directory:"
# The text that starts a parser's row naming a git remote URL the agent
# recorded for the session's repository (issue 253); the URL follows the
# prefix as recorded, and inventory.json lists it under the project's
# `recorded_remotes`.
GIT_REMOTE_PREFIX = "git remote: "


@dataclass
class Row:
    timestamp_utc: str = ""
    host: str = ""
    user: str = ""
    agent: str = ""
    session_id: str = ""
    project_path: str = ""
    git_branch: str = ""
    turn_type: str = ""
    model: str = ""
    tool_name: str = ""
    tool_use_id: str = ""
    text: str = ""
    source_file: str = ""
    source_line: int = 0
    # "yes" for a row of a secondary source that survived deduplication, so
    # the primary store does not hold the event (set by `dedup.deduplicate`,
    # or by a parser that pairs both copies within one file, as `opencode`
    # does for the 1.x tables of a 2.0 database).
    recovered: str = ""

    def as_dict(self) -> dict[str, object]:
        return {column: getattr(self, column) for column in TIMELINE_COLUMNS}


assert [row_field.name for row_field in fields(Row)] == TIMELINE_COLUMNS


@dataclass
class SessionSummary:
    host: str
    user: str
    agent: str
    session_id: str
    project_path: str = ""
    first_timestamp_utc: str = ""
    last_timestamp_utc: str = ""
    models: dict[str, None] = field(default_factory=dict)
    user_turns: int = 0
    assistant_turns: int = 0
    tool_calls: int = 0
    source_file: str = ""
    # "yes" when a row of the session carries the sync marker, "no" when the
    # agent's parser records sync state and none does, "" when it records
    # none (set by `summarise`).
    synced: str = ""
    # The same for the relay marker: "yes", "no" when the agent's parser
    # records relay state and no row carries the marker, "" otherwise.
    relayed: str = ""
    # "remote" when a row carries the origin marker, "local" when the
    # agent's parser records origin and no row does, "" otherwise.
    origin: str = ""
    # "yes" when every row of the session is `recovered`, "partial" when
    # some are, "no" when none are and the agent's parser reads a secondary
    # source, "" otherwise (set by `summarise`).
    recovered: str = ""
    _sources: dict[str, int] = field(default_factory=dict)
    _rows: int = 0
    _recovered_rows: int = 0
    _scratch_path: str = ""

    def add(self, row: Row) -> None:
        # Only event rows decide `recovered`: a `system` row describes its
        # source or the session, not a turn the primary store could lose.
        if row.turn_type != "system":
            self._rows += 1
            if row.recovered == "yes":
                self._recovered_rows += 1
        # The session's source is the file that contributed most rows, so a
        # transcript wins over the one-line-per-prompt history file.
        if row.source_file:
            self._sources[row.source_file] = self._sources.get(row.source_file, 0) + 1
            self.source_file = max(self._sources, key=self._sources.__getitem__)
        if row.timestamp_utc:
            if not self.first_timestamp_utc or row.timestamp_utc < self.first_timestamp_utc:
                self.first_timestamp_utc = row.timestamp_utc
            if row.timestamp_utc > self.last_timestamp_utc:
                self.last_timestamp_utc = row.timestamp_utc
        if row.model:
            self.models.setdefault(row.model)
        # A `scratch directory:` row names the agent's directory, not the
        # session's project, so it decides `project_path` only when no other
        # row has one (`summarise` applies the fallback).
        if row.turn_type == "system" and row.text.startswith(SCRATCH_PREFIX):
            if not self._scratch_path:
                self._scratch_path = row.project_path
        elif not self.project_path and row.project_path:
            self.project_path = row.project_path
        if row.turn_type == "user":
            self.user_turns += 1
        elif row.turn_type == "assistant":
            self.assistant_turns += 1
        elif row.turn_type == "tool_use":
            self.tool_calls += 1
        elif row.turn_type == "system" and row.text.startswith(SYNCED_PREFIX):
            self.synced = "yes"
        elif row.turn_type == "system" and row.text.startswith(RELAYED_PREFIX):
            self.relayed = "yes"
        elif row.turn_type == "system" and row.text.startswith(ORIGIN_PREFIX):
            self.origin = "remote"

    def as_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "user": self.user,
            "agent": self.agent,
            "session_id": self.session_id,
            "project_path": self.project_path,
            "first_timestamp_utc": self.first_timestamp_utc,
            "last_timestamp_utc": self.last_timestamp_utc,
            "models": list(self.models),
            "user_turns": self.user_turns,
            "assistant_turns": self.assistant_turns,
            "tool_calls": self.tool_calls,
            "source_file": self.source_file,
            "synced": self.synced,
            "relayed": self.relayed,
            "origin": self.origin,
            "recovered": self.recovered,
        }


def summarise(
    rows: list[Row],
    sync_agents: frozenset[str] = frozenset(),
    relay_agents: frozenset[str] = frozenset(),
    origin_agents: frozenset[str] = frozenset(),
    secondary_agents: frozenset[str] = frozenset(),
) -> list[SessionSummary]:
    """One summary per (host, user, agent, session id) of `rows`, sorted by
    first timestamp, agent and session id. `sync_agents` names the agents
    whose parser records sync state (`Parser.records_sync`); their sessions
    without the marker get `synced` "no", the others keep "". `relay_agents`
    does the same for `relayed` (`Parser.records_relay`), and
    `origin_agents` sets `origin` "local" (`Parser.records_origin`).
    `recovered` is "yes" when every row of the session is recovered,
    "partial" when some are, else "no" for an agent of `secondary_agents`
    (`Parser.has_secondary`) and "" for the others; `system` rows are left
    out of the count, so a session of only such rows is never "yes"."""
    out: dict[tuple, SessionSummary] = {}
    for row in rows:
        if not row.session_id:
            continue
        key = (row.host, row.user, row.agent, row.session_id)
        summary = out.get(key)
        if summary is None:
            summary = SessionSummary(row.host, row.user, row.agent, row.session_id)
            out[key] = summary
        summary.add(row)
    for summary in out.values():
        if not summary.project_path:
            summary.project_path = summary._scratch_path
        if not summary.synced and summary.agent in sync_agents:
            summary.synced = "no"
        if not summary.relayed and summary.agent in relay_agents:
            summary.relayed = "no"
        if not summary.origin and summary.agent in origin_agents:
            summary.origin = "local"
        if summary._recovered_rows:
            summary.recovered = "yes" if summary._recovered_rows == summary._rows else "partial"
        elif summary.agent in secondary_agents:
            summary.recovered = "no"
    return sorted(
        out.values(),
        key=lambda summary: (summary.first_timestamp_utc, summary.agent, summary.session_id),
    )


def compact(text: object | None) -> str:
    """Event text with leading and trailing whitespace stripped. Inner
    newlines and indentation are kept: JSON escapes them, so each record
    still stays on one line of the JSONL output."""
    if text is None:
        return ""
    value = text if isinstance(text, str) else str(text)
    return value.strip()


# A drive-letter path (`C:\x`, `c:/x`) and the extended-length prefixes
# `\\?\` and `\\?\UNC\` that Windows APIs and some agents put in front.
_DRIVE = re.compile(r"[A-Za-z]:[\\/]")
_EXTENDED = re.compile(r"\\\\\?\\(UNC\\)?", re.IGNORECASE)


def _windows_path(path: str) -> str | None:
    """`path` in the canonical Windows form `canonical_project_path`
    describes, or None when it is not a Windows form."""
    match = _EXTENDED.match(path)
    if match:
        path = ("\\\\" if match.group(1) else "") + path[match.end() :]
    if _DRIVE.match(path):
        parts = [part for part in path[2:].replace("/", "\\").split("\\") if part]
        return path[0].upper() + ":\\" + "\\".join(parts)
    if path.startswith("\\\\"):
        parts = [part for part in path[2:].replace("/", "\\").split("\\") if part]
        if parts:
            return "\\\\" + "\\".join(parts)
    return None


def is_windows_path(path: str) -> bool:
    """Whether `path` is in one of the Windows forms that
    `canonical_project_path` rewrites (a drive letter, UNC or `\\\\?\\`)."""
    return bool(path) and _windows_path(path) is not None


def canonical_project_path(path: str) -> str:
    r"""One spelling for a Windows `project_path`, so a folder that agents
    record as `c:/Users/a/demo`, `C:\Users\a\demo\` and
    `\\?\C:\Users\a\demo` is `C:\Users\a\demo` in every row.

    A Windows form is a path that starts with a drive letter, a colon and a
    separator, or with two backslashes (UNC, `\\server\share`), after the
    extended-length prefix `\\?\` is removed (`\\?\UNC\server\share`
    becomes `\\server\share`). Its canonical form has an upper-case drive
    letter, backslash separators, no repeated separators after the drive or
    the UNC prefix and no trailing separator, except in the root `C:\`.
    The case of everything after the drive is kept as recorded, because the
    analyzer cannot know the folder's real casing. Any other path, POSIX
    paths and `//server/share` included, is returned unchanged: a backslash
    is a legal character in a POSIX file name, and `file:` URIs are decoded
    by the parser that reads them."""
    if not path:
        return path
    windows_form = _windows_path(path)
    return path if windows_form is None else windows_form


def project_key(path: str) -> str:
    """The key under which `inventory.json` groups a `project_path`: the
    canonical form from `canonical_project_path`, lower-cased when it is a
    Windows form, because Windows file names are case-insensitive; any
    other path unchanged, compared exactly."""
    windows_form = _windows_path(path) if path else None
    return path if windows_form is None else windows_form.lower()
