# Makoto

Makoto holds a final answer while a file changed this session, or a file that uses a changed file, has not been run
since. It works in any language and needs no git. This variant can also run the project's own programs itself, to
check for you; see "The probe", which says exactly when it does and when it does not.

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
them: `Not run since a change: lib.py, main.py, u1.py. Run main.py and read the output.` There is no note after an
edit.

## The probe: Makoto runs project programs itself

At the final answer (Stop, or a subagent's SubagentStop), if demanded files are unchecked, Makoto runs the entry
programs that reach them. **This executes your project's code, by Makoto, not by Claude.** It does so only like this:

- **In an isolated copy.** The files under the working directory (the same set the snapshot uses) are copied to a new
  temporary directory, and the programs run there, in the same relative directory as the session, never in the real
  tree. The copy is deleted afterwards. Nothing is written into the real tree.
- **With no network.** `unshare -rn` on Linux, `sandbox-exec -n no-network` on macOS. If neither works on the
  machine, Makoto runs nothing and behaves as in "The hold" below.
- **Scrubbed.** The environment is PATH, HOME (the temporary directory) and LANG only; input is closed; each program
  gets 5 seconds, and the whole probe about 22.
- **Only these programs.** Programs a known interpreter (python3, node, ruby, perl, php, sh, bash; by extension or
  `#!` line) runs with no argument. Nothing else is run.
- **Never an outward program.** A file is outward when an import-style line names a network library (socket, ssl,
  http, urllib, requests, httpx, aiohttp, websockets, ftplib, smtplib, paramiko, boto3, grpc, net/http, axios,
  node-fetch, fetch, net, dgram, open-uri) or a process library (subprocess, multiprocessing, child_process,
  os/exec, pty). An entry program that reaches an outward file through the lookup is not probed. The lookup cannot
  see a shell string, a computed import or an environment switch, so the isolated copy with no network is the
  backstop, not the gate.
- **Not at all** when the copy would exceed 20,000 files or 50 MB.

A probe passes when the program exits 0 and its output holds no error marker. The files it reaches are then checked
and, if nothing else is unchecked, the final answer is admitted with no message. A probe that fails holds with the
message plus the last 15 lines of its output, at most 3 times per final answer, then the answer is admitted. A probe
that times out is neither a pass nor a failure.

## The hold

What no probe checked (an outward or unrunnable program, a timeout, no isolation, a copy over the caps) is held as
the message, once: a Stop that follows (`stop_hook_active`) is let through.

## What it never does

It never blocks the user's prompt or session start, never edits the real tree, calls no model and sends nothing
anywhere. The only programs it runs are the probes above. Its only other block is an error in Makoto itself (unreadable input, state lock busy, unwritable state),
which names the error and the one way out.

## Install

Claude Code 2.1.275 or later, Python 3.11 or later, standard library only:

    /plugin install makoto --marketplace Clear-Sights/Makoto

Hooks (`plugin/hooks/hooks.json`): SessionStart and UserPromptSubmit (snapshot and lookup, never block),
PostToolUse and PostToolUseFailure (record runs), Stop and SubagentStop (the probe and the hold; timeout 30 seconds).

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
