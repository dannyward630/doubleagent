"""The remotes and checked-out branch of a collected project's repository.

The collectors gather a project's `.git/HEAD`, `.git/config`,
`.git/FETCH_HEAD`, `.git/packed-refs`, `.git/refs`, `.git/logs` and
`.git/worktrees` with agent `project` (the project catalog's `project|.git/...`
lines, collector 1.19.0, issue 253). This module reads two of them:

* `.git/config`, git's INI-like configuration: a `[remote "<name>"]` section
  per remote, with `url` (where fetches come from, and pushes when there is
  no `pushurl`) and `pushurl` (where pushes go). Section and key names are
  matched without regard to case, as git does; the subsection (the remote's
  name) is kept as written. The deprecated `[remote.<name>]` form is read
  too. A value may be quoted, may hold `\\`, `\\"`, `\\n`, `\\t` and `\\b`
  escapes, keeps the whitespace quotes or an escape protect while the bare
  whitespace around it is trimmed, ends at a `#` or `;` outside quotes,
  and continues on the next
  line after a backslash at the end of the line that is part of the value:
  a backslash that ends a comment, a header line or a blank line continues
  nothing, as in git, so a comment such as `# C:\\git\\` never swallows the
  header after it. A pair may follow its header on the same line
  (`[remote "origin"] url = ...`), as git allows. A line that is not a
  section header or a `key = value` pair, and the keys after an
  unterminated section header, are skipped, and a value git rejects, a
  quoted one the file ends inside or one with an escape git does not
  define, is dropped and reported, since a config cut mid-URL or edited
  by hand must not yield a destination git would not read; the deprecated
  dotted form lower-cases its subsection, as git does;
  the rest of the file is still read. A remote may have several `url` and
  `pushurl` lines (git fetches from the first `url` and pushes to every
  `pushurl`, or to every `url` when there is none), so every value of each
  is kept, in file order.
* `.git/HEAD`: `ref: refs/heads/<branch>` while a branch is checked out,
  else the commit hash of a detached HEAD.

Files are read whole from the evidence copy, opened read-only and only when
`lstat` says they are regular files, so a symlink is never followed. A file
that cannot be read (missing, not a regular file, a permission or I/O
error) gives no remotes and no head, and `project_git` reports it as a
problem, `<path>: <reason>`, so an unreadable file is never mistaken for a
repository without remotes.
"""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterable
from pathlib import Path

from .inputs import PROJECT_AGENT, Artifact

CONFIG_REL = ".git/config"
HEAD_REL = ".git/HEAD"

_HEADER_RX = re.compile(r'\[\s*([A-Za-z0-9.-]+)(?:\s+"((?:[^"\\]|\\.)*)")?\s*\]')
_KEY_RX = re.compile(r"([A-Za-z][A-Za-z0-9-]*)\s*(?:=(.*))?$")
_ESCAPES = {"\\": "\\", '"': '"', "n": "\n", "t": "\t", "b": "\b"}


def read_text(path: Path) -> tuple[str, str]:
    """`(text, error)`: the whole file at `path` as text (UTF-8, undecodable
    bytes replaced) and `""`, or `""` and the reason when it is missing,
    unreadable or not a regular file. Never follows a symlink."""
    try:
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return "", "not a regular file"
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            data = handle.read()
    except OSError as error:
        return "", error.strerror or type(error).__name__
    return data.decode("utf-8", errors="replace"), ""


# The whitespace git trims around a value and a ref: ASCII only, since
# `str.strip()` would also take U+00A0 and its kind, which git keeps.
_ASCII_SPACE = " \t\r\f\v"


def _physical_lines(text: str) -> list[str]:
    """`text` split at line feeds only, a carriage return before one
    removed, and an initial byte-order mark dropped: git ends a line at LF
    or CRLF alone and accepts a UTF-8 BOM at the start of a config, while
    `str.splitlines()` would also split at U+2028, U+0085 and the ASCII
    separators, cutting a path that holds one."""
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [line[:-1] if line.endswith("\r") else line for line in lines]


def _parse_value(lines: list[str], index: int, text: str) -> tuple[str, int, str]:
    """The value that starts with `text` on line `i` of `lines`, with quotes
    and escapes resolved, a trailing comment removed and only the bare
    whitespace around it trimmed, the index of the last line it used, and
    `""` or the reason git would reject the line (an unterminated quote, an
    escape other than `\\\\`, `\\"`, `\\n`, `\\t` and `\\b`), in which case
    the value is `""`: a backslash at the end of the line, outside a
    comment, continues the value on the next line (a comment ends the line
    and never continues it, as in git). A lone backslash at the end of the
    file is dropped."""
    # Each character with whether quotes or an escape protect it: only bare
    # whitespace around the value is trimmed, as git trims it, so a quoted
    # path that ends in a space keeps its space.
    out: list[tuple[str, bool]] = []
    quoted = False
    while True:
        position = 0
        continued = False
        while position < len(text):
            character = text[position]
            if character == "\\":
                if position + 1 < len(text):
                    if text[position + 1] not in _ESCAPES:
                        # git rejects the line; the value is not evidence.
                        return "", index, "unsupported escape \\" + text[position + 1]
                    out.append((_ESCAPES[text[position + 1]], True))
                    position += 2
                    continue
                continued = True
                break
            if character == '"':
                quoted = not quoted
            elif character in "#;" and not quoted:
                break
            else:
                out.append((character, quoted))
            position += 1
        if continued and index + 1 < len(lines):
            index += 1
            text = lines[index]
            continue
        # One pass from each end, since the file is untrusted and a value
        # padded with kilobytes of spaces must not cost a pop(0) per space.
        first, last = 0, len(out)
        while first < last and out[first][0] in _ASCII_SPACE and not out[first][1]:
            first += 1
        while last > first and out[last - 1][0] in _ASCII_SPACE and not out[last - 1][1]:
            last -= 1
        value = "".join(character for character, _ in out[first:last])
        # A quote still open at the end is a value the file ends inside: git
        # rejects the line, and the text so far is not the destination.
        return value, index, "unterminated quoted value" if quoted else ""


def _entries(text: str, errors: list[str]) -> Iterable[tuple[str, str | None]]:
    """The config's entries in order: `("[", header)` for a section header
    and `(key, value)` for a pair, the key lower-cased and the value
    resolved by `_parse_value`. A pair may follow its header on the same
    line (`[remote "origin"] url = ...`), as git allows. Comment, blank and
    unparseable lines are skipped; only a value continues across lines. A
    pair git would reject, a quoted value the file ends inside or an
    escape git does not define, is dropped and described in `errors`
    (`line <n>: unterminated quoted value`, `line <n>: unsupported escape
    \\q`), since its text is not the value git would have read."""
    lines = _physical_lines(text)
    index = 0
    while index < len(lines):
        # Only leading whitespace is dropped here: a value's trailing
        # whitespace is _parse_value's to judge, since `\ ` at the end of a
        # line is an escaped space, not a continuation.
        line = lines[index].lstrip(_ASCII_SPACE)
        if line.startswith("["):
            match = _HEADER_RX.match(line)
            if match is None:
                yield "[", line.rstrip(_ASCII_SPACE)  # unterminated or malformed
                index += 1
                continue
            yield "[", match.group(0)
            line = line[match.end() :].lstrip(_ASCII_SPACE)
        if not line or line[0] in "#;":
            index += 1
            continue
        match = _KEY_RX.match(line)
        if match is None:
            index += 1
            continue
        if match.group(2) is None:
            yield match.group(1).lower(), None
            index += 1
            continue
        start = index + 1
        value, index, error = _parse_value(lines, index, match.group(2))
        if error:
            errors.append("line %d: %s" % (start, error))
        else:
            yield match.group(1).lower(), value
        index += 1


def parse_remotes(text: str, errors: list[str] | None = None) -> list[dict]:
    """The remotes of a `.git/config` text: one `{"name", "urls",
    "pushurls"}` per `[remote "<name>"]` section that sets a non-empty `url`
    or `pushurl`, sorted by name. `urls` and `pushurls` hold every value of
    the key in file order, `[]` when the section sets none: `pushurls` is
    what the file says, not git's fallback to `urls`. A value the file ends
    inside (an unterminated quote) is left out and, when `errors` is given,
    described in it as `_entries` does."""
    remotes: dict[str, dict] = {}
    current: str | None = None
    for key, value in _entries(text, [] if errors is None else errors):
        if key == "[":
            match = _HEADER_RX.match(value or "")
            current = None
            if match is None:
                continue  # unterminated or malformed: its keys belong to no section
            section, subsection = match.group(1).lower(), match.group(2)
            if subsection is not None:
                if section == "remote":
                    current = re.sub(r"\\(.)", r"\1", subsection)
            elif section.startswith("remote.") and len(section) > len("remote."):
                # git lower-cases the dotted form's subsection, so
                # [remote.Origin] and [remote "origin"] are one remote.
                current = section[len("remote.") :]
            continue
        if current is None or key not in ("url", "pushurl") or not value:
            continue
        remote = remotes.setdefault(current, {"name": current, "urls": [], "pushurls": []})
        remote[key + "s"].append(value)
    return [remote for _, remote in sorted(remotes.items())]


def parse_head(text: str) -> str:
    """The branch a `.git/HEAD` text names (`ref: refs/heads/<branch>`), the
    full ref for any other symbolic ref, else the detached commit hash; ""
    for an empty text. The first line ends at a line feed, and only ASCII
    whitespace is trimmed, since a ref may hold other whitespace."""
    lines = [line.strip(_ASCII_SPACE) for line in _physical_lines(text)]
    first = next((line for line in lines if line), "")
    if first.startswith("ref:"):
        ref = first[len("ref:") :].strip(_ASCII_SPACE)
        return ref[len("refs/heads/") :] if ref.startswith("refs/heads/") else ref
    return first


def project_git(
    artifacts: Iterable[Artifact], problems: list[str] | None = None
) -> dict[str, dict]:
    """`{"remotes": [...], "head": str}` per project directory among the
    `artifacts`, keyed as `cli.project_agents` keys it (`home.original`, or
    the disk path when that is empty), from its `.git/config` and
    `.git/HEAD` files with agent `project`. A project without them is
    absent. The file is chosen by name: the exact spelling when the
    collection has it, else the first file whose name matches without
    regard to case, because the PowerShell collector matches the catalog
    that way and keeps the on-disk spelling (`.GIT/CONFIG` on Windows, and
    on a macOS or other case-insensitive volume), while a case-sensitive
    volume that holds both spellings keeps git's own. A file that cannot
    be read, or a pair in it git would reject, is appended to `problems`,
    when given, as `<original path>: <reason>` (once per path)."""
    chosen: dict[str, dict[str, Artifact]] = {}
    for artifact in artifacts:
        if not artifact.home.project or artifact.agent != PROJECT_AGENT:
            continue
        lower = artifact.rel.lower()
        if lower == CONFIG_REL:
            field, exact = "remotes", artifact.rel == CONFIG_REL
        elif lower == HEAD_REL.lower():
            field, exact = "head", artifact.rel == HEAD_REL
        else:
            continue
        path = artifact.home.original or str(artifact.home.disk_path)
        fields = chosen.setdefault(path, {})
        if field not in fields or (exact and fields[field].rel != artifact.rel):
            fields[field] = artifact
    out: dict[str, dict] = {}
    for path, fields in chosen.items():
        entry = out[path] = {"remotes": [], "head": ""}
        for field, artifact in fields.items():
            text, error = read_text(artifact.disk_path)
            errors = [error] if error else []
            if not error:
                if field == "head":
                    entry[field] = parse_head(text)
                else:
                    entry[field] = parse_remotes(text, errors)
            for message in errors:
                line = "%s: %s" % (artifact.original, message)
                if problems is not None and line not in problems:
                    problems.append(line)
    return out
