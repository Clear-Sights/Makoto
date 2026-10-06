# Makoto 5.0.0-dev

Makoto surfaces the session's reading lineage before dependent writes, git
commit/push and final answers. The summary reports facts under LINEAGE, OTHER
POINT, SWITCH and SPEC, with empty categories silent and counted list caps.
PreToolUse receives `additionalContext`. Stop blocks once to show the surface;
`stop_hook_active` suppresses its repetition while exact unpaid obligations
continue to block. An empty ledger produces an empty surface.

`inferred` is the only adapter and the default. Exact path/URL names and trace
values identify record gaps for awareness; they do not create source obligations.
Only host-registered obligations and recorded stale mutation subjects cause hard
holds. An existing target changed this session, or a named mutated subject, needs
a complete content reading after the recorded mutation at its destination.
The declared adapter and its basis grammar have been removed.

Host-owned `makoto.obligations` and `makoto.dependencies` specify exact reading
contracts for the four families. The host envelope is trusted instrumentation outside tool inputs: it must never
be copied from assistant-authored receipt declarations. Its `turn_id`, `place`,
`definitions`, `reads`, `effects`, `invocation`, `aliases` and `destination`
provide exact identities, selectors, origins, versions and points. Definitions
register on UserPromptSubmit or an internal Register event. Instrument arbitrary
shell effects and commit/push snapshot dependencies explicitly. Cross-session
receipt imports are not implemented; parent and worker ledgers stay separate.

Native Read, Grep, WebFetch and restricted single-file `cat` observations require
paired PreToolUse/PostToolUse IDs. Grep supplies its exact query selector,
WebFetch its requested representation selector, and partial Read its region
selector. Empty returned content counts. Completed nonzero probe responses
count; pending calls, replayed IDs, background launches and failed reads do not.
Writes never pay source obligations. Read-back of a session-written subject is
a relay unless the host explicitly attests an original source role. General
Bash calls without subject/effect instrumentation are journaled as unknown.

PreToolUse denies every unpaid attempt. Stop and SubagentStop block every unpaid
final, including retries with `stop_hook_active`; those retries are recorded.
The host must enforce these decisions before execution/delivery. The example
`tools/deliver.py` owns final stdout and emits text only after an admitted Stop.
It does not install final-message interception into another host. Native Stop
pre-delivery timing has not been independently validated here.

Session state is a locked, hash-linked append-only journal in
`~/.claude/makoto2_state`; `MAKOTO_STATE_DIR` overrides it. Every output records
its obligations and prior reading IDs. Mutation reservations invalidate affected
current receipts before settlement; partial failure keeps the reservation until
host-attested no-effect clearance. Corruption and invalid input fail closed as
transport/contract errors. Unknown instrumentation is recorded separately from
missing-reading findings. External changes require host epoch/effect records.
The runtime does not probe source files or execute missing checks itself.

Install through the existing marketplace:

```text
/plugin marketplace add Clear-Sights/Makoto
/plugin install makoto@makoto
```

Python 3.11 or later is required; runtime dependencies are standard library only.
Run the generated plants and retained applicable regressions with:

```sh
python3 -m pytest -q tests
```

The grading entry point is `tools/run_pairs.py INPUT.json --adapter inferred`.
It accepts a session list or `{"sessions": [...]}`. Each session contains `id`,
`events`, zero-based `step_index`, and optional relative-path `files`. It uses
fresh temporary state/cwd and the live `python -m makoto2` entry for every event,
then prints JSON with the selected step's `held` flag and exact emitted `surface`. It never executes recorded
commands or opens recorded source subjects. Historical evidence remains in the
repository for audit; old corpus accuracy counts do not grade these predicates.

These checks establish exact presence under their record contract. They cannot
recover undeclared prose dependencies, unobserved external mutations, hidden
branch choices or unavailable source provenance. Universal 100% accuracy over
free prose has not been established.
