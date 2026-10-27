"""Tests for tools/check_code_style.py, the naming and comment checker, on synthetic files."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2] / "tools" / "check_code_style.py"
_spec = importlib.util.spec_from_file_location("check_code_style", TOOL)
assert _spec is not None and _spec.loader is not None
style = importlib.util.module_from_spec(_spec)
sys.modules["check_code_style"] = style
_spec.loader.exec_module(style)


def findings(directory: Path, name: str, text: str) -> list[str]:
    """Write `text` to `name` under `directory` and return the checker's findings for it."""
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return style.check_file(path)


def comment_lines(count: int) -> str:
    """Return `count` whole-line comments."""
    return "".join("# line %d\n" % number for number in range(count))


def docstring(count: int) -> str:
    """Return the body of a docstring `count` lines long."""
    return "Summary.\n" + "".join("text\n" for _ in range(count - 2)) + "end."


def test_python_short_name(tmp_path):
    assert findings(tmp_path, "ok.py", "row = 1\n") == []
    assert findings(tmp_path, "bad.py", "r = 1\n") == [
        "%s:1: name 'r' is shorter than 3 characters" % (tmp_path / "bad.py")
    ]


def test_python_allowed_short_names(tmp_path):
    source = "for i in range(3):\n    for _ in range(i):\n        pass\n"
    assert findings(tmp_path, "ok.py", source) == []
    assert findings(tmp_path, "bad.py", "for n in range(3):\n    pass\n") != []


def test_python_parameter_function_and_class_names(tmp_path):
    source = "class Reader:\n    def read(self, path):\n        return path\n"
    assert findings(tmp_path, "ok.py", source) == []
    source = "class Rd:\n    def rd(self, p):\n        return p\n"
    assert len(findings(tmp_path, "bad.py", source)) == 3


def test_python_with_except_walrus_and_comprehension_targets(tmp_path):
    source = (
        "import re\n"
        "with open('x') as handle:\n    pass\n"
        "try:\n    pass\nexcept OSError as error:\n    pass\n"
        "if (match := re.match('a', 'a')):\n    pass\n"
        "items = [value for value in range(3)]\n"
    )
    assert findings(tmp_path, "ok.py", source) == []
    source = source.replace("handle", "fh").replace("error", "e")
    source = source.replace("match", "m").replace("value", "v")
    assert len(findings(tmp_path, "bad.py", source)) == 4


def test_abbreviation_as_whole_name_and_segment(tmp_path):
    assert findings(tmp_path, "ok.py", "message_id = 1\nsession_id = 2\n") == []
    messages = findings(tmp_path, "bad.py", "msg = 1\nmsg_id = 2\nSTATE_DB_REL = 3\n")
    assert [message.split(": ", 1)[1] for message in messages] == [
        "name 'msg' abbreviates a word ('msg')",
        "name 'msg_id' abbreviates a word ('msg')",
        "name 'STATE_DB_REL' abbreviates a word ('db')",
    ]


def test_workspace_abbreviation_is_rejected(tmp_path):
    assert findings(tmp_path, "ok.py", "VSCODE_WORKSPACE = 1\n") == []
    assert findings(tmp_path, "bad.py", "VSCODE_WS = 1\n") != []


def test_class_body_field_declaration_is_exempt(tmp_path):
    source = "class Record:\n    at: str\n    id: int\n"
    assert findings(tmp_path, "ok.py", source) == []
    source = "class Record:\n    at: str = ''\n"
    assert findings(tmp_path, "bad.py", source) != []


def test_sh_temporaries_prefix(tmp_path):
    source = "#!/bin/sh\n_cp_user=1\n_ret_json=2\n"
    assert findings(tmp_path, "ok.sh", source) == []
    messages = findings(tmp_path, "bad.sh", "#!/bin/sh\n_cp_u=1\n")
    assert [message.split(": ", 1)[1] for message in messages] == [
        "name 'u' is shorter than 3 characters"
    ]


def test_sh_for_and_read_variables(tmp_path):
    source = '#!/bin/sh\nfor argument in "$@"; do :; done\nread -r line rest\n'
    assert findings(tmp_path, "ok.sh", source) == []
    source = '#!/bin/sh\nfor a in "$@"; do :; done\nread -r ln rest\n'
    assert len(findings(tmp_path, "bad.sh", source)) == 2


def test_pytest_fixture_name_is_exempt(tmp_path):
    assert findings(tmp_path, "ok.py", "def test_read(tmp_path):\n    pass\n") == []
    assert findings(tmp_path, "bad.py", "def test_read(tmp_dir):\n    pass\n") != []


def test_sh_tz_is_exempt(tmp_path):
    assert findings(tmp_path, "ok.sh", "#!/bin/sh\nTZ=UTC\n") == []
    assert findings(tmp_path, "bad.sh", "#!/bin/sh\nTS=1\n") != []


def test_sh_file_found_by_shebang(tmp_path):
    assert findings(tmp_path, "hook", "#!/bin/sh\nf=1\n") != []
    assert findings(tmp_path, "notes", "f=1\n") == []


def test_powershell_variable_prefixes(tmp_path):
    source = "$row = 1\n$script:Manifest = 2\n$_ | Out-Null\n$args | Out-Null\n"
    assert findings(tmp_path, "ok.ps1", source) == []
    messages = findings(tmp_path, "bad.ps1", "$r = 1\n$script:M = 2\n")
    assert [message.split(": ", 1)[1] for message in messages] == [
        "name 'r' is shorter than 3 characters",
        "name 'M' is shorter than 3 characters",
    ]


def test_issue_reference_in_comment(tmp_path):
    assert findings(tmp_path, "ok.py", "# Read the index first.\n") == []
    messages = findings(tmp_path, "bad.py", "# See #113.\n# Fixed in issue 42.\n")
    assert len(messages) == 2
    assert "issue or pull request" in messages[0]


def test_issue_reference_in_docstring(tmp_path):
    source = 'def read():\n    """Read the index (pull request 129)."""\n'
    assert len(findings(tmp_path, "bad.py", source)) == 1
    source = 'def read():\n    """Read the index."""\n'
    assert findings(tmp_path, "ok.py", source) == []


def test_issue_number_inside_a_quoted_check_name_is_text(tmp_path):
    source = '#!/bin/sh\ncheck "codex logs (#113)" "true"\n'
    assert findings(tmp_path, "ok.sh", source) == []
    source = "#!/bin/sh\ncheck name true  # see #113\n"
    assert findings(tmp_path, "bad.sh", source) != []
    source = '$checks += "codex logs (#113)"\n'
    assert findings(tmp_path, "ok.ps1", source) == []


def test_date_in_comment(tmp_path):
    assert findings(tmp_path, "ok.py", "# Read the index.\n") == []
    source = "# Seen 2026-10-27.\n# Seen October 2026.\n# Seen in 2026.\n"
    assert len(findings(tmp_path, "bad.py", source)) == 3


def test_code_point_and_copyright_are_not_dates(tmp_path):
    source = "# Split at U+2028 too.\n# Copyright 2026 the authors.\n"
    assert findings(tmp_path, "ok.py", source) == []


def test_smoke_fixture_label_is_exempt(tmp_path):
    label = "#!/bin/sh\n# 2026-10-21 codex logs (#113)\n"
    assert findings(tmp_path, "smoke.sh", label) == []
    assert len(findings(tmp_path, "other.sh", label)) == 2
    assert findings(tmp_path, "smoke.ps1", "# 2026-10-21 codex logs (#113)\n") == []


def test_comment_block_cap(tmp_path):
    code = "row = 1\nrow = 2\n"
    assert findings(tmp_path, "ok.py", code + comment_lines(10) + code) == []
    messages = findings(tmp_path, "bad.py", code + comment_lines(11) + code)
    assert [message.split(": ", 1)[1] for message in messages] == [
        "comment block of 11 lines is longer than 10"
    ]


def test_file_header_and_readers_guide_are_exempt(tmp_path):
    assert findings(tmp_path, "header.sh", "#!/bin/sh\n" + comment_lines(20)) == []
    guide = "row=1\n# Reader's guide\n" + comment_lines(20) + "row=2\n"
    assert findings(tmp_path, "guide.sh", "#!/bin/sh\n" + guide) == []
    other = "row=1\n# Notes\n" + comment_lines(20) + "row=2\n"
    assert findings(tmp_path, "other.sh", "#!/bin/sh\n" + other) != []


def test_docstring_cap(tmp_path):
    source = 'def read():\n    """%s"""\n'
    assert findings(tmp_path, "ok.py", source % docstring(10)) == []
    messages = findings(tmp_path, "bad.py", source % docstring(11))
    assert [message.split(": ", 1)[1] for message in messages] == [
        "docstring of 11 lines is longer than 10"
    ]


def test_module_docstring_cap(tmp_path):
    assert findings(tmp_path, "ok.py", '"""%s"""\n' % docstring(30)) == []
    messages = findings(tmp_path, "bad.py", '"""%s"""\n' % docstring(31))
    assert [message.split(": ", 1)[1] for message in messages] == [
        "docstring of 31 lines is longer than 30"
    ]


def test_quoted_text_is_not_scanned_for_names(tmp_path):
    source = '#!/bin/sh\necho "for a in the list; x=1"\n'
    assert findings(tmp_path, "ok.sh", source) == []
    assert findings(tmp_path, "bad.sh", "#!/bin/sh\nfor a in x; do :; done\n") != []
    assert findings(tmp_path, "ok.ps1", "Write-Output '$r is text'\n") == []


def test_here_document_comment_line_is_skipped(tmp_path):
    source = "#!/bin/sh\nWORKER=$(cat <<'EOF'\n# for a in the list\nEOF\n)\n"
    assert findings(tmp_path, "ok.sh", source) == []
    source = "#!/bin/sh\nWORKER=$(cat <<'EOF'\nfor a in x; do :; done\nEOF\n)\n"
    assert findings(tmp_path, "bad.sh", source) != []


def test_main_exit_status(tmp_path, capsys):
    good = tmp_path / "good.py"
    good.write_text("row = 1\n", encoding="utf-8")
    bad = tmp_path / "bad.py"
    bad.write_text("r = 1\n", encoding="utf-8")
    assert style.main([str(good)]) == 0
    assert style.main([str(good), str(bad)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "%s:1: name 'r' is shorter than 3 characters\n" % bad
    assert captured.err == "1 finding(s)\n"
