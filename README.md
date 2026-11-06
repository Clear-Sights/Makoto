# Makoto

Makoto is a Claude Code hook. Before a dependent step runs (Write, Edit, MultiEdit, NotebookEdit,
Bash `git commit`/`git push`, or Stop), it checks the session record. If a reading the step needs
is missing, it holds the step: a PreToolUse step gets a native deny and a Stop gets a native block.
The hold names the rule, its shape, the exact subject, the one Immediacy rule it enforces and the missing reading. An admitted step gets `{}`. The checker uses no model and no network.

## Install

Claude Code 2.1.275 or later:

    /plugin install makoto --marketplace Clear-Sights/Makoto

`plugin/hooks/hooks.json` sends each native event to `cd plugin && python3 -m makoto2`. Makoto
needs Python 3.11 or later and uses only the standard library.

## The principle

Makoto is deterministic enforcement of Immediacy:

    IMMEDIACY: A more immediate read assumes less.
      + Original: Read the original instead of a derivation.
      − Unchanged: Do not assume what can change has not.

Code decides every hold from the session record. An admitted step gets `{}`: Makoto adds nothing to
the model's context, so no check depends on the model reading injected text. A hold states the rule
it enforces and the specific missing reading, and asks no question. Three paths turn a decided hold
into text only: the `MAKOTO_BLOCK_IN` report, the `stop_cap`
admission and the infrastructure fail-open.

## The four rules

- **a (lineage), enforces Original:** the step needs an original artifact reading. Assistant text, worker answers and
  readings of files this session wrote do not count. A completed run, query or request response
  does count, and a run of a session-written script reads that script's response.
- **b (spec), enforces Original:** each name the step uses (path, URL, email, identifier, hash, UUID, version) must
  appear with its exact characters in an earlier tool input, an original response, or the user
  prompt. Writer targets and files this session wrote are outputs, so b does not apply to them.
- **c (other point), enforces Original:** a named URL, a versioned package or a host-classified public project
  needs an online fetch or search of that subject in the current turn.
- **d (switch), enforces Unchanged:** when a step names an edited code, script or config subject, or ships session
  edits through a commit, push or final answer, a paired call must have run that subject after its
  last edit and returned output. For a config file without a shebang, a full read after the last
  edit also pays d. Reading code never pays d.

A locked, hash-linked journal keeps every turn under `~/.claude/makoto2_state`
(`MAKOTO_STATE_DIR` overrides). If `MAKOTO_BLOCK_IN` is set to a path-separated list of
directories, a hold whose cwd lies outside all of them is only reported in `systemMessage`.
The optional host envelope `makoto` (`effects`, `external_subjects`, `network_subjects`,
`invocation.subject(s)`, `turn_id`, `detio_store`) lets the host record what it saw, such as
opaque mutations, public names or the program that actually ran. The host must enforce the
decision before it runs a tool or delivers a final answer.

## Never stuck

- Only rule findings hold a step. Any other failure (state folder, lock, journal, transcript, a
  malformed host event) admits the step with a `systemMessage` naming the error.
- Every hook in hooks.json has a 10 s `timeout`. The per-session lock is never waited on longer
  than 3 s (`MAKOTO_LOCK_SECONDS`); a busy lock admits the step.
- A `stop_hook_active` Stop is held at most once per turn. A second held retry is admitted with
  its findings shown in `systemMessage` and kept in the journal (`stop_cap`).
- Each call reads only the journal rows and transcript lines added since the previous call: a
  `.ckpt` file beside the journal keeps both reads and the replayed record. A checkpoint that
  does not match is ignored and the call replays in full; `MAKOTO_CHECKPOINT=0` always does.

## Development

`python3 -m pytest -q` runs `tests/`. For each of rules a-d, `test_rules.py` sends a plant
and its twin through the exact hooks.json command: the plant is held and the twin is admitted.
`test_robust.py` plants each way a session could get stuck and checks that checkpointed calls
decide exactly as full replay does.
`scripts/measure_cost.py` reports per-hook wall time (cold and warm bytecode) and the bytes a hook
adds to the model's context, on the events `tests/` already contains; `MEASURE_REPEAT` sets the repeat count.
The full suite, fixtures, tools and records live in Clear-Sights/Makoto-Dev. This repository
receives only finished versions. The cut `mesh/` gate is kept in git history at 295bf44.
