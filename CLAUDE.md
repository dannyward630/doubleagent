# CLAUDE.md

@AGENTS.md

Claude Code specific notes:

- Prefer `collectors/tests/smoke.sh dash` as the first check after any edit to
  a collector; dash is the strictest of the installed shells and catches most
  bash-isms. For the analyzer, run `analyzer/tests/run.sh`.
- Before committing Python, Markdown, sh or PowerShell, run the matching
  lint commands from "Quality gates" in [AGENTS.md](AGENTS.md#quality-gates); CI runs them, the
  pre-commit hook does not.
- The collector logs every collected path to stderr unless `-q` is passed.
  Use `-q` when running it from a tool call so the output stays readable.
- A live run against this workstation collects the author's own Claude Code,
  Gemini, Antigravity, Codex and Copilot state. Write it under the scratchpad
  directory and delete it afterwards.
- This Mac's `python3` is 3.14 without `zstandard` or `python-dateutil`, so
  `analyzer/tests/run.sh` fails at import; make a venv in the scratchpad
  (`python3 -m venv venv && venv/bin/pip install -r analyzer/requirements.txt
  ruff==0.16.10 pyright==1.1.414`), run the suite with `venv/bin/python -m
  unittest discover -s tests -t tests` from `analyzer/`, and pyright with
  `--pythonpath venv/bin/python`. `uvx`, shellcheck, shfmt and pwsh are
  not installed; CI runs those gates.
- This Mac has `/bin/dash` (macOS 26 ships it; `tests/smoke.sh dash` takes a
  few minutes) but no busybox, posh, pwsh, shellcheck or shfmt. Its
  `/bin/sh` is bash 3.2, the one shell CI does not run, and the smoke
  test passes under it since collector 1.11.0 ([issue 78](https://github.com/seanthegeek/doubleagent/issues/78) and [issue 82](https://github.com/seanthegeek/doubleagent/issues/82)): about
  17 minutes with no VM running, far longer while a Parallels VM holds
  most of the 8 GB, so never run it beside a VM. When a Linux lab VM is
  up, run dash, bash and busybox there instead (a few minutes each) and
  let CI cover the rest; run the analyzer tests here. Under fish, a string of ssh flags in a variable
  is not word-split; keep an ssh config file with host aliases in the
  scratchpad and pass it with `-F`.
- The research documents under `research/` (one per agent, a Collection part
  and a Parsing part) link every source citation to the commit that was
  reviewed. Open that link
  when checking a path or record shape; the line numbers are only valid at
  that commit, not on the default branch.
- Parser work suits delegation: give a subagent the research document and the
  "Adding a parser" checklist in [AGENTS.md](AGENTS.md#adding-a-parser), one agent per parser, and reserve
  the main session for review. The same pattern, one agent per lineage pair,
  did the citation linking pass.

## Orchestration

Work in this repository is split by model to keep Fable usage for the parts
that need it:

- **Fable plans.** The main session, on Fable, scopes the task, reads what it
  needs to write a precise brief, and decides how to split the work.
- **Opus implements.** Every implementation step goes to a subagent with
  `model: opus`: parsers, catalog research, citation passes, and the
  integration that merges the pieces. One subagent per self-contained unit
  (one parser, one research document, one lineage pair), launched in
  parallel. When several units touch the same files, give each subagent
  `isolation: worktree`, tell it to commit on its branch without pushing,
  keep shared-file edits append-only, and send one more Opus subagent to
  merge the branches and resolve the predictable overlaps (registries,
  fixtures, test classes, README tables).
- **Fable reviews.** The main session reads each subagent's report, checks
  the diff against the brief and the research documents, runs the test
  suite itself, fixes or sends back what is wrong, then commits, pushes
  the branch and opens the pull request. The user merges it and decides
  on any tag; the rules are under [Conventions](AGENTS.md#conventions) in
  AGENTS.md. Subagent reports are evidence, not approval; a claim that
  tests pass is re-run, not trusted.

For a real-install round of a CLI agent, Fable drives the agent in the
VM itself (ssh + a detached `screen`, one listing per step) and the user
does only the browser, phone and GUI steps; the rules are under
[Real-install rounds](AGENTS.md#real-install-rounds) in AGENTS.md.

The brief for each subagent lives in the scratchpad as one file every
subagent in that round reads, so the rules are identical and the prompt per
agent is only its assignment. The brief names the files to read first, the
rules that must hold, the files the agent may and may not touch, and the
report format.

If Fable becomes unavailable mid-task (a usage-limit or rate-limit error
from the API), say so to the user in plain words before doing anything
else, then continue with Opus: run the planning and review steps through
`model: opus` subagents rather than stopping, and label the result as
Opus-reviewed so the user can decide whether a Fable pass is still wanted.
Never fabricate a report from a subagent that was cut off; relaunch it.
