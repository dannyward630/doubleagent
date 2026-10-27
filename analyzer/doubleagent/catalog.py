"""The shared artifact catalog.

`catalog.txt` is a verbatim copy of `collect-agent-artifacts.sh --list` and is
the analyzer's detection database: the same `agent|glob` table that tells the
collectors what to gather tells the analyzer what a loose directory contains.
`collectors/tests/catalog-sync.sh` fails when the copy drifts. Regenerate it
with:

    collectors/collect-agent-artifacts.sh --list > analyzer/doubleagent/catalog.txt

Glob semantics match the collectors: catalog globs do not cross `/`, exclusion
and secret globs do, `[...]` classes work everywhere.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

CATALOG_FILE = Path(__file__).with_name("catalog.txt")


@dataclass
class Entry:
    agent: str
    glob: str
    segments: tuple[str, ...]
    regexes: tuple[re.Pattern[str], ...]

    @property
    def first_segment(self) -> str:
        return self.segments[0]


@dataclass
class Catalog:
    entries: list[Entry] = field(default_factory=list)
    project_entries: list[Entry] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)
    docker_volumes: list[Entry] = field(default_factory=list)  # agent|volume name glob
    text: str = ""

    @property
    def agents(self) -> list[str]:
        seen: dict[str, None] = {}
        for entry in self.entries:
            seen.setdefault(entry.agent)
        return list(seen)

    def first_segment_regexes(self) -> list[re.Pattern[str]]:
        seen: dict[str, re.Pattern[str]] = {}
        for entry in self.entries:
            seen.setdefault(entry.first_segment, entry.regexes[0])
        return list(seen.values())

    def project_agent_for(self, rel: str) -> str:
        """The agent of the project catalog entry that claims `rel`, a path
        relative to a project directory, or `""` when none matches. The most
        specific matching entry wins (`.pi/approved-plan.md` before `.pi`),
        then the first in catalog order, as the collectors' nested-claim rule
        attributes a file. Used to re-attribute rows that collectors before
        1.12.0 recorded with agent `project`; the result is `project` for a
        file the catalog still leaves to no single agent (`AGENTS.md`)."""
        parts = [part for part in rel.replace("\\", "/").split("/") if part]
        best: Entry | None = None
        for entry in self.project_entries:
            depth = len(entry.segments)
            if depth > len(parts) or (best is not None and depth <= len(best.segments)):
                continue
            if all(
                pattern.fullmatch(part)
                for pattern, part in zip(entry.regexes, parts[:depth], strict=True)
            ):
                best = entry
        return best.agent if best is not None else ""

    def claims_home_path(self, rel: str, windows: bool = False) -> str:
        """The agent of the home catalog entry that claims `rel`, a path
        relative to a home, or `""` when none matches. An entry claims the
        path when it has no more segments than the path and each of its
        segment regexes fully matches the path's segment at the same place,
        so `.copilot` claims `.copilot/chats/<id>` and `.config/[Cc]ursor`
        claims `.config/Cursor/x`, while `.config/myproject` is claimed by
        no entry, since none is the bare `.config`. The most specific
        matching entry wins, then the first in catalog order. With
        `windows` the path is split on backslashes and every segment is
        matched without regard to case, as Windows compares file names.
        Used to tell an agent's own working directory (a scratch
        directory) from a project in inventory.json (issue 149)."""
        separator = "\\" if windows else "/"
        parts = [part for part in rel.split(separator) if part]
        flags = re.IGNORECASE if windows else 0
        best: Entry | None = None
        for entry in self.entries:
            depth = len(entry.segments)
            if depth > len(parts) or (best is not None and depth <= len(best.segments)):
                continue
            pairs = zip(entry.regexes, parts[:depth], strict=True)
            if all(re.fullmatch(pattern.pattern, part, flags) for pattern, part in pairs):
                best = entry
        return best.agent if best is not None else ""

    def nested_matches(self, agent_dir: Path, onerror=None) -> Iterator[tuple[Entry, Path]]:
        """Yield (entry, path) for catalog globs that live inside agent_dir
        when agent_dir itself is the first segment of their glob, for example
        .gemini/antigravity-cli inside a .gemini directory given as the root."""
        listing_cache: dict[Path, list[str]] = {}
        for entry in self.entries:
            if len(entry.segments) < 2 or entry.regexes[0].fullmatch(agent_dir.name) is None:
                continue
            for hit in _expand(agent_dir, entry.regexes[1:], listing_cache, onerror):
                yield entry, hit

    def matches_in_home(self, home: Path, onerror=None) -> Iterator[tuple[Entry, Path]]:
        """Yield (entry, path) for every catalog glob that exists under home.

        Expansion is segment by segment through real directory listings, so
        the cost is proportional to the catalog, not to the size of the tree.
        Symlinks are never followed. A directory that cannot be listed
        matches nothing and is passed, as the OSError, to `onerror` once.
        """
        listing_cache: dict[Path, list[str]] = {}
        for entry in self.entries:
            for hit in _expand(home, entry.regexes, listing_cache, onerror):
                yield entry, hit


def glob_segment_to_regex(segment: str) -> re.Pattern[str]:
    """Convert one glob path segment to a regex. `*` and `?` never match `/`;
    `[...]` passes through with `!` meaning negation as in sh."""
    out = []
    i = 0
    while i < len(segment):
        character = segment[i]
        if character == "*":
            out.append("[^/]*")
        elif character == "?":
            out.append("[^/]")
        elif character == "[":
            j = segment.find("]", i + 1)
            if j == -1:
                out.append(re.escape(character))
            else:
                body = segment[i + 1 : j]
                if body.startswith("!"):
                    body = "^" + body[1:]
                body = body.replace("\\", "\\\\")
                out.append("[" + body + "]")
                i = j
        else:
            out.append(re.escape(character))
        i += 1
    return re.compile("".join(out))


def _expand(
    base: Path,
    regexes: tuple[re.Pattern[str], ...],
    cache: dict[Path, list[str]],
    onerror=None,
) -> Iterator[Path]:
    if not regexes:
        yield base
        return
    names = cache.get(base)
    if names is None:
        try:
            names = os.listdir(base)
        except OSError as error:
            names = []
            if onerror is not None:
                onerror(error)
        cache[base] = names
    pattern = regexes[0]
    rest = regexes[1:]
    for name in names:
        if pattern.fullmatch(name) is None:
            continue
        child = base / name
        if rest:
            if child.is_dir() and not child.is_symlink():
                yield from _expand(child, rest, cache, onerror)
        else:
            yield child


def _make_entry(agent: str, glob: str) -> Entry:
    segments = tuple(segment for segment in glob.split("/") if segment)
    return Entry(
        agent, glob, segments, tuple(glob_segment_to_regex(segment) for segment in segments)
    )


def load(path: Path = CATALOG_FILE) -> Catalog:
    text = path.read_text(encoding="utf-8")
    return parse(text)


def parse(text: str) -> Catalog:
    catalog = Catalog(text=text)
    section = "home"
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        if line.startswith("#"):
            head = line[1:].strip().lower()
            if head.startswith("home artifacts"):
                section = "home"
            elif head.startswith("project artifacts"):
                section = "project"
            elif head.startswith("excluded"):
                section = "exclude"
            elif head.startswith("credential files"):
                section = "secret"
            elif head.startswith("docker volumes"):
                section = "docker"
            continue
        if section == "home":
            agent, _, glob = line.partition("|")
            catalog.entries.append(_make_entry(agent, glob))
        elif section == "project":
            agent, _, glob = line.partition("|")
            catalog.project_entries.append(_make_entry(agent, glob))
        elif section == "exclude":
            catalog.excludes.append(line)
        elif section == "docker":
            agent, _, glob = line.partition("|")
            catalog.docker_volumes.append(_make_entry(agent, glob))
        else:
            catalog.secrets.append(line)
    return catalog
