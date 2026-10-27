#!/usr/bin/env python3
"""Regenerate the real-run examples in ``analyzer/docs/output.md``."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from importlib import import_module
from pathlib import Path, PurePosixPath

ANALYZER = Path(__file__).resolve().parents[1]
REPO = ANALYZER.parent
DOC = ANALYZER / "docs" / "output.md"
COLLECTOR = REPO / "collectors" / "collect-agent-artifacts.sh"
FIXTURE_EVENT_MTIME = 1_790_852_400  # Match fixture event time: 2026-10-01T11:00:00Z.
DOC_TEMP_ROOT = "/tmp/doubleagent-output-examples"
BLOCKS = (
    "detect-json",
    "timeline-stdout",
    "inventory-json",
    "timeline-jsonl",
    "sessions-jsonl",
)
BEGIN = "<!-- BEGIN GENERATED: %s -->"
END = "<!-- END GENERATED: %s -->"
BEGIN_PREFIX = BEGIN.split("%s")[0]
END_PREFIX = END.split("%s")[0]

sys.path.insert(0, str(ANALYZER))
sys.path.insert(0, str(ANALYZER / "tests"))
FIXTURE_MODULE = import_module("fixtures")
CLAUDE_295_SESSION = FIXTURE_MODULE.CLAUDE_295_SESSION
PROJECT_PUSH_URL = FIXTURE_MODULE.PROJECT_PUSH_URL
build_image = FIXTURE_MODULE.build_image


class MarkerError(Exception):
    """The document does not have exactly one ordered pair of markers per block."""


class DocumentError(Exception):
    """The document is not UTF-8 text with LF line endings."""


class RunError(Exception):
    """A collector or analyzer command failed, so its output is not an example."""


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        encoding="utf-8",
        capture_output=True,
    )
    if result.returncode:
        raise RunError(
            "command failed (%d): %s\n%s%s"
            % (result.returncode, " ".join(command), result.stdout, result.stderr)
        )
    return result.stdout


def shell_path(shell: str, path: Path, *, cwd: Path, env: dict[str, str]) -> str:
    return run([shell, "-c", 'cd -- "$1" && pwd -P', "sh", str(path)], cwd=cwd, env=env).strip()


def normalize_output_paths(text: str, *, temporary_root: str, image_root: str) -> str:
    text = text.replace(image_root.rstrip("/") + "/", "/")
    return text.replace(temporary_root.rstrip("/"), DOC_TEMP_ROOT)


def normalize_fixture(image: Path) -> None:
    """Make text fixtures and their metadata stable across operating systems."""
    for path in image.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        data = path.read_bytes()
        if b"\0" not in data:
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError:
                pass
            else:
                content = content.replace("\r\n", "\n").replace("\r", "\n")
                with path.open("w", encoding="utf-8", newline="\n") as stream:
                    stream.write(content)
        os.utime(path, (FIXTURE_EVENT_MTIME, FIXTURE_EVENT_MTIME))


def build_collection(parent: Path) -> tuple[Path, str, str]:
    """Run the collector over the full shared fixture and keep its real output."""
    image = build_image(parent / "image")
    git_config = image / "srv/proj/.git/config"
    safe_git_config = git_config.read_text(encoding="utf-8").replace(
        PROJECT_PUSH_URL, "https://github.com/alice/proj.git"
    )
    with git_config.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(safe_git_config)
    normalize_fixture(image)

    shell = shutil.which("sh")
    if shell is None:
        raise RunError("sh is required to run collectors/collect-agent-artifacts.sh")
    output = parent / "collector-output"
    env = os.environ.copy()
    env.update(LC_ALL="C", TZ="UTC")
    temporary_root = shell_path(shell, parent, cwd=REPO, env=env)
    image_root = shell_path(shell, image, cwd=REPO, env=env)
    run(
        [
            shell,
            str(COLLECTOR),
            "--root",
            str(image),
            "--output",
            str(output),
            "--no-docker",
            "--keep-staging",
            "--quiet",
        ],
        cwd=REPO,
        env=env,
    )

    staging = sorted(output.glob(".stage-*"))
    if len(staging) != 1:
        raise RunError("the collector did not leave exactly one staging collection")
    collection = parent / "ws01"
    staging[0].rename(collection)

    manifest_path = collection / "manifest.jsonl"
    manifest = [
        (json.loads(line), line) for line in manifest_path.read_text(encoding="utf-8").splitlines()
    ]
    manifest.sort(
        key=lambda item: (
            tuple(part.casefold() for part in PurePosixPath(item[0]["path"]).parts),
            item[1],
        )
    )
    with manifest_path.open("w", encoding="utf-8", newline="\n") as stream:
        for _, line in manifest:
            stream.write(line + "\n")

    summary_path = collection / "collection.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["hostname"] = "ws01"
    with summary_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(summary, stream, indent=2)
        stream.write("\n")
    return collection, temporary_root, image_root


def cli_output(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    temporary_root: str,
    image_root: str,
) -> str:
    output = run([sys.executable, "-m", "doubleagent", *args], cwd=cwd, env=env)
    return normalize_output_paths(output, temporary_root=temporary_root, image_root=image_root)


def timeline_example_rows(text: str) -> str:
    """Return every row from the fixture's short Claude Code 2.1.295 session."""
    selected = []
    for line in text.splitlines():
        row = json.loads(line)
        if (
            row["user"] == "alice"
            and row["agent"] == "claude-code"
            and row["session_id"] == CLAUDE_295_SESSION
        ):
            selected.append(line)
    if not selected:
        raise RunError("the fixture timeline has no rows for the selected session")
    return "\n".join(selected)


def markdown_block(language: str, content: str) -> str:
    return "```%s\n%s\n```\n" % (language, content.rstrip())


def marker_spans(document: str) -> dict[str, tuple[int, int]]:
    """Return the text spans between each ordered begin/end marker pair.

    Raises:
        MarkerError: The document has a missing, duplicated, misplaced or stray marker.
    """
    expected = [marker % name for name in BLOCKS for marker in (BEGIN, END)]
    found = []
    offset = 0
    for line in document.split("\n"):
        if line.startswith((BEGIN_PREFIX, END_PREFIX)):
            found.append((line, offset, offset + len(line) + 1))
        offset += len(line) + 1
    if [line for line, _, _ in found] != expected:
        raise MarkerError(
            "markers must be these lines, in order: %s; found: %s"
            % (", ".join(expected), ", ".join(line for line, _, _ in found) or "none")
        )
    return {
        name: (found[2 * index][2], found[2 * index + 1][1])
        for index, name in enumerate(BLOCKS)
    }


def render(document: str, blocks: dict[str, str]) -> str:
    """Return the document with generated blocks between their existing markers."""
    spans = marker_spans(document)
    for name in reversed(BLOCKS):
        start, stop = spans[name]
        document = document[:start] + blocks[name] + document[stop:]
    return document


def read_document(document: Path) -> str:
    """Read a UTF-8 LF document without changing its bytes."""
    try:
        text = document.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        raise DocumentError("%s is not UTF-8: %s" % (document, error)) from error
    if "\r" in text:
        raise DocumentError("%s has CR line endings; only LF is kept" % document)
    return text


def write_document(document: Path, text: str) -> None:
    """Replace the document atomically and keep its permissions."""
    mode = stat.S_IMODE(document.stat().st_mode)
    descriptor, temporary = tempfile.mkstemp(dir=document.parent, prefix=document.name + ".")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(text.encode("utf-8"))
        os.chmod(temporary, mode)
        os.replace(temporary, document)
    except BaseException:
        os.unlink(temporary)
        raise


def generate() -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="doubleagent-output-examples-") as temporary:
        parent = Path(temporary)
        collection, temporary_root, image_root = build_collection(parent)
        env = os.environ.copy()
        old_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(ANALYZER) + (os.pathsep + old_pythonpath if old_pythonpath else "")

        detected = cli_output(
            ["detect", str(collection.resolve()), "--json"],
            cwd=parent,
            env=env,
            temporary_root=temporary_root,
            image_root=image_root,
        ).rstrip()
        output_dir = parent / "out"
        timeline_stdout = (
            cli_output(
                [
                    "timeline",
                    str(collection.resolve()),
                    "--agent",
                    "claude-code",
                    "-o",
                    "out",
                ],
                cwd=parent,
                env=env,
                temporary_root=temporary_root,
                image_root=image_root,
            )
            .replace("\\", "/")
            .rstrip()
        )
        inventory = (output_dir / "inventory.json").read_text(encoding="utf-8")
        timeline = (output_dir / "timeline.jsonl").read_text(encoding="utf-8")
        sessions = (output_dir / "sessions.jsonl").read_text(encoding="utf-8")
        return {
            "detect-json": markdown_block("json", detected),
            "timeline-stdout": markdown_block("text", timeline_stdout),
            "inventory-json": markdown_block(
                "json",
                normalize_output_paths(
                    inventory, temporary_root=temporary_root, image_root=image_root
                ).rstrip(),
            ),
            "timeline-jsonl": markdown_block(
                "jsonl",
                timeline_example_rows(
                    normalize_output_paths(
                        timeline, temporary_root=temporary_root, image_root=image_root
                    )
                ),
            ),
            "sessions-jsonl": markdown_block(
                "jsonl",
                normalize_output_paths(
                    sessions, temporary_root=temporary_root, image_root=image_root
                ).rstrip(),
            ),
        }


def check(document: Path = DOC) -> list[str]:
    """Return one unified diff per stale generated block, or an empty list."""
    text = read_document(document)
    spans = marker_spans(text)
    blocks = generate()
    diffs = []
    for name in BLOCKS:
        start, stop = spans[name]
        if text[start:stop] != blocks[name]:
            diff = difflib.unified_diff(
                text[start:stop].splitlines(keepends=True),
                blocks[name].splitlines(keepends=True),
                "%s (%s, documented)" % (document, name),
                "%s (%s, regenerated)" % (document, name),
            )
            diffs.append("".join(diff))
    return diffs


def regenerate(document: Path = DOC) -> None:
    """Replace each generated block with a fresh collector and analyzer run."""
    document = document.resolve()
    text = read_document(document)
    marker_spans(text)
    write_document(document, render(text, generate()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if output.md does not match the generated examples",
    )
    parser.add_argument("--document", type=Path, default=DOC, help="default: %(default)s")
    args = parser.parse_args()
    try:
        if not args.check:
            regenerate(args.document)
            return 0
        diffs = check(args.document)
    except (MarkerError, DocumentError, RunError, OSError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 2
    for diff in diffs:
        sys.stdout.write(diff)
    if diffs:
        print(
            "stale; run python3 analyzer/tests/regenerate_output_examples.py",
            file=sys.stderr,
        )
    return 1 if diffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
