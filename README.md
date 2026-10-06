# Makoto 5.0.0-dev

Makoto holds dependent steps until their required readings are in the session's
hook record. It checks presence, not whether a reading agrees with a claim.
One ledger and four predicates replace the previous heuristic decision engine.

The four shapes are SPEC (a held definition and its subject reading), OTHER
POINT (two distinct readings of the same subject at required points), SWITCH
(an exact input invocation and its paired completed response), and LINEAGE
(original source readings this turn before the dependent output).

Choose `declared` or `inferred` with `MAKOTO_ADAPTER`, or the `adapter` key in
`plugin/makoto2/config.json`. `declared` is the default.

The declared adapter requires a basis line in a tool input's `description` or
leading comment, and in the final assistant message:

```text
makoto-basis: source=path; second=path@revision; act=cat path->path; def=definition-id:path
```

Each field accepts comma-separated entries. An empty `makoto-basis:` declares
a novel output with no dependencies. Write, Edit, MultiEdit, NotebookEdit,
Bash git commit/push and final messages require the line. A trace value from
this turn's source readings also needs coverage in the line. Definitions must
already be registered by the operator/host. Named second points resolve through
host `makoto.points`, or an exact revision string. Commands with commas or
semicolons need host obligation records instead of this compact grammar.

The inferred adapter binds exact recorded paths/URLs named in content and exact
trace values to source receipts. A named mutated subject also requires an
observation after the mutation at its recorded destination. SPEC and SWITCH
come only from exact host obligation records; arbitrary prose does not establish
a definition or a selected branch. Numeric tokens have at least three digits;
paths, URLs, `id:` tokens and hexadecimal identifiers use structural parsing.

Both adapters accept host-owned `makoto.obligations` and `makoto.dependencies`.
The host envelope is trusted instrumentation outside tool inputs: it must never
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

The grading entry point is `tools/run_pairs.py INPUT.json --adapter declared|inferred`.
It accepts a session list or `{"sessions": [...]}`. Each session contains `id`,
`events`, zero-based `step_index`, and optional relative-path `files`. It uses
fresh temporary state/cwd and the live `python -m makoto2` entry for every event,
then prints JSON with the selected step's `held` flag. It never executes recorded
commands or opens recorded source subjects. Historical evidence remains in the
repository for audit; old corpus accuracy counts do not grade these predicates.

These checks establish exact presence under their record contract. They cannot
recover undeclared prose dependencies, unobserved external mutations, hidden
branch choices or unavailable source provenance. Universal 100% accuracy over
free prose has not been established.
