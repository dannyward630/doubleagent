"""Merge the collectors' inventory output into one fleet CSV.

The input is the JSON Lines a collector prints with --inventory (sh) or
-Inventory (PowerShell), one saved stdout per host; the output is one CSV row
per host and agent, and a per-agent rollup.

Record shapes, from collect-agent-artifacts.sh and Collect-AgentArtifacts.ps1
(collector 1.6.0):

  {"type":"host","host":...,"collector":...,"mode":...,"at":...,
   "users_scanned":N,"users_unreadable":N,"docker_volumes":N}
  {"type":"agent","host":...,"user":...,"agent":...,"files":N,"bytes":N,
   "first":...,"last":...,"projects":N,"evidence":...}

A host line opens a run; the agent lines after it belong to that run until
the next host line. Anything else on a line (console banners, prompts, a
PowerShell error record) is junk: skipped and counted, never fatal.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Iterable
from pathlib import Path

from .timeutil import to_utc

DEFAULT_NAME = "fleet-inventory.csv"

INVENTORY_COLUMNS = [
    "host",
    "collector",
    "mode",
    "at",
    "user",
    "agent",
    "files",
    "bytes",
    "first",
    "last",
    "projects",
    "evidence",
]

HOST_FIELDS = ("host", "collector", "mode", "at")
AGENT_FIELDS = ("user", "agent", "files", "bytes", "first", "last", "projects", "evidence")
TIME_FIELDS = ("at", "first", "last")


def input_files(paths: Iterable[Path]) -> list[Path]:
    """Return each input file, and the regular files of each input directory.

    A directory is not read recursively, its files are sorted by name, and
    symlinks are not followed.

    Raises:
        OSError: An input cannot be stat'ed or listed.
        ValueError: An input is a symlink, or neither a file nor a directory.
    """
    out: list[Path] = []
    for path in paths:
        # lstat, not exists(): exists() hides the reason, and from Python
        # 3.14 returns False for a permission error.
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode):
            raise ValueError("%s is a symlink; give its target" % path)
        if stat.S_ISDIR(mode):
            with os.scandir(path) as entries:
                out.extend(
                    sorted(
                        Path(entry.path)
                        for entry in entries
                        if entry.is_file(follow_symlinks=False)
                    )
                )
        elif stat.S_ISREG(mode):
            out.append(path)
        else:
            raise ValueError("%s is neither a regular file nor a directory" % path)
    return out


def _cell(field: str, value) -> str:
    if value is None:
        return ""
    if field in TIME_FIELDS:
        return to_utc(value)
    return str(value)


def _record(line: str) -> dict | None:
    line = line.strip().lstrip("﻿")
    if not line.startswith("{"):
        return None
    try:
        record = json.loads(line)
    except ValueError:
        return None
    if not isinstance(record, dict) or record.get("type") not in ("host", "agent"):
        return None
    return record


def read_file(path: Path) -> tuple[list[list[str]], int]:
    """Return the CSV rows of one saved stdout and the number of junk lines skipped."""
    rows: list[list[str]] = []
    junk = 0
    host: dict[str, str] | None = None
    host_has_agents = False

    def close_host() -> None:
        if host is not None and not host_has_agents:
            rows.append([host[name] for name in HOST_FIELDS] + [""] * len(AGENT_FIELDS))

    with open(path, encoding="utf-8-sig", errors="replace") as handle:
        for line in handle:
            record = _record(line)
            if record is None:
                if line.strip():
                    junk += 1
                continue
            if record["type"] == "host":
                close_host()
                host = {name: _cell(name, record.get(name)) for name in HOST_FIELDS}
                host_has_agents = False
                continue
            if host is not None:
                head = [host[name] for name in HOST_FIELDS]
                host_has_agents = True
            else:
                # An agent line with no host line before it: its own host
                # field, and the run fields left empty.
                head = [_cell("host", record.get("host")), "", "", ""]
            rows.append(head + [_cell(name, record.get(name)) for name in AGENT_FIELDS])
    close_host()
    return rows, junk


def rollup(rows: list[list[str]]) -> list[tuple[str, int, int, str]]:
    """Return (agent, hosts, users, latest `last`) per agent.

    `users` counts distinct (host, user) pairs. The list is sorted by hosts,
    then users, descending, then by agent name.
    """
    hosts: dict[str, set] = {}
    users: dict[str, set] = {}
    latest: dict[str, str] = {}
    host_index, user_index, agent_index, last_index = (
        INVENTORY_COLUMNS.index(column) for column in ("host", "user", "agent", "last")
    )
    for row in rows:
        agent = row[agent_index]
        if not agent:
            continue
        hosts.setdefault(agent, set()).add(row[host_index])
        users.setdefault(agent, set()).add((row[host_index], row[user_index]))
        if row[last_index] > latest.get(agent, ""):
            latest[agent] = row[last_index]
        else:
            latest.setdefault(agent, "")
    out = [(agent, len(hosts[agent]), len(users[agent]), latest[agent]) for agent in hosts]
    out.sort(key=lambda entry: (-entry[1], -entry[2], entry[0]))
    return out
