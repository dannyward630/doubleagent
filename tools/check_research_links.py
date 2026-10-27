#!/usr/bin/env python3
"""Verify every GitHub blob link in the research documents.

Each citation in research/*.md links to a file and line range at the commit
the document reviewed. This checks that the path exists at that commit and
that the line range lies inside the file.
It is the first review gate for a research round: a citation that does not
resolve, or a claim with no citation, is unverified.

Usage: tools/check_research_links.py [--repos DIR] [FILE...]

With --repos, a checkout under DIR whose HEAD is the cited commit is used
instead of the network (name the checkout after the repository, e.g.
DIR/gemini-cli). Otherwise each file is fetched once from
raw.githubusercontent.com. Exit status 1 when any link fails.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAT = re.compile(
    r"https://github\.com/([^/\s)]+/[^/\s)]+)/blob/([0-9a-f]{40})/([^\s)#]+)"
    r"(?:#L(\d+)(?:-L(\d+))?)?"
)


def line_count_local(repos: pathlib.Path, repo: str, sha: str, path: str):
    name = repo.split("/")[1]
    checkout = repos / name
    if not (checkout / ".git").exists():
        return None
    head = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    if head != sha:
        return None
    # A link may percent-encode characters such as the parentheses in a Next.js
    # route group directory; the checkout holds the decoded name.
    file_path = checkout / urllib.parse.unquote(path)
    if not file_path.is_file():
        return -1
    with open(file_path, "rb") as handle:
        return sum(1 for _ in handle)


def line_count_remote(repo: str, sha: str, path: str):
    url = "https://raw.githubusercontent.com/%s/%s/%s" % (repo, sha, path)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
    except urllib.error.HTTPError as error:
        return -1 if error.code == 404 else None
    except urllib.error.URLError:
        return None
    return data.count(b"\n") + (0 if data.endswith(b"\n") or not data else 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--repos", type=pathlib.Path, help="directory of local checkouts")
    parser.add_argument("files", nargs="*", type=lambda argument: pathlib.Path(argument).resolve())
    args = parser.parse_args()
    files = args.files or sorted((ROOT / "research").glob("*.md"))
    cache = {}
    total = bad = 0
    for document in files:
        links = 0
        for match in PAT.finditer(document.read_text(encoding="utf-8")):
            repo, sha, path, first_line, last_line = match.groups()
            total += 1
            links += 1
            key = (repo, sha, path)
            if key not in cache:
                count = None
                if args.repos:
                    count = line_count_local(args.repos, repo, sha, path)
                if count is None:
                    count = line_count_remote(repo, sha, path)
                cache[key] = count
            count = cache[key]
            rel = document.relative_to(ROOT)
            if count is None:
                print("%s: could not fetch %s@%s/%s" % (rel, repo, sha[:8], path))
                bad += 1
            elif count < 0:
                print("%s: missing file %s@%s/%s" % (rel, repo, sha[:8], path))
                bad += 1
            elif first_line:
                start, end = int(first_line), int(last_line or first_line)
                if start < 1 or end > count or end < start:
                    print(
                        "%s: L%s-L%s outside %s (%d lines)"
                        % (rel, first_line, last_line or first_line, path, count)
                    )
                    bad += 1
        if links:
            print("%4d %s" % (links, document.relative_to(ROOT)))
    print("total links %d, problems %d" % (total, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
