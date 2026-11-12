# Makoto

Makoto holds a final answer while a file changed this session, or a file that depends on it, has not been run since.
It works in any language and needs no git.

## The map

Makoto's whole state is one map of the files under the working directory.

- **Node**, one per file: its size and modified time at session start, the start time of the last successful run
  that reached it, a failed flag, and a noted flag.
- **Link**, from a file to a file it depends on, read from the files' text and read again for files that change:
  - **uses**: an import-style line (`import`, `from`, `require`, `include`, `use`, `source`, `load`) names the other
    file's module path or base name;
  - **reads**: a quoted string names another project file by relative path or base name with extension;
  - **produced by**: the same, on a line with a write marker (`>`, `>>`, a `'w'` or `'a'` mode, `write`, `dump`,
    `save`, `to_csv`, `to_json`). The link points from the data file to the file that writes it.

A run is not kept. A successful run stamps its start time on every node it reaches; a failed run sets their failed
flag. A run reaches the program it names and everything that program depends on, so a run of a script that reads
`out.json` reaches `out.json` and the script that writes it. A test runner with no program argument (pytest,
`python -m pytest`, go test, cargo test, npm test, make) reaches every file.

## What is demanded

- **changed**: files that differ from their session-start size or time, and new files.
- **demanded**: changed files that are runnable (a known interpreter's extension, or a `#!` line) or tied to another
  file by a uses or reads link, plus every file that reaches a changed file through links. A changed script is
  demanded even with no link. Plain documents and loose data files with no link are not.
- **checked**: demanded files stamped after the latest change among the changed files they reach.

## What checks it

A run that succeeded. It failed when the tool call failed or its output holds an error marker (a Traceback,
`...Error:` at a line start, `exit=N`, `FAILED`, `panic:`, `command not found`, `No such file or directory`); a
failed run checks nothing and the message then says the file needs a run that succeeds.

## The message

One message names the demanded files not yet checked and the entry programs (files no other file depends on) that
reach them: `Not run since a change: lib.py, main.py, u1.py. Run main.py and read the output.`

- After a Write, Edit, MultiEdit or NotebookEdit it arrives as a note, once per changed file until checked.
- At the final answer (Stop, or a subagent's SubagentStop) it is a hold, once: a Stop that follows a hold
  (`stop_hook_active`) is let through.

It never blocks the user's prompt or session start, edits nothing, runs nothing and calls no model. Its only other
block is an error in Makoto itself (unreadable input, state lock busy, unwritable state), which names the error and
the one way out.

## State

One JSON file per session, `~/.claude/makoto2_state/<sha256 of session id>.json`, written under a lock: the map and
nothing else. No list of runs, reads, notes or unpaid files. It never grows with the session; its size is bounded by
the tree's files (at most 20,000, skipping only `.git`, `node_modules`, `__pycache__`, `.venv` and `venv` by name,
and files git ignores) and their links. `MAKOTO_STATE_DIR` moves it; `MAKOTO_LOCK_SECONDS` (default 3) sets how long
a busy lock is waited for.

## Limits

- Literal paths only: a path built at run time, or a name that is not quoted, makes no link.
- Per file, not per function: any change to a file demands everything that depends on the file.
- A run is judged by the tool call and its output markers, not by what the program did.

## Install

Claude Code 2.1.275 or later, Python 3.11 or later, standard library only:

    /plugin install makoto --marketplace Clear-Sights/Makoto

Hooks (`plugin/hooks/hooks.json`): SessionStart and UserPromptSubmit (build the map, never block), PostToolUse and
PostToolUseFailure (stamp runs; the note), Stop and SubagentStop (the hold).

## Disable

    claude plugin disable makoto

## Tests

    python3 -m pytest -q tests

`tests/test_makoto.py` drives the hooks.json command with real temporary directories, with and without a git
repository. The code is `plugin/makoto2.py`. License: see LICENSE and NOTICE.
