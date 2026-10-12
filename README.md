# Makoto

Makoto is a Claude Code hook. Before a dependent step runs (Write, Edit, MultiEdit, NotebookEdit,
Bash `git commit`/`git push`, or Stop), it checks the session record. If a reading the step needs
is missing, it holds the step: a PreToolUse step gets a native deny and a Stop gets a native block.
The hold names the rule, its shape and the exact subject. The checker uses no model and no network.

## Install

Claude Code 2.1.275 or later:

    /plugin install makoto --marketplace Clear-Sights/Makoto

`plugin/hooks/hooks.json` sends each native event to `cd plugin && python3 -m makoto2`. Makoto
needs Python 3.11 or later and uses only the standard library.

## The four questions

Every admitted dependent PreToolUse step receives these questions as `additionalContext`. An
admitted Stop shows them once as its block reason, and a `stop_hook_active` retry that is
otherwise admitted gets `{}`:

"Before this step: (1) If it relies on a definition, did you read the thing itself against that definition? (2) If it carries a result to another place or time, did you read the same thing again where and when it lands? (3) If it says how a branch behaves, did you feed that branch an input and read its response? (4) Is it based on the original source, read this turn, rather than on an earlier answer?"

## The four rules

- **a (lineage):** the step needs an original artifact reading. Assistant text, worker answers and
  readings of files this session wrote do not count. A completed run, query or request response
  does count, and a run of a session-written script reads that script's response.
- **b (spec):** each name the step uses (path, URL, email, identifier, hash, UUID, version) must
  appear with its exact characters in an earlier tool input, an original response, or the user
  prompt. Writer targets and files this session wrote are outputs, so b does not apply to them.
- **c (other point):** a named URL, a versioned package or a host-classified public project
  needs an online fetch or search of that subject in the current turn.
- **d (switch):** when a step names an edited code, script or config subject, or ships session
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

## Development

`python3 -m pytest -q` runs `tests/test_rules.py`. For each of rules a-d, the test sends a plant
and its twin through the exact hooks.json command: the plant is held and the twin is admitted.
The full suite, fixtures, tools and records live in Clear-Sights/Makoto-Dev. This repository
receives only finished versions. The cut `mesh/` gate is kept in git history at 295bf44.
