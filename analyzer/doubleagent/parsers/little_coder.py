"""little-coder's own files.

Validated against source, itayinbarr/little-coder at 89d4fa0a (pinning pi
0.83.x, October 2026), with a synthetic fixture; see
`research/little-coder.md`. little-coder is a launcher and extension set for
pi, so its transcripts are pi session files in pi's directory, parsed by
`pi.py` under agent `pi` with a system row naming little-coder. This parser
reads what little-coder writes itself:

* `~/.pi/agent/little-coder-prompt-history.json`: a JSON array of up to
  100 prompt strings, oldest first. No timestamps and no session ids, so
  the `user` rows have neither; `source_line` is the 1-based array index.
  A truncated array still yields the prompts before the cut.
* `~/.little-coder/checkpoints/<session file name>/<path with
  [^A-Za-z0-9._-] replaced by _>`: the pre-edit copy of each file a
  session's first `write`/`edit` touched, or an empty `<name>.absent`
  sentinel when the file did not exist yet. The directory name is the pi
  session file's basename (`<time>_<session id>.jsonl`), or `default` when
  there was no session file. One system row per directory, emitted on its
  alphabetically first file, names the session and the files; its
  timestamp is the earliest file mtime (the first checkpoint, kept by the
  collector's `cp -p`). The session id is taken from the directory name,
  and the project path from the pi session header when that file was
  collected in the same home.

The retired v0.0.x Python releases (read at tag v0.0.5, 424f7a4b) kept
their own state in `~/.little-coder`, which an install that never upgraded
still has. Everything below is source-derived; no real install has shown
it.

* Saved sessions, one JSON object `{session_id (8 hex, made at save
  time), saved_at ("YYYY-MM-DD HH:MM:SS", host local time, no zone),
  messages, turn_count, total_input_tokens, total_output_tokens}`:
  `sessions/daily/<YYYY-MM-DD>/session_<HHMMSS>_<id>.json` (written at
  exit, pruned to the newest few per day) and `sessions/session_<time>_<id>.json`
  or another name (`/save`), both primary; `sessions/mr_sessions/
  session_latest.json` (the exit save again) and `sessions/history.json`
  (`{total_turns, sessions: [...]}`, every exit save, the last 100 to 200
  kept), both secondary, since they repeat the daily copy. `messages` are
  the neutral format: `user` (`content`), `assistant` (`content`,
  `tool_calls[{id, name, input}]`) and `tool` (`tool_call_id`, `name`,
  `content`). No message has a time, a model or a working directory, so
  every row carries the session's `saved_at`, emitted as if it were UTC
  (the host's offset is not recorded), and an empty `project_path`. A
  `session saved:` system row starts each session. A `tool` result whose
  content is `Denied: user rejected this operation` is followed by
  `permission decision: denied (Denied: user rejected this operation)`
  with the call's `tool_name` and `tool_use_id`. In `history.json`
  `source_line` is the session's position in the array; in a session
  file it is the message's position (0 for the `session saved:` row). A
  file cut mid-write still yields the messages before the cut.
* `input_history.txt`: the REPL's readline history, one prompt per line
  as Python's `readline.write_history_file` wrote it, with no time,
  session or project; a secondary source of `user` rows, matched on text
  alone.
* `config.json` (a secret file: it holds `gist_token`, `telegram_token`
  and provider keys, none of which is read): `cloudsave_last_gist_id`
  gives `session synced: gist <id> (from .little-coder/config.json, file
  mtime)`, `telegram_chat_id` gives `session relayed: telegram chat <id>
  (from .little-coder/config.json, file mtime)` and `permission_mode`
  gives `permission setting: permission_mode=<value> (from
  .little-coder/config.json, file mtime)`, each at the file's
  modification time with an empty `session_id`: the gist holds an upload
  with a fresh session id of its own, and the bridge records no session,
  so neither joins a saved session. `records_sync` and `records_relay` are
  set all the same, since the parser writes both kinds of row; with no
  session named, every little-coder session's `synced` and `relayed` read
  `no`.
* `checkpoints/<session id>/snapshots.json`: a JSON array of snapshots
  `{id, session_id, created_at (naive local ISO), turn_count,
  message_index, user_prompt_preview, token_snapshot, file_backups{<path>:
  {backup_filename, version, backup_time}}}`; one system row per snapshot
  at `created_at`, as if UTC. The session id is the REPL's runtime id,
  which matches no saved session file. The copies under `backups/` are not
  read.
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
from .base import Options, Parser, error_rows, file_mtime, line_text, setting_value, text_of
from .cline_legacy import iter_array_at, iter_json_array, read_text
from .pi import args_summary, read_session

HISTORY_REL = ".pi/agent/little-coder-prompt-history.json"
CHECKPOINT_RX = re.compile(r"^\.little-coder/checkpoints/([^/]+)/[^/]+$")
SESSION_FILE_RX = re.compile(r"_([^_/]+)\.jsonl$")

# The v0.0.x Python layout under ~/.little-coder.
LEGACY_SESSION_RX = re.compile(r"^\.little-coder/sessions/(?:[^/]+/)*[^/]+\.json$")
LEGACY_HISTORY_REL = ".little-coder/sessions/history.json"
LEGACY_LATEST_REL = ".little-coder/sessions/mr_sessions/session_latest.json"
LEGACY_INPUT_REL = ".little-coder/input_history.txt"
LEGACY_CONFIG_REL = ".little-coder/config.json"
LEGACY_SNAPSHOTS_RX = re.compile(r"^\.little-coder/checkpoints/([^/]+)/snapshots\.json$")
LEGACY_DENIED = "Denied: user rejected this operation"
SESSIONS_KEY_RX = re.compile(r'"sessions"\s*:\s*')
MESSAGES_KEY_RX = re.compile(r'"messages"\s*:\s*')
SESSION_ID_RX = re.compile(r'"session_id"\s*:\s*"([^"\\]*)"')
SAVED_AT_RX = re.compile(r'"saved_at"\s*:\s*"([^"\\]*)"')


def _regular_files(directory: Path) -> list[os.DirEntry]:
    try:
        return sorted(
            (entry for entry in os.scandir(directory) if entry.is_file(follow_symlinks=False)),
            key=lambda entry: entry.name,
        )
    except OSError:
        return []


def _session_header(home: Path, name: str) -> dict | None:
    sessions = home / ".pi/agent/sessions"
    if sessions.is_symlink() or not sessions.is_dir():
        return None
    for directory in sorted(sessions.iterdir()):
        session_path = directory / name
        if (
            not directory.is_symlink()
            and directory.is_dir()
            and not session_path.is_symlink()
            and session_path.is_file()
        ):
            return read_session(session_path).header or None
    return None


def _dash(value) -> str:
    return "-" if value in (None, "") else setting_value(value)


class LittleCoderParser(Parser):
    agent = "little-coder"
    name = "little-coder"
    has_secondary = True
    records_sync = True
    records_relay = True

    def wants(self, artifact: Artifact) -> bool:
        rel = artifact.rel
        return (
            rel in (HISTORY_REL, LEGACY_INPUT_REL, LEGACY_CONFIG_REL)
            or bool(CHECKPOINT_RX.match(rel))
            or bool(LEGACY_SESSION_RX.match(rel))
        )

    def secondary(self, artifact: Artifact) -> bool:
        return artifact.rel in (LEGACY_HISTORY_REL, LEGACY_LATEST_REL, LEGACY_INPUT_REL)

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        rel = artifact.rel
        if rel == HISTORY_REL:
            yield from self._parse_history(artifact, opts)
        elif rel == LEGACY_INPUT_REL:
            yield from self._parse_input_history(artifact)
        elif rel == LEGACY_CONFIG_REL:
            yield from self._parse_legacy_config(artifact)
        elif rel == LEGACY_HISTORY_REL:
            yield from self._parse_legacy_history(artifact)
        elif LEGACY_SESSION_RX.match(rel):
            yield from self._parse_legacy_session(artifact)
        elif LEGACY_SNAPSHOTS_RX.match(rel) and not SESSION_FILE_RX.search(rel.split("/")[2]):
            yield from self._parse_legacy_snapshots(artifact)
        else:
            yield from self._parse_checkpoints(artifact, opts)

    def _parse_history(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        errors: list = []
        for position, prompt in iter_json_array(artifact.disk_path, errors):
            if not isinstance(prompt, str) or not prompt:
                continue
            row = self.base_row(artifact)
            row.source_line = position
            row.turn_type = "user"
            row.text = compact(prompt)
            yield row
        yield from error_rows(self, artifact, errors)

    def _parse_checkpoints(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        match = CHECKPOINT_RX.match(artifact.rel)
        assert match is not None  # wants() accepted only matching paths
        set_name = match.group(1)
        files = _regular_files(artifact.disk_path.parent)
        if not files or files[0].name != artifact.disk_path.name:
            return  # the set's row comes from its first file
        mtimes: list[float] = []
        names: list[tuple[str, bool]] = []
        for entry in files:
            try:
                mtimes.append(entry.stat(follow_symlinks=False).st_mtime)
            except OSError:
                pass
            absent = entry.name.endswith(".absent")
            names.append((entry.name[: -len(".absent")] if absent else entry.name, absent))
        match = SESSION_FILE_RX.search(set_name)
        row = self.base_row(artifact)
        row.source_line = 0
        row.turn_type = "system"
        row.session_id = match.group(1) if match else ""
        header = _session_header(artifact.home.disk_path, set_name) if match else None
        if header:
            row.session_id = str(header.get("id") or row.session_id)
            row.project_path = str(header.get("cwd") or "")
        row.timestamp_utc = to_utc(min(mtimes)) if mtimes else ""
        listed = "; ".join(
            file_name + (" (did not exist)" if was_absent else "")
            for file_name, was_absent in names
        )
        what = "pi session %s" % set_name if match else "no session file (%s)" % set_name
        row.text = compact(
            "little-coder checkpoints for %s: %d pre-edit file(s)%s: %s"
            % (what, len(names), "" if header else ", session file not collected", listed),
        )
        yield row

    # ---- the v0.0.x Python layout -------------------------------------------

    def _parse_input_history(self, artifact: Artifact) -> Iterator[Row]:
        """`input_history.txt`: one readline entry per line, no time."""
        with open(artifact.disk_path, "rb") as handle:
            for line_number, raw in enumerate(handle, 1):
                text = line_text(raw)
                if not text.strip():
                    continue
                row = self.base_row(artifact)
                row.source_line, row.turn_type, row.text = line_number, "user", compact(text)
                yield row

    def _parse_legacy_config(self, artifact: Artifact) -> Iterator[Row]:
        """`config.json`: the gist id, the Telegram chat id and the permission
        mode, never a token or a key."""
        try:
            document = json.loads(artifact.disk_path.read_bytes().decode("utf-8", errors="replace"))
        except (OSError, ValueError):
            document = None
        timestamp = file_mtime(artifact)
        if not isinstance(document, dict):
            row = self.base_row(artifact)
            row.source_line, row.turn_type, row.timestamp_utc = 1, "system", timestamp
            row.text = "parser: %s is not a JSON object" % artifact.rel
            yield row
            return
        source = "(from %s, file mtime)" % artifact.rel
        texts = []
        if document.get("cloudsave_last_gist_id") not in (None, ""):
            texts.append(
                "session synced: gist %s %s" % (_dash(document["cloudsave_last_gist_id"]), source)
            )
        if document.get("telegram_chat_id") not in (None, "", 0):
            texts.append(
                "session relayed: telegram chat %s %s"
                % (_dash(document["telegram_chat_id"]), source)
            )
        if document.get("permission_mode") not in (None, ""):
            texts.append(
                "permission setting: permission_mode=%s %s"
                % (_dash(document["permission_mode"]), source)
            )
        for text in texts:
            row = self.base_row(artifact)
            row.source_line, row.turn_type, row.timestamp_utc = 1, "system", timestamp
            row.text = compact(text)
            yield row

    def _parse_legacy_history(self, artifact: Artifact) -> Iterator[Row]:
        """`sessions/history.json`: every session saved at exit."""
        errors: list = []
        text = read_text(artifact.disk_path)
        document = None
        if text is not None:
            try:
                document = json.loads(text)
            except ValueError:
                document = None
        if isinstance(document, dict) and isinstance(document.get("sessions"), list):
            sessions = enumerate(document["sessions"], 1)
        elif text is None:
            errors.append((0, "unreadable", ""))
            sessions = iter(())
        else:
            # Cut mid-write: walk the sessions array as far as it parses.
            match = SESSIONS_KEY_RX.search(text)
            if match:
                sessions = iter_array_at(text, match.end(), errors)
            else:
                errors.append((0, "history.json has no sessions array", ""))
                sessions = iter(())
        for position, session in sessions:
            if not isinstance(session, dict):
                continue
            yield from self._legacy_rows(
                artifact,
                session,
                enumerate(session.get("messages") or [], 1),
                str(session.get("session_id") or ""),
                str(session.get("saved_at") or ""),
                position,
            )
        yield from error_rows(self, artifact, errors)

    def _parse_legacy_session(self, artifact: Artifact) -> Iterator[Row]:
        """One saved session file (daily, `/save`, or `session_latest.json`)."""
        errors: list = []
        text = read_text(artifact.disk_path)
        document = None
        if text is not None:
            try:
                document = json.loads(text)
            except ValueError:
                document = None
        if isinstance(document, dict):
            yield from self._legacy_rows(
                artifact,
                document,
                enumerate(document.get("messages") or [], 1),
                str(document.get("session_id") or ""),
                str(document.get("saved_at") or ""),
            )
        elif text is None:
            errors.append((0, "unreadable", ""))
        else:
            # Cut mid-write: the keys before `messages` and the messages
            # array as far as it parses.
            match = MESSAGES_KEY_RX.search(text)
            if match:
                head = text[: match.start()]
                session_id = SESSION_ID_RX.search(head)
                saved = SAVED_AT_RX.search(head)
                yield from self._legacy_rows(
                    artifact,
                    {},
                    iter_array_at(text, match.end(), errors),
                    session_id.group(1) if session_id else "",
                    saved.group(1) if saved else "",
                )
            else:
                errors.append((0, "session file is not a JSON object", ""))
        yield from error_rows(self, artifact, errors)

    def _legacy_rows(
        self,
        artifact: Artifact,
        session: dict,
        messages,
        session_id: str,
        saved_at: str,
        session_position: int = 0,
    ) -> Iterator[Row]:
        """Rows for one v0.0.x session: a `session saved:` row, then each
        message at the session's `saved_at`. `pos` is the session's position
        in `history.json`, 0 for a session file."""
        timestamp = to_utc(saved_at)

        def make_row(
            source_line: int, turn: str, text: str, tool_name: str = "", tool_use_id: str = ""
        ) -> Row:
            row = self.base_row(artifact)
            row.source_line = session_position or source_line
            row.timestamp_utc = timestamp
            row.session_id = session_id
            row.turn_type = turn
            row.tool_name = tool_name
            row.tool_use_id = tool_use_id
            row.text = compact(text)
            return row

        yield make_row(
            0,
            "system",
            "session saved: little-coder v0.0.x session %s turn_count=%s input_tokens=%s "
            "output_tokens=%s (saved_at %s, host local time)"
            % (
                _dash(session_id),
                _dash(session.get("turn_count")),
                _dash(session.get("total_input_tokens")),
                _dash(session.get("total_output_tokens")),
                _dash(saved_at),
            ),
        )
        for position, message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            text = text_of(message.get("content"))
            if role == "user":
                if message.get("images"):
                    text = (text + "\n" if text else "") + "[%d image(s)]" % len(message["images"])
                if text:
                    yield make_row(position, "user", text)
            elif role == "assistant":
                if text:
                    yield make_row(position, "assistant", text)
                calls = message.get("tool_calls")
                for tool_call in calls if isinstance(calls, list) else []:
                    if isinstance(tool_call, dict):
                        yield make_row(
                            position,
                            "tool_use",
                            args_summary(tool_call.get("input")),
                            str(tool_call.get("name") or ""),
                            str(tool_call.get("id") or ""),
                        )
            elif role == "tool":
                name = str(message.get("name") or "")
                call_id = str(message.get("tool_call_id") or "")
                yield make_row(position, "tool_result", text, name, call_id)
                if text == LEGACY_DENIED:
                    yield make_row(
                        position, "system", "permission decision: denied (%s)" % text, name, call_id
                    )

    def _parse_legacy_snapshots(self, artifact: Artifact) -> Iterator[Row]:
        """`checkpoints/<id>/snapshots.json`: one row per snapshot."""
        session_id = artifact.rel.split("/")[2]
        errors: list = []
        for position, snapshot in iter_json_array(artifact.disk_path, errors):
            if not isinstance(snapshot, dict):
                continue
            backups = snapshot.get("file_backups")
            files = []
            for path, backup in (backups if isinstance(backups, dict) else {}).items():
                name = backup.get("backup_filename") if isinstance(backup, dict) else None
                files.append("%s (%s)" % (path, "backup %s" % name if name else "did not exist"))
            row = self.base_row(artifact)
            row.source_line, row.turn_type = position, "system"
            row.timestamp_utc = to_utc(snapshot.get("created_at"))
            row.session_id = str(snapshot.get("session_id") or session_id)
            row.text = compact(
                "little-coder v0.0.x checkpoint %s: turn_count=%s prompt=%s files=%s "
                "(created_at host local time)"
                % (
                    _dash(snapshot.get("id")),
                    _dash(snapshot.get("turn_count")),
                    _dash(snapshot.get("user_prompt_preview")),
                    "; ".join(files) or "-",
                )
            )
            yield row
        yield from error_rows(self, artifact, errors)
