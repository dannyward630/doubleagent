"""Parser interface. A parser owns one agent name from the catalog, says which
of that agent's artifacts it reads, and yields timeline rows from each."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass

from ..dedup import TOLERANCE_SECONDS
from ..inputs import Artifact
from ..model import Row
from ..timeutil import to_utc


@dataclass
class Options:
    include_thinking: bool = False


class Parser:
    agent: str = ""
    name: str = ""
    # Other catalog agents whose artifacts this parser is also offered: an
    # extension whose chats are rows of the editor's own state.vscdb, which
    # the catalog attributes to `vscode` or to a fork such as `cursor`, lists
    # those editors here (`vscode_state.EDITOR_AGENTS`).
    reads_agents: tuple[str, ...] = ()
    # True when the agent's format records whether a session is synced to a
    # remote account, and the parser yields a `system` row starting
    # `session synced:` for a synced one (issue 151). `sessions.jsonl` then
    # says `synced` "no" for a session without that row rather than "".
    records_sync: bool = False
    # True when the agent's format records whether a session was carried
    # through a messaging platform (Telegram, WhatsApp, email), and the
    # parser yields a `system` row starting `session relayed:` for such a
    # session (issue 153). `sessions.jsonl` then says `relayed` "no" for a
    # session without that row rather than "".
    records_relay: bool = False
    # True when the agent's format records whether a session began on the
    # vendor's servers and is only listed locally, and the parser yields a
    # `system` row starting `session origin: remote` for such a session
    # (issue 153). `sessions.jsonl` then says `origin` "local" for a session
    # without that row rather than "".
    records_origin: bool = False
    # True when `secondary()` can return True for some artifact, so the agent
    # reads at least one secondary source; `sessions.jsonl` then says
    # `recovered` "no" for a session with no recovered row rather than "".
    # `secondary()` needs an artifact to answer, so this says it per class.
    has_secondary: bool = False

    def wants(self, artifact: Artifact) -> bool:
        raise NotImplementedError

    def parse(self, artifact: Artifact, opts: Options) -> Iterator[Row]:
        raise NotImplementedError

    def secondary(self, artifact: Artifact) -> bool:
        """True when `artifact` is a secondary source of this parser: a
        per-prompt history file, a mirror or a projection of a store the
        parser also reads. Its rows are kept in the timeline unless the
        primary store yields the same event (`dedup.deduplicate`), so a
        session whose primary store is gone is still recovered from it."""
        return False

    def secondary_tolerance(self, artifact: Artifact) -> float:
        """Seconds a secondary row's `timestamp_utc` may differ from the primary
        row's for `dedup.deduplicate` to pair them. The default suits a history
        line written when the prompt was submitted; a parser whose secondary
        source stamps an event later than the primary store does (a transcript
        captured at the end of a turn) returns a wider window and says why in
        its docstring."""
        return TOLERANCE_SECONDS

    def base_row(self, artifact: Artifact) -> Row:
        return Row(
            host=artifact.home.host,
            user=artifact.home.user,
            agent=self.agent,
            source_file=artifact.original,
        )


def iter_jsonl(path, errors: list) -> Iterator[tuple[int, dict]]:
    """Yield (line_number, record) for each JSON object line. A bad line is
    appended to `errors` as (line_number, message, raw_text) and skipped: a
    transcript truncated mid-write by a running agent must not lose its
    earlier turns. A line that decodes to a JSON value other than an object
    (an array, a string, a number, `null`) is a bad line too, with the
    message `unparseable line (not a JSON object)` (issue 228); a parser
    whose format holds such lines reads them itself. `raw_text` is the line
    as read, decoded UTF-8 with `errors="replace"`, less only its trailing
    line terminator, for `error_rows` to report in full (issue 136)."""
    with open(path, "rb") as handle:
        for line_number, raw in enumerate(handle, 1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped.decode("utf-8", errors="replace"))
            except ValueError as error:
                errors.append((line_number, "unparseable line (%s)" % error, line_text(raw)))
                continue
            if not isinstance(record, dict):
                errors.append((line_number, "unparseable line (not a JSON object)", line_text(raw)))
                continue
            yield line_number, record


def line_text(raw: bytes) -> str:
    """A line read in binary mode as error row text: decoded UTF-8 with
    `errors="replace"`, its trailing `\\n` and then `\\r` removed, nothing
    else stripped."""
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if raw.endswith(b"\r"):
        raw = raw[:-1]
    return raw.decode("utf-8", errors="replace")


def tail_text(text: str, start: int) -> str:
    """`s` from `start` to its end as error row text, its trailing `\n` and
    then `\r` removed, nothing else stripped, as `line_text` treats a line:
    the record a JSON array reader failed to decode at `start`, with
    everything after it that was never decoded, since a broken record has
    no boundary of its own."""
    tail = text[start:]
    if tail.endswith("\n"):
        tail = tail[:-1]
    if tail.endswith("\r"):
        tail = tail[:-1]
    return tail


def error_rows(
    parser: Parser, artifact: Artifact, errors: list, session_id: str = "", project_path: str = ""
) -> Iterator[Row]:
    """One `system` row per entry of `errors` (issue 136), in list order,
    with the given `session_id` and `project_path` and `source_line` set to
    the entry's line number (0 when the error has none).

    An entry is (line, message, raw), or the older (line, message) pair,
    read as raw `""`. The message carries the whole label: a JSONL reader
    writes `unparseable line (<reason>)`, a JSON array reader
    `unparseable record <N> (<reason>)`, and a line that decodes but cannot
    be applied names what failed (`mutation not applied (<reason>)`). When
    raw is not empty the row text is `parser: <message>: <raw>`, carrying
    the line or record exactly as the reader stored it: no field is pulled
    out of the broken record, nothing is repaired or shortened, and the
    text is not passed through `compact()`. When raw is empty the error
    concerns the whole file (it could not be read, it is not a JSON array,
    it was cut off after record N) or a record with no text left, and the
    row text is `parser: <message>`."""
    for entry in errors:
        line, message = entry[0], entry[1]
        raw = entry[2] if len(entry) > 2 else ""
        row = parser.base_row(artifact)
        row.session_id = session_id
        row.project_path = project_path
        row.turn_type = "system"
        row.source_line = line if isinstance(line, int) else 0
        if raw:
            row.text = "parser: %s: %s" % (message, raw)
        else:
            row.text = "parser: %s" % message
        yield row


def text_of(content) -> str:
    """Flatten the content field of a chat message: a string, or a list of
    typed blocks whose text lives under `text`."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
                elif block.get("type") == "image":
                    parts.append("[image]")
        return "\n".join(parts)
    if isinstance(content, dict):
        text = content.get("text")
        return text if isinstance(text, str) else json.dumps(content, ensure_ascii=False)
    return str(content)


def compact_json(value) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError):
        text = str(value)
    return text


def file_mtime(artifact: Artifact) -> str:
    """The file's modification time as a timeline timestamp: the manifest's
    pre-copy `mtime` when the collection has a manifest, else the file's
    own. Standing settings rows (`permission setting: ... (from <file>,
    file mtime)`) are timestamped with this."""
    mtime = (artifact.manifest or {}).get("mtime")
    if isinstance(mtime, (int, float)) and not isinstance(mtime, bool) and mtime > 0:
        return to_utc(mtime)
    try:
        return to_utc(artifact.disk_path.lstat().st_mtime)
    except OSError:
        return ""


def setting_value(value) -> str:
    """A setting as row text: a bool as `true`/`false`, a string as it is,
    anything else as compact JSON."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    return compact_json(value)


def track_change(label: str, seen: dict, key, value: str) -> str:
    """The `system` row text for a tracked state (`model`, `permission mode`)
    when `value` is new for `key` (a session or thread id): `<label>: <value>`
    the first time, `<label>: <old> -> <new>` on a change, and `""` when it
    is unchanged or empty. `seen` is the parser's per-file dict."""
    if not value:
        return ""
    old = seen.get(key)
    if old == value:
        return ""
    seen[key] = value
    return "%s: %s -> %s" % (label, old, value) if old else "%s: %s" % (label, value)
