"""Command line: detect agents in an input, or write the JSONL timeline."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

from . import VERSION, gitmeta
from . import catalog as catalog_mod
from . import inventory as inventory_mod
from .dedup import deduplicate
from .filters import FORMS_HELP, RowFilter, parse_bound
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


def build_parser() -> argparse.ArgumentParser:
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
    args = build_parser().parse_args(argv)
    if args.command == "catalog":
        return cmd_catalog(args)
    if args.command == "inventory":
        return cmd_inventory(args)
    if args.command == "timeline":
        # Checked before an archive is extracted, so a typo fails at once.
        try:
            args.row_filter = build_filter(args)
        except ValueError as error:
            print("error: %s" % error, file=sys.stderr)
            return 2
    catalog = catalog_mod.load()
    try:
        collection = open_input(args.input, catalog, work_dir=args.work_dir, host=args.host)
    except OSError as error:
        print("error: %s" % describe_error(args.input, error), file=sys.stderr)
        return 2
    except ValueError as error:
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
    try:
        files = inventory_mod.input_files(args.input)
    except OSError as error:
        print("error: %s" % describe_error("", error), file=sys.stderr)
        return 2
    except ValueError as error:
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


def detect_table(collection: Collection, include_projects: bool = True) -> list[dict]:
    """One row per user, home and agent, in the order the first file was
    met: `user`, `home`, `agent`, `files`, `bytes` (manifest `size`, or the
    size on disk in loose mode), `parser`, `inferred`. With
    `include_projects` false, artifacts in a project directory (a home
    marked `project`) are left out: that is the first table of `detect`,
    whose rows keep this order rather than the per-home grouping of
    `home_agents`."""
    parsers = by_agent()
    rows: dict[tuple[str, str, str], dict] = OrderedDict()
    for artifact in collection.artifacts:
        if artifact.home.project and not include_projects:
            continue
        key = (artifact.home.user, artifact.home.original, artifact.agent)
        row = rows.get(key)
        if row is None:
            row = rows[key] = {
                "user": artifact.home.user,
                "home": artifact.home.original or str(artifact.home.disk_path),
                "agent": artifact.agent,
                "files": 0,
                "bytes": 0,
                "parser": artifact.agent in parsers,
                "inferred": artifact.home.inferred,
            }
        row["files"] += 1
        row["bytes"] += artifact_bytes(artifact)
    return list(rows.values())


def artifact_bytes(artifact) -> int:
    """The size of one artifact: the manifest `size` when the input has a
    manifest, else the file's `lstat` size (0 when it cannot be read)."""
    if artifact.manifest is not None:
        return int(artifact.manifest.get("size") or 0)
    try:
        return artifact.disk_path.lstat().st_size
    except OSError:
        return 0


def home_agents(collection: Collection) -> list[dict]:
    """The `homes` array of `detect --json` and inventory.json: one object
    per user home or Docker volume (a home not marked `project`), in the
    order its first collected row was met, with the keys `user`, `home`
    (`home.original`: the manifest `home`, or in loose mode the path
    relative to the input root with a leading `/`, `""` when the root is
    the home), `inferred` and `agents`. `agents` is sorted by agent, one
    object of `agent`, `files`, `bytes` (as in `detect_table`) and
    `parser` per agent with files in that home; a home whose files were
    all missing from the collection has an empty array."""
    parsers = by_agent()
    counts: dict[int, dict[str, dict]] = {}
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
                {"agent": agent, **agent_counts, "parser": agent in parsers}
                for agent, agent_counts in sorted(counts.get(id(home), {}).items())
            ],
        }
        for home in collection.homes
        if not home.project
    ]


def project_agents(collection: Collection) -> dict[str, dict]:
    """The agents used on each project directory the input holds, keyed by
    the directory's path on the source host (`home.original`, which in image
    mode still carries the `-r` root) and sorted by it. Only artifacts whose
    home is marked `project` count, so loose input yields an empty dict.

    Each value has `users` (sorted distinct users whose rows name the
    directory), `agents` (keyed by agent, sorted: `files` and `bytes` of
    that agent's files in the directory), and `shared_files` and
    `shared_bytes`, the files with agent `project` (those no single agent
    owns, such as AGENTS.md), which is not an agent and so never a key of
    `agents`. Bytes are the manifest `size`, as in `detect_table`."""
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


def detect_object(collection: Collection) -> dict:
    """The keys `detect --json` and inventory.json share, in order: `input`,
    `kind`, `host`, `notes`, `homes` (`home_agents`) and `projects` (one
    object per project directory from `project_agents`, its `agents` an
    array of `agent`, `files`, `bytes`, `parser`, as in `homes`, and its
    last two keys `remotes` and `head` from `gitmeta.project_git`, `[]`
    and `""` without the repository files; one the analyzer cannot read is
    added to `col.problems`). The callers add `problems`, and
    `detect --json --files` adds `files`."""
    parsers = by_agent()
    git = gitmeta.project_git(collection.artifacts, collection.problems)
    projects = [
        {
            "path": path,
            "users": project["users"],
            "agents": [
                {"agent": agent, **counts, "parser": agent in parsers}
                for agent, counts in project["agents"].items()
            ],
            "shared_files": project["shared_files"],
            "shared_bytes": project["shared_bytes"],
            "remotes": git.get(path, {}).get("remotes", []),
            "head": git.get(path, {}).get("head", ""),
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


def print_project_table(projects: list[dict]) -> None:
    """The second table of `detect`: one line per agent of each project,
    then a `(shared)` line when the project holds shared files, then a
    `remotes:` line (`remotes_text`) when its repository has remotes; the
    path and users appear on the project's first line only."""
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


def remotes_text(remotes: list[dict]) -> str:
    """`<name> <url> ...` per remote, its `urls` joined by a space, then
    ` (push <pushurl> ...)` when it sets `pushurls`; remotes joined with
    `, `."""
    parts = []
    for remote in remotes:
        text = " ".join([remote["name"], *remote["urls"]])
        if remote["pushurls"]:
            text += " (push %s)" % " ".join(remote["pushurls"])
        parts.append(text)
    return ", ".join(parts)


def cmd_detect(args: argparse.Namespace, collection: Collection) -> int:
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
    """Parse every artifact into timeline rows. Returns the rows, sorted;
    their counts per (agent, turn_type); the problems; and the rows dropped
    per agent because a secondary source repeated a primary store's event
    (`dedup.deduplicate`, issue 122)."""
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
                    # store the path came from (issue 112).
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
    """One JSON object on one line, keys in schema order. Non-ASCII text is
    written as UTF-8 rather than escaped, so grep finds it as typed. U+2028
    and U+2029 are escaped because some line readers (Python's
    str.splitlines among them) split on them, and a record holding a lone
    surrogate, which UTF-8 cannot encode, falls back to ASCII escapes."""
    text = json.dumps(record, ensure_ascii=False, separators=JSONL_SEPARATORS)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return json.dumps(record, separators=JSONL_SEPARATORS)
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def write_jsonl(path: Path, rows) -> None:
    with open(path, "w", newline="\n", encoding="utf-8") as handle:
        for row in rows:
            handle.write(jsonl_line(row.as_dict()))
            handle.write("\n")


def build_filter(args: argparse.Namespace) -> RowFilter:
    """The row filter from --since, --until, --keep-undated and --match.
    Raises ValueError with a message for the user on a bad value."""
    since = parse_bound(args.since) if args.since else ""
    until = parse_bound(args.until, end=True) if args.until else ""
    if since and until and since > until:
        raise ValueError("--since %s is after --until %s" % (since, until))
    flags = re.IGNORECASE if args.ignore_case else 0
    patterns = []
    for expression in args.match:
        try:
            patterns.append(re.compile(expression, flags))
        except re.error as error:
            raise ValueError("--match %r: %s" % (expression, error)) from None
    return RowFilter(since, until, args.keep_undated, patterns)


def dropped_summary(deduplicated: Counter) -> str:
    """The text of the timeline's `dropped:` line: the secondary-source rows
    `dedup.deduplicate` dropped, with the agents that had any, by name."""
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
    """The text of the timeline's `agents:` line. `detected` says whether the
    input held any agent at all; `parsed` are the agents that produced rows,
    `unparsed` the detected agents with no parser that are a parser backlog,
    `collected_only` the detected agents with no parser whose files hold
    nothing to parse (`parsers.NO_TRANSCRIPTS`), and `no_rows` the detected
    agents whose parser ran and produced no rows. Each list is sorted and
    reads `none` when empty; `collected_only` and `no_rows` are shown only
    when they have an entry."""

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
    files: dict[str, dict] | None = None,
) -> dict[str, dict]:
    """Counts per project, the empty path included: rows and sessions in
    total, and per agent the rows, sessions and rows by `turn_type`. A
    session is counted under its summary's project, the first non-empty
    `project_path` among its rows.

    Paths are grouped by `project_key`, so the spellings of one Windows
    folder that differ only in case are one project; any other path is
    compared exactly as recorded. A group is keyed by the spelling of the
    collected project it matches, else by the first spelling seen, in the
    rows (timeline order), then the sessions, then `files`; the output is
    sorted by that key.

    Each non-empty key is a project entry with the keys `status`, `rows`,
    `sessions`, `agents`, `shared_files`, then the four marks of
    `PROJECT_MARKS` (`synced`, `relayed`, `origin`, `recovered`), in that
    order. `status` is
    `collected` when the group matches one of `collected` (the project
    directories the input holds), else `referenced` (named only by rows); a
    collected project no row names is listed with zero counts. `files` maps
    a project path to `project_files` output, looked up through
    `project_key` (the counts of paths with one key are added); each agent
    of a project entry gets `files` and `bytes` after `turn_types` from it
    (0 when absent), an agent with files and no rows is listed with zero
    counts, and `shared_files` is the project's files with agent `project`.
    Each mark is `project_mark` of the project's sessions. After the marks
    come `remotes` and `head`, the repository's (`files` entry, `[]` and
    `""` when it has none, so always for a `referenced` project), and
    `recorded_remotes`, the sorted distinct URLs of the `git remote:` rows
    (`GIT_REMOTE_PREFIX`) among `rows`: a row of a session is counted under
    the session's project, a row without a session under its own
    `project_path`. The empty path's entry (`outside_projects`) has no
    `status`, no `shared_files`, no file counts and none of the three
    repository keys: `rows`, `sessions`, `agents`, then the same marks over
    its sessions."""
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
    """The URLs of the `git remote:` rows of `rows` by `project_key`: a row
    with a session id under its session's project (the summary's
    `project_path`, which `sessions` holds), a row without one, or of a
    session `sessions` does not hold, under its own `project_path`."""
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
    """A project's mark (`PROJECT_MARKS` row `mark`) from its `sessions`:
    the full label ("yes", or "remote" for origin) when every session has
    the full value, the some label ("partial", "mixed") when some have a
    counted value, the none label ("no", "local") when none has and one of
    the project's `agents` records the mark, "" otherwise and for a project
    with no session."""
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
    """The project directories the input holds, as their paths on the source
    host: collection.json `projects`, even one none of whose files were
    collected, and the homes marked `project` (which adds the bases of rows
    with agent `project` in a collection whose collection.json is missing),
    each in `canonical_project_path` form, sorted and de-duplicated."""
    summary = collection.summary or {}
    listed = summary.get("projects")
    paths = {str(path) for path in (listed if isinstance(listed, list) else []) if path}
    paths.update(home.original for home in collection.homes if home.project and home.original)
    return sorted({canonical_project_path(strip_image_root(path, summary)) for path in paths})


def scratch_keys(
    collection: Collection, rows: list[Row], catalog: catalog_mod.Catalog | None = None
) -> set[str]:
    """The `project_key` of every path inventory.json would list as a
    project that is a scratch directory, a working directory that belongs
    to the agent rather than to the user (issue 149); inventory.json lists
    these under `scratch_directories` instead of `projects`. A path is one
    when either holds:

    1. A parser says so: a `system` row whose text starts with
       `SCRATCH_PREFIX` (`scratch directory:`) names it in its own
       `project_path`.
    2. The catalog says so: the path, a `project_path` of `rows` or a
       project directory the input holds (`collected_projects`), is in
       or under a directory that a home catalog entry (of `cat`, the
       bundled catalog when None) names, in one of the input's homes that
       is not a project directory and has a known path on the source host
       (`home_scratch_key`), or it is under a directory that one agent's
       project catalog entry names inside another directory, as an
       agent's own worktree `<project>/.claude/worktrees/<name>` is
       (`project_scratch_key`, issue 227).

    The collector's project list only adds paths to test: a scratch
    directory the collector collected project files from stays one."""
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
    r"""Whether `key`, a `project_key`, lies under a directory that a
    project catalog entry of one agent names inside a project:
    `<project>/<entry>/<more>`, with at least one segment before the entry
    (the project) and at least one after it, so `/srv/p/.kilo/worktrees/x`
    is under the `kilo-code` entry `.kilo` of the project `/srv/p`, while
    `/srv/p/.kilo` itself and `/srv/p/src` are not. The entries of the
    pseudo-agent `project` (`AGENTS.md`, `.agents`), which belong to no
    single agent, are skipped. Unlike `home_scratch_key` this needs no
    home path, so it applies in loose mode too. A Windows path is split on
    backslashes and its segments are matched without regard to case."""
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
    r"""Whether `key`, a `project_key`, lies in or under a directory that a
    home catalog entry names in `home`, a home's path on the source host:
    `key` must be the home or start with it and a separator, and
    `Catalog.claims_home_path` must claim the rest. A Windows home
    (`C:\Users\a`) is compared in `project_key` form, lower case with
    backslashes, and its segments are matched without regard to case; any
    other home is compared exactly."""
    windows = is_windows_path(home)
    separator = "\\" if windows else "/"
    home_key = project_key(home)
    prefix = home_key if home_key.endswith(separator) else home_key + separator
    if key != home_key and not key.startswith(prefix):
        return False
    return bool(catalog.claims_home_path(key[len(home_key) :], windows))


def project_files(collection: Collection, problems: list[str] | None = None) -> dict[str, dict]:
    """`project_agents` keyed as `collected_projects` keys its paths, with
    the image root stripped and in `canonical_project_path` form, and summed
    when two directories map to one path: per path `agents` (agent to
    `files` and `bytes`), `shared_files`, and the `remotes` and `head` of
    `gitmeta.project_git` (the first directory's that has them; a
    repository file it cannot read is added to `problems`)."""
    summary = collection.summary or {}
    git = gitmeta.project_git(collection.artifacts, problems)
    merged: dict[str, dict] = {}
    for path, project in project_agents(collection).items():
        key = canonical_project_path(strip_image_root(path, summary))
        merged_entry = merged.setdefault(
            key, {"agents": {}, "shared_files": 0, "remotes": [], "head": ""}
        )
        merged_entry["shared_files"] += project["shared_files"]
        repository = git.get(path, {})
        merged_entry["remotes"] = merged_entry["remotes"] or repository.get("remotes", [])
        merged_entry["head"] = merged_entry["head"] or repository.get("head", "")
        for agent, counts in project["agents"].items():
            agent_files = merged_entry["agents"].setdefault(agent, {"files": 0, "bytes": 0})
            agent_files["files"] += counts["files"]
            agent_files["bytes"] += counts["bytes"]
    return merged


def strip_image_root(path: str, summary: dict) -> str:
    """A collected path as the imaged host saw it: in image mode the
    collector records `-r <root>/srv/proj`, while the transcripts on that
    host say `/srv/proj`. Paths outside the root are returned unchanged."""
    root = str(summary.get("root") or "")
    if summary.get("mode") != "image" or root in ("", "/", "\\"):
        return path
    root = root.rstrip("/\\")
    if path.startswith(root) and path[len(root) : len(root) + 1] in ("/", "\\"):
        return path[len(root) :]
    return path


def synced_homes(homes: list[dict], sessions: list[SessionSummary]) -> list[dict]:
    """The `homes` array of inventory.json: `homes` (`home_agents`) with four
    last keys in each agent object, `synced_sessions`, `relayed_sessions`,
    `remote_sessions` and `recovered_sessions`, the number of the sessions
    of that user and agent whose `synced` (issue 151) or `relayed` (issue
    153) is "yes", whose `origin` is "remote" (issue 153), or whose
    `recovered` is "yes" or "partial"."""
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
