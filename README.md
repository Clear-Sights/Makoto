# Makoto

Makoto is a Claude Code hook with one job: it holds a final answer that ships a code file edited in this session
and not run since its last edit. It uses no model and no network. Everything else is admitted without a word
(`{}`), including every edit, commit and push, and the user's own prompt.

## Install

Claude Code 2.1.275 or later:

    /plugin install makoto --marketplace Clear-Sights/Makoto

`plugin/hooks/hooks.json` sends each native event (PreToolUse, PostToolUse, PostToolUseFailure, Stop,
SubagentStop, UserPromptSubmit) to `cd "${CLAUDE_PLUGIN_ROOT}" && python3 -m makoto2`, where the plugin root is
`plugin/`. Makoto needs Python 3.11 or later and uses only the standard library.

## What it holds

Makoto records each edit (Write, Edit, MultiEdit, NotebookEdit, and Bash redirects, `touch`, `cp`, `mv`,
`sed -i`) of a code, script or config file. At a final answer (Stop, SubagentStop, or a host's PreDelivery) it
blocks while such a file has no payment after its last edit. The block names the file:

    makoto rule d [switch]: "<file>": Unchanged: Do not assume what can change has not. Missing: a run of it, with its output read, after its last edit. Clear: Run it and read its output.

Rule d is the name of this one rule; the text is the same every time. A hold is never capped: a Stop with
`stop_hook_active` is held again every time until the file is paid.

A file is paid, after its last edit, by any one of:

- a completed run of the file itself (`python3 f.py`, `node f.js`, `./f.sh`, `pytest f.py`, `go run f.go`, ...)
  that returned a response, even a failing one;
- a completed run of a Python program whose static imports, resolved from the working directory, include it;
- for a config file (json, yaml, toml, ini and the like, without a shebang), a full read: `Read` with no
  offset or limit, `cat` of that one file, or a whole-file `json.load`.

Reading code never pays. A deleted file owes nothing. A subagent's Stop is held only for the files that agent
edited.

## The note

After a completed `.py` edit inside the working directory, and once per file until it is run, the PostToolUse
response carries one line of guidance (never a block) naming the program to run:

    Before your final answer, run python3 <program> and read its output: it runs <file>.

`<program>` is a program that is not imported by another and whose imports include the file, else the file itself.

## Records

A locked, hash-linked journal keeps every event under `~/.claude/makoto2_state` (`MAKOTO_STATE_DIR`
overrides), and the host transcript is replayed with it. Each call reads only the journal rows and transcript
lines added since the previous call: a `.ckpt` file beside the journal keeps both reads and the replayed
record. A checkpoint that does not match is ignored and the call replays in full; `MAKOTO_CHECKPOINT=0` always
does. The optional host envelope `makoto` (`effects`, `reads`, `invocation.subject(s)`, `no_effect`, `turn_id`)
lets a host record what it saw, such as opaque mutations or the program that actually ran. The host must
enforce the decision before it delivers a final answer.

## Errors block, and the way out

- An error in Makoto's own work (state folder, lock, transcript, a malformed host event, `MAKOTO_ADAPTER` set
  to anything but `inferred`) blocks the step, names the error, and gives the one way to disable Makoto. The
  user's own prompt (UserPromptSubmit) is never blocked: it is admitted and, whenever the journal is writable,
  recorded.
- A corrupted journal does not stop the session. It is moved beside a fresh journal as
  `<journal>.corrupt-<ns>`, and the call decides from what can still be read (the transcript, then new calls).
- The one way to disable Makoto, if an error keeps blocking, is to run this in a terminal outside the
  session, so a broken install cannot trap you:

      claude plugin disable makoto

- Every hook in hooks.json has a 10 s `timeout`. The per-session lock is never waited on longer
  than 3 s (`MAKOTO_LOCK_SECONDS`); a busy lock blocks the step with that error.

## License

FSL-1.1-ALv2 (`LICENSE`): use, copy, modify and redistribute Makoto for any purpose except a Competing Use, which is offering it, or a product with the same or substantially similar functionality, to others as a commercial product or service. Internal use, non-commercial education and research, and professional services to a licensee are permitted. Each version becomes Apache-2.0 two years after its release. Versions up to and including 85ac4d5 stay Apache-2.0. `NOTICE` lists the Apache-2.0 excerpts from DetIO and Causality.

## Development

`python3 -m pytest -q` runs `tests/`: `test_rules.py` sends rule d's plant and its twin through the exact hooks.json
command (the plant is held, the twin is admitted); `test_lean2.py` and `test_function.py` cover what pays;
`test_lean3.py` the note; `test_chat_only.py` that a tool-less final answer is admitted; `test_robust.py` plants
each infrastructure error and checks that it blocks with the way out, and that checkpointed calls decide exactly
as full replay does.
`scripts/measure_cost.py` reports per-hook wall time (cold and warm bytecode) and the bytes a hook
adds to the model's context, on the events `tests/` already contains; `MEASURE_REPEAT` sets the repeat count.
`eval/run_corpus.py` replays a corpus of sessions (built by `eval/corpus.py` from a Clear-Sights/Tiller-from-the-Ashes
checkout) through a plugin directory and records every decision. `eval/equivalence.py` replays a corpus and a test
suite through two plugin directories and fails on any difference in a hook response.
`eval/RESULTS.md` is a historical record of Makoto before 6.0.0, which also held a, b, c and e; those no longer exist.
