"""Timestamp normalisation. Every timestamp the analyzer emits is UTC ISO 8601
with millisecond precision and a trailing Z, so rows from different agents
sort together."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

OUT_FMT = "%Y-%m-%dT%H:%M:%S.%f"
_FRACTION_RX = re.compile(r"\.(\d+)")
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def to_utc(value: object) -> str:
    """Return a canonical UTC string for an ISO 8601 string or an epoch number.

    Epoch values above 1e11 are taken as milliseconds (Claude Code's
    history.jsonl), below as seconds (Codex's history.jsonl). Unparseable
    input returns an empty string rather than raising, so one bad record
    never aborts a timeline.
    """
    if value is None or value == "":
        return ""
    try:
        if isinstance(value, bool):
            return ""
        if isinstance(value, (int, float)):
            return _from_epoch(float(value))
        text = str(value).strip()
        if text.replace(".", "", 1).isdigit():
            return _from_epoch(float(text))
        if text.endswith("Z") or text.endswith("z"):
            text = text[:-1] + "+00:00"
        # SQLite CURRENT_TIMESTAMP text, nanosecond fractions (Go) and
        # fractions with trailing zeros trimmed (go-sqlite3's `.5-08:00`) are
        # not accepted by fromisoformat before Python 3.11, which wants
        # exactly three or six digits.
        if len(text) > 10 and text[10] == " ":
            text = text[:10] + "T" + text[11:]
        text = _FRACTION_RX.sub(lambda match: "." + match.group(1)[:6].ljust(6, "0"), text, count=1)
        moment = datetime.fromisoformat(text)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return format_utc(moment.astimezone(timezone.utc))
    except (ValueError, OverflowError, OSError):
        return ""


def _from_epoch(seconds: float) -> str:
    if seconds > 1e11:
        seconds = seconds / 1000.0
    return format_utc(datetime.fromtimestamp(seconds, tz=timezone.utc))


def format_utc(moment: datetime) -> str:
    return moment.strftime(OUT_FMT)[:-3] + "Z"


def epoch_ms(value: str) -> int | None:
    """Epoch milliseconds of a timeline timestamp (`YYYY-MM-DDTHH:MM:SS.mmmZ`,
    as `to_utc` writes it), or None for an empty or unparseable one. An
    integer, so differences between two timestamps are exact."""
    if not value:
        return None
    try:
        moment = datetime.strptime(value, OUT_FMT + "Z")
    except ValueError:
        return None
    return (moment.replace(tzinfo=timezone.utc) - _EPOCH) // timedelta(milliseconds=1)


def first_nonempty(*values: str | None) -> str:
    for value in values:
        if value:
            return value
    return ""
