"""Tests that the real-run examples of docs/output.md match what the analyzer writes now."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "regenerate_examples.py"
_spec = importlib.util.spec_from_file_location("regenerate_examples", TOOL)
assert _spec is not None and _spec.loader is not None
examples = importlib.util.module_from_spec(_spec)
sys.modules["regenerate_examples"] = examples
_spec.loader.exec_module(examples)

RUN = "run python3 analyzer/tools/regenerate_examples.py from the repository root"


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


def test_missing_or_duplicated_marker_fails(tmp_path):
    text = examples.DOCUMENT.read_text(encoding="utf-8")
    end = examples.END % "inventory-json"
    begin = examples.BEGIN % "detect-json"
    cases = {
        "missing end": text.replace(end + "\n", ""),
        "duplicated begin": text.replace(begin, begin + "\n" + begin),
        "overlapping blocks": text.replace(examples.END % "detect-json" + "\n", "").replace(
            end + "\n", end + "\n" + examples.END % "detect-json" + "\n"
        ),
    }
    for case, broken in cases.items():
        document = tmp_path / "output.md"
        document.write_text(broken, encoding="utf-8")
        status, stdout, stderr = run_main("--document", str(document))
        assert status == 2, case
        assert stdout == "" and "error: block" in stderr, case
        assert document.read_text(encoding="utf-8") == broken, "%s: document rewritten" % case
        assert run_main("--check", "--document", str(document))[0] == 2, case
