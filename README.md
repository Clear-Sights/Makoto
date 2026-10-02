# Makoto 4.0.1

[![CI](https://github.com/Clear-Sights/Makoto/actions/workflows/ci.yml/badge.svg)](https://github.com/Clear-Sights/Makoto/actions/workflows/ci.yml)

“Makoto prevents blindspots through detection”
(cmsg_01CZb217TBsj7a1uAAdtXepP3dgKHAVmDP8Nk9f2nVV5uu, 2026-10-01T21:41Z).

Makoto enforces the blindspot register through Claude Code hooks. It checks
source text and observed tool effects, blocking a finding or staying silent.
Live-session outcomes remain unmeasured.

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
[rows.tsv](plugin/makoto2/rows.tsv) holds historical rules and source quotes.
[evaluate.py](plugin/makoto2/evaluate.py) runs the register's SPEC, OTHER POINT,
SWITCH and LINEAGE families before the remaining historical rules, and
[hook.py](plugin/makoto2/hook.py) emits a pre-tool denial or a Stop/SubagentStop
block. Other events record effects or mark turn boundaries. Findings are
deduplicated by rule, object and recorded state; SPEC findings
include event history in that state. There is no advisory output.

The claim reader uses a fixed word table, with no semantic classifier. Source
references require prior readings; available current readings are checked for
drift. This is a bounded evaluator.

State is appended lazily to session JSONL files in `~/.claude/makoto2_state`.
Set `MAKOTO_STATE_DIR` to choose another directory. Runtime defaults are in
[config.json](plugin/makoto2/config.json), with keys documented in
[CONFIG_KEYS.txt](plugin/makoto2/CONFIG_KEYS.txt). Some historical rule inputs
refer to external words files; those are not bundled or created by installation.

For a workspace that wants explicit worker contracts, set `dispatch = true` in
its `makoto.toml`. The default is off; false, absent or invalid declarations
keep the existing behavior. R04 requires case-sensitive `READ:`,
`WRITE:` and `ACCEPTANCE:` labels on Agent briefs. R08 checks Agent briefs for `@` followed by at least 12 lowercase
hexadecimal digits on a `READ:` line; it does not validate every input token.
READ lists can span lines and use whitespace or commas. With dispatch enabled,
Stop requires an observed exit-zero execution of each Agent ACCEPTANCE command
even when the closing text makes no completion claim. Recognized completion
claims also require later settled acceptance executions for Agent/Task briefs.
Background launches and results from workers do not pay that obligation.
Accepted Pre briefs are stored as contracts and never treated as settled effects.
These checks do not prove snapshots or causal validity.

## Verify

```
python -m pip install pytest
python -m pytest -q tests
```

CI runs the suite on Linux with Python 3.11, 3.12 and 3.13, and on macOS and
Windows with Python 3.13. Tests cover register-family predicates, observed
effects, dispatch contracts, completion witnesses, and six hook assertions
executed during collection. [sources.tsv](tests/sources.tsv) pins
historical quotes inside the repository; tests do not depend on changing live
memory files. A pin records historical text, not independently verified provenance.

Manual release reads the version from the plugin manifest to derive its tag.
The old catalog, CLI, packaging and replay tooling have been replaced by this
runtime and suite.

## Mesh and handoff

[mesh/README.md](mesh/README.md) describes the requirement model and its checks.
[PLAN.md](PLAN.md) records dependency waves; [HANDOFF.md](HANDOFF.md) describes
how to resume and distinguish model validity from implementation evidence.
The pinned README in `mesh/reference/` is a historical source snapshot.

## Uninstall

```
/plugin uninstall makoto
```

Uninstall preserves the state directory. Earlier standalone installations should
remove their old manually managed hook entries before enabling the plugin to
avoid running both implementations.
