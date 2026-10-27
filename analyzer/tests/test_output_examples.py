"""Regression tests for generated analyzer output documentation."""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REGENERATOR = REPO / "analyzer" / "tests" / "regenerate_output_examples.py"
OUTPUT_DOC = REPO / "analyzer" / "docs" / "output.md"


def run_generator(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the output-example generator from the repository root."""
    return subprocess.run(
        [sys.executable, str(REGENERATOR), *arguments],
        cwd=REPO,
        check=False,
        encoding="utf-8",
        capture_output=True,
    )


def test_documented_examples_match_collected_fixture() -> None:
    """Require every documented block to match a fresh collector run."""
    result = run_generator("--check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_stale_check_does_not_rewrite_document(tmp_path: Path) -> None:
    """Keep check mode read-only when one generated block is stale."""
    document = tmp_path / "output.md"
    original = OUTPUT_DOC.read_text(encoding="utf-8")
    begin = "<!-- BEGIN GENERATED: detect-json -->"
    end = "<!-- END GENERATED: detect-json -->"
    start = original.index(begin) + len(begin)
    stop = original.index(end, start)
    stale = original[:start] + "\n<!-- stale test content -->\n" + original[stop:]
    document.write_text(stale, encoding="utf-8")
    result = run_generator("--check", "--document", str(document))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "stale; run" in result.stderr
    assert document.read_text(encoding="utf-8") == stale


def test_missing_marker_fails_without_changing_document(tmp_path: Path) -> None:
    """Reject a missing marker before generation and leave its document intact."""
    document = tmp_path / "output.md"
    original = OUTPUT_DOC.read_text(encoding="utf-8")
    begin = "<!-- BEGIN GENERATED: timeline-stdout -->"
    malformed = original.replace(begin, "<!-- MISSING GENERATED: timeline-stdout -->", 1)
    assert malformed != original
    document.write_text(malformed, encoding="utf-8")
    result = run_generator("--check", "--document", str(document))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "markers must be these lines" in result.stderr
    assert document.read_text(encoding="utf-8") == malformed
