"""Tests that the real-run examples of docs/output.md match what the analyzer writes now."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import itertools
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "regenerate_examples.py"
_spec = importlib.util.spec_from_file_location("regenerate_examples", TOOL)
assert _spec is not None and _spec.loader is not None
examples = importlib.util.module_from_spec(_spec)
sys.modules["regenerate_examples"] = examples
_spec.loader.exec_module(examples)

RUN = "run python3 analyzer/tools/regenerate_examples.py"


def run_main(*argv: str) -> tuple[int, str, str]:
    """Run the tool's command line in this process; return the exit status, stdout and stderr."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = examples.main(list(argv))
    return status, stdout.getvalue(), stderr.getvalue()


def test_documented_examples_are_current():
    diffs = examples.check()
    assert diffs == [], "stale examples in docs/output.md; %s:\n%s" % (RUN, "".join(diffs))


def test_generate_is_repeatable():
    assert examples.generate() == examples.generate()


def test_check_reports_a_stale_block(tmp_path):
    document = tmp_path / "output.md"
    text = examples.DOCUMENT.read_text(encoding="utf-8")
    stale = text.replace('"kind": "collected"', '"kind": "loose"', 1)
    document.write_text(stale, encoding="utf-8")
    status, stdout, _ = run_main("--check", "--document", str(document))
    assert status == 1
    assert '-  "kind": "loose",' in stdout and "detect-json" in stdout
    assert "inventory-json" not in stdout
    assert document.read_text(encoding="utf-8") == stale, "--check must write nothing"
    assert run_main("--document", str(document))[0] == 0
    assert document.read_text(encoding="utf-8") == text


def marker_faults(text: str) -> dict[str, str]:
    """Return the document `text` broken in every way the marker rule rejects, by case name."""
    markers = [
        marker % name for name in examples.BLOCKS for marker in (examples.BEGIN, examples.END)
    ]
    lines = text.split("\n")
    slots = [lines.index(marker) for marker in markers]
    cases = {}
    for order in itertools.permutations(markers):
        if list(order) != markers:
            moved = list(lines)
            for slot, marker in zip(slots, order, strict=True):
                moved[slot] = marker
            cases["order " + " / ".join(order)] = "\n".join(moved)
    for slot, marker in zip(slots, markers, strict=True):
        cases["missing " + marker] = "\n".join(lines[:slot] + lines[slot + 1 :])
        cases["duplicated " + marker] = "\n".join([*lines[:slot], marker, *lines[slot:]])
    stray = examples.BEGIN % "other"
    cases["stray marker"] = "\n".join([*lines[: slots[1] + 1], stray, *lines[slots[1] + 1 :]])
    return cases


def test_every_marker_fault_fails_and_writes_nothing(tmp_path):
    text = examples.DOCUMENT.read_text(encoding="utf-8")
    cases = marker_faults(text)
    assert len(cases) == 23 + 4 + 4 + 1
    document = tmp_path / "output.md"
    for case, broken in cases.items():
        document.write_text(broken, encoding="utf-8")
        for mode in ([], ["--check"]):
            status, stdout, stderr = run_main(*mode, "--document", str(document))
            assert status == 2, (case, mode)
            assert stdout == "" and "error: markers must be" in stderr, (case, mode)
            assert document.read_text(encoding="utf-8") == broken, (case, mode)
