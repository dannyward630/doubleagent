"""Drop rows from secondary sources that a primary store also records
(issue 122).

A secondary source is a file a parser reads beside the agent's own
transcript store and that repeats some of its events: a per-prompt history
file, a mirror or a projection (`Parser.secondary`). Every source is parsed
on every run; this module then keeps each event once. A secondary row is
dropped when a primary row has

- the same `host`, `user`, `agent` and `turn_type`, and the same `text`;
  but two `tool_use` or two `tool_result` rows that both carry a
  `tool_use_id` pair on the same `tool_use_id` instead, and never on text
  when the ids differ, since a mirror can record a call in another form
  than the transcript does (Codex's projection holds the parsed command,
  the rollout the model's arguments) and a call id is unique within a
  session; a tool row without an id pairs on text with one with an id or
  without;
- the same `session_id` when the secondary row has one; otherwise the same
  `project_path` when the secondary row has one; otherwise any primary row
  of that host, user and agent, since a text-only history records neither;
- when the secondary row has a `timestamp_utc`, a `timestamp_utc` at most
  the source's tolerance away (`Parser.secondary_tolerance`, by default
  `TOLERANCE_SECONDS`), the bound included; when it has none, any time or
  none.

An agent whose secondary source writes an event in another form than its
primary store registers a match form in `MATCH_FORMS`, and its rows match
on the `(turn_type, text)` that function returns instead of their own:
Claude Code's `history.jsonl` keeps a slash command as typed and a paste as
expanded text, where the transcript has a tag-form `slash command:` row
and the prompt joined differently (`claude_code.match_form`). It can also
register a wider window for some of its secondary rows in
`MATCH_TOLERANCES`: a Claude Code command that opens a picker or an
overlay is recorded in the transcript when it completes, seconds to
minutes after its history line (`claude_code.match_tolerance`). The
widening is forward only and against primary rows only: the row keeps
its source's window backwards (a record is never written before its
line was typed) and among secondary sources, and it may not take a
primary row recorded at or after the next secondary row of the same
text that could take that same record (for a record of a session: the
session's rows, the session-less rows of its project and the rows with
neither; a row of another session never counts), so an earlier history
line whose own record is missing never claims a later line's record.

Matching is one-to-one, the primary row always survives, and a secondary
row with no match is kept, so a session whose transcript was deleted,
excluded by size or truncated is still recovered from its history lines.
Each secondary row kept is marked `recovered` "yes" (`Row.recovered`),
except its `system` rows (an index header, a thread record, a snapshot,
a `parser:` problem), which describe the source rather than an event the
primary store lost, and `sessions.jsonl` sums the marks per session.
The timestamped secondary rows go first, in time order, each to the
nearest unused primary row within its tolerance; then the rows with no
timestamp, the session-scoped ones first, then those with only a project,
then those with neither, each group in input order, each to the
earliest-timestamped unused candidate, the undated candidates last in
input order. Taking the timestamped rows first keeps an undated row from
claiming the primary row a timestamped one would pair with, and taking
the most specific undated copy first lets it, not a text-only history
line, take the primary row.

Then the secondary rows no primary row took are matched against the
other secondary rows, one-to-one, under the same rule (the tolerance of
the row being tested), and a row that pairs is dropped and counted like
the others. The candidates are every secondary row a primary row took,
so a third copy of a primary event collapses onto the copy the primary
row took and only the primary row is left, and every row tested before
it: the timestamped rows in time order, then the undated rows in input
order, so the copy kept of several is the earliest timestamped one, and
an undated copy pairs with a timestamped one (no time constraint on the
undated side) rather than the reverse. In this pass a row looks under its
own scope first and then under the broader ones, its project when it has
one and then its identity alone, so a history line with a project and no
session meets a mirror line with a session and no project; under a
broader scope a candidate whose session or project differs from one the
row records is never taken. This shows once the several copies of one
event that backups, snapshots, archives and mirrors keep, also after the
primary store is gone. A row pairs only with a row from a different
`source_file`, since two identical lines in one file are two events that
file records. The primary pass looks under the row's own scope only.

Why two seconds: Codex writes `history.jsonl` `ts` in whole seconds beside
the millisecond timestamps of its rollouts; an Antigravity history line and
the database step for the same prompt differ by under a second; Claude
Code writes its history entry when the prompt is submitted, as the
transcript's user record is. Known miss: a prompt an agent queued and sent
later (Claude Code queues input typed while it works) can be minutes from
its transcript record, and is then shown twice, the history line's time
being when it was typed.

A `system` row whose `text` starts with `parser:` (`error_rows`) is never
dropped and never a candidate (issue 135): it describes its own
`source_file` (that file was unreadable, not a JSON array, cut off, or held
an unparseable line), so two such rows are never the same event, even when
a history file and a rollout fail with the same message.

Two cases the fixed window does not fit. A text-only prompt history with no
time of its own (Muse Code's `tui-history.jsonl`) yields rows with an empty
`timestamp_utc`, and those match on text and scope alone. A mirror that
stamps an event later than the primary store does (a transcript captured
at the end of a turn) gets a wider window from its parser's
`secondary_tolerance()`. A timestamped secondary row never matches a
primary row with no timestamp.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from collections import Counter
from collections.abc import Callable, Container

from .model import Row
from .timeutil import epoch_ms

TOLERANCE_SECONDS = 2.0

# The match form per agent: a function of a row that returns the
# `(turn_type, text)` the row is matched under in place of its own. A
# parser registers one when its secondary source records an event in
# another form than its primary store does (Claude Code's history line
# `/model` for the transcript's tag-form `slash command:` row); the rows of
# every other agent match on their own `turn_type` and `text`.
MATCH_FORMS: dict[str, Callable[[Row], tuple[str, str]]] = {}
# The time window per agent: a function of a secondary row that returns a
# wider window in seconds for that row, or None for the source's own. A
# parser registers one when some of its secondary rows record an event
# much earlier than the primary store does (a Claude Code slash command
# typed before the picker it opens is closed and recorded).
MATCH_TOLERANCES: dict[str, Callable[[Row], float | None]] = {}

_Dated = list[tuple[int, int]]  # (epoch ms, row index), sorted
_Upper = Callable[[int], int | None]  # a candidate's row index -> its bound (epoch ms)

_TOOL_TYPES = ("tool_use", "tool_result")


class _Bucket:
    """The candidate rows of one match key: those with a timestamp, sorted
    by time, and those without, in input order."""

    __slots__ = ("dated", "undated")

    def __init__(self) -> None:
        self.dated: _Dated = []
        self.undated: list[int] = []


def _has_id(r: Row) -> bool:
    """Whether `r` is a tool call or result with a `tool_use_id`."""
    return r.turn_type in _TOOL_TYPES and bool(r.tool_use_id)


def _by_text(r: Row) -> tuple[str, ...]:
    form = MATCH_FORMS.get(r.agent)
    turn_type, text = form(r) if form else (r.turn_type, r.text)
    return (r.host, r.user, r.agent, turn_type, "text", text)


def _by_id(r: Row) -> tuple[str, ...]:
    return (r.host, r.user, r.agent, r.turn_type, "id", r.tool_use_id)


def _is_parser_row(r: Row) -> bool:
    """Whether `r` is a `parser:` row about its own `source_file`, which
    neither pairs nor is paired with (issue 135)."""
    return r.turn_type == "system" and r.text.startswith("parser:")


def _scope_rank(r: Row) -> int:
    """0 for a row with a `session_id`, 1 for one with only a
    `project_path`, 2 for one with neither."""
    if r.session_id:
        return 0
    return 1 if r.project_path else 2


def _lookups(r: Row, broaden: bool) -> list[tuple[tuple, bool, bool]]:
    """The keys secondary row `r` looks under, in order, each with whether
    it is a broader scope than the row's own and whether only candidates
    without a `tool_use_id` may be taken there. A row with an id looks
    under its id, then under its text for candidates with no id; any
    other row under its text. The scope is the row's own (session, else
    project, else none) and, with `broaden`, then its project when it has
    one and its identity alone."""
    scopes: list[tuple] = []
    if r.session_id:
        scopes.append(("session", r.session_id))
    if r.project_path:
        scopes.append(("project", r.project_path))
    scopes.append(("any",))
    if not broaden:
        scopes = scopes[:1]
    idents = [(_by_id(r), False), (_by_text(r), True)] if _has_id(r) else [(_by_text(r), False)]
    return [
        ((*ident, *scope), n > 0, idless)
        for n, scope in enumerate(scopes)
        for ident, idless in idents
    ]


def _add(buckets: dict[tuple, _Bucket], r: Row, i: int, ms: int | None) -> None:
    """File candidate `r`, row index `i`, under its text and, with a
    `tool_use_id`, its id, each under its session, its project and alone,
    keeping each bucket's timestamps sorted."""
    idents = [_by_text(r), _by_id(r)] if _has_id(r) else [_by_text(r)]
    for ident in idents:
        for scope in (("session", r.session_id), ("project", r.project_path), ("any",)):
            bucket = buckets.setdefault((*ident, *scope), _Bucket())
            if ms is None:
                bucket.undated.append(i)
            else:
                insort(bucket.dated, (ms, i))


def _nearest(
    dated: _Dated,
    ms: int,
    back_ms: int,
    forward_ms: int,
    used: Container[int],
    upper: _Upper | None = None,
) -> int | None:
    """The index of the unused row in `dated` nearest to `ms`, no more
    than `back_ms` before it or `forward_ms` after it, the earlier one on
    a tie, and, when `upper` is given, before the epoch ms it returns for
    that candidate's index (None for no bound); None when there is none.
    The bound is the candidate's own (`_Bounds.upper`), so the scan runs
    to the end of the window rather than stopping at one time."""
    best: tuple[int, int] | None = None
    k = bisect_left(dated, (ms - back_ms, -1))
    while k < len(dated) and dated[k][0] <= ms + forward_ms:
        t, i = dated[k]
        k += 1
        if i in used:
            continue
        if upper is not None:
            limit = upper(i)
            if limit is not None and t >= limit:
                continue
        if best is None or abs(t - ms) < best[0]:
            best = (abs(t - ms), i)
    return best[1] if best else None


def _earliest(bucket: _Bucket, used: Container[int]) -> int | None:
    """The index of the earliest-timestamped unused row in `bucket`, the
    undated ones last in input order; None when every one is used."""
    for _, i in bucket.dated:
        if i not in used:
            return i
    for i in bucket.undated:
        if i not in used:
            return i
    return None


def _pair(
    bucket: _Bucket | None,
    r: Row,
    tolerance: float,
    used: Container[int],
    upper: _Upper | None = None,
    forward: float | None = None,
) -> int | None:
    """The candidate in `bucket` not in `used` that secondary row `r` pairs
    with under the time rule (`tolerance` either way, or `forward` after
    `r` when given), before the candidate's bound from `upper` when one
    is given, or None."""
    if bucket is None:
        return None
    ms = epoch_ms(r.timestamp_utc)
    if ms is None:
        return _earliest(bucket, used)
    back_ms = int(tolerance * 1000)
    forward_ms = back_ms if forward is None else int(forward * 1000)
    return _nearest(bucket.dated, ms, back_ms, forward_ms, used, upper)


def _processing_order(secondary: list[tuple[Row, float]], by_scope: bool) -> list[int]:
    """The secondary row indices in the order the rule tests them: the
    timestamped rows in time order, then the undated rows in input order,
    with `by_scope` grouped session-scoped, project-scoped, unscoped.
    `parser:` rows are left out, so they are never dropped."""
    stamped = []
    undated = []
    for j, (r, _) in enumerate(secondary):
        if _is_parser_row(r):
            continue
        ms = epoch_ms(r.timestamp_utc)
        if ms is None:
            undated.append(j)
        else:
            stamped.append((ms, j))
    if by_scope:
        undated.sort(key=lambda j: _scope_rank(secondary[j][0]))
    return [j for _, j in sorted(stamped)] + undated


class _Unavailable:
    """The candidate rows row `r` may not pair with: those already taken;
    with `same_file`, those from its own `source_file`, which records them
    as separate events; under a key marked id-less, those with a
    `tool_use_id`, a call of their own; and under a broader scope than
    the row's own, those whose session or project differs from one `r`
    records."""

    def __init__(self, rows: list[Row], used: set[int], r: Row, same_file: bool) -> None:
        self.rows = rows
        self.used = used
        self.row = r
        self.same_file = same_file
        self.broad = False
        self.idless = False

    def __contains__(self, i: object) -> bool:
        if not isinstance(i, int) or i in self.used:
            return True
        c, r = self.rows[i], self.row
        if self.same_file and c.source_file == r.source_file:
            return True
        if self.idless and _has_id(c):
            return True
        if not self.broad:
            return False
        session_differs = bool(r.session_id and c.session_id and c.session_id != r.session_id)
        project_differs = bool(
            r.project_path and c.project_path and c.project_path != r.project_path
        )
        return session_differs or project_differs


def _find(
    buckets: dict[tuple, _Bucket],
    r: Row,
    tolerance: float,
    unavailable: _Unavailable,
    broaden: bool,
    upper: _Upper | None = None,
    forward: float | None = None,
) -> int | None:
    """The candidate row `r` pairs with, trying its lookups in order,
    before each candidate's bound from `upper` and within `forward`
    seconds after `r` when given."""
    for key, broad, idless in _lookups(r, broaden):
        unavailable.broad, unavailable.idless = broad, idless
        i = _pair(buckets.get(key), r, tolerance, unavailable, upper, forward)
        if i is not None:
            return i
    return None


def _scope(r: Row) -> tuple:
    """The scope a row matches under: its session, else its project, else
    none (the first of `_lookups`)."""
    if r.session_id:
        return ("session", r.session_id)
    if r.project_path:
        return ("project", r.project_path)
    return ("any",)


class _Bounds:
    """The times of the secondary rows by match text and scope, for the
    next-line bound of a widened row (`upper`): a widened row may not take
    a primary row recorded at or after the next strictly later secondary
    row of the same text that could take that same primary row, so the
    later line keeps the later record. Which rows could take it depends on
    the candidate: a primary row of a session can be taken by that
    session's rows, by its project's rows with no session and by the rows
    with neither; one of a project with no session by the project's
    session-less rows and the rows with neither; one with neither by the
    rows with neither. A row of a different session never counts, and a
    copy at the same time (the same line in two history files) does not
    bound. Built only when some row is widened; each index is sorted once
    and searched by bisection."""

    __slots__ = ("by_none", "by_project_free", "by_session")

    def __init__(self, secondary: list[tuple[Row, float]]) -> None:
        self.by_session: dict[tuple, list[int]] = {}
        self.by_project_free: dict[tuple, list[int]] = {}
        self.by_none: dict[tuple, list[int]] = {}
        for r, _ in secondary:
            ms = epoch_ms(r.timestamp_utc)
            if ms is None or _is_parser_row(r):
                continue
            text = _by_text(r)
            if r.session_id:
                self.by_session.setdefault((text, r.session_id), []).append(ms)
            elif r.project_path:
                self.by_project_free.setdefault((text, r.project_path), []).append(ms)
            else:
                self.by_none.setdefault(text, []).append(ms)
        for index in (self.by_session, self.by_project_free, self.by_none):
            for times in index.values():
                times.sort()

    def upper(self, text: tuple, ms: int, candidate: Row) -> int | None:
        """The bound for a widened row of match `text` at `ms` against
        `candidate`, a primary row: the next time after `ms` among the
        secondary rows that could take `candidate`, or None."""
        lists = [self.by_none.get(text)]
        if candidate.session_id:
            lists.append(self.by_session.get((text, candidate.session_id)))
        if candidate.project_path:
            lists.append(self.by_project_free.get((text, candidate.project_path)))
        later: int | None = None
        for times in lists:
            if not times:
                continue
            k = bisect_right(times, ms)
            if k < len(times) and (later is None or times[k] < later):
                later = times[k]
        return later


def _candidate_bound(bounds: _Bounds, primary: list[Row], r: Row) -> _Upper | None:
    """The bound function for widened secondary row `r` over the rows of
    `primary`, by candidate index; None when `r` has no timestamp."""
    ms = epoch_ms(r.timestamp_utc)
    if ms is None:
        return None
    text = _by_text(r)
    return lambda i: bounds.upper(text, ms, primary[i])


def _against_primary(
    primary: list[Row],
    secondary: list[tuple[Row, float]],
    bounds: _Bounds | None = None,
    forward: dict[int, float] | None = None,
) -> list[int]:
    """The indices of the secondary rows that pair with a primary row,
    each looking only under its own scope, and for a row in `forward` up
    to that many seconds after it instead of its tolerance, taking no
    candidate at or after the bound `bounds` gives for it."""
    buckets: dict[tuple, _Bucket] = {}
    for i, r in enumerate(primary):
        if not _is_parser_row(r):
            _add(buckets, r, i, epoch_ms(r.timestamp_utc))
    used: set[int] = set()
    matched: list[int] = []
    for j in _processing_order(secondary, by_scope=True):
        r, tolerance = secondary[j]
        fwd = forward.get(j) if forward else None
        upper = _candidate_bound(bounds, primary, r) if bounds and fwd is not None else None
        i = _find(buckets, r, tolerance, _Unavailable(primary, used, r, False), False, upper, fwd)
        if i is not None:
            used.add(i)
            matched.append(j)
    return matched


def _among_secondary(secondary: list[tuple[Row, float]], matched: set[int]) -> list[int]:
    """The indices of the secondary rows, of those no primary row took, that
    pair with another secondary row from a different `source_file`: one a
    primary row took, or one tested before it. Each candidate is taken
    once; a row looks under its own scope, then the broader ones."""
    rows = [r for r, _ in secondary]
    buckets: dict[tuple, _Bucket] = {}
    for j in sorted(matched):
        _add(buckets, rows[j], j, epoch_ms(rows[j].timestamp_utc))
    used: set[int] = set()
    copies: list[int] = []
    for j in _processing_order(secondary, by_scope=False):
        if j in matched:
            continue
        r, tolerance = secondary[j]
        i = _find(buckets, r, tolerance, _Unavailable(rows, used, r, True), True)
        if i is not None:
            used.add(i)
            copies.append(j)
        _add(buckets, r, j, epoch_ms(r.timestamp_utc))
    return copies


def _forward_windows(secondary: list[tuple[Row, float]]) -> dict[int, float]:
    """The secondary rows whose agent's `MATCH_TOLERANCES` function gives a
    window wider than their own, with that window: how far after the row a
    primary row may be and still match."""
    windows: dict[int, float] = {}
    for j, (r, tolerance) in enumerate(secondary):
        window = MATCH_TOLERANCES.get(r.agent)
        wider = window(r) if window else None
        if wider is not None and wider > tolerance:
            windows[j] = wider
    return windows


def deduplicate(
    primary: list[Row], secondary: list[tuple[Row, float]]
) -> tuple[list[Row], Counter[str]]:
    """The rows to keep (every primary row, then the secondary rows with no
    primary match and no copy kept before them, in the order given) and
    the dropped rows per agent. Each secondary row comes with its
    tolerance in seconds. Every secondary row kept gets `recovered` "yes",
    since no primary row holds its event, except a `system` row, which
    describes the source itself (a header, a record, a `parser:` problem)
    rather than a lost event; this is where the field is set. A row whose
    agent registered a `MATCH_TOLERANCES` function may pair with a primary
    row up to that function's window after it (its source's window still
    bounds the search backwards and among secondary rows), and not with a
    primary row recorded at or after the next secondary row of the same
    text that could take that primary row (`_Bounds`)."""
    forward = _forward_windows(secondary)
    bounds = _Bounds(secondary) if forward else None
    matched = set(_against_primary(primary, secondary, bounds, forward))
    dropped = matched | set(_among_secondary(secondary, matched))
    counts: Counter[str] = Counter(secondary[j][0].agent for j in dropped)
    survivors = [r for j, (r, _) in enumerate(secondary) if j not in dropped]
    for r in survivors:
        if r.turn_type != "system":
            r.recovered = "yes"
    return list(primary) + survivors, counts
