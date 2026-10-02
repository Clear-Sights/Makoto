# Makoto 4.0.0

[![CI](https://github.com/Clear-Sights/Makoto/actions/workflows/ci.yml/badge.svg)](https://github.com/Clear-Sights/Makoto/actions/workflows/ci.yml)

“Makoto prevents blindspots through detection”
(cmsg_01CZb217TBsj7a1uAAdtXepP3dgKHAVmDP8Nk9f2nVV5uu, 2026-10-01T21:41Z).

The shipped runtime is an integrity hook for Claude Code. It checks statements
against the agent's observed tool effects, blocking a finding or staying silent.
It does not certify code quality or correctness. Live-session outcomes remain
unmeasured.

## Install

```
/plugin marketplace add Clear-Sights/Makoto
/plugin install makoto@makoto
```

The marketplace points at `plugin/`. [hooks.json](plugin/hooks/hooks.json) wires
PreToolUse, PostToolUse, PostToolUseFailure, Stop, SubagentStop and UserPromptSubmit
to `cd "${CLAUDE_PLUGIN_ROOT}" && python3 -m makoto2`. Python 3.11 or newer is
required; the runtime uses only the standard library.

## Skill triggers

Makoto also carries advisory, fail-silent triggers for cheap-execution,
adversarial-review and harness-execution. They read the user's installed skills
at session start and relevant tool calls, without a setup step, and never block
tool calls. The layer uses
Python 3's standard library and keeps its independent state in
`${CLAUDE_PLUGIN_DATA:-$HOME/.cache/makoto}/skill-triggers`.

## Runtime and rules

[observed.py](plugin/makoto2/observed.py) records settled tool effects.
[rows.tsv](plugin/makoto2/rows.tsv) holds 12 rules and their historical source
quotes. [evaluate.py](plugin/makoto2/evaluate.py) evaluates those rules, and
[hook.py](plugin/makoto2/hook.py) emits a pre-tool denial or a Stop/SubagentStop
block. Other events record effects or mark turn boundaries. Findings fire once
per rule, object and observed object state; there is no advisory output.

The rules cover redundant permission questions, repeated worker starts,
rebriefing without fetching, unsupported absence claims, unattributed thread
claims, inaccurate quotes, unread plans, unchanged retries after refusal,
implicit time limits, unwitnessed completion, unread counts and repeated probes.
Completion witnesses must match the named subject and operation. Pending launch
acknowledgements, empty or invalid artifacts, named failures and superseded
successes cannot stand in for terminal success. This is a bounded evaluator,
not a claim that every integrity failure is detected. No claim reader is shipped.

State is appended lazily to session JSONL files in `~/.claude/makoto2_state`.
Set `MAKOTO_STATE_DIR` to choose another directory. Runtime defaults are in
[config.json](plugin/makoto2/config.json), with keys documented in
[CONFIG_KEYS.txt](plugin/makoto2/CONFIG_KEYS.txt). Some historical rule inputs
refer to external words files; those are not bundled or created by installation.

For a workspace that wants explicit worker contracts, set `dispatch = true` in
its `makoto.toml`. The default is off; false, absent or invalid declarations
keep the existing behavior. R04 requires filled, case-sensitive `READ:`,
`WRITE:` and `ACCEPTANCE:` fields on Agent/Task briefs. R08 requires each READ
input token to carry its own `@` followed by at least 12 hexadecimal digits;
READ lists can span lines and use whitespace or commas. R11 blocks recognized
done/fixed/finished/completed assertions until every accepted brief's literal
ACCEPTANCE command has a later settled Bash execution with explicit exit zero.
Background launches and results from workers do not pay that obligation.
Accepted Pre briefs are stored as contracts and never treated as settled effects.
This checks declared pins and delivered outcomes; it does not prove snapshots
or causal validity, or govern expensive Bash calls without a declared READ list.

## Verify

```
python -m pip install pytest
python -m pytest -q tests
```

CI runs the suite on Linux with Python 3.11, 3.12 and 3.13, and on macOS and
Windows with Python 3.13. Tests include a blocking plant and silent look-alike
for every rule, observed-effect cases, completion witness cases, and six hook
assertions executed during collection. [sources.tsv](tests/sources.tsv) pins
historical quotes inside the repository; tests do not depend on changing live
memory files. A pin records historical text, not independently verified provenance.

Manual release reads version `4.0.0` from the plugin manifest to derive its tag.
The old catalog, CLI, packaging and replay tooling have been replaced by this
runtime and suite.

## Uninstall

```
/plugin uninstall makoto
```

Uninstall preserves the state directory. Earlier standalone installations should
remove their old manually managed hook entries before enabling the plugin to
avoid running both implementations.
