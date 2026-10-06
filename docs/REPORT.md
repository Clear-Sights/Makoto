Makoto 5.0.0-dev now uses one session reading ledger and four presence predicates.
The legacy heuristic decision route and rows engine have been removed.
Both obligation adapters use the same live hook, ledger, predicates and journals.
Declared requires a makoto-basis line on dependent writes, git commit/push and finals.
Declared covers source, second-point, exact-act and definition-bound reading obligations.
Declared also holds trace values from this turn's sources omitted from the basis line.
Declared cannot recover dependencies that neither the basis nor host record exposes.
Inferred covers exact recorded paths/URLs and trace values with current original sources.
Inferred adds destination read-back after recorded mutation, transfer, push or deployment.
Inferred gets SPEC and SWITCH only from exact host obligation records, without word lists.
Inferred cannot infer free-prose meaning, hidden branches or unrecorded external changes.
Native paired Read, Grep, WebFetch and restricted cat receipts feed the shared ledger.
PreToolUse and Stop/SubagentStop hold every unpaid attempt, including unchanged retries.
97 tests passed in 4.13 seconds; all eight family/adapter present-absent pairs use live hooks.
No forbidden input or pairs file was read; nothing was pushed.

Implementation and supported contract

A session is identified exactly and has a locked, hash-linked append-only event
journal. The ledger reconstructs ordered source receipts, immutable definitions,
turns, places, versions, pending calls, effects, mutation reservations and aliases.
Only settled responses paired to admitted PreToolUse IDs create receipts. Replayed,
mismatched, denied, pending, truncated and background observations cannot pay a
source obligation. Empty complete content and attributable nonzero completed
probe responses are valid. Writes and unimported worker answers are never originals.
Read-back of a session-written subject defaults to relay origin; a trusted host
can explicitly attest source origin. Outstanding or partially failed mutations
invalidate current evidence; only attested no-effect clearance releases failures.

The host-owned makoto envelope is trusted instrumentation, outside tool_input.
It supplies identities, origin roles, selector completeness, versions, points,
invocation digests, dependencies and affected subjects for arbitrary tool effects.
Native paths are lexically canonical within cwd; verified symlink/transfer aliases
require host mappings. URL queries/fragments and typed authorities remain distinct.
No tool response, file, command or source is independently executed or probed by
this detector. Cross-session original-receipt imports are not implemented; separate
session IDs cannot share receipts. Unsupported general Bash subject/effect coverage
is recorded as unknown, separate from missing-reading and transport errors.

Declared grammar

makoto-basis: source=<subject>[,..]; second=<subject>@<point>[,..]; act=<command>-><subject>[,..]; def=<definition id>:<subject>[,..]

A tool description or leading content/command comment carries the line. A final
message carries a standalone line. MultiEdit and NotebookEdit can use description.
An empty basis line declares a novel output. Every declared source requires a
current original source reading this turn. second resolves a host named point or
an exact revision and retains the first observation as its initial point. def
requires prior operator/host registration; content disagreement never triggers
SPEC. act matches exact command/context plus its paired subject response; general
commands need wrapper invocation/reading receipts. Commas and semicolons delimit
this compact grammar; richer commands/selectors use host obligations. A missing
line, invalid field or understated traced value is an explicit contract hold.

Inferred structural coverage

Content names are bound to exact ledger subjects using absolute and cwd-relative
path spellings, URL identities and typed host manifests. Recorded mutations also
establish subjects, so a newly written file named before any read remains unpaid.
Trace values include paths, URLs, id: identifiers, hexadecimal identifiers and
numbers of at least three digits. Values observed only in admitted assistant
answers, worker relays or session-written content cannot replace this turn's
original source response. Named path/URL identity obligations are separate from
copy-value obligations. A recorded mutation adds the prior and destination points
and requires a read after its settlement. Transfers need host identity aliases.
SPEC and SWITCH are exact only when the host supplies their obligation identity,
held definition/revision or invocation selector/input digest respectively.

Prevention and delivery

Every dependent PreToolUse is checked before admission and effect reservation.
Bash git commit/push recognition handles global git options, leading basis
comments and shell command boundaries. Arbitrary shell wrappers, aliases and
effects require trusted host adapters; shell semantics are not guessed.
All simultaneous unpaid families are retained in the audit row, along with the
output's obligation/receipt snapshot. Repeated unpaid Stop attempts still block;
stop_hook_active_unpaid records the retry rather than suppressing enforcement.
Malformed input, missing session/tool identity and corrupted journal data fail
closed as transport/contract errors, not as invented shape findings.

Native Stop is wired as the requested final gate. This build has not independently
validated another host's Stop-before-delivery timing. tools/deliver.py demonstrates
an actual stdout interception: denied final bytes never reach stdout, while a
paid final is emitted. It is a host integration example, not an installed Claude
interception. Hosts must apply denies before tool side effects and blocks before
final delivery. The suite's delivery-marker probe proves the included wrapper.

Validation and scope

python3 -m pytest -q tests: 97 passed in 4.13 seconds, below the 15-second bar.
The 16 isolated live cases form a present/absent pair for every family under each
adapter. Declared plants exercise basis syntax itself; inferred SPEC/SWITCH plants
use exact host obligations. Additional controls cover every write/final/git gate,
repeated holds, host turn changes, region/query/representation selectors, empty
content, nonzero responses, immutable definition revisions, mutation epochs,
pending/failed mutations, partial failures, relay origins, replay/mismatched IDs,
session separation, typed authorities, transfer aliases, multiple findings,
corruption, malformed envelopes and destination read-back. Applicable lifecycle,
audit, packaging and subtraction regression assertions were retained.

These are generated plants built from SHAPES.md, not any external test set.
No supplied pairs file was run. No 4,096-session construction campaign, mutation
certificate campaign, independent real-transcript grading, production latency
benchmark or universal 100%-accuracy claim is made. The structural record contract
cannot supply absent instrumentation or determine arbitrary prose dependencies.
The historical 74 issue names were read only as the specified family inventory;
no case vocabulary was imported into predicates or obligation inference.

Grading entry

python3 /home/user/build/makoto/tools/run_pairs.py PAIRS.json --adapter declared|inferred

The implementation accepts a session list or a sessions wrapper. Each session has
id, events, zero-based step_index and optional files mapping relative paths to
text. It writes files only under a temporary cwd, uses a fresh state directory
per session, serializes every event through python -m makoto2 in plugin/, and
prints the selected step's held flag plus its actual response. It never executes
recorded commands or opens recorded subjects. The suite calls the driver only
with self-authored in-memory events, never a pairs file.

Inventory and commits

NOLOSS-MAP.tsv has 482 explicit file/function/config/row inventory entries,
including every removed runtime/test file and every removed baseline function.
29 files were removed relative to e8032ec: 9 legacy runtime files and 20 old test
files. Historical evidence, quote pins and receipts remain in the repository.
Packaging/lifecycle utilities stay outside the four-shape decision engine.

Branch: shapes. Author: Clear-Sights <clear-sights@users.noreply.github.com>.
There are four commits after e8032ec: two inherited build/WIP commits and two
resume commits (implementation/tests, then reviewable report/inventory).
The environment's signing backend was unavailable, so resume commits are unsigned.
There are no AI attribution lines and no push was performed.

The canonical requested outputs are /home/user/build/REPORT.md and
/home/user/build/NOLOSS-MAP.tsv; identical copies are committed under makoto/docs/.
