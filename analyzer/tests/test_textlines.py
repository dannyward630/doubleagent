"""Tests of `textlines`: line ends at LF or CRLF only, ASCII-only trims."""

from doubleagent.textlines import ASCII_SPACE, SPACE_OR_TAB, split_lines, without_terminator

SEPARATORS = ("\u2028", "\u2029", "\u0085", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e")


def test_split_at_lf():
    assert split_lines("a\nb") == ["a", "b"]


def test_split_at_crlf():
    assert split_lines("a\r\nb\r\n") == ["a", "b"]


def test_lone_cr_kept_in_the_line():
    assert split_lines("a\rb\n") == ["a\rb"]


def test_no_split_at_unicode_or_ascii_separators():
    for separator in SEPARATORS:
        assert split_lines("a%sb\n" % separator) == ["a%sb" % separator]


def test_terminating_lf_gives_no_empty_line():
    assert split_lines("a\n") == ["a"]
    assert split_lines("") == []


def test_blank_lines_inside_are_kept():
    assert split_lines("a\n\n\nb\n\n") == ["a", "", "", "b", ""]


def test_byte_order_mark_is_kept():
    assert split_lines("\ufeffa\n") == ["\ufeffa"]


def test_without_terminator_drops_lf_or_crlf_only():
    assert without_terminator("a\r\n") == "a"
    assert without_terminator("a\n") == "a"
    assert without_terminator("a") == "a"
    assert without_terminator("a\r") == "a\r"
    assert without_terminator("a\n\n") == "a\n"
    assert without_terminator(" a\u2028 \n") == " a\u2028 "


def test_trim_keeps_unicode_spaces():
    for space in ("\u00a0", "\u2028", "\u3000", "\u0085"):
        padded = " %sa%s\t" % (space, space)
        assert padded.strip(ASCII_SPACE) == "%sa%s" % (space, space)
        assert padded.strip(SPACE_OR_TAB) == "%sa%s" % (space, space)


def test_trim_takes_ascii_whitespace():
    assert " \t\r\f\va\v\f\r\t ".strip(ASCII_SPACE) == "a"
    assert " \ta\f".strip(SPACE_OR_TAB) == "a\f"
