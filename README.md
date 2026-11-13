# Makoto

Makoto holds a final answer while a file changed this session, or a file that depends on it, has not been run since.
It needs no git. Its rules are not tied to a language; what has been measured is under "What is measured".

## The map

Makoto's whole state is one map of the files under the working directory.

- **Node**, one per file: its size and modified time at session start, the start time of the last successful run
  that reached it, a failed flag, and a noted flag (set on an entry program an earlier note named), the hash of the last probe failure noted for it, and a named flag (set when a note has named it as an unchanged user of a changed file).
- **Link**, from a file to a file it depends on, read from the files' text and read again for files that change:
  - **uses**: an import-style line (`import`, `from`, `require`, `include`, `use`, `source`, `load`) names the other
    file's module path or base name;
  - **reads**: a quoted string names another project file by relative path or base name with extension;
  - **produced by**: the same, on a line with a write marker (`>`, `>>`, a `'w'` or `'a'` mode, `write`, `dump`,
    `save`, `to_csv`, `to_json`). The link points from the data file to the file that writes it.
  - **shell redirects**: in a shell file (extension `sh`, `bash` or `zsh`, or a shell shebang), an unquoted `> path`,
    `>> path` or `tee path` makes a produced-by link and an unquoted `< path` a reads link, when the path names a
    project file.

A run is not kept. A successful run stamps its start time on every node it reaches; a failed run sets their failed
flag. A run reaches the program it names and everything that program depends on, so a run of a script that reads
`out.json` reaches `out.json` and the script that writes it. A test runner with no program argument (pytest,
`python -m pytest`, go test, cargo test, jest, vitest, mocha, make, npm/yarn/pnpm run, test or start) reaches the
test files (a name containing `test` or `spec`, or a file under a folder named `test`, `tests`, `spec` or
`__tests__`) and everything they depend on, not every file; a changed file no test reaches stays demanded.

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

- After a completed Write, Edit, MultiEdit or NotebookEdit it arrives as a note when the tree holds a new unchecked
  change and the entry programs it names include one that no earlier note in the session named; otherwise no note. A
  run that checks the change gets no note. Twelve changes whose runs are all the same entry program give one note; a
  new entry program gives another. A change made any other way (a shell command, a script) gets no plain note and is
  caught at the final answer: measured, a note there costs more and gains nothing.
- At the final answer (Stop, or a subagent's SubagentStop) it is a hold, once: a Stop that follows a hold
  (`stop_hook_active`) is let through.

It never blocks the user's prompt or session start, edits nothing in your tree and calls no model. The only
programs it runs are the probes below. Its only other block is an error in Makoto itself (unreadable input, state lock
busy, unwritable state), which names the error and the one way out.

When Makoto has run the program itself and it failed, the message also carries the last 15 lines of the output and
ends `(run in a sandbox with no network)`.

## Makoto runs the check itself

Where the Claude Code sandbox runtime (`srt`, the `@anthropic-ai/sandbox-runtime` package) is installed, Makoto runs
the check instead of asking Claude to:

- **When:** after any completed tool call that leaves an unchecked change, and at the final answer if one remains.
- **What it runs:** every entry program the message names (a file nothing else depends on) that a known interpreter
  (python3, node, ruby, perl, php, sh, bash; by extension or `#!` line) runs with no argument, whatever it imports.
  Programs run in the same relative directory as the session, in order, with input closed, and all of them together
  get 8 seconds.
- **In which sandbox:** one `srt` call, in a temporary copy of the tree (at most 20,000 files and 50 MB), deleted
  afterwards. The sandbox allows no network and no write outside the copy, so a probe cannot change your files or send
  anything out. The settings file it uses is deleted too.
- **A pass** (exit 0, no error marker) marks the files it reached as checked, silently.
- **A pass that printed nothing** shows nothing of the change: a file that only defines functions exits 0 whether
  its callers are right or wrong. Makoto does not then ask Claude for a run it has itself seen show nothing. It
  names the files at risk instead, at once: after any tool call, every file that uses a changed file, was not
  itself changed, and is unchecked or only silently run is named once, with the changed files it uses:
  `Not changed, but uses a changed file: app/rollup.py (app/core.py). Check each against the change.`
  Measured, every failure of this kind was such a file, and the note replaces the held final answer.
- **A fail** puts the output's last 15 lines in the message, ending `(run in a sandbox with no network)`: as a note
  after any tool call, once per distinct output, and in the hold at the final answer. **A failing test file** is
  reported only at the final answer: while a change is in progress, a test states what the code did before it.
  A program that needs the network (or anything else the sandbox blocks) fails there and is reported the same way.
- **When it does not probe,** and behaves exactly as without it (the note and the hold of "The message"): `srt` is
  not found or errors; the program has no known interpreter; the copy would pass the caps; the probe times out; or the
  tree changed while the probe ran (a result counts only for the tree it read).
- **Is it active?** It is when `srt` is installed: on `PATH`, or named by the environment variable `MAKOTO_SRT`.
  No setting turns it on or off. Install it with `npm install -g @anthropic-ai/sandbox-runtime`; it needs bubblewrap
  and socat on Linux.

## State

One JSON file per session, `~/.claude/makoto2_state/<sha256 of session id>.json`, written under a lock: the map and
nothing else. No list of runs, reads, notes or unpaid files. It never grows with the session; its size is bounded by
the tree's files (at most 20,000, skipping only `.git`, `node_modules`, `__pycache__`, `.venv` and `venv` by name, any folder that holds a
`CACHEDIR.TAG` file (a tool's cache, such as `.pytest_cache`),
and files git ignores) and their links. `MAKOTO_STATE_DIR` moves it; `MAKOTO_LOCK_SECONDS` (default 3) sets how long
a busy lock is waited for.

## What is measured

Each row is 40 fresh tasks (Claude Code 2.1.323). The tasks were built for these tests, so they show what Makoto
does on tasks of these kinds and no more. The records are on the `research` branch.

**This version (6.5.0) with the sandbox runtime installed,** against 6.2.1, which had no sandboxed check
(`research/downstream/`):

| tasks | model | without Makoto | 6.2.1 | 6.5.0 with sandbox | cost: 6.2.1; 6.5.0 | held answers per run: 6.2.1; 6.5.0 |
|---|---|---|---|---|---|---|
| Python: a change with 12 dependent files | Sonnet | 33 of 40 | 40 of 40 | 40 of 40 | 1.54; 1.06 times | 1.00; 0 |
| Python: an edit that fails only when run | Sonnet | 17 of 40 | 40 of 40 | 38 of 40 | 1.52; 1.31 times | 1.00; 0 |
| Python: a change with 12 dependent files | Haiku | 34 of 40 | 39 of 40 | 38 of 40 | 1.21; 0.95 times | 1.00; 0 |
| Python: an edit that fails only when run | Haiku | 27 of 40 | 34 of 40 | 35 of 40 | 1.29; 1.25 times | 0.15; 0.08 |

- **What the sandboxed check adds:** the final answer is no longer held and thrown away. Where running the entry
  program exercises the change, Makoto reports the failure itself; where a run shows nothing, it names the files
  that use the change and were not changed.
- **Earlier builds of the sandboxed check failed** and were not kept: one counted a silent exit 0 as a check with
  nothing said, and passed fewer tasks than no Makoto (`research/collect/`); two cost more than 6.2.1 in one cell
  (`research/observed/`, `research/quiet/`). 6.4.0 kept the hold for silent files (`research/testwait/`).
- **The note is sent only with the sandbox.** Without it the hold stays and names the same files, and the note then
  only added cost (Sonnet, run-only failures: 1.63 against 1.52 times, 35 against 40 of 40).

**Without the sandbox runtime,** 6.5.0 behaves as 6.2.1 (`research/v621/` and `research/claims/`):

| tasks | model | without Makoto | with Makoto | cost with Makoto |
|---|---|---|---|---|
| Python: an edit that fails only when run | Haiku | 24 of 40 | 36 of 40 | 1.34 times |
| Python: a change with 12 dependent files | Haiku | 27 of 40 | 37 of 40 | 1.33 times |
| Python: one script writes a file another reads | Haiku | 6 of 40 | 19 of 40 | 1.44 times |
| JavaScript: an edit that fails only when run | Haiku | 40 of 40 | 40 of 40 | 1.21 times |
| Python: an edit that fails only when run | Sonnet | 16 of 40 | 38 of 40 | 1.68 times |
| Python: a change with 12 dependent files | Sonnet | 28 of 40 | 40 of 40 | 1.57 times |

- **Where it helps:** where the model would finish without running what it changed. In these tasks the goal says
  there is no need to run it, and both models then skip the run.
- **Where it only costs:** where the model already gets it right, as on the JavaScript tasks. Makoto then adds about
  a fifth to the cost and gains nothing.
- **Not measured live:** Go, Rust, Ruby and shell projects, which only the unit tests cover; Opus; tasks whose goal
  does not discourage a run; the sandboxed check on anything but the two Python task kinds above.

## Limits

- With the sandbox, a file whose run prints nothing is not held. If Claude changed such a file wrongly, nothing but
  the note on its unchanged users can catch it; no such failure occurred in the measured runs.
- A probe is a run with no argument in a copy: a program that needs arguments, input, the network or files outside the
  tree fails there, and what it prints is not a test of the real environment.
- Literal paths only: a path built at run time, or a name that is not quoted (outside shell redirects), makes no link.
- Per file, not per function: any change to a file demands everything that depends on the file.
- A run is judged by the tool call (or the probe's exit code) and its output markers, not by what the program did.

## Install

Claude Code 2.1.275 or later, Python 3.11 or later, standard library only:

    /plugin install makoto --marketplace Clear-Sights/Makoto

Hooks (`plugin/hooks/hooks.json`): SessionStart and UserPromptSubmit (build the map, never block), PostToolUse and
PostToolUseFailure (stamp runs; the note; the probe after PostToolUse, timeout 20 seconds), Stop and SubagentStop (the
probe and the hold, timeout 20 seconds).

## Disable

    claude plugin disable makoto

## Tests

    python3 -m pytest -q tests

`tests/test_makoto.py` drives the hooks.json command with real temporary directories, with and without a git
repository. The code is `plugin/makoto2.py`. License: see LICENSE and NOTICE.
