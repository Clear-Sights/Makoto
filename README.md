# Makoto

Makoto does one job: it holds a final answer while a file changed this session has not been checked since it changed.
It works for code in any language, and for config and data files. It needs no git.

## What it holds

When Claude Code is about to give its final answer (Stop, or a subagent's SubagentStop), Makoto compares the files
under the working directory with a snapshot taken when the session started. A file that is new or different is
unchecked until something checks it. Held files:

- code and scripts in any language, by extension (py, js, ts, go, rs, rb, php, java, c, sh and many more) or by a
  `#!` line;
- config and data files (json, yaml, toml, ini, cfg, env, xml, csv and similar).

Plain documents (md, txt, rst) are never held. A file that was already different before the session began is in the
snapshot, so it is never held. Makoto reads the file system, not the edits, so a change made by a script, a build
or a shell command is seen like any other.

## What pays

A completed program or test run that succeeded and started after the file's last change pays it, when the run reaches the file: it
names the file, or names a program or test in the same top-level folder, or it is a project-wide runner (make,
npm/yarn/pnpm run, test or start, pytest, jest, vitest, mocha, go test, cargo run or test, npx, and the like).
Recognised runs: python, node, deno, bun, ruby, perl, php, go run/test/build, cargo run/test, java, dotnet, make,
npm/yarn/pnpm, pytest, jest, vitest, mocha, sh, bash, zsh and `./path`, including after `cd x &&`, in pipes, with
`2>&1` or with `VAR=value` prefixes. A run of something unrelated does not pay, and neither does a run that
began before the change or one that failed: the tool call failed, or its output (stdout or stderr) holds an error
marker (a Traceback, a line starting `...Error:` or `...Exception:`, `exit=N` or `exit code N` with N not 0, `FAILED`,
`panic:`, `command not found`, `No such file or directory`). The hold then ends: `Missing: a run of it that succeeds,
after its last edit. Clear: Fix the error, run it again and read its output.` The word "error" in prose is no marker. A config or data file is also paid by reading it in full after its
last change (the Read tool, or `cat`).

The hold names each unchecked file and asks for a run with its output read. It blocks once: a Stop that follows a
hold (`stop_hook_active`) is let through.

## The note

After a completed Write, Edit, MultiEdit or NotebookEdit of a code file, Makoto adds one line of context, once per
file until a run pays it: `Before your final answer, run the program or tests that use <file> and read the output.`

## What it never does

It never blocks the user's prompt or session start, never holds a plain document, never edits a file, runs
nothing and calls no model, and sends nothing anywhere. Its only block besides the hold is an error in Makoto itself
(unreadable input, state lock busy, unwritable state), which names the error and the one way out.

## Install

Claude Code 2.1.275 or later, Python 3.11 or later, standard library only:

    /plugin install makoto --marketplace Clear-Sights/Makoto

Hooks (`plugin/hooks/hooks.json`): SessionStart and UserPromptSubmit (take the snapshot, never block),
PostToolUse and PostToolUseFailure (record runs and read-backs; the note), Stop and SubagentStop.

## Disable

    claude plugin disable makoto

## State

One JSON file per session, `~/.claude/makoto2_state/<sha256 of session id>.json`, written under a lock: the
snapshot (path, size, modified time; at most 20,000 files, skipping only `.git`, `node_modules`, `__pycache__`, `.venv` and `venv` by name), the
recent runs and reads, the files already noted. `MAKOTO_STATE_DIR` moves it; `MAKOTO_LOCK_SECONDS` (default 3)
sets how long a busy lock is waited for. Git, when present, only lets Makoto skip ignored files.

## Tests

    python3 -m pytest -q tests

`tests/test_makoto.py` drives the hooks.json command with real temporary directories, with and without a git
repository. The code is `plugin/makoto2.py`. License: see LICENSE and NOTICE.
