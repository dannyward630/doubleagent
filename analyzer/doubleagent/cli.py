"""Run the `doubleagent` command: detect agents, write the timeline, merge inventories."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, OrderedDict
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypedDict

from . import VERSION, gitmeta
from . import catalog as catalog_mod
from . import inventory as inventory_mod
from .dedup import deduplicate
from .errors import DoubleAgentError
from .filters import FORMS_HELP, RowFilter, parse_bound
from .gitmeta import Remote
from .inputs import PROJECT_AGENT, Collection, describe_error, error_reason, open_input
from .model import (
    GIT_REMOTE_PREFIX,
    SCRATCH_PREFIX,
    Row,
    SessionSummary,
    canonical_project_path,
    is_windows_path,
    project_key,
    summarise,
)
from .parsers import ALL, NO_TRANSCRIPTS, Options, by_agent

PROG = "doubleagent"
# The agents whose parser reads at least one secondary source
# (`Parser.has_secondary`), and the `recovered` values of a session that
# secondary sources kept rows of.
SECONDARY_AGENTS = frozenset(parser.agent for parser in ALL if parser.has_secondary)
RECOVERED = ("yes", "partial")
# The agents whose parser records sync, relay and origin state
# (`Parser.records_sync`, `records_relay`, `records_origin`).
SYNC_AGENTS = frozenset(parser.agent for parser in ALL if parser.records_sync)
RELAY_AGENTS = frozenset(parser.agent for parser in ALL if parser.records_relay)
ORIGIN_AGENTS = frozenset(parser.agent for parser in ALL if parser.records_origin)
# The session marks summarised per project, in key order: the key, which
# is also the `SessionSummary` attribute, the value every session must have
# for the full label, the values a session counts with, the full, some and
# none labels, and the agents whose parser records the mark.
PROJECT_MARKS = (
    ("synced", "yes", ("yes",), ("yes", "partial", "no"), SYNC_AGENTS),
    ("relayed", "yes", ("yes",), ("yes", "partial", "no"), RELAY_AGENTS),
    ("origin", "remote", ("remote",), ("remote", "mixed", "local"), ORIGIN_AGENTS),
    ("recovered", "yes", RECOVERED, ("yes", "partial", "no"), SECONDARY_AGENTS),
)


class FileCounts(TypedDict):
    """The number and total size of an agent's files."""

    files: int
    bytes: int


class DetectRow(TypedDict):
    """One row of the `detect` table."""

    user: str
    home: str
    agent: str
    files: int
    bytes: int
    parser: bool
    inferred: bool


class HomeAgent(TypedDict):
    """One agent of a home or project in `detect --json` and inventory.json."""

    agent: str
    files: int
    bytes: int
    parser: bool


class HomeEntry(TypedDict):
    """One home of the `homes` array of `detect --json` and inventory.json."""

    user: str
    home: str
    inferred: bool
    agents: list[HomeAgent]


class ProjectAgents(TypedDict):
    """The users and agents of one project directory of the input."""

    users: list[str]
    agents: dict[str, FileCounts]
    shared_files: int
    shared_bytes: int


class DetectProject(TypedDict):
    """One project of the `projects` array of `detect --json`."""

    path: str
    users: list[str]
    agents: list[HomeAgent]
    shared_files: int
    shared_bytes: int
    remotes: list[Remote]
    head: str


class DetectObject(TypedDict):
    """The keys `detect --json` and inventory.json share."""

    input: str
    kind: str
    host: str
    notes: list[str]
    homes: list[HomeEntry]
    projects: list[DetectProject]


class ProjectFiles(TypedDict):
    """The collected files and repository of one project path."""

    agents: dict[str, FileCounts]
    shared_files: int
    remotes: list[Remote]
    head: str


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser of the command and its subcommands."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Detect AI agent state in a collection and parse it into a JSONL timeline.",
    )
    parser.add_argument("--version", action="version", version="%s %s" % (PROG, VERSION))
    subcommands = parser.add_subparsers(dest="command", required=True)

    def add_input(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "input",
            type=Path,
            help="collector archive (.tar.gz or .zip), extracted collection, or any directory",
        )
        subparser.add_argument(
            "--host", default="", help="host name to record when the input has no collection.json"
        )
        subparser.add_argument(
            "--user",
            default="",
            help="user name to record for a home whose owner cannot be inferred",
        )
        subparser.add_argument(
            "--work-dir",
            type=Path,
            default=None,
            help="where to extract an archive (default: a temporary directory removed afterwards)",
        )
        subparser.add_argument(
            "--keep-extracted", action="store_true", help="do not delete the extracted archive"
        )

    detect = subcommands.add_parser(
        "detect", help="list the homes, users and agents found in the input"
    )
    add_input(detect)
    detect.add_argument("--json", action="store_true", help="machine-readable output")
    detect.add_argument("--files", action="store_true", help="list every attributed file")

    timeline = subcommands.add_parser(
        "timeline", help="parse transcripts into timeline.jsonl and sessions.jsonl"
    )
    add_input(timeline)
    timeline.add_argument("-o", "--output", type=Path, required=True, help="output directory")
    timeline.add_argument(
        "--include-thinking",
        action="store_true",
        help="emit thinking and reasoning blocks as rows of type thinking",
    )
    timeline.add_argument(
        "--agent",
        action="append",
        default=[],
        help="only parse this agent (repeatable); default is every agent with a parser",
    )
    timeline.add_argument(
        "--since",
        metavar="WHEN",
        default="",
        help="keep rows at or after WHEN; see --until for the forms",
    )
    timeline.add_argument(
        "--until",
        metavar="WHEN",
        default="",
        help="keep rows at or before WHEN. UTC unless an offset is given; a value without a "
        "time of day (2026-10-01, 2026-10, today) covers that whole period. " + FORMS_HELP,
    )
    timeline.add_argument(
        "--keep-undated",
        action="store_true",
        help="with --since or --until, also keep rows that have no timestamp",
    )
    timeline.add_argument(
        "--match",
        metavar="REGEX",
        action="append",
        default=[],
        help="keep rows whose text matches this Python regular expression (repeatable, any may "
        "match); a matched tool call keeps its result and a matched result its call",
    )
    timeline.add_argument(
        "-i",
        "--ignore-case",
        action="store_true",
        help="make --match case-insensitive",
    )

    inventory = subcommands.add_parser(
        "inventory", help="merge collector --inventory outputs into one fleet CSV"
    )
    inventory.add_argument(
        "input",
        type=Path,
        nargs="+",
        help="a saved stdout of collect-agent-artifacts --inventory, or a directory of them",
    )
    inventory.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(inventory_mod.DEFAULT_NAME),
        help="CSV to write (default: %s in the current directory)" % inventory_mod.DEFAULT_NAME,
    )

    catalog = subcommands.add_parser("catalog", help="print the bundled artifact catalog")
    catalog.add_argument(
        "--agents", action="store_true", help="print agent names and whether a parser exists"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command with the given arguments and return its exit code."""
    args = build_parser().parse_args(argv)
    if args.command == "catalog":
        return cmd_catalog(args)
    if args.command == "inventory":
        return cmd_inventory(args)
    if args.command == "timeline":
        # Checked before an archive is extracted, so a typo fails at once.
        # ValueError here and below is the standard library refusing a value,
        # such as an integer too long to convert or a path with a null byte.
        try:
            args.row_filter = build_filter(args)
        except (DoubleAgentError, ValueError) as error:
            print("error: %s" % error, file=sys.stderr)
            return 2
    catalog = catalog_mod.load()
    try:
        collection = open_input(args.input, catalog, work_dir=args.work_dir, host=args.host)
    except OSError as error:
        print("error: %s" % describe_error(args.input, error), file=sys.stderr)
        return 2
    except (DoubleAgentError, ValueError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 2
    try:
        if args.user:
            for home in collection.homes:
                if not home.user:
                    home.user = args.user
        if args.command == "detect":
            return cmd_detect(args, collection)
        return cmd_timeline(args, collection)
    finally:
        if not args.keep_extracted:
            collection.cleanup()
        elif collection._tmp:
            print("extracted to: %s" % collection._tmp, file=sys.stderr)


# ---- catalog --------------------------------------------------------------------


def cmd_catalog(args: argparse.Namespace) -> int:
    """Print the bundled catalog, or its agents and whether each has a parser."""
    catalog = catalog_mod.load()
    if not args.agents:
        sys.stdout.write(catalog.text)
        return 0
    parsers = by_agent()
    for agent in catalog.agents:
        print("%-20s %s" % (agent, "parser" if agent in parsers else "detect only"))
    return 0


# ---- inventory ------------------------------------------------------------------


def cmd_inventory(args: argparse.Namespace) -> int:
    """Merge inventory files into the fleet CSV and print the per-agent rollup."""
    try:
        files = inventory_mod.input_files(args.input)
    except OSError as error:
        print("error: %s" % describe_error("", error), file=sys.stderr)
        return 2
    except (DoubleAgentError, ValueError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 2
    rows: list[list[str]] = []
    for path in files:
        try:
            file_rows, junk = inventory_mod.read_file(path)
        except OSError as error:
            print("error: %s" % describe_error(path, error), file=sys.stderr)
            return 2
        if junk:
            print(
                "skipped %d non-inventory line%s in %s" % (junk, "" if junk == 1 else "s", path),
                file=sys.stderr,
            )
        rows.extend(file_rows)
    if args.output.parent != Path(""):
        args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(inventory_mod.INVENTORY_COLUMNS)
        writer.writerows(rows)
    hosts = {row[0] for row in rows}
    print(
        "rows:   %d from %d host%s in %s"
        % (len(rows), len(hosts), "" if len(hosts) == 1 else "s", args.output)
    )
    totals = inventory_mod.rollup(rows)
    if totals:
        print()
        print("%-22s %6s %6s  %s" % ("agent", "hosts", "users", "latest"))
        for agent, host_count, user_count, last in totals:
            print("%-22s %6d %6d  %s" % (agent, host_count, user_count, last))
    return 0 if rows else 1


# ---- detect ---------------------------------------------------------------------


def detect_table(collection: Collection, include_projects: bool = True) -> list[DetectRow]:
    """Return the rows of the `detect` table: one per user, home and agent.

    Each row has `user`, `home`, `agent`, `files`, `bytes` (`artifact_bytes`),
    `parser` and `inferred`, in the order the first file was met. Without
    `include_projects`, artifacts in a project directory are left out.
    """
    parsers = by_agent()
    rows: dict[tuple[str, str, str], DetectRow] = OrderedDict()
    for artifact in collection.artifacts:
        if artifact.home.project and not include_projects:
            continue
        key = (artifact.home.user, artifact.home.original, artifact.agent)
        row = rows.get(key)
        if row is None:
            row = rows[key] = DetectRow(
                {
                    "user": artifact.home.user,
                    "home": artifact.home.original or str(artifact.home.disk_path),
                    "agent": artifact.agent,
                    "files": 0,
                    "bytes": 0,
                    "parser": artifact.agent in parsers,
                    "inferred": artifact.home.inferred,
                }
            )
        row["files"] += 1
        row["bytes"] += artifact_bytes(artifact)
    return list(rows.values())


def artifact_bytes(artifact) -> int:
    """Return an artifact's manifest `size`, else its `lstat` size, 0 when unreadable."""
    if artifact.manifest is not None:
        return int(artifact.manifest.get("size") or 0)
    try:
        return artifact.disk_path.lstat().st_size
    except OSError:
        return 0


def home_agents(collection: Collection) -> list[HomeEntry]:
    """Return the `homes` array of `detect --json` and inventory.json.

    One object per home that is not a project, in the order its first row was
    met, with `user`, `home`, `inferred` and `agents`: per agent with files
    there, sorted, its `agent`, `files`, `bytes` and `parser`.
    """
    parsers = by_agent()
    counts: dict[int, dict[str, FileCounts]] = {}
    for artifact in collection.artifacts:
        if artifact.home.project:
            continue
        agent_counts = counts.setdefault(id(artifact.home), {}).setdefault(
            artifact.agent, {"files": 0, "bytes": 0}
        )
        agent_counts["files"] += 1
        agent_counts["bytes"] += artifact_bytes(artifact)
    return [
        {
            "user": home.user,
            "home": home.original,
            "inferred": home.inferred,
            "agents": [
                {
                    "agent": agent,
                    "files": agent_counts["files"],
                    "bytes": agent_counts["bytes"],
                    "parser": agent in parsers,
                }
                for agent, agent_counts in sorted(counts.get(id(home), {}).items())
            ],
        }
        for home in collection.homes
        if not home.project
    ]


def project_agents(collection: Collection) -> dict[str, ProjectAgents]:
    """Return the agents used in each project directory of the input, keyed by its path.

    The path is `home.original` on the source host (with the image root in
    image mode), sorted. Each value has the sorted `users`, the `agents`
    with their `files` and `bytes`, and `shared_files` and `shared_bytes` for
    the files of agent `project`, which no single agent owns. Loose input
    gives an empty dict.
    """
    groups: dict[str, dict] = {}
    for artifact in collection.artifacts:
        if not artifact.home.project:
            continue
        path = artifact.home.original or str(artifact.home.disk_path)
        group = groups.setdefault(
            path, {"users": set(), "agents": {}, "shared_files": 0, "shared_bytes": 0}
        )
        if artifact.home.user:
            group["users"].add(artifact.home.user)
        size = artifact_bytes(artifact)
        if artifact.agent == PROJECT_AGENT:
            group["shared_files"] += 1
            group["shared_bytes"] += size
        else:
            counts = group["agents"].setdefault(artifact.agent, {"files": 0, "bytes": 0})
            counts["files"] += 1
            counts["bytes"] += size
    return {
        path: {
            "users": sorted(group["users"]),
            "agents": dict(sorted(group["agents"].items())),
            "shared_files": group["shared_files"],
            "shared_bytes": group["shared_bytes"],
        }
        for path, group in sorted(groups.items())
    }


def detect_object(collection: Collection) -> DetectObject:
    """Return the keys `detect --json` and inventory.json share, in order.

    The keys are `input`, `kind`, `host`, `notes`, `homes` (`home_agents`) and
    `projects`, whose entries end with the repository's `remotes` and `head`
    (`gitmeta.project_git`). A repository file that cannot be read is added
    to `collection.problems`.
    """
    parsers = by_agent()
    git = gitmeta.project_git(collection.artifacts, collection.problems)
    projects: list[DetectProject] = [
        {
            "path": path,
            "users": project["users"],
            "agents": [
                {
                    "agent": agent,
                    "files": counts["files"],
                    "bytes": counts["bytes"],
                    "parser": agent in parsers,
                }
                for agent, counts in project["agents"].items()
            ],
            "shared_files": project["shared_files"],
            "shared_bytes": project["shared_bytes"],
            "remotes": git[path]["remotes"] if path in git else [],
            "head": git[path]["head"] if path in git else "",
        }
        for path, project in project_agents(collection).items()
    ]
    return {
        "input": str(collection.source),
        "kind": collection.kind,
        "host": collection.host,
        "notes": collection.notes,
        "homes": home_agents(collection),
        "projects": projects,
    }


def print_project_table(projects: list[DetectProject]) -> None:
    """Print the project table of `detect`.

    Each project gets one line per agent, a `(shared)` line for its shared
    files and a `remotes:` line when its repository has remotes; the path and
    users appear on its first line only.
    """
    line = "%-40s %-14s %-18s %8s %12s  %s"
    print(line % ("project", "users", "agent", "files", "bytes", "parser"))
    for project in projects:
        lines = [
            (
                entry["agent"],
                entry["files"],
                entry["bytes"],
                "yes" if entry["parser"] else "detect only",
            )
            for entry in project["agents"]
        ]
        if project["shared_files"]:
            lines.append(("(shared)", project["shared_files"], project["shared_bytes"], ""))
        first = (project["path"][:40], ",".join(project["users"]) or "?")
        for i, (agent, files, size, parser) in enumerate(lines):
            path, users = first if i == 0 else ("", "")
            print((line % (path, users, agent, files, size, parser)).rstrip())
        if project["remotes"]:
            print("  remotes: " + remotes_text(project["remotes"]))


def remotes_text(remotes: list[Remote]) -> str:
    """Return the remotes as `<name> <url> ... (push <pushurl> ...)`, joined with `, `."""
    parts = []
    for remote in remotes:
        text = " ".join([remote["name"], *remote["urls"]])
        if remote["pushurls"]:
            text += " (push %s)" % " ".join(remote["pushurls"])
        parts.append(text)
    return ", ".join(parts)


def cmd_detect(args: argparse.Namespace, collection: Collection) -> int:
    """Print the homes, agents and projects of the input, as tables or JSON."""
    detection = detect_object(collection)
    if args.json:
        out = {**detection, "problems": collection.problems}
        if args.files:
            out["files"] = [
                {"user": artifact.home.user, "agent": artifact.agent, "path": artifact.original}
                for artifact in collection.artifacts
            ]
        json.dump(out, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    print("input:   %s" % collection.source)
    print(
        "kind:    %s%s"
        % (
            collection.kind,
            ""
            if collection.kind != "loose"
            else " (no manifest; user and home inferred from paths)",
        )
    )
    print("host:    %s" % (collection.host or "(unknown)"))
    for note in collection.notes:
        print("note:    %s" % note)
    for problem in collection.problems:
        print("problem: %s" % problem)
    table, projects = detect_table(collection, include_projects=False), detection["projects"]
    if not table and not projects:
        print("no agent artifacts found")
        return 1
    if table:
        print()
        print(
            "%-14s %-32s %-18s %8s %12s  %s" % ("user", "home", "agent", "files", "bytes", "parser")
        )
    for row in table:
        print(
            "%-14s %-32s %-18s %8d %12d  %s"
            % (
                row["user"] or "?",
                row["home"][:32],
                row["agent"],
                row["files"],
                row["bytes"],
                "yes" if row["parser"] else "detect only",
            )
        )
    if projects:
        print()
        print_project_table(projects)
    if args.files:
        print()
        for artifact in collection.artifacts:
            print("%s\t%s\t%s" % (artifact.home.user, artifact.agent, artifact.original))
    return 0


# ---- timeline -------------------------------------------------------------------


def parsers_for(artifact, parsers: dict[str, list]) -> list:
    """Return the parsers offered an artifact: its agent's and those naming it in `reads_agents`."""
    # A file in a project directory that the catalog leaves to no single
    # agent (agent `project`, inputs.PROJECT_AGENT) may be read by any of
    # them, so it is offered to every parser.
    if artifact.agent == PROJECT_AGENT:
        return ALL
    own = parsers.get(artifact.agent, [])
    # Parsers that read another agent's files (Cody and Twinny rows inside
    # the state.vscdb of `vscode` or a fork) say so in `reads_agents`.
    return own + [
        parser for parser in ALL if artifact.agent in parser.reads_agents and parser not in own
    ]


def collect_rows(
    collection: Collection, opts: Options, agents: list[str]
) -> tuple[list[Row], Counter, list[str], Counter]:
    """Parse every artifact into timeline rows.

    Returns:
        The rows, sorted; their counts per (agent, turn_type); the problems;
        and the rows `dedup.deduplicate` dropped per agent.
    """
    parsers = by_agent()
    primary: list[Row] = []
    secondary: list[tuple[Row, float]] = []
    problems: list[str] = list(collection.problems)
    for artifact in collection.artifacts:
        for parser in parsers_for(artifact, parsers):
            # Filter on the parser's agent, so --agent aider also takes the
            # repository-level Aider files the manifest calls `project`.
            if agents and parser.agent not in agents:
                continue
            if not parser.wants(artifact):
                continue
            tolerance = parser.secondary_tolerance(artifact) if parser.secondary(artifact) else None
            try:
                for row in parser.parse(artifact, opts):
                    # One spelling per Windows folder, whichever parser and
                    # store the path came from.
                    row.project_path = canonical_project_path(row.project_path)
                    if tolerance is None:
                        primary.append(row)
                    else:
                        secondary.append((row, tolerance))
            except OSError as error:
                problems.append("%s: %s" % (artifact.original, error_reason(error)))
    rows, deduplicated = deduplicate(primary, secondary)
    counts: Counter = Counter((row.agent, row.turn_type) for row in rows)
    rows.sort(
        key=lambda row: (
            row.timestamp_utc == "",
            row.timestamp_utc,
            row.source_file,
            row.source_line,
        )
    )
    return rows, counts, problems, deduplicated


# No spaces after separators: the same layout as `jq -c`, so a grep pattern
# such as '"agent":"codex-cli"' matches both the file and jq's output.
JSONL_SEPARATORS = (",", ":")


def jsonl_line(record: dict) -> str:
    """Return a record as one JSON line, keys in schema order.

    Non-ASCII text is written as UTF-8, so grep finds it as typed. The Unicode
    line and paragraph separators are escaped because some readers split
    on them, and a record
    holding a lone surrogate, which UTF-8 cannot encode, falls back to ASCII
    escapes.
    """
    text = json.dumps(record, ensure_ascii=False, separators=JSONL_SEPARATORS)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return json.dumps(record, separators=JSONL_SEPARATORS)
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def write_jsonl(path: Path, rows) -> None:
    """Write rows (`Row` or `SessionSummary`) to a JSONL file."""
    with open(path, "w", newline="\n", encoding="utf-8") as handle:
        for row in rows:
            handle.write(jsonl_line(row.as_dict()))
            handle.write("\n")


def build_filter(args: argparse.Namespace) -> RowFilter:
    """Return the row filter of `--since`, `--until`, `--keep-undated` and `--match`.

    Raises:
        DoubleAgentError: A value is bad; the message is for the analyst.
    """
    since = parse_bound(args.since) if args.since else ""
    until = parse_bound(args.until, end=True) if args.until else ""
    if since and until and since > until:
        raise DoubleAgentError("--since %s is after --until %s" % (since, until))
    flags = re.IGNORECASE if args.ignore_case else 0
    patterns = []
    for expression in args.match:
        try:
            patterns.append(re.compile(expression, flags))
        except re.error as error:
            raise DoubleAgentError("--match %r: %s" % (expression, error)) from None
    return RowFilter(since, until, args.keep_undated, patterns)


def dropped_summary(deduplicated: Counter) -> str:
    """Return the text of the timeline's `dropped:` line, with the agents that had any."""
    total = sum(deduplicated.values())
    text = "%d duplicate rows from secondary sources" % total
    if total:
        text += " (%s)" % ", ".join(
            "%s %d" % (agent, deduplicated[agent])
            for agent in sorted(deduplicated)
            if deduplicated[agent]
        )
    return text


def agents_summary(
    detected: bool,
    parsed: list[str],
    unparsed: list[str],
    no_rows: list[str],
    collected_only: list[str] | None = None,
) -> str:
    """Return the text of the timeline's `agents:` line.

    Args:
        detected: Whether the input held any agent at all.
        parsed: The agents that produced rows.
        unparsed: The detected agents without a parser, a parser backlog.
        no_rows: The detected agents whose parser ran and found no rows.
        collected_only: The detected agents in `parsers.NO_TRANSCRIPTS`.
    """

    def names(agents: list[str]) -> str:
        return ", ".join(sorted(set(agents))) or "none"

    if not detected and not parsed:
        return "none were found"
    text = "parsed: %s; detected but not parsed: %s" % (names(parsed), names(unparsed))
    if collected_only:
        text += "; collected only: %s" % names(collected_only)
    if no_rows:
        text += "; parser found no rows: %s" % names(no_rows)
    return text


def project_inventory(
    rows: list[Row],
    sessions: list[SessionSummary],
    collected: list[str] | None = None,
    files: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, dict]:
    """Return the `projects` entries of inventory.json, the empty path included.

    Paths are grouped by `project_key` and keyed by the collected spelling,
    else the first seen. Each entry counts rows, sessions and turn types per
    agent and adds the file counts of `files`, the marks of `PROJECT_MARKS`
    and the repository keys; the empty path's entry (`outside_projects`) has
    only the counts and the marks. The keys and their order are listed in
    `analyzer/docs/output.md` under "inventory.json".
    """
    groups: dict[str, dict] = {}
    names: dict[str, str] = {}

    def group(path: str) -> dict:
        key = project_key(path)
        names.setdefault(key, path)
        return groups.setdefault(key, {"rows": 0, "sessions": 0, "agents": {}})

    marks: dict[str, list[SessionSummary]] = {}

    def agent_of(path: str, agent: str) -> tuple[dict, dict]:
        totals = group(path)
        agent_counts = totals["agents"].setdefault(
            agent, {"rows": 0, "sessions": 0, "turn_types": {}}
        )
        return totals, agent_counts

    # Collected spellings first, so they name their groups.
    for path in collected or []:
        if path:
            group(path)
    collected_keys = set(groups)
    on_disk_by_key: dict[str, dict] = {}
    for path, file_counts in (files or {}).items():
        merged = on_disk_by_key.setdefault(
            project_key(path), {"agents": {}, "shared_files": 0, "remotes": [], "head": ""}
        )
        merged["shared_files"] += file_counts["shared_files"]
        merged["remotes"] = merged["remotes"] or file_counts.get("remotes", [])
        merged["head"] = merged["head"] or file_counts.get("head", "")
        for agent, counts in file_counts["agents"].items():
            agent_files = merged["agents"].setdefault(agent, {"files": 0, "bytes": 0})
            agent_files["files"] += counts["files"]
            agent_files["bytes"] += counts["bytes"]
    for row in rows:
        totals, agent_counts = agent_of(row.project_path, row.agent)
        totals["rows"] += 1
        agent_counts["rows"] += 1
        agent_counts["turn_types"][row.turn_type] = (
            agent_counts["turn_types"].get(row.turn_type, 0) + 1
        )
    for session in sessions:
        totals, agent_counts = agent_of(session.project_path, session.agent)
        totals["sessions"] += 1
        agent_counts["sessions"] += 1
        marks.setdefault(project_key(session.project_path), []).append(session)
    for path, file_counts in (files or {}).items():
        if path:
            for agent in file_counts["agents"]:
                agent_of(path, agent)
    recorded = recorded_remotes(rows, sessions)
    out: dict[str, dict] = {}
    for key in sorted(groups, key=names.__getitem__):
        totals, path = groups[key], names[key]
        empty_disk = {"agents": {}, "shared_files": 0, "remotes": [], "head": ""}
        on_disk = on_disk_by_key.get(key, empty_disk) if path else None
        agents = {}
        for name in sorted(totals["agents"]):
            agent_counts = totals["agents"][name]
            agent_counts["turn_types"] = dict(sorted(agent_counts["turn_types"].items()))
            if on_disk is not None:
                counts = on_disk["agents"].get(name, {"files": 0, "bytes": 0})
                agent_counts["files"], agent_counts["bytes"] = counts["files"], counts["bytes"]
            agents[name] = agent_counts
        if on_disk is None:
            out[path] = {"rows": totals["rows"], "sessions": totals["sessions"], "agents": agents}
        else:
            out[path] = {
                "status": "collected" if key in collected_keys else "referenced",
                "rows": totals["rows"],
                "sessions": totals["sessions"],
                "agents": agents,
                "shared_files": on_disk["shared_files"],
            }
        for mark in PROJECT_MARKS:
            out[path][mark[0]] = project_mark(marks.get(key, []), mark, set(agents))
        if on_disk is not None:
            out[path]["remotes"] = on_disk["remotes"] if key in collected_keys else []
            out[path]["head"] = on_disk["head"] if key in collected_keys else ""
            out[path]["recorded_remotes"] = sorted(recorded.get(key, ()))
    return out


def recorded_remotes(rows: list[Row], sessions: list[SessionSummary]) -> dict[str, set[str]]:
    """Return the URLs of the `git remote:` rows by `project_key`.

    A row with a session is counted under its session's project, any other
    row under its own `project_path`.
    """
    projects = {
        (session.host, session.user, session.agent, session.session_id): session.project_path
        for session in sessions
    }
    out: dict[str, set[str]] = {}
    for row in rows:
        if row.turn_type != "system" or not row.text.startswith(GIT_REMOTE_PREFIX):
            continue
        url = row.text[len(GIT_REMOTE_PREFIX) :]
        if not url:
            continue
        path = projects.get((row.host, row.user, row.agent, row.session_id), row.project_path)
        out.setdefault(project_key(path), set()).add(url)
    return out


def project_mark(sessions: list[SessionSummary], mark: tuple, agents: set[str]) -> str:
    """Return a project's mark, a row of `PROJECT_MARKS`, from its sessions.

    The full label ("yes", or "remote" for origin) when every session has the
    full value, the some label ("partial", "mixed") when some count, the none
    label ("no", "local") when none does and one of `agents` records the mark,
    else `""`, as for a project with no session.
    """
    attribute, full, hits, labels, mark_agents = mark
    values = [getattr(session, attribute) for session in sessions]
    if not values:
        return ""
    if all(value == full for value in values):
        return labels[0]
    if any(value in hits for value in values):
        return labels[1]
    return labels[2] if mark_agents & agents else ""


def collected_projects(collection: Collection) -> list[str]:
    """Return the project directories the input holds, as paths on the source host.

    They come from collection.json `projects` and the homes marked `project`,
    each in `canonical_project_path` form, sorted and de-duplicated.
    """
    summary = collection.summary or {}
    listed = summary.get("projects")
    paths = {str(path) for path in (listed if isinstance(listed, list) else []) if path}
    paths.update(home.original for home in collection.homes if home.project and home.original)
    return sorted({canonical_project_path(strip_image_root(path, summary)) for path in paths})


def scratch_keys(
    collection: Collection, rows: list[Row], catalog: catalog_mod.Catalog | None = None
) -> set[str]:
    """Return the `project_key` of every project path that is a scratch directory.

    A scratch directory is a working directory that belongs to the agent
    rather than the user; inventory.json lists it under `scratch_directories`.
    A path is one when a parser's `scratch directory:` row names it, or when a
    home catalog entry claims it in one of the input's homes
    (`home_scratch_key`) or a project catalog entry claims a directory above
    it inside a project (`project_scratch_key`).
    """
    keys = {
        project_key(row.project_path)
        for row in rows
        if row.turn_type == "system" and row.project_path and row.text.startswith(SCRATCH_PREFIX)
    }
    catalog = catalog or catalog_mod.load()
    summary = collection.summary or {}
    homes = {
        strip_image_root(home.original, summary)
        for home in collection.homes
        if home.original and not home.project
    }
    paths = [row.project_path for row in rows] + collected_projects(collection)
    for key in {project_key(path) for path in paths if path} - keys:
        if project_scratch_key(key, catalog) or any(
            home_scratch_key(key, home, catalog) for home in homes
        ):
            keys.add(key)
    return keys


def project_scratch_key(key: str, catalog: catalog_mod.Catalog) -> bool:
    r"""Return whether a `project_key` lies under a directory a project catalog entry names.

    The entry must sit inside a project: at least one segment before it and
    one after, so `/srv/p/.kilo/worktrees/x` is claimed while `/srv/p/.kilo`
    is not. Entries of agent `project` are skipped. A Windows path is split on
    backslashes and matched without regard to case.
    """
    windows = is_windows_path(key)
    flags = re.IGNORECASE if windows else 0
    parts = [part for part in key.split("\\" if windows else "/") if part]
    for entry in catalog.project_entries:
        if entry.agent == PROJECT_AGENT:
            continue
        depth = len(entry.segments)
        for i in range(1, len(parts) - depth):
            pairs = zip(entry.regexes, parts[i : i + depth], strict=True)
            if all(re.fullmatch(pattern.pattern, part, flags) for pattern, part in pairs):
                return True
    return False


def home_scratch_key(key: str, home: str, catalog: catalog_mod.Catalog) -> bool:
    r"""Return whether a `project_key` lies in or under a directory a home entry claims.

    `home` is a home's path on the source host; `Catalog.claims_home_path`
    must claim the rest of the key. A Windows home (`C:\Users\a`) is compared
    in `project_key` form and matched without regard to case.
    """
    windows = is_windows_path(home)
    separator = "\\" if windows else "/"
    home_key = project_key(home)
    prefix = home_key if home_key.endswith(separator) else home_key + separator
    if key != home_key and not key.startswith(prefix):
        return False
    return bool(catalog.claims_home_path(key[len(home_key) :], windows))


def project_files(
    collection: Collection, problems: list[str] | None = None
) -> dict[str, ProjectFiles]:
    """Return `project_agents` keyed as `collected_projects` keys its paths.

    Directories that map to one path are summed. Each value has `agents`
    (`files` and `bytes`), `shared_files`, and the first `remotes` and `head`
    of `gitmeta.project_git`; a repository file it cannot read is added to
    `problems`.
    """
    summary = collection.summary or {}
    git = gitmeta.project_git(collection.artifacts, problems)
    merged: dict[str, ProjectFiles] = {}
    for path, project in project_agents(collection).items():
        key = canonical_project_path(strip_image_root(path, summary))
        merged_entry = merged.setdefault(
            key, {"agents": {}, "shared_files": 0, "remotes": [], "head": ""}
        )
        merged_entry["shared_files"] += project["shared_files"]
        if path in git:
            merged_entry["remotes"] = merged_entry["remotes"] or git[path]["remotes"]
            merged_entry["head"] = merged_entry["head"] or git[path]["head"]
        for agent, counts in project["agents"].items():
            agent_files = merged_entry["agents"].setdefault(agent, {"files": 0, "bytes": 0})
            agent_files["files"] += counts["files"]
            agent_files["bytes"] += counts["bytes"]
    return merged


def strip_image_root(path: str, summary: dict) -> str:
    """Return a collected path as the imaged host saw it.

    In image mode the collector records `-r <root>/srv/proj` where the
    transcripts say `/srv/proj`. A path outside the root is returned
    unchanged.
    """
    root = str(summary.get("root") or "")
    if summary.get("mode") != "image" or root in ("", "/", "\\"):
        return path
    root = root.rstrip("/\\")
    if path.startswith(root) and path[len(root) : len(root) + 1] in ("/", "\\"):
        return path[len(root) :]
    return path


def synced_homes(homes: list[HomeEntry], sessions: list[SessionSummary]) -> list[dict]:
    """Return the `homes` array of inventory.json: `home_agents` with session counts.

    Each agent object ends with `synced_sessions`, `relayed_sessions`,
    `remote_sessions` and `recovered_sessions`, the user's sessions of that
    agent with that mark.
    """
    synced = Counter(
        (session.user, session.agent) for session in sessions if session.synced == "yes"
    )
    relayed = Counter(
        (session.user, session.agent) for session in sessions if session.relayed == "yes"
    )
    remote = Counter(
        (session.user, session.agent) for session in sessions if session.origin == "remote"
    )
    recovered = Counter(
        (session.user, session.agent) for session in sessions if session.recovered in RECOVERED
    )
    return [
        {
            **home,
            "agents": [
                {
                    **agent,
                    "synced_sessions": synced[(home["user"], agent["agent"])],
                    "relayed_sessions": relayed[(home["user"], agent["agent"])],
                    "remote_sessions": remote[(home["user"], agent["agent"])],
                    "recovered_sessions": recovered[(home["user"], agent["agent"])],
                }
                for agent in home["agents"]
            ],
        }
        for home in homes
    ]


def cmd_timeline(args: argparse.Namespace, collection: Collection) -> int:
    """Write timeline.jsonl, sessions.jsonl and inventory.json, and print the summary."""
    opts = Options(include_thinking=args.include_thinking)
    row_filter: RowFilter = args.row_filter
    args.output.mkdir(parents=True, exist_ok=True)
    rows, counts, problems, deduplicated = collect_rows(collection, opts, args.agent)
    parsed_agents = sorted({agent for agent, _ in counts})
    if row_filter.active:
        rows = row_filter.apply(rows)
        counts = Counter((row.agent, row.turn_type) for row in rows)
    sessions = summarise(rows, SYNC_AGENTS, RELAY_AGENTS, ORIGIN_AGENTS, SECONDARY_AGENTS)
    timeline = args.output / "timeline.jsonl"
    sessions_path = args.output / "sessions.jsonl"
    write_jsonl(timeline, rows)
    write_jsonl(sessions_path, sessions)
    detect = detect_object(collection)
    # Before the problem: lines, since a repository file it cannot read is one.
    files = project_files(collection, problems)
    print("input:     %s (%s)" % (collection.source, collection.kind))
    print("host:      %s" % (collection.host or "(unknown)"))
    for note in collection.notes:
        print("note:      %s" % note)
    for problem in problems:
        print("problem:   %s" % problem)
    if row_filter.since or row_filter.until:
        print(
            "window:    %s to %s%s"
            % (
                row_filter.since or "(start)",
                row_filter.until or "(end)",
                ", undated rows kept" if row_filter.keep_undated else "",
            )
        )
    if row_filter.patterns:
        print(
            "match:     %s%s"
            % (
                " | ".join(pattern.pattern for pattern in row_filter.patterns),
                " (ignore case)" if args.ignore_case else "",
            )
        )
    if row_filter.active:
        print(
            "filtered:  %d outside the window, %d without a timestamp, %d not matching"
            % (row_filter.dropped_window, row_filter.dropped_undated, row_filter.dropped_match)
        )
    print("dropped:   " + dropped_summary(deduplicated))
    # The agents outside and inside project directories. Shared project
    # files (agent `project`) are routed to every parser, so they are never
    # "detected but not parsed" in their own right.
    agents = [
        entry
        for home in detect["homes"]
        for entry in home["agents"]
        if entry["agent"] != PROJECT_AGENT
    ]
    agents += [entry for project in detect["projects"] for entry in project["agents"]]
    # Agents with no parser are a parser backlog, unless their files hold
    # nothing to parse (NO_TRANSCRIPTS), which are collected only.
    unparsed = [
        entry["agent"]
        for entry in agents
        if not entry["parser"] and entry["agent"] not in NO_TRANSCRIPTS
    ]
    collected_only = [
        entry["agent"]
        for entry in agents
        if not entry["parser"] and entry["agent"] in NO_TRANSCRIPTS
    ]
    # An agent left out by --agent was not parsed, so it did not come up empty.
    no_rows = [
        entry["agent"]
        for entry in agents
        if entry["parser"]
        and entry["agent"] not in parsed_agents
        and (not args.agent or entry["agent"] in args.agent)
    ]
    groups = project_inventory(rows, sessions, collected_projects(collection), files)
    scratch = scratch_keys(collection, rows)
    synced = sum(1 for session in sessions if session.synced == "yes")
    relayed = sum(1 for session in sessions if session.relayed == "yes")
    remote = sum(1 for session in sessions if session.origin == "remote")
    recovered = sum(1 for session in sessions if session.recovered in RECOVERED)
    empty: dict = {"rows": 0, "sessions": 0, "agents": {}}
    empty.update({mark[0]: "" for mark in PROJECT_MARKS})
    inventory_path = args.output / "inventory.json"
    with open(inventory_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "doubleagent_version": VERSION,
                **{key: detect[key] for key in ("input", "kind", "host", "notes")},
                "problems": problems,
                "rows": len(rows),
                "sessions": len(sessions),
                "parsed": parsed_agents,
                "detected_not_parsed": sorted(set(unparsed)),
                "no_rows": sorted(set(no_rows)),
                "homes": synced_homes(detect["homes"], sessions),
                "projects": {
                    key: value
                    for key, value in groups.items()
                    if key and project_key(key) not in scratch
                },
                "outside_projects": groups.get("", empty),
                "deduplicated": {
                    key: deduplicated[key] for key in sorted(deduplicated) if deduplicated[key]
                },
                "collected_only": sorted(set(collected_only)),
                "synced_sessions": synced,
                "relayed_sessions": relayed,
                "remote_sessions": remote,
                "recovered_sessions": recovered,
                "scratch_directories": {
                    key: value
                    for key, value in groups.items()
                    if key and project_key(key) in scratch
                },
            },
            handle,
            indent=2,
        )
    print(
        "agents:    "
        + agents_summary(
            bool(agents), parsed_agents, unparsed, sorted(set(no_rows)), collected_only
        )
    )
    print("rows:      %d in %s" % (len(rows), timeline))
    for (agent, turn_type), count in sorted(counts.items()):
        print("           %-14s %-12s %d" % (agent, turn_type, count))
    marks = ["%d synced" % synced] if synced else []
    marks += ["%d relayed" % relayed] if relayed else []
    marks += ["%d remote" % remote] if remote else []
    marks += ["%d recovered" % recovered] if recovered else []
    print(
        "sessions:  %d in %s%s"
        % (len(sessions), sessions_path, " (%s)" % ", ".join(marks) if marks else "")
    )
    print(
        "inventory: %s (homes, projects, scratch directories, counts per agent, problems)"
        % inventory_path
    )
    return 0 if rows else 1
