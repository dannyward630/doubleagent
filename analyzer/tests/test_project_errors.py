"""Tests of the analyzer's own exceptions and the command's handling of them."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from doubleagent import cli
from doubleagent.errors import DoubleAgentError, InputError
from doubleagent.filters import BoundError, parse_bound
from doubleagent.inputs import open_input
from doubleagent.inventory import input_files
from doubleagent.parsers.vscode import MutationError, apply_mutation


def run_main(arguments):
    """Run the command and return its exit code and stderr."""
    stderr = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
        exit_code = cli.main(arguments)
    return exit_code, stderr.getvalue()


class HierarchyTests(unittest.TestCase):
    """The project's errors share one base, which is not a ValueError."""

    def test_subclasses(self):
        for error_class in (BoundError, InputError, MutationError):
            self.assertTrue(issubclass(error_class, DoubleAgentError), error_class)
        self.assertTrue(issubclass(DoubleAgentError, RuntimeError))
        self.assertFalse(issubclass(DoubleAgentError, ValueError))

    def test_raisers(self):
        with self.assertRaises(DoubleAgentError):
            parse_bound("not a time")
        with self.assertRaises(DoubleAgentError):
            apply_mutation({}, {"kind": 1, "k": "not a list"})


class CommandErrorTests(unittest.TestCase):
    """Each project error reaches the analyst as an `error:` line and exit code 2."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_bad_since(self):
        exit_code, stderr = run_main(
            ["timeline", str(self.tmp), "-o", str(self.tmp / "out"), "--since", "soon"]
        )
        self.assertEqual(exit_code, 2)
        self.assertTrue(stderr.startswith("error: cannot read 'soon' as a time"), stderr)

    def test_since_after_until(self):
        arguments = ["timeline", str(self.tmp), "-o", str(self.tmp / "out")]
        exit_code, stderr = run_main([*arguments, "--since", "2026-10-02", "--until", "2026-10-01"])
        self.assertEqual(exit_code, 2)
        self.assertIn("is after --until", stderr)

    def test_bad_match(self):
        arguments = ["timeline", str(self.tmp), "-o", str(self.tmp / "out"), "--match", "("]
        exit_code, stderr = run_main(arguments)
        self.assertEqual(exit_code, 2)
        self.assertTrue(stderr.startswith("error: --match '('"), stderr)

    def test_file_that_is_not_an_archive(self):
        path = self.tmp / "notes.txt"
        path.write_text("not an archive\n", encoding="utf-8")
        with self.assertRaises(InputError):
            open_input(path, cli.catalog_mod.load())
        exit_code, stderr = run_main(["detect", str(path)])
        self.assertEqual(exit_code, 2)
        self.assertIn("is neither a tar nor a zip archive", stderr)

    def test_inventory_symlink(self):
        target = self.tmp / "inventory.jsonl"
        target.write_text("", encoding="utf-8")
        link = self.tmp / "link.jsonl"
        os.symlink(target, link)
        with self.assertRaises(InputError):
            input_files([link])
        exit_code, stderr = run_main(["inventory", str(link), "-o", str(self.tmp / "x.csv")])
        self.assertEqual(exit_code, 2)
        self.assertIn("is a symlink; give its target", stderr)


if __name__ == "__main__":
    unittest.main()
