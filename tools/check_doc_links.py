#!/usr/bin/env python3
"""Verify the links, section references and external references in the Markdown documents.

Every reference from one project document to another is a Markdown link with
a path relative to the citing file, and every reference to a section links to
its heading (the link rule under "Conventions" in AGENTS.md). This checks, in
every tracked Markdown file and every untracked one git does not ignore:

- each inline link `[text](target)` and reference definition `[label]: target`
  whose target has no URL scheme resolves to a file or directory that exists,
  relative to the citing file (an empty path is the citing file itself);
- when the target is a Markdown file and has a `#fragment`, the file has a
  heading whose GitHub anchor equals the fragment (lower case, characters
  other than letters, digits, spaces, hyphens and underscores removed, spaces
  to hyphens, `-1`, `-2` appended to repeated anchors);
- no `section <n>` or `sections <n>` appears, even as link text: the research
  documents' sections are named, not numbered, and a section reference links
  to the heading with the heading's name as its text;
- no `issue <n>`, `issues <n>`, `pull request <n>`, `PR <n>`, `discussion <n>`
  or `#<n>` appears except as link text, since an issue or pull request
  named in a document is a link to it, one link per issue (the link rule
  under "Conventions" in AGENTS.md); `[#<n>]`, the changelogs' reference
  link form, is not matched, and neither is a number inside a code span;
- with link targets, reference definition targets and `<autolinks>` also
  ignored, no `http://` or `https://` URL and no scheme-less host path such as
  `github.com/owner/repo` is left in the text, and no inline link has a URL or
  host path as its text, since an external source is one link whose text
  names it and whose target is the full URL;
- with the same parts ignored, no bare commit hash is left in the text: a
  lowercase hexadecimal word of 7 to 40 characters preceded by `at `,
  `commit ` or `@`, since a commit hash named in a document is a link to the
  commit, `[<short hash>](https://github.com/<owner>/<repo>/commit/<sha>)`.
  A purely decimal word is not taken for a hash, so the bundle citation form
  `<tool> <version> <platform> @<byte offset>` passes, and a 64-character
  sha256 of an artifact is longer than any match;
- in every document but AGENTS.md, CLAUDE.md and the research documents, a
  term AGENTS.md defines and uses as a term of art (`TERMS`: cell, round,
  surface, Observed bullet, listing diff, secondary source, nested entry) is
  introduced before it is relied on: the page has a heading that holds the
  term, or the term's first use is link text (pointing at where it is
  defined) or is followed by a parenthesised gloss. A plain sense listed in
  `TERM_PLAIN` (a spreadsheet's or a table's cell) is not a use, and neither
  is a word inside a link destination, a reference definition's target or
  an autolink, which the reader does not see. The term
  rule under "Conventions" in AGENTS.md is the reason: a reader who has only
  the page must not need AGENTS.md to decode a sentence;
- in AGENTS.md and CLAUDE.md alone (`NO_PROVENANCE_FILES`), no inline link
  or reference definition points at one of this repository's issues or pull
  requests (`PROVENANCE_LINK`), since those files state rules, not the
  history behind them (the rule under "Conventions" in AGENTS.md); the link
  forms the Conventions section shows sit inside code spans and are not
  matched.

Fenced code blocks and inline code spans are ignored before matching. The
documentation site (mkdocs/hooks.py) gives every heading the anchor
`heading_anchors()` returns, so a link this check accepts also works there.

Usage: tools/check_doc_links.py [FILE...]

With FILE arguments only those files are scanned. Every failure is printed as
`path:line: message`; the exit status is 1 when any check failed.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent

FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
CODE_SPAN = re.compile(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.S)
# Link text may hold one level of nested brackets; the target may be <...>
# and may be followed by a title.
INLINE_LINK = re.compile(
    r"\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\(\s*(<[^>\n]*>|[^\s()]+(?:\([^\s()]*\)[^\s()]*)*)"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)"
)
REF_DEF = re.compile(r"^ {0,3}\[[^\]]+\]:[ \t]*(<[^>\n]*>|\S+)", re.M)
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
SECTION = re.compile(r"\bsections?\s+\d+", re.I)
ISSUE = re.compile(
    r"(?<![\w/#\[-])(?:(?:issues?|pull requests?|PRs?|discussions?)\s+#?\d+|#\d+)(?![\w-])",
    re.I,
)
ATX = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
HTML_ID = re.compile(r"<a\s[^>]*\b(?:id|name)=\"([^\"]+)\"", re.I)
URL = re.compile(r"\bhttps?://[^\s<>()\[\]]+", re.I)
HOST_PATH = re.compile(
    r"(?<![\w/@.-])(?:[a-z0-9-]+\.)+(?:com|io|org|net|dev|ai|co|google)/[^\s)\],;]+"
)
# A commit hash left as text: 7 to 40 lowercase hex characters after "at ",
# "commit " or "@", not part of a longer word (so a 64-character sha256 never
# matches). Purely decimal words are byte offsets, rejected in main().
BARE_COMMIT = re.compile(r"(?:\bat |\bcommit |@)([0-9a-f]{7,40})(?![0-9A-Za-z_])")
AUTOLINK = re.compile(r"<[A-Za-z][A-Za-z0-9+.-]*:[^\s<>]*>")
LINK_IN_HEADING = re.compile(r"!?\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\([^)]*\)")
# Terms AGENTS.md defines and uses as terms of art (a cell is one surface on
# one platform of a real-install round, and so on). A page written for a
# reader may rely on one only once it has introduced it: a heading that holds
# the term, a first use that is link text pointing at the definition, or a
# first use followed by a parenthesised gloss. Each entry is the regex of the
# term's forms and the name the message prints.
TERMS: tuple[tuple[str, str], ...] = (
    (r"cells?", "cell"),
    (r"rounds?", "round"),
    (r"surfaces?", "surface"),
    (r"Observed bullets?", "Observed bullet"),
    (r"listing diffs?", "listing diff"),
    (r"secondary sources?", "secondary source"),
    (r"nested entr(?:y|ies)", "nested entry"),
)
# Phrases in which a term has its plain sense and needs no introduction: a
# spreadsheet's or a table's cell. Matched against the text that ends with the
# term, lower-cased.
TERM_PLAIN: dict[str, tuple[str, ...]] = {"cell": ("per cell", "table cell", "table's cell")}
# The documents that define the terms or whose outline AGENTS.md fixes.
TERM_EXEMPT_FILES = ("AGENTS.md", "CLAUDE.md")
TERM_EXEMPT_DIRS = ("research/",)
# The files that state rules without their history: a link to one of this
# repository's issues or pull requests is provenance, which they do not carry.
NO_PROVENANCE_FILES = ("AGENTS.md", "CLAUDE.md")
PROVENANCE_LINK = re.compile(
    r"^<?https?://github\.com/seanthegeek/doubleagent/(?:issues|pull)/\d+", re.I
)


def strip_fences(text: str) -> str:
    """Blank every line of a fenced code block, keeping line numbers."""
    out = []
    fence = ""
    for line in text.split("\n"):
        match = FENCE.match(line)
        if fence:
            closing = match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence)
            if closing and not line.strip().lstrip(fence[0]):
                fence = ""
            out.append("")
        elif match:
            fence = match.group(1)
            out.append("")
        else:
            out.append(line)
    return "\n".join(out)


def blank_code_spans(text: str) -> str:
    """Replace each inline code span with spaces, keeping offsets and newlines."""
    return CODE_SPAN.sub(lambda match: re.sub(r"[^\n]", " ", match.group(0)), text)


def blank(text: str, spans: list[tuple[int, int]]) -> str:
    """Replace each span with spaces, keeping offsets and newlines."""
    chars = list(text)
    for start, end in spans:
        for i in range(start, end):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def anchor(heading: str) -> str:
    text = LINK_IN_HEADING.sub(r"\1", heading)
    text = text.replace("`", "").strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def heading_anchors(text: str) -> list[str]:
    """Return the GitHub anchor of every heading in a Markdown text, in order."""
    lines = strip_fences(text).split("\n")
    seen: dict[str, int] = {}
    found: list[str] = []
    for i, line in enumerate(lines):
        match = ATX.match(line)
        heading = None
        if match:
            heading = match.group(2)
        elif (
            i > 0
            and SETEXT.match(line)
            and lines[i - 1].strip()
            and not ATX.match(lines[i - 1])
            and not (
                line.strip().startswith("-") and lines[i - 1].lstrip().startswith(("-", "*", "|"))
            )
        ):
            heading = lines[i - 1]
        if heading is None:
            continue
        slug = anchor(heading)
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        found.append(slug if count == 0 else "%s-%d" % (slug, count))
    return found


def anchors_of(path: pathlib.Path, cache: dict[pathlib.Path, set[str]]) -> set[str]:
    if path in cache:
        return cache[path]
    text = path.read_text(encoding="utf-8")
    found = set(heading_anchors(text))
    found.update(HTML_ID.findall(strip_fences(text)))
    cache[path] = found
    return found


def markdown_files() -> list[pathlib.Path]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    files = {ROOT / path for path in out.split("\0") if path.endswith(".md")}
    return sorted(path for path in files if path.is_file())


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def check_target(src: pathlib.Path, target: str, cache: dict[pathlib.Path, set[str]]) -> str | None:
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if SCHEME.match(target):
        return None
    path_part, _, fragment = target.partition("#")
    path_part = urllib.parse.unquote(path_part)
    if not path_part:
        dest = src
    elif path_part.startswith("/"):
        dest = ROOT / path_part.lstrip("/")
    else:
        dest = src.parent / path_part
    if not dest.exists():
        return "link target does not exist: %s" % target
    if (
        fragment
        and dest.is_file()
        and dest.suffix.lower() == ".md"
        and urllib.parse.unquote(fragment) not in anchors_of(dest, cache)
    ):
        return "no heading for #%s in %s" % (fragment, display(dest))
    return None


def display(path: pathlib.Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def term_problems(text: str, link_text: list[tuple[int, int]]) -> list[tuple[int, str]]:
    """The offset and message of each term of art in `TERMS` that `text` (fences
    stripped, code spans and link destinations blanked) relies on without
    introducing it: no heading
    holds the term, and its first use in a non-plain sense is neither inside
    one of the `link_text` spans nor followed by `(`."""
    headings = "\n".join(line for line in text.splitlines() if ATX.match(line))
    out: list[tuple[int, str]] = []
    for pattern, name in TERMS:
        term_pattern = re.compile(r"\b%s\b" % pattern, re.I)
        if term_pattern.search(headings):
            continue
        for match in term_pattern.finditer(text):
            lead = text[max(0, match.start() - 16) : match.end()].lower()
            if any(lead.endswith(phrase) for phrase in TERM_PLAIN.get(name, ())):
                continue
            if any(start <= match.start() and match.end() <= end for start, end in link_text):
                break
            if re.match(r"[ \t]*\(", text[match.end() : match.end() + 3]):
                break
            out.append(
                (
                    match.start(),
                    'term of art "%s" is not introduced: define it, link its definition, '
                    "or use plain words" % name,
                )
            )
            break
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("files", nargs="*", type=lambda argument: pathlib.Path(argument).resolve())
    args = parser.parse_args()
    files = args.files or markdown_files()
    cache: dict[pathlib.Path, set[str]] = {}
    links = bad = 0
    for path in files:
        rel = display(path)
        text = blank_code_spans(strip_fences(path.read_text(encoding="utf-8")))
        link_text: list[tuple[int, int]] = []
        targets: list[tuple[int, str]] = []
        hidden: list[tuple[int, int]] = []
        # The link destinations, reference targets and autolinks alone: what
        # the term check blanks, since a word inside a target is not displayed.
        unseen: list[tuple[int, int]] = []
        for match in INLINE_LINK.finditer(text):
            link_text.append((match.start(1), match.end(1)))
            targets.append((match.start(2), match.group(2)))
            hidden.append((match.start(1), match.end(1)))
            hidden.append((match.end(1), match.end(0)))
            unseen.append((match.end(1), match.end(0)))
            label = " ".join(match.group(1).split())
            if URL.search(label) or HOST_PATH.search(label):
                print("%s:%d: link text is a URL: %s" % (rel, line_of(text, match.start(1)), label))
                bad += 1
        for match in REF_DEF.finditer(text):
            targets.append((match.start(1), match.group(1)))
            hidden.append((match.start(1), match.end(1)))
            unseen.append((match.start(1), match.end(1)))
        for match in AUTOLINK.finditer(text):
            hidden.append((match.start(), match.end()))
            unseen.append((match.start(), match.end()))
        prose = blank(text, hidden)
        for pattern, what in ((URL, "URL"), (HOST_PATH, "host path")):
            for match in pattern.finditer(prose):
                print(
                    "%s:%d: %s is not a link: %s"
                    % (rel, line_of(prose, match.start()), what, match.group(0))
                )
                bad += 1
        for match in BARE_COMMIT.finditer(prose):
            if match.group(1).isdigit():
                continue
            print(
                "%s:%d: bare commit hash %s" % (rel, line_of(prose, match.start(1)), match.group(1))
            )
            bad += 1
        for offset, target in sorted(targets):
            links += 1
            msg = check_target(path, target, cache)
            if msg:
                print("%s:%d: %s" % (rel, line_of(text, offset), msg))
                bad += 1
            if rel in NO_PROVENANCE_FILES and PROVENANCE_LINK.match(target):
                print(
                    "%s:%d: issue or pull request link in a file that states rules, "
                    "not history: %s" % (rel, line_of(text, offset), target.strip("<>"))
                )
                bad += 1
        for match in ISSUE.finditer(text):
            if any(start <= match.start() and match.end() <= end for start, end in link_text):
                continue
            words = " ".join(match.group(0).split())
            print(
                "%s:%d: issue reference is not a link: %s"
                % (rel, line_of(text, match.start()), words)
            )
            bad += 1
        for match in SECTION.finditer(text):
            if any(start <= match.start() and match.end() <= end for start, end in link_text):
                continue
            words = " ".join(match.group(0).split())
            print(
                "%s:%d: section reference is not a link: %s"
                % (rel, line_of(text, match.start()), words)
            )
            bad += 1
        if rel not in TERM_EXEMPT_FILES and not rel.startswith(TERM_EXEMPT_DIRS):
            for offset, msg in term_problems(blank(text, unseen), link_text):
                print("%s:%d: %s" % (rel, line_of(text, offset), msg))
                bad += 1
    if bad:
        print("%d problems in %d links checked in %d files" % (bad, links, len(files)))
        return 1
    print("%d links checked in %d files" % (links, len(files)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
