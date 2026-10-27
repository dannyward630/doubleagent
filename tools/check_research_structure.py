#!/usr/bin/env python3
"""Check that every research document follows the structure AGENTS.md fixes.

Every agent's document under `research/` (not `research/README.md` and not
`research/frameworks.md`) has one H1 equal to the agent's catalog name, one
unheaded intro paragraph, then the outline of the "Research document
structure" subsection of AGENTS.md: `## Source and evidence` with
`### Observed` and `### Source reviews`; `## Collection` holding
`### Per-user storage` (with `#### Scratch directories`),
`### Credentials`, `### Exclusions`, `### Project-local files` and
`### Where the project path is recorded`; `## Parsing` holding
`### Transcript stores` (with `#### What survives a delete`),
`### Record schema`, `### Joins and timestamps`, `### Other
stores`, `### Format versions`, `### Secrets` and `### Parser
plan` (with the eight fixed `####` row subsections, in order, before any
other), or for an agent with nothing to parse one paragraph and no `###`;
then `## Confidence`. This checks, for each such file:

- the H1 is `# <agent>` where `<agent>` is the file's stem;
- the H2 headings are exactly `Source and evidence`, `Collection`,
  `Parsing`, `Confidence`, in order;
- the `###` headings under Collection and Parsing are exactly the numbered
  sections above, in order (Parsing may instead hold prose and no `###`);
- the fixed `###` and `####` subsections sit under the right heading;
- no bold label stands in for a heading: a paragraph may not open with
  `**Label**`, `**Label.**` or `**Label:**` followed by prose (a list item
  or table row may);
- no line assumes the two documents each agent had before the merge of
  October 2026 ("the collector document", "the analyzer review", "the two
  X documents", "collector concern");
- no confidence paragraph or bullet (`Confidence.`, `**Confidence:**`)
  stands outside `## Confidence`;
- no prose line is longer than `--width` characters (default 100) unless
  it carries a URL or is a single code span (delimited by a backtick run
  of any length, and optionally followed by closing parentheses and `.`,
  `,`, `;` or `:`), since neither can be wrapped.

With `--before DIR`, where DIR holds the `collectors/` and `analyzer/`
trees of the two documents each agent had before the merge, it also
reports every citation URL, code span, fenced-block line, number and bold
label that the old documents hold and the new one lacks, as `path: lost
<kind>: <text>`. A merge that collapses a repeated statement loses nothing;
one that drops a file name, a key, a size or a citation shows up here. A
code span wrapped across lines or moved into a fence still counts as kept.

Usage: tools/check_research_structure.py [--before DIR] [--width N] [FILE...]

Every failure is printed as `path[:line]: message`; the exit status is 1
when any check failed.
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RESEARCH = ROOT / "research"
SKIP = {"README.md", "frameworks.md"}

SECTIONS = ("Source and evidence", "Collection", "Parsing", "Confidence")
COLLECTION_H3 = (
    "Per-user storage",
    "Credentials",
    "Exclusions",
    "Project-local files",
    "Where the project path is recorded",
)
PARSING_H3 = (
    "Transcript stores",
    "Record schema",
    "Joins and timestamps",
    "Other stores",
    "Format versions",
    "Secrets",
    "Parser plan",
)
PLAN_H4 = (
    "Permission rows",
    "Model rows",
    "Past-use rows and secondary sources",
    "Sync, relay and origin rows",
    "Scratch directory rows",
    "Deletion rows",
    "Bad-line rows",
    "Fixtures",
)
# Fixed subsections, keyed by the heading they sit under.
FIXED = {
    "Source and evidence": ("Observed", "Source reviews"),
    "Per-user storage": ("Scratch directories",),
    "Transcript stores": ("What survives a delete",),
    "Parser plan": PLAN_H4,
}

ATX = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
BOLD_LEAD = re.compile(r"^\*\*[^*]+\*\*[.:]?(\s|$)")
URL = re.compile(r"https?://[^\s)\]>]+")
CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.S)
ONLY_CODE_SPAN = re.compile(r"^\s*(`+)(?!`)(?:[^`]|(?!\1(?!`))`+(?!`))+\1(?!`)[).,;:]*\s*$")
BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
NUMBER = re.compile(r"(?<![\w/.-])\d[\d,.]*(?:\s?(?:[KMGT]i?B|B|bytes|ms|s|%))?(?![\w/.-])")
# Wording that assumes the two documents each agent had before the merge.
SPLIT_PHRASE = re.compile(
    r"\b(?:the )?(?:collectors?|analyzer|parser) (?:document|review|research document)s?\b"
    r"|\bthe two [\w-]+ documents\b"
    r"|\bcollector (?:concern|class)\b",
    re.I,
)
# A confidence paragraph or bullet; it belongs in `## Confidence` only.
CONFIDENCE_LEAD = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?Confidence(?:\*\*)?\s*[.:]")


def load_link_check():
    """Import tools/check_doc_links.py, the oracle for fences and headings."""
    path = ROOT / "tools" / "check_doc_links.py"
    spec = importlib.util.spec_from_file_location("check_doc_links", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def research_files() -> list[pathlib.Path]:
    return [path for path in sorted(RESEARCH.glob("*.md")) if path.name not in SKIP]


def is_agent_document(path: pathlib.Path) -> bool:
    return path.resolve().parent == RESEARCH.resolve() and path.name not in SKIP


def headings(text: str) -> list[tuple[int, int, str]]:
    """(line number, level, text) of every ATX heading outside fences."""
    found = []
    for number, line in enumerate(text.split("\n"), 1):
        match = ATX.match(line)
        if match:
            found.append((number, len(match.group(1)), match.group(2).strip()))
    return found


def parents(heads: list[tuple[int, int, str]]) -> dict[str, list[str]]:
    """Each heading's direct children (level + 1), keyed by the parent's text."""
    owner: dict[str, list[str]] = {}
    stack: dict[int, str] = {}
    for _, level, title in heads:
        stack[level] = title
        for deeper in [k for k in stack if k > level]:
            del stack[deeper]
        parent = stack.get(level - 1, "")
        owner.setdefault(parent, []).append(title)
    return owner


def check_outline(rel, owner: dict[str, list[str]], sections: list[str]) -> list[str]:
    problems = []
    if sections != list(SECTIONS):
        problems.append(
            "%s: H2 headings must be, in order: %s; found: %s"
            % (rel, " | ".join(SECTIONS), " | ".join(sections) or "none")
        )
    if owner.get("Collection", []) != list(COLLECTION_H3):
        problems.append(
            "%s: Collection must hold, in order: %s; found: %s"
            % (rel, " | ".join(COLLECTION_H3), " | ".join(owner.get("Collection", [])) or "none")
        )
    parsing = owner.get("Parsing", [])
    if parsing and parsing != list(PARSING_H3):
        problems.append(
            "%s: Parsing must hold, in order: %s (or prose with no ###); found: %s"
            % (rel, " | ".join(PARSING_H3), " | ".join(parsing))
        )
    if owner.get("Confidence"):
        problems.append("%s: `Confidence` takes no subheadings" % rel)
    return problems


def check_fixed(rel, owner: dict[str, list[str]], present: set[str]) -> list[str]:
    problems = []
    for section, fixed in FIXED.items():
        if section not in present:
            continue
        have = owner.get(section, [])
        missing = [title for title in fixed if title not in have]
        if missing:
            problems.append(
                "%s: `%s` lacks the fixed subsection(s): %s" % (rel, section, ", ".join(missing))
            )
            continue
        if [title for title in have if title in fixed] != list(fixed):
            problems.append(
                "%s: `%s` fixed subsections out of order; want %s"
                % (rel, section, ", ".join(fixed))
            )
        if section == "Parser plan" and have[: len(fixed)] != list(fixed):
            problems.append(
                "%s: the eight fixed row subsections of `Parser plan` come before any other" % rel
            )
    return problems


def check_structure(path: pathlib.Path, text: str, width: int, link_check) -> list[str]:
    if not is_agent_document(path):
        return []
    rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    problems: list[str] = []
    stripped = link_check.strip_fences(text)
    heads = headings(stripped)
    top_heads = [head for head in heads if head[1] == 1]
    if len(top_heads) != 1 or top_heads[0][2] != path.stem:
        problems.append(
            "%s:%d: H1 must be `# %s`" % (rel, top_heads[0][0] if top_heads else 1, path.stem)
        )
    owner = parents(heads)
    problems += check_outline(rel, owner, [head[2] for head in heads if head[1] == 2])
    problems += check_fixed(rel, owner, {head[2] for head in heads})
    lines = stripped.split("\n")
    prev_blank = True
    section = ""
    for number, line in enumerate(lines, 1):
        if line.startswith("## "):
            section = line[3:].strip()
        in_prose = line.strip() and not line.lstrip().startswith(("|", "-", "*", ">", "#", "["))
        if prev_blank and in_prose and BOLD_LEAD.match(line):
            problems.append(
                "%s:%d: bold label used as a heading; make it a heading" % (rel, number)
            )
        split = SPLIT_PHRASE.search(line)
        if split:
            problems.append(
                '%s:%d: "%s" assumes two documents; the document speaks as one'
                % (rel, number, split.group(0))
            )
        if section != SECTIONS[3] and CONFIDENCE_LEAD.match(line):
            problems.append(
                "%s:%d: confidence statement outside `## Confidence`; move it there" % (rel, number)
            )
        long = in_prose and not line.lstrip()[:2].rstrip(".").isdigit() and len(line) > width
        if long and not URL.search(line) and not ONLY_CODE_SPAN.match(line):
            problems.append("%s:%d: prose line longer than %d characters" % (rel, number, width))
        prev_blank = not line.strip()
    first_h2 = next((head[0] for head in heads if head[1] == 2), None)
    if first_h2 is not None and top_heads:
        intro = [line for line in lines[top_heads[0][0] : first_h2 - 1] if line.strip()]
        if not intro:
            problems.append(
                "%s: no intro paragraph between the H1 and `## Source and evidence`" % rel
            )
    return problems


def tokens(text: str, link_check) -> dict[str, set[str]]:
    """The facts a rewrite must keep: URLs, code spans, fenced lines, numbers, bold labels.

    A code span is compared with its whitespace collapsed, so one wrapped
    across lines matches; a span also counts as kept when its text is a
    fenced line."""
    fenced: set[str] = set()
    in_fence = False
    for line in text.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence and line.strip():
            fenced.add(" ".join(line.split()))
    prose = link_check.strip_fences(text)
    spans = {" ".join(body.split()) for _, body in CODE_SPAN.findall(prose)}
    return {
        "url": {url.rstrip(".,;:") for url in URL.findall(prose)},
        "code span": spans | fenced,
        "fenced line": fenced,
        "number": {match.group(0).strip() for match in NUMBER.finditer(prose)},
        "bold label": {bold.strip().rstrip(".:") for bold in BOLD.findall(prose)},
    }


def check_invariants(path: pathlib.Path, text: str, before: pathlib.Path, link_check) -> list[str]:
    if not is_agent_document(path):
        return []
    rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    candidates = (before / "collectors" / path.name, before / "analyzer" / path.name)
    olds = [candidate for candidate in candidates if candidate.is_file()]
    if not olds:
        return ["%s: no pre-merge copy under %s" % (rel, before)]
    old: dict[str, set[str]] = {}
    for old_copy in olds:
        for kind, items in tokens(old_copy.read_text(encoding="utf-8"), link_check).items():
            old.setdefault(kind, set()).update(items)
    new = tokens(text, link_check)
    problems = []
    for kind in ("url", "code span", "fenced line", "number", "bold label"):
        for item in sorted(old.get(kind, set()) - new[kind]):
            problems.append("%s: lost %s: %s" % (rel, kind, item))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument(
        "--before", type=pathlib.Path, help="pre-merge copies, <DIR>/{collectors,analyzer}/"
    )
    parser.add_argument("--width", type=int, default=100, help="longest prose line allowed")
    parser.add_argument("files", nargs="*", type=lambda argument: pathlib.Path(argument).resolve())
    args = parser.parse_args()
    link_check = load_link_check()
    files = args.files or research_files()
    problems: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        problems += check_structure(path, text, args.width, link_check)
        if args.before:
            problems += check_invariants(path, text, args.before.resolve(), link_check)
    for problem in problems:
        print(problem)
    print("%d files checked, %d problems" % (len(files), len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
