"""Open Interpreter transcripts.

The current Open Interpreter is a Rust fork of Codex CLI that keeps Codex's rollout format under
`~/.openinterpreter`; checked against openinterpreter/openinterpreter at 2767e5f, with the record
shapes in `research/open-interpreter.md`. The shared `RolloutParser` in `codex.py` and the SQLite
readers in `codex_state.py` read every store, so the fields they list apply. Files:

* `.openinterpreter/sessions/YYYY/MM/DD/rollout-<timestamp>-<uuid>.jsonl` and the same under
  `archived_sessions/`, plain or `.jsonl.zst`. `session_meta.originator` is still
  `codex_cli_rs`, so only the file's location tells the fork from Codex. The fork keeps approval
  requests out of the rollout, so there is no per-call decision row.
* `history.jsonl` (`session_id`, `ts`, `text`): a secondary source.
* `state_5.sqlite` and `thread_history_1.sqlite`: Codex's schema up to migration 0006, without
  the item lifecycle times of 0007, so every item row takes `created_at_ms`; secondary sources.
* `logs_2.sqlite`: Codex's tracing log; each sent `/feedback` report gives a `session synced:`
  row, so `records_sync` is inherited and set.
* `config.toml`, `rules/*.rules`, `memories/rollout_summaries/*.md` and
  `db-backups/sqlite-*/state_5.sqlite`: read as for Codex at ac1fcc8 (source-derived). The fork
  has no `guardian_review_feedback` table, so no guardian review row occurs.
* `external_agent_session_imports.json`: the `/import` ledger, `records[]` with `source_path`,
  `content_sha256`, `imported_thread_id`, `imported_at` and optional `source_modified_at` (epoch
  seconds). Each record gives one `system` row with the imported thread's id as `session_id`:
  that rollout's turns were written in another agent and their times are import time.

Not parsed: `session_index.jsonl` (thread renames) and the zcode harness's oversized tool
results under `.zcode/cli/artifacts/`.
"""

from __future__ import annotations

from .codex import RolloutParser


class OpenInterpreterParser(RolloutParser):
    """Read Open Interpreter's Codex-format stores under `~/.openinterpreter`."""

    agent = "open-interpreter"
    name = "open-interpreter"
    home_prefix = ".openinterpreter"
    ledger_name = "external_agent_session_imports.json"
