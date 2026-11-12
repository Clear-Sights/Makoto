# Makoto

Makoto holds a final answer while a file changed this session, or a file that uses a changed file, has not been run
since. It works in any language and needs no git.

## How it decides

At session start Makoto records two things about the files under the working directory: a snapshot (path, size,
modified time) and a lookup of which file uses which. A file uses another when one of its import-style lines
(`import`, `from`, `require`, `include`, `use`, `source`, `load`) names the other's module path or base name. The
lookup is read again for files that change.

- **changed**: files that differ from the snapshot.
- **demanded**: changed files, plus every file that uses them, directly or through others. Only files that are in the
  lookup (use or are used by another file) or start with `#!` are demanded. Plain documents and loose data files
  with no import-style link are not.
- **checked**: demanded files reached by a run that succeeded and began after their last change (for a user of a
  changed file: after the latest change among the files it uses). A run reaches the program it names and everything
  that program uses. A test runner named with no program argument (pytest, `python -m pytest`, go test, cargo test,
  npm test, make) reaches every file.

A run failed when the tool call failed or its output holds an error marker (a Traceback, `...Error:` at a line
start, `exit=N`, `FAILED`, `panic:`, `command not found`, `No such file or directory`). A failed run checks nothing.

## The message

One message names the demanded files not yet checked and the entry programs (files no other file uses) that reach
them: `Not run since a change: lib.py, main.py, u1.py. Run main.py and read the output.`

- After a Write, Edit, MultiEdit or NotebookEdit it arrives as a note, once per changed file until checked.
- At the final answer (Stop, or a subagent's SubagentStop) it is a hold, once: a Stop that follows a hold
  (`stop_hook_active`) is let through.

## What it never does

It never blocks the user's prompt or session start, edits nothing, runs nothing, calls no model and sends nothing
anywhere. Its only other block is an error in Makoto itself (unreadable input, state lock busy, unwritable state),
which names the error and the one way out.

## Install

Claude Code 2.1.275 or later, Python 3.11 or later, standard library only:

    /plugin install makoto --marketplace Clear-Sights/Makoto

Hooks (`plugin/hooks/hooks.json`): SessionStart and UserPromptSubmit (snapshot and lookup, never block),
PostToolUse and PostToolUseFailure (record runs; the note), Stop and SubagentStop (the hold).

## Disable

    claude plugin disable makoto

## State

One JSON file per session, `~/.claude/makoto2_state/<sha256 of session id>.json`, written under a lock: the snapshot
(at most 20,000 files, skipping only `.git`, `node_modules`, `__pycache__`, `.venv` and `venv` by name, and files git
ignores), the lookup's raw names, the runs. `MAKOTO_STATE_DIR` moves it; `MAKOTO_LOCK_SECONDS` (default 3) sets how
long a busy lock is waited for.

## Tests

    python3 -m pytest -q tests

`tests/test_makoto.py` drives the hooks.json command with real temporary directories, with and without a git
repository. The code is `plugin/makoto2.py`. License: see LICENSE and NOTICE.
